"""サービス管理の状態遷移と、混同しやすい初期状態を検証する。"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided


class ServiceCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-services-test-")
        self.addCleanup(self.tmp.cleanup)
        self.terminal = guided.Terminal(Path(self.tmp.name), {})

    def prepare(self, **extra):
        guided.prepare_step(self.terminal, extra, fresh=True)

    def run_command(self, command, code=0):
        result = self.terminal.execute(command)
        self.assertEqual(result.code, code, result.output)
        return result.output

    def test_crontab_and_cron_service_have_separate_state(self):
        cron = ["30 2 * * * /home/learner/bin/backup.sh"]
        self.prepare(services={"cron": cron})
        self.assertEqual(self.run_command("crontab -l"), cron[0])
        self.assertEqual(self.run_command("systemctl is-active cron"), "active")
        self.run_command("crontab -r")
        self.run_command("crontab -l", 1)
        self.assertEqual(self.run_command("systemctl is-active cron"), "active")
        self.prepare(services={"cron": {"active": "inactive"}})
        self.assertEqual(self.run_command("systemctl is-active cron", 3), "inactive")
        self.run_command("crontab -l", 1)

    def test_reset_failed_only_resets_named_unit_without_starting_it(self):
        self.prepare(services={"nginx": {"active": "failed"}})
        before = self.run_command("systemctl list-units --state=failed")
        self.assertIn("nginx.service", before)
        self.assertIn("demo-app.service", before)
        self.run_command("systemctl reset-failed demo-app", 1)
        self.run_command("sudo systemctl reset-failed demo-app")
        self.assertEqual(self.run_command("systemctl is-active demo-app", 3), "inactive")
        after = self.run_command("systemctl --failed")
        self.assertIn("nginx.service", after)
        self.assertNotIn("demo-app.service", after)

    def test_enable_and_start_are_distinct_and_affect_processes(self):
        self.prepare()
        self.run_command("sudo systemctl enable nginx")
        self.assertEqual(self.run_command("systemctl is-active nginx", 3), "inactive")
        self.run_command("sudo systemctl start nginx")
        self.assertIn("nginx", self.run_command("ps aux"))
        self.run_command("sudo systemctl disable --now nginx")
        self.assertNotIn("nginx", self.run_command("ps aux"))
        self.assertEqual(self.run_command("systemctl is-enabled nginx", 1), "disabled")

    def test_follow_combination_keeps_unit_filter(self):
        self.prepare()
        self.assertEqual(self.run_command("journalctl -fu ssh"), self.run_command("journalctl -f -u ssh"))
        self.assertNotIn("demo-app", self.run_command("journalctl -fushh"))


if __name__ == "__main__":
    unittest.main()
