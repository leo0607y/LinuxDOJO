"""応用練習で使う模擬シェルの機能（パイプ・ワイルドカード・変数・プロセス・置換）の回帰テスト。"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import guided, readiness, save

ACCESS = "192.0.2.1 a 404\n192.0.2.2 b 200\n192.0.2.1 c 404\n192.0.2.3 d 500\n192.0.2.1 e 200\n"


class ShellFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-shell-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.progress = {}
        self.term = guided.Terminal(self.base / "t", self.progress)
        (self.term.root / "access.log").write_text(ACCESS, encoding="utf-8")

    def ok(self, command):
        result = self.term.execute(command)
        self.assertEqual(result.code, 0, f"{command}: {result.output}")
        return result.output

    def test_pipeline_ranking_matches_gnu_format(self):
        out = self.ok('cut -d " " -f 1 access.log | sort | uniq -c | sort -rn | head -n 2')
        self.assertEqual(out, "      3 192.0.2.1\n      1 192.0.2.3")

    def test_pipeline_result_can_be_saved_and_appended(self):
        self.ok("grep 404 access.log | wc -l > count.txt")
        self.ok("grep -c 500 access.log >> count.txt")
        self.assertEqual((self.term.root / "count.txt").read_text(encoding="utf-8"), "2\n1\n")

    def test_redirect_in_the_middle_of_a_pipeline_is_explained(self):
        result = self.term.execute("grep 404 access.log > a.txt | wc -l")
        self.assertEqual(result.code, 1)
        self.assertIn("最後", result.output)
        self.assertFalse((self.term.root / "a.txt").exists())

    def test_command_chaining_is_still_rejected(self):
        for command in ("ls && whoami", "ls ; whoami", "ls || whoami", "ls | | wc"):
            with self.subTest(command=command):
                self.assertNotEqual(self.term.execute(command).code, 0)

    def test_pipes_follow_quotes_like_bash(self):
        self.assertEqual(self.ok("grep -c 404 access.log|wc -l"), "1")
        self.assertEqual(self.ok('grep -E "404|500" access.log | wc -l'), "3")
        self.assertEqual(self.ok("echo 'a|b'"), "a|b")

    def test_grep_regex_and_options(self):
        (self.term.root / "app.conf").write_text("# c\nport=1\n\nhost=x\n", encoding="utf-8")
        self.assertEqual(self.ok('grep -v "^#" app.conf | grep -v "^$"'), "port=1\nhost=x")
        self.assertEqual(self.ok("grep -n port app.conf"), "2:port=1")
        self.assertEqual(self.term.execute("grep missing app.conf").code, 1)

    def test_globs_expand_inside_the_folder_only(self):
        for name in ("a.tmp", "b.tmp", ".hidden.tmp", "keep.txt"):
            (self.term.root / name).write_text("x", encoding="utf-8")
        self.assertEqual(self.ok("ls *.tmp"), "a.tmp\nb.tmp")
        self.ok("rm *.tmp")
        self.assertTrue((self.term.root / ".hidden.tmp").exists())
        self.assertTrue((self.term.root / "keep.txt").exists())
        self.assertNotEqual(self.term.execute("cat ../*").code, 0)
        self.assertNotEqual(self.term.execute("ls /etc/*").code, 0)
        self.assertNotEqual(self.term.execute("ls *.none").code, 0)  # 一致なしは名前のまま渡る

    def test_copy_and_move_several_files_into_a_folder(self):
        for name in ("a.log", "b.log"):
            (self.term.root / name).write_text(name, encoding="utf-8")
        self.ok("mkdir backup")
        self.ok("cp *.log backup")
        self.ok("mkdir archive")
        self.ok("mv a.log b.log archive")
        self.assertEqual(sorted(p.name for p in (self.term.root / "backup").iterdir()), ["a.log", "access.log", "b.log"])
        self.assertEqual(sorted(p.name for p in (self.term.root / "archive").iterdir()), ["a.log", "b.log"])
        self.assertNotEqual(self.term.execute("cp access.log backup/x archive/y").code, 0)

    def test_wc_with_several_files_prints_total(self):
        (self.term.root / "b.log").write_text("1\n2\n", encoding="utf-8")
        self.assertEqual(self.ok("wc -l access.log b.log"), "5 access.log\n2 b.log\n7 total")

    def test_variables_follow_quotes_and_export(self):
        self.assertEqual(self.ok("echo $HOME"), "/home/learner")
        self.assertEqual(self.ok("echo '$HOME'"), "$HOME")
        self.ok("NAME=dojo")
        self.assertEqual(self.ok('echo "hi $NAME"'), "hi dojo")
        self.assertNotIn("NAME=dojo", self.ok("env"))
        self.ok("export NAME")
        self.assertIn("NAME=dojo", self.ok("env"))
        self.ok("unset NAME")
        self.assertEqual(self.ok("echo $NAME"), "")

    def test_variable_values_are_not_executed_as_commands(self):
        marker = self.base / "must-not-exist"
        self.ok(f"export EVIL='$(touch {marker})'")
        self.ok("echo $EVIL")
        self.ok("export SPLIT='a && whoami'")
        self.assertEqual(self.ok("echo $SPLIT"), "a && whoami")
        self.assertFalse(marker.exists())

    def test_kill_rules(self):
        self.progress["processes"].append({"pid": 4321, "user": "learner", "cmd": "python3 runaway.py",
                                           "cpu": 99.0, "mem": 1.0, "ignores_term": True})
        self.assertIn("4321", self.ok("pgrep runaway"))
        self.ok("kill 4321")
        self.assertIn("runaway", self.ok("ps aux | grep runaway"))
        self.ok("kill -9 4321")
        self.assertEqual(self.term.execute("pgrep runaway").code, 1)
        self.assertIn("not permitted", self.term.execute("kill 845").output)
        self.assertNotEqual(self.term.execute("sudo kill 1").code, 0)
        self.assertNotEqual(self.term.execute("kill 2001").code, 0)
        self.ok("sudo kill 845")

    def test_kill_never_touches_host_processes(self):
        with patch("os.kill", side_effect=AssertionError("host kill")):
            self.ok("sudo kill -9 512")

    def test_steps_reset_processes_and_env(self):
        self.ok("export X=1")
        self.ok("sudo kill 845")
        guided.prepare_step(self.term, {"env": {"Y": "2"}})
        self.assertNotIn("X", self.progress["env"])
        self.assertEqual(self.progress["env"]["Y"], "2")
        self.assertIn("cron", self.ok("ps aux"))


class MoreCommandTests(ShellFeatureTests.__base__):
    setUp = ShellFeatureTests.setUp
    ok = ShellFeatureTests.ok

    def test_chmod_numbers_symbols_and_several_files(self):
        for name in ("a.sh", "b.sh", "secret.conf"):
            self.ok(f"touch {name}")
        self.ok("chmod 750 *.sh")
        self.assertEqual(self.term.mode_of(self.term.path("a.sh")), 0o750)
        self.ok("chmod go-r secret.conf")
        self.assertEqual(self.term.mode_of(self.term.path("secret.conf")), 0o600)
        self.ok("chmod a+x,u-w secret.conf")
        self.assertEqual(self.term.mode_of(self.term.path("secret.conf")), 0o511)
        self.ok("chmod +x b.sh")
        self.assertEqual(self.term.mode_of(self.term.path("b.sh")), 0o751)
        self.assertNotEqual(self.term.execute("chmod 999 a.sh").code, 0)

    def test_new_files_are_644_whatever_the_umask(self):
        import os
        old = os.umask(0o077)
        try:
            self.ok("touch new.txt")
            self.ok("echo hi > said.txt")
        finally:
            os.umask(old)
        self.assertEqual(self.term.mode_of(self.term.path("new.txt")), 0o644)
        self.assertEqual(self.term.mode_of(self.term.path("said.txt")), 0o644)

    def test_text_tools_header_skip_sort_key_open_range_and_diff(self):
        (self.term.root / "s.csv").write_text("name,score\nb,2\na,10\nc,1\n", encoding="utf-8")
        self.assertEqual(self.ok("tail -n +2 s.csv | sort -t , -k 2 -n"), "c,1\nb,2\na,10")
        self.assertEqual(self.ok("cut -d , -f 2- s.csv | head -n 1"), "score")
        (self.term.root / "new.conf").write_text("name,score\nb,3\na,10\n", encoding="utf-8")
        result = self.term.execute("diff s.csv new.conf")
        self.assertEqual(result.code, 1)
        self.assertEqual(result.output, "2c2\n< b,2\n---\n> b,3\n4d3\n< c,1")
        self.assertEqual(self.term.execute("diff s.csv s.csv").code, 0)

    def test_versions_and_apt_search_by_description(self):
        self.assertEqual(self.term.execute("jq --version").code, 127)
        self.assertIn("vim", self.ok("apt search エディタ"))

    def test_scp_with_port(self):
        self.progress["ssh_known"] = True
        (self.term.root / "up.txt").write_text("x\n", encoding="utf-8")
        self.ok("scp -P 2222 up.txt learner@training-server:up.txt")
        self.assertTrue((self.term.root / ".remote/up.txt").exists())
        self.assertEqual(self.term.execute("scp -P 9999 up.txt learner@training-server:x").code, 255)

    def test_du_counts_blocks(self):
        self.ok("mkdir logs")
        (self.term.root / "logs/a").write_text("x" * 20000, encoding="utf-8")
        self.assertEqual(self.ok("du -sh logs"), "24K\tlogs")  # フォルダ 4K + 20000 バイト（5ブロック）


class ReadinessCheckTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-checks-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def scenario(self, **checks):
        base = {"id": "t", "files": {}, "remote_files": {}, "expected_files": {}, "expected_modes": {}, "absent": [],
                "packages": [], "checks_commands": [], "require_disconnected": False, "expected_env": {},
                "process_gone": [], "process_kept": [], "min_lines": {}}
        base.update(checks)
        return base

    def test_package_absent_order_and_remote_files(self):
        sc = self.scenario(initial_packages=["jq"], apt_updated=True, packages_absent=["jq"],
                           ordered_commands=["ps aux", ["kill 4321", "kill -15 4321"], "kill -9 4321"],
                           remote_files={"app.conf": "a\n"}, remote_expected_files={"app.conf": "b\n"},
                           processes=[{"pid": 4321, "user": "learner", "cmd": "w", "cpu": 1, "mem": 1, "ignores_term": True}])
        t = readiness.prepare(sc, self.root)
        self.assertFalse(readiness.check(sc, t)[0])
        for command in ("sudo apt remove jq", "kill -9 4321"):
            t.execute(command)
        (t.root / ".remote/app.conf").write_text("b\n", encoding="utf-8")
        self.assertIn("順番", readiness.check(sc, t)[1])
        t = readiness.prepare(sc, self.root)
        for command in ("sudo apt remove jq", "ps aux", "kill 4321", "kill -9 4321"):
            t.execute(command)
        (t.root / ".remote/app.conf").write_text("b\n", encoding="utf-8")
        self.assertTrue(readiness.check(sc, t)[0], readiness.check(sc, t)[1])

    def test_initial_modes_and_removed_env(self):
        sc = self.scenario(files={"key": "k\n"}, modes={"key": 0o644}, expected_modes={"key": 0o600},
                           env={"DEBUG": "1"}, expected_env={"DEBUG": None})
        t = readiness.prepare(sc, self.root)
        self.assertFalse(readiness.check(sc, t)[0])
        t.execute("chmod 600 key")
        t.execute("unset DEBUG")
        self.assertTrue(readiness.check(sc, t)[0])


class VimSubstituteTests(unittest.TestCase):
    def test_substitute_line_and_file(self):
        from engine import vim_sim
        st = vim_sim.new_state("a", "a", False, ["a=1 a", "b=1", "a=1"], True)
        self.assertEqual(vim_sim.handle(st, ":s/a/x/")[1], 0)
        self.assertEqual(st["lines"][0], "x=1 a")
        vim_sim.handle(st, ":%s/a/y/g")
        self.assertEqual(st["lines"], ["x=1 y", "b=1", "y=1"])
        vim_sim.handle(st, "u")
        self.assertEqual(st["lines"], ["x=1 a", "b=1", "a=1"])
        self.assertEqual(vim_sim.handle(st, ":%s/zzz/q/")[1], 1)

    def test_ranges_delimiters_append_and_counted_delete(self):
        from engine import vim_sim
        st = vim_sim.new_state("a", "a", False, ["root=/var/www", "x", "x", "x"], True)
        vim_sim.handle(st, ":%s#/var/www#/srv/www#")
        self.assertEqual(st["lines"][0], "root=/srv/www")
        vim_sim.handle(st, ":2,3s/x/y/")
        self.assertEqual(st["lines"], ["root=/srv/www", "y", "y", "x"])
        self.assertEqual(vim_sim.handle(st, ":3,9s/x/y/")[1], 1)
        vim_sim.handle(st, "gg")
        vim_sim.handle(st, "A")
        vim_sim.handle(st, " # web")
        vim_sim.handle(st, "esc")
        self.assertEqual(st["lines"][0], "root=/srv/www # web")
        st["cursor"] = 1
        vim_sim.handle(st, "2dd")
        self.assertEqual(st["lines"], ["root=/srv/www # web", "x"])


class MasteryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-mastery-test-")
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(save, "SAVE", Path(self.tmp.name) / "save.json")
        p.start()
        self.addCleanup(p.stop)

    def test_every_area_has_items_and_progress_grows(self):
        d = save.empty()
        rows, ratio = readiness.mastery(d)
        self.assertEqual(ratio, 0)
        self.assertTrue(all(total > 0 for _, _, total in rows))
        d["learning"]["intro"]["completed"] = ["intro-01"]
        d["learning"]["readiness"] = {"completed": {"ready-02": {"assisted": False}}}
        d["cleared"]["1-1"] = {"score": 1}
        rows, ratio = readiness.mastery(d)
        self.assertEqual(rows[0][1], 2)
        self.assertEqual(rows[1][1], 1)
        self.assertGreater(ratio, 0)

    def test_full_completion_shows_master_title(self):
        d = save.empty()
        for name, lessons, challenges, missions in readiness.mastery_areas():
            d["learning"]["intro"]["completed"] += lessons
            d["learning"].setdefault("readiness", {"completed": {}})["completed"].update({x: {"assisted": False} for x in challenges})
            d["cleared"].update({x: {"score": 1} for x in missions})
        self.assertEqual(readiness.mastery(d)[1], 1.0)
        self.assertTrue(any("マスター" in line for line in readiness.mastery_lines(d)))

    def test_festival_menu_opens_a_pack_and_returns(self):
        save.store(save.empty())
        out = io.StringIO()
        with patch.object(readiness.ui, "clear"), patch("builtins.input", side_effect=["2", "b", "b"]), \
             contextlib.redirect_stdout(out):
            readiness.run()
        self.assertIn("自由自在度", out.getvalue())
        self.assertIn("★", out.getvalue())


if __name__ == "__main__":
    unittest.main()
