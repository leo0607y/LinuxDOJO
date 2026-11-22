"""raid lab rejects wrong context before any write and keeps its anti-cheat checks."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmRaidTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/raid.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-raid-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for lab_id, role in (("not-raid", "app"), ("raid", "client")):
                    with self.subTest(action=action, lab=lab_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_state_dir_must_be_exact(self):
        with tempfile.TemporaryDirectory(prefix="dojo-raid-state-") as temporary:
            result = subprocess.run(
                ["bash", "-c", 'set -euo pipefail; source "$1"; lab_setup', "guard", str(self.module)],
                env={"PATH": "/usr/bin:/bin", "LAB_ID": "raid", "LAB_VM_ROLE": "app", "LAB_STATE": temporary},
                capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_no_real_disk_or_root_targets(self):
        text = self.module.read_text()
        self.assertIsNone(re.search(r"/dev/(sd|vd|nvd|nvme|xvd)", text))
        self.assertNotIn("rm -rf", text)
        self.assertIn("losetup", text)

    def test_check_keeps_real_state_judgements(self):
        text = self.module.read_text()
        for needle in ['mdadm --detail "$RAID_MD"', '--zero-superblock', 'active sync', '/proc/mdstat', 'apt install -y mdadm', 'BEGIN linuxdojo-raid', '_raid_is_lab_loop', 'UUID=$uuid']:
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
