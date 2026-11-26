"""同じ場所を指す別の書き方（./ ~/ 末尾の /）と、sudo が必要な課題の文面を確かめる。"""
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided
from curriculum.beginner_lessons import LESSONS


def find(lesson_id):
    return next(s for items in LESSONS.values() for s in items if s["id"] == lesson_id)


def attempt(lesson_id, lines):
    step = find(lesson_id)
    with tempfile.TemporaryDirectory() as work:
        terminal = guided.Terminal(Path(work) / "s", {})
        guided.prepare_step(terminal, step, fresh=True)
        ok = False
        for line in lines:
            result = terminal.execute(line)
            ok = guided.accepted(line, result, step, terminal)
        return ok


class AlternativeAnswersTest(unittest.TestCase):
    def test_same_place_spellings_are_accepted(self):
        for lesson_id, line in [("intro-05", "cat ./welcome.txt"), ("intro-05", "cat ~/welcome.txt"),
                                ("basic-06", "cat ./memo.txt"), ("basic-12", "grep Linux ./memo.txt"),
                                ("ex-archive_find-01", "find ./logs -name '*.log'"),
                                ("ex-archive_find-02", "find data/ -type f"),
                                ("ex-archive_find-10", "find ./logs -maxdepth 1 -type f")]:
            self.assertTrue(attempt(lesson_id, [line]), (lesson_id, line))

    def test_pattern_and_other_place_are_not_confused(self):
        self.assertFalse(attempt("basic-12", ["grep ./Linux memo.txt"]))
        self.assertFalse(attempt("basic-06", ["cat /home/learner/memo.txt"]))

    def test_tilde_is_the_practice_home(self):
        with tempfile.TemporaryDirectory() as work:
            terminal = guided.Terminal(Path(work) / "s", {})
            terminal.execute("echo hi > memo.txt")
            self.assertEqual(terminal.execute("cat ~/memo.txt").output.strip(), "hi")

    def test_lessons_needing_sudo_say_so(self):
        for lesson_id in ("ex-network-18", "ex-network-20", "ex-users-41", "ex-users-43"):
            self.assertIn("管理者権限", find(lesson_id)["task"])

    def test_wrong_sudo_use_gets_a_pointer(self):
        def note(lesson_id, line):
            step = find(lesson_id)
            with tempfile.TemporaryDirectory() as work:
                terminal = guided.Terminal(Path(work) / "s", {})
                guided.prepare_step(terminal, step, fresh=True)
                result = terminal.execute(line)
                self.assertFalse(guided.accepted(line, result, step, terminal))
                return guided.rejection_note(line, result, step)
        self.assertIn("sudo を付けずに", note("intro-20", "sudo apt update"))
        self.assertIn("sudo を付けずに", note("ex-users-23", "sudo chgrp developers report.txt"))
        self.assertIn("sudo を付けて", note("ex-network-20", "ufw delete allow 8080/tcp"))


if __name__ == "__main__":
    unittest.main()
