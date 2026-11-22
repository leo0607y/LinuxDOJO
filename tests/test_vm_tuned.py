"""The tuned lab rejects wrong contexts before any write, is valid Bash, and checks real tool output."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmTunedTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/tuned.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-tuned-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-tuned", "app"), ("tuned", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, role=role, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_setup_detects_missing_package_before_writing(self):
        text = self.module.read_text()
        setup = text[text.index("lab_setup()"):text.index("lab_break()")]
        self.assertIn("sudo apt-get install -y tuned", setup)
        writes = [i for i in (setup.find("mkdir"), setup.find("> \""), setup.find("printf")) if i >= 0]
        self.assertLess(setup.index("command -v tuned-adm"), min(writes))

    def test_check_judges_real_tool_output(self):
        text = self.module.read_text()
        check = text[text.index("lab_check()"):text.index("lab_reset()")]
        for needle in ("tuned-adm verify", "sysctl -n vm.swappiness", "sysctl -n net.core.somaxconn", "orig.profile", "fault"):
            self.assertIn(needle, check)

if __name__ == "__main__":
    unittest.main()
