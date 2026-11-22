"""Guard lab: wrong context is refused before any write; static safety properties."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/guard.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmGuardTests(unittest.TestCase):
    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-guard-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "not-guard", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_role_rejected(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; lab_setup', "guard", str(MODULE)],
            env={"PATH": "/usr/bin:/bin", "LAB_ID": "guard", "LAB_VM_ROLE": "client",
                 "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/guard"},
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected lab context", result.stderr)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_static_safety_properties(self):
        text = MODULE.read_text()
        self.assertTrue(text.startswith("# title:"))
        self.assertIn("# roles: app", text)
        self.assertIn("192.0.2", text)
        self.assertNotIn("/var/log/auth.log", text)
        self.assertIn("apt-get install -y fail2ban auditd", text)
        self.assertNotIn("iptables", text)

    def test_helper_refuses_non_documentation_addresses(self):
        text = MODULE.read_text()
        start = text.index("<<'HELPER'\n") + len("<<'HELPER'\n")
        helper = text[start:text.index("\nHELPER\n", start)]
        with tempfile.TemporaryDirectory(prefix="dojo-guard-helper-") as temporary:
            script = Path(temporary) / "helper.sh"
            script.write_text(helper)
            for ip in ("8.8.8.8", "192.0.3.1", "192.0.2.999x", "127.0.0.1"):
                result = subprocess.run(["bash", str(script), "--print", ip], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2, ip)
            result = subprocess.run(["bash", str(script), "--print", "192.0.2.10"], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertIn("authentication failure for user admin from 192.0.2.10", result.stdout)


if __name__ == "__main__":
    unittest.main()
