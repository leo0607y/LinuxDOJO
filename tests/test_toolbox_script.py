"""Real bash scripting lab: solution passes, wrong or tampered outcomes fail."""
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

LAB = LABS["script"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入")
class ScriptLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-script-t-")
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
        def sub(old, new):
            return lambda r: (r / "tool.sh").write_text((r / "tool.sh").read_text().replace(old, new))
        mutations = {
            "restored": lambda r: (r / "tool.sh").write_text((r / "tool.orig.sh").read_text()),
            "original changed": lambda r: (r / "tool.orig.sh").write_text("#!/bin/bash\n"),
            "not executable": lambda r: (r / "tool.sh").chmod(0o644),
            "octal bug": sub("10#$size", "$size"),
            "exit code 1 lost": sub('exit "$bad"', "exit 0"),
            "usage code": sub("exit 2", "exit 1"),
            "no longest": sub('echo "longest=$longest"', "true"),
            "read without -r": sub("read -r path size", "read path size"),
            "syntax error": lambda r: (r / "tool.sh").write_text("#!/bin/bash\nif then\n"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
