"""mounts lab refuses wrong contexts before any write and keeps its destructive scope narrow."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/mounts.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmMountsTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-mounts-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for lab_id, role in (("not-mounts", "app"), ("mounts", "client")):
                    with self.subTest(action=action, lab=lab_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_static_safety_scope(self):
        text = MODULE.read_text()
        self.assertIn("dojo_vg", text)
        self.assertIn("dojo_lv", text)
        self.assertIn("BEGIN LinuxDOJO mounts lab", text)
        for forbidden in ("/dev/sd", "/dev/vd", "/dev/nvme", "wipefs", "sgdisk"):
            self.assertNotIn(forbidden, text)
        for needle in ("findmnt --verify", "swapon", "sha256sum", "tune2fs"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
