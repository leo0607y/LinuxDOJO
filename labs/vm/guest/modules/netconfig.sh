# title: NIC・固定IP・静的経路・DNSクライアント・IPv6を設定し、再起動後も保つ
# roles: app
# Guest-only. Uses a dedicated dummy interface (dojo0); the main NIC, default route and netplan are never touched.

_nc_paths() {
    [[ ${LAB_ID:-} == netconfig && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/netconfig ]] || { echo 'netconfig: unexpected lab context' >&2; return 1; }
    NC_DIR=/etc/systemd/network
    NC_NETDEV=$NC_DIR/49-dojo0.netdev
    NC_NETWORK=$NC_DIR/50-dojo0.network
    NC_MARK='# LinuxDOJO VM module: netconfig'
    [[ ! -L $NC_NETDEV && ! -L $NC_NETWORK && ! -L $NC_DIR ]] || { echo 'netconfig: unexpected lab context (symlink)' >&2; return 1; }
}

# Main-line fingerprint: default routes and non-dojo0 global addresses. Must not change during the lab.
_nc_snapshot() {
    python3 - <<'PY'
import json, subprocess
def ip(*a):
    return json.loads(subprocess.run(['ip', '-j', *a], capture_output=True, text=True, check=True).stdout or '[]')
out = []
for fam in ('-4', '-6'):
    for r in ip(fam, 'route', 'show', 'default'):
        out.append('route %s %s %s %s' % (fam, r.get('dev'), r.get('gateway'), r.get('metric')))
for link in ip('addr'):
    if link['ifname'] in ('lo', 'dojo0'):
        continue
    for a in link.get('addr_info', []):
        if a['family'] == 'inet6' and (a.get('scope') != 'global' or a.get('temporary')):
            continue
        out.append('addr %s %s/%s' % (link['ifname'], a['local'], a['prefixlen']))
print('\n'.join(sorted(out)))
PY
}

_nc_reload() {
    networkctl reload || return 1
    networkctl reconfigure dojo0 2>/dev/null || true
    udevadm settle 2>/dev/null || true
}

_nc_wait_link() {
    local i
    for i in $(seq 1 20); do ip link show dev dojo0 >/dev/null 2>&1 && return 0; sleep 0.5; done
    return 1
}

_nc_write_tasks() {
    cat > "$LAB_STATE/TASKS.txt" <<EOF
専用の仮想NIC dojo0 に、$NC_NETWORK として設定を書きます（本線のNIC・既定経路・netplanは触りません）。
- dojo0 に固定IPv4 192.0.2.10/24 とIPv6 2001:db8:10::10/64
- 静的経路: 198.51.100.0/24 を 192.0.2.1 経由、2001:db8:20::/64 を 2001:db8:10::1 経由（既定経路は設定しない）
- DNSサーバ 192.0.2.53、検索ドメイン dojo.test
書いたら networkctl reload / reconfigure で適用します。ヒント: networkctl status dojo0、ip -br addr、ip route、resolvectl dns dojo0 / domain
break後は誤った設定が適用されます。ip -j と resolvectl の実際の状態から原因を見つけ、ファイルを直して再適用します。
ファイルに書くだけでなく、適用後の実状態と、再起動後も同じになるファイル内容の両方が判定されます。
EOF
    cat "$LAB_STATE/TASKS.txt"
}

lab_setup() {
    _nc_paths || return 1
    [[ ! -e $LAB_STATE/owns-netdev && ! -e $NC_NETDEV && ! -e $NC_NETWORK ]] || { echo '既存の構成があります。resetするまで上書きしません。'; return 1; }
    ip link show dev dojo0 >/dev/null 2>&1 && { echo 'dojo0 が既に存在します。'; return 1; }
    systemctl is-active --quiet systemd-networkd || { echo 'systemd-networkd が動作していません。'; return 1; }
    systemctl is-active --quiet systemd-resolved || { echo 'systemd-resolved が動作していません。'; return 1; }
    modprobe dummy 2>/dev/null || [[ -d /sys/module/dummy ]] || { echo 'dummyカーネルモジュールを読み込めません。この実習はVMで実行できません。' >&2; return 1; }
    ip -j route show default > "$LAB_STATE/baseline-default-route.json"
    _nc_snapshot > "$LAB_STATE/baseline.txt" || return 1
    [[ -s $LAB_STATE/baseline.txt ]] || { echo '本線の状態を記録できません。' >&2; return 1; }
    cat > "$NC_NETDEV" <<EOF
$NC_MARK
[NetDev]
Name=dojo0
Kind=dummy
EOF
    chmod 644 "$NC_NETDEV"
    touch "$LAB_STATE/owns-netdev"
    _nc_reload && _nc_wait_link || { echo 'dojo0 を作成できません。'; return 1; }
    _nc_write_tasks
}

lab_break() {
    _nc_paths || return 1
    [[ -e $LAB_STATE/owns-netdev && -f $NC_NETDEV ]] && grep -qxF "$NC_MARK" "$NC_NETDEV" || { echo '先にsetupしてください。'; return 1; }
    cat > "$NC_NETWORK" <<EOF
[Match]
Name=dojo0

[Network]
Address=192.0.2.10/16
DNS=192.0.2.99
Domains=dojo.test

[Route]
Destination=198.51.100.0/24
Gateway=192.0.2.254
EOF
    chmod 644 "$NC_NETWORK"
    touch "$LAB_STATE/broken"
    _nc_reload || return 1
    echo '誤った設定(/16、誤ゲートウェイ、DNS誤り、IPv6欠落)を適用しました。直して再適用してください。'
}

# Fixed parser/validator for the learner file and the applied state. Exits non-zero with a reason.
_nc_validate() {
    python3 - "$NC_NETWORK" <<'PY'
import json, subprocess, sys, time, os
def fail(m):
    print('NG: ' + m, file=sys.stderr); sys.exit(1)
path = sys.argv[1]
st = os.lstat(path)
if st.st_uid != 0 or st.st_mode & 0o022:
    fail('設定ファイルの所有者/権限が不正です')
sections = []
for raw in open(path, encoding='utf-8'):
    line = raw.strip()
    if not line or line[0] in '#;':
        continue
    if line.startswith('[') and line.endswith(']'):
        sections.append((line[1:-1], []))
    elif '=' in line and sections:
        k, v = line.split('=', 1)
        sections[-1][1].append((k.strip(), v.strip()))
    else:
        fail('構文エラー: ' + line)
def vals(sec, key):
    return [v for n, kv in sections if n == sec for k, v in kv if k == key]
if {n for n, _ in sections} - {'Match', 'Network', 'Route', 'Address'}:
    fail('想定外のセクションがあります')
if vals('Match', 'Name') != ['dojo0']:
    fail('[Match] Name=dojo0 が必要です')
if vals('Network', 'Gateway') or vals('Network', 'DHCP') not in ([], ['no']):
    fail('既定経路/DHCPは設定しません')
want_addr = {'192.0.2.10/24', '2001:db8:10::10/64'}
if set(vals('Network', 'Address')) | set(vals('Address', 'Address')) != want_addr:
    fail('ファイルのAddressが期待と違います')
routes = {(d, g) for n, kv in sections if n == 'Route'
          for d in [dict(kv).get('Destination')] for g in [dict(kv).get('Gateway')]}
if routes != {('198.51.100.0/24', '192.0.2.1'), ('2001:db8:20::/64', '2001:db8:10::1')}:
    fail('ファイルの[Route]が期待と違います')
if vals('Network', 'DNS') != ['192.0.2.53'] or vals('Network', 'Domains') != ['dojo.test']:
    fail('ファイルのDNS/Domainsが期待と違います')

def run(*a):
    return subprocess.run(a, capture_output=True, text=True)
# applied state; DAD may take a moment
for _ in range(20):
    link = json.loads(run('ip', '-j', 'addr', 'show', 'dev', 'dojo0').stdout or '[]')
    infos = link[0]['addr_info'] if link else []
    if not any('tentative' in a.get('flags', []) for a in infos):
        break
    time.sleep(0.5)
else:
    fail('IPv6アドレスがtentativeのままです')
if not link:
    fail('dojo0がありません')
got = {'%s/%s' % (a['local'], a['prefixlen']) for a in infos if not (a['family'] == 'inet6' and a['local'].startswith('fe80'))}
if got != want_addr:
    fail('適用中のIPが期待と違います: %s' % sorted(got))
def rt(fam):
    return json.loads(run('ip', '-j', fam, 'route', 'show', 'dev', 'dojo0').stdout or '[]')
r4 = {(r['dst'], r.get('gateway')) for r in rt('-4')}
r6 = {(r['dst'], r.get('gateway')) for r in rt('-6')}
if ('198.51.100.0/24', '192.0.2.1') not in r4 or ('192.0.2.0/24', None) not in r4:
    fail('IPv4の適用中経路が期待と違います: %s' % sorted(map(str, r4)))
if ('2001:db8:20::/64', '2001:db8:10::1') not in r6:
    fail('IPv6の適用中経路が期待と違います: %s' % sorted(map(str, r6)))
if any(d == 'default' for d, _ in r4 | r6):
    fail('dojo0に既定経路があります')
for dst, gw in (('198.51.100.7', '192.0.2.1'), ('2001:db8:20::7', '2001:db8:10::1')):
    g = json.loads(run('ip', '-j', 'route', 'get', dst).stdout or '[{}]')[0]
    if g.get('dev') != 'dojo0' or g.get('gateway') != gw:
        fail('%s への経路選択が期待と違います' % dst)
def tail(*a):
    out = run('resolvectl', *a).stdout.strip()
    return set(out.split(':', 1)[1].split()) if ':' in out else set()
if tail('dns', 'dojo0') != {'192.0.2.53'}:
    fail('resolvectl dns dojo0 が期待と違います')
if tail('domain', 'dojo0') != {'dojo.test'}:
    fail('resolvectl domain dojo0 が期待と違います')
status = run('networkctl', 'status', 'dojo0', '--no-pager').stdout
if 'configured' not in status or '/etc/systemd/network/50-dojo0.network' not in status:
    fail('networkctl status dojo0 が configured でない、または50-dojo0.networkを使っていません')
PY
}

lab_check() {
    _nc_paths || return 1
    [[ -e $LAB_STATE/owns-netdev && -f $LAB_STATE/baseline.txt ]] || { echo '先にsetupしてください。'; return 1; }
    [[ -e $LAB_STATE/broken ]] || { echo '先にbreakしてください。'; return 1; }
    grep -qxF "$NC_MARK" "$NC_NETDEV" 2>/dev/null || { echo 'dojo0用.netdevの印がありません。'; return 1; }
    [[ -f $NC_NETWORK && ! -L $NC_NETWORK ]] || { echo "$NC_NETWORK がありません。"; return 1; }
    local now
    now=$(_nc_snapshot) || return 1
    [[ $now == "$(cat "$LAB_STATE/baseline.txt")" ]] || { echo '本線のIP/既定経路がsetup時から変わっています。dojo0以外は触らないでください。' >&2; return 1; }
    _nc_validate || return 1
    echo 'dojo0のIP・経路・DNS・IPv6が適用され、設定ファイルも再起動後に同じ内容になります。本線は不変です。'
}

lab_reset() {
    _nc_paths || return 1
    rm -f "$NC_NETWORK"
    if [[ -f $NC_NETDEV ]] && grep -qxF "$NC_MARK" "$NC_NETDEV"; then
        rm -f "$NC_NETDEV"
        [[ ! -e $LAB_STATE/owns-netdev ]] || ip link del dojo0 2>/dev/null || true
    fi
    systemctl is-active --quiet systemd-networkd && networkctl reload 2>/dev/null || true
    rm -f "$LAB_STATE/owns-netdev" "$LAB_STATE/broken" "$LAB_STATE/baseline.txt" "$LAB_STATE/baseline-default-route.json"
    echo 'dojo0と専用設定ファイルだけを削除しました。'
}
