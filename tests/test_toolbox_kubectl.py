"""Real kubectl lab: solution passes on fresh fixtures; wrong, partial and tampered outcomes fail."""
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

LAB = LABS["kubectl"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", script], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=240)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class KubectlLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-kubectl-")
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
            "image latest": lambda r: (r / "base/deployment.yaml").write_text(
                (r / "base/deployment.yaml").read_text().replace(":" + __import__("re").search(r"TAG=(.*)", (r / "spec.env").read_text()).group(1), ":latest")),
            "overlay removed": lambda r: (r / "overlays/prod/kustomization.yaml").write_text("resources: [../../base]\n"),
            "spec changed": lambda r: (r / "spec.env").write_text("APP=x\n"),
            "service file missing": lambda r: (r / "base/service.yaml").unlink(),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.tamper(mutate)

    def test_manifest_mistakes_rejected(self):
        self.variant("image: $IMAGE:$TAG", "image: $IMAGE:latest")
        self.variant("  selector: {app: $APP}\n  ports:", "  selector: {app: other}\n  ports:")
        self.variant("matchLabels: {app: $APP}", "matchLabels: {app: nope}")
        self.variant("          readinessProbe:\n            httpGet: {path: $HEALTH, port: http}\n", "")
        self.variant("            limits: {cpu: 500m, memory: 128Mi}\n", "")
        self.variant("replicas:\n  - {name: $APP, count: $PROD_REPLICAS}\n", "")
        self.variant("namePrefix: prod-\n", "")
        self.variant("envFrom:\n            - configMapRef: {name: $APP-config}\n", "")


if __name__ == "__main__":
    unittest.main()
