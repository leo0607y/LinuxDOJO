"""実 Docker の inspect 出力を使う判定を、デーモンなしで検証する。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.docker_backend import RealDocker


def result(stdout="", code=0):
    return subprocess.CompletedProcess([], code, stdout, "")


class RealDockerTests(unittest.TestCase):
    def setUp(self):
        self.backend = RealDocker(None)
        self.backend._run = Mock()

    def test_inspect_normalizes_operational_state(self):
        probe = ["CMD-SHELL", "curl -f http://localhost:80/ || exit 1"]
        inspected = {
            "Id": "0123456789abcdef", "Name": "/lq-web",
            "Config": {"Image": "nginx", "Env": ["TOKEN=a=b", "IGNORED"],
                       "Healthcheck": {"Test": probe}},
            "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
            "NetworkSettings": {"Networks": {"lq-net": {}, "bridge": {}}},
            "RestartCount": 3,
            "State": {"Running": True, "Status": "running", "Health": {"Status": "healthy"}},
        }
        self.backend._run.side_effect = [result("0123456789abcdef\n"), result(json.dumps([inspected]))]
        c = self.backend.containers()[0]
        self.assertEqual(c["id"], "0123456789ab")
        self.assertEqual(c["name"], "lq-web")
        self.assertEqual(c["healthcheck"]["test"], probe)
        self.assertEqual(c["health"], "healthy")
        self.assertEqual(c["networks"], ["bridge", "lq-net"])
        self.assertEqual(c["restart_policy"], "unless-stopped")
        self.assertEqual(c["restart_count"], 3)
        self.assertEqual(c["env"], {"TOKEN": "a=b"})
        self.assertTrue(c["running"])

    def test_inspect_without_healthcheck_has_safe_defaults(self):
        self.backend._run.side_effect = [result("id\n"), result('[{"Config": null, "HostConfig": null, "State": null}]')]
        c = self.backend.containers()[0]
        self.assertEqual(c["healthcheck"]["test"], [])
        self.assertIsNone(c["health"])
        self.assertEqual(c["networks"], [])
        self.assertEqual(c["restart_policy"], "no")
        self.assertEqual(c["restart_count"], 0)

    def test_image_size_comes_from_image_inspect(self):
        self.backend._run.return_value = result('[{"Size": 8900000}]')
        self.assertEqual(self.backend.image_details("lq-api:small"), {"size_bytes": 8900000})
        self.backend._run.assert_called_once_with("image", "inspect", "lq-api:small")
        self.backend._run.return_value = result(code=1)
        self.assertIsNone(self.backend.image_details("missing"))

    def test_reset_only_removes_prefixed_networks_from_labeled_query(self):
        def respond(*args, **kwargs):
            if args[:2] == ("network", "ls"):
                self.assertIn("label=lq=1", args)
                return result("lq-app\nproduction\nlq-test\nother-lq-network\n")
            return result()
        self.backend._run.side_effect = respond
        self.backend.reset()
        removed = [c.args for c in self.backend._run.call_args_list if c.args[:2] == ("network", "rm")]
        self.assertEqual(removed, [("network", "rm", "lq-app"), ("network", "rm", "lq-test")])
        self.backend._run.assert_any_call("network", "ls", "--filter", "label=lq=1", "--format", "{{.Name}}")

    def test_exec_preserves_failure_status_for_connectivity_checks(self):
        self.backend._run.return_value = result("", 7)
        self.assertEqual(self.backend.exec("lq-client", "wget", "http://api"), ("", 7))
        self.backend._run.assert_called_once_with("exec", "lq-client", "wget", "http://api", timeout=15)


if __name__ == "__main__":
    unittest.main()
