"""レッスンの品質テスト：答えを写すだけにならないか、ヒントは段階的か、別解・状態判定が働くか。

環境変数で絞り込める（作成中のファイルだけを確かめる用）:
    UNIT=archive_find  → id が ex-archive_find- で始まる達人モードのレッスン
    MODE=advanced      → そのモードのレッスン
"""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided
from curriculum.beginner_lessons import LESSONS


def selected():
    unit, mode = os.environ.get("UNIT"), os.environ.get("MODE")
    for name, course in LESSONS.items():
        if mode and name != mode:
            continue
        for index, step in enumerate(course):
            if unit and not step["id"].startswith(f"ex-{unit}-"):
                continue
            yield name, index, step


class LessonQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-units-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_no_lesson_reveals_its_answer(self):
        """課題文には答えを書かない。説明文にも、複数語の入力（引数まで含む1行）は書かない。

        単語1つだけの道具の名前は、初めて教えるときに説明文で紹介してよい（課題文には書かない）。
        はじめてモードの最初の5課題だけは入力するコマンドを表示するので例外。
        """
        for mode, index, step in selected():
            if mode == "intro" and index < guided.INTRO_SHOWN_ANSWERS:
                continue
            with self.subTest(lesson=step["id"]):
                for answer in guided.answers(step):
                    pattern = r"(?<![\w./-])" + re.escape(answer) + r"(?![\w./-])"
                    self.assertIsNone(re.search(pattern, step["task"]), f"{step['id']}: 課題文に答え {answer!r} が書かれています")
                    if len(answer.split()) > 1:
                        self.assertIsNone(re.search(pattern, step["explanation"]),
                                          f"{step['id']}: 説明文に答え {answer!r} が書かれています")

    def test_hints_offer_guidance_separately_from_answers(self):
        for mode, index, step in selected():
            if mode != "expert" and "hints" not in step:
                continue
            with self.subTest(lesson=step["id"]):
                hints = step.get("hints")
                self.assertIsInstance(hints, list, "hints（3段階）がありません")
                self.assertGreaterEqual(len(hints), 1)
                self.assertTrue(all(h.strip() for h in hints))
                command = step["command"]
                pattern = r"(?<![\w./-])" + re.escape(command) + r"(?![\w./-])"
                guidance = guided.guidance_hints(step)
                for hint in guidance:
                    if len(command.split()) > 1:
                        self.assertIsNone(re.search(pattern, hint), "完成した入力例は answer で表示する")

    def test_every_answer_is_accepted_from_a_fresh_start(self):
        for mode, index, step in selected():
            for number, answer in enumerate(guided.answers(step)):
                with self.subTest(lesson=step["id"], answer=answer):
                    terminal = guided.Terminal(self.base / step["id"] / str(number), {})
                    guided.prepare_step(terminal, step, fresh=True)
                    result = terminal.execute(answer)
                    self.assertTrue(guided.accepted(answer, result, step, terminal), result.output)

    def test_goal_lessons_start_unsolved_and_reject_unrelated_commands(self):
        for mode, index, step in selected():
            if "goal" not in step:
                continue
            with self.subTest(lesson=step["id"]):
                terminal = guided.Terminal(self.base / "g" / step["id"], {})
                guided.prepare_step(terminal, step, fresh=True)
                self.assertFalse(guided.goal_met(step, terminal), "最初から達成済みになっています")
                result = terminal.execute("pwd")
                self.assertFalse(guided.accepted("pwd", result, step, terminal))

    def test_expert_lessons_follow_the_unit_format(self):
        ids = set()
        for mode, index, step in selected():
            if mode != "expert":
                continue
            with self.subTest(lesson=step["id"]):
                self.assertRegex(step["id"], r"^ex-[a-z0-9_]+-\d\d$")
                self.assertNotIn(step["id"], ids)
                ids.add(step["id"])
                self.assertTrue(step.get("unit"))
                self.assertGreaterEqual(len(step["success"]), 12)

    def test_lessons_run_in_order_in_one_terminal(self):
        """課題を続けて解いても、前の課題の状態に引きずられて失敗しない。"""
        for mode, course in LESSONS.items():
            if os.environ.get("MODE") and mode != os.environ["MODE"]:
                continue
            terminal = guided.Terminal(self.base / "seq" / mode, {})
            for step in course:
                if os.environ.get("UNIT") and not step["id"].startswith(f"ex-{os.environ['UNIT']}-"):
                    continue
                with self.subTest(lesson=step["id"]):
                    guided.prepare_step(terminal, step)
                    result = terminal.execute(step["command"])
                    self.assertTrue(guided.accepted(step["command"], result, step, terminal), result.output)

    def test_hint_command_shows_one_stage_at_a_time(self):
        step = {"command": "ls -l", "hints": ["考え方", "道具は ls", "入力例: ls -l"]}
        self.assertEqual(guided.hint_text(step, 0), ("考え方", False))
        self.assertEqual(guided.hint_text(step, 2), ("道具は ls", True))
        self.assertEqual(guided.hint_text(step, 9)[1], True)
        auto, _ = guided.hint_text({"command": "ls -l"}, 1)
        self.assertIn("ls", auto)
        self.assertNotIn("ls -l", auto)


if __name__ == "__main__":
    unittest.main()
