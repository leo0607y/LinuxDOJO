"""Stage 16: SELinux・AppArmor・ACL・属性・権限・資源制限・認証保護。

getenforce/getfacl/lsattr/getcap 等の出力は保存済みの記録（架空データ）です。作業フォルダの外や
本物のOS設定には一切触れず、root権限も不要です。実機での適用はVM実習で行います。
"""
import configparser
import hashlib
import json
import os
import re
import secrets
import stat

from engine.runner import register

S = 16
NOTICE = ("このステージの *.txt / *.log は保存済みの記録(架空データ)で、あなたのPCの現在の状態ではありません。"
          "変更は作業フォルダ内だけで行い、sudo/rootは使いません。実機への適用はVM実習で行います。")


def hx(n=3):
    return secrets.token_hex(n)


def sh(ctx, rel):
    return hashlib.sha256(ctx.p(rel).read_bytes()).hexdigest()


def prepare(gen):
    def setup(ctx):
        case = "ACC-" + hx(4)
        ctx.data["case"] = case
        files, expected, req = gen(ctx)
        ctx.data["expected"] = expected
        ctx.write("case.json", json.dumps({"case": case, "mode": "recorded-observations", "scope": "workspace only"}, indent=2))
        ctx.write("README.txt", NOTICE + "\n")
        ctx.write("requirements.txt", req)
        names = ["case.json", "requirements.txt"]
        for path, content in files.items():
            if isinstance(content, tuple):
                ctx.write(path, content[0], mode=content[1])
            else:
                ctx.write(path, content)
            if not path.startswith("work/"):
                names.append(path)
        ctx.data["originals"] = {n: sh(ctx, n) for n in names}
    return setup


def diagnosis(ctx):
    for name, digest in ctx.data["originals"].items():
        ctx.require(ctx.isfile(name) and not ctx.p(name).is_symlink() and sh(ctx, name) == digest,
                    f"記録・資料 {name} を変更せず残してください。")
    try:
        data = json.loads(ctx.need_file("diagnosis.json"))
    except ValueError:
        ctx.fail("diagnosis.json をJSONとして保存してください。")
    ctx.require(isinstance(data, dict) and data.get("case") == ctx.data["case"], "今回の case を diagnosis.json に記録してください。")
    for k, v in ctx.data["expected"].items():
        ctx.require(data.get(k) == v, f"diagnosis.json の {k} が資料の内容と一致しません。")
    return data


def originals_only(ctx):
    for name, digest in ctx.data["originals"].items():
        ctx.require(ctx.isfile(name) and sh(ctx, name) == digest, f"資料 {name} は変更せず残してください。")


def PY(body):
    return ("python3 - <<'PYCODE'\nimport json,re\ncase=json.load(open('case.json'))['case']\n" + body
            + "\nr['case']=case\njson.dump(r,open('diagnosis.json','w'),indent=2)\nPYCODE\n")


def norm(s):
    return " ".join(str(s).replace("'", "").replace('"', "").split())


def add(n, title, story, gen, objectives, hints, explanation, tip, solution, wrong, extra=None, diag=True):
    def check(ctx):
        data = diagnosis(ctx) if diag else originals_only(ctx)
        if extra:
            extra(ctx, data)
    register(id=f"16-{n}", stage=S, title=title, story=story + "\n\n" + NOTICE, objectives=objectives,
             hints=hints, answer=solution, explanation=explanation, tip=tip,
             setup=prepare(gen), check=check, solution=solution, wrong=wrong)


EMPTY = "printf '{}\\n' > diagnosis.json"
TIP = "記録の事実と推測を分け、最小の変更で直し、変更後に正常な利用も確認します。"


# ---------------------------------------------------------------- 16-1 SELinux context
def g1(ctx):
    site, bad = hx(), secrets.choice(["upload.html", "report.html", "news.html", "about.html"])
    files = {"getenforce.txt": "Enforcing\n",
             "ls-Z.txt": (f"system_u:object_r:httpd_sys_content_t:s0 /srv/www/{site}/index.html\n"
                          f"unconfined_u:object_r:user_home_t:s0 /srv/www/{site}/{bad}\n"
                          f"system_u:object_r:httpd_sys_content_t:s0 /srv/www/{site}/style.css\n"),
             "fcontext.txt": "/srv/www(/.*)?    all files    system_u:object_r:httpd_sys_content_t:s0\n"}
    exp = {"mode": "enforcing", "bad_file": f"/srv/www/{site}/{bad}", "current_type": "user_home_t",
           "expected_type": "httpd_sys_content_t", "fix": "restorecon", "avoid": "setenforce-0"}
    req = ("diagnosis.json: mode(getenforce出力を小文字で), bad_file(型が合わないファイル), current_type, expected_type(fcontext.txtの規則)、"
           "fixはrestoreconまたはsemanage-fcontext、avoidは避けるべき近道を setenforce-0 か chmod-777 から選ぶ。\n")
    return files, exp, req


S1 = PY("""exp=re.search(r'object_r:(\\w+):',open('fcontext.txt').read()).group(1)
r={'mode':open('getenforce.txt').read().strip().lower(),'expected_type':exp,'fix':'restorecon','avoid':'setenforce-0'}
for l in open('ls-Z.txt'):
    t=l.split(':')[2]; p=l.split()[1]
    if t!=exp: r['bad_file']=p; r['current_type']=t""")
add(1, "SELinuxの動作モードとファイルコンテキスト",
    "ホームで作ったHTMLを /srv/www へ mv したら、Webサーバーが403を返します。chmodは正しいのに拒否されるのは、SELinuxの型(タイプ)が合っていないからかもしれません。",
    g1, ["動作モードの採取記録からモードを読む", "コンテキストの採取記録と規則(既定コンテキストの規則)を比べ、型が違うファイルを特定してdiagnosis.jsonへ記録する"],
    ["getenforceは Enforcing / Permissive / Disabled を返します。型は user:role:type:level の3番目です。",
     "ls -Z の type と、そのパスに対する既定の規則を比べます。規則があるなら restorecon で戻せます。", S1],
    "mvは元のコンテキスト(user_home_t)を持ち込みます。パスの規則が既にあるなら restorecon -v で既定の型へ戻します。setenforce 0 は全体の保護を止めるので原因を隠す近道です。規則が無い場所のときだけ semanage fcontext で規則を追加します。",
    TIP, S1, [EMPTY, S1 + "\nprintf 'x\\n' >> getenforce.txt"])


# ---------------------------------------------------------------- 16-2 AVC
def g2(ctx):
    port = secrets.randbelow(900) + 8100
    pid = secrets.randbelow(5000) + 1000
    log = (f'type=AVC msg=audit(1763686000.101:401): avc:  denied  {{ read }} for  pid={pid} comm="rsync" name="dump.sql" dev="vda1" ino=991 '
           f'scontext=system_u:system_r:rsync_t:s0 tcontext=unconfined_u:object_r:user_home_t:s0 tclass=file permissive=1\n'
           f'type=AVC msg=audit(1763686001.202:402): avc:  denied  {{ name_bind }} for  pid={pid+7} comm="httpd" src={port} '
           f'scontext=system_u:system_r:httpd_t:s0 tcontext=system_u:object_r:unreserved_port_t:s0 tclass=tcp_socket permissive=0\n'
           f'type=SERVICE_START msg=audit(1763686001.300:403): unit=httpd result=failed\n')
    exp = {"enforced_comm": "httpd", "denied_perm": "name_bind", "source_type": "httpd_t", "port": port,
           "fix": "semanage-port", "fix_command": f"semanage port -a -t http_port_t -p tcp {port}"}
    req = ("diagnosis.json: permissive=0 の拒否だけを対象に enforced_comm, denied_perm, source_type, port(数値)。"
           "fixはsemanage-port/restorecon/setenforce-0から選び、fix_commandは半角スペース1つ区切りの完全なコマンド"
           "(Webサーバーが待受を許される型 http_port_t へそのポートを追加)。\n")
    return {"audit.log": log}, exp, req


S2 = PY("""for l in open('audit.log'):
    if 'permissive=0' in l and 'avc:' in l:
        port=int(re.search(r'src=(\\d+)',l).group(1))
        r={'enforced_comm':re.search(r'comm="(\\w+)"',l).group(1),'denied_perm':re.search(r'\\{ (\\w+) \\}',l).group(1),
           'source_type':re.search(r'scontext=\\w+:\\w+:(\\w+):',l).group(1),'port':port,'fix':'semanage-port',
           'fix_command':'semanage port -a -t http_port_t -p tcp %d'%port}""")
add(2, "audit.logのAVC拒否を読み解く",
    "httpdが新しいポートで起動できません。audit.logにAVC拒否があります。permissive=1の拒否(記録のみ)と、実際に止めた拒否(permissive=0)を区別して、restoreconかsemanageかを判断します。",
    g2, ["audit.logで実際に拒否したAVC(permissive=0)を特定する", "拒否の権限・型・ポートを記録し、対応するsemanageコマンドを書く"],
    ["{ name_bind } はポートへの待受権限、tcontextのunreserved_port_tはポートの型です。permissive=1の行は拒否ではなく記録だけです。",
     "ファイルの型の誤りは restorecon、ポートやパスに新しい規則が要るときは semanage です。", S2],
    "ファイルのラベル不一致ならrestorecon、ポートの型が未登録なら semanage port -a -t http_port_t -p tcp PORT です。audit2allowで無差別にルールを足すより、まず正しいラベルを与えます。permissive=1は拒否されていません。",
    TIP, S2, [EMPTY, S2.replace("http_port_t", "unreserved_port_t")])


# ---------------------------------------------------------------- 16-3 AppArmor
def g3(ctx):
    name = "agent" + hx(2)
    path = f"/srv/{name}/inbox/data-{hx(2)}.txt"
    profile = (f"#include <tunables/global>\n/usr/sbin/{name} flags=(complain) {{\n  #include <abstractions/base>\n"
               f"  /etc/{name}.conf r,\n  /var/log/{name}.log w,\n}}\n")
    ctx.data["rule"] = f"{path} r,"
    ctx.data["name"] = name
    log = (f'audit: type=1400 audit(1763686100.1:51): apparmor="ALLOWED" operation="open" profile="/usr/sbin/{name}" name="{path}" pid=4410 comm="{name}" requested_mask="r" denied_mask="r" fsuid=996 ouid=996\n'
           f'audit: type=1400 audit(1763686101.2:52): apparmor="ALLOWED" operation="open" profile="/usr/bin/other-tool" name="/tmp/other.txt" pid=4500 comm="other-tool" requested_mask="w" denied_mask="w" fsuid=0 ouid=0\n')
    files = {"aa-status.txt": f"2 profiles are in enforce mode.\n   /usr/bin/man\n   /usr/bin/other-tool-enforced\n1 profiles are in complain mode.\n   /usr/sbin/{name}\n",
             "apparmor.log": log, "work/agent.profile": profile}
    req = ("work/agent.profile を直す: complainで観測された、このプロファイルへの必要な許可を最小の1行(読み取りのみ)として追加し、"
           "complainを外してenforce(既定)にする。他の行は変えず、/** のような広いルールは足さない。他のプロファイルは対象外。\n")
    return files, {}, req


def c3(ctx, _):
    name = ctx.data["name"]
    t = ctx.need_file("work/agent.profile")
    ctx.require("complain" not in t, "プロファイルをenforceモード(complainを外す)にしてください。")
    lines = {l.strip() for l in t.splitlines() if l.strip()}
    want = {"#include <tunables/global>", f"/usr/sbin/{name} {{", "#include <abstractions/base>",
            f"/etc/{name}.conf r,", f"/var/log/{name}.log w,", ctx.data["rule"], "}"}
    ctx.require(lines == want, "既存ルールを保ち、ログが示した1ファイルへのr許可だけを追加してください。")


S3 = """python3 - <<'PYCODE'
import re
L=open('apparmor.log').read()
t=open('work/agent.profile').read()
name=re.search(r'^(/\\S+)',t.split('\\n',1)[1],re.M).group(1)
p=re.search(r'profile="'+re.escape(name)+r'" name="([^"]+)"',L).group(1)
t=t.replace(' flags=(complain)','').rstrip().rstrip('}')+'  %s r,\\n}\\n'%p
open('work/agent.profile','w').write(t)
PYCODE
"""
add(3, "AppArmorのcomplainとenforce",
    "新しいAppArmorプロファイルはcomplain(学習)モードで運用中です。ログの内容から必要な許可を1行だけ足し、enforceへ切り替える準備をします。",
    g3, ["AppArmorのログからこのプロファイルのALLOWED記録を探す", "対象プロファイルの控えへ必要最小の許可を足し、complainを外す"],
    ["complainは違反を許可して記録するだけです。enforceは拒否します。別プロファイルの行は無関係です。",
     "ログのprofile=が一致する行のname=とrequested_mask=を読み、'  パス r,' を加え、flags=(complain)を消します。", S3],
    "complainのログは『enforceにしたら拒否される操作』の一覧です。必要なものだけ許可し、aa-enforce(実機)で切替え、aa-statusで確認します。/** rwのような広い許可は保護の意味を失います。",
    TIP, S3, ["sed -i 's/ flags=(complain)//' work/agent.profile",
              S3.replace("%s r,", "/** rw,").replace("% p", "% '/'")], extra=c3, diag=False)


# ---------------------------------------------------------------- 16-4 ACL
def g4(ctx):
    proj, user, grp, dgrp = "proj" + hx(2), secrets.choice(["alice", "bob", "carol", "dave"]), "dev" + hx(1), "ops" + hx(1)
    d = f"/srv/share/{proj}"
    ctx.data["dir"] = d
    txt = (f"# file: {d[1:]}\n# owner: root\n# group: root\nuser::rwx\nuser:{user}:rwx\t\t#effective:r--\n"
           f"group::r-x\t\t#effective:r--\ngroup:{grp}:rwx\t\t#effective:r--\nmask::r--\nother::---\n"
           f"default:user::rwx\ndefault:group::r-x\ndefault:group:{dgrp}:rwx\ndefault:mask::rwx\ndefault:other::---\n")
    exp = {"user": user, "effective": "r--", "cause": "mask", "new_file_group": dgrp}
    req = (f"diagnosis.json: user(名前付きACLがrwxなのに書けない利用者), effective(その実効権限), causeはmask/ownerから選ぶ、"
           f"new_file_group(新規ファイルへdefault ACLで継承される名前付きグループ)、fix_command(maskだけを直す1行 setfacl。対象は {d})。\n")
    return {"getfacl.txt": txt}, exp, req


def c4(ctx, data):
    ctx.require(norm(data.get("fix_command")).replace("mask::", "m::") == f"setfacl -m m::rwx {ctx.data['dir']}",
                "fix_command は mask を rwx にする setfacl コマンド1行にしてください。")


S4 = PY("""t=open('getfacl.txt').read()
d='/'+re.search(r'# file: (\\S+)',t).group(1)
u=re.search(r'^user:(\\w+):\\w+\\s+#effective:(\\S+)',t,re.M)
r={'user':u.group(1),'effective':u.group(2),'cause':'mask','new_file_group':re.search(r'^default:group:(\\w+):',t,re.M).group(1),
   'fix_command':'setfacl -m m::rwx '+d}""")
add(4, "ACLのmaskとdefault ACL",
    "ユーザーにrwxのACLを付けたのに書き込めません。getfacl出力の #effective とmaskに注目します。新規ファイルが共有グループに継承される仕組み(default ACL)も確認します。",
    g4, ["ACLの採取記録の #effective と mask:: を読む", "実効権限・原因・継承グループ・修復コマンドをdiagnosis.jsonに記録する"],
    ["名前付きユーザー/グループとグループ所有者の実効権限は『指定権限 AND mask』です。",
     "default: 行は、そのディレクトリ内で新規作成されるものが継承するACLです。", S4],
    "maskは名前付きエントリの上限です。chmod g=... でも変わるため、ACLを付けた後にmaskがr--になる事故が起きます。setfacl -m m::rwx で直し、継承は setfacl -d -m で設定したdefault ACLが担います。",
    TIP, S4, [EMPTY, S4.replace("m::rwx", "u:x:rwx")], extra=c4)


# ---------------------------------------------------------------- 16-5 chattr
def g5(ctx):
    a, lg = "app" + hx(2), "log" + hx(2)
    imm, apo, lic = f"/srv/{a}/config.yml", f"/var/log/{lg}/audit.log", f"/srv/{a}/license.key"
    ls = (f"----i---------e------- {imm}\n-----a---------e------- {apo}\n--------------e------- {lic}\n")
    err = (f"$ rm {imm}\nrm: cannot remove '{imm}': Operation not permitted   (running as root)\n"
           f"$ truncate -s0 {apo}\ntruncate: failed to truncate '{apo}': Operation not permitted\n$ echo ok >> {apo}\n(ok)\n")
    exp = {"immutable_file": imm, "append_only_file": apo, "unlock_command": f"chattr -i {imm}",
           "protect_command": f"chattr +i {lic}", "root_bypasses_attributes": False}
    req = ("diagnosis.json: immutable_file(iで保護), append_only_file(aで保護), unlock_command(設定を更新したい時に外す1行), "
           "protect_command(license.keyを削除・変更不可にする1行), root_bypasses_attributes(true/false)。コマンドは半角スペース区切り。\n")
    return {"lsattr.txt": ls, "errors.txt": err}, exp, req


S5 = PY("""ls=[l.split() for l in open('lsattr.txt')]
imm=[x[1] for x in ls if 'i' in x[0]][0]
apo=[x[1] for x in ls if 'a' in x[0]][0]
lic=[x[1] for x in ls if not set('ia')&set(x[0])][0]
r={'immutable_file':imm,'append_only_file':apo,'unlock_command':'chattr -i '+imm,'protect_command':'chattr +i '+lic,'root_bypasses_attributes':False}""")
add(5, "chattr +i と +a の属性を読む",
    "rootで削除しても『Operation not permitted』になるファイルがあります。lsattrの属性を読み、不変(i)と追記専用(a)を区別します。",
    g5, ["ファイル属性の採取記録から i と a の属性を持つファイルを区別する", "解除と保護のコマンドを記録する"],
    ["lsattrの先頭の属性欄に i や a が出ます。i は変更・削除・名前変更が不可、a は追記のみ可能です。",
     "設定の更新前に chattr -i、機密ファイルの保護は chattr +i。属性はrootでも先に外さないと変更できません。", S5],
    "iは内容・削除・リンクを禁じ、aは追記のみを許します。ログの改ざん防止にaが使われます。rootも属性を外すまで変更できませんが、外せる(CAP_LINUX_IMMUTABLE)ため万能ではありません。ext4/xfsなど対応FSが前提です。",
    TIP, S5, [EMPTY, S5.replace("-i ", "+i ", 1)])


# ---------------------------------------------------------------- 16-6 special bits
def g6(ctx):
    rg, sg = "editor-" + hx(2), "scan-" + hx(2)
    ctx.data.update(rg=rg, sg=sg)
    ctx.write("work/audit/bin/passwd-lite", "#!/bin/sh\n", mode=0o4755)
    ctx.write(f"work/audit/bin/{rg}", "#!/bin/sh\n", mode=0o4755)
    ctx.write(f"work/audit/bin/{sg}", "#!/bin/sh\n", mode=0o2755)
    ctx.write("work/audit/bin/plain-tool", "#!/bin/sh\n", mode=0o755)
    ctx.mkdir("work/share/drop")
    os.chmod(ctx.p("work/share/drop"), 0o777)
    files = {"baseline.txt": "approved setuid/setgid: work/audit/bin/passwd-lite\n"}
    req = ("baseline.txtに無い setuid/setgid ファイルから特別ビットだけを外す(実行権 755 は残す)。承認済みのものは変更しない。"
           "全員が書ける共有 work/share/drop は、他人のファイルを消せないよう sticky bit を付けて 1777 にする。\n")
    return files, {}, req


def c6(ctx, _):
    m = lambda p: stat.S_IMODE(os.lstat(ctx.p(p)).st_mode)
    ctx.require(m("work/audit/bin/passwd-lite") == 0o4755, "承認済みの passwd-lite の setuid は残してください。")
    for n in (ctx.data["rg"], ctx.data["sg"]):
        ctx.require(m(f"work/audit/bin/{n}") == 0o755, f"{n} は特別ビットのみ外し 755 にしてください。")
    ctx.require(m("work/audit/bin/plain-tool") == 0o755, "無関係のファイルは変更しないでください。")
    ctx.require(m("work/share/drop") == 0o1777, "共有ディレクトリは sticky bit 付きの 1777 にしてください。")


S6 = ("find work/audit/bin -perm /6000 ! -name passwd-lite -exec chmod u-s,g-s {} +\nchmod 1777 work/share/drop\n")
add(6, "setuid・setgid・stickyの監査",
    "監査で find -perm /6000 を実行します。承認一覧にないsetuid/setgidを除去し、共有ディレクトリにはsticky bitが必要かを確認します。",
    g6, ["find -perm /6000 で特別ビット付きを洗い出し、承認一覧と照合する", "未承認のsetuid/setgidを外し、共有ディレクトリにsticky bitを付ける"],
    ["find work/audit -perm /6000 -ls で一覧します。承認済みまで外すと正規の機能が壊れます。",
     "chmod u-s,g-s は実行権を残して特別ビットだけを外します。chmod +t または 1777 でsticky。", S6],
    "setuid/setgidは実行者に所有者/グループの権限を与えるため、未承認の存在は権限昇格の足場です。stickyはディレクトリで『自分のファイルだけ削除可』にします(/tmpが1777)。chmod -R で全部外すと正規のpasswd等が壊れます。",
    TIP, S6, ["find work/audit -perm /6000 -exec chmod u-s,g-s {} +\nchmod 1777 work/share/drop",
              "chmod 777 work/share/drop\n" + S6.splitlines()[0]], extra=c6, diag=False)


# ---------------------------------------------------------------- 16-7 capabilities
def g7(ctx):
    nm, bad = "portsvc-" + hx(2), "helper-" + hx(2)
    gc = f"/usr/local/bin/pingtool cap_net_raw=ep\n/usr/local/bin/{bad} cap_sys_admin=ep\n"
    txt = f"service: /usr/local/bin/{nm}\nrequirement: TCP 443 を非rootで待ち受ける(getcapに現在の設定なし)\ncurrent: -rwsr-xr-x root root (setuid root)\n"
    ctx.data["bin"] = f"/usr/local/bin/{nm}"
    exp = {"needed_capability": "cap_net_bind_service", "excessive_binary": f"/usr/local/bin/{bad}",
           "remove_command": f"setcap -r /usr/local/bin/{bad}", "avoid": "setuid-root"}
    req = ("diagnosis.json: needed_capability(443待受に必要な最小のもの), excessive_binary(過剰な特権をもつ記録上のファイル), "
           "remove_command(それのcapabilityを全部外す1行), avoid(setuid-rootかchmod-777)。さらに setcap_command(サービスへ最小権限を付ける1行 ep)。\n")
    return {"getcap.txt": gc, "service.txt": txt}, exp, req


def c7(ctx, data):
    c = norm(data.get("setcap_command")).replace("=+", "+").replace("=ep", "+ep")
    ctx.require(c == f"setcap cap_net_bind_service+ep {ctx.data['bin']}", "setcap_command で最小のcapabilityだけをサービスのバイナリへ付けてください。")


S7 = PY("""g=open('getcap.txt').read(); s=open('service.txt').read()
b=re.search(r'service: (\\S+)',s).group(1)
x=[l.split()[0] for l in g.splitlines() if 'cap_sys_admin' in l][0]
r={'needed_capability':'cap_net_bind_service','excessive_binary':x,'remove_command':'setcap -r '+x,'avoid':'setuid-root',
   'setcap_command':'setcap cap_net_bind_service=+ep '+b}""")
add(7, "capabilityで最小権限にする",
    "サービスは1024未満のポートを待ち受けたいだけなのに、setuid rootで運用されています。getcapの記録を調べ、必要なcapabilityだけにします。",
    g7, ["サービス仕様とcapabilityの採取記録を読み、必要なcapabilityと過剰なものを特定する", "setcap/付与・削除コマンドを記録する"],
    ["1024未満へのbindは CAP_NET_BIND_SERVICE です。CAP_SYS_ADMINは『ほぼroot』と呼ばれる強力な権限です。",
     "付与は setcap cap_net_bind_service=+ep FILE、一覧は getcap、全削除は setcap -r です。", S7],
    "setuid rootは全権限を与えます。file capabilityなら必要な1権限だけに絞れます。cap_sys_admin=ep の付いたバイナリは実質root相当なので外して見直します。変更後は getcap -r で確認します。",
    TIP, S7, [EMPTY, S7.replace("cap_net_bind_service=+ep", "cap_sys_admin=+ep")], extra=c7)


# ---------------------------------------------------------------- 16-8 limits
def g8(ctx):
    user, v = "svc" + hx(2), secrets.choice([8192, 16384, 32768, 65536])
    ctx.data.update(user=user, v=v)
    files = {"proc-limits.txt": f"# cat /proc/<pid>/limits  (user {user}, systemd service)\nMax open files            1024                 524288               files\napp log: accept: Too many open files\n",
             "work/limits.conf": f"* soft nofile 1024\n* hard nofile 524288\nbatch soft nofile 512\n",
             "work/app.service": f"[Unit]\nDescription=App {user}\n\n[Service]\nUser={user}\nExecStart=/usr/local/bin/app\n\n[Install]\nWantedBy=multi-user.target\n"}
    req = f"対象ユーザー: {user}\n必要なファイル記述子の上限: {v}\nwork/limits.conf にこのユーザーの soft/hard nofile を追加し、work/app.service の [Service] に LimitNOFILE を設定する。他の行は変えない。\n"
    return files, {}, req


def c8(ctx, _):
    user, v = ctx.data["user"], ctx.data["v"]
    lim = ctx.need_file("work/limits.conf").splitlines()
    ctx.require("* soft nofile 1024" in lim and "* hard nofile 524288" in lim and "batch soft nofile 512" in lim, "既存のlimits.confの行は残してください。")
    mine = [l.split() for l in lim if l.split()[:1] == [user]]
    ctx.require(sorted((x[1], x[2], x[3]) for x in mine) == [("hard", "nofile", str(v)), ("soft", "nofile", str(v))],
                f"{user} の soft/hard nofile を {v} にしてください。")
    svc = ctx.need_file("work/app.service")
    m = re.search(r"\[Service\]\n(.*?)(?:\n\[|\Z)", svc, re.S)
    ctx.require(m and f"LimitNOFILE={v}" in m.group(1).splitlines(), "[Service] セクションに LimitNOFILE を設定してください。")
    ctx.require(f"ExecStart=/usr/local/bin/app" in svc and f"User={user}" in svc, "unitの既存設定は残してください。")


S8 = """user=$(sed -n 's/^対象ユーザー: //p' requirements.txt); v=$(sed -n 's/^必要なファイル記述子の上限: //p' requirements.txt)
printf '%s soft nofile %s\\n%s hard nofile %s\\n' "$user" "$v" "$user" "$v" >> work/limits.conf
sed -i "/^\\[Service\\]/a LimitNOFILE=$v" work/app.service
"""
add(8, "ulimit・limits.conf・LimitNOFILE",
    "サービスが『Too many open files』で落ちます。/proc/<pid>/limitsの記録では上限が1024です。PAM経由のlimits.confと、systemdサービスが使うLimitNOFILEの違いを踏まえて直します。",
    g8, ["要件書の値を読む", "limits.confに対象ユーザーのsoft/hardを追加し、unitにLimitNOFILEを足す"],
    ["limits.confはPAMのログインセッションに効きます。systemdのサービスは unit の LimitNOFILE が効きます。",
     "softは実際の上限、hardはそれ以上に上げられない天井です。soft<=hard にします。", S8],
    "ulimit -n(soft)は現プロセスの上限です。ログイン経由はlimits.conf、systemdサービスはLimitNOFILE(systemctl daemon-reload後に再起動)で設定します。無制限(infinity)はfd枯渇や暴走を許すので必要な値に留めます。",
    TIP, S8, ["printf '* soft nofile 99999\\n' >> work/limits.conf", S8.splitlines()[0] + "\n" + S8.splitlines()[1] + "\nprintf '%s soft nofile %s\\n' \"$user\" \"$v\" >> work/limits.conf\n"],
    extra=c8, diag=False)


# ---------------------------------------------------------------- 16-9 cgroup / nice
def g9(ctx):
    quota, mib, oom, thr = secrets.choice([10000, 20000, 25000, 50000]), secrets.choice([256, 512, 1024]), secrets.randbelow(5) + 1, secrets.randbelow(4000) + 100
    pid, web = secrets.randbelow(9000) + 2000, secrets.randbelow(900) + 1000
    nm = "backup-" + hx(2)
    d = "recorded/cgroup/batch.slice/"
    files = {d + "cpu.max": f"{quota} 100000\n", d + "memory.max": f"{mib * 1048576}\n", d + "memory.high": "max\n",
             d + "memory.current": f"{mib * 1048576 - 4096}\n", d + "memory.events": f"low 0\nhigh 0\nmax 12\noom {oom}\noom_kill {oom}\n",
             d + "cpu.stat": f"usage_usec 90000000\nnr_periods 5000\nnr_throttled {thr}\nthrottled_usec 800000000\n",
             "ps.txt": f"  PID  NI %CPU COMMAND\n {web}   0  2.0 web-api\n {pid}   0 93.5 {nm}\n",
             "ionice.txt": f"{pid}: best-effort: prio 4\n{web}: best-effort: prio 4\n"}
    exp = {"cpu_limit_percent": quota // 1000, "memory_max_mib": mib, "oom_kills": oom, "cpu_throttled": True,
           "renice_command": f"renice -n 10 -p {pid}", "ionice_command": f"ionice -c 3 -p {pid}"}
    req = ("diagnosis.json: cpu_limit_percent(cpu.maxの 上限/周期 を%に), memory_max_mib, oom_kills(memory.events), "
           "cpu_throttled(true/false), 夜間バッチ(COMMANDがbackup-*)の優先度を下げる renice_command(nice値10) と ionice_command(idleクラス3)。\n")
    return files, exp, req


S9 = PY("""d='recorded/cgroup/batch.slice/'
q,p=open(d+'cpu.max').read().split()
ev=dict(l.split() for l in open(d+'memory.events'))
st=dict(l.split() for l in open(d+'cpu.stat'))
pid=[l.split()[0] for l in open('ps.txt') if 'backup-' in l][0]
r={'cpu_limit_percent':int(q)*100//int(p),'memory_max_mib':int(open(d+'memory.max').read())//1048576,'oom_kills':int(ev['oom_kill']),
   'cpu_throttled':int(st['nr_throttled'])>0,'renice_command':'renice -n 10 -p '+pid,'ionice_command':'ionice -c 3 -p '+pid}""")
add(9, "nice・renice・ioniceとcgroup v2の制限",
    "夜間バッチがWeb APIを遅くします。cgroup v2の制限ファイルの記録(cpu.max/memory.max/memory.events/cpu.stat)を読み、優先度を下げる準備をします。",
    g9, ["cpu.max・memory.max・memory.events・cpu.statを読み解く", "バッチのPIDに対するrenice/ioniceコマンドを記録する"],
    ["cpu.maxは『quota period』(マイクロ秒)で、quota/period が使えるCPU割合です。memory.eventsのoom_killはOOMで止めた回数です。",
     "niceは大きいほど低優先、ionice -c 3 はidleクラス。nr_throttledが増えると制限に当たっています。", S9],
    "cgroup v2はファイルで資源を制限します(cpu.max, memory.max/high)。niceはCPUスケジューラの重みで、ioniceはI/O優先度です。制限による待ち(throttled)とOOM killを区別し、制限値の根拠を確認してから変更します。",
    TIP, S9, [EMPTY, S9.replace("-n 10", "-n -20")])


# ---------------------------------------------------------------- 16-10 sudoers
def g10(ctx):
    unit = "dojo-" + hx(2)
    ctx.data["unit"] = unit
    files = {"work/sudoers.d/deploy": ("deploy ALL=(ALL) NOPASSWD: ALL\n", 0o640),
             "work/sudoers.d/ops": ("# ops is managed by another team\n%ops ALL=(root) /usr/bin/journalctl\n", 0o440)}
    req = (f"deployユーザーが許される作業は『root権限で systemctl restart {unit}.service のみ』。パスワード不要(NOPASSWD)を維持し、"
           "シェルや任意コマンドは許さない。work/sudoers.d/deploy を最小権限へ書き換え、権限モードを 0440 にする。opsの設定は触らない。\n")
    return files, {}, req


def c10(ctx, _):
    unit = ctx.data["unit"]
    t = ctx.need_file("work/sudoers.d/deploy")
    rules = [l.strip() for l in t.splitlines() if l.strip() and not l.strip().startswith("#")]
    ctx.require(len(rules) == 1 and re.fullmatch(rf"deploy\s+ALL=\(root\)\s+NOPASSWD:\s*/usr/bin/systemctl restart {unit}\.service", rules[0]),
                "ルールは deploy 1行だけで、許可コマンドを該当unitの restart に限定してください(ALLや*は不可)。")
    ctx.require(ctx.mode("work/sudoers.d/deploy") == 0o440, "sudoersのドロップインは 0440 にしてください。")
    ctx.require(ctx.need_file("work/sudoers.d/ops").startswith("# ops is managed"), "opsの設定は変更しないでください。")


S10 = """unit=$(grep -o 'dojo-[0-9a-f]*' requirements.txt | head -1)
echo "deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart $unit.service" > work/sudoers.d/deploy
chmod 0440 work/sudoers.d/deploy
"""
add(10, "sudoersを最小権限にする",
    "deployユーザーにNOPASSWD: ALLが付いています。作業が必要なのは1つのサービスの再起動だけです。sudoersのドロップインを最小権限へ直します。",
    g10, ["要件のunit名を確認する", "deployのルールを該当 systemctl restart だけに限定し、0440にする"],
    ["sudoersは『誰が ホスト=(実行ユーザー) コマンド』です。ALLやワイルドカードは過剰な許可になります。",
     "コマンドは絶対パスで引数まで指定します。ドロップインは0440が慣例で、実機では visudo -cf で構文確認します。", S10],
    "コマンドと引数を固定すれば、任意のsystemctl操作やシェル起動を防げます。ワイルドカード(restart *)は別unitや引数を許すので避けます。構文ミスは全sudoを壊すため、visudo -cfで検証し0440で配置します。",
    TIP, S10, ["echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl *' > work/sudoers.d/deploy\nchmod 0440 work/sudoers.d/deploy",
               S10.splitlines()[0] + "\n" + S10.splitlines()[1] + "\n"], extra=c10, diag=False)


# ---------------------------------------------------------------- 16-11 PAM / chage
def g11(ctx):
    deny, ul, ml, mx = secrets.choice([3, 4, 5]), secrets.choice([600, 900, 1800]), secrets.choice([12, 14, 16]), secrets.choice([60, 90, 120])
    user = "user" + hx(2)
    ctx.data.update(deny=deny, ul=ul, ml=ml, mx=mx, user=user)
    files = {"work/faillock.conf": "deny = 10\nfail_interval = 900\nunlock_time = 60\n",
             "work/pwquality.conf": "minlen = 6\ndcredit = -1\nretry = 3\n",
             "system-auth.txt": "auth required pam_faillock.so preauth silent\nauth sufficient pam_unix.so\nauth [default=die] pam_faillock.so authfail\npassword requisite pam_pwquality.so retry=3\n",
             "chage-list.txt": f"$ chage -l {user}\nMinimum number of days between password change\t: 0\nMaximum number of days between password change\t: 99999\nNumber of days of warning before password expires\t: 7\n"}
    req = (f"方針: {deny}回失敗でロック(deny={deny})、解除まで {ul} 秒、パスワード最小長 {ml}。work/faillock.conf と work/pwquality.conf のその3項目だけを変更。"
           f"さらに {user} のパスワードを最大{mx}日・最短1日・期限7日前に警告に設定する chage コマンド(1行)を diagnosis.json の chage_command に記録する(オプション順は問わない)。\n")
    return files, {}, req


def c11(ctx, _):
    d = ctx.data

    def kv(rel):
        return {a.strip(): b.strip() for a, b in (l.split("=", 1) for l in ctx.need_file(rel).splitlines() if "=" in l)}
    f = kv("work/faillock.conf")
    ctx.require(f == {"deny": str(d["deny"]), "fail_interval": "900", "unlock_time": str(d["ul"])}, "faillock.confのdenyとunlock_timeだけを方針値にしてください。")
    p = kv("work/pwquality.conf")
    ctx.require(p == {"minlen": str(d["ml"]), "dcredit": "-1", "retry": "3"}, "pwquality.confのminlenだけを方針値にしてください。")
    try:
        cmd = json.loads(ctx.need_file("diagnosis.json")).get("chage_command", "")
    except ValueError:
        ctx.fail("diagnosis.json をJSONで保存してください。")
    t = norm(cmd).split()
    ctx.require(len(t) == 8 and t[0] == "chage" and t[-1] == d["user"], "chage_command は chage -M .. -m .. -W .. ユーザー の形で書いてください。")
    ctx.require(dict(zip(t[1:7:2], t[2:7:2])) == {"-M": str(d["mx"]), "-m": "1", "-W": "7"}, "chageの最大日数・最短日数・警告日数が方針と一致しません。")


S11 = """d=$(grep -o 'deny=[0-9]*' requirements.txt | cut -d= -f2); u=$(grep -o '解除まで [0-9]*' requirements.txt | grep -o '[0-9]*$'); m=$(grep -o '最小長 [0-9]*' requirements.txt | grep -o '[0-9]*$')
x=$(grep -o '最大[0-9]*日' requirements.txt | grep -o '[0-9]*'); usr=$(grep -o 'user[0-9a-f]*' requirements.txt | head -1)
sed -i "s/^deny = .*/deny = $d/; s/^unlock_time = .*/unlock_time = $u/" work/faillock.conf
sed -i "s/^minlen = .*/minlen = $m/" work/pwquality.conf
echo "{\\"case\\": \\"$(python3 -c "import json;print(json.load(open('case.json'))['case'])")\\", \\"chage_command\\": \\"chage -M $x -m 1 -W 7 $usr\\"}" > diagnosis.json
"""
add(11, "PAMのfaillock・pwqualityとchage",
    "ブルートフォース対策とパスワード方針を整えます。pam_faillock(失敗回数でロック)とpam_pwquality(強度)の設定を直し、chageでパスワード期限を設けます。",
    g11, ["faillock.confとpwquality.confを方針値に直す(他は変更しない)", "パスワード期限の採取記録を参考に、期限設定のchageコマンドをdiagnosis.jsonへ記録する"],
    ["faillockは deny(失敗回数)・unlock_time(秒)、pwqualityは minlen で強度を決めます。PAMの順序(preauth→unix→authfail)は壊さないこと。",
     "chage -M 最大日数 -m 最短日数 -W 警告日数 ユーザー。一覧は chage -l です。", S11],
    "faillockは連続失敗でアカウントを一時ロックし、pwqualityは弱いパスワードを拒否します。chage -Mで定期変更を強制します。実機ではPAMの誤設定でログインできなくなるため、別のrootセッションを開いたまま確認します。",
    TIP, S11, [EMPTY, "sed -i 's/^deny = .*/deny = 0/' work/faillock.conf"], extra=c11, diag=False)


# ---------------------------------------------------------------- 16-12 fail2ban
def g12(ctx):
    admin = f"192.0.2.{secrets.randbelow(200) + 20}"
    mr, bt = secrets.choice([3, 4, 5]), secrets.choice(["1h", "2h", "12h"])
    ctx.data.update(admin=admin, mr=str(mr), bt=bt)
    files = {"work/jail.local": "[DEFAULT]\nbantime = 10m\n\n[sshd]\nenabled = false\nport = ssh\nmaxretry = 20\nfindtime = 1d\n",
             "fail2ban.log": f"2026-11-21 01:00:01 fail2ban.filter [1]: INFO [sshd] Found 198.51.100.7 - failed password\n2026-11-21 01:00:09 fail2ban.filter [1]: INFO [sshd] Found {admin} - failed password (admin typo)\n"}
    req = (f"work/jail.local の [sshd] を方針に合わせる: 有効化(enabled = true)、maxretry = {mr}、findtime = 10m、bantime = {bt}、"
           f"管理者の接続元 {admin} と 127.0.0.1/8 を ignoreip に入れ誤BANを防ぐ。portと[DEFAULT]は変更しない。\n")
    return files, {}, req


def c12(ctx, _):
    d = ctx.data
    cp = configparser.ConfigParser(strict=False, inline_comment_prefixes=("#",))
    try:
        cp.read_string(ctx.need_file("work/jail.local"))
    except configparser.Error:
        ctx.fail("jail.local がINIとして読めません。")
    ctx.require(cp.has_section("sshd") and cp.get("sshd", "port", fallback="") == "ssh", "[sshd] とその port = ssh を保ってください。")
    s = cp["sshd"]
    ctx.require(s.get("enabled", "").lower() == "true", "[sshd] を enabled = true にしてください。")
    ctx.require(s.get("maxretry") == d["mr"] and s.get("findtime") == "10m" and s.get("bantime") == d["bt"], "maxretry/findtime/bantime が方針値になっていません。")
    ign = s.get("ignoreip", "").replace(",", " ").split()
    ctx.require(d["admin"] in ign and "127.0.0.1/8" in ign, "ignoreip に管理者IPと 127.0.0.1/8 を入れてください。")
    ctx.require(all("/0" not in x for x in ign), "ignoreip に全体を指す範囲を入れてはいけません。")
    ctx.require(cp.get("DEFAULT", "bantime") == "10m", "[DEFAULT] は変更しないでください。")


S12 = """mr=$(grep -o 'maxretry = [0-9]*' requirements.txt | grep -o '[0-9]*$'); bt=$(grep -o 'bantime = [0-9a-z]*' requirements.txt | tail -1 | sed 's/.*= //')
ip=$(grep -o '192\\.0\\.2\\.[0-9]*' requirements.txt | head -1)
sed -i "s/^enabled = .*/enabled = true/; s/^maxretry = .*/maxretry = $mr/; s/^findtime = .*/findtime = 10m/" work/jail.local
printf 'bantime = %s\\nignoreip = 127.0.0.1/8 %s\\n' "$bt" "$ip" >> work/jail.local
"""
add(12, "fail2banのjail設定",
    "sshdへの総当たりが続いています。jail.localの[sshd]を有効にし、現実的な回数と時間を設定しつつ、管理者自身が誤BANされないようignoreipを設定します。",
    g12, ["fail2banのログと要件を読む", "[sshd]のenabled・maxretry・findtime・bantime・ignoreipを設定する"],
    ["maxretryはfindtime内の失敗許容回数、bantimeは遮断時間です。管理者IPは ignoreip に入れます。",
     "jail.localはINI形式です。[DEFAULT]や port は変更しないで [sshd] だけを直します。", S12],
    "fail2banはログから失敗を数えfirewallで一時遮断します。ignoreipが無いと打ち間違いで自分が締め出されます。ただし0.0.0.0/0のような広いignoreipは保護を無効化します。設定後は fail2ban-client status sshd で確認します。",
    TIP, S12, ["sed -i 's/^enabled = .*/enabled = true/' work/jail.local",
               S12.replace("127.0.0.1/8 %s", "0.0.0.0/0 %s")], extra=c12, diag=False)
