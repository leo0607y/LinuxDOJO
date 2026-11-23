"""答えを見て中断した問題も残し、自力の再挑戦でだけ復習対象から外す。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided, runner, save


class GuidedReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-review-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.save_patch = patch.object(save, "SAVE", self.root / "save.json")
        self.workspace_patch = patch.object(runner, "WORKSPACE", self.root / "workspace")
        self.save_patch.start()
        self.workspace_patch.start()
        self.addCleanup(self.save_patch.stop)
        self.addCleanup(self.workspace_patch.stop)

    def play(self, commands, start=None):
        output = io.StringIO()
        with patch("builtins.input", side_effect=commands), contextlib.redirect_stdout(output):
            guided.play("basic", start=start)
        return output.getvalue()

    def test_wrapped_answer_is_filtered_out_of_guided_hints(self):
        step = {"id": "test", "command": "echo hello",
                "hints": ["入力例（確認用）:\n`echo hello`"]}
        self.assertEqual(guided.guidance_hints(step), [])

    def test_answer_immediately_saves_unsolved_review_and_survives_resume(self):
        self.play(["answer", "menu"])
        data = save.load()
        self.assertEqual(save.review_ids(data, "basic"), ["basic-01"])
        self.assertNotIn("basic-01", data["learning"]["basic"]["completed"])
        self.play(["pwd", "menu"])
        self.assertEqual(save.review_ids(save.load(), "basic"), ["basic-01"])

    def test_reset_then_unassisted_completion_removes_review(self):
        self.play(["answer", "reset", "pwd", "menu"])
        data = save.load()
        self.assertEqual(save.review_ids(data, "basic"), [])
        self.assertIn("basic-01", data["learning"]["basic"]["completed"])

    def test_hint_after_reset_prevents_removal(self):
        self.play(["answer", "reset", "hint", "pwd", "menu"])
        self.assertEqual(save.review_ids(save.load(), "basic"), ["basic-01"])

    def test_selection_starts_a_new_independent_attempt(self):
        self.play(["answer", "pwd", "menu"])
        self.play(["pwd", "menu"], start=0)
        self.assertEqual(save.review_ids(save.load(), "basic"), [])
        self.play(["answer", "menu"], start=0)
        self.assertEqual(save.review_ids(save.load(), "basic"), ["basic-01"])

    def test_review_filter_keeps_original_lesson_numbers(self):
        self.play(["answer", "menu"], start=17)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["r", "18", "b"]), patch.object(guided, "play") as play, contextlib.redirect_stdout(output):
            guided.lesson_select("basic")
        play.assert_called_once_with("basic", 17)
        self.assertIn("復習対象", output.getvalue())

    def test_hint_count_is_arbitrary_and_completed_example_is_separate(self):
        step = {"command": "ls -l", "hints": ["考え方", "対象を調べる", "ls を使う", "表示形式を考える", "詳しい一覧は -l", "入力例: ls -l"]}
        for level, hint in enumerate(step["hints"][:-1]):
            self.assertEqual(guided.hint_text(step, level), (hint, level == 4))
        self.assertEqual(guided.hint_text(step, 100), (step["hints"][4], True))
        self.assertNotIn("ls -l", guided.hint_text(step, 100)[0])
        self.assertTrue(guided.hint_text({"command": "pwd", "hints": []}, 0)[1])

    def test_legacy_save_preserves_completion_when_review_is_added(self):
        data = save.empty()
        del data["review"]
        data["learning"]["basic"]["completed"] = ["basic-01"]
        save.SAVE.write_text(json.dumps(data))
        loaded = save.load()
        self.assertEqual(loaded["review"], {})
        self.assertEqual(loaded["learning"]["basic"]["completed"], ["basic-01"])


if __name__ == "__main__":
    unittest.main()
