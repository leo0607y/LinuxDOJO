# title: ブリッジ・VLAN・ボンディング・ポリシールーティング(専用netns内)
# roles: app
# Everything happens inside two lab-owned network namespaces. The VM's real NICs, routes and rules are never touched.
# Namespace-free persistence is only a draft kept under /etc/dojo-netlink-lab (never installed into the real networkd directory).

_nl_paths() {
    [[ ${LAB_ID:-} == netlink && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/netlink ]] || { echo 'netlink: unexpected lab context' >&2; return 1; }
    NS_A=dojo-nl-a
    NS_B=dojo-nl-b
    NL_DRAFT=/etc/dojo-netlink-lab/networkd
    [[ ! -L /etc/dojo-netlink-lab && ! -L $NL_DRAFT ]] || return 1
}

_nl_tools() {
    local t missing=()
    for t in ip bridge ping python3; do command -v "$t" >/dev/null || missing+=("$t"); done
    if ((${#missing[@]})); then
        echo "必要なコマンドがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y iproute2 iputils-ping python3'
        return 1
    fi
}

# Learner-facing shortcuts are `sudo ip netns exec NS ...`; these helpers do the same for judging.
_nl_a() { ip netns exec "$NS_A" "$@"; }
_nl_b() { ip netns exec "$NS_B" "$@"; }

_nl_ping() { # $1=ns-fn $2... ping args
    local fn=$1 i; shift
    for i in 1 2 3; do "$fn" ping -n -c1 -W2 "$@" >/dev/null 2>&1 && return 0; sleep 1; done
    return 1
}

_nl_links() {
    _nl_a ip -d -j link show > "$LAB_STATE/links-a.json" 2>/dev/null || return 1
    _nl_b ip -d -j link show > "$LAB_STATE/links-b.json" 2>/dev/null || return 1
    python3 - "$LAB_STATE/links-a.json" "$LAB_STATE/links-b.json" <<'PY'
import json, sys
a = {l['ifname']: l for l in json.load(open(sys.argv[1]))}
b = {l['ifname']: l for l in json.load(open(sys.argv[2]))}
def need(cond, msg):
    if not cond:
        print(msg); sys.exit(1)
def kind(l): return (l.get('linkinfo') or {}).get('info_kind')
def data(l): return (l.get('linkinfo') or {}).get('info_data') or {}
def up(l): return 'UP' in l.get('flags', [])
for name in ('dojobr0', 'dojobr1'):
    need(name in a and kind(a[name]) == 'bridge' and up(a[name]), 'namespace dojo-nl-a に UP のブリッジ %s が必要です(ip -d link)。' % name)
for name, br in (('dojo-v0', 'dojobr0'), ('dojo-bp0', 'dojobr1'), ('dojo-bp1', 'dojobr1')):
    need(name in a and kind(a[name]) == 'veth' and a[name].get('master') == br and up(a[name]),
         'dojo-nl-a の veth %s を UP にして %s へ接続します。' % (name, br))
v = a.get('dojobr0.20')
need(v and kind(v) == 'vlan' and data(v).get('id') == 20 and data(v).get('protocol') == '802.1Q' and v.get('link') == 'dojobr0' and up(v),
     'dojo-nl-a に dojobr0 上の 802.1Q VLAN id 20 のサブIF dojobr0.20 (UP) が必要です。実際のid/protocol/親を ip -d link で確認します。')
need('dojo-v1' in b and kind(b['dojo-v1']) == 'veth' and up(b['dojo-v1']), 'dojo-nl-b に UP の veth dojo-v1 が必要です(dojo-v0 の対向)。')
v = b.get('dojo-v1.20')
need(v and kind(v) == 'vlan' and data(v).get('id') == 20 and data(v).get('protocol') == '802.1Q' and v.get('link') == 'dojo-v1' and up(v),
     'dojo-nl-b に dojo-v1 上の VLAN id 20 のサブIF dojo-v1.20 (UP) が必要です。')
bond = b.get('dojo-bond0')
need(bond and kind(bond) == 'bond' and up(bond), 'dojo-nl-b に UP のボンド dojo-bond0 が必要です。')
need(data(bond).get('mode') == 'active-backup' and int(data(bond).get('miimon', 0)) > 0, 'ボンドは mode active-backup かつ miimon>0 (リンク監視)にします。')
for name in ('dojo-bl0', 'dojo-bl1'):
    need(name in b and kind(b[name]) == 'veth' and b[name].get('master') == 'dojo-bond0', '%s は dojo-bond0 のスレーブ(veth)にします。' % name)
PY
}

_nl_bridge_ports() {
    _nl_a bridge link show > "$LAB_STATE/bridge-link.txt" 2>&1 || return 1
    grep -Eq 'dojo-v0@.* master dojobr0 .*state forwarding' "$LAB_STATE/bridge-link.txt" \
        && grep -Eq 'dojo-bp0@.* master dojobr1 ' "$LAB_STATE/bridge-link.txt" \
        && grep -Eq 'dojo-bp1@.* master dojobr1 ' "$LAB_STATE/bridge-link.txt" \
        || { echo 'bridge link でdojo-v0がdojobr0、dojo-bp0/1がdojobr1のポートとして forwarding になっていません。'; return 1; }
}

_nl_bond_state() { # prints active slave on stdout
    local f=/proc/net/bonding/dojo-bond0 txt
    txt=$(_nl_b cat "$f" 2>/dev/null) || return 1
    grep -q 'Bonding Mode: fault-tolerance (active-backup)' <<<"$txt" || return 1
    [[ $(grep -c '^Slave Interface:' <<<"$txt") == 2 ]] || return 1
    awk -F': ' '/^Currently Active Slave/ {print $2}' <<<"$txt"
}

_nl_verify() {
    local out active other i ok
    _nl_links || return 1
    _nl_bridge_ports || return 1
    out=$(_nl_bond_state) && [[ $out == dojo-bl0 || $out == dojo-bl1 ]] || { echo '/proc/net/bonding/dojo-bond0 が active-backup・スレーブ2本・アクティブあり になっていません。'; return 1; }
    # IPv4/IPv6 address plan, judged by real traffic across the namespaces
    _nl_ping _nl_a 10.20.0.2 || { echo 'a から 10.20.0.2 (dojo-v1) に届きません。アドレスとリンクを確認します。'; return 1; }
    _nl_ping _nl_b 10.20.0.1 || { echo 'b から 10.20.0.1 (dojobr0) に届きません。'; return 1; }
    _nl_ping _nl_a -6 fd20:0:0:1::2 || { echo 'IPv6 fd20:0:0:1::1/64 <-> ::2/64 の疎通がありません(DADの待ちも考慮)。'; return 1; }
    _nl_ping _nl_a 10.20.20.2 || { echo 'VLAN 20: 10.20.20.1 <-> 10.20.20.2 の疎通がありません。'; return 1; }
    _nl_ping _nl_b 10.20.20.1 || { echo 'VLAN 20: b から 10.20.20.1 に届きません。'; return 1; }
    _nl_ping _nl_a 10.20.30.2 || { echo 'ボンド側 10.20.30.1(dojobr1) <-> 10.20.30.2(dojo-bond0) の疎通がありません。'; return 1; }
    # static route + policy routing
    out=$(_nl_a ip route get 10.99.0.1 2>&1)
    [[ $out == *"via 10.20.0.2 dev dojobr0"* ]] || { echo "10.99.0.1 への通常経路は 10.20.0.2 経由(dojobr0)のはずが: $out"; return 1; }
    out=$(_nl_a ip route get 10.99.0.1 from 10.20.20.1 2>&1)
    [[ $out == *"via 10.20.20.2 dev dojobr0.20"* ]] || { echo "送信元 10.20.20.1 は VLAN 経由(10.20.20.2, dojobr0.20)に ip rule で振り分けるはずが: $out"; return 1; }
    _nl_a ip -4 rule show | grep -Eq 'from 10\.20\.20\.1 .*lookup' || { echo 'ip rule で from 10.20.20.1 を別tableへ向ける規則がありません。'; return 1; }
    _nl_ping _nl_a -I 10.20.0.1 10.99.0.1 || { echo '通常経路での 10.99.0.1 疎通がありません。'; return 1; }
    _nl_ping _nl_a -I 10.20.20.1 10.99.0.1 || { echo 'ポリシー経路(送信元 10.20.20.1)での 10.99.0.1 疎通がありません。'; return 1; }
    # active-backup failover, restored afterwards
    active=$(_nl_bond_state); other=dojo-bl1; [[ $active == dojo-bl1 ]] && other=dojo-bl0
    _nl_b ip link set "$active" down
    ok=0
    for i in 1 2 3 4 5 6 7 8; do
        sleep 0.5
        [[ $(_nl_bond_state 2>/dev/null) == "$other" ]] && { ok=1; break; }
    done
    if ((ok)); then _nl_ping _nl_a 10.20.30.2 && ok=2; fi
    _nl_b ip link set "$active" up
    ((ok == 2)) || { echo "アクティブなスレーブ($active)を落としてもボンドが切り替わって疎通を維持しません(miimon・active-backupを確認)。"; return 1; }
    for i in 1 2 3 4 5 6; do [[ -n $(_nl_bond_state 2>/dev/null) ]] && break; sleep 0.5; done
    _nl_draft_check || return 1
    return 0
}

# Syntax-level check of the networkd draft. These files are never applied to the VM.
_nl_draft_check() {
    python3 - "$NL_DRAFT" <<'PY'
import glob, sys
def parse(path):
    sec, out = None, {}
    for raw in open(path):
        line = raw.strip()
        if not line or line[0] in '#;': continue
        if line.startswith('['): sec = line.strip('[]'); continue
        k, _, v = line.partition('=')
        out.setdefault(sec, {}).setdefault(k.strip(), []).append(v.strip())
    return out
nd, nw = [], []
for p in glob.glob(sys.argv[1] + '/*.netdev'): nd.append(parse(p))
for p in glob.glob(sys.argv[1] + '/*.network'): nw.append(parse(p))
def has_netdev(name, kind, vid=None):
    for d in nd:
        n = d.get('NetDev', {})
        if n.get('Name') == [name] and n.get('Kind') == [kind] and (vid is None or d.get('VLAN', {}).get('Id') == [vid]):
            return True
    return False
def has_network(name, pred):
    return any(d.get('Match', {}).get('Name') == [name] and pred(d) for d in nw)
ok = has_netdev('dojobr0', 'bridge') and has_netdev('dojobr0.20', 'vlan', '20') \
    and has_network('dojobr0', lambda d: 'dojobr0.20' in d.get('Network', {}).get('VLAN', []) and '10.20.0.1/24' in d.get('Network', {}).get('Address', [])) \
    and has_network('dojo-v0', lambda d: d.get('Network', {}).get('Bridge') == ['dojobr0'])
if not ok:
    print('永続化の下書き: %s に dojobr0.netdev(Kind=bridge)・dojobr0.20のVLAN netdev(Id=20)・dojobr0.network(VLAN=dojobr0.20, Address=10.20.0.1/24)・dojo-v0.network(Bridge=dojobr0)が必要です。' % sys.argv[1])
    print('(namespace内のIFはnetworkdでは作れないため、ここは文法の確認だけで、VM本体には適用しません)')
    sys.exit(1)
PY
}

lab_setup() {
    _nl_paths || return 1
    _nl_tools || return 1
    [[ ! -e /etc/dojo-netlink-lab && ! -e /run/netns/$NS_A && ! -e /run/netns/$NS_B ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    install -d -m 0755 /etc/dojo-netlink-lab "$NL_DRAFT"
    touch "$LAB_STATE/owns-ns"
    ip netns add "$NS_A" && ip netns add "$NS_B" || return 1
    _nl_a ip link set lo up
    _nl_b ip link set lo up
    _nl_b ip addr add 10.99.0.1/32 dev lo
    cat > "$LAB_STATE/TASKS.txt" <<TASK
VM本体のNICには触れません。すべて専用namespace内で作ります:  sudo ip netns exec $NS_A <cmd>  /  sudo ip netns exec $NS_B <cmd>
(namespace bの lo には「遠隔ネットワーク」として 10.99.0.1/32 が設定済み)
構成(名前は固定):
  A: ブリッジ dojobr0 と dojobr1。 B: ボンド dojo-bond0。
1. veth: dojo-v0(A) <-> dojo-v1(B)。 dojo-v0 を dojobr0 に接続。 ip link add ... type veth peer name ... netns ...
   アドレス: dojobr0 10.20.0.1/24 と fd20:0:0:1::1/64、 dojo-v1 10.20.0.2/24 と fd20:0:0:1::2/64。ping と ping -6 で疎通。
   bridge link で dojo-v0 がポートになっていることを見る。
2. VLAN(802.1Q id 20): A は dojobr0.20 (親 dojobr0) 10.20.20.1/24、 B は dojo-v1.20 (親 dojo-v1) 10.20.20.2/24。
   ip -d link show で id と protocol を確認。 pingで疎通。
3. ボンド(B): dojo-bond0 を mode active-backup, miimon 100。スレーブ veth は dojo-bl0 と dojo-bl1。
   その対向 dojo-bp0 / dojo-bp1 は A に置いて dojobr1 に接続。 dojobr1 10.20.30.1/24、 dojo-bond0 10.20.30.2/24。
   ※スレーブは down にしてから master 設定。cat /proc/net/bonding/dojo-bond0 で active slave を確認。
   ip netns exec 越しに /proc を読むとnamespaceごとの値が見える。
4. ルーティング(A): 10.99.0.1 へは通常 10.20.0.2 経由(静的経路)。
   ただし送信元 10.20.20.1 の通信だけは VLAN 側 (10.20.20.2 dojobr0.20) の別tableを使う: ip rule add from ... lookup N / ip route add ... table N
   確認: ip route get 10.99.0.1  と  ip route get 10.99.0.1 from 10.20.20.1  と  ping -I <送信元>
5. 永続化の下書き(適用はしません): $NL_DRAFT に systemd.netdev(5)/systemd.network(5) の文法で
   dojobr0.netdev(bridge), dojobr0.20.netdev(vlan, Id=20), dojobr0.network(VLAN=, Address=), dojo-v0.network(Bridge=)
6. 完成したら sudo dojo-vm-lab netlink break → ip -d link / ip rule / ip route get で原因を探して直す → check
   check はアクティブなスレーブを一時的に落として切替も実際に確認します(終了後に元へ戻します)。
7. 終了後 sudo dojo-vm-lab netlink reset (namespaceごと全て削除)
TASK
    echo "手順: $LAB_STATE/TASKS.txt"; cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _nl_paths || return 1
    [[ -f $LAB_STATE/owns-ns && ! -f $LAB_STATE/fault ]] || { echo '初期化済みで未breakの状態で実行します。'; return 1; }
    _nl_verify || { echo 'まず手順1-5を完了し、全項目が通る状態にします。'; return 1; }
    # VLAN id typo (21 instead of 20) on the A side, same address; and the policy rule disappears.
    _nl_a ip link del dojobr0.20 || return 1
    _nl_a ip link add link dojobr0 name dojobr0.20 type vlan id 21
    _nl_a ip link set dojobr0.20 up
    _nl_a ip addr add 10.20.20.1/24 dev dojobr0.20
    while _nl_a ip -4 rule del from 10.20.20.1 2>/dev/null; do :; done
    if _nl_ping _nl_a 10.20.20.2; then echo '障害を再現できませんでした。'; return 1; fi
    touch "$LAB_STATE/fault"
    echo '障害を仕込みました。VLAN経由の通信とポリシー経路が壊れています。ip -d link, ip rule, ip route get で調べます。'
}

lab_check() {
    _nl_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まず構成を作り、breakで障害を作ります。'; return 1; }
    _nl_verify || return 1
    echo 'PASS: ブリッジ・VLAN(802.1Q id 20)・active-backupボンド(切替含む)・IPv4/IPv6・静的/ポリシー経路を実際の ip -d link / bridge link / /proc/net/bonding / ping で確認しました。'
}

lab_reset() {
    _nl_paths || return 1
    [[ -f $LAB_STATE/owns-ns ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    ip netns del "$NS_A" 2>/dev/null || true
    ip netns del "$NS_B" 2>/dev/null || true
    rm -rf -- /etc/dojo-netlink-lab
    rm -f -- "${LAB_STATE:?}/owns-ns" "${LAB_STATE:?}/fault" "${LAB_STATE:?}/TASKS.txt" "${LAB_STATE:?}/links-a.json" "${LAB_STATE:?}/links-b.json" "${LAB_STATE:?}/bridge-link.txt"
    echo '専用namespaceと下書きを削除しました。VM本体のネットワーク設定は変更していません。'
}
