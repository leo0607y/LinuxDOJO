"""Stage 4: ネットワーク・通信デバッグ・アーカイブ操作（8問）"""
import io
import json
import os
import random
import re
import subprocess
import sys
import tarfile
import zipfile

from engine.runner import ROOT, register, proc_alive, wait_port, port_in_use

S = 4
SERVER = str(ROOT / "engine" / "servers.py")


def start_server(ctx, mode, port, **kw):
    argv = [sys.executable, SERVER, "--port", str(port), "--mode", mode]
    for k, v in kw.items():
        argv += [f"--{k}", str(v)]
    pid = ctx.spawn(f"server-{mode}", argv=argv)
    if not wait_port(port, 6):
        raise RuntimeError(f"test server did not start on {port}")
    return pid


def tar_members(path):
    try:
        with tarfile.open(path, "r:*") as t:
            return {m.name.lstrip("./"): m for m in t.getmembers()}, t
    except (OSError, tarfile.TarError):
        return None, None


# ------------------------------------------------------------------ 4-1
LOGS41 = {"logs/app.log": "app log\n" * 50, "logs/access.log": "access\n" * 80,
          "logs/2025/11/error.log": "error\n" * 10, "logs/.rotated": "1\n"}


def s41(ctx):
    for k, v in LOGS41.items():
        ctx.write(k, v)
    sql = f"customers_{random.randint(2023, 2025)}{random.randint(1, 12):02d}{random.randint(10, 28)}.sql"
    ctx.data["sql"] = sql
    buf = ctx.p("received.tar.gz")
    with tarfile.open(buf, "w:gz") as t:
        for name, data in {"export/README.txt": b"from partner\n", "export/images/logo.png": b"\x89PNG....",
                           f"export/db/{sql}": b"INSERT INTO customers VALUES (1,'x');\n",
                           "export/config/settings.json": b"{}\n"}.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))


def c41(ctx):
    p = ctx.p("logs_backup.tar.gz")
    if not p.exists():
        ctx.fail("`logs_backup.tar.gz` がまだありません。")
    with open(p, "rb") as f:
        if f.read(2) != b"\x1f\x8b":
            ctx.fail("`logs_backup.tar.gz` が gzip 圧縮されていません。`z` オプションを付けましょう。")
    try:
        with tarfile.open(p, "r:gz") as t:
            names = {m.name.lstrip("./").rstrip("/") for m in t.getmembers()}
    except tarfile.TarError:
        ctx.fail("`logs_backup.tar.gz` が tar アーカイブとして読めません。")
    for k in LOGS41:
        if k not in names:
            ctx.fail(f"アーカイブの中に `{k}` が入っていません（`logs/` ディレクトリごと固めましょう）。")
    if ctx.exists(f"export/db/{ctx.data['sql']}"):
        ctx.fail("`received.tar.gz` を展開してしまったようです。今回は **展開せずに** 中身の一覧だけを確認してください（`rm -rf export` してから再挑戦）。")
    ctx.need_submit(ctx.data["sql"], "SQLファイル名", normalize=lambda s: os.path.basename(s.strip()))


register(
    id="4-1", stage=S, title="tar で固める・覗く",
    story="""
ログをバックアップサーバーへ送る前に、`logs/` ディレクトリを **1つの圧縮ファイル** にまとめたい。
また、取引先から届いた `received.tar.gz` に **どんなSQLファイルが入っているか**、
（ウイルスの可能性もあるので）**展開せずに** 中身の一覧だけ確認してほしい。
""",
    objectives=["`logs/` ディレクトリを丸ごと gzip 圧縮して `logs_backup.tar.gz` を作る",
                "`received.tar.gz` を **展開せずに** 中身を一覧表示し、入っている `.sql` ファイルの名前を `submit` する"],
    hints=["tar は「c=作る」「x=展開」「t=一覧」が主役。`z` で gzip、`v` で詳細表示、`f` でファイル名指定です。",
           "作成は `tar czvf 出力.tar.gz 対象`、一覧は `tar tzvf ファイル.tar.gz`（t = list）。",
           "`tar czvf logs_backup.tar.gz logs/` → `tar tzvf received.tar.gz | grep .sql` → ファイル名を `submit`。"],
    answer="tar czvf logs_backup.tar.gz logs/\ntar tzvf logs_backup.tar.gz         # 作ったアーカイブの確認\ntar tzvf received.tar.gz | grep sql\nsubmit <<sql>>",
    explanation="""
tar のオプションは「動作 + 修飾」の組み合わせ:
  ・動作: `c` (create 作成) ／ `x` (extract 展開) ／ `t` (list 一覧)
  ・修飾: `z` (gzip) ／ `j` (bzip2) ／ `J` (xz) ／ `v` (verbose 詳細表示) ／ `f ファイル名`（**f は最後に置く**）
  ・`tar czvf a.tar.gz dir/` … 作成 ／ `tar tzvf a.tar.gz` … 中身確認 ／ `tar xzvf a.tar.gz` … 展開
  ・`-C ディレクトリ` … 展開先の指定（次の問題で！）
最近の GNU tar は展開時に圧縮形式を自動判別するので `tar xf a.tar.gz` でも展開できます。
""",
    tip="""
⚠ 知らないアーカイブをいきなり展開すると、カレントにファイルが散らばったり（tar bomb）、
`../../etc/passwd` のようなパスで既存ファイルを上書きされる危険があります。**まず `tar tzvf` で中身を確認** が鉄則です。
`tar czf - dir | ssh server 'tar xzf - -C /backup'` のように、パイプで送りながら固める合わせ技も現場の定番です。
""",
    setup=s41, check=c41,
    solution='tar czvf logs_backup.tar.gz logs/\nsubmit "$(tar tzf received.tar.gz | grep "\\.sql$" | xargs basename)"',
    wrong=['tar cvf logs_backup.tar.gz logs/\nsubmit "$(tar tzf received.tar.gz | grep "\\.sql$" | xargs basename)"',
           'tar czvf logs_backup.tar.gz logs/\ntar xzf received.tar.gz\nsubmit "$(tar tzf received.tar.gz | grep "\\.sql$" | xargs basename)"',
           "tar czvf logs_backup.tar.gz logs/app.log\nsubmit x.sql"],
)


# ------------------------------------------------------------------ 4-2
REL = {"app/main.py": "print('v2.0')\n", "app/lib/util.py": "def f(): pass\n", "VERSION": "2.0.0\n"}
DOCS = {"docs/index.md": "# Docs\n", "docs/api/users.md": "## Users API\n", "docs/img/arch.svg": "<svg/>\n"}
ASSETS = {"logo.png": b"\x89PNG fake", "fonts/noto.ttf": b"TTF fake", "css/site.css": b"body{}\n"}


def s42(ctx):
    with tarfile.open(ctx.p("release.tar.gz"), "w:gz") as t:
        for k, v in REL.items():
            data = v.encode()
            ti = tarfile.TarInfo(k)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    for k, v in DOCS.items():
        ctx.write(k, v)
    with zipfile.ZipFile(ctx.p("assets.zip"), "w") as z:
        for k, v in ASSETS.items():
            z.writestr(k, v)


def c42(ctx):
    for k, v in REL.items():
        if ctx.exists(k):
            ctx.fail(f"`{k}` がカレントディレクトリに展開されています。展開先を `releases/v2.0/` に指定しましょう（`rm -rf app VERSION` で片付けてから）。")
        if ctx.read(f"releases/v2.0/{k}") != v:
            ctx.fail(f"`releases/v2.0/{k}` がありません。`release.tar.gz` を `releases/v2.0/` の中に展開しましょう。")
    p = ctx.p("docs.zip")
    if not p.exists():
        ctx.fail("`docs.zip` がまだありません。")
    try:
        with zipfile.ZipFile(p) as z:
            names = {n.rstrip("/") for n in z.namelist()}
    except zipfile.BadZipFile:
        ctx.fail("`docs.zip` が zip ファイルとして読めません。")
    for k in DOCS:
        if k not in names:
            ctx.fail(f"`docs.zip` の中に `{k}` がありません。サブディレクトリも含めるオプションを付けましょう。")
    for k, v in ASSETS.items():
        q = ctx.p(f"assets/{k}")
        if not q.exists() or q.read_bytes() != v:
            ctx.fail(f"`assets/{k}` がありません。`assets.zip` を `assets/` ディレクトリに展開しましょう。")


register(
    id="4-2", stage=S, title="展開先を指定せよ（tar -C と zip/unzip）",
    story="""
新バージョンのリリースアーカイブ `release.tar.gz` を、決められた場所 `releases/v2.0/` に展開したい。
カレントに直接展開してゴチャゴチャにするのはNGだ。
さらに Windows ユーザー向けに `docs/` を zip にまとめ、デザイナーから届いた `assets.zip` も `assets/` に展開してほしい。
""",
    objectives=["`release.tar.gz` を `releases/v2.0/` ディレクトリの中に展開する（カレントには展開しない）",
                "`docs/` ディレクトリをサブディレクトリごと `docs.zip` に圧縮する",
                "`assets.zip` を `assets/` ディレクトリの中に展開する"],
    hints=["tar は展開先ディレクトリを指定するオプションがあります（展開先は事前に作っておく必要あり）。zip はディレクトリを含めるのにオプションが要ります。",
           "`mkdir -p` → `tar xzvf ファイル -C 展開先`。`zip -r 出力.zip ディレクトリ`。`unzip ファイル.zip -d 展開先`。",
           "`mkdir -p releases/v2.0 && tar xzvf release.tar.gz -C releases/v2.0` / `zip -r docs.zip docs/` / `unzip assets.zip -d assets`"],
    answer="tar tzvf release.tar.gz                 # まず中身を確認\nmkdir -p releases/v2.0\ntar xzvf release.tar.gz -C releases/v2.0\nzip -r docs.zip docs/\nunzip -l assets.zip                     # zip の中身確認\nunzip assets.zip -d assets",
    explanation="""
・`tar xzvf a.tar.gz -C dir` … `dir` の中に展開（`-C` = change directory。dir は事前に作成が必要）
・`zip -r out.zip dir/` … ディレクトリを再帰的に圧縮（`-r` を忘れると **空のディレクトリだけ** が入る）
・`unzip -l a.zip` … 中身の一覧 ／ `unzip a.zip -d dir` … 指定ディレクトリへ展開（dir は自動作成）
・`unzip -o` 上書き確認なし ／ `zip -e` パスワード付き
tar.gz と zip の使い分け: Linux 同士なら **tar.gz**（パーミッションやシンボリックリンクを保持）、
Windows の人に渡すなら **zip**（エクスプローラーで開ける）が無難です。
""",
    tip="""
`mkdir -p releases/v2.0 && tar xzf release.tar.gz -C releases/v2.0` の `&&` は「左が成功したら右を実行」。
デプロイスクリプトでよく見る書き方です（Extra Stage で詳しく！）。
アーカイブの1階層目を剥がして展開したいときは `tar xzf a.tar.gz --strip-components=1 -C dir` が便利です。
""",
    setup=s42, check=c42,
    solution="mkdir -p releases/v2.0\ntar xzvf release.tar.gz -C releases/v2.0\nzip -r docs.zip docs/\nunzip assets.zip -d assets",
    wrong=["tar xzvf release.tar.gz\nzip -r docs.zip docs/\nunzip assets.zip -d assets",
           "mkdir -p releases/v2.0\ntar xzvf release.tar.gz -C releases/v2.0\nzip docs.zip docs/\nunzip assets.zip -d assets",
           "mkdir -p releases/v2.0\ntar xzvf release.tar.gz -C releases/v2.0\nzip -r docs.zip docs/\nunzip assets.zip"],
)


# ------------------------------------------------------------------ 4-3
def s43(ctx):
    port = ctx.free_port(18000, 18999)
    ver = f"{random.randint(2, 4)}.{random.randint(0, 20)}.{random.randint(0, 9)}"
    token = ctx.rand(10)
    ctx.data.update(port=port, ver=ver, token=token)
    start_server(ctx, "api", port, token=token, version=ver)
    ctx.write("API_INFO.txt", f"Penguin API サーバー: http://localhost:{port}\nエンドポイント: /api/status  /api/health\n")


def c43(ctx):
    t = ctx.read("status.json")
    if t is None:
        ctx.fail("`status.json` がまだありません。")
    if "% Total" in t or "Dload" in t:
        ctx.fail("`status.json` に curl の進捗表示が混ざっています。`-s` (silent) を付けるか `-o` で保存しましょう。")
    try:
        d = json.loads(t)
    except ValueError:
        if t.startswith("HTTP/"):
            ctx.fail("`status.json` にレスポンスヘッダが混ざっています。本文だけを保存しましょう（`-i` は付けない）。")
        ctx.fail("`status.json` の中身が JSON として読めません。`/api/status` のレスポンス本文をそのまま保存しましょう。")
    if d.get("token") != ctx.data["token"]:
        ctx.fail("`status.json` の内容が `/api/status` のレスポンスと一致しません。")
    ctx.need_submit(ctx.data["ver"], "X-Server-Version の値")


register(
    id="4-3", stage=S, title="curl で API を叩く（GET とヘッダ確認）",
    story="""
社内API「Penguin API」が `http://localhost:<<port>>` で動いている。
動作確認のため、`/api/status` のレスポンスを **ファイルに保存** し、さらに `/api/health` の
**レスポンスヘッダ** に含まれる `X-Server-Version` の値（デプロイされているバージョン）を確認してほしい。
""",
    objectives=["`http://localhost:<<port>>/api/status` を GET し、レスポンス本文を `status.json` に保存する",
                "`http://localhost:<<port>>/api/health` の **レスポンスヘッダ** を表示し、`X-Server-Version` の値を `submit` する"],
    hints=["curl は URL を渡すだけで GET リクエストを送ります。本文の保存方法、ヘッダだけを見る方法はオプションで指定します。",
           "`-s` 進捗表示を消す、`-o ファイル` 保存、`-I` ヘッダだけ（HEADリクエスト）、`-i` ヘッダ＋本文、`-v` 通信の詳細。",
           "`curl -s http://localhost:<<port>>/api/status -o status.json` / `curl -I http://localhost:<<port>>/api/health`"],
    answer="curl -s http://localhost:<<port>>/api/status -o status.json\ncat status.json\ncurl -I http://localhost:<<port>>/api/health\nsubmit <<ver>>",
    explanation="""
curl の必修オプション:
  ・`-s` (silent) … 進捗メーターやエラーを消す（スクリプトで使うとき必須）／ `-S` と併用するとエラーだけは表示
  ・`-o file` … 本文をファイルへ保存（`> file` でも可）／ `-O` … URL の末尾の名前で保存
  ・`-I` (head) … **レスポンスヘッダだけ** を取得 ／ `-i` … ヘッダ＋本文
  ・`-v` (verbose) … リクエスト・レスポンスの詳細（TLS や リダイレクトのデバッグに）
  ・`-L` … リダイレクト（301/302）を追いかける ／ `-w '%{http_code}\\n'` … ステータスコードだけ表示
ヘッダには `Content-Type`・`Server`・キャッシュ制御・独自ヘッダ（`X-` で始まるもの）などの重要情報が詰まっています。
""",
    tip="""
ヘルスチェックの定番ワンライナー: `curl -s -o /dev/null -w '%{http_code}\\n' https://example.com` → 200 なら正常。
JSON を見やすく整形するには `curl -s URL | python3 -m json.tool` や `| jq .`（要インストール）が便利です。
「ブラウザでは見えるのに curl だと違う」ときは `-v` でリクエストヘッダを見比べるのが近道です。
""",
    setup=s43, check=c43,
    solution='curl -s http://localhost:<<port>>/api/status -o status.json\nsubmit "$(curl -sI http://localhost:<<port>>/api/health | grep -i x-server-version | cut -d" " -f2 | tr -d "\\r")"',
    wrong=["curl -i http://localhost:<<port>>/api/status > status.json\nsubmit <<ver>>",
           "curl -s http://localhost:<<port>>/api/status -o status.json\nsubmit 0.0.0"],
)


# ------------------------------------------------------------------ 4-4
def s44(ctx):
    port = ctx.free_port(18000, 18999)
    rec = ctx.state / "api_requests.jsonl"
    try:
        rec.unlink()
    except OSError:
        pass
    ctx.data.update(port=port, rec=str(rec))
    start_server(ctx, "api", port, record=rec, token=ctx.rand(8))
    ctx.write("new_user.json", '{"name": "penguin", "role": "admin"}\n')


def c44(ctx):
    try:
        reqs = [json.loads(ln) for ln in open(ctx.data["rec"]) if ln.strip()]
    except OSError:
        reqs = []
    if not reqs:
        ctx.fail("まだ `/api/users` に POST リクエストが届いていません。")
    for r in reversed(reqs):
        try:
            body = json.loads(r["body"])
        except ValueError:
            body = None
        if "application/json" in r["content_type"] and isinstance(body, dict) \
                and body.get("name") == "penguin" and body.get("role") == "admin":
            return
    last = reqs[-1]
    if "application/json" not in last["content_type"]:
        ctx.fail(f"リクエストは届きましたが Content-Type が `{last['content_type'] or 'なし'}` です。`-H 'Content-Type: application/json'` を付けましょう。")
    ctx.fail(f"リクエストは届きましたが、本文が期待と違います（受信: {last['body'][:80]}）。`{{\"name\":\"penguin\",\"role\":\"admin\"}}` を送りましょう。")


register(
    id="4-4", stage=S, title="curl で JSON を POST せよ",
    story="""
ユーザー登録APIのテストをしたい。`http://localhost:<<port>>/api/users` に、
新しいユーザー情報を **JSON 形式で POST** してほしい。フロントエンドが完成する前に、curl だけでAPIを検証するのはバックエンド開発の日常だ。
""",
    objectives=["`http://localhost:<<port>>/api/users` に **POST** メソッドでリクエストを送る",
                "本文は JSON `{\"name\": \"penguin\", \"role\": \"admin\"}`、ヘッダ `Content-Type: application/json` を付ける",
                "（レスポンスに `\"result\": \"created\"` が返れば成功）"],
    hints=["HTTPメソッドの指定、ヘッダの追加、本文の送信はそれぞれ別のオプションです。",
           "`-X POST` メソッド指定、`-H 'ヘッダ名: 値'` ヘッダ追加、`-d '本文'` データ送信（`-d @ファイル` でファイルから）。",
           "`curl -X POST -H 'Content-Type: application/json' -d '{\"name\":\"penguin\",\"role\":\"admin\"}' http://localhost:<<port>>/api/users`"],
    answer="curl -s -X POST http://localhost:<<port>>/api/users \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"name\": \"penguin\", \"role\": \"admin\"}'\n# 別解: ファイルから送る\ncurl -s -X POST -H 'Content-Type: application/json' -d @new_user.json http://localhost:<<port>>/api/users",
    explanation="""
・`-X POST` … HTTPメソッドを指定（GET/POST/PUT/PATCH/DELETE）。`-d` を付けると自動で POST になるので省略も可
・`-H 'Content-Type: application/json'` … 「本文は JSON です」とサーバーに伝える。**付け忘れると 415 や 400 エラー** の原因に
  （`-d` だけだと `application/x-www-form-urlencoded` として送られます）
・`-d '...'` … 本文。JSON の中の `"` と衝突しないよう、外側は **シングルクォート** で囲む
・`-d @file.json` … ファイルの中身を本文として送る（長いJSONに便利）
・長いコマンドは行末に `\\` を置くと改行して書けます。
最近の curl なら `--json '{"a":1}'` で Content-Type も自動設定されます（curl 7.82以降）。
""",
    tip="""
APIの不具合報告では「再現できる curl コマンド」を添えると開発者に感謝されます。
ブラウザの開発者ツールの Network タブで、リクエストを右クリック →「Copy as cURL」でそのまま curl コマンドにできます。
認証付きAPIは `-H 'Authorization: Bearer <トークン>'` の形で送るのが一般的です。
""",
    setup=s44, check=c44,
    solution="curl -s -X POST -H 'Content-Type: application/json' -d '{\"name\": \"penguin\", \"role\": \"admin\"}' http://localhost:<<port>>/api/users",
    wrong=["curl -s -X POST -d '{\"name\": \"penguin\", \"role\": \"admin\"}' http://localhost:<<port>>/api/users",
           "curl -s -X POST -H 'Content-Type: application/json' -d '{\"name\": \"penguin\"}' http://localhost:<<port>>/api/users",
           "curl -s http://localhost:<<port>>/api/users"],
)


# ------------------------------------------------------------------ 4-5
def s45(ctx):
    port = ctx.free_port(18000, 18999)
    ctx.data["port"] = port
    ctx.data["hog"] = start_server(ctx, "hog", port)
    ctx.write("start_app.sh", f"""#!/bin/bash
# Penguin Shop アプリ起動スクリプト（ポート {port} を使う）
if ! python3 -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", {port}))' 2>/dev/null; then
  echo "ERROR: [Errno 98] Address already in use: port {port}" >&2
  exit 1
fi
echo $$ > app.pid
exec python3 -m http.server {port} --bind 127.0.0.1 > app.log 2>&1
""", mode=0o755)


def c45(ctx):
    if proc_alive(ctx.data["hog"]):
        ctx.fail(f"ポート {ctx.data['port']} を占有している消し忘れプロセスがまだ動いています。`ss -tlnp` や `lsof -i :{ctx.data['port']}` で PID を調べましょう。")
    t = ctx.read("app.pid")
    if not t or not t.strip().isdigit() or not proc_alive(int(t.strip())):
        ctx.fail("ポートは空きました！ 次は `./start_app.sh &` でアプリをバックグラウンド起動しましょう。")
    if not port_in_use(ctx.data["port"]):
        ctx.fail("アプリがポートで待ち受けていません。`app.log` を確認してみましょう。")


register(
    id="4-5", stage=S, title="Address already in use を解決せよ",
    story="""
アプリを起動しようとしたら `ERROR: Address already in use: port <<port>>` と言われて起動できない！
誰かが開発中に立ち上げたサーバーを **消し忘れて** ポートを占有しているようだ。
犯人のプロセスを突き止めて停止し、正規のアプリを起動せよ。
""",
    objectives=["`./start_app.sh` を実行してエラーを確認する",
                "`ss` または `lsof` で、ポート <<port>> を LISTEN しているプロセスの PID を調べて停止する",
                "`./start_app.sh &` でアプリをバックグラウンド起動する"],
    hints=["「どのポートを、どのプロセスが待ち受けているか」を表示するコマンドがあります。",
           "`ss -tlnp`（t=TCP, l=LISTEN, n=数字表示, p=プロセス）や `lsof -i :ポート番号`。PID が分かったら `kill`。",
           "`ss -tlnp | grep <<port>>` → `users:((\"python3\",pid=XXXX,...))` の PID を `kill XXXX` → `./start_app.sh &`"],
    answer="./start_app.sh                  # → Address already in use\nss -tlnp | grep :<<port>>\nlsof -i :<<port>>               # 別解\nkill <<hog>>\n./start_app.sh &\ncurl -sI http://localhost:<<port>>/ | head -1",
    explanation="""
・`ss -tlnp` … TCP の LISTEN ソケットを数字表示＋プロセス付きで一覧（`-u` を足すと UDP も。`ss -tulnp` が定番）
  （他ユーザーのプロセス名を見るには `sudo` が必要）
・`lsof -i :8080` … そのポートを開いているプロセスを表示（list open files）
・`netstat -tlnp` … ss の前身。古いサーバーではこちらを使うことも（net-tools パッケージ）
・`fuser -k 8080/tcp` … ポートを使っているプロセスを一撃で kill する荒業
`Address already in use` は「同じポートで待ち受けられるのは1プロセスだけ」というルールに引っかかったエラーです。
""",
    tip="""
「Webサーバーが繋がらない」ときの切り分け: ① `ss -tlnp` でプロセスが LISTEN しているか → ② `curl localhost:ポート` で
ローカルから繋がるか → ③ ファイアウォール（`ufw status`）やクラウドのセキュリティグループ、の順に確認しましょう。
`127.0.0.1:8080` で LISTEN していると **外部からは繋がりません**（`0.0.0.0:8080` なら全インターフェースで待ち受け）。
""",
    setup=s45, check=c45,
    solution="kill $(lsof -t -i :<<port>> -sTCP:LISTEN)\nsleep 0.3\n./start_app.sh &\nsleep 1",
    wrong=["./start_app.sh &\nsleep 0.5", "kill $(lsof -t -i :<<port>> -sTCP:LISTEN)\nsleep 0.3"],
)


# ------------------------------------------------------------------ 4-6
def s46(ctx):
    ctx.write("README.txt", "ネットワーク疎通と名前解決の確認をしてください。\n")


def c46(ctx):
    t = ctx.read("ping.txt")
    if t is None:
        ctx.fail("`ping.txt` がまだありません。")
    m = re.search(r"(\d+) packets transmitted, (\d+) (packets )?received", t)
    if not m:
        ctx.fail("`ping.txt` に ping の統計（packets transmitted）がありません。回数を指定して終了させ、結果を保存しましょう。")
    if m.group(1) != "3":
        ctx.fail(f"ping の送信回数が {m.group(1)} 回です。ちょうど **3回** にしましょう。")
    if "127.0.0.1" not in t:
        ctx.fail("`127.0.0.1` に ping してください。")
    sub = (ctx.submitted() or "").strip().upper().rstrip(",")
    if sub == "NXDOMAIN":
        return
    if not sub:
        ctx.fail("ステータスをまだ提出していません。`submit <ステータス>` で提出してください。")
    # オフライン環境への配慮: この PC の dig が実際に返すステータスも正解として扱う
    actual = dig_status("nonexistent-penguin.invalid")
    if actual and sub == actual:
        return
    if actual is None:
        ctx.fail(f"提出されたステータス「{sub}」は正しくありません。"
                 "なお、この環境では DNS サーバーに問い合わせが届かないようです（オフライン？ `connection timed out` と出るなら DNS 不通）。"
                 "`.invalid` は「絶対に存在しない」予約ドメインなので、DNS が使える環境で返るのは「存在しない」を意味するステータスです（ヒント3参照）。")
    ctx.need_submit("NXDOMAIN", "ステータス", normalize=lambda s: s.strip().upper().rstrip(","))


def dig_status(name):
    """dig を実行して HEADER の status を返す。DNS に届かない（オフライン等）・dig が無い場合は None。"""
    try:
        r = subprocess.run(["dig", "+time=2", "+tries=1", name], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"status: ([A-Z]+)", r.stdout)
    return m.group(1) if m else None


register(
    id="4-6", stage=S, title="疎通確認と名前解決（ping / dig）",
    story="""
「サイトに繋がらない！」という問い合わせ。ネットワーク障害の切り分けは、**疎通（届くか）** と **名前解決（DNS）** の確認から。
まずは自分自身（ループバック）への疎通を確認し、次に DNS で **存在しないドメイン** を引いたときにどう見えるかを体験しよう。
""",
    objectives=["`127.0.0.1` へ **3回だけ** ping を送り、結果を `ping.txt` に保存する",
                "`dig` で `nonexistent-penguin.invalid` を問い合わせ、ヘッダの `status:` に表示される値を `submit` する"],
    hints=["Linux の ping は止めるまで永遠に送り続けます（Ctrl+C で停止）。回数を指定するオプションがあります。",
           "`ping -c 回数 宛先`。`dig ドメイン名` の出力の `->>HEADER<<-` 行の `status:` に注目（NOERROR / NXDOMAIN / SERVFAIL）。",
           "`ping -c 3 127.0.0.1 > ping.txt` / `dig nonexistent-penguin.invalid | grep status`（オフラインで status が出ない場合、正常時に返るのは `NXDOMAIN`）"],
    answer="ping -c 3 127.0.0.1 > ping.txt\ncat ping.txt\ndig nonexistent-penguin.invalid | grep status\nsubmit NXDOMAIN\n# 参考: getent hosts localhost / cat /etc/hosts / dig +short example.com",
    explanation="""
・`ping -c 3 host` … ICMP Echo を3回送る（`-c` = count）。`time=` が応答時間、`packet loss` が損失率
・`dig example.com` … DNS に問い合わせ。`status: NOERROR` 正常 ／ **`NXDOMAIN` = そのドメインは存在しない** ／ `SERVFAIL` = DNSサーバー側の障害
・`dig +short example.com` … IPアドレスだけ表示 ／ `dig example.com MX` … メールサーバー ／ `dig @8.8.8.8 example.com` … DNSサーバーを指定
・`nslookup` … dig の簡易版 ／ `getent hosts 名前` … **/etc/hosts も含めて** OS と同じ方法で名前解決
・`/etc/hosts` … DNS より先に参照されるローカルの名前表。`127.0.0.1 myapp.local` のように書くと開発用の名前が作れる
（`.invalid` は RFC で「絶対に存在しない」と決められた予約ドメインです）
""",
    tip="""
障害切り分けの定石: `ping IPアドレス` が通るのに `ping ドメイン名` が通らない → **DNS の問題**。
両方ダメ → ネットワーク経路の問題（`traceroute` / `mtr` で経路を調査）。ping は通るのに Web が見えない → アプリやポートの問題（前問の `ss` / `curl`）。
クラウドでは ICMP がファイアウォールで遮断されていることも多いので「ping が通らない＝落ちている」とは限りません。
""",
    setup=s46, check=c46,
    solution='ping -c 3 127.0.0.1 > ping.txt\nsubmit "$(dig nonexistent-penguin.invalid | grep -o "status: [A-Z]*" | cut -d" " -f2)"',
    wrong=["ping -c 5 127.0.0.1 > ping.txt\nsubmit NXDOMAIN", "ping -c 3 127.0.0.1 > ping.txt\nsubmit NOERROR"],
)


# ------------------------------------------------------------------ 4-7
PROJ = {"project/index.html": "<h1>v2</h1>\n", "project/css/site.css": "body{color:#333}\n",
        "project/js/app.js": "console.log('v2')\n", "project/img/logo.svg": "<svg/>\n"}


def s47(ctx):
    for k, v in PROJ.items():
        ctx.write(k, v)
    ctx.write("backup/index.html", "<h1>v1</h1>\n", age_days=30)
    ctx.write("backup/old_banner.png", "obsolete\n", age_days=30)
    ctx.write("backup/css/site.css", "body{}\n", age_days=30)
    ctx.write(".ssh/id_ed25519", "-----BEGIN OPENSSH PRIVATE KEY-----\n(dummy key for training)\n-----END OPENSSH PRIVATE KEY-----\n", mode=0o644)
    ctx.write(".ssh/id_ed25519.pub", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIdummy penguin@local\n", mode=0o644)
    os.chmod(ctx.p(".ssh"), 0o755)


def ssh_g(ctx):
    try:
        r = subprocess.run(["ssh", "-G", "-F", str(ctx.p(".ssh/config")), "web01"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None, "ssh コマンドが実行できません"
    if r.returncode != 0:
        return None, r.stderr.strip()
    out = {}
    for ln in r.stdout.splitlines():
        k, _, v = ln.partition(" ")
        out.setdefault(k, v)
    return out, ""


def c47(ctx):
    if not ctx.isfile(".ssh/config"):
        ctx.fail("`.ssh/config` がまだありません（この問題では本物の ~/.ssh ではなく、作業ディレクトリの `.ssh/` を使います）。")
    conf, err = ssh_g(ctx)
    if conf is None:
        ctx.fail(f"`.ssh/config` を ssh が読み込めません: {err}")
    want = {"hostname": "192.168.10.21", "user": "deploy", "port": "2222"}
    for k, v in want.items():
        if conf.get(k) != v:
            ctx.fail(f"`ssh web01` の設定で {k} が `{conf.get(k)}` になっています（期待: {v}）。`Host web01` ブロックの書き方を確認しましょう。")
    idf = conf.get("identityfile", "")
    if "id_ed25519" not in idf:
        ctx.fail("IdentityFile に `~/.ssh/id_ed25519` を指定してください。")
    if ctx.mode(".ssh") != 0o700:
        ctx.fail(f"`.ssh/` ディレクトリのパーミッションが {ctx.mode('.ssh'):03o} です。700 にしましょう。")
    for f in (".ssh/config", ".ssh/id_ed25519"):
        if ctx.mode(f) != 0o600:
            ctx.fail(f"`{f}` のパーミッションが {ctx.mode(f):03o} です。600 にしましょう（秘密鍵が他人に読めると ssh が使用を拒否します）。")
    if ctx.isdir("backup/project"):
        ctx.fail("`backup/project/` という入れ子ができています。rsync はコピー元の **末尾の `/`** の有無で挙動が変わります（`rm -rf backup/project` してやり直し）。")
    for k, v in PROJ.items():
        dst = k.replace("project/", "backup/", 1)
        if ctx.read(dst) != v:
            ctx.fail(f"`{dst}` が最新の `{k}` と一致しません。")
    if ctx.exists("backup/old_banner.png"):
        ctx.fail("コピー元に無い古いファイル `backup/old_banner.png` が残っています。完全なミラーにするオプションを付けましょう。")


register(
    id="4-7", stage=S, title="SSH の設定と rsync の差分同期",
    story="""
Webサーバー `web01`（IP: 192.168.10.21、ユーザー: deploy、ポート: 2222）に毎回
`ssh -i ~/.ssh/id_ed25519 -p 2222 deploy@192.168.10.21` と打つのは辛い。**SSH の設定ファイル** で `ssh web01` だけで繋がるようにしよう。
さらに、サイトのファイル `project/` を `backup/` へ **差分同期**（rsync）して、完全なミラーにしてほしい。
※ この問題では本物の `~/.ssh` は触らず、作業ディレクトリ内の `.ssh/` で練習します。
""",
    objectives=["`.ssh/config` に `Host web01` の設定（HostName 192.168.10.21 / User deploy / Port 2222 / IdentityFile ~/.ssh/id_ed25519）を書く",
                "`.ssh` ディレクトリを `700`、`.ssh/config` と秘密鍵 `.ssh/id_ed25519` を `600` にする",
                "`rsync` で `project/` の中身を `backup/` に同期し、`project/` に無い古いファイルは `backup/` から削除する"],
    hints=["SSH の設定ファイルは `Host 別名` の下にインデントして `キーワード 値` を並べる形式です。エディタ（nano/vim）か、ヒアドキュメント `cat > file <<'EOF'` で書けます。",
           "キーワードは `HostName` `User` `Port` `IdentityFile`。確認は `ssh -G -F .ssh/config web01`。rsync は `-a`(アーカイブ) `-v` `-z`(圧縮) `--delete`。",
           "`printf 'Host web01\\n  HostName 192.168.10.21\\n  User deploy\\n  Port 2222\\n  IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config` → `chmod 700 .ssh; chmod 600 .ssh/config .ssh/id_ed25519` → `rsync -avz --delete project/ backup/`"],
    answer="cat > .ssh/config <<'EOF'\nHost web01\n    HostName 192.168.10.21\n    User deploy\n    Port 2222\n    IdentityFile ~/.ssh/id_ed25519\nEOF\nchmod 700 .ssh\nchmod 600 .ssh/config .ssh/id_ed25519\nssh -G -F .ssh/config web01 | grep -E '^(hostname|user|port) '\nrsync -avz --delete --dry-run project/ backup/   # まず確認\nrsync -avz --delete project/ backup/",
    explanation="""
**~/.ssh/config** を書くと `ssh web01`・`scp file web01:/tmp/`・`rsync -av dir/ web01:/var/www/` のように **別名で全部繋がる** ようになります。
`ssh -G ホスト` は「その別名で接続するとき実際に使われる設定」を表示するデバッグ用オプションです（`-F` で設定ファイル指定）。
SSH はセキュリティに厳しく、`~/.ssh` が 700、秘密鍵が 600 でないと **鍵の使用を拒否** します。
rsync の要点:
  ・`-a` (archive) … 再帰・パーミッション・タイムスタンプ・リンクを保持 ／ `-v` 詳細 ／ `-z` 転送時に圧縮
  ・`--delete` … コピー元に無いファイルをコピー先から削除（完全ミラー）。**強力なので `--dry-run`(-n) で事前確認を！**
  ・⚠ `rsync project/ backup/` → 中身を同期 ／ `rsync project backup/` → `backup/project/` ができる（**末尾スラッシュの違い**）
  ・2回目以降は **差分だけ** を転送するので高速。`rsync -avz dir/ user@host:/path/` でリモートへも同じ書き方で同期可能
`scp file web01:/tmp/` は単純なコピー（毎回全量転送）。大量ファイルや再送には rsync が圧倒的に有利です。
""",
    tip="""
本番では `ssh-keygen -t ed25519` で鍵を作り、`ssh-copy-id web01` で公開鍵をサーバーに登録 → パスワードログインは無効化、が基本。
踏み台サーバー経由の接続も `~/.ssh/config` に `ProxyJump bastion` と1行書くだけで `ssh web01` 一発になります。
`rsync -avz --delete` はデプロイやバックアップの定番ですが、コピー元とコピー先を **逆に書くと全消し** の大事故。必ず `-n` で確認しましょう。
""",
    setup=s47, check=c47,
    solution="printf 'Host web01\\n    HostName 192.168.10.21\\n    User deploy\\n    Port 2222\\n    IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config\nchmod 700 .ssh\nchmod 600 .ssh/config .ssh/id_ed25519\nrsync -avz --delete project/ backup/",
    wrong=["printf 'Host web01\\n    HostName 192.168.10.21\\n    User deploy\\n    Port 2222\\n    IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config\nchmod 700 .ssh\nchmod 600 .ssh/config .ssh/id_ed25519\nrsync -avz project/ backup/",
           "printf 'Host web01\\n    HostName 192.168.10.21\\n    User deploy\\n    Port 2222\\n    IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config\nchmod 700 .ssh\nchmod 600 .ssh/config .ssh/id_ed25519\nrsync -avz --delete project backup/",
           "printf 'Host web01\\n    HostName 192.168.10.21\\n    User deploy\\n    IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config\nchmod 700 .ssh\nchmod 600 .ssh/config .ssh/id_ed25519\nrsync -avz --delete project/ backup/",
           "printf 'Host web01\\n    HostName 192.168.10.21\\n    User deploy\\n    Port 2222\\n    IdentityFile ~/.ssh/id_ed25519\\n' > .ssh/config\nrsync -avz --delete project/ backup/"],
)


# ------------------------------------------------------------------ 4-8
def s48(ctx):
    port = ctx.free_port(20000, 29999)
    token = "LQ-" + ctx.rand(12)
    ctx.data.update(port=port, token=token)
    start_server(ctx, "hidden", port, token=token)
    ctx.write("指令書.txt", "このマシンのどこかのポート(20000〜29999)で、トークン配布サーバー (python3) が動いている。\n"
                          "ポートを特定し、GET /api/token で得たトークンを token.txt に保存、submission.tar.gz に固めて提出せよ。\n")


def c48(ctx):
    p = ctx.p("submission.tar.gz")
    if not p.exists():
        if ctx.exists("token.txt"):
            if ctx.data["token"] in (ctx.read("token.txt") or ""):
                ctx.fail("トークンの取得は成功！ 最後に `token.txt` を `submission.tar.gz` に固めましょう。")
            ctx.fail("`token.txt` に正しいトークンが入っていません。")
        ctx.fail("`submission.tar.gz` がまだありません。まずはサーバーのポートを特定しましょう。")
    try:
        with tarfile.open(p, "r:gz") as t:
            mem = [m for m in t.getmembers() if m.isfile() and os.path.basename(m.name) == "token.txt"]
            if not mem:
                ctx.fail("`submission.tar.gz` の中に `token.txt` が入っていません。")
            data = t.extractfile(mem[0]).read().decode(errors="replace")
    except tarfile.TarError:
        ctx.fail("`submission.tar.gz` が gzip 圧縮された tar として読めません（`czf` を使いましょう）。")
    if ctx.data["token"] not in data:
        ctx.fail("`submission.tar.gz` 内の `token.txt` に正しいトークンが入っていません。")


register(
    id="4-8", stage=S, title="【実践】隠されたサーバーからトークンを奪取せよ",
    story="""
🕵️ 極秘指令: このマシンのどこか（ポート 20000〜29999 のどれか）で、**トークン配布サーバー** がひっそり動いている。
ポート番号は誰も知らない。`ss` でポートを突き止め、`curl` で `/api/token` を叩いてトークンを入手し、
`token.txt` に保存して `submission.tar.gz` に固めて提出せよ。
""",
    objectives=["`ss` で、LISTEN しているポートの中からトークン配布サーバー（python3）のポートを特定する",
                "`curl` で `http://localhost:<ポート>/api/token` を GET し、レスポンスを `token.txt` に保存する",
                "`token.txt` を `submission.tar.gz` に gzip 圧縮した tar で固める"],
    hints=["待ち受け中のポートとプロセス名を一覧するコマンドを思い出そう（前々問）。20000番台のポートで python3 が待っているはず。",
           "`ss -tlnp | grep python` でポートが分かります。取得は `curl -s URL > token.txt`、固めるのは `tar czf`。",
           "`ss -tlnp | grep python3` → `curl -s http://localhost:<ポート>/api/token > token.txt` → `tar czvf submission.tar.gz token.txt`"],
    answer="ss -tlnp | grep python3          # → 127.0.0.1:<<port>> ... python3\ncurl -s http://localhost:<<port>>/api/token > token.txt\ncat token.txt\ntar czvf submission.tar.gz token.txt\ntar tzvf submission.tar.gz",
    explanation="""
この問題は Stage 4 の総まとめです:
  ① **ss -tlnp** … LISTEN 中の TCP ポートとプロセスを一覧 → 20000番台で待ち受ける python3 を発見
  ② **curl -s** … 見つけたポートの API からトークンを取得し、`>` でファイルへ
  ③ **tar czvf** … 提出用にアーカイブ化（`tar tzvf` で中身を確認するまでがワンセット）
ポートが分からないときの別解: `lsof -i -P -n | grep LISTEN`、ブルートフォースなら
`for p in $(seq 20000 29999); do curl -s -m 0.2 localhost:$p/api/token && echo " <- $p"; done`（時間がかかるけど確実）。
""",
    tip="""
「どのプロセスがどのポートを使っているか」の把握は、セキュリティ監査でも重要です。
身に覚えのない LISTEN ポートがあったら、`ss -tlnp` → `ps -fp PID` → `ls -l /proc/PID/exe` で正体を追跡しましょう。
外部から開いているポートを確認するには `nmap`（許可された範囲でのみ！）を使います。
""",
    setup=s48, check=c48,
    solution="P=$(ss -tlnp | grep python3 | grep -oE '127.0.0.1:2[0-9]{4}' | cut -d: -f2 | while read p; do curl -s -m1 localhost:$p/api/token | grep -q token && echo $p; done | head -1)\ncurl -s http://localhost:$P/api/token > token.txt\ntar czvf submission.tar.gz token.txt",
    wrong=["curl -s http://localhost:<<port>>/api/token > token.txt", "echo dummy > token.txt\ntar czvf submission.tar.gz token.txt",
           "curl -s http://localhost:<<port>>/api/token > token.txt\ntar cvf submission.tar.gz token.txt"],
)
