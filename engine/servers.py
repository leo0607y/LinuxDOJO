#!/usr/bin/env python3
"""ミッション用のローカル HTTP サーバー（127.0.0.1 のみで待ち受け）。

modes:
  api    : /api/status (GET), /api/health (GET/HEAD + 独自ヘッダ), /api/users (POST JSON)
  hidden : /api/token でトークンを返すだけの「どのポートか分からない」サーバー
  hog    : ポートを占有しているだけの消し忘れ開発サーバー
一定時間 (--ttl 秒) で自動終了する。
API と token はローカル課題の模擬データであり、外部サービスの API キー・認証情報は使用しない。
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(opt):
    class H(BaseHTTPRequestHandler):
        server_version = "PenguinAPI/" + opt.version
        sys_version = ""

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None, head=False):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def _route(self, head=False):
            path = self.path.split("?")[0]
            if opt.mode == "hog":
                return self._send(200, "dev server (forgotten)\n", "text/plain", head=head)
            if opt.mode == "hidden":
                if path in ("/api/token", "/token"):
                    return self._send(200, json.dumps({"token": opt.token}) + "\n", head=head)
                if path == "/":
                    return self._send(200, "Hidden service. Try GET /api/token\n", "text/plain", head=head)
                return self._send(404, json.dumps({"error": "not found"}) + "\n", head=head)
            if path == "/api/status":
                return self._send(200, json.dumps({"service": "penguin-api", "status": "ok",
                                                   "token": opt.token}, ensure_ascii=False) + "\n", head=head)
            if path == "/api/health":
                return self._send(200, "OK\n", "text/plain", {"X-Server-Version": opt.version,
                                                             "X-Request-Id": opt.token[:8]}, head=head)
            if path == "/":
                return self._send(200, "Penguin API. endpoints: /api/status /api/health /api/users\n",
                                  "text/plain", head=head)
            return self._send(404, json.dumps({"error": "not found", "path": path}) + "\n", head=head)

        def do_GET(self):
            self._route()

        def do_HEAD(self):
            self._route(head=True)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            path = self.path.split("?")[0]
            if opt.mode != "api" or path != "/api/users":
                return self._send(404, json.dumps({"error": "not found"}) + "\n")
            ctype = self.headers.get("Content-Type", "")
            rec = {"content_type": ctype, "body": raw.decode(errors="replace"), "time": time.time()}
            if opt.record:
                with open(opt.record, "a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if "application/json" not in ctype:
                return self._send(415, json.dumps({"error": "Content-Type must be application/json",
                                                   "hint": "-H 'Content-Type: application/json' を付けてください"},
                                                  ensure_ascii=False) + "\n")
            try:
                body = json.loads(raw or b"null")
                assert isinstance(body, dict)
            except Exception:
                return self._send(400, json.dumps({"error": "invalid JSON", "received": raw.decode(errors="replace")},
                                                  ensure_ascii=False) + "\n")
            return self._send(201, json.dumps({"result": "created", "id": 1024, "user": body}, ensure_ascii=False) + "\n")

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--mode", default="api")
    ap.add_argument("--token", default="TOKEN")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--record", default="")
    ap.add_argument("--ttl", type=int, default=3 * 3600)
    opt = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", opt.port), make_handler(opt))
    threading.Timer(opt.ttl, lambda: os._exit(0)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
