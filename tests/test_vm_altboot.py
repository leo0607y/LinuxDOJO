"""Dedicated altboot lab: guards reject wrong context before any write; offline helper logic is exercised."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/altboot.sh"
BASH = shutil.which("bash")


def run_bash(script, *args, env=None):
    return subprocess.run([BASH, "-c", script, "t", str(MODULE), *args], env=env or {"PATH": "/nonexistent"},
                          capture_output=True, text=True, timeout=20)


@unittest.skipUnless(BASH, "Bash is required")
class VmAltbootTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run([BASH, "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-altboot-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for ident, role in (("not-altboot", "app"), ("altboot", "client")):
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
        result = run_bash('set -u; source "$1"; _ab_paths; _ab_tools',
                          env={"PATH": "/nonexistent", "LAB_ID": "altboot", "LAB_VM_ROLE": "app",
                               "LAB_STATE": "/var/lib/linuxdojo-vm-lab/state/altboot"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt-get install -y extlinux syslinux-common pxelinux dnsmasq", result.stdout)

    def cfgcheck(self, files, cfg, *extra):
        with tempfile.TemporaryDirectory(prefix="dojo-altboot-cfg-") as temporary:
            root = Path(temporary)
            state = root / "state"; state.mkdir()
            self.assertEqual(run_bash('LAB_STATE="$2"; source "$1"; _ab_write_helpers', str(state), env={"PATH": "/usr/bin:/bin"}).returncode, 0)
            boot = root / "boot"; boot.mkdir()
            for name in files:
                (boot / name).write_bytes(b"x")
            (boot / "cfg").write_text(cfg)
            return subprocess.run([sys.executable, str(state / "cfgcheck.py"), str(boot / "cfg"), str(boot), str(boot), *extra],
                                  capture_output=True, text=True)

    GOOD = "DEFAULT a\nTIMEOUT 50\nLABEL a\n  KERNEL vmlinuz\n  APPEND initrd=initrd.img ro\nLABEL b\n  LOCALBOOT 0\n"

    def test_config_validator_accepts_good_and_rejects_broken(self):
        self.assertEqual(self.cfgcheck(["vmlinuz", "initrd.img"], self.GOOD).returncode, 0)
        cases = {
            "default missing label": self.GOOD.replace("DEFAULT a", "DEFAULT zzz"),
            "bad timeout": self.GOOD.replace("50", "abc"),
            "label without kernel": self.GOOD.replace("  KERNEL vmlinuz\n", ""),
            "unknown keyword": self.GOOD + "BOGUS 1\n",
            "single label": "DEFAULT a\nTIMEOUT 5\nLABEL a\n  KERNEL vmlinuz\n",
        }
        for name, cfg in cases.items():
            with self.subTest(name):
                self.assertEqual(self.cfgcheck(["vmlinuz", "initrd.img"], cfg).returncode, 1)
        self.assertEqual(self.cfgcheck(["vmlinuz"], self.GOOD).returncode, 1)  # initrd missing
        self.assertEqual(self.cfgcheck(["vmlinuz", "initrd.img"], self.GOOD, "--need", "ldlinux.c32").returncode, 1)

    def test_pxe_probe_and_knowledge_check_present(self):
        text = MODULE.read_text()
        for needle in ("SO_BINDTODEVICE", "0x8000", "opts.get(66", "opts.get(67", "rrq(name)", "efibootmgr", "KNOWLEDGE CHECK"):
            self.assertIn(needle, text)
        compile_ok = subprocess.run([sys.executable, "-c", "import ast,re,sys;s=open(sys.argv[1]).read();[ast.parse(m) for m in re.findall(r\"<<'PY'\\n(.*?)\\nPY\\n\", s, re.S)]", str(MODULE)])
        self.assertEqual(compile_ok.returncode, 0)


if __name__ == "__main__":
    unittest.main()
