"""Git の履歴の保持、最小権限、運用課題の状態判定を検証する。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curriculum import festival
from engine import guided, readiness
from engine.commands import git, users


class GitAndAccountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-git-users-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.terminal = guided.Terminal(self.base / "terminal", {})

    def execute(self, *commands):
        for line in commands:
            result = self.terminal.execute(line)
            self.assertEqual(result.code, 0, f"{line}: {result.output}")

    def git_start(self, *ops):
        guided.prepare_step(self.terminal, {
            "cwd": "project", "packages": ["git"],
            "git": {"identity": True, "ops": [{"init": True}, *ops]},
        })

    def test_amend_first_commit_replaces_root_and_retains_tree(self):
        self.git_start({"commit": "Typo", "files": {"app.conf": "port=8080\n"}})
        _, repo = git.find_repo(self.terminal)
        old = git.head_id(repo)
        self.execute('git commit --amend -m "Initial config"')
        current = git.head_id(repo)
        self.assertNotEqual(current, old)
        self.assertEqual(git.history(repo, current), [current])
        self.assertIsNone(repo["commits"][current]["parent"])
        self.assertEqual(git.tree_of(repo, current), {"app.conf": "port=8080\n"})

    def test_amend_later_commit_keeps_original_parent(self):
        self.git_start({"commit": "Initial", "files": {"app.conf": "port=8080\n"}},
                       {"commit": "Typo", "files": {"app.conf": "port=9090\n"}})
        _, repo = git.find_repo(self.terminal)
        parent = repo["commits"][git.head_id(repo)]["parent"]
        self.execute('git commit --amend -m "Change port"')
        self.assertEqual(git.history(repo, git.head_id(repo)), [git.head_id(repo), parent])

    def test_amend_unborn_repository_cannot_create_a_commit(self):
        self.git_start()
        self.execute("echo content > app.conf", "git add app.conf")
        result = self.terminal.execute('git commit --amend -m "Wrong"')
        self.assertEqual(result.code, 128)
        self.assertIsNone(git.head_id(git.find_repo(self.terminal)[1]))

    def test_add_and_revoke_group_preserves_other_memberships(self):
        guided.prepare_step(self.terminal, {"cwd": "."})
        self.execute("sudo usermod -aG staff bob")
        self.assertIn("developers", users.groups_of(self.terminal, "bob"))
        self.assertIn("staff", users.groups_of(self.terminal, "bob"))
        self.execute("sudo gpasswd -d bob developers")
        self.assertNotIn("developers", users.groups_of(self.terminal, "bob"))
        self.assertIn("staff", users.groups_of(self.terminal, "bob"))
        self.assertIn("alice", users.state(self.terminal)["groups"]["developers"]["members"])

    def test_password_lock_does_not_change_shell_or_membership(self):
        guided.prepare_step(self.terminal, {"cwd": "."})
        before = users.groups_of(self.terminal, "bob")
        self.execute("sudo usermod -L bob")
        self.assertTrue(users.user_info(self.terminal, "bob")["locked"])
        self.assertEqual(users.user_info(self.terminal, "bob")["shell"], "/bin/bash")
        self.assertEqual(users.groups_of(self.terminal, "bob"), before)

    def test_default_id_reflects_current_users_group_memberships(self):
        guided.prepare_step(self.terminal, {"cwd": "."})
        before = self.terminal.execute("id")
        self.assertEqual(before.code, 0)
        self.assertIn("1000(learner)", before.output)
        self.assertIn("27(sudo)", before.output)
        self.assertNotIn("50(staff)", before.output)
        self.execute("sudo gpasswd -a learner staff")
        self.assertIn("50(staff)", self.terminal.execute("id").output)
        self.assertEqual(self.terminal.execute("id").output, self.terminal.execute("id learner").output)
        self.execute("sudo gpasswd -d learner staff")
        self.assertNotIn("50(staff)", self.terminal.execute("id").output)
        self.assertIn("27(sudo)", self.terminal.execute("id").output)

    def test_account_deletion_is_local_and_preserves_unrelated_files(self):
        guided.prepare_step(self.terminal, {"cwd": ".", "files": {"handover.txt": "keep\n"}})
        self.execute("sudo userdel --remove deploy")
        self.assertFalse(users.user_exists(self.terminal, "deploy"))
        self.assertEqual(self.terminal.path("handover.txt").read_text(), "keep\n")
        self.assertNotEqual(self.terminal.execute("sudo userdel learner").code, 0)
        self.assertTrue(users.user_exists(self.terminal, "learner"))
        fresh = guided.Terminal(self.base / "separate", {})
        self.assertTrue(users.user_exists(fresh, "deploy"))
        self.assertIn("deploy", users.BASE_USERS)

    def test_completed_git_task_rejects_subsequent_unstaged_change(self):
        scenario = next(s for _, _, items in festival.packs("operations") for s in items
                        if s["id"] == "fes-operations-04")
        self.terminal = readiness.prepare(scenario, self.base / "festival")
        self.execute(*scenario["solution"])
        self.assertTrue(readiness.check(scenario, self.terminal)[0])
        self.execute("echo extra > untracked.txt")
        self.assertFalse(readiness.check(scenario, self.terminal)[0])
        self.execute("rm untracked.txt", "echo wrong > app.conf")
        self.assertFalse(readiness.check(scenario, self.terminal)[0])

    def test_umask_applies_to_new_files_directories_and_copies(self):
        for virtual in (False, True):
            with self.subTest(virtual=virtual), patch.object(guided.Terminal, "VIRTUAL_MODES", virtual):
                self.terminal = guided.Terminal(self.base / f"mask-{virtual}", {})
                guided.prepare_step(self.terminal, {"cwd": ".", "packages": ["vim"], "files": {"original.sh": "echo ok\n"}})
                self.execute("chmod 755 original.sh", "umask 077", "touch new.txt", "echo hello > redirected.txt",
                             "mkdir -p private/nested", "cp original.sh copy.sh", "vim editor.txt", "i", "edited", "esc", ":wq")
                for name, mode in {"new.txt": 0o600, "redirected.txt": 0o600, "private": 0o700,
                                   "private/nested": 0o700, "copy.sh": 0o700, "editor.txt": 0o600}.items():
                    self.assertEqual(self.terminal.mode_of(self.terminal.path(name)), mode, name)
                # 再度の touch・上書き・mkdir -p は、既存の権限を変更しない。
                self.execute("umask 022", "touch new.txt", "echo update > redirected.txt", "mkdir -p private/nested")
                self.assertEqual(self.terminal.mode_of(self.terminal.path("new.txt")), 0o600)
                self.assertEqual(self.terminal.mode_of(self.terminal.path("redirected.txt")), 0o600)
                self.assertEqual(self.terminal.mode_of(self.terminal.path("private/nested")), 0o700)
                self.execute("umask 077")
                self.terminal.restore_file("fixture/seed.txt", "fixture\n")
                self.assertEqual(self.terminal.mode_of(self.terminal.path("fixture")), 0o755)
                self.assertEqual(self.terminal.mode_of(self.terminal.path("fixture/seed.txt")), 0o644)


if __name__ == "__main__":
    unittest.main()
