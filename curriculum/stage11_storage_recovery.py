"""Stage 11: captured storage/boot diagnosis and recovery planning.

Host operations are never simulated as real mounts. The accompanying VM modules
perform actual loop-backed ext4 and dedicated systemd service exercises.
"""
import hashlib
import json
import secrets
import uuid

from engine.runner import register

S = 11
NOTE = ("この課題は作業フォルダ内の採取済み診断データと設定控えを扱います。"
        "本物のディスク・マウント・LVM・起動設定は変更しません。実際の操作は別の使い捨てVM実習で行います。")


def dump(ctx, path, data):
    ctx.write(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def base(ctx):
    ctx.write('SCOPE.txt', NOTE + '\n')


def obj(ctx, path):
    try:
        value = json.loads(ctx.need_file(path))
    except (ValueError, TypeError):
        ctx.fail(f'{path} を有効なJSONで保存してください。')
    ctx.require(isinstance(value, dict), f'{path} はJSONオブジェクトです。')
    return value


def unchanged(ctx, *paths):
    for path in paths:
        ctx.require(ctx.isfile(path) and not ctx.p(path).is_symlink(), f'{path} の原本を維持してください。')
        digest = hashlib.sha256(ctx.p(path).read_bytes()).hexdigest()
        ctx.require(digest == ctx.data['originals'][path], f'{path} の原本を変えずに調査してください。')


def preserve(ctx, *paths):
    ctx.data['originals'] = {p: hashlib.sha256(ctx.p(p).read_bytes()).hexdigest() for p in paths}


def answer(ctx, expected):
    ctx.require(obj(ctx, 'result.json') == expected, 'result.json の対象・根拠・対処が要件と一致しません。元の採取データと形式を確認しましょう。')


def add(n, title, story, objectives, setup, check, solution, wrong, explanation):
    register(id=f'11-{n}', stage=S, title=title, story=story+'\n'+NOTE,
             objectives=objectives, hints=['対象の層と証拠を分け、元のデータを変えずに確認します。',
             'まず ls で資料を一覧し、cat で要件書と採取データを読み、必要な項目をJSONへ記録します。設定を直す課題は控えだけを編集します。',
             'answer で入力例を確認できます。まず手元のデータから根拠を探しましょう。'],
             answer=solution, explanation=explanation,
             tip='調査しただけか、設定を変更したか、実機で再検証したかを区別して記録します。',
             setup=setup, check=check, solution=solution, wrong=wrong)


def s1(ctx):
    base(ctx); uuid='11111111-2222-4333-8444-'+secrets.token_hex(6)
    ctx.data['uuid']=uuid
    dump(ctx,'capture/lsblk.json', {'blockdevices':[{'name':'vda','type':'disk','size':21474836480,'children':[
        {'name':'vda1','type':'part','fstype':'ext4','uuid':'root-fixture','mountpoints':['/']}]},
        {'name':'vdb','type':'disk','size':4294967296,'children':[{'name':'vdb1','type':'part','fstype':'ext4','uuid':uuid,'mountpoints':['/srv/data']}]}]})
    ctx.write('requirements.txt','/srv/data の partition・parent_disk・filesystem・stable_source(UUID=...) を result.json に記録。デバイス名とUUIDを区別する。\n')
    preserve(ctx,'capture/lsblk.json')


def c1(ctx):
    unchanged(ctx,'capture/lsblk.json')
    answer(ctx,dict(partition='vdb1',parent_disk='vdb',filesystem='ext4',stable_source='UUID='+ctx.data['uuid']))


SOL1="""python3 - <<'PYCODE'
import json
b=json.load(open('capture/lsblk.json'))['blockdevices']
p,c=next((p,c) for p in b for c in p.get('children',[]) if '/srv/data' in c.get('mountpoints',[]))
json.dump(dict(partition=c['name'],parent_disk=p['name'],filesystem=c['fstype'],stable_source='UUID='+c['uuid']),open('result.json','w'))
PYCODE"""
add(1,'ディスク・パーティション・UUIDを読み分ける','lsblk --json相当の採取データから、アプリデータがどこにあるかを調査します。',
    ['lsblkの採取データを変更しない','要件書の形式で /srv/data の構成を記録'],s1,c1,SOL1,["echo '{}' > result.json"],
    'ディスク、パーティション、その中のファイルシステム、マウント先は別の層です。UUIDはデバイスの列挙順に依存しない識別に使います。lsblkの列を指定して採取する習慣も大切です。')


def s2(ctx):
    base(ctx); identifier=str(uuid.uuid4()); ctx.data['uuid']=identifier
    ctx.write('capture/blkid.txt',f'/dev/vdb1: UUID="{identifier}" TYPE="ext4"\n')
    root='UUID=root-fixture / ext4 defaults 0 1\n';ctx.data['root']=root
    ctx.write('fstab',root+'UUID=missing /srv/data ext4 defaults 0 2\n')
    ctx.write('requirements.txt','fstabのroot行を維持。/srv/data のUUIDを採取値へ直し、ext4・defaults,nodev,nosuid・dump=0・pass=2とする。行は2行のみ。mountは実行しない。\n')
    preserve(ctx,'capture/blkid.txt')


def c2(ctx):
    unchanged(ctx,'capture/blkid.txt')
    lines=[x.split() for x in ctx.need_file('fstab').splitlines() if x.strip() and not x.lstrip().startswith('#')]
    ctx.require(len(lines)==2 and lines[0]==ctx.data['root'].split(), 'root行を維持し、必要な2行だけにします。')
    ctx.require(lines[1][:3]==['UUID='+ctx.data['uuid'],'/srv/data','ext4'] and len(lines[1])==6,
                'データ領域のUUID・マウント先・種類・6項目を確認します。')
    ctx.require(set(lines[1][3].split(','))=={'defaults','nodev','nosuid'} and lines[1][4:]==['0','2'], '必要なマウントオプションとpass番号を確認します。')


SOL2=r"""python3 - <<'PYCODE'
import re
from pathlib import Path
u=re.search(r'UUID="([^"]+)"',Path('capture/blkid.txt').read_text()).group(1)
p=Path('fstab'); p.write_text(p.read_text().splitlines()[0]+'\nUUID='+u+' /srv/data ext4 defaults,nodev,nosuid 0 2\n')
PYCODE"""
add(2,'fstabの控えをUUIDで修正する','デバイス名に頼らず、採取したUUIDと設定の対応を確認します。',
    ['rootの行を維持','要件書に従いfstabのデータ行だけを修正'],s2,c2,SOL2,["sed -i 's/missing/guessed/' fstab",'printf "UUID=root-fixture / ext4 defaults 0 1\\n" > fstab'],
    'fstabはsource・mountpoint・type・options・dump・passの6項目です。非rootのext4は通常pass=2で確認対象にします。この課題で実マウントの成功は検証していません。実機では構文、マウント状態、再起動後の結果を確認します。参考: https://www.man7.org/linux/man-pages/man5/fstab.5.html')


def s3(ctx):
    base(ctx)
    ctx.write('capture/df-h.txt','Filesystem Size Used Avail Use% Mounted on\n/dev/vdb1 4.0G 1.0G 3.0G 25% /srv/data\n')
    ctx.write('capture/df-i.txt','Filesystem Inodes IUsed IFree IUse% Mounted on\n/dev/vdb1 10000 10000 0 100% /srv/data\n')
    ctx.write('capture/files.txt','/srv/data/tmp/jobs: 9800 empty temporary files\n/srv/data/reports: 190 required files\nremaining inodes: directories and filesystem metadata\n')
    ctx.write('requirements.txt','result.jsonには resource（容量不足 / inode不足）, mount, cause（少数の大きなファイル / 多数の小さなファイル）, cleanup（整理対象のパス）, preserve（保持するパス）を記録する。captureの記録から値を判断する。原本は変更しない。これは診断のみ。\n')
    preserve(ctx,'capture/df-h.txt','capture/df-i.txt','capture/files.txt')


def c3(ctx):
    unchanged(ctx,'capture/df-h.txt','capture/df-i.txt','capture/files.txt')
    answer(ctx,dict(resource='inodes',mount='/srv/data',cause='many-small-files',cleanup='/srv/data/tmp/jobs',preserve='/srv/data/reports'))


SOL3="""cat capture/df-h.txt capture/df-i.txt capture/files.txt
printf '%s\n' '{"resource":"inodes","mount":"/srv/data","cause":"many-small-files","cleanup":"/srv/data/tmp/jobs","preserve":"/srv/data/reports"}' > result.json"""
add(3,'空き容量があるのに作れない理由','空きバイトはあるのに新規ファイルが作れません。容量とinodeを比較してください。',
    ['df-hとdf-iを比較','削除候補と保持対象を分けた診断をresult.jsonへ記録'],s3,c3,SOL3,[SOL3.replace('"inodes"','"bytes"')],
    'ファイルシステムはデータ用領域だけでなくinodeにも上限があります。小さいファイルが大量にあるとinodeが先に枯渇します。実VM実習では専用ext4内で実際に新規作成が失敗する状態と復旧を確認します。')


def s4(ctx):
    base(ctx); vg='vg_'+secrets.token_hex(2); ctx.data['vg']=vg
    dump(ctx,'capture/lvm.json',dict(vg=vg,extent_mib=4,free_extents=64,lv='data',lv_extents=256,filesystem='ext4',requested_growth_mib=128,reserve_mib=64))
    ctx.write('requirements.txt','result.json: target=/dev/<vg>/data, add_extents, final_lv_mib, remaining_vg_mib, filesystem_action=resize2fs。要求128MiBを追加し、64MiB以上をVGに残す。操作は実行しない。\n')
    preserve(ctx,'capture/lvm.json')


def c4(ctx):
    unchanged(ctx,'capture/lvm.json')
    answer(ctx,dict(target='/dev/'+ctx.data['vg']+'/data',add_extents=32,final_lv_mib=1152,remaining_vg_mib=128,filesystem_action='resize2fs'))


SOL4="""python3 - <<'PYCODE'
import json
x=json.load(open('capture/lvm.json')); n=x['requested_growth_mib']//x['extent_mib']
json.dump(dict(target='/dev/'+x['vg']+'/'+x['lv'],add_extents=n,final_lv_mib=(x['lv_extents']+n)*x['extent_mib'],remaining_vg_mib=(x['free_extents']-n)*x['extent_mib'],filesystem_action='resize2fs'),open('result.json','w'))
PYCODE"""
add(4,'LVMとファイルシステムの拡張を分ける','VGの空きを全部使わず、必要量のLV拡張と、その上のext4拡張を計画します。',
    ['extent単位へ換算','要求量と予備容量を満たす計画をresult.jsonへ記録'],s4,c4,SOL4,[SOL4.replace("n=x['requested_growth_mib']//x['extent_mib']","n=x['free_extents']")],
    'PV・VG・LVと、その上にあるファイルシステムは別の層です。LVだけ大きくしてもファイルシステムの利用可能容量が増えるとは限りません。実機ではバックアップ、対応するFS拡張、拡張後の確認が必要です。参考: https://man7.org/linux/man-pages/man8/lvextend.8.html')


def s5(ctx):
    base(ctx); token=secrets.token_hex(5);ctx.data['config']='mode=production\ninstance='+token+'\n'
    ctx.write('capture/journal.txt','dojo-data.service: Started.\ndojo-app.service: ConditionPathExists=/srv/dojo/config.ini was not met.\ndojo-app.service: Skipped due to failed condition.\n')
    ctx.write('backup/config.ini',ctx.data['config'],mode=0o600)
    ctx.write('units/dojo-app.service','[Unit]\nRequires=dojo-data.service\nAfter=dojo-data.service\nConditionPathExists=/srv/dojo/config.ini\n[Service]\nExecStart=/usr/bin/true\n')
    ctx.write('requirements.txt','backup/config.iniをrecovered/config.iniへ復元し権限600。result.jsonには cause（missing-config / failed-dependency / permission）, unit（起動できないサービス）, dependency（必要なサービス）, next_check（設定確認後に専用サービスを再起動 / 権限を確認）を記録する。ログとユニット定義から判断し、依存関係を削除しない。\n')
    preserve(ctx,'capture/journal.txt','backup/config.ini','units/dojo-app.service')


def c5(ctx):
    unchanged(ctx,'capture/journal.txt','backup/config.ini','units/dojo-app.service')
    ctx.require(ctx.need_file('recovered/config.ini')==ctx.data['config'] and ctx.mode('recovered/config.ini')==0o600,'内容を保ち権限600で設定を復元してください。')
    answer(ctx,dict(cause='missing-config',unit='dojo-app.service',dependency='dojo-data.service',next_check='verify-config-then-restart-dedicated-service'))


SOL5="""mkdir -p recovered
cp backup/config.ini recovered/config.ini
chmod 600 recovered/config.ini
printf '%s\n' '{"cause":"missing-config","unit":"dojo-app.service","dependency":"dojo-data.service","next_check":"verify-config-then-restart-dedicated-service"}' > result.json"""
add(5,'起動失敗を依存関係から調べる','採取したjournalでは、データ依存サービスは起動していますがアプリが開始されません。',
    ['journalとunitを比較','必要な設定を復元し、次に実機で確認する操作を記録'],s5,c5,SOL5,["sed -i '/ConditionPathExists/d' units/dojo-app.service",SOL5+'\nchmod 644 recovered/config.ini'],
    '条件不成立や依存サービスの失敗はアプリ自身のクラッシュとは違います。条件を消して見かけ上成功にせず、必要な設定と内容を復元します。実VM実習は専用サービスだけを故障させ、OS全体の起動を壊しません。')


def s6(ctx):
    base(ctx);text='mode=stable\ninstance='+secrets.token_hex(4)+'\n';ctx.data['text']=text
    ctx.write('backup/config.ini',text,mode=0o640);ctx.write('live/config.ini','mode=broken\n',mode=0o644)
    meta=dict(mode='0640',owner='dojo-app',group='dojo-app',acl=['user::rw-','user:auditor:r--','group::---','mask::r--','other::---'])
    dump(ctx,'backup/metadata.json',meta);dump(ctx,'live/metadata.json',dict(mode='0644',owner='root',group='root',acl=[]))
    ctx.data['metadata']=meta
    ctx.write('backup/SHA256SUMS',hashlib.sha256(text.encode()).hexdigest()+'  backup/config.ini\n')
    ctx.write('requirements.txt','バックアップのハッシュを照合し、結果を verification.txt に保存。変更前のlive/config.iniをevidence/before.iniに保ち、内容とmode640を復元。live/metadata.jsonにメタデータ控えを復元する。拡張ACLがある場合modeのgroupビットはmaskに対応する。所有者/ACLは控えの比較であり、実際のchown/setfacl操作は別VM実習。\n')
    preserve(ctx,'backup/config.ini','backup/metadata.json','backup/SHA256SUMS')


def c6(ctx):
    unchanged(ctx,'backup/config.ini','backup/metadata.json','backup/SHA256SUMS')
    ctx.require(ctx.need_file('evidence/before.ini')=='mode=broken\n','変更前を失わずに退避します。')
    ctx.require(ctx.need_file('live/config.ini')==ctx.data['text'] and ctx.mode('live/config.ini')==0o640,'復元後の本文とmodeを確認してください。')
    ctx.require(obj(ctx,'live/metadata.json')==ctx.data['metadata'],'所有者・グループ・ACLの控えも復元します。')
    ctx.require(ctx.need_file('verification.txt').strip()=='backup/config.ini: OK','承認済みハッシュとの照合結果をverification.txtに保存します。')


SOL6="""LC_ALL=C sha256sum -c backup/SHA256SUMS > verification.txt
mkdir -p evidence
cp live/config.ini evidence/before.ini
cp backup/config.ini live/config.ini
chmod 640 live/config.ini
cp backup/metadata.json live/metadata.json"""
add(6,'内容だけでなく権限とメタデータも復元する','設定ファイルは本文が同じでも、所有者・モード・ACLが違うと動作や公開範囲が変わります。',
    ['承認済みハッシュと照合','変更前を退避','本文・modeと所有者/ACLの控えを復元'],s6,c6,SOL6,["cp backup/config.ini live/config.ini",SOL6+'\nchmod 644 live/config.ini'],
    'バックアップは「保存できた」ではなく、対象・期待値・権限を含めて戻せるかで確認します。この課題の所有者とACLはJSONの控えです。実際のACL有効性は専用VMでsetfacl/getfaclと別ユーザーでのアクセスを確かめます。')


def s7(ctx):
    base(ctx);pid=2000+int(secrets.token_hex(2),16)%1000;ctx.data['pid']=pid
    ctx.write('capture/df.txt','/dev/vdb1 4G 3.8G 0.2G 95% /srv/data\n')
    ctx.write('capture/du.txt','400M /srv/data\n')
    ctx.write('capture/lsof.txt',f'COMMAND PID USER FD TYPE DEVICE SIZE/OFF NLINK NODE NAME\ndojo-log {pid} dojo-app 3w REG 7,0 3650722201 0 120 /srv/data/app.log (deleted)\n')
    ctx.write('requirements.txt','result.jsonには cause（削除済みだがプロセスが開いたまま / 通常の大容量ファイル）, pid, path, action（担当者とログ再オープンを調整 / 安全なタイミングでプロセスを終了）を記録する。必要な確認コマンドの配列も含める。この診断データのPIDを実ホストでkillしない。\n')
    preserve(ctx,'capture/df.txt','capture/du.txt','capture/lsof.txt')


def c7(ctx):
    unchanged(ctx,'capture/df.txt','capture/du.txt','capture/lsof.txt')
    answer(ctx,dict(cause='deleted-open-file',pid=ctx.data['pid'],path='/srv/data/app.log',action='coordinate-log-reopen',verify=['lsof +L1','df -h']))


SOL7="""python3 - <<'PYCODE'
import json
line=open('capture/lsof.txt').read().splitlines()[1].split()
json.dump(dict(cause='deleted-open-file',pid=int(line[1]),path='/srv/data/app.log',action='coordinate-log-reopen',verify=['lsof +L1','df -h']),open('result.json','w'))
PYCODE"""
add(7,'削除済みなのに容量が戻らない','dfとduの差を、プロセスが開いている削除済みファイルと関連付けます。',
    ['採取lsofのPIDとNLINKを読む','影響を確認してログ再オープンを調整する計画を記録'],s7,c7,SOL7,[SOL7.replace('coordinate-log-reopen','kill-all-processes')],
    '名前を削除しても、プロセスがファイル記述子を保持していれば領域は残ることがあります。業務影響を確認してログ再オープンや対象サービスの再起動を調整し、開いた削除済みファイルと空き容量の両方を再確認します。')


def s8(ctx):
    base(ctx);case='REC-'+secrets.token_hex(3);ctx.data['case']=case
    dump(ctx,'case.json',dict(case=case,target='disposable-vm',scope=['dedicated-image','dojo-app.service'],preserve=['guest-root-disk','original-evidence']))
    ctx.write('requirements.txt','result.json: case, target=disposable-vm, steps=[snapshot,collect-readonly-evidence,identify-cause,prepare-rollback,repair-dedicated-target,verify-data-and-service,reboot-and-reverify,document]。scopeとpreserveはcase.jsonと同じ値。物理/ルートディスクを変更しない。\n')
    preserve(ctx,'case.json')


def c8(ctx):
    unchanged(ctx,'case.json')
    answer(ctx,dict(case=ctx.data['case'],target='disposable-vm',steps=['snapshot','collect-readonly-evidence','identify-cause','prepare-rollback','repair-dedicated-target','verify-data-and-service','reboot-and-reverify','document'],scope=['dedicated-image','dojo-app.service'],preserve=['guest-root-disk','original-evidence']))


SOL8="""python3 - <<'PYCODE'
import json
p=json.load(open('case.json'));p['steps']=['snapshot','collect-readonly-evidence','identify-cause','prepare-rollback','repair-dedicated-target','verify-data-and-service','reboot-and-reverify','document'];json.dump(p,open('result.json','w'))
PYCODE"""
add(8,'再起動後まで確認する復旧手順','一時的な復旧だけでなく、変更を戻せることと再起動後にも維持されることを計画します。',
    ['ケース資料の対象と保持対象を維持','要件の順序で復旧ランブックを作成'],s8,c8,SOL8,[SOL8+"\npython3 -c \"import json;p=json.load(open('result.json'));p['steps'].remove('reboot-and-reverify');json.dump(p,open('result.json','w'))\""],
    '再起動後の確認は、手動で直した状態と永続設定の違いを見つけます。先に復元点を確保し、原本を保全してから最小範囲を修正し、データ・サービス・依存関係を確認します。実際のインストールや起動救援は使い捨てVMとコンソールで行います。')
