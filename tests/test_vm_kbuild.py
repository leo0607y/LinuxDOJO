"""kbuild lab: wrong-context rejection before writes, static safety properties."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/kbuild.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmKbuildTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-kbuild-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-kbuild", "app"), ("kbuild", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(action=action, lab=lab_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_static_safety_and_honesty(self):
        text = MODULE.read_text()
        self.assertIn("# roles: app", text)
        self.assertIn("apt install", text)
        self.assertIn("キーワード判定", text)
        for forbidden in ("mokutil --disable", "sig_enforce=0", "insmod --force", "modprobe -f", "rmmod -f"):
            self.assertNotIn(forbidden, text)

    def test_broken_fixture_has_the_three_faults(self):
        text = MODULE.read_text()
        self.assertIn("cnt)\n", text)
        self.assertIn('MODULE_LICENSE("Proprietary")', text)
        self.assertIn("/buld", text)
        self.assertIn("\n    $(MAKE) -C $(KDIR)", text)

    def test_export_contains_module(self):
        with tempfile.TemporaryDirectory(prefix="dojo-kbuild-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            self.assertEqual((bundle / "guest/modules/kbuild.sh").read_bytes(), MODULE.read_bytes())


if __name__ == "__main__":
    unittest.main()
