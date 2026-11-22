"""Dedicated Samba lab rejects wrong contexts before writing and has sane static shape."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/samba.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmSambaTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-samba-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env_extra in ({"LAB_ID": "not-samba", "LAB_VM_ROLE": "app"},
                                  {"LAB_ID": "samba", "LAB_VM_ROLE": "client"}):
                    with self.subTest(action=action, env=env_extra):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_STATE": str(root), **env_extra},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_state_path_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dojo-samba-guard-") as temporary:
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; lab_setup', "guard", str(MODULE)],
                env={"PATH": "/usr/bin:/bin", "LAB_ID": "samba", "LAB_VM_ROLE": "app", "LAB_STATE": temporary},
                capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_static_shape(self):
        text = MODULE.read_text()
        self.assertIn("# title:", text.splitlines()[1])
        self.assertIn("# roles: app", text)
        for needle in ("smb ports = $SM_PORT", "bind interfaces only = yes", "interfaces = 127.0.0.1",
                       "-s $SM_CONF", "valid usres", "map to guest = bad user",
                       "sudo apt-get install -y samba smbclient", "NT_STATUS_"):
            self.assertIn(needle, text)
        # Never touch the system Samba config.
        self.assertNotIn("/etc/samba/smb.conf", text.replace("/etc/samba, ", ""))

    def test_setup_without_samba_installed_writes_nothing(self):
        # Context valid but state dir not creatable here; with no samba tools it must stop first.
        if shutil.which("smbd"):
            self.skipTest("samba installed on this host")
        script = ('source "$1"; _sm_paths() { SM_UNIT=/nonexistent/u; SM_DIR=/nonexistent/d; SM_CONF=/nonexistent/c;'
                  ' SM_VAR=/nonexistent/v; SM_DATA=/nonexistent/s; SM_GROUP=g; SM_USER1=a; SM_USER2=b; SM_PORT=1445; }; lab_setup')
        result = subprocess.run(["bash", "-c", script, "t", str(MODULE)],
                                env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo apt-get install -y samba smbclient", result.stdout)


if __name__ == "__main__":
    unittest.main()
