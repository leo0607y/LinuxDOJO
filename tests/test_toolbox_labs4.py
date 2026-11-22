"""Real X11 / desktop-file / flatpak labs: solutions pass, wrong or tampered outcomes fail."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from curriculum.toolbox_labs import LABS

BAD = (ValueError, AssertionError, OSError)


def sh(root, script):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)


class Base:
    lab_id = ""

    def fresh(self):
        temporary = tempfile.TemporaryDirectory(prefix="dojo-%s-" % self.lab_id)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.lab["setup"](root)
        return root

    def solved(self):
        root = self.fresh()
        with self.assertRaises(BAD):
            self.lab["check"](root)
        result = sh(root, self.lab["solution"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.lab["check"](root)
        return root

    def test_solution_passes_with_fresh_fixtures(self):
        self.solved()
        self.solved()

    def test_wrong_examples_rejected(self):
        for wrong in self.lab["wrong"]:
            with self.subTest(wrong=wrong[:40]):
                root = self.fresh()
                sh(root, wrong)
                with self.assertRaises(BAD):
                    self.lab["check"](root)

    def tamper(self, mutations):
        for name, mutate in mutations.items():
            with self.subTest(name):
                root = self.solved()
                mutate(root)
                with self.assertRaises(BAD):
                    self.lab["check"](root)


def edit(name, old, new):
    return lambda r: (r / name).write_text((r / name).read_text().replace(old, new))


XTOOLS = all(shutil.which(t) for t in ("Xvfb", "xdpyinfo", "xauth", "xhost", "xdotool", "mcookie"))


@unittest.skipUnless(XTOOLS, "実ツール未導入: Xvfb/x11-utils/xauth/xdotool")
class XorgLabTests(Base, unittest.TestCase):
    lab = LABS["xorg"]
    lab_id = "xorg"

    def test_tampering_rejected(self):
        self.tamper({
            "open access": edit("xstart.sh", "-nolisten tcp", "-ac -nolisten tcp"),
            "no auth": edit("xstart.sh", '-auth "$PWD/Xauthority"', ""),
            "bad depth": edit("xstart.sh", "x24", "x16"),
            "remote cookie differs": lambda r: (r / "remote.xauth").write_bytes(b""),
            "wrong port": edit("answers.txt", "tcp_port_for_this_display=", "tcp_port_for_this_display=1"),
            "wrong -Y": edit("answers.txt", "ssh_trusted_forwarding_option=-Y", "ssh_trusted_forwarding_option=-X"),
            "conf layout": edit("xorg.conf.d/90-dojo.conf", "ctrl:nocaps", "grp:alt_shift_toggle"),
            "conf unbalanced": edit("xorg.conf.d/90-dojo.conf", "EndSection", ""),
            "conf not keyboard": edit("xorg.conf.d/90-dojo.conf", "MatchIsKeyboard", "MatchIsPointer"),
        })


DTOOLS = all(shutil.which(t) for t in ("desktop-file-validate", "xdg-mime", "update-desktop-database", "gio",
                                       "xdg-user-dirs-update", "xdg-user-dir"))


def entry(kind):
    def path(r):
        slug = json.loads((r / "spec.json").read_text())["slug"]
        return r / ("xdg/data/applications/%s-%s.desktop" % (slug, kind))
    return path


def swap(kind, old, new):
    return lambda r: entry(kind)(r).write_text(entry(kind)(r).read_text().replace(old, new))


def slug_of(r):
    return json.loads((r / "spec.json").read_text())["slug"]


@unittest.skipUnless(DTOOLS, "実ツール未導入: desktop-file-utils/xdg-utils/gio")
class DesktopFileLabTests(Base, unittest.TestCase):
    lab = LABS["desktopfile"]
    lab_id = "desktopfile"

    def test_tampering_rejected(self):
        self.tamper({
            "invalid key": lambda r: entry("viewer")(r).write_text(entry("viewer")(r).read_text() + "Bogus Line\n"),
            "no field code": swap("viewer", " %f", ""),
            "terminal false": swap("tui", "Terminal=true", "Terminal=false"),
            "mimeapps removed": lambda r: (r / "xdg/config/mimeapps.list").unlink(),
            "cache removed": lambda r: (r / "xdg/data/applications/mimeinfo.cache").unlink(),
            "icon missing": lambda r: (r / ("xdg/data/icons/hicolor/48x48/apps/%s.png" % slug_of(r))).unlink(),
            "autostart removed": lambda r: (r / ("xdg/config/autostart/%s-agent.desktop" % slug_of(r))).unlink(),
            "answers wrong": edit("answers.txt", "sticky_keys_key=stickykeys-enable", "sticky_keys_key=sticky"),
        })


@unittest.skipUnless(shutil.which("flatpak"), "実ツール未導入: flatpak")
class FlatpakLabTests(Base, unittest.TestCase):
    lab = LABS["flatpak"]
    lab_id = "flatpak"

    def test_tampering_rejected(self):
        self.tamper({
            "no network": edit("build/app/metadata", "shared=network;", ""),
            "override missing": lambda r: [p.unlink() for p in (r / "fpuser/overrides").iterdir()],
            "update missing": edit("update.txt", "Nothing to do", ""),
            "repo removed": lambda r: shutil.rmtree(r / "repo"),
            "installed wrong": edit("installed.txt", "local", "elsewhere"),
        })


if __name__ == "__main__":
    unittest.main()
