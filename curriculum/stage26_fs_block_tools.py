"""Stage 26: ファイルシステム・ブロックデバイス工具の総ざらい。サンドボックス内の偽データと採取済み出力だけを使う。"""
import hashlib
import json
import secrets
import shlex
import shutil
import struct
from pathlib import Path

from engine.runner import register

S = 26
NOTE = ("作業対象はこの課題のフォルダだけです。実ディスク・実パーティション・実マウントには触れず、rootも使いません。"
        "デバイス名やUUIDは訓練用の偽物で、実行環境にない工具は採取済みの出力から診断し、コマンドは書くだけで実行しません。")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text):
    ctx.write(name, text)
    ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(sha(ctx.need_file(name)) == h, name + ' は原本（採取済み記録）です。変更しないでください。')


def rj(ctx, name):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def cmds(ctx, name, n=None):
    ls = [x.strip() for x in ctx.need_file(name).splitlines() if x.strip() and not x.strip().startswith('#')]
    if n is not None:
        ctx.require(len(ls) == n, f'{name} には{n}行のコマンドを書きます（空行と#行は数えません）。')
    return [toks(ctx, x) for x in ls]


def head(ctx, t, *names):
    ctx.require(bool(t) and t[0] in names, f'{" か ".join(names)} で始まる行が必要です（今は {t[:1]}）。')


def has(ctx, t, *flags):
    for f in flags:
        ctx.require(f in t, f'{f} が必要です: {" ".join(t)}')


def val(ctx, t, flag):
    ctx.require(flag in t and t.index(flag) + 1 < len(t), f'{flag} と値を指定します。')
    return t[t.index(flag) + 1]


def dev():
    return '/dev/sd' + secrets.choice('bcdefgh')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'26-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='ブロックデバイス操作は破壊的です。まず読み取り専用・dry-runで確認し、バックアップとデバイス名の再確認を習慣にしましょう。')


# ---------------------------------------------------------------- 1 badblocks / blkdiscard / blockdev
def s1(ctx):
    d = dev()
    bs = 4096
    blocks = 20000 + secrets.randbelow(50000)
    bad = sorted(secrets.SystemRandom().sample(range(1000, blocks), 3))
    ctx.data.update(d=d, blocks=blocks, bad=bad, size=blocks * bs)
    put(ctx, 'record.txt', f'$ blockdev --getsize64 {d}\n{blocks * bs}\n$ blockdev --getbsz {d}\n{bs}\n'
        f'$ badblocks -sv -b {bs} {d}\nChecking blocks 0 to {blocks - 1}\nChecking for bad blocks (read-only test): done\n'
        + ''.join(f'{b}\n' for b in bad) + f'Pass completed, {len(bad)} bad blocks found. (3/0/0 errors)\n')
    ctx.write('requirements.txt', f'record.txtは{d}の採取済み診断。report.jsonに size_bytes（バイト数）、blocks（4096B単位のブロック数）、bad_blocks（不良ブロック番号の昇順リスト）を書く。'
              f'cmd.txtには(1)データを壊さない読み取り専用のbadblocks（-sv と -b 4096）、(2)診断中の誤書込を防ぐ blockdev --setro の2行を書く。blkdiscardは全データを破棄するので使わない。\n')


def c1(ctx):
    need_ro(ctx)
    r = rj(ctx, 'report.json')
    d = ctx.data
    ctx.require(r.get('size_bytes') == d['size'], 'size_bytes は blockdev --getsize64 の値です。')
    ctx.require(r.get('blocks') == d['blocks'], 'blocks はサイズを4096で割った値です。')
    ctx.require(r.get('bad_blocks') == d['bad'], 'bad_blocks は不良ブロック番号の昇順リストです。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    head(ctx, a, 'badblocks')
    has(ctx, a, '-b', d['d'])
    ctx.require(val(ctx, a, '-b') == '4096', '-b 4096 を指定します。')
    ctx.require(not any(x.startswith('-') and ('w' in x or 'n' in x) for x in a) and any(x.startswith('-') and 's' in x and 'v' in x for x in a), '読み取り専用(-wや-nを使わない)で、-sv で進捗と詳細を出します。')
    ctx.require(b[:2] == ['blockdev', '--setro'] and b[2:] == [d['d']], 'blockdev --setro デバイス の形です。')


SOL1 = """python3 - <<'PY'
import json
bad=<<bad>>
json.dump({"size_bytes":<<size>>,"blocks":<<blocks>>,"bad_blocks":bad},open("report.json","w"))
PY
printf '%s\\n' "badblocks -sv -b 4096 <<d>>" "blockdev --setro <<d>>" > cmd.txt"""
mission(1, 'badblocks・blkdiscard・blockdevで不良ブロック診断を読む',
        '古い外付けディスクの診断記録が届きました。blockdev でサイズとブロックサイズを確認し、badblocks の読み取りテストで不良ブロックを数えます。blkdiscard はSSD向けでデータを破棄する破壊的コマンドなので、診断には絶対使いません。',
        ['診断記録を見つけて読みreport.jsonへ', '安全なbadblocksとblockdev --setroをcmd.txtへ'], s1, c1, SOL1,
        ['printf \'%s\\n\' "badblocks -wsv -b 4096 <<d>>" "blockdev --setro <<d>>" > cmd.txt',
         'printf \'%s\\n\' "blkdiscard <<d>>" "blockdev --setro <<d>>" > cmd.txt'],
        'blockdev --getsize64 はバイト数、--getbsz はブロックサイズ、--setro は読み取り専用化(--setrwで戻す)です。badblocksは既定が読み取りテスト、-nは非破壊の読書き、-wは破壊的な書込みテストです。blkdiscardはTRIM/DISCARDを全域に発行しデータが失われるため、診断ではなく処分・初期化の最後に使います。',
        '読み取り専用と破壊的の差を見ます。', 'badblocks -sv -b 4096 デバイス と blockdev --setro デバイス。')


# ---------------------------------------------------------------- 2 cfdisk / sfdisk / partprobe
def s2(ctx):
    d = dev()
    total = 41943040
    s1_ = 2048
    z1 = 2097152
    s2_ = s1_ + z1
    z2 = 8388608
    want = z2 + 2097152 * (1 + secrets.randbelow(4))
    ctx.data.update(d=d, s2=s2_, z1=z1, z2=want, s1=s1_)
    put(ctx, 'dump.txt', f'$ sfdisk -d {d}\nlabel: gpt\ndevice: {d}\nunit: sectors\nfirst-lba: 34\nlast-lba: {total - 34}\n\n'
        f'{d}1 : start={s1_}, size={z1}, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n'
        f'{d}2 : start={s2_}, size={z2}, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n')
    ctx.write('requirements.txt', f'dump.txtは{d}のsfdisk -dの出力（全{total}セクタ、後ろは空き）。第2パーティションを size={want} セクタへ広げる設定をnew.sfdiskに書く'
              f'（labelとunit行、1つ目は不変）。cmd.txtに(1)実際には書き込まない dry-run の sfdisk（new.sfdiskを標準入力に）(2)カーネルに再読込させる partprobe の2行。対話UIのcfdiskは使わない。\n')


def c2(ctx):
    need_ro(ctx)
    d = ctx.data
    txt = ctx.need_file('new.sfdisk')
    ctx.require('label: gpt' in txt, 'label: gpt の行を残します。')
    parts = {}
    for ln in txt.splitlines():
        if ln.startswith(d['d']) and ':' in ln:
            name, rest = ln.split(':', 1)
            kv = dict(x.strip().split('=', 1) for x in rest.split(',') if '=' in x)
            parts[name.strip()] = kv
    p1, p2 = parts.get(d['d'] + '1'), parts.get(d['d'] + '2')
    ctx.require(p1 and p2, '2つのパーティション行が必要です。')
    ctx.require(p1.get('start') == str(d['s1']) and p1.get('size') == str(d['z1']), '第1パーティションは変更しません。')
    ctx.require(p2.get('start') == str(d['s2']) and p2.get('size') == str(d['z2']), '第2は start を変えず size だけを指定値にします。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    head(ctx, a, 'sfdisk')
    ctx.require(('--no-act' in a or '-n' in a) and d['d'] in a, 'sfdisk --no-act デバイス で dry-run にします。')
    ctx.require('<' in a and 'new.sfdisk' in a, '< new.sfdisk で設定を渡します。')
    ctx.require(b == ['partprobe', d['d']], 'partprobe デバイス でカーネルへ反映します。')


SOL2 = """printf 'label: gpt\\nunit: sectors\\n\\n<<d>>1 : start=<<s1>>, size=<<z1>>, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\\n<<d>>2 : start=<<s2>>, size=<<z2>>, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\\n' > new.sfdisk
printf '%s\\n' "sfdisk --no-act <<d>> < new.sfdisk" "partprobe <<d>>" > cmd.txt"""
mission(2, 'sfdisk dry-runとpartprobeでパーティションを広げる',
        'cfdisk は対話式の分割ツールですが、手順を残して再現するには sfdisk のスクリプトが向いています。まず -d のダンプを読み、新しい定義を作って dry-run で検証し、partprobe でカーネルへ反映する手順を書いてください。',
        ['new.sfdiskに新しいテーブルを書く', 'dry-runのsfdiskとpartprobeをcmd.txtへ'], s2, c2, SOL2,
        ['printf \'%s\\n\' "sfdisk <<d>> < new.sfdisk" "partprobe <<d>>" > cmd.txt',
         'printf \'%s\\n\' "cfdisk <<d>>" "partprobe <<d>>" > cmd.txt'],
        'sfdisk -d で現在のテーブルを保存でき、--no-act（-n）で書込みなしの検証ができます。成功を確認してから本実行し、変更後は partprobe（または partx -u）でカーネルのパーティション認識を更新します。cfdiskは対話式のTUI、sfdiskはスクリプト向けで、どちらも変更前にダンプを退避しておくと戻せます。',
        'dry-runが先、書込みが後です。', 'sfdisk --no-act デバイス < ファイル、そのあと partprobe デバイス。')


# ---------------------------------------------------------------- 3 partx / addpart / delpart / resizepart
def s3(ctx):
    d = dev()
    n = 3 + secrets.randbelow(5)
    start = 2048 * (100 + secrets.randbelow(200))
    ln = 2048 * (10 + secrets.randbelow(50))
    new = ln + 2048 * (5 + secrets.randbelow(20))
    ctx.data.update(d=d, n=n, start=start, ln=ln, new=new)
    put(ctx, 'record.txt', f'$ partx --show {d}\nNR START END SECTORS SIZE NAME UUID\n1 2048 {start - 1} {start - 2048} 5G\n2 {start + 10 ** 6} {start + 2 * 10 ** 6} 1000001 488M\n')
    ctx.write('requirements.txt', f'{d}にパーティション表を書き換えずカーネル上だけで操作したい。cmd.txtに順に(1)現在の一覧 partx --show（2）番号{n}を開始{start}・長さ{ln}セクタで追加 addpart（3）その長さを{new}セクタへ resizepart（4）番号{n}を削除 delpart、の4行を書く。\n')


def c3(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = cmds(ctx, 'cmd.txt', 4)
    ctx.require(ls[0][0] == 'partx' and ('--show' in ls[0] or '-s' in ls[0]) and d['d'] in ls[0], '1行目は partx --show デバイス です。')
    ctx.require(ls[1] == ['addpart', d['d'], str(d['n']), str(d['start']), str(d['ln'])], '2行目は addpart デバイス 番号 開始 長さ です。')
    ctx.require(ls[2] == ['resizepart', d['d'], str(d['n']), str(d['new'])], '3行目は resizepart デバイス 番号 新しい長さ です。')
    ctx.require(ls[3] == ['delpart', d['d'], str(d['n'])], '4行目は delpart デバイス 番号 です。')


SOL3 = 'printf \'%s\\n\' "partx --show <<d>>" "addpart <<d>> <<n>> <<start>> <<ln>>" "resizepart <<d>> <<n>> <<new>>" "delpart <<d>> <<n>>" > cmd.txt'
mission(3, 'partx・addpart・delpart・resizepartでカーネルのパーティション認識を操作する',
        'パーティション表（ディスク上の内容）とカーネルが認識している一覧は別物です。partx は一覧表示・追加・更新、addpart/delpart/resizepart は1つずつの認識を直接変えます。長さの単位は512バイトセクタです。',
        ['4つのコマンドの引数をcmd.txtへ'], s3, c3, SOL3,
        ['printf \'%s\\n\' "partx --show <<d>>" "addpart <<d>> <<n>> <<start>> <<ln>>" "delpart <<d>> <<n>>" "resizepart <<d>> <<n>> <<new>>" > cmd.txt',
         'printf \'%s\\n\' "partx --show <<d>>" "addpart <<d>> <<n>> <<ln>> <<start>>" "resizepart <<d>> <<n>> <<new>>" "delpart <<d>> <<n>>" > cmd.txt'],
        'これらはディスク上のパーティション表は書き換えず、カーネルの認識だけを変えます。使用中のパーティションに対する操作は拒否されます。パーティション表を実際に変えるには sfdisk/fdisk/parted を使い、その後 partprobe や partx -u で反映します。addpartの引数は 開始 長さ の順です。',
        '引数の順序（開始→長さ）に注意します。', 'addpart dev 番号 開始 長さ / resizepart dev 番号 新長さ / delpart dev 番号。')


# ---------------------------------------------------------------- 4 dumpe2fs / e2label
def s4(ctx):
    d = dev() + '1'
    label = 'old-' + secrets.token_hex(2)
    uuid = '-'.join(secrets.token_hex(n) for n in (4, 2, 2, 2, 6))
    blocks = 262144 * (1 + secrets.randbelow(8))
    free = blocks // 3 + secrets.randbelow(1000)
    journal = secrets.randbelow(2) == 1
    clean = secrets.randbelow(2) == 1
    feats = 'ext_attr resize_inode dir_index filetype extent 64bit flex_bg sparse_super large_file huge_file'
    if journal:
        feats = 'has_journal ' + feats
    new = 'data-' + secrets.token_hex(2)
    ctx.data.update(d=d, label=label, uuid=uuid, blocks=blocks, free=free, journal=journal, clean=clean, new=new)
    put(ctx, 'dumpe2fs.txt', f'$ dumpe2fs -h {d}\ndumpe2fs 1.47.0\nFilesystem volume name:   {label}\nFilesystem UUID:          {uuid}\n'
        f'Filesystem features:      {feats}\nFilesystem state:         {"clean" if clean else "not clean"}\nBlock count:              {blocks}\n'
        f'Free blocks:              {free}\nBlock size:               4096\nMount count:              12\n')
    ctx.write('requirements.txt', f'dumpe2fs.txtから info.json に label, uuid, state_clean(真偽), blocks, free_blocks, has_journal(真偽), size_bytes を書く。'
              f'cmd.txtにはラベルを {new} に変える e2label コマンドを1行（{d}）。\n')


def c4(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'info.json')
    ctx.require(r.get('label') == d['label'] and r.get('uuid') == d['uuid'], 'label と uuid を書き写します。')
    ctx.require(r.get('state_clean') is d['clean'], 'state_clean は Filesystem state が clean か。')
    ctx.require(r.get('blocks') == d['blocks'] and r.get('free_blocks') == d['free'], 'blocks と free_blocks を確認します。')
    ctx.require(r.get('has_journal') is d['journal'], 'has_journal は features に has_journal があるか。')
    ctx.require(r.get('size_bytes') == d['blocks'] * 4096, 'size_bytes は Block count × Block size。')
    (t,) = cmds(ctx, 'cmd.txt', 1)
    ctx.require(t == ['e2label', d['d'], d['new']], 'e2label デバイス 新ラベル の形です。')


SOL4 = """python3 - <<'PY'
import json
json.dump({"label":"<<label>>","uuid":"<<uuid>>","state_clean":<<clean_py>>,"blocks":<<blocks>>,"free_blocks":<<free>>,"has_journal":<<journal_py>>,"size_bytes":<<size>>},open("info.json","w"))
PY
echo "e2label <<d>> <<new>>" > cmd.txt"""


def s4b(ctx):
    s4(ctx)
    ctx.data['clean_py'] = 'True' if ctx.data['clean'] else 'False'
    ctx.data['journal_py'] = 'True' if ctx.data['journal'] else 'False'
    ctx.data['size'] = ctx.data['blocks'] * 4096


mission(4, 'dumpe2fs -hのスーパーブロックを読みe2labelでラベルを変える',
        'dumpe2fs -h はext系のスーパーブロック（ラベル・UUID・機能・状態・ブロック数）を表示します。記録を読んで要点をJSONにまとめ、e2label でラベルを付け替えるコマンドを書いてください。',
        ['info.jsonにまとめる', 'e2labelコマンドをcmd.txtへ'], s4b, c4, SOL4,
        ['echo "e2label <<new>> <<d>>" > cmd.txt', 'echo "tune2fs -U <<new>> <<d>>" > cmd.txt'],
        'dumpe2fs -h はヘッダだけ（グループ情報を省略）を表示します。e2label は ext2/3/4 のラベルの表示と変更ができ、16文字までです。内容は tune2fs -L と同じ効果です。ラベル変更だけならアンマウント不要ですが、fstab が LABEL= で参照していないか先に確認します。',
        'Filesystem features の has_journal に注目します。', 'e2label デバイス ラベル の順序です。')


# ---------------------------------------------------------------- 5 debugfs
def s5(ctx):
    d = dev() + '1'
    inos = secrets.SystemRandom().sample(range(12, 5000), 3)
    sizes = [secrets.randbelow(90000) + 1000 for _ in range(3)]
    owners = [1000, 1001, 0]
    k = secrets.randbelow(3)
    ctx.data.update(d=d, ino=inos[k], size=sizes[k], out='rec-' + secrets.token_hex(2) + '.bin')
    rows = ''.join(f' {inos[i]:6d} {owners[i]:6d} 100644 {sizes[i]:7d} 1/1 Sat Nov 21 10:0{i}:00 2026\n' for i in range(3))
    put(ctx, 'record.txt', f'$ debugfs -R lsdel {d}\ndebugfs 1.47.0 (read-only)\n Inode  Owner  Mode    Size    Blocks   Time deleted\n{rows}3 deleted inodes found.\n')
    ctx.write('requirements.txt', f'record.txtは削除済みinodeの一覧。所有者1000で大きさ{sizes[k]}バイトのinodeを、ディスクへ一切書き込まず {ctx.data["out"]} へ取り出す debugfs コマンドを1行cmd.txtに書く（デバイスは{d}）。\n')


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    (t,) = cmds(ctx, 'cmd.txt', 1)
    head(ctx, t, 'debugfs')
    ctx.require('-w' not in t, '-w は書込みを許すので付けません（読み取り専用）。')
    ctx.require(d['d'] in t, 'デバイスを指定します。')
    inner = toks(ctx, val(ctx, t, '-R'))
    ctx.require(inner == ['dump', f'<{d["ino"]}>', d['out']], f"-R の中は dump <{d['ino']}> {d['out']} です。")


SOL5 = 'echo "debugfs -R \'dump <<<ino>>> <<out>>\' <<d>>" > cmd.txt'
mission(5, 'debugfsを読み取り専用で使い削除ファイルを取り出す',
        'debugfs はext2/3/4の内部を直接調べる工具です。削除されたファイルのinodeを一覧(lsdel)から選び、書込みモードを使わずに内容を別ファイルへ dump してください。',
        ['対象inodeを特定', 'debugfs -R "dump" コマンドをcmd.txtへ'], s5, c5, SOL5,
        ['echo "debugfs -w -R \'dump <<<ino>>> <<out>>\' <<d>>" > cmd.txt', 'echo "debugfs -R \'undel <<<ino>>> <<out>>\' <<d>>" > cmd.txt'],
        'debugfs は既定で読み取り専用で開き、-w を付けたときだけ書込みます。-R で1つのコマンドを実行し、inodeは <番号> で指定します。undel はinodeを復活させる書込み操作で、まず dump による読み出しを選びます。復旧は常にコピーしたイメージ上で試すのが定石です。',
        'inodeの指定は山括弧で囲みます。', 'debugfs -R "dump <inode> 出力" デバイス。')


# ---------------------------------------------------------------- 6 e2freefrag / e4defrag
def s6(ctx):
    score = secrets.choice([5, 20, 40, 48, 60, 77, 90])
    ctx.data.update(score=score, verdict='none' if score <= 30 else 'slight' if score <= 55 else 'needed', mp='/mnt/data')
    mx = 100000 + secrets.randbelow(900000)
    ctx.data['mx'] = mx
    put(ctx, 'record.txt', f'$ e2freefrag /dev/sdb1\nDevice: /dev/sdb1\nBlocksize: 4096 bytes\nTotal blocks: 2621440\nFree blocks: 1048576 (40.0%)\n'
        f'Min. free extent: 4 KB\nMax. free extent: {mx} KB\nAvg. free extent: 256 KB\nNum. free extent: 8192\n\n'
        f'$ e4defrag -c /mnt/data\n<Fragmented files>   now/best   size/ext\n1. /mnt/data/a.db   40/1   120 KB\nTotal/best extents  5200/260\n'
        f'Average size per extent  210 KB\nFragmentation score  {score}\n[0-30 no problem: 31-55 a little bit fragmented: 56- needs defrag]\n')
    ctx.write('requirements.txt', 'record.txtを読み、frag.jsonに max_free_extent_kb（e2freefragの最大連続空き）, score（e4defragのスコア）, verdict（none/slight/needed）を書く。'
              'cmd.txtには実際には並べ替えずスコアだけ測る e4defrag の1行（/mnt/data）。\n')


def c6(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'frag.json')
    ctx.require(r.get('max_free_extent_kb') == d['mx'] and r.get('score') == d['score'], '数値を記録から書き写します。')
    ctx.require(r.get('verdict') == d['verdict'], '0-30 none、31-55 slight、56以上 needed です。')
    (t,) = cmds(ctx, 'cmd.txt', 1)
    ctx.require(t[0] == 'e4defrag' and '-c' in t and t[-1] == d['mp'], 'e4defrag -c /mnt/data です。')


SOL6 = """python3 - <<'PY'
import json
json.dump({"max_free_extent_kb":<<mx>>,"score":<<score>>,"verdict":"<<verdict>>"},open("frag.json","w"))
PY
echo "e4defrag -c /mnt/data" > cmd.txt"""
mission(6, 'e2freefragとe4defragで断片化を測り判断する',
        '空き領域の細かさは e2freefrag、ファイル側の断片化は e4defrag -c で測れます。再配置は負荷が大きいので、まず計測だけを行い、スコアで defrag が要るか判断します。',
        ['frag.jsonに数値と判定', '計測だけのe4defragをcmd.txtへ'], s6, c6, SOL6,
        ['echo "e4defrag /mnt/data" > cmd.txt', 'echo "e2freefrag /mnt/data" > cmd.txt'],
        'e2freefrag は未マウントでも使える空き領域の分布、e4defrag は extent を持つext4専用です。-c は計測のみで、スコアが低ければ何もしません。SSDでは断片化の影響が小さく、無用な書込みを避けるため defrag は基本不要です。',
        'ファイルの断片化は e4defrag、空きの断片化は e2freefrag。', 'e4defrag -c マウントポイント。')


# ---------------------------------------------------------------- 7 e2image / e2undo
def s7(ctx):
    d = dev() + '1'
    new = 'tmp-' + secrets.token_hex(2)
    ctx.data.update(d=d, new=new)
    ctx.write('requirements.txt', f'{d}のラベルを一時的に {new} へ変える作業を、戻せるように行う。cmd.txtに順に(1)メタデータだけの raw イメージ meta.raw を作る e2image -r (2)undoファイル undo.e2undo を作りながら変更する tune2fs -z undo.e2undo -L {new} (3)元に戻す e2undo undo.e2undo、の3行（すべて{d}対象）。\n')


def c7(ctx):
    d = ctx.data
    ls = cmds(ctx, 'cmd.txt', 3)
    ctx.require(ls[0] == ['e2image', '-r', d['d'], 'meta.raw'], '1行目は e2image -r デバイス meta.raw です。')
    ctx.require(ls[1] == ['tune2fs', '-z', 'undo.e2undo', '-L', d['new'], d['d']], '2行目は tune2fs -z undo.e2undo -L 新ラベル デバイス です。')
    ctx.require(ls[2] == ['e2undo', 'undo.e2undo', d['d']], '3行目は e2undo undoファイル デバイス です。')


SOL7 = 'printf \'%s\\n\' "e2image -r <<d>> meta.raw" "tune2fs -z undo.e2undo -L <<new>> <<d>>" "e2undo undo.e2undo <<d>>" > cmd.txt'
mission(7, 'e2imageとe2undoで変更前に退避し元へ戻す',
        'ファイルシステムの設定変更は戻せると安心です。e2image はメタデータだけを小さなイメージに保存し、e2undo は tune2fs/mke2fs/e2fsck などが作った undo ファイルを使って変更を取り消します。',
        ['3行の手順をcmd.txtへ'], s7, c7, SOL7,
        ['printf \'%s\\n\' "e2image <<d>> meta.raw" "tune2fs -L <<new>> <<d>>" "e2undo undo.e2undo <<d>>" > cmd.txt',
         'printf \'%s\\n\' "e2image -r <<d>> meta.raw" "tune2fs -z undo.e2undo -L <<new>> <<d>>" "e2undo <<d>> undo.e2undo" > cmd.txt'],
        'e2image -r は debugfs で開ける raw のメタデータイメージで、障害解析の送付にも使います（データ本体は含まない）。-z undoファイル を付けた変更は e2undo で元に戻せ、環境変数 E2FSPROGS_UNDO_DIR で自動作成もできます。ただし戻せるのはその書込みだけで、undoファイルを失うと戻せません。',
        '引数の順序は undoファイル、デバイスの順です。', 'e2image -r / tune2fs -z / e2undo。')


# ---------------------------------------------------------------- 8 e2scrub / e4crypt
def s8(ctx):
    pd = secrets.token_hex(8)
    ctx.data.update(pd=pd, lv='/dev/vg0/' + secrets.choice(['data', 'home', 'srv']), dr='/mnt/secure-' + secrets.token_hex(2),
                    cm=secrets.choice(['AES_256_XTS', 'AES_128_CBC']), fn=secrets.choice(['AES_256_CTS', 'AES_128_CTS']))
    d = ctx.data
    put(ctx, 'record.txt', f'$ e4crypt get_policy {d["dr"]}\n{d["dr"]}: Policy Version: 0 Policy Descriptor: {pd} Contents: {d["cm"]} Filenames: {d["fn"]}\n'
        f'$ e2scrub -n {d["lv"]}\nThis check only runs on LVM2 snapshots; -n reports without changing anything.\n')
    ctx.write('requirements.txt', f'record.txtのe4crypt get_policyの結果を policy.json に descriptor, contents, filenames で書く。cmd.txtに(1)LVの{d["lv"]}を変更せず検査する e2scrub -n (2)ディレクトリ{d["dr"]}の暗号化ポリシーを調べる e4crypt get_policy を書く。\n')


def c8(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'policy.json')
    ctx.require(r.get('descriptor') == d['pd'] and r.get('contents') == d['cm'] and r.get('filenames') == d['fn'], '記録のDescriptor/Contents/Filenamesを書き写します。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    ctx.require(a == ['e2scrub', '-n', d['lv']], 'e2scrub -n LV です。')
    ctx.require(b == ['e4crypt', 'get_policy', d['dr']], 'e4crypt get_policy ディレクトリ です。')


SOL8 = """python3 - <<'PY'
import json
json.dump({"descriptor":"<<pd>>","contents":"<<cm>>","filenames":"<<fn>>"},open("policy.json","w"))
PY
printf '%s\\n' "e2scrub -n <<lv>>" "e4crypt get_policy <<dr>>" > cmd.txt"""
mission(8, 'e2scrubとe4cryptで検査と暗号化ポリシーを確認する',
        'e2scrub はLVMのスナップショットを使ってオンラインでext4を検査し、e4crypt はext4のディレクトリ暗号化（fscrypt）のポリシーを扱う旧来の工具です。どちらも状態を変えない確認系の使い方を書いてください。',
        ['policy.jsonに記録を写す', '2つのコマンドをcmd.txtへ'], s8, c8, SOL8,
        ['printf \'%s\\n\' "e2scrub <<lv>>" "e4crypt get_policy <<dr>>" > cmd.txt', 'printf \'%s\\n\' "e2scrub -n <<lv>>" "e4crypt set_policy <<pd>> <<dr>>" > cmd.txt'],
        'e2scrub は読み取り専用スナップショットに対して e2fsck -n 相当を行い、-n は確認のみ、問題があるときだけ -r で修復を許します。e4crypt は add_key で鍵を登録、set_policy で空ディレクトリへポリシーを設定、get_policy で確認します。新規には fscrypt ツールが推奨されます。',
        '確認系と変更系（set_policy）を区別します。', 'e2scrub -n LV と e4crypt get_policy DIR。')


# ---------------------------------------------------------------- 9 findfs / findmnt
def s9(ctx):
    letters = list('bcdefg')
    secrets.SystemRandom().shuffle(letters)
    devs = ['/dev/sd' + x + '1' for x in letters[:4]]
    uu = ['-'.join(secrets.token_hex(n) for n in (4, 2, 2, 2, 6)) for _ in devs]
    k = secrets.randbelow(4)
    ctx.data.update(uuid=uu[k], dev=devs[k])
    put(ctx, 'blkid.txt', '$ blkid\n' + ''.join(f'{devs[i]}: UUID="{uu[i]}" TYPE="ext4"\n' for i in range(4)))
    put(ctx, 'fstab.txt', f'UUID={uu[k]} /data ext4 defaults 0 2\n')
    ctx.write('requirements.txt', 'fstab.txtの/dataが指すUUIDの実デバイスを blkid.txt から探して answer.json の device に書く。cmd.txtに(1)そのUUIDからデバイス名を引く findfs (2)/dataのSOURCE,FSTYPE,OPTIONSを出す findmnt --target の2行。\n')


def c9(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'answer.json').get('device') == d['dev'], 'UUIDに対応するデバイスを blkid.txt から探します。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    ctx.require(a == ['findfs', 'UUID=' + d['uuid']], 'findfs UUID=... です。')
    head(ctx, b, 'findmnt')
    ctx.require(val(ctx, b, '--target') == '/data' and val(ctx, b, '-o') == 'SOURCE,FSTYPE,OPTIONS', 'findmnt --target /data -o SOURCE,FSTYPE,OPTIONS です。')


SOL9 = """echo '{"device":"<<dev>>"}' > answer.json
printf '%s\\n' "findfs UUID=<<uuid>>" "findmnt --target /data -o SOURCE,FSTYPE,OPTIONS" > cmd.txt"""
mission(9, 'findfsとfindmntでUUIDからデバイスとマウント状況を引く',
        'fstab はUUIDで書かれ、デバイス名は再起動で変わることがあります。findfs はUUID/LABELからデバイスを検索し、findmnt はマウントの現在状態（またはfstab）を木構造・列指定で表示します。',
        ['answer.jsonにデバイスを書く', 'findfsとfindmntをcmd.txtへ'], s9, c9, SOL9,
        ['echo \'{"device":"<<dev>>"}\' > answer.json\nprintf \'%s\\n\' "findfs <<uuid>>" "findmnt --target /data -o SOURCE,FSTYPE,OPTIONS" > cmd.txt',
         'echo \'{"device":"/dev/sdz1"}\' > answer.json\nprintf \'%s\\n\' "findfs UUID=<<uuid>>" "findmnt /data" > cmd.txt'],
        'findfs は UUID=、LABEL=、PARTUUID= などの形式を受け付けます。findmnt は /proc/self/mountinfo を元に、--target で指定パスを含むマウント、--fstab で設定側、-o で列を選べ、--verify でfstabの整合性チェックもできます。',
        'findfs の引数はタグ=値の形式です。', 'findfs UUID=... / findmnt --target ... -o ...。')


# ---------------------------------------------------------------- 10 fsfreeze / fstrim
def s10(ctx):
    mp = '/mnt/' + secrets.choice(['db', 'ssd', 'vol'])
    ctx.data['mp'] = mp
    ctx.write('requirements.txt', f'SSD上の{mp}の整合スナップショットを取りたい。plan.shに順に(1)書込みを止める fsfreeze -f (2)スナップショット取得（コメント行 # snapshot ）(3)再開する fsfreeze -u (4)未使用ブロックをTRIM（詳細表示 -v）する fstrim、の順で書く。'
              '週次の自動化として systemctl enable --now fstrim.timer も最後の行に書く。fstrimは常時discardマウントではなく定期実行が推奨。\n')


def c10(ctx):
    mp = ctx.data['mp']
    ls = [x.strip() for x in ctx.need_file('plan.sh').splitlines() if x.strip()]
    ctx.require(len(ls) == 5, 'plan.sh は5行（コメント1行を含む）です。')
    ctx.require(toks(ctx, ls[0]) == ['fsfreeze', '-f', mp], '1行目は fsfreeze -f マウントポイント。')
    ctx.require(ls[1].startswith('#') and 'snapshot' in ls[1], '2行目は # snapshot のコメント。')
    ctx.require(toks(ctx, ls[2]) == ['fsfreeze', '-u', mp], '3行目は fsfreeze -u マウントポイント（解凍を忘れるとI/Oが止まったまま）。')
    t = toks(ctx, ls[3])
    ctx.require(t[0] == 'fstrim' and '-v' in t and t[-1] == mp, '4行目は fstrim -v マウントポイント。')
    ctx.require(toks(ctx, ls[4]) == ['systemctl', 'enable', '--now', 'fstrim.timer'], '5行目は systemctl enable --now fstrim.timer。')


SOL10 = 'printf \'%s\\n\' "fsfreeze -f <<mp>>" "# snapshot" "fsfreeze -u <<mp>>" "fstrim -v <<mp>>" "systemctl enable --now fstrim.timer" > plan.sh'
mission(10, 'fsfreezeとfstrimでスナップショットとSSDのTRIM運用を組む',
        'fsfreeze はファイルシステムへの書込みを一時停止して整合した状態を作ります。fstrim は未使用ブロックをSSDへ通知（TRIM）します。TRIM運用は常時discardより fstrim.timer による定期実行が一般的です。',
        ['5行のplan.shを書く'], s10, c10, SOL10,
        ['printf \'%s\\n\' "fsfreeze -f <<mp>>" "# snapshot" "fstrim -v <<mp>>" "fsfreeze -u <<mp>>" "systemctl enable --now fstrim.timer" > plan.sh',
         'printf \'%s\\n\' "fsfreeze -u <<mp>>" "# snapshot" "fsfreeze -f <<mp>>" "fstrim -v <<mp>>" "systemctl enable --now fstrim.timer" > plan.sh'],
        'fsfreeze -f で凍結、-u で解凍します。凍結中は書込みが待たされるため短時間にします（凍結中のfstrimは進みません）。fstrim -v は解放した量を表示し、-a で全対象を処理します。dm-cryptやRAIDではdiscard許可の設定が前提になります。',
        '凍結→スナップショット→解凍の順を崩しません。', 'fsfreeze -f / -u、fstrim -v、fstrim.timer。')


# ---------------------------------------------------------------- 11 losetup
def s11(ctx):
    n = [secrets.randbelow(8) for _ in range(3)]
    while len(set(n)) < 3:
        n = [secrets.randbelow(8) for _ in range(3)]
    imgs = ['/srv/img/a.img', '/srv/img/b.img', 'target-' + secrets.token_hex(2) + '.img']
    k = 2
    ctx.data.update(img=imgs[k], dev=f'/dev/loop{n[k]}', new='new-' + secrets.token_hex(2) + '.img')
    put(ctx, 'record.txt', '$ losetup -a\n' + ''.join(f'/dev/loop{n[i]}: []: (/{imgs[i]})\n' if False else f'/dev/loop{n[i]}: [64769]:{1000 + i} ({imgs[i]})\n' for i in range(3)))
    ctx.write('requirements.txt', f'record.txtから{ctx.data["img"]}に割り当て済みのループデバイスをanswer.jsonのdeviceに書く。cmd.txtに(1)そのファイルのループを調べる losetup -j (2)そのデバイスの割当解除 losetup -d (3){ctx.data["new"]}を空きループへ読み取り専用・パーティション走査付きで割り当て、デバイス名を表示する losetup、の3行。\n')


def c11(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'answer.json').get('device') == d['dev'], 'record.txtでそのイメージ行のデバイスを探します。')
    a, b, c = cmds(ctx, 'cmd.txt', 3)
    ctx.require(a == ['losetup', '-j', d['img']], 'losetup -j イメージ です。')
    ctx.require(b == ['losetup', '-d', d['dev']], 'losetup -d デバイス です。')
    head(ctx, c, 'losetup')
    ctx.require(('-f' in c or '--find' in c) and '--show' in c and ('-P' in c or '--partscan' in c) and ('-r' in c or '--read-only' in c) and c[-1] == d['new'], '-f --show -P -r に新しいイメージを付けます。')


SOL11 = """echo '{"device":"<<dev>>"}' > answer.json
printf '%s\\n' "losetup -j <<img>>" "losetup -d <<dev>>" "losetup -f --show -P -r <<new>>" > cmd.txt"""
mission(11, 'losetupでループデバイスの割当を調べ解除し新規に付ける',
        'ファイルをブロックデバイスとして扱うのが losetup です。使われているループを調べ、不要な割当を解除し、新しいイメージを読み取り専用で付ける手順を書いてください。',
        ['answer.jsonにデバイス', '3行をcmd.txtへ'], s11, c11, SOL11,
        ['echo \'{"device":"<<dev>>"}\' > answer.json\nprintf \'%s\\n\' "losetup <<img>>" "losetup -d <<dev>>" "losetup -f --show -P -r <<new>>" > cmd.txt',
         'echo \'{"device":"<<dev>>"}\' > answer.json\nprintf \'%s\\n\' "losetup -j <<img>>" "losetup -D" "losetup -f --show -P -r <<new>>" > cmd.txt'],
        'losetup -a は全割当の一覧、-j はファイル指定の検索、-d は個別解除、-D は全解除（他人の割当も外す危険）です。-f で空きを探し --show で名前を表示、-P で partscan（/dev/loopNp1を作る）、-r で読み取り専用にします。通常はroot権限が必要なため、この課題では書くだけです。',
        '-d と -D の影響範囲が違います。', 'losetup -j / -d / -f --show -P -r。')


# ---------------------------------------------------------------- 12 mke2fs (real image if available)
def s12(ctx):
    lab = 'img-' + secrets.token_hex(3)
    ctx.data.update(lab=lab, real=bool(shutil.which('mke2fs')))
    extra = ('実際に disk.img を作ります（truncate で8MiB→ mke2fs）。' if ctx.data['real'] else 'このPCには mke2fs がないため、コマンドだけをcmd.txtへ書きます。')
    ctx.write('requirements.txt', f'ext4のラベル {lab} を持つ8MiBのイメージ disk.img をファイルとして作る（-F で通常ファイルを許可し、-qで静かに）。{extra}'
              f'いずれの場合もcmd.txtに使った mke2fs の1行を書く。実デバイスには触れない。\n')


def c12(ctx):
    d = ctx.data
    (t,) = cmds(ctx, 'cmd.txt', 1)
    head(ctx, t, 'mke2fs')
    ctx.require('-F' in t and val(ctx, t, '-t') == 'ext4' and val(ctx, t, '-L') == d['lab'] and t[-1] == 'disk.img', 'mke2fs -F -t ext4 -L ラベル disk.img です。')
    if d['real']:
        p = ctx.p('disk.img')
        ctx.require(p.exists() and p.stat().st_size == 8 * 1024 * 1024, 'disk.img を8MiBで作ります（truncate -s 8M）。')
        b = p.read_bytes()[:2048]
        ctx.require(struct.unpack_from('<H', b, 1080)[0] == 0xEF53, 'ext系スーパーブロックがありません（mke2fsを実行）。')
        ctx.require(b[1144:1160].rstrip(b'\0').decode(errors='replace') == d['lab'], 'ラベルが違います。')
        ctx.require(struct.unpack_from('<I', b, 1116)[0] & 4 and struct.unpack_from('<I', b, 1120)[0] & 0x40, 'ext4（ジャーナルとextent）になっていません。-t ext4 を指定します。')


SOL12 = """truncate -s 8M disk.img
mke2fs -F -q -t ext4 -L <<lab>> disk.img 2>/dev/null || true
echo "mke2fs -F -q -t ext4 -L <<lab>> disk.img" > cmd.txt"""
mission(12, 'mke2fsでループ用イメージファイルにext4を作る',
        'mke2fs はext系ファイルシステムを作る本体で、mkfs.ext2/3/4 はそのリンクです。-t で種類、-L でラベルを指定します。デバイスの代わりに通常ファイルへ作れば、安全に練習できます。',
        ['8MiBのdisk.imgをext4で作る', '使ったmke2fsをcmd.txtへ'], s12, c12, SOL12,
        ['truncate -s 8M disk.img\nmke2fs -F -q -t ext3 -L <<lab>> disk.img 2>/dev/null || true\necho "mke2fs -F -q -t ext3 -L <<lab>> disk.img" > cmd.txt',
         'echo "mke2fs -F -t ext4 disk.img" > cmd.txt'],
        '-t ext4 は mkfs.ext4 と同等です。-F は通常ファイルへの作成の確認を省略し、-L はラベル、-q は出力抑制です。作成後は dumpe2fs -h や e2label disk.img で内容を確認できます。実デバイスで使うときは、誤ったデバイス指定が全消去になる点に最大限注意します。',
        '通常ファイルには -F が要ります。', 'truncate -s 8M disk.img のあと mke2fs -F -q -t ext4 -L ラベル disk.img。')


# ---------------------------------------------------------------- 13 mkfs.ext2/3/4, journal, barrier
def s13(ctx):
    ks = ['ext2', 'ext3', 'ext4']
    secrets.SystemRandom().shuffle(ks)
    names = ['A', 'B', 'C']
    base = 'ext_attr resize_inode dir_index filetype sparse_super'
    feat = {'ext2': base, 'ext3': 'has_journal ' + base, 'ext4': 'has_journal ' + base + ' extent 64bit flex_bg'}
    ctx.data.update(map={n: k for n, k in zip(names, ks)}, d=dev() + '1', jm=secrets.choice([64, 128, 256]))
    put(ctx, 'record.txt', ''.join(f'$ dumpe2fs -h image-{n}\nFilesystem features: {feat[k]}\n\n' for n, k in zip(names, ks)))
    ctx.write('requirements.txt', f'3つのイメージのうち、mkfs.ext2・mkfs.ext3・mkfs.ext4 のどれで作ったかを map.json に {{"A":"ext2",...}} で書く。cmd.txtには(1)ジャーナルサイズ{ctx.data["jm"]}MBでext4を作る mkfs.ext4 -J size=... {ctx.data["d"]} (2)ジャーナルとバリア保証付き（data=ordered、barrier=1）で /mnt/x に mount する行。\n')


def c13(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'map.json') == d['map'], 'ジャーナル無し→ext2、ジャーナルのみ→ext3、extentあり→ext4。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    ctx.require(a == ['mkfs.ext4', '-J', f'size={d["jm"]}', d['d']], 'mkfs.ext4 -J size=MB デバイス です。')
    head(ctx, b, 'mount')
    ctx.require(val(ctx, b, '-o').split(',') == ['data=ordered', 'barrier=1'] and b[-2:] == [d['d'], '/mnt/x'], 'mount -o data=ordered,barrier=1 デバイス /mnt/x です。')


SOL13 = """python3 - <<'PY'
import json
json.dump(<<map_py>>,open("map.json","w"))
PY
printf '%s\\n' "mkfs.ext4 -J size=<<jm>> <<d>>" "mount -o data=ordered,barrier=1 <<d>> /mnt/x" > cmd.txt"""


def s13b(ctx):
    s13(ctx)
    ctx.data['map_py'] = json.dumps(ctx.data['map'])


mission(13, 'mkfs.ext2・mkfs.ext3・mkfs.ext4の違いとジャーナル・バリア',
        'mkfs.ext2 はジャーナル無し、mkfs.ext3 はジャーナル付き、mkfs.ext4 はさらに extent など新機能を使います。ジャーナルは更新の途中で電源が落ちても整合を保つ仕組みで、バリア(barrier)は書込み順序をディスクのキャッシュ越しに守る設定です。',
        ['記録から種別をmap.jsonへ', 'mkfs.ext4とmountの行をcmd.txtへ'], s13b, c13, SOL13,
        ['python3 -c "import json;json.dump({\'A\':\'ext4\',\'B\':\'ext4\',\'C\':\'ext4\'},open(\'map.json\',\'w\'))"\nprintf \'%s\\n\' "mkfs.ext4 -J size=<<jm>> <<d>>" "mount -o data=ordered,barrier=1 <<d>> /mnt/x" > cmd.txt',
         'python3 - <<\'PY\'\nimport json\njson.dump(<<map_py>>,open("map.json","w"))\nPY\nprintf \'%s\\n\' "mkfs.ext4 -J size=<<jm>> <<d>>" "mount -o nobarrier <<d>> /mnt/x" > cmd.txt'],
        'ext3以降の has_journal はメタデータの変更をログに先に書き、クラッシュ後はログを再生して素早く整合させます。data=ordered は既定でデータ→メタデータの順を守ります。barrier=1 はディスクの書込みキャッシュを順序付きでフラッシュし、nobarrier は速度と引換えに電源断で壊れる危険を高めるため、バッテリ付きRAID以外では避けます。',
        '機能の有無でext2/3/4を判別します。', 'ジャーナル無しならext2、extentまであればext4。')


# ---------------------------------------------------------------- 14 fsck.ext*, mklost+found
def s14(ctx):
    t = secrets.choice(['ext2', 'ext3', 'ext4'])
    d = dev() + '1'
    inos = sorted(secrets.SystemRandom().sample(range(12, 900), 3))
    ctx.data.update(t=t, d=d, inos=inos)
    put(ctx, 'record.txt', f'$ fsck.{t} -fn {d}   (type {t})\nPass 1: Checking inodes, blocks, and sizes\nPass 3: Checking directory connectivity\n/lost+found not found.  Create? no\n'
        'Pass 4: Checking reference counts\n' + ''.join(f'Unattached inode {i}\nConnect to /lost+found? no\n' for i in inos) + 'Pass 5: Checking group summary information\n')
    ctx.write('requirements.txt', f'record.txtは種別{t}の{d}を読み取り専用でfsckした結果。orphans.jsonに orphans（孤立inode番号の昇順リスト）, lost_found_missing（真偽）を書く。'
              f'cmd.txtに(1)種別に合う fsck.{t} での強制(-f)・読み取り専用(-n)チェック(2)マウント直下で /lost+found を作り直す mklost+found、の2行。\n')


def c14(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'orphans.json')
    ctx.require(r.get('orphans') == d['inos'] and r.get('lost_found_missing') is True, 'Unattached inode の番号と、/lost+found not found かを確認。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    ctx.require(a[0] == 'fsck.' + d['t'] and a[-1] == d['d'] and '-n' in a and '-f' in a or (a[0] == 'fsck.' + d['t'] and '-fn' in a and a[-1] == d['d']), f'fsck.{d["t"]} -fn デバイス です。')
    ctx.require(b == ['mklost+found'], 'mklost+found だけを書きます（作業ディレクトリ直下に作る）。')


SOL14 = """python3 - <<'PY'
import json
json.dump({"orphans":<<inos>>,"lost_found_missing":True},open("orphans.json","w"))
PY
printf '%s\\n' "fsck.<<t>> -fn <<d>>" "mklost+found" > cmd.txt"""
mission(14, 'fsck.ext2/3/4とmklost+foundで孤立inodeと/lost+foundを扱う',
        'fsck.ext2・fsck.ext3・fsck.ext4 はどれも e2fsck の別名です。修復で見つかった孤立ファイルは /lost+found に入りますが、このディレクトリが消えていると接続できません。mklost+found で作り直します。',
        ['記録をorphans.jsonへ', 'fsckとmklost+foundをcmd.txtへ'], s14, c14, SOL14,
        ['printf \'%s\\n\' "fsck.<<t>> -y <<d>>" "mklost+found" > cmd.txt', 'printf \'%s\\n\' "fsck.<<t>> -fn <<d>>" "mkdir lost+found" > cmd.txt'],
        '/lost+found はファイルシステムの直下にある、fsck が孤立inodeを接続する場所です。事前に十分な大きさのブロックを確保してあり、mklost+found は同じ形で作り直します。-n は何も変更せず確認のみ、-y は全て自動修復で、先にバックアップがない状態の -y は避けます。fsck はマウント中のFSには実行しません。',
        '種別名がコマンド名になります。', 'fsck.ext? -fn と mklost+found。')


# ---------------------------------------------------------------- 15 cramfs / minix / bfs
def s15(ctx):
    nm = 'cr' + secrets.token_hex(2)
    ctx.data.update(nm=nm, ino=secrets.choice([32, 48, 64]), vol=secrets.token_hex(2))
    ctx.write('requirements.txt', f'小さな読み取り専用/旧式FSのイメージ作りを書く。cmd.txtに順に(1)rootdir から名前 {nm} の out.cramfs を作る mkfs.cramfs (2)それを検査する fsck.cramfs '
              f'(3)名前長30の1440ブロックの mini.img を作る mkfs.minix (4)inode数{ctx.data["ino"]}・ボリューム名{ctx.data["vol"]}の bfs.img を作る mkfs.bfs、の4行。\n')


def c15(ctx):
    d = ctx.data
    ls = cmds(ctx, 'cmd.txt', 4)
    ctx.require(ls[0] == ['mkfs.cramfs', '-n', d['nm'], 'rootdir', 'out.cramfs'], 'mkfs.cramfs -n 名前 ディレクトリ イメージ です。')
    ctx.require(ls[1] == ['fsck.cramfs', 'out.cramfs'], 'fsck.cramfs イメージ です。')
    ctx.require(ls[2] == ['mkfs.minix', '-n', '30', 'mini.img', '1440'], 'mkfs.minix -n 30 mini.img 1440 です。')
    ctx.require(ls[3][0] == 'mkfs.bfs' and val(ctx, ls[3], '-N') == str(d['ino']) and val(ctx, ls[3], '-V') == d['vol'] and ls[3][-1] == 'bfs.img', 'mkfs.bfs -N inode数 -V ボリューム名 bfs.img です。')


SOL15 = 'printf \'%s\\n\' "mkfs.cramfs -n <<nm>> rootdir out.cramfs" "fsck.cramfs out.cramfs" "mkfs.minix -n 30 mini.img 1440" "mkfs.bfs -N <<ino>> -V <<vol>> bfs.img" > cmd.txt'
mission(15, 'mkfs.cramfs・fsck.cramfs・mkfs.minix・mkfs.bfsで特殊FSを作る',
        'cramfs は圧縮した読み取り専用FSで、組込みの初期RAMDISKなどで使われました。minix と bfs は歴史的なFSです。いずれも util-linux のmkfs系で、通常ファイルをイメージにして試せます。',
        ['4行をcmd.txtへ'], s15, c15, SOL15,
        ['printf \'%s\\n\' "mkfs.cramfs out.cramfs rootdir" "fsck.cramfs out.cramfs" "mkfs.minix -n 30 mini.img 1440" "mkfs.bfs -N <<ino>> -V <<vol>> bfs.img" > cmd.txt',
         'printf \'%s\\n\' "mkfs.cramfs -n <<nm>> rootdir out.cramfs" "fsck.cramfs out.cramfs" "mkfs.minix mini.img 1440" "mkfs.bfs -V <<vol>> bfs.img" > cmd.txt'],
        'mkfs.cramfs は入力ディレクトリを先に、出力ファイルを後に指定し、-n でFS名を付けます。fsck.cramfs は検査専用です。mkfs.minix の -n は名前長（14か30）、末尾のブロック数でサイズを決めます。mkfs.bfs は -N でinode数、-V でボリューム名を指定します。cramfsは新規には squashfs が主流です。',
        'cramfsは 入力ディレクトリ→出力ファイル の順です。', 'mkfs.cramfs -n / fsck.cramfs / mkfs.minix -n / mkfs.bfs -N -V。')


# ---------------------------------------------------------------- 16 swaplabel / swapoff
def s16(ctx):
    d = dev() + '2'
    new = 'swap-' + secrets.token_hex(2)
    ctx.data.update(d=d, new=new)
    put(ctx, 'record.txt', f'$ swapon --show\nNAME TYPE SIZE USED PRIO\n{d} partition 4G 120M -2\n$ free -m\n              total   used   free\nMem:           7900   3100   2800\nSwap:          4095    120   3975\n')
    ctx.write('requirements.txt', f'{d}のスワップのラベルを {new} に変える。使用中は変更しないので、cmd.txtに順に(1)スワップ停止の swapoff (2)ラベル付与の swaplabel -L (3)再開の swapon、の3行を書く。'
              f'実メモリの空き(2800M)がスワップ使用量(120M)を上回るので swapoff は安全。\n')


def c16(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = cmds(ctx, 'cmd.txt', 3)
    ctx.require(ls == [['swapoff', d['d']], ['swaplabel', '-L', d['new'], d['d']], ['swapon', d['d']]], 'swapoff → swaplabel -L → swapon の順です。')


SOL16 = 'printf \'%s\\n\' "swapoff <<d>>" "swaplabel -L <<new>> <<d>>" "swapon <<d>>" > cmd.txt'
mission(16, 'swapoffとswaplabelでスワップのラベルを安全に変える',
        'スワップ領域のラベルやUUIDは swaplabel で変更できますが、使用中のスワップに行うのは危険です。swapoff で止める前に、使用中ページを戻せるだけの空きメモリがあるか確認します。',
        ['3行をcmd.txtへ'], s16, c16, SOL16,
        ['printf \'%s\\n\' "swaplabel -L <<new>> <<d>>" "swapoff <<d>>" "swapon <<d>>" > cmd.txt', 'printf \'%s\\n\' "swapoff <<d>>" "swaplabel <<new>> <<d>>" "swapon <<d>>" > cmd.txt'],
        'swapoff はスワップ内のページを物理メモリへ読み戻すため、空きが足りないとメモリ不足(OOM)や極端な遅延を招きます。swaplabel -L でラベル、-U でUUIDを変更し、変更後は swapon で再開します。fstab が LABEL=/UUID= で指す場合は、変更した値に合わせて更新します。',
        '止める→変える→戻す、の順序です。', 'swapoff dev / swaplabel -L ラベル dev / swapon dev。')


# ---------------------------------------------------------------- 17 wipefs
def s17(ctx):
    t, off = secrets.choice([('ext4', '0x438'), ('xfs', '0x0'), ('swap', '0xff6'), ('vfat', '0x52')])
    d = dev() + '1'
    ctx.data.update(t=t, off=off, d=d)
    put(ctx, 'record.txt', f'$ wipefs {d}\nDEVICE OFFSET TYPE UUID LABEL\n{d.split("/")[-1]} {off} {t} 1111-2222 old\n$ wipefs /dev/sdz\nDEVICE OFFSET TYPE\nsdz 0x200 gpt\nsdz 0x1fe PMBR\n')
    ctx.write('requirements.txt', f'{d}の古い {t} シグネチャだけを消したい（他は残す、-a は使わない）。cmd.txtに(1)実際には消さず確認する wipefs -n（-o でオフセット指定）(2)消す前の退避付き実行の wipefs --backup -o、の2行。\n')


def c17(ctx):
    need_ro(ctx)
    d = ctx.data
    a, b = cmds(ctx, 'cmd.txt', 2)
    ctx.require(a == ['wipefs', '-n', '-o', d['off'], d['d']], f"wipefs -n -o {d['off']} デバイス です。")
    ctx.require(b == ['wipefs', '--backup', '-o', d['off'], d['d']], f"wipefs --backup -o {d['off']} デバイス です。")


SOL17 = 'printf \'%s\\n\' "wipefs -n -o <<off>> <<d>>" "wipefs --backup -o <<off>> <<d>>" > cmd.txt'
mission(17, 'wipefsでシグネチャを確認し退避してから消す',
        'mkfs の前に古いファイルシステムの印が残っていると、blkid が誤認識します。wipefs は引数なしで一覧、-n で試行、-o でオフセット指定、--backup で消す前の内容を保存できます。',
        ['2行をcmd.txtへ'], s17, c17, SOL17,
        ['printf \'%s\\n\' "wipefs -n -a <<d>>" "wipefs -a <<d>>" > cmd.txt', 'printf \'%s\\n\' "wipefs -o <<off>> <<d>>" "wipefs --backup -o <<off>> <<d>>" > cmd.txt'],
        'wipefs -a は全シグネチャを消します。パーティションテーブルは別デバイス（ディスク全体）側のシグネチャなので、パーティションのシグネチャだけなら -o（オフセット）や -t（種別）で絞ります。--backup は ~/wipefs-名前-オフセット.bak に消した領域を保存し、dd で書き戻せます。',
        '先に -n、消す前に --backup。', 'wipefs -n -o オフセット デバイス。')


# ---------------------------------------------------------------- 18 zramctl / isosize
def s18(ctx):
    k = secrets.choice([2, 3, 4])
    comp = 50 + secrets.randbelow(100)
    data = comp * k
    sec = 100000 + secrets.randbelow(300000)
    ctx.data.update(ratio=float(k), iso=sec * 2048, size=secrets.choice([256, 512, 1024]))
    put(ctx, 'record.txt', f'$ zramctl\nNAME ALGORITHM DISKSIZE DATA COMPR TOTAL STREAMS MOUNTPOINT\n/dev/zram0 zstd 1G {data}M {comp}M {comp + 5}M 4 [SWAP]\n'
        f'$ isosize -x install.iso\nsector count: {sec}, sector size: 2048\n')
    ctx.write('requirements.txt', f'record.txtから result.json に ratio（DATA÷COMPR、小数可）, iso_bytes（ISOのバイト数）を書く。cmd.txtに(1){ctx.data["size"]}Mのzstd圧縮の空きzramを作る zramctl --find (2)ISOサイズを表示する isosize -x install.iso の2行。\n')


def c18(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'result.json')
    ctx.require(isinstance(r.get('ratio'), (int, float)) and abs(r['ratio'] - d['ratio']) < 0.1, 'ratio は DATA ÷ COMPR です。')
    ctx.require(r.get('iso_bytes') == d['iso'], 'iso_bytes は sector count × sector size です。')
    a, b = cmds(ctx, 'cmd.txt', 2)
    head(ctx, a, 'zramctl')
    ctx.require('--find' in a and val(ctx, a, '--size') == f'{d["size"]}M' and val(ctx, a, '--algorithm') == 'zstd', 'zramctl --find --size ..M --algorithm zstd です。')
    ctx.require(b == ['isosize', '-x', 'install.iso'], 'isosize -x install.iso です。')


SOL18 = """python3 - <<'PY'
import json
json.dump({"ratio":<<ratio>>,"iso_bytes":<<iso>>},open("result.json","w"))
PY
printf '%s\\n' "zramctl --find --size <<size>>M --algorithm zstd" "isosize -x install.iso" > cmd.txt"""
mission(18, 'zramctlとisosizeで圧縮メモリとISOサイズを読む',
        'zram は圧縮したメモリ上のブロックデバイスで、スワップやtmp領域に使えます。zramctl の列から圧縮率を読み、isosize は ISO9660 イメージの大きさをセクタ数から表示します。',
        ['result.jsonへ数値', 'zramctlとisosizeをcmd.txtへ'], s18, c18, SOL18,
        ['printf \'%s\\n\' "zramctl --size <<size>>M" "isosize install.iso" > cmd.txt', 'printf \'%s\\n\' "zramctl --find --size <<size>>M --algorithm lz4" "isosize -x install.iso" > cmd.txt'],
        'zramctl は割当(--find --size)・アルゴリズム(--algorithm)・解除(--reset)を扱い、DATA が非圧縮、COMPR が圧縮後のサイズです。isosize は既定でバイト数、-x でセクタ数とセクタサイズを表示します。zramのスワップは swapon -p で高い優先度を付けて併用するのが定番です。',
        '圧縮率は DATA ÷ COMPR。', 'zramctl --find --size .. --algorithm .. / isosize -x。')


# ---------------------------------------------------------------- 19 tune2fs / lsblk / blkid
def s19(ctx):
    d = dev() + '1'
    blocks = 100000 * (1 + secrets.randbelow(9))
    ctx.data.update(d=d, pct=secrets.choice([1, 2]), blocks=blocks, res=blocks * 5 // 100)
    put(ctx, 'record.txt', f'$ tune2fs -l {d}\nBlock count: {blocks}\nReserved block count: {blocks * 5 // 100}\nMount count: 30\nMaximum mount count: 30\nCheck interval: 15552000 (6 months)\n')
    ctx.write('requirements.txt', f'record.txtの予約ブロック率(%)を reserved.json の percent に整数で書く。データ専用のため予約を{ctx.data["pct"]}%へ下げ、マウント回数による定期チェックも無効にしたい。cmd.txtに(1)tune2fs -m と -c 0 を1行で{d}へ (2)UUIDだけを出す blkid -s UUID -o value (3)lsblk -f の3行。\n')


def c19(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'reserved.json').get('percent') == 5, '予約率は Reserved ÷ Block count = 5% です。')
    a, b, c = cmds(ctx, 'cmd.txt', 3)
    ctx.require(a == ['tune2fs', '-m', str(d['pct']), '-c', '0', d['d']] or a == ['tune2fs', '-c', '0', '-m', str(d['pct']), d['d']], 'tune2fs -m 率 -c 0 デバイス です。')
    ctx.require(b == ['blkid', '-s', 'UUID', '-o', 'value', d['d']], 'blkid -s UUID -o value デバイス です。')
    ctx.require(c[:2] == ['lsblk', '-f'], 'lsblk -f です。')


SOL19 = """echo '{"percent":5}' > reserved.json
printf '%s\\n' "tune2fs -m <<pct>> -c 0 <<d>>" "blkid -s UUID -o value <<d>>" "lsblk -f <<d>>" > cmd.txt"""
mission(19, 'tune2fs・blkid・lsblkで調整と識別を行う',
        'tune2fs はext系の調整（予約ブロック、チェック間隔、ラベルなど）、blkid はUUID/種別の取得、lsblk はデバイスの木構造表示です。データ専用ボリュームの予約領域を見直します。',
        ['reserved.jsonに現在の予約率', '3行をcmd.txtへ'], s19, c19, SOL19,
        ['echo \'{"percent":1}\' > reserved.json\nprintf \'%s\\n\' "tune2fs -m <<pct>> -c 0 <<d>>" "blkid -s UUID -o value <<d>>" "lsblk -f <<d>>" > cmd.txt',
         'echo \'{"percent":5}\' > reserved.json\nprintf \'%s\\n\' "tune2fs -r <<pct>> <<d>>" "blkid <<d>>" "lsblk <<d>>" > cmd.txt'],
        'tune2fs -l は設定表示、-m は予約率(%)、-r は予約ブロック数、-c は最大マウント回数、-i はチェック間隔、-L はラベルです。予約はroot専用の余裕で、システム領域では減らしすぎないこと。blkid -s UUID -o value はスクリプト向けに値だけを出し、lsblk -f は種別・ラベル・UUID・マウント先を表示します。',
        '-m は率、-r はブロック数です。', 'tune2fs -m 率 -c 0 dev / blkid -s UUID -o value / lsblk -f。')


# ---------------------------------------------------------------- 20 fstab, /proc/mounts, /proc/partitions
def s20(ctx):
    ru, du, su = ('-'.join(secrets.token_hex(n) for n in (4, 2, 2, 2, 6)) for _ in range(3))
    blocks = 1048576 * (2 + secrets.randbelow(30))
    ctx.data.update(ru=ru, du=du, su=su, gib=blocks // 1048576)
    put(ctx, 'fstab.broken', f'UUID={ru} / ext4 errors=remount-ro\nUUID={du} /data ext4 defaults,noatime\nUUID={su} none swap\ntmpfs /tmp tmpfs size=256m,mode=1777 0\n')
    put(ctx, 'proc.txt', f'$ cat /proc/partitions\nmajor minor  #blocks  name\n   8       16   {blocks * 2} sdb\n   8       17   {blocks} sdb1\n\n'
        f'$ grep -E "/data|/boot" /proc/mounts\n/dev/sdb1 /data ext4 rw,noatime 0 0\n/dev/sda1 /boot ext4 ro,relatime 0 0\n')
    ctx.write('requirements.txt', 'fstab.brokenは6列(デバイス, マウント先, 種別, オプション, dump, pass)が揃っていない。fstab.fixedに直す: /(UUID root, errors=remount-ro, 0 1) /data(noatime,nofail, 0 2) swap(none, sw, 0 0) /tmp(tmpfs, size=256m,mode=1777, 0 0)。'
              'さらに proc.txt（/proc/partitions の#blocksは1KiB単位）から sdb1 のGiB数と、/proc/mounts で実際に ro の挙動のマウント先を info.json に size_gib, ro_mounts(リスト) で書く。\n')


def c20(ctx):
    need_ro(ctx)
    d = ctx.data
    rows = {}
    for ln in ctx.need_file('fstab.fixed').splitlines():
        if ln.strip() and not ln.startswith('#'):
            f = ln.split()
            ctx.require(len(f) == 6, f'6列必要です: {ln}')
            rows[f[1]] = f
    ctx.require(rows.get('/', [''] * 6)[0] == 'UUID=' + d['ru'] and rows['/'][2:] == ['ext4', 'errors=remount-ro', '0', '1'], '/ の行を確認。')
    f = rows.get('/data', [''] * 6)
    ctx.require(f[0] == 'UUID=' + d['du'] and f[2] == 'ext4' and {'noatime', 'nofail'} <= set(f[3].split(',')) and f[4:] == ['0', '2'], '/data は noatime,nofail、0 2。')
    ctx.require(rows.get('none', [''] * 6)[:1] == ['UUID=' + d['su']] and rows['none'][2:] == ['swap', 'sw', '0', '0'] , 'swap行は UUID none swap sw 0 0。')
    ctx.require(rows.get('/tmp', [''] * 6) == ['tmpfs', '/tmp', 'tmpfs', 'size=256m,mode=1777', '0', '0'], '/tmp の行。')
    r = rj(ctx, 'info.json')
    ctx.require(r.get('size_gib') == d['gib'], '#blocks(1KiB単位)を1048576で割ります。')
    ctx.require(sorted(r.get('ro_mounts', [])) == ['/boot'], '/proc/mounts の4列目が ro のものだけです。')


SOL20 = """printf 'UUID=<<ru>> / ext4 errors=remount-ro 0 1\\nUUID=<<du>> /data ext4 noatime,nofail 0 2\\nUUID=<<su>> none swap sw 0 0\\ntmpfs /tmp tmpfs size=256m,mode=1777 0 0\\n' > fstab.fixed
echo '{"size_gib":<<gib>>,"ro_mounts":["/boot"]}' > info.json"""
mission(20, '/etc/fstabの6列とオプション、/proc/mounts・/proc/partitionsを読む',
        '/etc/fstab は起動時のマウント設定、/proc/mounts は今の実際の状態、/proc/partitions はカーネルが見ているパーティション一覧（1KiB単位）です。壊れたfstabを直し、実状態を照合してください。',
        ['fstab.fixedを書く', 'info.jsonに実測値'], s20, c20, SOL20,
        ['printf \'UUID=<<ru>> / ext4 errors=remount-ro 0 1\\nUUID=<<du>> /data ext4 defaults 0 2\\nUUID=<<su>> none swap sw 0 0\\ntmpfs /tmp tmpfs size=256m,mode=1777 0 0\\n\' > fstab.fixed\necho \'{"size_gib":<<gib>>,"ro_mounts":["/boot"]}\' > info.json',
         'printf \'UUID=<<ru>> / ext4 errors=remount-ro 0 1\\nUUID=<<du>> /data ext4 noatime,nofail 0 2\\nUUID=<<su>> none swap sw 0 0\\ntmpfs /tmp tmpfs size=256m,mode=1777 0 0\\n\' > fstab.fixed\necho \'{"size_gib":<<gib>>,"ro_mounts":["/boot","/data"]}\' > info.json'],
        'fstab の6列は デバイス・マウント先・種別・オプション・dump・fsck順序（rootは1、他は2、不要は0）です。nofail は起動時にデバイスが無くても止まらず、noatime はアクセス時刻の更新を省いて書込みを減らします。誤った fstab は起動不能を招くため、変更後は findmnt --verify と mount -a で確認します。/proc/mounts はカーネル視点の実状態で、ro/rw の最終確認に使います。',
        '列の数と、dump/pass の意味を確認します。', '6列そろえ、/proc/partitions の#blocksは1KiB単位。')


# ---------------------------------------------------------------- 21 /media vs /mnt, bind/tmpfs/overlay
def s21(ctx):
    t = secrets.token_hex(2)
    ctx.data.update(t=t)
    ctx.write('requirements.txt', f'place.json に usb_auto（USBメモリが自動マウントされる先のディレクトリ）と manual_temp（管理者が一時的に手動マウントする先）を書く（/media か /mnt）。'
              f'cmd.txtに順に(1)src-{t} を view-{t} へバインドマウント (2)tmpfsを scratch-{t} へサイズ64m・mode=1777でマウント (3)overlayを merged-{t} へ（lowerdir=base-{t}, upperdir=up-{t}, workdir=wk-{t}）マウント、の3行。/lost+found は各FS直下の fsck 用で、ここには手動でファイルを置かない。\n')


def c21(ctx):
    t = ctx.data['t']
    r = rj(ctx, 'place.json')
    ctx.require(r.get('usb_auto') == '/media' and r.get('manual_temp') == '/mnt', '自動マウントは /media、手動の一時マウントは /mnt です。')
    a, b, c = cmds(ctx, 'cmd.txt', 3)
    ctx.require(a in (['mount', '--bind', 'src-' + t, 'view-' + t], ['mount', '-o', 'bind', 'src-' + t, 'view-' + t]), 'mount --bind 元 先 です。')
    ctx.require(b[:3] == ['mount', '-t', 'tmpfs'] and b[-1] == 'scratch-' + t and set(val(ctx, b, '-o').split(',')) == {'size=64m', 'mode=1777'}, 'mount -t tmpfs -o size=64m,mode=1777 tmpfs scratch-.. です。')
    ctx.require(c[:3] == ['mount', '-t', 'overlay'] and c[-1] == 'merged-' + t, 'mount -t overlay overlay -o ... merged-.. です。')
    o = dict(x.split('=', 1) for x in val(ctx, c, '-o').split(','))
    ctx.require(o == {'lowerdir': 'base-' + t, 'upperdir': 'up-' + t, 'workdir': 'wk-' + t}, 'lowerdir/upperdir/workdir を指定します。')


SOL21 = """echo '{"usb_auto":"/media","manual_temp":"/mnt"}' > place.json
printf '%s\\n' "mount --bind src-<<t>> view-<<t>>" "mount -t tmpfs -o size=64m,mode=1777 tmpfs scratch-<<t>>" "mount -t overlay overlay -o lowerdir=base-<<t>>,upperdir=up-<<t>>,workdir=wk-<<t>> merged-<<t>>" > cmd.txt"""
mission(21, '/mediaと/mntの使い分け、bind・tmpfs・overlayのマウント',
        'ディレクトリは /media（デスクトップが自動でリムーバブルメディアをマウントする場所）と /mnt（管理者が手動で一時マウントする場所）で使い分けます。さらに特殊なマウント: ディレクトリを別の場所に見せる bind、メモリ上の tmpfs、層を重ねる overlay を書いてください。',
        ['place.jsonに使い分け', '3つのマウントをcmd.txtへ'], s21, c21, SOL21,
        ['echo \'{"usb_auto":"/mnt","manual_temp":"/media"}\' > place.json\nprintf \'%s\\n\' "mount --bind src-<<t>> view-<<t>>" "mount -t tmpfs -o size=64m,mode=1777 tmpfs scratch-<<t>>" "mount -t overlay overlay -o lowerdir=base-<<t>>,upperdir=up-<<t>>,workdir=wk-<<t>> merged-<<t>>" > cmd.txt',
         'echo \'{"usb_auto":"/media","manual_temp":"/mnt"}\' > place.json\nprintf \'%s\\n\' "mount src-<<t>> view-<<t>>" "mount -t tmpfs tmpfs scratch-<<t>>" "mount -t overlay overlay -o lowerdir=base-<<t>>,upperdir=up-<<t>> merged-<<t>>" > cmd.txt'],
        'bind は同じ実体を別パスに見せ（読み取り専用にするには mount -o remount,bind,ro）、tmpfs はRAM上でサイズ制限を -o size= で付け、overlay は読み取り専用の lowerdir に書込み用の upperdir を重ね workdir（upperと同じFS上の空ディレクトリ）が必要です。/lost+found は ext系の直下にあるfsck用の領域で、マウントポイントとは無関係に触らないこと。',
        'bind/tmpfs/overlay はいずれも mount の -t と -o で指定します。', 'mount --bind / -t tmpfs -o size=,mode= / -t overlay -o lowerdir=,upperdir=,workdir=。')


# ---------------------------------------------------------------- 22 ext4 vs xfs vs btrfs, health flow
def s22(ctx):
    ids = list('ABCDEF')
    secrets.SystemRandom().shuffle(ids)
    steps = ['backup', 'dmesg', 'smart_health', 'smart_attr', 'fsck_n', 'badblocks_ro']
    ctx.data.update(ids=ids, steps=steps)
    names = {'backup': 'rsyncで別ディスクへバックアップ', 'dmesg': 'dmesg でI/Oエラーを確認', 'smart_health': 'smartctl -H で自己診断結果',
             'smart_attr': 'smartctl -A で属性（再割当セクタ等）', 'fsck_n': 'fsck -n で読み取り専用の整合性検査', 'badblocks_ro': 'badblocks の読み取りテスト'}
    shuf = steps[:]
    secrets.SystemRandom().shuffle(shuf)
    ctx.data['map'] = {ids[i]: shuf[i] for i in range(6)}
    ctx.data['flow'] = [next(k for k, v in ctx.data['map'].items() if v == s) for s in steps]
    put(ctx, 'steps.txt', ''.join(f'{ids[i]}: {names[shuf[i]]}\n' for i in range(6)))
    ctx.write('requirements.txt', 'plan.jsonに2つ書く。(1)fs: 次の用途に合うFS（ext4/xfs/btrfs）を scenario→FS で。large_media=数TBの巨大ファイル並列書込み, snapshot=スナップショットとチェックサム・圧縮が必須, shrinkable=後でオンラインに近い形で縮小したい汎用 ext4が好ましい。'
              '(2)health: steps.txtの診断手順のIDを、故障しかけのディスクの定石順（データ保護→ログ→SMART健康→SMART属性→読み取り専用検査→読み取りテスト）で並べたリスト。\n')


def c22(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'plan.json')
    ctx.require(r.get('fs') == {'large_media': 'xfs', 'snapshot': 'btrfs', 'shrinkable': 'ext4'}, '巨大ファイル→xfs、スナップショット→btrfs、縮小可能→ext4（xfsは縮小不可）。')
    ctx.require(r.get('health') == d['flow'], '最初にバックアップ、破壊しない検査から順に並べます。')


SOL22 = """python3 - <<'PY'
import json
json.dump({"fs":{"large_media":"xfs","snapshot":"btrfs","shrinkable":"ext4"},"health":<<flow>>},open("plan.json","w"))
PY"""
mission(22, 'ext4・xfs・btrfsの選択基準とディスク健康診断の流れ',
        'ファイルシステムは用途で選びます。ext4は汎用で縮小もでき、xfsは大きなファイルと並列書込みに強く縮小不可、btrfsはスナップショット・チェックサム・圧縮を持ちます。壊れかけのディスクを調べる順序も、データ保護を最優先に整理します。',
        ['plan.jsonにFS選択と診断手順'], s22, c22, SOL22,
        ['python3 - <<\'PY\'\nimport json\njson.dump({"fs":{"large_media":"ext4","snapshot":"xfs","shrinkable":"btrfs"},"health":<<flow>>},open("plan.json","w"))\nPY',
         'python3 - <<\'PY\'\nimport json\njson.dump({"fs":{"large_media":"xfs","snapshot":"btrfs","shrinkable":"ext4"},"health":<<flow>>[::-1]},open("plan.json","w"))\nPY'],
        'xfsは拡張のみ、ext4は縮小可、btrfsは copy-on-write によるスナップショットとデータのチェックサムがあります。不調なディスクは、まずバックアップ、次に dmesg と smartctl -H/-A で兆候を見て、書込みを伴わない fsck -n と badblocks の読み取りテストへ進みます。SMARTの再割当セクタが増えるなら即交換です。',
        '破壊しない検査を先に、データ保護が最優先です。', 'steps.txtの内容を見て、IDを順序のリストにします。')
