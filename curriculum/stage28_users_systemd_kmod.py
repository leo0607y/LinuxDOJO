"""Stage 28: ユーザー管理・sudo・systemd周辺・カーネルモジュール・/etcの重要ファイルとユニットファイルの総ざらい。サンドボックス内の偽データだけを使う。"""
import hashlib
import json
import re
import secrets
import shlex
from pathlib import Path

from engine.runner import register

S = 28
NOTE = ("作業対象はこの課題のフォルダだけです。実OSのアカウント・sudoers・サービス・カーネルモジュール・SELinuxは変更せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないツールは採取済みの出力と設定例から診断・編集し、コマンドは実行予定の1行として書きます。")


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


def tk(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません: ' + line)


def cmdlines(ctx, name):
    out = []
    for ln in ctx.need_file(name).splitlines():
        if ln.strip() and not ln.strip().startswith('#'):
            out.append(tk(ctx, ln))
    return out


def tool(ctx, cl, name, what=None):
    for t in cl:
        if t and t[0] == name:
            return t
    ctx.fail(f'{what or "ファイル"}に {name} のコマンド行がありません。')


def optv(t, *names):
    for i, x in enumerate(t):
        for n in names:
            if x == n and i + 1 < len(t):
                return t[i + 1]
            if x.startswith(n + '=') and n.startswith('--'):
                return x.split('=', 1)[1]
    return None


def lines(ctx, name):
    return ctx.need_file(name).splitlines()


def unit(ctx, name):
    """INI形式ユニットを {section: [(key, value), ...]} に。"""
    d, cur = {}, None
    for ln in lines(ctx, name):
        s = ln.strip()
        if not s or s[0] in '#;':
            continue
        m = re.match(r'^\[(\w+)\]$', s)
        if m:
            cur = m.group(1)
            d.setdefault(cur, [])
        elif cur and '=' in s:
            k, v = s.split('=', 1)
            d[cur].append((k.strip(), v.strip()))
        else:
            ctx.fail(f'{name}: 解釈できない行です: {s}')
    return d


def uv(d, sec, key):
    return [v for k, v in d.get(sec, []) if k == key]


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'28-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='影響の大きい管理コマンドは、サンドボックスや検証用オプション（-R/--root、-c、-n）で先に試し、原本を保全してから本番へ適用します。')


def rnd(prefix='', n=2):
    return prefix + secrets.token_hex(n)


# ---------------------------------------------------------------- 1 chfn chsh
def s1(ctx):
    user = rnd('u')
    full = 'Taro ' + rnd('', 2).upper()
    shell = secrets.choice(['/usr/bin/zsh', '/usr/bin/fish', '/bin/dash'])
    ctx.data.update(user=user, full=full, shell=shell)
    rows = ['root:x:0:0:root:/root:/bin/bash', f'{user}:x:1001:1001:{rnd("old")}:/home/{user}:/bin/bash',
            'daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin', 'svc:x:998:998:Service:/var/lib/svc:/usr/sbin/nologin']
    ctx.data['others'] = [r for r in rows if not r.startswith(user + ':')]
    put(ctx, 'shells', '# /etc/shells\n/bin/sh\n/bin/bash\n/bin/dash\n/usr/bin/zsh\n/usr/bin/fish\n')
    ctx.write('passwd', '\n'.join(rows) + '\n')
    ctx.write('requirements.txt', f'passwdは訓練用コピーです。{user} のGECOS（氏名）を「{full}」に、ログインシェルを{shell}に直す。shellsに載っているシェルだけが許可される。同じ変更を実機で行うchfnとchshの実行予定を cmd.txt に2行（chfn、chsh）で書く。他のユーザー行は変えない。\n')


def c1(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = lines(ctx, 'passwd')
    mine = [x for x in ls if x.startswith(d['user'] + ':')]
    ctx.require(len(mine) == 1, 'ユーザー行が1行ではありません。')
    f = mine[0].split(':')
    ctx.require(len(f) == 7 and f[4].split(',')[0] == d['full'], 'GECOS（氏名）が指定どおりではありません。')
    ctx.require(f[6] == d['shell'], 'ログインシェルが指定どおりではありません。')
    ctx.require([x for x in ls if not x.startswith(d['user'] + ':')] == d['others'], '他のユーザー行は変更しません。')
    cl = cmdlines(ctx, 'cmd.txt')
    a = tool(ctx, cl, 'chfn')
    ctx.require(optv(a, '-f', '--full-name') == d['full'] and a[-1] == d['user'], 'chfn -f 氏名 ユーザー の形で書きます。')
    b = tool(ctx, cl, 'chsh')
    ctx.require(optv(b, '-s', '--shell') == d['shell'] and b[-1] == d['user'], 'chsh -s シェル ユーザー の形で書きます。')


SOL1 = """sed -i 's#^\\(<<user>>:[^:]*:[^:]*:[^:]*:\\)[^:]*:\\([^:]*\\):.*#\\1<<full>>:\\2:<<shell>>#' passwd
echo 'chfn -f "<<full>>" <<user>>' > cmd.txt
echo 'chsh -s <<shell>> <<user>>' >> cmd.txt"""
mission(1, 'chfnとchshでGECOSとログインシェルを直す',
        '人事異動で社員の氏名とログインシェルが変わりました。passwdの各フィールド（GECOSとシェル）を理解し、/etc/shellsに載るシェルだけを許可するchsh、氏名を直すchfnの使い方も押さえます。',
        ['passwdのGECOSとシェルを正しく更新', 'chfnとchshの実行予定をcmd.txtへ'], s1, c1, SOL1,
        ["sed -i 's#/bin/bash#<<shell>>#' passwd\necho 'chsh <<user>>' > cmd.txt",
         "sed -i 's#^\\(<<user>>:[^:]*:[^:]*:[^:]*:\\)[^:]*:\\([^:]*\\):.*#\\1<<full>>:\\2:/bin/nosuch#' passwd\necho 'chfn <<user>>' > cmd.txt"],
        'passwdは name:x:UID:GID:GECOS:home:shell の7項目です。chfnはGECOS（氏名・部屋番号など）を、chshはログインシェルを本人が変更でき、chshは/etc/shellsに載るシェルしか受け付けません。-f/-sで非対話に指定でき、rootなら他人の分も変更できます。設定ファイルを直接sedで編集する方法は障害復旧向けで、通常はchfn/chshを使います。',
        'passwdの第5項目と第7項目だけを置換します。', 'sedで該当ユーザー行の第5・第7フィールドを置換し、chfn -f / chsh -s を書きます。')


# ---------------------------------------------------------------- 2 chgpasswd groupmod groupmems
def s2(ctx):
    d = dict(old=rnd('team'), new=rnd('sre'), user=rnd('u'), secret=secrets.token_hex(4))
    ctx.data.update(d)
    ctx.write('requirements.txt', f'chrootのような作業ルート ./root の中のグループ {d["old"]} を {d["new"]} に改名し（groupmod）、メンバーに {d["user"]} を追加し（groupmems）、グループパスワード（{d["secret"]}）をSHA512で設定する（chgpasswd）。実行予定を cmds.txt に1コマンド1行で書く（groupmod・chgpasswdは -R ./root を付けて実OSに触れない。chgpasswdはパイプで group:パスワード を渡す）。\n')


def c2(ctx):
    d = ctx.data
    ls = ctx.need_file('cmds.txt').splitlines()
    ls = [x for x in ls if x.strip() and not x.strip().startswith('#')]
    seen = {}
    for ln in ls:
        segs = [tk(ctx, s) for s in ln.split('|')]
        for t in segs:
            if t:
                seen[t[0]] = (t, ln, segs)
    a = seen.get('groupmod')
    ctx.require(a, 'groupmodの行がありません。')
    t = a[0]
    ctx.require(optv(t, '-n', '--new-name') == d['new'] and t[-1] == d['old'], 'groupmod -n 新名 旧名 の形にします。')
    ctx.require(optv(t, '-R', '--root') == './root', '実OSに触れないよう -R ./root を付けます。')
    m = seen.get('groupmems')
    ctx.require(m, 'groupmemsの行がありません。')
    ctx.require(optv(m[0], '-g', '--group') == d['new'] and optv(m[0], '-a', '--add') == d['user'], 'groupmems -g 新グループ -a ユーザー の形にします（改名後の名前を使う）。')
    g = seen.get('chgpasswd')
    ctx.require(g, 'chgpasswdの行がありません。')
    ctx.require(optv(g[0], '-c', '--crypt-method') == 'SHA512', 'chgpasswd -c SHA512 でハッシュ方式を指定します。')
    ctx.require(optv(g[0], '-R', '--root') == './root', 'chgpasswdにも -R ./root を付けます。')
    ctx.require(f'{d["new"]}:{d["secret"]}' in g[1], '入力は 新グループ名:パスワード の形で、パイプで渡します。')
    ctx.require(g[2][0][0] in ('printf', 'echo') and g[2][-1][0] == 'chgpasswd', 'printf/echoの出力をchgpasswdへパイプします。')


SOL2 = """cat > cmds.txt <<'EOF'
groupmod -R ./root -n <<new>> <<old>>
groupmems -g <<new>> -a <<user>>
echo '<<new>>:<<secret>>' | chgpasswd -c SHA512 -R ./root
EOF"""
mission(2, 'groupmod・groupmems・chgpasswdでグループを整える',
        'チーム名が変わり、グループ名の変更・メンバー追加・グループパスワード設定をまとめて行います。groupmodは属性変更、groupmemsは一般ユーザーでもグループ管理者として操作できるメンバー管理、chgpasswdは複数のグループパスワードを一括設定するコマンドです。',
        ['groupmodで改名', 'groupmemsでメンバー追加', 'chgpasswdでSHA512パスワード設定'], s2, c2, SOL2,
        ["cat > cmds.txt <<'EOF'\ngroupmod -n <<new>> <<old>>\ngroupmems -g <<old>> -a <<user>>\nEOF",
         "cat > cmds.txt <<'EOF'\ngroupmod -R ./root -n <<new>> <<old>>\ngroupmems -g <<new>> -a <<user>>\necho '<<new>>:<<secret>>' | chgpasswd -R ./root\nEOF"],
        'groupmod -n は名前、-g はGIDを変更します。groupmems -g グループ -a/-d ユーザー でメンバーを追加・削除し、-l で一覧します。chgpasswdは標準入力の group:password 行を読み、-c SHA512 で暗号化方式、-e で暗号化済みを指定します。-R/--root は指定ディレクトリを根として操作でき、実OSを触らない検証に便利です。',
        '先に改名し、改名後の名前でgroupmemsとchgpasswdを呼びます。', '-R ./root を付け、printfまたはechoからchgpasswdへパイプします。')


# ---------------------------------------------------------------- 3 pwck grpck
def s3(ctx):
    u = [rnd('u') for _ in range(3)]
    g = [rnd('g') for _ in range(2)]
    gh = [rnd('ghost') for _ in range(2)]
    sh = rnd('sh')
    ctx.data.update(u=u, g=g, gh=gh, sh=sh)
    put(ctx, 'pwck.out', f"user '{u[0]}': directory '/home/{u[0]}' does not exist\n"
        f"user '{u[1]}': program '/usr/local/bin/{sh}' does not exist\n"
        f"user '{u[2]}': group '{3000 + secrets.randbelow(900)}' does not exist\n"
        "pwck: the files have been updated\n")
    put(ctx, 'grpck.out', f"group '{g[0]}': user '{gh[0]}' does not exist\n"
        f"group '{g[1]}': user '{gh[1]}' does not exist\n" "grpck: no changes\n")
    ctx.write('requirements.txt', 'pwck.out と grpck.out は管理者が読み取り専用で採取した検査結果です。report.json に {"missing_home":[ホームが無いユーザー],"bad_shell":[存在しないシェルのユーザー],"missing_group":[存在しないGIDのユーザー],"ghost_members":{グループ名:[存在しないメンバー]}} を作る。次に実機で再検査する読み取り専用コマンドを cmd.txt に2行（pwck と grpck、どちらも -r）書く。\n')


def c3(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'report.json')
    ctx.require(r.get('missing_home') == [d['u'][0]], 'missing_home が違います。')
    ctx.require(r.get('bad_shell') == [d['u'][1]], 'bad_shell が違います。')
    ctx.require(r.get('missing_group') == [d['u'][2]], 'missing_group が違います。')
    ctx.require(r.get('ghost_members') == {d['g'][0]: [d['gh'][0]], d['g'][1]: [d['gh'][1]]}, 'ghost_members が違います。')
    cl = cmdlines(ctx, 'cmd.txt')
    ctx.require('-r' in tool(ctx, cl, 'pwck'), 'pwck -r（読み取り専用）にします。')
    ctx.require('-r' in tool(ctx, cl, 'grpck'), 'grpck -r（読み取り専用）にします。')


SOL3 = """python3 - <<'PY'
import re, json
p = open('pwck.out').read(); g = open('grpck.out').read()
r = {'missing_home': re.findall(r"user '(\\S+)': directory", p), 'bad_shell': re.findall(r"user '(\\S+)': program", p),
     'missing_group': re.findall(r"user '(\\S+)': group", p), 'ghost_members': {}}
for a, b in re.findall(r"group '(\\S+)': user '(\\S+)' does not exist", g):
    r['ghost_members'].setdefault(a, []).append(b)
json.dump(r, open('report.json', 'w'))
PY
printf 'pwck -r\\ngrpck -r\\n' > cmd.txt"""
mission(3, 'pwckとgrpckの検査結果を診断する',
        'アカウントDBの定期検査でpwckとgrpckの結果が出ました。pwckはpasswd/shadowの各行（ホーム・シェル・GID・重複）を、grpckはgroup/gshadowを検査します。出力を読み、問題の種類ごとに整理してください。',
        ['report.jsonに問題を分類して保存', '読み取り専用の再検査コマンドをcmd.txtへ'], s3, c3, SOL3,
        ["echo '{}' > report.json\necho 'pwck' > cmd.txt",
         "python3 -c \"import json;json.dump({'missing_home':[],'bad_shell':[],'missing_group':[],'ghost_members':{}},open('report.json','w'))\"\nprintf 'pwck -r\\ngrpck -r\\n' > cmd.txt"],
        'pwckはpasswdとshadowの整合（フィールド数・重複UID・ホームの存在・シェルの存在・グループの存在）を検査し、grpckはgroupとgshadow（不明なメンバー・重複グループ）を検査します。-r は読み取り専用で何も修正せず、-s はソートします。対話で修正を求められる動作は誤操作しやすいので、まず-rで確認しましょう。',
        'メッセージの型ごとに正規表現で取り出します。', 'grepやpythonのreで分類し、json.dumpで保存します。')


# ---------------------------------------------------------------- 4 pwconv pwunconv grpconv grpunconv
def s4(ctx):
    users = [rnd('u') for _ in range(4)]
    hashes = {u: '$6$' + secrets.token_hex(4) + '$' + secrets.token_hex(12) for u in users}
    groups = [rnd('g') for _ in range(3)]
    gh = {g: '$6$' + secrets.token_hex(4) + '$' + secrets.token_hex(10) for g in groups}
    ctx.data.update(users=users, hashes=hashes, groups=groups, gh=gh)
    ctx.write('passwd', ''.join(f'{u}:{hashes[u]}:{1000 + i}:{1000 + i}:{u}:/home/{u}:/bin/bash\n' for i, u in enumerate(users)))
    ctx.write('group', ''.join(f'{g}:{gh[g]}:{2000 + i}:{users[i]},{users[i + 1]}\n' for i, g in enumerate(groups)))
    put(ctx, 'batch.txt', ''.join(f'{rnd("n")}:{secrets.token_hex(4)}:::新人:/home/n{i}:/bin/bash\n' for i in range(2)))
    ctx.write('requirements.txt', 'passwdとgroupは古い形式で、ハッシュが第2項目に直接入っている。pwconv/grpconvと同じ変換を手元で再現する。passwdの第2項目を x にして、ハッシュを新しい shadow（name:hash:19800:0:99999:7:::）へ。groupも同様にgshadow（name:hash::メンバー）へ。戻し用のpwunconvとgrpunconvを含む実行予定を cmd.txt に書く（pwconv, grpconv, pwunconv, grpunconv の4行）。加えて、passwd形式の新人一覧 batch.txt（平文パスワード入り）を一括登録する newusers を、SHA512で --root ./root 配下に対して実行する1行も足す。\n')


def c4(ctx):
    d = ctx.data
    pw = {l.split(':')[0]: l.split(':') for l in lines(ctx, 'passwd')}
    ctx.require(set(pw) == set(d['users']) and all(f[1] == 'x' for f in pw.values()), 'passwdの第2項目を全て x にします（ユーザー行は消さない）。')
    sh = {l.split(':')[0]: l.split(':') for l in lines(ctx, 'shadow')}
    ctx.require(set(sh) == set(d['users']), 'shadowに全ユーザーを移します。')
    for u in d['users']:
        f = sh[u]
        ctx.require(len(f) == 9 and f[1] == d['hashes'][u] and f[2] == '19800' and f[4] == '99999', f'{u} のshadow行（ハッシュ・日付）が違います。')
    gr = {l.split(':')[0]: l.split(':') for l in lines(ctx, 'group')}
    ctx.require(set(gr) == set(d['groups']) and all(f[1] == 'x' for f in gr.values()), 'groupの第2項目を全て x にします。')
    gs = {l.split(':')[0]: l.split(':') for l in lines(ctx, 'gshadow')}
    ctx.require(set(gs) == set(d['groups']), 'gshadowに全グループを移します。')
    for g in d['groups']:
        ctx.require(gs[g][1] == d['gh'][g] and gs[g][3] == gr[g][3], f'{g} のgshadow行が違います（第4項目はメンバー）。')
    cl = cmdlines(ctx, 'cmd.txt')
    for n in ('pwconv', 'grpconv', 'pwunconv', 'grpunconv'):
        tool(ctx, cl, n, 'cmd.txt')
    nu = tool(ctx, cl, 'newusers', 'cmd.txt')
    ctx.require(optv(nu, '-c', '--crypt-method') == 'SHA512' and optv(nu, '-R', '--root') == './root' and nu[-1] == 'batch.txt', 'newusers -c SHA512 -R ./root batch.txt にします。')
    order = [t[0] for t in cl]
    ctx.require(order.index('pwconv') < order.index('pwunconv') and order.index('grpconv') < order.index('grpunconv'), '変換を先、戻しを後に並べます。')


SOL4 = """awk -F: -v OFS=: '{print $1,$2,19800,0,99999,7,"","",""}' passwd > shadow
awk -F: -v OFS=: '{print $1,$2,"",$4}' group > gshadow
awk -F: -v OFS=: '{$2="x"; print}' passwd > p.tmp && mv p.tmp passwd
awk -F: -v OFS=: '{$2="x"; print}' group > g.tmp && mv g.tmp group
printf 'pwconv\\ngrpconv\\npwunconv\\ngrpunconv\\nnewusers -c SHA512 -R ./root batch.txt\\n' > cmd.txt"""
mission(4, 'pwconv・grpconv・pwunconv・grpunconv・newusersでシャドウ化と一括登録',
        '古いシステムではパスワードハッシュが誰でも読めるpasswd/groupに入っています。pwconvとgrpconvはハッシュをshadow/gshadowに移して x に置き換え、pwunconvとgrpunconvはその逆に統合し直します。',
        ['passwd/groupを x に置換しshadow/gshadowへ移す', '4コマンドの実行予定をcmd.txtへ'], s4, c4, SOL4,
        ["sed -i 's/^\\([^:]*\\):[^:]*:/\\1:x:/' passwd\nprintf 'pwconv\\n' > cmd.txt",
         "awk -F: -v OFS=: '{$2=\"x\"; print}' passwd > p.tmp && mv p.tmp passwd\nawk -F: -v OFS=: '{print $1,\"x\",19800,0,99999,7,\"\",\"\",\"\"}' passwd > shadow\nprintf 'pwconv\\ngrpconv\\npwunconv\\ngrpunconv\\n' > cmd.txt"],
        'pwconv/grpconvはpasswd/groupのハッシュをshadow/gshadowに移し x にします。newusersはpasswd形式の一覧から複数ユーザーを一括作成します（-cで方式）。pwunconv/grpunconvは逆にshadowの内容をpasswd等へ戻してshadowを削除する、移行や緊急時専用の操作です。shadowの第3項目は最終変更日（1970年からの日数）、第5項目は最大有効日数です。ハッシュは必ず置換前に取り出してからpasswdを書き換えます。',
        '置換より先にハッシュを取り出して別ファイルに保存します。', 'awkの-F: -v OFS=: で項目を組み替えます。')


# ---------------------------------------------------------------- 5 vipw vigr cppw cpgr
def s5(ctx):
    users = [rnd('u') for _ in range(4)]
    orph, miss = rnd('old'), users[3]
    ghost = rnd('ghost')
    ctx.data.update(users=users, orph=orph, miss=miss, ghost=ghost)
    put(ctx, 'passwd', ''.join(f'{u}:x:{1000 + i}:{1000 + i}:{u}:/home/{u}:/bin/bash\n' for i, u in enumerate(users)))
    put(ctx, 'shadow', ''.join(f'{u}:!:19800:0:99999:7:::\n' for u in users[:3]) + f'{orph}:!:19000:0:99999:7:::\n')
    put(ctx, 'group', f'ops:x:2000:{users[0]},{users[1]},{ghost}\ndev:x:2001:{users[2]}\n')
    ctx.write('requirements.txt', f'passwd/shadow/groupは原本。{miss} はshadow行がなく、{orph} はpasswdに存在しないのにshadowに残っている（pwckの典型）。さらにgroupのopsに存在しないメンバー {ghost} がいる。vipw -s/vigrなら排他ロック付きで直接編集するが、ここでは編集用コピー shadow.new と group.new を作る。shadow.newは余った行を削除し欠けた行は !（ロック）で追加、group.newは存在しないメンバーを外す。それを実機で本体へ反映するcppw -s と cpgr の実行予定を install.txt に2行書く。\n')


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    sh = [l.split(':') for l in lines(ctx, 'shadow.new')]
    ctx.require(sorted(f[0] for f in sh) == sorted(d['users']), 'shadow.newのユーザー集合がpasswdと一致しません。')
    byn = {f[0]: f for f in sh}
    ctx.require(len(byn[d['miss']]) == 9 and byn[d['miss']][1] == '!', '追加したshadow行は項目9個・ハッシュは ! にします。')
    ctx.require(all(byn[u][2] == '19800' for u in d['users'][:3]), '既存行は保持します。')
    gl = {l.split(':')[0]: l.split(':') for l in lines(ctx, 'group.new')}
    ctx.require(gl['ops'][3] == ','.join(d['users'][:2]) and gl['dev'][3] == d['users'][2], 'group.newはghostだけを外し他は保持します。')
    cl = cmdlines(ctx, 'install.txt')
    c = tool(ctx, cl, 'cppw')
    ctx.require('-s' in c and c[-1] == 'shadow.new', 'cppw -s shadow.new にします。')
    g = tool(ctx, cl, 'cpgr')
    ctx.require(g[-1] == 'group.new', 'cpgr group.new にします。')


SOL5 = """grep -v '^<<orph>>:' shadow > shadow.new
echo '<<miss>>:!:19800:0:99999:7:::' >> shadow.new
sed 's/,<<ghost>>$//' group > group.new
printf 'cppw -s shadow.new\\ncpgr group.new\\n' > install.txt"""
mission(5, 'vipw・vigr・cppw・cpgrでアカウントDBの整合を直す',
        'pwckがpasswdとshadowの食い違いを報告しました。vipwとvigrはロックを取ってpasswd/groupを安全に編集するコマンド（-sでshadow/gshadow）、cppwとcpgrは編集済みファイルを検査・ロックのうえ本体へ置き換えます。',
        ['shadow.newとgroup.newを作る', 'cppwとcpgrの実行予定をinstall.txtへ'], s5, c5, SOL5,
        ["cp shadow shadow.new\ncp group group.new\nprintf 'cppw shadow.new\\n' > install.txt",
         "grep -v '^<<orph>>:' shadow > shadow.new\nsed 's/,<<ghost>>$//' group > group.new\nprintf 'cppw -s shadow.new\\ncpgr group.new\\n' > install.txt"],
        'vipw/vigrはロックを取りエディタ（EDITOR）で編集、終了時に検査して反映します。cppw/cpgrは編集済みファイルを同じロック手順で本体へコピーします（-sでshadow/gshadow）。passwd/shadow/groupを直接viで編集しないのは、同時にpasswd等を更新するコマンドとの競合と、構文を壊す事故を防ぐためです。',
        'shadowのユーザー集合をpasswdと一致させ、欠けた行はロック済みで追加します。', 'grep -vで除去、echoで追加、sedでメンバー除去。')


# ---------------------------------------------------------------- 6 sudoers
def s6(ctx):
    svc = rnd('app') + '.service'
    port = 30000 + secrets.randbelow(2000)
    user = rnd('u')
    ctx.data.update(svc=svc, port=port, user=user)
    put(ctx, 'sudoers', 'Defaults\tenv_reset\nDefaults\tsecure_path="/usr/sbin:/usr/bin:/sbin:/bin"\nroot\tALL=(ALL:ALL) ALL\n%admin ALL=(ALL) ALL\n'
        f'%ops ALL=(ALL NOPASSWD /usr/bin/systemctl restart {svc}\n')
    put(ctx, 'visudo.out', 'sudoers:5:19: syntax error\n%ops ALL=(ALL NOPASSWD /usr/bin/systemctl restart ...\n                  ^\n')
    ctx.write('sudo_logsrvd.conf', '[server]\nlisten_address = 127.0.0.1:30344\n[iolog]\niolog_dir = /var/log/sudo-io\n')
    ctx.write('requirements.txt', f'(1) sudoersの5行目が壊れている（visudo.out）。sudoers.new に直し、opsは (root) として NOPASSWD: /usr/bin/systemctl restart {svc} だけを許可し、Defaults log_input, log_output を足す。(2) sudo_logsrvd.conf のlisten_addressを 0.0.0.0:{port} にし、iolog_dirを /srv/sudo-io にする。(3) cmd.txt に実行予定を4行: sudoedit /etc/sudoers.d/ops、visudo -cf sudoers.new、cvtsudoers -f json -o sudoers.json sudoers.new（JSON変換）、sudoreplay -l user {user}（-d ./iolog付き）。\n')


def c6(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = lines(ctx, 'sudoers.new')
    ops = [l for l in ls if l.startswith('%ops')]
    ctx.require(len(ops) == 1 and re.fullmatch(r'%ops\s+ALL=\(root\)\s+NOPASSWD:\s+/usr/bin/systemctl restart ' + re.escape(d['svc']), ops[0]), '%ops 行を「ALL=(root) NOPASSWD: /usr/bin/systemctl restart 対象」の形に直します。')
    ctx.require(not any('NOPASSWD' in l and 'ALL' in l.split('NOPASSWD')[1] for l in ls), 'NOPASSWD: ALL は許可しません。')
    txt = '\n'.join(ls)
    ctx.require('log_input' in txt and 'log_output' in txt, 'Defaults log_input, log_output を追加します。')
    ctx.require(any(l.startswith('%admin') for l in ls) and any(l.startswith('root') for l in ls), '他の行は残します。')
    c = {}
    for l in ctx.need_file('sudo_logsrvd.conf').splitlines():
        if '=' in l and not l.strip().startswith('#'):
            k, v = l.split('=', 1)
            c[k.strip()] = v.strip()
    ctx.require(c.get('listen_address') == f'0.0.0.0:{d["port"]}', 'listen_addressを指定どおりにします。')
    ctx.require(c.get('iolog_dir') == '/srv/sudo-io', 'iolog_dirを /srv/sudo-io にします。')
    cl = cmdlines(ctx, 'cmd.txt')
    ctx.require(tool(ctx, cl, 'sudoedit')[-1] == '/etc/sudoers.d/ops', 'sudoeditで /etc/sudoers.d/ops を編集します。')
    v = tool(ctx, cl, 'visudo')
    ctx.require('-c' in ''.join(x for x in v if x.startswith('-')) and v[-1] == 'sudoers.new', 'visudo -cf sudoers.new で構文検査します。')
    cv = tool(ctx, cl, 'cvtsudoers')
    ctx.require(optv(cv, '-f') == 'json' and optv(cv, '-o') == 'sudoers.json' and cv[-1] == 'sudoers.new', 'cvtsudoers -f json -o sudoers.json sudoers.new にします。')
    r = tool(ctx, cl, 'sudoreplay')
    ctx.require(optv(r, '-d') == './iolog' and '-l' in r and 'user' in r and d['user'] in r, 'sudoreplay -d ./iolog -l user ユーザー の形にします。')


SOL6 = """sed 's#^%ops .*#%ops ALL=(root) NOPASSWD: /usr/bin/systemctl restart <<svc>>#' sudoers > sudoers.new
echo 'Defaults log_input, log_output' >> sudoers.new
sed -i 's#^listen_address.*#listen_address = 0.0.0.0:<<port>>#; s#^iolog_dir.*#iolog_dir = /srv/sudo-io#' sudo_logsrvd.conf
cat > cmd.txt <<'EOF'
sudoedit /etc/sudoers.d/ops
visudo -cf sudoers.new
cvtsudoers -f json -o sudoers.json sudoers.new
sudoreplay -d ./iolog -l user <<user>>
EOF"""
mission(6, 'visudoで構文を直し、sudoedit・cvtsudoers・sudoreplay・sudo_logsrvdを使う',
        'sudoersの1行が壊れ、visudoが構文エラーを報告しています。sudoeditで安全に編集し、visudo -cで検査、cvtsudoersで他形式へ変換、sudo_logsrvdで入出力ログを集中収集し、sudoreplayで再生・検索します。',
        ['sudoers.newを修正してログ設定を追加', 'sudo_logsrvd.confを編集', '4コマンドをcmd.txtへ'], s6, c6, SOL6,
        ["cp sudoers sudoers.new\necho 'ALL ALL=(ALL) NOPASSWD: ALL' >> sudoers.new",
         "sed 's#^%ops .*#%ops ALL=(root) NOPASSWD: /usr/bin/systemctl restart <<svc>>#' sudoers > sudoers.new\necho 'Defaults log_input, log_output' >> sudoers.new\nprintf 'visudo sudoers.new\\n' > cmd.txt"],
        'visudoはロック付きで構文を検査してから反映し、-cf で任意ファイルの検査だけを行えます。sudoeditは権限昇格したコピーを編集して書き戻す安全な編集方法です。cvtsudoersはsudoersをJSON/LDIF等へ変換します。sudo_logsrvdはネットワーク越しにsudoのI/Oログを受け、sudoreplay -d ログDIR -l user 名 で検索・再生します。NOPASSWD: ALL は避け、必要なコマンドだけに限定します。',
        '壊れた行は括弧の閉じ忘れとコロンの欠落です。', 'sedで該当行を置換し、設定は=区切りの行を書き換えます。')


# ---------------------------------------------------------------- 7 update-alternatives chcon runcon
def s7(ctx):
    names = ['/usr/bin/vim.basic', '/usr/bin/nano', '/usr/bin/emacs', '/usr/bin/ed']
    prios = secrets.SystemRandom().sample(range(20, 90), 4)
    best = names[prios.index(max(prios))]
    new = f'/opt/{rnd("ed")}/bin/editor'
    dom = secrets.choice(['httpd_t', 'httpd_sys_script_t', 'ftpd_t'])
    p = [f'/srv/www/{rnd("p")}.html' for _ in range(4)]
    bad = [p[1], p[3]]
    ctx.data.update(best=best, new=new, newprio=max(prios) + 10, dom=dom, bad=bad)
    put(ctx, 'display.txt', 'editor - manual mode\n  link best version is ' + best + '\n  link currently points to /usr/bin/nano\n  link editor is /etc/alternatives/editor\n'
        + ''.join(f'{n} - priority {pr}\n' for n, pr in zip(names, prios)))
    typ = ['httpd_sys_content_t', 'user_home_t', 'httpd_sys_content_t', 'tmp_t']
    put(ctx, 'ls-Z.txt', ''.join(f'unconfined_u:object_r:{t}:s0 {q}\n' for t, q in zip(typ, p)))
    ctx.mkdir('etc/alternatives')
    ctx.write('requirements.txt', f'(1) display.txt（update-alternatives --display editor の記録）を読み、最優先の候補へ etc/alternatives/editor のシンボリックリンクを張る（--set 相当）。alt.txt に update-alternatives の実行予定を2行: --altdir ./etc/alternatives --admindir ./var/alt を付けた --set editor 最優先候補、と --install ./bin/editor editor {new} 優先度（最高より10高く）。(2) ls-Z.txt（ls -Z の記録）で httpd_sys_content_t でないファイルを洗い出し、fix.sh に chcon -t httpd_sys_content_t を1ファイル1行（SELinux文脈の修復、実行はしない）と、最後に runcon -t {dom} -- ./probe.sh を書く。\n')


def c7(ctx):
    need_ro(ctx)
    d = ctx.data
    import os
    l = ctx.p('etc/alternatives/editor')
    ctx.require(os.path.islink(l) and os.readlink(l) == d['best'], 'etc/alternatives/editor を最優先候補へ向けます。')
    cl = cmdlines(ctx, 'alt.txt')
    ctx.require(all(t[0] == 'update-alternatives' for t in cl) and len(cl) == 2, 'update-alternatives の行を2行にします。')
    for t in cl:
        ctx.require(optv(t, '--altdir') == './etc/alternatives' and optv(t, '--admindir') == './var/alt', '--altdir と --admindir でサンドボックスに閉じます。')
    st = [t for t in cl if '--set' in t]
    ctx.require(len(st) == 1 and st[0][st[0].index('--set') + 1:] == ['editor', d['best']], '--set editor 最優先候補 にします。')
    ins = [t for t in cl if '--install' in t]
    ctx.require(len(ins) == 1 and ins[0][ins[0].index('--install') + 1:] == ['./bin/editor', 'editor', d['new'], str(d['newprio'])], '--install リンク 名前 パス 優先度 の順です。')
    fx = cmdlines(ctx, 'fix.sh')
    ch = [t for t in fx if t[0] == 'chcon']
    ctx.require(sorted(t[-1] for t in ch) == sorted(d['bad']) and all(optv(t, '-t', '--type') == 'httpd_sys_content_t' for t in ch), 'chcon -t httpd_sys_content_t を、ずれたファイルだけに書きます。')
    rc = [t for t in fx if t[0] == 'runcon']
    ctx.require(len(rc) == 1 and optv(rc[0], '-t') == d['dom'] and rc[0][-1] == './probe.sh' and fx[-1] == rc[0], 'runcon -t ドメイン -- ./probe.sh を最後に書きます。')


SOL7 = """ln -sfn <<best>> etc/alternatives/editor
cat > alt.txt <<'EOF'
update-alternatives --altdir ./etc/alternatives --admindir ./var/alt --set editor <<best>>
update-alternatives --altdir ./etc/alternatives --admindir ./var/alt --install ./bin/editor editor <<new>> <<newprio>>
EOF
awk '$1 !~ /httpd_sys_content_t/ {print "chcon -t httpd_sys_content_t " $2}' ls-Z.txt > fix.sh
echo 'runcon -t <<dom>> -- ./probe.sh' >> fix.sh"""
mission(7, 'update-alternativesで既定を切替え、chconとruncon でSELinux文脈を診断する',
        '既定のeditorが手動でnanoに固定されたままです。update-alternativesの記録から最優先の候補へ切り替え、新しい候補も登録します。また、Webコンテンツの一部にSELinuxのファイル文脈の誤りがあり、chconで修復、runconで特定ドメインの動作確認をします。',
        ['alternativesのリンクと実行予定', '誤った文脈をchconで修復する行', 'runconの検証行'], s7, c7, SOL7,
        ["ln -sfn /usr/bin/nano etc/alternatives/editor\necho 'update-alternatives --set editor /usr/bin/nano' > alt.txt",
         "ln -sfn <<best>> etc/alternatives/editor\nprintf 'update-alternatives --altdir ./etc/alternatives --admindir ./var/alt --set editor <<best>>\\n' > alt.txt\nawk '{print \"chcon -t httpd_sys_content_t \" $2}' ls-Z.txt > fix.sh"],
        'update-alternativesは /etc/alternatives 経由で同名コマンドの実体を切り替えます（--install登録、--set手動、--auto自動、--display確認）。chconは文脈を一時的に変更するだけで、restorecon/semanage fcontextの規則と再ラベルで元に戻る点に注意します。runconは指定の文脈でコマンドを実行します。この課題ではSELinuxを実際には操作せず、記録を診断します。',
        '優先度が最大の候補が自動モードで選ばれる候補です。', 'sortで優先度を比較し、awkでls -Zの文脈列を判定します。')


# ---------------------------------------------------------------- 8 systemd-cat systemd-path systemd-escape
def esc(p):
    p = p.strip('/')
    if not p:
        return '-'
    o = ''
    for i, ch in enumerate(p):
        if ch == '/':
            o += '-'
        elif (ch.isascii() and ch.isalnum()) or ch in ':_' or (ch == '.' and i > 0):
            o += ch
        else:
            o += '\\x%02x' % ord(ch)
    return o


def s8(ctx):
    u = rnd('u')
    tag = rnd('job')
    paths = ['/mnt/' + rnd('backup-disk'), '/var/lib/' + rnd('my_app') + '/data dir', '/srv/' + rnd('web') + '/media-2024']
    ctx.data.update(u=u, tag=tag, paths=paths, units=[esc(p) + '.mount' for p in paths])
    put(ctx, 'path.out', f'temporary: /tmp\nuser-configuration: /home/{u}/.config\nsystem-configuration: /etc\nsystemd-system-unit: /usr/lib/systemd/system\nsystemd-user-unit: /usr/lib/systemd/user\nsearch-binaries: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin\n')
    put(ctx, 'paths.txt', '\n'.join(paths) + '\n')
    ctx.write('job.sh', '#!/bin/bash\necho "start"\n')
    ctx.write('requirements.txt', f'(1) path.out（systemd-pathの出力）から user-configuration と systemd-system-unit の値を paths.json（同名キー）に。(2) paths.txtの各パスを .mount ユニット名にした systemd-escape -p --suffix=mount の結果を、順に escapes.txt へ1行ずつ。(3) log.sh に、./job.sh の出力をsystemd-cat -t {tag} でジャーナルへ送り、失敗時の通知を priority err の systemd-cat -t {tag} -p err で送る2行を書く。\n')


def c8(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'paths.json')
    ctx.require(r.get('user-configuration') == f'/home/{d["u"]}/.config' and r.get('systemd-system-unit') == '/usr/lib/systemd/system', 'paths.jsonの値が違います。')
    ctx.require(lines(ctx, 'escapes.txt') == d['units'], 'escapes.txtのユニット名が違います（空白はエスケープ、/は-、-は\\x2d）。')
    segs = []
    for ln in lines(ctx, 'log.sh'):
        if ln.strip() and not ln.strip().startswith('#'):
            segs.append([tk(ctx, x) for x in ln.split('|')])
    cats = [(t, ln) for ln in segs for t in ln if t and t[0] == 'systemd-cat' and optv(t, '-t', '--identifier') == d['tag']]
    ctx.require(any(optv(t, '-p', '--priority') == 'err' for t, _ in cats), 'systemd-cat -t タグ -p err の行がありません。')
    ctx.require(any(optv(t, '-p', '--priority') is None and ln[0] and ln[0][0] == './job.sh' for t, ln in cats), './job.sh の出力をsystemd-cat -t タグ に渡す行が必要です。')


SOL8 = """python3 - <<'PY'
import json
d = dict(l.split(': ', 1) for l in open('path.out').read().splitlines())
json.dump({k: d[k] for k in ('user-configuration', 'systemd-system-unit')}, open('paths.json', 'w'))
def esc(p):
    p = p.strip('/'); o = ''
    for i, ch in enumerate(p):
        o += '-' if ch == '/' else ch if (ch.isalnum() or ch in ':_' or (ch == '.' and i)) else '\\\\x%02x' % ord(ch)
    return o + '.mount'
open('escapes.txt', 'w').write(''.join(esc(l.rstrip('\\n')) + '\\n' for l in open('paths.txt')))
PY
cat > log.sh <<'EOF'
./job.sh 2>&1 | systemd-cat -t <<tag>>
echo 'job failed' | systemd-cat -t <<tag>> -p err
EOF"""
mission(8, 'systemd-path・systemd-escape・systemd-catで場所とユニット名とログを扱う',
        'ユニット名の自動生成（スペース入りのマウントポイント）とログの送り先を整えます。systemd-pathはsystemdが使う各種ディレクトリを表示し、systemd-escapeは任意の文字列やパスをユニット名に使える形へ変換し、systemd-catは標準入出力をジャーナルへ送ります。',
        ['paths.jsonへ2つのパスを抽出', 'escapes.txtにマウントユニット名', 'log.shでsystemd-catを使う'], s8, c8, SOL8,
        ["echo '{}' > paths.json\nsed 's#/#-#g' paths.txt > escapes.txt\necho './job.sh' > log.sh",
         "echo '{}' > paths.json\ntr '/ ' '--' < paths.txt > escapes.txt\necho './job.sh | systemd-cat' > log.sh"],
        'systemd-escape -p はパスを「/ → -」「その他の特殊文字 → \\xNN」に変換し、--suffix=mount で単位名にします（元のハイフンも\\x2dになる）。systemd-path 名前 で該当ディレクトリを得られ、systemd-cat -t 識別子 -p 優先度 コマンド でログのタグと重要度を付けてジャーナルへ送れます。',
        'ハイフンと空白はそれぞれ \\x2d、\\x20 になります。', 'pythonで文字ごとに規則を適用するか、実機ではsystemd-escapeを使います。')


# ---------------------------------------------------------------- 9 systemd-tmpfiles systemd-sysusers
def s9(ctx):
    app = rnd('app')
    age = secrets.choice(['7d', '10d', '30d'])
    ctx.data.update(app=app, age=age)
    ctx.mkdir('root/etc/tmpfiles.d')
    ctx.mkdir('root/etc/sysusers.d')
    ctx.write('requirements.txt', f'サービス {app} の実行ユーザーとディレクトリを宣言的に用意する。(1) root/etc/sysusers.d/{app}.conf に、システムグループ {app}（g）とシステムユーザー {app}（u、説明 "{app} service"、ホーム /var/lib/{app}、シェル /usr/sbin/nologin）。(2) root/etc/tmpfiles.d/{app}.conf に、d /run/{app} 0750 {app} {app} -、d /var/cache/{app} 0755 {app} {app} {age}（古いものを自動削除）、f /var/log/{app}.log 0640 {app} {app} -。(3) cmd.txt に、ユーザー作成が先でディレクトリ作成が後になるよう systemd-sysusers と systemd-tmpfiles --create の実行予定（どちらも --root ./root）を2行。\n')


def c9(ctx):
    d = ctx.data
    a = d['app']

    def rows(name):
        return [tk(ctx, l) for l in lines(ctx, name) if l.strip() and not l.strip().startswith('#')]
    su = rows(f'root/etc/sysusers.d/{a}.conf')
    ctx.require(any(r[0] == 'g' and r[1] == a for r in su), f'g {a} の行がありません。')
    u = [r for r in su if r[0] == 'u' and r[1] == a]
    ctx.require(len(u) == 1 and len(u[0]) >= 6 and u[0][3] == f'{a} service' and u[0][4] == f'/var/lib/{a}' and u[0][5] == '/usr/sbin/nologin', 'u 行は「u 名前 ID 説明 ホーム シェル」の形です（IDは -）。')
    tf = {(r[0], r[1]): r for r in rows(f'root/etc/tmpfiles.d/{a}.conf')}
    r = tf.get(('d', f'/run/{a}'))
    ctx.require(r and r[2:5] == ['0750', a, a], f'd /run/{a} 0750 {a} {a} の行です。')
    r = tf.get(('d', f'/var/cache/{a}'))
    ctx.require(r and r[2:6] == ['0755', a, a, d['age']], f'd /var/cache/{a} の行に age {d["age"]} を付けます。')
    r = tf.get(('f', f'/var/log/{a}.log'))
    ctx.require(r and r[2:5] == ['0640', a, a], f'f /var/log/{a}.log 0640 {a} {a} の行です。')
    cl = cmdlines(ctx, 'cmd.txt')
    names = [t[0] for t in cl]
    ctx.require('systemd-sysusers' in names and 'systemd-tmpfiles' in names, '2つのコマンドを書きます。')
    ctx.require(names.index('systemd-sysusers') < names.index('systemd-tmpfiles'), 'ユーザー作成（sysusers）を先にします。')
    ctx.require(all(optv(t, '--root') == './root' for t in cl), '両方に --root ./root を付けます。')
    ctx.require('--create' in tool(ctx, cl, 'systemd-tmpfiles'), 'systemd-tmpfiles --create です。')


SOL9 = """cat > root/etc/sysusers.d/<<app>>.conf <<'EOF'
g <<app>> -
u <<app>> - "<<app>> service" /var/lib/<<app>> /usr/sbin/nologin
EOF
cat > root/etc/tmpfiles.d/<<app>>.conf <<'EOF'
d /run/<<app>> 0750 <<app>> <<app>> -
d /var/cache/<<app>> 0755 <<app>> <<app>> <<age>>
f /var/log/<<app>>.log 0640 <<app>> <<app>> -
EOF
printf 'systemd-sysusers --root ./root\\nsystemd-tmpfiles --create --root ./root\\n' > cmd.txt"""
mission(9, 'systemd-sysusersとsystemd-tmpfilesで実行環境を宣言する',
        '新サービスの実行ユーザーと作業ディレクトリを、手作業ではなく設定ファイルで再現可能にします。systemd-sysusersはsysusers.dからシステムユーザー/グループを作り、systemd-tmpfilesはtmpfiles.dからディレクトリ・ファイルの作成、権限、古いファイルの削除を行います。',
        ['sysusers.dの設定', 'tmpfiles.dの設定', '実行順をcmd.txtへ'], s9, c9, SOL9,
        ["printf 'useradd <<app>>\\nmkdir /run/<<app>>\\n' > cmd.txt",
         "printf 'g <<app>> -\\nu <<app>> - \"<<app>> service\" /var/lib/<<app>> /usr/sbin/nologin\\n' > root/etc/sysusers.d/<<app>>.conf\nprintf 'd /run/<<app>> 0750 <<app>> <<app>> -\\n' > root/etc/tmpfiles.d/<<app>>.conf\nprintf 'systemd-tmpfiles --create --root ./root\\nsystemd-sysusers --root ./root\\n' > cmd.txt"],
        'sysusers.dの書式は「種別 名前 ID 説明 ホーム シェル」で、g/u/mなどを使います。tmpfiles.dは「種別 パス モード 所有者 グループ 期間」で、dは作成、fはファイル、期間はsystemd-tmpfiles --cleanで古いものを削除する基準です。ユーザーが先に存在しないと所有者を指定できないため、sysusersを先に実行します。--root で実OSを触らず検証できます。',
        '所有者に指定するユーザーが先に必要です。', '各設定をheredocで書き、順序をcmd.txtに。')


# ---------------------------------------------------------------- 10 systemd-cgls systemd-cgtop
def s10(ctx):
    names = [rnd('svc') + '.service' for _ in range(4)]
    cpu = secrets.SystemRandom().sample(range(5, 95), 4)
    mem = secrets.SystemRandom().sample(range(64, 3000), 4)
    pids = secrets.SystemRandom().sample(range(1000, 9000), 5)
    tasks = secrets.SystemRandom().sample(range(2, 90), 4)

    def fm(m):
        return f'{m / 1024:.1f}G' if m >= 1024 else f'{m}M'
    rows = ''.join(f'/system.slice/{n} {t} {c:.1f} {fm(m)} - -\n' for n, t, c, m in zip(names, tasks, cpu, mem))
    put(ctx, 'cgtop.txt', 'Control Group                      Tasks  %CPU  Memory  Input/s Output/s\n/ 500 100.0 4.0G - -\n/system.slice 300 90.0 3.5G - -\n' + rows)
    target = pids[4]
    owner = secrets.randbelow(4)
    tree = '-.slice\n├─user.slice\n│ └─session-1.scope\n│   └─' + str(pids[0] + 10000) + ' bash\n└─system.slice\n'
    for i, n in enumerate(names):
        last = i == 3
        tree += ('  └─' if last else '  ├─') + n + '\n'
        pfx = '    ' if last else '  │ '
        tree += pfx + '└─' + str(target if i == owner else pids[i % 4]) + ' /usr/bin/' + n.split('.')[0] + '\n'
    put(ctx, 'cgls.txt', tree)
    ctx.data.update(top_cpu=names[cpu.index(max(cpu))], top_mem=names[mem.index(max(mem))], top_tasks=names[tasks.index(max(tasks))], pid=target, pid_unit=names[owner])
    ctx.write('requirements.txt', f'cgtop.txt（systemd-cgtop -b -n1 の記録）とcgls.txt（systemd-cglsの記録）から、report.json に cpu（%CPU最大のサービス）、memory（メモリ最大）、tasks（タスク数最大）、pid_unit（PID {target} が属するユニット）を保存する。\n')


def c10(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'report.json')
    for k, v in (('cpu', d['top_cpu']), ('memory', d['top_mem']), ('tasks', d['top_tasks']), ('pid_unit', d['pid_unit'])):
        ctx.require(r.get(k) == v, f'{k} が違います（スライス自体や行頭の / は除く、サービス名のみ）。')


SOL10 = """python3 - <<'PY'
import json, re
rows = [l.split() for l in open('cgtop.txt').read().splitlines()[1:] if l.startswith('/system.slice/')]
def mb(s): return float(s[:-1]) * (1024 if s[-1] == 'G' else 1)
name = lambda r: r[0].split('/')[-1]
rep = {'cpu': name(max(rows, key=lambda r: float(r[2]))), 'memory': name(max(rows, key=lambda r: mb(r[3]))), 'tasks': name(max(rows, key=lambda r: int(r[1])))}
cur = None
for l in open('cgls.txt'):
    m = re.search(r'([\\w.-]+\\.service)$', l.strip())
    if m: cur = m.group(1)
    elif re.search(r'[└├]─<<pid>> ', l): rep['pid_unit'] = cur
json.dump(rep, open('report.json', 'w'))
PY"""
mission(10, 'systemd-cglsとsystemd-cgtopでcgroupの資源消費を特定する',
        '負荷の高いサーバーでどのサービスが資源を食っているかを調べます。systemd-cgtopはcgroup単位のCPU・メモリ・タスク数を表示し、systemd-cglsはcgroupツリーでどのプロセスがどのユニットに属するかを表示します。記録を読んで原因ユニットを特定してください。',
        ['CPU・メモリ・タスク数が最大のユニット', '指定PIDが属するユニット'], s10, c10, SOL10,
        ["echo '{}' > report.json",
         "python3 -c \"import json;json.dump({'cpu':'/system.slice','memory':'/system.slice','tasks':'/system.slice','pid_unit':'-.slice'},open('report.json','w'))\""],
        'systemd-cgtopは表を%CPU・メモリ・タスク順などで並べ替えて眺められます（-b -n1 で一覧を1回出力）。メモリのG/Mの単位に注意しましょう。systemd-cglsはsystemdが管理するcgroup階層（スライス→ユニット→プロセス）を表示し、PIDから所属ユニットを逆引きできます。/system.slice のような親は合計値なので比較対象に含めません。',
        '単位G/Mをそろえて比較し、親のスライス行は除きます。', 'awkやpythonで列を比較し、cglsは上から読んで最後に出たユニットを覚えます。')


# ---------------------------------------------------------------- 11 systemd-inhibit systemd-notify systemd-socket-activate
def s11(ctx):
    who = rnd('backup')
    port = 20000 + secrets.randbelow(3000)
    st = rnd('ready')
    ctx.data.update(who=who, port=port, st=st)
    ctx.write('backup.sh', '#!/bin/bash\n# 夜間バックアップ（偽物）\nsleep 1\n')
    ctx.write('server.sh', '#!/bin/bash\n# inetd風に標準入出力でHTTP風応答を返す（偽物）\ncat\n')
    ctx.write('daemon.sh', '#!/bin/bash\nload_config\n# TODO: ここで準備完了をsystemdに通知する\nexec serve\n')
    ctx.write('requirements.txt', f'(1) cmd.txt の1行目: ./backup.sh の実行中に shutdown と sleep を --mode=block で止める systemd-inhibit（--who {who}、--why付き）。(2) daemon.sh のTODO行を、準備完了をsystemdへ知らせる systemd-notify --ready --status="{st}" に置き換える（Type=notifyユニット用）。(3) cmd.txt の2行目: ポート {port} で接続を待ち、接続時に ./server.sh を起動する systemd-socket-activate -l {port} ./server.sh。\n')


def c11(ctx):
    d = ctx.data
    cl = cmdlines(ctx, 'cmd.txt')
    a = tool(ctx, cl, 'systemd-inhibit')
    ctx.require(set((optv(a, '--what') or '').split(':')) == {'shutdown', 'sleep'}, '--what=shutdown:sleep を指定します。')
    ctx.require(optv(a, '--who') == d['who'] and optv(a, '--mode') == 'block' and optv(a, '--why'), '--who、--why、--mode=block を指定します。')
    ctx.require(a[-1] == './backup.sh', '最後に ./backup.sh を実行します。')
    b = tool(ctx, cl, 'systemd-socket-activate')
    ctx.require(optv(b, '-l', '--listen') == str(d['port']) and b[-1] == './server.sh', f'systemd-socket-activate -l {d["port"]} ./server.sh にします。')
    ls = lines(ctx, 'daemon.sh')
    idx = [i for i, l in enumerate(ls) if l.strip().startswith('systemd-notify')]
    ctx.require(len(idx) == 1, 'daemon.sh に systemd-notify を1行入れます。')
    t = tk(ctx, ls[idx[0]])
    ctx.require('--ready' in t and optv(t, '--status') == d['st'], '--ready と --status を指定します。')
    ctx.require(ls.index('load_config') < idx[0] < max(i for i, l in enumerate(ls) if l.strip() == 'exec serve'), '準備後・起動前に通知します。')
    ctx.require(not any('TODO' in l for l in ls), 'TODO行は置き換えます。')


SOL11 = """sed -i 's#^\\# TODO.*#systemd-notify --ready --status="<<st>>"#' daemon.sh
cat > cmd.txt <<'EOF'
systemd-inhibit --what=shutdown:sleep --who=<<who>> --why="nightly backup" --mode=block ./backup.sh
systemd-socket-activate -l <<port>> ./server.sh
EOF"""
mission(11, 'systemd-inhibit・systemd-notify・systemd-socket-activateを使う',
        '長時間のバックアップ中に電源が落ちないようにし、デーモンの準備完了をsystemdへ正しく伝え、ソケット活性化を手元で試します。systemd-inhibitは排他的ロックを取りながらコマンドを実行し、systemd-notifyはType=notifyのサービスの状態をsystemdへ通知し、systemd-socket-activateはソケット待ち受けを一時的に作ります。',
        ['inhibitとsocket-activateをcmd.txtへ', 'daemon.shに通知行を追加'], s11, c11, SOL11,
        ["echo './backup.sh' > cmd.txt",
         "sed -i 's#^\\# TODO.*#systemd-notify --ready#' daemon.sh\nprintf 'systemd-inhibit ./backup.sh\\nsystemd-socket-activate ./server.sh\\n' > cmd.txt"],
        'systemd-inhibit --what=shutdown:sleep は停止・スリープを抑止するロックを取り、ロックは子コマンドの終了で自動的に解放されます。--mode=block は強制、delay は猶予です。systemd-notify --ready はTYPE=notifyのユニットが「起動完了」を知らせるために使い、--status は systemctl status に表示されます。systemd-socket-activate は接続が来たらコマンドを起動し、起動時にはファイルディスクリプタが渡されます。',
        '通知は初期化の完了後に置きます。', 'sedでTODO行を置換し、cmd.txtはheredocで。')


# ---------------------------------------------------------------- 12 systemd-delta systemd-firstboot systemd-hwdb
def s12(ctx):
    names = [rnd('u') for _ in range(5)]
    ctx.data.update(names=names, host=rnd('node'), tz=secrets.choice(['Asia/Tokyo', 'Europe/Berlin', 'America/Chicago']),
                    vid=secrets.token_hex(2), pid=secrets.token_hex(2), vidU='', pidU='', dpi=secrets.choice(['800', '1200', '1600']))
    put(ctx, 'delta.txt', f'[EXTENDED]   /etc/systemd/system/{names[0]}.service.d/override.conf -> /usr/lib/systemd/system/{names[0]}.service\n'
        f'[OVERRIDDEN] /etc/systemd/system/{names[1]}.service -> /usr/lib/systemd/system/{names[1]}.service\n'
        f'[MASKED]     /etc/systemd/system/{names[2]}.service -> /usr/lib/systemd/system/{names[2]}.service\n'
        f'[OVERRIDDEN] /etc/systemd/system/{names[3]}.timer -> /usr/lib/systemd/system/{names[3]}.timer\n'
        f'[EQUIVALENT] /etc/systemd/system/{names[4]}.service -> /usr/lib/systemd/system/{names[4]}.service\n')
    ctx.data['vidU'] = ctx.data['vid'].upper()
    ctx.data['pidU'] = ctx.data['pid'].upper()
    ctx.mkdir('image/etc/udev/hwdb.d')
    ctx.write('requirements.txt', f'(1) delta.txt（systemd-deltaの記録）を種別で整理し、delta.json に {{"extended":[..],"overridden":[..],"masked":[..]}}（ユニット名。EQUIVALENTは無視）。(2) 新イメージ ./image の初期設定として、ホスト名 {ctx.data["host"]}、タイムゾーン {ctx.data["tz"]}、ロケール ja_JP.UTF-8 を設定するsystemd-firstbootを cmd.txt の1行目に。(3) udevの追加ハードウェア情報として image/etc/udev/hwdb.d/70-local.hwdb に、USBマウス v{ctx.data["vid"].upper()}p{ctx.data["pid"].upper()} のエントリ「mouse:usb:v{ctx.data["vid"].upper()}p{ctx.data["pid"].upper()}:*」と1つ字下げした MOUSE_DPI={ctx.data["dpi"]}@1000 を書き、cmd.txtの2行目にsystemd-hwdb update --root ./image、3行目にsystemd-hwdb query mouse:usb:v…（そのキー）を書く。\n')


def c12(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'delta.json')
    n = d['names']
    exp = {'extended': [n[0] + '.service'], 'overridden': sorted([n[1] + '.service', n[3] + '.timer']), 'masked': [n[2] + '.service']}
    ctx.require({k: sorted(v) for k, v in r.items()} == exp, 'extended/overridden/masked の整理が違います。')
    cl = cmdlines(ctx, 'cmd.txt')
    f = tool(ctx, cl, 'systemd-firstboot')
    ctx.require(optv(f, '--root') == './image' and optv(f, '--hostname') == d['host'] and optv(f, '--timezone') == d['tz'] and optv(f, '--locale') == 'ja_JP.UTF-8', 'systemd-firstboot --root ./image --hostname --timezone --locale を指定します。')
    key = f'mouse:usb:v{d["vid"].upper()}p{d["pid"].upper()}:*'
    ls = lines(ctx, 'image/etc/udev/hwdb.d/70-local.hwdb')
    ctx.require(key in ls and ls[ls.index(key) + 1] == f' MOUSE_DPI={d["dpi"]}@1000', 'hwdbのエントリは「マッチ行」の次に1文字字下げした MOUSE_DPI 行です。')
    h = [t for t in cl if t[0] == 'systemd-hwdb']
    ctx.require(len(h) == 2 and h[0][1] == 'update' and optv(h[0], '--root') == './image', '2行目は systemd-hwdb update --root ./image です。')
    ctx.require(h[1][1] == 'query' and h[1][-1] == f'mouse:usb:v{d["vid"].upper()}p{d["pid"].upper()}:', '3行目は systemd-hwdb query で具体的なキーを指定します。')


SOL12 = """python3 - <<'PY'
import json, re, os
r = {'extended': [], 'overridden': [], 'masked': []}
for l in open('delta.txt'):
    m = re.match(r'\\[(\\w+)\\]\\s+\\S+ -> (\\S+)', l)
    if m and m.group(1).lower() in r:
        r[m.group(1).lower()].append(os.path.basename(m.group(2)))
json.dump(r, open('delta.json', 'w'))
PY
cat > image/etc/udev/hwdb.d/70-local.hwdb <<'EOF'
mouse:usb:v<<vidU>>p<<pidU>>:*
 MOUSE_DPI=<<dpi>>@1000
EOF
cat > cmd.txt <<'EOF'
systemd-firstboot --root ./image --hostname=<<host>> --timezone=<<tz>> --locale=ja_JP.UTF-8
systemd-hwdb update --root ./image
systemd-hwdb query mouse:usb:v<<vidU>>p<<pidU>>:
EOF"""
mission(12, 'systemd-delta・systemd-firstboot・systemd-hwdbで差分と初期設定とudevデータを扱う',
        '設定の「上書き」が増え、どれが元の定義と違うのか不明です。systemd-deltaはvendor定義と/etc側の上書き・拡張・マスクを一覧します。さらに新イメージの初期設定をsystemd-firstbootで行い、udevのハードウェアデータベースへsystemd-hwdbで追記を反映します。',
        ['delta.jsonで種別ごとに整理', 'firstbootとhwdbの行をcmd.txtへ', '70-local.hwdbを作る'], s12, c12, SOL12,
        ["echo '{}' > delta.json\necho 'systemd-firstboot' > cmd.txt",
         "mkdir -p image/etc/udev/hwdb.d\nprintf 'mouse:usb:v<<vidU>>p<<pidU>>:*\\nMOUSE_DPI=<<dpi>>@1000\\n' > image/etc/udev/hwdb.d/70-local.hwdb\necho 'systemd-hwdb update' > cmd.txt"],
        'systemd-deltaの[EXTENDED]はdrop-inで拡張、[OVERRIDDEN]は/etcのファイルが丸ごと上書き、[MASKED]は無効化（/dev/nullへのリンク）、[EQUIVALENT]は内容が同じです。systemd-firstbootは初回起動時の設定（ロケール・ホスト名・タイムゾーン・root設定）を--rootで事前に埋め込めます。systemd-hwdb updateは/etc/udev/hwdb.d のエントリをhwdb.binに再構築し、queryでキーに対する属性を確認します。udevの規則ファイルと混同しないようにしましょう。',
        '矢印の右側のパスの末尾がユニット名です。', 'reで種別と右辺を取り出し、hwdbは「マッチ行＋字下げした属性行」です。')


# ---------------------------------------------------------------- 13 systemd-mount systemd-umount systemd-ask-password systemd-creds
def s13(ctx):
    d = dict(label=rnd('DATA'), mnt='/mnt/' + rnd('usb'), to=str(10 * (1 + secrets.randbelow(6))), cname=rnd('dbpass'))
    ctx.data.update(d)
    ctx.write('requirements.txt', f'rootなしで外部ディスクを扱い、秘密を安全に受け渡す手順を cmds.txt に1行ずつ書く。(1) ラベル {d["label"]} のext4を {d["mnt"]} に読み取り専用でsystemd-mount（--type と --options）。(2) 使用後に systemd-umount {d["mnt"]}。(3) 対話で秘密を受ける systemd-ask-password を --timeout={d["to"]} と質問文付きで。(4) その秘密を標準入力から暗号化し ./{d["cname"]}.cred に保存する systemd-creds encrypt --name={d["cname"]} - ./{d["cname"]}.cred。実行はしません。\n')


def c13(ctx):
    d = ctx.data
    cl = cmdlines(ctx, 'cmds.txt')
    m = tool(ctx, cl, 'systemd-mount')
    ctx.require(optv(m, '--type', '-t') == 'ext4' and 'ro' in (optv(m, '--options', '-o') or '').split(','), '--type=ext4 --options=ro を指定します。')
    ctx.require(m[-2:] == [f'/dev/disk/by-label/{d["label"]}', d['mnt']], '「/dev/disk/by-label/ラベル マウント先」の順に末尾へ置きます。')
    u = tool(ctx, cl, 'systemd-umount')
    ctx.require(u[-1] == d['mnt'], 'systemd-umount マウント先 です。')
    a = tool(ctx, cl, 'systemd-ask-password')
    ctx.require(optv(a, '--timeout') == d['to'] and len(a) >= 3 and not a[-1].startswith('-'), '--timeout=秒 と質問文を指定します。')
    c = tool(ctx, cl, 'systemd-creds')
    ctx.require(c[1] == 'encrypt' and optv(c, '--name') == d['cname'] and c[-2:] == ['-', f'./{d["cname"]}.cred'], 'systemd-creds encrypt --name=名 - ./出力 の形にします。')


SOL13 = """cat > cmds.txt <<'EOF'
systemd-mount --type=ext4 --options=ro /dev/disk/by-label/<<label>> <<mnt>>
systemd-umount <<mnt>>
systemd-ask-password --timeout=<<to>> "Database password:"
systemd-creds encrypt --name=<<cname>> - ./<<cname>>.cred
EOF"""
mission(13, 'systemd-mountとsystemd-umountとsystemd-ask-passwordとsystemd-creds',
        '一時的な外部ディスクのマウントと、データベースパスワードの受け渡しをsystemdの機能で行います。systemd-mount/systemd-umountは一時的なmount/automountユニットを作ってデバイスやパスを扱い、systemd-ask-passwordは端末やプラグイン経由で秘密を問い合わせ、systemd-credsはTPMやホスト鍵で秘密を暗号化して認証情報として管理します。',
        ['4つのコマンド行をcmds.txtへ'], s13, c13, SOL13,
        ["printf 'mount /dev/sdb1 /mnt\\numount /mnt\\n' > cmds.txt",
         "cat > cmds.txt <<'EOF'\nsystemd-mount /dev/disk/by-label/<<label>> <<mnt>>\nsystemd-umount <<mnt>>\nsystemd-ask-password\nsystemd-creds encrypt - out.cred\nEOF"],
        'systemd-mountはmount(8)の代わりに一時ユニットを作り、--type/--optionsで指定できます。systemd-umountは同様にアンマウントします。systemd-ask-passwordは --timeout で待ち時間を、--echo=no で入力を隠します。systemd-creds encrypt は --name で認証情報の名前を固定し、ユニットのLoadCredentialEncrypted=で読み込めます。標準入力は - で指定します。',
        '最後の引数が「デバイス マウント先」の順です。', '4行をheredocで1コマンド1行にします。')


# ---------------------------------------------------------------- 14 machine-id
def s14(ctx):
    clones = [rnd('vm') for _ in range(3)]
    mid = secrets.token_hex(16)
    ctx.data.update(clones=clones, mid=mid)
    ctx.write('golden/etc/machine-id', mid + '\n')
    for c in clones:
        ctx.write(f'clones/{c}/etc/machine-id', mid + '\n')
    ctx.write('requirements.txt', f'ゴールデンイメージ golden から複製した3台（clones/*）が同じ machine-id（{mid}）を持ち、DHCPやジャーナルで衝突する。(1) golden/etc/machine-id は空にする（初回起動時に再生成させる標準手順）。(2) 各clonesのetc/machine-idに、systemd-id128 new 相当の新しい32桁小文字16進を各々異なる値で書く。(3) 各クローンで var/lib/dbus/machine-id を /etc/machine-id へのシンボリックリンクにする。(4) cmd.txt に各クローン分の systemd-machine-id-setup --root ./clones/名前 を書く。\n')


def c14(ctx):
    import os
    d = ctx.data
    ctx.require(ctx.need_file('golden/etc/machine-id').strip() == '', 'golden/etc/machine-id は空にします。')
    ids = []
    for c in d['clones']:
        v = ctx.need_file(f'clones/{c}/etc/machine-id').strip()
        ctx.require(re.fullmatch(r'[0-9a-f]{32}', v) and v != d['mid'], f'{c} のmachine-idは新しい32桁小文字16進です。')
        ids.append(v)
        l = ctx.p(f'clones/{c}/var/lib/dbus/machine-id')
        ctx.require(os.path.islink(l) and os.readlink(l) == '/etc/machine-id', f'{c} の var/lib/dbus/machine-id を /etc/machine-id へのリンクにします。')
    ctx.require(len(set(ids)) == 3, 'machine-idは各台で異なる値にします。')
    cl = cmdlines(ctx, 'cmd.txt')
    got = sorted(optv(t, '--root') for t in cl if t[0] == 'systemd-machine-id-setup')
    ctx.require(got == sorted(f'./clones/{c}' for c in d['clones']), '各クローンに systemd-machine-id-setup --root ./clones/名前 を書きます。')


SOL14 = """: > golden/etc/machine-id
for c in clones/*; do
  python3 -c 'import uuid; print(uuid.uuid4().hex)' > $c/etc/machine-id
  mkdir -p $c/var/lib/dbus
  ln -sfn /etc/machine-id $c/var/lib/dbus/machine-id
  echo "systemd-machine-id-setup --root ./$c" >> cmd.txt
done"""
mission(14, 'machine-idを複製イメージごとに一意にする（systemd-machine-id-setup・systemd-id128）',
        '仮想マシンを同じイメージから複製したため、全台が同じ/etc/machine-idを持ちます。machine-idは128ビットの一意なホスト識別子で、journalのディレクトリやDHCPクライアントIDに使われます。systemd-id128 newで新しい値を作り、systemd-machine-id-setupで正しく初期化します。',
        ['goldenは空にする', '各クローンに一意なIDとdbusリンク', 'setupコマンドをcmd.txtへ'], s14, c14, SOL14,
        ["for c in clones/*; do cp golden/etc/machine-id $c/etc/machine-id; done",
         "for c in clones/*; do python3 -c 'import uuid; print(uuid.uuid4().hex)' > $c/etc/machine-id; done"],
        'machine-idは改行付き32桁の小文字16進です。golden側は空にしておくと初回起動でsystemd-machine-id-setupが生成し、transientとして扱われます。/var/lib/dbus/machine-id は /etc/machine-id へのシンボリックリンクにして値のずれを防ぎます。systemd-id128 new はUUID相当の値を、systemd-machine-id-setup --root は指定ルート下のIDを初期化します。',
        '値の重複と形式（32桁小文字16進）を確認します。', 'ループでpython3のuuidを呼び、ln -sfnでリンクします。')


# ---------------------------------------------------------------- 15 busctl networkctl varlinkctl kernel-install
def s15(ctx):
    ifs = ['lo', 'ens3', rnd('eth'), rnd('wlan')]
    ops = ['carrier', 'routable', 'no-carrier', 'routable']
    st = ['unmanaged', 'configured', 'failed', 'configured']
    ctx.data.update(ifs=ifs, failed=ifs[2], nocar=[ifs[2]], ver='6.' + str(secrets.randbelow(20)) + '.' + str(secrets.randbelow(9)) + '-generic')
    put(ctx, 'networkctl.txt', 'IDX LINK  TYPE     OPERATIONAL SETUP\n' + ''.join(f'{i + 1:3d} {a:<6} ether    {b:<11} {c}\n' for i, (a, b, c) in enumerate(zip(ifs, ops, st))))
    ctx.write('requirements.txt', f'(1) networkctl.txt（networkctl listの記録）から、SETUPが failed のインタフェースと、OPERATIONAL が no-carrier のインタフェース一覧を net.json に {{"failed":名前,"no_carrier":[名前]}} で保存。(2) cmds.txt に4行: そのfailedの詳細を見る networkctl status 名前、システムバスから org.freedesktop.hostname1 の Hostname プロパティを取る busctl get-property（--system、パス /org/freedesktop/hostname1、インタフェース org.freedesktop.hostname1）、Varlinkで io.systemd.Hostname.Describe を {{}} 引数で呼ぶ varlinkctl call（ソケット /run/systemd/io.systemd.Hostname）、新カーネル {ctx.data["ver"]} のブートエントリを追加する kernel-install add {ctx.data["ver"]} /boot/vmlinuz-{ctx.data["ver"]}。実行はしません。\n')


def c15(ctx):
    need_ro(ctx)
    d = ctx.data
    r = rj(ctx, 'net.json')
    ctx.require(r.get('failed') == d['failed'] and r.get('no_carrier') == d['nocar'], 'net.jsonの値が違います。')
    cl = cmdlines(ctx, 'cmds.txt')
    n = tool(ctx, cl, 'networkctl')
    ctx.require(n[1:] == ['status', d['failed']], 'networkctl status 名前 です。')
    b = tool(ctx, cl, 'busctl')
    ctx.require(b[-5:] == ['get-property', 'org.freedesktop.hostname1', '/org/freedesktop/hostname1', 'org.freedesktop.hostname1', 'Hostname'] and '--system' in b, '--system とプロパティ名 Hostname を含めます。')
    v = tool(ctx, cl, 'varlinkctl')
    ctx.require(v[1:4] == ['call', '/run/systemd/io.systemd.Hostname', 'io.systemd.Hostname.Describe'] and v[-1] == '{}', 'varlinkctl call ソケット メソッド {} の形です。')
    k = tool(ctx, cl, 'kernel-install')
    ctx.require(k[1:] == ['add', d['ver'], f'/boot/vmlinuz-{d["ver"]}'], 'kernel-install add バージョン イメージ です。')


SOL15 = """python3 - <<'PY'
import json
rows = [l.split() for l in open('networkctl.txt').read().splitlines()[1:]]
json.dump({'failed': [r[1] for r in rows if r[-1] == 'failed'][0], 'no_carrier': [r[1] for r in rows if r[3] == 'no-carrier']}, open('net.json', 'w'))
PY
cat > cmds.txt <<'EOF'
networkctl status <<failed>>
busctl --system get-property org.freedesktop.hostname1 /org/freedesktop/hostname1 org.freedesktop.hostname1 Hostname
varlinkctl call /run/systemd/io.systemd.Hostname io.systemd.Hostname.Describe {}
kernel-install add <<ver>> /boot/vmlinuz-<<ver>>
EOF"""
mission(15, 'networkctl・busctl・varlinkctl・kernel-installで状態確認とカーネル追加',
        '障害対応でネットワーク、D-Bus、Varlink、カーネルエントリを順に扱います。networkctlはsystemd-networkdの管理状態、busctlはD-Busの検査と呼出し、varlinkctlはVarlink IPCの呼出し、kernel-installは新カーネルをブートローダへ登録する入口です。',
        ['net.jsonへ診断を保存', '4コマンドをcmds.txtへ'], s15, c15, SOL15,
        ["echo '{}' > net.json\necho 'ip link' > cmds.txt",
         "echo '{\"failed\":\"lo\",\"no_carrier\":[\"lo\"]}' > net.json\nprintf 'networkctl status lo\\n' > cmds.txt"],
        'networkctl listのSETUPがfailedはsystemd-networkdの設定適用に失敗、OPERATIONALがno-carrierはリンクが上がっていません。busctlは --system/--user でバスを選び、get-propertyでプロパティを取得、varlinkctl callでVarlinkメソッドを呼び、kernel-install add は /usr/lib/kernel/install.d のフックでinitramfsとブートエントリを作ります。',
        '列の位置を決めて、failedとno-carrierを抽出します。', 'pythonまたはawkで列を判定し、コマンドはheredocで。')


# ---------------------------------------------------------------- 16 kmod depmod insmod rmmod modinfo modprobe.d
def s16(ctx):
    mods = [rnd('m') for _ in range(5)]
    A, B, C, D, E = mods
    ctx.data.update(mods=mods, param='queues', val=str(2 ** (1 + secrets.randbelow(4))), bl=rnd('badmod'))
    P = lambda m: f'kernel/drivers/{m}.ko'
    deps = {A: [B, C], B: [C, D], C: [], D: [], E: []}
    put(ctx, 'modules.dep', ''.join(f'{P(m)}:' + ''.join(' ' + P(x) for x in v) + '\n' for m, v in deps.items()))
    put(ctx, 'modinfo.out', f'filename:       /lib/modules/6.1/{P(A)}\nlicense:        GPL\ndescription:    test driver\ndepends:        {B},{C}\nparm:           debug:Enable debug (bool)\nparm:           queues:Number of queues (int)\n')
    ctx.data['deps'] = deps
    ctx.data.update(m0=A, m1=B, m2=C)
    ctx.write('requirements.txt', f'modules.depはdepmodが作る依存表で、modinfo.outは {A}.ko のmodinfoの記録。rootで依存解決をしないinsmodを使うため、(1) load.sh に {A} を読み込むinsmod行（依存を先に、重複なし、パスは modules.dep の相対パス）。(2) unload.sh に取り外すrmmod行（{A} が使う側なので先、依存は後。モジュール名で書く）。(3) kmod系のmodprobe用設定 modprobe.d/local.conf に、modinfo.outにあるパラメータ queues={ctx.data["val"]} の options 行と、{ctx.data["bl"]} をblacklistする行。\n')


def c16(ctx):
    need_ro(ctx)
    d = ctx.data
    deps = d['deps']
    A = d['mods'][0]
    mod = lambda path: path.split('/')[-1][:-3]
    ld = [tk(ctx, l) for l in lines(ctx, 'load.sh') if l.strip() and not l.startswith('#')]
    ctx.require(all(t[0] == 'insmod' and len(t) == 2 for t in ld), 'load.shはinsmod パス の行だけにします。')
    order = [mod(t[1]) for t in ld]
    need = set()

    def walk(m):
        need.add(m)
        for x in deps[m]:
            walk(x)
    walk(A)
    ctx.require(sorted(order) == sorted(need), '必要なモジュールを重複なしで全て読み込みます。')
    for i, m in enumerate(order):
        ctx.require(all(x in order[:i] for x in deps[m]), f'{m} の依存を先に読み込みます。')
    ctx.require(all(t[1] == f'kernel/drivers/{mod(t[1])}.ko' for t in ld), 'パスは modules.dep の相対パスです。')
    ul = [tk(ctx, l) for l in lines(ctx, 'unload.sh') if l.strip() and not l.startswith('#')]
    ctx.require(all(t[0] == 'rmmod' and len(t) == 2 for t in ul), 'unload.shはrmmod 名前 の行だけにします。')
    uo = [t[1] for t in ul]
    ctx.require(sorted(uo) == sorted(need), '取り外すモジュールは読み込んだ全てです。')
    for i, m in enumerate(uo):
        ctx.require(all(x in uo[i + 1:] for x in deps[m]), f'{m} を使う側が先、依存は後で外します。')
    ls = [l.split() for l in lines(ctx, 'modprobe.d/local.conf') if l.strip() and not l.startswith('#')]
    ctx.require(['options', A, f'{d["param"]}={d["val"]}'] in ls, f'options {A} queues={d["val"]} の行を書きます。')
    ctx.require(['blacklist', d['bl']] in ls, f'blacklist {d["bl"]} の行を書きます。')


SOL16 = """python3 - <<'PY'
import os
deps = {}
for l in open('modules.dep'):
    k, v = l.rstrip().split(':'); deps[k] = v.split()
name = lambda p: os.path.basename(p)[:-3]
target = [k for k in deps if name(k) == '<<A>>'][0]
order = []
def walk(p):
    for x in deps[p]: walk(x)
    if p not in order: order.append(p)
walk(target)
open('load.sh', 'w').write(''.join('insmod ' + p + '\\n' for p in order))
open('unload.sh', 'w').write(''.join('rmmod ' + name(p) + '\\n' for p in reversed(order)))
PY
mkdir -p modprobe.d
printf 'options <<A>> queues=<<val>>\\nblacklist <<bl>>\\n' > modprobe.d/local.conf"""
mission(16, 'kmodの依存解決をinsmod・rmmod・depmod・modinfoと modprobe.d で再現する',
        'kmodパッケージの道具（modprobe/depmod/insmod/rmmod/modinfo）の違いを手で再現します。depmodがmodules.depを作り、modinfoがパラメータ・依存を教え、modprobeは依存を解決しますがinsmodは1つのファイルをそのまま読むだけです。読み込み順と取り外し順を自分で決めます。',
        ['load.shを依存順に', 'unload.shを逆順に', 'modprobe.dの設定'], s16, c16, SOL16.replace('<<A>>', '<<m0>>'),
        ["python3 -c \"print(end=''.join('insmod kernel/drivers/%s.ko\\n' % m for m in '<<m0>> <<m1>> <<m2>>'.split()))\" > load.sh\ncp load.sh unload.sh",
         "mkdir -p modprobe.d\nprintf 'options <<m0>> debug=1\\nblacklist <<bl>>\\n' > modprobe.d/local.conf"],
        'modprobeはmodules.dep（depmodが生成、-aで全部、-bでルート指定）を読んで依存を自動解決します。insmodは依存を解決せず、依存モジュールを先に自分で読み込む必要があります。rmmodは使用中のモジュールを外せないため、使う側から外します。modinfoは depends / parm / license を表示します。/etc/modprobe.d/*.conf では options でパラメータを、blacklist で自動ロードを抑止します。',
        'modules.depの右辺が依存で、再帰的にたどります。', '再帰（深さ優先）で依存を先に出力し、unloadはその逆順です。')


# ---------------------------------------------------------------- 17 agetty getty ctrlaltdel inittab
def s17(ctx):
    baud = secrets.choice(['9600', '19200', '57600', '115200'])
    ctx.data['baud'] = baud
    ctx.write('inittab', 'id:3:initdefault:\nsi::sysinit:/etc/init.d/rcS\n1:2345:respawn:/sbin/getty 38400 tty1\n2:2345:respawn:/sbin/getty 38400 tty2\n'
              'ca::ctrlaltdel:/sbin/shutdown -t1 -a -r now\n')
    ctx.write('requirements.txt', f'古いSysV initのinittabを直す。(1) tty1の行を agetty に替え、画面を消さない --noclear と tty1 と速度 {baud} と端末 linux を指定（行のid・ランレベル・respawnは維持）。(2) tty2の行はgettyのまま残す。(3) 物理コンソールのCtrl-Alt-Delで再起動してしまうので、ctrlaltdel行のアクションを /bin/echo "ctrl-alt-del disabled" に変える（shutdownを呼ばない）。(4) シリアル用に S0:2345:respawn: の行を足し、agetty -L ttyS0 {baud} vt100。(5) systemd側の同等設定 cmds.txt に、systemctl mask ctrl-alt-del.target と systemctl enable serial-getty@ttyS0.service の2行。\n')


def c17(ctx):
    d = ctx.data
    ls = lines(ctx, 'inittab')
    by = {}
    for l in ls:
        if l.strip() and not l.startswith('#'):
            f = l.split(':', 3)
            by[f[0]] = f
    ctx.require(by.get('id') and by['id'][1] == '3' and by.get('si'), 'initdefaultなど他の行は残します。')
    t1 = by.get('1')
    ctx.require(t1 and t1[1] == '2345' and t1[2] == 'respawn', 'tty1の行のid・ランレベル・respawnは維持します。')
    a = tk(ctx, t1[3])
    ctx.require(a[0].endswith('agetty') and '--noclear' in a and a[-3:] == ['tty1', d['baud'], 'linux'], '/sbin/agetty --noclear tty1 速度 linux の形にします。')
    ctx.require(by.get('2') and by['2'][3] == '/sbin/getty 38400 tty2', 'tty2はgettyのままにします。')
    ca = [f for f in by.values() if f[2] == 'ctrlaltdel']
    ctx.require(len(ca) == 1 and 'shutdown' not in ca[0][3] and 'reboot' not in ca[0][3] and 'echo' in ca[0][3], 'ctrlaltdelのアクションを echo に変えます。')
    s0 = by.get('S0')
    ctx.require(s0 and s0[1] == '2345' and s0[2] == 'respawn', 'S0の行を足します。')
    b = tk(ctx, s0[3])
    ctx.require(b[0].endswith('agetty') and '-L' in b and b[-3:] == ['ttyS0', d['baud'], 'vt100'], 'agetty -L ttyS0 速度 vt100 の形にします。')
    cl = cmdlines(ctx, 'cmds.txt')
    ctx.require(['systemctl', 'mask', 'ctrl-alt-del.target'] in cl and ['systemctl', 'enable', 'serial-getty@ttyS0.service'] in cl, 'systemd側の2コマンドを書きます。')


SOL17 = """sed -i 's#^1:2345:respawn:.*#1:2345:respawn:/sbin/agetty --noclear tty1 <<baud>> linux#; s#^ca::ctrlaltdel:.*#ca::ctrlaltdel:/bin/echo "ctrl-alt-del disabled"#' inittab
echo 'S0:2345:respawn:/sbin/agetty -L ttyS0 <<baud>> vt100' >> inittab
printf 'systemctl mask ctrl-alt-del.target\\nsystemctl enable serial-getty@ttyS0.service\\n' > cmds.txt"""
mission(17, 'inittab・agetty・getty・ctrlaltdelをSysVとsystemdで対応づける',
        'ログインプロンプトを出すgettyと、Ctrl-Alt-Delの扱いを整えます。/etc/inittabはSysV initの設定で、agettyは高機能なgettyです。systemdではgetty@tty1.serviceやserial-getty@.serviceとctrl-alt-del.targetが対応します。',
        ['inittabの編集', 'systemd側の対応コマンドをcmds.txtへ'], s17, c17, SOL17,
        ["sed -i 's#getty 38400 tty1#agetty tty1#' inittab\necho 'systemctl disable getty@tty1' > cmds.txt",
         "sed -i 's#^ca::ctrlaltdel:.*#ca::ctrlaltdel:/sbin/shutdown -h now#' inittab"],
        'inittabは id:ランレベル:アクション:プロセス の4項目です。respawnは終了すると再起動する意味で、ctrlaltdelはCtrl-Alt-Del時に実行されます。agettyは --noclear、-L（ローカル接続）などで調整し、ttyに続けて速度と端末種別を渡します。systemdではctrl-alt-del.targetをmaskすると再起動を防げます。',
        '行の先頭4項目は : で区切ります。', 'sedで行を置換し、足す行はechoで。')


# ---------------------------------------------------------------- 18 nsswitch services protocols login.defs shells limits.conf
def s18(ctx):
    maxd = secrets.choice(['60', '90', '120'])
    svc = rnd('svc')
    port = str(40000 + secrets.randbelow(9000))
    proto = secrets.choice([('ospf', '89'), ('gre', '47'), ('esp', '50'), ('sctp', '132')])
    nofile = secrets.choice(['16384', '65536'])
    sh = secrets.choice(['/usr/bin/fish', '/usr/bin/zsh'])
    ctx.data.update(proto0=proto[0], maxd=maxd, svc=svc, port=port, proto=proto, nofile=nofile, sh=sh)
    ctx.mkdir('etc')
    ctx.write('etc/nsswitch.conf', 'passwd:         files systemd\ngroup:          files systemd\nhosts:          files mdns4_minimal [NOTFOUND=return] dns\nnetworks:       files\n')
    put(ctx, 'etc/protocols', 'ip\t0\tIP\nicmp\t1\tICMP\ntcp\t6\tTCP\nudp\t17\tUDP\ngre\t47\tGRE\nesp\t50\tIPSEC-ESP\nospf\t89\tOSPFIGP\nsctp\t132\tSCTP\n')
    ctx.write('etc/services', 'ssh\t\t22/tcp\nhttp\t\t80/tcp\nhttps\t\t443/tcp\n')
    ctx.write('etc/login.defs', '# login.defs\nPASS_MAX_DAYS\t99999\nPASS_MIN_DAYS\t0\nPASS_WARN_AGE\t7\nUMASK\t\t022\nENCRYPT_METHOD\tMD5\n')
    ctx.write('etc/shells', '# /etc/shells\n/bin/sh\n/bin/bash\n/opt/legacy/bin/oldsh\n')
    ctx.write('etc/security/limits.conf', '# limits.conf\n*\tsoft\tcore\t0\n', )
    ctx.write('requirements.txt', f'etc/ 以下の設定を整える。(1) nsswitch.conf の hosts を「files dns」の順だけにする（mdns無し）。(2) services に自作サービス {svc} を {port}/tcp で追記。(3) protocols（読み取り専用）から {proto[0]} のプロトコル番号を proto.txt に数字だけで。(4) login.defs を PASS_MAX_DAYS {maxd}、PASS_MIN_DAYS 1、PASS_WARN_AGE 14、UMASK 027、ENCRYPT_METHOD SHA512 に。(5) shells から /opt/legacy/bin/oldsh を除き {sh} を追加。(6) security/limits.conf に @dev soft nofile {nofile} と @dev hard nofile {nofile}、* hard core 0 を追記（既存の soft core 0 は残す）。\n')


def kv(ctx, name):
    d = {}
    for l in lines(ctx, name):
        if l.strip() and not l.strip().startswith('#'):
            f = l.split()
            d[f[0]] = f[1:]
    return d


def c18(ctx):
    need_ro(ctx)
    d = ctx.data
    ns = {l.split(':')[0]: l.split(':', 1)[1].split() for l in lines(ctx, 'etc/nsswitch.conf') if ':' in l}
    ctx.require(ns.get('hosts') == ['files', 'dns'] and ns.get('passwd') == ['files', 'systemd'], 'hosts は files dns のみにし、他の行は残します。')
    sv = [l.split() for l in lines(ctx, 'etc/services') if l.strip()]
    ctx.require([x for x in sv if x[0] == d['svc']] == [[d['svc'], d['port'] + '/tcp']] and len(sv) == 4, 'servicesに1行だけ追記します（既存は維持）。')
    ctx.require(ctx.need_file('proto.txt').strip() == d['proto'][1], 'proto.txt にプロトコル番号だけを書きます。')
    ld = kv(ctx, 'etc/login.defs')
    for k, v in (('PASS_MAX_DAYS', d['maxd']), ('PASS_MIN_DAYS', '1'), ('PASS_WARN_AGE', '14'), ('UMASK', '027'), ('ENCRYPT_METHOD', 'SHA512')):
        ctx.require(ld.get(k) == [v], f'login.defs の {k} は {v} にします。')
    sh = [l.strip() for l in lines(ctx, 'etc/shells') if l.strip() and not l.startswith('#')]
    ctx.require(sh == ['/bin/sh', '/bin/bash', d['sh']], 'shellsを旧シェル削除・新シェル追加の形にします。')
    lim = [l.split() for l in lines(ctx, 'etc/security/limits.conf') if l.strip() and not l.startswith('#')]
    for row in (['*', 'soft', 'core', '0'], ['*', 'hard', 'core', '0'], ['@dev', 'soft', 'nofile', d['nofile']], ['@dev', 'hard', 'nofile', d['nofile']]):
        ctx.require(row in lim, 'limits.conf に ' + ' '.join(row) + ' が必要です。')
    ctx.require(len(lim) == 4, 'limits.conf の行が余分です。')


SOL18 = """sed -i 's#^hosts:.*#hosts:          files dns#' etc/nsswitch.conf
printf '<<svc>>\\t\\t<<port>>/tcp\\n' >> etc/services
awk '$1=="<<proto0>>" {print $2}' etc/protocols > proto.txt
sed -i 's/^PASS_MAX_DAYS.*/PASS_MAX_DAYS\\t<<maxd>>/; s/^PASS_MIN_DAYS.*/PASS_MIN_DAYS\\t1/; s/^PASS_WARN_AGE.*/PASS_WARN_AGE\\t14/; s/^UMASK.*/UMASK\\t\\t027/; s/^ENCRYPT_METHOD.*/ENCRYPT_METHOD\\tSHA512/' etc/login.defs
sed -i '\\#/opt/legacy/bin/oldsh#d' etc/shells
echo '<<sh>>' >> etc/shells
printf '@dev soft nofile <<nofile>>\\n@dev hard nofile <<nofile>>\\n* hard core 0\\n' >> etc/security/limits.conf"""
mission(18, 'nsswitch.conf・services・protocols・login.defs・shells・limits.confを整える',
        '新サーバーの基本設定を点検します。nsswitch.confは名前解決の参照順、servicesとprotocolsはポート名・プロトコル番号の対応表、login.defsはパスワード期限やumask、shellsは有効なログインシェル、limits.confはPAMのリソース制限です。',
        ['6つの設定を指定どおりに編集する'], s18, c18, SOL18,
        ["sed -i 's#^hosts:.*#hosts: dns#' etc/nsswitch.conf\necho '<<svc>> <<port>>' >> etc/services",
         "echo 'PASS_MAX_DAYS <<maxd>>' >> etc/login.defs\nawk '$1==\"ospf\" {print $2}' etc/protocols > proto.txt\necho '<<sh>>' >> etc/shells"],
        'nsswitch.confのhosts行は「files dns」でhostsファイル→DNSの順に問い合わせます。services/protocolsは getservbyname 等が参照します。login.defsは項目名と値を空白で区切り、UMASKは8進、ENCRYPT_METHODはハッシュ方式です。chshは/etc/shellsに載るシェルだけを許可し、limits.confは「ドメイン 種別 項目 値」で、@はグループ、*は全員です。同じ項目の重複行を作らず、sedで既存行を置換します。',
        '設定は「項目 値」の行単位で、既存行は置換します。', 'sedで置換、追記はprintfで、protocolsはawkで検索。')


# ---------------------------------------------------------------- 19 profile environment motd issue skel
def s19(ctx):
    app = rnd('app')
    nu = rnd('new')
    when = f'2026-{1 + secrets.randbelow(12):02d}-{1 + secrets.randbelow(28):02d}'
    ctx.data.update(app=app, nu=nu, when=when)
    ctx.mkdir('etc/profile.d')
    ctx.write('etc/profile', '# system-wide .profile\numask 000\nfor i in /etc/profile.d/*.sh; do [ -r "$i" ] && . "$i"; done\n')
    ctx.write('etc/environment', 'LANG=C\nexport EDITOR=nano\n')
    ctx.write('etc/motd', 'Welcome.\n')
    ctx.write('etc/issue', 'Debian GNU/Linux \\n \\l\n')
    ctx.write('etc/skel/.bashrc', '# ~/.bashrc\nexport HISTSIZE=1000\n')
    ctx.mkdir('home')
    ctx.write('requirements.txt', f'(1) etc/profile の umask 000 を 027 に。(2) etc/profile.d/{app}.sh を新規作成し、PATH に /opt/{app}/bin を足す export 行を1行（既存PATHを保持）。(3) etc/environment（PAMが読む。export不可、KEY=VALUEのみ）の不正な行を直し EDITOR=vim、LANG を ja_JP.UTF-8 に。(4) etc/motd に「Maintenance: {when}」を含む行を追記。(5) etc/issue を ログイン前の注意書き「Authorized use only」の後に \\n \\l の入った形にする（既存の \\n \\l は残す）。(6) etc/skel/.bashrc に alias ll=\'ls -la\' を追記してから、新ユーザー {nu} のホームを skel から home/{nu} に作成（useradd -m -k の動作を cp -a で再現、隠しファイル含む）。\n')


def c19(ctx):
    d = ctx.data
    ctx.require(any(l.strip() == 'umask 027' for l in lines(ctx, 'etc/profile')) and not any(l.strip() == 'umask 000' for l in lines(ctx, 'etc/profile')) and 'profile.d' in ctx.need_file('etc/profile'), 'etc/profileのumaskを027にし、profile.dの読み込みは残します。')
    pd = [l.strip() for l in lines(ctx, f'etc/profile.d/{d["app"]}.sh') if l.strip() and not l.startswith('#')]
    ctx.require(pd == [f'export PATH="$PATH:/opt/{d["app"]}/bin"'] or pd == [f'export PATH=$PATH:/opt/{d["app"]}/bin'], 'export PATH="$PATH:/opt/アプリ/bin" の1行にします。')
    env = [l for l in lines(ctx, 'etc/environment') if l.strip()]
    ctx.require(sorted(env) == ['EDITOR=vim', 'LANG=ja_JP.UTF-8'], 'etc/environmentは export 無しの KEY=VALUE のみ（EDITOR=vim、LANG=ja_JP.UTF-8）です。')
    ctx.require(any(f'Maintenance: {d["when"]}' in l for l in lines(ctx, 'etc/motd')) and 'Welcome.' in ctx.need_file('etc/motd'), 'motdに保守日を追記します（既存行は残す）。')
    iss = ctx.need_file('etc/issue')
    ctx.require('Authorized use only' in iss and '\\n' in iss and '\\l' in iss, 'issueに注意書きとエスケープ \\n \\l を含めます。')
    ctx.require("alias ll='ls -la'" in ctx.need_file('etc/skel/.bashrc') and 'HISTSIZE=1000' in ctx.need_file('etc/skel/.bashrc'), 'skelの.bashrcに既存を残してaliasを追記します。')
    hb = ctx.need_file(f'home/{d["nu"]}/.bashrc')
    ctx.require("alias ll='ls -la'" in hb, 'skelのaliasを追記した後でコピーします。')


SOL19 = """sed -i 's/^umask 000/umask 027/' etc/profile
echo 'export PATH="$PATH:/opt/<<app>>/bin"' > etc/profile.d/<<app>>.sh
printf 'EDITOR=vim\\nLANG=ja_JP.UTF-8\\n' > etc/environment
echo 'Maintenance: <<when>>' >> etc/motd
printf 'Authorized use only\\n' | cat - etc/issue > issue.tmp && mv issue.tmp etc/issue
echo "alias ll='ls -la'" >> etc/skel/.bashrc
mkdir -p home/<<nu>> && cp -a etc/skel/. home/<<nu>>/"""
mission(19, 'profile・environment・motd・issue・skelでログイン環境を整える',
        'ログインから新規ユーザー作成までの共通環境を整えます。/etc/profileと/etc/profile.d/*.shはログインシェルが読む共通初期化、/etc/environmentはPAMが読むKEY=VALUEだけの環境変数、motdはログイン後、issueはログイン前に出る文章、/etc/skelは新規ユーザーのホームに配られる雛形です。',
        ['profile・profile.d・environment', 'motd・issue', 'skelと新ユーザーのホーム'], s19, c19, SOL19,
        ["sed -i 's/^umask 000/umask 027/' etc/profile\necho 'export EDITOR=vim' >> etc/environment",
         "mkdir -p home/<<nu>>\ncp -a etc/skel/. home/<<nu>>/\necho \"alias ll='ls -la'\" >> etc/skel/.bashrc"],
        'profileはシェル構文なので export が使え、/etc/environmentはシェルを通さないので export や変数展開は使えません。issueは getty が \\n（ホスト名）や \\l（tty）を展開し、motdは固定文です。skelは useradd -m（-k で別の雛形）がコピーするので、更新後に作るユーザーへだけ反映され、既存ユーザーは変わりません。ドットファイルは cp -a と末尾 /. で含めます。',
        'シェル用とPAM用で書式が違います。', 'sedとprintfで編集し、cp -a skel/. で隠しファイルまでコピーします。')


# ---------------------------------------------------------------- 20 unit service/timer
def s20(ctx):
    app = rnd('backup')
    hh = f'{secrets.randbelow(5) + 1:02d}:{secrets.choice(["00", "15", "30", "45"])}'
    jit = secrets.choice([300, 600, 900])
    ctx.data.update(app=app, hh=hh, jit=jit)
    ctx.mkdir('units')
    ctx.write('requirements.txt', f'毎日 {hh} にバックアップを実行する。units/{app}.service と units/{app}.timer を作る。service: Type=oneshot、ExecStart=/usr/local/bin/{app}.sh、User=backup、Nice=10（[Install]は不要）。timer: OnCalendar=*-*-* {hh}:00、Persistent=true（停止中の取りこぼしを起動後に実行）、RandomizedDelaySec={jit}、[Install]で WantedBy=timers.target。\n')


def c20(ctx):
    d = ctx.data
    s = unit(ctx, f'units/{d["app"]}.service')
    ctx.require('Service' in s and 'Install' not in s, 'serviceには[Service]を書き、[Install]は不要です。')
    ctx.require(uv(s, 'Service', 'Type') == ['oneshot'] and uv(s, 'Service', 'ExecStart') == [f'/usr/local/bin/{d["app"]}.sh'], 'Type=oneshot と ExecStart を指定します。')
    ctx.require(uv(s, 'Service', 'User') == ['backup'] and uv(s, 'Service', 'Nice') == ['10'], 'User=backup と Nice=10 を指定します。')
    t = unit(ctx, f'units/{d["app"]}.timer')
    ctx.require(uv(t, 'Timer', 'OnCalendar') == [f'*-*-* {d["hh"]}:00'], 'OnCalendar を指定どおりにします。')
    ctx.require(uv(t, 'Timer', 'Persistent') == ['true'] and uv(t, 'Timer', 'RandomizedDelaySec') == [str(d['jit'])], 'Persistent=true と RandomizedDelaySec を指定します。')
    ctx.require(uv(t, 'Install', 'WantedBy') == ['timers.target'], '[Install] WantedBy=timers.target にします。')


SOL20 = """cat > units/<<app>>.service <<'EOF'
[Unit]
Description=Daily backup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/<<app>>.sh
User=backup
Nice=10
EOF
cat > units/<<app>>.timer <<'EOF'
[Unit]
Description=Run backup daily

[Timer]
OnCalendar=*-*-* <<hh>>:00
Persistent=true
RandomizedDelaySec=<<jit>>

[Install]
WantedBy=timers.target
EOF"""
mission(20, 'serviceユニットとtimerユニットを作る',
        'cronの代わりにsystemdのタイマーで定期実行を作ります。serviceは実際の仕事、timerはいつ起動するかを定義し、同じ名前で対になります。',
        ['serviceユニット', 'timerユニット'], s20, c20, SOL20,
        ["cat > units/<<app>>.service <<'EOF'\n[Service]\nExecStart=/usr/local/bin/<<app>>.sh\nEOF",
         "cat > units/<<app>>.timer <<'EOF'\n[Timer]\nOnCalendar=daily\n[Install]\nWantedBy=multi-user.target\nEOF"],
        'Type=oneshot は処理が終わると完了するジョブ向けです。timerはOnCalendarで日時を、Persistent=trueで停止中の取りこぼしの補完を、RandomizedDelaySecで複数台の同時実行を避けます。timerユニットは [Install] で timers.target に結び付け、systemctl enable --now 名前.timer で有効にします。確認は systemctl list-timers と systemd-analyze calendar です。',
        'serviceは動作、timerは時刻の定義です。', '2つのファイルをheredocで書きます。')


# ---------------------------------------------------------------- 21 unit socket/path
def s21(ctx):
    app = rnd('echo')
    port = 31000 + secrets.randbelow(1000)
    ctx.data.update(app=app, port=port, spool=f'/var/spool/{app}/in')
    ctx.mkdir('units')
    ctx.write('requirements.txt', f'(1) ポート {port} で待ち受けて初回接続時にサービスを起動する。units/{app}.socket: ListenStream={port}、Accept=no、[Install] WantedBy=sockets.target。units/{app}.service: ExecStart=/usr/local/bin/{app}d（[Install]なし。ソケットが起動する）。(2) ディレクトリ /var/spool/{app}/in にファイルが出現・更新されたらインポートを走らせる。units/{app}-watch.path: PathChanged=/var/spool/{app}/in、Unit={app}-import.service、[Install] WantedBy=multi-user.target。units/{app}-import.service: Type=oneshot、ExecStart=/usr/local/bin/{app}-import。\n')


def c21(ctx):
    d = ctx.data
    a = d['app']
    so = unit(ctx, f'units/{a}.socket')
    ctx.require(uv(so, 'Socket', 'ListenStream') == [str(d['port'])] and uv(so, 'Socket', 'Accept') == ['no'] and uv(so, 'Install', 'WantedBy') == ['sockets.target'], '.socket の設定が違います。')
    sv = unit(ctx, f'units/{a}.service')
    ctx.require(uv(sv, 'Service', 'ExecStart') == [f'/usr/local/bin/{a}d'] and 'Install' not in sv, '.service は ExecStart のみ（[Install]無し）です。')
    pa = unit(ctx, f'units/{a}-watch.path')
    ctx.require(uv(pa, 'Path', 'PathChanged') == [d['spool']] and uv(pa, 'Path', 'Unit') == [f'{a}-import.service'] and uv(pa, 'Install', 'WantedBy') == ['multi-user.target'], '.path の設定が違います。')
    im = unit(ctx, f'units/{a}-import.service')
    ctx.require(uv(im, 'Service', 'Type') == ['oneshot'] and uv(im, 'Service', 'ExecStart') == [f'/usr/local/bin/{a}-import'], 'import.service の設定が違います。')


SOL21 = """cat > units/<<app>>.socket <<'EOF'
[Socket]
ListenStream=<<port>>
Accept=no

[Install]
WantedBy=sockets.target
EOF
cat > units/<<app>>.service <<'EOF'
[Service]
ExecStart=/usr/local/bin/<<app>>d
EOF
cat > units/<<app>>-watch.path <<'EOF'
[Path]
PathChanged=<<spool>>
Unit=<<app>>-import.service

[Install]
WantedBy=multi-user.target
EOF
cat > units/<<app>>-import.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/<<app>>-import
EOF"""
mission(21, 'socketユニットとpathユニットでオンデマンド起動を作る',
        '待ち受けと監視をsystemdに任せ、必要になったときだけサービスを起動します。socketユニットは接続時、pathユニットはファイルやディレクトリの変化時に、対応するserviceユニットを起動します。',
        ['socketとserviceのペア', 'pathとoneshot serviceのペア'], s21, c21, SOL21,
        ["cat > units/<<app>>.socket <<'EOF'\n[Socket]\nListenStream=<<port>>\nEOF",
         "cat > units/<<app>>-watch.path <<'EOF'\n[Path]\nPathExists=<<spool>>\n[Install]\nWantedBy=multi-user.target\nEOF"],
        'socketユニットはListenStream（TCP/UNIX）、Accept=no は1つのサービスが全接続を処理します（yesなら接続ごとにインスタンス）。pathユニットはPathExists/PathChanged/PathModified/DirectoryNotEmptyで監視し、Unit=で起動先を指定します（省略時は同名のサービス）。起動される側のserviceには通常[Install]を書かず、有効化はsocket/path側にします。',
        '起動される側のserviceは[Install]不要です。', '4ファイルをheredocで。')


# ---------------------------------------------------------------- 22 drop-in
def s22(ctx):
    app = rnd('web')
    nf = secrets.choice([8192, 16384, 65536])
    key = rnd('K').upper()
    val = rnd('v')
    port = 8000 + secrets.randbelow(1000)
    ctx.data.update(app=app, nf=nf, key=key, val=val, port=port)
    put(ctx, f'units/{app}.service', f'[Unit]\nDescription={app}\n\n[Service]\nExecStart=/usr/bin/{app}d --port 80\nRestart=no\n\n[Install]\nWantedBy=multi-user.target\n')
    ctx.mkdir(f'units/{app}.service.d')
    ctx.write('requirements.txt', f'ベンダー提供の units/{app}.service は直接編集せず、systemctl edit {app}.service が作る drop-in（units/{app}.service.d/override.conf）で上書きする。[Service] に、ExecStart=（空で既存を打ち消す）→ ExecStart=/usr/bin/{app}d --port {port}、Restart=on-failure、LimitNOFILE={nf}、Environment={key}={val} を書く。確認用に cmds.txt に systemctl edit {app}.service と systemctl cat {app}.service を書く（--fullは使わない）。\n')


def c22(ctx):
    need_ro(ctx)
    d = ctx.data
    a = d['app']
    s = unit(ctx, f'units/{a}.service.d/override.conf')
    ex = uv(s, 'Service', 'ExecStart')
    ctx.require(ex == ['', f'/usr/bin/{a}d --port {d["port"]}'], 'ExecStart= を先に空行で打ち消してから新しい値を書きます。')
    ctx.require(uv(s, 'Service', 'Restart') == ['on-failure'] and uv(s, 'Service', 'LimitNOFILE') == [str(d['nf'])] and uv(s, 'Service', 'Environment') == [f'{d["key"]}={d["val"]}'], 'Restart、LimitNOFILE、Environmentを指定します。')
    ctx.require(set(s) == {'Service'}, 'override.confには[Service]だけを書きます。')
    cl = cmdlines(ctx, 'cmds.txt')
    ctx.require(['systemctl', 'edit', f'{a}.service'] in cl and ['systemctl', 'cat', f'{a}.service'] in cl, 'systemctl edit と systemctl cat を書きます。')


SOL22 = """cat > units/<<app>>.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/<<app>>d --port <<port>>
Restart=on-failure
LimitNOFILE=<<nf>>
Environment=<<key>>=<<val>>
EOF
printf 'systemctl edit <<app>>.service\\nsystemctl cat <<app>>.service\\n' > cmds.txt"""
mission(22, 'systemctl editとdrop-inでベンダー設定を安全に上書きする',
        'パッケージ提供のユニットを直接書き換えると、更新で消えたり競合したりします。drop-inは設定の差分だけを /etc/systemd/system/名前.service.d/*.conf に置き、systemctl editが自動で作ります。',
        ['override.confを作る', 'systemctl editとcatをcmds.txtへ'], s22, c22, SOL22,
        ["sed -i 's/--port 80/--port <<port>>/' units/<<app>>.service",
         "cat > units/<<app>>.service.d/override.conf <<'EOF'\n[Service]\nExecStart=/usr/bin/<<app>>d --port <<port>>\nRestart=on-failure\nEOF"],
        'ExecStart等の複数指定できる項目は、drop-inで足すだけだと「2つのExecStart」になってエラーになります。空の ExecStart= で既存の定義を打ち消してから書き直します。systemctl edit は drop-in の作成と daemon-reload を行い、--full は全体のコピーを編集、systemctl cat で最終的な結果（本体＋drop-in）を確認します。',
        'ExecStart= の空指定が必要です。', 'override.confに空のExecStart=を先に書きます。')


# ---------------------------------------------------------------- 23 dependency/order
def s23(ctx):
    ctx.mkdir('units')
    ctx.write('units/web.service', '[Unit]\nDescription=web\nAfter=db.service\n\n[Service]\nExecStart=/usr/bin/webd\n')
    ctx.write('units/db.service', '[Unit]\nDescription=db\nAfter=web.service\n\n[Service]\nExecStart=/usr/bin/dbd\n')
    ctx.write('units/cache.service', '[Unit]\nDescription=cache\n\n[Service]\nExecStart=/usr/bin/cached\n')
    ctx.write('units/log.service', '[Unit]\nDescription=log\n\n[Service]\nExecStart=/usr/bin/logd\n')
    ctx.write('boot.log', 'systemd[1]: Found ordering cycle on web.service/start\nsystemd[1]: Found dependency on db.service/start\nsystemd[1]: Found dependency on web.service/start\nsystemd[1]: Job web.service/start deleted to break ordering cycle\n')
    ctx.write('requirements.txt', 'boot.log に順序の循環が出ている。units/web.service は原本ではなく編集してよい（本体のRequires/Wants系は[Unit]に書く）。(1) dbはwebより先に起動する必要がある。web は db に必須の依存（Requires=db.service と After=db.service）。db 側から web への順序指定は削除。(2) cache は任意の依存で Wants=cache.service と After=cache.service。(3) log は web より前に起動（log.service に Before=web.service）。(4) cmds.txt に systemd-analyze verify units/web.service と systemctl list-dependencies web.service を書く。\n')


def uw(d, sec, key):
    return sum((v.split() for v in uv(d, sec, key)), [])


def c23(ctx):
    w = unit(ctx, 'units/web.service')
    ctx.require('db.service' in uw(w, 'Unit', 'Requires') and 'db.service' in uw(w, 'Unit', 'After'), 'webは Requires=db.service と After=db.service です。')
    ctx.require('cache.service' in uw(w, 'Unit', 'Wants') and 'cache.service' in uw(w, 'Unit', 'After') and 'cache.service' not in uw(w, 'Unit', 'Requires'), 'cacheは Wants と After（Requiresにはしない）です。')
    db = unit(ctx, 'units/db.service')
    ctx.require('web.service' not in uw(db, 'Unit', 'After') + uw(db, 'Unit', 'Before') + uw(db, 'Unit', 'Requires') + uw(db, 'Unit', 'Wants'), 'dbからwebへの指定は消して循環を解消します。')
    lg = unit(ctx, 'units/log.service')
    ctx.require('web.service' in uw(lg, 'Unit', 'Before'), 'log.service に Before=web.service を書きます。')
    cl = cmdlines(ctx, 'cmds.txt')
    ctx.require(['systemd-analyze', 'verify', 'units/web.service'] in cl and ['systemctl', 'list-dependencies', 'web.service'] in cl, '検証用の2コマンドを書きます。')
    ctx.require(ctx.need_file('units/cache.service') and ctx.need_file('units/log.service'), 'ユニットファイルを消さないでください。')


SOL23 = """cat > units/web.service <<'EOF'
[Unit]
Description=web
Requires=db.service
After=db.service cache.service
Wants=cache.service

[Service]
ExecStart=/usr/bin/webd
EOF
sed -i '/^After=web.service/d' units/db.service
sed -i 's/^Description=log/Description=log\\nBefore=web.service/' units/log.service
printf 'systemd-analyze verify units/web.service\\nsystemctl list-dependencies web.service\\n' > cmds.txt"""
mission(23, 'systemdの依存（Requires・Wants）と順序（After・Before）を直す',
        '起動時に順序の循環が検出されました。systemdでは「何を必要とするか（依存）」と「どの順に起動するか（順序）」は別の指定です。Requires/Wantsは依存、After/Beforeは順序を定義します。',
        ['webの依存と順序', 'dbの循環解消', 'logの順序', '検証コマンド'], s23, c23, SOL23,
        ["sed -i '/^After=db.service/d' units/web.service",
         "sed -i 's/^After=web.service/After=cache.service/' units/db.service\nprintf 'systemctl status web\\n' > cmds.txt"],
        'Requires=は必須（失敗すれば自分も失敗）、Wants=は弱い依存、Requisite/BindsTo/PartOf/Conflictsもあります。依存だけでは起動順は決まらないため、After=/Before=で順序を足します。AがBにAfter、BがAにAfterだと循環し、片方のジョブが破棄されます。systemd-analyze verify で検査し、systemctl list-dependencies で依存木を確認します。',
        '順序の矢印が一方向であることを確認します。', 'web側を書き直し、dbのAfter=webを削除します。')


# ---------------------------------------------------------------- 24 target/runlevel
def s24(ctx):
    n = secrets.choice(['3', '5'])
    ctx.data['n'] = n
    put(ctx, 'inittab.old', f'id:{n}:initdefault:\n')
    put(ctx, 'ls-l.txt', 'lrwxrwxrwx 1 root root 15 runlevel0.target -> poweroff.target\nlrwxrwxrwx 1 root root 13 runlevel1.target -> rescue.target\n'
        'lrwxrwxrwx 1 root root 17 runlevel2.target -> multi-user.target\nlrwxrwxrwx 1 root root 17 runlevel3.target -> multi-user.target\n'
        'lrwxrwxrwx 1 root root 17 runlevel4.target -> multi-user.target\nlrwxrwxrwx 1 root root 16 runlevel5.target -> graphical.target\n'
        'lrwxrwxrwx 1 root root 13 runlevel6.target -> reboot.target\n')
    ctx.mkdir('etc/systemd/system')
    ctx.write('requirements.txt', 'ls-l.txt はランレベル互換ターゲットの一覧（ls -l の記録）。(1) runlevels.json に {"0":ターゲット,...,"6":ターゲット} の対応表。(2) 旧設定 inittab.old の initdefault と同じ既定ターゲットになるよう etc/systemd/system/default.target を /usr/lib/systemd/system/ターゲット へのシンボリックリンクにする（systemctl set-default 相当）。(3) cmds.txt に systemctl set-default 同ターゲット、systemctl get-default、実行中のサーバーを今すぐ rescue.target に切り替える systemctl isolate rescue.target を書く。\n')


def c24(ctx):
    import os
    need_ro(ctx)
    n = ctx.data['n']
    exp = {'0': 'poweroff.target', '1': 'rescue.target', '2': 'multi-user.target', '3': 'multi-user.target', '4': 'multi-user.target', '5': 'graphical.target', '6': 'reboot.target'}
    ctx.require(rj(ctx, 'runlevels.json') == exp, 'runlevels.jsonの対応表が違います。')
    t = exp[n]
    l = ctx.p('etc/systemd/system/default.target')
    ctx.require(os.path.islink(l) and os.readlink(l) == '/usr/lib/systemd/system/' + t, f'default.target を {t} へのリンクにします。')
    cl = cmdlines(ctx, 'cmds.txt')
    ctx.require(['systemctl', 'set-default', t] in cl and ['systemctl', 'get-default'] in cl and ['systemctl', 'isolate', 'rescue.target'] in cl, 'cmds.txtに3コマンドを書きます。')


SOL24 = """awk '{split($6,a,"runlevel"); gsub(/\\.target/,"",a[2]); printf "%s\\"%s\\":\\"%s\\"", (NR>1?",":"{"), a[2], $8} END {print "}"}' ls-l.txt > runlevels.json
n=$(sed 's/^id:\\([0-9]\\):.*/\\1/' inittab.old)
t=$(awk -v n="$n" '$6=="runlevel" n ".target" {print $8}' ls-l.txt)
ln -sfn /usr/lib/systemd/system/$t etc/systemd/system/default.target
printf 'systemctl set-default %s\\nsystemctl get-default\\nsystemctl isolate rescue.target\\n' "$t" > cmds.txt"""
mission(24, 'ターゲットとランレベルの対応を整理し既定ターゲットを決める',
        'SysV initのランレベルとsystemdのターゲットを対応づけます。runlevelN.targetは互換用のシンボリックリンクで、既定のターゲットは default.target のリンク先で決まります。',
        ['runlevels.jsonの対応表', 'default.targetのリンク', 'cmds.txtの3コマンド'], s24, c24, SOL24,
        ["echo '{}' > runlevels.json\nln -sfn /usr/lib/systemd/system/graphical.target etc/systemd/system/default.target",
         "ln -sfn /usr/lib/systemd/system/multi-user.target etc/systemd/system/default.target\nprintf 'systemctl set-default multi-user.target\\n' > cmds.txt"],
        'ランレベル0=poweroff、1=rescue、2〜4=multi-user、5=graphical、6=reboot です。default.targetのリンク先が既定ターゲットで、systemctl set-default が作成し、get-default が確認します。systemctl isolate は指定ターゲットに今すぐ切り替え、その依存に含まれないユニットを停止するため、リモートでは注意が必要です。',
        'ls -l の矢印の右側がターゲット名です。', 'awkで$9と$11を使い、ランレベルを抽出します。')
