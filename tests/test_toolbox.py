"""Native tool availability, safe setup/resume and evidence-based completion."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import toolbox


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dojo-toolbox-engine-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def setup(path):
            (path / "input").write_text("original")
        def check(path):
            if (path / "input").read_text() != "original":
                raise ValueError("原本を変更しています。")
            if (path / "answer").read_text() != "correct":
                raise ValueError("結果が異なります。")
        self.lab = {"title": "test", "task": "produce correct", "tools": ["bash"],
                    "packages": ["bash"], "solution": "printf correct > answer", "setup": setup, "check": check}
        self.patcher = patch.object(toolbox, "labs", return_value={"test": self.lab})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.directory = self.root / "exercise"

    def test_missing_tools_block_setup_and_cannot_retain_a_pass(self):
        with patch.object(toolbox.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "未導入"):
                toolbox.setup("test", self.directory)
        self.assertFalse(self.directory.exists())
        toolbox.setup("test", self.directory)
        (self.directory / "answer").write_text("correct")
        self.assertTrue(toolbox.check(self.directory)[0])
        with patch.object(toolbox.shutil, "which", return_value=None):
            self.assertFalse(toolbox.check(self.directory)[0])
        self.assertFalse(json.loads((self.directory / ".dojo/state.json").read_text())["passed"])

    def test_completion_is_rechecked_and_wrong_or_modified_inputs_fail(self):
        toolbox.setup("test", self.directory)
        self.assertFalse(toolbox.check(self.directory)[0])
        (self.directory / "answer").write_text("wrong")
        self.assertFalse(toolbox.check(self.directory)[0])
        (self.directory / "answer").write_text("correct")
        self.assertTrue(toolbox.check(self.directory)[0])
        (self.directory / "input").write_text("modified")
        self.assertFalse(toolbox.check(self.directory)[0])

    def test_setup_never_overwrites_an_existing_directory_or_follows_a_link(self):
        self.directory.mkdir()
        (self.directory / "keep").write_text("keep")
        with self.assertRaises(ValueError):
            toolbox.setup("test", self.directory)
        self.assertEqual((self.directory / "keep").read_text(), "keep")
        link = self.root / "link"
        link.symlink_to(self.directory, target_is_directory=True)
        for destination in (link, link / "child"):
            with self.assertRaises(ValueError):
                toolbox.setup("test", destination)
        self.assertFalse((self.directory / "child").exists())

    def test_answer_reference_is_retained_without_touching_legacy_save(self):
        toolbox.setup("test", self.directory)
        self.assertEqual(toolbox.solution("test", self.directory), self.lab["solution"])
        (self.directory / "answer").write_text("correct")
        ok, message = toolbox.check(self.directory)
        self.assertTrue(ok)
        self.assertIn("解答参照あり", message)
        self.assertTrue(json.loads((self.directory / ".dojo/state.json").read_text())["answer_viewed"])

    def test_foreign_and_linked_state_is_rejected(self):
        toolbox.setup("test", self.directory)
        state = self.directory / ".dojo/state.json"
        state.write_text('{"format":"unrelated","lab":"test"}')
        with self.assertRaises(ValueError):
            toolbox.check(self.directory)
        state.unlink()
        outside = self.root / "outside"
        outside.write_text('{}')
        state.symlink_to(outside)
        with self.assertRaises(ValueError):
            toolbox.check(self.directory)

    def test_cli_check_reports_failure_and_doctor_returns_nonzero_if_missing(self):
        toolbox.setup("test", self.directory)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(toolbox.main(["check", "--directory", str(self.directory)]), 1)
            with patch.object(toolbox.shutil, "which", return_value=None):
                self.assertEqual(toolbox.main(["doctor", "test"]), 2)

    def test_catalog_search_supports_purpose_and_multiple_terms(self):
        catalog = [{"id": "transfer", "title": "バックアップと転送", "commands": ["rsync"]},
                   {"id": "search", "title": "検索", "commands": ["rg"]}]
        with patch.object(toolbox, "topics", return_value=catalog):
            self.assertEqual(toolbox.search("バックアップ rsync"), [catalog[0]])
            self.assertEqual(toolbox.search("RSYNC"), [catalog[0]])
            self.assertEqual(toolbox.search("no-match"), [])

    def test_start_resumes_existing_exercise_and_uses_local_shell_history(self):
        toolbox.setup("test", self.directory)
        (self.directory / "answer").write_text("in progress")
        with patch.object(toolbox.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            toolbox.start("test", self.directory)
        self.assertEqual((self.directory / "answer").read_text(), "in progress")
        self.assertEqual(run.call_args.kwargs["cwd"], self.directory)
        rc = (self.directory / ".dojo/shell.bash").read_text()
        self.assertIn(str(self.directory / ".dojo/history"), rc)
        self.assertIn("check()", rc)

    def test_failed_setup_is_not_resumed_as_a_ready_exercise(self):
        def broken_setup(path):
            (path / "partial").write_text("incomplete")
            raise ValueError("missing runtime capability")
        self.lab["setup"] = broken_setup
        with self.assertRaisesRegex(ValueError, "runtime capability"):
            toolbox.setup("test", self.directory)
        self.assertFalse(toolbox.check(self.directory)[0])
        with patch.object(toolbox.subprocess, "run") as shell:
            with self.assertRaisesRegex(ValueError, "準備"):
                toolbox.start("test", self.directory)
        shell.assert_not_called()

    def test_resource_cleanup_invalidates_completion_but_keeps_work_files(self):
        removed = []
        self.lab["cleanup"] = lambda path: removed.append(path)
        toolbox.setup("test", self.directory)
        (self.directory / "answer").write_text("correct")
        self.assertTrue(toolbox.check(self.directory)[0])
        toolbox.cleanup(self.directory)
        self.assertEqual(removed, [self.directory])
        self.assertFalse(json.loads((self.directory / ".dojo/state.json").read_text())["passed"])
        self.assertEqual((self.directory / "answer").read_text(), "correct")


class CourseIntegrationTests(unittest.TestCase):
    def test_real_catalog_has_valid_mission_lab_and_guide_references(self):
        self.assertGreaterEqual(toolbox.validate_catalog(), 25)

    def test_main_menu_routes_to_daily_use_course(self):
        from engine import main
        with patch.object(main, "ask", side_effect=["9", "q"]), \
             patch.object(main, "header", return_value=""), \
             patch.object(main, "practice_resume", return_value=None), \
             patch.object(main.guided, "selected_mode", return_value="practice"), \
             patch.object(main.ui, "clear"), patch.object(toolbox, "menu") as menu, \
             contextlib.redirect_stdout(io.StringIO()):
            main.main_menu()
        menu.assert_called_once()


if __name__ == "__main__":
    unittest.main()
