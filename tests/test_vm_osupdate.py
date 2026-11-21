"""osupdate lab: context guard before any write, plus unprivileged repo/signature building."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs

MODULE = vm_labs.SOURCE / "guest/modules/osupdate.sh"
TOOLS = all(shutil.which(t) for t in ("bash", "gpg", "dpkg-deb", "sha256sum", "gpgv"))


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmOsupdateGuardTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(MODULE)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-osupdate-guard-") as temporary:
            root = Path(temporary)
            for env in ({"LAB_ID": "other", "LAB_VM_ROLE": "app"},
                        {"LAB_ID": "osupdate", "LAB_VM_ROLE": "client"},
                        {"LAB_ID": "osupdate", "LAB_VM_ROLE": "app"}):  # state path is not the real one
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(action=action, env=env):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(MODULE), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_STATE": str(root), **env},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_source_declares_checks_and_forbids_bypass(self):
        text = MODULE.read_text()
        self.assertIn("# roles: app", text)
        for needle in ("FINGERPRINT.txt", "dpkg --audit", "apt-get check", "apt-mark showhold",
                       "trusted|insecure", "allow-unauthenticated", "Signed-By: $_osu_keyring"):
            self.assertIn(needle, text)


@unittest.skipUnless(TOOLS, "gpg, gpgv and dpkg-deb are required")
class VmOsupdateBuildTests(unittest.TestCase):
    def run_bash(self, script, *args):
        return subprocess.run(["bash", "-c", 'set -euo pipefail; source "$1"; shift; ' + script, "t", str(MODULE), *args],
                              capture_output=True, text=True, timeout=60)

    def test_signed_flat_repo_verifies_and_foreign_key_fails(self):
        with tempfile.TemporaryDirectory(prefix="dojo-osupdate-build-") as temporary:
            base = Path(temporary)
            script = ('b=$1; _osu_build "$b"; f=$(_osu_genkey "$b/g1" real); d=$(_osu_genkey "$b/g2" decoy); '
                      '_osu_publish "$b/repo" "$b/debs" "$b/g1" 1.0 2.0; '
                      'gpg --homedir "$b/g1" --batch --export > "$b/real.gpg"; gpg --homedir "$b/g2" --batch --export > "$b/decoy.gpg"; '
                      'gpg --homedir "$b/g1" --batch --armor --export > "$b/real.asc"; echo "$f"; _osu_fprs "$b/real.asc"; _osu_fprs "$b/real.gpg"')
            result = self.run_bash(script, str(base))
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.split()
            self.assertEqual(len(lines[0]), 40)
            self.assertEqual(lines, [lines[0]] * 3)  # armored and binary keyrings report the same fingerprint
            repo = base / "repo"
            self.assertTrue((repo / "InRelease").is_file())
            self.assertFalse((repo / "Release").exists())
            packages = (repo / "Packages").read_text()
            self.assertIn("Depends: dojo-lib (>= 2.0)", packages)
            self.assertIn("Depends: dojo-lib (>= 1.0)", packages)
            good = subprocess.run(["gpgv", "--keyring", str(base / "real.gpg"), str(repo / "InRelease")], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            bad = subprocess.run(["gpgv", "--keyring", str(base / "decoy.gpg"), str(repo / "InRelease")], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            # Republishing 1.0 only drops the 2.0 packages.
            again = self.run_bash('b=$1; _osu_publish "$b/repo" "$b/debs" "$b/g1" 1.0', str(base))
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertNotIn("Version: 2.0", (repo / "Packages").read_text())


if __name__ == "__main__":
    unittest.main()
