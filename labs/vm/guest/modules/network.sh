#!/bin/bash
# title: 2台でDNSとHTTPを検証し、名前解決の誤りを切り分ける
# roles: app client
net_context() {
    [[ ${LAB_ID:-} == network && ${LAB_ROOT:-} == /var/lib/linuxdojo-vm-lab && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/network ]] || {
        echo 'network は専用dispatcherのVM実習です。' >&2; return 1;
    }
    case ${LAB_VM_ROLE:-} in app|client) ;; *) return 1 ;; esac
    local unit
    for unit in /etc/systemd/system/dojo-network-dns.service /etc/systemd/system/dojo-network-http.service; do
        [[ ! -L $unit ]] || return 1
        if [[ -e $unit ]]; then
            grep -qx '# LinuxDOJO VM module: network' "$unit" || { echo "別用途のunitは変更しません: $unit" >&2; return 1; }
        fi
    done
}
net_ip() {
    hostname -I | awk '{print $1}'
}
net_valid_ip() {
    python3 - "$1" <<'PY'
import ipaddress,sys
try:
    ip=ipaddress.IPv4Address(sys.argv[1])
    valid=any(ip in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
except ValueError:
    valid=False
raise SystemExit(0 if valid else 1)
PY
}
net_dns_config() {
    local ip=$1 answer=$2
    cat > "$LAB_STATE/dnsmasq.conf" <<EOF
# linuxdojo-owned
port=15353
bind-interfaces
listen-address=127.0.0.1,$ip
no-resolv
no-hosts
local=/dojo.test/
address=/app.dojo.test/$answer
log-queries
log-facility=-
EOF
    chmod 644 "$LAB_STATE/dnsmasq.conf"
}
lab_setup() {
    net_context || return
    if [[ $LAB_VM_ROLE == client ]]; then
        [[ -f $LAB_STATE/app-ip ]] || printf 'APP_PRIVATE_IP\n' > "$LAB_STATE/app-ip"
        cat > "$LAB_STATE/TASK.txt" <<EOF
app側でsetupとbreakを実行します。Multipassのinfoで確認したappのプライベートIPを、$LAB_STATE/app-ip に1行で保存します。
checkで、app側DNS(15353)への問い合わせと、その回答先HTTP(18080)を検証します。
IP直指定のHTTPが成功して名前の回答だけが誤る状況を比較し、app側のDNSを直します。
必要ならtcpdump -ni any 'port 15353 or port 18080' で、この教材の通信だけを観察します。
アプリ側のwebstack実習も併せる場合は、公開証明書をclientへコピーし、curl --cacertでTLSと名前も検証します。
EOF
        cat "$LAB_STATE/TASK.txt"
        return
    fi
    local ip
    ip=$(net_ip)
    net_valid_ip "$ip" || { echo 'RFC1918プライベートIPv4を確認できません。' >&2; return 1; }
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" "$LAB_STATE"
    install -d -m 755 "$LAB_STATE/www"
    printf 'linuxdojo-two-vm-network\n' > "$LAB_STATE/www/health"
    chmod 644 "$LAB_STATE/www/health"
    printf '%s\n' "$ip" > "$LAB_STATE/approved-ip"
    net_dns_config "$ip" "$ip"
    cat > /etc/systemd/system/dojo-network-dns.service <<EOF
# LinuxDOJO VM module: network
[Unit]
Description=LinuxDOJO dedicated nonrecursive DNS
After=network-online.target
Wants=network-online.target
[Service]
User=dnsmasq
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --pid-file --user=dnsmasq --conf-file=$LAB_STATE/dnsmasq.conf
Restart=on-failure
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/dojo-network-http.service <<EOF
# LinuxDOJO VM module: network
[Unit]
Description=LinuxDOJO dedicated network HTTP
After=network-online.target
Wants=network-online.target
[Service]
User=www-data
ExecStart=/usr/bin/python3 -m http.server 18080 --bind $ip --directory $LAB_STATE/www
Restart=on-failure
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now dojo-network-dns.service dojo-network-http.service
    systemctl restart dojo-network-dns.service dojo-network-http.service
    echo "app IP: $ip。clientからDNS15353とHTTP18080を確認します。"
    echo "break後は $LAB_STATE/dnsmasq.conf の回答だけを修正し、専用DNSサービスをrestartします。"
}
lab_break() {
    net_context || return
    [[ $LAB_VM_ROLE == app ]] || { echo '故障投入はapp VMで行います。' >&2; return 1; }
    local ip
    ip=$(cat "$LAB_STATE/approved-ip")
    net_valid_ip "$ip" || return 1
    net_dns_config "$ip" 192.0.2.99
    systemctl restart dojo-network-dns.service
    echo 'DNSの回答だけを文書用IPへ変更しました。HTTPは稼働したままです。'
}
lab_check() {
    net_context || return
    local ip answer
    if [[ $LAB_VM_ROLE == client ]]; then
        ip=$(cat "$LAB_STATE/app-ip")
    else
        ip=$(cat "$LAB_STATE/approved-ip")
        [[ $ip == "$(net_ip)" ]] || { echo 'IPが変わっています。承認値と現在値を確認します。' >&2; return 1; }
    fi
    net_valid_ip "$ip" || { echo 'appのRFC1918 IPv4を設定してください。' >&2; return 1; }
    # クライアントはユーザーが明示した訓練VMの私有IPだけへ要求する。
    dig +time=2 +tries=1 +short @"$ip" -p 15353 app.dojo.test A > "$LAB_STATE/dns-evidence.txt" || return 1
    answer=$(cat "$LAB_STATE/dns-evidence.txt")
    [[ $answer == "$ip" ]] || { echo 'DNS回答と承認されたapp IPが一致しません。' >&2; return 1; }
    curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS "http://$answer:18080/health" > "$LAB_STATE/http-evidence.txt" || return 1
    [[ $(cat "$LAB_STATE/http-evidence.txt") == linuxdojo-two-vm-network ]] || return 1
    if [[ $LAB_VM_ROLE == app ]]; then
        systemctl is-enabled --quiet dojo-network-dns.service dojo-network-http.service || return 1
    fi
    echo 'DNS回答と、回答先のHTTPを確認できました。clientでも実行して2台間の通信を確認します。'
}
lab_reset() {
    net_context || return
    if [[ $LAB_VM_ROLE == app ]]; then
        systemctl disable --now dojo-network-dns.service dojo-network-http.service 2>/dev/null || true
        rm -f /etc/systemd/system/dojo-network-dns.service /etc/systemd/system/dojo-network-http.service
        systemctl daemon-reload
    fi
    echo '専用サービスを解除しました。取得した証拠はLAB_STATEに保全します。'
}
