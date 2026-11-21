"""作成したバックアップを検査し、元のデータを保ちながら復元・整理する。"""

PACK_TITLE = "バックアップの検証と復元"

CONFIG = {'config/app.ini': 'mode=production\nport=8080\n',
          'config/database.ini': 'host=db.test\nname=dojo\n'}
OLD = {'config/app.ini': 'mode=production\nport=8000\n',
       'config/database.ini': 'host=old-db.test\nname=dojo\n'}
LOGS = {'logs/empty.tmp': '', 'logs/sub/empty.tmp': '',
        'logs/pending.tmp': 'incomplete upload; keep\n',
        'logs/empty.log': '', 'logs/access.log': 'INFO keep this audit trail\n'}


def task(number, title, brief, solution, alt_solutions, traps, thinking, tools, explanation, **extra):
    return dict(id=f'fes-backup_ops-{number:02d}', title=title, level=3, brief=brief,
                solution=solution, alt_solutions=alt_solutions, traps=traps,
                hints=[thinking, tools, '入力例: ' + ' → '.join(solution)],
                explanation=explanation, practice=['4-8'], **extra)


SCENARIOS = [
    task(1, '設定のバックアップを作り、内容の一覧を残す',
         'config 以下の設定2ファイルを、パス config/... を保った gzip 圧縮アーカイブ config.tar.gz に保存してください。'
         'アーカイブは設定ファイルだけを含め、notes.txt は含めません。元ファイルをすべて保ち、'
         'アーカイブ内の一覧を list.txt に保存してください。',
         ['tar -czf config.tar.gz config', 'tar -tf config.tar.gz > list.txt'],
         [['tar --create --gzip --file config.tar.gz config', 'tar -tf config.tar.gz > list.txt']],
         [['touch config.tar.gz', 'echo config > list.txt'],
          ['tar -cf config.tar.gz config', 'tar -tf config.tar.gz > list.txt'],
          ['tar -czf config.tar.gz config notes.txt', 'tar -tf config.tar.gz > list.txt']],
         '保存できたという表示だけでは不十分です。対象を絞って作成し、そのアーカイブを読み直しましょう。',
         'tar の作成・gzip 圧縮・ファイル名の指定と、一覧の出力を保存する操作を組み合わせます。',
         '保存対象以外を含めず、元の設定を保ってバックアップを作成しました。'
         '本番では別媒体への保管と、別の場所への復元試験も行います。',
         files={**CONFIG, 'notes.txt': 'internal memo; keep\n'}, expected_files={**CONFIG, 'notes.txt': 'internal memo; keep\n'},
         expected_archives={'config.tar.gz': CONFIG}, min_lines={'list.txt': 3},
         checks_commands=['tar -tf config.tar.gz > list.txt']),
    task(2, '現行設定を上書きせずに、古いバックアップを復元する',
         'received.tar.gz に古い設定があります。まず中身の一覧を確認し、そのあと restore フォルダに復元してください。'
         '現行の config フォルダは変更しません。復元したアプリ設定を読み、検証記録 restored-setting.txt にその内容を保存してください。'
         'アーカイブ自体も残します。',
         ['tar -tf received.tar.gz', 'mkdir restore', 'tar -xf received.tar.gz -C restore',
          'cat restore/config/app.ini > restored-setting.txt'],
         [['tar -tf received.tar.gz', 'mkdir -p restore', 'tar -xzf received.tar.gz -C restore',
           'cat restore/config/app.ini > restored-setting.txt']],
         [['tar -tf received.tar.gz', 'tar -xf received.tar.gz'],
          ['tar -tf received.tar.gz', 'mkdir restore', 'tar -xf received.tar.gz -C restore',
           'cat config/app.ini > restored-setting.txt']],
         '現行ファイルと復元する内容は違います。まず対象を確認し、専用の場所へ展開して、その場所のファイルを読みます。',
         'tar の一覧と展開を使い分け、-C で復元先を指定します。cat と > で検証記録を残せます。',
         '現行設定を変えずに復元できました。復元後の内容確認によって、ファイル名があるだけの不完全なバックアップも見分けます。',
         files=CONFIG, archives={'received.tar.gz': OLD},
         expected_files={**CONFIG, **{'restore/' + name: text for name, text in OLD.items()},
                         'restored-setting.txt': OLD['config/app.ini']},
         expected_archives={'received.tar.gz': OLD},
         ordered_commands=['tar -tf received.tar.gz', ['tar -xf received.tar.gz -C restore',
                                                     'tar -xzf received.tar.gz -C restore']]),
    task(3, '記録を退避してから、空の一時ファイルだけを整理する',
         'logs 以下を logs-before.tar.gz に丸ごとバックアップしてから、全階層の「0バイトかつ拡張子 .tmp」の通常ファイルだけを削除してください。'
         '中身のある .tmp、空の .log、監査用アクセスログ、フォルダは残します。削除前に候補を確認してください。',
         ['tar -czf logs-before.tar.gz logs', "find logs -type f -name '*.tmp' -size 0c",
          "find logs -type f -name '*.tmp' -size 0c -delete"],
         [['tar -czf logs-before.tar.gz logs', "find logs -type f -name '*.tmp' -size 0c",
           'rm logs/empty.tmp logs/sub/empty.tmp']],
         [["find logs -type f -name '*.tmp' -delete"],
          ['tar -czf logs-before.tar.gz logs', "find logs -type f -name '*.tmp' -delete"],
          ['tar -czf logs-before.tar.gz logs', 'find logs -type f -size 0c -delete']],
         '「一時ファイル」と「空」の両条件が必要です。バックアップ、候補の確認、削除の順番も考えましょう。',
         'tar で退避し、find の -type・-name・-size を合わせます。対象を確認した後に削除します。',
         '名前だけ、サイズだけで削除すると必要なファイルも消えます。複数の条件と退避を組み合わせることで、作業を限定できます。',
         files=LOGS, expected_archives={'logs-before.tar.gz': LOGS},
         expected_modes={'logs': 0o755, 'logs/sub': 0o755},
         expected_files={name: text for name, text in LOGS.items() if name not in ('logs/empty.tmp', 'logs/sub/empty.tmp')},
         absent=['logs/empty.tmp', 'logs/sub/empty.tmp'],
         ordered_commands=['tar -czf logs-before.tar.gz logs', "find logs -type f -name '*.tmp' -size 0c"]),
]
