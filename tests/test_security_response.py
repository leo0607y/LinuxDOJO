"""Incident exercises run only on synthetic files in a temporary workspace."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import runner
from curriculum import stage10_security_response as response


@unittest.skipUnless(shutil.which('bash'), 'real Bash required')
class SecurityResponseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='linuxdojo-incident-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, value in (('WORKSPACE', self.root), ('STATE', self.root / '.lq_state')):
            guard = patch.object(runner, name, value)
            guard.start()
            self.addCleanup(guard.stop)

    def prepare(self, number):
        mission = runner.get_mission(f'10-{number}')
        self.assertIsNotNone(mission)
        context = runner.prepare(mission, runner.new_token())
        return mission, context

    def execute(self, mission, context, script):
        result = subprocess.run(['bash', '-c', mission.render(script, context.data)],
                                cwd=str(context.work), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return runner.run_check(mission, context.token)

    def test_all_solutions_and_negative_routes(self):
        for number in range(1, 7):
            mission, ctx = self.prepare(number)
            with self.subTest(mission=mission.id, route='initial'):
                self.assertFalse(runner.run_check(mission, ctx.token)[0])
            for wrong in mission.wrong:
                mission, ctx = self.prepare(number)
                with self.subTest(mission=mission.id, route='wrong'):
                    self.assertFalse(self.execute(mission, ctx, wrong)[0])
            mission, ctx = self.prepare(number)
            with self.subTest(mission=mission.id, route='solution'):
                good, reason = self.execute(mission, ctx, mission.solution)
                self.assertTrue(good, reason)

    def test_case_identity_changes_and_success_event_is_not_compromise(self):
        mission, first = self.prepare(3)
        first_id = first.data['account']
        mission, ctx = self.prepare(3)
        self.assertNotEqual(first_id, ctx.data['account'])
        self.assertTrue(self.execute(mission, ctx, mission.solution)[0])
        finding = json.loads(ctx.p('triage.json').read_text())
        self.assertFalse(finding['compromise_confirmed'])
        self.assertEqual(finding['failed_events'], ['A01', 'A02'])
        self.assertNotIn('A05', finding['failed_events'])

    def test_timeline_offsets_and_complete_source_references(self):
        mission, ctx = self.prepare(2)
        self.assertTrue(self.execute(mission, ctx, mission.solution)[0])
        timeline = response.rows(ctx, 'timeline.csv')
        self.assertEqual(timeline[0]['utc'], '2026-11-20T23:00:00Z')
        self.assertEqual([r['event_id'] for r in timeline],
                         ['A01', 'A02', 'A03', 'W01', 'W02', 'A04', 'W03', 'A05'])
        self.assertEqual({r['source'] for r in timeline}, {'logs/auth.csv', 'logs/access.csv'})

    def test_retest_is_bound_to_current_config_and_preserves_service(self):
        mission, ctx = self.prepare(5)
        self.assertTrue(self.execute(mission, ctx, mission.solution)[0])
        settings = json.loads(ctx.p('settings.json').read_text())
        settings['session_max_age_minutes'] = 10
        ctx.p('settings.json').write_text(json.dumps(settings))
        self.assertFalse(runner.run_check(mission, ctx.token)[0])
        self.assertTrue(self.execute(mission, ctx, 'python3 verify.py > retest.json')[0])
        settings['service_enabled'] = False
        ctx.p('settings.json').write_text(json.dumps(settings))
        self.assertFalse(self.execute(mission, ctx, 'python3 verify.py > retest.json')[0])

    def test_report_rejects_wrong_evidence_and_scope(self):
        mission, ctx = self.prepare(6)
        self.assertTrue(self.execute(mission, ctx, mission.solution)[0])
        report = json.loads(ctx.p('report.json').read_text())
        report['findings'][0]['evidence'][0]['sha256'] = '0' * 64
        ctx.p('report.json').write_text(json.dumps(report))
        self.assertFalse(runner.run_check(mission, ctx.token)[0])
        self.assertTrue(self.execute(mission, ctx, mission.solution)[0])
        report = json.loads(ctx.p('report.json').read_text())
        report['scope'].append('unapproved-target')
        ctx.p('report.json').write_text(json.dumps(report))
        self.assertFalse(runner.run_check(mission, ctx.token)[0])


if __name__ == '__main__':
    unittest.main()
