"""Stage 17: ネットワーク管理・共有・パッケージ・バイナリ調査。

接続設定・ルールセット・記録済みの出力は作業フォルダ内の設定例/採取記録で診断する。
OSのネットワーク・時刻・パッケージ・ログ基盤は一切変更しない。
"""
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import time

from engine.runner import register

S = 17
NOTE = ("作業対象はこの課題のフォルダだけです。OSのネットワーク・時刻・パッケージ・syslogは変更しません。"
        "*.txt の出力は採取済みの記録（実測ではありません）で、実機での確認はVM実習で行います。")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def seal(ctx, *names):
    ctx.data['originals'] = {n: sha(ctx.p(n).read_bytes()) for n in names}


def intact(ctx):
    for n, h in ctx.data['originals'].items():
        ctx.require(ctx.isfile(n) and not ctx.p(n).is_symlink() and sha(ctx.p(n).read_bytes()) == h,
                    f'{n} は原本（採取記録）です。変更せず残してください。')


def jload(ctx, name):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存してください。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def norm(text):
    return [re.sub(r'\s+', ' ', l.strip()) for l in text.splitlines() if l.strip()]


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, h1, h2):
    register(id=f'17-{n}', stage=S, title=title, story=story + '\n' + NOTE, objectives=objectives,
             setup=setup, check=check, solution=solution, wrong=wrong, hints=[h1, h2, solution],
             answer=solution, explanation=explanation,
             tip='記録の読解・設定の検査・実機での確認は別の工程です。変更前の原本を残し、実機では変更後に再確認しましょう。')


# ---------------------------------------------------------------- 17-1 nmcli / resolvectl
def s1(ctx):
    good = f'192.0.2.{10 + secrets.randbelow(100)}'
    bad = f'192.0.2.{150 + secrets.randbelow(90)}'
    ctx.data.update(good=good, bad=bad)
    prof = ("[connection]\nid=office-lan\ntype=ethernet\ninterface-name=ens3\nautoconnect=true\n\n"
            f"[ipv4]\nmethod=manual\naddress1=10.20.0.15/24,10.20.0.1\ndns={bad};\ndns-search=dojo.test\n")
    ctx.write('ens3.nmconnection', prof)
    ctx.data['expected_prof'] = prof.replace(f'dns={bad};', f'dns={good};')
    ctx.write('resolvectl.txt', f"$ resolvectl status ens3\nLink 2 (ens3)\n  Current Scopes: DNS\n  Current DNS Server: {bad}\n  DNS Servers: {bad}\n  DNS Domain: dojo.test\n")
    ctx.write('requirements.txt', f"nmcli/NetworkManagerの接続プロファイル ens3.nmconnection（設定例）のDNSを承認済みリゾルバ {good} に直す。他の項目（method=manual・アドレス）は維持。\ndiagnosis.json に cause=wrong-dns-server, current, expected を記録。実OSには適用しません。\n")
    seal(ctx, 'resolvectl.txt', 'requirements.txt')


def c1(ctx):
    intact(ctx)
    ctx.require(ctx.need_file('ens3.nmconnection') == ctx.data['expected_prof'], 'dns= だけを承認済みリゾルバへ変更し、他の行は維持します。')
    ctx.require(jload(ctx, 'diagnosis.json') == dict(cause='wrong-dns-server', current=ctx.data['bad'], expected=ctx.data['good']),
                'resolvectlの現在のDNSと承認済みの値を diagnosis.json に記録します。')


mission(1, 'nmcliプロファイルとresolvectlの食い違い', 'resolvectlが示すDNSサーバーが、接続プロファイルの意図と違います。',
        ['resolvectl.txtとプロファイルの dns= を読む', 'ens3.nmconnection を最小限だけ修正', 'diagnosis.json に原因を記録'], s1, c1,
        """sed -i 's/^dns=.*/dns=<<good>>;/' ens3.nmconnection
echo '{"cause":"wrong-dns-server","current":"<<bad>>","expected":"<<good>>"}' > diagnosis.json""",
        ["sed -i 's/^method=.*/method=auto/' ens3.nmconnection", "echo '{\"cause\":\"wrong-dns-server\"}' > diagnosis.json",
         "sed -i 's/<<bad>>/<<good>>/' resolvectl.txt"],
        'resolvectl は実際に使われている状態、プロファイルはNetworkManagerが適用する意図です。両者を比較し、profileを直して再接続（nmcli con up）で反映します。記録を書き換えるのは診断になりません。',
        'resolvectlの「Current DNS Server」とプロファイルのdnsを並べて比べます。', 'sedで dns= の行だけを置換し、診断はechoでJSONにします。')


# ---------------------------------------------------------------- 17-2 nftables
def s2(ctx):
    admin = f'198.51.{100 + secrets.randbelow(100)}.0/24'
    ctx.data['admin'] = admin
    ctx.write('ruleset.nft', "table inet filter {\n  chain input {\n    type filter hook input priority 0; policy accept;\n    ct state established,related accept\n    tcp dport { 22, 80, 443, 3306, 6379 } accept\n  }\n}\n")
    ctx.write('listening.txt', "$ ss -tln\nLISTEN 0 128 0.0.0.0:22\nLISTEN 0 511 0.0.0.0:80\nLISTEN 0 511 0.0.0.0:443\nLISTEN 0 80 0.0.0.0:3306\nLISTEN 0 128 0.0.0.0:6379\n")
    ctx.write('requirements.txt', f"ruleset.nft（設定例）を読み、最小公開に直した版を ruleset.fixed.nft に保存する。公開は443のみ全体へ、22は管理網 {admin} だけ、既存接続は許可、既定はdrop。\n全体へ公開されていたポートの一覧（443以外・数値の昇順）を diagnosis.json の exposed に記録。実OSにはnft適用しません。\n")
    seal(ctx, 'ruleset.nft', 'listening.txt', 'requirements.txt')


def c2(ctx):
    intact(ctx)
    lines = set(norm(ctx.need_file('ruleset.fixed.nft')))
    adm = ctx.data['admin']
    exp = {'table inet filter {', 'chain input {', 'type filter hook input priority 0; policy drop;', 'ct state established,related accept',
           f'ip saddr {adm} tcp dport 22 accept', 'tcp dport 443 accept', '}'}
    ctx.require(lines == exp, '既定policyはdrop。許可は既存接続・管理網からの22・全体への443だけにします。')
    ctx.require(jload(ctx, 'diagnosis.json') == dict(exposed=[22, 80, 3306, 6379]), '全体に公開されていた443以外のポートを昇順で記録します。')


mission(2, 'nftablesルールを最小公開へ直す', 'DB(3306)やRedis(6379)まで全世界へ開いているルールセット案が見つかりました。',
        ['ruleset.nftの公開範囲を読み取る', 'ruleset.fixed.nftを最小公開で作る', 'exposedポートを記録'], s2, c2,
        """cat > ruleset.fixed.nft <<'EOF'
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    ip saddr <<admin>> tcp dport 22 accept
    tcp dport 443 accept
  }
}
EOF
echo '{"exposed":[22,80,3306,6379]}' > diagnosis.json""",
        ["sed 's/policy accept/policy drop/' ruleset.nft > ruleset.fixed.nft; echo '{\"exposed\":[3306]}' > diagnosis.json",
         "sed 's/, 3306, 6379//' ruleset.nft > ruleset.fixed.nft; echo '{\"exposed\":[22,80,3306,6379]}' > diagnosis.json"],
        'ファイアウォールは「既定drop＋必要最小限の許可」が基本です。firewalldでも同じ考え方（zone/service/rich rule）で、適用前に別セッションを保持し、変更は一時適用で確認します。',
        'policy accept のまま許可を足すのではなく、drop を既定にします。', '許可するのは established・管理網からの22・443の3つです。')


# ---------------------------------------------------------------- 17-3 bond/VLAN/bridge + ethtool
def s3(ctx):
    vlan = 100 + secrets.randbelow(800)
    wrong = vlan + 1 + secrets.randbelow(50)
    nic = f'enp{1 + secrets.randbelow(5)}s0'
    ctx.data.update(vlan=vlan, nic=nic)
    ctx.write('network.conf', f"bond0: mode=active-backup miimon=100 slaves={nic},enp9s0\nvlan0: parent=bond0 id={wrong}\nbr0: ports=vlan0 stp=off\n")
    ctx.data['expected_net'] = f"bond0: mode=802.3ad miimon=100 slaves={nic},enp9s0\nvlan0: parent=bond0 id={vlan}\nbr0: ports=vlan0 stp=off\n"
    ctx.write('switch.txt', f"port-channel 1: mode lacp active\ntrunk allowed vlan {vlan}\nport speed 1000 full auto-negotiation on\n")
    ctx.write(f'ethtool-{nic}.txt', f"$ ethtool {nic}\nSettings for {nic}:\n\tSpeed: 100Mb/s\n\tDuplex: Half\n\tAuto-negotiation: off\n\tLink detected: yes\n")
    ctx.write('requirements.txt', "network.conf（設定例）をswitch.txtに合わせ、bondのmodeとVLAN idだけ直す。ethtool記録のリンク不一致を診断し、直すコマンドを fix.sh に1行で書く（実行はしない）。\ndiagnosis.json に cause=duplex-mismatch, nic, vlan_id, bond_mode を記録。\n")
    seal(ctx, 'switch.txt', f'ethtool-{nic}.txt', 'requirements.txt')


def c3(ctx):
    intact(ctx)
    ctx.require(ctx.need_file('network.conf') == ctx.data['expected_net'], 'bondはLACP(802.3ad)、VLAN idはトランクの許可VLANに合わせ、他は維持します。')
    nic = ctx.data['nic']
    fx = norm(ctx.need_file('fix.sh'))
    ctx.require(fx in ([f'ethtool -s {nic} autoneg on'], ['#!/bin/sh', f'ethtool -s {nic} autoneg on'], ['#!/bin/bash', f'ethtool -s {nic} autoneg on']),
                '速度やduplexを固定せず、自動ネゴシエーションを有効にする1コマンドだけを書きます。')
    ctx.require(jload(ctx, 'diagnosis.json') == dict(cause='duplex-mismatch', nic=nic, vlan_id=ctx.data['vlan'], bond_mode='802.3ad'), '原因・NIC・VLAN・bondモードを記録します。')


mission(3, 'bond・VLANの設定とリンクduplex不一致', 'LACPのスイッチに対し、サーバー側のbondやVLAN idが合わず、片方のNICは100Mb/Halfで動いています。',
        ['network.confをswitch.txtと突き合わせて修正', 'ethtool記録からduplex不一致を特定', 'fix.shとdiagnosis.jsonを作る'], s3, c3,
        """sed -i 's/mode=active-backup/mode=802.3ad/; s/id=[0-9]*/id=<<vlan>>/' network.conf
echo 'ethtool -s <<nic>> autoneg on' > fix.sh
echo '{"cause":"duplex-mismatch","nic":"<<nic>>","vlan_id":<<vlan>>,"bond_mode":"802.3ad"}' > diagnosis.json""",
        ["sed -i 's/mode=active-backup/mode=802.3ad/' network.conf; echo 'ethtool -s <<nic>> autoneg on' > fix.sh",
         "sed -i 's/mode=active-backup/mode=802.3ad/; s/id=[0-9]*/id=<<vlan>>/' network.conf; echo 'ethtool -s <<nic>> speed 100 duplex full autoneg off' > fix.sh; echo '{}' > diagnosis.json"],
        '片側だけがautoneg offでHalfに固定されると、相手はFullのまま衝突やエラーが増えます。両端をautonegに揃えるのが原則です。bondのモードとVLANはスイッチ側と一致が必須です。',
        'switch.txtのLACPとVLAN、ethtool記録のDuplexを読みます。', 'sedで2項目だけ置換し、ethtool -s のコマンドは書くだけで実行しません。')


# ---------------------------------------------------------------- 17-4 tc
def s4(ctx):
    r = 5 + secrets.randbelow(40)
    dev = f'enp{1 + secrets.randbelow(5)}s0'
    ctx.data.update(r=r, dev=dev, r8=r * 8)
    ctx.write('shape.sh', f"#!/bin/sh\ntc qdisc add dev {dev} root tbf rate {r}mbps burst 32kbit latency 400ms\n")
    ctx.data['expected_shape'] = f"#!/bin/sh\ntc qdisc add dev {dev} root tbf rate {r}mbit burst 32kbit latency 400ms\n"
    ctx.write('tc-show.txt', f"$ tc qdisc show dev {dev}\nqdisc tbf 8001: root refcnt 2 rate {r * 8}Mbit burst 4Kb lat 400ms\n")
    ctx.write('requirements.txt', f"目標は {r} Mbit/s。shape.sh（設定例）の rate を直し、diagnosis.json に cause=mbps-is-bytes, configured_mbit, wanted_mbit を記録。実OSでtcは実行しません。\n")
    seal(ctx, 'tc-show.txt', 'requirements.txt')


def c4(ctx):
    intact(ctx)
    ctx.require(ctx.need_file('shape.sh') == ctx.data['expected_shape'], 'rate の単位だけを mbit に直し、他の行は維持します。')
    ctx.require(jload(ctx, 'diagnosis.json') == dict(cause='mbps-is-bytes', configured_mbit=ctx.data['r8'], wanted_mbit=ctx.data['r']), '実際の設定値と目標をMbitで記録します。')


mission(4, 'tcの帯域制御：mbpsとmbitの罠', '帯域を絞ったはずが、実測が想定の8倍になっています。tcの出力を読み解きましょう。',
        ['tc-show.txtの実効レートを読む', 'shape.shの単位を直す', '診断をdiagnosis.jsonへ'], s4, c4,
        """sed -i 's/mbps/mbit/' shape.sh
echo '{"cause":"mbps-is-bytes","configured_mbit":<<r8>>,"wanted_mbit":<<r>>}' > diagnosis.json""",
        ["sed -i 's/<<r>>mbps/<<r8>>mbit/' shape.sh; echo '{}' > diagnosis.json",
         "sed -i 's/mbps/mbit/' shape.sh; echo '{\"cause\":\"mbps-is-bytes\",\"configured_mbit\":<<r>>,\"wanted_mbit\":<<r>>}' > diagnosis.json"],
        'tcでは mbps はMバイト/秒、mbit はMビット/秒です。1B=8bitなので8倍違います。tc qdisc show の表示で実効値を必ず確認します。',
        'tc-show.txtの rate と設定の数値を比較します。', 'mbps は bit ではなく byte の単位です。')


# ---------------------------------------------------------------- 17-5 NFS / Samba
def s5(ctx):
    net = f'192.0.2.{secrets.randbelow(8) * 16}/28'
    ctx.data['net'] = net
    ex = "/srv/share *(rw,sync,no_root_squash)\n"
    ctx.write('exports', ex)
    smb = "[global]\nworkgroup = DOJO\n\n[share]\n  path = /srv/share\n  writable = yes\n  guest ok = yes\n  create mask = 0777\n"
    ctx.write('smb.conf', smb)
    ctx.write('requirements.txt', f"exports と smb.conf（設定例）を {net} 内の読み取り専用公開に絞る。NFSは ro,sync,root_squash の3つのオプション、Sambaは [share] に path / read only = yes / guest ok = no / hosts allow = {net} だけを持たせる。\n修正前の2ファイルは exports.orig と smb.conf.orig にコピーして残す。\n")
    ctx.data['orig_exports'] = ex
    ctx.data['orig_smb'] = smb
    seal(ctx, 'requirements.txt')


def c5(ctx):
    intact(ctx)
    net = ctx.data['net']
    ctx.require(ctx.need_file('exports.orig') == ctx.data['orig_exports'] and ctx.need_file('smb.conf.orig') == ctx.data['orig_smb'], '修正前のファイルをそのまま .orig として退避します。')
    m = re.fullmatch(r'/srv/share\s+(\S+?)\((.*)\)', ctx.need_file('exports').strip())
    ctx.require(bool(m) and m.group(1) == net and set(m.group(2).split(',')) == {'ro', 'sync', 'root_squash'}, 'exportsは対象網だけ、ro,sync,root_squashにします（*やno_root_squashは不可）。')
    sec, cur = {}, None
    for l in ctx.need_file('smb.conf').splitlines():
        l = l.strip()
        if l.startswith('[') and l.endswith(']'):
            cur = l[1:-1]
            sec[cur] = {}
        elif '=' in l and cur:
            k, v = l.split('=', 1)
            sec[cur][re.sub(r'\s+', ' ', k.strip())] = v.strip()
    ctx.require(sec.get('global') == {'workgroup': 'DOJO'}, '[global] は変更しません。')
    ctx.require(sec.get('share') == {'path': '/srv/share', 'read only': 'yes', 'guest ok': 'no', 'hosts allow': net}, '[share] は path・read only=yes・guest ok=no・hosts allow=対象網にします。')


mission(5, 'NFS exportsとSambaの公開範囲を絞る', '共有フォルダが全員に書き込み可能で公開されています（root権限の通過も許可）。',
        ['exportsとsmb.confを検査', '修正前を.origに退避', '対象網のみ・読み取り専用へ修正'], s5, c5,
        """cp exports exports.orig
cp smb.conf smb.conf.orig
echo '/srv/share <<net>>(ro,sync,root_squash)' > exports
cat > smb.conf <<'EOF'
[global]
workgroup = DOJO

[share]
  path = /srv/share
  read only = yes
  guest ok = no
  hosts allow = <<net>>
EOF""",
        ["cp exports exports.orig; cp smb.conf smb.conf.orig; sed -i 's/\\*/<<net>>/' exports",
         "echo '/srv/share <<net>>(ro,sync,root_squash)' > exports; echo '[share]' > smb.conf"],
        'NFSは「誰に・どの権限で」(host/オプション)、Sambaは hosts allow と guest/read only で範囲を絞ります。no_root_squashや0777のマスクは過剰な権限です。変更後は exportfs -ra / testparm で検証します。',
        'exportsのホスト指定とオプション、smb.confの guest・writable・hosts allow を見ます。', '修正前を cp で退避してから書き換えます。')


# ---------------------------------------------------------------- 17-6 chrony / timedatectl
def s6(ctx):
    ntp = f'ntp{1 + secrets.randbelow(9)}.dojo.test'
    off = 5 + secrets.randbelow(55) + 0.5
    ctx.data.update(ntp=ntp, off=off)
    ctx.write('chrony.conf', "pool 0.unreachable.example iburst\ndriftfile /var/lib/chrony/drift\n")
    ctx.data['expected_chrony'] = f"server {ntp} iburst\ndriftfile /var/lib/chrony/drift\nmakestep 1.0 3\n"
    ctx.write('timedatectl.txt', "$ timedatectl\n  System clock synchronized: no\n  NTP service: active\n  RTC in local TZ: no\n")
    ctx.write('tracking.txt', f"$ chronyc tracking\nReference ID    : 00000000 ()\nStratum         : 0\nSystem time     : {off} seconds slow of NTP time\nLeap status     : Not synchronised\n")
    ctx.write('requirements.txt', f"承認済みNTPは {ntp}。chrony.conf（設定例）を server <名前> iburst に直し、起動時の大きなずれを一気に補正する makestep 1.0 3 を追加。driftfileは維持。\ndiagnosis.json に cause=not-synchronized と offset_seconds（遅れ秒）を記録。\n")
    seal(ctx, 'timedatectl.txt', 'tracking.txt', 'requirements.txt')


def c6(ctx):
    intact(ctx)
    ctx.require(ctx.need_file('chrony.conf') == ctx.data['expected_chrony'], 'poolを承認済みserverへ置換し、makestepを追加します。')
    ctx.require(jload(ctx, 'diagnosis.json') == dict(cause='not-synchronized', offset_seconds=ctx.data['off']), 'trackingの記録から遅れ秒数を読み取って記録します。')


mission(6, 'chrony：時刻同期が取れない原因', 'ログの時刻がずれ、TLS検証や認証が失敗します。timedatectlとchronyc trackingの記録を読み解きましょう。',
        ['timedatectl.txtとtracking.txtを読む', 'chrony.confを修正', 'ずれを記録'], s6, c6,
        """printf 'server <<ntp>> iburst\\ndriftfile /var/lib/chrony/drift\\nmakestep 1.0 3\\n' > chrony.conf
echo '{"cause":"not-synchronized","offset_seconds":<<off>>}' > diagnosis.json""",
        ["sed -i 's/^pool.*/server <<ntp>> iburst/' chrony.conf; echo '{}' > diagnosis.json",
         "printf 'server <<ntp>> iburst\\ndriftfile /var/lib/chrony/drift\\nmakestep 1.0 3\\n' > chrony.conf; echo '{\"cause\":\"not-synchronized\",\"offset_seconds\":0}' > diagnosis.json"],
        'NTP serviceがactiveでも「System clock synchronized: no」なら同期できていません。Leap statusや参照元を見て、到達可能な時刻源へ。ずれが大きい時はmakestepで段階補正を避けます。',
        'tracking.txtの System time と Leap status を見ます。', 'printfで設定ファイル全体を作るのが簡単です。')


# ---------------------------------------------------------------- 17-7 hostnamectl / locale / iconv
def s7(ctx):
    short = 'web' + secrets.token_hex(2)
    fqdn = short + '.dojo.test'
    tok = ctx.rand(6)
    jp = f'設定メモ：サーバー{tok}の文字コードを統一する。\n'
    ctx.data.update(short=short, fqdn=fqdn, tok=tok, jp=jp)
    ctx.write('hostname', 'localhost.localdomain\n')
    ctx.write('hosts', "127.0.0.1 localhost\n")
    ctx.write('locale.conf', "LANG=C\n")
    ctx.write('hostnamectl.txt', "$ hostnamectl\n   Static hostname: localhost.localdomain\n         Icon name: computer-vm\n")
    ctx.write('memo.sjis.txt', jp.encode('cp932'), binary=True)
    ctx.write('requirements.txt', f"hostnameファイルを {fqdn}、hostsに「127.0.1.1 {fqdn} {short}」を追加（既存行は維持）、locale.confを LANG=ja_JP.UTF-8 に。memo.sjis.txt（CP932）をUTF-8へ変換して memo.utf8.txt に保存（原本は維持）。\n")
    seal(ctx, 'memo.sjis.txt', 'hostnamectl.txt', 'requirements.txt')


def c7(ctx):
    intact(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('hostname').strip() == d['fqdn'], 'hostnameを完全修飾名にします。')
    ctx.require(norm(ctx.need_file('hosts')) == ['127.0.0.1 localhost', f"127.0.1.1 {d['fqdn']} {d['short']}"], 'hostsは既存行を維持して1行追加します。')
    ctx.require(ctx.need_file('locale.conf') == 'LANG=ja_JP.UTF-8\n', 'LANGをja_JP.UTF-8にします。')
    try:
        out = ctx.p('memo.utf8.txt').read_bytes().decode('utf-8')
    except (OSError, UnicodeDecodeError):
        ctx.fail('memo.utf8.txt をUTF-8で保存してください。')
    ctx.require(out == d['jp'], '内容を壊さずCP932からUTF-8へ変換します（iconv -f CP932 -t UTF-8）。')


mission(7, 'hostnamectl・locale・文字コード変換', '新サーバーのホスト名とロケールが未設定で、旧システムのメモはShift_JIS(CP932)です。',
        ['hostname・hosts・locale.confを設定例で修正', 'iconvでCP932をUTF-8へ変換'], s7, c7,
        """echo '<<fqdn>>' > hostname
echo '127.0.1.1 <<fqdn>> <<short>>' >> hosts
echo 'LANG=ja_JP.UTF-8' > locale.conf
iconv -f CP932 -t UTF-8 memo.sjis.txt > memo.utf8.txt""",
        ["echo '<<fqdn>>' > hostname; echo '127.0.1.1 <<fqdn>> <<short>>' > hosts; echo 'LANG=ja_JP.UTF-8' > locale.conf; iconv -f CP932 -t UTF-8 memo.sjis.txt > memo.utf8.txt",
         "echo '<<fqdn>>' > hostname; echo '127.0.1.1 <<fqdn>> <<short>>' >> hosts; echo 'LANG=ja_JP.UTF-8' > locale.conf; cp memo.sjis.txt memo.utf8.txt"],
        'hostnamectl set-hostname と localectl set-locale が設定する実体はこれらのファイルです。文字コードは元の符号化を指定して変換し、cpでは文字化けします。hostsの追記は > ではなく >> です。',
        'ファイルを上書きすると既存のhostsの行が消えます。', 'iconv -f 元の文字コード -t 変換先 を使います。')


# ---------------------------------------------------------------- 17-8 packages
def s8(ctx):
    pkg = 'dojo' + secrets.choice(['tool', 'net', 'sync']) + secrets.token_hex(2)
    ver = f'{1 + secrets.randbelow(4)}.{secrets.randbelow(10)}.{secrets.randbelow(10)}-{1 + secrets.randbelow(5)}'
    cmd = f'/usr/bin/{pkg}'
    libs = sorted({secrets.choice(['libssl.so.3', 'libz.so.1', 'libcurl.so.4', 'libxml2.so.2', 'libpcre2-8.so.0']), 'libc.so.6', 'libm.so.6'})
    ctx.data.update(pkg=pkg, ver=ver, cmd=cmd, libs=libs)
    ctx.write('rpm-qf.txt', f"$ rpm -qf {cmd}\n{pkg}-{ver}.el9.x86_64\n")
    ctx.write('rpm-ql.txt', f"$ rpm -ql {pkg}\n{cmd}\n/usr/share/man/man1/{pkg}.1.gz\n")
    ctx.write('rpm-qR.txt', "$ rpm -qR " + pkg + "\nrpmlib(CompressedFileNames) <= 3.0.4-1\nrtld(GNU_HASH)\n" + ''.join(f'{l}()(64bit)\n' for l in libs))
    ctx.write('dpkg-S.txt', f"$ dpkg -S {cmd}\n{pkg}: {cmd}\n")
    ctx.write('requirements.txt', f"記録から {cmd} の所有パッケージ名(owner)・バージョン(version、-release まで・el9以降は除く)・依存ライブラリ(requires、昇順、rpmlib/rtld/()(64bit)を除く)を package.json に記録。pin.txt には dnf版とapt版の固定コマンドを2行（dnf versionlock add パッケージ-バージョン / apt-mark hold パッケージ）書く。\n")
    seal(ctx, 'rpm-qf.txt', 'rpm-ql.txt', 'rpm-qR.txt', 'dpkg-S.txt', 'requirements.txt')


def c8(ctx):
    intact(ctx)
    d = ctx.data
    ctx.require(jload(ctx, 'package.json') == dict(owner=d['pkg'], version=d['ver'], requires=d['libs']), '所有パッケージ・バージョン・依存ライブラリを記録から正確に読み取ります。')
    ctx.require(norm(ctx.need_file('pin.txt')) == [f"dnf versionlock add {d['pkg']}-{d['ver']}", f"apt-mark hold {d['pkg']}"], 'バージョン固定の2コマンドを順に書きます（実行はしません）。')


mission(8, 'rpm/dpkgの記録からパッケージを調べる', 'あるコマンドがどのパッケージ由来か、何に依存するか、更新で壊れないよう固定する方法を整理します。',
        ['rpm -qf / -ql / -qR / dpkg -S の記録を読む', 'package.jsonに整理', 'pin.txtに固定コマンドを書く'], s8, c8,
        """python3 - <<'PYCODE'
import json,re
t=open('rpm-qf.txt').read().splitlines()[1]
m=re.match(r'(.+?)-(\\d[^-]*-\\d+)\\.',t)
pkg,ver=m.group(1),m.group(2)
req=sorted({l.split('(')[0] for l in open('rpm-qR.txt').read().splitlines()[1:] if l.endswith('()(64bit)')})
json.dump(dict(owner=pkg,version=ver,requires=req),open('package.json','w'))
open('pin.txt','w').write(f'dnf versionlock add {pkg}-{ver}\\napt-mark hold {pkg}\\n')
PYCODE""",
        ["echo '{}' > package.json; echo 'dnf update' > pin.txt",
         "python3 -c \"import json;json.dump(dict(owner='<<pkg>>',version='<<ver>>.el9',requires=[]),open('package.json','w'))\"; echo 'apt-mark hold <<pkg>>' > pin.txt"],
        'rpm -qf はファイル→パッケージ、-ql はパッケージ→ファイル一覧、-qR は依存です。dpkg -S がrpm -qf、固定はdnf versionlock/apt-mark holdが相当します。snapは --channel と refresh.hold で制御します。',
        'rpm -qfの出力は 名前-バージョン-リリース.dist.arch の形です。', 'rpm-qRからlibだけを選び、()(64bit)の部分を除きます。')


# ---------------------------------------------------------------- 17-9 binaries
def s9(ctx):
    magic = secrets.token_bytes(4)
    tok = ctx.rand(10)
    blob = magic + secrets.token_bytes(40).replace(b'T', b'U') + f'TOKEN={tok}\0'.encode() + secrets.token_bytes(20).replace(b'T', b'U')
    ctx.write('blob.bin', blob, binary=True)
    miss = f'libdojo{secrets.randbelow(90) + 10}.so.1'
    ctx.data.update(magic=magic.hex(), tok=tok, miss=miss)
    ctx.write('ldd.txt', f"$ ldd ./app\n\tlinux-vdso.so.1 (0x00007ffc)\n\tlibc.so.6 => /lib64/libc.so.6 (0x00007f)\n\t{miss} => not found\n")
    ctx.write('requirements.txt', "blob.binの先頭4バイトを16進（小文字・連続）で magic.txt に、埋め込まれた TOKEN= の値を token.txt に（本物の xxd/od・grep -a 等で）。ldd.txtから見つからない共有ライブラリ名を missing.txt に。blob.binは変更しない。\n")
    seal(ctx, 'blob.bin', 'ldd.txt', 'requirements.txt')


def c9(ctx):
    intact(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('magic.txt').strip() == d['magic'], '先頭4バイトを16進で取り出します（xxd -p -l 4）。')
    ctx.require(ctx.need_file('token.txt').strip() == d['tok'], 'バイナリ内の文字列から TOKEN= の値だけを取り出します。')
    ctx.require(ctx.need_file('missing.txt').strip() == d['miss'], 'lddの "not found" の行にあるライブラリ名だけを書きます。')


mission(9, 'xxd・grep -a・lddでバイナリを調べる', '素性のわからないバイナリから、ヘッダ・埋め込み文字列・足りない共有ライブラリを突き止めます。',
        ['xxdで先頭バイトを読む', 'バイナリ内の文字列を抽出', 'lddの不足ライブラリを特定'], s9, c9,
        """xxd -p -l 4 blob.bin > magic.txt
grep -a -o 'TOKEN=[A-Z0-9]*' blob.bin | cut -d= -f2 > token.txt
grep 'not found' ldd.txt | awk '{print $1}' > missing.txt""",
        ["xxd -l 4 blob.bin > magic.txt; grep -a -o 'TOKEN=[A-Z0-9]*' blob.bin > token.txt; grep 'not found' ldd.txt > missing.txt",
         "head -c 4 blob.bin > magic.txt; grep -a TOKEN blob.bin > token.txt; grep -v 'not found' ldd.txt > missing.txt"],
        'file/xxd/od/hexdumpでヘッダとマジックナンバーを、strings(または grep -a)で埋め込み文字列を、lddで動的リンクの不足を調べます。信頼できないバイナリは実行せず静的に調べ、lddも注意が必要です。',
        'xxd -p は区切りなしの16進を出します。', 'テキスト検索は grep -a でバイナリを文字として扱えます。')


# ---------------------------------------------------------------- 17-10 transfer
def s10(ctx):
    tok = ctx.rand(5)
    ctx.data['tok'] = tok
    t = time.time() - 86400 * 3
    for rel, content in (('src/same.txt', 'same\n'), ('src/changed.txt', f'v2 {tok}\n'), ('src/new.txt', 'new\n'),
                         ('dest/same.txt', 'same\n'), ('dest/changed.txt', 'v1\n'), ('dest/keep.local', 'local only\n')):
        ctx.write(rel, content)
    for rel in ('src/same.txt', 'dest/same.txt', 'dest/changed.txt'):
        os.utime(ctx.p(rel), (t, t))
    ctx.write('requirements.txt', "src/ の変更だけを dest/ へ反映（実際のリモートはなし。ローカルのフォルダ間でrsyncの動作を学ぶ）。先に --dry-run の結果を plan.txt に保存し、その後に本実行。destだけにあるファイルは削除しない。\n")
    seal(ctx, 'requirements.txt')


def c10(ctx):
    intact(ctx)
    plan = ctx.need_file('plan.txt')
    ctx.require('changed.txt' in plan and 'new.txt' in plan and 'same.txt' not in plan, 'plan.txtに変更・新規だけが列挙された dry-run の出力を保存します。')
    ctx.require(ctx.read('dest/changed.txt') == f"v2 {ctx.data['tok']}\n" and ctx.read('dest/new.txt') == 'new\n', '変更と新規が反映されていません。')
    ctx.require(ctx.read('dest/keep.local') == 'local only\n', 'destだけのファイルは削除しません（--deleteは使いません）。')


mission(10, 'rsync --dry-run で安全に同期する', 'scp/sftp/rsyncのうち、差分だけを安全に同期するのはrsyncです。まず予行演習をします。',
        ['rsync -n(--dry-run)で計画をplan.txtへ', '本実行で差分を反映', '--deleteを使わず独自ファイルを守る'], s10, c10,
        """rsync -avn src/ dest/ > plan.txt
rsync -av src/ dest/""",
        ["rsync -av src/ dest/", "rsync -avn src/ dest/ > plan.txt; rsync -av --delete src/ dest/", "rsync -avn src/ dest/ > plan.txt"],
        'rsyncは差分だけ転送し、-n(--dry-run)で計画を確認できます。--deleteは宛先の余分なファイルを消すため、必ず予行演習で確認します。scpは単純コピー、sftpは対話的な転送です。リモートは user@host:path、末尾の / の有無で意味が変わります。',
        'まず -n を付けて何が起きるかを保存します。', 'src/ と dest/ の末尾スラッシュに注意します。')


# ---------------------------------------------------------------- 17-11 getopts + trap
def s11(ctx):
    ctx.data['tag'] = 'job' + ctx.rand(4)
    ctx.write('requirements.txt', "report.sh を作る。オプション -n COUNT -t TAG -v を getopts で解析。TAG-1 .. TAG-COUNT を1行ずつ出力（-vなら最初に verbose=on の行）。未知のオプションは使い方を標準エラーに出して終了コード2。\nmktemp -d の作業ディレクトリを使い、そのパスを last-tmp.txt に書き、正常終了・異常終了いずれでも trap で必ず削除。\n")
    seal(ctx, 'requirements.txt')


def run_script(ctx, *args):
    return subprocess.run(['bash', 'report.sh', *args], cwd=ctx.work, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)


def c11(ctx):
    intact(ctx)
    src = ctx.need_file('report.sh')
    ctx.require('getopts' in src and 'trap' in src, 'getoptsでの解析とtrapでの後始末を使います。')
    tag = ctx.data['tag']
    r = run_script(ctx, '-n', '3', '-t', tag)
    ctx.require(r.returncode == 0 and r.stdout.split() == [f'{tag}-1', f'{tag}-2', f'{tag}-3'], '-n と -t の値に従って連番を出力します。')
    tmp1 = ctx.need_file('last-tmp.txt').strip()
    ctx.require(bool(tmp1) and not os.path.exists(tmp1), '正常終了後も作業ディレクトリが残っています（trap EXIT）。')
    r = run_script(ctx, '-v', '-n', '1', '-t', tag)
    ctx.require(r.returncode == 0 and r.stdout.split() == ['verbose=on', f'{tag}-1'], '-v のときだけ最初に verbose=on を出力します。')
    r = run_script(ctx, '-x')
    ctx.require(r.returncode == 2 and r.stderr.strip() != '' and r.stdout.strip() == '', '未知のオプションは使い方を標準エラーへ出し、終了コード2にします。')
    tmp2 = ctx.need_file('last-tmp.txt').strip()
    ctx.require(not os.path.exists(tmp2), '異常終了でも作業ディレクトリは削除します。')


SOL11 = """cat > report.sh <<'EOF'
#!/bin/bash
usage() { echo "usage: $0 [-v] [-n COUNT] [-t TAG]" >&2; exit 2; }
n=1; tag=item; verbose=0
while getopts "n:t:v" opt; do
  case $opt in
    n) n=$OPTARG ;;
    t) tag=$OPTARG ;;
    v) verbose=1 ;;
    *) usage ;;
  esac
done
tmp=$(mktemp -d)
echo "$tmp" > last-tmp.txt
trap 'rm -rf "$tmp"' EXIT
[ "$verbose" = 1 ] && echo verbose=on
for i in $(seq 1 "$n"); do echo "$tag-$i"; done
EOF"""
mission(11, 'getoptsでオプション解析とtrapの後始末', '運用スクリプトにオプションを付け、途中で失敗しても一時ファイルを残さないようにします。',
        ['getoptsで -n -t -v を解析', '不正オプションは使い方と終了コード2', 'trap EXITで一時ディレクトリを削除'], s11, c11, SOL11,
        ["""cat > report.sh <<'EOF'
#!/bin/bash
tmp=$(mktemp -d); echo "$tmp" > last-tmp.txt
while getopts "n:t:v" o; do :; done
for i in 1 2 3; do echo "item-$i"; done
EOF""",
         """cat > report.sh <<'EOF'
#!/bin/bash
tmp=$(mktemp -d); echo "$tmp" > last-tmp.txt
echo trap
n=$2; tag=$4
for i in $(seq 1 $n); do echo "$tag-$i"; done
EOF"""],
        'getoptsはOPTARGと:付きの引数指定で安全にオプションを処理します。trap ... EXIT は成功・失敗・Ctrl-Cのどれでも後始末を実行します。一時ファイルはmktempで作り、固定名を避けます。',
        'getopts "n:t:v" のコロンは引数を取る印です。', '後始末は trap "rm -rf ..." EXIT です。')


# ---------------------------------------------------------------- 17-12 mkfifo + logger / rsyslog
def s12(ctx):
    ctx.data.update(tok=ctx.rand(6), tag='app' + ctx.rand(3).lower())
    ctx.write('requirements.txt', f"1) mkfifo で名前付きパイプ chan を作り、バックグラウンドの cat chan > out.log で受け、ここへ 'start TOK' と 'stop TOK' を送る(TOK={ctx.data['tok']})。\n2) rsyslog設定の断片 30-app.conf に、facility local5 のログを /var/log/{ctx.data['tag']}.log へ書く1行を書く。\n3) logger を使う実行例を logger-cmd.txt に1行で書く（-p local5.info -t {ctx.data['tag']} 'メッセージにTOKを含む'）。実行はしない。\n")
    seal(ctx, 'requirements.txt')


def c12(ctx):
    intact(ctx)
    d = ctx.data
    ctx.require(ctx.exists('chan') and stat.S_ISFIFO(os.lstat(ctx.p('chan')).st_mode), 'chan は mkfifo で作る名前付きパイプです。')
    ctx.require(ctx.read('out.log') == f"start {d['tok']}\nstop {d['tok']}\n", 'パイプ経由で受けた2行を out.log に保存します。')
    ctx.require(re.fullmatch(r'local5\.\*\s+-?/var/log/' + d['tag'] + r'\.log', ctx.need_file('30-app.conf').strip()) is not None, 'rsyslogのセレクタ local5.* と出力先を1行で書きます。')
    cmd = ctx.need_file('logger-cmd.txt').strip()
    ctx.require(cmd.startswith('logger ') and '-p local5.info' in cmd and f"-t {d['tag']}" in cmd and d['tok'] in cmd, 'logger に -p local5.info と -t タグ、TOKを含めます。')


mission(12, 'mkfifoでプロセス間通信、logger/rsyslogへ記録', '名前付きパイプでプロセス間にメッセージを渡し、rsyslogの設定とloggerの使い方まで整理します。',
        ['mkfifoでchanを作りcatで受信', 'rsyslogのlocal5ルールを書く', 'loggerコマンドの例を書く'], s12, c12,
        """mkfifo chan
cat chan > out.log &
printf 'start <<tok>>\\nstop <<tok>>\\n' > chan
wait
echo 'local5.*    /var/log/<<tag>>.log' > 30-app.conf
echo "logger -p local5.info -t <<tag>> 'done <<tok>>'" > logger-cmd.txt""",
        ["echo 'start <<tok>>' > out.log; echo 'local5.* /var/log/<<tag>>.log' > 30-app.conf",
         "touch chan out.log; echo 'local5.* /var/log/<<tag>>.log' > 30-app.conf; echo \"logger -t <<tag>> <<tok>>\" > logger-cmd.txt",
         "mkfifo chan; echo 'local7.* /var/log/<<tag>>.log' > 30-app.conf"],
        'FIFOは読み手と書き手が揃うまで開く側がブロックします。そのため受信側をバックグラウンドで先に起動します。loggerはsyslogへ、rsyslogはfacility.priorityで振り分けて保存します。',
        '読み手がいないFIFOへ書くとブロックします。先に cat chan > out.log & を。', 'rsyslogの1行は「セレクタ 出力先」です。')
