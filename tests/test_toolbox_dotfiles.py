"""Real dotfiles lab: solution passes, wrong or tampered outcomes fail."""
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

LAB = LABS["dotfiles"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入")
class DotfilesLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-dot-t-")
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
        def sub(name, old, new):
            return lambda r: (r / "home" / name).write_text((r / "home" / name).read_text().replace(old, new))
        mutations = {
            "original changed": lambda r: (r / "orig/.bashrc").write_text("x\n"),
            "spec changed": lambda r: (r / "spec.env").write_text("HIST_SIZE=1\n"),
            "no guard": sub(".bashrc", "case $- in *i*) ;; *) return ;; esac", ""),
            "dup path": sub(".bash_profile", 'case ":$PATH:" in *":$1:"*) ;; *) PATH="$1:$PATH" ;; esac', 'PATH="$1:$PATH"'),
            "profile does not source bashrc": sub(".bash_profile", '[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"', ""),
            "no histappend": sub(".bashrc", "histappend ", ""),
            "no mkdir": lambda r: (sub(".bashrc", 'mkdir -p "${HISTFILE%/*}"', "")(r), shutil.rmtree(r / "home/.local")),
            "xdg overwrite": sub(".bash_profile", "${XDG_STATE_HOME:-$HOME/.local/state}", "$HOME/.local/state"),
            "echo in rc": sub(".bashrc", "export EDITOR", "echo hi; export EDITOR"),
            "infinite loop": sub(".bashrc", "alias ll", "while :; do :; done; alias ll"),
            "syntax error": sub(".bashrc", "set -o noclobber", "if then"),
            "ready file cheat": lambda r: ((r / "home/.cache").mkdir(), (r / "home/.cache/ready").write_text("")),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)


if __name__ == "__main__":
    unittest.main()
