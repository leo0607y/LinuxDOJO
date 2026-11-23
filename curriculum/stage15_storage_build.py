"""Stage 15: ストレージ構築（パーティション設計・mkfs/fstab・LVM・RAID・swap・fsck・quota・dd・SMART）。

すべて作業フォルダ内の採取済みデータ・設定控え・ダミーファイルで行い、
実デバイスの変更や実マウント、root権限は使いません。
"""
import hashlib
import json
import random
import re
import secrets
import uuid as uuidlib

from engine.runner import register

S = 15
NOTE = ("この課題は作業フォルダ内の採取データと設定控え・ダミーファイルだけを扱います。"
        "本物のディスク・マウント・LVM・RAIDは変更しません。")


def base(ctx):
    ctx.write('SCOPE.txt', NOTE + '\n')


def jload(ctx, path):
    import json as _j
    try:
        v = _j.loads(ctx.need_file(path))
    except (ValueError, TypeError):
        ctx.fail(f'{path} を有効なJSONで保存してください。')
    ctx.require(isinstance(v, dict), f'{path} はJSONオブジェクトです。')
    return v


def sha(ctx, path):
    return hashlib.sha256(ctx.p(path).read_bytes()).hexdigest()


def preserve(ctx, *paths):
    ctx.data['originals'] = {p: sha(ctx, p) for p in paths}


def unchanged(ctx, *paths):
    for p in paths:
        ctx.require(ctx.isfile(p) and not ctx.p(p).is_symlink(), f'{p} の原本を維持してください。')
        ctx.require(sha(ctx, p) == ctx.data['originals'][p], f'{p} の原本を変えずに調査してください。')


def cmds(ctx, path):
    out = []
    for ln in ctx.need_file(path).splitlines():
        ln = ln.strip()
        if ln and not ln.startswith('#'):
            out.append(ln.split())
    return out


def idx(lines, pred):
    for i, t in enumerate(lines):
        if pred(t):
            return i
    return -1


def fstab_rows(ctx, path='fstab'):
    return [x.split() for x in ctx.need_file(path).splitlines() if x.strip() and not x.lstrip().startswith('#')]


def add(n, title, story, objectives, setup, check, solution, wrong, explanation, tip=None, hints=None):
    register(id=f'15-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives,
             hints=hints or ['まず要件と観測した事実を分け、必要な値と出力先を整理します。',
                    'ls で資料を一覧し、cat で要件書と採取記録を読みます。元の採取データは変更せず、値はデータから読み取ります。',
                    'answer で入力例を確認できます。形式は requirements.txt に従います。'],
             answer=solution, explanation=explanation,
             tip=tip or '実機では実行前に対象デバイスを必ず確認し、まず控えや計画書で手順と順序をレビューします。',
             setup=setup, check=check, solution=solution, wrong=wrong)


# ---------------------------------------------------------------- 1 fdisk
def s1(ctx):
    base(ctx)
    r = random.Random(secrets.randbits(32))
    sizes = [r.choice([1, 2, 4]) * 2048 * 256 for _ in range(3)]  # 128/256/512MiB単位
    total = 2048 * r.randint(4000, 9000)
    cur = 2048
    rows = []
    for i, s in enumerate(sizes, 1):
        rows.append((i, cur, cur + s - 1, s))
        cur += s
    ctx.data.update(free_start=cur, free_sectors=total - cur, free_mib=(total - cur) // 2048,
                    next_part='sdb4', last_part='sdb3', total=total)
    lines = [f'Disk /dev/sdb: {total * 512 // 2**20} MiB, {total * 512} bytes, {total} sectors',
             'Units: sectors of 1 * 512 = 512 bytes', 'Disklabel type: gpt', '',
             'Device       Start      End  Sectors Type']
    for i, a, b, s in rows:
        lines.append(f'/dev/sdb{i} {a:>10} {b:>10} {s:>10} Linux filesystem')
    ctx.write('capture/fdisk-l.txt', '\n'.join(lines) + '\n')
    ctx.write('requirements.txt', 'result.json: last_partition(最後のパーティション名 sdbN), free_start(空き開始セクタ), '
              'free_sectors(空きセクタ数。ディスク末尾まで), free_mib(空きMiB整数), next_partition(次に作る名前)。\n')
    preserve(ctx, 'capture/fdisk-l.txt')


def c1(ctx):
    unchanged(ctx, 'capture/fdisk-l.txt')
    d = ctx.data
    exp = dict(last_partition=d['last_part'], free_start=d['free_start'], free_sectors=d['free_sectors'],
               free_mib=d['free_mib'], next_partition=d['next_part'])
    ctx.require(jload(ctx, 'result.json') == exp, 'result.json の値が出力と一致しません。最終パーティションのEndの次が空き開始、ディスク全体のセクタ数との差が空きです。')


SOL1 = r"""python3 - <<'PYCODE'
import re, json
t=open('capture/fdisk-l.txt').read()
total=int(re.search(r'(\d+) sectors',t).group(1))
ps=[l.split() for l in t.splitlines() if l.startswith('/dev/sdb')]
last=ps[-1]; fs=int(last[2])+1
json.dump(dict(last_partition=last[0].split('/')[-1],free_start=fs,free_sectors=total-fs,free_mib=(total-fs)//2048,
 next_partition='sdb%d'%(len(ps)+1)),open('result.json','w'))
PYCODE"""
add(1, 'fdiskの出力から空き領域を読み解く', 'fdisk -l の採取結果から、新しいパーティションを作れる空きを計算します。',
    ['fdiskの採取記録を変更しない', '最終パーティションと空き領域を result.json に記録'], s1, c1, SOL1,
    ["echo '{}' > result.json",
     """python3 - <<'PYCODE'
import re, json
t=open('capture/fdisk-l.txt').read()
total=int(re.search(r'(\\d+) sectors',t).group(1))
ps=[l.split() for l in t.splitlines() if l.startswith('/dev/sdb')]
fs=int(ps[-1][2])
json.dump(dict(last_partition=ps[-1][0].split('/')[-1],free_start=fs,free_sectors=total-fs,free_mib=(total-fs)//2048,next_partition='sdb%d'%(len(ps)+1)),open('result.json','w'))
PYCODE"""],
    'Endは最終セクタ番号なので、次の空きは End+1 から始まります（1ずれの落とし穴）。1セクタ=512バイト、2048セクタ=1MiBでアラインメントします。')


# ---------------------------------------------------------------- 2 mkfs mount fstab
def s2(ctx):
    base(ctx)
    u = str(uuidlib.uuid4()); lab = 'data' + secrets.token_hex(2); dev = 'loop' + str(random.randint(10, 40))
    ctx.data.update(uuid=u, label=lab, dev=dev)
    ctx.write('capture/blkid.txt', f'/dev/{dev}: LABEL="{lab}" UUID="{u}" TYPE="ext4"\n')
    ctx.write('fstab', 'UUID=root-fixture / ext4 defaults 0 1\n')
    ctx.data['root'] = 'UUID=root-fixture / ext4 defaults 0 1'
    ctx.write('requirements.txt', f'新しいディスク /dev/{dev} (ファイルシステム未作成) を /mnt/{lab} にext4で永続マウントする。\n'
              'plan.txt に実行順のコマンドを1行ずつ(mkfs.ext4 -L <label>, mkdir -p, mount)書く。mkfsは作成後blkidで得たUUIDが分かる想定で、'
              'fstab(控え)にはroot行を残し、UUID指定・ext4・defaults,noatime・dump=0・pass=2 の行を追加する。実行はしない。\n')
    preserve(ctx, 'capture/blkid.txt')


def c2(ctx):
    unchanged(ctx, 'capture/blkid.txt')
    d = ctx.data; L = cmds(ctx, 'plan.txt')
    a = idx(L, lambda t: t[0] == 'mkfs.ext4' and t[-1] == '/dev/' + d['dev'] and '-L' in t and t[t.index('-L') + 1] == d['label'])
    b = idx(L, lambda t: t[:2] == ['mkdir', '-p'] and t[-1] == '/mnt/' + d['label'])
    m = idx(L, lambda t: t[0] == 'mount' and t[-1] == '/mnt/' + d['label'] and ('/dev/' + d['dev']) in t)
    ctx.require(a >= 0, 'mkfs.ext4 -L <label> /dev/<dev> の行がありません。')
    ctx.require(b > a, 'mkfsの後にマウントポイント作成(mkdir -p)が必要です。')
    ctx.require(m > b, 'マウントポイント作成の後に mount を書きます。')
    rows = fstab_rows(ctx)
    ctx.require(len(rows) == 2 and ' '.join(rows[0]) == d['root'], 'fstabはroot行を残し、追加は1行だけにします。')
    r = rows[1]
    ctx.require(len(r) == 6 and r[:3] == ['UUID=' + d['uuid'], '/mnt/' + d['label'], 'ext4'], 'UUID・マウント先・種類を確認しましょう。')
    ctx.require(set(r[3].split(',')) == {'defaults', 'noatime'} and r[4:] == ['0', '2'], 'オプションとdump/passを確認しましょう。')


SOL2 = """printf '%s\\n' 'mkfs.ext4 -L <<label>> /dev/<<dev>>' 'mkdir -p /mnt/<<label>>' 'mount /dev/<<dev>> /mnt/<<label>>' > plan.txt
u=$(sed -n 's/.*UUID="\\([^"]*\\)".*/\\1/p' capture/blkid.txt)
echo "UUID=$u /mnt/<<label>> ext4 defaults,noatime 0 2" >> fstab"""
add(2, 'mkfs→mount→fstabの一連手順を設計する', '新しいディスクを使えるようにし、再起動後も残す一連の手順を書面で組み立てます。',
    ['plan.txt に正しい順序でコマンドを書く', 'fstab控えへUUID指定の行を追加'], s2, c2, SOL2,
    ["printf '%s\\n' 'mount /dev/<<dev>> /mnt/<<label>>' 'mkfs.ext4 -L <<label>> /dev/<<dev>>' 'mkdir -p /mnt/<<label>>' > plan.txt",
     "printf '%s\\n' 'mkfs.ext4 -L <<label>> /dev/<<dev>>' 'mkdir -p /mnt/<<label>>' 'mount /dev/<<dev>> /mnt/<<label>>' > plan.txt; echo '/dev/<<dev>> /mnt/<<label>> ext4 defaults 0 0' >> fstab"],
    '順序は mkfs（ファイルシステム作成）→ mkdir（マウントポイント）→ mount → fstab追記です。fstabにはデバイス名よりUUIDを使い、ブート時の列挙順変化に備えます。mkfsは既存データを消すため、対象デバイス確認が最重要です。')


# ---------------------------------------------------------------- 3 LVM build
def s3(ctx):
    base(ctx)
    vg = 'vg_' + secrets.token_hex(2); lv = random.choice(['data', 'web', 'db']) + secrets.token_hex(1)
    d1, d2 = random.sample(['sdb', 'sdc', 'sdd', 'sde'], 2); size = random.choice([512, 768, 1024, 2048])
    ctx.data.update(vg=vg, lv=lv, d1=d1, d2=d2, size=size)
    ctx.write('requirements.txt', f'/dev/{d1} と /dev/{d2} から、VG {vg}、LV {lv}({size}MiB, ext4) を作り /srv/{lv} へマウントする手順を plan.txt に書く'
              '(1行1コマンド): pvcreate(2台) → vgcreate → lvcreate -L <size>M -n → mkfs.ext4 /dev/<vg>/<lv> → mkdir -p → mount。実行はしない。\n')


def c3(ctx):
    d = ctx.data; L = cmds(ctx, 'plan.txt'); dv = [f'/dev/{d["d1"]}', f'/dev/{d["d2"]}']
    pv = [i for i, t in enumerate(L) if t[0] == 'pvcreate' and set(t[1:]) <= set(dv)]
    ctx.require(len(pv) >= 1 and {x for i in pv for x in L[i][1:]} == set(dv), 'pvcreate で2台とも物理ボリューム化します。')
    vgi = idx(L, lambda t: t[0] == 'vgcreate' and t[1] == d['vg'] and set(t[2:]) == set(dv))
    ctx.require(vgi > max(pv), 'pvcreate の後に vgcreate <vg> <2台> を書きます。')
    lvi = idx(L, lambda t: t[0] == 'lvcreate' and d['vg'] in t and '-n' in t and t[t.index('-n') + 1] == d['lv']
              and '-L' in t and t[t.index('-L') + 1].upper() in (f'{d["size"]}M', f'{d["size"]}MIB'))
    ctx.require(lvi > vgi, 'vgcreate の後に lvcreate -L <size>M -n <lv> <vg> を書きます。')
    path = f'/dev/{d["vg"]}/{d["lv"]}'
    mk = idx(L, lambda t: t[0] == 'mkfs.ext4' and t[-1] == path)
    ctx.require(mk > lvi, 'LV作成後に mkfs.ext4 を LV のパスへ実行します。')
    md = idx(L, lambda t: t[:2] == ['mkdir', '-p'] and t[-1] == f'/srv/{d["lv"]}')
    mo = idx(L, lambda t: t[0] == 'mount' and path in t and t[-1] == f'/srv/{d["lv"]}')
    ctx.require(md > mk and mo > md, 'mkdir → mount の順に書きます。')


SOL3 = """printf '%s\\n' 'pvcreate /dev/<<d1>> /dev/<<d2>>' 'vgcreate <<vg>> /dev/<<d1>> /dev/<<d2>>' 'lvcreate -L <<size>>M -n <<lv>> <<vg>>' 'mkfs.ext4 /dev/<<vg>>/<<lv>>' 'mkdir -p /srv/<<lv>>' 'mount /dev/<<vg>>/<<lv>> /srv/<<lv>>' > plan.txt"""
add(3, 'LVMの構築順序を組み立てる', 'LVMは物理ボリューム（PV）をボリュームグループ（VG）にまとめ、そこから論理ボリューム（LV）を切り出します。LVにはファイルシステムを作ってからマウントします。2台のディスクからLVを作り、マウントするまでの正しい順序を計画します。',
    ['PV→VG→LV→mkfs→mountの順で plan.txt を作る'], s3, c3, SOL3,
    ["printf '%s\\n' 'vgcreate <<vg>> /dev/<<d1>> /dev/<<d2>>' 'pvcreate /dev/<<d1>> /dev/<<d2>>' 'lvcreate -L <<size>>M -n <<lv>> <<vg>>' 'mkfs.ext4 /dev/<<vg>>/<<lv>>' 'mkdir -p /srv/<<lv>>' 'mount /dev/<<vg>>/<<lv>> /srv/<<lv>>' > plan.txt",
     "printf '%s\\n' 'pvcreate /dev/<<d1>>' 'vgcreate <<vg>> /dev/<<d1>> /dev/<<d2>>' 'lvcreate -L <<size>>M -n <<lv>> <<vg>>' > plan.txt"],
    'LVMは物理ボリューム(PV)→ボリュームグループ(VG)→論理ボリューム(LV)の順で積み上げます。LVを作った後にファイルシステムを作り、マウントします。')


# ---------------------------------------------------------------- 4 LVM extend
def s4(ctx):
    base(ctx)
    vg = 'vg_' + secrets.token_hex(2); lv = 'data' + secrets.token_hex(1); nd = random.choice(['sdd', 'sde', 'sdf'])
    free = random.choice([64, 100, 128]); grow = random.choice([512, 768, 1024])
    ctx.data.update(vg=vg, lv=lv, nd=nd, grow=grow)
    ctx.write('capture/vgs.txt', f'VG   #PV #LV VSize VFree\n{vg} 1 1 2.00g {free}.00m\n')
    ctx.write('capture/lsblk.txt', f'NAME SIZE TYPE\nsdb 2G disk\n  {vg}-{lv} lvm\n{nd} 4G disk (未使用・PV未作成)\n')
    ctx.write('requirements.txt', f'LV /dev/{vg}/{lv}(ext4) を {grow}MiB 拡張したい。VFreeは足りない。未使用の /dev/{nd} を使う手順を plan.txt に1行1コマンドで書く: '
              'pvcreate → vgextend → lvextend -L +<size>M → resize2fs。実行はしない。\n')
    preserve(ctx, 'capture/vgs.txt', 'capture/lsblk.txt')


def c4(ctx):
    unchanged(ctx, 'capture/vgs.txt', 'capture/lsblk.txt')
    d = ctx.data; L = cmds(ctx, 'plan.txt'); dev = '/dev/' + d['nd']; lvp = f'/dev/{d["vg"]}/{d["lv"]}'
    a = idx(L, lambda t: t[:2] == ['pvcreate', dev] and len(t) == 2)
    b = idx(L, lambda t: t[:3] == ['vgextend', d['vg'], dev])
    e = idx(L, lambda t: t[0] == 'lvextend' and lvp in t and ('-L' in t and t[t.index('-L') + 1].upper() in (f'+{d["grow"]}M', f'+{d["grow"]}MIB')))
    f = idx(L, lambda t: t[0] == 'resize2fs' and t[1] == lvp)
    ctx.require(a >= 0, '新ディスクを pvcreate します。')
    ctx.require(b > a, 'pvcreate の後に vgextend <vg> <dev> でVGへ追加します。')
    ctx.require(e > b, 'VG拡張後に lvextend -L +<size>M <LVパス> を行います。')
    ctx.require(f > e, '最後に resize2fs <LVパス> でファイルシステムを拡張します。')


SOL4 = """printf '%s\\n' 'pvcreate /dev/<<nd>>' 'vgextend <<vg>> /dev/<<nd>>' 'lvextend -L +<<grow>>M /dev/<<vg>>/<<lv>>' 'resize2fs /dev/<<vg>>/<<lv>>' > plan.txt"""
add(4, 'LVの拡張手順を計画する', 'VGの空きが足りないとき、ディスク追加からファイルシステム拡張までの順序を計画します。',
    ['VGの空きを確認', 'pvcreate→vgextend→lvextend→resize2fs の plan.txt を作る'], s4, c4, SOL4,
    ["printf '%s\\n' 'lvextend -L +<<grow>>M /dev/<<vg>>/<<lv>>' 'resize2fs /dev/<<vg>>/<<lv>>' > plan.txt",
     "printf '%s\\n' 'pvcreate /dev/<<nd>>' 'vgextend <<vg>> /dev/<<nd>>' 'resize2fs /dev/<<vg>>/<<lv>>' 'lvextend -L +<<grow>>M /dev/<<vg>>/<<lv>>' > plan.txt"],
    'VFreeが足りなければ、PV作成→VG拡張→LV拡張の順です。LVを拡張してもファイルシステムは自動で広がらないため resize2fs（xfsなら xfs_growfs）が必要です（lvextend -r でも可）。')


# ---------------------------------------------------------------- 5 mdadm
def s5(ctx):
    base(ctx)
    n = random.randint(0, 9); bad = random.choice('bc'); good = 'a' if bad != 'a' else 'b'; spare = 'd'
    ctx.data.update(md=f'md{n}', bad=f'sd{bad}1', spare=f'sd{spare}1')
    mem = [f'sd{bad}1[1](F)', f'sd{good}1[0]'] if random.random() < .5 else [f'sd{good}1[0]', f'sd{bad}1[1](F)']
    ctx.write('capture/mdstat.txt', f'Personalities : [raid1]\nmd{n} : active raid1 {" ".join(mem)}\n      1046528 blocks super 1.2 [2/1] [U_]\n\nunused devices: <none>\n')
    ctx.write('requirements.txt', f'result.json: array, state(degraded|clean), failed(故障デバイス名 sdXN)。recovery.txt: 故障メンバを --remove し、新ディスク /dev/{ctx.data["spare"]} を --add する1行1コマンド(mdadm /dev/<md> --remove/--add)。実行はしない。\n')
    preserve(ctx, 'capture/mdstat.txt')


def c5(ctx):
    unchanged(ctx, 'capture/mdstat.txt'); d = ctx.data
    ctx.require(jload(ctx, 'result.json') == dict(array=d['md'], state='degraded', failed=d['bad']),
                'result.json: [2/1] [U_] は劣化(degraded)、(F)が付いたメンバが故障です。')
    L = cmds(ctx, 'recovery.txt'); arr = '/dev/' + d['md']
    r = idx(L, lambda t: t[0] == 'mdadm' and t[1] == arr and '--remove' in t and t[-1] == '/dev/' + d['bad'])
    a = idx(L, lambda t: t[0] == 'mdadm' and t[1] == arr and '--add' in t and t[-1] == '/dev/' + d['spare'])
    ctx.require(r >= 0, '故障メンバの --remove が必要です。')
    ctx.require(a > r, '取り外し後に新ディスクを --add します。')
    ctx.require(not any('--create' in t or '--zero-superblock' in t for t in L), '--create等の破壊的操作は不要です。')


SOL5 = """python3 - <<'PYCODE'
import re, json
t=open('capture/mdstat.txt').read()
md=re.search(r'^(md\\d+) :',t,re.M).group(1)
bad=re.search(r'(sd\\w+)\\[\\d+\\]\\(F\\)',t).group(1)
json.dump(dict(array=md,state='degraded' if '_' in re.search(r'\\[[U_]+\\]',t).group(0) else 'clean',failed=bad),open('result.json','w'))
PYCODE
printf '%s\\n' 'mdadm /dev/<<md>> --remove /dev/<<bad>>' 'mdadm /dev/<<md>> --add /dev/<<spare>>' > recovery.txt"""
add(5, '/proc/mdstatを読んで劣化RAIDを復旧する', 'RAID1の状態を示す /proc/mdstat の採取結果を読み、復旧手順を書きます。',
    ['RAID状態の採取記録を変更しない', '劣化状態と故障メンバを result.json へ', 'recovery.txt に --remove → --add'], s5, c5, SOL5,
    ["echo '{\"array\":\"<<md>>\",\"state\":\"clean\",\"failed\":\"<<bad>>\"}' > result.json; printf '%s\\n' 'mdadm /dev/<<md>> --add /dev/<<spare>>' 'mdadm /dev/<<md>> --remove /dev/<<bad>>' > recovery.txt",
     "echo '{\"array\":\"<<md>>\",\"state\":\"degraded\",\"failed\":\"<<bad>>\"}' > result.json; printf '%s\\n' 'mdadm --create /dev/<<md>> --level=1 --raid-devices=2 /dev/<<spare>> missing' > recovery.txt"],
    '[2/1] [U_] は2台中1台のみ稼働（Uが稼働、_が欠落）。(F)は故障扱いのメンバです。復旧は --remove で外し、新ディスクを --add すると再同期(recovery)が始まります。--create は既存データを壊す恐れがあります。')


# ---------------------------------------------------------------- 6 swap
def s6(ctx):
    base(ctx)
    mb = random.choice([8, 12, 16]); sw = random.choice([10, 20, 30, 40])
    ctx.data.update(mb=mb, sw=sw)
    ctx.write('fstab', 'UUID=root-fixture / ext4 defaults 0 1\n')
    ctx.data['root'] = 'UUID=root-fixture / ext4 defaults 0 1'
    ctx.write('requirements.txt', f'作業フォルダ内で swap を追加する練習。swapfile を {mb}MiB のファイル(dd使用, 内容はゼロ)として作り、権限を600にし、mkswapの控えとしてplan.txtに '
              f'"mkswap /swapfile" と "swapon /swapfile" の順で書く。fstab(控え)にroot行を残し "/swapfile none swap sw 0 0" を追加。sysctl.conf に vm.swappiness={sw} を書く。\n')


def c6(ctx):
    d = ctx.data; p = ctx.p('swapfile')
    ctx.require(ctx.isfile('swapfile') and not p.is_symlink(), 'swapfile を作成してください。')
    ctx.require(p.stat().st_size == d['mb'] * 2**20, f'swapfile は {d["mb"]}MiB ちょうどです。')
    ctx.require(p.stat().st_mode & 0o777 == 0o600, 'swapfile の権限は600にします（他ユーザに読ませない）。')
    ctx.require(p.read_bytes().count(b'\0') == p.stat().st_size, 'swapfile の内容はゼロで埋めます。')
    L = cmds(ctx, 'plan.txt')
    a = idx(L, lambda t: t == ['mkswap', '/swapfile']); b = idx(L, lambda t: t == ['swapon', '/swapfile'])
    ctx.require(a >= 0 and b > a, 'plan.txt: mkswap の後に swapon の順で書きます。')
    rows = fstab_rows(ctx)
    ctx.require(len(rows) == 2 and ' '.join(rows[0]) == d['root'] and rows[1] == ['/swapfile', 'none', 'swap', 'sw', '0', '0'], 'fstabにroot行とswap行(6項目)を置きます。')
    t = ctx.need_file('sysctl.conf')
    vals = re.findall(r'^\s*vm\.swappiness\s*=\s*(\d+)\s*$', t, re.M)
    ctx.require(vals == [str(d['sw'])], f'sysctl.conf に vm.swappiness={d["sw"]} を1行だけ書きます。')


SOL6 = """dd if=/dev/zero of=swapfile bs=1M count=<<mb>> status=none
chmod 600 swapfile
printf '%s\\n' 'mkswap /swapfile' 'swapon /swapfile' > plan.txt
echo '/swapfile none swap sw 0 0' >> fstab
echo 'vm.swappiness=<<sw>>' > sysctl.conf"""
add(6, 'swapファイルとswappinessを設定する', 'ダミーのswapファイルを作り、永続化設定と swappiness の控えを用意します。',
    ['ゼロ埋め・権限600のswapfile', 'plan.txtの順序、fstab、sysctl.conf'], s6, c6, SOL6,
    ["dd if=/dev/zero of=swapfile bs=1M count=<<mb>> status=none; printf '%s\\n' 'mkswap /swapfile' 'swapon /swapfile' > plan.txt; echo '/swapfile none swap sw 0 0' >> fstab; echo 'vm.swappiness=<<sw>>' > sysctl.conf",
     "dd if=/dev/zero of=swapfile bs=1M count=1 status=none; chmod 600 swapfile; printf '%s\\n' 'swapon /swapfile' 'mkswap /swapfile' > plan.txt; echo '/swapfile none swap sw 0 0' >> fstab; echo 'vm.swappiness=<<sw>>' > sysctl.conf"],
    'swapファイルは「作成→chmod 600→mkswap→swapon→fstab」の順。swappinessは小さいほどswapしにくくなり、永続化は /etc/sysctl.d/*.conf に書きます。')


# ---------------------------------------------------------------- 7 fsck judgement
def s7(ctx):
    base(ctx)
    devs = ['sdb1', 'sdc1', 'sdd1']; random.shuffle(devs)
    kinds = ['ext4-unmounted', 'xfs-unmounted', 'ext4-mounted']; random.shuffle(kinds)
    ctx.data['map'] = dict(zip(devs, kinds))
    cap = []
    for dv, k in ctx.data['map'].items():
        fs, st = k.split('-')
        cap.append(f'/dev/{dv}: TYPE="{fs}" state={"mounted at /srv/" + dv if st == "mounted" else "not mounted"}')
    ctx.write('capture/state.txt', '\n'.join(cap) + '\n')
    ctx.write('requirements.txt', 'result.json: 各デバイス名(sdXN)をキーに、修復の次の一手を値で書く。ext4で未マウント="e2fsck -f /dev/X"、xfsで未マウント="xfs_repair /dev/X"、'
              'マウント中="umount /dev/X"(まず外す)。\n')
    preserve(ctx, 'capture/state.txt')


def c7(ctx):
    unchanged(ctx, 'capture/state.txt'); exp = {}
    for dv, k in ctx.data['map'].items():
        exp[dv] = {'ext4-unmounted': f'e2fsck -f /dev/{dv}', 'xfs-unmounted': f'xfs_repair /dev/{dv}', 'ext4-mounted': f'umount /dev/{dv}'}[k]
    ctx.require(jload(ctx, 'result.json') == exp, 'ファイルシステム種別とマウント状態で判断します。マウント中は先に umount が必要です。')


SOL7 = """python3 - <<'PYCODE'
import re, json
r={}
for l in open('capture/state.txt'):
    dv=re.match(r'/dev/(\\w+):',l).group(1)
    if 'not mounted' not in l: r[dv]='umount /dev/'+dv
    elif 'xfs' in l: r[dv]='xfs_repair /dev/'+dv
    else: r[dv]='e2fsck -f /dev/'+dv
json.dump(r,open('result.json','w'))
PYCODE"""
add(7, 'fsckと修復の判断（e2fsck/xfs_repair）', '3つのデバイスについて、種類とマウント状態から次の一手を判断します。',
    ['デバイス状態の記録を変更しない', 'result.json に各デバイスの次の一手を記録'], s7, c7, SOL7,
    ["""python3 - <<'PYCODE'
import re, json
r={}
for l in open('capture/state.txt'):
    dv=re.match(r'/dev/(\\w+):',l).group(1)
    r[dv]='e2fsck -f /dev/'+dv
json.dump(r,open('result.json','w'))
PYCODE"""],
    'ext4は e2fsck、XFSは xfs_repair を使い、どちらもマウント中のFSには実行しません。XFSには e2fsck は使えず、まず umount してから修復します。')


# ---------------------------------------------------------------- 8 mount options + nfs
def s8(ctx):
    base(ctx)
    srv = 'nas' + secrets.token_hex(2) + '.lab.example'; ex = '/export/' + secrets.token_hex(2)
    ctx.data.update(srv=srv, ex=ex)
    root = 'UUID=root-fixture / ext4 defaults 0 1'; ctx.data['root'] = root
    u1 = str(uuidlib.uuid4()); u2 = str(uuidlib.uuid4()); ctx.data.update(u1=u1, u2=u2)
    ctx.write('fstab', f'{root}\nUUID={u1} /tmp ext4 defaults 0 2\nUUID={u2} /srv/archive ext4 defaults 0 2\n')
    ctx.write('requirements.txt', 'fstab(控え)を編集: /tmp は noexec,nosuid,nodev を追加(defaultsは残す)、/srv/archive は読み取り専用(ro)にし nosuid,nodev も付ける(defaultsは外す)。'
              f'さらに NFS {srv}:{ex} を /mnt/nfs に nfs4 で追加: オプションは defaults,_netdev,nosuid、dump/pass は 0 0。root行・UUIDは変えない。\n')


def c8(ctx):
    d = ctx.data; rows = fstab_rows(ctx)
    ctx.require(len(rows) == 4 and ' '.join(rows[0]) == d['root'], 'root行を維持し、全体で4行にします。')
    m = {r[1]: r for r in rows if len(r) == 6}
    ctx.require(len(m) == 4, '各行は6項目にします。')
    t = m.get('/tmp'); a = m.get('/srv/archive'); n = m.get('/mnt/nfs')
    ctx.require(t and t[0] == 'UUID=' + d['u1'] and t[2] == 'ext4' and set(t[3].split(',')) == {'defaults', 'noexec', 'nosuid', 'nodev'} and t[4:] == ['0', '2'], '/tmp の行を確認しましょう。')
    ctx.require(a and a[0] == 'UUID=' + d['u2'] and set(a[3].split(',')) == {'ro', 'nosuid', 'nodev'} and a[4:] == ['0', '2'], '/srv/archive の行を確認しましょう（defaultsを外すのは rw を含むためです）。')
    ctx.require(n and n[0] == f'{d["srv"]}:{d["ex"]}' and n[2] == 'nfs4' and set(n[3].split(',')) == {'defaults', '_netdev', 'nosuid'} and n[4:] == ['0', '0'], 'NFS行の形式を確認しましょう。')


SOL8 = """sed -i -E '/ \\/tmp /s/defaults/defaults,noexec,nosuid,nodev/; / \\/srv\\/archive /s/defaults/ro,nosuid,nodev/' fstab
echo '<<srv>>:<<ex>> /mnt/nfs nfs4 defaults,_netdev,nosuid 0 0' >> fstab"""
add(8, 'マウントオプションとNFSのfstab', 'noexec・nosuid・roを使い分け、NFSマウントの行も追加します。',
    ['/tmp と /srv/archive のオプション修正', 'NFS行の追加'], s8, c8, SOL8,
    ["sed -i -E '/ \\/tmp /s/defaults/defaults,noexec/; / \\/srv\\/archive /s/defaults/defaults,ro/' fstab; echo '<<srv>>:<<ex>> /mnt/nfs nfs4 defaults 0 0' >> fstab",
     "echo '<<srv>>:<<ex>> /mnt/nfs nfs <<ex>> 0 0' >> fstab"],
    'noexecは実行禁止、nosuidはsetuid無効、nodevはデバイスファイル無効、roは読み取り専用です。defaultsにはrwが含まれるので、roにするときはdefaultsを外します。NFSには_netdevを付けてネットワーク起動後にマウントさせます。')


# ---------------------------------------------------------------- 9 quota
def s9(ctx):
    base(ctx)
    user = 'user' + secrets.token_hex(2); soft = random.choice([500000, 800000, 1000000]); hard = soft + random.choice([100000, 200000])
    u = str(uuidlib.uuid4())
    ctx.data.update(user=user, soft=soft, hard=hard, u=u, root='UUID=root-fixture / ext4 defaults 0 1')
    ctx.write('fstab', f'{ctx.data["root"]}\nUUID={u} /home ext4 defaults 0 2\n')
    ctx.write('requirements.txt', f'/home でユーザ/グループquotaを有効にする設計。fstabの/home行に usrquota,grpquota を追加し、defaultsは残す。'
              f'plan.txt に1行1コマンドで手順を書く。対象ユーザは {user}、ブロック上限は soft={soft}, hard={hard}、inode上限は無制限。'
              'softは警告の基準、hardは超えられない上限。計画だけ作り、コマンドは実行しない。\n')


def c9(ctx):
    d = ctx.data; rows = fstab_rows(ctx)
    ctx.require(len(rows) == 2 and ' '.join(rows[0]) == d['root'], 'root行を維持します。')
    h = rows[1]
    ctx.require(h[:3] == ['UUID=' + d['u'], '/home', 'ext4'] and set(h[3].split(',')) == {'defaults', 'usrquota', 'grpquota'} and h[4:] == ['0', '2'], '/home 行を確認しましょう。')
    L = cmds(ctx, 'plan.txt')
    a = idx(L, lambda t: t[0] == 'quotacheck' and t[-1] == '/home' and any(x.startswith('-') and 'c' in x and 'u' in x and 'g' in x for x in t))
    b = idx(L, lambda t: t == ['quotaon', '/home'])
    c = idx(L, lambda t: t == ['setquota', '-u', d['user'], str(d['soft']), str(d['hard']), '0', '0', '/home'])
    ctx.require(a >= 0, 'quotacheck -cug /home で管理ファイルを作成します。')
    ctx.require(b > a, 'quotacheck の後に quotaon します。')
    ctx.require(c > b, 'quotaon の後に setquota で上限を設定します。')


SOL9 = """sed -i -E '/ \\/home /s/defaults/defaults,usrquota,grpquota/' fstab
printf '%s\\n' 'quotacheck -cug /home' 'quotaon /home' 'setquota -u <<user>> <<soft>> <<hard>> 0 0 /home' > plan.txt"""
add(9, 'quotaの設定例を作る', 'quotaはユーザごとのディスク使用量を制限する仕組みです。softは警告を出す基準、hardは超えられない上限です。fstabと計画ファイルに設定をまとめます。',
    ['fstabで /home のユーザ/グループquotaを有効化する', 'plan.txt に必要な手順を正しい順で書く'], s9, c9, SOL9,
    ["sed -i -E '/ \\/home /s/defaults/defaults,usrquota/' fstab; printf '%s\\n' 'setquota -u <<user>> <<soft>> <<hard>> 0 0 /home' 'quotaon /home' > plan.txt",
     "sed -i -E '/ \\/home /s/defaults/usrquota,grpquota/' fstab; printf '%s\\n' 'quotacheck -cug /home' 'quotaon /home' 'setquota -u <<user>> <<hard>> <<soft>> 0 0 /home' > plan.txt"],
    'quotaはマウントオプションで有効化し、quotacheckで集計ファイルを作り、quotaonで有効化、setquotaで上限を設定します。soft(警告)はhard(絶対上限)以下にします。',
    hints=['requirements.txt に対象ユーザと上限値があります。まず fstab の /home 行と必要な出力を確認します。',
           'quotaの準備、集計、上限設定を担当するコマンドを思い出し、plan.txt に1行ずつ正しい順序で書きます。',
           'man setquota で引数の順を確認できます。inodeを制限しない値と、soft/hard の位置に注意します。'])


# ---------------------------------------------------------------- 10 inode
def s10(ctx):
    base(ctx)
    names = ['cache', 'sessions', 'spool']; random.shuffle(names); big = names[0]; ctx.data['big'] = big
    nb = random.randint(300, 400)
    for nm in names:
        n = nb if nm == big else random.randint(20, 60)
        for i in range(n):
            ctx.write(f'fs/{nm}/f{i:04d}.tmp', '')
        ctx.write(f'fs/{nm}/important.keep', 'keep\n')
    ctx.data['others'] = {nm: len(list(ctx.p(f'fs/{nm}').iterdir())) for nm in names if nm != big}
    ctx.write('capture/df-i.txt', 'Filesystem Inodes IUsed IFree IUse% Mounted on\n/dev/vdb1 100000 100000 0 100% /srv\n')
    ctx.write('requirements.txt', 'fs/ 以下のうちファイル数が最多のディレクトリ名を result.txt に書き、その中の *.tmp だけ削除する(*.keep と他のディレクトリは残す)。\n')
    preserve(ctx, 'capture/df-i.txt')


def c10(ctx):
    unchanged(ctx, 'capture/df-i.txt'); d = ctx.data
    ctx.require(ctx.need_file('result.txt').strip() == d['big'], 'result.txt にファイル数最多のディレクトリ名のみを書きます。')
    ctx.require(not list(ctx.p(f'fs/{d["big"]}').glob('*.tmp')), f'fs/{d["big"]} の *.tmp が残っています。')
    ctx.require(ctx.isfile(f'fs/{d["big"]}/important.keep'), 'important.keep は残してください。')
    for nm, n in d['others'].items():
        ctx.require(len(list(ctx.p(f'fs/{nm}').iterdir())) == n, f'fs/{nm} は変更しないでください。')


SOL10 = """for d in fs/*/; do echo "$(ls "$d" | wc -l) $(basename $d)"; done | sort -rn | head -1 | awk '{print $2}' > result.txt
find fs/$(cat result.txt) -name '*.tmp' -delete"""
add(10, 'inode枯渇の原因ディレクトリを片付ける', 'IUse%が100%です。小さいファイルが集中しているディレクトリを見つけ、安全に掃除します。',
    ['最多ファイルのディレクトリ名を result.txt へ', '*.tmp のみ削除'], s10, c10, SOL10,
    ["rm -rf fs/*/*.tmp; echo cache > result.txt", "rm -rf fs/<<big>>; echo <<big>> > result.txt"],
    'df -i でinode枯渇を確認し、find / ls | wc -l でファイル数の多い場所を特定します。削除は find -delete で対象を絞り、保持すべきファイルを巻き込まないようにします。')


# ---------------------------------------------------------------- 11 dd + sha256
def s11(ctx):
    base(ctx)
    ctx.write('disk.img', secrets.token_bytes(256 * 1024), binary=True)
    ctx.write('requirements.txt', 'disk.img(模擬ディスク)を dd で backup.img へ複製(bs=64K)。backup.sha256 に sha256sum 形式("ハッシュ  backup.img")で記録し、'
              'sha256sum -c で検証できる状態にする。disk.img は変更しない。\n')
    preserve(ctx, 'disk.img')


def c11(ctx):
    unchanged(ctx, 'disk.img')
    ctx.require(ctx.isfile('backup.img') and not ctx.p('backup.img').is_symlink(), 'backup.img を作成してください。')
    ctx.require(ctx.p('backup.img').read_bytes() == ctx.p('disk.img').read_bytes(), 'backup.img が disk.img と一致しません。サイズ指定や中断に注意。')
    ln = ctx.need_file('backup.sha256').strip().splitlines()
    ctx.require(len(ln) == 1 and re.fullmatch(r'[0-9a-f]{64} [ *]{1,2}backup\.img', ln[0]) is not None, 'backup.sha256 は sha256sum の出力形式で、対象は backup.img です。')
    ctx.require(ln[0].split()[0] == sha(ctx, 'backup.img'), 'ハッシュ値が backup.img と一致しません。')


SOL11 = """dd if=disk.img of=backup.img bs=64K status=none
sha256sum backup.img > backup.sha256
sha256sum -c backup.sha256"""
add(11, 'ddでイメージを作りsha256で検証する', '模擬ディスクのバックアップイメージを作り、ハッシュで完全性を確認できる形にします。',
    ['dd でバックアップ作成', 'backup.sha256 を作り -c で検証'], s11, c11, SOL11,
    ["cp disk.img backup.img", "dd if=disk.img of=backup.img bs=64K count=2 status=none; sha256sum backup.img > backup.sha256",
     "dd if=disk.img of=backup.img bs=64K status=none; sha256sum disk.img > backup.sha256"],
    'ddは if(入力)/of(出力)/bs/count を指定します。countで途中までしか複製しない事故に注意。sha256sum で取ったハッシュを保存し sha256sum -c で後から検証します。実機では ofを逆にすると元ディスクを壊すため確認必須です。')


# ---------------------------------------------------------------- 12 smartctl
def s12(ctx):
    base(ctx)
    devs = ['sda', 'sdb', 'sdc']; random.shuffle(devs)
    ctx.data.update(bad=devs[0], cable=devs[1], ok=devs[2])
    pend = random.randint(40, 200); realloc = random.randint(300, 900); crc = random.randint(500, 3000)

    def blk(dv, r, p, c, hrs):
        return (f'=== /dev/{dv} ===\nSMART overall-health self-assessment test result: PASSED\n'
                f'ID# ATTRIBUTE_NAME RAW_VALUE\n  5 Reallocated_Sector_Ct {r}\n  9 Power_On_Hours {hrs}\n197 Current_Pending_Sector {p}\n199 UDMA_CRC_Error_Count {c}\n')
    t = {ctx.data['bad']: blk(ctx.data['bad'], realloc, pend, 0, 41000), ctx.data['cable']: blk(ctx.data['cable'], 0, 0, crc, 12000),
         ctx.data['ok']: blk(ctx.data['ok'], 0, 0, 0, 30000)}
    ctx.write('capture/smart.txt', ''.join(t[k] for k in sorted(t)))
    ctx.write('requirements.txt', 'result.json: replace(交換すべきディスク名。媒体の劣化=Reallocated/Pending が大), cable_check(ケーブル確認をすべきディスク名。UDMA_CRCのみ異常), '
              'reason(交換理由の属性名を配列で、例 ["Name1","Name2"]、アルファベット順)。overall PASSEDでも判断は属性で行う。\n')
    preserve(ctx, 'capture/smart.txt')


def c12(ctx):
    unchanged(ctx, 'capture/smart.txt'); d = ctx.data
    ctx.require(jload(ctx, 'result.json') == dict(replace=d['bad'], cable_check=d['cable'], reason=['Current_Pending_Sector', 'Reallocated_Sector_Ct']),
                'overall PASSEDは安心材料になりません。Reallocated/Pendingが増えた媒体は交換、CRCエラーのみならケーブル/コネクタを疑います。')


SOL12 = """python3 - <<'PYCODE'
import re, json
t=open('capture/smart.txt').read()
bad=cab=None
for blk in t.split('=== ')[1:]:
    dv=blk.split('/dev/')[1].split()[0]
    v={m[0]:int(m[1]) for m in re.findall(r'(\\w+_\\w+(?:_\\w+)*) (\\d+)\\s*$',blk,re.M)}
    if v['Reallocated_Sector_Ct'] or v['Current_Pending_Sector']: bad=dv
    elif v['UDMA_CRC_Error_Count']: cab=dv
json.dump(dict(replace=bad,cable_check=cab,reason=['Current_Pending_Sector','Reallocated_Sector_Ct']),open('result.json','w'))
PYCODE"""
add(12, 'smartctlの出力から交換判断をする', '3台分のSMART採取結果から、交換すべきディスクとケーブル確認で済むディスクを見分けます。',
    ['SMARTの採取記録を変更しない', '交換対象・ケーブル確認対象・理由を result.json へ'], s12, c12, SOL12,
    ["echo '{\"replace\":\"<<cable>>\",\"cable_check\":\"<<bad>>\",\"reason\":[\"UDMA_CRC_Error_Count\"]}' > result.json",
     "echo '{\"replace\":\"<<bad>>\",\"cable_check\":\"<<cable>>\",\"reason\":[\"UDMA_CRC_Error_Count\"]}' > result.json"],
    'Reallocated_Sector_CtやCurrent_Pending_Sectorは媒体劣化の兆候で、交換を計画します。UDMA_CRC_Error_Countは転送経路(ケーブル等)の問題を示すことが多いです。総合判定PASSEDでも属性の推移を見ます。')
