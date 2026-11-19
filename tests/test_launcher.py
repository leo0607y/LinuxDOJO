"""start 登録の回帰テスト。HOME と教材を一時領域に置き、実ユーザー設定は変更しない。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-launcher-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home with spaces"
        self.home.mkdir()
        self.project = self.base / "project with spaces"
        self.project.mkdir()
        shutil.copyfile(ROOT / "install-start.sh", self.project / "install-start.sh")
        self.target = self.project / "start.sh"
        self.target.write_text('#!/usr/bin/env bash\nprintf "TARGET_OK:%s\\n" "$@"\n')
        self.target.chmod(0o644)  # ZIPで実行権限がなくても起動できる。
        self.bin = self.home / ".local/bin"
        self.installed = self.bin / "start"
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "LANG": "C.UTF-8"}
        self.profile = self.home / ".bashrc"
        self.profile.write_text("# keep my shell settings\n")

    def install(self, *args, env=None):
        return subprocess.run(["bash", str(self.project / "install-start.sh"), *args],
                              cwd=self.project, env=env or self.env,
                              capture_output=True, text=True, timeout=10)

    def test_install_and_run_from_another_directory_with_arguments(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(self.installed, os.X_OK))
        result = subprocess.run(["bash", "-c", 'start --check "a b"'], cwd=self.home,
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "TARGET_OK:--check\nTARGET_OK:a b\n")
        self.assertEqual(self.profile.read_text(), "# keep my shell settings\n")

    def test_registration_is_idempotent(self):
        self.assertEqual(self.install().returncode, 0)
        before = self.installed.read_bytes()
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.installed.read_bytes(), before)
        self.assertEqual(list(self.bin.glob(".linuxdojo-start.*")), [])

    def test_existing_destination_file_is_never_overwritten_or_removed(self):
        self.bin.mkdir(parents=True)
        self.installed.write_text("existing command\n")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.installed.read_text(), "existing command\n")
        self.assertNotEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.installed.read_text(), "existing command\n")

    def test_existing_or_broken_symlink_is_not_overwritten(self):
        self.bin.mkdir(parents=True)
        self.installed.symlink_to(self.base / "not-created")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(self.installed.is_symlink())
        self.assertEqual(os.readlink(self.installed), str(self.base / "not-created"))

    def test_other_start_in_path_is_not_shadowed(self):
        other = self.base / "other-bin"
        other.mkdir()
        external = other / "start"
        external.write_text("#!/bin/sh\nexit 0\n")
        external.chmod(0o755)
        env = dict(self.env, PATH=f"{other}:{self.env['PATH']}")
        self.assertNotEqual(self.install(env=env).returncode, 0)
        self.assertFalse(self.installed.exists())
        self.assertEqual(external.read_text(), "#!/bin/sh\nexit 0\n")

    def test_exported_shell_function_collision_is_rejected(self):
        env = dict(self.env)
        env["BASH_FUNC_start%%"] = "() { echo external; }"
        self.assertNotEqual(self.install(env=env).returncode, 0)
        self.assertFalse(self.installed.exists())

    def test_missing_path_entry_prints_instructions_without_changing_profile(self):
        env = dict(self.env, PATH="/usr/bin:/bin")
        result = self.install(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', result.stdout)
        self.assertEqual(self.profile.read_text(), "# keep my shell settings\n")
        self.assertTrue(self.installed.exists())

    def test_uninstall_only_removes_our_registration(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertFalse(self.installed.exists())
        self.assertTrue(self.target.exists())
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.profile.read_text(), "# keep my shell settings\n")

    def test_failure_to_create_destination_is_nonzero(self):
        (self.home / ".local").write_text("file blocking directory\n")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse(self.installed.exists())
        self.assertEqual((self.home / ".local").read_text(), "file blocking directory\n")

    def test_unknown_option_does_not_register_anything(self):
        self.assertEqual(self.install("--unexpected").returncode, 2)
        self.assertFalse(self.installed.exists())


if __name__ == "__main__":
    unittest.main()
