"""Restore lab rejects wrong contexts before writes; non-privileged helpers are exercised."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/restore.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmRestoreTests(unittest.TestCase):
    def run_bash(self, script, env, *args):
        return subprocess.run(["bash", "-c", script, "t", str(MODULE), *args], env=env,
                              capture_output=True, text=True, timeout=10)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)
        self.assertIn("# roles: app client", MODULE.read_text())

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-restore-guard-") as temporary:
            root = Path(temporary)
            contexts = [
                {"LAB_ID": "other", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "restore", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "restore", "LAB_VM_ROLE": "web", "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/restore"},
            ]
            for env in contexts:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(action=action, env=env["LAB_ID"] + env["LAB_VM_ROLE"]):
                        result = self.run_bash('set -euo pipefail; source "$1"; "lab_$2"',
                                               {"PATH": "/usr/bin:/bin", **env}, action)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_fixed_constants_match_generated_content(self):
        with tempfile.TemporaryDirectory(prefix="dojo-restore-data-") as temporary:
            script = '''source "$1"; d=$2
_restore_write_index "$d/index.html"; _restore_make_db "$d/full.db" full; _restore_make_db "$d/stale.db" stale
[[ $(sha256sum "$d/index.html" | cut -d" " -f1) == "$RESTORE_INDEX_SHA" ]] || exit 11
_restore_db_verify "$d/full.db" || exit 12
if _restore_db_verify "$d/stale.db"; then exit 13; fi
grep -q "$RESTORE_TOKEN" "$d/index.html"'''
            result = subprocess.run(["bash", "-c", script, "t", str(MODULE), temporary],
                                    env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_export_contains_module(self):
        with tempfile.TemporaryDirectory(prefix="dojo-restore-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            self.assertEqual((bundle / "guest/modules/restore.sh").read_bytes(), MODULE.read_bytes())


if __name__ == "__main__":
    unittest.main()
