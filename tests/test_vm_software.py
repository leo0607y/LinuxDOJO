"""Exercise actual deb conffile semantics in an unprivileged private dpkg root.

These tests do not install host packages, run systemd, or claim VM runtime validation.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "labs/vm/guest/modules"


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=20, **kwargs)


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmSoftwareGuards(unittest.TestCase):
    def test_every_action_rejects_non_vm_context_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="dojo-vm-guard-") as folder:
            for module in ("packages", "software"):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(module=module, action=action):
                        result = run(["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"',
                                      "guard", str(MODULES / (module + ".sh")), action],
                                     env={"PATH": os.environ["PATH"], "LAB_ID": module,
                                          "LAB_VM_ROLE": "app", "LAB_STATE": folder})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_both_guest_modules_have_valid_bash_syntax(self):
        for module in ("packages", "software"):
            result = run(["bash", "-n", str(MODULES / (module + ".sh"))])
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(all(shutil.which(name) for name in ("bash", "dpkg", "dpkg-deb", "dpkg-query")),
                     "Actual Debian package tools required")
class RealPackageLifecycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dojo-private-dpkg-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.build = self.base / "builder"
        self.build.mkdir()
        result = run(["bash", "-c", 'set -euo pipefail; source "$1"; _packages_build "$2"',
                      "builder", str(MODULES / "packages.sh"), str(self.build)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.root = self.base / "root"
        admin = self.root / "var/lib/dpkg"
        admin.mkdir(parents=True)
        (admin / "status").touch()

    def dpkg(self, *args):
        # Every mutable dpkg path, including the log, is inside the temporary root.
        result = run(["dpkg", "--root=" + str(self.root), "--log=" + str(self.base / "dpkg.log"),
                      "--force-not-root", "--force-bad-path", "--force-depends", *args])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def archive(self, version):
        return str(self.build / "debs" / ("dojo-example_" + version + "_all.deb"))

    def status(self):
        return run(["dpkg-query", "--admindir=" + str(self.root / "var/lib/dpkg"),
                    "-W", "-f=${Status}|${Version}", "dojo-example"])

    def cli(self):
        return run([sys.executable, str(self.root / "usr/bin/dojo-example"),
                    "--config", str(self.root / "etc/dojo-example.conf")])

    def test_install_configure_upgrade_fault_repair_remove_and_purge_real_deb(self):
        self.dpkg("--install", self.archive("1.0"))
        self.assertEqual(self.status().stdout, "install ok installed|1.0")
        self.assertEqual(self.cli().stdout, "version=1.0 message=hello\n")
        config = self.root / "etc/dojo-example.conf"
        config.write_text("message=retained_" + self.base.name.replace("-", "_") + "\n")
        original = config.read_text()
        self.dpkg("--force-confold", "--install", self.archive("2.0"))
        self.assertEqual(self.status().stdout, "install ok installed|2.0")
        self.assertEqual(config.read_text(), original)
        self.assertEqual(self.cli().stdout, "version=2.0 " + original)
        config.write_text("message has invalid syntax\n")
        broken = self.cli()
        self.assertEqual(broken.returncode, 2)
        self.assertIn("configuration error:", broken.stderr)
        config.write_text(original)
        self.assertEqual(self.cli().returncode, 0)
        self.dpkg("--remove", "dojo-example")
        self.assertEqual(self.status().stdout, "deinstall ok config-files|2.0")
        self.assertFalse((self.root / "usr/bin/dojo-example").exists())
        self.assertEqual(config.read_text(), original)
        self.dpkg("--purge", "dojo-example")
        self.assertFalse(config.exists())
        self.assertNotEqual(self.status().returncode, 0)

    def test_package_contents_and_conffiles_are_real_and_owned_by_root(self):
        for version, default in (("1.0", "hello"), ("2.0", "welcome")):
            result = run(["dpkg-deb", "-f", self.archive(version), "Package", "Version", "Depends"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Package: dojo-example", result.stdout)
            self.assertIn("Version: " + version, result.stdout)
            self.assertIn("Depends: python3", result.stdout)
            result = run(["dpkg-deb", "-I", self.archive(version), "conffiles"])
            self.assertEqual(result.stdout, "/etc/dojo-example.conf\n")
            contents = run(["dpkg-deb", "-c", self.archive(version)])
            self.assertIn("root/root", contents.stdout)
            self.assertEqual((self.build / "build" / version / "etc/dojo-example.conf").read_text(),
                             "message=" + default + "\n")

    def test_builder_refuses_to_replace_existing_builds(self):
        result = run(["bash", "-c", 'set -euo pipefail; source "$1"; _packages_build "$2"',
                      "builder", str(MODULES / "packages.sh"), str(self.build)])
        self.assertNotEqual(result.returncode, 0)


@unittest.skipUnless(shutil.which("bash"), "Bash required to generate job")
class RealSoftwareJobTests(unittest.TestCase):
    def test_generated_job_writes_live_report_and_rejects_broken_configuration(self):
        with tempfile.TemporaryDirectory(prefix="dojo-report-job-") as folder:
            base = Path(folder)
            job = base / "job.py"
            result = run(["bash", "-c", 'set -euo pipefail; source "$1"; _software_write_job "$2"',
                          "builder", str(MODULES / "software.sh"), str(job)])
            self.assertEqual(result.returncode, 0, result.stderr)
            config = base / "config"
            config.write_text("message=test_report\n")
            env = dict(os.environ, STATE_DIRECTORY=folder)
            result = run([sys.executable, str(job), str(config)], env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((base / "report.json").read_text())
            self.assertEqual(report["message"], "test_report")
            self.assertEqual(report["uid"], os.getuid())
            self.assertGreater(report["timestamp_ns"], 0)
            self.assertIn("dojo-report-success test_report", result.stdout)
            config.write_text("message broken syntax\n")
            result = run([sys.executable, str(job), str(config)], env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("dojo-report-configuration-error:", result.stderr)
            self.assertEqual(json.loads((base / "report.json").read_text()), report)


if __name__ == "__main__":
    unittest.main()
