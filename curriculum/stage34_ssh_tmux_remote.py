"""Stage 34: SSH・tmux・リモート作業の実践。サンドボックス内の偽データと使える本物のツール（ssh -G・ssh-keygen）だけを使う。"""
import fnmatch
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from engine.runner import register

S = 34
NOTE = ("作業対象はこの課題のフォルダだけです。実際のサーバーへは接続せず、~/.ssh や実OSの設定には触れず、rootも使いません。"
        "鍵・ホスト名・IPは訓練用の偽物で、実行環境にないツール（tmux・sshd・sshfsなど）は採取済みの出力と設定例から診断します。")
ALNUM = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
SSH = shutil.which('ssh')
KG = shutil.which('ssh-keygen')


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


def rnd(n=6):
    return ''.join(secrets.choice(ALNUM) for _ in range(n))


def fakepub(kind='ssh-ed25519'):
    return f'{kind} AAAAC3NzaC1lZDI1NTE5AAAAI{rnd(43)}'


def fp_of(text):
    return 'SHA256:' + hashlib.sha256(text.encode()).hexdigest()[:43]


def kgrun(args, **kw):
    try:
        return subprocess.run([KG] + args, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, **kw)
    except (OSError, subprocess.SubprocessError):
        return None


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'34-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='接続・認証・権限の問題は、設定を推測で変えず ssh -G や -v の出力、ファイル権限を観測してから直しましょう。変更前の控えと別セッションの確認が事故を防ぎます。')


# ------------------------------------------------ ssh_config の解決（ssh -G。無い環境では簡易評価で代用）
def _parse_cfg(text):
    blocks, cur = [], (None, [])
    blocks.append(cur)
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith('#'):
            continue
        parts = re.split(r'\s*=\s*|\s+', ln, maxsplit=1)
        k, v = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else '')
        if k in ('host', 'match'):
            cur = ((k, v), [])
            blocks.append(cur)
        else:
            cur[1].append((k, v))
    return blocks


def _match(cond, host, user):
    if cond is None:
        return True
    k, v = cond
    if k == 'host':
        pats = shlex.split(v)
        pos = [p for p in pats if not p.startswith('!')]
        neg = [p[1:] for p in pats if p.startswith('!')]
        return any(fnmatch.fnmatchcase(host, p) for p in pos) and not any(fnmatch.fnmatchcase(host, p) for p in neg)
    t = shlex.split(v)
    i = 0
    while i < len(t):
        w = t[i].lower()
        if w == 'all':
            i += 1
            continue
        if w in ('host', 'originalhost', 'user') and i + 1 < len(t):
            val = host if w != 'user' else user
            if not any(fnmatch.fnmatchcase(val, p) for p in t[i + 1].split(',')):
                return False
            i += 2
            continue
        return False
    return True


def ssh_g(ctx, cfg, host, user='trainee'):
    """host に対する設定を {キー: [値...]} で返す。"""
    ctx.need_file(cfg)
    out = {}
    if SSH:
        r = subprocess.run([SSH, '-F', str(ctx.p(cfg)), '-G', host], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            ctx.fail(f'{cfg} を ssh が解釈できません: ' + r.stderr.strip()[:120])
        for ln in r.stdout.splitlines():
            k, _, v = ln.partition(' ')
            out.setdefault(k, []).append(v)
        return out
    for cond, items in _parse_cfg(ctx.need_file(cfg)):
        if _match(cond, host, user):
            for k, v in items:
                if k == 'identityfile':
                    out.setdefault(k, []).append(v)
                elif k not in out:
                    out[k] = [v]
    out.setdefault('user', [user])
    out.setdefault('port', ['22'])
    for k in ('controlmaster',):
        if k in out:
            out[k] = [{'no': 'false', 'yes': 'true'}.get(out[k][0], out[k][0])]
    return out


def first(d, k, default=None):
    return d.get(k, [default])[0]


def secs(v):
    m = re.fullmatch(r'(\d+)([smhdw]?)', str(v).strip())
    if not m:
        return None
    return int(m.group(1)) * {'': 1, 's': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}[m.group(2)]


def want(ctx, d, key, val, host):
    got = first(d, key)
    ctx.require(got == str(val), f'{host} の {key} は {val} になるはずですが、{got} と解決されました（ssh -G で確認します）。')


# ================================================================ 1
def s1(ctx):
    dp = 2200 + secrets.randbelow(600)
    ctx.data.update(dp=dp, ep=dp + 1, du='ops' + secrets.token_hex(2))
    put(ctx, 'ssh_config.orig', '# 現在の設定（先頭の Host * が値を先取りしてしまっている）\nHost *\n    User ops\n    Port 22\n\nHost web*\n    User deploy\n    Port %d\n' % dp)
    ctx.write('ssh_config', ctx.read('ssh_config.orig'))
    ctx.write('requirements.txt', f'ssh_config を直し、`ssh -F ssh_config -G ホスト名` で次のように解決させる。web01 は User deploy・Port {ctx.data["ep"]}（例外）、web02 など web* は User deploy・Port {dp}、それ以外（db01・cache9など）は User {ctx.data["du"]}・Port 22。ssh は「最初に得た値」を採用する点に注意。\n')


def c1(ctx):
    need_ro(ctx)
    d = ctx.data
    for h, u, p in (('web01', 'deploy', d['ep']), ('web02', 'deploy', d['dp']), ('web77', 'deploy', d['dp']), ('db01', d['du'], 22), ('cache9', d['du'], 22)):
        r = ssh_g(ctx, 'ssh_config', h)
        want(ctx, r, 'user', u, h)
        want(ctx, r, 'port', p, h)


SOL1 = """cat > ssh_config <<'EOF'
Host web01
    Port <<ep>>
Host web*
    User deploy
    Port <<dp>>
Host *
    User <<du>>
    Port 22
EOF"""
mission(1, 'ssh_configのHostワイルドカードとUser/Port・優先順位をssh -Gで検証する',
        '共通設定の Host * を先頭に書いたせいで、web* 用の User/Port が効きません。ssh_config は上から順に読まれ、同じキーは最初に得た値が優先されます。個別 > ワイルドカード > Host * の順に並べ替え、ssh -F ssh_config -G で解決結果を確かめてください。',
        ['ssh_config.orig は変更せず ssh_config を修正', 'ssh -G で web01・web*・その他が要件どおり解決される'], s1, c1, SOL1,
        ["sed -i 's/^Host \\*/Host db*/' ssh_config", "printf 'Host *\\n    User <<du>>\\n    Port 22\\n' > ssh_config"],
        'ssh_config は上から読み、各項目は最初に一致して得た値が採用されます（IdentityFileなど一部は累積）。そのため具体的な Host を先、ワイルドカードを後、全体既定の Host * を最後に置きます。ssh -G ホスト は実際に接続せず最終的な値（user・port・hostname）を表示するので、設定変更の検証に最適です。-F で別の設定ファイルを指定できます。',
        '先に得た値が勝つので、特殊なものを上に書きます。', 'Host web01、Host web*、Host * の順に書き、ssh -F ssh_config -G web01 で確認します。')


# ================================================================ 2
def s2(ctx):
    dom = rnd(5).lower() + '.test'
    ctx.data['dom'] = dom
    put(ctx, 'ssh_config.orig', '# 方針なし。全ての鍵がエージェントから順に提示されてしまう\nHost *\n    ServerAliveInterval 30\n')
    ctx.write('ssh_config', ctx.read('ssh_config.orig'))
    ctx.write('requirements.txt', f'git.{dom} は Match host を使い User git・IdentityFile ~/.ssh/id_git・IdentitiesOnly yes。*.corp.{dom}（Host で指定）は IdentityFile ~/.ssh/id_work・IdentitiesOnly yes。その他のホストは IdentitiesOnly を有効にしない。ssh -F ssh_config -G で検証される。\n')


def c2(ctx):
    need_ro(ctx)
    ctx.require(re.search(r'(?im)^\s*Match\s+host\b', ctx.need_file('ssh_config')), 'git.* の設定には Match host を使います。')
    g = ssh_g(ctx, 'ssh_config', 'git.' + ctx.data['dom'])
    want(ctx, g, 'user', 'git', 'git')
    ctx.require(first(g, 'identityfile', '').endswith('id_git'), 'git の最初の IdentityFile が ~/.ssh/id_git になっていません。')
    want(ctx, g, 'identitiesonly', 'yes', 'git')
    w = ssh_g(ctx, 'ssh_config', 'app.corp.' + ctx.data['dom'])
    ctx.require(first(w, 'identityfile', '').endswith('id_work'), 'corp の最初の IdentityFile が ~/.ssh/id_work になっていません。')
    want(ctx, w, 'identitiesonly', 'yes', 'corp')
    o = ssh_g(ctx, 'ssh_config', 'other.' + ctx.data['dom'])
    ctx.require(first(o, 'identitiesonly') in (None, 'no', 'false'), '無関係なホストには IdentitiesOnly を付けません。')


SOL2 = """cat > ssh_config <<'EOF'
Match host git.<<dom>>
    User git
    IdentityFile ~/.ssh/id_git
    IdentitiesOnly yes
Host *.corp.<<dom>>
    IdentityFile ~/.ssh/id_work
    IdentitiesOnly yes
Host *
    ServerAliveInterval 30
EOF"""
mission(2, 'MatchとIdentityFile・IdentitiesOnlyで接続先ごとに鍵を固定する',
        'エージェントに鍵が何本もあると、順に提示して Too many authentication failures になります。接続先ごとに IdentityFile を決め、IdentitiesOnly yes で指定した鍵だけを提示させましょう。条件指定には Host と Match（Match host / user / exec など）があります。',
        ['Match host と Host ワイルドカードを使い分ける', 'ssh -G で identityfile と identitiesonly を確認'], s2, c2, SOL2,
        ["printf 'Host *\\n    IdentitiesOnly yes\\n    IdentityFile ~/.ssh/id_work\\n' > ssh_config", "printf 'Host git.<<dom>>\\n    IdentityFile ~/.ssh/id_git\\n' > ssh_config"],
        'IdentityFile は鍵の候補を指定するだけで、IdentitiesOnly yes がないと ssh-agent の鍵も提示されます。Host は接続時に指定した名前、Match は host・user・exec・localnetwork など複数条件を AND で評価でき、Match all で全体になります。IdentityFile は累積、他の多くは最初の値が優先です。ssh -G で identityfile の並びを確認します。',
        'Match host ホスト名 のブロックに鍵と IdentitiesOnly を入れます。', 'Match host、Host *.corp.…、Host * の順に書き、ssh -G で確認します。')


# ================================================================ 3
def s3(ctx):
    dom = rnd(4).lower() + '.test'
    ip1, ip2 = f'10.20.0.{10 + secrets.randbelow(40)}', f'10.20.1.{10 + secrets.randbelow(40)}'
    ctx.data.update(dom=dom, bp=2200 + secrets.randbelow(500), ip1=ip1, ip2=ip2)
    put(ctx, 'jump.pub', fakepub() + ' jump-key\n')
    put(ctx, 'ssh_config.orig', '# 内部ホストは踏み台経由でしか届かない\nHost *\n    ServerAliveInterval 30\n')
    ctx.write('ssh_config', ctx.read('ssh_config.orig'))
    ctx.write('requirements.txt', f'(1) ssh_config: 別名 bastion（HostName bastion.{dom}・User jump・Port {ctx.data["bp"]}）を定義し、app-* と db-* は ProxyJump bastion・User deploy で届くようにする（bastion 自身は ProxyJump しない）。(2) 踏み台の jump アカウント用 bastion_authorized_keys を作る: jump.pub の鍵に restrict,port-forwarding,permitopen="{ip1}:22",permitopen="{ip2}:22" を付け、シェルを与えず中継だけ許可する。\n')


def c3(ctx):
    need_ro(ctx)
    a = ssh_g(ctx, 'ssh_config', 'app-01')
    ctx.require('bastion' in first(a, 'proxyjump', ''), 'app-01 に ProxyJump bastion が適用されていません。')
    want(ctx, a, 'user', 'deploy', 'app-01')
    ctx.require('bastion' in first(ssh_g(ctx, 'ssh_config', 'db-01'), 'proxyjump', ''), 'db-01 に ProxyJump bastion が適用されていません。')
    b = ssh_g(ctx, 'ssh_config', 'bastion')
    ctx.require(first(b, 'proxyjump') in (None, 'none'), 'bastion 自身が ProxyJump していると自己ループになります。')
    want(ctx, b, 'hostname', 'bastion.' + ctx.data['dom'], 'bastion')
    want(ctx, b, 'port', ctx.data['bp'], 'bastion')
    want(ctx, b, 'user', 'jump', 'bastion')
    ls = [x for x in ctx.need_file('bastion_authorized_keys').splitlines() if x.strip()]
    ctx.require(len(ls) == 1, 'bastion_authorized_keys は鍵1本・1行です。')
    key = ctx.read('jump.pub').split()[1]
    m = re.match(r'^(\S+) ssh-ed25519 (\S+)', ls[0])
    ctx.require(m and m.group(2) == key, '行頭に オプション を置き、その後に jump.pub の鍵をそのまま続けます。')
    opts = ls[0].split(' ssh-ed25519')[0]
    ctx.require('restrict' in opts.split(',') and 'port-forwarding' in opts.split(','), 'restrict で全機能を止め、port-forwarding だけ許可します。')
    for ip in (ctx.data['ip1'], ctx.data['ip2']):
        ctx.require(f'permitopen="{ip}:22"' in opts, f'permitopen="{ip}:22" がありません。')


SOL3 = """cat > ssh_config <<'EOF'
Host bastion
    HostName bastion.<<dom>>
    User jump
    Port <<bp>>
Host app-* db-*
    ProxyJump bastion
    User deploy
Host *
    ServerAliveInterval 30
EOF
printf 'restrict,port-forwarding,permitopen="%s:22",permitopen="%s:22" %s\\n' <<ip1>> <<ip2>> "$(cat jump.pub)" > bastion_authorized_keys"""
mission(3, 'ProxyJumpと踏み台サーバ運用（ssh -J・踏み台は中継専用に絞る）',
        '内部サーバーには踏み台（bastion）経由でしか入れません。毎回 ssh -J jump@bastion:ポート 内部ホスト と打つ代わりに ProxyJump を設定し、踏み台側の authorized_keys は中継（permitopen）だけ許す運用にします。scp や rsync でも -J や ProxyJump がそのまま使えます。',
        ['ProxyJump を設定し bastion 自身はループさせない', 'bastion_authorized_keys に restrict,port-forwarding,permitopen を設定'], s3, c3, SOL3,
        ["printf 'Host *\\n    ProxyJump bastion\\n' > ssh_config", "echo \"$(cat jump.pub)\" > bastion_authorized_keys"],
        'ProxyJump（-J）は踏み台に接続してそこから目的地へ中継する方式で、秘密鍵を踏み台に置かずに済みます（ForwardAgent より安全）。Host bastion を先に書いて ProxyJump を継承させない点が重要です。踏み台の authorized_keys は restrict で既定の機能をすべて止め、port-forwarding と permitopen で許可先だけ通します。踏み台の操作ログは監査に使えます。',
        '踏み台自身の設定を先に書かないと自分自身を経由してしまいます。', 'Host bastion を先に、続けて Host app-* db-* に ProxyJump bastion を書きます。')


# ================================================================ 4
def s4(ctx):
    pm, si = 5 + secrets.randbelow(25), 15 * (1 + secrets.randbelow(6))
    ctx.data.update(pm=pm, si=si)
    put(ctx, 'ssh_config.orig', '# 同じ踏み台へ何度も接続するので毎回の認証が遅い。無通信でNATに切られる\nHost *\n    User ops\n')
    ctx.write('ssh_config', ctx.read('ssh_config.orig'))
    ctx.write('requirements.txt', f'全ホストで ControlMaster auto・ControlPath ~/.ssh/cm/%C・ControlPersist {pm}m（最後の接続から{pm}分保持）・ServerAliveInterval {si}・ServerAliveCountMax 3 を有効にする。ただし ci-* は毎回新規接続したいので ControlMaster を no にする。ssh -G で検証される。\n')


def c4(ctx):
    need_ro(ctx)
    d = ctx.data
    for h in ('web01', 'db01'):
        r = ssh_g(ctx, 'ssh_config', h)
        want(ctx, r, 'controlmaster', 'auto', h)
        ctx.require('cm' in first(r, 'controlpath', '') and first(r, 'controlpath') != 'none', 'ControlPath を ~/.ssh/cm/%C のように設定します。')
        ctx.require(secs(first(r, 'controlpersist', '')) == d['pm'] * 60, f'ControlPersist は {d["pm"]}分（{d["pm"] * 60}秒）です。')
        want(ctx, r, 'serveraliveinterval', d['si'], h)
        want(ctx, r, 'serveralivecountmax', 3, h)
    ci = ssh_g(ctx, 'ssh_config', 'ci-7')
    ctx.require(first(ci, 'controlmaster') in ('false', 'no'), 'ci-* は ControlMaster no にします（先に書く）。')
    ctx.require(first(ssh_g(ctx, 'ssh_config', 'ci-7'), 'serveraliveinterval') == str(d['si']), 'ci-* でも ServerAliveInterval は共通設定を使います。')


SOL4 = """cat > ssh_config <<'EOF'
Host ci-*
    ControlMaster no
Host *
    User ops
    ControlMaster auto
    ControlPath ~/.ssh/cm/%C
    ControlPersist <<pm>>m
    ServerAliveInterval <<si>>
    ServerAliveCountMax 3
EOF"""
mission(4, 'ControlMaster/ControlPersistとServerAliveIntervalで接続を速く保つ',
        '同じサーバーへ何度も ssh/scp すると毎回認証が走って遅く、無通信でファイアウォールに切られることもあります。ControlMaster と ControlPersist で接続を多重化・保持し、ServerAliveInterval で生存確認を送りましょう。多重化の確認は ssh -O check、終了は ssh -O exit です。',
        ['共通設定を Host * に書く', 'ci-* だけ ControlMaster no の例外にする'], s4, c4, SOL4,
        ["printf 'Host *\\n    ControlMaster auto\\n' > ssh_config", "printf 'Host *\\n    ControlMaster auto\\n    ControlPersist <<pm>>\\n    ServerAliveInterval <<si>>\\n' > ssh_config"],
        'ControlMaster auto は最初の接続がマスターになりソケット（ControlPath）経由で後続が相乗りします。ControlPersist 10m のように指定するとマスターが最後の接続後も一定時間バックグラウンドに残ります。ControlPath は長さ制限があるので %C（ハッシュ）が安全です。ServerAliveInterval 秒ごとに応答確認し、ServerAliveCountMax 回無応答で切断します。例外（ci-*）は先に書きます。',
        '例外は先に、共通は Host * に書きます。', 'ControlMaster・ControlPath・ControlPersist・ServerAliveInterval・ServerAliveCountMax をまとめて指定します。')


# ================================================================ 5 ssh-keygen 種類
def s5(ctx):
    tag = rnd(4).lower()
    ctx.data.update(tag=tag, c1=f'trainee@laptop-{tag}', c2=f'legacy-{tag}')
    ctx.mkdir('keys')
    ctx.write('requirements.txt', f'keys/ に次の2本をパスフレーズなし（検証用）で作る。(1) ed25519: keys/id_ed25519_{tag}（コメント trainee@laptop-{tag}）(2) RSA 4096bit: keys/id_rsa_{tag}（コメント legacy-{tag}）。' + ('' if KG else ' ※ssh-keygenがない環境なので、使うコマンドを cmd.txt に2行で書く。') + '\n')


def c5(ctx):
    d = ctx.data
    if not KG:
        t = ctx.need_file('cmd.txt')
        ctx.require('-t ed25519' in t and '-t rsa' in t and '-b 4096' in t, 'cmd.txt に -t ed25519 と -t rsa -b 4096 を含めます。')
        return
    for name, bits, kind, com in ((f'id_ed25519_{d["tag"]}', '256', 'ED25519', d['c1']), (f'id_rsa_{d["tag"]}', '4096', 'RSA', d['c2'])):
        ctx.require(ctx.exists(f'keys/{name}') and ctx.exists(f'keys/{name}.pub'), f'keys/{name} と .pub が必要です。')
        r = kgrun(['-l', '-f', str(ctx.p(f'keys/{name}.pub'))])
        ctx.require(r and r.returncode == 0, f'keys/{name}.pub を読めません。')
        f = r.stdout.split()
        ctx.require(f[0] == bits and f[-1] == f'({kind})', f'{name} は {kind} {bits} である必要があります（ssh-keygen -l の結果: {r.stdout.strip()}）。')
        ctx.require(com in r.stdout, f'コメントは {com} にします（-C）。')
        ctx.require(ctx.mode(f'keys/{name}') == 0o600, '秘密鍵のパーミッションは 600 です。')
        r2 = kgrun(['-y', '-P', '', '-f', str(ctx.p(f'keys/{name}'))])
        ctx.require(r2 and r2.returncode == 0, 'パスフレーズなしの鍵として作ってください（-N ""）。')


SOL5 = """ssh-keygen -q -t ed25519 -C '<<c1>>' -N '' -f keys/id_ed25519_<<tag>>
ssh-keygen -q -t rsa -b 4096 -C '<<c2>>' -N '' -f keys/id_rsa_<<tag>>"""
mission(5, 'ssh-keygenの鍵の種類（ed25519とrsa）を使い分けて作る',
        '新しい端末用の鍵を作ります。今の標準は ed25519（短く高速で安全）、古い機器向けには RSA 4096bit も必要です。ssh-keygen -t で種類、-b でビット数、-C でコメント、-f で出力先、-N でパスフレーズを指定します。',
        ['ed25519 鍵を作る', 'RSA 4096bit 鍵を作る'], s5, c5, SOL5,
        ["ssh-keygen -q -t ed25519 -N '' -f keys/id_ed25519_<<tag>>\nssh-keygen -q -t rsa -N '' -f keys/id_rsa_<<tag>>", "ssh-keygen -q -t rsa -b 4096 -N '' -C '<<c1>>' -f keys/id_ed25519_<<tag>>"],
        'ed25519 は固定長（256bit）で鍵が小さく署名が速い現在の推奨です。RSA は互換性のため残し、3072bit以上（実務では4096）を使います。-C はコメント（誰の鍵かの識別）、-f は出力ファイル、-N は新しいパスフレーズ（本番では必ず設定し ssh-agent で運用）。秘密鍵は 600、公開鍵は .pub で配布します。',
        '種類は -t、RSAのビット数は -b です。', 'ssh-keygen -t ed25519 -C コメント -f 出力先 を2種類分実行します。')


# ================================================================ 6 -p -l -y
def s6(ctx):
    old, new = 'old-' + rnd(6), 'new-' + rnd(6)
    ctx.data.update(old=old, new=new)
    ctx.mkdir('keys')
    if KG:
        kgrun(['-q', '-t', 'ed25519', '-N', old, '-C', 'work', '-f', str(ctx.p('keys/id_work'))])
        ctx.p('keys/id_work.pub').unlink(missing_ok=True)
    ctx.write('requirements.txt', f'keys/id_work のパスフレーズを {old} から {new} へ変更し（ssh-keygen -p）、鍵のフィンガープリントを fingerprint.txt に保存（-l）、失われた公開鍵 keys/id_work.pub を秘密鍵から復元（-y）する。' + ('' if KG else ' ※ssh-keygenがない環境なので、3つのコマンドを cmd.txt に書く。') + '\n')


def c6(ctx):
    d = ctx.data
    if not KG:
        t = ctx.need_file('cmd.txt')
        ctx.require(all(x in t for x in ('-p', '-l', '-y')), 'cmd.txt に -p・-l・-y の3つのコマンドを書きます。')
        return
    k = str(ctx.p('keys/id_work'))
    r = kgrun(['-y', '-P', d['new'], '-f', k])
    ctx.require(r and r.returncode == 0, 'パスフレーズが新しい値になっていません（ssh-keygen -p -P 旧 -N 新）。')
    ctx.require(kgrun(['-y', '-P', d['old'], '-f', k]).returncode != 0, '旧パスフレーズがまだ有効です。')
    pub = ctx.need_file('keys/id_work.pub').split()
    ctx.require(pub[:2] == r.stdout.split()[:2], 'keys/id_work.pub が秘密鍵（-y）の出力と一致しません。')
    fp = kgrun(['-l', '-f', str(ctx.p('keys/id_work.pub'))]).stdout.split()[1]
    ctx.require(fp in ctx.need_file('fingerprint.txt'), 'fingerprint.txt に ssh-keygen -l の SHA256 フィンガープリントがありません。')


SOL6 = """ssh-keygen -p -P '<<old>>' -N '<<new>>' -f keys/id_work
ssh-keygen -l -f keys/id_work > fingerprint.txt
ssh-keygen -y -P '<<new>>' -f keys/id_work > keys/id_work.pub"""
mission(6, 'ssh-keygenで鍵のパスフレーズ変更(-p)・フィンガープリント確認(-l)・公開鍵の抽出(-y)',
        '担当者が代わるので鍵のパスフレーズを変更し、鍵の識別に使うフィンガープリントを記録します。さらに公開鍵ファイルを紛失したので秘密鍵から取り出します。それぞれ ssh-keygen の -p、-l、-y です。',
        ['-p で旧→新パスフレーズに変更', '-l のフィンガープリントを保存', '-y で公開鍵を復元'], s6, c6, SOL6,
        ["ssh-keygen -p -N '<<new>>' -f keys/id_work </dev/null", "ssh-keygen -p -P '<<old>>' -N '<<new>>' -f keys/id_work\nssh-keygen -y -P '<<new>>' -f keys/id_work > fingerprint.txt"],
        '-p は秘密鍵のパスフレーズ変更（-P 旧・-N 新で非対話）、-l -f は鍵のフィンガープリント（SHA256）表示で、サーバー側の鍵と照合するのに使います。-y は秘密鍵から公開鍵を再生成します。パスフレーズ付きの秘密鍵は漏洩しても直ちに使われません。コマンドラインのパスフレーズは履歴に残るので本番では対話入力にします。',
        '3つとも ssh-keygen のオプションです。', 'ssh-keygen -p ... / -l -f ... / -y ... を順に実行します。')


# ================================================================ 7 authorized_keys オプション
def _split_opts(s):
    return re.findall(r'(?:[^,"]|"[^"]*")+', s)


def s7(ctx):
    cidr = f'10.{secrets.randbelow(200)}.0.0/16'
    script = f'/usr/local/bin/backup-{rnd(3).lower()}.sh'
    ctx.data.update(cidr=cidr, script=script)
    put(ctx, 'backup.pub', fakepub() + ' backup@batch\n')
    put(ctx, 'legacy.pub', fakepub() + ' ops@legacy\n')
    ctx.write('requirements.txt', f'authorized_keys を作る。(1) backup.pub: command="{script}"・from="{cidr}"・restrict（コマンドは固定、接続元を制限）。(2) legacy.pub（古いsshdで restrict が使えない）: no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty を明示。鍵本体は変更しない。\n')


def c7(ctx):
    need_ro(ctx)
    ls = [x for x in ctx.need_file('authorized_keys').splitlines() if x.strip() and not x.startswith('#')]
    ctx.require(len(ls) == 2, '鍵ごとに1行、合計2行です。')
    byk = {}
    for ln in ls:
        m = re.match(r'^(.*?)\s*(ssh-ed25519 \S+)(?: .*)?$', ln)
        ctx.require(m, '行の形式が不正です（オプション 鍵種別 鍵 コメント）。')
        byk[m.group(2).split()[1]] = _split_opts(m.group(1)) if m.group(1) else []
    bk, lk = ctx.read('backup.pub').split()[1], ctx.read('legacy.pub').split()[1]
    ctx.require(bk in byk and lk in byk, '両方の鍵を（鍵本体を変えずに）含めます。')
    o = byk[bk]
    ctx.require(f'command="{ctx.data["script"]}"' in o, 'backup 鍵に command="…" を付けます。')
    ctx.require(f'from="{ctx.data["cidr"]}"' in o, 'backup 鍵に from="…" を付けます。')
    ctx.require('restrict' in o, 'backup 鍵に restrict を付けます。')
    for w in ('no-port-forwarding', 'no-agent-forwarding', 'no-X11-forwarding', 'no-pty'):
        ctx.require(w in byk[lk], f'legacy 鍵に {w} を付けます。')


SOL7 = """printf 'command="%s",from="%s",restrict %s\\n' '<<script>>' '<<cidr>>' "$(cat backup.pub)" > authorized_keys
printf 'no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s\\n' "$(cat legacy.pub)" >> authorized_keys"""
mission(7, 'authorized_keysのオプション（command= from= no-port-forwarding restrict）で鍵を縛る',
        '自動バックアップ用の鍵が漏れても被害を最小にするため、authorized_keys の各行に鍵の使い道を制限するオプションを付けます。command= で実行コマンドを固定、from= で接続元を制限、restrict でポート転送・エージェント・pty などをまとめて禁止します。',
        ['backup 鍵に command=・from=・restrict', 'legacy 鍵に個別の no-* オプション'], s7, c7, SOL7,
        ["cat backup.pub legacy.pub > authorized_keys", "printf 'command=\"<<script>>\" %s\\n' \"$(cat backup.pub)\" > authorized_keys\ncat legacy.pub >> authorized_keys"],
        'オプションは行頭にカンマ区切りで書き、値は二重引用符で囲みます。command= は鍵で認証されると指定コマンドしか実行できず（元の指定は SSH_ORIGINAL_COMMAND に入る）、from= は接続元アドレス/CIDR/ホスト名を絞ります。restrict は no-port-forwarding・no-agent-forwarding・no-X11-forwarding・no-pty・no-user-rc をまとめて有効にし、必要なものだけ後から許可します（OpenSSH 7.2以降）。',
        'オプションは鍵の種別（ssh-ed25519）の手前に置きます。', 'printf で オプション + 鍵本体 の1行を組み立てます。')


# ================================================================ 8 ssh-copy-id
def s8(ctx):
    user, host, port = 'deploy', f'app{secrets.randbelow(90) + 10}.example.test', 2200 + secrets.randbelow(500)
    ctx.data.update(user=user, host=host, port=port)
    put(ctx, 'keys/id_ci.pub', fakepub() + ' ci@runner\n')
    ex = fakepub() + ' alice@existing'
    ctx.data['existing'] = ex
    put(ctx, 'remote_home/.ssh/authorized_keys', ex + '\n')
    os.chmod(ctx.p('remote_home/.ssh/authorized_keys'), 0o644)
    ctx.mkdir('remote_home/.ssh', 0o755)
    ctx.write('requirements.txt', f'(1) copy.txt に、ポート{port}の {user}@{host} へ keys/id_ci.pub を登録する ssh-copy-id を1行で書く（実行しない）。(2) ssh-copy-id が使えない場合の手作業として、同じ鍵を remote_home/.ssh/authorized_keys（既存の鍵は残す・重複させない）へ追加し、.ssh は 700、authorized_keys は 600 にする。\n')


def c8(ctx):
    need_ro(ctx.__class__ and ctx) if False else None
    d = ctx.data
    t = toks(ctx, one_line(ctx, 'copy.txt'))
    ctx.require(t[0] == 'ssh-copy-id', 'copy.txt は ssh-copy-id です。')
    ctx.require('-i' in t and t[t.index('-i') + 1] == 'keys/id_ci.pub', '-i で公開鍵 keys/id_ci.pub を指定します。')
    ctx.require('-p' in t and t[t.index('-p') + 1] == str(d['port']), f'-p {d["port"]} でポートを指定します。')
    ctx.require(t[-1] == f'{d["user"]}@{d["host"]}', '最後に ユーザー@ホスト を置きます。')
    ls = ctx.need_file('remote_home/.ssh/authorized_keys').splitlines()
    ctx.require(d['existing'] in ls, '既存の鍵を消してはいけません（>> で追記）。')
    ctx.require(ls.count(ctx.read('keys/id_ci.pub').strip()) == 1, 'id_ci の鍵が1回だけ登録されている必要があります。')
    ctx.require(ctx.mode('remote_home/.ssh') == 0o700, '.ssh は 700 にします。')
    ctx.require(ctx.mode('remote_home/.ssh/authorized_keys') == 0o600, 'authorized_keys は 600 にします。')
    ctx.require(sha(ctx.read('keys/id_ci.pub')) == ctx.data['ro']['keys/id_ci.pub'], '公開鍵は変更しません。')


SOL8 = """echo "ssh-copy-id -i keys/id_ci.pub -p <<port>> <<user>>@<<host>>" > copy.txt
cat keys/id_ci.pub >> remote_home/.ssh/authorized_keys
chmod 700 remote_home/.ssh
chmod 600 remote_home/.ssh/authorized_keys"""
mission(8, 'ssh-copy-idで公開鍵を登録し、使えない時の手作業も知る',
        '新しいCI用の公開鍵をサーバーに登録します。通常は ssh-copy-id で安全に追記できますが、使えない環境では authorized_keys への追記と権限設定を手でやります。ここでは実際の接続はせず、コマンドの組み立てと、サンドボックス内の疑似ホームでの手作業を練習します。',
        ['ssh-copy-id のコマンドを copy.txt へ', '疑似ホームに追記し権限を設定'], s8, c8, SOL8,
        ["echo \"ssh-copy-id keys/id_ci.pub <<user>>@<<host>>\" > copy.txt\ncp keys/id_ci.pub remote_home/.ssh/authorized_keys", "echo \"ssh-copy-id -i keys/id_ci.pub -p <<port>> <<user>>@<<host>>\" > copy.txt\ncat keys/id_ci.pub >> remote_home/.ssh/authorized_keys"],
        'ssh-copy-id -i 公開鍵 [-p ポート] ユーザー@ホスト は、対象の ~/.ssh を作成して authorized_keys に追記し、権限（.ssh 700・authorized_keys 600）も整えます。重複登録はスキップされます。手作業では必ず > ではなく >> で追記します（既存の鍵が消えてログインできなくなる事故を防ぐ）。-i は公開鍵（または秘密鍵）、-o で ssh オプションも渡せます。',
        'ssh-copy-id は -i と -p を取ります。', '手作業は cat 公開鍵 >> authorized_keys と chmod 700/600 です。')


# ================================================================ 9 SSH 証明書
VALS = [('+4h', 14400), ('+1d', 86400), ('+2d', 172800), ('+1w', 604800)]


def s9(ctx):
    kid = f'user-{rnd(4).lower()}'
    pr = secrets.choice([['alice', 'deploy'], ['bob', 'dbadmin'], ['carol', 'ops', 'deploy']])
    val = secrets.choice(VALS)
    ctx.data.update(kid=kid, princ=','.join(pr), val=val[0], valsec=val[1])
    ctx.mkdir('keys')
    if KG:
        kgrun(['-q', '-t', 'ed25519', '-N', '', '-C', 'ca', '-f', str(ctx.p('keys/ca'))])
        kgrun(['-q', '-t', 'ed25519', '-N', '', '-C', 'user', '-f', str(ctx.p('keys/user_key'))])
    ctx.write('requirements.txt', f'CA鍵 keys/ca で keys/user_key.pub に署名して証明書を発行する（ssh-keygen -s）。Key ID は {kid}、プリンシパルは {",".join(pr)}、有効期間は {val[0]}。さらにサーバー側で CA を信頼する行を sshd_ca.conf に1行書く（CA公開鍵のパスは /etc/ssh/ca.pub）。' + ('' if KG else ' ※ssh-keygenがない環境なので、署名コマンドを cmd.txt に書く。') + '\n')


def c9(ctx):
    d = ctx.data
    ctx.require(re.search(r'(?m)^\s*TrustedUserCAKeys\s+/etc/ssh/ca\.pub\s*$', ctx.need_file('sshd_ca.conf')), 'sshd_ca.conf に TrustedUserCAKeys /etc/ssh/ca.pub を書きます。')
    if not KG:
        t = ctx.need_file('cmd.txt')
        ctx.require(all(x in t for x in ('-s', '-I', '-n', '-V')), 'cmd.txt に -s -I -n -V を含めます。')
        return
    ctx.require(ctx.exists('keys/user_key-cert.pub'), 'keys/user_key-cert.pub（証明書）がありません。')
    r = kgrun(['-L', '-f', str(ctx.p('keys/user_key-cert.pub'))])
    ctx.require(r and r.returncode == 0, '証明書を読めません。')
    out = r.stdout
    ctx.require(f'Key ID: "{d["kid"]}"' in out, f'Key ID は {d["kid"]} です（-I）。')
    pr = re.split(r'Principals:\s*\n', out)[-1].split('Critical')[0].split() if 'Principals:' in out else []
    ctx.require(pr == d['princ'].split(','), f'プリンシパルは {d["princ"]} です（-n）。')
    m = re.search(r'Valid: from (\S+) to (\S+)', out)
    ctx.require(m, '有効期間が設定されていません（-V）。')
    f = '%Y-%m-%dT%H:%M:%S'
    ctx.require(abs((datetime.strptime(m.group(2), f) - datetime.strptime(m.group(1), f)).total_seconds() - d['valsec']) < 300, f'有効期間は {d["val"]} です。')
    ca = kgrun(['-l', '-f', str(ctx.p('keys/ca.pub'))]).stdout.split()[1]
    ctx.require(ca in out, '署名者が keys/ca ではありません（-s）。')


SOL9 = """ssh-keygen -s keys/ca -I '<<kid>>' -n '<<princ>>' -V '<<val>>' keys/user_key.pub
echo 'TrustedUserCAKeys /etc/ssh/ca.pub' > sshd_ca.conf"""
mission(9, 'SSH証明書認証（ssh-keygen -s でCA署名し、サーバーはCAを信頼する）',
        '社員が増えるたびに全サーバーの authorized_keys を更新するのは大変です。CA（認証局）鍵で利用者の公開鍵に有効期限付きの証明書を署名し、サーバーはCAだけを信頼する方式にします。署名は ssh-keygen -s、内容確認は ssh-keygen -L です。',
        ['-s -I -n -V で証明書を発行', 'TrustedUserCAKeys の行を sshd_ca.conf へ'], s9, c9, SOL9,
        ["ssh-keygen -s keys/ca -I '<<kid>>' keys/user_key.pub\necho 'TrustedUserCAKeys /etc/ssh/ca.pub' > sshd_ca.conf", "ssh-keygen -s keys/user_key -I '<<kid>>' -n '<<princ>>' -V '<<val>>' keys/ca.pub\necho 'TrustedUserCAKeys /etc/ssh/ca.pub' > sshd_ca.conf"],
        'ssh-keygen -s CA秘密鍵 -I 識別名 -n プリンシパル -V 有効期間 利用者公開鍵 で *-cert.pub が作られます。-n はログインを許す名前（sshd 側の AuthorizedPrincipalsFile や対象ユーザー名と照合）、-V +4h のような短い期限が運用の肝で、失効管理が楽になります。サーバーは sshd_config に TrustedUserCAKeys を書くだけで、利用者側は ssh -i 鍵 で同名の -cert.pub を自動的に使います。ssh-keygen -L -f で内容を確認します。',
        '署名するのはCAの秘密鍵、署名される対象は利用者の公開鍵です。', 'ssh-keygen -s keys/ca -I ID -n 名前 -V +期間 keys/user_key.pub です。')


# ================================================================ 10 権限
def s10(ctx):
    u = 'home/trainee'
    ctx.mkdir(u, 0o775)
    ctx.mkdir(u + '/.ssh', 0o777)
    key = '-----BEGIN OPENSSH PRIVATE KEY-----\n' + rnd(60) + '\n-----END OPENSSH PRIVATE KEY-----\n'
    for n, t, m in (('id_ed25519', key, 0o644), ('id_ed25519.pub', fakepub() + ' me\n', 0o644), ('authorized_keys', fakepub() + ' me\n', 0o666), ('config', 'Host *\n    ServerAliveInterval 30\n', 0o664)):
        put(ctx, f'{u}/.ssh/{n}', t)
        os.chmod(ctx.p(f'{u}/.ssh/{n}'), m)
    put(ctx, 'ssh_debug.txt', "debug1: identity file /home/trainee/.ssh/id_ed25519 type 3\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @\nPermissions 0644 for '/home/trainee/.ssh/id_ed25519' are too open.\nThis private key will be ignored.\nLoad key \"/home/trainee/.ssh/id_ed25519\": bad permissions\n")
    put(ctx, 'sshd_auth.log', "Nov 21 10:02:11 web01 sshd[2211]: Authentication refused: bad ownership or modes for directory /home/trainee/.ssh\nNov 21 10:02:11 web01 sshd[2211]: Authentication refused: bad ownership or modes for file /home/trainee/.ssh/authorized_keys\n")
    ctx.write('requirements.txt', 'home/trainee を疑似ホームとして、ssh_debug.txt（クライアント）と sshd_auth.log（サーバー）のエラーが出なくなるよう権限を直す: ~/.ssh は 700、秘密鍵と config と authorized_keys は 600、ホームは他人が書き込めない状態に。中身は変更しない。\n')


def c10(ctx):
    need_ro(ctx)
    u = 'home/trainee'
    ctx.require(ctx.mode(u + '/.ssh') == 0o700, '~/.ssh は 700 にします。')
    ctx.require(ctx.mode(u + '/.ssh/id_ed25519') == 0o600, '秘密鍵は 600 にします（"too open" の原因）。')
    ctx.require(ctx.mode(u + '/.ssh/authorized_keys') == 0o600, 'authorized_keys は 600（"bad ownership or modes"）。')
    ctx.require(ctx.mode(u + '/.ssh/config') == 0o600, 'config は 600 にします。')
    ctx.require(ctx.mode(u + '/.ssh/id_ed25519.pub') & 0o022 == 0, '公開鍵も他人が書き込めない状態にします。')
    ctx.require(ctx.mode(u) & 0o022 == 0, 'ホームディレクトリが group/other に書き込み可能だと sshd(StrictModes) が拒否します。')


SOL10 = """chmod go-w home/trainee
chmod 700 home/trainee/.ssh
chmod 600 home/trainee/.ssh/id_ed25519 home/trainee/.ssh/authorized_keys home/trainee/.ssh/config"""
mission(10, '~/.sshは700・鍵は600: 権限エラー（too open・bad ownership）の診断と修正',
        '鍵認証がなぜか通りません。クライアントの ssh_debug.txt には "UNPROTECTED PRIVATE KEY FILE"、サーバー側の sshd_auth.log には "bad ownership or modes" があります。メッセージから原因を読み、疑似ホームの権限を直してください。',
        ['2つのログから原因を特定', 'ホーム・.ssh・鍵・authorized_keys・config の権限を修正'], s10, c10, SOL10,
        ["chmod -R 600 home/trainee/.ssh", "chmod 600 home/trainee/.ssh/id_ed25519"],
        '秘密鍵が他人に読めると ssh はその鍵を無視します（クライアント側）。サーバーは StrictModes yes で、ホーム・~/.ssh・authorized_keys が他人に書き込み可能だと鍵を拒否します。目安は ~/.ssh が700、秘密鍵・config・authorized_keys が600、ホームは755以下（group/other 書き込み不可）です。chmod -R 600 は ディレクトリの実行権を奪うので不可です。',
        'ログに出ている3種類の対象を整理しましょう。', 'ディレクトリは700、ファイルは600。ホームは go-w です。')


# ================================================================ 11 -vvv ログ
def s11(ctx):
    kind = secrets.choice(['key_not_authorized', 'identity_file_missing', 'permissions_too_open', 'too_many_auth_failures'])
    host, user = '10.0.0.' + str(10 + secrets.randbelow(200)), 'deploy'
    head = f"OpenSSH_9.6p1, OpenSSL 3.0.13\ndebug1: Reading configuration data /home/trainee/.ssh/config\ndebug1: Connecting to {host} [{host}] port 22.\ndebug1: Connection established.\ndebug1: Authenticating to {host}:22 as '{user}'\n"
    fp = fp_of(rnd())
    if kind == 'key_not_authorized':
        ev = fp
        body = f"debug1: Will attempt key: /home/trainee/.ssh/id_ed25519 ED25519 {fp} explicit\ndebug1: Authentications that can continue: publickey\ndebug1: Next authentication method: publickey\ndebug1: Offering public key: /home/trainee/.ssh/id_ed25519 ED25519 {fp} explicit\ndebug3: receive packet: type 51\ndebug1: Authentications that can continue: publickey\ndebug1: No more authentication methods to try.\n{user}@{host}: Permission denied (publickey).\n"
    elif kind == 'identity_file_missing':
        ev = '/home/trainee/.ssh/id_deploy'
        body = f"debug1: identity file {ev} type -1\ndebug3: no such identity: {ev}: No such file or directory\ndebug1: Authentications that can continue: publickey\ndebug1: No more authentication methods to try.\n{user}@{host}: Permission denied (publickey).\n"
    elif kind == 'permissions_too_open':
        ev = '0644'
        body = f"@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @\nPermissions {ev} for '/home/trainee/.ssh/id_ed25519' are too open.\nThis private key will be ignored.\ndebug1: No more authentication methods to try.\n{user}@{host}: Permission denied (publickey).\n"
    else:
        n = 5 + secrets.randbelow(3)
        ev = str(n)
        body = ''.join(f"debug1: Offering public key: agent-key-{i} RSA {fp_of(rnd())} agent\ndebug1: Authentications that can continue: publickey\n" for i in range(n))
        body += f"Received disconnect from {host} port 22:2: Too many authentication failures\nDisconnected from {host} port 22\n"
    ctx.data.update(cause=kind, evidence=ev)
    put(ctx, 'ssh_vvv.log', head + body)
    ctx.write('requirements.txt', 'ssh -vvv の ssh_vvv.log を読み、diagnosis.json に {"cause": 原因, "evidence": 根拠} を書く。cause は key_not_authorized（鍵は提示されたが拒否）/ identity_file_missing（指定の鍵ファイルが無い）/ permissions_too_open（鍵の権限）/ too_many_auth_failures（鍵の提示過多）のいずれか。evidence は 提示された鍵のフィンガープリント / 無い鍵のパス / 問題の権限値 / 提示された鍵の本数 のどれか該当するものを文字列で。\n')


def c11(ctx):
    need_ro(ctx)
    j = rj(ctx, 'diagnosis.json')
    ctx.require(j.get('cause') == ctx.data['cause'], 'cause が違います。"Offering public key" や "Permissions" などの行の流れを追いましょう。')
    ctx.require(str(j.get('evidence')) == ctx.data['evidence'], 'evidence（根拠）がログの記述と一致しません。')


SOL11 = """echo '{"cause": "<<cause>>", "evidence": "<<evidence>>"}' > diagnosis.json"""
mission(11, 'ssh -v/-vvvのログを読んでPermission denied (publickey)の原因を切り分ける',
        '"Permission denied (publickey)" だけでは原因が分かりません。ssh -v（詳細度は -vv、-vvv の順に増える）のログで、鍵が提示されたか、サーバーが拒否したか、そもそも読み込めなかったかを追います。',
        ['ssh_vvv.log から原因を判定', 'diagnosis.json に cause と evidence を保存'], s11, c11, SOL11,
        ['echo \'{"cause": "key_not_authorized", "evidence": "none"}\' > diagnosis.json', 'echo \'{"cause": "too_many_auth_failures", "evidence": "1"}\' > diagnosis.json'],
        '"Offering public key" の後に type 51（SSH_MSG_USERAUTH_FAILURE）が返れば、鍵は提示されたがサーバーの authorized_keys にありません。"no such identity" は IdentityFile の指定違い、"UNPROTECTED PRIVATE KEY FILE" は権限、"Too many authentication failures" はエージェントの鍵を順に出しすぎた場合で IdentitiesOnly yes と -i で解決します。サーバー側は sshd の auth.log（journalctl -u ssh）も合わせて見ます。',
        '提示（Offering）→拒否（receive packet: type 51）という流れの有無を見ます。', 'ログに出る Offering/no such identity/Permissions/Too many の行で場合分けします。')


# ================================================================ 12 scp/sftp/rsync
def s12(ctx):
    host, port, user = f'files{secrets.randbelow(80) + 10}.example.test', 2200 + secrets.randbelow(500), 'deploy'
    ctx.data.update(host=host, port=port, user=user)
    ctx.write('requirements.txt', f'{user}@{host}（ポート{port}）に対し、(1) copy.txt: report.csv 1個を /srv/in/ へ送る scp、(2) sync.txt: ローカル site/ を /var/www/site/ へ差分同期する rsync（-a を使い、ssh のポートを -e で渡す。site/ は末尾スラッシュ）、(3) get.txt: 対話で中を見て回れる sftp 接続、をそれぞれ1行で書く。さらに plan.json に {{"single_small_file": ?, "large_dir_resume_diff": ?, "interactive_browse": ?}} を scp/rsync/sftp のいずれかで書く。\n')


def c12(ctx):
    d = ctx.data
    t = toks(ctx, one_line(ctx, 'copy.txt'))
    ctx.require(t[0] == 'scp' and '-P' in t and t[t.index('-P') + 1] == str(d['port']), 'scp のポート指定は大文字の -P です。')
    ctx.require('report.csv' in t and t[-1].startswith(f'{d["user"]}@{d["host"]}:/srv/in'), 'scp report.csv ユーザー@ホスト:/srv/in/ の形にします。')
    t = toks(ctx, one_line(ctx, 'sync.txt'))
    ctx.require(t[0] == 'rsync' and any(x.startswith('-a') or x == '-az' for x in t), 'rsync -a を使います。')
    ctx.require('-e' in t and 'ssh' in t[t.index('-e') + 1] and f'-p {d["port"]}' in t[t.index('-e') + 1], f'-e "ssh -p {d["port"]}" で ssh を指定します（rsync のポートは -e 経由）。')
    ctx.require('site/' in t and t[-1].startswith(f'{d["user"]}@{d["host"]}:/var/www/site/'), 'site/ を ユーザー@ホスト:/var/www/site/ へ。')
    t = toks(ctx, one_line(ctx, 'get.txt'))
    ctx.require(t[0] == 'sftp' and '-P' in t and t[t.index('-P') + 1] == str(d['port']) and t[-1] == f'{d["user"]}@{d["host"]}', 'sftp -P ポート ユーザー@ホスト です。')
    j = rj(ctx, 'plan.json')
    ctx.require(j == {'single_small_file': 'scp', 'large_dir_resume_diff': 'rsync', 'interactive_browse': 'sftp'}, 'plan.json の使い分けが違います（単発=scp、差分・再開=rsync、対話=sftp）。')


SOL12 = """echo "scp -P <<port>> report.csv <<user>>@<<host>>:/srv/in/" > copy.txt
echo "rsync -az -e 'ssh -p <<port>>' site/ <<user>>@<<host>>:/var/www/site/" > sync.txt
echo "sftp -P <<port>> <<user>>@<<host>>" > get.txt
echo '{"single_small_file": "scp", "large_dir_resume_diff": "rsync", "interactive_browse": "sftp"}' > plan.json"""
mission(12, 'scpとsftpとrsync -e sshの使い分け',
        'ファイル転送には scp・sftp・rsync -e ssh があり、ポートの指定方法も得意分野も違います。1ファイルを送る、大きなディレクトリを差分同期する、対話的に見て回る、の3場面に適した行を書きましょう。',
        ['3つの転送コマンドをファイルに記述', 'plan.json に使い分けを記録'], s12, c12, SOL12,
        ["echo \"scp -p <<port>> report.csv <<user>>@<<host>>:/srv/in/\" > copy.txt\necho \"rsync -a site <<user>>@<<host>>:/var/www/\" > sync.txt\necho \"sftp <<user>>@<<host>>\" > get.txt", "echo '{\"single_small_file\": \"rsync\", \"large_dir_resume_diff\": \"scp\", \"interactive_browse\": \"sftp\"}' > plan.json"],
        'scp は単発コピー（ポートは -P）、sftp は対話的な操作（ポートは -P）、rsync -e "ssh -p N" は差分転送・--partial での再開・--delete・--dry-run が使えます（ポートは ssh 側の -p を -e 経由で渡す点が違う）。site/ と site の末尾スラッシュで「中身」か「ディレクトリ自体」かが変わります。同期前に -n（--dry-run）で確認しましょう。',
        'scp と sftp は -P、ssh と rsync -e の中は -p です。', 'rsync は -e でラップした ssh にポートを渡します。')


# ================================================================ 13 sshfs
def s13(ctx):
    me = 'trainee'
    stale = f'/home/{me}/mnt/' + secrets.choice(['logs', 'data', 'backup'])
    other = f'/home/{me}/mnt/media'
    rs, ro_ = f'ops@files01:/srv/{rnd(4).lower()}', 'ops@files02:/exports/media'
    ctx.data.update(stale=stale, rs=rs, other=other)
    lines = ['sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)', 'tmpfs on /run type tmpfs (rw,nosuid,nodev,size=1618320k,mode=755)',
             f'{rs} on {stale} type fuse.sshfs (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000)',
             'nas01:/vol/share on /mnt/nas type nfs4 (rw,relatime,vers=4.2)',
             f'{ro_} on {other} type fuse.sshfs (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000)']
    put(ctx, 'mount.txt', '$ mount\n' + '\n'.join(lines) + '\n')
    put(ctx, 'ls_error.txt', f"$ ls {stale}\nls: cannot access '{stale}': Transport endpoint is not connected\n")
    ctx.write('requirements.txt', f'mount.txt と ls_error.txt を読み、(1) mounts.json に {{"sshfs_mounts": [fuse.sshfs のマウント先を昇順で]}}、(2) umount.txt に、固まった（切断された）マウントだけを外す fusermount -u の1行、(3) remount.txt に、同じ {rs} を同じ場所へ、切断後に自動再接続し無通信で切られない sshfs コマンド（-o reconnect,ServerAliveInterval=15）を1行で書く。\n')


def c13(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'mounts.json')
    ctx.require(j.get('sshfs_mounts') == sorted([d['stale'], d['other']]), 'sshfs_mounts は fuse.sshfs の行のマウント先だけ（nfs4 や tmpfs は除く）を昇順で。')
    t = toks(ctx, one_line(ctx, 'umount.txt'))
    ctx.require(t[0] in ('fusermount', 'fusermount3') and t[1] in ('-u', '-uz', '-zu') and t[-1] == d['stale'], 'fusermount -u 切断されたマウント先 です（他のマウントは外さない）。')
    t = toks(ctx, one_line(ctx, 'remount.txt'))
    ctx.require(t[0] == 'sshfs' and d['rs'] in t and d['stale'] in t, f'sshfs {d["rs"]} {d["stale"]} の形で再マウントします。')
    o = ','.join(t[i + 1] for i, x in enumerate(t) if x == '-o' and i + 1 < len(t))
    ctx.require('reconnect' in o.split(',') and 'ServerAliveInterval=15' in o.split(','), '-o reconnect,ServerAliveInterval=15 を付けます。')


SOL13 = """echo '{"sshfs_mounts": ["<<other>>", "<<stale>>"]}' | python3 -c 'import json,sys; d=json.load(sys.stdin); d["sshfs_mounts"].sort(); print(json.dumps(d))' > mounts.json
echo "fusermount -u <<stale>>" > umount.txt
echo "sshfs <<rs>> <<stale>> -o reconnect,ServerAliveInterval=15" > remount.txt"""
mission(13, 'sshfsのマウント出力を読み、固まったマウントを外して再マウントする',
        'リモートのディレクトリを sshfs でローカルにマウントして使っています。ノートPCのスリープ後に "Transport endpoint is not connected" となりました。mount の出力から fuse.sshfs だけを抜き出し、固まったものを fusermount -u で外して、自動再接続付きで再マウントします。',
        ['mounts.json に sshfs のマウント先一覧', 'fusermount -u と sshfs 再マウントを記述'], s13, c13, SOL13,
        ["grep sshfs mount.txt > mounts.json\necho \"umount -f /\" > umount.txt\necho \"sshfs <<rs>> <<stale>>\" > remount.txt", "echo \"fusermount -u <<other>>\" > umount.txt"],
        'mount の type 列が fuse.sshfs のものがsshfsです（他にnfs4やtmpfsが混じる）。sshfs 利用者 @ ホスト:パス マウント先 -o reconnect,ServerAliveInterval=15 で切断後の再接続と生存確認が有効になります。FUSE のマウントは一般ユーザーが fusermount -u（-z で遅延）で外せ、rootは不要です。大量ファイルのI/OはNFSやrsyncより遅いことがあります。',
        'type が fuse.sshfs の行だけを見ます。', 'fusermount -u と sshfs ... -o reconnect,ServerAliveInterval=15 です。')


# ================================================================ 14 mosh / autossh
def s14(ctx):
    host, port, mp = 'dev.example.test', 2200 + secrets.randbelow(500), 60001 + secrets.randbelow(900)
    ctx.data.update(host=host, port=port, mp=mp)
    ctx.write('requirements.txt', f'ユーザー trainee で {host}（sshはポート{port}）へ。(1) mosh.txt: モバイル回線で切れても使い続けたい。ssh のポートを --ssh で渡し、ファイアウォールが UDP {mp} だけ開けているので -p で固定する mosh の1行。(2) autossh.txt: 切れたら自動再接続したい。監視ポートを使わず（-M 0）ServerAliveInterval=15 と ServerAliveCountMax=3 を付け、接続後に tmux new -A -s main へ入る autossh の1行（-t で端末割り当て）。\n')


def c14(ctx):
    d = ctx.data
    t = toks(ctx, one_line(ctx, 'mosh.txt'))
    ctx.require(t[0] == 'mosh' and t[-1] == f'trainee@{d["host"]}', 'mosh ... trainee@ホスト の形です。')
    ctx.require(any(x == f'--ssh=ssh -p {d["port"]}' for x in t), f'--ssh="ssh -p {d["port"]}" で ssh のポートを渡します。')
    ctx.require('-p' in t and t[t.index('-p') + 1] == str(d['mp']), f'-p {d["mp"]} でUDPポートを固定します。')
    t = toks(ctx, one_line(ctx, 'autossh.txt'))
    ctx.require(t[0] == 'autossh' and '-M' in t and t[t.index('-M') + 1] == '0', 'autossh -M 0 にします。')
    s = ' '.join(t)
    ctx.require('ServerAliveInterval=15' in s and 'ServerAliveCountMax=3' in s and '-t' in t, '-o ServerAliveInterval=15 -o ServerAliveCountMax=3 と -t が必要です。')
    ctx.require(f'-p {d["port"]}' in s or f'-p{d["port"]}' in s, f'ssh のポート {d["port"]} を -p で渡します。')
    ctx.require(any('tmux new -A -s main' in x for x in t) and t[-2] == f'trainee@{d["host"]}', '最後に ホスト と tmux new -A -s main を置きます。')


SOL14 = """echo "mosh --ssh='ssh -p <<port>>' -p <<mp>> trainee@<<host>>" > mosh.txt
echo "autossh -M 0 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -p <<port>> -t trainee@<<host>> 'tmux new -A -s main'" > autossh.txt"""
mission(14, 'moshとautosshの用途（ローミング耐性と自動再接続）',
        'モバイル回線やスリープで ssh がすぐ切れて困っています。mosh は UDP を使った切断に強い対話シェル、autossh は ssh が切れたら再接続を繰り返す監視ツールです。それぞれの用途に合わせたコマンドを組み立ててください。',
        ['mosh のポート指定コマンド', 'autossh と tmux の組み合わせ'], s14, c14, SOL14,
        ["echo \"mosh trainee@<<host>>\" > mosh.txt\necho \"autossh trainee@<<host>>\" > autossh.txt", "echo \"mosh -p <<port>> trainee@<<host>>\" > mosh.txt\necho \"autossh -M 0 -p <<port>> trainee@<<host>> 'tmux new -A -s main'\" > autossh.txt"],
        'mosh は最初に ssh で認証して mosh-server を起動し、以後はUDP（既定 60000〜61000）で通信するためIP変更・スリープから復帰できますが、サーバー側にも mosh のインストールとUDP開放が必要です。-p でUDPポートを固定できます。autossh は -M 0 で監視用ポートを使わず ssh 自身の ServerAlive で切断を検知して再接続します。tmux new -A -s main は既存セッションがあれば attach、なければ新規作成です。',
        'moshはUDP、autosshは自動再接続です。', 'mosh --ssh="ssh -p ポート" -p UDPポート ホスト、autossh -M 0 -o ... です。')


# ================================================================ 15 リモート実行
def s15(ctx):
    host = 'prod' + str(secrets.randbelow(80) + 10)
    ctx.data['host'] = host
    ctx.mkdir('site'); ctx.write('site/index.html', 'hello\n'); ctx.write('data.txt', 'c\nb\na\n')
    ctx.write('requirements.txt', f'remote.sh に、{host} へ接続した次の3つの操作を書く（実行はしない）。(1) tar czf - で site を固めて標準出力へ流し、パイプで ssh のリモート側 tar xzf - -C /srv へ渡す。(2) ssh {host} \'sort\' < data.txt > sorted.txt のように、手元のdata.txtを標準入力としてリモートの sort に渡し結果を手元に保存。(3) ssh -T {host} に引用符付きヒアドキュメント（<<\'EOF\'）で複数行の命令を渡し、リモート側で $HOSTNAME を展開させる。\n')


def c15(ctx):
    h = ctx.data['host']
    t = ctx.need_file('remote.sh')
    ctx.require(re.search(r'tar\s+-?c\w*f\s+-\s+(-C\s+\S+\s+)?\S+\s*\|\s*ssh\s+(-\S+\s+)*' + h + r"\s+['\"]tar\s+-?x\w*f\s+-\s+-C\s+/srv", t), f'tar czf - ... | ssh {h} \'tar xzf - -C /srv\' の形にします。')
    ctx.require(re.search(r"ssh\s+(-\S+\s+)*" + h + r"\s+'sort'\s*<\s*data\.txt\s*>\s*sorted\.txt", t), f"ssh {h} 'sort' < data.txt > sorted.txt の形にします。")
    m = re.search(r"ssh\s+-T\s+" + h + r"\s+<<\s*'(\w+)'\s*\n(.*?)\n\1\s*$", t, re.S | re.M)
    ctx.require(m, f"ssh -T {h} <<'EOF' ... EOF のように区切りを引用符で囲むヒアドキュメントにします（ローカルで先に展開されないため）。")
    ctx.require('$HOSTNAME' in m.group(2), 'ヒアドキュメントの中でリモートの $HOSTNAME を使います。')


SOL15 = """cat > remote.sh <<'END'
tar czf - site | ssh <<host>> 'tar xzf - -C /srv'
ssh <<host>> 'sort' < data.txt > sorted.txt
ssh -T <<host>> <<'EOF'
echo "on $HOSTNAME"
uptime
EOF
END"""
mission(15, 'sshでのリモートコマンド実行・heredoc・パイプ・標準入力転送',
        'ssh は単なるログイン手段ではなく、リモートでコマンドを実行し、標準入出力をパイプでつなぐ道具です。tar をパイプで流し込む、手元のファイルをリモートのコマンドへ標準入力で渡す、ヒアドキュメントで複数行を実行する、の3つの書き方を整理します。',
        ['tar | ssh tar の転送', '標準入力転送', '引用符付き heredoc'], s15, c15, SOL15,
        ["echo \"scp -r site <<host>>:/srv\" > remote.sh", "cat > remote.sh <<'END'\ntar czf - site | ssh <<host>> 'tar xzf - -C /srv'\nssh <<host>> sort < data.txt > sorted.txt\nssh -T <<host>> <<EOF\necho $HOSTNAME\nEOF\nEND"],
        'ssh ホスト \'コマンド\' はリモートで実行して終了します。標準入力はそのままリモートコマンドに渡るため、tar czf - | ssh ... tar xzf - のストリーム転送や、ssh ホスト sort < ファイル が成立します。<<\'EOF\'（引用符付き）にすると $変数 が手元で展開されずリモートで評価されます。引用符なしの <<EOF は先に手元で展開されてしまいます。while read ループ内では ssh -n で標準入力を奪われないようにします。',
        'コマンド全体をクォートしないと手元のシェルが先に解釈します。', 'パイプ、<、<<\'EOF\' の3パターンを順に書きます。')


# ================================================================ 16 ssh-keyscan
def s16(ctx):
    host, port = 'git' + str(secrets.randbelow(80) + 10) + '.example.test', 2200 + secrets.randbelow(500)
    ctx.data.update(host=host, port=port)
    tag = f'[{host}]:{port}'
    keys = {'ed25519': fakepub('ssh-ed25519'), 'ecdsa': 'ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAI' + rnd(60), 'rsa': 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB' + rnd(80)}
    ctx.data['ed'] = f'{tag} {keys["ed25519"]}'
    sc = ''.join(f'# {tag} SSH-2.0-OpenSSH_9.6\n{tag} {keys[k]}\n' for k in ('rsa', 'ecdsa', 'ed25519'))
    put(ctx, 'scan.txt', f'$ ssh-keyscan -p {port} {host}\n' + sc)
    ctx.write('requirements.txt', f'(1) cmd.txt に、{host}（ポート{port}）の ed25519 ホスト鍵だけを取得する ssh-keyscan の1行。(2) 取得済みの scan.txt から、コメント行と ed25519 以外を除いた known_hosts_new を作る。この結果は公式のフィンガープリントと照合してから known_hosts に追記する。\n')


def c16(ctx):
    need_ro(ctx)
    d = ctx.data
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'ssh-keyscan' and '-t' in t and t[t.index('-t') + 1] == 'ed25519', 'ssh-keyscan -t ed25519 を使います。')
    ctx.require('-p' in t and t[t.index('-p') + 1] == str(d['port']) and t[-1] == d['host'], f'-p {d["port"]} とホスト名を指定します。')
    ls = [x for x in ctx.need_file('known_hosts_new').splitlines() if x.strip()]
    ctx.require(ls == [d['ed']], 'known_hosts_new には対象の ed25519 の鍵1行（[ホスト]:ポート 形式）だけを入れます。')


SOL16 = """echo "ssh-keyscan -t ed25519 -p <<port>> <<host>>" > cmd.txt
grep -v '^#' scan.txt | grep ' ssh-ed25519 ' > known_hosts_new"""
mission(16, 'ssh-keyscanでホスト鍵を取得しknown_hostsを作る',
        '初回接続の "authenticity of host can\'t be established" を安全に処理するため、事前にホスト鍵を取得して known_hosts に入れておきます。ssh-keyscan は接続せずに公開されているホスト鍵を取得します。ただし中間者の可能性があるので、取得結果は別の経路で得たフィンガープリントと照合します。',
        ['ssh-keyscan の取得コマンド', 'scan.txt から ed25519 だけを抽出'], s16, c16, SOL16,
        ["echo \"ssh-keyscan <<host>>\" > cmd.txt\ncp scan.txt known_hosts_new", "echo \"ssh-keyscan -p <<port>> <<host>>\" > cmd.txt\ngrep ssh scan.txt > known_hosts_new"],
        'ssh-keyscan -t 種類 -p ポート ホスト でホスト鍵を取得します。-H を付けるとホスト名をハッシュ化できます。標準ポート以外は known_hosts に [ホスト]:ポート の形式で記録されます。出力のコメント行（#）と他の鍵種別を除き、ssh-keygen -l -f で得たフィンガープリントを公式の値と照合してから追記します。盲目的に >> ~/.ssh/known_hosts するとTOFUの保護が失われます。',
        '取得は -t と -p、整形は grep です。', 'grep -v "^#" scan.txt | grep " ssh-ed25519 " で抽出します。')


# ================================================================ 17 Windows/WSL
def s17(ctx):
    cfg = 'Host dev\r\n    HostName dev.example.test\r\n    User trainee\r\n'
    ak = fakepub() + ' me@win\r\n'
    sh = '#!/bin/bash\r\necho deploy\r\n'
    ctx.data['exp'] = {'ssh/config': cfg.replace('\r', ''), 'ssh/authorized_keys': ak.replace('\r', ''), 'deploy.sh': sh.replace('\r', '')}
    for n, t in (('ssh/config', cfg), ('ssh/authorized_keys', ak), ('deploy.sh', sh)):
        ctx.write(n, t, binary=False) if False else (ctx.p(n).parent.mkdir(parents=True, exist_ok=True), ctx.p(n).write_bytes(t.encode()))
    os.chmod(ctx.p('ssh/config'), 0o644)
    put(ctx, 'wsl.conf', '[boot]\nsystemd=true\n[automount]\nenabled = true\n')
    put(ctx, 'wsl_error.txt', "$ ssh dev\n/mnt/c/Users/me/.ssh/config line 1: garbage at end of line; \"\\r\".\n/mnt/c/Users/me/.ssh/config: terminating, 1 bad configuration options\n\n$ ssh -i /mnt/c/Users/me/.ssh/id_ed25519 dev\nPermissions 0777 for '/mnt/c/Users/me/.ssh/id_ed25519' are too open.\n")
    ctx.data['ro'].pop('wsl.conf')
    ctx.write('requirements.txt', 'Windowsで編集した ssh/config・ssh/authorized_keys・deploy.sh に CRLF が混入している。(1) 3つを LF に直す（sed か dos2unix。ssh/config は 600 に）。(2) wsl.conf の [automount] に options = "metadata,umask=022,fmask=011" を追加し /mnt/c でも chmod が効くようにする。(3) .gitattributes に *.sh と config の改行を LF に固定する行（eol=lf）を書く。\n')


def c17(ctx):
    for n, t in ctx.data['exp'].items():
        b = ctx.p(n).read_bytes() if ctx.exists(n) else b''
        ctx.require(b'\r' not in b, f'{n} にまだ CR（\\r）が残っています。')
        ctx.require(b.decode() == t, f'{n} の中身は改行以外変更しません。')
    ctx.require(ctx.mode('ssh/config') == 0o600, 'ssh/config は 600 にします。')
    w = ctx.need_file('wsl.conf')
    m = re.search(r'\[automount\](.*?)(?=\n\[|\Z)', w, re.S)
    ctx.require(m and re.search(r'(?m)^options\s*=\s*"[^"]*metadata[^"]*"', m.group(1)), 'wsl.conf の [automount] セクションに options = "metadata,..." が必要です。')
    ctx.require('enabled' in m.group(1) and '[boot]' in w, 'wsl.conf の既存設定は残します。')
    g = ctx.need_file('.gitattributes')
    ctx.require(re.search(r'(?m)^\*\.sh\s+.*eol=lf', g) and re.search(r'(?m)^config\s+.*eol=lf', g), '.gitattributes に "*.sh text eol=lf" と "config text eol=lf" を書きます。')


SOL17 = """sed -i 's/\\r$//' ssh/config ssh/authorized_keys deploy.sh
chmod 600 ssh/config
sed -i '/^enabled = true/a options = "metadata,umask=022,fmask=011"' wsl.conf
printf '*.sh text eol=lf\\nconfig text eol=lf\\n' > .gitattributes"""
mission(17, 'Windows/WSLからのssh利用とsshファイルの改行（CRLFと権限）',
        'Windows側で編集した ssh の設定ファイルに CRLF 改行が混じり、"garbage at end of line" で ssh が動きません。また /mnt/c 上の鍵は権限が 777 に見えて "too open" になります。WSL からの利用で定番のこの2つの問題を、改行の変換と wsl.conf の metadata オプションで解消します。',
        ['3つのファイルを LF に変換', 'wsl.conf と .gitattributes を設定'], s17, c17, SOL17,
        ["sed -i 's/\\r$//' ssh/config\nchmod 600 ssh/config", "dos2unix ssh/config 2>/dev/null; chmod 777 ssh/config"],
        'CRLF は sed -i "s/\\r$//" ファイル または dos2unix で除去します（スクリプトは shebang に \\r が付くと bad interpreter になります）。WSL の /mnt/c は既定では全ファイルが 777 風に見えるため、[automount] options = "metadata" で Linux 権限を保存させるか、鍵は WSL 側のホーム（~/.ssh）に置くのが安全です。Git の autocrlf による混入は .gitattributes の eol=lf で防ぎます。',
        '\\r を取り除くのが先、権限はその後です。', 'sed -i で \\r を削除、wsl.conf は sed の a で options 行を追加します。')


# ================================================================ 18 sshd -t / パスワード認証オフ
ALLOWED = {'include', 'port', 'permitrootlogin', 'passwordauthentication', 'pubkeyauthentication', 'kbdinteractiveauthentication', 'usepam', 'x11forwarding', 'authorizedkeysfile', 'allowusers', 'subsystem', 'maxauthtries', 'logingracetime'}


def _sshd_effective(ctx, name='sshd_config'):
    seen, errs = {}, []

    def walk(rel):
        for i, raw in enumerate(ctx.need_file(rel).splitlines(), 1):
            ln = raw.strip()
            if not ln or ln.startswith('#'):
                continue
            k, _, v = ln.partition(' ')
            kl = k.lower()
            if kl not in ALLOWED:
                errs.append((rel, i, k))
                continue
            if kl == 'include':
                for p in sorted(Path(ctx.p('.')).glob(v.strip())):
                    walk(str(p.relative_to(ctx.p('.'))))
            else:
                seen.setdefault(kl, v.strip())
    walk(name)
    return seen, errs


def s18(ctx):
    lines = ['Include sshd_config.d/*.conf', 'Port 22', 'PermitRootLogin yes', 'PubkeyAuthentication yes', 'PasswordAuthentication yes', 'KbdInteractiveAuthentication yes', 'UsePAM yes', 'X11Forwarding no']
    i = lines.index('PubkeyAuthentication yes')
    lines[i] = 'PubkeyAuthenticaton yes'
    ctx.data['lineno'] = i + 1
    ctx.write('sshd_config', '\n'.join(lines) + '\n')
    ctx.mkdir('sshd_config.d')
    put(ctx, 'sshd_config.d/50-cloud-init.conf', 'PasswordAuthentication yes\n')
    put(ctx, 'sshd_t_output.txt', f'$ sshd -t\n/etc/ssh/sshd_config line {i + 1}: Bad configuration option: PubkeyAuthenticaton\n/etc/ssh/sshd_config: terminating, 1 bad configuration options\n')
    ctx.write('requirements.txt', 'パスワード認証をやめ鍵認証だけにする。sshd_config の実効値を PasswordAuthentication no・KbdInteractiveAuthentication no・PubkeyAuthentication yes・PermitRootLogin prohibit-password にする（sshd_config.d の設定が先に読まれ優先される点に注意。sshd -t の出力にあるタイポも直す。drop-inは編集せず、sshd_config の Include を末尾へ移して勝たせてもよい）。さらに procedure.txt に安全な手順を1行ずつ: (1) 設定のバックアップ cp、(2) sshd -t で検証、(3) systemctl reload ssh、(4) 既存セッションを閉じず別端末から ssh -o PreferredAuthentications=publickey で鍵ログインを確認。\n')


def c18(ctx):
    need_ro(ctx)
    seen, errs = _sshd_effective(ctx)
    ctx.require(not errs, f'sshd -t がエラーにします: {errs[0][0]} line {errs[0][1]}: Bad configuration option: {errs[0][2]}' if errs else '')
    for k, v in (('passwordauthentication', 'no'), ('kbdinteractiveauthentication', 'no'), ('pubkeyauthentication', 'yes'), ('permitrootlogin', 'prohibit-password')):
        ctx.require(seen.get(k) == v, f'実効値の {k} は {v} になるはずですが {seen.get(k)} です（最初に得た値が優先。Include の位置を確認）。')
    ls = [x for x in ctx.need_file('procedure.txt').splitlines() if x.strip()]
    pats = [r'\bcp\b.*sshd_config', r'sshd\s+-t\b', r'systemctl\s+reload\s+ssh', r'ssh\s+.*PreferredAuthentications=publickey']
    pos = -1
    for p in pats:
        idx = next((i for i, x in enumerate(ls) if re.search(p, x)), None)
        ctx.require(idx is not None and idx > pos, f'procedure.txt の手順 {p} が無いか順序が違います（バックアップ→sshd -t→reload→別端末で確認）。')
        pos = idx


SOL18 = """sed -i 's/PubkeyAuthenticaton/PubkeyAuthentication/; s/^PermitRootLogin yes/PermitRootLogin prohibit-password/; s/^PasswordAuthentication yes/PasswordAuthentication no/; s/^KbdInteractiveAuthentication yes/KbdInteractiveAuthentication no/' sshd_config
sed -i '/^Include/d' sshd_config
echo 'Include sshd_config.d/*.conf' >> sshd_config
cat > procedure.txt <<'EOF'
cp -p /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
sshd -t
systemctl reload ssh
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no deploy@server
EOF"""
mission(18, 'パスワード認証オフ移行の安全手順とsshd -tによる設定検証',
        'サーバーの SSH をパスワード認証から鍵認証へ移行します。設定を間違えて自分が締め出されないよう、sshd -t で検証し、reload し、別端末で確認する手順を守ります。クラウドの drop-in（sshd_config.d）が先に読まれて設定が効かない罠にも注意してください。',
        ['sshd_t_output.txt のエラーとタイポを修正', '実効値を鍵認証のみにする', 'procedure.txt に安全な手順を記録'], s18, c18, SOL18,
        ["sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' sshd_config", "sed -i 's/PubkeyAuthenticaton/PubkeyAuthentication/' sshd_config\nprintf 'systemctl restart ssh\\n' > procedure.txt"],
        'sshd_config は最初に得た値が優先で、Include を先頭に書くと sshd_config.d の 50-cloud-init.conf などが勝ちます。sshd -t は構文だけを検証し、-T で実効値を表示できます。手順は、設定バックアップ → sshd -t → systemctl reload（restartより接続を切らない）→ 既存セッションを閉じずに別端末から PreferredAuthentications=publickey で鍵ログイン確認 → 完了、の順です。失敗しても元のセッションが生きているので戻せます。',
        '実効値と設定の読み込み順を確認しましょう。', 'sed でタイポと値を直し、Include を末尾へ移します。procedure.txt に4行書きます。')


# ================================================================ 19 tmux 自動化
def s19(ctx):
    sess = 'job-' + rnd(4).lower()
    ctx.data.update(sess=sess)
    ctx.write('requirements.txt', f'remote_build.sh に tmux のコマンドを1行ずつ書く。(1) デタッチ状態でセッション {sess} を作成（tmux new -d -s）、(2) そこへ ./build.sh を send-keys で送って実行（最後は Enter）、(3) 新しいウィンドウ logs を tmux new-window で追加し tail -f build.log を送る、(4) 現在ウィンドウを左右に分割（split-window -h）、(5) 最後に tmux attach -t で接続。\n')


def c19(ctx):
    s = ctx.data['sess']
    ls = [x.strip() for x in ctx.need_file('remote_build.sh').splitlines() if x.strip() and not x.startswith('#')]
    pats = [r'^tmux\s+(new|new-session)\s+.*-d\b.*-s\s+' + s + r'\b|^tmux\s+(new|new-session)\s+.*-s\s+' + s + r'\s+.*-d\b',
            r'^tmux\s+send-keys\s+-t\s+' + s + r"\S*\s+['\"]?\./build\.sh['\"]?\s+(Enter|C-m)$",
            r'^tmux\s+new-window\s+.*-t\s+' + s + r'\b.*-n\s+logs\b|^tmux\s+new-window\s+.*-n\s+logs\b.*-t\s+' + s + r'\b',
            r"^tmux\s+send-keys\s+-t\s+" + s + r":logs\S*\s+['\"]tail -f build\.log['\"]\s+(Enter|C-m)$",
            r'^tmux\s+split-window\s+.*-h\b',
            r'^tmux\s+(attach|attach-session|a)\s+.*-t\s+' + s + r'\b']
    pos = -1
    for p in pats:
        idx = next((i for i, x in enumerate(ls) if re.search(p, x)), None)
        ctx.require(idx is not None and idx > pos, f'次の形の行が無いか、順序が違います: {p.split("|")[0]}')
        pos = idx


SOL19 = """cat > remote_build.sh <<'EOF'
tmux new -d -s <<sess>>
tmux send-keys -t <<sess>> './build.sh' Enter
tmux new-window -t <<sess>> -n logs
tmux send-keys -t <<sess>>:logs 'tail -f build.log' Enter
tmux split-window -h -t <<sess>>
tmux attach -t <<sess>>
EOF"""
mission(19, 'tmuxのセッション・ウィンドウ・ペインをtmux new -dとsend-keysで自動化する',
        'tmux は、セッション（作業単位）→ ウィンドウ（タブ）→ ペイン（分割画面）という階層を持ち、detach しても中のプロセスは動き続けます。接続を切っても残したいビルドを、人が操作せずスクリプトから立ち上げる手順を書いてみましょう。この環境に tmux が無くても、コマンドの組み立てを練習できます。',
        ['new -d と send-keys', 'new-window・split-window・attach を順に'], s19, c19, SOL19,
        ["echo \"tmux new -s <<sess>>\" > remote_build.sh", "cat > remote_build.sh <<'EOF'\ntmux attach -t <<sess>>\ntmux new -d -s <<sess>>\ntmux send-keys -t <<sess>> './build.sh' Enter\nEOF"],
        'tmux new -d -s 名前 はデタッチ状態で作成するのでスクリプトに向きます。send-keys -t 対象 \'文字列\' Enter はキー入力を送るので、既存のペイン内のシェルでコマンドを実行できます（対象は セッション:ウィンドウ.ペイン）。new-window -n 名前 でウィンドウ、split-window -h で左右分割（-v は上下）。最後に attach で人が接続します。切断は prefix(Ctrl-b) d の detach で、プロセスは生き続けます。',
        'まずデタッチで作って、中身を送り込み、最後に attach します。', 'tmux new -d -s、send-keys -t ... Enter、new-window -n、split-window -h、attach -t の順です。')


# ================================================================ 20 tmux ls 読解・キー
def s20(ctx):
    names = secrets.SystemRandom().sample(['api', 'db', 'web', 'batch', 'ops'], 3)
    wins = {n: 1 + secrets.randbelow(4) for n in names}
    att = sorted(secrets.SystemRandom().sample(names, 1 + secrets.randbelow(2)))
    ls = ''.join(f'{n}: {wins[n]} windows (created Sat Nov 21 09:0{i}:00 2026) [120x30]' + (' (attached)' if n in att else '') + '\n' for i, n in enumerate(names))
    panes, pl = 0, ''
    for n in names:
        for w in range(wins[n]):
            for p in range(1 + secrets.randbelow(3)):
                pl += f'{n}:{w}.{p}: [60x30] [history 12/2000, 3401 bytes] %{panes}' + (' (active)' if p == 0 else '') + '\n'
                panes += 1
    tgt = names[1]
    ctx.data.update(att=att, tw=wins[tgt], tp=panes, tgt=tgt)
    put(ctx, 'tmux_ls.txt', '$ tmux ls\n' + ls + '$ tmux list-panes -a\n' + pl)
    ctx.write('requirements.txt', f'tmux_ls.txt を読み、state.json に {{"attached": [接続中のセッション名を昇順], "target_windows": セッション {tgt} のウィンドウ数, "total_panes": ペイン総数}} を書く。さらに keys.json に、prefix（Ctrl-b）の後に押すキーを書く: {{"detach": ?, "new_window": ?, "split_left_right": ?, "split_top_bottom": ?, "copy_mode": ?, "paste": ?}}（コピーモードは scroll back に入るキー）。\n')


def c20(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'state.json')
    ctx.require(j.get('attached') == d['att'], 'attached は "(attached)" が付いたセッション名を昇順で。')
    ctx.require(j.get('target_windows') == d['tw'], f'{d["tgt"]} の windows 数が違います。')
    ctx.require(j.get('total_panes') == d['tp'], 'list-panes -a の行数（ペイン総数）が違います。')
    k = rj(ctx, 'keys.json')
    ctx.require(k == {'detach': 'd', 'new_window': 'c', 'split_left_right': '%', 'split_top_bottom': '"', 'copy_mode': '[', 'paste': ']'}, 'keys.json のキーが違います（detach=d、新ウィンドウ=c、左右分割=%、上下分割="、コピーモード=[、貼り付け=]）。')


SOL20 = """python3 - <<'PY'
import json,re
t=open('tmux_ls.txt').read()
ls,pl=t.split('$ tmux list-panes -a\\n')
rows=[l for l in ls.splitlines()[1:] if l]
att=sorted(l.split(':')[0] for l in rows if '(attached)' in l)
tw=[int(re.search(r': (\\d+) windows',l).group(1)) for l in rows if l.startswith('<<tgt>>:')][0]
json.dump({"attached":att,"target_windows":tw,"total_panes":len([l for l in pl.splitlines() if l])},open('state.json','w'))
PY
echo '{"detach": "d", "new_window": "c", "split_left_right": "%", "split_top_bottom": "\\"", "copy_mode": "[", "paste": "]"}' > keys.json"""
mission(20, 'tmux lsの出力を読み、detach/attach・ウィンドウ・ペイン・コピーモードのキーを整理する',
        '共有開発サーバーの tmux の状態を tmux ls と tmux list-panes -a の出力で把握し、誰かが接続中か、どのセッションにウィンドウとペインがいくつあるかを集計します。あわせて、日常操作に使う prefix キー（detach・新ウィンドウ・分割・コピーモード）を整理します。',
        ['state.json に接続状況・ウィンドウ数・ペイン数', 'keys.json に prefix 後のキー'], s20, c20, SOL20,
        ["echo '{\"attached\": [], \"target_windows\": 1, \"total_panes\": 1}' > state.json\necho '{}' > keys.json", "grep -c panes tmux_ls.txt > state.json"],
        'tmux ls は「セッション名: N windows (created ...) (attached)」を表示し、attached が付いたものは誰かが接続中です。list-panes -a は全ペインを セッション:ウィンドウ.ペイン で列挙します。prefix の後のキーは d（detach）、c（新ウィンドウ）、%（左右分割）、"（上下分割）、[（コピーモード。スクロールや選択、vi/emacs キーで操作）、]（貼り付け）です。接続し直すには tmux attach -t 名前（a）、再接続で他の接続を外すには -d です。',
        'ls の attached と、pane の行数を数えます。', 'python3 か grep/awk で集計し、キーは tmux の基本操作を思い出します。')


# ================================================================ 21 .tmux.conf
def s21(ctx):
    si, hl = secrets.choice([2, 5, 10]), secrets.choice([20000, 50000])
    ctx.data.update(si=si, hl=hl)
    put(ctx, 'tmux.conf.orig', 'set -g prefix C-b\nset -g mouse off\nset -g status-interval 15\nset -g history-limit 2000\nset -g status-left "#H"\n')
    ctx.write('.tmux.conf', ctx.read('tmux.conf.orig'))
    ctx.write('requirements.txt', f'.tmux.conf を編集して: prefix を C-a に変更（旧 C-b を unbind し、入れ子のtmux用に bind C-a send-prefix）、mouse on、status-interval {si}、history-limit {hl}、status-left に [#S] を含める、status-right に %H:%M を表示、mode-keys vi。\n')


def _tmux_opts(text):
    opts, binds, unb = {}, [], []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        try:
            t = shlex.split(ln)
        except ValueError:
            continue
        if t[0] in ('set', 'set-option', 'set-window-option', 'setw') and len(t) >= 3:
            rest = [x for x in t[1:] if not x.startswith('-')] if True else t
            if len(rest) >= 2:
                opts[rest[0]] = ' '.join(rest[1:])
        elif t[0] in ('bind', 'bind-key'):
            binds.append([x for x in t[1:] if not x.startswith('-')])
        elif t[0] in ('unbind', 'unbind-key'):
            unb.append([x for x in t[1:] if not x.startswith('-')])
    return opts, binds, unb


def c21(ctx):
    need_ro(ctx)
    o, b, u = _tmux_opts(ctx.need_file('.tmux.conf'))
    d = ctx.data
    ctx.require(o.get('prefix') == 'C-a', 'set -g prefix C-a にします（最後の指定が有効）。')
    ctx.require(['C-b'] in u, 'unbind C-b で旧prefixを解除します。')
    ctx.require(['C-a', 'send-prefix'] in b, 'bind C-a send-prefix を書きます。')
    ctx.require(o.get('mouse') == 'on', 'set -g mouse on')
    ctx.require(o.get('status-interval') == str(d['si']), f'status-interval は {d["si"]} です。')
    ctx.require(o.get('history-limit') == str(d['hl']), f'history-limit は {d["hl"]} です。')
    ctx.require('[#S]' in o.get('status-left', ''), 'status-left に [#S]（セッション名）を含めます。')
    ctx.require('%H:%M' in o.get('status-right', ''), 'status-right に %H:%M を表示します。')
    ctx.require(o.get('mode-keys') == 'vi', 'setw -g mode-keys vi（コピーモードをviキーに）。')


SOL21 = """cat > .tmux.conf <<'EOF'
set -g prefix C-a
unbind C-b
bind C-a send-prefix
set -g mouse on
set -g status-interval <<si>>
set -g history-limit <<hl>>
set -g status-left "[#S] "
set -g status-right "%H:%M"
setw -g mode-keys vi
EOF"""
mission(21, '.tmux.confでprefixの変更・マウス有効化・status設定を行う',
        '.tmux.conf を使いやすく整えます。prefix を Ctrl-a に変更し、マウント操作（スクロール・ペイン選択）を有効にし、ステータスバーに情報を表示します。tmux が無くても、設定ファイルの記述として読み書きを練習できます。反映は tmux source-file ~/.tmux.conf です。',
        ['prefix と unbind と send-prefix', 'mouse・status・history・mode-keys'], s21, c21, SOL21,
        ["sed -i 's/C-b/C-a/' .tmux.conf", "echo 'set -g mouse on' >> .tmux.conf"],
        'set -g はグローバルオプション、setw はウィンドウオプションです。prefix を変えたら旧キーを unbind し、入れ子（SSH先のtmux）に prefix を送る bind C-a send-prefix を併記します。同じオプションは後の行が有効なので、既存行の書き換えか末尾への追記で上書きできます。mouse on でスクロール・リサイズ、status-interval で更新間隔、status-left/right で表示（#S=セッション名）、mode-keys vi でコピーモードのキーを変更します。tmux source-file ~/.tmux.conf で再読込します。',
        '同じキーの設定は後の行が勝ちます。', 'set -g prefix C-a / unbind C-b / bind C-a send-prefix などを書きます。')


# ================================================================ 22 screen と byobu
def s22(ctx):
    b, l, o = 'build' + rnd(2).lower(), 'logs' + rnd(2).lower(), 'old' + rnd(2).lower()
    ctx.data.update(b=b, l=l, o=o)
    put(ctx, 'screen_ls.txt', f'$ screen -ls\nThere are screens on:\n\t12345.{b}\t(11/21/2026 09:00:00 AM)\t(Detached)\n\t23456.{l}\t(11/21/2026 09:05:00 AM)\t(Attached)\n\t34567.{o}\t(11/20/2026 06:00:00 PM)\t(Dead ???)\nRemove dead screens with \'screen -wipe\'.\n3 Sockets in /run/screen/S-trainee.\n')
    ctx.write('requirements.txt', f'screen_ls.txt を読み、(1) reattach.txt: Detached の {b} に再接続する screen の1行、(2) steal.txt: 別端末で Attached の {l} を強制的に切り離して自分の端末へ接続し直す screen の1行（-d -r）、(3) cleanup.txt: 死んだソケットを掃除する1行、(4) equiv.json: screen -S 名前 / screen -ls / screen -r 名前 に相当する tmux のコマンドを {{"screen -S build":"tmux ...", "screen -ls":"tmux ...", "screen -r build":"tmux ..."}} で、(5) byobu.json: byobu の裏側（tmux か screen）と、新規ウィンドウ（F2）・detach（F6）のキーを {{"backend": ?, "new_window": ?, "detach": ?}} で書く。\n')


def _tm(s):
    return re.sub(r'\s+', ' ', s.strip())


def c22(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(toks(ctx, one_line(ctx, 'reattach.txt')) == ['screen', '-r', d['b']], 'screen -r ' + d['b'])
    t = toks(ctx, one_line(ctx, 'steal.txt'))
    ctx.require(t[0] == 'screen' and t[-1] == d['l'] and ('-d' in t and '-r' in t or '-dr' in t or '-D' in t), 'screen -d -r ' + d['l'])
    ctx.require(toks(ctx, one_line(ctx, 'cleanup.txt')) == ['screen', '-wipe'], 'screen -wipe')
    j = rj(ctx, 'equiv.json')
    ctx.require(_tm(j.get('screen -S build', '')) in ('tmux new -s build', 'tmux new-session -s build'), 'screen -S build は tmux new -s build です。')
    ctx.require(_tm(j.get('screen -ls', '')) in ('tmux ls', 'tmux list-sessions'), 'screen -ls は tmux ls です。')
    ctx.require(_tm(j.get('screen -r build', '')) in ('tmux attach -t build', 'tmux a -t build', 'tmux attach-session -t build'), 'screen -r build は tmux attach -t build です。')
    ctx.require(rj(ctx, 'byobu.json') == {'backend': 'tmux', 'new_window': 'F2', 'detach': 'F6'}, 'byobu は既定で tmux を使い、F2=新規ウィンドウ、F6=detach です。')


SOL22 = """echo "screen -r <<b>>" > reattach.txt
echo "screen -d -r <<l>>" > steal.txt
echo "screen -wipe" > cleanup.txt
echo '{"screen -S build": "tmux new -s build", "screen -ls": "tmux ls", "screen -r build": "tmux attach -t build"}' > equiv.json
echo '{"backend": "tmux", "new_window": "F2", "detach": "F6"}' > byobu.json"""
mission(22, 'screenとbyobuを読み解き、tmuxの対応コマンドを押さえる',
        '古いサーバーでは tmux ではなく screen が使われています。screen -ls の出力から接続すべきセッションと掃除すべきソケットを判断し、tmux の対応コマンドも整理します。byobu は tmux/screen をまとめて使いやすくするラッパーです。',
        ['screen の再接続・強制接続・掃除', 'tmux との対応表と byobu のキー'], s22, c22, SOL22,
        ["echo \"screen -S <<b>>\" > reattach.txt\necho \"screen -r <<l>>\" > steal.txt\necho \"screen -ls\" > cleanup.txt", "echo '{\"screen -S build\": \"tmux attach\", \"screen -ls\": \"tmux ls\"}' > equiv.json"],
        'screen -r は Detached のセッションへ再接続、すでに Attached（別端末から接続中）のものは screen -d -r（または -D -r）で切り離して接続します。Dead ??? は screen -wipe で掃除します。screen -S は名前付き作成、Ctrl-a d が detach です。tmux では tmux new -s、tmux ls、tmux attach -t、prefix d に対応します。byobu は既定で tmux をバックエンドにし F2（新規ウィンドウ）・F6（detach）・F9（メニュー）で操作できます。',
        '状態（Detached/Attached/Dead）ごとに使うオプションが違います。', 'screen -r、screen -d -r、screen -wipe を状態に合わせて書きます。')


# ================================================================ 23 長時間ジョブ
def s23(ctx):
    order = ['A', 'B', 'C']
    secrets.SystemRandom().shuffle(order)
    ctx.data.update(jn=order[0], jt=order[1], js=order[2], un='batch-' + rnd(3).lower(), mem=str(256 * (1 + secrets.randbelow(4))) + 'M')
    put(ctx, 'jobs.txt', f'ジョブ{order[0]}: 夜間バッチ。対話は不要、ログをファイルに残し、ログアウトしても動けばよい（./nightly.sh）。\nジョブ{order[1]}: 対話的なデバッグ。出力を見ながら入力し、別の端末や別日にも同じ画面へ戻りたい。\nジョブ{order[2]}: 重い集計。メモリ上限を課し、システムのユニットとして管理（停止・状態確認）し、ログアウト後も動かしたい（./heavy.sh）。\n')
    ctx.write('requirements.txt', f'jobs.txt のジョブごとに最適な手段を plan.json（{{"A": ?, "B": ?, "C": ?}} を nohup / tmux / systemd-run で）に書く。さらに nohup.txt に、nightly.sh を nohup で標準出力と標準エラーを nightly.log にまとめバックグラウンド実行する1行、sdrun.txt に、heavy.sh を --user で、ユニット名 {ctx.data["un"]}・メモリ上限 {ctx.data["mem"]}（MemoryMax）、終了後にユニットを自動削除（--collect）で起動する systemd-run の1行を書く。\n')


def c23(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(rj(ctx, 'plan.json') == {d['jn']: 'nohup', d['jt']: 'tmux', d['js']: 'systemd-run'}, 'plan.json: 対話不要=nohup、対話・再接続=tmux、資源制限と管理=systemd-run です。')
    t = toks(ctx, one_line(ctx, 'nohup.txt'))
    ctx.require(t[0] == 'nohup' and './nightly.sh' in t and '>' in t and t[t.index('>') + 1] == 'nightly.log' and '2>&1' in t and t[-1] == '&', 'nohup ./nightly.sh > nightly.log 2>&1 & の形です。')
    t = toks(ctx, one_line(ctx, 'sdrun.txt'))
    ctx.require(t[0] == 'systemd-run' and '--user' in t and '--collect' in t and f'--unit={d["un"]}' in t, '--user --collect --unit=名前 を付けます。')
    ctx.require('-p' in t and t[t.index('-p') + 1] == f'MemoryMax={d["mem"]}' and t[-1] == './heavy.sh', f'-p MemoryMax={d["mem"]} と最後に ./heavy.sh を置きます。')


SOL23 = """echo '{"<<jn>>": "nohup", "<<jt>>": "tmux", "<<js>>": "systemd-run"}' > plan.json
echo "nohup ./nightly.sh > nightly.log 2>&1 &" > nohup.txt
echo "systemd-run --user --collect --unit=<<un>> -p MemoryMax=<<mem>> ./heavy.sh" > sdrun.txt"""
mission(23, '長時間ジョブをnohup・tmux・systemd-runで使い分ける',
        'SSH が切れるとシェルの子プロセスは SIGHUP で終了します。長時間ジョブを残す方法には nohup、tmux、systemd-run があり、向き不向きがあります。ジョブの性質を読んで適切な手段を選び、それぞれのコマンドを正しく書いてください。',
        ['plan.json に手段を選択', 'nohup と systemd-run のコマンドを記述'], s23, c23, SOL23,
        ["echo '{\"A\": \"tmux\", \"B\": \"tmux\", \"C\": \"tmux\"}' > plan.json\necho \"nohup ./nightly.sh &\" > nohup.txt\necho \"systemd-run ./heavy.sh\" > sdrun.txt", "echo \"nohup ./nightly.sh > nightly.log &\" > nohup.txt"],
        'nohup は SIGHUP を無視させるだけの手軽な方法で、ログは自分でリダイレクトします（> log 2>&1 &）。tmux は後から画面に戻れて対話できます。systemd-run --user はcgroupによる資源制限（MemoryMaxなど）・状態確認（systemctl --user status 名前）・停止ができ、--collect で終了後に自動で片付きます。ログアウト後も動かすなら loginctl enable-linger が必要な場合があります。',
        '対話の要否・資源制限の要否で選びます。', 'nohup は > ログ 2>&1 &、systemd-run は --user --collect --unit -p です。')


# ================================================================ 24 vim -r
def s24(ctx):
    run = secrets.choice([True, False])
    pid = 2000 + secrets.randbelow(30000)
    ctx.data.update(run=run, pid=pid)
    put(ctx, 'app.conf', 'listen 8080\nworkers 4\n')
    put(ctx, '.app.conf.swp', 'b0VIM 9.1 (swap file)\n')
    put(ctx, 'vim_warning.txt', f'$ vim app.conf\nE325: ATTENTION\nFound a swap file by the name ".app.conf.swp"\n          owned by: trainee   dated: Sat Nov 21 10:02:11 2026\n         file name: ~trainee/app.conf\n          modified: YES\n         user name: trainee   host name: web01\n        process ID: {pid}' + (' (STILL RUNNING)' if run else '') + '\nWhile opening file "app.conf"\n')
    act = 'read_only' if run else 'recover'
    ctx.data['act'] = act
    ctx.write('requirements.txt', 'vim_warning.txt を読んで、(1) decision.json に {"pid": 該当PID, "still_running": true/false, "action": "read_only" か "recover"} を書く（プロセスが生きていれば他の人が編集中なので上書きしない）。(2) steps.txt に、実行する手順を1行ずつ書く。read_only なら読み取り専用で開く1行（vim -R）。recover なら、まず元ファイルを cp -p で app.conf.bak に控え、vim -r で復旧し、diff -u app.conf.bak app.conf で差分を確認、問題なければ不要になったスワップ .app.conf.swp を rm する。\n')


def c24(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'decision.json')
    ctx.require(j.get('pid') == d['pid'] and j.get('still_running') is d['run'] and j.get('action') == d['act'], 'decision.json: process ID と (STILL RUNNING) の有無から判断します。')
    ls = [x.strip() for x in ctx.need_file('steps.txt').splitlines() if x.strip()]
    if d['run']:
        ctx.require(len(ls) == 1 and re.fullmatch(r'(vim -R|view|vim -M) app\.conf', ls[0]), '稼働中なら vim -R app.conf（または view）で読み取り専用です。')
        return
    pats = [r'^cp -p app\.conf app\.conf\.bak$', r'^vim -r app\.conf$', r'^diff -u app\.conf\.bak app\.conf$', r'^rm (-f )?\.app\.conf\.swp$']
    ctx.require(len(ls) == 4 and all(re.search(p, x) for p, x in zip(pats, ls)), '4行: cp -p → vim -r → diff -u → rm .app.conf.swp の順です。')


SOL24 = """python3 - <<'PY'
import json,re
t=open('vim_warning.txt').read()
pid=int(re.search(r'process ID: (\\d+)',t).group(1)); run='STILL RUNNING' in t
json.dump({"pid":pid,"still_running":run,"action":"read_only" if run else "recover"},open('decision.json','w'))
open('steps.txt','w').write('vim -R app.conf\\n' if run else 'cp -p app.conf app.conf.bak\\nvim -r app.conf\\ndiff -u app.conf.bak app.conf\\nrm .app.conf.swp\\n')
PY"""
mission(24, 'リモートでの安全なファイル編集（vimのスワップ警告とvim -rによる復旧）',
        'ssh 越しに設定ファイルを編集中に回線が切れ、再度開くと vim が E325 の警告を出しました。スワップファイルは「誰かが編集中」か「前回の異常終了」の印です。警告の内容から、読み取り専用で開くか vim -r で復旧するかを判断し、手順を書いてください。',
        ['警告文から状況を判定', 'steps.txt に安全な手順'], s24, c24, SOL24,
        ["echo '{\"pid\": 1, \"still_running\": false, \"action\": \"recover\"}' > decision.json\necho 'rm .app.conf.swp' > steps.txt", "echo 'vim app.conf' > steps.txt"],
        'process ID に (STILL RUNNING) があれば、そのプロセスが編集中です。無視して開くと二重編集で内容が壊れるため vim -R（読み取り専用）で見ます。無い場合は異常終了の残りで、vim -r ファイル でスワップから復旧し、:w で保存してから diff -u で元ファイルとの差分を確認し、不要なスワップを削除します。編集前に cp -p で控えを取る習慣が、リモートでは特に重要です。',
        'process ID の行を読みます。', 'STILL RUNNING なら vim -R、それ以外は cp -p → vim -r → diff -u → rm です。')


# ================================================================ 25 作業ログ
def s25(ctx):
    n, tag = secrets.choice([20000, 50000, 100000]), rnd(4).lower()
    ctx.data.update(n=n, tag=tag)
    put(ctx, 'bashrc_work.orig', '# 作業用シェル設定\nexport PS1="\\u@\\h:\\w\\$ "\n')
    ctx.write('bashrc_work', ctx.read('bashrc_work.orig'))
    ctx.write('requirements.txt', f'本番作業の証跡を残す設定を整える。(1) bashrc_work に、history に実行日時を記録する HISTTIMEFORMAT（%F %T の形式）、HISTSIZE={n}、シェル終了時に履歴を上書きでなく追記する shopt -s histappend を追記する。(2) script.txt に、端末の入出力を ops_{tag}.log へ追記モード（-a）で静かに（-q）記録する script の1行を書く。\n')


def c25(ctx):
    d = ctx.data
    r = subprocess.run(['bash', '--norc', '--noprofile', '-c', 'source bashrc_work; echo "$HISTTIMEFORMAT|$HISTSIZE"; shopt -p histappend'], cwd=ctx.p('.'), capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    lines = r.stdout.splitlines()
    ctx.require(len(lines) >= 2, 'bashrc_work を読み込めません。')
    f, n = lines[0].split('|')
    ctx.require('%F' in f and '%T' in f, 'HISTTIMEFORMAT は "%F %T " のように日付と時刻を含めます。')
    ctx.require(n == str(d['n']), f'HISTSIZE は {d["n"]} です。')
    ctx.require(lines[1].strip() == 'shopt -s histappend', 'shopt -s histappend で履歴を追記にします。')
    t = toks(ctx, one_line(ctx, 'script.txt'))
    ctx.require(t[0] == 'script' and t[-1] == f'ops_{d["tag"]}.log', f'script ... ops_{d["tag"]}.log の形です。')
    fl = ''.join(x[1:] for x in t[1:-1] if x.startswith('-') and not x.startswith('--'))
    ctx.require('a' in fl and 'q' in fl, '-a（追記）と -q（静か）を付けます。')


SOL25 = """cat >> bashrc_work <<'EOF'
export HISTTIMEFORMAT='%F %T '
export HISTSIZE=<<n>>
shopt -s histappend
EOF
echo "script -q -a ops_<<tag>>.log" > script.txt"""
mission(25, '作業ログを残す（scriptとhistoryのHISTTIMEFORMAT）',
        '障害対応の作業履歴は後から「いつ何をしたか」を追えることが重要です。history に日時を付ける HISTTIMEFORMAT と、画面入出力を丸ごと記録する script を設定し、作業の証跡を残します。',
        ['HISTTIMEFORMAT・HISTSIZE・histappend を設定', 'script で追記記録するコマンド'], s25, c25, SOL25,
        ["echo 'export HISTSIZE=<<n>>' >> bashrc_work\necho \"script ops_<<tag>>.log\" > script.txt", "echo 'HISTTIMEFORMAT=%F' >> bashrc_work\necho \"script -q -a\" > script.txt"],
        'HISTTIMEFORMAT を設定すると history の各行に strftime 形式の日時が付きます（例 "%F %T "）。HISTSIZE は保持件数、shopt -s histappend は複数セッションの履歴が上書きでなく追記されるようにします。script は端末の入出力をファイルへ記録し、-a で追記、-q で開始・終了メッセージを抑え、exit で終了します。記録にはパスワード入力が含まれうるのでファイルの扱いに注意します。',
        '履歴は環境変数、記録は script です。', 'export HISTTIMEFORMAT=... と script -q -a ファイル です。')
