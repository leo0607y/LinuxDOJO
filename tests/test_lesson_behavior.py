"""全課題の「ヒント・判定」の品質を静的に守る回帰テスト（tools/audit_lessons.py の軽量版）。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from engine import guided, guidance, readiness  # noqa: E402
import audit_lessons as audit  # noqa: E402
from curriculum import festival  # noqa: E402


def _lessons():
    for mode in ("intro", "basic", "advanced", "expert"):
        for step in guided.lessons(mode):
            yield mode, step


class HintQualityTest(unittest.TestCase):
    def test_no_lesson_hint_contains_a_full_solution_and_each_has_two_stages(self):
        bad = []
        for mode, step in _lessons():
            hints = guided.guidance_hints(step)
            answers = guided.answers(step)
            if len(hints) < 2:
                bad.append((step["id"], "ヒントが1段階以下"))
            if len(set(hints)) != len(hints):
                bad.append((step["id"], "ヒントの重複"))
            for h in hints:
                if audit.leak(h, answers):
                    bad.append((step["id"], "完全な正解がヒントにある: " + audit.leak(h, answers)))
        self.assertEqual(bad, [])

    def test_no_festival_hint_contains_a_solution_line(self):
        bad = []
        scenarios = [sc for _name, _title, items in festival.packs() for sc in items]
        self.assertGreater(len(scenarios), 200)
        for scenario in scenarios:
            solution = scenario["solution"]
            answers = solution if isinstance(solution, list) else [solution]
            for h in readiness.advice_hints(scenario):
                lk = audit.leak(h, answers)
                if lk:
                    bad.append((scenario["id"], lk))
        self.assertEqual(bad, [])


class LeakMatchingTest(unittest.TestCase):
    def test_single_letter_answer_only_matches_as_a_word(self):
        self.assertFalse(guidance.contains_full_solution("取り消し（undo）の頭文字、1文字を入力します。", ["u"]))
        self.assertTrue(guidance.contains_full_solution("入力例: u", ["u"]))
        self.assertTrue(guidance.contains_full_solution("道具は cd です。", ["cd"]))


class EquivalentSpellingTest(unittest.TestCase):
    def _step(self, command, **extra):
        return {"command": command, **extra}

    def test_ssh_option_order_is_free(self):
        step = self._step("ssh -p 2222 -i .ssh/training_key learner@training-server")
        self.assertTrue(guided.matches("ssh -i .ssh/training_key -p 2222 learner@training-server", step))
        self.assertFalse(guided.matches("ssh -i .ssh/training_key -p 22 learner@training-server", step))

    def test_clustered_and_split_short_flags_match(self):
        step = self._step("tar -tf backup.tar.gz")
        self.assertTrue(guided.matches("tar -t -f backup.tar.gz", step))
        step = self._step("ss -tln")
        self.assertTrue(guided.matches("ss -t -l -n", step))
        self.assertFalse(guided.matches("ss -t -l", step))

    def test_simulator_runs_split_flags_for_plugin_commands(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            terminal = guided.Terminal(Path(work) / "t", {})
            # ss は管理者権限つきで調べる
            joined = terminal.execute("sudo ss -tln")
            split = terminal.execute("sudo ss -t -l -n")
            self.assertEqual(split.code, 0)
            self.assertEqual(joined.output, split.output)
            self.assertIn("LISTEN", split.output)


if __name__ == "__main__":
    unittest.main()
