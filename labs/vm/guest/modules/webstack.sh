#!/bin/bash
# title: Nginx・TLS・SQLiteをつなぎ、502を直して再起動後も確認する
# roles: app
# 本物のサービスを変更する。VM専用dispatcherによる確認の後だけ読み込む。

ws_role() {
    [[ ${LAB_ID:-} == webstack && ${LAB_VM_ROLE:-} == app && ${LAB_ROOT:-} == /var/lib/linuxdojo-vm-lab && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/webstack ]] || {
        echo 'webstack は専用dispatcherのapp VM実習です。' >&2; return 1;
    }
    local unit
    for unit in /etc/systemd/system/dojo-webstack-backend.service /etc/systemd/system/dojo-webstack-proxy.service; do
        [[ ! -L $unit ]] || return 1
        if [[ -e $unit ]]; then
            grep -qx '# LinuxDOJO VM module: webstack' "$unit" || { echo "別用途のunitは変更しません: $unit" >&2; return 1; }
        fi
    done
}
ws_config() {
    local upstream=$1
    cat > "$LAB_STATE/nginx.conf" <<EOF
# linuxdojo-owned
pid $LAB_STATE/nginx.pid;
error_log stderr notice;
events { worker_connections 64; }
http {
    access_log $LAB_STATE/access.log;
    server {
        listen 8088;
        server_name app.dojo.test;
        location / { proxy_set_header Host \$host; proxy_pass http://127.0.0.1:$upstream; }
    }
    server {
        listen 8448 ssl;
        server_name app.dojo.test;
        ssl_certificate $LAB_STATE/server.crt;
        ssl_certificate_key $LAB_STATE/server.key;
        location / { proxy_set_header Host \$host; proxy_pass http://127.0.0.1:$upstream; }
    }
}
EOF
    chmod 644 "$LAB_STATE/nginx.conf"
}
lab_setup() {
    ws_role || return
    local tool
    for tool in nginx openssl python3 curl systemctl; do command -v "$tool" >/dev/null || { echo "必要なコマンド: $tool" >&2; return 1; }; done
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" "$LAB_STATE"
    install -d -m 750 -o www-data -g www-data "$LAB_STATE/data"
    cat > "$LAB_STATE/backend.py" <<'PY'
import json, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
DB='data/app.db'
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
    db.execute('INSERT OR IGNORE INTO notes VALUES(1,?)',('linuxdojo-vm-data',))
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404); return
        try:
            with sqlite3.connect(DB) as db:
                row=db.execute('SELECT body FROM notes WHERE id=1').fetchone()
                valid=db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            code=200 if row and valid else 503
            content=json.dumps(dict(service='dojo-webstack',database='ok' if valid else 'error',note=row[0] if row else None)).encode()+b'\n'
        except sqlite3.Error:
            code,content=503,b'{"database":"unavailable"}\n'
        self.send_response(code); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)
HTTPServer(('127.0.0.1',18088),H).serve_forever()
PY
    chmod 644 "$LAB_STATE/backend.py"
    if [[ ! -f $LAB_STATE/server.crt || ! -f $LAB_STATE/server.key ]]; then
        openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj /CN=app.dojo.test \
            -addext subjectAltName=DNS:app.dojo.test -keyout "$LAB_STATE/server.key" -out "$LAB_STATE/server.crt" >/dev/null 2>&1
    fi
    chmod 600 "$LAB_STATE/server.key"
    chmod 644 "$LAB_STATE/server.crt"
    ws_config 18088
    cat > /etc/systemd/system/dojo-webstack-backend.service <<EOF
# LinuxDOJO VM module: webstack
[Unit]
Description=LinuxDOJO dedicated SQLite backend
After=network.target
[Service]
User=www-data
Group=www-data
WorkingDirectory=$LAB_STATE
ExecStart=/usr/bin/python3 $LAB_STATE/backend.py
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$LAB_STATE/data
[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/dojo-webstack-proxy.service <<EOF
# LinuxDOJO VM module: webstack
[Unit]
Description=LinuxDOJO dedicated reverse proxy
After=network.target dojo-webstack-backend.service
Wants=dojo-webstack-backend.service
[Service]
Type=simple
ExecStartPre=/usr/sbin/nginx -t -c $LAB_STATE/nginx.conf
ExecStart=/usr/sbin/nginx -c $LAB_STATE/nginx.conf -g "daemon off;"
ExecReload=/usr/sbin/nginx -c $LAB_STATE/nginx.conf -s reload
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now dojo-webstack-backend.service dojo-webstack-proxy.service
    systemctl restart dojo-webstack-backend.service dojo-webstack-proxy.service
    rm -f -- "$LAB_STATE/fault" "$LAB_STATE/broken-boot-id"
    cat > "$LAB_STATE/TASK.txt" <<EOF
1. setupで構築し、curl http://127.0.0.1:18088/health と http://127.0.0.1:8088/health を比較する。
2. breakで上流ポートだけを壊す。journalctl -u dojo-webstack-proxy と ss -ltnp で原因を調べる。
3. $LAB_STATE/nginx.conf のproxy_passを両serverで正しい上流へ直す。nginx -t -c ... で確認後に専用サービスをreloadする。
4. curl --noproxy '*' --cacert $LAB_STATE/server.crt --resolve app.dojo.test:8448:127.0.0.1 https://app.dojo.test:8448/health を確認する。-kは使わない。
5. VMを再起動してから check。バックエンド、HTTP、TLS、DB、enabled状態をまとめて確認する。
6. SQLite backup APIでDBを退避し、別VMへ証明書の公開部分・設定・データを移し、再構築する。秘密鍵は保管範囲を管理する。
EOF
    echo "構築済み。課題: $LAB_STATE/TASK.txt"
}
lab_break() {
    ws_role || return
    [[ -f $LAB_STATE/nginx.conf ]] || { echo '先にsetupします。' >&2; return 1; }
    cp "$LAB_STATE/nginx.conf" "$LAB_STATE/nginx.before.conf"
    ws_config 18089
    nginx -t -c "$LAB_STATE/nginx.conf"
    systemctl reload dojo-webstack-proxy.service
    cat /proc/sys/kernel/random/boot_id > "$LAB_STATE/broken-boot-id"
    printf 'upstream-port-mismatch\n' > "$LAB_STATE/fault"
    echo '上流ポートの故障を投入しました。DBとバックエンドは保持しています。'
}
lab_check() {
    ws_role || return
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/broken-boot-id ]] || {
        echo 'まずbreakで故障を投入し、原因を調べて修正してください。正常時の比較にはTASK.txtのcurlを使います。' >&2; return 1;
    }
    systemctl is-active --quiet dojo-webstack-backend.service dojo-webstack-proxy.service || return 1
    systemctl is-enabled --quiet dojo-webstack-backend.service dojo-webstack-proxy.service || return 1
    nginx -t -c "$LAB_STATE/nginx.conf" || return 1
    curl --noproxy '*' -fsS http://127.0.0.1:8088/health > "$LAB_STATE/http-evidence.json" || return 1
    curl --noproxy '*' -fsS --cacert "$LAB_STATE/server.crt" --resolve app.dojo.test:8448:127.0.0.1 \
        https://app.dojo.test:8448/health > "$LAB_STATE/tls-evidence.json" || return 1
    python3 - "$LAB_STATE" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ('http-evidence.json','tls-evidence.json'):
    data=json.loads((root/name).read_text())
    if data != dict(service='dojo-webstack',database='ok',note='linuxdojo-vm-data'):
        raise SystemExit('応答・DBの既存データを確認してください。')
PY
    [[ $(cat "$LAB_STATE/broken-boot-id") != "$(cat /proc/sys/kernel/random/boot_id)" ]] || {
        echo '通信は正常です。永続化の確認のためVMを再起動し、もう一度checkします。' >&2; return 1;
    }
    echo '再起動後のサービス・HTTP・TLS・SQLiteが正常です。'
}
lab_reset() {
    ws_role || return
    systemctl disable --now dojo-webstack-proxy.service dojo-webstack-backend.service 2>/dev/null || true
    rm -f /etc/systemd/system/dojo-webstack-proxy.service /etc/systemd/system/dojo-webstack-backend.service
    systemctl daemon-reload
    echo '専用サービスを解除しました。データと証拠はLAB_STATEに保全しています。'
}
