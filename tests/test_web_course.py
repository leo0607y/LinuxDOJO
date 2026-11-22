"""/course/ 用データ生成 (tools/build_course_data.py) の確認。ネットワーク不要。"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_course_data as bcd  # noqa: E402

SITE = ROOT / "web" / "danganlog"


class CourseDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = bcd.build()

    def test_all_catalog_topics_with_goals(self):
        from curriculum.toolbox_catalog import TOPICS
        self.assertEqual([t["id"] for t in self.data["topics"]], [t["id"] for t in TOPICS])
        self.assertEqual(len(TOPICS), 32)
        for t in self.data["topics"]:
            self.assertTrue(t["goal"], t["id"])
            self.assertTrue(t["blocks"], t["id"])

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a" / "course-data.json", Path(tmp) / "b" / "course-data.json"
            bcd.main(["-o", str(a)]); bcd.main(["-o", str(b)])
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual((a.parent / "course-search.json").read_bytes(), (b.parent / "course-search.json").read_bytes())

    def test_status_labels_are_honest(self):
        for module in bcd.VM_STATIC:
            self.assertIn("実VM未実施", bcd.vm_status(module)[1])
        for module in bcd.VM_NEW:
            self.assertIn("実VM未実施", bcd.vm_status(module)[1])
        self.assertEqual(bcd.vm_status("boot")[0], "real")
        listed = {v["id"] for t in self.data["topics"] for v in t["vm"]}
        self.assertTrue(listed <= set(self.data["vmModules"]))

    def test_coverage_matches_rows(self):
        cov = self.data["coverage"]
        for exam in cov["exams"]:
            counted = cov["counted"][exam["exam"]]
            for key in ("covered", "partial", "missing"):
                self.assertEqual(exam[key], counted[key], exam["exam"])

    def test_generated_files_are_git_ignored_and_no_emoji(self):
        out = subprocess.run(["git", "check-ignore", "web/danganlog/public/course-data.json",
                              "web/danganlog/public/course-search.json"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        import re
        emoji = re.compile("[\U0001F000-\U0001FAFF✅❌✨⭐⚠]")
        for path in (SITE / "app" / "course").rglob("*"):
            if path.is_file():
                self.assertIsNone(emoji.search(path.read_text(encoding="utf-8")), str(path))

    @unittest.skipUnless(shutil.which("node") and (SITE / "node_modules").is_dir(), "node/node_modules なし")
    def test_node_tests(self):
        r = subprocess.run(["node", "--test", "tests/course.test.mjs"], cwd=SITE, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
