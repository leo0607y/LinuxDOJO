"""netconfig lab never touches a host outside its dedicated VM context."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/netconfig.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmNetconfigTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-netconfig-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-netconfig", "app"), ("netconfig", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, role=role, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_static_safety_properties(self):
        text = MODULE.read_text()
        self.assertIn("# roles: app", text)
        self.assertIn("49-dojo0.netdev", text)
        self.assertIn("50-dojo0.network", text)
        self.assertNotIn("/etc/netplan", text)
        self.assertNotIn("ip route add default", text)
        self.assertNotIn("ip route del", text)

    def test_export_contains_module(self):
        with tempfile.TemporaryDirectory(prefix="dojo-netconfig-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            self.assertEqual((bundle / "guest/modules/netconfig.sh").read_bytes(), MODULE.read_bytes())


if __name__ == "__main__":
    unittest.main()
