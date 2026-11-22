"""systemdadv lab: wrong context refused before writes; static safety properties."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/systemdadv.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmSystemdAdvTests(unittest.TestCase):
    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-sa-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "not-systemdadv", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_role_rejected(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; lab_check', "guard", str(MODULE)],
            env={"PATH": "/usr/bin:/bin", "LAB_ID": "systemdadv", "LAB_VM_ROLE": "client",
                 "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/systemdadv"},
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected lab context", result.stderr)

    def test_syntax_and_header(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)
        self.assertTrue(MODULE.read_text().startswith("# title:"))

    def test_only_lab_named_units_are_touched(self):
        text = MODULE.read_text()
        for line in text.splitlines():
            if re.match(r"\s*systemctl (start|stop|restart|disable|enable|mask)\b", line):
                for unit in re.findall(r"[A-Za-z0-9@.-]+\.(?:service|socket|timer)", line):
                    self.assertTrue(unit.startswith("dojo-adv-"), line)
        self.assertIn("127.0.0.1:18200", text)
        self.assertIn("systemd-analyze security", text)
        self.assertIn("start-limit-hit", text)

    def test_embedded_python_programs_compile(self):
        text = MODULE.read_text()
        for name in ("dojo-adv-sock.py", "dojo-adv-data.py"):
            marker = f"> \"$SA_LIB/{name}\" <<'PROGRAM'\n"
            start = text.index(marker) + len(marker)
            compile(text[start:text.index("\nPROGRAM\n", start)] + "\n", name, "exec")


if __name__ == "__main__":
    unittest.main()
