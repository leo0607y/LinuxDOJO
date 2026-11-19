"""Stage 2: テキスト処理・検索・パイプとリダイレクトの極意（8問）"""
import os
import random
import re

from engine.runner import register

S = 2


def gen_access_log(n=1000, bad_ips=None, seed_status=None):
    """Apache/Nginx の combined 形式の擬似アクセスログを生成。"""
    paths = ["/", "/login", "/api/items", "/api/cart", "/api/order", "/static/app.js", "/static/style.css",
             "/search?q=penguin", "/api/user/profile", "/healthz"]
    uas = ["Mozilla/5.0 (Windows NT 10.0)", "Mozilla/5.0 (Macintosh)", "curl/8.5.0", "Googlebot/2.1"]
    ips = [f"192.168.{random.randint(0, 3)}.{random.randint(2, 254)}" for _ in range(40)] + \
          [f"10.0.{random.randint(0, 9)}.{random.randint(2, 254)}" for _ in range(20)]
    bad_ips = bad_ips or {}
    lines = []
    for ip, cnt in bad_ips.items():
        for _ in range(cnt):
            lines.append((ip, 500))
    while len(lines) < n:
        st = random.choice([200] * 14 + [301, 304, 404, 404, 403])
        lines.append((random.choice(ips + list(bad_ips)), st))
    random.shuffle(lines)
    out = []
    for i, (ip, st) in enumerate(lines):
        ts = f"18/Nov/2025:{10 + i // 3600:02d}:{i // 60 % 60:02d}:{i % 60:02d} +0900"
        method = "POST" if random.random() < 0.2 else "GET"
        out.append(f'{ip} - - [{ts}] "{method} {random.choice(paths)} HTTP/1.1" {st} {random.randint(600, 20000)} "-" "{random.choice(uas)}"')
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ 2-1
DEPLOY_HIST = "2025-11-01 deploy v1.0.0 OK\n2025-11-08 deploy v1.1.0 OK\n2025-11-15 deploy v1.2.0 OK\n"


def s21(ctx):
    run = ctx.rand(6)
    ctx.data["run"] = run
    ctx.write("deploy.log", DEPLOY_HIST)
    ctx.write("deploy.sh", f"""#!/bin/bash
echo "[INFO] deploy v1.3.0 start (run={run})"
echo "[WARN] cache server is slow (run={run})" >&2
echo "[INFO] deploy v1.3.0 done (run={run})"
""", mode=0o755)
    ctx.write("noisy.sh", """#!/bin/bash
for i in 1 2 3; do echo "warning: deprecated option #$i" >&2; done
echo "RESULT: 42 items processed"
echo "error: optional plugin not found" >&2
""", mode=0o755)


def c21(ctx):
    log = ctx.read("deploy.log")
    run = ctx.data["run"]
    if log is None:
        ctx.fail("`deploy.log` が消えています！ `reset_mission` でやり直しましょう。")
    if not log.startswith(DEPLOY_HIST):
        ctx.fail("`deploy.log` の過去の記録（既存の3行）が消えています！ `>` は **上書き** です。追記には `>>` を使います。`reset_mission` でやり直しましょう。")
    new = log[len(DEPLOY_HIST):]
    if f"start (run={run})" not in new:
        ctx.fail("`deploy.log` に今回の `./deploy.sh` の実行結果が追記されていません。")
    if f"cache server is slow (run={run})" not in new:
        ctx.fail("標準出力は追記できていますが、**標準エラー出力**（[WARN] の行）が `deploy.log` に入っていません。`2>&1` を使いましょう。")
    res = ctx.read("result.txt")
    if res is None:
        ctx.fail("`result.txt` がまだありません（`./noisy.sh` の正常な結果だけを保存）。")
    if res.strip() != "RESULT: 42 items processed":
        ctx.fail("`result.txt` には `./noisy.sh` の **標準出力だけ**（RESULT の1行）を入れてください。")
    if not ctx.used("2>/dev/null", "2> /dev/null", "2>>/dev/null"):
        ctx.fail("`./noisy.sh` 実行時のエラー出力を `2>/dev/null` で捨てて、画面をスッキリさせてみましょう。")


register(
    id="2-1", stage=S, title="リダイレクトの使い分け",
    story="""
デプロイスクリプト `deploy.sh` の実行結果を、運用ログ `deploy.log` に **追記** で残したい。
ただし `deploy.sh` は通常メッセージ（標準出力）と警告（標準エラー出力）の両方を出す。**両方とも** 記録すること。
また `noisy.sh` は大量の警告で画面を汚すので、警告は捨てて正常な結果だけ `result.txt` に保存したい。
""",
    objectives=["`./deploy.sh` の標準出力と標準エラー出力の **両方** を、既存の記録を消さずに `deploy.log` へ追記する",
                "`./noisy.sh` のエラー出力を `/dev/null` に捨て、標準出力だけを `result.txt` に保存する"],
    hints=["出力には「標準出力(1番)」と「標準エラー出力(2番)」の2系統があります。`>` は上書き、`>>` は追記です。",
           "`2>&1` は「2番（エラー）を1番（標準出力）と同じ行き先へ」。`2>/dev/null` は「エラーをブラックホールへ捨てる」。",
           "`./deploy.sh >> deploy.log 2>&1` と `./noisy.sh 2>/dev/null > result.txt`。順番に注意！"],
    answer="./deploy.sh >> deploy.log 2>&1\ncat deploy.log\n./noisy.sh 2>/dev/null > result.txt",
    explanation="""
・`cmd > file` … 標準出力を **上書き** 保存（ファイルは一度空になる！）
・`cmd >> file` … 標準出力を **追記**
・`cmd 2> err.log` … 標準エラー出力だけを保存
・`cmd > file 2>&1` … 標準出力をファイルへ向け、**その後で** エラーも同じ先へ（両方保存）
・`cmd 2>/dev/null` … エラーを捨てる。`/dev/null` は書いたものが全部消える特殊ファイル
⚠ `cmd 2>&1 >> file` と順番を逆にすると、エラーは「その時点の標準出力＝画面」に向いたままになり、ファイルに入りません。
  リダイレクトは **左から順に** 評価される、と覚えましょう。bash なら `cmd &>> file` という短縮形もあります。
""",
    tip="""
cron で動かすバッチは `0 3 * * * /opt/batch.sh >> /var/log/batch.log 2>&1` が定番の書き方。
`2>&1` を忘れるとエラーがどこにも残らず、「夜間バッチが失敗していたのに誰も気づかない」事故の原因になります。
`find / -name foo 2>/dev/null` のように、Permission denied の大量エラーを捨てる使い方も頻出です。
""",
    setup=s21, check=c21,
    solution="./deploy.sh >> deploy.log 2>&1\n./noisy.sh 2>/dev/null > result.txt",
    wrong=["./deploy.sh > deploy.log 2>&1\n./noisy.sh 2>/dev/null > result.txt",
           "./deploy.sh >> deploy.log\n./noisy.sh 2>/dev/null > result.txt",
           "./deploy.sh 2>&1 >> deploy.log\n./noisy.sh 2>/dev/null > result.txt",
           "./deploy.sh >> deploy.log 2>&1\n./noisy.sh > result.txt 2>&1"],
)


# ------------------------------------------------------------------ 2-2
def s22(ctx):
    msgs = ["INFO user login ok", "INFO cart updated", "WARN slow query 1200ms", "ERROR payment gateway timeout",
            "error: failed to send mail", "INFO order created", "Error while reading cache", "warn: disk 85% used",
            "INFO health ok", "DEBUG retry=1", "Warning: deprecated API v1 called", "FATAL out of memory"]
    lines = [f"2025-11-18 10:{i // 60:02d}:{i % 60:02d} {random.choice(msgs)}" for i in range(400)]
    ctx.write("app.log", "\n".join(lines) + "\n")
    ctx.data["warn"] = sum(1 for ln in lines if "warn" in ln.lower())


def c22(ctx):
    src = ctx.lines("app.log")
    want = [ln for ln in src if "error" in ln.lower()]
    got = ctx.lines("errors.txt")
    if got is None:
        ctx.fail("`errors.txt` がまだありません。")
    if got != want:
        upper = [ln for ln in src if "ERROR" in ln]
        if got == upper:
            ctx.fail("`ERROR` だけでなく `error` や `Error` も拾う必要があります。大文字小文字を無視するオプションは？")
        ctx.fail(f"`errors.txt` の内容が期待と違います（期待 {len(want)} 行 / 現在 {len(got)} 行）。")
    ctx.need_submit(ctx.data["warn"], "警告の行数")


register(
    id="2-2", stage=S, title="大文字も小文字もまとめて grep",
    story="""
アプリのログ `app.log` には `ERROR` `error:` `Error` と、表記ゆれのあるエラーが混在している。
開発チームから「**エラー系の行を全部**抜き出して送って」「ついでに **警告(warn)系が何行あるか** も教えて」と頼まれた。
""",
    objectives=["`app.log` から、大文字小文字を問わず `error` を含む行をすべて `errors.txt` に保存する",
                "大文字小文字を問わず `warn` を含む行の **行数** を数えて `submit` する"],
    hints=["`grep 文字列 ファイル` で一致する行を抽出できます。ただし標準では大文字小文字を区別します。",
           "`-i` (ignore-case) で大文字小文字を無視。行数を数えるなら `-c`（count）か `| wc -l`。",
           "`grep -i error app.log > errors.txt` と `grep -ic warn app.log` → 出た数字を `submit`。"],
    answer="grep -i error app.log > errors.txt\ngrep -ic warn app.log      # または grep -i warn app.log | wc -l\nsubmit <<warn>>",
    explanation="""
grep の基本オプション:
  ・`-i` … 大文字小文字を無視（ignore case）
  ・`-c` … 一致した **行数** だけを表示（count）
  ・`-n` … 行番号を付けて表示
  ・`-w` … 単語単位で一致（`error` は `errors` にマッチしなくなる）
  ・`-o` … 一致した部分だけを表示
`| wc -l` はパイプで受け取った行数を数えます。`grep -c` と同じ結果になりますが、
`wc -l` は「どんなコマンドの出力でも数えられる」万能選手です（`ls | wc -l` でファイル数など）。
""",
    tip="""
本番ログ調査は `grep -i error app.log | tail -n 20` で「直近のエラー20件」を見るところから始まることが多いです。
ログが圧縮されていても `zgrep -i error app.log.1.gz` でそのまま検索できます。
`grep --color=auto` を有効にしておくと一致部分が色付きで強調されて見やすくなります（このシェルでは有効化済み）。
""",
    setup=s22, check=c22,
    solution='grep -i error app.log > errors.txt\nsubmit "$(grep -ic warn app.log)"',
    wrong=["grep ERROR app.log > errors.txt\nsubmit 0", 'grep -i error app.log > errors.txt\nsubmit "$(grep -c warn app.log)"'],
)


# ------------------------------------------------------------------ 2-3
# grep の検索練習用に意図的に埋め込んだ架空パスワードです。実際の認証情報ではありません。
SRC_FILES = {
    "src/app.py": "import os\nDB = os.environ['DB_URL']\n",
    "src/config/settings.py": "DEBUG = False\nPASSWORD=hunter2  # TODO: remove\n",
    "src/utils/helpers.py": "def add(a, b):\n    return a + b\n",
    "src/utils/legacy/old_db.py": "conn = connect(user='admin', PASSWORD='admin123')\n",
    "src/templates/login.html": "<input type='password' name='password_hint'>\n",
    "src/scripts/deploy.sh": "#!/bin/bash\nexport PASSWORD=rootpass\nrsync -a . server:/app\n",
    "src/README.md": "環境変数 DB_URL を設定してください\n",
    "src/tests/test_app.py": "def test_ok():\n    assert True\n",
}
LEAKED = {"src/config/settings.py", "src/utils/legacy/old_db.py", "src/scripts/deploy.sh"}


def s23(ctx):
    for k, v in SRC_FILES.items():
        ctx.write(k, v)
    # 読み取り権限を学ぶためのダミーパスワード。実サービスには対応しません。
    ctx.write("src/private/secret_vault.txt", "PASSWORD=you-cannot-read-me\n")
    os.chmod(ctx.p("src/private"), 0o000)  # 読めないディレクトリ → Permission denied が出る


def _norm_paths(ctx, lines, bases=("",)):
    out = set()
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        for b in bases:
            p = (ctx.work / b / ln).resolve()
            if p.exists():
                out.add(str(p.relative_to(ctx.work.resolve())))
                break
        else:
            out.add("?" + ln)
    return out


def c23(ctx):
    lines = ctx.lines("leaked.txt")
    if lines is None:
        ctx.fail("`leaked.txt` がまだありません。")
    if any("Permission denied" in ln or "許可がありません" in ln for ln in lines):
        ctx.fail("`leaked.txt` にエラーメッセージが混ざっています。")
    if any(":" in ln and ("PASSWORD" in ln) for ln in lines):
        ctx.fail("`leaked.txt` には一致した行ではなく **ファイル名だけ** を1行ずつ書いてください（`-l` オプション）。")
    got = _norm_paths(ctx, lines, ("", "src"))
    if got != LEAKED:
        miss = LEAKED - got
        extra = got - LEAKED
        msg = "ファイル一覧が正しくありません。"
        if miss:
            msg += f" 足りないもの: {len(miss)}件。サブディレクトリの奥まで探していますか？"
        if extra:
            msg += f" 余計なもの: {', '.join(sorted(x.lstrip('?') for x in extra))}（大文字の `PASSWORD=` だけが対象）"
        ctx.fail(msg)


register(
    id="2-3", stage=S, title="ソースコードに埋まった秘密を暴け",
    story="""
セキュリティ監査で「**パスワードのハードコード**」が見つかった。`src/` 配下のどのファイルに `PASSWORD=` という文字列が
書かれているかを洗い出し、該当ファイルの一覧を作って開発チームに渡したい。
なお `src/private/` は権限がなく読めないので、エラーが出ても気にせず捨ててよい。
""",
    objectives=["`src/` 配下を再帰的に検索し、`PASSWORD=` を含む **ファイルのパスだけ** を `leaked.txt` に1行ずつ保存する",
                "読めないディレクトリの Permission denied エラーは `2>/dev/null` で捨てる"],
    hints=["`grep` はディレクトリの中身をまるごと再帰的に検索することもできます。ファイル名だけを出すオプションもあります。",
           "`-r`（recursive）で再帰検索、`-l`（files-with-matches）で一致したファイル名だけを表示。",
           "`grep -rl 'PASSWORD=' src 2>/dev/null > leaked.txt`"],
    answer="grep -rl 'PASSWORD=' src 2>/dev/null > leaked.txt\ncat leaked.txt",
    explanation="""
・`grep -r パターン ディレクトリ` … ディレクトリ配下の全ファイルを再帰的に検索
・`-l` … 一致したファイル名だけ（中身は出さない）／ `-L` は逆に「一致しなかったファイル」
・`-n` … 一致行の行番号付き（どこを直せばいいか一目で分かる）
・`--include='*.py'` … 対象ファイルを絞り込み、`--exclude-dir=node_modules` … 除外
・`2>/dev/null` … 読めないディレクトリの `Permission denied` エラーを捨てる
大文字小文字を区別するので `password_hint` にはマッチしません（`-i` を付ければマッチします）。
""",
    tip="""
実務では `grep -rn 'TODO' --include='*.py' .` のようにソースを横断検索する場面が非常に多いです。
大規模リポジトリでは高速な `git grep` や `ripgrep (rg)` もよく使われます。
秘密情報の混入チェックは **gitleaks** や **trufflehog** のような専用ツールを CI に組み込むのがベストプラクティスです。
""",
    setup=s23, check=c23,
    solution="grep -rl 'PASSWORD=' src 2>/dev/null > leaked.txt",
    wrong=["grep -r 'PASSWORD=' src 2>/dev/null > leaked.txt", "grep -l 'PASSWORD=' src/* 2>/dev/null > leaked.txt",
           "grep -rli 'password' src 2>/dev/null > leaked.txt"],
)


# ------------------------------------------------------------------ 2-4
APP_CONF = """# ==========================================
#  Penguin Shop web server configuration
# ==========================================

# listen port
listen 8080

server_name shop.example.com
    # worker settings (tuned for 4 cores)
worker_processes 4

# logging
access_log /var/log/shop/access.log
#error_log /var/log/shop/debug.log debug
error_log /var/log/shop/error.log warn

    # TLS
ssl_certificate /etc/ssl/shop.crt
ssl_certificate_key /etc/ssl/shop.key   # keep secret!
"""


def s24(ctx):
    ctx.write("app.conf", APP_CONF)


def c24(ctx):
    want = [ln for ln in APP_CONF.splitlines() if ln.strip() and not re.match(r"^\s*#", ln)]
    got = ctx.lines("clean.conf")
    if got is None:
        ctx.fail("`clean.conf` がまだありません。")
    if any(not ln.strip() for ln in got):
        ctx.fail("`clean.conf` に空行が残っています。空行は正規表現 `^$` で表せます。")
    if any(re.match(r"^\s*#", ln) for ln in got):
        ctx.fail("`clean.conf` にコメント行が残っています。**行頭にスペースがあるコメント** にも注意！")
    if got != want:
        ctx.fail("`clean.conf` の内容が期待と違います。有効な設定行（行末コメント付きの行も含む）は残しましょう。")


register(
    id="2-4", stage=S, title="コメントと空行を取り除け（grep -v と正規表現）",
    story="""
設定ファイル `app.conf` はコメントだらけで、**実際に有効な設定がどれか** 分かりにくい。
コメント行と空行を取り除いた「有効な設定だけ」の一覧 `clean.conf` を作って、レビューに回したい。
""",
    objectives=["`app.conf` から、コメント行（行頭や **インデント後** が `#` の行）と空行を取り除いた結果を `clean.conf` に保存する"],
    hints=["「マッチした行を **除外** する」オプションが grep にはあります。行頭は正規表現で `^` と書きます。",
           "`grep -v`（invert）で除外。`-E` で拡張正規表現。`^\\s*#` は「行頭から空白の後に #」、`^$` は空行。",
           "`grep -Ev '^\\s*(#|$)' app.conf > clean.conf` または `grep -v '^\\s*#' app.conf | grep -v '^$' > clean.conf`"],
    answer="grep -Ev '^\\s*(#|$)' app.conf > clean.conf\ncat clean.conf",
    explanation="""
正規表現の基本パーツ:
  ・`^` 行頭 ／ `$` 行末 ／ `.` 任意の1文字 ／ `*` 直前の0回以上の繰り返し
  ・`\\s` 空白文字（スペース・タブ） ／ `[0-9]` 文字クラス ／ `(a|b)` a または b（`-E` が必要）
`grep -v` は「マッチしない行」を出力します。
`'^\\s*(#|$)'` = 「行頭 → 空白が0個以上 → `#` か行末」なので、コメント行・インデント付きコメント・空行をまとめて除外できます。
⚠ `grep -v '^#'` だけでは、インデントされたコメント (`    # TLS`) が残ってしまいます。
行末コメント付きの `ssl_certificate_key ... # keep secret!` は **有効な設定** なので残すのが正解です。
""",
    tip="""
サーバー構築の現場で `grep -Ev '^\\s*(#|$)' /etc/ssh/sshd_config` は鉄板のワンライナー。
数百行のデフォルト設定から「実際に効いている設定」だけを一瞬で抽出できます。
シングルクォート `'...'` で囲むのを忘れずに。囲まないとシェルが `$` や `*` を先に解釈してしまいます。
""",
    setup=s24, check=c24,
    solution="grep -Ev '^\\s*(#|$)' app.conf > clean.conf",
    wrong=["grep -v '^#' app.conf > clean.conf", "grep -v '^#' app.conf | grep -v '^$' > clean.conf",
           "grep -v '#' app.conf | grep -v '^$' > clean.conf"],
)


# ------------------------------------------------------------------ 2-5
def s25(ctx):
    lines = []
    n = 300
    oom = random.randint(80, 260)
    for i in range(n):
        lines.append(f"2025-11-18 03:{i // 60:02d}:{i % 60:02d} INFO batch worker processed chunk={i}")
    lines[oom - 2] = f"2025-11-18 03:{(oom - 2) // 60:02d}:{(oom - 2) % 60:02d} WARN heap usage 92%"
    lines[oom - 1] = f"2025-11-18 03:{(oom - 1) // 60:02d}:{(oom - 1) % 60:02d} WARN GC overhead limit approaching"
    lines[oom] = f"2025-11-18 03:{oom // 60:02d}:{oom % 60:02d} ERROR java.lang.OutOfMemoryError: Java heap space"
    lines[oom + 1] = f"2025-11-18 03:{(oom + 1) // 60:02d}:{(oom + 1) % 60:02d} INFO worker restarting..."
    ctx.write("batch.log", "\n".join(lines) + "\n")
    ctx.data["oom"] = oom


def c25(ctx):
    src = ctx.lines("batch.log")
    i = ctx.data["oom"]
    want = src[i - 2:i + 3]
    got = ctx.lines("context.txt")
    if got is None:
        ctx.fail("`context.txt` がまだありません。")
    got = [ln for ln in got if ln != "--"]
    stripped = [re.sub(r"^\d+[:-](?=\d{4}-)", "", ln) for ln in got]
    if got != want and stripped != want:
        ctx.fail(f"`context.txt` は「OutOfMemoryError の行」＋「その前後2行ずつ」の計5行にしてください（現在 {len(got)} 行）。")


register(
    id="2-5", stage=S, title="障害の『前後』を読む（grep -C）",
    story="""
深夜3時のバッチが `OutOfMemoryError` で落ちた。エラー行そのものだけでなく、
**直前に何が起きていて、直後にどうなったか** が原因究明のカギになる。
""",
    objectives=["`batch.log` から `OutOfMemoryError` を含む行と、その **前後2行ずつ**（計5行）を `context.txt` に保存する"],
    hints=["grep には一致した行の「前」「後」「前後」の行も一緒に表示するオプションがあります。",
           "`-A n`（After）、`-B n`（Before）、`-C n`（Context: 前後）。",
           "`grep -C 2 OutOfMemoryError batch.log > context.txt`"],
    answer="grep -C 2 OutOfMemoryError batch.log > context.txt\ncat context.txt",
    explanation="""
・`grep -A 3 pattern` … 一致行と **その後** 3行（スタックトレースを見るときに便利）
・`grep -B 3 pattern` … 一致行と **その前** 3行
・`grep -C 2 pattern` … **前後** 2行ずつ
複数箇所が一致すると、ブロックの区切りに `--` が表示されます。
`-n` を足すと行番号付きになり、`less +行番号 batch.log` でその場所へジャンプできます。
""",
    tip="""
Java/Python のエラーは **スタックトレース** が後ろに続くので `grep -A 20 Exception app.log` が定番。
今回のように「heap 92% → GC 警告 → OOM」という **予兆** は直前のログに出ていることが多く、
監視アラートの閾値を決める根拠にもなります。
""",
    setup=s25, check=c25,
    solution="grep -C 2 OutOfMemoryError batch.log > context.txt",
    wrong=["grep OutOfMemoryError batch.log > context.txt", "grep -A 2 OutOfMemoryError batch.log > context.txt"],
)


# ------------------------------------------------------------------ 2-6
BIG = {"project/logs/app.log": 3 * 1024 * 1024, "project/logs/2025/access.log": 2 * 1024 * 1024,
       "project/services/api/debug.log": 1536 * 1024}
SMALL = {"project/logs/worker.log": 40 * 1024, "project/services/api/error.log": 500 * 1024,
         "project/services/web/web.log": 120 * 1024}
OLD = {"backups/db_2025-09-01.tar.gz": 78, "backups/db_2025-10-01.tar.gz": 48, "backups/db_2025-11-01.tar.gz": 17,
       "backups/db_2025-11-08.tar.gz": 10}
NEW = {"backups/db_2025-11-12.tar.gz": 6, "backups/db_2025-11-15.tar.gz": 3, "backups/db_2025-11-17.tar.gz": 1}


def s26(ctx):
    for k, v in {**BIG, **SMALL}.items():
        ctx.sparse(k, v)
    ctx.sparse("project/logs/old/app.log.gz", 2 * 1024 * 1024)   # .log ではない
    ctx.mkdir("project/archive.log")                               # ディレクトリの罠
    ctx.sparse("project/archive.log/readme.txt", 2 * 1024 * 1024)
    for k, age in {**OLD, **NEW}.items():
        ctx.write(k, "dummy backup\n", age_days=age)
    ctx.write("backups/README.txt", "バックアップ置き場（このファイルは消さないこと）\n", age_days=120)


def c26(ctx):
    lines = ctx.lines("big_logs.txt")
    if lines is None:
        ctx.fail("`big_logs.txt` がまだありません。")
    got = _norm_paths(ctx, lines, ("", "project"))
    want = set(BIG)
    if got != want:
        if "project/archive.log" in got:
            ctx.fail("`project/archive.log` は **ディレクトリ** です。ファイルだけに絞るオプションを使いましょう。")
        if any(x.endswith(".gz") for x in got):
            ctx.fail("`.log.gz` は対象外です（名前が `.log` で終わるファイルだけ）。")
        ctx.fail(f"`big_logs.txt` のファイル一覧が違います（期待 {len(want)} 件 / 現在 {len(got)} 件）。1MB より大きい `.log` ファイルだけを列挙しましょう。")
    for k in NEW:
        if not ctx.exists(k):
            ctx.fail(f"🚨 新しいバックアップ `{k}` まで消えています！ `reset_mission` でやり直しましょう。")
    if not ctx.exists("backups/README.txt"):
        ctx.fail("🚨 `backups/README.txt` が消えています。`-name` で対象を絞りましょう。")
    for k in OLD:
        if ctx.exists(k):
            ctx.fail(f"7日より古いバックアップ `{k}` がまだ残っています。")


register(
    id="2-6", stage=S, title="find で探して、古いものを片付ける",
    story="""
ディスク使用率が 90% を超えたとアラートが鳴った！
まず `project/` 配下で **1MB を超える巨大な .log ファイル** を洗い出してリストにまとめ、
さらに `backups/` にある **7日より古いバックアップ (*.tar.gz)** を削除して空き容量を確保せよ。
""",
    objectives=["`project/` 配下から「通常ファイル」かつ「名前が `.log` で終わる」かつ「1MB 超」のものを探し、パス一覧を `big_logs.txt` に保存する",
                "`backups/` の `*.tar.gz` のうち、最終更新が **7日より前** のものを削除する（新しいものと README.txt は残す）"],
    hints=["`find 探す場所 条件...` で条件に合うファイルを探せます。種類・名前・サイズ・更新日時を条件にできます。",
           "`-type f`（ファイルのみ）、`-name '*.log'`、`-size +1M`（1MB超）、`-mtime +7`（7日より前）、`-delete`（削除）。",
           "`find project -type f -name '*.log' -size +1M > big_logs.txt` / まず `find backups -name '*.tar.gz' -mtime +7` で確認 → 末尾に `-delete`。"],
    answer="find project -type f -name '*.log' -size +1M > big_logs.txt\nfind backups -name '*.tar.gz' -mtime +7          # まず確認！\nfind backups -name '*.tar.gz' -mtime +7 -delete",
    explanation="""
find の主な条件:
  ・`-type f` ファイル ／ `-type d` ディレクトリ ／ `-type l` シンボリックリンク
  ・`-name '*.log'` 名前（**必ずクォート**。しないとシェルが先に `*` を展開してしまう）／ `-iname` は大文字小文字無視
  ・`-size +1M` 1MB超 ／ `-size -100k` 100KB未満
  ・`-mtime +7` 7日より前に更新 ／ `-mtime -1` 24時間以内 ／ `-mmin -30` 30分以内
  ・`-delete` 見つけたものを削除 ／ `-exec コマンド {} \\;` 見つけたものに任意のコマンドを実行
条件を並べると AND（かつ）になります。`-o` で OR も書けます。
⚠ `-delete` は必ず最後に置き、**付ける前に一度そのまま実行して対象を確認** するのが鉄則です。
""",
    tip="""
ログローテーションの自前実装として `find /var/log/app -name '*.log.gz' -mtime +30 -delete` を cron に仕込むのは定番。
「ディスクを食っている犯人探し」には `find / -xdev -type f -size +500M 2>/dev/null` が効きます（`-xdev` で別ディスクに潜らない）。
`-mtime +7` は「7×24時間より前」ではなく「経過日数を切り捨てて 7 より大きい」＝ 実質8日以上前、という細かい仕様もあります。
""",
    setup=s26, check=c26,
    solution="find project -type f -name '*.log' -size +1M > big_logs.txt\nfind backups -name '*.tar.gz' -mtime +7 -delete",
    wrong=["find project -type f -name '*.log' > big_logs.txt\nfind backups -name '*.tar.gz' -mtime +7 -delete",
           "find project -type f -name '*.log' -size +1M > big_logs.txt\nfind backups -mtime +7 -delete",
           "find project -type f -name '*.log' -size +1M > big_logs.txt\nfind backups -name '*.tar.gz' -mtime -7 -delete"],
)


# ------------------------------------------------------------------ 2-7
def s27(ctx):
    counts = random.sample(range(3, 45), 6)
    ips = [f"203.0.113.{random.randint(2, 250)}" for _ in range(6)]
    while len(set(ips)) < 6:
        ips = [f"203.0.113.{random.randint(2, 250)}" for _ in range(6)]
    bad = dict(zip(ips, counts))
    ctx.write("access.log", gen_access_log(1000, bad))
    ctx.data["ranking"] = sorted(([c, ip] for ip, c in bad.items()), reverse=True)


def c27(ctx):
    lines = ctx.lines("report.txt")
    if lines is None:
        ctx.fail("`report.txt` がまだありません。")
    rows = []
    for ln in lines:
        parts = ln.split()
        if not parts:
            continue
        if len(parts) != 2:
            ctx.fail(f"`report.txt` の形式が違います:「{ln.strip()}」→ 各行は「件数 IPアドレス」の2列にしましょう（`uniq -c` の出力形式）。")
        a, b = parts
        if a.isdigit():
            rows.append([int(a), b])
        elif b.isdigit():
            rows.append([int(b), a])
        else:
            ctx.fail(f"`report.txt` の行「{ln.strip()}」に件数がありません。`uniq -c` で数えましょう。")
    want = [list(x) for x in ctx.data["ranking"]]
    if sorted(rows) == sorted(want) and rows != want:
        ctx.fail("集計は合っていますが **並び順** が違います。件数の多い順（数値として降順）に並べましょう。")
    if rows != want:
        if any(r[0] == 1 for r in rows) and len(rows) > len(want):
            ctx.fail("件数が1のIPがたくさん並んでいます。`uniq` は **隣り合った** 重複しかまとめないので、先に `sort` が必要です。")
        ctx.fail(f"集計結果が違います（期待 {len(want)} 行 / 現在 {len(rows)} 行）。ステータスコード 500 の行だけに絞っていますか？")


register(
    id="2-7", stage=S, title="【実践】500エラーの犯人IPランキング",
    story="""
「ECサイトで 500 Internal Server Error が多発している。**どのIPからのアクセスでエラーが起きているか**、
多い順のランキングを出してくれ！」とリーダーから緊急依頼。
`access.log`（1000行、Nginx の combined 形式）を集計パイプラインで料理せよ。
""",
    objectives=["`access.log` のうちステータスコードが **500** の行だけを対象にする（ステータスは9列目）",
                "IPアドレス（1列目）ごとの件数を数え、**件数の多い順** に「件数 IP」の形式で `report.txt` に保存する"],
    hints=["「500の行を絞る → IPだけ取り出す → 並べる → 重複を数える → 件数で並べ直す」とパイプで段階的に加工します。まず `head -3 access.log` で形式を確認！",
           "`awk '$9 == 500 {print $1}'` で9列目が500の行の1列目を表示。`sort` → `uniq -c` → `sort -rn`。",
           "`awk '$9==500 {print $1}' access.log | sort | uniq -c | sort -rn > report.txt`"],
    answer="awk '$9 == 500 {print $1}' access.log | sort | uniq -c | sort -rn > report.txt\ncat report.txt",
    explanation="""
パイプ `|` は「左のコマンドの出力」を「右のコマンドの入力」に流し込みます。1段ずつ確認しながら組み立てるのがコツ:
  ① `awk '$9 == 500 {print $1}' access.log` … 空白区切りで9列目が500の行だけ、1列目(IP)を表示
  ② `| sort` … IPを並べ替えて、同じIPを隣り合わせにする
  ③ `| uniq -c` … **隣り合った** 重複をまとめ、件数を先頭に付ける（だから②の sort が必須！）
  ④ `| sort -rn` … `-n` 数値として、`-r` 逆順（大きい順）に並べる
`sort -rn` の `-n` を忘れると「9 → 45 → 3」のような文字列順になってしまいます。
`grep ' 500 ' access.log | cut -d' ' -f1 | ...` でも可能ですが、awk なら列を正確に指定できます。
""",
    tip="""
`sort | uniq -c | sort -rn | head` は **ログ集計の黄金パイプライン**。
「アクセスの多いURL TOP10」「エラーの多い時間帯」「攻撃元IPの特定」など、あらゆる集計に応用できます。
攻撃元を特定したら、そのIPを `iptables` やWAF、Nginx の `deny` で遮断するのが次の一手です。
""",
    setup=s27, check=c27,
    solution="awk '$9 == 500 {print $1}' access.log | sort | uniq -c | sort -rn > report.txt",
    wrong=["awk '$9 == 500 {print $1}' access.log | sort | uniq -c > report.txt",
           "awk '$9 == 500 {print $1}' access.log | uniq -c | sort -rn > report.txt",
           "awk '{print $1}' access.log | sort | uniq -c | sort -rn > report.txt"],
)


# ------------------------------------------------------------------ 2-8
CONFIG_YAML = """app:
  name: penguin-shop
  debug: true
database:
  db_host: localhost
  db_port: 5432
cache:
  cache_host: localhost
  cache_port: 6379
replica:
  db_host: localhost
"""


def s28(ctx):
    depts = ["dev", "sales", "devops", "hr", "dev", "design"]
    rows = ["id,name,email,department"]
    names = ["sato", "suzuki", "takahashi", "tanaka", "ito", "watanabe", "yamamoto", "nakamura", "kobayashi", "kato",
             "yoshida", "yamada", "sasaki", "yamaguchi", "matsumoto"]
    for i, n in enumerate(names, 1):
        rows.append(f"{i},{n.capitalize()},{n}@penguin.example.com,{random.choice(depts)}")
    if not any(r.endswith(",dev") for r in rows[1:]):
        rows[1] = rows[1].rsplit(",", 1)[0] + ",dev"
    if not any(r.endswith(",devops") for r in rows[1:]):
        rows[2] = rows[2].rsplit(",", 1)[0] + ",devops"
    ctx.write("users.csv", "\n".join(rows) + "\n")
    ctx.write("config.yaml", CONFIG_YAML)


def c28(ctx):
    rows = [r.split(",") for r in ctx.lines("users.csv")[1:]]
    want = [r[2] for r in rows if r[3] == "dev"]
    got = ctx.lines("dev_emails.txt")
    if got is None:
        ctx.fail("`dev_emails.txt` がまだありません。")
    got = [g.strip() for g in got if g.strip()]
    if got != want:
        if "email" in got:
            ctx.fail("ヘッダー行の `email` が混ざっています。")
        devops = [r[2] for r in rows if r[3] in ("dev", "devops")]
        if got == devops:
            ctx.fail("`devops` 部署の人まで含まれています！部署が **完全に** `dev` の人だけに絞りましょう。")
        ctx.fail(f"`dev_emails.txt` の内容が違います（期待 {len(want)} 件 / 現在 {len(got)} 件）。メールアドレス（3列目）だけを出力しましょう。")
    want_cfg = CONFIG_YAML.replace("db_host: localhost", "db_host: db.prod.internal").replace("debug: true", "debug: false")
    cfg = ctx.read("config.yaml")
    if cfg == want_cfg:
        return
    if cfg and "cache_host: db.prod.internal" in cfg:
        ctx.fail("`cache_host` まで書き換わっています！置換対象は `db_host: localhost` だけです（`reset_mission` で戻せます）。")
    if cfg and cfg.count("db_host: db.prod.internal") == 1:
        ctx.fail("`db_host` が1か所しか置換されていません。replica セクションにもあります。")
    if cfg and "debug: true" in cfg:
        ctx.fail("`debug: true` を `debug: false` に変更してください。")
    ctx.fail("`config.yaml` の内容が期待と違います。")


register(
    id="2-8", stage=S, title="CSV の列抽出と設定の一括置換",
    story="""
2つの依頼が同時に来た。
① 人事から「`users.csv` から **開発部(dev)** のメンバーのメールアドレス一覧が欲しい」。※ `devops` 部署もあるので注意！
② 本番リリースに向けて `config.yaml` の **DBホストを `localhost` → `db.prod.internal` に一括置換**、デバッグモードも OFF にしたい。
""",
    objectives=["`users.csv`（id,name,email,department）から、department が **ちょうど** `dev` の人の email だけを `dev_emails.txt` に保存する",
                "`config.yaml` の `db_host: localhost` をすべて `db_host: db.prod.internal` に置換する（`cache_host` は変えない）",
                "`config.yaml` の `debug: true` を `debug: false` にする（ファイルを直接書き換える）"],
    hints=["CSV はカンマ区切りの「列」データ。列を指定して取り出すコマンドと、文字列を置換してファイルを書き換えるコマンドがあります。",
           "`awk -F, '$4 == \"dev\" {print $3}'`（-F で区切り文字指定）や `cut -d, -f3`。置換は `sed -i 's/旧/新/g' ファイル`。",
           "`awk -F, '$4==\"dev\"{print $3}' users.csv > dev_emails.txt` / `sed -i 's/db_host: localhost/db_host: db.prod.internal/; s/debug: true/debug: false/' config.yaml`"],
    answer="awk -F, '$4 == \"dev\" {print $3}' users.csv > dev_emails.txt\nsed -i 's/db_host: localhost/db_host: db.prod.internal/g; s/debug: true/debug: false/' config.yaml\ncat config.yaml",
    explanation="""
・`cut -d, -f3 users.csv` … `,` 区切りで3列目を切り出す（シンプルな列抽出に最適）
・`awk -F, '$4 == "dev" {print $3}'` … 4列目が完全一致で dev の行だけ3列目を出力（条件付き抽出は awk が得意）
  ⚠ `grep dev users.csv | cut -d, -f3` だと **devops も一致** してしまいます。`grep ',dev$'` のように行末 `$` まで指定すれば回避可能。
・`sed 's/旧/新/'` … 各行の最初の1つを置換 ／ `s/旧/新/g` … 行内のすべてを置換（global）
・`sed -i` … 結果を画面に出さず **ファイルを直接書き換える**（in-place）
・`;` で複数の置換を1回で実行できます。`-i.bak` とすると元ファイルを `.bak` として残してくれます。
単に `s/localhost/db.prod.internal/` だと `cache_host` まで書き換わる事故になります。置換対象は **具体的に** 書きましょう。
""",
    tip="""
`sed -i` は強力ですが、いきなり本番ファイルに使うのは危険。まず `-i` なしで実行して画面で結果を確認 →
問題なければ `-i.bak` 付きで実行、が安全な手順です。
大量ファイルの一括置換は `grep -rl 'old' . | xargs sed -i 's/old/new/g'` という合わせ技も定番です（Extra Stage で xargs を特訓）。
""",
    setup=s28, check=c28,
    solution="awk -F, '$4 == \"dev\" {print $3}' users.csv > dev_emails.txt\nsed -i 's/db_host: localhost/db_host: db.prod.internal/; s/debug: true/debug: false/' config.yaml",
    wrong=["grep dev users.csv | cut -d, -f3 > dev_emails.txt\nsed -i 's/db_host: localhost/db_host: db.prod.internal/; s/debug: true/debug: false/' config.yaml",
           "awk -F, '$4 == \"dev\" {print $3}' users.csv > dev_emails.txt\nsed -i 's/localhost/db.prod.internal/g; s/debug: true/debug: false/' config.yaml",
           "awk -F, '$4 == \"dev\" {print $3}' users.csv > dev_emails.txt\nsed -i 's/db_host: localhost/db_host: db.prod.internal/' config.yaml"],
)
