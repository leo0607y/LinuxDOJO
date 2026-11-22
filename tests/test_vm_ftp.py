"""Dedicated ftp lab: guards reject wrong context before any write; offline helper logic is exercised."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/ftp.sh"
BASH = shutil.which("bash")


def run_bash(script, *args, env=None):
    return subprocess.run([BASH, "-c", script, "t", str(MODULE), *args], env=env or {"PATH": "/nonexistent"},
                          capture_output=True, text=True, timeout=20)


@unittest.skipUnless(BASH, "Bash is required")
class VmFtpTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run([BASH, "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-ftp-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for ident, role in (("not-ftp", "app"), ("ftp", "client")):
                    with self.subTest(action=action, ident=ident):
                        result = run_bash('set -euo pipefail; source "$1"; "lab_$2"', action,
                                          env={"PATH": "/nonexistent", "LAB_ID": ident, "LAB_VM_ROLE": role, "LAB_STATE": str(root)})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_header_and_functions(self):
        text = MODULE.read_text()
        self.assertTrue(text.startswith("# title: "))
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_missing_package_prints_apt_line_without_writes(self):
        # Context is correct, PATH is empty so no tool exists: must stop at the tool check, before writing.
        with tempfile.TemporaryDirectory(prefix="dojo-ftp-nopkg-") as temporary:
            result = run_bash('set -u; source "$1"; _ftp_paths; _ftp_tools',
                              env={"PATH": "/nonexistent", "LAB_ID": "ftp", "LAB_VM_ROLE": "app",
                                   "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/ftp"})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("apt-get install -y vsftpd", result.stdout)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def policy(self, conf):
        with tempfile.TemporaryDirectory(prefix="dojo-ftp-policy-") as temporary:
            path = Path(temporary) / "vsftpd.conf"
            path.write_text(conf)
            return run_bash('source "$1"; F_CONF="$2"; _ftp_policy', str(path), env={"PATH": "/usr/bin:/bin"})

    GOOD = ("listen_address=127.0.0.1\nlisten_port=2121\nanonymous_enable=NO\nchroot_local_user=YES\n"
            "userlist_enable=YES\nuserlist_deny=NO\npasv_min_port=30000\npasv_max_port=30010\npasv_address=127.0.0.1\n")

    def test_policy_accepts_proper_config_and_rejects_shortcuts(self):
        self.assertEqual(self.policy(self.GOOD).returncode, 0)
        for bad in (self.GOOD + "allow_writeable_chroot=YES\n", self.GOOD.replace("anonymous_enable=NO", "anonymous_enable=YES"),
                    self.GOOD.replace("userlist_deny=NO", "userlist_deny=YES"), self.GOOD.replace("30010", "30100"),
                    self.GOOD.replace("chroot_local_user=YES\n", ""), self.GOOD.replace("pasv_address=127.0.0.1\n", "")):
            with self.subTest(bad=bad):
                self.assertEqual(self.policy(bad).returncode, 1)

    def test_probe_requires_live_server(self):
        text = MODULE.read_text()
        for needle in ("ftplib", "makepasv", "30000 <= port <= 30010", "'..'", "refused('anonymous'", "sha256"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
