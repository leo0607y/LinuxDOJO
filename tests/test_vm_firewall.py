"""Firewall lab refuses wrong contexts before any write and keeps to its own nft table."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/firewall.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmFirewallTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-fw-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env in ({"LAB_ID": "not-firewall", "LAB_VM_ROLE": "app"},
                            {"LAB_ID": "firewall", "LAB_VM_ROLE": "client"}):
                    with self.subTest(action=action, env=env):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_STATE": str(root), **env},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_static_scope_and_requirements(self):
        text = MODULE.read_text()
        for needle in ("inet dojo_fw", "--on-active=90s", "nft -c -f", "policy drop", "broken", "dojo-fw-peer"):
            self.assertIn(needle, text)
        for forbidden in ("nft flush ruleset", "ufw disable", "ufw reset"):
            self.assertNotIn(forbidden, text)

    def test_module_is_exported(self):
        with tempfile.TemporaryDirectory(prefix="dojo-fw-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            self.assertEqual((bundle / "guest/modules/firewall.sh").read_bytes(), MODULE.read_bytes())


if __name__ == "__main__":
    unittest.main()
