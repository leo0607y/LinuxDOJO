"""応用練習モード。コマンドを「組み合わせて」目的の結果を作る練習。

基礎練習の次、実践（本物の bash）の前の段階。すべて engine.guided の模擬端末で動き、
実際の PC のファイル・プロセス・環境変数は読まず、変更もしない。
IP アドレスは説明用に予約された範囲（RFC 5737）の値を使う。
"""
from curriculum.lesson_kit import LS_VIEW, absent, all_of, content, editor, editor_closed, is_file, lesson

_ACCESS = [
    "192.0.2.10 GET /index.html 200",
    "198.51.100.7 GET /login 404",
    "192.0.2.10 GET /about 200",
    "203.0.113.5 GET /admin 403",
    "198.51.100.7 GET /login 404",
    "192.0.2.10 GET /contact 500",
    "203.0.113.5 GET /index.html 200",
    "198.51.100.7 GET /wp-login.php 404",
    "192.0.2.10 GET /index.html 200",
    "192.0.2.99 GET /index.html 200",
]
ACCESS_LOG = "\n".join(_ACCESS) + "\n"
TOP3 = "      4 192.0.2.10\n      3 198.51.100.7\n      2 203.0.113.5\n"
NAMES = "sato\nsuzuki\nsato\ntanaka\nsuzuki\nsato\n"
USERS_CSV = "1,sato,dev\n2,suzuki,ops\n3,tanaka,dev\n4,ito,sales\n"
APP_LOG = ("INFO 起動しました\nerror 小文字で書かれたエラー\nERROR データベースに接続できません\n"
           "WARN 再試行します\nERROR タイムアウトしました\nINFO 終了しました\n")
WEB_LOG = "INFO リクエストを受け付けました\nERROR 画像が見つかりません\n"
APP_CONF = "# アプリの設定\nport=8080\n\n# ログの細かさ\nlog_level=debug\nhost=0.0.0.0\n"
CLEAN_CONF = "port=8080\nlog_level=debug\nhost=0.0.0.0\n"
FIXED_CONF = APP_CONF.replace("port=8080", "port=80").replace("log_level=debug", "log_level=info")
_RUNAWAY = {"pid": 4321, "user": "learner", "cmd": "python3 runaway.py", "cpu": 99.0, "mem": 12.5,
            "ignores_term": True}
_OLD_LOGS = {"logs/old-2024-01.log": "古いログ\n" * 1500, "logs/old-2024-02.log": "古いログ\n" * 1500,
             "logs/current.log": "今のログ\n"}


def _env_is(name, value):
    return lambda t: t.progress["env"].get(name) == value


def _no_process(pid):
    return lambda t: all(p["pid"] != pid for p in t.progress["processes"])


def _conf_line(text):
    return editor(lambda e: text in e["lines"])


_WILD = "ワイルドカードでまとめて扱う"
_PIPE = "パイプでつないで集計する"
_GREP = "grep を使いこなす"
_ENV = "環境変数を読む・設定する"
_PROC = "プロセスを調べて止める"
_DISK = "容量を調べて空ける"
_VIM = "vim で設定ファイルを直す"

ADVANCED = [
    # ---------------------------------------------------------------- ワイルドカード
    lesson("adv-01", "* で名前をまとめて指定する",
           "* （アスタリスク）は「どんな文字が何文字でも」を表す記号で、ワイルドカードと呼びます。\n"
           "*.log と書くと「.log で終わるすべての名前」になります。シェルが一致する名前に置き換えてからコマンドを動かします。",
           ".log で終わるファイルだけを一覧に表示しましょう。", "ls *.log",
           "app.log と error.log だけが表示されました。notes.txt は対象外です。",
           unit=_WILD, files={"app.log": "app\n", "error.log": "error\n", "notes.txt": "メモ\n"}, accept=["ls *log"]),
    lesson("adv-02", "まとめて行数を数える",
           "ワイルドカードは、ファイル名を受け取るほとんどのコマンドで使えます。\n"
           "wc -l に複数のファイルを渡すと、ファイルごとの行数と合計（total）を表示します。",
           ".log で終わるファイルの行数をまとめて数えましょう。", "wc -l *.log",
           "ファイルごとの行数と合計が出ました。1つずつ調べる手間が省けます。",
           unit=_WILD, files={"app.log": APP_LOG, "error.log": "ERROR 1\nERROR 2\n"}, accept=["wc -l app.log error.log"]),
    lesson("adv-03", "まとめてコピーする",
           "cp の最後にフォルダを書くと、その前に並べたファイルをすべてそのフォルダへコピーします。\n"
           "*.log と組み合わせれば、ログを一度にバックアップできます。",
           ".log で終わるファイルを、すべて backup フォルダへコピーしましょう。", "cp *.log backup",
           "まとめてコピーできました。元のファイルも残っています。",
           unit=_WILD, files={"app.log": "app\n", "error.log": "error\n", "notes.txt": "メモ\n"}, dirs=["backup"],
           remove=["backup/app.log", "backup/error.log"], accept=["cp *.log backup/", "cp app.log error.log backup"],
           goal=all_of(is_file("backup/app.log"), is_file("backup/error.log"), is_file("app.log"), absent("backup/notes.txt"))),
    lesson("adv-04", "不要なファイルをまとめて消す",
           "ワイルドカードで消すときは、まず ls *.tmp で対象を確かめてから rm するのが安全です。\n"
           "今回の対象は cache1.tmp と cache2.tmp です。notes.txt は残します。",
           ".tmp で終わるファイルだけを削除しましょう。", "rm *.tmp",
           "一時ファイルだけを消せました。本物でも「確かめてから消す」を習慣にしましょう。",
           unit=_WILD, files={"cache1.tmp": "x\n", "cache2.tmp": "y\n", "notes.txt": "メモ\n"},
           accept=["rm cache1.tmp cache2.tmp"], goal=all_of(absent("cache1.tmp"), absent("cache2.tmp"), is_file("notes.txt"))),
    lesson("adv-05", "1文字だけのワイルドカード",
           "? は「ちょうど1文字」を表します。?.txt は a.txt や b.txt には一致し、ab.txt には一致しません。\n"
           "* より細かく条件を指定したいときに使います。",
           "名前が1文字の .txt ファイルだけを一覧にしましょう。", "ls ?.txt",
           "a.txt と b.txt だけが表示されました。* と ? を使い分けられます。",
           unit=_WILD, files={"a.txt": "a\n", "b.txt": "b\n", "ab.txt": "ab\n"}),
    # ---------------------------------------------------------------- パイプ
    lesson("adv-06", "パイプで結果を次へ渡す",
           "| （パイプ）は、左のコマンドの出力を、右のコマンドの入力として渡します。\n"
           "cat access.log | head -n 3 は「ログ全体を出す → その先頭3行だけにする」という意味です。\n"
           "小さな道具をつないで目的の結果を作るのが、Linux の得意技です。",
           "access.log の内容をパイプで head に渡し、先頭3行を表示しましょう。", "cat access.log | head -n 3",
           "先頭3行だけになりました。head -n 3 access.log と書いても同じ結果です。",
           unit=_PIPE, files={"access.log": ACCESS_LOG}, accept=["head -n 3 access.log", "head -3 access.log", "cat access.log | head -3"]),
    lesson("adv-07", "見つけた行を数える",
           "grep で見つけた行を wc -l に渡すと、件数が分かります。\n"
           "access.log の各行の最後は、結果を表す番号です。404 は「ページが見つからない」という意味です。",
           "404 を含む行が何行あるか数えましょう。", "grep 404 access.log | wc -l",
           "3件ありました。grep -c 404 access.log でも同じ件数を数えられます。",
           unit=_PIPE, files={"access.log": ACCESS_LOG},
           accept=["grep -c 404 access.log", "cat access.log | grep 404 | wc -l", "cat access.log | grep -c 404"]),
    lesson("adv-08", "並べ替える",
           "sort は行を並べ替えます。文字の順（辞書の順）に並びます。\n"
           "names.txt には、受付に来た人の名前が来た順に書かれています。",
           "names.txt を並べ替えて表示しましょう。", "sort names.txt",
           "同じ名前が隣どうしに集まりました。これが次の uniq で効いてきます。",
           unit=_PIPE, files={"names.txt": NAMES}, accept=["cat names.txt | sort"]),
    lesson("adv-09", "重複をまとめる",
           "uniq は「隣どうしで同じ行」を1つにまとめます。離れた重複はまとめないので、先に sort で並べます。\n"
           "sort と uniq をパイプでつなぐのが定番の組み合わせです。sort -u でも同じ結果になります。",
           "names.txt から重複をなくした名前の一覧を表示しましょう。", "sort names.txt | uniq",
           "3人の名前が1回ずつになりました。",
           unit=_PIPE, files={"names.txt": NAMES},
           accept=["sort -u names.txt", "cat names.txt | sort | uniq", "cat names.txt | sort -u"]),
    lesson("adv-10", "回数を数える",
           "uniq -c は、まとめた行が何回出てきたかを左に表示します。\n"
           "「誰が何回来たか」「どのエラーが何回出たか」を数える基本の形です。",
           "names.txt の名前ごとの回数を表示しましょう。", "sort names.txt | uniq -c",
           "sato が3回、suzuki が2回、tanaka が1回と分かりました。",
           unit=_PIPE, files={"names.txt": NAMES}, accept=["cat names.txt | sort | uniq -c"]),
    lesson("adv-11", "多い順に並べる",
           "sort -n は数値として並べ、-r は逆順（大きい順）にします。-rn とまとめても書けます。\n"
           "uniq -c の結果をもう一度 sort -rn に渡すと、多い順のランキングになります。",
           "名前の回数を、多い順に並べましょう。", "sort names.txt | uniq -c | sort -rn",
           "回数の多い順に並びました。3つのコマンドをつないだランキングの完成です。",
           unit=_PIPE, files={"names.txt": NAMES},
           accept=["sort names.txt | uniq -c | sort -nr", "sort names.txt | uniq -c | sort -r -n",
                   "cat names.txt | sort | uniq -c | sort -rn"]),
    lesson("adv-12", "列を取り出す",
           "cut は行の一部分を切り出します。-d で区切り文字、-f で何番目の列かを指定します。\n"
           "users.csv は「番号,名前,部署」がカンマで区切られた CSV です。",
           "users.csv の2列目（名前）だけを表示しましょう。", "cut -d , -f 2 users.csv",
           "名前の列だけが取り出せました。-d, -f2 のように詰めて書いても同じです。",
           unit=_PIPE, files={"users.csv": USERS_CSV},
           accept=["cut -d, -f2 users.csv", "cut -d , -f2 users.csv", "cut -f 2 -d , users.csv", "cat users.csv | cut -d , -f 2"]),
    lesson("adv-13", "部署の一覧を作る",
           "cut で取り出した列を sort -u に渡すと、重複のない一覧になります。\n"
           "部署は3列目です。",
           "users.csv にある部署の一覧を、重複なしで表示しましょう。", "cut -d , -f 3 users.csv | sort -u",
           "dev・ops・sales の3つだと分かりました。",
           unit=_PIPE, files={"users.csv": USERS_CSV},
           accept=["cut -d , -f 3 users.csv | sort | uniq", "cut -d, -f3 users.csv | sort -u", "cut -d, -f3 users.csv | sort | uniq"]),
    lesson("adv-14", "アクセスの多い相手を調べる",
           "実際のサーバー運用でよく使う形です。access.log の1列目は、アクセスしてきた相手の IP アドレスです。\n"
           "スペースで区切られているので -d \" \" を使います。cut → sort → uniq -c → sort -rn とつなぎます。",
           "IP アドレスごとのアクセス回数を、多い順に表示しましょう。",
           "cut -d \" \" -f 1 access.log | sort | uniq -c | sort -rn",
           "192.0.2.10 が一番多いと分かりました。4つの道具をつなぐと、こんな調査もできます。",
           unit=_PIPE, files={"access.log": ACCESS_LOG},
           accept=["cut -d ' ' -f 1 access.log | sort | uniq -c | sort -rn", "cut -d \" \" -f 1 access.log | sort | uniq -c | sort -nr",
                   "cut -d ' ' -f1 access.log | sort | uniq -c | sort -rn"]),
    lesson("adv-15", "上位3件を報告ファイルに残す",
           "パイプの一番最後に > ファイル名 を付けると、最終結果を保存できます。\n"
           "前の課題のランキングに head -n 3 をつなぎ、top.txt に保存しましょう。\n"
           "書き方は自由です。top.txt の中身が上位3件のランキングになっていれば正解です。",
           "アクセス数の上位3件を top.txt に保存しましょう。",
           "cut -d \" \" -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 > top.txt",
           "報告ファイルができました。調べた結果を残せると、他の人に引き継げます。",
           unit=_PIPE, files={"access.log": ACCESS_LOG}, remove=["top.txt"], goal=content("top.txt", TOP3)),
    lesson("adv-16", "報告ファイルを確かめる",
           "保存したら、中身を表示して確かめます。",
           "top.txt の中身を表示しましょう。", "cat top.txt",
           "上位3件が残っていました。作る → 確かめる の流れです。",
           unit=_PIPE, initial_files={"top.txt": TOP3}),
    # ---------------------------------------------------------------- grep
    lesson("adv-17", "大文字と小文字を区別せず探す",
           "grep は大文字と小文字を区別します。-i を付けると区別せずに探します。\n"
           "app.log には ERROR と小文字の error が混ざっています。",
           "app.log から error を、大文字小文字を区別せずに探しましょう。", "grep -i error app.log",
           "小文字の error も大文字の ERROR も見つかりました。",
           unit=_GREP, files={"app.log": APP_LOG}, accept=["grep -i ERROR app.log", "cat app.log | grep -i error"]),
    lesson("adv-18", "見つけた行の番号も出す",
           "-n を付けると、見つけた行が何行目かを左に表示します。vim で直す場所を探すときにも便利です。",
           "app.log の ERROR を、行番号付きで表示しましょう。", "grep -n ERROR app.log",
           "3行目と5行目だと分かりました。",
           unit=_GREP, files={"app.log": APP_LOG}),
    lesson("adv-19", "一致しない行を表示する",
           "-v は「一致しない行」を表示します。見たくない行を取り除くときに使います。",
           "app.log から INFO の行を除いて表示しましょう。", "grep -v INFO app.log",
           "INFO 以外の、気にするべき行だけが残りました。",
           unit=_GREP, files={"app.log": APP_LOG}, accept=["cat app.log | grep -v INFO"]),
    lesson("adv-20", "行の先頭で探す",
           "grep の探す文字には「正規表現」という書き方を使えます。^ は行の先頭を表します。\n"
           "\"^#\" は「# で始まる行」、つまり設定ファイルのコメント行です。-v と組み合わせるとコメントを除けます。\n"
           "記号を含むときは \" \" か ' ' で囲むと安全です。",
           "app.conf からコメント行（# で始まる行）を除いて表示しましょう。", "grep -v \"^#\" app.conf",
           "コメントが消えて、設定だけが見えました。まだ空行が残っています。",
           unit=_GREP, files={"app.conf": APP_CONF}, accept=["grep -v '^#' app.conf", "grep -v ^# app.conf", "cat app.conf | grep -v \"^#\""]),
    lesson("adv-21", "空行も除いて保存する",
           "^$ は「行の先頭のすぐ後が行の終わり」、つまり空行です。\n"
           "コメントを除いた結果をもう一度 grep -v に渡して空行も除き、clean.conf に保存しましょう。\n"
           "やり方は自由です。clean.conf が設定の3行だけになっていれば正解です。",
           "コメントと空行を除いた設定を clean.conf に保存しましょう。",
           "grep -v \"^#\" app.conf | grep -v \"^$\" > clean.conf",
           "設定だけの読みやすいファイルができました。長い設定ファイルを読むときの定番です。",
           unit=_GREP, files={"app.conf": APP_CONF}, remove=["clean.conf"], goal=content("clean.conf", CLEAN_CONF)),
    lesson("adv-22", "複数のファイルから探す",
           "grep にもワイルドカードで複数のファイルを渡せます。どのファイルの行かが左に表示されます。",
           ".log で終わるすべてのファイルから ERROR を探しましょう。", "grep ERROR *.log",
           "ファイル名付きで見つかりました。どのログで起きたかがすぐ分かります。",
           unit=_GREP, files={"app.log": APP_LOG, "web.log": WEB_LOG}, accept=["grep ERROR app.log web.log"]),
    # ---------------------------------------------------------------- 環境変数
    lesson("adv-23", "変数の値を読む",
           "シェルは、名前の付いた値（変数）を覚えています。$ の後ろに名前を書くと、その値に置き換わります。\n"
           "HOME は自分のホームフォルダの場所を表す変数です。",
           "HOME の値を表示しましょう。", "echo $HOME",
           "/home/learner と表示されました。cd だけでここへ戻れるのは、この値のおかげです。",
           unit=_ENV, accept=["printenv HOME", "echo \"$HOME\"", "echo ${HOME}"]),
    lesson("adv-24", "コマンドを探す場所を知る",
           "PATH は、コマンドの本体を探すフォルダの一覧です。: で区切って並んでいます。\n"
           "ls と打つだけで動くのは、この一覧のどこかに ls があるからです。「command not found」は、ここに見つからないという意味です。",
           "PATH の値を表示しましょう。", "echo $PATH",
           "コマンドを探す場所の一覧が見えました。",
           unit=_ENV, accept=["printenv PATH", "echo \"$PATH\""]),
    lesson("adv-25", "環境変数を設定する",
           "export 名前=値 で、環境変数を設定します。= の前後にスペースを入れないのがルールです。\n"
           "環境変数は、そのシェルから起動するプログラムにも引き継がれます。アプリの設定を渡すときによく使います。",
           "GREETING という環境変数に hello を設定しましょう。", "export GREETING=hello",
           "設定できました。何も表示されないのは成功の印です。",
           unit=_ENV, accept=["export GREETING='hello'", "export GREETING=\"hello\""], goal=_env_is("GREETING", "hello")),
    lesson("adv-26", "設定した値を使う",
           "設定した変数も $ で読み出せます。\" \" の中でも置き換わりますが、' ' の中では置き換わりません。",
           "GREETING の値を表示しましょう。", "echo $GREETING",
           "hello と表示されました。",
           unit=_ENV, env={"GREETING": "hello"}, accept=["printenv GREETING", "echo \"$GREETING\"", "echo ${GREETING}"]),
    lesson("adv-27", "環境変数の一覧から探す",
           "env は環境変数の一覧を表示します。数が多いので grep に渡して探します。",
           "環境変数の一覧から GREETING を探しましょう。", "env | grep GREETING",
           "GREETING=hello が見つかりました。",
           unit=_ENV, env={"GREETING": "hello"}, accept=["printenv | grep GREETING", "env | grep GREET"]),
    lesson("adv-28", "変数を消す",
           "unset 名前 で変数を消します。いらなくなった設定を残さないようにしましょう。",
           "GREETING を消しましょう。", "unset GREETING",
           "消せました。echo $GREETING を実行すると、空の行になります。",
           unit=_ENV, env={"GREETING": "hello"}, goal=lambda t: "GREETING" not in t.progress["env"]),
    # ---------------------------------------------------------------- プロセス
    lesson("adv-29", "自分の端末で動いているもの",
           "動いているプログラムを「プロセス」と呼びます。ps は、今の端末で動いているプロセスを表示します。\n"
           "PID はプロセスにつけられた番号です。止めるときにこの番号を使います。",
           "今の端末のプロセスを表示しましょう。", "ps",
           "bash（今使っているシェル）と、ps 自身が見えました。",
           unit=_PROC, processes=[_RUNAWAY]),
    lesson("adv-30", "すべてのプロセスを見る",
           "ps aux は、ほかのユーザーのものも含めたすべてのプロセスを表示します。\n"
           "%CPU は CPU をどれだけ使っているかです。サーバーが重いときは、ここが大きいものを探します。",
           "すべてのプロセスを表示しましょう。", "ps aux",
           "CPU を 99% 使っている python3 runaway.py が見つかりました。これが重さの原因のようです。",
           unit=_PROC, processes=[_RUNAWAY], accept=["ps -ef", "ps ax", "ps -e"]),
    lesson("adv-31", "目的のプロセスだけ探す",
           "ps aux の結果を grep に渡すと、名前で絞り込めます。pgrep 名前 は番号（PID）だけを表示します。",
           "runaway という名前を含むプロセスを探しましょう。", "ps aux | grep runaway",
           "PID が 4321 だと分かりました。",
           unit=_PROC, processes=[_RUNAWAY], accept=["pgrep runaway", "ps -ef | grep runaway", "ps aux | grep runaway.py"]),
    lesson("adv-32", "終了をお願いする",
           "kill PID は、プロセスに「終了してください」という合図（TERM シグナル）を送ります。\n"
           "プログラムは後片付けをしてから終了できます。まずはこの穏やかな方法を使います。",
           "PID 4321 に終了の合図を送りましょう。", "kill 4321",
           "合図は送れました。でも、本当に止まったかは確かめないと分かりません。",
           unit=_PROC, processes=[_RUNAWAY], accept=["kill -15 4321", "kill -TERM 4321", "kill -s TERM 4321"]),
    lesson("adv-33", "止まったか確かめる",
           "kill は合図を送るだけです。プログラムによっては合図を無視することがあります。\n"
           "もう一度 ps で確かめましょう。",
           "runaway がまだ動いているか確かめましょう。", "ps aux | grep runaway",
           "まだ動いています！ この プログラムは終了の合図を無視していました。",
           unit=_PROC, processes=[_RUNAWAY], accept=["pgrep runaway", "ps -ef | grep runaway", "ps aux | grep runaway.py"]),
    lesson("adv-34", "強制的に止める",
           "kill -9 PID は、プログラムに後片付けをさせずに強制終了させます（KILL シグナル）。\n"
           "データが壊れる可能性があるので最後の手段です。TERM で止まらないときだけ使います。",
           "PID 4321 を強制終了しましょう。", "kill -9 4321",
           "止まりました。まず TERM、だめなら -9 という順番を覚えておきましょう。",
           unit=_PROC, processes=[_RUNAWAY], accept=["kill -KILL 4321", "kill -s KILL 4321"], goal=_no_process(4321)),
    lesson("adv-35", "ほかの人のプロセスは止められない",
           "PID 845 は cron という、決まった時刻に仕事を動かすシステムのプロセスです。持ち主は root（管理者）です。\n"
           "一般ユーザーは、ほかのユーザーのプロセスを止められません。表示を読んでみましょう。\n"
           "sudo を付ければ止められますが、何のプロセスか分からないまま止めてはいけません。",
           "PID 845 の終了を試して、表示を読みましょう。", "kill 845",
           "Operation not permitted と断られました。権限の仕組みがシステムを守っています。",
           unit=_PROC, expected_code=1),
    # ---------------------------------------------------------------- 容量
    lesson("adv-36", "ディスクの空きを調べる",
           "df -h は、ディスク全体の大きさ・使用量・空きを表示します。-h は G や M など読みやすい単位にする指定です。\n"
           "Use% が 90% を超えると、ログが書けなくなるなどの障害が起きやすくなります。",
           "ディスクの使用状況を表示しましょう。", "df -h",
           "/ が 90% 使われていました。何が容量を使っているか調べましょう。",
           unit=_DISK),
    lesson("adv-37", "フォルダの大きさを調べる",
           "du -sh フォルダ は、そのフォルダの中身の合計サイズを表示します（-s は合計だけ、-h は読みやすい単位）。",
           "logs フォルダの大きさを調べましょう。", "du -sh logs",
           "logs フォルダが大きいと分かりました。中身は古いログがほとんどです。",
           unit=_DISK, files=_OLD_LOGS, accept=["du -sh logs/", "du -hs logs", "du -s -h logs"]),
    lesson("adv-38", "古いログだけをまとめて消す",
           "古いログは old- で始まる名前です。今使っている current.log は消してはいけません。\n"
           "ワイルドカードで古いものだけを指定しましょう。消す前に ls で対象を確かめるとさらに安全です。",
           "logs フォルダの old- で始まるログだけを削除しましょう。", "rm logs/old-*.log",
           "古いログだけ消せました。current.log は残っています。",
           unit=_DISK, files=_OLD_LOGS, accept=["rm logs/old-2024-01.log logs/old-2024-02.log", "rm logs/old-*"],
           goal=all_of(absent("logs/old-2024-01.log"), absent("logs/old-2024-02.log"), is_file("logs/current.log"))),
    lesson("adv-39", "残ったファイルを確かめる",
           "片付けた後は、必要なものが残っているか確かめます。",
           "logs フォルダの中を一覧にしましょう。", "ls logs",
           "current.log だけが残っていました。",
           unit=_DISK, initial_files={"logs/current.log": "今のログ\n"},
           accept=["ls logs/"] + [x.replace(" .", "") + " logs" for x in LS_VIEW if x != "ls ."]),
    # ---------------------------------------------------------------- vim 応用
    lesson("adv-40", "直す前にコピーを取る",
           "設定ファイルを直す前には、元に戻せるようコピーを取っておきます。.bak という名前がよく使われます。",
           "app.conf を app.conf.bak という名前でコピーしましょう。", "cp app.conf app.conf.bak",
           "退避できました。失敗しても元に戻せます。",
           unit=_VIM, files={"app.conf": APP_CONF}, remove=["app.conf.bak"], packages=["vim"],
           goal=content("app.conf.bak", APP_CONF)),
    lesson("adv-41", "設定ファイルを開く",
           "ポート番号を 8080 から 80 に、ログの細かさを debug から info に直します。\n"
           "まずは vim で app.conf を開きましょう。",
           "vim で app.conf を開きましょう。", "vim app.conf",
           "開けました。今はノーマルモードです。",
           unit=_VIM, files={"app.conf": APP_CONF}, packages=["vim"], accept=["vi app.conf"],
           goal=editor(lambda e: e["key"] == "app.conf")),
    lesson("adv-42", "直す場所へ一気に移動する",
           "/ の後ろに文字を書くと、その文字のある行へ移動します。長い設定ファイルでも迷いません。",
           "port と書かれた行へ移動しましょう。", "/port",
           "port=8080 の行に移動しました。",
           unit=_VIM, files={"app.conf": APP_CONF}, packages=["vim"], accept=["/port=", "/8080"],
           editor={"file": "app.conf", "continue": True}, goal=editor(lambda e: "port" in e["lines"][e["cursor"]])),
    lesson("adv-43", "今の行の文字を置き換える",
           ":s/前/後/ は、カーソルのある行の文字を置き換えます。\n"
           "s は substitute（置き換える）の s です。/ で区切って、前の文字と後の文字を書きます。",
           "今の行の 8080 を 80 に置き換えましょう。", ":s/8080/80/",
           "port=80 になりました。",
           unit=_VIM, files={"app.conf": APP_CONF}, packages=["vim"],
           accept=[":%s/8080/80/", ":%s/8080/80/g", ":s/8080/80/g"],
           editor={"file": "app.conf", "cursor": 1, "continue": True}, goal=_conf_line("port=80")),
    lesson("adv-44", "ファイル全体で置き換える",
           ":%s/前/後/g の % は「ファイル全体」、最後の g は「行の中で見つかったものすべて」という意味です。\n"
           "どこにあるか分からなくても、まとめて置き換えられます。",
           "ファイル全体の debug を info に置き換えましょう。", ":%s/debug/info/g",
           "log_level=info になりました。",
           unit=_VIM, files={"app.conf": APP_CONF}, packages=["vim"], accept=[":%s/debug/info/"],
           editor={"file": "app.conf", "lines": APP_CONF.replace("port=8080", "port=80").splitlines(),
                   "cursor": 1, "modified": True, "continue": True},
           goal=_conf_line("log_level=info")),
    lesson("adv-45", "保存して閉じる",
           "2か所を直したので、保存して終了します。",
           "保存して vim を終了しましょう。", ":wq",
           "保存できました。",
           unit=_VIM, files={"app.conf": APP_CONF}, packages=["vim"], accept=[":x", "ZZ"],
           editor={"file": "app.conf", "lines": FIXED_CONF.splitlines(), "modified": True, "continue": True},
           goal=all_of(editor_closed, lambda t: "port=80" in t.path("app.conf").read_text(encoding="utf-8").splitlines()
                       and "log_level=info" in t.path("app.conf").read_text(encoding="utf-8"))),
    lesson("adv-46", "直した設定を確かめる",
           "最後に、コメントを除いた設定を表示して、直したい値になっているか確かめます。\n"
           "ここまでの組み合わせで、ログの調査・片付け・設定の修正までできるようになりました！\n"
           "次は総合復習の「課題まつり」で、手本なしの力試しをしてみましょう。",
           "app.conf からコメント行を除いて表示しましょう。", "grep -v \"^#\" app.conf",
           "port=80 と log_level=info になっていました。応用練習モード、修了です！",
           unit=_VIM, initial_files={"app.conf": FIXED_CONF},
           accept=["grep -v '^#' app.conf", "cat app.conf", "grep -v ^# app.conf"]),
]

for step in ADVANCED:
    step.setdefault("cwd", ".")
    step.setdefault("remote", False)
    step.setdefault("ssh_known", False)
    step.setdefault("ssh_pending", False)
