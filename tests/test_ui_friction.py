"""メニュー操作の分かりやすさ（無効入力の案内・戻り方の表示・絵文字なし）の回帰テスト。"""
import contextlib
import io
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cli, main, runner, toolbox, ui  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⭐✅❌]")


class FlashTests(unittest.TestCase):
    def test_invalid_choice_is_shown_once_and_names_valid_choices(self):
        ui.take_flash()
        ui.invalid_choice("zzz", "1〜9 か q")
        text = ui.strip_ansi(ui.take_flash())
        self.assertIn("「zzz」は選べません", text)
        self.assertIn("1〜9 か q", text)
        self.assertEqual(ui.take_flash(), "")

    def test_very_long_input_is_clipped(self):
        ui.take_flash()
        ui.invalid_choice("あ" * 500, "b")
        self.assertLess(len(ui.strip_ansi(ui.take_flash())), 120)


class MenuTests(unittest.TestCase):
    def run_main_menu(self, answers):
        out = io.StringIO()
        with patch.object(main, "ask", side_effect=answers), \
             patch.object(main, "header", return_value=""), \
             patch.object(main, "practice_resume", return_value=None), \
             patch.object(main.guided, "selected_mode", return_value="practice"), \
             patch.object(main.ui, "clear"), contextlib.redirect_stdout(out):
            main.main_menu()
        return ui.strip_ansi(out.getvalue())

    def test_main_menu_explains_unknown_input_and_how_to_quit(self):
        text = self.run_main_menu(["zzz", "q"])
        self.assertIn("「zzz」は選べません", text)
        self.assertIn("終了は q", text)
        self.assertIn("次回は", text)

    def run_toolbox(self, answers):
        out = io.StringIO()
        with patch("builtins.input", side_effect=answers), patch.object(ui, "clear"), \
             contextlib.redirect_stdout(out):
            toolbox.menu()
        return ui.strip_ansi(out.getvalue())

    def test_toolbox_menu_reports_unknown_menu_choice(self):
        self.assertIn("「xx」は選べません", self.run_toolbox(["xx", "b"]))

    def test_toolbox_search_without_hits_and_unknown_lab_tell_what_to_do(self):
        text = self.run_toolbox(["1", "存在しない言葉zzz", "", "2", "nosuch", "", "b"])
        self.assertIn("該当する分野がありません", text)
        self.assertIn("「nosuch」という実習はありません", text)
        self.assertIn("戻る（メインメニューへ）", text)


class PathAndLauncherTests(unittest.TestCase):
    def test_mission_path_outside_project_does_not_crash(self):
        self.assertEqual(cli._shown_path(Path("/somewhere/else/stage_01")), "/somewhere/else/stage_01")
        self.assertEqual(cli._shown_path(ROOT / "workspace" / "stage_01"), "workspace/stage_01")

    def test_launchers_have_no_emoji(self):
        for name in ("start.sh", "install-start.sh", "start.bat"):
            self.assertIsNone(EMOJI.search((ROOT / name).read_text(encoding="utf-8")), name)


if __name__ == "__main__":
    unittest.main()
