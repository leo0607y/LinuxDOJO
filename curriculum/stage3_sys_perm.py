"""Stage 3: パーミッション・プロセス・環境変数・システム監視（8問）"""
import os
import random
import re

from engine.runner import register, proc_alive, proc_cmdline

S = 3


def _oct(m):
    return f"{m:03o}"


# ------------------------------------------------------------------ 3-1
def s31(ctx):
    ctx.write("deploy.sh", "#!/bin/bash\necho 'deploying...'\n", mode=0o644)
    # 権限設定の教材用ダミー鍵。PEM の見出しだけを模しており、暗号鍵として利用できません。
    ctx.write("secret.key", "-----BEGIN PRIVATE KEY-----\nMIIE...dummy...\n-----END PRIVATE KEY-----\n", mode=0o644)
    ctx.write("index.html", "<h1>Penguin Shop</h1>\n", mode=0o600)


def c31(ctx):
    if ctx.mode("deploy.sh") != 0o755:
        ctx.fail(f"`deploy.sh` のパーミッションが {_oct(ctx.mode('deploy.sh'))} です。所有者は全権限、他は読み＋実行（755）にしましょう。")
    if ctx.mode("secret.key") != 0o600:
        ctx.fail(f"`secret.key` のパーミッションが {_oct(ctx.mode('secret.key'))} です。所有者だけが読み書きできる状態（600）にしましょう。")
    if ctx.mode("index.html") != 0o644:
        ctx.fail(f"`index.html` のパーミッションが {_oct(ctx.mode('index.html'))} です。Webサーバーが読めるよう 644 にしましょう。")
    u = os.umask(0)
    os.umask(u)
    s = ctx.submitted()
    if not s:
        ctx.fail("最後に `umask` コマンドで現在の umask 値を確認し、`submit` してください。")
    try:
        ok = int(s.strip(), 8) == u
    except ValueError:
        ok = False
    if not ok:
        ctx.fail(f"提出された umask「{s}」は現在の値と違います。`umask` を実行して表示された数字をそのまま提出しましょう。")


register(
    id="3-1", stage=S, title="パーミッションを数字で操る",
    story="""
新しいWebサーバーにファイルを配置したが、権限がバラバラで動かない＆危ない状態だ。
`deploy.sh` は実行できず、秘密鍵 `secret.key` は誰でも読めてしまい、`index.html` は Web サーバーから読めない。
`ls -l` で現状を確認し、**数値指定** で正しい権限に直せ。
""",
    objectives=["`deploy.sh` → `755`（rwxr-xr-x）", "`secret.key` → `600`（rw-------）", "`index.html` → `644`（rw-r--r--）",
                "`umask` を実行し、表示された値を `submit` する（新規ファイルの既定権限を決める値）"],
    hints=["`ls -l` の `rwxr-xr-x` は「所有者 / グループ / その他」の3組。r=4, w=2, x=1 の足し算で数字にできます。",
           "`chmod 755 ファイル` のように3桁の数字で指定します。rwx=7, rw-=6, r-x=5, r--=4。",
           "`chmod 755 deploy.sh` / `chmod 600 secret.key` / `chmod 644 index.html` / `umask` → 出た値を `submit 0002` のように提出。"],
    answer="ls -l\nchmod 755 deploy.sh\nchmod 600 secret.key\nchmod 644 index.html\numask           # 例: 0002\nsubmit 0002",
    explanation="""
`ls -l` の先頭 `-rwxr-xr-x` の読み方: 1文字目は種類（`-`ファイル `d`ディレクトリ `l`リンク）、残り9文字が
「所有者(u)」「グループ(g)」「その他(o)」に3文字ずつ。r(読み)=4, w(書き)=2, x(実行)=1 を足すと数字になります。
  ・`755` = rwx / r-x / r-x … スクリプトやディレクトリの定番
  ・`644` = rw- / r-- / r-- … 一般的なファイル
  ・`600` = rw- / --- / --- … 秘密鍵・パスワードファイル
  ・`700` = rwx / --- / --- … `~/.ssh` ディレクトリなど
**umask** は新規作成時に「外す権限」です。umask `0022` なら ファイル 666−022 = **644**、ディレクトリ 777−022 = **755** で作られます。
（Ubuntu の一般ユーザーは `0002` が多く、その場合は 664 / 775 になります）
""",
    tip="""
SSH は秘密鍵のパーミッションが緩いと `WARNING: UNPROTECTED PRIVATE KEY FILE!` と言って **接続を拒否** します。
`chmod 600 ~/.ssh/id_ed25519` は必修。
⚠ 困ったときの `chmod 777` は「誰でも書き換え可能」＝改ざん・マルウェア設置の温床になるので、本番では絶対に避けましょう。
""",
    setup=s31, check=c31,
    solution='chmod 755 deploy.sh\nchmod 600 secret.key\nchmod 644 index.html\nsubmit "$(umask)"',
    wrong=['chmod 777 deploy.sh secret.key index.html\nsubmit "$(umask)"',
           'chmod 755 deploy.sh\nchmod 644 secret.key\nchmod 644 index.html\nsubmit "$(umask)"',
           "chmod 755 deploy.sh\nchmod 600 secret.key\nchmod 644 index.html\nsubmit 0777"],
)


# ------------------------------------------------------------------ 3-2
SCRIPTS = ["scripts/backup.sh", "scripts/cleanup.sh", "scripts/healthcheck.sh"]


def s32(ctx):
    for f in SCRIPTS:
        ctx.write(f, "#!/bin/bash\necho ok\n", mode=0o644)
    ctx.write("scripts/README.md", "スクリプト置き場\n", mode=0o644)
    ctx.write("public/notice.txt", "お知らせ\n", mode=0o666)
    ctx.write("public/terms.txt", "利用規約\n", mode=0o666)


def c32(ctx):
    for f in SCRIPTS:
        m = ctx.mode(f)
        if m != 0o744:
            if m & 0o011:
                ctx.fail(f"`{f}` がグループやその他のユーザーにも実行可能になっています（{_oct(m)}）。**所有者だけ** に実行権限を付けましょう（u+x）。")
            ctx.fail(f"`{f}` のパーミッションが {_oct(m)} です。所有者に実行権限を追加して 744 にしましょう。")
    if ctx.mode("scripts/README.md") != 0o644:
        ctx.fail("`scripts/README.md` はスクリプトではないので 644 のままにしましょう（`*.sh` だけが対象）。")
    for f in ("public/notice.txt", "public/terms.txt"):
        m = ctx.mode(f)
        if m != 0o664:
            ctx.fail(f"`{f}` のパーミッションが {_oct(m)} です。「その他(o)」から書き込み(w)権限だけを外しましょう（664 になるはず）。")


register(
    id="3-2", stage=S, title="記号モードで差分だけ変更する",
    story="""
数字指定は「全部を決め直す」方法。でも現場では「**今の権限に実行権限だけ足したい**」「**他人の書き込みだけ外したい**」
という差分変更が多い。記号モード（`u+x` など）でピンポイントに直そう。
""",
    objectives=["`scripts/` 内の `*.sh` すべてに **所有者だけ** 実行権限を追加する（644 → 744）",
                "`public/` 内の2ファイルから **その他のユーザーの書き込み権限** だけを外す（666 → 664）"],
    hints=["記号モードは「誰に(u/g/o/a)」「足す(+)/外す(-)」「何を(r/w/x)」の組み合わせです。",
           "`chmod u+x ファイル` で所有者に実行権限を追加。`chmod o-w ファイル` でその他から書き込みを除去。ワイルドカードも使えます。",
           "`chmod u+x scripts/*.sh` と `chmod o-w public/*.txt`"],
    answer="chmod u+x scripts/*.sh\nchmod o-w public/*.txt\nls -l scripts public",
    explanation="""
記号モードの書式: `chmod [u|g|o|a][+|-|=][r|w|x] ファイル`
  ・`u`=所有者(user) `g`=グループ `o`=その他(others) `a`=全員(all)
  ・`+` 追加 ／ `-` 削除 ／ `=` その値に設定
  ・例: `chmod +x run.sh`（誰に、を省略すると umask を考慮した全員）、`chmod go-rwx secret`、`chmod u=rw,go=r file`
`chmod -R` で配下を再帰的に変更できますが、ディレクトリとファイルで適切な権限は違うので、
`find . -type f -exec chmod 644 {} +` / `find . -type d -exec chmod 755 {} +` のように分けるのがプロの技です。
""",
    tip="""
Git で管理しているスクリプトに実行権限を付けたら、`git update-index --chmod=+x script.sh` でリポジトリにも記録できます。
「Permission denied で CI のスクリプトが動かない」は実行権限の付け忘れが原因の定番トラブルです。
`chmod +x` は `a+x` と違い umask の影響を受ける、という細かい違いも覚えておくと一目置かれます。
""",
    setup=s32, check=c32,
    solution="chmod u+x scripts/*.sh\nchmod o-w public/*.txt",
    wrong=["chmod +x scripts/*.sh\nchmod o-w public/*.txt", "chmod u+x scripts/*\nchmod o-w public/*.txt",
           "chmod u+x scripts/*.sh\nchmod 644 public/*.txt"],
)


# ------------------------------------------------------------------ 3-3
def s33(ctx):
    ctx.write("versions/app-2.0.0/app.py", "VERSION = '2.0.0'\n")
    ctx.write("versions/app-2.1.0/app.py", "VERSION = '2.1.0'\n")
    os.symlink("versions/app-2.0.0", ctx.p("current"))
    ctx.write("logs_store/app.log", "log line\n")
    os.symlink("/var/log/penguin-old-deleted", ctx.p("logs"))
    ctx.write("data.txt", "大事なマスターデータ\n")


def c33(ctx):
    cur = ctx.p("current")
    if not cur.is_symlink():
        ctx.fail("`current` がシンボリックリンクになっていません（ディレクトリやファイルになっていませんか？）。")
    if cur.resolve() != ctx.p("versions/app-2.1.0").resolve():
        if ctx.p("versions/app-2.0.0/app-2.1.0").is_symlink():
            ctx.fail("`versions/app-2.0.0/` の中にリンクが作られてしまっています。既存リンクの **リンク先ディレクトリの中** に作らないよう `-n` を付けましょう。")
        ctx.fail(f"`current` が `versions/app-2.1.0` を指していません（現在: {os.readlink(cur)}）。")
    lg = ctx.p("logs")
    if not lg.is_symlink():
        ctx.fail("`logs` をシンボリックリンクとして作り直してください。")
    if not lg.exists() or lg.resolve() != ctx.p("logs_store").resolve():
        ctx.fail("`logs` のリンクが切れているか、`logs_store` を指していません。")
    h = ctx.p("data_hard.txt")
    if not h.exists():
        ctx.fail("ハードリンク `data_hard.txt` がありません。")
    if h.is_symlink():
        ctx.fail("`data_hard.txt` がシンボリックリンクになっています。`-s` を付けずに **ハードリンク** を作りましょう。")
    if os.stat(h).st_ino != os.stat(ctx.p("data.txt")).st_ino:
        ctx.fail("`data_hard.txt` が `data.txt` と同じ実体（inode）を共有していません。コピーではなくハードリンクを作りましょう。")


register(
    id="3-3", stage=S, title="リンクで切り替えるデプロイ術",
    story="""
本番サーバーでは `current` というシンボリックリンクで「今動かすバージョン」を切り替えている。
新バージョン `app-2.1.0` をリリースするので、リンクを張り替えてほしい。
ついでに、リンク先が消えて **リンク切れ** になっている `logs` の修復と、`data.txt` の **ハードリンク** 作成も頼む。
""",
    objectives=["`current` の向き先を `versions/app-2.1.0` に張り替える（現在は 2.0.0 を指している）",
                "リンク切れの `logs` を、`logs_store` を指すリンクに作り直す",
                "`data.txt` のハードリンク `data_hard.txt` を作成する"],
    hints=["`ls -l` で `current -> versions/app-2.0.0` のように向き先が見えます。リンク切れは赤く表示されることも。",
           "`ln -s 実体 リンク名` でシンボリックリンク。既存リンクの上書きは `-f`、ディレクトリへのリンクは `-n` も必要。ハードリンクは `-s` なし。",
           "`ln -sfn versions/app-2.1.0 current` / `ln -sfn logs_store logs` / `ln data.txt data_hard.txt`"],
    answer="ls -l\nln -sfn versions/app-2.1.0 current\nln -sfn logs_store logs\nln data.txt data_hard.txt\nls -li data.txt data_hard.txt   # inode 番号が同じ！",
    explanation="""
・**シンボリックリンク** (`ln -s`) … 「パスへのショートカット」。実体が消えると **リンク切れ** になる。ディレクトリにも張れる。
・**ハードリンク** (`ln`) … 同じ実体（inode）に別名を付ける。どちらかを消してももう片方から読める。ディレクトリや別ディスクには不可。
`ls -li` の先頭の数字が inode 番号。ハードリンク同士は同じ番号になります。
⚠ 既存の `current`（ディレクトリへのリンク）に `ln -sf new current` すると、リンクを辿って
  `versions/app-2.0.0/app-2.1.0` という **リンク先の中** に作られてしまいます。`-n`（no-dereference）でリンク自体を置き換えましょう。
リンク切れの発見には `find . -xtype l` が便利です。
""",
    tip="""
Capistrano などのデプロイツールは `releases/日時/` に新版を置き、`current` シンボリックリンクを `ln -sfn` で張り替えます。
**切り替えが一瞬** で、問題があれば前のリリースにリンクを戻すだけでロールバックできるのが利点です。
`/etc/nginx/sites-enabled/` → `sites-available/` へのリンクや、`python3 -> python3.12` も同じ仕組みです。
""",
    setup=s33, check=c33,
    solution="ln -sfn versions/app-2.1.0 current\nln -sfn logs_store logs\nln data.txt data_hard.txt",
    wrong=["ln -sf versions/app-2.1.0 current\nln -sfn logs_store logs\nln data.txt data_hard.txt",
           "ln -sfn versions/app-2.1.0 current\nln -sfn logs_store logs\nln -s data.txt data_hard.txt",
           "ln -sfn versions/app-2.1.0 current\nln -sfn logs_store logs\ncp data.txt data_hard.txt"],
)


# ------------------------------------------------------------------ 3-4
def s34(ctx):
    ctx.write("mytools/bin/hello-lq", "#!/bin/bash\necho \"Hello from hello-lq! APP_ENV=${APP_ENV:-未設定}\"\n", mode=0o755)
    ctx.write("mytools/bin/logcount", "#!/bin/bash\nwc -l \"$@\"\n", mode=0o755)


def c34(ctx):
    env = ctx.env()
    if not env:
        ctx.fail("環境の情報がありません。コマンドを1つ実行してから `check` してください。")
    target = ctx.p("mytools/bin").resolve()
    entries = env.get("PATH", "").split(":")
    hit = [e for e in entries if e and os.path.isabs(e) and os.path.realpath(e) == str(target)]
    if not hit:
        rel = [e for e in entries if e and not os.path.isabs(e) and "mytools" in e]
        if rel:
            ctx.fail(f"PATH に相対パス `{rel[0]}` が入っています。別のディレクトリに移動すると見つからなくなるので **絶対パス** で追加しましょう（`$PWD` が便利）。")
        if ctx.used("PATH="):
            ctx.fail("PATH に `mytools/bin` の絶対パスが含まれていません。元の `$PATH` を消さずに **追加** できていますか？")
        ctx.fail("環境変数 PATH に `mytools/bin` の絶対パスが追加されていません。")
    if "/usr/bin" not in entries and "/bin" not in entries:
        ctx.fail("PATH から `/usr/bin` が消えています！ `ls` すら動かない状態です。`export PATH=\"新しいパス:$PATH\"` のように元の値を残しましょう。")
    if env.get("APP_ENV") != "production":
        if ctx.used("APP_ENV=production"):
            ctx.fail("`APP_ENV` は設定されていますが **export** されていません。子プロセス（`hello-lq` など）から見えるように `export` しましょう。")
        ctx.fail("環境変数 `APP_ENV=production` が export されていません。")


register(
    id="3-4", stage=S, title="環境変数と PATH の仕組み",
    story="""
チームの便利ツール集 `mytools/bin/` に `hello-lq` コマンドがある。でも毎回 `./mytools/bin/hello-lq` と打つのは面倒だ。
**PATH を通して** どこからでも `hello-lq` で実行できるようにし、アプリが本番モードで動くよう `APP_ENV=production` も設定しよう。
""",
    objectives=["`mytools/bin` の **絶対パス** を、元の PATH を残したまま環境変数 `PATH` に追加する",
                "環境変数 `APP_ENV` に `production` を設定し、子プロセスからも見えるよう **export** する",
                "（確認）`hello-lq` とだけ打って `APP_ENV=production` と表示されれば OK"],
    hints=["コマンド名だけで実行できるのは、PATH に並んだディレクトリをシェルが順番に探しているから。`echo $PATH` で中身を見てみよう。",
           "`export 変数名=値` で環境変数を設定。PATH は `:` 区切り。今いる場所の絶対パスは `$PWD` で取れます。",
           "`export PATH=\"$PWD/mytools/bin:$PATH\"` と `export APP_ENV=production` → `hello-lq` で確認。"],
    answer="echo $PATH\nexport PATH=\"$PWD/mytools/bin:$PATH\"\nexport APP_ENV=production\nhello-lq\nwhich hello-lq\nenv | grep APP_ENV",
    explanation="""
・`VAR=value` … **シェル変数**。そのシェルの中だけで有効
・`export VAR=value` … **環境変数**。そのシェルから起動する子プロセス（コマンドやスクリプト）にも引き継がれる
・`env` / `printenv` … 環境変数の一覧 ／ `echo $VAR` … 値の表示 ／ `unset VAR` … 削除
PATH は「コマンドを探すディレクトリ」を `:` で繋いだリストで、**左から順に** 探されます。
`export PATH="$PWD/mytools/bin:$PATH"` は「新しいディレクトリ + 元の PATH」という意味。
⚠ `export PATH=mytools/bin` のように元の値を消すと、`ls` も `cat` も見つからなくなります（そのシェルを閉じれば元通り）。
`which コマンド` / `type コマンド` で、実際にどのファイルが実行されるか確認できます。
""",
    tip="""
ここで設定した PATH は **このシェルを閉じると消えます**。永続化するには `~/.bashrc` に
`export PATH="$HOME/bin:$PATH"` を追記し、`source ~/.bashrc` で反映します。
Docker や CI では環境変数で設定を切り替えるのが基本（The Twelve-Factor App）。
`APP_ENV=staging ./app` のように **1コマンドだけ** に環境変数を渡す書き方も便利です。
""",
    setup=s34, check=c34,
    solution='export PATH="$PWD/mytools/bin:$PATH"\nexport APP_ENV=production\nhello-lq',
    wrong=['export PATH="mytools/bin:$PATH"\nexport APP_ENV=production',
           'export PATH="$PWD/mytools/bin:$PATH"\nAPP_ENV=production',
           'export PATH="$PWD/mytools/bin"\nexport APP_ENV=production'],
)


# ------------------------------------------------------------------ 3-5
def s35(ctx):
    log = ctx.p("worker.log")
    ctx.write("worker.log", "")
    body = f"""#!/bin/bash
# 暴走ワーカー（SIGTERM を無視する行儀の悪いプロセス）
trap 'echo "$(date +%T) SIGTERM を受け取ったが無視した" >> "{log}"' TERM
while [ $SECONDS -lt 10800 ]; do
  echo "$(date +%T) working..." >> "{log}.raw"
  sleep 1
done
"""
    ctx.data["pid"] = ctx.spawn("lq_runaway_worker", body)
    ctx.write("README.txt", "ワーカーが暴走中。lq_runaway_worker という名前のプロセスを止めてください。\n")


def c35(ctx):
    pid = ctx.data["pid"]
    if proc_alive(pid):
        ign = ctx.read("worker.log") or ""
        if "無視" in ign:
            ctx.fail("`kill`（SIGTERM）は無視されてしまったようです（worker.log を見てみよう）。強制終了のシグナルを送りましょう。")
        ctx.fail("`lq_runaway_worker` プロセスがまだ動いています。PID を調べて停止させましょう。")


register(
    id="3-5", stage=S, title="言うことを聞かない暴走プロセス",
    story="""
夜間バッチのワーカー `lq_runaway_worker` が暴走して止まらない！
まずは行儀よく `kill`（SIGTERM）で止めてみよう…と思ったが、どうやらこのプロセスは **SIGTERM を無視する** 作りらしい。
""",
    objectives=["`ps aux` や `pgrep` で `lq_runaway_worker` の PID を特定する",
                "`kill` で停止を試み、止まらなければ **強制終了** する"],
    hints=["実行中のプロセス一覧は `ps aux`。大量に出るので grep で絞り込みましょう。`pgrep` なら PID だけを直接出せます。",
           "`kill PID` は SIGTERM（終了してね、というお願い）。無視されたら `kill -9 PID`（SIGKILL: 問答無用で強制終了）。",
           "`ps aux | grep lq_runaway` または `pgrep -f lq_runaway_worker` → `kill <PID>` → `cat worker.log` → `kill -9 <PID>`"],
    answer="ps aux | grep [l]q_runaway_worker\npgrep -f lq_runaway_worker        # PID だけ表示\nkill <<pid>>                       # SIGTERM → 無視される\ncat worker.log\nkill -9 <<pid>>                    # SIGKILL で強制終了\npgrep -f lq_runaway_worker || echo 停止完了",
    explanation="""
・`ps aux` … 全プロセスを表示（a=全ユーザー, u=詳細, x=端末なしも）。PID は2列目、%CPU/%MEM も見られる
・`ps aux | grep [l]q_runaway` … `[l]` のトリックで grep 自身の行が出なくなる
・`pgrep -f 名前` … コマンドライン全体から検索して PID だけを出力 ／ `pkill -f 名前` … 名前で直接 kill
シグナルの種類:
  ・`kill PID` = `kill -15` = **SIGTERM** … 「終了してください」。プロセスは後片付けしてから終了できる（無視もできる）
  ・`kill -9 PID` = **SIGKILL** … カーネルが強制終了。無視不可だが、後片付けされない（一時ファイルやロックが残る）
  ・`kill -HUP PID` … 設定の再読み込みに使われることが多い
**まず SIGTERM、ダメなら SIGKILL** が正しい順番です。最初から `-9` はデータ破損のリスクがあります。
""",
    tip="""
リソースを食い潰しているプロセスを探すなら `top`（`P` でCPU順、`M` でメモリ順、`k` でkill、`q` で終了）や
高機能版の `htop` が定番です。`ps aux --sort=-%cpu | head` でも CPU 上位を一発で出せます。
systemd 管理のサービスなら `kill` ではなく `systemctl stop サービス名` で止めるのが正解です。
""",
    setup=s35, check=c35,
    solution="kill $(pgrep -f lq_runaway_worker)\nsleep 0.3\nkill -9 $(pgrep -f lq_runaway_worker)\nsleep 0.2",
    wrong=["kill $(pgrep -f lq_runaway_worker)\nsleep 1.5"],
)


# ------------------------------------------------------------------ 3-6
def s36(ctx):
    ctx.write("backup_job.sh", """#!/bin/bash
# 時間のかかるバックアップ処理（の模擬）
for i in $(seq 1 600); do
  echo "$(date +%T) backup progress: $i/600" >> backup_progress.log
  sleep 1
done
""", mode=0o755)


def c36(ctx):
    jobs = ctx.jobs()
    lines = [ln for ln in jobs.splitlines() if "backup_job.sh" in ln]
    if not lines:
        ctx.fail("`jobs` に `backup_job.sh` が見当たりません。バックグラウンドジョブとして実行しましょう。")
    if not any(re.search(r"Running|実行中", ln) for ln in lines):
        if any(re.search(r"Stopped|停止", ln) for ln in lines):
            ctx.fail("`backup_job.sh` は **一時停止(Stopped)** 中です。`bg` でバックグラウンドで再開させましょう。")
        ctx.fail("`backup_job.sh` がバックグラウンドで実行中(Running)になっていません。")


register(
    id="3-6", stage=S, title="ジョブ制御: 端末を手放さずに待つ",
    story="""
10分かかるバックアップ `./backup_job.sh` を実行したら、終わるまで端末が使えなくなってしまった！
処理は止めずに、**バックグラウンドに回して** 作業を続けたい。
""",
    objectives=["`./backup_job.sh` を実行し、`Ctrl+Z` で一時停止 → `bg` でバックグラウンド再開する（または最初から `&` 付きで起動）",
                "`jobs` でそのジョブが Running（実行中）になっていることを確認する"],
    hints=["フォアグラウンドで動いているコマンドは `Ctrl+Z` で一時停止できます。停止したジョブは別のコマンドで再開できます。",
           "`bg` = バックグラウンドで再開、`fg` = フォアグラウンドに戻す、`jobs` = ジョブ一覧。最初から `コマンド &` でもOK。",
           "`./backup_job.sh` → `Ctrl+Z` → `bg` → `jobs`（`[1]+ 実行中 ./backup_job.sh &` と出ればOK）"],
    answer="./backup_job.sh     # 実行して…\n# Ctrl+Z を押す → [1]+ 停止 ./backup_job.sh\nbg                  # バックグラウンドで再開\njobs                # [1]+ 実行中 ./backup_job.sh &\n# （別解）./backup_job.sh &",
    explanation="""
・`コマンド &` … 最初からバックグラウンドで実行（`[1] 12345` のようにジョブ番号とPIDが表示される）
・`Ctrl+Z` … フォアグラウンドのジョブを **一時停止**（SIGTSTP）。止まっているだけで終了はしていない
・`bg [%番号]` … 停止中のジョブをバックグラウンドで再開
・`fg [%番号]` … バックグラウンドのジョブをフォアグラウンドに戻す（Ctrl+C で止めたいときなど）
・`jobs -l` … ジョブ一覧を PID 付きで表示 ／ `kill %1` … ジョブ番号1を終了
`tail -f backup_progress.log` で進捗を眺めてみましょう（Ctrl+C で tail だけ終了）。
""",
    tip="""
⚠ `&` や `bg` のジョブは **端末（SSH）を閉じると道連れで終了** することがあります（SIGHUP）。
SSH 切断後も処理を続けたいなら `nohup ./job.sh > job.log 2>&1 &` や、`tmux` / `screen` のセッション内で実行するのが鉄則。
すでに実行中のジョブなら `disown %1` で端末から切り離せます（Extra Stage の小ネタ集も参照）。
""",
    setup=s36, check=c36,
    solution="./backup_job.sh &\nsleep 0.2",
    wrong=["./backup_job.sh & \nkill %1\nsleep 0.2"],
)


# ------------------------------------------------------------------ 3-7
def s37(ctx):
    ctx.write("README.txt", "サーバーの健康診断をして health_report.txt にまとめてください。\n")


def c37(ctx):
    t = ctx.read("health_report.txt")
    if t is None:
        ctx.fail("`health_report.txt` がまだありません。")
    if not re.search(r"Filesystem|ファイルシス", t):
        ctx.fail("ディスク使用量（`df -h` の結果）が含まれていません。")
    if "Mem:" not in t and "メモリ" not in t:
        ctx.fail("メモリ使用量（`free -h` の結果）が含まれていません。")
    if not re.search(r"load average|負荷平均", t):
        ctx.fail("負荷状況（`uptime` の結果）が含まれていません。")
    if not ctx.used("-h"):
        ctx.fail("`df` や `free` は `-h` を付けて人間が読みやすい単位で表示しましょう。")


register(
    id="3-7", stage=S, title="サーバーの健康診断レポート",
    story="""
「最近サーバーが重い気がする」と問い合わせが来た。まずは基本の健康診断だ。
**ディスク・メモリ・負荷** の3点を確認し、結果を1つのレポートファイルにまとめて共有しよう。
""",
    objectives=["`df -h`（ディスク使用量）、`free -h`（メモリ使用量）、`uptime`（稼働時間と負荷平均）を実行する",
                "3つの結果をすべて `health_report.txt` にまとめて保存する（`>` と `>>` を使い分けよう）"],
    hints=["1つ目は `>` で新規作成、2つ目以降は `>>` で追記すれば、1つのファイルにまとめられます。",
           "`df -h` / `free -h` / `uptime`。`{ cmd1; cmd2; cmd3; } > file` とまとめてリダイレクトする方法もあります。",
           "`df -h > health_report.txt` → `free -h >> health_report.txt` → `uptime >> health_report.txt`"],
    answer="df -h > health_report.txt\nfree -h >> health_report.txt\nuptime >> health_report.txt\ncat health_report.txt\n# 別解: { df -h; free -h; uptime; } > health_report.txt",
    explanation="""
・`df -h` … ファイルシステム（ディスク）ごとの使用量。**Use% が 80〜90% を超えていたら要注意**
・`free -h` … メモリ使用量。見るべきは `available`（実際に使える量）。`buff/cache` はすぐ解放できるので心配不要
・`uptime` … 稼働時間と **load average**（1分/5分/15分平均）。CPUコア数（`nproc`）を大きく超えていたら過負荷
・`du -sh *` … カレント配下の各ファイル・ディレクトリの合計サイズ（次の問題で使います！）
`{ cmd1; cmd2; }` はコマンドのグループ化。まとめて1回のリダイレクトで保存できます（`}` の前の `;` を忘れずに）。
""",
    tip="""
障害の初動は「`uptime` → `free -h` → `df -h` → `top`」の順で全体像を掴むのが定番です。
`df -i` で **inode 枯渇**（容量は空いているのにファイルが作れない）もチェックできます。
定期的な監視は Prometheus + node_exporter や Zabbix などの監視ツールに任せ、閾値を超えたらアラートを飛ばすのが現代流です。
""",
    setup=s37, check=c37,
    solution="df -h > health_report.txt\nfree -h >> health_report.txt\nuptime >> health_report.txt",
    wrong=["df -h > health_report.txt\nfree -h > health_report.txt\nuptime > health_report.txt"],
)


# ------------------------------------------------------------------ 3-8
def s38(ctx):
    ctx.sparse("var/cache/app/tmp/core.20251118.dump", 40 * 1024 * 1024)
    for f, sz in {"var/log/app/app.log": 900_000, "var/log/app/access.log": 1_200_000,
                  "var/lib/app/data.db": 2_000_000, "var/cache/app/thumb_001.jpg": 300_000,
                  "var/cache/app/thumb_002.jpg": 300_000, "var/lib/app/sessions/sess_01": 50_000}.items():
        ctx.sparse(f, sz)
    ctx.write("deploy.sh", f"""#!/bin/bash
# 本番アプリ起動スクリプト
USED=$(du -sm var | cut -f1)
if [ "$USED" -gt 20 ]; then
  echo "ERROR: ディスク逼迫のため起動できません (var/ 使用量 ${{USED}}MB > 20MB)" >&2
  exit 1
fi
echo $$ > deploy.pid
echo "$(date +%T) app started (pid=$$)" >> app_boot.log
while [ $SECONDS -lt 10800 ]; do sleep 2; done
""", mode=0o644)


def c38(ctx):
    for f in ("var/log/app/app.log", "var/log/app/access.log", "var/lib/app/data.db"):
        if not ctx.exists(f):
            ctx.fail(f"🚨 必要なファイル `{f}` まで消えています！犯人の巨大ファイルだけを消しましょう（`reset_mission` でやり直し）。")
    if ctx.exists("var/cache/app/tmp/core.20251118.dump"):
        ctx.fail("ディスクを圧迫している巨大ファイルがまだ残っています。`du` で犯人を突き止めましょう。")
    if not os.access(ctx.p("deploy.sh"), os.X_OK):
        ctx.fail("`deploy.sh` に実行権限がありません。")
    pidtxt = ctx.read("deploy.pid")
    if not pidtxt or not pidtxt.strip().isdigit():
        ctx.fail("アプリがまだ起動していません（`deploy.pid` がありません）。`./deploy.sh` をバックグラウンドで起動しましょう。")
    pid = int(pidtxt.strip())
    if not proc_alive(pid) or "deploy.sh" not in proc_cmdline(pid):
        ctx.fail("`deploy.sh` のプロセスが動いていません。Ctrl+C で止めたりしていませんか？ `&` を付けてバックグラウンドで起動しましょう。")


register(
    id="3-8", stage=S, title="【実践】ディスク逼迫と起動しないアプリ",
    story="""
🚨 深夜のアラート:「本番アプリが落ちている。再起動スクリプト `deploy.sh` も動かない！」
調べると、① `var/` 配下のどこかに **巨大なゴミファイル** があってディスクが逼迫し、② `deploy.sh` には **実行権限が無い** らしい。
犯人を突き止めて片付け、アプリを **バックグラウンドで** 起動させよ。
""",
    objectives=["`du` で `var/` 配下の容量食いの犯人（巨大な不要ファイル）を突き止めて **それだけ** 削除する",
                "`deploy.sh` に実行権限を付ける",
                "`./deploy.sh` をバックグラウンドで起動し、プロセスが動き続けている状態にする"],
    hints=["大きいディレクトリを上から順に掘っていくのが定石。`du` で各ディレクトリの合計サイズを見て、大きい方へ潜っていきます。",
           "`du -sh var/*` → 一番大きいところへ → `du -sh var/cache/*` …。`du -ah var | sort -h | tail` で一気に探す手も。権限は `chmod +x`、起動は `&`。",
           "`du -ah var | sort -h | tail -5` → `rm var/cache/app/tmp/core.*.dump` → `chmod +x deploy.sh` → `./deploy.sh &` → `jobs`"],
    answer="du -sh var/*\ndu -ah var | sort -h | tail -5     # 犯人: var/cache/app/tmp/core.20251118.dump\nrm var/cache/app/tmp/core.20251118.dump\nchmod +x deploy.sh\n./deploy.sh &\njobs\ncat app_boot.log",
    explanation="""
・`du -sh ディレクトリ` … 合計サイズ（s=summary, h=human-readable）
・`du -sh var/*` … 直下の各項目のサイズ。大きいものを順に掘り下げていく
・`du -ah var | sort -h | tail` … 全ファイルをサイズ順に並べて最後（=最大）を表示（`sort -h` は 1K/2M/3G を正しく比較）
・`core.*.dump` はプロセスがクラッシュしたときのメモリダンプで、巨大になりがちな「容量食い」の常連です
`./deploy.sh` が `Permission denied` になるのは実行権限(x)が無いため。`bash deploy.sh` なら権限なしでも動きますが、
正しくは `chmod +x` で権限を付けます。起動は `&` でバックグラウンドへ。
""",
    tip="""
`df -h` で「どのディスクが一杯か」→ `du -sh /* 2>/dev/null | sort -h` で「どこが大きいか」→ 掘り下げ、が定番の調査手順。
⚠ 実行中のプロセスが掴んだまま削除したファイルは、**プロセスが終わるまで容量が解放されません**。
`lsof +L1` で「削除済みだが開かれているファイル」を探し、プロセスを再起動しましょう。
ncdu（要インストール）を使えば、対話的にディスク使用量を掘り下げられて便利です。
""",
    setup=s38, check=c38,
    solution="rm var/cache/app/tmp/core.20251118.dump\nchmod +x deploy.sh\n./deploy.sh &\nsleep 0.5",
    wrong=["chmod +x deploy.sh\n./deploy.sh &\nsleep 0.5",
           "rm -rf var/cache var/lib\nchmod +x deploy.sh\n./deploy.sh &\nsleep 0.5",
           "rm var/cache/app/tmp/core.20251118.dump\nbash deploy.sh &\nsleep 0.5"],
)
