#!/bin/bash
# title: 専用sshdを鍵認証のみに堅牢化し、拒否を実接続で確認してProxyJumpで中継する
# roles: app
# Guest-only. Dedicated sshd on 127.0.0.1:22223 with its own config dir and host key.
# The system sshd and /root/.ssh are never touched.

_sshd_paths() {
    [[ ${LAB_ID:-} == sshd && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/sshd ]] || { echo 'sshd: unexpected lab context' >&2; return 1; }
    SD_UNIT=/etc/systemd/system/dojo-sshd.service
    SD_DIR=/etc/dojo-sshd
    SD_CONF=$SD_DIR/sshd_config
    SD_CLIENT=/home/ubuntu/dojo-sshd-client
    SD_PORT=22223
    [[ ! -L $SD_UNIT && ! -L $SD_DIR && ! -L $SD_CLIENT && ! -L $SD_CONF ]] || return 1
}

_sshd_loose_config() {
    cat <<CONF
# LinuxDOJO dedicated sshd (port $SD_PORT only). Not the system sshd.
ListenAddress 127.0.0.1
Port $SD_PORT
HostKey $SD_DIR/hostkey
PidFile /run/dojo-sshd.pid
AuthorizedKeysFile $SD_DIR/keys/%u
StrictModes yes
UsePAM no
PubkeyAuthentication yes
PasswordAuthentication yes
KbdInteractiveAuthentication yes
PermitRootLogin yes
MaxAuthTries 6
Subsystem sftp internal-sftp
LogLevel VERBOSE
CONF
}

# Real client attempts, run as root with the lab client key.
_sshd_key_ssh() { # user cmd...
    local user=$1; shift
    ssh -n -F /dev/null -i "$SD_CLIENT/id_ed25519" -o BatchMode=yes -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$SD_CLIENT/known_hosts" \
        -o ConnectTimeout=3 -p "$SD_PORT" "$user@127.0.0.1" "$@"
}

_sshd_key_ssh_retry() { # reload leaves a short gap
    local i
    for i in 1 2 3 4 5 6; do
        _sshd_key_ssh "$@" && return 0
        sleep 1
    done
    return 1
}

# Password-only attempt using the real password via SSH_ASKPASS (no sshpass needed).
_sshd_password_ssh() { # user
    SSH_ASKPASS="$LAB_STATE/askpass.sh" SSH_ASKPASS_REQUIRE=force DISPLAY=none:0 \
    ssh -n -F /dev/null -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive \
        -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$SD_CLIENT/known_hosts" \
        -o ConnectTimeout=3 -p "$SD_PORT" "$1@127.0.0.1" true
}

_sshd_effective() { # user outfile
    sshd -T -f "$SD_CONF" -C "user=$1,host=localhost,addr=127.0.0.1" > "$2"
}

# Echo "ok" only when effective values for a user satisfy the hardening policy.
_sshd_policy() { # effective-file user  (prints problems to stdout, returns 1 on problem)
    python3 - "$1" "$2" "$SD_DIR" "$SD_PORT" <<'PY'
from pathlib import Path
import sys
path, user, sd, port = sys.argv[1:5]
v = {}
for line in Path(path).read_text().splitlines():
    k, _, val = line.partition(' ')
    v.setdefault(k, []).append(val)
bad = []
def one(k): return v.get(k, [None])[0]
if one('passwordauthentication') != 'no': bad.append('PasswordAuthentication no が必要です')
if one('kbdinteractiveauthentication') != 'no': bad.append('KbdInteractiveAuthentication no が必要です')
if one('permitrootlogin') != 'no': bad.append('PermitRootLogin no が必要です')
if one('permitemptypasswords') != 'no': bad.append('空パスワードは許可できません')
if one('pubkeyauthentication') != 'yes': bad.append('鍵認証が無効だと締め出されます')
try:
    if not 1 <= int(one('maxauthtries')) <= 3: bad.append('MaxAuthTries は1から3にします')
except (TypeError, ValueError): bad.append('MaxAuthTries が読めません')
if sorted(v.get('allowusers', [])) != ['dojo-hard', 'dojo-hop']: bad.append('AllowUsers は専用の2アカウントだけにします')
if v.get('port') != [port]: bad.append('Port は固定です')
if v.get('listenaddress') != ['127.0.0.1:' + port]: bad.append('ListenAddress は固定です')
if v.get('hostkey') != [sd + '/hostkey']: bad.append('HostKey は固定です')
if v.get('authorizedkeysfile') != [sd + '/keys/%u']: bad.append('AuthorizedKeysFile は固定です')
if one('strictmodes') != 'yes': bad.append('StrictModes は有効のままにします')
print('\n'.join(bad))
sys.exit(1 if bad else 0)
PY
}

_sshd_client_config() {
    [[ -f $SD_CLIENT/ssh_config && ! -L $SD_CLIENT/ssh_config ]] || { echo 'ssh_config がありません。'; return 1; }
    ssh -G -F "$SD_CLIENT/ssh_config" dojo-hop > "$LAB_STATE/client-hop.txt" || return 1
    ssh -G -F "$SD_CLIENT/ssh_config" dojo-target > "$LAB_STATE/client-target.txt" || return 1
    python3 - "$LAB_STATE/client-hop.txt" "$LAB_STATE/client-target.txt" "$SD_CLIENT" "$SD_PORT" <<'PY'
from pathlib import Path
import sys
hop, target, client, port = sys.argv[1:5]
def load(p):
    v = {}
    for line in Path(p).read_text().splitlines():
        k, _, val = line.partition(' ')
        v.setdefault(k, []).append(val)
    return v
for name, p, user in (('dojo-hop', hop, 'dojo-hop'), ('dojo-target', target, 'dojo-hard')):
    v = load(p)
    for k, want in {'hostname': '127.0.0.1', 'port': port, 'user': user,
                    'identitiesonly': 'yes', 'batchmode': 'yes'}.items():
        assert v.get(k) == [want], '%s: %s が不正' % (name, k)
    assert v.get('stricthostkeychecking') in (['true'], ['yes']), name + ': ホスト鍵検証は必須'
    assert v.get('userknownhostsfile') == [client + '/known_hosts'], name + ': 専用known_hosts'
    assert client + '/id_ed25519' in v.get('identityfile', []), name + ': 専用鍵'
    assert v.get('proxycommand', ['none']) == ['none'], name + ': ProxyCommandは使わない'
v = load(target)
assert v.get('proxyjump', ['none']) != ['none'], 'dojo-target に ProxyJump が必要です'
assert load(hop).get('proxyjump', ['none']) == ['none'], 'dojo-hop 自体は中継しません'
PY
}

lab_setup() {
    _sshd_paths || return 1
    [[ ! -e $SD_UNIT && ! -e $SD_DIR && ! -e $SD_CLIENT ]] || { echo '専用構成が既にあります。上書きしません。'; return 1; }
    if getent passwd dojo-hard >/dev/null || getent passwd dojo-hop >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    getent passwd ubuntu >/dev/null || return 1
    command -v sshd >/dev/null && command -v ssh-keygen >/dev/null || return 1
    install -d -m 0755 /run/sshd
    local pw hash
    pw=$(cat /proc/sys/kernel/random/uuid)
    hash=$(openssl passwd -6 "$pw") || return 1
    useradd --create-home --shell /bin/bash --password "$hash" dojo-hard || return 1
    echo dojo-hard >> "$LAB_STATE/owns-account"
    useradd --create-home --shell /usr/sbin/nologin --password "$hash" dojo-hop || return 1
    echo dojo-hop >> "$LAB_STATE/owns-account"
    install -d -m 0755 "$SD_DIR" "$SD_DIR/keys"
    ssh-keygen -q -t ed25519 -N '' -f "$SD_DIR/hostkey"
    install -d -o ubuntu -g ubuntu -m 0700 "$SD_CLIENT"
    ssh-keygen -q -t ed25519 -N '' -C dojo-sshd-lab -f "$SD_CLIENT/id_ed25519"
    chown ubuntu:ubuntu "$SD_CLIENT/id_ed25519" "$SD_CLIENT/id_ed25519.pub"
    local u
    for u in dojo-hard dojo-hop root; do
        install -o root -g root -m 0644 "$SD_CLIENT/id_ed25519.pub" "$SD_DIR/keys/$u"
    done
    awk -v p="$SD_PORT" '{print "[127.0.0.1]:" p " " $1 " " $2}' "$SD_DIR/hostkey.pub" > "$SD_CLIENT/known_hosts"
    chown ubuntu:ubuntu "$SD_CLIENT/known_hosts"
    printf '%s\n' "$pw" > "$SD_CLIENT/password.txt"
    chown ubuntu:ubuntu "$SD_CLIENT/password.txt"; chmod 0600 "$SD_CLIENT/password.txt"
    printf '#!/bin/sh\ncat %s\n' "$LAB_STATE/password" > "$LAB_STATE/askpass.sh"
    printf '%s\n' "$pw" > "$LAB_STATE/password"
    chmod 0700 "$LAB_STATE/askpass.sh"; chmod 0600 "$LAB_STATE/password"
    _sshd_loose_config > "$SD_CONF"
    chmod 0644 "$SD_CONF"
    sshd -t -f "$SD_CONF" || return 1
    cat > "$SD_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated hardening exercise sshd (port $SD_PORT)
After=network.target
[Service]
ExecStartPre=/usr/bin/install -d -m 0755 /run/sshd
ExecStartPre=/usr/sbin/sshd -t -f $SD_CONF
ExecStart=/usr/sbin/sshd -D -e -f $SD_CONF
ExecReload=/usr/sbin/sshd -t -f $SD_CONF
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$SD_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-sshd.service || return 1
    cat > "$SD_CLIENT/TASK.txt" <<TASK
この課題はapp VMのubuntuユーザーで操作する。専用sshdは127.0.0.1:$SD_PORT（OS標準sshdとは別）。
設定: $SD_CONF（sudoで編集）。アカウント: dojo-hard（本命）、dojo-hop（中継用）。
鍵: ~/dojo-sshd-client/id_ed25519。パスワード: ~/dojo-sshd-client/password.txt
1. 現状の緩い設定を確認する。パスワード認証やroot直接ログインが通ってしまうことを実接続で観察:
   sudo sshd -T -f $SD_CONF | grep -Ei 'password|rootlogin|maxauth|allowusers'
   ssh -v -o PubkeyAuthentication=no -o PreferredAuthentications=password -p $SD_PORT dojo-hard@127.0.0.1 true
   （-vの "Authentications that can continue" に注目）
2. 設定を堅牢化する:
   - パスワードとkeyboard-interactiveを無効、rootログイン禁止
   - AllowUsersは専用の2アカウントのみ、MaxAuthTriesは小さく（3以下）
   - Port/ListenAddress/HostKey/AuthorizedKeysFileなど他の行は変えない
3. 反映前に必ず検証し、その後reload（restartより接続を保てる）:
   sudo sshd -t -f $SD_CONF
   sudo systemctl reload dojo-sshd.service
   検証せずに壊れた設定を反映すると全員締め出される。鍵ログインが生きているかも必ず確認する。
4. 実接続で証明: 鍵ログインは成功し、パスワード指定・root指定は拒否される
   ssh -i ~/dojo-sshd-client/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=~/dojo-sshd-client/known_hosts -p $SD_PORT dojo-hard@127.0.0.1 id
   拒否時のメッセージの認証方式一覧を読む。
5. ~/dojo-sshd-client/ssh_config を書く。Host dojo-hop（dojo-hop）と Host dojo-target（dojo-hard、ProxyJumpでdojo-hop経由）。
   どちらも HostName 127.0.0.1、Port $SD_PORT、IdentityFile 絶対パス、UserKnownHostsFile 絶対パス、
   IdentitiesOnly yes、StrictHostKeyChecking yes、BatchMode yes。
   ssh -G -F ssh_config dojo-target で実効値を確認し、ssh -F ssh_config dojo-target id で実際に中継する。
   dojo-hopのシェルはnologinだが、ProxyJumpは転送だけなので通る。
6. sudo dojo-vm-lab sshd break （緩い設定が配布し直される）。もう一度堅牢化して反映。
7. sudo dojo-vm-lab sshd check
8. 終了後 sudo dojo-vm-lab sshd reset （専用アカウント・設定・鍵を削除）
実務ではAllowGroups、Match、fail2ban、鍵の失効なども併用する。本物のsshdの設定変更は別のコンソールを開いたまま行う。
TASK
    chown ubuntu:ubuntu "$SD_CLIENT/TASK.txt"
    echo "手順: $SD_CLIENT/TASK.txt。専用sshd(127.0.0.1:$SD_PORT)で操作します。"
}

lab_break() {
    _sshd_paths || return 1
    [[ -f $LAB_STATE/owns-account && -f $SD_CONF && -f $SD_CLIENT/id_ed25519 && -f $LAB_STATE/unit.sha256 ]] || { echo 'まずsetupしてください。'; return 1; }
    _sshd_loose_config > "$SD_CONF"
    sshd -t -f "$SD_CONF" || return 1
    systemctl reload dojo-sshd.service || return 1
    local i ok=
    for i in 1 2 3 4 5 6; do
        if _sshd_password_ssh dojo-hard >/dev/null 2>&1; then ok=1; break; fi
        sleep 1
    done
    [[ -n $ok ]] || { echo '緩い設定の反映を確認できません。'; return 1; }
    _sshd_key_ssh root true >/dev/null 2>&1 || { echo 'root直接ログインが通る状態を確認できません。'; return 1; }
    touch "$LAB_STATE/fault"
    echo '緩い設定(パスワード認証・root許可)が配布されました。堅牢化して検証、reloadし直してください。'
}

lab_check() {
    _sshd_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで緩い設定を配布し、堅牢化し直してください。'; return 1; }
    [[ -f $LAB_STATE/owns-account && -f $LAB_STATE/unit.sha256 ]] || return 1
    [[ $(sha256sum "$SD_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || { echo 'unitは変更せず設定ファイルだけを直します。'; return 1; }
    systemctl is-active --quiet dojo-sshd.service || { echo '専用sshdが停止しています。sshd -tで検証してから起動します。'; return 1; }
    sshd -t -f "$SD_CONF" || { echo 'sshd -t が失敗する設定です。'; return 1; }
    local u problems
    for u in dojo-hard dojo-hop root; do
        _sshd_effective "$u" "$LAB_STATE/effective-$u.txt" || return 1
        if ! problems=$(_sshd_policy "$LAB_STATE/effective-$u.txt" "$u"); then
            echo "実効設定(sshd -T, user=$u)が不十分です:"; echo "$problems"; return 1
        fi
    done
    # Lock-out guard: the running daemon must still accept key logins.
    _sshd_key_ssh_retry dojo-hard 'test "$(id -un)" = dojo-hard' || { echo '鍵ログインできません。締め出し状態の設定です。'; return 1; }
    # The running daemon (after reload) must refuse passwords and root.
    if _sshd_password_ssh dojo-hard >/dev/null 2>&1; then echo '稼働中のsshdでパスワードログインが通ります(reload済みか確認)。'; return 1; fi
    local denied
    denied=$(ssh -n -F /dev/null -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive \
        -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$SD_CLIENT/known_hosts" \
        -o ConnectTimeout=3 -p "$SD_PORT" dojo-hard@127.0.0.1 true 2>&1) && return 1
    [[ $denied == *'Permission denied (publickey)'* ]] || { echo "拒否メッセージが想定外です: $denied"; return 1; }
    if _sshd_key_ssh root true >/dev/null 2>&1; then echo 'rootが鍵でログインできます。'; return 1; fi
    # ssh_config and a real ProxyJump hop through dojo-hop.
    _sshd_client_config || { echo 'ssh_configの実効値(ssh -G)を確認してください。'; return 1; }
    local before after who
    before=$(journalctl -u dojo-sshd.service --no-pager -o cat 2>/dev/null | grep -c 'Accepted publickey for dojo-hop' || true)
    who=$(ssh -n -F "$SD_CLIENT/ssh_config" dojo-target 'id -un') || { echo 'ProxyJump経由の接続に失敗しました。'; return 1; }
    [[ $who == dojo-hard ]] || return 1
    sleep 1
    after=$(journalctl -u dojo-sshd.service --no-pager -o cat 2>/dev/null | grep -c 'Accepted publickey for dojo-hop' || true)
    (( after > before )) || { echo 'dojo-hopを経由した接続がログに残っていません。'; return 1; }
    echo 'PASS: sshd -T実効値・reload済みデーモンの鍵のみ認証・パスワード/root拒否・ProxyJump経由接続を確認しました。'
}

lab_reset() {
    _sshd_paths || return 1
    [[ -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成したアカウントではありません。'; return 1; }
    local u
    systemctl disable --now dojo-sshd.service 2>/dev/null || true
    rm -f -- "$SD_UNIT"
    systemctl daemon-reload
    while read -r u; do
        [[ $u == dojo-hard || $u == dojo-hop ]] && userdel --remove "$u" 2>/dev/null
    done < "$LAB_STATE/owns-account"
    rm -rf -- "$SD_DIR" "$SD_CLIENT"
    rm -f -- "$LAB_STATE/owns-account" "$LAB_STATE/fault" "$LAB_STATE/unit.sha256" "$LAB_STATE/askpass.sh" "$LAB_STATE/password" \
        "$LAB_STATE"/effective-*.txt "$LAB_STATE/client-hop.txt" "$LAB_STATE/client-target.txt" /run/dojo-sshd.pid
    echo '専用sshd構成を削除しました。OS標準sshdの設定は変更していません。'
}
