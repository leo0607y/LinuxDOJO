"""aws(ローカルmoto)/zsh/fish/stowの実ツールで解答と誤答を判定する。未導入ツールは明示的にskip。"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS
import curriculum.toolbox_labs5 as labs5

BAD = (ValueError, AssertionError, OSError)
IDS = ("awscli-s3", "awscli-query", "zsh", "fish", "stow")


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)


class CloudShellLabs(unittest.TestCase):
    def fresh(self, id):
        lab = LABS[id]
        missing = [t for t in lab["tools"] if not shutil.which(t)]
        if missing:
            self.skipTest("実ツール未導入: " + ", ".join(missing))
        temporary = tempfile.TemporaryDirectory(prefix="dojo-cloudshell-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        lab["setup"](root)
        self.addCleanup(self.stop, root)
        return lab, root

    @staticmethod
    def stop(root):
        import json
        try:
            labs5._stop_emulator(json.loads((root / ".fixture.json").read_text()).get("pid"))
        except (OSError, ValueError):
            pass

    def test_solutions_pass_and_empty_state_fails(self):
        for id in IDS:
            with self.subTest(id=id):
                lab, root = self.fresh(id)
                with self.assertRaises(BAD):
                    lab["check"](root)
                result = sh(root, lab["solution"])
                self.assertEqual(result.returncode, 0, id + "\n" + result.stdout + result.stderr)
                lab["check"](root)

    def test_wrong_answers_fail(self):
        for id in IDS:
            with self.subTest(id=id):
                lab, root = self.fresh(id)
                for wrong in lab["wrong"]:
                    sh(root, wrong)
                    with self.assertRaises(BAD):
                        lab["check"](root)

    def test_real_endpoint_in_config_rejected(self):
        lab, root = self.fresh("awscli-s3")
        sh(root, lab["solution"])
        (root / "aws/config").write_text((root / "aws/config").read_text()
                                         + "\n[services x]\nendpoint_url = https://s3.amazonaws.com\n")
        with self.assertRaises(ValueError):
            lab["check"](root)

    def test_adopt_is_detected(self):
        lab, root = self.fresh("stow")
        sh(root, lab["solution"])
        (root / "home/dotfiles/shell/.bashrc").write_text("adopted\n")
        with self.assertRaises(ValueError):
            lab["check"](root)

    def test_fixtures_vary(self):
        values = set()
        for _ in range(2):
            lab, root = self.fresh("zsh")
            values.add((root / "vars.zsh").read_text())
        self.assertEqual(len(values), 2)


if __name__ == "__main__":
    unittest.main()
