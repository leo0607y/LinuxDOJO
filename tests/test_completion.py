"""Tab 補完 (模擬ターミナル側の候補計算) の回帰テスト。状態を変えず、実環境に触れない。"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-complete-")
        self.addCleanup(self.tmp.cleanup)
        self.term = guided.Terminal(Path(self.tmp.name) / "course", {})
        self.term.execute("mkdir notes")
        self.term.execute("touch notes/todo.txt")

    def test_command_names(self):
        start, found = self.term.complete("ec")
        self.assertEqual((start, found), (0, ["echo"]))
        self.assertIn("cat", self.term.complete("c")[1])

    def test_files_and_directories(self):
        self.assertEqual(self.term.complete("cat wel"), (4, ["welcome.txt"]))
        self.assertEqual(self.term.complete("cd no"), (3, ["notes/"]))
        self.assertEqual(self.term.complete("cat notes/t"), (4, ["notes/todo.txt"]))

    def test_hidden_files_only_when_asked(self):
        self.assertNotIn(".memo", self.term.complete("cat ")[1])
        self.assertEqual(self.term.complete("cat .m"), (4, [".memo"]))
        self.assertNotIn(".remote", self.term.complete("ls .")[1])

    def test_no_completion_for_options_quotes_or_missing(self):
        self.assertEqual(self.term.complete("ls -")[1], [])
        self.assertEqual(self.term.complete("echo 'wel")[1], [])
        self.assertEqual(self.term.complete("cat zzz")[1], [])
        self.assertEqual(self.term.complete("cat /etc/pa")[1], [])
        self.assertEqual(self.term.complete("cat ../")[1], [])

    def test_does_not_change_state(self):
        before = dict(self.term.progress)
        self.term.complete("cat wel")
        self.assertEqual(before, self.term.progress)


if __name__ == "__main__":
    unittest.main()
