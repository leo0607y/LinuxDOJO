"""ブラウザ版ブリッジ（web/danganlog/public/worker.js 内の Python）で全課題を正解入力で通せること。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_bridge(work):
    src = (ROOT / "web/danganlog/public/worker.js").read_text(encoding="utf-8")
    code = re.search(r"PYTHON_BRIDGE = String\.raw`(.*?)\n`;", src, re.S).group(1)
    code = code.replace("/dojo-src/curriculum", str(ROOT / "curriculum")).replace("/dojo-work/session", str(work))
    ns = {}
    sys.path.insert(0, str(ROOT))
    exec(compile(code, "bridge", "exec"), ns)
    return ns


class WebBridgeTest(unittest.TestCase):
    def test_every_guided_lesson_completes_through_browser_bridge(self):
        with tempfile.TemporaryDirectory() as work:
            ns = _load_bridge(Path(work) / "session")
            req, lessons = ns["browser_request"], ns["LESSONS"]
            failed = []
            for mode, items in lessons.items():
                for i, step in enumerate(items):
                    req(json.dumps({"type": "select", "mode": mode, "index": i}))
                    cmds = [step["command"]] if isinstance(step["command"], str) else list(step["command"])
                    out = None
                    for c in cmds:
                        for line in c.split("\n"):
                            out = json.loads(req(json.dumps({"type": "execute", "line": line})))
                    if not (out and out.get("completed")):
                        failed.append(step["id"])
            self.assertEqual(failed, [])

    def test_export_is_plain_json_and_import_restores_state(self):
        def plain(o):
            if type(o) in (str, int, float, bool, type(None)):
                return True
            if type(o) is list:
                return all(plain(v) for v in o)
            return type(o) is dict and all(type(k) is str and plain(v) for k, v in o.items())
        with tempfile.TemporaryDirectory() as work:
            ns = _load_bridge(Path(work) / "session")
            req = lambda d: json.loads(ns["browser_request"](json.dumps(d)))
            picks = [(m, i) for m, items in ns["LESSONS"].items() for i in range(0, len(items), 9)]
            for mode, i in picks:
                step = ns["LESSONS"][mode][i]
                req({"type": "select", "mode": mode, "index": i})
                req({"type": "hint"}); req({"type": "answer"})
                cmds = [step["command"]] if isinstance(step["command"], str) else list(step["command"])
                for c in cmds:
                    for line in c.split("\n"):
                        view = req({"type": "execute", "line": line})
                state = req({"type": "export"})["state"]
                self.assertTrue(plain(state), step["id"])
                back = json.loads(json.dumps(state))
                self.assertEqual(back, state)
                req({"type": "import", "state": back})
                self.assertEqual(req({"type": "export"})["state"], back, step["id"])
                self.assertTrue(req({"type": "select", "mode": mode, "index": i})["completed"], step["id"])
            scenario = ns["_web_scenarios"][0]
            req({"type": "select", "mode": "festival", "index": 0})
            sol = scenario["solution"]
            for line in ("\n".join(sol) if isinstance(sol, list) else sol).split("\n"):
                req({"type": "execute", "line": line})
            self.assertTrue(req({"type": "execute", "line": "check"})["completed"])
            state = json.loads(json.dumps(req({"type": "export"})["state"]))
            req({"type": "import", "state": state})
            self.assertEqual(req({"type": "export"})["state"], state)
            self.assertTrue(req({"type": "select", "mode": "festival", "index": 0})["completed"])

    def test_reset_mode_clears_only_that_mode(self):
        with tempfile.TemporaryDirectory() as work:
            ns = _load_bridge(Path(work) / "session")
            req = ns["browser_request"]
            for mode, cmd in (("intro", "echo こんにちは"), ("basic", None)):
                req(json.dumps({"type": "select", "mode": mode, "index": 0}))
                step = ns["LESSONS"][mode][0]
                req(json.dumps({"type": "execute", "line": cmd or step["command"]}))
            view = json.loads(req(json.dumps({"type": "resetMode", "mode": "intro"})))
            self.assertEqual(view["index"], 0)
            self.assertFalse(view["completed"])
            state = view["state"]
            self.assertEqual(state["completed"]["intro"], [])
            self.assertTrue(state["completed"]["basic"])
            self.assertFalse([k for k in state["sessions"] if k.startswith("intro:") and k != "intro:intro-01"])

    def test_reset_all_clears_every_mode(self):
        with tempfile.TemporaryDirectory() as work:
            ns = _load_bridge(Path(work) / "session")
            req = ns["browser_request"]
            for mode in ("intro", "basic"):
                req(json.dumps({"type": "select", "mode": mode, "index": 0}))
                req(json.dumps({"type": "execute", "line": ns["LESSONS"][mode][0]["command"]}))
            view = json.loads(req(json.dumps({"type": "resetAll"})))
            self.assertFalse(view["completed"])
            self.assertTrue(all(not v for k, v in view["state"]["completed"].items() if k != "festival"))
            self.assertEqual(view["state"]["review"], {})


if __name__ == "__main__":
    unittest.main()
