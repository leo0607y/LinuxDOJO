"""追加のネイティブ実習(第4群): X11/xauth、デスクトップ統合、Flatpak。"""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import zlib

from curriculum.toolbox_labs import add, put, read, require, run, remember, fixture  # noqa: F401


def need_tools(*names):
    for name in names:
        require(shutil.which(name), name + " が未導入です。パッケージを入れてから再開します。")


def kv_answers(root, name, expected):
    """key=value の回答ファイルを事実と照合する。"""
    got = {}
    for line in read(root, name).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            require("=" in line, name + " は key=value 形式です: " + line)
            key, value = line.split("=", 1)
            got[key.strip()] = value.strip().strip("\"'")
    for key, accepted in expected.items():
        require(key in got, name + " に " + key + " がありません。")
        accepted = accepted if isinstance(accepted, tuple) else (accepted,)
        require(got[key].lower() in [a.lower() for a in accepted], key + " の値が事実と違います: " + got[key])


# ---------------------------------------------------------------- xorg
X_SIZES = [(1152, 720), (1280, 800), (1366, 768), (1024, 768)]
X_LAYOUTS = ["fr", "de", "es", "it"]


def x_display_free(number):
    return not (Path("/tmp/.X11-unix/X%d" % number).exists() or Path("/tmp/.X%d-lock" % number).exists())


def xorg_setup(root):
    need_tools("Xvfb", "xdpyinfo", "xauth", "xhost", "xdotool", "mcookie")
    number = next(n for n in (90 + secrets.randbelow(100) for _ in range(200)) if x_display_free(n))
    width, height = X_SIZES[secrets.randbelow(len(X_SIZES))]
    spec = {"display": number, "width": width, "height": height, "depth": 24,
            "layout": X_LAYOUTS[secrets.randbelow(len(X_LAYOUTS))]}
    put(root, "spec.json", json.dumps(spec, indent=1) + "\n")
    remember(root, spec, ["spec.json"])


def x_env(root, number, auth):
    env = dict(os.environ, DISPLAY=":%d" % number, LC_ALL="C", XAUTHORITY=str(auth))
    env.pop("WAYLAND_DISPLAY", None)
    return env


def x_client(root, number, auth, *command):
    return subprocess.run(command, cwd=root, env=x_env(root, number, auth), text=True,
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=15)


def x_cookie(path, number):
    """Xauthority中の MIT-MAGIC-COOKIE-1 の16進値を実 xauth で読む。"""
    result = subprocess.run(["xauth", "-f", str(path), "list"], text=True, capture_output=True,
                            env=dict(os.environ, LC_ALL="C"), timeout=15)
    require(result.returncode == 0, str(path.name) + " を xauth で読めません。")
    cookies = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].endswith(":%d" % number) and parts[1] == "MIT-MAGIC-COOKIE-1":
            cookies.append(parts[2])
    return cookies


def parse_xorg_conf(text):
    sections = []
    current = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r'Section\s+"(\w+)"', line)
        if match:
            require(current is None, "Section が入れ子です(%d行目)。" % number)
            current = {"name": match.group(1), "options": {}, "keys": {}}
            continue
        if line == "EndSection":
            require(current is not None, "対応しない EndSection です(%d行目)。" % number)
            sections.append(current)
            current = None
            continue
        require(current is not None, "Section の外に記述があります(%d行目)。" % number)
        match = re.fullmatch(r'Option\s+"([^"]+)"\s+"([^"]*)"', line)
        if match:
            current["options"][match.group(1)] = match.group(2)
            continue
        match = re.fullmatch(r'(Identifier|Match\w+|Driver)\s+"([^"]*)"', line)
        require(match, "xorg.conf の書式として解釈できません(%d行目): %s" % (number, line))
        current["keys"][match.group(1)] = match.group(2)
    require(current is None, "EndSection が足りません。")
    return sections


def xorg_check(root):
    spec = fixture(root)
    number = spec["display"]
    # 設定スニペット(構造を構文解析で判定。Xorg本体の-configは特権が要るため使わない)
    conf = root / "xorg.conf.d"
    files = sorted(conf.glob("*.conf")) if conf.is_dir() else []
    require(files, "xorg.conf.d/ に NN-名前.conf を置きます。")
    require(all(re.fullmatch(r"\d\d-[\w.-]+\.conf", f.name) for f in files), "ファイル名は 90-dojo.conf のように NN-名前.conf にします。")
    sections = [s for f in files for s in parse_xorg_conf(f.read_text(encoding="utf-8"))]
    inputs = [s for s in sections if s["name"] == "InputClass"]
    require(len(inputs) == 1 and inputs[0]["keys"].get("Identifier"), "InputClass を1つ、Identifier付きで書きます。")
    cls = inputs[0]
    require(cls["keys"].get("MatchIsKeyboard", "").lower() in ("on", "yes", "true", "1"), "キーボードだけに効くよう MatchIsKeyboard \"on\" を指定します。")
    require(cls["options"].get("XkbLayout") == spec["layout"], "XkbLayout は spec.json の layout (%s) にします。" % spec["layout"])
    require("ctrl:nocaps" in cls["options"].get("XkbOptions", "").split(","), "XkbOptions に ctrl:nocaps を指定します。")
    flags = [s for s in sections if s["name"] == "ServerFlags"]
    require(len(flags) == 1 and flags[0]["options"].get("DontZap", "").lower() in ("on", "true", "yes", "1"), "ServerFlags に Option \"DontZap\" \"true\" を書きます。")
    if Path("/usr/share/X11/xkb/symbols").is_dir():
        require((Path("/usr/share/X11/xkb/symbols") / spec["layout"]).is_file(), "layout がXKB定義に存在しません。")
    # 回答
    kv_answers(root, "answers.txt", {
        "unix_socket_dir": "/tmp/.X11-unix",
        "tcp_port_for_this_display": str(6000 + number),
        "ssh_forward_first_display": "10",
        "ssh_trusted_forwarding_option": "-Y",
        "cookie_protocol": "MIT-MAGIC-COOKIE-1",
        "default_cookie_file": ("~/.Xauthority", "$HOME/.Xauthority"),
        "cookie_file_env": "XAUTHORITY",
        "wayland_socket_env": "WAYLAND_DISPLAY",
        "session_type_env": "XDG_SESSION_TYPE",
        "x11_compat_server_on_wayland": "Xwayland",
        "xorg_config_dir": "/etc/X11/xorg.conf.d",
    })
    # 起動スクリプトを実際に動かす
    script = root / "xstart.sh"
    text = read(root, "xstart.sh")
    require(os.access(script, os.X_OK), "xstart.sh は実行可能にします。")
    require(not re.search(r"(^|\s)-ac(\s|$)|xhost\s+\+", text), "アクセス制御の全面解除(-ac / xhost +)は禁止です。")
    require(x_display_free(number), "表示番号 :%d が使用中です。新しい演習環境で再開してください。" % number)
    proc = subprocess.Popen(["bash", str(script), str(number)], cwd=root, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                            env=dict(os.environ, LC_ALL="C"))
    try:
        sock = Path("/tmp/.X11-unix/X%d" % number)
        for _ in range(100):
            if sock.exists() or proc.poll() is not None:
                break
            time.sleep(0.1)
        require(sock.exists() and proc.poll() is None, "xstart.sh で Xvfb が起動していません。")
        auth = root / "Xauthority"
        require(auth.is_file(), "xstart.sh は ./Xauthority を作ります。")
        time.sleep(0.5)
        cookies = x_cookie(auth, number)
        require(len(cookies) == 1 and re.fullmatch(r"[0-9a-f]{32}", cookies[0]), "Xauthority に :%d 用の128bit cookie を1つ登録します。" % number)
        # cookieなしは拒否される
        denied = x_client(root, number, root / "no-such-xauthority", "xdpyinfo")
        require(denied.returncode != 0, "cookieなしで接続できています。-auth とアクセス制御を確認します。")
        wrong = root / ".wrong.xauth"
        subprocess.run(["xauth", "-f", str(wrong), "add", ":%d" % number, ".", secrets.token_hex(16)],
                       capture_output=True, timeout=15)
        try:
            require(x_client(root, number, wrong, "xdpyinfo").returncode != 0, "誤ったcookieでも接続できています。")
        finally:
            wrong.unlink(missing_ok=True)
        info = x_client(root, number, auth, "xdpyinfo")
        require(info.returncode == 0, "正しいcookieで接続できません: " + info.stderr[-200:])
        require("dimensions:    %dx%d pixels" % (spec["width"], spec["height"]) in info.stdout, "画面は spec.json の %dx%d にします。" % (spec["width"], spec["height"]))
        require(re.search(r"depth of root window:\s+%d planes" % spec["depth"], info.stdout), "色深度は24にします。")
        geo = x_client(root, number, auth, "xdotool", "getdisplaygeometry")
        require(geo.stdout.split() == [str(spec["width"]), str(spec["height"])], "xdotool の画面寸法が一致しません。")
        require(x_client(root, number, auth, "xset", "q").returncode == 0, "xset が接続できません。")
        require(x_client(root, number, auth, "xprop", "-root").returncode == 0, "xprop が接続できません。")
        require(x_client(root, number, auth, "xwininfo", "-root").returncode == 0, "xwininfo が接続できません。")
        require(x_client(root, number, auth, "xrandr").returncode == 0, "xrandr が接続できません。")
        hosts = x_client(root, number, auth, "xhost")
        require("access control enabled" in hosts.stdout, "xhost: アクセス制御が無効です(xhost + 禁止)。")
        # リモート側へ渡すcookie(ssh -X が行う extract|merge と同じ操作)
        remote = root / "remote.xauth"
        require(remote.is_file(), "remote.xauth を extract | merge で作ります。")
        require(x_cookie(remote, number) == cookies, "remote.xauth の cookie が Xauthority と一致しません。")
        got = x_client(root, number, remote, "xdpyinfo")
        require(got.returncode == 0, "remote.xauth で接続できません。")
        require(re.search(r"dimensions:\s+(\d+x\d+) pixels", read(root, "dimensions.txt")) and
                "%dx%d" % (spec["width"], spec["height"]) in read(root, "dimensions.txt"),
                "dimensions.txt に xdpyinfo の dimensions 行を記録します。")
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
        Path("/tmp/.X%d-lock" % number).unlink(missing_ok=True)


XORG_ANSWERS = '''unix_socket_dir=/tmp/.X11-unix
tcp_port_for_this_display=$((6000 + N))
ssh_forward_first_display=10
ssh_trusted_forwarding_option=-Y
cookie_protocol=MIT-MAGIC-COOKIE-1
default_cookie_file=~/.Xauthority
cookie_file_env=XAUTHORITY
wayland_socket_env=WAYLAND_DISPLAY
session_type_env=XDG_SESSION_TYPE
x11_compat_server_on_wayland=Xwayland
xorg_config_dir=/etc/X11/xorg.conf.d'''

add("xorg", "ヘッドレスX(Xvfb)を起動し、xauthのcookieでアクセスを絞る",
    "bash Xvfb xdpyinfo xauth xhost xdotool mcookie",
    "bash xvfb x11-utils xauth xdotool util-linux",
    "spec.json の display(N)・画面寸法・layout に従う。表示は必ず DISPLAY=:N を明示し、xhost + や -ac は使わない。\n"
    "1) xstart.sh(引数$1=表示番号): ./Xauthority に :$1 用の128bit cookie(mcookie)を xauth -f で登録(未登録時のみ)し、\n"
    "   exec Xvfb :$1 -screen 0 幅x高さx24 -nolisten tcp -auth \"$PWD/Xauthority\" で起動。chmod +x。\n"
    "2) 起動して xdpyinfo の dimensions 行を dimensions.txt へ。xauth -f Xauthority extract - :N | xauth -f remote.xauth merge - で\n"
    "   リモート側へ渡すcookieファイルを作る(ssh -X の仕組み)。確認後サーバーは止める。\n"
    "3) xorg.conf.d/90-dojo.conf: InputClass(Identifier, MatchIsKeyboard \"on\", XkbLayout=layout, XkbOptions=ctrl:nocaps)と\n"
    "   ServerFlags(DontZap true)。\n"
    "4) answers.txt(key=value 11行): unix_socket_dir, tcp_port_for_this_display(6000+N), ssh_forward_first_display(sshd既定の最初のDISPLAY番号),\n"
    "   ssh_trusted_forwarding_option, cookie_protocol, default_cookie_file, cookie_file_env, wayland_socket_env,\n"
    "   session_type_env, x11_compat_server_on_wayland, xorg_config_dir。\n"
    "判定はcheckがxstart.shを実際に起動し、cookieなし/誤cookieの拒否と各X11クライアントの成功を確認します。",
    xorg_setup, xorg_check,
    '''N=$(python3 -c 'import json; print(json.load(open("spec.json"))["display"])')
W=$(python3 -c 'import json; print(json.load(open("spec.json"))["width"])')
H=$(python3 -c 'import json; print(json.load(open("spec.json"))["height"])')
L=$(python3 -c 'import json; print(json.load(open("spec.json"))["layout"])')
cat > xstart.sh <<'EOS'
#!/bin/bash
set -eu
n=$1
cd "$(dirname "$0")"
spec() { python3 -c "import json; print(json.load(open('spec.json'))['$1'])"; }
if ! xauth -f Xauthority list ":$n" 2>/dev/null | grep -q MIT-MAGIC-COOKIE-1; then
  xauth -f Xauthority add ":$n" . "$(mcookie)"
fi
exec Xvfb ":$n" -screen 0 "$(spec width)x$(spec height)x24" -nolisten tcp -auth "$PWD/Xauthority"
EOS
chmod +x xstart.sh
./xstart.sh "$N" >/dev/null 2>&1 &
pid=$!
for i in $(seq 100); do [ -S /tmp/.X11-unix/X$N ] && break; sleep 0.1; done
sleep 0.5
DISPLAY=:$N XAUTHORITY=$PWD/Xauthority xdpyinfo | grep dimensions > dimensions.txt
xauth -f Xauthority extract - ":$N" | xauth -f remote.xauth merge -
kill $pid; wait $pid 2>/dev/null || true
mkdir -p xorg.conf.d
cat > xorg.conf.d/90-dojo.conf <<CONF
Section "InputClass"
    Identifier "dojo keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "$L"
    Option "XkbOptions" "ctrl:nocaps"
EndSection

Section "ServerFlags"
    Option "DontZap" "true"
EndSection
CONF
cat > answers.txt <<ANS
''' + XORG_ANSWERS.replace("$((6000 + N))", "$((6000 + N))") + '''
ANS''',
    ["printf '#!/bin/bash\\nexec Xvfb :$1 -ac\\n' > xstart.sh; chmod +x xstart.sh",
     "echo 'dimensions: 1x1 pixels' > dimensions.txt; : > remote.xauth"])


# ---------------------------------------------------------------- desktopfile
MIME_TYPES = ["text/csv", "text/markdown", "application/json", "text/x-python", "text/html", "application/xml"]


def png_bytes():
    def chunk(kind, data):
        return (len(data).to_bytes(4, "big") + kind + data +
                (zlib.crc32(kind + data) & 0xFFFFFFFF).to_bytes(4, "big"))
    raw = zlib.compress(b"\x00\xff\x00\x00\xff")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", (1).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00") +
            chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def desktop_setup(root):
    need_tools("desktop-file-validate", "xdg-mime", "update-desktop-database", "gio", "xdg-user-dirs-update", "xdg-user-dir")
    slug = "dojo" + secrets.token_hex(3)
    first, second = secrets.SystemRandom().sample(MIME_TYPES, 2)
    spec = {"slug": slug, "mime_view": first, "mime_term": second}
    for part in ("data/applications", "config/autostart", "home"):
        (root / "xdg" / part).mkdir(parents=True, exist_ok=True)
    (root / "icon.png").write_bytes(png_bytes())
    put(root, "spec.json", json.dumps(spec, indent=1) + "\n")
    remember(root, spec, ["spec.json", "icon.png"])


def xdg_env(root):
    base = root / "xdg"
    return dict(os.environ, LC_ALL="C", HOME=str(base / "home"), XDG_DATA_HOME=str(base / "data"),
                XDG_CONFIG_HOME=str(base / "config"), XDG_DATA_DIRS=str(base / "data") + ":/usr/share",
                XDG_CONFIG_DIRS="/etc/xdg")


def xdg_run(root, *command):
    result = subprocess.run(command, cwd=root, env=xdg_env(root), text=True, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=20)
    return result


def desktop_entry(root, relative):
    """.desktop を実 desktop-file-validate で検証し、[Desktop Entry] を辞書化する。"""
    text = read(root, relative)
    result = xdg_run(root, "desktop-file-validate", str(root / relative))
    require(result.returncode == 0 and not result.stdout.strip(),
            relative + " の検証に失敗: " + (result.stdout + result.stderr)[-300:])
    lines = text.splitlines()
    require(lines and lines[0].strip() == "[Desktop Entry]", relative + " は [Desktop Entry] から始めます。")
    values = {}
    for line in lines[1:]:
        if line.startswith("["):
            break
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def desktop_check(root):
    spec = fixture(root)
    slug = spec["slug"]
    data = root / "xdg/data"
    viewer = desktop_entry(root, "xdg/data/applications/%s-viewer.desktop" % slug)
    require(viewer.get("Type") == "Application" and viewer.get("Terminal", "false") == "false", "viewer は Type=Application, Terminal=false です。")
    require(re.search(r"%[fFuU]\b", viewer.get("Exec", "")), "viewer の Exec にファイル/URLのフィールドコード(%f など)が要ります。")
    require("Utility;" in viewer.get("Categories", "").split(";") or "Utility" in viewer.get("Categories", "").split(";"), "Categories に Utility を含めます。")
    require(viewer.get("Categories", "").endswith(";"), "Categories は ; で終えます。")
    require(spec["mime_view"] in viewer.get("MimeType", "").split(";"), "MimeType に " + spec["mime_view"] + " を含めます。")
    require(viewer.get("Icon") == slug, "Icon は " + slug + " (アイコンテーマ名)にします。")
    term = desktop_entry(root, "xdg/data/applications/%s-tui.desktop" % slug)
    require(term.get("Terminal") == "true", "tui は Terminal=true です。")
    require("%F" in term.get("Exec", "").split() or "%f" in term.get("Exec", "").split(), "tui の Exec に %F か %f を単独の引数で置きます。")
    require(spec["mime_term"] in term.get("MimeType", "").split(";"), "tui の MimeType に " + spec["mime_term"] + " を含めます。")
    auto = desktop_entry(root, "xdg/config/autostart/%s-agent.desktop" % slug)
    require(auto.get("Type") == "Application" and auto.get("Exec") and auto.get("X-GNOME-Autostart-enabled") == "true"
            and auto.get("Hidden", "false") == "false", "autostart は有効な Application エントリにします。")
    # アイコンテーマ
    icon = data / "icons/hicolor/48x48/apps" / (slug + ".png")
    require(icon.is_file() and icon.read_bytes() == (root / "icon.png").read_bytes(), "icon.png を hicolor/48x48/apps/%s.png へ置きます。" % slug)
    # MIME関連付け(実xdg-mime / gio)
    require(read(root, "xdg/config/mimeapps.list").lstrip().startswith(("[Default Applications]", "[")), "mimeapps.list が不正です。")
    for mime, name in ((spec["mime_view"], slug + "-viewer.desktop"), (spec["mime_term"], slug + "-tui.desktop")):
        result = xdg_run(root, "xdg-mime", "query", "default", mime)
        require(result.stdout.strip() == name, "%s の既定アプリが %s ではありません: %s" % (mime, name, result.stdout.strip()))
        listing = xdg_run(root, "gio", "mime", mime).stdout
        require(re.search(r"Default application for .*:\s*" + re.escape(name), listing), "gio mime が既定アプリを返しません。")
        require(name in listing, "gio mime の登録アプリに " + name + " がありません。")
    cache = read(root, "xdg/data/applications/mimeinfo.cache")
    require(re.search(re.escape(spec["mime_view"]) + "=.*" + slug + "-viewer.desktop", cache), "update-desktop-database で mimeinfo.cache を更新します。")
    require(re.search(re.escape(spec["mime_term"]) + "=.*" + slug + "-tui.desktop", cache), "mimeinfo.cache に tui の関連付けがありません。")
    # xdg-user-dirs
    wanted = root / "xdg/home" / ("Downloads-" + slug)
    require(wanted.is_dir(), "ダウンロード用ディレクトリ " + wanted.name + " を作ります。")
    result = xdg_run(root, "xdg-user-dir", "DOWNLOAD")
    require(Path(result.stdout.strip()) == wanted, "xdg-user-dir DOWNLOAD が " + str(wanted) + " を指していません。")
    require(not (root / "xdg/home/Downloads").exists(), "既定の Downloads を作らないようにします。")
    # アクセシビリティ回答
    kv_answers(root, "answers.txt", {
        "disable_gtk_a11y_value": "none",
        "gtk_a11y_env": "GTK_A11Y",
        "a11y_interface_schema": "org.gnome.desktop.a11y.interface",
        "high_contrast_key": "high-contrast",
        "screen_reader_schema": "org.gnome.desktop.a11y.applications",
        "screen_reader_key": "screen-reader-enabled",
        "screen_reader_program": "orca",
        "text_scale_schema": "org.gnome.desktop.interface",
        "text_scale_key": "text-scaling-factor",
        "keyboard_a11y_schema": "org.gnome.desktop.a11y.keyboard",
        "sticky_keys_key": "stickykeys-enable",
        "x11_layout_command": "setxkbmap",
        "persistent_keymap_command": "localectl",
        "console_keymap_file": "/etc/vconsole.conf",
        "xdg_dirs_config_file": "user-dirs.dirs",
    })
    schemas = subprocess.run(["gsettings", "list-schemas"], capture_output=True, text=True, timeout=15,
                             env=dict(os.environ, LC_ALL="C")).stdout.split() if shutil.which("gsettings") else []
    if "org.gnome.desktop.a11y.interface" in schemas:
        keys = subprocess.run(["gsettings", "list-keys", "org.gnome.desktop.a11y.interface"], capture_output=True,
                              text=True, timeout=15).stdout.split()
        require("high-contrast" in keys, "実環境のスキーマに high-contrast がありません。")


DESKTOP_ANSWERS = '''disable_gtk_a11y_value=none
gtk_a11y_env=GTK_A11Y
a11y_interface_schema=org.gnome.desktop.a11y.interface
high_contrast_key=high-contrast
screen_reader_schema=org.gnome.desktop.a11y.applications
screen_reader_key=screen-reader-enabled
screen_reader_program=orca
text_scale_schema=org.gnome.desktop.interface
text_scale_key=text-scaling-factor
keyboard_a11y_schema=org.gnome.desktop.a11y.keyboard
sticky_keys_key=stickykeys-enable
x11_layout_command=setxkbmap
persistent_keymap_command=localectl
console_keymap_file=/etc/vconsole.conf
xdg_dirs_config_file=user-dirs.dirs'''

add("desktopfile", "デスクトップ統合：.desktop・MIME既定アプリ・autostart・アクセシビリティ",
    "bash desktop-file-validate xdg-mime update-desktop-database gio xdg-user-dirs-update xdg-user-dir",
    "bash desktop-file-utils xdg-utils shared-mime-info libglib2.0-bin xdg-user-dirs",
    "GUIは使わず、専用のXDG領域(xdg/data=XDG_DATA_HOME, xdg/config=XDG_CONFIG_HOME, xdg/home=HOME)の中だけで作業する。\n"
    "各コマンドの前に export HOME=$PWD/xdg/home XDG_DATA_HOME=$PWD/xdg/data XDG_CONFIG_HOME=$PWD/xdg/config XDG_DATA_DIRS=$PWD/xdg/data:/usr/share LC_ALL=C。\n"
    "slug・mime_view・mime_term は spec.json。\n"
    "1) xdg/data/applications/<slug>-viewer.desktop: Type=Application, Name, Exec=(任意のコマンド) %f, Terminal=false,\n"
    "   Categories=Utility;, MimeType=<mime_view>;, Icon=<slug>。\n"
    "2) <slug>-tui.desktop: Terminal=true, Exec に %F, MimeType=<mime_term>;。\n"
    "3) xdg/config/autostart/<slug>-agent.desktop(X-GNOME-Autostart-enabled=true)。以上は desktop-file-validate が無出力で通ること。\n"
    "4) icon.png を xdg/data/icons/hicolor/48x48/apps/<slug>.png へ。\n"
    "5) xdg-mime default で viewer を mime_view、tui を mime_term の既定にし、update-desktop-database xdg/data/applications。\n"
    "6) xdg-user-dirs-update --set DOWNLOAD で xdg/home/Downloads-<slug> を既定のダウンロード先に(ディレクトリも作る)。\n"
    "7) answers.txt(key=value 15行): disable_gtk_a11y_value, gtk_a11y_env, a11y_interface_schema, high_contrast_key,\n"
    "   screen_reader_schema, screen_reader_key, screen_reader_program, text_scale_schema, text_scale_key,\n"
    "   keyboard_a11y_schema, sticky_keys_key, x11_layout_command, persistent_keymap_command, console_keymap_file, xdg_dirs_config_file。\n"
    "   (GTKのATSPI無効化値、GNOMEの高コントラスト/スクリーンリーダー/文字拡大/固定キーのgsettings名など。)",
    desktop_setup, desktop_check,
    '''S=$(python3 -c 'import json; print(json.load(open("spec.json"))["slug"])')
MV=$(python3 -c 'import json; print(json.load(open("spec.json"))["mime_view"])')
MT=$(python3 -c 'import json; print(json.load(open("spec.json"))["mime_term"])')
export HOME=$PWD/xdg/home XDG_DATA_HOME=$PWD/xdg/data XDG_CONFIG_HOME=$PWD/xdg/config XDG_DATA_DIRS=$PWD/xdg/data:/usr/share LC_ALL=C
A=xdg/data/applications
cat > $A/$S-viewer.desktop <<E
[Desktop Entry]
Type=Application
Version=1.0
Name=Dojo Viewer
Exec=/usr/bin/true %f
Terminal=false
Categories=Utility;
MimeType=$MV;
Icon=$S
E
cat > $A/$S-tui.desktop <<E
[Desktop Entry]
Type=Application
Version=1.0
Name=Dojo TUI
Exec=/usr/bin/less %F
Terminal=true
Categories=Utility;
MimeType=$MT;
E
cat > xdg/config/autostart/$S-agent.desktop <<E
[Desktop Entry]
Type=Application
Version=1.0
Name=Dojo Agent
Exec=/usr/bin/true
X-GNOME-Autostart-enabled=true
E
for f in $A/*.desktop xdg/config/autostart/*.desktop; do desktop-file-validate $f; done
mkdir -p xdg/data/icons/hicolor/48x48/apps
cp icon.png xdg/data/icons/hicolor/48x48/apps/$S.png
update-desktop-database $A
xdg-mime default $S-viewer.desktop $MV
xdg-mime default $S-tui.desktop $MT
mkdir -p xdg/home/Downloads-$S
xdg-user-dirs-update --set DOWNLOAD $HOME/Downloads-$S
cat > answers.txt <<ANS
''' + DESKTOP_ANSWERS + '''
ANS''',
    ["echo '[Desktop Entry]' > xdg/data/applications/x-viewer.desktop; echo Name=x >> xdg/data/applications/x-viewer.desktop",
     "echo 'disable_gtk_a11y_value=off' > answers.txt"])


# ---------------------------------------------------------------- flatpak
def fp_env(root, user_dir=None, **extra):
    env = dict(os.environ, LC_ALL="C", FLATPAK_USER_DIR=str(user_dir or root / "fpuser"))
    env.pop("FLATPAK_SYSTEM_DIR", None)
    env.update(extra)
    return env


def fp(root, *command, user_dir=None):
    result = subprocess.run(("flatpak",) + command, cwd=root, env=fp_env(root, user_dir), text=True,
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    return result


def flatpak_setup(root):
    need_tools("flatpak")
    arch = subprocess.run(["flatpak", "--default-arch"], capture_output=True, text=True, timeout=15).stdout.strip()
    require(arch, "flatpak のアーキテクチャを取得できません。")
    app = "org.dojo.T" + secrets.token_hex(3)
    runtime = "org.dojo.Platform"
    spec = {"app": app, "runtime": runtime, "arch": arch, "branch": "1"}
    put(root, "build/app/files/bin/hello", "#!/bin/sh\necho hello from " + app + "\n", 0o755)
    (root / "build/rt/files").mkdir(parents=True, exist_ok=True)
    (root / "build/rt/usr/bin").mkdir(parents=True, exist_ok=True)
    put(root, "build/rt/usr/bin/true", "#!/bin/sh\nexit 0\n", 0o755)
    put(root, "spec.json", json.dumps(spec, indent=1) + "\n")
    remember(root, spec, ["spec.json", "build/app/files/bin/hello"])


def flatpak_check(root):
    spec = fixture(root)
    app, rt, arch, branch = spec["app"], spec["runtime"], spec["arch"], spec["branch"]
    ref = "%s/%s/%s" % (rt, arch, branch)
    meta = read(root, "build/app/metadata")
    require(re.search(r"(?m)^\[Application\]\s*$", meta) and ("name=" + app) in meta.splitlines(), "app の metadata に [Application] と name=" + app + " が必要です。")
    require(("runtime=" + ref) in meta.splitlines() and "command=hello" in meta.splitlines(), "app の metadata に runtime=" + ref + " と command=hello が必要です。")
    require(re.search(r"(?m)^shared=network;\s*$", meta) and re.search(r"(?m)^sockets=x11;\s*$", meta), "build-finish --share=network --socket=x11 で権限を付けます。")
    require((root / "build/app/export").is_dir(), "flatpak build-finish を実行していません(export/ がありません)。")
    rmeta = read(root, "build/rt/metadata")
    require(re.search(r"(?m)^\[Runtime\]\s*$", rmeta) and ("name=" + rt) in rmeta.splitlines(), "runtime の metadata に [Runtime] と name=" + rt + " が必要です。")
    # 作ったリポジトリを使い捨てのユーザー領域で本当に追加・参照・インストールする
    require((root / "repo/summary").is_file() and (root / "repo/config").is_file(), "build-export と build-update-repo で repo/ を作ります。")
    with tempfile.TemporaryDirectory(prefix="dojo-fpcheck-") as scratch:
        scratch = Path(scratch) / "u"
        url = "file://" + str(root / "repo")
        result = fp(root, "remote-add", "--user", "--no-gpg-verify", "chk", url, user_dir=scratch)
        require(result.returncode == 0, "repo を remote-add できません: " + result.stderr[-300:])
        listing = fp(root, "remote-ls", "--user", "chk", "--columns=application,branch", user_dir=scratch).stdout
        rows = [line.split() for line in listing.splitlines()]
        require([app, branch] in rows and [rt, branch] in rows, "repo に app と runtime(ブランチ" + branch + ")をエクスポートします。")
        result = fp(root, "install", "--user", "-y", "chk", app, user_dir=scratch)
        require(result.returncode == 0, "app をインストールできません: " + result.stderr[-300:])
        info = fp(root, "info", "--user", "--show-permissions", app, user_dir=scratch).stdout
        require("shared=network;" in info and "sockets=x11;" in info, "インストールされた app に network と x11 の権限がありません。")
        installed = scratch / "app" / app / arch / branch / "active/files/bin/hello"
        require(installed.is_file() and os.access(installed, os.X_OK), "app の実体がインストールされていません。")
    # 学習者の領域(FLATPAK_USER_DIR=./fpuser)の最終状態
    user = root / "fpuser"
    require(user.is_dir() and (user / "repo").is_dir(), "FLATPAK_USER_DIR=$PWD/fpuser で操作します。")
    override = (user / "overrides" / app)
    require(override.is_file(), "flatpak override --user を実行していません。")
    text = override.read_text()
    require("sockets=!x11;" in text and "filesystems=home:ro;" in text, "override は --nosocket=x11 --filesystem=home:ro にします。")
    require(fp(root, "list", "--user", "--columns=application").stdout.strip() == "", "app と runtime をアンインストールします(--unused まで)。")
    require("local" not in fp(root, "remotes", "--user", "--columns=name").stdout.split(), "remote local を削除します。")
    for name, needles in {
        "remote-ls.txt": [app, rt],
        "installed.txt": [app, rt, "local"],
        "perms.txt": ["shared=network;", "home:ro"],
        "update.txt": ["Nothing to do"],
    }.items():
        body = read(root, name)
        for needle in needles:
            require(needle in body, name + " に " + needle + " が必要です(実コマンドの出力を保存)。")
    require("x11" not in read(root, "perms.txt").replace("!x11", ""), "perms.txt は override 後の権限(x11なし)を記録します。")
    require(re.search(r"(?m)^%s\s+%s\s+local\b" % (re.escape(app), re.escape(branch)), read(root, "installed.txt")), "installed.txt は --columns=application,branch,origin の出力です。")


add("flatpak", "Flatpak：ローカルリポジトリを作り、追加・導入・権限上書き・削除する",
    "bash flatpak",
    "bash flatpak",
    "実環境のFlatpakをユーザー領域だけで使う。export FLATPAK_USER_DIR=$PWD/fpuser LC_ALL=C。spec.json の app/runtime/arch/branch を使う。\n"
    "1) build/app/metadata を手書き: [Application] name=app, runtime=runtime/arch/branch, sdk=同じ, command=hello。\n"
    "   build/rt/metadata: [Runtime] name=runtime, runtime=…, sdk=…。flatpak build-finish build/app --share=network --socket=x11。\n"
    "2) flatpak build-export repo build/rt branch --runtime、flatpak build-export repo build/app branch、flatpak build-update-repo repo。\n"
    "3) flatpak remote-add --user --no-gpg-verify local file://$PWD/repo。flatpak remote-ls --user local --columns=application,branch,name > remote-ls.txt。\n"
    "4) flatpak install --user -y local app(runtimeは自動導入)。flatpak list --user --columns=application,branch,origin > installed.txt。\n"
    "5) flatpak override --user --nosocket=x11 --filesystem=home:ro app。flatpak info --user --show-permissions app > perms.txt。\n"
    "6) flatpak update --user -y > update.txt。flatpak uninstall --user -y app、flatpak uninstall --user --unused -y、flatpak remote-delete --user local。\n"
    "最終状態: 何も導入されず remote なし、override ファイルだけ残る。checkは作ったrepoを別の使い捨て領域で追加・導入して権限まで確認します。\n"
    "注意: flatpak run はbwrapのユーザー名前空間が使える環境のみで、この実習では使いません。",
    flatpak_setup, flatpak_check,
    '''export FLATPAK_USER_DIR=$PWD/fpuser LC_ALL=C
eval "$(python3 -c 'import json; d=json.load(open("spec.json")); print("A=%s R=%s ARCH=%s B=%s" % (d["app"], d["runtime"], d["arch"], d["branch"]))')"
printf '[Application]\\nname=%s\\nruntime=%s/%s/%s\\nsdk=%s/%s/%s\\ncommand=hello\\n' "$A" "$R" "$ARCH" "$B" "$R" "$ARCH" "$B" > build/app/metadata
printf '[Runtime]\\nname=%s\\nruntime=%s/%s/%s\\nsdk=%s/%s/%s\\n' "$R" "$R" "$ARCH" "$B" "$R" "$ARCH" "$B" > build/rt/metadata
flatpak build-finish build/app --share=network --socket=x11
flatpak build-export repo build/rt "$B" --runtime
flatpak build-export repo build/app "$B"
flatpak build-update-repo repo
flatpak remote-add --user --no-gpg-verify local "file://$PWD/repo"
flatpak remote-ls --user local --columns=application,branch,name > remote-ls.txt
flatpak install --user -y local "$A"
flatpak list --user --columns=application,branch,origin > installed.txt
flatpak override --user --nosocket=x11 --filesystem=home:ro "$A"
flatpak info --user --show-permissions "$A" > perms.txt
flatpak update --user -y > update.txt
flatpak uninstall --user -y "$A"
flatpak uninstall --user --unused -y
flatpak remote-delete --user local''',
    ["export FLATPAK_USER_DIR=$PWD/fpuser; mkdir -p repo; flatpak remote-ls --user 2>/dev/null || true; echo 'sockets=!x11;' > placeholder.txt",
     "export FLATPAK_USER_DIR=$PWD/fpuser; flatpak override --user --nosocket=x11 org.example.None; echo x > installed.txt"])
