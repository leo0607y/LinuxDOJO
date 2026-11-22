#!/bin/bash
# title: nftablesで基本ファイアウォールを適用し、接続を保ったまま復旧する
# roles: app
# Guest-only. Uses only the dedicated table "inet dojo_fw"; never touches ufw or other nftables tables.

_fw_ctx() {
    [[ ${LAB_ID:-} == firewall && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/firewall ]] || { echo 'firewall: unexpected lab context' >&2; return 1; }
    FW_NS=dojo-fw-peer
    FW_HOST_IF=dojo-fwh
    FW_PEER_IF=dojo-fwp
    FW_HOST_IP=10.77.0.1
    FW_PEER_IP=10.77.0.2
    FW_DIR=/etc/dojo-firewall
    FW_RULES=$FW_DIR/rules.nft
    FW_UNITS="dojo-fw-web-18080 dojo-fw-web-18081"
    [[ ! -L $FW_DIR && ! -L $FW_RULES && ! -L /etc/systemd/system/dojo-fw-web-18080.service && ! -L /etc/systemd/system/dojo-fw-web-18081.service ]] || { echo 'firewall: unexpected lab context' >&2; return 1; }
    local u
    for u in $FW_UNITS; do
        if [[ -e /etc/systemd/system/$u.service ]] && ! grep -qx '# LinuxDOJO VM module: firewall' "/etc/systemd/system/$u.service"; then
            echo "別用途のunitは変更しません: $u" >&2; return 1
        fi
    done
}

# Real TCP probe from the peer namespace (traffic enters through the input hook, unlike loopback).
# $1 = port. Exit 0 only when a full request/response exchange works.
_fw_probe() {
    ip netns exec "$FW_NS" python3 - "$FW_HOST_IP" "$1" <<'PY'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), timeout=2)
    s.settimeout(2)
    if port == 22:
        data = s.recv(64)
        ok = data.startswith(b'SSH-')
    else:
        s.sendall(b'GET /health HTTP/1.0\r\n\r\n')
        data = b''
        while True:
            chunk = s.recv(512)
            if not chunk: break
            data += chunk
        ok = b'linuxdojo-firewall' in data
    s.close()
except OSError:
    ok = False
raise SystemExit(0 if ok else 1)
PY
}

# Host-initiated connection to a listener inside the peer namespace: the SYN-ACK returns through the
# input hook, so it only works when established/related traffic is accepted.
_fw_reverse_probe() {
    ip netns exec "$FW_NS" python3 - "$FW_PEER_IP" <<'PY' &
import socket, sys
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((sys.argv[1], 19099)); s.listen(1); s.settimeout(4)
try:
    c, _ = s.accept(); c.sendall(b'ok'); c.close()
except OSError:
    pass
PY
    local pid=$!
    sleep 0.7
    python3 - "$FW_PEER_IP" <<'PY'
import socket, sys
try:
    s = socket.create_connection((sys.argv[1], 19099), timeout=2)
    s.settimeout(2)
    ok = s.recv(8) == b'ok'
except OSError:
    ok = False
raise SystemExit(0 if ok else 1)
PY
    local rc=$?
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    return $rc
}

_fw_loopback_probe() {
    python3 - "$1" <<'PY'
import socket, sys
try:
    s = socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=2)
    s.settimeout(2)
    s.sendall(b'GET /health HTTP/1.0\r\n\r\n')
    data = b''
    while True:
        chunk = s.recv(512)
        if not chunk: break
        data += chunk
    ok = b'linuxdojo-firewall' in data
except OSError:
    ok = False
raise SystemExit(0 if ok else 1)
PY
}

_fw_write_safe_apply() {
    cat > "$LAB_STATE/safe-apply" <<'EOS'
#!/bin/bash
# Usage: sudo safe-apply RULEFILE
# 1) syntax check  2) apply  3) schedule automatic rollback in 90s unless $STATE/confirm exists
set -u
STATE=/var/lib/linuxdojo-vm-lab/state/firewall
[[ $EUID == 0 ]] || { echo 'root で実行してください(sudo)。' >&2; exit 2; }
file=${1:-}
[[ -n $file && -f $file && ! -L $file ]] || { echo "使い方: $0 RULEFILE" >&2; exit 2; }
if grep -Eq '^[[:space:]]*flush[[:space:]]+ruleset' "$file"; then
    echo 'flush ruleset は使えません。専用テーブル inet dojo_fw だけを扱います。' >&2; exit 2
fi
nft -c -f "$file" || { echo '構文エラーのため適用しません。' >&2; exit 1; }
rm -f "$STATE/confirm"
systemctl stop dojo-fw-rollback.timer dojo-fw-rollback.service 2>/dev/null
systemctl reset-failed dojo-fw-rollback.timer dojo-fw-rollback.service 2>/dev/null
nft delete table inet dojo_fw 2>/dev/null
if ! nft -f "$file"; then
    echo '適用に失敗しました。' >&2; exit 1
fi
systemd-run --quiet --unit=dojo-fw-rollback --on-active=90s \
    /bin/sh -c "[ -e $STATE/confirm ] || nft delete table inet dojo_fw" || {
    echo '自動復旧タイマーを作れないため、ルールを外します。' >&2
    nft delete table inet dojo_fw; exit 1; }
echo '適用しました。90秒以内に接続を確認し、問題なければ次を実行してください:'
echo "  sudo touch $STATE/confirm"
echo '確認しないと dojo_fw テーブルは自動で削除されます。'
EOS
    chmod 700 "$LAB_STATE/safe-apply"
}

lab_setup() {
    _fw_ctx || return
    command -v nft >/dev/null && command -v ip >/dev/null || { echo 'nft と ip(iproute2) が必要です。' >&2; return 1; }
    # www-data must be able to traverse down to $LAB_STATE/www (the dispatcher creates these 0700).
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" "$LAB_STATE" || return 1
    install -d -m 755 "$LAB_STATE/www" "$FW_DIR"
    printf 'linuxdojo-firewall\n' > "$LAB_STATE/www/health"
    chmod 644 "$LAB_STATE/www/health"
    local port
    for port in 18080 18081; do
        cat > /etc/systemd/system/dojo-fw-web-$port.service <<UNIT
# LinuxDOJO VM module: firewall
[Unit]
Description=LinuxDOJO firewall lab HTTP $port
After=network.target
[Service]
User=www-data
ExecStart=/usr/bin/python3 -m http.server $port --bind 0.0.0.0 --directory $LAB_STATE/www
Restart=on-failure
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
UNIT
    done
    # namespace + veth; net-created records that this lab owns them
    if ! ip netns list | grep -q "^$FW_NS\b"; then
        ip netns add "$FW_NS" || return 1
    fi
    if ! ip link show "$FW_HOST_IF" >/dev/null 2>&1; then
        ip link add "$FW_HOST_IF" type veth peer name "$FW_PEER_IF" || return 1
        ip link set "$FW_PEER_IF" netns "$FW_NS" || return 1
        ip addr add "$FW_HOST_IP/24" dev "$FW_HOST_IF"
        ip link set "$FW_HOST_IF" up
        ip netns exec "$FW_NS" ip addr add "$FW_PEER_IP/24" dev "$FW_PEER_IF"
        ip netns exec "$FW_NS" ip link set "$FW_PEER_IF" up
        ip netns exec "$FW_NS" ip link set lo up
    fi
    : > "$LAB_STATE/net-created"
    systemctl daemon-reload
    systemctl enable --now dojo-fw-web-18080.service dojo-fw-web-18081.service
    _fw_write_safe_apply
    rm -f "$LAB_STATE/broken" "$LAB_STATE/confirm"
    if [[ ! -e $FW_RULES ]]; then
        printf '# LinuxDOJO firewall lab: ここに nft ルールを書く (table inet dojo_fw)\n' > "$FW_RULES"
    fi
    cat > "$LAB_STATE/TASKS.txt" <<TASKS
サーバ(app VM)は SSH(22)、HTTP 18080、18081 で待ち受けています。
namespace $FW_NS ($FW_PEER_IP) からのアクセスは、本物のファイアウォール(inputフック)を通ります。
1. sudo dojo-vm-lab firewall break で壊れた状態にし、namespaceから接続できないことを確認する
   (ヒント: sudo ip netns exec $FW_NS curl -m2 http://$FW_HOST_IP:18080/health)
2. $FW_RULES に、専用テーブル inet dojo_fw のルールを書く。要件:
   - policy drop の input チェーン。lo は許可、確立済み/関連接続は許可
   - tcp 22 と 18080 は許可、18081 は拒否、ICMP は許可
   - 再読込で重複しないよう、冒頭でテーブルを宣言して消す書き方(table / delete table)を調べる
3. 適用は必ず sudo $LAB_STATE/safe-apply $FW_RULES を使う(構文検査後に適用し、90秒で自動ロールバック予約)
4. 接続が保てたことを確認して sudo touch $LAB_STATE/confirm で確定する
5. sudo dojo-vm-lab firewall check
既存の ufw や他の nftables テーブルは変更しないこと。
TASKS
    cat "$LAB_STATE/TASKS.txt"
    if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q 'Status: active'; then
        echo '注意: ufwが有効です。この実習の判定に影響する場合があります。' >&2
    fi
    return 0
}

lab_break() {
    _fw_ctx || return
    [[ -f $LAB_STATE/net-created && -x $LAB_STATE/safe-apply ]] || { echo '先に setup を実行してください。' >&2; return 1; }
    cat > "$FW_RULES" <<'BROKEN'
# LinuxDOJO firewall lab: BROKEN (dojo-fwh からの入力を全て破棄)
table inet dojo_fw
delete table inet dojo_fw
table inet dojo_fw {
    chain input {
        type filter hook input priority 0; policy accept;
        iifname "dojo-fwh" drop
    }
}
BROKEN
    systemctl stop dojo-fw-rollback.timer dojo-fw-rollback.service 2>/dev/null || true
    nft delete table inet dojo_fw 2>/dev/null || true
    nft -f "$FW_RULES" || return 1
    rm -f "$LAB_STATE/confirm"
    : > "$LAB_STATE/broken"
    echo "dojo-fwh からの入力だけを破棄する壊れたルールを適用しました(本線のSSHは影響なし)。$FW_RULES を直してください。"
}

_fw_verify_live() {
    local listing
    listing=$(nft list table inet dojo_fw 2>/dev/null) || { echo 'テーブル inet dojo_fw がありません。' >&2; return 1; }
    grep -Eq 'hook input .*policy drop' <<<"$listing" || { echo 'input フックの policy drop が必要です。' >&2; return 1; }
    _fw_probe 22 || { echo 'namespaceからSSH(22)に接続できません。' >&2; return 1; }
    _fw_probe 18080 || { echo 'namespaceから18080に接続できません。' >&2; return 1; }
    if _fw_probe 18081; then echo '18081 が拒否されていません。' >&2; return 1; fi
    ip netns exec "$FW_NS" ping -c1 -W2 "$FW_HOST_IP" >/dev/null 2>&1 || { echo 'ICMPが許可されていません。' >&2; return 1; }
    _fw_reverse_probe || { echo '確立済み/関連接続(ct state established,related)が許可されていません。' >&2; return 1; }
}

lab_check() {
    _fw_ctx || return
    [[ -f $LAB_STATE/broken ]] || { echo 'break済みの記録がありません。先に break を実行してください。' >&2; return 1; }
    [[ -f $LAB_STATE/net-created ]] || return 1
    [[ -f $LAB_STATE/confirm ]] || { echo 'confirm がありません。接続確認後に sudo touch で確定してください。' >&2; return 1; }
    ip netns list | grep -q "^$FW_NS\b" || { echo 'namespace がありません。' >&2; return 1; }
    systemctl is-active --quiet dojo-fw-web-18080.service dojo-fw-web-18081.service || { echo '専用Webサービスが停止しています。' >&2; return 1; }
    _fw_loopback_probe 18081 || { echo 'loopback から 18081 に届きません(lo許可を確認)。' >&2; return 1; }
    _fw_verify_live || return 1
    # persistence: remove the table, reload from the rules file, verify again
    local backup="$LAB_STATE/table-backup.nft"
    nft list table inet dojo_fw > "$backup" || return 1
    nft delete table inet dojo_fw || return 1
    if ! nft -f "$FW_RULES"; then
        nft delete table inet dojo_fw 2>/dev/null; nft -f "$backup"
        echo "$FW_RULES から再読込できません。" >&2; return 1
    fi
    if ! _fw_verify_live; then
        echo "$FW_RULES の再読込後に要件を満たしません(永続化されていません)。" >&2
        nft delete table inet dojo_fw 2>/dev/null; nft -f "$backup"
        return 1
    fi
    # idempotence: loading the same file again must not duplicate rules
    local before after
    before=$(nft list table inet dojo_fw) && nft -f "$FW_RULES" 2>/dev/null && after=$(nft list table inet dojo_fw) || after=
    if [[ $before != "$after" ]]; then
        echo "$FW_RULES を再読込するとルールが重複/変化します。冒頭で table と delete table を書いてください。" >&2
        nft delete table inet dojo_fw 2>/dev/null; nft -f "$backup"
        return 1
    fi
    echo '基本ファイアウォールが要件通りに動作し、ルールファイルからの再読込でも同じ結果になりました。'
}

lab_reset() {
    _fw_ctx || return
    systemctl stop dojo-fw-rollback.timer dojo-fw-rollback.service 2>/dev/null || true
    systemctl reset-failed dojo-fw-rollback.timer dojo-fw-rollback.service 2>/dev/null || true
    nft delete table inet dojo_fw 2>/dev/null || true
    if [[ -f $LAB_STATE/net-created ]]; then
        ip link delete "$FW_HOST_IF" 2>/dev/null || true
        ip netns delete "$FW_NS" 2>/dev/null || true
    fi
    local u
    for u in $FW_UNITS; do
        if [[ -f /etc/systemd/system/$u.service ]] && grep -qx '# LinuxDOJO VM module: firewall' "/etc/systemd/system/$u.service"; then
            systemctl disable --now "$u.service" 2>/dev/null || true
            rm -f "/etc/systemd/system/$u.service"
        fi
    done
    systemctl daemon-reload
    rm -f "$FW_RULES"
    rmdir "$FW_DIR" 2>/dev/null || true
    rm -f "$LAB_STATE/net-created" "$LAB_STATE/broken" "$LAB_STATE/confirm" "$LAB_STATE/safe-apply" "$LAB_STATE/table-backup.nft" "$LAB_STATE/TASKS.txt"
    rm -rf "$LAB_STATE/www"
    echo '専用テーブル・namespace・veth・unit・ルールファイルを削除しました。'
}
