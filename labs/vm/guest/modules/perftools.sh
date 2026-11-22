#!/bin/bash
# title: vmstat/iostat/pidstat/ss/lsofで既知の負荷を実測する
# roles: app
# Guest-only. Starts bounded (900s) lab processes tagged with $LAB_STATE/load.py; reset kills only those.

_pt_ctx() {
    if [[ ${LAB_ID:-} != perftools || ${LAB_VM_ROLE:-} != app || ${LAB_STATE:-} != /var/lib/linuxdojo-vm-lab/state/perftools || ${LAB_ROOT:-} != /var/lib/linuxdojo-vm-lab ]]; then
        echo 'perftools: unexpected lab context' >&2; return 1
    fi
    [[ ! -L $LAB_STATE ]] || { echo 'perftools: unexpected lab context' >&2; return 1; }
}

_pt_missing() {
    local t missing=0
    for t in vmstat iostat sar mpstat pidstat lsof ss free top ps python3; do
        command -v "$t" >/dev/null 2>&1 || { echo "missing tool: $t" >&2; missing=1; }
    done
    return $missing
}

# Kill only processes whose pidfile AND cmdline both prove they belong to this lab.
_pt_kill() {
    local f pid
    [[ -d $LAB_STATE/pids ]] || return 0
    for f in "$LAB_STATE"/pids/*.pid; do
        [[ -f $f ]] || continue
        pid=$(cat "$f" 2>/dev/null) || continue
        [[ $pid =~ ^[0-9]+$ ]] || continue
        if [[ -r /proc/$pid/cmdline ]] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -qF "$LAB_STATE/load.py"; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    sleep 0.5
    rm -rf -- "$LAB_STATE/pids"
}

lab_setup() {
    _pt_ctx || return 1
    if ! _pt_missing; then
        echo '計測ツールが足りません。次を実行してから再度 setup してください:' >&2
        echo 'sudo apt-get install -y sysstat procps lsof iproute2' >&2
        return 1
    fi
    install -d -m 0700 "$LAB_STATE"
    cat > "$LAB_STATE/load.py" <<'PY'
import os, socket, sys, time
# usage: load.py ROLE SECONDS STATE [ARGS...]   (bounded lab load, never exceeds SECONDS)
role, seconds, state = sys.argv[1], int(sys.argv[2]), sys.argv[3]
args = sys.argv[4:]
deadline = time.time() + seconds
with open('%s/pids/%s.pid' % (state, role), 'w') as f:
    f.write(str(os.getpid()))
if role == 'cpu':
    x = 1
    while time.time() < deadline:
        for _ in range(200000):
            x = (x * 3 + 1) % 1000003
elif role == 'tick':
    while time.time() < deadline:
        sum(range(20000)); time.sleep(0.5)
elif role == 'disk':
    fd = os.open(state + '/disk.dat', os.O_WRONLY | os.O_CREAT, 0o600)
    chunk = b'd' * 32768
    rate = int(args[0]) * 1024
    off = sent = 0
    t0 = time.time()
    while time.time() < deadline:
        os.pwrite(fd, chunk, off); os.fsync(fd)
        off = (off + 32768) % (16 * 1048576); sent += 32768
        delay = t0 + sent / rate - time.time()
        if delay > 0:
            time.sleep(delay)
elif role == 'mem':
    block = bytearray(b'm') * (int(args[0]) * 1048576)
    while time.time() < deadline:
        time.sleep(1)
elif role == 'fd':
    held = [open(os.devnull) for _ in range(int(args[0]))]
    while time.time() < deadline:
        time.sleep(1)
elif role == 'net':
    count, port = int(args[0]), int(args[1])
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', port)); srv.listen(64)
    held = []
    for _ in range(count):
        c = socket.create_connection(('127.0.0.1', port)); a, _ = srv.accept(); held += [c, a]
    while time.time() < deadline:
        time.sleep(1)
PY
    chmod 0600 "$LAB_STATE/load.py"
    cat > "$LAB_STATE/TASKS.txt" <<EOF2
このVMで既知の負荷プロセスを実測する練習です。対象は $LAB_STATE/load.py 配下の実習プロセスだけです。
1. sudo dojo-vm-lab perftools break で負荷を起動します(PIDと大きさは毎回ランダム、900秒で自動終了)。
2. 次のツールで観察します: vmstat 1 5 / mpstat -P ALL 1 3 / pidstat 1 3 / pidstat -d 1 3 / iostat -x 1 3 /
   sar -u 1 3 / free -m / ss -s / ss -ltnp / lsof -p PID / top -b -n1 / ps -eo pid,pcpu,rss,cmd --sort=-pcpu / cat /proc/PID/status
   実習プロセスは ps -eo pid,pcpu,rss,args | grep load.py で見つかります(roleは引数で分かります)。
3. $LAB_STATE/answers.txt に key=value で書きます(break後に更新したものだけ有効):
   cpu_pid        CPUを使い続けているプロセス
   writer_pid / write_kb_s   fsync付きで書き込んでいるプロセスとその書き込み速度(KiB/s)
   holder_pid / holder_rss_kb   メモリを保持しているプロセスのRSS(kB)
   fd_pid / fd_count            ファイルを大量に開いているプロセスとfd数
   listener_pid / conn_count    TCP待受プロセスと、その待受ポートのESTABLISHED接続数
4. sudo dojo-vm-lab perftools check で、その場の実測値(/proc, ss)と照合します(誤差あり)。古い数字は不合格です。
EOF2
    cat "$LAB_STATE/TASKS.txt"
    echo 'setup complete'
}

lab_break() {
    _pt_ctx || return 1
    _pt_missing || { echo 'sudo apt-get install -y sysstat procps lsof iproute2' >&2; return 1; }
    [[ -f $LAB_STATE/load.py ]] || { echo 'run setup first' >&2; return 1; }
    _pt_kill
    install -d -m 0700 "$LAB_STATE/pids"
    rm -f -- "$LAB_STATE/answers.txt" "$LAB_STATE/started" "$LAB_STATE/disk.dat"
    local rate=$((256 * (RANDOM % 4 + 1))) mem=$((40 + 8 * (RANDOM % 5))) fdn=$((150 + RANDOM % 101))
    local conns=$((7 + RANDOM % 17)) port=$((20000 + RANDOM % 20000)) secs=900 role
    local -A extra=([cpu]= [tick]= [disk]=$rate [mem]=$mem [fd]=$fdn [net]="$conns $port")
    for role in cpu tick disk mem fd net; do
        # shellcheck disable=SC2086
        setsid nohup python3 "$LAB_STATE/load.py" "$role" "$secs" "$LAB_STATE" ${extra[$role]} </dev/null >/dev/null 2>&1 &
    done
    local i
    for i in $(seq 1 50); do
        [[ $(find "$LAB_STATE/pids" -name '*.pid' -size +0 2>/dev/null | wc -l) -ge 6 ]] && break
        sleep 0.2
    done
    sleep 1
    cat > "$LAB_STATE/answers.txt" <<'EOF2'
cpu_pid=
writer_pid=
write_kb_s=
holder_pid=
holder_rss_kb=
fd_pid=
fd_count=
listener_pid=
conn_count=
EOF2
    sleep 0.2
    touch "$LAB_STATE/started"
    echo "負荷を起動しました(900秒で終了)。TASKS.txt の手順で測定し answers.txt を埋めてください。"
}

lab_check() {
    _pt_ctx || return 1
    [[ -f $LAB_STATE/started ]] || { echo 'run break and measure first' >&2; return 1; }
    python3 - "$LAB_STATE" <<'PY'
import os, subprocess, sys, time
from pathlib import Path
state = Path(sys.argv[1])
fail = []
def bad(msg): fail.append(msg)
procs = {}
for role in ('cpu', 'tick', 'disk', 'mem', 'fd', 'net'):
    try:
        pid = int((state / 'pids' / (role + '.pid')).read_text().strip())
        cmd = Path('/proc/%d/cmdline' % pid).read_bytes().split(b'\0')
        if len(cmd) < 3 or cmd[1].decode() != str(state / 'load.py') or cmd[2].decode() != role:
            raise ValueError
        procs[role] = (pid, [c.decode() for c in cmd[5:] if c])
    except Exception:
        bad('lab process "%s" is not running (it expires after 900s); run break again' % role)
if fail:
    print('FAIL: ' + '; '.join(fail), file=sys.stderr); sys.exit(1)
started = (state / 'started').stat().st_mtime_ns
ansf = state / 'answers.txt'
if not ansf.exists() or ansf.stat().st_mtime_ns <= started:
    print('FAIL: answers.txt was not updated after break (stale answers)', file=sys.stderr); sys.exit(1)
ans = {}
for line in ansf.read_text().splitlines():
    k, _, v = line.partition('=')
    ans[k.strip()] = v.strip()
def num(key):
    try: return int(ans.get(key, ''))
    except ValueError:
        bad('%s must be an integer' % key); return None
def cpu_ticks(pid):
    f = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
    return int(f[11]) + int(f[12])
def io_write(pid):
    for line in Path('/proc/%d/io' % pid).read_text().splitlines():
        if line.startswith('write_bytes:'): return int(line.split()[1])
# Two live samples
t0 = time.time()
ticks0 = {r: cpu_ticks(p[0]) for r, p in procs.items()}
w0 = io_write(procs['disk'][0])
time.sleep(3)
dt = time.time() - t0
ticks1 = {r: cpu_ticks(p[0]) for r, p in procs.items()}
w1 = io_write(procs['disk'][0])
hz = os.sysconf('SC_CLK_TCK')
use = {r: (ticks1[r] - ticks0[r]) / hz / dt for r in procs}
# cpu hog
top = max(use, key=use.get)
if top != 'cpu' or use['cpu'] < 0.5:
    bad('lab CPU burner is not running hot (measured %.2f cores)' % use['cpu'])
v = num('cpu_pid')
if v is not None and v != procs['cpu'][0]: bad('cpu_pid is not the CPU hog')
# disk
rate = int(procs['disk'][1][0])
live = (w1 - w0) / 1024 / dt
if not (0.5 * rate <= live <= 1.5 * rate): bad('writer is not at its expected rate (live %.0f KiB/s)' % live)
v = num('writer_pid')
if v is not None and v != procs['disk'][0]: bad('writer_pid is not the fsync writer')
v = num('write_kb_s')
if v is not None and not (0.7 * live <= v <= 1.3 * live) and not (0.75 * rate <= v <= 1.25 * rate):
    bad('write_kb_s is outside the tolerated band; measure with pidstat -d / iostat -x')
# memory
pid = procs['mem'][0]
rss = int([l for l in Path('/proc/%d/status' % pid).read_text().splitlines() if l.startswith('VmRSS:')][0].split()[1])
v = num('holder_pid')
if v is not None and v != pid: bad('holder_pid is not the memory holder')
v = num('holder_rss_kb')
if v is not None and abs(v - rss) > 0.1 * rss: bad('holder_rss_kb differs from live VmRSS by more than 10%')
# fds
pid = procs['fd'][0]
n = len(os.listdir('/proc/%d/fd' % pid))
v = num('fd_pid')
if v is not None and v != pid: bad('fd_pid is not the fd holder')
v = num('fd_count')
if v is not None and abs(v - n) > 5: bad('fd_count differs from live /proc/PID/fd by more than 5')
# connections
pid = procs['net'][0]
port = procs['net'][1][1]
out = subprocess.run(['ss', '-Htn', 'state', 'established', 'sport', '=', ':' + port], capture_output=True, text=True).stdout
conns = len([l for l in out.splitlines() if l.strip()])
v = num('listener_pid')
if v is not None and v != pid: bad('listener_pid is not the TCP listener')
v = num('conn_count')
if v is not None and v != conns: bad('conn_count must equal the live ESTABLISHED connections to the listener port')
if fail:
    print('FAIL: ' + '; '.join(fail), file=sys.stderr); sys.exit(1)
print('PASS: all measurements match live /proc and ss values')
PY
}

lab_reset() {
    _pt_ctx || return 1
    _pt_kill
    rm -rf -- "$LAB_STATE"
    echo 'perftools: removed only its own processes and state'
}
