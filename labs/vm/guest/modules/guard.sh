# title: fail2banによる自動遮断とauditdによる監査証跡
# roles: app
# Lab-owned log, lab-owned jail/filter/action and a watched lab file. Only 192.0.2.0/24 (documentation range) is ever used.
# fail2ban and auditd are NOT part of the base image: setup refuses with an install instruction when missing.

_guard_paths() {
    [[ ${LAB_ID:-} == guard && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/guard ]] || { echo 'guard: unexpected lab context' >&2; return 1; }
    G_DIR=/var/log/dojo-guard-lab
    G_LOG=$G_DIR/login.log
    G_BANS=$LAB_STATE/bans.txt
    G_HELPER=/usr/local/sbin/dojo-guard-fail
    G_JAIL=/etc/fail2ban/jail.d/dojo-sshd-lab.conf
    G_FILTER=/etc/fail2ban/filter.d/dojo-sshd-lab.conf
    G_ACTION=/etc/fail2ban/action.d/dojo-lab-record.conf
    G_RULES=/etc/audit/rules.d/dojo-guard.rules
    G_AUDIT_DIR=/srv/dojo-audit
    G_TARGET=$G_AUDIT_DIR/secret.txt
    G_USER=dojo-auditor
    G_JAILNAME=dojo-sshd-lab
    [[ ! -L $G_DIR && ! -L $G_HELPER && ! -L $G_AUDIT_DIR && ! -L $G_ACTION && ! -L $G_FILTER && ! -L $G_JAIL && ! -L $G_RULES ]] || return 1
}

_guard_tools() {
    local missing=() t
    for t in fail2ban-client fail2ban-regex auditctl ausearch aureport augenrules; do
        command -v "$t" >/dev/null || missing+=("$t")
    done
    if ((${#missing[@]})); then
        echo "必要なコマンドがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y fail2ban auditd'
        return 1
    fi
    systemctl is-active --quiet fail2ban || systemctl start fail2ban || return 1
    systemctl is-active --quiet auditd || systemctl start auditd || return 1
}

# Writes the shipped (broken-format) filter. $1 = file
_guard_write_bad_filter() {
    cat > "$1" <<'CONF'
[Definition]
failregex = ^.*Failed password for .* from <HOST>\b
ignoreregex =
CONF
}

# Banned IPs per fail2ban-client, one per line.
_guard_banned() {
    fail2ban-client status "$G_JAILNAME" 2>/dev/null | sed -n 's/.*Banned IP list:[[:space:]]*//p' | tr ' ' '\n' | sed '/^$/d'
}

_guard_is_banned() { _guard_banned | grep -qxF -- "$1"; }

_guard_get() { fail2ban-client get "$G_JAILNAME" "$@" 2>/dev/null; }

_guard_regex_match() { # $1 line; returns 0 if exactly 1 matched
    local out
    out=$(fail2ban-regex "$1" "$G_FILTER" 2>&1) || return 1
    grep -Eq 'Lines: 1 lines, 0 ignored, 1 matched, 0 missed' <<<"$out"
}

_guard_audit_loaded() {
    auditctl -l 2>/dev/null | grep -F -- "-w $G_TARGET" | grep -Eq -- '-k dojo$'
}

lab_setup() {
    _guard_paths || return 1
    _guard_tools || return 1
    [[ ! -e $G_DIR && ! -e $G_HELPER && ! -e $G_AUDIT_DIR && ! -e $G_ACTION && ! -e $G_FILTER && ! -e $G_JAIL && ! -e $G_RULES ]] \
        || { echo '専用構成が既にあります。既存データを上書きしません。'; return 1; }
    if getent passwd "$G_USER" >/dev/null; then echo '専用アカウント名が使用済みです。'; return 1; fi
    install -d -m 0755 "$G_DIR"
    : > "$G_LOG"; chmod 0644 "$G_LOG"
    : > "$G_BANS"
    cat > "$G_HELPER" <<'HELPER'
#!/bin/bash
# LinuxDOJO lab helper: append failed-login lines to the lab log. Documentation range 192.0.2.0/24 only.
# usage: dojo-guard-fail [--print] IP [COUNT=1] [AGE_SECONDS=0]
set -euo pipefail
LOG=/var/log/dojo-guard-lab/login.log
print_only=0
if [[ ${1:-} == --print ]]; then print_only=1; shift; fi
ip=${1:-}; count=${2:-1}; age=${3:-0}
[[ $ip =~ ^192\.0\.2\.([0-9]{1,3})$ && ${BASH_REMATCH[1]} -le 255 ]] || { echo '192.0.2.0/24 (文書用アドレス) 以外は使えません。' >&2; exit 2; }
[[ $count =~ ^[0-9]{1,2}$ && $count -ge 1 && $count -le 20 ]] || { echo 'COUNTは1-20' >&2; exit 2; }
[[ $age =~ ^[0-9]{1,6}$ ]] || { echo 'AGE_SECONDSは数値' >&2; exit 2; }
stamp=$(date -d "-${age} seconds" '+%b %d %H:%M:%S')
for ((i = 0; i < count; i++)); do
    line="$stamp dojo-app dojo-login[$$]: authentication failure for user admin from $ip"
    if ((print_only)); then echo "$line"; else echo "$line" >> "$LOG"; fi
done
HELPER
    chmod 0755 "$G_HELPER"
    cat > "$G_ACTION" <<CONF
[Definition]
actionstart =
actionstop =
actioncheck =
actionban = echo "<ip>" >> $G_BANS
actionunban = sed -i '/^<ip>\$/d' $G_BANS
CONF
    useradd --system --home-dir "$G_AUDIT_DIR" --create-home --shell /bin/bash "$G_USER" || return 1
    touch "$LAB_STATE/owns-account"
    printf 'dojo-secret-%s\n' "$(cat /proc/sys/kernel/random/uuid)" > "$G_TARGET"
    chown "$G_USER:$G_USER" "$G_TARGET"; chmod 0644 "$G_TARGET"
    touch "$LAB_STATE/owns-files"
    cat > "$LAB_STATE/TASKS.txt" <<'TASK'
この課題はapp VMで sudo 付きで操作する。使うのは文書用アドレス 192.0.2.0/24 だけ。
本物のsshdやauth.logには触れない。fail2banの専用jailは専用ログ /var/log/dojo-guard-lab/login.log だけを見る。

[A] fail2ban
1. ログの書式を読む:  sudo dojo-guard-fail --print 192.0.2.10
2. /etc/fail2ban/filter.d/dojo-sshd-lab.conf を書く（failregexに <HOST> を使う）。
   fail2ban-regex "$(sudo dojo-guard-fail --print 192.0.2.10)" /etc/fail2ban/filter.d/dojo-sshd-lab.conf
   で 1 matched になること。成功ログ等は一致させない（.* だけの雑な正規表現は不正解）。
3. /etc/fail2ban/jail.d/dojo-sshd-lab.conf に jail [dojo-sshd-lab] を書く。
   enabled / filter / logpath(専用ログのみ) / backend = polling /
   action = dojo-lab-record（提供済み。banを $LAB_STATE の bans.txt に記録するだけ）
   maxretry 2-5, findtime 10以上, bantime 60以上。ignoreipで 192.0.2.0/24 を除外してはならない。
4. sudo fail2ban-client reload  →  sudo fail2ban-client status dojo-sshd-lab
5. sudo dojo-guard-fail 192.0.2.10 <maxretry回>  → statusで遮断を確認。
   sudo fail2ban-client set dojo-sshd-lab unbanip 192.0.2.10 で解除。
6. maxretry未満では遮断されないこと、findtimeより古い失敗(第3引数AGE秒)は数えられないことを試す。

[B] auditd
7. /etc/audit/rules.d/dojo-guard.rules に /srv/dojo-audit/secret.txt の読取・書込・属性変更を
   監視する規則を書く（キーは dojo）。 sudo augenrules --load → sudo auditctl -l
8. dojo-auditorとして読む/追記/chmodする:  sudo runuser -u dojo-auditor -- cat /srv/dojo-audit/secret.txt など
9. sudo ausearch -k dojo -i  で誰が何をしたか確認し、sudo aureport -k --summary で集計。

[C] 障害
10. A・Bが動いたら sudo dojo-vm-lab guard break
    遮断もされず監査も取れない状態になる。fail2ban-regex と auditctl -l / ausearch から原因を特定し直す。
11. sudo dojo-vm-lab guard check
12. 終了後 sudo dojo-vm-lab guard reset（専用のjail/filter/規則/ユーザー/ログのみ削除）
TASK
    echo "手順: $LAB_STATE/TASKS.txt （この課題が作る構成は専用ログ・専用jail・専用監査規則のみです）"
}

lab_break() {
    _guard_paths || return 1
    [[ -f $LAB_STATE/owns-files && -f $LAB_STATE/owns-account ]] || return 1
    _guard_tools || return 1
    [[ -f $G_FILTER && -f $G_JAIL && -f $G_RULES ]] || { echo 'まずfilter・jail・監査規則を作成します。'; return 1; }
    _guard_regex_match "$("$G_HELPER" --print 192.0.2.10)" || { echo 'まずfilterを正しく書き、fail2ban-regexで一致させます。'; return 1; }
    _guard_audit_loaded || { echo 'まず監査規則を読み込みます(augenrules --load)。'; return 1; }
    _guard_write_bad_filter "$G_FILTER"
    sed -i -E 's/-k[[:space:]]+[^[:space:]]+/-k dojo-wrong/' "$G_RULES"
    fail2ban-client reload >/dev/null || return 1
    augenrules --load >/dev/null 2>&1 || true
    _guard_regex_match "$("$G_HELPER" --print 192.0.2.10)" && { echo '障害を作れませんでした。'; return 1; }
    touch "$LAB_STATE/fault"
    echo 'ログ失敗が遮断されず、監査キーも合わない状態です。fail2ban-regexとausearch -k dojoで調べます。'
}

lab_check() {
    _guard_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずA・Bを完成させ、breakで障害を作ります。'; return 1; }
    _guard_tools || return 1
    local line ip=192.0.2.77 old=192.0.2.78 maxretry findtime bantime n ok i start out
    # --- fail2ban: real configuration of the running jail
    fail2ban-client status "$G_JAILNAME" >/dev/null 2>&1 || { echo "jail $G_JAILNAME が動いていません。reloadを確認します。"; return 1; }
    [[ $(_guard_get logpath | grep -cE '^[|`]?-' ) -eq 1 ]] && _guard_get logpath | grep -qF -- "$G_LOG" \
        || { echo 'logpathは専用ログ1つだけにします。'; return 1; }
    n=$(_guard_get actions | sed '1d' | sed '/^$/d')
    [[ $n == dojo-lab-record ]] || { echo 'actionはdojo-lab-recordだけにします。'; return 1; }
    grep -Eq '^[[:space:]]*backend[[:space:]]*=[[:space:]]*polling' "$G_JAIL" || { echo 'backend = polling を指定します。'; return 1; }
    maxretry=$(_guard_get maxretry); findtime=$(_guard_get findtime); bantime=$(_guard_get bantime)
    [[ $maxretry =~ ^[0-9]+$ && $maxretry -ge 2 && $maxretry -le 5 ]] || { echo 'maxretryは2-5。'; return 1; }
    [[ $findtime =~ ^[0-9]+$ && $findtime -ge 10 && $findtime -le 3600 ]] || { echo 'findtimeは10-3600秒。'; return 1; }
    [[ $bantime =~ ^[0-9]+$ && $bantime -ge 60 ]] || { echo 'bantimeは60秒以上。'; return 1; }
    if _guard_get ignoreip | grep -Eq '192\.0\.2\.|192\.0\.0\.0|0\.0\.0\.0|/(0|8|16|24)\b'; then
        echo '文書用アドレスをignoreipに入れて回避してはいけません。'; return 1
    fi
    # --- filter regex judged by fail2ban-regex on real lines
    line=$("$G_HELPER" --print "$ip")
    _guard_regex_match "$line" || { echo 'filterがログ書式に一致しません(fail2ban-regex)。'; return 1; }
    fail2ban-regex "${line/authentication failure/session opened}" "$G_FILTER" 2>&1 | grep -Eq '0 matched' \
        || { echo '失敗以外の行に一致しています。failregexを絞ります。'; return 1; }
    # --- real ban, record and unban
    _guard_is_banned "$ip" && fail2ban-client set "$G_JAILNAME" unbanip "$ip" >/dev/null
    "$G_HELPER" "$ip" "$maxretry" || return 1
    ok=0
    for i in $(seq 1 25); do _guard_is_banned "$ip" && { ok=1; break; }; sleep 1; done
    ((ok)) || { echo "maxretry回の失敗で $ip が遮断されません。"; return 1; }
    grep -qxF "$ip" "$G_BANS" || { echo 'actionがbanを記録していません。'; return 1; }
    if _guard_banned | grep -qvE '^192\.0\.2\.[0-9]{1,3}$'; then
        echo '文書用アドレス以外が遮断されています。jailの対象を確認します(自動解除はしません)。'; return 1
    fi
    fail2ban-client set "$G_JAILNAME" unbanip "$ip" >/dev/null || return 1
    sleep 1
    _guard_is_banned "$ip" && { echo '解除できていません。'; return 1; }
    grep -qxF "$ip" "$G_BANS" && { echo 'unbanがactionに反映されていません。'; return 1; }
    # --- findtime: old failures must not count
    "$G_HELPER" "$old" "$((maxretry + 2))" "$((findtime + 300))" || return 1
    sleep 4
    _guard_is_banned "$old" && { echo 'findtimeより古い失敗で遮断されています。'; fail2ban-client set "$G_JAILNAME" unbanip "$old" >/dev/null; return 1; }
    # --- auditd: real events by a dedicated user
    _guard_audit_loaded || { echo '監査規則がカーネルに読み込まれていません(auditctl -l)。キーはdojo。'; return 1; }
    auditctl -l | grep -F -- "-w $G_TARGET" | grep -Eq -- '-p [rwxa]*r[rwxa]*w|-p [rwxa]*w[rwxa]*r' \
        && auditctl -l | grep -F -- "-w $G_TARGET" | grep -Eq -- '-p [rwxa]*a' || { echo '読取・書込・属性変更(r,w,a)を監視します。'; return 1; }
    [[ -f $G_RULES ]] || return 1
    sleep 1; start=$(date +%T)
    runuser -u "$G_USER" -- cat "$G_TARGET" >/dev/null || return 1
    runuser -u "$G_USER" -- sh -c "echo check >> '$G_TARGET'" || return 1
    runuser -u "$G_USER" -- chmod 0640 "$G_TARGET" || return 1
    runuser -u "$G_USER" -- chmod 0644 "$G_TARGET" || return 1
    sleep 3
    out=$(ausearch -k dojo -i -f "$G_TARGET" -ts "$start" 2>/dev/null) || { echo 'ausearch -k dojo に該当イベントがありません。'; return 1; }
    grep -q 'uid=dojo-auditor' <<<"$out" || { echo 'dojo-auditorの操作が記録されていません。'; return 1; }
    grep -Eq 'syscall=(open|openat)' <<<"$out" && grep -Eq 'syscall=(chmod|fchmodat|fchmodat2)' <<<"$out" \
        || { echo '読み書きと属性変更の両方を記録します。'; return 1; }
    aureport -k -i --summary -ts "$start" 2>/dev/null | grep -Eq '(^|[[:space:]])dojo$' || { echo 'aureportの鍵集計にdojoがありません。'; return 1; }
    echo 'PASS: jailの実設定・filterの一致/非一致・実際の遮断と解除・findtime・専用ユーザー操作の監査記録を確認しました。'
}

lab_reset() {
    _guard_paths || return 1
    [[ -f $LAB_STATE/owns-files && -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    command -v fail2ban-client >/dev/null && fail2ban-client set "$G_JAILNAME" unbanip 192.0.2.10 >/dev/null 2>&1 || true
    rm -f -- "$G_JAIL" "$G_FILTER" "$G_ACTION" "$G_RULES" "$G_HELPER"
    if command -v fail2ban-client >/dev/null; then fail2ban-client reload >/dev/null 2>&1 || true; fi
    if command -v auditctl >/dev/null; then
        auditctl -W "$G_TARGET" -p rwxa -k dojo >/dev/null 2>&1 || true
        auditctl -W "$G_TARGET" -p rwxa -k dojo-wrong >/dev/null 2>&1 || true
        command -v augenrules >/dev/null && augenrules --load >/dev/null 2>&1 || true
    fi
    userdel --remove "$G_USER" 2>/dev/null || true
    rm -rf -- "$G_AUDIT_DIR" "$G_DIR"
    rm -f -- "$G_BANS" "$LAB_STATE/owns-files" "$LAB_STATE/owns-account" "$LAB_STATE/fault" "$LAB_STATE/TASKS.txt"
    echo '専用のjail/filter/action/監査規則/ユーザー/ログを削除しました。fail2ban・auditd本体と他の設定は変更していません。'
}
