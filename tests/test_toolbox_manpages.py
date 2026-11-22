"""Real manpages lab: solution passes, wrong or tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS
import curriculum.toolbox_labs2  # noqa: F401

LAB = LABS["manpages"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入")
class ManpagesLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-man-t-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        try:
            LAB["setup"](root)
        except ValueError as error:
            self.skipTest(str(error))
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
        for _ in range(6):  # 変種が全部出るよう複数回
            self.solved()

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                root = self.fresh()
                sh(root, wrong)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_tampering_rejected(self):
        def sub(old, new):
            return lambda r: (r / "answers.txt").write_text((r / "answers.txt").read_text().replace(old, new))
        mutations = {
            "questions changed": lambda r: (r / "questions.txt").write_text("x\n"),
            "grep codes swapped": sub("Q2=1 2", "Q2=2 1"),
            "sort stable": sub("Q3=no", "Q3=yes"),
            "danger exec": lambda r: (r / "answers.txt").write_text(
                (r / "answers.txt").read_text().replace("Q1=", "Q1=-exec rm {} ; #")),
            "blank answer": sub("Q5=--strip-components", "Q5x=--strip-components"),
            "shell injection": sub("Q2=1 2", "Q2=1 2; rm -rf x"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
