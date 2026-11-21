"""Stage 21: DNS・DHCP・LDAP・メール・負荷分散・プロキシ。サンドボックス内の偽データと設定ファイルだけを使う。"""
import hashlib
import json
import re
import secrets
import shlex
import datetime

from engine.runner import register

S = 21
NOTE = ("作業対象はこの課題のフォルダだけです。実OSのサービス・DNS・メール・ネットワークは変更せず、rootも使いません。"
        "データは訓練用の偽物で、実行環境にないサーバー系ツールは設定ファイルや採取済みの出力から読み解きます。")


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


def opt(t, flag):
    """flag の次のトークン（なければ None）。"""
    return t[t.index(flag) + 1] if flag in t and t.index(flag) + 1 < len(t) else None


def lines_of(text, marks=('#',)):
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s and not any(s.startswith(m) for m in marks):
            out.append(s)
    return out


def block(text, pat):
    m = re.search(pat, text)
    if not m:
        return None
    i = j = m.end()
    depth = 1
    while j < len(text) and depth:
        depth += (text[j] == '{') - (text[j] == '}')
        j += 1
    return text[i:j - 1] if depth == 0 else None


def kv(text, sep=r'\s*=\s*'):
    d = {}
    for s in lines_of(text):
        m = re.match(r'([A-Za-z_][\w.-]*)' + sep + r'(.*)$', s)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def keep_orig(ctx, name, orig_name, skip=()):
    have = set(x.strip() for x in ctx.need_file(name).splitlines())
    for ln in ctx.need_file(orig_name).splitlines():
        if ln.strip() and not any(k in ln for k in skip):
            ctx.require(ln.strip() in have, f'{name} の元の行「{ln.strip()}」を消さずに残します。')


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'21-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='設定を変えたら必ず構文チェックのコマンド（named-checkconf・haproxy -c・nginx -t など）を通し、原本は残して差分で確認する習慣をつけましょう。')


def dom():
    return 'corp-' + secrets.token_hex(2) + '.test'


# ---------------------------------------------------------------- 1 BIND named.conf
def s1(ctx):
    d, sec = dom(), f'192.0.2.{20 + secrets.randbelow(200)}'
    ctx.data.update(dom=d, sec=sec)
    orig = ('options {\n    directory "/var/cache/bind";\n    recursion no;\n    allow-query { any; };\n};\n\n'
            'zone "." {\n    type hint;\n    file "/usr/share/dns/root.hints";\n};\n')
    put(ctx, 'named.conf.orig', orig)
    ctx.write('named.conf', orig)
    ctx.write('requirements.txt', f'named.conf に権威ゾーン {d} を追加する。type master、ゾーンファイルは "/etc/bind/db.{d}"、ゾーン転送(allow-transfer)はセカンダリ {sec} だけに許可（any禁止）。元の設定は残す。構文確認のnamed-checkconfコマンドを1行でcmd.txtに書く（実行は不要）。\n')


def c1(ctx):
    need_ro(ctx)
    d, sec = ctx.data['dom'], ctx.data['sec']
    t = ctx.need_file('named.conf')
    keep_orig(ctx, 'named.conf', 'named.conf.orig')
    ctx.require(t.count('{') == t.count('}'), '波括弧の数が合っていません。')
    z = block(t, r'zone\s+"' + re.escape(d) + r'"\s*(?:IN\s*)?\{')
    ctx.require(z is not None, f'zone "{d}" {{ ... }}; ブロックを追加します。')
    ctx.require(re.search(r'type\s+(master|primary)\s*;', z), 'プライマリなので type master; にします。')
    ctx.require(re.search(r'file\s+"/etc/bind/db\.' + re.escape(d) + r'"\s*;', z), 'file にゾーンファイルのパスを指定します。')
    at = block(z, r'allow-transfer\s*\{')
    ctx.require(at is not None and sec in at and 'any' not in at, f'allow-transfer {{ {sec}; }}; だけに制限します。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[0] == 'named-checkconf' and 'named.conf' in t[1:], 'named-checkconf named.conf を書きます。')


SOL1 = """cat >> named.conf <<'EOF'
zone "<<dom>>" {
    type master;
    file "/etc/bind/db.<<dom>>";
    allow-transfer { <<sec>>; };
};
EOF
echo 'named-checkconf named.conf' > cmd.txt"""
mission(1, 'BIND named.confにゾーンを追加しnamed-checkconfで検査',
        'BINDのnamed.confに自社ドメインのゾーン定義を足します。requirements.txtを読み、zoneステートメント（type・file・allow-transfer）を追記して、反映前にnamed-checkconfで構文を確認するコマンドを用意してください。',
        ['named.confにzoneブロックを追記', 'named-checkconfのコマンドをcmd.txtへ'], s1, c1, SOL1,
        ["cat >> named.conf <<'EOF'\nzone \"<<dom>>\" {\n    type slave;\n    file \"/etc/bind/db.<<dom>>\";\n};\nEOF\necho 'named-checkconf named.conf' > cmd.txt",
         "cat >> named.conf <<'EOF'\nzone \"<<dom>>\" {\n    type master;\n    file \"/etc/bind/db.<<dom>>\";\n    allow-transfer { any; };\n};\nEOF\necho 'named-checkconf named.conf' > cmd.txt"],
        'named.confはoptions・zoneなどのステートメントを「;」で終えます。権威サーバーはtype master（新しい表記はprimary）でzoneファイルを読み、allow-transferを絞らないと全ゾーン情報が第三者に転送されます。named-checkconfはnamed.confの構文を、named-checkzoneはゾーンファイルを検査し、問題なければ何も出力せず終了コード0を返します。実際の反映はrndc reloadで行います。',
        'zoneブロックの中身はtype・file・allow-transferです。', '追記は cat >> と heredoc、検査コマンドは名前どおり named-checkconf です。')


# ---------------------------------------------------------------- 2 zone file / SOA / RR / TTL
def s2(ctx):
    d = dom()
    old = '20260311%02d' % (10 + secrets.randbelow(80))
    ips = ['198.51.100.%d' % x for x in secrets.SystemRandom().sample(range(10, 240), 3)]
    ctx.data.update(dom=d, old=old, new=str(int(old) + 1), ip1=ips[0], ip2=ips[1], ip3=ips[2])
    z = (f'$TTL 86400\n@   IN SOA ns1.{d}. hostmaster.{d}. (\n        {old} ; serial\n        3600 ; refresh\n'
         f'        900 ; retry\n        604800 ; expire\n        300 ) ; negative cache TTL\n    IN NS ns1.{d}.\n'
         'ns1 IN A 192.0.2.53\nwww IN A 192.0.2.80\n')
    put(ctx, 'db.orig', z)
    ctx.write('db.zone', z)
    ctx.write('requirements.txt', f'db.zone（ゾーン{d}）に、DNSラウンドロビンとして app を {" ".join(ips)} の3つのAレコードで登録する。切替に備えTTLはレコードに明示で60秒。SOAのシリアルを増やす（10桁 YYYYMMDDnn で現在より大きく）。既存レコードは残す。検査のnamed-checkzoneコマンドをcmd.txtに1行で書く。\n')


def c2(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('db.zone')
    keep_orig(ctx, 'db.zone', 'db.orig', skip=('serial',))
    m = re.search(r'(\d+)\s*;\s*serial', t)
    ctx.require(m and len(m.group(1)) == 10 and int(m.group(1)) > int(D['old']), 'SOAシリアルを現在より大きい10桁の値に増やします（変更時は必ず増やす）。')
    got = {}
    for ln in t.splitlines():
        f = ln.split(';')[0].split()
        if f and f[0] == 'app' and 'A' in f:
            ttl = f[1] if f[1].isdigit() else None
            ctx.require(ttl == '60', 'appのAレコードにはTTL 60を明示します（例: app 60 IN A ...）。')
            got[f[f.index('A') + 1]] = 1
    ctx.require(set(got) == {D['ip1'], D['ip2'], D['ip3']}, 'appに指定の3つのIPを1行ずつAレコードで登録します。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'named-checkzone' and D['dom'] in c and 'db.zone' in c, 'named-checkzone ゾーン名 db.zone を書きます。')


SOL2 = """sed -i 's/<<old>> ; serial/<<new>> ; serial/' db.zone
printf 'app 60 IN A %s\\n' <<ip1>> <<ip2>> <<ip3>> >> db.zone
echo 'named-checkzone <<dom>> db.zone' > cmd.txt"""
mission(2, 'ゾーンファイル・SOAシリアル・DNSラウンドロビンとTTL',
        'ゾーンファイルを更新します。同じ名前に複数のAレコードを並べるのがDNSラウンドロビンです。TTLが長いと切替が反映されないため短くします。SOAシリアルを上げ忘れるとセカンダリが更新を取りこみません。named-checkzoneで検査します。',
        ['SOAシリアルを増やす', 'ラウンドロビンのAレコード3つをTTL60で追加', 'named-checkzoneのコマンドをcmd.txtへ'], s2, c2, SOL2,
        ["printf 'app 60 IN A %s\\n' <<ip1>> <<ip2>> <<ip3>> >> db.zone\necho 'named-checkzone <<dom>> db.zone' > cmd.txt",
         "sed -i 's/<<old>> ; serial/<<new>> ; serial/' db.zone\nprintf 'app IN A %s\\n' <<ip1>> <<ip2>> <<ip3>> >> db.zone\necho 'named-checkzone <<dom>> db.zone' > cmd.txt"],
        'SOAのserialはゾーン更新の版番号で、プライマリの値がセカンダリより大きいときだけ転送が走ります（YYYYMMDDnn形式が慣例）。同名に複数のAレコードを置くとDNSラウンドロビンになり、順番を回して返しますが、障害ノードは除外されません。TTLはキャッシュ保持秒数で、移行前に下げておくと切替が早く浸透します。検査はnamed-checkzone ゾーン名 ファイルです。',
        '更新作業は3点セット（シリアル・レコード・検査）です。', 'sed -i でシリアル行を置換、printf で3行追記、検査コマンドを書きます。')


# ---------------------------------------------------------------- 3 dig
def s3(ctx):
    d = 'shop-' + secrets.token_hex(2) + '.test'
    h1, h2 = secrets.token_hex(2), secrets.token_hex(2)
    ns = f'ns-{h1}.dnsprov.net'
    ip, ttl = f'203.0.113.{10 + secrets.randbelow(200)}', secrets.choice([60, 120, 300, 600])
    signed = secrets.choice([True, False])
    ctx.data.update(dom=d, ns=ns)
    tr = (f'; <<>> DiG 9.18.24 <<>> +trace www.{d}\n;; global options: +cmd\n'
          '.                       518400  IN  NS  a.root-servers.net.\n.                       518400  IN  NS  b.root-servers.net.\n'
          ';; Received 811 bytes from 127.0.0.53#53(127.0.0.53) in 3 ms\n\n'
          'test.                   172800  IN  NS  a.nic.test.\ntest.                   172800  IN  NS  b.nic.test.\n'
          ';; Received 600 bytes from 198.41.0.4#53(a.root-servers.net) in 21 ms\n\n'
          f'{d}.         86400   IN  NS  {ns}.\n{d}.         86400   IN  NS  ns-{h2}.dnsprov.net.\n'
          ';; Received 200 bytes from 192.5.6.30#53(a.nic.test) in 30 ms\n\n'
          f'www.{d}.     {ttl}  IN  A   {ip}\n;; Received 60 bytes from 192.0.2.53#53({ns}) in 12 ms\n')
    put(ctx, 'dig_trace.txt', tr)
    sg = (f'; <<>> DiG 9.18.24 <<>> +dnssec www.{d}\n;; ->>HEADER<<- opcode: QUERY, status: NOERROR\n'
          f';; flags: qr rd ra{" ad" if signed else ""}; QUERY: 1, ANSWER: {2 if signed else 1}, AUTHORITY: 0\n\n;; ANSWER SECTION:\n'
          f'www.{d}.  {ttl} IN A {ip}\n' + (f'www.{d}.  {ttl} IN RRSIG A 13 3 {ttl} 20260401000000 20260311000000 12345 {d}. abcDEF==\n' if signed else ''))
    put(ctx, 'dig_dnssec.txt', sg)
    ctx.data.update(ip=ip, ttl=ttl, signed=str(signed).lower())
    ctx.write('requirements.txt', f'dig_trace.txt（dig +trace の記録）とdig_dnssec.txt（dig +dnssec の記録）から answer.json を作る: auth_ns（最終的に答えを返した権威サーバーのホスト名・末尾のドットなし）、address、ttl（数値）、signed（DNSSEC検証済みか、真偽値）。cmd.txtには、{d} のレコードを短く表示するdigコマンド（+short、種別ANY）を1行で。\n')


def c3(ctx):
    need_ro(ctx)
    D = ctx.data
    j = rj(ctx, 'answer.json')
    ctx.require(str(j.get('auth_ns', '')).rstrip('.') == D['ns'], 'auth_ns は最後の「;; Received」行のカッコ内のサーバーです。')
    ctx.require(j.get('address') == D['ip'] and j.get('ttl') == D['ttl'], 'address・ttl(数値)をAnswerの行から読みます。')
    ctx.require(j.get('signed') is (D['signed'] == 'true'), 'signed は +dnssec の応答のフラグに ad（Authenticated Data）があるかで判断します。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'dig' and '+short' in c and 'ANY' in [x.upper() for x in c] and D['dom'] in c, 'dig +short ANY ドメイン の形で書きます。')


SOL3 = """auth=$(grep '^;; Received' dig_trace.txt | tail -1 | sed 's/.*(\\(.*\\)).*/\\1/')
ip=$(grep '^www' dig_trace.txt | awk '{print $NF}')
ttl=$(grep '^www' dig_trace.txt | awk '{print $2}')
if grep -q 'flags:.* ad' dig_dnssec.txt; then s=true; else s=false; fi
printf '{"auth_ns": "%s", "address": "%s", "ttl": %s, "signed": %s}\\n' "$auth" "$ip" "$ttl" "$s" > answer.json
echo 'dig +short ANY <<dom>>' > cmd.txt"""
mission(3, 'digの+trace・+short・ANYとDNSSEC基礎',
        '名前解決の調査記録を読みます。dig +trace はルートからTLD、権威サーバーへと委任をたどり、+short は答えだけを表示し、ANY は全種別を要求します（近年は応答を絞るサーバーが多い）。dig +dnssec の応答に ad フラグとRRSIGがあれば署名の検証済みです。',
        ['権威サーバー・IP・TTL・DNSSEC検証を読み取りanswer.jsonへ', 'dig +short ANYのコマンドをcmd.txtへ'], s3, c3, SOL3,
        ["printf '{\"auth_ns\": \"a.nic.test\", \"address\": \"%s\", \"ttl\": %s, \"signed\": true}\\n' x 1 > answer.json\necho 'dig +short ANY <<dom>>' > cmd.txt",
         "auth=$(grep '^;; Received' dig_trace.txt | tail -1 | sed 's/.*(\\(.*\\)).*/\\1/')\nip=$(grep '^www' dig_trace.txt | awk '{print $NF}')\nttl=$(grep '^www' dig_trace.txt | awk '{print $2}')\nprintf '{\"auth_ns\": \"%s\", \"address\": \"%s\", \"ttl\": %s, \"signed\": false}\\n' \"$auth\" \"$ip\" \"$ttl\" > answer.json\necho 'dig +short <<dom>>' > cmd.txt"],
        'dig +traceは各段階で「このゾーンのNSはどれか」を示し、最後の「Received」行が実際に答えたサーバーです。+shortは値だけ、ANYは全レコード種別を問い合わせます。DNSSECは署名(RRSIG)と信頼の連鎖(DS・DNSKEY)で応答の改ざんを検出する仕組みで、検証リゾルバが成功すると応答にadフラグが付きます。',
        '最後の Received 行と、flags 行の ad を探します。', 'grep・awk・sed で取り出し、printf で JSON にします。')


# ---------------------------------------------------------------- 4 dnsmasq
def s4(ctx):
    d = 'lab-' + secrets.token_hex(2) + '.test'
    n = 10 + secrets.randbelow(200)
    pre = f'192.168.{n}'
    mac = ':'.join(secrets.token_hex(1) for _ in range(6))
    ctx.data.update(dom=d, pre=pre, mac=mac, nasip=f'{pre}.{20 + secrets.randbelow(20)}', up=f'10.9.{secrets.randbelow(200)}.53', pc=f'{pre}.{60 + secrets.randbelow(30)}')
    o = 'domain-needed\nbogus-priv\nno-resolv\nserver=1.1.1.1\n'
    put(ctx, 'dnsmasq.conf.orig', o)
    ctx.write('dnsmasq.conf', o)
    D = ctx.data
    ctx.write('requirements.txt', f'dnsmasq.confに追記: nas.{d} を {D["nasip"]} に固定解決(address)、*.corp.{d} だけ上位DNS {D["up"]} へ転送(server=/ドメイン/IP)、DHCP範囲 {pre}.100〜{pre}.150 リース12時間、MAC {mac} には {D["pc"]} を固定割当(dhcp-host、ホスト名pc01)。構文確認の dnsmasq --test -C dnsmasq.conf をcmd.txtへ。元の行は残す。\n')


def c4(ctx):
    need_ro(ctx)
    D = ctx.data
    keep_orig(ctx, 'dnsmasq.conf', 'dnsmasq.conf.orig')
    L = lines_of(ctx.need_file('dnsmasq.conf'))
    ctx.require(f'address=/nas.{D["dom"]}/{D["nasip"]}' in L, 'address=/ホスト名/IP の形で固定解決を書きます。')
    ctx.require(f'server=/corp.{D["dom"]}/{D["up"]}' in L, 'server=/ドメイン/上位DNS で特定ドメインだけ転送します。')
    r = [x for x in L if x.startswith('dhcp-range=')]
    ctx.require(r and r[-1].split('=')[1].split(',')[:3] == [D['pre'] + '.100', D['pre'] + '.150', '12h'], 'dhcp-range=開始,終了,12h を書きます。')
    h = [x for x in L if x.startswith('dhcp-host=')]
    ctx.require(h and set(h[-1].split('=')[1].lower().split(',')) >= {D['mac'], D['pc']}, 'dhcp-host=MAC,ホスト名,IP の形で固定割当します。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'dnsmasq' and '--test' in c and opt(c, '-C') == 'dnsmasq.conf', 'dnsmasq --test -C dnsmasq.conf を書きます。')


SOL4 = """cat >> dnsmasq.conf <<'EOF'
address=/nas.<<dom>>/<<nasip>>
server=/corp.<<dom>>/<<up>>
dhcp-range=<<pre>>.100,<<pre>>.150,12h
dhcp-host=<<mac>>,pc01,<<pc>>
EOF
echo 'dnsmasq --test -C dnsmasq.conf' > cmd.txt"""
mission(4, 'dnsmasqでDNSとDHCPを小さく構成する',
        '小規模拠点ではdnsmasq 1台でDNSキャッシュ・ローカル名・DHCPをまとめます。dnsmasq.confにaddress・server・dhcp-range・dhcp-hostを書き、dnsmasq --test で構文を確認します。',
        ['dnsmasq.confに4つの設定を追記', 'dnsmasq --testのコマンドをcmd.txtへ'], s4, c4, SOL4,
        ["cat >> dnsmasq.conf <<'EOF'\naddress=/nas.<<dom>>/<<nasip>>\nserver=<<up>>\ndhcp-range=<<pre>>.100,<<pre>>.150,12h\ndhcp-host=<<mac>>,pc01,<<pc>>\nEOF\necho 'dnsmasq --test -C dnsmasq.conf' > cmd.txt",
         "cat >> dnsmasq.conf <<'EOF'\naddress=/nas.<<dom>>/<<nasip>>\nserver=/corp.<<dom>>/<<up>>\ndhcp-range=<<pre>>.100,<<pre>>.150\ndhcp-host=<<mac>>,pc01,<<pc>>\nEOF\necho 'dnsmasq -C dnsmasq.conf' > cmd.txt"],
        'dnsmasqはDNSフォワーダとDHCPサーバーを兼ねます。address=/名前/IPはその名前（配下も）を固定で返し、server=/ドメイン/IPはそのドメインだけ別の上位DNSへ転送します。dhcp-rangeは配布範囲とリース時間、dhcp-hostはMACごとの固定割当です。--testは構文だけを確認して終了します。',
        '4種類のディレクティブはどれも key=値 の1行です。', 'heredocで追記し、検査は --test オプションです。')


# ---------------------------------------------------------------- 5 dhcpd
def s5(ctx):
    n = 10 + secrets.randbelow(200)
    pre = f'192.168.{n}'
    mac = ':'.join(secrets.token_hex(1) for _ in range(6))
    fx = f'{pre}.{20 + secrets.randbelow(40)}'
    ctx.data.update(pre=pre, mac=mac, fx=fx)
    o = (f'default-lease-time 600;\nmax-lease-time 7200;\nauthoritative;\nsubnet {pre}.0 netmask 255.255.255.0 {{\n'
         f'  range {pre}.100 {pre}.200;\n  option routers {pre}.1;\n}}\n')
    put(ctx, 'dhcpd.conf.orig', o)
    ctx.write('dhcpd.conf', o)
    nact = 3 + secrets.randbelow(3)
    nfree = 2 + secrets.randbelow(3)
    target = secrets.randbelow(nact)
    out = ''
    ctx.data['active'] = nact
    for i in range(nact + nfree):
        act = i < nact
        m = mac2 = ':'.join(secrets.token_hex(1) for _ in range(6))
        if act and i == target:
            m = ctx.data['lmac'] = ':'.join(secrets.token_hex(1) for _ in range(6))
            ctx.data['lip'] = f'{pre}.{100 + i}'
        out += (f'lease {pre}.{100 + i} {{\n  starts 3 2026/03/11 10:00:00;\n  ends 4 2026/03/12 10:00:00;\n'
                f'  binding state {"active" if act else "free"};\n  hardware ethernet {m};\n  client-hostname "host{i}";\n}}\n')
    put(ctx, 'dhcpd.leases', out)
    ctx.write('requirements.txt', f'(1) dhcpd.confに、MAC {mac} のプリンタへ固定アドレス {fx} を割り当てるhostブロックを追加（範囲外のアドレス）。(2) dhcpd.leases（リース記録）から leases.json を作る: active（binding state active の件数）、ip（MAC {ctx.data["lmac"]} が現在借りているIP）。\n')


def c5(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('dhcpd.conf')
    keep_orig(ctx, 'dhcpd.conf', 'dhcpd.conf.orig')
    hs = [block(t[m.start():], r'host\s+\S+\s*\{') for m in re.finditer(r'host\s+\S+\s*\{', t)]
    ok = [b for b in hs if b and re.search(r'hardware\s+ethernet\s+' + re.escape(D['mac']) + r'\s*;', b, re.I)
          and re.search(r'fixed-address\s+' + re.escape(D['fx']) + r'\s*;', b)]
    ctx.require(ok, 'host 名 { hardware ethernet MAC; fixed-address IP; } を追加します。')
    j = rj(ctx, 'leases.json')
    ctx.require(j.get('active') == D['active'] and j.get('ip') == D['lip'], 'leasesのbinding state active の件数と、指定MACのリースのIPを読みます。')


SOL5 = """cat >> dhcpd.conf <<'EOF'
host printer {
  hardware ethernet <<mac>>;
  fixed-address <<fx>>;
}
EOF
n=$(grep -c 'binding state active' dhcpd.leases)
ip=$(awk '/^lease/{ip=$2} /hardware ethernet <<lmac>>/{print ip}' dhcpd.leases)
printf '{"active": %s, "ip": "%s"}\\n' "$n" "$ip" > leases.json"""
mission(5, 'ISC dhcpdの設定・リース読解・固定割当',
        'ISC dhcpdのdhcpd.confにはサブネットと範囲、host宣言による固定割当を書きます。実際の貸出はdhcpd.leasesに追記されます。プリンタの固定割当を足し、リース記録から現在の貸出状況を集計してください。',
        ['dhcpd.confにhostブロックを追加', 'dhcpd.leasesの集計をleases.jsonへ'], s5, c5, SOL5,
        ["cat >> dhcpd.conf <<'EOF'\nhost printer {\n  hardware ethernet <<mac>>;\n  fixed-address <<fx>>;\n}\nEOF\nprintf '{\"active\": %s, \"ip\": \"%s\"}\\n' $(grep -c lease dhcpd.leases) x > leases.json",
         "cat >> dhcpd.conf <<'EOF'\nhost printer {\n  hardware ethernet <<mac>>;\n}\nEOF\nn=$(grep -c 'binding state active' dhcpd.leases)\nip=$(awk '/^lease/{ip=$2} /hardware ethernet <<lmac>>/{print ip}' dhcpd.leases)\nprintf '{\"active\": %s, \"ip\": \"%s\"}\\n' \"$n\" \"$ip\" > leases.json"],
        'dhcpd.confのsubnet宣言のrangeは動的配布範囲です。host宣言にhardware ethernetとfixed-addressを書くとMACごとに固定IPを渡せます（範囲の外に置くと衝突しません）。dhcpd.leasesはリースの履歴で、同じIPでも最後のエントリが有効、binding stateがactive/free/expiredで状態が分かります。',
        '固定割当はMACとIPの対応づけ、リースは awk で状態ごとに数えます。', '追記は heredoc、集計は grep -c と awk です。')


# ---------------------------------------------------------------- 6 LDAP LDIF
def parse_ldif(text):
    ents = []
    for chunk in re.split(r'\n\s*\n', text.strip()):
        e = {}
        for ln in chunk.splitlines():
            if ':' in ln and not ln.startswith('#'):
                k, v = ln.split(':', 1)
                e.setdefault(k.strip().lower(), []).append(v.strip())
        if e:
            ents.append(e)
    return ents


def s6(ctx):
    base = f'dc=co{secrets.token_hex(2)},dc=test'
    nm = 'user' + secrets.token_hex(2)
    mx = 10000 + secrets.randbelow(100)
    ctx.data.update(base=base, nm=nm, uid=mx + 1)
    ex = ''.join(f'dn: uid=old{i},ou=People,{base}\nobjectClass: inetOrgPerson\nobjectClass: posixAccount\nuid: old{i}\ncn: Old {i}\nsn: Old\n'
                 f'uidNumber: {mx - i}\ngidNumber: 10000\nhomeDirectory: /home/old{i}\nloginShell: /bin/bash\n\n' for i in range(2))
    put(ctx, 'existing.ldif', ex)
    ctx.write('requirements.txt', f'ディレクトリ {base}（管理者 cn=admin,{base}、サーバー ldap://localhost）に新ユーザー {nm} を登録する。existing.ldifの形式を参考に、uidNumberは既存の最大値+1、gidNumberは10000、ホームは /home/{nm}。add_user.ldifを作り、登録用のldapadd（簡易認証 -x、パスワードは -W で入力、-D 管理者 -f ファイル）をadd.txtへ、確認用のldapsearch（ou=People配下、(uid={nm})で絞り、cn と uidNumber だけ表示）をsearch.txtへ、各1行で。\n')


def c6(ctx):
    need_ro(ctx)
    D = ctx.data
    es = parse_ldif(ctx.need_file('add_user.ldif'))
    ctx.require(len(es) == 1, 'add_user.ldifにはエントリを1つだけ書きます。')
    e = es[0]
    ctx.require(e.get('dn') == [f'uid={D["nm"]},ou=People,{D["base"]}'], 'dn: uid=名前,ou=People,ベースDN にします。')
    ctx.require({'inetorgperson', 'posixaccount'} <= {x.lower() for x in e.get('objectclass', [])}, 'objectClassにinetOrgPersonとposixAccountを指定します。')
    for k in ('uid', 'cn', 'sn', 'loginshell'):
        ctx.require(e.get(k), f'{k} 属性が必要です。')
    ctx.require(e.get('uidnumber') == [str(D['uid'])] and e.get('gidnumber') == ['10000'], 'uidNumberは既存の最大値+1、gidNumberは10000です。')
    ctx.require(e.get('homedirectory') == [f'/home/{D["nm"]}'], 'homeDirectoryを指定します。')
    a = toks(ctx, one_line(ctx, 'add.txt'))
    ctx.require(a[0] == 'ldapadd' and '-x' in a and opt(a, '-D') == f'cn=admin,{D["base"]}' and opt(a, '-f') == 'add_user.ldif' and '-W' in a, 'ldapadd -x -D 管理者DN -W -f add_user.ldif の形です。')
    s = toks(ctx, one_line(ctx, 'search.txt'))
    ctx.require(s[0] == 'ldapsearch' and '-x' in s and opt(s, '-b') == f'ou=People,{D["base"]}' and f'(uid={D["nm"]})' in s, 'ldapsearch -x -b ベース (uid=名前) の形です。')
    ctx.require('cn' in s and 'uidNumber' in s, '表示する属性 cn と uidNumber を末尾に並べます。')


SOL6 = """cat > add_user.ldif <<'EOF'
dn: uid=<<nm>>,ou=People,<<base>>
objectClass: inetOrgPerson
objectClass: posixAccount
uid: <<nm>>
cn: New User
sn: User
uidNumber: <<uid>>
gidNumber: 10000
homeDirectory: /home/<<nm>>
loginShell: /bin/bash
EOF
echo 'ldapadd -x -H ldap://localhost -D "cn=admin,<<base>>" -W -f add_user.ldif' > add.txt
echo 'ldapsearch -x -H ldap://localhost -b "ou=People,<<base>>" "(uid=<<nm>>)" cn uidNumber' > search.txt"""
mission(6, 'LDAPのLDIF作成とldapadd・ldapsearch',
        'OpenLDAPなどのディレクトリにはLDIF形式でエントリを渡し、ldapaddで登録、ldapsearchで検索します。既存のLDIFを参考に新ユーザーを登録するLDIFと、登録・確認のコマンドを用意してください。',
        ['add_user.ldifを作成', 'ldapaddコマンドをadd.txtへ', 'ldapsearchコマンドをsearch.txtへ'], s6, c6, SOL6,
        ["cat > add_user.ldif <<'EOF'\ndn: uid=<<nm>>,ou=People,<<base>>\nobjectClass: inetOrgPerson\nuid: <<nm>>\ncn: New User\nsn: User\nuidNumber: <<uid>>\ngidNumber: 10000\nhomeDirectory: /home/<<nm>>\nloginShell: /bin/bash\nEOF\necho 'ldapadd -x -D \"cn=admin,<<base>>\" -W -f add_user.ldif' > add.txt\necho 'ldapsearch -x -b \"ou=People,<<base>>\" \"(uid=<<nm>>)\" cn uidNumber' > search.txt",
         "cat > add_user.ldif <<'EOF'\ndn: uid=<<nm>>,ou=People,<<base>>\nobjectClass: inetOrgPerson\nobjectClass: posixAccount\nuid: <<nm>>\ncn: New User\nsn: User\nuidNumber: 10000\ngidNumber: 10000\nhomeDirectory: /home/<<nm>>\nloginShell: /bin/bash\nEOF\necho 'ldapadd -x -D \"cn=admin,<<base>>\" -W -f add_user.ldif' > add.txt\necho 'ldapsearch -x -b \"ou=People,<<base>>\" \"(uid=<<nm>>)\" cn uidNumber' > search.txt"],
        'LDIFはdn行に続けて「属性: 値」を並べ、エントリは空行で区切ります。ldapaddは-f のLDIFを追加し、-x は簡易認証、-D は束縛するDN、-W はパスワードのプロンプトです。ldapsearchは-bの検索ベースと(uid=名前)のフィルタ、取得したい属性を指定します。posixAccountの属性(uidNumber等)はユーザーの重複を避けて割り当てます。',
        'LDIFの各属性は「名前: 値」、uidNumberは重複させません。', 'LDIFはheredocで作り、コマンド行は echo で書き出します。')


# ---------------------------------------------------------------- 7 SSSD
def s7(ctx):
    h = secrets.token_hex(2)
    suf = f'dc=site{h},dc=test'
    ctx.data.update(suf=suf, h=h)
    put(ctx, 'rootdse.txt', f'# ldapsearch -x -H ldaps://ldap.site{h}.test -b "" -s base namingContexts\ndn:\nnamingContexts: {suf}\n')
    ctx.write('sssd.conf', f'[sssd]\nservices = nss, pam\ndomains = LDAP\n\n[domain/LDAP]\nid_provider = ldap\nauth_provider = ldap\n'
              f'ldap_uri = ldap://ldap.site{h}.test\nldap_search_base = dc=old{h},dc=test\nldap_tls_reqcert = never\nenumerate = true\ncache_credentials = true\n', mode=0o644)
    ctx.write('nsswitch.conf', 'passwd:   files\ngroup:    files\nshadow:   files\nhosts:    files dns\n')
    ctx.write('requirements.txt', 'OpenLDAPのサーバー情報はrootdse.txtにある。SSSDで利用者を引けるようにsssd.confを直す: ldap_search_baseをサーバーのsuffix(namingContexts)に、ldap_uriを暗号化接続のldaps://（ホストは同じ）に、証明書検証 ldap_tls_reqcert を demand に、enumerate を false に。SSSDは権限が緩い設定を拒否するので所有者以外が読めないようにする。さらにnsswitch.confのpasswdとgroupにsssを追加。\n')


def c7(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('sssd.conf')
    sec = block('\n' + t.split('[domain/LDAP]', 1)[-1] + '\n}', r'\A') if '[domain/LDAP]' in t else None
    ctx.require(sec is not None, '[domain/LDAP] セクションは残します。')
    d = kv(t.split('[domain/LDAP]', 1)[1])
    ctx.require(d.get('id_provider') == 'ldap', 'id_provider = ldap は残します。')
    ctx.require(d.get('ldap_search_base') == D['suf'], 'ldap_search_baseをrootdse.txtのsuffixにします。')
    ctx.require(d.get('ldap_uri', '') == f'ldaps://ldap.site{D["h"]}.test', 'ldap_uriをldaps://ホスト にします。')
    ctx.require(d.get('ldap_tls_reqcert') == 'demand', '証明書は検証(demand)します。')
    ctx.require(d.get('enumerate', '').lower() == 'false', '全ユーザー列挙(enumerate)は負荷が高いのでfalseです。')
    ctx.require(ctx.mode('sssd.conf') & 0o077 == 0, 'sssd.confの権限を所有者のみ(600)にします。')
    n = kv(ctx.need_file('nsswitch.conf'), r':\s*')
    ctx.require('sss' in n.get('passwd', '').split() and 'sss' in n.get('group', '').split(), 'passwdとgroupにsssを追加します。')


SOL7 = """sed -i -E -e 's|^ldap_search_base.*|ldap_search_base = <<suf>>|' -e 's|^ldap_uri = ldap://|ldap_uri = ldaps://|' -e 's|^ldap_tls_reqcert.*|ldap_tls_reqcert = demand|' -e 's|^enumerate.*|enumerate = false|' sssd.conf
chmod 600 sssd.conf
sed -i -E '/^(passwd|group):/s/$/ sss/' nsswitch.conf"""
mission(7, 'OpenLDAPとSSSD連携の設定を直す',
        'LinuxサーバーでLDAPの利用者を使うにはSSSD（sssd.conf）とnsswitch.confを設定します。OpenLDAP側のsuffixはrootdse.txtで確認できます。検索ベースの食い違い・平文接続・権限の緩さを直してください。',
        ['sssd.confの4項目を修正', 'sssd.confを600に', 'nsswitch.confにsssを追加'], s7, c7, SOL7,
        ["sed -i -E -e 's|^ldap_search_base.*|ldap_search_base = <<suf>>|' -e 's|^ldap_uri = ldap://|ldap_uri = ldaps://|' -e 's|^ldap_tls_reqcert.*|ldap_tls_reqcert = demand|' -e 's|^enumerate.*|enumerate = false|' sssd.conf\nsed -i -E '/^(passwd|group):/s/$/ sss/' nsswitch.conf",
         "sed -i -E -e 's|^ldap_search_base.*|ldap_search_base = <<suf>>|' -e 's|^ldap_uri = ldap://|ldap_uri = ldaps://|' -e 's|^enumerate.*|enumerate = false|' sssd.conf\nchmod 600 sssd.conf\nsed -i -E '/^(passwd|group):/s/$/ sss/' nsswitch.conf"],
        'SSSDはldap_uri・ldap_search_base・id_provider/auth_providerでOpenLDAPに接続します。検索ベースがサーバーのsuffix（rootDSEのnamingContexts）と違うと利用者が見つかりません。ldapsや証明書検証(demand)がなければ通信が盗聴・なりすましされます。sssd.confは600でないとSSSDが起動を拒否します。nsswitch.confにsssを書いて初めてgetentが利用者を返します。',
        '3つのファイルの問題はそれぞれ「接続先・安全性・権限」です。', 'sed -i で各行を置換し、chmod 600 を忘れずに。')


# ---------------------------------------------------------------- 8 Postfix main.cf relay
def s8(ctx):
    d = dom()
    lan = f'192.168.{secrets.randbelow(250)}.0/24'
    ctx.data.update(dom=d, lan=lan)
    ctx.write('main.cf', 'smtpd_banner = $myhostname ESMTP\nmyhostname = localhost\nmyorigin = /etc/mailname\ninet_interfaces = all\n'
              'mynetworks = 0.0.0.0/0\nrelayhost =\nsmtp_tls_security_level = may\n')
    put(ctx, 'main.cf.orig', ctx.read('main.cf'))
    ctx.write('requirements.txt', f'このPostfixはオープンリレー状態で、外部へ送るにも向いていない。main.cfを直す: myhostname を mail.{d}、relayhost をSMTPリレー [relay.{d}]:587（ホストを[]で囲みMX引きしない）、mynetworks を 127.0.0.0/8 [::1]/128 {lan} だけ、リレーの認証 smtp_sasl_auth_enable を yes、パスワード表 smtp_sasl_password_maps を hash:/etc/postfix/sasl_passwd、TLSは smtp_tls_security_level を encrypt に。実効設定を表示するpostconf -nをcmd.txtへ。\n')


def c8(ctx):
    D = ctx.data
    t = ctx.need_file('main.cf')
    d = {}
    for s in lines_of(t):
        m = re.match(r'(\w+)\s*=\s*(.*)$', s)
        if m:
            d[m.group(1)] = m.group(2).strip()
    ctx.require('smtpd_banner' in d, '他の設定行は残します。')
    ctx.require(d.get('myhostname') == 'mail.' + D['dom'], 'myhostnameを設定します。')
    ctx.require(d.get('relayhost') == f'[relay.{D["dom"]}]:587', 'relayhost = [ホスト]:587 にします。')
    ctx.require(set(d.get('mynetworks', '').replace(',', ' ').split()) == {'127.0.0.0/8', '[::1]/128', D['lan']}, 'mynetworksは自分とLANだけ（0.0.0.0/0は危険）です。')
    ctx.require(d.get('smtp_sasl_auth_enable') == 'yes' and d.get('smtp_sasl_password_maps') == 'hash:/etc/postfix/sasl_passwd', 'SASL認証を有効にしてパスワード表を指定します。')
    ctx.require(d.get('smtp_tls_security_level') == 'encrypt', 'TLSは必須(encrypt)にします。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'postconf' and '-n' in c, 'postconf -n を書きます。')


SOL8 = """sed -i -E '/^(myhostname|relayhost|mynetworks|smtp_tls_security_level)/d' main.cf
cat >> main.cf <<'EOF'
myhostname = mail.<<dom>>
relayhost = [relay.<<dom>>]:587
mynetworks = 127.0.0.0/8 [::1]/128 <<lan>>
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_tls_security_level = encrypt
EOF
echo 'postconf -n' > cmd.txt"""
mission(8, 'Postfix main.cfのリレー設定とmynetworks',
        'Postfixのmain.cfで、外部SMTPリレー（relayhost）経由の送信とSASL認証、そして許可ネットワーク(mynetworks)の絞り込みを設定します。mynetworksが広すぎるとスパムの踏み台になります。変更後はpostconf -nで実効設定を確認します。',
        ['main.cfを修正', 'postconf -nをcmd.txtへ'], s8, c8, SOL8,
        ["cat >> main.cf <<'EOF'\nmyhostname = mail.<<dom>>\nrelayhost = relay.<<dom>>:587\nmynetworks = 127.0.0.0/8 [::1]/128 <<lan>>\nsmtp_sasl_auth_enable = yes\nsmtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd\nsmtp_tls_security_level = encrypt\nEOF\necho 'postconf -n' > cmd.txt",
         "cat >> main.cf <<'EOF'\nmyhostname = mail.<<dom>>\nrelayhost = [relay.<<dom>>]:587\nsmtp_sasl_auth_enable = yes\nsmtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd\nsmtp_tls_security_level = encrypt\nEOF\necho 'postconf -n' > cmd.txt"],
        'main.cfは「パラメータ = 値」で、同じ名前が複数あると最後が有効です。relayhostを[ ]で囲むとMX検索を省いてそのホストへ送ります。mynetworksは認証なしで中継を許す範囲で、0.0.0.0/0は誰でも中継できる危険な設定です。smtp_sasl_*はリレー先への認証、postconf -nは既定との差分だけを表示します。',
        'パラメータ名ごとに値を直します（同名は重複させない）。', '古い行を sed で消してから heredoc で追記し、postconf -n を記録します。')


# ---------------------------------------------------------------- 9 queue + log
def s9(ctx):
    rnd = secrets.SystemRandom()
    stuck = f'slow{secrets.token_hex(2)}.test'
    base = datetime.datetime(2026, 3, 11, 12, 0, 0)
    ids = []
    while len(ids) < 8:
        x = secrets.token_hex(5).upper()
        if x not in ids:
            ids.append(x)
    rows = []
    for i, qid in enumerate(ids):
        when = base - datetime.timedelta(hours=rnd.randrange(1, 70), minutes=rnd.randrange(60))
        if i == 0:
            rows.append((qid, True, when, 'noreply@corp.test', 'user@ok.test', ''))
        elif i <= 4:
            rows.append((qid, False, when, 'alice@corp.test', f'u{i}@{stuck}', f'(connect to mx.{stuck}[203.0.113.9]:25: Connection timed out)'))
        else:
            rows.append((qid, False, when, 'bob@corp.test', f'u{i}@other{i}.test', f'(host mx.other{i}.test[198.51.100.{i}] said: 450 try again later)'))
    q = '-Queue ID-  --Size-- ----Arrival Time---- -Sender/Recipient-------\n'
    for qid, act, w, s, r, why in rows:
        q += f'{qid}{"*" if act else " "}   {rnd.randrange(900, 9000):6d} {w.strftime("%a %b %d %H:%M:%S")}  {s}\n'
        if why:
            q += why + '\n'
        q += f'{" " * 42}{r}\n'
    q += f'-- 12 Kbytes in {len(rows)} Requests.\n'
    put(ctx, 'queue.txt', q)
    dfr = [r for r in rows if not r[1]]
    ctx.data.update(deferred=len(dfr), stuck=stuck, oldest=min(dfr, key=lambda r: r[2])[0])
    ns, nb = 3 + secrets.randbelow(6), 1 + secrets.randbelow(4)
    lg = ''.join(f'Mar 11 08:{i:02d}:11 mail postfix/smtp[{300 + i}]: {secrets.token_hex(5).upper()}: to=<u{i}@ok.test>, relay=mx.ok.test[192.0.2.1]:25, delay=0.7, dsn=2.0.0, status=sent (250 2.0.0 OK)\n' for i in range(ns))
    lg += ''.join(f'Mar 11 09:{i:02d}:11 mail postfix/smtp[{400 + i}]: {secrets.token_hex(5).upper()}: to=<x{i}@gone.test>, relay=mx.gone.test[192.0.2.2]:25, delay=0.9, dsn=5.1.1, status=bounced (550 5.1.1 User unknown)\n' for i in range(nb))
    lg += ''.join(f'Mar 11 10:00:{i:02d} mail postfix/smtp[{500 + i}]: {r[0]}: to=<{r[4]}>, relay=none, delay=3000, dsn=4.4.1, status=deferred {r[5]}\n' for i, r in enumerate(dfr))
    put(ctx, 'mail.log', lg)
    ctx.data.update(sent=ns, bounced=nb)
    ctx.write('requirements.txt', 'queue.txt（postqueue -p の記録）とmail.log（配送ログ）を読み、report.jsonを作る: deferred（保留中の件数。*付きは配送中なので除く）、stuck_domain（保留の宛先が最も多いドメイン）、oldest_id（保留のうち最も古いキューID）、sent・bounced（mail.logのstatus=sent/bouncedの件数）、postcat_cmd（そのoldest_idの中身を見るpostcat -q）、flush_cmd（保留をすぐ再配送するpostqueue -f）。\n')


def c9(ctx):
    need_ro(ctx)
    D = ctx.data
    j = rj(ctx, 'report.json')
    ctx.require(j.get('deferred') == D['deferred'], 'deferredは*の付かない（保留の）キューの件数です。')
    ctx.require(j.get('stuck_domain') == D['stuck'], '保留宛先が最も多いドメインを数えます。')
    ctx.require(j.get('oldest_id') == D['oldest'], '保留のうち到着時刻が最も古いIDです。')
    ctx.require(j.get('sent') == D['sent'] and j.get('bounced') == D['bounced'], 'mail.logのstatus=sent / bouncedを数えます。')
    p = toks(ctx, str(j.get('postcat_cmd', '')))
    ctx.require(p[:1] == ['postcat'] and '-q' in p and D['oldest'] in p, 'postcat_cmdは postcat -q キューID です。')
    f = toks(ctx, str(j.get('flush_cmd', '')))
    ctx.require(f == ['postqueue', '-f'], 'flush_cmdは postqueue -f です。')


SOL9 = """n=$(grep -cE '^[0-9A-F]{10} ' queue.txt)
s=$(grep -c 'status=sent' mail.log)
b=$(grep -c 'status=bounced' mail.log)
printf '{"deferred": %s, "stuck_domain": "<<stuck>>", "oldest_id": "<<oldest>>", "sent": %s, "bounced": %s, "postcat_cmd": "postcat -q <<oldest>>", "flush_cmd": "postqueue -f"}\\n' "$n" "$s" "$b" > report.json"""
mission(9, 'Postfixのキュー滞留とメール配送ログを読む',
        'メールが届かないという報告です。postqueue -p のキュー一覧、postcat でのメッセージ確認、mail.log の配送ログ（status=sent・deferred・bounced）を読んで滞留の原因ドメインと件数を特定し、報告をまとめてください。',
        ['キューと配送ログを集計しreport.jsonへ', 'postcatとpostqueue -fのコマンドを記載'], s9, c9, SOL9,
        ["printf '{\"deferred\": 8, \"stuck_domain\": \"ok.test\", \"oldest_id\": \"x\", \"sent\": 0, \"bounced\": 0, \"postcat_cmd\": \"postcat x\", \"flush_cmd\": \"postsuper -d ALL\"}\\n' > report.json",
         "n=$(grep -c . queue.txt)\ns=$(grep -c 'status=sent' mail.log)\nb=$(grep -c 'status=bounced' mail.log)\nprintf '{\"deferred\": %s, \"stuck_domain\": \"<<stuck>>\", \"oldest_id\": \"<<oldest>>\", \"sent\": %s, \"bounced\": %s, \"postcat_cmd\": \"postcat -q <<oldest>>\", \"flush_cmd\": \"postqueue -f\"}\\n' \"$n\" \"$s\" \"$b\" > report.json"],
        'postqueue -pはキューを表示し、IDに*が付くのは配送中(active)、付かないものは保留(deferred)で、理由が括弧で出ます。特定の宛先で固まるなら相手MXへの接続やDNSを疑います。postcat -q IDでヘッダと本文を確認し、postqueue -fで保留分を再配送します。mail.logのstatus=sent/deferred/bouncedとdsn(2.x成功・4.x一時失敗・5.x恒久失敗)で配送の結末を読めます。postsuper -d ALLは全削除なので原因調査前に使いません。',
        'キューIDの*の有無、理由の括弧、dsnのコードが手がかりです。', 'grep -c と、最も多い宛先ドメイン・最も古い時刻を目で読みます。')


# ---------------------------------------------------------------- 10 SPF / DKIM / DMARC
def s10(ctx):
    d = dom()
    sel = 'k' + secrets.token_hex(2)
    ip = f'198.51.100.{10 + secrets.randbelow(200)}'
    old = f'203.0.113.{10 + secrets.randbelow(200)}'
    dk = secrets.choice(['pass', 'fail'])
    dm = 'pass' if dk == 'pass' else 'fail'
    ctx.data.update(dom=d, ip=ip, old=old, dk=dk, dm=dm)
    put(ctx, 'headers.txt', f'Received: from mail.{d} (mail.{d} [{ip}]) by mx.recv.test with ESMTPS\nAuthentication-Results: mx.recv.test;\n'
        f' spf=fail smtp.mailfrom={d} (sender IP is {ip});\n dkim={dk} header.d={d} header.s={sel};\n dmarc={dm} header.from={d}\n'
        f'DKIM-Signature: v=1; a=rsa-sha256; d={d}; s={sel}; h=from:to:subject; bh=abc=; b=def=\nFrom: info@{d}\n')
    dkl = f'{sel}._domainkey.{d}. IN TXT "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ"'
    ctx.data['dkl'] = dkl
    ctx.write('dns_txt.txt', f'{d}. IN TXT "v=spf1 ip4:{old} -all"\n_dmarc.{d}. IN TXT "v=DMARC1; p=none"\n{dkl}\n')
    ctx.write('requirements.txt', f'受信側で認証が失敗した。headers.txtのAuthentication-Resultsからspf・dkim・dmarcの結果(pass/fail)を result.json に書く。あわせてdns_txt.txt（ゾーンのTXT）を直す: SPFには送信元IP {ip} を ip4: で追加（元の許可は残し、末尾は -all のまま）、DMARCはp=quarantineとrua=mailto:dmarc@{d} を設定。DKIMの公開鍵行は変更しない。\n')


def c10(ctx):
    need_ro(ctx)
    D = ctx.data
    j = rj(ctx, 'result.json')
    ctx.require(j.get('spf') == 'fail' and j.get('dkim') == D['dk'] and j.get('dmarc') == D['dm'], 'Authentication-Resultsのspf・dkim・dmarcの値をそのまま書きます。')
    t = ctx.need_file('dns_txt.txt')
    ls = [x.strip() for x in t.splitlines() if x.strip()]
    ctx.require(D['dkl'] in ls, 'DKIMの公開鍵行は変更しません。')
    sp = [x for x in ls if x.startswith(D['dom'] + '. ') and 'v=spf1' in x]
    ctx.require(len(sp) == 1, 'SPFレコードは1つだけにします。')
    txt = re.search(r'"(.*)"', sp[0]).group(1).split()
    ctx.require(f'ip4:{D["ip"]}' in txt and f'ip4:{D["old"]}' in txt, '元のIPを残したまま送信元IPを ip4: で追加します。')
    ctx.require(txt[0] == 'v=spf1' and txt[-1] == '-all', 'SPFの末尾は -all のままにします。')
    dm = [x for x in ls if x.startswith('_dmarc.' + D['dom'] + '.')]
    ctx.require(len(dm) == 1, '_dmarcのTXTは1つです。')
    tags = dict(p.strip().split('=', 1) for p in re.search(r'"(.*)"', dm[0]).group(1).split(';') if '=' in p)
    ctx.require(tags.get('v') == 'DMARC1' and tags.get('p') == 'quarantine' and tags.get('rua') == f'mailto:dmarc@{D["dom"]}', 'DMARCは v=DMARC1; p=quarantine; rua=mailto:... にします。')


SOL10 = """for k in spf dkim dmarc; do eval "$k=$(grep -o "$k=[a-z]*" headers.txt | head -1 | cut -d= -f2)"; done
printf '{"spf": "%s", "dkim": "%s", "dmarc": "%s"}\\n' "$spf" "$dkim" "$dmarc" > result.json
sed -i 's|ip4:<<old>> -all|ip4:<<old>> ip4:<<ip>> -all|' dns_txt.txt
sed -i 's|p=none|p=quarantine; rua=mailto:dmarc@<<dom>>|' dns_txt.txt"""
mission(10, 'SPF・DKIM・DMARCの認証結果を読みDNSを直す',
        '自社メールが受信側で迷惑メール扱いされます。ヘッダーのAuthentication-Resultsで SPF（送信IPの許可）、DKIM（電子署名）、DMARC（SPF/DKIMの整合と失敗時の扱い）の結果を読み、DNSのTXTレコードを修正してください。',
        ['認証結果をresult.jsonへ', 'dns_txt.txtのSPFとDMARCを修正'], s10, c10, SOL10,
        ["sed -i 's|ip4:<<old>> -all|ip4:<<ip>> -all|' dns_txt.txt\nsed -i 's|p=none|p=quarantine; rua=mailto:dmarc@<<dom>>|' dns_txt.txt\necho '{\"spf\": \"pass\", \"dkim\": \"pass\", \"dmarc\": \"pass\"}' > result.json",
         "sed -i 's|ip4:<<old>> -all|ip4:<<old>> ip4:<<ip>> +all|' dns_txt.txt\nsed -i 's|p=none|p=quarantine; rua=mailto:dmarc@<<dom>>|' dns_txt.txt\nprintf '{\"spf\": \"fail\", \"dkim\": \"<<dk>>\", \"dmarc\": \"<<dm>>\"}\\n' > result.json"],
        'SPFは送信を許すIP（ip4:）をDNSのTXTに列挙し、-allはそれ以外を拒否します（+allは全許可なので厳禁）。DKIMは送信側が秘密鍵で署名し、DNSのセレクタ._domainkeyの公開鍵で検証します。DMARCはSPFまたはDKIMがFromドメインと整合すればpassで、失敗時の扱い(p=none/quarantine/reject)と集計の送信先(rua)を宣言します。送信元を足したらSPFを更新し、DMARCは段階的に厳しくします。',
        'SPFは IP の許可、DKIM は署名、DMARC は両者の整合です。', 'grep -o で結果を抜き、sed で TXT の文字列を置換します。')


# ---------------------------------------------------------------- 11 Dovecot
def s11(ctx):
    ctx.write('dovecot.conf', 'protocols = imap pop3 lmtp\ndisable_plaintext_auth = no\nmail_location = mbox:~/mail:INBOX=/var/mail/%u\nssl = no\nauth_mechanisms = plain login\n'
              'service imap-login {\n  inet_listener imap {\n    port = 143\n  }\n  inet_listener imaps {\n    port = 993\n    ssl = yes\n  }\n}\n')
    ctx.write('requirements.txt', 'dovecot.confを安全な構成にする: protocolsはimapとlmtpだけ（pop3を無効に）、disable_plaintext_auth を yes、メール保存は mail_location を maildir:~/Maildir、ssl は required、平文のimapリスナー(143)は port = 0 で閉じる（imapsの993は残す）。設定を確認するdoveconf -nをcmd.txtへ。\n')


def c11(ctx):
    t = ctx.need_file('dovecot.conf')
    g = lambda k: (re.search(r'^' + k + r'\s*=\s*(.*)$', t, re.M) or [None, None])[1]
    ctx.require(g('protocols') and set(g('protocols').split()) == {'imap', 'lmtp'}, 'protocols = imap lmtp にします。')
    ctx.require(g('disable_plaintext_auth') == 'yes', 'disable_plaintext_auth = yes にします。')
    ctx.require(g('mail_location') == 'maildir:~/Maildir', 'mail_location = maildir:~/Maildir にします。')
    ctx.require(g('ssl') == 'required', 'ssl = required にします。')
    ctx.require(re.search(r'inet_listener imap \{[^}]*port\s*=\s*0\b', t), 'inet_listener imap の port を 0 にします。')
    ctx.require(re.search(r'inet_listener imaps \{[^}]*port\s*=\s*993\b', t), 'imapsの993は残します。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'doveconf' and '-n' in c, 'doveconf -n を書きます。')


SOL11 = """sed -i -e 's/^protocols = .*/protocols = imap lmtp/' -e 's/^disable_plaintext_auth = .*/disable_plaintext_auth = yes/' -e 's|^mail_location = .*|mail_location = maildir:~/Maildir|' -e 's/^ssl = no/ssl = required/' -e '/inet_listener imap {/,/}/ s/port = 143/port = 0/' dovecot.conf
echo 'doveconf -n' > cmd.txt"""
mission(11, 'Dovecotを暗号化必須のIMAPに設定する',
        'メール受信用のDovecotの設定を見直します。POP3の停止、平文認証の禁止、Maildir形式、TLS必須、平文IMAPポートの閉鎖をdovecot.confに反映し、doveconf -n で実効設定を確認します。',
        ['dovecot.confを5点修正', 'doveconf -nをcmd.txtへ'], s11, c11, SOL11,
        ["sed -i -e 's/^protocols = .*/protocols = imap lmtp/' -e 's/^disable_plaintext_auth = .*/disable_plaintext_auth = yes/' -e 's/^ssl = no/ssl = required/' dovecot.conf\necho 'doveconf -n' > cmd.txt",
         "sed -i -e 's/^protocols = .*/protocols = imap lmtp/' -e 's/^disable_plaintext_auth = .*/disable_plaintext_auth = yes/' -e 's|^mail_location = .*|mail_location = maildir:~/Maildir|' -e 's/^ssl = no/ssl = yes/' -e 's/port = 143/port = 0/g' dovecot.conf\necho 'doveconf -n' > cmd.txt"],
        'Dovecotはprotocolsで受け付けるプロトコルを決め、service imap-login内のinet_listenerでポートを定義します（port = 0 でそのリスナーを無効化）。disable_plaintext_auth=yesはTLS前の平文パスワードを拒否し、ssl=requiredでTLSを強制します。mail_locationのmaildirは1通1ファイルで、mboxより壊れにくく並行アクセスに強い形式です。doveconf -nは既定との差分を表示します。',
        'トップレベルの設定と、service 内のリスナーを分けて直します。', 'sed の範囲指定（/開始/,/終了/）でリスナー内だけを置換します。')


# ---------------------------------------------------------------- 12 HAProxy
def parse_haproxy(t):
    secs, cur = {}, None
    for ln in t.splitlines():
        if not ln.strip() or ln.strip().startswith('#'):
            continue
        if not ln[0].isspace():
            cur = ln.strip()
            secs[cur] = []
        elif cur:
            secs[cur].append(ln.strip())
    return secs


def s12(ctx):
    hp = '/health' + secrets.token_hex(1)
    adm = '/admin' + secrets.token_hex(1)
    port = 8000 + secrets.randbelow(900)
    s2 = f'10.0.0.{20 + secrets.randbelow(100)}'
    ctx.data.update(hp=hp, adm=adm, port=port, s2=s2)
    o = ('global\n    maxconn 2000\n\ndefaults\n    mode http\n    timeout connect 5s\n    timeout client 30s\n    timeout server 30s\n\n'
         f'frontend web\n    bind *:80\n    default_backend app\n\nbackend app\n    balance roundrobin\n    server s1 10.0.0.11:{port}\n')
    put(ctx, 'haproxy.cfg.orig', o)
    ctx.write('haproxy.cfg', o)
    ctx.write('requirements.txt', f'haproxy.cfgを直す: backend app に ヘルスチェック option httpchk GET {hp} を設け、s1と新サーバーs2({s2}:{port})の両方に check inter 2s fall 3 rise 2 を付ける。frontend webに、パスが {adm} で始まるACL(is_admin)、送信元が10.0.0.0/8のACL(internal)を定義し、社内以外から管理パスへのアクセスは http-request deny、管理パスは別backend admin_be（サーバー a1 10.0.0.30:9000 check）へ use_backend。検査のhaproxy -c -f haproxy.cfg をcmd.txtへ。\n')


def c12(ctx):
    need_ro(ctx)
    D = ctx.data
    s = parse_haproxy(ctx.need_file('haproxy.cfg'))
    ctx.require('global' in s and 'defaults' in s and 'frontend web' in s and 'bind *:80' in s['frontend web'], 'global・defaults・frontend webとbindは残します。')
    app = s.get('backend app')
    ctx.require(app is not None and f'option httpchk GET {D["hp"]}' in app, 'backend appにoption httpchk GET パス を書きます。')
    srv = {x.split()[1]: x for x in app if x.startswith('server ')}
    for n, a in (('s1', f'10.0.0.11:{D["port"]}'), ('s2', f'{D["s2"]}:{D["port"]}')):
        ctx.require(n in srv and srv[n].split()[2] == a, f'server {n} {a} ... を定義します。')
        ctx.require(re.search(r'\bcheck\b.*\binter 2s\b.*\bfall 3\b.*\brise 2\b', srv[n]), f'{n}に check inter 2s fall 3 rise 2 を付けます。')
    fe = s['frontend web']
    ctx.require(f'acl is_admin path_beg {D["adm"]}' in fe and 'acl internal src 10.0.0.0/8' in fe, 'aclを2つ定義します。')
    ctx.require('http-request deny if is_admin !internal' in fe, '管理パスで社内以外を拒否します。')
    ctx.require('use_backend admin_be if is_admin' in fe, '管理パスはadmin_beへ振り分けます。')
    ab = s.get('backend admin_be')
    ctx.require(ab and any(x.startswith('server a1 10.0.0.30:9000') and ' check' in x for x in ab), 'backend admin_beにa1をcheck付きで定義します。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'haproxy' and '-c' in c and opt(c, '-f') == 'haproxy.cfg', 'haproxy -c -f haproxy.cfg を書きます。')


SOL12 = """cat > haproxy.cfg <<'EOF'
global
    maxconn 2000

defaults
    mode http
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend web
    bind *:80
    acl is_admin path_beg <<adm>>
    acl internal src 10.0.0.0/8
    http-request deny if is_admin !internal
    use_backend admin_be if is_admin
    default_backend app

backend app
    balance roundrobin
    option httpchk GET <<hp>>
    server s1 10.0.0.11:<<port>> check inter 2s fall 3 rise 2
    server s2 <<s2>>:<<port>> check inter 2s fall 3 rise 2

backend admin_be
    server a1 10.0.0.30:9000 check
EOF
echo 'haproxy -c -f haproxy.cfg' > cmd.txt"""
mission(12, 'HAProxyのfrontend/backend・ヘルスチェック・ACL',
        'HAProxyでWebサーバーを2台に負荷分散します。frontendが受けた通信をbackendへ振り分け、health check（check）で落ちたサーバーを外し、ACLで管理パスを社内だけに制限します。',
        ['haproxy.cfgを修正', 'haproxy -cのコマンドをcmd.txtへ'], s12, c12, SOL12,
        ["cat > haproxy.cfg <<'EOF'\nglobal\n    maxconn 2000\n\ndefaults\n    mode http\n\nfrontend web\n    bind *:80\n    default_backend app\n\nbackend app\n    balance roundrobin\n    server s1 10.0.0.11:<<port>> check\n    server s2 <<s2>>:<<port>> check\nEOF\necho 'haproxy -c -f haproxy.cfg' > cmd.txt",
         "sed -i 's/server s1 .*/server s1 10.0.0.11:<<port>> check inter 2s fall 3 rise 2/' haproxy.cfg\necho 'haproxy -c -f haproxy.cfg' > cmd.txt"],
        'HAProxyはfrontend（待受）、backend（振り分け先）、defaultsとglobalで構成します。serverのcheckで死活監視し、inter（間隔）・fall（連続失敗で除外）・rise（連続成功で復帰）で調整、option httpchkでHTTPレベルの確認ができます。aclで条件に名前を付け、use_backendやhttp-request denyに「if 条件」で使います。検査はhaproxy -c -f です。',
        'frontend・backend・ACL・health checkの4点です。', '設定が長いので heredoc で全体を書き直すと間違いが減ります。')


# ---------------------------------------------------------------- 13 keepalived
def s13(ctx):
    vrid = 10 + secrets.randbelow(200)
    pw = secrets.token_hex(4)
    vip = f'192.168.1.{100 + secrets.randbelow(100)}'
    ctx.data.update(vrid=vrid, pw=pw, vip=vip)
    put(ctx, 'keepalived.conf', f'vrrp_instance VI_1 {{\n    state MASTER\n    interface eth0\n    virtual_router_id {vrid}\n    priority 150\n    advert_int 1\n'
        f'    authentication {{\n        auth_type PASS\n        auth_pass {pw}\n    }}\n    virtual_ipaddress {{\n        {vip}/24\n    }}\n}}\n')
    a, b = 'node-' + secrets.token_hex(1), 'node-' + secrets.token_hex(1)
    h, m = 2 + secrets.randbelow(20), secrets.randbelow(50)
    ctx.data.update(b=b, at=f'{h:02d}:{m:02d}:14')
    put(ctx, 'vrrp.log', f'Mar 11 01:00:02 {b} Keepalived_vrrp[812]: (VI_1) Entering BACKUP STATE\n'
        f'Mar 11 {h:02d}:{m:02d}:10 {b} Keepalived_vrrp[812]: (VI_1) Receive advertisement timeout\n'
        f'Mar 11 {h:02d}:{m:02d}:14 {b} Keepalived_vrrp[812]: (VI_1) Entering MASTER STATE\n'
        f'Mar 11 {h:02d}:{m:02d}:14 {b} Keepalived_vrrp[812]: (VI_1) setting VIPs.\n')
    ctx.write('requirements.txt', f'keepalived.confは主系(MASTER)の設定。(1) 待機系用に keepalived_b.conf を作る: BACKUP、同じinterfaceとvirtual_router_id・認証パスワード・VIP、priorityは主系より低い値。(2) vrrp.log（待機系のログ）から failover.json を作る: new_master（昇格したホスト名）、at（MASTERになった時刻 HH:MM:SS）、vip（virtual_ipaddressのIP・マスク無し）。\n')


def c13(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('keepalived_b.conf')
    g = lambda k: (re.search(r'^\s*' + k + r'\s+(\S+)', t, re.M) or [None, None])[1]
    ctx.require(g('state') == 'BACKUP', 'state は BACKUP にします。')
    ctx.require(g('interface') == 'eth0', 'interface は主系と同じです。')
    ctx.require(g('virtual_router_id') == str(D['vrid']), 'virtual_router_idは主系と同じ値でなければ同じグループになりません。')
    ctx.require(g('auth_pass') == D['pw'], 'auth_passは主系と同じにします。')
    ctx.require(f'{D["vip"]}/24' in t, 'virtual_ipaddressは主系と同じVIPです。')
    ctx.require(g('priority') and 0 < int(g('priority')) < 150, 'priorityは主系(150)より低くします。')
    j = rj(ctx, 'failover.json')
    ctx.require(j.get('new_master') == D['b'] and j.get('at') == D['at'] and j.get('vip') == D['vip'], 'ログの Entering MASTER STATE の行のホスト名と時刻、設定のVIPを書きます。')


SOL13 = """sed -e 's/state MASTER/state BACKUP/' -e 's/priority 150/priority 100/' keepalived.conf > keepalived_b.conf
host=$(grep 'Entering MASTER' vrrp.log | awk '{print $4}')
at=$(grep 'Entering MASTER' vrrp.log | awk '{print $3}')
vip=$(grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+/[0-9]+' keepalived.conf | cut -d/ -f1)
printf '{"new_master": "%s", "at": "%s", "vip": "%s"}\\n' "$host" "$at" "$vip" > failover.json"""
mission(13, 'keepalivedのVRRP冗長化とフェイルオーバーログ',
        'keepalivedはVRRPで複数サーバー間に仮想IP(VIP)を共有し、主系が落ちると待機系が引き継ぎます。主系の設定から待機系の設定を作り、フェイルオーバー時のログから昇格したノードを特定してください。',
        ['待機系keepalived_b.confを作成', 'failover.jsonを作成'], s13, c13, SOL13,
        ["sed -e 's/priority 150/priority 100/' keepalived.conf > keepalived_b.conf\nhost=$(grep 'Entering MASTER' vrrp.log | awk '{print $4}')\nat=$(grep 'Entering MASTER' vrrp.log | awk '{print $3}')\nvip=$(grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+/[0-9]+' keepalived.conf | cut -d/ -f1)\nprintf '{\"new_master\": \"%s\", \"at\": \"%s\", \"vip\": \"%s\"}\\n' \"$host\" \"$at\" \"$vip\" > failover.json",
         "sed -e 's/state MASTER/state BACKUP/' -e 's/priority 150/priority 200/' keepalived.conf > keepalived_b.conf\nhost=$(grep 'Entering MASTER' vrrp.log | awk '{print $4}')\nat=$(grep 'Entering MASTER' vrrp.log | awk '{print $3}')\nvip=$(grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+/[0-9]+' keepalived.conf | cut -d/ -f1)\nprintf '{\"new_master\": \"%s\", \"at\": \"%s\", \"vip\": \"%s\"}\\n' \"$host\" \"$at\" \"$vip\" > failover.json"],
        'VRRPのグループはvirtual_router_idとauthが一致するノードで構成され、priorityが最も高いノードがMASTERです。待機系はMASTERからの広告(advert)が途絶える(Receive advertisement timeout)とEntering MASTER STATEに遷移してVIPを引き継ぎます。同一ネットワークで他のグループとvirtual_router_idを重複させないこと、priorityを主系より低くすることが大切です。',
        '同じにする項目（id・認証・VIP）と変える項目（state・priority）を分けます。', 'sed で主系設定を加工し、ログは grep と awk で読みます。')


# ---------------------------------------------------------------- 14 Nginx
def s14(ctx):
    d = dom()
    pool = 'app_' + secrets.token_hex(2)
    a1, a2, a3 = (f'10.0.1.{10 + i * 5 + secrets.randbelow(4)}:{8000 + secrets.randbelow(100)}' for i in range(3))
    ctx.data.update(dom=d, pool=pool, a1=a1, a2=a2, a3=a3)
    o = f'events {{}}\nhttp {{\n    server {{\n        listen 80;\n        server_name {d};\n        location / {{\n            return 200 \'ok\';\n        }}\n    }}\n}}\n'
    put(ctx, 'nginx.conf.orig', o)
    ctx.write('nginx.conf', o)
    ctx.write('requirements.txt', f'nginx.confをリバースプロキシにする: upstream {pool} に least_conn、{a1}(weight=3)・{a2}、予備として {a3}(backup)。location / は proxy_pass http://{pool} へ（return 200は外す）。ヘッダは Host $host、X-Real-IP $remote_addr、X-Forwarded-For $proxy_add_x_forwarded_for、障害時に次のサーバーへ送る proxy_next_upstream error timeout http_502。検査の nginx -t -c nginx.conf をcmd.txtへ。\n')


def c14(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('nginx.conf')
    ctx.require('events' in t and f'server_name {D["dom"]};' in t, 'events・server_nameは残します。')
    up = block(t, r'upstream\s+' + re.escape(D['pool']) + r'\s*\{')
    ctx.require(up is not None, f'http内に upstream {D["pool"]} {{ }} を定義します。')
    L = [x.strip().rstrip(';').split() for x in up.splitlines() if x.strip()]
    ctx.require(['least_conn'] in L, 'least_conn; で接続数の少ないサーバーへ振ります。')
    sv = {x[1]: x[2:] for x in L if x[0] == 'server'}
    ctx.require(sv.get(D['a1']) == ['weight=3'] and sv.get(D['a2']) == [] and sv.get(D['a3']) == ['backup'], 'server行: a1はweight=3、a2は指定なし、a3はbackupにします。')
    loc = block(t, r'location\s+/\s*\{')
    ctx.require(loc is not None and f'proxy_pass http://{D["pool"]};' in loc and 'return' not in loc, 'location / に proxy_pass http://upstream名; を書きます。')
    for h in ('proxy_set_header Host $host;', 'proxy_set_header X-Real-IP $remote_addr;', 'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;', 'proxy_next_upstream error timeout http_502;'):
        ctx.require(h in loc, h + ' が必要です。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] == 'nginx' and '-t' in c and opt(c, '-c') == 'nginx.conf', 'nginx -t -c nginx.conf を書きます。')


SOL14 = """cat > nginx.conf <<'EOF'
events {}
http {
    upstream <<pool>> {
        least_conn;
        server <<a1>> weight=3;
        server <<a2>>;
        server <<a3>> backup;
    }
    server {
        listen 80;
        server_name <<dom>>;
        location / {
            proxy_pass http://<<pool>>;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_next_upstream error timeout http_502;
        }
    }
}
EOF
echo 'nginx -t -c nginx.conf' > cmd.txt"""
mission(14, 'Nginxのリバースプロキシとupstream',
        'Nginxをアプリサーバー前段のリバースプロキシにし、複数のバックエンドへ負荷分散します。upstreamブロックでサーバー群と方式を定義し、proxy_passで転送、元のクライアント情報をヘッダで渡します。',
        ['nginx.confを書き換え', 'nginx -tのコマンドをcmd.txtへ'], s14, c14, SOL14,
        ["cat > nginx.conf <<'EOF'\nevents {}\nhttp {\n    upstream <<pool>> {\n        server <<a1>> weight=3;\n        server <<a2>>;\n        server <<a3>> backup;\n    }\n    server {\n        listen 80;\n        server_name <<dom>>;\n        location / {\n            proxy_pass http://<<pool>>;\n        }\n    }\n}\nEOF\necho 'nginx -t -c nginx.conf' > cmd.txt",
         "cat > nginx.conf <<'EOF'\nevents {}\nhttp {\n    upstream <<pool>> {\n        least_conn;\n        server <<a1>> weight=3;\n        server <<a2>>;\n        server <<a3>>;\n    }\n    server {\n        listen 80;\n        server_name <<dom>>;\n        location / {\n            proxy_pass http://<<pool>>;\n            proxy_set_header Host $host;\n            proxy_set_header X-Real-IP $remote_addr;\n            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n            proxy_next_upstream error timeout http_502;\n        }\n    }\n}\nEOF\necho 'nginx -t -c nginx.conf' > cmd.txt"],
        'upstreamは分散先の集合で、least_connやip_hashで方式を選び、weightで比重、backupで予備にします。proxy_passでそのupstream名へ転送し、Hostを保持し、X-Real-IP・X-Forwarded-Forでクライアントのアドレスをアプリに伝えます。proxy_next_upstreamは障害時に別サーバーへ再試行する条件です。nginx -tは構文検査です。',
        'upstream の中と location の中、2か所に分けて書きます。', '全体を heredoc で書き、$ を展開させないため EOF を引用します。')


# ---------------------------------------------------------------- 15 Apache
def s15(ctx):
    d = dom()
    old, new = 'old-' + secrets.token_hex(2), 'new-' + secrets.token_hex(2)
    ctx.data.update(dom=d, old=old, new=new)
    o = 'ServerRoot "/etc/httpd"\nListen 80\n#LoadModule rewrite_module modules/mod_rewrite.so\nLoadModule dir_module modules/mod_dir.so\nServerName localhost\nDocumentRoot "/var/www/html"\n'
    put(ctx, 'httpd.conf.orig', o)
    ctx.write('httpd.conf', o)
    ctx.write('requirements.txt', f'(1) httpd.confで mod_rewrite を有効化（コメントを外す）し、<VirtualHost *:80> を追加: ServerName {d}、ServerAlias www.{d}、DocumentRoot /var/www/{d}/public、そのDirectoryは .htaccess のFileInfo系のみ許可(AllowOverride FileInfo)し Require all granted。(2) site/.htaccess に RewriteEngine On と、/{old} を /{new} へ恒久リダイレクト(301)する RewriteRule（[R=301,L]）。(3) 構文確認の apachectl configtest をcmd.txtへ。\n')


def c15(ctx):
    need_ro(ctx)
    D = ctx.data
    t = ctx.need_file('httpd.conf')
    ls = [x.strip() for x in t.splitlines()]
    ctx.require('LoadModule rewrite_module modules/mod_rewrite.so' in ls, 'LoadModule rewrite_module の行のコメントを外します。')
    keep_orig(ctx, 'httpd.conf', 'httpd.conf.orig', skip=('mod_rewrite',))
    v = re.search(r'<VirtualHost\s+\*:80>(.*?)</VirtualHost>', t, re.S)
    ctx.require(v, '<VirtualHost *:80> ... </VirtualHost> を追加します。')
    v = v.group(1)
    ctx.require(f'ServerName {D["dom"]}' in v and f'ServerAlias www.{D["dom"]}' in v and f'DocumentRoot /var/www/{D["dom"]}/public' in v, 'ServerName・ServerAlias・DocumentRootを書きます。')
    dr = re.search(r'<Directory\s+"?/var/www/' + re.escape(D['dom']) + r'/public"?>(.*?)</Directory>', v, re.S)
    ctx.require(dr and re.search(r'AllowOverride\s+FileInfo\b', dr.group(1)) and 'Require all granted' in dr.group(1), 'Directoryに AllowOverride FileInfo と Require all granted を書きます。')
    h = lines_of(ctx.need_file('site/.htaccess'))
    ctx.require('RewriteEngine On' in h, 'RewriteEngine On を書きます。')
    ok = False
    for x in h:
        f = x.split()
        if len(f) >= 4 and f[0] == 'RewriteRule' and f[1] in (f'^{D["old"]}$', f'^/{D["old"]}$') and f[2] in (f'/{D["new"]}', f'{D["new"]}') and 'R=301' in f[3] and 'L' in f[3].strip('[]').split(','):
            ok = True
    ctx.require(ok, f'RewriteRule ^{D["old"]}$ /{D["new"]} [R=301,L] の形で書きます。')
    c = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(c[0] in ('apachectl', 'apache2ctl', 'httpd') and ('configtest' in c or '-t' in c), 'apachectl configtest を書きます。')


SOL15 = """sed -i 's/^#LoadModule rewrite_module/LoadModule rewrite_module/' httpd.conf
cat >> httpd.conf <<'EOF'
<VirtualHost *:80>
    ServerName <<dom>>
    ServerAlias www.<<dom>>
    DocumentRoot /var/www/<<dom>>/public
    <Directory "/var/www/<<dom>>/public">
        AllowOverride FileInfo
        Require all granted
    </Directory>
</VirtualHost>
EOF
mkdir -p site
cat > site/.htaccess <<'EOF'
RewriteEngine On
RewriteRule ^<<old>>$ /<<new>> [R=301,L]
EOF
echo 'apachectl configtest' > cmd.txt"""
mission(15, 'Apacheのhttpd.conf・VirtualHost・mod_rewrite・.htaccess',
        'Apache httpdで1台に複数サイトを載せるため、httpd.confにVirtualHost（名前ベース）を追加します。URLの付け替えはmod_rewriteと、ディレクトリ単位で設定できる.htaccessで行います。AllowOverrideで.htaccessに許す範囲を絞ります。',
        ['httpd.confを修正', 'site/.htaccessを作成', 'apachectl configtestをcmd.txtへ'], s15, c15, SOL15,
        ["cat >> httpd.conf <<'EOF'\n<VirtualHost *:80>\n    ServerName <<dom>>\n    DocumentRoot /var/www/<<dom>>/public\n    <Directory \"/var/www/<<dom>>/public\">\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\nEOF\nmkdir -p site\nprintf 'RewriteEngine On\\nRewriteRule ^<<old>>$ /<<new>> [R=301,L]\\n' > site/.htaccess\necho 'apachectl configtest' > cmd.txt",
         "sed -i 's/^#LoadModule rewrite_module/LoadModule rewrite_module/' httpd.conf\ncat >> httpd.conf <<'EOF'\n<VirtualHost *:80>\n    ServerName <<dom>>\n    ServerAlias www.<<dom>>\n    DocumentRoot /var/www/<<dom>>/public\n    <Directory \"/var/www/<<dom>>/public\">\n        AllowOverride FileInfo\n        Require all granted\n    </Directory>\n</VirtualHost>\nEOF\nmkdir -p site\nprintf 'RewriteEngine On\\nRewriteRule ^<<old>>$ /<<new>> [R=302]\\n' > site/.htaccess\necho 'apachectl configtest' > cmd.txt"],
        'VirtualHostはServerName/ServerAliasのホスト名ごとにDocumentRootを切り替えます。mod_rewriteはLoadModuleで有効にし、RewriteRule パターン 置換 [フラグ]でURLを書き換えます（R=301は恒久リダイレクト、Lは最終規則）。.htaccessはAllowOverrideで許された範囲だけ効き、Allにすると何でも上書きされ性能も落ちるのでFileInfoなど最小限にします。構文はapachectl configtestで確認します。',
        'httpd.conf側と .htaccess側の役割を分けます。', 'sed でコメントを外し、heredoc で VirtualHost と .htaccess を書きます。')


# ---------------------------------------------------------------- 16 squid / chrony / rsyslog
def s16(ctx):
    bad = 'bad' + secrets.token_hex(2) + '.test'
    net = f'192.168.{secrets.randbelow(250)}.0/24'
    log = f'10.{70 + secrets.randbelow(20)}.'
    ctx.data.update(bad=bad, net=net, log=log)
    put(ctx, 'squid.conf.orig', 'http_port 3128\nacl localnet src 10.0.0.0/8\nhttp_access deny all\n')
    ctx.write('squid.conf', ctx.read('squid.conf.orig'))
    put(ctx, 'chrony.conf.orig', 'pool 2.pool.ntp.org iburst\ndriftfile /var/lib/chrony/drift\nmakestep 1.0 3\n')
    ctx.write('chrony.conf', ctx.read('chrony.conf.orig'))
    put(ctx, 'rsyslog.conf.orig', 'module(load="imuxsock")\n*.info;mail.none /var/log/messages\n')
    ctx.write('rsyslog.conf', ctx.read('rsyslog.conf.orig'))
    ctx.write('requirements.txt', f'社内の基盤サーバーを設定する。(1) squid.conf: ドメイン .{bad} を拒否するACL(blocked)を定義し、順序は http_access deny blocked → allow localnet → deny all。(2) chrony.conf: NTPサーバーとしてLAN {net} に allow を出し、上位に届かない時の local stratum 10 も設定。(3) rsyslog.conf（ログ受信側）: UDP 514で受信(imudp)、送信元IPが {log} で始まるログを /var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log に保存するテンプレートRemoteLogsを使い、保存後は stop で他へ流さない。元の行は残す。\n')


def c16(ctx):
    need_ro(ctx)
    D = ctx.data
    keep_orig(ctx, 'squid.conf', 'squid.conf.orig')
    sq = lines_of(ctx.need_file('squid.conf'))
    ctx.require(f'acl blocked dstdomain .{D["bad"]}' in sq, f'acl blocked dstdomain .{D["bad"]} を定義します。')
    ha = [x for x in sq if x.startswith('http_access')]
    ctx.require(ha == ['http_access deny blocked', 'http_access allow localnet', 'http_access deny all'], 'http_accessは上から順に評価されるので deny blocked → allow localnet → deny all の順にします。')
    keep_orig(ctx, 'chrony.conf', 'chrony.conf.orig')
    ch = lines_of(ctx.need_file('chrony.conf'))
    ctx.require(f'allow {D["net"]}' in ch and 'local stratum 10' in ch, 'allow LANのCIDR と local stratum 10 を書きます。')
    keep_orig(ctx, 'rsyslog.conf', 'rsyslog.conf.orig')
    r = ctx.need_file('rsyslog.conf')
    ctx.require('module(load="imudp")' in r and re.search(r'input\(type="imudp"\s+port="514"\)', r), 'imudpを読み込み、port 514で受信します。')
    ctx.require(re.search(r'template\(name="RemoteLogs"\s+type="string"\s+string="/var/log/remote/%HOSTNAME%/%PROGRAMNAME%\.log"\)', r), 'template(name="RemoteLogs" type="string" string="...") を定義します。')
    ctx.require(re.search(r"if\s+\$fromhost-ip\s+startswith\s+'" + re.escape(D['log']) + r"'\s+then\s+\?RemoteLogs\s*\n\s*&\s*stop", r), "if $fromhost-ip startswith '送信元' then ?RemoteLogs の次の行に & stop を書きます。")
    ctx.require(r.index('template(') < r.index('?RemoteLogs'), 'テンプレートはルールより前に定義します。')


SOL16 = """sed -i '/^http_access deny all/i acl blocked dstdomain .<<bad>>\\nhttp_access deny blocked\\nhttp_access allow localnet' squid.conf
printf 'allow %s\\nlocal stratum 10\\n' <<net>> >> chrony.conf
cat >> rsyslog.conf <<'EOF'
module(load="imudp")
input(type="imudp" port="514")
template(name="RemoteLogs" type="string" string="/var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log")
if $fromhost-ip startswith '<<log>>' then ?RemoteLogs
& stop
EOF"""
mission(16, 'squidプロキシ・chronyのNTPサーバー・rsyslog受信側',
        '社内の基盤サーバー3役を設定します。squidでWebアクセスをACLで制御し、chronyでLANにNTPを提供し（allow）、rsyslogで他のサーバーのログを集約受信します。',
        ['squid.confのACLと順序', 'chrony.confのallow', 'rsyslog.confの受信設定'], s16, c16, SOL16,
        ["sed -i '/^http_access deny all/i http_access allow localnet\\nacl blocked dstdomain .<<bad>>\\nhttp_access deny blocked' squid.conf\nprintf 'allow %s\\nlocal stratum 10\\n' <<net>> >> chrony.conf\ncat >> rsyslog.conf <<'EOF'\nmodule(load=\"imudp\")\ninput(type=\"imudp\" port=\"514\")\ntemplate(name=\"RemoteLogs\" type=\"string\" string=\"/var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log\")\nif $fromhost-ip startswith '<<log>>' then ?RemoteLogs\n& stop\nEOF",
         "sed -i '/^http_access deny all/i acl blocked dstdomain .<<bad>>\\nhttp_access deny blocked\\nhttp_access allow localnet' squid.conf\nprintf 'local stratum 10\\n' >> chrony.conf\ncat >> rsyslog.conf <<'EOF'\nmodule(load=\"imudp\")\ninput(type=\"imudp\" port=\"514\")\nif $fromhost-ip startswith '<<log>>' then /var/log/remote.log\nEOF"],
        'squidのhttp_accessは上から順に最初に一致した規則が適用され、最後のdeny allは必ず末尾に置きます。chronyは既定ではNTPサーバーとして応答せず、allowで許可するネットワークを指定して初めてLANのクライアントに時刻を配ります（上位に届かない時はlocal stratumで自己時刻を提供）。rsyslogの受信側はimudp/imtcpを読み込み、template と $fromhost-ip の条件でホスト別ファイルへ保存し、stopで重複記録を防ぎます。',
        '順序が意味を持つのは squid と rsyslog（テンプレート→ルール）です。', 'sed の i コマンドで deny all の直前に挿入し、残りは追記します。')
