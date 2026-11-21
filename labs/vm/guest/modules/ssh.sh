# title: SSH接続・ホスト鍵照合・scp/rsync転送・権限障害からの復旧
# Guest-only, dedicated loopback listener and dedicated account; no system sshd changes.

_ssh_paths() {
    [[ ${LAB_ID:-} == ssh && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/ssh ]] || { echo 'ssh: unexpected lab context' >&2; return 1; }
    SSH_UNIT=/etc/systemd/system/dojo-ssh.service
    SSH_REMOTE=/srv/dojo-remote
    SSH_CLIENT=/home/ubuntu/dojo-ssh-client
    [[ ! -L $SSH_UNIT && ! -L $SSH_REMOTE && ! -L $SSH_CLIENT ]] || return 1
}

_ssh_connect() {
    ssh -n -F /dev/null -i "$SSH_CLIENT/id_ed25519" -o BatchMode=yes -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$SSH_CLIENT/known_hosts" \
        -o ConnectTimeout=3 -p 22222 dojo-remote@127.0.0.1 "$@"
}

_ssh_client_config() {
    [[ -f $SSH_CLIENT/ssh_config && ! -L $SSH_CLIENT/ssh_config ]] || return 1
    ssh -G -F "$SSH_CLIENT/ssh_config" dojo > "$LAB_STATE/client-effective.txt" || return 1
    python3 - "$LAB_STATE/client-effective.txt" "$SSH_CLIENT" <<'PY'
from pathlib import Path
import sys
values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    key, _, value = line.partition(' ')
    values.setdefault(key, []).append(value)
client = sys.argv[2]
for key, value in {'hostname': '127.0.0.1', 'port': '22222', 'user': 'dojo-remote',
                   'identitiesonly': 'yes', 'batchmode': 'yes'}.items():
    assert values.get(key) == [value], 'ssh_config: ' + key
assert values.get('stricthostkeychecking') in (['true'], ['yes']), 'host key checking is required'
assert values.get('userknownhostsfile') == [client + '/known_hosts'], 'dedicated known_hosts is required'
assert client + '/id_ed25519' in values.get('identityfile', []), 'dedicated identity is required'
assert values.get('proxycommand', ['none']) == ['none'], 'no external proxy in this loopback lab'
assert values.get('proxyjump', ['none']) == ['none'], 'no external jump host in this loopback lab'
PY
}

lab_setup() {
    _ssh_paths || return 1
    [[ ! -e $SSH_UNIT && ! -e $SSH_REMOTE && ! -e $SSH_CLIENT ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if getent passwd dojo-remote >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    getent passwd ubuntu >/dev/null || return 1
    command -v sshd >/dev/null && command -v rsync >/dev/null || return 1
    install -d -m 0755 /run/sshd
    # Random unknown password keeps account unlocked; only public-key auth is enabled.
    local password_hash
    password_hash=$(openssl passwd -6 "$(cat /proc/sys/kernel/random/uuid)") || return 1
    useradd --create-home --home-dir "$SSH_REMOTE" --shell /bin/bash --password "$password_hash" dojo-remote
    touch "$LAB_STATE/owns-account"
    install -d -o dojo-remote -g dojo-remote -m 0700 "$SSH_REMOTE/.ssh"
    install -d -o dojo-remote -g dojo-remote -m 0750 "$SSH_REMOTE/inbox"
    install -o dojo-remote -g dojo-remote -m 0600 /dev/null "$SSH_REMOTE/.ssh/authorized_keys"
    install -d -o ubuntu -g ubuntu -m 0700 "$SSH_CLIENT"
    printf 'training-%s\n' "$(cat /proc/sys/kernel/random/uuid)" > "$SSH_CLIENT/upload.txt"
    chown ubuntu:ubuntu "$SSH_CLIENT/upload.txt"
    sha256sum "$SSH_CLIENT/upload.txt" | cut -d ' ' -f 1 > "$LAB_STATE/payload.sha256"
    ssh-keygen -q -t ed25519 -N '' -f "$LAB_STATE/hostkey"
    cat > "$LAB_STATE/sshd_config" <<CONF
ListenAddress 127.0.0.1
Port 22222
HostKey $LAB_STATE/hostkey
PidFile $LAB_STATE/sshd.pid
AuthorizedKeysFile .ssh/authorized_keys
StrictModes yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers dojo-remote
UsePAM no
Subsystem sftp internal-sftp
LogLevel VERBOSE
CONF
    sshd -t -f "$LAB_STATE/sshd_config"
    sha256sum "$LAB_STATE/sshd_config" | cut -d ' ' -f 1 > "$LAB_STATE/config.sha256"
    cat > "$SSH_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated loopback SSH exercise
After=network.target
[Service]
ExecStartPre=/usr/bin/install -d -m 0755 /run/sshd
ExecStart=/usr/sbin/sshd -D -e -f $LAB_STATE/sshd_config
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$SSH_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-ssh.service
    cat > "$SSH_CLIENT/TASK.txt" <<'TASK'
この課題はapp VMのubuntuユーザーで操作する。接続先は127.0.0.1:22222だけ。
cd ~/dojo-ssh-client
1. ssh-keygen -t ed25519 -N '' -f id_ed25519
   sudo install -o dojo-remote -g dojo-remote -m 0600 id_ed25519.pub /srv/dojo-remote/.ssh/authorized_keys
2. 信頼したVMコンソールでサーバー鍵の指紋を確認する:
   sudo ssh-keygen -lf /var/lib/linuxdojo-vm-lab/state/ssh/hostkey.pub
   この同じコンソールから公開鍵をknown_hostsへ登録する:
   sudo awk '{print "[127.0.0.1]:22222 " $1 " " $2}' /var/lib/linuxdojo-vm-lab/state/ssh/hostkey.pub > known_hosts
   ssh-keygen -lf known_hosts でも指紋を照合。ssh-keyscanだけでは相手の正当性は確認できない。
3. ssh_configを作成（IdentityFileとUserKnownHostsFileは絶対パス）:
   Host dojo
       HostName 127.0.0.1
       Port 22222
       User dojo-remote
       IdentityFile /home/ubuntu/dojo-ssh-client/id_ed25519
       UserKnownHostsFile /home/ubuntu/dojo-ssh-client/known_hosts
       IdentitiesOnly yes
       StrictHostKeyChecking yes
       BatchMode yes
4. ssh -F ssh_config dojo 'id; pwd'
   scp -F ssh_config upload.txt dojo:inbox/upload.txt
5. sudo dojo-vm-lab ssh break
   ssh -vv -F ssh_config dojo true と sudo journalctl -u dojo-ssh.service -b を比較。
   authorized_keysの所有者・権限と親ディレクトリを確認し、原因を修正。
   StrictModesやホスト鍵検証を無効にして通すのは不正解。
6. mkdir -p downloaded
   rsync -av -e 'ssh -F ssh_config' dojo:inbox/upload.txt downloaded/
   cmp upload.txt downloaded/upload.txt
   sudo dojo-vm-lab ssh check
7. 終了後 sudo dojo-vm-lab ssh reset （専用ユーザー・鍵・転送データを削除）
実務では空パスフレーズの鍵をそのまま使わず、鍵保護・ssh-agent・鍵更新も学ぶ。
ポートやユーザーが違う実サーバーへの接続は既存Stage34へ。2台間の疎通はnetwork実習へ。
TASK
    chown ubuntu:ubuntu "$SSH_CLIENT/TASK.txt"
    echo "手順: $SSH_CLIENT/TASK.txt。ubuntuのシェルで操作します。"
}

lab_break() {
    _ssh_paths || return 1
    [[ -f $LAB_STATE/owns-account && -f $SSH_CLIENT/known_hosts && -f $SSH_CLIENT/id_ed25519 ]] || return 1
    _ssh_client_config || { echo 'ssh_configの実効値を確認します。'; return 1; }
    _ssh_connect true || { echo 'まず鍵とホスト鍵を準備し、接続を成功させます。'; return 1; }
    [[ -f $SSH_REMOTE/inbox/upload.txt ]] && cmp -s "$SSH_CLIENT/upload.txt" "$SSH_REMOTE/inbox/upload.txt" || { echo 'まずscpでupload.txtを転送します。'; return 1; }
    chmod 0666 "$SSH_REMOTE/.ssh/authorized_keys"
    if _ssh_connect true > "$LAB_STATE/denied.log" 2>&1; then
        echo '権限障害での拒否を確認できません。'; return 1
    fi
    touch "$LAB_STATE/fault"
    echo '接続が失敗する状態です。ssh -vvと専用サービスのログから権限を調査します。'
}

lab_check() {
    _ssh_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まず初回接続とscpを成功させ、breakで障害を作ります。'; return 1; }
    _ssh_client_config || return 1
    [[ $(sha256sum "$LAB_STATE/sshd_config" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/config.sha256") ]] || { echo 'sshdの検証設定を変更せず権限を直します。'; return 1; }
    [[ $(sha256sum "$SSH_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || return 1
    [[ $(stat -c %a "$SSH_REMOTE/.ssh/authorized_keys") == 600 && $(stat -c %U "$SSH_REMOTE/.ssh/authorized_keys") == dojo-remote ]] || { echo 'authorized_keysの所有者と600権限を確認します。'; return 1; }
    [[ $(stat -c %a "$SSH_CLIENT/id_ed25519") == 600 ]] || return 1
    [[ $(sha256sum "$SSH_CLIENT/upload.txt" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/payload.sha256") ]] || return 1
    _ssh_connect true || return 1
    cmp -s "$SSH_CLIENT/upload.txt" "$SSH_REMOTE/inbox/upload.txt" || return 1
    cmp -s "$SSH_CLIENT/upload.txt" "$SSH_CLIENT/downloaded/upload.txt" || { echo 'rsyncで取得したデータを確認します。'; return 1; }
    echo 'PASS: 鍵認証・ホスト鍵検証・実scp転送・権限障害の復旧・実rsync取得を確認しました。'
}

lab_reset() {
    _ssh_paths || return 1
    [[ -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成したアカウントではありません。'; return 1; }
    systemctl disable --now dojo-ssh.service || return 1
    rm -f -- "$SSH_UNIT"
    systemctl daemon-reload
    userdel --remove dojo-remote || return 1
    rm -rf -- "$SSH_CLIENT"
    rm -f -- "$LAB_STATE/owns-account" "$LAB_STATE/fault" "$LAB_STATE/denied.log" "$LAB_STATE/payload.sha256" "$LAB_STATE/config.sha256" "$LAB_STATE/unit.sha256" "$LAB_STATE/hostkey" "$LAB_STATE/hostkey.pub" "$LAB_STATE/sshd_config" "$LAB_STATE/sshd.pid" "$LAB_STATE/client-effective.txt"
    echo '専用SSH構成を削除しました。OS標準sshdの設定は変更していません。'
}
