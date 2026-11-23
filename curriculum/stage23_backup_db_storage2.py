"""Stage 23: バックアップ・DB・ストレージ応用・ログ運用。サンドボックス内の偽データと採取済み出力・設定例だけを使う。"""
import hashlib
import json
import re
import secrets
import shlex
import subprocess

from engine.runner import register

S = 23
NOTE = ("作業対象はこの課題のフォルダだけです。実OSのサービス・ネットワーク・ストレージ・設定は変更せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないツールは採取済みの出力と設定例から診断・記述します（コマンドは実行しません）。")
R = secrets.randbelow


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text, readonly=True):
    ctx.write(name, text)
    if readonly:
        ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(sha(ctx.need_file(name)) == h, name + ' は原本です。変更しないでください。')


def rj(ctx, name):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def parse(ctx, name):
    """スクリプトを1行1コマンドとして分解する。export K=V は環境として返す。"""
    env, out = {}, []
    for ln in ctx.need_file(name).splitlines():
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        t = toks(ctx, s)
        if t[0] == 'export' and len(t) > 1 and '=' in t[1]:
            k, v = t[1].split('=', 1)
            env[k] = v
            continue
        out.append(t)
    ctx.require(out, name + ' にコマンドがありません。')
    return out, env


def optv(t, *names):
    for i, x in enumerate(t):
        if x in names and i + 1 < len(t):
            return t[i + 1]
        for n in names:
            if x.startswith(n + '='):
                return x.split('=', 1)[1]
    return None


def find(ctx, cmds, tool, subc=None):
    for t in cmds:
        for i, x in enumerate(t):
            if x == tool and (i == 0 or t[i - 1] == '|'):
                seg = []
                for y in t[i:]:
                    if y in ('|', '>', '>>', '&&', ';'):
                        break
                    seg.append(y)
                if subc is None or subc in seg[1:]:
                    return seg
    ctx.fail(f'{tool}{(" " + subc) if subc else ""} のコマンドが見つかりません。')


def kv(text, sep='='):
    d = {}
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s[0] in '#;[':
            continue
        if sep == ' ':
            p = s.split(None, 1)
        else:
            p = [x.strip() for x in s.split('=', 1)]
        if len(p) == 2:
            d[p[0].strip()] = p[1].strip()
    return d


def mb(v):
    m = re.fullmatch(r'(\d+)\s*([KMG]?)B?', v.strip(), re.I)
    if not m:
        return None
    return int(m.group(1)) * {'': 1 / 1048576, 'K': 1 / 1024, 'M': 1, 'G': 1024}[m.group(2).upper()]


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'23-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='バックアップは「取れた」ではなく「戻せた」で完成です。設定は変更前に控えを取り、観測で検証しましょう。')


# ------------------------------------------------------------ 1 restic
def s1(ctx):
    d = dict(repo='repo-' + secrets.token_hex(3), kd=3 + R(7), kw=2 + R(5), km=2 + R(11))
    ctx.data.update(d)
    put(ctx, 'pw.txt', 'pw-' + secrets.token_hex(6) + '\n')
    put(ctx, 'data/a.txt', 'customer-' + secrets.token_hex(4) + '\n')
    ctx.write('requirements.txt', f'データ data/ を暗号化リポジトリ {d["repo"]} にresticでバックアップする restic.sh を書く。パスワードは pw.txt（--password-file）。\n'
              f'順に init / backup / forget（保持: 日次{d["kd"]}・週次{d["kw"]}・月次{d["km"]}、同時にprune）/ check / restore（最新を restore/ へ）の5工程。\n')


def c1(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, env = parse(ctx, 'restic.sh')
    idx = {}
    for sub in ('init', 'backup', 'forget', 'check', 'restore'):
        t = find(ctx, cmds, 'restic', sub)
        idx[sub] = next(i for i, c in enumerate(cmds) if sub in c[1:] and c[0] == 'restic')
        repo = optv(t, '-r', '--repo') or env.get('RESTIC_REPOSITORY')
        ctx.require(repo and repo.rstrip('/').lstrip('./') == d['repo'], f'restic {sub}: リポジトリ {d["repo"]} を -r または RESTIC_REPOSITORY で指定します。')
        pw = optv(t, '--password-file') or env.get('RESTIC_PASSWORD_FILE')
        ctx.require(pw == 'pw.txt', f'restic {sub}: パスワードは --password-file pw.txt で渡します（コマンドラインに平文を書かない）。')
        if sub == 'backup':
            ctx.require('data' in t or 'data/' in t, 'backupの対象は data/ です。')
        if sub == 'forget':
            for opt, k in (('--keep-daily', 'kd'), ('--keep-weekly', 'kw'), ('--keep-monthly', 'km')):
                ctx.require(optv(t, opt) == str(d[k]), f'{opt} {d[k]} を指定します。')
            ctx.require('--prune' in t or any('prune' in c for c in cmds), '不要データの実削除には --prune（または restic prune）が必要です。')
        if sub == 'restore':
            ctx.require('latest' in t, 'restoreは最新スナップショット latest を指定します。')
            ctx.require((optv(t, '--target', '-t') or '').strip('/') == 'restore', '--target restore へ復元します。')
    ctx.require(idx['init'] < idx['backup'], 'initはbackupより先です。')


SOL1 = """cat > restic.sh <<'EOF'
export RESTIC_REPOSITORY=<<repo>>
export RESTIC_PASSWORD_FILE=pw.txt
restic init
restic backup data
restic forget --keep-daily <<kd>> --keep-weekly <<kw>> --keep-monthly <<km>> --prune
restic check
restic restore latest --target restore
EOF"""
mission(1, 'restic: 暗号化リポジトリのバックアップと保持ポリシー',
        '小規模サーバーの用意された業務データをrestic（init / backup / prune / check / restore）で暗号化バックアップします。requirements.txtの保持ポリシーに合わせて restic.sh を書いてください。',
        ['restic.sh に5工程を書く', '保持ポリシーとprune、パスワードファイルを正しく指定する'], s1, c1, SOL1,
        ["echo 'restic backup data' > restic.sh",
         "printf 'restic -r <<repo>> init\\nrestic -r <<repo>> backup data\\nrestic -r <<repo>> forget --keep-last 3 --prune\\nrestic -r <<repo>> check\\nrestic -r <<repo>> restore latest --target restore\\n' > restic.sh"],
        'resticはリポジトリを常に暗号化し、パスワードは --password-file か RESTIC_PASSWORD_FILE で渡します（コマンド履歴に残さないため）。forget は保持ポリシーに合わないスナップショットを外し、--prune でデータ本体を削除します。check でリポジトリの整合性を確認し、restore で戻せることを定期的に試します。',
        '各工程のコマンドと、保持ポリシーのオプション名を整理します。', 'export で RESTIC_REPOSITORY と RESTIC_PASSWORD_FILE を設定してからサブコマンドを並べます。')


# ------------------------------------------------------------ 2 borg
def s2(ctx):
    d = dict(repo='borg-' + secrets.token_hex(3) + '.repo', arc='arc-' + secrets.token_hex(2), kd=3 + R(7), kw=2 + R(5), km=2 + R(8))
    ctx.data.update(d)
    put(ctx, 'data/a.txt', 'ledger-' + secrets.token_hex(4) + '\n')
    ctx.write('requirements.txt', f'borgで data/ を暗号化リポジトリ {d["repo"]} にアーカイブ名 {d["arc"]} で保存する borg.sh を書く。\n'
              f'init（鍵はリポジトリ内に持つ repokey 系の暗号化）/ create / prune（日次{d["kd"]}・週次{d["kw"]}・月次{d["km"]}）/ check / extract の5工程。\n')


def c2(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, env = parse(ctx, 'borg.sh')
    t = find(ctx, cmds, 'borg', 'init')
    enc = optv(t, '-e', '--encryption')
    ctx.require(enc and re.fullmatch(r'(repokey|keyfile)(-blake2)?', enc), '暗号化なしは不可です。--encryption=repokey-blake2 などを指定します。')
    ctx.require(d['repo'] in t, 'borg init の対象はリポジトリ ' + d['repo'])
    t = find(ctx, cmds, 'borg', 'create')
    ctx.require(any(x.rstrip('/') == f'{d["repo"]}::{d["arc"]}' for x in t), 'borg create は repo::アーカイブ名 の形式で指定します。')
    ctx.require('data' in t or 'data/' in t, 'createの対象は data/ です。')
    t = find(ctx, cmds, 'borg', 'prune')
    for opt, k in (('--keep-daily', 'kd'), ('--keep-weekly', 'kw'), ('--keep-monthly', 'km')):
        ctx.require(optv(t, opt) == str(d[k]), f'borg prune: {opt} {d[k]} を指定します。')
    ctx.require(d['repo'] in t, 'borg prune のリポジトリ指定がありません。')
    t = find(ctx, cmds, 'borg', 'check')
    ctx.require(d['repo'] in ' '.join(t), 'borg check のリポジトリ指定がありません。')
    t = find(ctx, cmds, 'borg', 'extract')
    ctx.require(f'{d["repo"]}::{d["arc"]}' in t, 'borg extract は repo::アーカイブ名 を指定します。')


SOL2 = """cat > borg.sh <<'EOF'
export BORG_PASSCOMMAND="cat pw.txt"
borg init --encryption=repokey-blake2 <<repo>>
borg create --stats <<repo>>::<<arc>> data
borg prune --keep-daily <<kd>> --keep-weekly <<kw>> --keep-monthly <<km>> <<repo>>
borg check <<repo>>
borg extract <<repo>>::<<arc>>
EOF"""
mission(2, 'borg: init/create/prune/check/extract と暗号化リポジトリ',
        'borgでも同じ運用を設計します。リポジトリ作成（暗号化モード）、アーカイブ作成、保持ポリシーでのprune、整合性check、extractでの復元をborg.shにまとめてください。',
        ['borg.sh に5工程を書く', '暗号化モードとアーカイブ名 repo::name を正しく指定する'], s2, c2, SOL2,
        ["echo 'borg init --encryption=none <<repo>>' > borg.sh",
         "printf 'borg init -e repokey <<repo>>\\nborg create <<repo>> data\\nborg prune --keep-daily 3 <<repo>>\\nborg check <<repo>>\\nborg extract <<repo>>\\n' > borg.sh"],
        'borg init の --encryption で repokey（鍵をリポジトリ内に保存）か keyfile（鍵を手元に保存）を選びます。none は暗号化なしです。アーカイブは repo::name で指定し、prune は保持ポリシーの外を削除します。鍵とパスフレーズのバックアップ（borg key export）を別に保管しないと復元できなくなります。',
        'resticとの違いは、アーカイブ名を repo::name で指定する点です。', 'borg init -e モード リポジトリ の形から始めます。')


# ------------------------------------------------------------ 3 rsync + tar
def s3(ctx):
    d = dict(prev='gen-2026-11-' + str(10 + R(9)), new='gen-2026-11-29', snar='snap-' + secrets.token_hex(2) + '.snar',
             full='full-' + secrets.token_hex(2) + '.tar', inc='inc-' + secrets.token_hex(2) + '.tar')
    ctx.data.update(d)
    put(ctx, 'src/a.txt', 'x\n')
    ctx.mkdir('backups/' + d['prev'])
    ctx.write('requirements.txt', f'1) src/ を backups/{d["new"]}/ へrsyncで世代バックアップする。前世代は backups/{d["prev"]}/ で、変更のないファイルはハードリンクで容量を節約する（--link-dest）。-aと--deleteを付ける。\n'
              f'2) tarの増分: スナップショットファイル {d["snar"]} を使い、フルを {d["full"]}、増分を {d["inc"]} に作る（--listed-incremental）。対象は src。\nコマンドを backup.sh に1行ずつ書く。\n')


def c3(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, _ = parse(ctx, 'backup.sh')
    t = find(ctx, cmds, 'rsync')
    ctx.require(any(x.startswith('-') and not x.startswith('--') and 'a' in x for x in t) or '--archive' in t, 'rsync は -a（アーカイブ）で。')
    ctx.require('--delete' in t, '--delete で削除も反映します。')
    ld = optv(t, '--link-dest')
    ctx.require(ld, '--link-dest で前世代を指定します。')
    ctx.require(ld.rstrip('/').split('/')[-1] == d['prev'] and (ld.startswith('../') or ld.startswith('/') or ld.startswith('backups/')), '--link-dest は前世代 ' + d['prev'] + ' を指します（相対パスは宛先ディレクトリからの相対）。')
    ctx.require(any(x.rstrip('/') == 'backups/' + d['new'] for x in t) or any(x.rstrip('/').endswith(d['new']) for x in t), '宛先は新世代 ' + d['new'] + ' です。')
    ctx.require('src/' in t or 'src' in t, 'rsyncの転送元は src/ です。')
    tars = [x for x in cmds if x and x[0] == 'tar']
    ctx.require(len(tars) >= 2, 'tar を2回（フルと増分）書きます。')
    res = {}
    for x in tars:
        s = optv(x, '--listed-incremental', '-g')
        f = optv(x, '--file', '-f')
        ctx.require(s, 'tar に --listed-incremental（または -g）でスナップショットファイルを渡します。')
        res[f] = s
    ctx.require(set(res) >= {d['full'], d['inc']}, 'フルは ' + d['full'] + '、増分は ' + d['inc'] + ' に作ります。')
    ctx.require(res[d['full']] == res[d['inc']] == d['snar'], 'フルと増分で同じスナップショットファイル ' + d['snar'] + ' を使います。')
    ctx.require([x for x in tars if optv(x, '--file', '-f') == d['full']] and cmds.index([x for x in tars if optv(x, '--file', '-f') == d['full']][0]) < cmds.index([x for x in tars if optv(x, '--file', '-f') == d['inc']][0]), 'フルが先、増分が後です。')


SOL3 = """cat > backup.sh <<'EOF'
rsync -a --delete --link-dest=../<<prev>> src/ backups/<<new>>/
tar --create --listed-incremental=<<snar>> --file=<<full>> src
tar --create --listed-incremental=<<snar>> --file=<<inc>> src
EOF"""
mission(3, 'rsync --link-dest の世代管理と tar --listed-incremental の増分',
        '2種類の世代バックアップを設計します。rsyncは --link-dest で前世代とのハードリンクにより世代ごとの完全なツリーを少ない容量で持ち、tarは --listed-incremental のスナップショットファイルで増分を作ります。backup.sh に書いてください。',
        ['rsync --link-dest の世代バックアップ行', 'tar のフルと増分（同じsnar）'], s3, c3, SOL3,
        ["echo 'rsync -a src/ backups/<<new>>/' > backup.sh",
         "printf 'rsync -a --delete --link-dest=backups/<<new>> src/ backups/<<new>>/\\ntar -cf <<full>> src\\ntar -cf <<inc>> src\\n' > backup.sh"],
        '--link-dest=DIR は、DIRにある同一ファイルを新しい宛先へハードリンクし、変更分だけ実コピーします。相対パスは宛先からの相対なので ../前世代 と書きます。tarの --listed-incremental=FILE は、ファイルが無ければフル（レベル0）、同じFILEを再利用すると前回以降の変更だけの増分になります。増分を戻す時は古い順にextractします。',
        'rsyncは前世代の指し方、tarは同じスナップショットファイルの再利用がポイントです。', 'rsync -a --delete --link-dest=../前世代 src/ 宛先/、tar --create --listed-incremental=SNAR --file=名前 src。')


# ------------------------------------------------------------ 4 RPO/RTO 3-2-1
def s4(ctx):
    k = 2 + R(7)
    interval = [4, 6, 12, 24][R(4)]
    rpo_t = [6, 12, 24][R(3)]
    rto_t = [2, 4, 8][R(3)]
    n = 360 * k
    copies = [('primary', 'disk', 'onsite'), ('nas', 'disk', 'onsite')]
    extra = [None, ('tape', 'tape', 'offsite'), ('cloud', 'object', 'offsite'), ('nas2', 'disk', 'onsite')][R(4)]
    if extra:
        copies.append(extra)
    rpo, rto = interval, k + 1
    meets = len(copies) >= 3 and len({c[1] for c in copies}) >= 2 and any(c[2] == 'offsite' for c in copies)
    ctx.data.update(rpo=rpo, rto=rto, mrpo='true' if rpo <= rpo_t else 'false', mrto='true' if rto <= rto_t else 'false', m321='true' if meets else 'false')
    put(ctx, 'policy.txt', f'バックアップ間隔: {interval}時間ごと\n復元対象データ量: {n}GB（1GB=1000MB）\n復元スループット: 100MB/s\n復元後の検証・切替作業: 1時間\n'
        f'要件: RPO {rpo_t}時間以内 / RTO {rto_t}時間以内\n')
    put(ctx, 'inventory.txt', 'コピー名 媒体 設置場所\n' + ''.join(f'{a} {b} {c}\n' for a, b, c in copies))
    ctx.write('requirements.txt', 'policy.txt と inventory.txt を読み、plan.json に rpo_hours, rto_hours（データ転送時間+検証時間）, meets_rpo, meets_rto, meets_321（3コピー・2種類の媒体・1つはオフサイト）を書く。\n')


def c4(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'plan.json')
    ctx.require(j.get('rpo_hours') == d['rpo'], 'RPOはバックアップ間隔（最悪この時間分のデータを失う）です。')
    ctx.require(j.get('rto_hours') == d['rto'], 'RTO = データ量÷スループット + 検証作業 です。')
    ctx.require(j.get('meets_rpo') is (d['mrpo'] == 'true'), 'meets_rpo の判定が違います。')
    ctx.require(j.get('meets_rto') is (d['mrto'] == 'true'), 'meets_rto の判定が違います。')
    ctx.require(j.get('meets_321') is (d['m321'] == 'true'), '3-2-1原則: コピー3つ以上・媒体2種類以上・オフサイト1つ以上を確認します。')


SOL4 = """echo '{"rpo_hours": <<rpo>>, "rto_hours": <<rto>>, "meets_rpo": <<mrpo>>, "meets_rto": <<mrto>>, "meets_321": <<m321>>}' > plan.json"""
mission(4, 'RPOとRTOを計算し3-2-1原則で評価する',
        '経営層から「バックアップは大丈夫か」と聞かれました。RPO（許容できるデータ損失時間）とRTO（復旧にかかる時間）を現状から算出し、3-2-1原則（3コピー・2種類の媒体・1つはオフサイト）を満たすか評価してください。',
        ['運用方針からRPO/RTOを算出', 'バックアップ一覧で3-2-1を判定しplan.jsonへ'], s4, c4, SOL4,
        ["echo '{\"rpo_hours\": 1, \"rto_hours\": 1, \"meets_rpo\": true, \"meets_rto\": true, \"meets_321\": true}' > plan.json", 'echo "{}" > plan.json'],
        'RPOは最後のバックアップから障害までに失う最大時間で、バックアップ間隔が下限になります。RTOは復旧完了までの時間で、データ転送だけでなく検証や切替も含みます。3-2-1原則は、データのコピーを3つ、2種類の媒体、1つはオフサイトに置くことで、同時に壊れる原因（災害・ランサムウェア）を分散します。',
        '数字は policy.txt、コピーの属性は inventory.txt を読みます。', 'RTO = GB×1000÷100MB/s÷3600 + 検証。媒体の種類数は重複を除いて数えます。')


# ------------------------------------------------------------ 5 mysqldump + binlog
def s5(ctx):
    n = 10 + R(80)
    db = 'shop' + secrets.token_hex(2)
    pos = 400 + R(9000)
    h, m = 9 + R(8), R(60)
    stop = f'2026-11-20 {h:02d}:{m:02d}:00'
    ctx.data.update(db=db, n=n, pos=pos, stop=stop, out=db + '.sql.gz', f0=f'mysql-bin.{n:06d}', fl=[f'mysql-bin.{n + i:06d}' for i in range(3)])
    put(ctx, 'dump_head.sql', f'-- MySQL dump (採取済み)\n-- CHANGE MASTER TO MASTER_LOG_FILE=\'mysql-bin.{n:06d}\', MASTER_LOG_POS={pos};\n')
    put(ctx, 'binlogs.txt', 'mysql> SHOW BINARY LOGS;\n' + ''.join(f'mysql-bin.{n + i:06d} {100000 + i}\n' for i in range(-2, 3)).replace(f'mysql-bin.{n + 2:06d}', f'mysql-bin.{n + 2:06d}'))
    ctx.write('requirements.txt', f'1) データベース {db} を、InnoDBをロックせず一貫性のある形で（--single-transaction）、ストアドルーチンとトリガーも含め、binlog位置をコメントで残して（--source-data=2 か --master-data=2）、gzipして {db}.sql.gz へ出す1行を dump.sh に書く。\n'
              f'2) 事故時刻 {stop} の直前までのbinlogを、ダンプ時点の位置から再生する mysqlbinlog の1行を recover.sh に書く（--start-position と --stop-datetime。対象はダンプ時のbinlogファイル以降の全ファイル。結果はmysqlへパイプ）。\n')


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, _ = parse(ctx, 'dump.sh')
    t = find(ctx, cmds, 'mysqldump')
    ctx.require('--single-transaction' in t, '--single-transaction でテーブルをロックせずに一貫性を得ます。')
    ctx.require('--routines' in t and '--triggers' in t, '--routines と --triggers を付けます。')
    ctx.require(optv(t, '--source-data', '--master-data') == '2', 'binlog位置をコメントで残す --source-data=2（旧 --master-data=2）を付けます。')
    ctx.require(d['db'] in t, 'DB名 ' + d['db'])
    ctx.require(any(x == 'gzip' for x in sum(cmds, [])) and d['out'] in sum(cmds, []), 'gzipへパイプし ' + d['out'] + ' へ保存します。')
    cmds, _ = parse(ctx, 'recover.sh')
    t = find(ctx, cmds, 'mysqlbinlog')
    ctx.require(optv(t, '--start-position') == str(d['pos']), 'ダンプ時の位置 ' + str(d['pos']) + ' を --start-position に。')
    ctx.require(optv(t, '--stop-datetime') == d['stop'], '--stop-datetime で事故時刻を指定します。')
    got = [x for x in t if re.fullmatch(r'.*mysql-bin\.\d+', x)]
    ctx.require(sorted(x.split('/')[-1] for x in got) == d['fl'], 'ダンプ時のbinlogファイル以降の全てのファイルを順に渡します。')
    ctx.require(any(c[:1] == ['mysql'] or 'mysql' in c for c in cmds) and '|' in sum(cmds, []), 'mysql へパイプして適用します。')


SOL5 = """echo "mysqldump --single-transaction --routines --triggers --source-data=2 <<db>> | gzip > <<out>>" > dump.sh
echo "mysqlbinlog --start-position=<<pos>> --stop-datetime='<<stop>>' <<fl>> | mysql" > recover.sh"""
SOL5 = SOL5.replace('<<fl>>', '<<f0>> mysql-bin.<<n1>> mysql-bin.<<n2>>')


def s5b(ctx):
    s5(ctx)
    ctx.data.update(n1=f'{ctx.data["n"] + 1:06d}', n2=f'{ctx.data["n"] + 2:06d}')
    ctx.save_data() if False else None


mission(5, 'mysqldump --single-transaction とbinlogによる時点復旧',
        'MySQL/MariaDBの日次ダンプと、binlogを使った事故直前までの復旧手順を用意します。ダンプ先頭のコメントとSHOW BINARY LOGSの採取結果を読み、mysqldumpの行とmysqlbinlogの行を書いてください。',
        ['dump.sh に一貫性のあるmysqldump', 'recover.sh にbinlogの時点指定再生'], s5b, c5, SOL5,
        ["echo 'mysqldump <<db>> > <<out>>' > dump.sh\necho 'mysqlbinlog <<f0>> | mysql' > recover.sh",
         "echo \"mysqldump --lock-all-tables <<db>> | gzip > <<out>>\" > dump.sh\necho \"mysqlbinlog --stop-datetime='<<stop>>' <<f0>> | mysql\" > recover.sh"],
        '--single-transaction はInnoDBでREPEATABLE READのトランザクションを使い、ロックなしで一貫したダンプを得ます（MyISAMには効きません）。--source-data=2（旧 --master-data=2）はダンプ時のbinlogファイルと位置をコメントで残し、そこからmysqlbinlogの --start-position で差分を再生して、--stop-datetime で事故の直前に止められます。',
        'ダンプは位置のコメントを残し、復旧はその位置からbinlogを再生します。', 'binlogs.txtで、ダンプ時のファイルから最新までの名前を確認します。')


# ------------------------------------------------------------ 6 MySQL GRANT + my.cnf + slow log
def s6(ctx):
    ram = [8, 16, 32][R(3)]
    d = dict(ram=ram, bp=ram * 1024 // 2, db='app' + secrets.token_hex(2), host='10.0.%d.%%' % (1 + R(200)), pw='Pw-' + secrets.token_hex(5),
             slow='/var/log/mysql/slow-' + secrets.token_hex(2) + '.log')
    rows = [R(900000) + 10000 for _ in range(4)]
    t = [round(1.5 + R(900) / 10, 1) for _ in range(4)]
    while len(set(t)) < 4:
        t = [round(1.5 + R(900) / 10, 1) for _ in range(4)]
    d['worst'] = rows[t.index(max(t))]
    ctx.data.update(d)
    ctx.write('my.cnf', '[mysqld]\ndatadir=/var/lib/mysql\ninnodb_buffer_pool_size=128M\nmax_connections=151\nslow_query_log=0\nlong_query_time=10\nlog_bin=mysql-bin\n')
    put(ctx, 'slow.log', ''.join(f'# Time: 2026-11-20T0{i}:00:00\n# Query_time: {t[i]}  Lock_time: 0.0  Rows_sent: 1  Rows_examined: {rows[i]}\nSELECT * FROM orders WHERE note LIKE \'%x{i}%\';\n' for i in range(4)))
    ctx.write('requirements.txt', f'このDBサーバーはRAM {ram}GBの専用機。my.cnfで innodb_buffer_pool_size をRAMの半分にし、スロークエリログを有効（slow_query_log=1, slow_query_log_file={d["slow"]}, long_query_time=1）にする。他の行（datadir, log_bin）は残す。\n'
              f'grants.sql に、ユーザー \'app\'@\'{d["host"]}\' を作成（パスワード {d["pw"]}）し、{d["db"]} だけの SELECT,INSERT,UPDATE,DELETE を GRANT する。slow.log で最も遅いクエリの Rows_examined を worst.txt に書く。\n')


def c6(ctx):
    need_ro(ctx)
    d = ctx.data
    c = kv(ctx.need_file('my.cnf'))
    ctx.require(c.get('datadir') == '/var/lib/mysql' and c.get('log_bin') == 'mysql-bin', 'datadirとlog_binの行は残します。')
    ctx.require(mb(c.get('innodb_buffer_pool_size', '')) == d['bp'], f'innodb_buffer_pool_size はRAMの半分（{d["bp"]}M）です。')
    ctx.require(c.get('slow_query_log', '').upper() in ('1', 'ON'), 'slow_query_log を有効にします。')
    ctx.require(c.get('slow_query_log_file') == d['slow'], 'slow_query_log_file を指定します。')
    ctx.require(c.get('long_query_time') in ('1', '1.0'), 'long_query_time は 1 秒にします。')
    sql = ' '.join(ctx.need_file('grants.sql').split())
    ctx.require(re.search(r"CREATE USER (IF NOT EXISTS )?'app'@'" + re.escape(d['host']) + r"' IDENTIFIED BY '" + re.escape(d['pw']) + "'", sql, re.I), 'CREATE USER ... IDENTIFIED BY で作成します。')
    m = re.search(r"GRANT ([A-Z, ]+) ON `?" + d['db'] + r"`?\.\* TO 'app'@'" + re.escape(d['host']) + "'", sql, re.I)
    ctx.require(m, f'GRANT ... ON {d["db"]}.* TO 用のGRANT文が必要です。')
    ctx.require({x.strip().upper() for x in m.group(1).split(',')} == {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}, '必要最小限の4権限だけにします（ALLは不可）。')
    ctx.require('GRANT OPTION' not in sql.upper() and '*.*' not in sql, 'WITH GRANT OPTION や *.* は使いません。')
    ctx.require(ctx.need_file('worst.txt').strip() == str(d['worst']), '最もQuery_timeが長いクエリのRows_examinedです。')


SOL6 = """cat > my.cnf <<'EOF'
[mysqld]
datadir=/var/lib/mysql
innodb_buffer_pool_size=<<bp>>M
max_connections=151
slow_query_log=1
slow_query_log_file=<<slow>>
long_query_time=1
log_bin=mysql-bin
EOF
cat > grants.sql <<'EOF'
CREATE USER 'app'@'<<host>>' IDENTIFIED BY '<<pw>>';
GRANT SELECT, INSERT, UPDATE, DELETE ON <<db>>.* TO 'app'@'<<host>>';
FLUSH PRIVILEGES;
EOF
echo <<worst>> > worst.txt"""
mission(6, 'MySQL: GRANT最小権限・my.cnfチューニング・スロークエリログ',
        'MySQL/MariaDBの運用設定を整えます。my.cnfのチューニング項目を読み書きし、スロークエリログ（mysqldumpslow などで集計する元データ）を有効化、アプリ用ユーザーへは GRANT で必要最小限の権限だけ与えます。',
        ['my.cnfを編集', 'grants.sqlを書く', 'スロークエリの記録から最悪クエリの値をworst.txtへ'], s6, c6, SOL6,
        ["echo 'GRANT ALL PRIVILEGES ON *.* TO \"app\"@\"%\";' > grants.sql", "sed -i 's/slow_query_log=0/slow_query_log=1/' my.cnf"],
        'innodb_buffer_pool_size は専用DBサーバーならRAMの50〜70%が目安です。slow_query_log=1 と long_query_time でしきい値を超えたクエリを記録し、mysqldumpslow -s t や Rows_examined の大きさで索引不足を探します。GRANT は ON db.* で対象を絞り、権限も必要最小限にします。',
        'my.cnfは[mysqld]セクションの項目、権限は ON と TO の範囲を意識します。', 'slow.logは Query_time の最大の行に付いている Rows_examined を読みます。')


# ------------------------------------------------------------ 7 pg_dump / pg_restore / psql
def s7(ctx):
    d = dict(db='sales' + secrets.token_hex(2), new='restore' + secrets.token_hex(2), tbl='orders_' + secrets.token_hex(2), out='db-' + secrets.token_hex(2) + '.dump')
    ctx.data.update(d)
    ctx.write('requirements.txt', f'PostgreSQLの {d["db"]} をカスタム形式（-Fc）で {d["out"]} にpg_dumpする → 新DB {d["new"]} へテーブル {d["tbl"]} だけpg_restoreする（-d, -t）→ psqlで {d["new"]} の {d["tbl"]} の件数を SELECT count(*) で確認する。3行を cmds.sh に書く。\n')


def c7(ctx):
    d = ctx.data
    cmds, _ = parse(ctx, 'cmds.sh')
    t = find(ctx, cmds, 'pg_dump')
    ctx.require('-Fc' in t or optv(t, '-F', '--format') in ('c', 'custom'), 'pg_dump はカスタム形式（-Fc）で、pg_restoreで選択復元できるようにします。')
    ctx.require(optv(t, '-f', '--file') == d['out'] and d['db'] in t, 'pg_dump の -f 出力先と対象DBが違います。')
    t = find(ctx, cmds, 'pg_restore')
    ctx.require(optv(t, '-d', '--dbname') == d['new'], 'pg_restore -d は復元先の新DBです。')
    ctx.require(optv(t, '-t', '--table') == d['tbl'], 'pg_restore -t で対象テーブルだけ復元します。')
    ctx.require(d['out'] in t, 'pg_restore にダンプファイルを渡します。')
    t = find(ctx, cmds, 'psql')
    ctx.require(optv(t, '-d', '--dbname') == d['new'] or d['new'] in t, 'psql は復元先DBへ接続します。')
    q = optv(t, '-c', '--command') or ''
    ctx.require(re.fullmatch(r'\s*select\s+count\(\*\)\s+from\s+' + d['tbl'] + r'\s*;?\s*', q, re.I), '-c "SELECT count(*) FROM テーブル;" で確認します。')


SOL7 = """cat > cmds.sh <<'EOF'
pg_dump -Fc -f <<out>> <<db>>
pg_restore -d <<new>> -t <<tbl>> <<out>>
psql -d <<new>> -c "SELECT count(*) FROM <<tbl>>;"
EOF"""
mission(7, 'PostgreSQL: pg_dump/pg_restore で1テーブルを戻し psql で確認',
        '誤ってテーブルを消した想定で、PostgreSQLのバックアップから1テーブルだけ別DBへ復元します。pg_dumpのカスタム形式、pg_restoreの選択復元、psqlでの件数確認を書いてください。',
        ['pg_dump -Fc', 'pg_restore -t', 'psql -c で確認'], s7, c7, SOL7,
        ["echo 'pg_dump <<db>> > <<out>>' > cmds.sh", "printf 'pg_dump -Fc -f <<out>> <<db>>\\npg_restore -d <<new>> <<out>>\\npsql <<new>>\\n' > cmds.sh"],
        'pg_dump -Fc（カスタム形式）は圧縮され、pg_restore で -t（テーブル）や -l（一覧）の選択復元ができます。プレーンSQLはpsqlで流し込みます。psqlは -d でDB、-c で1つのSQLを実行できます。復元後に件数を確認するのは「戻せたか」の最低限の検証です。',
        '形式は-Fc、復元は-d（先）と-t（対象）です。', 'pg_dump -Fc -f ファイル DB、pg_restore -d 新DB -t テーブル ファイル、psql -d 新DB -c "SQL"。')


# ------------------------------------------------------------ 8 pg_hba / VACUUM / WAL
def s8(ctx):
    d = dict(db='crm' + secrets.token_hex(2), user='app' + secrets.token_hex(2), cidr='10.%d.%d.0/24' % (1 + R(200), R(250)), arch='/archive/' + secrets.token_hex(3))
    tabs = []
    for i in range(5):
        live = 10000 + R(90000)
        dead = int(live * (0.05 if R(2) else 0.4)) + R(100)
        tabs.append(('t_' + secrets.token_hex(2), live, dead))
    d['bloated'] = sorted(n for n, l, dd in tabs if dd / (l + dd) > 0.2)
    ctx.data.update(d)
    ctx.write('pg_hba.conf', 'local   all   postgres                 peer\nhost    all   all    127.0.0.1/32     scram-sha-256\nhost    all   all    0.0.0.0/0        trust\n')
    ctx.write('postgresql.conf', "wal_level = minimal\narchive_mode = off\n#archive_command = ''\nmax_wal_size = 1GB\n")
    put(ctx, 'pgstat.txt', 'relname n_live_tup n_dead_tup\n' + ''.join(f'{a} {b} {c}\n' for a, b, c in tabs))
    ctx.write('requirements.txt', f'1) pg_hba.conf: 全員trustの行を削除し、{d["db"]} へ {d["user"]} が {d["cidr"]} からだけscram-sha-256で接続できる行を足す。localのpostgres peer行は残す。\n'
              f'2) postgresql.conf: WALをPITR向けにする（wal_level=replica, archive_mode=on, archive_command で {d["arch"]}/%f へ %p をcpする）。\n'
              '3) maintenance.sql: pgstat.txtで不要領域（n_dead_tup/(live+dead)）が20%超のテーブルだけを VACUUM (ANALYZE) する（VACUUM FULLは使わない）。\n')


def c8(ctx):
    need_ro(ctx)
    d = ctx.data
    hba = [x.split() for x in ctx.need_file('pg_hba.conf').splitlines() if x.strip() and not x.strip().startswith('#')]
    ctx.require(['local', 'all', 'postgres', 'peer'] in hba, 'local postgres peer の行は残します。')
    ctx.require(not any('trust' in x for x in hba) and not any('0.0.0.0/0' in x for x in hba), '全員に開いたtrustの行は削除します。')
    ctx.require(any(x[:2] in (['host', d['db']], ['hostssl', d['db']]) and x[2:] == [d['user'], d['cidr'], 'scram-sha-256'] for x in hba), f'host {d["db"]} {d["user"]} {d["cidr"]} scram-sha-256 の行が必要です。')
    c = kv(ctx.need_file('postgresql.conf'))
    ctx.require(c.get('wal_level') in ('replica', 'logical'), 'wal_level を replica にします。')
    ctx.require(c.get('archive_mode') == 'on', 'archive_mode = on')
    ac = c.get('archive_command', '')
    ctx.require('%p' in ac and '%f' in ac and d['arch'] in ac, "archive_command に %p, %f とアーカイブ先を使います。")
    sql = ctx.need_file('maintenance.sql')
    ctx.require('FULL' not in sql.upper(), 'VACUUM FULL は排他ロックを取るので使いません。')
    got = sorted(re.findall(r'vacuum\s*(?:\(\s*analyze\s*\)|analyze)\s+(\w+)', sql, re.I))
    ctx.require(got == d['bloated'], '不要領域が20%を超えたテーブルだけが対象です。')


SOL8 = """cat > pg_hba.conf <<'EOF'
local   all   postgres                 peer
host    all   all    127.0.0.1/32     scram-sha-256
host    <<db>>   <<user>>   <<cidr>>   scram-sha-256
EOF
cat > postgresql.conf <<'EOF'
wal_level = replica
archive_mode = on
archive_command = 'cp %p <<arch>>/%f'
max_wal_size = 1GB
EOF
awk 'NR>1 && $3/($2+$3)>0.2 {print "VACUUM (ANALYZE) " $1 ";"}' pgstat.txt > maintenance.sql"""
mission(8, 'PostgreSQL: pg_hba.conf・VACUUM・WALアーカイブ',
        'PostgreSQLの設定点検です。pg_hba.conf の認証設定を締め、WALアーカイブでPITRできるようpostgresql.confを直し、dead tuple の多いテーブルだけ VACUUM を計画してください。',
        ['pg_hba.confを締める', 'WAL設定を直す', 'VACUUM対象をmaintenance.sqlへ'], s8, c8, SOL8,
        ["echo 'host all all 0.0.0.0/0 md5' >> pg_hba.conf", "sed -i 's/archive_mode = off/archive_mode = on/' postgresql.conf\necho 'VACUUM FULL;' > maintenance.sql"],
        'pg_hba.conf は上から順に最初に一致した行が使われ、type/database/user/address/methodの順に書きます。trustは無認証なので使いません。VACUUM は更新・削除で残った不要タプルを回収し、ANALYZE で統計を更新します（FULLは排他ロック）。WALは更新ログで、archive_mode と archive_command でアーカイブするとベースバックアップ+WALによる時点復旧ができます。',
        'pg_hba.confは範囲を狭く、VACUUMは割合で選びます。', "awk で pgstat.txt の割合を計算して SQL 行を作れます。")


# ------------------------------------------------------------ 9 redis / memcached
def s9(ctx):
    d = dict(pw='rp-' + secrets.token_hex(5), mm=64 * (1 + R(8)), mc=1024 * (1 + R(4)), mem=64 * (1 + R(8)))
    ctx.data.update(d)
    ctx.write('redis.conf', 'bind 0.0.0.0\nsave 3600 1\nappendonly no\nappendfsync always\n')
    ctx.write('memcached.conf', 'OPTIONS="-m 64 -l 0.0.0.0 -c 1024"\n')
    ctx.write('requirements.txt', f'redis.conf: 127.0.0.1だけで待ち受け、RDB（save 行）は残したままAOFを有効（appendonly yes, appendfsync everysec）、requirepass {d["pw"]}、maxmemory {d["mm"]}mb で上限に達したら allkeys-lru で追い出す。\n'
              f'memcached.conf: OPTIONS を メモリ{d["mem"]}MB(-m)、127.0.0.1のみ(-l)、UDP無効(-U 0)にする。memcachedは永続化しないのでデータ保全には使えない。cmd.txt に非同期でRDBを保存する redis-cli の1行（-a でパスワード、BGSAVE）を書く。\n')


def c9(ctx):
    d = ctx.data
    c = {}
    saves = []
    for ln in ctx.need_file('redis.conf').splitlines():
        p = ln.split(None, 1)
        if len(p) == 2 and not ln.startswith('#'):
            if p[0] == 'save':
                saves.append(p[1])
            c[p[0]] = p[1].strip()
    ctx.require(c.get('bind') == '127.0.0.1', 'bind は 127.0.0.1 だけにします。')
    ctx.require(saves, 'RDBのsave行は残します。')
    ctx.require(c.get('appendonly') == 'yes' and c.get('appendfsync') == 'everysec', 'appendonly yes / appendfsync everysec')
    ctx.require(c.get('requirepass') == d['pw'], 'requirepass を設定します。')
    ctx.require(mb(c.get('maxmemory', '').replace('mb', 'M')) == d['mm'], f'maxmemory {d["mm"]}mb')
    ctx.require(c.get('maxmemory-policy') == 'allkeys-lru', 'maxmemory-policy は allkeys-lru（キャッシュ用途）。')
    m = re.fullmatch(r'OPTIONS="(.*)"', ctx.need_file('memcached.conf').strip())
    ctx.require(m, 'OPTIONS="..." の形式を保ちます。')
    o = m.group(1).split()
    ctx.require(optv(o, '-m') == str(d['mem']) and optv(o, '-l') == '127.0.0.1' and optv(o, '-U') == '0', '-m, -l 127.0.0.1, -U 0 を指定します。')
    cmds, _ = parse(ctx, 'cmd.txt')
    t = find(ctx, cmds, 'redis-cli')
    ctx.require(optv(t, '-a') == d['pw'] and 'BGSAVE' in [x.upper() for x in t], 'redis-cli -a パスワード BGSAVE（SAVEはブロッキングなので避けます）。')


SOL9 = """cat > redis.conf <<'EOF'
bind 127.0.0.1
save 3600 1
appendonly yes
appendfsync everysec
requirepass <<pw>>
maxmemory <<mm>>mb
maxmemory-policy allkeys-lru
EOF
echo 'OPTIONS="-m <<mem>> -l 127.0.0.1 -c 1024 -U 0"' > memcached.conf
echo 'redis-cli -a <<pw>> BGSAVE' > cmd.txt"""
mission(9, 'Redis の永続化と memcached の運用設定',
        'キャッシュ基盤の設定を見直します。Redisは RDB と AOF の両方で永続化し、公開範囲・認証・メモリ上限を整えます。memcachedは永続化できないので、メモリと待ち受けだけを安全に設定します。',
        ['redis.confを直す', 'memcached.confを直す', 'redis-cli BGSAVEの行を書く'], s9, c9, SOL9,
        ["echo 'appendonly yes' >> redis.conf", "echo 'redis-cli SAVE' > cmd.txt"],
        'Redisの RDB は定期スナップショット（BGSAVEは子プロセスで非同期）、AOF は書き込み操作のログで appendfsync everysec なら最大約1秒の損失に抑えられます。maxmemory-policy で上限時の追い出し方を決めます。memcachedはメモリのみで再起動すると消え、-m・-l・-c・-U で運用を絞ります。',
        'Redisとmemcachedはどちらもbindとメモリがポイントです。', 'redis.conf は「キー 値」形式、memcachedは OPTIONS のオプション列です。')


# ------------------------------------------------------------ 10 multipath / iSCSI
def s10(ctx):
    bad = 'sd' + chr(ord('c') + R(10))
    good = ['sd' + chr(ord('x') + i) for i in range(3)]
    wwid = '3600' + secrets.token_hex(14)
    wb = '3600' + secrets.token_hex(14)
    d = dict(bad=bad, wb=wb, ip='192.0.2.%d' % (10 + R(200)), iqn='iqn.2026-11.example.lab:' + secrets.token_hex(3), user='ini' + secrets.token_hex(2), pw='ch-' + secrets.token_hex(6),
             rt=5 + R(20))
    ctx.data.update(d)
    mp = f'''mpatha ({wwid}) dm-0 EXAMPLE,VOL
size=100G features='1 queue_if_no_path' hwhandler='1 alua' wp=rw
|-+- policy='service-time 0' prio=50 status=active
| `- 3:0:0:1 {good[0]} 8:16 active ready running
`-+- policy='service-time 0' prio=10 status=enabled
  `- 4:0:0:1 {good[1]} 8:32 active ready running
mpathb ({wb}) dm-1 EXAMPLE,VOL
size=200G features='1 queue_if_no_path' hwhandler='1 alua' wp=rw
|-+- policy='service-time 0' prio=50 status=active
| `- 3:0:0:2 {good[2]} 8:48 active ready running
`-+- policy='service-time 0' prio=0 status=enabled
  `- 4:0:0:2 {bad} 8:64 failed faulty running
'''
    put(ctx, 'multipath.txt', '# multipath -ll (採取済み)\n' + mp)
    ctx.write('iscsid.conf', 'node.startup = manual\nnode.session.auth.authmethod = None\nnode.session.timeo.replacement_timeout = 120\n')
    ctx.write('requirements.txt', f'1) multipath.txt（multipath -ll の出力）から障害のある（failed faulty）パスを探し、fault.json に {{"map": マップ名, "wwid": WWID, "path": デバイス名}} を書く。\n'
              f'2) iscsid.conf（initiator設定）: 起動時に自動ログイン（node.startup=automatic）、CHAP認証（authmethod=CHAP, username={d["user"]}, password={d["pw"]}）、replacement_timeout を {d["rt"]} にする。\n'
              f'3) iscsi.sh: iscsiadm でターゲット {d["ip"]}:3260 をsendtargets探索し、{d["iqn"]} へログインする2行。\n')


def c10(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'fault.json')
    ctx.require(j == {'map': 'mpathb', 'wwid': d['wb'], 'path': d['bad']}, 'failed faulty の行を持つマップ・そのWWID・デバイス名を書きます。')
    c = kv(ctx.need_file('iscsid.conf'))
    ctx.require(c.get('node.startup') == 'automatic', 'node.startup = automatic')
    ctx.require(c.get('node.session.auth.authmethod') == 'CHAP' and c.get('node.session.auth.username') == d['user'] and c.get('node.session.auth.password') == d['pw'], 'CHAPの認証設定が違います。')
    ctx.require(c.get('node.session.timeo.replacement_timeout') == str(d['rt']), 'replacement_timeout が違います。')
    cmds, _ = parse(ctx, 'iscsi.sh')
    t = find(ctx, cmds, 'iscsiadm')
    ctx.require(optv(t, '-m', '--mode') == 'discovery' and optv(t, '-t', '--type') == 'sendtargets' and optv(t, '-p', '--portal') in (d['ip'], d['ip'] + ':3260'), '探索は -m discovery -t sendtargets -p IP:3260')
    t = [c for c in cmds if c and c[0] == 'iscsiadm' and optv(c, '-m', '--mode') == 'node']
    ctx.require(t and optv(t[0], '-T', '--targetname') == d['iqn'] and ('-l' in t[0] or '--login' in t[0]), '-m node -T IQN -p IP --login でログインします。')


SOL10 = """grep -B3 'failed faulty' multipath.txt   # mpathb / sdX を確認
echo '{"map": "mpathb", "wwid": "<<wb>>", "path": "<<bad>>"}' > fault.json
cat > iscsid.conf <<'EOF'
node.startup = automatic
node.session.auth.authmethod = CHAP
node.session.auth.username = <<user>>
node.session.auth.password = <<pw>>
node.session.timeo.replacement_timeout = <<rt>>
EOF
cat > iscsi.sh <<'EOF'
iscsiadm -m discovery -t sendtargets -p <<ip>>:3260
iscsiadm -m node -T <<iqn>> -p <<ip>>:3260 --login
EOF"""
mission(10, 'multipath -ll の障害パスとiSCSI initiator設定',
        'SANストレージの片系障害の疑いです。multipath -ll の出力から障害パスを見つけ、iSCSI initiatorの設定（iscsid.conf）と iscsiadm のログイン手順を整えてください。',
        ['multipathの採取記録から障害パスをfault.jsonへ', 'iscsid.confを編集', 'iscsiadmの2行を書く'], s10, c10, SOL10,
        ["echo '{\"map\": \"mpatha\"}' > fault.json", "echo 'iscsiadm -m node --login' > iscsi.sh"],
        'multipath -ll はマップ(mpathX)ごとにパスグループと各パスの状態を示し、「failed faulty」が障害パスです（もう片系の active ready で通信は継続）。iSCSIは iscsiadm -m discovery -t sendtargets で探索し、-m node -T IQN --login でログインします。iscsid.conf の node.startup=automatic で起動時に自動接続し、replacement_timeout は経路障害時にI/Oを諦める時間です。',
        '出力の状態語（active ready / failed faulty）を探します。', 'grep -B で障害パスの親マップを確認し、iscsiadm の -m を使い分けます。')


# ------------------------------------------------------------ 11 autofs / NFSv4 / fstab
def s11(ctx):
    d = dict(srv='nfs' + secrets.token_hex(2) + '.lab', key='proj' + secrets.token_hex(2), to=30 + 10 * R(10), exp='/export/' + secrets.token_hex(3), fx='/export/bk' + secrets.token_hex(2), fm='/mnt/bk' + secrets.token_hex(2))
    ctx.data.update(d)
    ctx.write('auto.master', '/misc /etc/auto.misc\n+dir:/etc/auto.master.d\n')
    ctx.write('fstab', 'UUID=1111-2222 / ext4 defaults 0 1\n')
    ctx.write('requirements.txt', f'1) auto.master に、/mnt/nfs 配下を auto.nfs で管理しアイドル{d["to"]}秒で自動アンマウントする行を追加（既存行は残す）。\n'
              f'2) auto.nfs を新規作成: キー {d["key"]} を NFSv4（-fstype=nfs4, rw, soft）で {d["srv"]}:{d["exp"]} にマップ。\n'
              f'3) fstab に常時マウントの1行を追加: {d["srv"]}:{d["fx"]} を {d["fm"]} へ nfs4、オプションに _netdev（ネットワーク起動後に）を含め、dump/passは0 0。\n')


def c11(ctx):
    d = ctx.data
    ms = [x.split() for x in ctx.need_file('auto.master').splitlines() if x.strip()]
    ctx.require(['/misc', '/etc/auto.misc'] in ms and ['+dir:/etc/auto.master.d'] in ms, 'auto.masterの既存行は残します。')
    ctx.require(any(x[0] == '/mnt/nfs' and x[1].endswith('auto.nfs') and any(o in ('--timeout=%d' % d['to'], '-t=%d' % d['to'], '--timeout %d' % d['to']) for o in x[2:]) or (x[0] == '/mnt/nfs' and x[1].endswith('auto.nfs') and ('--timeout=%d' % d['to']) in x[2:]) for x in ms), '/mnt/nfs auto.nfs --timeout=秒 の行が必要です。')
    an = [x.split() for x in ctx.need_file('auto.nfs').splitlines() if x.strip() and not x.startswith('#')]
    ctx.require(len(an) == 1 and an[0][0] == d['key'] and an[0][2] == f'{d["srv"]}:{d["exp"]}', 'auto.nfs は「キー -オプション サーバー:パス」の1行です。')
    o = an[0][1]
    ctx.require(o.startswith('-') and 'fstype=nfs4' in o.split(',') or 'fstype=nfs4' in o, '-fstype=nfs4 を指定します。')
    ctx.require({'rw', 'soft'} <= set(o.lstrip('-').split(',')), 'rw と soft を含めます。')
    fs = [x.split() for x in ctx.need_file('fstab').splitlines() if x.strip()]
    ctx.require(['UUID=1111-2222', '/', 'ext4', 'defaults', '0', '1'] in fs, '既存のfstab行は残します。')
    ctx.require(any(len(x) == 6 and x[:3] == [f'{d["srv"]}:{d["fx"]}', d['fm'], 'nfs4'] and '_netdev' in x[3].split(',') and x[4:] == ['0', '0'] for x in fs), 'fstabの行（6フィールド、nfs4、_netdev、0 0）が違います。')


SOL11 = """echo '/mnt/nfs /etc/auto.nfs --timeout=<<to>>' >> auto.master
echo '<<key>> -fstype=nfs4,rw,soft <<srv>>:<<exp>>' > auto.nfs
echo '<<srv>>:<<fx>> <<fm>> nfs4 defaults,_netdev 0 0' >> fstab"""
mission(11, 'autofs(auto.master/auto.nfs) と NFSv4 の fstab',
        'ファイルサーバーの共有を、普段はautofsでアクセス時だけマウントし、バックアップ用の1つはfstabで常時マウントします。auto.master / auto.nfs / fstab を編集してください。',
        ['auto.masterに行を追加', 'auto.nfsを作る', 'fstabにnfs4行を追加'], s11, c11, SOL11,
        ["echo '/mnt/nfs auto.nfs' >> auto.master", "echo '<<srv>>:<<fx>> <<fm>> nfs defaults 0 0' >> fstab"],
        'autofs は auto.master の「マウントポイント マップ オプション」行で管理し、マップ（auto.nfs）の「キー -オプション 場所」で、アクセス時に自動マウント、--timeout 秒の無通信でアンマウントします。NFS v4 のfstab行は type を nfs4（または nfs と vers=4.x）にし、_netdev でネットワーク起動後に回します。',
        'auto.masterは親の設定、auto.nfsは各キーの設定です。', 'fstabは6フィールド: 場所 マウント先 種別 オプション dump pass。')


# ------------------------------------------------------------ 12 btrfs / ZFS
def s12(ctx):
    names = ['auto-2026-10-%02d' % (1 + i * 5) for i in range(5)]
    sizes = [('4.2G', 4.2e9), ('812M', 8.12e8), ('15.5G', 1.55e10), ('96K', 9.6e4), ('2.1G', 2.1e9)]
    R2 = secrets.SystemRandom()
    R2.shuffle(sizes)
    big = names[max(range(5), key=lambda i: sizes[i][1])]
    ds = 'tank/' + secrets.token_hex(2)
    tag = 'before-' + secrets.token_hex(2)
    d = dict(ds=ds, big=big, tag=tag, bdest='snapshots/data-' + secrets.token_hex(2))
    ctx.data.update(d)
    ls = 'NAME USED AVAIL REFER MOUNTPOINT\ntank 1.20T 2.40T 96K /tank\n' + f'{ds} 300G 2.40T 280G /{ds}\n' + ''.join(f'{ds}@{n} {s[0]} - 280G -\n' for n, s in zip(names, sizes))
    put(ctx, 'zfs_list.txt', '$ zfs list -t all -r ' + ds + '\n' + ls)
    ctx.write('requirements.txt', f'btrfsとZFSのスナップショット運用。snap.sh に3行: 1) btrfs subvolume snapshot で読み取り専用(-r)のスナップショット {d["bdest"]} を subvol-data から作る。2) zfs snapshot で {ds}@{tag} を作る。'
              f'3) zfs_list.txt（zfs list の出力）で使用量(USED)が最大のスナップショットを zfs destroy で削除する。\n')


def c12(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, _ = parse(ctx, 'snap.sh')
    t = find(ctx, cmds, 'btrfs', 'snapshot')
    ctx.require(t[1:3] == ['subvolume', 'snapshot'] and '-r' in t, 'btrfs subvolume snapshot -r（読み取り専用）で作ります。')
    ctx.require(t[-2:] == ['subvol-data', d['bdest']], 'btrfs subvolume snapshot -r 元 先 の順です。')
    t = find(ctx, cmds, 'zfs', 'snapshot')
    ctx.require(t == ['zfs', 'snapshot', f'{d["ds"]}@{d["tag"]}'], 'zfs snapshot データセット@名前')
    t = find(ctx, cmds, 'zfs', 'destroy')
    ctx.require(t == ['zfs', 'destroy', f'{d["ds"]}@{d["big"]}'], 'USEDが最大のスナップショットを destroy します（単位 K/M/G に注意）。')


SOL12 = """cat > snap.sh <<'EOF'
btrfs subvolume snapshot -r subvol-data <<bdest>>
zfs snapshot <<ds>>@<<tag>>
zfs destroy <<ds>>@<<big>>
EOF"""
mission(12, 'btrfs・ZFS のスナップショット作成と zfs list の読解',
        'ストレージのスナップショット運用です。btrfsは subvolume snapshot、ZFSは zfs snapshot で作り、zfs list の出力（USEDの単位に注意）から容量を食っているスナップショットを選んで整理します。',
        ['btrfsとzfsのsnapshot行', 'USED最大のスナップショットをdestroy'], s12, c12, SOL12,
        ["echo 'btrfs subvolume snapshot subvol-data <<bdest>>' > snap.sh", "printf 'btrfs subvolume snapshot -r subvol-data <<bdest>>\\nzfs snapshot <<ds>>@<<tag>>\\nzfs destroy <<ds>>@nonexistent-snap\\n' > snap.sh"],
        'btrfs subvolume snapshot -r は読み取り専用のスナップショットで、コピーオンライトにより作成は一瞬です。zfs list -t snapshot の USED は「そのスナップショットだけが持つ領域」で、K < M < G の単位を揃えて比較します。zfs destroy でその領域が戻ります。スナップショットは同一ストレージ内のため別媒体のバックアップの代わりにはなりません。',
        '値は単位つきの文字列です。', 'zfs list の USED の列を、K/M/G を揃えて比べます。')


# ------------------------------------------------------------ 13 logrotate
def s13(ctx):
    d = dict(app='/var/log/app-' + secrets.token_hex(2) + '/app.log', web='/var/log/web-' + secrets.token_hex(2) + '/*.log', ra=4 + R(8), rw=7 + R(30), svc='nginx' + secrets.token_hex(1))
    ctx.data.update(d)
    ctx.write('logrotate.conf', '# 作成してください\n')
    ctx.write('requirements.txt', f'logrotate.conf に2ブロックを書く。\n1) {d["app"]}: 週次, {d["ra"]}世代, compress+delaycompress, missingok, notifempty。アプリはログを開きっぱなしで再読込できないので copytruncate。\n'
              f'2) {d["web"]}: 日次, {d["rw"]}世代, compress, missingok, notifempty, create 0640 www-data adm, sharedscripts。ローテート後に postrotate〜endscript で systemctl reload {d["svc"]} を実行（失敗しても全体は成功: || true）。\n')


def c13(ctx):
    d = ctx.data
    t = ctx.need_file('logrotate.conf')
    bl = {m.group(1): m.group(2) for m in re.finditer(r'(\S+)\s*\{(.*?)\n\}', t, re.S)}
    ctx.require(d['app'] in bl and d['web'] in bl, '2つのブロック「パス {  }」が必要です。')
    a = bl[d['app']]
    al = {x.strip() for x in a.splitlines() if x.strip()}
    ctx.require({'weekly', f'rotate {d["ra"]}', 'compress', 'delaycompress', 'missingok', 'notifempty', 'copytruncate'} <= al, 'appブロックの指令が足りません（weekly, rotate N, compress, delaycompress, missingok, notifempty, copytruncate）。')
    b = bl[d['web']]
    bs = {x.strip() for x in b.splitlines() if x.strip()}
    ctx.require({'daily', f'rotate {d["rw"]}', 'compress', 'missingok', 'notifempty', 'create 0640 www-data adm', 'sharedscripts', 'postrotate', 'endscript'} <= bs, 'webブロックの指令が足りません。')
    m = re.search(r'postrotate\s*\n(.*?)\n\s*endscript', b, re.S)
    ctx.require(m and re.search(r'systemctl reload ' + d['svc'] + r'.*\|\|\s*true', m.group(1)), 'postrotate内で systemctl reload サービス || true を実行します。')


SOL13 = """cat > logrotate.conf <<'EOF'
<<app>> {
    weekly
    rotate <<ra>>
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
<<web>> {
    daily
    rotate <<rw>>
    compress
    missingok
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        systemctl reload <<svc>> > /dev/null 2>&1 || true
    endscript
}
EOF"""
mission(13, 'logrotate: copytruncate と postrotate の設定',
        'ログが肥大化しています。logrotateの設定を書きます。ログを開きっぱなしにするアプリには copytruncate、再読込に対応するサービスには postrotate で reload を使います。',
        ['logrotate.confに2ブロックを書く'], s13, c13, SOL13,
        ["echo '/var/log/*.log { daily }' > logrotate.conf", "printf '<<app>> {\\n  weekly\\n}\\n<<web>> {\\n  daily\\n}\\n' > logrotate.conf"],
        'logrotate は「パス { 指令 }」の形です。copytruncate はログをコピーしてから元を空にするため、書き込み中のプロセスの再起動が不要ですが、コピーと切り詰めの間の少量のログが失われます。postrotate〜endscript はローテート後に実行するシェルで、sharedscripts を付けるとワイルドカード一致の全ファイルで1回だけ実行します。logrotate -d で設定を試験できます。',
        'ブロックごとに必要な指令を整理します。', '2つのブロックを heredoc で一度に書けば確実です。')


# ------------------------------------------------------------ 14 journald
def s14(ctx):
    d = dict(sm=['200M', '500M', '1G'][R(3)], kf=['1G', '2G'][R(2)], ret=['2week', '1month', '3month'][R(3)], unit='app-' + secrets.token_hex(2) + '.service', vac=['100M', '300M'][R(2)])
    ctx.data.update(d)
    ctx.write('journald.conf', '[Journal]\n#Storage=auto\n#SystemMaxUse=\n#SystemKeepFree=\n#MaxRetentionSec=\n#Compress=yes\n')
    ctx.write('requirements.txt', f'journald.conf: 再起動後もログを残す（Storage=persistent）、ログ全体の上限 SystemMaxUse={d["sm"]}、ディスクの空きを SystemKeepFree={d["kf"]} 確保、MaxRetentionSec={d["ret"]}。\n'
              f'cmds.sh: 1) {d["unit"]} の今日の warning以上 を journalctl で絞る（-u, -p warning, --since today）。2) ジャーナルのディスク使用量を表示。3) 古いログを {d["vac"]} まで削除（--vacuum-size）。\n')


def c14(ctx):
    d = ctx.data
    t = ctx.need_file('journald.conf')
    ctx.require(t.lstrip().startswith('[Journal]'), '[Journal] セクションを保ちます。')
    c = kv(t)
    ctx.require(c.get('Storage') == 'persistent' and c.get('SystemMaxUse') == d['sm'] and c.get('SystemKeepFree') == d['kf'] and c.get('MaxRetentionSec') == d['ret'], 'journald.conf の4項目（コメント解除）が違います。')
    cmds, _ = parse(ctx, 'cmds.sh')
    ts = [x for x in cmds if x[0] == 'journalctl']
    ctx.require(any(optv(x, '-u', '--unit') == d['unit'] and optv(x, '-p', '--priority') == 'warning' and optv(x, '--since') == 'today' for x in ts), '絞り込み: journalctl -u UNIT -p warning --since today')
    ctx.require(any('--disk-usage' in x for x in ts), 'journalctl --disk-usage')
    ctx.require(any(optv(x, '--vacuum-size') == d['vac'] for x in ts), 'journalctl --vacuum-size=' + d['vac'])


SOL14 = """cat > journald.conf <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=<<sm>>
SystemKeepFree=<<kf>>
MaxRetentionSec=<<ret>>
EOF
cat > cmds.sh <<'EOF'
journalctl -u <<unit>> -p warning --since today
journalctl --disk-usage
journalctl --vacuum-size=<<vac>>
EOF"""
mission(14, 'journald の永続化・容量制限と journalctl の絞り込み',
        'journaldのログが再起動で消え、逆にディスクを圧迫しています。journald.conf で永続化と容量制限を設定し、journalctl での絞り込み・容量確認・整理コマンドを用意してください。',
        ['journald.confを編集', 'journalctlの3行をcmds.shへ'], s14, c14, SOL14,
        ["echo 'Storage=persistent' > journald.conf", "echo 'journalctl -u x' > cmds.sh"],
        'journald.conf の Storage=persistent は /var/log/journal に保存して再起動後も残します（autoだとこのディレクトリが無い時は揮発）。SystemMaxUse・SystemKeepFree・MaxRetentionSec で容量と保存期間を制限します。journalctl は -u（ユニット）、-p（優先度）、--since/--until（期間）で絞り、--disk-usage で使用量、--vacuum-size で削減できます。',
        '設定ファイルは[Journal]セクション、操作はjournalctlのオプションです。', 'コメントの # を外して値を入れ、journalctl のオプションを並べます。')


# ------------------------------------------------------------ 15 at / batch / anacron
def s15(ctx):
    hh, mm = 1 + R(5), 5 * R(12)
    d = dict(t=f'{hh:02d}:{mm:02d}', aid='weekly-' + secrets.token_hex(2), delay=5 + R(40), old=1000 + R(500))
    ctx.data.update(d)
    jobs = [(d['old'] + 1, 'backup.sh'), (d['old'], 'oldtask.sh'), (d['old'] + 2, 'report.sh')]
    put(ctx, 'atq.txt', '# atq の出力と各ジョブの中身\n' + ''.join(f'{n}\tFri Nov 21 10:00:00 2026 a trainee  -> {c}\n' for n, c in jobs))
    ctx.write('anacrontab', 'SHELL=/bin/sh\n1 5 cron.daily nice run-parts /etc/cron.daily\n')
    ctx.write('requirements.txt', f'at.sh に3行: 1) ./job.sh を今夜 {d["t"]} に一度だけ実行（echo ... | at 時刻）。2) ./heavy.sh をシステム負荷が下がったら実行（batch）。3) atq.txt の oldtask.sh を実行するジョブを atrm で取り消す。\n'
              f'anacrontab に、ノートPCのように常時稼働でなくても週1回（期間 7日）・遅延{d["delay"]}分・識別名 {d["aid"]} で ./rsync-backup.sh を実行する行を追加（既存行は残す）。\n')


def c15(ctx):
    need_ro(ctx)
    d = ctx.data
    cmds, _ = parse(ctx, 'at.sh')
    ctx.require(any(x[:1] == ['echo'] and './job.sh' in ' '.join(x) and '|' in x and 'at' in x[x.index('|') + 1:x.index('|') + 2] and d['t'] in x for x in cmds), "echo './job.sh' | at 時刻 の形で一度だけ実行します。")
    ctx.require(any(('|' in x and x[x.index('|') + 1:x.index('|') + 2] == ['batch'] and './heavy.sh' in ' '.join(x)) or x == ['batch'] for x in cmds), "echo './heavy.sh' | batch の形です。")
    ctx.require(any(x == ['atrm', str(d['old'])] for x in cmds), 'oldtask.sh のジョブ番号 ' + str(d['old']) + ' を atrm します。')
    ls = [x.split() for x in ctx.need_file('anacrontab').splitlines() if x.strip()]
    ctx.require(['SHELL=/bin/sh'] in ls and ['1', '5', 'cron.daily', 'nice', 'run-parts', '/etc/cron.daily'] in ls, '既存行は残します。')
    ctx.require(any(x[:4] == ['7', str(d['delay']), d['aid'], './rsync-backup.sh'] and len(x) == 4 for x in ls), 'anacrontab は「期間(日) 遅延(分) 識別名 コマンド」の4項目です。')


SOL15 = """cat > at.sh <<'EOF'
echo './job.sh' | at <<t>>
echo './heavy.sh' | batch
atrm <<old>>
EOF
echo '7 <<delay>> <<aid>> ./rsync-backup.sh' >> anacrontab"""
mission(15, 'at・batch・anacron で一回限りの実行と定期ジョブ',
        'cronでは足りないジョブを整理します。一度だけ実行したい作業は at、負荷が下がってから流す作業は batch、電源が落ちていた日の分も後から実行したい定期処理は anacron に任せます。',
        ['at.shに3行', 'anacrontabに1行追加'], s15, c15, SOL15,
        ["echo './job.sh' > at.sh", "echo '7 5 x ./rsync-backup.sh' >> anacrontab"],
        'at は標準入力のコマンドを指定時刻に一度だけ実行し、atq で一覧、atrm でジョブ番号を指定して取り消します。batch は負荷が閾値より下がると実行されます。anacron は電源断などで実行できなかった周期ジョブを、次の起動後にdelay分待って実行します（期間はcronより粗い日単位）。',
        '一度だけ→at、負荷待ち→batch、取りこぼし防止→anacron。', 'atrmの番号は atq.txt の行から取ります。')


# ------------------------------------------------------------ 16 disk watch script
def df_text(rows):
    return 'Filesystem Size Used Avail Use% Mounted\n' + ''.join(f'{a} {b} {c} {e} {p}% {m}\n' for a, b, c, e, p, m in rows)


def s16(ctx):
    th = 70 + R(20)
    mounts = ['/', '/var', '/home', '/data', '/backup', '/tmp']
    rows = [('/dev/sda%d' % (i + 1), '50G', '10G', '40G', 5 + R(95), m) for i, m in enumerate(mounts)]
    ctx.data.update(th=th)
    put(ctx, 'df.txt', df_text(rows))
    ctx.write('requirements.txt', f'ディスク容量監視スクリプト diskwatch.sh を書く。使い方: bash diskwatch.sh df出力ファイル 閾値%。\n'
              f'Use% が閾値以上のマウントごとに「ALERT マウント Use%」（例: ALERT /var 85%）を df の順に出力。1つもなければ OK だけ出力。警告があれば終了コード1、なければ0。df.txt で動作確認（閾値の例 {th}）。\n')


def run(ctx, f, th):
    p = subprocess.run(['bash', 'diskwatch.sh', f, str(th)], cwd=ctx.work, capture_output=True, text=True, timeout=10)
    return p.stdout.strip(), p.returncode


def expect(path_text, th):
    out, bad = [], 0
    for ln in path_text.splitlines()[1:]:
        f = ln.split()
        u = int(f[4].rstrip('%'))
        if u >= th:
            out.append(f'ALERT {f[5]} {u}%')
            bad += 1
    return ('\n'.join(out) if bad else 'OK'), (1 if bad else 0)


def c16(ctx):
    need_ro(ctx)
    ctx.need_file('diskwatch.sh')
    cases = [(ctx.need_file('df.txt'), ctx.data['th'])]
    for th, base in ((50, 20), (101, 0), (0, 0)):
        rows = [('/dev/x%d' % i, '9G', '1G', '8G', min(100, base + R(60)), '/m%d' % i) for i in range(5)]
        cases.append((df_text(rows), th))
    for i, (txt, th) in enumerate(cases):
        f = ctx.p(f'.case{i}.txt')
        f.write_text(txt)
        got = run(ctx, f.name, th)
        ctx.require(got == expect(txt, th), f'出力/終了コードが想定と違います（閾値{th}）: {got}')
        f.unlink()


SOL16 = """cat > diskwatch.sh <<'EOF'
#!/bin/bash
awk -v t="$2" 'NR>1 { u=$5; sub(/%/,"",u); if (u+0 >= t) { print "ALERT", $6, u "%"; n++ } } END { if (!n) print "OK"; exit (n>0) }' "$1"
EOF
bash diskwatch.sh df.txt <<th>>"""
mission(16, 'ディスク容量監視スクリプトを書く',
        '本番サーバーでディスクが満杯になる前に気付くため、df の出力を読んで閾値を超えたマウントを警告し、終了コードで監視ツールに伝えるスクリプトを書きます（cronやsystemd timerから呼べる形）。',
        ['diskwatch.shを書く', '閾値以上でALERTと終了コード1'], s16, c16, SOL16,
        ["echo 'df -h' > diskwatch.sh", "printf '#!/bin/bash\\necho OK\\n' > diskwatch.sh"],
        'df の Use% 列から % を除いて数値比較します。awk の END ブロックで exit に条件式を渡すとスクリプトの終了コードにできます。監視は「異常時に非ゼロで終了」「出力は機械で読める1行1件」にすると、cron や監視ツールと繋げやすくなります。',
        '2列目以降の列番号とヘッダ行の除外に注意します。', 'awk -v t="$2" で閾値を渡し、sub(/%/,"",u) で記号を除きます。')
