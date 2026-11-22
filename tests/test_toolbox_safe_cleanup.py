"""Exercise actual filesystem and tar with hostile filenames; reject loss and symlink shortcuts."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curriculum.toolbox_labs import LABS

LAB = LABS['safe-cleanup']


@unittest.skipUnless(all(shutil.which(t) for t in LAB['tools']), '実ツールが必要')
class SafeCleanupTests(unittest.TestCase):
    def fresh(self):
        temp = tempfile.TemporaryDirectory(prefix='dojo-safe-cleanup-')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        LAB['setup'](root)
        return root

    def execute(self, root, script):
        return subprocess.run(['bash', '-c', 'set -euo pipefail\n' + script], cwd=root,
                              capture_output=True, text=True, timeout=20)

    def solve(self):
        root = self.fresh()
        with self.assertRaises(ValueError):
            LAB['check'](root)
        result = self.execute(root, LAB['solution'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        LAB['check'](root)
        return root

    def test_real_solution_with_random_content_and_unusual_names(self):
        self.solve()
        self.solve()

    def test_wrong_examples_are_rejected(self):
        for script in LAB['wrong']:
            with self.subTest(script=script[:60]):
                root = self.fresh()
                self.execute(root, script)
                with self.assertRaises((ValueError, OSError)):
                    LAB['check'](root)

    def test_loss_tampering_and_symlink_replacement_rejected(self):
        for mutation in ('content', 'mode', 'plan', 'backup', 'protected', 'symlink'):
            with self.subTest(mutation=mutation):
                root = self.solve()
                target = root / 'quarantine/cache/-n.tmp'
                if mutation == 'content':
                    target.write_text('fake')
                elif mutation == 'mode':
                    target.chmod(0o644)
                elif mutation == 'plan':
                    with (root / 'candidates.nul').open('ab') as f:
                        f.write(b'cache/-n.tmp\0')
                elif mutation == 'backup':
                    (root / 'before-cleanup.tar.gz').write_bytes(b'fake')
                elif mutation == 'protected':
                    (root / 'important/records.tmp').unlink()
                else:
                    target.unlink()
                    target.symlink_to(root / 'restored/cache/-n.tmp')
                with self.assertRaises((ValueError, OSError, __import__('tarfile').TarError)):
                    LAB['check'](root)
