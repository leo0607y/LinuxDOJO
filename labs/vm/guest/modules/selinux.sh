#!/bin/bash
# title: SELinux enforcing のまま AVC 拒否を fcontext/restorecon/ブール値で直す (RHEL系)
# roles: app
# Guest-only, RHEL family only (Rocky/AlmaLinux/RHEL/CentOS). Never disables SELinux or sets permissive.
# Owns only: /srv/dojo-se, /etc/httpd/conf.d/zz-dojo-se.conf, dojo-se-backend.service, one fcontext rule, httpd_can_network_connect.

_se_ctx() {
    [[ ${LAB_ID:-} == selinux && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/selinux ]] || { echo 'selinux: unexpected lab context' >&2; return 1; }
    local id
    id=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-unknown}")
    case $id in
        rocky|almalinux|rhel|centos) ;;
        *) echo "${id:-unknown}: this lab needs a RHEL-family VM" >&2; return 1 ;;
    esac
    SE_ROOT=/srv/dojo-se
    SE_SITE=$SE_ROOT/site
    SE_CONF=/etc/httpd/conf.d/zz-dojo-se.conf
    SE_UNIT=/etc/systemd/system/dojo-se-backend.service
    SE_BOOL=httpd_can_network_connect
    SE_MARK='# LinuxDOJO VM module: selinux'
    [[ ! -L $SE_ROOT && ! -L $SE_SITE && ! -L $SE_CONF && ! -L $SE_UNIT ]] || { echo 'selinux: unexpected lab context (symlink)' >&2; return 1; }
    if [[ -e $SE_CONF ]] && ! grep -qx "$SE_MARK" "$SE_CONF"; then echo '別用途の設定は変更しません。' >&2; return 1; fi
    if [[ -e $SE_UNIT ]] && ! grep -qx "$SE_MARK" "$SE_UNIT"; then echo '別用途のunitは変更しません。' >&2; return 1; fi
}

_se_probe_site() { curl -fsS -m3 http://127.0.0.1:8008/index.html 2>/dev/null | grep -q 'linuxdojo-selinux-site'; }
_se_probe_api()  { curl -fsS -m3 http://127.0.0.1:8008/api/health 2>/dev/null | grep -q 'linuxdojo-selinux-backend'; }

lab_setup() {
    _se_ctx || return 1
    local c
    for c in getenforce setenforce semanage restorecon setsebool getsebool ausearch curl python3 httpd; do
        command -v "$c" >/dev/null || { echo "$c が必要です (dnf install httpd policycoreutils-python-utils audit curl python3)。" >&2; return 1; }
    done
    [[ $(getenforce) == Enforcing ]] || { echo 'SELinux が Enforcing ではありません。setenforce 1 してから開始してください(この実習は無効化しません)。' >&2; return 1; }
    systemctl is-active --quiet auditd || { echo 'auditd が動いていません(AVC を読むために必要)。' >&2; return 1; }
    if [[ ! -e $SE_CONF ]] && { systemctl is-active --quiet httpd || systemctl is-enabled --quiet httpd; }; then
        echo '既存の httpd が稼働/有効です。他用途のサービスを壊さないため開始しません。' >&2; return 1
    fi
    [[ ! -e $SE_ROOT ]] || [[ -f $LAB_STATE/created ]] || { echo "$SE_ROOT が既にあります。上書きしません。" >&2; return 1; }
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" 2>/dev/null || true
    getsebool "$SE_BOOL" | awk '{print $3}' > "$LAB_STATE/orig-bool"
    install -d -m 755 "$SE_SITE" "$LAB_STATE/backend"
    printf '<html>linuxdojo-selinux-site</html>\n' > "$SE_SITE/index.html"
    printf 'linuxdojo-selinux-backend\n' > "$LAB_STATE/backend/health"
    chmod 644 "$SE_SITE/index.html" "$LAB_STATE/backend/health"
    cat > "$SE_UNIT" <<UNIT
$SE_MARK
[Unit]
Description=LinuxDOJO SELinux lab backend
[Service]
User=nobody
ExecStart=/usr/bin/python3 -m http.server 18091 --bind 127.0.0.1 --directory $LAB_STATE/backend
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    cat > "$SE_CONF" <<CONF
$SE_MARK
Listen 8008
<VirtualHost *:8008>
    DocumentRoot $SE_SITE
    <Directory $SE_SITE>
        Require all granted
    </Directory>
    ProxyPass /api/ http://127.0.0.1:18091/
    ProxyPassReverse /api/ http://127.0.0.1:18091/
</VirtualHost>
CONF
    sha256sum "$SE_CONF" | awk '{print $1}' > "$LAB_STATE/conf.sha"
    : > "$LAB_STATE/created"
    systemctl daemon-reload
    systemctl enable --now dojo-se-backend.service || return 1
    httpd -t 2>/dev/null || { echo 'httpd の設定検査に失敗しました(mod_proxy が必要)。' >&2; return 1; }
    systemctl restart httpd || return 1
    cat > "$LAB_STATE/TASKS.txt" <<'TASKS'
httpd がポート 8008 で非標準ディレクトリ /srv/dojo-se/site を配信し、/api/ を 127.0.0.1:18091 へ中継します。
SELinux は Enforcing のまま直すこと。setenforce 0 / permissive / SELINUX=disabled は不合格です。
1. sudo dojo-vm-lab selinux break で故障状態にする
2. curl -i http://127.0.0.1:8008/index.html と /api/health を試す。どちらも失敗するはず
3. getenforce, ls -dZ /srv/dojo-se/site, ps -eZ | grep httpd で現状を確認
4. sudo ausearch -m avc -ts recent で AVC を読む (scontext / tcontext / tclass / permissive=0)。
   必要なら audit2why で理由を見る。ファイル由来の拒否とネットワーク接続由来の拒否は別物
5. ファイル: 一時的な chcon ではなく、永続的な規則 (semanage fcontext) を足してから restorecon -Rv で適用
6. 接続: 該当するブール値を調べ (getsebool -a | grep httpd, semanage boolean -l)、再起動後も残る形 (-P) で設定
7. sudo dojo-vm-lab selinux check
TASKS
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _se_ctx || return 1
    [[ -f $LAB_STATE/created ]] || { echo '先に setup を実行してください。' >&2; return 1; }
    [[ $(getenforce) == Enforcing ]] || { echo 'SELinux が Enforcing ではありません。setenforce 1 してください。' >&2; return 1; }
    local l
    while read -r l; do
        if [[ -n $l ]]; then semanage fcontext -d "$l" 2>/dev/null || true; fi
    done < <(semanage fcontext -l -C 2>/dev/null | awk -v p="$SE_SITE" 'index($1, p) == 1 {print $1}')
    restorecon -RF "$SE_ROOT" || return 1
    setsebool -P "$SE_BOOL" off || return 1
    systemctl restart httpd || return 1
    : > "$LAB_STATE/broken"
    echo "故障状態にしました(ファイルのラベルとブール値)。curl で 403/503 を確認してください。"
}

lab_check() {
    _se_ctx || return 1
    [[ -f $LAB_STATE/broken ]] || { echo 'break済みの記録がありません。先に break を実行してください。' >&2; return 1; }
    local mode cfg
    mode=$(getenforce)
    [[ $mode == Enforcing ]] || { echo "SELinux が $mode です。Enforcing のまま直してください。" >&2; return 1; }
    cfg=$(sed -n 's/^SELINUX=//p' /etc/selinux/config 2>/dev/null | head -1)
    [[ $cfg == enforcing ]] || { echo "/etc/selinux/config の SELINUX=$cfg です。enforcing に戻してください。" >&2; return 1; }
    if semanage permissive -l 2>/dev/null | grep -Eq '(^|[[:space:]])httpd_t([[:space:]]|$)'; then
        echo 'httpd_t が permissive ドメインにされています。解除してください。' >&2; return 1
    fi
    [[ $(sha256sum "$SE_CONF" 2>/dev/null | awk '{print $1}') == "$(cat "$LAB_STATE/conf.sha")" ]] || { echo 'httpd 設定が変更されています。SELinux 側で直してください。' >&2; return 1; }
    [[ -d $SE_SITE ]] || return 1
    systemctl is-active --quiet httpd dojo-se-backend.service || { echo 'httpd/backend が動いていません。' >&2; return 1; }
    ps -eZ 2>/dev/null | grep -E 'httpd' | grep -q 'httpd_t' || { echo 'httpd が httpd_t で動いていません。' >&2; return 1; }
    semanage fcontext -l -C 2>/dev/null | grep -F "$SE_SITE" | grep -Eq 'httpd_[a-z_]*content_t' \
        || { echo "$SE_SITE の永続的な fcontext 規則(httpd_*content_t)がありません。chcon だけでは再ラベルで消えます。" >&2; return 1; }
    [[ -z $(restorecon -RFn -v "$SE_ROOT" 2>/dev/null) ]] || { echo '現在のラベルが規則と一致しません。restorecon -R を実行してください。' >&2; return 1; }
    [[ $(getsebool "$SE_BOOL" | awk '{print $3}') == on ]] || { echo "$SE_BOOL が現在 off です。" >&2; return 1; }
    semanage boolean -l -C 2>/dev/null | grep -Eq "^$SE_BOOL[[:space:]]+\(on[[:space:]]*,[[:space:]]*on\)" \
        || { echo "$SE_BOOL が永続化されていません(setsebool -P)。" >&2; return 1; }
    local d t
    d=$(LC_ALL=C date '+%m/%d/%Y'); t=$(LC_ALL=C date '+%H:%M:%S')
    sleep 1
    _se_probe_site || { echo "http://127.0.0.1:8008/index.html が取得できません。" >&2; return 1; }
    _se_probe_api || { echo "http://127.0.0.1:8008/api/health が取得できません。" >&2; return 1; }
    sleep 1
    if LC_ALL=C ausearch -m avc,user_avc -ts "$d" "$t" 2>/dev/null | grep -q 'httpd_t'; then
        echo '確認中に httpd_t の AVC 拒否が新しく記録されました。ausearch で確認してください。' >&2; return 1
    fi
    echo 'Enforcing のまま、永続的な fcontext とブール値で復旧し、確認中に新しい AVC もありません。'
}

lab_reset() {
    _se_ctx || return 1
    if [[ -f $SE_CONF ]] && grep -qx "$SE_MARK" "$SE_CONF"; then systemctl stop httpd 2>/dev/null || true; rm -f "$SE_CONF"; fi
    if [[ -f $SE_UNIT ]] && grep -qx "$SE_MARK" "$SE_UNIT"; then
        systemctl disable --now dojo-se-backend.service 2>/dev/null || true
        rm -f "$SE_UNIT"
    fi
    systemctl daemon-reload
    local l
    while read -r l; do
        if [[ -n $l ]]; then semanage fcontext -d "$l" 2>/dev/null || true; fi
    done < <(semanage fcontext -l -C 2>/dev/null | awk -v p="$SE_SITE" 'index($1, p) == 1 {print $1}')
    if [[ -f $LAB_STATE/orig-bool ]]; then
        setsebool -P "$SE_BOOL" "$(cat "$LAB_STATE/orig-bool")" 2>/dev/null || true
    fi
    if [[ -f $LAB_STATE/created ]]; then rm -rf "${SE_ROOT:?}"; fi
    rm -rf "${LAB_STATE:?}/backend"
    rm -f "${LAB_STATE:?}/created" "${LAB_STATE:?}/broken" "${LAB_STATE:?}/conf.sha" "${LAB_STATE:?}/orig-bool" "${LAB_STATE:?}/TASKS.txt"
    echo '専用 httpd 設定・backend・fcontext 規則・ブール値・/srv/dojo-se を元に戻しました。'
}
