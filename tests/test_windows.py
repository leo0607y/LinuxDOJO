"""Windows 向けの動作を Linux 上で再現して確認する。すべて一時領域で実行。

- ファイル権限は Windows では模擬（Terminal.VIRTUAL_MODES）
- 実践モードは WSL が必要（runner.practice_supported が False）
"""
import contextlib
import io
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, readiness, runner, save


def real_mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class VirtualPermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-windows-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        virtual = patch.object(guided.Terminal, "VIRTUAL_MODES", True)
        virtual.start()
        self.addCleanup(virtual.stop)
        self.progress = {}
        self.term = guided.Terminal(self.base / "course", self.progress)

    def ok(self, command):
        result = self.term.execute(command)
        self.assertEqual(result.code, 0, f"{command}: {result.output}")
        return result.output

    def test_all_lessons_pass_in_order_with_virtual_permissions(self):
        from curriculum.beginner_lessons import LESSONS
        for mode, course in LESSONS.items():
            terminal = guided.Terminal(self.base / mode, {})
            for step in course:
                with self.subTest(mode=mode, lesson=step["id"]):
                    guided.prepare_step(terminal, step)
                    result = terminal.execute(step["command"])
                    expected = step.get("expected_code", 100 if step["command"] == "apt update" else 0)
                    self.assertEqual(result.code, expected, result.output)

    def test_chmod_and_ls_use_saved_permission_without_touching_the_real_file(self):
        self.ok("touch script.sh")
        before = real_mode(self.term.root / "script.sh")
        self.assertTrue(self.ok("ls -l script.sh").startswith("-rw-r--r--"))
        self.ok("chmod u+x script.sh")
        self.assertTrue(self.ok("ls -l script.sh").startswith("-rwxr--r--"))
        self.ok("chmod 600 script.sh")
        self.assertTrue(self.ok("ls -l script.sh").startswith("-rw-------"))
        self.assertEqual(real_mode(self.term.root / "script.sh"), before)
        self.assertEqual(self.progress["modes"], {"script.sh": 0o600})

    def test_private_key_needs_chmod_600_with_virtual_permissions(self):
        self.progress["ssh_known"] = True
        guided.prepare_step(self.term, {"files": {".ssh/training_key": "DUMMY-NOT-A-REAL-KEY\n"}})
        result = self.term.execute("ssh -i .ssh/training_key learner@training-server")
        self.assertIn("UNPROTECTED PRIVATE KEY", result.output)
        self.ok("chmod 600 .ssh/training_key")
        self.ok("ssh -i .ssh/training_key learner@training-server")
        self.assertTrue(self.progress["remote"])

    def test_move_keeps_and_remove_forgets_the_permission(self):
        self.ok("touch a.sh")
        self.ok("chmod 755 a.sh")
        self.ok("mkdir bin")
        self.ok("mv a.sh bin")
        self.assertEqual(self.progress["modes"], {"bin/a.sh": 0o755})
        self.ok("rm bin/a.sh")
        self.ok("touch bin/a.sh")
        self.assertTrue(self.ok("ls -l bin/a.sh").startswith("-rw-r--r--"))

    def test_new_copy_keeps_the_source_permission_like_real_cp(self):
        self.ok("touch secret.txt")
        self.ok("chmod 600 secret.txt")
        self.ok("cp secret.txt copy.txt")
        self.assertTrue(self.ok("ls -l copy.txt").startswith("-rw-------"))
        self.ok("touch existing.txt")
        self.ok("cp secret.txt existing.txt")
        self.assertTrue(self.ok("ls -l existing.txt").startswith("-rw-r--r--"))

    def test_reset_restores_expected_permission(self):
        step = {"files": {"script.sh": "echo original\n"}, "modes": {"script.sh": 0o744}}
        guided.prepare_step(self.term, step)
        self.ok("chmod 600 script.sh")
        guided.prepare_step(self.term, step)
        self.assertEqual(self.term.mode_of(self.term.path("script.sh")), 0o744)

    def test_nested_cwd_is_shown_with_forward_slashes(self):
        guided.prepare_step(self.term, {"cwd": "notes/archive"})
        self.assertEqual(self.progress["cwd"], "notes/archive")
        self.assertEqual(self.ok("pwd"), "/home/learner/notes/archive")

    def test_readiness_scenarios_accept_solutions_with_virtual_permissions(self):
        with patch.object(save, "SAVE", self.base / "save.json"):
            for scenario in readiness.scenarios():
                with self.subTest(scenario=scenario["id"]):
                    terminal = readiness.prepare(scenario, self.base / "readiness")
                    for command in scenario["solution"]:
                        result = terminal.execute(command)
                        expected = scenario.get("expected_codes", {}).get(command, 0)
                        self.assertEqual(result.code, expected, f"{command}: {result.output}")
                    self.assertTrue(readiness.check(scenario, terminal)[0])


class PracticeUnavailableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-windows-mode-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "save_data.json"
        for p in (patch.object(save, "SAVE", self.path),
                  patch.object(runner, "practice_supported", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def test_saved_practice_mode_falls_back_without_changing_the_save(self):
        d = save.empty()
        d["learning"]["mode"] = "practice"
        d["cleared"]["1-1"] = {"score": 100}
        save.store(d)
        self.assertEqual(guided.selected_mode(), "intro")
        d = save.load()
        d["learning"]["intro"]["completed"] = [step["id"] for step in guided.lessons("intro")]
        save.store(d)
        self.assertEqual(guided.selected_mode(), "basic")
        self.assertEqual(save.load()["learning"]["mode"], "practice")
        self.assertIn("1-1", save.load()["cleared"])

    def test_choosing_practice_shows_wsl_guide_and_keeps_mode(self):
        from engine import main
        save.store(save.empty())
        out = io.StringIO()
        with patch("builtins.input", side_effect=["5", "", "b"]), contextlib.redirect_stdout(out):
            main.mode_select()
        self.assertIn("wsl --install", out.getvalue())
        self.assertEqual(save.load()["learning"]["mode"], "intro")


class WindowsFilesTests(unittest.TestCase):
    def test_save_is_written_as_utf8(self):
        with tempfile.TemporaryDirectory(prefix="linuxdojo-utf8-test-") as tmp:
            path = Path(tmp) / "save.json"
            with patch.object(save, "SAVE", path):
                d = save.empty()
                d["titles"].append("🏅 ファイルシステムの開拓者")
                save.store(d)
                self.assertIn("開拓者", path.read_bytes().decode("utf-8"))
                self.assertEqual(save.load()["titles"], d["titles"])

    def test_windows_launcher_uses_crlf_and_scripts_stay_lf(self):
        bat = (ROOT / "start.bat").read_bytes()
        self.assertNotIn(b"\n", bat.replace(b"\r\n", b""))
        self.assertIn(b"chcp 65001", bat)
        self.assertIn(b"engine\\main.py", bat)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        for rule in ("*.sh    text eol=lf", "bin/**  text eol=lf", "*.bat   text eol=crlf"):
            self.assertIn(rule, attributes)


if __name__ == "__main__":
    unittest.main()
