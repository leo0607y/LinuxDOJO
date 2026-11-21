"""初心者の模擬ターミナル・教材・モード別再開の回帰テスト。すべて一時領域で実行。"""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, runner, save


class GuidedTerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-guided-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.progress = {}
        self.term = guided.Terminal(self.base / "intro", self.progress)

    def ok(self, command):
        result = self.term.execute(command)
        self.assertEqual(result.code, 0, f"{command}: {result.output}")
        return result.output

    def test_privileged_practice_never_executes_a_host_command(self):
        with patch("subprocess.run", side_effect=AssertionError("host subprocess")), \
             patch("subprocess.Popen", side_effect=AssertionError("host process")), \
             patch("os.system", side_effect=AssertionError("host shell")), \
             patch("os.execve", side_effect=AssertionError("host exec")):
            self.assertEqual(self.ok("whoami"), "learner")
            self.assertEqual(self.ok("sudo whoami"), "root")
            self.assertEqual(self.term.execute("apt update").code, 100)
            self.ok("sudo apt update")
            self.ok("sudo apt install tree")
            self.assertIn("welcome.txt", self.ok("tree"))
            self.ok("sudo apt remove tree")
            self.assertEqual(self.term.execute("tree").code, 127)

    def test_package_list_update_does_not_install_software(self):
        self.assertEqual(self.term.execute("tree").code, 127)
        self.assertIn("tree", self.ok("apt search tree"))
        self.assertIn("Package: tree", self.ok("apt show tree"))
        self.assertEqual(self.term.execute("sudo apt install tree").code, 100)
        self.ok("sudo apt update")
        self.assertEqual(self.progress["packages"], [])
        self.ok("sudo apt install tree")
        self.ok("sudo apt install tree")
        self.assertEqual(self.progress["packages"], ["tree"])
        self.assertEqual(self.term.execute("apt remove tree").code, 100)
        self.assertIn("tree", self.progress["packages"])

    def test_shell_expansion_and_dangerous_commands_do_not_run(self):
        marker = self.base / "must-not-exist"
        for command in ("sudo rm -rf /", "rm -rf /", "bash", "sh -c whoami", "curl https://example.com", "python3 -c print(1)", "echo hello && whoami"):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)
        self.ok(f'echo "$(touch {marker})"')
        self.ok(f'echo "`touch {marker}`"')
        self.assertFalse(marker.exists())

    def test_paths_cannot_escape_the_practice_root(self):
        outside = self.base / "private.txt"
        outside.write_text("private test fixture\n")
        for command in ("cat ../private.txt", "cat /etc/passwd", "cat /home/learner/../private.txt", "echo overwritten > ../private.txt", "touch /tmp/outside", "cd .."):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)
        self.assertEqual(outside.read_text(), "private test fixture\n")
        self.assertEqual(self.term.display_cwd, "/home/learner")

    def test_existing_symlinks_cannot_read_or_write_outside(self):
        outside = self.base / "private.txt"
        outside.write_text("private test fixture\n")
        (self.term.root / "link").symlink_to(outside)
        (self.term.root / "folder-link").symlink_to(self.base, target_is_directory=True)
        for command in ("cat link", "echo overwritten > link", "cp welcome.txt link", "chmod 600 link", "touch folder-link/new.txt", "cd folder-link"):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)
        self.assertEqual(outside.read_text(), "private test fixture\n")
        self.assertFalse((self.base / "new.txt").exists())

    def test_initial_files_do_not_follow_a_broken_symlink(self):
        root = self.base / "broken-link-course"
        root.mkdir()
        outside = self.base / "must-not-be-created"
        (root / "welcome.txt").symlink_to(outside)
        try:
            guided.Terminal(root, {})
        except guided.TrainingError:
            pass
        self.assertFalse(outside.exists())

    def test_practice_root_cannot_be_a_symlink_to_another_directory(self):
        outside = self.base / "outside"
        outside.mkdir()
        linked_root = self.base / "linked-root"
        linked_root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(guided.TrainingError):
            guided.Terminal(linked_root, {})
        self.assertEqual(list(outside.iterdir()), [])

    def test_listing_a_missing_file_reports_failure(self):
        result = self.term.execute("ls missing.txt")
        self.assertNotEqual(result.code, 0)
        self.assertIn("見つかりません", result.output)

    def test_files_navigation_quotes_and_redirection(self):
        self.ok("mkdir practice")
        self.ok("cd practice")
        self.assertEqual(self.ok("pwd"), "/home/learner/practice")
        self.ok("touch empty.txt")
        self.assertEqual(self.ok("cat empty.txt"), "")
        self.ok('echo "hello world" > note.txt')
        self.ok("echo second >> note.txt")
        self.assertEqual((self.term.root / "practice/note.txt").read_text(), "hello world\nsecond\n")
        self.ok("cp note.txt copy.txt")
        self.ok("mv copy.txt final.txt")
        self.assertFalse((self.term.root / "practice/copy.txt").exists())
        self.assertEqual(self.ok("cat final.txt"), "hello world\nsecond")
        self.ok("rm final.txt")
        self.assertFalse((self.term.root / "practice/final.txt").exists())
        self.ok("cd ..")
        self.assertEqual(self.term.display_cwd, "/home/learner")
        self.assertIn("practice/", self.ok("ls"))
        self.assertNotIn(".memo", self.ok("ls"))
        self.assertIn(".memo", self.ok("ls -a"))

    def test_copy_and_move_into_a_directory_from_nested_cwd(self):
        self.ok("mkdir -p work/archive")
        self.ok("cd work")
        self.ok("echo saved > note.txt")
        self.ok("cp note.txt archive")
        self.assertEqual((self.term.root / "work/archive/note.txt").read_text(), "saved\n")
        self.ok("echo second > other.txt")
        self.ok("mv other.txt archive")
        self.assertFalse((self.term.root / "work/other.txt").exists())
        self.assertEqual((self.term.root / "work/archive/other.txt").read_text(), "second\n")

    def test_search_line_count_and_permission_changes(self):
        self.ok("echo INFO > app.log")
        self.ok("echo ERROR >> app.log")
        self.assertEqual(self.ok("grep ERROR app.log"), "ERROR")
        self.assertEqual(self.ok("grep -i error app.log"), "ERROR")
        self.assertEqual(self.term.execute("grep absent app.log").code, 1)
        self.assertEqual(self.ok("wc -l app.log"), "2 app.log")
        self.ok("touch script.sh")
        self.ok("chmod 644 script.sh")
        self.assertFalse((self.term.root / "script.sh").stat().st_mode & stat.S_IXUSR)
        self.ok("chmod u+x script.sh")
        self.assertTrue((self.term.root / "script.sh").stat().st_mode & stat.S_IXUSR)
        self.assertIn("-rwx", self.ok("ls -l script.sh"))

    def test_mistyped_input_is_explained_without_a_traceback(self):
        self.assertIn("$", self.term.execute("$ pwd").output)
        for command in ("", "echo 'unfinished", "cat missing.txt", "cd welcome.txt", "ls --bad", "sudo"):
            result = self.term.execute(command)
            self.assertNotEqual(result.code, 0, command)
            self.assertTrue(result.output, command)

    def test_files_and_packages_are_independent_between_modes(self):
        basic_progress = {}
        basic = guided.Terminal(self.base / "basic", basic_progress)
        self.ok("echo intro-only > mine.txt")
        self.ok("sudo apt update")
        self.ok("sudo apt install tree")
        self.assertFalse((basic.root / "mine.txt").exists())
        self.assertEqual(basic.execute("tree").code, 127)
        self.assertEqual(basic_progress["packages"], [])
        self.assertFalse(basic_progress["apt_updated"])


class GuidedProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-guided-save-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.path = self.base / "save_data.json"
        self.save_patch = patch.object(save, "SAVE", self.path)
        self.save_patch.start()
        self.addCleanup(self.save_patch.stop)

    def test_new_player_starts_in_intro_without_overwriting_real_save(self):
        self.assertEqual(save.load()["learning"]["mode"], "intro")
        self.assertFalse(self.path.exists())
        self.assertEqual(save.load()["cleared"], {})

    def test_legacy_experience_and_unknown_fields_are_preserved(self):
        legacy = save.empty()
        legacy.pop("learning", None)
        legacy["cleared"]["1-1"] = {"score": 90}
        legacy["player"]["sessions"] = 3
        legacy["custom"] = "retained"
        self.path.write_text(json.dumps(legacy))
        loaded = save.load()
        self.assertEqual(loaded["learning"]["mode"], "practice")
        self.assertEqual(loaded["cleared"], legacy["cleared"])
        self.assertEqual(loaded["player"], legacy["player"])
        self.assertEqual(loaded["custom"], "retained")
        save.store(loaded)
        self.assertEqual(save.load()["learning"]["mode"], "practice")

    def test_mode_progress_cursor_and_package_state_survive_restart(self):
        d = save.empty()
        d["cleared"]["5-1"] = {"score": 100}
        d["learning"]["mode"] = "basic"
        save.store(d)
        progress = guided.progress_for("intro")
        progress.update(cursor="intro-fixture", completed=["intro-first"], cwd="practice",
                        packages=["tree"], apt_updated=True)
        guided.remember("intro", progress)
        reloaded = save.load()
        self.assertEqual(reloaded["learning"]["intro"]["cursor"], "intro-fixture")
        self.assertEqual(reloaded["learning"]["intro"]["cwd"], "practice")
        self.assertEqual(reloaded["learning"]["intro"]["packages"], ["tree"])
        self.assertEqual(reloaded["learning"]["mode"], "basic")
        self.assertEqual(reloaded["learning"]["basic"].get("completed", []), [])
        self.assertEqual(reloaded["cleared"]["5-1"], {"score": 100})

    def test_guided_play_saves_the_next_lesson_when_returning_to_menu(self):
        from curriculum.beginner_lessons import LESSONS
        course = LESSONS["intro"]
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=[course[0]["command"], "menu"]), \
             patch.object(guided.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            guided.play("intro")
        progress = guided.progress_for("intro")
        self.assertIn(course[0]["id"], progress["completed"])
        self.assertEqual(progress["cursor"], course[1]["id"])
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=["menu"]), \
             patch.object(guided.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            guided.play("intro")
        self.assertEqual(guided.progress_for("intro")["cursor"], course[1]["id"])


class GuidedCurriculumTests(unittest.TestCase):
    def test_every_lesson_has_clear_beginner_instructions_and_a_unique_id(self):
        from curriculum.beginner_lessons import LESSONS
        seen = set()
        self.assertEqual(set(LESSONS), {"intro", "basic", "advanced", "expert"})
        for mode, course in LESSONS.items():
            self.assertGreaterEqual(len(course), 15)
            for step in course:
                with self.subTest(mode=mode, lesson=step["id"]):
                    self.assertNotIn(step["id"], seen)
                    seen.add(step["id"])
                    for key in ("title", "explanation", "task", "command", "success"):
                        self.assertTrue(step[key].strip(), key)
                    self.assertNotIn("\n", step["command"])

    def test_all_lesson_solutions_work_in_order(self):
        from curriculum.beginner_lessons import LESSONS
        with tempfile.TemporaryDirectory(prefix="linuxdojo-course-test-") as tmp:
            for mode, course in LESSONS.items():
                terminal = guided.Terminal(Path(tmp) / mode, {})
                for step in course:
                    with self.subTest(mode=mode, lesson=step["id"], command=step["command"]):
                        guided.prepare_step(terminal, step)
                        result = terminal.execute(step["command"])
                        expected = step.get("expected_code", 100 if step["command"] == "apt update" else 0)
                        self.assertEqual(result.code, expected, result.output)
                        self.assertTrue(guided.matches(step["command"], step))

    def test_each_lesson_can_be_selected_for_independent_review(self):
        from curriculum.beginner_lessons import LESSONS
        with tempfile.TemporaryDirectory(prefix="linuxdojo-review-test-") as tmp:
            for mode, course in LESSONS.items():
                for step in course:
                    with self.subTest(mode=mode, lesson=step["id"], command=step["command"]):
                        terminal = guided.Terminal(Path(tmp) / mode / step["id"], {})
                        guided.prepare_step(terminal, step)
                        result = terminal.execute(step["command"])
                        expected = step.get("expected_code", 100 if step["command"] == "apt update" else 0)
                        self.assertEqual(result.code, expected, result.output)

    def test_reset_recovers_fixture_files_replaced_with_directories(self):
        with tempfile.TemporaryDirectory(prefix="linuxdojo-reset-types-test-") as tmp:
            terminal = guided.Terminal(Path(tmp), {})
            terminal.execute("rm welcome.txt")
            terminal.execute("mkdir welcome.txt")
            terminal.execute("mkdir -p welcome.txt/nested")
            terminal.execute("rm .memo")
            terminal.execute("mkdir .memo")
            terminal.execute("mkdir script.sh")
            guided.prepare_step(terminal, {"cwd": ".", "files": {"script.sh": "echo restored\n"}})
            self.assertEqual((terminal.root / "welcome.txt").read_text(), "LinuxDOJOへようこそ！\n")
            self.assertEqual((terminal.root / ".memo").read_text(), "見つけました！\n")
            self.assertEqual((terminal.root / "script.sh").read_text(), "echo restored\n")
            self.assertEqual(stat.S_IMODE((terminal.root / "script.sh").stat().st_mode), 0o644)

    def test_reset_recovers_cwd_and_required_parent_directories_replaced_with_files(self):
        with tempfile.TemporaryDirectory(prefix="linuxdojo-reset-directory-test-") as tmp:
            terminal = guided.Terminal(Path(tmp), {})
            terminal.execute("touch notes")
            guided.prepare_step(terminal, {"cwd": "notes"})
            self.assertTrue((terminal.root / "notes").is_dir())
            self.assertEqual(terminal.display_cwd, "/home/learner/notes")
            terminal.execute("touch archive")
            terminal.execute("touch assets")
            guided.prepare_step(terminal, {"cwd": "notes", "dirs": ["archive/subfolder"],
                                           "files": {"assets/readme.txt": "restored\n"}})
            self.assertTrue((terminal.root / "notes/archive/subfolder").is_dir())
            self.assertEqual((terminal.root / "notes/assets/readme.txt").read_text(), "restored\n")

    def test_every_lesson_can_be_reviewed_twice_with_fresh_task_state(self):
        from curriculum.beginner_lessons import LESSONS
        with tempfile.TemporaryDirectory(prefix="linuxdojo-review-twice-test-") as tmp:
            for mode, course in LESSONS.items():
                for step in course:
                    terminal = guided.Terminal(Path(tmp) / mode / step["id"], {})
                    for repetition in range(2):
                        with self.subTest(mode=mode, lesson=step["id"], repetition=repetition):
                            guided.prepare_step(terminal, step)
                            result = terminal.execute(step["command"])
                            expected = step.get("expected_code", 100 if step["command"] == "apt update" else 0)
                            self.assertEqual(result.code, expected, result.output)

    def test_reset_restores_file_contents_and_expected_permission_before_review(self):
        with tempfile.TemporaryDirectory(prefix="linuxdojo-reset-test-") as tmp:
            terminal = guided.Terminal(Path(tmp), {})
            step = {"cwd": ".", "files": {"script.sh": "echo original\n"},
                    "modes": {"script.sh": 0o744}, "remove": ["copy.txt"]}
            guided.prepare_step(terminal, step)
            terminal.execute("echo changed > script.sh")
            terminal.execute("chmod 600 script.sh")
            terminal.execute("cp script.sh copy.txt")
            guided.prepare_step(terminal, step)
            self.assertEqual((terminal.root / "script.sh").read_text(), "echo original\n")
            self.assertEqual(stat.S_IMODE((terminal.root / "script.sh").stat().st_mode), 0o744)
            self.assertFalse((terminal.root / "copy.txt").exists())


class GuidedMenuTests(unittest.TestCase):
    setUp = GuidedProgressTests.setUp

    def test_switching_modes_keeps_both_cursors_and_practice_results(self):
        from engine import main
        d = save.empty()
        d["learning"]["intro"]["cursor"] = "intro-09"
        d["learning"]["basic"]["cursor"] = "basic-12"
        d["learning"]["practice"]["mission"] = "7-3"
        d["cleared"]["1-1"] = {"score": 100}
        save.store(d)
        with patch("builtins.input", return_value="2"), patch.object(main.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            main.mode_select()
        after = save.load()
        self.assertEqual(after["learning"]["mode"], "basic")
        for key in ("intro", "basic", "practice"):
            self.assertEqual(after["learning"][key], d["learning"][key])
        self.assertEqual(after["cleared"], d["cleared"])

    def test_continue_and_lesson_selection_route_to_the_selected_mode(self):
        from engine import main
        d = save.empty()
        d["learning"]["mode"] = "basic"
        save.store(d)
        with patch("builtins.input", side_effect=["1", "2", "q"]), \
             patch.object(main.ui, "clear"), \
             patch.object(guided, "play") as play, \
             patch.object(guided, "lesson_select") as select, \
             patch.object(main, "play") as practice, contextlib.redirect_stdout(io.StringIO()):
            main.main_menu()
        play.assert_called_once_with("basic")
        select.assert_called_once_with("basic")
        practice.assert_not_called()

    def test_completed_course_requires_every_lesson_not_just_the_last_cursor(self):
        from curriculum.beginner_lessons import LESSONS
        course = LESSONS["intro"]
        all_ids = [step["id"] for step in course]
        self.assertFalse(guided.completed_course("intro", {"cursor": all_ids[-1], "completed": all_ids[:-1]}))
        self.assertTrue(guided.completed_course("intro", {"completed": all_ids + [all_ids[0], "unknown-id"]}))
        self.assertFalse(guided.completed_course("intro", {"completed": ["unknown-id"] * len(all_ids)}))

    def test_completed_mode_continue_opens_mode_selection_and_review_remains_available(self):
        from engine import main
        from curriculum.beginner_lessons import LESSONS
        d = save.empty()
        d["learning"]["intro"]["completed"] = [step["id"] for step in LESSONS["intro"]]
        save.store(d)
        capture = io.StringIO()
        with patch("builtins.input", side_effect=["1", "2", "q"]), \
             patch.object(main.ui, "clear"), \
             patch.object(main, "mode_select") as choose, \
             patch.object(guided, "play") as play, \
             patch.object(guided, "lesson_select") as review, contextlib.redirect_stdout(capture):
            main.main_menu()
        choose.assert_called_once_with()
        play.assert_not_called()
        review.assert_called_once_with("intro")
        self.assertIn("次のモードを選ぶ", capture.getvalue())
        self.assertEqual(len(save.load()["learning"]["intro"]["completed"]), len(LESSONS["intro"]))

    def test_completed_course_can_resume_a_partially_finished_review(self):
        from engine import main
        from curriculum.beginner_lessons import LESSONS
        course = LESSONS["intro"]
        d = save.empty()
        d["learning"]["intro"]["completed"] = [step["id"] for step in course]
        save.store(d)
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=["menu"]), \
             patch.object(main.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            guided.play("intro", start=4)
        paused = guided.progress_for("intro")
        self.assertTrue(paused["reviewing"])
        self.assertEqual(paused["cursor"], course[4]["id"])
        capture = io.StringIO()
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=["1", "menu", "q"]), \
             patch.object(main.ui, "clear"), \
             patch.object(main, "mode_select") as choose, \
             patch.object(guided, "play", wraps=guided.play) as play, contextlib.redirect_stdout(capture):
            main.main_menu()
        play.assert_called_once_with("intro")
        choose.assert_not_called()
        self.assertIn(course[4]["title"], capture.getvalue())
        self.assertEqual(guided.progress_for("intro")["cursor"], course[4]["id"])
        self.assertTrue(guided.progress_for("intro")["reviewing"])

    def test_finishing_the_last_review_lesson_returns_to_course_complete_state(self):
        from curriculum.beginner_lessons import LESSONS
        course = LESSONS["intro"]
        d = save.empty()
        d["learning"]["intro"]["completed"] = [step["id"] for step in course]
        save.store(d)
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=[course[-1]["command"], "menu"]), \
             patch.object(guided.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            guided.play("intro", start=len(course) - 1)
        self.assertFalse(guided.progress_for("intro")["reviewing"])
        self.assertTrue(guided.completed_course("intro"))
        self.assertEqual(len(guided.progress_for("intro")["completed"]), len(course))

    def test_reset_command_recovers_from_a_wrong_file_type_during_a_lesson(self):
        from curriculum.beginner_lessons import LESSONS
        course = LESSONS["intro"]
        with patch.object(runner, "WORKSPACE", self.base / "workspace"), \
             patch("builtins.input", side_effect=["rm welcome.txt", "mkdir welcome.txt", "reset", "cat welcome.txt", "menu"]), \
             patch.object(guided.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
            guided.play("intro", start=4)
        progress = guided.progress_for("intro")
        self.assertIn(course[4]["id"], progress["completed"])
        self.assertEqual(progress["cursor"], course[5]["id"])
        restored = self.base / "workspace/learning_intro/welcome.txt"
        self.assertTrue(restored.is_file())
        self.assertEqual(restored.read_text(), "LinuxDOJOへようこそ！\n")

    def test_practice_continue_prefers_the_last_unfinished_mission(self):
        from engine import main
        d = save.empty()
        d["learning"]["mode"] = "practice"
        d["learning"]["practice"]["mission"] = "7-3"
        save.store(d)
        self.assertEqual(main.practice_resume().id, "7-3")
        d["cleared"]["7-3"] = {"score": 100}
        save.store(d)
        self.assertEqual(main.practice_resume().id, "1-1")
        d["learning"]["practice"]["mission"] = "removed-mission"
        save.store(d)
        self.assertEqual(main.practice_resume().id, "1-1")

    def test_practice_mission_is_bookmarked_before_preparation(self):
        from engine import main
        save.store(save.empty())
        with patch.object(runner, "prepare", side_effect=RuntimeError("fixture error")), \
             patch.object(runner, "kill_session"), \
             patch.object(main, "briefing_splash"), \
             patch.object(main, "pause"), contextlib.redirect_stdout(io.StringIO()):
            main.play(runner.get_mission("7-3"))
        self.assertEqual(save.load()["learning"]["practice"]["mission"], "7-3")

    def test_beginner_settings_never_inspects_host_docker(self):
        from engine import main, docker_backend
        d = save.empty()
        d["learning"]["mode"] = "basic"
        save.store(d)
        capture = io.StringIO()
        with patch("builtins.input", return_value=""), \
             patch.object(main.ui, "clear"), \
             patch.object(docker_backend, "real_available", side_effect=AssertionError("host Docker check")), \
             patch.object(docker_backend, "detect_mode", side_effect=AssertionError("Docker mode detection")), \
             contextlib.redirect_stdout(capture):
            main.settings()
        self.assertIn("初心者モードの設定", capture.getvalue())
        self.assertNotIn("Docker", capture.getvalue())
        self.assertEqual(save.load(), d)

    def test_beginner_reset_without_exact_yes_preserves_all_progress(self):
        from engine import main
        d = save.empty()
        d["learning"]["mode"] = "basic"
        d["learning"]["intro"].update(cursor="intro-09", completed=["intro-01"], packages=["tree"])
        d["learning"]["basic"].update(cursor="basic-12", completed=["basic-01"])
        d["learning"]["practice"]["mission"] = "7-3"
        d["cleared"]["1-1"] = {"score": 100}
        d["titles"] = ["existing-title"]
        d["settings"]["docker_mode"] = "mock"
        save.store(d)
        for confirmation in ("", "no", "YES"):
            with self.subTest(confirmation=confirmation), \
                 patch("builtins.input", side_effect=["r", confirmation]), \
                 patch.object(main.ui, "clear"), contextlib.redirect_stdout(io.StringIO()):
                main.settings()
            self.assertEqual(save.load(), d)

    def test_confirmed_beginner_reset_clears_all_modes_but_keeps_settings(self):
        from engine import main
        d = save.empty()
        d["learning"]["mode"] = "basic"
        d["learning"]["intro"].update(cursor="intro-09", completed=["intro-01"], packages=["tree"], apt_updated=True)
        d["learning"]["basic"].update(cursor="basic-12", completed=["basic-01"])
        d["learning"]["practice"]["mission"] = "7-3"
        d["cleared"]["1-1"] = {"score": 100}
        d["titles"] = ["existing-title"]
        d["stats"]["checks"] = 12
        d["player"]["sessions"] = 3
        d["settings"].update(docker_mode="mock", custom_setting="preserved")
        save.store(d)
        with patch("builtins.input", side_effect=["r", "yes"]), \
             patch.object(main.ui, "clear"), patch.object(main, "pause"), \
             contextlib.redirect_stdout(io.StringIO()):
            main.settings()
        reset = save.load()
        self.assertEqual(reset["settings"], d["settings"])
        self.assertEqual(reset["learning"]["mode"], "intro")
        self.assertEqual(reset["learning"], save.empty()["learning"])
        self.assertEqual(reset["cleared"], {})
        self.assertEqual(reset["titles"], [])
        self.assertEqual(reset["stats"], save.empty()["stats"])
        self.assertEqual(reset["player"], save.empty()["player"])

    def test_beginner_header_has_its_own_progress_and_no_score_penalty(self):
        from engine import main
        from curriculum.beginner_lessons import LESSONS
        d = save.empty()
        first = LESSONS["intro"][0]
        d["learning"]["intro"]["completed"] = [first["id"]]
        d["learning"]["intro"]["cursor"] = LESSONS["intro"][1]["id"]
        save.store(d)
        text = main.header()
        self.assertIn("はじめてモード", text)
        self.assertIn(f'1/{len(LESSONS["intro"])}', text)
        self.assertIn("減点なし", text)
        self.assertNotIn("総スコア", text)


if __name__ == "__main__":
    unittest.main()
