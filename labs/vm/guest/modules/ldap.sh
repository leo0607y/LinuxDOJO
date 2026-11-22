#!/bin/bash
# title: 専用slapdでDIT構築・ldapsearch/ldapmodify・ACLでuserPasswordを保護する
# roles: app
# Guest-only. Dedicated slapd instance on ldap://127.0.0.1:3890 plus its own ldapi socket, with its own
# slapd.d (cn=config) directory, its own MDB directory and its own user (dojo-ldap). The system slapd,
# distro slapd.d directory, port 389, nsswitch, PAM and sssd are never touched.
# Requires: slapd ldap-utils (not in the base image; the learner installs them).
# AppArmor: the Ubuntu slapd profile only allows /var/lib/ldap/**, /run/slapd/** and /etc/ldap/**,
# so every dedicated path lives under /var/lib/ldap/dojo and /run/slapd/dojo.

_ldap_paths() {
    [[ ${LAB_ID:-} == ldap && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/ldap ]] || { echo 'ldap: unexpected lab context' >&2; return 1; }
    LDAP_UNIT=/etc/systemd/system/dojo-ldap.service
    LDAP_HOME=/var/lib/ldap/dojo
    LDAP_CONF=$LDAP_HOME/config
    LDAP_DB=$LDAP_HOME/db
    LDAP_RUN=/run/slapd/dojo
    LDAP_USER=dojo-ldap
    LDAP_URI=ldap://127.0.0.1:3890
    LDAP_SOCK=ldapi://%2Frun%2Fslapd%2Fdojo%2Fldapi
    LDAP_BASE=dc=dojo,dc=test
    LDAP_ADMIN=cn=admin,dc=dojo,dc=test
    local p
    for p in "$LDAP_UNIT" "$LDAP_HOME" "$LDAP_CONF" "$LDAP_DB" "$LDAP_RUN"; do
        [[ ! -L $p ]] || { echo 'ldap: unexpected lab context' >&2; return 1; }
    done
}

_ldap_need_pkgs() {
    local t missing=0
    for t in slapadd slapcat slaptest slappasswd ldapsearch ldapmodify ldapadd ldappasswd ldapwhoami ss runuser; do
        command -v "$t" >/dev/null 2>&1 || missing=1
    done
    [[ -x /usr/sbin/slapd ]] || missing=1
    if (( missing )); then
        echo 'slapd / ldap-utils が未導入です。何も書き込まずに終了します。次を実行してから setup をやり直してください。' >&2
        echo '  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y slapd ldap-utils' >&2
        echo '  (debconfを対話させないための指定。標準のslapdが389番で起動しても、この実習は触りません)' >&2
        return 1
    fi
}

_ldap_owned() { [[ -f $LAB_STATE/owns-ldap && -f $LDAP_HOME/.linuxdojo-ldap ]]; }

_ldap_admin() { env LDAPNOINIT=1 timeout 15 ldapsearch -x -LLL -o ldif-wrap=no -H "$LDAP_URI" -D "$LDAP_ADMIN" -y "$LAB_STATE/admin.pw" "$@"; }

_ldap_as() { # user-name pwfile ldapsearch-args...
    local dn=$1 pw=$2; shift 2
    env LDAPNOINIT=1 timeout 15 ldapsearch -x -LLL -o ldif-wrap=no -H "$LDAP_URI" -D "$dn" -y "$pw" "$@"
}

_ldap_anon() { env LDAPNOINIT=1 timeout 15 ldapsearch -x -LLL -o ldif-wrap=no -H "$LDAP_URI" "$@"; }

_ldap_external() { env LDAPNOINIT=1 timeout 15 ldapsearch -Q -LLL -Y EXTERNAL -H "$LDAP_SOCK" "$@"; }

_ldap_whoami() { # dn pwfile-or-@literal
    local dn=$1 pw=$2
    if [[ $pw == @* ]]; then
        env LDAPNOINIT=1 timeout 15 ldapwhoami -x -H "$LDAP_URI" -D "$dn" -w "${pw#@}"
    else
        env LDAPNOINIT=1 timeout 15 ldapwhoami -x -H "$LDAP_URI" -D "$dn" -y "$pw"
    fi
}

# Validate a full-subtree LDIF dump (admin view) against the expected DIT. No lab paths needed.
_ldap_dit_validate() {
    python3 - "$1" <<'PY'
import sys
entries = {}
cur = None
for raw in open(sys.argv[1], encoding='utf-8', errors='replace').read().split('\n'):
    if raw.startswith(' ') and cur is not None:
        cur[-1] = (cur[-1][0], cur[-1][1] + raw[1:])
        continue
    if not raw.strip():
        cur = None
        continue
    key, _, val = raw.partition(':')
    val = val.lstrip(':').strip() if val.startswith(':') else val.strip()
    if key.lower() == 'dn':
        dn = ','.join(p.strip() for p in val.lower().split(','))
        cur = entries.setdefault(dn, [])
    elif cur is not None:
        cur.append((key.lower(), val))
def fail(msg):
    print(msg)
    sys.exit(1)
base = 'dc=dojo,dc=test'
users = ['alice', 'bob', 'carol']
expected = {base, 'ou=people,' + base, 'ou=groups,' + base, 'cn=staff,ou=groups,' + base}
expected |= {'uid=%s,ou=people,%s' % (u, base) for u in users}
if set(entries) != expected:
    extra = sorted(set(entries) - expected); lack = sorted(expected - set(entries))
    fail('DITのエントリが想定と違います。不足=%s 余分=%s' % (lack, extra))
def vals(dn, k): return [v for kk, v in entries[dn] if kk == k]
def ocs(dn): return {v.lower() for v in vals(dn, 'objectclass')}
if 'organization' not in ocs(base) or vals(base, 'dc') != ['dojo']:
    fail('dc=dojo,dc=test はorganization(+dcObject)でdc=dojoが必要です。')
for ou in ('people', 'groups'):
    if 'organizationalunit' not in ocs('ou=%s,%s' % (ou, base)):
        fail('ou=%s はorganizationalUnitが必要です。' % ou)
seen = set()
for u in users:
    dn = 'uid=%s,ou=people,%s' % (u, base)
    if 'posixaccount' not in ocs(dn):
        fail('%s にposixAccountがありません。' % dn)
    try:
        num = int(vals(dn, 'uidnumber')[0]); int(vals(dn, 'gidnumber')[0])
    except (IndexError, ValueError):
        fail('%s のuidNumber/gidNumberが数値ではありません。' % dn)
    if num < 1000 or num in seen:
        fail('%s のuidNumberは1000以上で重複不可です。' % dn)
    seen.add(num)
    if vals(dn, 'uid') != [u]:
        fail('%s のuid属性が不正です。' % dn)
    home = vals(dn, 'homedirectory')
    if not home or not home[0].startswith('/'):
        fail('%s のhomeDirectoryが絶対パスではありません。' % dn)
    if not vals(dn, 'loginshell') or not vals(dn, 'cn') or not vals(dn, 'sn'):
        fail('%s にloginShell/cn/snが必要です。' % dn)
g = 'cn=staff,ou=groups,' + base
if 'posixgroup' not in ocs(g):
    fail('cn=staffはposixGroupが必要です。')
try:
    int(vals(g, 'gidnumber')[0])
except (IndexError, ValueError):
    fail('cn=staffのgidNumberが数値ではありません。')
if sorted(vals(g, 'memberuid')) != sorted(users):
    fail('cn=staffのmemberUidはalice, bob, carolの3名である必要があります。')
PY
}

# Verify real LDAP behaviour. Prints a Japanese hint and returns 1 on the first failure.
_ldap_verify() {
    local dump="$LAB_STATE/dit.ldif" cnt a_dn b_dn msg rc
    systemctl is-active --quiet dojo-ldap.service || { echo 'dojo-ldap.service が動いていません。journalctl -u dojo-ldap.service を確認します。'; return 1; }
    local listen
    listen=$(ss -H -ltn 'sport = :3890') || return 1
    [[ $listen == *127.0.0.1:3890* && $listen != *0.0.0.0:3890* && $listen != *'*:3890'* && $listen != *'[::]:3890'* ]] \
        || { echo '3890番は127.0.0.1だけで待ち受ける必要があります。'; return 1; }
    [[ $(_ldap_external -b cn=config "(olcSuffix=$LDAP_BASE)" dn 2>/dev/null | grep -c '^dn:') == 1 ]] \
        || { echo '専用ソケット経由でdojoのDBを確認できません。'; return 1; }
    _ldap_whoami "$LDAP_ADMIN" "$LAB_STATE/admin.pw" >/dev/null 2>&1 \
        || { echo 'rootdn(cn=admin)でbindできません。olcRootPWを確認します。'; return 1; }
    _ldap_whoami "$LDAP_ADMIN" '@definitely-wrong' >/dev/null 2>&1 && rc=0 || rc=$?
    [[ $rc == 49 ]] || { echo "rootdnの誤パスワードがerr 49で拒否されません (rc=$rc)。"; return 1; }
    _ldap_admin -b "$LDAP_BASE" -s sub '*' > "$dump" 2>/dev/null || { echo 'DITを読み出せません。まずLDIFでツリーを作ります。'; return 1; }
    chmod 600 "$dump"
    msg=$(_ldap_dit_validate "$dump") || { echo "$msg"; return 1; }
    a_dn=uid=alice,ou=people,$LDAP_BASE
    b_dn=uid=bob,ou=people,$LDAP_BASE
    [[ $(grep -ci '^userPassword:' "$dump") == 3 ]] || { echo '3ユーザー全員にuserPasswordが必要です(ldappasswdなど)。'; return 1; }
    cnt=$(_ldap_anon -b "$LDAP_BASE" -s sub '(uid=*)' userPassword 2>/dev/null | grep -ci '^userPassword')
    [[ $cnt == 0 ]] || { echo '匿名bindでuserPasswordが読めます。ACLで塞ぎます。'; return 1; }
    _ldap_whoami "$a_dn" "$LAB_STATE/alice.pw" >/dev/null 2>&1 || { echo "aliceが $LAB_STATE/alice.pw のパスワードでbindできません。"; return 1; }
    _ldap_whoami "$a_dn" '@definitely-wrong' >/dev/null 2>&1 && rc=0 || rc=$?
    [[ $rc == 49 ]] || { echo "aliceの誤パスワードがerr 49で拒否されません (rc=$rc)。"; return 1; }
    [[ $(_ldap_as "$a_dn" "$LAB_STATE/alice.pw" -b "$a_dn" -s base uidNumber 2>/dev/null | grep -c '^uidNumber:') == 1 ]] \
        || { echo 'aliceが自分のエントリを読めません。'; return 1; }
    [[ $(_ldap_as "$a_dn" "$LAB_STATE/alice.pw" -b "$b_dn" -s base uidNumber 2>/dev/null | grep -c '^uidNumber:') == 1 ]] \
        || { echo 'ユーザーは他人のuidNumber等の公開属性は読める設計です(ACLを締めすぎです)。'; return 1; }
    [[ $(_ldap_as "$a_dn" "$LAB_STATE/alice.pw" -b "$b_dn" -s base userPassword 2>/dev/null | grep -ci '^userPassword') == 0 ]] \
        || { echo 'aliceがbobのuserPasswordを読めます。'; return 1; }
    # slapcat (offline reader) must agree with what the server returns.
    runuser -u "$LDAP_USER" -- slaptest -u -F "$LDAP_CONF" >/dev/null 2>&1 || { echo 'slaptest -u が失敗します。cn=configが壊れています。'; return 1; }
    runuser -u "$LDAP_USER" -- slapcat -F "$LDAP_CONF" -b "$LDAP_BASE" > "$LAB_STATE/slapcat.ldif" 2>/dev/null || { echo 'slapcatが失敗します。'; return 1; }
    chmod 600 "$LAB_STATE/slapcat.ldif"
    local norm='tr A-Z a-z | sed "s/, */,/g" | sort'
    diff -q <(grep -i '^dn:' "$LAB_STATE/slapcat.ldif" | eval "$norm") <(grep -i '^dn:' "$dump" | eval "$norm") >/dev/null \
        || { echo 'slapcatとldapsearchのエントリ一覧が一致しません。'; return 1; }
    [[ $(grep -ci '^dn:' "$LAB_STATE/slapcat.ldif") == 7 ]] || { echo 'slapcatのエントリ数が7ではありません。'; return 1; }
}

lab_setup() {
    _ldap_paths || return 1
    _ldap_need_pkgs || return 1
    [[ ! -e $LDAP_UNIT && ! -e $LDAP_HOME && ! -e $LDAP_RUN ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if getent passwd "$LDAP_USER" >/dev/null || getent group "$LDAP_USER" >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    if [[ -n $(ss -H -ltn 'sport = :3890') ]]; then echo '3890番は既に使用中です。'; return 1; fi
    local f
    for f in core cosine nis inetorgperson; do
        [[ -r /etc/ldap/schema/$f.ldif ]] || { echo "/etc/ldap/schema/$f.ldif がありません。"; return 1; }
    done
    useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$LDAP_USER" || return 1
    touch "$LAB_STATE/owns-ldap"
    [[ -d /var/lib/ldap ]] || install -d -m 0755 /var/lib/ldap
    install -d -o "$LDAP_USER" -g "$LDAP_USER" -m 0750 "$LDAP_HOME" "$LDAP_CONF" "$LDAP_DB"
    : > "$LDAP_HOME/.linuxdojo-ldap"
    umask 077
    printf '%s' "adm-$(cat /proc/sys/kernel/random/uuid)" > "$LAB_STATE/admin.pw"
    printf '%s' "alice-$(cat /proc/sys/kernel/random/uuid)" > "$LAB_STATE/alice.pw"
    local hash conf=$LDAP_HOME/conf.ldif
    hash=$(slappasswd -s "$(cat "$LAB_STATE/admin.pw")") || return 1
    {
        cat <<CONF
dn: cn=config
objectClass: olcGlobal
cn: config
olcLogLevel: stats

dn: cn=module{0},cn=config
objectClass: olcModuleList
cn: module{0}
olcModulePath: /usr/lib/ldap
olcModuleLoad: back_mdb

dn: cn=schema,cn=config
objectClass: olcSchemaConfig
cn: schema

CONF
        for f in core cosine nis inetorgperson; do cat "/etc/ldap/schema/$f.ldif"; echo; done
        cat <<CONF
dn: olcDatabase={0}config,cn=config
objectClass: olcDatabaseConfig
olcDatabase: {0}config
olcAccess: {0}to * by dn.exact="gidNumber=0+uidNumber=0,cn=peercred,cn=external,cn=auth" manage by * none

dn: olcDatabase={1}mdb,cn=config
objectClass: olcDatabaseConfig
objectClass: olcMdbConfig
olcDatabase: {1}mdb
olcDbDirectory: $LDAP_DB
olcSuffix: $LDAP_BASE
olcRootDN: $LDAP_ADMIN
olcRootPW: $hash
olcDbIndex: objectClass eq
olcDbIndex: uid eq
olcAccess: {0}to * by * read
CONF
    } > "$conf"
    chown "$LDAP_USER:$LDAP_USER" "$conf"
    umask 022
    runuser -u "$LDAP_USER" -- slapadd -n 0 -F "$LDAP_CONF" -l "$conf" || return 1
    rm -f -- "$conf"
    cat > "$LDAP_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated slapd exercise (127.0.0.1:3890)
After=network.target
[Service]
User=$LDAP_USER
Group=$LDAP_USER
ExecStartPre=+/usr/bin/install -d -m 0755 /run/slapd
ExecStartPre=+/usr/bin/install -d -o $LDAP_USER -g $LDAP_USER -m 0755 $LDAP_RUN
ExecStart=/usr/sbin/slapd -d 256 -F $LDAP_CONF -h "ldap://127.0.0.1:3890/ ldapi://%%2Frun%%2Fslapd%%2Fdojo%%2Fldapi/"
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now dojo-ldap.service || return 1
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do
        _ldap_external -b cn=config -s base dn >/dev/null 2>&1 && break
        sleep 1
    done
    _ldap_external -b cn=config -s base dn >/dev/null 2>&1 || { echo 'slapdが起動しません。journalctl -u dojo-ldap.service (AppArmorの拒否はdmesg)を確認します。'; return 1; }
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用slapd (ldap://127.0.0.1:3890 と ldapiソケット) だけを使う。標準のslapd/389番/nsswitch/PAM/sssdは触らない。
パスワードは root だけが読める: sudo cat $LAB_STATE/admin.pw (cn=admin,$LDAP_BASE) と alice.pw (aliceに設定すべき値)。
ldapコマンドは sudo で実行してよい。-x は簡易認証、-y はパスワードファイル指定(改行なしファイル)。
1. 状態確認: ldapsearch -x -H $LDAP_URI -s base -b '' namingContexts
   設定(cn=config)はsudo ldapsearch -Y EXTERNAL -H $LDAP_SOCK -b cn=config で読める。
2. DITをLDIFで作る(ldapadd -x -D rootdn -y admin.pw -f file.ldif。slapaddはsystemctl stop後にdojo-ldapユーザーで)。
   $LDAP_BASE (organization+dcObject)、ou=people、ou=groups、
   uid=alice/bob/carol (inetOrgPerson+posixAccount。uidNumber>=1000で重複なし、gidNumber、homeDirectory、loginShell、cn、sn)、
   cn=staff,ou=groups (posixGroup、gidNumber、memberUid=alice,bob,carol) の計7エントリ。ほかは作らない。
3. ldappasswdで3人全員のuserPasswordを設定する。aliceは alice.pw の内容にする(-T で新パスワードファイル指定)。
   ldapmodifyでbobのloginShellを変更して、ldapsearchで確認する。
4. ACLを書く。ldapmodify -Y EXTERNAL -H $LDAP_SOCK で olcDatabase={1}mdb,cn=config のolcAccessをreplaceする。
   - userPassword: 本人はwrite、認証(auth)は誰でも可、それ以外は none
   - それ以外の属性: 全員read
   順序が重要(最初に一致した to 句だけ評価される)。匿名でuserPasswordを読めず、aliceがbobのuidNumberは読めることを確認する。
5. 検証: ldapwhoami -x -H $LDAP_URI -D uid=alice,ou=people,$LDAP_BASE -y alice.pw 、誤パスワードは err 49 (Invalid credentials)。
   slapcat (dojo-ldapユーザーで -F $LDAP_CONF -b $LDAP_BASE) とldapsearchの結果が同じか比べる。
   sudo dojo-vm-lab ldap break
6. breakの後は匿名でuserPasswordが読め、rootdnでbindできない。原因をcn=configから調べ、
   ACLを再び締め、olcRootPWをadmin.pwの内容のハッシュ(slappasswd)に直す。DIT側のデータは変更しない。
   sudo dojo-vm-lab ldap check
7. sudo dojo-vm-lab ldap reset (専用インスタンスだけ削除)
次の一歩(この実習の範囲外): StartTLS (ldap://+TLS / ldaps) で通信を暗号化する。クライアント側は
nsswitch.conf/PAMにldapを直接書かず、SSSD (sssd-ldap) でldap_uri・ldap_search_baseを設定してgetent passwd aliceで解決する。
TASK
    echo "手順: sudo cat $LAB_STATE/TASKS.txt"
}

lab_break() {
    _ldap_paths || return 1
    _ldap_owned || { echo '先にsetupしてください。'; return 1; }
    _ldap_verify || { echo 'まずDIT・パスワード・ACLを完成させてからbreakします。'; return 1; }
    local hash
    hash=$(slappasswd -s "wrong-$(cat /proc/sys/kernel/random/uuid)") || return 1
    _ldap_external_modify() { env LDAPNOINIT=1 timeout 15 ldapmodify -Q -Y EXTERNAL -H "$LDAP_SOCK"; }
    _ldap_external_modify <<LDIF >/dev/null || { echo 'break用の変更に失敗しました。'; return 1; }
dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcAccess
olcAccess: {0}to * by * read
-
replace: olcRootPW
olcRootPW: $hash
LDIF
    local cnt rc
    cnt=$(_ldap_anon -b "$LDAP_BASE" -s sub '(uid=*)' userPassword 2>/dev/null | grep -ci '^userPassword')
    [[ $cnt == 3 ]] || { echo '匿名読み取りの障害を確認できません。'; return 1; }
    _ldap_whoami "$LDAP_ADMIN" "$LAB_STATE/admin.pw" >/dev/null 2>&1 && rc=0 || rc=$?
    [[ $rc == 49 ]] || { echo 'rootdn障害を確認できません。'; return 1; }
    touch "$LAB_STATE/fault"
    echo '匿名でuserPasswordが読め、rootdnでbindできない状態です。cn=configのolcAccessとolcRootPWを調べて直します。'
}

lab_check() {
    _ldap_paths || return 1
    _ldap_owned || { echo '先にsetupしてください。'; return 1; }
    [[ -f $LAB_STATE/fault ]] || { echo 'まずDITとACLを完成させ、breakで障害を作ります。'; return 1; }
    _ldap_verify || return 1
    echo 'PASS: 専用slapd上で、DIT7エントリ・正誤パスワードのbind(err 49)・匿名のuserPassword拒否・本人の参照・slapcat一致・rootdn復旧を実接続で確認しました。'
}

lab_reset() {
    _ldap_paths || return 1
    _ldap_owned || { echo 'この課題が作成した専用インスタンスではありません。'; return 1; }
    systemctl disable --now dojo-ldap.service 2>/dev/null || true
    rm -f -- "$LDAP_UNIT"
    systemctl daemon-reload
    rm -rf -- "$LDAP_HOME" "$LDAP_RUN"
    getent passwd "$LDAP_USER" >/dev/null && { userdel "$LDAP_USER" || return 1; }
    rm -f -- "$LAB_STATE/owns-ldap" "$LAB_STATE/fault" "$LAB_STATE/admin.pw" "$LAB_STATE/alice.pw" "$LAB_STATE/dit.ldif" "$LAB_STATE/slapcat.ldif" "$LAB_STATE/TASKS.txt"
    echo '専用slapdを削除しました。OS標準のslapd・/etc/ldap・389番は変更していません。'
}
