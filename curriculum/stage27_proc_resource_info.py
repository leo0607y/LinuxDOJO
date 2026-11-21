"""Stage 27: プロセス・資源・システム情報の総ざらい。サンドボックス内の偽データと採取済み出力だけを使う。"""
import hashlib
import json
import math
import os
import secrets
import shlex
import subprocess
import time

from engine.runner import register

S = 27
NOTE = ("作業対象はこの課題のフォルダだけです。実OSのプロセス・IPC・ロック・ログ・電源・端末は操作せず、rootも使いません。"
        "データは訓練用の偽物で、環境にないツールは採取済みの出力と設定例から診断します。")
TIP = '実機では必ず対象を確認(読み取り系コマンド)してから変更し、結果をもう一度観測して確かめましょう。'


def rp(lo, hi):
    return lo + secrets.randbelow(hi - lo + 1)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text):
    ctx.write(name, text)
    ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(sha(ctx.need_file(name)) == h, name + ' は原本です。変更しないでください。')


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def mutate(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, float):
        return v + 1.0
    if isinstance(v, str):
        return v + 'x'
    if isinstance(v, list):
        return v[:-1] if v else [0]
    if isinstance(v, dict):
        d = dict(v)
        k = sorted(d)[0]
        d[k] = mutate(d[k])
        return d
    return v


def finish_exp(ctx, exp):
    ctx.data['exp'] = dumps(exp)
    k = sorted(exp)[0]
    w = dict(exp)
    w[k] = mutate(w[k])
    ctx.data['wrong1'] = dumps(w)


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= 0.011
        except (TypeError, ValueError):
            return False
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def jcheck(ctx, name='answer.json'):
    try:
        got = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(got, dict), name + ' の最上位はオブジェクトです。')
    exp = json.loads(ctx.data['exp'])
    for k, v in exp.items():
        ctx.require(k in got, f'キー "{k}" がありません。')
        ctx.require(same(got[k], v), f'"{k}" の値が記録と合いません。出力を読み直しましょう。')
    ctx.require(set(got) <= set(exp), '指定にないキーは入れません。')


def lines_of(ctx, name, n=None):
    ls = [x.strip() for x in ctx.need_file(name).splitlines() if x.strip()]
    if n is not None:
        ctx.require(len(ls) == n, f'{name} には{n}行のコマンドを書きます。')
    return ls


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def cmd(ctx, name, n):
    return [toks(ctx, x) for x in lines_of(ctx, name, n)]


def has_flag(t, *flags):
    for x in t:
        for f in flags:
            if len(f) == 1 and x.startswith('-') and not x.startswith('--') and f in x[1:]:
                return True
            if len(f) > 1 and (x == '--' + f or x.startswith('--' + f + '=')):
                return True
    return False


def after(t, *flags):
    """フラグの直後の値。 -p 10 / --pid=10 / -p10 に対応。"""
    for i, x in enumerate(t):
        for f in flags:
            if x == f and i + 1 < len(t):
                return t[i + 1]
            if x.startswith(f + '=') and f.startswith('--'):
                return x.split('=', 1)[1]
            if len(f) == 2 and not f.startswith('--') and x.startswith(f) and len(x) > 2 and x[2] != '-':
                return x[2:]
    return None


def need(ctx, t, prog):
    ctx.require(t and t[0] == prog, f'{prog} で始めます。')
    ctx.require('sudo' not in t, 'rootは使いません。')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'27-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation, tip=TIP)


JSON_WRONG = ["echo '{}' > answer.json", "echo '<<wrong1>>' > answer.json"]
JSON_SOL = "echo '<<exp>>' > answer.json"


def pids(k, lo=3000, hi=60000):
    out = set()
    while len(out) < k:
        out.add(rp(lo, hi))
    return sorted(out)


# ------------------------------------------------------------ 1 親子・ゾンビ・孤児
def s1(ctx):
    b = rp(3000, 9000)
    sup, w1, w2, o = b + 30, b + 31, b + 32, b + 50
    zs = [b + 33 + i for i in range(rp(1, 2))]
    rows = [(1, 0, 'Ss', 'root', '/sbin/init'), (b, 1, 'Ss', 'root', 'sshd: trainee [priv]'), (b + 5, 1, 'Ss', 'root', 'cron -f'),
            (b + 10, b, 'Ss', 'trainee', '-bash'), (sup, b + 10, 'Sl', 'trainee', 'python3 supervisor.py'),
            (w1, sup, 'S', 'trainee', 'python3 worker.py'), (w2, sup, 'R', 'trainee', 'python3 worker.py'),
            (o, 1, 'S', 'trainee', 'python3 /home/trainee/longjob.py')]
    rows += [(z, sup, 'Z', 'trainee', '[worker] <defunct>') for z in zs]
    rows.sort()
    put(ctx, 'ps.txt', '  PID  PPID STAT USER     COMMAND\n' + ''.join(f'{a:5d} {p:5d} {s:<4} {u:<8} {c}\n' for a, p, s, u, c in rows))
    cwd = '/home/trainee/work/' + secrets.token_hex(2)
    put(ctx, 'pwdx.txt', f'{o}: {cwd}\n{sup}: /home/trainee/app\n')
    finish_exp(ctx, {'zombies': zs, 'zombie_parent': sup, 'orphans': [o], 'orphan_cwd': cwd})
    ctx.write('requirements.txt', 'ps.txt(ps -eo pid,ppid,stat,user,cmd の記録)とpwdx.txt(pwdxの記録)を読み、answer.jsonに '
              'zombies(ゾンビPID昇順), zombie_parent(そのゾンビの親PID), orphans(親がPID 1に付け替わった一般ユーザーのプロセスPID配列), '
              'orphan_cwd(その孤児のカレントディレクトリ)を書く。')


def c1(ctx):
    need_ro(ctx)
    jcheck(ctx)


mission(1, 'ps・pstree・pwdxで親子関係とゾンビ・孤児を見分ける',
        '何日も動く作業の周りにdefunctな行があります。ps(STAT列がZ)とPPIDの親子関係を読み、ゾンビと孤児の違い、PID 1(init/systemd)の役割を整理して、pstreeで描くはずの木を頭の中で組み立てます。孤児の作業ディレクトリはpwdxの記録で調べます。',
        ['ゾンビとその親を特定', 'PID 1に引き取られた孤児と、そのcwdを特定'], s1, c1, JSON_SOL, JSON_WRONG,
        'ゾンビ(STAT=Z)は終了済みだが親がwaitしないため終了コードの置き場だけ残った子で、killしても消えません。親にSIGCHLDを送って回収させるか親を終了させます。孤児は親が先に終了した子で、PID 1に付け替えられて(PPID=1)回収されます。pstree -p で木構造、ps -o pid,ppid,stat、pwdx PID でcwdを確認します。',
        'STATがZの行がゾンビで、その行のPPIDが親です。親が1の一般ユーザーのプロセスが孤児です。', 'awkでSTATとPPIDを絞り、孤児のPIDをpwdx.txtから引きます。')


# ------------------------------------------------------------ 2 pgrep / pidwait / top
def s2(ctx):
    tag = 'batch-' + secrets.token_hex(3)
    user = secrets.choice(['trainee', 'deploy', 'analyst'])
    ctx.data.update(tag=tag, user=user, pid=rp(3000, 9000))
    ctx.write('requirements.txt', f'ユーザー{user}が動かしている「{tag}」を含む処理(PID {ctx.data["pid"]})について、watch.txtに4行を書く。'
              f'1行目: 対象をコマンドライン付きで確認するpgrep(-u {user} -f)。2行目: その終了を待つpidwait(-u -f)。'
              f'3行目: topをバッチモード1回(-b -n 1)でPID指定(-p)して負荷を見る。4行目: psでpid,ni,pcpu,cmdの列だけをそのPIDについて表示。実行はしません。')


def c2(ctx):
    a, b, tp, ps = cmd(ctx, 'watch.txt', 4)
    d = ctx.data
    need(ctx, a, 'pgrep')
    ctx.require(has_flag(a, 'f') and after(a, '-u') == d['user'] and any(d['tag'] in x for x in a), 'pgrep は -u 所有者 -f 識別子 を指定します。')
    ctx.require(has_flag(a, 'a') or has_flag(a, 'l'), 'コマンドラインを見るには -a (または -l) を付けます。')
    need(ctx, b, 'pidwait')
    ctx.require(has_flag(b, 'f') and after(b, '-u') == d['user'] and any(d['tag'] in x for x in b), 'pidwaitも -u と -f と識別子を指定します。')
    need(ctx, tp, 'top')
    ctx.require(has_flag(tp, 'b') and after(tp, '-n') == '1' and after(tp, '-p') == str(d['pid']), 'top -b -n 1 -p PID を使います。')
    need(ctx, ps, 'ps')
    ctx.require(after(ps, '-p') == str(d['pid']) and any(x.startswith('pid,') and 'ni' in x and 'pcpu' in x and 'cmd' in x for x in ps) or
                after(ps, '-o') and after(ps, '-p') == str(d['pid']) and all(k in after(ps, '-o') for k in ('pid', 'ni', 'pcpu', 'cmd')),
                'ps -o pid,ni,pcpu,cmd -p PID の形にします。')


SOL2 = """printf '%s\\n' "pgrep -af -u <<user>> -- <<tag>>" "pidwait -u <<user>> -f -- <<tag>>" "top -b -n 1 -p <<pid>>" "ps -o pid,ni,pcpu,cmd -p <<pid>>" > watch.txt"""
mission(2, 'pgrep・pidwait・top・psで対象を確かめて終了を待つ',
        '終わったら次の工程へ進みたいバッチ処理があります。psとtopの出力を見る定番に加え、名前や引数でPIDを探すpgrepと、その終了を待つpidwait(pwait)を組み合わせて、ポーリングなしで待つ手順を作ります。',
        ['watch.txtに4行のコマンドを書く'], s2, c2, SOL2,
        ['printf \'%s\\n\' "pgrep python" "sleep 600" "top" "ps" > watch.txt',
         'printf \'%s\\n\' "pgrep -u <<user>> <<tag>>" "pidwait <<tag>>" "top -p <<pid>>" "ps -p <<pid>>" > watch.txt'],
        'pgrepはPIDの検索(-fで引数まで、-aで表示、-uで所有者)、pidwaitはその終了を待ちます。topの-bは非対話、-nは回数、-pはPID指定、psの-oは列の指定でNI(nice値)やpcpuを選べます。名前だけの指定は無関係な処理に当たるので、-uと-fで絞ります。',
        'まず対象を特定する読み取り(pgrep -a)、次に待つ(pidwait)、最後に状態を見る(top/ps)の順です。', 'フラグ -u -f -a -b -n -p -o を組み合わせます。')


# ------------------------------------------------------------ 3 prtstat / pslog / peekfd
def s3(ctx):
    pid = rp(3000, 60000)
    fd = rp(3, 8)
    th = rp(2, 12)
    ppid = rp(500, 2999)
    st = secrets.choice([('S', 'sleeping'), ('R', 'running'), ('D', 'disk sleep')])
    log = f'/var/log/app/{secrets.token_hex(2)}.log'
    put(ctx, 'prtstat.txt', f'Process: worker             State: {st[0]} ({st[1]})\n  CPU#:  1  TTY: 0:0    Threads: {th}\n'
        f'Process ID: {pid}  Session ID: {ppid}\nParent ID: {ppid}\nUid: 1000  Gid: 1000\n')
    other = fd + 1
    put(ctx, 'pslog.txt', f'Pid name: worker\nPid no: {pid}\nOpen files:\n  fd 0 /dev/null\n  fd 1 /dev/null\n  fd 2 /dev/null\n  fd {fd} {log}\n  fd {other} socket:[{rp(10000, 99999)}]\n')
    ctx.data['pid'], ctx.data['fd'] = pid, fd
    finish_exp(ctx, {'state': st[0], 'threads': th, 'ppid': ppid, 'log_path': log, 'log_fd': fd})
    ctx.write('requirements.txt', 'prtstat.txt(prtstatの出力)とpslog.txt(pslogの出力)を読み、answer.jsonに state(1文字), threads, ppid, log_path, log_fd を書く。'
              f'さらにpeek.txtに、そのログfdを通る入出力を覗くpeekfdコマンドを1行書く(ptrace権限が必要なので実行はしない)。')


def c3(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'peek.txt', 1)
    need(ctx, t, 'peekfd')
    d = ctx.data
    ctx.require(str(d['pid']) in t and t.index(str(d['pid'])) < len(t) - 1 and str(d['fd']) in t[t.index(str(d['pid'])) + 1:], 'peekfd PID FD の順に指定します。')


SOL3 = """echo '<<exp>>' > answer.json
echo "peekfd <<pid>> <<fd>>" > peek.txt"""
mission(3, 'prtstat・pslogで素性を読みpeekfdで中身を覗く',
        'psmiscのprtstatはプロセスの状態・親・スレッド数を、pslogは書き込み先のログファイルを教えてくれます。出力の記録から対象の素性を読み取り、さらにpeekfd(概念)でそのファイルディスクリプタに流れるデータを覗くコマンドを書きます。',
        ['answer.jsonに素性を書く', 'peekfdコマンドをpeek.txtへ'], s3, c3, SOL3,
        ["echo '{}' > answer.json\necho 'peekfd worker' > peek.txt", "echo '<<wrong1>>' > answer.json\necho 'peekfd <<pid>> <<fd>>' > peek.txt"],
        'prtstat PID は/proc/PID/statの要約、pslog PID は開いているログ/ファイルの一覧、peekfd PID FD... はptraceでread/writeの内容を覗きます(strace -e read,write の軽量版)。権限が必要で、本番では慎重に使います。fdの番号は/proc/PID/fd と一致します。',
        'ログのパスがつながっているfd番号を取り違えないようにします。', 'prtstat.txtとpslog.txtから値を拾います。')


# ------------------------------------------------------------ 4 pmap / maps
def s4(ctx):
    pid = rp(3000, 60000)
    base = 0x55d0c0000000 + rp(0, 0xfff) * 0x1000
    spec = [('/usr/bin/app', 'r-x--', rp(8, 40), 'x'), ('/usr/bin/app', 'rw---', rp(1, 8), 'x'), ('[ heap ]', 'rw---', rp(100, 900) * 4, 'h'),
            ('libc.so.6', 'r-x--', rp(900, 1600), 'x'), ('[ anon ]', 'rw---', rp(20, 90) * 4, 'a'), ('[ anon ]', 'rw---', rp(20, 90) * 4 + 4, 'a'),
            ('[ stack ]', 'rw---', 132, 's')]
    rows, maps, addr = [], [], base
    heap = None
    for name, mode, kb, kind in spec:
        rss = max(4, kb - rp(0, 3) * 4)
        rows.append((addr, kb, rss, name, mode))
        mn = name if name.startswith('/') else ('[heap]' if kind == 'h' else '[stack]' if kind == 's' else '')
        maps.append(f'{addr:x}-{addr + kb * 1024:x} {mode[:3]}p 00000000 00:00 0 {mn}'.rstrip())
        if kind == 'h':
            heap = f'{addr:x}-{addr + kb * 1024:x}'
        addr += kb * 1024 + 0x1000
    tk = sum(r[1] for r in rows)
    tr = sum(r[2] for r in rows)
    out = f'{pid}:   /usr/bin/app\nAddress           Kbytes     RSS   Dirty Mode  Mapping\n'
    out += ''.join(f'{a:016x} {k:7d} {r:7d} {r:7d} {m} {n}\n' for a, k, r, n, m in rows)
    out += f'---------------- ------- ------- ------- \ntotal kB         {tk:7d} {tr:7d} {tr:7d}\n'
    put(ctx, 'pmap.txt', out)
    put(ctx, 'maps.txt', '\n'.join(maps) + '\n')
    big = max(rows, key=lambda r: r[1])[3]
    finish_exp(ctx, {'total_kb': tk, 'rss_kb': tr, 'largest_mapping': big, 'anon_kb': sum(r[1] for r in rows if r[3] == '[ anon ]'), 'heap_range': heap})
    ctx.write('requirements.txt', 'pmap.txt(pmap -x PID)とmaps.txt(/proc/PID/maps)を読み、answer.jsonに total_kb(Kbytes合計), rss_kb(RSS合計), '
              'largest_mapping(Kbytesが最大のMapping名), anon_kb([ anon ]のKbytes合計), heap_range(mapsの[heap]のアドレス範囲)を書く。')


mission(4, 'pmapと/proc/PID/mapsでメモリの使われ方を読む',
        'アプリのメモリ使用量が増え続けています。pmap -x のKbytesとRSS、/proc/<pid>/maps のアドレス範囲を読み比べて、どのマッピング(ヒープ・匿名領域・共有ライブラリ)が大きいかを数字で報告してください。',
        ['answer.jsonに合計・最大・匿名・ヒープ範囲を書く'], s4, lambda ctx: (need_ro(ctx), jcheck(ctx)), JSON_SOL, JSON_WRONG,
        'pmap PID は仮想メモリのマッピング一覧で、Kbytesは仮想、RSSは実際に載っている量です。/proc/PID/maps は同じ情報の生データ(開始-終了 権限 オフセット デバイス inode 名前)です。[heap]はmalloc、[ anon ]は匿名mmap、[stack]はスタックです。',
        'KbytesとRSSの違い、[heap]と[ anon ]の違いを区別します。', 'awkで列を足し合わせ、mapsの[heap]行を探します。')


# ------------------------------------------------------------ 5 /proc/PID
def s5(ctx):
    pid = rp(3000, 60000)
    tok = secrets.token_hex(4)
    port = rp(8000, 8999)
    args = ['--port', str(port), '--tag', secrets.token_hex(2)]
    ppid = rp(500, 2999)
    log_fd = rp(3, 8)
    nfd = rp(7, 12)
    d = f'proc/{pid}'
    put(ctx, f'{d}/status', f'Name:\tserver\nState:\tS (sleeping)\nPid:\t{pid}\nPPid:\t{ppid}\nUid:\t1000\t1000\t1000\t1000\nVmRSS:\t{rp(5000, 90000)} kB\n')
    ctx.write(f'{d}/cmdline', b'/usr/bin/server\0' + b'\0'.join(a.encode() for a in args) + b'\0', binary=True)
    ctx.write(f'{d}/environ', f'HOME=/home/trainee\0LANG=C\0APP_TOKEN={tok}\0PATH=/usr/bin\0'.encode(), binary=True)
    ctx.mkdir(f'{d}/fd')
    for i in range(nfd):
        tgt = '/dev/null' if i < 3 else f'/var/log/app/{secrets.token_hex(2)}.log' if i == log_fd else f'socket:[{rp(10000, 99999)}]'
        os.symlink(tgt, ctx.p(f'{d}/fd/{i}'))
    ctx.data['pid'] = pid
    finish_exp(ctx, {'name': 'server', 'ppid': ppid, 'args': args, 'app_token': tok, 'fd_count': nfd, 'log_fd': log_fd})
    ctx.write('requirements.txt', f'proc/{pid}/ はプロセスの/proc/<pid>/を複写したものです。status, cmdline(NUL区切り), environ(NUL区切り), fd/(シンボリックリンク)を調べ、'
              'answer.jsonに name, ppid, args(argv[0]を除く引数の配列), app_token(環境変数APP_TOKENの値), fd_count(fdの個数), log_fd(.logを指すfd番号)を書く。')


mission(5, '/proc/PID の status・cmdline・environ・fd を読む',
        'プロセスの正体はpsだけではわかりません。/proc/<pid>/status で状態と親、cmdline で起動引数、environ で環境変数、fd/ で開いているファイルを調べます。cmdlineとenvironはNUL区切りなので tr で読みやすくします。',
        ['answer.jsonに素性を書く'], s5, lambda ctx: (need_ro(ctx), jcheck(ctx)), JSON_SOL, JSON_WRONG,
        '/proc/PID/status は人が読める状態、cmdline/environ はNUL(\\0)区切り(tr "\\0" "\\n" < environ)、fd/ は開いているファイルへのシンボリックリンク(ls -l、本数がfd数)です。/proc/PID/fd の本数はファイルディスクリプタ上限(RLIMIT_NOFILE)との比較に使います。',
        'cmdlineの最初の要素は実行ファイルです。environは行ごとにKEY=値です。', 'tr "\\0" "\\n"、ls proc/PID/fd | wc -l、ls -l でリンク先を見ます。')


# ------------------------------------------------------------ 6 コンテキストスイッチ
def s6(ctx):
    names = ['encoder', 'webserver', 'logger', 'compiler']
    ps = pids(4)
    rows = []
    for nm, p in zip(names, ps):
        total = rp(40000, 90000)
        rows.append((p, nm, total, 0))
    # 非自発率を明確に分ける
    ratios = [0.85, 0.40, 0.08, 0.60]
    secrets.SystemRandom().shuffle(ratios)
    data = []
    for (p, nm, total, _), r in zip(rows, ratios):
        nv = int(total * r)
        data.append((p, nm, total - nv, nv))
    text = 'PID NAME voluntary_ctxt_switches nonvoluntary_ctxt_switches\n' + ''.join(f'{p} {n} {v} {nv}\n' for p, n, v, nv in data)
    put(ctx, 'ctxsw.txt', text)
    cpu = max(data, key=lambda r: r[3] / (r[2] + r[3]))
    io = min(data, key=lambda r: r[3] / (r[2] + r[3]))
    finish_exp(ctx, {'cpu_bound': cpu[0], 'io_bound': io[0], 'cpu_bound_total': cpu[2] + cpu[3]})
    ctx.write('requirements.txt', 'ctxsw.txt は4つのプロセスの/proc/PID/statusにある voluntary_ctxt_switches と nonvoluntary_ctxt_switches の抜粋です。'
              'answer.jsonに cpu_bound(非自発の割合が最大のPID), io_bound(最小のPID), cpu_bound_total(cpu_boundの合計切替回数)を書く。')


mission(6, 'コンテキストスイッチの回数からCPU待ちとI/O待ちを見分ける',
        '/proc/<pid>/status の voluntary_ctxt_switches は自分からCPUを手放した(I/O待ちなど)回数、nonvoluntary_ctxt_switches はタイムスライス切れなどで取り上げられた回数です。割合を見ればCPUを使い切るプロセスと待ちが多いプロセスを区別できます。',
        ['answer.jsonにCPU型とI/O型のPIDを書く'], s6, lambda ctx: (need_ro(ctx), jcheck(ctx)), JSON_SOL, JSON_WRONG,
        'コンテキストスイッチはCPUが実行中のプロセスを別のものに切り替えることです。自発的(voluntary)が多い=I/Oや待ち中心、非自発的(nonvoluntary)が多い=CPUを奪い合っている状態で、nice/chrt/tasksetで調整する材料になります。',
        '合計ではなく、非自発の割合で比べます。', 'awkで nv/(v+nv) を計算して並べます。')


# ------------------------------------------------------------ 7 loadavg / tload
def s7(ctx):
    n = secrets.choice([2, 4, 8])
    trend = secrets.choice(['rising', 'falling'])
    base = rp(50, 300) / 100 * n / 2
    a, b, c = (base * 1.6, base * 1.2, base) if trend == 'rising' else (base, base * 1.2, base * 1.6)
    l1, l5, l15 = round(a, 2), round(b, 2), round(c, 2)
    run = rp(1, 9)
    put(ctx, 'loadavg.txt', f'{l1:.2f} {l5:.2f} {l15:.2f} {run}/{rp(200, 900)} {rp(10000, 99999)}\n')
    put(ctx, 'lscpu.txt', f'Architecture:        x86_64\nCPU(s):              {n}\nThread(s) per core:  2\n')
    d = rp(1, 5)
    sc = math.ceil(l1)
    ctx.data.update(d=d, sc=sc)
    finish_exp(ctx, {'cpus': n, 'load1_per_cpu': round(l1 / n, 2), 'load15_per_cpu': round(l15 / n, 2), 'trend': trend,
                     'state': 'overloaded' if l5 / n > 1 else 'ok', 'running': run})
    ctx.write('requirements.txt', 'loadavg.txt(/proc/loadavg)とlscpu.txtを読み、answer.jsonに cpus, load1_per_cpu(1分値/CPU数, 小数2桁), load15_per_cpu, '
              'trend(1分値が15分値より大きければ rising、小さければ falling), state(5分値/CPU数が1を超えれば overloaded、以内なら ok), running(実行可能タスク数、4つ目の欄の分子)を書く。'
              f'さらに tload.txt にtloadを{d}秒間隔(-d)・目盛り{sc}(-s)で動かす1行を書く(実行はしない)。')


def c7(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'tload.txt', 1)
    need(ctx, t, 'tload')
    ctx.require(after(t, '-d') == str(ctx.data['d']) and after(t, '-s') == str(ctx.data['sc']), 'tload -d 間隔 -s 目盛り の形にします。')


SOL7 = """echo '<<exp>>' > answer.json
echo "tload -d <<d>> -s <<sc>>" > tload.txt"""
mission(7, 'ロードアベレージをCPU数で割って読む(/proc/loadavg・tload)',
        'ロードアベレージは1/5/15分の実行待ち(+割り込み不可の待ち)プロセスの平均数で、CPU数で割って初めて混み具合になります。値の並び(1分>15分なら上昇中)も読みます。tloadは端末にグラフで描きます。',
        ['answer.jsonに指標を書く', 'tload.txtにtloadコマンドを書く'], s7, c7, SOL7,
        ["echo '{}' > answer.json\necho 'tload' > tload.txt", "echo '<<wrong1>>' > answer.json\necho 'tload -d <<d>> -s <<sc>>' > tload.txt"],
        '/proc/loadavg は「1分 5分 15分 実行中/全タスク 直近PID」。CPU数(lscpu、nproc)で割って1付近が満員の目安です。1分>15分なら悪化中、逆なら回復中。tload [-d 秒] [-s 目盛り] [tty] は負荷のグラフです。topやuptimeでも同じ値が見られます。',
        'CPU数で割る点と、並びから傾向を読む点です。', 'awkやpythonで割り算して小数2桁に丸めます。')


# ------------------------------------------------------------ 8 nice/renice/snice/skill/top/ps
def s8(ctx):
    pid = rp(3000, 60000)
    n = rp(5, 15)
    user = secrets.choice(['analyst', 'builder', 'deploy'])
    ctx.data.update(pid=pid, n=n, user=user)
    ctx.write('requirements.txt', f'{user}の重い集計(PID {pid})が他の作業を邪魔しています。plan.txtに5行書く。1行目: そのPIDのnice値を{n}にするrenice。'
              f'2行目: {user}の全プロセスの優先度を{n}だけ下げるsnice(+{n}形式)。3行目: {user}の全プロセスを一時停止するskill(SIGSTOPを名前で)。'
              f'4行目: 後で再開するkill(SIGCONTをPID指定)。5行目: ps -oでpid,ni,cmdをそのPIDだけ表示。実行はしません。')


def c8(ctx):
    a, b, c, k, p = cmd(ctx, 'plan.txt', 5)
    d = ctx.data
    need(ctx, a, 'renice')
    ctx.require(str(d['n']) in a and after(a, '-p') == str(d['pid']) or (str(d['n']) in a and str(d['pid']) in a), 'renice -n N -p PID の形にします。')
    ctx.require('-n' in a and a[a.index('-n') + 1] == str(d['n']) or a[1] == str(d['n']), '優先度は -n で指定します。')
    need(ctx, b, 'snice')
    ctx.require(d['user'] in b and any(x.lstrip('+') == str(d['n']) for x in b), 'snice +N -u ユーザー の形にします。')
    need(ctx, c, 'skill')
    ctx.require(d['user'] in c and any(x in ('-STOP', '-SIGSTOP', '-19', '-s') for x in c) and ('-s' not in c or 'STOP' in c), 'skill -STOP -u ユーザー の形にします。')
    need(ctx, k, 'kill')
    ctx.require(str(d['pid']) in k and any(x in ('-CONT', '-SIGCONT', '-18', '-s') for x in k) and ('-s' not in k or 'CONT' in k), 'kill -CONT PID の形にします。')
    need(ctx, p, 'ps')
    ctx.require(str(d['pid']) in p and any(x.replace('-o', '').startswith('pid,ni') for x in p), 'ps -o pid,ni,cmd -p PID の形にします。')


SOL8 = """printf '%s\\n' "renice -n <<n>> -p <<pid>>" "snice +<<n>> -u <<user>>" "skill -STOP -u <<user>>" "kill -CONT <<pid>>" "ps -o pid,ni,cmd -p <<pid>>" > plan.txt"""
mission(8, 'nice・renice・snice・skillで優先度を下げて一時停止する',
        '集計処理を止めたくはないが、他の作業を優先したい場面です。起動時にnice、起動後にrenice、ユーザー単位でsnice、一時停止にskill(SIGSTOP)、再開にkill -CONT、結果の確認にps/topを使います。',
        ['plan.txtに5行のコマンドを書く'], s8, c8, SOL8,
        ['printf \'%s\\n\' "nice 10 ./job" "snice -9 -u <<user>>" "skill -KILL <<user>>" "kill <<pid>>" "ps" > plan.txt',
         'printf \'%s\\n\' "renice <<pid>> -n <<n>>" "snice <<user>>" "skill <<user>>" "kill -CONT <<pid>>" "ps <<pid>>" > plan.txt'],
        'nice -n N cmd は起動時、renice -n N -p PID は実行中のnice値変更(一般ユーザーは上げる方向のみ)です。snice/skill(procps)はユーザーや端末単位で優先度変更・シグナル送信を行います(現在は使われなくなりつつあり、pkillを推奨)。kill -STOP/-CONT は一時停止/再開で、top(キー r で renice)やps -o ni で確認します。',
        '優先度を下げる=nice値を上げる、一時停止=STOP、再開=CONTです。', 'man renice snice skill のフラグ順に注意します。')


# ------------------------------------------------------------ 9 シグナル
SIGS = [('設定ファイルを再読込させたい(終了させない)', 'SIGHUP', 1), ('処理を終わらせる通常の依頼(後始末ができる)', 'SIGTERM', 15),
        ('プロセスに握り潰されず強制終了したい(最後の手段)', 'SIGKILL', 9), ('プロセスを一時停止したい(捕捉できない)', 'SIGSTOP', 19),
        ('一時停止したプロセスを再開したい', 'SIGCONT', 18), ('アプリ独自の用途(例: ログローテーションやデバッグダンプ)', 'SIGUSR1', 10)]


def s9(ctx):
    order = list(range(6))
    secrets.SystemRandom().shuffle(order)
    letters = 'ABCDEF'
    ctx.write('scenarios.txt', ''.join(f'{letters[i]}: {SIGS[o][0]}\n' for i, o in enumerate(order)))
    ctx.data['scen_sha'] = sha(open(ctx.p('scenarios.txt')).read())
    names = {letters[i]: SIGS[o][1] for i, o in enumerate(order)}
    nums = {letters[i]: SIGS[o][2] for i, o in enumerate(order)}
    pid = rp(3000, 60000)
    ctx.data['pid'] = pid
    finish_exp(ctx, {'names': names, 'numbers': nums})
    ctx.write('requirements.txt', 'scenarios.txt の各場面(A-F)に合うシグナルを、answer.jsonの names(場面->SIG名)と numbers(場面->Linux x86での番号)に書く。'
              f'さらにreload.txtに、PID {pid} へ設定の再読込を依頼するkillコマンドを1行書く(実行はしない)。シグナル候補: SIGTERM SIGKILL SIGHUP SIGSTOP SIGCONT SIGUSR1。')


def c9(ctx):
    jcheck(ctx)
    (t,) = cmd(ctx, 'reload.txt', 1)
    need(ctx, t, 'kill')
    ctx.require(str(ctx.data['pid']) in t and any(x in ('-HUP', '-SIGHUP', '-1', 'HUP', 'SIGHUP') for x in t), '再読込はSIGHUPです。')


SOL9 = """echo '<<exp>>' > answer.json
echo "kill -HUP <<pid>>" > reload.txt"""
mission(9, 'シグナルの使い分け(TERM/KILL/HUP/STOP/CONT/USR1)',
        'killコマンドはプロセスを殺すものではなく、シグナルを送るものです。場面ごとにどのシグナルを選ぶべきか、名前と番号(kill -l で一覧)を答え、設定再読込のkillコマンドを書きます。',
        ['場面とシグナルの対応をanswer.jsonへ', 'reload.txtにkillコマンドを書く'], s9, c9, SOL9,
        ["echo '{}' > answer.json\necho 'kill -9 <<pid>>' > reload.txt", "echo '<<wrong1>>' > answer.json\necho 'kill -HUP <<pid>>' > reload.txt"],
        'SIGTERM(15)は終了依頼で捕捉可、SIGKILL(9)とSIGSTOP(19)は捕捉・無視できません。SIGHUP(1)は端末切断やデーモンの設定再読込、SIGCONT(18)で再開、SIGUSR1(10)はアプリ定義です。まずTERM、駄目ならKILLの順にします。kill -l で一覧、kill -s NAME PID でも指定できます。',
        '最後の手段はKILLですが、後始末ができないので最初には使いません。', 'kill -l で番号と名前を確かめます。')


# ------------------------------------------------------------ 10 nohup/disown/jobs
def s10(ctx):
    tag = 'run-' + secrets.token_hex(3)
    ctx.data['tag'] = tag
    put(ctx, 'job.sh', f'#!/bin/bash\necho "started {tag}"\nsleep 0.5\necho "finished {tag}"\n')
    os.chmod(ctx.p('job.sh'), 0o755)
    ctx.write('requirements.txt', 'launcher.sh を作る(bash)。./job.sh をターミナルを閉じても止まらないよう nohup で、出力は job.log へ(stderrも)、バックグラウンド(&)で起動し、'
              'その後 disown でシェルのジョブ表から外す。jobs で確認する手順もコメントに残すこと。')


def c10(ctx):
    need_ro(ctx)
    text = ctx.need_file('launcher.sh')
    code = '\n'.join(x for x in text.splitlines() if not x.strip().startswith('#'))
    ctx.require('nohup' in code and 'job.sh' in code, 'nohup ./job.sh で起動します。')
    ctx.require('&' in code.replace('&>', '').replace('2>&1', '').replace('&&', ''), 'バックグラウンド(&)で起動します。')
    ctx.require('disown' in code, 'disown でジョブ表から外します。')
    ctx.require('jobs' in text, 'コメントなどにjobsでの確認を残します。')
    for f in ('job.log', 'nohup.out'):
        if ctx.exists(f):
            os.remove(ctx.p(f))
    subprocess.run(['bash', 'launcher.sh'], cwd=str(ctx.work), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    end = time.time() + 6
    while time.time() < end:
        if 'finished ' + ctx.data['tag'] in (ctx.read('job.log') or ''):
            break
        time.sleep(0.2)
    ctx.require('started ' + ctx.data['tag'] in (ctx.read('job.log') or ''), 'job.log に出力が残りません。リダイレクトを確認しましょう。')


SOL10 = """cat > launcher.sh <<'EOF'
#!/bin/bash
nohup ./job.sh > job.log 2>&1 &
disown
# jobs で一覧、ps/pgrep でPIDを確認する
EOF"""
mission(10, 'nohup・&・disown・jobsでログアウト後も動かす',
        '長い処理をSSHで実行中にログアウトしてもSIGHUPで死なないようにします。nohupは終了シグナル(SIGHUP)を無視させ、&でバックグラウンド化、jobsでジョブ番号を確認、disownでシェルのジョブ表から外します。',
        ['launcher.shを書く(実行して出力が残ること)'], s10, c10, SOL10,
        ["cat > launcher.sh <<'EOF'\n#!/bin/bash\n./job.sh > job.log 2>&1 &\n# jobs\nEOF", "cat > launcher.sh <<'EOF'\n#!/bin/bash\nnohup ./job.sh > job.log 2>&1 &\n# jobs\nEOF"],
        'nohupはSIGHUPを無視して起動し(出力先未指定ならnohup.out)、&はバックグラウンド、jobsは現在のシェルのジョブ一覧、disownはジョブ表から外してシェル終了時のSIGHUP送信を防ぎます(bg/fgで戻せなくなる)。ログの出力先は明示します。長期運用にはsystemdやtmuxが望ましいです。',
        'nohup、&、disownの3点セットです。', 'コメント行にjobsを書いておきます。')


# ------------------------------------------------------------ 11 chrt/taskset/uclampset
def s11(ctx):
    d = dict(pid=rp(3000, 60000), prio=rp(10, 60), a=rp(0, 3), umin=rp(100, 400), umax=rp(600, 1024))
    d['b'] = d['a'] + rp(1, 3)
    d['cpus'] = f'{d["a"]},{d["b"]}'
    ctx.data.update(d)
    ctx.write('requirements.txt', f'リアルタイム処理(PID {d["pid"]})を、plan.txtの3行で調整する。1行目: chrtでSCHED_FIFO・優先度{d["prio"]}に(-f -p)。'
              f'2行目: tasksetでCPU {d["cpus"]} だけに固定(-c -p)。3行目: uclampsetで使用率クランプの下限{d["umin"]}・上限{d["umax"]}を設定(-m -M -p)。実行はしません。')


def c11(ctx):
    a, b, c = cmd(ctx, 'plan.txt', 3)
    d = ctx.data
    need(ctx, a, 'chrt')
    ctx.require(has_flag(a, 'f', 'fifo') and has_flag(a, 'p', 'pid') and str(d['prio']) in a and str(d['pid']) == a[-1], 'chrt -f -p 優先度 PID の形にします。')
    need(ctx, b, 'taskset')
    ctx.require(has_flag(b, 'c', 'cpu-list') and has_flag(b, 'p', 'pid') and d['cpus'] in b and str(d['pid']) == b[-1], 'taskset -cp CPU一覧 PID の形にします。')
    need(ctx, c, 'uclampset')
    ctx.require(after(c, '-m') == str(d['umin']) and after(c, '-M') == str(d['umax']) and after(c, '-p') == str(d['pid']), 'uclampset -m 下限 -M 上限 -p PID の形にします。')


SOL11 = """printf '%s\\n' "chrt -f -p <<prio>> <<pid>>" "taskset -cp <<cpus>> <<pid>>" "uclampset -m <<umin>> -M <<umax>> -p <<pid>>" > plan.txt"""
mission(11, 'chrt・taskset・uclampsetでスケジューリングを調整する',
        'niceでは足りないとき、スケジューリングポリシー(chrt)、使用するCPUの固定(taskset)、使用率クランプ(uclampset)を調整します。リアルタイム優先度は強力なので手順書の段階で慎重に確認します。',
        ['plan.txtに3行のコマンドを書く'], s11, c11, SOL11,
        ['printf \'%s\\n\' "nice -n -20 <<pid>>" "taskset <<cpus>> <<pid>>" "uclampset <<pid>>" > plan.txt',
         'printf \'%s\\n\' "chrt -p <<prio>> <<pid>>" "taskset -p <<cpus>> <<pid>>" "uclampset -m <<umin>> -M <<umax>> <<pid>>" > plan.txt'],
        'chrt -f(FIFO)/-r(RR)/-o(OTHER) -p 優先度 PID でポリシー変更、taskset -cp CPU一覧 PID でアフィニティ、uclampset -m/-M -p PID でユーティライゼーションのクランプを指定します。実機のRT設定はCAP_SYS_NICEが要り、暴走するとシステムが固まるので注意です。chrt -p PID(優先度なし)は表示だけです。',
        '3つとも -p でPIDを指定する形です(chrtのPIDは末尾)。', 'フラグの組み合わせと引数の順序を確かめます。')


# ------------------------------------------------------------ 12 OOM / choom
def s12(ctx):
    ps = pids(4)
    names = ['postgres', 'batch-report', 'nginx', 'indexer']
    sc = [rp(100, 300), rp(500, 800), rp(50, 150), rp(300, 450)]
    adj = [0, 0, 0, 0]
    put(ctx, 'oom.txt', 'PID NAME oom_score oom_score_adj\n' + ''.join(f'{p} {n} {s} {a}\n' for p, n, s, a in zip(ps, names, sc, adj)))
    ctx.data.update(db=ps[0], batch=ps[1], val=rp(300, 800))
    v = max(zip(sc, ps))[1]
    finish_exp(ctx, {'victim': v, 'victim_name': names[ps.index(v)]})
    ctx.write('requirements.txt', f'oom.txt は /proc/PID/oom_score と oom_score_adj の記録です。answer.jsonに、メモリ不足で最初にOOMキラーに選ばれそうな victim(PID)と victim_name を書く。'
              f'さらに protect.txt に2行: 1行目はpostgres(PID {ps[0]})を殺されにくくするchoom(-1000)、2行目はbatch-report(PID {ps[1]})を先に殺される側にするchoom({ctx.data["val"]})。')


def c12(ctx):
    need_ro(ctx)
    jcheck(ctx)
    a, b = cmd(ctx, 'protect.txt', 2)
    d = ctx.data
    need(ctx, a, 'choom')
    ctx.require(after(a, '-p') == str(d['db']) and after(a, '-n') == '-1000', 'choom -p PID -n -1000 の形にします。')
    need(ctx, b, 'choom')
    ctx.require(after(b, '-p') == str(d['batch']) and after(b, '-n') == str(d['val']), 'choom -p PID -n 値 の形にします。')


SOL12 = """echo '<<exp>>' > answer.json
printf '%s\\n' "choom -p <<db>> -n -1000" "choom -p <<batch>> -n <<val>>" > protect.txt"""
mission(12, 'OOM scoreを読みchoomで殺される順序を変える',
        'メモリが枯渇するとカーネルのOOMキラーがoom_scoreの高いプロセスを選んで殺します。/proc/PID/oom_score(算出値)とoom_score_adj(-1000〜1000の調整)の記録から犠牲者を予想し、DBを守り、バッチを先に犠牲にする設定をchoomで組みます。',
        ['犠牲者をanswer.jsonへ', 'protect.txtにchoomを2行'], s12, c12, SOL12,
        ["echo '{}' > answer.json\nprintf '%s\\n' 'choom -p <<db>> -n 1000' 'choom -p <<batch>> -n -1000' > protect.txt",
         "echo '<<wrong1>>' > answer.json\nprintf '%s\\n' 'choom -p <<db>> -n -1000' 'choom -p <<batch>> -n <<val>>' > protect.txt"],
        'oom_scoreが高いほど殺されやすく、oom_score_adjを-1000にすると対象外(CAP_SYS_RESOURCEが必要)、+1000で最優先の犠牲者になります。choom -p PID -n 値 が /proc/PID/oom_score_adj の書換えの簡便版です。OOMの発生はdmesgや/var/log/messagesに残ります。',
        '数値が最大のものが先に選ばれます。守る側は小さく(負に)します。', 'oom.txtの列を読み、choomは -p と -n を使います。')


# ------------------------------------------------------------ 13 prlimit / fd上限
def s13(ctx):
    soft = secrets.choice([256, 512, 1024])
    hard = soft * 8
    new = soft * rp(2, 4)
    pid = rp(3000, 60000)
    n = soft - rp(1, 3)
    put(ctx, 'limits.txt', f'Limit                     Soft Limit           Hard Limit           Units\nMax cpu time              unlimited            unlimited            seconds\n'
        f'Max open files            {soft}                 {hard}                 files\nMax processes             7890                 7890                 processes\n')
    put(ctx, 'error.log', f'accept: Too many open files (pid {pid})\nopen /var/log/app/x.log: Too many open files\n')
    put(ctx, 'fdcount.txt', f'{n}\n')
    ctx.data.update(pid=pid, new=new, hard=hard)
    finish_exp(ctx, {'soft': soft, 'hard': hard, 'open': n, 'headroom': soft - n})
    ctx.write('requirements.txt', f'limits.txt(/proc/{pid}/limits)、error.log、fdcount.txt(開いているfdの数)を読み、answer.jsonに soft, hard, open, headroom(softまでの残り)を書く。'
              f'さらに fix.txt に、PID {pid} のソフト上限を{new}(ハードは据え置き)にするprlimit(--nofile)を1行書く。')


def c13(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'fix.txt', 1)
    need(ctx, t, 'prlimit')
    d = ctx.data
    ctx.require(after(t, '--pid') == str(d['pid']) or after(t, '-p') == str(d['pid']), '--pid でPIDを指定します。')
    v = after(t, '--nofile') or after(t, '-n')
    ctx.require(v is not None and v.split(':')[0] == str(d['new']) and (':' not in v or v.split(':')[1] == str(d['hard'])), '--nofile=ソフト:ハード の形で、ハードは据え置きます。')


SOL13 = """echo '<<exp>>' > answer.json
echo "prlimit --pid <<pid>> --nofile=<<new>>:<<hard>>" > fix.txt"""
mission(13, 'ファイルディスクリプタ上限(Too many open files)をprlimitで直す',
        '「Too many open files」で新しい接続を受けられません。/proc/PID/limits のMax open files(ソフトとハード)、実際に開いているfd数、残りを調べ、ulimit -n の元になるRLIMIT_NOFILEを稼働中のプロセスに対してprlimitで引き上げます。',
        ['数値をanswer.jsonへ', 'fix.txtにprlimit'], s13, c13, SOL13,
        ["echo '{}' > answer.json\necho 'ulimit -n <<new>>' > fix.txt", "echo '<<wrong1>>' > answer.json\necho 'prlimit --pid <<pid>> --nofile=<<new>>:<<new>>' > fix.txt"],
        'ソフト上限は超えられず、ソフトはハードまで上げられます(ハード上げはroot)。prlimit --pid PID --nofile=ソフト:ハード で稼働中のプロセスを変更でき、ulimit -n は自シェルと子にだけ効きます。恒久対応はsystemdのLimitNOFILE=や/etc/security/limits.confです。リーク(fdの増え続け)も疑って ls /proc/PID/fd | wc -l を観測します。',
        '残りはソフト上限から現在の数を引きます。ハードは変えません。', 'prlimitの--nofileはソフト:ハードの順です。')


# ------------------------------------------------------------ 14 lscpu / chcpu / cpuinfo
def s14(ctx):
    sk = rp(1, 2)
    co = rp(2, 4)
    th = 2
    n = sk * co * th
    model = secrets.choice(['Intel(R) Xeon(R) Gold 6130', 'AMD EPYC 7413', 'Intel(R) Core(TM) i7-9700'])
    put(ctx, 'lscpu.txt', f'Architecture:        x86_64\nCPU(s):              {n}\nOn-line CPU(s) list: 0-{n - 1}\nThread(s) per core:  {th}\n'
        f'Core(s) per socket:  {co}\nSocket(s):           {sk}\nModel name:          {model}\n')
    ci = ''.join(f'processor\t: {i}\nmodel name\t: {model}\nphysical id\t: {i // (co * th)}\ncore id\t\t: {(i // th) % co}\ncpu MHz\t\t: {rp(1800, 3600)}.000\n\n' for i in range(n))
    put(ctx, 'cpuinfo.txt', ci)
    off = rp(1, n - 1)
    ctx.data['off'] = off
    finish_exp(ctx, {'cpus': n, 'sockets': sk, 'cores_per_socket': co, 'threads_per_core': th, 'model': model, 'cpuinfo_processors': n})
    ctx.write('requirements.txt', f'lscpu.txt(lscpuの出力)と cpuinfo.txt(/proc/cpuinfo)を読み、answer.jsonに cpus, sockets, cores_per_socket, threads_per_core, model, cpuinfo_processors(cpuinfoのprocessor行の数)を書く。'
              f'さらに offline.txt に、CPU {off} をオフラインにするchcpuを1行書く(実行はしない)。')


def c14(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'offline.txt', 1)
    need(ctx, t, 'chcpu')
    ctx.require(after(t, '-d') == str(ctx.data['off']) or after(t, '--disable') == str(ctx.data['off']), 'chcpu -d CPU番号 の形にします。')


SOL14 = """echo '<<exp>>' > answer.json
echo "chcpu -d <<off>>" > offline.txt"""
mission(14, 'lscpuと/proc/cpuinfoでCPU構成を読みchcpuで無効化する',
        'サーバーのCPU構成(ソケット・コア・ハイパースレッド)を確認し、検証のため特定のCPUをオフラインにする手順を書きます。lscpuは/proc/cpuinfoと/sys/devices/system/cpuを整形して要約します。',
        ['answer.jsonに構成を書く', 'offline.txtにchcpu -d'], s14, c14, SOL14,
        ["echo '{}' > answer.json\necho 'chcpu -e <<off>>' > offline.txt", "echo '<<wrong1>>' > answer.json\necho 'chcpu -d <<off>>' > offline.txt"],
        'CPU総数=ソケット×コア/ソケット×スレッド/コア です。lscpuの-eで一覧、/proc/cpuinfoのprocessor、core id、physical idでも同じことがわかります。chcpu -e/-d は有効化/無効化(root、/sys/devices/system/cpu/cpuN/onlineへの書込み)、chcpu -c/-g はconfigure/deconfigure(s390向け)です。',
        'CPU総数と「物理コア数」は別です。', 'lscpuの出力から数字を拾い、cpuinfoのprocessor行を数えます。')


# ------------------------------------------------------------ 15 lsmem / chmem / meminfo / slabtop
def s15(ctx):
    on = rp(8, 20)
    off = rp(2, 6)
    blocks = [('online', rp(1, 3)) for _ in range(3)]
    rows, start = [], 0
    onl = 0
    for st, k in [('online', on // 2), ('offline', off), ('online', on - on // 2)]:
        size = k * 128
        rows.append(f'0x{start * 128 * 2**20:016x}-0x{(start + k) * 128 * 2**20 - 1:016x} {size:5d}M {st:<8} {"yes" if st == "online" else "-":<9}')
        if st == 'online':
            onl += size
        start += k
    put(ctx, 'lsmem.txt', 'RANGE                                  SIZE  STATE    REMOVABLE\n' + '\n'.join(rows) + '\n\nMemory block size:       128M\n')
    avail = rp(1000, 6000) * 1024 + rp(0, 1023)
    put(ctx, 'meminfo.txt', f'MemTotal:       {onl * 1024} kB\nMemFree:        {rp(100, 900) * 1024} kB\nMemAvailable:   {avail} kB\nSwapTotal:      2097148 kB\nSwapFree:       2097148 kB\n')
    caches = [('dentry', rp(100, 900)), ('kmalloc-256', rp(100, 900)), ('inode_cache', rp(100, 900)), ('buffer_head', rp(100, 900))]
    put(ctx, 'slabtop.txt', ' OBJS ACTIVE  USE OBJ SIZE  SLABS OBJ/SLAB CACHE SIZE NAME\n' + ''.join(f'{rp(1000, 9000)} {rp(1000, 9000)} 90% 0.19K {rp(50, 400)} 21 {sz}K {n}\n' for n, sz in caches))
    top = max(caches, key=lambda c: c[1])[0]
    ctx.data['offmb'] = off * 128
    finish_exp(ctx, {'online_mb': onl, 'offline_mb': off * 128, 'mem_available_mb': avail // 1024, 'top_slab': top})
    ctx.write('requirements.txt', 'lsmem.txt(lsmemの出力), meminfo.txt(/proc/meminfo), slabtop.txt(slabtop -oの出力)を読み、answer.jsonに online_mb, offline_mb(合計), mem_available_mb(MemAvailableをMBに、切り捨て), '
              f'top_slab(CACHE SIZEが最大のキャッシュ名)を書く。さらに online.txt にオフライン分をすべてオンラインに戻すchmem(-e サイズ、{off * 128}M)を1行書く。')


def c15(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'online.txt', 1)
    need(ctx, t, 'chmem')
    ctx.require(has_flag(t, 'e', 'enable') and any(x in (f'{ctx.data["offmb"]}M', f'{ctx.data["offmb"] // 128 * 128}M') for x in t), 'chmem -e サイズ の形にします。')


SOL15 = """echo '<<exp>>' > answer.json
echo "chmem -e <<offmb>>M" > online.txt"""
mission(15, 'lsmem・chmem・/proc/meminfo・slabtopでメモリ状況を診断する',
        'メモリ増設/縮退後の状態を調べます。lsmemでメモリブロックのオンライン/オフライン、/proc/meminfoでMemAvailable(実質的な空き)、slabtopでカーネルのslabキャッシュの大物を確認し、オフラインのブロックをchmemで戻します。',
        ['answer.jsonに数値を書く', 'online.txtにchmem -e'], s15, c15, SOL15,
        ["echo '{}' > answer.json\necho 'chmem -d <<offmb>>M' > online.txt", "echo '<<wrong1>>' > answer.json\necho 'chmem -e <<offmb>>M' > online.txt"],
        'MemFreeは未使用だけ、MemAvailableはキャッシュを回収できる分を含む実質の空きです。lsmemはメモリブロック単位の状態、chmem -e/-d SIZE でオンライン/オフライン(root)、slabtopはカーネルオブジェクトキャッシュ(dentryやinodeなど)の使用量を上位から表示します。',
        'MemFreeではなくMemAvailableを使います。', 'awkでkB→MBに換算します。')


# ------------------------------------------------------------ 16 lsns / /proc/net / /sys/class
TYPES = ['cgroup', 'ipc', 'mnt', 'net', 'pid', 'user', 'uts']


def s16(ctx):
    cp = rp(3000, 60000)
    host, ctr = {}, {}
    iso = sorted(secrets.SystemRandom().sample(TYPES, rp(3, 6)))
    if 'pid' not in iso:
        iso = sorted(iso + ['pid'])
    for t in TYPES:
        host[t] = 4026531800 + rp(0, 99)
        ctr[t] = 4026532000 + rp(0, 999) if t in iso else host[t]
    mk = lambda d, p: 'NS TYPE NPROCS PID USER COMMAND\n' + ''.join(f'{d[t]} {t} {rp(1, 90)} {p} root /sbin/init\n' for t in TYPES)
    put(ctx, 'lsns_host.txt', mk(host, 1))
    put(ctx, 'lsns_ctr.txt', mk(ctr, cp))
    ifs = {'lo': 'unknown', 'eth0': 'up', 'eth1': secrets.choice(['up', 'down']), 'docker0': secrets.choice(['up', 'down'])}
    rx = {i: rp(1000, 99999) * 1000 + n for n, i in enumerate(ifs)}
    for i, st in ifs.items():
        put(ctx, f'sys/class/net/{i}/operstate', st + '\n')
    put(ctx, 'proc_net_dev.txt', 'Inter-|   Receive\n face |bytes    packets\n' + ''.join(f'{i}: {rx[i]} {rp(10, 999)}\n' for i in ifs))
    busy = max((rx[i], i) for i in ifs if i != 'lo')[1]
    finish_exp(ctx, {'container_pid_ns': ctr['pid'], 'isolated': iso, 'shared': sorted(set(TYPES) - set(iso)), 'up_ifaces': sorted(i for i, s in ifs.items() if s == 'up'), 'busiest_rx_iface': busy})
    ctx.write('requirements.txt', f'lsns_host.txt は lsns -p 1、lsns_ctr.txt はコンテナ内プロセス(PID {cp})の lsns -p の記録です。answer.jsonに container_pid_ns(コンテナのpid名前空間のID), '
              'isolated(ホストと異なる名前空間種別の配列), shared(同じ種別)を書く。さらに sys/class/net/*/operstate と proc_net_dev.txt(/proc/net/devの複写)から up_ifaces(operstateがupのIF名)と busiest_rx_iface(lo以外で受信バイト最大)も書く。')


mission(16, 'lsnsで名前空間を読み/proc/net・/sys/classでNICを調べる',
        'コンテナは名前空間(namespaces)で隔離されたプロセスにすぎません。lsnsの記録からホストとコンテナで共有している種別と分離している種別を見分け、ネットワーク名前空間内のNICの状態は/sys/class/net/*/operstate と /proc/net/dev から読み取ります。',
        ['answer.jsonに名前空間とNICを書く'], s16, lambda ctx: (need_ro(ctx), jcheck(ctx)), JSON_SOL, JSON_WRONG,
        '名前空間にはmnt/pid/net/ipc/uts/user/cgroupがあり、lsns でID(inode)・所属プロセス数が見られます。同じIDなら共有、違えば隔離です。/proc/<pid>/ns/* のリンク先と同じ情報です。/sys/class/net/IF/operstate はリンク状態、/proc/net/dev は受信/送信のバイト数・パケット数で、そのプロセスのnet名前空間の分が見えます。',
        '同じIDは共有、違うIDは隔離です。', 'lsnsの2つの記録でNS列を比べます(diff、join、awk)。')


# ------------------------------------------------------------ 17 IPC
def s17(ctx):
    ids = pids(8, 100, 9999)
    shm, sem = [], []
    owners = ['trainee', 'trainee', 'trainee', 'www', 'postgres']
    for i in range(5):
        shm.append((rp(0x1000, 0x7fff), ids[i], owners[i], 600, rp(1, 64) * 4096, rp(0, 1) if i < 3 else 2))
    shm[0] = shm[0][:5] + (0,)
    shm[2] = shm[2][:5] + (0,)
    shm[1] = shm[1][:5] + (3,)
    for i in range(3):
        sem.append((rp(0x1000, 0x7fff), ids[5 + i], ['trainee', 'www', 'trainee'][i], 600, rp(1, 8)))
    put(ctx, 'ipcs.txt', '------ Shared Memory Segments --------\nkey        shmid      owner      perms      bytes      nattch\n' +
        ''.join(f'0x{k:08x} {i:<10} {o:<10} {p:<10} {b:<10} {n}\n' for k, i, o, p, b, n in shm) +
        '\n------ Semaphore Arrays --------\nkey        semid      owner      perms      nsems\n' +
        ''.join(f'0x{k:08x} {i:<10} {o:<10} {p:<10} {n}\n' for k, i, o, p, n in sem) + '\n------ Message Queues --------\nkey        msqid      owner      perms      used-bytes   messages\n')
    orph = sorted(s[1] for s in shm if s[2] == 'trainee' and s[5] == 0)
    sems = sorted(s[1] for s in sem if s[2] == 'trainee')
    size = rp(1, 8) * 4096
    ctx.data.update(orph=orph, sems=sems, size=size)
    finish_exp(ctx, {'orphan_shm': orph, 'trainee_semaphores': sems, 'trainee_shm_bytes': sum(s[4] for s in shm if s[2] == 'trainee')})
    ctx.write('requirements.txt', 'ipcs.txt(ipcs -aの記録)を読み、answer.jsonに orphan_shm(所有者trainee・nattch 0の共有メモリID昇順), trainee_semaphores(traineeのセマフォ配列ID昇順), '
              'trainee_shm_bytes(traineeの共有メモリのbytes合計)を書く。cleanup.shにorphan_shmとtrainee_semaphoresをすべて消すipcrm(共有メモリは-m、セマフォは-s)を1行ずつ書く。'
              f'さらに mk.txt に2行: 1行目は検証用に{size}バイトの共有メモリを作るipcmk(-M)、2行目は共有メモリの一覧を出すlsipc(-m)。実行はしません。')


def c17(ctx):
    need_ro(ctx)
    jcheck(ctx)
    d = ctx.data
    want = {('-m', str(i)) for i in d['orph']} | {('-s', str(i)) for i in d['sems']}
    got = set()
    for t in cmd(ctx, 'cleanup.sh', len(want)):
        need(ctx, t, 'ipcrm')
        for fl, lf in (('-m', '--shmem-id'), ('-s', '--semaphore-id')):
            v = after(t, fl) or after(t, lf)
            if v is not None:
                got.add((fl, v))
    ctx.require(got == want, '対象のIDだけ、種別に合う -m / -s で消します。')
    a, b = cmd(ctx, 'mk.txt', 2)
    need(ctx, a, 'ipcmk')
    ctx.require(after(a, '-M') == str(d['size']) or after(a, '--shmem') == str(d['size']), 'ipcmk -M サイズ の形にします。')
    need(ctx, b, 'lsipc')
    ctx.require(has_flag(b, 'm', 'shmems'), 'lsipc -m で共有メモリを表示します。')


SOL17 = """echo '<<exp>>' > answer.json
for i in <<orph_list>>; do echo "ipcrm -m $i"; done > cleanup.sh
for i in <<sems_list>>; do echo "ipcrm -s $i"; done >> cleanup.sh
printf '%s\\n' "ipcmk -M <<size>>" "lsipc -m" > mk.txt"""
_s17 = s17


def s17w(ctx):
    _s17(ctx)
    ctx.data['orph_list'] = ' '.join(map(str, ctx.data['orph']))
    ctx.data['sems_list'] = ' '.join(map(str, ctx.data['sems']))


mission(17, 'ipcs・lsipc・ipcrm・ipcmkでIPC(共有メモリ・セマフォ・メッセージキュー)を掃除する',
        '異常終了したプロセスが共有メモリやセマフォを残したままです。IPC(共有メモリ/セマフォ/メッセージキュー)の一覧をipcsとlsipcで確認し、アタッチ数が0の孤児を特定してipcrmで消し、テスト用の領域をipcmkで作る手順を書きます。',
        ['answer.jsonに調査結果を書く', 'cleanup.shとmk.txtを書く'], s17w, c17, SOL17,
        ["echo '{}' > answer.json\necho 'ipcrm -a' > cleanup.sh\necho 'ipcmk' > mk.txt", "echo '<<wrong1>>' > answer.json\nfor i in <<orph_list>>; do echo \"ipcrm -s $i\"; done > cleanup.sh\nprintf '%s\\n' 'ipcmk -M <<size>>' 'lsipc -m' > mk.txt"],
        'ipcs -a が全種別の一覧、lsipc はより読みやすい新しい一覧(-m共有メモリ、-s セマフォ、-q メッセージキュー)。ipcrm -m/-s/-q ID(または --shmem-id など)で削除し、nattchが0の共有メモリは使用者がいないので安全に消せます(使用中は削除予約になるだけ)。ipcmk -M サイズ/-S 個数/-Q は検証用の作成です。',
        'nattch(アタッチ数)が0かどうか、所有者がtraineeかどうかを見ます。', '共有メモリは-m、セマフォは-sと、種別でオプションが違います。')
# solution-side lists (orph_list/sems_list) are filled by s17w above


# ------------------------------------------------------------ 18 lslocks
def s18(ctx):
    ps = pids(5)
    path = '/var/lib/app/db-' + secrets.token_hex(2) + '.lock'
    other = '/run/app-' + secrets.token_hex(2) + '.pid'
    holder, w1, w2 = ps[0], ps[1], ps[2]
    rows = [('app-db', holder, 'POSIX', 'WRITE', 0, path), ('app-db', w1, 'POSIX', 'WRITE', 1, path), ('app-db', w2, 'POSIX', 'WRITE', 1, path),
            ('cron', ps[3], 'FLOCK', 'WRITE', 0, other), ('sshd', ps[4], 'FLOCK', 'READ', 0, '/run/utmp.lock')]
    secrets.SystemRandom().shuffle(rows)
    put(ctx, 'lslocks.txt', 'COMMAND PID TYPE MODE M PATH\n' + ''.join(f'{c} {p} {t} {m} {x} {pa}\n' for c, p, t, m, x, pa in rows))
    finish_exp(ctx, {'path': path, 'holder': holder, 'waiters': sorted([w1, w2])})
    ctx.write('requirements.txt', 'lslocks.txt はlslocksの記録です(M列が1=ロック待ちの要求、0=取得済み)。ロック待ちが発生しているファイルpathと、そのロックを取得しているholder(PID)、待っているwaiters(PID昇順)をanswer.jsonに書く。')


mission(18, 'lslocksでロックを握っているプロセスを特定する',
        '更新処理が止まっています。lslocksはカーネルが管理するファイルロックを一覧し(/proc/locks が元データ)、誰が握り誰が待っているかがわかります。待ちが発生しているファイルと保持者を特定します。',
        ['answer.jsonにpath, holder, waitersを書く'], s18, lambda ctx: (need_ro(ctx), jcheck(ctx)), JSON_SOL, JSON_WRONG,
        'lslocks はFLOCK/POSIXロックのCOMMAND・PID・種別・モード・対象パスを表示し、M列が1なら取得待ちです。/proc/locks も同じ情報の生データで、inodeで対象を特定します。保持者を無理にkillせず、まずその処理が何をしているか確認します。',
        '同じパスに対して取得済み(0)と待ち(1)が混在している行を探します。', 'awkでM列が1の行のパスを拾い、同パスのM=0を探します。')


# ------------------------------------------------------------ 19 setarch / setpriv
def s19(ctx):
    uid = rp(2000, 2999)
    gid = rp(2000, 2999)
    ctx.data.update(uid=uid, gid=gid)
    ctx.write('requirements.txt', f'./job.sh を再現性の検証のため plan.txt の2行で起動する(実行はしない)。1行目: setarchでx86_64のpersonalityのままアドレス空間配置のランダム化を無効にして(-R)起動。'
              f'2行目: setprivでUID {uid}・GID {gid}に落とし(--reuid --regid)、補助グループを外し(--clear-groups)、新たな特権の取得を禁止(--no-new-privs)して起動。')


def c19(ctx):
    a, b = cmd(ctx, 'plan.txt', 2)
    d = ctx.data
    need(ctx, a, 'setarch')
    ctx.require(has_flag(a, 'R', 'addr-no-randomize') and a[-1] == './job.sh' and ('x86_64' in a or 'linux64' in a), 'setarch x86_64 -R ./job.sh の形にします。')
    need(ctx, b, 'setpriv')
    ctx.require(after(b, '--reuid') == str(d['uid']) and after(b, '--regid') == str(d['gid']), '--reuid=UID --regid=GID を指定します。')
    ctx.require(has_flag(b, 'clear-groups') and has_flag(b, 'no-new-privs') and b[-1] == './job.sh', '--clear-groups --no-new-privs を付け、最後に ./job.sh を置きます。')


SOL19 = """printf '%s\\n' "setarch x86_64 -R ./job.sh" "setpriv --reuid=<<uid>> --regid=<<gid>> --clear-groups --no-new-privs ./job.sh" > plan.txt"""
mission(19, 'setarchとsetprivで実行環境と権限を絞って起動する',
        'setarchはカーネルから見たアーキテクチャ(personality)やASLR無効化などの実行環境を変えて、setprivはUID/GID・補助グループ・ケイパビリティ・no_new_privsを指定して、子プロセスを起動します。サンドボックス用の起動行を作ります。',
        ['plan.txtに2行のコマンドを書く'], s19, c19, SOL19,
        ['printf \'%s\\n\' "setarch -R ./job.sh" "su <<uid>> -c ./job.sh" > plan.txt',
         'printf \'%s\\n\' "setarch x86_64 -R ./job.sh" "setpriv --reuid=<<uid>> --regid=<<gid>> ./job.sh" > plan.txt'],
        'setarch ARCH -R CMD はASLR(アドレス空間配置のランダム化)を無効化し、デバッグやメモリ配置の再現に使います。setpriv は suid を使わず権限を落として起動でき、--clear-groups、--no-new-privs、--bounding-set、--inh-caps などが使えます。UID変更自体にはroot権限が必要なので、本番ではsystemdのUser=などと使い分けます。',
        'setarchは「アーキ」「オプション」「コマンド」の順、setprivは長い --opt=値 形式です。', 'man setarch setpriv で確かめます。')


# ------------------------------------------------------------ 20 runuser / sulogin
def s20(ctx):
    user = secrets.choice(['backup', 'appsvc', 'dbadmin'])
    ctx.data['user'] = user
    unit = '[Unit]\nDescription=Rescue Shell\nDefaultDependencies=no\n\n[Service]\nType=idle\nExecStart=-/bin/bash\nStandardInput=tty-force\nStandardOutput=inherit\n'
    put(ctx, 'rescue.service.orig', unit)
    ctx.write('rescue.service', unit)
    ctx.write('requirements.txt', f'1) cmd.txt に、rootのcronから{user}として ./backup.sh を実行するrunuserコマンドを1行書く(ログインシェルではなく -u ユーザー、引数の前は --)。'
              '2) rescue.service(レスキュー用ユニット)のExecStartを、rootパスワードを聞いてから単一ユーザーのシェルを出すsulogin(/sbin/sulogin か /usr/sbin/sulogin)に書き換える。他の行は変えない。')


def c20(ctx):
    need_ro(ctx)
    (t,) = cmd(ctx, 'cmd.txt', 1)
    need(ctx, t, 'runuser')
    u = ctx.data['user']
    ctx.require((after(t, '-u') == u or after(t, '--user') == u) and '--' in t and t[-1] == './backup.sh' and t.index('--') < len(t) - 1, 'runuser -u ユーザー -- ./backup.sh の形にします。')
    old = ctx.read('rescue.service.orig').splitlines()
    new = ctx.need_file('rescue.service').splitlines()
    ctx.require(len(old) == len(new), '行数は変えず、ExecStartの行だけを書き換えます。')
    for o, n in zip(old, new):
        if o.startswith('ExecStart'):
            ctx.require(n.startswith('ExecStart=') and os.path.basename(n.split('=', 1)[1].lstrip('-').split()[0]) == 'sulogin' and 'bash' not in n, 'ExecStartをsuloginにします。')
        else:
            ctx.require(o == n, 'ExecStart以外の行は変更しません。')


SOL20 = """echo "runuser -u <<user>> -- ./backup.sh" > cmd.txt
sed -i 's|^ExecStart=.*|ExecStart=-/usr/sbin/sulogin|' rescue.service"""
mission(20, 'runuserとsuloginで権限を渡す・レスキュー環境を守る',
        'runuserはrootがパスワードなしで他ユーザーとしてコマンドを実行する(PAM設定が違うsuの代替)ためのコマンドで、cronやスクリプト向けです。suloginはシングルユーザー/レスキュー起動時にrootパスワードを要求してシェルを出す仕組みで、パスワード無しの素のbashを出す設定は危険です。',
        ['runuserの行をcmd.txtへ', 'rescue.serviceのExecStartをsuloginに'], s20, c20, SOL20,
        ['echo "su - <<user>> -c ./backup.sh" > cmd.txt', "echo \"runuser -u <<user>> -- ./backup.sh\" > cmd.txt\nsed -i 's|^ExecStart=.*|ExecStart=-/bin/sh|' rescue.service"],
        'runuser -u USER -- CMD はrootだけが実行でき、パスワードを聞きません(-lでログインシェル)。sulogin はコンソールでrootパスワードを要求してメンテナンスシェルを開き(--forceでパスワードロックでも入る)、systemdのrescue.service/emergency.serviceのExecStartが使います。素のbashにすると物理アクセスで誰でもrootになれます。',
        'runuserは--で区切ってコマンドを渡します。', 'sedでExecStart行だけを置換します。')


# ------------------------------------------------------------ 21 lastb / faillog / btmp
IPS = ['203.0.113.7', '198.51.100.23', '192.0.2.99', '203.0.113.50']


def s21(ctx):
    users = ['root', 'admin', 'trainee', 'oracle']
    cnts = pids(4, 3, 40)
    secrets.SystemRandom().shuffle(cnts)
    cnt = dict(zip(IPS, cnts))
    rows, per_user = [], {u: 0 for u in users}
    for ip, n in cnt.items():
        for i in range(n):
            u = secrets.choice(users)
            per_user[u] += 1
            rows.append(f'[6] [{rp(1000, 30000):05d}] [ssh:] [{u:<8}] [ssh:notty] [{ip:<15}] [{ip}] [Nov 03 {rp(0, 23):02d}:{rp(0, 59):02d}:{rp(0, 59):02d} 2026]')
    secrets.SystemRandom().shuffle(rows)
    put(ctx, 'btmp.sample', '\n'.join(rows) + '\n')
    fl = {u: (per_user[u], 5 if u != 'trainee' else 0) for u in users}
    put(ctx, 'faillog.txt', 'Login  Failures Maximum\n' + ''.join(f'{u:<7} {f:5d} {m:5d}\n' for u, (f, m) in fl.items()))
    top = max(cnt, key=cnt.get)
    mt = max(per_user, key=per_user.get)
    victim = secrets.choice(users)
    ctx.data['victim'] = victim
    locked = sorted(u for u, (f, m) in fl.items() if m and f >= m)
    exp = {'top_ip': top, 'top_count': cnt[top], 'most_targeted_user': mt, 'locked_users': locked}
    if len(set(per_user.values())) != len(users):
        return s21(ctx)
    finish_exp(ctx, exp)
    ctx.write('requirements.txt', 'btmp.sample は utmpdump /var/log/btmp の出力(失敗ログイン)、faillog.txt は faillog -a の記録です。answer.jsonに top_ip(失敗が最多の接続元), top_count, most_targeted_user(最も狙われたユーザー), '
              f'locked_users(失敗数がMaximum以上のユーザー、Maximum 0は無制限)を書く。さらに cmd.txt に2行: 1行目はローカルのbtmp.sampleを読むlastb(-fでファイル指定)、2行目は{victim}の失敗カウンタを0に戻すfaillog(-uと-r)。実行はしません。')


def c21(ctx):
    need_ro(ctx)
    jcheck(ctx)
    a, b = cmd(ctx, 'cmd.txt', 2)
    need(ctx, a, 'lastb')
    ctx.require(after(a, '-f') == 'btmp.sample' or after(a, '--file') == 'btmp.sample', 'lastb -f btmp.sample の形にします。')
    need(ctx, b, 'faillog')
    ctx.require(after(b, '-u') == ctx.data['victim'] and has_flag(b, 'r', 'reset'), 'faillog -u ユーザー -r の形にします。')


SOL21 = """echo '<<exp>>' > answer.json
printf '%s\\n' "lastb -f btmp.sample" "faillog -u <<victim>> -r" > cmd.txt"""
mission(21, 'lastb・faillog・utmpdumpで/var/log/btmpの失敗ログインを分析する',
        '/var/log/btmpは失敗したログインのバイナリ記録で、utmpdumpで読め、lastbで一覧できます。接続元ごとの回数、狙われたユーザー、faillogのロック状況をまとめ、カウンタ解除の手順まで書きます。',
        ['answer.jsonに分析結果を書く', 'cmd.txtにlastbとfaillog'], s21, c21, SOL21,
        ["echo '{}' > answer.json\nprintf '%s\\n' 'lastb' 'faillog -a' > cmd.txt", "echo '<<wrong1>>' > answer.json\nprintf '%s\\n' 'lastb -f btmp.sample' 'faillog -u <<victim>>' > cmd.txt"],
        'btmpはバイナリなのでcat不可で、utmpdump /var/log/btmp(テキスト化、-r で逆変換)かlastb(-f ファイル、-i でIP)で読みます。faillogは失敗回数とロック上限を扱い、-u ユーザー -r でリセット、-m で上限、-a で全員表示です。権限は通常rootのみで、ログは上書きせず写しで分析します。',
        'IPごと、ユーザーごとに別々に集計します。', 'awkで[ ]の欄を分け、sort | uniq -c で数えます。')


# ------------------------------------------------------------ 22 wtmp / lastlog / messages / secure
def s22(ctx):
    ip_ok = secrets.choice(['203.0.113.9', '198.51.100.7'])
    ip_bad = '192.0.2.' + str(rp(1, 99))
    day = 'Nov  3'
    sec = []
    for i in range(rp(3, 5)):
        sec.append(f'{day} 10:0{i}:1{i} srv sshd[{rp(100, 999)}]: Failed password for root from {ip_ok} port {rp(20000, 60000)} ssh2')
    sec.append(f'{day} 10:09:00 srv sshd[{rp(100, 999)}]: Accepted password for trainee from {ip_ok} port {rp(20000, 60000)} ssh2')
    for i in range(2):
        sec.append(f'{day} 11:0{i}:1{i} srv sshd[{rp(100, 999)}]: Failed password for admin from {ip_bad} port {rp(20000, 60000)} ssh2')
    put(ctx, 'secure.txt', '\n'.join(sec) + '\n')
    victim = secrets.choice(['indexer', 'batch-report', 'rsyncd'])
    pid = rp(3000, 60000)
    put(ctx, 'messages.txt', f'{day} 09:00:01 srv kernel: eth0: link up\n{day} 12:30:55 srv kernel: Out of memory: Killed process {pid} ({victim}) total-vm:812340kB\n{day} 12:31:00 srv systemd[1]: {victim}.service: Main process exited, code=killed\n')
    never = sorted(secrets.SystemRandom().sample(['guest', 'daemon', 'backup', 'www', 'deploy'], rp(2, 3)))
    ll = 'Username         Port     From             Latest\n' + ''.join(f'{u:<16} **Never logged in**\n' for u in never) + 'trainee          pts/0    10.0.0.5         Mon Nov  3 10:09:00 +0900 2026\nroot             tty1                      Sun Nov  2 08:00:00 +0900 2026\n'
    put(ctx, 'lastlog.txt', ll)
    still = sorted(secrets.SystemRandom().sample(['alice', 'bob', 'carol', 'dave'], rp(1, 2)))
    wt = ''.join(f'{u:<8} pts/{i}     10.0.0.{i + 10}  Mon Nov  3 0{i + 8}:00   still logged in\n' for i, u in enumerate(still)) + 'trainee  pts/9     10.0.0.5     Mon Nov  3 10:00 - 10:30  (00:30)\nreboot   system boot  6.8.0        Mon Nov  3 07:55   still running\n'
    put(ctx, 'last.txt', wt)
    finish_exp(ctx, {'never_logged_in': never, 'still_logged_in': still, 'breached_ip': ip_ok, 'oom_killed': victim, 'oom_pid': pid})
    ctx.write('requirements.txt', 'lastlog.txt(lastlogの出力), last.txt(last = /var/log/wtmpの整形), secure.txt(/var/log/secure), messages.txt(/var/log/messages)を読み、answer.jsonに '
              'never_logged_in(一度もログインしていないアカウント昇順), still_logged_in(still logged inのユーザー昇順), breached_ip(失敗が重なったあと同じIPからAcceptedされたIP), oom_killed(OOMで殺されたプロセス名), oom_pid を書く。'
              'さらに dump.txt に、wtmp.txt(utmpdump出力)を逆変換してwtmp.newを作る1行(utmpdump -r、標準入出力のリダイレクトでよい)を書く。')


def c22(ctx):
    need_ro(ctx)
    jcheck(ctx)
    (t,) = cmd(ctx, 'dump.txt', 1)
    need(ctx, t, 'utmpdump')
    ctx.require('-r' in t and 'wtmp.txt' in t and 'wtmp.new' in t, 'utmpdump -r < wtmp.txt > wtmp.new の形にします。')


SOL22 = """echo '<<exp>>' > answer.json
echo "utmpdump -r < wtmp.txt > wtmp.new" > dump.txt"""
mission(22, 'lastlog・wtmp・/var/log/secure・messagesから出来事をたどる',
        '侵入や不審な動きの調査では、ログイン履歴(/var/log/wtmpとlast、lastlog)、認証ログ(/var/log/secure、Debian系ではauth.log)、システムログ(/var/log/messages)を突き合わせます。wtmpはバイナリなのでutmpdumpで読み書きします。',
        ['answer.jsonに調査結果を書く', 'dump.txtにutmpdump -r'], s22, c22, SOL22,
        ["echo '{}' > answer.json\necho 'cat /var/log/wtmp' > dump.txt", "echo '<<wrong1>>' > answer.json\necho 'utmpdump wtmp.txt' > dump.txt"],
        'lastlogは各アカウントの最終ログイン(**Never logged in**は未使用)、lastはwtmpの履歴、/var/log/secureはsshdの成功/失敗(失敗の連続後の成功は総当たりの疑い)、messagesはカーネルのOOM Killerなどです。utmpdumpはバイナリ→テキスト、-rで逆変換です。',
        '失敗が続いたあとにAcceptedが出るIPが怪しい点です。', 'grepで Failed / Accepted を集計し、lastlog.txtから Never を拾います。')


# ------------------------------------------------------------ 23 wall / mesg / pinky
def s23(ctx):
    users = ['alice', 'bob', 'carol', 'dave', 'erin']
    off = sorted(secrets.SystemRandom().sample(range(5), rp(1, 3)))
    rows = []
    for i, u in enumerate(users):
        rows.append(f'{u:<8} {u.title():<8} {"*" if i in off else " "}pts/{i}   {rp(0, 40):2d}   Nov  3 10:{i:02d} 10.0.0.{i + 10}')
    put(ctx, 'pinky.txt', 'Login    Name     TTY      Idle  When       Where\n' + '\n'.join(rows) + '\n')
    secs = rp(5, 60)
    ctx.data['secs'] = secs
    put(ctx, 'notice.txt', 'メンテナンスのため10分後に再起動します。\n')
    finish_exp(ctx, {'mesg_off_ttys': [f'pts/{i}' for i in off], 'writable_users': sorted(users[i] for i in range(5) if i not in off)})
    ctx.write('requirements.txt', 'pinky.txt はpinkyの出力で、TTY欄の先頭の * は mesg n (メッセージ拒否)の端末です。answer.jsonに mesg_off_ttys(拒否のTTY昇順), writable_users(受信できるユーザー昇順)を書く。'
              f'さらに cmd.txt に2行: 1行目は自分の端末へのwrite/wallメッセージを拒否するmesg、2行目は{secs}秒でタイムアウトさせてnotice.txtの内容を全員にブロードキャストするwall(-t)。実行はしません。')


def c23(ctx):
    need_ro(ctx)
    jcheck(ctx)
    a, b = cmd(ctx, 'cmd.txt', 2)
    need(ctx, a, 'mesg')
    ctx.require(a[1:] == ['n'], '拒否は mesg n です(y は許可)。')
    need(ctx, b, 'wall')
    ctx.require(after(b, '-t') == str(ctx.data['secs']) or after(b, '--timeout') == str(ctx.data['secs']), 'wall -t 秒 の形にします。')
    ctx.require(b[-1] == 'notice.txt', '最後にメッセージのファイルを渡します。')


SOL23 = """echo '<<exp>>' > answer.json
printf '%s\\n' "mesg n" "wall -t <<secs>> notice.txt" > cmd.txt"""
mission(23, 'pinky・mesg・wallで利用者に通知する',
        '再起動の前に全ログインユーザーへ告知します。pinkyはfingerの軽量版で端末と*(mesg n)の状態が見え、mesgは自分の端末の受信可否を切り替え、wallは全端末へメッセージを送ります。',
        ['answer.jsonに状態を書く', 'cmd.txtにmesgとwall'], s23, c23, SOL23,
        ["echo '{}' > answer.json\nprintf '%s\\n' 'mesg y' 'wall notice.txt' > cmd.txt", "echo '<<wrong1>>' > answer.json\nprintf '%s\\n' 'mesg n' 'wall -t <<secs>> notice.txt' > cmd.txt"],
        'wall [-t 秒] [ファイル] はmesg yの端末に送り(rootは拒否端末にも届く)、pinkyは利用者・TTY・アイドル・ログイン時刻を一覧します。mesg n で自分は受信しなくなります。write/wall/shutdownの告知はこの経路です。',
        '* が付いた端末はmesg nです。', 'pinky.txtのTTY欄を見て、*の有無で分けます。')


# ------------------------------------------------------------ 24 detect-virt / rtcwake / setterm
def s24(ctx):
    kinds = [('kvm', 'none', 'kvm', 'vm'), ('none', 'docker', 'none', 'container'), ('none', 'none', 'none', 'physical')]
    secrets.SystemRandom().shuffle(kinds)
    exp = {}
    for i, (g, c, v, k) in enumerate(kinds):
        L = 'ABC'[i]
        put(ctx, f'host_{L}.txt', f'$ systemd-detect-virt\n{g if g != "none" else (c if c != "none" else "none")}\n$ systemd-detect-virt --container\n{c}\n$ systemd-detect-virt --vm\n{v}\n')
        exp[L] = k
    secs = rp(2, 12) * 300
    mins = rp(1, 30)
    ctx.data.update(secs=secs, mins=mins)
    finish_exp(ctx, {'hosts': exp})
    ctx.write('requirements.txt', 'host_A/B/C.txt は3台でsystemd-detect-virt(引数なし/--container/--vm)を実行した記録です。answer.jsonに hosts として A/B/C それぞれを '
              'vm(--vmが検出)、container(--containerが検出)、physical(どちらもnone)で分類して書く。'
              f'さらに plan.txt に3行: 1行目は{secs}秒後にRTCアラームを設定するが、サスペンドはしないrtcwake(-m no -s)、2行目は仮想コンソールの画面消去を{mins}分後にするsetterm(--blank)、3行目はコンテナ判定だけをするsystemd-detect-virt(--container)。実行はしません。')


def c24(ctx):
    need_ro(ctx)
    jcheck(ctx)
    a, b, c = cmd(ctx, 'plan.txt', 3)
    d = ctx.data
    need(ctx, a, 'rtcwake')
    ctx.require((after(a, '-m') == 'no' or after(a, '--mode') == 'no') and (after(a, '-s') == str(d['secs']) or after(a, '--seconds') == str(d['secs'])), 'rtcwake -m no -s 秒 の形にします。')
    need(ctx, b, 'setterm')
    ctx.require(after(b, '--blank') == str(d['mins']) or after(b, '-blank') == str(d['mins']), 'setterm --blank 分 の形にします。')
    need(ctx, c, 'systemd-detect-virt')
    ctx.require(has_flag(c, 'c', 'container'), 'systemd-detect-virt --container の形にします。')


SOL24 = """echo '<<exp>>' > answer.json
printf '%s\\n' "rtcwake -m no -s <<secs>>" "setterm --blank <<mins>>" "systemd-detect-virt --container" > plan.txt"""
mission(24, 'systemd-detect-virt・rtcwake・settermでホストの種類と電源・端末を扱う',
        '手元のスクリプトが物理機・VM・コンテナのどこで動いているかを systemd-detect-virt で判定し、電源まわりのrtcwake(RTCアラームで起床)と仮想コンソールのsettermの設定行も用意します。',
        ['answer.jsonに分類を書く', 'plan.txtに3行のコマンド'], s24, c24, SOL24,
        ["echo '{}' > answer.json\nprintf '%s\\n' 'rtcwake -m mem -s <<secs>>' 'setterm -blank' 'systemd-detect-virt' > plan.txt", "echo '<<wrong1>>' > answer.json\nprintf '%s\\n' 'rtcwake -m no -s <<secs>>' 'setterm --blank <<mins>>' 'systemd-detect-virt --vm' > plan.txt"],
        'systemd-detect-virt は仮想化の種類を出し(なければnone)、--vm は仮想マシン、--container はコンテナに限定します。rtcwake -m no -s N はRTCにアラームだけを設定(-m mem/disk/standbyは実際にサスペンド)、setterm --blank N はコンソールの画面消去までの分数、--powersave 等で電源管理を設定します。',
        'どちらもnoneなら物理機(またはWSLなどの別判定)と読みます。', 'フラグ名は --container / --vm / --mode / --seconds / --blank です。')
