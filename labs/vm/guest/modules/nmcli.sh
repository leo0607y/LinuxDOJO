#!/bin/bash
# title: nmcliで接続プロファイルを作成・修正する(ダミーNICのみ)
# roles: app
# Guest-only. Needs NetworkManager. Touches only dummy devices dojo1/dojo2 and profiles dojo-lab/dojo-lab2.

_nm_ctx() {
    if [[ ${LAB_ID:-} != nmcli || ${LAB_VM_ROLE:-} != app || ${LAB_STATE:-} != /var/lib/linuxdojo-vm-lab/state/nmcli || ${LAB_ROOT:-} != /var/lib/linuxdojo-vm-lab ]]; then
        echo 'nmcli: unexpected lab context' >&2; return 1
    fi
    [[ ! -L $LAB_STATE ]] || { echo 'nmcli: unexpected lab context' >&2; return 1; }
}

# Refuse unless NetworkManager is running and does NOT manage the primary NIC.
_nm_safe() {
    if ! command -v nmcli >/dev/null 2>&1; then
        echo 'NetworkManager がありません。次を実行してから再度 setup してください:' >&2
        echo 'sudo apt-get install -y network-manager' >&2
        return 1
    fi
    if [[ $(nmcli -t -g RUNNING general 2>/dev/null) != running ]]; then
        echo 'NetworkManager が起動していません。sudo systemctl start NetworkManager のあとに再実行してください。' >&2
        return 1
    fi
    local dev state
    dev=$(ip -4 route show default 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}')
    if [[ -n $dev ]]; then
        state=$(nmcli -t -g GENERAL.STATE device show "$dev" 2>/dev/null || true)
        if [[ -n $state && $state != 10* ]]; then
            echo "NetworkManager が主NIC($dev)を管理しています($state)。接続を壊す恐れがあるため実行しません。" >&2
            return 1
        fi
    fi
}

_nm_is_lab_profile() {  # name -> must be a dummy profile on the lab interface
    local name=$1 type ifn
    type=$(nmcli -g connection.type connection show "$name" 2>/dev/null) || return 1
    ifn=$(nmcli -g connection.interface-name connection show "$name" 2>/dev/null) || return 1
    [[ $type == *dummy* ]] || return 1
    case "$name:$ifn" in dojo-lab:dojo1|dojo-lab2:dojo2) return 0 ;; *) return 1 ;; esac
}

lab_setup() {
    _nm_ctx || return 1
    _nm_safe || return 1
    local p
    for p in dojo-lab dojo-lab2; do
        if nmcli -g connection.id connection show "$p" >/dev/null 2>&1 && [[ ! -f $LAB_STATE/ready ]]; then
            echo "既存のプロファイル $p があります。実習用ではないため変更しません。" >&2; return 1
        fi
    done
    for p in dojo1 dojo2; do
        if ip link show "$p" >/dev/null 2>&1 && [[ ! -f $LAB_STATE/ready ]]; then
            echo "既存のインターフェース $p があります。変更しません。" >&2; return 1
        fi
    done
    install -d -m 0700 "$LAB_STATE"
    touch "$LAB_STATE/ready"
    cat > "$LAB_STATE/TASKS.txt" <<'EOF2'
対象はダミーデバイス dojo1/dojo2 とプロファイル dojo-lab/dojo-lab2 だけです(主NICには触れません)。
1. sudo dojo-vm-lab nmcli break で、問題のある2つのプロファイルを作ります。
2. 観察: nmcli connection show / nmcli connection show --active / nmcli -f GENERAL,IP4,IP6 device show dojo1 /
   nmcli -g ipv4.addresses,ipv4.routes,ipv4.dns,connection.autoconnect connection show dojo-lab / ip addr / ip route
3. nmcli connection modify で次の状態にします(down/upで反映):
   dojo-lab (dojo1): IPv4 静的 10.77.0.10/24、IPv6 静的 fd77:7700::10/64、
     静的ルート 10.99.0.0/24 を ゲートウェイ 10.77.0.1 経由・メトリック 250、
     DNS は 192.0.2.53 (192.0.2.0/24 の範囲のみ可。検索ドメインの ~dojo.test は消さない)、autoconnect を有効、接続はactive。
   dojo-lab2 (dojo2): dojo-lab と IPv4 アドレスが重複している。10.77.0.0/24 内の別アドレスにして接続はactive。
   デフォルトルートを dojo1/dojo2 に作ってはいけません(主NICの通信を奪います)。
4. sudo dojo-vm-lab nmcli check で ip addr/ip route と nmcli -g の実値を確認します。
EOF2
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _nm_ctx || return 1
    [[ -f $LAB_STATE/ready ]] || { echo 'run setup first' >&2; return 1; }
    _nm_safe || return 1
    local p
    for p in dojo-lab dojo-lab2; do
        if nmcli -g connection.id connection show "$p" >/dev/null 2>&1; then
            _nm_is_lab_profile "$p" || { echo "$p is not a lab profile; refusing" >&2; return 1; }
            nmcli connection delete "$p" >/dev/null
        fi
    done
    # wrong static-route gateway, no DNS, autoconnect off, IPv6 not configured
    nmcli connection add type dummy ifname dojo1 con-name dojo-lab autoconnect no \
        ipv4.method manual ipv4.addresses 10.77.0.10/24 ipv4.routes '10.99.0.0/24 10.77.0.254 250' \
        ipv4.never-default yes ipv4.dns-search '~dojo.test' ipv6.method ignore >/dev/null
    # duplicate IPv4 address
    nmcli connection add type dummy ifname dojo2 con-name dojo-lab2 autoconnect no \
        ipv4.method manual ipv4.addresses 10.77.0.10/24 ipv4.never-default yes ipv6.method ignore >/dev/null
    nmcli connection up dojo-lab >/dev/null || true
    nmcli connection up dojo-lab2 >/dev/null || true
    touch "$LAB_STATE/broken-at"
    echo '問題のあるプロファイル dojo-lab / dojo-lab2 を作成しました。TASKS.txt の目標状態にしてください。'
}

lab_check() {
    _nm_ctx || return 1
    [[ -f $LAB_STATE/broken-at ]] || { echo 'run break and repair first' >&2; return 1; }
    _nm_safe || return 1
    local p
    for p in dojo-lab dojo-lab2; do
        _nm_is_lab_profile "$p" || { echo "FAIL: lab profile $p is missing or changed type/interface" >&2; return 1; }
    done
    local f=0 v
    _nm_fail() { echo "FAIL: $*" >&2; f=1; }
    [[ $(nmcli -g connection.autoconnect connection show dojo-lab) == yes ]] || _nm_fail 'dojo-lab autoconnect must be yes'
    nmcli -g NAME connection show --active | grep -qx dojo-lab || _nm_fail 'dojo-lab is not active'
    nmcli -g NAME connection show --active | grep -qx dojo-lab2 || _nm_fail 'dojo-lab2 is not active'
    [[ $(nmcli -g GENERAL.STATE device show dojo1) == 100* ]] || _nm_fail 'dojo1 is not connected'
    ip -4 -o addr show dev dojo1 | grep -qw '10.77.0.10/24' || _nm_fail 'dojo1 must have 10.77.0.10/24 (ip addr)'
    ip -6 -o addr show dev dojo1 | grep -qw 'fd77:7700::10/64' || _nm_fail 'dojo1 must have fd77:7700::10/64 (ip addr)'
    ip -4 route show 10.99.0.0/24 dev dojo1 | grep -Eq '^10\.99\.0\.0/24 via 10\.77\.0\.1 .*metric 250( |$)' || _nm_fail 'route 10.99.0.0/24 via 10.77.0.1 metric 250 on dojo1 is missing (ip route)'
    local dns
    dns=$(nmcli -g ipv4.dns connection show dojo-lab | tr ',; ' '\n\n\n' | sed '/^$/d')
    grep -qx 192.0.2.53 <<<"$dns" || _nm_fail 'ipv4.dns of dojo-lab must contain 192.0.2.53'
    if grep -vE '^192\.0\.2\.[0-9]+$' <<<"$dns" | grep -q .; then _nm_fail 'DNS servers must stay inside 192.0.2.0/24 in this lab'; fi
    nmcli -g IP4.DNS device show dojo1 | grep -qw 192.0.2.53 || _nm_fail 'device dojo1 does not report DNS 192.0.2.53 (nmcli device show)'
    nmcli -g ipv4.dns-search connection show dojo-lab | grep -qF '~dojo.test' || _nm_fail 'keep ipv4.dns-search ~dojo.test (protects host DNS)'
    # No default route may exist on lab devices
    [[ -z $(ip route show default dev dojo1; ip route show default dev dojo2) ]] || _nm_fail 'default route on a lab device is forbidden'
    # duplicate address removed
    local a1 a2
    a1=$(ip -4 -o addr show dev dojo1 | awk '{print $4}' | sort)
    a2=$(ip -4 -o addr show dev dojo2 | awk '{print $4}' | sort)
    [[ -n $a2 ]] || _nm_fail 'dojo2 has no IPv4 address'
    [[ -z $(comm -12 <(echo "$a1") <(echo "$a2")) ]] || _nm_fail 'dojo1 and dojo2 still share an IPv4 address'
    grep -q '^10\.77\.0\.' <<<"$a2" || _nm_fail 'dojo2 must use an address in 10.77.0.0/24'
    [[ $f == 0 ]] || return 1
    echo 'PASS: profiles, addresses, route/metric, DNS and autoconnect match the live ip/nmcli state'
}

lab_reset() {
    _nm_ctx || return 1
    local p ifn
    if command -v nmcli >/dev/null 2>&1; then
        for p in dojo-lab dojo-lab2; do
            if _nm_is_lab_profile "$p"; then
                nmcli connection delete "$p" >/dev/null 2>&1 || true
            fi
        done
    fi
    for ifn in dojo1 dojo2; do
        if [[ -f $LAB_STATE/ready ]] && ip -d link show "$ifn" 2>/dev/null | grep -qw dummy; then
            ip link del "$ifn" 2>/dev/null || true
        fi
    done
    rm -rf -- "$LAB_STATE"
    echo 'nmcli: removed only lab profiles, dummy devices dojo1/dojo2 and state'
}
