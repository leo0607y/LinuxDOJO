"""課題まつりの全課題を検証する。すべて一時領域で実行し、ホストのコマンドは動かさない。

- 用意した直後は未達成
- solution と alt_solutions のどれでも達成できる
- traps の手順では達成できない
- 手順はすべて成功する（終了コード 0。expected_codes で例外を書ける）
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum import festival
from engine import readiness


def packs():
    # FESTIVAL_PACK=名前 で1つのパックだけを検証できる（作成中のパックを個別に確かめる用）。
    return festival.packs(os.environ.get("FESTIVAL_PACK") or None)

REQUIRED = ("id", "title", "brief", "solution", "hints", "explanation", "practice")


def festival_scenarios():
    return [s for _, _, items in packs() for s in items]


class FestivalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-festival-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        guard = patch("subprocess.run", side_effect=AssertionError("host subprocess"))
        guard.start()
        self.addCleanup(guard.stop)

    def run_steps(self, scenario, steps, label, require_success=True):
        terminal = readiness.prepare(scenario, self.root / label)
        for command in steps:
            result = terminal.execute(command)
            if require_success:
                allowed = scenario.get("expected_codes", {}).get(command, 0)
                self.assertEqual(result.code, allowed, f"{scenario['id']} [{label}] {command!r}: {result.output}")
        return terminal

    def test_pack_files_are_well_formed(self):
        seen = set()
        for name, title, items in packs():
            with self.subTest(pack=name):
                self.assertTrue(title.strip())
                self.assertGreaterEqual(len(items), 1)
            for scenario in items:
                with self.subTest(scenario=scenario.get("id")):
                    for key in REQUIRED:
                        self.assertIn(key, scenario)
                    self.assertTrue(scenario["id"].startswith(f"fes-{name}-"), scenario["id"])
                    self.assertNotIn(scenario["id"], seen)
                    seen.add(scenario["id"])
                    self.assertGreaterEqual(len(scenario["hints"]), 1)
                    self.assertIn(scenario["level"], (1, 2, 3))

    def test_every_scenario_starts_unsolved(self):
        for scenario in festival_scenarios():
            with self.subTest(scenario=scenario["id"]):
                terminal = readiness.prepare(scenario, self.root / "fresh")
                self.assertFalse(readiness.check(scenario, terminal)[0])

    def test_solution_and_alternatives_are_accepted(self):
        for scenario in festival_scenarios():
            for number, steps in enumerate([scenario["solution"], *scenario["alt_solutions"]]):
                with self.subTest(scenario=scenario["id"], route=number):
                    terminal = self.run_steps(scenario, steps, f"route{number}")
                    ok, message = readiness.check(scenario, terminal)
                    self.assertTrue(ok, f"{scenario['id']} route {number}: {message}")

    def test_traps_are_rejected(self):
        for scenario in festival_scenarios():
            for number, steps in enumerate(scenario["traps"]):
                with self.subTest(scenario=scenario["id"], trap=number):
                    terminal = self.run_steps(scenario, steps, f"trap{number}", require_success=False)
                    self.assertFalse(readiness.check(scenario, terminal)[0], f"{scenario['id']} trap {number} passed")


if __name__ == "__main__":
    unittest.main()
