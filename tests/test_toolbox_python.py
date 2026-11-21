"""Exercise real offline pip without modifying host Python or its packages."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_python import LABS


@unittest.skipUnless(shutil.which("python3") and shutil.which("bash"), "Python and Bash required")
class OfflinePipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(["python3", "-m", "ensurepip", "--version"], capture_output=True, timeout=15)
        if probe.returncode:
            raise unittest.SkipTest("pip付きvenv未導入: python3-venvが必要です。代替pipは使いません。")

    def run_script(self, root, script):
        return subprocess.run(["bash", "-c", script], cwd=root, capture_output=True,
                              text=True, timeout=90, stdin=subprocess.DEVNULL)

    def test_actual_pip_install_use_upgrade_freeze_and_isolation_on_fresh_wheels(self):
        lab = LABS["python-packages"]
        values = []
        for _ in range(2):
            with tempfile.TemporaryDirectory(prefix="dojo-offline-pip-") as folder:
                root = Path(folder)
                lab["setup"](root)
                with self.assertRaises((ValueError, OSError)):
                    lab["check"](root)
                result = self.run_script(root, lab["solution"])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                lab["check"](root)
                values.append((root / "v2.txt").read_text())
                (root / "requirements.lock").write_text("dojo-demo==1.0\n")
                with self.assertRaises(ValueError):
                    lab["check"](root)
        self.assertNotEqual(values[0], values[1], "exercise fixture must vary")

    def test_old_version_is_rejected_despite_completed_looking_outputs(self):
        lab = LABS["python-packages"]
        with tempfile.TemporaryDirectory(prefix="dojo-offline-pip-wrong-") as folder:
            root = Path(folder)
            lab["setup"](root)
            result = self.run_script(root, lab["wrong"][0])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with self.assertRaises(ValueError):
                lab["check"](root)

    def test_real_uninstall_and_reinstall_from_lock(self):
        lab = LABS["python-packages"]
        with tempfile.TemporaryDirectory(prefix="dojo-offline-pip-remove-") as folder:
            root = Path(folder)
            lab["setup"](root)
            result = self.run_script(root, lab["solution"])
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_script(root, ".venv/bin/python -m pip --isolated uninstall -y dojo-demo")
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaises(ValueError):
                lab["check"](root)
            result = self.run_script(root, ".venv/bin/python -m pip --isolated install --no-index --find-links wheels -r requirements.lock")
            self.assertEqual(result.returncode, 0, result.stderr)
            lab["check"](root)


if __name__ == "__main__":
    unittest.main()
