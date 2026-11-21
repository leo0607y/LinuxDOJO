"""Validate authored examples with real bash separately from guided simulation."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curriculum.units.scripting import LESSONS
from engine import guided

BASH = shutil.which("bash")


class ScriptAuthoringInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="linuxdojo-script-input-")
        self.addCleanup(temporary.cleanup)
        self.terminal = guided.Terminal(Path(temporary.name) / "course", {})

    def test_all_authoring_commands_are_one_input_line(self):
        for step in LESSONS:
            with self.subTest(lesson=step["id"]):
                self.assertNotIn("\n", step["command"])
                guided.prepare_step(self.terminal, step, fresh=True)
                result = self.terminal.execute(step["command"])
                self.assertEqual(result.code, 0, result.output)
                self.assertEqual(self.terminal.path(step["source_file"]).read_text(encoding="utf-8"),
                                 step["source"])

    def test_printf_source_is_data_and_not_executed(self):
        result = self.terminal.execute("printf '%s\\n' '$(touch unexpected)' > source.txt")
        self.assertEqual(result.code, 0, result.output)
        self.assertEqual(self.terminal.path("source.txt").read_text(encoding="utf-8"),
                         "$(touch unexpected)\n")
        self.assertFalse(self.terminal.path("unexpected").exists())

    def test_unsupported_printf_formats_are_explicit(self):
        for line in ("printf '%d' 42", "printf '%s' hello"):
            with self.subTest(line=line):
                result = self.terminal.execute(line)
                self.assertNotEqual(result.code, 0)
                self.assertIn("%s", result.output)


@unittest.skipUnless(BASH, "real bash is required for runtime validation")
class AuthoredScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="linuxdojo-script-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_script(self, number, *args, environment=None):
        step = LESSONS[number - 1]
        path = self.root / step["source_file"]
        path.write_text(step["source"], encoding="utf-8")
        env = dict(os.environ)
        if environment:
            env.update(environment)
        return subprocess.run([BASH, str(path), *args], cwd=str(self.root), env=env,
                              text=True, capture_output=True, timeout=5)

    def test_every_shell_example_has_valid_bash_syntax(self):
        for step in LESSONS:
            if not step["source_file"].endswith(".sh"):
                continue
            with self.subTest(lesson=step["id"]):
                result = subprocess.run([BASH, "-n"], input=step["source"], text=True,
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_positional_arguments_keep_spaces_and_glob_characters(self):
        result = self.run_script(4, "two words", "*.log", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "two words\n*.log\n\n")
        self.assertEqual(self.run_script(5).returncode, 2)
        self.assertEqual(self.run_script(5, "two words").stdout, "two words\n")
        self.assertEqual(self.run_script(15).stdout, "guest\n")

    def test_error_stream_and_saved_failure_status(self):
        result = self.run_script(9)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (2, "", "usage: check FILE\n"))
        result = self.run_script(10)
        self.assertEqual((result.returncode, result.stdout), (1, "finished\n"))

    def test_no_glob_matches_and_names_with_spaces(self):
        self.assertEqual(self.run_script(12).stdout, "")
        (self.root / "two words.log").write_text("one\n", encoding="utf-8")
        self.assertEqual(self.run_script(12).stdout, "two words.log\n")

    def test_line_reader_keeps_spaces_and_backslashes(self):
        text = "  spaces  \nback\\slash\n\n"
        (self.root / "input file").write_text(text, encoding="utf-8")
        result = self.run_script(13, "input file")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, text)

    def test_cleanup_removes_only_its_temporary_file(self):
        directory = self.root / "temporary"
        directory.mkdir()
        keep = directory / "keep.txt"
        keep.write_text("keep\n", encoding="utf-8")
        result = self.run_script(16, environment={"TMPDIR": str(directory)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ready\n")
        self.assertEqual(list(directory.iterdir()), [keep])

    def test_report_handles_empty_results_and_invalid_arguments(self):
        path = self.root / "input log"
        path.write_text("INFO start\nERROR failed\n", encoding="utf-8")
        result = self.run_script(17, "input log")
        self.assertEqual((result.returncode, result.stdout), (0, "ERROR failed\n"))
        path.write_text("INFO start\n", encoding="utf-8")
        result = self.run_script(17, "input log")
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(self.run_script(17).returncode, 2)
        self.assertEqual(self.run_script(17, "missing").returncode, 1)


if __name__ == "__main__":
    unittest.main()
