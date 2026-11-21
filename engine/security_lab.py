"""Loopback-only HTTP configuration fixture for defensive security exercises.

All accounts and documents are synthetic. There are no arbitrary file, command,
proxy, injection or URL-fetching endpoints. This is HTTP for local header testing;
it does not implement TLS or a production authentication/session system.
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

SECURE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}


def secure_config():
    return {"headers": dict(SECURE_HEADERS), "require_auth": True,
            "enforce_ownership": True,
            "cookie": {"secure": True, "httponly": True, "samesite": "Strict"}}


class LabServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, config, fixture):
        self.config_path = Path(config)
        self.fixture = fixture
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "DojoSecurityLab/1.0"
    sys_version = ""

    def log_message(self, *args):
        pass

    def _send(self, status, body, config, extra=None, head=False):
        payload = (json.dumps(body, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Lab-Run", self.server.fixture["run"])
        if status == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="dojo-lab"')
        # Only known security header names can be configured. No arbitrary headers.
        for name in SECURE_HEADERS:
            value = config.get("headers", {}).get(name)
            if isinstance(value, str) and "\r" not in value and "\n" not in value:
                self.send_header(name, value)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(payload)

    def _route(self, head=False):
        fixture = self.server.fixture
        try:
            config = json.loads(self.server.config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("configuration must be an object")
            if not isinstance(config.get("headers", {}), dict) or not isinstance(config.get("cookie", {}), dict):
                raise ValueError("headers and cookie must be objects")
            for key in ("require_auth", "enforce_ownership"):
                if key in config and not isinstance(config[key], bool):
                    raise ValueError("access policy must be boolean")
            for key in ("secure", "httponly"):
                if key in config.get("cookie", {}) and not isinstance(config["cookie"][key], bool):
                    raise ValueError("cookie flags must be boolean")
        except (OSError, ValueError):
            return self._send(503, {"error": "invalid lab configuration"}, {}, head=head)
        path = urlsplit(self.path).path
        if path == "/health":
            return self._send(200, {"service": "dojo-security-lab", "run": fixture["run"], "status": "ok"}, config, head=head)
        if path == "/catalog":
            return self._send(200, {"run": fixture["run"], "paths": ["/health", "/catalog", "/session", "/documents/alice-note", "/documents/bob-note"]}, config, head=head)
        authorization = self.headers.get("Authorization", "")
        credentials = authorization.split()
        token = credentials[1] if len(credentials) == 2 and credentials[0].lower() == "bearer" else None
        user = next((name for name, value in fixture["accounts"].items() if token == value), None)
        if path == "/session":
            if user is None:
                return self._send(401, {"error": "authentication required", "run": fixture["run"]}, config, head=head)
            policy = config.get("cookie", {})
            cookie = "dojo_session=training-only; Path=/"
            if policy.get("secure") is True:
                cookie += "; Secure"
            if policy.get("httponly") is True:
                cookie += "; HttpOnly"
            if policy.get("samesite") in ("Strict", "Lax"):
                cookie += "; SameSite=" + policy["samesite"]
            return self._send(200, {"user": user, "run": fixture["run"], "note": "cookie attributes only; bearer authentication remains required"}, config, {"Set-Cookie": cookie}, head)
        if path.startswith("/documents/"):
            key = path[len("/documents/"):]
            document = fixture["documents"].get(key)
            if document is None:
                return self._send(404, {"error": "not found", "run": fixture["run"]}, config, head=head)
            if config.get("require_auth", True) and user is None:
                return self._send(401, {"error": "authentication required", "run": fixture["run"]}, config, head=head)
            if config.get("enforce_ownership", True) and user != document["owner"]:
                return self._send(403, {"error": "forbidden", "run": fixture["run"]}, config, head=head)
            return self._send(200, {"document": key, "owner": document["owner"], "content": document["content"], "run": fixture["run"]}, config, head=head)
        return self._send(404, {"error": "not found", "run": fixture["run"]}, config, head=head)

    def do_GET(self):
        self._route()

    def do_HEAD(self):
        self._route(head=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--ttl", type=int, default=10800)
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    server = LabServer(args.port, args.config, fixture)
    timer = threading.Timer(args.ttl, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
