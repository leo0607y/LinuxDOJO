"""共通レイアウト部品（見出し・メニュー行・フッター・進捗バー・パレット）の回帰テスト。"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import ui  # noqa: E402


class LayoutTests(unittest.TestCase):
    def test_header_is_two_lines_and_fits_width(self):
        with patch.object(ui, "term_width", return_value=80):
            text = ui.strip_ansi(ui.header(["実践モード", "ステージ選択"], ui.progress_bar(0.5, 8) + " 3/6 問"))
        first, rule = text.split("\n")
        self.assertIn("LinuxDOJO", first)
        self.assertIn("ステージ選択", first)
        self.assertLessEqual(ui.width(first), 78)
        self.assertEqual(set(rule), {"─"})

    def test_menu_rows_align_descriptions_with_full_width_labels(self):
        with patch.object(ui, "term_width", return_value=80):
            rows = [ui.strip_ansi(ui.menu_row(k, label, "説明", label_w=20)) for k, label in
                    (("1", "続きから"), ("2", "Linux 常用コース"), ("q", "終了"))]
        columns = {ui.width(r[:r.index("説明")]) for r in rows}
        self.assertEqual(len(columns), 1)
        for row in rows:
            self.assertLessEqual(ui.width(row), 78)

    def test_menu_row_tag_does_not_shift_description(self):
        with patch.object(ui, "term_width", return_value=80):
            a = ui.strip_ansi(ui.menu_row("1", "基礎", "説明", label_w=8, tag="現在", tag_w=4))
            b = ui.strip_ansi(ui.menu_row("2", "応用", "説明", label_w=8, tag="", tag_w=4))
        self.assertEqual(ui.width(a[:a.index("説明")]), ui.width(b[:b.index("説明")]))

    def test_footer_drops_trailing_items_on_narrow_terminals(self):
        pairs = [("mission", "問題"), ("hint", "ヒント"), ("answer", "解答"), ("check", "判定"), ("menu", "戻る")]
        with patch.object(ui, "term_width", return_value=60):
            narrow = ui.strip_ansi(ui.footer(*pairs))
        with patch.object(ui, "term_width", return_value=110):
            wide = ui.strip_ansi(ui.footer(*pairs))
        self.assertLessEqual(ui.width(narrow), 60)
        self.assertIn("mission 問題", narrow)
        self.assertIn("menu 戻る", wide)

    def test_progress_bar_width_is_stable_and_never_looks_empty_or_full_by_rounding(self):
        for ratio in (0, 0.01, 0.5, 0.99, 1):
            self.assertEqual(ui.width(ui.progress_bar(ratio, 10)), 10)
        self.assertTrue(ui.strip_ansi(ui.progress_bar(0.01, 10)).startswith("█"))
        self.assertTrue(ui.strip_ansi(ui.progress_bar(0.99, 10)).endswith("░"))

    def test_start_palette_and_penguin_have_distinct_colors_and_stable_frames(self):
        self.assertEqual(len({ui.CODES[n] for n in ("blue", "magenta", "cyan")}), 3)
        frames = [ui.penguin_art(mood) for mood in ("ready", "blink", "wink", "happy")]
        self.assertEqual(len({len(ui.strip_ansi(f)) for f in frames}), 1)
        for frame in frames:
            self.assertEqual(len(frame.splitlines()), 7)
            self.assertIn("HELLO, COMMAND LINE.", frame)

    def test_intro_without_color_is_static_and_does_not_wait(self):
        import io
        output = io.StringIO()
        with patch.object(ui, "USE_COLOR", False), patch.object(ui.sys, "stdout", output), patch.object(ui.select, "select") as wait:
            ui.penguin_intro()
        wait.assert_not_called()
        self.assertNotIn("\x1b", output.getvalue())

    def test_no_color_output_has_no_escape_sequences(self):
        with patch.object(ui, "USE_COLOR", False):
            text = ui.header(["x"], "y") + ui.footer(("b", "戻る")) + ui.status_line("ok", "完了") + ui.box(["a"], title="t")
        self.assertNotIn("\x1b", text)

    def test_status_line_uses_text_markers(self):
        for kind, marker in (("ok", ui.OK), ("ng", ui.NG), ("warn", ui.WARN), ("info", ui.INFO)):
            self.assertIn(marker, ui.strip_ansi(ui.status_line(kind, "msg")))

    def test_box_keeps_every_row_the_same_width(self):
        with patch.object(ui, "USE_COLOR", False):
            rows = ui.box(["日本語の行", "ascii line", "" ], title="題名", w=40).split("\n")
        self.assertEqual({ui.width(r) for r in rows}, {40})


if __name__ == "__main__":
    unittest.main()
