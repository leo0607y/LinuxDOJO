"""Real backup lab: solution passes on fresh fixtures; wrong, partial and tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import curriculum.toolbox_labs3  # noqa: F401  registers the lab
from curriculum.toolbox_labs import LABS

LAB = LABS["backup"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", script], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=240)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class BackupLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-backup-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        LAB["setup"](root)
        return root

    def solved(self, script=None):
        root = self.fresh()
        result = sh(root, script or LAB["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return root

    def rejected(self, script):
        root = self.fresh()
        sh(root, script)
        with self.assertRaises(BAD):
            LAB["check"](root)

    def test_solution_passes_with_fresh_fixtures(self):
        for _ in range(2):
            root = self.fresh()
            with self.assertRaises(BAD):
                LAB["check"](root)
            sh(root, LAB["solution"])
            LAB["check"](root)

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                self.rejected(wrong)

    def variant(self, old, new):
        self.assertIn(old, LAB["solution"])
        self.rejected(LAB["solution"].replace(old, new, 1))

    def tamper(self, mutate):
        root = self.solved()
        LAB["check"](root)
        mutate(root)
        with self.assertRaises(BAD):
            LAB["check"](root)

    def test_tampering_rejected(self):
        cases = {
            "restore-one wrong": lambda r: next((r / "restore-one").rglob("notes.txt")).write_text("x"),
            "restore-full missing file": lambda r: next((r / "restore-full").rglob("keep.txt")).unlink(),
            "source data changed": lambda r: (r / "data/keep.txt").write_text("changed"),
            "exit code faked": lambda r: (r / "broken-check.exit").write_text("0\n"),
            "diff empty": lambda r: (r / "diff.txt").write_text(""),
            "broken repo is healthy": lambda r: (shutil.rmtree(r / "repo-broken"), shutil.copytree(r / "repo", r / "repo-broken")),
            "repo gone": lambda r: shutil.rmtree(r / "repo"),
            "password changed": lambda r: (r / "password.txt").write_text("new\n"),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.tamper(mutate)

    def test_forget_without_prune_or_wrong_policy_rejected(self):
        self.variant("forget --keep-last 2 --prune", "forget --keep-last 2")
        self.variant("forget --keep-last 2 --prune", "forget --keep-last 1 --prune")

    def test_noncorrupt_copy_rejected(self):
        self.variant("printf 'corruption' >> \"$pack\"", "true")


if __name__ == "__main__":
    unittest.main()
