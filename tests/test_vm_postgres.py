"""The postgres lab refuses wrong contexts before any write and keeps its safety invariants."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/postgres.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmPostgresTests(unittest.TestCase):
    def test_syntax_and_metadata(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)], capture_output=True).returncode, 0)
        lines = MODULE.read_text().splitlines()
        self.assertTrue(lines[0].startswith("# title: "))
        self.assertIn("# roles: app", lines[:3])
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", MODULE.read_text())

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-pg-guard-") as temporary:
            root = Path(temporary)
            contexts = [
                {"LAB_ID": "not-postgres", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "postgres", "LAB_VM_ROLE": "client", "LAB_STATE": str(root)},
                {"LAB_ID": "postgres", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
            ]
            for env in contexts:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(env=env["LAB_ID"] + env["LAB_VM_ROLE"], action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_missing_packages_refuse_without_writing(self):
        state = "/var/lib/linuxdojo-vm-lab/state/postgres"
        result = subprocess.run(
            [shutil.which("bash"), "-c", 'set -euo pipefail; source "$1"; _pg_paths; _pg_tools', "t", str(MODULE)],
            env={"PATH": "/nonexistent", "LAB_ID": "postgres", "LAB_VM_ROLE": "app", "LAB_STATE": state},
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo apt-get install -y postgresql postgresql-client", result.stdout)

    def test_invariants(self):
        text = MODULE.read_text()
        self.assertIn('pg_createcluster "$PG_VER" "$PG_NAME" --port "$PG_PORT"', text)
        self.assertIn("pg_dropcluster", text)
        self.assertIn("dojo-lab-marker", text)
        self.assertIn("pg_verifybackup", text)
        self.assertIn("pg_hba_file_rules", text)
        self.assertIn("PGPASSFILE=/dev/null", text)
        self.assertIn('"${PG_LAB:?}"', text)
        self.assertNotIn("dropcluster 16 main", text)
        self.assertNotIn("0.0.0.0/0", text)
        self.assertNotIn("listen_addresses = '*'", text)
        # dropcluster appears only in reset, after the marker check
        reset = text[text.index("lab_reset()"):]
        self.assertLess(reset.index("dojo-lab-marker"), reset.index("pg_dropcluster"))
        self.assertEqual(text.count("pg_dropcluster \""), 1)


if __name__ == "__main__":
    unittest.main()
