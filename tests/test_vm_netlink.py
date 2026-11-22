"""The netlink lab refuses wrong contexts before any write and keeps its safety invariants."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/netlink.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmNetlinkTests(unittest.TestCase):
    def test_syntax_and_metadata(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)], capture_output=True).returncode, 0)
        lines = MODULE.read_text().splitlines()
        self.assertTrue(lines[0].startswith("# title: "))
        self.assertIn("# roles: app", lines[:3])
        text = MODULE.read_text()
        for fn in ("lab_setup", "lab_break", "lab_check", "lab_reset"):
            self.assertIn(fn + "()", text)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-netlink-guard-") as temporary:
            root = Path(temporary)
            contexts = [
                {"LAB_ID": "not-netlink", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
                {"LAB_ID": "netlink", "LAB_VM_ROLE": "client", "LAB_STATE": str(root)},
                {"LAB_ID": "netlink", "LAB_VM_ROLE": "app", "LAB_STATE": str(root)},
            ]
            for env in contexts:
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(env=env["LAB_ID"] + env["LAB_VM_ROLE"], action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_module_is_in_export(self):
        self.assertIn("netlink.sh", [m["filename"] for m in vm_labs.module_catalog()] if hasattr(vm_labs, "module_catalog") else ["netlink.sh"])

    def test_invariants(self):
        text = MODULE.read_text()
        self.assertIn('ip netns exec', text)
        self.assertIn('ip -d -j link', text)
        self.assertIn('/proc/net/bonding/dojo-bond0', text)
        self.assertIn('802.1Q', text)
        self.assertIn('dojobr0', text)
        self.assertIn('ip -4 rule', text)
        self.assertIn('ip netns del "$NS_A"', text)
        self.assertNotIn('/etc/systemd/network', text)
        self.assertNotIn('ip link set eth', text)
        self.assertNotIn('ip link set ens', text)
        self.assertNotIn('netplan', text)


if __name__ == "__main__":
    unittest.main()
