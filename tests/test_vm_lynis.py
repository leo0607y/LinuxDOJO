"""Dedicated lynis lab: guards reject wrong context before any write; offline helper logic is exercised."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/lynis.sh"
BASH = shutil.which("bash")


def run_bash(script, *args, env=None):
    return subprocess.run([BASH, "-c", script, "t", str(MODULE), *args], env=env or {"PATH": "/nonexistent"},
                          capture_output=True, text=True, timeout=20)


@unittest.skipUnless(BASH, "Bash is required")
class VmLynisTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run([BASH, "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-lynis-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for ident, role in (("not-lynis", "app"), ("lynis", "client")):
                    with self.subTest(action=action, ident=ident):
                        result = run_bash('set -euo pipefail; source "$1"; "lab_$2"', action,
                                          env={"PATH": "/nonexistent", "LAB_ID": ident, "LAB_VM_ROLE": role, "LAB_STATE": str(root)})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_header_and_functions(self):
        text = MODULE.read_text()
        self.assertTrue(text.startswith("# title: "))
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_missing_package_prints_apt_line_without_writes(self):
        result = run_bash('set -u; source "$1"; _ly_paths; _ly_tools',
                          env={"PATH": "/nonexistent", "LAB_ID": "lynis", "LAB_VM_ROLE": "app",
                               "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/lynis"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt-get install -y lynis", result.stdout)

    REPORT = ("hardening_index={idx}\ntests_executed=BANN-7130|PKGS-7420|AUTH-9328|\n"
              "warning[]=W-1|something|\nsuggestion[]={sug}|text|-|-|\nsuggestion[]=AUTH-9328|umask|-|-|\n")

    def summarize(self, idx, sug):
        with tempfile.TemporaryDirectory(prefix="dojo-lynis-") as temporary:
            report = Path(temporary) / "r.dat"
            report.write_text(self.REPORT.format(idx=idx, sug=sug))
            result = run_bash('source "$1"; _ly_summary "$2"', str(report), env={"PATH": "/usr/bin:/bin"})
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_report_parsing_and_comparison(self):
        base, after = self.summarize(60, "BANN-7130"), self.summarize(62, "PKGS-7420")
        self.assertIn('"index": 60', base)
        self.assertIn('"suggestions": ["AUTH-9328", "BANN-7130"]', base)
        with tempfile.TemporaryDirectory(prefix="dojo-lynis-cmp-") as temporary:
            files = {}
            for name, text in (("base", base), ("after", after), ("same", self.summarize(60, "BANN-7130")), ("flat", self.summarize(60, "PKGS-7420"))):
                files[name] = Path(temporary) / (name + ".json"); files[name].write_text(text)
            def compare(a, targets):
                return run_bash('source "$1"; _ly_compare "$2" "$3" "$4"', str(files["base"]), str(files[a]), targets,
                                env={"PATH": "/usr/bin:/bin"}).returncode
            self.assertEqual(compare("after", "BANN-7130"), 0)
            self.assertEqual(compare("same", "BANN-7130"), 1)     # nothing fixed
            self.assertEqual(compare("flat", "BANN-7130"), 1)     # index not raised by the margin
            self.assertEqual(compare("after", "PKGS-7420"), 1)    # target still suggested
            self.assertEqual(compare("after", "NOPE-0000"), 1)    # target not executed

    def test_uses_own_report_files_and_cleans_only_its_own(self):
        text = MODULE.read_text()
        self.assertIn("--report-file", text)
        self.assertIn("--no-colors --quiet", text)
        self.assertNotIn("/var/log/lynis-report.dat", text.replace("# ", "").split("lab_setup")[1])
        reset = text.split("lab_reset()")[1]
        self.assertNotIn("apt-get remove", reset)
        self.assertNotIn("rm -rf", reset)


if __name__ == "__main__":
    unittest.main()
