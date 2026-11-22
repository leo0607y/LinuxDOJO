# title: Apache専用インスタンス: 名前ベースvhost・.htaccess・Basic認証・書き換え・障害復旧
# roles: app
# Dedicated apache2 process on 127.0.0.1:8088 with its own config root (/srv/dojo-apache). The OS apache2 service is never touched.
# apache2 and apache2-utils are NOT part of the base image: setup refuses with an install instruction when missing.

_apache_paths() {
    [[ ${LAB_ID:-} == apache && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/apache ]] || { echo 'apache: unexpected lab context' >&2; return 1; }
    A_ROOT=/srv/dojo-apache
    A_CONF=$A_ROOT/conf/apache2.conf
    A_UNIT=/etc/systemd/system/dojo-apache.service
    A_PORT=8088
    A_ALPHA=alpha.dojo.test
    A_BETA=beta.dojo.test
    [[ ! -L $A_ROOT && ! -L $A_UNIT ]] || return 1
}

_apache_tools() {
    local missing=() t
    for t in apache2ctl apache2 htpasswd curl; do
        command -v "$t" >/dev/null || missing+=("$t")
    done
    if ((${#missing[@]})); then
        echo "必要なコマンドがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y apache2 apache2-utils'
        return 1
    fi
    getent passwd www-data >/dev/null || { echo 'www-dataユーザーがありません。'; return 1; }
}

# $1=host $2=path, rest = extra curl args. Prints "CODE REDIRECT"; body goes to $LAB_STATE/last-body.
_apache_get() {
    local host=$1 path=$2; shift 2
    curl -s --max-time 5 -o "$LAB_STATE/last-body" -w '%{http_code} %{redirect_url}' \
        --resolve "$host:$A_PORT:127.0.0.1" "$@" "http://$host:$A_PORT$path" 2>/dev/null || echo '000 '
}

_apache_expect() { # $1=host $2=path $3=expected code, rest curl args
    local host=$1 path=$2 want=$3; shift 3
    local out; out=$(_apache_get "$host" "$path" "$@")
    [[ ${out%% *} == "$want" ]] || { echo "$host$path は HTTP $want のはずが ${out%% *} です。"; return 1; }
}

_apache_syntax() { apache2ctl -f "$A_CONF" -t >"$LAB_STATE/syntax.txt" 2>&1; }

_apache_verify() {
    local pw out tok i found
    systemctl is-active --quiet dojo-apache.service || { echo 'dojo-apache.serviceが動いていません。journalctl -u dojo-apacheを確認します。'; return 1; }
    _apache_syntax || { echo 'apache2ctl -t が失敗します:'; cat "$LAB_STATE/syntax.txt"; return 1; }
    [[ $(stat -c %a "$A_ROOT/www/alpha") =~ [0-7][0-7][0-5] ]] || { echo 'alphaのDocumentRootが全員書き込み可です。必要最小限の権限にします。'; return 1; }
    pw=$(cat "$LAB_STATE/admin.pw")
    # name-based virtual hosts
    _apache_expect "$A_ALPHA" / 200 || return 1
    grep -q "$(cat "$LAB_STATE/alpha.token")" "$LAB_STATE/last-body" || { echo "$A_ALPHA が alpha の内容を返していません。"; return 1; }
    _apache_expect "$A_BETA" / 200 || return 1
    grep -q "$(cat "$LAB_STATE/beta.token")" "$LAB_STATE/last-body" || { echo "$A_BETA が beta の内容を返していません。"; return 1; }
    # redirect (.htaccess + mod_rewrite)
    out=$(_apache_get "$A_ALPHA" /old.html)
    [[ ${out%% *} == 301 && ${out#* } == */new.html ]] || { echo "/old.html は /new.html への 301 のはずが: $out"; return 1; }
    _apache_expect "$A_ALPHA" /new.html 200 || return 1
    # basic auth
    _apache_expect "$A_ALPHA" /admin/ 401 || return 1
    _apache_expect "$A_ALPHA" /admin/ 401 -u "dojo-admin:wrong-$pw" || return 1
    _apache_expect "$A_ALPHA" /admin/ 200 -u "dojo-admin:$pw" || return 1
    # .htaccess really drives the redirect (AllowOverride must be enabled)
    [[ -s $A_ROOT/www/alpha/.htaccess ]] || { echo 'alphaの.htaccessがありません。リダイレクトは.htaccessで行います。'; return 1; }
    mv -- "$A_ROOT/www/alpha/.htaccess" "$LAB_STATE/htaccess.aside"
    out=$(_apache_get "$A_ALPHA" /old.html)
    mv -- "$LAB_STATE/htaccess.aside" "$A_ROOT/www/alpha/.htaccess"
    [[ ${out%% *} == 404 ]] || { echo '.htaccessを外しても/old.htmlがリダイレクトされます。vhost側ではなく.htaccess(AllowOverride)で実現してください。'; return 1; }
    # per-vhost logs, judged by requests made right now
    tok=$(cat /proc/sys/kernel/random/uuid)
    _apache_get "$A_ALPHA" "/dojo-check-a-$tok" >/dev/null
    _apache_get "$A_BETA" "/dojo-check-b-$tok" >/dev/null
    found=0
    for i in 1 2 3 4 5 6; do
        if grep -q "dojo-check-a-$tok" "$A_ROOT/logs/alpha-access.log" 2>/dev/null && grep -q "dojo-check-b-$tok" "$A_ROOT/logs/beta-access.log" 2>/dev/null; then found=1; break; fi
        sleep 0.5
    done
    ((found)) || { echo 'logs/alpha-access.log と logs/beta-access.log にvhostごとのアクセスが記録されていません。'; return 1; }
    if grep -q "dojo-check-b-$tok" "$A_ROOT/logs/alpha-access.log" || grep -q "dojo-check-a-$tok" "$A_ROOT/logs/beta-access.log"; then
        echo 'vhostのログが混ざっています。'; return 1
    fi
    return 0
}

lab_setup() {
    _apache_paths || return 1
    _apache_tools || return 1
    [[ ! -e $A_ROOT && ! -e $A_UNIT ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if ss -ltn "sport = :$A_PORT" 2>/dev/null | grep -q LISTEN; then echo "ポート $A_PORT は使用中です。"; return 1; fi
    local d m mods='mpm_event authn_core authn_file authz_core authz_host authz_user auth_basic alias dir mime log_config rewrite unixd headers'
    for d in conf sites conf.d logs run www/default www/alpha/admin www/beta; do install -d -m 0755 "$A_ROOT/$d"; done
    touch "$LAB_STATE/owns-files"
    echo "dojo-alpha-$(cat /proc/sys/kernel/random/uuid)" > "$LAB_STATE/alpha.token"
    echo "dojo-beta-$(cat /proc/sys/kernel/random/uuid)" > "$LAB_STATE/beta.token"
    openssl rand -hex 8 > "$LAB_STATE/admin.pw"; chmod 0600 "$LAB_STATE/admin.pw"
    echo "<h1>default</h1>" > "$A_ROOT/www/default/index.html"
    echo "<h1>$(cat "$LAB_STATE/alpha.token")</h1>" > "$A_ROOT/www/alpha/index.html"
    echo '<h1>new page</h1>' > "$A_ROOT/www/alpha/new.html"
    echo '<h1>admin area</h1>' > "$A_ROOT/www/alpha/admin/index.html"
    echo "<h1>$(cat "$LAB_STATE/beta.token")</h1>" > "$A_ROOT/www/beta/index.html"
    chmod -R a+rX "$A_ROOT/www"
    {
        cat <<CONF
ServerRoot "$A_ROOT"
ServerName dojo-apache.local
Listen 127.0.0.1:$A_PORT
PidFile $A_ROOT/run/apache2.pid
DefaultRuntimeDir $A_ROOT/run
Mutex file:$A_ROOT/run default
User www-data
Group www-data
ErrorLog $A_ROOT/logs/error.log
LogLevel warn
LogFormat "%h %t \"%r\" %>s %b" dojo
TypesConfig /etc/mime.types
HostnameLookups Off
AccessFileName .htaccess
CONF
        # Debian/Ubuntu compile some modules in (log_config, unixd): loading them again is a syntax error.
        local builtin; builtin=$(apache2 -l 2>/dev/null)
        for m in $mods; do
            grep -q "mod_$m\.c" <<<"$builtin" && continue
            echo "LoadModule ${m}_module /usr/lib/apache2/modules/mod_$m.so"
        done
        cat <<CONF
<FilesMatch "^\.ht">
    Require all denied
</FilesMatch>
<Directory />
    Options FollowSymLinks
    AllowOverride None
    Require all denied
</Directory>
DocumentRoot "$A_ROOT/www/default"
<Directory "$A_ROOT/www">
    Require all granted
</Directory>
IncludeOptional conf.d/*.conf
IncludeOptional sites/*.conf
CONF
    } > "$A_CONF"
    apache2ctl -f "$A_CONF" -t >"$LAB_STATE/syntax.txt" 2>&1 || { cat "$LAB_STATE/syntax.txt"; echo '基本設定が検証できません。'; return 1; }
    cat > "$A_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated Apache exercise (127.0.0.1:$A_PORT)
After=network.target
[Service]
ExecStart=/usr/sbin/apache2 -f $A_CONF -D FOREGROUND
ExecReload=/usr/sbin/apache2 -f $A_CONF -k graceful
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now dojo-apache.service
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用Apache(設定ルート $A_ROOT, 127.0.0.1:$A_PORT)。OS標準のapache2は触りません。
全体設定は $A_CONF 。末尾で sites/*.conf を読みます。ここにvhostを書きます。
1. sites/alpha.conf と sites/beta.conf に名前ベースvhostを作る
   ServerName は $A_ALPHA と $A_BETA、DocumentRoot は www/alpha と www/beta、
   ログは logs/alpha-access.log / logs/beta-access.log (LogFormat名は dojo)、vhostごとに別ファイル。
   確認: curl --resolve $A_ALPHA:$A_PORT:127.0.0.1 http://$A_ALPHA:$A_PORT/
2. www/alpha/.htaccess で /old.html を /new.html へ 301 リダイレクト(mod_rewrite)。
   .htaccessを有効にするには vhost の <Directory> で何を許可する? (AllowOverride)
3. www/alpha/admin/ をBasic認証で保護。ユーザー dojo-admin、
   パスワードは sudo cat $LAB_STATE/admin.pw 。htpasswdで $A_ROOT/htpasswd を作る(DocumentRoot外)。
4. 変更のたび apache2ctl -f $A_CONF -t で構文確認し、sudo systemctl reload dojo-apache
   エラーは $A_ROOT/logs/error.log 。
5. sudo dojo-vm-lab apache break   (構文エラーと権限不備を仕込みます。基本機能が全部通っている時だけ)
   curlの応答コード、apache2ctl -t、error.log、ls -ld で原因を特定して直す。権限の広げすぎ(全員書込可)は不正解。
6. sudo dojo-vm-lab apache check
7. 終了後 sudo dojo-vm-lab apache reset
TASK
    echo "手順: $LAB_STATE/TASKS.txt"; cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _apache_paths || return 1
    [[ -f $LAB_STATE/owns-files && ! -f $LAB_STATE/fault ]] || { echo '初期化済みで未breakの状態で実行します。'; return 1; }
    _apache_verify || { echo 'まず手順1-4を完了し、全部の応答が正しくなるようにします。'; return 1; }
    stat -c %a "$A_ROOT/www/alpha" > "$LAB_STATE/alpha.mode"
    chmod 0700 "$A_ROOT/www/alpha"
    cat > "$A_ROOT/conf.d/zz-lab.conf" <<CONF
<Directory "$A_ROOT/www/beta">
    Optionz Indexes
</Directory>
CONF
    systemctl reload dojo-apache.service 2>/dev/null || true
    if _apache_syntax || [[ $(_apache_get "$A_ALPHA" /) != 403* ]]; then
        chmod "$(cat "$LAB_STATE/alpha.mode")" "$A_ROOT/www/alpha"; rm -f -- "$A_ROOT/conf.d/zz-lab.conf"
        echo '障害を再現できませんでした。元に戻しました。'; return 1
    fi
    touch "$LAB_STATE/fault"
    echo "障害を仕込みました。reloadが失敗し、$A_ALPHA が 403 になります。原因を調べて直します。"
}

lab_check() {
    _apache_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まず基本機能を作り、breakで障害を作ります。'; return 1; }
    _apache_verify || return 1
    echo 'PASS: vhost・.htaccessリダイレクト・Basic認証・vhost別ログ・構文(apache2ctl -t)・403の復旧を実際のcurl応答で確認しました。'
}

lab_reset() {
    _apache_paths || return 1
    [[ -f $LAB_STATE/owns-files ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    systemctl disable --now dojo-apache.service 2>/dev/null || true
    rm -f -- "$A_UNIT"
    systemctl daemon-reload
    rm -rf -- "${A_ROOT:?}"
    rm -f -- "${LAB_STATE:?}/owns-files" "${LAB_STATE:?}/fault" "${LAB_STATE:?}/alpha.token" "${LAB_STATE:?}/beta.token" \
        "${LAB_STATE:?}/admin.pw" "${LAB_STATE:?}/alpha.mode" "${LAB_STATE:?}/last-body" "${LAB_STATE:?}/syntax.txt" \
        "${LAB_STATE:?}/htaccess.aside" "${LAB_STATE:?}/TASKS.txt"
    echo '専用Apache(設定・ログ・サイト)を削除しました。OS標準のapache2は変更していません。'
}
