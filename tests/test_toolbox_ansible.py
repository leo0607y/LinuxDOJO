"""Real ansible lab: solution passes on fresh fixtures; wrong, partial and tampered outcomes fail."""
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

LAB = LABS["ansible"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", script], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=240)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class AnsibleLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-ansible-")
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
            "second run not idempotent": lambda r: (r / "second.txt").write_text("localhost : ok=3 changed=2 unreachable=0 failed=0\n"),
            "check output missing": lambda r: (r / "check.txt").write_text(""),
            "target drifted": lambda r: (r / "target/motd").write_text("drift\n"),
            "inventory changed": lambda r: (r / "inventory.ini").write_text("[x]\n"),
            "handler.log doubled": lambda r: (r / "target/handler.log").write_text("reload\nreload\n"),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.tamper(mutate)

    def test_playbook_mistakes_rejected(self):
        self.variant('mode: "0750"', 'mode: "0755"')
        self.variant("notify: reload app", "")
        self.variant('        line: "port={{ app_port }}"\n        regexp: \'^port=\'\n',
                     '        line: "port={{ app_port }}"\n        regexp: \'^nomatch=\'\n')   # appends every run


if __name__ == "__main__":
    unittest.main()
