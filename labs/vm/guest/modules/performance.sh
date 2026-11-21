# LinuxDOJO VM module: performance
# title: 実測とサービス設定の故障調査
# Sourced only by the guarded dojo-vm-lab dispatcher. No host execution.
_perf_require() {
    [ "${LAB_VM_ROLE:-}" = app ] || { echo 'performance is an app VM exercise' >&2; return 1; }
    [ "${LAB_STATE:-}" = "${LAB_ROOT:-}/state/performance" ] && [ "${LAB_ROOT:-}" = /var/lib/linuxdojo-vm-lab ] || return 1
    [ ! -L "$LAB_STATE" ] || { echo 'module state must not be a symlink' >&2; return 1; }
    if [ -e /etc/systemd/system/dojo-performance.service ]; then
        grep -qx '# LinuxDOJO VM module: performance' /etc/systemd/system/dojo-performance.service || {
            echo 'refusing to replace an unowned unit' >&2; return 1;
        }
    fi
}
lab_setup() {
    _perf_require || return 1
    chmod 0755 "$LAB_ROOT" "$LAB_ROOT/state"
    install -d -m 0755 "$LAB_STATE"
    install -d -m 0700 "$LAB_STATE/evidence"
    printf 'id,work\n1,small\n' > "$LAB_STATE/input.csv"
    cat > "$LAB_STATE/toy_worker.py" <<'PY'
import json
from pathlib import Path
import sys
import time
root = Path(__file__).resolve().parent
config = json.loads((root / 'config.json').read_text())
source = Path(config['input'])
if source.parent != root or source.name not in ('input.csv', 'missing.csv'):
    raise SystemExit('fixture input must remain within this module')
print(source.read_text().splitlines()[0], flush=True)
if '--once' not in sys.argv:
    # Small finite work with sleeps: this is measurement practice, not stress.
    for _ in range(1200):
        sum(range(20000))
        time.sleep(0.1)
PY
    python3 - "$LAB_STATE" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
(root/'config.json').write_text(json.dumps({'input':str(root/'input.csv')}))
PY
    chmod 0644 "$LAB_STATE/input.csv" "$LAB_STATE/config.json" "$LAB_STATE/toy_worker.py"
    cat > /etc/systemd/system/dojo-performance.service <<EOF
# LinuxDOJO VM module: performance
[Unit]
Description=LinuxDOJO bounded observation worker
[Service]
Type=simple
User=nobody
ExecStart=/usr/bin/python3 $LAB_STATE/toy_worker.py
RuntimeMaxSec=180
Restart=no
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl restart dojo-performance.service
    cat > "$LAB_STATE/TASKS.txt" <<EOF
This is a disposable VM exercise; only dojo-performance.service and $LAB_STATE are targets.
1. Run dojo-vm-lab performance break to create a missing-input failure.
2. Read systemctl status dojo-performance.service and journalctl -u dojo-performance.service.
3. Before repair, record openat calls with:
   strace -e trace=openat -o $LAB_STATE/evidence/before.strace python3 $LAB_STATE/toy_worker.py --once
   This command is expected to fail. ENOENT is different from EACCES.
4. Fix config.json to use $LAB_STATE/input.csv, preserving the input.
5. Restart dojo-performance.service. Capture live samples:
   vmstat 1 3 > $LAB_STATE/evidence/vmstat.txt
   systemctl status dojo-performance.service > $LAB_STATE/evidence/service.txt
6. Run dojo-vm-lab performance check while the bounded worker is active.
The worker expires after180 seconds. Restart it if needed. High CPU or I/O failure is not deliberately generated.
EOF
    printf '%s\n' 'setup complete; read the module TASKS.txt and run break'
}
lab_break() {
    _perf_require || return 1
    [ -f "$LAB_STATE/toy_worker.py" ] || { echo 'run setup first' >&2; return 1; }
    python3 - "$LAB_STATE" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); (root/'config.json').write_text(json.dumps({'input':str(root/'missing.csv')}))
PY
    rm -f "$LAB_STATE/evidence/before.strace" "$LAB_STATE/evidence/vmstat.txt" "$LAB_STATE/evidence/service.txt"
    touch "$LAB_STATE/broken-at"
    systemctl restart dojo-performance.service || true
    echo 'Known module input failure created. Inspect the service and trace before repairing.'
}
lab_check() {
    _perf_require || return 1
    [ -f "$LAB_STATE/broken-at" ] || { echo 'run break, investigate, and repair first' >&2; return 1; }
    python3 - "$LAB_STATE" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); value=json.loads((root/'config.json').read_text())
assert value == {'input':str(root/'input.csv')}, 'restore the intended input path'
assert (root/'input.csv').read_text() == 'id,work\n1,small\n', 'preserve original input'
trace=(root/'evidence/before.strace').read_text()
assert str(root/'missing.csv') in trace and 'ENOENT' in trace, 'capture the missing-input observation'
sample=(root/'evidence/vmstat.txt').read_text()
assert 'procs' in sample and 'swpd' in sample and len(sample.splitlines()) >= 5, 'capture live vmstat samples'
assert 'active (running)' in (root/'evidence/service.txt').read_text(), 'save the running service status'
for name in ('before.strace','vmstat.txt','service.txt'):
    assert (root/'evidence'/name).stat().st_mtime >= (root/'broken-at').stat().st_mtime, 'collect this exercise evidence after break'
PY
    systemctl is-active --quiet dojo-performance.service || { echo 'worker must be running after repair' >&2; return 1; }
    echo 'PASS: observed missing input, repaired config, and captured live process/system evidence'
}
lab_reset() {
    _perf_require || return 1
    if [ -f /etc/systemd/system/dojo-performance.service ]; then
        systemctl stop dojo-performance.service
        rm /etc/systemd/system/dojo-performance.service
        systemctl daemon-reload
        systemctl reset-failed dojo-performance.service 2>/dev/null || true
    fi
    rm -rf -- "$LAB_STATE"
    echo 'Only performance module state and its unit were removed'
}
