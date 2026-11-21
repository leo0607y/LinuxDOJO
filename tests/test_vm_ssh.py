"""Dedicated SSH lab never mutates an unprovisioned host; export includes its source."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmSshTests(unittest.TestCase):
    def test_all_ssh_actions_reject_wrong_context_before_writes(self):
        module = vm_labs.SOURCE / "guest/modules/ssh.sh"
        with tempfile.TemporaryDirectory(prefix="dojo-ssh-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(module), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "not-ssh", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_actual_export_contains_new_lifecycle_labs_and_their_guide(self):
        with tempfile.TemporaryDirectory(prefix="dojo-ssh-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            for name in ("ssh", "packages", "software"):
                self.assertEqual((bundle / "guest/modules" / (name + ".sh")).read_bytes(),
                                 (vm_labs.SOURCE / "guest/modules" / (name + ".sh")).read_bytes())
            self.assertEqual((bundle / "SOFTWARE.md").read_bytes(), (vm_labs.SOURCE / "SOFTWARE.md").read_bytes())
            rendered = (bundle / "app-cloud-init.yaml").read_text()
            self.assertIn("  - openssh-server", rendered)
            self.assertIn("  - tmux", rendered)
            self.assertIn("  - gcc", rendered)


if __name__ == "__main__":
    unittest.main()
