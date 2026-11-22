# title: リソース制限（MemoryMax・LimitNOFILE）によるサービス障害の調査と修復
# roles: app
# Guest-only. Dedicated units, dedicated user, tiny (40MB / 200fd) allocations. No host execution.

_lim_paths() {
    [[ ${LAB_ID:-} == limits && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/limits ]] || { echo 'limits: unexpected lab context' >&2; return 1; }
    LIM_USER=dojo-limits
    LIM_MARK='# LinuxDOJO VM module: limits'
    LIM_UNITS=(dojo-limits-mem dojo-limits-fd)
    LIM_DIR=/etc/systemd/system
    [[ ! -L $LAB_STATE && ! -L $LIM_DIR/dojo-limits-mem.service && ! -L $LIM_DIR/dojo-limits-fd.service ]] || { echo 'limits: symlink refused' >&2; return 1; }
    local u
    for u in "${LIM_UNITS[@]}"; do
        if [[ -e $LIM_DIR/$u.service ]] && ! grep -qxF "$LIM_MARK" "$LIM_DIR/$u.service"; then
            echo 'limits: refusing to replace an unowned unit' >&2; return 1
        fi
    done
    if getent passwd "$LIM_USER" >/dev/null && [[ $(getent passwd "$LIM_USER" | cut -d: -f5) != 'LinuxDOJO limits lab' ]]; then
        echo 'limits: refusing an unowned user' >&2; return 1
    fi
}

# $1 mem|fd  $2 MemoryMax  $3 LimitNOFILE
_lim_write_unit() {
    local kind=$1 mem=$2 nofile=$3 desc
    if [[ $kind == mem ]]; then desc='LinuxDOJO limits lab memory worker'; else desc='LinuxDOJO limits lab file-descriptor worker'; fi
    cat > "$LIM_DIR/dojo-limits-$kind.service" <<UNIT
$LIM_MARK
[Unit]
Description=$desc
StartLimitIntervalSec=0
[Service]
Type=simple
User=$LIM_USER
ExecStart=/usr/bin/python3 $LAB_STATE/app.py $kind
RuntimeDirectory=dojo-limits-$kind
Restart=always
RestartSec=2
MemoryMax=$mem
TasksMax=32
CPUQuota=20%
LimitNOFILE=$nofile
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
UNIT
}

_lim_hash_units() {
    (cd "$LIM_DIR" && sha256sum dojo-limits-mem.service dojo-limits-fd.service) > "$LAB_STATE/units.sha256"
    sha256sum "$LAB_STATE/app.py" >> "$LAB_STATE/units.sha256"
}

_lim_clear_dropins() {
    local u
    for u in "${LIM_UNITS[@]}"; do
        rm -rf -- "${LIM_DIR:?}/${u:?}.service.d"
    done
}

lab_setup() {
    _lim_paths || return 1
    getent passwd "$LIM_USER" >/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin --comment 'LinuxDOJO limits lab' "$LIM_USER"
    chmod 0755 "$LAB_ROOT" "$LAB_ROOT/state"
    install -d -m 0755 "$LAB_STATE"
    cat > "$LAB_STATE/app.py" <<'PY'
import os, sys, time
kind = sys.argv[1]
status = '/run/dojo-limits-%s/status' % kind
def publish(line):
    tmp = status + '.tmp'
    with open(tmp, 'w') as f:
        f.write(line + '\n')
    os.replace(tmp, status)
if kind == 'mem':
    size = 40 * 1024 * 1024
    buf = bytearray(size)
    for i in range(0, size, 4096):
        buf[i] = 1
    line = 'mem-ok 40MB pid=%d' % os.getpid()
elif kind == 'fd':
    held = [os.open('/etc/hostname', os.O_RDONLY) for _ in range(200)]
    line = 'fd-ok 200 pid=%d' % os.getpid()
else:
    raise SystemExit('unknown kind')
while True:
    publish(line)
    time.sleep(1)
PY
    chmod 0644 "$LAB_STATE/app.py"
    _lim_write_unit mem 128M 1024
    _lim_write_unit fd 128M 1024
    systemctl daemon-reload
    systemctl restart dojo-limits-mem.service dojo-limits-fd.service
    cat > "$LAB_STATE/TASKS.txt" <<EOF
dojo-limits-mem.service と dojo-limits-fd.service が対象です（実行ユーザー $LIM_USER、メモリは 40MB 程度のみ使用）。
1. dojo-vm-lab limits break を実行すると 2 つのサービスが異常になります。
2. 原因調査のヒント:
   - systemctl show -p Result,ExitCode,NRestarts,MemoryMax,LimitNOFILE <unit>
   - journalctl -u <unit> と journalctl -k（カーネルの OOM 記録）
   - /sys/fs/cgroup/system.slice/<unit>.service/ の memory.max と memory.events
   - 動いている間の cat /proc/<PID>/limits
3. 修復は元ユニットを編集せず、ドロップイン（systemctl edit <unit> 相当 /etc/systemd/system/<unit>.service.d/*.conf）で行います。
   上限を外す（infinity）のではなく、アプリが必要とする量に見合う妥当な値へ引き上げてください。
4. systemctl daemon-reload のあと restart し、安定して動くことを確認してから dojo-vm-lab limits check を実行します。
EOF
    echo 'setup complete; read the module TASKS.txt and run break'
}

lab_break() {
    _lim_paths || return 1
    [[ -f $LAB_STATE/app.py ]] || { echo 'run setup first' >&2; return 1; }
    systemctl stop dojo-limits-mem.service dojo-limits-fd.service 2>/dev/null || true
    _lim_clear_dropins
    _lim_write_unit mem 16M 1024
    _lim_write_unit fd 128M 64
    _lim_hash_units
    systemctl daemon-reload
    systemctl reset-failed dojo-limits-mem.service dojo-limits-fd.service 2>/dev/null || true
    touch "$LAB_STATE/broken-at"
    systemctl start dojo-limits-mem.service dojo-limits-fd.service || true
    echo 'Both services now misbehave (restart loops). Investigate, fix with drop-ins, then run check.'
}

_lim_prop() { systemctl show -p "$2" --value "$1.service"; }

_lim_check_unit() {
    local kind=$1 u=dojo-limits-$1 pid1 pid2 n1 n2 mem cg line nofile lim age
    local hdir=$LIM_DIR/$u.service.d
    compgen -G "$hdir/*.conf" >/dev/null || { echo "$u: put the fix in a drop-in under $hdir" >&2; return 1; }
    [[ $(_lim_prop "$u" FragmentPath) == "$LIM_DIR/$u.service" ]] || { echo "$u: unexpected unit" >&2; return 1; }
    [[ $(_lim_prop "$u" User) == "$LIM_USER" ]] || { echo "$u: User must stay $LIM_USER" >&2; return 1; }
    _lim_prop "$u" ExecStart | grep -qF "path=/usr/bin/python3 ; argv[]=/usr/bin/python3 $LAB_STATE/app.py $kind ;" || { echo "$u: ExecStart must stay unchanged" >&2; return 1; }
    [[ $(_lim_prop "$u" ActiveState) == active && $(_lim_prop "$u" SubState) == running ]] || { echo "$u: service is not running" >&2; return 1; }
    mem=$(_lim_prop "$u" MemoryMax)
    [[ $mem =~ ^[0-9]+$ ]] || { echo "$u: MemoryMax must remain a finite cap" >&2; return 1; }
    (( mem >= 100*1024*1024 && mem <= 512*1024*1024 )) || { echo "$u: MemoryMax must be a sane finite value (100M-512M)" >&2; return 1; }
    [[ $(_lim_prop "$u" TasksMax) =~ ^[0-9]+$ ]] || { echo "$u: TasksMax cap must remain" >&2; return 1; }
    [[ $(_lim_prop "$u" CPUQuotaPerSecUSec) != infinity ]] || { echo "$u: CPUQuota cap must remain" >&2; return 1; }
    nofile=$(_lim_prop "$u" LimitNOFILE)
    if ! [[ $nofile =~ ^[0-9]+$ ]] || (( nofile < 256 || nofile > 1048576 )); then
        echo "$u: LimitNOFILE must be a finite value of at least 256" >&2; return 1
    fi
    pid1=$(_lim_prop "$u" MainPID); n1=$(_lim_prop "$u" NRestarts)
    [[ $pid1 =~ ^[1-9][0-9]*$ ]] || { echo "$u: no main process" >&2; return 1; }
    sleep 8
    pid2=$(_lim_prop "$u" MainPID); n2=$(_lim_prop "$u" NRestarts)
    [[ $pid1 == "$pid2" && $n1 == "$n2" ]] || { echo "$u: still restarting; it must stay up without new restarts" >&2; return 1; }
    [[ $(_lim_prop "$u" ActiveState) == active ]] || { echo "$u: not active" >&2; return 1; }
    lim=$(awk -F'  +' '/^Max open files/ {print $2}' "/proc/$pid2/limits" 2>/dev/null)
    [[ $lim =~ ^[0-9]+$ ]] && (( lim >= 256 )) || { echo "$u: live process open-files limit too small" >&2; return 1; }
    cg=$(_lim_prop "$u" ControlGroup)
    [[ $(cat "/sys/fs/cgroup$cg/memory.max" 2>/dev/null) == "$mem" ]] || { echo "$u: cgroup memory.max does not match the effective cap" >&2; return 1; }
    line=$(cat "/run/$u/status" 2>/dev/null) || { echo "$u: application output missing" >&2; return 1; }
    [[ $line == "$kind-ok "*" pid=$pid2" ]] || { echo "$u: application is not serving its output" >&2; return 1; }
    age=$(( $(date +%s) - $(stat -c %Y "/run/$u/status") ))
    (( age <= 5 )) || { echo "$u: application output is stale" >&2; return 1; }
}

lab_check() {
    _lim_paths || return 1
    [[ -f $LAB_STATE/broken-at && -f $LAB_STATE/units.sha256 ]] || { echo 'run break, investigate, and repair first' >&2; return 1; }
    sha256sum -c --quiet <(sed "s# dojo-limits# $LIM_DIR/dojo-limits#" "$LAB_STATE/units.sha256") >/dev/null 2>&1 || { echo 'base unit files and app.py must not be edited; use drop-ins' >&2; return 1; }
    local k
    for k in mem fd; do _lim_check_unit "$k" || return 1; done
    echo 'PASS: both services run stably with sane finite MemoryMax and LimitNOFILE set through drop-ins'
}

lab_reset() {
    _lim_paths || return 1
    local u
    for u in "${LIM_UNITS[@]}"; do
        if [[ -f $LIM_DIR/$u.service ]]; then
            systemctl stop "$u.service" 2>/dev/null || true
            rm -f -- "${LIM_DIR:?}/${u:?}.service"
            systemctl reset-failed "$u.service" 2>/dev/null || true
        fi
    done
    _lim_clear_dropins
    systemctl daemon-reload
    if getent passwd "$LIM_USER" >/dev/null; then userdel "$LIM_USER" 2>/dev/null || true; fi
    rm -rf -- "${LAB_STATE:?}"
    echo 'Only limits module units, drop-ins, user and state were removed'
}
