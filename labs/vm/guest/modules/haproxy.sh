# title: HAProxy リバースプロキシ・負荷分散・ヘルスチェック・ACL・stats socket
# roles: app
# Guest-only. Dedicated HAProxy instance (own config/unit, 127.0.0.1:8090) and two python backends (18101/18102).
# The distro's own haproxy.service and /etc/haproxy are never touched.

_hp_paths() {
    [[ ${LAB_ID:-} == haproxy && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/haproxy ]] || { echo 'haproxy: unexpected lab context' >&2; return 1; }
    HP_DIR=/etc/dojo-haproxy
    HP_CFG=$HP_DIR/haproxy.cfg
    HP_LIB=/usr/local/lib/dojo-haproxy
    HP_UNIT=/etc/systemd/system/dojo-haproxy.service
    HP_B1=/etc/systemd/system/dojo-backend-1.service
    HP_B2=/etc/systemd/system/dojo-backend-2.service
    [[ ! -L $HP_DIR && ! -L $HP_LIB && ! -L $HP_UNIT && ! -L $HP_B1 && ! -L $HP_B2 ]] || return 1
}

_hp_sock() {   # path of the learner's stats socket, parsed from the config
    sed -n 's/^[[:space:]]*stats[[:space:]]\+socket[[:space:]]\+\([^[:space:]]\+\).*/\1/p' "$HP_CFG" | head -n 1
}

lab_setup() {
    _hp_paths || return 1
    local hp
    hp=$(command -v haproxy) || {
        echo 'haproxyが入っていません。次を実行してから、もう一度setupしてください:'
        echo '  sudo apt-get install -y haproxy'
        return 1
    }
    command -v python3 >/dev/null && command -v systemctl >/dev/null || return 1
    [[ ! -e $HP_DIR && ! -e $HP_LIB && ! -e $HP_UNIT && ! -e $HP_B1 && ! -e $HP_B2 && ! -e $LAB_STATE/owns-lab ]] || { echo '専用構成が既にあります。上書きしません。'; return 1; }
    local p
    for p in 8090 18101 18102; do
        if ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN; then echo "ポート $p は使用中です。"; return 1; fi
    done
    touch "$LAB_STATE/owns-lab"
    install -d -m 0755 "$HP_LIB" "$HP_DIR"
    cat > "$HP_LIB/backend.py" <<'PY'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
name, port = sys.argv[1], int(sys.argv[2])
class H(BaseHTTPRequestHandler):
    def _send(self, head):
        body = b'ok\n' if self.path == '/health' else ('backend=%s path=%s host=%s\n' % (name, self.path, self.headers.get('Host', ''))).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Backend', name)
        self.end_headers()
        if not head:
            self.wfile.write(body)
    def do_GET(self): self._send(False)
    def do_HEAD(self): self._send(True)
    def do_OPTIONS(self): self._send(True)
    def log_message(self, *a): pass
ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
PY
    local i
    for i in 1 2; do
        cat > "/etc/systemd/system/dojo-backend-$i.service" <<UNIT
[Unit]
Description=LinuxDOJO HAProxy exercise backend app$i
[Service]
User=nobody
ExecStart=/usr/bin/python3 $HP_LIB/backend.py app$i 1810$i
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    done
    cat > "$HP_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated HAProxy exercise
After=network.target dojo-backend-1.service dojo-backend-2.service
[Service]
Type=notify
RuntimeDirectory=dojo-haproxy
ExecStart=$hp -Ws -f $HP_CFG
ExecReload=$hp -Ws -f $HP_CFG -c -q
ExecReload=/bin/kill -USR2 \$MAINPID
KillMode=mixed
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    cat > "$HP_DIR/haproxy.cfg.example" <<'EX'
# 書き方の見出しだけのひな形。haproxy.cfg を自分で書く(このファイルは動作しません)。
# global   : stats socket /run/dojo-haproxy/admin.sock mode 660 level admin
# defaults : mode http / timeout connect / timeout client / timeout server
# frontend : bind 127.0.0.1:8090 / acl / use_backend / default_backend
# backend  : balance roundrobin / option httpchk / server ... check
EX
    sha256sum "$HP_UNIT" "$HP_B1" "$HP_B2" "$HP_LIB/backend.py" > "$LAB_STATE/files.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-backend-1.service dojo-backend-2.service
    cat > "$LAB_STATE/TASKS.txt" <<'TASK'
HAProxy実習（専用インスタンス。OS標準の haproxy.service / /etc/haproxy は使いません）
用意済み: バックエンド2つ(自分の名前を返す) 127.0.0.1:18101 (app1) / 127.0.0.1:18102 (app2)
  curl http://127.0.0.1:18101/ と 18102 で応答を確認。ヘルス用に /health も200を返す。
自分で書く: /etc/dojo-haproxy/haproxy.cfg  (見出しだけのひな形: haproxy.cfg.example)
 1. global に stats socket /run/dojo-haproxy/admin.sock mode 660 level admin
    defaults に mode http と timeout connect / client / server (全て設定)
 2. frontend は 127.0.0.1:8090 で待ち受ける。
 3. 既定のbackend(web): 18101と18102を balance roundrobin、option httpchk(GET /health)、各serverに check
    (check の inter / fall / rise を短めにして故障検知を早める)
 4. ACLで振り分け:
      パスが /api で始まる      -> app2(18102)だけのbackend
      Hostが admin.dojo.test    -> app1(18101)だけのbackend
    (それ以外はweb)。確認: curl -H 'Host: admin.dojo.test' http://127.0.0.1:8090/
 5. 検証して起動: haproxy -c -f /etc/dojo-haproxy/haproxy.cfg
    sudo systemctl enable --now dojo-haproxy ; 設定変更後は systemctl reload dojo-haproxy
 6. 20回 curl して分散を数える。stats socket: echo 'show servers state' | nc -U /run/dojo-haproxy/admin.sock
    (ncが無ければ python3 の socket でも可)
 7. sudo dojo-vm-lab haproxy break
    (server行のポート誤り・timeout欠落・checkが外れて死んだbackendが残る) 症状を curl -i と
    haproxy -c の警告、show servers state から調べて設定を直す。
 8. sudo dojo-vm-lab haproxy check
    (ラウンドロビン分散・ACL・片方のbackendを停止して自動切り離し/復旧を実際のHTTPで確認。
     checkがbackendの停止と再起動を行います)
 9. 終了後 sudo dojo-vm-lab haproxy reset
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudo cat で表示)"
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _hp_paths || return 1
    [[ -f $LAB_STATE/owns-lab && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで、未breakのときだけ実行できます。'; return 1; }
    [[ -f $HP_CFG ]] || { echo '先に haproxy.cfg を書きます。'; return 1; }
    haproxy -c -q -f "$HP_CFG" 2>/dev/null || { echo '先に haproxy -c が通る設定にします。'; return 1; }
    systemctl is-active --quiet dojo-haproxy.service || { echo '先に dojo-haproxy を起動します。'; return 1; }
    install -m 0600 "$HP_CFG" "$LAB_STATE/good.cfg"
    python3 - "$HP_CFG" <<'PY' || { echo 'server行(:18102)・timeout・checkのいずれかが見つからず、故障を作れません。'; return 1; }
import os, re, sys
path = sys.argv[1]
lines = open(path).read().splitlines()
out, port_done, timeouts, checks = [], False, 0, 0
for line in lines:
    s = line.strip()
    if re.match(r'timeout\s', s):
        timeouts += 1
        continue
    if s.startswith('server ') or s.startswith('server\t'):
        new = re.sub(r'(?<=\s)check(?=\s|$)', '', line)
        if new != line: checks += 1
        line = new
        if not port_done and ':18102' in line:
            line, port_done = line.replace(':18102', ':18120', 1), True
    out.append(line)
if not (port_done and timeouts and checks):
    sys.exit(1)
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    f.write('\n'.join(out) + '\n')
os.replace(tmp, path)
PY
    systemctl stop dojo-backend-1.service
    systemctl restart dojo-haproxy.service || true
    touch "$LAB_STATE/fault"
    echo '故障を入れました(backend1は停止中)。curl -i http://127.0.0.1:8090/ と haproxy -c -f の警告、stats socketで調べて直します。'
}

lab_check() {
    _hp_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで障害を作り、直してから実行します。'; return 1; }
    sha256sum -c --quiet "$LAB_STATE/files.sha256" >/dev/null 2>&1 || { echo '専用のunit・バックエンドは変更せず、haproxy.cfgだけを直します。'; return 1; }
    local out
    out=$(haproxy -c -f "$HP_CFG" 2>&1) || { echo 'haproxy -c が失敗します:'; echo "$out"; return 1; }
    if grep -qi 'missing timeouts' <<<"$out"; then echo 'timeoutが不足しています(haproxy -cの警告)。connect/client/serverを設定します。'; return 1; fi
    systemctl is-active --quiet dojo-haproxy.service || { echo 'dojo-haproxy が動いていません。'; return 1; }
    local sock
    sock=$(_hp_sock)
    [[ -n $sock && $sock == /run/dojo-haproxy/* ]] || { echo 'globalに stats socket /run/dojo-haproxy/admin.sock ... を設定します。'; return 1; }
    local rc=0
    HP_SOCK=$sock python3 - <<'PY' || rc=$?
import collections, http.client, os, socket, subprocess, sys, time
sock_path = os.environ['HP_SOCK']
def bad(msg):
    print(msg); sys.exit(1)
def get(path='/', host='www.dojo.test'):
    try:
        c = http.client.HTTPConnection('127.0.0.1', 8090, timeout=3)
        c.request('GET', path, headers={'Host': host})
        r = c.getresponse(); body = r.read().decode(errors='replace')
        c.close()
        return r.status, (body.split('backend=')[1].split()[0] if r.status == 200 and 'backend=' in body else '')
    except Exception:
        return 0, ''
def servers():
    s = socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect(sock_path)
    s.sendall(b'show servers state\n'); data = b''
    while True:
        chunk = s.recv(65536)
        if not chunk: break
        data += chunk
    s.close()
    cols, rows = None, []
    for line in data.decode().splitlines():
        if line.startswith('#'):
            cols = line.lstrip('# ').split(); continue
        f = line.split()
        if cols and len(f) >= len(cols): rows.append(dict(zip(cols, f)))
    return rows
def state(port):   # op_state of every server entry pointing at the backend port
    return [r['srv_op_state'] for r in servers() if r.get('srv_port') == str(port)]
def units(action):
    subprocess.run(['systemctl', action, 'dojo-backend-1.service'], check=False)
def wait(fn, secs):
    end = time.time() + secs
    while time.time() < end:
        if fn(): return True
        time.sleep(0.5)
    return False
def restore():
    subprocess.run(['systemctl', 'start', 'dojo-backend-1.service', 'dojo-backend-2.service'], check=False)
try:
    restore()
    if not wait(lambda: get('/')[0] == 200 and get('/')[1] != '' and set(state(18101) + state(18102)) == {'2'}, 30):
        bad('両backendを起動しても、プロキシのserverがUP(op_state 2)になりません。ポート・check・stats socketを確認します。')
    # round robin over 20 requests
    seen = collections.Counter(get('/')[1] for _ in range(20))
    if set(seen) != {'app1', 'app2'} or not all(9 <= seen[k] <= 11 for k in ('app1', 'app2')):
        bad('ラウンドロビンになっていません: %s (20回で各9-11回を期待)' % dict(seen))
    # ACL routing
    if {get('/api/x')[1] for _ in range(6)} != {'app2'}: bad('/api で始まるパスは app2 だけに届けます。')
    if {get('/', 'admin.dojo.test')[1] for _ in range(6)} != {'app1'}: bad('Host admin.dojo.test は app1 だけに届けます。')
    # real health-check evidence: stopping app1 must take it out of rotation
    units('stop')
    if not wait(lambda: all(get('/')[0] == 200 and get('/')[1] == 'app2' for _ in range(10)), 40):
        bad('app1停止後も、プロキシが死んだbackendを切り離しません(option httpchk と check を確認)。')
    if set(state(18101)) != {'0'}: bad('show servers state でapp1がDOWNになっていません。')
    # recovery
    units('start')
    if not wait(lambda: set(collections.Counter(get('/')[1] for _ in range(10))) == {'app1', 'app2'}, 40):
        bad('app1を再起動しても、分散に復帰しません(rise/checkを確認)。')
finally:
    restore()
PY
    (( rc == 0 )) || return 1
    echo 'PASS: haproxy -c・実HTTPのラウンドロビン・ACL振り分け・backend停止時の自動切り離しと復帰を確認しました。'
}

lab_reset() {
    _hp_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    systemctl disable --now dojo-haproxy.service dojo-backend-1.service dojo-backend-2.service 2>/dev/null || true
    rm -f -- "$HP_UNIT" "$HP_B1" "$HP_B2"
    systemctl daemon-reload
    rm -rf -- "$HP_DIR" "$HP_LIB"
    rm -f -- "$LAB_STATE/owns-lab" "$LAB_STATE/fault" "$LAB_STATE/good.cfg" "$LAB_STATE/files.sha256" "$LAB_STATE/TASKS.txt"
    echo '専用のHAProxy・backend・設定を削除しました。OS標準のhaproxy設定は変更していません。'
}
