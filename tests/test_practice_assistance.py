"""実践モードの可変段階ヒントと、解答閲覧から自力復習への導線。"""
import contextlib
from dataclasses import replace
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import cli, main, runner, save


class PracticeAssistanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dojo-practice-assistance-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.mission = runner.get_mission("1-1")
        for obj, name, value in ((cli, "STATE", self.state),
                                 (runner, "STATE", self.state),
                                 (runner, "WORKSPACE", self.base / "workspace"),
                                 (save, "SAVE", self.base / "save.json")):
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(cli, "_mission", return_value=self.mission)
        self.get_mission = p.start()
        self.addCleanup(p.stop)
        p = patch.object(cli, "_tty", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def capture(self, fn, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = fn(*args)
        return result, stream.getvalue()

    def test_wrapped_or_backticked_full_solution_is_not_a_hint(self):
        mission = replace(self.mission, answer="echo complete", solution="echo complete",
                          hints=["入力例（実行前に確認）:\n`echo complete`"])
        self.assertEqual(runner.hint_steps(mission), [])

    def test_any_number_of_hints_is_available_without_exposing_answer(self):
        hints = [f"助言その{i}" for i in range(1, 6)]
        mission = replace(self.mission, hints=hints + [self.mission.answer])
        self.get_mission.return_value = mission
        for _ in range(7):
            _, output = self.capture(cli.cmd_hint, [])
        self.assertEqual(cli._hint_level(), 5)
        self.assertIn("助言その5", output)
        self.assertIn("HINT 5/5", output)
        self.assertNotIn(mission.answer.strip(), output)
        self.assertEqual(save.review_ids(save.load(), "practice"), [])
        self.assertEqual(save.load()["stats"]["hints"], 5)
        _, output = self.capture(cli.cmd_mission)
        self.assertIn("ヒント 5/5", output)

    def test_single_hint_and_explicit_large_hint_number(self):
        self.get_mission.return_value = replace(self.mission, hints=["手がかりを比べましょう"])
        _, output = self.capture(cli.cmd_hint, ["99"])
        self.assertIn("HINT 1/1", output)
        self.assertEqual(cli._hint_level(), 1)

    def test_legacy_final_command_example_is_reserved_for_answer(self):
        mission = replace(self.mission, hints=["考え方", "入力例: " + self.mission.answer])
        self.assertEqual(runner.hint_steps(mission), ["考え方"])

    def test_answer_immediately_adds_uncleared_mission_and_counts_once(self):
        for _ in range(2):
            self.capture(cli.cmd_answer)
        d = save.load()
        self.assertEqual(save.review_ids(d, "practice"), [self.mission.id])
        self.assertNotIn(self.mission.id, d["cleared"])
        self.assertEqual(d["stats"]["answers"], 1)

    def test_cancelled_answer_does_not_mark_review(self):
        with patch.object(cli, "_tty", return_value=True), patch("builtins.input", return_value="n"):
            self.capture(cli.cmd_answer)
        self.assertFalse(cli._answer_viewed())
        self.assertEqual(save.review_ids(save.load(), "practice"), [])

    def test_review_survives_assisted_clear_and_reset_until_independent_clear(self):
        self.capture(cli.cmd_answer)
        self.capture(cli.celebrate, self.mission)
        self.assertIn(self.mission.id, save.review_ids(save.load(), "practice"))
        runner.prepare(self.mission, runner.new_token())
        self.assertFalse(cli._answer_viewed())
        self.capture(cli.cmd_hint, [])
        self.capture(cli.celebrate, self.mission)
        self.assertIn(self.mission.id, save.review_ids(save.load(), "practice"))
        runner.prepare(self.mission, runner.new_token())
        self.capture(cli.celebrate, self.mission)
        self.assertNotIn(self.mission.id, save.review_ids(save.load(), "practice"))
        self.assertEqual(save.load()["cleared"][self.mission.id]["score"], self.mission.points)

    def test_review_list_reopens_uncleared_mission_without_stale_ids(self):
        d = save.empty()
        save.mark_review(d, "practice", self.mission.id)
        save.mark_review(d, "practice", "removed-mission")
        save.mark_review(d, "basic", "basic-01")
        save.store(d)
        with patch.object(main, "header", return_value="復習"), \
             patch.object(main.ui, "clear"), \
             patch.object(main, "ask", return_value="1"), \
             patch.object(main, "play", return_value="menu") as play:
            result, output = self.capture(main.review_select)
        self.assertEqual(result, "menu")
        play.assert_called_once_with(self.mission)
        self.assertIn(self.mission.id, output)
        self.assertNotIn("removed-mission", output)
        self.assertNotIn("basic-01", output)


if __name__ == "__main__":
    unittest.main()
