"""Native workflows reject incomplete/wrong outcomes and run against fresh data.

Unavailable executables are explicit skips, never simulated as a successful lab.
The CLI's doctor reports the same dependencies before learners start a lab.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS


class NativeToolboxTests(unittest.TestCase):
    def run_script(self, root, script):
        # No automatic package installation; the exercise's declared tools must exist.
        return subprocess.run(["bash", "-c", script], cwd=root,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=60)

    def exercise(self, id):
        lab = LABS[id]
        missing = [tool for tool in lab["tools"] if not shutil.which(tool)]
        if missing:
            self.skipTest("実ツール未導入: " + ", ".join(missing))
        for attempt in range(2):
            with self.subTest(id=id, fresh_fixture=attempt):
                with tempfile.TemporaryDirectory(prefix="dojo-native-") as temporary:
                    root = Path(temporary)
                    lab["setup"](root)
                    with self.assertRaises((ValueError, AssertionError, OSError)):
                        lab["check"](root)
                    result = self.run_script(root, lab["solution"])
                    self.assertEqual(result.returncode, 0,
                                     f"{id} solution failed:\n{result.stdout}\n{result.stderr}")
                    lab["check"](root)
        for wrong in lab["wrong"]:
            with self.subTest(id=id, wrong=wrong):
                with tempfile.TemporaryDirectory(prefix="dojo-native-wrong-") as temporary:
                    root = Path(temporary)
                    lab["setup"](root)
                    self.run_script(root, wrong)
                    with self.assertRaises((ValueError, AssertionError, OSError)):
                        lab["check"](root)

    def test_moved_bytes_and_backup_target_cannot_be_faked(self):
        cases = (
            ("find", lambda root: next((root / "quarantine").iterdir()).write_text("lost data")),
            ("archive", lambda root: (root / "backup.sha256").write_text("")),
            ("release", lambda root: (root / "deployed/run.sh").write_text("#!/bin/sh\nprintf 'ready\\n'\n")),
        )
        for id, mutate in cases:
            with self.subTest(id=id):
                missing = [tool for tool in LABS[id]["tools"] if not shutil.which(tool)]
                if missing:
                    continue
                with tempfile.TemporaryDirectory(prefix="dojo-native-tamper-") as temporary:
                    root = Path(temporary)
                    LABS[id]["setup"](root)
                    result = self.run_script(root, LABS[id]["solution"])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    LABS[id]["check"](root)
                    mutate(root)
                    with self.assertRaises((ValueError, AssertionError, OSError)):
                        LABS[id]["check"](root)

    def test_catalog_has_concrete_native_workflows(self):
        self.assertEqual(len(LABS), 18)
        for id, lab in LABS.items():
            with self.subTest(id=id):
                for field in ("title", "tools", "packages", "task", "solution", "wrong"):
                    self.assertTrue(lab[field])
                self.assertTrue(callable(lab["setup"]))
                self.assertTrue(callable(lab["check"]))


for _id in LABS:
    def _test(self, id=_id):
        self.exercise(id)
    setattr(NativeToolboxTests, "test_native_" + _id, _test)


if __name__ == "__main__":
    unittest.main()
