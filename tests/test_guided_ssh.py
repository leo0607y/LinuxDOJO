"""基礎コマンドとSSH模擬学習の回帰テスト。通信せず一時領域だけを使う。"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, runner, save


class GuidedSSHTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-ssh-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.progress = {}
        self.term = guided.Terminal(self.base / "course", self.progress)

    def ok(self, command):
        result = self.term.execute(command)
        self.assertEqual(result.code, 0, f"{command}: {result.output}")
        return result.output

    def connect(self):
        self.ok("ssh learner@training-server")
        if not self.progress.get("remote"):
            self.assertTrue(self.progress.get("ssh_pending"))
            self.ok("yes")
        self.assertTrue(self.progress["remote"])

    def remote_file(self, name, text):
        guided.prepare_step(self.term, {
            "cwd": ".", "remote": False,
            "remote_files": {name: text},
        })

    def test_first_connection_can_be_declined_without_trusting_host(self):
        self.assertEqual(self.ok("hostname"), "dojo-local")
        message = self.ok("ssh learner@training-server")
        self.assertIn("SHA256:TRAINING-NOT-A-REAL-FINGERPRINT", message)
        self.assertTrue(self.progress["ssh_pending"])
        self.assertFalse(self.progress.get("remote", False))
        self.assertEqual(self.term.execute("no").code, 255)
        self.assertFalse(self.progress.get("ssh_pending", False))
        self.assertFalse(self.progress.get("ssh_known", False))
        self.assertFalse(self.progress.get("remote", False))
        self.assertEqual(self.ok("hostname"), "dojo-local")

    def test_confirmation_changes_host_and_exit_restores_local_directory(self):
        self.ok("mkdir work")
        self.ok("cd work")
        self.connect()
        self.assertTrue(self.progress["ssh_known"])
        self.assertEqual(self.ok("hostname"), "training-server")
        self.assertEqual(self.ok("pwd"), "/home/learner")
        self.ok("mkdir remote-work")
        self.ok("cd remote-work")
        self.ok("exit")
        self.assertFalse(self.progress.get("remote", False))
        self.assertEqual(self.ok("hostname"), "dojo-local")
        self.assertEqual(self.ok("pwd"), "/home/learner/work")
        self.assertFalse((self.term.root / "remote-work").exists())

    def test_same_filename_does_not_mix_local_and_remote_content(self):
        self.ok("echo local-data > note.txt")
        self.connect()
        self.ok("echo remote-data > note.txt")
        self.assertEqual(self.ok("cat note.txt"), "remote-data")
        self.ok("exit")
        self.assertEqual(self.ok("cat note.txt"), "local-data")
        self.assertEqual((self.term.root / ".remote/note.txt").read_text(), "remote-data\n")

    def test_reconnection_uses_remembered_host_and_dummy_key(self):
        self.connect()
        self.ok("exit")
        self.ok("mkdir -p .ssh")
        # 無効な教材用文字列。実際の秘密鍵は作成・取得しない。
        key = self.term.root / ".ssh/training_key"
        key.write_text("DUMMY-NOT-A-REAL-KEY\n")
        key.chmod(0o600)
        self.ok("ssh -p 2222 -i .ssh/training_key learner@training-server")
        self.assertTrue(self.progress["remote"])
        self.assertFalse(self.progress.get("ssh_pending", False))

    def test_missing_or_nontraining_private_key_is_rejected(self):
        self.progress["ssh_known"] = True
        self.assertNotEqual(self.term.execute("ssh -i .ssh/missing learner@training-server").code, 0)
        self.ok("mkdir -p .ssh")
        key = self.term.root / ".ssh/training_key"
        key.write_text("arbitrary-test-data-not-a-training-key\n")
        key.chmod(0o600)
        self.assertNotEqual(self.term.execute("ssh -i .ssh/training_key learner@training-server").code, 0)
        self.assertFalse(self.progress.get("remote", False))

    def test_readable_private_key_is_rejected_until_its_permission_is_600(self):
        self.progress["ssh_known"] = True
        self.ok("mkdir -p .ssh")
        key = self.term.root / ".ssh/training_key"
        key.write_text("DUMMY-NOT-A-REAL-KEY\n")
        key.chmod(0o644)
        result = self.term.execute("ssh -i .ssh/training_key learner@training-server")
        self.assertEqual(result.code, 255)
        self.assertIn("UNPROTECTED PRIVATE KEY", result.output)
        self.assertFalse(self.progress.get("remote", False))
        self.ok("chmod 600 .ssh/training_key")
        self.ok("ssh -i .ssh/training_key learner@training-server")
        self.assertTrue(self.progress["remote"])

    def test_connection_errors_do_not_start_a_local_or_remote_session(self):
        self.progress["ssh_known"] = True
        for command in (
            "ssh guest@training-server",
            "ssh -p 9999 learner@training-server",
            "ssh learner@outside.invalid",
            "ssh -o ProxyCommand=anything learner@training-server",
        ):
            with self.subTest(command=command):
                result = self.term.execute(command)
                self.assertNotEqual(result.code, 0)
                self.assertFalse(self.progress.get("remote", False))
        self.assertEqual(self.term.execute("ssh guest@training-server").code, 255)
        self.assertEqual(self.term.execute("ssh -p 9999 learner@training-server").code, 255)
        self.assertEqual(self.ok("hostname"), "dojo-local")

    def test_scp_upload_and_download_preserve_source_and_separate_hosts(self):
        self.progress["ssh_known"] = True
        self.ok("echo upload-data > note.txt")
        self.remote_file("download.txt", "download-data\n")
        self.ok("scp note.txt learner@training-server:upload.txt")
        self.assertEqual((self.term.root / "note.txt").read_text(), "upload-data\n")
        self.assertEqual((self.term.root / ".remote/upload.txt").read_text(), "upload-data\n")
        self.ok("scp learner@training-server:download.txt received.txt")
        self.assertEqual((self.term.root / "received.txt").read_text(), "download-data\n")
        self.assertEqual((self.term.root / ".remote/download.txt").read_text(), "download-data\n")
        self.assertFalse(self.progress.get("remote", False))

    def test_local_and_remote_roots_are_not_accessible_through_each_other(self):
        self.assertNotIn(".remote", self.ok("ls -a"))
        self.assertEqual(self.ok("find . -name server-note.txt"), "")
        self.assertNotEqual(self.term.execute("cat .remote/server-note.txt").code, 0)
        self.connect()
        self.assertNotEqual(self.term.execute("cat ../welcome.txt").code, 0)
        self.assertNotEqual(self.term.execute("echo changed > ../welcome.txt").code, 0)
        self.ok("exit")
        self.assertEqual(self.ok("cat welcome.txt"), "LinuxDOJOへようこそ！")

    def test_scp_does_not_silently_trust_an_unknown_host(self):
        self.ok("echo training > note.txt")
        result = self.term.execute("scp note.txt learner@training-server:upload.txt")
        self.assertEqual(result.code, 255)
        self.assertFalse(self.progress.get("ssh_known", False))
        self.assertFalse((self.term.root / ".remote/upload.txt").exists())

    def test_transfer_paths_and_symlinks_cannot_escape_either_host(self):
        self.progress["ssh_known"] = True
        self.ok("echo training > note.txt")
        outside = self.base / "private-fixture.txt"
        outside.write_text("private test fixture\n")
        self.remote_file("download.txt", "download-data\n")
        for command in (
            "scp note.txt learner@training-server:../outside.txt",
            "scp note.txt learner@training-server:/etc/passwd",
            "scp learner@training-server:../private-fixture.txt leaked.txt",
            "scp learner@training-server:download.txt ../private-fixture.txt",
            "scp note.txt learner@outside.invalid:upload.txt",
        ):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)
        remote_root = self.term.root / ".remote"
        (remote_root / "link").symlink_to(outside)
        self.assertNotEqual(self.term.execute("scp learner@training-server:link leaked.txt").code, 0)
        self.assertNotEqual(self.term.execute("scp note.txt learner@training-server:link").code, 0)
        self.assertEqual(outside.read_text(), "private test fixture\n")
        self.assertFalse((self.term.root / "leaked.txt").exists())

    def test_ssh_and_scp_never_invoke_host_processes_or_network_connections(self):
        self.ok("echo training > note.txt")
        with patch("subprocess.run", side_effect=AssertionError("host process")), \
             patch("subprocess.Popen", side_effect=AssertionError("host process")), \
             patch("os.system", side_effect=AssertionError("host shell")), \
             patch("socket.create_connection", side_effect=AssertionError("network connection")), \
             patch("socket.socket.connect", side_effect=AssertionError("network connection")):
            self.connect()
            self.ok("hostname")
            self.ok("exit")
            self.ok("scp note.txt learner@training-server:upload.txt")
            self.assertNotEqual(self.term.execute("ssh learner@outside.invalid").code, 0)

    def test_pending_confirmation_and_remote_files_survive_terminal_restart(self):
        self.ok("ssh learner@training-server")
        self.assertTrue(self.progress["ssh_pending"])
        restarted = guided.Terminal(self.term.root, self.progress)
        self.assertEqual(restarted.execute("yes").code, 0)
        self.assertTrue(self.progress["remote"])
        self.assertEqual(restarted.execute("echo saved > remote.txt").code, 0)
        resumed = guided.Terminal(self.term.root, self.progress)
        self.assertEqual(resumed.execute("cat remote.txt").output, "saved")
        self.assertEqual(resumed.execute("exit").code, 0)
        self.assertNotEqual(resumed.execute("cat remote.txt").code, 0)


class GuidedEssentialCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-essentials-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "course"
        self.progress = {}
        self.term = guided.Terminal(self.root, self.progress)

    def ok(self, command):
        result = self.term.execute(command)
        self.assertEqual(result.code, 0, result.output)
        return result.output

    def test_help_and_manual_explain_options_without_using_system_man(self):
        with patch("subprocess.run", side_effect=AssertionError("host man")):
            self.assertIn("-a", self.ok("ls --help"))
            self.assertIn("ls", self.ok("man ls"))

    def test_viewing_head_tail_and_find_reports_actual_training_files(self):
        (self.root / "report.txt").write_text("one\ntwo\nthree\nfour\n")
        self.assertEqual(self.ok("head -n 2 report.txt").strip(), "one\ntwo")
        self.assertEqual(self.ok("tail -n 2 report.txt").strip(), "three\nfour")
        self.ok("mkdir -p docs/sub")
        self.ok("touch docs/sub/note.txt")
        self.ok("touch docs/other.txt")
        found = self.ok("find . -name note.txt")
        self.assertIn("docs/sub/note.txt", found)
        self.assertNotIn("other.txt", found)
        self.assertNotEqual(self.term.execute("find .. -name note.txt").code, 0)

    def test_redirected_command_output_is_saved_without_executing_a_shell(self):
        (self.root / "app.log").write_text("INFO ready\nERROR failed\n")
        self.ok("grep ERROR app.log > errors.txt")
        self.assertEqual((self.root / "errors.txt").read_text(), "ERROR failed\n")
        self.ok("head -n 1 app.log >> errors.txt")
        self.assertEqual((self.root / "errors.txt").read_text(), "ERROR failed\nINFO ready\n")
        for command in ("> note.txt", ">> note.txt", "head -n 1 app.log >", "head -n 1 app.log > one two"):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)
        self.assertFalse((self.root / "note.txt").exists())

    def test_history_and_exit_status_distinguish_failure_from_success(self):
        self.ok("pwd")
        self.assertEqual(self.term.execute("false").code, 1)
        self.assertEqual(self.ok("echo $?"), "1")
        self.assertEqual(self.ok("echo $?"), "0")
        history = self.ok("history")
        self.assertIn("pwd", history)
        self.assertIn("false", history)
        self.assertIn("echo $?", history)


class GuidedSSHProgressTests(unittest.TestCase):
    def test_exit_in_an_ssh_lesson_disconnects_and_completes_the_step(self):
        course = [
            {"id": "ssh-exit-fixture", "title": "切断", "explanation": "SSH の接続を終了します。",
             "task": "exit で戻る", "command": "exit", "success": "ローカルに戻りました。",
             "remote": True, "cwd": "."},
            {"id": "ssh-local-fixture", "title": "接続先確認", "explanation": "自分の端末を確認します。",
             "task": "hostname", "command": "hostname", "success": "確認できました。",
             "remote": False, "cwd": "."},
        ]
        with tempfile.TemporaryDirectory(prefix="linuxdojo-ssh-exit-test-") as tmp:
            base = Path(tmp)
            with patch.object(save, "SAVE", base / "save.json"), \
                 patch.object(runner, "WORKSPACE", base / "workspace"), \
                 patch.object(guided, "lessons", return_value=course), \
                 patch.object(guided.ui, "clear"), \
                 patch("builtins.input", side_effect=["exit", "menu"]), \
                 contextlib.redirect_stdout(io.StringIO()):
                guided.play("basic")
                progress = guided.progress_for("basic")
                self.assertIn("ssh-exit-fixture", progress["completed"])
                self.assertEqual(progress["cursor"], "ssh-local-fixture")
                self.assertFalse(progress.get("remote", False))

    def test_remote_confirmation_state_is_saved_per_mode_and_keeps_practice_results(self):
        with tempfile.TemporaryDirectory(prefix="linuxdojo-ssh-save-test-") as tmp:
            path = Path(tmp) / "save.json"
            with patch.object(save, "SAVE", path):
                data = save.empty()
                data["cleared"]["1-1"] = {"score": 100}
                data["learning"]["mode"] = "basic"
                save.store(data)
                progress = guided.progress_for("basic")
                terminal = guided.Terminal(Path(tmp) / "course", progress)
                self.assertEqual(terminal.execute("ssh learner@training-server").code, 0)
                guided.remember("basic", progress)
                reloaded = save.load()
                self.assertTrue(reloaded["learning"]["basic"]["ssh_pending"])
                self.assertFalse(reloaded["learning"]["intro"].get("ssh_pending", False))
                self.assertEqual(reloaded["cleared"], data["cleared"])
                self.assertEqual(reloaded["learning"]["mode"], "basic")


if __name__ == "__main__":
    unittest.main()
