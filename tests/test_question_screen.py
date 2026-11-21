"""Question headers survive repeated errors; terminal state is restored on exit."""
import contextlib
import io
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided, readiness, runner, save, ui

try:
    import pyte
except ImportError:
    pyte = None


class TtyOutput(io.StringIO):
    def isatty(self):
        return True


class QuestionScreenTests(unittest.TestCase):
    def setUp(self):
        self.output = TtyOutput()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(sys, "stdout", self.output))
        self.stack.enter_context(patch.object(sys.stdin, "isatty", return_value=True))
        self.stack.enter_context(patch.dict(os.environ, {"TERM": "xterm-256color"}))
        self.size = self.stack.enter_context(patch.object(ui.QuestionScreen, "_dimensions",
                                                       return_value=os.terminal_size((80, 24))))

    def test_repeated_error_refreshes_do_not_redraw_or_erase_the_question(self):
        with ui.QuestionScreen(["Question", "Keep this task visible"]) as screen:
            header = self.output.getvalue()
            self.assertTrue(screen.active)
            for index in range(50):
                print("Incorrect attempt", index)
                screen.refresh()
            during = self.output.getvalue()
            self.assertEqual(during.count("Keep this task visible"), 1)
            self.assertEqual(during.count("\x1b[2J"), 1)
            self.assertNotIn("\x1b[3J", during)
            self.assertTrue(during.startswith(header))
        self.assertTrue(self.output.getvalue().endswith("\x1b[r\x1b[24;1H\n"))

    def test_long_explanation_uses_full_task_in_compact_header(self):
        task = "keep complete task " * 12
        with ui.QuestionScreen(["Title", *["long explanation"] * 35, task],
                               summary=["Title", task]) as screen:
            self.assertTrue(screen.active)
            emitted = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", self.output.getvalue())
            compact = re.sub(r"[\s│]+", "", emitted)  # wrapping may split words
            self.assertEqual(compact.count("keepcompletetask"), 12)
            self.assertNotIn("long explanation", emitted)

    def test_tiny_or_unfit_task_falls_back_without_changing_scroll_margins(self):
        for size in ((25, 10), (80, 12)):
            with self.subTest(size=size):
                self.size.return_value = os.terminal_size(size)
                self.output.seek(0)
                self.output.truncate()
                with ui.QuestionScreen(["Title", "complete task"] * 12) as screen:
                    self.assertFalse(screen.active)
                self.assertNotIn("\x1b[", self.output.getvalue())
                self.assertEqual(self.output.getvalue().count("complete task"), 12)

    def test_redirected_and_dumb_output_stays_plain(self):
        for interactive, term in ((False, "xterm"), (True, "dumb")):
            with self.subTest(interactive=interactive, term=term):
                plain = io.StringIO()
                with patch.object(sys, "stdout", plain), \
                     patch.object(sys.stdin, "isatty", return_value=interactive), \
                     patch.dict(os.environ, {"TERM": term}):
                    with ui.QuestionScreen(["Title", "Task"]) as screen:
                        self.assertFalse(screen.active)
                self.assertIn("Task", plain.getvalue())
                self.assertNotIn("\x1b[", plain.getvalue())

    def test_resize_reflows_header_and_exception_restores_terminal_handler(self):
        previous = signal.getsignal(signal.SIGWINCH) if hasattr(signal, "SIGWINCH") else None
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with ui.QuestionScreen(["Title", "Task"]) as screen:
                self.size.return_value = os.terminal_size((100, 30))
                screen.refresh()
                self.assertEqual(self.output.getvalue().count("Task"), 2)
                raise RuntimeError("stop")
        self.assertFalse(screen.active)
        self.assertTrue(self.output.getvalue().endswith("\x1b[r\x1b[30;1H\n"))
        if hasattr(signal, "SIGWINCH"):
            self.assertEqual(signal.getsignal(signal.SIGWINCH), previous)


class GuidedQuestionIntegrationTests(unittest.TestCase):
    def test_guided_wrong_attempts_keep_one_question_and_exit_cleanly(self):
        with tempfile.TemporaryDirectory(prefix="dojo-question-guided-") as temporary:
            root = Path(temporary)
            output = TtyOutput()
            with patch.object(runner, "WORKSPACE", root / "workspace"), \
                 patch.object(save, "SAVE", root / "save.json"), \
                 patch.object(sys.stdin, "isatty", return_value=True), \
                 patch.object(sys, "stdout", output), \
                 patch.dict(os.environ, {"TERM": "xterm"}), \
                 patch.object(ui.QuestionScreen, "_dimensions", return_value=os.terminal_size((80, 24))), \
                 patch("builtins.input", side_effect=["not-a-command"] * 30 + ["menu"]):
                guided.play("intro")
            text = output.getvalue()
            self.assertEqual(text.count("やってみよう:"), 1)
            self.assertEqual(text.count("\x1b[2J"), 1)
            self.assertTrue(text.endswith("\x1b[r\x1b[24;1H\n"))

    def test_readiness_check_failures_keep_one_brief_and_exit_cleanly(self):
        scenario = readiness.scenarios()[0]
        with tempfile.TemporaryDirectory(prefix="dojo-question-readiness-") as temporary:
            root = Path(temporary)
            output = TtyOutput()
            with patch.object(runner, "WORKSPACE", root / "workspace"), \
                 patch.object(save, "SAVE", root / "save.json"), \
                 patch.object(sys.stdin, "isatty", return_value=True), \
                 patch.object(sys, "stdout", output), \
                 patch.dict(os.environ, {"TERM": "xterm"}), \
                 patch.object(ui.QuestionScreen, "_dimensions", return_value=os.terminal_size((80, 24))), \
                 patch("builtins.input", side_effect=["check"] * 25 + ["menu"]):
                readiness.play(scenario)
            self.assertEqual(output.getvalue().count(scenario["title"]), 1)
            self.assertEqual(output.getvalue().count("\x1b[2J"), 1)
            self.assertTrue(output.getvalue().endswith("\x1b[r\x1b[24;1H\n"))


@unittest.skipUnless(pyte is not None and sys.platform != "win32",
                     "Optional PTY terminal-state verification requires pyte")
class RealTerminalQuestionTests(unittest.TestCase):
    def test_pty_question_remains_visible_after_a_hundred_errors(self):
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        script = """from engine import ui
with ui.QuestionScreen(['QUESTION TITLE', 'TASK: preserve this question']) as screen:
    for i in range(100):
        print('Wrong attempt %d: correct the command' % i)
        screen.refresh()
    print('READY')
    input()
"""
        env = dict(os.environ, TERM="xterm-256color", PYTHONUNBUFFERED="1")
        process = subprocess.Popen([sys.executable, "-c", script], cwd=ui.__file__.rsplit("/engine/", 1)[0],
                                   stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        stream = pyte.Stream(pyte.Screen(80, 24))
        screen = stream.listener
        import select
        captured = b""
        while b"READY" not in captured:
            self.assertTrue(select.select([master], [], [], 10)[0], "PTY output timed out")
            data = os.read(master, 65536)
            self.assertTrue(data, "child ended before its prompt")
            captured += data
        stream.feed(captured.decode())
        self.assertIn("QUESTION TITLE", screen.display[1])
        self.assertIn("TASK: preserve this question", "\n".join(screen.display[:5]))
        self.assertIn("Wrong attempt 99", "\n".join(screen.display[5:]))
        self.assertNotIn("Wrong attempt 0:", "\n".join(screen.display))
        os.write(master, b"\n")
        process.wait(timeout=5)
        remainder = b""
        while select.select([master], [], [], 0.2)[0]:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            remainder += data
        stream.feed(remainder.decode())
        self.assertIsNone(screen.margins, "normal terminal margins must be restored")


if __name__ == "__main__":
    unittest.main()
