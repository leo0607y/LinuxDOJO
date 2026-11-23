"""Stage 31: Vim・nano・Emacsの実践。本物のvimを非対話(-Es)で使い、結果のファイルで検証する。"""
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from engine.runner import register

S = 31
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・本物の ~/.vimrc ・クリップボードは変更せず、rootも使いません。"
        "データは訓練用の偽物です。自動採点できるよう、エディタは対話ではなく vim -Nu NONE -Es（サイレントEx）で動かします。")
R = random.SystemRandom()
WORDS = ['apple', 'river', 'stone', 'cloud', 'tiger', 'maple', 'ember', 'frost', 'delta', 'lunar', 'pixel', 'quartz',
         'raven', 'solar', 'tulip', 'umber', 'vivid', 'wheat', 'zebra', 'amber', 'cedar', 'dune', 'fjord', 'grove']


def rw(n):
    return R.sample(WORDS, n)


def tag(n=3):
    return ''.join(R.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(n * 2))


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


def one_line(ctx, name):
    ls = [x for x in ctx.need_file(name).splitlines() if x.strip()]
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0].strip()


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def same(ctx, name, lines, what=''):
    got = ctx.need_file(name).split('\n')
    want = list(lines) + ['']
    if got != want:
        for i, (g, w) in enumerate(zip(got, want), 1):
            if g != w:
                ctx.fail(f'{name} の{i}行目が違います。期待「{w}」/ 実際「{g}」。{what}')
        ctx.fail(f'{name} の行数が違います（期待 {len(want) - 1} 行 / 実際 {len(got) - 1} 行）。{what}')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'31-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='まず対話で試し、うまくいった手順を -Es のスクリプトにすると再現性が上がります。壊してよいコピーで確かめてから本物に適用しましょう。')


# ---------------------------------------------------------------- 1 motions
def s1(ctx):
    w = rw(8)
    ctx.data.update(w=w)
    lines = [f'{w[0]} {w[1]} {w[2]} {w[3]}', f'{w[4]} {w[5]} {w[6]}', f'{w[7]} tail', 'calc(a, b) = a*b',
             f'{w[0]}:x:1000:home', f'{w[1]}=value', 'FOOTER']
    put(ctx, 'nav.txt', '\n'.join(lines) + '\n')
    ctx.write('requirements.txt', 'nav.txt を原本のまま残し、コピー out.txt に次の編集をモーションだけで行う。\n'
              '1行目 0 w w D / 2行目 $ b D / 3行目 0 e D / 4行目 0 f( % D / 5行目 0 f: ; ; , D / 6行目 0 t= D / 最終行 G 0 x\n'
              '（行へは gg, 2G, G で移動）。out.txt を保存。\n')


def c1(ctx):
    need_ro(ctx)
    w = ctx.data['w']
    same(ctx, 'out.txt', [f'{w[0]} {w[1]} ', f'{w[4]} {w[5]} ', w[7][:-1], 'calc(a, b', f'{w[0]}:x', w[1][:-1], 'OOTER'],
         '要件の順にモーションを実行した結果と比べています。')


SOL1 = """cp nav.txt out.txt
vim -Nu NONE -Es out.txt -c 'normal gg0wwD' -c 'normal 2G$bD' -c 'normal 3G0eD' -c 'normal 4G0f(%D' -c 'normal 5G0f:;;,D' -c 'normal 6G0t=D' -c 'normal G0x' -c 'wq'"""
mission(1, 'Vimのモードとモーション（w b e 0 $ gg G % f t ; ,）',
        'Vimはノーマル・インサート・ビジュアル・コマンドラインの4モードで動き、カーソル移動(モーション)がオペレータの「範囲」になります。w b e は単語単位、0 は行頭、$ は行末、gg は先頭行、G は最終行、% は対応する括弧、f と t は行内の文字検索（f はその文字の上、t はその手前）で ; が同方向に繰り返し、, が逆方向に繰り返します。requirements.txtの通りに out.txt を作ってください。対話なら vim out.txt を開いて同じキーを打ちます。',
        ['out.txt が要件の編集結果と一致', 'nav.txt は原本のまま'], s1, c1, SOL1,
        ["cp nav.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg0wwD' -c 'normal 2G$bD' -c 'normal 3G0eD' -c 'normal 4G0f(D' -c 'normal 5G0f:;;,D' -c 'normal 6G0t=D' -c 'normal G0x' -c 'wq'",
         "cp nav.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg0wwD' -c 'wq'"],
        '-c "normal キー列" はノーマルモードのキーをそのまま実行します。D は行末まで削除、x は1文字削除。e は単語末尾に止まるため 0eD は単語の最後の1文字から消し、t= は = の手前で止まります。f: の後の ; は次のコロン、, は逆向きに戻ります。w b e 0 $ gg G % f t ; , を組み合わせると、マウスなしで素早く位置決めできます。',
        'D は「カーソルから行末まで」を消します。まず各行でカーソルがどこへ止まるかを考えます。', 'vim -Nu NONE -Es ファイル -c \'normal キー列\' -c wq の形で行ごとに実行します。')


# ---------------------------------------------------------------- 2 operators
def s2(ctx):
    old, new = rw(2)
    ctx.data.update(old=old, new=new + tag(1))
    put(ctx, 'edit.txt', f'user {old} logged in\nmsg = "delete me"\ncall(arg1, arg2) end\n\npara one\npara two\n\nlast\n')
    ctx.write('requirements.txt', f'edit.txt のコピー out.txt を作り、1行目の2語目({old})を {ctx.data["new"]} に ciw で置換、2行目の "..." の中身を di" で空に、3行目の (arg1, arg2) を ya( でヤンクして行末へ $p で貼る、5行目の段落を dap で削除。\n')


def c2(ctx):
    need_ro(ctx)
    same(ctx, 'out.txt', [f'user {ctx.data["new"]} logged in', 'msg = ""', 'call(arg1, arg2) end(arg1, arg2)', '', 'last'])


SOL2 = """cp edit.txt out.txt
vim -Nu NONE -Es out.txt -c 'normal 1Gwciw<<new>>' -c 'normal 2Gf"di"' -c 'normal 3Gf(ya($p' -c 'normal 5Gdap' -c 'wq'"""
mission(2, 'オペレータ+テキストオブジェクト（ciw di" ya( dap）',
        'Vimの編集は「オペレータ(d 削除 / c 変更 / y ヤンク) + モーション/テキストオブジェクト」です。i は内側(inner)、a は周囲も含む(around)。ciw は単語を変更、di" は引用符の中身を削除、ya( は括弧ごとヤンク、dap は空行付きの段落を削除します。edit.txt のコピー out.txt に requirements.txt の編集をしてください。',
        ['out.txt が期待通り', 'edit.txt は原本のまま'], s2, c2, SOL2,
        ["cp edit.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal 1Gwciw<<new>>' -c 'normal 2Gf\"da\"' -c 'normal 3Gf(ya($p' -c 'normal 5Gdap' -c 'wq'",
         "cp edit.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal 1Gwciw<<new>>' -c 'normal 2Gf\"di\"' -c 'normal 3Gf(yi($p' -c 'normal 5Gdd' -c 'wq'"],
        'ciw は単語全体を消して挿入、di" と da" の差は引用符を残すか消すか、ya( と yi( の差は括弧を含めるか。dap は段落と直後の空行まで消します。-c normal では挿入した文字列で挿入モードが自動終了します。',
        'i と a の違い（中身だけか、囲みごとか）に注意します。', 'cp してから vim -Nu NONE -Es out.txt -c \'normal ...\' を行ごとに実行します。')


# ---------------------------------------------------------------- 3 repeat / undo
def s3(ctx):
    w = rw(5)
    ctx.data.update(w=w)
    put(ctx, 'todo.txt', ''.join(f'TODO {x}\n' for x in w))
    ctx.write('requirements.txt', 'todo.txt のコピー out.txt で、1行目の TODO を ciw で DONE にし、j. を4回繰り返して全行 DONE にしたあと、u を2回で5・4行目を戻し、Ctrl-r で4行目だけ やり直す。結果は1〜4行目が DONE、5行目が TODO。\n')


def c3(ctx):
    need_ro(ctx)
    w = ctx.data['w']
    same(ctx, 'out.txt', [f'DONE {x}' for x in w[:4]] + [f'TODO {w[4]}'])


SOL3 = """cp todo.txt out.txt
cat > undo.vim <<'EOF'
normal gg0ciwDONE
let &ul = &ul
normal j.
let &ul = &ul
normal j.
let &ul = &ul
normal j.
let &ul = &ul
normal j.
let &ul = &ul
normal u
normal u
exe "normal \\<C-r>"
wq
EOF
vim -Nu NONE -Es out.txt -S undo.vim"""
mission(3, '. リピートと u / Ctrl-r（undo と redo）',
        '. は直前の変更を繰り返し、u は元に戻し、Ctrl-r は戻したものをやり直します。ciwDONE の後に j. と打てば次の行へ同じ変更を適用できます。todo.txt のコピー out.txt に requirements.txt の手順を適用してください。手順は undo.vim に書き、Ctrl-r は exe "normal \\<C-r>" と書きます。非対話では変更が1つの undo 単位に結合されるため、各変更の後に let &ul = &ul で区切ります。',
        ['out.txt の1〜4行目が DONE、5行目が TODO', 'todo.txt は原本のまま'], s3, c3, SOL3,
        ["cp todo.txt out.txt\ncat > undo.vim <<'EOF'\nnormal gg0ciwDONE\nlet &ul = &ul\nnormal j.\nlet &ul = &ul\nnormal j.\nlet &ul = &ul\nnormal j.\nlet &ul = &ul\nnormal j.\nlet &ul = &ul\nnormal u\nnormal u\nwq\nEOF\nvim -Nu NONE -Es out.txt -S undo.vim",
         "cp todo.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg0ciwDONE' -c 'normal j.' -c 'normal j.' -c 'normal j.' -c 'normal j.' -c 'wq'"],
        'u は変更単位で履歴を戻します（非対話の -Es では全変更が1つの塊になるので、let &ul = &ul で undo の区切りを入れます）。u を2回で2変更ぶん戻り、Ctrl-r(redo) で1変更ぶんだけ進めるので4行目が DONE に戻ります。. は最後の変更だけを繰り返すため、同じ操作を複数箇所へ適用するときに強力です。',
        'u を2回、Ctrl-r を1回で差し引き1変更ぶん戻っています。', '-c exe "normal \\<C-r>" で Ctrl-r を送ります。')


# ---------------------------------------------------------------- 4 registers
def s4(ctx):
    a, junk, b = rw(3)
    ctx.data.update(a=a, junk=junk, b=b)
    put(ctx, 'reg.txt', f'{a}\n{junk}\n{b}\n')
    ctx.write('requirements.txt', f'reg.txt のコピー out.txt で: 1行目を "ayy でレジスタaへ、最終行を yy でヤンク(\\"0 に入る)、2行目({junk})を ブラックホール "_dd で捨て、最終行へ "ap でaを貼り、先頭へ "0P でヤンクした行を貼る。結果は {b},{a},{b},{a} の4行。\n')


def c4(ctx):
    need_ro(ctx)
    d = ctx.data
    same(ctx, 'out.txt', [d['b'], d['a'], d['b'], d['a']], '捨てた行がレジスタに混ざっていないか確認します。')


SOL4 = """cp reg.txt out.txt
vim -Nu NONE -Es out.txt -c 'normal gg"ayy' -c 'normal G' -c 'normal yy' -c 'normal 2G"_dd' -c 'normal G"ap' -c 'normal gg"0P' -c 'wq'"""
mission(4, 'レジスタ（"ay "ap "0 "+ ブラックホール）',
        'Vimのコピー先は名前付きレジスタです。"ayy は a に保存、"ap は a から貼り付け、何も指定しないヤンクは "0 にも入り、削除は無名レジスタを上書きします。"_ はブラックホール（どこにも保存しない削除）、"+ はシステムクリップボードです（"+y でコピー、"+p で貼り付け。クリップボード付きのVimが必要で、この課題では実機に触れないので使いません）。requirements.txt の手順で out.txt を作ってください。',
        ['out.txt が期待通りの4行', 'reg.txt は原本のまま'], s4, c4, SOL4,
        ["cp reg.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg\"ayy' -c 'normal G' -c 'normal yy' -c 'normal 2Gdd' -c 'normal Gp' -c 'normal ggP' -c 'wq'",
         "cp reg.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg\"ayy' -c 'normal 2G\"_dd' -c 'normal G\"ap' -c 'wq'"],
        'dd は削除した行を無名レジスタに入れるため、直後の p は消したものを貼ります。ブラックホール "_dd なら無名レジスタを汚さず、ヤンク専用の "0 もそのまま残ります。大切な内容をヤンクした後に不要行を消すときは "_d か "0p を使います。":reg で中身を一覧できます。',
        '消した行が無名レジスタに入るのが落とし穴です。', '"a と "0 と "_ をそれぞれ使い分けます。')


# ---------------------------------------------------------------- 5 macro
def s5(ctx):
    n = R.randint(6, 14)
    ctx.data.update(n=n, n1=n - 1)
    put(ctx, 'items.txt', ''.join(f'{w}{i}\n' for i, w in enumerate(R.sample(WORDS, n))))
    ctx.write('requirements.txt', f'items.txt（{n}行）の各行を <li>行</li> に囲んだ out.txt を作る。マクロ qa…q で「I<li>Esc A</li>Esc j」を録り、@a で1回、{n - 1}@@ で残りを実行する。\n')


def c5(ctx):
    need_ro(ctx)
    src = ctx.need_file('items.txt').splitlines()
    same(ctx, 'out.txt', [f'<li>{x}</li>' for x in src])


SOL5 = """cp items.txt out.txt
vim -Nu NONE -Es out.txt -c 'let @a="I<li>\\<Esc>A</li>\\<Esc>j"' -c 'normal gg' -c 'normal @a' -c 'normal <<n1>>@@' -c 'wq'"""
mission(5, 'マクロ（qa…q と @a と 10@@）',
        'マクロはキー操作の録画です。対話なら qa で録画開始、操作して q で停止、@a で再生、@@ で直前のマクロを再実行、10@@ で10回再実行できます。マクロの実体はレジスタ a の文字列なので、let @a="…" でスクリプトからも作れます。items.txt の全行を <li>…</li> に囲む out.txt を作ってください。',
        ['out.txt が全行 <li>…</li>', 'items.txt は原本のまま'], s5, c5, SOL5,
        ["cp items.txt out.txt\nvim -Nu NONE -Es out.txt -c 'let @a=\"I<li>\\<Esc>A</li>\\<Esc>j\"' -c 'normal gg' -c 'normal @a' -c 'wq'",
         "cp items.txt out.txt\nvim -Nu NONE -Es out.txt -c 'normal gg' -c 'normal I<li>' -c 'normal A</li>' -c 'wq'"],
        'マクロの最後を j にして次の行へ移るのが定石です。最後の行で j が失敗するとマクロは自動的に止まるため、回数を多めにしても安全です。N@@ のかわりに :%normal @a や :g/^/normal @a でも全行へ適用できます。',
        '1回ぶんの操作を、行末で次の行へ進む形にします。', 'let @a="..." と \\<Esc> でレジスタaにキー列を入れ、normal @a と normal N@@ で実行します。')


# ---------------------------------------------------------------- 6 visual
def s6(ctx):
    rows = [f'{a} {R.randint(10, 99)}' for a in rw(5)]
    ctx.data.update(rows=rows)
    put(ctx, 'table.txt', '# header one\n# header two\n' + '\n'.join(rows) + '\n')
    ctx.write('requirements.txt', 'table.txt のコピー out.txt で: V j d で先頭2行のヘッダを削除、0 v e U で先頭行の1語目を大文字化、Ctrl-v ビジュアルブロックで全行の行頭へ I で "| "、行末へ $ A で " |" を挿入する。\n')


def c6(ctx):
    need_ro(ctx)
    rows = list(ctx.data['rows'])
    first = rows[0].split(' ', 1)
    rows[0] = first[0].upper() + ' ' + first[1]
    same(ctx, 'out.txt', [f'| {r} |' for r in rows])


SOL6 = """cp table.txt out.txt
cat > block.vim <<'EOF'
normal ggVjd
normal gg0veU
exe "normal gg\\<C-v>GI| \\<Esc>"
exe "normal gg\\<C-v>G$A |\\<Esc>"
wq
EOF
vim -Nu NONE -Es out.txt -S block.vim"""
mission(6, 'ビジュアルモード（v V Ctrl-v と ブロックの I / A）',
        'v は文字単位、V は行単位、Ctrl-v は矩形（ビジュアルブロック）の選択です。ブロックを選んで I で全行の同じ桁へ挿入、$ A で全行の行末へ追記できます（Esc で確定）。table.txt のコピー out.txt に requirements.txt の編集を行い、手順を block.vim に書いて -S で実行してください。',
        ['out.txt が期待通り', 'table.txt は原本のまま'], s6, c6, SOL6,
        ["cp table.txt out.txt\ncat > block.vim <<'EOF'\nnormal ggVjd\nexe \"normal gg\\<C-v>GI| \\<Esc>\"\nwq\nEOF\nvim -Nu NONE -Es out.txt -S block.vim",
         "cp table.txt out.txt\ncat > block.vim <<'EOF'\nnormal gg0veU\nexe \"normal gg\\<C-v>GI| \\<Esc>\"\nexe \"normal gg\\<C-v>G$A |\\<Esc>\"\nwq\nEOF\nvim -Nu NONE -Es out.txt -S block.vim"],
        'ブロック選択後の I は選択した左端の桁へ全行同時に挿入、A は右端（$ を併用すると各行の行末）へ追記します。スクリプト内では Ctrl-v を "\\<C-v>" と書きます。v/V/Ctrl-v を使い分けると、列編集もマウスなしで行えます。',
        '先頭の2行削除、1語目の大文字化、列編集の順に手順を作ります。', 'Vim scriptファイルに exe "normal ..." を並べ、vim -Es -S で実行します。')


# ---------------------------------------------------------------- 7 search replace
def s7(ctx):
    rows = []
    for _ in range(7):
        rows.append((R.choice(['ERROR', 'WARN', 'INFO']), R.randint(2020, 2026), R.randint(1, 12), R.randint(1, 28),
                     R.randint(100, 999), R.choice(WORDS)))
    ctx.data.update(rows=rows)
    put(ctx, 'log.txt', ''.join(f'{l} {y}-{m:02d}-{d:02d} code={c} {w}\n' for l, y, m, d, c, w in rows))
    ctx.write('requirements.txt', 'log.txt のコピー out.txt で、日付 YYYY-MM-DD を DD/MM/YYYY に \\v（very magic）の括弧キャプチャで置換し、code=数字 の数字部分を [&] で囲む（& はマッチ全体）。\n')


def c7(ctx):
    need_ro(ctx)
    same(ctx, 'out.txt', [f'{l} {d:02d}/{m:02d}/{y} code=[{c}] {w}' for l, y, m, d, c, w in ctx.data['rows']])


SOL7 = """cp log.txt out.txt
vim -Nu NONE -Es out.txt -c '%s#\\v(\\d{4})-(\\d{2})-(\\d{2})#\\3/\\2/\\1#g' -c '%s#\\vcode\\=\\zs\\d+#[&]#' -c 'wq'"""
mission(7, '検索と置換（:%s///gc・\\v very magic・&）',
        ':%s/検索/置換/g は全行置換です。末尾に c を付けた :%s/old/new/gc は1件ごとに y/n/a/q/l で確認します（対話専用なので、この課題では g で一括します）。\\v（very magic）を付けると ( ) { } + = などが正規表現の記号として素直に書け、置換側では \\1 \\2 がキャプチャ、& がマッチ全体です。区切りには / 以外（#）も使えます。log.txt のコピー out.txt を要件通りに整形してください。',
        ['out.txt の日付が DD/MM/YYYY、code が [数字]', 'log.txt は原本のまま'], s7, c7, SOL7,
        ["cp log.txt out.txt\nvim -Nu NONE -Es out.txt -c '%s#\\v(\\d{4})-(\\d{2})-(\\d{2})#\\3/\\2/\\1#g' -c 'wq'",
         "cp log.txt out.txt\nvim -Nu NONE -Es out.txt -c '%s#\\v(\\d{4})-(\\d{2})-(\\d{2})#\\1/\\2/\\3#g' -c '%s#\\vcode\\=\\zs\\d+#[&]#' -c 'wq'"],
        '\\v では = が「0回か1回」の量指定子になるため code\\= とエスケープします。\\zs でマッチの開始位置を決めると、前の文字列を置換に含めずに済みます。置換先の & は元のマッチ全体、\\1 \\2 \\3 は括弧の順序です。確認しながら直したいときは同じ式に gc を付けて対話で実行します。',
        '日付は括弧3つで取り出して順序を入れ替えます。', ':%s#パターン#置換#g の区切りを # にすると / のエスケープが不要です。')


# ---------------------------------------------------------------- 8 :g :v
def s8(ctx):
    lines = []
    for i in range(20):
        lines.append(f'{R.choice(["INFO", "DEBUG", "ERROR", "WARN"])} {R.choice(WORDS)}{i}')
    lines[0] = 'ERROR boot'
    lines[1] = 'DEBUG trace'
    ctx.data.update(lines=lines)
    put(ctx, 'app.log', '\n'.join(lines) + '\n')
    ctx.write('requirements.txt', 'app.log を壊さず、:g/DEBUG/d で DEBUG 行を除いたものを clean.log、:v/ERROR/d で ERROR 行だけ抜き出したものを errors.log に書く（:w! 別名 を使う）。\n')


def c8(ctx):
    need_ro(ctx)
    ls = ctx.data['lines']
    clean = [x for x in ls if 'DEBUG' not in x]
    same(ctx, 'clean.log', clean)
    same(ctx, 'errors.log', [x for x in clean if 'ERROR' in x])


SOL8 = """vim -Nu NONE -Es app.log -c 'g/DEBUG/d' -c 'w! clean.log' -c 'v/ERROR/d' -c 'w! errors.log' -c 'q!'"""
mission(8, '行の抽出と削除（:g と :v）',
        ':g/パターン/コマンド はパターンに一致する行へコマンドを実行し、:v/パターン/コマンド（:g!）は一致しない行へ実行します。:g/DEBUG/d で一致行を削除、:v/ERROR/d で ERROR 以外を全部削除（= ERROR行だけ抽出）。:w! 別名 で編集中の内容を別ファイルへ保存でき、最後に q! で捨てれば原本は無傷です。',
        ['clean.log が DEBUG 無し', 'errors.log が ERROR 行のみ', 'app.log は原本のまま'], s8, c8, SOL8,
        ["vim -Nu NONE -Es app.log -c 'g/DEBUG/d' -c 'w! clean.log' -c 'g/ERROR/d' -c 'w! errors.log' -c 'q!'",
         "grep -v DEBUG app.log > clean.log\ngrep -v ERROR app.log > errors.log"],
        'ファイルへ w! で書き出した直後でもバッファは編集中のままなので、続けて別の絞り込みができます。:g/pat/normal ... や :g/pat/m0（行を先頭へ移動）のように、行単位の操作と組み合わせると強力です。',
        '消す条件が「一致」か「不一致」かで :g と :v を選びます。', ':g と :v を順に使い、途中で :w! します。')


# ---------------------------------------------------------------- 9 :normal :sort
def s9(ctx):
    nums = [R.randint(2, 9), R.randint(100, 149)] + R.sample(range(10, 99), 4)
    rows = [f'{n} {w}' for n, w in zip(nums, rw(6))]
    rows += R.sample(rows, 3)
    R.shuffle(rows)
    ctx.data.update(rows=rows)
    put(ctx, 'items.txt', '\n'.join(rows) + '\n')
    ctx.write('requirements.txt', 'items.txt のコピー out.txt を :sort n u（数値で並べ重複削除）し、:%normal A, で全行の末尾に , を付ける。\n')


def c9(ctx):
    need_ro(ctx)
    rows = sorted(set(ctx.data['rows']), key=lambda r: int(r.split()[0]))
    same(ctx, 'out.txt', [r + ',' for r in rows], '文字列順ではなく数値順です。')


SOL9 = """cp items.txt out.txt
vim -Nu NONE -Es out.txt -c 'sort n u' -c '%normal A,' -c 'wq'"""
mission(9, ':normal と :sort で一括整形',
        ':sort は行を並べ替え、n で数値順、u で重複削除、! で逆順になります。:normal は Ex からノーマルモードのキーを実行し、:%normal A, のように範囲（%）と組み合わせると全行へ同じ操作をします。items.txt のコピー out.txt を数値順・重複なし・各行末カンマ付きにしてください。',
        ['out.txt が数値順・重複なし・末尾カンマ', 'items.txt は原本のまま'], s9, c9, SOL9,
        ["cp items.txt out.txt\nvim -Nu NONE -Es out.txt -c 'sort u' -c '%normal A,' -c 'wq'",
         "cp items.txt out.txt\nvim -Nu NONE -Es out.txt -c 'sort n' -c '%normal A,' -c 'wq'"],
        'sort のデフォルトは文字列順で、10 が 9 より前に来ます。n を付けると行頭の数値で比較します。:%normal は行ごとにカーソルを置いて実行するため、マクロ不要の簡易一括編集に向きます。',
        '文字列順と数値順の違いに注意します。', ':sort n u の後に :%normal A, を実行します。')


# ---------------------------------------------------------------- 10 :r ! / :w !
def s10(ctx):
    ws = rw(5)
    ws += R.sample(ws, 2)
    R.shuffle(ws)
    ctx.data.update(ws=ws, tg=tag(2))
    put(ctx, 'fruits.txt', '\n'.join(ws) + '\n')
    ctx.write('report.txt', f'# report {ctx.data["tg"]}\n')
    ctx.write('requirements.txt', 'report.txt を編集し、末尾へ :$r !sort -u fruits.txt の出力を読み込み、続けて :w !sha256sum > sum.txt でバッファ全体のハッシュを sum.txt に書く。最後に report.txt を保存。\n')


def c10(ctx):
    need_ro(ctx)
    d = ctx.data
    want = [f'# report {d["tg"]}'] + sorted(set(d['ws']))
    same(ctx, 'report.txt', want)
    got = ctx.need_file('sum.txt').split()
    ctx.require(got and got[0] == sha(ctx.need_file('report.txt')), 'sum.txt は :r の後の report.txt 全体の sha256 のはずです。')


SOL10 = """vim -Nu NONE -Es report.txt -c '$r !sort -u fruits.txt' -c 'w !sha256sum > sum.txt' -c 'wq'"""
mission(10, '外部コマンドとの連携（:r !cmd と :w !cmd）',
        ':r !コマンド はコマンドの標準出力をカーソルの下へ読み込み、:w !コマンド は編集中のバッファをコマンドの標準入力へ渡します（ファイルは書き換わりません）。つまり Vim を中心に sort や sha256sum といったフィルタをつなげます。要件の通りに report.txt を仕上げてください。',
        ['report.txt に重複なしの一覧が追記', 'sum.txt に report.txt 全体の sha256'], s10, c10, SOL10,
        ["vim -Nu NONE -Es report.txt -c '$r !sort fruits.txt' -c 'w !sha256sum > sum.txt' -c 'wq'",
         "vim -Nu NONE -Es report.txt -c 'w !sha256sum > sum.txt' -c '$r !sort -u fruits.txt' -c 'wq'"],
        ':r !cmd と :w !cmd の ! の後はシェルに渡されるため、リダイレクトも使えます。:%!sort のようにバッファ全体をフィルタで置き換える形（範囲!cmd）もよく使います。順序が重要で、:w ! はその時点の内容を渡します。',
        '読み込み(:r !)の後でハッシュを取る順序です。', ':$r !… で末尾へ追加し、:w !sha256sum > sum.txt の後に :wq します。')


# ---------------------------------------------------------------- 11 windows/tabs
def s11(ctx):
    t = 'a1-' + tag(2)
    ctx.data.update(t=t)
    ctx.write('a.txt', t + '\na2\n')
    for f in 'bcd':
        ctx.write(f + '.txt', f'{f}1\n{f}2\n')
    ctx.data['ro'] = {'a.txt': sha(t + '\na2\n')}
    ctx.write('requirements.txt', 'a.txt の1行目をヤンクし、:vsplit b.txt、:tabnew c.txt、:split d.txt の各ウィンドウで1行目の下へ貼り付けて :write する。a.txt は変更しない。\n')


def c11(ctx):
    need_ro(ctx)
    t = ctx.data['t']
    for f in 'bcd':
        same(ctx, f + '.txt', [f + '1', t, f + '2'])


SOL11 = """cat > win.vim <<'EOF'
normal ggyy
vsplit b.txt
normal ggp
write
tabnew c.txt
normal ggp
write
split d.txt
normal ggp
write
qa!
EOF
vim -Nu NONE -Es a.txt -S win.vim"""
mission(11, '複数ウィンドウとタブ（:sp :vs :tabnew）',
        ':split(:sp) は上下、:vsplit(:vs) は左右にウィンドウを分け、:tabnew は新しいタブページを作ります。Ctrl-w w / Ctrl-w h j k l でウィンドウを移動、gt / gT でタブを切り替えます。レジスタはウィンドウをまたいで共有されるので、a.txt でヤンクした行を別ファイルへ貼り付けられます。',
        ['b.txt c.txt d.txt の1行目の下に a.txt の1行目', 'a.txt は変更なし'], s11, c11, SOL11,
        ["vim -Nu NONE -Es b.txt -c 'normal ggp' -c 'wq'",
         "vim -Nu NONE -Es a.txt -c 'normal ggyy' -c 'vsplit b.txt' -c 'normal ggp' -c 'write' -c 'qa!'"],
        '-Es でもウィンドウ・タブは仮想的に作られ、:vsplit したウィンドウが現在のウィンドウになります。複数ファイル編集では :wa で全て保存、:qa! で破棄終了できます。',
        '行をヤンクした後、開いた各ウィンドウで貼り付けと保存をします。', ':vsplit / :tabnew / :split でファイルを開き、そのつど normal ggp と write をします。')


# ---------------------------------------------------------------- 12 buffers + marks
def s12(ctx):
    blk = rw(3)
    ctx.data.update(blk=blk)
    ctx.write('a.txt', 'a1\n')
    ctx.write('b.txt', 'top\nBEGIN\n' + '\n'.join(blk) + '\nEND\nbottom\n')
    ctx.write('c.txt', 'c1\n')
    ctx.data['ro'] = {'a.txt': sha('a1\n'), 'c.txt': sha('c1\n')}
    ctx.write('requirements.txt', 'vim a.txt b.txt c.txt を開き、:ls の出力を redir で buffers.txt に保存。:b 2 で2番目のバッファへ移り、/^BEGIN/ で ma、/^END/ で mb とマークを付け、:\'a,\'bd で BEGIN〜END を削除して保存する。\n')


def c12(ctx):
    need_ro(ctx)
    same(ctx, 'b.txt', ['top', 'bottom'])
    t = ctx.need_file('buffers.txt')
    for f in ('a.txt', 'b.txt', 'c.txt'):
        ctx.require(f in t, 'buffers.txt に :ls の一覧（' + f + '）がありません。')


SOL12 = """cat > mark.vim <<'EOF'
redir! > buffers.txt
silent ls
redir END
buffer 2
normal gg
/^BEGIN/
normal ma
/^END/
normal mb
'a,'bd
write
qa!
EOF
vim -Nu NONE -Es a.txt b.txt c.txt -S mark.vim"""
mission(12, 'バッファ（:ls :b）とマーク（ma \'a）',
        'Vimは開いたファイルをバッファとして保持し、:ls で一覧、:b 番号（:b 名前の一部）で切り替えます。マークは ma で位置に a と名前を付け、\'a でその行へ、`a でその桁へ戻れ、:\'a,\'b は「マークaからbまでの行範囲」としてコマンドに渡せます。:ls の出力は :redir で保存できます。',
        ['buffers.txt に :ls の出力', 'b.txt から BEGIN〜END が消え、他は変更なし'], s12, c12, SOL12,
        ["vim -Nu NONE -Es b.txt -c 'g/BEGIN/,/END/d' -c 'wq'",
         "vim -Nu NONE -Es a.txt b.txt c.txt -c 'redir! > buffers.txt' -c 'silent ls' -c 'redir END' -c 'buffer 2' -c 'normal gg' -c '/^BEGIN/' -c 'normal ma' -c '/^END/' -c 'normal mb' -c \"'a,'bd\" -c 'qa!'"],
        '複数ファイルを引数に渡すとそれぞれがバッファになり、:b2 で2つ目に移れます。小文字マーク(a-z)はバッファごと、大文字マーク(A-Z)はファイルをまたいで有効です。変更を :w しないまま :qa! するとバッファは捨てられます。',
        '3つのバッファのうち、編集する対象は2番です。', ':redir! > ファイル と :silent ls で :ls を保存します。')


# ---------------------------------------------------------------- 13 vimrc
def s13(ctx):
    n = R.choice([2, 4, 8])
    ctx.data.update(n=n)
    ctx.write('requirements.txt', f'my.vimrc（.vimrc の練習用。本物の ~/.vimrc は触らない）を書き、行番号を表示、タブをスペースに展開、shiftwidth と tabstop を {n}、検索は ignorecase かつ smartcase、hlsearch を有効、折り返しなし(nowrap)に設定する。vim -u my.vimrc で読み込んで確認される。\n')


def c13(ctx):
    n = ctx.data['n']
    ctx.need_file('my.vimrc')
    probe = ctx.p('probe.txt')
    if probe.exists():
        probe.unlink()
    expr = 'call writefile([join([&number,&expandtab,&shiftwidth,&tabstop,&ignorecase,&smartcase,&hlsearch,&wrap], ",")], "probe.txt")'
    try:
        subprocess.run(['vim', '-Nu', 'my.vimrc', '-Es', '-c', expr, '-c', 'qa!'], cwd=str(ctx.work), timeout=15,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        ctx.fail('vim -u my.vimrc で読み込めませんでした。')
    ctx.require(probe.exists(), 'my.vimrc の読み込み中に vim が止まりました。構文を確認してください。')
    got = probe.read_text().strip()
    probe.unlink()
    ctx.require(got == f'1,1,{n},{n},1,1,1,0', f'設定値が違います（number,expandtab,sw,ts,ignorecase,smartcase,hlsearch,wrap = {got}）。')


SOL13 = """cat > my.vimrc <<'EOF'
set number
set expandtab
set shiftwidth=<<n>>
set tabstop=<<n>>
set ignorecase smartcase
set hlsearch
set nowrap
EOF"""
mission(13, '.vimrc に設定を書く（number expandtab shiftwidth ignorecase smartcase）',
        'Vimの設定は ~/.vimrc に :set コマンドを1行ずつ書きます（set number、set expandtab、set shiftwidth=4 など）。smartcase は ignorecase と併用し、大文字を含む検索だけ大小を区別します。ここでは練習用 my.vimrc を作り、vim -u my.vimrc で読み込ませて採点します。',
        ['my.vimrc を読み込んだ設定値が要件通り'], s13, c13, SOL13,
        ["cat > my.vimrc <<'EOF'\nset number\nset expandtab\nset shiftwidth=<<n>>\nset ignorecase\nset hlsearch\nset nowrap\nEOF",
         "cat > my.vimrc <<'EOF'\nset number expandtab\nset sw=3 ts=3\nset ignorecase smartcase hlsearch nowrap\nEOF"],
        'set 名前 で有効、set no名前 で無効、set 名前=値 で値設定です。smartcase 単独では効かず ignorecase が前提。本番では ~/.vimrc（Neovimは init.vim）に同じ内容を書き、:source % で再読込できます。',
        'タブ幅は shiftwidth（インデント幅）と tabstop（見た目の幅）の2つです。', 'cat > my.vimrc <<\'EOF\' で set 行を並べます。')


# ---------------------------------------------------------------- 14 ctags
def s14(ctx):
    names = rw(6)
    files = ['src/' + x + '.py' for x in rw(3)]
    defs = {}
    body = {f: [] for f in files}
    for i, nm in enumerate(names):
        f = files[i % 3]
        body[f].append(f'def {nm}(x):\n    return x\n')
        defs[nm] = f
    tags = ['!_TAG_FILE_FORMAT\t2\t/extended format/', '!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted, 2=foldcase/',
            '!_TAG_PROGRAM_NAME\tUniversal Ctags']
    rows = {}
    for f in files:
        txt = '"""module"""\n\n' + '\n'.join(body[f])
        ctx.write(f, txt)
        ctx.data.setdefault('ro', {})[f] = sha(txt)
        for ln, line in enumerate(txt.splitlines(), 1):
            m = re.match(r'def (\w+)\(', line)
            if m:
                rows[m.group(1)] = (f, ln, line)
                tags.append(f'{m.group(1)}\t{f}\t/^def {m.group(1)}(/;"\tf')
    head, rest = tags[:3], sorted(tags[3:])
    ctx.write('tags', '\n'.join(head + rest) + '\n')
    tg = R.choice(names)
    ctx.data.update(tg=tg, want=f'{rows[tg][0]}:{rows[tg][1]}')
    ctx.write('requirements.txt', f'ctags が無い環境のため、ctags -R の出力と同形式の tags ファイルを用意した。vim -t {tg} のようにタグジャンプし、ジャンプ先の「ファイル:行番号」を where.txt に書く。\n')


def c14(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('where.txt').strip() == ctx.data['want'], f'where.txt は「ファイル:行」の形で、{ctx.data["tg"]} の定義位置を書きます。')


SOL14 = """vim -Nu NONE -Es -t <<tg>> -c 'call writefile([expand("%").":".line(".")], "where.txt")' -c 'qa!'"""
mission(14, 'ctags と tags ジャンプ（:tag と Ctrl-]）',
        'ctags -R . はソースの関数名と定義位置を tags ファイルに索引化し、Vimは :tag 名前、vim -t 名前、カーソル上の語で Ctrl-]（戻りは Ctrl-t）で定義へ飛べます。この環境には ctags が無いかもしれないので、同じ形式の tags ファイルを用意しました（名前・ファイル・検索パターン・種別がタブ区切り）。',
        ['where.txt に定義位置が「ファイル:行」で書かれる', 'ソースと tags は原本のまま'], s14, c14, SOL14,
        ["grep -rn 'def <<tg>>' src | head -1 | cut -d: -f1 > where.txt",
         "echo 'src/none.py:1' > where.txt"],
        'tags ファイルは「タグ名 ファイル 検索パターン」をタブで区切った行です。Vimは検索パターンで位置を探すので、少し行がずれても追従します。タグが複数ある時は :tselect、戻る時は Ctrl-t を使います。再生成は ctags -R . です。',
        'vim -t タグ名 で tags ファイルを使って開けます。', "expand('%') と line('.') を writefile に渡します。")


# ---------------------------------------------------------------- 15 vimdiff
def s15(ctx):
    a = [f'line{i}={tag(1)}' for i in range(1, 10)]
    b = list(a)
    for i in (1, 4, 7):
        while b[i] == a[i]:
            b[i] = f'line{i + 1}={tag(1)}'
    ctx.data.update(want=[b[1] if i == 1 else b[7] if i == 7 else a[i] for i in range(9)])
    put(ctx, 'a.conf', '\n'.join(a) + '\n')
    put(ctx, 'b.conf', '\n'.join(b) + '\n')
    ctx.write('requirements.txt', 'vimdiff（vim -d）で a.conf と b.conf を比べ、差分が3か所ある。1か所目と3か所目だけ b.conf から取り込み（]c で次の差分へ、:diffget）、2か所目は a.conf のまま。結果を merged.conf に :w! で保存する。\n')


def c15(ctx):
    need_ro(ctx)
    same(ctx, 'merged.conf', ctx.data['want'])


SOL15 = """vim -Nu NONE -Es -d a.conf b.conf -c 'normal gg' -c 'normal ]c' -c 'diffget' -c 'normal ]c' -c 'normal ]c' -c 'diffget' -c 'w! merged.conf' -c 'qa!'"""
mission(15, 'diff モード（vimdiff と ]c / :diffget）',
        'vimdiff a b（= vim -d a b）は2ファイルを並べて差分を色付けします。]c / [c で次/前の差分へ、:diffget（do）で相手側の内容を取り込み、:diffput（dp）で相手へ送ります。差分の1か所目と3か所目だけ b.conf を採用し、2か所目は a.conf のままにしたマージ結果 merged.conf を作ってください。',
        ['merged.conf が1・3か所目だけ b.conf', '原本 a.conf b.conf は変更なし'], s15, c15, SOL15,
        ["cp b.conf merged.conf",
         "vim -Nu NONE -Es -d a.conf b.conf -c 'normal gg' -c 'normal ]c' -c 'diffget' -c 'w! merged.conf' -c 'qa!'"],
        'diffget は「他方のウィンドウの差分箇所」を現在のバッファに取り込みます。取り込んだ差分は解消されるため、次の ]c で2か所目に移ります。マージ作業はこの繰り返しです。',
        '差分を取り込んだ後の次の ]c がどこへ進むかを考えます。', 'vim -Es -d で2ファイルを開き、]c と diffget を組み合わせます。')


# ---------------------------------------------------------------- 16 swap recovery
def s16(ctx):
    t = 'unsaved-' + tag(2)
    ctx.data.update(t=t)
    ctx.write('notes.txt', 'saved line 1\nsaved line 2\n')
    for p in ctx.work.glob('.notes.txt.sw*'):
        p.unlink()
    expr = 'call setline(3, "%s")' % t
    pr = subprocess.Popen(['vim', '-Nu', 'NONE', '-Es', 'notes.txt', '-c', expr, '-c', 'preserve',
                           '-c', 'call system("kill -9 " . getpid())'], cwd=str(ctx.work),
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pr.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pr.kill()
    ctx.data['swap'] = any(ctx.work.glob('.notes.txt.sw*'))
    ctx.write('requirements.txt', 'Vimが強制終了し、作業フォルダのメモには保存前の編集がありません。復旧候補を調べ、残った編集記録から vim -r で復旧した内容を recovered.txt に保存する（元のメモ自体は上書きしない）。\n')


def c16(ctx):
    ctx.require(ctx.data.get('swap'), 'この環境ではswapを作れませんでした（採点不能）。')
    ctx.require(ctx.need_file('notes.txt') == 'saved line 1\nsaved line 2\n', 'notes.txt は上書きしません。')
    same(ctx, 'recovered.txt', ['saved line 1', 'saved line 2', ctx.data['t']])


SOL16 = """ls -a
vim -Nu NONE -Es -r notes.txt -c 'w! recovered.txt' -c 'qa!'"""
mission(16, 'swap ファイルからの復旧（vim -r）',
        'Vimは編集中の内容を .ファイル名.swp に定期保存し、異常終了すると残ります。vim -r（引数なし）で復旧可能なファイル一覧、vim -r ファイル名 で復旧できます。復旧後は内容を確認してから保存し、不要になった swap は消します（誰かが同じファイルを開いている場合の警告と区別しましょう）。',
        ['recovered.txt に保存前の行を含む内容', '復旧元のファイルは変更なし'], s16, c16, SOL16,
        ["cp notes.txt recovered.txt",
         "vim -Nu NONE -Es notes.txt -c 'w! recovered.txt' -c 'qa!'"],
        'swap は隠しファイルなので ls -a で確認できます。通常の vim notes.txt で開くと「swapが存在する」警告が出て、R で復旧、D で swap 削除を選べます。復旧後は :w で保存しないと swap が残り続けます。',
        'まず復旧できる編集記録を探し、保存済みの内容と区別しましょう。', 'ls -a で隠しファイルまで確認し、vim -r（引数なし）で復旧候補を調べます。対象を vim -r ファイル名 で復元し、:w! で別名保存します。')


# ---------------------------------------------------------------- 17 big file / view / vimtutor
def s17(ctx):
    tg = tag(2)
    n = 60000
    pos = R.randint(1000, n - 1000)
    rows = []
    errs = 0
    for i in range(n):
        if i % 7 == 0:
            rows.append(f'{i} ERROR disk')
            errs += 1
        else:
            rows.append(f'{i} INFO ok')
    rows[pos] = f'{pos} INFO FIX_{tg}'
    # The marker can replace an ERROR row; count the final fixture, not the pre-edit rows.
    errs = sum(' ERROR ' in row for row in rows)
    text = '\n'.join(rows) + '\n'
    ctx.write('big.log', text)
    ctx.data.update(tg=tg, orig=sha(text), errs=errs)
    ctx.write('config.ini', '[main]\nvalue=1\n', mode=0o644)
    ctx.data['ro'] = {'config.ini': sha('[main]\nvalue=1\n')}
    ctx.write('requirements.txt', 'big.log（6万行）を vim -n（swap無し）で開き、:%s/ERROR//gn で数だけ数えた出力を redir で count.txt に保存、FIX_' + tg + ' を DONE_' + tg +
              ' に置換して保存。view で config.ini を開いて readonly なら mode.txt に readonly と書く。学習用に日本語の vimtutor を起動するコマンドを learn.txt の1行に書く。\n')


def c17(ctx):
    need_ro(ctx)
    d = ctx.data
    t = ctx.need_file('big.log')
    ctx.require(t.count('DONE_' + d['tg']) == 1 and 'FIX_' + d['tg'] not in t and sha(t.replace('DONE_' + d['tg'], 'FIX_' + d['tg'])) == d['orig'],
                'big.log の FIX_ の1か所だけを DONE_ に置換します（他は変更しない）。')
    ctx.require(str(d['errs']) in ctx.need_file('count.txt'), 'count.txt に ERROR の件数がありません（:%s/ERROR//gn の出力）。')
    ctx.require(ctx.need_file('mode.txt').strip() == 'readonly', 'mode.txt は view で開いた結果の readonly です。')
    ctx.require(re.fullmatch(r'vimtutor\s+ja', one_line(ctx, 'learn.txt')) is not None, 'learn.txt は vimtutor ja の1行です。')


SOL17 = """vim -Nu NONE -n -Es big.log -c 'redir! > count.txt' -c '%s/ERROR//gn' -c 'redir END' -c '%s/FIX_<<tg>>/DONE_<<tg>>/' -c 'wq'
view -Nu NONE -Es -n config.ini -c 'call writefile([&readonly ? "readonly" : "writable"], "mode.txt")' -c 'qa!'
echo 'vimtutor ja' > learn.txt"""
mission(17, '大きなファイルの編集と view / vimtutor',
        '大きなログは vim -n（swap無し）で開くと速く、:%s/パターン//gn は置換せず件数だけを数えます。view は vim -R と同じ読み取り専用で、うっかり編集して保存する事故を防ぎます（:w! で上書きは可能）。vimtutor は約30分の対話チュートリアルで、vimtutor ja のように言語を指定できます。要件を満たしてください。',
        ['big.log を1か所だけ置換', 'count.txt に ERROR の件数', 'mode.txt が readonly', 'learn.txt に vimtutor ja'], s17, c17, SOL17,
        ["grep -c ERROR big.log > count.txt\nvim -Nu NONE -Es big.log -c '%s/FIX_<<tg>>/DONE_<<tg>>/' -c 'wq'\nvim -Nu NONE -Es -n config.ini -c 'call writefile([&readonly ? \"readonly\" : \"writable\"], \"mode.txt\")' -c 'qa!'\necho vimtutor > learn.txt",
         "sed -i 's/FIX_<<tg>>/DONE_<<tg>>/g;s/INFO/DONE_<<tg>>/' big.log"],
        '-n は swap を作らないため大きなファイルで速く安全ですが、クラッシュ時の復旧はできません。さらに巨大なら less や split、sed -n "100,200p" で範囲だけ見るのが現実的です。view/vim -R は readonly、vimtutor は初学者の最初の一歩におすすめです。',
        '件数だけ数える :s///gn、読み取り専用の view、日本語の vimtutor。', 'redir で :s///gn の出力を保存し、view -Es で &readonly を確認します。')


# ---------------------------------------------------------------- 18 EDITOR/VISUAL/sudoedit/git
def s18(ctx):
    tw = R.choice([50, 60, 72])
    ed = R.choice(['nano', 'vim'])
    ctx.data.update(tw=tw, ed=ed)
    ctx.write('gitconfig', '[user]\n\tname = Trainee\n')
    ctx.write('requirements.txt', f'editor.sh を作り（source される）、VISUAL=vim、EDITOR={ed}、sudoedit用に SUDO_EDITOR=vim を export する。さらにサンドボックスの gitconfig の [core] に、git commit 用のエディタとして vim -c "set textwidth={tw}" を設定する。\n')


def c18(ctx):
    d = ctx.data
    ctx.need_file('editor.sh')
    try:
        out = subprocess.run(['env', '-i', 'PATH=/usr/bin:/bin', 'bash', '-c',
                              '. ./editor.sh >/dev/null 2>&1; bash -c \'printf "%s|%s|%s" "$VISUAL" "$EDITOR" "$SUDO_EDITOR"\''],
                             cwd=str(ctx.work), capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        ctx.fail('editor.sh を読み込めませんでした。')
    ctx.require(out == f'vim|{d["ed"]}|vim', f'export された値が違います（VISUAL|EDITOR|SUDO_EDITOR = {out}）。export を忘れていませんか。')
    t = ctx.need_file('gitconfig')
    ctx.require('[user]' in t and 'Trainee' in t, 'gitconfig の既存の [user] は残します。')
    if shutil.which('git'):
        r = subprocess.run(['git', 'config', '--file', 'gitconfig', 'core.editor'], cwd=str(ctx.work), capture_output=True, text=True)
        v = r.stdout.strip()
    else:
        m = re.search(r'^\s*editor\s*=\s*(.*)$', t, re.M)
        v = m.group(1).strip() if m else ''
    ctx.require(v.startswith('vim') and f'textwidth={d["tw"]}' in v, 'core.editor に vim と textwidth の設定が必要です。')


SOL18 = """cat > editor.sh <<'EOF'
export VISUAL=vim
export EDITOR=<<ed>>
export SUDO_EDITOR=vim
EOF
git config --file gitconfig core.editor 'vim -c "set textwidth=<<tw>>"'"""
mission(18, 'EDITOR / VISUAL / sudoedit / git commit のエディタ設定',
        'crontab -e や git commit などは環境変数でエディタを決めます。VISUAL（画面型）と EDITOR（行型を含む既定）があり、sudoedit は SUDO_EDITOR、VISUAL、EDITOR の順で参照し、編集用の一時コピーを使って root 権限のファイルを安全に編集します（sudoedit /etc/hosts のように使う）。git は core.editor（または GIT_EDITOR）を最優先します。サンドボックス内の editor.sh と gitconfig を要件通りに設定してください（実際の ~/.gitconfig は触りません）。',
        ['editor.sh の export が要件通り', 'gitconfig の core.editor が vim + textwidth'], s18, c18, SOL18,
        ["cat > editor.sh <<'EOF'\nVISUAL=vim\nEDITOR=<<ed>>\nSUDO_EDITOR=vim\nEOF\ngit config --file gitconfig core.editor 'vim -c \"set textwidth=<<tw>>\"'",
         "cat > editor.sh <<'EOF'\nexport VISUAL=vim\nexport EDITOR=<<ed>>\nexport SUDO_EDITOR=vim\nEOF\ngit config --file gitconfig core.editor vim"],
        '変数は export しないと子プロセス（git や sudo）へ引き継がれません。設定は ~/.bashrc に書いて恒久化します。git config --file を使うと対象ファイルを明示でき、本物の設定を壊さず練習できます。',
        '子プロセスに渡すには export が必要です。', 'git config --file gitconfig core.editor "…" で書き込みます。')


# ---------------------------------------------------------------- 19 nano
def s19(ctx):
    ts = R.choice([2, 4, 8])
    opts = sorted(R.sample(['autoindent', 'linenumbers', 'tabstospaces', 'softwrap', 'smooth', 'casesensitive'], 3))
    off = R.choice([x for x in ['mouse', 'constantshow', 'whitespace'] if x not in opts])
    ln = R.randint(20, 90)
    ctx.data.update(ts=ts, opts=opts, ln=ln, opts_json=json.dumps(opts))
    lines = ['# nano settings', f'set tabsize {ts}'] + [f'set {o}' for o in opts] + [f'# set {off}']
    put(ctx, 'sample.nanorc', '\n'.join(lines) + '\n')
    ctx.write('app.conf', '\n'.join(f'k{i}=v' for i in range(100)) + '\n')
    ctx.write('requirements.txt', f'sample.nanorc を読み、nano.json に tabsize（数値）、enabled（コメントでない set のうち値を取らないフラグ名の昇順配列）、keys（save=ファイル保存 exit=終了 search=検索 cut=行切り取り paste=貼り付け help=ヘルプ の ^ 表記）を書く。cmd.txt には sample.nanorc を指定して app.conf の{ln}行目から nano を開く1行を書く。\n')


def c19(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'nano.json')
    ctx.require(j.get('tabsize') == d['ts'], 'tabsize が違います。')
    ctx.require(j.get('enabled') == d['opts'], 'enabled は、コメントでない set のフラグ名の昇順配列です。')
    k = {a: str(b).upper().replace('CTRL-', '^') for a, b in (j.get('keys') or {}).items()}
    ctx.require(k == {'save': '^O', 'exit': '^X', 'search': '^W', 'cut': '^K', 'paste': '^U', 'help': '^G'}, 'keys のCtrlキー表記が違います（例 ^O）。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'nano' and t[-1] == 'app.conf', 'cmd.txt は nano … app.conf の形です。')
    ctx.require(('--rcfile=sample.nanorc' in t) or ('--rcfile' in t and 'sample.nanorc' in t), '--rcfile で sample.nanorc を指定します。')
    ctx.require(f'+{d["ln"]}' in t, f'+{d["ln"]} で行番号を指定します。')


SOL19 = """cat > nano.json <<'EOF'
{"tabsize": <<ts>>, "enabled": <<opts_json>>, "keys": {"save": "^O", "exit": "^X", "search": "^W", "cut": "^K", "paste": "^U", "help": "^G"}}
EOF
echo 'nano --rcfile=sample.nanorc +<<ln>> app.conf' > cmd.txt"""
mission(19, 'nano のCtrlキーと .nanorc の読解',
        'nano は画面下にコマンドが出る初心者向けエディタです。Ctrl-O で保存(書き出し)、Ctrl-X で終了、Ctrl-W で検索、Ctrl-K で行切り取り、Ctrl-U で貼り付け、Ctrl-G でヘルプ。設定は ~/.nanorc に set tabsize 4、set linenumbers のように書き、# 始まりはコメントです。nano --rcfile=設定 +行番号 ファイル で設定と開始行を指定できます。この環境で nano は使えない場合もあるので、記録された sample.nanorc を読んで答えてください。',
        ['nano.json が設定とキー操作を正しく表す', 'cmd.txt が行番号付きの nano コマンド'], s19, c19, SOL19,
        ["cat > nano.json <<'EOF'\n{\"tabsize\": <<ts>>, \"enabled\": [], \"keys\": {\"save\": \"^S\", \"exit\": \"^Q\", \"search\": \"^F\", \"cut\": \"^X\", \"paste\": \"^V\", \"help\": \"^H\"}}\nEOF\necho 'nano app.conf' > cmd.txt"],
        'nano の下部の ^ は Ctrl、M- は Alt を表します。set tabstospaces でタブをスペース化、set linenumbers で行番号表示。コメント行（# set …）は無効で、読むときに数えないよう注意します。',
        'コメントされた set は有効ではありません。', 'JSON を heredoc で書き、cmd.txt に --rcfile=… +行 を付けます。')


# ---------------------------------------------------------------- 20 emacs
def s20(ctx):
    ring = rw(3)
    k = R.randint(0, 2)
    ctx.data.update(ring=ring, k=k, final=ring[k], old=tag(1), new=tag(1))
    put(ctx, 'killring.txt', 'kill-ring (newest first)\n' + '\n'.join(f'{i}: {x}' for i, x in enumerate(ring)) + '\n')
    ctx.write('config.txt', 'color=' + ctx.data['old'] + '\n')
    ctx.write('requirements.txt', f'この環境にEmacsは無いかもしれない。emacs.json に keys（open=ファイルを開く save=保存 abort=中断 command=M-x switch_buffer=バッファ切替 kill_line=行末までキル yank=貼り付け yank_pop=リング循環）と、killring.txt の状態で C-y のあと M-y を{k}回押したときに貼り付けられる語を final_text に書く。cmd.txt には emacs --batch で config.txt の {ctx.data["old"]} を {ctx.data["new"]} に置換し save-buffer する1行を書く（実行はしない）。\n')


def c20(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'emacs.json')
    want = {'open': 'C-x C-f', 'save': 'C-x C-s', 'abort': 'C-g', 'command': 'M-x', 'switch_buffer': 'C-x b',
            'kill_line': 'C-k', 'yank': 'C-y', 'yank_pop': 'M-y'}
    got = {a: ' '.join(str(b).split()).lower() for a, b in (j.get('keys') or {}).items()}
    ctx.require(got == {a: b.lower() for a, b in want.items()}, 'keys のEmacsキー表記が違います（例 C-x C-s）。')
    ctx.require(j.get('final_text') == d['ring'][d['k']], 'final_text が違います。C-y は最新、M-y で1つ古いものへ置き換わります。')
    line = one_line(ctx, 'cmd.txt')
    t = toks(ctx, line)
    ctx.require(t[0] == 'emacs' and '--batch' in t and 'config.txt' in t, 'emacs --batch config.txt … の形です。')
    ctx.require(any(x in ('--eval', '--execute', '-f', '--funcall', '-l', '--load') for x in t), '--eval で式を渡します。')
    ctx.require(d['old'] in line and d['new'] in line and 'save-buffer' in line, '置換する語と save-buffer が必要です。')
    ctx.require('replace' in line or 'search-forward' in line, 'search-forward と replace-match などで置換します。')


SOL20 = """cat > emacs.json <<'EOF'
{"keys": {"open": "C-x C-f", "save": "C-x C-s", "abort": "C-g", "command": "M-x", "switch_buffer": "C-x b", "kill_line": "C-k", "yank": "C-y", "yank_pop": "M-y"}, "final_text": "<<final>>"}
EOF
cat > cmd.txt <<'EOF'
emacs --batch config.txt --eval '(progn (goto-char (point-min)) (while (search-forward "<<old>>" nil t) (replace-match "<<new>>")) (save-buffer))'
EOF"""
mission(20, 'Emacs の基本キー・キルリングと emacs --batch',
        'Emacs は Ctrl(C-) と Meta(M-, Alt/Esc) の組み合わせで操作します。C-x C-f でファイルを開き、C-x C-s で保存、C-g で現在のコマンドを中断、M-x でコマンド名を実行、C-x b でバッファ切替。C-k で行末までをキルリングへ切り取り、C-y で最新を貼り付け(yank)、直後の M-y で1つ古いものへ置き換えます。emacs --batch ファイル --eval 式 で非対話に編集できます（この環境にemacsが無い場合は記録された状態から診断し、実行はしません）。',
        ['emacs.json のキーと final_text が正しい', 'cmd.txt の emacs --batch コマンドが置換と保存を行う'], s20, c20, SOL20,
        ["cat > emacs.json <<'EOF'\n{\"keys\": {\"open\": \"C-o\", \"save\": \"C-s\", \"abort\": \"C-c\", \"command\": \"C-x\", \"switch_buffer\": \"C-b\", \"kill_line\": \"C-d\", \"yank\": \"C-v\", \"yank_pop\": \"C-y\"}, \"final_text\": \"x\"}\nEOF\necho 'emacs config.txt' > cmd.txt"],
        'C-g は途中のコマンドを取り消す緊急脱出、C-x C-c が Emacs 終了です。キルリングは過去の切り取りの履歴で、C-y 直後に M-y を繰り返すと貼り付けた内容がリングを順に遡って入れ替わります。--batch は画面を開かない非対話モードで、スクリプトやCIで使えます。',
        'キルリングは新しい順です。M-y のたびに1つ古くなります。', 'emacs --batch ファイル --eval \'(progn …)\' の形で書きます。')
