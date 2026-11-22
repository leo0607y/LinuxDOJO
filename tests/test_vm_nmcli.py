"""Guards and static checks for the nmcli VM lab (not verified in a real VM)."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/nmcli.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmNmcliTests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run(["bash", "-n", str(MODULE)], check=True)

    def test_header_and_functions(self):
        text = MODULE.read_text()
        self.assertRegex(text, r"(?m)^# title: .+")
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-nmcli-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-nmcli", "app"), ("nmcli", "client")):
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

    def test_missing_networkmanager_prints_apt_line_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-nm-") as temporary:
            base = Path(temporary)
            state = base / "state/nmcli"
            state.mkdir(parents=True)
            text = MODULE.read_text().replace("/var/lib/linuxdojo-vm-lab/state/nmcli", str(state)) \
                .replace('${LAB_ROOT:-} != /var/lib/linuxdojo-vm-lab', '${LAB_ROOT:-} != ' + str(base))
            script = base / "m.sh"
            script.write_text(text)
            empty = base / "bin"
            empty.mkdir()
            result = subprocess.run(
                ["/bin/bash", "-c", 'set -euo pipefail; source "$1"; lab_setup', "x", str(script)],
                env={"PATH": str(empty), "LAB_ID": "nmcli", "LAB_VM_ROLE": "app",
                     "LAB_STATE": str(state), "LAB_ROOT": str(base)},
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sudo apt-get install -y network-manager", result.stderr)
            self.assertEqual(list(state.iterdir()), [])

    def test_only_lab_devices_and_profiles_are_touched(self):
        text = MODULE.read_text()
        self.assertIn("ifname dojo1", text)
        self.assertIn("ifname dojo2", text)
        self.assertIn("GENERAL.STATE", text)               # primary NIC must be unmanaged
        self.assertNotRegex(text, r"nmcli (connection|con|c) delete \"?\$(?!p)")
        reset = text.split("lab_reset()")[1]
        self.assertIn("_nm_is_lab_profile", reset)
        self.assertIn("grep -qw dummy", reset)
        for needle in ("ip addr", "ip route", "never-default", "192.0.2"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
