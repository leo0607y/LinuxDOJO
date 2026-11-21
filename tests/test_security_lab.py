"""Real HTTP checks for the loopback defensive configuration fixture."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.security_lab import LabServer, SECURE_HEADERS, secure_config


class SecurityLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="linuxdojo-security-")
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.json"
        self.write(secure_config())
        self.fixture = {"run": "test-run", "accounts": {"alice": "alice-test-token", "bob": "bob-test-token"},
                        "documents": {"alice-note": {"owner": "alice", "content": "synthetic-a"},
                                      "bob-note": {"owner": "bob", "content": "synthetic-b"}}}
        self.server = LabServer(0, self.config, self.fixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def write(self, config):
        self.config.write_text(json.dumps(config), encoding="utf-8")

    def get(self, path, user=None):
        headers = {"Authorization": "Bearer " + self.fixture["accounts"][user]} if user else {}
        request = urllib.request.Request(self.url + path, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=2)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, dict(response.headers), json.loads(response.read())

    def test_server_binds_loopback_and_only_exposes_fixed_fixture_routes(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(self.get("/health")[0], 200)
        self.assertEqual(self.get("/etc/passwd")[0], 404)
        self.assertEqual(self.get("/documents/unknown", "alice")[0], 404)
        self.assertEqual(self.get("/health?url=http://example.com")[2]["run"], "test-run")

    def test_authentication_and_ownership_positive_negative_matrix(self):
        for document, user, code in (("alice-note", "alice", 200), ("bob-note", "bob", 200),
                                     ("alice-note", "bob", 403), ("bob-note", "alice", 403),
                                     ("alice-note", None, 401)):
            with self.subTest(document=document, user=user):
                status, _, body = self.get("/documents/" + document, user)
                self.assertEqual(status, code)
                if code != 200:
                    self.assertNotIn("content", body)

    def test_configuration_reload_changes_actual_access_control(self):
        config = secure_config()
        config["enforce_ownership"] = False
        self.write(config)
        self.assertEqual(self.get("/documents/bob-note", "alice")[0], 200)
        config["enforce_ownership"] = True
        self.write(config)
        self.assertEqual(self.get("/documents/bob-note", "alice")[0], 403)
        self.assertEqual(self.get("/documents/bob-note", "bob")[0], 200)

    def test_headers_are_returned_on_success_and_authentication_failure(self):
        for path in ("/health", "/documents/alice-note"):
            _, headers, _ = self.get(path)
            self.assertEqual(headers["X-Lab-Run"], "test-run")
            for key, value in SECURE_HEADERS.items():
                self.assertEqual(headers[key], value)

    def test_cookie_flags_are_attributes_only_and_not_an_authentication_bypass(self):
        status, headers, _ = self.get("/session", "alice")
        self.assertEqual(status, 200)
        attrs = {s.strip().lower() for s in headers["Set-Cookie"].split(";")[1:]}
        self.assertTrue({"secure", "httponly", "samesite=strict", "path=/"} <= attrs)
        self.assertEqual(self.get("/session")[0], 401)

    def test_invalid_configuration_fails_closed(self):
        for configuration in ("broken json", '[]', '{"headers": []}', '{"cookie": []}', '{"require_auth": "false"}'):
            with self.subTest(configuration=configuration):
                self.config.write_text(configuration, encoding="utf-8")
                status, _, body = self.get("/documents/alice-note", "alice")
                self.assertEqual(status, 503)
                self.assertNotIn("content", body)

    def test_only_bearer_scheme_accepts_a_known_account_token(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for value in ("alice-test-token", "Basic alice-test-token", "Bearer invalid", "Bearer ALICE-TEST-TOKEN"):
            with self.subTest(authorization=value):
                req = urllib.request.Request(self.url + "/documents/alice-note", headers={"Authorization": value})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(req, timeout=2)
                self.assertEqual(error.exception.code, 401)
                self.assertEqual(error.exception.headers["WWW-Authenticate"], 'Bearer realm="dojo-lab"')
                error.exception.close()
        for value in ("bearer alice-test-token", "BEARER alice-test-token"):
            req = urllib.request.Request(self.url + "/documents/alice-note", headers={"Authorization": value})
            with opener.open(req, timeout=2) as response:
                self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
