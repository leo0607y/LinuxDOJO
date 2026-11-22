"""Real regex ladder lab: solution passes, wrong or tampered outcomes fail."""
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

LAB = LABS["regex"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入")
class RegexLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-regex-t-")
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

    def test_hard_coded_output_rejected(self):
        root = self.solved()
        visible = (root / "access.log").read_text()
        # t01 を見えているデータ専用の固定出力に差し替える
        text = (root / "answers.sh").read_text()
        lines = [l for l in text.splitlines() if not l.startswith("t01()")]
        fixed = "".join(l + "\n" for l in visible.splitlines() if " ERROR " in l or " WARN " in l)
        (root / "answers.sh").write_text("\n".join(lines) + "\nt01() { cat <<'EOF'\n" + fixed + "EOF\n}\n")
        with self.assertRaises(BAD):
            LAB["check"](root)

    def test_tampering_rejected(self):
        def sub(old, new):
            return lambda r: (r / "answers.sh").write_text((r / "answers.sh").read_text().replace(old, new))
        mutations = {
            "original changed": lambda r: (r / "answers.orig.sh").write_text("x\n"),
            "visible data changed": lambda r: (r / "access.log").write_text("x\n"),
            "greedy t07": sub("'s/^[^\"]*\"([^\"]*)\".*/\\1/'", "'s/^[^\"]*\"(.*)\".*/\\1/'"),
            "unanchored level": sub("'^[^ ]+ (ERROR|WARN) '", "'ERROR|WARN'"),
            "no -i": sub("grep -ci", "grep -c"),
            "perl": sub("t08() { sed -E", "t08() { perl -pe 's/.*msg=\"([^\"]*)\"$/$1/' \"$1\"; }; t99() { sed -E"),
            "syntax error": lambda r: (r / "answers.sh").write_text("t01() { if then\n"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
