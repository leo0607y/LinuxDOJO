# title: systemd応用 ソケット起動・テンプレート・依存循環・timer・再起動制限・サンドボックス
# roles: app
# All units are lab-named dojo-adv-*; nothing else under /etc/systemd is touched. Guest-only.

# Calibrated on Ubuntu 24.04 (systemd 255) with a real VM: ProtectSystem=strict+ProtectHome+PrivateTmp+NoNewPrivileges
# +ReadWritePaths scores 8.7; +CapabilityBoundingSet= 6.2; +SystemCallFilter=@system-service 4.8 (4.6 with ~@privileged @resources);
# keeping one capability (CAP_CHOWN) 5.0; only dropping CAP_SYS_ADMIN 7.1. 5.5 requires the caps AND syscall filter work
# but leaves 0.7 of margin for score drift between systemd versions.
SA_THRESHOLD=5.5

_sa_paths() {
    [[ ${LAB_ID:-} == systemdadv && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/systemdadv ]] || { echo 'systemdadv: unexpected lab context' >&2; return 1; }
    SA_UNITDIR=/etc/systemd/system
    SA_LIB=/usr/local/lib/linuxdojo-vm-lab
    SA_DATA=/var/lib/dojo-adv-data
    SA_RUN=/run/dojo-adv
    SA_UNITS=(dojo-adv-sock.socket dojo-adv-sock.service dojo-adv-worker@.service dojo-adv-a.service dojo-adv-b.service dojo-adv-c.service dojo-adv-cal.timer dojo-adv-cal.service dojo-adv-crash.service dojo-adv-data.service)
    SA_SCRIPTS=(dojo-adv-sock.py dojo-adv-worker.sh dojo-adv-data.py dojo-adv-crash.sh)
    local u
    for u in "${SA_UNITS[@]}"; do
        [[ ! -L $SA_UNITDIR/$u && ! -L $SA_UNITDIR/$u.d ]] || { echo 'systemdadv: symbolic target rejected' >&2; return 1; }
    done
    [[ ! -L $SA_DATA && ! -L $SA_RUN ]] || { echo 'systemdadv: symbolic target rejected' >&2; return 1; }
}

_sa_prop() { systemctl show -P "$2" "$1" 2>/dev/null; }

_sa_write_scripts() {
    cat > "$SA_LIB/dojo-adv-sock.py" <<'PROGRAM'
#!/usr/bin/python3
# Socket-activated server: serves connections, exits after 4 idle seconds.
import os
import socket
import sys

if os.environ.get("LISTEN_FDS") != "1" or os.environ.get("LISTEN_PID") != str(os.getpid()):
    sys.exit("not socket-activated")
server = socket.socket(fileno=3)
server.settimeout(4)
while True:
    try:
        conn, _ = server.accept()
    except socket.timeout:
        sys.exit(0)
    with conn:
        conn.settimeout(2)
        try:
            conn.recv(64)
        except OSError:
            pass
        conn.sendall(("dojo-adv-sock pid=%d\n" % os.getpid()).encode())
PROGRAM
    cat > "$SA_LIB/dojo-adv-worker.sh" <<'PROGRAM'
#!/bin/bash
# Template instance worker: records its instance name and pid, then idles.
set -eu
inst=${1:?instance required}
[[ $inst =~ ^[a-z0-9]+$ ]]
install -d -m 0755 /run/dojo-adv
printf '%s %s\n' "$inst" "$$" > "/run/dojo-adv/worker-$inst"
exec /usr/bin/sleep infinity
PROGRAM
    cat > "$SA_LIB/dojo-adv-data.py" <<'PROGRAM'
#!/usr/bin/python3
# Writes a heartbeat into its data directory once a second.
import os
import time

directory = "/var/lib/dojo-adv-data"
count = 0
while True:
    count += 1
    tmp = directory + "/beat.tmp"
    with open(tmp, "w") as handle:
        handle.write("%d %d\n" % (count, int(time.time())))
    os.replace(tmp, directory + "/beat")
    time.sleep(1)
PROGRAM
    cat > "$SA_LIB/dojo-adv-crash.sh" <<'PROGRAM'
#!/bin/bash
echo 'dojo-adv-crash: simulated failure' >&2
exit 1
PROGRAM
    chmod 0755 "$SA_LIB"/dojo-adv-sock.py "$SA_LIB"/dojo-adv-worker.sh "$SA_LIB"/dojo-adv-data.py "$SA_LIB"/dojo-adv-crash.sh
}

_sa_write_units() {
    local d=$SA_UNITDIR
    cat > "$d/dojo-adv-sock.socket" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: socket
[Socket]
ListenStream=127.0.0.1:18200
[Install]
WantedBy=sockets.target
UNIT
    cat > "$d/dojo-adv-sock.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: socket-activated server
[Service]
ExecStart=$SA_LIB/dojo-adv-sock.py
UNIT
    cat > "$d/dojo-adv-worker@.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: worker instance %i
[Service]
ExecStart=$SA_LIB/dojo-adv-worker.sh %i
ExecStopPost=/usr/bin/rm -f /run/dojo-adv/worker-%i
UNIT
    cat > "$d/dojo-adv-a.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: A (needs B)
Requires=dojo-adv-b.service
After=dojo-adv-b.service
[Service]
ExecStart=/usr/bin/sleep infinity
UNIT
    cat > "$d/dojo-adv-b.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: B (base)
[Service]
ExecStart=/usr/bin/sleep infinity
UNIT
    cat > "$d/dojo-adv-c.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: C (bound to B)
BindsTo=dojo-adv-b.service
After=dojo-adv-b.service
[Service]
ExecStart=/usr/bin/sleep infinity
UNIT
    cat > "$d/dojo-adv-cal.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: scheduled job
[Service]
Type=oneshot
ExecStart=/usr/bin/true
UNIT
    cat > "$d/dojo-adv-cal.timer" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: weekday 03:30 timer
[Timer]
OnCalendar=Mon..Fri *-*-* 03:30:00
Unit=dojo-adv-cal.service
[Install]
WantedBy=timers.target
UNIT
    cat > "$d/dojo-adv-crash.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: crashing service
[Service]
ExecStart=$SA_LIB/dojo-adv-crash.sh
Restart=always
RestartSec=100ms
UNIT
    cat > "$d/dojo-adv-data.service" <<UNIT
[Unit]
Description=LinuxDOJO advanced systemd: heartbeat writer
[Service]
ExecStart=$SA_LIB/dojo-adv-data.py
UNIT
}

lab_setup() {
    _sa_paths || return 1
    command -v systemd-analyze >/dev/null && command -v python3 >/dev/null || { echo 'systemd-analyze と python3 が必要です。'; return 1; }
    local u s
    for u in "${SA_UNITS[@]}"; do
        [[ ! -e $SA_UNITDIR/$u && ! -e $SA_UNITDIR/$u.d ]] || { echo "既存の対象を上書きしません: $u"; return 1; }
    done
    for s in "${SA_SCRIPTS[@]}"; do [[ ! -e $SA_LIB/$s ]] || { echo "既存の対象を上書きしません: $s"; return 1; }; done
    [[ ! -e $SA_DATA && ! -e $SA_RUN ]] || { echo '専用ディレクトリが既にあります。'; return 1; }
    if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq ':18200$'; then echo 'ポート18200は使用中です。'; return 1; fi
    touch "$LAB_STATE/owns-units"
    install -d -m 0755 "$SA_DATA" || return 1
    _sa_write_scripts || return 1
    _sa_write_units || return 1
    sha256sum "$SA_UNITDIR/dojo-adv-crash.service" | cut -d ' ' -f 1 > "$LAB_STATE/crash.sha256"
    systemctl daemon-reload || return 1
    systemctl start dojo-adv-sock.socket dojo-adv-data.service || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
対象は dojo-adv-* のunitと専用ディレクトリだけです。他のunitは変更しません。
この専用VMの中で sudo -i を実行して作業します。unitは /etc/systemd/system にあります。
初期状態: socketとdojo-adv-dataが動いています。まず次で全体を観察します。
  systemctl list-units 'dojo-adv-*' --all ; systemctl cat dojo-adv-sock.socket
  ss -ltn ; systemd-analyze security dojo-adv-data.service
1. sudo dojo-vm-lab systemdadv break で故障を入れます。
2. 次を直します。変更は原則 systemctl edit (drop-in) か unitの修正で行い、変更後は daemon-reload を忘れずに。
   a. ソケット: 127.0.0.1:18200 に接続した時だけdojo-adv-sock.serviceが起動し、静かになると終了すること。
      (systemctl show -p Listen dojo-adv-sock.socket / ss -ltn / 接続して確かめる。bashの /dev/tcp が使えます)
   b. テンプレート: dojo-adv-worker@.service を dojo-adv-worker@a と @b の2つ起動し、
      /run/dojo-adv/worker-* に各instance名(%i)が別々に記録されること。
   c. 依存: dojo-adv-a/b/c の順序循環を systemd-analyze verify で診断し、解消します。
      Requires=は起動も連動、After=は順序だけ、BindsTo=は相手が止まれば自分も止まる、の違いを
      dojo-adv-a を起動し systemd-analyze critical-chain dojo-adv-a.service で確認します。
   d. timer: dojo-adv-cal.timer を「平日(月〜金)の毎朝03:30」で動かし、電源断の取りこぼしを補う設定(Persistent)を
      drop-inで加えて有効化します。systemd-analyze calendar '...' --iterations=7 で先に検証します。
      (OnCalendar= を空にしてリセットしないと値は追加されます)
   e. 再起動制限: dojo-adv-crash.service は即時に死に続けます。drop-inで、失敗時のみ再起動、
      RestartSecを1〜3秒、StartLimitBurstを2〜5回にして、上限に達したら failed (start-limit-hit) で止まるようにします。
      本体unitファイルは編集せず drop-in で行います。journalctl -u dojo-adv-crash で確認。
   f. サンドボックス: dojo-adv-data が書けなくなっています。journalctl で原因を読み、必要な書込先だけを許可しつつ、
      ProtectSystem=strict / ProtectHome / PrivateTmp / NoNewPrivileges / CapabilityBoundingSet / SystemCallFilter などで
      systemd-analyze security dojo-adv-data.service の露出スコアを $SA_THRESHOLD 未満にします。サービスは動き続けること。
3. sudo dojo-vm-lab systemdadv check
4. 片付け: sudo dojo-vm-lab systemdadv reset (dojo-adv-* だけ削除)。
TASK
    echo "手順: $LAB_STATE/TASKS.txt"
}

lab_break() {
    _sa_paths || return 1
    [[ -f $LAB_STATE/owns-units && ! -f $LAB_STATE/broken ]] || { echo 'setup済みで未breakの状態で実行してください。'; return 1; }
    [[ -f $SA_UNITDIR/dojo-adv-b.service && -f $SA_UNITDIR/dojo-adv-sock.socket && -f $SA_UNITDIR/dojo-adv-cal.timer ]] || return 1
    # 1) ordering cycle: B after A while A is after B
    sed -i 's/^Description=.*B (base)$/&\nAfter=dojo-adv-a.service/' "$SA_UNITDIR/dojo-adv-b.service"
    # 2) wrong port
    sed -i 's/^ListenStream=.*/ListenStream=127.0.0.1:18201/' "$SA_UNITDIR/dojo-adv-sock.socket"
    # 3) weekdays wrong
    sed -i 's/^OnCalendar=.*/OnCalendar=Mon,Fri *-*-* 03:30:00/' "$SA_UNITDIR/dojo-adv-cal.timer"
    # 4) sandbox that blocks the writable data dir
    install -d -m 0755 "$SA_UNITDIR/dojo-adv-data.service.d"
    cat > "$SA_UNITDIR/dojo-adv-data.service.d/10-sandbox.conf" <<'UNIT'
[Service]
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
UNIT
    systemctl daemon-reload || return 1
    systemctl restart dojo-adv-sock.socket
    systemctl restart dojo-adv-data.service || true
    sleep 2
    if systemctl is-active --quiet dojo-adv-data.service; then
        echo 'サンドボックス故障を確認できません。'; return 1
    fi
    touch "$LAB_STATE/broken"
    echo '故障を入れました。TASKS.txt の a〜f を調査して直します。'
}

SA_FAILS=0
_sa_fail() { echo "NG: $*"; SA_FAILS=$((SA_FAILS + 1)); }

_sa_check_socket() {
    local listen out pid i
    systemctl is-active --quiet dojo-adv-sock.socket || { _sa_fail 'dojo-adv-sock.socket が動いていません'; return; }
    listen=$(_sa_prop dojo-adv-sock.socket Listen)
    [[ $listen == *127.0.0.1:18200* ]] || { _sa_fail "ListenStreamが 127.0.0.1:18200 ではありません: $listen"; return; }
    systemctl stop dojo-adv-sock.service 2>/dev/null
    if systemctl is-active --quiet dojo-adv-sock.service; then _sa_fail 'serviceを停止できません'; return; fi
    out=$(python3 - <<'PY' 2>/dev/null
import socket
s = socket.create_connection(("127.0.0.1", 18200), timeout=4)
s.sendall(b"ping\n")
print(s.recv(128).decode().strip())
PY
    ) || { _sa_fail '127.0.0.1:18200 へ接続して応答を得られません'; return; }
    [[ $out =~ ^dojo-adv-sock\ pid=([0-9]+)$ ]] || { _sa_fail "想定外の応答です: $out"; return; }
    pid=${BASH_REMATCH[1]}
    [[ $(_sa_prop dojo-adv-sock.service MainPID) == "$pid" ]] || { _sa_fail '接続でserviceが起動した証拠(MainPID)がありません'; return; }
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
        systemctl is-active --quiet dojo-adv-sock.service || return 0
        sleep 1
    done
    _sa_fail 'アイドル後にserviceが終了しません'
}

_sa_check_template() {
    local n pid f inst
    for inst in a b; do
        systemctl is-active --quiet "dojo-adv-worker@$inst.service" || { _sa_fail "dojo-adv-worker@$inst が動いていません"; return; }
        f=$SA_RUN/worker-$inst
        [[ -f $f ]] || { _sa_fail "$f がありません"; return; }
        read -r n pid < "$f"
        [[ $n == "$inst" && $pid == "$(_sa_prop "dojo-adv-worker@$inst.service" MainPID)" ]] || { _sa_fail "instance $inst の%iまたはPIDが一致しません"; return; }
    done
    [[ $(_sa_prop dojo-adv-worker@a.service MainPID) != "$(_sa_prop dojo-adv-worker@b.service MainPID)" ]] || _sa_fail 'a/bのPIDが同一です'
}

_sa_check_deps() {
    local out rc
    out=$(cd "$SA_UNITDIR" && systemd-analyze verify dojo-adv-a.service dojo-adv-b.service dojo-adv-c.service dojo-adv-sock.socket dojo-adv-sock.service dojo-adv-cal.timer dojo-adv-cal.service dojo-adv-crash.service dojo-adv-data.service 2>&1)
    rc=$?
    if ((rc != 0)) || grep -qi 'cycle' <<<"$out"; then _sa_fail "systemd-analyze verify が警告します: $(head -3 <<<"$out" | tr '\n' ' ')"; return; fi
    systemctl stop dojo-adv-a.service dojo-adv-b.service dojo-adv-c.service 2>/dev/null
    systemctl start dojo-adv-a.service dojo-adv-c.service 2>/dev/null || { _sa_fail 'a/cを起動できません'; return; }
    systemctl is-active --quiet dojo-adv-b.service || { _sa_fail 'Requires=でbが連動起動していません'; return; }
    systemd-analyze critical-chain dojo-adv-a.service > "$LAB_STATE/critical-chain.txt" 2>&1 || _sa_fail 'critical-chainが取得できません'
    systemctl stop dojo-adv-b.service 2>/dev/null
    if systemctl is-active --quiet dojo-adv-c.service || systemctl is-active --quiet dojo-adv-a.service; then
        _sa_fail 'bを止めてもa(Requires)/c(BindsTo)が止まりません'
    fi
    systemctl stop dojo-adv-a.service dojo-adv-b.service dojo-adv-c.service 2>/dev/null
}

_sa_check_timer() {
    local specs state persistent
    state=$(_sa_prop dojo-adv-cal.timer ActiveState)
    [[ $state == active ]] || { _sa_fail 'dojo-adv-cal.timer が active ではありません'; return; }
    persistent=$(_sa_prop dojo-adv-cal.timer Persistent)
    [[ $persistent == yes ]] || { _sa_fail 'Persistent=yes ではありません'; return; }
    [[ -n $(_sa_prop dojo-adv-cal.timer NextElapseUSecRealtime) ]] || { _sa_fail '次回実行時刻がありません'; return; }
    specs=$(_sa_prop dojo-adv-cal.timer TimersCalendar)
    SA_SPECS=$specs python3 - <<'PY' || _sa_fail 'OnCalendarが平日(月〜金)の03:30のみになっていません'
import datetime
import os
import re
import subprocess
import sys

specs = re.findall(r"OnCalendar=(.*?) ;", os.environ["SA_SPECS"])
if not specs:
    sys.exit(1)
days = set()
for spec in specs:
    out = subprocess.run(["systemd-analyze", "calendar", "--iterations=14", spec], capture_output=True, text=True)
    if out.returncode:
        sys.exit(1)
    found = re.findall(r"(?:Next elapse|Iter(?:ation|\.) #\d+): \w{3} (\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)", out.stdout)
    if not found:
        sys.exit(1)
    for date, clock in found:
        if clock != "03:30:00":
            sys.exit(1)
        days.add(datetime.date.fromisoformat(date).isoweekday())
sys.exit(0 if days == {1, 2, 3, 4, 5} else 1)
PY
}

_sa_secs() { # "2s" "100ms" "1min 30s" -> whole seconds
    python3 - "$1" <<'PY'
import re
import sys

total = 0.0
for n, u in re.findall(r"([\d.]+)\s*(ms|us|min|s|h)", sys.argv[1]):
    total += float(n) * {"us": 1e-6, "ms": 1e-3, "s": 1, "min": 60, "h": 3600}[u]
print(int(total))
PY
}

_sa_check_crash() {
    local u=dojo-adv-crash.service burst rs i result=
    [[ $(sha256sum "$SA_UNITDIR/$u" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/crash.sha256") ]] || { _sa_fail '本体unitではなくdrop-inで設定してください'; return; }
    [[ -n $(_sa_prop $u DropInPaths) ]] || { _sa_fail 'drop-inがありません'; return; }
    [[ $(_sa_prop $u Restart) == on-failure ]] || { _sa_fail 'Restart=on-failure ではありません'; return; }
    burst=$(_sa_prop $u StartLimitBurst)
    [[ $burst =~ ^[0-9]+$ ]] && ((burst >= 2 && burst <= 5)) || { _sa_fail 'StartLimitBurstは2〜5にします'; return; }
    rs=$(_sa_secs "$(_sa_prop $u RestartUSec)")
    ((rs >= 1 && rs <= 3)) || { _sa_fail 'RestartSecは1〜3秒にします'; return; }
    systemctl reset-failed $u 2>/dev/null || true
    systemctl start --no-block $u
    for i in $(seq 1 40); do
        result=$(_sa_prop $u Result)
        [[ $result == start-limit-hit ]] && break
        sleep 1
    done
    systemctl stop $u 2>/dev/null || true
    systemctl reset-failed $u 2>/dev/null || true
    [[ $result == start-limit-hit ]] || _sa_fail "再起動上限(start-limit-hit)で停止しませんでした: Result=$result"
}

_sa_check_sandbox() {
    local u=dojo-adv-data.service v b1 b2 score caps
    systemctl restart $u 2>/dev/null
    sleep 2
    systemctl is-active --quiet $u || { _sa_fail 'dojo-adv-data が動いていません(書込先の許可を確認)'; return; }
    b1=$(cut -d ' ' -f 1 "$SA_DATA/beat" 2>/dev/null)
    sleep 3
    b2=$(cut -d ' ' -f 1 "$SA_DATA/beat" 2>/dev/null)
    [[ $b1 =~ ^[0-9]+$ && $b2 =~ ^[0-9]+$ ]] && ((b2 > b1)) || { _sa_fail 'heartbeatが更新されません'; return; }
    [[ $(_sa_prop $u ProtectSystem) == strict ]] || _sa_fail 'ProtectSystem=strict ではありません'
    v=$(_sa_prop $u ProtectHome)
    [[ -n $v && $v != no ]] || _sa_fail 'ProtectHomeが無効です'
    [[ $(_sa_prop $u PrivateTmp) == yes ]] || _sa_fail 'PrivateTmp=yes ではありません'
    [[ $(_sa_prop $u NoNewPrivileges) == yes ]] || _sa_fail 'NoNewPrivileges=yes ではありません'
    [[ $(_sa_prop $u ReadWritePaths) == *"$SA_DATA"* ]] || _sa_fail "ReadWritePathsに $SA_DATA がありません"
    [[ -n $(_sa_prop $u SystemCallFilter) ]] || _sa_fail 'SystemCallFilterがありません'
    caps=$(_sa_prop $u CapabilityBoundingSet)
    if [[ $caps == *cap_sys_admin* || $caps == *ffffffff* ]]; then _sa_fail 'CapabilityBoundingSetが絞られていません'; fi
    score=$(systemd-analyze security --no-pager $u 2>/dev/null | sed -n 's/.*[Oo]verall exposure level for [^:]*: *\([0-9][0-9.]*\).*/\1/p' | tail -1)
    [[ -n $score ]] || { _sa_fail 'systemd-analyze security のスコアを取得できません'; return; }
    awk -v s="$score" -v t="$SA_THRESHOLD" 'BEGIN{exit !(s<t)}' || _sa_fail "露出スコア $score が目標 $SA_THRESHOLD 未満ではありません"
}

lab_check() {
    _sa_paths || return 1
    [[ -f $LAB_STATE/owns-units && -f $LAB_STATE/broken ]] || { echo 'まずsetupとbreakを実行してください。'; return 1; }
    SA_FAILS=0
    systemctl daemon-reload
    _sa_check_socket
    _sa_check_template
    _sa_check_deps
    _sa_check_timer
    _sa_check_crash
    _sa_check_sandbox
    if ((SA_FAILS == 0)); then
        echo 'PASS: ソケット起動・テンプレート・依存・timer・再起動制限・サンドボックス(動作維持)を実状態で確認しました。'
        return 0
    fi
    return 1
}

lab_reset() {
    _sa_paths || return 1
    [[ -f $LAB_STATE/owns-units ]] || { echo 'この課題が作成したunitではありません。'; return 1; }
    local u inst
    systemctl stop dojo-adv-sock.socket dojo-adv-sock.service dojo-adv-a.service dojo-adv-b.service dojo-adv-c.service dojo-adv-cal.timer dojo-adv-cal.service dojo-adv-crash.service dojo-adv-data.service 2>/dev/null
    for inst in $(systemctl list-units --all --plain --no-legend 'dojo-adv-worker@*.service' 2>/dev/null | awk '{print $1}'); do
        if [[ $inst =~ ^dojo-adv-worker@[a-z0-9]+\.service$ ]]; then systemctl stop "$inst" 2>/dev/null; fi
    done
    systemctl disable dojo-adv-sock.socket dojo-adv-cal.timer 2>/dev/null
    for u in "${SA_UNITS[@]}"; do
        rm -f -- "${SA_UNITDIR:?}/${u:?}"
        rm -rf --one-file-system -- "${SA_UNITDIR:?}/${u:?}.d"
    done
    rm -f -- "${SA_LIB:?}"/dojo-adv-sock.py "${SA_LIB:?}"/dojo-adv-worker.sh "${SA_LIB:?}"/dojo-adv-data.py "${SA_LIB:?}"/dojo-adv-crash.sh
    rm -rf --one-file-system -- "${SA_DATA:?}" "${SA_RUN:?}"
    systemctl daemon-reload
    systemctl reset-failed 2>/dev/null
    rm -f -- "${LAB_STATE:?}"/owns-units "${LAB_STATE:?}"/broken "${LAB_STATE:?}"/crash.sha256 "${LAB_STATE:?}"/critical-chain.txt
    echo 'dojo-adv-* のunitと専用ディレクトリを削除しました。他のunitは変更していません。'
}
