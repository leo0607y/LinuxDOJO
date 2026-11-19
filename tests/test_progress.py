"""59問の進捗・ランクと旧セーブデータ互換性の回帰テスト。"""
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import runner, save


class ProgressTests(unittest.TestCase):
    def test_curriculum_contains_all_59_missions(self):
        missions = runner.load_curriculum()
        self.assertEqual(len(missions), 59)
        self.assertEqual(len({m.id for m in missions}), 59)
        self.assertEqual(Counter(m.stage for m in missions),
                         {1: 8, 2: 8, 3: 8, 4: 8, 5: 7, 6: 8, 7: 7, 99: 5})
        self.assertEqual({m.id for m in missions if m.stage == 7},
                         {f"7-{n}" for n in range(1, 8)})

    def test_rank_boundaries_require_all_59_for_max(self):
        for cleared, level, next_threshold in (
            (43, "Lv.7", 44), (44, "Lv.8", 52),
            (51, "Lv.8", 52), (52, "Lv.9", 59),
            (58, "Lv.9", 59), (59, "Lv.MAX", None),
        ):
            with self.subTest(cleared=cleared):
                self.assertEqual(save.rank_of(cleared)[1], level)
                following = save.next_rank(cleared)
                self.assertEqual(following[0] if following else None, next_threshold)

    def test_existing_save_survives_new_clear_and_keeps_best_score(self):
        with tempfile.TemporaryDirectory(prefix="lq-progress-test-") as tmp:
            path = Path(tmp) / "save_data.json"
            legacy_clear = {"score": 90, "hints": 1, "answer": False,
                            "seconds": 123, "date": "2025-01-02 03:04"}
            legacy = {
                "version": 1,
                "player": {"created": "2025-01-01", "play_seconds": 321, "sessions": 7},
                "cleared": {"1-1": legacy_clear},
                "titles": ["既存の称号"], "stats": {"checks": 12},
                "settings": {"docker_mode": "mock"},
                "custom_note": "既存の拡張フィールド",
            }
            path.write_text(json.dumps(legacy, ensure_ascii=False))
            with patch.object(save, "SAVE", path):
                mission = runner.get_mission("7-5")
                result = save.record_clear(mission, hint_level=0,
                                           answer_viewed=False, seconds=42)
                self.assertTrue(result["first"])
                after = save.load()
                self.assertEqual(after["cleared"]["1-1"], legacy_clear)
                self.assertEqual(after["cleared"]["7-5"]["score"], 100)
                self.assertEqual(after["version"], 1)
                for key in ("player", "titles", "settings", "custom_note"):
                    self.assertEqual(after[key], legacy[key])
                self.assertEqual(after["stats"]["checks"], 12)
                self.assertEqual(after["stats"]["hints"], 0)
                best = after["cleared"]["7-5"].copy()
                repeated = save.record_clear(mission, hint_level=3,
                                             answer_viewed=True, seconds=99)
                self.assertFalse(repeated["first"])
                self.assertEqual(save.load()["cleared"]["7-5"], best)
                self.assertEqual(save.total_score(), 190)


if __name__ == "__main__":
    unittest.main()
