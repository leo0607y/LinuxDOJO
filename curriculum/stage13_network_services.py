"""ネットワーク・TLS・SQLite・構成管理。workspace課題と実VMの範囲を区別する。"""
import hashlib
import json
import secrets
import shutil
import sqlite3
import subprocess
from pathlib import Path

from engine.runner import register

S = 13
NOTE = ("作業対象はこの課題のフォルダだけです。OSのネットワークやDNSは変更しません。"
        "経路・DNS・プロキシは設定例と採取済み記録の診断、TLS証明書とSQLiteは本物のツールによるローカル操作です。"
        "複数台の通信と実際のNginxはVM実習webstack/networkで検証します。")


def write_json(ctx, name, data):
    ctx.write(name, json.dumps(data, indent=2) + '\n')


def read_json(ctx, name):
    try:
        value = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONとして保存します。')
    ctx.require(isinstance(value, dict), name + ' の最上位はオブジェクトです。')
    return value


def unchanged(ctx, name):
    ctx.require(hashlib.sha256(ctx.need_file(name).encode()).hexdigest() == ctx.data['originals'][name], name + ' は承認された原本です。変更しないでください。')


def approve(ctx, data):
    write_json(ctx, 'approved.json', data)
    ctx.data['approved'] = data
    ctx.data['originals'] = {'approved.json': hashlib.sha256(ctx.need_file('approved.json').encode()).hexdigest()}


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'13-{n}', stage=S, title=title, story=story+'\n'+NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='記録からの診断・設定の検査・実行中サービスの検証は別です。実VM実習では変更後と再起動後にも確認しましょう。')


def s1(ctx):
    net = 20 + secrets.randbelow(180)
    data = dict(address=f'192.0.{net}.20/24', gateway=f'192.0.{net}.1', resolver=f'192.0.{net}.53', interface='ens3')
    approve(ctx, data)
    write_json(ctx, 'netplan.json', {'network': {'version': 2, 'ethernets': {'ens3': {
        'addresses': [data['address']], 'routes': [{'to': 'default', 'via': '198.51.100.1'}],
        'nameservers': {'addresses': [data['resolver']]}}}}})
    ctx.write('observations.txt', f"$ ip route\n192.0.{net}.0/24 dev ens3 scope link\n$ ip route get 203.0.113.10\nRTNETLINK answers: Network is unreachable\n")
    ctx.write('requirements.txt', 'netplan.jsonはYAMLのJSON形式の設定例です。approved.jsonに従いdefault経路だけを修正し、他の値を維持。diagnosis.jsonにcause=default-gateway-outside-subnetとgatewayを記録。実OSには適用しません。\n')


def c1(ctx):
    unchanged(ctx, 'approved.json'); a=ctx.data['approved']
    n=read_json(ctx, 'netplan.json')
    expected={'network': {'version': 2, 'ethernets': {a['interface']: {'addresses': [a['address']], 'routes': [{'to':'default','via':a['gateway']}], 'nameservers':{'addresses':[a['resolver']]}}}}}
    ctx.require(n==expected, 'アドレス・名前解決先を保ち、承認済みの同一サブネットのゲートウェイを指定します。')
    ctx.require(read_json(ctx,'diagnosis.json')==dict(cause='default-gateway-outside-subnet',gateway=a['gateway']), '原因と修正した出口を記録します。')


SOL1="""python3 - <<'PYCODE'
import json
p='netplan.json'; n=json.load(open(p)); a=json.load(open('approved.json'))
n['network']['ethernets'][a['interface']]['routes']=[dict(to='default',via=a['gateway'])]
json.dump(n,open(p,'w'),indent=2)
json.dump(dict(cause='default-gateway-outside-subnet',gateway=a['gateway']),open('diagnosis.json','w'))
PYCODE"""
mission(1,'接続を維持する経路設定の修正','出口のアドレスだけが別ネットワークを指す設定案が届きました。',
 ['採取済みの経路と承認されたアドレスを比較する','経路の設定控えの経路を直しdiagnosis.jsonへ理由を残す'],s1,c1,SOL1,
 ["echo '{}' > diagnosis.json", "cp approved.json netplan.json"],
 '経路の設定はアドレス・サブネット・インターフェースとセットで検証します。設定例の一致は通信成功の証明ではないため、VMでは相手からの通信も確認します。',
 '宛先の前に、自分が渡せる出口かを考えます。','JSON形式の設定例を読み、routesだけを編集します。')


def s2(ctx):
    label='app-'+secrets.token_hex(3)+'.dojo.test'
    approve(ctx, dict(name=label,address='192.0.2.20',ttl=300,serial=2026112102))
    write_json(ctx,'zone.json',dict(name=label,address='192.0.2.99',ttl=300,serial=2026112101))
    ctx.write('dns-observation.txt',f';; status: NOERROR\n{label}. 300 IN A 192.0.2.99\n')
    ctx.write('requirements.txt','zone.jsonはDNSレコードの設定案。名前とTTLを維持し承認済みAと更新番号を設定。diagnosis.jsonにcause=stale-a-record、name、answerを記録。DNSサーバーを実行する課題ではありません。\n')


def c2(ctx):
    unchanged(ctx,'approved.json'); a=ctx.data['approved']
    ctx.require(read_json(ctx,'zone.json')==a,'名前・TTL・A・更新番号をすべて確認します。')
    ctx.require(read_json(ctx,'diagnosis.json')==dict(cause='stale-a-record',name=a['name'],answer=a['address']),'NXDOMAINと古い正常応答を区別し、修正した名前と回答を記録します。')


SOL2="""python3 - <<'PYCODE'
import json
a=json.load(open('approved.json')); json.dump(a,open('zone.json','w'),indent=2)
json.dump(dict(cause='stale-a-record',name=a['name'],answer=a['address']),open('diagnosis.json','w'))
PYCODE"""
mission(2,'名前が引けても宛先が古い','DNSは正常応答ですが、移設前のアドレスが返っています。',
 ['DNS観測記録と承認資料を照合する','zone.jsonとdiagnosis.jsonを作る'],s2,c2,SOL2,
 ["echo '{}' > zone.json", "echo '{\"cause\":\"nxdomain\"}' > diagnosis.json"],
 'NOERRORはサービスの正しい配置まで保証しません。キャッシュのTTL、権威側の更新、問い合わせ先を分けて確認します。実DNSの再読込と複数台からの照合はVMで学びます。',
 '名前が存在しない場合と、違う番号を返す場合を分けます。','採取済み回答のAレコードと承認されたIPを比較します。')


def openssl(ctx,*args):
    tool=shutil.which('openssl')
    ctx.require(bool(tool),'この課題にはopensslが必要です。準備後にresetします。')
    result=subprocess.run([tool,*args],cwd=ctx.work,capture_output=True,text=True,timeout=20)
    ctx.require(result.returncode==0,'証明書をopensslで検査できません。ファイルと引数を確認します。')
    return result.stdout


def s3(ctx):
    host='web-'+secrets.token_hex(3)+'.dojo.test'
    ctx.data['hostname'] = host
    approve(ctx,dict(hostname=host))
    # 課題専用の鍵と証明書だけを作成する。ホストの信頼ストアは変更しない。
    openssl(ctx,'req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=old.dojo.test',
            '-addext','subjectAltName=DNS:old.dojo.test','-keyout','server.key','-out','server.crt')
    ctx.p('server.key').chmod(0o600)
    ctx.data['before_hash']=hashlib.sha256(ctx.p('server.crt').read_bytes()).hexdigest()
    ctx.write('requirements.txt',f'承認済みの名前{host}をSANへ含む訓練用自己署名証明書を発行。元の証明書はbefore.crtへ退避。秘密鍵600。openssl x509 -noout -ext subjectAltNameの結果をsan.txtへ保存。\n')


def c3(ctx):
    unchanged(ctx,'approved.json')
    ctx.require(hashlib.sha256(ctx.need_file('before.crt').encode()).hexdigest()==ctx.data['before_hash'],'元の証明書をbefore.crtに保全してください。')
    host=ctx.data['approved']['hostname']
    san=openssl(ctx,'x509','-in','server.crt','-noout','-ext','subjectAltName')
    names=[n.strip() for n in san.splitlines()[-1].split(',')]
    ctx.require('DNS:'+host in names,'CNだけでなくSANに承認済みの名前が必要です。')
    ctx.require(host in ctx.need_file('san.txt'),'SANの確認結果を保存してください。')
    openssl(ctx,'x509','-in','server.crt','-noout','-checkend','0')
    cert=openssl(ctx,'x509','-in','server.crt','-noout','-pubkey')
    key=openssl(ctx,'pkey','-in','server.key','-pubout')
    ctx.require(cert==key,'証明書と秘密鍵が対応していません。')
    ctx.require(ctx.mode('server.key')==0o600,'秘密鍵は600にします。')


SOL3="""cp server.crt before.crt
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj '/CN=<<hostname>>' -addext 'subjectAltName=DNS:<<hostname>>' -keyout server.key -out server.crt
chmod 600 server.key
openssl x509 -in server.crt -noout -ext subjectAltName > san.txt"""
mission(3,'TLS証明書の名前と秘密鍵を照合する','接続名と証明書のSANが一致していません。信頼検証を無効にせず、訓練用証明書を作り直します。',
 ['元の証明書をbefore.crtに保全','SANに指定名を持つ証明書と対応鍵を作成','鍵600とSANの確認結果san.txtを提出'],s3,c3,SOL3,
 ["cp server.crt before.crt\nopenssl x509 -in server.crt -noout -ext subjectAltName > san.txt",SOL3+'\nchmod 644 server.key'],
 'SANの名前、有効期限、鍵との対応、信頼する発行者は別々の検証点です。ここでは訓練用自己署名証明書を生成し、VMではcurl --cacertで名前と信頼も検証します。-kで検証を省く方法は使いません。',
 '名前の不一致を、証明書の検査を無効にして隠してはいけません。','openssl reqでSAN付きの訓練用証明書、openssl x509とpkeyで内容と公開鍵を確認します。')


def s4(ctx):
    port=18000+secrets.randbelow(1000)
    approve(ctx,dict(listen=8088,upstream=f'http://127.0.0.1:{port}',host_header='$host',health_path='/health'))
    write_json(ctx,'proxy.json',dict(listen=8088,upstream='http://127.0.0.1:1',host_header='$host',health_path='/health'))
    ctx.write('error.log','connect() failed (111: Connection refused) while connecting to upstream, upstream: "http://127.0.0.1:1/health"\n')
    ctx.write('backend-listen.txt',f'LISTEN 0 128 127.0.0.1:{port} 0.0.0.0:*\n')
    ctx.write('requirements.txt','proxy.jsonの設定案の上流だけを修正。diagnosis.jsonにcause=wrong-upstream-portとupstreamを記録。Nginxを実際に起動する課題ではありません。VM webstackで実機検証します。\n')


def c4(ctx):
    unchanged(ctx,'approved.json'); a=ctx.data['approved']
    ctx.require(read_json(ctx,'proxy.json')==a,'公開口・上流・Host・正常性パスを確認します。')
    ctx.require(read_json(ctx,'diagnosis.json')==dict(cause='wrong-upstream-port',upstream=a['upstream']),'502の原因をログと待ち受けに照らして記録します。')


SOL4="""python3 - <<'PYCODE'
import json
a=json.load(open('approved.json')); p=json.load(open('proxy.json')); p['upstream']=a['upstream']; json.dump(p,open('proxy.json','w'))
json.dump(dict(cause='wrong-upstream-port',upstream=a['upstream']),open('diagnosis.json','w'))
PYCODE"""
mission(4,'502の上流と待ち受けを照合する','公開口へは届きますが、リバースプロキシが別のポートへ接続しています。',
 ['エラーログとバックエンドの待ち受け記録を比較','プロキシの設定控えを修正しdiagnosis.jsonに根拠を記録'],s4,c4,SOL4,
 ["echo '{}' > proxy.json", "echo '{\"cause\":\"dns\"}' > diagnosis.json"],
 'フロントへの接続、上流への接続、アプリの処理は別の段階です。502という数字だけで再起動せず、上流のURLと実際の待ち受けを照合します。',
 'ブラウザーから公開口まで届くことと、公開口からアプリへ届くことを分けます。','接続拒否の宛先とLISTENの番号を比較します。')


def s5(ctx):
    tag='record-'+secrets.token_hex(4)
    with sqlite3.connect(ctx.p('app.db')) as db:
        db.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        db.executemany('INSERT INTO records(name) VALUES (?)',[(tag,),('keep-this-record',)])
        db.execute('PRAGMA user_version=1')
    ctx.data['record']=tag
    ctx.write('requirements.txt','app.dbの全データを保持してstatus TEXT NOT NULL DEFAULT active列を追加しuser_version=2へ。移行前backup.dbをSQLiteのbackup APIで作成。integrity.txtはPRAGMA integrity_checkの結果。\n')


def database(ctx,name):
    path=ctx.p(name)
    ctx.require(path.is_file() and not path.is_symlink(),name+'の通常ファイルが必要です。')
    return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)


def c5(ctx):
    expected=[(1,ctx.data['record']),(2,'keep-this-record')]
    try:
        with database(ctx,'backup.db') as db:
            ctx.require(db.execute('PRAGMA user_version').fetchone()[0]==1,'バックアップは移行前の版が必要です。')
            ctx.require(db.execute('SELECT id,name FROM records ORDER BY id').fetchall()==expected,'移行前のデータを残してください。')
            ctx.require([r[1] for r in db.execute('PRAGMA table_info(records)')]==['id','name'],'バックアップを移行後のDBで上書きしないでください。')
        with database(ctx,'app.db') as db:
            ctx.require(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'DB整合性を確認します。')
            ctx.require(db.execute('PRAGMA user_version').fetchone()[0]==2,'移行後の版は2です。')
            ctx.require(db.execute('SELECT id,name FROM records ORDER BY id').fetchall()==expected,'既存のデータが変わっています。')
            ctx.require(db.execute('SELECT status FROM records ORDER BY id').fetchall()==[('active',),('active',)],'既存データに既定値を適用します。')
            column=next((r for r in db.execute('PRAGMA table_info(records)') if r[1]=='status'),None)
            ctx.require(column is not None and column[2].upper()=='TEXT' and column[3]==1,'statusはTEXT NOT NULLとして追加します。')
            ctx.require(str(column[4]).strip("'\"()") == 'active', 'statusの既定値もactiveに設定します。')
    except sqlite3.Error as error:
        ctx.fail('SQLiteの構造と退避データを確認します: '+str(error))
    ctx.require(ctx.need_file('integrity.txt').strip()=='ok','整合性の検査結果を保存します。')


SOL5="""python3 - <<'PYCODE'
import sqlite3
with sqlite3.connect('app.db') as db, sqlite3.connect('backup.db') as backup:
 db.backup(backup)
 db.execute(\"ALTER TABLE records ADD COLUMN status TEXT NOT NULL DEFAULT 'active'\")
 db.execute('PRAGMA user_version=2')
 open('integrity.txt','w').write(db.execute('PRAGMA integrity_check').fetchone()[0]+'\\n')
PYCODE"""
mission(5,'SQLiteを退避してから移行する','実データを残したままDB構造を更新します。空のDBを作り直す方法では達成できません。',
 ['backup APIで移行前のbackup.dbを作る','既存行を保ちstatus列と版を追加','整合性を確認してintegrity.txtへ保存'],s5,c5,SOL5,
 ["touch backup.db integrity.txt",SOL5+'\ncp app.db backup.db'],
 'SQLiteの稼働中DBでは単純なファイルコピーだけでなくbackup APIなど整合性を保つ方法を使います。退避の存在、内容、移行前の版、更新後の構造を分けて確認します。',
 '退避と更新の順序が逆だと、元へ戻すためのDBが残りません。','Python標準のsqlite3 Connection.backupとALTER TABLE、PRAGMAで作業します。')


def s6(ctx):
    client='192.0.2.'+str(30+secrets.randbelow(100))
    approve(ctx,dict(client=client,resolver='192.0.2.53',server='192.0.2.20',port=8088))
    ctx.write('packets.txt',f'''# 採取済みtcpdump風要約。パケットキャプチャを実行する課題ではありません。
10:00:00 IP {client}.40100 > 192.0.2.53.53: 1001+ A? app.dojo.test.
10:00:00 IP 192.0.2.53.53 > {client}.40100: 1001 1/0/0 A 192.0.2.20
10:00:01 IP {client}.40101 > 192.0.2.20.8088: Flags [S], seq 100
10:00:01 IP 192.0.2.20.8088 > {client}.40101: Flags [R.], ack 101
''')
    ctx.write('requirements.txt','diagnosis.jsonには client, dns（answered / no-answer）, tcp（refused / timeout / connected）, layer（listener-or-active-reject / route / service）, next_check（ss-listener-and-firewall / route-check / service-check）を記録する。packets.txtの要約から選び、RSTだけで原因を断定しない。\n')


def c6(ctx):
    unchanged(ctx,'approved.json')
    ctx.require(read_json(ctx,'diagnosis.json')==dict(client=ctx.data['approved']['client'],dns='answered',tcp='refused',layer='listener-or-active-reject',next_check='ss-listener-and-firewall'),'DNSの回答・SYNへのRST・次の確認を区別します。タイムアウトや接続成立とは異なります。')


SOL6="""python3 - <<'PYCODE'
import json
a=json.load(open('approved.json')); json.dump(dict(client=a['client'],dns='answered',tcp='refused',layer='listener-or-active-reject',next_check='ss-listener-and-firewall'),open('diagnosis.json','w'))
PYCODE"""
mission(6,'DNSとTCPの観測を分けて読む','採取済みパケット要約から、どこまで成功しどこから調査すべきかを判断します。',
 ['パケット要約の記録のDNS応答とTCPフラグを読む','要件書に従いdiagnosis.jsonへ観測と次の確認を保存'],s6,c6,SOL6,
 ["echo '{\"dns\":\"failed\"}' > diagnosis.json", "echo '{\"tcp\":\"connected\"}' > diagnosis.json"],
 'SYNに対するRSTは接続拒否を示す観測で、待ち受け不在や明示的な拒否などを追加確認します。採取済み要約の診断と、本物のパケット採取・解析は別です。VM networkで自分の通信を観察します。',
 '最初の問い合わせが成功しているか、次の接続に何が返ったかを順に読みます。','Aの回答とSYN/RSTを確認し、待ち受けとファイアウォールを次に調べます。')


def s7(ctx):
    nonce=secrets.token_hex(5)
    approve(ctx,dict(schema=1,port=8088,mode='production',revision=nonce))
    write_json(ctx,'inventory.json',dict(hosts=[dict(name='ubuntu-node',os='ubuntu',manager='apt',package='nginx'),dict(name='rhel-node',os='rhel',manager='dnf',package='nginx')]))
    ctx.write('requirements.txt','plan.jsonにinventory.jsonのhostsを保持し、各hostにdesired=approved.json、actions=[backup,validate,apply,verify,rollback-on-failure]を追加。secretを含めない。ホストへ接続・インストールはせず、構成管理の計画を作る課題。\n')


def c7(ctx):
    unchanged(ctx,'approved.json')
    plan=read_json(ctx,'plan.json')
    original=[dict(name='ubuntu-node',os='ubuntu',manager='apt',package='nginx'),dict(name='rhel-node',os='rhel',manager='dnf',package='nginx')]
    expected={'hosts':[dict(h,desired=ctx.data['approved'],actions=['backup','validate','apply','verify','rollback-on-failure']) for h in original]}
    ctx.require(plan==expected,'OSごとの管理方法、承認済み状態、退避から検証と戻しまでの計画を確認します。')


SOL7="""python3 - <<'PYCODE'
import json
a=json.load(open('approved.json')); i=json.load(open('inventory.json'))
for h in i['hosts']: h.update(desired=a,actions=['backup','validate','apply','verify','rollback-on-failure'])
json.dump(i,open('plan.json','w'),indent=2)
PYCODE"""
mission(7,'OS差分を含む再現可能な変更計画','UbuntuとRHEL系の設定更新を同じコマンドで流す案を、環境差と復旧まで考えた計画へ直します。',
 ['環境一覧と承認資料を読みplan.jsonを作る','OSごとのパッケージ管理と変更手順を保つ'],s7,c7,SOL7,
 ["cp approved.json plan.json", "echo '{\"hosts\":[]}' > plan.json"],
 '構成管理では目的の状態と実行方法を分け、環境差と冪等性を検証します。この課題は計画の作成でありAnsibleの実行ではありません。VM実習ではsetupの繰り返しと再起動後の状態を確認します。',
 '対象のOSと、作業が失敗したときに戻す条件を計画へ含めます。','inventoryの各hostへdesiredと順序付きactionsを追加します。')


def s8(ctx):
    name='db-'+secrets.token_hex(3)
    approve(ctx,dict(asset=name,rpo_minutes=15,rto_minutes=60,restore_target='replacement-vm'))
    ctx.write('requirements.txt','recovery.jsonにasset,rpo_minutes,rto_minutes,restore_targetを承認どおり記録。steps=[provision,verify-backup-integrity,restore-data,restore-permissions,verify-service,verify-client,record-loss-and-time]。単にbackup-successでは達成しません。\n')


def c8(ctx):
    unchanged(ctx,'approved.json')
    expected=dict(ctx.data['approved'],steps=['provision','verify-backup-integrity','restore-data','restore-permissions','verify-service','verify-client','record-loss-and-time'])
    ctx.require(read_json(ctx,'recovery.json')==expected,'新しい環境への復元、整合性、権限、サービスと別端末からの確認、復旧時間と欠損の記録まで必要です。')


SOL8="""python3 - <<'PYCODE'
import json
a=json.load(open('approved.json')); a['steps']=['provision','verify-backup-integrity','restore-data','restore-permissions','verify-service','verify-client','record-loss-and-time']
json.dump(a,open('recovery.json','w'),indent=2)
PYCODE"""
mission(8,'バックアップから別環境へ戻す計画','バックアップ成功の通知だけでは、サービスを復旧できるか分かりません。復元を試す計画を作ります。',
 ['承認資料の許容欠損時間と復旧時間を理解する','別VMへの復元と利用側の確認までrecovery.jsonへ記録'],s8,c8,SOL8,
 ["cp approved.json recovery.json", "echo '{\"steps\":[\"backup-success\"]}' > recovery.json"],
 'RPOは許容するデータ欠損時間、RTOは目標復旧時間です。計画の一致だけで実現を保証できないので、VMの複製や再構築で実際の時間と欠損を測る必要があります。',
 'バックアップの成功と、利用者が再び使える状態への復旧を区別します。','承認条件と、新環境・検査・権限・サービス・利用側・結果記録の順序を組み合わせます。')
