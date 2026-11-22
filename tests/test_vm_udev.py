"""Guards and static checks for the udev VM lab (not verified in a real VM)."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/udev.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmUdevTests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run(["bash", "-n", str(MODULE)], check=True)

    def test_header_and_functions(self):
        text = MODULE.read_text()
        self.assertRegex(text, r"(?m)^# title: .+")
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-udev-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-udev", "app"), ("udev", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role,
                                 "LAB_STATE": str(root), "LAB_ROOT": "/var/lib/linuxdojo-vm-lab"},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_rules_are_confined_to_lab_devices(self):
        text = MODULE.read_text()
        self.assertIn("/etc/udev/rules.d/90-dojo.rules", text)
        self.assertNotIn("scsi_debug", text.replace("scsi_debug, no real", ""))
        self.assertNotIn("modprobe", text)
        # check must reject unrestricted rules, program execution, and arbitrary RUN
        for needle in ("not restricted to a lab device", "RUN must only touch", "syntax error near", "owns-rules"):
            self.assertIn(needle, text)
        self.assertIn("udevadm info -q property", text)
        # reset only deletes what setup/break recorded
        reset = text.split("lab_reset()")[1]
        self.assertIn("owns-rules", reset)
        self.assertIn("losetup -j", reset)
        self.assertIn("grep -qw dummy", reset)

    def test_break_seeds_syntax_error_and_wrong_match_key(self):
        text = MODULE.read_text()
        self.assertIn('ATTR{loop/backing_files}', text)   # wrong key
        self.assertRegex(text, r'disk\.img" SYMLINK')     # missing comma
        self.assertIn('KERNEL=="dojo-ud0"', text)         # wrong NIC name


if __name__ == "__main__":
    unittest.main()
