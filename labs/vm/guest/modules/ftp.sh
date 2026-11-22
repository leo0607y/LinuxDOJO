# title: FTPサーバ(vsftpd専用インスタンス): chroot・匿名拒否・userlist・passive転送
# roles: app
# Dedicated vsftpd on 127.0.0.1:2121 with its own config (/etc/dojo-ftp). The OS vsftpd.service is never touched.
# vsftpd is NOT part of the base image: setup prints the apt line and exits without writing when missing.

_ftp_paths() {
    [[ ${LAB_ID:-} == ftp && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/ftp ]] || { echo 'ftp: unexpected lab context' >&2; return 1; }
    F_ETC=/etc/dojo-ftp
    F_CONF=$F_ETC/vsftpd.conf
    F_LIST=$F_ETC/user_list
    F_ROOT=/srv/dojo-ftp
    F_UNIT=/etc/systemd/system/dojo-ftp.service
    F_OTHERHOME=/srv/dojo-ftp2
    F_USER=dojo-ftp
    F_OTHER=dojo-ftp2
    [[ ! -L $F_ETC && ! -L $F_ROOT && ! -L $F_OTHERHOME && ! -L $F_UNIT ]] || return 1
}

_ftp_tools() {
    command -v vsftpd >/dev/null && command -v python3 >/dev/null || {
        echo 'vsftpd がありません。次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y vsftpd'
        return 1
    }
}

_ftp_write_conf() { # $1 = good|broken
    {
        cat <<CONF
# LinuxDOJO dedicated vsftpd (127.0.0.1:2121). OS vsftpd.service is separate.
listen=YES
listen_ipv6=NO
listen_address=127.0.0.1
listen_port=2121
background=NO
secure_chroot_dir=$F_ETC/empty
pam_service_name=vsftpd
local_enable=YES
write_enable=YES
local_umask=022
userlist_enable=YES
userlist_file=$F_LIST
xferlog_enable=YES
vsftpd_log_file=$LAB_STATE/vsftpd.log
CONF
        if [[ $1 == good ]]; then
            cat <<CONF
anonymous_enable=NO
userlist_deny=NO
chroot_local_user=YES
pasv_enable=YES
pasv_min_port=30000
pasv_max_port=30010
pasv_address=127.0.0.1
CONF
        else
            cat <<CONF
anonymous_enable=YES
userlist_deny=YES
chroot_local_user=YES
pasv_enable=YES
CONF
        fi
    } > "$F_CONF"
}

_ftp_restart() { systemctl restart dojo-ftp.service; sleep 1; systemctl is-active --quiet dojo-ftp.service; }

# Probe the real server with ftplib. $1 = login | full. Exit 0 only when everything holds.
_ftp_probe() {
    FTP_MODE=$1 FTP_USER=$F_USER FTP_OTHER=$F_OTHER FTP_PW=$(cat "$LAB_STATE/user.pw") FTP_PW2=$(cat "$LAB_STATE/other.pw") \
    python3 - <<'PY'
import ftplib, hashlib, io, os, sys
H, P = '127.0.0.1', 2121
def fail(msg):
    print(msg); sys.exit(1)
def conn():
    f = ftplib.FTP(); f.connect(H, P, timeout=5); return f
def refused(user, pw):
    f = conn()
    try:
        f.login(user, pw)
    except ftplib.error_perm:
        return True
    except (ftplib.all_errors, OSError):
        return True
    finally:
        try: f.close()
        except Exception: pass
    return False
mode = os.environ['FTP_MODE']
try:
    f = conn()
    f.login(os.environ['FTP_USER'], os.environ['FTP_PW'])
except (ftplib.all_errors, OSError) as e:
    fail('dojo-ftp でログインできません: %s' % e)
if mode == 'login':
    sys.exit(0)
try:
    if f.pwd() != '/':
        fail('chroot されていません(ログイン直後のPWDが / ではない)。')
    f.set_pasv(True)
    host, port = f.makepasv()
    if not 30000 <= port <= 30010:
        fail('PASVポートが 30000-30010 の範囲外です: %d' % port)
    if host != '127.0.0.1':
        fail('PASVの応答アドレスが 127.0.0.1 ではありません: %s' % host)
    data = os.urandom(65536 * 3)
    f.cwd('/upload')
    f.storbinary('STOR roundtrip.bin', io.BytesIO(data))
    buf = io.BytesIO(); f.retrbinary('RETR roundtrip.bin', buf.write)
    if hashlib.sha256(buf.getvalue()).digest() != hashlib.sha256(data).digest():
        fail('アップロード/ダウンロードのチェックサムが一致しません。')
    f.delete('roundtrip.bin')
    f.cwd('/')
    for target in ('..', '../..', '../../..'):
        try: f.cwd(target)
        except ftplib.error_perm: pass
    if f.pwd() != '/' or 'upload' not in f.nlst() or 'etc' in f.nlst():
        fail('CWD .. でchrootの外に出られます。')
    try:
        f.cwd('/etc'); fail('/etc に移動できました(chroot外)。')
    except ftplib.error_perm:
        pass
finally:
    try: f.close()
    except Exception: pass
if not refused('anonymous', 'a@example.com') or not refused('ftp', ''):
    fail('匿名ログインが拒否されていません。')
if not refused(os.environ['FTP_OTHER'], os.environ['FTP_PW2']):
    fail('userlistに無いユーザー dojo-ftp2 が(正しいパスワードで)ログインできてしまいます。')
PY
}

# Static policy checks on the effective config; the safe fix is proper directory structure, not allow_writeable_chroot.
_ftp_policy() {
    python3 - "$F_CONF" <<'PY'
import sys
v = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, _, x = line.partition('='); v[k.strip()] = x.strip().upper() if x.strip().upper() in ('YES', 'NO') else x.strip()
bad = []
if v.get('allow_writeable_chroot') == 'YES': bad.append('allow_writeable_chroot=YES は使わず、chrootルートを root:root 755 にして書込み用サブディレクトリを分けます')
if v.get('anonymous_enable') != 'NO': bad.append('anonymous_enable=NO')
if v.get('chroot_local_user') != 'YES': bad.append('chroot_local_user=YES')
if v.get('pasv_address') != '127.0.0.1': bad.append('pasv_address=127.0.0.1')
if v.get('listen_address') != '127.0.0.1' or v.get('listen_port') != '2121': bad.append('listen_address=127.0.0.1 / listen_port=2121')
if v.get('userlist_enable') != 'YES' or v.get('userlist_deny') != 'NO': bad.append('userlist_enable=YES と userlist_deny=NO(許可リスト方式)')
if v.get('pasv_min_port') != '30000' or v.get('pasv_max_port') != '30010': bad.append('pasv_min_port=30000 / pasv_max_port=30010')
if v.get('ssl_enable') == 'YES' and not v.get('rsa_cert_file'): bad.append('ssl_enable=YES には rsa_cert_file が必要')
for b in bad: print('設定の確認: ' + b)
sys.exit(1 if bad else 0)
PY
}

lab_setup() {
    _ftp_paths || return 1
    _ftp_tools || return 1
    [[ ! -e $F_ETC && ! -e $F_ROOT && ! -e $F_OTHERHOME && ! -e $F_UNIT ]] || { echo '専用構成が既にあります。既存データを上書きしません。'; return 1; }
    if getent passwd "$F_USER" >/dev/null || getent passwd "$F_OTHER" >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    ss -ltn 2>/dev/null | grep -qE '127\.0\.0\.1:2121\b' && { echo '2121番が使用中です。'; return 1; }
    install -d -m 0755 "$F_ETC" "$F_ETC/empty"
    local pw pw2
    pw=$(cat /proc/sys/kernel/random/uuid); pw2=$(cat /proc/sys/kernel/random/uuid)
    install -d -m 0755 "$F_ROOT"
    useradd --home-dir "$F_ROOT" --no-create-home --shell /bin/bash "$F_USER" || return 1
    install -d -o root -g root -m 0755 "$F_OTHERHOME" "$F_OTHERHOME/upload"   # valid chroot, so only the userlist can refuse this account
    useradd --home-dir "$F_OTHERHOME" --no-create-home --shell /bin/bash "$F_OTHER" || return 1
    printf '%s:%s\n%s:%s\n' "$F_USER" "$pw" "$F_OTHER" "$pw2" | chpasswd || return 1
    ( umask 077; printf '%s\n' "$pw" > "$LAB_STATE/user.pw"; printf '%s\n' "$pw2" > "$LAB_STATE/other.pw" )
    touch "$LAB_STATE/owns-account"
    # Proper structure: root-owned non-writable chroot root, writable subdirectory.
    chown root:root "$F_ROOT"; chmod 0755 "$F_ROOT"
    install -d -o "$F_USER" -g "$F_USER" -m 0755 "$F_ROOT/upload"
    printf '%s\n' "$F_USER" > "$F_LIST"
    _ftp_write_conf good
    cat > "$F_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated loopback vsftpd exercise
After=network.target
[Service]
ExecStart=$(command -v vsftpd) $F_CONF
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$F_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-ftp.service
    sleep 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用vsftpd(127.0.0.1:2121)。設定: $F_CONF  許可リスト: $F_LIST  ルート: $F_ROOT  パスワード: sudo cat $LAB_STATE/user.pw
1. 動作確認: python3 -c "import ftplib;f=ftplib.FTP();f.connect('127.0.0.1',2121);print(f.login('$F_USER',open('$LAB_STATE/user.pw').read().strip()));print(f.pwd(),f.nlst())"
   (標準のftpクライアントが無くてもPythonのftplibで確認できる)
2. sudo dojo-vm-lab ftp break  で設定が壊れる。症状を確認する:
   sudo journalctl -u dojo-ftp.service / $LAB_STATE/vsftpd.log / ftplibでログイン
3. 修正する点(ヒント):
   - 匿名ログインは許可してよいか。
   - userlist は「許可リスト」か「拒否リスト」か(userlist_deny の意味)。dojo-ftp2 はリスト外。
   - chroot_local_user=YES では chrootルートが書込み可だと vsftpd が 500 OOPS で拒否する。
     allow_writeable_chroot=YES で回避するのは近道であり不正解。ディレクトリ構造で解決する(書込み先は専用サブディレクトリ)。
   - PASVデータ接続のポート範囲を 30000-30010 に固定し、アドレスは 127.0.0.1。
   設定変更後は sudo systemctl restart dojo-ftp.service
4. 判定: sudo dojo-vm-lab ftp check
   (ログイン・匿名拒否・up/downロードのチェックサム・CWD ..の遮断・PASVポート・リスト外ユーザー拒否を実接続で確認)
5. 発展(判定外): openssl req -x509 で自己署名証明書を作り ssl_enable=YES, rsa_cert_file, force_local_logins_ssl を試す(FTPS)。
6. 終了後 sudo dojo-vm-lab ftp reset
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudoで読む)。次に sudo dojo-vm-lab ftp break"
}

lab_break() {
    _ftp_paths || return 1
    [[ -f $LAB_STATE/owns-account && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで、未breakの状態で実行します。'; return 1; }
    _ftp_probe full || { echo '正常状態の確認に失敗しました。setupをやり直してください。'; return 1; }
    _ftp_write_conf broken
    chown "$F_USER:$F_USER" "$F_ROOT"; chmod 0775 "$F_ROOT"   # writable chroot root pitfall
    _ftp_restart || { echo 'dojo-ftp.serviceが起動しません。'; }
    if _ftp_probe login >/dev/null 2>&1; then echo '障害を再現できませんでした。'; return 1; fi
    touch "$LAB_STATE/fault"
    echo 'FTPが壊れた状態です。ログを調べ、設定とディレクトリ構造を直してください。'
}

lab_check() {
    _ftp_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/owns-account ]] || { echo 'まず break で障害を作ります。'; return 1; }
    [[ $(sha256sum "$F_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || { echo 'unitは変更せず、設定ファイルを直します。'; return 1; }
    _ftp_policy || return 1
    [[ $(stat -c %U "$F_ROOT") == root && ( $(stat -c %a "$F_ROOT") =~ ^[0-7][0-5][0-5]$ ) ]] || { echo "chrootルート $F_ROOT は root 所有で書込み不可にします。"; return 1; }
    [[ $(stat -c %U "$F_ROOT/upload") == "$F_USER" ]] || { echo '書込み先 upload は dojo-ftp 所有にします。'; return 1; }
    systemctl is-active --quiet dojo-ftp.service || { echo 'dojo-ftp.serviceが動いていません。'; return 1; }
    _ftp_probe full || return 1
    echo 'PASS: ログイン・匿名拒否・チェックサム付き往復転送・chroot脱出遮断・PASV範囲・リスト外ユーザー拒否を実接続で確認しました。'
}

lab_reset() {
    _ftp_paths || return 1
    [[ -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    systemctl disable --now dojo-ftp.service 2>/dev/null || true
    rm -f -- "$F_UNIT"
    systemctl daemon-reload
    userdel "$F_USER" 2>/dev/null || true
    userdel "$F_OTHER" 2>/dev/null || true
    rm -rf -- "$F_ROOT" "$F_OTHERHOME" "$F_ETC"
    rm -f -- "$LAB_STATE/owns-account" "$LAB_STATE/fault" "$LAB_STATE/unit.sha256" "$LAB_STATE/user.pw" "$LAB_STATE/other.pw" "$LAB_STATE/TASKS.txt" "$LAB_STATE/vsftpd.log"
    echo '専用vsftpd構成を削除しました。OS標準のvsftpd設定は変更していません。'
}
