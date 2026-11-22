"""RHEL-family labs (selinux, dnf, firewalld): guard behavior and static properties only.
Nothing here executes SELinux, dnf, rpm or firewalld; none of these labs has been run on a real RHEL-family VM."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

LABS = {"selinux": "SE", "dnf": "DN", "firewalld": "FD"}
RHEL_IDS = ("rocky", "almalinux", "rhel", "centos")


def host_is_rhel_family():
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("ID="):
                return line.split("=", 1)[1].strip('"') in RHEL_IDS
    except OSError:
        pass
    return False


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmRhelTests(unittest.TestCase):
    def module(self, lab):
        return vm_labs.SOURCE / "guest/modules" / (lab + ".sh")

    def test_syntax_and_title(self):
        for lab in LABS:
            with self.subTest(lab=lab):
                self.assertEqual(subprocess.run(["bash", "-n", str(self.module(lab))]).returncode, 0)
                text = self.module(lab).read_text()
                self.assertRegex(text, r"(?m)^# title: .+")
                self.assertIn("# roles: app", text)
                for fn in ("lab_setup()", "lab_break()", "lab_check()", "lab_reset()"):
                    self.assertIn(fn, text)

    def test_wrong_context_rejected_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-rhel-guard-") as temporary:
            root = Path(temporary)
            for lab in LABS:
                for lab_id, role in (("not-" + lab, "app"), (lab, "client")):
                    for action in ("setup", "break", "check", "reset"):
                        with self.subTest(lab=lab, lab_id=lab_id, role=role, action=action):
                            result = subprocess.run(
                                ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module(lab)), action],
                                env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                                capture_output=True, text=True, timeout=5)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    @unittest.skipIf(host_is_rhel_family(), "host is RHEL-family; the distro guard would pass")
    def test_non_rhel_distro_rejected_before_any_action(self):
        # Correct context but non-RHEL host (Ubuntu dev machine / CI): must stop on the distro guard. LAB_STATE is the
        # real path, which the guard must refuse before creating anything.
        for lab in LABS:
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(lab=lab, action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module(lab)), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": lab, "LAB_VM_ROLE": "app",
                             "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/" + lab, "LAB_ROOT": "/nonexistent-dojo-root"},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("this lab needs a RHEL-family VM", result.stderr)
                    self.assertFalse(Path("/var/lib/linuxdojo-vm-lab/state/" + lab).exists())

    def test_distro_guard_lists_rhel_ids_in_every_module(self):
        for lab in LABS:
            text = self.module(lab).read_text()
            self.assertIn("rocky|almalinux|rhel|centos", text)
            self.assertIn("this lab needs a RHEL-family VM", text)
            self.assertLess(text.index("/etc/os-release"), text.index("lab_setup()"))

    def test_selinux_check_uses_real_state_and_never_weakens_selinux(self):
        text = self.module("selinux").read_text()
        for needle in ("getenforce", "ausearch -m avc", "semanage fcontext -l -C", "restorecon -RFn", "setsebool -P",
                       "semanage boolean -l -C", "semanage permissive -l", "/etc/selinux/config", "ps -eZ"):
            self.assertIn(needle, text)
        check = text[text.index("lab_check()"):text.index("lab_reset()")]
        self.assertNotIn("setenforce", check)  # check never changes the mode
        self.assertNotIn("setenforce 0", text.replace("setenforce 0 /", ""))  # only mentioned as forbidden in prose

    def test_dnf_uses_local_signed_repo_and_real_verification(self):
        text = self.module("dnf").read_text()
        for needle in ("rpmbuild", "createrepo_c", "rpmsign", "gpg", "repo_gpgcheck", "rpm -V", "dnf versionlock",
                       "history info", "check-update", "SIGPGP", "file://"):
            self.assertIn(needle, text)
        self.assertNotIn("--nogpgcheck", text.replace("--nogpgcheck は不合格", ""))
        self.assertNotIn("gpgcheck=0", text.replace("gpgcheck=0 や", ""))

    def test_firewalld_check_probes_namespace_and_reloads(self):
        text = self.module("firewalld").read_text()
        for needle in ("ip netns exec", "--reload", "--query-panic", "--runtime-to-permanent", "ConnectionRefusedError",
                       "--get-zone-of-interface", "systemd-run", "FD_ZONE=dojo-lab"):
            self.assertIn(needle, text)
        self.assertNotIn("--set-default-zone", text)

    def test_modules_exported_in_cloud_init(self):
        catalog = {entry["id"] for entry in vm_labs.lab_catalog()}
        self.assertTrue(set(LABS) <= catalog)


if __name__ == "__main__":
    unittest.main()
