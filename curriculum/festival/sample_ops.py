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
        "brief": "app.conf の port=8080 を port=80 に直してください。直す前に、元の内容を app.conf.bak に残します。"
                 "この環境にはまだ vim が入っていないので、使えるようにしてから編集してください。ほかの行は変えません。",
        "files": {"app.conf": APP_CONF},
        "solution": ["sudo apt update", "sudo apt install vim", "cp app.conf app.conf.bak", "vim app.conf",
                     ":%s/8080/80/g", ":wq"],
        "alt_solutions": [["cp app.conf app.conf.bak", "sudo apt update", "sudo apt install -y vim", "vim app.conf",
                           "/port", ":s/8080/80/", "ZZ"]],
        "traps": [["sudo apt update", "sudo apt install vim", "vim app.conf", ":%s/8080/80/g", ":wq",
                   "cp app.conf app.conf.bak"]],
        "expected_files": {"app.conf": _PORT_FIXED, "app.conf.bak": APP_CONF},
        "packages": ["vim"],
        "hints": ["順番が大切です。道具を用意する → 元を残す → 直す。", "sudo apt update と sudo apt install vim で vim を入れ、cp で退避してから vim で開きます。",
                  "vim app.conf を開いたら :%s/8080/80/g で置き換え、:wq で保存して閉じます。"],
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
        "hints": ["まず一覧を見て、%CPU が大きいものを探します。", "ps aux で PID を調べて kill します。止まったかも ps で確かめます。",
                  "kill 4321 で止まらなければ kill -9 4321。rsync（4400）は止めません。"],
        "explanation": "kill は合図を送るだけで、止まったかどうかは別に確かめます。TERM で止まらないときだけ -9 を使い、無関係なプロセスは巻き込みません。",
        "practice": ["3-5", "3-7"],
    },
    {
        "id": "fes-sample_ops-03",
        "level": 1,
        "title": "古いログを片付けて容量を空ける",
        "brief": "ディスクが逼迫しています。logs フォルダにある old- で始まる古いログだけを削除してください。"
                 "今使っている current.log は残します。作業の前に df -h で空き容量を確認してください。",
        "files": dict(_LOGS),
        "solution": ["df -h", "du -sh logs", "rm logs/old-*.log"],
        "alt_solutions": [["df -h", "rm logs/old-2024-01.log logs/old-2024-02.log"], ["df -h", "cd logs", "rm old-*", "cd .."]],
        "traps": [["rm logs/old-*.log"], ["df -h", "rm logs/*.log"]],
        "absent": ["logs/old-2024-01.log", "logs/old-2024-02.log"],
        "expected_files": {"logs/current.log": "今のログ\n"},
        "checks_commands": [["df -h", "df"]],
        "hints": ["まず容量を確かめる、が依頼の条件です。", "df -h で全体、du -sh logs でフォルダの大きさが分かります。",
                  "df -h を実行してから、rm logs/old-*.log で古いものだけ消します。"],
        "explanation": "ワイルドカードで消すときは、消してはいけないものが一致しないか先に確かめます。*.log では current.log まで消えてしまいます。",
        "practice": ["3-8", "2-6"],
    },
]
