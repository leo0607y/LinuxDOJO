"""Course completeness, independent assessment and legacy save integration."""
from collections import Counter
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided, readiness, runner, save


class LearningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-integration-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def completed(self):
        data = save.empty()
        for mode in guided.GUIDED_MODES:
            data["learning"][mode]["completed"] = [s["id"] for s in guided.lessons(mode)]
        data["learning"]["readiness"] = {"completed": {
            s["id"]: {"assisted": False} for s in readiness.scenarios()}}
        data["cleared"] = {m.id: {"score": 100} for m in runner.load_curriculum()}
        return data

    def test_mastery_includes_every_lesson_challenge_and_mission_once(self):
        areas = readiness.mastery_areas()
        expected = (
            [s["id"] for mode in guided.GUIDED_MODES for s in guided.lessons(mode)],
            [s["id"] for s in readiness.scenarios()],
            [m.id for m in runner.load_curriculum()],
        )
        for column, items in enumerate(expected, 1):
            with self.subTest(column=column):
                actual = [key for area in areas for key in area[column]]
                self.assertEqual(Counter(actual), Counter(items))
                self.assertTrue(all(n == 1 for n in Counter(actual).values()))

    def test_assisted_completion_requires_independent_retake_for_title(self):
        data = self.completed()
        self.assertEqual(readiness.mastery(data)[1], 1)
        self.assertTrue(any("すべて制覇" in line for line in readiness.mastery_lines(data)))
        key = readiness.scenarios()[0]["id"]
        data["learning"]["readiness"]["completed"][key]["assisted"] = True
        self.assertFalse(any("すべて制覇" in line for line in readiness.mastery_lines(data)))
        self.assertTrue(any("手本なし" in line for line in readiness.mastery_lines(data)))

    def test_legacy_save_adds_expert_without_losing_other_progress(self):
        data = self.completed()
        del data["learning"]["expert"]
        data["learning"]["mode"] = "practice"
        data["learning"]["practice"]["mission"] = "4-3"
        before = copy.deepcopy(data)
        path = self.root / "save.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(save, "SAVE", path):
            loaded = save.load()
        self.assertEqual(loaded["learning"]["expert"]["completed"], [])
        for mode in ("intro", "basic", "advanced", "practice"):
            self.assertEqual(loaded["learning"][mode], before["learning"][mode])
        self.assertEqual(loaded["cleared"], before["cleared"])
        self.assertEqual(loaded["learning"]["mode"], "practice")

    def test_expert_state_survives_json_save_and_resume(self):
        terminal = guided.Terminal(self.root / "terminal", {})
        step = next(s for s in guided.lessons("expert") if s["id"] == "ex-network-18")
        guided.prepare_step(terminal, step)
        result = terminal.execute(step["command"])
        self.assertTrue(guided.accepted(step["command"], result, step, terminal))
        state = json.loads(json.dumps(terminal.progress))
        resumed = guided.Terminal(terminal.root, state)
        self.assertTrue(guided.goal_met(step, resumed))
        self.assertIn(["8080/tcp", "ALLOW", "192.0.2.10"], state["network"]["ufw"]["rules"])

    def test_shared_getent_supports_both_hosts_and_accounts(self):
        terminal = guided.Terminal(self.root / "terminal", {})
        self.assertIn("203.0.113.10", terminal.execute("getent hosts example.com").output)
        self.assertIn("learner:x:1000:", terminal.execute("getent passwd learner").output)
        self.assertEqual(terminal.execute("getent hosts missing.invalid").code, 2)

    def test_which_only_finds_optional_commands_after_package_installation(self):
        terminal = guided.Terminal(self.root / "terminal", {})
        for name in ("git", "dig", "curl", "htop"):
            self.assertEqual(terminal.execute("which " + name).code, 1)
        self.assertEqual(terminal.execute("sudo apt update").code, 0)
        for package, name in (("git", "git"), ("dnsutils", "dig"), ("curl", "curl"), ("htop", "htop")):
            self.assertEqual(terminal.execute("sudo apt install " + package).code, 0)
            self.assertEqual(terminal.execute("which " + name).output, "/usr/bin/" + name)

    def test_network_exercises_do_not_open_connections_or_run_host_commands(self):
        with patch("socket.socket", side_effect=AssertionError("host socket")), \
             patch("subprocess.run", side_effect=AssertionError("host subprocess")):
            for step in guided.lessons("expert"):
                if not step["id"].startswith("ex-network-"):
                    continue
                with self.subTest(lesson=step["id"]):
                    terminal = guided.Terminal(self.root / step["id"], {})
                    guided.prepare_step(terminal, step, fresh=True)
                    result = terminal.execute(step["command"])
                    self.assertTrue(guided.accepted(step["command"], result, step, terminal), result.output)


if __name__ == "__main__":
    unittest.main()
