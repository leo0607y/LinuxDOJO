"""Real unprivileged logrotate lab: solution passes, wrong or tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS

LAB = LABS["logrotate"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(shutil.which("logrotate") and shutil.which("gzip"), "実ツール未導入: logrotate")
class LogrotateLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-logrotate-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        LAB["setup"](root)
        return root

    def solved(self):
        root = self.fresh()
        with self.assertRaises(BAD):
            LAB["check"](root)
        result = sh(root, LAB["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        LAB["check"](root)
        return root

    def test_solution_passes_with_fresh_fixtures(self):
        self.solved()
        self.solved()

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                root = self.fresh()
                sh(root, wrong)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_tampering_rejected(self):
        mutations = {
            "lost lines": lambda r: (r / "app.log.1").write_text("seq 000001 event\n"),
            "fake gzip": lambda r: (r / "app.log.2.gz").write_text("not gzip"),
            "extra generation": lambda r: (r / "app.log.4.gz").write_bytes(b"x"),
            "writer changed": lambda r: (r / "writer.sh").write_text("#!/bin/sh\n"),
            "no dry run": lambda r: (r / "dry-run.txt").write_text(""),
            "no copytruncate": lambda r: (r / "rotate.conf").write_text(
                (r / "rotate.conf").read_text().replace("copytruncate", "")),
            "inode replaced": lambda r: ((r / "app.log").rename(r / "x"), (r / "app.log").write_text("")),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
