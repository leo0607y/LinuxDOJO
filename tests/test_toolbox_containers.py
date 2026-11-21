"""Docker resource scope tests plus an explicitly gated real-daemon lifecycle test.

Without a real daemon this module reports an integration skip, never a simulated PASS.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curriculum import toolbox_containers as labs


def available():
    try:
        labs.local_context()
        return bool(labs.docker("info", "--format", "{{.ServerVersion}}", timeout=10).strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


class DockerScopeTests(unittest.TestCase):
    def test_mock_cli_is_rejected_before_executing_anything(self):
        with patch.object(labs.shutil, "which", return_value="/training/bin/mock/docker"), \
             patch.object(labs.subprocess, "run", side_effect=AssertionError("must not run mock")):
            with self.assertRaisesRegex(ValueError, "本物"):
                labs.docker("info")

    def test_setup_only_probes_daemon_and_creates_local_exercise_files(self):
        with tempfile.TemporaryDirectory(prefix="dojo-container-scope-") as temporary:
            root = Path(temporary)
            with patch.object(labs, "local_context", return_value="unix:///var/run/docker.sock"), \
                 patch.object(labs, "docker", return_value="27.0.0\n") as command:
                labs.setup(root)
            command.assert_called_once_with("info", "--format", "{{.ServerVersion}}")
            data = labs.state(root)
            self.assertIn("USER 10001:10001", (root / "Dockerfile").read_text())
            self.assertIn("!server.py", (root / ".dockerignore").read_text())
            self.assertNotIn("name", data["token"])
            self.assertTrue(data["name"].startswith("dojo-"))

    def test_unrelated_resource_label_is_rejected(self):
        with patch.object(labs, "inspect", return_value={"Config": {"Labels": {labs.LABEL: "someone-else"}}}):
            with self.assertRaisesRegex(ValueError, "ラベル"):
                labs.owned("container", "dojo-1234", "1234")

    def test_cleanup_refuses_to_delete_a_same_named_foreign_container(self):
        with tempfile.TemporaryDirectory(prefix="dojo-container-cleanup-") as temporary:
            root = Path(temporary)
            with patch.object(labs, "local_context", return_value="unix:///var/run/docker.sock"), \
                 patch.object(labs, "docker", return_value="27\n"):
                labs.setup(root)
            foreign = {"Config": {"Labels": {labs.LABEL: "different-course"}}}
            probe = subprocess.CompletedProcess([], 0, "[]", "")
            with patch.object(labs.shutil, "which", return_value="/usr/bin/docker"), \
                 patch.object(labs.subprocess, "run", return_value=probe), \
                 patch.object(labs, "inspect", return_value=foreign), \
                 patch.object(labs, "local_context", return_value="unix:///var/run/docker.sock"), \
                 patch.object(labs, "docker") as command:
                with self.assertRaisesRegex(ValueError, "ラベル"):
                    labs.cleanup(root)
                command.assert_called_once_with("info", "--format", "{{.ServerVersion}}")

    def test_remote_host_is_rejected_before_setup_creates_files(self):
        for host in ("tcp://example.invalid:2376", "ssh://example.invalid", "npipe:////./pipe/docker_engine"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with patch.dict(os.environ, {"DOCKER_HOST": host}, clear=True), \
                     patch.object(labs.subprocess, "run", side_effect=AssertionError("remote command")):
                    with self.assertRaisesRegex(ValueError, "遠隔"):
                        labs.setup(root)
                self.assertEqual(list(root.iterdir()), [])

    def test_remote_context_overrides_unix_host_and_is_rejected(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CONTEXT": "remote"}, clear=True), \
             patch.object(labs, "docker", return_value="ssh://example.invalid\n") as command:
            with self.assertRaisesRegex(ValueError, "遠隔"):
                labs.local_context()
            command.assert_called_once_with("context", "inspect", "--format", "{{.Endpoints.docker.Host}}")

    def test_cleanup_refuses_remote_endpoint_and_mock_cli_before_any_daemon_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(labs, "local_context", return_value="unix:///var/run/docker.sock"), \
                 patch.object(labs, "docker", return_value="27\n"):
                labs.setup(root)
            with patch.dict(os.environ, {"DOCKER_HOST": "tcp://example.invalid:2376"}, clear=True), \
                 patch.object(labs.subprocess, "run", side_effect=AssertionError("remote cleanup")):
                with self.assertRaisesRegex(ValueError, "遠隔"):
                    labs.cleanup(root)
            with patch.dict(os.environ, {"DOCKER_HOST": "unix:///var/run/docker.sock"}, clear=True), \
                 patch.object(labs.shutil, "which", return_value="/training/bin/mock/docker"), \
                 patch.object(labs.subprocess, "run", side_effect=AssertionError("mock cleanup")):
                with self.assertRaisesRegex(ValueError, "本物"):
                    labs.cleanup(root)

    def test_resource_names_cannot_be_retargeted_to_other_containers(self):
        with tempfile.TemporaryDirectory(prefix="dojo-container-name-") as temporary:
            root = Path(temporary)
            with patch.object(labs, "local_context", return_value="unix:///var/run/docker.sock"), \
                 patch.object(labs, "docker", return_value="27\n"):
                labs.setup(root)
            data = labs.state(root)
            data["name"] = "existing-production-container"
            (root / ".docker-fixture.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "専用"):
                labs.state(root)


class DockerLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(available(), "本物のDockerデーモンに接続できません。実機ライフサイクルは未検証。")
    def test_real_build_failure_recovery_recreation_and_volume_persistence(self):
        with tempfile.TemporaryDirectory(prefix="dojo-container-runtime-") as temporary:
            root = Path(temporary)
            labs.setup(root)
            try:
                with self.assertRaises((ValueError, OSError)):
                    labs.check(root)
                result = subprocess.run(["bash", "-c", labs.SOLUTION], cwd=root,
                                        capture_output=True, text=True, timeout=300)
                self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
                labs.check(root)
                (root / "health.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "health.json"):
                    labs.check(root)
            finally:
                labs.cleanup(root)


if __name__ == "__main__":
    unittest.main()
