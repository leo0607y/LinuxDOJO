"""Resource-limits lab rejects wrong context before any write and keeps its anti-cheat checks."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmLimitsTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/limits.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-limits-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for lab_id, role in (("not-limits", "app"), ("limits", "client")):
                    with self.subTest(action=action, lab=lab_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_check_enforces_finite_caps_and_drop_in(self):
        text = self.module.read_text()
        for needle in ("must remain a finite cap", "drop-in", "NRestarts", "/proc/$pid2/limits",
                       "memory.max", "ExecStart must stay unchanged", "sha256sum -c"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
