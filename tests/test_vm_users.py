"""Users/sudo lab rejects wrong contexts before any write and keeps safety rules in the source."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/users.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmUsersTests(unittest.TestCase):
    def run_action(self, action, env):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-users-guard-") as temporary:
            root = Path(temporary)
            contexts = [
                {"LAB_ID": "not-users", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "users", "LAB_VM_ROLE": "client", "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/users"},
                {"LAB_ID": "users", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
            ]
            for env in contexts:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(action=action, env=env["LAB_ID"] + env["LAB_VM_ROLE"]):
                        result = self.run_action(action, env)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_safety_rules_present(self):
        text = MODULE.read_text()
        self.assertIn("# roles: app", text)
        self.assertIn("visudo -cf", text)
        self.assertIn("visudo -c ", text)
        self.assertIn("sudo -n -l", text)
        self.assertIn("440 root root", text)
        self.assertIn("alice.ids", text)  # reset only removes the recorded uid/gid
        self.assertIn("/usr/bin/id", text)
        self.assertNotIn("sudo -n /usr/bin/systemctl", text)  # never execute the permitted command


if __name__ == "__main__":
    unittest.main()
