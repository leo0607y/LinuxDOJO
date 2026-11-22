"""Real tcpdump lab: solution passes, wrong or tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS

LAB = LABS["tcpdump"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class TcpdumpLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-tcpdump-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        LAB["setup"](root)
        return root

    def solved(self):
        root = self.fresh()
        with self.assertRaises(BAD):
            LAB["check"](root)
        result = sh(root, LAB["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        LAB["check"](root)
        return root

    def test_solution_passes_with_fresh_fixtures(self):
        self.solved()
        self.solved()

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                root = self.fresh()
                sh(root, wrong)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_tampering_rejected(self):
        mutations = {
            "pcap replaced": lambda r: (r / "web.pcap").write_bytes((r / "traffic.pcap").read_bytes()),
            "pcap not pcap": lambda r: (r / "web.pcap").write_text("text"),
            "request edited": lambda r: (r / "request-line.txt").write_text("GET /x HTTP/1.1\n"),
            "count off": lambda r: (r / "new-conns.txt").write_text("99\n"),
            "first3 too long": lambda r: (r / "first3.txt").write_text((r / "first3.txt").read_text() * 2),
            "source pcap changed": lambda r: (r / "traffic.pcap").write_bytes((r / "traffic.pcap").read_bytes()[:-5]),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_fixture_is_valid_pcap_with_real_parsing(self):
        root = self.fresh()
        out = subprocess.run(["tcpdump", "-nn", "-v", "-r", "traffic.pcap"], cwd=root,
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("bad cksum", out.stdout)
        self.assertIn("HTTP", subprocess.run(["tcpdump", "-nn", "-A", "-r", "traffic.pcap"], cwd=root,
                                             capture_output=True, text=True).stdout)

    def test_capture_privilege_variant_is_documented(self):
        self.assertIn("CAP_NET_RAW", LAB["task"])


if __name__ == "__main__":
    unittest.main()
