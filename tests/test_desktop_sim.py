"""デスクトップ周辺機器【模擬】の検証。全課題の正解が通り、罠が通らないこと、模擬である旨の表示、取り込みの安全性。"""
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum import festival
from engine import guided, readiness

SCENARIOS = [s for _, _, items in festival.packs("desktop_hw") for s in items]


class DesktopSimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="linuxdojo-desktop-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        guard = patch("subprocess.run", side_effect=AssertionError("host subprocess"))
        guard.start()
        self.addCleanup(guard.stop)

    def run_steps(self, scenario, steps, label, strict=True):
        terminal = readiness.prepare(scenario, self.root / label)
        for command in steps:
            result = terminal.execute(command)
            if strict:
                self.assertEqual(result.code, scenario.get("expected_codes", {}).get(command, 0),
                                 f"{scenario['id']} {command!r}: {result.output}")
        return terminal

    def term(self, preset="healthy", files=None):
        scenario = {"id": "x", "files": files or {}, "remote_files": {}, "desktop": preset}
        return readiness.prepare(scenario, self.root / ("t-" + preset))

    def test_at_least_24_tasks_over_four_areas_with_levels(self):
        self.assertGreaterEqual(len(SCENARIOS), 24)
        self.assertEqual({s["level"] for s in SCENARIOS}, {1, 2, 3})
        for area, low in (("wifi", 6), ("bt", 6), ("audio", 6), ("print", 6)):
            self.assertGreaterEqual(sum(1 for s in SCENARIOS if s["desktop"].startswith(area)), low, area)

    def test_every_task_is_labelled_as_simulation(self):
        for s in SCENARIOS:
            with self.subTest(task=s["id"]):
                self.assertIn("【模擬】", s["title"])
                self.assertIn("【模擬】", s["brief"])
                self.assertIn("実機", s["explanation"])
                self.assertIn("証明にはなりません", s["explanation"])

    def test_every_task_starts_unsolved_and_every_solution_passes(self):
        for s in SCENARIOS:
            self.assertFalse(readiness.check(s, readiness.prepare(s, self.root / "fresh"))[0], s["id"])
            for n, steps in enumerate([s["solution"], *s["alt_solutions"]]):
                with self.subTest(task=s["id"], route=n):
                    ok, message = readiness.check(s, self.run_steps(s, steps, f"r{n}"))
                    self.assertTrue(ok, f"{s['id']} route {n}: {message}")

    def test_every_trap_fails_and_each_task_has_a_trap_and_hints(self):
        for s in SCENARIOS:
            self.assertTrue(s["traps"], s["id"])
            self.assertEqual(len(s["hints"]), 3)
            for n, steps in enumerate(s["traps"]):
                with self.subTest(task=s["id"], trap=n):
                    self.assertFalse(readiness.check(s, self.run_steps(s, steps, f"t{n}", strict=False))[0])

    def test_state_does_not_leak_between_tasks(self):
        t = self.term("wifi_blocked")
        self.assertIn("Soft blocked: yes", t.execute("rfkill list wifi").output)
        scenario = {"id": "y", "files": {}, "remote_files": {}}
        t2 = readiness.prepare(scenario, self.root / "other", t.progress)
        self.assertNotIn("desktop", t2.progress)

    def test_wifi_formats_and_errors(self):
        t = self.term("wifi_idle")
        self.assertTrue(t.execute("nmcli general status").output.startswith("STATE"))
        self.assertIn("Error: No network with SSID 'Nope' found.", t.execute("nmcli device wifi connect Nope password abcdefgh").output)
        r = t.execute("nmcli device wifi connect HomeNet password badpass99")
        self.assertEqual(r.code, 4)
        self.assertIn("(7) Secrets were required", r.output)
        self.assertIn("pre-shared key may be incorrect", t.execute("journalctl -u wpa_supplicant").output)
        self.assertIn("RF-kill", t.execute("rfkill block wifi").output + t.execute("sudo ip link set wlan0 up").output)
        self.assertIn("Operation not permitted", t.execute("iw dev wlan0 scan").output)

    def test_blocked_wifi_reports_the_classic_errors(self):
        t = self.term("wifi_blocked")
        self.assertIn("Scanning not allowed while unavailable", t.execute("nmcli device wifi rescan").output)
        self.assertIn("RF-kill", t.execute("sudo iw dev wlan0 scan").output)
        self.assertIn("unavailable", t.execute("nmcli device status").output)

    def test_bluetooth_errors(self):
        t = self.term("bt_blocked")
        self.assertEqual(t.execute("bluetoothctl power on").output, "Failed to set power on: org.bluez.Error.Blocked")
        t = self.term("bt_off")
        self.assertIn("NotReady", t.execute("bluetoothctl scan on").output)
        t = self.term("bt_service_down")
        self.assertIn("Waiting to connect to bluetoothd", t.execute("bluetoothctl devices").output)

    def test_audio_and_print_outputs(self):
        t = self.term("audio_profile_off")
        self.assertIn("auto_null", t.execute("pactl list short sinks").output)
        self.assertIn("Dummy Output", t.execute("wpctl status").output)
        t = self.term("audio_pulse_down")
        self.assertIn("Connection refused", t.execute("pactl info").output)
        self.assertEqual(t.execute("speaker-test -c2").code, 1)
        t = self.term("print_reject", {"a.txt": "x\n"})
        self.assertEqual(t.execute("lp -d Office-Laser a.txt").output, 'lp: Destination "Office-Laser" is not accepting jobs.')
        t = self.term("print_paused")
        self.assertIn("disabled since", t.execute("lpstat -p").output)
        self.assertIn("is not ready", t.execute("lpq").output)
        self.assertIn("Forbidden", t.execute("cupsenable Office-Laser").output)
        self.assertIn("DeviceURI", t.execute("cat etc-cups/printers.conf").output)

    def test_unsupported_syntax_uses_the_standard_message(self):
        t = self.term()
        for line in ("nmcli device wifi hotspot", "bluetoothctl", "lp -Z x", "pactl load-module foo", "wpctl inspect 3"):
            with self.subTest(line=line):
                self.assertIn("未対応", t.execute(line).output)

    def test_module_imports_nothing_dangerous_and_is_in_the_web_bundle(self):
        source = (ROOT / "engine" / "commands" / "desktop.py").read_text(encoding="utf-8")
        modules = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                modules |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertFalse(modules & {"subprocess", "socket", "os", "shutil", "urllib", "http"}, modules)
        sys.path.insert(0, str(ROOT / "tools"))
        self.addCleanup(sys.path.remove, str(ROOT / "tools"))
        import build_web
        patch.stopall()
        files = build_web.module_files()
        self.assertIn("engine/commands/desktop.py", files)
        self.assertIn("curriculum/festival/desktop_hw.py", files)


if __name__ == "__main__":
    unittest.main()
