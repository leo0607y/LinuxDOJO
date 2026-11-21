"""バックアップを作って検査・復元し、条件から対象を探す。"""
import shlex
import gzip
import tarfile
from curriculum.lesson_kit import lesson, all_of, content, absent, is_file

UNIT_TITLE = "検索とバックアップ・復元"
ORDER = 10


def typed(check):
    return lambda t: check(shlex.split(t.progress['command_events'][-1]['line']))


FILES = {'project/config.ini': 'mode=production\n', 'project/data.txt': 'important data\n'}
LESSONS = []


def archived(name, files, compressed=False):
    def check(terminal):
        path = terminal.path(name)
        try:
            if compressed and path.read_bytes()[:2] != b'\x1f\x8b':
                return False
            with tarfile.open(path, 'r:*') as bundle:
                actual = {entry.name: bundle.extractfile(entry).read().decode('utf-8')
                          for entry in bundle.getmembers() if entry.isfile()}
            return actual == files
        except (OSError, tarfile.TarError, EOFError, UnicodeError):
            return False
    return check


def gzipped(name, text):
    def check(terminal):
        try:
            with gzip.open(terminal.path(name), 'rt', encoding='utf-8') as stream:
                return stream.read(16 * 1024 * 1024 + 1) == text
        except (OSError, EOFError, UnicodeError):
            return False
    return check


def add(title, explanation, task, command, success, thinking, tool, **extra):
    LESSONS.append(lesson('ex-archive_find-%02d' % (len(LESSONS) + 1), title, explanation, task, command, success,
                          hints=[thinking, tool, '入力例: ' + command], **extra))


add('条件に合う名前を探す',
    'find はフォルダをたどって探す道具です。-name は名前の条件で、* は任意の文字列です。検索条件は引用符で囲んで、シェルが先に広げないようにします。',
    'logs 以下から、拡張子が .log のものを階層の奥まで探しましょう。', "find logs -name '*.log'",
    '深い階層の記録も見つかりました。検索条件を引用符で囲む理由も覚えておきましょう。',
    '一覧では見えない下の階層も含め、名前の末尾で探します。', 'find に、開始場所と -name による名前の条件を渡します。',
    files={'logs/app.log': 'ok\n', 'logs/old/error.log': 'error\n', 'logs/readme.txt': 'notes\n'},
    goal=typed(lambda w: w[:2] == ['find', 'logs'] and '-name' in w and '*.log' in w))
add('種類も条件にする',
    '同じ名前でも、通常ファイルとフォルダは別物です。-type の f は file、d は directory。複数の条件は、両方を満たす対象だけに絞ります。',
    'data 以下から、通常ファイルだけを見つけましょう。', 'find data -type f',
    'フォルダ自体を除外できました。種類を確認すると、後続の処理がより安全になります。',
    '何という名前かではなく、何の種類かで絞りましょう。', 'find の -type に、file の頭文字を指定します。',
    files={'data/one.txt': '1\n', 'data/sub/two.txt': '2\n'}, dirs=['data/empty'],
    goal=typed(lambda w: w[:2] == ['find', 'data'] and w[-2:] == ['-type', 'f']))
add('容量から探す',
    '-size は大きさの条件です。c はバイト、k は1024バイト単位です。先頭の + は指定値より大きいもの、- は小さいものを意味します。',
    'data 以下から、1024バイトより大きい通常ファイルを探しましょう。', 'find data -type f -size +1k',
    '容量を使っている候補を発見しました。削除する前に、中身と用途も確認しましょう。',
    'サイズを比べる条件と、通常ファイルという条件を合わせます。', 'find の -size に + と大きさと単位を指定します。',
    files={'data/big.bin': 'a' * 2048, 'data/small.txt': 'tiny\n'},
    goal=typed(lambda w: w[:2] == ['find', 'data'] and '+1k' in w and '-size' in w and '-type' in w))
add('空ファイルを見つける',
    '0バイトのファイルは、記録の失敗やまだ使われていない出力先の手がかりになります。バイト単位で正確に比較すると、空のものを探せます。',
    'reports 以下から、0バイトの通常ファイルを探しましょう。', 'find reports -type f -size 0c',
    '空ファイルを特定しました。空であることだけで不要とは決めず、作成目的を確認します。',
    '「空」を容量の数字に置き換えて考えましょう。', 'find の種類とサイズを組み合わせます。バイトの単位は c です。',
    files={'reports/empty.txt': '', 'reports/ok.txt': 'complete\n'},
    goal=typed(lambda w: w[:2] == ['find', 'reports'] and '0c' in w and '-size' in w))
add('検索結果を保存する',
    '検索の結果をファイルに残せば、確認・共有・後の作業に使えます。画面への出力は > で保存できました。',
    'logs 以下の通常ファイルの一覧を、inventory.txt に保存しましょう。', 'find logs -type f > inventory.txt',
    '一覧を保存しました。対象の確認記録を残すことは、作業の再現性につながります。',
    '検索の道具と、出力を保存する記号を組み合わせます。', 'find の結果を > で指定ファイルへ送ります。',
    files={'logs/a.log': 'ok\n', 'logs/sub/b.log': 'ok\n'}, remove=['logs', 'inventory.txt'],
    goal=content('inventory.txt', 'logs/a.log\nlogs/sub/b.log\n'))
add('まとめてバックアップする',
    'tar は複数のファイルやフォルダを1つのアーカイブにまとめます。-c は create（作成）、-f はアーカイブのファイル名を指定します。対象はその後に並べます。',
    'project フォルダを、backup.tar という1つのアーカイブに保存しましょう。', 'tar -cf backup.tar project',
    'バックアップを作成しました。作れただけで安心せず、次に中身の一覧と復元を確認します。',
    'まとめる道具に、作成することと保存先を指定します。', 'tar の -c と -f を合わせて使えます。保存先の後ろに対象を置きます。',
    files=FILES, remove=['backup.tar'], goal=archived('backup.tar', FILES))
add('圧縮して保存する',
    'アーカイブと圧縮は別の役割です。tar に -z を付けると gzip 圧縮も行います。拡張子 .tar.gz は、まとめて圧縮したものという目印です。',
    'project を gzip 圧縮した backup.tar.gz として保存しましょう。', 'tar -czf backup.tar.gz project',
    '圧縮バックアップを作りました。圧縮は容量を減らしますが、中身を守る暗号化ではありません。',
    '前のまとめる操作に、圧縮の指定を足しましょう。', 'tar の作成・gzip・ファイル名のオプションは c・z・f です。',
    files=FILES, remove=['backup.tar.gz'], goal=archived('backup.tar.gz', FILES, compressed=True))
add('壊れたアーカイブを見分ける',
    '展開する前に -t（list）で一覧を確認します。単に名前を .tar に変えても、アーカイブにはなりません。読み取れなければ終了コードが0以外になります。',
    'broken.tar の一覧を表示しようとして、正しいアーカイブではないことを確認しましょう。', 'tar -tf broken.tar',
    '読み取りエラーになりました。拡張子だけで信頼せず、バックアップの実体を検証しましょう。',
    'まだ展開せず、一覧を読むだけにします。', 'tar に -t と -f を指定します。',
    files={'broken.tar': 'not an archive\n'}, expected_code=2)
add('1ファイルを圧縮する',
    'gzip は1つのファイルを圧縮します。標準では元のファイルが消えて .gz のファイルになります。元も残したいときは -k（keep）を付けます。',
    'app.log を圧縮し、元のファイルも残しましょう。', 'gzip -k app.log',
    '元と圧縮済みの両方を残しました。-k の有無で元のファイルが残るか変わります。',
    'ファイルを1つ圧縮する道具に、保持する指定を足します。', 'gzip の -k は元のファイルを keep します。',
    files={'app.log': 'INFO ready\n' * 20}, remove=['app.log.gz'], goal=all_of(content('app.log', 'INFO ready\n' * 20), gzipped('app.log.gz', 'INFO ready\n' * 20)))
add('深さを限定する',
    '検索を浅い階層だけで行いたいときは -maxdepth を使います。開始場所が深さ0、その直下が深さ1です。',
    'logs の直下だけから通常ファイルを探しましょう。下のフォルダには入らないでください。', 'find logs -maxdepth 1 -type f',
    '直下だけに絞れました。対象範囲を限定する習慣は、大量のデータを扱うときにも役立ちます。',
    'どこまで深くたどるかを、数字で制限します。', 'find の -maxdepth と種類の条件を使います。',
    files={'logs/a.log': 'ok\n', 'logs/old/b.log': 'ok\n'},
    goal=typed(lambda w: w[:2] == ['find', 'logs'] and '-maxdepth' in w and w[w.index('-maxdepth') + 1] == '1'))
add('展開前に一覧を確認する',
    '受け取ったバックアップは、まず一覧を読みます。展開したときにどの名前で作られるかを確認してから、専用の場所へ戻しましょう。',
    'backup.tar.gz の中身を、展開せず一覧で確認しましょう。', 'tar -tf backup.tar.gz',
    '設定とデータの名前が確認できました。次は本体と分けた復元場所で、実際に読めるか確かめます。',
    '見るだけの操作と、展開する操作を区別しましょう。', 'tar の -t は一覧、-f の後ろにはアーカイブ名です。',
    archives={'backup.tar.gz': FILES})
add('別の場所へ復元する',
    'tar の -x は extract（展開）です。-C は作業場所を変更してから処理する指定です。復元先は先に作り、本番のファイルを上書きしない場所で試します。',
    'backup.tar.gz を、用意された restore フォルダに復元しましょう。', 'tar -xf backup.tar.gz -C restore',
    '復元先に設定とデータが戻りました。バックアップは「復元できること」まで確かめて初めて役に立ちます。',
    '展開の操作と、復元先フォルダの指定を組み合わせます。', 'tar の -x と -f、場所を変える -C を使います。',
    accept=['tar -xzf backup.tar.gz -C restore'], archives={'backup.tar.gz': FILES}, dirs=['restore'], remove=['restore'],
    goal=all_of(content('restore/project/config.ini', FILES['project/config.ini']), content('restore/project/data.txt', FILES['project/data.txt'])))
add('復元した内容を読む',
    '一覧で名前が見えても、中身が期待どおりとは限りません。復元後は設定の値を読んだり、元データと比較したりします。',
    '復元済みの restore/project/config.ini を読んで、設定内容を確認しましょう。', 'cat restore/project/config.ini',
    '本番モードの設定が読めました。バックアップ作成・一覧・別の場所への復元・内容確認が1つの作業です。',
    '戻したファイルを、普段のファイルとして開いて確認します。', '中身を表示する道具 cat に、復元先のパスを渡します。',
    files={'restore/project/config.ini': FILES['project/config.ini']})
add('圧縮した1ファイルを戻す',
    'gunzip は gzip 圧縮を戻す道具で、gzip の -d と同じ役割です。通常は .gz を取り除いた名前へ戻し、圧縮済みファイルを削除します。',
    'app.log.gz を元の app.log に戻しましょう。', 'gunzip app.log.gz',
    '圧縮前のログへ戻せました。形式が違うアーカイブは、それぞれに合った道具で開きます。',
    'まとめたものを展開する操作ではなく、1ファイルの圧縮を戻します。', 'gunzip に圧縮済みのファイル名を渡します。',
    accept=['gzip -d app.log.gz'], gzip_files={'app.log.gz': 'INFO ready\n'}, remove=['app.log'],
    goal=all_of(content('app.log', 'INFO ready\n'), absent('app.log.gz')))
