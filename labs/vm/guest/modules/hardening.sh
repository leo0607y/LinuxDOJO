# title: Linuxの基本ハードニング監査 SUID・world-writable・孤児ファイル・空パスワード・umask・sudoers・sshd設定
# roles: app
# Fixes happen only on lab-owned paths (/srv/dojo-hardening, user dojo-hard). Host files are inspected read-only.
# Note: /srv/dojo-audit belongs to the guard lab, so this lab uses /srv/dojo-hardening.

_hd_paths() {
    [[ ${LAB_ID:-} == hardening && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/hardening ]] || { echo 'hardening: unexpected lab context' >&2; return 1; }
    HD=/srv/dojo-hardening
    HD_USER=dojo-hard
    HD_UNIT=dojo-hard-listener
    HD_PORT=18300
    HD_REPORT=$HD/report.txt
    [[ ! -L $HD ]] || { echo 'hardening: symbolic target rejected' >&2; return 1; }
}

_hd_tools() {
    local t missing=()
    for t in sshd ss visudo ssh-keygen python3 systemd-run find useradd userdel passwd; do
        command -v "$t" >/dev/null || missing+=("$t")
    done
    if ((${#missing[@]})); then echo "必要なコマンドがありません: ${missing[*]}"; return 1; fi
}

_hd_unused_uid() {
    local u
    for u in 60123 60124 60125 60126; do
        getent passwd "$u" >/dev/null || getent group "$u" >/dev/null || { echo "$u"; return 0; }
    done
    return 1
}

_hd_write_good_sshd() {
    cat > "$HD/etc/sshd_config" <<CONF
# LinuxDOJO hardening lab copy. Never used by the real sshd.
Port 22222
HostKey $HD/etc/ssh_host_ed25519_key
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
X11Forwarding no
PubkeyAuthentication yes
CONF
}

lab_setup() {
    _hd_paths || return 1
    _hd_tools || return 1
    [[ ! -e $HD ]] || { echo '専用ディレクトリが既にあります。既存データを上書きしません。'; return 1; }
    if getent passwd "$HD_USER" >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    if systemctl cat "$HD_UNIT.service" >/dev/null 2>&1; then echo '専用unit名が使用済みです。'; return 1; fi
    if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq ":$HD_PORT\$"; then echo "ポート$HD_PORT は使用中です。"; return 1; fi
    install -d -m 0755 "$HD" || return 1
    touch "$HD/.dojo-hardening-lab" "$LAB_STATE/owns-lab"
    install -d -m 0755 "$HD/bin" "$HD/data" "$HD/etc" "$HD/etc/sudoers.d" "$HD/policy" "$HD/www"
    install -d -m 0777 "$HD/tmp"; chmod 1777 "$HD/tmp"
    install -d -m 0755 "$HD/shared"
    echo 'dojo hardening lab' > "$HD/www/index.html"
    install -m 0755 /usr/bin/true "$HD/bin/dojo-helper"; chmod 4755 "$HD/bin/dojo-helper"
    sha256sum /usr/bin/true | cut -d ' ' -f 1 > "$LAB_STATE/true.sha256"
    printf 'bin/dojo-helper\n' > "$HD/suid-allowlist.txt"
    printf '%s\n' "$HD_PORT" > "$HD/listener-allow.txt"
    sha256sum "$HD/suid-allowlist.txt" "$HD/listener-allow.txt" > "$LAB_STATE/allow.sha256"
    useradd --no-create-home --home-dir "$HD/home" --shell /usr/sbin/nologin "$HD_USER" || return 1
    touch "$LAB_STATE/owns-account"
    passwd -l "$HD_USER" >/dev/null
    printf 'umask 027\n' > "$HD/policy/umask.sh"
    printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl status ssh\n' "$HD_USER" > "$HD/etc/sudoers.d/90-dojo-hard"
    chmod 0440 "$HD/etc/sudoers.d/90-dojo-hard"
    ssh-keygen -q -t ed25519 -N '' -f "$HD/etc/ssh_host_ed25519_key" || return 1
    install -d -m 0755 /run/sshd
    _hd_write_good_sshd
    systemd-run --quiet --unit="$HD_UNIT" --collect -p DynamicUser=yes -p ProtectSystem=strict -p ProtectHome=yes \
        /usr/bin/python3 -m http.server "$HD_PORT" --bind 127.0.0.1 --directory "$HD/www" || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
対象は $HD とユーザー $HD_USER だけです。ホスト全体の設定(/etc/passwd, sshd, umask等)は読むだけで変更しません。
この専用VMの中で sudo -i を実行して作業します。
1. sudo dojo-vm-lab hardening break で、$HD に弱点を仕込みます(どこに何があるかは書きません)。
2. 監査します。道具の例:
   find $HD -xdev -type f \( -perm -4000 -o -perm -2000 \) -ls      (SUID/SGID。suid-allowlist.txt と突き合わせ)
   find $HD -xdev \( -type f -perm -0002 \) -o \( -type d -perm -0002 ! -perm -1000 \)   (world-writable、sticky無しのdir)
   find $HD -xdev \( -nouser -o -nogroup \) -ls
   getent shadow $HD_USER ; passwd -S $HD_USER ; ls -l /etc/passwd /etc/shadow        (読むだけ)
   bash -c '. $HD/policy/umask.sh; umask' ; visudo -cf $HD/etc/sudoers.d/90-dojo-hard
   sshd -T -f $HD/etc/sshd_config | grep -Ei 'permitroot|password|x11|emptypass'
   apt-config dump | grep -i Periodic ; dpkg -l unattended-upgrades ; sudo ss -ltnp
   (lynis があれば lynis audit system --quick を参考に。必須ではありません)
3. 弱点を直します(許可リストにある正規のSUIDは残す。sticky付きの共有dirは正規なので残す)。
   chmod u-s / g-s / o-w、chown、passwd -l、umask設定、sudoers最小権限化、sshd設定の修正など。
4. $HD_REPORT に所見を書きます。見つけた弱点ごとにファイル名/設定名と理由・対処、加えて次を含めます。
   - /etc/passwd と /etc/shadow の実際のモード
   - 行 'unattended-upgrades: enabled' / 'disabled' / 'not-installed' のいずれか(実際の状態)
   - ss -ltnp に出た待受ポートすべてと、許可リスト($HD/listener-allow.txt)に対する評価(許可/要確認)
5. sudo dojo-vm-lab hardening check
6. 片付け: sudo dojo-vm-lab hardening reset
TASK
    echo "手順: $LAB_STATE/TASKS.txt"
}

lab_break() {
    _hd_paths || return 1
    [[ -f $LAB_STATE/owns-lab && -f $LAB_STATE/owns-account && ! -f $LAB_STATE/broken && -f $HD/.dojo-hardening-lab ]] || { echo 'setup済みで未breakの状態で実行してください。'; return 1; }
    local uid
    uid=$(_hd_unused_uid) || { echo '孤児ファイル用のIDを確保できません。'; return 1; }
    install -m 0755 /usr/bin/true "$HD/bin/dojo-update"; chmod 4755 "$HD/bin/dojo-update"
    install -m 0755 /usr/bin/true "$HD/bin/dojo-wall"; chmod 2755 "$HD/bin/dojo-wall"
    chmod 0777 "$HD/shared"
    echo 'memo' > "$HD/shared/notes.txt"; chmod 0666 "$HD/shared/notes.txt"
    echo 'orphan' > "$HD/data/orphan.dat"; chown "$uid:$uid" "$HD/data/orphan.dat"
    passwd -d "$HD_USER" >/dev/null || return 1
    printf 'umask 000\n' > "$HD/policy/umask.sh"
    printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$HD_USER" > "$HD/etc/sudoers.d/90-dojo-hard"
    cat > "$HD/etc/sshd_config" <<CONF
# LinuxDOJO hardening lab copy. Never used by the real sshd.
Port 22222
HostKey $HD/etc/ssh_host_ed25519_key
PermitRootLogin yes
PasswordAuthentication yes
PermitEmptyPasswords yes
X11Forwarding yes
CONF
    [[ $(getent shadow "$HD_USER" | cut -d: -f2) == '' ]] || { echo '空パスワードを作れませんでした。'; return 1; }
    rm -f -- "$HD_REPORT"
    touch "$LAB_STATE/broken"
    echo "弱点を仕込みました。$LAB_STATE/TASKS.txt の手順で監査・修復・報告します。"
}

_hd_fail() { echo "NG: $*"; HD_FAILS=$((HD_FAILS + 1)); }

_hd_check_fixes() {
    local out m sshd shadow
    # allow-lists must be untouched
    (cd / && sha256sum -c --quiet "$LAB_STATE/allow.sha256" >/dev/null 2>&1) || { _hd_fail '許可リストが変更されています(リストではなく弱点を直します)'; }
    if [[ -f $HD/bin/dojo-helper ]]; then
        [[ $(stat -c %a "$HD/bin/dojo-helper") == 4755 && $(sha256sum "$HD/bin/dojo-helper" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/true.sha256") ]] || _hd_fail '許可済みSUID(bin/dojo-helper)は変更しません'
    else
        _hd_fail '許可済みSUID(bin/dojo-helper)が消えています'
    fi
    out=$(find "$HD" -xdev -type f -perm -4000 ! -path "$HD/bin/dojo-helper" 2>/dev/null)
    [[ -z $out ]] || _hd_fail "許可リスト外のSUIDが残っています: $out"
    out=$(find "$HD" -xdev -type f -perm -2000 2>/dev/null)
    [[ -z $out ]] || _hd_fail "SGIDが残っています: $out"
    out=$(find "$HD" -xdev \( -type f -perm -0002 \) -o \( -type d -perm -0002 ! -perm -1000 \) 2>/dev/null)
    [[ -z $out ]] || _hd_fail "world-writable(sticky無しdirを含む)が残っています: $out"
    [[ $(stat -c %a "$HD/tmp" 2>/dev/null) == 1777 ]] || _hd_fail 'sticky付き共有dir(tmp)は正規なので1777のまま残します'
    out=$(find "$HD" -xdev \( -nouser -o -nogroup \) 2>/dev/null)
    [[ -z $out ]] || _hd_fail "所有者/グループ不明のファイルが残っています: $out"
    shadow=$(getent shadow "$HD_USER" | cut -d: -f2)
    if [[ -z $shadow || ${shadow:0:1} != '!' && ${shadow:0:1} != '*' ]]; then _hd_fail "$HD_USER がロックされていません(空パスワード等)"; fi
    m=$(bash -c ". '$HD/policy/umask.sh' >/dev/null 2>&1; umask" 2>/dev/null)
    if [[ $m =~ ^[0-7]+$ ]] && (((8#$m & 8#027) == 8#027)); then :; else _hd_fail "umaskが027以上に厳しくありません(現在: ${m:-不明})"; fi
    visudo -cf "$HD/etc/sudoers.d/90-dojo-hard" >/dev/null 2>&1 || _hd_fail 'sudoersの構文が不正です'
    if grep -Ev '^[[:space:]]*(#|$)' "$HD/etc/sudoers.d/90-dojo-hard" 2>/dev/null | grep -Eq '[):=][[:space:]]*ALL[[:space:]]*$'; then _hd_fail 'sudoersが全コマンドを許可したままです'; fi
    sshd=$(sshd -T -f "$HD/etc/sshd_config" 2>&1) || { _hd_fail "sshd -T が失敗します: $(head -1 <<<"$sshd")"; return; }
    grep -Eqx 'permitrootlogin (no|prohibit-password)' <<<"$sshd" || _hd_fail 'PermitRootLoginが危険です'
    grep -Eqx 'passwordauthentication no' <<<"$sshd" || _hd_fail 'PasswordAuthenticationがnoではありません'
    grep -Eqx 'permitemptypasswords no' <<<"$sshd" || _hd_fail 'PermitEmptyPasswordsがnoではありません'
    grep -Eqx 'x11forwarding no' <<<"$sshd" || _hd_fail 'X11Forwardingがnoではありません'
}

_hd_check_report() {
    local text want pkg periodic state port listed
    if [[ ! -f $HD_REPORT || -L $HD_REPORT ]]; then _hd_fail "$HD_REPORT がありません"; return; fi
    [[ $HD_REPORT -nt $LAB_STATE/broken ]] || { _hd_fail 'レポートがbreak後に書かれていません'; return; }
    [[ $(stat -c %s "$HD_REPORT") -ge 300 ]] || { _hd_fail 'レポートが短すぎます'; return; }
    text=$(<"$HD_REPORT")
    for want in dojo-update dojo-wall notes.txt orphan.dat "$HD_USER" umask 90-dojo-hard PermitRootLogin PasswordAuthentication PermitEmptyPasswords X11Forwarding; do
        grep -qiF -- "$want" <<<"$text" || _hd_fail "レポートに '$want' の所見がありません"
    done
    for want in /etc/passwd /etc/shadow; do
        grep -F -- "$want" <<<"$text" | grep -q -- "$(stat -c %a "$want")" || _hd_fail "レポートに $want の実際のモード $(stat -c %a "$want") がありません"
    done
    pkg=$(dpkg-query -W -f='${Status}' unattended-upgrades 2>/dev/null)
    if [[ $pkg != *'install ok installed'* ]]; then state=not-installed
    else
        periodic=$(apt-config dump 2>/dev/null | sed -n 's/^APT::Periodic::Unattended-Upgrade "\(.*\)";/\1/p')
        if [[ $periodic =~ ^[1-9] ]]; then state=enabled; else state=disabled; fi
    fi
    grep -Eiq "unattended-upgrades:[[:space:]]*$state([^-a-z]|\$)" <<<"$text" || _hd_fail "unattended-upgradesの実際の状態($state)が 'unattended-upgrades: $state' の形でありません"
    while read -r port; do
        [[ -n $port ]] || continue
        grep -Eq "(^|[^0-9])$port([^0-9]|\$)" <<<"$text" || _hd_fail "待受ポート $port の評価がレポートにありません"
    done < <(ss -ltnH 2>/dev/null | awk '{n=split($4,a,":"); print a[n]}' | sort -un)
    listed=$(grep -E "(^|[^0-9])$HD_PORT([^0-9]|\$)" <<<"$text")
    grep -Eiq 'allow|許可|expected|想定' <<<"$listed" || _hd_fail "ポート $HD_PORT が許可リスト内であると記述されていません"
}

lab_check() {
    _hd_paths || return 1
    [[ -f $LAB_STATE/owns-lab && -f $LAB_STATE/broken && -f $HD/.dojo-hardening-lab ]] || { echo 'まずsetupとbreakを実行してください。'; return 1; }
    HD_FAILS=0
    systemctl is-active --quiet "$HD_UNIT" || _hd_fail "専用リスナー($HD_UNIT)が停止しています"
    _hd_check_fixes
    _hd_check_report
    if ((HD_FAILS == 0)); then
        echo 'PASS: 実ファイルのモード/所有者/アカウント状態と、所見レポートを確認しました。'
        return 0
    fi
    return 1
}

lab_reset() {
    _hd_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成したものではありません。'; return 1; }
    systemctl stop "$HD_UNIT" 2>/dev/null
    systemctl reset-failed "$HD_UNIT" 2>/dev/null
    if [[ -f $LAB_STATE/owns-account ]] && getent passwd "$HD_USER" >/dev/null; then
        [[ $(getent passwd "$HD_USER" | cut -d: -f6) == "$HD/home" ]] || { echo "$HD_USER は想定の専用アカウントではありません。"; return 1; }
        userdel "$HD_USER" || return 1
    fi
    if [[ -d $HD && -f $HD/.dojo-hardening-lab ]]; then
        rm -rf --one-file-system -- "${HD:?}"
    fi
    rm -f -- "${LAB_STATE:?}"/owns-lab "${LAB_STATE:?}"/owns-account "${LAB_STATE:?}"/broken "${LAB_STATE:?}"/true.sha256 "${LAB_STATE:?}"/allow.sha256
    echo "$HD と $HD_USER を削除しました。ホストの設定は変更していません。"
}
