#!/bin/bash
# title: 専用BINDで権威ゾーンを書き、named-checkzone・rndc・digで検証してAXFR開放を塞ぐ
# roles: app
# Guest-only. Dedicated named instance on 127.0.0.1:5354 (rndc 127.0.0.1:9531) with its own
# config dir, zone dir, key and user. The system named.conf / port 53 / user bind are never touched.
# Requires: bind9 bind9-utils dnsutils (not in the base image; the learner installs them).

_dns_paths() {
    [[ ${LAB_ID:-} == dnsserver && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/dnsserver ]] || { echo 'dnsserver: unexpected lab context' >&2; return 1; }
    DNS_UNIT=/etc/systemd/system/dojo-dnsserver.service
    DNS_DIR=/etc/bind/dojo
    DNS_ZDIR=/var/lib/bind/dojo
    DNS_CONF=$DNS_DIR/named.conf
    DNS_KEY=$DNS_DIR/rndc.key
    DNS_USER=dojo-named
    DNS_PORT=5354
    DNS_RNDC=9531
    DNS_FWD=$DNS_ZDIR/db.lab.invalid
    DNS_REV=$DNS_ZDIR/db.192.0.2
    local p
    for p in "$DNS_UNIT" "$DNS_DIR" "$DNS_ZDIR" "$DNS_CONF" "$DNS_KEY" "$DNS_FWD" "$DNS_REV"; do
        [[ ! -L $p ]] || { echo 'dnsserver: unexpected lab context' >&2; return 1; }
    done
}

_dns_need_bind() {
    local t missing=0
    for t in named named-checkconf named-checkzone rndc rndc-confgen dig; do
        command -v "$t" >/dev/null 2>&1 || missing=1
    done
    [[ -x /usr/sbin/named ]] || missing=1
    if (( missing )); then
        echo 'bind9 が未導入です。何も書き込まずに終了します。次を実行してから setup をやり直してください。' >&2
        echo '  sudo apt-get install -y bind9 bind9-utils dnsutils' >&2
        return 1
    fi
}

_dns_owned() { [[ -f $DNS_DIR/.linuxdojo-dnsserver ]]; }

_dns_conf() { # allow-transfer value
    cat <<CONF
// LinuxDOJO dedicated named (not the system named.conf)
include "$DNS_KEY";
controls { inet 127.0.0.1 port $DNS_RNDC allow { 127.0.0.1; } keys { "dojo-rndc"; }; };
options {
    directory "$DNS_ZDIR";
    listen-on port $DNS_PORT { 127.0.0.1; };
    listen-on-v6 { none; };
    pid-file none;
    recursion no;
    dnssec-validation no;
    allow-query { 127.0.0.0/8; };
    allow-transfer { $1; };
};
zone "lab.invalid" { type primary; file "$DNS_FWD"; };
zone "2.0.192.in-addr.arpa" { type primary; file "$DNS_REV"; };
CONF
}

_dns_good_fwd() {
    cat <<'ZONE'
$TTL 3600
@   IN SOA ns1.lab.invalid. hostmaster.lab.invalid. (
        2024010101 ; serial
        3600       ; refresh
        900        ; retry
        604800     ; expire
        300 )      ; negative TTL
    IN NS ns1.lab.invalid.
ns1 IN A 192.0.2.53
www IN A 192.0.2.10
ZONE
}

_dns_good_rev() {
    cat <<'ZONE'
$TTL 3600
@   IN SOA ns1.lab.invalid. hostmaster.lab.invalid. (
        2024010101 3600 900 604800 300 )
    IN NS ns1.lab.invalid.
53  IN PTR ns1.lab.invalid.
ZONE
}

_dns_broken_fwd() {
    cat <<'ZONE'
$TTL 3600
@   IN SOA ns1.lab.invalid. hostmaster.lab.invalid. (
        2024010101 ; serial (stale)
        3600 900 604800 300 )
    IN NS ns1.lab.invalid.
    IN CNAME www
    IN MX 10 mail.lab.invalid
    IN TXT "v=spf1 -all"
ns1 IN A 192.0.2.53
www IN A 192.0.2.10
www IN AAAA 2001:db8::10
mail IN A 192.0.2.25
ftp IN CNAME www.lab.invalid.
ZONE
}

_dns_broken_rev() {
    cat <<'ZONE'
$TTL 3600
@   IN SOA ns1.lab.invalid. hostmaster.lab.invalid. (
        2024010101 3600 900 604800 300 )
    IN NS ns1.lab.invalid.
53  IN PTR ns1.lab.invalid.
10  IN PTR www.lab.invalid
ZONE
}

_dns_rndc() { rndc -s 127.0.0.1 -p "$DNS_RNDC" -k "$DNS_KEY" "$@"; }
_dns_dig() { dig +norecurse +time=2 +tries=1 "$@"; }
_dns_q() { _dns_dig +short @127.0.0.1 -p "$DNS_PORT" "$@"; }
_dns_serial() { # file-serial via named-checkzone
    named-checkzone "$1" "$2" 2>/dev/null | sed -n 's/.*loaded serial \([0-9]*\).*/\1/p'
}

lab_setup() {
    _dns_paths || return 1
    _dns_need_bind || return 1
    if [[ -e $DNS_DIR ]] && ! _dns_owned; then echo "別用途のディレクトリは変更しません: $DNS_DIR" >&2; return 1; fi
    if [[ -e $DNS_UNIT ]] && ! grep -qx '# LinuxDOJO VM module: dnsserver' "$DNS_UNIT"; then
        echo "別用途のunitは変更しません: $DNS_UNIT" >&2; return 1
    fi
    if [[ ! -e $DNS_UNIT ]] && ss -ltnu 2>/dev/null | grep -qE "[:.]($DNS_PORT|$DNS_RNDC)\b"; then
        echo "ポート $DNS_PORT/$DNS_RNDC は別プロセスが使用中です。" >&2; return 1
    fi
    id "$DNS_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin \
        --comment 'LinuxDOJO dnsserver' "$DNS_USER"
    install -d -m 750 -o root -g "$DNS_USER" "$DNS_DIR"
    install -d -m 755 "$DNS_ZDIR"
    : > "$DNS_DIR/.linuxdojo-dnsserver"
    if [[ ! -f $DNS_KEY ]]; then
        rndc-confgen -a -A hmac-sha256 -k dojo-rndc -c "$DNS_KEY" >/dev/null 2>&1 || return 1
    fi
    chown root:"$DNS_USER" "$DNS_KEY"; chmod 640 "$DNS_KEY"
    _dns_conf 127.0.0.1 > "$DNS_CONF"
    _dns_good_fwd > "$DNS_FWD"; _dns_good_rev > "$DNS_REV"
    chmod 644 "$DNS_CONF" "$DNS_FWD" "$DNS_REV"; chown root:"$DNS_USER" "$DNS_CONF"; chmod 640 "$DNS_CONF"
    named-checkconf -z "$DNS_CONF" || { echo '初期設定の検査に失敗しました。' >&2; return 1; }
    cat > "$DNS_UNIT" <<EOF
# LinuxDOJO VM module: dnsserver
[Unit]
Description=LinuxDOJO dedicated BIND (127.0.0.1:$DNS_PORT)
After=network.target
[Service]
ExecStart=/usr/sbin/named -f -c $DNS_CONF -u $DNS_USER
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now dojo-dnsserver.service
    systemctl restart dojo-dnsserver.service
    rm -f "$LAB_STATE/broken-serial"
    cat > "$LAB_STATE/TASKS.txt" <<EOF
専用named: 127.0.0.1:$DNS_PORT / rndc 127.0.0.1:$DNS_RNDC (systemのnamed・port53とは別)
設定: $DNS_CONF  ゾーン: $DNS_FWD (lab.invalid), $DNS_REV (2.0.192.in-addr.arpa)
rndcの鍵: $DNS_KEY  (rndc -s 127.0.0.1 -p $DNS_RNDC -k 鍵 status)
1. 今は最小のゾーンが動いています。dig @127.0.0.1 -p $DNS_PORT www.lab.invalid +short で確認します。
2. break 後、ゾーンに追加すべき内容: AAAA(www)、MX(mail)、TXT(SPF)、CNAME(ftp->www)、PTR(10.2.0.192)。
3. 反映前に named-checkconf と named-checkzone で検査し、エラーを読んで直します。
4. SOAのシリアルを必ず増やしてから rndc reload します(壊れた版と同じ値は不合格)。
5. dig +norecurse、+short、-t SOA で実際の応答を確認します。
6. 転送(AXFR)は許可IPだけ。dig AXFR lab.invalid @127.0.0.1 -p $DNS_PORT と、-b 127.0.0.2 での拒否を比べます。
EOF
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _dns_paths || return 1
    _dns_owned || { echo 'dnsserver: setup を先に実行してください。' >&2; return 1; }
    _dns_conf any > "$DNS_CONF"
    _dns_broken_fwd > "$DNS_FWD"
    _dns_broken_rev > "$DNS_REV"
    chown root:"$DNS_USER" "$DNS_CONF"; chmod 640 "$DNS_CONF"; chmod 644 "$DNS_FWD" "$DNS_REV"
    printf '2024010101\n' > "$LAB_STATE/broken-serial"
    echo '壊れた設定とゾーンを配置しました(まだreloadしていません)。'
    echo 'named-checkconf / named-checkzone で原因を見つけ、直してから rndc reload します。'
}

lab_check() {
    _dns_paths || return 1
    _dns_owned || { echo 'dnsserver: setup が必要です。' >&2; return 1; }
    [[ -f $LAB_STATE/broken-serial ]] || { echo 'dnsserver: break を先に実行してください。' >&2; return 1; }
    _dns_need_bind || return 1
    local bs fs rs live out ttl
    bs=$(cat "$LAB_STATE/broken-serial")
    [[ $bs =~ ^[0-9]+$ ]] || return 1
    named-checkconf -z "$DNS_CONF" >/dev/null 2>&1 || { echo 'named-checkconfが失敗します。'; return 1; }
    fs=$(_dns_serial lab.invalid "$DNS_FWD"); rs=$(_dns_serial 2.0.192.in-addr.arpa "$DNS_REV")
    [[ -n $fs && -n $rs ]] || { echo 'named-checkzoneが失敗します(ゾーン内容を確認)。'; return 1; }
    named-checkzone -k fail lab.invalid "$DNS_FWD" >/dev/null 2>&1 || { echo '正引きゾーンに検査エラーがあります。'; return 1; }
    (( fs > bs && rs > bs )) || { echo "シリアルが壊れた版($bs)より増えていません。"; return 1; }
    systemctl is-active --quiet dojo-dnsserver.service || { echo '専用namedが動いていません。'; return 1; }
    _dns_rndc status >/dev/null 2>&1 || { echo 'rndcで専用namedに接続できません。'; return 1; }
    live=$(_dns_q lab.invalid SOA | awk '{print $3}')
    [[ $live == "$fs" ]] || { echo "稼働中のシリアル($live)がファイル($fs)と違います。rndc reloadが必要です。"; return 1; }
    out=$(_dns_dig @127.0.0.1 -p "$DNS_PORT" lab.invalid SOA)
    grep -Eq 'flags:.* aa[ ;]' <<<"$out" || { echo '権威応答(aa)ではありません。'; return 1; }
    [[ $(_dns_q lab.invalid CNAME) == '' ]] || { echo 'apexにCNAMEが残っています。'; return 1; }
    [[ $(_dns_q www.lab.invalid A) == 192.0.2.10 ]] || { echo 'www Aが違います。'; return 1; }
    [[ $(_dns_q www.lab.invalid AAAA) == 2001:db8::10 ]] || { echo 'www AAAAが違います。'; return 1; }
    [[ $(_dns_q ftp.lab.invalid CNAME) == www.lab.invalid. ]] || { echo 'ftp CNAMEが違います。'; return 1; }
    [[ $(_dns_q lab.invalid MX) == '10 mail.lab.invalid.' ]] || { echo 'MXが違います(末尾のドットを確認)。'; return 1; }
    [[ $(_dns_q mail.lab.invalid A) == 192.0.2.25 ]] || { echo 'mail Aが違います。'; return 1; }
    _dns_q lab.invalid TXT | grep -q 'v=spf1' || { echo 'TXT(SPF)がありません。'; return 1; }
    [[ $(_dns_q -x 192.0.2.10) == www.lab.invalid. ]] || { echo 'PTRが違います(末尾のドットを確認)。'; return 1; }
    ttl=$(_dns_dig +noall +answer @127.0.0.1 -p "$DNS_PORT" www.lab.invalid A | awk 'NR==1{print $2}')
    [[ $ttl =~ ^[0-9]+$ ]] && (( ttl >= 60 && ttl <= 86400 )) || { echo 'TTLが想定範囲(60-86400)外です。'; return 1; }
    # AXFR: allowed source works, any other source is refused.
    out=$(dig +time=3 +tries=1 AXFR lab.invalid @127.0.0.1 -p "$DNS_PORT" 2>&1) || true
    grep -q 'www.lab.invalid.' <<<"$out" || { echo '許可IPからのAXFRが成功しません。'; return 1; }
    out=$(dig +time=3 +tries=1 -b 127.0.0.2 AXFR lab.invalid @127.0.0.1 -p "$DNS_PORT" 2>&1) || true
    if grep -q 'www.lab.invalid.' <<<"$out"; then echo 'AXFRが許可IP以外にも開いています(allow-transfer)。'; return 1; fi
    echo 'ゾーン検査・rndc reload・dig応答・シリアル増加・AXFR制限を確認できました。'
}

lab_reset() {
    _dns_paths || return 1
    if [[ -e $DNS_UNIT ]] && grep -qx '# LinuxDOJO VM module: dnsserver' "$DNS_UNIT"; then
        systemctl disable --now dojo-dnsserver.service 2>/dev/null || true
        rm -f "$DNS_UNIT"
        systemctl daemon-reload
    fi
    if _dns_owned; then
        rm -rf -- "$DNS_DIR" "$DNS_ZDIR"
        if [[ $(getent passwd "$DNS_USER" | cut -d: -f5) == 'LinuxDOJO dnsserver' ]]; then
            userdel "$DNS_USER" 2>/dev/null || true
        fi
    fi
    rm -f "$LAB_STATE/broken-serial"
    echo '専用named・設定・ゾーン・専用ユーザーだけを削除しました(bind9パッケージとsystem namedは未変更)。'
}
