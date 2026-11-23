"""Stage 25: ハッシュ・テキスト・圧縮・シェル組み込みの総ざらい。サンドボックス内の偽データと標準ツールだけを使う。"""
import gzip
import hashlib
import json
import lzma
import os
import re
import secrets
import shlex
import stat
import subprocess
from pathlib import Path

from engine.runner import register

S = 25
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・デバイス・ネットワークは変更せず、rootも使いません。"
        "データは訓練用の偽物で、環境依存の値は採取済みの出力から診断します。")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text, readonly=True):
    ctx.write(name, text)
    if readonly:
        ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(sha(ctx.need_file(name)) == h, name + ' は原本です。変更しないでください。')


def one_line(ctx, name):
    ls = [x for x in ctx.need_file(name).splitlines() if x.strip()]
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0].strip()


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def run(ctx, *argv, inp=None):
    r = subprocess.run(list(argv), cwd=ctx.work, capture_output=True, text=True, timeout=20, input=inp)
    return r


def out(ctx, *argv):
    return run(ctx, *argv).stdout


def script_out(ctx, name, *args):
    ctx.require(ctx.exists(name), name + ' が見つかりません。')
    try:
        r = subprocess.run(['bash', name, *args], cwd=ctx.work, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        ctx.fail(name + ' が終わりません。待ち続けていないか確認します。')
    return r


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'25-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='実行する前に対象を確認し、結果を別の手段で検証します。元データは必ず原本のまま残しましょう。')


# ---------------------------------------------------------------- 1 hash families
def s1(ctx):
    tag = secrets.token_hex(8)
    put(ctx, 'payload.bin', ''.join(f'release-{tag}-{i}\n' for i in range(5)))
    ctx.write('requirements.txt', 'payload.binのmd5sum, sha1sum, b2sum, cksumの値（先頭の1項目だけ）を「ツール名 値」の形でdigests.txtに、この順で4行書く。\n')


def c1(ctx):
    need_ro(ctx)
    ls = ctx.need_file('digests.txt').splitlines()
    ctx.require(len(ls) == 4, '4行（md5sum, sha1sum, b2sum, cksum）で書きます。')
    for line, t in zip(ls, ['md5sum', 'sha1sum', 'b2sum', 'cksum']):
        f = line.split()
        ctx.require(len(f) == 2 and f[0] == t, f'{t} の行を決められた順に「ツール名 値」で書きます。')
        ctx.require(f[1] == out(ctx, t, 'payload.bin').split()[0], f'{t} の値が違います。')


SOL1 = 'for t in md5sum sha1sum b2sum cksum; do echo "$t $($t payload.bin | cut -d\' \' -f1)"; done > digests.txt'
mission(1, 'md5sum・sha1sum・b2sum・cksumの出力を並べる',
        '用意されたバイナリの配布物について、古い互換用のmd5sumとsha1sum、現代的で高速なb2sum、誤り検出専用のcksumの値を一覧にします。ツールごとに出力の桁数と用途が違うことを確かめましょう。',
        ['4つのツールで同じファイルの値を得る', 'digests.txtに順番通り書く'], s1, c1, SOL1,
        ["for t in sha256sum sha256sum sha256sum sha256sum; do echo \"$t $($t payload.bin | cut -d' ' -f1)\"; done > digests.txt",
         "md5sum payload.bin > digests.txt"],
        'md5sumとsha1sumは衝突攻撃が実用化済みで、改ざん検知には不向きです。重複検出や壊れ検知なら十分です。b2sum(BLAKE2)は高速で安全性が高く、cksumはCRCによる転送エラー検出用で悪意ある改変には無力です。用途で選びます。',
        '4つとも「値 ファイル名」の形式で出力します。', 'ループでツール名を変え、cutで先頭の項目を取ります。')


# ---------------------------------------------------------------- 2 tamper
def s2(ctx):
    names = [f'pkg-{c}-{secrets.token_hex(2)}.tgz' for c in 'abcd']
    sums, bad = [], []
    k = secrets.randbelow(2) + 1
    badset = set(secrets.SystemRandom().sample(range(4), k))
    lines = ''
    for i, n in enumerate(names):
        body = f'content-{n}-{secrets.token_hex(6)}\n'
        lines += f'{hashlib.sha256(body.encode()).hexdigest()}  {n}\n'
        if i in badset:
            bad.append(n)
            body += 'injected\n'
        put(ctx, n, body)
    put(ctx, 'SHA256SUMS', lines)
    ctx.data['bad'] = sorted(bad)
    ctx.write('requirements.txt', 'SHA256SUMSと照合して改ざんされたファイル名だけを、ソート済みで1行ずつtampered.txtに書く。SHA256SUMSや配布物は直さない。\n')


def c2(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('tampered.txt').split() == ctx.data['bad'], '照合に失敗したファイル名だけを昇順で書きます。')


SOL2 = 'LC_ALL=C sha256sum -c SHA256SUMS 2>/dev/null | grep FAILED | cut -d: -f1 | sort > tampered.txt'
mission(2, 'sha256sum -cでダウンロードを検証して改ざんを見つける',
        'ミラーから取得した4つのパッケージと検証用のハッシュ一覧があります。以前学んだ整合性の確認方法を使い、改ざんされたものを特定してください。',
        ['sha256sum -cで照合する', '失敗したファイル名をtampered.txtへ'], s2, c2, SOL2,
        ["sha256sum pkg-* > tampered.txt", "ls pkg-* > tampered.txt"],
        'sha*sum --checkは一覧のハッシュと実ファイルを再計算して比較し、OKかFAILEDを出します。ハッシュの一覧自体が改ざんされないよう、別経路や署名で入手することが前提です。--quietは失敗だけ、--statusは終了コードだけにします。',
        '一覧は「ハッシュ  ファイル名」の形式です。', '-cの出力のFAILED行を絞り込みます。日本語環境では表示が翻訳されるのでLC_ALL=Cを付けます。')


# ---------------------------------------------------------------- 3 manifests
def s3(ctx):
    ctx.mkdir('dist')
    ctx.data['names'] = []
    for i in range(3):
        n = f'dist/part{i}-{secrets.token_hex(2)}.bin'
        put(ctx, n, secrets.token_hex(20) + '\n')
        ctx.data['names'].append(n)
    ctx.write('requirements.txt', 'dist内の全ファイルについて、sha224sumでm224.sum、sha384sumでm384.sum、sha512sumでm512.sumを作る。それぞれ対応するツールの--checkが成功すること。\n')


def c3(ctx):
    need_ro(ctx)
    for bits in (224, 384, 512):
        m = f'm{bits}.sum'
        ls = [x for x in ctx.need_file(m).splitlines() if x.strip()]
        ctx.require(len(ls) == 3, f'{m} には3ファイル分の行が必要です。')
        r = run(ctx, f'sha{bits}sum', '--check', '--quiet', m)
        ctx.require(r.returncode == 0, f'sha{bits}sum --check が成功しません。種類を合わせます。')


SOL3 = 'for n in 224 384 512; do sha${n}sum dist/* > m$n.sum; done\nsha384sum --check m384.sum'
mission(3, 'sha224sum・sha384sum・sha512sumで検証用マニフェストを作る',
        '配布先ごとに要求されるハッシュ長が違います。配布物が置かれたディレクトリを探し、sha224sum、sha384sum、sha512sumで同じ内容のマニフェストを m224.sum・m384.sum・m512.sum として作り、--checkで自己検証します。',
        ['3種のマニフェスト m224.sum・m384.sum・m512.sum を作る', '--checkが成功する'], s3, c3, SOL3,
        ["for n in 224 384 512; do sha256sum dist/* > m$n.sum; done", "sha512sum dist/* > m224.sum; sha512sum dist/* > m384.sum; sha512sum dist/* > m512.sum"],
        'SHA-2は出力長が違うだけの兄弟で、sha224sumからsha512sumまで同じ作法です。マニフェストの行はハッシュ種別と一致している必要があり、検証には同じ種類のsha*sum --checkを使います。長いほど衝突に強い一方で、署名や規格が種類を指定する場合はそれに従います。',
        '種類によってコマンド名だけが変わります。', 'ループとシェル展開でコマンド名を組み立てます。')


# ---------------------------------------------------------------- 4 base32 / basenc
def s4(ctx):
    sec = secrets.token_hex(6) + '>>??~~'
    msg = 'message-' + secrets.token_hex(4)
    put(ctx, 'secret.txt', sec + '\n')
    put(ctx, 'incoming.b32', subprocess.run(['base32'], input=msg + '\n', capture_output=True, text=True).stdout)
    ctx.data['msg'] = msg
    ctx.write('requirements.txt', 'secret.txtをbase32でtoken.b32、basenc --base64urlでtoken.b64uに符号化。incoming.b32を復号してmessage.txtへ。\n')


def c4(ctx):
    need_ro(ctx)
    sec = ctx.need_file('secret.txt')
    r = run(ctx, 'base32', '-d', 'token.b32')
    ctx.require(r.returncode == 0 and r.stdout == sec, 'token.b32 は secret.txt のbase32です。')
    t = ctx.need_file('token.b64u')
    ctx.require('+' not in t and '/' not in t, 'URLセーフ形式では+と/を使いません。')
    r = run(ctx, 'basenc', '--base64url', '-d', 'token.b64u')
    ctx.require(r.returncode == 0 and r.stdout == sec, 'token.b64u は --base64url で符号化します。')
    ctx.require(ctx.need_file('message.txt').strip() == ctx.data['msg'], 'incoming.b32を復号して保存します。')


SOL4 = 'base32 secret.txt > token.b32\nbasenc --base64url secret.txt > token.b64u\nbase32 -d incoming.b32 > message.txt'
mission(4, 'base32・basencで符号化と復号をする',
        '設定の値を人が手入力するためにbase32、URLに載せるためにbasenc --base64urlで符号化します。受信したbase32形式のデータはbase32 -dで戻します。',
        ['2形式で符号化', '受信データを復号'], s4, c4, SOL4,
        ['base64 secret.txt > token.b32\nbase64 secret.txt > token.b64u\nbase64 -d incoming.b32 > message.txt',
         'base32 secret.txt > token.b32\nbase32 secret.txt > token.b64u\nbase32 -d incoming.b32 > message.txt'],
        'base32は大文字と数字だけで読み間違いに強く、basencはbase64url・base16・z85など多くの形式を切り替えられます。符号化は暗号化ではなく、誰でも元に戻せます。秘密の保護には使えません。',
        '+や/はURLでは意味を持つ文字です。', 'basenc --helpで形式の一覧を確認できます。')


# ---------------------------------------------------------------- 5 csplit / ptx
def s5(ctx):
    n = 3 + secrets.randbelow(3)
    txt = ''
    for i in range(n):
        txt += f'=== host-{secrets.token_hex(2)} ===\n' + ''.join(f'line {j} {secrets.token_hex(2)}\n' for j in range(2 + secrets.randbelow(2)))
    put(ctx, 'report.txt', txt)
    ctx.data['n'] = n
    put(ctx, 'notes.txt', 'the cache restarts the daemon\nthe daemon reads a config\nlogs of the cache rotate\n')
    put(ctx, 'ignore.txt', 'the\na\nof\n')
    ctx.write('requirements.txt', 'report.txtを「=== 」で始まる行ごとにcsplitで part-00.txt, part-01.txt ... に分割（空ファイルは作らない）。notes.txtからignore.txtの語を除いたptxの索引をindex.txtへ。\n')


def c5(ctx):
    need_ro(ctx)
    n = ctx.data['n']
    got = sorted(p.name for p in ctx.work.glob('part-*'))
    ctx.require(got == [f'part-{i:02d}.txt' for i in range(n)], f'part-00.txt から {n} 個だけ作ります。')
    ctx.require(all(ctx.read(g).startswith('=== ') for g in got), '各ファイルは見出し行から始まります。')
    ctx.require(''.join(ctx.read(g) for g in got) == ctx.read('report.txt'), '分割結果を連結すると原本に一致する必要があります。')
    ctx.require(ctx.need_file('index.txt') == out(ctx, 'ptx', '-i', 'ignore.txt', 'notes.txt'), 'ptx -i で無視語を指定した索引にします。')


SOL5 = "csplit -z -f part- -b '%02d.txt' report.txt '/^=== /' '{*}' > /dev/null\nptx -i ignore.txt notes.txt > index.txt"
mission(5, 'csplitでレポートを分割しptxで用語索引を作る',
        '複数ホストの結果を連結したレポートを、以前学んだ方法で見出しごとに切り出してください。今回はさらに ptx を使います。ptx はメモから用語の前後関係を並べた文脈付き索引(KWIC)を作る道具です。',
        ['csplitで見出しごとに分割', 'ptxの索引を作る'], s5, c5, SOL5,
        ["split -l 3 report.txt part-\nptx notes.txt > index.txt", "csplit report.txt '/^=== /' '{*}' > /dev/null\nptx -i ignore.txt notes.txt > index.txt"],
        'csplitは正規表現や行番号で区切ります。{*}で繰り返し、-zは空の断片を捨て、-fと-bで名前を整えます。splitは行数やバイト数で機械的に切る違いがあります。ptxは各語を中央に並べた索引を作り、-iで無視語（the, a など）を除きます。',
        '最初の区切りの前は空の断片になります。', '正規表現のパターンと{*}を使います。')


# ---------------------------------------------------------------- 6 diff3 / sdiff
def s6(ctx):
    base = [f'k{i}=v{i}' for i in range(1, 7)]
    a, b = 'mine-' + secrets.token_hex(2), 'theirs-' + secrets.token_hex(2)
    mine = list(base)
    mine[1] = 'k2=' + a
    theirs = list(base)
    theirs[4] = 'k5=' + b
    exp = list(base)
    exp[1], exp[4] = mine[1], theirs[4]
    put(ctx, 'old.conf', '\n'.join(base) + '\n')
    put(ctx, 'mine.conf', '\n'.join(mine) + '\n')
    put(ctx, 'theirs.conf', '\n'.join(theirs) + '\n')
    ctx.data['exp'] = exp
    ctx.write('requirements.txt', 'old.confを共通の祖先として、mine.confとtheirs.confをdiff3 -mで統合しmerged.confに。さらにsdiff -sでold.confとmine.confの差分行だけをchanges.txtに。\n')


def c6(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('merged.conf').splitlines() == ctx.data['exp'], '両者の変更が衝突なく取り込まれたmerged.confにします。')
    ctx.require(ctx.need_file('changes.txt') == out(ctx, 'sdiff', '-s', 'old.conf', 'mine.conf'), 'sdiff -s の出力をそのまま保存します。')


SOL6 = 'diff3 -m mine.conf old.conf theirs.conf > merged.conf\nsdiff -s old.conf mine.conf > changes.txt'
mission(6, 'diff3で三者統合しsdiffで並べて比較する',
        '同じ設定を二人が別々に編集しました。三者の差分を扱うdiff3で自動統合し、sdiffで左右に並べて変更行を確認します。',
        ['diff3 -mで統合', 'sdiff -sで差分行だけ保存'], s6, c6, SOL6,
        ['cp mine.conf merged.conf\ndiff -u old.conf mine.conf > changes.txt', 'diff3 -m old.conf mine.conf theirs.conf > merged.conf\nsdiff old.conf mine.conf > changes.txt'],
        'diff3は「自分・共通祖先・相手」の順に3ファイルを取り、-mで統合結果を出します。同じ場所を別々に変えると衝突マーカーが入ります。sdiffは2ファイルを左右に並べ、-sで同一行を省略します。順序を間違えると祖先の扱いが変わるので注意します。',
        '共通祖先は真ん中に置きます。', 'diff3 -m 自分 祖先 相手 の順です。')


# ---------------------------------------------------------------- 7 expand etc.
def s7(ctx):
    w = [secrets.token_hex(2) for _ in range(3)]
    put(ctx, 'tabbed.txt', f'ab\t{w[0]}\n\t{w[1]}\tx\n{w[2]}\tz\n')
    put(ctx, 'flat.txt', f'        {w[0]} end\n    {w[1]}\n{w[2]}  keep\n')
    ctx.write('number.txt', str(100000 + secrets.randbelow(900000)) + '\n')
    ctx.write('bytes.txt', str(10 ** 6 + secrets.randbelow(10 ** 9)) + '\n')
    ctx.write('requirements.txt', 'tabbed.txtのタブを4桁でexpandしspaced.txtへ。flat.txtの行頭の空白を4桁でunexpandしretabbed.txtへ。number.txtをfactorしprimes.txtへ、bytes.txtの値をnumfmt --to=iecで人間向けにhuman.txtへ。\n')


def c7(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('spaced.txt') == out(ctx, 'expand', '-t', '4', 'tabbed.txt'), 'タブ幅4でexpandします。')
    ctx.require(ctx.need_file('retabbed.txt') == out(ctx, 'unexpand', '-t', '4', 'flat.txt'), '行頭だけをタブ幅4でunexpandします。')
    n = ctx.need_file('number.txt').strip()
    ctx.require(ctx.need_file('primes.txt') == out(ctx, 'factor', n), 'factorの出力をそのまま保存します。')
    b = ctx.need_file('bytes.txt').strip()
    ctx.require(ctx.need_file('human.txt') == out(ctx, 'numfmt', '--to=iec', b), 'numfmt --to=iec の結果にします。')


SOL7 = 'expand -t 4 tabbed.txt > spaced.txt\nunexpand -t 4 flat.txt > retabbed.txt\nfactor $(cat number.txt) > primes.txt\nnumfmt --to=iec $(cat bytes.txt) > human.txt'
mission(7, 'expand・unexpand・factor・numfmtで整形と数値変換',
        '表示が崩れるタブ、数値の素因数、バイト数の単位表記など、小さな変換ツールをまとめて使います。',
        ['タブと空白を相互変換', '素因数分解と単位変換'], s7, c7, SOL7,
        ['cp tabbed.txt spaced.txt\ncp flat.txt retabbed.txt\ncp number.txt primes.txt\ncp bytes.txt human.txt',
         'expand tabbed.txt > spaced.txt\nunexpand flat.txt > retabbed.txt\nfactor $(cat number.txt) > primes.txt\nnumfmt --to=si $(cat bytes.txt) > human.txt'],
        'expandはタブを空白に、unexpandは空白をタブに戻します（既定は行頭のみ、-aで全体）。-tで桁幅を指定します。factorは素因数分解、numfmtは--to=iecで1024基準、--to=siで1000基準の単位に変換します。',
        '標準の桁幅は8です。', '-tで桁、--toで単位体系を指定します。')


# ---------------------------------------------------------------- 8 fallocate / filefrag
def s8(ctx):
    n = 3 + secrets.randbelow(7)
    ctx.data['mb'] = n
    names = ['app.db', 'cache.bin', 'mail.mbox', 'video.mkv']
    ext = secrets.SystemRandom().sample([2, 7, 41, 13], 4)
    ctx.data['worst'] = names[ext.index(41)]
    put(ctx, 'frag.txt', ''.join(f'{a}: {e} extents found\n' for a, e in zip(names, ext)))
    ctx.write('requirements.txt', f'fallocate で {n}MiB の領域を実際に確保したdisk.imgを作り、所有者のみ読み書き(600)にする。filefragの採取結果frag.txtから、断片化(extent数)が最大のファイル名をworst.txtへ。\n')


def c8(ctx):
    need_ro(ctx)
    p = ctx.p('disk.img')
    ctx.require(p.is_file() and p.stat().st_size == ctx.data['mb'] * 1048576, '指定サイズのdisk.imgを作ります。')
    ctx.require(p.stat().st_blocks * 512 >= p.stat().st_size * 0.9, 'truncateのスパースではなく、fallocateで領域を確保します。')
    ctx.require(stat.S_IMODE(p.stat().st_mode) == 0o600, '権限は600にします。')
    ctx.require(ctx.need_file('worst.txt').strip() == ctx.data['worst'], 'extent数が最大のファイルを書きます。')


SOL8 = ("fallocate -l <<mb>>M disk.img\nchmod 600 disk.img\nfilefrag disk.img > /dev/null 2>&1 || true\n"
        "awk -F': ' '{split($2,a,\" \"); print a[1], $1}' frag.txt | sort -n | tail -1 | cut -d' ' -f2 > worst.txt")
mission(8, 'fallocateで領域確保しfilefragの結果を診断',
        'ディスクイメージは実際にブロックを確保して作りたいので、truncateではなくfallocateを使います。さらに断片化の調査としてfilefragの採取結果から最悪のファイルを選びます。',
        ['fallocateで確保', 'filefrag結果から最大断片化を特定'], s8, c8, SOL8,
        ['truncate -s <<mb>>M disk.img\nchmod 600 disk.img\necho app.db > worst.txt', 'fallocate -l <<mb>>M disk.img\necho cache.bin > worst.txt'],
        'fallocateはファイル領域を先に確保し、書き込み時の容量不足や断片化を避けます（スワップファイル作成でも使います）。truncateは「穴あき」の疎ファイルです。filefragはextent（連続領域）の数を示し、数が多いほど断片化しています。FIEMAPが使えない環境があるので結果は参考値です。',
        'ブロックを実際に使うかが違いです。', 'awkでextent数を取り出して数値ソートします。')


# ---------------------------------------------------------------- 9 shred / stdbuf
def s9(ctx):
    ctx.write('secret.key', 'KEY-' + secrets.token_hex(16) + '\n')
    put(ctx, 'keep.key', 'KEEP-' + secrets.token_hex(8) + '\n')
    ctx.write('access.log', 'ok\n')
    ctx.write('requirements.txt', 'secret.keyをshredで2回上書き+最後にゼロ埋めし、削除まで行う（keep.keyは触らない）。tail -fで監視中のaccess.logからERRORだけを、パイプでも遅延せず1行ずつ出すstdbuf付きの1行をcmd.txtへ（実行はしない）。\n')


def c9(ctx):
    need_ro(ctx)
    ctx.require(not ctx.exists('secret.key'), 'secret.keyは削除します。')
    ctx.require(ctx.used('shred'), 'rmではなくshredで消去します。')
    t = toks(ctx, one_line(ctx, 'cmd.txt').replace('|', ' | '))
    ctx.require(t[:3] == ['tail', '-f', 'access.log'], 'tail -f access.log から始めます。')
    i = t.index('stdbuf') if 'stdbuf' in t else -1
    ctx.require(i > 0 and ('-oL' in t[i + 1:] or '--output=L' in t[i + 1:]), 'stdbuf -oL で出力を行バッファにします。')
    ctx.require('grep' in t[i + 1:] and 'ERROR' in t, 'stdbufはgrepの前に付けます。')


SOL9 = "shred -n 2 -z -u secret.key\necho 'tail -f access.log | stdbuf -oL grep ERROR' > cmd.txt"
mission(9, 'shredで安全に消去しstdbufでパイプの遅延を除く',
        '不要になった秘密鍵はrmではなくshredで上書き消去します。監視ログの絞り込みでは、パイプ先のバッファのせいで行が遅れて出るのをstdbufで避けます。',
        ['shredで消去', 'stdbuf付きの監視コマンド'], s9, c9, SOL9,
        ['rm secret.key\necho "tail -f access.log | grep ERROR" > cmd.txt', 'shred secret.key\necho "tail -f access.log | grep --line-buffered ERROR" > cmd.txt'],
        'shredはファイルの中身を上書きしますが、ジャーナルFSやSSD、スナップショットでは完全消去を保証しません。-nで回数、-zで最後のゼロ埋め、-uで削除です。stdbufはlibcの標準入出力バッファ設定を変え、-oLで行単位にします。grep --line-buffered と同様の目的です。',
        'パイプの途中は通常ブロックバッファになります。', 'shred -u、stdbuf -oLを使います。')


# ---------------------------------------------------------------- 10 pathchk / tsort / stty
def s10(ctx):
    t = secrets.token_hex(2)
    names = [f'report_{t}.txt', 'data file.csv', 'a' * 20 + '.txt', 'ok-name.log', 'bad:name', 'ünï.txt', '-dash', f'x{t}']
    ctx.write('names.txt', '\n'.join(names) + '\n')
    perm = [f'task{i}' for i in range(6)]
    secrets.SystemRandom().shuffle(perm)
    edges = [(perm[i], perm[i + 1]) for i in range(5)] + [(perm[0], perm[3]), (perm[2], perm[5])]
    ctx.data['edges'] = edges
    ctx.write('deps.txt', ''.join(f'{a} {b}\n' for a, b in edges))
    put(ctx, 'tty_dump.txt', 'speed 38400 baud; rows 24; columns 80;\nisig icanon iexten -echo echoe echok\n-icanon -echo -isig opost\n')
    ctx.write('requirements.txt', 'names.txtからpathchk -pでPOSIX可搬と判定される名前だけportable.txtへ（順序維持）。deps.txt（「前 後」の組）をtsortで順序付けしorder.txtへ。端末が-echoのまま壊れたtty_dump.txtを直すstty1行をfix.txtへ。\n')


def c10(ctx):
    need_ro(ctx)
    exp = [n for n in ctx.read('names.txt').splitlines() if run(ctx, 'pathchk', '-p', '--', n).returncode == 0]
    ctx.require(ctx.need_file('portable.txt').splitlines() == exp, 'pathchk -p を通る名前だけを書きます。')
    order = ctx.need_file('order.txt').split()
    nodes = {x for e in ctx.data['edges'] for x in e}
    ctx.require(sorted(order) == sorted(nodes), '全ての項目を1回ずつ出力します。')
    ctx.require(all(order.index(a) < order.index(b) for a, b in ctx.data['edges']), '「前」が必ず「後」より先になる順序にします。')
    t = toks(ctx, one_line(ctx, 'fix.txt'))
    ctx.require(t[0] == 'stty' and ('sane' in t or ('echo' in t and 'icanon' in t)), 'stty sane、またはechoとicanonを有効にします。')


SOL10 = ('while IFS= read -r n; do pathchk -p -- "$n" 2>/dev/null && printf \'%s\\n\' "$n"; done < names.txt > portable.txt\n'
         'tsort deps.txt > order.txt\necho "stty sane" > fix.txt')
mission(10, 'pathchk・tsort・sttyで名前検査と順序付けと端末復旧',
        '他OSへ持ち出すファイル名の可搬性をpathchkで検査し、依存関係はtsortで実行順に直し、壊れた端末はsttyで復旧します。',
        ['可搬な名前だけ抽出', 'tsortで順序化', 'stty修復行'], s10, c10, SOL10,
        ["cp names.txt portable.txt\nls > order.txt\necho 'stty -echo' > fix.txt", "tsort deps.txt > order.txt\ncp names.txt portable.txt\necho 'stty sane' > fix.txt"],
        'pathchk -pはPOSIXの可搬文字集合と長さを検査します（日本語・空白・先頭ハイフンは不可）。tsortは「前 後」の組から位相順序を作り、循環は検出して警告します。sttyは端末設定の表示と変更を行い、sttyのsaneで安全な既定に戻せます。',
        '各ツールの入力形式を確認します。', 'pathchkは名前ごとに終了ステータスで判定します。')


# ---------------------------------------------------------------- 11 namei / logname / vdir / hardlink
def s11(ctx):
    app = 'app' + secrets.token_hex(2)
    comps = ['srv', app, 'data']
    blocker = secrets.SystemRandom().choice(comps)
    ctx.data['blocker'] = blocker
    rows = ['f: /srv/%s/data/report.csv' % app, ' dr-xr-xr-x root root /']
    for c in comps:
        mode = 'drwxr-x---' if c == blocker else 'drwxr-xr-x'
        rows.append(f' {mode} root root {c}')
    rows.append(' -rw-r--r-- app app report.csv')
    put(ctx, 'perm.txt', '\n'.join(rows).replace(' ', ' ', 1) + '\n')
    who = 'user' + secrets.token_hex(2)
    ctx.data['who'] = who
    put(ctx, 'audit.txt', f'logname: {who}\nwhoami: root\nid -un: root\n')
    ctx.mkdir('dups')
    names = ['a.dat', 'b.dat', 'c.dat', 'd.dat', 'e.dat']
    for n in names:
        ctx.write('dups/' + n, 'data-' + secrets.token_hex(4) + '\n')
    for x, y in (('a.dat', 'c.dat'), ('d.dat', 'e.dat')):
        os.unlink(ctx.p('dups/' + y))
        os.link(ctx.p('dups/' + x), ctx.p('dups/' + y))
    ctx.write('requirements.txt', 'perm.txt（namei -l の採取結果）から他者に実行権(x)がなく辿れないディレクトリ名をblocker.txtへ。audit.txtから sudo前の元のログイン名(logname)をwho.txtへ。dups内でハードリンクにより既に共有されているファイル名をvdirで調べ昇順でlinked.txtへ。重複排除をまず試行だけするhardlinkのコマンド（-nと-v付き、dups対象）をdedupe.txtへ。\n')


def c11(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('blocker.txt').strip() == ctx.data['blocker'], '「x」が無く辿れないディレクトリ名を書きます。')
    ctx.require(ctx.need_file('who.txt').strip() == ctx.data['who'], 'logname の行の名前を書きます（whoamiではない）。')
    exp = sorted(n for n in os.listdir(ctx.p('dups')) if os.stat(ctx.p('dups/' + n)).st_nlink > 1)
    ctx.require(ctx.need_file('linked.txt').split() == exp, 'リンク数が2以上のファイル名を昇順で書きます。')
    t = toks(ctx, one_line(ctx, 'dedupe.txt'))
    ctx.require(t[0] == 'hardlink' and ('-n' in t or '--dry-run' in t) and ('-v' in t or '--verbose' in t) and 'dups' in t, 'hardlink -n -v dups で試行します。')


SOL11 = ("awk '$1 ~ /^d/ && substr($1,10,1)!=\"x\" {print $NF}' perm.txt > blocker.txt\n"
         "grep '^logname' audit.txt | awk '{print $2}' > who.txt\n"
         "vdir -l dups | awk 'NR>1 && $2>1 {print $NF}' | sort > linked.txt\n"
         "echo 'hardlink -n -v dups' > dedupe.txt")
mission(11, 'namei・logname・vdir・hardlinkで所有と共有を調べる',
        '権限で辿れない経路を示すnamei -lの記録、sudo後も元の利用者を示すlogname、リンク数を見るvdir、重複の統合を行うhardlinkの使い方を練習します。',
        ['4つの調査結果を書く'], s11, c11, SOL11,
        ["echo srv > blocker.txt\necho root > who.txt\nls dups > linked.txt\necho 'hardlink dups' > dedupe.txt",
         "echo data > blocker.txt\ngrep whoami audit.txt | awk '{print $2}' > who.txt\nls dups > linked.txt\necho 'hardlink -n -v dups' > dedupe.txt"],
        'namei -lは経路の各要素の権限を並べるので、途中のディレクトリの実行権欠落が分かります。lognameはログインに使った名前、whoamiは現在の実効ユーザーです。vdirは ls -l に近い詳細表示で、2列目がリンク数です。hardlinkは同一内容を同じiノードに統合するので、必ず-nで確認してから実行します。',
        'リンク数が2以上なら実体を共有しています。', 'awkでmodeの10文字目や2列目を見ます。')


# ---------------------------------------------------------------- 12 xz
def s12(ctx):
    ls = [f'INFO boot {secrets.token_hex(2)}', f'ERROR disk {secrets.token_hex(2)}', 'INFO ok']
    ls2 = ls + [f'ERROR net {secrets.token_hex(2)}']
    ctx.write('a.log.xz', lzma.compress(('\n'.join(ls) + '\n').encode()), binary=True)
    ctx.write('b.log.xz', lzma.compress(('\n'.join(ls2) + '\n').encode()), binary=True)
    ctx.data['cfg'] = 'mode=' + secrets.token_hex(3)
    ctx.write('site.cfg.xz', lzma.compress((ctx.data['cfg'] + '\n').encode()), binary=True)
    ctx.write('requirements.txt', '展開せずに、a.log.xzとb.log.xzからERROR行だけを（ファイル名なしで）xzgrepしてerrors.txtへ。両者の差をxzdiffでdiff.txtへ。a.log.xzの行数をxzcatで数えlines.txtへ。site.cfg.xzはunxzで元の.xzを残して展開。\n')


def c12(ctx):
    ctx.require(ctx.need_file('errors.txt') == out(ctx, 'xzgrep', '-h', 'ERROR', 'a.log.xz', 'b.log.xz'), 'xzgrep -h ERROR の結果です。')
    ctx.require(ctx.need_file('diff.txt') == out(ctx, 'xzdiff', 'a.log.xz', 'b.log.xz'), 'xzdiff の結果です。')
    ctx.require(ctx.need_file('lines.txt').strip() == '3', 'xzcatで展開して数えます。')
    ctx.require(ctx.exists('site.cfg.xz') and ctx.read('site.cfg') == ctx.data['cfg'] + '\n', 'unxz -k で展開し原本も残します。')


SOL12 = ("xzgrep -h ERROR a.log.xz b.log.xz > errors.txt\nxzdiff a.log.xz b.log.xz > diff.txt\n"
         "xzcat a.log.xz | wc -l > lines.txt\nunxz -k site.cfg.xz")
mission(12, 'xzcat・xzgrep・xzdiff・unxzで圧縮ログを展開せず扱う',
        '圧縮したままのログ解析です。xzcat・xzgrep・xzdiffは展開せず読み、ページャーはxzless、古い.Zの展開はuncompressです。設定ファイルはunxzで展開します。',
        ['展開せず検索・比較', 'unxz -kで展開'], s12, c12, SOL12,
        ['grep ERROR a.log.xz b.log.xz > errors.txt\nxzdiff a.log.xz b.log.xz > diff.txt\nwc -l a.log.xz > lines.txt\nunxz site.cfg.xz',
         "xzgrep ERROR a.log.xz b.log.xz > errors.txt\nxzdiff a.log.xz b.log.xz > diff.txt\nxzcat a.log.xz | wc -l > lines.txt\nunxz -k site.cfg.xz"],
        'xz系ツールは内部で展開して標準のgrep・diff・lessなどに渡します。複数ファイルでは行頭にファイル名が付くため-hで抑えます。unxzは既定で元を消すので-kで残します。uncompressは古いcompress形式(.Z)用、xzlessはxz圧縮ファイルのless表示です。',
        '圧縮ファイルに直接grepしても読めません。', 'xzcat・xzgrep・xzdiff・unxz -kです。')


# ---------------------------------------------------------------- 13 gz
def s13(ctx):
    ls = [f'INFO start {secrets.token_hex(2)}', f'WARN slow {secrets.token_hex(2)}', 'INFO done']
    ls2 = ls + [f'WARN retry {secrets.token_hex(2)}']

    def gz(name, lines):
        ctx.write(name, gzip.compress(('\n'.join(lines) + '\n').encode(), mtime=0), binary=True)
    gz('a.gz', ls)
    gz('a2.gz', ls)
    gz('b.gz', ls2)
    other = secrets.choice(['a2.gz', 'b.gz'])
    ctx.data['other'] = other
    ctx.write('requirements.txt', f'a.gzとb.gzからWARN行だけ（ファイル名なし）zgrepでwarns.txtへ。zdiffの差をdiff.txtへ。zcatで先頭1行をfirst.txtへ。a.gzと{other}を展開せずzcmpで比べ、同じならsame、違えばdifferをverdict.txtへ。\n')


def c13(ctx):
    ctx.require(ctx.need_file('warns.txt') == out(ctx, 'zgrep', '-h', 'WARN', 'a.gz', 'b.gz'), 'zgrep -h WARN の結果です。')
    ctx.require(ctx.need_file('diff.txt') == out(ctx, 'zdiff', 'a.gz', 'b.gz'), 'zdiffの結果です。')
    ctx.require(ctx.need_file('first.txt') == gzip.decompress(ctx.p('a.gz').read_bytes()).decode().splitlines()[0] + '\n', 'zcatの先頭1行です。')
    exp = 'same' if run(ctx, 'zcmp', '-s', 'a.gz', ctx.data['other']).returncode == 0 else 'differ'
    ctx.require(ctx.need_file('verdict.txt').strip() == exp, 'zcmpの結果で判定します。')


SOL13 = ("zgrep -h WARN a.gz b.gz > warns.txt\nzdiff a.gz b.gz > diff.txt\nzcat a.gz | head -n 1 > first.txt\n"
         "if zcmp -s a.gz <<other>>; then echo same; else echo differ; fi > verdict.txt")
mission(13, 'zcat・zgrep・zdiff・zcmpでgzipログを読む',
        'gzipの世代ログを展開せずに調べます。zcat、zgrep、zdiff、zcmpを使い、長い出力を見るときはzlessも便利です。',
        ['展開せず検索・比較・判定'], s13, c13, SOL13,
        ['grep WARN a.gz b.gz > warns.txt\nzdiff a.gz b.gz > diff.txt\nhead -n 1 a.gz > first.txt\necho same > verdict.txt',
         'zgrep WARN a.gz b.gz > warns.txt\nzdiff a.gz b.gz > diff.txt\nzcat a.gz | head -n 1 > first.txt\necho same > verdict.txt'],
        'zcat・zgrep・zdiff・zcmp・zlessは、gzip圧縮のまま内容を扱うラッパーです。zcmpは-sで静かに終了ステータスだけを返すので、if文の条件に使えます。ファイル名の付与を避けるにはzgrep -hです。',
        '圧縮ファイルをそのままgrepしても読めません。', 'zgrep -h、zcat、zcmp -sを使います。')


# ---------------------------------------------------------------- 14 zforce / znew / gzexe
def s14(ctx):
    ctx.mkdir('blobs')
    for i in (1, 2):
        ctx.write(f'blobs/x{i}', gzip.compress(f'blob {i} {secrets.token_hex(4)}\n'.encode(), mtime=0), binary=True)
    tag = secrets.token_hex(4)
    ctx.data['tag'] = tag
    body = '#!/bin/bash\n' + ''.join(f'# filler line {i} for compression\n' for i in range(60)) + f'echo tool-{tag}\n'
    ctx.write('app.sh', body, mode=0o755)
    ctx.data['app_sha'] = sha(body)
    ctx.write('requirements.txt', 'blobs/内の拡張子なしgzipファイルを、zforceで.gz付きにする。app.shをgzexeで自己展開型に圧縮（バックアップのapp.sh~は残す）。旧形式legacy.Zを.gzへ変換しつつ原本を残すznewのコマンド1行をznew.txtへ（実行はしない）。\n')


def c14(ctx):
    ctx.require(ctx.isfile('blobs/x1.gz') and ctx.isfile('blobs/x2.gz') and not ctx.exists('blobs/x1') and not ctx.exists('blobs/x2'), 'zforceでblobs内の名前に.gzを付けます。')
    ctx.require(ctx.exists('app.sh~') and sha(ctx.read('app.sh~')) == ctx.data['app_sha'], 'gzexeはapp.sh~にバックアップを作ります。')
    ctx.require(ctx.p('app.sh').stat().st_size < len(ctx.read('app.sh~')), 'app.shが圧縮されていません。')
    r = script_out(ctx, 'app.sh')
    ctx.require(r.stdout.strip() == 'tool-' + ctx.data['tag'], '圧縮後も実行できる必要があります。')
    t = toks(ctx, one_line(ctx, 'znew.txt'))
    ctx.require(t[0] == 'znew' and '-K' in t and 'legacy.Z' in t, 'znew -K legacy.Z で原本を残します。')


SOL14 = "zforce blobs/*\ngzexe app.sh\necho 'znew -K legacy.Z' > znew.txt"
mission(14, 'zforce・gzexe・znewで圧縮の整理と変換',
        '拡張子が欠けたgzipの整理にzforce、スクリプトの自己展開型圧縮にgzexe、旧形式.Zから.gzへの変換にznewを使います。',
        ['zforceで名前を直す', 'gzexeで圧縮', 'znewのコマンド'], s14, c14, SOL14,
        ['gzip blobs/*\ngzexe app.sh\necho "znew legacy.Z" > znew.txt', 'zforce blobs/*\nrm app.sh\necho "znew -K legacy.Z" > znew.txt'],
        'zforceはgzip形式のファイルに.gzを付けて二重圧縮を防ぎます。gzexeは実行ファイルを自己展開型にし、元は~付きで残ります。znewはcompress形式を.gzに変える補助で、-Kで小さくならなくても元を残します。gzexe後は-dで元に戻せます。',
        '既に圧縮されたものをまた圧縮しない工夫です。', 'zforce、gzexe、znew -Kです。')


# ---------------------------------------------------------------- 15 less / rename.ul
def s15(ctx):
    for c in 'abc':
        ctx.write(f'img_{c}.jpeg', 'x\n')
    k = secrets.choice('mnoyz')
    ctx.data['key'] = k
    ctx.write('requirements.txt', f'rename.ulでimg_*.jpegを.jpgに一括変更。lesskey用のbind.srcに、キー「{k}」で1画面進む(forw-screen)#commandの設定を書き、lesskey -oでbind.outを生成。less_env.shにLESSOPENを「|lesspipe %s」でexport。lessechoで文字列を展開しても安全に渡せる使い方も試す。\n')


def c15(ctx):
    ctx.require(all(ctx.isfile(f'img_{c}.jpg') for c in 'abc') and not any(ctx.exists(f'img_{c}.jpeg') for c in 'abc'), 'rename.ulで一括変更します。')
    src = ctx.need_file('bind.src').splitlines()
    ctx.require('#command' in src and f'{ctx.data["key"]} forw-screen' in [' '.join(x.split()) for x in src], '#commandの下に「キー forw-screen」の行を書きます。')
    ctx.require(ctx.exists('bind.out'), 'lesskey -o で bind.out を生成します。')
    ctx.require(re.search(r'export\s+LESSOPEN=["\']?\|\s*lesspipe %s', ctx.need_file('less_env.sh')), 'export LESSOPEN="|lesspipe %s" を書きます。')


SOL15 = ("rename.ul jpeg jpg img_*.jpeg\nprintf '#command\\n<<key>> forw-screen\\n' > bind.src\nlesskey -o bind.out bind.src\n"
         "echo 'export LESSOPEN=\"|lesspipe %s\"' > less_env.sh\nlessecho 'a b' > /dev/null")
mission(15, 'rename.ul・lesskey・lesspipe・lessechoでlessを整える',
        '写真の拡張子を一括変更するrename.ulと、閲覧ツールlessのカスタマイズ(lesskey・lesspipe・lessecho)を設定します。',
        ['一括変更', 'lesskeyとLESSOPEN'], s15, c15, SOL15,
        ['for f in img_*.jpeg; do mv $f $f.jpg; done\necho x > bind.src', 'rename.ul jpeg jpg img_*.jpeg\nprintf "#command\\n<<key>> forw-screen\\n" > bind.src\necho "export LESSOPEN=lesspipe" > less_env.sh'],
        'rename.ulはutil-linux版で「置換前 置換後 ファイル群」の形式です（Perl版とは引数が違う）。lesskeyはキー割り当てを、lesspipeはLESSOPEN経由でPDFや圧縮の中身表示を、lessechoはlessがメタ文字を展開した名前を扱う補助です。',
        '2つの別のツールの設定です。', 'rename.ul 置換前 置換後 ファイル。lesskey -o 出力 入力。')


# ---------------------------------------------------------------- 16 dircolors / mcookie / hostid
def s16(ctx):
    c = f'01;{30 + secrets.randbelow(8)}'
    ctx.data['color'] = c
    h = secrets.token_hex(4)
    ctx.data['same'] = secrets.randbelow(2) == 0
    lic = h if ctx.data['same'] else secrets.token_hex(4)
    put(ctx, 'host_report.txt', f'hostid: {h}\nhostname: node1\n')
    put(ctx, 'license.txt', f'bound_hostid={lic}\n')
    ctx.write('requirements.txt', f'dircolors -p で既定設定を出し、さらに「.log {c}」を足してmy.dircolorsを作る。mcookie（32桁の16進乱数）をcookie.txtへ。host_report.txt（hostidの採取値）とlicense.txtを比べ、一致ならmatch、違えばmismatchをverdict.txtへ。\n')


def c16(ctx):
    need_ro(ctx)
    ctx.need_file('my.dircolors')
    r = run(ctx, 'dircolors', '-b', 'my.dircolors')
    ctx.require(r.returncode == 0 and f'*.log={ctx.data["color"]}' in r.stdout, 'my.dircolorsに指定の.log色を入れます。')
    ctx.require(re.fullmatch(r'[0-9a-f]{32}', ctx.need_file('cookie.txt').strip()), 'mcookieの32桁の16進を書きます。')
    ctx.require(ctx.need_file('verdict.txt').strip() == ('match' if ctx.data['same'] else 'mismatch'), 'hostidとライセンスの値を比べます。')


SOL16 = ("dircolors -p > my.dircolors\necho '.log <<color>>' >> my.dircolors\nmcookie > cookie.txt\n"
         "if [ \"$(awk '/^hostid/{print $2}' host_report.txt)\" = \"$(cut -d= -f2 license.txt)\" ]; then echo match; else echo mismatch; fi > verdict.txt")
mission(16, 'dircolors・mcookie・hostidで色設定と識別子を扱う',
        'lsの色はdircolorsで設計し、認証用の乱数はmcookie、ライセンスの照合は機体識別のhostidで行います。hostidの値は環境依存なので採取済みの結果を使います。',
        ['dircolors設定を作る', 'mcookieを作る', 'hostid照合'], s16, c16, SOL16,
        ['echo ".log <<color>>" > my.dircolors\nopenssl rand -hex 8 > cookie.txt\necho match > verdict.txt', 'dircolors -p > my.dircolors\nmcookie > cookie.txt\necho match > verdict.txt'],
        'dircolors -pは既定の色定義を出力し、編集して-bで環境変数LS_COLORSの形に変換します。mcookieはX認証用の128ビット乱数で、32桁の16進です。hostidは機体に紐づく数値ですが偽装は容易で、強い認証には向きません。',
        '3つはそれぞれ独立した小課題です。', 'dircolors -p、mcookie、awkとcutで比較します。')


# ---------------------------------------------------------------- 17 mknod
def s17(ctx):
    dev = {'null': 3, 'zero': 5, 'full': 7, 'random': 8, 'urandom': 9}
    miss = secrets.choice(sorted(dev))
    ctx.data['miss'] = miss
    if ctx.exists('jobs.fifo'):
        os.unlink(ctx.p('jobs.fifo'))
    ctx.data['minor'] = dev[miss]
    rows = ''.join(f'crw-rw-rw- 1 root root 1, {m} Jan  1 00:00 {n}\n' for n, m in dev.items() if n != miss)
    put(ctx, 'dev_listing.txt', rows)
    put(ctx, 'ref.txt', 'メモリ系キャラクタデバイスはメジャー番号1。マイナー番号: null=3, zero=5, full=7, random=8, urandom=9。\n')
    ctx.write('requirements.txt', 'dev_listing.txt（ls -l /dev の採取）で欠けているデバイスを診断し、diag.jsonに{"missing","type","major","minor"}で書く。さらにmknodで所有者のみ読み書き(600)のFIFO jobs.fifoを作る。\n')


def c17(ctx):
    need_ro(ctx)
    try:
        d = json.loads(ctx.need_file('diag.json'))
    except ValueError:
        ctx.fail('diag.jsonは有効なJSONです。')
    ctx.require(d == {'missing': ctx.data['miss'], 'type': 'c', 'major': 1, 'minor': ctx.data['minor']}, '欠けたデバイス名とタイプ・番号を書きます。')
    p = ctx.p('jobs.fifo')
    ctx.require(p.exists() and stat.S_ISFIFO(p.stat().st_mode), 'jobs.fifo はmknod ... p で作るFIFOです。')
    ctx.require(stat.S_IMODE(p.stat().st_mode) == 0o600, 'mknod -m 600 で権限を付けます。')


SOL17 = ("mknod -m 600 jobs.fifo p\nprintf '{\"missing\":\"<<miss>>\",\"type\":\"c\",\"major\":1,\"minor\":<<minor>>}\\n' > diag.json")
mission(17, 'mknodでFIFOを作りデバイス欠落を診断する',
        'デバイスファイルはmknodで作ります。実際のcharデバイス作成にはrootが必要なので、ここでは欠けたノードを記録から診断し、rootなしで作れるFIFOでmknodを練習します。',
        ['欠落の診断をJSONへ', 'mknod pでFIFO作成'], s17, c17, SOL17,
        ['mkfifo -m 600 jobs.fifo\necho "{}" > diag.json', 'mknod jobs.fifo p\nprintf \'{"missing":"null","type":"c","major":1,"minor":3}\\n\' > diag.json'],
        'mknod 名前 種類 [メジャー マイナー] で、cはキャラクタ、bはブロック、pはFIFOです。メジャー番号がドライバ、マイナー番号がインスタンスを表します。現在はudevが自動作成するため、手作業は復旧や最小環境(initramfs・コンテナ)で使います。-mで権限を同時指定します。',
        'FIFOはメジャー番号が不要です。', 'mknod -m 600 名前 p。診断はref.txtの対応表を使います。')


# ---------------------------------------------------------------- 18 globbing
def s18(ctx):
    t = secrets.token_hex(2)
    files = ['src/main.py', 'src/test_main.py', f'src/util/h{t}.py', 'src/util/test_h.py', 'src/util/deep/x.py', 'src/util/deep/y.txt', 'src/.hidden.py', 'docs/conf.py']
    for f in files:
        ctx.write(f, '#\n')
    ctx.data['exp'] = sorted(['src/main.py', f'src/util/h{t}.py', 'src/util/deep/x.py', 'docs/conf.py'])
    ctx.write('requirements.txt', 'サブフォルダを含め、名前が「test_」で始まらない.pyファイルを（隠しファイルを除き）printfとglobで列挙し、昇順でfiles.txtへ。shoptでglobstarとextglobを有効にして使う。\n')


def c18(ctx):
    ctx.require(ctx.need_file('files.txt').split() == ctx.data['exp'], 'test_で始まらない.pyファイルだけを、相対パスで昇順に書きます。')
    ctx.require(ctx.used('globstar') and ctx.used('extglob'), 'shopt -s globstar extglob を使います。')


SOL18 = "shopt -s globstar extglob nullglob\nprintf '%s\\n' **/!(test_*).py | sort > files.txt"
mission(18, 'ワイルドカードとshoptのextglob・globstar',
        'findを使わず、シェルのパス名展開(globbing)だけで再帰的に絞り込みます。**はglobstar、!(...)はextglobで、どちらもshoptで有効にします。',
        ['globstarとextglobを有効化', 'files.txtを作る'], s18, c18, SOL18,
        ["find . -name '*.py' | sort > files.txt", "ls src/*.py > files.txt"],
        'ワイルドカードはシェルが展開してからコマンドへ渡します。*は任意文字列、?は1文字、[]は文字集合です。shopt -s globstarで**が階層を再帰し、extglobで!(...)・+(...)などの拡張パターンが使えます。nullglobは不一致を空に、dotglobは隠しファイルも対象にします。',
        '隠しファイルは通常は展開されません。', 'shoptで二つのオプションをオンにして、printfで1行ずつ出します。')


# ---------------------------------------------------------------- 19 quoting
def s19(ctx):
    ctx.data['tag'] = 'v' + secrets.token_hex(3)
    ctx.write('requirements.txt', f'name={ctx.data["tag"]} を設定し、次の3行をquotes.txtへ。\nliteral: $name\nexpanded: {ctx.data["tag"]}\nescaped: it\'s "{ctx.data["tag"]}"\n')


def c19(ctx):
    t = ctx.data['tag']
    ctx.require(ctx.need_file('quotes.txt') == f'literal: $name\nexpanded: {t}\nescaped: it\'s "{t}"\n', '単一引用符・二重引用符・バックスラッシュの違いで3行を作ります。')


SOL19 = "name=<<tag>>\n{ echo 'literal: $name'; echo \"expanded: $name\"; echo \"escaped: it's \\\"$name\\\"\"; } > quotes.txt"
mission(19, 'クォート3種で展開を制御しprintfとdeclareで出力',
        'シェルのクォートは単一引用符、二重引用符、バックスラッシュの3種です。変数展開を止める・通す・文字として扱う、を使い分けて3行を作ります。',
        ['3種のクォートを使い分ける'], s19, c19, SOL19,
        ["name=<<tag>>\necho \"literal: $name\" > quotes.txt\necho \"expanded: $name\" >> quotes.txt", "name=<<tag>>\necho 'literal: $name' > quotes.txt\necho 'expanded: $name' >> quotes.txt"],
        '単一引用符は一切展開せず、二重引用符は$と`と\\だけ解釈し、バックスラッシュは直後の1文字を保護します。printfは書式で安全に出力でき、declare -p 変数で値と属性を確認できます。変数は基本的に二重引用符で囲みます。',
        '$nameを展開させるかどうかが違いです。', '単一/二重/エスケープを行ごとに使います。')


# ---------------------------------------------------------------- 20 redirects
def s20(ctx):
    ctx.data['tag'] = secrets.token_hex(3)
    ctx.write('requirements.txt', f'''次を作る（タグ {ctx.data["tag"]}）。
audit.log: exec 3>audit.log でファイルディスクリプタ3を開き、「start タグ」「end タグ」を>&3で書き、最後に3を閉じる。
err.log: 存在しない no-such-タグ をlsしたときの標準エラーのみ。
combined.log: sh -c 'echo out; echo err >&2' の標準出力と標準エラーの両方（2>&1）。
pad.bin: /dev/zeroからddで1KiB x 4 のゼロ。
key.hex: /dev/urandomの16バイトを16進32桁（od -An -tx1 | tr -d ' \\n'）。
最後に /dev/null で出力を捨てる実行も1回行う。
''')


def c20(ctx):
    t = ctx.data['tag']
    ctx.require(ctx.need_file('audit.log').splitlines() == [f'start {t}', f'end {t}'], 'audit.logはfd3で2行だけ書きます。')
    ctx.require(ctx.used('exec 3>'), 'exec 3> でFDを開きます。')
    e = ctx.need_file('err.log')
    ctx.require(t in e and 'no-such' in e, 'err.logに標準エラーだけを保存します。')
    ctx.require(sorted(ctx.need_file('combined.log').split()) == ['err', 'out'], 'combined.logにoutとerrの両方を入れます。')
    ctx.require(ctx.p('pad.bin').read_bytes() == b'\0' * 4096, 'pad.binは4096バイトのゼロです。')
    ctx.require(re.fullmatch(r'[0-9a-f]{32}', ctx.need_file('key.hex').strip()), 'key.hexは32桁の16進です。')
    ctx.require(ctx.used('/dev/null'), '/dev/null に出力を捨てる例も行います。')


SOL20 = ("exec 3>audit.log\necho 'start <<tag>>' >&3\necho 'end <<tag>>' >&3\nexec 3>&-\n"
         "ls no-such-<<tag>> 2> err.log\nsh -c 'echo out; echo err >&2' > combined.log 2>&1\n"
         "dd if=/dev/zero of=pad.bin bs=1k count=4 2>/dev/null\n"
         "head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \\n' > key.hex\nls /nonexistent >/dev/null 2>&1")
mission(20, 'リダイレクトとファイルディスクリプタ・特殊デバイス',
        '標準出力(1)と標準エラー(2)の振り分け、exec 3>…による追加のFD、2>&1の合流、/dev/null・/dev/zero・/dev/urandomの使い分けを一通り操作します。',
        ['FD3とリダイレクトを使い分ける', '特殊デバイスを使う'], s20, c20, SOL20,
        ["echo 'start <<tag>>' > audit.log\nls no-such-<<tag>> > err.log", "exec 3>audit.log\necho 'start <<tag>>' >&3\nls no-such-<<tag>> 2> err.log\nsh -c 'echo out; echo err >&2' > combined.log"],
        '2>&1は「標準エラーを今の標準出力の行き先へ」の意味で、順序が重要です(> file 2>&1)。exec 3>fileでスクリプト内のFDをファイルに結び、>&3で書き、3>&-で閉じます。/dev/nullは捨て場所、/dev/zeroはゼロの供給、/dev/urandomは乱数の供給です。',
        '番号1は標準出力、2は標準エラーです。', 'exec 3>…、2>、2>&1、dd、head -cの組み合わせです。')


# ---------------------------------------------------------------- 21 exit status
def s21(ctx):
    ctx.write('ok.log', 'INFO fine\n')
    ctx.write('bad.log', 'INFO a\nFATAL disk\n')
    ctx.write('requirements.txt', 'report.sh（引数1つ＝ログ）を書く。まず command -v grep で道具を確認。ファイルが無ければ「missing」を出して終了ステータス2、FATALを含めば「NG」を出して1、それ以外は「OK」を出して0。ステータスは$?やexitで正しく伝える。\n')


def c21(ctx):
    cases = [('ok.log', 'OK', 0), ('bad.log', 'NG', 1), ('nothing.log', 'missing', 2)]
    for f, o, rc in cases:
        r = script_out(ctx, 'report.sh', f)
        ctx.require(r.stdout.strip() == o and r.returncode == rc, f'{f} の結果は「{o}」・終了ステータス{rc}です。')


SOL21 = ("cat > report.sh <<'EOF'\ncommand -v grep >/dev/null || exit 127\n"
         "[ -f \"$1\" ] || { echo missing; exit 2; }\n"
         "if grep -q FATAL \"$1\"; then echo NG; exit 1; fi\necho OK\nexit 0\nEOF")
mission(21, '終了ステータスで分岐し、type・commandで道具を確かめる',
        '0が成功、それ以外が失敗というシェルの約束を使い、ログ判定スクリプトを作ります。道具の存在確認にはtypeやcommand -vを使います。',
        ['3通りの終了ステータスを返す'], s21, c21, SOL21,
        ["echo 'echo OK' > report.sh", "cat > report.sh <<'EOF'\ngrep FATAL \"$1\" && echo NG\necho OK\nEOF"],
        '直前のコマンドの終了ステータスは$?で見え、&&と||と if の条件はこの値で動きます。command -vやtypeは名前の解決を確認でき、127は「コマンドが無い」を示す慣習です。意味のある数値を決めて呼び出し側へ伝えます。',
        'エラー処理が最初に来ます。', 'if grep -q、[ -f ]、exitを使います。')


# ---------------------------------------------------------------- 22 builtins A
def s22(ctx):
    a, b = 2 + secrets.randbelow(8), 2 + secrets.randbelow(8)
    ctx.data.update(a=a, b=b, c=a * b + 3)
    ctx.write('requirements.txt', f'''b1.sh を書き、実行すると次の5行を出す。
1) letで c = {a} * {b} + 3 を計算した値
2) type -t cd の結果
3) hash -p /bin/echo myecho の後の type -t myecho の結果
4) shopt -s expand_aliases のもとで alias hi='echo hijacked' を作り unalias hi した後、type -t hi が無ければ gone を出す
5) command -v cd の結果
''')


def c22(ctx):
    r = script_out(ctx, 'b1.sh')
    ctx.require(r.stdout.split() == [str(ctx.data['c']), 'builtin', 'file', 'gone', 'cd'], 'b1.shの出力が期待の5行になりません。letの計算とtype/hash/unalias/commandを確認します。')


SOL22 = ("cat > b1.sh <<'EOF'\nlet \"c = <<a>> * <<b>> + 3\"\necho $c\ntype -t cd\nhash -p /bin/echo myecho\ntype -t myecho\n"
         "shopt -s expand_aliases\nalias hi='echo hijacked'\nunalias hi\ntype -t hi || echo gone\ncommand -v cd\nEOF")
mission(22, 'let・hash・type・command・unalias・shoptの基本',
        'シェル組み込みのlet(整数計算)、hash(コマンド位置キャッシュ)、type・command(名前解決の確認)、unalias(別名解除)、shopt(拡張オプション)を一つのスクリプトで確かめます。',
        ['b1.shを作る'], s22, c22, SOL22,
        ["echo 'echo 0' > b1.sh", "cat > b1.sh <<'EOF'\nc=<<a>>*<<b>>+3\necho $c\ntype -t cd\nEOF"],
        'letは算術式を評価して変数に代入します。hashはPATH検索結果を覚え、-pで手動登録、-rで消去します。type -tは種別(alias/builtin/file/function)を、command -vは実行される名前を返します。unaliasは別名を外し、shoptはbash独自のオプションを切り替えます。',
        '5行の出力順に作ります。', 'let "c = a * b + 3"、type -t、hash -p です。')


# ---------------------------------------------------------------- 23 mapfile etc.
def s23(ctx):
    t = ''.join(secrets.choice('abcdefgh') for _ in range(5))
    names = [secrets.token_hex(2) for _ in range(4)]
    ctx.data.update(tag=t, last=names[-1], n=4, up=t.upper())
    ctx.write('names.txt', '\n'.join(names) + '\n')
    ctx.write('history.txt', '  101  grep -rn ERORR logs\n')
    ctx.write('requirements.txt', f'''m.sh を書き、次の4行を出す。
1) mapfile -t でnames.txtを配列に読み込んだ行数
2) readarray -t でも読み込み、配列の最後の要素
3) compgen -W "build bench branch test" -- b の候補数
4) coprocを使い、{t} をtrで大文字にして返させた結果
さらに fc.txt に、履歴の直前コマンド（誤字ERORR）を修正して再実行するfcコマンド1行（実行はしない）。
''')


def c23(ctx):
    r = script_out(ctx, 'm.sh')
    d = ctx.data
    ctx.require(r.stdout.split() == ['4', d['last'], '3', d['up']], 'm.shの出力は「行数・最後の要素・候補数・大文字化結果」の4行です。')
    t = toks(ctx, one_line(ctx, 'fc.txt'))
    ctx.require(t[0] == 'fc' and '-s' in t and 'ERORR=ERROR' in t, 'fc -s ERORR=ERROR で直前を置換して再実行します。')


SOL23 = ("cat > m.sh <<'EOF'\nmapfile -t lines < names.txt\necho ${#lines[@]}\nreadarray -t other < names.txt\necho ${other[-1]}\n"
         "compgen -W \"build bench branch test\" -- b | wc -l\n"
         "coproc UP { tr a-z A-Z; }\necho <<tag>> >&\"${UP[1]}\"\nexec {UP[1]}>&-\nread -r res <&\"${UP[0]}\"\necho $res\nEOF\n"
         "echo 'fc -s ERORR=ERROR' > fc.txt")
mission(23, 'mapfile・readarray・coproc・compgen・fcを使う',
        '行を配列に読むmapfile(別名readarray)、双方向パイプのcoproc、補完候補を作るcompgen、履歴を修正して再実行するfcを使い分けます。',
        ['m.shを作る', 'fc.txtを書く'], s23, c23, SOL23,
        ["echo 4 > m.sh\necho 'fc' > fc.txt", "cat > m.sh <<'EOF'\nwc -l < names.txt\ntail -n 1 names.txt\necho 3\necho wrong\nEOF\necho 'fc -s ERORR=ERROR' > fc.txt"],
        'mapfile -tは改行を除いて各行を配列要素にします。coprocは名前付きの子プロセスを作り、NAME[0]から読み、NAME[1]へ書きます。compgen -Wは単語リストから前方一致を出し、補完スクリプトの部品です。fc -s 旧=新は直前コマンドを置換して再実行します。',
        'coprocは書き込み側を閉じないと終わりません。', 'exec {UP[1]}>&- で入力を閉じます。')


# ---------------------------------------------------------------- 24 pushd etc.
def s24(ctx):
    d = ctx.data
    d['lim'] = 10 + secrets.randbelow(80)
    d['tag'] = secrets.token_hex(3)
    d['nums'] = [secrets.randbelow(20) + 1 for _ in range(4)]
    ctx.write('requirements.txt', f'''s.sh を書き、次の8行を出す（mkdir -pで作業用ディレクトリを自作してよい）。
1) pushd で2つのディレクトリ（d1, d2）へ移動した直後の dirs -p の行数
2) popd した後のカレントディレクトリ名
3) 関数 sum（local変数とshiftで全引数の合計）に {' '.join(map(str, d['nums']))} を渡した合計
4) 関数 where の中の caller 0 が返す3番目の値（スクリプトのファイル名）
5) read -p "name: " に here-string で {d['tag']} を与えて表示した値
6) printf '%05d' で 42 を整形
7) readonly LIMIT={d['lim']} にし、(LIMIT=1)が失敗したら locked を出す
8) declare -p LIMIT の出力
''')


def c24(ctx):
    d = ctx.data
    r = script_out(ctx, 's.sh')
    exp = ['3', 'd1', str(sum(d['nums'])), 's.sh', d['tag'], '00042', 'locked', f'declare -r LIMIT="{d["lim"]}"']
    ctx.require([x.strip() for x in r.stdout.strip().splitlines()] == exp, 's.shの出力が期待の8行と一致しません。')


SOL24 = ("cat > s.sh <<'EOF'\nmkdir -p d1 d2\npushd d1 >/dev/null\npushd ../d2 >/dev/null\ndirs -p | wc -l\npopd >/dev/null\nbasename \"$PWD\"\n"
         "sum() { local t=0; while [ $# -gt 0 ]; do t=$((t+$1)); shift; done; echo $t; }\nsum <<nums_sp>>\n"
         "where() { caller 0 | cut -d' ' -f3; }\nwhere\nread -p \"name: \" v <<< \"<<tag>>\"\necho $v\nprintf '%05d\\n' 42\n"
         "readonly LIMIT=<<lim>>\n(LIMIT=1) 2>/dev/null || echo locked\ndeclare -p LIMIT\nEOF")
mission(24, 'pushd・popd・dirs・caller・read・printf・declare・local・readonly・shift',
        '作業フォルダの出し入れ(pushd・popd・dirs)、関数の局所変数(local)と引数の消費(shift)、呼び出し元の追跡(caller)、入力(read -p)、整形(printf)、定数化(readonly)と属性表示(declare)を1本のスクリプトで練習します。',
        ['s.shを作る'], lambda ctx: (s24(ctx), ctx.data.__setitem__('nums_sp', ' '.join(map(str, ctx.data['nums']))))[0], c24, SOL24,
        ["echo 3 > s.sh", "cat > s.sh <<'EOF'\nmkdir -p d1 d2\npushd d1 >/dev/null\necho 2\nEOF"],
        'pushd/popdはディレクトリスタックで、dirs -pで1行ずつ見えます。localは関数内だけの変数、shiftは位置パラメータを1つ消費します。callerは呼び出し行・関数名・ファイルを返します。read -pは端末入力時にだけ表示されます。readonlyは再代入を拒否し、declare -pは属性付きで値を表示します。',
        '出力は8行です。順に1つずつ作ります。', 'dirs -p、local、shift、caller 0、declare -p を使います。')
