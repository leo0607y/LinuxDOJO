"""Security assessment checks reject plausible-but-unsafe host remediation."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import runner
from engine.security_checks import archive_texts, service_values, ssh_values
import curriculum.stage9_host_security  # noqa: F401


class HostSecurityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="linuxdojo-security-host-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (("WORKSPACE", self.root / "workspace"), ("STATE", self.root / "workspace/.lq_state")):
            guard = patch.object(runner, name, value)
            guard.start()
            self.addCleanup(guard.stop)

    def prepare(self, number):
        mission = runner.get_mission("9-" + str(number))
        return mission, runner.prepare(mission, runner.new_token())

    def solve(self, mission, ctx):
        script = mission.render(mission.solution, ctx.data)
        result = subprocess.run(["bash", "-c", script], cwd=ctx.work, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        good, message = runner.run_check(mission, ctx.token)
        self.assertTrue(good, message)

    def test_ssh_first_value_cannot_be_overridden_by_append(self):
        self.assertEqual(ssh_values("PermitRootLogin yes\npermitrootlogin no\n")["permitrootlogin"], "yes")
        with self.assertRaises(ValueError):
            ssh_values("PermitRootLogin no\nMatch User root\n PermitRootLogin yes\n")

    def test_service_directives_must_be_in_service_section(self):
        values = service_values("[Service]\nUser=root\n[Install]\nUser=dojo-app\n")
        self.assertEqual(values["User"], "root")
        with self.assertRaises(ValueError):
            service_values("[Service]\nExecStart=/bin/true\nExecStart=/bin/false\n")

    def test_archive_alias_duplicates_and_traversal_are_rejected_without_extracting(self):
        target = self.root / "bundle.tar"
        for names in (("file", "./file"), ("../escape",)):
            with self.subTest(names=names):
                with tarfile.open(target, "w") as archive:
                    for name in names:
                        info = tarfile.TarInfo(name)
                        info.size = 1
                        archive.addfile(info, io.BytesIO(b"x"))
                with self.assertRaises(ValueError):
                    archive_texts(target)
        self.assertFalse((self.root / "escape").exists())

    def test_correct_report_does_not_hide_secret_in_archive(self):
        mission, ctx = self.prepare(6)
        self.solve(mission, ctx)
        with tarfile.open(ctx.p("bundle.tar.gz"), "w:gz") as archive:
            archive.add(ctx.p("release"), arcname="release")
        self.assertFalse(runner.run_check(mission, ctx.token)[0])

    def test_expected_hash_cannot_be_replaced_to_bless_wrong_restore(self):
        mission, ctx = self.prepare(7)
        self.solve(mission, ctx)
        ctx.p("approved.sha256").write_text("0" * 64 + "  backup/app.conf\n")
        self.assertFalse(runner.run_check(mission, ctx.token)[0])

    def test_scope_authorization_cannot_be_rewritten(self):
        mission, ctx = self.prepare(1)
        self.solve(mission, ctx)
        authorization = json.loads(ctx.p("engagement.json").read_text())
        authorization["allowed_assets"].append("production.example.invalid")
        ctx.p("engagement.json").write_text(json.dumps(authorization))
        self.assertFalse(runner.run_check(mission, ctx.token)[0])

    def test_all_seven_initial_states_and_solutions(self):
        for number in range(1, 8):
            with self.subTest(mission=number):
                mission, ctx = self.prepare(number)
                self.assertFalse(runner.run_check(mission, ctx.token)[0])
                self.solve(mission, ctx)


if __name__ == "__main__":
    unittest.main()
