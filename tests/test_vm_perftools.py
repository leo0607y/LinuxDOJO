"""Guards and static checks for the perftools VM lab (not verified in a real VM)."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/perftools.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmPerftoolsTests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run(["bash", "-n", str(MODULE)], check=True)

    def test_header_and_functions(self):
        text = MODULE.read_text()
        self.assertRegex(text, r"(?m)^# title: .+")
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-perftools-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-perftools", "app"), ("perftools", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role,
                                 "LAB_STATE": str(root), "LAB_ROOT": "/var/lib/linuxdojo-vm-lab"},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def _copy(self, base):
        state = base / "state/perftools"
        text = MODULE.read_text().replace("/var/lib/linuxdojo-vm-lab/state/perftools", str(state)) \
            .replace('${LAB_ROOT:-} != /var/lib/linuxdojo-vm-lab', '${LAB_ROOT:-} != ' + str(base))
        script = base / "perftools.sh"
        script.write_text(text)
        return script, state

    def _run(self, script, state, base, action, timeout=60):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "x", str(script), action],
            env={"PATH": "/usr/sbin:/usr/bin:/bin", "LAB_ID": "perftools", "LAB_VM_ROLE": "app",
                 "LAB_STATE": str(state), "LAB_ROOT": str(base)},
            capture_output=True, text=True, timeout=timeout)

    def test_missing_tools_print_apt_line_and_write_nothing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-pt-") as temporary:
            base = Path(temporary)
            script, state = self._copy(base)
            state.mkdir(parents=True)
            empty = base / "bin"
            empty.mkdir()
            result = subprocess.run(
                ["/bin/bash", "-c", 'set -euo pipefail; source "$1"; lab_setup', "x", str(script)],
                env={"PATH": str(empty), "LAB_ID": "perftools", "LAB_VM_ROLE": "app",
                     "LAB_STATE": str(state), "LAB_ROOT": str(base)},
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("apt-get install -y sysstat", result.stderr)
            self.assertEqual(list(state.iterdir()), [])

    def test_check_refuses_before_break_and_rejects_stale_or_wrong_answers(self):
        tools = ("vmstat", "iostat", "sar", "mpstat", "pidstat", "lsof", "ss", "free", "top", "ps", "python3")
        if not all(shutil.which(t) for t in tools):
            self.skipTest("measurement tools not installed")
        with tempfile.TemporaryDirectory(prefix="dojo-pt-") as temporary:
            base = Path(temporary)
            script, state = self._copy(base)
            state.mkdir(parents=True)
            self.assertNotEqual(self._run(script, state, base, "check").returncode, 0)
            self.assertEqual(self._run(script, state, base, "setup").returncode, 0)
            try:
                self.assertEqual(self._run(script, state, base, "break").returncode, 0)
                blank = self._run(script, state, base, "check")
                self.assertNotEqual(blank.returncode, 0)
                self.assertIn("stale", blank.stderr)
                import time
                time.sleep(0.05)
                pid = lambda role: (state / "pids" / (role + ".pid")).read_text().strip()
                wrong = "\n".join("%s=1" % k for k in ("cpu_pid", "writer_pid", "write_kb_s", "holder_pid",
                                                       "holder_rss_kb", "fd_pid", "fd_count", "listener_pid", "conn_count"))
                (state / "answers.txt").write_text(wrong + "\n")
                self.assertNotEqual(self._run(script, state, base, "check").returncode, 0)
                # Correct answers computed from live /proc must pass (tick process is the decoy).
                import os
                port = Path("/proc/%s/cmdline" % pid("net")).read_bytes().split(b"\0")[6].decode()
                ss = subprocess.run(["ss", "-Htn", "state", "established", "sport", "=", ":" + port],
                                    capture_output=True, text=True).stdout.split("\n")
                rss = [l for l in Path("/proc/%s/status" % pid("mem")).read_text().splitlines() if l.startswith("VmRSS")][0].split()[1]
                rate = Path("/proc/%s/cmdline" % pid("disk")).read_bytes().split(b"\0")[5].decode()
                good = {"cpu_pid": pid("cpu"), "writer_pid": pid("disk"), "write_kb_s": rate,
                        "holder_pid": pid("mem"), "holder_rss_kb": rss, "fd_pid": pid("fd"),
                        "fd_count": len(os.listdir("/proc/%s/fd" % pid("fd"))),
                        "listener_pid": pid("net"), "conn_count": len([l for l in ss if l.strip()])}
                (state / "answers.txt").write_text("\n".join("%s=%s" % kv for kv in good.items()) + "\n")
                ok = self._run(script, state, base, "check")
                self.assertEqual(ok.returncode, 0, ok.stderr)
                (state / "answers.txt").write_text(
                    "\n".join("%s=%s" % (k, v if k != "cpu_pid" else pid("tick")) for k, v in good.items()) + "\n")
                self.assertNotEqual(self._run(script, state, base, "check").returncode, 0)
            finally:
                self._run(script, state, base, "reset")
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
