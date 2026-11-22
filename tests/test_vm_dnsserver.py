"""Dedicated BIND lab: wrong contexts rejected before writes; missing bind9 gives install hint; static safety."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/dnsserver.sh"


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmDnsserverTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-dns-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env_id, role in (("not-dnsserver", "app"), ("dnsserver", "client")):
                    with self.subTest(action=action, lab=env_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": env_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_missing_bind_prints_install_instruction(self):
        with tempfile.TemporaryDirectory(prefix="dojo-dns-nobind-") as empty:
            result = subprocess.run([shutil.which("bash"), "-c", 'source "$1"; _dns_need_bind', "x", str(MODULE)],
                                    env={"PATH": empty}, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo apt-get install -y bind9 bind9-utils dnsutils", result.stderr)

    def test_broken_content_and_good_content_differ_as_designed(self):
        script = 'source "$1"; DNS_FWD=f; DNS_REV=r; DNS_ZDIR=z; DNS_KEY=k; DNS_RNDC=1; DNS_PORT=2; %s'
        run = lambda body: subprocess.run(["bash", "-c", script % body, "x", str(MODULE)],
                                          capture_output=True, text=True, timeout=5, env={"PATH": "/usr/bin:/bin"}).stdout
        broken = run("_dns_broken_fwd")
        self.assertIn("IN CNAME www\n", broken.split("ns1 IN A")[0])  # apex CNAME
        self.assertIn("mail.lab.invalid\n", broken)                  # missing trailing dot
        self.assertIn("2024010101", broken)                          # stale serial
        self.assertIn("allow-transfer { any; }", run("_dns_conf any"))
        self.assertIn("allow-transfer { 127.0.0.1; }", run("_dns_conf 127.0.0.1"))

    def test_module_stays_on_dedicated_instance(self):
        text = MODULE.read_text()
        for needle in ("/etc/bind/named.conf", "systemctl restart named", "systemctl stop named"):
            self.assertNotIn(needle, text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("5354", text)


if __name__ == "__main__":
    unittest.main()
