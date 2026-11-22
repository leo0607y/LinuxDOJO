# title: 代替ブートローダ: extlinux(ループ画像)・PXE(dnsmasq DHCP/TFTP+pxelinux.cfg)・UEFI/BIOS知識確認
# roles: app
# Never touches the real boot path: extlinux goes into a loop-mounted image file; PXE runs in a namespace pair (dojo-pxe-a/b).
# Packages are NOT in the base image: setup prints the apt line and exits without writing when something is missing.

_ab_paths() {
    [[ ${LAB_ID:-} == altboot && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/altboot ]] || { echo 'altboot: unexpected lab context' >&2; return 1; }
    AB=/srv/dojo-altboot
    AB_IMG=$AB/disk.img
    AB_MNT=$AB/mnt
    AB_CFG=$AB_MNT/boot/syslinux/syslinux.cfg
    AB_PXE=$AB/pxe
    AB_DNS=$AB_PXE/dnsmasq.conf
    AB_TFTP=$AB/tftp
    AB_ANS=$AB/answers.txt
    AB_UNIT=/etc/systemd/system/dojo-pxe.service
    AB_NSA=dojo-pxe-a AB_NSB=dojo-pxe-b AB_IFA=dojo-pxe-a0 AB_IFB=dojo-pxe-b0
    AB_IPA=10.77.0.1 AB_IPB=10.77.0.2
    [[ ! -L $AB && ! -L $AB_UNIT ]] || return 1
}

_ab_tools() {
    local missing=() t
    for t in extlinux dnsmasq ip losetup mkfs.ext4 mount python3; do command -v "$t" >/dev/null || missing+=("$t"); done
    [[ -f /usr/lib/PXELINUX/pxelinux.0 ]] || missing+=(pxelinux.0)
    [[ -f /usr/lib/syslinux/modules/bios/ldlinux.c32 ]] || missing+=(ldlinux.c32)
    if ((${#missing[@]})); then
        echo "必要なものがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y extlinux syslinux-common pxelinux dnsmasq'
        return 1
    fi
}

_ab_write_helpers() {
    cat > "$LAB_STATE/cfgcheck.py" <<'PY'
# usage: cfgcheck.py CFG BASEDIR ROOTDIR [--need FILE]...   (syslinux/extlinux/pxelinux config syntax + referenced files)
import os, sys
cfg, base, root = sys.argv[1:4]
need = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--need']
top = {'default', 'prompt', 'timeout', 'ontimeout', 'ui', 'menu', 'label', 'say', 'display', 'serial', 'font', 'nohalt', 'include', 'path', 'allowoptions', 'noescape', 'totaltimeout', 'implicit', 'console', 'f1', 'f2', 'f3', 'f4'}
inlabel = {'menu', 'kernel', 'linux', 'initrd', 'append', 'localboot', 'com32', 'ipappend', 'config', 'say', 'text', 'endtext', 'help', 'sysappend'}
errs = []
def resolve(p):
    return os.path.join(root, p.lstrip('/')) if p.startswith('/') else os.path.join(base, p)
try:
    lines = open(cfg).read().splitlines()
except OSError as e:
    print('設定を読めません: %s' % e); sys.exit(1)
labels, cur, default, timeout, ui, in_text = {}, None, None, None, None, False
for n, raw in enumerate(lines, 1):
    line = raw.strip()
    if in_text:
        if line.lower() == 'endtext': in_text = False
        continue
    if not line or line.startswith('#'): continue
    key, _, val = line.partition(' ')
    k, val = key.lower(), val.strip()
    if k == 'text': in_text = True; continue
    if k == 'label':
        if not val: errs.append('%d行: LABEL に名前がありません' % n)
        cur = labels.setdefault(val, {}); continue
    if k not in top and k not in inlabel:
        errs.append('%d行: 未知のキーワード %r' % (n, key)); continue
    if k == 'default' and cur is None: default = val
    elif k == 'timeout' and cur is None:
        if not val.isdigit(): errs.append('%d行: TIMEOUT は数字(1/10秒)です: %r' % (n, val))
        timeout = val
    elif k == 'ui' and cur is None: ui = val
    elif cur is not None and k in inlabel:
        cur.setdefault(k, []).append(val)
    elif k in inlabel and k not in ('menu', 'say'):
        errs.append('%d行: %s は LABEL の中に書きます' % (n, key))
if len(labels) < 2: errs.append('LABEL が2つ以上必要です(現在 %d)' % len(labels))
if default is None: errs.append('DEFAULT がありません')
elif default not in labels and default.lower() not in ('menu.c32', 'vesamenu.c32'): errs.append('DEFAULT %r に対応する LABEL がありません' % default)
if timeout is None: errs.append('TIMEOUT がありません')
for name, body in labels.items():
    if not any(x in body for x in ('kernel', 'linux', 'localboot', 'com32', 'config')):
        errs.append('LABEL %s に KERNEL/LINUX/LOCALBOOT がありません' % name); continue
    files = [v.split()[0] for x in ('kernel', 'linux', 'initrd') for v in body.get(x, []) if v and not v.lower().endswith(('.c32', '.0')) and v.split()[0] != '-']
    for v in body.get('append', []):
        files += [t.split('=', 1)[1] for t in v.split() if t.startswith('initrd=')]
    for f in files:
        if not os.path.isfile(resolve(f)): errs.append('LABEL %s が参照する %s がありません' % (name, f))
if ui and 'menu.c32' in ui.lower():
    need += ['menu.c32', 'libutil.c32']
for f in need:
    if not os.path.isfile(resolve(f)): errs.append('必要なファイル %s がありません' % f)
for e in errs: print(e)
sys.exit(1 if errs else 0)
PY
    cat > "$LAB_STATE/probe_pxe.py" <<'PY'
# usage (inside client netns): probe_pxe.py SERVER_IP TFTP_ROOT IFACE
import os, random, socket, struct, sys
server, root, iface = sys.argv[1:4]
def fail(m): print(m); sys.exit(1)
xid = random.getrandbits(32)
mac = bytes([0x02, 0x00, 0x00, 0x77, 0x00, random.randrange(1, 255)])
pkt = struct.pack('!BBBBIHH4s4s4s4s', 1, 1, 6, 0, xid, 0, 0x8000, b'\0' * 4, b'\0' * 4, b'\0' * 4, b'\0' * 4)
pkt += mac + b'\0' * 10 + b'\0' * 64 + b'\0' * 128 + bytes([99, 130, 83, 99])
vc = b'PXEClient:Arch:00000:UNDI:002001'
pkt += bytes([53, 1, 1, 55, 7, 1, 3, 6, 12, 15, 66, 67, 60, len(vc)]) + vc + bytes([93, 2, 0, 0, 255])
pkt += b'\0' * max(0, 300 - len(pkt))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface.encode())
s.bind(('0.0.0.0', 68)); s.settimeout(3)
offer = None
for _ in range(3):
    s.sendto(pkt, ('255.255.255.255', 67))
    try:
        while True:
            d, _a = s.recvfrom(2048)
            if len(d) > 240 and d[0] == 2 and struct.unpack('!I', d[4:8])[0] == xid: offer = d; break
    except socket.timeout:
        pass
    if offer: break
s.close()
if not offer: fail('DHCPDISCOVER に OFFER が返りません(dnsmasqのdhcp-range・interface・サービス状態を確認)。')
yi, si = socket.inet_ntoa(offer[16:20]), socket.inet_ntoa(offer[20:24])
fname = offer[108:236].split(b'\0')[0].decode(errors='replace')
opts, i = {}, 240
while i < len(offer) and offer[i] != 255:
    if offer[i] == 0: i += 1; continue
    opts[offer[i]] = offer[i + 2:i + 2 + offer[i + 1]]; i += 2 + offer[i + 1]
if opts.get(53) != b'\x02': fail('OFFER 以外のDHCPメッセージです。')
if not yi.startswith('10.77.0.') or yi in (server, '10.77.0.2'): fail('払い出しアドレスが想定外です: %s' % yi)
tftp = opts.get(66, b'').decode(errors='replace').strip('\0') or si
boot = opts.get(67, b'').decode(errors='replace').strip('\0') or fname
if tftp != server: fail('次サーバ(option 66 / siaddr)が %s ではありません: %r' % (server, tftp))
if boot != 'pxelinux.0': fail('ブートファイル名(option 67 / file)が pxelinux.0 ではありません: %r' % boot)
print('DHCP OFFER: yiaddr=%s next-server=%s bootfile=%s' % (yi, tftp, boot))
def rrq(name):
    t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); t.settimeout(3)
    t.sendto(b'\0\x01' + name.encode() + b'\0octet\0', (server, 69))
    out, blk = b'', 1
    for _ in range(4000):
        try: d, a = t.recvfrom(1024)
        except socket.timeout: t.close(); return None, 'timeout'
        op, n = struct.unpack('!HH', d[:4])
        if op == 5: t.close(); return None, d[4:-1].decode(errors='replace')
        if op != 3 or n != blk: continue
        out += d[4:]; t.sendto(struct.pack('!HH', 4, n), a); blk += 1
        if len(d) - 4 < 512: t.close(); return out, ''
    t.close(); return None, 'too many blocks'
for name in (boot, 'ldlinux.c32', 'pxelinux.cfg/default'):
    data, err = rrq(name)
    if data is None: fail('TFTP RRQ %s に失敗: %s' % (name, err))
    try: want = open(os.path.join(root, name), 'rb').read()
    except OSError: fail('TFTPルート内に %s がありません。' % name)
    if data != want: fail('TFTPで取得した %s が元ファイルと一致しません。' % name)
    print('TFTP RRQ %s: %d bytes 一致' % (name, len(data)))
PY
}

_ab_restart_pxe() { systemctl restart dojo-pxe.service; sleep 1; systemctl is-active --quiet dojo-pxe.service; }

_ab_mounted() {
    local src
    findmnt -n -M "$AB_MNT" >/dev/null 2>&1 || return 1
    src=$(findmnt -n -o SOURCE -M "$AB_MNT") || return 1
    losetup -j "$AB_IMG" 2>/dev/null | grep -q "^$src:"
}

lab_setup() {
    _ab_paths || return 1
    _ab_tools || return 1
    [[ ! -e $AB && ! -e $AB_UNIT ]] || { echo '専用構成が既にあります。既存データを上書きしません。'; return 1; }
    ip netns list | grep -qE "^($AB_NSA|$AB_NSB)\b" && { echo '専用namespaceが既にあります。'; return 1; }
    ip link show "$AB_IFA" >/dev/null 2>&1 && { echo '専用veth名が使用済みです。'; return 1; }
    install -d -m 0755 "$AB" "$AB_MNT" "$AB_PXE" "$AB_TFTP"
    touch "$LAB_STATE/owns-lab"
    _ab_write_helpers
    # (1) extlinux image: filesystem only; the learner installs extlinux and writes the cfg
    truncate -s 48M "$AB_IMG" && mkfs.ext4 -q -F "$AB_IMG" || return 1
    mount -o loop "$AB_IMG" "$AB_MNT" || return 1
    install -d -m 0755 "$AB_MNT/boot/syslinux"
    head -c 4096 /dev/urandom > "$AB_MNT/boot/vmlinuz-lab"; head -c 4096 /dev/urandom > "$AB_MNT/boot/initrd-lab.img"
    # (2) PXE namespace pair
    ip netns add "$AB_NSA" && ip netns add "$AB_NSB" || return 1
    touch "$LAB_STATE/net-created"
    ip link add "$AB_IFA" type veth peer name "$AB_IFB" || return 1
    ip link set "$AB_IFA" netns "$AB_NSA"; ip link set "$AB_IFB" netns "$AB_NSB"
    ip netns exec "$AB_NSA" ip addr add "$AB_IPA/24" dev "$AB_IFA"
    ip netns exec "$AB_NSB" ip addr add "$AB_IPB/24" dev "$AB_IFB"
    local ns
    for ns in "$AB_NSA:$AB_IFA" "$AB_NSB:$AB_IFB"; do
        ip netns exec "${ns%%:*}" ip link set "${ns##*:}" up; ip netns exec "${ns%%:*}" ip link set lo up
    done
    head -c 4096 /dev/urandom > "$AB_TFTP/vmlinuz-lab"; head -c 4096 /dev/urandom > "$AB_TFTP/initrd-lab.img"
    chmod 0644 "$AB_TFTP"/*
    cat > "$AB_DNS" <<CONF
# --- 隔離設定(変更しない) ---
interface=$AB_IFA
bind-interfaces
port=0
no-resolv
no-hosts
log-dhcp
log-facility=-
# --- ここから学習者が書く: dhcp-range / dhcp-boot / enable-tftp / tftp-root ---
CONF
    dnsmasq --test -C "$AB_DNS" >/dev/null 2>&1 || { echo 'dnsmasq設定のテストに失敗しました。'; return 1; }
    cat > "$AB_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO PXE exercise dnsmasq (namespace $AB_NSA)
After=network.target
[Service]
ExecStart=$(command -v ip) netns exec $AB_NSA $(command -v dnsmasq) -k --pid-file= -C $AB_DNS
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$AB_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-pxe.service
    # (3) knowledge file
    cat > "$AB_ANS" <<'ANS'
# KNOWLEDGE CHECK(キーワード判定。実機のUEFI環境は検証しない)。この行以外の # 行は無視されます。
# 自分の言葉で書く: BIOS(MBR)起動とUEFI起動の違い。
#  - BIOSはどこにある何を最初に実行するか / UEFIはどのパーティションのどのファイルを読むか
#  - そのパーティションの種類とファイルシステム
#  - Secure Boot で shim と GRUB の EFI アプリ(grubx64.efi)がどう連鎖するか
#  - 起動エントリ・起動順序の確認と変更に使うコマンドと、情報が保存される場所
ANS
    chown ubuntu:ubuntu "$AB_ANS" 2>/dev/null || true
    cat > "$LAB_STATE/TASKS.txt" <<TASK
すべて隔離済み: 実ブートには触れない。ルート: $AB  (sudoで作業。answers.txtだけubuntuで編集可)
[A] extlinux (ループ画像 $AB_IMG が $AB_MNT にマウント済み)
  1. sudo dojo-vm-lab altboot break  で壊れた syslinux.cfg と PXE 設定が置かれる(先に読むのは $AB_MNT/boot/syslinux と $AB_PXE)
  2. extlinux --install $AB_MNT/boot/syslinux  でブートローダを画像へ導入(ヒント: ldlinux.sys ができる)
  3. /usr/lib/syslinux/modules/bios/ から ldlinux.c32 と、メニューを使うなら menu.c32 libutil.c32 を同じディレクトリへ
  4. $AB_CFG を直す: DEFAULT/TIMEOUT/LABEL・KERNEL・APPEND initrd=... (カーネルは /boot/vmlinuz-lab, /boot/initrd-lab.img)
[B] PXE ($AB_NSA が DHCP/TFTPサーバ $AB_IPA、$AB_NSB がクライアント)
  5. $AB_DNS を直す(隔離設定の行は変更しない): 10.77.0.50-60 のDHCP範囲、dhcp-boot=pxelinux.0、TFTP有効化、tftp-rootを $AB_TFTP に。
     dnsmasq --test -C $AB_DNS で構文確認、sudo systemctl restart dojo-pxe.service、journalctl -u dojo-pxe.service でDHCPログ
  6. $AB_TFTP に /usr/lib/PXELINUX/pxelinux.0 と ldlinux.c32 を置き、pxelinux.cfg/default を書く(syslinuxと同じ書式、2エントリ以上、
     カーネル/initrdは $AB_TFTP のvmlinuz-lab / initrd-lab.img)
  7. クライアント側からの確認はsudo ip netns exec $AB_NSB ... で行える(判定ではDHCP DISCOVERとTFTP RRQを自動で行う)
[C] 知識確認(キーワード判定): $AB_ANS にUEFIとBIOSの違いを書く
判定: sudo dojo-vm-lab altboot check
終了後: sudo dojo-vm-lab altboot reset
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudoで読む)。次に sudo dojo-vm-lab altboot break"
}

lab_break() {
    _ab_paths || return 1
    [[ -f $LAB_STATE/owns-lab && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで、未breakの状態で実行します。'; return 1; }
    _ab_mounted || { echo 'ループ画像がマウントされていません。'; return 1; }
    cat > "$AB_CFG" <<'CFG'
DEFAULT linux-dojo
TIMEOUT abc
LABEL rescue
  KERNEL
  APPEND single
LABEL normal
  KERNEL /boot/vmlinuz-missing
  APPEND initrd=/boot/initrd-lab.img
CFG
    cat >> "$AB_DNS" <<CONF
dhcp-range=10.77.0.50,10.77.0.60,12h
dhcp-boot=pxelinux.O
tftp-root=$AB/tftpboot
CONF
    _ab_restart_pxe || echo 'dojo-pxe.serviceが起動しません。journalctl -u dojo-pxe.service を確認します。'
    touch "$LAB_STATE/fault"
    echo '壊れた設定を配置しました。TASKS.txt の手順で直してください。'
}

lab_check() {
    _ab_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/owns-lab ]] || { echo 'まず break で開始状態を作ります。'; return 1; }
    [[ $(sha256sum "$AB_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || { echo 'unitは変更しません。'; return 1; }
    # A: extlinux image
    _ab_mounted || { echo "ループ画像 $AB_IMG が $AB_MNT にマウントされていません。"; return 1; }
    [[ -s $AB_MNT/boot/syslinux/ldlinux.sys ]] || { echo 'extlinux --install が未実施です(ldlinux.sys がありません)。'; return 1; }
    python3 "$LAB_STATE/cfgcheck.py" "$AB_CFG" "$AB_MNT/boot/syslinux" "$AB_MNT" --need ldlinux.sys --need ldlinux.c32 || { echo 'syslinux.cfg に問題があります。'; return 1; }
    # B: PXE
    local k
    for k in "interface=$AB_IFA" bind-interfaces port=0; do
        grep -qxF "$k" "$AB_DNS" || { echo "隔離設定 $k を残します。"; return 1; }
    done
    dnsmasq --test -C "$AB_DNS" >/dev/null 2>&1 || { echo 'dnsmasq --test が失敗します。'; return 1; }
    systemctl is-active --quiet dojo-pxe.service || { echo 'dojo-pxe.serviceが動いていません。再起動を忘れていませんか。'; return 1; }
    python3 "$LAB_STATE/cfgcheck.py" "$AB_TFTP/pxelinux.cfg/default" "$AB_TFTP" "$AB_TFTP" --need pxelinux.0 --need ldlinux.c32 || { echo 'pxelinux.cfg/default に問題があります。'; return 1; }
    ip netns exec "$AB_NSB" python3 "$LAB_STATE/probe_pxe.py" "$AB_IPA" "$AB_TFTP" "$AB_IFB" || return 1
    # C: knowledge check
    python3 - "$AB_ANS" <<'PY' || return 1
import re, sys
lines = [l for l in open(sys.argv[1]).read().splitlines() if not l.lstrip().startswith('#')]
t = '\n'.join(lines).lower()
groups = [('ESP', ['esp', 'efi system partition']), ('FAT', ['fat']), ('shim', ['shim']), ('grubx64.efi', ['grubx64.efi']),
          ('efibootmgr', ['efibootmgr']), ('BIOS', ['bios']), ('MBR/boot sector', ['mbr', 'boot sector', 'ブートセクタ']),
          ('Secure Boot', ['secure boot', 'セキュアブート']), ('NVRAM/起動順序', ['nvram', 'boot order', 'bootorder', 'bootnum', '起動順'])]
miss = [n for n, alts in groups if not any(a in t for a in alts)]
if len(re.sub(r'\s+', '', t)) < 200: print('answers.txt の説明が短すぎます(自分の言葉で200字以上)。'); sys.exit(1)
if miss: print('answers.txt に不足する観点: ' + ', '.join(miss)); sys.exit(1)
PY
    echo 'PASS: extlinuxの導入と設定構文、dnsmasqのDHCP(option 66/67)とTFTP RRQ、pxelinux.cfg、知識確認(キーワード判定のみ)を確認しました。'
}

lab_reset() {
    _ab_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    systemctl disable --now dojo-pxe.service 2>/dev/null || true
    rm -f -- "$AB_UNIT"; systemctl daemon-reload
    if [[ -f $LAB_STATE/net-created ]]; then
        ip netns del "$AB_NSA" 2>/dev/null || true
        ip netns del "$AB_NSB" 2>/dev/null || true
    fi
    if _ab_mounted; then umount "$AB_MNT" || return 1; fi
    local dev f
    for dev in $(losetup -j "$AB_IMG" 2>/dev/null | cut -d: -f1); do losetup -d "$dev" 2>/dev/null || true; done
    rm -rf -- "${AB:?}"
    for f in owns-lab net-created fault unit.sha256 cfgcheck.py probe_pxe.py TASKS.txt; do rm -f -- "${LAB_STATE:?}/${f:?}"; done
    echo '専用のloop画像・namespace・dnsmasq・TFTPデータを削除しました。実ブート設定は変更していません。'
}
