"""課題まつり：ログ解析とテキスト集計（grep / sort / uniq / cut / wc / head / tail とリダイレクト）。

ログや CSV はすべて教材用の架空データ。IP アドレスは文書用の範囲（192.0.2.0/24 など）だけを使う。
"""

PACK_TITLE = "ログ解析とテキスト集計"


def _req(ip, day, time, method, path, status, size):
    return f'{ip} - - [{day}/Nov/2026:{time} +0900] "{method} {path} HTTP/1.1" {status} {size}\n'


# Web サーバーのアクセスログ（11/21 の分）。空白区切りで 1列目=IP、7列目=パス、9列目=ステータス。
ACCESS = "".join([
    _req("203.0.113.7", 21, "09:58:12", "GET", "/", 200, 5120),
    _req("198.51.100.23", 21, "09:59:40", "GET", "/login", 200, 2048),
    _req("203.0.113.7", 21, "10:01:05", "GET", "/api/items", 200, 8404),
    _req("192.0.2.44", 21, "10:02:30", "GET", "/old-page", 404, 312),
    _req("198.51.100.23", 21, "10:05:11", "POST", "/api/order", 500, 128),
    _req("203.0.113.7", 21, "10:07:45", "GET", "/docs/404-guide", 200, 4404),
    _req("192.0.2.44", 21, "10:10:02", "GET", "/favicon.ico", 404, 312),
    _req("203.0.113.50", 21, "10:12:19", "GET", "/api/items", 200, 8404),
    _req("203.0.113.7", 21, "10:15:33", "GET", "/api/cart", 502, 256),
    _req("198.51.100.23", 21, "10:20:00", "GET", "/static/app.js", 200, 40400),
    _req("203.0.113.50", 21, "11:01:10", "GET", "/login", 200, 2048),
    _req("192.0.2.44", 21, "11:03:27", "GET", "/wp-admin", 404, 312),
    _req("203.0.113.7", 21, "11:05:50", "GET", "/api/order", 503, 128),
    _req("198.51.100.23", 21, "11:10:41", "GET", "/", 200, 5120),
    _req("203.0.113.7", 21, "11:20:15", "GET", "/api/items", 200, 8404),
    _req("203.0.113.50", 21, "11:30:03", "POST", "/api/order", 500, 128),
    _req("192.0.2.44", 21, "11:45:59", "GET", "/search", 200, 3072),
    _req("203.0.113.7", 21, "12:00:01", "GET", "/", 200, 5120),
    _req("198.51.100.23", 21, "12:10:22", "GET", "/api/cart", 200, 1024),
    _req("203.0.113.7", 21, "12:30:45", "GET", "/api/items", 304, 0),
])

# ローテーションされた前日分（11/20）。
ACCESS_OLD = "".join([
    _req("198.51.100.23", 20, "09:10:00", "GET", "/", 200, 5120),
    _req("203.0.113.7", 20, "10:00:05", "GET", "/api/items", 200, 8404),
    _req("203.0.113.7", 20, "10:20:10", "GET", "/api/order", 500, 128),
    _req("192.0.2.44", 20, "10:40:00", "GET", "/login", 200, 2048),
    _req("198.51.100.9", 20, "11:00:30", "GET", "/api/cart", 200, 1024),
    _req("203.0.113.50", 20, "11:15:00", "GET", "/api/order", 503, 128),
    _req("203.0.113.7", 20, "11:50:00", "GET", "/", 200, 5120),
    _req("198.51.100.23", 20, "12:05:00", "GET", "/search", 200, 3072),
    _req("203.0.113.7", 20, "12:15:00", "GET", "/api/items", 502, 256),
])

APP = (
    "2026-11-21 09:00:00 INFO server started\n"
    "2026-11-21 09:05:12 WARN disk usage 81%\n"
    "2026-11-21 09:10:40 ERROR db connection timeout\n"
    "2026-11-21 09:15:03 INFO user=alice login\n"
    "2026-11-21 09:20:31 warn slow response 2.3s\n"
    "2026-11-21 09:25:00 INFO retry finished without error\n"
    "2026-11-21 09:30:18 ERROR payment api returned 502\n"
    "2026-11-21 09:41:07 Warning cache size near limit\n"
    "2026-11-21 09:50:55 INFO user=bob login\n"
    "2026-11-21 10:02:14 ERROR db connection timeout\n"
    "2026-11-21 10:10:00 INFO request timeout recovered\n"
    "2026-11-21 10:15:42 INFO user=alice logout\n"
)
_APP_LINES = APP.splitlines(keepends=True)

APP_HOURS = (
    "2026-11-21 09:55:01 ERROR cache miss storm\n"
    "2026-11-21 10:00:12 INFO batch start\n"
    "2026-11-21 10:03:44 ERROR db connection timeout\n"
    "2026-11-21 10:30:00 WARN queue length 120\n"
    "2026-11-21 11:12:09 ERROR payment api returned 502\n"
    "2026-11-21 11:40:00 INFO retry ok after 10 seconds\n"
    "2026-11-21 11:59:59 ERROR db deadlock detected\n"
    "2026-11-21 12:00:03 ERROR session store unavailable\n"
    "2026-11-21 12:40:10 INFO batch end\n"
)

AUTH = (
    "Nov 21 09:00:01 web01 sshd[1001]: Accepted password for alice from 192.0.2.10 port 50001 ssh2\n"
    "Nov 21 09:01:12 web01 sshd[1002]: Failed password for root from 203.0.113.66 port 50122 ssh2\n"
    "Nov 21 09:01:15 web01 sshd[1003]: Failed password for root from 203.0.113.66 port 50123 ssh2\n"
    "Nov 21 09:02:40 web01 sshd[1004]: Failed password for admin from 198.51.100.77 port 50300 ssh2\n"
    "Nov 21 09:03:05 web01 sshd[1005]: Failed password for root from 203.0.113.66 port 50124 ssh2\n"
    "Nov 21 09:05:00 web01 sshd[1006]: Accepted password for bob from 192.0.2.11 port 50400 ssh2\n"
    "Nov 21 09:06:31 web01 sshd[1007]: Failed password for alice from 192.0.2.10 port 50002 ssh2\n"
    "Nov 21 09:07:45 web01 sshd[1008]: Failed password for admin from 198.51.100.77 port 50301 ssh2\n"
    "Nov 21 09:08:10 web01 CRON[1009]: session opened for user root\n"
)

AUTH_1 = (
    "Nov 20 22:10:01 web01 sshd[901]: Failed password for root from 203.0.113.66 port 40001 ssh2\n"
    "Nov 20 22:10:04 web01 sshd[902]: Failed password for root from 203.0.113.66 port 40002 ssh2\n"
    "Nov 20 22:30:00 web01 sshd[903]: Accepted password for alice from 192.0.2.10 port 40100 ssh2\n"
    "Nov 20 23:00:12 web01 sshd[904]: Failed password for guest from 192.0.2.100 port 40200 ssh2\n"
    "Nov 20 23:00:15 web01 sshd[905]: Failed password for guest from 192.0.2.100 port 40201 ssh2\n"
)
AUTH_2 = (
    "Nov 21 08:59:50 web01 sshd[1001]: Failed password for alice from 192.0.2.10 port 50001 ssh2\n"
    "Nov 21 09:00:01 web01 sshd[1002]: Accepted password for alice from 192.0.2.10 port 50002 ssh2\n"
    "Nov 21 09:01:12 web01 sshd[1003]: Failed password for root from 203.0.113.66 port 50122 ssh2\n"
    "Nov 21 09:02:40 web01 sshd[1004]: Failed password for admin from 198.51.100.77 port 50300 ssh2\n"
    "Nov 21 09:03:05 web01 sshd[1005]: Failed password for root from 203.0.113.66 port 50124 ssh2\n"
    "Nov 21 09:04:00 web01 sshd[1006]: Failed password for guest from 192.0.2.100 port 50201 ssh2\n"
    "Nov 21 09:05:10 web01 sshd[1007]: Failed password for alice from 192.0.2.10 port 50003 ssh2\n"
)

USERS_CSV = (
    "id,name,email,department\n"
    "1,sato,sato@example.com,sales\n"
    "2,suzuki,suzuki@example.com,dev\n"
    "3,takahashi,takahashi@example.com,presales\n"
    "4,tanaka,tanaka@example.com,sales\n"
    "5,ito,ito@example.com,support\n"
    "6,watanabe,sales-desk@example.com,dev\n"
)

SALES_CSV = (
    "date,store,item,qty\n"
    "2026-11-21,shibuya,coffee,2\n"
    "2026-11-21,ueno,tea,1\n"
    "2026-11-21,shibuya,cake,1\n"
    "2026-11-21,ikebukuro,coffee,3\n"
    "2026-11-21,shibuya,coffee,1\n"
    "2026-11-21,ueno,coffee,2\n"
    "2026-11-21,shibuya,tea,1\n"
    "2026-11-21,ikebukuro,cake,2\n"
    "2026-11-21,ueno,cake,1\n"
)

_SALES_HEAD = "date,store,item,qty\n"
_SALES_IKEBUKURO = "2026-11-22,ikebukuro,coffee,3\n2026-11-22,ikebukuro,sandwich,1\n"
_SALES_SHIBUYA = ("2026-11-22,shibuya,coffee,2\n2026-11-22,shibuya,cake,1\n2026-11-22,shibuya,coffee,1\n"
                  "2026-11-22,shibuya,tea,2\n")
_SALES_UENO = "2026-11-22,ueno,cake,2\n2026-11-22,ueno,coffee,1\n2026-11-22,ueno,cake,1\n"

APP_CONF = (
    "# アプリ設定（教材用）\n"
    "port=8080\n"
    "\n"
    "# 接続先\n"
    "db_host=db.internal\n"
    "theme_color=#336699\n"
    "#debug=true\n"
    "\n"
    "log_level=info\n"
)

VISITORS = "sato\ntanaka\nsato\nito\nsuzuki\ntanaka\nsato\nito\n"

_DAY_LOGS = {
    "logs/2026-11-19.log": "2026-11-19 10:00:00 INFO backup ok\n2026-11-19 22:00:00 WARN backup slow\n",
    "logs/2026-11-20.log": "2026-11-20 10:00:00 INFO backup ok\n",
    "logs/2026-11-21.log": "2026-11-21 10:00:00 ERROR backup failed\n2026-11-21 10:05:00 INFO backup retry ok\n",
    "logs/README.txt": "このフォルダには日付ごとのバックアップログを置きます。\n",
}

_WEB_LOGS = {
    "logs/web1.log": ("2026-11-21 10:00:01 web1 INFO start\n"
                      "2026-11-21 10:03:12 web1 ERROR db timeout\n"
                      "2026-11-21 10:07:40 web1 ERROR db timeout\n"
                      "2026-11-21 10:09:00 web1 INFO error budget ok\n"),
    "logs/web2.log": ("2026-11-21 10:00:02 web2 INFO start\n"
                      "2026-11-21 10:30:00 web2 INFO healthy\n"),
    "logs/web3.log": ("2026-11-21 10:00:03 web3 INFO start\n"
                      "2026-11-21 10:02:55 web3 ERROR cache unavailable\n"
                      "2026-11-21 10:04:10 web3 ERROR db timeout\n"
                      "2026-11-21 10:06:30 web3 ERROR disk full\n"),
}

_INCIDENT_LOGS = {
    "logs/web1.log": ("2026-11-21 10:00:01 web1 INFO start\n"
                      "2026-11-21 10:03:12 web1 ERROR db timeout\n"
                      "2026-11-21 10:07:40 web1 ERROR db timeout\n"
                      "2026-11-21 10:09:00 web1 INFO error budget ok\n"
                      "2026-11-21 10:12:30 web1 ERROR cache unavailable\n"),
    "logs/web2.log": ("2026-11-21 10:00:02 web2 INFO start\n"
                      "2026-11-21 10:02:05 web2 ERROR db timeout\n"
                      "2026-11-21 10:05:44 web2 WARN slow query\n"
                      "2026-11-21 10:10:10 web2 ERROR disk full\n"
                      "2026-11-21 10:11:00 web2 ERROR db timeout\n"),
}

_WEEKLY = "# 週次障害メモ\n11/20: ERROR なし\n"

SCENARIOS = [
    # ------------------------------------------------------------------ ★1
    {
        "id": "fes-logs-01",
        "level": 1,
        "title": "404 の行だけを抜き出す",
        "brief": 'アクセスログ から、ステータスコードが 404（ページが見つからない）の行だけを not_found.txt に保存してください。パスやデータサイズにたまたま 404 という数字が入っている行は含めません。アクセスログ は変更しません。',
        "files": {"access.log": ACCESS},
        "solution": ['grep " 404 " access.log > not_found.txt'],
        "alt_solutions": [['cat access.log | grep " 404 " > not_found.txt'],
                          ['grep "\\" 404 " access.log > not_found.txt']],
        "traps": [["grep 404 access.log > not_found.txt"], ["grep -c \" 404 \" access.log > not_found.txt"]],
        "expected_files": {"access.log": ACCESS,
                           "not_found.txt": "".join(l for l in ACCESS.splitlines(keepends=True) if " 404 " in l)},
        "hints": ["404 という文字は、ステータスコード以外の場所（パスやサイズ）にも出てきます。まず cat で中身を見ましょう。",
                  'ls と cat で対象の名前・場所・内容を確かめます。ステータスコードは前後が空白で区切られています。空白ごと探すと、ほかの数字と区別できます。',
                  "grep \" 404 \" access.log > not_found.txt のように、引用符で空白を含めて探します。"],
        "explanation": "grep は「その文字を含む行」をすべて拾います。8404 や /docs/404-guide のような行まで混ざると、障害の件数を見誤ります。"
                       "前後の区切り（空白）まで含めて探すのが、ログを正しく絞り込むコツです。",
        "practice": ["2-2", "2-7"],
    },
    {
        "id": "fes-logs-02",
        "level": 1,
        "title": "ERROR の件数を数字だけで残す",
        "brief": 'アプリのログ に、大文字の ERROR を含む行が何行あるかを数え、その数字だけを error_count.txt に保存してください。ファイル名などの余計な文字は入れません。小文字の error（正常な行の説明）は数えません。',
        "files": {"app.log": APP},
        "solution": ["grep -c ERROR app.log > error_count.txt"],
        "alt_solutions": [["grep ERROR app.log | wc -l > error_count.txt"],
                          ["cat app.log | grep -c ERROR > error_count.txt"]],
        "traps": [["grep -ci error app.log > error_count.txt"], ["wc -l app.log > error_count.txt"],
                  ["grep ERROR app.log | wc -l app.log > error_count.txt"]],
        "expected_files": {"error_count.txt": "3\n", "app.log": APP},
        "hints": ["行を探すコマンドには、一致した行の「数」だけを表示するオプションがあります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。grep -c は一致した行数を数えます。grep の結果を wc -l に渡しても数えられます。',
                  "grep -c ERROR app.log > error_count.txt。-i を付けると小文字の error まで数えてしまいます。"],
        "explanation": "障害報告では「何件起きたか」をすぐ聞かれます。grep -c や grep | wc -l で数えれば、目で数えるより速く正確です。"
                       "大文字小文字の違いで件数が変わるので、何を数えるのかを先に決めます。",
        "practice": ["2-2", "2-5"],
    },
    {
        "id": "fes-logs-03",
        "level": 1,
        "title": "表記ゆれのある警告をまとめて拾う",
        "brief": 'アプリのログ の警告は、書いた人によって WARN・warn・Warning と表記がばらばらです。大文字小文字に関係なく warn を含む行をすべて warnings.txt に保存してください。行の順番は元のままにします。',
        "files": {"app.log": APP},
        "solution": ["grep -i warn app.log > warnings.txt"],
        "alt_solutions": [["cat app.log | grep -i WARN > warnings.txt"],
                          ["grep [Ww][Aa][Rr][Nn] app.log > warnings.txt"]],
        "traps": [["grep WARN app.log > warnings.txt"], ["grep warn app.log > warnings.txt"],
                  ["grep -i warning app.log > warnings.txt"]],
        "expected_files": {"warnings.txt": _APP_LINES[1] + _APP_LINES[4] + _APP_LINES[7], "app.log": APP},
        "hints": ["grep はふつう大文字と小文字を区別します。WARN で探すと warn や Warning は見つかりません。",
                  'ls と cat で対象の名前・場所・内容を確かめます。大文字小文字を区別しないで探すオプションがあります（ignore case の i）。',
                  "grep -i warn app.log > warnings.txt で3行が保存されます。"],
        "explanation": "複数のプログラムが書くログは表記がそろっていないことがよくあります。-i を使うと表記ゆれを1回で拾えます。"
                       "逆に、件数を厳密に数えたいときは -i を付けないなど、目的で使い分けます。",
        "practice": ["2-2"],
    },
    {
        "id": "fes-logs-04",
        "level": 1,
        "title": "timeout が何行目にあるかを記録する",
        "brief": 'アプリのログ の中で timeout を含む行を、何行目かが分かる形（行番号:行の内容）で timeout_lines.txt に保存してください。あとで vim などでその行へすぐ飛べるようにするためです。',
        "files": {"app.log": APP},
        "solution": ["grep -n timeout app.log > timeout_lines.txt"],
        "alt_solutions": [["cat app.log | grep -n timeout > timeout_lines.txt"]],
        "traps": [["grep timeout app.log > timeout_lines.txt"], ["cat -n app.log | grep timeout > timeout_lines.txt"],
                  ["grep timeout app.log | grep -n timeout > timeout_lines.txt"]],
        "expected_files": {"timeout_lines.txt": "3:" + _APP_LINES[2] + "10:" + _APP_LINES[9] + "11:" + _APP_LINES[10]},
        "hints": ["grep には、見つかった行の番号を先頭に付けるオプションがあります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。grep -n は「行番号:内容」の形で表示します。cat -n とは表示の形が違います。',
                  "grep -n timeout app.log > timeout_lines.txt"],
        "explanation": "行番号が分かれば、エディタでその場所へ直接移動したり、前後の行を確認したりできます。"
                       "先に絞り込んでから番号を付けると、元のファイルの行番号ではなくなる点にも注意します。",
        "practice": ["2-2", "2-5"],
    },
    {
        "id": "fes-logs-05",
        "level": 1,
        "title": "最新のログ5行を切り出す",
        "brief": 'アプリのログ は新しい行が下に追記されていきます。最新の5行だけを recent.txt に保存してください。順番は元のままにします。',
        "files": {"app.log": APP},
        "solution": ["tail -n 5 app.log > recent.txt"],
        "alt_solutions": [["tail -5 app.log > recent.txt"], ["cat app.log | tail -n 5 > recent.txt"]],
        "traps": [["head -n 5 app.log > recent.txt"], ["sort -r app.log | head -n 5 > recent.txt"],
                  ["tail app.log > recent.txt"]],
        "expected_files": {"recent.txt": "".join(_APP_LINES[-5:])},
        "hints": ["ファイルの先頭を見るコマンドと、末尾を見るコマンドがあります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。tail は末尾を表示します。何行出すかは -n で決めます（何も付けないと10行）。',
                  "tail -n 5 app.log > recent.txt"],
        "explanation": "障害対応ではまず「今何が起きているか」を見るため、ログの末尾を確認します。"
                       "巨大なログでも tail なら必要な分だけをすぐ取り出せます。",
        "practice": ["1-7"],
    },
    {
        "id": "fes-logs-06",
        "level": 1,
        "title": "ファイルごとの行数一覧を残す",
        "brief": 'ログ用フォルダの3台分のログについて、ファイルごとの行数と合計の行数を一覧にして line_counts.txt に保存してください。各行は「行数 ファイル名」の形で、最後に total の行が付く形にします。',
        "files": dict(_WEB_LOGS),
        "solution": ["wc -l logs/*.log > line_counts.txt"],
        "alt_solutions": [["wc -l logs/web1.log logs/web2.log logs/web3.log > line_counts.txt"]],
        "traps": [["cat logs/*.log | wc -l > line_counts.txt"], ["wc logs/*.log > line_counts.txt"],
                  ["wc -l logs/web1.log logs/web3.log > line_counts.txt"]],
        "expected_files": {"line_counts.txt": "4 logs/web1.log\n2 logs/web2.log\n4 logs/web3.log\n10 total\n"},
        "hints": ["行数を数えるコマンドに、ファイルを複数並べて渡すとどう表示されるか試してみましょう。",
                  'ls と cat で対象の名前・場所・内容を確かめます。wc -l にファイルを複数渡すと、ファイルごとの行数と total が出ます。ワイルドカード * も使えます。',
                  "wc -l logs/*.log > line_counts.txt"],
        "explanation": "どのサーバーのログが急に増えたかは、ファイル別の行数を比べると分かります。"
                       "同じ wc -l でも、パイプで1本にまとめると合計しか分からない点が違います。",
        "practice": ["1-3", "1-7"],
    },
    {
        "id": "fes-logs-07",
        "level": 1,
        "title": "日付ごとのログを1つにまとめる",
        "brief": 'ログ用フォルダに日付ごとのログ3つと説明書があります。3日分のログだけを日付の古い順につなげて week.log に保存してください。説明書の中身は入れません。',
        "files": dict(_DAY_LOGS),
        "solution": ["cat logs/*.log > week.log"],
        "alt_solutions": [["cat logs/2026-11-19.log logs/2026-11-20.log logs/2026-11-21.log > week.log"],
                          ["cat logs/2026-11-19.log > week.log", "cat logs/2026-11-20.log >> week.log",
                           "cat logs/2026-11-21.log >> week.log"]],
        "traps": [["cat logs/* > week.log"],
                  ["cat logs/2026-11-21.log logs/2026-11-20.log logs/2026-11-19.log > week.log"],
                  ["cat logs/2026-11-19.log > week.log", "cat logs/2026-11-20.log > week.log",
                   "cat logs/2026-11-21.log > week.log"]],
        "expected_files": {"week.log": _DAY_LOGS["logs/2026-11-19.log"] + _DAY_LOGS["logs/2026-11-20.log"]
                           + _DAY_LOGS["logs/2026-11-21.log"]},
        "hints": ["cat はファイルを複数並べると、並べた順につなげて表示します。",
                  'ls と cat で対象の名前・場所・内容を確かめます。ワイルドカード *.log は名前順に広がります。* だけだと README.txt まで含まれます。',
                  "cat logs/*.log > week.log。1つずつ追記するなら2つ目からは >> を使います。"],
        "explanation": "ログは日付ごとに分かれていることが多く、まとめて調べるには連結が必要です。"
                       "ワイルドカードの一致範囲を絞ること、> は上書きで >> は追記であることが大切です。",
        "practice": ["2-1", "1-3"],
    },
    {
        "id": "fes-logs-08",
        "level": 1,
        "title": "来店者を重複なしの名簿にする",
        "brief": '来店者の記録ファイル には来店した人の名前が来た順に並んでいて、同じ人が何度も出てきます。重複を取り除き、名前順（アルファベット順）に並べた一覧を members.txt に保存してください。',
        "files": {"visitors.txt": VISITORS},
        "solution": ["sort -u visitors.txt > members.txt"],
        "alt_solutions": [["sort visitors.txt | uniq > members.txt"], ["cat visitors.txt | sort | uniq > members.txt"]],
        "traps": [["uniq visitors.txt > members.txt"], ["sort visitors.txt > members.txt"],
                  ["uniq visitors.txt | sort > members.txt"]],
        "expected_files": {"members.txt": "ito\nsato\nsuzuki\ntanaka\n", "visitors.txt": VISITORS},
        "hints": ["uniq は「となり合った」同じ行しかまとめません。まず同じ名前を隣どうしに集める必要があります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。sort で並べ替えてから uniq に渡すか、sort の重複除去オプションを使います。',
                  "sort -u visitors.txt > members.txt、または sort visitors.txt | uniq > members.txt"],
        "explanation": "uniq だけでは離れた場所の重複が残る、というのはとてもよくある失敗です。"
                       "「並べ替えてからまとめる」は集計の基本の型なので、手に覚えさせましょう。",
        "practice": ["2-7"],
    },
    {
        "id": "fes-logs-09",
        "level": 1,
        "title": "週次メモにエラーを書き足す",
        "brief": '週次メモのファイル には先週までのメモがすでに書かれています。この内容を消さずに、アプリのログ の ERROR を含む行を末尾に書き足してください。',
        "files": {"weekly.txt": _WEEKLY, "app.log": APP},
        "solution": ["grep ERROR app.log >> weekly.txt"],
        "alt_solutions": [["cat app.log | grep ERROR >> weekly.txt"]],
        "traps": [["grep ERROR app.log > weekly.txt"], ["grep -i error app.log >> weekly.txt"]],
        "expected_files": {"weekly.txt": _WEEKLY + _APP_LINES[2] + _APP_LINES[6] + _APP_LINES[9]},
        "hints": ["> で保存すると、それまでの中身は消えてしまいます。",
                  'ls と cat で対象の名前・場所・内容を確かめます。既存のファイルの末尾に足すときは >> を使います。',
                  "grep ERROR app.log >> weekly.txt。終わったら cat weekly.txt で前の内容が残っているか確かめます。"],
        "explanation": "> と >> の取り違えは、大切な記録を一瞬で消してしまう事故の代表です。"
                       "書き足すときは >>、作り直すときは > と、意識して使い分けます。",
        "practice": ["2-1", "EX-3"],
    },
    # ------------------------------------------------------------------ ★2
    {
        "id": "fes-logs-10",
        "level": 2,
        "title": "コメントと空行を除いた設定だけを見る",
        "brief": 'アプリの設定ファイル から、# で始まるコメント行と空行を取り除き、実際に効いている設定だけを active.conf に保存してください。theme_color=#336699 のように、行の途中に # がある設定は残します。アプリの設定ファイル は変更しません。',
        "files": {"app.conf": APP_CONF},
        "solution": ['grep -v "^#" app.conf | grep -v "^$" > active.conf'],
        "alt_solutions": [['grep -v "^$" app.conf | grep -v "^#" > active.conf'],
                          ["grep = app.conf | grep -v ^# > active.conf"]],
        "traps": [['grep -v "#" app.conf | grep -v "^$" > active.conf'], ['grep -v "^#" app.conf > active.conf'],
                  ['grep -v "^$" app.conf > active.conf']],
        "expected_files": {"active.conf": "port=8080\ndb_host=db.internal\ntheme_color=#336699\nlog_level=info\n",
                           "app.conf": APP_CONF},
        "hints": ["「〜を含まない行」を残す grep のオプションと、「行の先頭」「行の終わり」を表す記号を組み合わせます。",
                  'ls と cat で対象の名前・場所・内容を確かめます。grep -v で一致しない行を残せます。^# は「# で始まる」、^$ は「何もない行（空行）」です。',
                  "grep -v \"^#\" app.conf | grep -v \"^$\" > active.conf"],
        "explanation": "長い設定ファイルは説明コメントが大半で、効いている値が見えにくいものです。"
                       "^ と $ で「行のどこに一致するか」を指定すると、必要な行を消しすぎずに絞り込めます。",
        "practice": ["2-4"],
    },
    {
        "id": "fes-logs-11",
        "level": 2,
        "title": "営業部のメールアドレスだけを抜き出す",
        "brief": '利用者名簿の CSV（id,name,email,department）から、department がちょうど sales の人のメールアドレスだけを1行ずつ sales_emails.txt に保存してください。presales の人や、アドレスに sales を含むだけの人は入れません。見出し行も入れません。',
        "files": {"users.csv": USERS_CSV},
        "solution": ['grep ",sales$" users.csv | cut -d , -f 3 > sales_emails.txt'],
        "alt_solutions": [['cut -d , -f 3,4 users.csv | grep ",sales$" | cut -d , -f 1 > sales_emails.txt'],
                          ['cat users.csv | grep ",sales$" | cut -d , -f 3 > sales_emails.txt']],
        "traps": [["grep sales users.csv | cut -d , -f 3 > sales_emails.txt"],
                  ['grep ",sales" users.csv | cut -d , -f 3 > sales_emails.txt'],
                  ['grep ",sales$" users.csv > sales_emails.txt']],
        "expected_files": {"sales_emails.txt": "sato@example.com\ntanaka@example.com\n"},
        "hints": ["まず条件に合う行を絞り込み、そのあとで必要な列だけを取り出す、の2段階です。",
                  'ls と cat で対象の名前・場所・内容を確かめます。department は行の最後の列です。「,sales で終わる」は $ を使って表せます。列の取り出しは cut -d , -f 番号 です。',
                  "grep \",sales$\" users.csv | cut -d , -f 3 > sales_emails.txt"],
        "explanation": "CSV は「区切り文字で列を数える」と扱えます。ただ単語で grep すると別の列や似た値まで拾うので、"
                       "区切り文字や行末まで含めて条件を書くのが、名簿やデータを正確に扱うコツです。",
        "practice": ["2-8"],
    },
    {
        "id": "fes-logs-12",
        "level": 2,
        "title": "3台分の ERROR を合計で数える",
        "brief": 'ログ用フォルダの 3台分のログ に出ている、大文字 ERROR の行の合計件数を数え、数字1つだけを total_errors.txt に保存してください。ファイルごとの内訳ではなく、全体の合計です。',
        "files": dict(_WEB_LOGS),
        "solution": ["cat logs/*.log | grep -c ERROR > total_errors.txt"],
        "alt_solutions": [["grep ERROR logs/*.log | wc -l > total_errors.txt"],
                          ["cat logs/web1.log logs/web2.log logs/web3.log | grep ERROR | wc -l > total_errors.txt"]],
        "traps": [["grep -c ERROR logs/*.log > total_errors.txt"], ["cat logs/*.log | grep -ci error > total_errors.txt"],
                  ["wc -l logs/*.log > total_errors.txt"]],
        "expected_files": {"total_errors.txt": "5\n"},
        "hints": ["grep -c に複数のファイルを渡すと、ファイルごとの件数が別々に表示されます。一度試してみましょう。",
                  'ls と cat で対象の名前・場所・内容を確かめます。全部のファイルを cat で1本の流れにしてから数えるか、grep の結果の行数を wc -l で数えます。',
                  "cat logs/*.log | grep -c ERROR > total_errors.txt"],
        "explanation": "grep -c ERROR *.log はファイル別の件数を出すので、合計を聞かれたときの答えにはなりません。"
                       "「内訳」なのか「合計」なのかを意識して、パイプで1本にまとめるかどうかを選びます。",
        "practice": ["2-2", "2-7"],
    },
    {
        "id": "fes-logs-13",
        "level": 2,
        "title": "ステータスコード別の件数表を作る",
        "brief": 'アクセスログ のステータスコード（200 や 404 など）ごとに、何件あったかを数えて status_count.txt に保存してください。形式は uniq -c の表示どおり「件数 ステータスコード」で、ステータスコードの小さい順に並べます。',
        "files": {"access.log": ACCESS},
        "solution": ['cut -d " " -f 9 access.log | sort | uniq -c > status_count.txt'],
        "alt_solutions": [["cut -d '\"' -f 3 access.log | cut -d \" \" -f 2 | sort | uniq -c > status_count.txt"],
                          ['cat access.log | cut -d " " -f 9 | sort | uniq -c > status_count.txt']],
        "traps": [['cut -d " " -f 9 access.log | uniq -c > status_count.txt'],
                  ['cut -d " " -f 9 access.log | sort -u > status_count.txt'],
                  ['cut -d " " -f 10 access.log | sort | uniq -c > status_count.txt']],
        "expected_files": {"status_count.txt": "     12 200\n      1 304\n      3 404\n      2 500\n      1 502\n      1 503\n"},
        "hints": ["ステータスコードは、空白で区切ると左から何番目の列でしょうか。cat で1行を数えてみましょう。",
                  'ls と cat で対象の名前・場所・内容を確かめます。cut -d " " -f 番号 で列を取り出し、sort で同じ値を集めてから uniq -c で数えます。',
                  "cut -d \" \" -f 9 access.log | sort | uniq -c > status_count.txt"],
        "explanation": "「列を取り出す → 並べる → 数える」は、ログ集計でいちばんよく使う型です。"
                       "sort を忘れると、同じコードが離れて出てきたときに別々に数えられてしまいます。",
        "practice": ["2-7", "6-5"],
    },
    {
        "id": "fes-logs-14",
        "level": 2,
        "title": "アクセスの多い IP 上位3件",
        "brief": 'アクセスログ で、アクセス回数の多い IP アドレスの上位3件を top_ip.txt に保存してください。形式は「件数 IPアドレス」（uniq -c の表示）で、回数の多い順に3行だけにします。',
        "files": {"access.log": ACCESS},
        "solution": ['cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 > top_ip.txt'],
        "alt_solutions": [['cut -d " " -f 1 access.log | sort | uniq -c | sort -n | tail -n 3 | sort -rn > top_ip.txt'],
                          ['cat access.log | cut -d " " -f 1 | sort | uniq -c | sort -r -n | head -3 > top_ip.txt']],
        "traps": [['cut -d " " -f 1 access.log | sort | uniq -c | sort -n | head -n 3 > top_ip.txt'],
                  ['cut -d " " -f 1 access.log | uniq -c | sort -rn | head -n 3 > top_ip.txt'],
                  ['cut -d " " -f 1 access.log | sort -u | head -n 3 > top_ip.txt']],
        "expected_files": {"top_ip.txt": "      8 203.0.113.7\n      5 198.51.100.23\n      4 192.0.2.44\n"},
        "hints": ["まず IP ごとの件数表を作り、それを件数で並べ替えてから先頭を取ります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。件数は数字なので、並べ替えは数値として（-n）、多い順に（-r）します。先頭3行は head です。',
                  "cut -d \" \" -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 > top_ip.txt"],
        "explanation": "ランキングは攻撃元の特定や、負荷の原因調査でよく使います。"
                       "-n を付けないと文字として比べるので、桁の違う数で順位が狂うことがあります。",
        "practice": ["2-7"],
    },
    {
        "id": "fes-logs-15",
        "level": 2,
        "title": "時間帯ごとのアクセス数を調べる",
        "brief": 'アクセスログ の時刻（[21/Nov/2026:10:01:05 のような部分）から「時」だけを取り出し、時間帯ごとのアクセス件数を hourly.txt に保存してください。形式は「件数 時」（例: 8 10）で、時の早い順に並べます。',
        "files": {"access.log": ACCESS},
        "solution": ["cut -d : -f 2 access.log | sort | uniq -c > hourly.txt"],
        "alt_solutions": [['cut -d " " -f 4 access.log | cut -d : -f 2 | sort | uniq -c > hourly.txt'],
                          ["cut -d [ -f 2 access.log | cut -d : -f 2 | sort | uniq -c > hourly.txt"]],
        "traps": [["cut -d : -f 3 access.log | sort | uniq -c > hourly.txt"],
                  ["cut -d : -f 2 access.log | sort -u > hourly.txt"],
                  ["cut -d : -f 2 access.log | sort | uniq -c | sort -rn > hourly.txt"]],
        "expected_files": {"hourly.txt": "      2 09\n      8 10\n      7 11\n      3 12\n"},
        "hints": ["時刻は : で区切られています。区切り文字を : にすると、「時」は何番目の列になるでしょうか。",
                  'ls と cat で対象の名前・場所・内容を確かめます。cut -d : -f 番号 で「時」を取り出し、sort と uniq -c で数えます。',
                  "cut -d : -f 2 access.log | sort | uniq -c > hourly.txt"],
        "explanation": "区切り文字は空白やカンマだけではありません。: で切れば時刻の一部を取り出せます。"
                       "時間帯別の件数は、混雑のピークや障害の始まりを見つける手がかりになります。",
        "practice": ["2-7", "2-8"],
    },
    {
        "id": "fes-logs-16",
        "level": 2,
        "title": "ログイン失敗の多いユーザーを調べる",
        "brief": '認証ログ から、パスワード認証に失敗した（Failed password の）記録だけを対象に、狙われたユーザー名ごとの回数を failed_users.txt に保存してください。形式は「件数 ユーザー名」で、回数の多い順に並べます。ログインに成功した記録は数えません。',
        "files": {"auth.log": AUTH},
        "solution": ['grep "Failed password" auth.log | cut -d " " -f 9 | sort | uniq -c | sort -rn > failed_users.txt'],
        "alt_solutions": [['cut -d " " -f 6,9 auth.log | grep Failed | cut -d " " -f 2 | sort | uniq -c | sort -rn > failed_users.txt'],
                          ['grep Failed auth.log | cut -d " " -f 9 | sort | uniq -c | sort -r -n > failed_users.txt']],
        "traps": [['grep password auth.log | cut -d " " -f 9 | sort | uniq -c | sort -rn > failed_users.txt'],
                  ['grep Failed auth.log | cut -d " " -f 9 | uniq -c | sort -rn > failed_users.txt'],
                  ['grep Failed auth.log | cut -d " " -f 11 | sort | uniq -c | sort -rn > failed_users.txt']],
        "expected_files": {"failed_users.txt": "      3 root\n      2 admin\n      1 alice\n"},
        "hints": ["まず失敗の行だけに絞ります。Accepted password（成功）の行も password を含むので注意します。",
                  'ls と cat で対象の名前・場所・内容を確かめます。Failed password で絞ったら、ユーザー名が空白区切りで何番目かを数えて cut します。あとは集計の型です。',
                  "grep \"Failed password\" auth.log | cut -d \" \" -f 9 | sort | uniq -c | sort -rn > failed_users.txt"],
        "explanation": "root や admin への失敗が続くのは、総当たり攻撃のよくある兆候です。"
                       "認証ログを集計できると、どのアカウントが狙われているかを数字で示せます。",
        "practice": ["2-7", "4-7"],
    },
    {
        "id": "fes-logs-17",
        "level": 2,
        "title": "10時台と11時台のエラーだけを抜き出す",
        "brief": 'アプリのログ から、10:00〜11:59 の間に出た ERROR の行だけを incident.txt に保存してください。9時台や12時台の ERROR は入れません。行の順番は元のままにします。',
        "files": {"app.log": APP_HOURS},
        "solution": ['grep " 1[01]:" app.log | grep ERROR > incident.txt'],
        "alt_solutions": [['grep ERROR app.log | grep "^2026-11-21 1[01]:" > incident.txt'],
                          ['grep -E "^[0-9-]+ 1[01]:[0-9:]+ ERROR" app.log > incident.txt']],
        "traps": [["grep ERROR app.log | grep 1[01] > incident.txt"],
                  ['grep ERROR app.log | grep " 10:" > incident.txt'],
                  ['grep ERROR app.log | grep " 1" > incident.txt']],
        "expected_files": {"incident.txt": "2026-11-21 10:03:44 ERROR db connection timeout\n"
                                           "2026-11-21 11:12:09 ERROR payment api returned 502\n"
                                           "2026-11-21 11:59:59 ERROR db deadlock detected\n"},
        "hints": ["日付の 2026-11-21 にも 1 や 11 が含まれています。「時」の部分だけに一致させる工夫が必要です。",
                  'ls と cat で対象の名前・場所・内容を確かめます。[01] は「0 か 1 のどちらか1文字」です。時刻の前の空白と後ろの : まで含めると、時の位置に限定できます。',
                  "grep \" 1[01]:\" app.log | grep ERROR > incident.txt"],
        "explanation": "障害は「何時から何時まで」と時間で区切って調べることが多いです。"
                       "[ ] や ^ などの正規表現で位置まで指定すると、日付や数値への誤ヒットを防げます。",
        "practice": ["2-4", "2-5"],
    },
    {
        "id": "fes-logs-18",
        "level": 2,
        "title": "店舗別の取引件数ランキング",
        "brief": '売上の CSV（date,store,item,qty）の取引の行数を店舗（store）ごとに数え、多い順に store_rank.txt に保存してください。形式は「件数 店舗名」です。1行目の見出し行は数に入れません。',
        "files": {"sales.csv": SALES_CSV},
        "solution": ["grep -v ^date sales.csv | cut -d , -f 2 | sort | uniq -c | sort -rn > store_rank.txt"],
        "alt_solutions": [["cut -d , -f 2 sales.csv | grep -v store | sort | uniq -c | sort -rn > store_rank.txt"],
                          ["grep 2026 sales.csv | cut -d , -f 2 | sort | uniq -c | sort -rn > store_rank.txt"]],
        "traps": [["cut -d , -f 2 sales.csv | sort | uniq -c | sort -rn > store_rank.txt"],
                  ["grep -v ^date sales.csv | cut -d , -f 2 | sort | uniq -c > store_rank.txt"],
                  ["grep -v ^date sales.csv | cut -d , -f 3 | sort | uniq -c | sort -rn > store_rank.txt"]],
        "expected_files": {"store_rank.txt": "      4 shibuya\n      3 ueno\n      2 ikebukuro\n", "sales.csv": SALES_CSV},
        "hints": ["CSV の1行目は列の名前（見出し）です。そのまま集計すると store という店舗が1件あることになってしまいます。",
                  'ls と cat で対象の名前・場所・内容を確かめます。grep -v で見出し行を除き、cut -d , -f 2 で店舗名を取り出してから、件数の集計とランキングの型につなげます。',
                  "grep -v ^date sales.csv | cut -d , -f 2 | sort | uniq -c | sort -rn > store_rank.txt"],
        "explanation": "表計算ソフトがなくても、CSV の集計はコマンドだけでできます。"
                       "見出し行が集計に混ざるのはよくあるミスなので、結果に見慣れない値がないか必ず確認します。",
        "practice": ["2-8", "6-5"],
    },
    {
        "id": "fes-logs-19",
        "level": 2,
        "title": "5xx エラーが出たページの一覧",
        "brief": 'アクセスログ から、ステータスコードが 500 番台（500・502・503 など、サーバー側のエラー）だった行のパスを、重複なしで名前順に error_paths.txt に保存してください。500 だけでなく 500 番台すべてが対象です。',
        "files": {"access.log": ACCESS},
        "solution": ['grep " 5[0-9][0-9] " access.log | cut -d " " -f 7 | sort -u > error_paths.txt'],
        "alt_solutions": [['grep -E "\\" 5[0-9]{2} " access.log | cut -d " " -f 7 | sort | uniq > error_paths.txt'],
                          ['cut -d " " -f 7,9 access.log | grep " 5" | cut -d " " -f 1 | sort -u > error_paths.txt']],
        "traps": [['grep " 500 " access.log | cut -d " " -f 7 | sort -u > error_paths.txt'],
                  ['grep " 5" access.log | cut -d " " -f 7 | sort -u > error_paths.txt'],
                  ['grep " 5[0-9][0-9] " access.log | cut -d " " -f 7 | uniq > error_paths.txt']],
        "expected_files": {"error_paths.txt": "/api/cart\n/api/order\n"},
        "hints": ["500 番台は「5 のあとに数字が2つ」です。正規表現の [0-9] は数字1文字を表します。",
                  'ls と cat で対象の名前・場所・内容を確かめます。前後の空白も含めて grep " 5[0-9][0-9] " のように探すと、データサイズの 5120 などに一致しません。そのあとパスの列を取り出します。',
                  "grep \" 5[0-9][0-9] \" access.log | cut -d \" \" -f 7 | sort -u > error_paths.txt"],
        "explanation": "5xx はサーバー側の不具合を表すので、どのページで起きたかが修正の出発点になります。"
                       "[0-9] を使うと、コードを1つずつ並べなくても「500 番台すべて」を表せます。",
        "practice": ["2-4", "2-7"],
    },
    # ------------------------------------------------------------------ ★3
    {
        "id": "fes-logs-20",
        "level": 3,
        "title": "総合：アクセス日報を1ファイルにまとめる",
        "brief": 'アクセスログ から日報 report.txt を作ってください。内容は上から順に次の7行のかたまりです。(1) 見出し「== アクセス日報 2026-11-21 ==」 (2) 「総アクセス数」 (3) 総アクセス数の数字だけ (4) 「ステータス別」 (5) ステータスコード別の件数（「件数 コード」、コードの小さい順） (6) 「上位IP」 (7) アクセスの多い IP 上位3件（「件数 IP」、多い順）。見出しの文字は書かれたとおりにします。',
        "files": {"access.log": ACCESS},
        "solution": ['echo "== アクセス日報 2026-11-21 ==" > report.txt',
                     "echo 総アクセス数 >> report.txt",
                     "cat access.log | wc -l >> report.txt",
                     "echo ステータス別 >> report.txt",
                     'cut -d " " -f 9 access.log | sort | uniq -c >> report.txt',
                     "echo 上位IP >> report.txt",
                     'cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 >> report.txt'],
        "alt_solutions": [['echo "== アクセス日報 2026-11-21 ==" > report.txt',
                           "echo 総アクセス数 >> report.txt",
                           'grep -c "" access.log >> report.txt',
                           "echo ステータス別 >> report.txt",
                           "cut -d '\"' -f 3 access.log | cut -d \" \" -f 2 | sort | uniq -c >> report.txt",
                           "echo 上位IP >> report.txt",
                           'cat access.log | cut -d " " -f 1 | sort | uniq -c | sort -n | tail -3 | sort -rn >> report.txt']],
        "traps": [['echo "== アクセス日報 2026-11-21 ==" > report.txt',
                   "echo 総アクセス数 >> report.txt",
                   "wc -l access.log >> report.txt",
                   "echo ステータス別 >> report.txt",
                   'cut -d " " -f 9 access.log | sort | uniq -c >> report.txt',
                   "echo 上位IP >> report.txt",
                   'cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 >> report.txt'],
                  ['echo "== アクセス日報 2026-11-21 ==" > report.txt',
                   "echo 総アクセス数 >> report.txt",
                   "cat access.log | wc -l >> report.txt",
                   "echo ステータス別 > report.txt",
                   'cut -d " " -f 9 access.log | sort | uniq -c >> report.txt',
                   "echo 上位IP >> report.txt",
                   'cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 >> report.txt'],
                  ['echo "== アクセス日報 2026-11-21 ==" > report.txt',
                   "echo 総アクセス数 >> report.txt",
                   "cat access.log | wc -l >> report.txt",
                   "echo ステータス別 >> report.txt",
                   'cut -d " " -f 9 access.log | uniq -c >> report.txt',
                   "echo 上位IP >> report.txt",
                   'cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 3 >> report.txt']],
        "expected_files": {"report.txt": "== アクセス日報 2026-11-21 ==\n総アクセス数\n20\nステータス別\n"
                                         "     12 200\n      1 304\n      3 404\n      2 500\n      1 502\n      1 503\n"
                                         "上位IP\n      8 203.0.113.7\n      5 198.51.100.23\n      4 192.0.2.44\n"},
        "hints": ["1行目だけ新しく作り、2つ目からはすべて末尾に書き足していきます。途中で > を使うと、それまでの内容が消えます。",
                  "ls と cat で対象の名前・場所・内容を確かめます。見出しは echo で書けます。総数は wc -l にファイル名を渡すと名前まで付くので、パイプで渡して数字だけにします。",
                  "最初の見出しだけ > で、あとはすべて >> です。ステータスは cut の -d と -f で9列目を取り出し、sort のあと uniq -c で数えます。上位IPは1列目を同様に数え、sort -rn のあと head で3行に絞ります。"],
        "explanation": "毎日同じ形の報告を作る作業は、コマンドの組み合わせで再現できます。"
                       "最初は > で作り直し、以降は >> で積み上げる、という流れはシェルスクリプトで自動化するときの土台になります。",
        "practice": ["2-1", "2-7", "6-1", "EX-3"],
    },
    {
        "id": "fes-logs-21",
        "level": 3,
        "title": "総合：2日分の認証ログから遮断リストを作る",
        "brief": 'ログ用フォルダにある前日と当日の認証ログを対象に、Failed password の記録を調べてください。監視サーバー 192.0.2.10 は打ち間違いなので対象外です（192.0.2.100 など似た別のアドレスは対象）。(1) 失敗した接続元 IP を重複なしで名前順に blocklist.txt へ保存する。(2) 失敗回数の多い接続元 IP 上位2件を「件数 IP」の形で多い順に attack_top.txt へ保存する。',
        "files": {"logs/auth-1.log": AUTH_1, "logs/auth-2.log": AUTH_2},
        "solution": ['cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | grep -v "^192\\.0\\.2\\.10$" | sort -u > blocklist.txt',
                     'cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | grep -v "^192\\.0\\.2\\.10$" | sort | uniq -c | sort -rn | head -n 2 > attack_top.txt'],
        "alt_solutions": [['grep Failed logs/auth-*.log | cut -d " " -f 11 | grep -v "^192.0.2.10$" | sort | uniq > blocklist.txt',
                           'grep Failed logs/auth-*.log | cut -d " " -f 11 | sort | uniq -c | sort -rn | grep -v " 192.0.2.10$" | head -2 > attack_top.txt'],
                          ['cat logs/auth-1.log logs/auth-2.log | grep "Failed password" > failed.txt',
                           'cut -d " " -f 11 failed.txt | grep -v "^192.0.2.10$" | sort -u > blocklist.txt',
                           'cut -d " " -f 11 failed.txt | grep -v "^192.0.2.10$" | sort | uniq -c | sort -rn | head -n 2 > attack_top.txt']],
        "traps": [['cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | grep -v 192.0.2.10 | sort -u > blocklist.txt',
                   'cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | grep -v 192.0.2.10 | sort | uniq -c | sort -rn | head -n 2 > attack_top.txt'],
                  ['grep "Failed password" logs/auth-2.log | cut -d " " -f 11 | grep -v "^192.0.2.10$" | sort -u > blocklist.txt',
                   'grep "Failed password" logs/auth-2.log | cut -d " " -f 11 | grep -v "^192.0.2.10$" | sort | uniq -c | sort -rn | head -n 2 > attack_top.txt'],
                  ['cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | sort -u > blocklist.txt',
                   'cat logs/auth-*.log | grep "Failed password" | cut -d " " -f 11 | sort | uniq -c | sort -rn | head -n 2 > attack_top.txt']],
        "expected_files": {"blocklist.txt": "192.0.2.100\n198.51.100.77\n203.0.113.66\n",
                           "attack_top.txt": "      4 203.0.113.66\n      3 192.0.2.100\n"},
        "hints": ["2つのファイルをまとめて1本の流れにし、失敗の行 → IP の列 → 監視サーバーを除く、と順に絞ります。",
                  'ls と cat で対象の名前・場所・内容を確かめます。grep -v 192.0.2.10 だと 192.0.2.100 まで消えます。^ と $ で「行全体がそのアドレス」に限定しましょう。. は任意の1文字なので \\. と書くとより正確です。',
                  "cat logs/auth-*.log | grep \"Failed password\" | cut -d \" \" -f 11 | grep -v \"^192.0.2.10$\" のあとに、"
                  "sort -u > blocklist.txt、または sort | uniq -c | sort -rn | head -n 2 > attack_top.txt をつなげます。"],
        "explanation": "攻撃の調査では、ローテーションされた古いログも合わせて見ないと回数を少なく見積もってしまいます。"
                       "除外条件が甘いと、本当に止めるべき相手を見逃すことにもなります。行全体に一致させる ^...$ は除外リストを作るときの基本です。",
        "practice": ["2-4", "2-7", "4-7"],
    },
    {
        "id": "fes-logs-22",
        "level": 3,
        "title": "総合：店舗別の売上 CSV を1つにまとめて集計する",
        "brief": '売上用フォルダに、店舗ごとの CSV が3つあります。(1) 見出しを1行目に1回だけ置き、3店舗のデータ行をファイル名順につなげた all.csv を作ってください。(2) 商品（item）ごとの取引行数を多い順に「件数 商品名」の形で item_rank.txt に保存します。元の CSV は変更しません。',
        "files": {"sales/ikebukuro.csv": _SALES_HEAD + _SALES_IKEBUKURO, "sales/shibuya.csv": _SALES_HEAD + _SALES_SHIBUYA,
                  "sales/ueno.csv": _SALES_HEAD + _SALES_UENO},
        "solution": ["head -n 1 sales/shibuya.csv > all.csv",
                     "cat sales/*.csv | grep -v ^date >> all.csv",
                     "grep -v ^date all.csv | cut -d , -f 3 | sort | uniq -c | sort -rn > item_rank.txt"],
        "alt_solutions": [["echo date,store,item,qty > all.csv",
                           "grep -v ^date sales/ikebukuro.csv >> all.csv",
                           "grep -v ^date sales/shibuya.csv >> all.csv",
                           "grep -v ^date sales/ueno.csv >> all.csv",
                           "cut -d , -f 3 sales/*.csv | grep -v item | sort | uniq -c | sort -rn > item_rank.txt"],
                          ["head -1 sales/ueno.csv > all.csv",
                           "cat sales/ikebukuro.csv sales/shibuya.csv sales/ueno.csv | grep 2026 >> all.csv",
                           "cut -d , -f 3 all.csv | grep -v ^item | sort | uniq -c | sort -rn > item_rank.txt"]],
        "traps": [["cat sales/*.csv > all.csv",
                   "grep -v ^date all.csv | cut -d , -f 3 | sort | uniq -c | sort -rn > item_rank.txt"],
                  ["head -n 1 sales/shibuya.csv > all.csv",
                   "grep -v ^date sales/*.csv >> all.csv",
                   "grep -v ^date all.csv | cut -d , -f 3 | sort | uniq -c | sort -rn > item_rank.txt"],
                  ["head -n 1 sales/shibuya.csv > all.csv",
                   "cat sales/*.csv | grep -v ^date >> all.csv",
                   "cut -d , -f 3 all.csv | sort | uniq -c | sort -rn > item_rank.txt"]],
        "expected_files": {"all.csv": _SALES_HEAD + _SALES_IKEBUKURO + _SALES_SHIBUYA + _SALES_UENO,
                           "item_rank.txt": "      4 coffee\n      3 cake\n      1 tea\n      1 sandwich\n",
                           "sales/shibuya.csv": _SALES_HEAD + _SALES_SHIBUYA},
        "hints": ["そのまま cat でつなぐと見出しが3回出てきます。見出しは1回だけ先に書き、データ行はあとから追記します。",
                  'ls と cat で対象の名前・場所・内容を確かめます。head -n 1 で見出しだけを作り、grep -v ^date で見出しを除いたデータ行を >> で足します。grep に複数ファイルを渡すと行頭にファイル名が付くので、cat でまとめてから grep すると安全です。',
                  "head -n 1 sales/shibuya.csv > all.csv → cat sales/*.csv | grep -v ^date >> all.csv → "
                  "grep -v ^date all.csv | cut -d , -f 3 | sort | uniq -c | sort -rn > item_rank.txt"],
        "explanation": "拠点ごとに分かれたデータを1つにまとめるのは、集計前のよくある下ごしらえです。"
                       "見出しの重複やファイル名の混入は、あとで表計算ソフトや別のプログラムに読ませたときのエラーの元になります。",
        "practice": ["2-8", "2-1", "6-5"],
    },
    {
        "id": "fes-logs-23",
        "level": 3,
        "title": "総合：2台のサーバーの障害を時系列にまとめる",
        "brief": 'ログ用フォルダにある2台分の Web サーバーのログから、incident.txt を作ってください。上から (1)「== 障害調査 2026-11-21 ==」(2)「ERROR の時系列」(3) 2台分の ERROR 行を時刻の早い順に並べたもの (4)「種類別の件数」(5) ERROR の種類ごとの件数を多い順に「件数 種類」で保存します。小文字の error を含むだけの INFO 行は入れません。',
        "files": dict(_INCIDENT_LOGS),
        "solution": ['echo "== 障害調査 2026-11-21 ==" > incident.txt',
                     "echo ERROR の時系列 >> incident.txt",
                     "cat logs/*.log | grep ERROR | sort >> incident.txt",
                     "echo 種類別の件数 >> incident.txt",
                     'cat logs/*.log | grep ERROR | cut -d " " -f 5 | sort | uniq -c | sort -rn >> incident.txt'],
        "alt_solutions": [['cat logs/web1.log logs/web2.log | grep ERROR | sort > errors.txt',
                           'echo "== 障害調査 2026-11-21 ==" > incident.txt',
                           "echo ERROR の時系列 >> incident.txt",
                           "cat errors.txt >> incident.txt",
                           "echo 種類別の件数 >> incident.txt",
                           'cut -d " " -f 5 errors.txt | sort | uniq -c | sort -rn >> incident.txt']],
        "traps": [['echo "== 障害調査 2026-11-21 ==" > incident.txt',
                   "echo ERROR の時系列 >> incident.txt",
                   "cat logs/*.log | grep ERROR >> incident.txt",
                   "echo 種類別の件数 >> incident.txt",
                   'cat logs/*.log | grep ERROR | cut -d " " -f 5 | sort | uniq -c | sort -rn >> incident.txt'],
                  ['echo "== 障害調査 2026-11-21 ==" > incident.txt',
                   "echo ERROR の時系列 >> incident.txt",
                   "cat logs/*.log | grep -i error | sort >> incident.txt",
                   "echo 種類別の件数 >> incident.txt",
                   'cat logs/*.log | grep -i error | cut -d " " -f 5 | sort | uniq -c | sort -rn >> incident.txt'],
                  ['echo "== 障害調査 2026-11-21 ==" > incident.txt',
                   "echo ERROR の時系列 >> incident.txt",
                   "grep ERROR logs/*.log | sort >> incident.txt",
                   "echo 種類別の件数 >> incident.txt",
                   'grep ERROR logs/*.log | cut -d " " -f 5 | sort | uniq -c | sort -rn >> incident.txt']],
        "expected_files": {"incident.txt": "== 障害調査 2026-11-21 ==\nERROR の時系列\n"
                                           "2026-11-21 10:02:05 web2 ERROR db timeout\n"
                                           "2026-11-21 10:03:12 web1 ERROR db timeout\n"
                                           "2026-11-21 10:07:40 web1 ERROR db timeout\n"
                                           "2026-11-21 10:10:10 web2 ERROR disk full\n"
                                           "2026-11-21 10:11:00 web2 ERROR db timeout\n"
                                           "2026-11-21 10:12:30 web1 ERROR cache unavailable\n"
                                           "種類別の件数\n"
                                           "      4 db\n      1 disk\n      1 cache\n"},
        "hints": ["2台のログをつなげただけでは、web1 の行が全部終わってから web2 の行が並びます。行の先頭が日付と時刻なら、並べ替えるだけで時系列になります。",
                  "ls と cat で対象の名前・場所・内容を確かめます。cat でまとめて grep ERROR、そのあと sort で時刻順にします。種類は空白区切りの5列目です。grep に複数ファイルを渡すと行頭にファイル名が付き、時刻順に並ばなくなります。",
                  "見出しは echo で書き、1回目だけ > にします。ERROR の時系列は、つなげて grep し sort して >> で追記します。種類別は cut で5列目を取り出し、sort、uniq -c、sort -rn の順に整えて >> で追記します。"],
        "explanation": "複数のサーバーにまたがる障害は、時刻順に並べて初めて「どこで最初に起きたか」が見えます。"
                       "ここでは web2 の db timeout が最初だと分かります。種類別の件数と合わせると、原因の当たりを付けやすくなります。",
        "practice": ["2-5", "2-7", "7-2"],
    },
    {
        "id": "fes-logs-24",
        "level": 3,
        "title": "総合：ローテーションされたログで混雑とエラーの時間帯を調べる",
        "brief": '当日と、ローテーションで別名になった前日のアクセスログを合わせ、peak.txt を作ってください。上から (1)「== 時間帯別アクセス（2日分） ==」(2) 時ごとのアクセス件数を時の早い順に「件数 時」で (3)「== 最も混む時間帯 ==」(4) 件数が最も多い時間帯の1行 (5)「== 5xx が出た時間帯 ==」(6) 500番台の行だけを時ごとに数えたものを時の早い順に保存します。',
        "files": {"access.log": ACCESS, "access.log.1": ACCESS_OLD},
        "solution": ['echo "== 時間帯別アクセス（2日分） ==" > peak.txt',
                     "cat access.log* | cut -d : -f 2 | sort | uniq -c >> peak.txt",
                     'echo "== 最も混む時間帯 ==" >> peak.txt',
                     "cat access.log* | cut -d : -f 2 | sort | uniq -c | sort -rn | head -n 1 >> peak.txt",
                     'echo "== 5xx が出た時間帯 ==" >> peak.txt',
                     'cat access.log* | grep " 5[0-9][0-9] " | cut -d : -f 2 | sort | uniq -c >> peak.txt'],
        "alt_solutions": [["cat access.log.1 access.log > both.log",
                           "cut -d : -f 2 both.log | sort | uniq -c > hours.txt",
                           'echo "== 時間帯別アクセス（2日分） ==" > peak.txt',
                           "cat hours.txt >> peak.txt",
                           'echo "== 最も混む時間帯 ==" >> peak.txt',
                           "sort -n hours.txt | tail -n 1 >> peak.txt",
                           'echo "== 5xx が出た時間帯 ==" >> peak.txt',
                           'grep -E "\\" 5[0-9]{2} " both.log | cut -d : -f 2 | sort | uniq -c >> peak.txt']],
        "traps": [['echo "== 時間帯別アクセス（2日分） ==" > peak.txt',
                   "cut -d : -f 2 access.log | sort | uniq -c >> peak.txt",
                   'echo "== 最も混む時間帯 ==" >> peak.txt',
                   "cut -d : -f 2 access.log | sort | uniq -c | sort -rn | head -n 1 >> peak.txt",
                   'echo "== 5xx が出た時間帯 ==" >> peak.txt',
                   'grep " 5[0-9][0-9] " access.log | cut -d : -f 2 | sort | uniq -c >> peak.txt'],
                  ['echo "== 時間帯別アクセス（2日分） ==" > peak.txt',
                   "cat access.log* | cut -d : -f 2 | uniq -c >> peak.txt",
                   'echo "== 最も混む時間帯 ==" >> peak.txt',
                   "cat access.log* | cut -d : -f 2 | uniq -c | sort -rn | head -n 1 >> peak.txt",
                   'echo "== 5xx が出た時間帯 ==" >> peak.txt',
                   'cat access.log* | grep " 5[0-9][0-9] " | cut -d : -f 2 | uniq -c >> peak.txt'],
                  ['echo "== 時間帯別アクセス（2日分） ==" > peak.txt',
                   "cat access.log* | cut -d : -f 2 | sort | uniq -c >> peak.txt",
                   'echo "== 最も混む時間帯 ==" >> peak.txt',
                   "cat access.log* | cut -d : -f 2 | sort | uniq -c | sort -rn | head -n 1 >> peak.txt",
                   'echo "== 5xx が出た時間帯 ==" >> peak.txt',
                   'cat access.log* | grep " 500 " | cut -d : -f 2 | sort | uniq -c >> peak.txt']],
        "expected_files": {"peak.txt": "== 時間帯別アクセス（2日分） ==\n"
                                       "      3 09\n     11 10\n     10 11\n      5 12\n"
                                       "== 最も混む時間帯 ==\n     11 10\n"
                                       "== 5xx が出た時間帯 ==\n      3 10\n      3 11\n      1 12\n",
                           "access.log.1": ACCESS_OLD},
        "hints": ["ローテーションされたログは名前の後ろに番号が付きます。ワイルドカードの * で両方を指定できます。",
                  "ls と cat で対象の名前・場所・内容を確かめます。2日分をつなげると、時刻の順番が日をまたいで戻ります。集計の前に必ず sort します。最も混む時間帯は、件数表を sort -rn で並べて先頭1行です。500 番台は \" 5[0-9][0-9] \" で探せます。",
                  "見出しは echo で書き、1回目だけ > にします。集計は cat でつなげ、cut の -d : で時の列を取り出し、sort と uniq -c で数えて >> で追記します。5xx は grep で絞ってから同じ集計をします。"],
        "explanation": "ログは容量を抑えるため定期的に別名へ移されます（ローテーション）。当日分だけを見ると傾向を見誤るので、"
                       "古いファイルも含めて集計するのが実務の基本です。混雑とエラーの時間帯が重なっていれば、負荷が原因の障害を疑えます。",
        "practice": ["1-3", "2-7", "6-7", "6-8"],
    },
]
