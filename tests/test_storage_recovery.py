"""Captured-data diagnosis is tested independently of privileged VM operations."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from engine import runner
import curriculum.stage11_storage_recovery  # noqa: F401


@unittest.skipUnless(shutil.which('bash'),'real bash required')
class StorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='linuxdojo-storage-')
        self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for name,value in (('WORKSPACE',self.root/'workspace'),('STATE',self.root/'workspace/.lq_state')):
            guard=patch.object(runner,name,value);guard.start();self.addCleanup(guard.stop)

    def prepare(self,n):
        m=runner.get_mission('11-'+str(n));return m,runner.prepare(m,runner.new_token())

    def execute(self,m,ctx,source):
        proc=subprocess.run(['bash','-c',m.render(source,ctx.data)],cwd=ctx.work,text=True,capture_output=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        return runner.run_check(m,ctx.token)

    def test_all_initial_wrong_and_solution_routes(self):
        for n in range(1,9):
            m,ctx=self.prepare(n)
            self.assertFalse(runner.run_check(m,ctx.token)[0],m.id)
            for wrong in m.wrong:
                m,ctx=self.prepare(n)
                with self.subTest(mission=m.id,route='wrong'):
                    self.assertFalse(self.execute(m,ctx,wrong)[0])
            m,ctx=self.prepare(n)
            with self.subTest(mission=m.id,route='solution'):
                ok,reason=self.execute(m,ctx,m.solution);self.assertTrue(ok,reason)

    def test_topology_source_cannot_be_rewritten(self):
        m,ctx=self.prepare(1);self.assertTrue(self.execute(m,ctx,m.solution)[0])
        ctx.p('capture/lsblk.json').write_text('{}')
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_fstab_uses_same_uuid_and_preserves_root(self):
        m,ctx=self.prepare(2);self.assertTrue(self.execute(m,ctx,m.solution)[0])
        text=ctx.p('fstab').read_text();ctx.p('fstab').write_text(text.replace('root-fixture','wrong-root'))
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_lvm_free_space_and_filesystem_are_distinct(self):
        m,ctx=self.prepare(4);self.assertTrue(self.execute(m,ctx,m.solution)[0])
        data=json.loads(ctx.p('result.json').read_text());data['filesystem_action']='none'
        ctx.p('result.json').write_text(json.dumps(data));self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_restore_does_not_accept_replaced_hash_or_wrong_mode(self):
        m,ctx=self.prepare(6);self.assertTrue(self.execute(m,ctx,m.solution)[0])
        ctx.p('live/config.ini').chmod(0o644)
        self.assertFalse(runner.run_check(m,ctx.token)[0])
        ctx.p('live/config.ini').chmod(0o640)
        ctx.p('backup/SHA256SUMS').write_text('0'*64+'  backup/config.ini\n')
        self.assertFalse(runner.run_check(m,ctx.token)[0])

    def test_guest_modules_parse_and_reject_unexpected_context(self):
        repository=Path(__file__).resolve().parent.parent
        for name in ('storage','boot'):
            module=repository/'labs/vm/guest/modules'/f'{name}.sh'
            syntax=subprocess.run(['bash','-n',str(module)],capture_output=True,text=True)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            script='set -euo pipefail\nsource "$1"\nLAB_ID=wrong LAB_VM_ROLE=app LAB_STATE=/tmp/not-a-lab lab_setup'
            result=subprocess.run(['bash','-c',script,'context-check',str(module)],cwd=self.root,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('unexpected lab context',result.stderr)


if __name__=='__main__':unittest.main()
