"""日付境界・復習の報酬・旧セーブ互換性を確認する。"""
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import save


class ActivityTests(unittest.TestCase):
    def test_rewards_are_deduplicated_per_day_and_allow_review(self):
        data = save.empty()
        today = date(2026, 11, 21)
        self.assertEqual(save.record_activity(data, "intro:1", today)["earned"], 10)
        self.assertEqual(save.record_activity(data, "intro:1", today)["earned"], 0)
        reward = save.record_activity(data, "intro:1", today + timedelta(days=1))
        self.assertEqual(reward["xp"], 20)
        self.assertEqual(reward["streak"], 2)

    def test_streak_survives_until_end_of_next_day_and_then_resets(self):
        data = {}
        today = date(2026, 11, 21)
        save.record_activity(data, "basic:1", today)
        self.assertEqual(save.activity_summary(data, today + timedelta(days=1))["streak"], 1)
        self.assertEqual(save.activity_summary(data, today + timedelta(days=2))["streak"], 0)
        self.assertEqual(save.activity_summary(data, today + timedelta(days=1))["today"], 0)

    def test_old_save_and_daily_goal(self):
        data = save.empty()
        self.assertEqual(save.activity_summary(data)["xp"], 0)
        for lesson in ("intro:1", "intro:2", "basic:1"):
            summary = save.record_activity(data, lesson)
        self.assertEqual(summary["today"], summary["goal"])
        self.assertIn("今日の目標達成", save.activity_line(data))

    def test_partial_activity_from_old_save(self):
        data = {"activity": {"days": {}}}
        self.assertEqual(save.record_activity(data, "intro:1")["xp"], 10)

    def test_record_clear_rewards_practice_once_per_day(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        mission = SimpleNamespace(id="1-1", points=100, stage=1)
        with tempfile.TemporaryDirectory(prefix="lq-activity-test-") as tmp:
            with patch.object(save, "SAVE", Path(tmp) / "save.json"):
                self.assertEqual(save.record_clear(mission, 0, False, 5)["activity"]["earned"], 10)
                self.assertEqual(save.record_clear(mission, 0, False, 5)["activity"]["earned"], 0)
                self.assertEqual(save.load()["activity"]["xp"], 10)


if __name__ == "__main__":
    unittest.main()
