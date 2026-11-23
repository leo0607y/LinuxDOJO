"""Stage 20: 暗号化・VPN・SSHトンネル。サンドボックス内の偽データ・採取済み出力・実在するopensslだけを使う。"""
import base64
import hashlib
import json
import re
import secrets
import shlex
import shutil
import string
import struct
import subprocess
import uuid
from datetime import datetime, timedelta

from engine.runner import register

S = 20
NOTE = ("作業対象はこの課題のフォルダだけです。実OSの設定・ネットワーク・ディスク・VPNは変更せず、rootも使いません。"
        "鍵・証明書・ホスト名は訓練用の偽物で、実行環境にないツールは採取済みの出力と設定例から診断します。")
SR = secrets.SystemRandom()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def put(ctx, name, text):
    ctx.write(name, text)
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


def lines_of(ctx, name):
    return [x for x in ctx.need_file(name).splitlines() if x.strip()]


def one_line(ctx, name):
    ls = lines_of(ctx, name)
    ctx.require(len(ls) == 1, name + ' には1行のコマンドだけを書きます。')
    return ls[0].strip()


def toks(ctx, line):
    try:
        return shlex.split(line)
    except ValueError:
        ctx.fail('コマンドの引用符が閉じていません。')


def b64key():
    return base64.b64encode(secrets.token_bytes(32)).decode()


def fp():
    return 'SHA256:' + base64.b64encode(secrets.token_bytes(32)).decode().rstrip('=')


def pubkey(comment):
    blob = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + secrets.token_bytes(32)
    return 'ssh-ed25519 ' + base64.b64encode(blob).decode() + ' ' + comment


def kv_conf(text):
    """'key value' / 'key=value' を [(section, {key: [values]})] にする。Host/Match/conn/[Peer]で区切る。"""
    out = [('', {})]
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('['):
            out.append((s, {}))
            continue
        m = re.match(r'(\S+?)\s*(?:=|\s)\s*(.*)$', s)
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2).strip()
        if k in ('host', 'match', 'conn'):
            out.append((k + ' ' + v, {}))
        else:
            out[-1][1].setdefault(k, []).append(v)
    return out


def openssl(ctx, *args):
    tool = shutil.which('openssl')
    ctx.require(bool(tool), 'この課題にはopensslが必要です。')
    r = subprocess.run([tool, *args], cwd=ctx.work, capture_output=True, text=True, timeout=30)
    ctx.require(r.returncode == 0, 'opensslで検査できません。ファイルと引数を確認します: ' + ' '.join(args[:2]))
    return r.stdout


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'20-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='鍵と証明書は「作る・配る・確認する・失効させる」までを一続きの手順として扱い、元の状態を保全してから変更しましょう。')


# ---------------------------------------------------------------- 1 LUKS dump / layers
def s1(ctx):
    dev = '/dev/sd' + secrets.choice('bcdef') + '1'
    uid = str(uuid.uuid4())
    slots = sorted(SR.sample(range(8), 3))
    owners = ['ex-admin', 'ops-team', 'recovery']
    SR.shuffle(owners)
    kill = slots[owners.index('ex-admin')]
    dump = f'LUKS header information\nVersion:        2\nEpoch:          7\nUUID:           {uid}\n\nData segments:\n  0: crypt\n\toffset: 16777216 [bytes]\n\tcipher: aes-xts-plain64\n\nKeyslots:\n'
    for s in slots:
        dump += f'  {s}: luks2\n\tKey:        512 bits\n\tPBKDF:      argon2id\n\tCipher:     aes-xts-plain64\n'
    dump += 'Tokens:\nDigests:\n  0: pbkdf2\n'
    t = secrets.token_hex(2)
    ds = dict(d_luks='laptop-disk-' + t, d_fscrypt='home-alice-' + t, d_ecryptfs='legacy-home-' + t)
    inv = [f'{ds["d_luks"]}: ブロックデバイス全体。盗難・紛失時にディスク全体の中身を保護したい',
           f'{ds["d_fscrypt"]}: 共有サーバーのext4上のユーザー別ディレクトリだけ。ユーザーごとの鍵、カーネル標準機能',
           f'{ds["d_ecryptfs"]}: 旧Ubuntuのスタック型ファイルシステム。メンテナンス終了で移行対象']
    SR.shuffle(inv)
    ctx.data.update(uuid=uid, dev=dev, slots_json=json.dumps(slots, separators=(',', ':')), kill=kill, **ds)
    put(ctx, 'luksdump.txt', f'$ sudo cryptsetup luksDump {dev}\n' + dump)
    put(ctx, 'slots.txt', ''.join(f'slot {s}: {o}\n' for s, o in zip(slots, owners)))
    put(ctx, 'inventory.txt', '\n'.join(inv) + '\n')
    ctx.write('requirements.txt', 'cryptsetup luksFormatで作り luksOpenで開く暗号化ディスクの鍵スロットを棚卸しする。luksdump.txtのUUIDとデバイス、有効な鍵スロット番号をdiag.jsonへ（uuid, device, enabled_slots, revoke_slot）。退職したex-adminのパスフレーズが入るスロットだけをcryptsetup luksKillSlotで無効化する1行をcmd.txtへ（実行はしません）。'
              'さらにinventory.txtの各データを守る層をlayers.jsonへ（名前→"luks"か"fscrypt"か"ecryptfs"）。\n')


def c1(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'diag.json')
    ctx.require(j.get('uuid') == d['uuid'] and j.get('device') == d['dev'], 'luksDumpのUUIDとデバイスを正確に写します。')
    ctx.require(j.get('enabled_slots') == json.loads(d['slots_json']), '有効な鍵スロット番号を昇順の配列で書きます。')
    ctx.require(j.get('revoke_slot') == d['kill'], '無効化するのはex-adminのスロットだけです（slots.txtと照合）。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[:2] == ['cryptsetup', 'luksKillSlot'], '鍵スロット1つを消すのはcryptsetup luksKillSlotです（luksErase等は全滅します）。')
    ctx.require(t[2:] == [d['dev'], str(d['kill'])], 'luksKillSlot デバイス スロット番号 の順です。')
    ctx.require(rj(ctx, 'layers.json') == {d['d_luks']: 'luks', d['d_fscrypt']: 'fscrypt', d['d_ecryptfs']: 'ecryptfs'},
                'ディスク全体=LUKS、ディレクトリ単位=fscrypt、旧スタック型=eCryptfsに対応づけます。')


SOL1 = """echo '{"uuid":"<<uuid>>","device":"<<dev>>","enabled_slots":<<slots_json>>,"revoke_slot":<<kill>>}' > diag.json
echo "cryptsetup luksKillSlot <<dev>> <<kill>>" > cmd.txt
echo '{"<<d_luks>>":"luks","<<d_fscrypt>>":"fscrypt","<<d_ecryptfs>>":"ecryptfs"}' > layers.json"""
mission(1, 'luksDumpで鍵スロットを棚卸しし暗号化層を選ぶ',
        '退職者のパスフレーズがLUKSの鍵スロットに残っています。cryptsetup luksFormatで作成し、luksOpenで開くdm-crypt/LUKSの設定はluksDumpで読めます。またディレクトリ単位のfscryptや旧式のeCryptfsとの使い分けも整理します。',
        ['luksdump.txtから情報をdiag.jsonへ', 'ex-adminのスロットだけを消すcmd.txt', 'layers.jsonで暗号化層を対応づける'], s1, c1, SOL1,
        ['echo "cryptsetup luksKillSlot <<dev>> 0" > cmd.txt\necho \'{"uuid":"<<uuid>>","device":"<<dev>>","enabled_slots":[0],"revoke_slot":0}\' > diag.json',
         'echo "cryptsetup luksErase <<dev>>" > cmd.txt\necho \'{"<<d_luks>>":"fscrypt","<<d_fscrypt>>":"luks","<<d_ecryptfs>>":"ecryptfs"}\' > layers.json'],
        'LUKSはブロックデバイス全体を暗号化し、マスター鍵を複数の鍵スロット（最大8、LUKS2は多数）が別々のパスフレーズや鍵ファイルで包みます。cryptsetup luksDumpで有効なスロットが分かり、cryptsetup luksKillSlot デバイス 番号 で1つだけ無効化できます。残り1つを消すと開けなくなるので事前にヘッダのバックアップを取ります。fscryptはext4/f2fs等でディレクトリ単位に暗号化するカーネル標準機能、eCryptfsは旧来のスタック型で新規採用は避けます。',
        'luksDumpは有効なスロットだけを列挙します。', 'slots.txtの持ち主とluksdump.txtを番号で対応づけます。')


# ---------------------------------------------------------------- 2 LUKS header backup / crypttab
def s2(ctx):
    name = 'data-' + secrets.token_hex(2)
    uid = str(uuid.uuid4())
    dev = '/dev/sd' + secrets.choice('bcdef') + '1'
    ctx.data.update(name=name, uuid=uid, dev=dev)
    old = 'swap /dev/sda3 /dev/urandom swap,cipher=aes-xts-plain64,size=256\n'
    ctx.write('crypttab', '# <name> <device> <password> <options>\n' + old)
    ctx.data['old_crypttab'] = old
    put(ctx, 'luksdump.txt', f'$ sudo cryptsetup luksDump {dev}\nLUKS header information\nVersion:        2\nUUID:           {uid}\n')
    ctx.write('requirements.txt', f'{dev}（UUID={uid}）はluksOpenで{name}として開く暗号化ボリューム。ヘッダが壊れると全データを失うので、cryptsetup luksHeaderBackupでヘッダを{name}-header.imgへ退避するコマンドを1行backup.txtへ。'
              f'起動時に自動で開くため、crypttabへ名前{name}・UUID指定・鍵はnone（起動時に入力）・オプションluks,discardの行を追加（既存行は変更しない）。\n')


def c2(ctx):
    need_ro(ctx)
    d = ctx.data
    t = toks(ctx, one_line(ctx, 'backup.txt'))
    ctx.require(t[:2] == ['cryptsetup', 'luksHeaderBackup'] and d['dev'] in t, 'cryptsetup luksHeaderBackup デバイス --header-backup-file ファイル です。')
    ctx.require('--header-backup-file' in t and t[t.index('--header-backup-file') + 1:][:1] == [d['name'] + '-header.img'], '退避先は --header-backup-file で指定します。')
    text = ctx.need_file('crypttab')
    ctx.require(text.startswith('# <name> <device> <password> <options>\n' + d['old_crypttab']), '既存のcrypttab行は変更しません。')
    new = [x.split() for x in text.splitlines() if x.split()[:1] == [d['name']]]
    ctx.require(len(new) == 1, f'{d["name"]} の行を1つ追加します。')
    f = new[0]
    ctx.require(len(f) == 4, 'crypttabは name device password options の4欄です。')
    ctx.require(f[1] == 'UUID=' + d['uuid'], 'デバイス名はsdX1が変わり得るのでUUID=で指定します。')
    ctx.require(f[2] == 'none', '鍵ファイルを置かず起動時に入力するならnoneです。')
    ctx.require(set(f[3].split(',')) >= {'luks', 'discard'}, 'オプションにluksとdiscardを入れます。')


SOL2 = """echo "cryptsetup luksHeaderBackup <<dev>> --header-backup-file <<name>>-header.img" > backup.txt
echo "<<name>> UUID=<<uuid>> none luks,discard" >> crypttab"""
mission(2, 'luksHeaderBackupとcrypttabで起動時に開く',
        '暗号化ボリュームはヘッダが壊れると復旧できません。cryptsetup luksHeaderBackupでヘッダを退避し、/etc/crypttab相当のファイルへluksOpenと同じ設定を書いて起動時に開けるようにします。',
        ['backup.txtにluksHeaderBackupの1行', 'crypttabへUUID指定の行を追加'], s2, c2, SOL2,
        ['echo "cp <<dev>> <<name>>-header.img" > backup.txt\necho "<<name>> <<dev>> none luks" >> crypttab',
         'echo "cryptsetup luksHeaderBackup <<dev>> --header-backup-file <<name>>-header.img" > backup.txt\necho "<<name>> UUID=<<uuid>> /root/key luks" > crypttab'],
        'ヘッダバックアップには鍵スロット情報が含まれ、バックアップを持つ人は当時のパスフレーズで開けるので、デバイスとは別の安全な場所に暗号化して保管します。crypttabの欄は 名前・デバイス（UUID=推奨）・鍵ファイルまたはnone・オプション。起動時にsystemd-cryptsetupがluksOpen相当を行います。',
        'デバイス名は変わることがあります。', 'luksHeaderBackupの--header-backup-fileと、crypttabの4欄を確認します。')


# ---------------------------------------------------------------- 3 wg0.conf
def s3(ctx):
    sub = 10 + secrets.randbelow(200)
    port = 51820 + secrets.randbelow(100)
    lap = secrets.token_hex(2)
    pub1, pub2 = b64key(), b64key()
    key = b64key()
    ctx.data.update(port=port, lap=lap, ip1=f'10.{sub}.0.2', pub1=pub1, pub2=pub2, ip2=f'10.{sub}.0.3', sub=sub)
    put(ctx, 'server.key', key + '\n')
    ctx.write('wg0.conf', f'[Interface]\nAddress = 10.{sub}.0.1/24\nListenPort = 51821\nPrivateKey = REPLACE_ME\n\n'
              f'[Peer]\n# laptop-{lap}\nPublicKey = {pub1}\nAllowedIPs = 0.0.0.0/0\n\n'
              f'[Peer]\n# branch\nPublicKey = {pub2}\nAllowedIPs = 10.{sub}.0.3/32, 192.168.50.0/24\n', mode=0o644)
    ctx.write('requirements.txt', f'サーバーのWireGuard設定ファイルを探して仕上げる。用意されたサーバー秘密鍵を見つけてPrivateKeyに設定し、ListenPortは{port}。全経路を引き込んでいるlaptop用ピアを調べ、そのピアに割り当てられたトンネルIPだけ（/32）をAllowedIPsに残す。他のピアは変更しない。秘密鍵を含むので設定ファイルのモードは600。\n')


def c3(ctx):
    need_ro(ctx)
    d = ctx.data
    secs = kv_conf(ctx.need_file('wg0.conf'))
    ifs = [s for s in secs if s[0] == '[Interface]']
    peers = [s[1] for s in secs if s[0] == '[Peer]']
    ctx.require(len(ifs) == 1 and len(peers) == 2, '[Interface]1つと[Peer]2つの構成を保ちます。')
    i = ifs[0][1]
    ctx.require(i.get('privatekey') == [ctx.need_file('server.key').strip()], 'PrivateKeyはserver.keyの値にします。')
    ctx.require(i.get('listenport') == [str(d['port'])], f'ListenPortは{d["port"]}です。')
    ctx.require(i.get('address') == [f'10.{d["sub"]}.0.1/24'], 'Addressは変更しません。')
    by = {p['publickey'][0]: p for p in peers}
    ctx.require(by[d['pub1']].get('allowedips') == [d['ip1'] + '/32'], 'ラップトップのAllowedIPsはそのピアのトンネルIPの/32だけです。')
    ctx.require(by[d['pub2']].get('allowedips') == [f'{d["ip2"]}/32, 192.168.50.0/24'], 'branchのピアは変更しません。')
    ctx.require(ctx.mode('wg0.conf') == 0o600, '秘密鍵を含む設定はchmod 600にします。')


SOL3 = """sed -i -e 's|^PrivateKey = .*|PrivateKey = '"$(cat server.key)"'|' -e 's|^ListenPort = .*|ListenPort = <<port>>|' wg0.conf
sed -i '/^# laptop-<<lap>>$/,/^$/ s|^AllowedIPs = .*|AllowedIPs = <<ip1>>/32|' wg0.conf
chmod 600 wg0.conf"""
mission(3, 'WireGuardのAllowedIPsを絞る',
        'サーバーのWireGuard設定と秘密鍵を探してください。ListenPortを指定値に合わせ、全経路を指定しているlaptop用ピアは割り当てられたトンネルIPだけに絞ります。他のピアは変更せず、秘密鍵を含む設定ファイルを所有者だけが読める権限にしてください。',
        ['PrivateKeyとListenPortを設定', 'laptopのAllowedIPsを/32へ', 'wg0.confをモード600に'], s3, c3, SOL3,
        ["sed -i 's|^AllowedIPs = .*|AllowedIPs = <<ip1>>/32|' wg0.conf\nsed -i 's|^PrivateKey = .*|PrivateKey = x|' wg0.conf",
         "sed -i 's|^PrivateKey = .*|PrivateKey = '\"$(cat server.key)\"'|; s|^ListenPort = .*|ListenPort = <<port>>|' wg0.conf\nchmod 600 wg0.conf"],
        'AllowedIPsはWireGuardの暗号鍵ルーティング表です。ピアごとに重ならない範囲を割り当てます。0.0.0.0/0はクライアント側の「全通信をVPNへ」設定で、サーバー側のピアに書くと他のピアと衝突します。wg-quickは秘密鍵を含む設定がグループ・他人に読めると警告します。',
        'ls -a で設定と秘密鍵を探し、cat でPeer名・公開鍵・トンネルIPの対応を読みます。', 'AllowedIPsの範囲アドレスで、対象Peerのブロックだけを変更します。秘密鍵を含むファイルの権限も設定します。')


# ---------------------------------------------------------------- 4 wg show
def s4(ctx):
    names = ['tokyo-' + secrets.token_hex(1), 'osaka-' + secrets.token_hex(1), 'nagoya-' + secrets.token_hex(1)]
    bad = SR.randrange(3)
    cause = secrets.choice(['key_mismatch', 'endpoint_mismatch'])
    peers = []
    for i, n in enumerate(names):
        peers.append(dict(name=n, key=b64key(), ip=f'198.51.100.{10 + i * 7}', port=51820 + secrets.randbelow(50), tun=f'10.9.0.{2 + i}'))
    ctx.data.update(peer=names[bad], cause=cause)
    show = '$ sudo wg show wg0\ninterface: wg0\n  public key: ' + b64key() + '\n  private key: (hidden)\n  listening port: 51820\n\n'
    for i, p in enumerate(peers):
        key, port = p['key'], p['port']
        if i == bad:
            if cause == 'key_mismatch':
                key = key[:5] + ('A' if key[5] != 'A' else 'B') + key[6:]
            else:
                port += 1
        show += f'peer: {key}\n  endpoint: {p["ip"]}:{port}\n  allowed ips: {p["tun"]}/32\n'
        if i == bad:
            show += '  transfer: 0 B received, 1.45 KiB sent\n\n'
        else:
            show += f'  latest handshake: {1 + secrets.randbelow(100)} seconds ago\n  transfer: 1.20 MiB received, 340.00 KiB sent\n\n'
    put(ctx, 'wgshow.txt', show)
    put(ctx, 'peers.txt', ''.join(f'{p["name"]} {p["key"]} {p["ip"]}:{p["port"]} {p["tun"]}/32\n' for p in peers))
    ctx.write('requirements.txt', 'wg showの出力で、handshakeが一度も成立せず受信が0Bのピアが1つあります。peers.txt（名前・公開鍵・期待するendpoint）と照合し、その名前と原因（公開鍵が違うならkey_mismatch、鍵は同じでendpointのポートが違うならendpoint_mismatch）をdiag.jsonへ（peer, cause）。'
              'あわせて新しい鍵ペアを作るwg genkeyとwg pubkeyのパイプラインを、秘密鍵が他人に読まれないようumask 077を付けてkeygen.txtへ1行で書く（実行はしません）。\n')


def c4(ctx):
    need_ro(ctx)
    j = rj(ctx, 'diag.json')
    ctx.require(j.get('peer') == ctx.data['peer'], 'handshakeがなく受信0Bのピアを、endpointと公開鍵でpeers.txtと照合します。')
    ctx.require(j.get('cause') == ctx.data['cause'], '原因は、公開鍵の不一致かendpointの不一致かを見分けます。')
    t = one_line(ctx, 'keygen.txt')
    ctx.require('umask 077' in t, '秘密鍵が読まれないようumask 077を先に付けます。')
    ctx.require(re.search(r'wg genkey\s*\|\s*tee\s+\S+\s*\|\s*wg pubkey', t), 'wg genkey | tee 秘密鍵ファイル | wg pubkey の形です。')
    ctx.require('>' in t, '公開鍵はリダイレクトで保存します。')


SOL4 = """echo '{"peer":"<<peer>>","cause":"<<cause>>"}' > diag.json
echo 'umask 077; wg genkey | tee privatekey | wg pubkey > publickey' > keygen.txt"""
mission(4, 'wg showを読んで握手できないピアを特定する',
        'VPNのピアの1つが繋がりません。wg showの出力ではlatest handshakeの有無とtransferが最初の手がかりです。鍵を作り直す場合に備え、wg genkeyの手順も整えます。',
        ['握手できないピアと原因をdiag.jsonへ', 'wg genkeyの1行をkeygen.txtへ'], s4, c4, SOL4,
        ['echo \'{"peer":"<<peer>>","cause":"firewall"}\' > diag.json\necho "wg genkey > privatekey" > keygen.txt',
         'echo \'{"peer":"tokyo-00","cause":"<<cause>>"}\' > diag.json\necho "wg genkey | wg pubkey" > keygen.txt'],
        'WireGuardは鍵が一致しないピアのパケットを黙って捨てるので、handshakeが無い・受信が0Bならまず公開鍵、次にendpoint・UDPポート・AllowedIPsを疑います。鍵の生成は wg genkey | tee privatekey | wg pubkey > publickey で、umaskで作成時から600にします。',
        'handshakeの有無とtransferを比べます。', 'wgshow.txtのpeer行とpeers.txtを突き合わせます。')


# ---------------------------------------------------------------- 5 OpenVPN
def s5(ctx):
    port = secrets.choice([1194, 443, 1195, 11194])
    proto = secrets.choice(['udp', 'tcp'])
    cipher = secrets.choice(['AES-256-GCM', 'AES-128-GCM'])
    ctx.data.update(port=port, proto=proto, cipher=cipher)
    put(ctx, 'server.conf', f'port {port}\nproto {proto}\ndev tun\nca ca.crt\ncert server.crt\nkey server.key\ndh dh.pem\nserver 10.8.0.0 255.255.255.0\n'
        f'tls-auth ta.key 0\ncipher {cipher}\nauth SHA256\nverify-client-cert none\nduplicate-cn\nkeepalive 10 120\npush "redirect-gateway def1"\n')
    wc = 'AES-128-GCM' if cipher == 'AES-256-GCM' else 'AES-256-GCM'
    ctx.write('client.ovpn', f'client\ndev tun\nproto {"tcp" if proto == "udp" else "udp"}\nremote vpn.dojo.test {1194 if port != 1194 else 443}\nca ca.crt\ncert client.crt\nkey client.key\ntls-auth ta.key 0\ncipher {wc}\nauth SHA256\n')
    ctx.write('requirements.txt', 'OpenVPNのclient.ovpnがserver.confと食い違って接続できない。proto・remoteのポート・cipherをserver.confに合わせ、tls-authの方向（サーバーが0ならクライアントは1）を直す。他の行は変えない。'
              'またserver.confのうち、クライアント証明書の検証を無効にする、または同じ証明書の同時利用を許す危険な行を、そのままの文字列でfindings.jsonへ（{"risky": [...]}、辞書順）。\n')


def c5(ctx):
    need_ro(ctx)
    d = ctx.data
    c = {}
    for ln in ctx.need_file('client.ovpn').splitlines():
        if ln.strip():
            k, _, v = ln.strip().partition(' ')
            c[k] = v
    ctx.require(c.get('proto') == d['proto'], 'protoはserver.confと同じにします。')
    ctx.require(c.get('remote') == f'vpn.dojo.test {d["port"]}', 'remoteのホストは維持しポートをserver.confのportに合わせます。')
    ctx.require(c.get('tls-auth') == 'ta.key 1', 'tls-authはサーバー0に対しクライアントは方向1です。')
    ctx.require(c.get('cipher') == d['cipher'], 'cipherを揃えます。')
    ctx.require(c.get('client') == '' and c.get('dev') == 'tun' and c.get('auth') == 'SHA256' and c.get('cert') == 'client.crt', 'その他の行は変更しません。')
    ctx.require(rj(ctx, 'findings.json') == {'risky': ['duplicate-cn', 'verify-client-cert none']}, '危険な行は verify-client-cert none と duplicate-cn です。')


SOL5 = r"""sed -i -e 's/^proto .*/proto <<proto>>/' -e 's/^remote \(\S*\) .*/remote \1 <<port>>/' -e 's/^tls-auth ta.key 0/tls-auth ta.key 1/' -e 's/^cipher .*/cipher <<cipher>>/' client.ovpn
echo '{"risky":["duplicate-cn","verify-client-cert none"]}' > findings.json"""
mission(5, 'OpenVPNのserver.confとclient.ovpnを突き合わせる',
        'OpenVPNのserver.confとclient.ovpnは、proto・port・cipher・tls-authの鍵方向が一致して初めて繋がります。さらにserver.confには脆弱な設定が混ざっています。',
        ['client.ovpnをserver.confに合わせる', '危険な設定行をfindings.jsonへ'], s5, c5, SOL5,
        ["sed -i 's/^proto .*/proto <<proto>>/' client.ovpn\necho '{\"risky\":[\"duplicate-cn\"]}' > findings.json",
         "sed -i 's/^tls-auth ta.key 0/tls-auth ta.key 0/' client.ovpn\necho '{\"risky\":[\"duplicate-cn\",\"keepalive 10 120\"]}' > findings.json"],
        'tls-authのkey-directionは片側が0なら反対側は1です。cipherやauthが違うとTLSは成立しても接続後に失敗します。verify-client-cert noneはクライアント証明書を検証せず、duplicate-cnは同じ証明書の使い回しを許すので、失効や追跡が効かなくなります。',
        'サーバーとクライアントで揃える項目を洗い出します。', 'sedでclient.ovpnの該当行だけ置換します。')


# ---------------------------------------------------------------- 6 ssh tunnels
def s6(ctx):
    t = secrets.token_hex(2)
    d = dict(user='ops-' + t, bast='bastion.dojo.test', dbh=f'db-{t}.internal', alias='db-' + t,
             lp=15000 + secrets.randbelow(2000), rp=18000 + secrets.randbelow(2000), sp=1080 + secrets.randbelow(100))
    ctx.data.update(d)
    ctx.write('ssh_config', f'Host bastion\n    HostName {d["bast"]}\n    User {d["user"]}\n')
    ctx.data['ro_bastion'] = f'Host bastion\n    HostName {d["bast"]}\n    User {d["user"]}\n'
    ctx.write('requirements.txt', f'踏み台bastion（{d["user"]}@{d["bast"]}、ssh_configにalias bastion）経由で作業する。コマンドは全てシェルを開かない -N 付き。\n'
              f'l.txt: 手元のlocalhost:{d["lp"]}を踏み台の先の{d["dbh"]}:5432へ転送するssh -L。\n'
              f'r.txt: 手元のlocalhost:8080を、踏み台のループバックの{d["rp"]}番から見えるようにするssh -R（外部公開はしない）。\n'
              f'd.txt: 手元の{d["sp"]}番にSOCKSプロキシを立てるssh -D。\n'
              f'jump.txt: ssh -Jでbastionを経由して dbadmin@{d["dbh"]} へ入るコマンド。\n'
              f'ssh_configには同じ経路をProxyJumpで書いたHost {d["alias"]}（HostName {d["dbh"]}、User dbadmin、ProxyJump bastion）を追加（bastionの既存ブロックは変更しない）。\n')


def opt_args(t, flag):
    out = []
    for i, x in enumerate(t):
        if x == flag and i + 1 < len(t):
            out.append(t[i + 1])
        elif x.startswith(flag) and len(x) > 2 and not x.startswith('--'):
            out.append(x[2:])
    return out


def c6(ctx):
    d = ctx.data
    dest = lambda t: t[-1] in ('bastion', d['bast']) or t[-1] == f'{d["user"]}@{d["bast"]}' or t[-1] == f'{d["user"]}@bastion'
    for fn, flag, ok in (('l.txt', '-L', {f'{d["lp"]}:{d["dbh"]}:5432', f'localhost:{d["lp"]}:{d["dbh"]}:5432', f'127.0.0.1:{d["lp"]}:{d["dbh"]}:5432'}),
                         ('r.txt', '-R', {f'{d["rp"]}:localhost:8080', f'127.0.0.1:{d["rp"]}:localhost:8080', f'localhost:{d["rp"]}:localhost:8080', f'{d["rp"]}:127.0.0.1:8080'}),
                         ('d.txt', '-D', {str(d['sp']), f'127.0.0.1:{d["sp"]}', f'localhost:{d["sp"]}'})):
        t = toks(ctx, one_line(ctx, fn))
        ctx.require(t[0] == 'ssh' and '-N' in t, f'{fn}: ssh -N で始めます。')
        ctx.require(set(opt_args(t, flag)) & ok and len(opt_args(t, flag)) == 1, f'{fn}: {flag} の指定が違います（-Lは手元→先、-Rは先→手元、-Dは動的SOCKS）。')
        ctx.require(dest(t), f'{fn}: 最後に踏み台（bastion）を指定します。')
    ctx.require('0.0.0.0' not in ctx.need_file('r.txt') and '*:' not in ctx.need_file('r.txt'), '-Rを全インターフェースで公開してはいけません。')
    t = toks(ctx, one_line(ctx, 'jump.txt'))
    ctx.require(t[0] == 'ssh' and '-J' in t and 'bastion' in t[t.index('-J') + 1], 'ssh -J 踏み台 宛先 の形です。')
    ctx.require(t[-1] == f'dbadmin@{d["dbh"]}', '宛先は dbadmin@DBホスト です。')
    secs = kv_conf(ctx.need_file('ssh_config'))
    ctx.require(any(s[0] == 'host bastion' and s[1] == {'hostname': [d['bast']], 'user': [d['user']]} for s in secs), 'bastionの既存ブロックは変更しません。')
    blk = [s[1] for s in secs if s[0] == 'host ' + d['alias']]
    ctx.require(len(blk) == 1, f'Host {d["alias"]} のブロックを追加します。')
    b = blk[0]
    ctx.require(b.get('hostname') == [d['dbh']] and b.get('user') == ['dbadmin'], 'HostNameとUserを設定します。')
    ctx.require(b.get('proxyjump') == ['bastion'] and 'proxycommand' not in b and b.get('forwardagent') in (None, ['no']), 'ProxyJump bastion で経由させます（agent forwardingやProxyCommandは使わない）。')


SOL6 = """echo "ssh -N -L <<lp>>:<<dbh>>:5432 <<user>>@<<bast>>" > l.txt
echo "ssh -N -R 127.0.0.1:<<rp>>:localhost:8080 <<user>>@<<bast>>" > r.txt
echo "ssh -N -D <<sp>> bastion" > d.txt
echo "ssh -J <<user>>@<<bast>> dbadmin@<<dbh>>" > jump.txt
printf '\\nHost <<alias>>\\n    HostName <<dbh>>\\n    User dbadmin\\n    ProxyJump bastion\\n' >> ssh_config"""
mission(6, 'ssh -L/-R/-DとProxyJumpで踏み台を越える',
        '踏み台サーバー経由でDBへ入ったり、手元のサービスを一時的に見せたりします。ssh -L（ローカル転送）、ssh -R（リモート転送）、ssh -D（SOCKS）の向きを混同しやすく、ProxyJumpやssh -Jを使えば多段接続が1行で書けます。',
        ['-L/-R/-Dの3コマンドを作成', 'ssh -Jのコマンド', 'ssh_configにProxyJumpのブロックを追加'], s6, c6, SOL6,
        ['echo "ssh -N -L <<dbh>>:5432:<<lp>> bastion" > l.txt\necho "ssh -N -R 0.0.0.0:<<rp>>:localhost:8080 bastion" > r.txt\necho "ssh -N -D <<sp>> bastion" > d.txt',
         'echo "ssh -N -L <<lp>>:<<dbh>>:5432 bastion" > l.txt\necho "ssh -N -R <<rp>>:localhost:8080 bastion" > r.txt\necho "ssh -N -D <<sp>> bastion" > d.txt\necho "ssh -J bastion <<dbh>>" > jump.txt'],
        '-L 手元ポート:宛先:宛先ポート は手元で待ち受けて踏み台の先へ、-R 踏み台側ポート:宛先:ポート は踏み台で待ち受けて手元側へ、-D ポート は動的SOCKSプロキシです。-Nはシェルを開かず転送だけ行います。-Rを0.0.0.0にするとGatewayPortsが許せば外部に公開されます。ProxyJumpは踏み台に秘密鍵や認証エージェントを渡さずにTCPだけ中継するため、agent forwardingより安全です。',
        '転送の向きを確認します。', '-L bind:host:port の3つ組を順に書きます。')


# ---------------------------------------------------------------- 7 ssh-agent / ssh_config
def s7(ctx):
    t = secrets.token_hex(2)
    secs = secrets.choice([1800, 3600, 7200])
    ctx.data.update(secs=secs, build='build-' + t, tag=t)
    ctx.write('ssh_config', f'Host *\n    ForwardAgent yes\n    StrictHostKeyChecking no\n    ServerAliveInterval 60\n\nHost bastion\n    HostName bastion.dojo.test\n    User ops\n\nHost build-{t}\n    HostName build-{t}.internal\n    User ci\n    ForwardAgent yes\n')
    ctx.write('requirements.txt', f'ssh-agentの認証ソケットをagent forwardingで渡すと、踏み台のrootが転送ソケットを使って利用者になりすませる。クライアントのssh_configを直す: 全ての ForwardAgent yes を no にし、StrictHostKeyChecking noをaskに、Host *へIdentitiesOnly yesを追加。ServerAliveInterval 60とbastionのブロックは維持。build-{t}はbastion経由（ProxyJump bastion）に変える。\n'
              f'agent.txtには3行: ssh-agentを起動して環境へ反映するeval行、{secs}秒で期限切れになるssh-add（~/.ssh/id_ed25519）、登録済みを確認するssh-add -l。\n')


def c7(ctx):
    d = ctx.data
    secs = kv_conf(ctx.need_file('ssh_config'))
    ctx.require(not any('yes' in [v.lower() for v in s[1].get('forwardagent', [])] for s in secs), 'ForwardAgent yes を全て無くします。')
    star = [s[1] for s in secs if s[0] == 'host *']
    ctx.require(len(star) == 1, 'Host * ブロックは1つです。')
    ctx.require(star[0].get('forwardagent') == ['no'], 'Host *にForwardAgent noを置きます。')
    ctx.require(star[0].get('stricthostkeychecking') in (['ask'], ['yes'], ['accept-new']), 'StrictHostKeyChecking noは中間者攻撃を見逃します。')
    ctx.require(star[0].get('identitiesonly') == ['yes'] and star[0].get('serveraliveinterval') == ['60'], 'IdentitiesOnly yesを追加し、他の設定は維持します。')
    ctx.require(any(s[0] == 'host bastion' and s[1].get('hostname') == ['bastion.dojo.test'] for s in secs), 'bastionのブロックは維持します。')
    b = [s[1] for s in secs if s[0] == 'host ' + d['build']]
    ctx.require(len(b) == 1 and b[0].get('proxyjump') == ['bastion'], f'{d["build"]}はProxyJump bastionにします。')
    ls = lines_of(ctx, 'agent.txt')
    ctx.require(len(ls) == 3, 'agent.txtは3行です。')
    ctx.require(re.fullmatch(r'eval\s+"?\$\(ssh-agent -s\)"?', ls[0].strip()), '1行目は eval "$(ssh-agent -s)" です。')
    t = toks(ctx, ls[1])
    ctx.require(t[:1] == ['ssh-add'] and '-t' in t and t[t.index('-t') + 1] == str(d['secs']) and t[-1].endswith('id_ed25519'), f'2行目は ssh-add -t {d["secs"]} ~/.ssh/id_ed25519 です。')
    ctx.require(ls[2].split() == ['ssh-add', '-l'], '3行目は ssh-add -l です。')


SOL7 = """cat > ssh_config <<'EOF'
Host *
    ForwardAgent no
    StrictHostKeyChecking ask
    IdentitiesOnly yes
    ServerAliveInterval 60

Host bastion
    HostName bastion.dojo.test
    User ops

Host <<build>>
    HostName <<build>>.internal
    User ci
    ProxyJump bastion
EOF
cat > agent.txt <<'EOF'
eval "$(ssh-agent -s)"
ssh-add -t <<secs>> ~/.ssh/id_ed25519
ssh-add -l
EOF"""
mission(7, 'ssh-agentとagent forwardingの危険を塞ぐ',
        'ssh-agentに鍵を預けてssh-addで登録すると便利ですが、ForwardAgent（agent forwarding）をむやみに有効にすると接続先のrootがソケット経由で鍵を使えます。クライアントのssh_configを堅牢にします。',
        ['ssh_configを直す', 'agent.txtにssh-agent起動・期限付きssh-add・確認'], s7, c7, SOL7,
        ["sed -i 's/ForwardAgent yes/ForwardAgent no/' ssh_config\nprintf 'ssh-agent\\nssh-add\\nssh-add -l\\n' > agent.txt",
         "cat > agent.txt <<'EOF'\neval \"$(ssh-agent -s)\"\nssh-add -t <<secs>> ~/.ssh/id_ed25519\nssh-add -l\nEOF"],
        'agent forwardingは鍵そのものは渡しませんが、接続先で認証要求を代行できるソケットを渡します。多段接続にはProxyJump/-Jを使います。ssh-add -t で登録に期限を付け、ssh-add -D で全削除します。ssh_configのHost *にIdentitiesOnly yesを置くと、無関係な鍵を片端から試して送ることを避けられます。',
        'ForwardAgentの無効化と、代わりの多段接続方法を考えます。', 'ssh_configを書き直し、agent.txtはヒアドキュメントで書きます。')


# ---------------------------------------------------------------- 8 sshd_config
def s8(ctx):
    users = ['deploy-' + secrets.token_hex(2), 'alice-' + secrets.token_hex(2)]
    ctx.data.update(users=' '.join(users), u1=users[0], u2=users[1])
    ctx.write('sshd_config', 'Port 22\nPermitRootLogin yes\nPubkeyAuthentication no\nPasswordAuthentication yes\nPermitEmptyPasswords yes\nMaxAuthTries 10\nX11Forwarding yes\nClientAliveInterval 0\n'
              '#AllowUsers\nSubsystem sftp /usr/lib/openssh/sftp-server\n\nMatch Address 10.0.0.0/8\n    PasswordAuthentication yes\n')
    ctx.write('requirements.txt', f'sshd_configを堅牢化する。rootログイン禁止、パスワード認証禁止（Matchブロックでの許可も撤去）、公開鍵認証を有効、空パスワード禁止、MaxAuthTries 3、X11Forwarding禁止、ClientAliveInterval 300、AllowUsersは{users[0]}と{users[1]}だけ。PortとSubsystem sftpの行は維持。\n')


def c8(ctx):
    d = ctx.data
    secs = kv_conf(ctx.need_file('sshd_config'))
    g = secs[0][1]
    for k, v in (('permitrootlogin', 'no'), ('passwordauthentication', 'no'), ('pubkeyauthentication', 'yes'), ('permitemptypasswords', 'no'),
                 ('maxauthtries', '3'), ('x11forwarding', 'no'), ('clientaliveinterval', '300')):
        ctx.require(g.get(k) == [v], f'{k} は {v} 1行にします。')
    ctx.require(len(g.get('allowusers', [])) == 1 and sorted(g['allowusers'][0].split()) == sorted(d['users'].split()), f'AllowUsers は {d["users"]} だけです。')
    ctx.require(g.get('port') == ['22'] and g.get('subsystem') == ['sftp /usr/lib/openssh/sftp-server'], 'PortとSubsystemは維持します。')
    ctx.require(len(secs) == 1, 'パスワードを許すMatchブロックは撤去します。')


SOL8 = """sed -i -e 's/^PermitRootLogin .*/PermitRootLogin no/' -e 's/^PubkeyAuthentication .*/PubkeyAuthentication yes/' -e 's/^PasswordAuthentication .*/PasswordAuthentication no/' -e 's/^PermitEmptyPasswords .*/PermitEmptyPasswords no/' -e 's/^MaxAuthTries .*/MaxAuthTries 3/' -e 's/^X11Forwarding .*/X11Forwarding no/' -e 's/^ClientAliveInterval .*/ClientAliveInterval 300/' -e '/^Match/,$d' sshd_config
echo "AllowUsers <<users>>" >> sshd_config"""
mission(8, 'sshd_configを堅牢化する',
        'サーバー側のsshd_configが初期のまま緩んでいます。ssh_configがクライアント設定なのに対し、sshd_configはサーバーの受け入れ設定です。sshdは最初に現れた値を採用し、Matchブロックは条件に合う接続で上書きする点に注意します。',
        ['危険な設定を安全な値へ', 'Matchの許可を撤去', 'AllowUsersを設定'], s8, c8, SOL8,
        ["sed -i -e 's/^PermitRootLogin .*/PermitRootLogin no/' -e 's/^PasswordAuthentication .*/PasswordAuthentication no/' sshd_config\necho 'AllowUsers <<users>>' >> sshd_config",
         "sed -i 's/^PermitRootLogin .*/PermitRootLogin no/' sshd_config\necho 'PasswordAuthentication no' >> sshd_config"],
        'sshd_configはキーワードごとに最初の値が有効です。末尾に足しただけでは上書きできません。Matchは特定条件でグローバル設定を変えるので、パスワード許可が残ると穴になります。反映前にsshd -tで構文確認し、別の端末を残したまま再読み込みするのが安全です。',
        '最初に現れた設定が有効であることに注意します。', 'sedで各行を置換し、Match以降を削除してAllowUsersを追加します。')


# ---------------------------------------------------------------- 9 known_hosts
def s9(ctx):
    host = 'srv-' + secrets.token_hex(2) + '.dojo.test'
    legit = SR.random() < 0.5
    old, new = fp(), fp()
    line = 2 + secrets.randbelow(3)
    kh = [f'other{i}.dojo.test {pubkey("x")}\n' for i in range(4)]
    kh.insert(line - 1, f'{host} {pubkey("old")}\n')
    oob = new if legit else fp()
    ctx.data.update(host=host, legit=legit, verdict='accept' if legit else 'reject', line=line, cmd=f'ssh-keygen -R {host}' if legit else f'ssh-keygen -F {host}')
    put(ctx, 'known_hosts', ''.join(kh))
    put(ctx, 'warning.txt', '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n'
        f'The fingerprint for the ED25519 key sent by the remote host is\n{new}.\nOffending ED25519 key in /home/trainee/.ssh/known_hosts:{line}\nHost key verification failed.\n')
    put(ctx, 'ticket.txt', f'件名: {host} のホスト鍵について\n'
        f'サーバー側コンソールで ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub を実行した結果（sshd_configのHostKeyが指すED25519鍵）: {oob}\n'
        f'再構築作業: {"本日実施済み（OS再インストール）" if legit else "予定なし。変更の連絡も受けていない"}\n')
    ctx.write('requirements.txt', f'{host} に繋ぐとHost key変更の警告が出た。ticket.txtの帯域外の指紋と、warning.txtで提示された指紋を照合して判断し、decision.json（verdict: accept か reject、line: known_hostsで問題の行番号）を書く。'
              'acceptなら古い鍵だけをssh-keygen -Rで消す1行、rejectなら鍵を消さず該当行をssh-keygen -Fで確認する1行を、cmd.txtへ（実行はしません。known_hostsは変更しない）。\n')


def c9(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'decision.json')
    ctx.require(j.get('verdict') == d['verdict'], '提示された指紋が帯域外の指紋と一致し再構築の連絡もあるときだけacceptです。違えば中間者攻撃を疑いrejectします。')
    ctx.require(j.get('line') == d['line'], '問題の行番号はwarning.txtのknown_hosts:N の N です。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t == d['cmd'].split(), f'cmd.txtは {d["cmd"]} です。')


SOL9 = """echo '{"verdict":"<<verdict>>","line":<<line>>}' > decision.json
echo "<<cmd>>" > cmd.txt"""
mission(9, 'known_hostsの警告を指紋で判断する',
        'ssh接続時に「REMOTE HOST IDENTIFICATION HAS CHANGED」と出ました。known_hostsを消せば繋がりますが、本当に再構築なのか中間者攻撃なのかを、サーバーのHostKeyの指紋（帯域外で入手）と照合して決めます。',
        ['指紋を照合しdecision.jsonへ', '対応する1行をcmd.txtへ'], s9, c9, SOL9,
        ['echo \'{"verdict":"accept","line":1}\' > decision.json\necho "rm known_hosts" > cmd.txt',
         'echo \'{"verdict":"<<verdict>>","line":<<line>>}\' > decision.json\necho "ssh -o StrictHostKeyChecking=no <<host>>" > cmd.txt'],
        '警告を無視してknown_hostsを消す・StrictHostKeyCheckingを切るのは最悪の対応です。まず別経路（コンソール、チケット）でホスト鍵の指紋を確認し、一致して正当な理由があればssh-keygen -R ホスト で古い行だけ消して再接続します。一致しなければ接続せず管理者へ連絡します。',
        '再構築の事実と指紋の両方を確認します。', 'warning.txtの指紋とticket.txtを比べ、行番号はOffending行から読みます。')


# ---------------------------------------------------------------- 10 s_client
def s10(ctx):
    cause = secrets.choice(['expired', 'self_signed', 'hostname_mismatch'])
    host = 'www-' + secrets.token_hex(2) + '.dojo.test'
    code = {'expired': 10, 'self_signed': 18, 'hostname_mismatch': 62}[cause]
    now = datetime(2026, 11, 21)
    na = now - timedelta(days=3 + secrets.randbelow(30)) if cause == 'expired' else now + timedelta(days=60)
    fmt = lambda t: t.strftime('%b %d 00:00:00 %Y GMT')
    cn = host if cause != 'hostname_mismatch' else 'other-' + secrets.token_hex(2) + '.dojo.test'
    issuer = cn if cause == 'self_signed' else 'Dojo Test CA'
    msg = {10: 'certificate has expired', 18: 'self-signed certificate',
           62: f"Hostname mismatch, certificate is not valid for '{host}'"}[code]
    ctx.data.update(cause=cause, code=code, na=fmt(na), cn=cn, host=host)
    out = f'$ openssl s_client -connect {host}:443 -servername {host} </dev/null\nCONNECTED(00000003)\n'
    if cause != 'hostname_mismatch':
        out += f'depth=0 CN = {cn}\nverify error:num={code}:{msg}\n'
    out += f'---\nCertificate chain\n 0 s:CN = {cn}\n   i:CN = {issuer}\n---\nSSL handshake has read 1520 bytes\nProtocol  : TLSv1.3\n'
    out += f'Verify return code: {code} ({msg})\n'
    put(ctx, 'sclient.txt', out)
    put(ctx, 'cert-dump.txt', f'$ openssl x509 -in cert.pem -noout -subject -issuer -enddate\nsubject=CN = {cn}\nissuer=CN = {issuer}\nnotAfter={fmt(na)}\n')
    ctx.write('requirements.txt', f'https://{host} に繋がらない。まず状況を再現・確認するコマンドを書く。cmd.txtの1行目は、SNIを指定して443番へ繋ぐopenssl s_clientコマンド、2行目はcert.pemから終了日・subject・issuerを表示するopenssl x509コマンド（実行はしません）。'
              '次に採取済みのsclient.txtとcert-dump.txtから原因をdiag.jsonへ（cause: expired / self_signed / hostname_mismatch、verify_code: 数値、not_after: 終了日の文字列そのまま、cn）。\n')


def c10(ctx):
    need_ro(ctx)
    d = ctx.data
    ls = lines_of(ctx, 'cmd.txt')
    ctx.require(len(ls) == 2, 'cmd.txtは2行です。')
    a = toks(ctx, ls[0])
    ctx.require(a[:2] == ['openssl', 's_client'] and '-connect' in a and a[a.index('-connect') + 1] == d['host'] + ':443', '1行目は openssl s_client -connect ホスト:443 です。')
    ctx.require('-servername' in a and a[a.index('-servername') + 1] == d['host'], '-servername でSNIを指定します。')
    b = toks(ctx, ls[1])
    ctx.require(b[:2] == ['openssl', 'x509'] and '-in' in b and b[b.index('-in') + 1] == 'cert.pem' and '-noout' in b, '2行目は openssl x509 -in cert.pem -noout ... です。')
    ctx.require({'-enddate', '-subject', '-issuer'} <= set(b), '-enddate -subject -issuer を指定します。')
    j = rj(ctx, 'diag.json')
    ctx.require(j.get('cause') == d['cause'] and j.get('verify_code') == d['code'], '原因とVerify return codeを写します。')
    ctx.require(j.get('not_after') == d['na'] and j.get('cn') == d['cn'], 'notAfterとCNを出力のまま写します。')


SOL10 = """printf '%s\\n' "openssl s_client -connect <<host>>:443 -servername <<host>>" "openssl x509 -in cert.pem -noout -enddate -subject -issuer" > cmd.txt
echo '{"cause":"<<cause>>","verify_code":<<code>>,"not_after":"<<na>>","cn":"<<cn>>"}' > diag.json"""
mission(10, 'openssl s_clientとx509でTLS接続エラーを切り分ける',
        'サイトのTLS接続が失敗します。openssl s_clientで実際に握手してVerify return codeを読み、openssl x509で証明書の期限・発行者・名前を見て原因を切り分けます。',
        ['確認コマンドをcmd.txtへ', '原因をdiag.jsonへ'], s10, c10, SOL10,
        ['echo "curl -k https://<<host>>" > cmd.txt\necho \'{"cause":"expired"}\' > diag.json',
         'printf \'%s\\n\' "openssl s_client -connect <<host>>:443" "openssl x509 -in cert.pem -noout -enddate" > cmd.txt\necho \'{"cause":"<<cause>>","verify_code":0}\' > diag.json'],
        'Verify return code 10は期限切れ、18は自己署名、62はホスト名不一致（codeはOpenSSLのX509エラー番号）です。-servernameを付けないと複数サイトを持つサーバーで別の証明書が返ります。curl -kは検証を無効化してしまうので原因調査には使えません。',
        'Verify return codeが手がかりです。', 'recordedの2つのファイルから値を写します。')


# ---------------------------------------------------------------- 11 CA / CSR (real openssl)
def s11(ctx):
    ctx.data.update(host='api-' + secrets.token_hex(3) + '.dojo.test', tag=secrets.token_hex(2))
    ctx.write('requirements.txt', f'訓練用の私設認証局を作り、サーバー証明書を発行する。(1) 自己署名のCA（ca.key / ca.crt、CN=Dojo Test CA {ctx.data["tag"]}、CA:TRUE）をopenssl reqで。(2) サーバーの鍵server.keyとCSR（server.csr、CN={ctx.data["host"]}）をopenssl reqで。'
              f'(3) CAでCSRに署名しserver.crtを発行（SANにDNS:{ctx.data["host"]}を入れる）。(4) 秘密鍵ca.keyとserver.keyはモード600。\n')


def c11(ctx):
    d = ctx.data
    for f in ('ca.key', 'ca.crt', 'server.key', 'server.csr', 'server.crt'):
        ctx.need_file(f)
    ctx.require(f'CN = Dojo Test CA {d["tag"]}' in openssl(ctx, 'x509', '-in', 'ca.crt', '-noout', '-subject'), 'CAのCNを指定どおりにします。')
    ctx.require('CA:TRUE' in openssl(ctx, 'x509', '-in', 'ca.crt', '-noout', '-ext', 'basicConstraints'), 'CAはbasicConstraintsでCA:TRUEにします。')
    ctx.require(openssl(ctx, 'x509', '-in', 'ca.crt', '-noout', '-pubkey') == openssl(ctx, 'pkey', '-in', 'ca.key', '-pubout'), 'ca.crtとca.keyが対応していません。')
    openssl(ctx, 'req', '-in', 'server.csr', '-noout', '-verify')
    ctx.require(d['host'] in openssl(ctx, 'req', '-in', 'server.csr', '-noout', '-subject'), 'CSRのCNにサーバー名を入れます。')
    ctx.require('CN = Dojo Test CA' in openssl(ctx, 'x509', '-in', 'server.crt', '-noout', '-issuer'), 'server.crtの発行者はCAでなければなりません（自己署名にしない）。')
    ctx.require('OK' in openssl(ctx, 'verify', '-CAfile', 'ca.crt', 'server.crt'), 'CAでserver.crtを検証できません。')
    ctx.require('DNS:' + d['host'] in openssl(ctx, 'x509', '-in', 'server.crt', '-noout', '-ext', 'subjectAltName'), 'SANにサーバー名を入れて署名します。')
    ctx.require(openssl(ctx, 'x509', '-in', 'server.crt', '-noout', '-pubkey') == openssl(ctx, 'pkey', '-in', 'server.key', '-pubout'), 'server.crtとserver.keyが対応していません。')
    ctx.require(ctx.mode('ca.key') == 0o600 and ctx.mode('server.key') == 0o600, '秘密鍵はchmod 600にします。')


SOL11 = """openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 30 -subj "/CN=Dojo Test CA <<tag>>" -addext basicConstraints=critical,CA:TRUE
openssl req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=<<host>>"
printf 'subjectAltName=DNS:<<host>>\\n' > san.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 20 -extfile san.ext -out server.crt
chmod 600 ca.key server.key"""
mission(11, 'openssl reqで自己署名CAを作りCSRに署名する',
        'テスト環境のTLS用に、自己署名の認証局（CA）を作り、サーバーのCSR（証明書署名要求）をopenssl reqで作り、CAでopenssl x509 -reqして証明書を発行します。',
        ['CAの鍵と自己署名証明書', 'サーバー鍵とCSR', 'CAで署名しSANを含める'], s11, c11, SOL11,
        ['openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out server.crt -days 20 -subj "/CN=<<host>>"',
         'openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 30 -subj "/CN=Dojo Test CA <<tag>>"\nopenssl req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=<<host>>"\ncp ca.crt server.crt'],
        '私設CAの流れは、CAの鍵と自己署名証明書→サーバー鍵とCSR→CAがCSRに署名、です。CSRは公開鍵と名前の署名付き依頼で、秘密鍵は含みません。最近のTLSクライアントはCNでなくSANを見るので、署名時に-extfileでsubjectAltNameを付けます。自己署名のサーバー証明書をそのまま配るとCAとして信頼を一括管理できません。',
        'CAとサーバーで鍵を分けます。', 'openssl req -x509（CA）、openssl req -new（CSR）、openssl x509 -req（署名）の順です。')


# ---------------------------------------------------------------- 12 certbot
def s12(ctx):
    doms = [f'{n}-{secrets.token_hex(2)}.dojo.test' for n in ('www', 'shop', 'blog')]
    bad = secrets.choice(doms)
    cause = secrets.choice(['firewall', 'webroot', 'dns'])
    detail = {'firewall': f'203.0.113.9: Fetching http://{bad}/.well-known/acme-challenge/Xk3q: Timeout during connect (likely firewall problem)',
              'webroot': f'203.0.113.9: Invalid response from http://{bad}/.well-known/acme-challenge/Xk3q: 404',
              'dns': f'DNS problem: NXDOMAIN looking up A for {bad} - check that a DNS record exists for this domain'}[cause]
    typ = {'firewall': 'connection', 'webroot': 'unauthorized', 'dns': 'dns'}[cause]
    ctx.data.update(bad=bad, cause=cause)
    out = '$ sudo certbot renew --dry-run\nSaving debug log to /var/log/letsencrypt/letsencrypt.log\n\n- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -\n'
    for dm in doms:
        out += f'Processing /etc/letsencrypt/renewal/{dm}.conf\n- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -\nSimulating renewal of an existing certificate for {dm}\n'
        if dm == bad:
            out += f'Certbot failed to authenticate some domains (authenticator: webroot). The Certificate Authority reported these problems:\n  Domain: {dm}\n  Type:   {typ}\n  Detail: {detail}\n\n'
        else:
            out += f'Congratulations, all simulated renewals succeeded: /etc/letsencrypt/live/{dm}/fullchain.pem (success)\n'
    out += f'\nFailed simulated renewals: 1 renew failure(s)\n  /etc/letsencrypt/live/{bad}/fullchain.pem (failure)\n'
    put(ctx, 'renew.log', out)
    ctx.write('requirements.txt', 'Let\'s Encryptの証明書の自動更新をcertbot renew --dry-runで検証したら一部が失敗した。renew.logを読み、失敗したドメインと原因（Timeout during connect=firewall / 404=webroot / NXDOMAIN=dns）をdiag.jsonへ（failed: ドメインの配列, cause）。'
              '修正後に失敗した証明書だけ再検証するcertbot renew --dry-run --cert-name の1行をcmd.txtへ（実行はしません）。\n')


def c12(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'diag.json')
    ctx.require(j.get('failed') == [d['bad']], '失敗したドメインだけを配列で書きます。')
    ctx.require(j.get('cause') == d['cause'], 'Detail行で原因を見分けます。')
    ctx.require(toks(ctx, one_line(ctx, 'cmd.txt')) == ['certbot', 'renew', '--dry-run', '--cert-name', d['bad']], '再検証は certbot renew --dry-run --cert-name 対象 です。')


SOL12 = """echo '{"failed":["<<bad>>"],"cause":"<<cause>>"}' > diag.json
echo "certbot renew --dry-run --cert-name <<bad>>" > cmd.txt"""
mission(12, 'certbot renew --dry-runの失敗を読む',
        'certbot renewは期限が近い証明書を更新します。本番で失敗する前にrenew --dry-run（テスト用環境でのシミュレーション）を実行すると、Let\'s Encryptのチャレンジ検証の失敗を先に見つけられます。',
        ['失敗ドメインと原因をdiag.jsonへ', '再検証のcertbotをcmd.txtへ'], s12, c12, SOL12,
        ['echo \'{"failed":["<<bad>>"],"cause":"dns"}\' > diag.json\necho "certbot renew --force-renewal" > cmd.txt',
         'echo \'{"failed":["<<bad>>"],"cause":"<<cause>>"}\' > diag.json\necho "certbot renew --dry-run" > cmd.txt'],
        'HTTP-01チャレンジは80番で /.well-known/acme-challenge/ を取得するため、Timeoutはファイアウォール・NAT、404はwebrootの指定ミス、NXDOMAINはDNS設定を疑います。--dry-runはステージング環境を使い本番のレート制限を消費しません。--force-renewalを乱発すると上限に達します。',
        'Typeと Detail行が原因を示します。', 'renew.logの失敗ブロックを読みます。')


# ---------------------------------------------------------------- 13 strongSwan
def s13(ctx):
    bits = secrets.choice(['128', '256'])
    ike = f'aes{bits}-sha256-modp2048'
    esp = f'aes{bits}-sha256'
    a, b = 10 + secrets.randbelow(200), 16 + secrets.randbelow(10)
    ctx.data.update(ike=ike, esp=esp, ls=f'10.{a}.0.0/24', rs=f'172.{b}.5.0/24')
    ctx.write('ipsec.conf', f'config setup\n    charondebug="ike 1"\n\nconn branch\n    keyexchange=ikev2\n    left=203.0.113.10\n    leftsubnet=10.{a}.0.0/24\n    right=198.51.100.20\n    rightsubnet=172.{b}.9.0/24\n    ike=aes256-sha384-modp3072\n    esp=aes256-sha384\n    authby=secret\n    auto=start\n')
    put(ctx, 'peer-log.txt', f'charon: 09[IKE] received proposals: IKE:AES_CBC_{bits}/HMAC_SHA2_256_128/PRF_HMAC_SHA2_256/MODP_2048\ncharon: 09[IKE] configured proposals: IKE:AES_CBC_256/HMAC_SHA2_384_192/PRF_HMAC_SHA2_384/MODP_3072\n'
        f'charon: 09[IKE] no matching proposal found, sending NO_PROPOSAL_CHOSEN\ncharon: 11[CFG] received ESP proposals: ESP:AES_CBC_{bits}/HMAC_SHA2_256_128\n'
        f'charon: 11[IKE] traffic selectors 10.{a}.0.0/24 === 172.{b}.5.0/24 inacceptable (peer local === peer remote: 172.{b}.5.0/24 === 10.{a}.0.0/24), sending TS_UNACCEPTABLE\n')
    ctx.write('requirements.txt', 'IPsec(strongSwan)のipsec.confのconn branchが、対向のログ(peer-log.txt)と合わず確立できない。IKEとESPの提案(ike=, esp=)、およびトンネルのサブネット(leftsubnet / rightsubnet)を対向に合わせる。left/right/keyexchange/authby/autoは変更しない。\n')


def c13(ctx):
    need_ro(ctx)
    d = ctx.data
    secs = kv_conf(ctx.need_file('ipsec.conf'))
    c = [s[1] for s in secs if s[0] == 'conn branch']
    ctx.require(len(c) == 1, 'conn branchを残します。')
    c = {k: v[0].rstrip('!') for k, v in c[0].items()}
    ctx.require(c.get('ike') == d['ike'] and c.get('esp') == d['esp'], 'ike=/esp=を対向が受け取った提案に合わせます。')
    ctx.require(c.get('leftsubnet') == d['ls'] and c.get('rightsubnet') == d['rs'], 'サブネットは対向のpeer remote/localの鏡写しに合わせます。')
    ctx.require(c.get('left') == '203.0.113.10' and c.get('right') == '198.51.100.20' and c.get('keyexchange') == 'ikev2' and c.get('authby') == 'secret' and c.get('auto') == 'start', 'その他の項目は変更しません。')


SOL13 = r"""sed -i -e 's/^\( *\)ike=.*/\1ike=<<ike>>/' -e 's/^\( *\)esp=.*/\1esp=<<esp>>/' -e 's|^\( *\)rightsubnet=.*|\1rightsubnet=<<rs>>|' ipsec.conf"""
mission(13, 'strongSwanのipsec.confを対向の提案に合わせる',
        'IPsecトンネル(strongSwan)が確立しません。対向のログのNO_PROPOSAL_CHOSENとTS_UNACCEPTABLEは、暗号スイートの提案と保護するサブネットが一致しないことを示します。',
        ['ike/espを揃える', 'サブネットを揃える'], s13, c13, SOL13,
        ["sed -i 's/^\\( *\\)ike=.*/\\1ike=<<ike>>/' ipsec.conf",
         "sed -i -e 's|^\\( *\\)rightsubnet=.*|\\1rightsubnet=<<ls>>|' -e 's/^\\( *\\)ike=.*/\\1ike=<<ike>>/' -e 's/^\\( *\\)esp=.*/\\1esp=<<esp>>/' ipsec.conf"],
        'IKEv2は(1)IKE SAの暗号提案(ike=)、(2)Child SAの暗号提案(esp=)、(3)トラフィックセレクタ(subnet)の3段階で合意します。NO_PROPOSAL_CHOSENは提案、TS_UNACCEPTABLEはサブネットの不一致です。左右は自分側/相手側で、相手のpeer local/remoteは逆向きになります。',
        '段階ごとに失敗原因が違います。', 'ログの received と configured を比べます。')


# ---------------------------------------------------------------- 14 nginx TLS
def s14(ctx):
    t = secrets.token_hex(2)
    blocks = ''
    keep = []
    for n in ('www', 'api'):
        nm = f'{n}-{t}.dojo.test'
        pre = [f'    listen 443 ssl;', f'    server_name {nm};', f'    ssl_certificate /etc/ssl/{n}.crt;', f'    ssl_certificate_key /etc/ssl/{n}.key;']
        keep += pre[:3]
        blocks += 'server {\n' + '\n'.join(pre) + '\n    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;\n    ssl_ciphers RC4:3DES:HIGH:!aNULL;\n    location / { return 200; }\n}\n\n'
    ctx.data['keep'] = keep
    ctx.write('nginx.conf', blocks)
    put(ctx, 'scan.txt', 'TLS 1.0   offered (deprecated)\nTLS 1.1   offered (deprecated)\nTLS 1.2   offered\nTLS 1.3   not offered\nRC4       offered (VULNERABLE)\n3DES      offered (VULNERABLE, Sweet32)\nHSTS      not offered\n')
    ctx.write('requirements.txt', 'nginx.confの全serverブロックのTLS設定を、scan.txtの指摘に従って直す。ssl_protocolsはTLSv1.2 TLSv1.3だけ、ssl_cipherにはRC4・3DES・DES・MD5・NULLを含めずECDHEのAEAD(GCM/CHACHA20)スイートのみ。各ブロックにStrict-Transport-Securityヘッダ(max-age=31536000)も追加。listen・server_name・ssl_certificate行は変更しない。\n')


def c14(ctx):
    need_ro(ctx)
    text = ctx.need_file('nginx.conf')
    ls = [x.strip() for x in text.splitlines()]
    keep = [x.strip() for x in ctx.data['keep']]
    ctx.require(all(ls.count(k) == keep.count(k) for k in keep) and len([x for x in ls if x.startswith('server {')]) == 2, 'listen / server_name / ssl_certificate と2つのserverブロックを維持します。')
    prots = [x for x in ls if x.startswith('ssl_protocols')]
    ctx.require(len(prots) == 2 and all(x.rstrip(';').split()[1:] == ['TLSv1.2', 'TLSv1.3'] for x in prots), '全ブロックでssl_protocols TLSv1.2 TLSv1.3;にします。')
    ciph = [x for x in ls if x.startswith('ssl_ciphers')]
    ctx.require(len(ciph) == 2, '各ブロックにssl_ciphersを置きます。')
    for x in ciph:
        body = x.rstrip(';').split(None, 1)[1]
        ctx.require(not re.search(r'RC4|3DES|DES|MD5|NULL|EXPORT', body) and 'ECDHE' in body and re.search(r'GCM|CHACHA20', body), 'ssl_ciphersは弱い暗号を含めず、ECDHE+AEADにします。')
    hs = [x for x in ls if x.lower().startswith('add_header strict-transport-security')]
    ctx.require(len(hs) == 2 and all(re.search(r'max-age=(\d+)', x) and int(re.search(r'max-age=(\d+)', x).group(1)) >= 31536000 for x in hs), '各ブロックにHSTS（max-age>=31536000）を追加します。')


SOL14 = r"""sed -i -e 's/^\( *\)ssl_protocols .*/\1ssl_protocols TLSv1.2 TLSv1.3;/' -e 's/^\( *\)ssl_ciphers .*/\1ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305;/' -e 's/^\( *\)ssl_certificate_key .*/&\n\1add_header Strict-Transport-Security "max-age=31536000" always;/' nginx.conf"""
mission(14, 'nginxのssl_protocolsと暗号スイートを現代化する',
        'TLSスキャンの採取記録で古いTLSプロトコルと弱い暗号スイートが指摘されました。nginxのssl_protocolsとssl_ciphers、HSTSを全serverブロックで直します。',
        ['ssl_protocolsを整理', 'ssl_ciphersを強いものだけに', 'HSTSを追加'], s14, c14, SOL14,
        ["sed -i 's/^\\( *\\)ssl_protocols .*/\\1ssl_protocols TLSv1.2 TLSv1.3;/' nginx.conf",
         "sed -i -e '0,/ssl_protocols .*/s//ssl_protocols TLSv1.2 TLSv1.3;/' -e 's/ssl_ciphers .*/ssl_ciphers HIGH:!aNULL;/' nginx.conf"],
        'ssl_protocolsはTLS 1.0/1.1を外し1.2と1.3だけにします。TLS 1.3では暗号スイートが固定でssl_ciphersはTLS 1.2用です。RC4・3DESは既知の攻撃があり、ECDHEで前方秘匿性、GCM/ChaCha20でAEADを得ます。HSTSはHTTPS固定をブラウザへ伝えるヘッダです。変更後はnginx -tで検証してからreloadします。',
        'serverブロックが複数あり、全て直す必要があります。', 'sedは全行に効きます。-eを複数並べます。')


# ---------------------------------------------------------------- 15 key rotation
def s15(ctx):
    t = secrets.token_hex(2)
    oldc = 'deploy-old-' + t
    ctx.data.update(tag=t, oldc=oldc)
    old, col, ci = pubkey(oldc), pubkey('alice@laptop'), pubkey('ci-' + t)
    ctx.data.update(col=col, ci=ci)
    ctx.write('id_old', '-----BEGIN OPENSSH PRIVATE KEY-----\n(fake)\n-----END OPENSSH PRIVATE KEY-----\n', mode=0o600)
    ctx.write('id_old.pub', old + '\n')
    ctx.write('authorized_keys', f'{col}\n{old}\n{ci}\n')
    ctx.write('requirements.txt', f'デプロイ用のSSH鍵をローテーションする。鍵ファイルのコメント deploy-old-{t} から旧鍵を特定し、新しいed25519鍵 id_new（パスフレーズなし、コメント deploy-{t}）を作る。authorized_keysには他の2行を残して新公開鍵を加え、旧公開鍵だけを除く。旧秘密鍵と公開鍵を retired/ へ移す。\n')


def c15(ctx):
    d = ctx.data
    ak = [x for x in ctx.need_file('authorized_keys').splitlines() if x.strip()]
    pub = ctx.need_file('id_new.pub').strip()
    ctx.require(ctx.need_file('id_new').startswith('-----BEGIN OPENSSH PRIVATE KEY-----'), 'id_newは秘密鍵です。')
    m = pub.split()
    ctx.require(len(m) == 3 and m[0] == 'ssh-ed25519' and m[2] == 'deploy-' + d['tag'], 'ed25519でコメントdeploy-タグを付けます。')
    try:
        blob = base64.b64decode(m[1])
    except ValueError:
        ctx.fail('公開鍵が壊れています。')
    ctx.require(blob.startswith(struct.pack('>I', 11) + b'ssh-ed25519') and len(blob) == 51, 'ed25519の公開鍵ではありません。')
    ctx.require(ctx.mode('id_new') == 0o600, '秘密鍵はモード600です。')
    ctx.require(sorted(ak) == sorted([d['col'], d['ci'], pub]), 'authorized_keysは「他人の2行＋新公開鍵」だけにします（旧鍵を除き、他人の鍵は残す）。')
    ctx.require(not ctx.exists('id_old') and not ctx.exists('id_old.pub') and ctx.exists('retired/id_old') and ctx.exists('retired/id_old.pub'), '旧鍵はretired/へ移します。')


SOL15 = """ssh-keygen -q -t ed25519 -N '' -C deploy-<<tag>> -f id_new
cat id_new.pub >> authorized_keys
grep -v ' <<oldc>>$' authorized_keys > ak.tmp && mv ak.tmp authorized_keys
mkdir retired && mv id_old id_old.pub retired/"""
mission(15, 'SSH鍵ローテーションを重複運用で安全に行う',
        '長く使った鍵の入れ替え(鍵ローテーション)です。先に旧鍵を消すと自分も締め出されるため、新鍵を追加して接続を確認してから旧鍵を失効させます。',
        ['ed25519の新鍵を作る', 'authorized_keysを更新', '旧鍵を退避'], s15, c15, SOL15,
        ["ssh-keygen -q -t ed25519 -N '' -C deploy-<<tag>> -f id_new\ncat id_new.pub > authorized_keys\nmkdir retired && mv id_old id_old.pub retired/",
         "ssh-keygen -q -t ed25519 -N '' -C deploy-<<tag>> -f id_new\ncat id_new.pub >> authorized_keys\nmkdir retired && mv id_old id_old.pub retired/"],
        'ローテーションは(1)生成(2)新旧併存で配布(3)新鍵で接続確認(4)旧鍵の削除(5)旧秘密鍵の無効化と記録、の順です。authorized_keysに > で書くと他の人の鍵まで消えます。コメントで鍵を識別できるようにしておくと棚卸しやgrep -vによる除去ができます。',
        'authorized_keysには他の利用者の鍵もあります。', '追記は >>、旧鍵の除去はgrep -vで行います。')


# ---------------------------------------------------------------- 16 CRL / OCSP
def s16(ctx):
    ser = [secrets.token_hex(4).upper() for _ in range(6)]
    crl_rev = sorted(SR.sample(ser, 2))
    ocsp_only = secrets.choice([s for s in ser if s not in crl_rev])
    stale = SR.random() < 0.5
    now = datetime(2026, 11, 21, 9)
    fmt = lambda t: t.strftime('%b %d %H:%M:%S %Y GMT')
    lu = now - timedelta(days=9 if stale else 1)
    nu = now - timedelta(days=2 if stale else 0, hours=0) if stale else now + timedelta(days=6)
    crl = f'$ openssl crl -in ca.crl -noout -text\nCertificate Revocation List (CRL):\n  Issuer: CN = Dojo Test CA\n  Last Update: {fmt(lu)}\n  Next Update: {fmt(nu)}\nRevoked Certificates:\n'
    for s in crl_rev:
        crl += f'    Serial Number: {s}\n        Revocation Date: {fmt(lu - timedelta(days=5))}\n'
    ocsp = ''
    for s in ser[:5]:
        st = 'revoked' if s in crl_rev or s == ocsp_only else 'good'
        ocsp += f'$ openssl ocsp -issuer ca.crt -serial 0x{s} -url http://ocsp.dojo.test -resp_text\nOCSP Response Status: successful (0x0)\nCert Status: {st}\n\n'
    ctx.data.update(revoked=json.dumps(sorted(set(crl_rev) | {ocsp_only}), separators=(',', ':')), stale=json.dumps(stale))
    ctx.data['ser'] = ser
    put(ctx, 'crl.txt', crl)
    put(ctx, 'ocsp.txt', ocsp)
    ctx.write('requirements.txt', f'証明書失効の状況を調べる。確認時刻は{fmt(now)}。crl.txt(CRL)とocsp.txt(OCSPの応答)を突き合わせ、失効しているシリアルの和集合（昇順）と、CRLがNext Updateを過ぎていて古いかどうかをrevocation.jsonへ（revoked, crl_stale: true/false）。'
              'ocsp.txtに載っていないシリアル（直近で発行された証明書）を確認するopenssl ocspコマンド（-issuer ca.crt -cert server.crt -url http://ocsp.dojo.test、応答の文面を出す-resp_text付き）を1行でcmd.txtへ。実行はしません。\n')


def c16(ctx):
    need_ro(ctx)
    d = ctx.data
    j = rj(ctx, 'revocation.json')
    ctx.require(j.get('revoked') == json.loads(d['revoked']), '失効はCRLとOCSPのどちらかにあれば失効です。CRLが古いとOCSPにだけ現れます。')
    ctx.require(j.get('crl_stale') is json.loads(d['stale']), 'CRLのNext Updateと確認時刻を比べます。')
    t = toks(ctx, one_line(ctx, 'cmd.txt'))
    ctx.require(t[:2] == ['openssl', 'ocsp'], 'openssl ocspで問い合わせます。')
    ctx.require(all(o in t for o in ('-issuer', '-cert', '-url', '-resp_text')) and t[t.index('-issuer') + 1] == 'ca.crt' and t[t.index('-cert') + 1] == 'server.crt' and t[t.index('-url') + 1] == 'http://ocsp.dojo.test', '-issuer ca.crt -cert server.crt -url ... -resp_text を指定します。')


SOL16 = """echo '{"revoked":<<revoked>>,"crl_stale":<<stale>>}' > revocation.json
echo "openssl ocsp -issuer ca.crt -cert server.crt -url http://ocsp.dojo.test -resp_text" > cmd.txt"""
mission(16, 'CRLとOCSPで証明書の失効を確かめる',
        '漏えいした鍵の証明書は失効(revoke)させ、クライアントはCRLまたはOCSPで確認します。CRLは更新間隔があるため古いことがあり、OCSPは1枚ごとの最新状態を返します。両方を突き合わせて失効一覧を作ります。',
        ['失効の和集合とCRLの古さをrevocation.jsonへ', 'openssl ocspの問い合わせをcmd.txtへ'], s16, c16, SOL16,
        ['echo \'{"revoked":[],"crl_stale":false}\' > revocation.json\necho "openssl ocsp -cert server.crt" > cmd.txt',
         'echo \'{"revoked":<<revoked>>,"crl_stale":<<stale>>}\' > revocation.json\necho "openssl crl -in ca.crl -noout -text" > cmd.txt'],
        'CRLは失効シリアルの一覧に Last Update / Next Update が付き、Next Updateを過ぎたものは信頼できません。OCSPは証明書ごとにgood/revoked/unknownを返し、サーバー側でOCSP staplingを有効にするとクライアントの問い合わせ負荷を下げられます。失効状況は片方だけで判断せず、確認方法ごとの更新間隔を踏まえて判断します。',
        'CRLが古いとOCSPにだけ失効が現れます。', 'jsonの値は2つのファイルから集めます。')
