"""説明付き基礎から自力の実践へ進む、状態判定型の総合復習。

既存59ミッションとは別枠。engine.readiness が模擬ターミナルで使う。
認証情報・秘密設定・指紋の例は教材用のダミーであり、外部サービスには対応しない。
"""

_FINGERPRINT = "SHA256:TRAINING-NOT-A-REAL-FINGERPRINT"

SCENARIOS = [
    {
        "id": "ready-01",
        "title": "引き継ぎメモを整理する",
        "brief": "散らかった引き継ぎメモを整理してください。handover フォルダを作り、draft.txt のコピーを handover/note.txt に置きます。元の draft.txt は archive.txt へ名前を変えます。最後に handover/status.txt を作り、ready という1行を保存してください。",
        "files": {"draft.txt": "サーバーの確認をお願いします。\n"},
        "solution": ["mkdir handover", "cp draft.txt handover/note.txt", "mv draft.txt archive.txt", "echo ready > handover/status.txt"],
        "expected_files": {"handover/note.txt": "サーバーの確認をお願いします。\n", "archive.txt": "サーバーの確認をお願いします。\n", "handover/status.txt": "ready\n"},
        "absent": ["draft.txt"],
        "hints": ["作業用フォルダを作り、コピーと名前変更を使い分けます。", "mkdir はフォルダ作成、cp は元を残すコピー、mv は移動や名前変更です。", "mkdir handover → cp draft.txt handover/note.txt → mv draft.txt archive.txt。文字保存には echo ready > handover/status.txt を使えます。"],
        "explanation": "cp はコピー元を残し、mv はコピー元の名前や場所を変えます。出力を保存する > は、保存先が既存なら内容を置き換えます。作業後は ls と cat で確かめましょう。",
        "practice": ["1-4", "1-5", "1-8"],
    },
    {
        "id": "ready-02",
        "title": "障害ログだけを報告に残す",
        "brief": "app.log から、大文字の ERROR を含む行だけを抜き出し、errors.txt に保存してください。正常な行と警告の行は報告に含めません。元のログはそのまま残します。",
        "files": {"app.log": "INFO start\nERROR database unavailable\nWARN retrying\nERROR request failed\nINFO stopped\n"},
        "solution": ["grep ERROR app.log > errors.txt"],
        "expected_files": {"app.log": "INFO start\nERROR database unavailable\nWARN retrying\nERROR request failed\nINFO stopped\n", "errors.txt": "ERROR database unavailable\nERROR request failed\n"},
        "hints": ["行を探すコマンドの出力を、報告用ファイルへ保存します。", "grep 文字列 ファイル で一致する行を表示し、> 保存先 で保存できます。", "grep ERROR app.log > errors.txt。そのあと cat errors.txt で結果を確認できます。"],
        "explanation": "検索と出力先の切り替えを組み合わせると、必要な行だけをファイルへ保存できます。grep に -i を付けると大文字小文字の区別が変わるため、報告の条件を先に確認します。",
        "practice": ["2-1", "2-2", "2-5"],
    },
    {
        "id": "ready-03",
        "title": "公開してよい権限に直す",
        "brief": "secret.conf は所有者だけが読み書きできる600にしてください。run.sh は所有者に実行権限を追加し、744にしてください。中身は変更せず、実行する必要もありません。設定値は訓練用のダミーです。",
        # パスワードではなく、秘密設定を扱う手順のための無効なダミー文字列。
        "files": {"secret.conf": "TRAINING_VALUE=not-a-real-secret\n", "run.sh": "#!/bin/sh\necho training\n"},
        "solution": ["chmod 600 secret.conf", "chmod u+x run.sh"],
        "expected_files": {"secret.conf": "TRAINING_VALUE=not-a-real-secret\n", "run.sh": "#!/bin/sh\necho training\n"},
        "expected_modes": {"secret.conf": 0o600, "run.sh": 0o744},
        "hints": ["中身とアクセス権限は別の情報です。実行はせず、権限だけを変えます。", "chmod 600 ファイル は所有者の読み書きだけ、chmod u+x ファイル は所有者に実行権限を追加します。", "chmod 600 secret.conf と chmod u+x run.sh を実行し、ls -l で確認しましょう。"],
        "explanation": "600は所有者だけの読み書き、744は所有者の読み書き実行と、その他の読み取りです。chmod はファイル内容を変えません。実際の秘密鍵や設定も、必要な人だけが読めるようにします。",
        "practice": ["3-1", "3-2", "4-7"],
    },
    {
        "id": "ready-04",
        "title": "設定変更の前に退避する",
        "brief": "app.conf の元の設定を app.conf.bak に残してから、app.conf の内容を mode=training という1行へ変更してください。退避したファイルには mode=old が残っている必要があります。",
        "files": {"app.conf": "mode=old\n"},
        "solution": ["cp app.conf app.conf.bak", "echo mode=training > app.conf"],
        "expected_files": {"app.conf.bak": "mode=old\n", "app.conf": "mode=training\n"},
        "hints": ["変更した後では、古い設定をコピーできません。順序を考えましょう。", "最初に cp で元ファイルを退避し、次に > で本体だけを書き換えます。", "cp app.conf app.conf.bak → echo mode=training > app.conf。両方の内容を cat で比べましょう。"],
        "explanation": "設定変更では、まず戻せる状態を作ります。cp で元の内容を退避し、変更後は本体とバックアップの両方を確認すると、取り違えに気づけます。",
        "practice": ["1-5", "2-8", "EX-1"],
    },
    {
        "id": "ready-05",
        "title": "必要な道具を追加する",
        "brief": "作業場所の構造を表示できるように、訓練用の tree を追加してください。ソフトの情報一覧を更新する操作と、本体を追加する操作を使い分けます。実際のPCのソフトは変更されません。",
        "files": {"project/note.txt": "構造を確認する練習です。\n"},
        "solution": ["sudo apt update", "sudo apt install tree", "tree"],
        "expected_files": {"project/note.txt": "構造を確認する練習です。\n"},
        "packages": ["tree"],
        "checks_commands": ["tree"],
        "hints": ["一覧の更新だけでは、ソフト本体は追加されません。管理者として行う操作です。", "sudo apt update で一覧を更新し、sudo apt install 名前 で本体を追加します。", "sudo apt update → sudo apt install tree → tree の順に実行します。"],
        "explanation": "update は取得可能なソフトの情報一覧、install は指定したソフトの追加です。tree を追加したあと実際に使い、目的の作業ができるかまで確認します。",
        "practice": ["3-4", "3-7"],
    },
    {
        "id": "ready-06",
        "title": "接続先を確かめて成果物を受け取る",
        "brief": "管理者から別の経路で受け取った server-fingerprint.txt の指紋を読み、訓練サーバー training-server の接続確認表示と比べてください。一致する場合だけ learner として接続し、接続先名と server-note.txt の内容を確認します。接続を閉じて手元へ戻り、サーバーの download.txt を手元の received.txt としてコピーしてください。実通信は行いません。",
        "files": {"server-fingerprint.txt": "training-server: " + _FINGERPRINT + "\nこれは教材専用の架空の指紋です。\n"},
        "remote_files": {"server-note.txt": "接続先は training-server です。\n", "download.txt": "訓練サーバーの成果物です。\n"},
        "solution": ["cat server-fingerprint.txt", "ssh learner@training-server", "yes", "hostname", "cat server-note.txt", "exit", "scp learner@training-server:download.txt received.txt"],
        "expected_files": {"received.txt": "訓練サーバーの成果物です。\n"},
        "checks_commands": ["cat server-fingerprint.txt", "hostname", "cat server-note.txt"],
        "require_disconnected": True,
        "hints": ["手元側と接続先を区別します。事前の指紋を読み、接続先で確認して、手元へ戻ってから受け取ります。", "cat で指紋を読む → ssh learner@training-server → 一致を確認して yes → hostname と cat → exit → scp で受信です。", "接続を閉じたあと、scp learner@training-server:download.txt received.txt で手元に保存できます。秘密鍵や実際の認証情報は入力しません。"],
        "explanation": "SSHでは接続相手を確認してからユーザー認証を行います。接続後は hostname で操作先を意識し、作業が終わったら exit で手元へ戻ります。scp はリモート側を user@host:path で指定し、コピー元とコピー先の順で書きます。",
        "practice": ["4-7", "4-8"],
    },
    {
        "id": "ready-07",
        "title": "探した場所を引き継ぎに残す",
        "brief": "今いる場所の下から target.txt という名前のファイルを探し、そのパスを found.txt に保存してください。資料の中身は変更しません。担当者が次に同じ場所を見つけられる報告を作る練習です。",
        "files": {"records/target.txt": "探す対象の資料です。\n", "records/other.txt": "別の資料です。\n"},
        "solution": ["find . -name target.txt > found.txt"],
        "expected_files": {"records/target.txt": "探す対象の資料です。\n", "found.txt": "./records/target.txt\n"},
        "hints": ["ファイル名で探す操作と、表示をファイルへ保存する操作を組み合わせます。", "find . -name 名前 の出力を > found.txt で保存できます。", "find . -name target.txt > found.txt を実行し、cat found.txt でパスを確認しましょう。"],
        "explanation": "find の検索結果も、標準出力を持つコマンドの結果です。> を組み合わせれば報告用に残せます。先頭の ./ は、現在地を基準にしたパスであることを表します。",
        "practice": ["2-1", "2-6", "EX-2"],
    },
    {
        "id": "ready-08",
        "title": "変更・退避・確認をひと通り行う",
        "brief": "サービス設定の更新を引き継ぎます。service.conf を service.conf.bak へ退避し、本体を environment=training に変更してください。作業記録 work.log には既存の started を残して completed を次の行へ追記します。不要な scratch.txt だけを削除し、設定本体の権限を600にします。最後に手元側のコンピューター名を確認して、作業を終えてください。",
        "files": {"service.conf": "environment=old\n", "work.log": "started\n", "scratch.txt": "消してよい練習用メモです。\n"},
        "solution": ["cp service.conf service.conf.bak", "echo environment=training > service.conf", "echo completed >> work.log", "rm scratch.txt", "chmod 600 service.conf", "hostname"],
        "expected_files": {"service.conf.bak": "environment=old\n", "service.conf": "environment=training\n", "work.log": "started\ncompleted\n"},
        "expected_modes": {"service.conf": 0o600},
        "absent": ["scratch.txt"],
        "checks_commands": ["hostname"],
        "require_disconnected": True,
        "hints": ["変更前の退避、上書きと追記の使い分け、削除対象、権限を順番に確認します。", "cp で退避、echo と > で設定変更、>> で記録を追記し、rm と chmod で仕上げます。", "cp service.conf service.conf.bak → echo environment=training > service.conf → echo completed >> work.log → rm scratch.txt → chmod 600 service.conf → hostname。"],
        "explanation": "実務では単独のコマンドより、目的に合わせて複数の操作を組み合わせます。元へ戻せるよう退避し、不要なものだけを消し、必要な権限に直して、最後に状態を確認する流れが基本です。",
        "practice": ["1-5", "2-1", "3-1", "3-8"],
    },
]

for scenario in SCENARIOS:
    scenario.setdefault("expected_modes", {})
    scenario.setdefault("packages", [])
    scenario.setdefault("remote_files", {})
    scenario.setdefault("require_disconnected", False)
    scenario.setdefault("checks_commands", [])
    scenario.setdefault("absent", [])
