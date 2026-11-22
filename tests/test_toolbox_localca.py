"""Real localca lab: solution passes on fresh fixtures; wrong, partial and tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import curriculum.toolbox_labs3  # noqa: F401  registers the lab
from curriculum.toolbox_labs import LABS

LAB = LABS["localca"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", script], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=240)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class LocalCaLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-localca-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        LAB["setup"](root)
        return root

    def solved(self, script=None):
        root = self.fresh()
        result = sh(root, script or LAB["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return root

    def rejected(self, script):
        root = self.fresh()
        sh(root, script)
        with self.assertRaises(BAD):
            LAB["check"](root)

    def test_solution_passes_with_fresh_fixtures(self):
        for _ in range(2):
            root = self.fresh()
            with self.assertRaises(BAD):
                LAB["check"](root)
            sh(root, LAB["solution"])
            LAB["check"](root)

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                self.rejected(wrong)

    def variant(self, old, new):
        self.assertIn(old, LAB["solution"])
        self.rejected(LAB["solution"].replace(old, new, 1))

    def tamper(self, mutate):
        root = self.solved()
        LAB["check"](root)
        mutate(root)
        with self.assertRaises(BAD):
            LAB["check"](root)

    def test_tampering_rejected(self):
        cases = {
            "key mode": lambda r: (r / "server.key").chmod(0o644),
            "handshake faked": lambda r: (r / "handshake.txt").write_text("nothing"),
            "crl removed": lambda r: (r / "ca.crl").write_text(""),
            "cert swapped for self-signed": lambda r: subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "9",
                 "-keyout", "server.key", "-out", "server.crt", "-subj", "/CN=x"], cwd=r, capture_output=True),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.tamper(mutate)

    def test_issuance_mistakes_rejected(self):
        self.variant("subjectAltName=DNS:%s", "subjectAltName=DNS:wrong.corp.test%.0s")      # wrong SAN name
        self.variant("extendedKeyUsage=serverAuth", "extendedKeyUsage=clientAuth")           # wrong key usage
        self.variant("\nsubjectAltName=DNS:%s\n' \"$name\"", "\n'")                          # no SAN at all
        self.variant("-startdate 20200101000000Z -enddate 20200102000000Z", "-days 30")     # not expired
        self.variant("openssl ca -batch -config ca.cnf -revoke revoked.crt", "true")        # never revoked
        self.variant("-extensions ca_ext", "")                                              # CA without CA:TRUE


if __name__ == "__main__":
    unittest.main()
