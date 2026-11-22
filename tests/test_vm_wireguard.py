"""The wireguard lab rejects wrong contexts before writing, and exits cleanly when its package is absent."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/wireguard.sh"
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "Bash is required")
class VmWireguardTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run([BASH, "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-wireguard-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(action=action):
                    result = subprocess.run(
                        [BASH, "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "not-wireguard", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_role_is_rejected(self):
        result = subprocess.run(
            [BASH, "-c", 'source "$1"; lab_check', "guard", str(MODULE)],
            env={"PATH": "/usr/bin:/bin", "LAB_ID": "wireguard", "LAB_VM_ROLE": "client",
                 "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/wireguard"},
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected lab context", result.stderr)

    def test_setup_without_package_prints_apt_line_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-wireguard-empty-") as empty:
            result = subprocess.run(
                [BASH, "-c", 'source "$1"; lab_setup', "guard", str(MODULE)],
                env={"PATH": empty, "LAB_ID": "wireguard", "LAB_VM_ROLE": "app",
                     "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/wireguard"},
                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt-get install", result.stdout)
        self.assertFalse(Path("/var/lib/linuxdojo-vm-lab/state/wireguard").exists())

    def test_checks_require_break_marker(self):
        source = MODULE.read_text()
        self.assertIn("fault", source)
        self.assertIn("lab_reset", source)


if __name__ == "__main__":
    unittest.main()
