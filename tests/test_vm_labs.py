"""VM bundles are inert on the host; provisioning content round-trips correctly."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


class VmLabExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="linuxdojo-vm-export-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        (self.source / "guest/modules").mkdir(parents=True)
        for name in ("README.md", "cloud-init.yaml.in"):
            shutil.copyfile(vm_labs.SOURCE / name, self.source / name)
        shutil.copyfile(vm_labs.SOURCE / "guest/dojo-vm-lab", self.source / "guest/dojo-vm-lab")
        self.module = "# title: Test lab\nlab_setup() { :; }\nlab_break() { :; }\nlab_check() { :; }\nlab_reset() { :; }\n"
        (self.source / "guest/modules/test-lab.sh").write_text(self.module)

    def decoded_files(self, rendered):
        entries = {}
        destination = None
        for line in rendered.splitlines():
            if line.startswith("  - path: "):
                destination = json.loads(line[len("  - path: "):])
            if line.startswith("    content: "):
                entries[destination] = base64.b64decode(json.loads(line[len("    content: "):]), validate=True)
        return entries

    def test_role_specific_cloud_init_round_trips_scripts_as_data(self):
        for role in ("app", "client"):
            rendered = vm_labs.render_cloud_init(role, self.source)
            self.assertTrue(rendered.startswith("#cloud-config\n"))
            self.assertNotIn("@@", rendered)
            entries = self.decoded_files(rendered)
            self.assertEqual(entries["/etc/linuxdojo-vm-lab"],
                             f"format=linuxdojo-vm-v1\nrole={role}\nhostname=linuxdojo-{role}\n".encode())
            self.assertEqual(entries["/usr/local/lib/linuxdojo-vm-lab/modules/test-lab.sh"].decode(), self.module)
            self.assertEqual(entries["/usr/local/sbin/dojo-vm-lab"], (self.source / "guest/dojo-vm-lab").read_bytes())
            self.assertIn("    permissions: \"0600\"", rendered)

    def test_export_never_executes_host_or_guest_commands(self):
        with patch("subprocess.run", side_effect=AssertionError("host command")), \
             patch("subprocess.Popen", side_effect=AssertionError("host process")):
            output = vm_labs.export_bundle(self.base / "bundle", self.source)
        self.assertEqual(json.loads((output / "manifest.json").read_text())["modules"][0]["id"], "test-lab")
        self.assertTrue((output / "app-cloud-init.yaml").is_file())
        self.assertTrue((output / "client-cloud-init.yaml").is_file())
        self.assertTrue((output / "SHA256SUMS.json").is_file())

    def test_existing_export_and_symlink_destination_are_never_overwritten(self):
        output = self.base / "existing"
        output.mkdir()
        (output / "keep").write_text("keep")
        with self.assertRaises(ValueError):
            vm_labs.export_bundle(output, self.source)
        self.assertEqual((output / "keep").read_text(), "keep")
        (self.base / "link").symlink_to(output)
        with self.assertRaises(ValueError):
            vm_labs.export_bundle(self.base / "link", self.source)

    def test_invalid_or_linked_modules_are_rejected(self):
        target = self.source / "guest/modules/test-lab.sh"
        target.unlink()
        target.symlink_to(self.base / "outside")
        with self.assertRaises(ValueError):
            vm_labs.lab_catalog(self.source)
        target.unlink()
        (self.source / "guest/modules/bad name.sh").write_text(self.module)
        with self.assertRaises(ValueError):
            vm_labs.lab_catalog(self.source)

    def test_empty_course_cannot_be_exported_as_a_working_bundle(self):
        (self.source / "guest/modules/test-lab.sh").unlink()
        with self.assertRaises(ValueError):
            vm_labs.export_bundle(self.base / "empty", self.source)
        self.assertFalse((self.base / "empty").exists())

    @unittest.skipUnless(shutil.which("bash"), "bash syntax check requires Bash")
    def test_guest_dispatcher_and_available_modules_have_valid_bash_syntax(self):
        paths = [vm_labs.SOURCE / "guest/dojo-vm-lab", *sorted((vm_labs.SOURCE / "guest/modules").glob("*.sh"))]
        for path in paths:
            with self.subTest(path=path.name):
                result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("bash"), "guard check requires Bash")
    def test_guest_dispatcher_refuses_this_unprovisioned_host(self):
        if Path("/etc/linuxdojo-vm-lab").exists():
            self.skipTest("this machine has been explicitly provisioned as a LinuxDOJO lab")
        result = subprocess.run(["bash", str(vm_labs.SOURCE / "guest/dojo-vm-lab"), "test-lab", "setup"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("LinuxDOJO VM:", result.stderr)

    @unittest.skipUnless(shutil.which("bash"), "module guard checks require Bash")
    def test_web_and_network_actions_reject_an_invalid_lab_context(self):
        for name in ("webstack", "network"):
            path = vm_labs.SOURCE / "guest/modules" / (name + ".sh")
            for action in ("setup", "break", "check", "reset"):
                with self.subTest(module=name, action=action):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(path), action],
                        env={"PATH": "/usr/bin:/bin", "LAB_ID": "unexpected", "LAB_VM_ROLE": "app",
                             "LAB_ROOT": str(self.base), "LAB_STATE": str(self.base / "state")},
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "state").exists())


if __name__ == "__main__":
    unittest.main()
