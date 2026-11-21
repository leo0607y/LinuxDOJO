"""Recorded-observation checks and guest module syntax; no privileged host actions."""
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
import curriculum.stage12_observability_ops  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which('bash'), 'Bash needed for workspace solutions')
class ObservabilityOpsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='linuxdojo-observability-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for key,value in (('WORKSPACE',self.root),('STATE',self.root/'.lq_state')):
            guard=patch.object(runner,key,value);guard.start();self.addCleanup(guard.stop)

    def prepare(self,n):
        mission=runner.get_mission(f'12-{n}')
        return mission,runner.prepare(mission,runner.new_token())

    def execute(self,m,ctx,script):
        result=subprocess.run(['bash','-c',m.render(script,ctx.data)],cwd=ctx.work,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return runner.run_check(m,ctx.token)

    def test_all_eight_initial_wrong_and_solution_routes(self):
        for n in range(1,9):
            m,ctx=self.prepare(n)
            with self.subTest(mission=m.id,route='initial'):
                self.assertFalse(runner.run_check(m,ctx.token)[0])
            for route,wrong in enumerate(m.wrong):
                m,ctx=self.prepare(n)
                with self.subTest(mission=m.id,route=route):
                    self.assertFalse(self.execute(m,ctx,wrong)[0])
            m,ctx=self.prepare(n)
            with self.subTest(mission=m.id,route='solution'):
                ok,message=self.execute(m,ctx,m.solution)
                self.assertTrue(ok,message)

    def test_high_iowait_does_not_prove_disk_failure(self):
        m,ctx=self.prepare(3)
        self.assertTrue(self.execute(m,ctx,m.solution)[0])
        data=json.loads(ctx.p('diagnosis.json').read_text());data['physical_failure_confirmed']=True
        ctx.p('diagnosis.json').write_text(json.dumps(data))
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_update_merge_keeps_original_local_binding_and_port(self):
        m,ctx=self.prepare(5)
        self.assertTrue(self.execute(m,ctx,m.solution)[0])
        ctx.p('work/app.conf').write_text(ctx.p('app.conf.rpmnew').read_text())
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_acl_fix_requires_existing_and_future_permissions(self):
        m,ctx=self.prepare(7)
        self.assertTrue(self.execute(m,ctx,m.solution)[0])
        ctx.p('work/reports.default.acl').unlink()
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_mac_cannot_be_disabled_as_a_remediation(self):
        m,ctx=self.prepare(8)
        self.assertTrue(self.execute(m,ctx,m.solution)[0])
        path=ctx.p('work/service-security.json');data=json.loads(path.read_text());data['mac_mode']='disabled';path.write_text(json.dumps(data))
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_vm_modules_have_valid_shell_and_definitions_without_side_effects_on_source(self):
        for name in ('performance','permissions'):
            path=ROOT/'labs/vm/guest/modules'/f'{name}.sh'
            result=subprocess.run(['bash','-n',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            command='source "$1"; declare -F lab_setup lab_break lab_check lab_reset'
            result=subprocess.run(['bash','-c',command,'check',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(result.stdout.splitlines()),4)
            # Wrong role/path rejects before any root action.
            command='source "$1"; export LAB_ROOT=/invalid LAB_STATE=/invalid/state LAB_VM_ROLE=client; lab_setup'
            result=subprocess.run(['bash','-c',command,'check',str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':
    unittest.main()
