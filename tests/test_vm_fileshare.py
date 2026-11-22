"""fileshare lab refuses wrong contexts before writing, and its judging is live-state based."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/fileshare.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmFileshareTests(unittest.TestCase):
    def run_action(self, action, env):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        bad = [
            {"LAB_ID": "not-fileshare", "LAB_VM_ROLE": "app"},
            {"LAB_ID": "fileshare", "LAB_VM_ROLE": "client"},   # state path is wrong
            {"LAB_ID": "fileshare", "LAB_VM_ROLE": "other"},
        ]
        with tempfile.TemporaryDirectory(prefix="dojo-fileshare-guard-") as temporary:
            root = Path(temporary)
            for env in bad:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(env=env, action=action):
                        result = self.run_action(action, {**env, "LAB_STATE": str(root)})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_header_and_safety_properties(self):
        text = MODULE.read_text()
        self.assertIn("# title:", text.splitlines()[1])
        self.assertIn("# roles: app client", text)
        self.assertIn("/etc/exports.d/dojo.exports", text)
        self.assertNotIn("> /etc/exports ", text)
        self.assertIn("_netdev", text)
        self.assertIn("nofail", text)
        self.assertIn("apt install -y nfs-kernel-server", text)
        self.assertIn("apt install -y nfs-common", text)

    def test_package_check_precedes_any_write(self):
        text = MODULE.read_text()
        setup = text[text.index("lab_setup()"):text.index("lab_break()")]
        self.assertLess(setup.index("_fs_need_pkg"), setup.index("useradd"))
        self.assertLess(setup.index("_fs_need_pkg"), setup.index("_fs_write_exports"))

    def test_judging_uses_live_state(self):
        text = MODULE.read_text()
        for needle in ("exportfs -v", "findmnt", "runuser -u", "stat -c %u", "65534"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
