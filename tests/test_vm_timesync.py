"""Timesync lab rejects wrong context before any write and is syntactically valid."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmTimesyncTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/timesync.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-timesync-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env in ({"LAB_ID": "ssh", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                            {"LAB_ID": "timesync", "LAB_VM_ROLE": "client",
                             "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/timesync"}):
                    with self.subTest(action=action, env=env["LAB_ID"] + env["LAB_VM_ROLE"]):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_check_uses_effective_state_not_file_text(self):
        text = self.module.read_text()
        for needle in ("show-timesync", "locale -a", "date +%z", "localectl status"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
