set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}
lab() { dojo-vm-lab firewall "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/firewall
lab reset
nft add table inet dojo_verify_sentinel
sentinel=$(nft list table inet dojo_verify_sentinel)
expect 0 setup lab setup
expect 1 before-break lab check
expect 0 break lab break
expect 1 unconfirmed lab check
touch "$state/confirm"
expect 1 broken lab check
rules=/etc/dojo-firewall/rules.nft
cat > "$rules" <<'NFT'
table inet dojo_fw
delete table inet dojo_fw
table inet dojo_fw {
 chain input {
  type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related accept
  tcp dport {22,18080} accept
  ip protocol icmp accept
 }
}
NFT
"$state/safe-apply" "$rules"
expect 1 confirm-required lab check
touch "$state/confirm"
expect 0 repaired lab check
cp "$rules" "$state/good-rules"
sed -i '/ct state/d' "$rules"
nft -f "$rules"
expect 1 no-established lab check
cp "$state/good-rules" "$rules"
sed -i 's/22,18080/22,18080,18081/' "$rules"
nft -f "$rules"
expect 1 exposed-port lab check
cp "$state/good-rules" "$rules"
nft -f "$rules"
sed -i '/^delete table/d' "$rules"
expect 1 duplicate-on-reload lab check
mv "$state/good-rules" "$rules"
nft -f "$rules"
expect 0 repaired-again lab check
expect 0 reset lab reset
! nft list table inet dojo_fw
test "$(nft list table inet dojo_verify_sentinel)" = "$sentinel"
nft delete table inet dojo_verify_sentinel
! ip netns list | grep -q '^dojo-fw-peer\b'
! ip link show dojo-fwh
test ! -e /etc/dojo-firewall
test ! -e /etc/systemd/system/dojo-fw-web-18080.service
test ! -e /etc/systemd/system/dojo-fw-web-18081.service
test -z "$(find "$state" -mindepth 1 -print -quit)"
echo 'ASSERT cleanup: dedicated nft table/netns/veth/units/state removed; unrelated table preserved'
