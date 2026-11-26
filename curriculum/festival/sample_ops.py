"""課題まつり：運用の基本3題（ほかのパックを書くときの見本も兼ねる）。"""
from curriculum.advanced_lessons import APP_CONF

PACK_TITLE = "運用の第一歩"

_PORT_FIXED = APP_CONF.replace("port=8080", "port=80")
_RUNAWAY = {"pid": 4321, "user": "learner", "cmd": "python3 runaway.py", "cpu": 99.0, "mem": 12.5,
            "ignores_term": True}
_BACKUP = {"pid": 4400, "user": "learner", "cmd": "rsync -a data/ backup/", "cpu": 3.0, "mem": 1.0}
_LOGS = {"logs/old-2024-01.log": "古いログ\n" * 800, "logs/old-2024-02.log": "古いログ\n" * 800,
         "logs/current.log": "今のログ\n"}

SCENARIOS = [
    {
        "id": "fes-sample_ops-01",
        "level": 2,
        "title": "vim を入れてポート番号を直す",
        "brief": 'アプリの設定ファイル の port=8080 を port=80 に直してください。直す前に、元の内容を app.conf.bak に残します。この環境にはまだ vim が入っていないので、使えるようにしてから編集してください。ほかの行は変えません。',
        "files": {"app.conf": APP_CONF},
        "solution": ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "vim app.conf",
                     ":%s/8080/80/g", ":wq"],
        "alt_solutions": [["cp app.conf app.conf.bak", "sudo apt update", "sudo apt install -y vim", "vim app.conf",
                           "/port", ":s/8080/80/", "ZZ"]],
        "traps": [["sudo apt update", "sudo apt install vim", "vim app.conf", ":%s/8080/80/g", ":wq",
                   "cp app.conf app.conf.bak"]],
        "expected_files": {"app.conf": _PORT_FIXED, "app.conf.bak": APP_CONF},
        "packages": ["vim"],
        "hints": ["順番が大切です。道具を用意する → 元を残す → 直す。",
                  "ls と cat で対象の名前・場所・内容を確かめます。apt の update と install（sudo 付き）で vim を入れ、cp で app.conf を退避してから vim で開きます。",
                  "vim の中では : で始まるコマンドを使います。置換は s、全体に効かせるのは %、保存して閉じるのは wq です。"],
        "explanation": "変更前の退避は、変更した後では取れません。編集の道具がなければ自分で入れ、退避してから直す、が安全な順番です。",
        "practice": ["6-6", "1-5"],
    },
    {
        "id": "fes-sample_ops-02",
        "level": 2,
        "title": "重いプロセスだけを止める",
        "brief": "サーバーが重くなっています。CPU を使い切っているプロセスを見つけて止めてください。"
                 "ただし、動いているバックアップ（rsync）や、システムの cron は止めてはいけません。",
        "processes": [_RUNAWAY, _BACKUP],
        "solution": ["ps aux", "kill 4321", "ps aux | grep runaway", "kill -9 4321"],
        "alt_solutions": [["pgrep runaway", "kill -9 4321"], ["ps aux | grep python3", "kill -KILL 4321"]],
        "traps": [["kill 4321"], ["kill -9 4321 4400"], ["sudo kill -9 4321 845"]],
        "process_gone": ["runaway.py"],
        "process_kept": ["rsync", "cron"],
        "hints": ["まず一覧を見て、%CPU が大きいものを探します。",
                  "ps の aux 表示で PID を調べて kill します。止まったかも ps で確かめます。",
                  "穏やかな kill で止まらなければ、-9 を付けて強く止めます。rsync（4400）は止めません。"],
        "explanation": "kill は合図を送るだけで、止まったかどうかは別に確かめます。TERM で止まらないときだけ -9 を使い、無関係なプロセスは巻き込みません。",
        "practice": ["3-5", "3-7"],
    },
    {
        "id": "fes-sample_ops-03",
        "level": 1,
        "title": "古いログを片付けて容量を空ける",
        "brief": 'ディスクが逼迫しています。ログ用フォルダを探し、古いログだけを削除してください。使用中のログは残します。作業の前にディスク全体の空き容量を確認してください。',
        "files": dict(_LOGS),
        "solution": ["df -h", "du -sh logs", "rm logs/old-*.log"],
        "alt_solutions": [["df -h", "rm logs/old-2024-01.log logs/old-2024-02.log"], ["df -h", "cd logs", "rm old-*", "cd .."]],
        "traps": [["rm logs/old-*.log"], ["df -h", "rm logs/*.log"]],
        "absent": ["logs/old-2024-01.log", "logs/old-2024-02.log"],
        "expected_files": {"logs/current.log": "今のログ\n"},
        "checks_commands": [["df -h", "df"]],
        "hints": ["まず容量を確かめる、が依頼の条件です。",
                  "ls と cat で対象の名前・場所・内容を確かめます。df で全体、du に -sh を付けるとフォルダの大きさが分かります。",
                  "df を実行してから、old- で始まる .log だけに一致するパターンで rm します。current.log が巻き込まれないよう注意します。"],
        "explanation": "ワイルドカードで消すときは、消してはいけないものが一致しないか先に確かめます。*.log では current.log まで消えてしまいます。",
        "practice": ["3-8", "2-6"],
    },
]
