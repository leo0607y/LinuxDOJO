"""Stage 1: 超基礎・ファイルシステムと基本操作（8問）"""
import random

from engine.runner import register

S = 1


# ------------------------------------------------------------------ 1-1
def s11(ctx):
    word = f"{random.choice(['penguin', 'tux', 'kernel', 'shell', 'daemon'])}-{random.randint(1000, 9999)}"
    ctx.data["word"] = word
    ctx.write("README.txt", "ようこそ、株式会社ペンギン商事 インフラ部へ！\nまずはこのサーバーの中を見て回ってください。\n")
    ctx.write("src/main.py", "print('hello')\n")
    ctx.write("docs/manual.md", "# 運用マニュアル\n")
    ctx.write(".gitignore", "*.log\n.env\n")
    ctx.write(".secret_note", f"このメモを見つけたあなたへ。\n普通の ls では見えない場所に大事なものは隠れています。\n合言葉: {word}\n")


def c11(ctx):
    ctx.need_submit(ctx.data["word"], "合言葉")


register(
    id="1-1", stage=S, title="現在地と隠しファイル",
    story="""
入社初日。先輩から「サーバーに入ったら、まず **自分がどこにいるか** と **何があるか** を確認するクセをつけて」と言われた。
このディレクトリのどこかに、普通の `ls` では表示されない **隠しファイル** があり、合言葉が書かれているらしい。
""",
    objectives=["`pwd` で現在地を確認し、`ls` のオプションで隠しファイルを見つける",
                "隠しファイルの中身を読み、書かれている合言葉を `submit 合言葉` で提出する"],
    hints=["Linux では名前が `.`（ドット）で始まるファイルは「隠しファイル」扱いになり、普通の `ls` には出てきません。",
           "`ls` に「all（すべて）」を意味するオプションを付けると隠しファイルも表示されます。中身の表示は `cat` です。",
           "`ls -la` → `.secret_note` を見つけたら `cat .secret_note` → 書かれた合言葉を `submit penguin-1234` のように提出。"],
    answer="pwd\nls -la\ncat .secret_note\nsubmit <<word>>",
    explanation="""
`pwd` (print working directory) は今いるディレクトリの **絶対パス** を表示します。
`ls -la` は 2 つのオプションの組み合わせです:
  ・`-a` (all) … `.` で始まる隠しファイルも表示（`.` は自分自身、`..` は親ディレクトリ）
  ・`-l` (long) … パーミッション・所有者・サイズ・更新日時を1行ずつ詳しく表示
`-h` を足して `ls -lah` にするとサイズが `4.0K` `12M` のように人間が読みやすい単位になります。
`cat` (concatenate) はファイルの中身をそのまま画面に出力します。
""",
    tip="""
`.env`・`.git`・`.ssh`・`.bashrc` など、**重要な設定ほど隠しファイル** になっています。
障害調査でサーバーに入ったら、まず `pwd` と `ls -la` で「どこで・何があるか」を確認するのがプロの初動です。
`ls -A` なら `.` と `..` を除いた隠しファイルだけを表示できて少しスッキリします。
""",
    setup=s11, check=c11,
    solution='pwd\nls -la\nsubmit "$(sed -n "s/^合言葉: //p" .secret_note)"',
    wrong=["submit wrong-0000"],
)


# ------------------------------------------------------------------ 1-2
def s12(ctx):
    boxes = []
    for a in "abc":
        for sh in (1, 2, 3):
            for b in (1, 2, 3, 4):
                d = f"warehouse/area-{a}/shelf-{sh}/box-{b}"
                ctx.mkdir(d)
                boxes.append(d)
    target = random.choice(boxes)
    ctx.data["box"] = target
    ctx.write(f"{target}/treasure.txt", "おめでとう！ここが宝箱です。\n")
    ctx.write("warehouse/README.txt", "倉庫の地図: area-a〜c / shelf-1〜3 / box-1〜4\n宝箱 (treasure.txt) はどこかの box の中にあります。\n")
    for d in random.sample(boxes, 6):
        if d != target:
            ctx.write(f"{d}/dummy.txt", "ハズレ\n")


def c12(ctx):
    cwd = ctx.cwd()
    target = (ctx.work / ctx.data["box"]).resolve()
    if cwd is None:
        ctx.fail("現在地の情報がありません。コマンドを1つ以上実行してください。")
    if cwd.resolve() != target:
        rel = str(cwd).replace(str(ctx.work), "stage_01") if str(cwd).startswith(str(ctx.work)) else str(cwd)
        ctx.fail(f"今いる場所（{rel}）は宝箱のあるディレクトリではありません。`cd` で移動しましょう。")


register(
    id="1-2", stage=S, title="倉庫で宝探し（cd の極意）",
    story="""
古い倉庫サーバーの中に、宝物のファイルが入ったディレクトリが1つだけある。倉庫の案内を読んで手がかりを探そう。
エリア → 棚 → 箱という3階層の迷路を、`cd` と `ls` を駆使して探し出し、**宝箱のディレクトリへ移動** せよ。
""",
    objectives=["宝物のファイルが入っているディレクトリを見つける",
                "`cd` でそのディレクトリに移動した状態で `check` する"],
    hints=["1つずつ `cd` → `ls` を繰り返してもOK。ただし `ls` には中身を再帰的に全部見せてくれるオプションもあります。",
           "まず ls で倉庫の名前を調べ、`ls -R ディレクトリ` で全階層を一覧できます。`cd ..` で1つ上、`cd -` で直前にいた場所へ戻れます。",
           "`ls -R warehouse | less` で `treasure` を探し、見つけたら `cd warehouse/area-b/shelf-2/box-3` のように相対パスで移動。"],
    answer="ls -R warehouse | grep -B5 treasure   # 場所を探す\ncd <<box>>\npwd",
    explanation="""
パスには2種類あります:
  ・**絶対パス** … `/` から始まる完全な住所（例: `/home/user/warehouse`）
  ・**相対パス** … 今いる場所からの道のり（例: `warehouse/area-a`、`../shelf-2`）
`cd` の便利な使い方:
  ・`cd ..` … 1つ上へ ／ `cd ../..` … 2つ上へ
  ・`cd -` … 直前にいたディレクトリへ戻る（2か所を行き来するときに超便利）
  ・`cd` または `cd ~` … ホームディレクトリへ
`ls -R` は Recursive（再帰的）にすべての階層を表示します。量が多ければ `| less` でページ送りしましょう。
""",
    tip="""
本番サーバーの `/etc/nginx/sites-enabled/` や `/var/log/app/` のような深い階層の行き来は日常茶飯事。
**Tab キーでのパス補完** を使うとタイプミスが激減します（`cd wa` + Tab → `cd warehouse/`）。
2つのディレクトリを往復するなら `cd -` を、たくさんの場所を巡るなら `pushd` / `popd` を覚えておくと便利です。
""",
    setup=s12, check=c12,
    solution="ls -R warehouse > /dev/null\ncd <<box>>",
    wrong=["cd warehouse/area-a"],
)


# ------------------------------------------------------------------ 1-3
def s13(ctx):
    names = [f"app-2025-{m:02d}.log" for m in range(1, 9)]
    ages = random.sample(range(2, 60), len(names))
    newest = random.choice(names[:-1])  # アルファベット順で最後にならないファイル
    for n, a in zip(names, ages):
        size = random.randint(200, 3000) * 100
        ctx.write(f"logs/{n}", ("2025-xx-xx INFO request ok\n" * (size // 26)), age_days=a)
    ctx.age(f"logs/{newest}", 0.01)
    ctx.data["newest"] = newest


def c13(ctx):
    ctx.need_submit(ctx.data["newest"], "ファイル名")


register(
    id="1-3", stage=S, title="最後に更新されたログはどれ？",
    story="""
「さっきアプリが落ちたんだけど、**一番最近更新されたログ** はどれ？」と先輩に聞かれた。
ログのディレクトリには月ごとのファイルが並んでいるが、ファイル名の順番と更新された順番は一致しないようだ。
""",
    objectives=["`ls` のオプションでログのディレクトリ内のファイルを **更新日時の新しい順** に並べる",
                "最も新しく更新されたファイル名を `submit ファイル名` で提出する"],
    hints=["`ls -l` で更新日時は見えますが、目で比べるのは大変。`ls` には並び替えのオプションがあります。",
           "`-t` (time) を付けると更新日時の新しい順に並びます。`-h` でサイズも読みやすくなります。",
           "`ls -lht logs/` の一番上の行が答え。ファイル名だけなら `ls -t logs | head -n 1`。"],
    answer="ls -lht logs/\nsubmit <<newest>>",
    explanation="""
`ls` の並び替え系オプション:
  ・`-t` … 更新日時の **新しい順**
  ・`-S` … ファイルサイズの **大きい順**
  ・`-r` … 並び順を **逆にする**（`-ltr` で古い順 → 最新が一番下に来るので、ターミナルで見やすい）
  ・`-h` … `-l` と組み合わせてサイズを `1.2M` のような単位付きで表示
`ls -t logs | head -n 1` のように **パイプ** で繋ぐと「最新の1件だけ」を取り出せます（Stage 2 で詳しく！）。
""",
    tip="""
障害対応では `ls -ltr /var/log/` が定番コマンド。**一番下に最新のファイルが来る** ので、
「どのログが今まさに書き込まれているか」が一目で分かります。
ディスクが溢れたときは `ls -lhS` で大きいファイルから順に確認しましょう。
""",
    setup=s13, check=c13,
    solution='submit "$(ls -t logs | head -n 1)"',
    wrong=['submit "$(ls logs | tail -n 1)"'],
)


# ------------------------------------------------------------------ 1-4
DIRS14 = ["myapp/src/components", "myapp/src/utils", "myapp/tests/unit", "myapp/docs"]
FILES14 = ["myapp/README.md", "myapp/src/main.py", "myapp/tests/unit/test_main.py"]


def s14(ctx):
    ctx.write("要件.txt", "新規プロジェクト myapp の雛形を作ってください。\n" + "\n".join(DIRS14 + FILES14) + "\n")


def c14(ctx):
    for d in DIRS14:
        if not ctx.isdir(d):
            ctx.fail(f"ディレクトリ `{d}/` がまだありません。")
    for f in FILES14:
        if not ctx.isfile(f):
            ctx.fail(f"ファイル `{f}` がまだありません（空ファイルでOK）。")


register(
    id="1-4", stage=S, title="プロジェクトの雛形を一撃で作れ",
    story="""
新規プロジェクト `myapp` を立ち上げることになった。チームの標準構成どおりに、
ディレクトリと空ファイルの雛形を作成してほしい。`mkdir` を何回も打つのはスマートじゃない…。
""",
    objectives=["ディレクトリ: `myapp/src/components` `myapp/src/utils` `myapp/tests/unit` `myapp/docs`",
                "空ファイル: `myapp/README.md` `myapp/src/main.py` `myapp/tests/unit/test_main.py`"],
    hints=["普通の `mkdir a/b/c` は、途中の `a` や `a/b` が無いとエラーになります。途中も自動で作るオプションがあります。",
           "`mkdir -p`（parents）で深い階層を一気に作れます。空ファイルの作成は `touch` です。",
           "`mkdir -p myapp/src/components myapp/src/utils myapp/tests/unit myapp/docs` → `touch myapp/README.md myapp/src/main.py myapp/tests/unit/test_main.py`"],
    answer="mkdir -p myapp/src/components myapp/src/utils myapp/tests/unit myapp/docs\ntouch myapp/README.md myapp/src/main.py myapp/tests/unit/test_main.py",
    explanation="""
`mkdir -p` (parents) は、途中のディレクトリが無ければまとめて作成し、既に存在してもエラーにしません。
そのため **何度実行しても同じ結果になる（冪等）** ので、スクリプトの中で安心して使えます。
`touch` は本来「ファイルの更新日時を今に更新する」コマンドで、ファイルが無ければ空ファイルを作ります。
上級テク: ブレース展開を使えば `mkdir -p myapp/{src/{components,utils},tests/unit,docs}` と1行で書けます（Extra Stage で特訓！）。
""",
    tip="""
CI/CD やデプロイスクリプトでは `mkdir -p /var/log/myapp` のように **-p 付きが鉄則**。
-p が無いと「2回目の実行で File exists エラー → スクリプト停止」という事故が起こります。
`tree myapp` コマンド（要インストール）や `find myapp` で作った構造を確認するクセもつけましょう。
""",
    setup=s14, check=c14,
    solution="mkdir -p " + " ".join(DIRS14) + "\ntouch " + " ".join(FILES14),
    wrong=["mkdir myapp", "mkdir -p " + " ".join(DIRS14)],
)


# ------------------------------------------------------------------ 1-5
# 教材用の架空設定。以下の SECRET_KEY は実サービスでは使えないダミー値です。
CFG = {
    "config/app.yaml": "app:\n  name: penguin-shop\n  port: 8080\n",
    "config/db/database.yaml": "db:\n  host: localhost\n  port: 5432\n",
    "config/db/replica.yaml": "replica:\n  host: db-replica\n",
    "config/.env": "SECRET_KEY=s3cr3t\n",
}


def s15(ctx):
    for k, v in CFG.items():
        ctx.write(k, v)
    ctx.write("nginx.conf", "server {\n    listen 80;\n    server_name shop.example.com;\n}\n")


def c15(ctx):
    if not ctx.exists("nginx.conf"):
        ctx.fail("元の `nginx.conf` が無くなっています！ `mv` ではなく `cp` でコピーを取りましょう（`reset_mission` でやり直せます）。")
    if ctx.read("nginx.conf.bak") != ctx.read("nginx.conf"):
        ctx.fail("`nginx.conf.bak` が無いか、中身が `nginx.conf` と一致しません。")
    if ctx.isdir("config_backup/config"):
        ctx.fail("`config_backup/config/` という二重構造になっています。コピー先が既に存在すると、その中にコピーされます。`rm -rf config_backup` してからやり直しましょう。")
    if not ctx.isdir("config_backup"):
        ctx.fail("`config_backup/` ディレクトリがありません。")
    for k, v in CFG.items():
        dst = k.replace("config/", "config_backup/", 1)
        if ctx.read(dst) != v:
            ctx.fail(f"`{dst}` がコピーされていません。サブディレクトリや隠しファイルも含めて丸ごとコピーしましょう。")
    for k, v in CFG.items():
        if ctx.read(k) != v:
            ctx.fail(f"元の `{k}` が変更・削除されています。")


register(
    id="1-5", stage=S, title="作業前のバックアップは命綱",
    story="""
これから本番の設定ファイルを修正する。**作業前のバックアップ** は鉄則だ。
アプリ設定のディレクトリ（サブディレクトリや隠しファイルも含む）と、Webサーバーの設定ファイルのバックアップを取れ。
""",
    objectives=["アプリ設定のディレクトリを中身ごと丸ごと `config_backup/` としてコピーする",
                "Webサーバーの設定ファイルを `nginx.conf.bak` という名前でコピーする（元ファイルは残す）"],
    hints=["ファイルのコピーは `cp コピー元 コピー先`。ただしディレクトリをコピーするにはオプションが必要です。",
           "`cp -r`（recursive: 再帰的）でディレクトリを中身ごとコピーできます。",
           "`cp -r config config_backup` と `cp nginx.conf nginx.conf.bak`。"],
    answer="cp -r config config_backup\ncp nginx.conf nginx.conf.bak\nls -la config_backup config_backup/db",
    explanation="""
`cp -r`（または `-R`）はディレクトリを再帰的に、隠しファイルも含めて丸ごとコピーします。
注意: 落とし穴: コピー先 `config_backup` が **既に存在する** と、`config_backup/config/` の中にコピーされます。
  中身だけを既存ディレクトリへ入れたいなら `cp -r config/. config_backup/` と書きます。
`cp -a`（archive）は `-r` に加えてパーミッション・所有者・タイムスタンプも保持するので、バックアップにはより適しています。
`cp -i` を付けると上書き前に確認してくれます。
""",
    tip="""
現場では `cp nginx.conf nginx.conf.$(date +%Y%m%d)` のように **日付付きバックアップ** を取るのが定番。
Extra Stage で習うブレース展開を使えば `cp nginx.conf{,.bak}` と短く書けます。
「設定変更の前にバックアップ」「変更後に `diff` で差分確認」をセットで習慣にしましょう。
""",
    setup=s15, check=c15,
    solution="cp -r config config_backup\ncp nginx.conf nginx.conf.bak",
    wrong=["mv nginx.conf nginx.conf.bak\ncp -r config config_backup",
           "mkdir config_backup\ncp config/app.yaml config_backup/\ncp nginx.conf nginx.conf.bak",
           "mkdir config_backup\ncp -r config config_backup\ncp nginx.conf nginx.conf.bak"],
)


# ------------------------------------------------------------------ 1-6
IMPORTANT = {"important/customers.csv": "id,name\n1,ペンギン太郎\n2,ペンギン花子\n",
             "important/contract.pdf.txt": "契約書（重要）\n"}


def s16(ctx):
    for i in range(1, 6):
        ctx.write(f"tmp_cache/session_{i}.cache", "x" * 100)
    ctx.write("tmp_cache/thumbs/a.png.cache", "x")
    ctx.write("tmp_cache/thumbs/b.png.cache", "x")
    ctx.write("tmp_cache/locked.cache", "readonly", mode=0o444)
    for k, v in IMPORTANT.items():
        ctx.write(k, v)
    for n in ("build1.tmp", "build2.tmp", "upload.tmp"):
        ctx.write(n, "temp")
    ctx.write("report.tmp.bak", "これは消さないでください（.tmp で終わっていない）\n")


def c16(ctx):
    for k, v in IMPORTANT.items():
        if ctx.read(k) != v:
            ctx.fail(f"警告: `{k}` が消えています！重要データを誤削除しました。`reset_mission` でやり直しましょう。")
    if not ctx.exists("report.tmp.bak"):
        ctx.fail("警告: `report.tmp.bak` まで消えています。`*.tmp` は「.tmp で終わる」ファイルだけにマッチします。")
    if ctx.exists("tmp_cache"):
        ctx.fail("`tmp_cache/` がまだ残っています（中に書き込み禁止のファイルもあるので注意）。")
    left = [p.name for p in ctx.work.glob("*.tmp")]
    if left:
        ctx.fail(f"`.tmp` ファイルがまだ残っています: {', '.join(sorted(left))}")


register(
    id="1-6", stage=S, title="rm -rf は慎重に",
    story="""
ディスク容量が逼迫している。不要なキャッシュのディレクトリと、カレントにある一時ファイル `*.tmp` を削除してほしい。
ただし顧客データのディレクトリと、一時ファイルの名前に .bak が付いたバックアップは保持対象だ。**絶対に消してはいけない。**
""",
    objectives=["キャッシュのディレクトリを中身ごと削除する（書き込み禁止ファイル入り）",
                "カレントディレクトリの `*.tmp` ファイルをすべて削除する",
                "顧客データと .bak のバックアップは残す"],
    hints=["ディレクトリを消すには再帰オプションが必要。書き込み禁止ファイルがあると確認を求められます。消す前に `ls` で対象を確認！",
           "`rm -r` で再帰削除、`-f` で確認なし強制削除。`*.tmp` のようなワイルドカード（glob）も使えます。",
           "まず `ls *.tmp` で対象を確認 → `rm -rf tmp_cache` → `rm *.tmp`。"],
    answer="ls -la            # まず対象を確認\nls *.tmp          # 消す前にワイルドカードの展開結果を確認\nrm -rf tmp_cache\nrm *.tmp",
    explanation="""
`rm` のオプション:
  ・`-r` … ディレクトリを中身ごと再帰的に削除
  ・`-f` … 確認なし・存在しなくてもエラーにしない（強制）
  ・`-i` … 1ファイルずつ確認（不安なときに）
`*.tmp` はシェルが **実行前に** `build1.tmp build2.tmp upload.tmp` へ展開します（glob）。
`report.tmp.bak` は「.tmp で終わらない」のでマッチしません。消す前に `ls *.tmp` で展開結果を確認するのがプロの作法です。
Linux の `rm` には **ゴミ箱がありません**。消したら基本的に戻りません。
""",
    tip="""
注意: 伝説の事故: `rm -rf $DIR/` で変数 `DIR` が空だと `rm -rf /` になります。
スクリプトでは `rm -rf "${DIR:?DIR is empty}"` と書くと、変数が空のときに停止してくれます。
また `rm -rf * .tmp`（スペースが混入）は **全ファイル削除** になる恐怖のタイプミス。
本番では「`ls` で確認 → 同じ引数で `rm`」のクセを徹底しましょう。
""",
    setup=s16, check=c16,
    solution="rm -rf tmp_cache\nrm *.tmp",
    wrong=["rm -rf tmp_cache important\nrm *.tmp", "rm -rf tmp_cache\nrm *.tmp*", "rm *.tmp"],
)


# ------------------------------------------------------------------ 1-7
def s17(ctx):
    code = ctx.rand(6)
    old = ctx.rand(6)
    ctx.data["code"] = code
    lines = ["# Penguin Shop server log", f"# server version: v{random.randint(2, 5)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
             "# started at 2025-11-18 09:00:00"]
    for i in range(997):
        lv = random.choice(["INFO"] * 8 + ["WARN", "ERROR"])
        lines.append(f"2025-11-18 09:{i // 60 % 60:02d}:{i % 60:02d} {lv} req_id={random.randint(10000, 99999)} path=/api/item/{random.randint(1, 500)}")
    ctx.write("server.log", "\n".join(lines) + "\n")
    man = [f"運用マニュアル {i}行目: 定期作業の手順が書かれています。" for i in range(1, 2001)]
    man[random.randint(200, 700)] = f"■ 旧パスコード: {old} （※2024年に廃止。使用不可）"
    man[random.randint(1200, 1900)] = f"■ 最新パスコード: {code}"
    ctx.write("manual.txt", "\n".join(man) + "\n")


def c17(ctx):
    log = ctx.lines("server.log")
    h = ctx.lines("header.txt")
    if h is None:
        ctx.fail("`header.txt` がまだありません。")
    if h != log[:3]:
        ctx.fail(f"`header.txt` が server.log の先頭3行と一致しません（現在 {len(h)} 行）。行数を指定するオプションを使いましょう。")
    t = ctx.lines("last5.txt")
    if t is None:
        ctx.fail("`last5.txt` がまだありません。")
    if t != log[-5:]:
        ctx.fail(f"`last5.txt` が server.log の末尾5行と一致しません（現在 {len(t)} 行）。")
    ctx.need_submit(ctx.data["code"], "最新パスコード")


register(
    id="1-7", stage=S, title="巨大ログの覗き見術",
    story="""
1000行あるサーバーログと、2000行のマニュアルがある。`cat` で全部表示すると画面が流れて何も読めない…。
必要な部分だけを **切り取って** 確認しよう。
""",
    objectives=["サーバーログの **先頭3行** を `header.txt` に保存する",
                "サーバーログの **末尾5行** を `last5.txt` に保存する",
                "`less` でマニュアルを開き、`/` 検索で「最新パスコード」を探して `submit` する（旧パスコードは無効！）"],
    hints=["ファイルの先頭だけ見るコマンド、末尾だけ見るコマンドがあります。画面に出た結果は `>` でファイルに保存できます。",
           "`head -n 行数` と `tail -n 行数`。`less ファイル` の中では `/文字列` で検索、`n` で次の候補、`q` で終了。",
           "`head -n 3 server.log > header.txt` / `tail -n 5 server.log > last5.txt` / `less manual.txt` → `/パスコード` → `n` で次へ。"],
    answer="head -n 3 server.log > header.txt\ntail -n 5 server.log > last5.txt\nless manual.txt     # /パスコード で検索、n で次へ、q で終了\nsubmit <<code>>",
    explanation="""
・`head -n 3 file` … 先頭3行（`-n` を省略すると10行）
・`tail -n 5 file` … 末尾5行。`tail -n +2 file` だと「2行目以降すべて」（CSVのヘッダー除去に便利）
・`> file` … 画面に出るはずの出力（標準出力）をファイルに書き込む（上書き）。Stage 2 で詳しく！
・`less file` … ページャ。巨大ファイルでも一瞬で開けます。主な操作:
    `Space`/`b` で1画面進む/戻る、`g`/`G` で先頭/末尾、`/文字列` で前方検索、`?文字列` で後方検索、
    `n`/`N` で次/前の検索結果、`q` で終了。
""",
    tip="""
障害対応の最重要コマンドは **`tail -f /var/log/app.log`**。ログに追記される内容をリアルタイムで流し続けます（Ctrl+C で終了）。
`less +F` でも同様の追従ができ、Ctrl+C で止めてそのまま検索モードに移れるので上級者に人気です。
巨大ログに `cat` や `vim` を使うとメモリを食ったり固まったりするので、**まずは `less` / `tail`** が鉄則です。
""",
    setup=s17, check=c17,
    solution='head -n 3 server.log > header.txt\ntail -n 5 server.log > last5.txt\nsubmit "$(grep "最新パスコード" manual.txt | sed "s/.*: //")"',
    wrong=["head server.log > header.txt\ntail server.log > last5.txt",
           'head -n 3 server.log > header.txt\ntail -n 5 server.log > last5.txt\nsubmit "$(grep "旧パスコード" manual.txt | sed "s/.*: //;s/ .*//")"'],
)


# ------------------------------------------------------------------ 1-8
# ファイル整理課題のダミー認証情報。API_KEY を含め、実サービスのキーやパスワードではありません。
ENVS = {"messy_project/.env": "DB_PASSWORD=p@ssw0rd\n",
        "messy_project/api/.env.production": "API_KEY=prod-xxxxxxxx\n",
        "messy_project/frontend/.env.local": "NEXT_PUBLIC_DEBUG=true\n"}


def s18(ctx):
    for k, v in ENVS.items():
        ctx.write(k, v)
    ctx.write("messy_project/.env.example", "DB_PASSWORD=\nAPI_KEY=\n")
    ctx.write("messy_project/README.md", "# messy project\n")
    ctx.write("messy_project/api/server.js", "// api\n")
    ctx.write("messy_project/frontend/index.html", "<html></html>\n")
    ctx.write("messy_project/frontend/old/memo.txt", "TODO 整理する\n")
    ctx.write("messy_project/.git/HEAD", "ref: refs/heads/main\n")
    ctx.write("messy_project/docs/.keep", "")


def c18(ctx):
    dst = "backup/secrets/2025"
    if not ctx.isdir(dst):
        ctx.fail(f"`{dst}/` ディレクトリがありません。")
    for k, v in ENVS.items():
        name = k.split("/")[-1]
        if ctx.exists(k):
            ctx.fail(f"`{k}` がまだ元の場所に残っています（コピーではなく **移動** してください）。")
        if ctx.read(f"{dst}/{name}") != v:
            ctx.fail(f"`{dst}/{name}` がありません。")
    if not ctx.exists("messy_project/.env.example"):
        ctx.fail("`.env.example` はテンプレートなので、元の場所に残してください。")
    if ctx.exists(f"{dst}/.env.example"):
        ctx.fail("`.env.example` はバックアップ対象外です。元の場所に戻しましょう。")


register(
    id="1-8", stage=S, title="【実践】散らかった機密ファイルの整理",
    story="""
退職した前任者のプロジェクトが散らかっている。パスワード入りの設定ファイルが
各サブディレクトリに紛れているらしい。セキュリティ監査の前に、これらを1か所のバックアップ階層へ **移動** して整理せよ。
""",
    objectives=["`backup/secrets/2025/` を作成する",
                "前任者のプロジェクトに散らばった、パスワードなどの値が入った設定ファイルをそこへ **移動** する",
                "ただし値の入っていない設定テンプレートは元の場所に残す"],
    hints=["隠しファイルは `ls -la` で各ディレクトリを確認すれば見つかります。どこにあるか一気に調べる方法もあります。",
           "`mkdir -p` で深い階層を作成、`mv 移動元... 移動先/` で複数ファイルを一度に移動できます。探索は `ls -laR` で隠れたものを含めて一覧し、cat で設定の用途を確かめます。",
           "`mkdir -p backup/secrets/2025` → `mv messy_project/.env messy_project/api/.env.production messy_project/frontend/.env.local backup/secrets/2025/`"],
    answer="find messy_project -name '.env*'     # どこにあるか調べる\nmkdir -p backup/secrets/2025\nmv messy_project/.env messy_project/api/.env.production messy_project/frontend/.env.local backup/secrets/2025/\nls -la backup/secrets/2025",
    explanation="""
`mv` は「移動」と「名前変更（リネーム）」の両方を担うコマンドです:
  ・`mv a.txt dir/` … dir の中へ移動
  ・`mv a.txt b.txt` … 名前を変更
  ・`mv f1 f2 f3 dir/` … 最後の引数がディレクトリなら、複数ファイルをまとめて移動
`mv -i` で上書き前に確認、`mv -n` で上書きしない。移動先の末尾に `/` を付けておくと、
ディレクトリが存在しない場合に「リネーム」と誤解されず、エラーで気づけます。
`ls -laR` や `find -name '.env*'` で隠しファイルを効率よく探せます（find は Stage 2 で本格的に！）。
""",
    tip="""
`.env` は Git にコミットしてはいけない代表格。`.gitignore` に `.env*` と `!.env.example` を書くのが定石です。
誤ってコミットした秘密情報は **履歴に残り続ける** ので、キーのローテーション（再発行）が必要になります。
機密ファイルを集めたら `chmod 600` で自分以外読めないようにしておくとさらに安全です（Stage 3）。
""",
    setup=s18, check=c18,
    solution="mkdir -p backup/secrets/2025\nmv messy_project/.env messy_project/api/.env.production messy_project/frontend/.env.local backup/secrets/2025/",
    wrong=["mkdir -p backup/secrets/2025\ncp messy_project/.env messy_project/api/.env.production messy_project/frontend/.env.local backup/secrets/2025/",
           "mkdir -p backup/secrets/2025\nmv messy_project/.env* messy_project/api/.env.production messy_project/frontend/.env.local backup/secrets/2025/"],
)
