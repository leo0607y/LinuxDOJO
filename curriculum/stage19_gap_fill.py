"""Stage 19: 補完・性能計測・ログ・暗号基盤の総点検。サンドボックス内の偽データと、どの環境にもある道具だけを使う。"""
import calendar
import gzip
import hashlib
import secrets
import shlex
import shutil
from pathlib import Path

from engine.runner import register

S = 19
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・サービス・カーネル・ネットワークは変更せず、rootも使いません。"
        "データは訓練用の偽物で、環境にないかもしれないツールは採取済みの出力から診断します。")


def sha(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode()).hexdigest()


def put(ctx, name, text):
    if isinstance(text, bytes):
        ctx.write(name, text, binary=True)
    else:
        ctx.write(name, text)
    ctx.data.setdefault('ro', {})[name] = sha(text)


def need_ro(ctx):
    for name, h in ctx.data.get('ro', {}).items():
        ctx.require(ctx.p(name).exists() and sha(ctx.p(name).read_bytes()) == h, name + ' は原本です。変更しないでください。')


def lines(ctx, name):
    return [x for x in ctx.need_file(name).splitlines() if x.strip()]


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def kv(ctx, name='answer.txt'):
    d = {}
    for ln in ctx.need_file(name).splitlines():
        if '=' in ln:
            k, v = ln.split('=', 1)
            d[k.strip()] = v.strip()
    return d


def check_kv(ctx):
    need_ro(ctx)
    got = kv(ctx)
    for k, v in ctx.data['exp'].items():
        ctx.require(got.get(k) == v, f'answer.txt の {k} が資料の内容と一致しません。')


def hx(n=2):
    return secrets.token_hex(n)


def pick(seq, n):
    seq = list(seq)
    out = []
    while len(out) < n:
        out.append(seq.pop(secrets.randbelow(len(seq))))
    return out


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'19-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='道具ごとの「何を見せる道具か」を意識すると、コマンドを探す時間が減ります。出力は原本を残して読み、結論をファイルに記録しましょう。')


# ---------------------------------------------------------------- 1 whereis / which / type
def s1(ctx):
    tn = 'backup-' + hx()
    ctx.data.update(tn=tn)
    put(ctx, 'type.txt', f"$ type -a {tn}\n{tn} is /usr/local/bin/{tn}\n{tn} is /usr/bin/{tn}\n$ type -a ll\nll is aliased to `ls -l'\n$ type -a cd\ncd is a shell builtin\n")
    put(ctx, 'which.txt', f"$ which {tn}\n/usr/local/bin/{tn}\n$ which ll\n(出力なし。終了コード1)\n")
    put(ctx, 'whereis.txt', f"{tn}: /usr/bin/{tn} /usr/local/bin/{tn} /usr/share/man/man1/{tn}.1.gz\n")
    ctx.data['exp'] = dict(ll='alias', cd='builtin', run=f'/usr/local/bin/{tn}', man=f'/usr/share/man/man1/{tn}.1.gz')
    ctx.write('requirements.txt', f'type.txt / which.txt / whereis.txt は {tn} などを調べた記録です。answer.txt に ll=（alias/builtin/file のどれか）、cd=（同）、run=（{tn} と打ったとき実際に実行されるパス）、man=（マニュアルの場所）を key=value で1行ずつ書く。\n')


SOL1 = r'''{ echo "ll=$(awk '/^ll is aliased/{print "alias"}' type.txt)"; echo "cd=$(awk '/^cd is a shell builtin/{print "builtin"}' type.txt)"; echo "run=$(awk '/^<<tn>> is \//{print $3; exit}' type.txt)"; echo "man=$(grep -o '[^ ]*\.1\.gz' whereis.txt)"; } > answer.txt'''
mission(1, 'whereis・which・typeの違いを使い分ける',
        'whereis、which、type は似ていますが、見ているものが違います。type はシェルが解釈する種類（alias・builtin・ファイル）を、which はPATH上の実行ファイルだけを、whereis はバイナリ・man・ソースの場所を答えます。記録を読み、aliasやbuiltinを which が見落とすことと、同名コマンドの優先順位を確かめてください。',
        ['typeの出力からllとcdの種類を答える', '実際に実行されるパスとmanの場所を答える'], s1, check_kv, SOL1,
        [r'''{ echo "ll=alias"; echo "cd=builtin"; echo "run=/usr/bin/<<tn>>"; echo "man=/usr/share/man/man1/<<tn>>.1.gz"; } > answer.txt''',
         r'''{ echo "ll=file"; echo "cd=builtin"; echo "run=/usr/local/bin/<<tn>>"; echo "man=/usr/share/man/man1/<<tn>>.1.gz"; } > answer.txt'''],
        'type -a は優先順に全候補を出し、先頭が実行されます。whereis の並びは探索順で実行順ではありません。which は alias や builtin を知らないので、llのようなaliasは出力なしになります。コマンドの正体を疑うときはまず type、manの場所は whereis、PATH上の実体は which を使います。',
        'type.txtの最初に出る候補が実行される側です。', 'awkで type.txt の行を条件抽出し、grepでwhereis.txtから.1.gzを取り出します。')


# ---------------------------------------------------------------- 2 csplit / split / zcat / zgrep
def s2(ctx):
    k = 3 + secrets.randbelow(3)
    ctx.data['k'] = k
    out = ''
    for i in range(k):
        out += f'=== host-{hx(2)} ===\n' + ''.join(f'10:0{j} INFO task-{hx(2)} done\n' for j in range(2 + i))
    put(ctx, 'big.log', out)
    put(ctx, 'rotated.log', ''.join(f'row {i + 1} {hx(3)}\n' for i in range(10)))
    rid = 'req-' + hx(3)
    ctx.data['rid'] = rid
    files = []
    for n in range(3):
        files.append([f'2026-11-0{n + 1} INFO ok req-{hx(3)}\n', f'2026-11-0{n + 1} ERROR timeout req-{hx(3)}\n'])
    files[0].append(f'2026-11-01 ERROR db down {rid}\n')
    files[2].append(f'2026-11-03 WARN retry {rid}\n')
    files[1].append('2026-11-02 ERROR disk slow req-' + hx(3) + '\n')
    for n, ls in enumerate(files, 1):
        put(ctx, f'logs/app-{n}.log.gz', gzip.compress(''.join(ls).encode(), mtime=0))
    ctx.data['found'] = [x.rstrip('\n') for ls in files for x in ls if rid in x]
    ctx.data['errors'] = sum('ERROR' in x for ls in files for x in ls)
    ctx.write('requirements.txt', f'big.logを見出し行（=== で始まる）ごとの sec-00.. に分け、rotated.logを4行ずつ chunk-00.. に分ける。logs/*.gz は展開せずに {rid} を含む行をfound.txtへ、ERROR行の総数をcount.txtへ書く。\n')


def c2(ctx):
    need_ro(ctx)
    k = ctx.data['k']
    secs = sorted(ctx.work.glob('sec-*'))
    ctx.require(len(secs) == k, f'見出しごとに{k}個のsec-NNファイルになる必要があります。')
    for f in secs:
        ls = f.read_text().splitlines()
        ctx.require(ls and ls[0].startswith('=== ') and sum(x.startswith('=== ') for x in ls) == 1, f'{f.name} は見出し1つで始まる断片にします。')
    ctx.require(''.join(f.read_text() for f in secs) == ctx.need_file('big.log'), 'sec-* を連結すると元のbig.logに戻る必要があります。')
    ch = sorted(ctx.work.glob('chunk-*'))
    ctx.require(len(ch) == 3 and all(len(f.read_text().splitlines()) <= 4 for f in ch), 'rotated.logは4行以下のchunk-NN 3個に分けます。')
    ctx.require(''.join(f.read_text() for f in ch) == ctx.need_file('rotated.log'), 'chunk-* を連結すると元に戻る必要があります。')
    ctx.require([x.strip() for x in ctx.need_file('found.txt').splitlines()] == ctx.data['found'], 'found.txtには指定IDを含む行だけを、ファイル順に書きます。')
    ctx.require(ctx.need_file('count.txt').strip() == str(ctx.data['errors']), 'count.txtは全gzのERROR行の総数です。')


SOL2 = r'''csplit -z -s -f sec- big.log '/^=== /' '{*}'
split -l 4 -d rotated.log chunk-
zgrep -h '<<rid>>' logs/*.gz > found.txt
zcat logs/*.gz | grep -c ERROR > count.txt'''
mission(2, 'csplitとsplitでログを分割しzcat・zgrepで圧縮ログを検索する',
        '巨大なログを調べます。見出し行で意味のある区切りにしたいときは csplit、行数や容量で機械的に切るなら split が向きます。さらに古いログはgzip圧縮されているので、zcat で流し込むか zgrep で展開せず検索します。',
        ['big.logをcsplitで見出し単位に分割', 'rotated.logをsplitで4行ずつに分割', 'zgrep/zcatでID検索とERROR件数'], s2, c2, SOL2,
        [r'''csplit -f sec- big.log '/^=== /'
split -l 4 -d rotated.log chunk-
zgrep -h '<<rid>>' logs/*.gz > found.txt
zcat logs/*.gz | grep -c ERROR > count.txt''',
         r'''split -l 5 -d big.log sec-
split -l 4 -d rotated.log chunk-
grep -h '<<rid>>' logs/*.gz > found.txt
grep -c ERROR logs/*.gz > count.txt'''],
        'csplit は正規表現や行番号で区切り、{*} で繰り返します（-z で空ファイルを作らない、-s で出力抑制）。split は -l 行数・-b バイト数・-d 数字接尾辞で等分します。zcat は展開して標準出力、zgrep はgrepを展開しながら実行し、複数ファイルでは -h でファイル名を省けます。',
        '見出し位置で切るのはcsplit、固定行数はsplitです。', 'csplitの繰り返し指定 {*}、zgrep -h、zcatをgrep -cへパイプします。')


# ---------------------------------------------------------------- 3 hexdump / od / xxd
def s3(ctx):
    ident = bytes([0x80 + secrets.randbelow(100)]) + secrets.token_bytes(3)
    sec = hx(4)
    put(ctx, 'blob.bin', b'LQ' + ident + sec.encode())
    ctx.data['exp'] = dict(magic='LQ', id=ident.hex(), secret=sec)
    ctx.write('requirements.txt', 'blob.bin は「先頭2バイトのマジック(ASCII)・次の4バイトのID・残りのASCII秘密」の形です。answer.txtに magic= id=（16進8桁の小文字）secret= を書く。hexdump -C か xxd が無くても od で読めます。\n')


SOL3 = r'''{ echo "magic=$(head -c2 blob.bin)"; echo "id=$(od -An -tx1 -j2 -N4 blob.bin | tr -d ' \n')"; echo "secret=$(tail -c +7 blob.bin)"; } > answer.txt'''
mission(3, 'hexdump -C・od・xxdで同じバイト列を読む',
        'バイナリ形式を調べるときは16進ダンプを使います。hexdump -C と xxd は見やすい表示ですが、環境によって無いことがあります。coreutilsの od（-An -tx1 -j -N）ならほぼ必ず使えるので、offsetと長さを指定して同じ情報を取り出してください。',
        ['blob.binのマジック・ID・秘密を取り出す'], s3, check_kv, SOL3,
        [r'''{ echo "magic=LQ"; echo "id=$(od -An -tx1 -N4 blob.bin | tr -d ' \n')"; echo "secret=$(tail -c +7 blob.bin)"; } > answer.txt''',
         r'''{ echo "magic=$(head -c2 blob.bin)"; echo "id=$(head -c6 blob.bin | tail -c4)"; echo "secret=$(tail -c +7 blob.bin)"; } > answer.txt'''],
        'hexdump -C は offset・16進・ASCII列、xxd は同様の表示に加え xxd -r で逆変換もできます。od は -j でoffsetを飛ばし -N で長さを制限し、-An でアドレス列を消し -tx1 で1バイト16進にします。同じバイト列でも、先頭からの位置（0始まり）とtail -c +N（1始まり）の数え方の違いに注意します。',
        '先頭から2バイトはマジック、IDはその次の4バイトです。', 'od -An -tx1 -j 2 -N 4、head -c、tail -c +7 を使います。')


# ---------------------------------------------------------------- 4 cpio
def s4(ctx):
    mode = 'real' if shutil.which('cpio') else 'rec'
    ctx.data['mode'] = mode
    a, b = 'note-' + hx(4), 'port=' + str(1000 + secrets.randbelow(8000))
    put(ctx, 'src/notes.txt', a + '\n')
    put(ctx, 'src/conf/app.ini', b + '\n')
    if mode == 'rec':
        put(ctx, 'listing.txt', 'src/notes.txt\nsrc/conf/app.ini\nsrc/conf\n2 blocks\n')
        ctx.write('requirements.txt', 'cpioが無い環境です。listing.txt は cpio -it < backup.cpio の記録です。収録されているファイルとディレクトリ名（blocks行以外）を辞書順でmembers.txtへ書く。\n')
    else:
        ctx.write('requirements.txt', 'src 以下の通常ファイルを find とパイプで cpio -o にかけて backup.cpio を作り、restore/ に cpio -idm で展開して src と同じ内容に戻す。\n')


def c4(ctx):
    need_ro(ctx)
    if ctx.data['mode'] == 'rec':
        got = [x.strip() for x in ctx.need_file('members.txt').splitlines() if x.strip()]
        ctx.require(got == sorted(['src/notes.txt', 'src/conf/app.ini', 'src/conf']), 'members.txtはblocks行を除く収録名を辞書順で書きます。')
        return
    arc = ctx.p('backup.cpio')
    ctx.require(arc.exists() and arc.read_bytes()[:6] in (b'070701', b'070707'), 'backup.cpioがcpioアーカイブ形式ではありません。')
    for rel in ('src/notes.txt', 'src/conf/app.ini'):
        ctx.require(ctx.p('restore/' + rel).exists() and ctx.p('restore/' + rel).read_bytes() == ctx.p(rel).read_bytes(), f'restore/{rel} が元と一致しません（-d でディレクトリも作ります）。')


SOL4 = r'''if command -v cpio >/dev/null 2>&1; then
  find src -type f | cpio -o -H newc > backup.cpio 2>/dev/null
  mkdir -p restore && (cd restore && cpio -idm < ../backup.cpio 2>/dev/null)
else
  grep -v blocks listing.txt | sort > members.txt
fi'''
mission(4, 'cpioアーカイブを作成して展開する',
        'cpio は tar より古い形式ですが、initramfsやrpmの内部で今も使われます。ファイル名を標準入力から受け取るのが特徴です。find と組み合わせて作成（-o）し、-i で展開、-t で内容確認、-d でディレクトリ作成、-m で更新時刻保持です。cpioが無い環境なら、記録された cpio -it の出力を読んで内容を診断します。',
        ['cpioで作成と展開（無ければ記録から一覧）'], s4, c4, SOL4,
        [r'''tar -cf backup.cpio src; mkdir -p restore; tar -xf backup.cpio -C restore; sort listing.txt > members.txt''',
         r'''find src -type f | cpio -o -H newc > backup.cpio 2>/dev/null; mkdir -p restore; (cd restore && cpio -im < ../backup.cpio 2>/dev/null); sort listing.txt > members.txt'''],
        'cpio -o（copy-out）は標準入力のパス一覧を読んで標準出力へアーカイブを書き、-i（copy-in）は展開、-t は一覧、-p は別ディレクトリへのコピーです。-H newc は新形式でinitramfsが使います。展開先のディレクトリが無いと失敗するので -d を付けます。tarと違い対象は引数でなくパイプで渡します。',
        'tarとは逆に、ファイルのリストは標準入力で渡します。', 'find src -type f | cpio -o、cpio -idm < archive です。')


# ---------------------------------------------------------------- 5 lastlog / last / w
def s5(ctx):
    names = pick(['alice', 'bob', 'carol', 'dave', 'erin', 'frank', 'grace', 'heidi'], 6)
    nev = sorted(names[:2])
    ok = names[2:]
    ips = [f'203.0.113.{10 + secrets.randbelow(200)}' for _ in ok]
    ll = 'Username         Port     From             Latest\n'
    for n in nev:
        ll += f'{n:<16} **Never logged in**\n'
    for n, ip in zip(ok, ips):
        ll += f'{n:<16} pts/0    {ip:<16} Mon Nov 10 09:12:44 +0900 2026\n'
    put(ctx, 'lastlog.txt', ll)
    lt = 'reboot   system boot  6.8.0-45-generic Mon Nov 10 08:00   still running\n'
    for n, ip in zip(ok, ips):
        lt += f'{n:<8} pts/0        {ip:<15} Mon Nov 10 09:12   still logged in\n'
    lt += '\nwtmp begins Mon Nov  3 07:59:00 2026\n'
    put(ctx, 'last.txt', lt)
    ri = secrets.randbelow(len(ok))
    w = ' 09:30:01 up 1:30,  2 users,  load average: 0.10, 0.08, 0.05\nUSER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT\n'
    for i, n in enumerate(ok):
        w += f'{n:<8} pts/{i}    {(ips[i] if i == ri else "-"):<16} 09:12    {i}:00   0.01s  0.01s bash\n'
    put(ctx, 'w.txt', w)
    ctx.data['exp'] = dict(never=','.join(nev), latest=ok[0], remote=f'{ok[ri]}@{ips[ri]}')
    ctx.write('requirements.txt', 'lastlog.txt・last.txt・w.txt は各コマンドの記録です。answer.txtに never=（一度もログインしていないユーザーをカンマ区切りで辞書順）、latest=（rebootを除きlastの先頭のユーザー）、remote=（wで今リモート接続中のユーザー@IP）を書く。\n')


SOL5 = r'''{ echo "never=$(awk '/Never logged in/{print $1}' lastlog.txt | LC_ALL=C sort | paste -sd, -)"; echo "latest=$(awk '$1!="reboot" && NF>2{print $1; exit}' last.txt)"; echo "remote=$(awk 'NR>2 && $3!="-"{print $1"@"$3}' w.txt)"; } > answer.txt'''
mission(5, 'lastlogとlastとwで最終ログインを調べる',
        '不審なアカウントの調査です。lastlog はユーザーごとの最終ログイン（未ログインも分かる）、last は /var/log/wtmp の履歴（再起動も含む）、w は今ログインしている人と何をしているかを示します。3つの記録を読み分けてください。',
        ['未ログインのユーザーを列挙', '最新ログインと現在のリモート接続を特定'], s5, check_kv, SOL5,
        [r'''{ echo "never=$(awk '/Never logged in/{print $1}' lastlog.txt | head -1)"; echo "latest=reboot"; echo "remote=$(awk 'NR>2 && $3!="-"{print $1"@"$3}' w.txt)"; } > answer.txt''',
         r'''{ echo "never=$(awk '/Never logged in/{print $1}' lastlog.txt | LC_ALL=C sort | paste -sd, -)"; echo "latest=$(awk '$1!="reboot" && NF>2{print $1; exit}' last.txt)"; echo "remote=$(awk 'NR>2 && $3!="-"{print $3"@"$1}' w.txt)"; } > answer.txt'''],
        'lastlog は /var/log/lastlog の最終ログイン1件、last は wtmp の全履歴で新しい順（reboot行も混ざる）、lastb は失敗履歴（要root）、w は現在のセッションとFROM/IDLE/WHATです。履歴の調査には last、今の接続の確認には w と使い分けます。',
        'rebootの行や、wのFROMが - のローカル接続を除きます。', 'awkで未ログイン行、reboot以外の先頭行、FROMが - 以外の行を拾います。')


# ---------------------------------------------------------------- 6 sar / vmstat
def s6(ctx):
    io = secrets.randbelow(2) == 0
    pi = 2 + secrets.randbelow(8)
    swap = secrets.randbelow(2) == 0
    sar = 'Linux 6.8.0 (lq-host) \t11/20/2026\n\n10:00:01 CPU %user %nice %system %iowait %steal %idle\n'
    vm = 'procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu----- -----timestamp-----\n r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st                 UTC\n'
    times = []
    for i in range(12):
        t = f'{10 + (i * 10) // 60:02d}:{(i * 10) % 60:02d}:01'
        times.append(t)
        u, wa, sy = 5 + secrets.randbelow(10), 1 + secrets.randbelow(3), 3
        si = 0
        if i == pi:
            if io:
                wa, u = 40 + secrets.randbelow(15), 8 + secrets.randbelow(5)
            else:
                u, wa = 70 + secrets.randbelow(15), 1 + secrets.randbelow(3)
            si = 800 if swap else 0
        idle = 100 - u - sy - wa
        sar += f'{t} all {u:.2f} 0.00 {sy:.2f} {wa:.2f} 0.00 {idle:.2f}\n'
        vm += f' 1  0 {si * 3:6d} 123456  20000 400000 {si:4d} {si:4d}   10   20  300  400 {u:2d} {sy:2d} {idle:2d} {wa:2d}  0 2026-11-20 {t}\n'
        if i == pi:
            peak = t
    sar += 'Average: all 12.00 0.00 3.00 2.00 0.00 83.00\n'
    put(ctx, 'sar.txt', sar)
    put(ctx, 'vmstat.txt', vm)
    ctx.data['exp'] = dict(peak=peak, cause='io' if io else 'cpu', swap='yes' if swap else 'no')
    ctx.write('requirements.txt', 'sar.txt は sar -u の履歴、vmstat.txt は vmstat -t のログです。answer.txtに peak=（CPU使用率が最大の時刻）、cause=（%iowaitが%userより大きければio、そうでなければcpu）、swap=（その時刻のvmstatでsi/soが0でなければyes）を書く。\n')


SOL6 = r'''{ awk '$2=="all" && $1 ~ /^[0-9]/ {u=100-$8; if(u>m){m=u; t=$1; io=$6; us=$3}} END{print "peak=" t; print "cause=" (io+0>us+0 ? "io" : "cpu")}' sar.txt; t=$(awk '$2=="all" && $1 ~ /^[0-9]/ {u=100-$8; if(u>m){m=u; t=$1}} END{print t}' sar.txt); awk -v t="$t" '$19==t {print "swap=" (($7+$8)>0 ? "yes" : "no")}' vmstat.txt; } > answer.txt'''
mission(6, 'sarとvmstatの履歴から性能ピークを特定する',
        '昨日の昼に遅くなったという報告です。sar は過去の履歴を時刻付きで残し、vmstat は短い間隔の実況に向きます。sar -u でピークの時刻と原因（CPUかI/O待ちか）を決め、同じ時刻の vmstat でスワップが起きていたかも確認してください。',
        ['sarからピーク時刻と原因を特定', 'vmstatでswapの有無を確認'], s6, check_kv, SOL6,
        [r'''{ echo "peak=10:00:01"; echo "cause=cpu"; echo "swap=no"; } > answer.txt''',
         r'''{ awk '$2=="all" && $1 ~ /^[0-9]/ {u=100-$8; if(u>m){m=u; t=$1; io=$6; us=$3}} END{print "peak=" t; print "cause=" (io+0<us+0 ? "io" : "cpu")}' sar.txt; echo "swap=no"; } > answer.txt'''],
        'CPU使用率は 100-%idle で読みます。%iowait が高ければCPUでなくディスク待ちが原因で、%user が高ければ計算負荷です。vmstat の si/so（スワップイン/アウト）が出ているとメモリ不足の兆候です。sarは過去の履歴(sa)、vmstat は現在のスナップショットという違いも押さえます。',
        'ピークは%idleが最小の行です。', 'awkで $8 (%idle) の最小行を探し、同時刻をvmstat.txtの時刻列で引きます。')


# ---------------------------------------------------------------- 7 ltrace / strace
def s7(ctx):
    cfg = f'/opt/lic/{hx(3)}.conf'
    sec = 'LQ-' + hx(4)
    put(ctx, 'strace.txt', 'execve("./licensed", ["./licensed"], 0x7ffd) = 0\nopenat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3\n'
        f'openat(AT_FDCWD, "{cfg}", O_RDONLY) = -1 ENOENT (No such file or directory)\nwrite(1, "license check failed\\n", 21) = 21\nexit_group(1) = ?\n')
    put(ctx, 'ltrace.txt', f'getenv("HOME") = "/home/trainee"\nstrcmp("trial-key", "{sec}") = 1\nputs("license check failed") = 21\n')
    ctx.data['exp'] = dict(missing=cfg, secret=sec, systool='strace', libtool='ltrace')
    ctx.write('requirements.txt', 'strace.txt は strace、ltrace.txt は ltrace で同じ偽プログラムを追った記録です。answer.txtに missing=（開けなかったファイル）、secret=（strcmpで比べられている正しい鍵）、systool=（システムコールを見る道具名）、libtool=（ライブラリ関数呼び出しを見る道具名）を書く。\n')


SOL7 = r'''{ echo "missing=$(awk -F'"' '/ENOENT/{print $2}' strace.txt)"; echo "secret=$(awk -F'"' '/^strcmp/{print $4}' ltrace.txt)"; echo "systool=strace"; echo "libtool=ltrace"; } > answer.txt'''
mission(7, 'ltraceとstraceの違いで原因を絞る',
        'ライセンス確認で失敗する偽プログラムがあります。strace はカーネルへのシステムコール（open, read, write）を、ltrace は共有ライブラリの関数呼び出し（strcmp, getenv）を追跡します。どちらで何が見えるのかを記録から確かめ、足りないファイルと比較されている鍵を特定してください。',
        ['stracheから開けないファイルを特定', 'ltraceから比較文字列を特定'], s7, check_kv, SOL7,
        [r'''{ echo "missing=/etc/ld.so.cache"; echo "secret=trial-key"; echo "systool=ltrace"; echo "libtool=strace"; } > answer.txt''',
         r'''{ echo "missing=$(awk -F'"' '/ENOENT/{print $2}' strace.txt)"; echo "secret=$(awk -F'"' '/^strcmp/{print $2}' ltrace.txt)"; echo "systool=strace"; echo "libtool=ltrace"; } > answer.txt'''],
        'strace は ENOENT などのエラーでファイルや権限の問題を見つけるのに向き、ltrace は strcmp の引数などで認証ロジックやライブラリ呼び出しの挙動を見ます。ltraceは静的リンクやセキュリティ設定で使えないことがあり、本番プロセスへのアタッチは性能影響があるので注意します。',
        'ENOENT は「そのファイルが存在しない」を表します。', 'awkの区切り文字を二重引用符にして、必要な引数を取り出します。')


# ---------------------------------------------------------------- 8 perf / bpftrace
def s8(ctx):
    mem = secrets.randbelow(2) == 0
    syms = pick(['inflate_fast', 'memcpy_avx', 'json_parse', 'sha256_block', 'do_syscall_64', 'copy_page'], 4)
    pcts = pick([41.2, 23.5, 12.8, 6.1, 3.3], 4)
    pt = '# Overhead  Shared Object  Symbol\n' + ''.join(f'{p:5.2f}%  {d:<12} [.] {s}\n' for p, d, s in zip(pcts, ['libz.so', 'app', 'libjson.so', 'libcrypto.so'], syms))
    put(ctx, 'perf_top.txt', pt)
    ipc, miss = (f'0.{40 + secrets.randbelow(50)}', '31.2') if mem else (f'2.{secrets.randbelow(9)}1', '1.4')
    put(ctx, 'perf_stat.txt', f" Performance counter stats for 'app':\n\n   12,345,678,901  cycles\n    5,000,000,000  instructions   #    {ipc}  insn per cycle\n          100,000  cache-misses   #   {miss} % of all cache refs\n")
    cm = pick(['nginx', 'cron', 'sshd', 'indexer-' + hx(1)], 4)
    cnt = pick([120, 9876, 45, 3300], 4)
    put(ctx, 'bpftrace.txt', "$ bpftrace -e 'tracepoint:syscalls:sys_enter_openat { @[comm] = count(); }'\nAttaching 1 probe...\n^C\n\n" + ''.join(f'@[{c}]: {n}\n' for c, n in zip(cm, cnt)))
    top = max(zip(cnt, cm))[1]
    ctx.data['exp'] = dict(hot=syms[pcts.index(max(pcts))], bound='memory' if mem else 'cpu', opener=top)
    ctx.write('requirements.txt', 'perf_top.txt は perf top、perf_stat.txt は perf stat、bpftrace.txt はワンライナーの記録です。answer.txtに hot=（最もオーバーヘッドが大きい関数）、bound=（IPCが1未満ならmemory、以上ならcpu）、opener=（openatを最も多く呼んだプロセス名）を書く。\n')


SOL8 = r'''{ echo "hot=$(awk 'NF==4 && $1 ~ /%$/' perf_top.txt | sort -rn | awk 'NR==1{print $4}')"; awk '/insn per cycle/{print ($4<1 ? "bound=memory" : "bound=cpu")}' perf_stat.txt; echo "opener=$(grep '^@\[' bpftrace.txt | sed 's/^@\[\(.*\)\]: \([0-9]*\)$/\2 \1/' | sort -rn | head -1 | cut -d' ' -f2)"; } > answer.txt'''
mission(8, 'perf top・perf stat・bpftraceでボトルネックを特定する',
        '遅いアプリの原因調査です。perf top は今どの関数にCPU時間が使われているか、perf stat は命令数・サイクル・キャッシュミスなどのカウンタ、bpftrace はカーネルのイベントを一行で集計できます。記録を読み、ホットな関数・CPU律速かメモリ律速か・openatを多く呼ぶ犯人を特定してください。',
        ['perf topから最上位の関数', 'perf statからCPU/メモリ律速を判断', 'bpftraceから呼び出し元を特定'], s8, check_kv, SOL8,
        [r'''{ echo "hot=$(awk 'NF==4 && $1 ~ /%$/{print $4; exit}' perf_top.txt)"; echo "bound=cpu"; echo "opener=$(grep '^@\[' bpftrace.txt | head -1)"; } > answer.txt''',
         r'''{ echo "hot=$(awk 'NF==4 && $1 ~ /%$/' perf_top.txt | sort -rn | awk 'NR==1{print $4}')"; awk '/insn per cycle/{print ($4<1 ? "bound=cpu" : "bound=memory")}' perf_stat.txt; echo "opener=$(grep '^@\[' bpftrace.txt | sed 's/^@\[\(.*\)\]: \([0-9]*\)$/\2 \1/' | sort -rn | head -1 | cut -d' ' -f2)"; } > answer.txt'''],
        'IPC（insn per cycle）が低くキャッシュミス率が高ければメモリ待ちが支配的で、IPCが高ければ計算（CPU）律速です。perf top は並び順が保証されないのでOverheadで比較します。bpftraceの @[comm] = count() はプロセス名別の連想配列集計で、-e のワンライナーが読めれば何を数えているか分かります。要root・カーネル設定が必要なので、本番では影響範囲に注意します。',
        'perf top の並び順に頼らず、Overhead列の最大を探します。', 'sort -rn で最大を選び、ipcは$4で読みます。')


# ---------------------------------------------------------------- 9 ifconfig/ip, brctl/bridge, tracepath/traceroute
def s9(ctx):
    d = dict(i='eth' + str(secrets.randbelow(4)), ip=f'192.168.{secrets.randbelow(200)}.{10 + secrets.randbelow(200)}',
             gw=f'192.168.1.{1 + secrets.randbelow(250)}', br='br' + str(secrets.randbelow(3)), port='veth' + hx(1))
    ctx.data.update(d)
    put(ctx, 'legacy.txt', f"ifconfig {d['i']} {d['ip']} netmask 255.255.255.0\nifconfig {d['i']} down\nroute add default gw {d['gw']}\narp -n\nbrctl show\nbrctl addif {d['br']} {d['port']}\n")
    ports = sorted('veth' + hx(2) for _ in range(2 + secrets.randbelow(2)))
    bt = 'bridge name\tbridge id\t\tSTP enabled\tinterfaces\n' + f'{d["br"]}\t\t8000.0a1b2c3d4e5f\tno\t\t{ports[0]}\n' + ''.join(f'\t\t\t\t\t\t{p}\n' for p in ports[1:])
    put(ctx, 'brctl.txt', bt)
    pm = 1280 + 10 * secrets.randbelow(20)
    put(ctx, 'trace.txt', f' 1?: [LOCALHOST]                      pmtu 1500\n 1:  gw                                     0.4ms\n 2:  10.0.0.1                               1.1ms\n 3:  no reply\n     Resume: pmtu {pm} hops 3 back 3\n')
    ctx.data['exp'] = dict(pmtu=str(pm), tool='tracepath', bridge=d['br'], ports=','.join(ports))
    ctx.write('requirements.txt', 'legacy.txt は古いnet-tools/bridge-utilsコマンドです。同じ順にiproute2の等価コマンドをnew.txtへ1行ずつ書く（ifconfigの設定→ip addr add /24 dev、downはip link set、route→ip route、arp→ip neigh、brctl show→bridge link、brctl addif→ip link set master）。さらにtrace.txt（tracepath）とbrctl.txtから answer.txt に pmtu= tool=（root不要でpmtuを出す方）bridge= ports=（カンマ区切り辞書順）を書く。\n')


def c9(ctx):
    need_ro(ctx)
    d = ctx.data
    exp = [['ip', 'addr', 'add', d['ip'] + '/24', 'dev', d['i']], ['ip', 'link', 'set', d['i'], 'down'],
           ['ip', 'route', 'add', 'default', 'via', d['gw']], ['ip', 'neigh'], ['bridge', 'link'],
           ['ip', 'link', 'set', d['port'], 'master', d['br']]]
    got = [toks(ctx, x) for x in lines(ctx, 'new.txt')]
    ctx.require(len(got) == 6, 'new.txtは6行（legacy.txtと同順）です。')
    for i, (g, e) in enumerate(zip(got, exp), 1):
        ctx.require(g == e or (e in (['ip', 'neigh'], ['bridge', 'link']) and g == e + ['show']), f'{i}行目の読み替えが正しくありません。')
    got2 = kv(ctx)
    for k, v in d['exp'].items():
        ctx.require(got2.get(k) == v, f'answer.txt の {k} が一致しません。')


SOL9 = r'''cat > new.txt <<'EOF'
ip addr add <<ip>>/24 dev <<i>>
ip link set <<i>> down
ip route add default via <<gw>>
ip neigh
bridge link
ip link set <<port>> master <<br>>
EOF
{ echo "pmtu=$(awk '/Resume:/{print $3}' trace.txt)"; echo "tool=tracepath"; echo "bridge=$(awk 'NR==2{print $1}' brctl.txt)"; echo "ports=$(awk 'NR==2{print $4; next} NR>2{print $1}' brctl.txt | LC_ALL=C sort | paste -sd, -)"; } > answer.txt'''
mission(9, 'ifconfig・brctlをipとbridgeへ読み替え、tracepathとtraceroute',
        '古い手順書の ifconfig・route・arp・brctl は新しい環境では ip や bridge に置き換えます。対応表を作り、さらにroot不要でMTU経路も分かる tracepath と、プロトコルを選べる traceroute の違いを確認します。',
        ['legacy.txtをiproute2へ読み替え', 'tracepathの結果からpmtuを読む', 'brctl.txtからブリッジとポートを読む'], s9, c9, SOL9,
        [SOL9.replace('ip link set <<port>> master <<br>>', 'brctl addif <<br>> <<port>>'),
         SOL9.replace('tool=tracepath', 'tool=traceroute')],
        'ifconfig→ip addr/ip link、route→ip route、arp→ip neigh、netstat→ss、brctl→bridge/ip link set master と対応します。tracepath はroot不要でpath MTU（pmtu）を発見でき、traceroute はICMP/TCP/UDPを選べますがrawソケットで権限が要ることがあります。ifconfigとbrctlは新しいディストリでは未導入が普通です。',
        '/24は255.255.255.0、デフォルトルートはdefault via です。', 'ip addr add、ip link set、ip route add を使い、brctl.txtは2行目以降を読みます。')


# ---------------------------------------------------------------- 10 firewall-cmd
def s10(ctx):
    extras = pick(['http', 'mysql', 'cockpit', 'samba', 'nfs', 'dhcpv6-client'], 2 + secrets.randbelow(2))
    ports = pick(['8443/tcp', '5432/tcp', '3306/tcp', '9090/tcp'], 1 + secrets.randbelow(2))
    put(ctx, 'fw.txt', f'$ firewall-cmd --list-all --zone=public\npublic (active)\n  target: default\n  interfaces: eth0\n  sources:\n  services: ssh {" ".join(extras)}\n  ports: {" ".join(ports)}\n  protocols:\n  forward: no\n')
    ctx.data['want'] = sorted([f'remove-service={s}' for s in extras] + [f'remove-port={p}' for p in ports] + ['add-service=https'])
    ctx.write('requirements.txt', 'publicゾーンは ssh と https だけを公開する方針です。fw.txtを読み、恒久設定(--permanent)でゾーンpublicに対する firewall-cmd コマンドを fix.sh に1行ずつ（不要なserviceとportの削除、https追加）、最後に --reload を書く。実行はしません。\n')


def c10(ctx):
    need_ro(ctx)
    ls = [toks(ctx, x) for x in lines(ctx, 'fix.sh')]
    ctx.require(ls and ls[-1] == ['firewall-cmd', '--reload'], '最後の行は firewall-cmd --reload にします。')
    ops = []
    for t in ls[:-1]:
        ctx.require(t[0] == 'firewall-cmd' and '--permanent' in t and '--zone=public' in t, '各行は firewall-cmd --permanent --zone=public です。')
        op = [x for x in t[1:] if x.startswith('--') and x not in ('--permanent', '--zone=public')]
        ctx.require(len(op) == 1, '各行の操作は1つだけです。')
        ops.append(op[0][2:])
    ctx.require(sorted(ops) == ctx.data['want'], '削除するサービス・ポートとhttps追加が、fw.txtの状態と方針に一致しません（sshは残します）。')


SOL10 = r'''{ for s in $(awk '/^ *services:/{$1=""; print}' fw.txt); do [ "$s" = ssh ] || echo "firewall-cmd --permanent --zone=public --remove-service=$s"; done; for p in $(awk '/^ *ports:/{$1=""; print}' fw.txt); do echo "firewall-cmd --permanent --zone=public --remove-port=$p"; done; echo "firewall-cmd --permanent --zone=public --add-service=https"; echo "firewall-cmd --reload"; } > fix.sh'''
mission(10, 'firewall-cmdでゾーンとサービスを読み最小公開にする',
        'firewalld は ゾーンにサービスやポートを割り当てて通信を制御します。fw.txt は firewall-cmd --list-all の出力です。--permanent は再起動後も残す設定で、実行中の状態に反映するには --reload が必要です。不要な公開を削り、必要最小限にしてください。',
        ['fw.txtから不要な公開を洗い出す', '--permanent付きの削除とhttps追加、--reloadを書く'], s10, c10, SOL10,
        [r'''echo "firewall-cmd --permanent --zone=public --add-service=https" > fix.sh; echo "firewall-cmd --reload" >> fix.sh''',
         r'''{ for s in $(awk '/^ *services:/{$1=""; print}' fw.txt); do [ "$s" = ssh ] || echo "firewall-cmd --zone=public --remove-service=$s"; done; echo "firewall-cmd --reload"; } > fix.sh'''],
        'firewall-cmd --get-active-zones でゾーン、--list-all で内容を見ます。--add-service/--remove-service はサービス名（定義済みポート群）、--add-port/--remove-port は個別ポートです。--permanent なしの変更は reload や再起動で消え、--permanent だけだと実行中には反映されません。sshを誤って消すと接続不能になるので、必ず残します。',
        'sshは管理用に残します。', 'servicesとportsの行を読み、1つずつ削除コマンドにします。')


# ---------------------------------------------------------------- 11 cal / cron
def s11(ctx):
    y, m = 2026 + secrets.randbelow(2), 1 + secrets.randbelow(12)
    ctx.data['ym'] = f'{y}-{m:02d}'
    put(ctx, 'cal.txt', calendar.TextCalendar(6).formatmonth(y, m))
    weeks = calendar.monthcalendar(y, m)
    lastfri = max(w[calendar.FRIDAY] for w in weeks)
    wd = sum(1 for w in weeks for i in range(5) if w[i])
    ctx.data['exp'] = dict(lastfri=f'{y}-{m:02d}-{lastfri:02d}', workdays=str(wd))
    ctx.write('requirements.txt', f'cal.txt は {y}年{m}月のcalendar出力（日曜始まり）です。answer.txtに lastfri=（最終金曜日 YYYY-MM-DD）workdays=（月〜金の日数）を書く。cron.txtには、毎週火曜と木曜の22:15に /home/trainee/bin/report.sh を実行するcrontab行を1行書く（曜日欄で指定し、日欄は*）。\n')


def c11(ctx):
    need_ro(ctx)
    got = kv(ctx)
    for k, v in ctx.data['exp'].items():
        ctx.require(got.get(k) == v, f'answer.txt の {k} がcal.txtと一致しません。')
    ls = lines(ctx, 'cron.txt')
    ctx.require(len(ls) == 1, 'cron.txtは1行です。')
    f = ls[0].split(None, 5)
    ctx.require(len(f) == 6 and f[5] == '/home/trainee/bin/report.sh', '「分 時 日 月 曜日 コマンド」の形で書きます。')
    ctx.require(f[0] == '15' and f[1] == '22' and f[2] == '*' and f[3] == '*', '22:15、日欄・月欄は * にします。')
    names = {'tue': '2', 'thu': '4', '2': '2', '4': '4'}
    ctx.require(sorted(names.get(x.lower(), '?') for x in f[4].split(',')) == ['2', '4'], '曜日欄は火曜(2)と木曜(4)です（日曜が0）。')


SOL11 = r'''{ echo "lastfri=<<ym>>-$(awk 'NR>2{d=substr($0,16,2)+0; if(d>0)l=d} END{printf "%02d", l}' cal.txt)"; echo "workdays=$(awk 'NR>2{for(i=4;i<=16;i+=3){if(substr($0,i,2)+0>0)n++}} END{print n}' cal.txt)"; } > answer.txt
echo '15 22 * * 2,4 /home/trainee/bin/report.sh' > cron.txt'''
mission(11, 'calでカレンダーを読みcronの曜日指定を書く',
        '月末処理の日程調整です。cal は月のカレンダーを表示し、最終金曜日や営業日数を数えるのに使えます。cron の曜日欄は 0（または7）が日曜で、日欄と同時に指定するとORで動く点にも注意します。',
        ['cal.txtから最終金曜と営業日数を数える', '火曜と木曜のcron行を書く'], s11, c11, SOL11,
        [SOL11.replace('15 22 * * 2,4', '15 22 2,4 * *'), SOL11.replace('15 22 * * 2,4', '22 15 * * 2,4')],
        'cal の列は3文字幅で、日曜始まりなら金曜は6列目です。crontab は「分 時 日 月 曜日」の順で、曜日は0-7（0と7が日曜）か略称（tue,thu）です。日欄と曜日欄の両方を * 以外にするとどちらかに合えば実行されます（OR）。cal が無い環境では date -d や python3 の calendar でも同じ計算ができます。',
        '金曜は左から6列目、cronは分から先に書きます。', 'awkのsubstrで固定幅の列を切り出します。')


# ---------------------------------------------------------------- 12 insmod / modprobe
def s12(ctx):
    h = hx(2)
    t, d1, d2 = f'lqnet_{h}', f'lqcore_{h}', f'lqlib_{h}'
    ctx.data['mod'] = t
    put(ctx, 'modules.dep', f'kernel/drivers/net/{t}.ko: kernel/net/{d1}.ko kernel/lib/{d2}.ko\nkernel/net/{d1}.ko: kernel/lib/{d2}.ko\nkernel/lib/{d2}.ko:\nkernel/fs/xfs_{h}.ko: kernel/lib/{d2}.ko\n')
    ctx.data['order'] = [f'kernel/lib/{d2}.ko', f'kernel/net/{d1}.ko', f'kernel/drivers/net/{t}.ko']
    ctx.write('requirements.txt', f'modules.dep は depmod が作る依存表です（コロンの右は新しい依存が先に並ぶので、右端から読み込む）。insmod は依存を自動解決しないため、{t} を手動で読み込む場合の insmod コマンドを依存先から順に order.txt へ1行ずつ書く。modprobe.txt には依存を自動解決する modprobe コマンドを1行（-n -v の試験実行可）。実行はしません。\n')


def c12(ctx):
    need_ro(ctx)
    got = [toks(ctx, x) for x in lines(ctx, 'order.txt')]
    ctx.require(got == [['insmod', p] for p in ctx.data['order']], 'order.txtは依存先から順に insmod パス を並べます。')
    t = toks(ctx, one(ctx, 'modprobe.txt'))
    ctx.require(t[0] == 'modprobe' and t[-1] == ctx.data['mod'] and set(t[1:-1]) <= {'-n', '-v', '--dry-run', '--verbose'}, 'modprobe [-n -v] モジュール名 の形です（パスや.koは付けない）。')


def one(ctx, name):
    ls = lines(ctx, name)
    ctx.require(len(ls) == 1, name + ' には1行だけを書きます。')
    return ls[0]


SOL12 = r'''awk -F': ' -v t=<<mod>> '$1 ~ "/" t "\\.ko$" {n=split($2,a," "); for(i=n;i>=1;i--) print "insmod " a[i]; print "insmod " $1}' modules.dep > order.txt
echo "modprobe -n -v <<mod>>" > modprobe.txt'''
mission(12, 'insmodとmodprobeの違いと依存解決',
        'カーネルモジュールの読み込みです。insmod は指定した .ko を1つ読み込むだけで依存モジュールは面倒を見ず、modprobe は modules.dep を使って依存を先に読み込みます。modules.dep から必要な順序を読み、手動手順と modprobe の書き方を作ってください。',
        ['依存順のinsmod列をorder.txtへ', 'modprobeの一行をmodprobe.txtへ'], s12, c12, SOL12,
        [r'''echo "insmod kernel/drivers/net/<<mod>>.ko" > order.txt; echo "modprobe <<mod>>" > modprobe.txt''',
         r'''awk -F': ' -v t=<<mod>> '$1 ~ "/" t "\\.ko$" {n=split($2,a," "); for(i=1;i<=n;i++) print "insmod " a[i]; print "insmod " $1}' modules.dep > order.txt; echo "modprobe kernel/drivers/net/<<mod>>.ko" > modprobe.txt'''],
        'insmod は依存未解決だとエラー（Unknown symbol）になり、modprobe は /lib/modules/<ver>/modules.dep と modprobe.d の設定（blacklist, options）を使います。-n で試験実行、-v で詳細表示、-r で依存を考慮して取り外し（rmmodは単体）です。modprobeはモジュール名で指定し、パスや .ko は付けません。この課題では実際にはカーネルへ読み込みません。',
        '依存はコロンの右、右端が最も奥です。', 'awkで右辺を分割して逆順に出力します。')


# ---------------------------------------------------------------- 13 ausearch / capsh / getcap
def s13(ctx):
    comm = 'worker-' + hx(2)
    name = '/var/www/' + hx(3) + '.db'
    perm = secrets.choice(['write', 'read', 'unlink'])
    put(ctx, 'audit.log', 'type=AVC msg=audit(1731234501.100:101): avc:  granted  { read } for  pid=900 comm="cron" name="tab" scontext=system_u:system_r:crond_t:s0 tcontext=system_u:object_r:etc_t:s0 tclass=file\n'
        f'type=AVC msg=audit(1731234567.123:456): avc:  denied  {{ {perm} }} for  pid=1234 comm="{comm}" name="{name}" dev="sda1" scontext=system_u:system_r:httpd_t:s0 tcontext=system_u:object_r:var_t:s0 tclass=file permissive=0\n'
        'type=SYSCALL msg=audit(1731234567.123:456): arch=c000003e syscall=257 success=no exit=-13\n')
    caps = pick(['cap_chown', 'cap_dac_override', 'cap_sys_admin', 'cap_sys_ptrace', 'cap_setuid', 'cap_kill'], 2 + secrets.randbelow(2))
    allc = sorted(caps + ['cap_net_bind_service'])
    put(ctx, 'caps.txt', f'Current: {",".join(allc)}=ep\nBounding set =cap_chown,cap_net_bind_service,cap_sys_admin\nSecurebits: 00/0x0/1\'b0\n')
    put(ctx, 'getcap.txt', '/usr/local/bin/webd cap_net_bind_service=ep\n/usr/bin/ping cap_net_raw=ep\n/usr/local/bin/helper-' + hx(2) + ' cap_sys_admin=ep\n')
    extra = ','.join(sorted(c for c in allc if c != 'cap_net_bind_service'))
    risky = [x for x in ctx.read('getcap.txt').splitlines() if 'cap_sys_admin' in x][0].split()[0]
    ctx.data['exp'] = dict(comm=comm, perm=perm, name=name, tclass='file', extra=extra, risky=risky)
    ctx.data['comm'] = comm
    ctx.write('requirements.txt', 'audit.logはausearchで見る監査ログ、caps.txtは capsh --print、getcap.txtは getcap -r の記録です。cmd.txtに「AVCメッセージをコマンド名で絞るausearch」を1行、answer.txtに comm= perm= name= tclass=（拒否された1件）と、Webサーバに不要なcapability extra=（cap_net_bind_service以外をカンマ区切り辞書順）、risky=（cap_sys_adminを持つファイル）を書く。\n')


def c13(ctx):
    need_ro(ctx)
    t = toks(ctx, one(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'ausearch', 'ausearchで始めます。')
    ctx.require('-m' in t and t[t.index('-m') + 1].lower() == 'avc', '-m AVC でAVCメッセージに絞ります。')
    ctx.require(any(a in t and t[t.index(a) + 1] == ctx.data['comm'] for a in ('-c', '--comm')), '-c でコマンド名に絞ります。')
    got = kv(ctx)
    for k, v in ctx.data['exp'].items():
        ctx.require(got.get(k) == v, f'answer.txt の {k} が一致しません。')


SOL13 = r'''echo "ausearch -m AVC -c <<comm>>" > cmd.txt
{ for k in comm name; do echo "$k=$(grep denied audit.log | grep -o " $k=\"[^\"]*\"" | cut -d'"' -f2)"; done; echo "perm=$(grep denied audit.log | grep -o '{ [a-z_]* }' | tr -d '{} ')"; echo "tclass=$(grep denied audit.log | grep -o 'tclass=[a-z_]*' | cut -d= -f2)"; echo "extra=$(sed -n 's/^Current: \(.*\)=ep$/\1/p' caps.txt | tr ',' '\n' | grep -v '^cap_net_bind_service$' | LC_ALL=C sort | paste -sd, -)"; echo "risky=$(awk '/cap_sys_admin/{print $1}' getcap.txt)"; } > answer.txt'''
mission(13, 'ausearchで拒否理由を探しcapshとgetcapで不要なcapabilityを特定する',
        'セキュリティ監査です。SELinuxの拒否は ausearch -m AVC で audit.log から絞り込めます。さらにプロセスの権限は capsh --print、ファイルに付いた権限は getcap -r で確認し、80番ポートを開くだけのWebサーバに余計な capability が付いていないか見つけます。',
        ['ausearchの絞り込みを書き拒否1件を読む', 'capsh/getcapから不要な権限を特定'], s13, c13, SOL13,
        [r'''echo "ausearch -c <<comm>>" > cmd.txt; echo "comm=cron" > answer.txt''',
         SOL13.replace('/cap_sys_admin/', '/cap_net_raw/')],
        'ausearch は -m でメッセージ種別、-c でコマンド名、-ts で開始時刻、-i で人間向けに表示します。AVCのdeniedは「scontextがtcontextのtclassにpermを行い拒否」と読みます。capsh --print の Current は今のプロセスが持つ権限で、cap_net_bind_service だけが1024未満のポートの束縛に必要です。getcap -r / はファイル能力を再帰的に探し、cap_sys_admin はほぼroot同等なので最優先で外します。',
        'deniedの行は1件、必要な権限は1つだけです。', 'grepとsed/awkで該当行を取り出し、cutで値を切り出します。')


# ---------------------------------------------------------------- 14 tune2fs / hdparm / fio
def s14(ctx):
    dev = '/dev/sd' + secrets.choice('bcd') + '1'
    ctx.data['dev'] = dev
    put(ctx, 'tune2fs.txt', f'$ tune2fs -l {dev}\nFilesystem volume name:   data\nFilesystem state:         clean\nErrors behavior:          Continue\nMount count:              {secrets.randbelow(30)}\nMaximum mount count:      30\nCheck interval:           15552000 (6 months)\n')
    ssd = secrets.choice(['sda', 'sdb'])
    hdd = 'sdb' if ssd == 'sda' else 'sda'
    ctx.data['exp'] = {}
    seqs = {ssd: 250 + secrets.randbelow(100), hdd: 500 + secrets.randbelow(100)}
    for d, rot in ((ssd, 'Solid State Device'), (hdd, '7200')):
        put(ctx, f'hdparm_{d}.txt', f'$ hdparm -I /dev/{d}\n\tModel Number:       DISK-{d}\n\tNominal Media Rotation Rate: {rot}\n$ hdparm -t /dev/{d}\n Timing buffered disk reads: 900 MB in  3.00 seconds = {seqs[d]}.00 MB/sec\n')
    iops = {ssd: 20000 + secrets.randbelow(30000), hdd: 80 + secrets.randbelow(200)}
    for d in (ssd, hdd):
        put(ctx, f'fio_{d}.txt', f'$ fio --name=r --rw=randread --bs=4k\n  read: IOPS={iops[d]}, BW=1000KiB/s (1024kB/s)(60.0MiB/60000msec)\n')
    seq_best = max(seqs, key=seqs.get)
    ctx.data['exp'] = dict(ssd=ssd, randread_best=ssd, seq_best=seq_best)
    ctx.write('requirements.txt', f'tune2fs.txt は tune2fs -l、hdparm_*.txt は hdparm -I/-t、fio_*.txt は fio のランダムリードの記録です。{dev} の設定として、定期的な自動fsck（mount count）を無効にする tune2fs -c と、エラー時に読み取り専用で再マウントする -e remount-ro の2行を tune.txt に書く（実行しない）。answer.txtに ssd=（SSDのデバイス名）randread_best=（IOPSが高い方）seq_best=（シーケンシャル読み込みが速い方）を書く。\n')


def c14(ctx):
    need_ro(ctx)
    dev = ctx.data['dev']
    got = [toks(ctx, x) for x in lines(ctx, 'tune.txt')]
    ctx.require(len(got) == 2 and ['tune2fs', '-e', 'remount-ro', dev] in got, f'tune.txtに tune2fs -e remount-ro {dev} が必要です。')
    ctx.require(['tune2fs', '-c', '0', dev] in got or ['tune2fs', '-c', '-1', dev] in got, 'もう1行は tune2fs -c 0 デバイス です（0か-1で無効化）。')
    a = kv(ctx)
    for k, v in ctx.data['exp'].items():
        ctx.require(a.get(k) == v, f'answer.txt の {k} が一致しません。')


SOL14 = r'''dev=$(awk '/^\$ tune2fs -l/{print $4}' tune2fs.txt)
printf 'tune2fs -c 0 %s\ntune2fs -e remount-ro %s\n' "$dev" "$dev" > tune.txt
ssd=$(grep -l 'Solid State' hdparm_*.txt | sed 's/hdparm_\(.*\)\.txt/\1/')
seq=$(for f in hdparm_*.txt; do echo "$(awk '/MB\/sec/{print $(NF-1)}' $f) $f"; done | sort -rn | head -1 | sed 's/.* hdparm_\(.*\)\.txt/\1/')
rr=$(for f in fio_*.txt; do echo "$(sed -n 's/.*IOPS=\([0-9]*\),.*/\1/p' $f) $f"; done | sort -rn | head -1 | sed 's/.* fio_\(.*\)\.txt/\1/')
{ echo "ssd=$ssd"; echo "randread_best=$rr"; echo "seq_best=$seq"; } > answer.txt'''
mission(14, 'tune2fsとhdparm・fioの結果からI/O性能と設定を判断する',
        'ストレージの診断です。tune2fs -l でext4の設定（最大マウント回数 -c、エラー時の動作 -e）を読み、hdparm -I で機器情報、hdparm -t でシーケンシャル速度、fio でランダムI/Oの性能を確認します。連続読みが速くてもランダム性能は別物な点を確かめてください。',
        ['tune2fsの設定変更コマンドを書く', 'hdparm/fioからSSDと速い方を判断'], s14, c14, SOL14,
        [r'''printf 'tune2fs -c 30 <<dev>>\ntune2fs -e continue <<dev>>\n' > tune.txt''',
         SOL14.replace('randread_best=$rr', 'randread_best=$seq')],
        'tune2fs -c は最大マウント回数（0または-1で無効）、-e はエラー時の挙動（continue / remount-ro / panic）、-l は現在値の表示です。hdparm -I は機器の仕様（回転数が Solid State Device ならSSD）、-t はバッファ読み出しの連続速度です。fio はブロックサイズやrandread/seqなどを指定した実際の負荷試験で、IOPSと帯域・レイテンシから用途に合うかを判断します。この課題ではデバイスに触れません。',
        'IOPSの桁と連続読み出し速度は別の指標です。', 'sort -rn で最大値を選び、ファイル名からデバイス名を取り出します。')


# ---------------------------------------------------------------- 15 chronyd
def s15(ctx):
    sel, other, bad = 'ntp-' + hx(2), 'ntp-' + hx(2), 'ntp-' + hx(2)
    st = 2 + secrets.randbelow(3)
    direction = secrets.choice(['fast', 'slow'])
    put(ctx, 'tracking.txt', f'Reference ID    : C0A80101 ({sel})\nStratum         : {st}\nSystem time     : 0.000345678 seconds {direction} of NTP time\nLeap status     : Normal\n')
    put(ctx, 'sources.txt', 'MS Name/IP address         Stratum Poll Reach LastRx Last sample\n' + '=' * 79 + '\n'
        f'^+ {other}   2   6   377    23   +45us[ +60us] +/- 12ms\n^? {bad}   0  10     0     -     +0ns[   +0ns] +/-    0ns\n^* {sel}   {st - 1}   6   377    21   -12us[ -20us] +/- 9ms\n')
    ctx.data['exp'] = dict(selected=sel, stratum=str(st), direction=direction, unreachable=bad)
    ctx.write('requirements.txt', 'tracking.txt は chronyc tracking、sources.txt は chronyc sources の記録です。answer.txtに selected=（同期元に選ばれたサーバ=^*）stratum=（自分のstratum）direction=（System timeが進んでいればfast、遅れていればslow）unreachable=（Reachが0のサーバ）を書く。\n')


SOL15 = r'''{ echo "selected=$(awk '$1=="^*"{print $2}' sources.txt)"; echo "stratum=$(awk '/^Stratum/{print $3}' tracking.txt)"; echo "direction=$(awk '/^System time/{print $6}' tracking.txt)"; echo "unreachable=$(awk '$1 ~ /^\^/ && $5==0{print $2}' sources.txt)"; } > answer.txt'''
mission(15, 'chronydのchronyc tracking・sources出力を読む',
        '時刻ずれの調査です。chronyd の状態は chronyc tracking（自分の同期状態とずれ）と chronyc sources（各サーバの状態）で読みます。sources の ^* は現在の同期元、^+ は候補、^? は到達できないか未評価の状態です。Reach は直近8回の応答履歴（377は全て成功）です。',
        ['選択中の同期元とstratumを読む', 'ずれの向きと到達不能サーバを特定'], s15, check_kv, SOL15,
        [r'''{ echo "selected=$(awk '$1=="^+"{print $2}' sources.txt)"; echo "stratum=$(awk '/^Stratum/{print $3}' tracking.txt)"; echo "direction=fast"; echo "unreachable=$(awk '$1=="^*"{print $2}' sources.txt)"; } > answer.txt''',
         r'''{ echo "selected=$(awk '$1=="^*"{print $2}' sources.txt)"; echo "stratum=$(awk '$1=="^*"{print $3}' sources.txt)"; echo "direction=$(awk '/^System time/{print $6}' tracking.txt)"; echo "unreachable=$(awk '$1 ~ /^\^/ && $5==0{print $2}' sources.txt)"; } > answer.txt'''],
        'chronyc tracking の System time は「NTP時刻に対してfast（進んでいる）/slow（遅れている）」で、Last offset や RMS offset と合わせてずれの大きさを見ます。stratum は基準時計までの段数（自分は同期元より1大きい）。chronyc sources -v で列の凡例が出ます。Reachが0のサーバはネットワークやFWを疑います。',
        'sourcesの1列目の記号が状態を表します。', 'awkの1列目で ^* を、Reach列で0を判定します。')


# ---------------------------------------------------------------- 16 smbclient / smb.conf (testparm相当)
def s16(ctx):
    bad = 'pub-' + hx(2)
    ok1, ok2, hid = 'docs-' + hx(2), 'priv-' + hx(2), 'hr-' + hx(2)
    conf = '[global]\n   workgroup = LQ\n   security = user\n\n'
    for n, guest, ro, br in ((ok1, 'yes', 'yes', 'yes'), (bad, 'yes', 'no', 'yes'), (ok2, 'no', 'no', 'yes'), (hid, 'no', 'no', 'no')):
        conf += f'[{n}]\n   path = /srv/{n}\n   guest ok = {guest}\n   read only = {ro}\n   browseable = {br}\n\n'
    put(ctx, 'smb.conf', conf)
    shares = sorted([ok1, bad, ok2])
    sc = '\tSharename       Type      Comment\n\t---------       ----      -------\n' + ''.join(f'\t{n:<15} Disk      files\n' for n in shares) + '\tIPC$            IPC       IPC Service\n'
    put(ctx, 'smbclient.txt', '$ smbclient -L //fileserver -N\n' + sc)
    ctx.data.update(bad=bad)
    ctx.data['exp'] = dict(guest_writable=bad, shares=','.join(shares))
    ctx.write('requirements.txt', 'smbclient.txt は smbclient -L の記録、smb.conf は設定です。testparm でやるような設定チェックを手で行い、answer.txtに guest_writable=（ゲスト可かつ書き込み可の共有）shares=（smbclientに見えるDisk共有をカンマ区切り辞書順、IPC$除く）を書き、smb.conf を直接変更せず smb.conf.fixed にその共有の guest ok を no にしたコピーを作る。\n')


def c16(ctx):
    need_ro(ctx)
    got = kv(ctx)
    for k, v in ctx.data['exp'].items():
        ctx.require(got.get(k) == v, f'answer.txt の {k} が一致しません。')
    want = ctx.need_file('smb.conf').replace('guest ok = yes\n   read only = no', 'guest ok = no\n   read only = no').splitlines()
    cur, bad = None, ctx.data['bad']
    exp = []
    for ln in ctx.need_file('smb.conf').splitlines():
        if ln.startswith('['):
            cur = ln.strip('[]')
        exp.append(ln.replace('yes', 'no') if cur == bad and 'guest ok' in ln else ln)
    ctx.require([x.rstrip() for x in ctx.need_file('smb.conf.fixed').splitlines()] == exp, 'smb.conf.fixedは対象共有のguest ok行だけをnoにし、他は変えません。')
    del want


SOL16 = r'''{ echo "guest_writable=$(awk '/^\[/{s=substr($0,2,length($0)-2)} /guest ok = yes/{g[s]=1} /read only = no/{w[s]=1} END{for(s in g) if(w[s]) print s}' smb.conf)"; echo "shares=$(awk '$2=="Disk"{print $1}' smbclient.txt | LC_ALL=C sort | paste -sd, -)"; } > answer.txt
awk '/^\[/{s=substr($0,2,length($0)-2)} s=="<<bad>>" && /guest ok = yes/{sub(/yes/,"no")} {print}' smb.conf > smb.conf.fixed'''
mission(16, 'smbclientの共有一覧とsmb.confをtestparm相当で点検する',
        'Sambaサーバの点検です。smbclient -L は公開されている共有を一覧し、testparm は smb.conf の構文と有効な設定を検証します。ここでは testparm が使えない想定で、設定を読んで危険な共有（ゲスト可かつ書き込み可）を見つけ、browseable = no の共有がsmbclientに出ない理由も確かめます。',
        ['smbclientに見える共有を列挙', '危険な共有を特定しsmb.conf.fixedで修正'], s16, c16, SOL16,
        [r'''{ echo "guest_writable=<<bad>>"; echo "shares=$(awk '$2=="Disk"{print $1}' smbclient.txt | LC_ALL=C sort | paste -sd, -)"; } > answer.txt; sed 's/guest ok = yes/guest ok = no/' smb.conf > smb.conf.fixed''',
         r'''{ echo "guest_writable=<<bad>>"; echo "shares=$(awk '$2=="Disk"{print $1}' smbclient.txt | LC_ALL=C sort | paste -sd, -),hidden"; } > answer.txt; cp smb.conf smb.conf.fixed'''],
        'smbclient -L //host -N は匿名で共有一覧を取得し、IPC$ は管理用の特殊共有です。browseable = no の共有は一覧に出ませんが存在します。testparm は smb.conf の構文エラーや非推奨パラメータを報告し、-s で有効設定だけを出力します。guest ok = yes と read only = no の組み合わせは、認証なしで書き込める危険な設定です。',
        '一覧に無い共有は browseable = no かもしれません。', 'awkで [共有名] を覚えながら、ゲスト可と書き込み可の両方がある共有を探します。')
