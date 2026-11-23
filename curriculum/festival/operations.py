"""ユーザー管理と Git を組み合わせた、目的から解く運用課題。"""

PACK_TITLE = "アカウント管理と変更の運用"


def _task(number, title, brief, solution, alternatives, traps, thinking, tools, explanation, **extra):
    return dict(id=f"fes-operations-{number:02d}", level=3, title=title, brief=brief,
                solution=solution, alt_solutions=alternatives, traps=traps,
                hints=[thinking, tools, "入力例: " + " → ".join(solution)],
                explanation=explanation, practice=["6-1"], **extra)


def _departing(data):
    data["groups"]["sudo"]["members"].append("deploy")
    data["groups"]["staff"]["members"].append("deploy")


APP = "port=8080\nmode=production\n"
BROKEN = "port=oops\nmode=production\n"
SCRIPT = "#!/bin/bash\necho release\n"


def _git(*ops):
    return {"identity": True, "ops": list(ops)}


SCENARIOS = [
    _task(1, "新しい担当者に必要な権限だけを渡す",
          'リリース担当 carol を新規登録してください。ホーム作成あり、ログインシェルは /bin/bash、パスワードはロックしたままです。新設する release グループに所属させ、sudo グループには入れません。リリース用スクリプト の所有者を carol、グループを release とし、所有者は全権限、グループは読み取り・実行、その他は権限なしにしてください。',
          ["sudo groupadd release", "sudo useradd -m -s /bin/bash -G release carol",
           "chmod 750 release.sh", "sudo chown carol:release release.sh"],
          [["sudo groupadd release", "sudo useradd -m -s /bin/bash carol", "sudo usermod -aG release carol",
            "chmod u=rwx,g=rx,o= release.sh", "sudo chown carol:release release.sh"]],
          [["sudo groupadd release", "sudo useradd -m -s /bin/bash -G release,sudo carol",
            "sudo chown carol:release release.sh", "chmod 750 release.sh"],
           ["sudo groupadd release", "sudo useradd -m -s /bin/bash -G release carol",
            "sudo chown carol:release release.sh", "chmod 777 release.sh"]],
          "アカウント、所属、所有者、権限は別の設定です。管理者権限を広く渡す必要はありません。",
          'ls と cat で対象の名前・場所・内容を確かめます。groupadd / useradd / usermod / chown / chmod を組み合わせ、id と stat で確認できます。',
          "必要な担当グループだけに所属させます。750 は所有者 rwx、グループ r-x、その他 --- です。",
          files={"release.sh": SCRIPT}, expected_files={"release.sh": SCRIPT},
          expected_modes={"release.sh": 0o750}, expected_owners={"release.sh": "carol:release"},
          expected_users={"carol": {"shell": "/bin/bash", "home_created": True, "locked": True,
                                    "groups": ["release"], "groups_absent": ["sudo"]}}),
    _task(2, "共同作業の権限を整える",
          '既存の developers グループに deploy を追加し、alice と bob の所属も残してください。共同作業用フォルダとその中のメモを探し、所有者を root、グループを developers にそろえます。フォルダは所有者・グループが全権限、その他は権限なし。ファイルは所有者・グループが読み書きでき、その他は権限なしにします。',
          ["sudo usermod -aG developers deploy", "chmod 770 shared", "chmod 660 shared/notes.txt",
           "sudo chown -R root:developers shared"],
          [["sudo gpasswd -a deploy developers", "chmod u=rwx,g=rwx,o= shared", "chmod u=rw,g=rw,o= shared/notes.txt",
            "sudo chown root:developers shared shared/notes.txt"]],
          [["sudo usermod -aG developers deploy", "sudo chown -R root:developers shared",
            "chmod 777 shared", "chmod 666 shared/notes.txt"]],
          "フォルダを通過するには実行権限が必要です。共有ファイルには実行権限を付ける必要はありません。",
          'ls と cat で対象の名前・場所・内容を確かめます。usermod -aG または gpasswd で追加し、chown と chmod で所有者と権限を整えます。',
          "共有ディレクトリとファイルでは必要な権限が違います。グループを追加する際は既存の所属も保ちます。",
          files={"shared/notes.txt": "handover\n"}, expected_files={"shared/notes.txt": "handover\n"},
          expected_modes={"shared": 0o770, "shared/notes.txt": 0o660},
          expected_owners={"shared": "root:developers", "shared/notes.txt": "root:developers"},
          expected_groups={"developers": {"members": ["alice", "bob", "deploy"]}}),
    _task(3, "退任者の権限を回収し、記録は残す",
          'deploy の対話ログインとパスワード認証を止め、sudo グループから外してください。アカウント、staff グループへの所属、引き継ぎ記録のファイル の内容は監査のため残します。ログインシェルは /usr/sbin/nologin にします。パスワードのロックだけでは公開鍵ログインなどを止められない点にも注意してください。',
          ["sudo usermod -L deploy", "sudo usermod -s /usr/sbin/nologin deploy", "sudo gpasswd -d deploy sudo"],
          [["sudo usermod -L -s /usr/sbin/nologin deploy", "sudo gpasswd -d deploy sudo"]],
          [["sudo usermod -L deploy"], ["sudo userdel deploy"]],
          "パスワードのロック、シェルの制限、特権グループからの除外は、それぞれ別の対策です。",
          'ls と cat で対象の名前・場所・内容を確かめます。usermod の -L と -s、gpasswd の -d を使います。削除は要件に合いません。',
          "監査用データを保ちながら権限を回収しました。実環境では既存セッション・SSH鍵・定期実行・サービス用認証も別途確認します。",
          users_setup=_departing, files={"handover.txt": "keep audit evidence\n"},
          expected_files={"handover.txt": "keep audit evidence\n"},
          expected_users={"deploy": {"locked": True, "shell": "/usr/sbin/nologin",
                                     "groups": ["staff"], "groups_absent": ["sudo"]}}),
    _task(4, "秘密情報を含めず変更を記録する",
          '現在のリポジトリのアプリ設定と、新しく作る .gitignore を、メッセージ Release config で最初のコミットにしてください。秘密の環境設定ファイルと、拡張子 .log の全ファイルは除外し、履歴にもステージにも含めません。元ファイルは消さず、最後は main ブランチで未記録の変更をなくします。',
          ["echo .env > .gitignore", 'echo "*.log" >> .gitignore', "git add app.conf .gitignore", 'git commit -m "Release config"'],
          [["echo .env > .gitignore", "echo '*.log' >> .gitignore", "git add .", "git commit -m 'Release config'"]],
          [["git add .", 'git commit -m "Release config"'],
           ["echo .env > .gitignore", 'echo "*.log" >> .gitignore', "git add app.conf", 'git commit -m "Release config"']],
          "共有すべき設定と、秘密・実行時ログを分けます。除外ルールも共有する必要があります。",
          'ls -a で隠れた項目も調べ、ls フォルダ名 や cat で用途と内容を確かめます。.gitignore にパターンを書き、git add の対象と git status を確認してから commit します。',
          "除外ルールは未追跡ファイルに働きます。すでに追跡した秘密情報は除外設定を書くだけでは消えません。",
          cwd="project", initial_packages=["git"],
          git=_git({"init": True}, {"write": {"app.conf": APP, ".env": "TOKEN=training-only\n", "debug.log": "debug\n"}}),
          expected_files={"project/app.conf": APP, "project/.env": "TOKEN=training-only\n", "project/debug.log": "debug\n"},
          expected_git={"project": {"branch": "main", "messages": ["Release config"], "clean": True,
                                    "tracked": {"app.conf": APP, ".gitignore": ".env\n*.log\n"},
                                    "untracked": [".env", "debug.log"], "ignored": [".env", "debug.log", "future.log"]}}),
    _task(5, "変更を別ブランチで記録し、本流へ取り込む",
          '現在のリポジトリの main に最初の設定が記録されています。release ブランチを作って移動し、アプリ設定を port=9090、mode=production の2行に更新してください。メッセージ Change port で1回記録し、main に戻って変更を取り込んでください。release ブランチと最初の履歴も残します。',
          ["git switch -c release", "echo port=9090 > app.conf", "echo mode=production >> app.conf",
           'git commit -am "Change port"', "git switch main", "git merge release"],
          [["git branch release", "git checkout release", "echo port=9090 > app.conf", "echo mode=production >> app.conf",
            "git add app.conf", "git commit -m 'Change port'", "git checkout main", "git merge release"]],
          [["echo port=9090 > app.conf", "echo mode=production >> app.conf", 'git commit -am "Change port"'],
           ["git switch -c release", "echo port=9090 > app.conf", "echo mode=production >> app.conf", 'git commit -am "Change port"']],
          "作業ブランチで記録し、本流に戻って取り込みます。最後にファイルが正しいだけではなく、履歴とブランチも確認します。",
          'ls と cat で対象の名前・場所・内容を確かめます。git switch、commit、merge を使います。取り込みの前に現在地を main に戻します。',
          "ブランチはコミットへの目印です。ここでは main を release まで早送りできるので fast-forward になります。",
          cwd="project", initial_packages=["git"],
          git=_git({"init": True}, {"commit": "Initial config", "files": {"app.conf": APP}}),
          ordered_commands=[["git switch -c release", "git checkout release", "git switch release", "git checkout -b release"],
                            ['git commit -am "Change port"', 'git commit -m "Change port"'],
                            ["git switch main", "git checkout main"], "git merge release"],
          expected_files={"project/app.conf": "port=9090\nmode=production\n"},
          expected_git={"project": {"branch": "main", "messages": ["Change port", "Initial config"], "clean": True,
                                    "branches": ["release"], "same_tip": ["main", "release"],
                                    "tracked": {"app.conf": "port=9090\nmode=production\n"}}}),
    _task(6, "壊れた設定を証拠を残して戻す",
          '現在のリポジトリのアプリ設定に未記録の不正な変更が入りました。現在の内容をリポジトリのすぐ外の incident.txt に保存してから、最後にコミットした内容へ戻してください。新しいコミットは作らず、既存の履歴と main を保ち、未記録の変更もなくします。最後にリポジトリの状態を確認してください。',
          ["cp app.conf ../incident.txt", "git restore app.conf", "git status"],
          [["cp app.conf ../incident.txt", "git checkout -- app.conf", "git status"]],
          [["git restore app.conf"], ["git restore app.conf", "cp app.conf ../incident.txt"]],
          "復旧前の証拠を残す順番が重要です。記録済みの正しい版と、壊れた作業ファイルを区別します。",
          'ls と cat で対象の名前・場所・内容を確かめます。cp でリポジトリの外へ控えを作り、git restore で記録済みの内容を復元できます。',
          "未コミットの変更は restore で失われます。証拠や必要な変更を退避してから戻し、最後に状態を確かめます。",
          cwd="project", initial_packages=["git"],
          git=_git({"init": True}, {"commit": "Initial config", "files": {"app.conf": APP}}, {"write": {"app.conf": BROKEN}}),
          expected_files={"project/app.conf": APP, "incident.txt": BROKEN},
          checks_commands=["git status"],
          expected_git={"project": {"branch": "main", "messages": ["Initial config"], "clean": True}}),
]
