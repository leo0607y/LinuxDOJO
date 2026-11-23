"""Stage 18: プロセス管理・暗号・コンテナ基盤・構成管理。サンドボックス内の偽データと使える本物のツールだけを使う。"""
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
from pathlib import Path

from engine.runner import register

S = 18
NOTE = ("作業対象はこの課題のフォルダだけです。実OSのプロセス・サービス・コンテナ・設定は変更せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないツールは採取済みの出力と設定例から診断します。")


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


def one_line(ctx, name):
    ls = [x for x in ctx.need_file(name).splitlines() if x.strip()]
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0].strip()


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'18-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='実行する前に対象を確認し、結果を観測で検証します。本番では影響範囲の小さい指定と元データの保全を優先しましょう。')


# ---------------------------------------------------------------- 1 pkill
def s1(ctx):
    tag = 'sync-' + secrets.token_hex(3)
    ctx.data['tag'] = tag
    base = 2000 + secrets.randbelow(5000)
    p = [base + i * 7 for i in range(6)]
    rows = [(p[0], 'trainee', f'python3 /opt/app/worker.py --job {tag}'),
            (p[1], 'trainee', 'python3 /opt/app/worker.py --job report-' + secrets.token_hex(2)),
            (p[2], 'batch', f'python3 /opt/app/worker.py --job {tag}'),
            (p[3], 'trainee', f'python3 /opt/app/worker.py --job {tag} --retry'),
            (p[4], 'trainee', 'python3 -m http.server 9000'),
            (p[5], 'root', 'sshd: trainee [priv]')]
    put(ctx, 'processes.txt', '  PID USER     COMMAND\n' + ''.join(f'{a:5d} {b:<8} {c}\n' for a, b, c in rows))
    ctx.write('requirements.txt', f'trainee自身のworker.pyのうち、--job {tag} を含むものだけを止めたい。pids.txtに対象PIDを昇順1行ずつ、kill.txtに実行予定のpkillを1行書く（-uで所有者、-fで引数一致を指定。-9やkillallは使わない）。実際には終了させません。\n')


def c1(ctx):
    need_ro(ctx)
    tag = ctx.data['tag']
    want = []
    for ln in ctx.need_file('processes.txt').splitlines()[1:]:
        f = ln.split(None, 2)
        if f[1] == 'trainee' and ('--job ' + tag) in f[2]:
            want.append(f[0])
    got = ctx.need_file('pids.txt').split()
    ctx.require(got == sorted(want, key=int), '所有者がtraineeで、引数に指定の--jobを含むPIDだけを昇順で書きます。')
    t = toks(ctx, one_line(ctx, 'kill.txt'))
    ctx.require(t[0] == 'pkill', 'kill.txtはpkillコマンドです（killallは名前一致で誤爆しやすい）。')
    ctx.require(not any(x.startswith('-9') or x == '-KILL' or x == '-SIGKILL' for x in t), '最初はSIGTERMで依頼し、-9は避けます。')
    ctx.require('-u' in t and t[t.index('-u') + 1] == 'trainee', '-u trainee で所有者を絞ります。')
    ctx.require('-f' in t and any(tag in x for x in t), '-f と一意な--job識別子でコマンドライン全体を絞ります。')


SOL1 = """awk 'NR>1 && $2=="trainee" && /--job <<tag>>/ {print $1}' processes.txt | sort -n > pids.txt
echo "pkill -u trainee -f -- '--job <<tag>>'" > kill.txt"""
mission(1, 'pkill・killall・pgrepで誤爆せず止める',
        '同じworker.pyが他のユーザーや別ジョブでも動いています。killall python3 のような名前だけの指定は無関係な処理まで止めます。プロセスの採取記録のps出力を読み、まずpgrep相当で対象を絞り、pkillで止める手順を作ってください。',
        ['プロセスの採取記録から対象PIDだけをpids.txtへ', 'ユーザーと引数で絞ったpkillをkill.txtへ'], s1, c1, SOL1,
        ["awk 'NR>1 && /worker.py/ {print $1}' processes.txt | sort -n > pids.txt\necho 'killall python3' > kill.txt",
         "awk 'NR>1 && /--job <<tag>>/ {print $1}' processes.txt | sort -n > pids.txt\necho \"pkill -9 -f <<tag>>\" > kill.txt"],
        'pgrepは対象の確認、pkillは同じ条件で通知、killallは名前の完全一致で全員に通知します。-uで所有者、-fでコマンドライン全体、-xで完全一致を指定できます。止める前に必ず同じ条件でpgrep -af を実行して対象一覧を見て、まずSIGTERMを使います。この課題ではOSのプロセスを実際には操作しません。',
        '名前だけが同じ別人・別ジョブがいます。', 'awkで所有者と--jobを条件にPIDを抽出し、pkill -u 所有者 -f 一意な文字列を組み立てます。')


# ---------------------------------------------------------------- 2 systemd-run
def s2(ctx):
    a = dict(mem=str(128 * (1 + secrets.randbelow(6))) + 'M', cpu=str(10 * (1 + secrets.randbelow(8))) + '%', tasks=10 + secrets.randbelow(40))
    ctx.data.update(a)
    put(ctx, 'job.sh', '#!/bin/bash\n# 重い集計処理（偽物）\nsleep 1\n')
    put(ctx, 'example.txt', '例: systemd-run --user --scope -p MemoryMax=64M ./other.sh\n'
        '-p/--property でcgroupの制限（MemoryMax, CPUQuota, TasksMax）を渡す。--user は利用者のsystemdで実行しrootが不要。--scope は呼び出し元のプロセスを即座に包み、省略すると一時的な.serviceユニットとして裏で動く。\n'
        'systemctl --user show 一時ユニット -p MemoryMax で確認する。\n')
    ctx.write('requirements.txt', f'./job.sh をrootなしで、メモリ上限{a["mem"]}・CPU{a["cpu"]}・タスク数{a["tasks"]}の制限付きで一時実行するsystemd-runコマンドを1行でcmd.txtに書く。実行はしません。\n')


def c2(ctx):
    need_ro(ctx)
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'systemd-run', 'systemd-runで始めます。')
    ctx.require('--user' in t and 'sudo' not in t, '--userでrootなしにします。')
    props = []
    for i, x in enumerate(t):
        if x in ('-p', '--property') and i + 1 < len(t):
            props.append(t[i + 1])
        elif x.startswith('--property='):
            props.append(x.split('=', 1)[1])
    d = ctx.data
    for want in (f'MemoryMax={d["mem"]}', f'CPUQuota={d["cpu"]}', f'TasksMax={d["tasks"]}'):
        ctx.require(want in props, f'{want} を -p で指定します。')
    ctx.require(t[-1] == './job.sh', '最後に実行するコマンドを置きます。')


SOL2 = 'echo "systemd-run --user --scope -p MemoryMax=<<mem>> -p CPUQuota=<<cpu>> -p TasksMax=<<tasks>> ./job.sh" > cmd.txt'
mission(2, 'systemd-runで制限付きに一時実行する',
        'バッチ処理が他のサービスのメモリを圧迫しないよう、一時的なユニットとして資源制限を付けて動かします。実行要件の資料の設定例（ユニットとプロパティ）を読み、systemd-runコマンドを組み立てます。',
        ['実行要件の資料を読む', '指定の制限を全て含むsystemd-runをcmd.txtへ'], s2, c2, SOL2,
        ['echo "./job.sh" > cmd.txt', 'echo "sudo systemd-run -p MemoryMax=<<mem>> ./job.sh" > cmd.txt'],
        'systemd-runはcgroup上に一時ユニットを作って実行します。MemoryMaxは上限、CPUQuotaは使用率の上限、TasksMaxはプロセス数の上限です。--userはユーザーマネージャー配下で実行でき、完了後の確認はsystemctl --user showやsystemd-cgtopで行います。実機では実行中のcgroup制限を検証してください。',
        '制限はコマンドではなくsystemdのプロパティで与えます。', 'systemd-run --user --scope -p プロパティ=値 コマンド の形です。')


# ---------------------------------------------------------------- 3 loginctl
def s3(ctx):
    user = 'ops-' + secrets.token_hex(2)
    ids = [str(20 + i) for i in range(5)]
    secrets.SystemRandom().shuffle(ids)
    target = ids[0]
    ctx.data.update(user=user, target=target)
    rows = [(ids[0], user, 'pts/3', 'yes', '203.0.113.7', 'online', 'yes'),
            (ids[1], user, 'tty2', 'no', '-', 'active', 'no'),
            (ids[2], user, 'pts/5', 'yes', '198.51.100.4', 'active', 'no'),
            (ids[3], 'alice', 'pts/1', 'yes', '203.0.113.7', 'online', 'yes'),
            (ids[4], 'bob', 'pts/2', 'no', '-', 'active', 'no')]
    ls = 'SESSION UID USER SEAT TTY\n' + ''.join(f'{r[0]:>7} {1000 + i} {r[1]} {"seat0" if r[3] == "no" else "-"} {r[2]}\n' for i, r in enumerate(rows))
    ls += '\n5 sessions listed.\n'
    show = ''.join(f'$ loginctl show-session {r[0]} -p Name -p Remote -p RemoteHost -p State -p IdleHint\nName={r[1]}\nRemote={r[3]}\nRemoteHost={r[4]}\nState={r[5]}\nIdleHint={r[6]}\n\n' for r in rows)
    put(ctx, 'sessions.txt', '$ loginctl list-sessions\n' + ls)
    put(ctx, 'show.txt', show)
    ctx.write('requirements.txt', f'{user}のSSH経由（Remote=yes）で放置された（IdleHint=yes、State=online）セッションだけを終了したい。他のセッション、およびユーザー全体は止めない。cmd.txtにloginctlの1行を書く。実行しません。\n')


def c3(ctx):
    need_ro(ctx)
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[:2] == ['loginctl', 'terminate-session'], 'terminate-userではなくterminate-sessionで1セッションだけ終了します。')
    ctx.require(t[2:] == [ctx.data['target']], '対象セッションIDが違います。Remote・State・IdleHintの全部を照合します。')


SOL3 = 'echo "loginctl terminate-session <<target>>" > cmd.txt'
mission(3, 'loginctlのセッション出力を読んで1つだけ終了する',
        '共有サーバーに同じユーザーの複数セッションが残っています。loginctl list-sessions と show-sessionの出力から、放置されたリモートセッションだけを特定してください。',
        ['セッション一覧と属性の採取記録を読み対象を特定', 'loginctl terminate-sessionをcmd.txtへ'], s3, c3, SOL3,
        ['echo "loginctl terminate-user <<user>>" > cmd.txt', 'echo "loginctl terminate-session 1" > cmd.txt'],
        'loginctl list-sessionsは一覧、show-sessionは属性（Remote, State, IdleHint）を表示します。terminate-sessionは指定した1セッション、terminate-userはそのユーザーの全セッションを終了するので影響範囲が大きく違います。lock-sessionでロックだけする方法もあり、実機ではセッションIDを再確認してから実行します。',
        '同じユーザー名のセッションが複数あります。', '属性の組み合わせで1つに絞り、terminate-sessionに渡します。')


# ---------------------------------------------------------------- 4 gpg real
def gpg_env(ctx):
    env = dict(os.environ)
    env['GNUPGHOME'] = str(ctx.p('gnupg'))
    return env


def gpg(ctx, *args):
    return subprocess.run(['gpg', '--batch', '--no-tty', *args], cwd=ctx.work, env=gpg_env(ctx), capture_output=True, text=True, timeout=60)


def gpg_ok():
    try:
        return subprocess.run(['gpg', '--version'], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def s4(ctx):
    tag = secrets.token_hex(3)
    secret = 'memo-' + secrets.token_hex(8)
    ctx.data.update(tag=tag, secret=secret, real=gpg_ok())
    put(ctx, 'message.txt', secret + '\n')
    if ctx.data['real']:
        ctx.write('requirements.txt', f'この課題専用のGNUPGHOME=./gnupg（700）に鍵dojo-{tag}@example.test（パスフレーズなし、訓練用）を作成。message.txtを分離署名してmessage.txt.asc、公開鍵で暗号化してmessage.txt.gpg、復号してdecrypted.txtを作る。自分のGnuPG設定には触れない。\n')
    else:
        fp = secrets.token_hex(20).upper()
        ctx.data['fp'] = fp
        put(ctx, 'recorded.txt', f'$ gpg --list-keys --fingerprint dojo-{tag}@example.test\npub   ed25519 2026-01-01 [SC]\n      {fp}\nuid           [ultimate] dojo-{tag}@example.test\n')
        ctx.write('requirements.txt', 'gpgを実行できない環境です。recorded.txtの出力から鍵のフィンガープリント（空白なし）をfingerprint.txtへ書いてください。\n')


def c4(ctx):
    need_ro(ctx)
    if not ctx.data.get('real'):
        ctx.require(ctx.need_file('fingerprint.txt').strip().replace(' ', '') == ctx.data['fp'], 'recorded.txtのフィンガープリントを写します。')
        return
    ctx.require(ctx.isdir('gnupg') and ctx.mode('gnupg') == 0o700, 'gnupgは700のディレクトリです。')
    try:
        keys = gpg(ctx, '--list-keys', '--with-colons').stdout
        ctx.require(f'dojo-{ctx.data["tag"]}@example.test' in keys, '指定のユーザーIDの鍵がありません。')
        v = gpg(ctx, '--status-fd', '1', '--verify', 'message.txt.asc', 'message.txt')
        ctx.require(v.returncode == 0 and 'GOODSIG' in v.stdout, 'message.txt.ascがmessage.txtへの正しい署名ではありません。')
        enc = ctx.p('message.txt.gpg')
        ctx.require(enc.is_file() and ctx.data['secret'].encode() not in enc.read_bytes(), 'message.txt.gpgは暗号化されたファイルにします。')
        d = gpg(ctx, '--decrypt', 'message.txt.gpg')
        ctx.require(d.returncode == 0 and d.stdout == ctx.data['secret'] + '\n', 'message.txt.gpgを復号できません（公開鍵宛てに暗号化）。')
        ctx.require(ctx.need_file('decrypted.txt') == ctx.data['secret'] + '\n', 'decrypted.txtは復号結果です。')
    finally:
        subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=gpg_env(ctx), capture_output=True)


SOL4 = """mkdir -m 700 gnupg
export GNUPGHOME=$PWD/gnupg
gpg --batch --pinentry-mode loopback --passphrase '' --quick-generate-key dojo-<<tag>>@example.test default default never
gpg --batch --armor --detach-sign -u dojo-<<tag>>@example.test -o message.txt.asc message.txt
gpg --batch --trust-model always -r dojo-<<tag>>@example.test -o message.txt.gpg --encrypt message.txt
gpg --batch --decrypt -o decrypted.txt message.txt.gpg
gpg --verify message.txt.asc message.txt
gpgconf --kill gpg-agent || true"""
mission(4, 'GPGの鍵生成・署名・検証・暗号化・復号',
        '使い捨てのGNUPGHOMEでGPGの基本を一巡します。署名は「誰が書いたか・改ざんされていないか」、暗号化は「宛先だけが読める」ための別の機能です。',
        ['gnupg（700）に訓練用の鍵を作る', '分離署名・検証・暗号化・復号を行う'], s4, c4, SOL4,
        ['mkdir -m 700 gnupg\ncp message.txt message.txt.gpg\ncp message.txt message.txt.asc\ncp message.txt decrypted.txt',
         'mkdir gnupg\nexport GNUPGHOME=$PWD/gnupg\ngpg --batch --pinentry-mode loopback --passphrase "" --quick-generate-key dojo-<<tag>>@example.test default default never\ncp message.txt message.txt.gpg'],
        'GNUPGHOMEで鍵束の場所を切り替えるため、実環境の鍵束を汚しません。--detach-signは本体と署名を分け、--verifyで署名の正しさを確認します。--encrypt -r宛先は公開鍵で暗号化し、秘密鍵を持つ人だけが--decryptできます。署名と暗号化の失敗は別々に確認し、本物の鍵ではパスフレーズと失効証明書を管理します。gpgが無い環境では記録されたフィンガープリントの読解に切り替わります。',
        '署名と暗号化は目的が違います。', '鍵作成はgpg --quick-generate-key、署名は--detach-sign、暗号化は-r付き--encryptです。')


# ---------------------------------------------------------------- 5 gpg verify log
def s5(ctx):
    names = ['app-' + secrets.token_hex(2) + '.tar.gz' for _ in range(3)]
    good, bad, unk = names
    keyid = secrets.token_hex(8).upper()
    ctx.data.update(good=good, bad=bad, unk=unk, keyid=keyid)
    blocks = [(good, 'Good signature from "Release Team <release@dojo.test>" [full]', 'ABCDEF0123456789'),
              (bad, 'BAD signature from "Release Team <release@dojo.test>" [full]', 'ABCDEF0123456789'),
              (unk, None, keyid)]
    secrets.SystemRandom().shuffle(blocks)
    out = ''
    for n, line, k in blocks:
        out += f'$ gpg --verify {n}.sig {n}\ngpg: Signature made Mon 01 Jan 2026 using EDDSA key ID {k}\n'
        out += ('gpg: ' + line + '\n') if line else 'gpg: Can\'t check signature: No public key\n'
        out += '\n'
    put(ctx, 'verify.log', out)
    ctx.write('requirements.txt', 'verify.logを読み、result.jsonに tampered（改ざんの疑い）, unknown_key（未知の鍵で署名された）, trusted（検証成功）のファイル名、fetch_keyid（取得すべき鍵ID）, next_step（"verify-fingerprint-out-of-band"）を保存。\n')


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'result.json') == dict(tampered=d['bad'], unknown_key=d['unk'], trusted=d['good'], fetch_keyid=d['keyid'], next_step='verify-fingerprint-out-of-band'),
                'Good/BAD/No public keyは別の状態です。未知の鍵は取得しても、フィンガープリントを別経路で確認するまで信頼しません。')


SOL5 = """python3 - <<'PYCODE'
import json,re
t=open('verify.log').read(); r={}
for b in t.split('$ gpg --verify ')[1:]:
    n=b.split()[1]
    if 'BAD signature' in b: r['tampered']=n
    elif 'No public key' in b: r['unknown_key']=n; r['fetch_keyid']=re.search(r'key ID (\\w+)',b).group(1)
    else: r['trusted']=n
r['next_step']='verify-fingerprint-out-of-band'
json.dump(r,open('result.json','w'))
PYCODE"""
mission(5, 'gpg --verifyの結果を読み分ける',
        '配布物3つの検証ログが届きました。Good signature、BAD signature、No public keyは意味が全く違います。',
        ['署名検証の記録を読み分ける', 'result.jsonを作る'], s5, c5, SOL5,
        ["echo '{}' > result.json", 'python3 - <<\'PYCODE\'\nimport json\njson.dump(dict(tampered="x"),open("result.json","w"))\nPYCODE'],
        'BAD signatureは内容か署名が改ざんされた疑いで使用しません。No public keyは検証不能で、未知の鍵をgpg --recv-keysで取得してもフィンガープリントを公式の別経路と照合してから信頼します。Good signatureでも、その鍵が正しい発行元のものかを確認する必要があります。',
        '3つの状態はそれぞれ対応が違います。', 'ログを順に読み、状態ごとに分類してJSONにします。')


# ---------------------------------------------------------------- 6 flatpak / snap
def s6(ctx):
    risky = 'org.dojo.Notes' + secrets.token_hex(1)
    safe = ['org.dojo.Viewer', 'org.dojo.Music']
    snap = 'dojo-sync' + secrets.token_hex(1)
    ctx.data.update(risky=risky, snap=snap)
    put(ctx, 'flatpak-list.txt', f'$ flatpak list --app --columns=application,origin,installation\n{risky}\tflathub\tsystem\n{safe[0]}\tflathub\tuser\n{safe[1]}\tflathub\tuser\n')
    perms = lambda app, fs: f'$ flatpak info --show-permissions {app}\n[Context]\nshared=network;ipc;\nsockets=wayland;\nfilesystems={fs};\n\n'
    put(ctx, 'flatpak-perms.txt', perms(risky, 'host') + perms(safe[0], 'xdg-download:ro') + perms(safe[1], 'xdg-music'))
    put(ctx, 'snap-connections.txt', f'$ snap connections\nInterface   Plug            Slot       Notes\nssh-keys    {snap}:ssh-keys :ssh-keys  manual\nhome        {snap}:home     :home      -\nnetwork     {snap}:network  :network   -\nnetwork     other:network   :network   -\n')
    ctx.write('requirements.txt', 'audit.jsonに flatpak_app（filesystems=hostのアプリ）, flatpak_fix（そのアプリの--user向けhostファイルシステム権限を外すflatpak overrideコマンド）, snap（手動接続されたssh-keysを持つsnap名）, snap_fix（そのインターフェースを切断するsnap disconnectコマンド）を保存。実行しません。\n')


def c6(ctx):
    need_ro(ctx)
    d = ctx.data
    a = rj(ctx, 'audit.json')
    n = lambda s: ' '.join(str(s).split())
    ctx.require(a.get('flatpak_app') == d['risky'] and n(a.get('flatpak_fix')) == f'flatpak override --user --nofilesystem=host {d["risky"]}', 'host全体にアクセスできるFlatpakと、権限を外す--nofilesystemを確認します。')
    ctx.require(a.get('snap') == d['snap'] and n(a.get('snap_fix')) == f'snap disconnect {d["snap"]}:ssh-keys', 'ssh-keysを手動接続しているsnapと切断コマンドを確認します。')


SOL6 = """python3 - <<'PYCODE'
import json
a=dict(flatpak_app='<<risky>>',flatpak_fix='flatpak override --user --nofilesystem=host <<risky>>',snap='<<snap>>',snap_fix='snap disconnect <<snap>>:ssh-keys')
json.dump(a,open('audit.json','w'))
PYCODE"""
mission(6, 'FlatpakとSnapの権限出力を監査する',
        '配布元の違うアプリが入っています。flatpak list/infoとsnap connectionsの出力から、必要以上に広い権限を持つものを探して絞ります。',
        ['権限出力を読む', '過剰な権限を外すコマンドをaudit.jsonへ'], s6, c6, SOL6,
        ["echo '{}' > audit.json", 'python3 - <<\'PYCODE\'\nimport json\njson.dump(dict(flatpak_app="org.dojo.Viewer",flatpak_fix="flatpak uninstall x",snap="other",snap_fix="snap remove other"),open("audit.json","w"))\nPYCODE'],
        'Flatpakはflatpak info --show-permissionsとflatpak override --user --nofilesystem=で、Snapはsnap connectionsとsnap disconnectで権限を確認・調整します。アンインストールより先に最小権限化を試みます。システム全体への適用(--system)は管理者の判断が必要です。この課題では実行せず、記録した出力から判断します。',
        'ネットワークは普通ですが、ホスト全体やSSH鍵へのアクセスは別問題です。', 'filesystems=hostとssh-keysを探します。')


# ---------------------------------------------------------------- 7 shuf fold sort -R
def s7(ctx):
    ids = [f'row-{i:03d},{secrets.token_hex(2)}' for i in range(1, 61)]
    put(ctx, 'ids.txt', '\n'.join(ids) + '\n')
    words = ' '.join(secrets.choice(['configuration', 'authentication', 'infrastructure', 'observability', 'rollback', 'maintenance', 'repository']) for _ in range(12))
    put(ctx, 'notes.txt', words + '\n')
    ctx.write('requirements.txt', 'ids.txtから重複なしの7行をランダム抽出してsample.txt、全行を並べ替えてshuffled.txt（sort -R）、notes.txtを単語の途中で折り返さず幅28桁で整形してwrapped.txt（fold）を作る。ids.txtとnotes.txtは変更しない。\n')


def c7(ctx):
    need_ro(ctx)
    ids = ctx.need_file('ids.txt').splitlines()
    sm = ctx.need_file('sample.txt').splitlines()
    ctx.require(len(sm) == 7 and len(set(sm)) == 7 and set(sm) <= set(ids), 'ids.txtにある重複しない7行を抽出します。')
    ctx.require(sm != ids[:7], '先頭7行はランダム抽出ではありません。shufを使います。')
    sh = ctx.need_file('shuffled.txt').splitlines()
    ctx.require(sorted(sh) == sorted(ids), 'shuffled.txtは全行を過不足なく含みます。')
    ctx.require(sh != ids and sh != sorted(ids), '並びが元と同じです。sort -Rで並べ替えます。')
    r = subprocess.run(['fold', '-s', '-w', '28', 'notes.txt'], cwd=ctx.work, capture_output=True, text=True)
    ctx.require(ctx.need_file('wrapped.txt') == r.stdout, 'fold -s -w 28 の出力と一致させます（-sで単語境界）。')


SOL7 = """shuf -n 7 ids.txt > sample.txt
sort -R ids.txt > shuffled.txt
fold -s -w 28 notes.txt > wrapped.txt"""
mission(7, 'shuf・sort -R・foldでデータを整形する',
        'テスト用に一覧からランダムなサンプルを取り、全体の順序を混ぜ、長い文を読みやすい幅に折り返します。',
        ['shufで7行抽出', 'sort -Rで全行を並べ替え', 'foldで単語境界の折り返し'], s7, c7, SOL7,
        ['head -7 ids.txt > sample.txt\nsort ids.txt > shuffled.txt\nfold -w 28 notes.txt > wrapped.txt',
         'shuf -n 7 ids.txt > sample.txt\nshuf ids.txt > shuffled.txt\nfold -w 28 notes.txt > wrapped.txt'],
        'shufは行を等確率で並べ替え、-n 件数で抽出できます。sort -Rは同じキーの行をまとめる点で完全なランダムとは限りません。foldは既定で桁数ちょうどで切るため単語が割れ、-sで空白位置を優先します。再現が必要なときは--random-sourceを使います。',
        '先頭から取るのはサンプリングではありません。', 'shuf -n、sort -R、fold -s -w を組み合わせます。')


# ---------------------------------------------------------------- 8 eval
def s8(ctx):
    tag = secrets.token_hex(3)
    ctx.data['tag'] = tag
    name = f'report-{tag}; touch PWNED-{tag}'
    lines = secrets.randbelow(8) + 3
    ctx.data.update(fname=name, n=lines)
    ctx.write(name, ''.join(f'line {i}\n' for i in range(lines)))
    ctx.write('plain.txt', 'a\nb\n')
    put(ctx, 'vulnerable.sh', '#!/bin/bash\n# 行数を数える（脆弱）\nf="$1"\neval "wc -l < $f"\n')
    ctx.write('requirements.txt', 'vulnerable.shはevalでユーザー入力を実行する。名前に; touch PWNED-... を含むファイルを渡すと、コマンドが実行される。evalを使わないsafe.shを作り、引数のファイルの行数だけを表示する（空白や;を含む名前でも安全に）。\n')


def run_safe(ctx, arg):
    return subprocess.run(['bash', 'safe.sh', arg], cwd=ctx.work, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)


def c8(ctx):
    need_ro(ctx)
    src = ctx.need_file('safe.sh')
    code = '\n'.join(x.split('#')[0] for x in src.splitlines())
    ctx.require(not re.search(r'\beval\b', code), 'evalを使いません。')
    r = run_safe(ctx, ctx.data['fname'])
    ctx.require(not ctx.exists('PWNED-' + ctx.data['tag']), '入力がコマンドとして実行されました。')
    ctx.require(r.stdout.split()[:1] == [str(ctx.data['n'])], '特殊文字を含む名前のファイルの行数を表示します。')
    ctx.require(run_safe(ctx, 'plain.txt').stdout.split()[:1] == ['2'], '通常のファイルでも動くようにします。')


SOL8 = """cat > safe.sh <<'EOF'
#!/bin/bash
f="$1"
wc -l < "$f"
EOF"""
mission(8, 'evalの危険とインジェクションを避ける',
        'evalは文字列をシェルコードとして再解釈します。入力に;や$(...)があると、意図しないコマンドが実行されます。脆弱なスクリプトを読み、同じ目的の安全なsafe.shを作ってください。',
        ['脆弱な点を理解する', 'evalなしのsafe.shを作る'], s8, c8, SOL8,
        ["cat > safe.sh <<'EOF'\n#!/bin/bash\neval \"wc -l < \\\"$1\\\"\"\nEOF", "cat > safe.sh <<'EOF'\n#!/bin/bash\nwc -l < $1\nEOF"],
        '入力をeval・bash -c・sh -cへ連結するとコードになります。必要ならprintf %qでの引用や、配列と"$@"、case文による許可リストを使います。変数は必ず"$var"と引用し、ファイル名の先頭が-なら--や./を付けます。evalが必要な場面でも入力は信頼できる値だけに限定します。',
        '文字列を再解釈する仕組みが問題です。', '変数を引用符で包んで直接wcへ渡します。')


# ---------------------------------------------------------------- 9 sosreport
def s9(ctx):
    pw, key, tok = ['pw' + secrets.token_hex(5), 'k' + secrets.token_hex(6), 't' + secrets.token_hex(7)]
    ctx.data.update(vals=[pw, key, tok])
    put(ctx, 'collect/etc/app.conf', f'listen=0.0.0.0:8080\ndb_password={pw}\nretries=3\napi_key: {key}\nmode=production\n')
    put(ctx, 'collect/logs/journal.txt', f'Jan 01 app started\nJan 01 request Authorization: Bearer {tok}\nJan 01 disk usage 71%\n')
    put(ctx, 'collect/os-release', 'NAME="Ubuntu"\nVERSION_ID="24.04"\n')
    ctx.write('requirements.txt', 'sosreportで集めた診断情報collect/を、ベンダーへ送る前にbundle/へ同じ構成でコピーし、パスワード・APIキー・Bearerトークンの値を<REDACTED>に置換する。collect/は証拠として変更しない。他の行（設定値・ログ）は一字も変えない。\n')


def c9(ctx):
    need_ro(ctx)
    vals = ctx.data['vals']
    hits = 0
    for name in ctx.data['ro']:
        src = ctx.need_file(name)
        dst = ctx.need_file(name.replace('collect/', 'bundle/', 1), '同じ構成でコピーしてください。')
        sl, dl = src.splitlines(), dst.splitlines()
        ctx.require(len(sl) == len(dl), name + ' の行数が変わっています。')
        for a, b in zip(sl, dl):
            if any(v in a for v in vals):
                ctx.require('<REDACTED>' in b and not any(v in b for v in vals), '機密値が残っているか、マスクされていません。')
                hits += 1
            else:
                ctx.require(a == b, '機密でない行は変更しません: ' + a)
    ctx.require(hits == 3, '3つの機密値をマスクします。')


SOL9 = """find collect -type f | while read -r f; do
  d=bundle/${f#collect/}; mkdir -p "$(dirname "$d")"
  sed -E 's/((pass(word)?|secret|api_key|token)[A-Za-z_]*[=:] *).*/\\1<REDACTED>/I; s/(Bearer ).*/\\1<REDACTED>/' "$f" > "$d"
done"""
mission(9, '診断情報を安全に共有する前に機密をマスクする',
        'sosreport（RHEL系）やsos report、journalctl・設定ファイルを集めた診断バンドルをサポートへ送ります。パスワードやAPIキーが入ったまま出してはいけません。',
        ['収集済みの診断資料を変更せずbundle/へ複製', '機密値だけを<REDACTED>に置換'], s9, c9, SOL9,
        ['cp -r collect bundle', 'cp -r collect bundle\nsed -i "s/.*//" bundle/etc/app.conf'],
        'sosreportは構成・ログを自動収集しますが、環境固有の機密は残ることがあります。送る前に元データは保全したまま複製に対しマスクし、grepで値が残っていないことを検証します。sos reportの--cleanなどの匿名化も、結果の確認は人が行います。行を丸ごと消すより、キー名を残してどの設定があったか分かるようにします。',
        '全消去では診断に使えません。', 'sed -Eで値の部分だけを置換し、同じ構成で出力します。')


# ---------------------------------------------------------------- 10 podman
def s10(ctx):
    name = 'web-' + secrets.token_hex(2)
    image = 'docker.io/library/nginx:' + secrets.choice(['1.25', '1.26', '1.27'])
    ctx.data.update(name=name, image=image)
    put(ctx, 'compose.yml', f'services:\n  web:\n    image: {image}\n    container_name: {name}\n    ports:\n      - "80:80"\n    volumes:\n      - ./data:/usr/share/nginx/html\n')
    put(ctx, 'podman-info.txt', 'host:\n  security:\n    rootless: true\n    selinuxEnabled: true\n  rootlessNetworkCmd: pasta\n')
    put(ctx, 'error.txt', "Error: rootlessport cannot expose privileged port 80, you can add 'net.ipv4.ip_unprivileged_port_start=80' to /etc/sysctl.conf (currently 1024), or choose a larger port number (>= 1024): listen tcp 0.0.0.0:80: bind: permission denied\n")
    ctx.write('requirements.txt', 'rootlessのpodmanでcompose.ymlと同等のコンテナを起動する1行のコマンドをrun.shに書く（-d, --name, 1024以上のホストポート, ./dataのボリューム, イメージ）。sudoやdocker、--privilegedは使わない。diagnosis.jsonにcause=privileged-port-rootlessを記録。\n')


def c10(ctx):
    need_ro(ctx)
    ctx.require(rj(ctx, 'diagnosis.json') == dict(cause='privileged-port-rootless'), 'エラーの原因を記録します。')
    t = toks(ctx, one_line(ctx, 'run.sh'))
    ctx.require(t[:2] == ['podman', 'run'], 'podman runで始めます（dockerではありません）。')
    ctx.require(not {'sudo', '--privileged'} & set(t), 'rootや特権は使いません。')
    ctx.require('-d' in t and '--name' in t and t[t.index('--name') + 1] == ctx.data['name'], '-dと--nameを指定します。')
    ps = [x for i, x in enumerate(t) if i and t[i - 1] in ('-p', '--publish')]
    ctx.require(len(ps) == 1 and re.fullmatch(r'(?:[\d.]+:)?(\d+):80', ps[0]) and int(re.fullmatch(r'(?:[\d.]+:)?(\d+):80', ps[0]).group(1)) >= 1024, '1024以上のホストポートを80へ割り当てます。')
    vs = [x for i, x in enumerate(t) if i and t[i - 1] in ('-v', '--volume')]
    ctx.require(len(vs) == 1 and re.match(r'(\./|\$PWD/|\$\(pwd\)/)?data:/usr/share/nginx/html', vs[0]), '(./data)をコンテナのHTML置き場へ渡します。')
    ctx.require(t[-1] == ctx.data['image'], '最後にイメージを指定します。')


SOL10 = """echo '{"cause":"privileged-port-rootless"}' > diagnosis.json
echo "podman run -d --name <<name>> -p 8080:80 -v ./data:/usr/share/nginx/html:Z <<image>>" > run.sh"""
mission(10, 'rootless podmanへの読み替え',
        'docker composeの定義をrootless podmanで動かします。podmanはデーモンなしで一般ユーザーのまま動き、podman-composeやquadletでも同様に扱えます。エラーログとpodmanの環境情報を読み、動くコマンドに直してください。',
        ['エラーの原因を診断', 'rootlessで動くpodman runをrun.shへ'], s10, c10, SOL10,
        ['echo "docker run -d --name <<name>> -p 80:80 <<image>>" > run.sh', 'echo "sudo podman run -d --name <<name>> -p 80:80 <<image>>" > run.sh\necho \'{"cause":"privileged-port-rootless"}\' > diagnosis.json'],
        'rootless podmanは1024未満のポートへの割り当てにsysctl net.ipv4.ip_unprivileged_port_startの変更が必要ですが、通常は高番号ポートに公開し、前段のプロキシで受けます。SELinux有効環境ではボリュームに:Zを付けます。dockerとの違いは常駐デーモンがないこと、rootless、podman generate/quadletでsystemd統合できることです。',
        'rootlessでは特権ポートを使えません。', 'podman runに-p 8080:80、-v ./data:...:Z、イメージを指定します。')


# ---------------------------------------------------------------- 11 nsenter
def s11(ctx):
    base = 3000 + secrets.randbelow(5000)
    c, side, other = base, base + 11, base + 25
    ctx.data.update(c=c, side=side)
    host = {'net': 'net:[4026531840]', 'mnt': 'mnt:[4026531841]', 'pid': 'pid:[4026531836]'}
    ce = {'net': 'net:[4026532500]', 'mnt': 'mnt:[4026532498]', 'pid': 'pid:[4026532501]'}
    sd = dict(ce, mnt='mnt:[4026532600]', pid='pid:[4026532601]')
    rows = [(1, 'systemd', host), (other, 'sshd', host), (c, 'nginx', ce), (side, 'log-agent', sd), (side + 5, 'bash', host)]
    secrets.SystemRandom().shuffle(rows)
    put(ctx, 'ns.txt', '  PID COMMAND    NET                MNT                PID_NS\n' + ''.join(f'{p:5d} {n:<10} {d["net"]:<18} {d["mnt"]:<18} {d["pid"]}\n' for p, n, d in rows))
    ctx.write('requirements.txt', f'コンテナのnginx(PID {c})とネットワークnamespaceを共有する他のPIDと、そのネットワークだけに入ってip addrを実行するnsenterコマンドをdiagnosis.jsonに記録する（shares_net_with配列、command文字列）。実行はしません。\n')


def c11(ctx):
    need_ro(ctx)
    d = rj(ctx, 'diagnosis.json')
    ctx.require(d.get('shares_net_with') == [ctx.data['side']], '同じNET番号を持つ他のプロセスを探します（ホストのNETとは別）。')
    t = toks(ctx, str(d.get('command', '')))
    c = str(ctx.data['c'])
    ctx.require(t[:1] == ['nsenter'], 'nsenterを使います。')
    rest = t[1:]
    ok_t = any(rest[i] in ('-t', '--target') and rest[i + 1] == c for i in range(len(rest) - 1)) or f'--target={c}' in rest or f'-t{c}' in rest
    ctx.require(ok_t, '-t でコンテナのPIDを指定します。')
    ctx.require(any(x in ('-n', '--net') or x == '--net=' for x in rest) and not any(x in ('-a', '--all', '-m', '--mount', '-p', '--pid') for x in rest), 'ネットワークnamespaceだけに入ります（-n）。')
    ctx.require(t[-2:] in (['ip', 'addr'], ['ip', 'a']), '最後にip addrを実行します。')


SOL11 = """python3 - <<'PYCODE'
import json
rows=[l.split() for l in open('ns.txt').read().splitlines()[1:]]
c=<<c>>; net=[r[2] for r in rows if int(r[0])==c][0]
json.dump(dict(shares_net_with=sorted(int(r[0]) for r in rows if r[2]==net and int(r[0])!=c),command=f'nsenter -t {c} -n ip addr'),open('diagnosis.json','w'))
PYCODE"""
mission(11, 'nsenterでnamespaceの共有を読み解く',
        'コンテナやPodの中ではプロセスごとにnamespaceが分かれます。/proc/PID/nsのinode番号（lsnsでも確認可）が同じなら同じ空間です。namespaceの採取記録を読み、nsenterで調べる対象を決めます。',
        ['NETの同じプロセスを特定', 'nsenterコマンドを記録'], s11, c11, SOL11,
        ["echo '{}' > diagnosis.json", "python3 - <<'PYCODE'\nimport json\njson.dump(dict(shares_net_with=[],command='nsenter -t <<c>> -a ip addr'),open('diagnosis.json','w'))\nPYCODE"],
        'namespaceは番号が同じなら共有です。nsenter -t PID -nは対象プロセスのネットワークnamespaceだけに入り、ホストのツールでip addrやssを実行できます。-aは全namespaceへ入り影響が大きいので必要な種類だけ指定します。nsenterは通常rootまたは権限が必要ですが、この課題では記録の読解だけを行います。',
        'inode番号の一致が共有です。', 'NET列を比較し、nsenter -t PID -n を使います。')


# ---------------------------------------------------------------- 12 chroot / unshare
def s12(ctx):
    libs = ['/lib/x86_64-linux-gnu/libc.so.6', '/lib/x86_64-linux-gnu/libtinfo.so.6', '/lib/x86_64-linux-gnu/libselinux.so.1', '/lib/x86_64-linux-gnu/libpcre2-8.so.0', '/lib64/ld-linux-x86-64.so.2']
    miss = sorted(secrets.SystemRandom().sample(libs, 2))
    ctx.data['miss'] = miss
    present = [x for x in libs if x not in miss]
    put(ctx, 'ldd.txt', '$ ldd /bin/sh\n' + ''.join(f'\t{os.path.basename(x)} => {x} (0x00007f0000000000)\n' for x in libs))
    put(ctx, 'newroot-tree.txt', '$ find newroot -type f\nnewroot/bin/sh\n' + ''.join('newroot' + x + '\n' for x in present))
    put(ctx, 'error.txt', "$ chroot newroot /bin/sh\nchroot: failed to run command '/bin/sh': No such file or directory\n")
    ctx.write('requirements.txt', 'diagnosis.jsonには cause（missing-command / permission / missing-shared-libraries）、newrootに不足するライブラリの絶対パス配列missing（昇順）、boundary（filesystem-root-only / process-network-user-isolation）を保存する。lddとファイル一覧を比較する。chroot自体はプロセス・ネットワーク・ユーザーを隔離しない。\n')


def c12(ctx):
    need_ro(ctx)
    ctx.require(rj(ctx, 'diagnosis.json') == dict(cause='missing-shared-libraries', missing=ctx.data['miss'], boundary='filesystem-root-only'),
                '/bin/shが存在してもlddの依存ライブラリがnewrootに無いと起動できません。')


SOL12 = """python3 - <<'PYCODE'
import json,re
libs=re.findall(r'=> (\\S+)',open('ldd.txt').read())
tree=open('newroot-tree.txt').read()
json.dump(dict(cause='missing-shared-libraries',missing=sorted(x for x in libs if 'newroot'+x not in tree),boundary='filesystem-root-only'),open('diagnosis.json','w'))
PYCODE"""
mission(12, 'chrootとunshareの隔離範囲を診断する',
        'chrootで作った最小環境が起動しません。unshare・nsenterによるnamespace隔離との違いも含めて、記録から原因を読み解きます。',
        ['lddとファイル一覧を比較', 'diagnosis.jsonに原因と隔離範囲を保存'], s12, c12, SOL12,
        ["echo '{\"cause\":\"permission\"}' > diagnosis.json", "python3 - <<'PYCODE'\nimport json\njson.dump(dict(cause='missing-shared-libraries',missing=[],boundary='filesystem-root-only'),open('diagnosis.json','w'))\nPYCODE"],
        'chrootはルートディレクトリの見え方を変えるだけで、PID・ネットワーク・ユーザーなどは分離しません。それらはunshare --pid --net --user --mount などのnamespaceで行い、コンテナはそれらとcgroupの組み合わせです。No such file or directoryは、実行ファイルだけでなく動的リンカーと共有ライブラリが新しいルートに無い場合にも出ます。',
        'エラーはシェル自体の欠如とは限りません。', 'lddの一覧からnewrootに無い依存を探します。')


# ---------------------------------------------------------------- 13 ansible inventory
def s13(ctx):
    group = 'webservers_' + secrets.token_hex(2)
    wrong = 'web_' + secrets.token_hex(2)
    ctx.data.update(group=group)
    put(ctx, 'inventory.ini', f'[{group}]\nweb1 ansible_host=192.0.2.11\nweb2 ansible_host=192.0.2.12\n\n[db]\ndb1 ansible_host=192.0.2.21\n')
    ctx.write('site.yml', f'- hosts: {wrong}\n  become: true\n  tasks:\n    - name: ensure nginx is installed\n      ansible.builtin.package:\n        name: nginx\n        state: present\n')
    ctx.data['orig_site'] = ctx.read('site.yml')
    put(ctx, 'output.txt', f"$ ansible-playbook -i inventory.ini site.yml\n[WARNING]: Could not match supplied host pattern, ignoring: {wrong}\nPLAY [{wrong}] ***\nskipping: no hosts matched\nPLAY RECAP ***\n")
    ctx.write('requirements.txt', 'site.ymlのhosts行だけを修正してインベントリのWebグループを対象にする。他の行は変更しない。実行はしません。\n')


def c13(ctx):
    need_ro(ctx)
    want = re.sub(r'^- hosts: .*$', '- hosts: ' + ctx.data['group'], ctx.data['orig_site'], flags=re.M)
    ctx.require(ctx.need_file('site.yml') == want, 'hosts行をインベントリのグループ名に合わせます。ほかは変更しません。')


SOL13 = "sed -i 's/^- hosts: .*/- hosts: <<group>>/' site.yml"
mission(13, 'Ansibleのインベントリとplaybookを読み合わせる',
        'ansible-playbookが「no hosts matched」で何もせず成功します。ansible-inventory --listで見えるグループ名とplaybookのhostsを突き合わせてください。',
        ['インベントリの控えのグループを確認', 'playbookの控えのhostsを修正'], s13, c13, SOL13,
        ["sed -i 's/^- hosts: .*/- hosts: all/' site.yml", "sed -i 's/^- hosts: .*/- hosts: db/' site.yml"],
        'hostsに書く名前はインベントリのグループ・ホスト名と一致する必要があります。allなどで広げると意図しない環境も変更します。実行前にansible-inventory --graphとansible-playbook --list-hostsで対象を確認し、--limitで絞ります。',
        '一致しないパターンはエラーにならず飛ばされます。', 'hosts行だけをsedなどで差し替えます。')


# ---------------------------------------------------------------- 14 ansible idempotence
def s14(ctx):
    n = 100 + secrets.randbelow(900)
    ctx.data['n'] = n
    ctx.write('site.yml', f'- hosts: all\n  tasks:\n    - name: set max connections\n      ansible.builtin.shell: echo "max_conn={n}" >> /etc/app.conf\n')
    put(ctx, 'run1.txt', '$ ansible-playbook site.yml\nTASK [set max connections]\nchanged: [web1]\nPLAY RECAP: web1 ok=1 changed=1\n')
    put(ctx, 'run2.txt', '$ ansible-playbook site.yml --check --diff\nTASK [set max connections]\nchanged: [web1]\n+max_conn=%d\nPLAY RECAP: web1 ok=1 changed=1\n' % n)
    ctx.write('requirements.txt', 'run2.txtの2回目でもchangedなのは冪等でないため。site.ymlのタスクをlineinfile（path: /etc/app.conf, regexp, line: "max_conn=値"）に置き換え、shell/commandは使わない。idempotent.txtにchangedとして報告された元のタスク名を書く。\n')


def c14(ctx):
    need_ro(ctx)
    ctx.require(ctx.need_file('idempotent.txt').strip() == 'set max connections', 'run2.txtでchangedになったタスク名を書きます。')
    y = ctx.need_file('site.yml')
    ctx.require(re.search(r'ansible\.builtin\.lineinfile:|^\s*lineinfile:', y, re.M), 'lineinfileモジュールを使います。')
    ctx.require(not re.search(r'\b(shell|command|raw):|>>', y), 'shell/command/追記リダイレクトは冪等ではありません。')
    ctx.require(re.search(r'path:\s*/etc/app\.conf\s*$', y, re.M) and re.search(r'regexp:\s*\S+', y), 'pathとregexp（既存行の識別）を指定します。')
    ctx.require(re.search(r'line:\s*["\']?max_conn=%d["\']?\s*$' % ctx.data['n'], y, re.M), 'line: "max_conn=値" で目的の状態を宣言します。')


SOL14 = """cat > site.yml <<'EOF'
- hosts: all
  tasks:
    - name: set max connections
      ansible.builtin.lineinfile:
        path: /etc/app.conf
        regexp: '^max_conn='
        line: "max_conn=<<n>>"
EOF
echo 'set max connections' > idempotent.txt"""
mission(14, 'Ansibleの冪等性を--check出力で診断する',
        'playbookを2回実行しても毎回changedになります。--check --diff相当の記録を読み、「やり方」ではなく「状態」を宣言する形に直します。',
        ['2回目の実行記録でchangedの理由を読む', 'playbookの控えをlineinfileにして冪等にする'], s14, c14, SOL14,
        ["echo 'set max connections' > idempotent.txt", "echo 'set max connections' > idempotent.txt\nsed -i 's/shell/command/' site.yml"],
        'shellやcommandで追記すると実行のたびに行が増えます。lineinfileは正規表現で行を特定し、すでに目的の状態ならokになります。ansible-playbook --check --diffで差分だけを事前確認し、2回目の実行でchanged=0になることを冪等性の判定にします。',
        '2回目に何が変わるかを見ます。', 'lineinfileにpath, regexp, lineを指定します。')
