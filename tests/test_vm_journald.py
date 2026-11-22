"""journald lab rejects wrong contexts before any write; syntax is valid."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmJournaldTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/journald.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-journald-guard-") as temporary:
            root = Path(temporary)
            for env_extra in ({"LAB_ID": "not-journald", "LAB_VM_ROLE": "app"},
                              {"LAB_ID": "journald", "LAB_VM_ROLE": "client"},
                              {"LAB_ID": "journald", "LAB_VM_ROLE": "app"}):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(action=action, ctx=env_extra):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_STATE": str(root), **env_extra},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_uses_dropin_not_main_config(self):
        text = self.module.read_text()
        self.assertNotIn("> /etc/systemd/journald.conf\n", text)
        self.assertIn("50-dojo.conf", text)


if __name__ == "__main__":
    unittest.main()
