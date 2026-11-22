"""GRUB rescue lab rejects wrong contexts before any write, parses grub.cfg correctly and judges real artifacts."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import vm_labs


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class VmGrubRescueTests(unittest.TestCase):
    module = vm_labs.SOURCE / "guest/modules/grubrescue.sh"

    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.module)]).returncode, 0)

    def test_all_actions_reject_wrong_context_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="dojo-grubrescue-guard-") as temporary:
            root = Path(temporary)
            for lab_id, role in (("not-grubrescue", "app"), ("grubrescue", "client")):
                for action in ("setup", "break", "check", "reset"):
                    with self.subTest(lab=lab_id, role=role, action=action):
                        result = subprocess.run(
                            ["bash", "-c", 'set -euo pipefail; source "$1"; "lab_$2"', "guard", str(self.module), action],
                            env={"PATH": "/usr/bin:/bin", "LAB_ID": lab_id, "LAB_VM_ROLE": role, "LAB_STATE": str(root)},
                            capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_state_path_must_match_exactly(self):
        with tempfile.TemporaryDirectory(prefix="dojo-grubrescue-guard-") as temporary:
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; lab_setup', "guard", str(self.module)],
                env={"PATH": "/usr/bin:/bin", "LAB_ID": "grubrescue", "LAB_VM_ROLE": "app", "LAB_STATE": temporary},
                capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected lab context", result.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_cfg_parser_counts_linux_and_initrd_per_entry(self):
        cfg = "menuentry 'A' --class x {\n\tlinux\t/boot/v root=UUID=1 ro\n\tinitrd /boot/i\n}\nmenuentry \"B\" {\n  linux /boot/v root=UUID=1\n}\n"
        with tempfile.TemporaryDirectory(prefix="dojo-grubrescue-parse-") as temporary:
            path = Path(temporary) / "grub.cfg"
            path.write_text(cfg)
            result = subprocess.run(["bash", "-c", 'source "$1"; _gr_entries "$2"', "p", str(self.module), str(path)],
                                    capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("E\tA\t1\t1", result.stdout)
        self.assertIn("E\tB\t1\t0", result.stdout)
        self.assertIn("L\tA\tlinux /boot/v root=UUID=1 ro", result.stdout)

    def test_check_uses_real_artifacts_and_never_touches_real_boot(self):
        text = self.module.read_text()
        for needle in ("losetup -j", "blkid -p", "grub-probe -t fs_uuid", "grub-script-check", "dd if=\"$loop\"",
                       "core.img", "grub-install", "BEGIN /etc/grub.d/10_linux", "host-cfg.sha256", "unshare -m"):
            self.assertIn(needle, text)
        # grub-install must only ever name the lab loop device in the learner text, never a real disk
        self.assertNotIn("--boot-directory=/boot", text)

    def test_keyword_set_covers_rescue_topics(self):
        text = self.module.read_text()
        for needle in ("init=/bin/bash", "systemd\\.unit=rescue\\.target", "rd\\.break", "/sysroot", "autorelabel", "chroot"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
