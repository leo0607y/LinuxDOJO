"""同じ端末で解いた後のresetが、自力で解き直せる初期状態へ戻すこと。"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided


class GuidedResetTests(unittest.TestCase):
    def test_every_goal_lesson_requires_work_after_a_fresh_reset(self):
        with tempfile.TemporaryDirectory(prefix="dojo-reset-goals-") as tmp:
            checked = 0
            for mode in guided.GUIDED_MODES:
                for step in guided.lessons(mode):
                    if not step.get("goal"):
                        continue
                    with self.subTest(mode=mode, lesson=step["id"]):
                        terminal = guided.Terminal(Path(tmp) / step["id"], {})
                        guided.prepare_step(terminal, step)
                        answer = terminal.execute(step["command"])
                        self.assertTrue(guided.accepted(step["command"], answer, step, terminal),
                                        "監査する前に、代表解で実際に達成できること")
                        # 同じTerminalを再利用し、提出済みファイルやパッケージも残っている状態から戻す。
                        guided.prepare_step(terminal, step, fresh=True)
                        unrelated = terminal.execute("echo unrelated")
                        self.assertFalse(guided.accepted("echo unrelated", unrelated, step, terminal),
                                         "前回の成果が残り、解き直さずに達成できてしまいます")
                        checked += 1
            self.assertGreater(checked, 200)


if __name__ == "__main__":
    unittest.main()
