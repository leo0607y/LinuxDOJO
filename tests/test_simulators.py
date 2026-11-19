"""管理系/Docker シミュレーターの回帰テスト（全状態を一時ディレクトリに隔離）。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import dockermock as dm, sim_ops


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lq-sim-test-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.state = self.work / "state"
        self.state.mkdir()
        self.env = dict(os.environ, LQ_HOME=str(ROOT), LQ_WORK=str(self.work),
                        LQ_STATE=str(self.state), LQ_SIM_ROOT="0",
                        PATH=f"{ROOT / 'bin/sim'}:{ROOT / 'bin/mock'}:{os.environ['PATH']}")
        sim_ops.init_system(self.work, self.state)
        self.old_state = dm.STATE_DIR
        self.addCleanup(setattr, dm, "STATE_DIR", self.old_state)
        dm.STATE_DIR = self.state / "docker"

    def cli(self, *args):
        return subprocess.run(args, env=self.env, cwd=self.work, capture_output=True,
                              text=True, timeout=15)

    def docker(self, *args):
        result = self.cli("docker", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_simulated_privilege_does_not_inherit_host_root(self):
        with patch.dict(os.environ, {"LQ_SIM_ROOT": "0"}), patch("os.geteuid", return_value=0):
            self.assertFalse(sim_ops.is_root())
        denied = self.cli("systemctl", "stop", "ssh")
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(sim_ops.unit_state("ssh.service")["active"], "active")
        self.assertEqual(self.cli("sudo", "systemctl", "stop", "ssh").returncode, 0)
        self.assertEqual(sim_ops.unit_state("ssh.service")["active"], "inactive")

    def test_group_append_preserves_existing_memberships(self):
        self.assertEqual(self.cli("sudo", "useradd", "-m", "-G", "sudo", "alice").returncode, 0)
        self.assertEqual(self.cli("sudo", "usermod", "-aG", "docker", "alice").returncode, 0)
        self.assertTrue({"sudo", "docker"} <= set(sim_ops.user_info("alice")["groups"]))
        self.assertTrue((self.work / "sysroot/home/alice/.bashrc").exists())
        self.assertEqual(self.cli("sudo", "usermod", "-G", "docker", "alice").returncode, 0)
        self.assertNotIn("sudo", sim_ops.user_info("alice")["groups"])

    def test_network_alias_dns_and_actual_port(self):
        self.docker("network", "create", "appnet")
        self.docker("run", "-d", "--name", "web", "--network", "appnet", "--network-alias", "api", "nginx")
        self.docker("run", "-d", "--name", "client", "alpine", "sleep", "3600")
        self.assertNotEqual(self.cli("docker", "exec", "client", "wget", "-qO-", "http://api").returncode, 0)
        self.docker("network", "connect", "appnet", "client")
        self.docker("exec", "client", "wget", "-qO-", "http://api:80")
        self.assertNotEqual(self.cli("docker", "exec", "client", "wget", "-qO-", "http://api:9999").returncode, 0)
        self.docker("network", "disconnect", "appnet", "client")
        self.assertNotEqual(self.cli("docker", "exec", "client", "wget", "-qO-", "http://api").returncode, 0)

    def test_healthcheck_failure_and_process_restart_are_independent(self):
        self.docker("run", "-d", "--name", "web", "--restart", "unless-stopped",
                    "--health-cmd", "false", "nginx")
        before = json.loads(self.docker("inspect", "web").stdout)[0]
        self.assertEqual(before["State"]["Health"]["Status"], "unhealthy")
        self.assertEqual(before["RestartCount"], 0)
        self.docker("exec", "web", "sh", "-c", "kill -9 1")
        after = json.loads(self.docker("inspect", "web").stdout)[0]
        self.assertTrue(after["State"]["Running"])
        self.assertGreater(after["RestartCount"], 0)
        self.docker("stop", "web")
        stopped = json.loads(self.docker("inspect", "web").stdout)[0]
        self.assertFalse(stopped["State"]["Running"])

    def test_healthcheck_requires_tool_and_matching_port(self):
        for name, probe, expected in (("good", "curl -f http://localhost:80/", "healthy"),
                                      ("badport", "curl -f http://localhost:9999/", "unhealthy"),
                                      ("missingtool", "wget http://localhost/", "unhealthy")):
            self.docker("run", "-d", "--name", name, "--health-cmd", probe, "nginx")
            info = json.loads(self.docker("inspect", name).stdout)[0]
            self.assertEqual(info["State"]["Health"]["Status"], expected)

    def test_database_readiness_is_not_healthy_before_initialization(self):
        st = dm.load()
        dm.ensure_image(st, "postgres:16")
        c = dm.new_container(st, "db", "postgres:16", [], {}, {}, [], {},
                             healthcheck={"test": ["CMD", "pg_isready"]})
        c["status"] = "running"
        c["ready_at"] = float("inf")
        self.assertFalse(dm.health_eval(st, c)[0])


if __name__ == "__main__":
    unittest.main()
