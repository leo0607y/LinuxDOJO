"""Stage 33: 言語環境・ビルド・デバッグ・品質ツール。サンドボックス内の偽データと使える本物のツールだけを使う。"""
import ast
import hashlib
import json
import os
import random
import re
import shlex
import subprocess
import tomllib
from pathlib import Path

from engine.runner import register

S = 33
R = random.SystemRandom()
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・パッケージ・ネットワークは変更せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないツールは採取済みの出力と設定例から診断します。")


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


def rtoml(ctx, name):
    try:
        return tomllib.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' はTOMLとして正しい形式で書きます。')


def one_line(ctx, name):
    ls = [x for x in ctx.need_file(name).splitlines() if x.strip()]
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0].strip()


def tk(line):
    try:
        return shlex.split(line)
    except ValueError:
        return []


def toks(ctx, line):
    t = tk(line)
    ctx.require(bool(t), 'コマンドの引用符が閉じていません。')
    return t


def seq(ctx, name, preds):
    ls = [x.strip() for x in ctx.need_file(name).splitlines() if x.strip() and not x.strip().startswith('#')]
    i = 0
    for fn, msg in preds:
        while i < len(ls) and not fn(ls[i]):
            i += 1
        ctx.require(i < len(ls), name + ': ' + msg + '（行の順序も確認）')
        i += 1
    return ls


def starts(*words):
    return lambda l: tk(l)[:len(words)] == list(words)


def req(ctx, text):
    ctx.write('requirements.txt', text + '\n')


def run(ctx, args, env=None, cwd=None, inp=None):
    e = {'PATH': '/usr/bin:/bin', 'HOME': str(ctx.work), 'LANG': 'C.UTF-8'}
    e.update(env or {})
    try:
        return subprocess.run(args, cwd=str(cwd or ctx.work), env=e, capture_output=True, text=True, timeout=20, input=inp)
    except (OSError, subprocess.SubprocessError):
        ctx.fail('実行を確認できませんでした。')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'33-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='設定ファイルとログは「何が原因か」を1行で言い切れるまで読みましょう。再現手順を固定すると他の人も同じ結果を得られます。')


# ------------------------------------------------------------ 1 venv / pip
def s1(ctx):
    pool = [('requests', '2.31.'), ('flask', '3.0.'), ('click', '8.1.'), ('pyyaml', '6.0.'), ('rich', '13.7.'), ('pytest', '8.0.')]
    pick = R.sample(pool, 3)
    direct = {n: f'{n}=={v}{R.randrange(10)}' for n, v in pick}
    trans = ['certifi==2024.2.2', 'charset-normalizer==3.3.2', 'idna==3.6', 'urllib3==2.2.1']
    allv = sorted(list(direct.values()) + trans)
    put(ctx, 'pip_freeze.txt', '\n'.join(allv) + '\n')
    put(ctx, 'requirements.in', '\n'.join(sorted(direct)) + '\n')
    ctx.data['pat'] = '|'.join(sorted(direct))
    ctx.data['direct'] = sorted(direct.values())
    req(ctx, 'pip_freeze.txt は検証済みの環境で採取した pip freeze の出力です。requirements.in の直接依存だけを、pip freeze のバージョンで == 固定して requirements.txt に書く。'
        '再現用の手順 steps.sh（コメント以外の行で、仮想環境 .venv の作成・有効化・pip install -r requirements.txt・pip freeze > frozen.txt をこの順に）も書く。実行はしません。')


def c1(ctx):
    need_ro(ctx)
    got = sorted(x.strip() for x in ctx.need_file('requirements.txt').splitlines() if x.strip())
    ctx.require(got == ctx.data['direct'], 'requirements.txtには直接依存だけを、pip freezeと同じ == 固定で書きます（推移的依存は含めません）。')
    seq(ctx, 'steps.sh', [
        (lambda l: tk(l)[:3] in (['python3', '-m', 'venv'], ['python', '-m', 'venv']) and '.venv' in tk(l), 'python3 -m venv .venv'),
        (lambda l: tk(l) in (['source', '.venv/bin/activate'], ['.', '.venv/bin/activate']), 'source .venv/bin/activate'),
        (lambda l: tk(l)[:4] == ['pip', 'install', '-r', 'requirements.txt'], 'pip install -r requirements.txt'),
        (lambda l: re.fullmatch(r'pip freeze\s*>\s*frozen\.txt', l) is not None, 'pip freeze > frozen.txt')])


SOL1 = """grep -E '^(<<pat>>)==' pip_freeze.txt > requirements.txt
printf '%s\\n' 'python3 -m venv .venv' 'source .venv/bin/activate' 'pip install -r requirements.txt' 'pip freeze > frozen.txt' > steps.sh"""
mission(1, 'venvとrequirements.txt：pip freezeで依存を固定する',
        '別のPCで同じ環境を作れず困っています。Pythonの仮想環境 venv を作り、pip の requirements.txt に依存を固定し、pip freeze で確認する流れを整えます。pip freezeの結果には推移的依存も混ざるため、直接依存だけを選びます。',
        ['requirements.txtに直接依存だけを==固定で書く', 'steps.shに再現手順を順番どおり書く'], s1, c1, SOL1,
        ["cp pip_freeze.txt requirements.txt\nprintf '%s\\n' 'python3 -m venv .venv' 'source .venv/bin/activate' 'pip install -r requirements.txt' 'pip freeze > frozen.txt' > steps.sh",
         "cp requirements.in requirements.txt\nprintf '%s\\n' 'pip install -r requirements.txt' 'python3 -m venv .venv' > steps.sh"],
        'python3 -m venv .venv で依存を隔離し、有効化後の pip install -r requirements.txt で再現します。pip freeze の出力は環境の完全な記録ですが、全部を書くと更新が大変になるため、直接依存を==で固定する運用（または requirements.in から pip-compile）が一般的です。環境の外に出るには deactivate、.venv はコミットしません。',
        'pip freezeには自分が入れていない依存も含まれます。', 'grep -Eで直接依存名の行だけを抜き出し、printfで手順を並べます。')


# ------------------------------------------------------------ 2 pyproject
def s2(ctx):
    name = 'tool-' + '%04x' % R.randrange(65536)
    ver = f'{R.randrange(0, 4)}.{R.randrange(10)}.{R.randrange(10)}'
    py = f'>=3.{R.randrange(9, 13)}'
    deps = sorted(R.sample(['requests>=2.31', 'click>=8.1,<9', 'rich>=13', 'pydantic>=2.5', 'httpx>=0.27'], 2))
    dev = sorted(R.sample(['pytest>=8', 'ruff>=0.4', 'black>=24', 'mypy>=1.8'], 2))
    cmd = R.choice(['fetch', 'sync', 'report', 'scan'])
    ep = f'{name.replace("-", "_")}.cli:main'
    be = R.choice(['setuptools.build_meta', 'hatchling.build', 'flit_core.buildapi'])
    q = lambda xs: ', '.join(json.dumps(x) for x in xs)
    put(ctx, 'pyproject.toml', f'''[build-system]
requires = ["{be.split('.')[0].replace('_', '-')}"]
build-backend = "{be}"

[project]
name = "{name}"
version = "{ver}"
requires-python = "{py}"
dependencies = [{q(deps)}]

[project.optional-dependencies]
dev = [{q(dev)}]

[project.scripts]
{cmd} = "{ep}"
''')
    ctx.data['exp'] = dict(name=name, version=ver, requires_python=py, dependencies=deps, dev_dependencies=dev,
                           script_name=cmd, entry_point=ep, build_backend=be)
    req(ctx, 'pyproject.toml を読み、answer.json に name・version・requires_python・dependencies（実行時依存の配列）・dev_dependencies（optional-dependencies の dev）・script_name・entry_point（scripts の呼び出し先）・build_backend（build-system のもの）を書く。')


def c2(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    for k, v in ctx.data['exp'].items():
        got = a.get(k)
        if isinstance(v, list):
            got = sorted(got) if isinstance(got, list) else got
        ctx.require(got == v, f'answer.json の {k} が違います。pyproject.tomlの該当セクションを読み直してください。')


SOL2 = """python3 - <<'PY'
import json, tomllib
d = tomllib.load(open('pyproject.toml', 'rb'))
p = d['project']
(sn, ep), = p['scripts'].items()
json.dump({'name': p['name'], 'version': p['version'], 'requires_python': p['requires-python'],
           'dependencies': p['dependencies'], 'dev_dependencies': p['optional-dependencies']['dev'],
           'script_name': sn, 'entry_point': ep, 'build_backend': d['build-system']['build-backend']},
          open('answer.json', 'w'))
PY"""
mission(2, 'pyproject.tomlを読み解く',
        '引き継いだPythonパッケージには setup.py がなく pyproject.toml だけがあります。[build-system]・[project]・[project.scripts] の意味を読み、要点をanswer.jsonにまとめてください。',
        ['pyproject.tomlの各セクションを読む', 'answer.jsonに要点を書く'], s2, c2, SOL2,
        ['echo \'{"name": "x"}\' > answer.json', 'python3 -c "print(1)" > answer.json'],
        'pyproject.toml は PEP 621 のメタデータ（[project]）とビルド方法（[build-system]）を1か所にまとめます。pip install . や pip install -e .（編集可能インストール）は build-backend を呼びます。[project.scripts] はインストール時にコマンド名を作り、optional-dependencies は pip install ".[dev]" のように追加指定します。',
        '依存は実行時用と開発用で場所が違います。', 'tomllibで読み込んでjson.dumpすると読み間違いがありません。')


# ------------------------------------------------------------ 3 pytest
def s3(ctx):
    good = R.choice([0.05, 0.08, 0.1, 0.2])
    bad = round(good * 100, 2)
    bad_s = repr(float(bad))
    exp = round(200 * (1 + good))
    got = round(200 * (1 + bad))
    ctx.data.update(good=good, bad=bad_s, exp=exp)
    put(ctx, 'calc.py', f'''TAX_RATE = {bad_s}


def total(prices):
    return sum(prices)


def with_tax(price):
    return round(price * (1 + TAX_RATE))
''', readonly=False)
    t = f'''from calc import total, with_tax


def test_total():
    assert total([1, 2, 3]) == 6


def test_with_tax():
    assert with_tax(200) == {exp}
'''
    put(ctx, 'test_calc.py', t)
    ln = t.splitlines().index(f'    assert with_tax(200) == {exp}') + 1
    put(ctx, 'pytest.log', f'''============================= test session starts ==============================
collected 2 items

test_calc.py .F                                                          [100%]

=================================== FAILURES ===================================
________________________________ test_with_tax _________________________________

    def test_with_tax():
>       assert with_tax(200) == {exp}
E       assert {got} == {exp}
E        +  where {got} = with_tax(200)

test_calc.py:{ln}: AssertionError
=========================== short test summary info ============================
FAILED test_calc.py::test_with_tax - assert {got} == {exp}
========================= 1 failed, 1 passed in 0.03s ==========================
''')
    req(ctx, 'pytest.log の失敗ログを診断する。失敗したテストのIDを failed.txt に（1行、test_calc.py::関数名）書き、calc.py の原因を直してテストを通す。テストの期待値は正しいので test_calc.py は変更しない。')


def c3(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('failed.txt').strip() == 'test_calc.py::test_with_tax', 'failed.txt に失敗したテストID（test_calc.py::test_with_tax形式）を書きます。')
    code = f"import sys; sys.path.insert(0, {str(ctx.work)!r}); import test_calc as t; t.test_total(); t.test_with_tax()"
    r = run(ctx, ['python3', '-B', '-c', code])
    ctx.require(r.returncode == 0, 'テストがまだ通りません: ' + r.stderr.strip().splitlines()[-1][:100] if r.stderr.strip() else 'テストがまだ通りません。')


SOL3 = """sed -i 's/^TAX_RATE = .*/TAX_RATE = <<good>>/' calc.py
echo 'test_calc.py::test_with_tax' > failed.txt"""
mission(3, 'pytestの失敗ログから原因を見つけて直す',
        'CIで pytest が1件失敗しました。pytestの採取記録でassertの左右の値を比べ、どちらが期待値でどちらが実際の値かを読み、原因のコードを直します。',
        ['failed.txtに失敗テストIDを書く', '失敗原因のコードを見つけて直しテストを通す'], s3, c3, SOL3,
        ["echo 'test_calc.py::test_with_tax' > failed.txt\nsed -i 's/^TAX_RATE = .*/TAX_RATE = 0.5/' calc.py",
         "echo 'test_calc.py::test_total' > failed.txt\nsed -i 's/^TAX_RATE = .*/TAX_RATE = <<good>>/' calc.py"],
        'pytestの失敗ログは「>」で失敗した行、「E」で実際の値と期待値、最後の FAILED 行でテストIDを示します。assert 実際 == 期待 の左が実際の値です。テストを書き換えて通すのは本末転倒で、期待値が仕様なら製品コードを直します。pytest -k 名前 や pytest test_calc.py::test_with_tax で1件だけ再実行できます。',
        'assertの左側が実際の値です。', 'sed -iで定数の行を置き換えます。')


# ------------------------------------------------------------ 4 lint
def s4(ctx):
    um = R.choice(['os', 'sys', 'glob'])
    fn = R.choice(['add_pair', 'sum_two', 'combine'])
    tmp = R.choice(['tmp', 'unused', 'dummy'])
    ctx.data.update(um=um, fn=fn)
    src = f'''import json
import {um}


def {fn}(a,b):
    {tmp} = a * b
    total=a+b
    return json.dumps({{"total": total, "label": "result of adding the two input numbers together"}})
'''
    put(ctx, 'messy.py', src, readonly=False)
    ls = src.splitlines()
    put(ctx, 'flake8.log', f'''messy.py:2:1: F401 '{um}' imported but unused
messy.py:5:{len(fn) + 7}: E231 missing whitespace after ','
messy.py:6:5: F841 local variable '{tmp}' is assigned to but never used
messy.py:7:10: E225 missing whitespace around operator
messy.py:8:80: E501 line too long ({len(ls[7])} > 79 characters)
''')
    req(ctx, 'flake8.log（flake8 の指摘。black や ruff check --fix でも同種の整形・修正ができる）の全指摘を messy.py で直す。動作（返すJSONの total と label キー）は変えない。さらに lint.sh に flake8・black --check・ruff check を各1行（コメント以外）で書く。')


def c4(ctx):
    need_ro(ctx)
    src = ctx.need_file('messy.py')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        ctx.fail('messy.py に構文エラーがあります。')
    for i, l in enumerate(src.splitlines(), 1):
        ctx.require(len(l) <= 79, f'{i}行目が79文字を超えています（E501）。')
        ctx.require(l == l.rstrip(), f'{i}行目の末尾に空白があります。')
        ctx.require(not re.search(r',\S', l), f'{i}行目: カンマの後に空白が必要です（E231）。')
        ctx.require(not re.match(r'\s*\w+=\S', l) and not re.search(r'\w\+\w', l), f'{i}行目: 演算子の前後に空白が必要です（E225）。')
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    ctx.require(imported <= used, '使っていないimportが残っています（F401）。')
    for f in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        st = {n.id for n in ast.walk(f) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        ld = {n.id for n in ast.walk(f) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        ctx.require(st <= ld, '代入だけして使っていない変数があります（F841）。')
    ns = {}
    exec(compile(src, 'messy.py', 'exec'), ns)
    try:
        r = json.loads(ns[ctx.data['fn']](2, 3))
    except Exception:
        ctx.fail('関数の動作を保ってください（JSON文字列を返す）。')
    ctx.require(r.get('total') == 5 and 'label' in r, '返す値（total=a+b と label）は変えません。')
    seq(ctx, 'lint.sh', [(starts('flake8'), 'flake8'), (starts('black', '--check'), 'black --check'), (starts('ruff', 'check'), 'ruff check')])


SOL4 = """cat > messy.py <<'EOF'
import json


def <<fn>>(a, b):
    total = a + b
    label = "result of adding the two numbers"
    return json.dumps({"total": total, "label": label})
EOF
printf '%s\\n' 'flake8 .' 'black --check .' 'ruff check .' > lint.sh"""
mission(4, 'flake8・black・ruffの指摘を直す',
        'レビューで flake8 の指摘が大量に出ました。コード規約はツールに任せたいので、black（整形）と ruff（高速なlinter）も使えるようにしておきます。flake8の採取記録の各コード（E・F）の意味を読んで直してください。',
        ['messy.pyの指摘を全て直す', 'lint.shにflake8・black・ruffを書く'], s4, c4, SOL4,
        ["sed -i '/^import <<um>>$/d' messy.py\nprintf '%s\\n' 'flake8 .' 'black --check .' 'ruff check .' > lint.sh",
         "echo 'flake8 .' > lint.sh"],
        'Fxxxはpyflakes（未使用import F401・未使用変数 F841）、Exxx/Wxxxはpycodestyle（空白E225/E231・行長E501）の指摘です。blackは整形を自動適用（--checkは差分があれば失敗）、ruff check --fix は多くのF/E指摘を自動修正します。flake8 は報告だけなので手で直します。',
        '指摘は5種類あります。', 'ログの行番号とコードを1つずつ対応させ、まとめて書き直します。')


# ------------------------------------------------------------ 5 http.server / json.tool
def s5(ctx):
    ctx.data['port'] = 8000 + R.randrange(1000)
    ctx.write('site/index.html', '<h1>demo</h1>\n')
    d = {'id': R.randrange(1000), 'tags': ['a', 'b'], 'nested': {'ok': True, 'n': R.randrange(100)}}
    put(ctx, 'raw.json', json.dumps(d, separators=(',', ':')) + '\n')
    ctx.data['raw'] = d
    req(ctx, f'site/ を 127.0.0.1 のみで、ポート {ctx.data["port"]} で配信する標準ライブラリのコマンドを serve.sh に1行で書く（起動はしない）。'
        'また minify された raw.json を標準ライブラリで整形して pretty.json に保存する（raw.json は変更しない）。')


def c5(ctx):
    need_ro(ctx)
    t = toks(ctx, one_line(ctx, 'serve.sh'))
    ctx.require(t[0] in ('python3', 'python') and t[1:3] == ['-m', 'http.server'], 'python3 -m http.server を使います。')
    ctx.require(str(ctx.data['port']) in t, 'ポート番号を指定します。')
    ctx.require('--bind' in t and t[t.index('--bind') + 1] == '127.0.0.1', '--bind 127.0.0.1 で自分のPCだけに公開します。')
    ctx.require('--directory' in t and t[t.index('--directory') + 1].rstrip('/') == 'site', '--directory site を指定します。')
    txt = ctx.need_file('pretty.json')
    try:
        ok = json.loads(txt) == ctx.data['raw']
    except ValueError:
        ok = False
    ctx.require(ok, 'pretty.json はraw.jsonと同じ内容のJSONにします。')
    ctx.require('\n    "' in txt, 'インデント付きで整形します（python3 -m json.tool）。')


SOL5 = """echo "python3 -m http.server <<port>> --bind 127.0.0.1 --directory site" > serve.sh
python3 -m json.tool raw.json pretty.json"""
mission(5, 'python -m http.serverとjson.toolを使う',
        '共有用に静的ファイルを手早く公開し、APIの応答JSONを読みやすく整える作業です。インストール不要の python -m http.server と python -m json.tool で済ませます。',
        ['serve.shに公開用コマンドを1行で書く', 'json.toolでpretty.jsonを作る'], s5, c5, SOL5,
        ['echo "python3 -m http.server <<port>> --directory site" > serve.sh\ncp raw.json pretty.json',
         'echo "python -m SimpleHTTPServer <<port>>" > serve.sh\npython3 -m json.tool raw.json pretty.json'],
        'python3 -m http.server は既定で全インターフェースに公開するので、--bind 127.0.0.1 で限定し、--directory で公開フォルダを指定します（本番用ではありません）。python3 -m json.tool 入力 出力 はJSONの検証と整形（--sort-keys, --indent）ができ、壊れたJSONならエラーになるので検証にも使えます。',
        '公開範囲を意識します。', '2つのモジュールは python3 -m で呼びます。')


# ------------------------------------------------------------ 6 package.json / lock
def s6(ctx):
    exp_v = f'4.{R.randrange(17, 19)}.{R.randrange(10)}'
    lock_v = f'4.{R.randrange(19, 22)}.{R.randrange(10)}'
    flags = R.choice(['--ci', '--runInBand', '--silent'])
    pj = {'name': 'web-app', 'version': '1.0.0', 'private': True,
          'scripts': {'build': 'tsc -p .', 'test': f'jest {flags}', 'lint': 'eslint src', 'start': 'node dist/index.js'},
          'dependencies': {'express': '^' + exp_v}}
    put(ctx, 'package.json', json.dumps(pj, indent=2) + '\n')
    lock = {'name': 'web-app', 'version': '1.0.0', 'lockfileVersion': 3, 'requires': True,
            'packages': {'': {'name': 'web-app', 'dependencies': {'express': '^' + exp_v}},
                         'node_modules/express': {'version': lock_v, 'resolved': 'https://registry.npmjs.org/express/-/express-' + lock_v + '.tgz'}}}
    put(ctx, 'package-lock.json', json.dumps(lock, indent=2) + '\n')
    ctx.data.update(test=pj['scripts']['test'], lock_v=lock_v)
    req(ctx, 'package.json と package-lock.json を読み、answer.json に test_command（npm test が実行する文字列）・npm_build（ビルドの npm コマンド）・yarn_build（同じ意味の yarn コマンド）・locked_express（実際に固定されている express の版）・lockfile_version を書く。'
        'また、prettier をインストールせず1回だけ src を --check する npx コマンドを cmd.txt に1行で書く。')


def c6(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    d = ctx.data
    ctx.require(a.get('test_command') == d['test'], 'test_command は scripts.test の文字列です。')
    ctx.require(a.get('npm_build') == 'npm run build' and a.get('yarn_build') == 'yarn build', 'npm は npm run build、yarn は yarn build です。')
    ctx.require(a.get('locked_express') == d['lock_v'], 'locked_express は package-lock.json の実際の版です（package.jsonの範囲ではありません）。')
    ctx.require(a.get('lockfile_version') == 3, 'lockfile_version を読み直してください。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'npx' and 'prettier' in t and '--check' in t and 'src' in t, 'npx prettier --check src の形にします。')


SOL6 = """python3 - <<'PY'
import json
p = json.load(open('package.json')); l = json.load(open('package-lock.json'))
json.dump({'test_command': p['scripts']['test'], 'npm_build': 'npm run build', 'yarn_build': 'yarn build',
           'locked_express': l['packages']['node_modules/express']['version'],
           'lockfile_version': l['lockfileVersion']}, open('answer.json', 'w'))
PY
echo "npx prettier --check src" > cmd.txt"""
mission(6, 'package.jsonとpackage-lock・scripts・npx',
        'Node.jsプロジェクトを引き継ぎました。package.json の scripts（npm run / yarn の呼び出し先）、package-lock.json が固定する実際の版、一時実行する npx の使い方を整理します。',
        ['answer.jsonにscriptsとlockの要点を書く', 'cmd.txtにnpxコマンドを書く'], s6, c6, SOL6,
        ['echo \'{"test_command": "jest"}\' > answer.json\necho "npm install -g prettier" > cmd.txt', 'echo "npx prettier src" > cmd.txt'],
        'package.json の dependencies は許容範囲（^4.18.0 など）、package-lock.json は実際に解決した版を固定し、npm ci はlockのとおりに再現します。scripts は npm run 名前（test と start は run 省略可）、yarn なら yarn 名前 で実行します。npx はローカルの node_modules/.bin を優先し、なければ一時的に取得して実行します。',
        '範囲と固定は別物です。', 'JSONはpythonで読むと確実です。')


# ------------------------------------------------------------ 7 nvm / eslint / prettier
def s7(ctx):
    n = R.choice([18, 20, 22])
    semi = R.choice(['always', 'never'])
    q = R.choice(['single', 'double'])
    w = R.choice([80, 100, 120])
    put(ctx, 'package.json', json.dumps({'name': 'site', 'engines': {'node': f'>={n}'}}, indent=2) + '\n')
    put(ctx, '.eslintrc.json', json.dumps({'extends': 'eslint:recommended', 'rules': {'semi': ['error', semi], 'quotes': ['error', q], 'no-unused-vars': 'warn'}}, indent=2) + '\n')
    ctx.write('.prettierrc', json.dumps({'printWidth': w, 'semi': semi == 'never', 'singleQuote': q == 'double'}, indent=2) + '\n')
    ctx.data.update(n=n, semi=semi, q=q, w=w)
    req(ctx, 'package.json の engines に合う Node のメジャー版を .nvmrc に（数字だけ）書き、nvm.sh に nvm install と nvm use を（引数なしで .nvmrc を使う形で）この順に書く。'
        '.eslintrc.json と .prettierrc がぶつかっているので、.prettierrc の semi と singleQuote を ESLint 側に合わせる（printWidth は変更しない）。answer.json に eslint_semi・eslint_quotes・prettier_print_width を書く。')


def c7(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('.nvmrc').strip().lstrip('v') == str(d['n']), f'.nvmrc には engines の最小版 {d["n"]} を書きます。')
    seq(ctx, 'nvm.sh', [(lambda l: tk(l) == ['nvm', 'install'], 'nvm install'), (lambda l: tk(l) == ['nvm', 'use'], 'nvm use')])
    p = rj(ctx, '.prettierrc')
    ctx.require(p.get('semi') == (d['semi'] == 'always'), 'semi を ESLint の設定に合わせます。')
    ctx.require(p.get('singleQuote') == (d['q'] == 'single'), 'singleQuote を ESLint の quotes に合わせます。')
    ctx.require(p.get('printWidth') == d['w'], 'printWidth は変更しません。')
    a = rj(ctx, 'answer.json')
    ctx.require(a.get('eslint_semi') == d['semi'] and a.get('eslint_quotes') == d['q'] and a.get('prettier_print_width') == d['w'], 'answer.json の値を設定から読み直してください。')


SOL7 = """echo <<n>> > .nvmrc
printf '%s\\n' 'nvm install' 'nvm use' > nvm.sh
python3 - <<'PY'
import json
e = json.load(open('.eslintrc.json'))['rules']; p = json.load(open('.prettierrc'))
p['semi'] = e['semi'][1] == 'always'; p['singleQuote'] = e['quotes'][1] == 'single'
json.dump(p, open('.prettierrc', 'w'))
json.dump({'eslint_semi': e['semi'][1], 'eslint_quotes': e['quotes'][1], 'prettier_print_width': p['printWidth']}, open('answer.json', 'w'))
PY"""
mission(7, 'nvmでNode版を揃え、ESLintとPrettierの設定を読む',
        'チームでNodeの版がバラバラで、ESLintとPrettierの規則も衝突して保存のたびに差分が出ます。nvm（Node Version Manager）の考え方は「プロジェクトの .nvmrc を読んで版を切り替える」ことです。',
        ['.nvmrcとnvm.shを書く', '.prettierrcをESLintに合わせてanswer.jsonを書く'], s7, c7, SOL7,
        ["echo <<n>> > .nvmrc\nprintf '%s\\n' 'nvm install' 'nvm use' > nvm.sh", "echo 99 > .nvmrc\nprintf '%s\\n' 'nvm use' > nvm.sh"],
        'nvm は版ごとにNodeを ~/.nvm 配下に入れ、シェルの PATH を切り替えます。.nvmrc があれば nvm use / nvm install は引数なしで読み取ります。ESLint は品質ルール（semi・quotes・no-unused-vars の error/warn/off）、Prettier は見た目の整形で、両方が同じ semi・quote を求めないと保存のたびに衝突します（衝突を避ける eslint-config-prettier もあります）。',
        'ESLintのルールは [重大度, 値] の配列です。', 'jsonで3つの設定ファイルを読み、1つだけ書き換えます。')


# ------------------------------------------------------------ 8 npm audit
def s8(ctx):
    names = R.sample(['lodash', 'minimist', 'axios', 'semver', 'tar', 'qs'], 5)
    sev = ['critical', 'high', 'moderate', 'low', 'high']
    R.shuffle(sev)
    vul = {}
    for nme, s in zip(names, sev):
        vul[nme] = {'name': nme, 'severity': s, 'fixAvailable': True}
    hi = [n for n in names if vul[n]['severity'] in ('high', 'critical')]
    major = [R.choice(hi), R.choice(names)]
    for n in set(major):
        vul[n]['fixAvailable'] = {'name': n, 'version': '9.0.0', 'isSemVerMajor': True}
    put(ctx, 'audit.json', json.dumps({'auditReportVersion': 2, 'vulnerabilities': vul}, indent=2) + '\n')
    ctx.data['hi'] = sorted(hi)
    ctx.data['major'] = sorted(n for n in names if vul[n]['fixAvailable'] is not True)
    req(ctx, 'audit.json は npm audit --json の出力です。severity が high か critical の依存名（昇順）を high_or_critical に、'
        '修正に破壊的変更（isSemVerMajor）が必要な依存名（昇順）を needs_major に answer.json で書く。破壊的変更なしで直せる範囲だけを適用する npm のコマンドを fix.txt に1行で書く。')


def c8(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    ctx.require(a.get('high_or_critical') == ctx.data['hi'], 'high_or_critical は severity が high または critical の依存名だけです。')
    ctx.require(a.get('needs_major') == ctx.data['major'], 'needs_major は fixAvailable が isSemVerMajor の依存名です。')
    t = toks(ctx, one_line(ctx, 'fix.txt'))
    ctx.require(t == ['npm', 'audit', 'fix'], '--force なしの npm audit fix にします（破壊的変更は個別に判断）。')


SOL8 = """python3 - <<'PY'
import json
v = json.load(open('audit.json'))['vulnerabilities']
json.dump({'high_or_critical': sorted(n for n, x in v.items() if x['severity'] in ('high', 'critical')),
           'needs_major': sorted(n for n, x in v.items() if x['fixAvailable'] is not True and x['fixAvailable']['isSemVerMajor'])},
          open('answer.json', 'w'))
PY
echo "npm audit fix" > fix.txt"""
mission(8, 'npm auditの出力を読んで優先度を付ける',
        'CIが npm audit で失敗しました。出力（JSON）から、深刻度の高いものと、直すと互換性が壊れるもの（breaking change）を分けて報告します。',
        ['answer.jsonに2種類の依存名を書く', 'fix.txtに安全な修正コマンドを書く'], s8, c8, SOL8,
        ['echo "npm audit fix --force" > fix.txt\necho \'{}\' > answer.json', "echo 'npm update' > fix.txt"],
        'npm audit は依存ツリーの既知脆弱性を severity（critical・high・moderate・low）で示します。fixAvailable が true なら npm audit fix（semver範囲内の更新）で直せ、isSemVerMajor が true だと --force が必要で互換性が壊れる可能性があるため、テストを付けて個別に更新します。実行環境が本番向けか開発専用かも優先度の材料です。',
        'fixAvailableは真偽値か、オブジェクトです。', 'pythonでJSONの辞書を絞り込みます。')


# ------------------------------------------------------------ 9 Go
def s9(ctx):
    mod = 'example.com/' + R.choice(['calc', 'shop', 'tool']) + '%02d' % R.randrange(100)
    gv = '1.%d' % R.randrange(20, 23)
    pkg = R.choice(['github.com/google/uuid', 'github.com/spf13/cobra', 'github.com/rs/zerolog'])
    ln = R.randrange(8, 40)
    got = R.randrange(4, 9)
    want = got + R.choice([-1, 1])
    put(ctx, 'go.mod', f'module {mod}\n\ngo {gv}\n')
    put(ctx, 'build.log', f'main.go:5:2: no required module provides package {pkg}; to add it:\n\tgo get {pkg}\n')
    put(ctx, 'test.log', f'--- FAIL: TestAdd (0.00s)\n    calc_test.go:{ln}: Add(2, 3) = {got}; want {want}\nFAIL\nFAIL\t{mod}\t0.002s\nFAIL\n')
    ctx.data.update(mod=mod, gv=gv, pkg=pkg, ln=ln, got=got, want=want)
    req(ctx, 'go build と go test の出力（build.log・test.log）と go.mod を読み、answer.json に module・go_version・missing_package・failed_test・test_file・test_line・got・want（数値）を書く。'
        '足りない依存を整えるコマンド（go mod tidy か go get 該当パッケージ）を fix.txt に1行で書く。')


def c9(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    d = ctx.data
    exp = dict(module=d['mod'], go_version=d['gv'], missing_package=d['pkg'], failed_test='TestAdd', test_file='calc_test.go',
               test_line=d['ln'], got=d['got'], want=d['want'])
    for k, v in exp.items():
        ctx.require(a.get(k) == v, f'answer.json の {k} が違います。')
    t = toks(ctx, one_line(ctx, 'fix.txt'))
    ctx.require(t == ['go', 'mod', 'tidy'] or t == ['go', 'get', d['pkg']], 'go mod tidy か go get パッケージ名 にします。')


SOL9 = """python3 - <<'PY'
import json, re
b = open('build.log').read(); t = open('test.log').read(); m = open('go.mod').read()
f, l, got, want = re.search(r'(\\w+_test\\.go):(\\d+): .*= (\\d+); want (\\d+)', t).groups()
json.dump({'module': re.search(r'^module (\\S+)', m, re.M).group(1), 'go_version': re.search(r'^go (\\S+)', m, re.M).group(1),
           'missing_package': re.search(r'provides package (\\S+?);', b).group(1), 'failed_test': re.search(r'--- FAIL: (\\w+)', t).group(1),
           'test_file': f, 'test_line': int(l), 'got': int(got), 'want': int(want)}, open('answer.json', 'w'))
PY
echo "go mod tidy" > fix.txt"""
mission(9, 'go mod・go build・go testの出力を読む',
        'Goプロジェクトのビルドとテストが失敗しています。go.mod（モジュール名とgoの版）、go build のエラー、go test の FAIL 行を読み分け、足りない依存の解決方法を決めます。',
        ['answer.jsonに診断結果を書く', 'fix.txtに修復コマンドを書く'], s9, c9, SOL9,
        ['echo \'{"failed_test": "TestAdd"}\' > answer.json\necho "go mod tidy" > fix.txt', 'echo "go build ./..." > fix.txt'],
        'go.mod は module（自分のパス）・go（言語版）・require（依存）を持ちます。go build の "no required module provides package" は依存が未登録で、go get パッケージ か go mod tidy（使用中の依存を追加し不要なものを削除）で直します。go test の "--- FAIL: 名前" と "ファイル:行: 内容" が失敗箇所、want が期待値です。',
        'build.logとtest.logは別の問題です。', '正規表現で値を拾ってjsonに入れます。')


# ------------------------------------------------------------ 10 Rust
def s10(ctx):
    name = R.choice(['rtool', 'scanner', 'cruncher']) + str(R.randrange(10))
    ver = f'0.{R.randrange(1, 9)}.{R.randrange(10)}'
    serde = f'1.0.{R.randrange(150, 200)}'
    chan = f'1.{R.randrange(70, 80)}.0'
    lint = R.choice([('needless_return', 'unneeded `return` statement'), ('len_zero', 'length comparison to zero'),
                     ('redundant_clone', 'redundant clone'), ('collapsible_if', 'this `if` statement can be collapsed')])
    ln, col = R.randrange(5, 60), R.randrange(4, 20)
    put(ctx, 'Cargo.toml', f'[package]\nname = "{name}"\nversion = "{ver}"\nedition = "2018"\n\n[dependencies]\n', readonly=False)
    put(ctx, 'clippy.log', f'''warning: {lint[1]}
 --> src/main.rs:{ln}:{col}
  |
  = help: for further information visit https://rust-lang.github.io/rust-clippy/master/index.html#{lint[0]}
  = note: `#[warn(clippy::{lint[0]})]` on by default

warning: 1 warning emitted
''')
    ctx.data.update(name=name, ver=ver, serde=serde, chan=chan, lint=lint[0], ln=ln)
    req(ctx, f'Cargo.toml を edition 2021 にして serde = {{ version = "{serde}", features = ["derive"] }} を依存に加える（名前と版は変えない）。'
        f'rustup の toolchain を固定する rust-toolchain.toml（channel = "{chan}"、components に clippy）を作る。ci.sh に cargo build・cargo test・cargo clippy -- -D warnings をこの順で書く。'
        'clippy.log の警告名（lint名）と位置を answer.json の clippy_lint・line に書く。')


def c10(ctx):
    need_ro(ctx)
    d = ctx.data
    c = rtoml(ctx, 'Cargo.toml')
    p = c.get('package', {})
    ctx.require(p.get('name') == d['name'] and p.get('version') == d['ver'], 'packageの名前と版は変えません。')
    ctx.require(p.get('edition') == '2021', 'edition を 2021 にします。')
    s = c.get('dependencies', {}).get('serde')
    ctx.require(isinstance(s, dict) and s.get('version') == d['serde'] and s.get('features') == ['derive'], 'serde を version と features = ["derive"] 付きで書きます。')
    t = rtoml(ctx, 'rust-toolchain.toml').get('toolchain', {})
    ctx.require(t.get('channel') == d['chan'] and 'clippy' in t.get('components', []), 'rust-toolchain.toml の [toolchain] に channel と components = ["clippy"] を書きます。')
    seq(ctx, 'ci.sh', [(lambda l: tk(l) == ['cargo', 'build'], 'cargo build'), (lambda l: tk(l) == ['cargo', 'test'], 'cargo test'),
                       (lambda l: tk(l) == ['cargo', 'clippy', '--', '-D', 'warnings'], 'cargo clippy -- -D warnings')])
    a = rj(ctx, 'answer.json')
    ctx.require(a.get('clippy_lint') == d['lint'] and a.get('line') == d['ln'], 'clippy_lint と line をログから読み直してください。')


SOL10 = """cat > Cargo.toml <<'EOF'
[package]
name = "<<name>>"
version = "<<ver>>"
edition = "2021"

[dependencies]
serde = { version = "<<serde>>", features = ["derive"] }
EOF
printf '[toolchain]\\nchannel = "<<chan>>"\\ncomponents = ["clippy"]\\n' > rust-toolchain.toml
printf '%s\\n' 'cargo build' 'cargo test' 'cargo clippy -- -D warnings' > ci.sh
echo '{"clippy_lint": "<<lint>>", "line": <<ln>>}' > answer.json"""
mission(10, 'Cargo.toml・rustup toolchain・cargo clippy',
        'Rustの新規メンバーのPCで、手元のコンパイラの版が違いビルドが通りません。Cargo.toml（依存とedition）と rust-toolchain.toml（rustup が選ぶ toolchain）で環境を固定し、CIの cargo build / cargo test / cargo clippy の手順も揃えます。',
        ['Cargo.tomlとrust-toolchain.tomlを書く', 'ci.shとanswer.jsonを書く'], s10, c10, SOL10,
        ["sed -i 's/2018/2021/' Cargo.toml\nprintf '%s\\n' 'cargo build' > ci.sh", "printf '[toolchain]\\nchannel = \"<<chan>>\"\\n' > rust-toolchain.toml"],
        'Cargo.toml の [dependencies] で依存の版（SemVer互換の範囲）と features を指定し、edition は言語の互換世代です。rustup は rust-toolchain.toml を見て toolchain（stable・版番号・nightly）と components を自動で選びます。cargo clippy は lint で、-D warnings は警告をエラーにしてCIで落とします。警告は clippy::名前 で識別します。',
        'Tomlの構造を崩さないよう書きます。', 'cat > ファイル <<EOF で全文を書くのが確実です。')


# ------------------------------------------------------------ 11 Java
def s11(ctx):
    rel = R.choice([11, 17, 21])
    g = 'com.example.' + R.choice(['shop', 'billing', 'search'])
    a = R.choice(['api', 'core', 'batch']) + '-service'
    v = f'{R.randrange(1, 4)}.{R.randrange(10)}.{R.randrange(10)}'
    pj, gj = f'5.10.{R.randrange(5)}', f'5.9.{R.randrange(5)}'
    put(ctx, 'pom.xml', f'''<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>{g}</groupId>
  <artifactId>{a}</artifactId>
  <version>{v}</version>
  <properties>
    <maven.compiler.release>{rel}</maven.compiler.release>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>{pj}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
''')
    put(ctx, 'build.gradle', f'''plugins {{ id 'java' }}
group = '{g}'
version = '{v}'
java {{ toolchain {{ languageVersion = JavaLanguageVersion.of({rel}) }} }}
dependencies {{
    testImplementation 'org.junit.jupiter:junit-jupiter:{gj}'
}}
''')
    for j in (11, 17, 21):
        ctx.write(f'jdks/jdk-{j}/bin/java', f'#!/bin/sh\necho \'openjdk version "{j}.0.1"\' >&2\n', mode=0o755)
    ctx.data.update(rel=rel, exp=dict(group_id=g, artifact_id=a, version=v, java_release=rel, pom_junit_version=pj,
                                      gradle_junit_version=gj, gradle_test_config='testImplementation'))
    ctx.data['ans'] = json.dumps(ctx.data['exp'])
    req(ctx, 'pom.xml（Maven）と build.gradle（Gradle）を読み、answer.json に group_id・artifact_id・version・java_release（数値）・pom_junit_version・gradle_junit_version・gradle_test_config（JUnitを宣言しているconfiguration名）を書く。'
        '必要なJavaの版に合う jdks/jdk-版 を指す env.sh（JAVA_HOME を設定し、その bin を PATH の先頭に）も作る。')


def c11(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    for k, v in ctx.data['exp'].items():
        ctx.require(a.get(k) == v, f'answer.json の {k} が違います。')
    r = run(ctx, ['bash', '-c', '. ./env.sh && echo "$JAVA_HOME" && command -v java'])
    ctx.require(r.returncode == 0 and len(r.stdout.split('\n')) >= 2, 'env.sh を source できません。')
    jh, jv = r.stdout.split('\n')[:2]
    base = ctx.p(f'jdks/jdk-{ctx.data["rel"]}')
    ctx.require(os.path.realpath(jh) == str(base.resolve()), f'JAVA_HOME は jdks/jdk-{ctx.data["rel"]} を指します。')
    ctx.require(os.path.realpath(jv) == str((base / 'bin/java').resolve()), 'JAVA_HOME/bin を PATH の先頭に置き、java がそれを指すようにします。')


SOL11 = """cat > answer.json <<'EOF'
<<ans>>
EOF
printf '%s\\n' 'export JAVA_HOME="$PWD/jdks/jdk-<<rel>>"' 'export PATH="$JAVA_HOME/bin:$PATH"' > env.sh"""
mission(11, 'pom.xmlとbuild.gradleの読解・JAVA_HOME',
        'Javaのサービスが Maven でも Gradle でもビルドできる状態で渡されました。両方の設定（座標・Javaの版・テスト依存）を読み、使う JDK を JAVA_HOME で切り替えられるようにします。',
        ['answer.jsonに設定の要点を書く', 'env.shでJAVA_HOMEを設定する'], s11, c11, SOL11,
        ['echo \'{}\' > answer.json\necho \'export JAVA_HOME=/usr\' > env.sh', "printf '%s\\n' 'export JAVA_HOME=\"$PWD/jdks/jdk-<<rel>>\"' > env.sh\necho '{}' > answer.json"],
        'Mavenは groupId・artifactId・version（GAV）で成果物を特定し、maven.compiler.release がJavaの版、scope=test がテスト限定です。Gradleでは group・version・toolchain の languageVersion、testImplementation がテスト用の依存です。JAVA_HOME は mvn/gradle が使うJDKの場所で、$JAVA_HOME/bin を PATH の先頭に置かないと別の java が使われます。',
        'MavenとGradleでJUnitの版が食い違っています。', 'export行は printf で書き、変数は評価前に保存します。')


# ------------------------------------------------------------ 12 Makefile
def s12(ctx):
    prog = R.choice(['app', 'calc', 'tool'])
    ctx.data['prog'] = prog
    put(ctx, 'util.h', 'int util(int);\n')
    put(ctx, 'main.c', '#include "util.h"\nint main(void) { return util(0); }\n')
    put(ctx, 'util.c', '#include "util.h"\nint util(int x) { return x; }\n')
    ctx.write('Makefile', f'{prog}: main.o util.o\n\tgcc main.o util.o -o {prog}\nmain.o: main.c\n\tgcc -c main.c\nutil.o: util.c\n\tgcc -c util.c\nclean:\n\trm -f *.o {prog}\n')
    req(ctx, f'util.h を変更しても再ビルドされず、gcc の指定も直書きです。Makefile を直す: 変数 CC = gcc・CFLAGS（-Wall -O2 -g）・OBJS（main.o util.o）、先頭ターゲット all（{prog} を作る）、.PHONY: all clean、'
        f'{prog} は $(OBJS) に依存、main.o と util.o は .c に加えて util.h にも依存、レシピは $(CC) と $(CFLAGS) を使いタブでインデントする。')


def c12(ctx):
    need_ro(ctx)
    mk = ctx.need_file('Makefile')
    prog = ctx.data['prog']
    ctx.require(re.search(r'^CC\s*[:?]?=\s*gcc\s*$', mk, re.M), 'CC = gcc の変数を定義します。')
    cf = re.search(r'^CFLAGS\s*[:?]?=(.*)$', mk, re.M)
    ctx.require(cf and all(f in cf.group(1).split() for f in ('-Wall', '-O2', '-g')), 'CFLAGS に -Wall -O2 -g を入れます。')
    ob = re.search(r'^OBJS\s*[:?]?=(.*)$', mk, re.M)
    ctx.require(ob and {'main.o', 'util.o'} <= set(ob.group(1).split()), 'OBJS に main.o util.o を入れます。')
    ph = re.search(r'^\.PHONY\s*:(.*)$', mk, re.M)
    ctx.require(ph and {'all', 'clean'} <= set(ph.group(1).split()), '.PHONY: all clean を宣言します。')
    rules = {}
    order = []
    for l in mk.splitlines():
        m = re.match(r'^([A-Za-z0-9_.$()/-]+)\s*:(?!=)\s*(.*)$', l)
        if m and not l.startswith('\t') and not l.startswith('.PHONY'):
            rules[m.group(1)] = m.group(2).split()
            order.append(m.group(1))
    ctx.require(order and order[0] == 'all', '先頭のターゲットを all にします。')
    ctx.require(prog in rules.get('all', []), f'all は {prog} に依存させます。')
    ctx.require('$(OBJS)' in rules.get(prog, []), f'{prog} は $(OBJS) に依存します。')
    for o, c in (('main.o', 'main.c'), ('util.o', 'util.c')):
        ctx.require(c in rules.get(o, []) and 'util.h' in rules.get(o, []), f'{o} は {c} と util.h の両方に依存させます。')
    rec = [l for l in mk.splitlines() if l.startswith('\t')]
    ctx.require(not any(re.match(r' {2,}\S', l) for l in mk.splitlines()), 'レシピのインデントはタブです。')
    ctx.require(rec and not any(re.search(r'\bgcc\b', l) for l in rec) and any('$(CC)' in l and '$(CFLAGS)' in l for l in rec), 'レシピは gcc 直書きではなく $(CC) $(CFLAGS) を使います。')


SOL12 = """cat > Makefile <<'EOF'
CC = gcc
CFLAGS = -Wall -O2 -g
OBJS = main.o util.o

.PHONY: all clean

all: <<prog>>

<<prog>>: $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) -o $@

main.o: main.c util.h
	$(CC) $(CFLAGS) -c main.c

util.o: util.c util.h
	$(CC) $(CFLAGS) -c util.c

clean:
	rm -f $(OBJS) <<prog>>
EOF"""
mission(12, 'Makefileの依存・.PHONY・変数',
        'ヘッダを書き換えても make が何もせず古いバイナリが残る、という報告です。Makefile の依存関係（ターゲット: 前提）、.PHONY、変数の使い方を直します。',
        ['Makefileを仕様どおり書き直す'], s12, c12, SOL12,
        ["sed -i 's/^clean:/.PHONY: clean\\nclean:/' Makefile", "printf 'CC = gcc\\nCFLAGS = -Wall -O2 -g\\nOBJS = main.o util.o\\n' > Makefile"],
        'makeはターゲットより前提（.c/.h）が新しいときだけレシピを実行します。ヘッダ依存を書かないとヘッダの変更を検知できません。.PHONY はファイル名ではない「動作」のターゲット（all・clean）を宣言し、同名ファイルがあっても必ず実行します。CC・CFLAGS・OBJS の変数を使えば変更が1か所で済み、$@ はターゲット名です。レシピは必ずタブで始めます。',
        'ヘッダへの依存が抜けています。', 'cat > Makefile <<EOF で、レシピ行はタブにします。')


# ------------------------------------------------------------ 13 gcc / undefined reference
def s13(ctx):
    fn = R.choice(['vec_norm', 'mat_len', 'dist2'])
    prog = R.choice(['calc', 'app', 'geo'])
    ctx.data.update(fn=fn, prog=prog)
    put(ctx, 'main.c', f'#include <stdio.h>\ndouble {fn}(double);\nint main(void) {{ printf("%f\\n", {fn}(2.0)); return 0; }}\n')
    put(ctx, 'vec.c', f'#include <math.h>\ndouble {fn}(double x) {{ return sqrt(x); }}\n')
    put(ctx, 'link.log', f"/usr/bin/ld: main.o: in function `main':\nmain.c:3: undefined reference to `{fn}'\ncollect2: error: ld returned 1 exit status\n")
    ctx.write('build.sh', f'gcc -c main.c\ngcc -o {prog} main.o\n')
    req(ctx, f'link.log のリンクエラーを診断し、answer.json に symbol（未定義の記号）・defined_in（定義されているソース）・cause（missing_object か missing_library）を書く。'
        f'build.sh を直す: 全ソースを gcc -Wall -O2 -g -c でコンパイルし、{prog} を -o でリンクする（vec.c が使う数学関数のため -l のライブラリも、オブジェクトより後ろに）。')


def c13(ctx):
    need_ro(ctx)
    d = ctx.data
    a = rj(ctx, 'answer.json')
    ctx.require(a.get('symbol') == d['fn'] and a.get('defined_in') == 'vec.c' and a.get('cause') == 'missing_object', 'symbol・defined_in・cause を読み直してください（vec.o をリンクしていません）。')
    ls = [x.strip() for x in ctx.need_file('build.sh').splitlines() if x.strip() and not x.strip().startswith('#')]
    comp, srcs, link = [], set(), None
    for l in ls:
        t = tk(l)
        if not t or t[0] not in ('gcc', 'cc'):
            continue
        if '-c' in t:
            ctx.require(all(f in t for f in ('-Wall', '-O2', '-g')), 'コンパイル行に -Wall -O2 -g を付けます。')
            srcs |= {x for x in t if x.endswith('.c')}
        else:
            link = t
    ctx.require({'main.c', 'vec.c'} <= srcs, 'main.c と vec.c の両方を -c でコンパイルします。')
    ctx.require(link and '-o' in link and link[link.index('-o') + 1] == d['prog'], f'リンク行は -o {d["prog"]} にします。')
    ctx.require('main.o' in link and 'vec.o' in link, 'リンクには main.o と vec.o を渡します。')
    ctx.require('-lm' in link and link.index('-lm') > link.index('vec.o'), '-lm は全オブジェクトより後ろに置きます。')


SOL13 = """echo '{"symbol": "<<fn>>", "defined_in": "vec.c", "cause": "missing_object"}' > answer.json
printf '%s\\n' 'gcc -Wall -O2 -g -c main.c' 'gcc -Wall -O2 -g -c vec.c' 'gcc -o <<prog>> main.o vec.o -lm' > build.sh"""
mission(13, 'gcc -Wall -O2 -g -c/-o/-lとundefined referenceの診断',
        'リンク時に undefined reference が出て実行ファイルができません。コンパイル（-c）とリンク（-o）が別工程であることを踏まえ、gcc のオプション（-Wall・-O2・-g・-l）を整理して build.sh を直します。',
        ['answer.jsonに診断を書く', 'build.shを直す'], s13, c13, SOL13,
        ['echo \'{"symbol": "<<fn>>"}\' > answer.json\necho "gcc -o <<prog>> main.c vec.c" > build.sh',
         "printf '%s\\n' 'gcc -Wall -O2 -g -c main.c' 'gcc -Wall -O2 -g -c vec.c' 'gcc -lm -o <<prog>> main.o vec.o' > build.sh"],
        'gcc -c でソースをオブジェクト（.o）にし、-o で出力名を指定してリンクします。-Wall は主な警告、-O2 は最適化、-g はデバッグ情報、-lm は libm（-l名前）を探します。undefined reference は「呼び出しはあるが定義が見つからない」リンクエラーで、定義元のオブジェクトやライブラリの渡し忘れが原因です。静的ライブラリは参照元の後ろに置かないと解決されません。',
        '未定義の記号がどのファイルで定義されているか探します。', 'リンク行の順序は オブジェクト → -l です。')


# ------------------------------------------------------------ 14 cmake / pkg-config
def s14(ctx):
    lib = R.choice(['fastjson', 'zlibx', 'netkit'])
    pre = '/opt/' + lib + '%d' % R.randrange(10)
    prog = R.choice(['viewer', 'agent', 'tool'])
    put(ctx, f'libs/{lib}.pc', f'prefix={pre}\nincludedir=${{prefix}}/include/{lib}\nlibdir=${{prefix}}/lib\n\nName: {lib}\nVersion: 2.{R.randrange(10)}\nCflags: -I${{includedir}}\nLibs: -L${{libdir}} -l{lib}\n')
    ctx.write('CMakeLists.txt', f'cmake_minimum_required(VERSION 3.16)\nproject({prog} C)\nadd_executable({prog} main.c)\n')
    ctx.data.update(lib=lib, prog=prog, flags=f'-I{pre}/include/{lib} -L{pre}/lib -l{lib}')
    req(ctx, f'libs/{lib}.pc（pkg-config の定義）を読み、pkg-config --cflags --libs {lib} が出力する1行を flags.txt に書く（変数 ${{prefix}} 等は展開する）。'
        f'CMakeLists.txt に find_package(PkgConfig ...)・pkg_check_modules（{lib}）・target_link_libraries({prog} ...) をこの順で追加する。'
        'build.sh には out-of-source build（ソースと別の build ディレクトリ。cmake -S . -B build）と cmake --build build を書く。')


def c14(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(sorted(ctx.need_file('flags.txt').split()) == sorted(d['flags'].split()), 'flags.txt は .pc の Cflags と Libs を展開した結果です。')
    cm = ctx.need_file('CMakeLists.txt')
    ctx.require(f'add_executable({d["prog"]}' in cm, 'add_executable は残します。')
    pos = [cm.find('find_package(PkgConfig'), cm.find('pkg_check_modules('), cm.find(f'target_link_libraries({d["prog"]}')]
    ctx.require(all(p >= 0 for p in pos) and pos == sorted(pos), 'find_package(PkgConfig) → pkg_check_modules → target_link_libraries の順に書きます。')
    ctx.require(re.search(r'pkg_check_modules\([^)]*\b' + d['lib'] + r'\b', cm) is not None, f'pkg_check_modules に {d["lib"]} を指定します。')
    ls = [x.strip() for x in ctx.need_file('build.sh').splitlines() if x.strip() and not x.strip().startswith('#')]
    ok1 = any(tk(l)[:1] == ['cmake'] and '-B' in tk(l) and tk(l)[tk(l).index('-B') + 1] == 'build' for l in ls)
    ok2 = 'cmake ..' in ls and any(l.startswith('cd build') for l in ls)
    ctx.require(ok1 or ok2, 'ビルドディレクトリを分けて（-B build か cd build; cmake ..）構成します。')
    ctx.require('cmake .' not in ls, 'ソースの中で cmake . は実行しません（out-of-source）。')
    ctx.require(any(l.startswith('cmake --build') or l == 'make' for l in ls), 'ビルドを実行する行も書きます（cmake --build build）。')


SOL14 = """echo "<<flags>>" > flags.txt
cat >> CMakeLists.txt <<'EOF'
find_package(PkgConfig REQUIRED)
pkg_check_modules(DEPS REQUIRED IMPORTED_TARGET <<lib>>)
target_link_libraries(<<prog>> PRIVATE PkgConfig::DEPS)
EOF
printf '%s\\n' 'cmake -S . -B build' 'cmake --build build' > build.sh"""
mission(14, 'CMakeLists.txtとout-of-source build・pkg-config',
        'C言語のプロジェクトを CMake に移行中です。外部ライブラリは pkg-config の .pc ファイル経由で探し、ビルド生成物でソースを汚さない out-of-source build にします。',
        ['flags.txtとCMakeLists.txtを書く', 'build.shを書く'], s14, c14, SOL14,
        ["echo '-l<<lib>>' > flags.txt\necho 'cmake .' > build.sh", "echo '<<flags>>' > flags.txt\nprintf '%s\\n' 'cmake .' 'make' > build.sh"],
        'CMakeLists.txt が設計図で、cmake -S ソース -B build が構成（生成物は build 側のみ）、cmake --build build が実際のビルドです。pkg-config は .pc を読み、--cflags は -I（ヘッダの場所）、--libs は -L と -l（ライブラリ）を返し、PKG_CONFIG_PATH で探索先を足せます。CMakeでは find_package(PkgConfig) と pkg_check_modules で同じ情報を使います。',
        '.pc の変数は prefix から展開します。', 'cat >> で既存の設定の後ろに追記します。')


# ------------------------------------------------------------ 15 gdb / core dump
def s15(ctx):
    f = R.choice(['list_append', 'node_free', 'read_item'])
    p = R.choice(['node', 'cur', 'head'])
    mid = R.choice(['process', 'walk', 'handle'])
    src = R.choice(['list.c', 'queue.c'])
    l1, l2, l3 = R.randrange(10, 50), R.randrange(50, 90), R.randrange(90, 130)
    exe = R.choice(['server', 'worker'])
    h = lambda: '0x0000%012x' % R.randrange(1 << 40)
    cnt = R.randrange(2, 9)
    put(ctx, 'gdb.log', f'''Program received signal SIGSEGV, Segmentation fault.
{h()} in {f} ({p}=0x0) at {src}:{l1}
{l1}\t    return {p}->value;
(gdb) bt
#0  {f} ({p}=0x0) at {src}:{l1}
#1  {h()} in {mid} (n={cnt}) at {src}:{l2}
#2  {h()} in main () at main.c:{l3}
(gdb) print {p}
$1 = (struct node *) 0x0
(gdb) print n
$2 = {cnt}
''')
    pids = [R.randrange(1000, 9000) for _ in range(5)]
    path = f'/home/trainee/bin/{exe}'
    rows = [('Tue 2026-11-17 09:12:01 JST', pids[0], 'SIGABRT', 'present', '/usr/bin/other'),
            ('Tue 2026-11-17 11:40:22 JST', pids[1], 'SIGSEGV', 'present', path),
            ('Wed 2026-11-18 08:01:09 JST', pids[2], 'SIGSEGV', 'missing', path),
            ('Wed 2026-11-18 15:33:45 JST', pids[3], 'SIGSEGV', 'present', path),
            ('Thu 2026-11-19 10:00:13 JST', pids[4], 'SIGTERM', 'present', path)]
    put(ctx, 'coredumps.txt', 'TIME                            PID  UID  GID SIG     COREFILE EXE\n' + ''.join(f'{t} {a} 1000 1000 {s} {c} {e}\n' for t, a, s, c, e in rows))
    ctx.data.update(f=f, p=p, mid=mid, src=src, l1=l1, pid=pids[3], exe=exe)
    req(ctx, f'gdb.log（gdb の bt・print の出力）から answer.json に crash_function・crash_file・crash_line・caller（#1 の関数）・null_var（NULLの引数名）・pid を書く。pid は coredumps.txt（coredumpctl list の出力）で {path} がSIGSEGVで落ち、コアが present の最新のもの。'
        'debug.sh には ulimit -c unlimited の次に coredumpctl gdb PID を、gdbcmds.txt には問題の関数への break（関数名または 行番号付き）・bt・print 引数名 を書く。')


def c15(ctx):
    need_ro(ctx)
    d = ctx.data
    a = rj(ctx, 'answer.json')
    exp = dict(crash_function=d['f'], crash_file=d['src'], crash_line=d['l1'], caller=d['mid'], null_var=d['p'], pid=d['pid'])
    for k, v in exp.items():
        ctx.require(a.get(k) == v, f'answer.json の {k} が違います。')
    seq(ctx, 'debug.sh', [(lambda l: tk(l) == ['ulimit', '-c', 'unlimited'], 'ulimit -c unlimited'),
                          (lambda l: tk(l) == ['coredumpctl', 'gdb', str(d['pid'])], 'coredumpctl gdb PID')])
    seq(ctx, 'gdbcmds.txt', [(lambda l: tk(l)[:1] == ['break'] and tk(l)[1:2] and tk(l)[1] in (d['f'], f'{d["src"]}:{d["l1"]}'), 'break 関数名 か ファイル:行'),
                             (lambda l: tk(l) == ['bt'], 'bt'), (lambda l: tk(l) == ['print', d['p']], 'print 引数名')])


SOL15 = """python3 - <<'PY'
import json, re
g = open('gdb.log').read(); c = open('coredumps.txt').read().splitlines()[1:]
f, p, src, l1 = re.search(r'#0  (\\w+) \\((\\w+)=0x0\\) at ([\\w.]+):(\\d+)', g).groups()
mid = re.search(r'#1  \\S+ in (\\w+)', g).group(1)
pid = [int(m.group(1)) for l in c for m in [re.search(r' (\\d+) 1000 1000 SIGSEGV present\\s+(\\S*<<exe>>)$', l)] if m][-1]
json.dump({'crash_function': f, 'crash_file': src, 'crash_line': int(l1), 'caller': mid, 'null_var': p, 'pid': pid}, open('answer.json', 'w'))
open('debug.sh', 'w').write('ulimit -c unlimited\\ncoredumpctl gdb %d\\n' % pid)
open('gdbcmds.txt', 'w').write('break %s\\nbt\\nprint %s\\n' % (f, p))
PY"""
mission(15, 'gdb（bt・break・print）とcore dump（ulimit -c・coredumpctl）',
        '本番で落ちたプロセスのコアダンプを解析します。コアを残すには ulimit -c、systemd環境では coredumpctl で一覧と gdb 起動ができ、gdb では bt（呼び出し履歴）・break（停止位置）・print（変数）を使います。',
        ['answer.jsonに診断を書く', 'debug.shとgdbcmds.txtを書く'], s15, c15, SOL15,
        ['echo \'{"crash_function": "main"}\' > answer.json\necho "ulimit -c 0" > debug.sh', "echo '{}' > answer.json\nprintf 'ulimit -c unlimited\\ncoredumpctl gdb 1\\n' > debug.sh"],
        'ulimit -c unlimited で現在のシェルから起動するプロセスのコア制限を外します（既定は0）。systemdのシステムでは coredumpctl list で記録を見て、coredumpctl gdb PID で直接gdbを開きます。gdbの bt は #0 が落ちた場所、#1 以降が呼び出し元で、print 変数 で値（0x0はNULL）を確認し、break 関数 または break ファイル:行 で再現時に止めます。',
        'COREFILEがmissingのものは解析できません。', 'coredumpsはSIGとCOREFILEの両方で絞ります。')


# ------------------------------------------------------------ 16 valgrind
def s16(ctx):
    fn = R.choice(['load_config', 'read_table', 'build_index'])
    n1, b1 = R.randrange(2, 5), R.choice([16, 32, 64])
    lost = n1 * b1
    ln = R.randrange(10, 40)
    other = R.choice([24, 40])
    put(ctx, 'valgrind.log', f'''==1234== HEAP SUMMARY:
==1234==     in use at exit: {lost + other} bytes in {n1 + 1} blocks
==1234== {lost} bytes in {n1} blocks are definitely lost in loss record 2 of 2
==1234==    at 0x4C2FB0F: malloc (vg_replace_malloc.c:381)
==1234==    by 0x1091A6: {fn} (config.c:{ln})
==1234==    by 0x1092B0: main (main.c:12)
==1234== {other} bytes in 1 blocks are still reachable in loss record 1 of 2
==1234== LEAK SUMMARY:
==1234==    definitely lost: {lost} bytes in {n1} blocks
==1234==    still reachable: {other} bytes in 1 blocks
''')
    ctx.write('config.c', f'#include <stdlib.h>\n#include <string.h>\n\nint {fn}(void) {{\n    char *buf = malloc({b1});\n    if (!buf) {{\n        return -1;\n    }}\n    memset(buf, 0, {b1});\n    return 0;\n}}\n')
    ctx.data.update(fn=fn, lost=lost, n1=n1, ln=ln)
    req(ctx, 'valgrind.log を読み、answer.json に definitely_lost_bytes・blocks・alloc_function・alloc_file・alloc_line（malloc を呼んだ行）を書く。'
        'config.c のリークを free で直す（正常終了の return の直前に）。確認コマンドを cmd.txt に1行で書く（valgrind --leak-check=full ./app）。')


def c16(ctx):
    need_ro(ctx)
    d = ctx.data
    a = rj(ctx, 'answer.json')
    exp = dict(definitely_lost_bytes=d['lost'], blocks=d['n1'], alloc_function=d['fn'], alloc_file='config.c', alloc_line=d['ln'])
    for k, v in exp.items():
        ctx.require(a.get(k) == v, f'answer.json の {k} が違います（definitely lost の loss record を読みます）。')
    c = ctx.need_file('config.c')
    ctx.require('malloc(' in c and re.search(r'free\(buf\);\s*\n\s*return 0;', c) is not None, '正常終了の return 0 の直前に free(buf); を入れます。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'valgrind' and '--leak-check=full' in t and t[-1] == './app', 'valgrind --leak-check=full ./app にします。')


SOL16 = """echo '{"definitely_lost_bytes": <<lost>>, "blocks": <<n1>>, "alloc_function": "<<fn>>", "alloc_file": "config.c", "alloc_line": <<ln>>}' > answer.json
sed -i 's/^    return 0;/    free(buf);\\n    return 0;/' config.c
echo "valgrind --leak-check=full ./app" > cmd.txt"""
mission(16, 'valgrindのメモリリーク出力を読む',
        'サービスのメモリが増え続けます。valgrind の出力から、本当に失われたメモリ（definitely lost）を確認し、malloc の呼び出し位置までスタックをたどって修正します。',
        ['answer.jsonにリークの要約を書く', 'config.cを直しcmd.txtを書く'], s16, c16, SOL16,
        ['echo \'{}\' > answer.json\necho "valgrind ./app" > cmd.txt', "sed -i 's/^    return 0;\\n}/x/' config.c\necho '{}' > answer.json"],
        'valgrind の definitely lost は参照が失われた確実なリーク、still reachable は終了時もポインタが残っている（多くは害が小さい）ものです。loss record のスタック（at malloc → by 関数 (ファイル:行)）の上から2行目が確保した場所です。--leak-check=full で詳細を出し、-g 付きでビルドすると行番号が出ます。',
        'definitely lostとstill reachableを区別します。', 'logから数値と関数名を拾い、freeを追加します。')


# ------------------------------------------------------------ 17 strace / ltrace / perf
def s17(ctx):
    pa = R.choice(['/etc/app/config.yml', '/var/lib/app/state.db', '/opt/app/license.key'])
    sym = [('a', '起動直後に設定ファイルが見つからず終了する。どのシステムコールが何のエラーで失敗したかを知りたい', 'strace'),
           ('b', 'ライブラリ関数（malloc や strlen など）の呼び出し回数と引数を調べたい', 'ltrace'),
           ('c', 'CPU使用率が高い。どの関数が時間を消費しているかをサンプリングで知りたい', 'perf')]
    R.shuffle(sym)
    put(ctx, 'symptoms.txt', ''.join(f'{k}: {t}\n' for k, t, _ in sym))
    put(ctx, 'strace.log', f'execve("./app", ["./app"], 0x7ffd) = 0\nopenat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3\nopenat(AT_FDCWD, "{pa}", O_RDONLY) = -1 ENOENT (No such file or directory)\nwrite(2, "config not found\\n", 17) = 17\nexit_group(1) = ?\n')
    ctx.data['tools_json'] = json.dumps({k: tl for k, _, tl in sorted(sym)})
    ctx.data['pa'] = pa
    req(ctx, 'symptoms.txt の3つの症状a・b・cに最適なツール（strace・ltrace・perf）を tools.json の {"a": ..} に書く。strace.log から失敗した open のパスを missing_path、エラー名を errno として answer.json に書く。'
        'さらに ./app を子プロセスも含め（-f）openat だけを trace.log に記録する strace のコマンドを cmd.txt に1行で書く。')


def c17(ctx):
    need_ro(ctx)
    ctx.require(rj(ctx, 'tools.json') == json.loads(ctx.data['tools_json']), 'tools.json: 症状とツール（システムコール=strace、ライブラリ呼び出し=ltrace、CPU消費=perf）の対応を見直します。')
    a = rj(ctx, 'answer.json')
    ctx.require(a.get('missing_path') == ctx.data['pa'] and a.get('errno') == 'ENOENT', 'answer.json: -1 ENOENT で失敗した openat のパスを書きます。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'strace' and '-f' in t and t[-1] == './app', 'strace ... ./app の形で書きます。')
    ctx.require(any(x in ('trace=openat', 'trace=open,openat') or x.endswith('trace=openat') for x in t) or ('-e' in t and t[t.index('-e') + 1] == 'trace=openat'), '-e trace=openat で絞ります。')
    ctx.require('-o' in t and t[t.index('-o') + 1] == 'trace.log', '-o trace.log に保存します。')


SOL17 = """echo '<<tools_json>>' > tools.json
echo '{"missing_path": "<<pa>>", "errno": "ENOENT"}' > answer.json
echo "strace -f -e trace=openat -o trace.log ./app" > cmd.txt"""
mission(17, 'strace・ltrace・perfの使い分け',
        '原因不明の不具合が3種類あります。システムコールを見る strace、ライブラリ関数呼び出しを見る ltrace、CPU時間のサンプリングをする perf のどれが適切かを選び、strace の出力を読んで原因を特定します。',
        ['tools.jsonに症状別のツールを書く', 'answer.jsonとcmd.txtを書く'], s17, c17, SOL17,
        ['echo \'{"a": "perf", "b": "strace", "c": "ltrace"}\' > tools.json\necho "strace ./app" > cmd.txt', "echo '{}' > tools.json"],
        'strace はカーネルとのやり取り（システムコール）、ltrace は共有ライブラリの関数呼び出し、perf（perf top / perf record）はCPUサンプリングでホットスポットを見ます。strace の -f は子プロセスも、-e trace=openat で種類を絞り、-o でファイルに保存します。-1 ENOENT (No such file or directory) は「パスが存在しない」を意味します。',
        '「どの層」を見たいかで選びます。', 'tools.jsonのキーはa・b・cです。')


# ------------------------------------------------------------ 18 pre-commit etc.
def s18(ctx):
    t = R.choice([('feat', '新しいオプション --dry-run を追加'), ('fix', 'null参照で落ちるバグを修正'), ('docs', 'README の手順を更新')])
    sc = R.choice(['parser', 'api', 'cli'])
    revs = [f'v{R.randrange(3, 6)}.{R.randrange(10)}.0', f'v0.{R.randrange(8, 11)}.{R.randrange(3)}', f'v3.{R.randrange(5, 9)}.{R.randrange(5)}-1']
    ctx.data.update(typ=t[0], scope=sc, r0=revs[0], r1=revs[1], r2=revs[2])
    ctx.write('.pre-commit-config.yaml', 'repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n    rev: ' + revs[0] + '\n    hooks:\n      - id: trailing-whitespace\n')
    put(ctx, 'diff.txt', f' src/{sc}/main.c | 4 ++--\n 1 file changed\n変更内容: {t[1]}\n')
    ctx.write('deploy.sh', '#!/bin/bash\nset -eu\nmkdir -p "$DEST_DIR"\ncp $SRC $DEST_DIR/\n')
    put(ctx, 'shellcheck.log', 'In deploy.sh line 4:\ncp $SRC $DEST_DIR/\n   ^--^ SC2086 (info): Double quote to prevent globbing and word splitting.\n   ^------^ SC2086 (info): Double quote to prevent globbing and word splitting.\n')
    req(ctx, f'.pre-commit-config.yaml に end-of-file-fixer を既存リポジトリ（rev {revs[0]}）の hooks に追加し、shellcheck（https://github.com/koalaman/shellcheck-precommit、rev {revs[1]}）と shfmt（https://github.com/scop/pre-commit-shfmt、rev {revs[2]}）のリポジトリ・hook を足す（rev は固定）。'
        'shellcheck.log の指摘（SC2086）を deploy.sh で直す。hooks.sh に pre-commit install・pre-commit run --all-files・shellcheck deploy.sh・shfmt -d deploy.sh をこの順で書く。'
        'diff.txt の変更に Conventional Commits 形式（種別(範囲): 要約、72文字以内、末尾にピリオドなし）のコミットメッセージを commit_msg.txt の1行目に書く。')


def c18(ctx):
    need_ro(ctx)
    d = ctx.data
    repos = []
    for l in ctx.need_file('.pre-commit-config.yaml').splitlines():
        m = re.match(r'\s*- repo:\s*(\S+)', l)
        if m:
            repos.append({'url': m.group(1), 'rev': None, 'ids': []})
        m = re.match(r'\s*rev:\s*(\S+)', l)
        if m and repos:
            repos[-1]['rev'] = m.group(1)
        m = re.match(r'\s*- id:\s*(\S+)', l)
        if m and repos:
            repos[-1]['ids'].append(m.group(1))
    ctx.require(all(r['rev'] and re.match(r'v?\d', r['rev']) for r in repos), '各リポジトリの rev は main/master ではなく版番号で固定します。')
    by = {i: r for r in repos for i in r['ids']}
    ctx.require('pre-commit-hooks' in by.get('trailing-whitespace', {}).get('url', '') and by['trailing-whitespace']['rev'] == d['r0'], '既存の hook と rev は残します。')
    ctx.require(by.get('end-of-file-fixer', {}).get('url') == by.get('trailing-whitespace', {}).get('url'), 'end-of-file-fixer は pre-commit-hooks リポジトリの hooks に追加します。')
    ctx.require('shellcheck' in by.get('shellcheck', {}).get('url', '') and by['shellcheck']['rev'] == d['r1'], 'shellcheck-precommit の shellcheck hook を指定の rev で追加します。')
    ctx.require('shfmt' in by.get('shfmt', {}).get('url', '') and by['shfmt']['rev'] == d['r2'], 'pre-commit-shfmt の shfmt hook を指定の rev で追加します。')
    sd = ctx.need_file('deploy.sh')
    ctx.require(not re.search(r'(?<!")\$SRC\b', sd) and not re.search(r'(?<!")\$DEST_DIR/?(?!")(?=\s|$)', sd.split('mkdir')[1].split('\n', 1)[1]), 'SC2086: 変数展開は "$SRC" のように二重引用符で囲みます。')
    os.makedirs(ctx.p('t18/out'), exist_ok=True)
    ctx.write('t18/a b.txt', 'x')
    r = run(ctx, ['bash', 'deploy.sh'], env={'SRC': str(ctx.p('t18/a b.txt')), 'DEST_DIR': str(ctx.p('t18/out'))})
    ctx.require(r.returncode == 0 and ctx.exists('t18/out/a b.txt'), '空白を含むパスでも deploy.sh が動くようにします。')
    seq(ctx, 'hooks.sh', [(lambda l: tk(l) == ['pre-commit', 'install'], 'pre-commit install'), (lambda l: tk(l) == ['pre-commit', 'run', '--all-files'], 'pre-commit run --all-files'),
                          (lambda l: tk(l) == ['shellcheck', 'deploy.sh'], 'shellcheck deploy.sh'), (lambda l: tk(l) == ['shfmt', '-d', 'deploy.sh'], 'shfmt -d deploy.sh')])
    first = ctx.need_file('commit_msg.txt').splitlines()[:1]
    ctx.require(bool(first) and re.fullmatch(rf'{d["typ"]}\({d["scope"]}\): [^\s.].*[^.\s]', first[0]) is not None and len(first[0]) <= 72,
                f'1行目は「{d["typ"]}({d["scope"]}): 要約」の形、72文字以内、末尾ピリオドなしにします。')


SOL18 = """cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: <<r0>>
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
  - repo: https://github.com/koalaman/shellcheck-precommit
    rev: <<r1>>
    hooks:
      - id: shellcheck
  - repo: https://github.com/scop/pre-commit-shfmt
    rev: <<r2>>
    hooks:
      - id: shfmt
EOF
sed -i 's|^cp .*|cp "$SRC" "$DEST_DIR/"|' deploy.sh
printf '%s\\n' 'pre-commit install' 'pre-commit run --all-files' 'shellcheck deploy.sh' 'shfmt -d deploy.sh' > hooks.sh
echo '<<typ>>(<<scope>>): update behavior' > commit_msg.txt"""
mission(18, 'pre-commit・shellcheck・shfmtとコミット規約',
        'コミット前に自動で品質を検査する品質ゲートを導入します。.pre-commit-config.yaml でフックを宣言し、シェルスクリプトには shellcheck（静的解析）と shfmt（整形）を使い、コミットメッセージは Conventional Commits の規約に揃えます。',
        ['.pre-commit-config.yamlを仕様どおり書く', 'deploy.shとhooks.shを直す', 'commit_msg.txtを書く'], s18, c18, SOL18,
        ["sed -i 's|^cp .*|cp \"$SRC\" \"$DEST_DIR/\"|' deploy.sh\necho 'fix: stuff.' > commit_msg.txt", "printf '%s\\n' 'pre-commit install' > hooks.sh"],
        'pre-commit は .pre-commit-config.yaml の repo・rev（固定版）・hooks（id）を取得し、git commit 時に変更ファイルへ実行します。shellcheck は SC2086 のような品質問題を指摘し、shfmt -d は整形の差分を出します。コミットメッセージの規約（feat/fix/docs…(範囲): 要約）はリリースノートや SemVer の判断に使えます。',
        'revは必ず版番号で固定します。', 'YAMLはheredocで全文を書きます。')


# ------------------------------------------------------------ 19 editorconfig / encoding / CRLF
def s19(ctx):
    tok = secrets_hex()
    for n, body in (('run.sh', f'#!/bin/bash\necho start {tok}\n'), ('tool.py', f'print("{tok}")\n')):
        ctx.write('src/' + n, body.replace('\n', '\r\n'), binary=False) if False else ctx.write('src/' + n, body.replace('\n', '\r\n').encode(), binary=True)
    txt = f'データ移行手順メモ {tok}\n確認済み\n'
    b = txt.encode('shift_jis')
    ctx.write('notes_sjis.txt', b, binary=True)
    ctx.data.update(tok=tok, notes=txt, nh=hashlib.sha256(b).hexdigest())
    req(ctx, 'Windows由来のファイルを整える。src/run.sh と src/tool.py を CRLF から LF に直す（dos2unix または sed）。notes_sjis.txt（Shift_JIS）を iconv で UTF-8 にして notes.txt に保存（原本は残す）。'
        '.editorconfig（root = true。[*] に charset = utf-8・end_of_line = lf・insert_final_newline = true・trim_trailing_whitespace = true、[*.py] に indent_style = space と indent_size = 4、[Makefile] に indent_style = tab）も作る。')


def secrets_hex():
    return '%06x' % R.randrange(1 << 24)


def c19(ctx):
    d = ctx.data
    nb = ctx.p('notes_sjis.txt').read_bytes() if ctx.exists('notes_sjis.txt') else b''
    ctx.require(hashlib.sha256(nb).hexdigest() == d['nh'], 'notes_sjis.txt の原本は変更しません。')
    for n, exp in (('run.sh', f'#!/bin/bash\necho start {d["tok"]}\n'), ('tool.py', f'print("{d["tok"]}")\n')):
        b = ctx.p('src/' + n).read_bytes() if ctx.exists('src/' + n) else b''
        ctx.require(b'\r' not in b, f'src/{n} にCRが残っています。')
        ctx.require(b.decode() == exp, f'src/{n} の内容は変えず改行だけをLFにします。')
    ctx.require(ctx.need_file('notes.txt') == d['notes'], 'notes.txt は notes_sjis.txt をUTF-8に変換した内容にします。')
    sec, cur = {}, None
    for l in ctx.need_file('.editorconfig').splitlines():
        l = l.strip()
        if not l or l[0] in '#;':
            continue
        m = re.fullmatch(r'\[(.+)\]', l)
        if m:
            cur = m.group(1)
            sec[cur] = {}
            continue
        if '=' in l:
            k, v = [x.strip().lower() for x in l.split('=', 1)]
            sec.setdefault(cur, {})[k] = v
    ctx.require(sec.get(None, {}).get('root') == 'true', 'セクションより前に root = true を書きます。')
    ctx.require(all(sec.get('*', {}).get(k) == v for k, v in (('charset', 'utf-8'), ('end_of_line', 'lf'), ('insert_final_newline', 'true'), ('trim_trailing_whitespace', 'true'))), '[*] の4つの設定を書きます。')
    ctx.require(any('py' in s and v.get('indent_style') == 'space' and v.get('indent_size') == '4' for s, v in sec.items() if s), '[*.py] に indent_style = space と indent_size = 4 を書きます。')
    ctx.require(sec.get('Makefile', {}).get('indent_style') == 'tab', '[Makefile] に indent_style = tab を書きます。')


SOL19 = """sed -i 's/\\r$//' src/run.sh src/tool.py
iconv -f SHIFT_JIS -t UTF-8 notes_sjis.txt > notes.txt
cat > .editorconfig <<'EOF'
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[Makefile]
indent_style = tab
EOF"""
mission(19, 'EditorConfigと文字コード・改行（LF/CRLF・dos2unix）',
        'WindowsとLinuxの混在チームで、シェルスクリプトが ^M のエラーで動かず、メモが文字化けします。改行コード（CRLF と LF）と文字コード（Shift_JIS と UTF-8）を揃え、EditorConfig でエディタの設定を共有します。',
        ['src配下の改行をLFにする', 'notes.txtをUTF-8で作る', '.editorconfigを書く'], s19, c19, SOL19,
        ["sed -i 's/\\r$//' src/run.sh\niconv -f SHIFT_JIS -t UTF-8 notes_sjis.txt > notes.txt", "iconv -f SHIFT_JIS -t UTF-8 notes_sjis.txt > notes_sjis.txt\nsed -i 's/\\r$//' src/run.sh src/tool.py"],
        'CRLF（\\r\\n）のスクリプトは "bad interpreter: /bin/bash^M" で動きません。dos2unix（または sed -i \'s/\\r$//\'）でLFにします。file コマンドは文字コードと改行の種類を推定します。iconv -f 元 -t 先 で変換しますが、入力と同じファイルへのリダイレクトは内容が消えるため別名で保存します。.editorconfig は多くのエディタが自動で読み、charset・end_of_line・インデントの規則をチームで共有します。',
        '改行コードと文字コードは別の問題です。', 'sed -i と iconv、heredocを組み合わせます。')


# ------------------------------------------------------------ 20 Docker multi-stage / devcontainer / asdf / mise
def s20(ctx):
    rt = R.choice(['alpine:3.19', 'debian:bookworm-slim', 'gcr.io/distroless/static-debian12'])
    port = R.randrange(3000, 9000)
    app = R.choice(['api', 'gateway', 'worker'])
    gv, nv = f'1.22.{R.randrange(5)}', f'20.{R.randrange(5, 12)}.{R.randrange(5)}'
    ctx.data.update(rt=rt, port=port, app=app, gv=gv, nv=nv)
    ctx.write('Dockerfile', f'FROM golang:1.22\nWORKDIR /src\nCOPY . .\nRUN go build -o /out/{app} .\nEXPOSE {port}\nCMD ["/out/{app}"]\n')
    req(ctx, f'イメージが大きすぎる。Dockerfile をマルチステージにする: 1段目は golang:1.22 を AS build とし go build -o /out/{app} . まで、2段目は {rt} で COPY --from=build /out/{app} /usr/local/bin/{app} 、EXPOSE {port}、CMD ["{app}"]（2段目にビルドは含めない）。'
        f'.devcontainer/devcontainer.json（image は mcr.microsoft.com/devcontainers/go:1 、forwardPorts は [{port}]、postCreateCommand は go mod download）、'
        f'asdf 用の .tool-versions（golang {gv} と nodejs {nv}）、mise 用の mise.toml（[tools] に go = "{gv}"・node = "{nv}"）も作る。')


def c20(ctx):
    d = ctx.data
    stages = []
    for l in ctx.need_file('Dockerfile').splitlines():
        m = re.match(r'(?i)FROM\s+(\S+)(?:\s+AS\s+(\S+))?', l.strip())
        if m:
            stages.append([m.group(1), (m.group(2) or '').lower(), []])
        elif stages and l.strip():
            stages[-1][2].append(l.strip())
    ctx.require(len(stages) == 2, 'FROM は2つ（ビルド用と実行用）にします。')
    ctx.require(stages[0][0] == 'golang:1.22' and stages[0][1] == 'build', '1段目は FROM golang:1.22 AS build です。')
    ctx.require(any(re.search(r'RUN go build\b', x) and f'/out/{d["app"]}' in x for x in stages[0][2]), '1段目で go build を実行します。')
    ctx.require(stages[1][0] == d['rt'], f'2段目の基になるイメージは {d["rt"]} です。')
    s2l = stages[1][2]
    ctx.require(not any('go build' in x for x in s2l), '2段目にビルドは含めません。')
    ctx.require(any(f'COPY --from=build /out/{d["app"]} ' in x for x in s2l), '2段目で COPY --from=build 成果物 をコピーします。')
    ctx.require(any(x == f'EXPOSE {d["port"]}' for x in s2l) and any(x.startswith(('CMD', 'ENTRYPOINT')) for x in s2l), '2段目に EXPOSE と CMD を書きます。')
    j = rj(ctx, '.devcontainer/devcontainer.json')
    ctx.require(j.get('image') == 'mcr.microsoft.com/devcontainers/go:1' and j.get('forwardPorts') == [d['port']] and j.get('postCreateCommand') == 'go mod download', 'devcontainer.json の image・forwardPorts・postCreateCommand を指定どおりに書きます。')
    tv = {l.split()[0]: l.split()[1] for l in ctx.need_file('.tool-versions').splitlines() if len(l.split()) == 2}
    ctx.require(tv == {'golang': d['gv'], 'nodejs': d['nv']}, '.tool-versions に「ツール名 版」を1行ずつ書きます。')
    t = rtoml(ctx, 'mise.toml').get('tools', {})
    ctx.require(t.get('go') == d['gv'] and t.get('node') == d['nv'], 'mise.toml の [tools] に go と node を書きます。')


SOL20 = """cat > Dockerfile <<'EOF'
FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go build -o /out/<<app>> .

FROM <<rt>>
COPY --from=build /out/<<app>> /usr/local/bin/<<app>>
EXPOSE <<port>>
CMD ["<<app>>"]
EOF
mkdir -p .devcontainer
echo '{"image": "mcr.microsoft.com/devcontainers/go:1", "forwardPorts": [<<port>>], "postCreateCommand": "go mod download"}' > .devcontainer/devcontainer.json
printf 'golang <<gv>>\\nnodejs <<nv>>\\n' > .tool-versions
printf '[tools]\\ngo = "<<gv>>"\\nnode = "<<nv>>"\\n' > mise.toml"""
mission(20, 'Dockerfileのマルチステージ・devcontainer・asdf/mise',
        '開発環境と本番イメージの再現性を高めます。Dockerfile はビルド用と実行用の段を分けるマルチステージにし、VS Code の devcontainer で開発環境を共有し、言語の版は asdf や mise の設定ファイルで固定します。',
        ['Dockerfileをマルチステージにする', 'devcontainer・.tool-versions・mise.tomlを書く'], s20, c20, SOL20,
        ["sed -i 's/^FROM golang:1.22$/FROM golang:1.22 AS build/' Dockerfile", "printf 'golang <<gv>>\\n' > .tool-versions"],
        'マルチステージビルドは FROM ごとに段を分け、COPY --from=build で成果物だけを最終イメージへ運ぶため、コンパイラが含まれず小さく安全になります。devcontainer.json はコンテナを開発環境にする設定（image・forwardPorts・postCreateCommand）です。asdf は .tool-versions、mise は mise.toml（または .mise.toml）でツールの版を固定し、チームで同じ版を使えます。',
        '最終段にはビルドツールを持ち込みません。', '各設定ファイルの書式が違うことに注意し、heredocで書きます。')


# ------------------------------------------------------------ 21 semver / CHANGELOG
def s21(ctx):
    a, b, c = R.randrange(1, 4), R.randrange(2, 9), R.randrange(1, 9)
    kind = R.choice(['major', 'minor', 'patch'])
    adds = ['- 新しい --format オプションを追加']
    fixes = ['- 空入力でクラッシュする問題を修正']
    secs = ['### Fixed\n' + '\n'.join(fixes)]
    if kind in ('minor', 'major'):
        secs.insert(0, '### Added\n' + '\n'.join(adds))
    if kind == 'major':
        secs.append('### Removed\n- BREAKING: 旧 --legacy オプションを削除')
    cur = f'{a}.{b}.{c}'
    nxt = {'major': f'{a + 1}.0.0', 'minor': f'{a}.{b + 1}.0', 'patch': f'{a}.{b}.{c + 1}'}[kind]
    date = f'2026-11-{R.randrange(10, 20)}'
    put(ctx, 'VERSION', cur + '\n')
    ctx.write('CHANGELOG.md', '# Changelog\n\n## [Unreleased]\n' + '\n\n'.join(secs) + f'\n\n## [{cur}] - 2026-10-01\n### Fixed\n- 起動時のログ出力を修正\n')
    ctx.data.update(nxt=nxt, date=date, kind=kind, cur=cur)
    ctx.data['bul'] = sorted(x for s in secs for x in s.splitlines() if x.startswith('- '))
    req(ctx, f'現在の版は VERSION のとおり。セマンティックバージョニング（破壊的変更は MAJOR、後方互換の機能追加は MINOR、後方互換のバグ修正は PATCH）で次の版を決め next_version.txt に書く。'
        f'CHANGELOG.md は Keep a Changelog の流儀で、[Unreleased] を空にして、その内容を "## [次の版] - {date}" の見出しの下へ移す。リリースの注釈付きタグを作る git tag -a v次の版 -m メッセージ を tag.txt に1行で書く（実行はしない）。')


def c21(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('next_version.txt').strip() == d['nxt'], '次の版が違います。変更内容の種類（破壊的・機能追加・修正）を見直してください。')
    ls = ctx.need_file('CHANGELOG.md').splitlines()
    hd = [i for i, l in enumerate(ls) if l.startswith('## ')]
    ctx.require(len(hd) == 3 and ls[hd[0]] == '## [Unreleased]', '見出しは [Unreleased]・新しい版・旧版の順に3つです。')
    ctx.require(not any(l.startswith('- ') for l in ls[hd[0]:hd[1]]), '[Unreleased] は空にします。')
    ctx.require(ls[hd[1]] == f'## [{d["nxt"]}] - {d["date"]}', f'見出しは "## [{d["nxt"]}] - {d["date"]}" にします。')
    ctx.require(sorted(l for l in ls[hd[1]:hd[2]] if l.startswith('- ')) == d['bul'], '未リリースの項目を全て新しい版の下に移します（消さない）。')
    ctx.require(f'## [{d["cur"]}]' in ls[hd[2]], '旧版の記録は残します。')
    t = toks(ctx, one_line(ctx, 'tag.txt'))
    ctx.require(t[:3] == ['git', 'tag', '-a'] and t[3] == 'v' + d['nxt'] and '-m' in t, f'git tag -a v{d["nxt"]} -m "メッセージ" の形にします。')


SOL21 = """python3 - <<'PY'
a, b, c = map(int, open('VERSION').read().strip().split('.'))
t = open('CHANGELOG.md').read()
head, rest = t.split('## [Unreleased]\\n', 1)
body, old = rest.split('\\n## [', 1)
n = (a + 1, 0, 0) if 'BREAKING' in body else (a, b + 1, 0) if '### Added' in body else (a, b, c + 1)
v = '.'.join(map(str, n))
open('next_version.txt', 'w').write(v + '\\n')
open('CHANGELOG.md', 'w').write(head + '## [Unreleased]\\n\\n## [' + v + '] - <<date>>\\n' + body.strip('\\n') + '\\n\\n## [' + old)
open('tag.txt', 'w').write('git tag -a v%s -m "Release %s"\\n' % (v, v))
PY"""
mission(21, 'セマンティックバージョニングとCHANGELOG',
        'リリース担当になりました。未リリースの変更一覧（CHANGELOG の Unreleased）から、セマンティックバージョニング（SemVer）に従って次の版番号を決め、CHANGELOG を整理してタグを用意します。',
        ['next_version.txtを書く', 'CHANGELOG.mdを整理する', 'tag.txtを書く'], s21, c21, SOL21,
        ["echo 99.0.0 > next_version.txt", "python3 -c \"import re;v=open('VERSION').read().split('.');print('%s.%s.%d'%(v[0],v[1],int(v[2])+1))\" > next_version.txt"],
        'SemVer は MAJOR.MINOR.PATCH で、互換性を壊す変更なら MAJOR を上げ（MINOR・PATCH は0に）、互換性を保つ機能追加は MINOR（PATCHは0）、バグ修正のみは PATCH を上げます。CHANGELOG は人が読む変更履歴で、Added・Changed・Fixed・Removed に分け、[Unreleased] で次回リリース分を溜めます。注釈付きタグ（git tag -a）でその時点を固定します。',
        '最も影響の大きい変更で上げる桁が決まります。', 'pythonで版を計算し、CHANGELOGを組み替えます。')


# ------------------------------------------------------------ 22 env / 12-factor / structured logs
def s22(ctx):
    sec = 'pw-' + secrets_hex() + secrets_hex()
    ctx.data['sec'] = sec
    put(ctx, '.env', f'APP_DB_PASSWORD={sec}\nAPP_DB_USER=admin\nAPP_LOG_LEVEL=info\n')
    ctx.write('app.py', f'DB_PASSWORD = "{sec}"\nprint("connecting as admin with password " + DB_PASSWORD)\n')
    req(ctx, '設定とログを 12-factor app に沿って直す。アプリのコードはパスワードを環境変数 APP_DB_PASSWORD から取得（未設定なら終了コード非0で失敗）、ユーザーは APP_DB_USER（既定 admin）。ログはパスワードを含めず、標準出力へ構造化ログ（level と event を含む1行のJSON）で出す。'
        '秘密を含む環境設定ファイルは .gitignore に記録してコミットしない。共有用の見本 .env.example を作り、元ファイルと同じキーを値を空にして書く（秘密を含む元ファイルは変更しない）。')


def c22(ctx):
    need_ro(ctx)
    sec = ctx.data['sec']
    ctx.require(sec not in ctx.need_file('app.py'), 'app.py に秘密の値を直書きしたままです。')
    probe = 'probe-' + secrets_hex()
    r = run(ctx, ['python3', '-B', 'app.py'], env={'APP_DB_PASSWORD': probe})
    ctx.require(r.returncode == 0 and r.stdout.strip(), 'APP_DB_PASSWORD を設定すると正常に動いてログを出す必要があります。')
    ctx.require(probe not in r.stdout + r.stderr, 'ログに秘密の値を出してはいけません。')
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1])
    except ValueError:
        ctx.fail('ログは1行のJSON（構造化ログ）で標準出力に出します。')
    ctx.require(isinstance(j, dict) and 'level' in j and 'event' in j, 'ログのJSONに level と event を含めます。')
    r2 = run(ctx, ['python3', '-B', 'app.py'])
    ctx.require(r2.returncode != 0, 'APP_DB_PASSWORD 未設定のときは失敗（非0終了）させます。')
    ctx.require(sec not in r2.stdout + r2.stderr, '失敗時にも秘密は出しません。')
    gi = [x.strip() for x in ctx.need_file('.gitignore').splitlines()]
    ctx.require('.env' in gi, '.gitignore に .env を書きます。')
    ex = {}
    for l in ctx.need_file('.env.example').splitlines():
        if '=' in l:
            k, v = l.split('=', 1)
            ex[k.strip()] = v.strip()
    ctx.require(ex == {'APP_DB_PASSWORD': '', 'APP_DB_USER': '', 'APP_LOG_LEVEL': ''}, '.env.example は .env と同じキーで値を空にします。')


SOL22 = """cat > app.py <<'EOF'
import json
import os
import sys
import time

try:
    password = os.environ["APP_DB_PASSWORD"]
except KeyError:
    sys.exit("APP_DB_PASSWORD is required")
user = os.environ.get("APP_DB_USER", "admin")
print(json.dumps({"ts": time.time(), "level": "info", "event": "db_connect", "user": user, "password_len": len(password)}))
EOF
echo ".env" > .gitignore
sed 's/=.*/=/' .env > .env.example"""
mission(22, '環境変数・.env・12-factor・構造化ログ',
        '設定にパスワードが直書きされ、ログにも出ています。12-factor app の考え方（設定は環境変数で、ログは標準出力へのイベントの流れとして出す）に直し、.env を誤ってコミットしない運用にします。',
        ['app.pyを環境変数と構造化ログに直す', '.gitignoreと.env.exampleを作る'], s22, c22, SOL22,
        ["echo '.env' > .gitignore\nsed 's/=.*/=/' .env > .env.example", "cp .env .env.example\necho '.env' > .gitignore"],
        '12-factor の「設定」の原則は、環境ごとに変わる値をコードから分け、環境変数で渡すことです。.env はローカル開発用の環境変数の置き場で、秘密を含むためコミットしない（.gitignore）、キーだけの .env.example をコミットして共有します。構造化ログ（1行1JSONで level・event などのフィールド）は集約・検索しやすく、秘密を出さない設計が必要です。必須設定が欠けたら起動時に失敗させます。',
        'コードに書いてよいのは設定名だけです。', 'os.environで読み、jsonで1行出力します。')
