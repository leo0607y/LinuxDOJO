"""Regression for the real GNU df failure found during the KVM storage lab."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash") and shutil.which("df") and sys.platform.startswith("linux"),
                     "This lab targets Linux and GNU df")
class StorageInodeTests(unittest.TestCase):
    def test_actual_inode_query_returns_a_number_and_rejects_a_missing_target(self):
        module = vm_labs.SOURCE / "guest/modules/storage.sh"
        with tempfile.TemporaryDirectory(prefix="dojo-inodes-") as temporary:
            for path, valid in ((Path(temporary), True), (Path(temporary) / "missing", False)):
                with self.subTest(path=path):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; STORAGE_MOUNT=$2; _storage_free_inodes',
                         "query", str(module), str(path)], capture_output=True, text=True, timeout=5)
                    if valid:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertTrue(result.stdout.strip().isdigit(), result.stdout)
                    else:
                        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
