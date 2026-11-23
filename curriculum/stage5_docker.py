"""Stage 5: Docker & コンテナ実践テクニック（7問）

本物の Docker デーモンが使える場合は実際のコンテナで、使えない場合は模擬 docker CLI
（シミュレーションモード）で同じ課題に取り組める。判定は engine.docker_backend 経由で行う。
"""
import os
import random
import shlex
import time

from engine.docker_backend import find, image_matches
from engine.runner import register

S = 5


def need_running(ctx, name, hint=""):
    c = find(ctx.docker.containers(), name)
    if not c:
        ctx.fail(f"コンテナ `{name}` が見つかりません。`--name {name}` を付けて起動しましょう。{hint}")
    if not c["running"]:
        ctx.fail(f"コンテナ `{name}` は存在しますが停止しています（{c['status']}）。`docker ps -a` と `docker logs {name}` で原因を確認しましょう。{hint}")
    return c


# ------------------------------------------------------------------ 5-1
def s51(ctx):
    ctx.docker.reset()
    ctx.write("README.txt", "nginx を lq-web という名前で、ホストの 8080 番 → コンテナの 80 番で公開してください。\n")


def c51(ctx):
    c = need_running(ctx, "lq-web", "（`-d` を付けないとフォアグラウンドに張り付き、Ctrl+C で止まってしまいます）")
    if not image_matches(c["image"], "nginx"):
        ctx.fail(f"`lq-web` のイメージが `{c['image']}` です。`nginx` イメージを使いましょう。")
    hp = c["ports"].get("80/tcp")
    if hp != "8080":
        if c["ports"].get("8080/tcp") == "80":
            ctx.fail("ポートの向きが逆です！ `-p ホスト側:コンテナ側` なので `-p 8080:80` です（`docker rm -f lq-web` してやり直し）。")
        ctx.fail(f"ポート公開が違います（現在: {c['ports'] or 'なし'}）。ホストの 8080 → コンテナの 80 を `-p 8080:80` で公開しましょう。")


register(
    id="5-1", stage=S, title="はじめてのコンテナ起動", docker=True,
    story="""
いよいよコンテナの世界へ！ まずは Web サーバー **nginx** をコンテナで動かしてみよう。
ブラウザから `http://localhost:8080` で見られるように、ホストの 8080 番ポートをコンテナの 80 番に繋ぐこと。
""",
    objectives=["`nginx` イメージから、名前 `lq-web` のコンテナを **バックグラウンド** で起動する",
                "ホストの `8080` 番ポートを、コンテナの `80` 番ポートに公開する",
                "`docker ps` で STATUS が `Up` になっていることを確認する"],
    hints=["`docker run` に「バックグラウンド実行」「名前」「ポート公開」の3つのオプションを付けます。",
           "`-d`（detach）でバックグラウンド、`--name 名前`、`-p ホスト側:コンテナ側` でポート公開。",
           "`docker run -d --name lq-web -p 8080:80 nginx` → `docker ps`"],
    answer="docker run -d --name lq-web -p 8080:80 nginx\ndocker ps\ncurl -s http://localhost:8080 | head -5   # 本物の Docker なら Welcome to nginx! が返る",
    explanation="""
`docker run [オプション] イメージ [コマンド]` は「イメージをダウンロード（無ければ）→ コンテナ作成 → 起動」を一度に行います。
  ・`-d` (detach) … バックグラウンドで実行し、コンテナIDだけを表示。**付けないとログに張り付き、Ctrl+C でコンテナが止まる**
  ・`--name lq-web` … 名前を付ける（付けないと `brave_turing` のようなランダム名になる）
  ・`-p 8080:80` … **ホスト側:コンテナ側**。「ホストの 8080 に来た通信をコンテナの 80 へ転送」
  ・`docker ps` … 実行中のコンテナ一覧 ／ `docker ps -a` … 停止中も含めて全部
同じ名前のコンテナは2つ作れません（Conflict エラー）。作り直すときは `docker rm -f lq-web` で消してから。
""",
    tip="""
`-p 8080:80` の向きは本当によく間違えます。「**外:中**」と覚えましょう。
`-p 127.0.0.1:8080:80` とすると自分のマシンからしかアクセスできなくなり、開発時のセキュリティ対策になります。
イメージは `nginx:1.27-alpine` のように **タグを明示** するのが本番の鉄則（`latest` は中身が勝手に変わる可能性がある）。
""",
    setup=s51, check=c51,
    solution="docker run -d --name lq-web -p 8080:80 nginx\ndocker ps",
    wrong=["docker run --name lq-web -p 8080:80 nginx", "docker run -d --name lq-web -p 80:8080 nginx",
           "docker run -d --name lq-web -p 8080:80 httpd"],
)


# ------------------------------------------------------------------ 5-2
def s52(ctx):
    ctx.docker.reset()
    code = f"E-{random.randint(1000, 9999)}"
    ctx.data["code"] = code
    logs = ("2025-11-18T09:00:01Z INFO  starting order-api v3.2.1\n"
            "2025-11-18T09:00:01Z INFO  loading config from /etc/order-api/config.toml\n"
            "2025-11-18T09:00:02Z WARN  config key 'timeout' is deprecated\n"
            f"2025-11-18T09:00:02Z FATAL failed to parse config: unexpected token at line 12 (error_code={code})\n"
            "2025-11-18T09:00:02Z INFO  shutting down\n")
    ctx.docker.add_container("lq-cache", "redis:7", running=True,
                             logs="1:M * Ready to accept connections tcp\n",
                             real_cmd=None)
    ctx.docker.add_container("lq-api", "alpine", cmd=["/app/order-api"], running=False, exit_code=1, logs=logs,
                             real_cmd=["sh", "-c", f"printf %s {shlex.quote(logs)}; exit 1"])


def c52(ctx):
    cs = ctx.docker.containers()
    if not find(cs, "lq-cache"):
        ctx.fail("警告: 動いていた `lq-cache` まで消えています！ 削除するのは停止した `lq-api` だけです（`reset_mission` でやり直し）。")
    ctx.need_submit(ctx.data["code"], "エラーコード")
    if find(cs, "lq-api"):
        ctx.fail("エラーコードは正解！ 原因を記録したので、停止したままの `lq-api` コンテナを削除して片付けましょう。")


register(
    id="5-2", stage=S, title="消えたコンテナの死因を探れ", docker=True,
    story="""
「注文APIのコンテナ `lq-api` がいつの間にか落ちている」と報告があった。
`docker ps` には表示されないが、停止したコンテナは **消えずに残っている** はずだ。ログから死因（エラーコード）を突き止め、
記録したら停止したコンテナを片付けてほしい。（同じサーバーで動いている `lq-cache` は消さないこと！）
""",
    objectives=["`docker ps -a` で停止中のコンテナも含めて一覧し、`lq-api` の状態（Exited）を確認する",
                "`docker logs` で `lq-api` のログを読み、FATAL 行の `error_code` を `submit` する",
                "停止した `lq-api` コンテナを削除する（`lq-cache` は残す）"],
    hints=["`docker ps` は実行中のものだけを表示します。止まったものも見るオプションがあります。",
           "`docker ps -a` で全コンテナ、`docker logs コンテナ名` でログ表示（`--tail 20` で末尾だけ）。削除は `docker rm`。",
           "`docker ps -a` → `docker logs lq-api | grep FATAL` → `submit E-XXXX` → `docker rm lq-api`"],
    answer="docker ps -a\ndocker logs lq-api\ndocker logs lq-api 2>&1 | grep -i fatal\nsubmit <<code>>\ndocker rm lq-api",
    explanation="""
・`docker ps -a` … 停止中も含めた全コンテナ。STATUS の `Exited (1)` の数字は **終了コード**（0 = 正常終了、それ以外 = 異常）
・`docker logs 名前` … コンテナの標準出力/標準エラーの記録。**停止したコンテナでも読める**
  `-f` で追従（tail -f と同じ）、`--tail 50` で末尾50行、`-t` でタイムスタンプ付き、`--since 10m` で直近10分
・`docker rm 名前` … 停止したコンテナを削除（実行中なら `docker rm -f` か、先に `docker stop`）
・まとめて掃除: `docker container prune`（停止コンテナを全削除）、`docker system prune`（停止コンテナ＋未使用ネットワーク＋dangling イメージ＋ビルドキャッシュ）
  注意: `docker system prune -a` は **使っていないイメージも全部消す** ので、次回の起動でダウンロードし直しになります。
""",
    tip="""
本番では `--restart unless-stopped` を付けて、落ちても自動で再起動するようにするのが一般的です。
ただし「再起動ループ」に入ると `docker ps` の STATUS が `Restarting` になり続けるので、`docker logs` で原因を見るのが先決。
終了コード `137` はメモリ不足などで **SIGKILL** された印（`docker inspect` の `OOMKilled` を確認）です。
""",
    setup=s52, check=c52,
    solution='docker ps -a\nsubmit "$(docker logs lq-api 2>&1 | grep -o "error_code=E-[0-9]*" | cut -d= -f2)"\ndocker rm lq-api',
    wrong=['submit "$(docker logs lq-api 2>&1 | grep -o "error_code=E-[0-9]*" | cut -d= -f2)"',
           'submit "$(docker logs lq-api 2>&1 | grep -o "error_code=E-[0-9]*" | cut -d= -f2)"\ndocker rm -f lq-api lq-cache',
           "docker rm lq-api\nsubmit E-0000"],
)


# ------------------------------------------------------------------ 5-3
def s53(ctx):
    ctx.docker.reset()
    # 訓練コンテナの設定探索用に生成する架空パスワード。実サービスの資格情報ではありません。
    pw = "pg_" + ctx.rand(8).lower()
    ctx.data["pw"] = pw
    conf = f"# order-db secret config\nDB_USER=penguin\nDB_PASSWORD={pw}\nDB_NAME=shop\n"
    ctx.docker.add_container("lq-db", "alpine", cmd=["sleep", "3600"], running=True,
                             files={"/etc/app/secret.conf": conf, "/etc/app/app.conf": "log_level=info\n",
                                    "/var/lib/app/data.db": "SQLite format 3\n"},
                             real_cmd=["sh", "-c", f"mkdir -p /etc/app && printf %s {shlex.quote(conf)} > /etc/app/secret.conf && echo log_level=info > /etc/app/app.conf && sleep 3600"])


def c53(ctx):
    need_running(ctx, "lq-db")
    ctx.need_submit(ctx.data["pw"], "DB_PASSWORD の値")


register(
    id="5-3", stage=S, title="コンテナの中に潜入せよ（docker exec）", docker=True,
    story="""
DBコンテナ `lq-db` の接続パスワードが分からなくなった。アプリの設定はコンテナの **中** にあるらしい。
コンテナを止めずに中に入り（または中でコマンドを実行し）、`DB_PASSWORD` の値を確認せよ。
""",
    objectives=["`docker exec` でコンテナ内のシェルに入り、アプリの設定を探す（`exit` で戻る）",
                "設定ファイルに書かれた `DB_PASSWORD` の値を `submit` する",
                "（おまけ）`docker inspect lq-db` でコンテナの詳細情報（IPアドレスなど）も眺めてみよう"],
    hints=["実行中のコンテナの中でコマンドを実行する `docker exec` を使います。対話的に操作するにはオプションが必要です。",
           "`-i`（標準入力を開く）＋ `-t`（端末を割り当てる）＝ `-it`。alpine には bash が無いので `sh` を使います。入ったら ls や cat でアプリの設定を探します。",
           "`docker exec -it lq-db sh` → `ls /etc/app` → `cat /etc/app/secret.conf` → `exit`。1発なら `docker exec lq-db cat /etc/app/secret.conf`。"],
    answer="docker exec -it lq-db sh\n  ls /etc/app\n  cat /etc/app/secret.conf\n  exit\n# 1行で: docker exec lq-db cat /etc/app/secret.conf\nsubmit <<pw>>\ndocker inspect lq-db | grep IPAddress",
    explanation="""
・`docker exec -it コンテナ sh` … 実行中のコンテナの中でシェルを起動して潜入（`-i` 入力を受け付ける ＋ `-t` 疑似端末）
  イメージによって `bash` が無い（alpine など）ので、`executable file not found` と言われたら `sh` を試す
・`docker exec コンテナ cat ファイル` … 中に入らず1コマンドだけ実行
・`docker run -it --rm alpine sh` … 使い捨てコンテナを起動して中に入る（`--rm` で終了時に自動削除）
・`docker inspect コンテナ` … 設定・状態・IP・マウント・環境変数などを JSON で全部表示
  `docker inspect -f '{{.NetworkSettings.IPAddress}}' lq-db` のように `-f` で必要な値だけ取り出せる
・`docker cp lq-db:/etc/app/secret.conf .` … コンテナ⇔ホスト間でファイルをコピー
""",
    tip="""
注意: `docker exec` でコンテナ内のファイルを書き換えても、**コンテナを作り直すと消えます**（コンテナは使い捨てが原則）。
恒久的な設定変更は Dockerfile やボリューム、環境変数で行いましょう。
パスワードを設定ファイルや環境変数に平文で置くのは本番では避け、Docker secrets やクラウドのシークレット管理サービスを使うのがベストです。
""",
    setup=s53, check=c53,
    solution='submit "$(docker exec lq-db cat /etc/app/secret.conf | grep DB_PASSWORD | cut -d= -f2)"',
    wrong=["submit password123", "docker stop lq-db\nsubmit <<pw>>"],
)


# ------------------------------------------------------------------ 5-4
def s54(ctx):
    ctx.docker.reset()
    ctx.write("html/index.html", "<!DOCTYPE html>\n<html><body><h1>Penguin Shop - 開発版</h1></body></html>\n")
    ctx.write("html/about.html", "<h1>About</h1>\n")


def c54(ctx):
    c = need_running(ctx, "lq-site")
    if not image_matches(c["image"], "nginx"):
        ctx.fail("`lq-site` は `nginx` イメージで起動しましょう。")
    if c["ports"].get("80/tcp") != "8081":
        ctx.fail(f"ポート公開が違います（現在: {c['ports'] or 'なし'}）。`-p 8081:80` にしましょう。")
    want_src = str(ctx.p("html").resolve())
    m = [x for x in c["mounts"] if x["dst"].rstrip("/") == "/usr/share/nginx/html"]
    if not m:
        ctx.fail("`/usr/share/nginx/html` へのボリュームマウントがありません。`-v ホスト側:コンテナ側` で html/ をマウントしましょう。")
    if os.path.realpath(m[0]["src"]) != want_src:
        ctx.fail(f"マウント元が `{m[0]['src']}` になっています。作業ディレクトリの `html/` を **絶対パス**（`\"$PWD/html\"`）で指定しましょう。")
    if c["env"].get("TZ") != "Asia/Tokyo":
        ctx.fail("環境変数 `TZ=Asia/Tokyo` が設定されていません。`-e` で渡しましょう。")
    leftovers = [x for x in ctx.docker.containers() if image_matches(x["image"], "alpine") and not x["running"]]
    if leftovers:
        ctx.fail(f"停止した alpine コンテナが {len(leftovers)} 個残っています。使い捨ての実行には `--rm` を付けて、終了時に自動削除させましょう（`docker rm` で片付けてから再実行）。")
    if not ctx.used("--rm"):
        ctx.fail("最後に `docker run --rm alpine cat /etc/os-release` のように、`--rm` 付きの使い捨てコンテナを1回実行してみましょう。")


register(
    id="5-4", stage=S, title="ボリュームと環境変数、そして使い捨てコンテナ", docker=True,
    story="""
デザイナーが作ったHTMLのディレクトリをすぐ確認できる開発サーバーが欲しい。HTML を書き換えるたびにイメージを作り直すのは大変なので、
**ホストのディレクトリをそのままコンテナにマウント** しよう。ログの時刻を日本時間にするため、環境変数 `TZ` も渡すこと。
最後に、OS のバージョン確認だけをする **使い捨てコンテナ** の作法も覚えよう。
""",
    objectives=["`nginx` で `lq-site` をバックグラウンド起動し、ホスト `8081` → コンテナ `80` を公開する",
                "作業フォルダ内のHTMLのディレクトリをコンテナの `/usr/share/nginx/html` にマウントし、環境変数 `TZ=Asia/Tokyo` を渡す",
                "`docker run --rm alpine cat /etc/os-release` で使い捨てコンテナを実行する（停止コンテナを残さない）"],
    hints=["`docker run` にはホストのディレクトリをコンテナに見せるオプションと、環境変数を渡すオプションがあります。",
           "`-v ホストの絶対パス:コンテナのパス`（`\"$PWD/html\"` が便利）、`-e 変数=値`、終了時自動削除は `--rm`。",
           "`docker run -d --name lq-site -p 8081:80 -v \"$PWD/html\":/usr/share/nginx/html:ro -e TZ=Asia/Tokyo nginx` / `docker run --rm alpine cat /etc/os-release`"],
    answer="docker run -d --name lq-site -p 8081:80 \\\n  -v \"$PWD/html\":/usr/share/nginx/html:ro \\\n  -e TZ=Asia/Tokyo nginx\ndocker exec lq-site cat /usr/share/nginx/html/index.html   # ホストのファイルが見える！\ndocker inspect lq-site | grep -A3 Mounts\ndocker run --rm alpine cat /etc/os-release\ndocker ps -a    # alpine の停止コンテナが残っていないこと",
    explanation="""
・`-v /ホスト/パス:/コンテナ/パス` … **バインドマウント**。ホストのファイルをコンテナから直接見せる（編集が即反映）
  末尾に `:ro` を付けると読み取り専用。相対パスだと「名前付きボリューム」と解釈されることがあるので **絶対パス** が安全（`"$PWD/html"`）
・`-v mydata:/var/lib/postgresql/data` … **名前付きボリューム**。Docker が管理する領域にデータを永続化（DBに最適）
・`-e KEY=value` … 環境変数を渡す（複数なら `-e` を繰り返すか、`--env-file .env`）
・`--rm` … コンテナ終了時に自動で削除。`docker run --rm -it ubuntu bash` のような **使い捨て実験環境** に最適
`docker ps -a` に `Exited` のコンテナが溜まっていくのは `--rm` を付け忘れた証拠です。
""",
    tip="""
コンテナの中身は作り直すと消えます。**消えて困るデータ（DB・アップロードファイル）は必ずボリュームへ**。
開発ではソースをバインドマウントしてホットリロード、本番ではイメージにソースを焼き込む、という使い分けが一般的です。
`docker run --rm -v "$PWD":/work -w /work python:3.12-slim python script.py` のように、
ホストを汚さずに好きなバージョンのツールを使い捨てで実行するテクニックも超便利です。
""",
    setup=s54, check=c54,
    solution='docker run -d --name lq-site -p 8081:80 -v "$PWD/html":/usr/share/nginx/html:ro -e TZ=Asia/Tokyo nginx\ndocker run --rm alpine cat /etc/os-release',
    wrong=['docker run -d --name lq-site -p 8081:80 -v "$PWD/html":/usr/share/nginx/html:ro nginx\ndocker run --rm alpine cat /etc/os-release',
           'docker run -d --name lq-site -p 8081:80 -v "$PWD/html":/usr/share/nginx/html:ro -e TZ=Asia/Tokyo nginx\ndocker run alpine cat /etc/os-release',
           'docker run -d --name lq-site -p 8081:80 -e TZ=Asia/Tokyo nginx\ndocker run --rm alpine cat /etc/os-release'],
)


# ------------------------------------------------------------------ 5-5
BROKEN_DF = """FORM python:3.12
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirement.txt
EXPOSE 5000
CMD ["python", "app.py"]
"""


def s55(ctx):
    ctx.docker.reset()
    ctx.data["t0"] = time.time()
    ctx.write("app.py", "from flask import Flask\napp = Flask(__name__)\n\n@app.get('/')\ndef index():\n    return 'Hello from LinuxQuest!'\n\nif __name__ == '__main__':\n    app.run(host='0.0.0.0', port=5000)\n")
    ctx.write("requirements.txt", "flask==3.0.3\n")
    ctx.write("Dockerfile", BROKEN_DF)
    ctx.write(".dockerignore", ".git\n__pycache__\n*.log\n")
    ctx.write("README.txt", "Dockerfile が壊れていてビルドできません。直して lq-app:1.0 をビルドしてください。\n")


def c55(ctx):
    from engine import dockermock
    t = ctx.read("Dockerfile") or ""
    try:
        ins = dockermock.parse_dockerfile(t)
    except ValueError as e:
        ctx.fail(f"Dockerfile の {e.args[0]} 行目: {e.args[1]}")
    froms = [a for _, i, a in ins if i == "FROM"]
    if not froms:
        ctx.fail("Dockerfile に `FROM` がありません。")
    base = froms[0].split()[0]
    if not ("slim" in base or "alpine" in base):
        ctx.fail(f"ベースイメージ `{base}` は約1GBと巨大です。軽量な `python:3.12-slim` を使いましょう。")
    order = [(i, a) for _, i, a in ins]

    def idx(pred):
        for n, (i, a) in enumerate(order):
            if pred(i, a):
                return n
        return None
    i_req = idx(lambda i, a: i in ("COPY", "ADD") and "requirements.txt" in a and not a.split()[0] in (".", "./"))
    i_pip = idx(lambda i, a: i == "RUN" and "pip" in a)
    i_all = idx(lambda i, a: i in ("COPY", "ADD") and a.split()[0] in (".", "./"))
    if i_pip is None:
        ctx.fail("`RUN pip install -r requirements.txt` の行が見当たりません。")
    if "requirements.txt" not in order[i_pip][1]:
        ctx.fail("pip install で指定しているファイル名を確認しましょう（`requirement.txt` → `requirements.txt`）。")
    if i_req is None or i_all is None or not (i_req < i_pip < i_all):
        ctx.fail("レイヤーキャッシュを活かす順番になっていません。`COPY requirements.txt .` → `RUN pip install ...` → `COPY . .` の順にしましょう。")
    created = ctx.docker.image_created("lq-app:1.0")
    if not created or created < ctx.data["t0"] - 5:
        ctx.fail("Dockerfile は良さそう！ 最後に `docker build -t lq-app:1.0 .` でイメージをビルドしましょう。")


register(
    id="5-5", stage=S, title="壊れた Dockerfile を直してビルドせよ", docker=True,
    story="""
前任者が残した Flask アプリの `Dockerfile` がビルドできない！ さらにレビューで
「ベースイメージが重すぎる」「ソースを1行直すたびに pip install が走ってビルドが遅い」と指摘されている。
エラーメッセージを読んで直し、**軽量でキャッシュの効く** Dockerfile にして `lq-app:1.0` をビルドせよ。
""",
    objectives=["`docker build` のエラーを読み、Dockerfile のタイプミス（2か所）を修正する",
                "ベースイメージを軽量な `python:3.12-slim` にする",
                "`COPY requirements.txt .` → `RUN pip install ...` → `COPY . .` の順に並べ替える（レイヤーキャッシュ対策）",
                "`docker build -t lq-app:1.0 .` でビルドを成功させる"],
    hints=["まず `docker build -t lq-app:1.0 .` を実行してエラーを読もう。1つ直したら再ビルド、を繰り返すのが基本。",
           "命令のスペル（FROM）と、pip に渡すファイル名をよく見る。依存関係のインストールは、ソース全体のコピーより **前** に。",
           "完成形: `FROM python:3.12-slim` / `WORKDIR /app` / `COPY requirements.txt .` / `RUN pip install --no-cache-dir -r requirements.txt` / `COPY . .` / `EXPOSE 5000` / `CMD [\"python\", \"app.py\"]`"],
    answer="cat > Dockerfile <<'EOF'\nFROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 5000\nCMD [\"python\", \"app.py\"]\nEOF\ndocker build -t lq-app:1.0 .\ndocker images | grep lq-app\n# app.py だけ変更して再ビルドすると pip install の行が CACHED になる！",
    explanation="""
Dockerfile の各命令は **レイヤー** になり、内容が変わっていない層は前回の結果（キャッシュ）が再利用されます。
ただし **ある層が変わると、それ以降の層はすべて作り直し** になります。
  NG `COPY . .` → `RUN pip install` … app.py を1文字変えただけで COPY 層が変わり、毎回 pip install が走る
  ○ `COPY requirements.txt .` → `RUN pip install` → `COPY . .` … 依存が変わらない限り pip install は CACHED
軽量化のポイント:
  ・`python:3.12`（約1GB）→ `python:3.12-slim`（約130MB）→ `alpine` 系（さらに小さいが musl 由来の互換性問題に注意）
  ・`pip install --no-cache-dir` で pip のキャッシュをイメージに残さない
  ・`.dockerignore` で `.git` やログなど不要なファイルをビルドコンテキストから除外
・`docker build -t 名前:タグ .` の最後の `.` は **ビルドコンテキスト**（COPY の起点になるディレクトリ）です。
""",
    tip="""
CI/CD ではビルド時間がそのままコストと待ち時間になるため、**変更頻度の低いものほど上に書く** のが鉄則です。
さらに上を目指すなら **マルチステージビルド**（ビルド用イメージでコンパイル → 実行用の小さなイメージに成果物だけコピー）で
Go や Node.js のイメージを数十MBまで削れます。`docker history lq-app:1.0` で各レイヤーのサイズを確認できます。
""",
    setup=s55, check=c55,
    solution="cat > Dockerfile <<'EOF'\nFROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 5000\nCMD [\"python\", \"app.py\"]\nEOF\ndocker build -t lq-app:1.0 .",
    wrong=["sed -i 's/FORM/FROM/; s/requirement.txt/requirements.txt/' Dockerfile\ndocker build -t lq-app:1.0 .",
           "cat > Dockerfile <<'EOF'\nFROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nRUN pip install --no-cache-dir -r requirements.txt\nCMD [\"python\", \"app.py\"]\nEOF\ndocker build -t lq-app:1.0 .",
           "cat > Dockerfile <<'EOF'\nFROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nCMD [\"python\", \"app.py\"]\nEOF"],
)


# ------------------------------------------------------------------ 5-6
COMPOSE = """services:
  web:
    image: nginx:1.27
    ports:
      - "8080:80"
    depends_on:
      - db
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: penguin
      POSTGRES_DB: shop
"""


def s56(ctx):
    ctx.docker.reset()
    ctx.write("compose.yaml", COMPOSE)
    ctx.write("README.txt", "web のポートは 8080 が他のサービスと衝突するため 8088 に変更すること。\n")


def c56(ctx):
    cs = [c for c in ctx.docker.containers() if c["labels"].get("com.docker.compose.project") == ctx.work.name.lower()]
    web = [c for c in cs if c["labels"].get("com.docker.compose.service") == "web"]
    db = [c for c in cs if c["labels"].get("com.docker.compose.service") == "db"]
    if not web and not db:
        ctx.fail("compose で起動したコンテナがありません。`docker compose up -d` で起動しましょう（compose.yaml のあるディレクトリで実行）。")
    if not db or not db[0]["running"]:
        ctx.fail("`db` サービスが起動していません。`docker compose ps -a` と `docker compose logs db` で原因を調べましょう。")
    if db[0]["env"].get("POSTGRES_PASSWORD", "") == "":
        ctx.fail("`db` に `POSTGRES_PASSWORD` が設定されていません。")
    if not web or not web[0]["running"]:
        ctx.fail("`web` サービスが起動していません。")
    if web[0]["ports"].get("80/tcp") != "8088":
        ctx.fail(f"`web` のホスト側ポートが {web[0]['ports'].get('80/tcp')} です。compose.yaml を `\"8088:80\"` に直して `docker compose up -d` で再適用しましょう。")


register(
# この課題の解答例にある POSTGRES_PASSWORD: secret は訓練専用。本番環境で再利用しないこと。
    id="5-6", stage=S, title="docker compose で複数コンテナを束ねる", docker=True,
    story="""
Web（nginx）と DB（PostgreSQL）の2つのコンテナを、毎回 `docker run` で長いオプション付きで起動するのは大変。
`compose.yaml` に構成を書いておけば **1コマンドでまとめて起動** できる。
ただし、渡された `compose.yaml` で起動すると DB が落ちるらしい…。ログを見て直し、web のポートも 8088 に変更せよ。
""",
    objectives=["`docker compose up -d` で起動し、`docker compose ps -a` と `docker compose logs db` で DB が落ちる原因を調べる",
                "`compose.yaml` の db サービスに、足りない環境変数を追加する（値は任意）",
                "web サービスのホスト側ポートを `8088` に変更し、`docker compose up -d` で再適用して両方を Running にする"],
    hints=["compose では `docker compose logs サービス名` でそのサービスのログが見られます。postgres は「ある環境変数」が無いと起動を拒否します。",
           "`environment:` の下に `POSTGRES_PASSWORD: 好きな値` を追加。ports は `- \"8088:80\"`。YAML は **スペースでインデント**（タブ禁止）。",
           "`sed -i 's/\"8080:80\"/\"8088:80\"/' compose.yaml` と、`POSTGRES_DB: shop` の下に `      POSTGRES_PASSWORD: secret` を追記 → `docker compose up -d` → `docker compose ps`"],
    answer="docker compose up -d\ndocker compose ps -a\ndocker compose logs db        # → POSTGRES_PASSWORD を指定せよ、と言っている\nvim compose.yaml              # (nano でもOK) 以下のように編集\n#   ports:\n#     - \"8088:80\"\n#   environment:\n#     POSTGRES_USER: penguin\n#     POSTGRES_DB: shop\n#     POSTGRES_PASSWORD: secret\ndocker compose up -d          # 変更があったサービスだけ作り直される\ndocker compose ps",
    explanation="""
`compose.yaml`（旧名 `docker-compose.yml`）は、複数コンテナの構成（イメージ・ポート・環境変数・ボリューム・依存関係）を宣言的に書くファイルです。
  ・`docker compose up -d` … 全サービスを作成・起動（設定が変わったサービスだけ再作成）
  ・`docker compose ps [-a]` … サービスの状態 ／ `docker compose logs [-f] サービス` … ログ
  ・`docker compose down` … 全コンテナとネットワークを削除（`-v` でボリュームも削除 注意: データ消失）
  ・`docker compose restart web` / `stop` / `start` … サービス単位の操作
  ・`docker compose exec db psql -U penguin shop` … サービスのコンテナ内でコマンド実行
同じ compose ファイル内のサービス同士は **サービス名で通信** できます（web から `db:5432` で接続可能）。
`depends_on` は起動 **順序** を制御するだけで、DB の準備完了までは待たない点に注意（`healthcheck` + `condition: service_healthy` を使う）。
""",
    tip="""
YAML のインデントミスは compose トラブルの最多原因。`docker compose config` で、解釈された最終的な設定を確認できます。
パスワードは compose.yaml に直書きせず、同じディレクトリの `.env` ファイルに書いて `${POSTGRES_PASSWORD}` で参照し、
`.env` は Git 管理外にするのが実務の定石です。旧コマンド `docker-compose`（ハイフン付き）は v1 で、現在は `docker compose` が標準です。
""",
    setup=s56, check=c56,
    solution="docker compose up -d\ndocker compose logs db\nsed -i 's/\"8080:80\"/\"8088:80\"/' compose.yaml\nsed -i 's/^      POSTGRES_DB: shop$/      POSTGRES_DB: shop\\n      POSTGRES_PASSWORD: secret/' compose.yaml\ndocker compose up -d\ndocker compose ps",
    wrong=["docker compose up -d", "sed -i 's/\"8080:80\"/\"8088:80\"/' compose.yaml\ndocker compose up -d",
           "sed -i 's/^      POSTGRES_DB: shop$/      POSTGRES_DB: shop\\n      POSTGRES_PASSWORD: secret/' compose.yaml\ndocker compose up -d"],
)


# ------------------------------------------------------------------ 5-7
ORDER_FAIL = ("[order-api] booting v1.4.0 ...\n"
              "[order-api] FATAL: 環境変数 DB_HOST が設定されていません (例: -e DB_HOST=db.internal)\n")
ORDER_OK = "[order-api] booting v1.4.0 ...\n[order-api] connected to DB_HOST={DB_HOST}\n[order-api] listening on 0.0.0.0:8080\n"
ORDER_REAL = """#!/bin/sh
echo "[order-api] booting v1.4.0 ..."
if [ -z "$DB_HOST" ]; then
  echo "[order-api] FATAL: 環境変数 DB_HOST が設定されていません (例: -e DB_HOST=db.internal)" >&2
  exit 1
fi
echo "[order-api] connected to DB_HOST=$DB_HOST"
echo "[order-api] listening on 0.0.0.0:8080"
exec httpd -f -p 8080 2>/dev/null || exec sleep 3600
"""


def s57(ctx):
    ctx.docker.reset()
    ctx.docker.add_image("lq/order-api:1.0", behavior={"require_env": ["DB_HOST"], "fail_log": ORDER_FAIL,
                                                      "logs": ORDER_OK, "listen": 8080, "real_script": ORDER_REAL,
                                                      "expose": ["8080/tcp"]})
    ctx.docker.add_container("lq-order", "lq/order-api:1.0", running=False, exit_code=1, logs=ORDER_FAIL,
                             ports={"80/tcp": "9090"})
    ctx.write("障害報告.txt", "注文API (lq-order) が起動直後に落ちる。前任者は以下で起動していた:\n"
                           "  docker run -d --name lq-order -p 9090:80 lq/order-api:1.0\n"
                           "ホストの 9090 番で注文APIに繋がるように直してほしい。\n")


def c57(ctx):
    c = find(ctx.docker.containers(), "lq-order")
    if not c:
        ctx.fail("`lq-order` コンテナがありません。正しいパラメータで `--name lq-order` として起動し直しましょう。")
    if not c["running"]:
        if not c["env"].get("DB_HOST"):
            ctx.fail("`lq-order` が停止しています。`docker logs lq-order` を見ると、何かの環境変数が足りないようです。")
        ctx.fail("`lq-order` が停止しています。`docker logs lq-order` で原因を確認しましょう。")
    if c["env"].get("DB_HOST") != "db.internal":
        ctx.fail(f"DB_HOST が `{c['env'].get('DB_HOST')}` です。ログに書かれている例のとおり `db.internal` を指定しましょう。")
    if c["ports"].get("8080/tcp") != "9090":
        if c["ports"].get("80/tcp"):
            ctx.fail("コンテナは動きましたが、アプリはコンテナ内の **8080** 番で待ち受けています（ログの `listening on` と `docker inspect` の ExposedPorts を確認）。`-p 9090:80` では繋がりません。")
        ctx.fail(f"ポート公開が違います（現在: {c['ports'] or 'なし'}）。ホスト 9090 → コンテナ 8080 にしましょう。")


register(
    id="5-7", stage=S, title="【実践】起動直後に落ちるコンテナを救え", docker=True,
    story="""
警告: 障害発生！ 注文API `lq-order` のコンテナが **起動直後に落ちる**。前任者の障害報告メモにある起動コマンドには、
どうやら **設定ミスが2つ** あるらしい。`docker logs` と `docker inspect` で原因を突き止め、正しいパラメータで起動し直せ。
""",
    objectives=["`docker ps -a` / `docker logs lq-order` で落ちた原因を調べる",
                "`docker inspect` などでアプリが待ち受けるコンテナ側ポートを確認する（イメージの情報やアプリのログを調べる）",
                "壊れた `lq-order` を削除し、正しい環境変数とポートで `lq-order` をバックグラウンド起動する（ホスト側は 9090 のまま）"],
    hints=["コンテナが落ちたらまずログ。直しても繋がらないときは「アプリがコンテナの中で何番ポートで待っているか」を疑おう。",
           "`docker logs lq-order` で足りない環境変数が分かる。`docker image inspect lq/order-api:1.0` の `ExposedPorts` や、直した後のログの `listening on` で待受ポートが分かる。",
           "`docker rm lq-order` → `docker run -d --name lq-order -e DB_HOST=db.internal -p 9090:8080 lq/order-api:1.0` → `docker logs lq-order`"],
    answer="docker ps -a\ndocker logs lq-order                          # → DB_HOST が無い\ndocker image inspect lq/order-api:1.0 | grep -A2 ExposedPorts   # → 8080/tcp\ndocker rm lq-order\ndocker run -d --name lq-order -e DB_HOST=db.internal -p 9090:8080 lq/order-api:1.0\ndocker logs lq-order                          # → listening on 0.0.0.0:8080\ndocker ps",
    explanation="""
コンテナが「起動直後に落ちる」ときの調査手順:
  ① `docker ps -a` … STATUS が `Exited (1)` → 異常終了。`Exited (137)` ならメモリ不足等で強制終了
  ② `docker logs コンテナ` … アプリ自身が出したエラーメッセージ（今回は DB_HOST 不足）
  ③ `docker inspect コンテナ` … 実際に渡された Env・PortBindings・Mounts・Cmd を確認（「渡したつもり」を検証）
  ④ `docker image inspect イメージ` … イメージ作者が想定している ExposedPorts・Cmd・Env
今回の設定ミス:
  ・**環境変数不足** … `-e DB_HOST=db.internal` が必要
  ・**ポート番号間違い** … アプリはコンテナ内の 8080 で待っているのに `-p 9090:80` と 80 に繋いでいた（起動はするが繋がらない、厄介なタイプ）
コンテナの設定は後から変更できないので、`docker rm` して **作り直す** のが基本です。
""",
    tip="""
「コンテナは動いているのに繋がらない」の3大原因: ① `-p` のコンテナ側ポート違い ② アプリが `127.0.0.1` で待ち受けている
（コンテナ内では `0.0.0.0` で待ち受ける必要がある） ③ ホスト側ポートの衝突。
すぐ落ちて中を調べられないときは `docker run -it --entrypoint sh イメージ` で、アプリを起動せずにシェルだけ立ち上げて調査する技が使えます。
""",
    setup=s57, check=c57,
    solution="docker logs lq-order\ndocker rm lq-order\ndocker run -d --name lq-order -e DB_HOST=db.internal -p 9090:8080 lq/order-api:1.0\ndocker logs lq-order",
    wrong=["docker rm lq-order\ndocker run -d --name lq-order -e DB_HOST=db.internal -p 9090:80 lq/order-api:1.0",
           "docker rm lq-order\ndocker run -d --name lq-order -p 9090:8080 lq/order-api:1.0",
           "docker start lq-order"],
)
