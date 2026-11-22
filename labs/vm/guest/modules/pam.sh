# title: PAMスタック設計: faillock・pwquality・access・listfile・制御フラグ(専用サービスdojo-lab)
# roles: app
# Only the lab-owned PAM service /etc/pam.d/dojo-lab and dedicated users are used; sshd/login/sudo stacks are never touched.
# pamtester is NOT part of the base image: setup refuses with an install instruction when missing.

_pam_paths() {
    [[ ${LAB_ID:-} == pam && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/pam ]] || { echo 'pam: unexpected lab context' >&2; return 1; }
    P_SVC=dojo-lab
    P_FILE=/etc/pam.d/dojo-lab
    P_DIR=/etc/dojo-pam-lab
    P_USERS='dojo-pam-ok dojo-pam-lock dojo-pam-bad dojo-pam-ban'
    [[ ! -L $P_FILE && ! -L $P_DIR ]] || return 1
}

_pam_tools() {
    local missing=()
    command -v pamtester >/dev/null || missing+=(pamtester)
    compgen -G '/usr/lib/*/security/pam_pwquality.so' >/dev/null || compgen -G '/lib/security/pam_pwquality.so' >/dev/null || missing+=(libpam-pwquality)
    command -v faillock >/dev/null || missing+=(libpam-modules-bin)
    command -v python3 >/dev/null || missing+=(python3)
    if ((${#missing[@]})); then
        echo "必要なものがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y pamtester libpam-pwquality libpam-modules-bin python3'
        return 1
    fi
}

_pam_pw() { awk -v u="$1" '$1 == u {print $2}' "$LAB_STATE/passwords.txt"; }

# $1=user $2=password $3=new password ("" if none), rest = pamtester operations. Runs pamtester on a pty. Exit status = pamtester's.
_pam_try() {
    local user=$1 pw=$2 newpw=$3; shift 3
    DOJO_PW=$pw DOJO_NEWPW=$newpw python3 - "$P_SVC" "$user" "$@" <<'PY'
import os, pty, select, subprocess, sys, time
svc, user, ops = sys.argv[1], sys.argv[2], sys.argv[3:]
pw, newpw = os.environ['DOJO_PW'], os.environ.get('DOJO_NEWPW', '')
args = ['pamtester']
try:
    helptxt = subprocess.run(['pamtester', '-h'], capture_output=True, text=True, timeout=5)
    if '-I' in helptxt.stdout + helptxt.stderr:
        args += ['-I', 'tty=dojo-tty', '-I', 'rhost=localhost']
except Exception:
    pass
args += [svc, user] + ops
pid, fd = pty.fork()
if pid == 0:
    os.execvp('pamtester', args)
out, done, deadline = b'', 0, time.time() + 20
while time.time() < deadline:
    r, _, _ = select.select([fd], [], [], 0.5)
    if not r:
        continue
    try:
        data = os.read(fd, 4096)
    except OSError:
        break
    if not data:
        break
    out += data
    tail = out[done:].lower().rstrip()
    if tail.endswith(b'password:'):
        text = tail
        if (b'new' in text or b'retype' in text) and newpw:
            os.write(fd, newpw.encode() + b'\n')
        else:
            os.write(fd, pw.encode() + b'\n')
        done = len(out)
else:
    os.kill(pid, 9)
_, status = os.waitpid(pid, 0)
sys.exit(os.waitstatus_to_exitcode(status))
PY
}

_pam_reset_locks() { local u; for u in $P_USERS; do faillock --user "$u" --reset >/dev/null 2>&1 || true; done; }

# Static rules that no sane stack may break, parsed from the real file.
_pam_static() {
    [[ -f $P_FILE && ! -L $P_FILE && $(stat -c %U "$P_FILE") == root ]] || { echo "$P_FILE がありません。"; return 1; }
    python3 - "$P_FILE" <<'PY'
import re, sys
lines, buf = [], ''
for raw in open(sys.argv[1]):
    raw = raw.rstrip('\n')
    if raw.endswith('\\'):
        buf += raw[:-1] + ' '; continue
    lines.append(buf + raw); buf = ''
rules = []
for l in lines:
    l = l.split('#', 1)[0].strip()
    if not l: continue
    m = re.match(r'^(-?)(auth|account|password|session)\s+(\[[^\]]*\]|\S+)\s+(\S+)\s*(.*)$', l)
    if m:
        rules.append((m.group(2), m.group(3), m.group(4), m.group(5)))
def mods(t): return [r for r in rules if r[0] == t]
def bad(msg): print(msg); sys.exit(1)
auth = mods('auth')
if not auth: bad('auth の行がありません。')
if any('pam_permit.so' in r[2] for r in auth): bad('auth に pam_permit.so は使えません(誰でも通ります)。認証は pam_unix.so で行います。')
if not any('pam_unix.so' in r[2] for r in auth): bad('auth に実際にパスワードを検証する pam_unix.so が必要です。')
if any('pam_rootok.so' in r[2] for r in auth): bad('auth に pam_rootok.so は使えません。')
if not any('pam_faillock.so' in r[2] for r in rules): bad('pam_faillock.so (deny=3, unlock_time) が必要です。')
if not any(re.search(r'unlock_time=\d+', r[3]) for r in rules if 'pam_faillock.so' in r[2]): bad('pam_faillock に unlock_time=秒 を指定します。')
if not any('pam_access.so' in r[2] for r in mods('account')): bad('account に pam_access.so が必要です(access.confで許可/拒否)。')
if not any('pam_listfile.so' in r[2] for r in auth): bad('auth に pam_listfile.so (禁止ユーザー一覧)が必要です。')
if not any('pam_pwquality.so' in r[2] for r in mods('password')): bad('password に pam_pwquality.so が必要です。')
PY
}

_pam_verify() {
    local ok_pw lock_pw bad_pw ban_pw strong i
    _pam_static || return 1
    ok_pw=$(_pam_pw dojo-pam-ok); lock_pw=$(_pam_pw dojo-pam-lock); bad_pw=$(_pam_pw dojo-pam-bad); ban_pw=$(_pam_pw dojo-pam-ban)
    _pam_reset_locks
    # 1. correct password accepted, wrong refused
    _pam_try dojo-pam-ok "$ok_pw" '' authenticate acct_mgmt || { echo 'dojo-pam-ok の正しいパスワードが拒否されました(pamtester dojo-lab dojo-pam-ok authenticate acct_mgmt)。'; _pam_reset_locks; return 1; }
    _pam_try dojo-pam-ok "wrong-$ok_pw" '' authenticate && { echo '誤ったパスワードが受理されています。'; _pam_reset_locks; return 1; }
    _pam_reset_locks
    # 2. faillock: two failures are fine, three lock even the correct password
    _pam_try dojo-pam-lock "x1$lock_pw" '' authenticate; _pam_try dojo-pam-lock "x2$lock_pw" '' authenticate
    _pam_try dojo-pam-lock "$lock_pw" '' authenticate acct_mgmt || { echo '2回失敗しただけで正しいパスワードが拒否されました。deny=3 を確認します。'; _pam_reset_locks; return 1; }
    for i in 1 2 3; do _pam_try dojo-pam-lock "bad$i$lock_pw" '' authenticate; done
    if _pam_try dojo-pam-lock "$lock_pw" '' authenticate; then echo '3回失敗した後も正しいパスワードが通ります。faillockの preauth / authfail / authsucc の並びとフラグを確認します。'; _pam_reset_locks; return 1; fi
    _pam_reset_locks
    # 3. pam_access: denied user refused even with the right password, listed user accepted (above)
    _pam_try dojo-pam-bad "$bad_pw" '' authenticate acct_mgmt && { echo 'access.confで拒否すべき dojo-pam-bad が通っています。'; _pam_reset_locks; return 1; }
    # 4. pam_listfile: banned user refused with the right password
    _pam_try dojo-pam-ban "$ban_pw" '' authenticate && { echo 'banned.txt の dojo-pam-ban が正しいパスワードで認証されています。'; _pam_reset_locks; return 1; }
    _pam_reset_locks
    # 5. pam_pwquality: weak new password rejected, strong accepted (password restored afterwards)
    if _pam_try dojo-pam-ok "$ok_pw" 'abc123' chauthtok; then echo '弱いパスワード(abc123)への変更が通りました。pam_pwquality の minlen と enforce_for_root(pamtesterはroot実行)を確認します。'; echo "dojo-pam-ok:$ok_pw" | chpasswd; _pam_reset_locks; return 1; fi
    strong="Zq$(openssl rand -hex 6)-Lm9!"
    if ! _pam_try dojo-pam-ok "$ok_pw" "$strong" chauthtok; then echo '十分に強い新パスワードの変更が拒否されました(password スタックの pam_unix に use_authtok が必要)。'; echo "dojo-pam-ok:$ok_pw" | chpasswd; _pam_reset_locks; return 1; fi
    echo "dojo-pam-ok:$ok_pw" | chpasswd
    _pam_reset_locks
    return 0
}

lab_setup() {
    _pam_paths || return 1
    _pam_tools || return 1
    local u pw
    [[ ! -e $P_FILE && ! -e $P_DIR ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    for u in $P_USERS; do getent passwd "$u" >/dev/null && { echo "専用アカウント名 $u が使用済みです。"; return 1; }; done
    install -d -m 0755 "$P_DIR"
    touch "$LAB_STATE/owns-files"
    : > "$LAB_STATE/passwords.txt"; chmod 0600 "$LAB_STATE/passwords.txt"
    for u in $P_USERS; do
        pw="Dj$(openssl rand -hex 6)-Qx7!"
        useradd --no-create-home --shell /usr/sbin/nologin --comment 'linuxdojo pam lab' "$u"
        echo "$u:$pw" | chpasswd
        echo "$u $pw" >> "$LAB_STATE/passwords.txt"
    done
    touch "$LAB_STATE/owns-accounts"
    printf '# one user name per line; users listed here must be refused by the dojo-lab stack\ndojo-pam-ban\n' > "$P_DIR/banned.txt"
    printf '# access.conf format: permission : users : origins   (see man access.conf)\n# TODO: allow dojo-pam-ok, dojo-pam-lock and dojo-pam-ban, refuse everyone else\n' > "$P_DIR/access.conf"
    chmod 0644 "$P_DIR/banned.txt" "$P_DIR/access.conf"
    printf '# dojo-lab PAM service. Build the stack here (man pam.conf, man pam_faillock, man pam_access, man pam_listfile, man pam_pwquality).\n' > "$P_FILE"
    chmod 0644 "$P_FILE"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用PAMサービス /etc/pam.d/dojo-lab だけを編集します(sshd/login/sudo は絶対に触らない)。
試験用ユーザー: dojo-pam-ok / dojo-pam-lock / dojo-pam-bad / dojo-pam-ban。パスワードは sudo cat $LAB_STATE/passwords.txt
試験コマンド例: sudo pamtester dojo-lab dojo-pam-ok authenticate acct_mgmt    (成功なら "successfully authenticated")
先に man pam.conf で type・control(required/requisite/sufficient/optional/[value=action])の意味と評価順を読む。
作るスタック:
 1. auth: pam_faillock(preauth) -> pam_unix -> pam_faillock(authfail)、成功時のリセット(authsucc)。deny=3 と unlock_time=秒。
    失敗3回の後は正しいパスワードでも拒否される。faillock --user <名前> で記録を見る/消す。
 2. auth: pam_listfile で $P_DIR/banned.txt のユーザーを拒否(item=user sense=deny onerr=succeed か fail か、意味を man で確認)。
 3. account: pam_access で $P_DIR/access.conf を使う(accessfile=)。access.conf を書き、
    dojo-pam-ok と dojo-pam-lock と dojo-pam-ban は許可、dojo-pam-bad はパスワードが正しくても拒否。
 4. password: pam_pwquality(minlen・retry・enforce_for_root)に pam_unix use_authtok。弱いパスワードは変更不可、強ければ変更可。
    pam_limits(session)も1行入れて意味を man limits.conf で確認(判定対象外)。
 5. pam_permit.so を auth の唯一の砦にしない。順序とフラグ(sufficient/requisite/[success=1 default=bad]等)が判定に直結する。
 6. sudo dojo-vm-lab pam break   (順序・フラグの誤りで全員が通る/全員が拒否される スタックに差し替えます。全項目が通る時だけ)
    pamtester で症状を再現し、man pam.conf を読みながら直す。
 7. sudo dojo-vm-lab pam check
 8. 終了後 sudo dojo-vm-lab pam reset
注意: dojo-lab を壊しても他のサービスには影響しません。別のコンソールを開いたまま作業するのが実務の習慣です。
TASK
    echo "手順: $LAB_STATE/TASKS.txt"; cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _pam_paths || return 1
    [[ -f $LAB_STATE/owns-files && -f $LAB_STATE/owns-accounts && ! -f $LAB_STATE/fault ]] || { echo '初期化済みで未breakの状態で実行します。'; return 1; }
    _pam_verify || { echo 'まず手順1-4を完了し、全項目が通る状態にします。'; return 1; }
    cp -p -- "$P_FILE" "$LAB_STATE/dojo-lab.pre-break"
    cat > "$P_FILE" <<CONF
# dojo-lab (BROKEN): fix the order and the control flags
auth     sufficient    pam_unix.so
auth     requisite     pam_faillock.so preauth deny=3 unlock_time=300
auth     [default=die] pam_faillock.so authfail deny=3 unlock_time=300
auth     requisite     pam_listfile.so item=user sense=deny file=$P_DIR/banned.txt onerr=succeed
auth     required      pam_deny.so
account  sufficient    pam_access.so accessfile=$P_DIR/access.conf
account  required      pam_permit.so
password requisite     pam_pwquality.so retry=3 minlen=12 enforce_for_root
password required      pam_unix.so use_authtok
CONF
    _pam_reset_locks
    if _pam_try dojo-pam-ban "$(_pam_pw dojo-pam-ban)" '' authenticate && _pam_try dojo-pam-bad "$(_pam_pw dojo-pam-bad)" '' authenticate acct_mgmt; then
        touch "$LAB_STATE/fault"
        echo '障害を仕込みました。禁止ユーザーとaccess拒否ユーザーが通ってしまいます。pamtesterで再現し、順序とフラグを直します。'
    else
        cp -p -- "$LAB_STATE/dojo-lab.pre-break" "$P_FILE"; rm -f -- "$LAB_STATE/dojo-lab.pre-break"
        echo '障害を再現できませんでした。元に戻しました。'; return 1
    fi
}

lab_check() {
    _pam_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずスタックを作り、breakで障害を作ります。'; return 1; }
    _pam_verify || return 1
    echo 'PASS: 正しいパスワード受理・誤り拒否・faillock(3回で正しくても拒否)・access.conf・listfile・pwqualityをpamtesterの実結果で確認しました。'
}

lab_reset() {
    _pam_paths || return 1
    [[ -f $LAB_STATE/owns-files ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    local u
    if [[ -f $LAB_STATE/owns-accounts ]]; then
        for u in $P_USERS; do
            if getent passwd "$u" | grep -q ':linuxdojo pam lab:'; then
                command -v faillock >/dev/null && faillock --user "$u" --reset >/dev/null 2>&1 || true
                userdel "$u" || return 1
            fi
        done
    fi
    rm -f -- "$P_FILE"
    rm -rf -- "${P_DIR:?}"
    rm -f -- "${LAB_STATE:?}/owns-files" "${LAB_STATE:?}/owns-accounts" "${LAB_STATE:?}/fault" "${LAB_STATE:?}/passwords.txt" "${LAB_STATE:?}/dojo-lab.pre-break" "${LAB_STATE:?}/TASKS.txt"
    echo '専用PAMサービス・設定ファイル・試験ユーザーを削除しました。OS標準のPAM設定は変更していません。'
}
