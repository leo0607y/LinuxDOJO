"""Real cron lab: solution passes, wrong or tampered outcomes fail."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS

LAB = LABS["cron"]
BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(all(shutil.which(t) for t in LAB["tools"]), "実ツール未導入: " + " ".join(LAB["tools"]))
class CronLabTests(unittest.TestCase):
    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-cron-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        LAB["setup"](root)
        return root

    def solved(self):
        root = self.fresh()
        with self.assertRaises(BAD):
            LAB["check"](root)
        result = sh(root, LAB["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        LAB["check"](root)
        return root

    def test_solution_passes_with_fresh_fixtures(self):
        self.solved()
        self.solved()

    def test_wrong_examples_rejected(self):
        for wrong in LAB["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                root = self.fresh()
                sh(root, wrong)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_tampering_rejected(self):
        mutations = {
            "no crontab": lambda r: (r / "crontab.txt").unlink(),
            "job modified": lambda r: (r / "job.sh").write_text("#!/bin/sh\nexit 0\n"),
            "tool modified": lambda r: (r / "tools/report-tool").write_text("#!/bin/sh\nexit 0\n"),
            "two jobs": lambda r: (r / "crontab.txt").write_text(
                (r / "crontab.txt").read_text() + (r / "crontab.txt").read_text().splitlines()[-1] + "\n"),
            "six fields only": lambda r: (r / "crontab.txt").write_text("PATH=/usr/bin:/bin\n0 0 * * /bin/true x\n"),
            "unescaped percent": lambda r: (r / "crontab.txt").write_text(
                (r / "crontab.txt").read_text().replace("\\%", "%")),
            "no flock": lambda r: (r / "crontab.txt").write_text(
                (r / "crontab.txt").read_text().replace("flock -n", "env")),
            "wrong weekday": lambda r: (r / "crontab.txt").write_text(
                (r / "crontab.txt").read_text().replace("* * 1-5", "* * 0-6")),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    LAB["check"](root)

    def test_cron_schedule_parser(self):
        from curriculum.toolbox_labs import cron_parse, cron_fires, cron_split_percent
        import datetime
        ref = datetime.datetime(2026, 3, 6, 12, 0)
        fires = cron_fires(cron_parse("*/20 9-10 * * mon-fri".split()), ref, 4)
        self.assertEqual([f.strftime("%a %H:%M") for f in fires], ["Mon 09:00", "Mon 09:20", "Mon 09:40", "Mon 10:00"])
        self.assertEqual(cron_fires(cron_parse("0 0 13 * fri".split()), ref, 2)[0].day, 13)
        for bad in ("60 * * * *", "* 24 * * *", "*/0 * * * *", "a * * * *"):
            with self.assertRaises(ValueError):
                cron_parse(bad.split())
        self.assertEqual(cron_split_percent("date +\\%F%in%put"), ("date +%F", "in\nput"))


if __name__ == "__main__":
    unittest.main()
