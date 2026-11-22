"""Mailserver lab rejects wrong context before writes and never mutates an unprovisioned host."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmMailserverTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/mailserver.sh"

    def run_action(self, action, env):
        return subprocess.run(
            [shutil.which("bash"), "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
            env=env, capture_output=True, text=True, timeout=5)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-mail-guard-") as temporary:
            root = Path(temporary)
            for ident, role in (("not-mailserver", "app"), ("mailserver", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(ident=ident, role=role, action=action):
                        result = self.run_action(action, {"PATH": "/usr/bin:/bin", "LAB_ID": ident,
                                                          "LAB_VM_ROLE": role, "LAB_STATE": str(root)})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_setup_without_postfix_prints_install_hint_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-mail-empty-") as empty:
            result = self.run_action("setup", {"PATH": empty, "LAB_ID": "mailserver", "LAB_VM_ROLE": "app",
                                               "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/mailserver"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt-get install -y postfix", result.stdout)
        self.assertIn("Local only", result.stdout)

    def test_static_safety_properties(self):
        text = self.module.read_text()
        self.assertIn("127.0.0.1:2526 inet", text)
        self.assertIn("default_transport = error:", text)
        self.assertIn("mynetworks = 0.0.0.0/0", text)
        self.assertNotIn("/etc/postfix/main.cf", text)


if __name__ == "__main__":
    unittest.main()
