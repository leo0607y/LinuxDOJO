"""Dedicated sshd hardening lab rejects wrong contexts before writes; policy checker is strict."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/sshd.sh"

GOOD = """passwordauthentication no
kbdinteractiveauthentication no
permitrootlogin no
permitemptypasswords no
pubkeyauthentication yes
maxauthtries 3
allowusers dojo-hard
allowusers dojo-hop
port 22223
listenaddress 127.0.0.1:22223
hostkey /etc/dojo-sshd/hostkey
authorizedkeysfile /etc/dojo-sshd/keys/%u
strictmodes yes
"""


def policy(text):
    with tempfile.TemporaryDirectory(prefix="dojo-sshd-policy-") as tmp:
        eff = Path(tmp) / "eff.txt"
        eff.write_text(text)
        script = ('set -euo pipefail; source "$1"; SD_DIR=/etc/dojo-sshd; SD_PORT=22223; '
                  '_sshd_policy "$2" dojo-hard')
        return subprocess.run(["bash", "-c", script, "x", str(MODULE), str(eff)],
                              env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)


@unittest.skipUnless(shutil.which("bash") and shutil.which("python3"), "Bash and Python are required")
class VmSshdTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-sshd-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env_id, role in (("not-sshd", "app"), ("sshd", "client")):
                    with self.subTest(action=action, lab=env_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": env_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_policy_accepts_hardened_values(self):
        self.assertEqual(policy(GOOD).returncode, 0)

    def test_policy_rejects_each_weakness_or_lockout(self):
        weak = {
            "password": GOOD.replace("passwordauthentication no", "passwordauthentication yes"),
            "kbd": GOOD.replace("kbdinteractiveauthentication no", "kbdinteractiveauthentication yes"),
            "root": GOOD.replace("permitrootlogin no", "permitrootlogin yes"),
            "tries": GOOD.replace("maxauthtries 3", "maxauthtries 6"),
            "pubkey_off": GOOD.replace("pubkeyauthentication yes", "pubkeyauthentication no"),
            "no_allowusers": GOOD.replace("allowusers dojo-hard\nallowusers dojo-hop\n", ""),
            "allowusers_wide": GOOD + "allowusers ubuntu\n",
            "allowusers_locked": GOOD.replace("allowusers dojo-hard\n", ""),
            "port": GOOD.replace("22223", "22"),
            "empty_pw": GOOD.replace("permitemptypasswords no", "permitemptypasswords yes"),
        }
        for name, text in weak.items():
            with self.subTest(name=name):
                self.assertNotEqual(policy(text).returncode, 0)

    def test_module_never_touches_system_sshd_or_root_home(self):
        text = MODULE.read_text()
        import re
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        for pattern in (r"/etc/ssh/", r"(?<![-\w])sshd?\.service", r"/root/\.ssh"):
            self.assertIsNone(re.search(pattern, code), pattern)
        self.assertIn("-f $LAB_STATE/fault", code)

    def test_export_contains_module(self):
        with tempfile.TemporaryDirectory(prefix="dojo-sshd-export-") as temporary:
            bundle = vm_labs.export_bundle(Path(temporary) / "bundle")
            self.assertEqual((bundle / "guest/modules/sshd.sh").read_bytes(), MODULE.read_bytes())


if __name__ == "__main__":
    unittest.main()
