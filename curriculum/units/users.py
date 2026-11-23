"""達人モードのユニット：ユーザー・グループ・所有者と権限。

コマンドの模擬は engine/commands/users.py にある。ここでは状態で判定する goal を使う。
"""
from curriculum.lesson_kit import lesson, executable, content, all_of

UNIT_TITLE = "ユーザー・グループ・権限"
ORDER = 30


def _u():
    from engine.commands import users
    return users


def owner_is(name, owner, group=None):
    return lambda t: _u().owner_of(t, name)[0] == owner and (group is None or _u().owner_of(t, name)[1] == group)


def mode_is(name, mode):
    return lambda t: t.mode_of(t.path(name)) & 0o7777 == mode


def has_user(name, **fields):
    return lambda t: _u().user_exists(t, name) and all(_u().user_info(t, name).get(k) == v for k, v in fields.items())


def no_user(name):
    return lambda t: not _u().user_exists(t, name)


def in_group(user, group, present=True):
    return lambda t: (group in _u().groups_of(t, user)) == present


def umask_is(value):
    return lambda t: _u().umask_of(t) == value


def _add_carol(data):
    data["users"]["carol"] = {"uid": 1004, "gid": 1004, "gecos": "Carol Example", "home": "/home/carol",
                              "shell": "/bin/bash", "locked": False, "pw": True}
    data["groups"]["carol"] = {"gid": 1004, "members": []}


def _lock_bob(data):
    data["users"]["bob"]["locked"] = True


def _add_qa(data):
    data["groups"]["qa"] = {"gid": 2100, "members": []}


def _alice_no_pw(data):
    data["users"]["alice"]["pw"] = False
    data["users"]["alice"]["locked"] = True


PASSWD = """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
learner:x:1000:1000:Learner:/home/learner:/bin/bash
alice:x:1001:1001:Alice Example:/home/alice:/bin/bash
bob:x:1002:1002:Bob Example:/home/bob:/bin/bash
"""
GROUP = """root:x:0:
sudo:x:27:learner
learner:x:1000:
alice:x:1001:
developers:x:2000:alice,bob
"""
SUDOERS = """Defaults	env_reset
root	ALL=(ALL:ALL) ALL
%sudo	ALL=(ALL:ALL) ALL
alice	ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx
"""
OWNED = {"report.txt": "売上レポート\n", "build.sh": "#!/bin/bash\necho build\n", "notes.txt": "メモ\n"}
OWNERS = {"report.txt": "alice:developers", "build.sh": "root:root"}

LESSONS = [
    lesson("ex-users-01", "自分は誰で、どのグループか",
           "Linux のすべてのファイルとプロセスには「持ち主（ユーザー）」と「グループ」があり、権限の判断はこの2つで決まります。まず自分の立場を知りましょう。"
           "ユーザー番号（uid）・基本グループ番号（gid）・所属グループの一覧を一度に出す道具があります。名前は identity（身元）に由来する2文字です。",
           "自分のユーザー番号と、所属しているグループをまとめて表示しましょう。", "id",
           "uid=1000(learner)、そして groups に sudo が見えました。sudo グループの所属が、管理者権限を借りられる理由です。",
           accept=["id learner"],
           hints=["自分の身元（番号と所属）を一度に知る道具です。whoami は名前だけでした。",
                  "identity の頭の2文字です。オプションなしで使えます。", "入力例: id"]),
    lesson("ex-users-02", "所属グループの名前だけを見る",
           "id は番号つきで情報が多めです。グループの名前だけを、スペース区切りで短く見たいときの道具があります。名前はそのまま「複数のグループ」を意味する英単語です。",
           "自分が所属しているグループの名前だけを表示しましょう。", "groups",
           "learner sudo と出ました。先頭が基本グループで、新しく作ったファイルのグループになります。",
           accept=["groups learner", "id -Gn"],
           hints=["「何のグループに入っているか」を名前だけで答える道具です。",
                  "名前は英語の複数形で、そのままグループ（複数）の意味です。", "入力例: groups"]),
    lesson("ex-users-03", "他の人の所属を調べる",
           "id や groups は、ユーザー名を後ろに書くと、その人の情報を表示します。誰かにファイルを共有できるか確かめるときに使います。ここでは alice を調べます。",
           "alice のユーザー番号と、所属グループを表示しましょう。", "id alice",
           "alice は developers グループ（gid 2000）にも入っています。learner は入っていないので、そのグループ専用のファイルは扱えません。",
           accept=["sudo id alice"],
           hints=["自分を調べる道具に、調べたい人の名前を渡せます。",
                  "道具は identity の2文字です。後ろにユーザー名を付けます。", "入力例: id alice"]),
    lesson("ex-users-04", "ユーザー番号だけを取り出す",
           "スクリプトでは、番号だけを欲しいことがよくあります（例: root かどうかを 0 かで判定）。id には、必要な項目だけを出すオプションがあります。"
           "ユーザー番号は user の頭文字です。",
           "自分のユーザー番号（数字だけ）を表示しましょう。", "id -u",
           "1000 と数字だけが出ました。一般ユーザーは 1000 以降、root は 0、システム用の特殊ユーザーは 1〜999 が慣習です。",
           accept=["id -u learner"],
           hints=["全部ではなく、番号の項目だけを選ぶ「オプション」が必要です。",
                  "identity の道具に、user の頭文字をオプションとして付けます。", "入力例: id -u"]),
    lesson("ex-users-05", "いま誰がログインしているか",
           "サーバーを複数人で使うとき、「いま誰が入っているか」は障害対応の最初の確認点です。"
           "名前が英語の疑問詞（誰）と同じ、短い道具が一覧を出します。接続元の IP アドレスも見えます。",
           "現在ログインしているユーザーの一覧を表示しましょう。", "who",
           "learner と alice が入っています。接続元は 192.0.2.10 などの練習用アドレスです。知らない IP からのログインは要注意です。",
           accept=["w", "w -h"],
           hints=["ログイン中の人を列挙する道具です。自分以外の人が見えるかもしれません。",
                  "名前は英語で「誰」を意味する、3文字の単語です。", "入力例: who"]),
    lesson("ex-users-06", "ログイン中の人が何をしているか",
           "who は「誰がいるか」だけでした。「その人がいま何を実行しているか」と、負荷の目安（load average）まで知りたいときの道具があります。名前はたった1文字です。",
           "ログイン中のユーザーと、その人が実行中のコマンドを表示しましょう。", "w",
           "alice が vim notes.txt を12分間放置していると分かります。IDLE 列は無操作時間です。",
           hints=["誰がいるかに加え、何をしているかも出る道具です。",
                  "名前はアルファベット1文字です（who の仲間）。", "入力例: w"]),
    lesson("ex-users-07", "過去のログイン履歴を見る",
           "いまいない人も含めて、「いつ・どこから入ったか」を過去にさかのぼって確認する道具があります。名前は「最後」を意味する英単語です。"
           "セキュリティの調査で、見覚えのないログインを探すときに使います。",
           "過去のログイン履歴を表示しましょう。", "last",
           "reboot の行は再起動の記録です。ログインの終了時刻と、つないでいた時間も分かります。",
           accept=["last -n 5", "last -n 10"],
           hints=["「過去の」ログインの記録を読む道具です。",
                  "名前は、英語で「最後」を意味する単語です。", "入力例: last"]),
    lesson("ex-users-08", "特定の人のログイン履歴",
           "履歴が長いサーバーでは、人を絞らないと読めません。履歴の道具の後ろにユーザー名を書くと、その人の分だけになります。",
           "alice のログイン履歴だけを表示しましょう。", "last alice",
           "alice の行だけが出ました。最近ログインした記録が自分の覚えと違えば、不正利用を疑います。",
           accept=["last -n 5 alice", "last -n 10 alice"],
           hints=["履歴の道具に、絞り込みたい相手を渡します。",
                  "履歴の道具は last です。後ろにユーザー名を付けます。", "入力例: last alice"]),
    lesson("ex-users-09", "アカウント台帳から1人を引く",
           "ユーザーの正体は /etc/passwd という台帳にあります。1行が1ユーザーで、コロン区切りの7項目"
           "（名前:x:uid:gid:説明:ホーム:シェル）です。2項目目の x は「パスワードは別ファイルに隠している」の印です。"
           "台帳の調べ方には getent があり、LDAP など外部の台帳も含めて同じ書式で引けるので、passwd を直接読むより確実です。",
           "alice のアカウント情報（台帳の1行）を表示しましょう。", "getent passwd alice",
           "alice:x:1001:1001:Alice Example:/home/alice:/bin/bash と出ました。シェルが nologin なら、ログインできない特殊ユーザーです。",
           hints=["「アカウント台帳」を名前で引く道具があります。台帳の種類（アカウントかグループか）も指定します。",
                  "道具は getent、台帳の種類は passwd、その後ろに調べたい名前を付けます。", "入力例: getent passwd alice"]),
    lesson("ex-users-10", "passwd の控えから alice の行を探す",
           '手元に /etc/passwd の控えがあります。台帳の行頭はユーザー名です。全体を読むだけでなく、必要な人の情報を選んで調べましょう。',
           'アカウント台帳の控えから、alice の行だけを抜き出しましょう。', "grep alice passwd.sample",
           "台帳もただのテキストです。grep で行を探せることを覚えておくと、調査の幅が広がります。",
           files={"passwd.sample": PASSWD},
           accept=["grep ^alice passwd.sample", "grep alice: passwd.sample", "cat passwd.sample | grep alice", "grep -E ^alice: passwd.sample"],
           hints=["ファイルから特定の文字を含む行だけを探したいときの道具を使います。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。道具は grep です。探す文字と、ファイル名を並べます。', "入力例: grep alice passwd.sample"]),
    lesson("ex-users-11", "ユーザー名だけを一覧にする",
           "台帳の1項目目（名前）だけを全員分並べたいときは、区切り文字を指定して列を切り出します。区切りはコロンです。",
           'アカウント台帳の控えから、ユーザー名の列だけを表示しましょう。', "cut -d: -f1 passwd.sample",
           "root から bob まで6名が並びました。区切り文字（-d）と取り出す列（-f）を指定する形は、/etc/group や CSV にも使えます。",
           files={"passwd.sample": PASSWD},
           accept=["cut -f1 -d: passwd.sample", "cat passwd.sample | cut -d: -f1", "cut -d : -f 1 passwd.sample"],
           hints=["「列を切り出す」道具です。区切り文字が何かを伝える必要があります。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。道具は cut です。区切り（-d）と欄の番号（-f）を指定します。台帳の区切りはコロンです。',
                  "入力例: cut -d: -f1 passwd.sample"]),
    lesson("ex-users-12", "ログインできないユーザーを探す",
           "7項目目はログインシェルです。/usr/sbin/nologin や /bin/false が設定されたユーザーは、人間がログインできません。"
           "www-data や daemon のような、サービス専用のユーザーがこれにあたります。",
           'アカウント台帳の控えから、ログインできない設定（nologin）のユーザーの行を探しましょう。', "grep nologin passwd.sample",
           "daemon と www-data がログイン不可です。サービス用ユーザーを人間用にしないのは、侵入されたときの被害を小さくする基本です。",
           files={"passwd.sample": PASSWD},
           accept=["cat passwd.sample | grep nologin", "grep -n nologin passwd.sample"],
           hints=["ファイルから、ある単語を含む行を探す道具を使います。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。grep を使います。探す語は、台帳の最後の欄にあるシェルの名前の一部です。', "入力例: grep nologin passwd.sample"]),
    lesson("ex-users-13", "グループ台帳を読む",
           "グループの台帳は /etc/group です。書式は「グループ名:x:gid:メンバー1,メンバー2」。基本グループは passwd 側に書かれるので、メンバー欄に載らないことが多い点に注意しましょう。",
           "developers グループのメンバーが誰かを、グループ台帳から表示しましょう。", "getent group developers",
           "developers:x:2000:alice,bob と出ました。メンバーは alice と bob です。",
           files={"group.sample": GROUP},
           accept=["grep developers group.sample"],
           hints=["アカウント台帳を引いた道具は、グループ台帳も引けます。",
                  "getent の台帳の種類を group にして、名前を付けます（控えを grep で読んでも構いません）。", "入力例: getent group developers"]),
    lesson("ex-users-14", "所有者とグループの列まで読む",
           "ls -l の2〜4列目は「権限・リンク数・所有者・グループ」です。本物の ls -l は所有者とグループも出しますが、この練習の ls -l は簡略版です。"
           "代わりに、所有者・グループ・サイズ・日付を省略せず出す、ll という道具を使います（Ubuntu でも ll は ls を詳しくする別名です）。",
           "フォルダの中身を、所有者とグループの列まで含めて詳しく一覧表示しましょう。", "ll",
           "先頭の10文字が種類と権限（- はファイル、d はフォルダ）、続いてリンク数・所有者・グループ・サイズ・日時・名前です。build.sh が root のものだと読み取れます。",
           files=OWNED, owners=OWNERS, accept=["ll ."],
           hints=["所有者とグループの列を含む詳しい一覧を出したいときです。",
                  "名前は小文字のエル2つです。ls の長い形式の別名です。", "入力例: ll"]),
    lesson("ex-users-15", "一覧から所有者を読み取る",
           "一覧を「見る」だけでなく「読む」練習です。誰のものかは、3列目に書かれています。調べた結果を、ファイルに書いて報告しましょう。"
           "文字を書き出すには、echo の出力を > でファイルに保存する形が使えます。",
           "フォルダ内のファイルのうち、所有者が root のファイルの名前を answer.txt に書き残しましょう。", "echo build.sh > answer.txt",
           "build.sh が root 所有です。ファイル名を一行だけ書いた answer.txt ができました。",
           files=OWNED, owners=OWNERS, remove=["answer.txt"], goal=content("answer.txt", "build.sh\n"),
           hints=["まず、所有者の列が見える一覧を出して、どれが root のものか確かめます。そのあと、名前を保存します。",
                  "所有者つきの一覧は ll。名前を保存するのは echo の出力をファイルへ向ける > を使います。",
                  "入力例: echo build.sh > answer.txt"]),
    lesson("ex-users-16", "ファイルの詳しい身元を見る",
           "ls は一覧向きですが、1つのファイルの権限を「数字（8進）と記号の両方」、所有者の名前と番号、更新日時まで知りたいときは別の道具があります。名前は「状態」を意味する英単語です。",
           '売上レポートのファイルを見つけ、その詳細情報（権限・所有者・グループ・日時）を表示しましょう。', "stat report.txt",
           "Access: (0644/-rw-r--r--) の0644が数字表記、続くのが記号表記です。Uid・Gid で所有者とグループの名前と番号が分かります。",
           files=OWNED, owners=OWNERS,
           hints=["1つのファイルを、一覧より詳しく調べる道具です。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。名前は英語で「状態」。後ろにファイル名を付けます。', "入力例: stat report.txt"]),
    lesson("ex-users-17", "権限を数字だけで取り出す",
           "stat には -c で出力の書式を決める機能があり、%a は「数字の権限」、%U は「所有者名」を表します。"
           "スクリプトが権限を検査するときにとても便利です。",
           '売上レポートのファイルの権限を、数字（8進）だけで表示しましょう。', "stat -c %a report.txt",
           "644 と出ました。数字は 4=読み、2=書き、1=実行 の足し算で、所有者・グループ・その他の順に並びます。6=4+2、つまり所有者は読み書き、他は読み取りだけです。",
           files=OWNED, owners=OWNERS,
           accept=["stat -c '%a' report.txt", 'stat -c "%a" report.txt', "stat --format=%a report.txt"],
           hints=["詳細を出す道具に、出力の形を指定して、権限の数字の欄だけにします。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。stat に -c（書式）を付けます。書式の中の %a が数字の権限を表します。', "入力例: stat -c %a report.txt"]),
    lesson("ex-users-18", "ls -l の権限の文字列を読む",
           "詳しい一覧表示の先頭10文字は、1文字目が種類（- ファイル / d フォルダ）、残り9文字が rwx の3組です。順に「所有者・グループ・その他」の権限を表します。"
           "r=読む w=書く x=実行（フォルダでは「中に入る」）、- は権限なしです。",
           "フォルダの中身を、権限の文字列つきで詳しく表示しましょう。", "ls -l",
           "-rw-r--r-- は「所有者は読み書き、グループとその他は読むだけ」です。build.sh のように x が付いていれば実行できます。",
           files={"report.txt": "a\n", "run.sh": "#!/bin/bash\n"}, modes={"run.sh": 0o755},
           accept=["ls -la", "ls -al"],
           hints=["一覧を、1行1ファイルの詳しい形式（権限つき）で出したいときです。",
                  "ls に「詳しく（long）」を意味するオプションを付けます。", "入力例: ls -l"]),
    lesson("ex-users-19", "スクリプトに実行権を付ける",
           "シェルスクリプトは、実行権（x）がないと ./ で動かせません。chmod は、記号の指定（誰に + − = 何を）で権限を足し引きします。"
           "誰は u（所有者）・g（グループ）・o（その他）・a（全員）、何は r・w・x です。",
           'セットアップ用のスクリプトを見つけ、自分が実行できるようにしましょう。', "chmod u+x setup.sh",
           "u+x で「所有者に実行権を足す」ことができました。+ は足す、- は引く、= はそのとおりに決める、です。",
           files={"setup.sh": "#!/bin/bash\necho setup\n"}, goal=executable("setup.sh"),
           accept=["chmod +x setup.sh", "chmod a+x setup.sh", "chmod 755 setup.sh", "chmod 744 setup.sh", "chmod 700 setup.sh", "chmod 750 setup.sh"],
           hints=["権限を変える道具を使います。必要なのは「所有者に実行を許す」ことです。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。chmod を使います。誰（u=所有者）に、足す（+）、何を（x=実行）の順に書きます。', "入力例: chmod u+x setup.sh"]),
    lesson("ex-users-20", "秘密のファイルを自分専用にする",
           "パスワードや鍵の入ったファイルは、自分以外に読ませてはいけません。8進数の指定（3桁）は、所有者・グループ・その他の順に、r=4 w=2 x=1 を足した値です。",
           '秘密情報を収めたテキストファイルを見つけ、自分だけが読み書きでき、他の人には何の権限も与えない状態にしましょう。', "chmod 600 secrets.txt",
           "600 は 所有者 rw-（4+2）、グループ ---、その他 --- です。SSH の秘密鍵が 600 でないと拒否されるのも同じ考えです。",
           files={"secrets.txt": "TRAINING_ONLY_NOT_A_SECRET\n"}, goal=mode_is("secrets.txt", 0o600),
           accept=["chmod u=rw,go= secrets.txt", "chmod go-rwx secrets.txt", "chmod u=rw,g=,o= secrets.txt", "chmod og-r secrets.txt"],
           hints=["所有者に読み書き、それ以外は何もなし、という状態を数字か記号で表します。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。chmod に3桁の数字を渡します。読み4・書き2・実行1の足し算で、所有者の桁は 4+2 です。他の2桁は 0 です。', "入力例: chmod 600 secrets.txt"]),
    lesson("ex-users-21", "その他のユーザーから読み取りを外す",
           "既に 644 のファイルから、「その他」の読み取りだけを外すなら、数字を計算し直すより、記号で「引く」ほうが安全です。",
           '共有用のテキストファイルから、「その他」の人の権限だけを取り除き、所有者とグループの権限はそのままにしましょう。', "chmod o-r share.txt",
           "o-r で「その他」から読み取りを引き、644 が 640 になりました。数字より、記号は現状を見ずに安全に変えられるのが長所です。",
           files={"share.txt": "共有メモ\n"}, goal=mode_is("share.txt", 0o640),
           accept=["chmod 640 share.txt", "chmod o= share.txt", "chmod o-rwx share.txt", "chmod u=rw,g=r,o= share.txt"],
           hints=["全体を決め直すのではなく、一部の権限だけを「引く」ことで変えます。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。chmod の記号指定で、対象は「その他」、操作は「引く（-）」、権限は読み取りです。', "入力例: chmod o-r share.txt"]),
    lesson("ex-users-22", "フォルダの権限は「入れるか」を決める",
           "フォルダの r は「中身の一覧が見える」、w は「中でファイルを作る・消す」、x は「中に入れる（cd できる）」です。"
           "x がないフォルダは、中身が見えても入れません。チーム用フォルダは、所有者に全部、グループに読みと入る権限、その他には何もなし、とするのが定番です。",
           'チーム用フォルダを見つけ、所有者は全部、グループは読みと入るだけ、その他は無しの権限にしましょう。', "chmod 750 team",
           "750 は rwxr-x---。フォルダに実行(x)がないと中に入れないことが、ファイルとの大きな違いです。",
           dirs=["team"], modes={"team": 0o755}, goal=mode_is("team", 0o750),
           accept=["chmod u=rwx,g=rx,o= team", "chmod o-rwx team", "chmod 0750 team"],
           hints=["所有者・グループ・その他の3つの桁を、それぞれ決めます。フォルダは「入る」権限が大切です。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。chmod で3桁の数字です。所有者は全部(4+2+1)、グループは読み+実行(4+1)、その他は0です。', "入力例: chmod 750 team"]),
    lesson("ex-users-23", "一般ユーザーは他人にファイルを譲れない",
           "chown（所有者を変える）や chgrp（グループを変える）は、安全のため一般ユーザーにはほぼ許されません。"
           "chgrp は自分のファイルを「自分が所属するグループ」に変える場合だけ可能です。learner は developers に入っていないので、失敗するはずです。"
           "まず、失敗する様子を実際に見ておきましょう。エラーも読む練習です。",
           '管理者権限を使わずに、売上レポートのファイルのグループを developers に変えようとしてみましょう（失敗が正解です）。', "chgrp developers report.txt",
           "Operation not permitted。自分が入っていないグループには変えられません。次の課題で、正しい解決（管理者の力を借りる）を学びます。",
           files={"report.txt": "売上レポート\n"}, expected_code=1,
           accept=["chown :developers report.txt", "chown learner:developers report.txt"],
           hints=["グループを変える道具を、権限を借りずに使ってみます。エラーを見るのが目的です。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。グループを変えるのは chgrp。新しいグループ名とファイル名を並べます。sudo は付けません。', "入力例: chgrp developers report.txt"]),
    lesson("ex-users-24", "管理者権限でグループを変える",
           "sudo は、1コマンドだけ root（管理者）として実行する仕組みです。前の課題と同じ変更が、今度は成功します。"
           "変更の結果は ll や stat で必ず確かめる習慣をつけましょう。",
           '管理者権限を借りて、売上レポートのファイルのグループを developers にしましょう。', "sudo chgrp developers report.txt",
           "developers グループのメンバー（alice, bob）は、グループ権限でこのファイルを使えます。chgrp は chown :グループ とも書けます（コロンの前を省略）。",
           files={"report.txt": "売上レポート\n"}, goal=owner_is("report.txt", "learner", "developers"),
           accept=["sudo chown :developers report.txt", "sudo chown learner:developers report.txt"],
           hints=["前の課題と同じ変更を、権限を借りて実行します。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。先頭に sudo を付けます。グループを変える道具は chgrp、または chown のグループだけ指定する形です。', "入力例: sudo chgrp developers report.txt"]),
    lesson("ex-users-25", "所有者を変える",
           "chown は所有者を変える道具です。書式は「chown 新しい所有者 ファイル」。デプロイ用のスクリプトを、専用ユーザー deploy に渡す場面です。",
           'デプロイ用スクリプトの所有者を deploy ユーザーに変えましょう（管理者権限が必要です）。', "sudo chown deploy deploy.sh",
           "所有者が deploy になりました。chown の変更には root の権限が要るので、sudo が必要でした。",
           files={"deploy.sh": "#!/bin/bash\necho deploy\n"}, goal=owner_is("deploy.sh", "deploy"),
           accept=["sudo chown deploy:learner deploy.sh", "sudo chown deploy: deploy.sh", "sudo chown deploy:deploy deploy.sh"],
           hints=["所有者を変えるのは、権限の変更とは別の道具です。管理者の力も必要です。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。sudo の後ろに chown。新しい所有者名とファイル名を並べます。', "入力例: sudo chown deploy deploy.sh"]),
    lesson("ex-users-26", "所有者とグループを同時に変える",
           "chown は「所有者:グループ」とコロンでつなぐと、2つを同時に変えます。:の前だけなら所有者のみ、:の後ろだけならグループのみです。"
           "「所有者:」と後ろを空にすると、そのユーザーの基本グループになります。",
           'アプリの設定ファイルの所有者を alice、グループを developers に、1回の操作で変えましょう。', "sudo chown alice:developers app.conf",
           "alice:developers で2つを同時に設定できました。古い書き方の alice.developers も動きますが、: が推奨です。",
           files={"app.conf": "port=8080\n"}, goal=owner_is("app.conf", "alice", "developers"),
           accept=["sudo chown alice.developers app.conf"],
           hints=["所有者とグループの2つを、1つの引数にまとめて渡せます。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。sudo chown を使い、所有者とグループを区切り文字でつなげて1つにします。', "入力例: sudo chown alice:developers app.conf"]),
    lesson("ex-users-27", "フォルダごと所有者を変える",
           "フォルダの中身まですべて持ち主を変えたいときは、-R（recursive：再帰的）を付けます。Web サイトの公開フォルダを www-data に渡すような場面です。"
           "-R を付け忘れると、フォルダ自体だけが変わり、中身は元のままです。",
           'Web サイトの公開フォルダと、その中身すべての所有者を www-data に変えましょう。', "sudo chown -R www-data:www-data site",
           "フォルダとその下すべてが www-data になりました。大きなフォルダでは影響範囲が広いので、パスをよく確認してから実行しましょう。",
           files={"site/index.html": "<h1>hello</h1>\n", "site/css/style.css": "body{}\n"},
           goal=all_of(owner_is("site", "www-data"), owner_is("site/index.html", "www-data"), owner_is("site/css/style.css", "www-data")),
           accept=["sudo chown -R www-data site", "sudo chown -R www-data: site", "sudo chown -R www-data:learner site"],
           hints=["フォルダの中身まで、まとめて変えるオプションがあります。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。sudo chown に、再帰を意味する大文字のオプションを付けます。所有者名の後に、フォルダ名です。', "入力例: sudo chown -R www-data:www-data site"]),
    lesson("ex-users-28", "グループの詳細を確認する",
           "所有者・グループ・その他それぞれの権限を、ACL 形式で表示する getfacl という道具もあります。stat より「誰にどの権限か」が読みやすい表示です。",
           '売上レポートのファイルの所有者・グループ・権限を、user / group / other の形式で表示しましょう。', "getfacl report.txt",
           "user::rw- がファイルの所有者の権限、group:: がグループ、other:: がその他です。# owner と # group の行で、誰のものかも分かります。",
           files=OWNED, owners=OWNERS,
           hints=["権限を、誰向けかが分かる形で出す道具です。ACL に関する名前です。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。名前は get と facl（ファイルアクセス制御リスト）をつないだものです。', "入力例: getfacl report.txt"]),
    lesson("ex-users-29", "umask：新しいファイルの既定の権限",
           "新しいファイルの権限は、既定値（ファイル 666、フォルダ 777）から umask で指定した権限ビットを取り除いたものになります。単純な引き算ではありません。"
           "ふつうの umask は 022 で、ファイルは 644、フォルダは 755 です。この値は「この端末の設定」で、現在の値を見るには、道具名そのものを入力します。",
           "新しいファイルから取り除く、現在の権限マスクの値を表示しましょう。", "umask",
           "0022 と出ました。グループとその他の書き込み権限を取り除くと、新しいファイルは 644 になります。共同作業では 002 としてグループへの書き込みを許す場合もあります。",
           hints=["「新しいファイルから差し引く権限」を管理する設定です。値を表示するだけです。",
                  "名前は user mask を縮めたものです。引数なしで使います。", "入力例: umask"]),
    lesson("ex-users-30", "umask を記号で見る",
           "umask の -S オプションは、「引く値」ではなく「許される権限」を、u=rwx,g=rx,o=rx のような記号で表示します。chmod の記号指定と同じ書き方で、読みやすいです。",
           "umask の現在の設定を、権限の記号の形式で表示しましょう。", "umask -S",
           "u=rwx,g=rx,o=rx は、新しいフォルダの権限が 755 になることを意味します。",
           hints=["umask に、表示の形式を変えるオプションを付けます。",
                  "S は symbolic（記号）の頭文字です。", "入力例: umask -S"]),
    lesson("ex-users-31", "umask を厳しくする",
           "他人に一切見せたくない作業をするときは、umask を厳しくします。設定した後に作るファイルが対象で、既存のファイルは変わりません。"
           "また、この設定は今のシェルだけで有効です（ログアウトで元に戻ります）。永続化するには ~/.bashrc などに書きます。",
           "今後作るファイルとフォルダが、自分以外には一切権限を持たないようにする umask を設定しましょう。", "umask 077",
           "077 は「グループとその他から、読み書き実行をすべて引く」の意味です。ファイルは 600、フォルダは 700 になります。",
           goal=umask_is(0o077), accept=["umask 0077"],
           hints=["引く値を決めます。所有者の桁は何も引かず、グループ・その他は全部引きます。",
                  "umask の後ろに3桁の数字を書きます。7 は rwx をすべて引く値です。", "入力例: umask 077"]),
    lesson("ex-users-32", "umask の計算問題",
           "umask が 022 のとき、新しく作るファイルの権限を数字で答えます。ファイルの既定値は 666（実行権は最初は付かない）で、そこからマスクに含まれる権限を取り除きます。"
           "答えを mask.txt に書いて報告してください。",
           "umask が 022 のときに新しく作る普通のファイルの権限（3桁の数字）を、mask.txt に書き残しましょう。", "echo 644 > mask.txt",
           "022 はグループとその他の w を取り除く指定なので、ファイルは 644、フォルダは 755 です。077 でもファイルは 600 になり、単純に 666 から引き算するわけではありません。",
           remove=["mask.txt"], goal=content("mask.txt", "644\n"),
           hints=["ファイルの既定値から、マスクに含まれる権限ビットを取り除きます。",
                  "既定値は 666、umask は 022。結果の3桁を、echo の出力をファイルへ向けて書き込みます。", "入力例: echo 644 > mask.txt"]),
    lesson("ex-users-33", "特殊な権限ビット（setuid）を見つける",
           "権限には 9 ビットのほかに、特別な3つがあります。setuid（実行中は所有者の権限で動く）は所有者の x の位置に s、"
           "setgid はグループの x の位置に s、sticky（自分のファイルしか消せない）はその他の x の位置に t と表示されます。"
           "passwd コマンドが一般ユーザーでもパスワード変更できるのは、root の setuid が付いているからです。",
           "一覧で権限を確かめて、所有者の実行権の位置が s になっているファイルの名前を、answer.txt に書き残しましょう。", "echo tool.bin > answer.txt",
           "-rwsr-xr-x の s が setuid です。セキュリティ監査では、想定外の setuid ファイルが無いかを探すのが基本です。",
           files={"tool.bin": "bin\n", "plain.sh": "sh\n", "data.txt": "d\n"},
           modes={"tool.bin": 0o4755, "plain.sh": 0o755}, owners={"tool.bin": "root:root"},
           remove=["answer.txt"], goal=content("answer.txt", "tool.bin\n"),
           hints=["権限の文字列を一覧で読み、他と違う表示の1つを探します。",
                  "ll や ls -l で見ます。所有者の実行権の位置が x ではなく s のものを探し、名前を echo で保存します。", "入力例: echo tool.bin > answer.txt"]),
    lesson("ex-users-34", "sticky ビットのフォルダを数字で確認する",
           "/tmp のように全員が書き込めるフォルダには、sticky ビットが付いています。ファイルの削除・名前変更は、そのファイルの持ち主かフォルダの持ち主だけ可能になり、他人のファイルを消せません。"
           "特殊ビットは、数字では4桁目として表されます（setuid=4、setgid=2、sticky=1）。",
           '公開用フォルダを見つけ、その権限を特殊ビットも含めた数字（8進）で表示しましょう。', "stat -c %a pub",
           "1777 と出ました。先頭の 1 が sticky、続く 777 は全員が読み書きできることを表します。ls -l では drwxrwxrwt と、末尾の t で表示されます。",
           dirs=["pub"], modes={"pub": 0o1777},
           accept=["stat -c '%a' pub", 'stat -c "%a" pub'],
           hints=["フォルダ1つの権限を、数字だけで取り出す形式を思い出しましょう。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。stat の -c で書式を指定します。数字の権限は %a です。', "入力例: stat -c %a pub"]),
    lesson("ex-users-35", "一般ユーザーはアカウントを作れない",
           "useradd（ユーザーを追加）は /etc/passwd を書き換えるので、root だけが実行できます。一般ユーザーが試すと断られます。"
           "エラーメッセージを読むのも大事な技術です。",
           "管理者権限を使わずに、carol というユーザーを作ろうとしてみましょう（失敗が正解です）。", "useradd carol",
           "Permission denied（権限がない）。管理者でないとアカウントは作れません。",
           expected_code=1, accept=["useradd -m carol"],
           hints=["ユーザーを追加する道具を、そのまま使ってみます。失敗する様子を見るのが目的です。",
                  "道具は useradd です。ユーザー名を付けますが、sudo は付けません。", "入力例: useradd carol"]),
    lesson("ex-users-36", "ユーザーを作る",
           "useradd の主なオプションは、-m（ホームフォルダを作る）、-s（ログインシェル）、-G（追加のグループ）、-c（説明）です。"
           "-m を忘れると、ホームフォルダのないユーザーができます。シェルを省略すると /bin/sh になり、bash の便利機能が使えません。",
           "新しいメンバー carol のアカウントを、ホームフォルダつき、ログインシェルは bash で作りましょう（管理者権限が必要です）。",
           "sudo useradd -m -s /bin/bash carol",
           "carol が作られました。パスワードはまだなので、ログインはできない状態（ロック）です。次の課題で確認しましょう。",
           goal=has_user("carol", shell="/bin/bash", home_created=True),
           accept=["sudo useradd -s /bin/bash -m carol", "sudo useradd --create-home -s /bin/bash carol", "sudo useradd -m -s /bin/bash -c carol carol"],
           hints=["アカウントを作る道具に、ホームの作成とシェルの指定を足します。管理者権限も必要です。",
                  "sudo useradd を使います。ホームを作る -m と、シェルを決める -s を付け、最後にユーザー名です。", "入力例: sudo useradd -m -s /bin/bash carol"]),
    lesson("ex-users-37", "作ったアカウントを確認する",
           "作成した後は、必ず結果を確かめます。番号が自動で割り当てられ（既存の次の番号）、同名のグループも自動で作られます。",
           "carol のユーザー番号と所属グループを確認しましょう。", "id carol",
           "uid=1004(carol) gid=1004(carol) …。同名の基本グループが作られているのが分かります。",
           users_setup=_add_carol,
           hints=["先に学んだ「ある人の身元を調べる」道具が使えます。",
                  "id の後ろにユーザー名を付けます。", "入力例: id carol"]),
    lesson("ex-users-38", "グループを作る",
           "チームごとにグループを作り、ファイルの共有範囲を決めるのが Linux の基本設計です。groupadd がグループを作ります。番号は自動で割り当てられます。",
           "qa という名前の新しいグループを作りましょう（管理者権限が必要です）。", "sudo groupadd qa",
           "qa グループができました。次は、メンバーを追加します。",
           goal=lambda t: _u().group_exists(t, "qa"), accept=["sudo groupadd -g 2100 qa"],
           hints=["グループを作る道具があります。ユーザーを作る道具の仲間です。",
                  "sudo groupadd の後ろに名前です。", "入力例: sudo groupadd qa"]),
    lesson("ex-users-39", "グループにメンバーを追加する（-a を忘れずに）",
           "usermod -G は「所属グループを、指定した一覧で置き換える」ので、-a（append：追加）を付けないと、既存の所属が消えます。"
           "必ず -aG のように -a とセットで使います。bob は今 developers に入っています。それを残したまま qa に追加しましょう。",
           "bob を qa グループに追加しましょう。既存の所属グループは保ったままにします。", "sudo usermod -aG qa bob",
           "bob は developers と qa の両方に入りました。-a を忘れて developers が消えるのは、現場でよくある事故です。",
           users_setup=_add_qa,
           goal=all_of(in_group("bob", "qa"), in_group("bob", "developers")),
           accept=["sudo usermod -a -G qa bob", "sudo gpasswd -a bob qa"],
           hints=["置き換えではなく「追加」する指定にします。既存の所属を消さないことが条件です。",
                  "sudo usermod に、追加の -a とグループの -G、グループ名、ユーザー名を並べます。", "入力例: sudo usermod -aG qa bob"]),
    lesson("ex-users-40", "グループからメンバーを外す",
           "メンバーを外すには gpasswd -d が簡単です。usermod には「外す」専用の指定がないので、残したいグループを -G で全部指定し直す方法になります。",
           "alice を developers グループから外しましょう。", "sudo gpasswd -d alice developers",
           "alice は developers から外れました。ただし、すでにログイン中のセッションには反映されず、次回ログインからです。",
           goal=in_group("alice", "developers", present=False), accept=["sudo usermod -G alice alice"],
           hints=["グループのメンバーを1人だけ減らします。「置き換え」ではなく「削除」です。",
                  "sudo gpasswd にメンバー削除の -d、ユーザー名、グループ名を渡します。", "入力例: sudo gpasswd -d alice developers"]),
    lesson("ex-users-41", "退職したユーザーをロックする",
           "退職者のアカウントは、すぐ削除せず、まずロック（無効化）するのが安全です。ファイルは残り、いつでも復旧できます。"
           "usermod の -L は lock の頭文字です。",
           "bob のアカウントを、削除はせずにログインできない状態にしましょう。", "sudo usermod -L bob",
           "bob はロックされました。パスワードの前に ! を付けて無効にする仕組みです。",
           goal=lambda t: _u().user_info(t, "bob")["locked"], accept=["sudo passwd -l bob"],
           hints=["消すのではなく、使えなくする方法があります。",
                  "ユーザー情報を変える usermod に、lock の頭文字のオプションを付けます。", "入力例: sudo usermod -L bob"]),
    lesson("ex-users-42", "アカウントの状態を調べる",
           "passwd -S は、パスワードの状態を1行で示します。2項目目が L（ロック）、P（パスワードあり）、NP（パスワードなし）です。他人の状態は root だけが見られます。",
           "bob のアカウントの状態（ロックされているか）を表示しましょう（管理者権限が必要です）。", "sudo passwd -S bob",
           "bob L … と出れば、ロック済みです。",
           users_setup=_lock_bob,
           hints=["パスワード状態を表示する道具に、状態表示のオプションを付けます。",
                  "sudo passwd に、status の頭文字のオプションとユーザー名です。", "入力例: sudo passwd -S bob"]),
    lesson("ex-users-43", "ロックを解除する",
           "復職などで、ロックしたアカウントを使えるように戻します。-L の反対は -U（unlock）です。",
           "ロックされている bob のアカウントを、使える状態に戻しましょう。", "sudo usermod -U bob",
           "ロック解除。ファイルや所属は元のままです。",
           users_setup=_lock_bob, goal=lambda t: not _u().user_info(t, "bob")["locked"], accept=["sudo passwd -u bob"],
           hints=["ロックの反対の操作です。",
                  "usermod に、unlock の頭文字のオプションを付けます。", "入力例: sudo usermod -U bob"]),
    lesson("ex-users-44", "パスワードを非対話で設定する",
           "passwd は対話式（2回入力）ですが、スクリプトや大量のアカウントには chpasswd が便利です。標準入力から「ユーザー名:パスワード」の行を受け取ります。"
           "この練習では、必ず明らかなダミー値を使います（実際のパスワードは決して入力しないこと）。",
           "alice のパスワードを TRAINING_ONLY_NOT_A_SECRET に設定しましょう。入力は対話せず、1行で渡します。",
           "echo alice:TRAINING_ONLY_NOT_A_SECRET | sudo chpasswd",
           "alice のパスワードが設定され、ロックも解除されました。コマンド履歴にパスワードが残るので、本番では標準入力をファイルから渡す等の工夫が必要です。",
           users_setup=_alice_no_pw, goal=has_user("alice", pw=True),
           accept=["echo 'alice:TRAINING_ONLY_NOT_A_SECRET' | sudo chpasswd"],
           hints=["「名前:パスワード」の文字を、パイプで一括設定の道具に渡します。",
                  "echo の出力を、パイプ（|）で sudo chpasswd に渡します。", "入力例: echo alice:TRAINING_ONLY_NOT_A_SECRET | sudo chpasswd"]),
    lesson("ex-users-45", "ユーザーを削除する",
           "userdel でアカウントを削除します。-r（remove）を付けると、ホームフォルダとメールも一緒に消えます。付けなければ、ファイルは残ります。"
           "-r は元に戻せないので、バックアップを確認してから使いましょう。",
           "deploy ユーザーを、ホームフォルダごと削除しましょう。", "sudo userdel -r deploy",
           "deploy は削除されました。同名のグループも、他に使う人がいなければ自動で消えます。",
           goal=no_user("deploy"), accept=["sudo userdel --remove deploy"],
           hints=["アカウントを削除する道具があります。ホームも消すオプションが必要です。",
                  "sudo userdel に、remove の頭文字のオプションとユーザー名を付けます。", "入力例: sudo userdel -r deploy"]),
    lesson("ex-users-46", "他人のパスワードなしでは su できない",
           "su は別のユーザーに切り替えます。パスワードを聞かれ、他人のパスワードは知らないので、一般ユーザーは失敗します。"
           "管理者（sudo）だけがパスワードなしで切り替えられます。まず失敗を確認しましょう。",
           "管理者権限を使わずに、alice のユーザーに切り替えようとしてみましょう（失敗が正解です）。", "su alice",
           "Authentication failure。他人になりすませないための仕組みです。",
           expected_code=1, accept=["su - alice"],
           hints=["ユーザーを切り替える道具に、切り替え先を渡します。",
                  "su の後ろにユーザー名です。sudo は付けません。", "入力例: su alice"]),
    lesson("ex-users-47", "alice として1つだけコマンドを実行する",
           "管理者なら、パスワードなしで別のユーザーとして動けます。-c を付けると、その人としてコマンドを1つだけ実行して戻ります。"
           "ハイフン（-）を付けると、その人のログイン環境（ホーム、環境変数）も再現されます。権限の問題を調べるとき、「その人から見たらどう動くか」を確かめるのに使います。",
           "alice になりきって、whoami を1回だけ実行し、alice と表示させましょう。", "sudo su - alice -c whoami",
           "alice と表示されました。sudo の su で、alice 視点の動作確認ができます。",
           accept=["sudo su alice -c whoami", "sudo su -l alice -c whoami"],
           hints=["管理者の力で別人に切り替え、1つだけ命令を実行します。",
                  "sudo su に、ユーザー名、命令を渡すオプション -c、命令を並べます。", "入力例: sudo su - alice -c whoami"]),
    lesson("ex-users-48", "sudoers を読む：誰が何を許されるか",
           'sudo を使える人は /etc/sudoers で決まります。1行は「誰 ホスト=(実行する人) 実行できるコマンド」です。% で始まる名前はグループを表し、%sudo は sudo グループ全員の意味です。NOPASSWD: を付けるとパスワードなしになります。練習用の控えで、グループ全員に与えている行を探しましょう。',
           '管理者権限の設定の控えから、sudo グループのメンバー全員に権限を与えている行を探して表示しましょう。', "grep %sudo sudoers.sample",
           "%sudo ALL=(ALL:ALL) ALL は「sudo グループの人は、どのホストでも、誰としても、どんなコマンドでも実行できる」の意味です。",
           files={"sudoers.sample": SUDOERS},
           accept=["grep '%sudo' sudoers.sample", 'grep "%sudo" sudoers.sample', "cat sudoers.sample | grep %sudo"],
           hints=["ファイルから、グループを表す記号で始まる行を探します。",
                  'ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。ls（隠し項目も見るときは ls -a）と cat で対象を確かめます。grep でファイルを検索します。sudo グループを表す表記は % を頭に付けます。', "入力例: grep %sudo sudoers.sample"]),
    lesson("ex-users-49", "sudoers を安全に点検する",
           "sudoers を直接編集して書式を間違えると、誰も sudo できなくなり、締め出されます。そのため専用の道具（編集時は visudo）を使い、保存前に文法を検査します。"
           "編集せずに文法だけ確かめる -c というオプションもあります。",
           "sudoers の文法に誤りがないか、検査だけしましょう（管理者権限が必要です）。", "sudo visudo -c",
           "parsed OK なら文法は正常です。設定を変えたあとの確認は、習慣にしましょう。",
           hints=["sudoers 専用の検査・編集の道具があります。検査だけにします。",
                  "sudo visudo に、check の頭文字のオプションを付けます。", "入力例: sudo visudo -c"]),
]
