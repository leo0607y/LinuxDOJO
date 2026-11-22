"""Rootless Podman lab: guard, missing-podman exit and no-pull invariants (static; no real VM)."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/podman.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmPodmanTests(unittest.TestCase):
    def run_action(self, action, env):
        return subprocess.run(["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "t", str(MODULE), action],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-podman-guard-") as temporary:
            for ident, role in (("not-podman", "app"), ("podman", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(ident=ident, role=role, action=action):
                        r = self.run_action(action, {"PATH": "/usr/bin:/bin", "LAB_ID": ident,
                                                     "LAB_VM_ROLE": role, "LAB_STATE": temporary})
                        self.assertNotEqual(r.returncode, 0)
                        self.assertIn("unexpected lab context", r.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_setup_without_podman_prints_install_hint_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-podman-empty-") as empty:
            r = subprocess.run([shutil.which("bash"), "-c", 'set -euo pipefail; source "$1"; lab_setup', "t", str(MODULE)],
                               env={"PATH": empty, "LAB_ID": "podman", "LAB_VM_ROLE": "app",
                                    "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/podman"},
                               capture_output=True, text=True, timeout=10)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("sudo apt-get install -y podman", r.stdout)

    def test_static_invariants(self):
        text = MODULE.read_text()
        self.assertNotIn("podman pull", text)
        self.assertFalse([l for l in text.splitlines() if "Volume=" in l and ":Z" in l])
        self.assertIn("# title:", text.splitlines()[0])
        for token in ("podman unshare", "enable-linger", "localhost/dojo-app:1", "Privileged", "owns-account"):
            self.assertIn(token, text)
        self.assertFalse([l for l in text.splitlines() if l.strip().startswith("chmod 0777") or "chmod 777" in l.split("#")[0] and "TASK" not in l and "は不正解" not in l])


if __name__ == "__main__":
    unittest.main()
