#!/bin/bash
# title: firewalld のゾーン/サービス/ポート/rich rule、runtime と permanent、タイマー付き自動復旧 (RHEL系)
# roles: app
# Guest-only, RHEL family only. Uses only the dedicated zone "dojo-lab" bound to the lab veth; never touches the default zone or other zones.

_fd_ctx() {
    [[ ${LAB_ID:-} == firewalld && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/firewalld ]] || { echo 'firewalld: unexpected lab context' >&2; return 1; }
    local id
    id=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-unknown}")
    case $id in
        rocky|almalinux|rhel|centos) ;;
        *) echo "${id:-unknown}: this lab needs a RHEL-family VM" >&2; return 1 ;;
    esac
    FD_NS=dojo-fd-peer
    FD_HOST_IF=dojo-fdh
    FD_PEER_IF=dojo-fdp
    FD_HOST_IP=10.78.0.1
    FD_PEER_IP=10.78.0.2
    FD_ZONE=dojo-lab
    FD_UNITS="dojo-fd-web-18080 dojo-fd-web-18081"
    FD_MARK='# LinuxDOJO VM module: firewalld'
    [[ ! -L /etc/systemd/system/dojo-fd-web-18080.service && ! -L /etc/systemd/system/dojo-fd-web-18081.service ]] || { echo 'firewalld: unexpected lab context (symlink)' >&2; return 1; }
    local u
    for u in $FD_UNITS; do
        if [[ -e /etc/systemd/system/$u.service ]] && ! grep -qx "$FD_MARK" "/etc/systemd/system/$u.service"; then
            echo "別用途のunitは変更しません: $u" >&2; return 1
        fi
    done
}

# Exit 0: full exchange OK. 2: connection actively refused (RST / ICMP unreachable). 1: anything else (timeout, prohibited).
_fd_probe() {
    ip netns exec "$FD_NS" python3 - "$FD_HOST_IP" "$1" <<'PY'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), timeout=3)
except ConnectionRefusedError:
    raise SystemExit(2)
except OSError:
    raise SystemExit(1)
try:
    s.settimeout(2)
    if port == 22:
        ok = s.recv(64).startswith(b'SSH-')
    else:
        s.sendall(b'GET /health HTTP/1.0\r\n\r\n')
        data = b''
        while True:
            chunk = s.recv(512)
            if not chunk: break
            data += chunk
        ok = b'linuxdojo-firewalld' in data
except OSError:
    ok = False
raise SystemExit(0 if ok else 1)
PY
}

_fd_write_arm() {
    cat > "$LAB_STATE/arm-rollback" <<'EOS'
#!/bin/bash
# Usage: sudo arm-rollback   (run BEFORE making risky runtime changes)
# Schedules "firewall-cmd --reload" in 90s, which discards every runtime-only change and returns to the permanent config.
# Cancel by: sudo touch $STATE/confirm   (then make the change permanent yourself with --runtime-to-permanent)
set -u
STATE=/var/lib/linuxdojo-vm-lab/state/firewalld
[[ $EUID == 0 ]] || { echo 'root で実行してください(sudo)。' >&2; exit 2; }
rm -f "$STATE/confirm"
systemctl stop dojo-fd-rollback.timer dojo-fd-rollback.service 2>/dev/null
systemctl reset-failed dojo-fd-rollback.timer dojo-fd-rollback.service 2>/dev/null
systemd-run --quiet --unit=dojo-fd-rollback --on-active=90s \
    /bin/sh -c "[ -e $STATE/confirm ] || firewall-cmd --reload" || { echo 'タイマーを作れませんでした。' >&2; exit 1; }
echo '90秒後に firewall-cmd --reload が走り、runtime だけの変更は消えます。'
echo "接続確認後に sudo touch $STATE/confirm で取り消し、sudo firewall-cmd --runtime-to-permanent で確定してください。"
EOS
    chmod 700 "$LAB_STATE/arm-rollback"
}

lab_setup() {
    _fd_ctx || return 1
    local c
    for c in firewall-cmd ip python3 curl systemctl; do
        command -v "$c" >/dev/null || { echo "$c が必要です (dnf install firewalld iproute python3 curl)。" >&2; return 1; }
    done
    systemctl is-active --quiet firewalld || { echo 'firewalld が動いていません (systemctl enable --now firewalld)。' >&2; return 1; }
    systemctl is-active --quiet sshd || { echo 'sshd が動いていません。' >&2; return 1; }
    if firewall-cmd --permanent --get-zones | tr ' ' '\n' | grep -qx "$FD_ZONE" && [[ ! -f $LAB_STATE/created ]]; then
        echo "ゾーン $FD_ZONE が既にあります。上書きしません。" >&2; return 1
    fi
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" 2>/dev/null || true
    : > "$LAB_STATE/created"
    install -d -m 755 "$LAB_STATE/www"
    printf 'linuxdojo-firewalld\n' > "$LAB_STATE/www/health"
    chmod 644 "$LAB_STATE/www/health"
    local port
    for port in 18080 18081; do
        cat > /etc/systemd/system/dojo-fd-web-$port.service <<UNIT
$FD_MARK
[Unit]
Description=LinuxDOJO firewalld lab HTTP $port
After=network.target
[Service]
User=nobody
ExecStart=/usr/bin/python3 -m http.server $port --bind 0.0.0.0 --directory $LAB_STATE/www
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    done
    if ! ip netns list | grep -q "^$FD_NS\b"; then ip netns add "$FD_NS" || return 1; fi
    if ! ip link show "$FD_HOST_IF" >/dev/null 2>&1; then
        ip link add "$FD_HOST_IF" type veth peer name "$FD_PEER_IF" || return 1
        ip link set "$FD_PEER_IF" netns "$FD_NS" || return 1
        ip addr add "$FD_HOST_IP/24" dev "$FD_HOST_IF"
        ip link set "$FD_HOST_IF" up
        ip netns exec "$FD_NS" ip addr add "$FD_PEER_IP/24" dev "$FD_PEER_IF"
        ip netns exec "$FD_NS" ip link set "$FD_PEER_IF" up
        ip netns exec "$FD_NS" ip link set lo up
    fi
    : > "$LAB_STATE/net-created"
    systemctl daemon-reload
    systemctl enable --now dojo-fd-web-18080.service dojo-fd-web-18081.service || return 1
    firewall-cmd --permanent --new-zone="$FD_ZONE" >/dev/null || return 1
    firewall-cmd --reload >/dev/null
    firewall-cmd --permanent --zone="$FD_ZONE" --add-interface="$FD_HOST_IF" >/dev/null
    firewall-cmd --reload >/dev/null
    _fd_write_arm
    cat > "$LAB_STATE/TASKS.txt" <<TASKS
専用ゾーン $FD_ZONE に veth $FD_HOST_IF ($FD_HOST_IP) を割り当てました。namespace $FD_NS ($FD_PEER_IP) からの通信は本物の firewalld を通ります。
app VM は SSH(22)、HTTP 18080、18081 で待ち受けています。既定ゾーンや他のゾーンは変更しないこと。
1. firewall-cmd --get-active-zones / --list-all --zone=$FD_ZONE で現状を見る。--get-services で組み込みサービスを眺める
2. sudo dojo-vm-lab firewalld break で故障状態にし、namespace から届かないことを確認
   (sudo ip netns exec $FD_NS curl -m3 http://$FD_HOST_IP:18080/health)
3. 危ない runtime 変更の前に sudo $LAB_STATE/arm-rollback で 90 秒後の自動 --reload を仕掛ける (--panic-on は使わない)
4. $FD_ZONE に次を (まず runtime で) 設定して疎通を確認:
   - ssh サービスを許可、18080/tcp を許可
   - 18081/tcp は rich rule で reject する (拒否が「接続拒否」として返ること。単に塞ぐだけでは不合格)
   - 通常のゾーン target のままで ICMP(ping) が通ること
5. 確認できたら sudo touch $LAB_STATE/confirm で自動復旧を止め、firewall-cmd --runtime-to-permanent (または --permanent で書き直し) で永続化
6. firewall-cmd --reload しても同じ結果になることを確認してから sudo dojo-vm-lab firewalld check
TASKS
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _fd_ctx || return 1
    [[ -f $LAB_STATE/net-created && -x $LAB_STATE/arm-rollback ]] || { echo '先に setup を実行してください。' >&2; return 1; }
    firewall-cmd --permanent --zone="$FD_ZONE" --set-target=DROP >/dev/null || return 1
    local s p r
    for s in $(firewall-cmd --permanent --zone="$FD_ZONE" --list-services); do firewall-cmd --permanent --zone="$FD_ZONE" --remove-service="$s" >/dev/null; done
    for p in $(firewall-cmd --permanent --zone="$FD_ZONE" --list-ports); do firewall-cmd --permanent --zone="$FD_ZONE" --remove-port="$p" >/dev/null; done
    while IFS= read -r r; do if [[ -n $r ]]; then firewall-cmd --permanent --zone="$FD_ZONE" --remove-rich-rule="$r" >/dev/null; fi; done \
        < <(firewall-cmd --permanent --zone="$FD_ZONE" --list-rich-rules)
    firewall-cmd --reload >/dev/null || return 1
    systemctl stop dojo-fd-rollback.timer dojo-fd-rollback.service 2>/dev/null || true
    rm -f "$LAB_STATE/confirm"
    : > "$LAB_STATE/broken"
    echo "ゾーン $FD_ZONE を target=DROP・許可なしにしました(本線のSSHは影響なし)。"
}

lab_check() {
    _fd_ctx || return 1
    [[ -f $LAB_STATE/broken ]] || { echo 'break済みの記録がありません。先に break を実行してください。' >&2; return 1; }
    [[ -f $LAB_STATE/net-created ]] || return 1
    [[ -f $LAB_STATE/confirm ]] || { echo 'confirm がありません。接続確認後に sudo touch で確定してください。' >&2; return 1; }
    systemctl is-active --quiet firewalld || { echo 'firewalld が停止しています。' >&2; return 1; }
    [[ $(firewall-cmd --query-panic 2>/dev/null) == no ]] || { echo 'panic mode が有効です。firewall-cmd --panic-off してください。' >&2; return 1; }
    ip netns list | grep -q "^$FD_NS\b" || { echo 'namespace がありません。' >&2; return 1; }
    systemctl is-active --quiet dojo-fd-web-18080.service dojo-fd-web-18081.service || { echo '専用Webサービスが停止しています。' >&2; return 1; }
    [[ $(firewall-cmd --get-zone-of-interface="$FD_HOST_IF" 2>/dev/null) == "$FD_ZONE" ]] || { echo "$FD_HOST_IF が $FD_ZONE にありません。" >&2; return 1; }
    [[ $(firewall-cmd --permanent --zone="$FD_ZONE" --get-target 2>/dev/null) != DROP ]] || { echo 'permanent の target が DROP のままです。' >&2; return 1; }
    firewall-cmd --permanent --zone="$FD_ZONE" --list-rich-rules | grep -Eq '18081.*reject|reject.*18081' || { echo 'permanent に 18081 の rich rule(reject) がありません。' >&2; return 1; }
    # runtime must equal permanent: reload (discards runtime-only changes), then probe the real behavior
    firewall-cmd --reload >/dev/null || return 1
    local rc
    _fd_probe 22 || { echo 'reload 後、namespace から SSH(22) に接続できません(permanent 化漏れ?)。' >&2; return 1; }
    _fd_probe 18080 || { echo 'reload 後、18080 に接続できません(permanent 化漏れ?)。' >&2; return 1; }
    _fd_probe 18081 && rc=0 || rc=$?
    [[ $rc -eq 2 ]] || { echo "18081 が 接続拒否(reject)になっていません (rc=$rc。0=通る, 1=drop/prohibited)。" >&2; return 1; }
    ip netns exec "$FD_NS" ping -c1 -W2 "$FD_HOST_IP" >/dev/null 2>&1 || { echo 'ICMP が通りません。' >&2; return 1; }
    [[ $(firewall-cmd --get-default-zone) != "$FD_ZONE" ]] || { echo '既定ゾーンを変更しないでください。' >&2; return 1; }
    echo 'permanent の設定を --reload で再読込しても、ssh/18080 許可・18081 reject・ICMP が実接続で確認できました。'
}

lab_reset() {
    _fd_ctx || return 1
    systemctl stop dojo-fd-rollback.timer dojo-fd-rollback.service 2>/dev/null || true
    systemctl reset-failed dojo-fd-rollback.timer dojo-fd-rollback.service 2>/dev/null || true
    if [[ -f $LAB_STATE/created ]] && command -v firewall-cmd >/dev/null; then
        firewall-cmd --panic-off >/dev/null 2>&1 || true
        firewall-cmd --permanent --delete-zone="$FD_ZONE" >/dev/null 2>&1 || true
        firewall-cmd --reload >/dev/null 2>&1 || true
    fi
    if [[ -f $LAB_STATE/net-created ]]; then
        ip link delete "$FD_HOST_IF" 2>/dev/null || true
        ip netns delete "$FD_NS" 2>/dev/null || true
    fi
    local u
    for u in $FD_UNITS; do
        if [[ -f /etc/systemd/system/$u.service ]] && grep -qx "$FD_MARK" "/etc/systemd/system/$u.service"; then
            systemctl disable --now "$u.service" 2>/dev/null || true
            rm -f "/etc/systemd/system/$u.service"
        fi
    done
    systemctl daemon-reload
    rm -rf "${LAB_STATE:?}/www"
    rm -f "${LAB_STATE:?}/created" "${LAB_STATE:?}/net-created" "${LAB_STATE:?}/broken" "${LAB_STATE:?}/confirm" "${LAB_STATE:?}/arm-rollback" "${LAB_STATE:?}/TASKS.txt"
    echo '専用ゾーン・namespace・veth・unit を削除しました。'
}
