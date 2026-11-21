"""Stage 24: 正規表現・シェル上級・パッケージ作成・カーネルビルド。サンドボックス内の偽データと使える本物のツールだけを使う。"""
import calendar
import hashlib
import json
import os
import random
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from engine.runner import register

S = 24
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・ネットワーク・パッケージDBは変更せず、rootも使いません。"
        "データは訓練用の偽物です。実行可能な課題はコマンドやスクリプトの動作で判定します。未導入ツールや実OSを操作する課題は、設定や手順の内容を検査します。")


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


def cmd_lines(ctx, name, n):
    ls = [x.strip() for x in ctx.need_file(name).splitlines() if x.strip()]
    ctx.require(len(ls) == n, f'{name} には{n}行のコマンドを書きます（現在{len(ls)}行）。')
    return ls


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def runc(ctx, line, cwd=None, env=None, timeout=10):
    e = dict(os.environ, LC_ALL='C', TZ='Asia/Tokyo')
    e.pop('TITLE', None)
    for k, v in (env or {}).items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    try:
        r = subprocess.run(['bash', '-c', line], cwd=str(cwd or ctx.work), env=e, capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        ctx.fail('コマンドが終了しません（無限待ちになっていませんか）。')
    return r


@contextmanager
def sandbox(ctx):
    d = tempfile.mkdtemp(prefix='lq24-')
    w = Path(d) / 'w'
    try:
        shutil.copytree(ctx.work, w, symlinks=True)
        yield w
    finally:
        shutil.rmtree(d, ignore_errors=True)


def same(ctx, got, want, what):
    ctx.require(got.rstrip('\n') == want.rstrip('\n'),
                f'{what} の出力が期待と違います。\n--- あなたの出力 ---\n{got[:300]}\n--- 期待 ---\n{want[:300]}')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'24-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='実行前に対象を確認し、結果を観測で検証します。複雑な処理は小さな部品に分けて、1つずつ出力を確かめながら組み立てましょう。')


def rword(k=1):
    return ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(k))


# ---------------------------------------------------------------- 1 BRE / ERE
def s1(ctx):
    valid = []
    while len(valid) < 4:
        v = ''.join(random.choice('ABCDEFGH') for _ in range(2)) + '%03d' % random.randint(0, 999)
        if v not in valid:
            valid.append(v)
    dec = ['AB12', 'AB1234', 'xAB123', 'ab123', 'AB123x', 'A1234']
    lines = valid + dec
    random.shuffle(lines)
    put(ctx, 'codes.txt', '\n'.join(lines) + '\n')
    ctx.data['want1'] = '\n'.join(x for x in lines if re.fullmatch(r'[A-Z]{2}[0-9]{3}', x))
    ctx.write('requirements.txt', '社員コードは「英大文字2文字+数字3桁」だけが正式です。codes.txtから正式なコードの行だけを出す grep を、'
              'cmds.txt の1行目にBRE（-Eなし）、2行目にERE（grep -E）で書いてください。どちらもアンカーで行全体に一致させます。\n')


def c1(ctx):
    need_ro(ctx)
    ls = cmd_lines(ctx, 'cmds.txt', 2)
    t1, t2 = toks(ctx, ls[0]), toks(ctx, ls[1])
    ctx.require(t1[0] == 'grep' and t2[0] == 'grep', '両方 grep で書きます。')
    ctx.require(not any(x.startswith('-') and ('E' in x or 'P' in x) for x in t1[1:]), '1行目はBRE（-E/-Pなし）です。')
    ctx.require('\\{' in ls[0], 'BREでは量指定子の波括弧を \\{ \\} と書きます。')
    ctx.require(any(x.startswith('-') and 'E' in x for x in t2[1:]) and '{' in ls[1] and '\\{' not in ls[1],
                '2行目は grep -E で、波括弧はバックスラッシュなしの {n} と書きます。')
    same(ctx, runc(ctx, ls[0]).stdout, ctx.data['want1'], '1行目(BRE)')
    same(ctx, runc(ctx, ls[1]).stdout, ctx.data['want1'], '2行目(ERE)')


SOL1 = r"""cat > cmds.txt <<'EOF'
grep '^[A-Z]\{2\}[0-9]\{3\}$' codes.txt
grep -E '^[A-Z]{2}[0-9]{3}$' codes.txt
EOF"""
mission(1, '正規表現の基礎: BRE・ERE・アンカー・量指定子',
        '正規表現には方言があります。grep の既定は BRE、grep -E は ERE、grep -P は PCRE（Perl互換）です。BREでは {n} や + ( ) | をバックスラッシュ付きで書き、EREではそのまま書きます。^ $ のアンカーで行全体を縛り、{2} や {3} の量指定子で桁数を指定します。同じ条件をBREとEREで書いてください。',
        ['1行目にBREのgrep', '2行目にgrep -EのERE'], s1, c1, SOL1,
        ["cat > cmds.txt <<'EOF'\ngrep -E '^[A-Z]{2}[0-9]{3}$' codes.txt\ngrep -E '^[A-Z]{2}[0-9]{3}$' codes.txt\nEOF",
         "cat > cmds.txt <<'EOF'\ngrep '[A-Z]\\{2\\}[0-9]\\{3\\}' codes.txt\ngrep -E '[A-Z]{2}[0-9]{3}' codes.txt\nEOF"],
        'BRE/ERE/PCREの違い: BREは ? + | ( ) { } が通常文字で、使うには \\{ \\} のように \\ を付けます（GNU拡張）。EREはそれらが特殊文字、PCREはさらに \\d \\b 先読み 非貪欲 を持ちます。アンカー ^ は行頭、$ は行末で、これが無いと AB1234 や xAB123 も一部一致して混ざります。量指定子は * + ? {n,m} です。',
        'アンカーを付け忘れると桁あふれの行が混ざります。', 'BREは \\{3\\}、ERE（grep -E）は {3}。^ と $ で行全体を囲みます。')


# ---------------------------------------------------------------- 2 backref / lazy
def s2(ctx):
    ws = ['the', 'cat', 'sat', 'on', 'mat', 'and', 'dog', 'ran', 'big', 'red', 'car', 'fast', 'old', 'sun']
    L, dup = [], 0
    for i in range(7):
        w = random.sample(ws, 5)
        if i % 2 == 0:
            k = random.randrange(5)
            w.insert(k, w[k])
        L.append(' '.join(w))
    put(ctx, 'text.txt', '\n'.join(L) + '\n')
    ctx.data['w1'] = '\n'.join(x for x in L if re.search(r'\b([a-z]+) \1\b', x))
    H = []
    for _ in range(4):
        parts = ['<b>%s</b>' % rword(4) for _ in range(random.randint(2, 3))]
        H.append(' <i>x</i> '.join(parts))
    put(ctx, 'tags.html', '\n'.join(H) + '\n')
    ctx.data['w2'] = '\n'.join(m for x in H for m in re.findall(r'<b>.*?</b>', x))
    ctx.write('requirements.txt', 'cmd1.txt: text.txt から「同じ単語が連続する行」を grep -E と後方参照(\\1)で出す1行。\n'
              'cmd2.txt: tags.html から <b>…</b> を1つずつ別の行で出す grep -o と -P（非貪欲 .*? ）の1行。\n')


def c2(ctx):
    need_ro(ctx)
    l1 = cmd_lines(ctx, 'cmd1.txt', 1)[0]
    l2 = cmd_lines(ctx, 'cmd2.txt', 1)[0]
    t1, t2 = toks(ctx, l1), toks(ctx, l2)
    ctx.require(t1[0] == 'grep' and any(x.startswith('-') and 'E' in x for x in t1[1:]) and '\\1' in l1,
                'cmd1は grep -E と後方参照 \\1 を使います。')
    ctx.require(t2[0] == 'grep' and any(x.startswith('-') and 'P' in x for x in t2[1:])
                and any(x.startswith('-') and 'o' in x for x in t2[1:]) and '.*?' in l2,
                'cmd2は grep -o と -P、非貪欲の .*? を使います。')
    same(ctx, runc(ctx, l1).stdout, ctx.data['w1'], 'cmd1')
    same(ctx, runc(ctx, l2).stdout, ctx.data['w2'], 'cmd2')


SOL2 = r"""cat > cmd1.txt <<'EOF'
grep -E '\b([a-z]+) \1\b' text.txt
EOF
cat > cmd2.txt <<'EOF'
grep -oP '<b>.*?</b>' tags.html
EOF"""
mission(2, '正規表現の応用: 後方参照・貪欲/非貪欲・grep -P/-o',
        '( ) で囲んだ部分は \\1 で後方参照でき、「同じ語の繰り返し」を検出できます。また .* は貪欲（最長一致）なので <b>a</b> と <b>b</b> が並ぶ行を1つの塊にしてしまいます。grep -P（PCRE）の非貪欲 .*? と grep -o（一致部分だけ出力）を使って1つずつ取り出しましょう。',
        ['cmd1.txtに後方参照のgrep -E', 'cmd2.txtに非貪欲のgrep -oP'], s2, c2, SOL2,
        ["cat > cmd1.txt <<'EOF'\ngrep -E '[a-z]+ [a-z]+' text.txt\nEOF\ncat > cmd2.txt <<'EOF'\ngrep -oP '<b>.*?</b>' tags.html\nEOF",
         "cat > cmd1.txt <<'EOF'\ngrep -E '\\b([a-z]+) \\1\\b' text.txt\nEOF\ncat > cmd2.txt <<'EOF'\ngrep -o '<b>.*</b>' tags.html\nEOF"],
        '後方参照はBRE/EREでも使えます（\\1）が、非貪欲な量指定子 *? +? はPCREだけです。貪欲/非貪欲の違いを覚えましょう: .* は可能な限り長く、.*? は最短で止まります。grep -o は一致部分だけを1行ずつ出し、grep -P はPCREを有効にします（GNU grepのみ。無い環境ではperl -ne を使います）。',
        '貪欲な .* だと行内の最初の <b> から最後の </b> まで取ります。', '-o と -P を組み合わせ、.*? で最短一致にします。後方参照は ([a-z]+) と \\1。')


# ---------------------------------------------------------------- 3 sed -E
def s3(ctx):
    L = []
    for _ in range(5):
        L.append('2026-%02d-%02d %s user=%s code=%d' % (random.randint(1, 12), random.randint(10, 28),
                 random.choice(['ERROR', 'WARN', 'INFO']), rword(5), random.randint(100, 599)))
    put(ctx, 'logs.txt', '\n'.join(L) + '\n')
    ctx.data['w'] = '\n'.join(re.sub(r' code=\d+', '', re.sub(r'^(\d{4})-(\d{2})-(\d{2})', r'\3/\2/\1', x)) for x in L)
    ctx.write('requirements.txt', 'logs.txt の先頭の日付 YYYY-MM-DD を DD/MM/YYYY に並べ替え、さらに " code=数字" を削除して表示する sed -E の1行コマンドを sed.txt に書く（ファイルは書き換えない）。\n')


def c3(ctx):
    need_ro(ctx)
    l = cmd_lines(ctx, 'sed.txt', 1)[0]
    t = toks(ctx, l)
    ctx.require(t[0] == 'sed' and any(x in ('-E', '-r', '-nE', '-En') for x in t), 'sed -E（拡張正規表現）を使います。')
    ctx.require(not any(x.startswith('-i') for x in t), 'ここでは -i を使わず標準出力に出します。')
    ctx.require(re.search(r'\\[1-3]', l), '日付の並べ替えには \\1 \\2 \\3 の後方参照を使います。')
    same(ctx, runc(ctx, l).stdout, ctx.data['w'], 'sed.txt')


SOL3 = r"""cat > sed.txt <<'EOF'
sed -E 's/^([0-9]{4})-([0-9]{2})-([0-9]{2})/\3\/\2\/\1/; s/ code=[0-9]+//' logs.txt
EOF"""
mission(3, 'sed -E で並べ替え置換する（ERE と PCRE の違い）',
        'sed の既定はBREですが、sed -E を付けるとEREになり、{4} + ( ) をエスケープなしで書けます。ただしEREには \\d や非貪欲 .*? はありません（それはPCREで、perlやgrep -Pの領分）。日付の形式変換を1本のsed -Eで実装してください。',
        ['日付をDD/MM/YYYYへ', 'code=欄を削除', 'sed.txtに1行'], s3, c3, SOL3,
        ["echo \"sed -E 's/ code=[0-9]+//' logs.txt\" > sed.txt",
         "echo \"sed 's/^([0-9]{4})-([0-9]{2})-([0-9]{2})/\\3\\/\\2\\/\\1/; s/ code=[0-9]+//' logs.txt\" > sed.txt"],
        'sed -E の置換では ( ) で捕まえた部分を \\1..\\9 で参照します。-E なしだと ( ) {4} + は文字そのものとして扱われ一致しません。区切り文字がスラッシュと衝突するときは s|a|b| のように別の文字を使うこともできます。\\d や \\w の一部（GNU sedの \\w）は拡張ですが、可搬性を考えて [0-9] を使うのが安全です。',
        '一致しない原因はBRE/EREの取り違えが多いです。', 's/(…)(…)(…)/\\3\\/\\2\\/\\1/ をセミコロンでつなぎ、-E を付けます。')


# ---------------------------------------------------------------- 4 awk assoc
def s4(ctx):
    regs = random.sample(['east', 'west', 'north', 'south', 'central'], 3)
    rows = []
    for _ in range(9):
        rows.append((random.choice(regs), rword(4), random.randint(10, 900)))
    put(ctx, 'sales.csv', ''.join('%s,%s,%d\n' % r for r in rows))
    s, c, t = {}, {}, 0
    for r, _, a in rows:
        s[r] = s.get(r, 0) + a
        c[r] = c.get(r, 0) + 1
        t += a
    L = ['# region total count'] + ['%-8s %6d %3d' % (r, s[r], c[r]) for r in s] + ['%-8s %6d' % ('ALL', t)]
    ctx.data['w'] = '\n'.join(sorted(L))
    ctx.write('requirements.txt', 'report.awk を書く。BEGIN で見出し行 "# region total count" を出し、地域ごとの合計と件数を連想配列で集計して、'
              'END で printf "%-8s %6d %3d\\n" で地域別に出力、最後に全体合計を printf "%-8s %6d\\n" の "ALL" 行で出す。実行は awk -F, -f report.awk sales.csv | sort\n')


def c4(ctx):
    need_ro(ctx)
    t = ctx.need_file('report.awk')
    for w in ('BEGIN', 'END', 'printf'):
        ctx.require(w in t, f'report.awk に {w} が必要です。')
    ctx.require('[' in t, '連想配列（配列[キー]）で集計します。')
    same(ctx, runc(ctx, 'awk -F, -f report.awk sales.csv | sort').stdout, ctx.data['w'], 'report.awk')


SOL4 = r"""cat > report.awk <<'EOF'
BEGIN { print "# region total count" }
{ sum[$1] += $3; cnt[$1]++; all += $3 }
END {
  for (r in sum) printf "%-8s %6d %3d\n", r, sum[r], cnt[r]
  printf "%-8s %6d\n", "ALL", all
}
EOF"""
mission(4, 'awk 上級: 連想配列・BEGIN/END・printf',
        'awk は連想配列を標準で持ち、BEGIN は入力前、END は入力後に1回だけ実行されます。printf で桁をそろえた集計表を作ります。for (k in arr) の順序は不定なので、表示時は sort に任せます。',
        ['report.awkを書く', '地域別の合計・件数と ALL 行'], s4, c4, SOL4,
        ["cat > report.awk <<'EOF'\n{ print $1 }\nEOF",
         "cat > report.awk <<'EOF'\nBEGIN { print \"# region total count\" }\n{ s += $3 }\nEND { printf \"%-8s %6d\\n\", \"ALL\", s }\nEOF"],
        '連想配列は sum[$1] += $3 のように初期化なしで使えます（未定義は0）。BEGIN で見出し、END で集計出力という型は帳票の基本です。printf は書式 %-8s（左寄せ8桁）と %6d（右寄せ数値）を指定でき、print と違い改行を自分で \\n と書きます。',
        'キーごとに足し込む配列と件数用の配列が必要です。', 'sum[$1]+=$3; cnt[$1]++ を本体に、for (r in sum) printf を END に。')


# ---------------------------------------------------------------- 5 FNR / NR
def s5(ctx):
    ids = random.sample(range(1000, 9999), 5)
    names = [rword(5) for _ in ids]
    put(ctx, 'master.txt', ''.join(f'{i} {n}\n' for i, n in zip(ids, names)))
    ords = []
    for _ in range(6):
        ords.append((random.choice(ids + [1 + random.randint(0, 99)]), random.randint(10, 500)))
    put(ctx, 'orders.txt', ''.join(f'{i} {a}\n' for i, a in ords))
    m = dict(zip(ids, names))
    ctx.data['w'] = '\n'.join(f'{m.get(i, "UNKNOWN")} {a}' for i, a in ords)
    ctx.write('requirements.txt', 'master.txt（ID 名前）と orders.txt（ID 金額）を awk 1本で結合し、orders の順に「名前 金額」を表示する（ID未登録は名前の代わりに UNKNOWN）。'
              'ファイルの区別には NR==FNR を使う。1行を cmd5.txt に書く。\n')


def c5(ctx):
    need_ro(ctx)
    l = cmd_lines(ctx, 'cmd5.txt', 1)[0]
    ctx.require(l.startswith('awk') and 'NR==FNR' in l.replace(' ', ''), 'awkで NR==FNR を使って1つ目のファイルを判別します。')
    ctx.require(l.index('master.txt') < l.index('orders.txt') if 'master.txt' in l and 'orders.txt' in l else False,
                'master.txt orders.txt の順にファイルを渡します。')
    same(ctx, runc(ctx, l).stdout, ctx.data['w'], 'cmd5')


SOL5 = r"""cat > cmd5.txt <<'EOF'
awk 'NR==FNR{n[$1]=$2; next} {print (($1 in n) ? n[$1] : "UNKNOWN"), $2}' master.txt orders.txt
EOF"""
mission(5, 'awk 上級: 複数ファイルを NR と FNR で結合する',
        'NR は全入力を通した行番号、FNR は現在のファイル内の行番号です。1つ目のファイルを読んでいる間だけ NR==FNR が成り立つので、マスタを連想配列に読み込み next で次の行へ進み、2つ目のファイルで参照する定番の結合（JOIN）が書けます。',
        ['NR==FNRで2ファイルを結合', 'cmd5.txtに1行'], s5, c5, SOL5,
        ["echo \"awk '{print \\$1, \\$2}' master.txt orders.txt\" > cmd5.txt",
         "echo \"awk 'NR==FNR{n[\\$1]=\\$2} {print n[\\$1], \\$2}' master.txt orders.txt\" > cmd5.txt"],
        'NR==FNR{…; next} の next を忘れると、1つ目のファイルの行も2つ目用の処理に流れ込みます。($1 in n) は連想配列にキーがあるかの判定で、n[$1] を参照するだけで空のキーを作ってしまうのを避けられます。ファイル順（マスタが先）が重要です。',
        '2つ目のファイルに入ったことをどう判別するか考えます。', '連想配列 n[ID]=名前 を作る → next → 2つ目で参照。')


# ---------------------------------------------------------------- 6 sed advanced
def s6(ctx):
    ports = [random.randint(1000, 9000) for _ in range(3)]
    conf = '[web]\nport=%d\nhost=a\n[db]\nhost=db1\nport=%d\n[cache]\nport=%d\n' % tuple(ports)
    put(ctx, 'app.conf', conf, readonly=False)
    new = random.randint(10000, 60000)
    ctx.data['port'] = new
    ctx.data['conf0'] = conf
    ctx.data['conf1'] = conf.replace('port=%d\n[cache]' % ports[1], 'port=%d\n[cache]' % new)
    ctx.data['conf1'] = '[web]\nport=%d\nhost=a\n[db]\nhost=db1\nport=%d\n[cache]\nport=%d\n' % (ports[0], new, ports[2])
    L = [rword(4) for _ in range(5)]
    put(ctx, 'list.txt', '\n'.join(L) + '\n')
    ctx.data['rev'] = '\n'.join(reversed(L))
    put(ctx, 'names.txt', 'banana\nurgent\n')
    ctx.data['y'] = 'bAnAnA\nUrgEnt'
    ctx.write('requirements.txt', f'sed.txt の3行: (1) sed -i.bak と[db]セクションだけを範囲アドレスで指定し、app.conf の port を {new} に書き換える（[web] と [cache] は不変、バックアップ app.conf.bak）'
              ' (2) list.txt の行をホールドスペースで逆順に出力 (3) names.txt の母音 aeiou を y/// で大文字にして出力\n')


def c6(ctx):
    need_ro(ctx)
    ls = cmd_lines(ctx, 'sed.txt', 3)
    for l in ls:
        ctx.require(toks(ctx, l)[0] == 'sed', '3行とも sed で書きます。')
    ctx.require('-i' in ls[0], '1行目は -i（インプレース）を使います。')
    ctx.require('G' in ls[1] and 'h' in ls[1], '2行目はホールドスペース（G と h）で逆順にします。')
    ctx.require('y/' in ls[2], '3行目は y/// を使います。')
    with sandbox(ctx) as w:
        runc(ctx, ls[0], cwd=w)
        ctx.require((w / 'app.conf').read_text() == ctx.data['conf1'], '[db] の port だけが書き換わっていません。')
        ctx.require((w / 'app.conf.bak').exists() and (w / 'app.conf.bak').read_text() == ctx.data['conf0'], 'app.conf.bak に元の内容を残します（-i.bak）。')
        same(ctx, runc(ctx, ls[1], cwd=w).stdout, ctx.data['rev'], '2行目')
        same(ctx, runc(ctx, ls[2], cwd=w).stdout, ctx.data['y'], '3行目')


SOL6 = r"""cat > sed.txt <<'EOF'
sed -i.bak '/^\[db\]/,/^\[/ s/^port=.*/port=<<port>>/' app.conf
sed -n '1!G;h;$p' list.txt
sed 'y/aeiou/AEIOU/' names.txt
EOF"""
mission(6, 'sed 上級: アドレス・ホールドスペース・-i・y///',
        'sed は「アドレス（行番号や /正規表現/ の範囲）」で処理対象を絞れます。ホールドスペースは行をまたいで保持する第2のバッファで、G（追記）・h（コピー）・x（交換）で行を並べ替えられます。-i でファイルを直接編集し、-i.bak なら元をバックアップ、y/// は1文字ずつの変換（tr相当）です。',
        ['範囲アドレス+-i.bakで[db]だけ変更', 'ホールドスペースで逆順', 'y///で変換'], s6, c6, SOL6,
        ["cat > sed.txt <<'EOF'\nsed -i.bak 's/^port=.*/port=<<port>>/' app.conf\nsed -n '1!G;h;$p' list.txt\nsed 'y/aeiou/AEIOU/' names.txt\nEOF",
         "cat > sed.txt <<'EOF'\nsed -i.bak '/^\\[db\\]/,/^\\[/ s/^port=.*/port=<<port>>/' app.conf\ntac list.txt\nsed 'y/aeiou/AEIOU/' names.txt\nEOF"],
        '範囲 /開始/,/終了/ は開始行から終了にマッチする行までで、終了の判定は次の行から始まります（[db]自身で終わらない）。ホールドスペースの逆順は 1!G;h;$p（2行目以降はホールドを下に追記→ホールドへコピー→最後に出力）。-n と p の組み合わせで自動出力を抑制します。y/// は正規表現ではなく文字の対応表です。-i は変更が戻せないので .bak を付ける習慣を。',
        '[db]の範囲だけに置換を限定します。', "'/^\\[db\\]/,/^\\[/ s/…/…/'、逆順は '1!G;h;$p'。")


# ---------------------------------------------------------------- 7 arrays / paramexp / heredoc
def s7(ctx):
    exts = ['tar.gz', 'zip', 'tar.bz2']
    rows = []
    for i in range(6):
        rows.append(('rep_%s_%d.%s' % (rword(3), random.randint(1, 9), random.choice(exts)), random.randint(1, 9)))
    put(ctx, 'files.txt', ''.join(f'{f} {q}\n' for f, q in rows))
    tot = {}
    out = ['Report: untitled']
    for f, q in rows:
        base, ext = f.split('.', 1)
        tot[ext] = tot.get(ext, 0) + q
        out.append(f'{base}|{ext}|{f.replace("_", "-")}')
    out.append('count=%d' % len(rows))
    for e in sorted(tot):
        out.append(f'{e}={tot[e]}')
    out.append('kinds=%d' % len(tot))
    ctx.data['w'] = '\n'.join(out)
    ctx.write('requirements.txt', 'report.sh（引数: files.txt）を書く。here document で見出し "Report: ${TITLE:-untitled}"、各行を '
              '"${f%%.*}|${f#*.}|${f//_/-}" の形で、行数を配列 names の ${#names[@]}、拡張子ごとの数量合計を declare -A の連想配列で集計し、'
              '最後に count=行数、拡張子=合計（ソート済み）、kinds=種類数 の順に出力する。\n')


def c7(ctx):
    need_ro(ctx)
    t = ctx.need_file('report.sh')
    for w, m in (('declare -A', '連想配列 declare -A'), ('<<', 'here document'), ('%%', '${var%%…}'), ('//', '${var//…}'), (':-', '${var:-…}'), ('${#', '配列の要素数')):
        ctx.require(w in t, f'report.sh に {m} が必要です。')
    r = runc(ctx, 'bash report.sh files.txt')
    same(ctx, r.stdout, ctx.data['w'], 'report.sh')
    r2 = runc(ctx, 'bash report.sh files.txt', env={'TITLE': 'Q4'})
    ctx.require(r2.stdout.splitlines()[:1] == ['Report: Q4'], 'TITLE を設定したときは見出しにその値が入ります。')


SOL7 = r"""cat > report.sh <<'EOF'
#!/bin/bash
declare -A total
names=()
cat <<EOT
Report: ${TITLE:-untitled}
EOT
while read -r f q; do
  base=${f%%.*}
  ext=${f#*.}
  names+=("$base")
  (( total[$ext] += q ))
  echo "$base|$ext|${f//_/-}"
done < "$1"
echo "count=${#names[@]}"
for e in "${!total[@]}"; do echo "$e=${total[$e]}"; done | sort
echo "kinds=${#total[@]}"
EOF"""
mission(7, 'bash: 配列・declare -A・パラメータ展開・here document',
        'bashの配列 names=() と連想配列 declare -A は、外部コマンドなしで集計する道具です。パラメータ展開 ${var:-既定値}（未設定時の既定）・${var%%パターン}（後ろから最長削除）・${var#パターン}（前から最短削除）・${var//置換元/置換先}（全置換）でファイル名を加工し、here document（<<EOT）で複数行の出力を書きます。',
        ['report.shを書く', '連想配列で拡張子別集計', 'TITLE未設定時はuntitled'], s7, c7, SOL7,
        ["cat > report.sh <<'EOF'\n#!/bin/bash\necho \"Report: $TITLE\"\ncat \"$1\"\nEOF",
         "cat > report.sh <<'EOF'\n#!/bin/bash\ndeclare -A total\necho \"Report: $TITLE\"\nwhile read -r f q; do (( total[${f#*.}] += q )); done < \"$1\"\nEOF"],
        '${f%%.*} は最後ではなく「最長の .* を末尾から削除」するので tar.gz のような複数拡張子では最初のドットから後ろをすべて消します。${f#*.} は最初のドットまでを削除、${f//_/-} は全ての _ を置換（/ が1つだと最初だけ）。${var:-x} は変数が未設定または空のとき x を使うだけで変数自体は変えません。連想配列のキー列は ${!total[@]}、要素数は ${#total[@]}。here documentの区切り語を引用すると展開が止まります。',
        '展開は文字列を加工する演算子です。', 'declare -A と (( total[$ext] += q )) と cat <<EOT を組み合わせます。')


# ---------------------------------------------------------------- 8 safe script
def s8(ctx):
    n = random.randint(3, 12)
    put(ctx, 'data.txt', '\n'.join(rword(4) for _ in range(n)) + '\n')
    ctx.data['n'] = n
    ctx.write('requirements.txt', 'safe.sh FILE を書く。set -euo pipefail、mktemp -d の作業ディレクトリを trap で必ず後始末、関数 count_lines の中で local を使い、'
              'ソート済み一時ファイルの行数を "lines=N" と出力する。引数なしや存在しない FILE は非0で終了し、一時ディレクトリを残さない。（getopts によるオプション解析は既習なので使わなくてよい）\n')


def c8(ctx):
    need_ro(ctx)
    t = ctx.need_file('safe.sh')
    ctx.require(re.search(r'set\s+-[a-z]*e', t) and 'pipefail' in t and re.search(r'set\s+-[a-z]*u', t), 'set -euo pipefail を宣言します。')
    ctx.require('trap' in t and 'mktemp' in t and 'local' in t, 'trap・mktemp・local を使います。')
    tmp = ctx.p('tmp')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    env = {'TMPDIR': str(tmp)}
    r = runc(ctx, 'bash safe.sh data.txt', env=env)
    ctx.require(r.returncode == 0 and r.stdout.strip() == 'lines=%d' % ctx.data['n'], '正常系は lines=N を出力して成功します。')
    r = runc(ctx, 'bash safe.sh nothere.txt', env=env)
    ctx.require(r.returncode != 0 and 'lines=' not in r.stdout, '存在しない入力では非0で終了し、lines= を出しません。')
    r = runc(ctx, 'bash safe.sh', env=env)
    ctx.require(r.returncode != 0, '引数なしは非0で終了します（${1:?}）。')
    ctx.require(not any(tmp.iterdir()), '終了後に一時ディレクトリが残っています（trap ... EXIT で消す）。')
    shutil.rmtree(tmp, ignore_errors=True)


SOL8 = r"""cat > safe.sh <<'EOF'
#!/bin/bash
set -euo pipefail
input=${1:?usage: safe.sh FILE}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
count_lines() {
  local f=$1
  wc -l < "$f"
}
sort "$input" > "$work/sorted"
n=$(count_lines "$work/sorted")
echo "lines=$n"
EOF"""
mission(8, 'bash: 関数・local・set -euo pipefail・trap EXIT',
        '壊れにくいシェルスクリプトの型です。set -euo pipefail（-e エラーで停止、-u 未定義変数をエラー、pipefail パイプ途中の失敗も検知）、関数内の local 変数、trap ... EXIT による後始末を組み合わせます。オプション解析の getopts は既出なので、今回は異常系の振る舞いを確かめます。',
        ['safe.shを書く', '正常系/異常系を満たす', '一時ディレクトリを残さない'], s8, c8, SOL8,
        ["cat > safe.sh <<'EOF'\n#!/bin/bash\nwork=$(mktemp -d)\nsort \"$1\" > \"$work/s\"\necho \"lines=$(wc -l < \"$work/s\")\"\nEOF",
         "cat > safe.sh <<'EOF'\n#!/bin/bash\nset -euo pipefail\nwork=$(mktemp -d)\nf() { local x=$1; wc -l < \"$x\"; }\nsort \"${1:-/dev/null}\" > \"$work/s\"\necho \"lines=$(f \"$work/s\")\"\nEOF"],
        'trap \'…\' EXIT は正常終了でも set -e による異常終了でも実行されるので、一時ファイルの後始末に最適です（SIGKILLでは動きません）。local が無い関数内変数はグローバルを汚します。${1:?メッセージ} は引数が無いとエラー終了。set -e は if の条件や && の左側では効かない点にも注意しましょう。',
        '失敗時にも後始末が走る仕組みが必要です。', 'set -euo pipefail; trap \'rm -rf "$work"\' EXIT; local f=$1')


# ---------------------------------------------------------------- 9 debug
def s9(ctx):
    k = random.randint(3, 8)
    ctx.data['line'] = k + 4
    pad = ''.join('# note %d\n' % i for i in range(k))
    body = '#!/bin/bash\n' + pad + 'SRC=$1\nDEST=$2\nmkdir -p $DEST\ncp $SRC/*.txt $DEST\n'
    put(ctx, 'deploy.sh', body)
    L = ctx.data['line']
    put(ctx, 'shellcheck.txt', f'In deploy.sh line {L}:\nmkdir -p $DEST\n         ^---^ SC2086 (info): Double quote to prevent globbing and word splitting.\n\n'
        f'In deploy.sh line {L + 1}:\ncp $SRC/*.txt $DEST\n   ^--^ SC2086 (info): Double quote to prevent globbing and word splitting.\n         ^---^ SC2086 (info): Double quote to prevent globbing and word splitting.\n')
    put(ctx, 'trace.txt', "$ bash -x deploy.sh 'my src' 'out dir'\n+ SRC='my src'\n+ DEST='out dir'\n+ mkdir -p out dir\n+ cp my src/a.txt my src/b.txt out dir\ncp: target 'dir' is not a directory\n")
    ctx.write('requirements.txt', 'trace.txt は bash -x の実行トレース、shellcheck.txt は shellcheck の指摘です。読んで、最初の警告のコード（SC番号）と行番号を diag.json に {"code":"SC…","line":N} で書き、'
              'deploy.sh を修正した fixed_deploy.sh を作る（引数のパスに空白があっても動くこと。deploy.sh は原本のまま）。\n')


def c9(ctx):
    need_ro(ctx)
    d = rj(ctx, 'diag.json')
    ctx.require(d.get('code') == 'SC2086' and d.get('line') == ctx.data['line'], 'diag.json の code と、最初の警告の行番号を確認してください。')
    ctx.need_file('fixed_deploy.sh')
    with sandbox(ctx) as w:
        (w / 'my src').mkdir()
        names = [rword(3) + '.txt' for _ in range(2)]
        for n in names:
            (w / 'my src' / n).write_text(n)
        r = runc(ctx, 'bash fixed_deploy.sh "my src" "out dir"', cwd=w)
        ctx.require(all((w / 'out dir' / n).exists() for n in names), '空白を含むパスでもコピーできるように、変数を二重引用符で囲みます。' + r.stderr[:100])


SOL9 = r"""echo '{"code":"SC2086","line":<<line>>}' > diag.json
sed -E 's/\$(SRC|DEST)/"$\1"/g' deploy.sh > fixed_deploy.sh"""
mission(9, 'シェルスクリプトのデバッグ: bash -x と shellcheck の読解',
        'bash -x は実行される各コマンドを展開後の形で表示するトレースで、変数の中身や単語分割の結果が見えます。shellcheck は静的解析で、SC2086 は「引用符が無く単語分割/グロブされる」警告です。記録された出力から原因を特定し、直してください。',
        ['最初の警告の code/line を diag.json へ', '空白パスでも動く fixed_deploy.sh'], s9, c9, SOL9,
        ['echo \'{"code":"SC2086","line":<<line>>}\' > diag.json\ncp deploy.sh fixed_deploy.sh',
         'echo \'{"code":"SC2034","line":1}\' > diag.json\nsed -E \'s/\\$(SRC|DEST)/"$\\1"/g\' deploy.sh > fixed_deploy.sh'],
        'トレースの「cp my src/a.txt my src/b.txt out dir」は引用符が外れて4つの引数に分割されたことを示します。shellcheck の SC2086 の指摘は変数展開を "$var" と囲めば解消します。bash -x でトレースし、set -x / set +x で一部だけ有効にもできます。PS4 を設定すると行番号付きのトレースにできます。shellcheck が無い環境でも、記録された指摘の読み方を知っていれば原因を絞れます。',
        '空白を含む値が単語分割されています。', '変数展開を "$SRC" "$DEST" と囲み、sed -E で一括置換します。')


# ---------------------------------------------------------------- 10 perl
def s10(ctx):
    sc = [random.randint(10, 90) for _ in range(5)]
    u = [rword(5) for _ in sc]
    put(ctx, 'data.txt', ''.join(f'user={a} score={b}\n' for a, b in zip(u, sc)))
    ctx.data['w1'] = '\n'.join(f'user={a} score={b + 10}' for a, b in zip(u, sc))
    ctx.data['w2'] = str(sum(sc))
    nh = 'new-' + rword(4)
    ctx.data['newhost'] = nh
    conf = 'name=app\nhost=old-%s\nport=80\n' % rword(3)
    put(ctx, 'net.conf', conf, readonly=False)
    ctx.data['conf0'] = conf
    ctx.data['conf1'] = re.sub(r'^host=.*', 'host=' + nh, conf, flags=re.M)
    ctx.write('requirements.txt', f'perl.txt の3行: (1) perl -pe で data.txt の score を +10 して表示（s///e）(2) perl -ne で score の合計だけ表示（END ブロック）'
              f'(3) perl -i.bak -pe で net.conf の host= 行を host={nh} に置換（バックアップ net.conf.bak）\n')


def c10(ctx):
    need_ro(ctx)
    ls = cmd_lines(ctx, 'perl.txt', 3)
    ctx.require(all(toks(ctx, x)[0] == 'perl' for x in ls), '3行とも perl で始めます。')
    ctx.require('-pe' in ls[0].split() and '-ne' in ls[1].split() and re.search(r'-i\S*\s', ls[2]), '1行目は -pe、2行目は -ne、3行目は -i を使います。')
    if shutil.which('perl'):
        with sandbox(ctx) as w:
            same(ctx, runc(ctx, ls[0], cwd=w).stdout, ctx.data['w1'], '1行目')
            same(ctx, runc(ctx, ls[1], cwd=w).stdout, ctx.data['w2'], '2行目')
            runc(ctx, ls[2], cwd=w)
            ctx.require((w / 'net.conf').read_text() == ctx.data['conf1'], '3行目で net.conf の host= 行が置換されていません。')
            ctx.require((w / 'net.conf.bak').exists(), '-i.bak でバックアップを残します。')


SOL10 = r"""cat > perl.txt <<'EOF'
perl -pe 's/score=(\d+)/"score=".($1+10)/e' data.txt
perl -ne '$s += $1 if /score=(\d+)/; END { print "$s\n" }' data.txt
perl -i.bak -pe 's/^host=.*/host=<<newhost>>/' net.conf
EOF"""
mission(10, 'Perl ワンライナー: perl -pe / -ne / -i',
        'Perl は sed/awk より強力な正規表現（PCRE相当）を持つため、ワンライナーが定番です。perl -pe は「各行にコードを実行して自動で出力」、perl -ne は「実行するだけで出力は自分で print」、perl -i[.bak] は in-place 編集です。s///e は置換部分をPerlの式として評価します。',
        ['perl -peで数値加算', 'perl -neで合計', 'perl -i.bak -peで設定置換'], s10, c10, SOL10,
        ["cat > perl.txt <<'EOF'\nsed 's/score=/score=1/' data.txt\nawk '{print}' data.txt\nsed -i 's/host=.*/host=x/' net.conf\nEOF",
         "cat > perl.txt <<'EOF'\nperl -pe 's/score=(\\d+)/score=$1/' data.txt\nperl -pe 'print' data.txt\nperl -i -pe 's/^host=.*/host=<<newhost>>/' net.conf\nEOF"],
        '-p は while(<>){…; print} で囲み、-n は print なしで囲みます。-i を付けないと元ファイルは変わりません。-i.bak は元をバックアップして上書きします。END { } は全行処理後に1回実行されるので集計に使えます。-e は複数指定でき、-l で改行処理も自動化できます。',
        '行ごと処理か集計かで -p と -n を使い分けます。', '-pe + s///e、-ne + END、-i.bak -pe。')


# ---------------------------------------------------------------- 11 Makefile
def s11(ctx):
    names = [rword(4) for _ in range(3)]
    for n in names:
        put(ctx, f'src/{n}.txt', rword(8) + '\n')
    ctx.data['names'] = names
    ctx.write('requirements.txt', 'Makefile を書く。変数 SRC := $(wildcard src/*.txt) と、そこから作る OUT := $(SRC:src/%.txt=build/%.up)。最初のターゲットは all（OUTに依存）。'
              'パターンルール build/%.up: src/%.txt は mkdir -p build の後 tr a-z A-Z < $< > $@ で大文字化。clean は rm -rf build。all と clean は .PHONY に。（レシピ行の先頭はTab）\n')


def c11(ctx):
    need_ro(ctx)
    t = ctx.need_file('Makefile')
    lines = t.splitlines()
    ctx.require(any(re.match(r'^\w+\s*:?=', x) for x in lines), '変数（SRC := …）を定義します。')
    ctx.require(any(re.match(r'^\.PHONY\s*:', x) and 'all' in x and 'clean' in x for x in lines), '.PHONY: all clean を宣言します。')
    ctx.require(any(re.match(r'^build/%\.up\s*:\s*src/%\.txt', x) for x in lines), 'パターンルール build/%.up: src/%.txt が必要です。')
    rec = [x for x in lines if x.startswith('\t')]
    ctx.require(rec, 'レシピ行は先頭をTab文字にします（空白ではmakeがエラーにします）。')
    ctx.require(any('$@' in x for x in rec) and any('$<' in x for x in rec), '自動変数 $@ と $< を使います。')
    ctx.require(any('rm' in x and 'build' in x for x in rec), 'clean ターゲットで build を消します。')
    tg = [x for x in lines if re.match(r'^[A-Za-z_./%-]+\s*:', x) and not x.startswith('.') and ':=' not in x]
    ctx.require(tg and tg[0].startswith('all'), '最初のターゲットを all にします（引数なしの make で動く既定）。')
    if shutil.which('make'):
        with sandbox(ctx) as w:
            r = runc(ctx, 'make', cwd=w)
            for n in ctx.data['names']:
                f = w / 'build' / (n + '.up')
                ctx.require(f.exists() and f.read_text() == (w / 'src' / (n + '.txt')).read_text().upper(), 'make で build/*.up が大文字化されて作られません。' + r.stderr[:150])
            runc(ctx, 'make clean', cwd=w)
            ctx.require(not (w / 'build').exists(), 'make clean で build が消えません。')


SOL11 = """cat > Makefile <<'EOF'
SRC := $(wildcard src/*.txt)
OUT := $(SRC:src/%.txt=build/%.up)

.PHONY: all clean

all: $(OUT)

build/%.up: src/%.txt
	mkdir -p build
	tr a-z A-Z < $< > $@

clean:
	rm -rf build
EOF"""
mission(11, 'Makefile 基礎: 変数・パターンルール・.PHONY・自動変数',
        'Makefile は「ターゲット: 依存」と、Tabで始まるレシピで構成されます。更新されたファイルだけ作り直すのが make の強みです。変数 := 、パターンルール %、自動変数 $@（ターゲット）と $<（最初の依存）、実ファイルを作らない .PHONY を使って、src の各ファイルを大文字化する小さなビルドを書きます。',
        ['Makefileを書く', '変数/パターンルール/.PHONY/自動変数', 'clean'], s11, c11, SOL11,
        ["printf 'all:\\n    echo hi\\n' > Makefile",
         "printf 'SRC := $(wildcard src/*.txt)\\nall:\\n\\techo $(SRC)\\nclean:\\n\\trm -rf build\\n' > Makefile"],
        'Makefileのレシピ行がTabでないと "missing separator" になります。.PHONY を付けないと all や clean という名前のファイルがあるとき実行されません。$@ はターゲット名、$< は最初の依存、$^ は依存全部。make -n は実行せず表示だけ（ドライラン）、make -j は並列実行です。この環境に make が無くても、構造を読んで書けることが重要です。',
        'Tabの有無と、パターンルール（%）の対応関係を確認します。', 'build/%.up: src/%.txt、レシピは tr a-z A-Z < $< > $@。')


# ---------------------------------------------------------------- 12 packaging
def s12(ctx):
    pn = 'tool-' + secrets.token_hex(2)
    ver = '1.%d.%d' % (random.randint(0, 9), random.randint(0, 9))
    ctx.data.update(pname=pn, ver=ver)
    put(ctx, f'pkg/usr/local/bin/{pn}', f'#!/bin/sh\necho {pn}\n')
    os.chmod(ctx.p(f'pkg/usr/local/bin/{pn}'), 0o755)
    ctx.mkdir('pkg/DEBIAN')
    ctx.write('requirements.txt', f'パッケージ {pn} バージョン {ver} を作る。(1) pkg/DEBIAN/control（Package/Version/Architecture: all/Maintainer/Description）'
              f'(2) rpm用 app.spec（Name/Version/Release/Summary/License/BuildArch: noarch と %description %install %files。%install では install -D で %{{buildroot}}/usr/local/bin/{pn} へ）'
              f'(3) build.txt の2行: dpkg-deb --build で {pn}_{ver}_all.deb を作る行、rpmbuild -ba app.spec の行\n')


def c12(ctx):
    need_ro(ctx)
    pn, ver = ctx.data['pname'], ctx.data['ver']
    ctl = {}
    for x in ctx.need_file('pkg/DEBIAN/control').splitlines():
        if ': ' in x and not x.startswith(' '):
            k, v = x.split(': ', 1)
            ctl[k] = v.strip()
    ctx.require(ctl.get('Package') == pn and ctl.get('Version') == ver and ctl.get('Architecture') == 'all', 'control の Package/Version/Architecture を確認します。')
    ctx.require(ctl.get('Maintainer') and ctl.get('Description'), 'control に Maintainer と Description が必要です。')
    sp = ctx.need_file('app.spec')
    for k, v in (('Name', pn), ('Version', ver), ('BuildArch', 'noarch')):
        ctx.require(re.search(rf'^{k}:\s*{re.escape(v)}\s*$', sp, re.M), f'spec の {k}: {v} がありません。')
    for k in ('Release', 'Summary', 'License'):
        ctx.require(re.search(rf'^{k}:\s*\S', sp, re.M), f'spec に {k}: が必要です。')
    ctx.require(re.search(r'^%description', sp, re.M) and re.search(r'^%install', sp, re.M) and re.search(r'^%files', sp, re.M), 'spec に %description %install %files が必要です。')
    ctx.require(re.search(r'install\s.*%\{?buildroot\}?', sp), '%install では buildroot 配下に install します。')
    ctx.require(re.search(r'^%files\s*\n(.*\n)*?/usr/local/bin/' + re.escape(pn), sp, re.M), '%files にインストール先のパスを列挙します。')
    ls = cmd_lines(ctx, 'build.txt', 2)
    ctx.require(ls[0].startswith('dpkg-deb') and '--build' in ls[0] and f'{pn}_{ver}_all.deb' in ls[0], '1行目は dpkg-deb --build pkg 名前_版_all.deb です。')
    ctx.require(ls[1].startswith('rpmbuild') and '-ba' in ls[1] and 'app.spec' in ls[1], '2行目は rpmbuild -ba app.spec です。')
    if shutil.which('dpkg-deb'):
        with sandbox(ctx) as w:
            r = runc(ctx, 'dpkg-deb --build --root-owner-group pkg out.deb', cwd=w)
            ctx.require(r.returncode == 0, 'dpkg-deb --build に失敗します: ' + (r.stderr or r.stdout)[:200])


SOL12 = r"""cat > pkg/DEBIAN/control <<'EOF'
Package: <<pname>>
Version: <<ver>>
Architecture: all
Maintainer: Trainee <trainee@example.invalid>
Description: Demo tool
EOF
cat > app.spec <<'EOF'
Name: <<pname>>
Version: <<ver>>
Release: 1
Summary: Demo tool
License: MIT
BuildArch: noarch

%description
Demo tool for training.

%install
install -D -m 0755 usr/local/bin/<<pname>> %{buildroot}/usr/local/bin/<<pname>>

%files
/usr/local/bin/<<pname>>
EOF
cat > build.txt <<'EOF'
dpkg-deb --build pkg <<pname>>_<<ver>>_all.deb
rpmbuild -ba app.spec
EOF"""
mission(12, 'パッケージ作成: dpkg-deb と DEBIAN/control、rpmbuild の spec',
        'Debian系は、インストール先の木構造と DEBIAN/control（メタ情報）を用意して dpkg-deb --build で .deb にします。RPM系は spec ファイルに Name/Version/Release と %description・%install・%files を書き、rpmbuild -ba でバイナリ/ソース両方を作ります。同じ成果物を両形式で記述してください。',
        ['DEBIAN/controlを書く', 'app.specを書く', 'build.txtにビルド行'], s12, c12, SOL12,
        ["printf 'Package: x\\n' > pkg/DEBIAN/control\ntouch app.spec\necho 'tar czf x.tgz pkg' > build.txt",
         "cat > pkg/DEBIAN/control <<'EOF'\nPackage: <<pname>>\nVersion: <<ver>>\nArchitecture: all\nMaintainer: T <t@example.invalid>\nDescription: d\nEOF\nprintf 'Name: <<pname>>\\n' > app.spec\nprintf 'dpkg-deb --build pkg <<pname>>_<<ver>>_all.deb\\nrpmbuild -ba app.spec\\n' > build.txt"],
        'control の Description は必須で、続きの行は先頭を空白にします。dpkg-deb --build は DEBIAN ディレクトリの権限（0755）に厳しいです。spec の %install は buildroot（仮の根）へ配置し、%files はそのうちパッケージに含めるものを列挙します。%changelog もあると正式です。BuildArch: noarch はアーキ非依存（スクリプトなど）の意味です。',
        '2つの形式でメタ情報の書き方が違います。', 'Debianは key: value、RPMの spec は Name: と %セクション。')


# ---------------------------------------------------------------- 13 source / kernel build
def s13(ctx):
    pfx = '/opt/app-' + secrets.token_hex(2)
    ctx.data['pfx'] = pfx
    mods = random.sample(['CONFIG_USB_STORAGE', 'CONFIG_FUSE_FS', 'CONFIG_BTRFS_FS', 'CONFIG_NFS_FS', 'CONFIG_VFAT_FS'], 3)
    ctx.data['mods'] = mods
    ctx.data['m0'], ctx.data['m1'] = mods[0], mods[1]
    base = ['CONFIG_64BIT=y', 'CONFIG_SMP=y', '# %s is not set' % mods[0], 'CONFIG_EXT4_FS=y', '# %s is not set' % mods[1], '# %s is not set' % mods[2]]
    ctx.write('.config', '\n'.join(base) + '\n')
    put(ctx, 'config.orig', '\n'.join(base) + '\n')
    exp = list(base)
    exp[2] = mods[0] + '=m'
    exp[4] = mods[1] + '=m'
    ctx.data['exp'] = '\n'.join(exp)
    put(ctx, 'build.log', f'$ make install\ninstall: cannot create regular file \'{pfx}/bin/app\': Permission denied\nmake: *** [Makefile:12: install] Error 1\n')
    ctx.write('requirements.txt', f'(A) steps.txt の3行: 一般ユーザーで {pfx} を接頭辞に ./configure（--prefix）→ make -j4 → make に DESTDIR=$PWD/stage を付けて install（build.log の権限エラーを避け、stage 配下に仮インストール）。'
              f'(B) checkinstall.txt に、make install の代わりに .deb を作る checkinstall の1行（例 checkinstall -D make install）。'
              f'(C) kbuild.txt の4行: カーネルビルド手順を make menuconfig → make -j（並列ビルド）→ make modules_install → make install の順に。'
              f'(D) .config の {mods[0]} と {mods[1]} を =m（モジュール）にする。\n')


def c13(ctx):
    need_ro(ctx)
    pfx = ctx.data['pfx']
    s = cmd_lines(ctx, 'steps.txt', 3)
    t = toks(ctx, s[0])
    ctx.require(t[0] == './configure' and f'--prefix={pfx}' in t, '1行目は ./configure --prefix=' + pfx + ' です。')
    t = toks(ctx, s[1])
    ctx.require(t[0] == 'make' and 'install' not in t and any(x.startswith('-j') for x in t), '2行目は make -jN（ビルドだけ）です。')
    t = toks(ctx, s[2])
    ctx.require(t[0] == 'make' and 'install' in t and any(x.startswith('DESTDIR=') and 'stage' in x for x in t), '3行目は make DESTDIR=$PWD/stage install です。')
    t = toks(ctx, cmd_lines(ctx, 'checkinstall.txt', 1)[0])
    ctx.require(t[0] == 'checkinstall' and 'make' in t, 'checkinstall で make install を包みます。')
    k = [toks(ctx, x) for x in cmd_lines(ctx, 'kbuild.txt', 4)]
    ctx.require(k[0] == ['make', 'menuconfig'], '1行目は make menuconfig。')
    ctx.require(k[1][0] == 'make' and any(x.startswith('-j') for x in k[1]) and not any(x in k[1] for x in ('install', 'modules_install', 'menuconfig')), '2行目は make -jN のビルド。')
    ctx.require(k[2] == ['make', 'modules_install'], '3行目は make modules_install。')
    ctx.require(k[3] == ['make', 'install'], '4行目は make install。')
    same(ctx, ctx.need_file('.config'), ctx.data['exp'], '.config')


SOL13 = r"""cat > steps.txt <<'EOF'
./configure --prefix=<<pfx>>
make -j4
make DESTDIR=$PWD/stage install
EOF
echo 'checkinstall -D make install' > checkinstall.txt
cat > kbuild.txt <<'EOF'
make menuconfig
make -j4
make modules_install
make install
EOF
sed -i -E 's/^# (<<m0>>|<<m1>>) is not set$/\1=m/' .config"""
mission(13, 'ソースからのビルドとカーネルビルド手順の読解',
        './configure && make && make install が定番の手順です。--prefix でインストール先を決め、make install に DESTDIR（仮の根）を渡すと stage の下へ集められ、そのまま配布物やパッケージ化に使えます。checkinstall は make install を監視してパッケージ化する考え方です。カーネルは make menuconfig で .config を作り、make でビルド、make modules_install でモジュールを /lib/modules へ、make install でカーネル本体を入れます。',
        ['steps.txtのビルド手順', 'checkinstall.txt', 'kbuild.txtの順序', '.configでモジュール化'], s13, c13, SOL13,
        ["echo './configure' > steps.txt\necho 'make' >> steps.txt\necho 'make install' >> steps.txt\necho 'make install' > checkinstall.txt\necho 'make' > kbuild.txt",
         "printf '%s\\n' './configure --prefix=<<pfx>>' 'make -j4' 'make DESTDIR=$PWD/stage install' > steps.txt\necho 'checkinstall -D make install' > checkinstall.txt\nprintf '%s\\n' 'make menuconfig' 'make -j4' 'make modules_install' 'make install' > kbuild.txt\necho '<<m0>>=m' >> .config"],
        'DESTDIR は ./configure ではなく make install の引数で、インストールパスの先頭に付けるだけです（--prefix とは別物）。.config では =y が組み込み、=m がモジュール、「# CONFIG_X is not set」が無効です。make menuconfig を使わず .config を直接編集した後は make oldconfig で整合させるのが安全です。modules_install の後に install を行うのが一般的な順序です。実機の /boot を変えるため、ここでは読んで書くだけにします。',
        'prefixとDESTDIRとcheckinstallの役割が違います。', '--prefix=… / make DESTDIR=$PWD/stage install / sed -i で =m に。')


# ---------------------------------------------------------------- 14 diff / patch
def s14(ctx):
    port = random.randint(1000, 9000)
    old = f'[main]\nport={port}\nmode=old\nlegacy=1\n'
    new = f'[main]\nport={port + 1}\nmode=new\n'
    put(ctx, 'old/app.conf', old)
    put(ctx, 'new/app.conf', new)
    put(ctx, 'new/added.conf', f'extra={port}\n')
    ctx.write('requirements.txt', 'old/ から new/ への差分（変更と新規ファイル added.conf を含む）を、patch -p1 で適用できる統一形式（diff -u）で再帰的に fix.patch に保存し、'
              '適用前の確認用に patch -p1 --dry-run で fix.patch を読ませる1行を apply.txt に書く。\n')


def c14(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('fix.patch').strip(), 'fix.patch が空です。')
    l = cmd_lines(ctx, 'apply.txt', 1)[0]
    ctx.require(l.startswith('patch') and '-p1' in l and '--dry-run' in l and 'fix.patch' in l, 'apply.txt は patch -p1 --dry-run < fix.patch です。')
    if shutil.which('patch'):
        with sandbox(ctx) as w:
            (w / 'target').mkdir()
            shutil.copy(w / 'old' / 'app.conf', w / 'target' / 'app.conf')
            r = runc(ctx, 'patch -p1 < ../fix.patch', cwd=w / 'target')
            ctx.require(r.returncode == 0, 'patch -p1 で適用できません: ' + (r.stdout + r.stderr)[:200])
            ctx.require((w / 'target' / 'app.conf').read_text() == (w / 'new' / 'app.conf').read_text(), '適用結果が new と一致しません。')
            ctx.require((w / 'target' / 'added.conf').exists(), '新規ファイル added.conf が含まれていません（diff の -N / -r）。')


SOL14 = """diff -urN old new > fix.patch
echo 'patch -p1 --dry-run < fix.patch' > apply.txt"""
mission(14, 'diff と patch の応用: 再帰差分・-p・--dry-run',
        'diff -u は統一形式、-r はディレクトリを再帰比較、-N は存在しない側を空ファイル扱いにして新規・削除ファイルも差分に含めます。patch の -p1 は先頭のパス要素（old/ や new/）を1つ削って適用し、--dry-run は書き込まずに適用可否だけを確かめます。',
        ['diff -urNでfix.patch', 'apply.txtに--dry-runの確認行'], s14, c14, SOL14,
        ["diff old/app.conf new/app.conf > fix.patch\necho 'patch fix.patch' > apply.txt",
         "diff -ur old new > fix.patch\necho 'patch -p1 --dry-run < fix.patch' > apply.txt"],
        '-N を忘れると新規ファイルは "Only in new: added.conf" となり差分に入りません。-u なしの通常形式でも patch は解釈できますが、文脈が無く壊れやすいので統一形式を使います。逆適用は patch -R。適用で拒否された部分は .rej に残ります。',
        '新規ファイルまで含める再帰オプションが必要です。', 'diff -urN old new、patch -p1 --dry-run。')


# ---------------------------------------------------------------- 15 vim / tmux / screen
def s15(ctx):
    n = random.randint(5, 8)
    rows = ['item-%02d %s' % (random.randint(1, 99), rword(4)) for _ in range(n)]
    put(ctx, 'data.txt', '\n'.join(rows) + '\n', readonly=False)
    ctx.data['rows0'] = rows
    ctx.data['w'] = '\n'.join(re.sub(r'item-(\d+)', r'\1:item', x) for x in rows)
    ctx.data['n'] = n
    ctx.data['m1'] = n - 1
    k = random.randint(2, n - 1)
    ctx.data['k'] = k
    ctx.data['hist'] = random.choice([5000, 10000, 20000])
    ctx.write('requirements.txt',
              f'(1) vimcmd.txt: data.txt の item-NN を NN:item に直す :%s コマンド1行（very magic \\v とキャプチャ \\1、フラグ g）。\n'
              f'(2) macro.txt: 各行の末尾に ; を付けて次の行へ進むマクロを a レジスタに録画し（qa A;<Esc> j q）、残りの行に繰り返す（{n - 1}@a）を続けて1行で。\n'
              f'(3) reg.txt: {ctx.data["k"]} 行目へ移動し、その行を a レジスタにヤンクして最終行へ移動し貼り付ける、のキー列を1行で（G と "ay… "ap を使う）。\n'
              f'(4) tmux.conf: prefix を C-a に（C-b は unbind）、mouse on、history-limit {ctx.data["hist"]}、bind | split-window -h、mode-keys vi（set -g / setw -g）。\n'
              f'(5) screenrc: escape ^Aa、defscrollback {ctx.data["hist"]}、startup_message off。\n')


def c15(ctx):
    need_ro(ctx)
    v = cmd_lines(ctx, 'vimcmd.txt', 1)[0]
    ctx.require(v.lstrip(':').startswith('%s') and '\\1' in v, ':%s と後方参照 \\1 を使います。')
    if shutil.which('vim'):
        with sandbox(ctx) as w:
            subprocess.run(['vim', '-Nes', '-u', 'NONE', '-i', 'NONE', '-c', v.lstrip(':'), '-c', 'wq', 'data.txt'], cwd=str(w),
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
            same(ctx, (w / 'data.txt').read_text(), ctx.data['w'], 'vimcmd.txt を適用した data.txt')
    ctx.require(cmd_lines(ctx, 'macro.txt', 1)[0] == 'qaA;<Esc>jq%d@a' % (ctx.data['n'] - 1), 'macro.txt は qaA;<Esc>jq と繰り返し回数@a です。')
    ctx.require(cmd_lines(ctx, 'reg.txt', 1)[0] == '%dG"ayyG"ap' % ctx.data['k'], 'reg.txt は行番号G "ayy G "ap です。')
    tm = ctx.need_file('tmux.conf').splitlines()
    h = ctx.data['hist']
    for pat, msg in ((r'^set(-option)?\s+-g\s+prefix\s+C-a$', 'set -g prefix C-a'), (r'^unbind(-key)?\s+C-b$', 'unbind C-b'),
                     (r'^set(-option)?\s+-g\s+mouse\s+on$', 'set -g mouse on'), (r'^set(-option)?\s+-g\s+history-limit\s+%d$' % h, f'set -g history-limit {h}'),
                     (r'^bind(-key)?\s+\|\s+split-window\s+-h', 'bind | split-window -h'),
                     (r'^(setw|set-window-option|set\s+-w)\s+-g\s+mode-keys\s+vi$', 'setw -g mode-keys vi')):
        ctx.require(any(re.match(pat, x.strip()) for x in tm), 'tmux.conf に ' + msg + ' が必要です。')
    sc = ctx.need_file('screenrc').splitlines()
    for pat, msg in ((r'^escape\s+\^Aa$', 'escape ^Aa'), (r'^defscrollback\s+%d$' % h, f'defscrollback {h}'), (r'^startup_message\s+off$', 'startup_message off')):
        ctx.require(any(re.match(pat, x.strip()) for x in sc), 'screenrc に ' + msg + ' が必要です。')


SOL15 = r"""echo ':%s/\vitem-(\d+)/\1:item/g' > vimcmd.txt
echo 'qaA;<Esc>jq<<m1>>@a' > macro.txt
echo '<<k>>G"ayyG"ap' > reg.txt
cat > tmux.conf <<'EOF'
set -g prefix C-a
unbind C-b
set -g mouse on
set -g history-limit <<hist>>
bind | split-window -h
setw -g mode-keys vi
EOF
cat > screenrc <<'EOF'
escape ^Aa
defscrollback <<hist>>
startup_message off
EOF"""
mission(15, 'vim 上級（マクロ・:%s・レジスタ）と tmux/screen 設定',
        'vim のマクロは q{レジスタ}…q で録画し @{レジスタ} で再生、回数付き 7@a で繰り返せます。:%s/パターン/置換/g は全行置換で、\\v（very magic）なら ( ) + をエスケープなしで書け、\\1 でキャプチャを参照します。"ayy / "ap は名前付きレジスタへのヤンクと貼り付けです。端末多重化の tmux と screen は設定ファイル（tmux.conf / screenrc）でプレフィックスや履歴量を決めます。',
        ['vimcmdを動かして変換', 'macro/regのキー列', 'tmux.confとscreenrc'], s15, c15, SOL15,
        ["echo ':%s/item/x/g' > vimcmd.txt\necho 'qa@a' > macro.txt\necho 'yy' > reg.txt\necho 'set -g mouse on' > tmux.conf\necho 'startup_message off' > screenrc",
         "echo ':%s/\\vitem-(\\d+)/\\1:item/g' > vimcmd.txt\necho 'qaA;<Esc>jq3@a' > macro.txt\necho '3G\"ayyG\"ap' > reg.txt\necho 'set -g prefix C-a' > tmux.conf\necho 'escape ^Aa' > screenrc"],
        'マクロは最初の1回の録画中にも実行されるため、残りの行数は「全行数-1」です。:%s の \\v は very magic で、(\\d+) がそのままグループになります。tmux の設定変更は tmux source-file ~/.tmux.conf で反映します。screen は escape で Ctrl-a に変えるのが定番で、defscrollback でスクロールバックを増やします。ここでは実際のvim -Nes で置換を検証します。',
        '録画中の1回ぶんも数えます。', ':%s/\\v…(\\d+)…/\\1…/g、qa…q、"ayy と "ap、tmux/screen は設定行を書くだけ。')


# ---------------------------------------------------------------- 16 locale / env
def s16(ctx):
    d = 'tools-' + secrets.token_hex(2)
    ed = random.choice(['vim', 'nano'])
    ctx.data.update(tdir=d, ed=ed)
    ctx.write('requirements.txt', f'profile（~/.profile 相当：ログイン時に1回）と bashrc（~/.bashrc 相当：対話シェルごと）を書く。\n'
              f'profile: $HOME/{d}/bin を PATH の先頭に追加、export で LANG=C.UTF-8 と LC_COLLATE=C と EDITOR={ed} を子プロセスに継承、LC_ALL は設定しない（全ロケール設定を上書きするため）、'
              f'bash なら ~/.bashrc を読み込む（[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"）。\nbashrc: alias ll=\'ls -l\' だけ書く（PATH や export は書かない）。\n')


def c16(ctx):
    need_ro(ctx)
    p = ctx.need_file('profile')
    b = ctx.need_file('bashrc')
    ctx.require('.bashrc' in p, 'profile から ~/.bashrc を読み込みます。')
    ctx.require(re.search(r'^alias\s+ll=', b, re.M) and 'export' not in b and 'PATH' not in b, 'bashrc には alias ll=… だけを書きます（環境変数は profile）。')
    ctx.require('LC_ALL' not in re.sub(r'#.*', '', p), 'LC_ALL は設定しません。')
    d, ed = ctx.data['tdir'], ctx.data['ed']
    cmd = ('. ./profile; sh -c \'printf "%s|%s|%s|%s|%s" "$PATH" "$EDITOR" "$LANG" "$LC_COLLATE" "${LC_ALL-unset}"\'')
    e = {'HOME': '/home/trainee', 'PATH': '/usr/bin:/bin'}
    try:
        r = subprocess.run(['bash', '--noprofile', '--norc', '-c', cmd], cwd=str(ctx.work), env=e, capture_output=True, text=True, timeout=10,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        ctx.fail('profile の実行が終わりません。')
    want = f'/home/trainee/{d}/bin:/usr/bin:/bin|{ed}|C.UTF-8|C|unset'
    ctx.require(r.stdout == want, f'子プロセスから見た環境が違います。\n期待: {want}\n実際: {r.stdout}')


SOL16 = r"""cat > profile <<'EOF'
export PATH="$HOME/<<tdir>>/bin:$PATH"
export LANG=C.UTF-8
export LC_COLLATE=C
export EDITOR=<<ed>>
[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"
EOF
echo "alias ll='ls -l'" > bashrc"""
mission(16, 'ロケールと環境変数の継承: export・~/.profile と ~/.bashrc・PATH設計',
        'シェル変数は export しないと子プロセスに引き継がれません。~/.profile（ログインシェルが1回だけ読む）には PATH や locale（LANG/LC_*）などの環境変数を、~/.bashrc（対話bashが毎回読む）には alias や補完・プロンプトを置くのが原則です。PATH は先頭に置いたものが優先されます。LC_ALL は他のロケール変数を全て上書きするため常用しません。',
        ['profileに環境変数', 'bashrcにalias', '子プロセスで検証'], s16, c16, SOL16,
        ["echo 'PATH=$HOME/<<tdir>>/bin:$PATH' > profile\necho 'LANG=C.UTF-8' >> profile\necho '. ~/.bashrc' >> profile\necho \"alias ll='ls -l'\" > bashrc",
         "echo 'export PATH=$HOME/<<tdir>>/bin:$PATH' > bashrc\necho 'export LC_ALL=C.UTF-8' > profile\necho \"alias ll='ls -l'\" >> bashrc"],
        'export の無い PATH=… はそのシェル内だけで有効（ただし PATH は既に環境変数なので変更が子に伝わる）。LANG/LC_COLLATE/EDITOR は export して初めて子に渡ります。ログインシェルは ~/.bash_profile → ~/.profile を読み、~/.bashrc は自動では読まれないので、profile から明示的に読み込みます。locale -a で使えるロケールを確認できます。',
        '子プロセスから見える値で確認します。', 'export PATH="$HOME/…/bin:$PATH"、export LANG=…、profile から .bashrc を source。')


# ---------------------------------------------------------------- 17 process substitution / coproc
def s17(ctx):
    pool = random.sample(['apple', 'banana', 'cherry', 'date', 'elder', 'fig', 'grape', 'honey'], 8)
    a = random.sample(pool, 5)
    b = random.sample(pool, 5)
    put(ctx, 'a.txt', '\n'.join(a) + '\n')
    put(ctx, 'b.txt', '\n'.join(b) + '\n')
    ctx.data['w'] = '\n'.join(sorted(set(a) & set(b)))
    nums = [random.randint(1, 500) for _ in range(8)]
    put(ctx, 'nums.txt', '\n'.join(map(str, nums)) + '\n')
    ctx.data['wn'] = '\n'.join(map(str, sorted(nums)))
    ctx.write('requirements.txt', 'cmd17.txt: a.txt と b.txt の共通行を、一時ファイルを作らずプロセス置換 <( ) と comm -12 で出す1行。\n'
              'coproc.sh: coproc で sort -n を共同プロセスとして起こし、nums.txt を書き込み、書き込み側を閉じて、昇順の結果を読み出して表示する。\n')


def c17(ctx):
    need_ro(ctx)
    l = cmd_lines(ctx, 'cmd17.txt', 1)[0]
    ctx.require('<(' in l and 'comm' in l, 'comm と プロセス置換 <( ) を使います。')
    same(ctx, runc(ctx, l).stdout, ctx.data['w'], 'cmd17')
    t = ctx.need_file('coproc.sh')
    ctx.require('coproc' in t and '[1]' in t and '[0]' in t, 'coproc と、配列変数の [0]（読み）[1]（書き）を使います。')
    same(ctx, runc(ctx, 'bash coproc.sh').stdout, ctx.data['wn'], 'coproc.sh')


SOL17 = r"""echo 'comm -12 <(sort a.txt) <(sort b.txt)' > cmd17.txt
cat > coproc.sh <<'EOF'
#!/bin/bash
coproc SORTER { sort -n; }
while read -r n; do echo "$n" >&"${SORTER[1]}"; done < nums.txt
eval "exec ${SORTER[1]}>&-"
while read -r -u "${SORTER[0]}" n; do echo "$n"; done
EOF"""
mission(17, 'プロセス置換 <( ) と coproc',
        'プロセス置換 <(コマンド) は、コマンドの出力をファイル名のように渡す仕組みで、一時ファイル無しで diff や comm に2つの結果を比較させられます。coproc は非同期の共同プロセスを起こし、配列変数 NAME[0]（そこからの読み出し）と NAME[1]（そこへの書き込み）で双方向に通信できます。',
        ['プロセス置換で共通行', 'coprocでsort -n'], s17, c17, SOL17,
        ["echo 'comm -12 a.txt b.txt' > cmd17.txt\necho 'sort -n nums.txt' > coproc.sh",
         "echo 'comm -12 <(sort a.txt) <(sort b.txt)' > cmd17.txt\necho 'sort -n nums.txt' > coproc.sh"],
        'comm は入力が整列済みである必要があるので、<(sort …) で渡します。coproc の書き込み側 fd を閉じないと sort が入力終了を知れず読み出しで固まります（check側はタイムアウトで検知）。パイプ（|）は一方向で、coprocは往復できる点が違います。<( ) はbash/zshの機能で、sh（dash）では使えません。',
        'ファイルでなくコマンドの出力を渡す機能です。', "comm -12 <(sort a.txt) <(sort b.txt)、coproc SORTER { sort -n; }。")


# ---------------------------------------------------------------- 18 date / epoch
def s18(ctx):
    e1 = random.randint(1_700_000_000, 1_790_000_000)
    ctx.data['e1'] = e1
    ctx.data['w1'] = __import__('time').strftime('%Y-%m-%d %H:%M:%S', __import__('time').gmtime(e1))
    d2 = '%d-%02d-%02d %02d:%02d:%02d' % (2027, random.randint(1, 12), random.randint(1, 28), random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
    ctx.data['d2'] = d2
    ctx.data['w2'] = str(calendar.timegm(__import__('time').strptime(d2, '%Y-%m-%d %H:%M:%S')))
    import datetime
    a = datetime.date(2026, random.randint(1, 6), random.randint(1, 28))
    b = a + datetime.timedelta(days=random.randint(40, 400))
    ctx.data.update(a=a.isoformat(), b=b.isoformat(), w3=str((b - a).days))
    ctx.write('requirements.txt', f'date.txt の3行（実行環境のタイムゾーンは日本。結果はUTCで）: (1) epoch {e1} を "YYYY-MM-DD HH:MM:SS" のUTCで出す date -u -d @… 。'
              f'(2) UTCの "{d2}" の epoch 秒（+%s）。(3) {ctx.data["a"]} から {ctx.data["b"]} までの日数を、date -d と +%s の差を 86400 で割って $(( )) で出す。\n')


def c18(ctx):
    ls = cmd_lines(ctx, 'date.txt', 3)
    ctx.require('-u' in ls[0] and '-d' in ls[0] and ('@' + str(ctx.data['e1'])) in ls[0], '1行目は date -u -d @EPOCH です。')
    ctx.require('-u' in ls[1] and '-d' in ls[1] and '+%s' in ls[1], '2行目は date -u -d …  +%s です。')
    ctx.require(ls[2].count('date') >= 2 and '86400' in ls[2] and '$((' in ls[2], '3行目は $(( ($(date -d …) - $(date -d …)) / 86400 )) の形です。')
    same(ctx, runc(ctx, ls[0]).stdout, ctx.data['w1'], '1行目')
    same(ctx, runc(ctx, ls[1]).stdout, ctx.data['w2'], '2行目')
    same(ctx, runc(ctx, ls[2]).stdout, ctx.data['w3'], '3行目')


SOL18 = r"""cat > date.txt <<'EOF'
date -u -d @<<e1>> '+%Y-%m-%d %H:%M:%S'
date -u -d '<<d2>>' +%s
echo $(( ($(date -d <<b>> +%s) - $(date -d <<a>> +%s)) / 86400 ))
EOF"""
mission(18, '時間計算: date -d と epoch',
        'epoch（1970-01-01 UTC からの秒数）は時間計算の共通語です。date -d は「@epoch」や「2027-03-01 12:00」などの文字列を解釈でき、+%s で epoch 秒に、-u でタイムゾーンに左右されないUTC表示にできます。日数差は epoch の差を 86400 で割って求めます。',
        ['epochを日時に', '日時をepochに', '日数差を計算'], s18, c18, SOL18,
        ["cat > date.txt <<'EOF'\ndate -d @<<e1>> '+%Y-%m-%d %H:%M:%S'\ndate -d '<<d2>>' +%s\necho 0\nEOF",
         "cat > date.txt <<'EOF'\ndate -u -d @<<e1>> '+%Y-%m-%d %H:%M:%S'\ndate -u -d '<<d2>>'\necho $(( ($(date -d <<b>> +%s) - $(date -d <<a>> +%s)) ))\nEOF"],
        '-u を付けないと実行環境のタイムゾーン（日本ならUTC+9）で解釈・表示され、9時間ずれます。epoch は常にUTC基準なので、保存や比較には epoch、表示にだけ日時を使うのが安全です。夏時間のある地域では日数差を epoch/86400 で出すと1日ずれることがあるので、UTCで計算します。',
        'タイムゾーンと単位（秒/日）に注意します。', 'date -u -d @N、date -u -d "…" +%s、$(( (b-a)/86400 ))。')
