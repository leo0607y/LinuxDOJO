"""Sysctl/modprobe lab rejects wrong contexts before any write and is syntactically valid."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmSysctlTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/sysctl.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-sysctl-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-sysctl", "app"), ("sysctl", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, role=role, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_check_is_not_satisfied_by_text_alone(self):
        text = self.module.read_text()
        for needle in ("sysctl --system", "sysctl -n vm.swappiness", "modprobe -c", "modprobe -n -v", "lsmod"):
            self.assertIn(needle, text)

    def test_check_survives_no_match_pipelines_and_judges_own_files(self):
        text = self.module.read_text()
        # the dispatcher runs with pipefail: a grep with no match inside $(...) must not abort check silently
        self.assertIn("cut -d: -f1 || true)", text)
        self.assertEqual(text.count("cut -d: -f1 || true)"), 2)
        # Ubuntu kernels already blacklist softdog: the learner's own file must carry both lines
        self.assertIn('"$SC_BLACKLIST"', text)
        self.assertIn("/proc/sys/", text)


if __name__ == "__main__":
    unittest.main()
