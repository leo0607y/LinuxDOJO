"""Extra Stage: 現場で一目置かれる「Linux小ネタ・時短テクニック集」
  - TIPS: 閲覧モード用の解説10選（メインメニューの「小ネタ図鑑」から読める）
  - ミッション: 実践モードのミニ課題5問
"""
import random

from engine.runner import register

from engine.runner import EXTRA

S = EXTRA

# ------------------------------------------------------------------ 閲覧モード: 解説10選
TIPS = [
    {
        "title": "履歴の爆速再利用（!! / !$ / !* / Ctrl+R）",
        "body": """
同じコマンドを打ち直すのは時間の無駄。bash の履歴展開を使いこなそう。
  ・`!!` … 直前のコマンド全体。定番は権限エラーの後の **`sudo !!`**
  ・`!$` … 直前のコマンドの **最後の引数**。`mkdir -p /var/www/app && cd !$` のように使う
  ・`!*` … 直前のコマンドの **全引数**。`touch a b c` → `ls -l !*`
  ・`!grep` … `grep` で始まる直近のコマンドを再実行 ／ `!123` … `history` の123番を再実行
  ・**Ctrl+R** … 履歴をインクリメンタル検索。文字を打つと候補が出る → もう一度 Ctrl+R で更に過去へ → Enter で実行 / → で編集
  ・**Alt+.** … 直前のコマンドの最後の引数をその場に挿入（押すたびに更に過去へ）
""",
        "example": "mkdir -p deploy/2025/11\ncd !$\nhistory | tail -5\n# Ctrl+R を押して 'mkdir' と打ってみよう",
    },
    {
        "title": "ブレース展開の魔術（{a,b} / {1..10}）",
        "body": """
シェルが `{}` の中身を展開して、複数の引数を一瞬で生成します。
  ・`cp config.yml{,.bak}` → `cp config.yml config.yml.bak`（**最速バックアップ**）
  ・`mv app.log{,.old}` → リネーム ／ `diff nginx.conf{.bak,}` → バックアップと現在の比較
  ・`mkdir -p app/{src,test,docs}` → 3ディレクトリを一度に
  ・`mkdir -p project/{src/{components,utils},tests}` → 入れ子もOK
  ・`touch file{1..5}.txt` → file1.txt〜file5.txt ／ `echo {a..e}` → a b c d e ／ `{01..10}` でゼロ埋め
  ・`echo {1..10..2}` → 1 3 5 7 9（ステップ指定）
注意: `{a, b}` のように **スペースを入れると展開されません**。
""",
        "example": "echo cp nginx.conf{,.bak}     # echo を付けると展開結果だけ確認できる\nmkdir -p demo/{src,test,docs}\ntouch demo/src/file{1..3}.py\nls -R demo",
    },
    {
        "title": "xargs と find -print0 | xargs -0（スペース入りファイル名対策）",
        "body": """
`xargs` は標準入力から受け取った行を、別のコマンドの **引数** に変換します。
  ・`find . -name '*.log' | xargs rm` … 見つけたファイルをまとめて削除
  ・`cat urls.txt | xargs -n 1 curl -sO` … 1行ずつ curl（`-n 1` で1引数ずつ）
  ・`ls *.jpg | xargs -P 4 -I{} convert {} {}.png` … `-P 4` で4並列、`-I{}` で置換位置を指定
注意: ファイル名に **スペース** があると `my file.txt` が `my` と `file.txt` に分かれて事故る！
  → `find . -name '*.tmp' -print0 | xargs -0 rm` … NUL文字(\\0)区切りで受け渡すので安全
  → 別解: `find . -name '*.tmp' -exec rm {} +`（find だけで完結）
""",
        "example": "find . -name '*.tmp' -print0 | xargs -0 ls -l\ngrep -rl 'old_api' src | xargs sed -i 's/old_api/new_api/g'",
    },
    {
        "title": "tee（画面に出しつつファイルにも保存）",
        "body": """
`tee` は入力を **画面（標準出力）とファイルの両方** に書き出す T字型の配管です。
  ・`./deploy.sh | tee deploy.log` … 進捗を見ながらログも残す
  ・`./deploy.sh 2>&1 | tee -a deploy.log` … エラーも含めて追記（`-a` = append）
  ・`cmd | tee result.txt | grep ERROR` … 保存しつつ、パイプの続きで加工
  ・`echo 'nameserver 1.1.1.1' | sudo tee /etc/resolv.conf` … **sudo でファイルに書く定番技**
    （`sudo echo ... > /etc/file` は、リダイレクトを行うのが一般ユーザーのシェルなので Permission denied になる）
""",
        "example": "ls -la | tee listing.txt | wc -l\ncat listing.txt",
    },
    {
        "title": "終了ステータス $? と短絡評価（&& / ||）",
        "body": """
すべてのコマンドは終了時に **終了ステータス** を返します。0 = 成功、1〜255 = 失敗（種類はコマンドごと）。
  ・`echo $?` … 直前のコマンドの終了ステータス（次のコマンドを打つと上書きされるので即確認！）
  ・`cmd1 && cmd2` … cmd1 が **成功したら** cmd2 を実行
  ・`cmd1 || cmd2` … cmd1 が **失敗したら** cmd2 を実行
  ・`make && make test && ./deploy.sh || echo "Failed" >&2` … 成功の連鎖と失敗時の処理を1行で
  ・`cmd1 ; cmd2` … 成否に関係なく順番に実行
  ・`grep -q pattern file && echo found` … `-q` は何も出力せず終了ステータスだけ返す（条件判定に便利）
スクリプトの冒頭に `set -euo pipefail` を書くと「途中で失敗したら即停止」する安全なスクリプトになります。
""",
        "example": "ls /nonexistent; echo \"exit code: $?\"\nmkdir -p build && cd build && echo 'ready'\nfalse || echo 'false は失敗(1)を返す'",
    },
    {
        "title": "watch -n 1（リアルタイム監視）",
        "body": """
`watch` は指定したコマンドを一定間隔で再実行し、画面を更新し続けます（Ctrl+C で終了）。
  ・`watch -n 1 'ls -l uploads/'` … 1秒ごとにファイルの増減を監視
  ・`watch -n 2 df -h` … ディスク使用量の推移を監視
  ・`watch -d 'ss -tn | wc -l'` … `-d` で **変化した部分をハイライト**
  ・`watch -n 5 'docker ps --format "table {{.Names}}\\t{{.Status}}"'` … コンテナの状態監視
パイプやクォートを含むコマンドは全体を `'...'` で囲むのがポイント。
""",
        "example": "watch -n 1 date      # Ctrl+C で終了\nwatch -d -n 1 'ls -l /tmp | tail -5'",
    },
    {
        "title": "diff -u と patch の基本",
        "body": """
設定変更のレビューや差分の共有には **unified diff 形式** が標準です。
  ・`diff -u old.conf new.conf` … `-` 削除行、`+` 追加行、`@@` 変更箇所の位置
  ・`diff -u old.conf new.conf > fix.patch` … 差分をパッチファイルとして保存
  ・`patch target.conf < fix.patch` … 別のファイルに同じ変更を適用 ／ `patch -R` で取り消し ／ `--dry-run` で試行
  ・`diff -r dir1 dir2` … ディレクトリ同士を再帰比較 ／ `diff -q` 差分があるかだけ
  ・`vimdiff a b` / `git diff --no-index a b` … 色付きで見やすく比較
""",
        "example": "printf 'a\\nb\\nc\\n' > v1.txt; printf 'a\\nB\\nc\\nd\\n' > v2.txt\ndiff -u v1.txt v2.txt",
    },
    {
        "title": "プロセス置換 <(cmd) で2つの出力を直接比較",
        "body": """
`<(コマンド)` と書くと、そのコマンドの出力を **一時ファイルのように** 扱えます（実体は /dev/fd/63 など）。
  ・`diff <(sort a.txt) <(sort b.txt)` … 並び順の違う2つのリストを、一時ファイルを作らずに比較
  ・`diff <(ssh web01 cat /etc/nginx/nginx.conf) <(ssh web02 cat /etc/nginx/nginx.conf)` … 2台のサーバーの設定比較
  ・`comm -13 <(sort a) <(sort b)` … b にだけある行（`comm` はソート済み入力が必要）
  ・`while read line; do ...; done < <(cmd)` … ループの中で変数の変更を保持したまま出力を読む
""",
        "example": "diff <(ls /bin) <(ls /usr/bin) | head\ncomm -12 <(printf 'a\\nb\\nc\\n') <(printf 'b\\nc\\nd\\n')",
    },
    {
        "title": "nohup と tmux / screen の基礎知識",
        "body": """
SSH が切れると、そのセッションで動いていたコマンドは SIGHUP を受けて終了してしまいます。
  ・`nohup ./long_job.sh > job.log 2>&1 &` … ログアウトしても動き続ける（出力は job.log へ）
  ・`disown %1` … 既に実行中のジョブを端末から切り離す
  ・**tmux**（推奨）: `tmux new -s work` で新規セッション → 作業 → `Ctrl+B` → `D` でデタッチ（裏で動き続ける）
    → 再接続は `tmux attach -t work`、一覧は `tmux ls`。`Ctrl+B %` で縦分割、`Ctrl+B "` で横分割
  ・**screen**: `screen -S work` → `Ctrl+A` → `D` でデタッチ → `screen -r work` で再接続
長時間のバッチ・DB移行・大容量コピーは **必ず tmux の中で** 実行するのがインフラエンジニアの常識です。
""",
        "example": "nohup sleep 30 > /dev/null 2>&1 &\njobs -l\n# tmux があれば: tmux new -s demo",
    },
    {
        "title": "Readline キーバインド（Ctrl+A / E / W / U ほか）",
        "body": """
長いコマンドを矢印キーで行ったり来たりするのは卒業しよう。bash の行編集は Emacs 風キーバインドです。
  ・`Ctrl+A` 行頭へ ／ `Ctrl+E` 行末へ ／ `Alt+B` / `Alt+F` 単語単位で移動
  ・`Ctrl+W` カーソル前の **1単語を削除** ／ `Ctrl+U` カーソル前を **全部削除** ／ `Ctrl+K` カーソル後を全部削除
  ・`Ctrl+Y` 削除したものを貼り付け（ヤンク）
  ・`Ctrl+L` 画面クリア（`clear` と同じ）／ `Ctrl+C` 入力中の行を破棄 ／ `Ctrl+D` ログアウト（空行で）
  ・`Ctrl+R` 履歴検索 ／ `Ctrl+X Ctrl+E` 今の行を **エディタで編集**（長いワンライナーの修正に神）
  ・`Tab` 補完 ／ `Tab Tab` 候補一覧
""",
        "example": "# 試してみよう: 長い行を打ってから Ctrl+A → Ctrl+E → Ctrl+W → Ctrl+U\necho one two three four five",
    },
]


# ------------------------------------------------------------------ EX-1 ブレース展開
NGINX = "server {\n    listen 80;\n    root /var/www/html;\n}\n"


def se1(ctx):
    ctx.write("nginx.conf", NGINX)


def ce1(ctx):
    if ctx.read("nginx.conf") != NGINX:
        ctx.fail("元の `nginx.conf` が無くなっているか、変更されています。")
    if ctx.read("nginx.conf.bak") != NGINX:
        ctx.fail("`nginx.conf.bak` がありません。`cp nginx.conf{,.bak}` を使ってみよう。")
    for d in ("app/src", "app/test", "app/docs"):
        if not ctx.isdir(d):
            ctx.fail(f"`{d}/` がありません。")
    for i in range(1, 6):
        if not ctx.isfile(f"app/test/test_{i:02d}.py"):
            ctx.fail(f"`app/test/test_{i:02d}.py` がありません（01〜05 のゼロ埋め連番）。")
    if not ctx.used("{"):
        ctx.fail("今回は **ブレース展開** `{...}` を使って作ってみましょう（結果は合っています！）。")


register(
    id="EX-1", stage=S, title="ブレース展開で一撃作成",
    story="""
「バックアップのたびに同じファイル名を2回打つの、面倒じゃない？」と先輩がニヤリ。
**ブレース展開** を使えば、ファイル名を1回打つだけでバックアップも、ディレクトリの量産も一瞬だ。
""",
    objectives=["Webサーバーの設定ファイルを `nginx.conf.bak` へコピーする（元は変更しない）",
                "`app/src`・`app/test`・`app/docs` の3ディレクトリを作る",
                "`app/test/test_01.py` 〜 `app/test/test_05.py` の空ファイルを作る（01〜05 のゼロ埋め連番）",
                "作成にはブレース展開を使い、同じ部分の入力をまとめる"],
    hints=["繰り返す名前の共通部分と、末尾や連番など変わる部分を分けて考えましょう。",
           "ls で元の設定を探し、コピーは cp、ディレクトリ作成は mkdir -p、空ファイルは touch を使います。`{a,b}` は候補の列挙、`{01..05}` はゼロ埋め連番です。echo を先頭に付ければ展開結果だけを確認できます。",
           "`cp nginx.conf{,.bak}` / `mkdir -p app/{src,test,docs}` / `touch app/test/test_{01..05}.py`"],
    answer="echo cp nginx.conf{,.bak}       # 展開結果の確認\ncp nginx.conf{,.bak}\nmkdir -p app/{src,test,docs}\ntouch app/test/test_{01..05}.py\nls -R app",
    explanation="""
ブレース展開はシェルがコマンド実行 **前** に行う文字列生成です（ファイルが存在するかは関係なし）。
  ・`nginx.conf{,.bak}` → `nginx.conf nginx.conf.bak`（カンマの前が空 = 何も付けない）
  ・`app/{src,test,docs}` → `app/src app/test app/docs`
  ・`test_{01..05}.py` → `test_01.py test_02.py ... test_05.py`（先頭の 0 でゼロ埋め）
`*` などのワイルドカード（glob）は「存在するファイル」にマッチするのに対し、ブレース展開は「存在しなくても」文字列を作る、という違いがあります。
""",
    tip="""
設定変更の前に `cp file{,.$(date +%F)}` で日付付きバックアップ → 作業後に `diff file{.$(date +%F),}` で差分確認、が一瞬でできます。
`echo` を先頭に付けて展開結果を確認してから実行するクセを付けると、ブレース展開の事故を防げます。
""",
    setup=se1, check=ce1,
    solution="cp nginx.conf{,.bak}\nmkdir -p app/{src,test,docs}\ntouch app/test/test_{01..05}.py",
    wrong=["cp nginx.conf{,.bak}\nmkdir -p app/{src,test,docs}\ntouch app/test/test_{1..5}.py",
           "cp nginx.conf nginx.conf.bak\nmkdir -p app/src app/test app/docs\ntouch app/test/test_01.py app/test/test_02.py app/test/test_03.py app/test/test_04.py app/test/test_05.py"],
)


# ------------------------------------------------------------------ EX-2 find -print0 | xargs -0
TMPS = ["cache/old report.tmp", "cache/session 01.tmp", "cache/deep/dir name/upload chunk.tmp", "cache/plain.tmp",
        "cache/deep/x.tmp"]
KEEP = ["cache/important notes.txt", "cache/deep/config.yml", "cache/report.tmp.keep"]


def se2(ctx):
    for f in TMPS + KEEP:
        ctx.write(f, "data\n")


def ce2(ctx):
    for f in KEEP:
        if not ctx.exists(f):
            ctx.fail(f"警告: 消してはいけない `{f}` が消えています（`reset_mission` でやり直し）。")
    left = [f for f in TMPS if ctx.exists(f)]
    if left:
        ctx.fail(f"まだ `.tmp` ファイルが残っています: 「{left[0]}」など {len(left)} 件。スペース入りのファイル名が `xargs` で分割されていませんか？")
    if not ctx.used("xargs"):
        ctx.fail("今回は `find` と `xargs` の組み合わせで削除してみましょう（結果は合っています！）。")


register(
    id="EX-2", stage=S, title="スペース入りファイル名の罠（xargs -0）",
    story="""
キャッシュ用ディレクトリの一時ファイルを一括削除したい。検索結果を xargs に渡したら
「`old`: そのようなファイルはありません」と怒られた…。犯人は **ファイル名の中のスペース** だ。
""",
    objectives=["キャッシュ用ディレクトリで `.tmp` で終わる通常ファイルをすべて削除する（スペース入りの名前も含む）",
                "検索と一括処理には find と xargs を組み合わせる",
                "`.tmp` で終わらないファイルは残す"],
    hints=["ファイル名の途中の空白を、引数の区切りと取り違えていないか考えましょう。削除する前に対象を確認します。",
           "ls で対象ディレクトリを探します。find の `-print0` は NUL 文字で区切って出力し、`xargs -0` は NUL 区切りで受け取ります。この2つはセットで使います。",
           "`find cache -name '*.tmp' -print0 | xargs -0 rm -v`"],
    answer="find cache -name '*.tmp' | xargs ls      # ← スペースで分割されて失敗するのを観察\nfind cache -name '*.tmp' -print0 | xargs -0 rm -v\nfind cache -type f",
    explanation="""
`xargs` は標準入力を **空白・タブ・改行** で区切って引数にするため、`old report.tmp` は `old` と `report.tmp` の2つに分かれてしまいます。
  ・`find -print0` … ファイル名を NUL（`\\0`）で区切って出力。NUL はファイル名に使えない唯一の文字なので絶対に安全
  ・`xargs -0` … NUL 区切りで受け取る
  ・`xargs -r` … 入力が空ならコマンドを実行しない（GNU）。`rm` が引数なしでエラーになるのを防ぐ
  ・別解: `find cache -name '*.tmp' -delete` や `find cache -name '*.tmp' -exec rm {} +` も安全
""",
    tip="""
Windows や Mac から来たファイル（`New Folder`、`スクリーンショット 2025-11-18 10.00.00.png`）には平気でスペースが入っています。
スクリプトでは変数を必ず `"$file"` とダブルクォートで囲む、ループは `while IFS= read -r -d '' f; do ...; done < <(find ... -print0)`、
が「スペースに強い」書き方の鉄則です。
""",
    setup=se2, check=ce2,
    solution="find cache -name '*.tmp' -print0 | xargs -0 rm -v",
    wrong=["find cache -name '*.tmp' | xargs rm", "find cache -name '*.tmp*' -print0 | xargs -0 rm",
           "find cache -name '*.tmp' -delete"],
)


# ------------------------------------------------------------------ EX-3 tee
def se3(ctx):
    hosts = [f"web{i:02d}" for i in range(1, 13)]
    ng = random.sample(hosts, random.randint(2, 5))
    ctx.data["ng"] = len(ng)
    lines = [f"{h}: {'NG (timeout)' if h in ng else 'OK'}" for h in hosts]
    ctx.data["out"] = "\n".join(lines) + "\n"
    ctx.write(".hc_data", ctx.data["out"])
    ctx.write("healthcheck.sh", "#!/bin/bash\n# 全Webサーバーのヘルスチェック（模擬）\nwhile read -r l; do echo \"$l\"; sleep 0.05; done < .hc_data\n", mode=0o755)


def ce3(ctx):
    t = ctx.read("health.log")
    if t is None:
        ctx.fail("`health.log` がまだありません。")
    if t != ctx.data["out"]:
        ctx.fail("`health.log` にヘルスチェックの全結果（12行）が保存されていません。`grep` より **前** に `tee` を挟みましょう。")
    if not ctx.used("tee"):
        ctx.fail("今回は `tee` を使って、画面表示とファイル保存を同時に行いましょう。")
    ctx.need_submit(ctx.data["ng"], "NG の台数")


register(
    id="EX-3", stage=S, title="tee で見ながら残す",
    story="""
全Webサーバーのヘルスチェック用スクリプトを実行する。結果は **画面で見ながら**、証跡として **全結果をファイルにも保存** したい。
さらにそのまま **NG の台数** も数えてしまおう。1行のパイプラインで！
""",
    objectives=["ヘルスチェック用スクリプトの全出力を、表示用の処理に渡しつつ `health.log` に保存する（tee を使う）",
                "同じパイプラインの続きで NG の行数を数え、その数を `submit` する"],
    hints=["パイプの途中に「T字の分岐管」を挟むと、流れているデータをファイルにも書き出しつつ、次のコマンドへ流し続けられます。",
           "ls でスクリプトを探します。`cmd | tee ファイル | 次のコマンド` で保存と後続処理を両立できます。条件に合う行を数える道具は grep です。",
           "`./healthcheck.sh | tee health.log | grep -c NG` → 出た数を `submit`"],
    answer="./healthcheck.sh | tee health.log | grep -c NG\nsubmit <<ng>>\ncat health.log",
    explanation="""
`tee ファイル` は標準入力をそのまま標準出力に流しつつ、同じ内容をファイルにも書きます（名前は配管のT字継手から）。
  ・`cmd | tee out.txt` … 画面にも出てファイルにも残る
  ・`cmd | tee out.txt | grep NG` … 全結果を保存しつつ、パイプの続きで絞り込み（ファイルには **絞り込み前** の全結果）
  ・`tee -a` … 追記 ／ `tee f1 f2` … 複数ファイルに同時保存
  ・`cmd 2>&1 | tee log` … エラーも含めて保存
注意: `./healthcheck.sh | grep NG | tee health.log` と順番を変えると、ファイルには NG の行だけが残ります。
""",
    tip="""
長時間かかる作業（OSアップデート、DBマイグレーション）は `sudo apt upgrade 2>&1 | tee upgrade_$(date +%F).log` のように
**画面を見つつ証跡を残す** のがプロの作法。障害報告書に「実行ログ」を添付できます。
`sudo tee` で root 権限のファイルに書き込む技（`echo ... | sudo tee -a /etc/hosts`）も頻出です。
""",
    setup=se3, check=ce3,
    solution='submit "$(./healthcheck.sh | tee health.log | grep -c NG)"',
    wrong=['submit "$(./healthcheck.sh | grep NG | tee health.log | wc -l)"', "./healthcheck.sh > health.log\nsubmit 99"],
)


# ------------------------------------------------------------------ EX-4 $? と && ||
def se4(ctx):
    code = random.choice([2, 3, 4, 5, 7])
    ctx.data["code"] = code
    ctx.write("lint.sh", "#!/bin/bash\necho '[lint] 静的解析 OK'\nexit 0\n", mode=0o755)
    ctx.write("test.sh", f"#!/bin/bash\necho '[test] 42 tests, 1 failed'\nexit {code}\n", mode=0o755)


def ce4(ctx):
    if ctx.exists("deploy.ok"):
        ctx.fail("警告: テストが失敗しているのに `deploy.ok` が作られています！ 失敗したらそれ以降を実行しない繋ぎ方にしましょう（`rm deploy.ok` してやり直し）。")
    t = ctx.read("alert.log")
    if t is None or "FAILED" not in t:
        ctx.fail("`alert.log` に `FAILED` が書き込まれていません。失敗時に実行される側に `echo FAILED > alert.log` を書きましょう。")
    if not (ctx.used("&&") and ctx.used("||")):
        ctx.fail("`&&` と `||` を組み合わせた1行で書いてみましょう。")
    ctx.need_submit(ctx.data["code"], "test.sh の終了ステータス")


register(
    id="EX-4", stage=S, title="終了ステータスと && / || の連鎖",
    story="""
CI もどきを1行で組みたい。「lint が通ったら test、test も通ったらデプロイ許可フラグ `deploy.ok` を作る。
**どこかで失敗したら** `alert.log` に FAILED と書く」。ところで、テスト用スクリプトはどうやら失敗するらしい…。
""",
    objectives=["テスト用スクリプトの終了ステータスを確認し、その値を submit する",
                "lint、test、空ファイル deploy.ok の作成をこの順に、成功したときだけ次へ進む1行にまとめる。途中で失敗したら alert.log に FAILED を保存する（&& と || を使う）",
                "（test が失敗するので `deploy.ok` は作られず、`alert.log` に FAILED が残るのが正解）"],
    hints=["コマンドの成否は「終了ステータス」で判定されます。直前のコマンドの終了ステータスは特殊変数で見られます。",
           "ls と cat で各スクリプトの役割を確かめます。`$?` が直前の終了ステータス（0=成功）。`A && B` は A 成功時のみ B、`A || B` は A 失敗時のみ B。",
           "`./test.sh; echo $?` → `submit <数字>` / `./lint.sh && ./test.sh && touch deploy.ok || echo FAILED > alert.log`"],
    answer="./test.sh\necho $?                # → <<code>>\nsubmit <<code>>\n./lint.sh && ./test.sh && touch deploy.ok || echo FAILED > alert.log\nls; cat alert.log",
    explanation="""
・`$?` … 直前のコマンドの終了ステータス。0 が成功、それ以外が失敗（`grep` は「見つからない」で1、エラーで2 などコマンドごとに意味がある）
  次のコマンドを実行すると上書きされるので、確認は **直後に**。
・`A && B && C || D` の流れ:
  lint 成功(0) → test 失敗(<<code>>) → `touch deploy.ok` はスキップ → 直前の結果が失敗なので `|| D` が実行される
注意: `A && B || C` は if-then-else と完全には同じではありません。**B が失敗した場合も C が実行される** ので、
  厳密に分けたいときは `if A; then B; else C; fi` と書きます。
""",
    tip="""
シェルスクリプトの安全装置 `set -e`（失敗したら即終了）、`set -u`（未定義変数でエラー）、`set -o pipefail`（パイプ途中の失敗も検知）は
3点セットで `set -euo pipefail` と冒頭に書くのが現代の定石です。
`command -v docker >/dev/null || { echo "docker が必要です" >&2; exit 1; }` のような前提チェックも `||` の定番用法です。
""",
    setup=se4, check=ce4,
    solution="./test.sh\nsubmit $?\n./lint.sh && ./test.sh && touch deploy.ok || echo FAILED > alert.log",
    wrong=["./lint.sh ; ./test.sh ; touch deploy.ok || echo FAILED > alert.log\nsubmit <<code>>",
           "./lint.sh && ./test.sh && touch deploy.ok || echo FAILED > alert.log\nsubmit 0",
           "./lint.sh && ./test.sh && touch deploy.ok\nsubmit <<code>>"],
)


# ------------------------------------------------------------------ EX-5 diff -u / patch / プロセス置換
CONF_OLD = "worker_processes 2;\nkeepalive_timeout 65;\nclient_max_body_size 1m;\ngzip off;\n"
CONF_NEW = "worker_processes auto;\nkeepalive_timeout 65;\nclient_max_body_size 20m;\ngzip on;\ngzip_types text/css application/javascript;\n"


def se5(ctx):
    ctx.write("prod/app.conf", CONF_OLD)
    ctx.write("prod/app.conf.new", CONF_NEW)
    ctx.write("staging/app.conf", CONF_OLD)
    pk = ["nginx", "curl", "git", "vim", "htop", "rsync", "jq", "tmux", "openssl", "python3", "unzip", "wget"]
    a = random.sample(pk, len(pk))
    extra = random.choice(["redis-tools", "postgresql-client", "nmap", "strace", "tcpdump"])
    b = [x for x in pk if x != "vim"] + [extra]
    random.shuffle(b)
    ctx.data["extra"] = extra
    ctx.write("server_a.txt", "\n".join(a) + "\n")
    ctx.write("server_b.txt", "\n".join(b) + "\n")


def ce5(ctx):
    p = ctx.read("changes.patch")
    if p is None:
        ctx.fail("`changes.patch` がまだありません。")
    if not ("---" in p and "+++" in p and "@@" in p):
        ctx.fail("`changes.patch` が unified 形式（`---` `+++` `@@` を含む）になっていません。`diff -u` を使いましょう。")
    if ctx.read("prod/app.conf") != CONF_OLD:
        ctx.fail("`prod/app.conf` は変更しないでください（パッチは staging に当てます）。")
    if ctx.read("staging/app.conf") != CONF_NEW:
        ctx.fail("`staging/app.conf` にパッチが適用されていません。`patch staging/app.conf < changes.patch`")
    ctx.need_submit(ctx.data["extra"], "server_b にだけあるパッケージ名")


register(
    id="EX-5", stage=S, title="diff と patch、そしてプロセス置換",
    story="""
本番の設定に対する変更案が出てきた。まずは **差分をパッチファイル** にしてレビューに回し、
同じ変更をステージング環境の設定に **patch で適用** しよう。
ついでに、2台のサーバーのパッケージ一覧（並び順がバラバラ）を比べて、**server_b にだけ入っているもの** を見つけてほしい。
""",
    objectives=["本番の現設定から変更案への差分を、unified 形式の changes.patch に保存する",
                "パッチをステージングの設定に適用する（本番側は変更しない）",
                "並び順の違いを除いて2台のパッケージ一覧を比較し、server_b にだけあるパッケージ名を submit する"],
    hints=["設定の変更内容と、一覧の並び順による見かけの差を分けて考えましょう。本番の原本は保持します。",
           "ls や cat で現設定・変更案・比較資料を探します。差分は diff -u、適用は patch、一覧の並べ替えは sort です。`<(コマンド)` は出力を一時ファイルのように渡すプロセス置換です。",
           "`diff -u prod/app.conf prod/app.conf.new > changes.patch` / `patch staging/app.conf < changes.patch` / `diff <(sort server_a.txt) <(sort server_b.txt)`"],
    answer="diff -u prod/app.conf prod/app.conf.new > changes.patch\ncat changes.patch\npatch --dry-run staging/app.conf < changes.patch\npatch staging/app.conf < changes.patch\ndiff <(sort server_a.txt) <(sort server_b.txt)\nsubmit <<extra>>",
    explanation="""
・`diff -u A B` … unified 形式。`---`/`+++` がファイル名、`@@ -1,4 +1,5 @@` が変更箇所、`-` 行が削除、`+` 行が追加
  （`diff` の終了ステータスは 差分なし=0 / 差分あり=1 / エラー=2 なので、`&&` で繋ぐときは注意）
・`patch ファイル < パッチ` … 差分を適用。`--dry-run` で試行、`-R` で逆適用（取り消し）、`-b` で .orig バックアップ
・`diff <(sort a) <(sort b)` … **プロセス置換**。`sort a > /tmp/x; sort b > /tmp/y; diff /tmp/x /tmp/y` を一時ファイルなしで実現
  出力の `<` は左（a）だけ、`>` は右（b）だけにある行
・`comm -13 <(sort a) <(sort b)` なら「b にだけある行」だけを直接出力できます。
""",
    tip="""
「本番と検証環境で設定が違う」問題の調査に `diff <(ssh prod cat /etc/app.conf) <(ssh stg cat /etc/app.conf)` は超強力。
Git 管理外のサーバー設定を変更するときも、`diff -u` で差分を残してから適用すると、レビューもロールバックも楽になります。
（もちろん理想は、設定を Ansible などの構成管理ツールと Git で管理することです）
""",
    setup=se5, check=ce5,
    solution='diff -u prod/app.conf prod/app.conf.new > changes.patch\npatch staging/app.conf < changes.patch\nsubmit "$(diff <(sort server_a.txt) <(sort server_b.txt) | grep "^>" | cut -c3-)"',
    wrong=['diff prod/app.conf prod/app.conf.new > changes.patch\npatch staging/app.conf < changes.patch\nsubmit <<extra>>',
           'diff -u prod/app.conf prod/app.conf.new > changes.patch\npatch prod/app.conf < changes.patch\nsubmit <<extra>>',
           'diff -u prod/app.conf prod/app.conf.new > changes.patch\npatch staging/app.conf < changes.patch\nsubmit vim'],
)
