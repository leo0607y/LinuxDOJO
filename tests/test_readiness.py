"""総合復習の状態判定・自力達成の保存を一時領域で検証する。"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, readiness, runner, save


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-readiness-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "workspace"
        self.patch_save = patch.object(save, "SAVE", self.base / "save.json")
        self.patch_save.start()
        self.addCleanup(self.patch_save.stop)

    def scenario(self, scenario_id):
        return next(s for s in readiness.scenarios() if s["id"] == scenario_id)

    def prepare(self, scenario):
        return readiness.prepare(scenario, self.root)

    def solve(self, scenario, terminal, omit=()):
        for command in scenario["solution"]:
            if command in omit:
                continue
            result = terminal.execute(command)
            self.assertEqual(result.code, 0, f"{scenario['id']}: {command}: {result.output}")

    def test_all_eight_scenarios_begin_unsolved_and_accept_the_actual_solution(self):
        scenarios = readiness.scenarios()
        self.assertEqual(len(scenarios), 8)
        self.assertEqual(len({s["id"] for s in scenarios}), 8)
        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                terminal = self.prepare(scenario)
                ok, message = readiness.check(scenario, terminal)
                self.assertFalse(ok)
                self.assertTrue(message)
                self.solve(scenario, terminal)
                ok, message = readiness.check(scenario, terminal)
                self.assertTrue(ok, message)

    def test_incorrect_final_file_contents_are_rejected_even_after_solution_commands(self):
        for scenario in readiness.scenarios():
            with self.subTest(scenario=scenario["id"]):
                terminal = self.prepare(scenario)
                self.solve(scenario, terminal)
                target = next(iter(scenario["expected_files"]))
                self.assertEqual(terminal.execute(f"echo incorrect > {target}").code, 0)
                self.assertFalse(readiness.check(scenario, terminal)[0])

    def test_changing_contents_does_not_substitute_for_correct_permissions(self):
        scenario = self.scenario("ready-03")
        terminal = self.prepare(scenario)
        self.solve(scenario, terminal)
        self.assertTrue(readiness.check(scenario, terminal)[0])
        self.assertEqual(terminal.execute("chmod 644 secret.conf").code, 0)
        self.assertFalse(readiness.check(scenario, terminal)[0])
        self.assertEqual(terminal.execute("chmod 600 secret.conf").code, 0)
        self.assertTrue(readiness.check(scenario, terminal)[0])

    def test_backing_up_after_the_change_is_not_a_valid_original_backup(self):
        scenario = self.scenario("ready-04")
        terminal = self.prepare(scenario)
        self.assertEqual(terminal.execute("echo mode=training > app.conf").code, 0)
        self.assertEqual(terminal.execute("cp app.conf app.conf.bak").code, 0)
        ok, message = readiness.check(scenario, terminal)
        self.assertFalse(ok)
        self.assertTrue(message)

    def test_package_installed_without_actually_checking_the_command_is_incomplete(self):
        scenario = self.scenario("ready-05")
        terminal = self.prepare(scenario)
        self.solve(scenario, terminal, omit=("tree",))
        self.assertIn("tree", terminal.progress["packages"])
        self.assertFalse(readiness.check(scenario, terminal)[0])
        self.assertEqual(terminal.execute("tree").code, 0)
        self.assertTrue(readiness.check(scenario, terminal)[0])

    def test_ssh_task_requires_returning_to_local_terminal(self):
        scenario = self.scenario("ready-06")
        terminal = self.prepare(scenario)
        self.solve(scenario, terminal)
        self.assertTrue(readiness.check(scenario, terminal)[0])
        self.assertEqual(terminal.execute("ssh learner@training-server").code, 0)
        self.assertTrue(terminal.progress["remote"])
        self.assertFalse(readiness.check(scenario, terminal)[0])
        self.assertEqual(terminal.execute("exit").code, 0)
        self.assertTrue(readiness.check(scenario, terminal)[0])

    def test_failed_required_command_does_not_count_as_a_successful_remote_check(self):
        scenario = self.scenario("ready-06")
        terminal = self.prepare(scenario)
        self.solve(scenario, terminal, omit=("cat server-note.txt",))
        failed = terminal.execute("cat server-note.txt")
        self.assertNotEqual(failed.code, 0)
        self.assertFalse(readiness.check(scenario, terminal)[0])

    def test_confirming_hostname_on_localhost_does_not_count_as_remote_verification(self):
        scenario = self.scenario("ready-06")
        terminal = self.prepare(scenario)
        self.solve(scenario, terminal, omit=("hostname",))
        self.assertEqual(terminal.execute("hostname").output, "dojo-local")
        self.assertFalse(readiness.check(scenario, terminal)[0])

    def test_prepare_resets_only_its_own_training_scenario(self):
        scenario = self.scenario("ready-01")
        terminal = self.prepare(scenario)
        other = self.root / "other-scenario" / "keep.txt"
        other.parent.mkdir(parents=True)
        other.write_text("unrelated training work\n")
        self.solve(scenario, terminal)
        self.assertTrue(readiness.check(scenario, terminal)[0])
        reset = self.prepare(scenario)
        self.assertFalse(readiness.check(scenario, reset)[0])
        self.assertEqual(reset.execute("cat draft.txt").output, "サーバーの確認をお願いします。")
        self.assertNotEqual(reset.execute("cat archive.txt").code, 0)
        self.assertEqual(other.read_text(), "unrelated training work\n")

    def test_solutions_never_run_host_commands_or_network_connections(self):
        with patch("subprocess.run", side_effect=AssertionError("host process")), \
             patch("subprocess.Popen", side_effect=AssertionError("host process")), \
             patch("os.system", side_effect=AssertionError("host shell")), \
             patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("socket.socket.connect", side_effect=AssertionError("network")):
            for scenario in readiness.scenarios():
                with self.subTest(scenario=scenario["id"]):
                    terminal = self.prepare(scenario)
                    self.solve(scenario, terminal)
                    self.assertTrue(readiness.check(scenario, terminal)[0])

    def test_answer_solution_check_and_menu_record_an_assisted_result(self):
        scenario = self.scenario("ready-01")
        output = io.StringIO()
        with patch.object(runner, "WORKSPACE", self.root), \
             patch.object(readiness.ui, "clear"), \
             patch("builtins.input", side_effect=["answer", *scenario["solution"], "check", "menu"]), \
             contextlib.redirect_stdout(output):
            readiness.play(scenario)
        state = save.load()["learning"]["readiness"]
        self.assertTrue(state["completed"][scenario["id"]]["assisted"])
        self.assertIn("総合復習クリア", output.getvalue())
        self.assertEqual(state["active"], scenario["id"])
        self.assertIn(scenario["id"], state["sessions"])

    def test_ssh_confirmation_and_work_resume_from_saved_session(self):
        scenario = self.scenario("ready-06")
        with patch.object(runner, "WORKSPACE", self.root), \
             patch.object(readiness.ui, "clear"), \
             patch("builtins.input", side_effect=[*scenario["solution"][:2], "menu"]), \
             contextlib.redirect_stdout(io.StringIO()):
            readiness.play(scenario)
        state = save.load()["learning"]["readiness"]["sessions"][scenario["id"]]["terminal"]
        self.assertTrue(state["ssh_pending"])
        with patch.object(runner, "WORKSPACE", self.root), \
             patch.object(readiness.ui, "clear"), \
             patch("builtins.input", side_effect=[*scenario["solution"][2:], "check", "menu"]), \
             contextlib.redirect_stdout(io.StringIO()):
            readiness.play(scenario)
        state = save.load()["learning"]["readiness"]
        self.assertFalse(state["completed"][scenario["id"]]["assisted"])
        self.assertFalse(state["sessions"][scenario["id"]]["terminal"]["remote"])

    def test_reset_restores_task_and_discards_old_confirmation_events(self):
        scenario = self.scenario("ready-05")
        with patch.object(runner, "WORKSPACE", self.root), \
             patch.object(readiness.ui, "clear"), \
             patch("builtins.input", side_effect=[*scenario["solution"], "reset", "check", "menu"]), \
             contextlib.redirect_stdout(io.StringIO()):
            readiness.play(scenario)
        progress = save.load()["learning"]["readiness"]
        self.assertNotIn(scenario["id"], progress.get("completed", {}))
        state = progress["sessions"][scenario["id"]]["terminal"]
        self.assertEqual(state["packages"], [])
        self.assertEqual(state.get("command_events", []), [])

    def test_course_list_can_return_to_menu_without_changing_progress(self):
        initial = save.empty()
        save.store(initial)
        with patch.object(readiness.ui, "clear"), \
             patch("builtins.input", side_effect=["b"]), \
             contextlib.redirect_stdout(io.StringIO()):
            readiness.run()
        self.assertEqual(save.load(), initial)

    def test_recording_assistance_never_overwrites_a_prior_unassisted_success(self):
        scenario = self.scenario("ready-01")
        readiness.record_result(scenario, assisted=True)
        records = save.load()["learning"]["readiness"]["completed"]
        self.assertTrue(records[scenario["id"]]["assisted"])
        readiness.record_result(scenario, assisted=False)
        self.assertFalse(save.load()["learning"]["readiness"]["completed"][scenario["id"]]["assisted"])
        readiness.record_result(scenario, assisted=True)
        self.assertFalse(save.load()["learning"]["readiness"]["completed"][scenario["id"]]["assisted"])

    def test_existing_practice_and_beginner_progress_survive_readiness_results(self):
        data = save.empty()
        data["cleared"]["4-7"] = {"score": 90, "hints": 1}
        data["learning"]["mode"] = "basic"
        data["learning"]["intro"].update(cursor="intro-08", completed=["intro-01"])
        data["learning"]["basic"].update(cursor="basic-37", completed=["basic-01"], ssh_known=True)
        data["custom"] = "keep legacy extension"
        save.store(data)
        readiness.record_result(self.scenario("ready-02"), assisted=False)
        after = save.load()
        self.assertEqual(after["cleared"], data["cleared"])
        self.assertEqual(after["learning"]["intro"], data["learning"]["intro"])
        self.assertEqual(after["learning"]["basic"], data["learning"]["basic"])
        self.assertEqual(after["learning"]["mode"], "basic")
        self.assertEqual(after["custom"], "keep legacy extension")


if __name__ == "__main__":
    unittest.main()
