"""Stage 29: ネットワーク低レベル・パッケージ・マニュアル・SSH補助・FHS・時刻の総ざらい。サンドボックス内の偽データだけを使う。"""
import hashlib
import ipaddress
import json
import re
import secrets
import shlex
from pathlib import Path

from engine.runner import register

S = 29
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・ネットワーク・パッケージは変更せず、rootも使いません。"
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


def rj(ctx, name='answer.json'):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def jcheck(ctx, spec):
    v = rj(ctx)
    for k, dk in spec.items():
        ctx.require(k in v, f'answer.json に "{k}" がありません。')
        ctx.require(str(v[k]).strip() == str(ctx.data[dk]), f'"{k}" の値が記録と合いません。')


def jsol(**kv):
    return "echo '{" + ",".join(f'"{k}":"<<{v}>>"' for k, v in kv.items()) + "}' > answer.json"


def cl(ctx, name):
    ls = [x.strip() for x in ctx.need_file(name).splitlines() if x.strip() and not x.strip().startswith('#')]
    ctx.require(ls, name + ' が空です。')
    return ls


def one_line(ctx, name):
    ls = cl(ctx, name)
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0]


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def tk1(ctx, name):
    return toks(ctx, one_line(ctx, name))


def opt(t, *flags):
    for i, x in enumerate(t):
        for f in flags:
            if x == f and i + 1 < len(t):
                return t[i + 1]
            if f.startswith('--') and x.startswith(f + '='):
                return x.split('=', 1)[1]
    return None


def first(ctx, lines, cmd):
    r = [toks(ctx, x) for x in lines if toks(ctx, x) and toks(ctx, x)[0] == cmd]
    ctx.require(len(r) == 1, f'{cmd} の行がちょうど1つ必要です。')
    return r[0]


def rip():
    return f'10.{1 + secrets.randbelow(200)}.{secrets.randbelow(250)}.{1 + secrets.randbelow(250)}'


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'29-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='実行する前に対象を確認し、結果を観測で検証します。本番では影響範囲の小さい指定と元データの保全を優先しましょう。')


# ---------------------------------------------------------------- 1
def s1(ctx):
    d = ctx.data
    d.update(ip=rip(), ip2=rip(), p=str(8000 + secrets.randbelow(900)))
    ctx.write('requirements.txt', f'fw.sh に1行ずつ3本のコマンドを書く（実行はしない）。\n'
              f'1) arptables: INPUTで送信元 {d["ip"]} のARPを破棄\n'
              f'2) ebtables: FORWARDでIPv4の宛先 {d["ip2"]} (--ip-dst) を破棄\n'
              f'3) ip6tables: INPUTでIPv6のtcp {d["p"]}番(--dport)を許可\n')


def c1(ctx):
    ls = cl(ctx, 'fw.sh')
    ctx.require(len(ls) == 3, '3行ちょうど書きます。')
    d = ctx.data
    a, e, g = first(ctx, ls, 'arptables'), first(ctx, ls, 'ebtables'), first(ctx, ls, 'ip6tables')
    ctx.require(opt(a, '-A') == 'INPUT' and opt(a, '-s') == d['ip'] and opt(a, '-j') == 'DROP', 'arptablesの指定が違います。')
    ctx.require(opt(e, '-A') == 'FORWARD' and opt(e, '-p') == 'IPv4' and opt(e, '--ip-dst') == d['ip2'] and opt(e, '-j') == 'DROP', 'ebtablesの指定が違います。')
    ctx.require(opt(g, '-A') == 'INPUT' and opt(g, '-p') == 'tcp' and opt(g, '--dport') == d['p'] and opt(g, '-j') == 'ACCEPT', 'ip6tablesの指定が違います。')


mission(1, 'arptables・ebtables・ip6tablesを使い分ける',
        'パケットフィルタは層ごとに道具が違います。ARPはarptables、ブリッジ(L2)はebtables、IPv6はip6tablesが担当し、iptablesはIPv4専用です。requirements.txtの条件を読み、3つのコマンドをfw.shへ書いてください。',
        ['3つのツールを1行ずつfw.shへ', '各ツールのチェーンと条件を指定どおりに'], s1, c1,
        "printf '%s\\n' 'arptables -A INPUT -s <<ip>> -j DROP' 'ebtables -A FORWARD -p IPv4 --ip-dst <<ip2>> -j DROP' 'ip6tables -A INPUT -p tcp --dport <<p>> -j ACCEPT' > fw.sh",
        ["printf '%s\\n' 'iptables -A INPUT -s <<ip>> -j DROP' 'iptables -A FORWARD -d <<ip2>> -j DROP' 'iptables -A INPUT -p tcp --dport <<p>> -j ACCEPT' > fw.sh",
         "printf '%s\\n' 'arptables -A INPUT -s <<ip2>> -j DROP' 'ebtables -A FORWARD -p IPv4 --ip-dst <<ip>> -j DROP' 'ip6tables -A INPUT -p tcp --dport <<p>> -j ACCEPT' > fw.sh"],
        'arptablesはARP、ebtablesはEthernetブリッジのフレーム、ip6tablesはIPv6を扱います。いずれもテーブル/チェーン/-jターゲットの書式はiptablesと似ています。この課題では実行せず、規則の書式だけを組み立てます。',
        '三者の担当層を思い出します。', '-A チェーン -s/--ip-dst/--dport -j ターゲット の形で書きます。')


# ---------------------------------------------------------------- 2
def s2(ctx):
    d = ctx.data
    d['be'] = secrets.choice(['nft', 'legacy'])
    d['old'] = str(2000 + secrets.randbelow(900))
    d['new'] = str(3000 + secrets.randbelow(900))
    lines = ['*filter', ':INPUT DROP [0:0]', ':FORWARD DROP [0:0]', ':OUTPUT ACCEPT [0:0]', '-A INPUT -i lo -j ACCEPT',
             '-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT', f'-A INPUT -p tcp -m tcp --dport {d["old"]} -j ACCEPT', 'COMMIT']
    d['orig'] = lines
    ctx.write('rules.v4', '\n'.join(lines) + '\n')
    tag = '(nf_tables)' if d['be'] == 'nft' else '(legacy)'
    put(ctx, 'version.txt', f'$ iptables --version\niptables v1.8.9 {tag}\n$ update-alternatives --display iptables  # 実体は iptables-nft か iptables-legacy\n')
    ctx.write('requirements.txt', f'sshdの待受を {d["old"]} から {d["new"]} へ移した。rules.v4（iptables-save形式）の該当ルールを直す。\n'
              'answer.json に {"backend":"nft"か"legacy"} (version.txtで判断)、save.txt に現在規則を保存する(iptables-save系)1行、test.txt に rules.v4 を適用せず構文だけ検査する(iptables-restore系, --test)1行を書く。バックエンドに合う-nft-/-legacy-付きの実体名を使うこと。\n')


def c2(ctx):
    need_ro(ctx)
    d = ctx.data
    exp = [x.replace(d['old'], d['new']) for x in d['orig']]
    ctx.require(ctx.need_file('rules.v4').splitlines() == exp, 'rules.v4はsshの--dportだけを新しい番号へ直し、他は変えません。')
    v = rj(ctx)
    ctx.require(v.get('backend') == d['be'], 'backendが違います。version.txtの(nf_tables)/(legacy)を見ます。')
    s = tk1(ctx, 'save.txt')
    ctx.require(s[0] == f'iptables-{d["be"]}-save', f'save.txtは iptables-{d["be"]}-save です。')
    t = tk1(ctx, 'test.txt')
    ctx.require(t[0] == f'iptables-{d["be"]}-restore' and ('--test' in t or '-t' in t) and 'rules.v4' in t, 'test.txtは該当のrestoreに --test と rules.v4 を指定します。')


mission(2, 'iptables-legacy・iptables-nft・save・restoreを確かめる',
        'iptablesの実体は iptables-legacy(xtables) と iptables-nft(nf_tables互換) の2系統で、どちらが使われるかは update-alternatives で決まります。規則の保存は iptables-save、復元は iptables-restore です。version.txtから系統を判断し、rules.v4を直して保存・検査コマンドを用意してください。',
        ['rules.v4のポートを修正', 'backendを判定してanswer.jsonへ', 'save.txt/test.txtを正しい実体名で'], s2, c2,
        "sed -i 's/--dport <<old>>/--dport <<new>>/' rules.v4\necho '{\"backend\":\"<<be>>\"}' > answer.json\necho 'iptables-<<be>>-save' > save.txt\necho 'iptables-<<be>>-restore --test < rules.v4' > test.txt",
        ["sed -i 's/<<old>>/<<new>>/' rules.v4\necho '{\"backend\":\"nft\"}' > answer.json\necho 'iptables-save' > save.txt\necho 'iptables-restore < rules.v4' > test.txt",
         "echo '{\"backend\":\"<<be>>\"}' > answer.json\necho 'iptables-<<be>>-save' > save.txt\necho 'iptables-<<be>>-restore -t rules.v4' > test.txt"],
        'iptables-save/iptables-restoreは規則をテキストで一括出し入れします。restoreの--test(-t)は適用せず構文だけ検査します。-nft-と-legacy-は別の規則集合を持ち、混在させると規則が見えなくなる事故が起きます。',
        '--versionの括弧の中が系統です。', 'sedで置換し、系統名入りのコマンド名を作ります。')


# ---------------------------------------------------------------- 3
def s3(ctx):
    d = ctx.data
    d.update(net=f'10.{1 + secrets.randbelow(200)}.{secrets.randbelow(250)}.0', p=str(9000 + secrets.randbelow(900)), t=str(20 + secrets.randbelow(60)))
    ids = [secrets.token_hex(4) for _ in range(4)]
    tgt = 1 + secrets.randbelow(3)
    d['tid'] = ids[tgt]
    out = ''
    for i, x in enumerate(ids):
        port = d['p'] if i == tgt else secrets.choice(['22', '80', '443', '5432'])
        out += f' PACKET: 2 {x} IN=eth0 SRC=203.0.113.{10 + i} DST=192.0.2.1 LEN=60 TCP SPORT={40000 + i} DPORT={port}\n'
        if i == tgt:
            out += f'  TRACE: 2 {x} filter:INPUT:policy:DROP\n'
        else:
            out += f'  TRACE: 2 {x} filter:INPUT:rule:{2 + i}\n  TRACE: 2 {x} filter:INPUT:rule:{2 + i}:ACCEPT\n'
    put(ctx, 'trace.txt', '$ xtables-monitor --trace\n' + out)
    put(ctx, 'rules.v6', '*filter\n:INPUT DROP [0:0]\n-A INPUT -p tcp -m tcp --dport 22 -j ACCEPT\nCOMMIT\n')
    put(ctx, 'rules.v4', '*filter\n:INPUT DROP [0:0]\n-A INPUT -p tcp -m tcp --dport 22 -j ACCEPT\nCOMMIT\n')
    ctx.write('requirements.txt', f'移行準備。\ntranslate.txt: iptables-translate でINPUTの「送信元 {d["net"]}/24, tcp, --dport {d["p"]}, ACCEPT」を変換するコマンド1行\n'
              'nft.txt: その変換結果としてnftに渡す1行（例: nft \'add rule ip filter INPUT udp dport 53 counter accept\' の形式）\n'
              'v6.txt: rules.v6 を ip6tables-restore-translate で変換するコマンド1行 (-f)\n'
              f'apply.txt: rules.v4 を iptables-apply で適用し、{d["t"]}秒以内に確認できなければ自動で戻すコマンド1行\n'
              'monitor.txt: xtables-monitor でトレースを見るコマンド1行\n'
              'answer.json: trace.txtでポリシーによりDROPされたパケットの {"trace_id":"..."}\n')


def c3(ctx):
    need_ro(ctx)
    d = ctx.data
    t = tk1(ctx, 'translate.txt')
    ctx.require(t[0] == 'iptables-translate' and opt(t, '-A') == 'INPUT' and opt(t, '-p') == 'tcp' and opt(t, '-s') == d['net'] + '/24'
                and opt(t, '--dport') == d['p'] and opt(t, '-j') == 'ACCEPT', 'translate.txtの条件が違います。')
    n = one_line(ctx, 'nft.txt').lower()
    ctx.require(n.startswith('nft ') and f'ip saddr {d["net"]}/24' in n and f'tcp dport {d["p"]}' in n and 'accept' in n, 'nft.txtは nft \'add rule ip filter INPUT ip saddr ... tcp dport ... counter accept\' の形です。')
    v = tk1(ctx, 'v6.txt')
    ctx.require(v[0] == 'ip6tables-restore-translate' and 'rules.v6' in v, 'ip6tables-restore-translate -f rules.v6 の形です。')
    a = tk1(ctx, 'apply.txt')
    ctx.require(a[0] == 'iptables-apply' and opt(a, '-t', '--timeout') == d['t'] and 'rules.v4' in a, 'iptables-apply -t 秒 rules.v4 の形です。')
    m = tk1(ctx, 'monitor.txt')
    ctx.require(m[0] == 'xtables-monitor' and ('--trace' in m or '-t' in m), 'xtables-monitor --trace です。')
    jcheck(ctx, {'trace_id': 'tid'})


mission(3, 'iptables-translate・restore-translate・iptables-apply・xtables-monitor',
        'iptablesからnftablesへ移行する準備をします。iptables-translate は1規則を、ip6tables-restore-translate は保存形式を丸ごとnft構文に変換します。変更の適用は iptables-apply で時間切れ自動ロールバックを付け、xtables-monitor --trace で規則の通過を観察します。requirements.txtのとおりに5つの1行と、トレースの診断を提出してください。',
        ['変換・適用・監視コマンドを書く', 'トレースからDROPされたパケットを特定'], s3, c3,
        "echo 'iptables-translate -A INPUT -p tcp -s <<net>>/24 --dport <<p>> -j ACCEPT' > translate.txt\n"
        "echo \"nft 'add rule ip filter INPUT ip saddr <<net>>/24 tcp dport <<p>> counter accept'\" > nft.txt\n"
        "echo 'ip6tables-restore-translate -f rules.v6' > v6.txt\necho 'iptables-apply -t <<t>> rules.v4' > apply.txt\necho 'xtables-monitor --trace' > monitor.txt\n"
        "id=$(grep 'policy:DROP' trace.txt | awk '{print $3}')\necho \"{\\\"trace_id\\\":\\\"$id\\\"}\" > answer.json",
        ["echo 'iptables-translate -A INPUT -p tcp --dport <<p>> -j ACCEPT' > translate.txt\necho \"nft 'add rule ip filter INPUT tcp dport <<p>> accept'\" > nft.txt\necho 'ip6tables-restore-translate rules.v6' > v6.txt\necho 'iptables-apply rules.v4' > apply.txt\necho 'xtables-monitor' > monitor.txt\necho '{}' > answer.json",
         "echo 'iptables-translate -A INPUT -p tcp -s <<net>>/24 --dport <<p>> -j ACCEPT' > translate.txt\necho \"nft 'add rule ip filter INPUT ip saddr <<net>>/24 tcp dport <<p>> counter accept'\" > nft.txt\necho 'ip6tables-restore-translate -f rules.v6' > v6.txt\necho 'iptables-apply -t <<t>> rules.v4' > apply.txt\necho 'xtables-monitor --trace' > monitor.txt\necho '{\"trace_id\":\"deadbeef\"}' > answer.json"],
        'translate系は移行補助で、出力を人が確認してからnftへ流します。iptables-applyは規則適用後にタイムアウト内の確認入力がなければ元の規則へ戻すため、リモート作業の閉め出し事故を防ぎます。xtables-monitor --traceはTRACEターゲットの結果をnetlinkで受け取り、policy:DROPなら全規則に合わず既定で落ちたことを示します。',
        'translate は1規則、restore-translate は全体、apply は安全網、monitor は観察です。', 'grepでpolicy:DROPの行を探し、3列目のIDを使います。')


# ---------------------------------------------------------------- 4
def s4(ctx):
    d = ctx.data
    d['ret'] = str(100 + secrets.randbelow(9000))
    d['ld'] = str(1 + secrets.randbelow(900))
    cols = ['entries', 'searched', 'found', 'new', 'invalid', 'ignore', 'delete', 'delete_list', 'insert', 'insert_failed', 'drop', 'early_drop']
    vals = [str(50 + secrets.randbelow(9000)) for _ in cols]
    d['inv'] = vals[4]
    put(ctx, 'ctstat.txt', '  '.join(cols) + '\n' + '  '.join(vals) + '\n')
    put(ctx, 'nstat.txt', f'#kernel\nIpInReceives                    {secrets.randbelow(99999)}               0.0\nTcpRetransSegs                  {d["ret"]}                  0.0\nTcpExtListenDrops               {d["ld"]}                  0.0\n')
    ctx.write('requirements.txt', 'answer.json: {"retrans": nstat.txtのTcpRetransSegs, "ct_invalid": ctstat.txtのinvalid列の値}\n'
              'cmds.txt に3行: ctstat と同じ内容を出す lnstat 行(-f nf_conntrack)、rtstat と同じ内容を出す lnstat 行(-f rt_cache)、'
              'arpd でARP DB neigh.db を(-b)ダンプ表示(-l)する行。\n')


def c4(ctx):
    need_ro(ctx)
    jcheck(ctx, {'retrans': 'ret', 'ct_invalid': 'inv'})
    ls = cl(ctx, 'cmds.txt')
    ctx.require(len(ls) == 3, '3行書きます。')
    ts = [toks(ctx, x) for x in ls]
    lf = sorted(opt(t, '-f') for t in ts if t[0] == 'lnstat')
    ctx.require(lf == ['nf_conntrack', 'rt_cache'], 'lnstat -f nf_conntrack と lnstat -f rt_cache を1行ずつ書きます。')
    a = first(ctx, ls, 'arpd')
    ctx.require('-l' in a and opt(a, '-b') == 'neigh.db', 'arpd -l -b neigh.db です。')


mission(4, 'ctstat・lnstat・nstat・rtstat・arpdの統計を読む',
        'iproute2には統計・補助ツール群があります。nstat はカーネルのネットワークカウンタ、ctstat と rtstat は lnstat の別名(それぞれconntrackとルートキャッシュ)、arpd はユーザー空間ARP DBです。nstat.txtとctstat.txtを読み、必要な値を答えにして、同等コマンドも書いてください。',
        ['2つの記録から値を抽出', 'lnstatによる同等コマンドとarpdを書く'], s4, c4,
        "r=$(awk '/TcpRetransSegs/{print $2}' nstat.txt)\nc=$(awk 'NR==1{for(i=1;i<=NF;i++)if($i==\"invalid\")k=i} NR==2{print $k}' ctstat.txt)\n"
        "echo \"{\\\"retrans\\\":\\\"$r\\\",\\\"ct_invalid\\\":\\\"$c\\\"}\" > answer.json\nprintf '%s\\n' 'lnstat -f nf_conntrack' 'lnstat -f rt_cache' 'arpd -l -b neigh.db' > cmds.txt",
        ["echo '{\"retrans\":\"<<ld>>\",\"ct_invalid\":\"<<inv>>\"}' > answer.json\nprintf '%s\\n' 'ctstat' 'rtstat' 'arpd' > cmds.txt",
         "echo '{\"retrans\":\"<<ret>>\",\"ct_invalid\":\"<<inv>>\"}' > answer.json\nprintf '%s\\n' 'lnstat -f conntrack' 'lnstat -f route' 'arpd -b neigh.db' > cmds.txt"],
        'nstatは前回との差分を表示するのが既定(-aで絶対値)。ctstat/rtstatは実体がlnstatで、-fでファイルを選びます(/proc/net/stat/nf_conntrack, rt_cache)。ヘッダ行で列を特定してから値を読むのが安全です。',
        '列名を見て目的の列番号を決めます。', 'awkでヘッダから列番号を求めます。')


# ---------------------------------------------------------------- 5
def s5(ctx):
    d = ctx.data
    nets = [f'10.{i}.0.0/16' for i in secrets.SystemRandom().sample(range(1, 200), 4)]
    gws = [rip() for _ in nets]
    devs = ['eth0', 'eth1', 'wlan0', 'ens3']
    k = secrets.randbelow(4)
    d.update(net=nets[k], gw=gws[k], dev=devs[k])
    rows = '      target            gateway    proto      dev\n      default  192.168.0.1     static     eth0\n'
    for a, b, c in zip(nets, gws, devs):
        rows += f'{a:>13} {b:>18} {"static":>9} {c:>8}\n'
    put(ctx, 'routel.txt', '$ routel\n' + rows)
    fams = ['nlctrl', 'devlink', 'nl80211', 'ethtool', 'tcp_metrics']
    ids = secrets.SystemRandom().sample(range(16, 60), 5)
    f = secrets.randbelow(5)
    d['fam'] = fams[f]
    d['fid'] = hex(ids[f])
    put(ctx, 'genl.txt', '$ genl ctrl list\n' + ''.join(f'{hex(i)} Name: {n}\n' for i, n in zip(ids, fams)))
    ctx.write('requirements.txt', f'answer.json: {{"gateway","dev"}} = routel.txtで {d["net"]} へ向かう経路のゲートウェイとデバイス、'
              f'{{"genl_id"}} = genl.txtでファミリ {d["fam"]} のID(0x付き)。\nmon.txt: ルーティングの変化を rt.mon というファイルへ記録する rtmon のコマンド1行(file サブコマンド)。\n')


def c5(ctx):
    need_ro(ctx)
    jcheck(ctx, {'gateway': 'gw', 'dev': 'dev', 'genl_id': 'fid'})
    m = tk1(ctx, 'mon.txt')
    ctx.require(m[0] == 'rtmon' and 'file' in m and 'rt.mon' in m, 'rtmon file rt.mon の形です。')


mission(5, 'routel・rtmon・genlでルートとnetlinkを読む',
        'routel は ip route show table all を表形式にするスクリプト、rtmon は netlink のルーティング変更を記録して ip monitor file で再生できるツール、genl は Generic Netlink のファミリを調べるツールです。routel.txt と genl.txt の出力を読み、rtmon の記録コマンドを書いてください。',
        ['routel出力から経路を特定', 'genlのファミリIDを調べる', 'rtmon file のコマンドを書く'], s5, c5,
        "g=$(awk '$1==\"<<net>>\"{print $2}' routel.txt)\nv=$(awk '$1==\"<<net>>\"{print $4}' routel.txt)\nf=$(awk '/Name: <<fam>>$/{print $1}' genl.txt)\n"
        "echo \"{\\\"gateway\\\":\\\"$g\\\",\\\"dev\\\":\\\"$v\\\",\\\"genl_id\\\":\\\"$f\\\"}\" > answer.json\necho 'rtmon file rt.mon' > mon.txt",
        ["echo '{\"gateway\":\"192.168.0.1\",\"dev\":\"eth0\",\"genl_id\":\"0x10\"}' > answer.json\necho 'rtmon' > mon.txt",
         "echo '{\"gateway\":\"<<gw>>\",\"dev\":\"<<dev>>\",\"genl_id\":\"<<fid>>\"}' > answer.json\necho 'ip monitor file rt.mon' > mon.txt"],
        'routelは table all の経路を target/gateway/dev などの列で表示します。rtmonは記録側(ip monitor file で後から再生)、genlは ctrl list でファミリ名とIDの対応を示します。IDは環境ごとに変わるので名前で引きます。',
        '列は target gateway proto dev の順です。', 'awkで target を条件に列を取り出します。')


# ---------------------------------------------------------------- 6
def s6(ctx):
    d = ctx.data
    R = secrets.SystemRandom()
    nds = ['ens1f0', 'ens1f1', 'ens2f0']
    pci = [f'pci/0000:{R.choice(["3b","5e","af"])}:00.{i}' for i in range(3)]
    k = secrets.randbelow(3)
    d.update(nd=nds[k], dev=pci[k])
    put(ctx, 'devlink.txt', '$ devlink port show\n' + ''.join(f'{p}/1: type eth netdev {n} flavour physical port 0 splittable false\n' for p, n in zip(pci, nds)))
    d['pfc'] = str(secrets.randbelow(8))
    put(ctx, 'dcb.txt', '$ dcb pfc show dev ens1f0\npfc-cap 8 macc 0 delay 0 prio-pfc ' + ' '.join(f'{i}:{"on" if str(i) == d["pfc"] else "off"}' for i in range(8)) + '\n')
    en = ['eth0', 'eth1', 'eth2']
    k2 = secrets.randbelow(3)
    d['rnd'] = en[k2]
    names = R.sample(range(0, 9), 3)
    d['rdma'] = f'mlx5_{names[k2]}'
    put(ctx, 'rdma.txt', '$ rdma link show\n' + ''.join(f'link mlx5_{x}/1 state ACTIVE physical_state LINK_UP netdev {e}\n' for x, e in zip(names, en)))
    addrs = ['1.1.%d' % i for i in R.sample(range(1, 90), 4)]
    kd = secrets.randbelow(4)
    d['tipc'] = addrs[kd]
    put(ctx, 'tipc.txt', '$ tipc node list\n' + ''.join(f'{a}: {"down" if i == kd else "up"}\n' for i, a in enumerate(addrs)))
    vq = R.sample([2, 4, 8, 16, 32], 3)
    k3 = secrets.randbelow(3)
    d['vq'] = str(vq[k3])
    d['vdpa'] = f'vdpa{k3}'
    put(ctx, 'vdpa.txt', '$ vdpa dev show\n' + ''.join(f'vdpa{i}: type network mgmtdev pci/0000:3b:00.{i + 2} vendor_id 5555 max_vqs {q} max_vq_size 256\n' for i, q in enumerate(vq)))
    ctx.write('requirements.txt', f'answer.json に: devlink_dev = devlink.txtで netdev {d["nd"]} を持つデバイス(pci/...まで)、pfc_prio = dcb.txtでPFCがonの優先度、'
              f'rdma_dev = rdma.txtで netdev {d["rnd"]} のRDMAデバイス名(スラッシュ手前)、tipc_down = tipc.txtでdownのノード、vdpa_dev = vdpa.txtで max_vqs {d["vq"]} のデバイス名(コロン無し)。\n')


def c6(ctx):
    need_ro(ctx)
    jcheck(ctx, {'devlink_dev': 'dev', 'pfc_prio': 'pfc', 'rdma_dev': 'rdma', 'tipc_down': 'tipc', 'vdpa_dev': 'vdpa'})


mission(6, 'devlink・dcb・rdma・tipc・vdpaの出力を読解する',
        'iproute2にはNICやクラスタ向けの専門ツールもあります。devlink(デバイス管理)、dcb(データセンターブリッジング)、rdma(RDMAリンク)、tipc(クラスタ通信)、vdpa(仮想化向けデータパス)の採取済み出力を読み、必要な値をanswer.jsonへ抜き出してください。',
        ['5つの出力から該当値を探す', 'answer.jsonへ保存'], s6, c6,
        "a=$(grep 'netdev <<nd>> ' devlink.txt | cut -d/ -f1,2)\nb=$(grep -o '[0-9]:on' dcb.txt | cut -d: -f1)\nc=$(awk '$NF==\"<<rnd>>\"{split($2,x,\"/\");print x[1]}' rdma.txt)\n"
        "d=$(awk '/down/{sub(\":\",\"\",$1);print $1}' tipc.txt)\ne=$(awk '/max_vqs <<vq>> /{sub(\":\",\"\",$1);print $1}' vdpa.txt)\n"
        "echo \"{\\\"devlink_dev\\\":\\\"$a\\\",\\\"pfc_prio\\\":\\\"$b\\\",\\\"rdma_dev\\\":\\\"$c\\\",\\\"tipc_down\\\":\\\"$d\\\",\\\"vdpa_dev\\\":\\\"$e\\\"}\" > answer.json",
        ["echo '{\"devlink_dev\":\"pci/0000:3b:00.0\",\"pfc_prio\":\"3\",\"rdma_dev\":\"mlx5_0\",\"tipc_down\":\"1.1.1\",\"vdpa_dev\":\"vdpa0\"}' > answer.json",
         "echo '{}' > answer.json"],
        'これらはiproute2の補助コマンドで、devlinkはNICのポート/ファームウェア、dcbはPFCなどのQoS、rdmaはRDMAデバイスとnetdevの対応、tipcはクラスタノードの状態、vdpaは仮想デバイスの管理を表示します。出力は「キーワード 値」の並びなので、grepとawkで安全に抜き出せます。',
        '各ファイルの形式は「キー 値」の並びです。', 'grep/awk/cutで1つずつ取り出します。')


# ---------------------------------------------------------------- 7
def s7(ctx):
    d = ctx.data
    g = [f'{secrets.randbelow(65536):04x}' for _ in range(3)]
    full = f'2001:0db8:{g[0]}:0000:0000:0000:{g[1]}:{g[2]}'
    d['v6'] = ipaddress.ip_address(full).compressed
    d['pfx'] = f'2001:db8:{secrets.randbelow(65535) + 1:x}::/64'
    d['gw'] = f'fe80::{1 + secrets.randbelow(200):x}'
    put(ctx, 'addr.txt', full + '\n')
    ctx.write('requirements.txt', 'addr.txt のIPv6アドレスについて\nshort.txt: 最短の(RFC 5952の)表記を1行\n'
              f'ping.txt: そのアドレスへIPv6で3回(-c 3)pingするコマンド1行\nroute.txt: 宛先 {d["pfx"]} を {d["gw"]} 経由(dev eth0)で追加するIPv6ルートのコマンド1行\n')


def c7(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(one_line(ctx, 'short.txt').lower() == d['v6'], 'short.txtは先頭ゼロを省き、最長のゼロ連続を::にします。')
    t = tk1(ctx, 'ping.txt')
    ctx.require(t[0] == 'ping6' or (t[0] == 'ping' and '-6' in t), 'ping6 か ping -6 を使います。')
    ctx.require(opt(t, '-c') == '3', '-c 3 を付けます。')
    ctx.require(any(x == d['v6'] for x in t), 'アドレスを指定します。')
    r = tk1(ctx, 'route.txt')
    ctx.require(r[:4] == ['ip', '-6', 'route', 'add'] and r[4] == d['pfx'] and opt(r, 'via') == d['gw'] and opt(r, 'dev') == 'eth0', 'ip -6 route add 宛先 via ゲートウェイ dev eth0 の形です。')


mission(7, 'IPv6の表記・ping -6・ip -6 routeを扱う',
        'IPv6は16進8グループで、連続するゼロは :: で1回だけ省略できます。疎通確認は ping6(= ping -6)、IPv4側は ping4(= ping -4) と書き分けます。ルートは ip -6 route で扱います。addr.txtのアドレスを短縮し、確認コマンドと経路追加コマンドを書いてください。',
        ['短縮表記を求める', 'ping -6 と ip -6 route のコマンドを書く'], s7, c7,
        "echo '<<v6>>' > short.txt\necho 'ping -6 -c 3 <<v6>>' > ping.txt\necho 'ip -6 route add <<pfx>> via <<gw>> dev eth0' > route.txt",
        ["cat addr.txt > short.txt\necho 'ping -c 3 <<v6>>' > ping.txt\necho 'ip route add <<pfx>> via <<gw>> dev eth0' > route.txt",
         "echo '<<v6>>' > short.txt\necho 'ping -4 -c 3 <<v6>>' > ping.txt\necho 'ip -6 route add <<pfx>> via <<gw>> dev eth0' > route.txt"],
        '先頭ゼロの省略は各グループ内、:: は最長のゼロ連続(同長なら先頭側)で1回だけです。ping6/ping -6 はIPv6専用、ping4/ping -4 はIPv4専用で、ip -6 を付けるとIPv6のルーティングテーブルを扱います。リンクローカルfe80::は物理IFの指定が必要になることがあります。ipv6 の確認は ping -6 と ip -6 の「-6」で切り替えます。',
        'ゼロの連続は1箇所だけ ::。', 'ping -6 / ip -6 を使います。')


# ---------------------------------------------------------------- 8
def s8(ctx):
    d = ctx.data
    d['c'] = f'ci-{secrets.token_hex(2)}@lab'
    d['sec'] = str(300 + 60 * secrets.randbelow(20))
    ctx.write('requirements.txt', f'agent.sh に4行を順に書く（実行はしない）。\n1) ssh-keygen: ed25519鍵を keys/id_ed25519 に、パスフレーズ無し(-N \'\')、コメント {d["c"]} で作成\n'
              f'2) ssh-agent を起動して環境変数をシェルに取り込む(eval と -s)\n3) ssh-add: {d["sec"]}秒だけ有効にして keys/id_ed25519 を登録\n4) ssh-add で登録済み鍵の一覧表示\n')


def c8(ctx):
    d = ctx.data
    ls = cl(ctx, 'agent.sh')
    ctx.require(len(ls) == 4, '4行ちょうどです。')
    k = first(ctx, ls, 'ssh-keygen')
    ctx.require(opt(k, '-t') == 'ed25519' and opt(k, '-f') == 'keys/id_ed25519' and opt(k, '-C') == d['c'] and opt(k, '-N') == '', 'ssh-keygenの引数が違います(-N \'\' を忘れずに)。')
    ctx.require(re.match(r'^eval\s+["\']?\$\(ssh-agent\s+-s\)["\']?$', ls[1]), '2行目は eval "$(ssh-agent -s)" です。')
    adds = [toks(ctx, x) for x in ls if x.startswith('ssh-add')]
    ctx.require(len(adds) == 2, 'ssh-addは2回(登録と一覧)です。')
    reg = [t for t in adds if '-l' not in t]
    ctx.require(len(reg) == 1 and opt(reg[0], '-t') == d['sec'] and reg[0][-1] == 'keys/id_ed25519', 'ssh-add -t 秒 keys/id_ed25519 です。')
    ctx.require(ls.index(next(x for x in ls if x.startswith('ssh-keygen'))) < ls.index(next(x for x in ls if x.startswith('ssh-add'))), 'ssh-keygen → ssh-agent → ssh-add の順です。')


mission(8, 'ssh-keygen・ssh-agent・ssh-addで鍵運用の手順を書く',
        'SSH鍵は ssh-keygen で作り、ssh-agent に ssh-add で一時的に預けるとパスフレーズ入力の手間とリスクを減らせます。ssh-agent は環境変数を出力するので eval "$(ssh-agent -s)" で取り込みます。requirements.txtの条件で手順スクリプト agent.sh を書いてください。',
        ['4行の手順をagent.shへ', 'ssh-add -t で期限付き登録'], s8, c8,
        "printf '%s\\n' \"ssh-keygen -t ed25519 -f keys/id_ed25519 -N '' -C <<c>>\" 'eval \"$(ssh-agent -s)\"' 'ssh-add -t <<sec>> keys/id_ed25519' 'ssh-add -l' > agent.sh",
        ["printf '%s\\n' 'ssh-keygen -t rsa -f keys/id_ed25519' 'ssh-agent' 'ssh-add keys/id_ed25519' 'ssh-add -L' > agent.sh",
         "printf '%s\\n' \"ssh-keygen -t ed25519 -f keys/id_ed25519 -N '' -C <<c>>\" 'ssh-agent -s' 'ssh-add -t <<sec>> keys/id_ed25519' 'ssh-add -l' > agent.sh"],
        'ssh-agent単体はSSH_AUTH_SOCKなどの行を出力するだけで、evalしないと現在のシェルに反映されません。ssh-add -t は鍵の有効期限(秒)、-l は指紋の一覧、-L は公開鍵の一覧、-D は全削除です。',
        'エージェントはevalで取り込みます。', 'ssh-keygen -t -f -N -C, ssh-add -t -l を使います。')


# ---------------------------------------------------------------- 9
def s9(ctx):
    d = ctx.data
    b = lambda: ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/') for _ in range(44))
    d['host'] = f'bastion-{secrets.token_hex(2)}.example.test'
    d['dec'] = f'files-{secrets.token_hex(2)}.example.test'
    d['port'] = str(2200 + secrets.randbelow(700))
    d['user'] = 'ops' + secrets.token_hex(1)
    txt = ''
    for h in (d['dec'], d['host']):
        txt += f'# {h}:22 SSH-2.0-OpenSSH_9.2\n{h} ssh-rsa AAAAB3NzaC1yc2E{b()}\n{h} ecdsa-sha2-nistp256 AAAAE2VjZHNh{b()}\n{h} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA{b()}\n'
    put(ctx, 'keyscan.txt', '$ ssh-keyscan -t rsa,ecdsa,ed25519 host ...\n' + txt.replace('$ ssh-keyscan', '#'))
    d['kh'] = [x for x in txt.splitlines() if x.startswith(d['host'] + ' ssh-ed25519 ')][0]
    ctx.write('requirements.txt', f'keyscan.txt は ssh-keyscan の採取結果。known_hosts には {d["host"]} のed25519の1行だけを入れる（ssh-keyscan出力のコメントは除く）。\n'
              f'copy.txt: 公開鍵 keys/id_ed25519.pub を {d["user"]}@{d["host"]} のポート {d["port"]} へ登録する ssh-copy-id の1行\n'
              f'slogin.txt: 秘密鍵 keys/id_ed25519 を指定して同ホスト・ポートへ入る slogin の1行\n')


def c9(ctx):
    need_ro(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('known_hosts').splitlines() == [d['kh']], 'known_hostsは対象ホストのed25519の1行だけです。')
    c = tk1(ctx, 'copy.txt')
    ctx.require(c[0] == 'ssh-copy-id' and opt(c, '-i') == 'keys/id_ed25519.pub' and opt(c, '-p') == d['port'] and c[-1] == f'{d["user"]}@{d["host"]}', 'ssh-copy-id -i 公開鍵 -p ポート user@host です。')
    s = tk1(ctx, 'slogin.txt')
    ctx.require(s[0] == 'slogin' and opt(s, '-i') == 'keys/id_ed25519' and opt(s, '-p') == d['port'] and s[-1] == f'{d["user"]}@{d["host"]}', 'slogin -i 秘密鍵 -p ポート user@host です。')


mission(9, 'ssh-keyscan・ssh-copy-id・sloginで接続を準備する',
        '初回接続の確認をスクリプトで済ませるには ssh-keyscan でホスト鍵を集めて known_hosts に登録し、ssh-copy-id で公開鍵を authorized_keys へ置き、slogin(ssh の別名)で入ります。keyscan.txtから対象ホストのed25519鍵だけを known_hosts に入れ、2つのコマンドを書いてください。',
        ['known_hostsを作る', 'ssh-copy-idとsloginを書く'], s9, c9,
        "grep '^<<host>> ssh-ed25519 ' keyscan.txt > known_hosts\necho 'ssh-copy-id -i keys/id_ed25519.pub -p <<port>> <<user>>@<<host>>' > copy.txt\necho 'slogin -i keys/id_ed25519 -p <<port>> <<user>>@<<host>>' > slogin.txt",
        ["grep '<<host>>' keyscan.txt > known_hosts\necho 'ssh-copy-id <<user>>@<<host>>' > copy.txt\necho 'slogin <<user>>@<<host>>' > slogin.txt",
         "grep 'ssh-ed25519' keyscan.txt > known_hosts\necho 'ssh-copy-id -i keys/id_ed25519.pub -p <<port>> <<user>>@<<host>>' > copy.txt\necho 'slogin -i keys/id_ed25519 -p <<port>> <<user>>@<<host>>' > slogin.txt"],
        'ssh-keyscanは出力を無条件に信頼すると中間者に弱いので、本番では指紋を別経路で照合します。ssh-copy-id は -i で公開鍵を指定でき、-p のポートは ssh と同様です。slogin は ssh と同じプログラムの別名です。',
        'ホスト名の行頭一致とアルゴリズム名で絞ります。', 'grep "^ホスト ssh-ed25519 " を使います。')


# ---------------------------------------------------------------- 10
def s10(ctx):
    d = ctx.data
    b = lambda: ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789') for _ in range(43))
    d['dir'] = f'/srv/backup-{secrets.token_hex(2)}'
    d['tag'] = f'sync-{secrets.token_hex(2)}'
    d['host'] = f'rsync-{secrets.token_hex(2)}.example.test'
    d['mod'] = 'mod' + secrets.token_hex(2)
    d['key'] = f'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{b()} {d["tag"]}@ci'
    d['other'] = f'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{b()} admin@lab'
    ctx.write('authorized_keys', d['other'] + '\n' + d['key'] + '\n')
    ctx.write('requirements.txt', f'authorized_keys の {d["tag"]}@ci の鍵を、{d["dir"]} を読み取り専用でrsyncするだけに制限する(command=で rrsync -ro、restrictも付ける)。他の行は変えない。\n'
              f'rsync-ssl.txt: TLS越しに {d["host"]} のモジュール {d["mod"]} を rsync://形式で dest/ へアーカイブ(-a)同期する rsync-ssl の1行。\n')


def c10(ctx):
    d = ctx.data
    ls = ctx.need_file('authorized_keys').splitlines()
    ctx.require(len(ls) == 2 and ls[0] == d['other'], '他の鍵の行は変更しません。')
    ln = ls[1]
    ctx.require(ln.endswith(' ' + d['key']) and f'command="rrsync -ro {d["dir"]}"' in ln and 'restrict' in ln[:-len(d['key'])], 'command="rrsync -ro ディレクトリ",restrict を鍵の前に付けます。')
    t = tk1(ctx, 'rsync-ssl.txt')
    ctx.require(t[0] == 'rsync-ssl' and any(x.startswith('-') and not x.startswith('--') and 'a' in x for x in t) and t[-1].rstrip('/') == 'dest' and any(x.startswith(f'rsync://{d["host"]}/{d["mod"]}') for x in t), 'rsync-ssl -a rsync://host/module/ dest/ の形です。')


mission(10, 'rrsync・rsync-sslで同期の権限を絞る',
        'バックアップ専用の鍵にシェルを渡す必要はありません。authorized_keys の command= に rrsync(ssh用rsync制限ラッパー)を指定し -ro で読み取り専用・特定ディレクトリ限定にします。TLSで同期するクライアントは rsync-ssl です。requirements.txtのとおりに鍵を制限し、同期コマンドを書いてください。',
        ['authorized_keysの該当行を制限', 'rsync-ssl の1行を書く'], s10, c10,
        "sed -i 's#^\\(ssh-ed25519 .* <<tag>>@ci\\)$#command=\"rrsync -ro <<dir>>\",restrict \\1#' authorized_keys\necho 'rsync-ssl -a rsync://<<host>>/<<mod>>/ dest/' > rsync-ssl.txt",
        ["sed -i 's#^\\(ssh-ed25519 .* <<tag>>@ci\\)$#command=\"rsync --server\" \\1#' authorized_keys\necho 'rsync-ssl <<host>>' > rsync-ssl.txt",
         "sed -i 's#^\\(ssh-ed25519 .*\\)$#command=\"rrsync -ro <<dir>>\",restrict \\1#' authorized_keys\necho 'rsync-ssl -a rsync://<<host>>/<<mod>>/ dest/' > rsync-ssl.txt"],
        'rrsyncは受け付けるrsyncの引数を検査し、指定ディレクトリの外や書き込みを拒否します。-roで読み取り専用になります。restrictはポート転送・端末割当などを一括無効にします。rsync-sslはstunnelなどでrsyncデーモンへTLS接続する補助です。',
        '鍵の行の先頭にオプションを付けます。', 'sedの行指定を対象のコメントで絞ります。')


# ---------------------------------------------------------------- 11
def s11(ctx):
    d = ctx.data
    d['pkg'] = 'tool' + secrets.token_hex(2)
    d['inst'] = f'1.{secrets.randbelow(9)}.{secrets.randbelow(9)}-1'
    d['cand'] = f'2.{secrets.randbelow(9)}.{secrets.randbelow(9)}-1'
    d['suite'] = secrets.choice(['bookworm-backports', 'trixie', 'bookworm-updates'])
    put(ctx, 'policy.txt', f'$ apt-cache policy {d["pkg"]}\n{d["pkg"]}:\n  Installed: {d["inst"]}\n  Candidate: {d["cand"]}\n  Version table:\n     {d["cand"]} 500\n        500 http://deb.example.test/debian stable/main amd64 Packages\n *** {d["inst"]} 100\n        100 /var/lib/dpkg/status\n')
    ctx.write('requirements.txt', f'answer.json: {{"installed","candidate"}} を policy.txt (apt-cache policy の出力)から。\n'
              f'apt.conf.d/99local: apt設定(apt-config dumpで見える形式)で APT::Default-Release を "{d["suite"]}"、APT::Install-Recommends を "false" にする（書式: キー "値";）。\n'
              'dump.txt: 設定が効いたか apt-config dump で確認するコマンド1行（apt-config dump）。\n')


def c11(ctx):
    need_ro(ctx)
    jcheck(ctx, {'installed': 'inst', 'candidate': 'cand'})
    conf = {}
    for ln in ctx.need_file('apt.conf.d/99local').splitlines():
        m = re.match(r'^\s*([\w:-]+)\s+"([^"]*)"\s*;', ln)
        if m:
            conf[m.group(1)] = m.group(2)
    ctx.require(conf.get('APT::Default-Release') == ctx.data['suite'], 'APT::Default-Release "スイート"; を書きます。')
    ctx.require(conf.get('APT::Install-Recommends') == 'false', 'APT::Install-Recommends "false"; を書きます。')
    t = tk1(ctx, 'dump.txt')
    ctx.require(t[:2] == ['apt-config', 'dump'], 'apt-config dump です。')


mission(11, 'apt-cache・apt-configで候補版と設定を調べる',
        'apt-cache policy は「入っている版」と「入れられる候補版」、どのリポジトリが供給するかを示します。apt-config は設定(/etc/apt/apt.conf.d/*)を統合表示する道具です。policy.txtから版を読み取り、設定ファイルを作成して、確認コマンドを書いてください。',
        ['policyから版を抽出', 'apt.conf.d/99localを書く', 'apt-config dumpを書く'], s11, c11,
        "i=$(awk '/Installed:/{print $2}' policy.txt)\nc=$(awk '/Candidate:/{print $2}' policy.txt)\necho \"{\\\"installed\\\":\\\"$i\\\",\\\"candidate\\\":\\\"$c\\\"}\" > answer.json\n"
        "mkdir -p apt.conf.d\nprintf '%s\\n' 'APT::Default-Release \"<<suite>>\";' 'APT::Install-Recommends \"false\";' > apt.conf.d/99local\necho 'apt-config dump' > dump.txt",
        ["echo '{\"installed\":\"<<cand>>\",\"candidate\":\"<<inst>>\"}' > answer.json\nmkdir -p apt.conf.d\necho 'APT::Install-Recommends false' > apt.conf.d/99local\necho 'apt-cache dump' > dump.txt",
         "i=$(awk '/Installed:/{print $2}' policy.txt)\nc=$(awk '/Candidate:/{print $2}' policy.txt)\necho \"{\\\"installed\\\":\\\"$i\\\",\\\"candidate\\\":\\\"$c\\\"}\" > answer.json\nmkdir -p apt.conf.d\necho 'APT::Install-Recommends \"false\";' > apt.conf.d/99local\necho 'apt-config dump' > dump.txt"],
        '番号の大きいファイルが後勝ちなので、独自設定は99で始まる名前にします。apt-cache policy の *** は現在の版、500などは優先度(pin priority)です。Default-Release は特定スイートを優先させます。apt-config dump は反映後の全設定を表示します。',
        '設定は 末尾に ; が必要です。', 'awkで抽出し、printfで設定を作ります。')


# ---------------------------------------------------------------- 12
def s12(ctx):
    d = ctx.data
    d['name'] = 'vend' + secrets.token_hex(2)
    d['url'] = f'https://repo.{secrets.token_hex(2)}.example.test/debian'
    d['suite'] = secrets.choice(['stable', 'bookworm', 'trixie'])
    put(ctx, 'key.asc', '-----BEGIN PGP PUBLIC KEY BLOCK-----\n' + secrets.token_hex(24) + '\n-----END PGP PUBLIC KEY BLOCK-----\n')
    ctx.write('sources.list', f'deb {d["url"]} {d["suite"]} main\n')
    ctx.write('old.txt', 'これまでの手順: apt-key add key.asc (非推奨。鍵が全リポジトリで信頼されてしまう)\n')
    ctx.write('requirements.txt', f'apt-keyに頼らず、鍵を /etc/apt/keyrings/{d["name"]}.gpg に置いて、このリポジトリにだけ使う設計にする。\n'
              f'dearmor.txt: key.asc(ASCII armor)を上記のバイナリ鍵へ変換する gpg の1行。\nsources.list: signed-by=[ ] で鍵を指定した deb 1行へ書き換える（URLとスイートは維持）。\ncdrom.txt: 光学メディアをソースへ追加する apt-cdrom の1行(add)。\n')


def c12(ctx):
    need_ro(ctx)
    d = ctx.data
    kp = f'/etc/apt/keyrings/{d["name"]}.gpg'
    g = tk1(ctx, 'dearmor.txt')
    ctx.require(g[0] == 'gpg' and '--dearmor' in g and opt(g, '-o', '--output') == kp and 'key.asc' in g, f'gpg --dearmor -o {kp} key.asc の形です。')
    ls = cl(ctx, 'sources.list')
    ctx.require(len(ls) == 1 and ls[0] == f'deb [signed-by={kp}] {d["url"]} {d["suite"]} main', 'deb [signed-by=鍵] URL スイート main の1行にします。')
    c = tk1(ctx, 'cdrom.txt')
    ctx.require(c[0] == 'apt-cdrom' and 'add' in c, 'apt-cdrom add です。')


mission(12, 'apt-key廃止後のキーリングとsources.list・apt-cdrom',
        'apt-key は廃止予定です。全リポジトリが同じ鍵束を信頼するためで、現在は鍵を /etc/apt/keyrings/ 等に置き、sources.list の signed-by= でリポジトリごとに結びつけます。ASCII armor鍵は gpg --dearmor でバイナリ化します。物理メディアからの導入は apt-cdrom add です。requirements.txtのとおりに作成してください。',
        ['dearmorコマンド', 'signed-by付きsources.list', 'apt-cdrom add'], s12, c12,
        "echo 'gpg --dearmor -o /etc/apt/keyrings/<<name>>.gpg key.asc' > dearmor.txt\necho 'deb [signed-by=/etc/apt/keyrings/<<name>>.gpg] <<url>> <<suite>> main' > sources.list\necho 'apt-cdrom add' > cdrom.txt",
        ["echo 'apt-key add key.asc' > dearmor.txt\necho 'deb [trusted=yes] <<url>> <<suite>> main' > sources.list\necho 'apt-cdrom' > cdrom.txt",
         "echo 'gpg --dearmor -o /etc/apt/keyrings/<<name>>.gpg key.asc' > dearmor.txt\necho 'deb <<url>> <<suite>> main' > sources.list\necho 'apt-cdrom add' > cdrom.txt"],
        'signed-byを使うと、鍵の信頼範囲がそのリポジトリに限定されます。trusted=yes は署名検証を無効化するため避けます。apt-key list は参照用に残る場合もありますが、追加は推奨されません。',
        '鍵を共有せず、リポジトリごとに結びつけます。', 'gpg --dearmor -o と signed-by を使います。')


# ---------------------------------------------------------------- 13
def s13(ctx):
    d = ctx.data
    d['name'] = 'corp' + secrets.token_hex(2)
    d['url'] = f'https://mirror.{secrets.token_hex(2)}.example.test/pub'
    d['suite'] = 'stable'
    d['en'] = secrets.choice([0, 1])
    put(ctx, f'yum.repos.d/{d["name"]}.repo', f'[{d["name"]}]\nname=Corp repo\nbaseurl={d["url"]}\nenabled={d["en"]}\ngpgcheck=1\ngpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-{d["name"]}\n')
    ctx.mkdir('sources.list.d')
    ctx.write('requirements.txt', f'RPM系の yum.repos.d/{d["name"]}.repo と同じ意味のDebian系設定を sources.list.d/{d["name"]}.list に作る。\n'
              f'gpgcheck=1+gpgkey は signed-by=/etc/apt/keyrings/{d["name"]}.gpg に対応、baseurl は URL、スイートは {d["suite"]}、コンポーネントは main。\n'
              'enabled=0 のリポジトリは無効にする（行頭 # でコメントアウト）。enabled=1 なら有効な行にする。\n')


def c13(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = [x.strip() for x in ctx.need_file(f'sources.list.d/{d["name"]}.list').splitlines() if x.strip()]
    line = f'deb [signed-by=/etc/apt/keyrings/{d["name"]}.gpg] {d["url"]} {d["suite"]} main'
    if d['en'] == 1:
        ctx.require(ls == [line], '有効な deb 行が1つだけ必要です。')
    else:
        ctx.require(ls == ['# ' + line] or ls == ['#' + line], 'enabled=0 なので行頭を # でコメントアウトした行にします。')


mission(13, 'sources.listとyum.repos.dの設計を対応づける',
        'APT は /etc/apt/sources.list と sources.list.d/*.list、YUM/DNF は /etc/yum.repos.d/*.repo にリポジトリを書きます。形式は違っても、URL・有効/無効・署名鍵(キーリング)という同じ要素を持ちます。.repoファイルを読み、同じ意味のDebian系設定を作成してください。',
        ['.repoの意味を読む', 'sources.list.d/*.listを作る'], s13, c13,
        "line='deb [signed-by=/etc/apt/keyrings/<<name>>.gpg] <<url>> <<suite>> main'\n[ <<en>> = 1 ] && echo \"$line\" > sources.list.d/<<name>>.list || echo \"# $line\" > sources.list.d/<<name>>.list",
        ["echo 'deb <<url>> <<suite>> main' > sources.list.d/<<name>>.list",
         "[ <<en>> = 1 ] && echo '# deb [signed-by=/etc/apt/keyrings/<<name>>.gpg] <<url>> <<suite>> main' > sources.list.d/<<name>>.list || echo 'deb [signed-by=/etc/apt/keyrings/<<name>>.gpg] <<url>> <<suite>> main' > sources.list.d/<<name>>.list"],
        '対応は baseurl→deb行のURL、enabled→行の有無(コメント化)、gpgcheck/gpgkey→signed-by とキーリングです。キーリングはAPTが /etc/apt/keyrings や /usr/share/keyrings、RPMが /etc/pki/rpm-gpg に置くのが慣例です。',
        'enabled の値で行を有効/無効にします。', '条件分岐で echo の先頭に # を付け分けます。')


# ---------------------------------------------------------------- 14
def s14(ctx):
    d = ctx.data
    d['pkg'] = 'tool' + secrets.token_hex(2)
    d['ver'] = f'{1 + secrets.randbelow(5)}.{secrets.randbelow(9)}'
    d['kib'] = str(64 * (1 + secrets.randbelow(8)))
    ctx.write('pkgroot/DEBIAN/control', f'Package: {d["pkg"]}\nVersion: {d["ver"]}\nArchitecture: all\nMaintainer: Trainee <t@example.test>\nDescription: demo\n')
    ctx.data.setdefault('ro', {})['pkgroot/DEBIAN/control'] = sha(ctx.read('pkgroot/DEBIAN/control'))
    ctx.write('requirements.txt', 'pkgroot を .deb にする。ファイル名は control の Package_Version_Architecture.deb。\n'
              'build.txt: dpkg-deb で所有者をroot:rootにして(--root-owner-group)ビルドする1行\ninfo.txt: そのdebの Depends フィールドだけを表示する dpkg-deb の1行(-f)\n'
              f'split.txt: dpkg-split で {d["kib"]} KiB 毎の部品に分割する1行\njoin.txt: 部品 part1.deb part2.deb を dpkg-split で full.deb に結合する1行\n')


def c14(ctx):
    need_ro(ctx)
    d = ctx.data
    deb = f'{d["pkg"]}_{d["ver"]}_all.deb'
    b = tk1(ctx, 'build.txt')
    ctx.require(b[0] == 'dpkg-deb' and ('--build' in b or '-b' in b) and '--root-owner-group' in b and 'pkgroot' in b and b[-1] == deb, f'dpkg-deb --build --root-owner-group pkgroot {deb} です。')
    i = tk1(ctx, 'info.txt')
    ctx.require(i[0] == 'dpkg-deb' and ('-f' in i or '--field' in i) and deb in i and i[-1] == 'Depends', 'dpkg-deb -f ファイル Depends です。')
    s = tk1(ctx, 'split.txt')
    ctx.require(s[0] == 'dpkg-split' and ('--split' in s or '-s' in s) and opt(s, '-S', '--partsize') == d['kib'] and deb in s, 'dpkg-split --split --partsize KiB ファイル です。')
    j = tk1(ctx, 'join.txt')
    ctx.require(j[0] == 'dpkg-split' and ('--join' in j or '-j' in j) and opt(j, '-o', '--output') == 'full.deb' and 'part1.deb' in j and 'part2.deb' in j, 'dpkg-split --join -o full.deb part1.deb part2.deb です。')


mission(14, 'dpkg-debとdpkg-splitでパッケージを作る・分割する',
        'dpkg-deb は .deb の作成(--build)・内容表示(-c)・制御情報の取得(-f)を行います。大きな.debはメール添付やメディア容量のため dpkg-split で分割(--split)し、--join で戻せます。pkgroot の control を読んで、4つのコマンドを書いてください。',
        ['ファイル名をcontrolから決める', '4つのコマンドを書く'], s14, c14,
        "f=<<pkg>>_<<ver>>_all.deb\necho \"dpkg-deb --build --root-owner-group pkgroot $f\" > build.txt\necho \"dpkg-deb -f $f Depends\" > info.txt\necho \"dpkg-split --split --partsize <<kib>> $f\" > split.txt\necho 'dpkg-split --join -o full.deb part1.deb part2.deb' > join.txt",
        ["echo 'dpkg-deb --build pkgroot' > build.txt\necho 'dpkg-deb -I x.deb' > info.txt\necho 'dpkg-split x.deb' > split.txt\necho 'dpkg-split full.deb' > join.txt",
         "f=<<pkg>>_<<ver>>_amd64.deb\necho \"dpkg-deb --build --root-owner-group pkgroot $f\" > build.txt\necho \"dpkg-deb -f $f Depends\" > info.txt\necho \"dpkg-split --split --partsize <<kib>> $f\" > split.txt\necho 'dpkg-split --join -o full.deb part1.deb part2.deb' > join.txt"],
        '--root-owner-group を付けないと、ビルドしたユーザーの所有権が.debに入ります。dpkg-splitの部品は専用ヘッダを持つ独立した.debで、元の識別情報を保持します。-Iは制御情報の全表示、-fは特定フィールドです。',
        '名前は Package_Version_Architecture.deb。', 'ビルド・取得・分割・結合の4コマンドです。')


# ---------------------------------------------------------------- 15
def s15(ctx):
    d = ctx.data
    d['tool'] = 'util' + secrets.token_hex(2)
    d['usr'] = 'svc' + secrets.token_hex(2)
    d['mode'] = secrets.choice(['0750', '0640', '0700'])
    d['own'] = 'pkg' + secrets.token_hex(2)
    d['dpath'] = f'/usr/bin/{secrets.token_hex(2)}'
    n = 3
    ls = [f'local diversion of /usr/bin/a{secrets.token_hex(1)} to /usr/bin/a.orig' for _ in range(n)]
    ls += [f'diversion of {d["dpath"]} to {d["dpath"]}.distrib by {d["own"]}', 'diversion of /usr/bin/zz to /usr/bin/zz.real by other-pkg']
    secrets.SystemRandom().shuffle(ls)
    put(ctx, 'diversions.txt', '$ dpkg-divert --list\n' + '\n'.join(ls) + '\n')
    d['lc'] = str(n)
    ctx.write('requirements.txt', f'divert.txt: /usr/bin/{d["tool"]} を、パッケージ更新で上書きされないよう、管理者のローカル迂回として(--local)元ファイルを /usr/bin/{d["tool"]}.orig へ移し(--rename, --divert)追加する dpkg-divert の1行\n'
              f'statover.txt: {d["usr"]}:{d["usr"]} 所有、モード {d["mode"]} を /usr/bin/{d["tool"]} に恒久設定し即時反映もする dpkg-statoverride の1行(--update --add)\n'
              f'realpath.txt: /bin/{d["tool"]} の実体をdpkgの視点で解決する dpkg-realpath の1行\n'
              f'answer.json: {{"local_count": diversions.txtのローカル迂回の数, "owner": {d["dpath"]} を迂回しているパッケージ名}}\n')


def c15(ctx):
    need_ro(ctx)
    d = ctx.data
    p = f'/usr/bin/{d["tool"]}'
    t = tk1(ctx, 'divert.txt')
    ctx.require(t[0] == 'dpkg-divert' and '--add' in t and '--local' in t and '--rename' in t and opt(t, '--divert') == p + '.orig' and t[-1] == p, 'dpkg-divert --local --rename --divert パス.orig --add パス です。')
    s = tk1(ctx, 'statover.txt')
    ctx.require(s[0] == 'dpkg-statoverride' and '--update' in s and '--add' in s and s[s.index('--add') + 1:s.index('--add') + 5] == [d['usr'], d['usr'], d['mode'], p], 'dpkg-statoverride --update --add 所有者 グループ モード パス です。')
    r = tk1(ctx, 'realpath.txt')
    ctx.require(r[0] == 'dpkg-realpath' and r[-1] == f'/bin/{d["tool"]}', 'dpkg-realpath /bin/名前 です。')
    jcheck(ctx, {'local_count': 'lc', 'owner': 'own'})


mission(15, 'dpkg-divert・dpkg-statoverride・dpkg-realpath',
        'パッケージ管理下のファイルを上書き・権限変更してもアップグレードで元に戻されます。dpkg-divert はファイルの置き場所を迂回し、dpkg-statoverride は所有者・モードの変更を保持します。usrmergeで/binが/usr/binへのリンクになると実体の解決も重要で、dpkg-realpath が使えます。requirements.txtのとおりに書き、diversions.txtを診断してください。',
        ['3つのdpkgコマンドを書く', '迂回一覧を診断'], s15, c15,
        "p=/usr/bin/<<tool>>\necho \"dpkg-divert --local --rename --divert $p.orig --add $p\" > divert.txt\necho \"dpkg-statoverride --update --add <<usr>> <<usr>> <<mode>> $p\" > statover.txt\necho 'dpkg-realpath /bin/<<tool>>' > realpath.txt\n"
        "n=$(grep -c '^local diversion' diversions.txt)\no=$(grep ' <<dpath>> to ' diversions.txt | awk '{print $NF}')\necho \"{\\\"local_count\\\":\\\"$n\\\",\\\"owner\\\":\\\"$o\\\"}\" > answer.json",
        ["p=/usr/bin/<<tool>>\necho \"dpkg-divert --add $p\" > divert.txt\necho \"chmod <<mode>> $p\" > statover.txt\necho 'realpath /bin/<<tool>>' > realpath.txt\necho '{}' > answer.json",
         "p=/usr/bin/<<tool>>\necho \"dpkg-divert --local --rename --divert $p.orig --add $p\" > divert.txt\necho \"dpkg-statoverride --update --add <<usr>> <<usr>> <<mode>> $p\" > statover.txt\necho 'dpkg-realpath /bin/<<tool>>' > realpath.txt\necho '{\"local_count\":\"5\",\"owner\":\"other-pkg\"}' > answer.json"],
        '--localは管理者自身の迂回で、パッケージ名付きの迂回と区別されます。--renameで実ファイルも移動します。statoverrideは--updateで今すぐ反映し、dpkgが以後の展開でも設定を維持します。dpkg-realpathはdpkgの管理するパス体系で実体を解決します。',
        'ローカル迂回はパッケージ名の"by"が付きません。', 'grepでlocal diversionを数え、対象パスの行から末尾を取ります。')


# ---------------------------------------------------------------- 16
def s16(ctx):
    d = ctx.data
    d['app'] = 'app' + secrets.token_hex(2)
    d['ver'] = f'{2 + secrets.randbelow(5)}.{secrets.randbelow(9)}'
    d['wp'] = f'/usr/share/{secrets.choice(["mime", "icons", "applications"])}-{secrets.token_hex(1)}'
    d['np'] = f'/usr/share/{secrets.choice(["fonts", "man", "doc"])}-{secrets.token_hex(1)}'
    ctx.write('requirements.txt', f'パッケージ {d["app"]} (次版 {d["ver"]}) のメンテナ作業。\ntriggers: 別パッケージがこのパス {d["wp"]} を更新したら待たずに自分の postinst triggered を走らせる（interest-noawait）。\n'
              f'postinst.txt: 自分が {d["np"]} を更新したことを、待ち合わせなし(--no-await)で通知する dpkg-trigger の1行\n'
              f'maintscript: debian/*.maintscript の書式で、廃止設定 /etc/{d["app"]}/old.conf を版 {d["ver"]}~ で削除(rm_conffile)、/etc/{d["app"]}/a.conf を /etc/{d["app"]}/b.conf へ改名(mv_conffile)する2行\n'
              f'helper.sh: 実際のmaintainerスクリプトでdebhelperが作る dpkg-maintscript-helper の呼び出し1行(rm_conffile 設定 版~ -- "$@")\n')


def c16(ctx):
    d = ctx.data
    ctx.require(cl(ctx, 'triggers') == [f'interest-noawait {d["wp"]}'], 'triggers は interest-noawait パス の1行です。')
    t = tk1(ctx, 'postinst.txt')
    ctx.require(t[0] == 'dpkg-trigger' and '--no-await' in t and t[-1] == d['np'], 'dpkg-trigger --no-await パス です。')
    ms = [x.split() for x in cl(ctx, 'maintscript')]
    a = d['app']
    ctx.require(ms == [['rm_conffile', f'/etc/{a}/old.conf', d['ver'] + '~'], ['mv_conffile', f'/etc/{a}/a.conf', f'/etc/{a}/b.conf', d['ver'] + '~']], 'maintscriptの2行が違います(rm_conffile → mv_conffile の順)。')
    h = tk1(ctx, 'helper.sh')
    ctx.require(h == ['dpkg-maintscript-helper', 'rm_conffile', f'/etc/{a}/old.conf', d['ver'] + '~', '--', '$@'], 'dpkg-maintscript-helper rm_conffile 設定 版~ -- "$@" です。')


mission(16, 'dpkg-triggerとdpkg-maintscript-helperで保守スクリプトを書く',
        'dpkgのトリガは「共有データを更新したら後で一括処理」の仕組みで、関心を宣言する triggers ファイルと、更新を通知する dpkg-trigger があります。廃止した設定ファイルの扱いは dpkg-maintscript-helper(rm_conffile, mv_conffile)が安全に処理します。requirements.txtの成果物を作ってください。',
        ['triggersとdpkg-triggerを書く', 'maintscriptと呼び出し行を書く'], s16, c16,
        "echo 'interest-noawait <<wp>>' > triggers\necho 'dpkg-trigger --no-await <<np>>' > postinst.txt\nprintf '%s\\n' 'rm_conffile /etc/<<app>>/old.conf <<ver>>~' 'mv_conffile /etc/<<app>>/a.conf /etc/<<app>>/b.conf <<ver>>~' > maintscript\n"
        "echo 'dpkg-maintscript-helper rm_conffile /etc/<<app>>/old.conf <<ver>>~ -- \"$@\"' > helper.sh",
        ["echo 'interest <<wp>>' > triggers\necho 'dpkg-trigger <<np>>' > postinst.txt\necho 'rm /etc/<<app>>/old.conf' > maintscript\necho 'rm -f /etc/<<app>>/old.conf' > helper.sh",
         "echo 'interest-noawait <<wp>>' > triggers\necho 'dpkg-trigger --no-await <<np>>' > postinst.txt\nprintf '%s\\n' 'mv_conffile /etc/<<app>>/a.conf /etc/<<app>>/b.conf <<ver>>~' 'rm_conffile /etc/<<app>>/old.conf <<ver>>~' > maintscript\necho 'dpkg-maintscript-helper rm_conffile /etc/<<app>>/old.conf <<ver>>~ -- \"$@\"' > helper.sh"],
        '版の~は「その版より前」を意味し、その版へのアップグレード時だけ処理します。--no-awaitを使うと待ち合わせ関係を作らず通知でき、interest-noawaitと対応します。ユーザーが編集した設定ファイルは、rmで消さずヘルパーに任せて保全します。',
        'トリガは宣言と通知の2部品です。', 'maintscript は rm_conffile/mv_conffile の順で書きます。')


# ---------------------------------------------------------------- 17
def s17(ctx):
    d = ctx.data
    d['cmd'] = 'qt' + secrets.token_hex(2)
    roles = {'1': 'ユーザーコマンド', '5': 'ファイル形式', '8': '管理コマンド'}
    k = secrets.choice(list(roles))
    d['sec'] = k
    d['role'] = roles[k]
    desc = {'1': 'run the tool', '5': 'configuration file format', '8': 'system administration daemon'}
    put(ctx, 'whatis.txt', f'$ whatis {d["cmd"]}\n' + ''.join(f'{d["cmd"]} ({s}){" " * 4}- {desc[s]}\n' for s in ('1', '5', '8')))
    d['kw'] = secrets.choice(['network', 'filesystem', 'journal', 'mount'])
    ctx.write('requirements.txt', f'answer.json: {{"section": whatis.txt で {d["role"]} にあたるセクション番号}}\n'
              f'cmds.txt に5行: (1) インデックス(whatis DB)を静かに(-q)再構築する mandb (2) セクション8だけを対象に {d["kw"]} を検索する apropos (-s 8) (3) man の検索パスを表示する manpath (4) インデックスの中身を表示する accessdb (5) cat用ページを事前生成する catman\n')


def c17(ctx):
    need_ro(ctx)
    jcheck(ctx, {'section': 'sec'})
    ls = cl(ctx, 'cmds.txt')
    ctx.require(len(ls) == 5, '5行書きます。')
    m = first(ctx, ls, 'mandb')
    ctx.require('-q' in m or '--quiet' in m, 'mandb -q です。')
    a = first(ctx, ls, 'apropos')
    ctx.require(opt(a, '-s', '--sections') == '8' and ctx.data['kw'] in a, f'apropos -s 8 {ctx.data["kw"]} です。')
    for c in ('manpath', 'accessdb', 'catman'):
        first(ctx, ls, c)


mission(17, 'mandb・whatis・apropos・manpath・accessdb・catmanで索引を扱う',
        'manの検索はインデックスに依存します。mandb がDBを作り、whatis は名前の一行説明、apropos はキーワード検索、manpath は検索パス、accessdb はDBの内容ダンプ、catman は表示済み形式(cat)ページの事前生成です。whatis.txtを読み、5つの操作コマンドを書いてください。',
        ['セクションを特定', '5コマンドをcmds.txtへ'], s17, c17,
        "s=$(grep \"(\" whatis.txt | awk '/<<role>>/{print $2}')\n"
        "echo '{\"section\":\"<<sec>>\"}' > answer.json\nprintf '%s\\n' 'mandb -q' 'apropos -s 8 <<kw>>' 'manpath' 'accessdb' 'catman' > cmds.txt",
        ["echo '{\"section\":\"1\"}' > answer.json\nprintf '%s\\n' 'mandb' 'apropos <<kw>>' 'manpath' 'accessdb' 'catman' > cmds.txt",
         "echo '{\"section\":\"<<sec>>\"}' > answer.json\nprintf '%s\\n' 'mandb -q' 'whatis -s 8 <<kw>>' 'manpath' 'accessdb' 'catman' > cmds.txt"],
        'セクション1=コマンド、5=ファイル形式、8=管理コマンドです。新しいmanページを入れたら mandb でDBを更新しないと apropos/whatis に出ません。accessdb は索引の確認、catman は事前整形でページ表示を高速化します。',
        'セクション番号は括弧の中です。', 'apropos -s 8 キーワード を使います。')


# ---------------------------------------------------------------- 18
def s18(ctx):
    d = ctx.data
    d['tag'] = 'tl' + secrets.token_hex(2)
    d['desc'] = f'{secrets.choice(["sync", "audit", "rotate", "probe"])} {secrets.choice(["files", "logs", "disks", "hosts"])}'
    d['bin'] = f'/usr/local/bin/{d["tag"]}'
    put(ctx, 'lexgrog.txt', f'$ lexgrog /usr/share/man/man1/{d["tag"]}.1.gz\n/usr/share/man/man1/{d["tag"]}.1.gz: "{d["tag"]} - {d["desc"]}"\n')
    put(ctx, 'whereis.txt', f'$ whereis {d["tag"]}\n{d["tag"]}: {d["bin"]} /usr/share/man/man1/{d["tag"]}.1.gz\n')
    ctx.write(f'{d["tag"]}.ja.1', 'EUC-JPのmanページ(偽物)\n')
    ctx.data.setdefault('ro', {})[f'{d["tag"]}.ja.1'] = sha(ctx.read(f'{d["tag"]}.ja.1'))
    ctx.write('requirements.txt', 'answer.json: {"desc": lexgrog.txtの説明部分(" - "の後ろ), "bin": whereis.txtの実行ファイルパス, '
              '"flags": オプション一覧をざっと見たいときの手段, "full": 完全な参考資料を読むとき, "gnu": GNUのリンク付きマニュアルを読むとき, "examples": 実用例だけを短く見たいとき(コミュニティ版)}\n'
              '  flags/full/gnu/examples の値は --help, man, info, tldr のどれか。\n'
              f'recode.txt: 文字コードがEUC-JPの {d["tag"]}.ja.1 をUTF-8に変換する man-recode の1行(-t)\n')


def c18(ctx):
    need_ro(ctx)
    d = ctx.data
    d['flg'], d['ful'], d['gnu'], d['ex'] = '--help', 'man', 'info', 'tldr'
    jcheck(ctx, {'desc': 'desc', 'bin': 'bin', 'flags': 'flg', 'full': 'ful', 'gnu': 'gnu', 'examples': 'ex'})
    t = tk1(ctx, 'recode.txt')
    ctx.require(t[0] == 'man-recode' and (opt(t, '-t', '--to-code') or '').upper() == 'UTF-8' and f'{d["tag"]}.ja.1' in t, 'man-recode -t UTF-8 ファイル です。')


mission(18, 'lexgrog・man-recode・whereis・man・info・--help・tldrの調べ方',
        '調べ物は目的に合う手段を選びます。lexgrog はmanページの名前と説明を取り出し、whereis は実行ファイルとmanの場所を示し、man-recode はmanページの文字コードを変換します。素早い概要は --help、完全な資料は man、GNU製ツールの詳細は info、実例は tldr です。記録を読んで答えてください。',
        ['記録から説明とパスを抽出', '調べ方を選ぶ', 'man-recodeを書く'], s18, c18,
        "d=$(sed -n 's/.*\"[^ ]* - \\(.*\\)\"$/\\1/p' lexgrog.txt)\nb=$(awk 'NR==2{print $2}' whereis.txt)\n"
        "echo \"{\\\"desc\\\":\\\"$d\\\",\\\"bin\\\":\\\"$b\\\",\\\"flags\\\":\\\"--help\\\",\\\"full\\\":\\\"man\\\",\\\"gnu\\\":\\\"info\\\",\\\"examples\\\":\\\"tldr\\\"}\" > answer.json\necho 'man-recode -t UTF-8 <<tag>>.ja.1' > recode.txt",
        ["echo '{\"desc\":\"x\",\"bin\":\"y\",\"flags\":\"man\",\"full\":\"--help\",\"gnu\":\"tldr\",\"examples\":\"info\"}' > answer.json\necho 'iconv <<tag>>.ja.1' > recode.txt",
         "d=$(sed -n 's/.*\"[^ ]* - \\(.*\\)\"$/\\1/p' lexgrog.txt)\nb=$(awk 'NR==2{print $2}' whereis.txt)\necho \"{\\\"desc\\\":\\\"$d\\\",\\\"bin\\\":\\\"$b\\\",\\\"flags\\\":\\\"man\\\",\\\"full\\\":\\\"man\\\",\\\"gnu\\\":\\\"info\\\",\\\"examples\\\":\\\"tldr\\\"}\" > answer.json\necho 'man-recode -t UTF-8 <<tag>>.ja.1' > recode.txt"],
        'whereisは固定の標準場所を探します(PATH全体ならwhich/type -a)。--helpは軽量、manは完全版、infoは階層化したGNU資料、tldrは主な用例だけを短く示すコミュニティ製ツールで、実行環境にないこともあります。man-recode -t は変換後の文字コードです。',
        '目的の粒度(概要/完全/GNU詳細/実例)で選びます。', 'sedで引用符内の説明を取り出します。')


# ---------------------------------------------------------------- 19
def s19(ctx):
    d = ctx.data
    d['net'] = f'10.{1 + secrets.randbelow(200)}.{secrets.randbelow(250)}'
    d['app'] = 'app' + secrets.token_hex(2)
    d['lib'] = 'libx' + secrets.token_hex(2)
    ctx.write('etc/hosts.allow', '# TCP Wrappers 許可リスト\n')
    ctx.write('etc/hosts.deny', '# TCP Wrappers 拒否リスト\n')
    put(ctx, 'etc/ld.so.conf', 'include /etc/ld.so.conf.d/*.conf\n')
    ctx.mkdir('etc/ld.so.conf.d')
    ctx.write(f'opt/{d["app"]}/lib/{d["lib"]}.so.1', 'ELF風の偽ライブラリ\n')
    put(ctx, 'ldcache.txt', '$ ldconfig -p | grep ' + d['lib'] + '\n(出力なし = キャッシュに無い)\n')
    ctx.write('requirements.txt', f'etc/hosts.allow: sshd を {d["net"]}. (先頭一致の書式) からだけ許可。etc/hosts.deny: それ以外は全面拒否(ALL: ALL)。\n'
              f'/opt/{d["app"]}/lib の {d["lib"]}.so.1 がリンカに見つからない。etc/ld.so.conf.d/{d["app"]}.conf にそのディレクトリを追加し、'
              'reload.txt に キャッシュを再構築する ldconfig の1行(確認用の-pは使わない)を書く。\n')


def c19(ctx):
    need_ro(ctx)
    d = ctx.data
    allow = [re.sub(r'\s+', ' ', x) for x in cl(ctx, 'etc/hosts.allow')]
    ctx.require(allow == [f'sshd: {d["net"]}.'] or allow == [f'sshd : {d["net"]}.'], 'hosts.allowは sshd: ネットワーク. の1行です。')
    deny = [re.sub(r'\s+', '', x) for x in cl(ctx, 'etc/hosts.deny')]
    ctx.require(deny == ['ALL:ALL'], 'hosts.denyは ALL: ALL です。')
    ctx.require(f'/opt/{d["app"]}/lib' in [x.strip() for x in ctx.need_file(f'etc/ld.so.conf.d/{d["app"]}.conf').splitlines()], 'ld.so.conf.d の設定にディレクトリを書きます。')
    t = tk1(ctx, 'reload.txt')
    ctx.require(t[0] == 'ldconfig' and '-p' not in t and '--print-cache' not in t, 'キャッシュ再構築は引数なしの ldconfig(必要なら -v)です。')


mission(19, 'hosts.allow・hosts.deny・ld.so.conf・ldconfigを設定する',
        'TCP Wrappers は /etc/hosts.allow を先に、次に /etc/hosts.deny を見て許可・拒否を決めます。共有ライブラリは /etc/ld.so.conf (とld.so.conf.d)で探索ディレクトリを増やし、ldconfig でキャッシュを更新します。requirements.txtのとおりに設定してください(実OSでは行いません)。',
        ['hosts.allow/hosts.denyを書く', 'ld.so.conf.dを追加しldconfigを書く'], s19, c19,
        "echo 'sshd: <<net>>.' >> etc/hosts.allow\necho 'ALL: ALL' >> etc/hosts.deny\necho '/opt/<<app>>/lib' > etc/ld.so.conf.d/<<app>>.conf\necho 'ldconfig' > reload.txt",
        ["echo 'ALL: ALL' >> etc/hosts.allow\necho 'sshd: <<net>>.' >> etc/hosts.deny\necho '/opt/<<app>>/lib' > etc/ld.so.conf.d/<<app>>.conf\necho 'ldconfig -p' > reload.txt",
         "echo 'sshd: <<net>>.' >> etc/hosts.allow\necho 'ALL: ALL' >> etc/hosts.deny\necho 'opt/<<app>>/lib' > etc/ld.so.conf.d/<<app>>.conf\necho 'ldconfig' > reload.txt"],
        'allowが先に評価され、一致すれば許可、次にdenyが一致すれば拒否、どちらにも無ければ許可です。末尾のドットはネットワーク先頭一致を表します。現代の多くのsshdはlibwrapを使わないので実機では対応状況を確認します。ldconfig -p は表示だけでキャッシュは更新しません。',
        'allow(例外)とdeny(既定)を分けます。', 'echo で追記し、ld.so.conf.d にフルパスを書きます。')


# ---------------------------------------------------------------- 20
def s20(ctx):
    d = ctx.data
    d['job'] = 'job' + secrets.token_hex(2)
    d['n'] = str(5 * (1 + secrets.randbelow(11)))
    d['m'], d['h'] = str(secrets.randbelow(60)), str(secrets.randbelow(24))
    d['k'] = str(2 + secrets.randbelow(12))
    ctx.mkdir('etc/cron.d')
    ctx.mkdir('etc/logrotate.d')
    ctx.mkdir('etc/xdg/autostart')
    ctx.mkdir('var/spool/cron/crontabs')
    ctx.write('requirements.txt', f'4つの設定を、それぞれ正しい書式でサンドボックス内に作る。ジョブは /opt/{d["job"]}/run.sh。\n'
              f'1) etc/cron.d/{d["job"]}: {d["n"]}分ごと(*/{d["n"]})に root で実行（cron.dはユーザー欄あり）\n'
              f'2) var/spool/cron/crontabs/trainee: 毎日 {d["h"]}時{d["m"]}分に実行（ユーザー欄なし。/var/spool/cron の利用者別crontab）\n'
              f'3) etc/logrotate.d/{d["job"]}: /var/log/{d["job"]}/*.log を weekly, rotate {d["k"]}, compress, missingok\n'
              f'4) etc/xdg/autostart/{d["job"]}.desktop: ログイン時自動起動(/etc/xdg)。[Desktop Entry] に Type=Application, Name={d["job"]}, Exec=/opt/{d["job"]}/run.sh\n')


def c20(ctx):
    d = ctx.data
    run = f'/opt/{d["job"]}/run.sh'
    ok = False
    for x in cl(ctx, f'etc/cron.d/{d["job"]}'):
        f = x.split(None, 6)
        if len(f) == 7 and f[:5] == [f'*/{d["n"]}', '*', '*', '*', '*'] and f[5] == 'root' and f[6] == run:
            ok = True
    ctx.require(ok, 'cron.d は「*/N * * * * root コマンド」の形です。')
    ok = False
    for x in cl(ctx, 'var/spool/cron/crontabs/trainee'):
        f = x.split(None, 5)
        if len(f) == 6 and f[:5] == [d['m'], d['h'], '*', '*', '*'] and f[5] == run:
            ok = True
    ctx.require(ok, 'ユーザーcrontabは「分 時 * * * コマンド」でユーザー欄がありません。')
    lr = ctx.need_file(f'etc/logrotate.d/{d["job"]}')
    ctx.require(re.search(r'^\s*/var/log/' + d['job'] + r'/\*\.log\s*\{', lr, re.M) and re.search(r'^\s*weekly\s*$', lr, re.M) and re.search(rf'^\s*rotate\s+{d["k"]}\s*$', lr, re.M)
                and re.search(r'^\s*compress\s*$', lr, re.M) and re.search(r'^\s*missingok\s*$', lr, re.M) and '}' in lr, 'logrotate の書式(パス { 指示... })を確認します。')
    kv = {}
    sec = ''
    for x in ctx.need_file(f'etc/xdg/autostart/{d["job"]}.desktop').splitlines():
        x = x.strip()
        if x.startswith('['):
            sec = x
        elif '=' in x and sec == '[Desktop Entry]':
            a, b = x.split('=', 1)
            kv[a] = b
    ctx.require(kv.get('Type') == 'Application' and kv.get('Name') == d['job'] and kv.get('Exec') == run, '.desktopは [Desktop Entry] 内に Type/Name/Exec を書きます。')


mission(20, '/etc/cron.d・logrotate.d・xdg・/var/spool/cronの書式',
        'ジョブや自動起動の設定は置き場所ごとに書式が違います。/etc/cron.d は「分 時 日 月 曜 ユーザー コマンド」、/var/spool/cron の利用者別crontabはユーザー欄なし、/etc/logrotate.d は「パス { 指示 }」、/etc/xdg/autostart は .desktop 形式です。それぞれサンドボックス内に正しく作ってください。',
        ['4つの設定ファイルを作る'], s20, c20,
        "printf '%s\\n' '*/<<n>> * * * * root /opt/<<job>>/run.sh' > etc/cron.d/<<job>>\nprintf '%s\\n' '<<m>> <<h>> * * * /opt/<<job>>/run.sh' > var/spool/cron/crontabs/trainee\n"
        "printf '%s\\n' '/var/log/<<job>>/*.log {' '    weekly' '    rotate <<k>>' '    compress' '    missingok' '}' > etc/logrotate.d/<<job>>\n"
        "printf '%s\\n' '[Desktop Entry]' 'Type=Application' 'Name=<<job>>' 'Exec=/opt/<<job>>/run.sh' > etc/xdg/autostart/<<job>>.desktop",
        ["printf '%s\\n' '*/<<n>> * * * * /opt/<<job>>/run.sh' > etc/cron.d/<<job>>\nprintf '%s\\n' '<<m>> <<h>> * * * root /opt/<<job>>/run.sh' > var/spool/cron/crontabs/trainee\n"
         "printf '%s\\n' '/var/log/<<job>>/*.log {' '    weekly' '    rotate <<k>>' '    compress' '    missingok' '}' > etc/logrotate.d/<<job>>\nprintf '%s\\n' 'Exec=/opt/<<job>>/run.sh' > etc/xdg/autostart/<<job>>.desktop",
         "printf '%s\\n' '*/<<n>> * * * * root /opt/<<job>>/run.sh' > etc/cron.d/<<job>>\nprintf '%s\\n' '<<m>> <<h>> * * * /opt/<<job>>/run.sh' > var/spool/cron/crontabs/trainee\n"
         "printf '%s\\n' '/var/log/<<job>>/*.log' '    weekly' '    rotate <<k>>' > etc/logrotate.d/<<job>>\nprintf '%s\\n' '[Desktop Entry]' 'Type=Application' 'Name=<<job>>' 'Exec=/opt/<<job>>/run.sh' > etc/xdg/autostart/<<job>>.desktop"],
        'cron.dにユーザー欄が必要なのは、特定ユーザーの所有でない「システムのcron」だからです。/var/spool/cron は crontab -e が管理するファイルで、直接編集は避けます。logrotateは設定を /etc/logrotate.conf から include し、xdg/autostart はデスクトップ環境が起動時に読みます。',
        '置き場所ごとにユーザー欄の有無などが違います。', 'printfで1行ずつ書きます。')


# ---------------------------------------------------------------- 21
def s21(ctx):
    d = ctx.data
    delays = [secrets.randbelow(30) + 1 for _ in range(8 + secrets.randbelow(5))]
    sizes = [secrets.randbelow(40) + 1 for _ in delays]
    d['tot'] = '%.1f' % (sum(delays) / 10)
    d['div'] = str(2 + secrets.randbelow(4))
    put(ctx, 'session.tm', ''.join(f'{a // 10}.{a % 10} {b}\n' for a, b in zip(delays, sizes)))
    ctx.write('requirements.txt', f'session.tm は script が記録したタイミングファイル(各行: 待ち時間(秒) 出力バイト数)。\nanswer.json: {{"total_sec": 待ち時間の合計(小数1桁)}}\n'
              'record.txt: タイミングを session.tm、出力を session.log に記録して静かに(-q)端末を記録する script の1行(--log-timing, --log-out)\n'
              f'replay.txt: 同じ記録を {d["div"]} 倍速で再生する scriptreplay の1行(--timing, --typescript, --divisor)\n'
              'live.txt: 記録した入力をその場のシェルへ流し込み再実行する scriptlive の1行(--timing session.tm と session.log を使う)\n')


def c21(ctx):
    need_ro(ctx)
    jcheck(ctx, {'total_sec': 'tot'})
    r = tk1(ctx, 'record.txt')
    ctx.require(r[0] == 'script' and ('-q' in r or '--quiet' in r) and opt(r, '-T', '--log-timing') == 'session.tm' and opt(r, '-O', '--log-out') == 'session.log', 'script -q --log-timing session.tm --log-out session.log です。')
    p = tk1(ctx, 'replay.txt')
    ctx.require(p[0] == 'scriptreplay' and opt(p, '-t', '--timing', '-T', '--log-timing') == 'session.tm' and 'session.log' in p and opt(p, '-d', '--divisor') == ctx.data['div'], 'scriptreplay --timing session.tm --typescript session.log --divisor 倍率 です。')
    v = tk1(ctx, 'live.txt')
    ctx.require(v[0] == 'scriptlive' and 'session.tm' in v and 'session.log' in v, 'scriptlive --timing session.tm session.log を指定します。')


mission(21, 'script・scriptreplay・scriptliveで端末操作を記録・再生する',
        '手順書や障害対応の証跡は script で端末を記録します。--log-timing でタイミング、--log-out で出力を別ファイルに残すと、scriptreplay が時間どおり(--divisorで倍速)に再生でき、scriptlive は記録した入力を実際のシェルで再実行します。session.tmを集計し、3つのコマンドを書いてください。',
        ['待ち時間を合計', 'script/scriptreplay/scriptliveの行を書く'], s21, c21,
        "t=$(awk '{s+=$1} END{printf \"%.1f\", s}' session.tm)\necho \"{\\\"total_sec\\\":\\\"$t\\\"}\" > answer.json\necho 'script -q --log-timing session.tm --log-out session.log' > record.txt\n"
        "echo 'scriptreplay --timing session.tm --typescript session.log --divisor <<div>>' > replay.txt\necho 'scriptlive --timing session.tm session.log' > live.txt",
        ["echo '{\"total_sec\":\"0.0\"}' > answer.json\necho 'script session.log' > record.txt\necho 'scriptreplay session.log' > replay.txt\necho 'scriptlive session.log' > live.txt",
         "t=$(awk '{s+=$2} END{printf \"%.1f\", s}' session.tm)\necho \"{\\\"total_sec\\\":\\\"$t\\\"}\" > answer.json\necho 'script -q --log-timing session.tm --log-out session.log' > record.txt\necho 'scriptreplay --timing session.tm --typescript session.log --divisor <<div>>' > replay.txt\necho 'scriptlive --timing session.tm session.log' > live.txt"],
        'timingファイルは「前の出力からの待ち時間 バイト数」の繰り返しで、第1列の合計が総時間です。scriptlive は入力側の記録を使い、実機で動かす前に内容を必ず確認します。パスワード入力などが記録に残る点にも注意が必要です。',
        '第1列が待ち時間、第2列がバイト数。', 'awkで第1列を合計します。')


# ---------------------------------------------------------------- 22
def s22(ctx):
    d = ctx.data
    R = secrets.SystemRandom()
    names = [f'vol_{secrets.token_hex(2)}.tar' for _ in range(3)]
    d['parts'] = ' '.join(names)
    d['user'] = 'bk' + secrets.token_hex(1)
    d['host'] = f'tape-{secrets.token_hex(2)}.example.test'
    d['rpath'] = f'/backup/{secrets.token_hex(2)}.tar'
    put(ctx, 'order.txt', ''.join(n + '\n' for n in names))
    ctx.write('requirements.txt', f'rmt.txt: tar で data/ を {d["user"]}@{d["host"]}:{d["rpath"]} へ作成(-c, -f)し、リモート側のrmtに /usr/sbin/rmt-tar を使い(--rmt-command)、接続は /usr/bin/ssh(--rsh-command)にする1行\n'
              'cat.txt: order.txt の順序で並べた3つのテープ部品を tarcat で連結し merged.tar へリダイレクトする1行\n')


def c22(ctx):
    need_ro(ctx)
    d = ctx.data
    t = tk1(ctx, 'rmt.txt')
    remote = f'{d["user"]}@{d["host"]}:{d["rpath"]}'
    cf = any(x.startswith('-') and not x.startswith('--') and 'c' in x and 'f' in x for x in t) or ('--create' in t and ('-f' in t or '--file' in t))
    ctx.require(t[0] == 'tar' and cf and remote in t and 'data' in [x.rstrip('/') for x in t] and opt(t, '--rmt-command') == '/usr/sbin/rmt-tar' and opt(t, '--rsh-command') == '/usr/bin/ssh', 'tar --rmt-command=/usr/sbin/rmt-tar --rsh-command=/usr/bin/ssh -cf user@host:path data です。')
    c = tk1(ctx, 'cat.txt')
    ctx.require(c[0] == 'tarcat' and c[-2:] == ['>', 'merged.tar'] and c[1:-2] == d['parts'].split(), 'tarcat 部品(order.txtの順) > merged.tar です。')


mission(22, 'rmt-tarとtarcatでテープ形式のバックアップを扱う',
        'tar は host:path 形式でリモートのテープ装置やファイルへ書けます。リモート側の受け口が rmt で、Debian系の実体は rmt-tar です。複数テープ(ボリューム)に分かれたアーカイブは tarcat で連結します。要件のコマンドを書いてください。',
        ['rmt-tarを指定したtarコマンド', 'order.txtの順にtarcat'], s22, c22,
        "echo 'tar --rmt-command=/usr/sbin/rmt-tar --rsh-command=/usr/bin/ssh -cf <<user>>@<<host>>:<<rpath>> data' > rmt.txt\necho 'tarcat <<parts>> > merged.tar' > cat.txt",
        ["echo 'tar -cf <<user>>@<<host>>:<<rpath>> data' > rmt.txt\necho 'cat <<parts>> > merged.tar' > cat.txt",
         "echo 'tar --rmt-command=/usr/sbin/rmt-tar --rsh-command=/usr/bin/ssh -cf <<user>>@<<host>>:<<rpath>> data' > rmt.txt\necho 'tarcat '$(tac order.txt | tr '\\n' ' ')'> merged.tar' > cat.txt"],
        'host:path はtarが自動で遠隔指定と解釈します。--rsh-commandで通信手段、--rmt-commandでリモートの受け口を指定します。tarcatは各部品の終端ブロックを考慮して正しい1本のtarにするため、単純なcatと違います。順序を間違えると展開できません。',
        '遠隔指定の形は user@host:path。', 'order.txtの順に並べます。')


# ---------------------------------------------------------------- 23
def s23(ctx):
    d = ctx.data
    for k in 'abcdefg':
        d[k] = 'x' + secrets.token_hex(3)
    ctx.mkdir('root')
    ctx.write('inventory.txt', f"""root/ を仮のルートとして、次を正しいFHSの場所に作成する（ファイルは空でよい、ディレクトリ指定のものはディレクトリ）。
1. 自分でコンパイルした実行ファイル {d['a']}                       -> ローカル管理者のコマンド置き場
2. ベンダー配布の自己完結ソフト {d['b']}（実行物は bin/run）        -> /opt 配下のパッケージごとのディレクトリ
3. HTTPで配信するサイトの {d['c']}/index.html                       -> /srv 配下のサービス用データ(www/ 以下)
4. 管理者が手動で一時マウントする空の接続先 {d['d']}                -> 一時マウント用(ディレクトリ)
5. 自動マウントされる取り外しメディア(ユーザー trainee, ラベル {d['e']}) -> ディレクトリ
6. デーモン {d['f']} の実行中PIDファイル {d['f']}.pid               -> 実行時データ
7. アプリ {d['g']} が保存する永続状態 state.db                      -> /var/lib 配下のアプリ別ディレクトリ
8. 再起動で消えてもよい作業用の一時ファイル {d['a']}.tmp           -> 一時領域
場所の候補: /usr/local /opt /srv /mnt /media /run /var/lib /tmp
""")
    ctx.data.setdefault('ro', {})['inventory.txt'] = sha(ctx.read('inventory.txt'))


def c23(ctx):
    need_ro(ctx)
    d = ctx.data
    files = {f'usr/local/bin/{d["a"]}', f'opt/{d["b"]}/bin/run', f'srv/www/{d["c"]}/index.html', f'run/{d["f"]}.pid',
             f'var/lib/{d["g"]}/state.db', f'tmp/{d["a"]}.tmp'}
    dirs = [f'mnt/{d["d"]}', f'media/trainee/{d["e"]}']
    root = ctx.p('root')
    got = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    for f in sorted(files):
        ctx.require(f in got, f'root/{f} がありません。')
    ctx.require(got == files, 'FHSに合わない場所に余計なファイルがあります: ' + ', '.join(sorted(got - files)))
    for x in dirs:
        ctx.require((root / x).is_dir(), f'root/{x} はディレクトリで作ります。')


mission(23, 'FHSのディレクトリ配置(/usr/local /opt /srv /mnt /media /run /var/lib /tmp)',
        'FHS(ファイル階層標準)は置き場所の約束です。自前ビルドは /usr/local、自己完結の外部ソフトは /opt、サービスの配信データは /srv、手動の一時マウントは /mnt、自動マウントの取り外しメディアは /media、実行時のPIDやソケットは /run、アプリの永続状態は /var/lib、一時ファイルは /tmp です。inventory.txtを読み、root/ 以下へ実際に配置してください。',
        ['8項目を正しい場所へ作成', '余計な場所に置かない'], s23, c23,
        "mkdir -p root/usr/local/bin root/opt/<<b>>/bin root/srv/www/<<c>> root/mnt/<<d>> root/media/trainee/<<e>> root/run root/var/lib/<<g>> root/tmp\n"
        "touch root/usr/local/bin/<<a>> root/opt/<<b>>/bin/run root/srv/www/<<c>>/index.html root/run/<<f>>.pid root/var/lib/<<g>>/state.db root/tmp/<<a>>.tmp",
        ["mkdir -p root/usr/bin root/opt/<<b>>/bin root/srv/<<c>> root/mnt/<<d>> root/media/trainee/<<e>> root/run root/var/lib/<<g>> root/var/tmp\n"
         "touch root/usr/bin/<<a>> root/opt/<<b>>/bin/run root/srv/<<c>>/index.html root/run/<<f>>.pid root/var/lib/<<g>>/state.db root/var/tmp/<<a>>.tmp",
         "mkdir -p root/usr/local/bin root/opt/<<b>>/bin root/srv/www/<<c>> root/media/<<d>> root/mnt/trainee/<<e>> root/run root/var/lib/<<g>> root/tmp\n"
         "touch root/usr/local/bin/<<a>> root/opt/<<b>>/bin/run root/srv/www/<<c>>/index.html root/run/<<f>>.pid root/var/lib/<<g>>/state.db root/tmp/<<a>>.tmp"],
        '/usr/binはディストリビューションのパッケージ用で、自前物は /usr/local に分けて更新で上書きされないようにします。/runは再起動で消える実行時データ、/var/libは消えない状態、/tmpは一時用です。/mntは管理者の手動マウント、/mediaは自動マウント向けです。',
        '「誰が管理するか」「消えてよいか」で分けます。', 'mkdir -p と touch で作成します。')


# ---------------------------------------------------------------- 24
def s24(ctx):
    d = ctx.data
    drift = 5 + secrets.randbelow(200)
    sys_e = 1790000000 + secrets.randbelow(9999999)
    d['drift'] = str(drift)
    d['rtc'] = secrets.choice(['rtc_cmos', 'rtc-ds1307', 'rtc-pcf8563'])
    d['host'] = f'time-{secrets.token_hex(2)}.example.test'
    put(ctx, 'rtc.txt', f'$ grep -r . /sys/class/rtc/rtc0/name /sys/class/rtc/rtc0/since_epoch\n/sys/class/rtc/rtc0/name:{d["rtc"]}\n/sys/class/rtc/rtc0/since_epoch:{sys_e - drift}\n')
    put(ctx, 'sysdate.txt', f'$ date +%s\n{sys_e}\n')
    ctx.write('requirements.txt', 'rtc.txt は /sys/class/rtc/rtc0 (RTC=ハードウェア時計)の値、sysdate.txt は同時刻のシステム時計(エポック秒)。\n'
              'answer.json: {"drift_sec": システム時計 - RTC (秒), "rtc_name": RTCの名前}\n'
              f'cmds.txt に4行: (1) {d["host"]} の時刻を設定せず表示だけする rdate (-p) (2) 同ホストの時刻でシステム時計を設定する rdate (-s) '
              '(3) システム時計をUTCのままRTCへ書き込む hwclock (--systohc --utc) (4) /dev/rtc0 のRTC値を読み取って表示する hwclock (--show --rtc)\n')


def c24(ctx):
    need_ro(ctx)
    d = ctx.data
    jcheck(ctx, {'drift_sec': 'drift', 'rtc_name': 'rtc'})
    ls = cl(ctx, 'cmds.txt')
    ctx.require(len(ls) == 4, '4行書きます。')
    ts = [toks(ctx, x) for x in ls]
    rd = [t for t in ts if t[0] == 'rdate']
    ctx.require(len(rd) == 2, 'rdateは2行です。')
    ctx.require(any('-p' in t and '-s' not in t and t[-1] == d['host'] for t in rd), 'rdate -p ホスト は表示のみです。')
    ctx.require(any('-s' in t and '-p' not in t and t[-1] == d['host'] for t in rd), 'rdate -s ホスト で設定します。')
    hw = [t for t in ts if t[0] == 'hwclock']
    ctx.require(len(hw) == 2, 'hwclockは2行です。')
    ctx.require(any(('--systohc' in t or '-w' in t) and ('--utc' in t or '-u' in t) for t in hw), 'hwclock --systohc --utc です。')
    ctx.require(any(('--show' in t or '-r' in t) and opt(t, '--rtc') == '/dev/rtc0' for t in hw), 'hwclock --show --rtc=/dev/rtc0 です。')


mission(24, 'hwclock・rtc・rdateで時刻のずれを診断する',
        'PCには2つの時計があります。電池で動くハードウェア時計(RTC, /sys/class/rtc/rtc0 や /dev/rtc0)と、OSのシステム時計です。hwclock は両者を読み書きし(--systohc / --hctosys)、rdate はネットワーク上のホストから時刻を取得します(-p で表示、-s で設定)。記録からずれを求め、操作コマンドを書いてください。',
        ['ずれを計算', 'rdate/hwclockの4行を書く'], s24, c24,
        "r=$(awk -F: '/^.sys.*since_epoch/{print $NF}' rtc.txt)\ns=$(awk 'NR==2' sysdate.txt)\nn=$(awk -F: '/^.sys.*name:/{print $NF}' rtc.txt)\n"
        "echo \"{\\\"drift_sec\\\":\\\"$((s-r))\\\",\\\"rtc_name\\\":\\\"$n\\\"}\" > answer.json\nprintf '%s\\n' 'rdate -p <<host>>' 'rdate -s <<host>>' 'hwclock --systohc --utc' 'hwclock --show --rtc=/dev/rtc0' > cmds.txt",
        ["echo '{\"drift_sec\":\"0\",\"rtc_name\":\"rtc0\"}' > answer.json\nprintf '%s\\n' 'rdate <<host>>' 'rdate <<host>>' 'hwclock' 'hwclock' > cmds.txt",
         "echo '{\"drift_sec\":\"-<<drift>>\",\"rtc_name\":\"<<rtc>>\"}' > answer.json\nprintf '%s\\n' 'rdate -p <<host>>' 'rdate -s <<host>>' 'hwclock --systohc --utc' 'hwclock --show --rtc=/dev/rtc0' > cmds.txt"],
        'RTCはUTCで保持するのが一般的で、ローカル時刻にするとサマータイムや複数OSで混乱します。hwclock --systohc はシステム→RTC、--hctosys は RTC→システムです。rdate -p でまず確認してから -s で設定するのが安全で、通常はchronyやsystemd-timesyncdで同期します。',
        'ずれは システム - RTC で、RTCの値は since_epoch です。', 'awkでエポック秒を取り、$(( )) で引き算します。')
