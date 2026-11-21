"""Stage 22: 仮想化・NAT・Kubernetes・IaC・監視。サンドボックス内の偽データと採取済みの出力だけを使う。"""
import hashlib
import json
import re
import secrets
import shlex
import xml.etree.ElementTree as ET

from engine.runner import register

S = 22
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの仮想マシン・ネットワーク・クラスタ・クラウドは操作せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないツールは採取済みの出力と設定ファイルで扱います。")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text, readonly=True):
    ctx.write(name, text)
    if readonly:
        ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(sha(ctx.need_file(name)) == h, name + ' は原本です。変更しないでください。')


def rj(ctx, name):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def cmd_lines(ctx, name, count=None):
    """コマンドファイルを行ごとにトークン化する。"""
    out = []
    for ln in ctx.need_file(name).splitlines():
        if not ln.strip() or ln.strip().startswith('#'):
            continue
        try:
            t = shlex.split(ln)
        except ValueError:
            ctx.fail(name + ' の引用符が閉じていません。')
        if t and t[0] == 'sudo':
            t = t[1:]
        out.append(t)
    if count is not None:
        ctx.require(len(out) == count, f'{name} には{count}行のコマンドを書きます。')
    return out


def find_line(lines, pred):
    for i, t in enumerate(lines):
        if pred(t):
            return i
    return -1


def rx(ctx, text, pattern, msg, flags=re.M):
    ctx.require(re.search(pattern, text, flags), msg)


# ------------------------------------------------------------ 簡易YAMLパーサ（PyYAML非依存）
def _opens(s, i):
    return i == 0 or s[i - 1] in ' [{,:'


def _strip_comment(s):
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in '"\'' and _opens(s, i):
            q = ch
        elif ch == '#' and (i == 0 or s[i - 1] in ' \t'):
            return s[:i].rstrip()
    return s.rstrip()


def _split_kv(s):
    q = None
    depth = 0
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in '"\'' and _opens(s, i):
            q = ch
        elif ch in '[{':
            depth += 1
        elif ch in ']}':
            depth -= 1
        elif ch == ':' and depth == 0 and (i + 1 == len(s) or s[i + 1] == ' '):
            k = s[:i].strip()
            if len(k) >= 2 and k[0] == k[-1] and k[0] in '"\'':
                k = k[1:-1]
            return k, s[i + 1:].strip()
    return None


def _flow_split(s):
    parts, cur, q, depth = [], '', None, 0
    for i, ch in enumerate(s):
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in '"\'' and _opens(s, i):
            q = ch
            cur += ch
        elif ch in '[{':
            depth += 1
            cur += ch
        elif ch in ']}':
            depth -= 1
            cur += ch
        elif ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _scalar(s):
    s = s.strip()
    if s == '' or s in ('~', 'null'):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
        return s[1:-1]
    if s.startswith('['):
        if not s.endswith(']'):
            raise ValueError(s)
        return [_scalar(x) for x in _flow_split(s[1:-1])]
    if s.startswith('{'):
        if not s.endswith('}'):
            raise ValueError(s)
        d = {}
        for part in _flow_split(s[1:-1]):
            kv = _split_kv(part.strip())
            if not kv:
                raise ValueError(part)
            d[kv[0]] = _scalar(kv[1])
        return d
    if s.lower() == 'true':
        return True
    if s.lower() == 'false':
        return False
    if re.fullmatch(r'-?\d+', s):
        return int(s)
    if re.fullmatch(r'-?\d+\.\d+', s):
        return float(s)
    return s


def _block(L, i, ind):
    t = L[i][1]
    if t.startswith('- ') or t == '-':
        return _seq(L, i, ind)
    return _map(L, i, ind)


def _seq(L, i, ind):
    out = []
    while i < len(L) and L[i][0] == ind and (L[i][1].startswith('- ') or L[i][1] == '-'):
        rest = _strip_comment(L[i][1][1:].lstrip())
        off = len(L[i][1]) - len(L[i][1][1:].lstrip())
        if rest == '':
            i += 1
            if i < len(L) and L[i][0] > ind:
                v, i = _block(L, i, L[i][0])
                out.append(v)
            else:
                out.append(None)
        elif not rest.startswith(('[', '{', '"', "'")) and _split_kv(rest):
            L[i] = (ind + off, L[i][1][off:], None)
            v, i = _map(L, i, ind + off)
            out.append(v)
        else:
            out.append(_scalar(rest))
            i += 1
    return out, i


def _map(L, i, ind):
    out = {}
    while i < len(L) and L[i][0] == ind:
        t = _strip_comment(L[i][1])
        kv = _split_kv(t)
        if not kv:
            raise ValueError(t)
        k, v = kv
        i += 1
        if v in ('|', '>', '|-', '>-', '|+', '>+'):
            buf = []
            base = None
            while i < len(L) and L[i][0] > ind:
                if base is None:
                    base = L[i][0]
                buf.append(' ' * (L[i][0] - base) + L[i][1])
                i += 1
            val = ('\n' if v[0] == '|' else ' ').join(buf)
        elif v == '':
            if i < len(L) and L[i][0] > ind:
                val, i = _block(L, i, L[i][0])
            elif i < len(L) and L[i][0] == ind and L[i][1].startswith('- '):
                val, i = _seq(L, i, ind)
            else:
                val = None
        else:
            val = _scalar(v)
        out[k] = val
    return out, i


def parse_yaml(text):
    L = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        if raw.startswith('\t') or re.match(r' *\t', raw):
            raise ValueError('tab')
        stripped = raw.lstrip(' ')
        L.append((len(raw) - len(stripped), stripped.rstrip(), None))
    if not L:
        return None
    v, i = _block(L, 0, L[0][0])
    if i != len(L):
        raise ValueError('indent')
    return v


def yload(ctx, name, multi=False):
    text = ctx.need_file(name)
    try:
        docs = [parse_yaml(d) for d in re.split(r'(?m)^---\s*$', text) if d.strip()]
    except (ValueError, IndexError):
        ctx.fail(name + ' のYAMLを読み取れません。インデントはスペースで揃え、「キー: 値」の形を確認してください。')
    if multi:
        return docs
    ctx.require(len(docs) == 1 and docs[0] is not None, name + ' には1つのYAML文書を書きます。')
    return docs[0]


def g(d, *path):
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and -len(d) <= p < len(d):
            d = d[p]
        else:
            return None
    return d


def xml_load(ctx, name):
    try:
        return ET.fromstring(ctx.need_file(name))
    except ET.ParseError:
        ctx.fail(name + ' はXMLとして不正です。タグの閉じ忘れを確認してください。')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'22-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='本番に触れる前に定義ファイルと採取済みの出力で結果を予測し、差分と影響範囲を確認してから適用しましょう。')


def hx(n=2):
    return secrets.token_hex(n)


# ================================================================ 1 virsh domain XML
def s1(ctx):
    base, new = 'web' + hx(), 'clone-' + hx()
    mem, cpu = 1024 * (3 + secrets.randbelow(6)), 3 + secrets.randbelow(4)
    ctx.data.update(base=base, new=new, mem=mem, cpu=cpu, memkib=mem * 1024)
    u = '-'.join(hx(n) for n in (4, 2, 2, 2, 6))
    put(ctx, 'dom.xml', f"""<domain type='kvm'>
  <name>{base}</name>
  <uuid>{u}</uuid>
  <memory unit='KiB'>2097152</memory>
  <currentMemory unit='KiB'>2097152</currentMemory>
  <vcpu placement='static'>2</vcpu>
  <os>
    <type arch='x86_64' machine='pc-q35-8.2'>hvm</type>
    <boot dev='hd'/>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/{base}.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <mac address='52:54:00:{hx(1)}:{hx(1)}:{hx(1)}'/>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
  </devices>
</domain>
""")
    ctx.write('requirements.txt', f"dom.xml（virsh dumpxml 相当のdomain XML）を複製して新しいVMを作る。new.xml に: name={new}、メモリ{mem}MiB（memoryとcurrentMemory）、vCPU {cpu}、ディスクのsourceを /var/lib/libvirt/images/{new}.qcow2 に変更し、重複するuuidとMACアドレスの要素は削除する（libvirtが再生成する）。cmds.txt に virsh define → virsh start → virsh list --all の順で3行書く（実行はしない）。\n")


def kib(el):
    v = int(el.text.strip())
    return v * {'KiB': 1, 'MiB': 1024, 'GiB': 1024 * 1024}.get(el.get('unit', 'KiB'), 1)


def c1(ctx):
    need_ro(ctx)
    d, r = ctx.data, xml_load(ctx, 'new.xml')
    ctx.require((r.findtext('name') or '').strip() == d['new'], 'nameを新しいVM名にします。')
    ctx.require(r.find('uuid') is None, '複製元と同じuuidは削除します。')
    for tag in ('memory', 'currentMemory'):
        e = r.find(tag)
        ctx.require(e is not None and kib(e) == d['memkib'], f'{tag}を{d["mem"]}MiBにします（KiB換算で{d["memkib"]}）。')
    ctx.require((r.findtext('vcpu') or '').strip() == str(d['cpu']), f'vcpuを{d["cpu"]}にします。')
    src = r.find("./devices/disk/source")
    ctx.require(src is not None and src.get('file') == f'/var/lib/libvirt/images/{d["new"]}.qcow2', 'ディスクのsourceを新しいqcow2にします。')
    ctx.require(r.find("./devices/interface/mac") is None, '複製元と同じMACアドレスは削除します。')
    ls = cmd_lines(ctx, 'cmds.txt', 3)
    ctx.require(ls[0][:3] == ['virsh', 'define', 'new.xml'], '1行目は virsh define new.xml です。')
    ctx.require(ls[1][:3] == ['virsh', 'start', d['new']], '2行目は virsh start VM名 です。')
    ctx.require(ls[2][:2] == ['virsh', 'list'] and '--all' in ls[2], '3行目は virsh list --all で定義済みの全VMを確認します。')


mission(1, 'virsh define/start/listでdomain XMLからVMを複製する',
        'KVM/libvirtのVMはdomain XMLで定義されます。dom.xmlは既存VMのdomain XMLです。これを元に別名のVMを作るnew.xmlを作り、virsh define・virsh start・virsh list の手順をcmds.txtに書いてください。uuidとMACが重複するとlibvirtが拒否します。',
        ['new.xmlを要件どおりに作る', 'cmds.txtにvirshの3手順を書く'], s1, c1,
        """sed -e 's#<<base>>#<<new>>#g' -e '/<uuid>/d' -e '/<mac /d' -e 's#>2097152</#><<memkib>></#' -e 's#>2</vcpu>#><<cpu>></vcpu>#' dom.xml > new.xml
printf '%s\\n' 'virsh define new.xml' 'virsh start <<new>>' 'virsh list --all' > cmds.txt""",
        ["sed -e 's#<<base>>#<<new>>#g' dom.xml > new.xml\nprintf '%s\\n' 'virsh define new.xml' 'virsh start <<new>>' 'virsh list --all' > cmds.txt",
         "cp dom.xml new.xml\nprintf '%s\\n' 'virsh define new.xml' 'virsh start <<base>>' 'virsh list' > cmds.txt"],
        'domain XMLはVMのCPU・メモリ・ディスク・NICを宣言します。memoryのunitに注意し、KiB単位なら1MiB=1024KiBです。virsh define XML で永続定義を登録し（この時点では停止中）、virsh start 名前 で起動、virsh list は実行中だけ、--all を付けると停止中も表示します。複製ではname・uuid・MAC・ディスクの実体を必ず分けます。virsh dumpxml 名前 > file.xml で現在の定義を取り出せます。',
        '複製元と衝突する要素を洗い出します。', 'sedでname置換と衝突要素の削除、メモリ・vcpu書き換えを行います。')


# ================================================================ 2 storage pool & network
def s2(ctx):
    pool, net = 'pool' + hx(), 'lab' + hx()
    sub, br = 100 + secrets.randbelow(100), 10 + secrets.randbelow(80)
    ctx.data.update(pool=pool, net=net, sub=sub, br=br)
    ctx.write('requirements.txt', f"libvirtのストレージプールとネットワークをXMLで定義する。pool.xml: type='dir'、name={pool}、target path=/var/lib/libvirt/images/{pool}。net.xml: name={net}、forward mode='nat'、bridge name='virbr{br}'、ip 192.168.{sub}.1 / netmask 255.255.255.0、dhcp range 192.168.{sub}.100〜192.168.{sub}.200。cmds.txt に pool-define/pool-start/net-define/net-start/net-autostart（virsh）を書く（実行はしない）。\n")


def c2(ctx):
    d = ctx.data
    p = xml_load(ctx, 'pool.xml')
    ctx.require(p.tag == 'pool' and p.get('type') == 'dir', "pool.xmlは <pool type='dir'> です。")
    ctx.require((p.findtext('name') or '').strip() == d['pool'], 'プール名を指定どおりにします。')
    ctx.require((p.findtext('./target/path') or '').strip() == f'/var/lib/libvirt/images/{d["pool"]}', 'target/pathを指定のディレクトリにします。')
    n = xml_load(ctx, 'net.xml')
    ctx.require(n.tag == 'network' and (n.findtext('name') or '').strip() == d['net'], 'net.xmlのnameを指定どおりにします。')
    ctx.require(n.find('forward') is not None and n.find('forward').get('mode') == 'nat', "<forward mode='nat'/> でNAT型にします。")
    ctx.require(n.find('bridge') is not None and n.find('bridge').get('name') == f'virbr{d["br"]}', 'bridgeのnameを指定どおりにします。')
    ip = n.find('ip')
    ctx.require(ip is not None and ip.get('address') == f'192.168.{d["sub"]}.1' and ip.get('netmask') == '255.255.255.0', 'ipのaddressとnetmaskを指定します。')
    r = n.find('./ip/dhcp/range')
    ctx.require(r is not None and r.get('start') == f'192.168.{d["sub"]}.100' and r.get('end') == f'192.168.{d["sub"]}.200', 'dhcpのrange start/endを指定します。')
    ls = cmd_lines(ctx, 'cmds.txt')
    idx = {}
    for key in (('pool-define', 'pool.xml'), ('pool-start', d['pool']), ('net-define', 'net.xml'), ('net-start', d['net']), ('net-autostart', d['net'])):
        i = find_line(ls, lambda t, key=key: t[:1] == ['virsh'] and t[1:3] == list(key))
        ctx.require(i >= 0, f'virsh {key[0]} {key[1]} の行が必要です。')
        idx[key[0]] = i
    ctx.require(idx['pool-define'] < idx['pool-start'] and idx['net-define'] < idx['net-start'], 'define → start の順に並べます。')


mission(2, 'ストレージプールとネットワーク定義をvirshで登録する',
        'libvirtではVMのディスク置き場をストレージプール、VM用の仮想LANを仮想ネットワークとして別々に定義します。仕様どおりのpool.xmlとnet.xml（NAT型でDHCP付き）を書き、virshのpool-define・net-define等の手順をcmds.txtに並べてください。',
        ['pool.xmlとnet.xmlを作る', 'cmds.txtにvirshの登録手順を書く'], s2, c2,
        """cat > pool.xml <<'EOF'
<pool type='dir'>
  <name><<pool>></name>
  <target>
    <path>/var/lib/libvirt/images/<<pool>></path>
  </target>
</pool>
EOF
cat > net.xml <<'EOF'
<network>
  <name><<net>></name>
  <forward mode='nat'/>
  <bridge name='virbr<<br>>'/>
  <ip address='192.168.<<sub>>.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.<<sub>>.100' end='192.168.<<sub>>.200'/>
    </dhcp>
  </ip>
</network>
EOF
printf '%s\\n' 'virsh pool-define pool.xml' 'virsh pool-start <<pool>>' 'virsh net-define net.xml' 'virsh net-start <<net>>' 'virsh net-autostart <<net>>' > cmds.txt""",
        ["printf '%s\\n' \"<pool type='dir'><name><<pool>></name></pool>\" > pool.xml\nprintf '%s\\n' \"<network><name><<net>></name></network>\" > net.xml\nprintf '%s\\n' 'virsh pool-define pool.xml' 'virsh net-define net.xml' > cmds.txt"],
        'ストレージプールはdirやlvmなど種類があり、virsh pool-define pool.xml → virsh pool-start 名前 で使えるようになります。ネットワーク定義も virsh net-define → net-start で、net-autostart はホスト起動時の自動起動です。forward mode=nat は外向きだけNATされる設定で、dhcp rangeはゲストへ配るアドレス範囲です。確認は virsh pool-list --all と virsh net-list --all です。',
        '二つのXMLは別物です。', 'catとヒアドキュメントでXMLを書き、手順をprintfで並べます。')


# ================================================================ 3 qemu-img
def s3(ctx):
    v = 10 + secrets.randbelow(30)
    n = 2 + secrets.randbelow(3)
    pool = ['clean-install', 'before-upgrade', 'db-ready', 'patch-0101', 'golden']
    tags = [t + '-' + hx(1) for t in pool[:n]]
    grow, new = 5 + secrets.randbelow(15), 'pre-' + hx()
    ctx.data.update(virt=v, tagjson=json.dumps(tags), grow=grow, new=new)
    rows = ''.join(f'{i + 1:<10}{t:<22}{(i + 1) * 120:>5} MiB 2026-0{i + 1}-10 09:00:00 00:00:00.000          0\n' for i, t in enumerate(tags))
    put(ctx, 'info.txt', f"$ qemu-img info guest.qcow2\nimage: guest.qcow2\nfile format: qcow2\nvirtual size: {v} GiB ({v * 2 ** 30} bytes)\ndisk size: 3.2 GiB\ncluster_size: 65536\nbacking file: base-os.qcow2\nbacking file format: qcow2\nSnapshot list:\nID        TAG                     VM SIZE                DATE     VM CLOCK     ICOUNT\n{rows}")
    ctx.write('requirements.txt', f"info.txtはqemu-img infoの出力。answer.jsonに format・virtual_gib（整数）・backing_file・snapshots（TAGの配列、表の順）を書く。cmds.txtに3行（実行はしない）: (1)スナップショット {new} を guest.qcow2 に作る (2)guest.qcow2 を{grow}GiB拡張（縮小ではない相対指定） (3)guest.qcow2 を裏打ち(backing)にqcow2形式の差分イメージ overlay.qcow2 を作る（-F で裏打ちの形式も明示）。\n")


def c3(ctx):
    need_ro(ctx)
    d, a = ctx.data, rj(ctx, 'answer.json')
    want = {'format': 'qcow2', 'virtual_gib': d['virt'], 'backing_file': 'base-os.qcow2', 'snapshots': json.loads(d['tagjson'])}
    for k, v in want.items():
        ctx.require(a.get(k) == v, f'answer.jsonの{k}がinfo.txtと一致しません。')
    ls = cmd_lines(ctx, 'cmds.txt', 3)
    ctx.require(ls[0][:5] == ['qemu-img', 'snapshot', '-c', d['new'], 'guest.qcow2'], '1行目は qemu-img snapshot -c タグ guest.qcow2 です。')
    ctx.require(ls[1][:3] == ['qemu-img', 'resize', 'guest.qcow2'] and len(ls[1]) == 4 and re.fullmatch(r'\+%d(G|GiB)' % d['grow'], ls[1][3]) and '--shrink' not in ls[1], '2行目は qemu-img resize guest.qcow2 +NG です。')
    t = ls[2]
    ctx.require(t[:2] == ['qemu-img', 'create'] and '-f' in t and t[t.index('-f') + 1] == 'qcow2', '3行目は qemu-img create -f qcow2 ... です。')
    ctx.require('-b' in t and t[t.index('-b') + 1] == 'guest.qcow2' and '-F' in t and t[t.index('-F') + 1] == 'qcow2' and t[-1] == 'overlay.qcow2', '-b guest.qcow2 -F qcow2 で裏打ちを指定し、最後に overlay.qcow2 を置きます。')


mission(3, 'qemu-imgでqcow2のスナップショット・resize・差分を扱う',
        'KVMのディスクイメージにはqcow2形式が使われ、qemu-imgで調べ、スナップショットを取り、resizeで容量を増やし、裏打ちファイルを使った差分イメージも作れます。info.txtのqemu-img info出力を読んでanswer.jsonにまとめ、実行予定のコマンドをcmds.txtに書いてください。',
        ['answer.jsonに情報を書く', 'cmds.txtにスナップショット・resize・差分作成を書く'], s3, c3,
        """printf '{"format":"qcow2","virtual_gib":<<virt>>,"backing_file":"base-os.qcow2","snapshots":<<tagjson>>}\\n' > answer.json
printf '%s\\n' 'qemu-img snapshot -c <<new>> guest.qcow2' 'qemu-img resize guest.qcow2 +<<grow>>G' 'qemu-img create -f qcow2 -b guest.qcow2 -F qcow2 overlay.qcow2' > cmds.txt""",
        ["printf '%s\\n' 'qemu-img snapshot -c <<new>> guest.qcow2' 'qemu-img resize guest.qcow2 <<grow>>G' 'qemu-img create -f qcow2 -b guest.qcow2 overlay.qcow2' > cmds.txt",
         "printf '{\"format\":\"raw\",\"virtual_gib\":0,\"backing_file\":\"\",\"snapshots\":[]}\\n' > answer.json"],
        'qcow2は必要な分だけ領域を使うシンプロビジョニング形式で、virtual size（ゲストから見える容量）とdisk size（実使用量）が違います。qemu-img snapshot -c で内部スナップショット作成、-l で一覧、-a で復元、-d で削除。qemu-img resize は +NG で拡張でき、縮小は --shrink が必要でデータ破壊の危険があるため避けます。拡張後はゲスト内でパーティションとファイルシステムも拡げます。作業前に qemu-img check と、VM停止の確認を行います。',
        'virtual sizeと実使用量は別物です。', 'qemu-img snapshot -c、resize +NG、create -f qcow2 -b -F を使います。')


# ================================================================ 4 cloud-init
def s4(ctx):
    host, user = 'node-' + hx(), secrets.choice(['ops', 'deploy', 'admin']) + hx(1)
    pkg = secrets.choice(['nginx', 'chrony', 'fail2ban', 'rsyslog'])
    key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI' + secrets.token_urlsafe(30).replace('-', 'x').replace('_', 'y') + ' ' + user + '@lab'
    iid = 'iid-' + hx(3)
    ctx.data.update(host=host, user=user, pkg=pkg, key=key, iid=iid)
    ctx.write('requirements.txt', f"cloud-initでVMを初期化する。user-data（先頭は #cloud-config）に: hostname={host}、ユーザー{user}（sudo: ALL=(ALL) NOPASSWD:ALL、ssh_authorized_keys に pubkey.txt の鍵、パスワード直書き禁止）、ssh_pwauth を false、packages に {pkg}、runcmd で systemctl enable --now {pkg}。meta-data に instance-id: {iid} と local-hostname: {host}。seed.txt に seed ISOを作る1行（cloud-localds seed.iso user-data meta-data）を書く（実行しない）。\n")
    put(ctx, 'pubkey.txt', key + '\n')


def c4(ctx):
    need_ro(ctx)
    d = ctx.data
    raw = ctx.need_file('user-data')
    ctx.require(raw.splitlines()[0].strip() == '#cloud-config', 'user-dataの1行目は #cloud-config です。')
    u = yload(ctx, 'user-data')
    ctx.require(isinstance(u, dict) and u.get('hostname') == d['host'], 'hostnameを指定します。')
    us = [x for x in (u.get('users') or []) if isinstance(x, dict) and x.get('name') == d['user']]
    ctx.require(us, f'usersに {d["user"]} を作ります。')
    ctx.require('NOPASSWD' in str(us[0].get('sudo')) and 'ALL' in str(us[0].get('sudo')), 'sudoを指定します。')
    ctx.require(d['key'] in (us[0].get('ssh_authorized_keys') or []), 'ssh_authorized_keysにpubkey.txtの公開鍵を入れます。')
    ctx.require(u.get('ssh_pwauth') is False, 'ssh_pwauth: false でパスワード認証を無効にします。')
    ctx.require(not re.search(r'^\s*(passwd|plain_text_passwd|password):', raw, re.M), 'パスワードを平文で書きません。')
    ctx.require(d['pkg'] in (u.get('packages') or []), 'packagesにパッケージを指定します。')
    cmds = [' '.join(map(str, c)) if isinstance(c, list) else str(c) for c in (u.get('runcmd') or [])]
    ctx.require(any(f'systemctl enable --now {d["pkg"]}' in c for c in cmds), 'runcmdでサービスを有効化します。')
    m = yload(ctx, 'meta-data')
    ctx.require(g(m, 'instance-id') == d['iid'] and g(m, 'local-hostname') == d['host'], 'meta-dataにinstance-idとlocal-hostnameを書きます。')
    ls = cmd_lines(ctx, 'seed.txt', 1)[0]
    ok_a = ls[:2] == ['cloud-localds', 'seed.iso'] and ls[2:] == ['user-data', 'meta-data']
    ok_b = ls[0] in ('genisoimage', 'mkisofs') and 'cidata' in ls and 'user-data' in ls and 'meta-data' in ls
    ctx.require(ok_a or ok_b, 'cloud-localds seed.iso user-data meta-data（または volid cidata のgenisoimage）にします。')


mission(4, 'cloud-initのuser-dataでVMを初回設定する',
        'クラウドイメージは初回起動時にcloud-initが設定を適用します。入力はuser-dataとmeta-dataで、cidataラベルのseed ISOかクラウドのメタデータとして渡します。仕様どおりのuser-data（#cloud-config）とmeta-dataを書き、seed作成コマンドを記録してください。',
        ['user-dataを書く', 'meta-dataを書く', 'seed作成コマンドをseed.txtへ'], s4, c4,
        """cat > user-data <<'EOF'
#cloud-config
hostname: <<host>>
ssh_pwauth: false
users:
  - name: <<user>>
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - <<key>>
packages:
  - <<pkg>>
runcmd:
  - systemctl enable --now <<pkg>>
EOF
printf 'instance-id: <<iid>>\\nlocal-hostname: <<host>>\\n' > meta-data
echo 'cloud-localds seed.iso user-data meta-data' > seed.txt""",
        ["printf '#cloud-config\\nhostname: <<host>>\\nssh_pwauth: true\\n' > user-data\nprintf 'instance-id: <<iid>>\\n' > meta-data\necho 'cloud-localds seed.iso user-data meta-data' > seed.txt",
         "printf 'hostname: <<host>>\\n' > user-data\necho 'cloud-localds seed.iso user-data meta-data' > seed.txt"],
        'cloud-initはuser-dataの先頭行 #cloud-config でYAML設定と判断します。users・packages・runcmd・ssh_pwauthなどが使えます。パスワードを平文で書かず、公開鍵(ssh_authorized_keys)を使います。runcmdは初回のみ実行されます。instance-idを変えると別インスタンスとして再初期化されます。結果は cloud-init status --wait と /var/log/cloud-init-output.log で確認し、cloud-init schema --config-file user-data で文法検査できます。',
        'user-dataは必ずYAMLで、先頭に目印が要ります。', 'ヒアドキュメントでYAMLを作ります。')


# ================================================================ 5 NAT iptables
def s5(ctx):
    a, b = 10 + secrets.randbelow(200), secrets.randbelow(250)
    wan = secrets.choice(['eth0', 'ens3', 'enp1s0'])
    d = dict(cidr=f'10.{a}.{b}.0/24', wan=wan, pub=8000 + secrets.randbelow(900), ip=f'10.{a}.{b}.{10 + secrets.randbelow(100)}',
             port=secrets.choice([80, 8080, 3000]))
    ctx.data.update(d)
    put(ctx, 'current.txt', f"$ sudo iptables -t nat -S\n-P PREROUTING ACCEPT\n-P POSTROUTING ACCEPT\n$ sysctl net.ipv4.ip_forward\nnet.ipv4.ip_forward = 0\n# 症状: 内側 {d['cidr']} から外へ出られず、公開ポート{d['pub']}も内側へ届かない\n")
    ctx.write('requirements.txt', f"LANセグメント {d['cidr']} をWAN側{wan}からMASQUERADEで出し、公開ポート tcp/{d['pub']} を内側 {d['ip']}:{d['port']} へDNATし、FORWARDで許可する。nat.sh にiptablesコマンドを1行ずつ書く（-t nat の POSTROUTING/PREROUTING、FORWARDではESTABLISHED,RELATEDの戻り通信と {d['ip']}:{d['port']} 宛ての許可）と、sysctl -w net.ipv4.ip_forward=1 の行。再起動後も有効にするため99-forward.conf に net.ipv4.ip_forward = 1 を書く。実行はしません。\n")


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = cmd_lines(ctx, 'nat.sh')

    def has(t, *pairs):
        return all(p in t and t[t.index(p) + 1] == v if isinstance(p, str) else False for p, v in pairs)
    ctx.require(find_line(ls, lambda t: t[:1] == ['iptables'] and t[1:2] == ['-t'] and 'nat' in t and '-A' in t and t[t.index('-A') + 1] == 'POSTROUTING' and has(t, ('-s', d['cidr']), ('-o', d['wan']), ('-j', 'MASQUERADE'))) >= 0,
                'POSTROUTINGで -s LAN -o WAN -j MASQUERADE を追加します。')
    ctx.require(find_line(ls, lambda t: t[:1] == ['iptables'] and 'nat' in t and '-A' in t and t[t.index('-A') + 1] == 'PREROUTING' and has(t, ('-i', d['wan']), ('-p', 'tcp'), ('--dport', str(d['pub'])), ('-j', 'DNAT'), ('--to-destination', f"{d['ip']}:{d['port']}"))) >= 0,
                'PREROUTINGで -i WAN -p tcp --dport 公開ポート -j DNAT --to-destination 内側IP:ポート を追加します。')
    ctx.require(find_line(ls, lambda t: t[:1] == ['iptables'] and '-A' in t and t[t.index('-A') + 1] == 'FORWARD' and '-j' in t and t[t.index('-j') + 1] == 'ACCEPT' and any('ESTABLISHED' in x and 'RELATED' in x for x in t)) >= 0,
                'FORWARDで conntrack の ESTABLISHED,RELATED を許可します。')
    ctx.require(find_line(ls, lambda t: t[:1] == ['iptables'] and '-A' in t and t[t.index('-A') + 1] == 'FORWARD' and has(t, ('-d', d['ip']), ('-p', 'tcp'), ('--dport', str(d['port'])), ('-j', 'ACCEPT'))) >= 0,
                'FORWARDで内側IPのポート宛てを許可します（DNAT後の宛先で判定）。')
    ctx.require(not any('-F' in t or '-P' in t or 'SNAT' in t for t in ls), '全消去・ポリシー変更・SNATは使いません。')
    ctx.require(find_line(ls, lambda t: t[:2] == ['sysctl', '-w'] and 'net.ipv4.ip_forward=1' in t) >= 0, 'sysctl -w net.ipv4.ip_forward=1 を書きます。')
    ctx.require(re.search(r'^\s*net\.ipv4\.ip_forward\s*=\s*1\s*$', ctx.need_file('99-forward.conf'), re.M), '99-forward.confに net.ipv4.ip_forward = 1 を書きます。')


mission(5, 'iptablesのMASQUERADE/DNATとnet.ipv4.ip_forwardを設定する',
        '社内LANの出口ルーターでNATを設定します。出ていく通信はMASQUERADE、公開ポートへの着信はDNATで内側のサーバへ転送します。カーネルが転送を許可する net.ipv4.ip_forward も必要です。current.txtの症状を読み、実行予定のiptablesとsysctlをnat.shに書き、永続化の設定ファイルも作ってください。',
        ['nat.shにMASQUERADE・DNAT・FORWARD許可・sysctlを書く', '99-forward.confで永続化'], s5, c5,
        """cat > nat.sh <<'EOF'
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -s <<cidr>> -o <<wan>> -j MASQUERADE
iptables -t nat -A PREROUTING -i <<wan>> -p tcp --dport <<pub>> -j DNAT --to-destination <<ip>>:<<port>>
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A FORWARD -d <<ip>> -p tcp --dport <<port>> -j ACCEPT
EOF
echo 'net.ipv4.ip_forward = 1' > 99-forward.conf""",
        ["printf '%s\\n' 'iptables -t nat -A POSTROUTING -s <<cidr>> -o <<wan>> -j MASQUERADE' > nat.sh\necho 'net.ipv4.ip_forward = 1' > 99-forward.conf",
         "printf '%s\\n' 'sysctl -w net.ipv4.ip_forward=1' 'iptables -t nat -A POSTROUTING -s <<cidr>> -o <<wan>> -j MASQUERADE' 'iptables -t nat -A PREROUTING -p tcp --dport <<pub>> -j DNAT --to-destination <<ip>>' > nat.sh\necho 'net.ipv4.ip_forward = 1' > 99-forward.conf"],
        'MASQUERADEはPOSTROUTINGで送信元をWAN側アドレスに書き換え、DNATはPREROUTINGで宛先を書き換えます。DNATの後にFORWARDチェーンが見る宛先は内側のIP:ポートです。戻り通信はconntrackが記憶しているため、ESTABLISHED,RELATEDを許可すれば逆変換されます。ip_forward=0だとルーターとして転送されません。sysctl -wは即時、/etc/sysctl.d/のファイルは再起動後も有効にします。確認は iptables -t nat -S と sysctl net.ipv4.ip_forward です。',
        'どのチェーンが変換の前後を担うか整理します。', 'iptables -t nat -A POSTROUTING / PREROUTING と FORWARD、sysctlを組み合わせます。')


# ================================================================ 6 conntrack
def s6(ctx):
    pub, ip, port = 8000 + secrets.randbelow(900), '10.0.%d.%d' % (secrets.randbelow(200), 10 + secrets.randbelow(100)), secrets.choice([80, 8080])
    cl = ['203.0.113.%d' % (10 + i * 7 + secrets.randbelow(5)) for i in range(5)]
    counts = [9, 6, 4, 3, 2]
    secrets.SystemRandom().shuffle(counts)
    top = cl[counts.index(9)]
    rows, est, tw = [], 0, 0
    sport = 40000
    for c, n in zip(cl, counts):
        for _ in range(n):
            sport += 1 + secrets.randbelow(30)
            st = secrets.choice(['ESTABLISHED', 'ESTABLISHED', 'TIME_WAIT'])
            if st == 'ESTABLISHED':
                est += 1
            else:
                tw += 1
            rows.append(f"tcp      6 {secrets.randbelow(400000)} {st} src={c} dst=198.51.100.1 sport={sport} dport={pub} src={ip} dst={c} sport={port} dport={sport} [ASSURED] mark=0 use=1\n")
    for _ in range(3):
        sport += 5
        rows.append(f"tcp      6 {secrets.randbelow(100)} TIME_WAIT src=10.0.0.5 dst=192.0.2.9 sport={sport} dport=443 src=192.0.2.9 dst=198.51.100.1 sport=443 dport={sport} [ASSURED] mark=0 use=1\n")
    secrets.SystemRandom().shuffle(rows)
    mx = 4096 * (1 + secrets.randbelow(4))
    cnt = int(mx * (0.6 + secrets.randbelow(35) / 100))
    ctx.data.update(pub=pub, ip=ip, port=port, top=top, est=est, tw=tw + 3, pct=int(cnt * 100 / mx), full=int(cnt * 100 / mx) >= 80)
    put(ctx, 'conntrack.txt', '$ sudo conntrack -L\n' + ''.join(rows) + f"conntrack v1.4.7 ({len(rows)} flow entries have been shown.)\n")
    put(ctx, 'limits.txt', f"net.netfilter.nf_conntrack_count = {cnt}\nnet.netfilter.nf_conntrack_max = {mx}\n")
    ctx.write('requirements.txt', f"conntrack.txt は conntrack -L の出力、limits.txt はテーブル使用量。answer.jsonに top_source（公開ポート{pub}宛ての接続が最も多い送信元IP）、established（dport={pub} の ESTABLISHED の数）、time_wait（全体のTIME_WAIT数）、backend（dport={pub} の応答側 src= が示すDNAT先 IP:ポート）、usage_percent（count/max の整数%、切り捨て）、table_full_risk（80%以上でtrue）を書く。cmd.txtに、実機でdport={pub} のtcpだけを表示する conntrack -L のコマンド1行を書く。\n")


def c6(ctx):
    need_ro(ctx)
    d, a = ctx.data, rj(ctx, 'answer.json')
    want = dict(top_source=d['top'], established=d['est'], time_wait=d['tw'], backend=f"{d['ip']}:{d['port']}", usage_percent=d['pct'], table_full_risk=d['full'])
    for k, v in want.items():
        ctx.require(a.get(k) == v, f'answer.jsonの{k}がconntrack.txt/limits.txtと一致しません。')
    t = cmd_lines(ctx, 'cmd.txt', 1)[0]
    ctx.require(t[:2] == ['conntrack', '-L'] and ('-p' in t and t[t.index('-p') + 1] == 'tcp'), 'conntrack -L -p tcp ... にします。')
    ctx.require(any(x in t for x in ('--dport', '--orig-port-dst')) and str(d['pub']) in t, '--dport で公開ポートを指定します。')


mission(6, 'conntrackのエントリとテーブル使用量を読み解く',
        'NATされた通信はconntrackが1本ずつ追跡しています。conntrack -L の記録から、DNAT先・接続数・状態を読み、nf_conntrack_max に対する使用量も評価してください。実機で絞り込む conntrack -L のコマンドも書きます。',
        ['answer.jsonに分析結果を書く', 'cmd.txtに絞り込みのconntrackコマンドを書く'], s6, c6,
        """python3 - <<'PYCODE'
import collections, json, re
rows = [line.split() for line in open('conntrack.txt') if line.startswith('tcp ')]
selected = [r for r in rows if r[7] == 'dport=<<pub>>']
sources = collections.Counter(r[4].split('=', 1)[1] for r in selected)
limits = dict(re.findall(r'nf_conntrack_(count|max) = (\\d+)', open('limits.txt').read()))
pct = int(limits['count']) * 100 // int(limits['max'])
backend = selected[0][8].split('=', 1)[1] + ':' + selected[0][10].split('=', 1)[1]
json.dump(dict(top_source=sources.most_common(1)[0][0],
               established=sum(r[3] == 'ESTABLISHED' for r in selected),
               time_wait=sum(r[3] == 'TIME_WAIT' for r in rows),
               backend=backend, usage_percent=pct, table_full_risk=pct >= 80),
          open('answer.json', 'w'))
PYCODE
echo 'conntrack -L -p tcp --dport <<pub>>' > cmd.txt""",
        ["printf '{\"top_source\":\"192.0.2.9\"}\\n' > answer.json\necho 'conntrack -L' > cmd.txt", "echo 'conntrack -L -p tcp --dport 443' > cmd.txt"],
        'conntrackの1行は「元の方向(src,dst,sport,dport)」と「応答方向」の2組を持ちます。DNATされると応答方向のsrcが内側サーバになります。状態はESTABLISHED・TIME_WAITなどです。nf_conntrack_countがnf_conntrack_maxに近づくと新規接続が破棄されるので、使用率を監視し、必要なら sysctl で上限を見直します。conntrack -L の絞り込みは -p, --dport, --src などで行い、conntrack -S で統計、conntrack -D で削除できます。',
        '1行は往路と復路の2組で構成されます。', 'awkでsrc=を数え、dport=公開ポートの行を絞ります。')


# ================================================================ 7 iptables -> nft
def s7(ctx):
    ssh, db = secrets.choice([22, 2222, 22022]), secrets.choice([3306, 5432])
    cidr = f'10.{secrets.randbelow(200)}.{secrets.randbelow(250)}.0/24'
    ctx.data.update(ssh=ssh, db=db, cidr=cidr)
    put(ctx, 'rules.v4', f"*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT ACCEPT [0:0]\n-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT\n-A INPUT -i lo -j ACCEPT\n-A INPUT -p tcp --dport {ssh} -j ACCEPT\n-A INPUT -s {cidr} -p tcp --dport {db} -j ACCEPT\n-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT\nCOMMIT\n")
    ctx.write('requirements.txt', "rules.v4はiptables-saveの出力。同じ動作のnftablesルールセットを nft.nft に書く（table inet filter、チェーン input と forward を hook付きで、policyは元のとおり）。ct state / iif / tcp dport / ip saddr を使う。cmd.txtに、適用せず構文だけ検査する nft のコマンド1行（nft -c -f nft.nft）を書く。\n")


def c7(ctx):
    need_ro(ctx)
    d = ctx.data
    t = re.sub(r'\s+', ' ', ctx.need_file('nft.nft'))
    rx(ctx, t, r'table (inet|ip) \w+ \{', 'table inet filter { ... } を作ります。', 0)
    rx(ctx, t, r'chain input \{[^}]*?type filter hook input priority (0|filter) ?; policy drop ?;', 'chain input に type filter hook input priority 0; policy drop; を付けます。', 0)
    rx(ctx, t, r'chain forward \{[^}]*?type filter hook forward priority (0|filter) ?; policy drop ?;', 'chain forward も policy drop にします。', 0)
    rx(ctx, t, r'ct state (\{ ?)?(established ?, ?related|related ?, ?established)( ?\})? accept', 'conntrack状態は ct state established,related accept です。', 0)
    rx(ctx, t, r'iif(name)? "?lo"? accept', 'ループバックを許可します（iif lo accept）。', 0)
    rx(ctx, t, r'tcp dport %d accept' % d['ssh'], 'SSHのポートを tcp dport で許可します。', 0)
    rx(ctx, t, r'ip saddr %s tcp dport %d accept' % (re.escape(d['cidr']), d['db']), '送信元限定のDBポートを ip saddr ... tcp dport ... accept で書きます。', 0)
    both = re.search(r'tcp dport \{ ?(80 ?, ?443|443 ?, ?80) ?\} accept', t) or (re.search(r'tcp dport 80 accept', t) and re.search(r'tcp dport 443 accept', t))
    ctx.require(both, '80と443は集合 { 80, 443 } か2行で許可します（multiportの置き換え）。')
    ls = cmd_lines(ctx, 'cmd.txt', 1)[0]
    ctx.require(ls[:1] == ['nft'] and any(x in ls for x in ('-c', '--check')) and '-f' in ls and 'nft.nft' in ls, 'nft -c -f nft.nft で適用せず検査します。')


mission(7, 'iptablesルールをnftablesへ書き換える',
        '新しいサーバではiptablesではなくnftが標準です。rules.v4（iptables-save形式）を読み、同じ意味のnftルールセットを書いてください。iptables-translateのような変換ツールが使えても、出力は必ず自分で読み直します。適用はせず、nft -c で検査します。',
        ['nft.nftを書く', '検査コマンドをcmd.txtへ'], s7, c7,
        """cat > nft.nft <<'EOF'
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif "lo" accept
    tcp dport <<ssh>> accept
    ip saddr <<cidr>> tcp dport <<db>> accept
    tcp dport { 80, 443 } accept
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
  }
}
EOF
echo 'nft -c -f nft.nft' > cmd.txt""",
        ["printf 'table inet filter {\\n chain input {\\n type filter hook input priority 0; policy accept;\\n tcp dport <<ssh>> accept\\n }\\n}\\n' > nft.nft\necho 'nft -c -f nft.nft' > cmd.txt",
         "printf 'table inet filter {\\n chain input {\\n type filter hook input priority 0; policy drop;\\n }\\n}\\n' > nft.nft\necho 'nft list ruleset' > cmd.txt"],
        'iptablesの -A INPUT はnftではchain inputのルール、:INPUT DROP は policy drop、--ctstate は ct state、-i lo は iif "lo"、--dport は tcp dport、-s は ip saddr に対応します。multiportは集合 { 80, 443 } で書けます。inet テーブルはIPv4とIPv6の両方を扱います。nft -c -f ファイル は構文だけ検査し、nft -f で適用、nft list ruleset で現在の状態を確認します。iptables-translate や iptables-restore-translate で変換の下書きを得られます。',
        '各オプションに対応するnftの式を表にします。', 'table inet filter に chain input と forward を作ります。')


# ================================================================ 8 netns
def s8(ctx):
    ns, a = 'ns' + hx(), 10 + secrets.randbelow(200)
    d = dict(ns=ns, vh='vh' + hx(1), vn='vn' + hx(1), hip=f'10.{a}.0.1', nip=f'10.{a}.0.2')
    ctx.data.update(d)
    ctx.write('requirements.txt', f"ip netns で隔離したネットワークを作り疎通を検証する手順を verify.sh に1行ずつ書く（実行しない。実機ではroot権限が必要）。名前空間 {d['ns']}、vethペア {d['vh']}（ホスト側）と {d['vn']}（名前空間側）、ホスト側 {d['hip']}/24、名前空間側 {d['nip']}/24。順序: netns作成 → vethペア作成 → 片端を名前空間へ移動 → ホスト側にアドレスとup → 名前空間内でアドレス設定とupとloのup → 名前空間内から {d['hip']} へping -c 1 → 後片付け（netns削除）。ホスト自身のループバックやNICは触らない。\n")


def norm(t):
    if t[:3] == ['ip', 'netns', 'exec']:
        return ('ns', t[3], t[4:])
    if t[:2] == ['ip', '-n'] or t[:2] == ['ip', '-netns']:
        return ('ns', t[2], ['ip'] + t[3:])
    return ('host', None, t)


def c8(ctx):
    d = ctx.data
    ls = [norm(t) for t in cmd_lines(ctx, 'verify.sh')]
    ctx.require(not any(k == 'host' and ('lo' in t or 'eth0' in t) for k, _, t in ls), 'ホスト側のloや実NICは操作しません。')

    def idx(pred, msg):
        i = find_line(ls, pred)
        ctx.require(i >= 0, msg)
        return i

    def sub(t, *seq):
        return all(s in t for s in seq)
    i1 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'netns', 'add'] and d['ns'] in x[2], 'ip netns add で名前空間を作ります。')
    i2 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'link', 'add'] and 'veth' in x[2] and 'peer' in x[2] and d['vh'] in x[2] and d['vn'] in x[2], 'ip link add ... type veth peer name で作ります。')
    i3 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'link', 'set'] and d['vn'] in x[2] and 'netns' in x[2] and d['ns'] in x[2], 'ip link set 名前空間側 netns 名前空間 で移動します。')
    i4 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'addr', 'add'] and f"{d['hip']}/24" in x[2] and d['vh'] in x[2], 'ホスト側にアドレスを付けます。')
    i5 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'link', 'set'] and d['vh'] in x[2] and 'up' in x[2], 'ホスト側をupにします。')
    i6 = idx(lambda x: x[0] == 'ns' and x[1] == d['ns'] and x[2][:3] == ['ip', 'addr', 'add'] and f"{d['nip']}/24" in x[2] and d['vn'] in x[2], '名前空間内でアドレスを付けます。')
    i7 = idx(lambda x: x[0] == 'ns' and x[1] == d['ns'] and x[2][:3] == ['ip', 'link', 'set'] and d['vn'] in x[2] and 'up' in x[2], '名前空間内でvethをupにします。')
    i8 = idx(lambda x: x[0] == 'ns' and x[1] == d['ns'] and x[2][:3] == ['ip', 'link', 'set'] and 'lo' in x[2] and 'up' in x[2], '名前空間内のloもupにします。')
    i9 = idx(lambda x: x[0] == 'ns' and x[1] == d['ns'] and x[2][:1] == ['ping'] and d['hip'] in x[2] and '-c' in x[2], '名前空間内からホスト側へping -c 1 します。')
    i10 = idx(lambda x: x[0] == 'host' and x[2][:3] == ['ip', 'netns', 'del'] and d['ns'] in x[2], '最後にip netns delで片付けます。')
    ctx.require(i1 < i2 < i3 and i3 < i6 and i4 <= i9 and i5 < i9 and i6 < i9 and i7 < i9 and i8 < i9 and i9 < i10, '作成 → 移動 → 設定 → 検証 → 後片付けの順序にします（移動前の名前空間側設定は不可）。')


mission(8, 'ip netnsとvethで検証用ネットワークを組み立てる',
        'ファイアウォールやNATの検証は、本番を壊さないよう ip netns のネットワーク名前空間と veth で隔離して行います。要件の手順を verify.sh に並べてください。実行はしませんが、順序と対象を間違えると本物のNICを壊します。',
        ['verify.shに手順を順序どおり書く'], s8, c8,
        """cat > verify.sh <<'EOF'
ip netns add <<ns>>
ip link add <<vh>> type veth peer name <<vn>>
ip link set <<vn>> netns <<ns>>
ip addr add <<hip>>/24 dev <<vh>>
ip link set <<vh>> up
ip netns exec <<ns>> ip addr add <<nip>>/24 dev <<vn>>
ip netns exec <<ns>> ip link set <<vn>> up
ip netns exec <<ns>> ip link set lo up
ip netns exec <<ns>> ping -c 1 <<hip>>
ip netns del <<ns>>
EOF""",
        ["printf '%s\\n' 'ip netns add <<ns>>' 'ip link set lo up' 'ip netns exec <<ns>> ping -c 1 <<hip>>' > verify.sh",
         "printf '%s\\n' 'ip netns add <<ns>>' 'ip link add <<vh>> type veth peer name <<vn>>' 'ip netns exec <<ns>> ip addr add <<nip>>/24 dev <<vn>>' 'ip link set <<vn>> netns <<ns>>' 'ip netns exec <<ns>> ping -c 1 <<hip>>' 'ip netns del <<ns>>' > verify.sh"],
        'ip netns add で独立したネットワークスタックを作り、veth はケーブルのように両端がペアのインターフェースです。片端を ip link set ... netns で名前空間に移すと、ホスト側から見えなくなります。移した後の設定は ip netns exec 名前空間 コマンド（または ip -n 名前空間）で行います。名前空間内のloもupにしないと自己宛て通信が動きません。確認は ip netns list と ip -n NS addr、後片付けは ip netns del です。NATの検証ではこの中でiptables/nftを動かすと本物に影響しません。',
        '移動した後のインターフェースは名前空間内からしか設定できません。', 'ip netns add/exec/del と ip link add type veth を使います。')


# ================================================================ 9 vagrant
def s9(ctx):
    box = secrets.choice(['ubuntu/jammy64', 'generic/debian12', 'bento/rockylinux-9'])
    host, ip = 'dev-' + hx(), f'192.168.56.{10 + secrets.randbelow(200)}'
    hp, mem, cpu = 8000 + secrets.randbelow(900), 512 * (1 + secrets.randbelow(4)), 1 + secrets.randbelow(4)
    pkg = secrets.choice(['nginx', 'git', 'htop'])
    ctx.data.update(box=box, host=host, ip=ip, hp=hp, mem=mem, cpu=cpu, pkg=pkg)
    ctx.write('Vagrantfile', 'Vagrant.configure("2") do |config|\n  # TODO\nend\n')
    ctx.write('requirements.txt', f"Vagrantfileを完成させる: box={box}、hostname={host}、private_networkのip={ip}、forwarded_port guest 80 → host {hp}、VirtualBoxプロバイダでmemory={mem}・cpus={cpu}、shellプロビジョナ（inline）で apt-get install -y {pkg}。cmds.txtに vagrant validate / vagrant up / vagrant ssh -c で確認 / vagrant destroy -f を4行。compare.jsonに構成管理ツールの比較を書く: ansible・puppet・chef それぞれ agent（エージェント常駐が必要か、true/false）、format（yaml / puppet-dsl / ruby のいずれか）、mode（push / pull）。\n")


def c9(ctx):
    d = ctx.data
    v = ctx.need_file('Vagrantfile')
    rx(ctx, v, r'Vagrant\.configure\(["\']2["\']\)\s+do\s+\|config\|', 'Vagrant.configure("2") do |config| を保ちます。')
    rx(ctx, v, r'^\s*config\.vm\.box\s*=\s*["\']%s["\']' % re.escape(d['box']), 'config.vm.box を指定します。')
    rx(ctx, v, r'^\s*config\.vm\.hostname\s*=\s*["\']%s["\']' % d['host'], 'config.vm.hostname を指定します。')
    rx(ctx, v, r'config\.vm\.network\s+["\']private_network["\']\s*,\s*ip:\s*["\']%s["\']' % re.escape(d['ip']), 'private_networkのipを指定します。')
    rx(ctx, v, r'config\.vm\.network\s+["\']forwarded_port["\']\s*,\s*(guest:\s*80\s*,\s*host:\s*%d|host:\s*%d\s*,\s*guest:\s*80)\b' % (d['hp'], d['hp']), 'forwarded_portを指定します。')
    rx(ctx, v, r'config\.vm\.provider\s+["\']virtualbox["\']\s+do\s+\|(\w+)\|', 'config.vm.provider "virtualbox" do |vb| ブロックを書きます。')
    rx(ctx, v, r'\.memory\s*=\s*["\']?%d["\']?' % d['mem'], 'memoryを指定します。')
    rx(ctx, v, r'\.cpus\s*=\s*%d\b' % d['cpu'], 'cpusを指定します。')
    rx(ctx, v, r'config\.vm\.provision\s+["\']shell["\']\s*,\s*inline:\s*["\'][^"\']*apt-get install -y %s' % d['pkg'], 'shellプロビジョナのinlineでインストールします。')
    ctx.require(len(re.findall(r'^\s*end\s*$', v, re.M)) >= 2, 'doブロックを end で閉じます。')
    ls = cmd_lines(ctx, 'cmds.txt', 4)
    ctx.require(ls[0][:2] == ['vagrant', 'validate'] and ls[1][:2] == ['vagrant', 'up'], '最初は vagrant validate、次に vagrant up です。')
    ctx.require(ls[2][:2] == ['vagrant', 'ssh'] and '-c' in ls[2], 'vagrant ssh -c "コマンド" で確認します。')
    ctx.require(ls[3][:2] == ['vagrant', 'destroy'] and '-f' in ls[3], '最後は vagrant destroy -f です。')
    c = rj(ctx, 'compare.json')
    want = {'ansible': (False, 'yaml', 'push'), 'puppet': (True, 'puppet-dsl', 'pull'), 'chef': (True, 'ruby', 'pull')}
    for k, (ag, fm, md) in want.items():
        e = c.get(k)
        ctx.require(isinstance(e, dict) and e.get('agent') is ag and e.get('format') == fm and e.get('mode') == md, f'{k} の agent/format/mode が違います。')


mission(9, 'VagrantfileでVMを宣言しPuppet/Chefと比較する',
        'Vagrantは開発用VMをVagrantfileで宣言し、vagrant upで再現できる環境を作ります。要件に合わせたVagrantfileを書き、確認用の手順を残してください。またプロビジョナの選択肢として、既出のAnsibleと、PuppetやChefの考え方の違いをcompare.jsonに整理します。',
        ['Vagrantfileを完成させる', 'cmds.txtにvagrantの手順を書く', 'compare.jsonで構成管理ツールを比較'], s9, c9,
        """cat > Vagrantfile <<'EOF'
Vagrant.configure("2") do |config|
  config.vm.box = "<<box>>"
  config.vm.hostname = "<<host>>"
  config.vm.network "private_network", ip: "<<ip>>"
  config.vm.network "forwarded_port", guest: 80, host: <<hp>>
  config.vm.provider "virtualbox" do |vb|
    vb.memory = <<mem>>
    vb.cpus = <<cpu>>
  end
  config.vm.provision "shell", inline: "apt-get install -y <<pkg>>"
end
EOF
printf '%s\\n' 'vagrant validate' 'vagrant up' 'vagrant ssh -c "systemctl is-active <<pkg>>"' 'vagrant destroy -f' > cmds.txt
echo '{"ansible":{"agent":false,"format":"yaml","mode":"push"},"puppet":{"agent":true,"format":"puppet-dsl","mode":"pull"},"chef":{"agent":true,"format":"ruby","mode":"pull"}}' > compare.json""",
        ["printf 'Vagrant.configure(\"2\") do |config|\\n  config.vm.box = \"<<box>>\"\\nend\\n' > Vagrantfile\nprintf '%s\\n' 'vagrant validate' 'vagrant up' 'vagrant ssh -c \"ls\"' 'vagrant destroy -f' > cmds.txt\necho '{}' > compare.json",
         "echo '{\"ansible\":{\"agent\":true,\"format\":\"ruby\",\"mode\":\"pull\"}}' > compare.json"],
        'VagrantfileはRubyのDSLで、box・network・providerのメモリ設定・provisionを宣言します。vagrant validate で構文確認、up で作成と初回provision、ssh -c で中の状態確認、destroy -f で破棄します。構成管理は、Ansibleがエージェント不要でYAMLのplaybookをsshでpushするのに対し、Puppetは独自DSLのmanifestをエージェントが定期的にサーバからpullして収束させ、ChefはRubyのrecipeをchef-clientがpullします。どれも冪等性（目的の状態を宣言）が目標です。',
        'Vagrantfileは設定を宣言するだけで、実行は別コマンドです。', 'ヒアドキュメントでVagrantfileを書き、compare.jsonは1行JSONにします。')


# ================================================================ 10 kubectl diagnose
def s10(ctx):
    ns = 'shop-' + hx(1)
    api, web, okp = 'api-' + hx(3), 'web-' + hx(3), 'cache-' + hx(3)
    api = f'{api[:-1]}-{hx(2)}'
    env = secrets.choice(['DATABASE_URL', 'REDIS_HOST', 'JWT_SECRET_PATH', 'PAYMENT_ENDPOINT'])
    good = f'v2.{secrets.randbelow(5)}.{secrets.randbelow(9)}'
    bad = good + secrets.choice(['-rc', 'x', '.0'])
    img = f'registry.example.com/shop/web:{bad}'
    ctx.data.update(ns=ns, api=api, web=web, env=env, good=good, bad=bad)
    put(ctx, 'get-pods.txt', f"$ kubectl get pods -n {ns}\nNAME{' ' * 20}READY   STATUS             RESTARTS      AGE\n{okp:<24}1/1     Running            0             2d\n{api:<24}0/1     CrashLoopBackOff   {5 + secrets.randbelow(8)} (40s ago)   12m\n{web:<24}0/1     ImagePullBackOff   0             3m\n")
    put(ctx, 'describe-web.txt', f"$ kubectl describe pod {web} -n {ns}\nName:         {web}\nStatus:       Pending\nContainers:\n  web:\n    Image:          {img}\n    State:          Waiting\n      Reason:       ImagePullBackOff\nEvents:\n  Type     Reason     Message\n  Normal   Pulling    Pulling image \"{img}\"\n  Warning  Failed     Failed to pull image \"{img}\": rpc error: manifest unknown: manifest unknown\n  Warning  Failed     Error: ErrImagePull\n  Normal   BackOff    Back-off pulling image \"{img}\"\n")
    put(ctx, 'logs-api.txt', f"$ kubectl logs {api} -n {ns} --previous\n2026-11-20T09:00:01Z INFO  starting api server\n2026-11-20T09:00:01Z INFO  loading config\n2026-11-20T09:00:02Z FATAL environment variable {env} is required\n")
    put(ctx, 'describe-api.txt', f"$ kubectl describe pod {api} -n {ns}\nContainers:\n  api:\n    State:          Waiting\n      Reason:       CrashLoopBackOff\n    Last State:     Terminated\n      Reason:       Error\n      Exit Code:    1\n    Restart Count:  9\nEvents:\n  Warning  BackOff  Back-off restarting failed container api\n")
    put(ctx, 'release-notes.txt', f"web の公開済みタグ: v2.0.1 v2.1.0 {good} （最新の安定版は {good}）\n")
    ctx.write('requirements.txt', f"get-pods.txt（kubectl get）、describe-*.txt（kubectl describe）、logs-api.txt（kubectl logs --previous）から原因を診断し、answer.jsonに crashloop_pod, missing_env（ログが要求する環境変数名）, imagepull_pod, bad_tag, good_tag を書く。cmds.txtに実機で実行する3行: 前回のコンテナのログを見る kubectl logs（-p/--previous と -n）、{web} の kubectl describe pod、Deploymentのイメージを直す kubectl set image deployment/web web=...（-n付き）。\n")


def c10(ctx):
    need_ro(ctx)
    d, a = ctx.data, rj(ctx, 'answer.json')
    want = dict(crashloop_pod=d['api'], missing_env=d['env'], imagepull_pod=d['web'], bad_tag=d['bad'], good_tag=d['good'])
    for k, v in want.items():
        ctx.require(a.get(k) == v, f'answer.jsonの{k}が記録と一致しません。')
    ls = cmd_lines(ctx, 'cmds.txt', 3)
    ns = lambda t: d['ns'] in t and ('-n' in t or '--namespace' in t)
    ctx.require(ls[0][:2] == ['kubectl', 'logs'] and d['api'] in ls[0] and ('-p' in ls[0] or '--previous' in ls[0]) and ns(ls[0]), '1行目: kubectl logs POD --previous -n NS')
    ctx.require(ls[1][:3] == ['kubectl', 'describe', 'pod'] and d['web'] in ls[1] and ns(ls[1]), '2行目: kubectl describe pod POD -n NS')
    ctx.require(ls[2][:3] == ['kubectl', 'set', 'image'] and 'deployment/web' in ls[2] and f"web=registry.example.com/shop/web:{d['good']}" in ls[2] and ns(ls[2]), '3行目: kubectl set image deployment/web web=正しいイメージ -n NS')


mission(10, 'kubectl get/describe/logsでCrashLoopBackOffとImagePullBackOffを診断する',
        'Kubernetes上の2つのPodが起動しません。kubectl get でSTATUSを見て、kubectl describe のEventsとkubectl logs --previous の最後の行から原因を切り分けます。CrashLoopBackOff（起動してはすぐ落ちる）とImagePullBackOff（イメージを取得できない）では見る場所が違います。',
        ['answer.jsonに診断を書く', 'cmds.txtに実機での確認・修正コマンドを書く'], s10, c10,
        """python3 - <<'PYCODE'
import json, re
rows = [line.split() for line in open('get-pods.txt') if not line.startswith(('$', 'NAME'))]
crash = next(r[0] for r in rows if r[2] == 'CrashLoopBackOff')
pull = next(r[0] for r in rows if r[2] == 'ImagePullBackOff')
missing = re.search(r'environment variable (\\w+) is required', open('logs-api.txt').read()).group(1)
image = re.search(r'Image:\\s+(\\S+)', open('describe-web.txt').read()).group(1)
good = re.search(r'最新の安定版は (\\S+)）', open('release-notes.txt').read()).group(1)
json.dump(dict(crashloop_pod=crash, missing_env=missing, imagepull_pod=pull,
               bad_tag=image.rsplit(':', 1)[1], good_tag=good), open('answer.json', 'w'))
PYCODE
printf '%s\\n' 'kubectl logs <<api>> --previous -n <<ns>>' 'kubectl describe pod <<web>> -n <<ns>>' 'kubectl set image deployment/web web=registry.example.com/shop/web:<<good>> -n <<ns>>' > cmds.txt""",
        ["printf '{\"crashloop_pod\":\"<<web>>\",\"missing_env\":\"<<env>>\",\"imagepull_pod\":\"<<api>>\",\"bad_tag\":\"<<good>>\",\"good_tag\":\"<<bad>>\"}\\n' > answer.json\necho 'kubectl get pods' > cmds.txt",
         "printf '{\"crashloop_pod\":\"<<api>>\",\"missing_env\":\"<<env>>\",\"imagepull_pod\":\"<<web>>\",\"bad_tag\":\"<<bad>>\",\"good_tag\":\"<<good>>\"}\\n' > answer.json\nprintf '%s\\n' 'kubectl logs <<api>>' 'kubectl describe pod <<web>>' 'kubectl delete pod <<web>>' > cmds.txt"],
        'ImagePullBackOffは、イメージ名・タグ・レジストリ認証(imagePullSecrets)のどれかが原因で、kubectl describe pod のEventsに「manifest unknown」や「unauthorized」が出ます。CrashLoopBackOffはコンテナ自体が終了を繰り返す状態で、現在のコンテナは再起動直後で空のことが多いため kubectl logs --previous で直前の実行のログを見ます。Exit Code 1は設定不備、137はOOMKilled（メモリ超過）の目安です。直すのはPod単体ではなくDeploymentで、kubectl set image が使え、kubectl rollout status で結果を確認します。',
        'STATUSごとに見る場所が違います。', 'kubectl logs -p / describe pod / set image deployment/ を使います。')


# ================================================================ 11 manifests
def s11(ctx):
    app, ns = 'shop-' + hx(1), 'prod'
    cp = secrets.choice([8080, 3000, 9000])
    host = f'{app}.example.com'
    mem_req, mem_lim = secrets.choice([('128Mi', '256Mi'), ('256Mi', '512Mi'), ('64Mi', '128Mi')])
    ctx.data.update(app=app, cp=cp, host=host, mreq=mem_req, mlim=mem_lim)
    put(ctx, 'deployment.orig.yaml', f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {app}\nspec:\n  replicas: 3\n  selector:\n    matchLabels:\n      app: {app}\n  template:\n    metadata:\n      labels:\n        app: {app}\n    spec:\n      containers:\n        - name: web\n          image: registry.example.com/shop/web:v1.4.2\n          ports:\n            - containerPort: {cp}\n")
    ctx.write('deployment.yaml', ctx.read('deployment.orig.yaml'))
    ctx.write('service.yaml', f"apiVersion: v1\nkind: Service\nmetadata:\n  name: {app}-svc\nspec:\n  selector:\n    app: shop-web\n  ports:\n    - port: 80\n      targetPort: 80\n")
    ctx.write('ingress.yaml', f"apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: {app}\nspec:\n  rules:\n    - host: {host}\n      http:\n        paths:\n          - path: /\n            pathType: Prefix\n            backend:\n              service:\n                name: {app}\n                port:\n                  number: {cp}\n")
    ctx.write('requirements.txt', f"deployment.yaml（原本は deployment.orig.yaml）、service.yaml、ingress.yaml のYAMLを読む。(1) ServiceのselectorがDeploymentのPodラベルと違い、targetPortもコンテナのポートと違う。Serviceのportは80のまま、selectorとtargetPortを直す。(2) Ingressのbackendが存在しないService名とポートを指している。Service名と、Serviceのport(80)に直す。(3) deployment.yaml のコンテナに resources（requests: cpu 100m / memory {mem_req}、limits: cpu 500m / memory {mem_lim}）、readinessProbe（httpGet /healthz、ポート{cp}、initialDelaySeconds 5、periodSeconds 10）、livenessProbe（httpGet /livez、ポート{cp}、initialDelaySeconds 15、failureThreshold 3）を足す。他の項目は変えない。\n")


def c11(ctx):
    need_ro(ctx)
    d = ctx.data
    dep, svc, ing = yload(ctx, 'deployment.yaml'), yload(ctx, 'service.yaml'), yload(ctx, 'ingress.yaml')
    orig = parse_yaml(ctx.need_file('deployment.orig.yaml'))
    ctx.require(g(dep, 'kind') == 'Deployment' and g(dep, 'spec', 'replicas') == 3 and g(dep, 'spec', 'template', 'metadata', 'labels') == {'app': d['app']}, 'Deploymentの既存項目（replicasやlabels）は変えません。')
    c = g(dep, 'spec', 'template', 'spec', 'containers', 0)
    oc = g(orig, 'spec', 'template', 'spec', 'containers', 0)
    ctx.require(isinstance(c, dict) and c.get('image') == oc['image'] and c.get('name') == 'web' and g(c, 'ports', 0, 'containerPort') == d['cp'], 'コンテナのname/image/portは変えません。')
    ctx.require(g(c, 'resources', 'requests') == {'cpu': '100m', 'memory': d['mreq']}, 'resources.requests を指定します。')
    ctx.require(g(c, 'resources', 'limits') == {'cpu': '500m', 'memory': d['mlim']}, 'resources.limits を指定します。')
    for name, path, delay in (('readinessProbe', '/healthz', 5), ('livenessProbe', '/livez', 15)):
        ctx.require(g(c, name, 'httpGet', 'path') == path and g(c, name, 'httpGet', 'port') == d['cp'] and g(c, name, 'initialDelaySeconds') == delay, f'{name} のhttpGet path/port/initialDelaySecondsを指定します。')
    ctx.require(g(c, 'readinessProbe', 'periodSeconds') == 10 and g(c, 'livenessProbe', 'failureThreshold') == 3, 'periodSecondsとfailureThresholdも指定します。')
    ctx.require(g(svc, 'kind') == 'Service' and g(svc, 'spec', 'selector') == {'app': d['app']}, 'Serviceのselectorを Pod のラベルに合わせます。')
    ctx.require(g(svc, 'spec', 'ports', 0, 'port') == 80 and g(svc, 'spec', 'ports', 0, 'targetPort') == d['cp'], 'portは80、targetPortはコンテナのポートにします。')
    b = g(ing, 'spec', 'rules', 0, 'http', 'paths', 0, 'backend', 'service')
    ctx.require(g(b, 'name') == g(svc, 'metadata', 'name') and g(b, 'port', 'number') == 80, 'Ingressのbackendを Service名 と Serviceのport(80)に合わせます。')
    ctx.require(g(ing, 'spec', 'rules', 0, 'host') == d['host'], 'Ingressのhostは変えません。')


mission(11, 'Deployment・Service・Ingressを読み、requests/limits・probeを足す',
        'Kubernetesでは、Ingress → Service → Pod とラベルとポートで繋がります。1つでも食い違うと通信できません。3つのYAMLを読んで食い違いを直し、DeploymentにはCPU・メモリのrequests/limitsと、readiness・livenessのprobeを追加してください。',
        ['ServiceとIngressの食い違いを直す', 'Deploymentにresourcesとprobeを足す'], s11, c11,
        """sed -i 's/app: shop-web/app: <<app>>/; s/targetPort: 80/targetPort: <<cp>>/' service.yaml
sed -i 's/name: <<app>>$/name: <<app>>-svc/; s/number: <<cp>>/number: 80/' ingress.yaml
sed -i '1,/^spec:/!b' ingress.yaml
sed -i '0,/name: <<app>>-svc/s//name: <<app>>/' ingress.yaml
cat >> deployment.yaml <<'EOF'
          resources:
            requests:
              cpu: 100m
              memory: <<mreq>>
            limits:
              cpu: 500m
              memory: <<mlim>>
          readinessProbe:
            httpGet:
              path: /healthz
              port: <<cp>>
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /livez
              port: <<cp>>
            initialDelaySeconds: 15
            failureThreshold: 3
EOF""",
        ["sed -i 's/app: shop-web/app: <<app>>/' service.yaml",
         "sed -i 's/number: <<cp>>/number: 80/' ingress.yaml\ncat >> deployment.yaml <<'EOF'\n          resources:\n            limits:\n              memory: <<mlim>>\nEOF"],
        'DeploymentのPodテンプレートのlabelsに、Serviceのselectorが一致して初めてエンドポイントができます（kubectl get endpoints で確認）。Serviceのportは外から見える番号、targetPortはコンテナのポートです。IngressはServiceの名前とportを参照します。requestsはスケジューリングの予約量、limitsは上限で、メモリがlimitsを超えるとOOMKilledになります。readinessProbeは失敗するとトラフィックから外れ、livenessProbeは失敗が続くと再起動されます。YAMLを適用前に kubectl apply --dry-run=server や kubectl diff で確認します。',
        '上流から順に、名前・ラベル・ポートを突き合わせます。', 'sedで置換し、Deploymentは末尾にresourcesとprobeを足します。')


# ================================================================ 12 helm
def s12(ctx):
    app = 'shop' + hx(1)
    d = dict(app=app, rep=3 + secrets.randbelow(4), tag='1.%d.%d' % (5 + secrets.randbelow(5), secrets.randbelow(9)),
             host=f'{app}.example.com', mem=secrets.choice(['256Mi', '512Mi', '1Gi']), ns='prod-' + hx(1))
    ctx.data.update(d)
    ctx.mkdir('chart/templates')
    put(ctx, 'chart/values.yaml', "replicaCount: 1\nimage:\n  repository: registry.example.com/shop/web\n  tag: \"1.0.0\"\ningress:\n  enabled: false\n  host: example.local\nresources:\n  limits:\n    cpu: 500m\n    memory: 128Mi\n")
    put(ctx, 'chart/templates/deployment.yaml', "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {{ .Release.Name }}\nspec:\n  replicas: {{ .Values.replicaCount }}\n  template:\n    spec:\n      containers:\n        - name: web\n          image: \"{{ .Values.image.repository }}:{{ .Values.image.tag }}\"\n          resources:\n            {{- toYaml .Values.resources | nindent 12 }}\n")
    ctx.write('requirements.txt', f"Helmチャート ./chart の values.yaml を読み、本番用の values-prod.yaml（変更する項目だけ。存在しないキーは書かない）を作る: replicaCount={d['rep']}、image.tag={d['tag']}、ingress.enabled=true・ingress.host={d['host']}、resources.limits.memory={d['mem']}。helm.txtに3行: (1)レンダリングだけ確認する helm template（リリース名 {app}、-f 指定）、(2)名前空間 {d['ns']}（なければ作成）へ upgrade --install（--atomic、-f values-prod.yaml）、(3)失敗時にリビジョン1へ戻す helm rollback。\n")


def c12(ctx):
    need_ro(ctx)
    d = ctx.data
    v = yload(ctx, 'values-prod.yaml')
    base = parse_yaml(ctx.need_file('chart/values.yaml'))

    def keys(x, p=()):
        for k, val in x.items():
            yield p + (k,)
            if isinstance(val, dict):
                yield from keys(val, p + (k,))
    allowed = set(keys(base))
    for k in keys(v):
        ctx.require(k in allowed, '.'.join(k) + ' はvalues.yamlに存在しません（綴りを確認）。')
    ctx.require(v.get('replicaCount') == d['rep'] and g(v, 'image', 'tag') == d['tag'] and g(v, 'ingress', 'enabled') is True
                and g(v, 'ingress', 'host') == d['host'] and g(v, 'resources', 'limits', 'memory') == d['mem'], 'values-prod.yamlの値が要件と一致しません（tagは文字列、enabledは真偽値）。')
    ctx.require(str(g(v, 'image', 'tag')) == d['tag'], 'image.tagを指定します。')
    ls = cmd_lines(ctx, 'helm.txt', 3)
    ctx.require(ls[0][:3] == ['helm', 'template', d['app']] and './chart' in ls[0] and '-f' in ls[0] and 'values-prod.yaml' in ls[0], '1行目: helm template リリース名 ./chart -f values-prod.yaml')
    t = ls[1]
    ctx.require(t[:2] == ['helm', 'upgrade'] and '--install' in t and d['app'] in t and './chart' in t and '--atomic' in t and '--create-namespace' in t, '2行目: helm upgrade --install リリース名 ./chart ... --atomic --create-namespace')
    ctx.require('-n' in t and t[t.index('-n') + 1] == d['ns'] and '-f' in t and t[t.index('-f') + 1] == 'values-prod.yaml', '-n 名前空間 と -f values-prod.yaml を付けます。')
    ctx.require(ls[2][:3] == ['helm', 'rollback', d['app']] and '1' in ls[2] and d['ns'] in ls[2], '3行目: helm rollback リリース名 1 -n 名前空間')


mission(12, 'Helmのvaluesで環境差分を上書きしupgradeを組み立てる',
        'Helmはチャート（テンプレート＋既定のvalues.yaml）に、環境ごとのvaluesを重ねて、Kubernetesへ配布します。chart/values.yamlとテンプレートを読み、本番用のvalues-prod.yamlと、安全な helm upgrade --install の手順を書いてください。',
        ['values-prod.yamlを作る', 'helm.txtに3手順を書く'], s12, c12,
        """cat > values-prod.yaml <<'EOF'
replicaCount: <<rep>>
image:
  tag: "<<tag>>"
ingress:
  enabled: true
  host: <<host>>
resources:
  limits:
    memory: <<mem>>
EOF
printf '%s\\n' 'helm template <<app>> ./chart -f values-prod.yaml' 'helm upgrade --install <<app>> ./chart -n <<ns>> --create-namespace -f values-prod.yaml --atomic' 'helm rollback <<app>> 1 -n <<ns>>' > helm.txt""",
        ["printf 'replicas: <<rep>>\\nimage:\\n  tag: \"<<tag>>\"\\n' > values-prod.yaml\nprintf '%s\\n' 'helm template <<app>> ./chart -f values-prod.yaml' 'helm upgrade --install <<app>> ./chart -n <<ns>> --create-namespace -f values-prod.yaml --atomic' 'helm rollback <<app>> 1 -n <<ns>>' > helm.txt",
         "printf 'replicaCount: <<rep>>\\nimage:\\n  tag: \"<<tag>>\"\\ningress:\\n  enabled: true\\n  host: <<host>>\\nresources:\\n  limits:\\n    memory: <<mem>>\\n' > values-prod.yaml\nprintf '%s\\n' 'helm install <<app>> ./chart' 'helm upgrade <<app>> ./chart' 'helm rollback <<app>>' > helm.txt"],
        'values.yamlの既定値に -f で渡したファイルが深くマージされます（同じキーだけ上書き）。キーの綴りを間違えると無視されるため、まず helm template でレンダリング結果を確認し、helm lint も使います。helm upgrade --install は初回も更新も同じコマンドで、--atomic は失敗時に自動ロールバック、--create-namespace は名前空間を作ります。履歴は helm history、戻すのは helm rollback リリース名 リビジョン です。タグ "1.2.0" は数値と誤読されないよう文字列で書きます。',
        '上書きするのは変更する項目だけです。', 'values-prod.yamlはcatで書き、helm.txtはprintfで3行並べます。')


# ================================================================ 13 terraform
def s13(ctx):
    h = lambda: hx(3)
    web, db, tmp, role = [f'{t}.{n}' for t, n in (('aws_instance', 'web'), ('aws_db_instance', 'main'), ('aws_s3_bucket', 'tmp'), ('aws_iam_role', 'ci'))]
    sg = 'aws_security_group.app'
    attr = secrets.choice(['instance_type', 'desired_capacity', 'cidr_blocks'])
    drift_from, drift_to = {'instance_type': ('t3.small', 't3.large'), 'desired_capacity': ('2', '5'), 'cidr_blocks': ('10.0.0.0/16', '0.0.0.0/0')}[attr]
    n_inplace = 1 + secrets.randbelow(2)
    extra = [f'aws_instance.worker{i}' for i in range(n_inplace)]
    adds = 1 + 1  # role + replaced db
    changes = 1 + n_inplace  # web + extras
    destroys = 1 + 1  # tmp + replaced db
    ch = ''.join(f'  # {w} will be updated in-place\n  ~ resource "aws_instance" "{w.split(".")[1]}" {{\n      ~ tags = {{ "Env" = "dev" -> "prod" }}\n    }}\n\n' for w in [web] + extra)
    put(ctx, 'plan.txt', f"""$ terraform plan
aws_instance.web: Refreshing state... [id=i-{h()}]
aws_security_group.app: Refreshing state... [id=sg-{h()}]

Note: Objects have changed outside of Terraform

Terraform detected the following changes made outside of Terraform since the last "terraform apply":

  # {sg} has changed
  ~ resource "aws_security_group" "app" {{
      ~ {attr} = {'"' + drift_from + '"'} -> {'"' + drift_to + '"'}
        id = "sg-{h()}"
    }}

Terraform will perform the following actions:

{ch}  # {db} must be replaced
-/+ resource "aws_db_instance" "main" {{
      ~ engine_version = "13.7" -> "14.5" # forces replacement
    }}

  # {tmp} will be destroyed
  - resource "aws_s3_bucket" "tmp" {{
      - bucket = "tmp-{h()}" -> null
    }}

  # {role} will be created
  + resource "aws_iam_role" "ci" {{
      + name = "ci-runner"
    }}

Plan: {adds} to add, {changes} to change, {destroys} to destroy.
""")
    ctx.data.update(add=adds, change=changes, destroy=destroys, db=db, tmp=tmp, sg=sg, attr=attr, drift_to=drift_to)
    ctx.write('requirements.txt', f"plan.txtはterraform planの出力（途中に、Terraform外で変更された drift の報告を含む）。answer.jsonに add, change, destroy（末尾の Plan: 行の数）、replaced（\"must be replaced\" のアドレス配列）、destroyed_only（置換ではなく単に削除されるアドレス配列）、drift_resource（Terraform外で変更されたアドレス）、drift_attr、drift_to（その属性の変更後の値、文字列）を書く。cmds.txtに2行: drift_resource の state の中身を見る terraform state show、そして実インフラは変えずにdriftの内容だけをstateに取り込む terraform apply -refresh-only。\n")


def c13(ctx):
    need_ro(ctx)
    d, a = ctx.data, rj(ctx, 'answer.json')
    want = dict(add=d['add'], change=d['change'], destroy=d['destroy'], replaced=[d['db']], destroyed_only=[d['tmp']], drift_resource=d['sg'], drift_attr=d['attr'], drift_to=d['drift_to'])
    for k, v in want.items():
        ctx.require(a.get(k) == v, f'answer.jsonの{k}がplan.txtと一致しません。')
    ls = cmd_lines(ctx, 'cmds.txt', 2)
    ctx.require(ls[0][:3] == ['terraform', 'state', 'show'] and ls[0][3:] == [d['sg']], '1行目: terraform state show アドレス')
    ctx.require(ls[1][:2] == ['terraform', 'apply'] and '-refresh-only' in ls[1] and '-auto-approve' not in ls[1], '2行目: terraform apply -refresh-only（確認なし実行は付けない）')


mission(13, 'Terraformのplan/apply出力・state・driftを読む',
        'terraform plan の出力は、drift（手動変更）の報告と、これから行う変更（+ 作成、~ 変更、- 削除、-/+ 置換）で構成されます。applyする前に、何が消えて何が作り直されるかを読み取ってください。stateの確認と、driftだけをstateに反映する手順も書きます。',
        ['answer.jsonに読み取り結果を書く', 'cmds.txtにstate確認とrefresh-onlyを書く'], s13, c13,
        """printf '{"add":<<add>>,"change":<<change>>,"destroy":<<destroy>>,"replaced":["<<db>>"],"destroyed_only":["<<tmp>>"],"drift_resource":"<<sg>>","drift_attr":"<<attr>>","drift_to":"<<drift_to>>"}\\n' > answer.json
printf '%s\\n' 'terraform state show <<sg>>' 'terraform apply -refresh-only' > cmds.txt""",
        ["printf '{\"add\":1,\"change\":1,\"destroy\":1}\\n' > answer.json\necho 'terraform apply -auto-approve' > cmds.txt",
         "printf '{\"add\":<<add>>,\"change\":<<change>>,\"destroy\":<<destroy>>,\"replaced\":[\"<<tmp>>\"],\"destroyed_only\":[\"<<db>>\"],\"drift_resource\":\"<<sg>>\",\"drift_attr\":\"<<attr>>\",\"drift_to\":\"<<drift_to>>\"}\\n' > answer.json\nprintf '%s\\n' 'terraform state show <<sg>>' 'terraform apply -refresh-only' > cmds.txt"],
        'Planの数え方は、置換(-/+)が「1つ作成＋1つ削除」として加算される点が重要です。「forces replacement」の付いた属性変更はデータを持つリソース（DBなど）で事故になります。stateはTerraformが把握する現在の状態で、terraform state list / show で見られます。driftはstateと実際の状態のズレで、plan の冒頭 "Objects have changed outside of Terraform" に出ます。コードを正とするなら通常のapplyで元に戻し、実環境を正とするならコードを直すか terraform apply -refresh-only でstateだけを更新します。本番では plan -out=tfplan して、保存した計画だけを terraform apply tfplan で適用します。',
        'Plan行の数え方を確認します。', 'planの記号（+ ~ - -/+）を数え、置換の二重計上に注意します。')


# ================================================================ 14 prometheus
def s14(ctx):
    h1, h2 = 'node1.lab', 'node2.lab'
    thr, itv = 5 * (1 + secrets.randbelow(5)), secrets.choice([15, 30, 60])
    ctx.data.update(h1=h1, h2=h2, thr=thr, itv=itv)
    ctx.write('prometheus.yml', "global:\n  scrape_interval: 1m\nscrape_configs:\n  - job_name: prometheus\n    static_configs:\n      - targets: ['localhost:9090']\n")
    ctx.write('requirements.txt', f"監視スタックを組む。(1) prometheus.yml に、node_exporter（既定ポート9100）を2台({h1}, {h2})収集する job_name: node（scrape_interval {itv}s）を足し、rule_files に alert.rules.yml、alerting の alertmanagers に alertmanager:9093 を追加する（既存jobは残す）。(2) alert.rules.yml に alert rule: グループ名 node、alert: LowMemory、expr は MemAvailable が MemTotal の{thr}%未満（node_memory_MemAvailable_bytes と node_memory_MemTotal_bytes を使う）、for: 5m、labels の severity: warning。(3) promql.txt に1行のPromQL: インスタンス別のCPU使用率%（node_cpu_seconds_total の mode=\"idle\" のrate([5m])を使い 100 から引く）。(4) grafana-datasource.yml にGrafanaのプロビジョニング（apiVersion 1、datasourceに Prometheus、type prometheus、url http://prometheus:9090、access proxy、isDefault true）。(5) check.txtに promtool check config prometheus.yml と promtool check rules alert.rules.yml の2行。\n")


def c14(ctx):
    d = ctx.data
    p = yload(ctx, 'prometheus.yml')
    jobs = {j.get('job_name'): j for j in (p.get('scrape_configs') or []) if isinstance(j, dict)}
    ctx.require('prometheus' in jobs, '既存のjob_name: prometheus は残します。')
    n = jobs.get('node')
    ctx.require(n is not None and sorted(g(n, 'static_configs', 0, 'targets') or []) == sorted([d['h1'] + ':9100', d['h2'] + ':9100']), 'job node のtargetsに node_exporter（:9100）を2台書きます。')
    ctx.require(str(n.get('scrape_interval')) == f"{d['itv']}s", f'scrape_intervalを{d["itv"]}sにします。')
    ctx.require(p.get('rule_files') == ['alert.rules.yml'], 'rule_filesに alert.rules.yml を書きます。')
    ctx.require('alertmanager:9093' in (g(p, 'alerting', 'alertmanagers', 0, 'static_configs', 0, 'targets') or []), 'alertingにalertmanager:9093を書きます。')
    r = yload(ctx, 'alert.rules.yml')
    gr = g(r, 'groups', 0)
    ctx.require(g(gr, 'name') == 'node', 'グループ名は node です。')
    rule = g(gr, 'rules', 0) or {}
    ctx.require(rule.get('alert') == 'LowMemory' and str(rule.get('for')) == '5m' and g(rule, 'labels', 'severity') == 'warning', 'alert/for/labels.severity を指定します。')
    e = re.sub(r'\s+', '', str(rule.get('expr')))
    ctx.require('node_memory_MemAvailable_bytes' in e and 'node_memory_MemTotal_bytes' in e and '/' in e, 'exprにMemAvailableとMemTotalの比を使います。')
    ctx.require(re.search(r'<%d\b' % d['thr'], e) and (re.search(r'\*100<%d\b' % d['thr'], e) or re.search(r'<0\.%02d\b|<0\.%d\b' % (d['thr'], d['thr'] // 10), e) or '*100<' in e), f'{d["thr"]}%未満の条件にします（比に100を掛けて比較）。')
    q = re.sub(r'\s+', '', ctx.need_file('promql.txt').strip())
    ctx.require(len(ctx.need_file('promql.txt').strip().splitlines()) == 1, 'PromQLは1行です。')
    ctx.require('node_cpu_seconds_total{mode="idle"}' in q and 'rate(' in q and '[5m]' in q and re.search(r'avgby\(instance\)', q) and q.startswith('100-'), 'CPU使用率は 100 - avg by (instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100 の形です。')
    gf = yload(ctx, 'grafana-datasource.yml')
    ds = g(gf, 'datasources', 0) or {}
    ctx.require(gf.get('apiVersion') == 1 and ds.get('name') == 'Prometheus' and ds.get('type') == 'prometheus' and ds.get('url') == 'http://prometheus:9090' and ds.get('access') == 'proxy' and ds.get('isDefault') is True, 'Grafanaのdatasource設定が不足しています。')
    ls = cmd_lines(ctx, 'check.txt', 2)
    ctx.require(ls[0] == ['promtool', 'check', 'config', 'prometheus.yml'] and ls[1] == ['promtool', 'check', 'rules', 'alert.rules.yml'], 'promtool check config / rules の2行です。')


mission(14, 'Prometheusのscrape・alert rule・PromQLとGrafanaを設定する',
        'Prometheusは設定ファイルprometheus.ymlでscrape対象を決めます。サーバの指標を出すnode_exporterを収集し、アラート条件（alert rule）を書き、PromQLでCPU使用率を求め、Grafanaから見られるようにしてください。設定の検査はpromtoolで行います。',
        ['prometheus.ymlを編集', 'alert.rules.ymlとpromql.txtを書く', 'Grafanaのdatasourceとpromtool手順'], s14, c14,
        """cat > prometheus.yml <<'EOF'
global:
  scrape_interval: 1m
rule_files:
  - alert.rules.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ['localhost:9090']
  - job_name: node
    scrape_interval: <<itv>>s
    static_configs:
      - targets: ['<<h1>>:9100', '<<h2>>:9100']
EOF
cat > alert.rules.yml <<'EOF'
groups:
  - name: node
    rules:
      - alert: LowMemory
        expr: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100 < <<thr>>
        for: 5m
        labels:
          severity: warning
EOF
echo '100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100' > promql.txt
cat > grafana-datasource.yml <<'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF
printf '%s\\n' 'promtool check config prometheus.yml' 'promtool check rules alert.rules.yml' > check.txt""",
        ["printf 'global:\\n  scrape_interval: 1m\\nscrape_configs:\\n  - job_name: node\\n    static_configs:\\n      - targets: [\"<<h1>>:9100\"]\\n' > prometheus.yml",
         "echo 'rate(node_cpu_seconds_total[5m])' > promql.txt"],
        'Prometheusはpull型で、prometheus.ymlのscrape_configsにあるtargetsへ定期的にHTTPで指標を取りに行きます。node_exporterはLinuxホストのCPU・メモリ・ディスクを :9100/metrics で公開します。alert ruleはPromQLの式exprが真の状態がforの期間続くとalertを発火し、Alertmanagerへ通知します。node_cpu_seconds_total は累積カウンタなので rate() で毎秒の増加量にし、idleを100から引くと使用率になります。Grafanaはdatasourceとして Prometheus を登録し、PromQLでダッシュボードを描きます。設定変更前に promtool check config と check rules で検査します。',
        'カウンタは累積値なのでrateが必要です。', 'YAMLはヒアドキュメントで書き、PromQLはechoで1行にします。')


# ================================================================ 15 compose
def s15(ctx):
    pw = secrets.token_urlsafe(18)
    tag = f'1.{secrets.randbelow(9)}.{secrets.randbelow(9)}'
    ctx.data.update(pw=pw, tag=tag)
    ctx.write('secrets/db_password.txt', pw + '\n', mode=0o600)
    ctx.write('compose.yml', f"services:\n  web:\n    image: registry.example.com/shop/web:latest\n    ports:\n      - \"80:8080\"\n    depends_on:\n      - db\n  db:\n    image: postgres:16\n    ports:\n      - \"5432:5432\"\n    environment:\n      POSTGRES_PASSWORD: {pw}\n    volumes:\n      - ./pgdata:/var/lib/postgresql/data\n")
    ctx.write('requirements.txt', f"開発用のcompose.ymlを本番向けに直す。web: イメージを latest ではなく {tag} に固定。db: 5432をホストへ公開しない（portsを削除）、パスワードの直書きをやめ secrets（file: ./secrets/db_password.txt、secret名 db_password）を使い POSTGRES_PASSWORD_FILE=/run/secrets/db_password を設定、データは名前付きボリューム db-data（トップレベルvolumesで宣言）、healthcheck（test: [\"CMD-SHELL\", \"pg_isready -U postgres\"]、interval 10s）を追加。web は depends_on の db に condition: service_healthy。両サービスに restart: unless-stopped、logging（driver json-file、options の max-size 10m）。他は変えない。cmd.txtに構文検査の docker compose config -q を書く（実行しない）。\n")


def c15(ctx):
    d = ctx.data
    t = ctx.need_file('compose.yml')
    ctx.require(d['pw'] not in t, 'パスワードをcompose.ymlに直書きしません。')
    y = yload(ctx, 'compose.yml')
    web, db = g(y, 'services', 'web') or {}, g(y, 'services', 'db') or {}
    ctx.require(web.get('image') == f'registry.example.com/shop/web:{d["tag"]}', 'webのイメージタグを固定します。')
    ctx.require(web.get('ports') == ['80:8080'], 'webのportsは変えません。')
    ctx.require('ports' not in db, 'dbのportsは公開しません（同じネットワーク内から接続できます）。')
    env = db.get('environment') or {}
    if isinstance(env, list):
        env = dict(x.split('=', 1) for x in env if '=' in x)
    ctx.require(env.get('POSTGRES_PASSWORD_FILE') == '/run/secrets/db_password' and 'POSTGRES_PASSWORD' not in env, 'POSTGRES_PASSWORD_FILE を使い POSTGRES_PASSWORD は消します。')
    ctx.require('db_password' in (db.get('secrets') or []) and g(y, 'secrets', 'db_password', 'file') == './secrets/db_password.txt', 'secrets を定義してdbに渡します。')
    ctx.require(db.get('volumes') == ['db-data:/var/lib/postgresql/data'] and 'db-data' in (y.get('volumes') or {}), '名前付きボリューム db-data をトップレベルvolumesに宣言して使います。')
    hc = db.get('healthcheck') or {}
    ctx.require(hc.get('test') == ['CMD-SHELL', 'pg_isready -U postgres'] and str(hc.get('interval')) == '10s', 'dbにhealthcheckを追加します。')
    ctx.require(g(web, 'depends_on', 'db', 'condition') == 'service_healthy', 'webのdepends_onで condition: service_healthy を指定します。')
    for n, s in (('web', web), ('db', db)):
        ctx.require(s.get('restart') == 'unless-stopped', f'{n} に restart: unless-stopped を指定します。')
        ctx.require(g(s, 'logging', 'driver') == 'json-file' and str(g(s, 'logging', 'options', 'max-size')) == '10m', f'{n} のloggingでログ肥大を防ぎます。')
    ls = cmd_lines(ctx, 'cmd.txt', 1)[0]
    ctx.require(ls[:3] == ['docker', 'compose', 'config'] and any(x in ls for x in ('-q', '--quiet')), 'docker compose config -q で検査します。')
    ctx.require(ctx.need_file('secrets/db_password.txt').strip() == d['pw'], 'secretsファイルは変更しません。')


mission(15, 'Docker Composeを本番向けに直す（secrets・healthcheck・restart）',
        '開発用のDocker Compose設定を、本番で使える形に直します。バージョン固定、DBポートの非公開、パスワードのsecrets化、healthcheckと起動順序の制御、再起動方針、ログの肥大防止、名前付きボリュームが課題です。',
        ['compose.ymlを本番向けに直す', '検査コマンドをcmd.txtへ'], s15, c15,
        """cat > compose.yml <<'EOF'
services:
  web:
    image: registry.example.com/shop/web:<<tag>>
    ports:
      - "80:8080"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: 10m
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: 10m
secrets:
  db_password:
    file: ./secrets/db_password.txt
volumes:
  db-data:
EOF
echo 'docker compose config -q' > cmd.txt""",
        ["sed -i 's/:latest/:<<tag>>/' compose.yml\necho 'docker compose config -q' > cmd.txt",
         "sed -i '/5432:5432/d' compose.yml\nsed -i 's/POSTGRES_PASSWORD:.*/POSTGRES_PASSWORD: changeme/' compose.yml\necho 'docker compose config -q' > cmd.txt"],
        'latestタグは再現性がなく、いつの間にか別のバージョンになります。DBのポートを公開すると外部から到達できる恐れがあり、同じComposeネットワーク内の名前(db:5432)で足ります。パスワードを環境変数に直書きするとdocker inspectやGitに残るため、secretsのファイルを /run/secrets/ にマウントします（ファイルは.gitignoreに）。depends_onは起動順だけで、healthcheckとcondition: service_healthyで準備完了を待ちます。restart: unless-stoppedで障害や再起動から復帰し、json-fileのmax-sizeでディスク枯渇を防ぎます。検査は docker compose config -q です。',
        '開発用の便利な設定ほど本番では危険です。', 'compose.ymlをヒアドキュメントで書き直し、secretsとhealthcheckを足します。')


# ================================================================ 16 GitHub Actions
def s16(ctx):
    tok = 'ghp_' + secrets.token_urlsafe(27).replace('-', 'A').replace('_', 'B')
    ctx.data.update(tok=tok)
    lines = ["name: ci", "on:", "  pull_request_target:", "  push:", "    branches: [main]", "jobs:", "  test:", "    runs-on: ubuntu-latest", "    steps:",
             "      - uses: actions/checkout@main", "      - uses: actions/setup-node@v4", "      - run: npm ci && npm test",
             "  deploy:", "    runs-on: ubuntu-latest", "    needs: test", "    env:", f"      DEPLOY_TOKEN: {tok}", "    steps:",
             "      - uses: actions/checkout@master", "      - run: ./deploy.sh"]
    put(ctx, 'ci.orig.yml', '\n'.join(lines) + '\n')
    ctx.data['tokline'] = lines.index(f'      DEPLOY_TOKEN: {tok}') + 1
    ctx.write('requirements.txt', "ci.orig.ymlはGitHub ActionsのCI/CDパイプライン。findings.jsonに hardcoded_token_line（秘密情報が直書きされた行番号、1始まり）、unpinned（@main・@master など動く参照で使われている uses の値の配列、昇順）、risky_trigger（フォークのPRから秘密情報に触れうる on のトリガー名）を書く。ci.yml に修正版を書く: トリガーは pull_request と main への push、トップレベル permissions は contents: read のみ、トークンは secrets.DEPLOY_TOKEN から ${{ secrets.DEPLOY_TOKEN }} で渡し直書きしない、uses は @v4 などのバージョンタグに固定（checkoutは actions/checkout@v4）、deployジョブは if: github.ref == 'refs/heads/main' かつ environment: production。なお秘密情報はリポジトリのSettingsのSecretsに登録する（ここでは登録しない）。\n")


def c16(ctx):
    need_ro(ctx)
    d, f = ctx.data, rj(ctx, 'findings.json')
    ctx.require(f.get('hardcoded_token_line') == d['tokline'], 'hardcoded_token_line が違います。')
    ctx.require(f.get('unpinned') == ['actions/checkout@main', 'actions/checkout@master'], 'unpinnedは動く参照の uses の値を昇順で書きます。')
    ctx.require(f.get('risky_trigger') == 'pull_request_target', 'risky_triggerが違います。')
    t = ctx.need_file('ci.yml')
    ctx.require(d['tok'] not in t and not re.search(r'ghp_\w{10,}', t), 'トークンを直書きしません。')
    y = yload(ctx, 'ci.yml')
    on = y.get('on')
    trig = set(on) if isinstance(on, (dict, list)) else {on}
    ctx.require(trig == {'pull_request', 'push'} and g(on, 'push', 'branches') == ['main'], 'トリガーは pull_request と main への push だけにします。')
    ctx.require(y.get('permissions') == {'contents': 'read'}, 'トップレベルpermissionsを contents: read にします。')
    uses = []
    for j in (y.get('jobs') or {}).values():
        for s in j.get('steps') or []:
            if isinstance(s, dict) and 'uses' in s:
                uses.append(s['uses'])
    ctx.require('actions/checkout@v4' in uses and uses and all(re.search(r'@(v\d[\w.]*|[0-9a-f]{40})$', u) for u in uses), 'すべてのusesをバージョンタグ（@v4等）かコミットSHAに固定します。')
    dep = g(y, 'jobs', 'deploy') or {}
    ctx.require(g(dep, 'env', 'DEPLOY_TOKEN') == '${{ secrets.DEPLOY_TOKEN }}', 'DEPLOY_TOKENは ${{ secrets.DEPLOY_TOKEN }} で渡します。')
    ctx.require(str(dep.get('if')).replace(' ', '') in ("github.ref=='refs/heads/main'", "${{github.ref=='refs/heads/main'}}") and dep.get('environment') == 'production', 'deployにifとenvironment: productionを付けます。')
    ctx.require(dep.get('needs') == 'test' and g(y, 'jobs', 'test', 'runs-on') == 'ubuntu-latest', 'testジョブとneedsは変えません。')


mission(16, 'GitHub ActionsのCI/CDを読み、秘密情報を安全に扱う',
        'CI/CDパイプラインはリポジトリに置いたGitHub ActionsのYAMLで定義します。ci.orig.ymlには、秘密情報の直書き、フォークから実行されうるトリガー、バージョン固定のないactionがあります。リスクを読み取り、安全な修正版を書いてください。',
        ['findings.jsonにリスクをまとめる', 'ci.ymlを修正する'], s16, c16,
        """printf '{"hardcoded_token_line":<<tokline>>,"unpinned":["actions/checkout@main","actions/checkout@master"],"risky_trigger":"pull_request_target"}\\n' > findings.json
cat > ci.yml <<'EOF'
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci && npm test
  deploy:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    environment: production
    env:
      DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - run: ./deploy.sh
EOF""",
        ["sed 's/actions\\/checkout@main/actions\\/checkout@v4/' ci.orig.yml > ci.yml\nprintf '{}\\n' > findings.json",
         "printf '{\"hardcoded_token_line\":<<tokline>>,\"unpinned\":[\"actions/checkout@main\",\"actions/checkout@master\"],\"risky_trigger\":\"pull_request_target\"}\\n' > findings.json\ncp ci.orig.yml ci.yml"],
        'pull_request_targetは基盤リポジトリの権限とSecretsで動くため、フォークのPRのコードをチェックアウトして実行すると秘密情報を奪われます。通常は pull_request を使います。トークンをYAMLに書くとGit履歴に永久に残るので、リポジトリやEnvironmentのSecretsに登録して ${{ secrets.名前 }} で参照し、漏れた分は直ちに失効・再発行します。permissionsは最小権限（contents: read）にし、uses は @main のような動く参照を避けてタグかコミットSHAに固定します（サプライチェーン攻撃対策）。environment: production に承認ルールを付ければ、本番デプロイを人の承認で止められます。',
        '誰のコードが秘密情報の近くで動くかを考えます。', 'YAMLを読み、ヒアドキュメントで修正版を書きます。')
