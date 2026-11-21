"""Security progress requires complete evidence of independent mission clears."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import runner, save, security_progress


class SecurityProgressTests(unittest.TestCase):
    def test_linux_clears_do_not_count_as_security_work(self):
        data = save.empty()
        data['cleared'] = {m.id: {'hints': 0, 'answer': False}
                           for m in runner.load_curriculum() if m.stage not in (8, 9, 10)}
        rows = security_progress.progress(data)
        self.assertEqual([r['total'] for r in rows], [6, 7, 6])
        self.assertEqual(sum(r['completed'] for r in rows), 0)

    def test_missing_assistance_metadata_is_not_independent(self):
        data = save.empty()
        data['cleared']['8-1'] = {'score': 100}
        self.assertEqual(security_progress.progress(data)[0]['completed'], 1)
        self.assertEqual(security_progress.progress(data)[0]['independent'], 0)

    def test_hint_and_answer_clears_can_be_replaced_by_independent_review(self):
        data = save.empty()
        for mission in runner.load_curriculum():
            if mission.stage in (8, 9, 10):
                data['cleared'][mission.id] = {'hints': 0, 'answer': False}
        self.assertTrue(any('すべて手本なしで修了' in line for line in security_progress.lines(data)))
        data['cleared']['8-1']['answer'] = True
        data['cleared']['9-1']['hints'] = 1
        rows = security_progress.progress(data)
        self.assertEqual(sum(r['completed'] for r in rows), 19)
        self.assertEqual(sum(r['independent'] for r in rows), 17)
        self.assertFalse(any('すべて手本なしで修了' in line for line in security_progress.lines(data)))


if __name__ == '__main__':
    unittest.main()
