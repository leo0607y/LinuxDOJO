# title: WireGuard VPN（名前空間2つ・鍵生成・AllowedIPs・握手と実通信の検証）
# roles: app
# Guest-only. Two private network namespaces joined by a veth; the host's real interfaces and routes are never touched.

_wg_paths() {
    [[ ${LAB_ID:-} == wireguard && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/wireguard ]] || { echo 'wireguard: unexpected lab context' >&2; return 1; }
    WG_PRIV=/etc/dojo-wireguard   # 0700: keys and wg-quick configs (private keys live here only)
    WG_PUB=/srv/dojo-wg           # 0755: world-readable; public keys and notes only
    NS_A=dojo-wg-a
    NS_B=dojo-wg-b
    [[ ! -L $WG_PRIV && ! -L $WG_PUB ]] || return 1
}

_wg_in() { local ns=$1; shift; ip netns exec "$ns" "$@"; }

_wg_cleanup_ns() {
    ip netns del "$NS_A" 2>/dev/null || true
    ip netns del "$NS_B" 2>/dev/null || true
}

lab_setup() {
    _wg_paths || return 1
    local c missing=0
    for c in wg wg-quick ip python3; do command -v "$c" >/dev/null || missing=1; done
    if (( missing )); then
        echo 'WireGuardのツールが入っていません。次を実行してから、もう一度setupしてください:'
        echo '  sudo apt-get install -y wireguard-tools'
        return 1
    fi
    [[ ! -e $WG_PRIV && ! -e $WG_PUB && ! -e $LAB_STATE/owns-lab ]] || { echo '専用構成が既にあります。上書きしません。'; return 1; }
    if ip netns list 2>/dev/null | grep -Eq "^($NS_A|$NS_B)( |$)"; then echo '専用の名前空間名が使用済みです。'; return 1; fi
    ip netns add "$NS_A" && ip netns add "$NS_B" || { _wg_cleanup_ns; return 1; }
    touch "$LAB_STATE/owns-lab"
    # WireGuard link type must be creatable (kernel module); probe inside the private namespace only.
    modprobe wireguard 2>/dev/null || true
    if ! _wg_in "$NS_A" sh -c 'ip link add dojo-probe type wireguard && ip link del dojo-probe'; then
        echo 'カーネルがWireGuardを作れません (modprobe wireguard を確認)。'
        _wg_cleanup_ns; rm -f -- "$LAB_STATE/owns-lab"; return 1
    fi
    ip link add dojo-wga type veth peer name dojo-wgb || { _wg_cleanup_ns; rm -f -- "$LAB_STATE/owns-lab"; return 1; }
    ip link set dojo-wga netns "$NS_A"
    ip link set dojo-wgb netns "$NS_B"
    _wg_in "$NS_A" ip addr add 10.77.0.1/30 dev dojo-wga
    _wg_in "$NS_B" ip addr add 10.77.0.2/30 dev dojo-wgb
    _wg_in "$NS_A" ip link set dojo-wga up
    _wg_in "$NS_B" ip link set dojo-wgb up
    _wg_in "$NS_A" ip link set lo up
    _wg_in "$NS_B" ip link set lo up
    _wg_in "$NS_B" ip addr add 10.79.0.1/24 dev lo   # "office LAN" that only B knows
    _wg_in "$NS_A" ping -c1 -W2 10.77.0.2 >/dev/null || { echo '下回り(veth)の疎通を確認できません。'; _wg_cleanup_ns; rm -f -- "$LAB_STATE/owns-lab"; return 1; }
    install -d -m 0700 "$WG_PRIV"
    install -d -m 0755 "$WG_PUB"
    cat > "$LAB_STATE/TASKS.txt" <<'TASK'
WireGuard実習（root/sudoで操作。ホスト本体のインターフェースや経路は触りません）
構成: 名前空間 dojo-wg-a と dojo-wg-b が veth で接続済み。
  下回り: a=10.77.0.1/30  b=10.77.0.2/30
  トンネル(これから作る): a=10.78.0.1/24  b=10.78.0.2/24
  b側だけが持つ「社内LAN」: 10.79.0.1/24 (b の lo)。a からこの網へだけ届くようにする。
作業場所: 鍵と設定は /etc/dojo-wireguard (0700)。公開鍵メモだけ /srv/dojo-wg (誰でも読める)。
 1. 鍵を作る(umask 077): wg genkey | tee a.key | wg pubkey > a.pub と b も同様、wg genpsk > psk
    秘密鍵とpskは /etc/dojo-wireguard に0600で。*.pub だけを /srv/dojo-wg にコピー。
    ※ 2台で同じ鍵を使い回さない。自分の公開鍵を相手のPeerに書かない。
 2. wg-quick形式の設定を /etc/dojo-wireguard/wg-a.conf と wg-b.conf に書く(権限0600)。
    [Interface] Address / ListenPort / PrivateKey
      a: 10.78.0.1/24, ListenPort 51821    b: 10.78.0.2/24, ListenPort 51820
    [Peer] PublicKey(相手のもの) / PresharedKey / AllowedIPs / PersistentKeepalive(25前後)
      a側のPeerにEndpoint = 10.77.0.2:51820
    AllowedIPsは「そのPeerへ送る/から受けるアドレス範囲」。a側は 相手のトンネルIPと社内LAN(10.79.0.0/24)
    だけ。0.0.0.0/0 は全通信をトンネルに流す(フルトンネル)ので、今回は不可(スプリットトンネル)。
    DNS = は wg-quick が resolvconf を呼ぶため、この実習では行頭に # を付けたメモにとどめる。
 3. 各名前空間で起動: ip netns exec dojo-wg-a wg-quick up /etc/dojo-wireguard/wg-a.conf (bも同様)
 4. 確認: ip netns exec dojo-wg-a wg show  (latest handshake と transfer が増えるか)
    ip netns exec dojo-wg-a ping -c3 10.78.0.2   と   ping -c3 10.79.0.1
 5. sudo dojo-vm-lab wireguard break  (a側のPeer公開鍵が違う鍵に、AllowedIPsが0.0.0.0/0に)
    wg show が握手しない理由と、ip route の変化を調べ、設定を直して wg-quick down/up で再起動。
 6. sudo dojo-vm-lab wireguard check   (実際の握手<180秒・トンネル越しの通信・鍵権限・鍵の使い回しなしを確認)
 7. 終了後 sudo dojo-vm-lab wireguard reset
TASK
    cat <<'MSG'
準備できました。手順は /var/lib/linuxdojo-vm-lab/state/wireguard/TASKS.txt (sudo cat で表示)。
名前空間 dojo-wg-a / dojo-wg-b と veth を作りました。鍵と設定は /etc/dojo-wireguard に作ります。
MSG
    cat "$LAB_STATE/TASKS.txt"
}

# Real end-to-end probe used by break/check; sets nothing global, returns 0 only on real traffic.
_wg_ping_all() {
    _wg_in "$NS_A" ping -c3 -W2 10.78.0.2 >/dev/null 2>&1 && _wg_in "$NS_A" ping -c3 -W2 10.79.0.1 >/dev/null 2>&1
}

lab_break() {
    _wg_paths || return 1
    [[ -f $LAB_STATE/owns-lab && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで、未breakのときだけ実行できます。'; return 1; }
    [[ -f $WG_PRIV/wg-a.conf && -f $WG_PRIV/wg-b.conf ]] || { echo 'まず wg-a.conf / wg-b.conf を作って起動します。'; return 1; }
    _wg_in "$NS_A" wg show wg-a >/dev/null 2>&1 && _wg_in "$NS_B" wg show wg-b >/dev/null 2>&1 || { echo 'まず両方の名前空間でwg-quick upします。'; return 1; }
    _wg_ping_all || { echo 'まずトンネル越しのpingを成功させます。'; return 1; }
    install -m 0600 "$WG_PRIV/wg-a.conf" "$LAB_STATE/good-a.conf"
    local decoy
    decoy=$(wg genkey | wg pubkey) || return 1
    python3 - "$WG_PRIV/wg-a.conf" "$decoy" <<'PY' || { echo 'wg-a.confのPeer節を書き換えられません。'; return 1; }
import os, re, sys
path, decoy = sys.argv[1:3]
section, out, hit = None, [], {'key': 0, 'allowed': 0}
for line in open(path).read().splitlines():
    m = re.match(r'\s*\[(\w+)\]', line)
    if m:
        section = m.group(1).lower()
    elif section == 'peer' and re.match(r'\s*PublicKey\s*=', line):
        line, hit['key'] = 'PublicKey = ' + decoy, hit['key'] + 1
    elif section == 'peer' and re.match(r'\s*AllowedIPs\s*=', line):
        line, hit['allowed'] = 'AllowedIPs = 0.0.0.0/0', hit['allowed'] + 1
    out.append(line)
if not (hit['key'] and hit['allowed']):
    sys.exit(1)
tmp = path + '.tmp'
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('\n'.join(out) + '\n')
os.replace(tmp, path)
PY
    _wg_in "$NS_A" wg-quick down "$WG_PRIV/wg-a.conf" >/dev/null 2>&1 || true
    _wg_in "$NS_A" wg-quick up "$WG_PRIV/wg-a.conf" >/dev/null 2>&1 || { echo 'a側の再起動に失敗しました。'; return 1; }
    if _wg_ping_all; then echo '障害を確認できません。'; install -m 0600 "$LAB_STATE/good-a.conf" "$WG_PRIV/wg-a.conf"; return 1; fi
    touch "$LAB_STATE/fault"
    echo 'a側のトンネルが壊れました。wg show と ip route (a側) を調べて wg-a.conf を直し、wg-quick down/up で反映します。'
}

lab_check() {
    _wg_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで障害を作り、直してから実行します。'; return 1; }
    local f
    for f in a.key b.key psk wg-a.conf wg-b.conf; do
        [[ -f $WG_PRIV/$f && ! -L $WG_PRIV/$f && $(stat -c '%a %U' "$WG_PRIV/$f") == '600 root' ]] || { echo "$WG_PRIV/$f が無いか、root所有の0600ではありません。"; return 1; }
    done
    [[ $(stat -c %a "$WG_PRIV") == 700 ]] || { echo "$WG_PRIV は0700にします。"; return 1; }
    [[ -z $(find "$WG_PRIV" -mindepth 1 -perm /077) ]] || { echo '秘密情報のファイルがグループ/他人から読めます。'; return 1; }
    local pa pb
    pa=$(wg pubkey < "$WG_PRIV/a.key") && pb=$(wg pubkey < "$WG_PRIV/b.key") || { echo '秘密鍵が不正です。'; return 1; }
    [[ $pa != "$pb" ]] || { echo 'aとbに同じ鍵を使えません。'; return 1; }
    # Config content: reused/swapped keys are rejected here; live state is judged below.
    python3 - "$WG_PRIV" "$pa" "$pb" <<'PY' || return 1
import sys
from pathlib import Path
priv, pa, pb = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def parse(p):
    iface, peer, sec = {}, {}, None
    for raw in p.read_text().splitlines():
        s = raw.split('#', 1)[0].strip()
        if not s: continue
        if s.startswith('['): sec = s.strip('[]').lower(); continue
        k, _, v = s.partition('=')
        (iface if sec == 'interface' else peer)[k.strip().lower()] = v.strip()
    return iface, peer
ka, kb, psk = [(priv / n).read_text().strip() for n in ('a.key', 'b.key', 'psk')]
def bad(msg): print(msg); sys.exit(1)
ia, pra = parse(priv / 'wg-a.conf'); ib, prb = parse(priv / 'wg-b.conf')
if ia.get('privatekey') != ka or ib.get('privatekey') != kb: bad('設定のPrivateKeyが各鍵ファイルと一致しません(鍵の使い回し・取り違え)。')
if pra.get('publickey') != pb or prb.get('publickey') != pa: bad('Peerの公開鍵は「相手の」公開鍵にします。')
if psk in (ka, kb) or pra.get('presharedkey') != psk or prb.get('presharedkey') != psk: bad('PresharedKeyは両側で同じ専用のpskにします(秘密鍵と共用しない)。')
if ia.get('listenport') != '51821' or ib.get('listenport') != '51820': bad('ListenPortは a=51821, b=51820 です。')
if pra.get('endpoint') != '10.77.0.2:51820': bad('a側のEndpointは 10.77.0.2:51820 です。')
PY
    # Secrets must never be readable from the world-readable directory.
    local secret
    for secret in "$(cat "$WG_PRIV/a.key")" "$(cat "$WG_PRIV/b.key")" "$(cat "$WG_PRIV/psk")"; do
        if grep -rqF -- "$secret" "$WG_PUB"; then echo "$WG_PUB に秘密鍵/事前共有鍵が含まれています。公開鍵(*.pub)だけを置きます。"; return 1; fi
    done
    [[ -z $(find "$WG_PUB" -perm /002) ]] || { echo '公開ディレクトリが誰でも書き込める状態です。'; return 1; }
    # Live state in the namespaces.
    [[ $(_wg_in "$NS_A" wg show wg-a public-key 2>/dev/null) == "$pa" && $(_wg_in "$NS_B" wg show wg-b public-key 2>/dev/null) == "$pb" ]] || { echo '両側でwg-a/wg-bを起動し直します(wg-quick down/up)。'; return 1; }
    _wg_in "$NS_A" ip -d link show wg-a | grep -q wireguard || return 1
    [[ $(_wg_in "$NS_A" wg show wg-a peers) == "$pb" && $(_wg_in "$NS_B" wg show wg-b peers) == "$pa" ]] || { echo '実際に動作中のPeer公開鍵が違います。'; return 1; }
    [[ $(_wg_in "$NS_A" wg show wg-a listen-port) == 51821 && $(_wg_in "$NS_B" wg show wg-b listen-port) == 51820 ]] || return 1
    [[ $(_wg_in "$NS_A" wg show wg-a preshared-keys | cut -f2) == "$(cat "$WG_PRIV/psk")" ]] || { echo '動作中のpskが一致しません。'; return 1; }
    local ka kb
    ka=$(_wg_in "$NS_A" wg show wg-a persistent-keepalive | cut -f2)
    [[ $ka =~ ^[0-9]+$ ]] && (( ka >= 1 && ka <= 60 )) || { echo 'a側のPersistentKeepaliveを1-60秒で設定します。'; return 1; }
    python3 - "$(_wg_in "$NS_A" wg show wg-a allowed-ips | cut -f2)" "$(_wg_in "$NS_B" wg show wg-b allowed-ips | cut -f2)" <<'PY' || return 1
import ipaddress as ip, sys
def nets(s): return [ip.ip_network(x) for x in s.split()]
def covered(addr, ns): return any(ip.ip_address(addr) in n for n in ns)
def bad(msg): print(msg); sys.exit(1)
a, b = nets(sys.argv[1]), nets(sys.argv[2])
if any(n.prefixlen == 0 for n in a + b): bad('AllowedIPsに/0があります。必要な範囲だけに絞ります(スプリットトンネル)。')
allowed_a = [ip.ip_network('10.78.0.0/24'), ip.ip_network('10.79.0.0/24')]
if not all(any(n.subnet_of(w) for w in allowed_a) for n in a): bad('a側のAllowedIPsに不要な範囲があります。')
if not (covered('10.78.0.2', a) and all(covered(h, a) for h in ('10.79.0.1', '10.79.0.254'))): bad('a側のAllowedIPsに相手のトンネルIPと10.79.0.0/24が必要です。')
if not all(n.subnet_of(ip.ip_network('10.78.0.0/24')) for n in b) or not covered('10.78.0.1', b): bad('b側のAllowedIPsは a のトンネルIPだけにします。')
PY
    local rx0 tx0 rx1 tx1
    read -r rx0 tx0 < <(_wg_in "$NS_A" wg show wg-a transfer | cut -f2,3)
    _wg_ping_all || { echo 'トンネル越しの ping (10.78.0.2 と 10.79.0.1) が通りません。'; return 1; }
    read -r rx1 tx1 < <(_wg_in "$NS_A" wg show wg-a transfer | cut -f2,3)
    (( rx1 > rx0 && tx1 > tx0 )) || { echo 'wgのtransferカウンタが増えていません(トンネルを通っていません)。'; return 1; }
    local ns ifc t now
    now=$(date +%s)
    for ns in "$NS_A:wg-a" "$NS_B:wg-b"; do
        ifc=${ns#*:}; ns=${ns%%:*}
        t=$(_wg_in "$ns" wg show "$ifc" latest-handshakes | cut -f2)
        [[ $t =~ ^[0-9]+$ ]] && (( t > 0 && now - t < 180 && t - now < 5 )) || { echo "$ifc の握手が無い、または180秒より古いです。"; return 1; }
        if _wg_in "$ns" ip -4 route get 1.1.1.1 2>/dev/null | grep -q "dev $ifc"; then echo "$ns の既定の外向き通信がトンネルを通っています(フルトンネル)。"; return 1; fi
    done
    [[ $(_wg_in "$NS_A" wg show wg-a endpoints | cut -f2) == 10.77.0.2:51820 ]] || return 1
    echo 'PASS: 実際の握手・トンネル越しの通信・スプリットトンネル・鍵権限と鍵の分離を確認しました。'
}

lab_reset() {
    _wg_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    [[ -f $WG_PRIV/wg-a.conf ]] && _wg_in "$NS_A" wg-quick down "$WG_PRIV/wg-a.conf" >/dev/null 2>&1 || true
    [[ -f $WG_PRIV/wg-b.conf ]] && _wg_in "$NS_B" wg-quick down "$WG_PRIV/wg-b.conf" >/dev/null 2>&1 || true
    _wg_cleanup_ns
    ip link del dojo-wga 2>/dev/null || true
    rm -rf -- "$WG_PRIV" "$WG_PUB"
    rm -f -- "$LAB_STATE/owns-lab" "$LAB_STATE/fault" "$LAB_STATE/good-a.conf" "$LAB_STATE/TASKS.txt"
    echo '専用の名前空間・鍵・設定を削除しました。ホストのネットワーク設定は変更していません。'
}
