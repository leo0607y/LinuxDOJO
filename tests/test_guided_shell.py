"""Shell syntax regressions for the safe training terminal."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import guided


class TrainingShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="linuxdojo-shell-")
        self.addCleanup(temporary.cleanup)
        self.terminal = guided.Terminal(Path(temporary.name) / "course", {})

    def ok(self, line):
        result = self.terminal.execute(line)
        self.assertEqual(result.code, 0, result.output)
        return result.output

    def test_quoted_and_escaped_globs_stay_literal(self):
        self.ok("touch app.log other.log")
        for spelling in ("'*.log'", '"*.log"', r"\*.log"):
            self.ok("echo " + spelling + ">.gitignore")
            self.assertEqual(self.terminal.path(".gitignore").read_text(), "*.log\n")
        self.assertEqual(self.ok("echo *.log"), "app.log other.log")

    def test_input_redirection_with_output_and_pipeline(self):
        self.terminal.restore_file("input.txt", "a b\nc d\n")
        self.ok("awk '{print $2}'<input.txt>output.txt")
        self.assertEqual(self.terminal.path("output.txt").read_text(), "b\nd\n")
        self.assertEqual(self.ok("cat < input.txt | grep c"), "c d")

    def test_quoted_operators_are_text(self):
        self.assertEqual(self.ok("echo '>' ';' '&&' '<'"), "> ; && <")
        self.ok("echo 'a|b' > note.txt")
        self.assertEqual(self.terminal.path("note.txt").read_text(), "a|b\n")
        self.assertNotEqual(self.terminal.execute("echo a;touch unexpected").code, 0)
        self.assertFalse(self.terminal.path("unexpected").exists())

    def test_redirects_still_cannot_escape_training_root(self):
        result = self.terminal.execute("cat </etc/passwd >copy.txt")
        self.assertNotEqual(result.code, 0)
        self.assertFalse(self.terminal.path("copy.txt").exists())

    def test_permission_and_force_removal_alternatives(self):
        self.ok("touch script.sh")
        self.ok("chmod 0750 script.sh")
        self.assertEqual(self.terminal.mode_of(self.terminal.path("script.sh")), 0o750)
        self.ok("rm -f script.sh missing.txt")
        self.assertFalse(self.terminal.path("script.sh").exists())
        self.assertNotEqual(self.terminal.execute("rm -rf .").code, 0)


if __name__ == "__main__":
    unittest.main()
