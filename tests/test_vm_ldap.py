"""Dedicated slapd lab: wrong contexts rejected before writes; DIT validator rejects wrong trees; static safety."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/ldap.sh"
BASE = "dc=dojo,dc=test"


def good_ldif():
    out = [f"dn: {BASE}\nobjectClass: top\nobjectClass: dcObject\nobjectClass: organization\ndc: dojo\no: Dojo\n",
           f"dn: ou=people,{BASE}\nobjectClass: organizationalUnit\nou: people\n",
           f"dn: ou=groups,{BASE}\nobjectClass: organizationalUnit\nou: groups\n"]
    for i, u in enumerate(("alice", "bob", "carol")):
        out.append(f"dn: uid={u},ou=people,{BASE}\nobjectClass: inetOrgPerson\nobjectClass: posixAccount\n"
                   f"uid: {u}\ncn: {u}\nsn: {u}\nuidNumber: {10001 + i}\ngidNumber: 10000\n"
                   f"homeDirectory: /home/{u}\nloginShell: /bin/bash\nuserPassword:: e1NTSEF9eHh4\n")
    out.append(f"dn: cn=staff,ou=groups,{BASE}\nobjectClass: posixGroup\ncn: staff\ngidNumber: 10000\n"
               "memberUid: alice\nmemberUid: bob\nmemberUid: carol\n")
    return "\n".join(out)


@unittest.skipUnless(shutil.which("bash") and shutil.which("python3"), "Bash and python3 are required")
class VmLdapTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-ldap-guard-") as temporary:
            root = Path(temporary)
            for action in ("setup", "break", "check", "reset"):
                for env_id, role in (("not-ldap", "app"), ("ldap", "client")):
                    with self.subTest(action=action, lab=env_id, role=role):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": env_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def validate(self, text):
        with tempfile.TemporaryDirectory(prefix="dojo-ldap-dit-") as temporary:
            path = Path(temporary) / "dit.ldif"
            path.write_text(text)
            return subprocess.run(["bash", "-c", 'source "$1"; _ldap_dit_validate "$2"', "v", str(MODULE), str(path)],
                                  capture_output=True, text=True, timeout=10)

    def test_dit_validator_accepts_expected_tree(self):
        result = self.validate(good_ldif())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dit_validator_rejects_wrong_trees(self):
        good = good_ldif()
        cases = {
            "missing user": good.replace("uid=carol", "uid=dave"),
            "not posixAccount": good.replace("objectClass: posixAccount\nuid: bob", "uid: bob"),
            "duplicate uidNumber": good.replace("uidNumber: 10002", "uidNumber: 10001"),
            "low uidNumber": good.replace("uidNumber: 10003", "uidNumber: 5"),
            "group members": good.replace("memberUid: carol\n", ""),
            "no group": good.replace("posixGroup", "groupOfNames"),
            "extra entry": good + f"\ndn: ou=extra,{BASE}\nobjectClass: organizationalUnit\nou: extra\n",
            "relative home": good.replace("/home/alice", "home/alice"),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertNotEqual(self.validate(text).returncode, 0)

    def test_static_isolation_and_checks(self):
        text = MODULE.read_text()
        self.assertIn("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y slapd ldap-utils", text)
        self.assertIn("ldap://127.0.0.1:3890", text)
        for forbidden in ("slapd.service", "/etc/ldap/slapd.d", "nsswitch.conf <", "pam.d", "ldap://0.0.0.0", "ldap://:389/"):
            self.assertNotIn(forbidden, text)
        for needed in ("-F \"$LDAP_CONF\"", "rc == 49", "slapcat", "userdel \"$LDAP_USER\"", "linuxdojo-ldap"):
            self.assertIn(needed, text)


if __name__ == "__main__":
    unittest.main()
