#!/bin/bash
# title: 専用smbdでSambaの共有を設計し、smbclientで匿名拒否・権限・force groupを実接続で確認する
# roles: app
# Guest-only. Dedicated smbd (dojo-smbd.service) on 127.0.0.1:1445 with its own config, passdb and
# state directories. /etc/samba, the system smbd/nmbd and system Samba databases are never touched.
# Needs: sudo apt-get install -y samba smbclient   (not part of the base image)

_sm_paths() {
    [[ ${LAB_ID:-} == samba && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/samba ]] || { echo 'samba: unexpected lab context' >&2; return 1; }
    SM_UNIT=/etc/systemd/system/dojo-smbd.service
    SM_DIR=/etc/dojo-samba
    SM_CONF=$SM_DIR/smb.conf
    SM_VAR=/var/lib/dojo-samba
    SM_DATA=/srv/dojo-samba
    SM_GROUP=dojo-smbusers
    SM_USER1=dojo-smbalice   # member of dojo-smbusers
    SM_USER2=dojo-smbbob     # NOT a member
    SM_PORT=1445
    [[ ! -L $SM_UNIT && ! -L $SM_DIR && ! -L $SM_CONF && ! -L $SM_VAR && ! -L $SM_DATA ]] || return 1
}

_sm_global() {
    cat <<CONF
[global]
   workgroup = DOJO
   server role = standalone server
   server string = LinuxDOJO dedicated Samba
   disable netbios = yes
   smb ports = $SM_PORT
   bind interfaces only = yes
   interfaces = 127.0.0.1
   lock directory = $SM_VAR/lock
   state directory = $SM_VAR/state
   cache directory = $SM_VAR/cache
   private dir = $SM_VAR/private
   pid directory = $SM_VAR/pid
   passdb backend = tdbsam:$SM_VAR/private/passdb.tdb
   log file = $SM_VAR/log/log.%m
   max log size = 1000
   load printers = no
   printcap name = /dev/null
   disable spoolss = yes
   map to guest = never
CONF
}

_sm_have_tools() {
    local t
    for t in smbd testparm smbclient smbpasswd pdbedit; do command -v "$t" >/dev/null 2>&1 || return 1; done
}

# _sm_cli OUT TARGET CRED COMMAND   (CRED: anon or user%password)
_sm_cli() {
    local out=$1 target=$2 cred=$3 cmd=$4
    if [[ $cred == anon ]]; then
        timeout 20 smbclient -s "$LAB_STATE/client.conf" "$target" -p "$SM_PORT" -N -c "$cmd" > "$out" 2>&1
    else
        timeout 20 smbclient -s "$LAB_STATE/client.conf" "$target" -p "$SM_PORT" -U "$cred" -c "$cmd" > "$out" 2>&1
    fi
}

_sm_denied() { grep -Eq 'NT_STATUS_(ACCESS_DENIED|LOGON_FAILURE|ACCESS_VIOLATION|NO_SUCH_USER|WRONG_PASSWORD)' "$1"; }

_sm_wait_up() {
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do
        timeout 10 smbclient -s "$LAB_STATE/client.conf" -L //127.0.0.1 -p "$SM_PORT" -N >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

_sm_cred() { # 1|2 -> user%pw
    local u=$SM_USER1 f=$LAB_STATE/pass1
    [[ $1 == 2 ]] && { u=$SM_USER2; f=$LAB_STATE/pass2; }
    printf '%s%%%s' "$u" "$(cat "$f")"
}

_sm_passdb_has() { pdbedit -s "$SM_CONF" -L 2>/dev/null | cut -d: -f1 | grep -qx "$1"; }

_sm_param() { # [section] name -> value
    local section=$1 name=$2
    if [[ -n $section ]]; then
        testparm -s --section-name="$section" --parameter-name="$name" "$SM_CONF" 2>/dev/null </dev/null
    else
        testparm -s --parameter-name="$name" "$SM_CONF" 2>/dev/null </dev/null
    fi
}

lab_setup() {
    _sm_paths || return 1
    if ! _sm_have_tools; then
        echo 'sambaとsmbclientが未導入です。次を実行してから再度setupしてください:'
        echo '  sudo apt-get install -y samba smbclient'
        return 1
    fi
    [[ ! -e $SM_UNIT && ! -e $SM_DIR && ! -e $SM_VAR && ! -e $SM_DATA ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if getent group "$SM_GROUP" >/dev/null || getent passwd "$SM_USER1" >/dev/null || getent passwd "$SM_USER2" >/dev/null; then
        echo '専用のユーザー/グループ名が使用済みです。'; return 1
    fi
    if ss -ltn 2>/dev/null | grep -q ":$SM_PORT "; then echo "ポート$SM_PORTが使用中です。"; return 1; fi
    local smbd_bin p1 p2
    smbd_bin=$(command -v smbd)
    groupadd --system "$SM_GROUP"
    : > "$LAB_STATE/owns-samba"
    echo group >> "$LAB_STATE/owns-samba"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SM_USER1"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SM_USER2"
    echo users >> "$LAB_STATE/owns-samba"
    usermod -aG "$SM_GROUP" "$SM_USER1"
    p1=$(openssl rand -hex 8); p2=$(openssl rand -hex 8)
    ( umask 077; printf '%s\n' "$p1" > "$LAB_STATE/pass1"; printf '%s\n' "$p2" > "$LAB_STATE/pass2" )
    printf '[global]\n   workgroup = DOJO\n' > "$LAB_STATE/client.conf"
    install -d -m 0755 "$SM_DIR"
    install -d -m 0755 "$SM_VAR" "$SM_VAR/lock" "$SM_VAR/cache" "$SM_VAR/pid" "$SM_VAR/log"
    install -d -m 0755 "$SM_VAR/state"
    install -d -m 0700 "$SM_VAR/private"
    install -d -m 0755 "$SM_DATA" "$SM_DATA/public"
    install -d -o root -g root -m 0755 "$SM_DATA/private"
    printf 'LinuxDOJO public share\n' > "$SM_DATA/public/readme.txt"
    chmod 0644 "$SM_DATA/public/readme.txt"
    {
        _sm_global
        echo
        echo '# ここに [public] と [private] を書く（手順は TASKS.txt）'
    } > "$SM_CONF"
    sha256sum "$SM_CONF" > /dev/null
    testparm -s "$SM_CONF" >/dev/null 2>&1 </dev/null || { echo '初期smb.confが不正です。'; return 1; }
    cat > "$SM_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated Samba exercise (127.0.0.1:$SM_PORT)
After=network.target
[Service]
Type=simple
ExecStart=$smbd_bin --foreground --no-process-group -s $SM_CONF
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$SM_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-smbd.service
    cat > "$LAB_STATE/TASKS.txt" <<TASK
この課題はapp VMで操作する。専用smbdは 127.0.0.1:$SM_PORT だけで待ち受ける（OS標準のsambaには触れない）。
設定: $SM_CONF   （[global]は固定。変更しない。-s でこの設定を指定して起動する dojo-smbd.service）
Linuxユーザー: $SM_USER1（グループ$SM_GROUPのメンバー）, $SM_USER2（メンバーではない）
パスワード（Samba用）: $LAB_STATE/pass1, pass2 （sudoで読む）
データ: $SM_DATA/public, $SM_DATA/private

1. $SM_CONF に共有を追加する。
   [public]  読み取り専用で誰でも（匿名可）参照できる。
   [private] 書き込み可。$SM_GROUP のメンバーだけ（valid users）。guestは不可。
             作成ファイルのグループは $SM_GROUP に固定し（force group）、otherには権限を与えない（create mask）。
2. testparm -s $SM_CONF で警告が出ないこと、実効値（testparm -sv）を確認する。
3. Sambaユーザーを専用passdbに登録する。Linuxユーザーは作成済み。-c で設定ファイルを指定すること。
   ヒント: printf 'PW\nPW\n' | sudo smbpasswd -c $SM_CONF -a -s USER   （両ユーザーとも登録）
   確認: sudo pdbedit -s $SM_CONF -L
4. sudo systemctl restart dojo-smbd.service
5. 実接続で確認する（-p $SM_PORT を忘れない）:
   smbclient -L //127.0.0.1 -p $SM_PORT -N
   smbclient //127.0.0.1/public  -p $SM_PORT -N -c 'ls'
   smbclient //127.0.0.1/private -p $SM_PORT -U USER%PW -c 'put FILE; ls'
   匿名でのprivate接続・publicへの書き込みが拒否されること、$SM_USER2 がprivateに入れないことも確認する。
6. 共有の設定が書き込み可でも、Linux側のディレクトリの所有者・モードが合わないと書けない。
   private の実ディレクトリ ($SM_DATA/private) を、共有設定に合わせて調整する（setgid も検討）。
7. sudo dojo-vm-lab samba break  （誤設定を入れる。\`testparm\` の警告と匿名/ゲスト接続を調べて直す）
8. sudo dojo-vm-lab samba check
9. 終了後 sudo dojo-vm-lab samba reset （専用smbd・passdb・ユーザー・データのみ削除）
TASK
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _sm_paths || return 1
    [[ -f $LAB_STATE/owns-samba && -f $LAB_STATE/pass1 && -f $SM_CONF ]] || { echo '先にsetupしてください。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo 'すでにbreak済みです。'; return 1; }
    testparm -s "$SM_CONF" >/dev/null 2>&1 </dev/null || { echo 'まずsmb.confを警告なく動く状態にします（testparm -s）。'; return 1; }
    _sm_passdb_has "$SM_USER1" && _sm_passdb_has "$SM_USER2" || { echo 'まず両ユーザーをsmbpasswd -a で専用passdbに登録します。'; return 1; }
    systemctl is-active --quiet dojo-smbd.service || { echo 'dojo-smbd.serviceを起動して動作確認してから進めます。'; return 1; }
    cp -p "$SM_CONF" "$LAB_STATE/smb.conf.learner"
    {
        _sm_global | sed 's/^   map to guest = never$/   map to guest = bad user/'
        cat <<CONF

[public]
   path = $SM_DATA/public
   read only = yes
   guest ok = yes

[private]
   path = $SM_DATA/private
   read only = no
   guest ok = yes
   valid usres = @$SM_GROUP
   force group = users
   create mask = 0666
CONF
    } > "$SM_CONF"
    chown root:"$SM_GROUP" "$SM_DATA/private"
    chmod 0755 "$SM_DATA/private"   # listable by guest (so the anonymous hole is real) but not group-writable
    systemctl restart dojo-smbd.service
    _sm_wait_up || { echo 'smbdが再起動しません。'; cp -p "$LAB_STATE/smb.conf.learner" "$SM_CONF"; systemctl restart dojo-smbd.service; return 1; }
    # The fault must be real: anonymous access to the private share has to succeed now.
    if ! _sm_cli "$LAB_STATE/break-probe.log" //127.0.0.1/private anon 'ls'; then
        echo '誤設定が効いていません。'
        cp -p "$LAB_STATE/smb.conf.learner" "$SM_CONF"; systemctl restart dojo-smbd.service
        return 1
    fi
    touch "$LAB_STATE/fault"
    echo '誤設定を入れました。testparm -s の警告、匿名でのprivate接続、ファイルのグループ/モード、実ディレクトリの権限を調べて直し、再起動してください。'
}

lab_check() {
    _sm_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/owns-samba ]] || { echo 'まずbreakで障害を作り、直してからcheckします。'; return 1; }
    [[ $(cut -d ' ' -f 1 "$LAB_STATE/unit.sha256") == $(sha256sum "$SM_UNIT" | cut -d ' ' -f 1) ]] || { echo 'dojo-smbd.serviceは変更しません。'; return 1; }
    # 1. testparm clean
    local err=$LAB_STATE/testparm.err
    if ! testparm -s "$SM_CONF" >/dev/null 2>"$err" </dev/null; then echo 'testparmが失敗します。'; return 1; fi
    if grep -v 'Weak crypto' "$err" | grep -Eiq 'warning|unknown parameter|ignoring|rejected|error|invalid'; then
        echo 'testparmが警告を出しています（パラメータの綴りや値）:'; grep -v 'Weak crypto' "$err" | head -5; return 1
    fi
    # 2. fixed [global] settings still in force
    local pair name want got
    for pair in 'smb ports=1445' 'bind interfaces only=Yes' 'interfaces=127.0.0.1' 'map to guest=Never' \
                "lock directory=$SM_VAR/lock" "state directory=$SM_VAR/state" "private dir=$SM_VAR/private" \
                "passdb backend=tdbsam:$SM_VAR/private/passdb.tdb"; do
        name=${pair%%=*}; want=${pair#*=}
        got=$(_sm_param '' "$name" | head -1)
        [[ $got == "$want" ]] || { echo "[global]の '$name' は $want のままにします（現在: ${got:-なし}）。"; return 1; }
    done
    # 3. effective share definitions
    [[ $(_sm_param private 'guest ok' | head -1) == No ]] || { echo 'privateでguest okを許可しません。'; return 1; }
    [[ $(_sm_param private 'read only' | head -1) == No ]] || { echo 'privateは書き込み可にします。'; return 1; }
    [[ $(_sm_param private 'force group' | head -1) == "$SM_GROUP" ]] || { echo "privateのforce groupは $SM_GROUP にします。"; return 1; }
    _sm_param private 'valid users' | grep -q "$SM_GROUP" || { echo "privateのvalid usersは @$SM_GROUP にします。"; return 1; }
    [[ $(_sm_param public 'read only' | head -1) == Yes ]] || { echo 'publicは読み取り専用にします。'; return 1; }
    # 4. passdb and running service
    _sm_passdb_has "$SM_USER1" && _sm_passdb_has "$SM_USER2" || { echo '両ユーザーが専用passdbに必要です（smbpasswd -c ... -a）。'; return 1; }
    systemctl restart dojo-smbd.service
    _sm_wait_up || { echo 'dojo-smbdが応答しません。journalctl -u dojo-smbd を確認。'; return 1; }
    local o=$LAB_STATE/check.out rnd pu1 pu2 owner group mode
    rnd=$(openssl rand -hex 4)
    printf 'probe-%s\n' "$rnd" > "$LAB_STATE/probe.txt"
    pu1=$(_sm_cred 1); pu2=$(_sm_cred 2)
    _sm_cleanup() { rm -f -- "$SM_DATA"/public/anon-"$rnd".txt "$SM_DATA"/public/member-"$rnd".txt "$SM_DATA"/private/*-"$rnd".txt "$LAB_STATE/probe.txt"; }
    # anonymous: list shows public, public is readable, not writable
    timeout 20 smbclient -s "$LAB_STATE/client.conf" -L //127.0.0.1 -p "$SM_PORT" -N > "$o" 2>&1 || true
    grep -Eq '^[[:space:]]*public[[:space:]]+Disk' "$o" || { echo '匿名の共有一覧にpublicが見えません。'; _sm_cleanup; return 1; }
    _sm_cli "$o" //127.0.0.1/public anon 'ls' && grep -q readme.txt "$o" || { echo '匿名でpublicを読めません。'; _sm_cleanup; return 1; }
    _sm_cli "$o" //127.0.0.1/public anon "lcd $LAB_STATE; put probe.txt anon-$rnd.txt" || true
    if [[ -e $SM_DATA/public/anon-$rnd.txt ]] || ! _sm_denied "$o"; then echo '匿名でpublicへ書き込めてしまいます。'; _sm_cleanup; return 1; fi
    # even an authenticated member may not write to the read-only public share
    _sm_cli "$o" //127.0.0.1/public "$pu1" "lcd $LAB_STATE; put probe.txt member-$rnd.txt" || true
    if [[ -e $SM_DATA/public/member-$rnd.txt ]] || ! _sm_denied "$o"; then echo 'publicは認証済みでも読み取り専用です。'; _sm_cleanup; return 1; fi
    # private: anonymous / unknown user (map to guest) / wrong password / non-member all refused
    _sm_cli "$o" //127.0.0.1/private anon "lcd $LAB_STATE; put probe.txt anon-$rnd.txt" || true
    if [[ -e $SM_DATA/private/anon-$rnd.txt ]] || ! _sm_denied "$o"; then echo '匿名でprivateにアクセスできてしまいます。'; _sm_cleanup; return 1; fi
    _sm_cli "$o" //127.0.0.1/private "nosuchuser-$rnd%x" "lcd $LAB_STATE; put probe.txt ghost-$rnd.txt" || true
    if [[ -e $SM_DATA/private/ghost-$rnd.txt ]] || ! _sm_denied "$o"; then echo '存在しないユーザーがゲスト扱いでprivateに入れます（map to guest / guest ok）。'; _sm_cleanup; return 1; fi
    _sm_cli "$o" //127.0.0.1/private "$SM_USER1%wrong-$rnd" 'ls' || true
    _sm_denied "$o" || { echo '誤ったパスワードで接続できてしまいます。'; _sm_cleanup; return 1; }
    _sm_cli "$o" //127.0.0.1/private "$pu2" "lcd $LAB_STATE; put probe.txt bob-$rnd.txt" || true
    if [[ -e $SM_DATA/private/bob-$rnd.txt ]] || ! _sm_denied "$o"; then echo "グループ外の $SM_USER2 がprivateに入れます（valid users）。"; _sm_cleanup; return 1; fi
    # member: write works and has the expected on-disk ownership
    _sm_cli "$o" //127.0.0.1/private "$pu1" "lcd $LAB_STATE; put probe.txt alice-$rnd.txt; ls" || true
    if [[ ! -f $SM_DATA/private/alice-$rnd.txt ]]; then echo "$SM_USER1 がprivateへ書けません。共有設定と実ディレクトリの権限を確認。"; _sm_cleanup; return 1; fi
    cmp -s "$LAB_STATE/probe.txt" "$SM_DATA/private/alice-$rnd.txt" || { echo '転送内容が一致しません。'; _sm_cleanup; return 1; }
    read -r owner group mode < <(stat -c '%U %G %a' "$SM_DATA/private/alice-$rnd.txt")
    if [[ $owner != "$SM_USER1" || $group != "$SM_GROUP" ]]; then echo "ファイルの所有者:グループが $owner:$group です（期待: $SM_USER1:$SM_GROUP）。"; _sm_cleanup; return 1; fi
    if (( (8#$mode & 8#007) != 0 || (8#$mode & 8#060) != 8#060 )); then echo "ファイルのモードが $mode です（グループは読み書き可、otherは不可）。create maskを確認。"; _sm_cleanup; return 1; fi
    _sm_cleanup
    echo 'OK: 匿名はpublicの読み取りのみ、privateは認証とグループ必須、作成ファイルは期待どおりの所有者・グループ・モードです。'
}

lab_reset() {
    _sm_paths || return 1
    [[ -f $LAB_STATE/owns-samba ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    systemctl disable --now dojo-smbd.service 2>/dev/null || true
    rm -f -- "$SM_UNIT"
    systemctl daemon-reload
    getent passwd "$SM_USER1" >/dev/null && userdel "$SM_USER1" 2>/dev/null
    getent passwd "$SM_USER2" >/dev/null && userdel "$SM_USER2" 2>/dev/null
    getent group "$SM_GROUP" >/dev/null && groupdel "$SM_GROUP" 2>/dev/null
    rm -rf -- "$SM_DIR" "$SM_VAR" "$SM_DATA"
    rm -f -- "$LAB_STATE/owns-samba" "$LAB_STATE/fault" "$LAB_STATE/unit.sha256" "$LAB_STATE/pass1" "$LAB_STATE/pass2" \
        "$LAB_STATE/client.conf" "$LAB_STATE/TASKS.txt" "$LAB_STATE/smb.conf.learner" "$LAB_STATE/testparm.err" \
        "$LAB_STATE/check.out" "$LAB_STATE/break-probe.log" "$LAB_STATE/probe.txt"
    echo '専用smbd構成を削除しました。OS標準のSamba設定(/etc/samba)は変更していません。'
}
