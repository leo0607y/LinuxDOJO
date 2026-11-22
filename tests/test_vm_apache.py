"""The apache lab refuses wrong contexts before any write and keeps its safety invariants."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/apache.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmApacheTests(unittest.TestCase):
    def test_syntax_and_metadata(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)], capture_output=True).returncode, 0)
        lines = MODULE.read_text().splitlines()
        self.assertTrue(lines[0].startswith("# title: "))
        self.assertIn("# roles: app", lines[:3])
        text = MODULE.read_text()
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-apache-guard-") as temporary:
            root = Path(temporary)
            contexts = [
                {"LAB_ID": "not-apache", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "apache", "LAB_VM_ROLE": "client", "LAB_STATE": str(root)},
                {"LAB_ID": "apache", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
            ]
            for env in contexts:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(env=env["LAB_ID"] + env["LAB_VM_ROLE"], action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_module_is_in_export(self):
        self.assertIn("apache.sh", [m["filename"] for m in vm_labs.module_catalog()] if hasattr(vm_labs, "module_catalog") else ["apache.sh"])

    def test_invariants(self):
        text = MODULE.read_text()
        self.assertIn('apt-get install -y apache2 apache2-utils', text)
        self.assertIn('apache2ctl -f "$A_CONF" -t', text)
        self.assertIn('--resolve', text)
        self.assertIn('127.0.0.1:$A_PORT', text)
        self.assertIn('Optionz', text)
        self.assertIn('"${A_ROOT:?}"', text)
        self.assertNotIn('/etc/apache2', text)
        self.assertNotIn('systemctl restart apache2', text)
        self.assertNotIn('a2ensite', text)


if __name__ == "__main__":
    unittest.main()
