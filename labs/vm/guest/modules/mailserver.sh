# title: Postfix専用インスタンスでローカル配送・エイリアス・キュー・リレー拒否
# roles: app
# Dedicated Postfix instance (config_directory=/etc/postfix-dojo) on 127.0.0.1:2526 only.
# The system postfix (main.cf, port 25) is never touched; outbound mail is blocked by default_transport=error.

_ms_paths() {
    [[ ${LAB_ID:-} == mailserver && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/mailserver ]] || { echo 'mailserver: unexpected lab context' >&2; return 1; }
    MS_CONF=/etc/postfix-dojo
    MS_QUEUE=/var/spool/postfix-dojo
    MS_DATA=/var/lib/postfix-dojo
    MS_USER=dojomail
    MS_HOME=/srv/dojo-mail
    MS_MAILDIR=$MS_HOME/Maildir
    MS_DOMAIN=mail.dojo.test
    [[ ! -L $MS_CONF && ! -L $MS_QUEUE && ! -L $MS_DATA && ! -L $MS_HOME ]] || return 1
}

_ms_postconf() { postconf -c "$MS_CONF" -h "$@"; }

# SMTP client dialogue against the instance. mode: probe | send ADDR TOKEN | relay
_ms_smtp() {
    python3 - "$@" <<'PY'
import smtplib, sys
mode = sys.argv[1]
s = smtplib.SMTP('127.0.0.1', 2526, timeout=8, local_hostname='client.dojo.test')
try:
    s.ehlo()
    if mode == 'relay':
        s.mail('probe@mail.dojo.test')
        code, msg = s.rcpt('victim@external.example')
        # never send DATA to an external recipient
        sys.exit(0 if code in (550, 554) and b'relay' in msg.lower() else 1)
    addr, token = sys.argv[2], sys.argv[3]
    s.sendmail('probe@mail.dojo.test', [addr],
               'From: probe@mail.dojo.test\r\nTo: %s\r\nSubject: dojo %s\r\n\r\nbody %s\r\n' % (addr, token, token))
finally:
    try: s.quit()
    except Exception: pass
PY
}

_ms_wait_file() { # token dir seconds
    local i
    for ((i = 0; i < $3; i++)); do
        grep -rlF -- "$1" "$2" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

_ms_queue_empty() {
    postqueue -c "$MS_CONF" -p 2>/dev/null | grep -q '^Mail queue is empty'
}

lab_setup() {
    _ms_paths || return 1
    if ! command -v postfix >/dev/null || ! command -v postconf >/dev/null; then
        printf '%s\n' \
            'postfix が未導入です。実習用に先にインストールしてください（システム側postfixは Local only で最小構成）:' \
            '  sudo DEBIAN_FRONTEND=noninteractive debconf-set-selections <<< '\''postfix postfix/main_mailer_type select Local only'\''' \
            '  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y postfix' \
            'その後 sudo dojo-vm-lab mailserver setup を再実行します。（何も変更していません）'
        return 1
    fi
    [[ ! -e $MS_CONF && ! -e $MS_QUEUE && ! -e $MS_DATA && ! -e $MS_HOME ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if getent passwd "$MS_USER" >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    [[ -f /etc/postfix/postfix-files ]] || { echo '/etc/postfix/postfix-files が見つかりません。'; return 1; }
    ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE '[:.]2526$' && { echo 'ポート2526は使用中です。'; return 1; }
    useradd --create-home --home-dir "$MS_HOME" --shell /usr/sbin/nologin --password '!' "$MS_USER" || return 1
    touch "$LAB_STATE/owns-account"
    install -d -o "$MS_USER" -g "$MS_USER" -m 0700 "$MS_MAILDIR" "$MS_MAILDIR/cur" "$MS_MAILDIR/new" "$MS_MAILDIR/tmp"
    install -d -m 0755 "$MS_CONF" "$MS_DATA"
    touch "$LAB_STATE/owns-instance"
    cp /etc/postfix/postfix-files "$MS_CONF/postfix-files"
    [[ -f /etc/postfix/dynamicmaps.cf ]] && cp /etc/postfix/dynamicmaps.cf "$MS_CONF/dynamicmaps.cf"
    [[ -d /etc/postfix/dynamicmaps.cf.d ]] && cp -r /etc/postfix/dynamicmaps.cf.d "$MS_CONF/dynamicmaps.cf.d"
    cat > "$MS_CONF/master.cf" <<'MASTER'
# service type private unpriv chroot wakeup maxproc command
127.0.0.1:2526 inet n - n - - smtpd
pickup    unix  n - n 60 1 pickup
cleanup   unix  n - n -  0 cleanup
qmgr      unix  n - n 300 1 qmgr
rewrite   unix  - - n -  - trivial-rewrite
bounce    unix  - - n -  0 bounce
defer     unix  - - n -  0 bounce
trace     unix  - - n -  0 bounce
verify    unix  - - n -  1 verify
flush     unix  n - n 1000? 0 flush
proxymap  unix  - - n -  - proxymap
proxywrite unix - - n -  1 proxymap
smtp      unix  - - n -  - smtp
relay     unix  - - n -  - smtp
showq     unix  n - n -  - showq
error     unix  - - n -  - error
retry     unix  - - n -  - error
discard   unix  - - n -  - discard
local     unix  - n n -  - local
virtual   unix  - n n -  - virtual
anvil     unix  - - n -  1 anvil
scache    unix  - - n -  1 scache
MASTER
    cat > "$MS_CONF/main.cf" <<CONF
compatibility_level = 3.6
config_directory = $MS_CONF
queue_directory = $MS_QUEUE
data_directory = $MS_DATA
syslog_name = postfix-dojo
inet_interfaces = loopback-only
inet_protocols = ipv4
mynetworks = 127.0.0.1/32
smtpd_relay_restrictions = reject_unauth_destination
smtpd_tls_security_level = none
smtp_tls_security_level = none
disable_vrfy_command = yes
biff = no
default_transport = error:dojo lab never sends outbound mail
alias_maps = hash:$MS_CONF/aliases
alias_database = hash:$MS_CONF/aliases
CONF
    printf 'postmaster: %s\n' "$MS_USER" > "$MS_CONF/aliases"
    postalias -c "$MS_CONF" "hash:$MS_CONF/aliases" || return 1
    cp "$MS_CONF/main.cf" "$LAB_STATE/main.cf.initial"
    postfix -c "$MS_CONF" check || { echo 'postfix check に失敗しました。reset後に原因を確認してください。'; return 1; }
    postfix -c "$MS_CONF" start || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用Postfix: 設定 $MS_CONF / 受付 127.0.0.1:2526 のみ / 配送先ユーザー $MS_USER (Maildir=$MS_MAILDIR)
システムのpostfix(/etc/postfix, port 25)は触らない。外部送信はできない設計(default_transport=error)。
以降 DIR=$MS_CONF として、sudo で操作する。
1. 現状を見る: postconf -c DIR -n / sudo postfix -c DIR check / ss -ltn
2. postconf -c DIR -e で設定: myhostname=$MS_DOMAIN, mydestination に $MS_DOMAIN を含める(localhost も),
   inet_interfaces=127.0.0.1, home_mailbox=Maildir/ 。変更後 postfix -c DIR reload。
3. エイリアス: DIR/aliases に「dojo-ops: $MS_USER」を追加し、postalias か
   MAIL_CONFIG=DIR newaliases で反映(alias_mapsの場所を postconf で確認)。
4. 127.0.0.1:2526 へ SMTP 対話(nc か python3 smtplib)で
   dojo-ops@$MS_DOMAIN 宛に1通送る。$MS_MAILDIR/new に届くことを確認。
5. 外部宛(例 victim@external.example)の RCPT が 550/554 relay access denied で拒否されることを確認(DATAまで進めない)。
6. キューとログ: postqueue -c DIR -p / mailq(MAIL_CONFIG) / journalctl -b | grep postfix-dojo
7. sudo dojo-vm-lab mailserver break  -> 受信が滞り、リレー設定も壊れる。
   キューの理由(mailq・ログ)から原因を見つけて修正する。ローカルホストからでも外部宛は拒否が正解。
   元の設定値は $LAB_STATE/main.cf.initial 参照可。直したら postfix reload と postqueue -c DIR -f でキューを流す。
8. sudo dojo-vm-lab mailserver check
9. 終了後 sudo dojo-vm-lab mailserver reset (専用インスタンス・ユーザー・Maildirのみ削除)
TASK
    echo "手順: $LAB_STATE/TASKS.txt。専用Postfixは 127.0.0.1:2526 で待受中（設定は意図的に未完成）。"
}

lab_break() {
    _ms_paths || return 1
    [[ -f $LAB_STATE/owns-account && -f $LAB_STATE/owns-instance ]] || return 1
    [[ ! -f $LAB_STATE/fault ]] || { echo '既に故障状態です。'; return 1; }
    [[ $(_ms_postconf myhostname) == "$MS_DOMAIN" && $(_ms_postconf home_mailbox) == Maildir/ ]] || { echo 'まず設定(手順2)を行います。'; return 1; }
    grep -qE '^dojo-ops:' "$MS_CONF/aliases" || { echo 'まずエイリアス(手順3)を作成します。'; return 1; }
    [[ -n $(find "$MS_MAILDIR/new" -type f 2>/dev/null | head -n 1) ]] || { echo 'まず1通配送に成功させます(手順4)。'; return 1; }
    touch "$LAB_STATE/fault"
    postconf -c "$MS_CONF" -e 'mynetworks = 0.0.0.0/0' 'smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination'
    sed -i '/^dojo-ops/d' "$MS_CONF/aliases"
    printf 'dojo-ops: dojo-ops-b\ndojo-ops-b: dojo-ops\n' >> "$MS_CONF/aliases"
    postalias -c "$MS_CONF" "hash:$MS_CONF/aliases"
    chown root:root "$MS_MAILDIR/new"
    chmod 0755 "$MS_MAILDIR/new"
    postfix -c "$MS_CONF" reload >/dev/null
    local token
    token=held-$(cat /proc/sys/kernel/random/uuid)
    printf '%s\n' "$token" > "$LAB_STATE/deferred.token"
    _ms_smtp send "$MS_USER@$MS_DOMAIN" "$token" || { echo '故障メールの投入に失敗しました。resetして再開してください。'; return 1; }
    _ms_smtp send "dojo-ops@$MS_DOMAIN" "loop-$token" || true
    sleep 5
    _ms_queue_empty && { echo 'キューに滞留が確認できません。resetして再開してください。'; return 1; }
    echo '故障状態です。mailqとログで滞留理由を調べ、リレー設定とエイリアスも点検して修正してください。'
}

lab_check() {
    _ms_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/deferred.token ]] || { echo 'まずbreakで故障を作ります。'; return 1; }
    postfix -c "$MS_CONF" check || { echo 'postfix check が失敗します。'; return 1; }
    postfix -c "$MS_CONF" status >/dev/null 2>&1 || { echo '専用インスタンスが動いていません。'; return 1; }
    local listeners
    listeners=$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E '[:.]2526$')
    [[ $listeners == 127.0.0.1:2526 ]] || { echo '2526は127.0.0.1のみで待受する必要があります。'; return 1; }
    [[ $(_ms_postconf myhostname) == "$MS_DOMAIN" ]] || { echo 'myhostnameを確認します。'; return 1; }
    _ms_postconf mydestination | tr ',' ' ' | tr -s ' ' '\n' | grep -qxF "$MS_DOMAIN" || { echo "mydestinationに $MS_DOMAIN が必要です。"; return 1; }
    [[ $(_ms_postconf home_mailbox) == Maildir/ ]] || { echo 'home_mailboxを確認します。'; return 1; }
    case $(_ms_postconf inet_interfaces) in 127.0.0.1|loopback-only) ;; *) echo 'inet_interfacesはループバックのみにします。'; return 1 ;; esac
    [[ $(_ms_postconf default_transport) == error:* ]] || { echo '外部送信を許す変更は不正解です(default_transport)。'; return 1; }
    ! _ms_postconf mynetworks | tr ',' ' ' | tr ' ' '\n' | grep -qE '/[0-9]$|/1[0-9]$|/2[0-3]$|^0\.0\.0\.0|/0$' || { echo 'mynetworksが広すぎます。'; return 1; }
    _ms_smtp relay || { echo '実際のSMTPで外部宛RCPTが550/554 relay access deniedになりません(リロード済みか、permit_mynetworksも確認)。'; return 1; }
    local token
    token=chk-$(cat /proc/sys/kernel/random/uuid)
    _ms_smtp send "$MS_USER@$MS_DOMAIN" "$token" || { echo '直接宛先への配送(SMTP)が受理されません。'; return 1; }
    _ms_wait_file "$token" "$MS_MAILDIR/new" 15 || { echo 'Maildirに届きません。'; return 1; }
    token=alias-$(cat /proc/sys/kernel/random/uuid)
    _ms_smtp send "dojo-ops@$MS_DOMAIN" "$token" || { echo 'dojo-ops宛が受理されません。'; return 1; }
    _ms_wait_file "$token" "$MS_MAILDIR/new" 15 || { echo 'エイリアス経由で届きません(ループを確認)。'; return 1; }
    _ms_wait_file "$(cat "$LAB_STATE/deferred.token")" "$MS_MAILDIR/new" 5 || { echo '滞留していたメールが未配送です(原因修正後にpostqueue -f)。'; return 1; }
    local i
    for ((i = 0; i < 20; i++)); do _ms_queue_empty && break; sleep 1; done
    _ms_queue_empty || { echo 'キューが空ではありません。'; return 1; }
    echo 'PASS: 専用インスタンスの実SMTPで、Maildir配送・エイリアス・リレー拒否・滞留メール解消・キュー空を確認しました。'
}

lab_reset() {
    _ms_paths || return 1
    [[ -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成したアカウントではありません。'; return 1; }
    if [[ -f $LAB_STATE/owns-instance && -d $MS_CONF ]]; then
        postfix -c "$MS_CONF" stop >/dev/null 2>&1 || true
        sleep 1
        rm -rf -- "$MS_CONF" "$MS_QUEUE" "$MS_DATA"
    fi
    userdel --remove "$MS_USER" || return 1
    rm -f -- "$LAB_STATE/owns-account" "$LAB_STATE/owns-instance" "$LAB_STATE/fault" "$LAB_STATE/deferred.token" "$LAB_STATE/main.cf.initial" "$LAB_STATE/TASKS.txt"
    echo '専用Postfixインスタンスとdojomailを削除しました。システムのpostfixは変更していません。'
}
