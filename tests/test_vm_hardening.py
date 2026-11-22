"""hardening lab: wrong context refused before writes; host-wide settings are never modified."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/hardening.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmHardeningTests(unittest.TestCase):
    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-hd-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "not-hardening", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_role_rejected(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; lab_setup', "guard", str(MODULE)],
            env={"PATH": "/usr/bin:/bin", "LAB_ID": "hardening", "LAB_VM_ROLE": "client",
                 "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/hardening"},
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected lab context", result.stderr)

    def test_syntax_and_header(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)
        self.assertTrue(MODULE.read_text().startswith("# title:"))

    def test_host_wide_settings_are_never_modified(self):
        text = MODULE.read_text()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for forbidden in ("chmod /etc", "chown /etc", "> /etc/", ">> /etc/", "sed -i /etc", "usermod -L root",
                          "/etc/ssh/sshd_config\"", "sysctl -w", "systemctl restart ssh", "apt-get install"):
            self.assertNotIn(forbidden, code, forbidden)
        self.assertIn("sshd -T -f", code)
        self.assertIn("/srv/dojo-hardening", code)
        self.assertNotIn("/srv/dojo-audit", code)  # owned by the guard lab

    def test_reset_removes_only_marked_lab_paths(self):
        text = MODULE.read_text()
        self.assertIn(".dojo-hardening-lab", text)
        self.assertIn("owns-account", text)


if __name__ == "__main__":
    unittest.main()
