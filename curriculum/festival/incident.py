"""課題まつり：リモート作業と障害対応。

前半は模擬サーバー training-server への SSH / scp（指紋の照合・ポート・鍵・接続先の確認・転送の向き）。
後半はログ調査・ランキング・プロセス停止・容量確保・設定の退避と修正・障害報告を組み合わせた総合演習。
指紋と鍵は教材専用の架空の値だけを使い、IP は文書用のアドレス範囲だけを使う。
"""
from collections import Counter
from itertools import permutations

PACK_TITLE = "リモート作業と障害対応"

_T = "learner@training-server"
_FP_VALUE = "SHA256:TRAINING-NOT-A-REAL-FINGERPRINT"
_FP = ("# 管理者から別経路で届いた接続先の指紋\n"
       "training-server  ED25519  " + _FP_VALUE + "\n"
       "（教材専用の架空の指紋です）\n")
_FP_CHECK = ["cat fingerprint.txt", "cat -n fingerprint.txt", "cat ./fingerprint.txt"]
_KEY = "DUMMY-NOT-A-REAL-KEY\n"


def _ssh_forms(port=None, key=None):
    """checks_commands 用に、同じ意味の ssh の書き方をまとめて返す。"""
    keys = [key, "./" + key, "/home/learner/" + key] if key else [None]
    forms = []
    for key_path in keys:
        options = []
        if port:
            options.append(["-p", port])
        if key_path:
            options.append(["-i", key_path])
        for order in permutations(options):
            flat = [x for pair in order for x in pair]
            forms.append(" ".join(["ssh", *flat, _T]))
            forms.append(" ".join(["ssh", _T, *flat]))
    return sorted(set(forms))


def _scp_up(source, dest):
    """手元の source をサーバーの dest（ホーム基準）へ送る scp の書き方。"""
    name = source.rsplit("/", 1)[-1]
    sources = {source, "./" + source}
    targets = {f"{_T}:{dest}", f"{_T}:./{dest}", f"{_T}:/home/learner/{dest}"}
    if dest == name:
        targets |= {f"{_T}:.", f"{_T}:./", f"{_T}:/home/learner", f"{_T}:/home/learner/"}
    forms = {f"scp {s} {t}" for s in sources for t in targets}
    if "/" in source:  # 送るファイルのあるフォルダへ cd してから送る書き方
        forms |= {f"scp {name} {t}" for t in targets}
    return sorted(forms)


def _grep_n(text, word):
    return "".join(f"{i}:{line}\n" for i, line in enumerate(text.splitlines(), 1) if word in line)


def _rank(items):
    """sort | uniq -c | sort -rn と同じ表示（同数は作らないデータにしている）。"""
    counts = Counter(items)
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return "".join(f"{count:>7} {value}\n" for value, count in rows)


def _ps_row(p):
    return f"{p['user']:<10} {p['pid']:>5} {p['cpu']:>4.1f} {p['mem']:>4.1f} {p['cmd']}"


# ---- 01 掲示を読む
_NOTICE = "本日のお知らせ\nメンテナンス番号: MT-0412\n作業時間: 02:00-03:00\n"

# ---- 04 受け取り
_APP_0501 = "2024-05-01 02:00:00 INFO 起動\n2024-05-01 02:10:00 ERROR db-timeout\n"

# ---- 05 指紋が届いていない
_FP_PENDING = ("# 管理者から届いた接続先の指紋一覧\n"
               "training-server  （作り直したため、新しい指紋はまだ届いていません。届くまで接続しないでください）\n")

# ---- 06 送る
_CONF_NEW = "# 新しい設定\nport=8080\nworkers=8\n"
_CONF_OLD = "# 古い設定\nport=8080\nworkers=2\n"

# ---- 07 エラー行
_LOG07 = ("2024-05-01 01:58:02 INFO  起動しました\n"
          "2024-05-01 02:00:15 INFO  リクエスト受付 /top\n"
          "2024-05-01 02:03:41 ERROR db-timeout データベースの応答がありません\n"
          "2024-05-01 02:04:10 WARN  再試行します\n"
          "2024-05-01 02:04:12 INFO  retry after error\n"
          "2024-05-01 02:05:33 ERROR db-timeout データベースの応答がありません\n"
          "2024-05-01 02:07:02 ERROR disk-full ログを書き込めません\n"
          "2024-05-01 02:09:45 INFO  リクエスト受付 /login\n")

# ---- 08 障害メモ
_NOTE_HEAD = "# 障害メモ 2024-05-01\n"
_NOTE_LINES = ["02:10 アラート受信", "02:25 原因: ディスク不足", "02:40 復旧を確認"]

# ---- 10 最新ログで数える
_LOG_STALE = "INFO 起動\nERROR db-timeout\nINFO 受付\nERROR db-timeout\n"
_LOG_FRESH = ("INFO 起動\nERROR db-timeout\nERROR db-timeout\nINFO 受付\nERROR upstream-502\n"
              "WARN 遅延\nERROR db-timeout\nERROR disk-full\n")

# ---- 11 IP ランキング
_IP_ORDER = ("203.0.113.5 198.51.100.7 203.0.113.5 192.0.2.10 203.0.113.5 198.51.100.23 203.0.113.5 "
             "198.51.100.7 203.0.113.5 192.0.2.44 203.0.113.5 192.0.2.10 198.51.100.7 203.0.113.5 "
             "198.51.100.23 203.0.113.5 192.0.2.10 203.0.113.5 198.51.100.7 203.0.113.5").split()
_ACCESS11 = "".join(f'{ip} - - [01/May/2024:02:{i:02d}:00 +0900] "GET /index.html HTTP/1.1" 200 512\n'
                    for i, ip in enumerate(_IP_ORDER))
_TOP3 = "".join(_rank(_IP_ORDER).splitlines(keepends=True)[:3])

# ---- 12 エラーの集中した時間帯
_HOURS12 = [("01", "INFO"), ("01", "INFO"), ("01", "ERROR"), ("01", "INFO"), ("02", "ERROR"), ("01", "INFO"),
            ("02", "INFO"), ("03", "ERROR"), ("01", "INFO"), ("03", "ERROR"), ("02", "ERROR"), ("01", "INFO"),
            ("03", "ERROR"), ("03", "INFO"), ("03", "ERROR")]
_LOG12 = "".join(f"2024-05-01 {h}:{10 + i:02d}:00 {lvl} 処理{i}\n" for i, (h, lvl) in enumerate(_HOURS12))
_PEAK = _rank([f"2024-05-01 {h}" for h, lvl in _HOURS12 if lvl == "ERROR"]).splitlines(keepends=True)[0]

# ---- 13 他ユーザーの暴走
_MAILER = {"pid": 5101, "user": "www-data", "cmd": "php-fpm: pool mail-worker", "cpu": 98.5, "mem": 6.0,
           "ignores_term": True}
_WEBPOOL = {"pid": 5102, "user": "www-data", "cmd": "php-fpm: pool web", "cpu": 3.1, "mem": 4.2}

# ---- 14 ローテートされたログ
_ROTATED = {"logs/app.log": "今のログ\n", "logs/app.log.1": "昨日のログ\n" * 200,
            "logs/app.log.2": "2日前のログ\n" * 900, "logs/app.log.3": "3日前のログ\n" * 900,
            "logs/app.log.4": "4日前のログ\n" * 900}

# ---- 15 デバッグ設定の後始末
_CONF15 = ("# 注文アプリの設定\nport=8080\n"
           "debug_dump=/home/learner/dump\n"
           "log_level=debug\nhost=0.0.0.0\n")
_CONF15_FIXED = "# 注文アプリの設定\nport=8080\nlog_level=warn\nhost=0.0.0.0\n"

# ---- 16 サーバーの設定を直して戻す
_SITE = "max_clients=10\ntimeout=5\n"
_SITE_FIXED = "max_clients=200\ntimeout=5\n"

# ---- 17 証拠を残して止める
_LEAK = {"pid": 6200, "user": "learner", "cmd": "node leak-server.js", "cpu": 12.0, "mem": 71.3}
_API = {"pid": 6201, "user": "learner", "cmd": "node api-server.js", "cpu": 2.5, "mem": 3.4}

# ---- 18 容量の原因フォルダ
_CACHE = {"cache/render-001.tmp": "一時データ\n" * 3000, "cache/render-002.tmp": "一時データ\n" * 3000,
          "cache/render-003.tmp": "一時データ\n" * 3000, "cache/index.db": "索引データ\n",
          "data/orders.csv": "id,item\n1,りんご\n", "logs/current.log": "今のログ\n"}

# ---- 19 深夜2時のアラート
_LOG19 = ("02:00:01 INFO request /top\n"
          "02:01:10 ERROR db-timeout 応答なし\n"
          "02:01:30 WARN slow query\n"
          "02:02:05 ERROR upstream-502 上流の応答エラー\n"
          "02:02:40 ERROR db-timeout 応答なし\n"
          "02:03:00 INFO request /cart\n"
          "02:03:12 ERROR disk-full 書き込み失敗\n"
          "02:04:55 ERROR db-timeout 応答なし\n"
          "02:05:20 ERROR upstream-502 上流の応答エラー\n"
          "02:06:00 ERROR db-timeout 応答なし\n"
          "02:06:30 INFO request /login\n")
_RANK19 = _rank([line.split()[2] for line in _LOG19.splitlines() if "ERROR" in line])
_BATCH = {"pid": 7001, "user": "learner", "cmd": "python3 report-batch.py --all", "cpu": 99.0, "mem": 20.5,
          "ignores_term": True}
_WEBAPP = {"pid": 7002, "user": "learner", "cmd": "python3 web-app.py", "cpu": 4.0, "mem": 8.0}
_RSYNC = {"pid": 7003, "user": "learner", "cmd": "rsync -a uploads/ backup/", "cpu": 2.0, "mem": 1.0}

# ---- 20 ディスク満杯
_CONF20 = "# Web アプリ設定\nport=8080\nlog_level=debug\nlog_dir=/home/learner/logs\n"
_CONF20_FIXED = _CONF20.replace("log_level=debug", "log_level=info")
_LOGS20 = {"logs/app.log": "今のログ\n", "logs/app.log.1": "昨日のログ\n" * 300,
           "logs/app.log.2": "DEBUG 詳細ログ\n" * 1500, "logs/app.log.3": "DEBUG 詳細ログ\n" * 1500}

# ---- 21 リモートの障害
_LOG21_REMOTE = ("02:10:00 INFO request /top\n"
                 "02:11:00 ERROR upstream-502 上流の応答エラー\n"
                 "02:12:00 ERROR cert-expired 証明書の期限切れ\n"
                 "02:13:00 ERROR upstream-502 上流の応答エラー\n"
                 "02:14:00 INFO request /cart\n"
                 "02:15:00 ERROR upstream-502 上流の応答エラー\n")
_LOG21_STALE = "01:00:00 INFO request /top\n01:05:00 ERROR db-timeout 応答なし\n"
_ERR21 = _grep_n(_LOG21_REMOTE, "ERROR")
_RANK21 = _rank([line.split()[2] for line in _LOG21_REMOTE.splitlines() if "ERROR" in line])

# ---- 22 ロールバック
_CONF22_GOOD = "# 店舗サイト設定\nport=8080\nworkers=4\n"
_CONF22_BROKEN = "# 店舗サイト設定\nport=8O80\nworkers=4\ncache=on\n"
_CONF22_FINAL = _CONF22_GOOD + "cache=on\n"

# ---- 23 不審なアクセス
_REQ23 = ([("198.51.100.7", "GET /items", 200)] * 3 + [("203.0.113.66", "POST /login", 401)] * 2
          + [("192.0.2.10", "POST /login", 401), ("198.51.100.7", "GET /cart", 200)]
          + [("203.0.113.66", "POST /login", 401)] * 2 + [("198.51.100.7", "GET /items", 200)] * 3
          + [("192.0.2.10", "GET /items", 200)] * 3 + [("198.51.100.23", "POST /login", 401)]
          + [("203.0.113.66", "POST /login", 401)] * 2 + [("192.0.2.10", "POST /login", 401)]
          + [("198.51.100.7", "GET /items", 200)] * 2)
_ACCESS23 = "".join(f'{ip} - - [01/May/2024:03:{i:02d}:00 +0900] "{req} HTTP/1.1" {code} 128\n'
                    for i, (ip, req, code) in enumerate(_REQ23))
_SUSPECT = _rank([ip for ip, _, code in _REQ23 if code == 401])

# ---- 24 総仕上げ
_LOG24_REMOTE = ("04:00:00 INFO export start\n"
                 "04:01:00 ERROR export-timeout 書き出しが終わりません\n"
                 "04:02:00 ERROR db-lock 表がロックされています\n"
                 "04:03:00 ERROR export-timeout 書き出しが終わりません\n"
                 "04:04:00 WARN memory high\n"
                 "04:05:00 ERROR export-timeout 書き出しが終わりません\n")
_RANK24 = _rank([line.split()[2] for line in _LOG24_REMOTE.splitlines() if "ERROR" in line])
_EXPORT = {"pid": 8101, "user": "root", "cmd": "/usr/bin/python3 /opt/export.py", "cpu": 99.5, "mem": 30.0,
           "ignores_term": True}
_NGINX = {"pid": 8102, "user": "www-data", "cmd": "nginx: worker process", "cpu": 1.0, "mem": 2.0}
_CONF24 = "# 書き出し設定\nmax_connections=10\nexport_dir=/home/learner/export\n"
_CONF24_FIXED = _CONF24.replace("max_connections=10", "max_connections=100")
_LOGS24 = {"logs/export.log": "今のログ\n", "logs/export.log.1": "昨日のログ\n" * 200,
           "logs/export.log.2": "古いログ\n" * 1200, "logs/export.log.3": "古いログ\n" * 1200}


SCENARIOS = [
    # ================= ★1 =================
    {
        "id": "fes-incident-01",
        "level": 1,
        "title": "サーバーの掲示を読んで手元に控える",
        "brief": '管理者から届いた指紋の記録を見つけ、接続時の表示と比べてから training-server に learner として接続してください。サーバーの掲示を読み、メンテナンス番号（MT- で始まる値）だけを、手元の maint-id.txt に1行で控えます。最後は手元へ戻ってください。',
        "files": {"fingerprint.txt": _FP},
        "remote_files": {"notice.txt": _NOTICE},
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "hostname", "cat notice.txt", "exit",
                     "hostname", "echo MT-0412 > maint-id.txt"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:notice.txt notice.txt",
             "grep MT- notice.txt | cut -d ' ' -f 2 > maint-id.txt"],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "cat notice.txt", "echo MT-0412 > maint-id.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "cat notice.txt", "echo MT-0412 > maint-id.txt", "exit"],
        ],
        "expected_files": {"maint-id.txt": "MT-0412\n"},
        "checks_commands": [_FP_CHECK],
        "require_disconnected": True,
        "hints": ["サーバーで読んだ内容は、手元に戻ってから手元のファイルに書きます。プロンプトのホスト名に注目しましょう。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。cat で指紋を読む → ssh で接続して一致を確かめ yes → cat で掲示を読む → exit で戻る、の順です。',
                  "手元に戻ってから echo MT-0412 > maint-id.txt。サーバーにいるまま書くと、サーバー側にファイルができます。"],
        "explanation": "SSH で接続している間のコマンドは、すべて相手のサーバーで動きます。同じ「ファイルを作る」でも、"
                       "どちらの機械にいるかで保存先が変わります。作業の前後にプロンプトや hostname で今いる場所を確かめる習慣が、"
                       "取り違え事故を防ぎます。",
        "practice": ["4-7", "1-1", "2-1"],
    },
    {
        "id": "fes-incident-02",
        "level": 1,
        "title": "決められたポートで入って、戻る",
        "brief": 'training-server へ learner として、SSH の2222番ポートで接続します。管理者から届いた指紋の記録と表示を比べてから接続し、接続先のコンピューター名を確かめてください。最後は手元へ戻り、手元のコンピューター名も確かめます。',
        "files": {"fingerprint.txt": _FP},
        "solution": ["cat fingerprint.txt", f"ssh -p 2222 {_T}", "yes", "hostname", "exit", "hostname"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T} -p 2222", "yes", "pwd", "hostname", "exit", "hostname"],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "hostname", "exit", "hostname"],
            ["cat fingerprint.txt", f"ssh -p 2222 {_T}", "yes", "hostname"],
        ],
        "checks_commands": [_FP_CHECK, _ssh_forms(port="2222"), "hostname"],
        "require_disconnected": True,
        "hints": ["ポートの指定は ssh のオプションで行います。戻ったあとの確認も条件です。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。ssh -p ポート番号 ユーザー@ホスト の形です。接続後は hostname、戻るのは exit です。',
                  "cat fingerprint.txt → ssh -p 2222 learner@training-server → yes → hostname → exit → hostname。"],
        "explanation": "外部からの攻撃を減らすため、SSH を 22 番以外のポートで受け付けるサーバーは珍しくありません。"
                       "ポートを間違えると Connection refused になります。また、戻ったつもりで本番サーバーに残っている事故を防ぐため、"
                       "exit のあとにも hostname で確かめます。",
        "practice": ["4-7", "4-6"],
    },
    {
        "id": "fes-incident-03",
        "level": 1,
        "title": "鍵の権限を直してから鍵で入る",
        "brief": '用意された訓練用の鍵（無効な教材用ダミー）を使い、training-server に learner として接続してください。鍵の権限を自分だけが読み書きできる状態に直し、鍵を指定して接続し、確認が済んだら手元に戻ります。鍵の中身は変えません。接続前に管理者から届いた指紋と照合します。',
        "files": {"fingerprint.txt": _FP, "keys/training_key": _KEY},
        "solution": ["ls -l keys", "chmod 600 keys/training_key", "cat fingerprint.txt",
                     f"ssh -i keys/training_key {_T}", "yes", "hostname", "exit"],
        "alt_solutions": [
            ["cat fingerprint.txt", "cd keys", "chmod 600 training_key", "ls -l", "cd ..",
             f"ssh {_T} -i keys/training_key", "yes", "exit"],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh -i keys/training_key {_T}", "yes", "exit"],
            ["chmod 755 keys/training_key", "cat fingerprint.txt", f"ssh -i keys/training_key {_T}", "yes", "exit"],
            ["chmod 600 keys/training_key", "cat fingerprint.txt", f"ssh -i keys/training_key {_T}", "yes"],
        ],
        "expected_files": {"keys/training_key": _KEY},
        "expected_modes": {"keys/training_key": 0o600},
        "checks_commands": [_FP_CHECK, _ssh_forms(key="keys/training_key")],
        "require_disconnected": True,
        "hints": ['鍵の名前や場所も自分で調べます。対象と権限を確かめてから接続し、接続先と手元を取り違えないようにしましょう。',
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。秘密鍵は「自分だけ読み書きできる」600 にします。鍵の指定は ssh の -i オプションです。',
                  "chmod 600 keys/training_key → ssh -i keys/training_key learner@training-server → yes → exit。"],
        "explanation": "ssh は、ほかの人も読める秘密鍵を危険とみなして使いません（UNPROTECTED PRIVATE KEY FILE）。"
                       "鍵を受け取ったりコピーしたりしたら、まず chmod 600 にするのが定番です。本物の秘密鍵は人に渡したり画面に貼ったりしません。",
        "practice": ["4-7", "3-1"],
    },
    {
        "id": "fes-incident-04",
        "level": 1,
        "title": "サーバーのログを受け取りフォルダへ",
        "brief": 'training-server に learner として接続し、調査用のアプリのログを探してください。手元の受け取り用フォルダへ同じ名前でコピーします。接続先は管理者から届いた指紋と照合し、転送は手元に戻って行います。最後も手元にいる状態で終えます。',
        "files": {"fingerprint.txt": _FP, "incoming/README.txt": "サーバーから受け取ったファイルを置く場所です。\n"},
        "remote_files": {"logs/app-0501.log": _APP_0501},
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "ls logs", "exit",
                     f"scp {_T}:logs/app-0501.log incoming/"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:logs/app-0501.log incoming/app-0501.log"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", "cd incoming",
             f"scp {_T}:/home/learner/logs/app-0501.log ."],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", f"scp {_T}:logs/app-0501.log incoming/"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:logs/app-0501.log app-0501.log"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp incoming/README.txt {_T}:logs/"],
        ],
        "expected_files": {"incoming/app-0501.log": _APP_0501},
        "checks_commands": [_FP_CHECK],
        "require_disconnected": True,
        "hints": ["scp は「コピー元 → コピー先」の順に書き、サーバー側だけに ユーザー@ホスト: を付けます。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。受け取るときはサーバー側が先です。送り先にフォルダを書くと、同じ名前でその中に入ります。',
                  "接続して確かめ exit したあと、scp learner@training-server:logs/app-0501.log incoming/ を実行します。"],
        "explanation": "scp は cp と同じく「元 先」の順で、遠い側を ユーザー@ホスト:パス で表します。"
                       "向きを逆にすると、取り寄せるつもりが送ってしまったり、手元のファイルを上書きしたりします。"
                       "置き場所を決めておくと、あとで調査資料を探しやすくなります。",
        "practice": ["4-8", "1-4"],
    },
    {
        "id": "fes-incident-05",
        "level": 1,
        "title": "指紋が確かめられないときは接続しない",
        "brief": 'training-server が作り直されたと連絡がありました。管理者から届いた指紋一覧を読み、learner として接続を試みて表示される指紋と比べてください。確かめられなければ接続を中止します。表示された指紋（SHA256:から始まる値）だけを、手元の hold.txt に1行で記録してください。',
        "files": {"fingerprint-list.txt": _FP_PENDING},
        "solution": ["cat fingerprint-list.txt", f"ssh {_T}", "no", f"echo {_FP_VALUE} > hold.txt"],
        "alt_solutions": [
            ["cat fingerprint-list.txt", f"ssh -p 22 {_T}", "no", f"echo '{_FP_VALUE}' >> hold.txt", "cat hold.txt"],
        ],
        "traps": [
            ["cat fingerprint-list.txt", f"ssh {_T}", "yes", f"echo {_FP_VALUE} > hold.txt"],
            ["cat fingerprint-list.txt", f"ssh {_T}", "no", "echo SHA256 > hold.txt"],
        ],
        "expected_codes": {"no": 255},
        "expected_files": {"hold.txt": _FP_VALUE + "\n", "fingerprint-list.txt": _FP_PENDING},
        "checks_commands": [["cat fingerprint-list.txt", "cat -n fingerprint-list.txt"], [f"ssh {_T}", f"ssh -p 22 {_T}"]],
        "require_disconnected": True,
        "hints": ["接続確認の質問には、指紋が一致すると確認できたときだけ yes と答えます。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。一覧に training-server の指紋がないなら、yes ではなく no で中止します。表示された値は画面に残っています。',
                  "ssh learner@training-server → no → echo SHA256:TRAINING-NOT-A-REAL-FINGERPRINT > hold.txt。"],
        "explanation": "初回接続の指紋確認は、なりすましサーバーにつながっていないかを見分ける唯一の機会です。"
                       "「いつも yes で進む」癖は、パスワードを攻撃者に渡す入口になります。確かめられないときは中止し、"
                       "見えた値を記録して管理者に照会するのが正しい対応です。",
        "practice": ["4-7", "2-1"],
    },
    {
        "id": "fes-incident-06",
        "level": 1,
        "title": "直した設定をサーバーへ送る",
        "brief": '手元にあるレビュー済みの新しいアプリ設定を探し、training-server の learner のホーム直下に app.conf という名前で送ってください。サーバーの古い設定で手元の新しいものを上書きしないよう、向きに注意します。接続先は管理者から届いた指紋と照合し、最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP, "release/app.conf": _CONF_NEW},
        "remote_files": {"app.conf": _CONF_OLD},
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "cat app.conf", "exit",
                     f"scp release/app.conf {_T}:app.conf"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", "cd release", f"scp app.conf {_T}:app.conf", "cd .."],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp release/app.conf {_T}:/home/learner/"],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:app.conf release/app.conf"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", f"scp release/app.conf {_T}:app.conf"],
        ],
        "expected_files": {"release/app.conf": _CONF_NEW},
        "checks_commands": [_FP_CHECK, _scp_up("release/app.conf", "app.conf")],
        "require_disconnected": True,
        "hints": ["送るときは、手元のファイルが先、サーバー側が後ろです。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。scp 手元のパス learner@training-server:サーバーのパス の形です。scp は手元で実行します。',
                  "接続して確かめ exit したあと、scp release/app.conf learner@training-server:app.conf。"],
        "explanation": "アップロードとダウンロードは、引数の順番が入れ替わるだけです。逆向きに打つと、"
                       "せっかく直した手元の設定が古いもので上書きされます。送る前に「元はどっち、先はどっち」と声に出すくらいの慎重さが役立ちます。",
        "practice": ["4-8", "1-5"],
    },
    {
        "id": "fes-incident-07",
        "level": 1,
        "title": "エラー行を行番号つきで抜き出す",
        "brief": 'アプリのログから、大文字の ERROR を含む行だけを行番号つきで errors.txt に保存してください。小文字の error を含むだけの行は入れず、元のログは変更しません。',
        "files": {"logs/app.log": _LOG07},
        "solution": ["grep -n ERROR logs/app.log > errors.txt", "cat errors.txt"],
        "alt_solutions": [
            ["cd logs", "grep -n ERROR app.log > ../errors.txt", "cd .."],
            ["cat logs/app.log | grep -n ERROR > errors.txt"],
        ],
        "traps": [
            ["grep ERROR logs/app.log > errors.txt"],
            ["grep -in ERROR logs/app.log > errors.txt"],
            ["cat -n logs/app.log | grep ERROR > errors.txt"],
        ],
        "expected_files": {"errors.txt": _grep_n(_LOG07, "ERROR"), "logs/app.log": _LOG07},
        "hints": ["文字を含む行を探すのは grep です。行番号を付けるオプションがあります。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。grep の -n で「行番号:行」の形になります。大文字小文字を無視する -i は今回は使いません。',
                  "grep -n ERROR logs/app.log > errors.txt。"],
        "explanation": "障害報告では「何行目に出ていたか」が重要な手がかりになります。行番号があれば、"
                       "前後の行を見に戻ったり、ほかの人に場所を伝えたりできます。-i は便利ですが、拾いすぎることもあります。",
        "practice": ["2-1", "2-6"],
    },
    {
        "id": "fes-incident-08",
        "level": 1,
        "title": "障害メモを上書きせずに書き足す",
        "brief": '障害メモには見出しが1行だけあります。それを残したまま「02:10 アラート受信」「02:25 原因: ディスク不足」「02:40 復旧を確認」の3行を、この順で書き足してください。',
        "files": {"incident-note.txt": _NOTE_HEAD},
        "initial_packages": ["vim"],
        "solution": [f"echo '{line}' >> incident-note.txt" for line in _NOTE_LINES] + ["cat incident-note.txt"],
        "alt_solutions": [
            ["vim incident-note.txt", "G", "o", *_NOTE_LINES, "esc", ":wq"],
            [f'echo "{line}" >> incident-note.txt' for line in _NOTE_LINES],
        ],
        "traps": [
            [f"echo '{line}' > incident-note.txt" for line in _NOTE_LINES],
            [f"echo '{line}' >> incident-note.txt" for line in reversed(_NOTE_LINES)],
            ["vim incident-note.txt", "G", "o", *_NOTE_LINES, "esc", ":q!"],
        ],
        "expected_files": {"incident-note.txt": _NOTE_HEAD + "".join(x + "\n" for x in _NOTE_LINES)},
        "hints": ["> は上書き、>> は書き足しです。空白を含む文は引用符で囲みます。",
                  "ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。echo '文' >> ファイル を3回、書く順番どおりに実行します。vim で末尾に書き足しても構いません。",
                  "echo '02:10 アラート受信' >> incident-note.txt のように3行続けて追記します。"],
        "explanation": "障害対応中のメモは、時刻順に事実を積み上げていく記録です。> と >> を取り違えると、それまでの記録が一瞬で消えます。"
                       "報告書は後で原因分析や再発防止に使われるので、上書きしない書き方を手に覚えさせておきます。",
        "practice": ["2-6", "1-3"],
    },
    # ================= ★2 =================
    {
        "id": "fes-incident-09",
        "level": 2,
        "title": "鍵とポートで入り、居場所の証拠を持ち帰る",
        "brief": 'training-server へ learner として2222番ポートで接続します。用意された訓練用の鍵を探し、使える権限に整えて指定してください。管理者から届いた指紋とも照合します。サーバー上の whereami.txt に、1行目にコンピューター名、2行目に現在地のパスを記録し、手元へ remote-whereami.txt として持ち帰ります。最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP, "keys/ops_key": _KEY},
        "solution": ["chmod 600 keys/ops_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/ops_key {_T}", "yes",
                     "hostname > whereami.txt", "pwd >> whereami.txt", "cat whereami.txt", "exit",
                     f"scp {_T}:whereami.txt remote-whereami.txt", "cat remote-whereami.txt"],
        "alt_solutions": [
            ["cat fingerprint.txt", "chmod 600 keys/ops_key", f"ssh -i keys/ops_key -p 2222 {_T}", "yes",
             "hostname >> whereami.txt", "pwd >> whereami.txt", "exit",
             f"scp {_T}:/home/learner/whereami.txt remote-whereami.txt"],
        ],
        "traps": [
            ["chmod 600 keys/ops_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/ops_key {_T}", "yes", "exit",
             "hostname > remote-whereami.txt", "pwd >> remote-whereami.txt"],
            ["chmod 600 keys/ops_key", "cat fingerprint.txt", f"ssh -i keys/ops_key {_T}", "yes",
             "hostname > whereami.txt", "pwd >> whereami.txt", "exit", f"scp {_T}:whereami.txt remote-whereami.txt"],
            ["chmod 600 keys/ops_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/ops_key {_T}", "yes",
             "pwd > whereami.txt", "hostname >> whereami.txt", "exit", f"scp {_T}:whereami.txt remote-whereami.txt"],
        ],
        "expected_files": {"remote-whereami.txt": "training-server\n/home/learner\n", "keys/ops_key": _KEY},
        "expected_modes": {"keys/ops_key": 0o600},
        "checks_commands": [_FP_CHECK, _ssh_forms(port="2222", key="keys/ops_key")],
        "require_disconnected": True,
        "hints": ['鍵の名前や場所も自分で調べます。対象と権限を確かめてから接続し、接続先と手元を取り違えないようにしましょう。',
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。hostname と pwd の結果は > と >> でファイルに残せます。ssh の -p と -i は同時に使えます。',
                  "chmod 600 keys/ops_key → ssh -p 2222 -i keys/ops_key learner@training-server → yes → hostname > whereami.txt → pwd >> whereami.txt → exit → scp learner@training-server:whereami.txt remote-whereami.txt。"],
        "explanation": "「確かにそのサーバーで作業した」という証拠を残すのは、変更作業の記録の基本です。"
                       "手元で hostname を実行すると dojo-local になり、証拠になりません。ポート・鍵・ユーザーを1行の ssh にまとめて書けると、"
                       "実際の運用手順書もそのまま読めるようになります。",
        "practice": ["4-7", "4-8", "3-1"],
    },
    {
        "id": "fes-incident-10",
        "level": 2,
        "title": "サーバーの最新ログでエラーを数える",
        "brief": '手元のアプリのログは昨日の写しなので比較用に残します。training-server に learner として接続し、最新のアプリのログで ERROR を含む行数を調べ、数字だけを手元の error-count.txt に保存してください。接続先は管理者から届いた指紋と照合し、最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP, "app.log": _LOG_STALE},
        "remote_files": {"app.log": _LOG_FRESH},
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "grep -c ERROR app.log > error-count.txt", "exit",
                     f"scp {_T}:error-count.txt error-count.txt", "cat error-count.txt"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:app.log server-app.log",
             "grep -c ERROR server-app.log > error-count.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "grep ERROR app.log | wc -l > count.txt", "exit",
             f"scp {_T}:count.txt error-count.txt"],
        ],
        "traps": [
            ["grep -c ERROR app.log > error-count.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:app.log app.log",
             "grep -c ERROR app.log > error-count.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "grep -c ERROR app.log > error-count.txt"],
        ],
        "expected_files": {"error-count.txt": "5\n", "app.log": _LOG_STALE},
        "checks_commands": [_FP_CHECK],
        "require_disconnected": True,
        "hints": ['同じ名前の 対象のファイル が手元とサーバーの両方にあります。どちらを数えるべきでしょうか。',
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。サーバー上で数えて結果を持ち帰るか、サーバーのログを別名で取り寄せて手元で数えます。数えるのは grep -c です。',
                  "接続して grep -c ERROR app.log > error-count.txt → exit → scp learner@training-server:error-count.txt error-count.txt。"],
        "explanation": "障害調査で一番多い失敗の一つが「古いコピーを調べていた」です。同じ名前のファイルが複数の機械にあるときは、"
                       "どの機械のどの時点のものかを意識します。取り寄せるときも、手元の比較用ファイルを上書きしないよう別名にします。",
        "practice": ["2-1", "4-8", "2-7"],
    },
    {
        "id": "fes-incident-11",
        "level": 2,
        "title": "アクセスの多い IP 上位3件を出す",
        "brief": 'アクセスログの各行の先頭は、アクセス元 IP です。IP ごとのアクセス回数を数え、多い順の上位3件を top-ip.txt に保存してください。各行は「回数 IP」の形（uniq -c の表示のまま）にします。',
        "files": {"access.log": _ACCESS11},
        "solution": ["head -3 access.log", "cut -d ' ' -f 1 access.log | sort | uniq -c | sort -rn | head -3 > top-ip.txt",
                     "cat top-ip.txt"],
        "alt_solutions": [
            ["cat access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn | head -n 3 > top-ip.txt"],
            ["cut -d ' ' -f 1 access.log | sort | uniq -c | sort -rn > all-ip.txt", "head -3 all-ip.txt > top-ip.txt"],
        ],
        "traps": [
            ["cut -d ' ' -f 1 access.log | uniq -c | sort -rn | head -3 > top-ip.txt"],
            ["cut -d ' ' -f 1 access.log | sort | uniq -c | head -3 > top-ip.txt"],
            ["head -3 access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > top-ip.txt"],
        ],
        "expected_files": {"top-ip.txt": _TOP3, "access.log": _ACCESS11},
        "hints": ["列を取り出す → 並べる → 数える → 多い順に並べ直す → 先頭だけ、をパイプでつなぎます。",
                  "ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。cut -d ' ' -f 1 で IP、uniq -c は隣り合う同じ行しかまとめないので、その前に sort が必要です。",
                  "cut -d ' ' -f 1 access.log | sort | uniq -c | sort -rn | head -3 > top-ip.txt。"],
        "explanation": "sort | uniq -c | sort -rn は、ログから「何が一番多いか」を出す定番の組み合わせです。"
                       "最初の sort を忘れると、同じ IP がばらばらに数えられて順位が狂います。攻撃元の特定や負荷の原因調査で毎日のように使います。",
        "practice": ["2-2", "2-7", "2-6"],
    },
    {
        "id": "fes-incident-12",
        "level": 2,
        "title": "エラーが集中した時間帯を突き止める",
        "brief": '管理者から届いた接続先の指紋を確認し、training-server（SSH port 22）の表示と照合してから learner として接続してください。アプリのログを探して手元に取り寄せ、ERROR がいちばん多かった「時」を調べます。各行は「日付 時:分:秒 レベル …」です。「日付 時」ごとの ERROR 件数ランキングの1位だけを、uniq -c の表示のまま peak.txt に保存します。最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP},
        "remote_files": {"logs/app.log": _LOG12},
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:logs/app.log server-app.log",
                     "grep ERROR server-app.log | cut -d ':' -f 1 | sort | uniq -c | sort -rn | head -1 > peak.txt"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes",
             "grep ERROR logs/app.log | cut -d ':' -f 1 | sort | uniq -c | sort -rn | head -1 > peak.txt", "exit",
             f"scp {_T}:peak.txt peak.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:logs/app.log app.log",
             "grep ERROR app.log | cut -d ':' -f 1 | sort | uniq -c | sort -rn > hours.txt", "head -n 1 hours.txt > peak.txt"],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:logs/app.log server-app.log",
             "cut -d ':' -f 1 server-app.log | sort | uniq -c | sort -rn | head -1 > peak.txt"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes",
             "grep ERROR logs/app.log | cut -d ':' -f 1 | sort | uniq -c | sort -rn | head -1 > peak.txt"],
        ],
        "expected_files": {"peak.txt": _PEAK},
        "checks_commands": [_FP_CHECK],
        "require_disconnected": True,
        "hints": ["「時」までを取り出すには、: を区切りにした1列目が使えます。全体の行数ではなく ERROR だけを数えます。",
                  "ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。grep ERROR → cut -d ':' -f 1 → sort → uniq -c → sort -rn → head -1 の順につなぎます。",
                  "scp でログを取り寄せ、grep ERROR server-app.log | cut -d ':' -f 1 | sort | uniq -c | sort -rn | head -1 > peak.txt。"],
        "explanation": "エラーが「いつ」増えたかが分かると、その時刻に何が起きたか（リリース、バッチ、アクセス集中）と結び付けられます。"
                       "区切り文字を変えれば、cut で時刻の一部だけを切り出せます。絞り込み（grep）を先にしないと、普通のアクセスが多い時間帯を拾ってしまいます。",
        "practice": ["2-2", "2-7", "4-8"],
    },
    {
        "id": "fes-incident-13",
        "level": 2,
        "title": "他ユーザーの暴走プロセスを段階を踏んで止める",
        "brief": "メール送信用の php-fpm（mail-worker）が CPU を使い切っています。これは www-data ユーザーのプロセスです。"
                 "まず通常の停止要求（TERM）を送り、止まらなかったときだけ強制終了してください。"
                 "同じ php-fpm でも Web 用の pool web や、sshd・cron は止めてはいけません。",
        "processes": [_MAILER, _WEBPOOL],
        "solution": ["ps aux", "sudo kill 5101", "ps aux", "sudo kill -9 5101", "ps aux"],
        "alt_solutions": [
            ["pgrep mail-worker", "sudo kill -TERM 5101", "pgrep mail-worker", "sudo kill -KILL 5101"],
            ["ps aux | grep php-fpm", "sudo kill -15 5101", "ps aux | grep mail-worker", "sudo kill -9 5101"],
        ],
        "traps": [
            ["ps aux", "sudo kill -9 5101"],
            ["ps aux", "sudo kill 5101 5102", "sudo kill -9 5101 5102"],
            ["ps aux", "kill 5101", "kill -9 5101"],
        ],
        "process_gone": ["pool mail-worker"],
        "process_kept": ["pool web", "sshd", "cron"],
        "checks_commands": [["sudo kill 5101", "sudo kill -15 5101", "sudo kill -TERM 5101", "sudo kill -SIGTERM 5101",
                             "sudo kill -s TERM 5101"]],
        "hints": ["自分以外のユーザーのプロセスは、そのままでは止められません。名前の似たプロセスに注意しましょう。",
                  "ps aux で PID を確かめ、sudo を付けて kill します。止まったかを確かめてから -9 を使います。",
                  "sudo kill 5101 → ps aux で残っているのを確認 → sudo kill -9 5101。5102 は止めません。"],
        "explanation": "TERM はプロセスに後片付けの時間を与える「お願い」で、-9 は問答無用の強制終了です。"
                       "いきなり -9 を使うと書きかけのデータが壊れることがあるので、まず TERM、だめなら -9 の順にします。"
                       "似た名前のプロセスをまとめて止めると、無関係なサービスまで落とす二次障害になります。",
        "practice": ["3-5", "3-7", "7-1"],
    },
    {
        "id": "fes-incident-14",
        "level": 2,
        "title": "ローテートされた古いログだけを片付ける",
        "brief": 'ディスクの空きが少なくなっています。まず全体の空きを確認してください。アプリのログ用フォルダを見つけ、書き込み中のログと直近の1世代は残し、それより古い世代だけを削除してください。',
        "files": dict(_ROTATED),
        "solution": ["df -h", "du -sh logs", "ls -l logs", "rm logs/app.log.2 logs/app.log.3 logs/app.log.4", "du -sh logs"],
        "alt_solutions": [
            ["df -h", "rm logs/app.log.[2-4]", "ls logs"],
            ["df -h", "cd logs", "rm app.log.2", "rm app.log.3", "rm app.log.4", "cd .."],
        ],
        "traps": [
            ["df -h", "rm logs/app.log.*"],
            ["df -h", "rm logs/app.log*"],
            ["rm logs/app.log.2 logs/app.log.3 logs/app.log.4"],
        ],
        "absent": ["logs/app.log.2", "logs/app.log.3", "logs/app.log.4"],
        "expected_files": {"logs/app.log": _ROTATED["logs/app.log"], "logs/app.log.1": _ROTATED["logs/app.log.1"]},
        "checks_commands": [["df -h", "df"]],
        "hints": ["消す前に容量を確かめ、消す対象を ls で一覧して、残すものが含まれないか考えます。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。app.log.* は app.log.1 も含みます。番号を並べるか、[2-4] のような範囲指定を使います。',
                  "df -h → rm logs/app.log.2 logs/app.log.3 logs/app.log.4。"],
        "explanation": "ログは日ごとに app.log.1、app.log.2 … と名前を変えて保管されます（ローテート）。"
                       "直近の世代は障害調査で見返すことが多いので残し、古いものから消すのが基本です。"
                       "ワイルドカードは便利な反面、一致する範囲を一文字の違いで広げてしまいます。",
        "practice": ["3-8", "2-6", "7-2"],
    },
    {
        "id": "fes-incident-15",
        "level": 2,
        "title": "調査用のデバッグ設定を後片付けする",
        "brief": 'アプリの設定に調査用の指定が残っています。編集前の内容を app.conf.bak に残し、debug_dump の行を削除して log_level を warn に変えてください。ほかの行と順番はそのままにします。',
        "files": {"app.conf": _CONF15},
        "initial_packages": ["vim"],
        "solution": ["cp app.conf app.conf.bak", "vim app.conf", "/debug_dump", "dd", ":%s/log_level=debug/log_level=warn/",
                     ":wq", "cat app.conf"],
        "alt_solutions": [
            ["cp app.conf app.conf.bak", "grep -v debug_dump app.conf.bak > app.conf", "vim app.conf",
             ":%s/=debug/=warn/g", ":wq"],
            ["cp app.conf app.conf.bak", "vim app.conf", ":3", "dd", ":s/debug/warn/", "ZZ"],
        ],
        "traps": [
            ["vim app.conf", "/debug_dump", "dd", ":%s/log_level=debug/log_level=warn/", ":wq", "cp app.conf app.conf.bak"],
            ["cp app.conf app.conf.bak", "vim app.conf", ":%s/debug/warn/g", ":wq"],
            ["cp app.conf app.conf.bak", "vim app.conf", "/debug_dump", "dd", ":%s/log_level=debug/log_level=warn/", ":q!"],
        ],
        "expected_files": {"app.conf": _CONF15_FIXED, "app.conf.bak": _CONF15},
        "hints": ["順番は「退避 → 編集」です。行の削除と文字の置き換えの2つの操作が必要です。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。vim では /文字 で行を探し、dd でその行を削除、:%s/前/後/ で置き換え、:wq で保存します。',
                  "cp app.conf app.conf.bak → vim app.conf → /debug_dump → dd → :%s/log_level=debug/log_level=warn/ → :wq。"],
        "explanation": "調査のために入れたデバッグ設定は、消し忘れるとディスクを埋めたり、内部情報をログに出したりします。"
                       "置き換えの対象を広く取りすぎる（debug をすべて warn にする）と、消すべき行が別の値に化けて残ります。"
                       "変える範囲を正確に指定するのが設定編集のコツです。",
        "practice": ["6-6", "1-5", "2-1"],
    },
    {
        "id": "fes-incident-16",
        "level": 2,
        "title": "サーバーの設定を取り寄せ、直して送り返す",
        "brief": '管理者から届いた接続先の指紋を確認し、training-server（SSH port 22）の表示と照合してから learner として接続してください。Web サイト設定で max_clients=10 が少なすぎます。設定を探し、手元に同じ名前で取り寄せます。変更前の内容を site.conf.orig に残し、max_clients=200 に直してサーバーの元の場所へ送り返してください。timeout の行は変えず、最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP},
        "remote_files": {"site.conf": _SITE},
        "initial_packages": ["vim"],
        "solution": ["cat fingerprint.txt", f"ssh {_T}", "yes", "cat site.conf", "exit", f"scp {_T}:site.conf site.conf",
                     "cp site.conf site.conf.orig", "vim site.conf", ":%s/max_clients=10/max_clients=200/", ":wq",
                     f"scp site.conf {_T}:site.conf"],
        "alt_solutions": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:site.conf site.conf.orig",
             "echo max_clients=200 > site.conf", "echo timeout=5 >> site.conf", "cat site.conf",
             f"scp site.conf {_T}:."],
        ],
        "traps": [
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:site.conf site.conf", "vim site.conf",
             ":%s/max_clients=10/max_clients=200/", ":wq", "cp site.conf site.conf.orig", f"scp site.conf {_T}:site.conf"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:site.conf site.conf",
             "cp site.conf site.conf.orig", "vim site.conf", ":%s/max_clients=10/max_clients=200/", ":wq",
             f"scp {_T}:site.conf site.conf"],
            ["cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp {_T}:site.conf site.conf",
             "cp site.conf site.conf.orig", "vim site.conf", ":%s/max_clients=10/max_clients=200/", ":wq"],
        ],
        "expected_files": {"site.conf": _SITE_FIXED, "site.conf.orig": _SITE},
        "checks_commands": [_FP_CHECK, _scp_up("site.conf", "site.conf")],
        "require_disconnected": True,
        "hints": ["取り寄せ → 退避 → 編集 → 送り返す、の4段階です。それぞれ向きと順番を意識します。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。scp でサーバー側を先に書けば取り寄せ、後ろに書けば送り返しです。退避は cp、編集は vim が使えます。',
                  "scp learner@training-server:site.conf site.conf → cp site.conf site.conf.orig → vim で直して :wq → scp site.conf learner@training-server:site.conf。"],
        "explanation": "本番サーバーの上で直接編集せず、手元に取り寄せて直してから戻す運用はよくあります。"
                       "このとき元の版を残しておけば、直した設定で問題が出てもすぐ戻せます。"
                       "最後の送り返しを逆向きに打つと、直した内容が古い設定で上書きされて振り出しに戻ります。",
        "practice": ["4-8", "6-6", "1-5"],
    },
    {
        "id": "fes-incident-17",
        "level": 2,
        "title": "止める前に証拠を残す",
        "brief": "メモリを大量に使っているプロセスがあります。プロセス一覧から対象を特定し、止める前にそのプロセスの行だけを evidence.txt に保存してください。"
                 "保存したら止め、もう動いていないことを一覧で確かめます。同じ node で動いている api-server は止めません。",
        "processes": [_LEAK, _API],
        "solution": ["ps aux", "ps aux | grep leak-server > evidence.txt", "cat evidence.txt", "kill 6200", "ps aux"],
        "alt_solutions": [
            ["ps aux", "ps aux | grep leak > evidence.txt", "kill -15 6200", "ps aux | grep node"],
            ["ps aux", "ps aux | grep 6200 > evidence.txt", "kill -TERM 6200", "ps aux"],
        ],
        "traps": [
            ["ps aux", "kill 6200", "ps aux | grep leak-server > evidence.txt"],
            ["ps aux", "ps aux | grep node > evidence.txt", "kill 6200"],
            ["ps aux", "ps aux | grep leak-server > evidence.txt", "kill 6200 6201"],
        ],
        "expected_files": {"evidence.txt": _ps_row(_LEAK) + "\n"},
        "process_gone": ["leak-server"],
        "process_kept": ["api-server", "sshd", "cron"],
        "checks_commands": [["ps aux", "ps aux | grep node", "ps aux | grep leak", "ps aux | grep leak-server"]],
        "hints": ["%MEM の列を見て、どのプロセスかを決めます。止めてしまうと記録は取れません。",
                  "ps aux の結果を grep で1行に絞り、> で保存します。そのあと kill、最後にもう一度 ps aux。",
                  "ps aux | grep leak-server > evidence.txt → kill 6200 → ps aux。"],
        "explanation": "止めたプロセスの情報は二度と取れません。メモリ使用量や起動コマンドを記録してから止めれば、"
                       "あとで「なぜ増えたか」を開発者と調べられます。復旧を急ぐ場面でも、証拠を1行残す手間が再発防止につながります。",
        "practice": ["3-5", "3-7", "2-6"],
    },
    {
        "id": "fes-incident-18",
        "level": 2,
        "title": "容量を食っているフォルダを突き止めて片付ける",
        "brief": 'ディスクが逼迫しています。全体の空きを確認した後、ホーム内のフォルダの大きさを比較してください。原因のフォルダにある一時ファイル（.tmp）だけを削除し、索引データや他のフォルダのファイルは残します。最後に原因のフォルダの大きさをもう一度確かめます。',
        "files": dict(_CACHE),
        "solution": ["df -h", "du -sh data cache logs", "ls cache", "rm cache/*.tmp", "du -sh cache"],
        "alt_solutions": [
            ["df -h", "du -sh *", "rm cache/render-001.tmp cache/render-002.tmp cache/render-003.tmp", "du -sh cache/"],
            ["df -h", "du -sh cache", "cd cache", "rm render-*.tmp", "cd ..", "du -sh cache"],
        ],
        "traps": [
            ["df -h", "du -sh cache", "rm cache/*", "du -sh cache"],
            ["df -h", "du -sh cache", "rm cache/*.tmp logs/current.log", "du -sh cache"],
            ["rm cache/*.tmp"],
        ],
        "absent": ["cache/render-001.tmp", "cache/render-002.tmp", "cache/render-003.tmp"],
        "expected_files": {"cache/index.db": _CACHE["cache/index.db"], "data/orders.csv": _CACHE["data/orders.csv"],
                           "logs/current.log": _CACHE["logs/current.log"]},
        "checks_commands": [["df -h", "df"], ["du -sh cache", "du -sh cache/", "du -sh ./cache", "du -sh *",
                                             "du -sh data cache logs"]],
        "hints": ["df は全体、du はフォルダごとの大きさです。いきなり消さず、まず原因を特定します。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。du -sh にフォルダ名を並べると比べられます。消すのは .tmp で終わるものだけです。',
                  "df -h → du -sh data cache logs → rm cache/*.tmp → du -sh cache。"],
        "explanation": "「ディスクがいっぱい」と言われたら、df で全体を見て、du で犯人のフォルダを絞り込むのが定石です。"
                       "原因が分かっても、同じフォルダの必要なファイル（索引やデータ）まで消すと別の障害になります。"
                       "消したあとにもう一度測って、効果を数字で確かめます。",
        "practice": ["3-8", "2-6"],
    },
    # ================= ★3 =================
    {
        "id": "fes-incident-19",
        "level": 3,
        "title": "深夜2時のアラート：応答しない Web アプリ",
        "brief": '深夜に「Web が遅い」と連絡が来ました。(1) アプリのログの ERROR 行を行番号つきで errors.txt に保存する。(2) ERROR の種類（各行の3列目）ごとの件数を多い順に、uniq -c の表示のまま error-rank.txt に保存する。(3) CPU を使い切るプロセスを通常の停止要求で、止まらなければ強制終了で止める。Web アプリと rsync は止めない。(4) incident.txt に時刻・原因・対応を上書きせず追記し、3行以上の報告にする。',
        "files": {"logs/app.log": _LOG19},
        "processes": [_BATCH, _WEBAPP, _RSYNC],
        "solution": ["grep -n ERROR logs/app.log > errors.txt",
                     "grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > error-rank.txt",
                     "cat error-rank.txt", "ps aux", "kill 7001", "ps aux", "kill -9 7001", "ps aux",
                     "echo '02:10 Web 遅延のアラートを受信' >> incident.txt",
                     "echo '原因: report-batch が CPU を使い切り db-timeout が多発' >> incident.txt",
                     "echo '対応: report-batch を TERM で止まらず -9 で停止' >> incident.txt", "cat incident.txt"],
        "alt_solutions": [
            ["ps aux | grep python3", "kill -TERM 7001", "pgrep report-batch", "kill -KILL 7001",
             "cat logs/app.log | grep -n ERROR > errors.txt",
             "grep ERROR logs/app.log > only-error.txt", "cut -d ' ' -f 3 only-error.txt | sort | uniq -c | sort -rn > error-rank.txt",
             "echo 02:10 アラート受信 > incident.txt", "echo 原因 report-batch の暴走 >> incident.txt",
             "echo 対応 停止して復旧を確認 >> incident.txt"],
        ],
        "traps": [
            ["grep -n ERROR logs/app.log > errors.txt",
             "grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > error-rank.txt",
             "kill -9 7001", "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["grep -n ERROR logs/app.log > errors.txt",
             "grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > error-rank.txt",
             "kill 7001 7002", "kill -9 7001 7002", "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["grep -n ERROR logs/app.log > errors.txt",
             "grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > error-rank.txt",
             "kill 7001", "kill -9 7001", "echo 時刻 > incident.txt", "echo 原因 > incident.txt", "echo 対応 > incident.txt"],
            ["grep -n ERROR logs/app.log > errors.txt",
             "grep ERROR logs/app.log | cut -d ' ' -f 3 | uniq -c | sort -rn > error-rank.txt",
             "kill 7001", "kill -9 7001", "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
        ],
        "expected_files": {"errors.txt": _grep_n(_LOG19, "ERROR"), "error-rank.txt": _RANK19},
        "min_lines": {"incident.txt": 3},
        "process_gone": ["report-batch"],
        "process_kept": ["web-app", "rsync", "sshd", "cron"],
        "checks_commands": [["kill 7001", "kill -15 7001", "kill -TERM 7001", "kill -SIGTERM 7001", "kill -s TERM 7001"]],
        "hints": ["調査（行番号つき抽出・ランキング）→ 復旧（段階的な停止）→ 報告（追記）の3段で考えます。",
                  "ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。種類は grep ERROR のあと cut -d ' ' -f 3、数えるのは sort | uniq -c | sort -rn。停止は kill → 確認 → kill -9。",
                  "grep -n ERROR logs/app.log > errors.txt → grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > error-rank.txt → kill 7001 → kill -9 7001 → echo '…' >> incident.txt を3回。"],
        "explanation": "実際の当番では、調べる・止める・記録するを同時並行でこなします。どのエラーが最も多いかを数字で示し、"
                       "止めたプロセスと手順を時刻つきで残しておけば、朝に引き継ぐ人が状況をすぐ把握できます。"
                       "焦って似たプロセスまで止めたり、報告を上書きしたりしないことが、深夜対応の腕の見せどころです。",
        "practice": ["2-1", "2-7", "3-5", "2-6"],
    },
    {
        "id": "fes-incident-20",
        "level": 3,
        "title": "ディスク満杯：ログが書けない夜",
        "brief": 'ディスクがいっぱいでログが書けません。(1) 全体の空きとフォルダの大きさを調べる。(2) アプリのログは書き込み中と直近の1世代を残し、それより古い世代だけ削除する。(3) アプリ設定を app.conf.bak に退避し、log_level=info に直す（vim はまだありません）。ほかの行は変えない。(4) incident.txt に追記し、3行以上の報告を残す。',
        "files": {**_LOGS20, "app.conf": _CONF20},
        "solution": ["df -h", "du -sh logs", "ls -l logs", "rm logs/app.log.2 logs/app.log.3", "du -sh logs",
                     "cp app.conf app.conf.bak", "sudo apt update", "sudo apt install vim", "vim app.conf",
                     ":%s/log_level=debug/log_level=info/", ":wq", "cat app.conf",
                     "echo '03:05 ディスク満杯の連絡を受信' >> incident.txt",
                     "echo '原因: log_level=debug のままで詳細ログが増加' >> incident.txt",
                     "echo '対応: 古いログ2世代を削除し log_level=info に変更' >> incident.txt"],
        "alt_solutions": [
            ["sudo apt update", "sudo apt install -y vim", "df -h", "du -sh *", "rm logs/app.log.[23]",
             "cp app.conf app.conf.bak", "vim app.conf", "/log_level", ":s/debug/info/", "ZZ",
             "echo 03:05 連絡受信 >> incident.txt", "echo 原因 debug ログ >> incident.txt", "echo 対応 削除と設定変更 >> incident.txt"],
        ],
        "traps": [
            ["df -h", "du -sh logs", "rm logs/app.log*", "cp app.conf app.conf.bak", "sudo apt update", "sudo apt install vim",
             "vim app.conf", ":%s/log_level=debug/log_level=info/", ":wq",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["df -h", "du -sh logs", "rm logs/app.log.2 logs/app.log.3", "sudo apt update", "sudo apt install vim",
             "vim app.conf", ":%s/log_level=debug/log_level=info/", ":wq", "cp app.conf app.conf.bak",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["df -h", "du -sh logs", "rm logs/app.log.2 logs/app.log.3", "cp app.conf app.conf.bak", "sudo apt update",
             "sudo apt install vim", "vim app.conf", ":%s/debug/info/g", ":wq",
             "echo 1 > incident.txt", "echo 2 > incident.txt", "echo 3 > incident.txt"],
        ],
        "absent": ["logs/app.log.2", "logs/app.log.3"],
        "expected_files": {"logs/app.log": _LOGS20["logs/app.log"], "logs/app.log.1": _LOGS20["logs/app.log.1"],
                           "app.conf": _CONF20_FIXED, "app.conf.bak": _CONF20},
        "packages": ["vim"],
        "min_lines": {"incident.txt": 3},
        "checks_commands": [["df -h", "df"], ["du -sh logs", "du -sh logs/", "du -sh *", "du -sh ."]],
        "hints": ["応急処置（容量を空ける）と根本対策（設定を直す）の両方が必要です。設定は退避してから触ります。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。df -h と du -sh で確認 → 番号の大きいログだけ rm → cp で退避 → apt で vim を入れて置換 → >> で報告。',
                  "rm logs/app.log.2 logs/app.log.3 → cp app.conf app.conf.bak → sudo apt update → sudo apt install vim → vim app.conf → :%s/log_level=debug/log_level=info/ → :wq。"],
        "explanation": "ログを消すだけでは、数時間後にまたディスクが埋まります。応急処置で時間を稼ぎ、原因の設定を直してはじめて障害が終わります。"
                       "書き込み中のログまで消すと調査の手がかりが失われ、退避前に編集すると元に戻せません。応急・恒久・記録の3点セットを意識しましょう。",
        "practice": ["3-8", "6-6", "1-5", "7-2"],
    },
    {
        "id": "fes-incident-21",
        "level": 3,
        "title": "遠隔の障害：サーバーに入って原因を持ち帰る",
        "brief": 'training-server でエラーが多発しています。管理者から届いた指紋を表示と照合し、learner として2222番ポートへ接続してください。用意された訓練用の鍵を探して指定します。(1) サーバーのアプリのログから ERROR を行番号つきで抜き出し、手元へ server-errors.txt として持ち帰る。(2) 種類（行番号つき表示で3列目）ごとの件数を多い順に、uniq -c の表示のまま rank.txt に保存する。(3) incident.txt に追記して3行以上の報告を書く。手元の同名ログは昨日の写しなので使いません。最後は手元へ戻ります。',
        "files": {"fingerprint.txt": _FP, "keys/oncall_key": _KEY, "logs/app.log": _LOG21_STALE},
        "remote_files": {"logs/app.log": _LOG21_REMOTE},
        "solution": ["chmod 600 keys/oncall_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/oncall_key {_T}", "yes",
                     "hostname", "grep -n ERROR logs/app.log > server-errors.txt", "exit",
                     f"scp {_T}:server-errors.txt server-errors.txt",
                     "cut -d ' ' -f 3 server-errors.txt | sort | uniq -c | sort -rn > rank.txt", "cat rank.txt",
                     "echo '02:20 training-server のエラー多発を確認' >> incident.txt",
                     "echo '最多は upstream-502、cert-expired も発生' >> incident.txt",
                     "echo '証明書の更新を担当へ依頼' >> incident.txt", "hostname"],
        "alt_solutions": [
            ["cat fingerprint.txt", "chmod 600 keys/oncall_key", f"ssh {_T} -p 2222 -i keys/oncall_key", "yes", "exit",
             f"scp {_T}:logs/app.log server-app.log", "grep -n ERROR server-app.log > server-errors.txt",
             "cat server-errors.txt | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
             "echo 調査開始 >> incident.txt", "echo 最多 upstream-502 >> incident.txt", "echo 担当へ連絡 >> incident.txt"],
        ],
        "traps": [
            ["chmod 600 keys/oncall_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/oncall_key {_T}", "yes", "exit",
             "grep -n ERROR logs/app.log > server-errors.txt",
             "cut -d ' ' -f 3 server-errors.txt | sort | uniq -c | sort -rn > rank.txt",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["chmod 600 keys/oncall_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/oncall_key {_T}", "yes",
             "grep -n ERROR logs/app.log > server-errors.txt", "exit", f"scp {_T}:server-errors.txt server-errors.txt",
             "cut -d ' ' -f 3 server-errors.txt | sort | uniq -c | sort -rn > rank.txt",
             f"ssh -p 2222 -i keys/oncall_key {_T}",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["chmod 600 keys/oncall_key", "cat fingerprint.txt", f"ssh -i keys/oncall_key {_T}", "yes",
             "grep -n ERROR logs/app.log > server-errors.txt", "exit", f"scp {_T}:server-errors.txt server-errors.txt",
             "cut -d ' ' -f 3 server-errors.txt | sort | uniq -c | sort -rn > rank.txt",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
        ],
        "expected_files": {"server-errors.txt": _ERR21, "rank.txt": _RANK21, "logs/app.log": _LOG21_STALE,
                           "keys/oncall_key": _KEY},
        "expected_modes": {"keys/oncall_key": 0o600},
        "min_lines": {"incident.txt": 3},
        "checks_commands": [_FP_CHECK, _ssh_forms(port="2222", key="keys/oncall_key")],
        "require_disconnected": True,
        "hints": ['鍵の名前や場所も自分で調べます。対象と権限を確かめてから接続し、接続先と手元を取り違えないようにしましょう。',
                  "ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。サーバー上で grep -n の結果を > で保存し、exit してから scp で受け取ります。集計は cut -d ' ' -f 3 | sort | uniq -c | sort -rn。",
                  "chmod 600 keys/oncall_key → ssh -p 2222 -i keys/oncall_key learner@training-server → yes → grep -n ERROR logs/app.log > server-errors.txt → exit → scp learner@training-server:server-errors.txt server-errors.txt → cut … > rank.txt → echo … >> incident.txt。"],
        "explanation": "遠隔のサーバーでは、重い集計をせず必要な行だけを抜き出して持ち帰るのが、相手の負荷を増やさないやり方です。"
                       "手元に同じ名前の古いログがあると、気づかずにそちらを調べてしまいがちです。調べ終わったら接続を閉じ、"
                       "本番サーバーにつないだまま席を離れない、までが当番の作法です。",
        "practice": ["4-7", "4-8", "2-7", "2-1"],
    },
    {
        "id": "fes-incident-22",
        "level": 3,
        "title": "壊れた設定のロールバックと再配布",
        "brief": 'アプリ設定の変更後にサイトが起動しなくなりました。(1) 壊れた設定を app.conf.broken として残す。(2) 前日の正しい控えから設定を戻す。控えは残し、今回追加された cache=on は最後の行に残す。(3) 直った設定を training-server の learner のホーム直下の app.conf として送る。接続先は管理者から届いた指紋と照合する。(4) incident.txt に追記で3行以上の報告を書き、最後は手元へ戻る。',
        "files": {"fingerprint.txt": _FP, "app.conf": _CONF22_BROKEN, "app.conf.bak": _CONF22_GOOD},
        "remote_files": {"app.conf": _CONF22_BROKEN},
        "initial_packages": ["vim"],
        "solution": ["cat app.conf", "cp app.conf app.conf.broken", "cp app.conf.bak app.conf", "echo cache=on >> app.conf",
                     "cat app.conf", "cat fingerprint.txt", f"ssh {_T}", "yes", "cat app.conf", "exit",
                     f"scp app.conf {_T}:app.conf",
                     "echo '18:30 変更後にサイトが起動しない連絡' >> incident.txt",
                     "echo '原因: port=8O80 の打ち間違い' >> incident.txt",
                     "echo '対応: 前日の設定に戻し cache=on を再適用して配布' >> incident.txt"],
        "alt_solutions": [
            ["cp app.conf app.conf.broken", "vim app.conf", ":%s/8O80/8080/", ":wq", "cat fingerprint.txt", f"ssh {_T}",
             "yes", "exit", f"scp app.conf {_T}:/home/learner/app.conf",
             "echo 連絡受信 >> incident.txt", "echo 原因 打ち間違い >> incident.txt", "echo 対応 修正して配布 >> incident.txt"],
        ],
        "traps": [
            ["mv app.conf app.conf.broken", "mv app.conf.bak app.conf", "echo cache=on >> app.conf", "cat fingerprint.txt",
             f"ssh {_T}", "yes", "exit", f"scp app.conf {_T}:app.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["cp app.conf.bak app.conf", "echo cache=on >> app.conf", "cp app.conf app.conf.broken", "cat fingerprint.txt",
             f"ssh {_T}", "yes", "exit", f"scp app.conf {_T}:app.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["cp app.conf app.conf.broken", "cp app.conf.bak app.conf", "echo cache=on >> app.conf", "cat fingerprint.txt",
             f"ssh {_T}", "yes", "exit", f"scp {_T}:app.conf app.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["cp app.conf app.conf.broken", "cp app.conf.bak app.conf", "echo cache=on > app.conf", "cat fingerprint.txt",
             f"ssh {_T}", "yes", "exit", f"scp app.conf {_T}:app.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
        ],
        "expected_files": {"app.conf": _CONF22_FINAL, "app.conf.broken": _CONF22_BROKEN, "app.conf.bak": _CONF22_GOOD},
        "min_lines": {"incident.txt": 3},
        "checks_commands": [_FP_CHECK, _scp_up("app.conf", "app.conf")],
        "require_disconnected": True,
        "hints": ["壊れた版・正しい版・これから使う版の3つを区別します。mv で動かすと元の名前のファイルがなくなります。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。壊れた版を cp で残し、bak から cp で戻して cache=on を >> で足すか、vim で打ち間違いだけを直します。',
                  "cp app.conf app.conf.broken → cp app.conf.bak app.conf → echo cache=on >> app.conf → 接続確認 → exit → scp app.conf learner@training-server:app.conf → echo … >> incident.txt。"],
        "explanation": "ロールバック（元に戻す）は障害対応の最速の手段ですが、壊れた版を残さないと原因の検証ができず、"
                       "正しい版の控えを mv で使い切ると次に戻す先がなくなります。戻したうえで必要な変更だけを再適用し、"
                       "配布先にも確実に届ける。ここまでやって初めて「直った」と言えます。",
        "practice": ["1-5", "4-8", "6-6", "2-6"],
    },
    {
        "id": "fes-incident-23",
        "level": 3,
        "title": "ログイン失敗の嵐：攻撃元を遮断リストへ",
        "brief": 'ログイン画面へのアクセスが急増しています。アクセスログを調べ、(1) ステータス401の行だけをIPごとに数え、多い順に uniq -c の表示で suspect.txt に保存する。(2) 401が最多のIPを遮断するため deny.conf に「deny IP;」の1行を書く（例: deny 192.0.2.1;）。普通の利用者を遮断しない。(3) deny.conf を training-server の learner のホーム直下に送り、管理者から届いた指紋で接続先を確かめる。(4) incident.txt に追記で3行以上の報告を書き、最後は手元へ戻る。',
        "files": {"fingerprint.txt": _FP, "access.log": _ACCESS23},
        "solution": ["head -3 access.log", "grep ' 401 ' access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > suspect.txt",
                     "cat suspect.txt", "echo 'deny 203.0.113.66;' > deny.conf", "cat fingerprint.txt", f"ssh {_T}", "yes",
                     "exit", f"scp deny.conf {_T}:deny.conf",
                     "echo '03:20 ログイン失敗の急増を検知' >> incident.txt",
                     "echo '401 が最多の 203.0.113.66 を特定' >> incident.txt",
                     "echo 'deny.conf で遮断しサーバーへ配布' >> incident.txt"],
        "alt_solutions": [
            ["grep 401 access.log > failed.txt", "cut -d ' ' -f 1 failed.txt | sort | uniq -c | sort -rn > suspect.txt",
             "head -1 suspect.txt", "echo deny 203.0.113.66\\; > deny.conf", "cat fingerprint.txt", f"ssh {_T}", "yes",
             "exit", f"scp deny.conf {_T}:.",
             "echo 検知 >> incident.txt", "echo 特定 203.0.113.66 >> incident.txt", "echo 遮断 >> incident.txt"],
            ["cat access.log | grep -E ' 401 ' | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > suspect.txt",
             "echo \"deny 203.0.113.66;\" >> deny.conf", "cat fingerprint.txt", f"ssh {_T}", "yes", "exit",
             f"scp ./deny.conf {_T}:/home/learner/deny.conf",
             "echo 検知 >> incident.txt", "echo 特定 >> incident.txt", "echo 遮断 >> incident.txt"],
        ],
        "traps": [
            ["cut -d ' ' -f 1 access.log | sort | uniq -c | sort -rn > suspect.txt", "echo 'deny 198.51.100.7;' > deny.conf",
             "cat fingerprint.txt", f"ssh {_T}", "yes", "exit", f"scp deny.conf {_T}:deny.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["grep ' 401 ' access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > suspect.txt",
             "echo 'deny 203.0.113.66;' > deny.conf", "cat fingerprint.txt", f"ssh {_T}", "yes",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
            ["grep ' 401 ' access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > suspect.txt",
             "echo 'deny 203.0.113.66;' > deny.conf", "cat fingerprint.txt", f"ssh {_T}", "yes", "exit",
             f"scp {_T}:deny.conf deny.conf",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt"],
        ],
        "expected_files": {"suspect.txt": _SUSPECT, "deny.conf": "deny 203.0.113.66;\n", "access.log": _ACCESS23},
        "min_lines": {"incident.txt": 3},
        "checks_commands": [_FP_CHECK, _scp_up("deny.conf", "deny.conf")],
        "require_disconnected": True,
        "hints": ["「アクセスが多い」と「認証失敗が多い」は別物です。まず 401 の行だけに絞ってから数えます。",
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。grep で 401 の行 → cut で IP → sort | uniq -c | sort -rn。; を含む文は引用符で囲んで echo します。',
                  "grep ' 401 ' access.log | cut -d ' ' -f 1 | sort | uniq -c | sort -rn > suspect.txt → echo 'deny 203.0.113.66;' > deny.conf → 接続確認 → exit → scp deny.conf learner@training-server:deny.conf。"],
        "explanation": "攻撃対応で怖いのは、正しい利用者を巻き込んで遮断することです。単純なアクセス数ではなく、"
                       "認証失敗という「攻撃らしさ」で絞り込んでから順位を付けます。遮断リストは配布して初めて効くので、送り先と向きも確実に。",
        "practice": ["2-1", "2-7", "4-8", "2-6"],
    },
    {
        "id": "fes-incident-24",
        "level": 3,
        "title": "夜明けまでの総仕上げ：当番の一晩",
        "brief": '書き出しバッチが止まらず、サービスが重くなっています。(1) 訓練用の鍵を探し、使える権限にして、管理者から届いた指紋を照合し、learner として2222番ポートで training-server に接続する。(2) サーバーのアプリのログを手元に server-app.log として取り寄せ、ERROR の種類（3列目）ごとの件数を多い順に uniq -c の表示で rank.txt に保存する。(3) root の書き出しプロセスを通常の停止要求で、止まらなければ強制終了で止める。nginx・sshd・cron は止めない。(4) 手元の書き出しログは使用中と直近の1世代を残し、それより古い世代だけ削除する。(5) 書き出し設定を export.conf.bak に退避し、max_connections=100 に直す（vim はまだありません）。(6) incident.txt に追記して5行以上の報告を書く。最後は手元のコンピューターであることを確かめる。',
        "files": {"fingerprint.txt": _FP, "keys/night_key": _KEY, "export.conf": _CONF24, **_LOGS24},
        "remote_files": {"logs/app.log": _LOG24_REMOTE},
        "processes": [_EXPORT, _NGINX],
        "solution": ["chmod 600 keys/night_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/night_key {_T}", "yes",
                     "hostname", "tail -3 logs/app.log", "exit", f"scp {_T}:logs/app.log server-app.log",
                     "grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
                     "ps aux", "sudo kill 8101", "ps aux", "sudo kill -9 8101", "ps aux",
                     "df -h", "du -sh logs", "rm logs/export.log.2 logs/export.log.3",
                     "cp export.conf export.conf.bak", "sudo apt update", "sudo apt install vim", "vim export.conf",
                     ":%s/max_connections=10/max_connections=100/", ":wq",
                     "echo '04:00 書き出しバッチ遅延のアラート' >> incident.txt",
                     "echo 'ログ: export-timeout が最多、db-lock も発生' >> incident.txt",
                     "echo '対応1: export.py を TERM で止まらず -9 で停止' >> incident.txt",
                     "echo '対応2: 古いログ2世代を削除して容量を確保' >> incident.txt",
                     "echo '対応3: max_connections を 100 に変更、bak あり' >> incident.txt",
                     "cat incident.txt", "hostname"],
        "alt_solutions": [
            ["sudo apt update", "sudo apt install -y vim", "cp export.conf export.conf.bak", "vim export.conf",
             "/max_connections", ":s/=10/=100/", ":wq", "cat fingerprint.txt", "chmod 600 keys/night_key",
             f"ssh -i keys/night_key -p 2222 {_T}", "yes",
             "grep ERROR logs/app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt", "exit",
             f"scp {_T}:logs/app.log server-app.log", f"scp {_T}:rank.txt rank.txt",
             "pgrep export.py", "sudo kill -TERM 8101", "pgrep export.py", "sudo kill -KILL 8101",
             "df -h", "rm logs/export.log.[23]",
             "echo 1 アラート >> incident.txt", "echo 2 原因 >> incident.txt", "echo 3 停止 >> incident.txt",
             "echo 4 容量 >> incident.txt", "echo 5 設定 >> incident.txt", "hostname"],
        ],
        "traps": [
            ["chmod 600 keys/night_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/night_key {_T}", "yes", "exit",
             f"scp {_T}:logs/app.log server-app.log",
             "grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
             "sudo kill -9 8101", "rm logs/export.log.2 logs/export.log.3",
             "cp export.conf export.conf.bak", "sudo apt update", "sudo apt install vim", "vim export.conf",
             ":%s/max_connections=10/max_connections=100/", ":wq",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt", "echo 4 >> incident.txt",
             "echo 5 >> incident.txt", "hostname"],
            ["chmod 600 keys/night_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/night_key {_T}", "yes", "exit",
             f"scp {_T}:logs/app.log server-app.log",
             "grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
             "sudo kill 8101 8102", "sudo kill -9 8101 8102", "rm logs/export.log.2 logs/export.log.3",
             "cp export.conf export.conf.bak", "sudo apt update", "sudo apt install vim", "vim export.conf",
             ":%s/max_connections=10/max_connections=100/", ":wq",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt", "echo 4 >> incident.txt",
             "echo 5 >> incident.txt", "hostname"],
            ["chmod 600 keys/night_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/night_key {_T}", "yes", "exit",
             f"scp {_T}:logs/app.log server-app.log",
             "grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
             "sudo kill 8101", "sudo kill -9 8101", "rm logs/export.log.*",
             "sudo apt update", "sudo apt install vim", "vim export.conf",
             ":%s/max_connections=10/max_connections=100/", ":wq", "cp export.conf export.conf.bak",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt", "echo 4 >> incident.txt",
             "echo 5 >> incident.txt", "hostname"],
            ["chmod 600 keys/night_key", "cat fingerprint.txt", f"ssh -p 2222 -i keys/night_key {_T}", "yes", "exit",
             f"scp {_T}:logs/app.log server-app.log",
             "grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt",
             "sudo kill 8101", "sudo kill -9 8101", "rm logs/export.log.2 logs/export.log.3",
             "cp export.conf export.conf.bak", "sudo apt update", "sudo apt install vim", "vim export.conf",
             ":%s/max_connections=10/max_connections=100/", ":wq",
             "echo 1 >> incident.txt", "echo 2 >> incident.txt", "echo 3 >> incident.txt", "echo 4 >> incident.txt",
             "echo 5 >> incident.txt", f"ssh -p 2222 -i keys/night_key {_T}", "hostname"],
        ],
        "expected_files": {"server-app.log": _LOG24_REMOTE, "rank.txt": _RANK24,
                           "logs/export.log": _LOGS24["logs/export.log"], "logs/export.log.1": _LOGS24["logs/export.log.1"],
                           "export.conf": _CONF24_FIXED, "export.conf.bak": _CONF24, "keys/night_key": _KEY},
        "expected_modes": {"keys/night_key": 0o600},
        "absent": ["logs/export.log.2", "logs/export.log.3"],
        "packages": ["vim"],
        "min_lines": {"incident.txt": 5},
        "process_gone": ["/opt/export.py"],
        "process_kept": ["nginx", "sshd", "cron"],
        "checks_commands": [_FP_CHECK, _ssh_forms(port="2222", key="keys/night_key"),
                            ["sudo kill 8101", "sudo kill -15 8101", "sudo kill -TERM 8101", "sudo kill -SIGTERM 8101",
                             "sudo kill -s TERM 8101"],
                            "hostname"],
        "require_disconnected": True,
        "hints": ['鍵の名前や場所も自分で調べます。対象と権限を確かめてから接続し、接続先と手元を取り違えないようにしましょう。',
                  'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。鍵は chmod 600、接続は -p と -i、取り寄せは exit 後の scp、集計は grep | cut | sort | uniq -c | sort -rn、停止は sudo kill → sudo kill -9、設定は退避してから apt で vim を入れて置換、報告は >>。',
                  "chmod 600 keys/night_key → ssh -p 2222 -i keys/night_key learner@training-server → yes → exit → scp …:logs/app.log server-app.log → grep ERROR server-app.log | cut -d ' ' -f 3 | sort | uniq -c | sort -rn > rank.txt → sudo kill 8101 → sudo kill -9 8101 → rm logs/export.log.2 logs/export.log.3 → cp で退避 → apt で vim → :%s で置換 → echo … >> incident.txt を5回 → hostname。"],
        "explanation": "ここまでの操作をすべて組み合わせると、実際の当番の一晩になります。接続先を確かめ、証拠を残し、"
                       "影響の少ない手段から順に試し、消すもの・直すものの範囲を正確に絞り、元に戻せる状態を保ち、記録を積み上げる。"
                       "そして最後に、自分が本番サーバーではなく手元にいることを確かめてから引き継ぐ。これができれば、Linux の現場で自信を持って動けます。",
        "practice": ["4-7", "4-8", "2-7", "3-5", "3-8", "6-6", "1-5"],
    },
]
