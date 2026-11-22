"""Real debbuild lab: solution passes, wrong or tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS

LAB = LABS["debbuild"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class DebbuildLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-debbuild-")
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
            "deb removed": lambda r: (r / "dojo-hello_1.1-1_all.deb").unlink(),
            "deb replaced by v1": lambda r: shutil.copy(r / "dojo-hello_1.0-1_all.deb", r / "dojo-hello_1.1-1_all.deb"),
            "payload changed": lambda r: (r / "payload-v1/etc/dojo-hello.conf").write_text("greeting=x\n"),
            "info forged": lambda r: (r / "info.txt").write_text("new Debian package\n"),
            "contents forged": lambda r: (r / "contents.txt").write_text(""),
            "sysroot edit lost": lambda r: (r / "sysroot/etc/dojo-hello.conf").write_text("greeting=hello\n"),
            "sysroot marker removed": lambda r: (r / "sysroot/var/lib/dojo-hello/configured").unlink(),
            "dist removed": lambda r: (r / "sysroot/etc/dojo-hello.conf.dpkg-dist").unlink(),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
