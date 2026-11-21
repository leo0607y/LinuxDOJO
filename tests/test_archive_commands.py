"""アーカイブの復元可能性と、展開先の境界を検証する。"""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided
from engine.commands import archive


class ArchiveCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='linuxdojo-archive-test-')
        self.addCleanup(self.tmp.cleanup)
        self.terminal = guided.Terminal(Path(self.tmp.name) / 'workspace', {})

    def run_command(self, line, code=0):
        result = self.terminal.execute(line)
        self.assertEqual(result.code, code, result.output)
        return result.output

    def test_tar_roundtrip_preserves_contents_and_modes(self):
        guided.prepare_step(self.terminal, {'files': {'app/config.ini': 'mode=prod\n', 'app/run.sh': '#!/bin/bash\n'},
                                           'modes': {'app/run.sh': 0o750}, 'dirs': ['restore']})
        self.run_command('tar -czf backup.tar.gz app')
        self.assertIn('app/run.sh', self.run_command('tar -tf backup.tar.gz'))
        self.run_command('tar -xf backup.tar.gz -C restore')
        self.assertEqual(self.terminal.path('restore/app/config.ini').read_text(), 'mode=prod\n')
        self.assertEqual(self.terminal.mode_of(self.terminal.path('restore/app/run.sh')), 0o750)

    def test_rejects_traversal_links_and_special_files_before_writing(self):
        for bad_name, bad_type in [('../escape', tarfile.REGTYPE), ('/tmp/escape', tarfile.REGTYPE),
                                    ('link', tarfile.SYMTYPE), ('fifo', tarfile.FIFOTYPE)]:
            with self.subTest(name=bad_name, kind=bad_type):
                target = self.terminal.path('hostile.tar')
                with tarfile.open(target, 'w') as bundle:
                    safe = tarfile.TarInfo('safe.txt')
                    safe.size = 2
                    bundle.addfile(safe, io.BytesIO(b'ok'))
                    bad = tarfile.TarInfo(bad_name)
                    bad.type = bad_type
                    bad.linkname = '/tmp'
                    bundle.addfile(bad)
                self.assertNotEqual(self.terminal.execute('tar -xf hostile.tar').code, 0)
                self.assertFalse(self.terminal.path('safe.txt').exists(), 'Validate all names before writing anything')
        self.assertFalse((Path(self.tmp.name) / 'escape').exists())

    def test_gzip_keep_decompress_and_overwrite_protection(self):
        guided.prepare_step(self.terminal, {'files': {'app.log': 'line\n' * 40}})
        self.run_command('gzip -k app.log')
        self.assertTrue(self.terminal.path('app.log').exists())
        self.run_command('gunzip app.log.gz', 2)
        self.run_command('rm app.log')
        self.run_command('gunzip app.log.gz')
        self.assertEqual(self.terminal.path('app.log').read_text(), 'line\n' * 40)
        self.assertFalse(self.terminal.path('app.log.gz').exists())

    def test_find_size_depth_type_and_delete(self):
        guided.prepare_step(self.terminal, {'files': {'logs/empty.log': '', 'logs/big.log': 'a' * 2048,
                                                     'logs/sub/empty.log': ''}})
        self.assertEqual(self.run_command('find logs -type f -size +1k'), 'logs/big.log')
        self.assertEqual(self.run_command('find logs -maxdepth 1 -type f -size 0c'), 'logs/empty.log')
        self.run_command("find logs -type f -name 'empty.log' -delete")
        self.assertFalse(self.terminal.path('logs/empty.log').exists())
        self.assertFalse(self.terminal.path('logs/sub/empty.log').exists())
        self.assertTrue(self.terminal.path('logs/big.log').exists())

    def test_backup_goal_validates_data_and_compression(self):
        expected = {'app/config.ini': 'mode=prod\n'}
        scenario = {'expected_archives': {'backup.tar.gz': expected}}
        guided.prepare_step(self.terminal, {'files': expected})
        self.run_command('touch backup.tar.gz')
        self.assertFalse(archive.check(scenario, self.terminal)[0])
        self.run_command('tar -cf backup.tar.gz app')
        self.assertFalse(archive.check(scenario, self.terminal)[0])
        self.run_command('tar -czf backup.tar.gz app')
        self.assertIsNone(archive.check(scenario, self.terminal))
        self.run_command('echo changed > app/config.ini')
        self.run_command('tar -czf backup.tar.gz app')
        self.assertFalse(archive.check(scenario, self.terminal)[0])


if __name__ == '__main__':
    unittest.main()
