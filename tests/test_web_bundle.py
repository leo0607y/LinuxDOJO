"""ブラウザー版 (web/danganlog) の教材バンドルと静的サイト設定の確認。ネットワークは使わない。"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_web  # noqa: E402

SITE = ROOT / "web" / "danganlog"
WORKER = SITE / "public" / "worker.js"
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2705\u274C\u2728\u2B50\u2B55\u26A0\u2757]")

# worker.js の PYTHON_BRIDGE を、実際の Pyodide の代わりに通常の Python で動かす。
DRIVER = r'''
import json, re, sys
src, work, worker = sys.argv[1:4]
text = open(worker, encoding="utf-8").read()
bridge = re.search(r"String\.raw`(.*?)`;\n\nasync function initialize", text, re.S).group(1)
bridge = bridge.replace("/dojo-src", src).replace("/dojo-work/session", work)
sys.path.insert(0, src)
ns = {}
exec(compile(bridge, "bridge", "exec"), ns)
req = lambda **k: json.loads(ns["browser_request"](json.dumps(k)))
init = req(type="init")
assert [m["id"] for m in init["catalog"]["modes"]] == ["intro", "basic", "advanced", "expert"]
assert len(init["catalog"]["scenarios"]) > 100
sel = req(type="select", mode="intro", index=0)
task = sel["lesson"]["task"]
wrong = req(type="execute", line="zzz-not-a-command")
assert wrong["completed"] is False and wrong["lesson"]["task"] == task
answer = req(type="answer")["output"].split("\n")[0]
right = req(type="execute", line=answer)
assert right["completed"] is True, right["output"]
state = req(type="export")["state"]
assert req(type="import", state=state)["lesson"]["id"] == sel["lesson"]["id"]
fest = req(type="select", mode="festival", index=0)
assert fest["lesson"]["task"]
print("OK")
'''


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "python-source.json"
        build_web.write(cls.out)
        cls.bundle = json.loads(cls.out.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_contents_and_exclusions(self):
        files = self.bundle["files"]
        for needed in ("engine/guided.py", "engine/readiness.py", "engine/vim_sim.py", "curriculum/beginner_lessons.py",
                       "curriculum/readiness.py", "curriculum/festival/__init__.py", "engine/commands/users.py"):
            self.assertIn(needed, files)
        self.assertNotIn("curriculum/__init__.py", files)  # 実践ステージ(本物のbash)を読み込む入口
        for name in files:
            self.assertTrue(name.endswith(".py"))
            self.assertFalse(name.startswith("/") or ".." in name.split("/"))
            self.assertFalse(set(name.split("/")) & {"workspace", "bin", "sysroot", ".lq_state"})
            self.assertNotRegex(name, r"stage\d+_")
        self.assertFalse([n for n in files if "save_data" in n])
        self.assertNotIn("main.py", {Path(n).name for n in files})

    def test_deterministic(self):
        again = self.tmp / "again.json"
        build_web.write(again)
        self.assertEqual(again.read_bytes(), self.out.read_bytes())

    def test_import_closure_and_bridge_run_without_repo(self):
        src = self.tmp / "src"
        for name, source in self.bundle["files"].items():
            target = src / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        work = self.tmp / "work"
        work.mkdir()
        done = subprocess.run([sys.executable, "-I", "-c", DRIVER, str(src), str(work / "session"), str(WORKER)],
                              capture_output=True, text=True, cwd=str(self.tmp), timeout=240)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertIn("OK", done.stdout)


class StaticSiteTests(unittest.TestCase):
    def test_next_config_is_static_export(self):
        config = (SITE / "next.config.mjs").read_text(encoding="utf-8")
        self.assertIn("output: 'export'", config)
        self.assertIn("unoptimized: true", config)

    def test_no_server_features(self):
        for forbidden in (SITE / "app" / "api", SITE / "middleware.js", SITE / "middleware.ts", SITE / "functions"):
            self.assertFalse(forbidden.exists(), forbidden)
        for path in (SITE / "app").rglob("*"):
            if path.is_file():
                self.assertNotIn("use server", path.read_text(encoding="utf-8"))

    def test_dependencies_pinned_and_lockfile(self):
        package = json.loads((SITE / "package.json").read_text(encoding="utf-8"))
        for name, version in package["dependencies"].items():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", name)
        self.assertTrue((SITE / "package-lock.json").is_file())

    def test_worker_protocol_unchanged(self):
        text = WORKER.read_text(encoding="utf-8")
        for kind in ("init", "export", "import", "select", "reset", "hint", "answer", "execute"):
            self.assertIn(f"kind == '{kind}'" if kind != "execute" else "kind != 'execute'", text)
        self.assertIn("new URL('./pyodide/'", text)

    def test_no_emoji_in_sources(self):
        sources = [p for d in ("app", "components", "lib", "public", "scripts", "tests") for p in (SITE / d).rglob("*")
                   if p.is_file() and p.suffix in {".js", ".jsx", ".mjs", ".css", ".html"} and "pyodide" not in p.parts]
        sources.append(SITE / "README.md")
        for path in sources:
            if path.exists():
                self.assertIsNone(EMOJI.search(path.read_text(encoding="utf-8")), path)


class NodeTests(unittest.TestCase):
    def test_node_suite(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node がありません")
        if not (SITE / "node_modules").is_dir():
            self.skipTest("npm ci が未実行です")
        result = subprocess.run([node, "--test", "tests/core.test.mjs"], cwd=str(SITE), capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
