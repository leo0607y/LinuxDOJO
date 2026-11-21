"""模擬 vim と「正解は1つではない」判定の回帰テスト。すべて一時領域で実行。"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, runner, save


def all_steps():
    from curriculum.beginner_lessons import LESSONS
    for mode, course in LESSONS.items():
        for step in course:
            yield mode, step


class FlexibleAnswerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-answers-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_every_listed_answer_is_accepted_from_a_fresh_start(self):
        for mode, step in all_steps():
            for number, answer in enumerate(guided.answers(step)):
                with self.subTest(lesson=step["id"], answer=answer):
                    terminal = guided.Terminal(self.base / mode / step["id"] / str(number), {})
                    guided.prepare_step(terminal, step, fresh=True)
                    result = terminal.execute(answer)
                    self.assertTrue(guided.accepted(answer, result, step, terminal), result.output)

    def test_goal_lessons_are_not_already_solved_before_any_input(self):
        for mode, step in all_steps():
            if "goal" not in step:
                continue
            with self.subTest(lesson=step["id"]):
                terminal = guided.Terminal(self.base / mode / step["id"], {})
                guided.prepare_step(terminal, step, fresh=True)
                self.assertFalse(guided.goal_met(step, terminal))

    def test_unrelated_successful_command_does_not_solve_a_goal_lesson(self):
        for mode, step in all_steps():
            if "goal" not in step or step.get("editor"):
                continue
            with self.subTest(lesson=step["id"]):
                terminal = guided.Terminal(self.base / mode / step["id"], {})
                guided.prepare_step(terminal, step, fresh=True)
                result = terminal.execute("pwd")
                self.assertFalse(guided.accepted("pwd", result, step, terminal))

    def test_goal_accepts_a_route_not_listed_in_the_lesson(self):
        from curriculum.beginner_lessons import BASIC
        step = next(s for s in BASIC if s["id"] == "basic-16")  # chmod u+x script.sh
        terminal = guided.Terminal(self.base / "goal", {})
        guided.prepare_step(terminal, step, fresh=True)
        self.assertNotIn("chmod 744 script.sh", guided.answers(step))
        result = terminal.execute("chmod 744 script.sh")  # 登録していない書き方でも、結果が合えば正解
        self.assertTrue(guided.accepted("chmod 744 script.sh", result, step, terminal))


class VimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-vim-test-")
        self.addCleanup(self.tmp.cleanup)
        self.progress = {"packages": ["vim"]}
        self.term = guided.Terminal(Path(self.tmp.name) / "vim", self.progress)

    def run_keys(self, *keys):
        return [self.term.execute(key) for key in keys]

    def test_vim_must_be_installed_first(self):
        self.progress["packages"] = []
        result = self.term.execute("vim memo.txt")
        self.assertEqual(result.code, 127)
        self.assertIn("sudo apt install vim", result.output)
        self.assertNotEqual(self.term.execute("which vim").code, 0)
        self.term.execute("sudo apt update")
        self.assertEqual(self.term.execute("sudo apt install -y vim").code, 0)
        self.assertEqual(self.term.execute("which vim").output, "/usr/bin/vim")
        self.assertEqual(self.term.execute("vim memo.txt").code, 0)

    def test_write_lines_and_save(self):
        self.run_keys("vim memo.txt", "i", "1行目", "  字下げした行", "esc", ":wq")
        self.assertIsNone(self.progress["editor"])
        self.assertEqual((self.term.root / "memo.txt").read_text(encoding="utf-8"), "1行目\n  字下げした行\n")
        self.assertIn("vim memo.txt", self.progress["history"])
        self.assertNotIn(":wq", self.progress["history"])

    def test_quit_refuses_unsaved_changes_and_force_quit_discards(self):
        (self.term.root / "draft.txt").write_text("元\n", encoding="utf-8")
        results = self.run_keys("vim draft.txt", "o", "追加", "esc", ":q")
        self.assertEqual(results[-1].code, 1)
        self.assertIn("E37", results[-1].output)
        self.assertIsNotNone(self.progress["editor"])
        self.term.execute(":q!")
        self.assertIsNone(self.progress["editor"])
        self.assertEqual((self.term.root / "draft.txt").read_text(encoding="utf-8"), "元\n")

    def test_delete_undo_copy_paste_and_search(self):
        (self.term.root / "todo.txt").write_text("a\nb\nERROR c\n", encoding="utf-8")
        self.run_keys("vim todo.txt", "j", "dd")
        self.assertEqual(self.progress["editor"]["lines"], ["a", "ERROR c"])
        self.term.execute("u")
        self.assertEqual(self.progress["editor"]["lines"], ["a", "b", "ERROR c"])
        self.run_keys("gg", "yy", "p")
        self.assertEqual(self.progress["editor"]["lines"], ["a", "a", "b", "ERROR c"])
        self.term.execute("/ERROR")
        self.assertEqual(self.progress["editor"]["cursor"], 3)
        self.assertEqual(self.term.execute("/missing").code, 1)

    def test_typing_text_in_normal_mode_explains_insert_mode(self):
        self.term.execute("vim memo.txt")
        result = self.term.execute("hello")
        self.assertEqual(result.code, 1)
        self.assertIn("i を入力", result.output)
        self.assertEqual(self.progress["editor"]["lines"], [])

    def test_escape_key_and_inline_insert_work(self):
        self.run_keys("vim memo.txt", "iこんにちは\x1b")
        self.assertEqual(self.progress["editor"]["mode"], "normal")
        self.assertEqual(self.progress["editor"]["lines"], ["こんにちは"])

    def test_editor_cannot_write_outside_the_practice_folder(self):
        self.assertNotEqual(self.term.execute("vim ../outside.txt").code, 0)
        self.assertIsNone(self.progress["editor"])
        self.term.execute("vim memo.txt")
        self.progress["editor"]["key"] = "../outside.txt"  # 改ざんされたセーブを想定
        self.run_keys("i", "x", "esc")
        result = self.term.execute(":wq")
        self.assertEqual(result.code, 1)
        self.assertFalse((self.term.root.parent / "outside.txt").exists())

    def test_open_editor_survives_restart_of_the_terminal(self):
        self.run_keys("vim memo.txt", "i", "途中まで")
        again = guided.Terminal(self.term.root, self.progress)
        self.assertIn("INSERT", again.prompt_text())
        again.execute("esc")
        again.execute(":wq")
        self.assertEqual((self.term.root / "memo.txt").read_text(encoding="utf-8"), "途中まで\n")


class VimCoursePlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-vim-play-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        for p in (patch.object(save, "SAVE", self.base / "save.json"),
                  patch.object(runner, "WORKSPACE", self.base / "workspace"),
                  patch.object(guided.ui, "clear")):
            p.start()
            self.addCleanup(p.stop)

    def test_learner_text_is_kept_from_open_to_save(self):
        course = guided.lessons("basic")
        start = next(i for i, s in enumerate(course) if s["id"] == "basic-54")
        keys = ["vim memo.txt", "", "i", "", "自分で考えた文", "", "esc", "", "ZZ", "", "cat memo.txt", "menu"]
        out = io.StringIO()
        with patch("builtins.input", side_effect=keys), contextlib.redirect_stdout(out):
            guided.play("basic", start=start)
        text = (self.base / "workspace/learning_basic/memo.txt").read_text(encoding="utf-8")
        self.assertEqual(text, "自分で考えた文\n")
        self.assertIn("ほかの書き方でも正解です: :wq / :x", out.getvalue())
        completed = guided.progress_for("basic")["completed"]
        for lesson_id in ("basic-54", "basic-55", "basic-56", "basic-57", "basic-58", "basic-59"):
            self.assertIn(lesson_id, completed)


if __name__ == "__main__":
    unittest.main()
