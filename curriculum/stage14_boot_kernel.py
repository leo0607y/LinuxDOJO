"""Stage 14: ブート・カーネル・ハードウェア。設定例と採取済み出力を本物のツールで読み解く。"""
import hashlib
import re
import secrets
import subprocess
from pathlib import Path

from engine.runner import register

S = 14
NOTE = ("作業対象はこの課題のフォルダだけです。実機のGRUB・カーネル・udev・fstabは変更しません。"
        "設定例とサンプル出力（lspci・dmesgなど）を読み、grep/awk/sed/python3で編集・抽出します。"
        "実際の再起動やrescue起動はVM実習で確認します。")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def keep(ctx, *names):
    """原本として保護するファイルを記録する。"""
    ctx.data['orig'] = {n: sha(ctx.read(n)) for n in names}


def intact(ctx):
    for n, h in ctx.data['orig'].items():
        ctx.require(sha(ctx.need_file(n)) == h, n + ' は原本です。変更しないでください。')


def kv(ctx, name):
    out = {}
    for ln in ctx.need_file(name).splitlines():
        if ln.strip():
            ctx.require('=' in ln, name + ' は key=value の形式で1行ずつ書きます。')
            k, v = ln.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'14-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='起動まわりは「設定を書く」「生成/反映する」「再起動後に確認する」を別の手順として覚えましょう。')


def run_sh(ctx, script):
    return subprocess.run(['bash', script], cwd=ctx.work, capture_output=True, text=True, timeout=10)


# ---------------------------------------------------------------- 14-1 GRUB
def s1(ctx):
    p = 'dojo.tag=' + secrets.token_hex(2)
    ctx.data['param'] = p
    ctx.write('default_grub', 'GRUB_DEFAULT=0\nGRUB_TIMEOUT=5\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\nGRUB_CMDLINE_LINUX=""\n')
    ctx.write('grub.cfg.in', "set timeout=@TO@\nmenuentry 'Linux' {\n  linux /vmlinuz root=/dev/sda1 ro @CMD@\n  initrd /initrd.img\n}\n")
    ctx.write('mkconfig.sh', '#!/bin/bash\n# update-grub / grub-mkconfig の代わりの訓練用スクリプト\n. ./default_grub\n'
              'sed -e "s|@CMD@|$GRUB_CMDLINE_LINUX_DEFAULT|" -e "s|@TO@|$GRUB_TIMEOUT|" grub.cfg.in > grub.cfg\n', mode=0o755)
    run_sh(ctx, 'mkconfig.sh')
    ctx.write('ticket.txt', f'次回起動から追加するカーネル引数: {p}\n既存の quiet splash は残すこと。\n'
              'default_grub が元の設定、grub.cfg は ./mkconfig.sh が生成します。\n')
    keep(ctx, 'grub.cfg.in', 'mkconfig.sh')
    ctx.data['gcfg0'] = sha(ctx.read('grub.cfg'))


def c1(ctx):
    intact(ctx)
    p = ctx.data['param']
    lines = ctx.need_file('default_grub').splitlines()
    cm = [l for l in lines if l.startswith('GRUB_CMDLINE_LINUX_DEFAULT=')]
    ctx.require(len(cm) == 1, 'GRUB_CMDLINE_LINUX_DEFAULT は1行だけにします。')
    ctx.require(cm[0] == f'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash {p}"', '既存の引数を残し、末尾に新しい引数を追加します。')
    ctx.require([l for l in lines if 'CMDLINE_LINUX_DEFAULT' not in l] == ['GRUB_DEFAULT=0', 'GRUB_TIMEOUT=5', 'GRUB_CMDLINE_LINUX=""'], '他の設定行は変えません。')
    ctx.require(sha(ctx.need_file('grub.cfg')) != ctx.data['gcfg0'] and f'ro quiet splash {p}' in ctx.need_file('grub.cfg'),
                'default_grubを編集しただけでは反映されません。./mkconfig.sh でgrub.cfgを生成します。')


mission(1, 'GRUBの設定とカーネル引数の追加',
        'チケットのカーネル引数を次回起動から有効にします。/etc/default/grub相当の元設定を直し、grub.cfgを再生成します。',
        ['default_grubのGRUB_CMDLINE_LINUX_DEFAULTへ引数を追加する', './mkconfig.shでgrub.cfgを再生成する'], s1, c1,
        """P=$(grep -o 'dojo.tag=[0-9a-f]*' ticket.txt)
sed -i "s/^\\(GRUB_CMDLINE_LINUX_DEFAULT=\\"[^\\"]*\\)\\"/\\1 $P\\"/" default_grub
./mkconfig.sh""",
        ['P=$(grep -o "dojo.tag=[0-9a-f]*" ticket.txt); sed -i "s/ro quiet splash/ro quiet splash $P/" grub.cfg',
         'P=$(grep -o "dojo.tag=[0-9a-f]*" ticket.txt); echo "GRUB_CMDLINE_LINUX_DEFAULT=\\"$P\\"" >> default_grub; ./mkconfig.sh',
         'P=$(grep -o "dojo.tag=[0-9a-f]*" ticket.txt); sed -i "s/quiet splash/$P/" default_grub; ./mkconfig.sh'],
        'grub.cfgは生成物なので直接編集せず、/etc/default/grubを直して update-grub（grub2-mkconfig）で再生成します。直接編集は次の更新で消えます。',
        '元の設定と生成物のどちらを直すべきか考えます。', 'sed -iで行の閉じ引用符の前に引数を足し、./mkconfig.shを実行します。')


# ---------------------------------------------------------------- 14-2 起動順
def s2(ctx):
    names = secrets.SystemRandom().sample(['cache', 'queue', 'api', 'worker', 'report', 'mailer', 'proxy'], 4)
    names = [n + '.service' for n in names]
    ctx.data['order'] = names
    for i, n in enumerate(names):
        prev = 'network-online.target' if i == 0 else names[i - 1]
        ctx.write('units/' + n, f'[Unit]\nDescription=dojo {n}\nAfter={prev}\nWants={prev}\n\n[Service]\nExecStart=/bin/true\n')
    ctx.write('ticket.txt', 'units/ のサービスをsystemdが起動する順(After=を辿る)に、1行1ユニットでstart_order.txtへ書く。network-online.targetは含めない。\n')
    keep(ctx, *['units/' + n for n in names])


def c2(ctx):
    intact(ctx)
    got = ctx.need_file('start_order.txt').split()
    ctx.require(got == ctx.data['order'], '各ユニットのAfter=を辿り、先に起動するものから順に書きます。')


mission(2, 'systemdの起動順を読み解く', 'After=が連鎖した4つのサービスの起動順を確認します。',
        ['unitsのAfter=を読む', 'start_order.txtに起動順で書く'], s2, c2,
        """python3 - <<'PYCODE'
import glob,re,os
after={}
for f in glob.glob('units/*.service'):
    after[os.path.basename(f)]=re.search(r'^After=(.*)$',open(f).read(),re.M).group(1)
cur='network-online.target'; out=[]
while True:
    nxt=[u for u,a in after.items() if a==cur]
    if not nxt: break
    cur=nxt[0]; out.append(cur)
open('start_order.txt','w').write('\\n'.join(out)+'\\n')
PYCODE""",
        ["ls units > start_order.txt", "ls -r units > start_order.txt"],
        'After=は「その後に起動」。After=が指す相手が先です。Wants=は依存追加で順序は決めません。順序は systemd-analyze critical-chain でも確認できます。',
        'ファイル名順は起動順ではありません。', 'After=行をgrepし、network-online.targetから辿ります。')


# ---------------------------------------------------------------- 14-3 rescue
def s3(ctx):
    root, data = secrets.token_hex(4), secrets.token_hex(4)
    bad = data[:-1] + ('0' if data[-1] != '0' else '1')
    pw = 'Rescue-' + secrets.token_hex(3)
    ctx.data.update(root=root, data=data, pw=pw)
    ctx.write('blkid.txt', f'/dev/vda1: LABEL="root" UUID="{root}" TYPE="ext4"\n/dev/vdb1: LABEL="data" UUID="{data}" TYPE="ext4"\n')
    ctx.write('fstab', f'UUID={root} / ext4 defaults 0 1\nUUID={bad} /data ext4 defaults 0 2\n')
    ctx.write('shadow', 'root:!:19000:0:99999:7:::\ndaemon:*:19000:0:99999:7:::\nops:$6$salt$abcdef:19000:0:99999:7:::\n')
    ctx.write('ticket.txt', f'emergency modeで起動した。\n1) /data がマウントできない: fstabのUUIDをblkid.txtの正しい値へ(他行は変更しない)\n'
              f'2) rootがロックされている: shadowのrootのハッシュを次のパスワードの$6$ハッシュに(salt dojosalt)\npassword: {pw}\n(訓練用ダミー)\n')
    keep(ctx, 'blkid.txt')
    ctx.data['fstab0'] = ctx.read('fstab').splitlines()


def c3(ctx):
    intact(ctx)
    d = ctx.data
    f = ctx.need_file('fstab').splitlines()
    ctx.require(f == [d['fstab0'][0], f"UUID={d['data']} /data ext4 defaults 0 2"], 'rootの行は維持し、/data行のUUIDだけを正しい値へ直します。')
    rows = [l.split(':') for l in ctx.need_file('shadow').splitlines()]
    ctx.require(len(rows) == 3 and rows[1][1] == '*' and rows[2][1] == '$6$salt$abcdef', '他のユーザー行は変更しません。')
    h = rows[0][1]
    m = re.match(r'^\$6\$([^$]+)\$', h)
    ctx.require(bool(m), 'rootのハッシュは$6$形式(openssl passwd -6)にします。')
    exp = subprocess.run(['openssl', 'passwd', '-6', '-salt', m.group(1), d['pw']], capture_output=True, text=True).stdout.strip()
    ctx.require(h == exp, 'ハッシュがチケットのパスワードと一致しません。')


mission(3, 'emergencyモードでfstabとパスワードを直す', 'emergencyモードで起動しました。fstabの誤記とロックされたrootを修復します。',
        ['blkid.txtから正しいUUIDを取りfstabを直す', 'shadowのrootへ新しいハッシュを設定する'], s3, c3,
        """U=$(awk '/LABEL="data"/{for(i=1;i<=NF;i++) if($i ~ /^UUID=/){gsub(/UUID=|"/,"",$i); print $i}}' blkid.txt)
sed -i "s|^UUID=[^ ]* /data|UUID=$U /data|" fstab
PW=$(sed -n 's/^password: //p' ticket.txt)
H=$(openssl passwd -6 -salt dojosalt "$PW")
sed -i "s|^root:[^:]*:|root:$H:|" shadow""",
        ['sed -i "s|^root:[^:]*:|root::|" shadow', 'sed -i "s|/data|/dat|" fstab',
         'U=$(grep -o "UUID=\\"[^\\"]*" blkid.txt | head -1 | cut -d\\" -f2); sed -i "s|^UUID=[^ ]* /data|UUID=$U /data|" fstab'],
        'fstabの誤りで起動が止まったら、rescue/emergencyでrootをrw再マウントして直します(mount -o remount,rw /)。パスワードはpasswd rootが基本で、ここでは仕組みを学ぶためハッシュを直接扱いました。空パスワードは危険です。',
        'UUIDはlabelではなくデバイスごとに固有です。', 'blkid出力からLABEL="data"の行を選び、openssl passwd -6でハッシュを作ります。')


# ---------------------------------------------------------------- 14-4 modules
POOL = ['pcspkr', 'nouveau', 'bluetooth', 'snd_hda_intel', 'floppy', 'iwlwifi', 'uvcvideo', 'joydev', 'psmouse', 'cdrom', 'usbhid', 'btusb']


def s4(ctx):
    r = secrets.SystemRandom()
    m = r.sample(POOL, 9)
    bl, ins, loaded_only, target = m[:3], m[3:5], m[5:8], m[8]
    loaded = sorted(set(bl[:2] + ins[:1] + loaded_only))
    ctx.data['expect'] = sorted(set(bl + ins) & set(loaded))
    ctx.data['target'] = target
    ctx.write('modprobe.d/blacklist.conf', '# 基本の無効化\n' + ''.join(f'blacklist {x}\n' for x in bl) + ''.join(f'install {x} /bin/true\n' for x in ins))
    ctx.write('modprobe.d/local.conf', '# ローカル設定\n')
    ctx.write('lsmod.txt', 'Module                  Size  Used by\n' + ''.join(f'{x:<22}{r.randint(10000, 99999)}  0\n' for x in loaded))
    ctx.write('ticket.txt', f'1) modprobe.d の blacklist / install ... /bin/true で無効化されているのに現在ロード中のモジュールを、lsmod.txtから探しloaded_blacklisted.txtへ(昇順1行1つ)。\n'
              f'2) 追加でmodprobe.d/local.confへ次の行を追記する:\nblacklist {target}\n')
    keep(ctx, 'modprobe.d/blacklist.conf', 'lsmod.txt')


def c4(ctx):
    intact(ctx)
    ctx.require(ctx.need_file('loaded_blacklisted.txt').split() == ctx.data['expect'], 'blacklistとinstall /bin/trueの両方を対象に、ロード中のものだけを昇順で書きます。')
    ls = ctx.need_file('modprobe.d/local.conf').splitlines()
    ctx.require(ls == ['# ローカル設定', 'blacklist ' + ctx.data['target']], 'local.confへ指定のblacklist行を1行追記します(既存コメントは維持)。')


mission(4, 'カーネルモジュールの無効化設定を読む', 'blacklistされているはずのモジュールが動いています。設定とlsmodを突き合わせ、追加の無効化も入れます。',
        ['modprobe.dとlsmodを突き合わせる', 'local.confへblacklistを追記する'], s4, c4,
        """cat modprobe.d/*.conf | awk '$1=="blacklist"{print $2} $1=="install"&&$3=="/bin/true"{print $2}' | sort -u > bl.tmp
awk 'NR>1{print $1}' lsmod.txt | sort -u | comm -12 - bl.tmp > loaded_blacklisted.txt
rm bl.tmp
T=$(grep -o 'blacklist [a-z_0-9]*$' ticket.txt | cut -d' ' -f2)
echo "blacklist $T" >> modprobe.d/local.conf""",
        ["awk 'NR>1{print $1}' lsmod.txt | sort > loaded_blacklisted.txt",
         "grep -h blacklist modprobe.d/*.conf | awk '{print $2}' | sort > loaded_blacklisted.txt"],
        'blacklistは自動ロードを防ぐだけで、既にロード済みや他モジュールの依存では動き続けます。install X /bin/trueは手動modprobeも封じます。変更後はinitramfsの更新(update-initramfs -u)も必要な場合があります。',
        'lsmodの1列目がモジュール名です。', 'awkで抽出して、sortしたものをcommで共通部分を取ります。')


# ---------------------------------------------------------------- 14-5 sysctl
def s5(ctx):
    r = secrets.SystemRandom()
    spec = {'vm.swappiness': [10, 20, 30, 40], 'net.core.somaxconn': [1024, 2048, 4096], 'fs.file-max': [200000, 500000, 900000]}
    k1, k2 = r.sample(list(spec), 2)
    v1, v2 = r.choice(spec[k1]), r.choice(spec[k2])
    old = 60 if k1 == 'vm.swappiness' else 128
    ctx.data.update(k1=k1, k2=k2, v1=v1, v2=v2)
    ctx.write('sysctl.conf', f'# 恒久設定\nnet.ipv4.tcp_syncookies = 1\n{k1} = {old}\n')
    ctx.write('runtime.txt', f'net.ipv4.tcp_syncookies = 1\nnet.ipv4.ip_forward = 1\n{k1} = {v1}\n{k2} = {v2}\n')
    ctx.write('ticket.txt', f'sysctlで一時的に調整した値のうち、次の2項目だけを再起動後も維持したい: {k1}, {k2}\n(ip_forwardの一時変更は検証用なので恒久化しない)\n値はruntime.txtの現在値。sysctl.confの古い設定は置き換え、重複させない。\n')


def c5(ctx):
    d = ctx.data
    lines = ctx.need_file('sysctl.conf').splitlines()
    ent = {}
    for l in lines:
        if l.strip() and not l.startswith('#'):
            k, _, v = l.partition('=')
            ctx.require(k.strip() not in ent, f'{k.strip()} が重複しています。')
            ent[k.strip()] = v.strip()
    ctx.require(ent.get(d['k1']) == str(d['v1']) and ent.get(d['k2']) == str(d['v2']), '対象2項目をruntime.txtの現在値で恒久設定に入れます。')
    ctx.require('net.ipv4.ip_forward' not in ent, 'ip_forwardは恒久化しません。')
    ctx.require(ent.get('net.ipv4.tcp_syncookies') == '1' and '# 恒久設定' in lines, '既存の他の設定は維持します。')


mission(5, 'sysctlの恒久設定と一時設定', 'sysctl -wで調整した値は再起動で戻ります。必要なものだけを恒久設定へ移します。',
        ['runtime.txtの現在値を確認する', 'sysctl.confへ対象項目だけを重複なしで反映する'], s5, c5,
        """for k in $(sed -n 's/^.*維持したい: //p' ticket.txt | tr -d ',' ); do
  sed -i "/^$k[ =]/d" sysctl.conf
  grep "^$k " runtime.txt >> sysctl.conf
done""",
        ['cat runtime.txt >> sysctl.conf', "sed -i 's/60/10/' sysctl.conf"],
        'sysctl -w は現在のカーネルだけ、/etc/sysctl.conf と /etc/sysctl.d/*.conf は起動時に読まれる恒久設定です。反映は sysctl --system で行い、重複キーは後勝ちになり紛らわしいので避けます。',
        '現在値をそのまま全部コピーすると不要な一時変更まで固定されます。', 'ticketのキーを取り出し、sedで古い行を消してgrepで追記します。')


# ---------------------------------------------------------------- 14-6 /proc /sys
def s6(ctx):
    r = secrets.SystemRandom()
    n = r.randint(2, 8)
    mem = r.randint(2000000, 16000000)
    load = f'{r.randint(0, 9)}.{r.randint(10, 99)}'
    mac = ':'.join(secrets.token_hex(1) for _ in range(6))
    ctx.data['expect'] = dict(cpus=str(n), mem_total_kb=str(mem), load1=load, mac=mac)
    ctx.write('proc/cpuinfo', ''.join(f'processor\t: {i}\nmodel name\t: Dojo CPU\ncpu MHz\t\t: 2400.0\ncpu cores\t: {max(1, n // 2)}\n\n' for i in range(n)))
    ctx.write('proc/meminfo', f'MemTotal:       {mem} kB\nMemFree:        {mem // 3} kB\nMemAvailable:   {mem // 2} kB\n')
    ctx.write('proc/loadavg', f'{load} 0.50 0.40 1/200 4242\n')
    ctx.write('sys/class/net/eth0/address', mac + '\n')
    ctx.write('ticket.txt', '採取済みの proc/ と sys/ から、report.txt に次の4行を key=value で書く:\ncpus (processor数), mem_total_kb, load1 (1分平均), mac (eth0)\n')
    keep(ctx, 'proc/cpuinfo', 'proc/meminfo', 'proc/loadavg', 'sys/class/net/eth0/address')


def c6(ctx):
    intact(ctx)
    ctx.require(kv(ctx, 'report.txt') == ctx.data['expect'], 'cpusは論理プロセッサ数(processor行)、メモリはMemTotalのkB値です。')


mission(6, '/procと/sysから情報を読む', '/proc と /sys はカーネルが見せる情報です。採取済みコピーから必要な値を集めます。',
        ['cpuinfo/meminfo/loadavg/sysを読む', 'report.txtにkey=valueで書く'], s6, c6,
        """{ echo cpus=$(grep -c '^processor' proc/cpuinfo)
  echo mem_total_kb=$(awk '/^MemTotal/{print $2}' proc/meminfo)
  echo load1=$(cut -d' ' -f1 proc/loadavg)
  echo mac=$(cat sys/class/net/eth0/address); } > report.txt""",
        ["{ echo cpus=$(grep -c cpu proc/cpuinfo); echo mem_total_kb=$(awk '/^MemFree/{print $2}' proc/meminfo); echo load1=$(cut -d' ' -f2 proc/loadavg); echo mac=$(cat sys/class/net/eth0/address); } > report.txt"],
        '/procはプロセスとカーネル状態、/sysはデバイスと属性を表す仮想ファイルです。実体はディスク上になくread時に生成されます。「cpu cores」は物理コア数、processorは論理CPU数と別物です。',
        'MemTotalとMemFreeの違い、cpu行とprocessor行の違いに注意します。', 'grep -cで行を数え、awkで2列目を取ります。')


# ---------------------------------------------------------------- 14-7 hardware
def s7(ctx):
    r = secrets.SystemRandom()
    slot = f'{r.randint(1, 9):02d}:00.0'
    vid, pid = secrets.token_hex(2), secrets.token_hex(2)
    sn = 'SN' + secrets.token_hex(4).upper()
    bsn = 'BB' + secrets.token_hex(4).upper()
    prod = r.choice(['PowerEdge R250', 'ThinkSystem SR630', 'ProLiant DL20'])
    ctx.data['expect'] = dict(nic_slot=slot, usb_id=f'{vid}:{pid}', serial=sn, product=prod)
    ctx.write('lspci.txt', f'00:00.0 Host bridge: Intel Corporation Device 1234\n00:02.0 VGA compatible controller: Dojo Graphics\n{slot} Ethernet controller: Intel Corporation I219-V\n00:1f.3 Audio device: Intel Corporation Device 5678\n')
    ctx.write('lsusb.txt', f'Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\nBus 001 Device 003: ID 046d:c52b Logitech USB Receiver\nBus 001 Device 004: ID {vid}:{pid} Kingston DataTraveler\n')
    ctx.write('dmidecode.txt', f'Handle 0x0100\nSystem Information\n\tManufacturer: DojoCorp\n\tProduct Name: {prod}\n\tSerial Number: {sn}\n\nHandle 0x0200\nBase Board Information\n\tProduct Name: BB-100\n\tSerial Number: {bsn}\n\n')
    ctx.write('ticket.txt', '資産台帳用にhw.txtへkey=valueで書く: nic_slot(Ethernetコントローラのスロット), usb_id(DataTravelerのID vid:pid), serial と product(dmidecodeのSystem Information。Base Boardではない)\n')
    keep(ctx, 'lspci.txt', 'lsusb.txt', 'dmidecode.txt')


def c7(ctx):
    intact(ctx)
    ctx.require(kv(ctx, 'hw.txt') == ctx.data['expect'], 'Ethernet行のスロット、DataTravelerのID、System Information節のシリアルと製品名を確認します。')


mission(7, 'lspci・lsusb・dmidecodeの読み解き', '資産台帳のため、ハードウェア採取結果から必要な値を抜き出します。',
        ['lspci/lsusb/dmidecodeを読む', 'hw.txtへ書く'], s7, c7,
        """{ echo nic_slot=$(awk '/Ethernet controller/{print $1}' lspci.txt)
  echo usb_id=$(awk '/DataTraveler/{print $6}' lsusb.txt)
  S=$(sed -n '/^System Information/,/^$/p' dmidecode.txt)
  echo serial=$(echo "$S" | awk -F': ' '/Serial Number/{print $2}')
  echo product=$(echo "$S" | awk -F': ' '/Product Name/{print $2}'); } > hw.txt""",
        ["{ echo nic_slot=00:00.0; echo usb_id=1d6b:0002; echo serial=x; echo product=y; } > hw.txt",
         "{ echo nic_slot=$(awk '/Ethernet/{print $1}' lspci.txt); echo usb_id=$(awk '/DataTraveler/{print $6}' lsusb.txt); echo serial=$(awk -F': ' '/Serial Number/{print $2}' dmidecode.txt | tail -1); echo product=$(awk -F': ' '/Product Name/{print $2}' dmidecode.txt | head -1); } > hw.txt"],
        'lspciはPCI、lsusbはUSB、dmidecodeはBIOSのDMI表を表示します(dmidecodeは通常root権限)。dmidecodeは節(System/Base Board)ごとに同名項目があるので節を絞ります。',
        'dmidecodeは同じ項目名が複数あります。', 'sed -n \'/開始/,/^$/p\' で節を切り出してからawkします。')


# ---------------------------------------------------------------- 14-8 dmesg
def s8(ctx):
    r = secrets.SystemRandom()
    bad, ok = r.sample(['sda', 'sdb', 'sdc'], 2)
    n = r.randint(4, 9)
    t = 10.0
    out = ['[    0.000000] Linux version 5.15.0-91-generic', '[    2.100000] EXT4-fs (sda1): mounted filesystem']
    ev = []
    for i in range(n):
        ev.append(f'blk_update_request: I/O error, dev {bad}, sector {r.randint(1000, 999999)}')
        ev.append(f'Buffer I/O error on dev {bad}1, logical block {r.randint(1, 9999)}')
    ev.append(f'blk_update_request: I/O error, dev {ok}, sector 4096')
    ev.append('usb 1-1: USB disconnect, device number 3')
    ev.append('EXT4-fs error (device sda1): ext4_find_entry:1455: inode #2: comm ls: reading directory lblock 0')
    r.shuffle(ev)
    for e in ev:
        t += r.random() * 5
        out.append(f'[{t:12.6f}] {e}')
    ctx.write('dmesg.txt', '\n'.join(out) + '\n')
    ctx.data['expect'] = dict(device=bad, io_errors=str(n), cause='disk-io-error')
    ctx.write('ticket.txt', 'dmesg.txtから、最も多く "I/O error, dev X," を出しているディスクを特定し、diagnosis.txtへ\ndevice=, io_errors=(その行の数), cause=disk-io-error を書く。\n')
    keep(ctx, 'dmesg.txt')


def c8(ctx):
    intact(ctx)
    ctx.require(kv(ctx, 'diagnosis.txt') == ctx.data['expect'], '"I/O error, dev X,"の行をデバイスごとに数え、最多のものを選びます(Buffer I/O errorは別メッセージ)。')


mission(8, 'dmesgからディスク障害を推定', 'カーネルログに複数のエラーがあります。どのディスクが壊れかけているかを回数から推定します。',
        ['デバイスごとのI/Oエラーを集計する', 'diagnosis.txtに記録する'], s8, c8,
        """D=$(grep -o 'I/O error, dev sd[a-z]' dmesg.txt | awk '{print $4}' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
N=$(grep -c "I/O error, dev $D," dmesg.txt)
printf 'device=%s\\nio_errors=%s\\ncause=disk-io-error\\n' "$D" "$N" > diagnosis.txt""",
        ["N=$(grep -c error dmesg.txt); printf 'device=sda\\nio_errors=%s\\ncause=disk-io-error\\n' $N > diagnosis.txt",
         "N=$(grep -c 'I/O error' dmesg.txt); printf 'device=sdb\\nio_errors=%s\\ncause=disk-io-error\\n' $N > diagnosis.txt"],
        '同じデバイスに繰り返すI/Oエラーはディスクやケーブルの障害の兆候です。1回限りやUSB切断は別の問題です。SMART確認(smartctl)とバックアップ・交換計画へ進みます。',
        '単発のエラーとの違いを回数で判断します。', 'grep -oで抽出し、sort | uniq -c | sort -rnで集計します。')


# ---------------------------------------------------------------- 14-9 kernel version
def s9(ctx):
    r = secrets.SystemRandom()
    vs = sorted(r.sample(range(20, 120), 5))
    run = vs[r.randint(1, 3)]
    pk = [f'linux-image-5.15.0-{v}-generic' for v in vs]
    ctx.data['expect'] = sorted(x for x in pk if x != f'linux-image-5.15.0-{run}-generic' and x != pk[-1])
    shuf = pk[:]
    r.shuffle(shuf)
    ctx.write('installed.txt', ''.join(f'ii  {x}  5.15.0-{x.split("-")[3]}.1  amd64  Signed kernel image\n' for x in shuf))
    ctx.write('uname.txt', f'Linux dojo 5.15.0-{run}-generic #1 SMP x86_64 GNU/Linux\n')
    ctx.write('ticket.txt', 'ディスク整理のため、削除候補のカーネルパッケージ名をremovable.txtへ(1行1つ、バージョン順)。\n実行中のカーネルと、最新のカーネルは残す。\n')
    keep(ctx, 'installed.txt', 'uname.txt')


def c9(ctx):
    intact(ctx)
    got = ctx.need_file('removable.txt').split()
    ctx.require(sorted(got) == ctx.data['expect'] and len(got) == len(set(got)), '実行中(uname -r)と最新(sort -Vの末尾)以外のlinux-imageだけを書きます。')
    ctx.require(got == sorted(got, key=lambda x: int(x.split('-')[3])), 'バージョン順(数値)で並べます。')


mission(9, 'unameと古いカーネルの整理', 'uname -rの結果とインストール済みカーネル一覧から、削除してよい古いカーネルを選びます。',
        ['実行中カーネルを特定する', 'removable.txtを作る'], s9, c9,
        """R=$(awk '{print $3}' uname.txt)
PK=$(awk '{print $2}' installed.txt | sort -V)
N=$(echo "$PK" | tail -1)
echo "$PK" | grep -vxF -e "linux-image-$R" -e "$N" > removable.txt""",
        ["awk '{print $2}' installed.txt | sort > removable.txt", "awk '{print $2}' installed.txt | sort -V | head -2 > removable.txt"],
        'uname -rは実行中、dpkg -l/rpm -qaはインストール済みです。更新後は再起動するまで古いカーネルが動きます。数値は辞書順でなくsort -Vで比べます。通常は直前の1世代を予備に残します。',
        '辞書順だと 100 は 20 より前になります。', 'sort -V と grep -vxF を組み合わせます。')


# ---------------------------------------------------------------- 14-10 boot failure
def s10(ctx):
    root, old = secrets.token_hex(8), secrets.token_hex(8)
    ctx.data['root'] = root
    ctx.write('blkid.txt', f'/dev/vda2: LABEL="root" UUID="{root}" TYPE="ext4"\n/dev/vdb1: LABEL="data" UUID="{secrets.token_hex(8)}" TYPE="ext4"\n')
    ctx.write('cmdline.txt', f'BOOT_IMAGE=/vmlinuz-5.15.0 root=UUID={old} ro quiet splash\n')
    ctx.write('boot.log', f'Loading Linux 5.15.0 ...\nLoading initial ramdisk ...\nBegin: Waiting for root file system ...\nGave up waiting for root file system device.\nALERT!  UUID={old} does not exist.  Dropping to a shell!\n(initramfs)\n')
    ctx.write('initramfs-modules.txt', 'ext4\nmbcache\njbd2\nvirtio_blk\n')
    ctx.write('ticket.txt', 'boot.logの原因を調べ、cmdline.txtのroot=UUID=を現在のrootの正しい値へ直す(他の引数は維持)。\ncause.txtに wrong-root-uuid か missing-fs-module のどちらかを書く。\n')
    keep(ctx, 'blkid.txt', 'boot.log', 'initramfs-modules.txt')
    ctx.data['old'] = old


def c10(ctx):
    intact(ctx)
    d = ctx.data
    ctx.require(ctx.need_file('cmdline.txt').strip() == f"BOOT_IMAGE=/vmlinuz-5.15.0 root=UUID={d['root']} ro quiet splash", 'root=UUID=だけを正しい値に変え、他の引数は維持します。')
    ctx.require(ctx.need_file('cause.txt').strip() == 'wrong-root-uuid', 'initramfsにはext4があるので、原因はファイルシステムモジュール不足ではありません。')


mission(10, 'initramfsの起動失敗を診断する', '起動中に(initramfs)プロンプトへ落ちました。ログと情報から原因を特定し修正します。',
        ['boot.logとblkid・モジュール一覧を比較する', 'cmdline.txtとcause.txtを修正する'], s10, c10,
        """U=$(sed -n 's/.*LABEL="root" UUID="\\([^"]*\\)".*/\\1/p' blkid.txt)
sed -i "s/root=UUID=[^ ]*/root=UUID=$U/" cmdline.txt
echo wrong-root-uuid > cause.txt""",
        ['echo missing-fs-module > cause.txt', 'sed -i "s/root=UUID=[^ ]*/root=\\/dev\\/vda2/" cmdline.txt; echo wrong-root-uuid > cause.txt'],
        '"Gave up waiting for root file system"と"UUID=... does not exist"はrootのUUID違い(ディスク交換・複製)や、ストレージドライバがinitramfsに無い場合に出ます。blkidとinitramfsの内容(lsinitramfs)を照合します。',
        'ログのUUIDは実際のデバイスと一致しているでしょうか。', 'blkidのLABEL="root"の行からUUIDを取り出します。')


# ---------------------------------------------------------------- 14-11 udev
def s11(ctx):
    vid, pid = secrets.token_hex(2), secrets.token_hex(2)
    name = 'backup' + secrets.token_hex(2)
    ctx.data.update(vid=vid, pid=pid, name=name)
    ctx.write('lsusb.txt', f'Bus 001 Device 002: ID 8087:0024 Intel Corp. Hub\nBus 001 Device 005: ID {vid}:{pid} Kingston DataTraveler\n')
    ctx.write('rules.d/70-local.rules', '# local rules\nSUBSYSTEM=="tty", ATTRS{idVendor}=="0403", SYMLINK+="ttyserial"\n')
    ctx.write('ticket.txt', f'DataTravelerをシンボリックリンク名 /dev/{name}、権限0660で固定したい。\nrules.d/70-local.rules へ SUBSYSTEM=="usb" の規則を1行追記する(idVendor/idProduct==で照合、既存行は維持)。\nsymlink: {name}\n')
    keep(ctx, 'lsusb.txt')
    ctx.data['rules0'] = ctx.read('rules.d/70-local.rules')


def c11(ctx):
    intact(ctx)
    d = ctx.data
    t = ctx.need_file('rules.d/70-local.rules')
    ctx.require(t.startswith(d['rules0']), '既存の規則は維持して追記します。')
    new = [l for l in t[len(d['rules0']):].splitlines() if l.strip()]
    ctx.require(len(new) == 1, '追記する規則は1行です。')
    l = new[0]
    for frag in ['SUBSYSTEM=="usb"', f'ATTR{{idVendor}}=="{d["vid"]}"', f'ATTR{{idProduct}}=="{d["pid"]}"', f'SYMLINK+="{d["name"]}"', 'MODE="0660"']:
        ctx.require(frag in l, f'規則に {frag} が必要です(照合は==、代入は=や+=)。')


mission(11, 'udevルールでデバイス名を固定する', 'USBメモリに常に同じ名前と権限を与えるudevルールを書きます。',
        ['lsusbからidVendor/idProductを得る', 'rules.dへ規則を追記する'], s11, c11,
        """ID=$(awk '/DataTraveler/{print $6}' lsusb.txt)
V=${ID%:*}; P=${ID#*:}
N=$(sed -n 's/^symlink: //p' ticket.txt)
cat >> rules.d/70-local.rules <<EOF
SUBSYSTEM=="usb", ATTR{idVendor}=="$V", ATTR{idProduct}=="$P", SYMLINK+="$N", MODE="0660"
EOF""",
        ["echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"8087\", ATTR{idProduct}==\"0024\", SYMLINK+=\"x\", MODE=\"0660\"' >> rules.d/70-local.rules",
         "ID=$(awk '/DataTraveler/{print $6}' lsusb.txt); echo \"SUBSYSTEM=\\\"usb\\\", ATTR{idVendor}=\\\"${ID%:*}\\\", SYMLINK=\\\"x\\\"\" >> rules.d/70-local.rules"],
        'udevルールは「条件(==)」と「動作(=, +=)」をカンマで並べます。変更後は udevadm control --reload と udevadm trigger で反映・検証(udevadm test)します。条件を絞らないと他のデバイスにも適用されます。',
        '条件に使うのはlsusbのID(ベンダー:製品)です。', '$6のID vid:pid を ${ID%:*} と ${ID#*:} に分けます。')


# ---------------------------------------------------------------- 14-12 target
def s12(ctx):
    k = secrets.choice(['1', '3', '5'])
    cur = secrets.choice([t for t in ['rescue', 'multi-user', 'graphical'] if t != {'1': 'rescue', '3': 'multi-user', '5': 'graphical'}[k]])
    ctx.data['want'] = {'1': 'rescue', '3': 'multi-user', '5': 'graphical'}[k]
    for t in ['rescue', 'multi-user', 'graphical']:
        ctx.write(f'lib/systemd/system/{t}.target', f'[Unit]\nDescription={t}\n')
    ctx.mkdir('etc/systemd/system')
    link = ctx.p('etc/systemd/system/default.target')
    link.symlink_to(f'../../../lib/systemd/system/{cur}.target')
    ctx.write('ticket.txt', f'サーバーの標準起動をランレベル{k}相当にする。\n(1=rescue, 3=multi-user, 5=graphical)\nsystemctl set-default と同じく、default.targetのシンボリックリンクを正しく差し替える。\nrunlevel: {k}\n')
    keep(ctx, *[f'lib/systemd/system/{t}.target' for t in ['rescue', 'multi-user', 'graphical']])


def c12(ctx):
    intact(ctx)
    link = ctx.p('etc/systemd/system/default.target')
    ctx.require(link.is_symlink(), 'default.targetはシンボリックリンクのままにします(ファイルで上書きしない)。')
    tgt = link.resolve()
    ctx.require(tgt == ctx.p(f"lib/systemd/system/{ctx.data['want']}.target").resolve(), 'ランレベルに対応するtargetを指します(1=rescue, 3=multi-user, 5=graphical)。')


mission(12, 'ランレベルとtargetの切り替え', '旧ランレベルの指示を、systemdのdefault.targetへ翻訳して切り替えます。',
        ['ランレベルをtargetに対応づける', 'default.targetのリンクを差し替える'], s12, c12,
        """K=$(sed -n 's/^runlevel: //p' ticket.txt)
case $K in 1) T=rescue;; 3) T=multi-user;; 5) T=graphical;; esac
ln -sfn ../../../lib/systemd/system/$T.target etc/systemd/system/default.target""",
        ['cp lib/systemd/system/multi-user.target etc/systemd/system/default.target',
         'ln -s ../../../lib/systemd/system/graphical.target etc/systemd/system/default.target',
         'echo multi-user.target > etc/systemd/system/default.target'],
        'systemctl set-default X.targetはdefault.targetのリンクを差し替えます。ランレベル1=rescue、3=multi-user、5=graphical。現在のセッションだけ切り替えるにはsystemctl isolateを使います。ln -sfnでリンク自体を置き換えます。',
        'リンクは既にあるので、置き換えるオプションが必要です。', 'ln -sfn を使います。')
