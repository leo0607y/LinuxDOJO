"""Stage 32: 開発者ツールボックス（jq・curl・rg・fzf・監視/ネットワーク/変換ツール・dotfiles）。サンドボックス内の偽データと、使える本物のツールだけを使う。"""
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import zipfile

from engine.runner import register

S = 32
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・実ネットワークには触れず、rootも使いません。"
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
    return v


def cl(ctx, name):
    return [x.strip() for x in ctx.need_file(name).splitlines() if x.strip() and not x.strip().startswith('#')]


def tk(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません: ' + line)


def vals(t, *flags):
    return [t[i + 1] for i, x in enumerate(t[:-1]) if x in flags]


def nl(s):
    return re.sub(r'\s+', '', s)


def jqrun(ctx, args):
    if not shutil.which('jq'):
        return None
    return subprocess.run(['jq'] + args, cwd=ctx.work, capture_output=True, text=True, timeout=30)


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'32-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='道具は「何を入れて何が出るか」を先に決めると選べます。実行前に対象を確認し、結果を観測で検証しましょう。')


def rtxt(ctx, text):
    ctx.write('requirements.txt', text + '\n')


# ================================================================ 1 jq select/map
def s1(ctx):
    while True:
        mn = 100 * (1 + secrets.randbelow(5))
        orders = [{'id': 1000 + i, 'customer': secrets.choice(['sato', 'ito', 'kato', 'mori']),
                   'status': secrets.choice(['paid', 'pending', 'refunded']),
                   'total': 50 + secrets.randbelow(850)} for i in range(10)]
        hit = [o for o in orders if o['status'] == 'paid' and o['total'] >= mn]
        low = [o for o in orders if o['status'] == 'paid' and o['total'] < mn]
        if len(hit) >= 2 and low:
            break
    ctx.data['min'] = mn
    ctx.data['want'] = [{'id': o['id'], 'total': o['total']} for o in hit]
    put(ctx, 'orders.json', json.dumps({'orders': orders}, indent=1))
    rtxt(ctx, f'orders.json から status が "paid" で total が {mn} 以上の注文だけを、{{id,total}} だけ残した配列で出力する jq フィルタを filter.jq に保存する。select と map を使う。')


def c1(ctx):
    need_ro(ctx)
    f = ctx.need_file('filter.jq')
    ctx.require('select' in f and 'map' in f, 'filter.jq は map と select で絞り込みます。')
    r = jqrun(ctx, ['-c', '-f', 'filter.jq', 'orders.json'])
    if r is not None:
        ctx.require(r.returncode == 0, 'jq がエラーになりました: ' + r.stderr[:100])
        try:
            got = json.loads(r.stdout)
        except ValueError:
            ctx.fail('出力がJSONになっていません。')
        ctx.require(got == ctx.data['want'], '出力が期待と違います（条件・{id,total}への整形・配列かを確認）。')


mission(1, 'jqでmapとselectを使い注文を絞り込む',
        '売上JSONから支払済みの高額注文だけを取り出します。jq の基本は「.でたどり、select で行を絞り、map で配列の各要素を変換する」ことです。',
        ['filter.jq を作る', 'jq -f で期待の配列が出る'], s1, c1,
        "echo '.orders | map(select(.status==\"paid\" and .total >= <<min>>) | {id, total})' > filter.jq",
        ["echo '.orders | map(select(.status==\"paid\") | {id, total})' > filter.jq",
         "echo '.orders[] | select(.status==\"paid\" and .total >= <<min>>) | .id' > filter.jq"],
        'jq は map(f) が [.[]|f] の短縮形、select(cond) は条件が真のものだけ通します。-c で1行出力、-f でフィルタをファイルから読み、-r で文字列の引用符を外します。出力は必ず目で確認します。',
        '配列は .orders で取り出し、map の中で select と整形を組み合わせます。', 'map(select(条件) | {id, total}) の形です。')


# ================================================================ 2 jq group_by @csv
def s2(ctx):
    rg = ['east', 'north', 'south', 'west']
    rows = [{'region': rg[i % 4], 'rep': 'r' + str(i), 'amount': 100 + secrets.randbelow(900)} for i in range(12)]
    for i in range(secrets.randbelow(3)):
        rows.append({'region': 'north', 'rep': 'x' + str(i), 'amount': 50 + secrets.randbelow(100)})
    by = {}
    for r in rows:
        by.setdefault(r['region'], []).append(r['amount'])
    out = ['"region","total","count"'] + [f'"{k}",{sum(v)},{len(v)}' for k, v in sorted(by.items())]
    ctx.data['want'] = out
    put(ctx, 'sales.json', json.dumps(rows, indent=1))
    rtxt(ctx, 'sales.json（配列）を region ごとに集計し、見出し行 region,total,count 付きのCSVを report.csv に出す（地域名順、引用符つきの @csv 形式）。使ったフィルタは report.jq に保存する。group_by と @csv を使う。')


def c2(ctx):
    need_ro(ctx)
    f = ctx.need_file('report.jq')
    ctx.require('group_by' in f and '@csv' in f, 'report.jq は group_by と @csv を使います。')
    got = [x.strip() for x in ctx.need_file('report.csv').splitlines() if x.strip()]
    ctx.require(got == ctx.data['want'], 'report.csv が期待と違います。見出し・地域名順・合計と件数を確認してください。')


mission(2, 'jqのgroup_byと@csvで集計CSVを作る',
        '営業データを地域ごとに集計して、表計算に渡せるCSVにします。jq の group_by で同じキーをまとめ、@csv でCSV行に整形します。',
        ['report.jq を作る', 'report.csv を出力する'], s2, c2,
        """cat > report.jq <<'EOF'
["region","total","count"],
(group_by(.region)[] | [.[0].region, (map(.amount)|add), length])
| @csv
EOF
jq -r -f report.jq sales.json > report.csv""",
        ["jq -r '.[] | [.region,.amount] | @csv' sales.json > report.csv",
         """cat > report.jq <<'EOF'
group_by(.region)[] | [.[0].region, (map(.amount)|add), length] | @tsv
EOF
jq -r -f report.jq sales.json > report.csv"""],
        'group_by(.キー) は配列を「キーが同じ要素の配列」の配列にします。各グループの先頭から地域名、map(.amount)|add で合計、length で件数を取り、配列にして @csv に渡すと CSV 行になります。-r が無いと全体がJSON文字列になります。',
        'まずグループ化し、グループごとに [名前, 合計, 件数] の配列を作ります。', 'group_by(.region)[] | [...] を @csv へ。見出しは先頭に配列を足します。')


# ================================================================ 3 jq --arg
def s3(ctx):
    feats = ['search', 'beta_ui', 'export', 'audit']
    while True:
        fl = {k: secrets.choice([True, False]) for k in feats}
        if any(fl.values()) and not all(fl.values()):
            break
    env = 'prod-' + secrets.token_hex(2)
    cfg = {'service': 'shop-api', 'env': 'dev', 'replicas': 2 + secrets.randbelow(5), 'features': fl}
    ctx.data['envv'] = env
    ctx.data['want'] = {'service': 'shop-api', 'env': env, 'replicas': cfg['replicas'],
                        'features': [k for k, v in fl.items() if v]}
    put(ctx, 'config.json', json.dumps(cfg, indent=2))
    rtxt(ctx, f'config.json から deploy.json を作る。env を {env}（シェル変数のつもりで --arg env で渡す）に差し替え、features は「trueのものの名前だけの配列」に変換、他は維持。実行コマンドは cmd.sh に書き、sh cmd.sh で deploy.json を生成する。')


def c3(ctx):
    need_ro(ctx)
    t = ctx.need_file('cmd.sh')
    ctx.require('jq' in t and '--arg' in t, 'cmd.sh は jq の --arg で値を渡します（文字列連結で埋め込まない）。')
    ctx.require(rj(ctx, 'deploy.json') == ctx.data['want'], 'deploy.json が期待と違います。env の値と features の配列化を確認。')


mission(3, 'jqの--argとto_entriesで設定JSONを整形する',
        'デプロイ設定をJSON上で組み替えます。値は jq --arg で安全に渡し、オブジェクトは to_entries / map / select で配列へ組み替えます。複雑な整形も、小さな変換の連結です。',
        ['cmd.sh を作る', 'deploy.json を生成する'], s3, c3,
        """cat > cmd.sh <<'EOF'
jq --arg env '<<envv>>' '.env = $env | .features |= (to_entries | map(select(.value)) | map(.key))' config.json > deploy.json
EOF
sh cmd.sh""",
        ["""jq '.env = "<<envv>>"' config.json > deploy.json
echo "jq done" > cmd.sh""",
         """cat > cmd.sh <<'EOF'
jq '.env = "<<envv>>" | .features |= (to_entries | map(select(.value)) | map(.key))' config.json > deploy.json
EOF
sh cmd.sh"""],
        '--arg name 値 で $name に文字列が入ります。シェル変数を直接フィルタに埋め込むと引用符や記号で壊れる・注入されるので --arg（数値は --argjson）を使います。|= は「その場で更新」、to_entries は {key,value} の配列に分解します。',
        '更新は |= を使い、オブジェクトはto_entriesで配列にしてからselectします。', '--arg env 値 で渡し、features を to_entries|map(select(.value))|map(.key) にします。')


# ================================================================ 4 yq
def s4(ctx):
    old = f'1.{secrets.randbelow(5)}.{secrets.randbelow(9)}'
    tag = f'1.{5 + secrets.randbelow(4)}.{secrets.randbelow(9)}'
    rep = 4 + secrets.randbelow(6)
    lines = ['apiVersion: apps/v1', 'kind: Deployment', 'metadata:', '  name: shop-api', 'spec:', '  replicas: 2',
             '  template:', '    spec:', '      containers:', '        - name: app',
             f'          image: registry.local/shop-api:{old}', '        - name: log-agent',
             '          image: registry.local/log-agent:3.1']
    want = [x for x in lines]
    want[5] = f'  replicas: {rep}'
    want[10] = f'          image: registry.local/shop-api:{tag}'
    ctx.data.update(tag=tag, rep=rep, want=want)
    ctx.write('deployment.yaml', '\n'.join(lines) + '\n')
    rtxt(ctx, f'deployment.yaml の replicas を {rep}、app コンテナ（shop-api）のイメージタグを {tag} に更新する。log-agent サイドカーは変えない。yq が無い想定でテキスト編集（sed や python3）で直し、実機で使う yq のコマンドを1行 yq.txt に書く（-i で書き換え）。')


def c4(ctx):
    got = ctx.need_file('deployment.yaml').splitlines()
    ctx.require(got == ctx.data['want'], 'deployment.yaml の変更が期待と違います（replicas と app のタグだけを変える）。')
    ls = cl(ctx, 'yq.txt')
    ctx.require(len(ls) == 1, 'yq.txt は1行です。')
    t = tk(ctx, ls[0])
    ctx.require(t[0] == 'yq' and '-i' in t, 'yq -i で元ファイルを更新します。')
    s = ls[0]
    ctx.require('replicas' in s and str(ctx.data['rep']) in s and ctx.data['tag'] in s and 'deployment.yaml' in t, 'yq の式に replicas・新タグ・対象ファイルを入れます。')


mission(4, 'yqでk8sマニフェストを更新する（sed fallback）',
        'Kubernetesのマニフェストの更新は yq（YAML版のjq）の得意分野です。この環境に yq が無い場合は、構造を壊さないように行単位の編集（sed）や python3 で代替し、本来の yq コマンドは記録しておきます。',
        ['deployment.yaml を更新', 'yq.txt に yq -i の1行を書く'], s4, c4,
        """sed -i -e 's/^\\( *replicas:\\).*/\\1 <<rep>>/' -e 's#\\(image: registry.local/shop-api:\\).*#\\1<<tag>>#' deployment.yaml
echo "yq -i '.spec.replicas = <<rep>> | .spec.template.spec.containers[0].image = \\"registry.local/shop-api:<<tag>>\\"' deployment.yaml" > yq.txt""",
        ["""sed -i 's/^\\( *replicas:\\).*/\\1 <<rep>>/' deployment.yaml
echo "yq -i '.spec.replicas = <<rep>>' deployment.yaml" > yq.txt""",
         """sed -i -e 's/^\\( *replicas:\\).*/\\1 <<rep>>/' -e 's#image: .*#image: registry.local/shop-api:<<tag>>#' deployment.yaml
echo "yq -i '.spec.replicas = <<rep>> | .spec.template.spec.containers[0].image = \\"registry.local/shop-api:<<tag>>\\"' deployment.yaml" > yq.txt"""],
        'yq は .spec.replicas のようなパスで値を読み書きし、-i で上書きします（`yq -i`）。配列は containers[0] のように添字で指定します。yq が無い環境では、キーの位置を限定した sed か python3 で最小限だけ書き換え、差分を目視確認します。image: 全置換はサイドカーまで変えてしまいます。',
        '変えたいのは2行だけ。image: 行は2つあるので shop-api で絞ります。', 'sed -e で replicas 行と shop-api 行を別々に置換します。')


# ================================================================ 5 curl file://
def s5(ctx):
    ctx.write('site/index.html', f'<h1>{secrets.token_hex(4)}</h1>\n')
    ctx.write('site/data.json', json.dumps({'v': secrets.token_hex(4), 'n': secrets.randbelow(99)}) + '\n')
    ctx.data['h'] = {f: ctx.p('site/' + f).read_bytes().hex() for f in ('index.html', 'data.json')}
    rtxt(ctx, 'site/ の index.html と data.json を file:// URL で curl 取得し dl/ に保存する fetch.sh を書き、実行する。-o で保存先、-L でリダイレクト追従、--retry 3、-w で %{http_code} を codes.txt に追記（2行）。実ネットワークは使わない。')


def c5(ctx):
    t = ctx.need_file('fetch.sh')
    ctx.require(all(k in t for k in ('curl', '-o', '-L', '--retry', 'file://')) and '%{http_code}' in t, 'fetch.sh に curl・-o・-L・--retry・file://・-w %{http_code} が必要です。')
    for f, h in ctx.data['h'].items():
        ctx.require(os.path.isfile(ctx.p('dl/' + f)) and ctx.p('dl/' + f).read_bytes().hex() == h, f'dl/{f} が原本と一致しません。')
    ctx.require(len(ctx.need_file('codes.txt').split()) == 2, 'codes.txt にはリクエストごとのステータスを2行。')


mission(5, 'curlで-o -L --retry -wを使い取得を自動化する',
        'curl は取得の基本ツールです。-o で保存先、-L でリダイレクト追従、--retry で再試行、-w \'%{http_code}\' でステータスだけを取り出します。ここでは安全に file:// で練習します（file:// では http_code は 000 になる点も覚えておきましょう）。',
        ['fetch.sh を作って実行', 'dl/ に2ファイルと codes.txt'], s5, c5,
        """cat > fetch.sh <<'EOF'
mkdir -p dl
for f in index.html data.json; do
  curl -sS -L --retry 3 -o "dl/$f" -w '%{http_code}\\n' "file://$PWD/site/$f" >> codes.txt
done
EOF
sh fetch.sh""",
        ["""mkdir -p dl
for f in index.html data.json; do curl -s "file://$PWD/site/$f"; done > dl/all
echo 'curl -L --retry 3 -o x -w %{http_code} file://' > fetch.sh""",
         """cat > fetch.sh <<'EOF'
mkdir -p dl
for f in index.html data.json; do
  curl -sS -L -o "dl/$f" -w '%{http_code}\\n' "file://$PWD/site/$f" >> codes.txt
done
EOF
sh fetch.sh"""],
        '-o はファイル名指定、-O はURL末尾の名前で保存、-f はHTTPエラーで失敗扱い、-s は進捗を消し -S でエラーだけ表示します。--retry は一時的失敗のみ再試行します。ループ内で -w の値をファイルへ追記すると取得結果の記録になります。',
        'ループの中で curl を呼び、保存先はdl/$fです。', 'curl -sS -L --retry 3 -o dl/$f -w … file://$PWD/site/$f を for で回します。')


# ================================================================ 6 curl REST
def s6(ctx):
    d = dict(sku='SKU-' + secrets.token_hex(2), qty=1 + secrets.randbelow(9), rid=secrets.token_hex(4),
             user='api' + secrets.token_hex(1), pw=secrets.token_hex(4))
    ctx.data.update(d)
    rtxt(ctx, f'REST API（https://api.example.test/v1/orders、実際には送信しない）に注文を作る curl を cmd.txt に1行で書く。POSTで、JSON本文 {{"sku":"{d["sku"]}","qty":{d["qty"]}}}、Content-Type は JSON、X-Request-Id: {d["rid"]} ヘッダ、Basic認証（ユーザ {d["user"]} パスワード {d["pw"]}）。')


def c6(ctx):
    ls = cl(ctx, 'cmd.txt')
    ctx.require(len(ls) == 1, 'cmd.txt は1行です。')
    t = tk(ctx, ls[0])
    d = ctx.data
    ctx.require(t[0] == 'curl', 'curl コマンドです。')
    ctx.require('POST' in vals(t, '-X', '--request'), '-X POST を指定します。')
    hs = [nl(h).lower() for h in vals(t, '-H', '--header')]
    ctx.require('content-type:application/json' in hs, '-H で Content-Type: application/json を付けます。')
    ctx.require('x-request-id:' + d['rid'] in hs, 'X-Request-Id ヘッダを付けます。')
    ctx.require(f"{d['user']}:{d['pw']}" in vals(t, '-u', '--user'), 'Basic認証は -u ユーザ:パスワード です。')
    bodies = vals(t, '-d', '--data', '--data-raw')
    try:
        ok = len(bodies) == 1 and json.loads(bodies[0]) == {'sku': d['sku'], 'qty': d['qty']}
    except ValueError:
        ok = False
    ctx.require(ok, '-d の本文は {"sku":…,"qty":数値} のJSONです。')
    ctx.require('https://api.example.test/v1/orders' in t and '-k' not in t, 'URLを指定し、-k（証明書検証無効）は使いません。')


mission(6, 'curlでREST APIを呼ぶ（-X -H -d とBasic認証）',
        'RESTの流れは「メソッド・ヘッダ・本文・認証」を揃えて送ることです。curl では -X でメソッド、-H でヘッダ、-d で本文、-u でBasic認証を指定します。送信先は架空で、ここでは命令文を設計するだけです。',
        ['cmd.txt にcurl1行'], s6, c6,
        """cat > cmd.txt <<'EOF'
curl -X POST -H 'Content-Type: application/json' -H 'X-Request-Id: <<rid>>' -u <<user>>:<<pw>> -d '{"sku":"<<sku>>","qty":<<qty>>}' https://api.example.test/v1/orders
EOF""",
        ["""cat > cmd.txt <<'EOF'
curl -X POST -d '{"sku":"<<sku>>","qty":<<qty>>}' https://api.example.test/v1/orders
EOF""",
         """cat > cmd.txt <<'EOF'
curl -X POST -H 'Content-Type: application/json' -H 'X-Request-Id: <<rid>>' -u <<user>>:<<pw>> -d '{"sku":"<<sku>>","qty":"<<qty>>"}' https://api.example.test/v1/orders
EOF"""],
        '-d を使うと既定のメソッドはPOSTになりますが、意図を明示するため -X POST を書くのが読みやすいです。Basicは「ユーザ:パスワード」をbase64にしただけで暗号化ではないので、必ずHTTPSで使います。パスワードは履歴に残るため本番では環境変数や --netrc を使います。',
        '送るもの4点（メソッド・ヘッダ2つ・認証・本文）を順に書きます。', 'curl -X POST -H … -H … -u user:pw -d \'{…}\' URL')


# ================================================================ 7 curl form/cookie
def s7(ctx):
    d = dict(user='u' + secrets.token_hex(2), pw='pa ss&' + secrets.token_hex(2) + '%x', q='linux 入門 ' + secrets.token_hex(2),
             title='report-' + secrets.token_hex(2))
    ctx.data.update(d)
    ctx.write('report.csv', 'a,b\n1,2\n')
    rtxt(ctx, f'steps.sh に3行の curl（実送信はしない）を書く。(1) https://api.example.test/login にフォーム送信（user={d["user"]}、パスワード「{d["pw"]}」は記号があるので --data-urlencode）して cookie を jar.txt に保存（-c）。(2) /search に cookie を送り（-b jar.txt）-G --data-urlencode で q={d["q"]} をクエリ文字列に。(3) /upload に -b jar.txt でフォーム（multipart、-F）で file=@report.csv と title={d["title"]} を送り、-o /dev/null -w \'%{{http_code}}\' --retry 2。')


def c7(ctx):
    ls = [tk(ctx, x) for x in cl(ctx, 'steps.sh')]
    d = ctx.data

    def find(end):
        for t in ls:
            if t[0] == 'curl' and any(x.endswith(end) for x in t):
                return t
        ctx.fail(f'{end} へのcurl行がありません。')
    a = find('/login')
    ctx.require('jar.txt' in vals(a, '-c', '--cookie-jar'), 'ログインでは -c jar.txt でcookieを保存します。')
    ctx.require('user=' + d['user'] in vals(a, '-d', '--data'), '-d user=… を送ります。')
    ctx.require('password=' + d['pw'] in vals(a, '--data-urlencode'), 'パスワードは --data-urlencode password=… で送ります。')
    ctx.require(not any('password=' in x for x in vals(a, '-d', '--data')), 'パスワードを -d に直接書くと記号で壊れます。')
    b = find('/search')
    ctx.require('jar.txt' in vals(b, '-b', '--cookie') and '-G' in b and 'q=' + d['q'] in vals(b, '--data-urlencode'), '検索は -b jar.txt -G --data-urlencode q=… です。')
    c = find('/upload')
    ctx.require('jar.txt' in vals(c, '-b', '--cookie'), 'アップロードも -b jar.txt。')
    f = vals(c, '-F', '--form')
    ctx.require('file=@report.csv' in f and 'title=' + d['title'] in f, '-F file=@report.csv -F title=… の multipart です。')
    ctx.require('/dev/null' in vals(c, '-o') and any('%{http_code}' in x for x in vals(c, '-w')) and '--retry' in c, '-o /dev/null -w %{http_code} --retry を付けます。')


mission(7, 'curlでform・cookie・--data-urlencodeを組み合わせる',
        'ログインして検索しファイルを送る、という実際のWeb操作の流れをcurlで再現します。form送信は -d と --data-urlencode、cookie は -c（保存）と -b（送信）、ファイルの multipart は -F、結果の確認は -w \'%{http_code}\' です。',
        ['steps.sh に3行'], s7, c7,
        """cat > steps.sh <<'EOF'
curl -c jar.txt -d 'user=<<user>>' --data-urlencode 'password=<<pw>>' https://api.example.test/login
curl -b jar.txt -G --data-urlencode 'q=<<q>>' https://api.example.test/search
curl -b jar.txt -F 'file=@report.csv' -F 'title=<<title>>' -o /dev/null -w '%{http_code}' --retry 2 https://api.example.test/upload
EOF""",
        ["""cat > steps.sh <<'EOF'
curl -c jar.txt -d 'user=<<user>>&password=<<pw>>' https://api.example.test/login
curl -b jar.txt -G --data-urlencode 'q=<<q>>' https://api.example.test/search
curl -b jar.txt -F 'file=@report.csv' -F 'title=<<title>>' -o /dev/null -w '%{http_code}' --retry 2 https://api.example.test/upload
EOF""",
         """cat > steps.sh <<'EOF'
curl -c jar.txt -d 'user=<<user>>' --data-urlencode 'password=<<pw>>' https://api.example.test/login
curl -G --data-urlencode 'q=<<q>>' https://api.example.test/search
curl -b jar.txt -d 'file=@report.csv' -d 'title=<<title>>' -o /dev/null -w '%{http_code}' --retry 2 https://api.example.test/upload
EOF"""],
        '--data-urlencode は値をURLエンコードして送ります。-G を付けるとそれをPOST本文でなくクエリ文字列にします。-F は multipart/form-data で、ファイルは @ファイル名。cookie は -c で書き出し -b で送り返します（-b jar.txt -c jar.txt で更新も可能）。',
        'ログイン・検索・アップロードで使う道具が違います。', '各行の URL と必要なオプションを一つずつ満たします。')


# ================================================================ 8 wget / httpie
def s8(ctx):
    d = dict(tok=secrets.token_hex(4), qty=1 + secrets.randbelow(9), iid=secrets.randbelow(900) + 100,
             iso='dist-' + secrets.token_hex(2) + '.iso')
    ctx.data.update(d)
    ctx.write('curl.txt', f"curl -X PUT -H 'Authorization: Bearer {d['tok']}' -H 'Content-Type: application/json' -d '{{\"qty\":{d['qty']},\"note\":\"hello\"}}' https://api.example.test/v1/items/{d['iid']}\n")
    rtxt(ctx, f'wget.txt に2行：(1) https://docs.example.test/manual/ を丸ごと取得（--mirror）しリンクをローカル用に変換（--convert-links）、親ディレクトリに遡らない（--no-parent）。(2) https://dl.example.test/big.iso を中断再開（-c）で {d["iso"]} という名前（-O）で保存。http.txt には curl.txt と同じ操作の httpie コマンド（http）を1行で書く。')


def c8(ctx):
    d = ctx.data
    w = [tk(ctx, x) for x in cl(ctx, 'wget.txt')]
    ctx.require(len(w) == 2 and all(t[0] == 'wget' for t in w), 'wget.txt はwgetコマンド2行です。')
    a, b = w
    ctx.require(('--mirror' in a or '-m' in a) and '--convert-links' in a and '--no-parent' in a and 'https://docs.example.test/manual/' in a, '1行目は --mirror --convert-links --no-parent とURLです。')
    ctx.require('-c' in b and d['iso'] in vals(b, '-O') and 'https://dl.example.test/big.iso' in b, '2行目は -c と -O ファイル名とURLです。')
    h = cl(ctx, 'http.txt')
    ctx.require(len(h) == 1, 'http.txt は1行です。')
    t = tk(ctx, h[0])
    ctx.require(t[0] == 'http' and 'PUT' in t[:3], 'httpie は http PUT … と書きます。')
    ctx.require(f"https://api.example.test/v1/items/{d['iid']}" in t, 'URLを指定します。')
    ctx.require('Authorization:Bearer' + d['tok'] in [nl(x) for x in t], 'ヘッダは Authorization:Bearer … （コロンで区切る）。')
    ctx.require(f"qty:={d['qty']}" in t and 'note=hello' in t, 'JSONの数値は qty:=数値、文字列は note=hello です。')


mission(8, 'wgetの--mirror -c -Oとhttpieのhttpへの読み替え',
        'wget はサイト全体の取得と再開に強く、curl は1回のリクエストの細かな制御に強い道具です。httpie（http コマンド）は curl の -X/-H/-d を「メソッド URL ヘッダ:値 キー=値」という短い記法で書けます。両方を書き分けてみましょう。',
        ['wget.txt に2行', 'http.txt に1行'], s8, c8,
        """cat > wget.txt <<'EOF'
wget --mirror --convert-links --no-parent https://docs.example.test/manual/
wget -c -O <<iso>> https://dl.example.test/big.iso
EOF
cat > http.txt <<'EOF'
http PUT https://api.example.test/v1/items/<<iid>> 'Authorization:Bearer <<tok>>' qty:=<<qty>> note=hello
EOF""",
        ["""cat > wget.txt <<'EOF'
wget --mirror https://docs.example.test/manual/
wget -O <<iso>> https://dl.example.test/big.iso
EOF
echo 'http PUT https://api.example.test/v1/items/<<iid>> qty:=<<qty>>' > http.txt""",
         """cat > wget.txt <<'EOF'
wget --mirror --convert-links --no-parent https://docs.example.test/manual/
wget -c -O <<iso>> https://dl.example.test/big.iso
EOF
cat > http.txt <<'EOF'
http PUT https://api.example.test/v1/items/<<iid>> 'Authorization:Bearer <<tok>>' qty=<<qty>> note=hello
EOF"""],
        'wget の -O は保存名（-o はログ名で別物）、-c は途中からの再開、--mirror は -r -N -l inf --no-remove-listing の組です。httpie の記法は、: がヘッダ、= がJSON文字列、:= がJSONの生の値（数値・真偽値）、== がクエリ、@ がファイル。',
        '大文字小文字や = と := の違いに注意します。', 'wget --mirror --convert-links --no-parent URL / wget -c -O 名前 URL / http PUT URL ヘッダ:値 qty:=数値 note=文字列')


# ================================================================ 9 rg
def s9(ctx):
    owner = secrets.choice(['mika', 'ren', 'kai', 'yui']) + secrets.token_hex(1)
    files = ['src/app.py', 'src/db.py', 'lib/util.py', 'src/api.py']
    recs, files_hit = [], set()
    total = 0
    for f in files:
        recs.append({'type': 'begin', 'data': {'path': {'text': f}}})
        for i in range(1 + secrets.randbelow(3)):
            ln = 10 + i * 5
            recs.append({'type': 'context', 'data': {'path': {'text': f}, 'lines': {'text': 'x = 1\n'}, 'line_number': ln - 1}})
            recs.append({'type': 'match', 'data': {'path': {'text': f}, 'lines': {'text': f'# TODO({owner}) fix\n'}, 'line_number': ln}})
            total += 1
            files_hit.add(f)
        recs.append({'type': 'end', 'data': {'path': {'text': f}}})
    recs.append({'type': 'summary', 'data': {'stats': {'matches': total}}})
    ctx.data.update(owner=owner, want={'matches': total, 'files': sorted(files_hit)})
    put(ctx, 'rg.jsonl', ''.join(json.dumps(r) + '\n' for r in recs))
    rtxt(ctx, f'(1) Pythonファイルだけ（-t py）から TODO({owner}) を、前後2行の文脈つき（-C 2）で、JSON Lines形式（--json）で、vendor ディレクトリを除外（-g の否定glob）して検索する rg コマンドを rg.txt に1行で書く（.gitignore は rg が既定で尊重するので無効化しない）。(2) 採取済みの rg --json 出力 rg.jsonl から、type が match の件数とファイル一覧（重複なし・昇順）を answer.json {{"matches":N,"files":[...]}} に。')


def c9(ctx):
    need_ro(ctx)
    ls = cl(ctx, 'rg.txt')
    ctx.require(len(ls) == 1, 'rg.txt は1行です。')
    t = tk(ctx, ls[0])
    ctx.require(t[0] == 'rg' and '--json' in t, 'rg --json で出力します。')
    ctx.require('py' in vals(t, '-t', '--type'), '-t py で種類を絞ります。')
    ctx.require('2' in vals(t, '-C', '--context') or '-C2' in t, '-C 2 で前後2行の文脈。')
    ctx.require(any(x.startswith('!') and 'vendor' in x for x in vals(t, '-g', '--glob')), "-g '!vendor/**' のように否定globで除外します。")
    ctx.require(any('TODO' in x and ctx.data['owner'] in x for x in t), 'パターンに TODO(担当者) を入れます。')
    ctx.require(not any(x in t for x in ('-u', '-uu', '-uuu', '--no-ignore', '--no-ignore-vcs')), '.gitignore を無効化しないでください。')
    ctx.require(rj(ctx, 'answer.json') == ctx.data['want'], 'answer.json の件数・ファイル一覧が違います（context は数えない）。')


mission(9, 'ripgrepのrgで-g -t -C --jsonを使い分ける',
        'ripgrep（rg）は .gitignore を尊重して高速に検索します。-t で言語の種類、-g でglob（先頭の ! で除外）、-C で前後の文脈、--json で機械可読な出力を得られます。JSONの出力は jq で集計できます。',
        ['rg.txt にコマンド', 'answer.json に集計'], s9, c9,
        """cat > rg.txt <<'EOF'
rg --json -t py -C 2 -g '!vendor/**' 'TODO\\(<<owner>>\\)' .
EOF
jq -s -c '{matches: (map(select(.type=="match"))|length), files: (map(select(.type=="match")|.data.path.text)|unique)}' rg.jsonl > answer.json""",
        ["""cat > rg.txt <<'EOF'
rg -uuu --json -t py -C 2 -g '!vendor/**' 'TODO\\(<<owner>>\\)' .
EOF
jq -s -c '{matches: (map(select(.type=="match"))|length), files: (map(select(.type=="match")|.data.path.text)|unique)}' rg.jsonl > answer.json""",
         """cat > rg.txt <<'EOF'
rg --json -t py -C 2 -g '!vendor/**' 'TODO\\(<<owner>>\\)' .
EOF
jq -s -c '{matches: length, files: (map(.data.path.text)|unique)}' rg.jsonl > answer.json"""],
        'rg は既定で .gitignore・隠しファイル・バイナリを無視します（-u で段階的に解除）。--json は begin/match/context/end/summary の行を出し、match だけが一致です。-g \'*.py\' は含める指定、-g \'!dir/**\' は除外、-t py は型の定義済み拡張子です。',
        '集計では type を見て match だけを数えます。', 'rg --json -t py -C 2 -g \'!vendor/**\' パターン . と、jq -s で match を数えます。')


# ================================================================ 10 fd fzf bat tree ncdu
def s10(ctx):
    ctx.data['n'] = secrets.choice(['proj', 'app', 'site'])
    ctx.data['ln'] = 10 + secrets.randbelow(20)
    ctx.write(ctx.data['n'] + '/a.conf', 'x=1\n')
    n, ln = ctx.data['n'], ctx.data['ln']
    rtxt(ctx, f'pipe.txt に4行（実行はしない）。(1) fd で {n}/ 以下の隠しファイル込み（-H）、.git を除外（-E .git）、拡張子 conf（-e conf）を探し、fzf に渡し --preview で bat --color=always {{}} を表示。(2) tree で {n} を深さ2（-L 2）、ディレクトリのみ（-d）、node_modules と .git を除外（-I \'node_modules|.git\'）。(3) ncdu で {n} を他ファイルシステムに入らず（-x）対話的に容量調査。(4) bat で app.conf の1〜{ln}行（-r 1:{ln}）を行番号つき（-n）で表示。')


def c10(ctx):
    n, ln = ctx.data['n'], ctx.data['ln']
    ls = cl(ctx, 'pipe.txt')
    ctx.require(len(ls) == 4, 'pipe.txt は4行です。')
    t1 = tk(ctx, ls[0])
    ctx.require('|' in t1, '1行目は fd の結果をパイプで fzf に渡します。')
    i = t1.index('|')
    fd, fz = t1[:i], t1[i + 1:]
    ctx.require(fd[0] == 'fd' and '-H' in fd and '.git' in vals(fd, '-E', '--exclude') and 'conf' in vals(fd, '-e', '--extension'), 'fd -H -E .git -e conf …')
    ctx.require(fz[0] == 'fzf' and any('bat' in x and '{}' in x for x in vals(fz, '--preview')), 'fzf --preview \'bat … {}\'')
    t2 = tk(ctx, ls[1])
    ctx.require(t2[0] == 'tree' and '2' in vals(t2, '-L') and '-d' in t2 and any('node_modules' in x and '.git' in x for x in vals(t2, '-I')) and n in t2, 'tree -L 2 -d -I \'node_modules|.git\' ' + n)
    t3 = tk(ctx, ls[2])
    ctx.require(t3[0] == 'ncdu' and '-x' in t3 and n in t3, 'ncdu -x ' + n)
    t4 = tk(ctx, ls[3])
    ctx.require(t4[0] == 'bat' and ('-n' in t4 or '--number' in t4) and f'1:{ln}' in vals(t4, '-r', '--line-range') and 'app.conf' in ' '.join(t4), 'bat -n -r 1:N app.conf')


mission(10, 'fd・fzf・bat・tree・ncduで探して眺める',
        'find/grep/less/duの現代版です。fd は速く.gitignore対応のfind、fzf は曖昧検索の絞り込み画面、bat は行番号・色付きのcat、tree はディレクトリ構造の表示、ncdu は容量を対話的に調べる道具です。パイプで組み合わせるのが肝です。',
        ['pipe.txt に4行'], s10, c10,
        """cat > pipe.txt <<'EOF'
fd -H -E .git -e conf . <<n>> | fzf --preview 'bat --color=always {}'
tree -L 2 -d -I 'node_modules|.git' <<n>>
ncdu -x <<n>>
bat -n -r 1:<<ln>> app.conf
EOF""",
        ["""cat > pipe.txt <<'EOF'
fd -e conf . <<n>> | fzf --preview 'cat {}'
tree -L 2 -I 'node_modules|.git' <<n>>
ncdu <<n>>
bat app.conf
EOF""",
         """cat > pipe.txt <<'EOF'
fd -H -E .git -e conf . <<n>> | fzf --preview 'bat --color=always {}'
tree -L 2 -d <<n>>
ncdu -x <<n>>
bat -n -r 1:<<ln>> app.conf
EOF"""],
        'fzf は標準入力の行を選ぶ道具で、--preview \'コマンド {}\' の {} が選択中の行に置換されます。fd は既定で隠しファイルと .gitignore を除外し、-H で隠しファイル、-E で除外、-e で拡張子。tree -I は | 区切りの除外パターン、ncdu -x は同一ファイルシステムに限定。',
        '4つの道具の使いどころを一行ずつ。', 'fd … | fzf --preview \'bat --color=always {}\'、tree -L 2 -d -I …、ncdu -x、bat -n -r 1:N。')


# ================================================================ 11 htop btop iotop
def s11(ctx):
    cpu = secrets.SystemRandom().sample(range(100, 900), 6)
    mem = secrets.SystemRandom().sample(range(10, 800), 6)
    wr = secrets.SystemRandom().sample(range(100, 90000), 6)
    pids = secrets.SystemRandom().sample(range(1000, 9000), 6)
    names = ['python3 etl.py', 'postgres: writer', 'rsync -a /data', 'nginx: worker', 'java -jar app.jar', 'node server.js']
    load = [round(secrets.randbelow(900) / 100 + 0.1, 2) for _ in range(3)]
    h = f'  Tasks: 91, 320 thr; 2 running\n  Load average: {load[0]} {load[1]} {load[2]}\n\n    PID USER      PRI  NI  VIRT   RES   SHR S CPU% MEM%   TIME+  Command\n'
    io = 'Total DISK READ:   1.20 M/s | Total DISK WRITE:   4.30 M/s\n  TID  PRIO  USER     DISK READ  DISK WRITE  SWAPIN      IO    COMMAND\n'
    for i in range(6):
        h += f'{pids[i]:7d} trainee    20   0  1.2G  300M  20M S {cpu[i] / 10:4.1f} {mem[i] / 10:4.1f}  1:23.45 {names[i]}\n'
        io += f'{pids[i]:5d} be/4 trainee   {secrets.randbelow(500) / 10:7.2f} K/s {wr[i] / 100:8.2f} K/s  0.00 %  {secrets.randbelow(900) / 10:5.2f} % {names[i]}\n'
    ctx.data['want'] = {'top_cpu_pid': pids[cpu.index(max(cpu))], 'top_mem_pid': pids[mem.index(max(mem))],
                        'top_write_pid': pids[wr.index(max(wr))], 'load1': load[0]}
    put(ctx, 'htop.txt', h)
    put(ctx, 'iotop.txt', io)
    rtxt(ctx, 'htop（btop も同じ項目を表示）の採取結果 htop.txt と iotop -o -b の採取結果 iotop.txt から、CPU%最大のPID、MEM%最大のPID、DISK WRITE最大のPID、1分平均の負荷（Load average の最初の値）を answer.json {"top_cpu_pid":..,"top_mem_pid":..,"top_write_pid":..,"load1":..} に書く。')


def c11(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    w = ctx.data['want']
    for k in ('top_cpu_pid', 'top_mem_pid', 'top_write_pid'):
        ctx.require(a.get(k) == w[k], f'{k} が違います。')
    ctx.require(isinstance(a.get('load1'), (int, float)) and abs(a['load1'] - w['load1']) < 0.001, 'load1 は Load average の最初の値です。')


mission(11, 'htop・btop・iotopの出力から負荷の犯人を読む',
        'サーバが重いときは、CPU（htop/btop の CPU%）、メモリ（MEM%）、ディスク書き込み（iotop の DISK WRITE）のどれが原因かを分けて見ます。実機に無くても、採取した出力を読めるようになりましょう。',
        ['answer.json に4項目'], s11, c11,
        """cpu=$(awk '$1 ~ /^[0-9]+$/ && NF>=11 {print $9, $1}' htop.txt | sort -nr | head -1 | cut -d' ' -f2)
mem=$(awk '$1 ~ /^[0-9]+$/ && NF>=11 {print $10, $1}' htop.txt | sort -nr | head -1 | cut -d' ' -f2)
wr=$(awk '$1 ~ /^[0-9]+$/ && NF>=9 {print $6, $1}' iotop.txt | sort -nr | head -1 | cut -d' ' -f2)
load=$(awk '/Load average/ {print $3}' htop.txt)
printf '{"top_cpu_pid":%s,"top_mem_pid":%s,"top_write_pid":%s,"load1":%s}\\n' "$cpu" "$mem" "$wr" "$load" > answer.json""",
        ["""cpu=$(awk '$1 ~ /^[0-9]+$/ && NF>=11 {print $9, $1}' htop.txt | sort -nr | head -1 | cut -d' ' -f2)
printf '{"top_cpu_pid":%s,"top_mem_pid":%s,"top_write_pid":%s,"load1":1}\\n' "$cpu" "$cpu" "$cpu" > answer.json""",
         """cpu=$(awk '$1 ~ /^[0-9]+$/ && NF>=11 {print $9, $1}' htop.txt | sort -n | head -1 | cut -d' ' -f2)
mem=$(awk '$1 ~ /^[0-9]+$/ && NF>=11 {print $10, $1}' htop.txt | sort -nr | head -1 | cut -d' ' -f2)
wr=$(awk '$1 ~ /^[0-9]+$/ && NF>=9 {print $6, $1}' iotop.txt | sort -nr | head -1 | cut -d' ' -f2)
printf '{"top_cpu_pid":%s,"top_mem_pid":%s,"top_write_pid":%s,"load1":1}\\n' "$cpu" "$mem" "$wr" > answer.json"""],
        'htop/btop は CPU%・MEM%・負荷平均（1/5/15分）を一画面に、iotop は -o（実際にI/Oしているものだけ）で DISK WRITE を表示します（通常はroot権限が必要）。負荷平均が高くてもCPU%が低ければ、I/O待ちが疑わしいと読みます。',
        '列の位置を見極めて、列ごとに降順で先頭を取ります。', 'awk で列を取り出して sort -nr | head -1 し、printf でJSONにします。')


# ================================================================ 12 iftop nethogs nload vnstat
def s12(ctx):
    R = secrets.SystemRandom()
    pids = R.sample(range(1000, 9000), 4)
    rec = R.sample(range(100, 9000), 4)
    hosts = ['cdn.example.test', 'db.example.test', 'api.example.test', 'backup.example.test']
    cum = R.sample(range(100, 9900), 4)
    cum2 = R.sample(range(100, 9900), 4)
    days = ['2026-11-1' + str(i) for i in range(5)]
    tot = R.sample(range(1000, 90000), 5)
    nl_max = R.sample(range(1000, 9000), 3)
    nh = 'NetHogs version 0.8.7 (recorded)\n\n  PID USER     PROGRAM                      DEV        SENT      RECEIVED\n'
    for i in range(4):
        nh += f'{pids[i]:5d} trainee  /usr/bin/prog{i}                eth0     {R.randrange(1, 99)}.500    {rec[i] / 10:.3f} KB/sec\n'
    it = '   # host                      last 2s   last 10s  last 40s   cumulative\n'
    for i in range(4):
        it += f'{i + 1:3d} {hosts[i]:<24} => 1.00Mb  1.00Mb  1.00Mb  {cum[i] / 100:.2f}MB\n'
        it += f'    10.0.0.{i + 5:<17} <= 2.00Mb  2.00Mb  2.00Mb  {cum2[i] / 100:.2f}MB\n'
    vn = ' eth0 / daily\n\n         day        rx      |     tx      |    total    |   avg. rate\n     ------------------------+-------------+-------------+---------------\n'
    for i in range(5):
        t = tot[i] / 100
        vn += f'     {days[i]}    {t * 0.7:.2f} MiB |   {t * 0.3:.2f} MiB |  {t:.2f} MiB |    4.20 kbit/s\n'
    nlt = 'Device eth0 [10.0.0.2] (1/1):\n=====\nIncoming:\n  Curr: 1.00 MBit/s\n  Avg: 2.00 MBit/s\n  Min: 0.50 MBit/s\n' \
          f'  Max: {nl_max[0] / 100:.2f} MBit/s\nOutgoing:\n  Curr: 1.00 MBit/s\n  Avg: 2.00 MBit/s\n  Min: 0.50 MBit/s\n  Max: {nl_max[1] / 100:.2f} MBit/s\n'
    ctx.data['want'] = {'nethogs_top_recv_pid': pids[rec.index(max(rec))], 'iftop_top_host': hosts[cum.index(max(cum))],
                        'vnstat_peak_day': days[tot.index(max(tot))], 'nload_max_in': nl_max[0] / 100}
    for n, t in (('nethogs.txt', nh), ('iftop.txt', it), ('vnstat.txt', vn), ('nload.txt', nlt)):
        put(ctx, n, t)
    rtxt(ctx, '採取済みの nethogs.txt（プロセス別）、iftop.txt（通信相手別、=> が送信側の行）、vnstat.txt（日別累計）、nload.txt（Incomingの Curr/Avg/Min/Max）から answer.json {"nethogs_top_recv_pid":..,"iftop_top_host":..（=>行で cumulative が最大のホスト）,"vnstat_peak_day":..（total最大の日）,"nload_max_in":..（Incomingの Max の数値）} を作る。')


def c12(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    w = ctx.data['want']
    for k in ('nethogs_top_recv_pid', 'iftop_top_host', 'vnstat_peak_day'):
        ctx.require(a.get(k) == w[k], f'{k} が違います。')
    ctx.require(isinstance(a.get('nload_max_in'), (int, float)) and abs(a['nload_max_in'] - w['nload_max_in']) < 0.001, 'nload_max_in は Incoming の Max の数値です。')


mission(12, 'iftop・nethogs・nload・vnstatで通信量を読み分ける',
        '帯域の問題は「誰が（nethogs：プロセス別）」「どこと（iftop：相手別）」「今どれだけ（nload：リアルタイム）」「過去どれだけ（vnstat：日別累計）」で見る道具が違います。それぞれの出力を読み取ります。',
        ['answer.json に4項目'], s12, c12,
        """pid=$(awk '$1 ~ /^[0-9]+$/ {print $6, $1}' nethogs.txt | sort -nr | head -1 | cut -d' ' -f2)
host=$(awk '$3=="=>" {print $NF, $2}' iftop.txt | sort -nr | head -1 | cut -d' ' -f2)
day=$(awk '$1 ~ /^20[0-9][0-9]-/ {print $8, $1}' vnstat.txt | sort -nr | head -1 | cut -d' ' -f2)
mx=$(awk '/Incoming/ {f=1} f && /Max:/ {print $2; exit}' nload.txt)
printf '{"nethogs_top_recv_pid":%s,"iftop_top_host":"%s","vnstat_peak_day":"%s","nload_max_in":%s}\\n' "$pid" "$host" "$day" "$mx" > answer.json""",
        ["""pid=$(awk '$1 ~ /^[0-9]+$/ {print $6, $1}' nethogs.txt | sort -n | head -1 | cut -d' ' -f2)
host=$(awk '$3=="=>" {print $NF, $2}' iftop.txt | sort -nr | head -1 | cut -d' ' -f2)
day=$(awk '$1 ~ /^20[0-9][0-9]-/ {print $8, $1}' vnstat.txt | sort -nr | head -1 | cut -d' ' -f2)
mx=$(awk '/Incoming/ {f=1} f && /Max:/ {print $2; exit}' nload.txt)
printf '{"nethogs_top_recv_pid":%s,"iftop_top_host":"%s","vnstat_peak_day":"%s","nload_max_in":%s}\\n' "$pid" "$host" "$day" "$mx" > answer.json""",
         """pid=$(awk '$1 ~ /^[0-9]+$/ {print $6, $1}' nethogs.txt | sort -nr | head -1 | cut -d' ' -f2)
host=$(awk '$3=="=>" {print $NF, $2}' iftop.txt | sort -nr | head -1 | cut -d' ' -f2)
day=$(awk '$1 ~ /^20[0-9][0-9]-/ {print $8, $1}' vnstat.txt | sort -n | head -1 | cut -d' ' -f2)
mx=$(awk '/Max:/ {print $2; exit}' nload.txt | tail -1)
printf '{"nethogs_top_recv_pid":%s,"iftop_top_host":"%s","vnstat_peak_day":"%s","nload_max_in":%s}\\n' "$pid" "$host" "$day" "$mx" > answer.json"""],
        'nethogs はプロセスごとの SENT/RECEIVED（実行にroot権限が要る）、iftop は相手ごとに =>（送信）と <=（受信）を2行で示し 2s/10s/40s の平均と cumulative を出します。nload は Curr/Avg/Min/Max をIncoming/Outgoingで、vnstat は日・月ごとの累計を保存します。方向と列の取り違えが典型的な失敗です。',
        '各ファイルでどの列・どの行種別を見るかを決めます。', 'awk で列を取り出し、sort -nr | head -1 で最大を選びます。')


# ================================================================ 13 mtr / traceroute
def s13(ctx):
    n = 8 + secrets.randbelow(3)
    f = 2 + secrets.randbelow(3)
    r = 6 + secrets.randbelow(n - 6)
    loss = {}
    for h in range(1, n + 1):
        loss[h] = round(15 + secrets.randbelow(250) / 10, 1) if h >= r else 0.0
    loss[f] = round(20 + secrets.randbelow(400) / 10, 1)
    m = 'Start: 2026-11-01T10:00:00+0900\nHOST: lab                     Loss%   Snt   Last   Avg  Best  Wrst StDev\n'
    t = 'traceroute to dst.example.test (203.0.113.9), 30 hops max\n'
    for h in range(1, n + 1):
        m += f'{h:3d}.|-- hop{h}.isp.test        {loss[h]:5.1f}%   100   10.0  11.0   9.0  15.0   1.0\n'
        t += f'{h:2d}  * * *\n' if h == f else f'{h:2d}  hop{h}.isp.test (192.0.2.{h})  10.1 ms  10.3 ms  10.2 ms\n'
    ctx.data['want'] = {'real_loss_hop': r, 'false_alarm_hop': f, 'destination_loss': loss[n]}
    put(ctx, 'mtr.txt', m)
    put(ctx, 'traceroute.txt', t)
    rtxt(ctx, 'mtr --report の結果 mtr.txt と traceroute の結果 traceroute.txt がある。中間ルータが ICMP 応答を絞るだけの「見かけの損失」と、宛先まで続く「本当の損失」を区別し、answer.json {"real_loss_hop":本当の損失が始まるホップ番号,"false_alarm_hop":見かけの損失のホップ番号,"destination_loss":最終ホップのLoss%} を書く。')


def c13(ctx):
    need_ro(ctx)
    a = rj(ctx, 'answer.json')
    w = ctx.data['want']
    ctx.require(a.get('real_loss_hop') == w['real_loss_hop'], '本当の損失は「そこから宛先まで途切れず続く」最初のホップです。')
    ctx.require(a.get('false_alarm_hop') == w['false_alarm_hop'], '以降のホップが0%に戻っているのは見かけの損失です。')
    ctx.require(isinstance(a.get('destination_loss'), (int, float)) and abs(a['destination_loss'] - w['destination_loss']) < 0.001, 'destination_loss は最終ホップのLoss%です。')


mission(13, 'mtrとtracerouteの結果から本当の損失を読み分ける',
        'traceroute は1回ごとの経路スナップショット（応答なしは * * *）、mtr は経路と各ホップの損失率を連続計測して統計にします。途中のルータが応答を間引いていても、先のホップが0%なら実害はありません。宛先まで続く損失だけが本物です。',
        ['answer.json'], s13, c13,
        """awk '/\\|--/ {h=$1+0; l=$3+0; loss[h]=l; n=h} END {r=0; for (i=n; i>=1 && loss[i]>0; i--) r=i; f=0; for (i=1; i<r; i++) if (loss[i]>0) f=i; printf "{\\"real_loss_hop\\":%d,\\"false_alarm_hop\\":%d,\\"destination_loss\\":%s}\\n", r, f, loss[n]}' mtr.txt > answer.json""",
        ["""awk '/\\|--/ {h=$1+0; l=$3+0; if (l>0 && !f) f=h; n=h; d=l} END {printf "{\\"real_loss_hop\\":%d,\\"false_alarm_hop\\":%d,\\"destination_loss\\":%s}\\n", f, f, d}' mtr.txt > answer.json""",
         """awk '/\\|--/ {h=$1+0; l=$3+0; loss[h]=l; n=h} END {r=0; for (i=n; i>=1 && loss[i]>0; i--) r=i; printf "{\\"real_loss_hop\\":%d,\\"false_alarm_hop\\":%d,\\"destination_loss\\":0}\\n", r, r}' mtr.txt > answer.json"""],
        'mtr -rwc 100 のレポートは各行が ホップ番号.|-- ホスト Loss% Snt Last Avg … です。判断の原則は「損失が途中だけで次のホップから0%に戻る＝ICMPのレート制限などの見かけ」「あるホップから宛先まで損失が続く＝そこ以降が本物」。traceroute の * * * も同様に、先のホップが返っていれば実害ではありません。',
        '最終ホップから遡って、損失が途切れるまでを本物とみなします。', 'awk で各ホップの損失を配列に入れ、末尾から遡って最初の0%の手前を real にします。')


# ================================================================ 14 socat nc ncat
def s14(ctx):
    P = secrets.SystemRandom().sample(range(20000, 60000), 5)
    ctx.data.update(p1=P[0], p2=P[1], p3=P[2], p4=P[3], p5=P[4], lo=P[0] // 10 * 0 + 20, hi=26, fn='recv-' + secrets.token_hex(2) + '.bin')
    ctx.write('payload.bin', secrets.token_hex(8) + '\n')
    rtxt(ctx, f'net.txt に5行（実行はしない。ローカルホスト127.0.0.1限定）。(1) socat で {P[0]} 番で待ち受け、受けた接続ごとに fork して 127.0.0.1:{P[1]} へ転送（reuseaddr付き）。(2) socat で {P[2]} 番の受信内容を一方向（-u）で {ctx.data["fn"]} に OPEN（creat,trunc）。(3) ncat で {P[3]} 番を接続のたびに閉じず待ち受け続ける簡易サーバ（-l と -k）。(4) nc で 127.0.0.1 の 20-26 番ポートを接続だけして調べる簡易ポートスキャン（-z -v）。(5) nc で payload.bin を 127.0.0.1 の {P[4]} 番へ送る（< でリダイレクト）。')


def c14(ctx):
    d = ctx.data
    ls = cl(ctx, 'net.txt')
    ctx.require(len(ls) == 5, 'net.txt は5行です。')
    a, b, c, e, f = ls
    ctx.require(a.startswith('socat ') and f"TCP-LISTEN:{d['p1']}" in a.replace('TCP4-LISTEN', 'TCP-LISTEN') and 'fork' in a and 'reuseaddr' in a and f"TCP:127.0.0.1:{d['p2']}" in a.replace('TCP4:', 'TCP:'), '(1) socat TCP-LISTEN:ポート,fork,reuseaddr TCP:127.0.0.1:転送先')
    ctx.require(b.startswith('socat ') and '-u' in b.split() and f"TCP-LISTEN:{d['p3']}" in b and f"OPEN:{d['fn']}" in b and 'creat' in b, '(2) socat -u TCP-LISTEN:… OPEN:ファイル,creat,trunc')
    tc = tk(ctx, c)
    fl = ''.join(x[1:] for x in tc if x.startswith('-') and not x.startswith('--'))
    ctx.require(tc[0] == 'ncat' and 'l' in fl and 'k' in fl and str(d['p4']) in tc, '(3) ncat -l -k ポート')
    te = tk(ctx, e)
    fe = ''.join(x[1:] for x in te if x.startswith('-') and not x.startswith('--'))
    ctx.require(te[0] == 'nc' and 'z' in fe and 'v' in fe and '127.0.0.1' in te and '20-26' in te and 'l' not in fe, '(4) nc -zv 127.0.0.1 20-26')
    ctx.require(re.fullmatch(rf'nc\s+127\.0\.0\.1\s+{d["p5"]}\s*<\s*payload\.bin|cat\s+payload\.bin\s*\|\s*nc\s+127\.0\.0\.1\s+{d["p5"]}', f.strip()), '(5) nc 127.0.0.1 ポート < payload.bin')


mission(14, 'socatとnc・ncatでポート転送とファイル中継を組む',
        'nc（netcat）は TCP/UDP の万能つなぎ、ncat は nmap 付属の高機能版、socat は「2つのアドレスを双方向につなぐ」さらに強力な中継器です。ポート転送・ファイル受け渡し・簡易サーバ・ポート確認がコマンド1行でできます。実行せず、安全な形の1行を設計します。',
        ['net.txt に5行'], s14, c14,
        """cat > net.txt <<'EOF'
socat TCP-LISTEN:<<p1>>,fork,reuseaddr TCP:127.0.0.1:<<p2>>
socat -u TCP-LISTEN:<<p3>>,reuseaddr OPEN:<<fn>>,creat,trunc
ncat -l -k <<p4>>
nc -zv 127.0.0.1 20-26
nc 127.0.0.1 <<p5>> < payload.bin
EOF""",
        ["""cat > net.txt <<'EOF'
socat TCP-LISTEN:<<p2>>,fork,reuseaddr TCP:127.0.0.1:<<p1>>
socat -u TCP-LISTEN:<<p3>>,reuseaddr OPEN:<<fn>>,creat,trunc
ncat -l <<p4>>
nc -zv 127.0.0.1 20-26
nc 127.0.0.1 <<p5>> < payload.bin
EOF""",
         """cat > net.txt <<'EOF'
socat TCP-LISTEN:<<p1>>,fork,reuseaddr TCP:127.0.0.1:<<p2>>
socat TCP-LISTEN:<<p3>>,reuseaddr OPEN:<<fn>>
ncat -l -k <<p4>>
nc -l 20-26
nc 127.0.0.1 <<p5>> > payload.bin
EOF"""],
        'socat の fork は接続ごとに子プロセスを作り、reuseaddr は再起動時の「Address already in use」を避けます。-u は片方向、OPEN は ファイル,creat,trunc で作成・切り詰め。nc -z は送信せず接続だけ確認し、-v で結果表示。ncat は -k（--keep-open）で待ち受けを続けられます。外部公開する待ち受けは認証がないため危険です。',
        '待ち受け側と接続側、方向（< と >）を間違えないようにします。', 'socat TCP-LISTEN:…,fork,reuseaddr TCP:…、socat -u … OPEN:…、ncat -l -k、nc -zv、nc … < ファイル')


# ================================================================ 15 whois dig ss
def s15(ctx):
    port = secrets.choice([443, 8443, 9443])
    mxs = secrets.SystemRandom().sample([10, 20, 30], 3)
    names = ['mail1', 'mail2', 'mail3']
    exp = f'2027-{1 + secrets.randbelow(12):02d}-{1 + secrets.randbelow(28):02d}'
    reg = 'Example Registrar ' + secrets.token_hex(2).upper()
    pid = 1000 + secrets.randbelow(8000)
    proc = secrets.choice(['nginx', 'caddy', 'haproxy'])
    bind = secrets.choice(['127.0.0.1', '10.0.0.5'])
    wh = f'Domain Name: EXAMPLE.TEST\nRegistrar: {reg}\nRegistry Expiry Date: {exp}T00:00:00Z\nName Server: NS1.EXAMPLE.TEST\n'
    dg = 'example.test. 300 IN A 203.0.113.9\n' + ''.join(f'example.test. 300 IN MX {mxs[i]} {names[i]}.example.test.\n' for i in range(3)) + 'example.test. 300 IN NS ns1.example.test.\n'
    ss = 'State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n' \
         f'LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=900,fd=3))\nLISTEN 0 511 {bind}:{port} 0.0.0.0:* users:(("{proc}",pid={pid},fd=6))\n'
    ctx.data['want'] = {'registrar': reg, 'expires': exp, 'mx_host': names[mxs.index(min(mxs))] + '.example.test.',
                        'listen_proc': proc, 'listen_pid': pid, 'bind': bind}
    ctx.data['port'] = port
    for n, t in (('whois.txt', wh), ('dig.txt', dg), ('ss.txt', ss)):
        put(ctx, n, t)
    rtxt(ctx, f'サイトが外から見えない。whois.txt（whois）、dig.txt（dig +noall +answer）、ss.txt（ss -tlnp）を読み、answer.json {{"registrar":登録事業者,"expires":有効期限の日付(YYYY-MM-DD),"mx_host":優先度が最も高い（数値が最小の）MXホスト,"listen_proc":ポート{port}で待受するプロセス名,"listen_pid":そのPID,"bind":待受アドレス}} を書く。')


def c15(ctx):
    need_ro(ctx)
    ctx.require(rj(ctx, 'answer.json') == ctx.data['want'], 'answer.json が違います。MXは数値が小さいほど優先、待受は Local Address:Port の列です。')


mission(15, 'whois・dig・ssを組み合わせて到達不能を診断する',
        '「外から見えない」は、ドメインの状態（whois）、名前解決（dig）、待ち受けの状態（ss）の3点で切り分けます。whois は登録情報と期限、dig はA/MX/NSレコード、ss -tlnp は待受ポートとプロセス・バインドアドレスを見られます。',
        ['answer.json'], s15, c15,
        """reg=$(sed -n 's/^Registrar: *//p' whois.txt)
exp=$(sed -n 's/^Registry Expiry Date: *\\([0-9-]*\\).*/\\1/p' whois.txt)
mx=$(awk '$4=="MX" {print $5, $6}' dig.txt | sort -n | head -1 | cut -d' ' -f2)
row=$(awk '$4 ~ /:<<port>>$/' ss.txt)
bind=$(echo "$row" | awk '{print $4}' | sed 's/:[0-9]*$//')
proc=$(echo "$row" | sed 's/.*(("\\([^"]*\\)".*/\\1/')
pid=$(echo "$row" | grep -o 'pid=[0-9]*' | cut -d= -f2)
printf '{"registrar":"%s","expires":"%s","mx_host":"%s","listen_proc":"%s","listen_pid":%s,"bind":"%s"}\\n' "$reg" "$exp" "$mx" "$proc" "$pid" "$bind" > answer.json""",
        ["""reg=$(sed -n 's/^Registrar: *//p' whois.txt)
printf '{"registrar":"%s","expires":"","mx_host":"","listen_proc":"","listen_pid":0,"bind":""}\\n' "$reg" > answer.json""",
         """reg=$(sed -n 's/^Registrar: *//p' whois.txt)
exp=$(sed -n 's/^Registry Expiry Date: *\\([0-9-]*\\).*/\\1/p' whois.txt)
mx=$(awk '$4=="MX" {print $5, $6}' dig.txt | sort -nr | head -1 | cut -d' ' -f2)
row=$(awk '$4 ~ /:<<port>>$/' ss.txt)
bind=$(echo "$row" | awk '{print $4}' | sed 's/:[0-9]*$//')
proc=$(echo "$row" | sed 's/.*(("\\([^"]*\\)".*/\\1/')
pid=$(echo "$row" | grep -o 'pid=[0-9]*' | cut -d= -f2)
printf '{"registrar":"%s","expires":"%s","mx_host":"%s","listen_proc":"%s","listen_pid":%s,"bind":"%s"}\\n' "$reg" "$exp" "$mx" "$proc" "$pid" "$bind" > answer.json"""],
        'whois は登録者・期限・ネームサーバ、dig は +short や +noall +answer で必要な行だけを出せます（MXの数値は小さいほど優先）。ss -tlnp は待受(-l)TCP(-t)数値(-n)プロセス(-p)。127.0.0.1 で待ち受けていると外部からは接続できません。0.0.0.0 か外向きIPへのバインドが必要です。',
        '3つの情報源を順に読み、列の位置を確認します。', 'sed/awk で各値を取り出し、printf でJSONにします。')


# ================================================================ 16 tshark
def s16(ctx):
    src = '10.0.0.' + str(10 + secrets.randbelow(80))
    other = '10.0.0.' + str(100 + secrets.randbelow(80))
    dA, dB, dC = '203.0.113.10', '203.0.113.20', '203.0.113.30'
    rows = []
    nA, nB = 3 + secrets.randbelow(2), 1 + secrets.randbelow(2)

    def add(s, d, port, info):
        rows.append((len(rows) + 1, s, d, port, 'TCP', info))
    for _ in range(nA):
        add(src, dA, 443, '[TCP Retransmission] 51234 -> 443 [ACK] Seq=1')
        add(src, dC, 443, '51240 -> 443 [ACK] Seq=9')
    for _ in range(nB):
        add(src, dB, 443, '[TCP Retransmission] 51235 -> 443 [ACK] Seq=2')
    add(src, dB, 80, '[TCP Retransmission] 51236 -> 80 [ACK] Seq=3')
    add(src, dA, 80, '[TCP Retransmission] 51237 -> 80 [ACK] Seq=4')
    add(other, dA, 443, '[TCP Retransmission] 41111 -> 443 [ACK] Seq=5')
    add(other, dC, 443, '41112 -> 443 [ACK] Seq=6')
    ctx.data.update(src=src, want={'retransmissions': nA + nB, 'worst_dst': dA})
    put(ctx, 'packets.tsv', ''.join('\t'.join(map(str, r)) + '\n' for r in rows))
    rtxt(ctx, f'キャプチャ capture.pcap（実在しない。tshark -r で読む想定）から、送信元 {src} が宛先ポート443へ送った TCP 再送だけを表示する tshark コマンドを cmd.txt に1行で書く（表示フィルタは -Y。wireshark の画面の表示フィルタ欄に入れる式と同じ。-f はキャプチャフィルタなので使わない）。-T fields -e ip.dst も付ける。次に、採取済みの packets.tsv（列：番号,送信元,宛先,宛先ポート,プロトコル,情報）から同条件の再送数と、最も多い宛先を summary.json {{"retransmissions":N,"worst_dst":"IP"}} に。')


def c16(ctx):
    need_ro(ctx)
    ls = cl(ctx, 'cmd.txt')
    ctx.require(len(ls) == 1, 'cmd.txt は1行です。')
    t = tk(ctx, ls[0])
    ctx.require(t[0] == 'tshark' and 'capture.pcap' in vals(t, '-r') and '-f' not in t and '-R' not in t, 'tshark -r capture.pcap -Y … の形です。')
    y = vals(t, '-Y')
    ctx.require(len(y) == 1, '表示フィルタは -Y で1つ指定します。')
    f = nl(y[0])
    ctx.require('ip.src==' + ctx.data['src'] in f and 'tcp.analysis.retransmission' in f and 'tcp.dstport==443' in f, '式に ip.src == 送信元、tcp.analysis.retransmission、tcp.dstport == 443 を && でつなぎます。')
    ctx.require('-T' in t and 'fields' in vals(t, '-T') and 'ip.dst' in vals(t, '-e'), '-T fields -e ip.dst を付けます。')
    ctx.require(rj(ctx, 'summary.json') == ctx.data['want'], 'summary.json が違います（送信元・ポート443・再送の3条件）。')


mission(16, 'tsharkとwiresharkの表示フィルタを読み書きする',
        'tshark は wireshark のコマンド版です。-r でキャプチャファイルを読み、-Y の表示フィルタ（wireshark の画面で入力する式と同じ）で絞り、-T fields -e で列を指定します。表示フィルタはパケット解析済みの項目（tcp.analysis.retransmission 等）で絞れる点が、キャプチャ前の -f（BPF）との違いです。',
        ['cmd.txt', 'summary.json'], s16, c16,
        """cat > cmd.txt <<'EOF'
tshark -r capture.pcap -Y 'ip.src == <<src>> && tcp.analysis.retransmission && tcp.dstport == 443' -T fields -e ip.dst
EOF
r=$(awk -F'\\t' '$2=="<<src>>" && $4==443 && $6 ~ /Retransmission/ {print $3}' packets.tsv)
n=$(printf '%s\\n' "$r" | wc -l)
w=$(printf '%s\\n' "$r" | sort | uniq -c | sort -k1,1nr | head -1 | awk '{print $2}')
printf '{"retransmissions":%s,"worst_dst":"%s"}\\n' "$n" "$w" > summary.json""",
        ["""cat > cmd.txt <<'EOF'
tshark -r capture.pcap -f 'ip.src == <<src>> && tcp.analysis.retransmission && tcp.dstport == 443' -T fields -e ip.dst
EOF
printf '{"retransmissions":0,"worst_dst":""}\\n' > summary.json""",
         """cat > cmd.txt <<'EOF'
tshark -r capture.pcap -Y 'ip.src == <<src>> && tcp.analysis.retransmission && tcp.dstport == 443' -T fields -e ip.dst
EOF
r=$(awk -F'\\t' '$2=="<<src>>" && $6 ~ /Retransmission/ {print $3}' packets.tsv)
n=$(printf '%s\\n' "$r" | wc -l)
w=$(printf '%s\\n' "$r" | sort | uniq -c | sort -k1,1nr | head -1 | awk '{print $2}')
printf '{"retransmissions":%s,"worst_dst":"%s"}\\n' "$n" "$w" > summary.json"""],
        '表示フィルタは比較演算子（==, !=, >）と論理演算子（&&, ||, !）で組み、フィールド名は tshark -G fields で調べます。例：http.request.method == "POST"、tcp.flags.syn == 1 && tcp.flags.ack == 0。キャプチャフィルタ（-f）は BPF 構文（host 1.2.3.4 and port 443）で別物です。',
        '-Y は表示フィルタ、-f はキャプチャフィルタです。', 'tshark -r capture.pcap -Y \'式\' -T fields -e ip.dst。集計は awk -F\'\\t\' です。')


# ================================================================ 17 calc
def s17(ctx):
    import calendar
    a, b = 100 + secrets.randbelow(900), 3 + secrets.randbelow(20)
    while a % b == 0:
        a += 1
    q = a * 10000 // b
    c_, d_, e_ = 12 + secrets.randbelow(80), 7 + secrets.randbelow(50), secrets.randbelow(500)
    g, h, m = 2 + secrets.randbelow(8), 20 + secrets.randbelow(60), 1000 + secrets.randbelow(9000)
    y, mo = 2026, 1 + secrets.randbelow(12)
    cal = calendar.Calendar(firstweekday=6).monthdayscalendar(y, mo)
    fr = [w[5] for w in cal if w[5]]
    txt = f'{calendar.month_name[mo]} {y}'.center(20).rstrip() + '\nSu Mo Tu We Th Fr Sa\n' + ''.join(' '.join(f'{d:2d}' if d else '  ' for d in w).rstrip() + '\n' for w in cal)
    ctx.data.update(a=a, b=b, c=c_, d=d_, e=e_, g=g, h=h, m=m)
    ctx.data['want'] = [f'{q // 10000}.{q % 10000:04d}', str(c_ * d_ + e_), str(pow(g, h, m)), str(fr[2])]
    put(ctx, 'cal.txt', txt)
    rtxt(ctx, f'calc.sh を書いて実行し、results.txt に次の4行を順に出す。(1) bc で小数4桁の {a}/{b}（scale=4）。(2) dc の逆ポーランドで {c_}×{d_}+{e_}。(3) python3 -c で {g}の{h}乗を{m}で割った余り（pow の3引数）。(4) cal の出力 cal.txt（日曜始まり）から3番目の金曜日の日付（数字だけ）。')


def c17(ctx):
    need_ro(ctx)
    t = ctx.need_file('calc.sh')
    ctx.require(all(k in t for k in ('bc', 'dc', 'python3 -c')), 'calc.sh は bc・dc・python3 -c を使います。')
    got = [x.strip() for x in ctx.need_file('results.txt').splitlines() if x.strip()]
    ctx.require(got == ctx.data['want'], 'results.txt の4行が期待と違います（桁数・金曜の列に注意）。')


mission(17, 'bc・dc・python3 -c・calで計算と日付を扱う',
        'ターミナルの電卓は用途で使い分けます。bc は小数の精度指定（scale）、dc はスタック型（逆ポーランド）、python3 -c は何でも書ける一行スクリプトです。cal は月のカレンダーで、曜日の列を cut で読めば日付計算にも使えます。',
        ['calc.sh を作って実行', 'results.txt に4行'], s17, c17,
        """cat > calc.sh <<'EOF'
echo "scale=4; <<a>>/<<b>>" | bc > results.txt
dc -e "<<c>> <<d>> * <<e>> + p" >> results.txt
python3 -c "print(pow(<<g>>, <<h>>, <<m>>))" >> results.txt
sed -n '3,$p' cal.txt | cut -c16-17 | tr -d ' ' | grep . | sed -n 3p >> results.txt
EOF
sh calc.sh""",
        ["""cat > calc.sh <<'EOF'
echo "<<a>>/<<b>>" | bc > results.txt
dc -e "<<c>> <<d>> * <<e>> + p" >> results.txt
python3 -c "print(pow(<<g>>, <<h>>, <<m>>))" >> results.txt
sed -n '3,$p' cal.txt | cut -c16-17 | tr -d ' ' | grep . | sed -n 3p >> results.txt
EOF
sh calc.sh""",
         """cat > calc.sh <<'EOF'
echo "scale=4; <<a>>/<<b>>" | bc > results.txt
dc -e "<<c>> <<d>> * <<e>> + p" >> results.txt
python3 -c "print(<<g>> ** <<h>> % <<m>> + 1)" >> results.txt
sed -n '3,$p' cal.txt | cut -c13-14 | tr -d ' ' | grep . | sed -n 3p >> results.txt
EOF
sh calc.sh"""],
        'bc は既定で整数除算なので scale を指定し、dc は「数を積んで演算子で畳む」ので p で先頭を表示します。python3 -c は桁あふれのない整数計算に便利。cal の1日3文字幅の固定桁なので cut -c で曜日の列を取れます（日曜=1-2、金曜=16-17）。',
        '各ツールの得意な計算を1行ずつ書き、結果を追記していきます。', 'echo "scale=4; a/b" | bc、dc -e "c d * e + p"、python3 -c "print(pow(g,h,m))"、cal.txt を cut -c16-17。')


# ================================================================ 18 parallel xargs -P
def s18(ctx):
    for i in range(8):
        ctx.write(f'inputs/f{i}.txt', secrets.token_hex(6) + '\n')
    ctx.data['jobs'] = 2 + secrets.randbelow(5)
    put(ctx, 'job.sh', 'mkdir -p out\nsha256sum "inputs/$1" | cut -d" " -f1 > "out/$1.sum"\n')
    rtxt(ctx, f'inputs/ の8ファイルそれぞれに job.sh（引数＝ファイル名。out/名前.sum を作る）を実行する run.sh を、xargs の -P {ctx.data["jobs"]}（並列度）で書いて実行する。また同じ処理を GNU parallel（-j {ctx.data["jobs"]}）で書いた1行を parallel.txt に保存する。')


def c18(ctx):
    need_ro(ctx)
    j = ctx.data['jobs']
    t = ctx.need_file('run.sh')
    ctx.require('xargs' in t and re.search(rf'-P\s*{j}\b', t), f'run.sh は xargs -P {j} を使います。')
    for i in range(8):
        h = hashlib.sha256(ctx.p(f'inputs/f{i}.txt').read_bytes()).hexdigest()
        ctx.require(ctx.read(f'out/f{i}.txt.sum') is not None and ctx.read(f'out/f{i}.txt.sum').strip() == h, f'out/f{i}.txt.sum がありません/違います。run.sh を実行してください。')
    pl = cl(ctx, 'parallel.txt')
    ctx.require(len(pl) == 1 and 'parallel' in pl[0] and re.search(rf'-j\s*{j}\b', pl[0]) and 'job.sh' in pl[0], 'parallel.txt は parallel -j N … job.sh を含む1行です。')


mission(18, 'xargs -Pとparallelで処理を並列化する',
        '独立した多数の処理は並列にすると速くなります。標準の xargs は -P で並列度、-I{} で引数の置換ができ、GNU parallel は -j と {} と ::: でより高機能に書けます。順序が保証されない点には注意します。',
        ['run.sh を実行', 'parallel.txt'], s18, c18,
        """cat > run.sh <<'EOF'
ls inputs | xargs -P <<jobs>> -I{} sh job.sh {}
EOF
sh run.sh
echo "ls inputs | parallel -j <<jobs>> sh job.sh {}" > parallel.txt""",
        ["""cat > run.sh <<'EOF'
ls inputs | xargs -I{} sh job.sh {}
EOF
sh run.sh
echo "ls inputs | parallel -j <<jobs>> sh job.sh {}" > parallel.txt""",
         """cat > run.sh <<'EOF'
ls inputs | head -3 | xargs -P <<jobs>> -I{} sh job.sh {}
EOF
sh run.sh
echo "ls inputs | parallel -j <<jobs>> sh job.sh {}" > parallel.txt"""],
        'xargs -P N は同時にN個まで起動、-n 1 は1回1引数、-I{} は置換文字列、-0 は find -print0 と組みます。GNU parallel は parallel -j N cmd {} ::: 引数… や、標準入力から。出力が混ざらない（グループ化される）のが利点です。',
        '並列度は -P、置換は -I{} です。', 'ls inputs | xargs -P N -I{} sh job.sh {}')


# ================================================================ 19 envsubst
def s19(ctx):
    host = 'app-' + secrets.token_hex(2) + '.example.test'
    port = 8000 + secrets.randbelow(900)
    up = f'10.0.0.{secrets.randbelow(200) + 2}:{port + 1}'
    tpl = ('server {\n    listen ${PORT};\n    server_name ${HOST};\n    location / {\n        proxy_pass http://${UPSTREAM};\n'
           '        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n    }\n}\n')
    ctx.data.update(host=host, port=port, up=up)
    ctx.data['want'] = tpl.replace('${PORT}', str(port)).replace('${HOST}', host).replace('${UPSTREAM}', up)
    put(ctx, 'nginx.conf.tpl', tpl)
    rtxt(ctx, f'nginx.conf.tpl のテンプレートを envsubst（gettext パッケージの道具）で展開し nginx.conf を作る render.sh を書いて実行する。HOST={host} PORT={port} UPSTREAM={up}。nginx 自身の変数 $host と $remote_addr はそのまま残すこと（envsubst に置換対象の変数リストを渡す）。')


def c19(ctx):
    need_ro(ctx)
    t = ctx.need_file('render.sh')
    ctx.require(re.search(r"envsubst\s+(['\"])[^'\"]*PORT", t), "render.sh は envsubst '${HOST} ${PORT} ${UPSTREAM}' のように変数リストを渡します。")
    ctx.require(ctx.need_file('nginx.conf') == ctx.data['want'], 'nginx.conf が期待と違います。$host や $remote_addr が空になっていませんか。')


mission(19, 'envsubstとgettextでテンプレートを安全に展開する',
        'envsubst は gettext に含まれる、テンプレート内の ${VAR} を環境変数で置換するコマンドです。設定ファイルの量産に便利ですが、リストを渡さないと nginx の $host のような別用途の変数まで空にしてしまいます。',
        ['render.sh を作って実行', 'nginx.conf'], s19, c19,
        """cat > render.sh <<'EOF'
HOST=<<host>> PORT=<<port>> UPSTREAM=<<up>> envsubst '${HOST} ${PORT} ${UPSTREAM}' < nginx.conf.tpl > nginx.conf
EOF
sh render.sh""",
        ["""cat > render.sh <<'EOF'
HOST=<<host>> PORT=<<port>> UPSTREAM=<<up>> envsubst < nginx.conf.tpl > nginx.conf
EOF
sh render.sh""",
         """cat > render.sh <<'EOF'
sed -e 's/\\${HOST}/<<host>>/' -e 's/\\${PORT}/<<port>>/' nginx.conf.tpl > nginx.conf
EOF
sh render.sh"""],
        'envsubst \'${A} ${B}\' は指定した変数だけを置換します（シングルクォートで先にシェルに展開させないのが大事）。リストなしだとエクスポートされた全変数が対象で、未定義は空文字になります。--variables でテンプレート内の変数一覧を確認できます。',
        '変数リストをシングルクォートで渡します。', "VAR=… envsubst '${HOST} ${PORT} ${UPSTREAM}' < tpl > out")


# ================================================================ 20 entr watch direnv
def s20(ctx):
    sec = 'sk_live_' + secrets.token_hex(8)
    ctx.data.update(sec=sec, iv=2 + secrets.randbelow(8))
    envrc = f'# project env\nexport API_KEY={sec}\ncurl -fsSL http://setup.example.test/bootstrap.sh | sh\nPATH_add bin\nlayout python3\n'
    ctx.write('.envrc', envrc)
    ctx.write('.gitignore', '*.pyc\n')
    rtxt(ctx, f'(1) cmds.txt に2行：ファイル変更で自動再実行する entr（`ls *.py | entr -r python3 app.py` の形、-r は子プロセスを再起動）と、{ctx.data["iv"]}秒ごとに差分強調（-d）で `ss -tln` を繰り返す watch。(2) 危険な .envrc（direnv が cd で自動読込）を直す：秘密のAPI_KEYは .env.local へ移し（.gitignoreに追加）、.envrc からは dotenv .env.local で読む。curl|sh は削除し、PATH_add bin と layout python3 は残す。direnv allow はこの教材では実行しない。')


def c20(ctx):
    ls = cl(ctx, 'cmds.txt')
    ctx.require(len(ls) == 2, 'cmds.txt は2行です。')
    ctx.require(re.fullmatch(r'ls\s+\*\.py\s*\|\s*entr\s+-r\s+python3\s+app\.py', ls[0]), '1行目は ls *.py | entr -r python3 app.py')
    t = tk(ctx, ls[1])
    ctx.require(t[0] == 'watch' and str(ctx.data['iv']) in vals(t, '-n') and '-d' in t and 'ss' in ' '.join(t), '2行目は watch -n 秒 -d \'ss -tln\'')
    e = ctx.need_file('.envrc')
    ctx.require('curl' not in e and ctx.data['sec'] not in e, '.envrc から curl|sh と秘密の直書きを消します。')
    ls = [x.strip() for x in e.splitlines()]
    ctx.require('PATH_add bin' in ls and 'layout python3' in ls and 'dotenv .env.local' in ls, '.envrc に PATH_add bin / layout python3 / dotenv .env.local を残します。')
    ctx.require('API_KEY=' + ctx.data['sec'] in ctx.read('.env.local').split(), '.env.local に API_KEY=… を移します。')
    ctx.require('.env.local' in [x.strip() for x in ctx.need_file('.gitignore').splitlines()], '.gitignore に .env.local を追加します。')


mission(20, 'entr・watchの自動再実行とdirenvの.envrcを安全にする',
        '開発中の定型作業を自動化する道具と、その安全性の話です。entr はファイルの変更を検知してコマンドを再実行、watch は一定間隔で繰り返し実行します。direnv はディレクトリに入ると .envrc を自動で読み込むため、中身は危険で、秘密は別ファイルへ分けます。',
        ['cmds.txt', '.envrc を安全に直す'], s20, c20,
        """cat > cmds.txt <<'EOF'
ls *.py | entr -r python3 app.py
watch -n <<iv>> -d 'ss -tln'
EOF
grep '^export API_KEY' .envrc | sed 's/^export //' > .env.local
printf 'PATH_add bin\\nlayout python3\\ndotenv .env.local\\n' > .envrc
echo .env.local >> .gitignore""",
        ["""cat > cmds.txt <<'EOF'
ls *.py | entr python3 app.py
watch -n <<iv>> 'ss -tln'
EOF
grep '^export API_KEY' .envrc | sed 's/^export //' > .env.local
printf 'PATH_add bin\\nlayout python3\\ndotenv .env.local\\n' > .envrc
echo .env.local >> .gitignore""",
         """cat > cmds.txt <<'EOF'
ls *.py | entr -r python3 app.py
watch -n <<iv>> -d 'ss -tln'
EOF
sed -i '/curl/d' .envrc"""],
        'direnv は .envrc を初めて読むとき・変更されたときに direnv allow で明示的に許可するまで実行しません。これは「他人のリポジトリに cd しただけでコードが走る」危険を防ぐ仕組みです。allow の前に必ず中身を読み、curl | sh や秘密の直書き、.gitignore されていない .env を避けます。entr -r は常駐プロセスの再起動に使います。',
        '.envrc は「コード」です。中身を読んでから allow します。', 'entr と watch の1行を書き、秘密は .env.local へ移して .envrc は dotenv で読みます。')


# ================================================================ 21 pandoc ffmpeg imagemagick
def s21(ctx):
    br = secrets.choice([48, 64, 96])
    w = secrets.choice([640, 800, 1024])
    ctx.data.update(br=br, w=w)
    rtxt(ctx, f'convert.txt に3行（実行はしない）。(1) pandoc で report.md を単独文書（-s）・目次つき（--toc）で report.docx に変換。(2) ffmpeg で *.wav を for ループで1つずつ、Opus（-c:a libopus）{br}k（-b:a {br}k）の「元の名前.opus」へ変換（ファイル名は ${{f%.wav}}）。(3) imagemagick（magick。旧版は convert）で *.png を for ループで幅{w}（-resize {w}x）にして thumbs/ に「元の名前.jpg」で出力。')


def c21(ctx):
    br, w = ctx.data['br'], ctx.data['w']
    ls = cl(ctx, 'convert.txt')
    ctx.require(len(ls) == 3, 'convert.txt は3行です。')
    t = tk(ctx, ls[0])
    ctx.require(t[0] == 'pandoc' and 'report.md' in t and 'report.docx' in vals(t, '-o', '--output') and ('-s' in t or '--standalone' in t) and '--toc' in t, '(1) pandoc -s --toc report.md -o report.docx')
    ctx.require(re.search(rf'^for\s+f\s+in\s+\*\.wav\s*;\s*do\s+ffmpeg\s+.*-i\s+"\$f".*-c:a\s+libopus.*-b:a\s+{br}k.*"\$\{{f%\.wav\}}\.opus"\s*;\s*done$', ls[1]), '(2) for f in *.wav; do ffmpeg -i "$f" -c:a libopus -b:a Nk "${f%.wav}.opus"; done')
    ctx.require(re.search(rf'^for\s+f\s+in\s+\*\.png\s*;\s*do\s+(magick|convert)\s+"\$f"\s+-resize\s+{w}x\s+"thumbs/\$\{{f%\.png\}}\.jpg"\s*;\s*done$', ls[2]), '(3) for f in *.png; do magick "$f" -resize Wx "thumbs/${f%.png}.jpg"; done')


mission(21, 'pandoc・ffmpeg・imagemagickで一括変換の命令を設計する',
        '文書は pandoc、音声動画は ffmpeg、画像は ImageMagick（magick、旧名 convert）が定番です。一括変換は「for で1ファイルずつ・出力名を ${f%.拡張子} で作る」形にし、元ファイルを上書きしない設計が基本です。',
        ['convert.txt に3行'], s21, c21,
        """cat > convert.txt <<'EOF'
pandoc -s --toc report.md -o report.docx
for f in *.wav; do ffmpeg -i "$f" -c:a libopus -b:a <<br>>k "${f%.wav}.opus"; done
for f in *.png; do magick "$f" -resize <<w>>x "thumbs/${f%.png}.jpg"; done
EOF""",
        ["""cat > convert.txt <<'EOF'
pandoc report.md -o report.docx
ffmpeg -i *.wav -c:a libopus -b:a <<br>>k out.opus
magick *.png -resize <<w>>x thumbs/out.jpg
EOF""",
         """cat > convert.txt <<'EOF'
pandoc -s --toc report.md -o report.docx
for f in *.wav; do ffmpeg -i "$f" -c:a libopus -b:a 128k "${f%.wav}.opus"; done
for f in *.png; do magick "$f" -resize 100x "thumbs/${f%.png}.jpg"; done
EOF"""],
        'pandoc は -f 入力形式 -t 出力形式（省略時は拡張子で推測）。ffmpeg は -i が入力、出力ファイルは最後で、-c:a が音声コーデック、-b:a がビットレート。magick は IM7 の統合コマンドで、IM6 では convert。-resize 800x は幅だけ指定で縦横比維持です。',
        'ファイルが複数なので for ループと出力名の置換を使います。', 'for f in *.ext; do ツール "$f" … "${f%.ext}.新拡張子"; done')


# ================================================================ 22 compression
def s22(ctx):
    names = ['a.txt', 'b.csv', 'sub/c.log', 'cache.tmp', 'sub/x.tmp']
    for n in names:
        ctx.write('data/' + n, secrets.token_hex(20) * 20 + '\n')
    ctx.data['want'] = sorted('data/' + n for n in names if not n.endswith('.tmp'))
    ctx.write('logs.txt', ('2026-11-01 INFO ' + secrets.token_hex(4) + ' ok\n') * 400)
    ctx.data['h'] = hashlib.sha256(ctx.p('logs.txt').read_bytes()).hexdigest()
    rtxt(ctx, '(1) data/ を、.tmp ファイルを除いて bundle.zip にする（zip -r … -x \'*.tmp\'。確認は unzip -l）。(2) logs.txt を zstd -19 で logs.zst にする（元ファイルは残す）。(3) plan.json {"windows_share":..,"smallest_archive":..,"gzip_compatible_fast":..,"fast_modern":..} に、各用途に合う形式を zip / 7z / pigz / zstd から1つずつ選んで書く（windows_share=Windowsの相手にそのまま渡す、smallest_archive=サイズ最優先（7z -mx=9）、gzip_compatible_fast=gzip互換で多コア並列、fast_modern=高速で高圧縮率の新方式）。')


def c22(ctx):
    try:
        z = zipfile.ZipFile(ctx.p('bundle.zip'))
    except (OSError, zipfile.BadZipFile):
        ctx.fail('bundle.zip が見つからないか、zipとして壊れています。')
    ctx.require(sorted(n for n in z.namelist() if not n.endswith('/')) == ctx.data['want'], 'bundle.zip の中身は data/ 以下の .tmp 以外すべてです。')
    try:
        zs = ctx.p('logs.zst').read_bytes()
    except OSError:
        ctx.fail('logs.zst がありません。')
    ctx.require(zs[:4] == b'\x28\xb5\x2f\xfd', 'logs.zst が zstd 形式ではありません。')
    ctx.require(hashlib.sha256(ctx.p('logs.txt').read_bytes()).hexdigest() == ctx.data['h'], 'logs.txt は残してください（元を消さない）。')
    if shutil.which('zstd'):
        r = subprocess.run(['zstd', '-dc', 'logs.zst'], cwd=ctx.work, capture_output=True)
        ctx.require(hashlib.sha256(r.stdout).hexdigest() == ctx.data['h'], 'logs.zst の中身が logs.txt と一致しません。')
    ctx.require(rj(ctx, 'plan.json') == {'windows_share': 'zip', 'smallest_archive': '7z', 'gzip_compatible_fast': 'pigz', 'fast_modern': 'zstd'}, 'plan.json の選択が違います。')


mission(22, '7z・pigz・zstd・zip/unzipから圧縮形式を選んで使う',
        '圧縮形式は「誰が開くか・速度・圧縮率」で選びます。zip/unzip は互換性最強、7z は高圧縮、pigz は gzip 互換の並列版、zstd は高速かつ高圧縮の新しい標準です。実際に zip と zstd を使い、用途ごとの選択も書き出します。',
        ['bundle.zip', 'logs.zst', 'plan.json'], s22, c22,
        """zip -r -q bundle.zip data -x '*.tmp'
unzip -l bundle.zip > /dev/null
zstd -19 -q -o logs.zst logs.txt
cat > plan.json <<'EOF'
{"windows_share":"zip","smallest_archive":"7z","gzip_compatible_fast":"pigz","fast_modern":"zstd"}
EOF""",
        ["""zip -r -q bundle.zip data
zstd -19 -q -o logs.zst logs.txt
echo '{"windows_share":"7z","smallest_archive":"zip","gzip_compatible_fast":"zstd","fast_modern":"pigz"}' > plan.json""",
         """zip -r -q bundle.zip data -x '*.tmp'
zstd -19 -q --rm -o logs.zst logs.txt
echo '{"windows_share":"zip","smallest_archive":"7z","gzip_compatible_fast":"pigz","fast_modern":"zstd"}' > plan.json"""],
        'zip -r で再帰、-x で除外、unzip -l で内容確認（展開前に必ず）。7z a -mx=9 で最大圧縮、pigz は gzip と同じ形式を複数コアで作り、zstd は -1〜-19（--ultra で-22）と -T0（全コア）が使えます。zstd は既定で元ファイルを残します（--rm で削除）。',
        '互換性・サイズ・速度のうち何を優先するかで決めます。', 'zip -r bundle.zip data -x \'*.tmp\'、zstd -19 -o logs.zst logs.txt、plan.json は zip/7z/pigz/zstd')


# ================================================================ 23 rclone s3cmd tldr
def s23(ctx):
    bad = 's3.' + secrets.token_hex(2) + 'x.example.test'
    good = 's3.' + secrets.token_hex(2) + '.example.test'
    bk = 'bkt-' + secrets.token_hex(2)
    conf = ['[backup]', 'type = s3', 'provider = Other', 'access_key_id = AKIAFAKEFAKEFAKE', 'secret_access_key = fakefakefakefake', f'endpoint = https://{bad}']
    ctx.data.update(good=good, bk=bk, conf=conf)
    ctx.write('rclone.conf', '\n'.join(conf) + '\n')
    put(ctx, 'notes.txt', f'正しいエンドポイント: https://{good}\n')
    put(ctx, 'rclone.log', f'Failed to create file system for "backup:{bk}": dial tcp: lookup {bad}: no such host\n')
    ctx.write('photos/a.jpg', 'x')
    rtxt(ctx, f'rclone.log のエラーを読み、rclone.conf の endpoint を notes.txt の正しい値に直す（他の行は変えない）。次に cmds.txt に3行：(1) ローカル ./photos をリモート backup:{bk} へ sync する rclone を --dry-run で（まず予行）。(2) s3cmd で同じ内容を ./photos/ から s3://{bk}/photos/ へ sync する --dry-run。(3) rclone の使い方例を tldr で見るコマンド。')


def c23(ctx):
    need_ro(ctx)
    d = ctx.data
    want = list(d['conf'])
    want[-1] = f"endpoint = https://{d['good']}"
    ctx.require([x.rstrip() for x in ctx.need_file('rclone.conf').splitlines()] == want, 'rclone.conf は endpoint の行だけを正しい値に直します。')
    ls = cl(ctx, 'cmds.txt')
    ctx.require(len(ls) == 3, 'cmds.txt は3行です。')
    a = tk(ctx, ls[0])
    dst = f"backup:{d['bk']}"
    ctx.require(a[:2] == ['rclone', 'sync'] and '--dry-run' in a and dst in a and a.index('./photos') < a.index(dst) if './photos' in a and dst in a else False, 'rclone sync ./photos backup:バケット --dry-run（送り元が先）。')
    b = tk(ctx, ls[1])
    s3 = f"s3://{d['bk']}/photos/"
    ctx.require(b[:2] == ['s3cmd', 'sync'] and '--dry-run' in b and s3 in b and './photos/' in b and b.index('./photos/') < b.index(s3), 's3cmd sync --dry-run ./photos/ s3://…（送り元が先）。')
    c = tk(ctx, ls[2])
    ctx.require(c == ['tldr', 'rclone'], 'tldr rclone')


mission(23, 'rcloneとs3cmdのsyncを--dry-runで安全に試す',
        'rclone はクラウドストレージ全般、s3cmd は S3 互換向けの同期ツールです。sync は「宛先を送り元に合わせる」ため、向きを間違えると宛先のデータが消えます。必ず --dry-run で何が起きるか確認し、設定は rclone.conf のセクション名（backup:）で参照します。操作例は tldr で素早く調べられます。',
        ['rclone.conf を修正', 'cmds.txt に3行'], s23, c23,
        """sed -i 's#^endpoint = .*#endpoint = https://<<good>>#' rclone.conf
cat > cmds.txt <<'EOF'
rclone sync ./photos backup:<<bk>> --dry-run
s3cmd sync --dry-run ./photos/ s3://<<bk>>/photos/
tldr rclone
EOF""",
        ["""sed -i 's#^endpoint = .*#endpoint = https://<<good>>#' rclone.conf
cat > cmds.txt <<'EOF'
rclone sync backup:<<bk>> ./photos --dry-run
s3cmd sync --dry-run s3://<<bk>>/photos/ ./photos/
tldr rclone
EOF""",
         """sed -i 's#^endpoint = .*#endpoint = https://<<good>>#' rclone.conf
cat > cmds.txt <<'EOF'
rclone sync ./photos backup:<<bk>>
s3cmd sync ./photos/ s3://<<bk>>/photos/
tldr rclone
EOF"""],
        'rclone sync 送り元 宛先 は宛先を送り元に一致させ、余分な宛先ファイルを削除します。コピーだけなら rclone copy。--dry-run（-n）でログだけ出して変更しません。設定は rclone config file で場所を確認し、[remote名] セクションの type/provider/endpoint/認証情報を読みます。認証情報を含むので共有やGit登録に注意します。',
        '方向（送り元が先）と --dry-run、設定の1行だけを直します。', 'sed で endpoint を直し、rclone sync ./photos backup:バケット --dry-run などを書きます。')


# ================================================================ 24 sqlite3
def s24(ctx):
    import sqlite3
    names = ['sato', 'ito', 'kato', 'mori']
    tot = secrets.SystemRandom().sample(range(100, 2000), 4)
    p = ctx.p('shop.db')
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p)
    db.execute('CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT)')
    db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER, amount INTEGER)')
    for i, n in enumerate(names, 1):
        db.execute('INSERT INTO customers VALUES(?,?)', (i, n))
        a = tot[i - 1] // 2
        db.execute('INSERT INTO orders(customer_id,amount) VALUES(?,?)', (i, a))
        db.execute('INSERT INTO orders(customer_id,amount) VALUES(?,?)', (i, tot[i - 1] - a))
    db.commit()
    db.close()
    ctx.data['dbh'] = hashlib.sha256(p.read_bytes()).hexdigest()
    ctx.data['want'] = ['name,total'] + [f'{n},{t}' for t, n in sorted(zip(tot, names), reverse=True)]
    rtxt(ctx, 'shop.db（SQLite）の顧客ごとの注文合計を、合計の大きい順に result.csv（見出し name,total）へ出す。sqlite3 CLI の手順を session.sql に書く（.tables と .schema orders でまず構造確認、.headers on、.mode csv、.output result.csv、続けて SELECT）。sqlite3 コマンドが無い環境は python3 の sqlite3 モジュールで同じ結果を作る。shop.db は変更しない。')


def c24(ctx):
    ctx.require(hashlib.sha256(ctx.p('shop.db').read_bytes()).hexdigest() == ctx.data['dbh'], 'shop.db は読み取りだけにします。')
    s = ctx.need_file('session.sql')
    ctx.require(all(k in s for k in ('.tables', '.schema', '.mode csv', '.headers on', '.output result.csv')) and 'SELECT' in s.upper() and 'GROUP BY' in s.upper(), 'session.sql に .tables .schema .mode csv .headers on .output と GROUP BY つきSELECTを書きます。')
    got = [x.strip() for x in ctx.need_file('result.csv').splitlines() if x.strip()]
    ctx.require(got == ctx.data['want'], 'result.csv が違います（見出し・合計の降順）。')


mission(24, 'sqlite3 CLIの.tables .schema .mode csvで集計する',
        'sqlite3 コマンドは、ドットコマンド（.tables で表一覧、.schema で定義、.mode csv で出力形式、.headers on、.output でファイル出力）と普通のSQLを使います。コマンドが無い環境でも python3 の sqlite3 モジュールで同じことができます。',
        ['session.sql', 'result.csv'], s24, c24,
        """cat > session.sql <<'EOF'
.tables
.schema orders
.headers on
.mode csv
.output result.csv
SELECT c.name AS name, SUM(o.amount) AS total FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.id ORDER BY total DESC, name;
EOF
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 shop.db < session.sql
else
python3 - <<'PY'
import sqlite3, csv
db = sqlite3.connect('file:shop.db?mode=ro', uri=True)
cur = db.execute('SELECT c.name AS name, SUM(o.amount) AS total FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.id ORDER BY total DESC, name')
with open('result.csv', 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\\n')
    w.writerow(['name', 'total'])
    w.writerows(cur)
PY
fi""",
        ["""cat > session.sql <<'EOF'
.tables
.schema orders
.headers on
.mode csv
.output result.csv
SELECT name, amount FROM customers, orders;
EOF
printf 'name,total\\nsato,1\\n' > result.csv""",
         """cat > session.sql <<'EOF'
.headers on
.mode csv
SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON o.customer_id=c.id GROUP BY c.id;
EOF
printf 'name,total\\n' > result.csv"""],
        'sqlite3 shop.db \'.tables\' のようにワンライナー、またはファイルを < で流します。.mode csv/column/json で出力形式、.headers on で見出し、.output ファイル で出力先を切替え、.schema 表名 で CREATE 文を確認します。読み取り専用は file:…?mode=ro。',
        '先に構造確認、次に出力形式、最後にSQLです。', 'session.sql にドットコマンドとSQLを書き、sqlite3 か python3 で結果を作ります。')


# ================================================================ 25 PS1 bashrc aliases
def s25(ctx):
    ctx.write('home/.bashrc', '# ~/.bashrc (サンプル)\ncase $- in\n    *i*) ;;\n      *) return;;\nesac\nHISTSIZE=1000\nPS1=\'$ \'\n')
    ctx.mkdir('scratch')
    ctx.write('requirements.txt', 'home/.bashrc（= ~/.bashrc）と home/.bash_aliases（= ~/.bash_aliases）を編集する。(1) ~/.bashrc の末尾で、緑の ユーザ@ホスト、青の 作業ディレクトリ を表示する PS1 を設定（\\u \\h \\w と \\$、色は \\[ \\e[32m \\] のように \\[ \\] で囲む。末尾は "\\$ "）。(2) ~/.bash_aliases があれば読み込む行を ~/.bashrc に追加。(3) ~/.bash_aliases に alias ll=\'ls -alF\' と、ディレクトリを作って移動する関数 mkcd を定義。\n')
    ctx.data['home_ok'] = True


def c25(ctx):
    home = str(ctx.p('home'))
    b = ctx.need_file('home/.bashrc')
    ctx.require('.bash_aliases' in b, '.bashrc から ~/.bash_aliases を読み込みます。')
    env = {'HOME': home, 'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'TERM': 'xterm'}
    cmd = 'echo "PS1=[$PS1]"; alias ll; mkcd a/b && pwd'
    r = subprocess.run(['bash', '--noprofile', '--rcfile', home + '/.bashrc', '-i', '-c', cmd], cwd=ctx.p('scratch'), env=env,
                       capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    out = r.stdout
    m = re.search(r'PS1=\[(.*)\]\n', out, re.S)
    ctx.require(m is not None, 'bash が .bashrc を読めませんでした。構文エラーはありませんか: ' + r.stderr[-120:])
    ps1 = m.group(1)
    ctx.require('\\u' in ps1 and '\\h' in ps1 and '\\w' in ps1 and ps1.endswith('\\$ '), 'PS1 に \\u \\h \\w を入れ、末尾は \\$ とスペースです。')
    ctx.require(ps1.count('\\[') == ps1.count('\\]') and ps1.count('\\[') >= 2, '色の制御文字は \\[ と \\] で囲みます（囲まないと行編集がずれる）。')
    ctx.require("alias ll='ls -alF'" in out, 'alias ll=\'ls -alF\' が有効になっていません（.bash_aliases の読み込みと定義）。')
    ctx.require(out.strip().splitlines()[-1].endswith('scratch/a/b'), 'mkcd a/b で作成と移動ができる関数にします。')


mission(25, 'PS1・~/.bashrc・~/.bash_aliasesでシェルを整える',
        'シェルの使い勝手は設定ファイルで決まります。~/.bashrc に PS1（プロンプト）と読み込み設定を書き、~/.bash_aliases にエイリアスや関数を分けて置くのが定番です。非表示文字の色指定は \\[ \\] で囲むのが約束です。ここでは本物のbashで読み込んで検証します（実際の ~ は使いません）。',
        ['home/.bashrc', 'home/.bash_aliases'], s25, c25,
        """cat >> home/.bashrc <<'EOF'
PS1='\\[\\e[32m\\]\\u@\\h\\[\\e[0m\\]:\\[\\e[34m\\]\\w\\[\\e[0m\\]\\$ '
if [ -f ~/.bash_aliases ]; then . ~/.bash_aliases; fi
EOF
cat > home/.bash_aliases <<'EOF'
alias ll='ls -alF'
mkcd() { mkdir -p -- "$1" && cd -- "$1"; }
EOF""",
        ["""cat >> home/.bashrc <<'EOF'
PS1='\\e[32m\\u@\\h\\e[0m:\\w\\$ '
if [ -f ~/.bash_aliases ]; then . ~/.bash_aliases; fi
EOF
cat > home/.bash_aliases <<'EOF'
alias ll='ls -alF'
mkcd() { mkdir -p -- "$1" && cd -- "$1"; }
EOF""",
         """cat >> home/.bashrc <<'EOF'
PS1='\\[\\e[32m\\]\\u@\\h\\[\\e[0m\\]:\\[\\e[34m\\]\\w\\[\\e[0m\\]\\$ '
EOF
cat > home/.bash_aliases <<'EOF'
alias ll='ls -alF'
mkcd() { mkdir -p -- "$1" && cd -- "$1"; }
EOF"""],
        'ログインシェルは ~/.profile、対話シェルは ~/.bashrc を読みます。Debian系の既定 .bashrc には ~/.bash_aliases の読み込みが含まれる場合が多いです。PS1 のエスケープ：\\u ユーザ、\\h ホスト、\\w 作業ディレクトリ、\\$ 一般は$・rootは#。エイリアスは引数を途中に使えないので、そのような処理は関数にします。',
        'PS1 は後に書いた代入が有効になります。', '末尾に PS1 と読み込み行を追記し、.bash_aliases に alias と関数を書きます。')


# ================================================================ 26 dotfiles stow bare
def s26(ctx):
    ctx.write('home/.vimrc', 'set number\n' + secrets.token_hex(4) + '\n')
    ctx.write('home/.gitconfig', '[user]\n\tname = Trainee\n\temail = t' + secrets.token_hex(2) + '@example.test\n')
    ctx.mkdir('dotfiles')
    ctx.data['vim'] = ctx.read('home/.vimrc')
    ctx.data['git'] = ctx.read('home/.gitconfig')
    rtxt(ctx, 'home/ にある .vimrc と .gitconfig を GNU stow 方式で管理する。(1) dotfiles/vim/.vimrc と dotfiles/git/.gitconfig に実体を移し、home/ 側は stow が作るのと同じ相対シンボリックリンクにする（stow が無い想定で手で再現）。(2) stow.txt に実機での stow コマンド1行（-d dotfiles -t home -v vim git の形でも cd して -t ../home でも可）。(3) もう一つの方式、bare repo 方式の手順を bare.txt に：git init --bare $HOME/.dotfiles、alias dot=\'git --git-dir=$HOME/.dotfiles --work-tree=$HOME\'、dot config status.showUntrackedFiles no。')


def c26(ctx):
    for pkg, f, k in (('vim', '.vimrc', 'vim'), ('git', '.gitconfig', 'git')):
        real = f'dotfiles/{pkg}/{f}'
        ctx.require(ctx.isfile(real) and not os.path.islink(ctx.p(real)) and ctx.read(real) == ctx.data[k], f'{real} に実体（元の内容）を置きます。')
        ln = ctx.p('home/' + f)
        ctx.require(os.path.islink(ln), f'home/{f} はシンボリックリンクにします。')
        tgt = os.readlink(ln)
        ctx.require(not os.path.isabs(tgt) and os.path.realpath(ln) == os.path.realpath(ctx.p(real)), 'リンクは stow と同じ相対パス（../dotfiles/…）で実体を指します。')
    ls = cl(ctx, 'stow.txt')
    ctx.require(len(ls) == 1 and re.search(r'\bstow\b', ls[0]) and re.search(r'\s-t\s*\S+', ls[0]) and re.search(r'\bvim\b', ls[0]) and re.search(r'\bgit\b', ls[0]), 'stow.txt は stow -t ターゲット vim git を含む1行です。')
    b = ctx.need_file('bare.txt')
    ctx.require(re.search(r'git init --bare\s+\S*\.dotfiles', b) and '--git-dir=$HOME/.dotfiles' in b and '--work-tree=$HOME' in b and re.search(r'status\.showUntrackedFiles\s+no', b), 'bare.txt に init --bare・alias（--git-dir/--work-tree）・status.showUntrackedFiles no を書きます。')


mission(26, 'dotfilesをGNU stowとbare repoで管理する',
        'dotfiles（~/.vimrc などの設定）をGitで管理する定番は2つです。GNU stow は「パッケージ別ディレクトリ」を置き、そこから home へシンボリックリンクを張ります。もう一つの bare repo 方式は、$HOME 自体を作業ツリーにして .git を別の場所（bare repo）に置きます。',
        ['stow 配置の再現', 'stow.txt', 'bare.txt'], s26, c26,
        """mkdir -p dotfiles/vim dotfiles/git
mv home/.vimrc dotfiles/vim/.vimrc
mv home/.gitconfig dotfiles/git/.gitconfig
ln -s ../dotfiles/vim/.vimrc home/.vimrc
ln -s ../dotfiles/git/.gitconfig home/.gitconfig
echo 'stow -d dotfiles -t home -v vim git' > stow.txt
cat > bare.txt <<'EOF'
git init --bare $HOME/.dotfiles
alias dot='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
dot config status.showUntrackedFiles no
EOF""",
        ["""mkdir -p dotfiles/vim dotfiles/git
cp home/.vimrc dotfiles/vim/.vimrc
cp home/.gitconfig dotfiles/git/.gitconfig
echo 'stow -d dotfiles -t home -v vim git' > stow.txt
echo 'git init --bare $HOME/.dotfiles' > bare.txt""",
         """mkdir -p dotfiles/vim dotfiles/git
mv home/.vimrc dotfiles/vim/.vimrc
mv home/.gitconfig dotfiles/git/.gitconfig
ln -s "$PWD/dotfiles/vim/.vimrc" home/.vimrc
ln -s "$PWD/dotfiles/git/.gitconfig" home/.gitconfig
echo 'stow -d dotfiles -t home -v vim git' > stow.txt
cat > bare.txt <<'EOF'
git init --bare $HOME/.dotfiles
alias dot='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
dot config status.showUntrackedFiles no
EOF"""],
        'stow は「パッケージ内のパス＝ターゲット内のパス」で相対リンクを作ります（stow -n で予行、-D で解除）。既に実ファイルがあると衝突するため、先に退避が必要。bare repo 方式はリンク不要で、status.showUntrackedFiles no を設定しないとホーム全体が未追跡として表示されます。',
        'リンクは相対パス（../）で張るのが stow の形です。', 'mv で実体を移し ln -s ../dotfiles/パッケージ/ファイル home/ファイル。')
