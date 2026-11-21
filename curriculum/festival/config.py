"""課題まつり：設定ファイルを読む・退避する・vim で直す・権限で守る。

値・パスワード・トークンはすべて訓練用のダミー。IP アドレスは文書用の範囲（192.0.2.0/24 など）だけを使う。
"""

PACK_TITLE = "設定ファイルと vim 編集"

_VIM = ["vim"]
_DUMMY = "TRAINING_ONLY_NOT_A_SECRET"

# ---- 01
_MEMO = "点検メモ\nport と log_level を確認する\n"

# ---- 02
_HOSTS_LIST = ("# 社内サーバー一覧（訓練用）\n192.0.2.10  web01\n192.0.2.11  web02\n"
               "192.0.2.20  db01\n192.0.2.30  cache01\n")

# ---- 03
_APP_LOG = "# アプリの設定（訓練用）\nport=8080\nlog_level=debug\ndebug_toolbar=off\nhost=0.0.0.0\n"
_APP_LOG_FIXED = _APP_LOG.replace("log_level=debug", "log_level=info")

# ---- 04
_WEB = "# Web サーバー設定（訓練用）\nlisten=80\nworkers=4\n"

# ---- 05
_WORKER = ("# ワーカーの設定（訓練用）\n# 既定値は queue=default です\n\nqueue=reports\n\n"
           "# 同時に処理する数\nconcurrency=2\nretry=3\n")
_WORKER_ACTIVE = "queue=reports\nconcurrency=2\nretry=3\n"

# ---- 06
_ENV_06 = "APP_ENV=training\nDB_PASSWORD=" + _DUMMY + "\n"

# ---- 07
_DEPLOY_SH = "#!/bin/sh\necho deploy training\n"
_BACKUP_SH = "#!/bin/sh\necho backup training\n"
_NOTES = "配備の手順は deploy.sh を見てください。\n"

# ---- 08
_FEATURES = ("# 機能フラグ（訓練用）\nfeature_search=on\nfeature_export=off\n"
             "# ここから下は実験中の機能\nfeature_beta_ui=off\n")
_FEATURES_FIXED = _FEATURES.replace("feature_export=off\n", "feature_export=off\nfeature_dark_mode=on\n")

# ---- 09
_DB = "# DB 接続設定（訓練用）\nhost=192.0.2.20\nport=5432\ndebug_sql=true\npool=10\n"
_DB_FIXED = _DB.replace("debug_sql=true\n", "")

# ---- 10
_SITE = ("# Web サーバー設定（訓練用）\nserver {\n    listen 80;\n    server_name training.example;\n"
         "    location /api {\n        proxy_pass http://192.0.2.10:8000;\n    }\n}\n")
_SITE_FIXED = _SITE.replace("listen 80;", "listen 8080;")

# ---- 11
_LB = "# 負荷分散先（訓練用）\n192.0.2.11  web01\n192.0.2.12  web02\n192.0.2.20  db01\n"
_LB_FIXED = _LB.replace("web02\n", "web02\n192.0.2.13  web03\n")

# ---- 12
_ENV_12 = "APP_ENV=training\nAPI_TOKEN=" + _DUMMY + "\nLOG_LEVEL=info\n"

# ---- 13
_CRON = ("# 定期ジョブ（訓練用・crontab の形式）\n*/5 * * * * /home/learner/bin/health.sh\n"
         "0 * * * * /home/learner/bin/cleanup.sh\n30 3 * * * /home/learner/bin/backup.sh\n")
_CRON_FIXED = _CRON.replace("0 * * * * /home/learner/bin/cleanup.sh", "# 0 * * * * /home/learner/bin/cleanup.sh")

# ---- 14
_GOOD = "# アプリの設定（訓練用）\nport=8080\nlog_level=info\nhost=0.0.0.0\n"
_BROKEN = "# アプリの設定（訓練用）\nport=8080\nlog_level=\nhost=0.0.0.0 host=0.0.0.0\n"
_GOOD_FIXED = _GOOD.replace("port=8080", "port=8081")

# ---- 15
_FLAGS = ("# 機能フラグ（訓練用）\nnew_checkout=true\nlegacy_api=false\n# old_banner=true（廃止済み）\n"
          "fast_search=true\nmaintenance=false\n")
_FLAGS_REPORT = "2:new_checkout=true\n5:fast_search=true\n"

# ---- 16
_ENV_EXAMPLE = "# コピーして .env を作ります（訓練用）\nAPP_ENV=development\nAPI_KEY=CHANGE_ME\nLOG_LEVEL=debug\n"
_ENV_PROD = ("# コピーして .env を作ります（訓練用）\nAPP_ENV=production\nAPI_KEY=" + _DUMMY + "\nLOG_LEVEL=warn\n")

# ---- 17
_INI = ("# 配備先ごとの設定（訓練用）\n[staging]\nhost=198.51.100.10\nport=8080\n\n"
        "[production]\nhost=203.0.113.10\nport=8080\n")
_INI_FIXED = _INI[:_INI.index("[production]")] + "[production]\nhost=203.0.113.10\nport=8443\n"

# ---- 18
_ROTATE_HEAD = "#!/bin/sh\n"
_ROTATE = "#!/bin/sh\necho rotate logs training\n"

# ---- 19
_MAIN = "# 上から順に読み込みます（訓練用）\ninclude override.conf;\ninclude base.conf;\ninclude plugins.conf;\n"
_MAIN_FIXED = "# 上から順に読み込みます（訓練用）\ninclude base.conf;\ninclude plugins.conf;\ninclude override.conf;\n"

# ---- 20
_APP20 = "# アプリの設定（訓練用）\nport=8080\nlog_level=debug\nworkers=2\n"
_APP20_FIXED = "# アプリの設定（訓練用）\nport=3000\nlog_level=info\nworkers=2\ntimeout=30\n"
_SECRETS20 = "DB_PASSWORD=" + _DUMMY + "\n"
_START20 = "#!/bin/sh\necho start app training\n"

# ---- 21
_API21 = "# API サーバー（訓練用）\nport=8001\nlog_level=debug\ndebug_endpoint=off\n"
_WORKER21 = "# ワーカー（訓練用）\nqueue=default\nlog_level=debug\n"
_API21_FIXED = _API21.replace("log_level=debug", "log_level=warn")
_WORKER21_FIXED = _WORKER21.replace("log_level=debug", "log_level=warn")
_LEVELS21 = "conf/api.conf:3:log_level=warn\nconf/worker.conf:3:log_level=warn\n"

# ---- 22
_CRON22 = ("# 定期ジョブ（訓練用）\n*/10 * * * * /home/learner/bin/sync.sh\n"
           "0 9 * * * /home/learner/bin/send_mail.sh\n0 4 * * * /home/learner/bin/backup.sh\n")
_CRON22_FIXED = _CRON22.replace("0 9 * * *", "# 0 9 * * *")
_FLAGS22 = "# 運用フラグ（訓練用）\nmaintenance=off\nsignup=on\n"
_FLAGS22_FIXED = "# 運用フラグ（訓練用）\nmaintenance=on\nsignup=off\n"
_NOTICE_SH = "#!/bin/sh\necho maintenance training\n"
_WORKLOG22 = "2026-11-20 deploy done\n"

# ---- 23
_SHARED = ("# 共有設定（訓練用）\napp_name=training-shop\ndb_host=192.0.2.20\n"
           "db_password=" + _DUMMY + "\ncache_ttl=60\n")
_SHARED_FIXED = _SHARED.replace("db_password=" + _DUMMY + "\n", "")
_SECRET23 = "# 秘密の設定（訓練用）\n"
_SECRET23_FIXED = _SECRET23 + "db_password=" + _DUMMY + "\n"

# ---- 24
_NGX = ("# 公開用の Web 設定（訓練用）\nupstream app {\n    server 192.0.2.11:3000;\n    server 192.0.2.12:3000;\n}\n\n"
        "server {\n    listen 80;\n    server_name old.training.example;\n    # access_log off;\n"
        "    location / {\n        proxy_pass http://app;\n    }\n}\n")
_NGX_FIXED = (_NGX.replace("    server 192.0.2.12:3000;\n", "    server 192.0.2.12:3000;\n    server 192.0.2.13:3000;\n")
              .replace("old.training.example", "shop.training.example"))
_NGX_ACTIVE = "".join(line + "\n" for line in _NGX_FIXED.splitlines() if "#" not in line and line)

SCENARIOS = [
    # ------------------------------------------------------------------ ★1
    {
        "id": "fes-config-01",
        "level": 1,
        "title": "vim を用意して点検メモを書く",
        "brief": "点検の手順メモ check.txt を、vim を使って新しく作ってください。1行目は「点検メモ」、"
                 "2行目は「port と log_level を確認する」です。この環境にはまだ vim が入っていないので、使えるようにしてから書きます。",
        "solution": ["sudo apt update", "sudo apt install vim", "vim check.txt", "i", "点検メモ",
                     "port と log_level を確認する", "esc", ":wq"],
        "alt_solutions": [["sudo apt update", "sudo apt install -y vim", "vi check.txt", "a", "点検メモ",
                           "port と log_level を確認する", "esc", ":x"],
                          ["sudo apt update", "sudo apt install vim", "vim check.txt", "o", "点検メモ",
                           "port と log_level を確認する", "esc", "ZZ"]],
        "traps": [["echo 点検メモ > check.txt", "echo \"port と log_level を確認する\" >> check.txt"],
                  ["sudo apt update", "sudo apt install vim", "vim check.txt", "i", "点検メモ",
                   "port と log_level を確認する", "esc"],
                  ["sudo apt update", "sudo apt install vim", "vim check.txt", "i", "点検メモ",
                   "port と log_level を確認する", "esc", ":q!"]],
        "expected_files": {"check.txt": _MEMO},
        "packages": _VIM,
        "hints": ["vim が無いと開けません。まず道具を入れ、開いたら「書く状態」に切り替えます。",
                  "sudo apt update → sudo apt install vim で入れます。vim では i で入力モード、esc で戻り、:wq で保存して閉じます。",
                  "vim check.txt → i → 1行ずつ入力して Enter → esc → :wq。"],
        "explanation": "サーバーには vim が入っていないこともあります。自分で入れられれば、どこでも設定を書けます。"
                       "vim は「開いた直後は入力できない」「保存して閉じるまでファイルは変わらない」の2点を体で覚えるのが近道です。",
        "practice": ["6-6", "3-4"],
    },
    {
        "id": "fes-config-02",
        "level": 1,
        "title": "開いて確かめ、変えずに閉じる",
        "brief": "vim で hosts.txt を開き、db01 が何行目にあるかを確かめてください。hosts.txt は1文字も変えずに vim を閉じ、"
                 "見つけた行番号の数字だけを db_line.txt に保存します。",
        "initial_packages": _VIM,
        "files": {"hosts.txt": _HOSTS_LIST},
        "solution": ["vim hosts.txt", "/db01", ":q", "echo 4 > db_line.txt"],
        "alt_solutions": [["grep -n db01 hosts.txt", "vim hosts.txt", ":4", ":q", "echo 4 > db_line.txt"],
                          ["vi hosts.txt", "dd", "u", ":q!", "echo 4 > db_line.txt"],
                          ["vim hosts.txt", "dd", ":q!", "cat -n hosts.txt", "echo 4 > db_line.txt"]],
        "traps": [["vim hosts.txt", "dd", ":wq", "echo 4 > db_line.txt"],
                  ["grep -n db01 hosts.txt", "echo 4 > db_line.txt"],
                  ["vim hosts.txt", "/db01", ":q", "echo 5 > db_line.txt"]],
        "expected_files": {"hosts.txt": _HOSTS_LIST, "db_line.txt": "4\n"},
        "checks_commands": [["vim hosts.txt", "vi hosts.txt"]],
        "hints": ["vim の画面の左に行番号が出ます。検索して位置を確かめましょう。",
                  "/文字 で検索できます。うっかり変えてしまったら :q! で「保存せずに閉じる」ができます。",
                  "vim hosts.txt → /db01 → :q で閉じ、echo 4 > db_line.txt。"],
        "explanation": "設定ファイルは「見るだけ」のつもりで開いて、誤操作で壊すことがよくあります。"
                       "保存しない限り元のままなので、迷ったら :q! で捨てて閉じる、が一番安全な逃げ道です。",
        "practice": ["6-6", "2-1"],
    },
    {
        "id": "fes-config-03",
        "level": 1,
        "title": "ログの細かさを1か所だけ変える",
        "brief": "app.conf の log_level を debug から info に変えてください。よく似た名前の debug_toolbar の行を含め、"
                 "ほかの行は変えてはいけません。",
        "initial_packages": _VIM,
        "files": {"app.conf": _APP_LOG},
        "solution": ["vim app.conf", ":%s/=debug/=info/", ":wq"],
        "alt_solutions": [["vim app.conf", ":3", ":s/debug/info/", ":wq"],
                          ["vim app.conf", "/log_level", "dd", "O", "log_level=info", "esc", ":wq"],
                          ["vi app.conf", "/log_level", ":s/debug/info/", "ZZ"]],
        "traps": [["vim app.conf", ":%s/debug/info/g", ":wq"],
                  ["vim app.conf", ":%s/=debug/=info/", ":q!"],
                  ["vim app.conf", ":3", ":s/debug/info/"]],
        "expected_files": {"app.conf": _APP_LOG_FIXED},
        "hints": ["debug という文字は2つの行にあります。どちらを変えるか、目印を考えましょう。",
                  "全体置換なら =debug のように前の文字まで含めて絞ります。行へ移動してから :s で今の行だけ置き換える手もあります。",
                  "vim app.conf → :%s/=debug/=info/ → :wq（または :3 → :s/debug/info/ → :wq）。"],
        "explanation": "全体置換は便利ですが、似た文字を巻き込みやすい道具です。置き換える文字を長めに書くか、"
                       "行を決めてから置き換えると、狙った1か所だけを直せます。",
        "practice": ["6-6"],
    },
    {
        "id": "fes-config-04",
        "level": 1,
        "title": "追記の前に控えを取る",
        "brief": "web.conf の最後の行の下に timeout=30 を1行追加してください。追加する前の内容を web.conf.bak に残します。"
                 "既存の行は変えません。",
        "initial_packages": _VIM,
        "files": {"web.conf": _WEB},
        "solution": ["cp web.conf web.conf.bak", "echo timeout=30 >> web.conf"],
        "alt_solutions": [["cp web.conf web.conf.bak", "vim web.conf", "G", "o", "timeout=30", "esc", ":wq"],
                          ["cp web.conf web.conf.bak", "vim web.conf", ":3", "a", "timeout=30", "esc", "ZZ"]],
        "traps": [["echo timeout=30 >> web.conf", "cp web.conf web.conf.bak"],
                  ["cp web.conf web.conf.bak", "echo timeout=30 > web.conf"],
                  ["cp web.conf web.conf.bak", "vim web.conf", "o", "timeout=30", "esc", ":wq"]],
        "expected_files": {"web.conf": _WEB + "timeout=30\n", "web.conf.bak": _WEB},
        "hints": ["順番が大切です。控えは変更の前にしか取れません。",
                  "cp で控えを作ってから、末尾に足します。>> は追記、> は丸ごと置き換えです。",
                  "cp web.conf web.conf.bak → echo timeout=30 >> web.conf（vim なら G → o → 入力 → esc → :wq）。"],
        "explanation": "1行足すだけでも、設定は動かなくなることがあります。控えがあれば cp で一瞬で戻せます。"
                       "> と >> の取り違えは設定を丸ごと消す典型的な事故なので、追記は >> と覚えます。",
        "practice": ["1-5", "2-8", "6-6"],
    },
    {
        "id": "fes-config-05",
        "level": 1,
        "title": "コメントと空行を除いて読む",
        "brief": "worker.conf は説明のコメント（# で始まる行）と空行が多く、読みにくくなっています。"
                 "実際に効いている設定の行だけを、元の順番のまま active.conf に保存してください。worker.conf は変えません。",
        "files": {"worker.conf": _WORKER},
        "solution": ["grep -v \"^#\" worker.conf | grep -v \"^$\" > active.conf"],
        "alt_solutions": [["grep -v \"^$\" worker.conf | grep -v \"^#\" > active.conf"],
                          ["cat worker.conf | grep -v \"^#\" | grep -v \"^$\" > active.conf"],
                          ["grep -E \"^[a-z]\" worker.conf > active.conf"]],
        "traps": [["grep \"=\" worker.conf > active.conf"],
                  ["grep -v \"^#\" worker.conf > active.conf"],
                  ["grep -v \"^#\" worker.conf | grep -v \"^$\" | sort > active.conf"]],
        "expected_files": {"worker.conf": _WORKER, "active.conf": _WORKER_ACTIVE},
        "hints": ["「含まない行」を取り出す grep の使い方を、2回つなげます。",
                  "grep -v は一致しない行を出します。^# は「# で始まる」、^$ は「空の行」です。",
                  "grep -v \"^#\" worker.conf | grep -v \"^$\" > active.conf。"],
        "explanation": "実務の設定ファイルは説明だらけで、本当に効いている行は数行ということがよくあります。"
                       "「= を含む行」のような雑な絞り方だと、コメントの中の例まで拾ってしまう点に注意します。",
        "practice": ["2-1", "2-5"],
    },
    {
        "id": "fes-config-06",
        "level": 1,
        "title": "秘密の設定を自分だけのものにする",
        "brief": ".env と、以前に作られた控えの .env.bak には、パスワード（訓練用のダミー）が入っています。"
                 "どちらも所有者だけが読み書きできる 600 にしてください。中身は変えません。最後に ls で権限の表示を確かめます。",
        "files": {".env": _ENV_06, ".env.bak": _ENV_06},
        "solution": ["chmod 600 .env", "chmod 600 .env.bak", "ls -la"],
        "alt_solutions": [["ls -la", "chmod 600 .env.bak", "chmod 600 .env", "ls -al"],
                          ["chmod 600 .env", "ls -l .env", "chmod 600 .env.bak", "ls -l .env.bak"]],
        "traps": [["chmod 600 .env", "chmod 600 .env.bak"],
                  ["chmod 644 .env", "chmod 644 .env.bak", "ls -la"],
                  ["chmod 600 .env", "ls -la"]],
        "expected_files": {".env": _ENV_06, ".env.bak": _ENV_06},
        "expected_modes": {".env": 0o600, ".env.bak": 0o600},
        "checks_commands": [["ls -la", "ls -al", "ls -l -a", "ls -a -l", "ls -l .env", "ls -la .env", "ls -al .env",
                             "ls -l .env.bak"]],
        "hints": ["中身は変えず、権限だけを変えます。. で始まるファイルは ls に -a を付けないと見えません。",
                  "chmod 600 は所有者だけ読み書きです。控えのファイルも同じ秘密を持っています。",
                  "chmod 600 .env → chmod 600 .env.bak → ls -la で両方が -rw------- になったか確かめます。"],
        "explanation": ".env のような秘密を含む設定は、他人に読まれないよう 600 にするのが基本です。"
                       "本体だけ守って控えを読めるままにしておく、はよくある見落としです。変えたら ls -l で表示を確かめます。",
        "practice": ["3-1", "3-2", "1-3"],
    },
    {
        "id": "fes-config-07",
        "level": 1,
        "title": "スクリプトと説明書の権限を整える",
        "brief": "deploy.sh と backup.sh は、所有者が読み書き実行でき、ほかの人は読み・実行だけできる 755 にしてください。"
                 "説明書の notes.txt は 644 にします。どのファイルも中身は変えません。",
        "files": {"deploy.sh": _DEPLOY_SH, "backup.sh": _BACKUP_SH, "notes.txt": _NOTES},
        "solution": ["chmod 755 deploy.sh", "chmod 755 backup.sh", "chmod 644 notes.txt"],
        "alt_solutions": [["chmod 644 notes.txt", "chmod 755 backup.sh", "chmod 755 deploy.sh", "ls -l"],
                          ["ls -l", "chmod 755 deploy.sh", "chmod 755 backup.sh", "chmod 644 notes.txt", "ls -l"]],
        "traps": [["chmod u+x deploy.sh", "chmod u+x backup.sh", "chmod 644 notes.txt"],
                  ["chmod 755 deploy.sh", "chmod 755 backup.sh", "chmod 755 notes.txt"],
                  ["chmod 755 deploy.sh", "chmod 644 notes.txt"]],
        "expected_files": {"deploy.sh": _DEPLOY_SH, "backup.sh": _BACKUP_SH, "notes.txt": _NOTES},
        "expected_modes": {"deploy.sh": 0o755, "backup.sh": 0o755, "notes.txt": 0o644},
        "hints": ["数字の権限は「所有者・グループ・ほか」の順に3桁で書きます。",
                  "7 は読み書き実行、5 は読みと実行、4 は読むだけです。u+x では「ほか」に実行が付きません。",
                  "chmod 755 deploy.sh → chmod 755 backup.sh → chmod 644 notes.txt → ls -l で確認。"],
        "explanation": "スクリプトは実行権限がないと動きません。一方で説明書や設定に実行権限は不要です。"
                       "755 と 644 はサーバーで最もよく見る組み合わせなので、ls -l の表示と結び付けて覚えます。",
        "practice": ["3-1", "3-2"],
    },
    {
        "id": "fes-config-08",
        "level": 1,
        "title": "途中の行に設定を差し込む",
        "brief": "features.conf の feature_export=off の行のすぐ下に、feature_dark_mode=on を1行追加してください。"
                 "「ここから下は実験中の機能」のコメントより上に入れる必要があります。ほかの行は変えません。",
        "initial_packages": _VIM,
        "files": {"features.conf": _FEATURES},
        "solution": ["vim features.conf", "/feature_export", "o", "feature_dark_mode=on", "esc", ":wq"],
        "alt_solutions": [["vim features.conf", ":3", "a", "feature_dark_mode=on", "esc", ":x"],
                          ["vim features.conf", ":4", "O", "feature_dark_mode=on", "esc", "ZZ"],
                          ["head -n 3 features.conf > new.conf", "echo feature_dark_mode=on >> new.conf",
                           "tail -n 2 features.conf >> new.conf", "mv new.conf features.conf"]],
        "traps": [["echo feature_dark_mode=on >> features.conf"],
                  ["vim features.conf", "/feature_export", "O", "feature_dark_mode=on", "esc", ":wq"],
                  ["vim features.conf", "o", "feature_dark_mode=on", "esc", ":wq"]],
        "expected_files": {"features.conf": _FEATURES_FIXED},
        "hints": ["末尾に足す >> では、途中には入れられません。入れたい場所へ移動してから書きます。",
                  "vim の o は今の行の下に、O は今の行の上に新しい行を作ります。/文字 や :行番号 で移動できます。",
                  "vim features.conf → /feature_export → o → feature_dark_mode=on → esc → :wq。"],
        "explanation": "設定ファイルはコメントで区切られた「まとまり」になっていることが多く、置く場所にも意味があります。"
                       "移動してから o / O で行を作る操作は、vim での編集の基本形です。",
        "practice": ["6-6"],
    },
    {
        "id": "fes-config-09",
        "level": 1,
        "title": "調査用の設定を1行だけ消す",
        "brief": "db.conf に、調査のために一時的に入れた debug_sql=true の行が残っています。この行だけを削除してください。"
                 "ほかの行と順番はそのままにします。",
        "initial_packages": _VIM,
        "files": {"db.conf": _DB},
        "solution": ["grep -n debug_sql db.conf", "vim db.conf", ":4", "dd", ":wq"],
        "alt_solutions": [["vim db.conf", "/debug_sql", "dd", "ZZ"],
                          ["grep -v debug_sql db.conf > db.new", "mv db.new db.conf"]],
        "traps": [["vim db.conf", "dd", ":wq"],
                  ["vim db.conf", "/debug_sql", "dd", ":q!"],
                  ["vim db.conf", "/debug_sql", "dd", "u", ":wq"]],
        "expected_files": {"db.conf": _DB_FIXED},
        "hints": ["まず消したい行の位置を確かめ、その行へ移動してから消します。",
                  "grep -n で行番号が分かります。vim では :行番号 か /文字 で移動し、dd で今の行を消します。",
                  "vim db.conf → :4（または /debug_sql）→ dd → :wq。"],
        "explanation": "dd は「今カーソルがある行」を消します。開いた直後は1行目にいるので、移動を忘れると見出しを消してしまいます。"
                       "消しすぎたときは u で1つ戻せます。",
        "practice": ["6-6", "2-1"],
    },
    # ------------------------------------------------------------------ ★2
    {
        "id": "fes-config-10",
        "level": 2,
        "title": "Web サーバーの待ち受けポートを変える",
        "brief": "site.conf の listen 80; を listen 8080; に変えてください。変更前の内容は site.conf.bak に残します。"
                 "編集には vim を使いますが、この環境にはまだ入っていません。proxy_pass の行など、ほかの行は変えません。",
        "files": {"site.conf": _SITE},
        "solution": ["sudo apt update", "sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf",
                     ":%s/listen 80;/listen 8080;/", ":wq"],
        "alt_solutions": [["cp site.conf site.conf.bak", "sudo apt update", "sudo apt install -y vim", "vim site.conf",
                           "/listen", ":s/80/8080/", ":x"],
                          ["sudo apt update", "sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf",
                           ":3", "dd", "O", "    listen 8080;", "esc", ":wq"]],
        "traps": [["sudo apt update", "sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf",
                   ":%s/80/8080/g", ":wq"],
                  ["sudo apt update", "sudo apt install vim", "vim site.conf", ":%s/listen 80;/listen 8080;/", ":wq",
                   "cp site.conf site.conf.bak"],
                  ["sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf",
                   ":%s/listen 80;/listen 8080;/", ":wq"]],
        "expected_files": {"site.conf": _SITE_FIXED, "site.conf.bak": _SITE},
        "packages": _VIM,
        "hints": ["道具を用意する → 控えを取る → 直す、の順です。80 という文字はほかの行にも含まれています。",
                  "apt は一覧の更新（update）をしてから追加（install）します。置換は listen 80; のように長めに書くか、行へ移動して :s を使います。",
                  "sudo apt update → sudo apt install vim → cp site.conf site.conf.bak → vim site.conf → :%s/listen 80;/listen 8080;/ → :wq。"],
        "explanation": "nginx のような Web サーバーの設定では、ポート番号の数字が別の行（転送先など）にも現れます。"
                       ":%s/80/8080/g のような短い置換は 8000 を 808000 に変えてしまい、サーバーが起動しなくなります。",
        "practice": ["6-6", "3-4", "1-5"],
    },
    {
        "id": "fes-config-11",
        "level": 2,
        "title": "行を複製してサーバーを1台増やす",
        "brief": "負荷分散先の一覧 hosts.txt に、新しいサーバー「192.0.2.13  web03」（間は半角スペース2つ）を追加してください。"
                 "web02 の行のすぐ下に入れ、web02 の行はそのまま残します。",
        "initial_packages": _VIM,
        "files": {"hosts.txt": _LB},
        "solution": ["vim hosts.txt", "/web02", "yy", "p", ":s/.12/.13/", ":s/web02/web03/", ":wq"],
        "alt_solutions": [["vim hosts.txt", ":3", "o", "192.0.2.13  web03", "esc", ":wq"],
                          ["vim hosts.txt", ":4", "O", "192.0.2.13  web03", "esc", "ZZ"],
                          ["head -n 3 hosts.txt > new.txt", "echo \"192.0.2.13  web03\" >> new.txt",
                           "tail -n 1 hosts.txt >> new.txt", "mv new.txt hosts.txt"]],
        "traps": [["vim hosts.txt", "/web02", "yy", "p", ":%s/web02/web03/g", ":%s/.12/.13/g", ":wq"],
                  ["echo \"192.0.2.13  web03\" >> hosts.txt"],
                  ["vim hosts.txt", "/web02", "yy", "p", ":wq"]],
        "expected_files": {"hosts.txt": _LB_FIXED},
        "hints": ["似た行があるときは、写してから違う部分だけ直すと打ち間違いが減ります。",
                  "vim の yy で今の行をコピー、p で下に貼り付けます。貼り付けた行の上で :s を使えば、その行だけ置き換わります。",
                  "vim hosts.txt → /web02 → yy → p → :s/.12/.13/ → :s/web02/web03/ → :wq。"],
        "explanation": "サーバー一覧や許可リストは、既存の行を複製して書き換えるのが定番です。"
                       "ただし複製した後に全体置換をすると、元の行まで書き換わってしまいます。今の行だけを直す :s を使い分けます。",
        "practice": ["6-6"],
    },
    {
        "id": "fes-config-12",
        "level": 2,
        "title": ".env を新しく作って守る",
        "brief": "アプリ用の .env を新しく作ってください。中身は次の3行です：APP_ENV=training、API_TOKEN=" + _DUMMY +
                 "（訓練用のダミー）、LOG_LEVEL=info。秘密を含むので、所有者だけが読み書きできる権限にします。",
        "initial_packages": _VIM,
        "solution": ["vim .env", "i", "APP_ENV=training", "API_TOKEN=" + _DUMMY, "LOG_LEVEL=info", "esc", ":wq",
                     "chmod 600 .env"],
        "alt_solutions": [["touch .env", "chmod 600 .env", "vim .env", "i", "APP_ENV=training", "API_TOKEN=" + _DUMMY,
                           "LOG_LEVEL=info", "esc", ":x", "ls -la"],
                          ["echo APP_ENV=training > .env", "echo API_TOKEN=" + _DUMMY + " >> .env",
                           "echo LOG_LEVEL=info >> .env", "chmod 600 .env"]],
        "traps": [["echo APP_ENV=training > .env", "echo API_TOKEN=" + _DUMMY + " > .env",
                   "echo LOG_LEVEL=info > .env", "chmod 600 .env"],
                  ["vim .env", "i", "APP_ENV=training", "API_TOKEN=" + _DUMMY, "LOG_LEVEL=info", "esc", ":wq"],
                  ["vim .env", "i", "APP_ENV=training", "API_TOKEN=" + _DUMMY, "LOG_LEVEL=info", "esc", ":wq",
                   "chmod 644 .env"]],
        "expected_files": {".env": _ENV_12},
        "expected_modes": {".env": 0o600},
        "hints": ["中身を書くことと、読める人を絞ることの2つが必要です。",
                  "vim で i を押して3行書き、:wq で保存します。権限は 600 が「所有者だけ読み書き」です。",
                  "vim .env → i → 3行入力 → esc → :wq → chmod 600 .env（先に touch と chmod をしても構いません）。"],
        "explanation": ".env はデータベースや外部サービスの鍵を置く定番の場所です。作った直後はほかの人も読める権限なので、"
                       "600 にするところまでが「作る」作業です。先に空ファイルを 600 にしてから書くと、秘密が見える瞬間もなくなります。",
        "practice": ["6-6", "3-2", "2-8"],
    },
    {
        "id": "fes-config-13",
        "level": 2,
        "title": "定期ジョブを1つだけ一時停止する",
        "brief": "cron.txt（crontab と同じ形式）のうち、cleanup.sh を毎時動かしている行だけを、行頭に「# 」（# と半角スペース）を"
                 "付けてコメントにし、止めてください。行は消さずに残します。編集前の内容は cron.txt.bak に残します。",
        "initial_packages": _VIM,
        "files": {"cron.txt": _CRON},
        "solution": ["cp cron.txt cron.txt.bak", "vim cron.txt", "/cleanup", ":s/0/# 0/", ":wq"],
        "alt_solutions": [["cp cron.txt cron.txt.bak", "vim cron.txt", ":3", "dd", "O",
                           "# 0 * * * * /home/learner/bin/cleanup.sh", "esc", ":wq"],
                          ["cp cron.txt cron.txt.bak", "vim cron.txt", ":%s/0 * * * */# 0 * * * */", "ZZ"]],
        "traps": [["cp cron.txt cron.txt.bak", "vim cron.txt", "/cleanup", "dd", ":wq"],
                  ["vim cron.txt", "/cleanup", ":s/0/# 0/", ":wq", "cp cron.txt cron.txt.bak"],
                  ["cp cron.txt cron.txt.bak", "vim cron.txt", ":%s/0/# 0/g", ":wq"]],
        "expected_files": {"cron.txt": _CRON_FIXED, "cron.txt.bak": _CRON},
        "hints": ["消すのではなく、コメントにして「止めたことが分かる」形で残します。",
                  "/cleanup で行へ移動し、今の行だけを置き換える :s で行頭の 0 を「# 0」にできます。全体置換は数字を巻き込みます。",
                  "cp cron.txt cron.txt.bak → vim cron.txt → /cleanup → :s/0/# 0/ → :wq。"],
        "explanation": "一時停止したい定期ジョブは、消さずにコメントアウトするのが実務の作法です。"
                       "あとで再開するときも、何を止めていたのかがひと目で分かります。",
        "practice": ["6-6", "1-5"],
    },
    {
        "id": "fes-config-14",
        "level": 2,
        "title": "壊れた設定を控えから戻して直す",
        "brief": "誰かが app.conf を壊してしまいました（log_level が空です）。調査のため、壊れた今の内容を app.conf.broken として残し、"
                 "app.conf は控えの app.conf.bak の内容に戻してください。そのうえで app.conf の port を 8081 に変えます。"
                 "app.conf.bak は控えとしてそのまま残します。",
        "initial_packages": _VIM,
        "files": {"app.conf": _BROKEN, "app.conf.bak": _GOOD},
        "solution": ["mv app.conf app.conf.broken", "cp app.conf.bak app.conf", "vim app.conf", ":%s/8080/8081/", ":wq"],
        "alt_solutions": [["cp app.conf app.conf.broken", "cp app.conf.bak app.conf", "vim app.conf", "/port",
                           ":s/8080/8081/", "ZZ"],
                          ["cp app.conf app.conf.broken", "cp app.conf.bak app.conf", "vim app.conf", ":2", "dd", "O",
                           "port=8081", "esc", ":wq"]],
        "traps": [["mv app.conf app.conf.broken", "mv app.conf.bak app.conf", "vim app.conf", ":%s/8080/8081/", ":wq"],
                  ["cp app.conf.bak app.conf", "cp app.conf app.conf.broken", "vim app.conf", ":%s/8080/8081/", ":wq"],
                  ["cp app.conf app.conf.broken", "vim app.conf", ":%s/8080/8081/", ":wq"]],
        "expected_files": {"app.conf": _GOOD_FIXED, "app.conf.bak": _GOOD, "app.conf.broken": _BROKEN},
        "hints": ["「壊れた物を残す」「控えから戻す」「直す」の3つを、上書きで情報を失わない順にこなします。",
                  "先に壊れた app.conf を別名で残し、cp で控えを本体へ写します。mv で控えを動かすと控えが無くなります。",
                  "mv app.conf app.conf.broken → cp app.conf.bak app.conf → vim app.conf → :%s/8080/8081/ → :wq。"],
        "explanation": "控えは「戻す」ために取るものです。戻すときに mv を使うと控え自体が消え、次に失敗したとき戻れません。"
                       "壊れた状態も原因調査の材料になるので、上書きする前に別名で残します。",
        "practice": ["1-5", "1-4", "6-6"],
    },
    {
        "id": "fes-config-15",
        "level": 2,
        "title": "有効なフラグを行番号つきで報告する",
        "brief": "flags.conf のうち、値が true になっている有効な設定行だけを、flags.conf での行番号つき（例：2:名前=true）で"
                 "report.txt に保存してください。コメント行は含めません。flags.conf は変えません。",
        "files": {"flags.conf": _FLAGS},
        "solution": ["grep -n \"=true\" flags.conf | grep -v \"#\" > report.txt"],
        "alt_solutions": [["grep -n true flags.conf | grep -v \"#\" > report.txt"],
                          ["grep -n \"true$\" flags.conf > report.txt"],
                          ["cat -n flags.conf", "grep -n true flags.conf | grep -v old_banner > report.txt"]],
        "traps": [["grep -n true flags.conf > report.txt"],
                  ["grep true flags.conf | grep -v \"#\" > report.txt"],
                  ["grep -v \"#\" flags.conf | grep -n true > report.txt"]],
        "expected_files": {"flags.conf": _FLAGS, "report.txt": _FLAGS_REPORT},
        "hints": ["行番号は、元のファイルを最初に読んだときに付けないと、ずれてしまいます。",
                  "grep -n で行番号が付きます。その結果をもう一度 grep -v に通してコメントを除きます。",
                  "grep -n \"=true\" flags.conf | grep -v \"#\" > report.txt。"],
        "explanation": "「何行目に何があるか」を添えた報告は、相手が vim の :行番号 ですぐ確かめられるので親切です。"
                       "先にコメントを除いてから -n を付けると、番号が元のファイルとずれる点が落とし穴です。",
        "practice": ["2-1", "2-5", "6-6"],
    },
    {
        "id": "fes-config-16",
        "level": 2,
        "title": "見本から本番用の .env を作る",
        "brief": "見本の .env.example をもとに .env を作ってください。.env では APP_ENV を production に、API_KEY を "
                 + _DUMMY + "（訓練用のダミー）に、LOG_LEVEL を warn に変えます。1行目のコメントは残します。"
                 "見本の .env.example は変えずに残し、.env は所有者だけが読み書きできる権限にします。",
        "initial_packages": _VIM,
        "files": {".env.example": _ENV_EXAMPLE},
        "solution": ["cp .env.example .env", "vim .env", ":%s/development/production/", ":%s/CHANGE_ME/" + _DUMMY + "/",
                     ":%s/=debug/=warn/", ":wq", "chmod 600 .env"],
        "alt_solutions": [["cp .env.example .env", "chmod 600 .env", "vim .env", ":2", "dd", "dd", "dd", "o",
                           "APP_ENV=production", "API_KEY=" + _DUMMY, "LOG_LEVEL=warn", "esc", ":wq", "ls -la"],
                          ["cp .env.example .env", "vim .env", "/APP_ENV", ":s/development/production/", "j",
                           ":s/CHANGE_ME/" + _DUMMY + "/", "j", ":s/debug/warn/", ":x", "chmod 600 .env"]],
        "traps": [["mv .env.example .env", "vim .env", ":%s/development/production/", ":%s/CHANGE_ME/" + _DUMMY + "/",
                   ":%s/=debug/=warn/", ":wq", "chmod 600 .env"],
                  ["cp .env.example .env", "vim .env", ":%s/development/production/", ":%s/CHANGE_ME/" + _DUMMY + "/",
                   ":%s/=debug/=warn/", ":wq"],
                  ["vim .env.example", ":%s/development/production/", ":%s/CHANGE_ME/" + _DUMMY + "/",
                   ":%s/=debug/=warn/", ":wq", "cp .env.example .env", "chmod 600 .env"]],
        "expected_files": {".env.example": _ENV_EXAMPLE, ".env": _ENV_PROD},
        "expected_modes": {".env": 0o600},
        "hints": ["見本はコピーして使います。見本そのものを直したり、動かしたりはしません。",
                  "cp で .env を作り、vim の :%s で3か所を置き換えます。最後に権限を 600 にします。",
                  "cp .env.example .env → vim .env → :%s/development/production/ → :%s/CHANGE_ME/" + _DUMMY +
                  "/ → :%s/=debug/=warn/ → :wq → chmod 600 .env。"],
        "explanation": "多くのアプリは .env.example を見本として配り、各自がコピーして値を入れます。"
                       "見本は全員で共有するものなので書き換えず、本物の値を入れた .env だけを 600 で守ります。",
        "practice": ["1-5", "6-6", "3-2"],
    },
    {
        "id": "fes-config-17",
        "level": 2,
        "title": "同じ名前の設定をセクションで見分ける",
        "brief": "deploy.ini には [staging] と [production] の2つのセクションがあり、どちらにも port=8080 があります。"
                 "[production] の port だけを 8443 に変えてください。[staging] の設定は変えません。",
        "initial_packages": _VIM,
        "files": {"deploy.ini": _INI},
        "solution": ["vim deploy.ini", "/[production]", "j", "j", ":s/8080/8443/", ":wq"],
        "alt_solutions": [["grep -n port deploy.ini", "vim deploy.ini", ":8", ":s/8080/8443/", ":wq"],
                          ["vim deploy.ini", "G", ":s/8080/8443/", "ZZ"],
                          ["cat -n deploy.ini", "vim deploy.ini", ":8", "dd", "o", "port=8443", "esc", ":wq"]],
        "traps": [["vim deploy.ini", ":%s/8080/8443/g", ":wq"],
                  ["vim deploy.ini", "/port", ":s/8080/8443/", ":wq"],
                  ["vim deploy.ini", ":4", ":s/8080/8443/", ":wq"]],
        "expected_files": {"deploy.ini": _INI_FIXED},
        "hints": ["同じ行が2つあるので、全体置換や最初に見つかった行の置換では区別できません。",
                  "セクション名 [production] を検索してから下へ移動するか、grep -n で行番号を調べて :行番号 で飛びます。",
                  "vim deploy.ini → /[production] → j → j → :s/8080/8443/ → :wq（:8 で直接飛んでも構いません）。"],
        "explanation": "ini 形式や nginx の設定では、同じ名前の項目がセクションごとに何度も出てきます。"
                       "本番だけ直すつもりで検証環境まで変えてしまう事故を防ぐには、「どのまとまりの何行目か」を確かめてから直します。",
        "practice": ["6-6", "2-1"],
    },
    {
        "id": "fes-config-18",
        "level": 2,
        "title": "スクリプトを書き足して自分だけ実行できるようにする",
        "brief": "書きかけの rotate.sh（1行目の #!/bin/sh だけがあります）に、vim を使って2行目 echo rotate logs training を書き足してください。"
                 "所有者にだけ実行権限を追加し（ほかの権限はそのまま）、最後に ls -l で確かめます。"
                 "ソフトの一覧は更新済みですが、vim はまだ入っていません。",
        "apt_updated": True,
        "files": {"rotate.sh": _ROTATE_HEAD},
        "solution": ["sudo apt install vim", "vim rotate.sh", "o", "echo rotate logs training", "esc", ":wq",
                     "chmod u+x rotate.sh", "ls -l rotate.sh"],
        "alt_solutions": [["sudo apt install -y vim", "vi rotate.sh", "G", "a", "echo rotate logs training", "esc",
                           ":x", "chmod u+x rotate.sh", "ls -l"],
                          ["sudo apt update", "sudo apt install vim", "ls -l", "chmod u+x rotate.sh", "vim rotate.sh",
                           "dd", "i", "#!/bin/sh", "echo rotate logs training", "esc", "ZZ", "ls -l rotate.sh"]],
        "traps": [["echo echo rotate logs training >> rotate.sh", "chmod u+x rotate.sh", "ls -l rotate.sh"],
                  ["sudo apt install vim", "vim rotate.sh", "o", "echo rotate logs training", "esc", ":wq",
                   "chmod 755 rotate.sh", "ls -l rotate.sh"],
                  ["sudo apt install vim", "vim rotate.sh", "i", "echo rotate logs training", "esc", ":wq",
                   "chmod u+x rotate.sh", "ls -l rotate.sh"],
                  ["sudo apt install vim", "vim rotate.sh", "o", "echo rotate logs training", "esc", ":wq",
                   "chmod u+x rotate.sh"]],
        "expected_files": {"rotate.sh": _ROTATE},
        "expected_modes": {"rotate.sh": 0o744},
        "packages": _VIM,
        "checks_commands": [["ls -l rotate.sh", "ls -l", "ls -la", "ls -al"]],
        "hints": ["一覧の更新は済んでいるので、追加するだけで vim が使えます。権限は「所有者にだけ足す」です。",
                  "vim の o は今の行の下に書き始めます（i だと上に入ってしまいます）。u+x は所有者（user）に実行（x）を足す書き方です。",
                  "sudo apt install vim → vim rotate.sh → o → echo rotate logs training → esc → :wq → chmod u+x rotate.sh → ls -l rotate.sh。"],
        "explanation": "数字で 755 と書くとほかの人の権限まで決め直してしまいます。「今の権限に実行だけ足したい」ときは u+x が正確です。"
                       "ls -l で -rwxr--r-- のように所有者の欄にだけ x が付いたことを確かめます。",
        "practice": ["6-6", "3-1", "3-4"],
    },
    {
        "id": "fes-config-19",
        "level": 2,
        "title": "読み込み順を入れ替える",
        "brief": "main.conf は上の行から順に設定を読み込みます。上書き用の include override.conf; の行が一番上にあるため、"
                 "効いていません。この行を一番下へ移し、ほかの2行の順番はそのままにしてください。編集前の内容は main.conf.bak に残します。",
        "initial_packages": _VIM,
        "files": {"main.conf": _MAIN},
        "solution": ["cp main.conf main.conf.bak", "vim main.conf", "/override", "dd", "G", "p", ":wq"],
        "alt_solutions": [["cp main.conf main.conf.bak", "vim main.conf", ":2", "dd", ":3", "p", "ZZ"],
                          ["cp main.conf main.conf.bak", "vim main.conf", ":2", "dd", "G", "o", "include override.conf;",
                           "esc", ":wq"],
                          ["cp main.conf main.conf.bak", "grep -v override main.conf > main.new",
                           "echo \"include override.conf;\" >> main.new", "mv main.new main.conf"]],
        "traps": [["cp main.conf main.conf.bak", "vim main.conf", "/override", "dd", ":wq"],
                  ["cp main.conf main.conf.bak", "vim main.conf", "/override", "dd", "p", ":wq"],
                  ["vim main.conf", "/override", "dd", "G", "p", ":wq", "cp main.conf main.conf.bak"]],
        "expected_files": {"main.conf": _MAIN_FIXED, "main.conf.bak": _MAIN},
        "hints": ["vim の dd は「消す」だけでなく「切り取り」でもあります。消した行は貼り付けられます。",
                  "dd で切り取ったら、最後の行へ移動してから p で下に貼り付けます。移動せずに p すると位置がずれます。",
                  "cp main.conf main.conf.bak → vim main.conf → /override → dd → G → p → :wq。"],
        "explanation": "nginx の include や多くの設定は、後から読んだものが前を上書きします。行の並び順そのものが意味を持つので、"
                       "dd と p による「行の移動」は打ち直しより確実な直し方です。",
        "practice": ["6-6", "1-5"],
    },
    # ------------------------------------------------------------------ ★3
    {
        "id": "fes-config-20",
        "level": 3,
        "title": "総合：新しいアプリサーバーの初期設定",
        "brief": "新しいサーバーにアプリを置きました。次をすべて行ってください。"
                 "(1) app.conf の元の内容を app.conf.bak に残す。(2) vim で app.conf の port を 3000 に、log_level を info に変える。"
                 "(3) app.conf の最後に timeout=30 を1行足す。(4) secrets.env は所有者だけが読み書きできる 600 に、"
                 "start.sh は 755 にする。(5) 最後に ls -l で権限を確かめる。この環境にはまだ vim が入っていません。",
        "files": {"app.conf": _APP20, "secrets.env": _SECRETS20, "start.sh": _START20},
        "solution": ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "vim app.conf",
                     ":%s/8080/3000/", ":%s/debug/info/", "G", "o", "timeout=30", "esc", ":wq",
                     "chmod 600 secrets.env", "chmod 755 start.sh", "ls -l"],
        "alt_solutions": [["cp app.conf app.conf.bak", "sudo apt update", "sudo apt install -y vim", "vim app.conf",
                           ":2", ":s/8080/3000/", "j", ":s/debug/info/", ":x", "echo timeout=30 >> app.conf",
                           "chmod 755 start.sh", "chmod 600 secrets.env", "ls -l"],
                          ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "chmod 600 secrets.env",
                           "vim app.conf", "/port", "dd", "dd", "O", "port=3000", "log_level=info", "esc", "G", "a",
                           "timeout=30", "esc", ":w", ":q", "chmod 755 start.sh", "ls -l start.sh", "ls -l secrets.env"]],
        "traps": [["sudo apt update", "sudo apt install vim", "vim app.conf", ":%s/8080/3000/", ":%s/debug/info/", "G", "o",
                   "timeout=30", "esc", ":wq", "cp app.conf app.conf.bak", "chmod 600 secrets.env", "chmod 755 start.sh",
                   "ls -l"],
                  ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "vim app.conf",
                   ":%s/8080/3000/", ":%s/debug/info/", "G", "o", "timeout=30", "esc", ":wq",
                   "chmod 600 secrets.env", "chmod u+x start.sh", "ls -l"],
                  ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "vim app.conf",
                   ":%s/8080/3000/", ":%s/debug/info/", "G", "o", "timeout=30", "esc", ":wq",
                   "chmod 600 secrets.env", "chmod 755 start.sh"]],
        "expected_files": {"app.conf": _APP20_FIXED, "app.conf.bak": _APP20, "secrets.env": _SECRETS20,
                           "start.sh": _START20},
        "expected_modes": {"secrets.env": 0o600, "start.sh": 0o755},
        "packages": _VIM,
        "checks_commands": [["ls -l", "ls -la", "ls -al", "ls -l secrets.env", "ls -l start.sh"]],
        "hints": ["道具の用意 → 控え → 編集 → 権限 → 確認、と作業を区切って1つずつ片付けます。",
                  "sudo apt update と install で vim を入れ、cp で控えを取ってから :%s や :行番号 + :s で直します。末尾の追加は G → o か >> です。",
                  "sudo apt update → sudo apt install vim → cp app.conf app.conf.bak → vim app.conf → :%s/8080/3000/ → "
                  ":%s/debug/info/ → G → o → timeout=30 → esc → :wq → chmod 600 secrets.env → chmod 755 start.sh → ls -l。"],
        "explanation": "新しいサーバーの初期設定は、この順番の繰り返しです。どれか1つでも抜けると、"
                       "「戻せない」「起動しない」「秘密が読める」といった問題になります。最後の ls -l は、自分の作業を自分で検査する習慣です。",
        "practice": ["6-6", "3-4", "1-5", "3-2"],
    },
    {
        "id": "fes-config-21",
        "level": 3,
        "title": "総合：2つのサービスのログ設定を揃える",
        "brief": "conf フォルダの api.conf と worker.conf は、どちらも log_level=debug のままで、ログが溢れています。"
                 "(1) 編集の前に backup フォルダを作り、2つのファイルをそれぞれ同じ名前で backup の中へ控える。"
                 "(2) 両方の log_level を warn に変える。api.conf の debug_endpoint の行は変えない。"
                 "(3) 確認として、conf の中の2ファイルから log_level の行をファイル名と行番号つきで探し、その結果を levels.txt に保存する。",
        "initial_packages": _VIM,
        "files": {"conf/api.conf": _API21, "conf/worker.conf": _WORKER21},
        "solution": ["mkdir backup", "cp conf/api.conf conf/worker.conf backup/", "vim conf/api.conf",
                     ":%s/=debug/=warn/", ":wq", "vim conf/worker.conf", ":%s/=debug/=warn/", ":wq",
                     "grep -n log_level conf/*.conf > levels.txt"],
        "alt_solutions": [["mkdir backup", "cp conf/api.conf backup/api.conf", "cp conf/worker.conf backup/worker.conf",
                           "cd conf", "vim api.conf", ":3", ":s/debug/warn/", ":x", "vim worker.conf", "G",
                           ":s/debug/warn/", "ZZ", "cd ..", "grep -n log_level conf/*.conf > levels.txt"],
                          ["mkdir -p backup", "cp conf/*.conf backup", "vim conf/api.conf", "/log_level", "dd", "O",
                           "log_level=warn", "esc", ":wq", "vim conf/worker.conf", "/log_level", ":s/debug/warn/", ":wq",
                           "grep -n log_level conf/api.conf conf/worker.conf > levels.txt", "cat levels.txt"]],
        "traps": [["mkdir backup", "cp conf/api.conf conf/worker.conf backup/", "vim conf/api.conf",
                   ":%s/debug/warn/g", ":wq", "vim conf/worker.conf", ":%s/debug/warn/g", ":wq",
                   "grep -n log_level conf/*.conf > levels.txt"],
                  ["vim conf/api.conf", ":%s/=debug/=warn/", ":wq", "vim conf/worker.conf", ":%s/=debug/=warn/", ":wq",
                   "mkdir backup", "cp conf/api.conf conf/worker.conf backup/",
                   "grep -n log_level conf/*.conf > levels.txt"],
                  ["mkdir backup", "cp conf/api.conf conf/worker.conf backup/", "vim conf/api.conf",
                   ":%s/=debug/=warn/", ":wq", "grep -n log_level conf/*.conf > levels.txt"],
                  ["mkdir backup", "cp conf/api.conf conf/worker.conf backup/", "vim conf/api.conf",
                   ":%s/=debug/=warn/", ":wq", "vim conf/worker.conf", ":%s/=debug/=warn/", ":wq",
                   "grep log_level conf/*.conf > levels.txt"]],
        "expected_files": {"backup/api.conf": _API21, "backup/worker.conf": _WORKER21, "conf/api.conf": _API21_FIXED,
                           "conf/worker.conf": _WORKER21_FIXED, "levels.txt": _LEVELS21},
        "hints": ["複数ファイルの作業は、全部控える → 全部直す → まとめて確かめる、の順に進めると漏れません。",
                  "cp は最後にフォルダを書くと、複数のファイルをまとめてその中へ写せます。grep に複数のファイルを渡すとファイル名が付き、-n で行番号も付きます。",
                  "mkdir backup → cp conf/api.conf conf/worker.conf backup/ → 各ファイルを vim で :%s/=debug/=warn/ → :wq → "
                  "grep -n log_level conf/*.conf > levels.txt。"],
        "explanation": "同じ役割の設定が複数のサービスに散らばっていると、1つだけ直し忘れることがよくあります。"
                       "最後に grep で全ファイルを横断して確かめれば、直し漏れや巻き込みがひと目で分かります。",
        "practice": ["1-5", "2-1", "2-6", "6-6"],
    },
    {
        "id": "fes-config-22",
        "level": 3,
        "title": "総合：メンテナンスに入る準備",
        "brief": "今夜メンテナンスを行います。次をすべて行ってください。"
                 "(1) cron.txt を cron.txt.bak に控えてから、send_mail.sh を動かす行だけ、行頭に「# 」を付けて止める。"
                 "(2) flags.conf の maintenance を on に、signup を off に変える。"
                 "(3) notice.sh を新しく作る（1行目 #!/bin/sh、2行目 echo maintenance training）。権限は 755 にする。"
                 "(4) 作業記録 work.log の既存の行は残し、次の行に maintenance started を追記する。",
        "initial_packages": _VIM,
        "files": {"cron.txt": _CRON22, "flags.conf": _FLAGS22, "work.log": _WORKLOG22},
        "solution": ["cp cron.txt cron.txt.bak", "vim cron.txt", "/send_mail", ":s/0 9/# 0 9/", ":wq",
                     "vim flags.conf", ":%s/maintenance=off/maintenance=on/", ":%s/signup=on/signup=off/", ":wq",
                     "vim notice.sh", "i", "#!/bin/sh", "echo maintenance training", "esc", ":wq",
                     "chmod 755 notice.sh", "echo maintenance started >> work.log"],
        "alt_solutions": [["cp cron.txt cron.txt.bak", "vim cron.txt", ":3", "dd", "O",
                           "# 0 9 * * * /home/learner/bin/send_mail.sh", "esc", ":x", "vim flags.conf", ":2", "dd", "dd",
                           "o", "maintenance=on", "signup=off", "esc", ":x", "echo \"#!/bin/sh\" > notice.sh",
                           "echo echo maintenance training >> notice.sh", "chmod 755 notice.sh", "ls -l",
                           "echo maintenance started >> work.log"],
                          ["echo maintenance started >> work.log", "cp cron.txt cron.txt.bak", "vim notice.sh", "i",
                           "#!/bin/sh", "echo maintenance training", "esc", "ZZ", "chmod 755 notice.sh", "vim flags.conf",
                           "/maintenance", ":s/off/on/", "j", ":s/on/off/", "ZZ", "vim cron.txt", "/send_mail",
                           ":s/0/# 0/", "ZZ"]],
        "traps": [["cp cron.txt cron.txt.bak", "vim cron.txt", "/send_mail", "dd", ":wq",
                   "vim flags.conf", ":%s/maintenance=off/maintenance=on/", ":%s/signup=on/signup=off/", ":wq",
                   "vim notice.sh", "i", "#!/bin/sh", "echo maintenance training", "esc", ":wq",
                   "chmod 755 notice.sh", "echo maintenance started >> work.log"],
                  ["cp cron.txt cron.txt.bak", "vim cron.txt", "/send_mail", ":s/0 9/# 0 9/", ":wq",
                   "vim flags.conf", ":%s/=off/=on/", ":%s/=on/=off/", ":wq",
                   "vim notice.sh", "i", "#!/bin/sh", "echo maintenance training", "esc", ":wq",
                   "chmod 755 notice.sh", "echo maintenance started >> work.log"],
                  ["cp cron.txt cron.txt.bak", "vim cron.txt", "/send_mail", ":s/0 9/# 0 9/", ":wq",
                   "vim flags.conf", ":%s/maintenance=off/maintenance=on/", ":%s/signup=on/signup=off/", ":wq",
                   "vim notice.sh", "i", "#!/bin/sh", "echo maintenance training", "esc", ":wq",
                   "echo maintenance started > work.log"],
                  ["cp cron.txt cron.txt.bak", "vim cron.txt", "/send_mail", ":s/0 9/# 0 9/", ":wq",
                   "vim flags.conf", ":%s/maintenance=off/maintenance=on/", ":%s/signup=on/signup=off/", ":wq",
                   "vim notice.sh", "i", "#!/bin/sh", "echo maintenance training", "esc", ":wq",
                   "echo maintenance started >> work.log"]],
        "expected_files": {"cron.txt": _CRON22_FIXED, "cron.txt.bak": _CRON22, "flags.conf": _FLAGS22_FIXED,
                           "notice.sh": _NOTICE_SH, "work.log": _WORKLOG22 + "maintenance started\n"},
        "expected_modes": {"notice.sh": 0o755},
        "hints": ["4つの作業は互いに独立しています。1つ終えるごとに cat で確かめてから次へ進むと安心です。",
                  "cron は /send_mail で移動して :s で行頭に「# 」を足します。flags.conf は =on や =off だけで置き換えると、もう片方の行まで巻き込みます。記録は >> で追記します。",
                  "cp cron.txt cron.txt.bak → vim cron.txt → /send_mail → :s/0 9/# 0 9/ → :wq → vim flags.conf → "
                  ":%s/maintenance=off/maintenance=on/ → :%s/signup=on/signup=off/ → :wq → vim notice.sh で2行書く → "
                  "chmod 755 notice.sh → echo maintenance started >> work.log。"],
        "explanation": "メンテナンス前の作業は「止める」「切り替える」「知らせる」「記録する」の組み合わせです。"
                       "定期ジョブは消さずにコメントで止め、記録は上書きせず追記する。どれも、あとで元へ戻すための作法です。",
        "practice": ["6-6", "1-5", "2-8", "3-1"],
    },
    {
        "id": "fes-config-23",
        "level": 3,
        "title": "総合：秘密の行を共有設定から移す",
        "brief": "みんなが読む共有設定 shared.conf に、パスワードの行 db_password=...（訓練用のダミー）が紛れ込んでいます。"
                 "(1) まず shared.conf を shared.conf.bak に控える。控えにも秘密が含まれるので、控えは 600 にする。"
                 "(2) shared.conf から db_password の行だけを削除し、同じ行を secret.conf の最後に追加する。"
                 "(3) secret.conf は 600、shared.conf は 644 にする。(4) 最後に ls -l で権限を確かめる。",
        "initial_packages": _VIM,
        "files": {"shared.conf": _SHARED, "secret.conf": _SECRET23},
        "solution": ["cp shared.conf shared.conf.bak", "chmod 600 shared.conf.bak", "vim shared.conf", "/db_password",
                     "dd", ":wq", "vim secret.conf", "G", "o", "db_password=" + _DUMMY, "esc", ":wq",
                     "chmod 600 secret.conf", "chmod 644 shared.conf", "ls -l"],
        "alt_solutions": [["cp shared.conf shared.conf.bak", "chmod 600 shared.conf.bak",
                           "grep db_password shared.conf >> secret.conf", "grep -v db_password shared.conf > shared.new",
                           "mv shared.new shared.conf", "chmod 644 shared.conf", "chmod 600 secret.conf", "ls -l"],
                          ["cp shared.conf shared.conf.bak", "chmod 600 shared.conf.bak", "chmod 600 secret.conf",
                           "echo db_password=" + _DUMMY + " >> secret.conf", "vim shared.conf", ":4", "dd", "ZZ",
                           "chmod 644 shared.conf", "ls -l shared.conf", "ls -l secret.conf", "ls -l shared.conf.bak"]],
        "traps": [["cp shared.conf shared.conf.bak", "chmod 600 shared.conf.bak", "vim shared.conf", "/db_password",
                   "dd", ":wq", "chmod 600 secret.conf", "chmod 644 shared.conf", "ls -l"],
                  ["cp shared.conf shared.conf.bak", "vim shared.conf", "/db_password", "dd", ":wq", "vim secret.conf",
                   "G", "o", "db_password=" + _DUMMY, "esc", ":wq", "chmod 600 secret.conf", "chmod 644 shared.conf",
                   "ls -l"],
                  ["cp shared.conf shared.conf.bak", "chmod 600 shared.conf.bak", "vim shared.conf", "/db_password",
                   "dd", ":wq", "vim secret.conf", "o", "db_password=" + _DUMMY, "esc", ":wq",
                   "chmod 600 secret.conf", "chmod 644 shared.conf"],
                  ["vim shared.conf", "/db_password", "dd", ":wq", "cp shared.conf shared.conf.bak",
                   "chmod 600 shared.conf.bak", "echo db_password=" + _DUMMY + " >> secret.conf",
                   "chmod 600 secret.conf", "chmod 644 shared.conf", "ls -l"]],
        "expected_files": {"shared.conf": _SHARED_FIXED, "shared.conf.bak": _SHARED, "secret.conf": _SECRET23_FIXED},
        "expected_modes": {"shared.conf": 0o644, "shared.conf.bak": 0o600, "secret.conf": 0o600},
        "checks_commands": [["ls -l", "ls -la", "ls -al", "ls -l secret.conf", "ls -l shared.conf.bak"]],
        "hints": ["「移す」は「写す」と「消す」の組み合わせです。控えの中身も秘密を含むことを忘れずに。",
                  "vim の /db_password と dd で行を消し、secret.conf では G → o で末尾に書きます。grep と >> でも写せます。",
                  "cp shared.conf shared.conf.bak → chmod 600 shared.conf.bak → vim shared.conf → /db_password → dd → :wq → "
                  "vim secret.conf → G → o → 行を入力 → esc → :wq → chmod 600 secret.conf → chmod 644 shared.conf → ls -l。"],
        "explanation": "秘密が紛れ込んだ設定を直すときは、控えや作業途中のファイルにも秘密が残ることを意識します。"
                       "「控えを取ったら控えも守る」「共有するものと秘密を分ける」は、情報漏えいを防ぐ基本の考え方です。",
        "practice": ["6-6", "3-2", "2-1", "1-5"],
    },
    {
        "id": "fes-config-24",
        "level": 3,
        "title": "総合：Web サーバーの公開準備",
        "brief": "公開前の site.conf を仕上げます。vim を使ってください（一覧の更新は済んでいますが、vim はまだ入っていません）。"
                 "(1) 編集前の内容を site.conf.bak に残す。(2) upstream の 192.0.2.12:3000 の行のすぐ下に、"
                 "同じ形で 192.0.2.13:3000 の行を足す（先頭の空白4つも同じ）。(3) server_name を old.training.example から "
                 "shop.training.example に変える。(4) 仕上がった site.conf から、# を含む行と空行を除いた行だけを、"
                 "順番のまま active.conf に保存する。",
        "apt_updated": True,
        "files": {"site.conf": _NGX},
        "solution": ["sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf", "/192.0.2.12", "yy", "p",
                     ":s/.12:/.13:/", ":%s/old.training/shop.training/", ":wq",
                     "grep -v \"#\" site.conf | grep -v \"^$\" > active.conf"],
        "alt_solutions": [["cp site.conf site.conf.bak", "sudo apt install vim", "vim site.conf", ":4", "o",
                           "    server 192.0.2.13:3000;", "esc", "/server_name", ":s/old/shop/", ":x",
                           "cat site.conf | grep -v \"#\" | grep -v \"^$\" > active.conf"],
                          ["sudo apt install -y vim", "cp site.conf site.conf.bak", "vim site.conf", "/server_name",
                           "dd", "O", "    server_name shop.training.example;", "esc", ":5", "O",
                           "    server 192.0.2.13:3000;", "esc", ":w", ":q",
                           "grep -v \"^$\" site.conf | grep -v \"#\" > active.conf"]],
        "traps": [["sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf", "/192.0.2.12", "yy", "p",
                   ":s/.12:/.13:/", ":%s/old.training/shop.training/", ":wq",
                   "grep -v \"^#\" site.conf | grep -v \"^$\" > active.conf"],
                  ["sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf", "/192.0.2.12", "yy", "p",
                   ":s/.12:/.13:/", ":%s/old.training/shop.training/", ":wq",
                   "grep -v \"#\" site.conf.bak | grep -v \"^$\" > active.conf"],
                  ["sudo apt install vim", "cp site.conf site.conf.bak", "vim site.conf", "/192.0.2.12", "o",
                   "server 192.0.2.13:3000;", "esc", ":%s/old.training/shop.training/", ":wq",
                   "grep -v \"#\" site.conf | grep -v \"^$\" > active.conf"],
                  ["sudo apt install vim", "vim site.conf", "/192.0.2.12", "yy", "p", ":s/.12:/.13:/",
                   ":%s/old.training/shop.training/", ":wq", "cp site.conf site.conf.bak",
                   "grep -v \"#\" site.conf | grep -v \"^$\" > active.conf"]],
        "expected_files": {"site.conf": _NGX_FIXED, "site.conf.bak": _NGX, "active.conf": _NGX_ACTIVE},
        "packages": _VIM,
        "hints": ["編集の順番は 道具 → 控え → 直す → 仕上がりを読む、です。字下げされたコメント行もあることに注意します。",
                  "似た行は yy と p で複製し、:s でその行だけ直すと空白まで揃います。^# は行頭の # しか見ないので、字下げしたコメントには \"#\" で絞ります。",
                  "sudo apt install vim → cp site.conf site.conf.bak → vim site.conf → /192.0.2.12 → yy → p → :s/.12:/.13:/ → "
                  ":%s/old.training/shop.training/ → :wq → grep -v \"#\" site.conf | grep -v \"^$\" > active.conf。"],
        "explanation": "nginx のような設定では、字下げや ; の1文字が崩れるだけで起動しなくなります。"
                       "既存の行を複製して直すと形が揃い、仕上げにコメントと空行を除いて読み直すと、実際に効く設定を落ち着いて確認できます。",
        "practice": ["6-6", "3-4", "2-1", "2-5", "1-5"],
    },
]
