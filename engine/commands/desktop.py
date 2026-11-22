"""デスクトップ周辺機器（Wi-Fi・Bluetooth・音声・印刷）の【模擬】コマンド。

これは模擬です。本物の無線機器・音声機器・プリンターには一切触れず、terminal.progress["desktop"] の
架空の状態だけで動きます。出力の書式は筆者の記憶にある本物のツールに寄せていますが、バージョンや
環境で違いが出ます（細かい文言は完全一致を保証しません）。模擬で課題が通っても、実機の機器を扱えた
証明にはなりません。実機では必ず自分の機器で確かめてください。

対応: nmcli / rfkill / iw / ip(link, addr) / modprobe / bluetoothctl / pactl / wpctl / amixer / aplay /
speaker-test / lpstat / lpadmin / lpoptions / lp / lpr / lpq / cancel / lprm / cupsenable / cupsdisable /
cupsaccept / cupsreject / cupsctl、および systemctl・journalctl・dmesg の該当ユニット・行。
未対応の書式は None を返し、標準の「未対応」表示になります。

課題の初期状態は step の "desktop"（下の PRESETS の名前）で選び、判定は "desktop_goal"（GOALS の名前）。
/etc/cups は読み取れないため、printers.conf と cupsd.conf の読み取り専用の写しを ~/etc-cups/ に置きます。
"""
import datetime
import hashlib
import importlib
import math
import re

# 同名コマンド（systemctl / journalctl / dmesg / ip）は、後から登録した側が先に呼ばれ、None なら前の担当へ回る。
# そのため既存の担当を先に読み込んでから登録する。
importlib.import_module("engine.commands.network")
importlib.import_module("engine.commands.services")
from engine.commands import command, on_check, on_prepare, register_package
from engine.commands import services as _sv
from engine.guided import Result, TrainingError

register_package("linux-firmware", "無線LANなどの機器が使う firmware 一式", "20240318-training")

BASE = datetime.datetime(2026, 1, 15, 9, 30, 0)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HW_MAC = "3c:21:9c:11:22:33"
BT_MAC = "00:1A:7D:DA:71:13"
ALSA_CARD = "alsa_card.pci-0000_00_1f.3"
ANALOG = "alsa_output.pci-0000_00_1f.3.analog-stereo"
HDMI = "alsa_output.pci-0000_00_1f.3.hdmi-stereo"
ANALOG_PROFILE = "output:analog-stereo+input:analog-stereo"
HDMI_PROFILE = "output:hdmi-stereo"
SIM = "（模擬）"

# ユニット: (説明, PID, 主プロセス名, コマンド, ユーザーユニットか)
UNITS = {
    "NetworkManager": ("Network Manager", 812, "NetworkManager", "/usr/sbin/NetworkManager --no-daemon", False),
    "wpa_supplicant": ("WPA supplicant", 790, "wpa_supplicant", "/sbin/wpa_supplicant -u -s -O /run/wpa_supplicant", False),
    "bluetooth": ("Bluetooth service", 905, "bluetoothd", "/usr/libexec/bluetooth/bluetoothd", False),
    "cups": ("CUPS Scheduler", 1033, "cupsd", "/usr/sbin/cupsd -l", False),
    "pipewire": ("PipeWire Multimedia Service", 1523, "pipewire", "/usr/bin/pipewire", True),
    "wireplumber": ("Multimedia Service Session Manager", 1525, "wireplumber", "/usr/bin/wireplumber", True),
    "pipewire-pulse": ("PipeWire PulseAudio", 1526, "pipewire-pulse", "/usr/bin/pipewire-pulse", True),
}


# ---------------------------------------------------------------- 状態
def _uuid(seed):
    h = hashlib.md5(seed.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _aps():
    return [
        dict(ssid="HomeNet", bssid="AA:BB:CC:00:11:01", chan=36, freq=5180, rate="540 Mbit/s", signal=78, sec="WPA2",
             psk="sakura-2026", hidden=False, pending=False, ip="192.168.1.23/24"),
        dict(ssid="Cafe-Free", bssid="AA:BB:CC:00:11:02", chan=6, freq=2437, rate="130 Mbit/s", signal=52, sec="--",
             psk=None, hidden=False, pending=False, ip="10.20.0.57/24"),
        dict(ssid="Office-Lab", bssid="AA:BB:CC:00:11:03", chan=11, freq=2462, rate="130 Mbit/s", signal=40, sec="WPA2",
             psk="lab-secret-77", hidden=False, pending=False, ip="172.16.5.9/24"),
        dict(ssid="StaffNet", bssid="AA:BB:CC:00:11:04", chan=44, freq=5220, rate="270 Mbit/s", signal=65, sec="WPA2",
             psk="staff-pass-99", hidden=True, pending=False, ip="10.30.0.12/24"),
    ]


def _profile(ssid, psk=None, priority=0, autoconnect=True, hidden=False, name=None):
    name = name or ssid
    return dict(name=name, ssid=ssid, uuid=_uuid("wifi" + name), psk=psk, autoconnect=autoconnect,
                priority=priority, hidden=hidden, type="wifi")


def _bt_devices():
    return [
        dict(mac="AA:BB:CC:DD:EE:01", name="Dojo Buds", icon="audio-headset", cls="0x00240404", kind="audio",
             known=False, paired=False, trusted=False, connected=False, in_range=True, pin=None, stale=False,
             profile_on_connect="a2dp-sink", reconnect_fix=False, connects=0),
        dict(mac="AA:BB:CC:DD:EE:02", name="K380 Keyboard", icon="input-keyboard", cls="0x002540", kind="input",
             known=False, paired=False, trusted=False, connected=False, in_range=True, pin="482910", stale=False,
             profile_on_connect="", reconnect_fix=False, connects=0),
    ]


def _printer(uri, info, location="", default_model="everywhere"):
    return dict(uri=uri, info=info, location=location, model=default_model, enabled=True, accepting=True,
                reason="", rreason="", since=0, wait=False)


def _base():
    d = {
        "t": 0, "journal": [], "dmesg": [], "cups_files": False,
        "units": {n: {"active": "active", "enabled": True, "since": "07:16:0%d" % (i % 9)} for i, n in enumerate(UNITS)},
        "wifi": {"driver": "ok", "soft": False, "hard": False, "link_up": True, "active": None, "blocked_auto": False,
                 "aps": _aps(), "profiles": []},
        "bt": {"soft": False, "hard": False, "powered": True, "scanning": False, "agent": False, "default_agent": False,
               "devices": _bt_devices()},
        "audio": {"cards": [{"id": 49, "name": ALSA_CARD, "desc": "Built-in Audio", "kind": "alsa", "mac": "",
                             "profile": ANALOG_PROFILE}],
                  "sinks": [], "cfg": {}, "ids": {}, "next": 52, "default": ANALOG, "follow_new": True,
                  "alsa": {"hw": True, "Master": {"v": 87, "mute": False}, "Speaker": {"v": 87, "mute": False}}},
        "print": {"printers": {}, "default": None, "user_default": None, "jobs": [], "history": [], "next": 12,
                  "reachable": ["ipp://192.168.1.50/ipp/print", "ipp://192.168.1.60/ipp/print"], "ctl": {"debug": 0, "share": 0}},
    }
    _rebuild(d)
    return d


def _build(name):
    d = _base()
    PRESETS[name](d)
    _rebuild(d)
    _pump(d)
    return d


def _st(terminal, create=True):
    d = terminal.progress.get("desktop")
    if not isinstance(d, dict) or "wifi" not in d:
        if not create:
            return None
        d = terminal.progress["desktop"] = _base()
    return d


def _now(d, extra=0):
    return BASE + datetime.timedelta(seconds=7 * d["t"] + extra)


def _tick(d):
    d["t"] += 1


def _log(d, unit, prio, ident, pid, text):
    _tick(d)
    d["journal"].append([_now(d).strftime("%Y-%m-%d %H:%M:%S"), unit, prio, ident, pid, text])


def _epoch(d):
    return 1768437000 + 7 * d["t"] + 0.1234


def _nm(d, prio, text, level="info"):
    _log(d, "NetworkManager", prio, "NetworkManager", 812, f"<{level}>  [{_epoch(d):.4f}] {text}")


def _wpa(d, prio, text):
    _log(d, "wpa_supplicant", prio, "wpa_supplicant", 790, text)


BOOT = [
    ("NetworkManager", 6, "systemd", 1, "Started NetworkManager.service - Network Manager."),
    ("wpa_supplicant", 6, "systemd", 1, "Started wpa_supplicant.service - WPA supplicant."),
    ("bluetooth", 6, "systemd", 1, "Started bluetooth.service - Bluetooth service."),
    ("bluetooth", 6, "bluetoothd", 905, "Bluetooth management interface 1.22 initialized"),
    ("cups", 6, "systemd", 1, "Started cups.service - CUPS Scheduler."),
]


def _journal_rows(d):
    rows = [["2026-01-15 07:16:0%d" % (i + 3), u, p, ident, pid, text] for i, (u, p, ident, pid, text) in enumerate(BOOT)]
    return rows + d["journal"]


# ---------------------------------------------------------------- 表の整形・略称
def _table(headers, rows, fields=None):
    if fields:
        wanted = [f.strip().upper() for f in fields.split(",")]
        if any(w not in headers for w in wanted):
            return None
        idx = [headers.index(w) for w in wanted]
        headers, rows = wanted, [[r[i] for i in idx] for r in rows]
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    return "\n".join("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in cells)


def _abbr(word, options):
    hits = [o for o in options if o.startswith(word)]
    if word in options:
        return word
    return hits[0] if len(hits) == 1 else None


def _admin_needed(prog):
    return Result(f"{prog}: Forbidden", 1)


# ---------------------------------------------------------------- Wi-Fi の判定
def _unit_on(d, name):
    return d["units"][name]["active"] == "active"


def _wifi_block(d):
    w = d["wifi"]
    if w["driver"] != "ok":
        return "nodev"
    if not _unit_on(d, "NetworkManager"):
        return "nonm"
    if w["hard"] or w["soft"]:
        return "blocked"
    if not _unit_on(d, "wpa_supplicant"):
        return "nowpa"
    if not w["link_up"]:
        return "down"
    return None


def _ap_find(d, ssid, hidden_ok=False):
    for ap in d["wifi"]["aps"]:
        if ap["pending"] or ap["ssid"] != ssid:
            continue
        if ap["hidden"] and not hidden_ok:
            continue
        return ap
    return None


def _prof(d, name):
    return next((p for p in d["wifi"]["profiles"] if p["name"] == name), None)


def _activate(d, prof, ap):
    """成功なら True。パスフレーズ違いなら失敗の記録を残して False。"""
    w = d["wifi"]
    ok = ap["psk"] is None or prof["psk"] == ap["psk"]
    _nm(d, 6, "device (wlan0): Activation: starting connection '%s' (%s)" % (prof["name"], prof["uuid"]))
    _wpa(d, 6, f"wlan0: SME: Trying to authenticate with {ap['bssid'].lower()} (SSID='{ap['ssid']}' freq={ap['freq']} MHz)")
    if not ok:
        _wpa(d, 4, "wlan0: WPA: 4-Way Handshake failed - pre-shared key may be incorrect")
        _wpa(d, 4, f"wlan0: CTRL-EVENT-SSID-TEMP-DISABLED id=0 ssid=\"{ap['ssid']}\" auth_failures=1 duration=10 reason=WRONG_KEY")
        _nm(d, 4, f"device (wlan0): Activation: (wifi) access point '{prof['name']}' has security, but secrets are required.", "warn")
        _nm(d, 4, "device (wlan0): state change: need-auth -> failed (reason 'no-secrets', sys-iface-state: 'managed')", "warn")
        w["active"] = None
        return False
    _wpa(d, 6, f"wlan0: CTRL-EVENT-CONNECTED - Connection to {ap['bssid'].lower()} completed [id=0 id_str=]")
    _nm(d, 6, "device (wlan0): state change: ip-config -> activated (reason 'none', sys-iface-state: 'managed')")
    w["active"] = prof["name"]
    return True


def _ap_for(d, prof):
    return _ap_find(d, prof["ssid"], prof["hidden"])


def _autoconnect(d, exclude=()):
    w = d["wifi"]
    if _wifi_block(d) or w["active"] or w["blocked_auto"]:
        return
    cands = [p for p in w["profiles"] if p["type"] == "wifi" and p["autoconnect"] and p["name"] not in exclude
             and _ap_for(d, p)]
    for prof in sorted(cands, key=lambda p: -p["priority"]):
        if _activate(d, prof, _ap_for(d, prof)):
            return


def _wifi_refresh(d, exclude=()):
    w = d["wifi"]
    if _wifi_block(d) and w["active"]:
        _nm(d, 6, "device (wlan0): state change: activated -> unavailable (reason 'none', sys-iface-state: 'managed')")
        w["active"] = None
    _autoconnect(d, exclude)


def _dev_state(d):
    block = _wifi_block(d)
    if block:
        return "unavailable"
    return "connected" if d["wifi"]["active"] else "disconnected"


def _bars(sig):
    return "▂▄▆█" if sig >= 75 else "▂▄▆_" if sig >= 55 else "▂▄__" if sig >= 35 else "▂___"


# ---------------------------------------------------------------- nmcli
_NM_OBJS = ["general", "networking", "radio", "connection", "device", "agent", "monitor"]
_NM_NOT_RUNNING = Result("Error: NetworkManager is not running.", 8)


@command("nmcli")
def nmcli(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    args, fields = list(rest), None
    while args and args[0].startswith("-"):
        if args[0] in ("-f", "--fields") and len(args) > 1:
            fields = args[1]
            args = args[2:]
        else:
            return None
    if not args:
        return None
    obj = _abbr(args[0], _NM_OBJS)
    if obj is None:
        return None
    if not _unit_on(d, "NetworkManager"):
        return _NM_NOT_RUNNING
    sub = args[1:]
    out = {"general": _nm_general, "radio": _nm_radio, "connection": _nm_connection, "device": _nm_device}.get(obj)
    if out is None:
        return None
    return out(terminal, d, sub, fields)


def _nm_general(terminal, d, sub, fields):
    if sub and _abbr(sub[0], ["status"]) != "status":
        return None
    block = _wifi_block(d)
    w = d["wifi"]
    eth_up = False
    state = "connected" if w["active"] else "disconnected"
    conn = "full" if w["active"] else "none"
    table = _table(["STATE", "CONNECTIVITY", "WIFI-HW", "WIFI", "WWAN-HW", "WWAN"],
                   [[state if not eth_up else "connected", conn, "disabled" if w["hard"] else "enabled",
                     "disabled" if (w["soft"] or w["hard"]) else "enabled", "enabled", "enabled"]], fields)
    return Result(table) if table else None


def _nm_radio(terminal, d, sub, fields):
    w = d["wifi"]
    if not sub or sub[0] == "all":
        if len(sub) > 1:
            return None
        return Result(_table(["WIFI-HW", "WIFI", "WWAN-HW", "WWAN"],
                             [["disabled" if w["hard"] else "enabled", "disabled" if (w["soft"] or w["hard"]) else "enabled",
                               "enabled", "enabled"]]))
    if sub[0] != "wifi":
        return None
    if len(sub) == 1:
        return Result("disabled" if (w["soft"] or w["hard"]) else "enabled")
    if sub[1] not in ("on", "off") or len(sub) > 2:
        return None
    if sub[1] == "off":
        w["soft"] = True
        _nm(d, 6, "manager: rfkill: Wi-Fi now disabled by radio killswitch")
    else:
        w["soft"] = False
        _nm(d, 6, "manager: rfkill: Wi-Fi hardware radio set enabled")
    _wifi_refresh(d)
    return Result()


def _conn_rows(d):
    w = d["wifi"]
    rows = []
    for p in w["profiles"]:
        rows.append([p["name"], p["uuid"], "wifi", "wlan0" if w["active"] == p["name"] else "--",
                     "yes" if p["autoconnect"] else "no", str(p["priority"])])
    rows.append(["Wired connection 1", _uuid("eth"), "ethernet", "--", "yes", "-999"])
    return rows


def _nm_connection(terminal, d, sub, fields):
    w = d["wifi"]
    act = _abbr(sub[0], ["show", "up", "down", "delete", "modify", "add"]) if sub else "show"
    if act == "show":
        names = sub[1:]
        if "--active" in names or "-a" in names:
            rows = [r for r in _conn_rows(d) if r[3] != "--"]
            names = []
        else:
            rows = _conn_rows(d)
        if names:
            if len(names) != 1:
                return None
            return _nm_show(d, names[0])
        headers = ["NAME", "UUID", "TYPE", "DEVICE", "AUTOCONNECT", "AUTOCONNECT-PRIORITY"]
        default_fields = "NAME,UUID,TYPE,DEVICE" if not fields else fields
        text = _table(headers, rows, default_fields)
        return Result(text) if text else None
    if act in ("up", "down", "delete"):
        names = [a for a in sub[1:] if a != "id"]
        if len(names) != 1:
            return None
        name = names[0]
        prof = _prof(d, name)
        if prof is None:
            if act == "delete":
                return Result(f"Error: unknown connection '{name}'.\nError: not all connections deleted.", 10)
            if act == "down":
                return Result(f"Error: '{name}' is not an active connection.\nError: no active connection provided.", 10)
            return Result(f"Error: unknown connection '{name}'.", 10)
        if act == "delete":
            if w["active"] == name:
                w["active"] = None
            w["profiles"].remove(prof)
            _nm(d, 6, f"settings: connection '{name}' ({prof['uuid']}): deleted")
            return Result(f"Connection '{name}' ({prof['uuid']}) successfully deleted.")
        if act == "down":
            if w["active"] != name:
                return Result(f"Error: '{name}' is not an active connection.\nError: no active connection provided.", 10)
            w["active"] = None
            _nm(d, 6, "device (wlan0): state change: activated -> disconnected (reason 'user-requested', sys-iface-state: 'managed')")
            _autoconnect(d, exclude=(name,))
            return Result(f"Connection '{name}' successfully deactivated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/3)")
        block = _wifi_block(d)
        if block:
            return Result("Error: Connection activation failed: No suitable device found for this connection "
                          "(device wlan0 not available because device is not available).", 4)
        ap = _ap_for(d, prof)
        if ap is None:
            return Result("Error: Connection activation failed: The Wi-Fi network could not be found.", 4)
        if _activate(d, prof, ap):
            return Result("Connection successfully activated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/4)")
        return Result("Error: Connection activation failed: (7) Secrets were required, but not provided.", 4)
    if act == "modify":
        if len(sub) < 4 or len(sub) % 2:
            return None
        prof = _prof(d, sub[1])
        if prof is None:
            return Result(f"Error: unknown connection '{sub[1]}'.", 10)
        for key, value in zip(sub[2::2], sub[3::2]):
            err = _set_prop(prof, key, value)
            if err is None:
                return None
            if err:
                return err
        _nm(d, 6, f"settings: connection '{prof['name']}' ({prof['uuid']}): updated")
        return Result()
    if act == "add":
        return _nm_add(d, sub[1:])
    return None


_ALIAS = {"wifi-sec.": "802-11-wireless-security.", "wifi.": "802-11-wireless."}


def _norm_key(key):
    for short, full in _ALIAS.items():
        if key.startswith(short):
            return full + key[len(short):]
    return key


def _yes(value):
    return value.lower() in ("yes", "true", "on", "1")


def _set_prop(prof, key, value):
    key = _norm_key(key)
    if key == "connection.autoconnect":
        if value.lower() not in ("yes", "no", "true", "false", "on", "off", "1", "0"):
            return Result(f"Error: failed to modify connection.autoconnect: '{value}' is not a valid boolean.", 2)
        prof["autoconnect"] = _yes(value)
    elif key == "connection.autoconnect-priority":
        try:
            prof["priority"] = int(value)
        except ValueError:
            return Result(f"Error: failed to modify connection.autoconnect-priority: '{value}' is not a valid number.", 2)
    elif key == "802-11-wireless-security.psk":
        prof["psk"] = value
    elif key == "802-11-wireless.hidden":
        prof["hidden"] = _yes(value)
    elif key == "802-11-wireless-security.key-mgmt":
        pass
    else:
        return None
    return ""


def _nm_add(d, args):
    opts = dict(zip(args[0::2], args[1::2]))
    if len(args) % 2 or opts.get("type") != "wifi":
        return None
    name, ssid = opts.get("con-name") or opts.get("ssid"), opts.get("ssid")
    if not name or not ssid:
        return Result("Error: ssid: property is missing.", 2)
    prof = _profile(ssid, name=name)
    for key, value in opts.items():
        if key in ("type", "con-name", "ssid", "ifname"):
            continue
        err = _set_prop(prof, key, value)
        if err is None:
            return None
        if err:
            return err
    d["wifi"]["profiles"].append(prof)
    _nm(d, 6, f"settings: connection '{name}' ({prof['uuid']}): added")
    return Result(f"Connection '{name}' ({prof['uuid']}) successfully added.")


def _nm_show(d, name):
    prof = _prof(d, name)
    if prof is None:
        return Result(f"Error: {name} - no such connection profile.", 10)
    w = d["wifi"]
    rows = [("connection.id", prof["name"]), ("connection.uuid", prof["uuid"]), ("connection.type", "802-11-wireless"),
            ("connection.interface-name", "--"), ("connection.autoconnect", "yes" if prof["autoconnect"] else "no"),
            ("connection.autoconnect-priority", prof["priority"]), ("802-11-wireless.ssid", prof["ssid"]),
            ("802-11-wireless.mode", "infrastructure"), ("802-11-wireless.hidden", "yes" if prof["hidden"] else "no"),
            ("802-11-wireless-security.key-mgmt", "wpa-psk" if prof["psk"] else "--"),
            ("802-11-wireless-security.psk", "<hidden>" if prof["psk"] else "--"), ("ipv4.method", "auto")]
    if w["active"] == name:
        ap = _ap_for(d, prof)
        rows += [("GENERAL.STATE", "activated"), ("GENERAL.DEVICES", "wlan0"), ("IP4.ADDRESS[1]", ap["ip"] if ap else "--")]
    return Result("\n".join(f"{k + ':':<40}{v}" for k, v in rows))


def _wifi_list_rows(d):
    w = d["wifi"]
    rows = []
    active = _prof(d, w["active"]) if w["active"] else None
    for ap in sorted([a for a in w["aps"] if not a["pending"]], key=lambda a: -a["signal"]):
        used = "*" if active and active["ssid"] == ap["ssid"] else ""
        rows.append([used, ap["bssid"], "--" if ap["hidden"] else ap["ssid"], "Infra", str(ap["chan"]), ap["rate"],
                     str(ap["signal"]), _bars(ap["signal"]), ap["sec"]])
    return rows


def _nm_device(terminal, d, sub, fields):
    w = d["wifi"]
    act = _abbr(sub[0], ["status", "show", "connect", "disconnect", "wifi"]) if sub else "status"
    if act == "status":
        rows = []
        if w["driver"] == "ok":
            rows.append(["wlan0", "wifi", _dev_state(d), w["active"] or "--"])
        rows.append(["enp3s0", "ethernet", "unavailable", "--"])
        if w["driver"] == "ok":
            rows.append(["p2p-dev-wlan0", "wifi-p2p", "disconnected" if not _wifi_block(d) else "unavailable", "--"])
        rows.append(["lo", "loopback", "unmanaged", "--"])
        text = _table(["DEVICE", "TYPE", "STATE", "CONNECTION"], rows, fields)
        return Result(text) if text else None
    if act in ("connect", "disconnect"):
        if sub[1:] != ["wlan0"]:
            return None
        if w["driver"] != "ok":
            return Result(f"Error: Device 'wlan0' not found.", 10)
        if act == "disconnect":
            if not w["active"]:
                return Result("Error: Device 'wlan0' is not active.", 6)
            w["active"], w["blocked_auto"] = None, True
            return Result("Device 'wlan0' successfully disconnected.")
        if _wifi_block(d):
            return Result("Error: Connection activation failed: No suitable device found for this connection "
                          "(device wlan0 not available because device is not available).", 4)
        w["blocked_auto"] = False
        _autoconnect(d)
        if not w["active"]:
            return Result("Error: Connection activation failed: No suitable device found for this connection (profile is not compatible).", 4)
        return Result(f"Device 'wlan0' successfully activated with '{_prof(d, w['active'])['uuid']}'.")
    if act == "wifi":
        return _nm_wifi(d, sub[1:], fields)
    return None


def _nm_wifi(d, sub, fields):
    w = d["wifi"]
    act = _abbr(sub[0], ["list", "rescan", "connect"]) if sub else "list"
    if act is None:
        return None
    if w["driver"] != "ok":
        return Result("Error: No Wi-Fi device found.", 10)
    if act == "list":
        extra = sub[1:] if sub else []
        if extra and not (len(extra) == 2 and extra[0] == "ifname" and extra[1] == "wlan0"):
            return None
        if _wifi_block(d):
            return Result("")
        text = _table(["IN-USE", "BSSID", "SSID", "MODE", "CHAN", "RATE", "SIGNAL", "BARS", "SECURITY"], _wifi_list_rows(d), fields)
        return Result(text) if text else None
    if act == "rescan":
        extra = sub[1:]
        if extra and extra != ["ifname", "wlan0"]:
            return None
        if _wifi_block(d):
            return Result("Error: Failed to request scan: Scanning not allowed while unavailable", 1)
        for ap in w["aps"]:
            ap["pending"] = False
        _nm(d, 6, "device (wlan0): supplicant interface state: scan completed")
        return Result()
    return _wifi_connect(d, sub[1:])


def _wifi_connect(d, args):
    if not args:
        return None
    ssid, opts = args[0], {}
    rest = args[1:]
    if len(rest) % 2:
        return None
    for key, value in zip(rest[0::2], rest[1::2]):
        if key not in ("password", "ifname", "name", "hidden", "private", "bssid"):
            return None
        opts[key] = value
    hidden = _yes(opts.get("hidden", "no"))
    w = d["wifi"]
    ap = None if _wifi_block(d) else _ap_find(d, ssid, hidden)
    if ap is None:
        return Result(f"Error: No network with SSID '{ssid}' found.", 10)
    password = opts.get("password")
    if password is not None and ap["sec"] != "--" and not 8 <= len(password) <= 63:
        return Result("Error: Failed to add/activate new connection: Connection.802-11-wireless-security.psk: property is invalid", 1)
    prof = next((p for p in w["profiles"] if p["ssid"] == ssid), None)
    if prof is None:
        prof = _profile(ssid, name=opts.get("name"), hidden=hidden)
        w["profiles"].append(prof)
    if password is not None:
        prof["psk"] = password
    if hidden:
        prof["hidden"] = True
    w["blocked_auto"] = False
    if _activate(d, prof, ap):
        return Result(f"Device 'wlan0' successfully activated with '{prof['uuid']}'.")
    return Result("Error: Connection activation failed: (7) Secrets were required, but not provided.", 4)


# ---------------------------------------------------------------- rfkill / iw / ip / modprobe
def _rfkill_items(d):
    items = []
    if d["wifi"]["driver"] == "ok":
        items.append(("phy0", "Wireless LAN", "wifi", d["wifi"]))
    items.append(("hci0", "Bluetooth", "bluetooth", d["bt"]))
    return items


@command("rfkill", sudo=True)
def rfkill(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    act = rest[0] if rest else "list"
    items = _rfkill_items(d)
    if act == "list":
        sel = rest[1:]
        if len(sel) > 1:
            return None
        lines = []
        for i, (name, desc, kind, state) in enumerate(items):
            if sel and sel[0] not in (kind, str(i), "all"):
                continue
            lines += [f"{i}: {name}: {desc}", f"\tSoft blocked: {'yes' if state['soft'] else 'no'}",
                      f"\tHard blocked: {'yes' if state['hard'] else 'no'}"]
        return Result("\n".join(lines))
    if act in ("block", "unblock") and len(rest) == 2:
        hit = [(i, it) for i, it in enumerate(items) if rest[1] in (it[2], str(i), "all")]
        if not hit:
            return Result(f"rfkill: invalid identifier: {rest[1]}", 1)
        for _, (name, desc, kind, state) in hit:
            state["soft"] = act == "block"
            if kind == "bluetooth":
                if act == "block":
                    state["powered"], state["scanning"] = False, False
                    _bt_drop_connections(d)
        if act == "unblock":
            _wifi_refresh(d)
        else:
            _wifi_refresh(d)
        return Result()
    return None


@command("iw", sudo=True)
def iw(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    w = d["wifi"]
    if rest == ["dev"]:
        if w["driver"] != "ok":
            return Result("")
        return Result(f"phy#0\n\tInterface wlan0\n\t\tifindex 3\n\t\twdev 0x1\n\t\taddr {HW_MAC}\n\t\ttype managed\n\t\ttxpower 22.00 dBm")
    if rest[:1] != ["dev"] or len(rest) < 3 or rest[1] != "wlan0":
        return None
    if w["driver"] != "ok":
        return Result("command failed: No such device (-19)", 237)
    action = rest[2:]
    active = _prof(d, w["active"]) if w["active"] else None
    ap = _ap_for(d, active) if active else None
    if action == ["link"]:
        if not ap:
            return Result("Not connected.")
        return Result(f"Connected to {ap['bssid'].lower()} (on wlan0)\n\tSSID: {ap['ssid']}\n\tfreq: {ap['freq']}\n"
                      f"\tRX: 1234567 bytes (4321 packets)\n\tTX: 123456 bytes (987 packets)\n\tsignal: {ap['signal'] - 130} dBm\n"
                      "\trx bitrate: 433.3 MBit/s VHT-MCS 4 80MHz short GI VHT-NSS 2\n\ttx bitrate: 390.0 MBit/s VHT-MCS 4 80MHz VHT-NSS 2\n"
                      "\tbss flags: short-slot-time\n\tdtim period: 1\n\tbeacon int: 100")
    if action == ["info"]:
        line = f"\tssid {ap['ssid']}\n" if ap else ""
        return Result(f"Interface wlan0\n\tifindex 3\n\twdev 0x1\n\taddr {HW_MAC}\n{line}\ttype managed\n\twiphy 0\n\ttxpower 22.00 dBm")
    if action in (["scan"], ["scan", "dump"]):
        if action == ["scan"] and not admin:
            return Result("command failed: Operation not permitted (-1)", 243)
        if w["hard"] or w["soft"]:
            return Result("command failed: Operation not possible due to RF-kill (-132)", 124)
        if not w["link_up"]:
            return Result("command failed: Network is down (-100)", 156)
        out = []
        for a in w["aps"]:
            out += [f"BSS {a['bssid'].lower()}(on wlan0)", f"\tfreq: {a['freq']}", "\tbeacon interval: 100 TUs",
                    f"\tsignal: {a['signal'] - 130}.00 dBm", f"\tSSID: {'' if a['hidden'] else a['ssid']}"]
            if a["sec"] != "--":
                out.append("\tRSN:\t * Version: 1")
        return Result("\n".join(out))
    return None


def _ip_wlan(d, args, flags):
    w = d["wifi"]
    obj = args[0]
    rest = args[1:]
    if rest and rest[0] in ("show", "s", "list", "l"):
        rest = rest[1:]
    if rest and rest[0] == "dev":
        rest = rest[1:]
    if len(rest) > 1:
        return None
    want = rest[0] if rest else None
    block = _wifi_block(d)
    active = _prof(d, w["active"]) if w["active"] else None
    ap = _ap_for(d, active) if active else None
    ip_text = ap["ip"] if ap else None
    devs = [("lo", 1)]
    if want in (None, "enp3s0"):
        devs.append(("enp3s0", 2))
    if w["driver"] == "ok":
        devs.append(("wlan0", 3))
    if want:
        devs = [x for x in devs if x[0] == want]
        if not devs:
            return Result(f'Device "{want}" does not exist.', 1)
    brief = "br" in flags
    lines = []
    for name, idx in devs:
        if name == "lo":
            if brief:
                lines.append(f"{'lo':<16}{'UNKNOWN':<14}127.0.0.1/8 ::1/128")
            elif obj in ("a", "addr", "address"):
                lines += ["1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000",
                          "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00", "    inet 127.0.0.1/8 scope host lo",
                          "       valid_lft forever preferred_lft forever", "    inet6 ::1/128 scope host noprefixroute ",
                          "       valid_lft forever preferred_lft forever"]
            else:
                lines += ["1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000",
                          "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00"]
        elif name == "enp3s0":
            if brief:
                lines.append(f"{'enp3s0':<16}{'DOWN':<14}")
            else:
                lines += ["2: enp3s0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc fq_codel state DOWN mode DEFAULT group default qlen 1000",
                          "    link/ether 8c:16:45:aa:bb:cc brd ff:ff:ff:ff:ff:ff"]
        else:
            if block in ("blocked", "down", "nonm") or not w["link_up"]:
                flagtxt, state = "<BROADCAST,MULTICAST>", "DOWN"
                mode, qd = "DEFAULT", "noop"
            elif ip_text:
                flagtxt, state, mode, qd = "<BROADCAST,MULTICAST,UP,LOWER_UP>", "UP", "DORMANT", "noqueue"
            else:
                flagtxt, state, mode, qd = "<NO-CARRIER,BROADCAST,MULTICAST,UP>", "DOWN", "DORMANT", "noqueue"
            if brief:
                lines.append(f"{'wlan0':<16}{state:<14}" + (f"{ip_text} fe80::3e21:9cff:fe11:2233/64" if ip_text else ""))
            else:
                lines += [f"3: wlan0: {flagtxt} mtu 1500 qdisc {qd} state {state} mode {mode} group default qlen 1000",
                          f"    link/ether {HW_MAC} brd ff:ff:ff:ff:ff:ff"]
                if obj in ("a", "addr", "address") and ip_text:
                    base = ip_text.rsplit(".", 1)[0]
                    lines += [f"    inet {ip_text} brd {base}.255 scope global dynamic noprefixroute wlan0",
                              "       valid_lft 86389sec preferred_lft 86389sec"]
    return Result("\n".join(lines))


@command("ip", sudo=True)
def ip(terminal, rest, stdin=None, admin=False):
    d = _st(terminal, create=False)
    if d is None:
        return None
    flags, args = set(), []
    for a in rest:
        if a in ("-br", "-brief"):
            flags.add("br")
        elif a in ("-4", "-6") or a.startswith("-"):
            return None
        else:
            args.append(a)
    if len(args) >= 4 and args[0] in ("l", "link") and args[1] == "set":
        tail = args[2:]
        if tail[0] == "dev":
            tail = tail[1:]
        if len(tail) != 2 or tail[0] != "wlan0" or tail[1] not in ("up", "down"):
            return None
        w = d["wifi"]
        if w["driver"] != "ok":
            return Result('Cannot find device "wlan0"', 1)
        if not admin:
            return Result("RTNETLINK answers: Operation not permitted", 2)
        if tail[1] == "up" and (w["soft"] or w["hard"]):
            return Result("RTNETLINK answers: Operation not possible due to RF-kill", 2)
        w["link_up"] = tail[1] == "up"
        _wifi_refresh(d)
        return Result()
    if args and args[0] in ("a", "addr", "address", "l", "link"):
        if args[1:2] in (["add"], ["del"], ["set"], ["flush"]):
            return None
        return _ip_wlan(d, args, flags)
    return None


@command("modprobe", sudo=True)
def modprobe(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    remove = rest[:1] == ["-r"]
    names = rest[1:] if remove else rest
    if len(names) != 1 or names[0].startswith("-"):
        return None
    if not admin:
        return Result(f"modprobe: ERROR: could not insert '{names[0]}': Operation not permitted", 1)
    w = d["wifi"]
    if names[0] != "iwlwifi":
        return Result(f"modprobe: FATAL: Module {names[0]} not found in directory /lib/modules/6.8.0-training", 1)
    if remove:
        if w["driver"] == "none":
            return Result("modprobe: FATAL: Module iwlwifi is not currently loaded", 1)
        w["driver"], w["active"] = "none", None
        return Result()
    if w["driver"] != "none":
        return Result()
    if "linux-firmware" in terminal.progress["packages"]:
        w["driver"] = "ok"
        _wifi_refresh(d)
    else:
        w["driver"] = "nofw"
    return Result()


# ---------------------------------------------------------------- systemctl / journalctl / dmesg
def _norm_unit(text):
    return text[:-8] if text.endswith(".service") else text


def _unit_status(terminal, d, name):
    desc, pid, proc, cmd, user = UNITS[name]
    st = d["units"][name]
    root = "/usr/lib/systemd/user" if user else "/usr/lib/systemd/system"
    mark = "●" if st["active"] == "active" else "○"
    lines = [f"{mark} {name}.service - {desc}",
             f"     Loaded: loaded ({root}/{name}.service; {'enabled' if st['enabled'] else 'disabled'}; preset: enabled)"]
    if st["active"] == "active":
        lines += [f"     Active: active (running) since Thu 2026-01-15 {st['since']} JST; 2h ago", f"   Main PID: {pid} ({proc})",
                  "      Tasks: 3 (limit: 18884)", "     Memory: 7.5M",
                  f"     CGroup: {'/user.slice/user-1000.slice/user@1000.service/session.slice' if user else '/system.slice'}/{name}.service",
                  f"             └─{pid} {cmd}"]
    else:
        lines.append("     Active: inactive (dead)")
    rows = [r for r in _journal_rows(d) if r[1] == name][-6:]
    if rows:
        lines += [""] + [_sv._journal_line(terminal, r) for r in rows]
    return "\n".join(lines)


def _unit_effects(d, name, active):
    if name == "NetworkManager":
        _wifi_refresh(d)
    elif name == "wpa_supplicant":
        _wifi_refresh(d)
    elif name == "bluetooth":
        if not active:
            d["bt"]["scanning"] = False
            _bt_drop_connections(d)
        else:
            d["bt"]["powered"] = not (d["bt"]["soft"] or d["bt"]["hard"])
    elif name == "cups":
        _pump(d)
    elif name == "pipewire" and not active:
        for other in ("wireplumber", "pipewire-pulse"):
            d["units"][other]["active"] = "inactive"
    _rebuild(d)


@command("systemctl", sudo=True)
def systemctl(terminal, rest, stdin=None, admin=False):
    flags = [a for a in rest if a.startswith("-")]
    words = [a for a in rest if not a.startswith("-")]
    user = "--user" in flags
    if any(f not in ("--user", "--no-pager", "--now", "-l", "--full") for f in flags) or len(words) < 2:
        return None
    action, names = words[0], [_norm_unit(w) for w in words[1:]]
    mine = [n for n in names if n in UNITS and UNITS[n][4] == user]
    if not mine:
        if user and action in ("status", "start", "stop", "restart", "is-active", "enable", "disable"):
            return Result("\n".join(f"Unit {n}.service could not be found." for n in names), 4)
        if not user and any(n in UNITS for n in names):
            return Result("\n".join(f"Unit {n}.service could not be found." for n in names), 4)
        return None
    if len(mine) != len(names):
        return None
    d = _st(terminal)
    if action == "is-active":
        outs = [d["units"][n]["active"] for n in names]
        return Result("\n".join(outs), 0 if all(o == "active" for o in outs) else 3)
    if action == "is-enabled":
        outs = ["enabled" if d["units"][n]["enabled"] else "disabled" for n in names]
        return Result("\n".join(outs), 0 if all(o == "enabled" for o in outs) else 1)
    if action == "status":
        code = 0 if all(d["units"][n]["active"] == "active" for n in names) else 3
        return Result("\n\n".join(_unit_status(terminal, d, n) for n in names), code)
    if action not in ("start", "stop", "restart", "enable", "disable"):
        return None
    if not user and not admin:
        verb = {"enable": "enable unit", "disable": "disable unit"}.get(action, action)
        return Result(f"Failed to {verb} {names[0]}.service: Interactive authentication required.\n"
                      f"See system logs and 'systemctl status {names[0]}.service' for details.", 1)
    out = []
    for n in names:
        st = d["units"][n]
        desc = UNITS[n][0]
        if action in ("enable", "disable"):
            st["enabled"] = action == "enable"
            out.append(("Created symlink" if action == "enable" else "Removed") + f" /etc/systemd/system/multi-user.target.wants/{n}.service.")
            if "--now" not in flags:
                continue
            action_now = "start" if action == "enable" else "stop"
        else:
            action_now = action
        if action_now in ("stop", "restart") and st["active"] == "active":
            _log(d, n, 6, "systemd", 1, f"Stopping {n}.service - {desc}...")
            st["active"] = "inactive"
            _log(d, n, 6, "systemd", 1, f"Stopped {n}.service - {desc}.")
            _unit_effects(d, n, False)
        if action_now in ("start", "restart"):
            st["active"], st["since"] = "active", _now(d).strftime("%H:%M:%S")
            _log(d, n, 6, "systemd", 1, f"Started {n}.service - {desc}.")
            _unit_effects(d, n, True)
            if n == "pipewire" and action_now == "restart":
                for other in ("wireplumber", "pipewire-pulse"):
                    d["units"][other]["active"] = "active"
                _rebuild(d)
    return Result("\n".join(out))


@command("journalctl", sudo=True)
def journalctl(terminal, rest, stdin=None, admin=False):
    d = _st(terminal, create=False)
    if d is None:
        return None
    args, units, count, prio = list(rest), [], None, None
    while args:
        a = args.pop(0)
        if a in ("-u", "--unit") and args:
            units.append(_norm_unit(args.pop(0)))
        elif a in ("-n", "--lines") and args and args[0].isdigit():
            count = int(args.pop(0))
        elif a in ("-p", "--priority") and args:
            prio = _sv._parse_priority(args.pop(0))
        elif a in ("--no-pager", "-b", "-e", "-x", "-xe"):
            pass
        else:
            return None
    if not units or any(u not in UNITS or UNITS[u][4] for u in units):
        return None
    rows = [r for r in _journal_rows(d) if r[1] in units and (prio is None or r[2] <= prio)]
    if count is not None:
        rows = rows[len(rows) - count:] if count else []
    return Result("\n".join(_sv._journal_line(terminal, r) for r in rows) or "-- No entries --")


def _dmesg_rows(d):
    w = d["wifi"]
    rows = [(2.9, 6, "Bluetooth: Core ver 2.22"), (3.0, 6, "Bluetooth: HCI device and connection manager initialized")]
    if w["driver"] == "none":
        return rows
    rows.append((6.8, 6, "iwlwifi 0000:00:14.3: enabling device (0000 -> 0002)"))
    if w["driver"] == "nofw":
        rows += [(6.9, 3, "iwlwifi 0000:00:14.3: Direct firmware load for iwlwifi-cc-a0-77.ucode failed with error -2"),
                 (6.9, 3, "iwlwifi 0000:00:14.3: no suitable firmware found!")]
    else:
        rows += [(6.9, 6, "iwlwifi 0000:00:14.3: Detected Intel(R) Wi-Fi 6 AX201 160MHz, REV=0x350"),
                 (7.4, 6, "iwlwifi 0000:00:14.3: loaded firmware version 77.0 cc-a0-77.ucode op_mode iwlmvm")]
    return rows


@command("dmesg", sudo=True)
def dmesg(terminal, rest, stdin=None, admin=False):
    d = _st(terminal, create=False)
    if d is None:
        return None
    human, wanted, args = False, None, list(rest)
    while args:
        a = args.pop(0)
        if a == "-T":
            human = True
        elif a in ("-l", "--level") and args:
            wanted = {_sv._PRIORITIES[x] for x in args.pop(0).split(",") if x in _sv._PRIORITIES}
        else:
            return None
    if not admin:
        return Result("dmesg: read kernel buffer failed: Operation not permitted", 1)
    lines = []
    for sec, prio, text in sorted(list(_sv.DMESG) + _dmesg_rows(d), key=lambda r: r[0]):
        if wanted is not None and prio not in wanted:
            continue
        if human:
            when = _sv.BOOT + datetime.timedelta(seconds=int(sec))
            stamp = f"{DAYS[when.weekday()]} {MONTHS[when.month - 1]} {when.day:2d} {when:%H:%M:%S %Y}"
        else:
            stamp = f"{sec:>12.6f}"
        lines.append(f"[{stamp}] {text}")
    return Result("\n".join(lines))


# ---------------------------------------------------------------- Bluetooth
BT_PROFILES = [("a2dp-sink", "High Fidelity Playback (A2DP Sink, codec SBC)"), ("headset-head-unit", "Headset Head Unit (HSP/HFP, codec CVSD)"),
               ("off", "Off")]


def _dev(d, mac):
    return next((x for x in d["bt"]["devices"] if x["mac"].upper() == mac.upper()), None)


def _bt_drop_connections(d):
    for dev in d["bt"]["devices"]:
        if dev["connected"]:
            dev["connected"] = False
    d["audio"]["cards"] = [c for c in d["audio"]["cards"] if c["kind"] != "bluez"]
    _rebuild(d)


def _bt_cardname(dev):
    return "bluez_card." + dev["mac"].replace(":", "_")


def _bt_ready(d):
    b = d["bt"]
    if b["soft"] or b["hard"]:
        return "Blocked"
    return None if b["powered"] else "NotReady"


@command("bluetoothctl")
def bluetoothctl(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    b = d["bt"]
    args = list(rest)
    if args[:1] == ["--timeout"] and len(args) > 2 and args[1].isdigit():
        args = args[2:]
    if not args:
        return None
    sub, args = args[0], args[1:]
    if not _unit_on(d, "bluetooth"):
        return Result("Waiting to connect to bluetoothd...", 1)
    onoff = {"on": True, "off": False}
    if sub == "show" and not args:
        return Result(f"Controller {BT_MAC} (public)\n\tName: dojo-laptop\n\tAlias: dojo-laptop\n\tClass: 0x0000010c\n"
                      f"\tPowered: {'yes' if b['powered'] else 'no'}\n\tPowerState: {'on' if b['powered'] else 'off'}\n"
                      "\tDiscoverable: no\n\tPairable: yes\n\tUUID: A/V Remote Control (0000110e-0000-1000-8000-00805f9b34fb)\n"
                      f"\tModalias: usb:v1D6Bp0246d0540\n\tDiscovering: {'yes' if b['scanning'] else 'no'}")
    if sub == "power" and len(args) == 1 and args[0] in onoff:
        if args[0] == "on":
            if b["soft"] or b["hard"]:
                return Result("Failed to set power on: org.bluez.Error.Blocked", 1)
            b["powered"] = True
            return Result(f"Changing power on succeeded\n[CHG] Controller {BT_MAC} Powered: yes")
        b["powered"], b["scanning"] = False, False
        _bt_drop_connections(d)
        return Result(f"Changing power off succeeded\n[CHG] Controller {BT_MAC} Powered: no")
    if sub == "scan" and len(args) == 1 and args[0] in onoff:
        if args[0] == "off":
            b["scanning"] = False
            return Result(f"Discovery stopped\n[CHG] Controller {BT_MAC} Discovering: no")
        if _bt_ready(d):
            return Result("Failed to start discovery: org.bluez.Error.NotReady", 1)
        b["scanning"] = True
        out = ["Discovery started", f"[CHG] Controller {BT_MAC} Discovering: yes"]
        for dev in b["devices"]:
            if dev["in_range"] and not dev["known"]:
                dev["known"] = True
                out.append(f"[NEW] Device {dev['mac']} {dev['name']}")
        return Result("\n".join(out))
    if sub in ("devices", "paired-devices"):
        filt = args[0] if args else ("Paired" if sub == "paired-devices" else None)
        if len(args) > 1 or filt not in (None, "Paired", "Connected", "Trusted"):
            return None
        key = {"Paired": "paired", "Connected": "connected", "Trusted": "trusted"}.get(filt)
        return Result("\n".join(f"Device {x['mac']} {x['name']}" for x in b["devices"] if x["known"] and (key is None or x[key])))
    if sub == "agent" and len(args) == 1:
        if args[0] in ("off",):
            b["agent"], b["default_agent"] = False, False
            return Result("Agent unregistered")
        if args[0] in ("on", "KeyboardDisplay", "DisplayYesNo", "KeyboardOnly", "DisplayOnly"):
            b["agent"] = True
            return Result("Agent registered")
        return None
    if sub == "default-agent" and not args:
        if not b["agent"]:
            return Result("No agent is registered", 1)
        b["default_agent"] = True
        return Result("Default agent request successful")
    if sub not in ("info", "pair", "trust", "untrust", "connect", "disconnect", "remove") or len(args) != 1:
        return None
    dev = _dev(d, args[0])
    if dev is None or not dev["known"]:
        return Result(f"Device {args[0].upper()} not available", 1)
    mac = dev["mac"]
    if sub == "info":
        lines = [f"Device {mac} (public)", f"\tName: {dev['name']}", f"\tAlias: {dev['name']}", f"\tClass: {dev['cls']}",
                 f"\tIcon: {dev['icon']}", f"\tPaired: {'yes' if dev['paired'] else 'no'}", f"\tBonded: {'yes' if dev['paired'] else 'no'}",
                 f"\tTrusted: {'yes' if dev['trusted'] else 'no'}", "\tBlocked: no", f"\tConnected: {'yes' if dev['connected'] else 'no'}",
                 f"\tLegacyPairing: {'yes' if dev['pin'] else 'no'}"]
        lines.append("\tUUID: Audio Sink                (0000110b-0000-1000-8000-00805f9b34fb)" if dev["kind"] == "audio"
                     else "\tUUID: Human Interface Device... (00001124-0000-1000-8000-00805f9b34fb)")
        return Result("\n".join(lines))
    if sub == "remove":
        if dev["connected"]:
            dev["connected"] = False
            d["audio"]["cards"] = [c for c in d["audio"]["cards"] if c["name"] != _bt_cardname(dev)]
            _rebuild(d)
        dev.update(known=False, paired=False, trusted=False, stale=False)
        return Result(f"[DEL] Device {mac} {dev['name']}\nDevice has been removed")
    if sub in ("trust", "untrust"):
        dev["trusted"] = sub == "trust"
        word = "yes" if dev["trusted"] else "no"
        return Result(f"[CHG] Device {mac} Trusted: {word}\nChanging {mac} {sub} succeeded")
    err = _bt_ready(d)
    if err:
        return Result(f"Failed to {'pair' if sub == 'pair' else sub}: org.bluez.Error.{err}", 1)
    if sub == "pair":
        if dev["paired"]:
            return Result("Failed to pair: org.bluez.Error.AlreadyExists", 1)
        out = [f"Attempting to pair with {mac}"]
        if dev["pin"]:
            if not (b["agent"] and b["default_agent"]):
                return Result(f"{out[0]}\nFailed to pair: org.bluez.Error.AuthenticationFailed", 1)
            out += [f"[CHG] Device {mac} Connected: yes", f"[agent] Passkey: {dev['pin']}",
                    f"{SIM}相手の機器で {dev['pin']} を入力した扱いです。実機では機器側のキーボードに打ちます。"]
        else:
            out.append(f"[CHG] Device {mac} Connected: yes")
        dev["paired"] = True
        dev["connected"] = False
        out += [f"[CHG] Device {mac} Bonded: yes", f"[CHG] Device {mac} Paired: yes", "Pairing successful"]
        return Result("\n".join(out))
    if sub == "disconnect":
        if not dev["connected"]:
            return Result("Failed to disconnect: org.bluez.Error.NotConnected", 1)
        dev["connected"] = False
        d["audio"]["cards"] = [c for c in d["audio"]["cards"] if c["name"] != _bt_cardname(dev)]
        _rebuild(d)
        return Result(f"Attempting to disconnect from {mac}\nSuccessful disconnected")
    if dev["connected"]:
        return Result("Failed to connect: org.bluez.Error.AlreadyConnected", 1)
    if not dev["paired"] or dev["stale"]:
        return Result(f"Attempting to connect to {mac}\nFailed to connect: org.bluez.Error.Failed", 1)
    dev["connected"] = True
    dev["connects"] += 1
    if dev["kind"] == "audio":
        profile = "a2dp-sink" if (dev["reconnect_fix"] and dev["connects"] > 1) else dev["profile_on_connect"]
        d["audio"]["cards"].append({"id": d["audio"]["next"], "name": _bt_cardname(dev), "desc": dev["name"], "kind": "bluez",
                                    "mac": mac, "profile": profile})
        d["audio"]["next"] += 1
        _rebuild(d, new_bluez=True)
    return Result(f"Attempting to connect to {mac}\n[CHG] Device {mac} Connected: yes\nConnection successful")


# ---------------------------------------------------------------- 音声
def _card_profiles(card):
    if card["kind"] == "alsa":
        return [(ANALOG_PROFILE, "Analog Stereo Duplex"), (HDMI_PROFILE, "Digital Stereo (HDMI) Output"),
                ("HiFi", "HiFi (Speaker, HDMI)"), ("off", "Off")]
    return BT_PROFILES


def _card_sinks(card):
    prof, base = card["profile"], card["name"].split(".", 1)[1]
    if card["kind"] == "alsa":
        if prof == ANALOG_PROFILE:
            return [(ANALOG, "Built-in Audio Analog Stereo")]
        if prof == HDMI_PROFILE:
            return [(HDMI, "Built-in Audio Digital Stereo (HDMI)")]
        if prof == "HiFi":
            return [(ANALOG, "Built-in Audio Analog Stereo"), (HDMI, "Built-in Audio Digital Stereo (HDMI)")]
        return []
    return [(f"bluez_output.{base}.1", card["desc"])] if prof in ("a2dp-sink", "headset-head-unit") else []


def _audio_up(d):
    return _unit_on(d, "pipewire") and _unit_on(d, "wireplumber")


def _rebuild(d, new_bluez=False):
    a = d["audio"]
    old = {s["name"] for s in a["sinks"]}
    sinks = []
    if _audio_up(d):
        for card in a["cards"]:
            for name, desc in _card_sinks(card):
                sinks.append({"name": name, "desc": desc, "card": card["name"]})
        if not sinks:
            sinks = [{"name": "auto_null", "desc": "Dummy Output", "card": ""}]
    for s in sinks:
        if s["name"] == "auto_null":
            s["id"] = 47
        else:
            if s["name"] not in a["ids"]:
                a["ids"][s["name"]] = a["next"]
                a["next"] += 1
            s["id"] = a["ids"][s["name"]]
        a["cfg"].setdefault(s["name"], {"vol": 40, "mute": False})
    a["sinks"] = sinks
    names = [s["name"] for s in sinks]
    fresh = [s["name"] for s in sinks if s["name"] not in old and s["name"].startswith("bluez_output")]
    if new_bluez and fresh and a["follow_new"]:
        a["default"] = fresh[0]
    elif names and a["default"] not in names:
        a["default"] = names[0]


def _sink_ref(d, token):
    a = d["audio"]
    if token in ("@DEFAULT_SINK@", "@DEFAULT_AUDIO_SINK@"):
        token = a["default"]
    for s in a["sinks"]:
        if token == s["name"] or token == str(s["id"]):
            return s
    return None


def _db(pct):
    return "-inf" if pct <= 0 else f"{60 * math.log10(pct / 100):.2f}"


def _vol_text(pct):
    raw = round(pct * 65536 / 100)
    db = _db(pct)
    side = lambda n: f"{n}: {raw} / {pct:3d}% / {db} dB"
    return f"Volume: {side('front-left')},   {side('front-right')}\n        balance 0.00"


def _pulse_down():
    return Result("Connection failure: Connection refused\npa_context_connect() failed: Connection refused", 1)


def _parse_pct(value, current):
    m = re.fullmatch(r"([+-]?)(\d+)%", value)
    if m:
        n = int(m.group(2))
        return max(0, min(150, current + n if m.group(1) == "+" else current - n if m.group(1) == "-" else n))
    if re.fullmatch(r"\d+", value):
        return max(0, min(150, round(int(value) * 100 / 65536)))
    return None


@command("pactl")
def pactl(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    a = d["audio"]
    if not (_unit_on(d, "pipewire") and _unit_on(d, "pipewire-pulse")):
        return _pulse_down() if rest else None
    args = list(rest)
    if not args:
        return None
    if args[0] == "info" and len(args) == 1:
        default = a["default"] if a["sinks"] else ""
        return Result("Server String: /run/user/1000/pulse/native\nLibrary Protocol Version: 35\nServer Protocol Version: 35\n"
                      "Is Local: yes\nClient Index: 123\nTile Size: 65472\nUser Name: learner\nHost Name: dojo-laptop\n"
                      "Server Name: PulseAudio (on PipeWire 1.0.5)\nServer Version: 15.0.0\n"
                      "Default Sample Specification: float32le 2ch 48000Hz\nDefault Channel Map: front-left,front-right\n"
                      f"Default Sink: {default}\nDefault Source: alsa_input.pci-0000_00_1f.3.analog-stereo\nCookie: 3a5c:1f0b")
    if args[0] == "list":
        short = "short" in args[1:2]
        kinds = args[2:] if short else args[1:]
        if len(kinds) != 1:
            return None
        kind = kinds[0]
        if kind == "sinks" and short:
            return Result("\n".join(f"{s['id']}\t{s['name']}\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED" for s in a["sinks"]))
        if kind == "sources" and short:
            rows = [f"{s['id'] + 1}\t{s['name']}.monitor\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED" for s in a["sinks"]]
            if _audio_up(d) and any(c["profile"] == ANALOG_PROFILE for c in a["cards"]):
                rows.append("60\talsa_input.pci-0000_00_1f.3.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED")
            return Result("\n".join(rows))
        if kind == "cards" and short:
            return Result("\n".join(f"{c['id']}\t{c['name']}\t{'alsa' if c['kind'] == 'alsa' else 'bluez5'}" for c in a["cards"]))
        if kind == "cards":
            out = []
            for c in a["cards"]:
                out += [f"Card #{c['id']}", f"\tName: {c['name']}", f"\tDriver: {'alsa' if c['kind'] == 'alsa' else 'bluez5'}",
                        "\tOwner Module: n/a", "\tProperties:", f"\t\tdevice.description = \"{c['desc']}\"", "\tProfiles:"]
                for name, desc in _card_profiles(c):
                    n = len(_card_sinks({**c, "profile": name}))
                    out.append(f"\t\t{name}: {desc} (sinks: {n}, sources: {1 if 'input' in name else 0}, priority: 1000, available: yes)")
                out += [f"\tActive Profile: {c['profile']}", ""]
            return Result("\n".join(out).rstrip())
        if kind == "sinks":
            out = []
            for s in a["sinks"]:
                cfg = a["cfg"][s["name"]]
                out += [f"Sink #{s['id']}", "\tState: SUSPENDED", f"\tName: {s['name']}", f"\tDescription: {s['desc']}",
                        f"\tMute: {'yes' if cfg['mute'] else 'no'}", "\t" + _vol_text(cfg["vol"]).replace("\n", "\n\t"), ""]
            return Result("\n".join(out).rstrip())
        return None
    if args[0] == "get-default-sink" and len(args) == 1:
        return Result(a["default"] if a["sinks"] else "")
    if args[0] == "set-default-sink" and len(args) == 2:
        s = _sink_ref(d, args[1])
        if s is None:
            return Result(f"Failure: No such entity", 1)
        a["default"] = s["name"]
        return Result()
    if args[0] in ("set-sink-mute", "get-sink-mute", "set-sink-volume", "get-sink-volume") and len(args) >= 2:
        s = _sink_ref(d, args[1])
        if s is None:
            return Result("Failure: No such entity", 1)
        cfg = a["cfg"][s["name"]]
        if args[0] == "get-sink-mute" and len(args) == 2:
            return Result(f"Mute: {'yes' if cfg['mute'] else 'no'}")
        if args[0] == "get-sink-volume" and len(args) == 2:
            return Result(_vol_text(cfg["vol"]))
        if args[0] == "set-sink-mute" and len(args) == 3 and args[2] in ("0", "1", "toggle"):
            cfg["mute"] = (not cfg["mute"]) if args[2] == "toggle" else args[2] == "1"
            return Result()
        if args[0] == "set-sink-volume" and len(args) == 3:
            pct = _parse_pct(args[2], cfg["vol"])
            if pct is None:
                return None
            cfg["vol"] = pct
            return Result()
        return None
    if args[0] == "set-card-profile" and len(args) == 3:
        card = next((c for c in a["cards"] if args[1] in (c["name"], str(c["id"]))), None)
        if card is None:
            return Result("Failure: No such entity", 1)
        if args[2] not in [p for p, _ in _card_profiles(card)]:
            return Result("Failure: No such entity", 1)
        card["profile"] = args[2]
        _rebuild(d, new_bluez=card["kind"] == "bluez")
        return Result()
    return None


def _wp_node(d, token):
    return _sink_ref(d, token)


@command("wpctl")
def wpctl(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    a = d["audio"]
    if not rest:
        return None
    if not _unit_on(d, "pipewire"):
        return Result("Cannot connect to PipeWire", 1)
    if rest == ["status"]:
        lines = ["PipeWire 'pipewire-0' [1.0.5, learner@dojo-laptop, cookie:3487251]", " └─ Clients:",
                 f"        32. WirePlumber                         [1.0.5, learner@dojo-laptop, pid:1525]", "", "Audio", " ├─ Devices:"]
        for c in a["cards"] if _audio_up(d) else []:
            lines.append(f" │      {c['id']}. {c['desc']:<38} [{'alsa' if c['kind'] == 'alsa' else 'bluez5'}]")
        lines += [" │", " ├─ Sinks:"]
        for s in a["sinks"]:
            cfg = a["cfg"][s["name"]]
            mark = "*" if s["name"] == a["default"] else " "
            lines.append(f" │  {mark}   {s['id']}. {s['desc']:<38} [vol: {cfg['vol'] / 100:.2f}{' MUTED' if cfg['mute'] else ''}]")
        lines += [" │", " ├─ Sources:"]
        if _audio_up(d) and any(c["profile"] == ANALOG_PROFILE for c in a["cards"]):
            lines.append(" │  *   60. Built-in Audio Analog Stereo       [vol: 1.00]")
        lines += [" │", " ├─ Filters:", " │", " └─ Streams:", "", "Video", " ├─ Devices:", " │", " ├─ Sinks:", " │",
                  " ├─ Sources:", " │", " ├─ Filters:", " │", " └─ Streams:"]
        return Result("\n".join(lines))
    cmd, args = rest[0], rest[1:]
    if cmd == "set-default" and len(args) == 1:
        s = _wp_node(d, args[0])
        if s is None:
            return Result(f"Failed to set {args[0]} as default: Object '{args[0]}' not found", 1)
        a["default"] = s["name"]
        return Result()
    if cmd in ("get-volume", "set-volume", "set-mute") and args:
        s = _wp_node(d, args[0])
        if s is None:
            return Result(f"Object '{args[0]}' not found", 1)
        cfg = a["cfg"][s["name"]]
        if cmd == "get-volume" and len(args) == 1:
            return Result(f"Volume: {cfg['vol'] / 100:.2f}" + (" [MUTED]" if cfg["mute"] else ""))
        if cmd == "set-mute" and len(args) == 2 and args[1] in ("0", "1", "toggle"):
            cfg["mute"] = (not cfg["mute"]) if args[1] == "toggle" else args[1] == "1"
            return Result()
        if cmd == "set-volume" and len(args) == 2:
            v = args[1]
            m = re.fullmatch(r"(\d+)%([+-]?)", v)
            if m:
                n = int(m.group(1))
                cfg["vol"] = max(0, min(150, cfg["vol"] + n if m.group(2) == "+" else cfg["vol"] - n if m.group(2) == "-" else n))
                return Result()
            if re.fullmatch(r"\d+(\.\d+)?", v):
                cfg["vol"] = max(0, min(150, round(float(v) * 100)))
                return Result()
        return None
    return None


def _amix_control(d, args):
    device = None
    rest = []
    it = iter(args)
    for x in it:
        if x in ("-c", "-D", "-M"):
            nxt = next(it, None)
            if x == "-D":
                device = nxt
        elif x == "-q":
            continue
        else:
            rest.append(x)
    return device, rest


def _amix_dump(name, ctl, pulse):
    v = ctl["v"]
    if pulse:
        pct = round(v)
        return (f"Simple mixer control '{name}',0\n  Capabilities: pvolume pswitch\n  Playback channels: Front Left - Front Right\n"
                f"  Limits: Playback 0 - 65536\n  Mono:\n  Front Left: Playback {round(v * 65536 / 100)} [{pct}%] [{'off' if ctl['mute'] else 'on'}]\n"
                f"  Front Right: Playback {round(v * 65536 / 100)} [{pct}%] [{'off' if ctl['mute'] else 'on'}]")
    pct = round(v * 100 / 87)
    db = f"{(v - 87) * 0.75:.2f}dB"
    sw = "off" if ctl["mute"] else "on"
    caps = "pvolume pswitch pswitch-joined" if name == "Master" else "pvolume pswitch"
    return (f"Simple mixer control '{name}',0\n  Capabilities: {caps}\n  Playback channels: Front Left - Front Right\n"
            f"  Limits: Playback 0 - 87\n  Mono:\n  Front Left: Playback {v} [{pct}%] [{db}] [{sw}]\n"
            f"  Front Right: Playback {v} [{pct}%] [{db}] [{sw}]")


@command("amixer")
def amixer(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    device, args = _amix_control(d, rest)
    pulse = device == "pulse"
    if device not in (None, "pulse", "default", "hw:0"):
        return None
    a = d["audio"]
    if pulse and not (_unit_on(d, "pipewire") and _unit_on(d, "pipewire-pulse")):
        return Result("amixer: Mixer attach pulse error: Connection refused", 1)
    sink = _sink_ref(d, "@DEFAULT_SINK@") if pulse else None
    if pulse and sink is None:
        return Result("amixer: Mixer attach pulse error: No such device", 1)

    def control(name):
        if pulse:
            if name != "Master":
                return None
            cfg = a["cfg"][sink["name"]]
            return {"v": cfg["vol"], "mute": cfg["mute"], "_cfg": cfg}
        return a["alsa"].get(name) if name in ("Master", "Speaker") else None
    if not args:
        names = ["Master"] if pulse else ["Master", "Speaker"]
        return Result("\n".join(_amix_dump(n, control(n), pulse) for n in names))
    if args == ["scontrols"]:
        return Result("\n".join(f"Simple mixer control '{n}',0" for n in (["Master"] if pulse else ["Master", "Speaker"])))
    act = args[0]
    if act in ("get", "sget") and len(args) == 2:
        ctl = control(args[1])
        if ctl is None:
            return Result(f"amixer: Unable to find simple control '{args[1]}',0", 1)
        return Result(_amix_dump(args[1], ctl, pulse))
    if act in ("set", "sset") and len(args) >= 3:
        ctl = control(args[1])
        if ctl is None:
            return Result(f"amixer: Unable to find simple control '{args[1]}',0", 1)
        for value in args[2:]:
            if value in ("mute", "off"):
                ctl["mute"] = True
            elif value in ("unmute", "on"):
                ctl["mute"] = False
            elif value == "toggle":
                ctl["mute"] = not ctl["mute"]
            else:
                m = re.fullmatch(r"(\d+)%([+-]?)", value)
                if m:
                    n = int(m.group(1))
                    cur = ctl["v"] if pulse else round(ctl["v"] * 100 / 87)
                    pct = max(0, min(100, cur + n if m.group(2) == "+" else cur - n if m.group(2) == "-" else n))
                    ctl["v"] = pct if pulse else round(pct * 87 / 100)
                elif re.fullmatch(r"\d+", value) and not pulse:
                    ctl["v"] = max(0, min(87, int(value)))
                else:
                    return None
        if pulse:
            ctl["_cfg"]["vol"], ctl["_cfg"]["mute"] = ctl["v"], ctl["mute"]
        return Result(_amix_dump(args[1], ctl, pulse))
    return None


@command("aplay")
def aplay(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    if rest != ["-l"]:
        return None
    if not d["audio"]["alsa"]["hw"]:
        return Result("aplay: device_list:274: no soundcards found...", 1)
    return Result("**** List of PLAYBACK Hardware Devices ****\ncard 0: PCH [HDA Intel PCH], device 0: ALC3254 Analog [ALC3254 Analog]\n"
                  "  Subdevices: 1/1\n  Subdevice #0: subdevice #0\ncard 0: PCH [HDA Intel PCH], device 3: HDMI 0 [HDMI 0]\n"
                  "  Subdevices: 1/1\n  Subdevice #0: subdevice #0")


@command("speaker-test")
def speaker_test(terminal, rest, stdin=None, admin=False):
    return Result("speaker-test: この模擬環境では実際に音を出しません（拒否）。本物の PC では "
                  "speaker-test -c2 -t wav -l1 で左右のスピーカーから順に声が出ます。"
                  "模擬の設定が正しくても、実機で音が出ることの確認にはなりません。", 1)


# ---------------------------------------------------------------- 印刷 (CUPS)
def _cdate(d, t=None):
    n = _now(d) if t is None else BASE + datetime.timedelta(seconds=7 * t)
    hour = n.hour % 12 or 12
    return (f"{DAYS[n.weekday()]} {n.day:02d} {MONTHS[n.month - 1]} {n.year} "
            f"{hour:02d}:{n.minute:02d}:{n.second:02d} {'AM' if n.hour < 12 else 'PM'} JST")


def _effective_default(p):
    ud = p["user_default"]
    if ud and ud in p["printers"]:
        return ud
    return p["default"] if p["default"] in p["printers"] else None


def _pump(d):
    p = d["print"]
    for name, pr in p["printers"].items():
        jobs = [j for j in p["jobs"] if j["printer"] == name]
        pr["wait"] = False
        if not pr["enabled"] or not _unit_on(d, "cups"):
            continue
        for job in jobs:
            if pr["uri"] in p["reachable"]:
                p["jobs"].remove(job)
                p["history"].append({**job, "state": "completed"})
            else:
                pr["wait"] = True
                break


def _sync_cups(terminal, d):
    if not d.get("cups_files"):
        return
    p = d["print"]
    lines = ["# [模擬] /etc/cups/printers.conf の読み取り専用の写しです（実機の cupsd は書き換えを上書きします）",
             "# Printer configuration file for CUPS v2.4.7", "# Written by cupsd", "# DO NOT EDIT THIS FILE WHEN CUPSD IS RUNNING"]
    for name, pr in p["printers"].items():
        tag = "DefaultPrinter" if name == p["default"] else "Printer"
        lines += [f"<{tag} {name}>", f"UUID urn:uuid:{_uuid(name)}", f"Info {pr['info']}", f"Location {pr['location']}",
                  f"MakeModel {'Generic IPP Everywhere Printer' if pr['model'] == 'everywhere' else pr['model']}",
                  f"DeviceURI {pr['uri']}", f"State {'Idle' if pr['enabled'] else 'Stopped'}"]
        if not pr["enabled"]:
            lines.append(f"StateMessage {pr['reason'] or 'Paused'}")
        lines += ["StateTime 1768437000", f"Accepting {'Yes' if pr['accepting'] else 'No'}", "Shared No", "JobSheets none none",
                  "QuotaPeriod 0", "PageLimit 0", "KLimit 0", "OpPolicy default", "ErrorPolicy retry-job", f"</{tag}>"]
    conf = ("# [模擬] /etc/cups/cupsd.conf の読み取り専用の写しです\nLogLevel warn\nMaxLogSize 0\nListen localhost:631\n"
            "Listen /run/cups/cups.sock\nBrowsing No\nDefaultAuthType Basic\nWebInterface Yes\n<Location />\n  Order allow,deny\n</Location>\n"
            "<Location /admin>\n  Order allow,deny\n</Location>\n<Policy default>\n  JobPrivateAccess default\n</Policy>\n")
    for name, text in (("etc-cups/printers.conf", "\n".join(lines) + "\n"), ("etc-cups/cupsd.conf", conf)):
        try:
            path = terminal.path(name)
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                terminal.restore_file(name, text)
                terminal.set_mode(path, 0o444)
        except (OSError, TrainingError):
            pass


def _cups_off(prog):
    return Result(f"{prog}: Bad file descriptor", 1)


def _printer_names(p, names):
    return sorted(p["printers"]) if not names else names


def _split(names):
    return [n for part in names for n in part.split(",") if n]


def _lpstat_printer(d, name, pr):
    since = _cdate(d, pr["since"])
    if not pr["enabled"]:
        return f"printer {name} disabled since {since} -\n\t{pr['reason'] or 'Paused'}"
    job = next((j for j in d["print"]["jobs"] if j["printer"] == name), None)
    if pr["wait"] and job:
        return f"printer {name} now printing {name}-{job['id']}.  enabled since {since}\n\tWaiting for printer to become available."
    return f"printer {name} is idle.  enabled since {since}"


def _lpstat_accept(d, name, pr):
    since = _cdate(d, pr["since"])
    if pr["accepting"]:
        return f"{name} accepting requests since {since}"
    return f"{name} not accepting requests since {since} -\n\t{pr['rreason'] or 'Rejecting Jobs'}"


def _job_line(d, j):
    return f"{j['printer'] + '-' + str(j['id']):<22}{j['user']:<12}{j['size']:>8}   {_cdate(d, j['t'])}"


@command("lpstat")
def lpstat(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    p = d["print"]
    args, wants, hist = list(rest), [], False
    if "-W" in args:
        i = args.index("-W")
        if args[i + 1:i + 2] != ["completed"]:
            return None
        hist = True
        del args[i:i + 2]
    i = 0
    flags = []
    while i < len(args):
        a = args[i]
        if a not in ("-p", "-d", "-a", "-o", "-v", "-t", "-s", "-r"):
            return None
        names = []
        while i + 1 < len(args) and not args[i + 1].startswith("-"):
            names.append(args[i + 1])
            i += 1
        flags.append((a, _split(names)))
        i += 1
    if not flags:
        flags = [("-o", [])]
    if not _unit_on(d, "cups"):
        if flags[0][0] == "-r":
            return Result("scheduler is not running", 1)
        return _cups_off("lpstat")
    out, code = [], 0
    for flag, names in flags:
        if flag == "-t":
            flags_t = [("-r", []), ("-d", []), ("-v", []), ("-a", []), ("-p", []), ("-o", [])]
            sub = lpstat(terminal, [x for f, n in flags_t for x in ([f] + n)], stdin, admin)
            out.append(sub.output)
            continue
        if flag == "-s":
            sub = lpstat(terminal, ["-d", "-p", "-v"], stdin, admin)
            out.append(sub.output)
            continue
        if flag == "-r":
            out.append("scheduler is running")
            continue
        if flag == "-d":
            eff = _effective_default(p)
            out.append(f"system default destination: {eff}" if eff else "no system default destination")
            continue
        if flag == "-o":
            if hist:
                jobs = [j for j in p["history"] if j["state"] == "completed" and (not names or j["printer"] in names)]
            else:
                jobs = [j for j in p["jobs"] if not names or j["printer"] in names]
            out += [_job_line(d, j) for j in jobs]
            continue
        if not p["printers"]:
            out.append("lpstat: No destinations added.")
            code = 1
            continue
        bad = next((n for n in names if n not in p["printers"]), None)
        if bad:
            out.append(f'lpstat: Invalid destination name in list "{bad}"')
            code = 1
            continue
        for name in _printer_names(p, names):
            pr = p["printers"][name]
            out.append({"-p": _lpstat_printer, "-a": _lpstat_accept}.get(flag, lambda dd, n, q: f"device for {n}: {q['uri']}")(d, name, pr))
    return Result("\n".join(o for o in out if o != ""), code)


def _need_admin(admin, prog):
    return None if admin else _admin_needed(prog)


_URI_OK = ("ipp://", "ipps://", "socket://", "lpd://", "usb://", "dnssd://", "http://", "https://")
_MODELS = ("everywhere", "raw", "drv:///sample.drv/generic.ppd", "lsb/usr/cupsfilters/Generic-PDF_Printer-PDF.ppd")


@command("lpadmin", sudo=True)
def lpadmin(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    p = d["print"]
    args, name, uri, model, enable_after, enc_before = list(rest), None, None, None, False, False
    desc = loc = None
    delete = default = None
    while args:
        a = args.pop(0)
        if a == "-p" and args:
            name = args.pop(0)
        elif a == "-E":
            if name:
                enable_after = True
            else:
                enc_before = True
        elif a == "-v" and args:
            uri = args.pop(0)
        elif a == "-m" and args:
            model = args.pop(0)
        elif a == "-D" and args:
            desc = args.pop(0)
        elif a == "-L" and args:
            loc = args.pop(0)
        elif a == "-x" and args:
            delete = args.pop(0)
        elif a == "-d" and args:
            default = args.pop(0)
        elif a == "-o" and args and args[0].startswith("printer-error-policy="):
            args.pop(0)
        else:
            return None
    if not (name or delete or default):
        return None
    if not _unit_on(d, "cups"):
        return _cups_off("lpadmin")
    denied = _need_admin(admin, "lpadmin")
    if denied:
        return denied
    if delete:
        if delete not in p["printers"]:
            return Result("lpadmin: The printer or class does not exist.", 1)
        del p["printers"][delete]
        p["jobs"] = [j for j in p["jobs"] if j["printer"] != delete]
        if p["default"] == delete:
            p["default"] = None
        _log(d, "cups", 6, "cupsd", 1033, f'Printer "{delete}" deleted.')
        return _done(terminal, d)
    if default:
        if default not in p["printers"]:
            return Result("lpadmin: The printer or class does not exist.", 1)
        p["default"] = default
        return _done(terminal, d)
    notes = ""
    pr = p["printers"].get(name)
    if pr is None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            return Result("lpadmin: Printer name can only contain printable characters.", 1)
        if uri is None:
            return None
    if uri and not uri.startswith(_URI_OK):
        return Result(f'lpadmin: Bad device-uri "{uri}".', 1)
    if model and model not in _MODELS:
        return Result("lpadmin: Add-Modify-Printer failed: Bad request.", 1)
    if model == "everywhere" and uri and uri not in p["reachable"]:
        return Result(f"lpadmin: Unable to connect to printer at \"{uri}\" for driverless setup.", 1)
    if pr is None:
        pr = _printer(uri, name, "", model or "raw")
        pr.update(enabled=False, accepting=False, reason="Paused", rreason="Rejecting Jobs", since=d["t"])
        p["printers"][name] = pr
        if (model or "raw") == "raw":
            notes = "lpadmin: Raw queues are deprecated and will stop working in a future version of CUPS."
        _log(d, "cups", 6, "cupsd", 1033, f'Printer "{name}" added.')
    else:
        if uri:
            pr["uri"] = uri
        if model:
            pr["model"] = model
    if desc:
        pr["info"] = desc
    if loc:
        pr["location"] = loc
    if enable_after:
        pr.update(enabled=True, accepting=True, reason="", rreason="", since=d["t"])
    del enc_before
    return _done(terminal, d, notes)


def _done(terminal, d, text=""):
    _tick(d)
    _pump(d)
    _sync_cups(terminal, d)
    return Result(text)


@command("lpoptions")
def lpoptions(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    p = d["print"]
    if rest[:1] == ["-d"] and len(rest) == 2:
        if rest[1] not in p["printers"]:
            return Result(f'lpoptions: Unknown printer or class "{rest[1]}".', 1)
        p["user_default"] = rest[1]
        _sync_cups(terminal, d)
        return Result()
    if rest[:1] == ["-x"] and len(rest) == 2:
        if p["user_default"] == rest[1]:
            p["user_default"] = None
        return Result()
    if rest == []:
        eff = p["user_default"]
        return Result(f"Default {eff}" if eff else "")
    if rest[:1] == ["-p"] and len(rest) == 3 and rest[2] == "-l":
        if rest[1] not in p["printers"]:
            return Result(f'lpoptions: Unknown printer or class "{rest[1]}".', 1)
        return Result("PageSize/Media Size: *A4 Letter Legal\nsides/2-Sided Printing: *one-sided two-sided-long-edge two-sided-short-edge\n"
                      "number-up/Number-Up: *1 2 4 6 9 16")
    return None


_SIDES = ("one-sided", "two-sided-long-edge", "two-sided-short-edge")


def _submit(terminal, d, prog, dest, files, copies, opts, title, stdin):
    p = d["print"]
    if dest is None:
        dest = _effective_default(p)
        if dest is None:
            return Result(f"{prog}: Error - no default destination available.", 1)
    if dest not in p["printers"]:
        return Result(f"{prog}: The printer or class does not exist.", 1)
    size, label = 0, title
    if not files:
        if stdin is None:
            return None
        size, label = len(stdin.encode("utf-8")), title or "(stdin)"
    for f in files:
        try:
            path = terminal.path(f)
            size += len(path.read_bytes())
        except (OSError, TrainingError):
            return Result(f'{prog}: Error - unable to access "{f}" - No such file or directory', 1)
        label = title or f
    pr = p["printers"][dest]
    if not pr["accepting"]:
        return Result(f'{prog}: Destination "{dest}" is not accepting jobs.', 1)
    job = {"id": p["next"], "printer": dest, "user": "learner", "title": label, "size": size, "copies": copies,
           "opts": opts, "t": d["t"], "file": files[0] if files else "(stdin)"}
    p["next"] += 1
    p["jobs"].append(job)
    _done(terminal, d)
    return job


@command("lp")
def lp(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    args, dest, copies, opts, title, files = list(rest), None, 1, {}, None, []
    while args:
        a = args.pop(0)
        m = re.fullmatch(r"-([dnot])(.+)", a)
        if m and a not in ("-o",):
            args.insert(0, m.group(2))
            a = "-" + m.group(1)
        if a == "-d" and args:
            dest = args.pop(0)
        elif a == "-n" and args and args[0].isdigit() and int(args[0]) > 0:
            copies = int(args.pop(0))
        elif a == "-t" and args:
            title = args.pop(0)
        elif a == "-o" and args:
            k, _, v = args.pop(0).partition("=")
            if k == "sides" and v not in _SIDES or k not in ("sides", "media", "number-up", "fit-to-page", "orientation-requested"):
                return None
            opts[k] = v
        elif a.startswith("-"):
            return None
        else:
            files.append(a)
    if not _unit_on(d, "cups"):
        return _cups_off("lp")
    res = _submit(terminal, d, "lp", dest, files, copies, opts, title, stdin)
    if not isinstance(res, dict):
        return res
    return Result(f"request id is {res['printer']}-{res['id']} ({max(1, len(files))} file(s))")


@command("lpr")
def lpr(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    args, dest, copies, opts, title, files = list(rest), None, 1, {}, None, []
    while args:
        a = args.pop(0)
        if a == "-P" and args:
            dest = args.pop(0)
        elif a.startswith("-P") and len(a) > 2:
            dest = a[2:]
        elif a.startswith("-#") and a[2:].isdigit():
            copies = int(a[2:])
        elif a == "-#" and args and args[0].isdigit():
            copies = int(args.pop(0))
        elif a == "-T" and args:
            title = args.pop(0)
        elif a == "-o" and args:
            k, _, v = args.pop(0).partition("=")
            if k == "sides" and v not in _SIDES or k not in ("sides", "media", "number-up", "fit-to-page", "orientation-requested"):
                return None
            opts[k] = v
        elif a.startswith("-"):
            return None
        else:
            files.append(a)
    if not _unit_on(d, "cups"):
        return _cups_off("lpr")
    res = _submit(terminal, d, "lpr", dest, files, copies, opts, title, stdin)
    return Result() if isinstance(res, dict) else res


@command("lpq")
def lpq(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    p = d["print"]
    dest, args = None, list(rest)
    while args:
        a = args.pop(0)
        if a == "-P" and args:
            dest = args.pop(0)
        elif a == "-a":
            dest = dest or None
        else:
            return None
    if not _unit_on(d, "cups"):
        return _cups_off("lpq")
    dest = dest or _effective_default(p)
    if dest is None:
        return Result("lpq: Error - no default destination available.", 1)
    if dest not in p["printers"]:
        return Result(f'lpq: Unknown destination "{dest}"!', 1)
    pr = p["printers"][dest]
    jobs = [j for j in p["jobs"] if j["printer"] == dest]
    state = "is not ready" if not pr["enabled"] else ("is ready and printing" if jobs else "is ready")
    out = [f"{dest} {state}"]
    if not jobs:
        return Result("\n".join(out + ["no entries"]))
    out.append("Rank    Owner   Job     File(s)                         Total Size")
    for i, j in enumerate(jobs):
        rank = "active" if (i == 0 and pr["enabled"]) else {0: "1st", 1: "2nd", 2: "3rd"}.get(i - (0 if not pr["enabled"] else 1), f"{i + 1}th")
        out.append(f"{rank:<8}{j['user']:<8}{j['id']:<8}{j['file']:<32}{j['size']} bytes")
    return Result("\n".join(out))


def _cancel(terminal, prog, rest):
    d = _st(terminal)
    p = d["print"]
    if not _unit_on(d, "cups"):
        return _cups_off(prog)
    args = list(rest)
    if args and args[0] == "-a":
        dest = args[1] if len(args) > 1 else None
        if len(args) > 2 or (dest and dest not in p["printers"]):
            return Result(f"{prog}: The printer or class does not exist.", 1) if dest else None
        for j in [j for j in p["jobs"] if dest is None or j["printer"] == dest]:
            p["jobs"].remove(j)
            p["history"].append({**j, "state": "canceled"})
        return _done(terminal, d)
    if len(args) != 1:
        return None
    target = args[0]
    m = re.fullmatch(r"(?:(.+)-)?(\d+)", target)
    if m:
        job = next((j for j in p["jobs"] if j["id"] == int(m.group(2)) and (not m.group(1) or j["printer"] == m.group(1))), None)
        if job is None:
            return Result(f"{prog}: cancel-job failed: Job #{m.group(2)} doesn't exist.", 1)
    elif target in p["printers"]:
        job = next((j for j in p["jobs"] if j["printer"] == target), None)
        if job is None:
            return Result()
    else:
        return Result(f"{prog}: The printer or class does not exist.", 1)
    p["jobs"].remove(job)
    p["history"].append({**job, "state": "canceled"})
    return _done(terminal, d)


@command("cancel")
def cancel(terminal, rest, stdin=None, admin=False):
    return _cancel(terminal, "cancel", rest)


@command("lprm")
def lprm(terminal, rest, stdin=None, admin=False):
    return _cancel(terminal, "lprm", rest)


def _queue_ctl(terminal, prog, rest, admin, field):
    d = _st(terminal)
    p = d["print"]
    args, reason = list(rest), None
    while args and args[0].startswith("-"):
        a = args.pop(0)
        if a in ("-r", "--reason") and args:
            reason = args.pop(0)
        else:
            return None
    if len(args) != 1:
        return None
    if not _unit_on(d, "cups"):
        return _cups_off(prog)
    denied = _need_admin(admin, prog)
    if denied:
        return denied
    pr = p["printers"].get(args[0])
    if pr is None:
        return Result(f"{prog}: The printer or class does not exist.", 1)
    if field == "enable":
        pr.update(enabled=True, reason="", since=d["t"])
    elif field == "disable":
        pr.update(enabled=False, reason=reason or "Paused", since=d["t"])
    elif field == "accept":
        pr.update(accepting=True, rreason="", since=d["t"])
    else:
        pr.update(accepting=False, rreason=reason or "Rejecting Jobs", since=d["t"])
    return _done(terminal, d)


for _prog, _field in (("cupsenable", "enable"), ("cupsdisable", "disable"), ("cupsaccept", "accept"), ("cupsreject", "reject")):
    command(_prog, sudo=True)(lambda terminal, rest, stdin=None, admin=False, _p=_prog, _f=_field: _queue_ctl(terminal, _p, rest, admin, _f))


@command("cupsctl", sudo=True)
def cupsctl(terminal, rest, stdin=None, admin=False):
    d = _st(terminal)
    ctl = d["print"]["ctl"]
    if not rest:
        return Result(f"_debug_logging={ctl['debug']}\n_remote_admin=0\n_remote_any=0\n_share_printers={ctl['share']}\n_user_cancel_any=0")
    table = {"--debug-logging": ("debug", 1), "--no-debug-logging": ("debug", 0), "--share-printers": ("share", 1),
             "--no-share-printers": ("share", 0)}
    if len(rest) != 1 or rest[0] not in table:
        return None
    if not admin:
        return _admin_needed("cupsctl")
    ctl[table[rest[0]][0]] = table[rest[0]][1]
    return Result()


# ---------------------------------------------------------------- 初期状態（PRESETS）と判定（GOALS）
def _wifi_pending(d, ssids):
    for ap in d["wifi"]["aps"]:
        if ap["ssid"] in ssids:
            ap["pending"] = True


def _p_healthy(d):
    pass


def _p_wifi_blocked(d):
    d["wifi"]["soft"] = True


def _p_wifi_off_pending(d):
    d["wifi"]["soft"] = True
    _wifi_pending(d, ["Office-Lab"])


def _p_wifi_idle(d):
    pass


def _p_wifi_wrongpsk(d):
    d["wifi"]["profiles"].append(_profile("HomeNet", psk="sakura-2025"))
    _log(d, "wpa_supplicant", 4, "wpa_supplicant", 790, "wlan0: WPA: 4-Way Handshake failed - pre-shared key may be incorrect")
    _log(d, "wpa_supplicant", 4, "wpa_supplicant", 790,
         'wlan0: CTRL-EVENT-SSID-TEMP-DISABLED id=0 ssid="HomeNet" auth_failures=1 duration=10 reason=WRONG_KEY')


def _p_wifi_priority(d):
    d["wifi"]["profiles"] += [_profile("HomeNet", psk="sakura-2026", priority=0), _profile("Cafe-Free", priority=10)]
    d["wifi"]["active"] = "Cafe-Free"
    d["wifi"]["blocked_auto"] = False


def _p_wifi_nofw(d):
    d["wifi"]["driver"] = "nofw"


def _p_wifi_combo(d):
    d["wifi"]["soft"] = True
    d["units"]["wpa_supplicant"]["active"] = "inactive"
    d["wifi"]["profiles"].append(_profile("HomeNet", psk="sakura-2026"))


def _bt_blocked(d):
    d["bt"].update(soft=True, powered=False)


def _bt_off(d):
    d["bt"]["powered"] = False


def _bt_svc(d):
    d["units"]["bluetooth"]["active"] = "inactive"
    d["bt"]["powered"] = False


def _bt_noaudio(d):
    dev = d["bt"]["devices"][0]
    dev.update(known=True, paired=True, trusted=True, in_range=True, profile_on_connect="off", reconnect_fix=True)


def _bt_stale(d):
    dev = d["bt"]["devices"][0]
    dev.update(known=True, paired=True, trusted=True, stale=True)


def _a_hdmi_default(d):
    d["audio"]["cards"][0]["profile"] = "HiFi"
    d["audio"]["default"] = HDMI


def _a_muted(d):
    d["audio"]["cfg"][ANALOG] = {"vol": 40, "mute": True}


def _a_zero(d):
    d["audio"]["cfg"][ANALOG] = {"vol": 0, "mute": True}


def _a_profile_off(d):
    d["audio"]["cards"][0]["profile"] = "off"


def _a_wp_down(d):
    d["units"]["wireplumber"]["active"] = "inactive"


def _a_pulse_down(d):
    d["units"]["pipewire-pulse"]["active"] = "inactive"


def _a_alsa_muted(d):
    d["audio"]["alsa"]["Master"]["mute"] = True
    d["audio"]["alsa"]["Speaker"]["mute"] = True


def _a_dock(d):
    d["audio"]["cfg"][ANALOG] = {"vol": 25, "mute": True}
    d["audio"]["cards"][0]["profile"] = HDMI_PROFILE
    d["audio"]["default"] = HDMI


def _pr_two(d):
    p = d["print"]
    p["printers"] = {"Office-Laser": _printer("ipp://192.168.1.50/ipp/print", "Office Laser", "2F"),
                     "Photo-Inkjet": _printer("ipp://192.168.1.60/ipp/print", "Photo Inkjet", "1F")}
    p["default"] = "Photo-Inkjet"
    d["cups_files"] = True


def _job(d, printer, jid=12, title="report.txt", size=1024):
    d["print"]["jobs"].append({"id": jid, "printer": printer, "user": "learner", "title": title, "size": size, "copies": 1,
                               "opts": {}, "t": d["t"], "file": title})
    d["print"]["next"] = max(d["print"]["next"], jid + 1)


def _pr_userdef(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"
    d["print"]["user_default"] = "Photo-Inkjet"


def _pr_paused(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"
    d["print"]["printers"]["Office-Laser"].update(enabled=False, reason="Paused")
    _job(d, "Office-Laser")


def _pr_reject(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"
    d["print"]["printers"]["Office-Laser"].update(accepting=False, rreason="Rejecting Jobs")


def _pr_baduri(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"
    d["print"]["printers"]["Office-Laser"]["uri"] = "ipp://192.168.1.150/ipp/print"
    _job(d, "Office-Laser")


def _pr_empty(d):
    d["cups_files"] = True


def _pr_ok(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"


def _pr_wrongq(d):
    _pr_two(d)
    d["print"]["default"] = "Office-Laser"
    d["print"]["printers"]["Photo-Inkjet"].update(enabled=False, reason="Paused")
    _job(d, "Photo-Inkjet", 14)


PRESETS = {
    "healthy": _p_healthy, "wifi_blocked": _p_wifi_blocked, "wifi_blocked_pending": _p_wifi_off_pending,
    "wifi_idle": _p_wifi_idle, "wifi_wrongpsk": _p_wifi_wrongpsk, "wifi_priority": _p_wifi_priority,
    "wifi_nofw": _p_wifi_nofw, "wifi_combo": _p_wifi_combo, "bt_blocked": _bt_blocked, "bt_off": _bt_off,
    "bt_headset": _p_healthy, "bt_service_down": _bt_svc, "bt_keyboard": _p_healthy, "bt_noaudio": _bt_noaudio,
    "bt_stale": _bt_stale, "audio_hdmi_default": _a_hdmi_default, "audio_muted": _a_muted, "audio_zero": _a_zero,
    "audio_profile_off": _a_profile_off, "audio_wp_down": _a_wp_down, "audio_pulse_down": _a_pulse_down,
    "audio_alsa_muted": _a_alsa_muted, "audio_dock": _a_dock, "print_wrong_default": _pr_two, "print_userdef": _pr_userdef,
    "print_paused": _pr_paused, "print_reject": _pr_reject, "print_baduri": _pr_baduri, "print_empty": _pr_empty,
    "print_ok": _pr_ok, "print_wrongq": _pr_wrongq,
}


def _hist(d, **match):
    return [j for j in d["print"]["history"] if all(j.get(k) == v for k, v in match.items())]


def _default_sink(d):
    return next((s for s in d["audio"]["sinks"] if s["name"] == d["audio"]["default"]), None)


def _g_wifi_unblocked(d):
    return (not d["wifi"]["soft"], "Wi-Fi の無線がまだ止まっています（rfkill list で確認）。")


def _g_wifi_home(d):
    return (d["wifi"]["active"] == "HomeNet", "HomeNet に接続できていません。nmcli device status で確認しましょう。")


def _g_wifi_lab(d):
    return (d["wifi"]["active"] == "Office-Lab", "Office-Lab に接続できていません。")


def _g_wifi_staff(d):
    return (d["wifi"]["active"] == "StaffNet", "StaffNet に接続できていません。隠しSSIDは一覧に名前が出ません。")


def _g_wifi_priority(d):
    w = d["wifi"]
    home, cafe = _prof(d, "HomeNet"), _prof(d, "Cafe-Free")
    if w["active"] != "HomeNet":
        return False, "今の接続が HomeNet ではありません。"
    if cafe and cafe["autoconnect"] and cafe["priority"] >= home["priority"]:
        return False, "次回以降も Cafe-Free が優先されます。優先度か自動接続の設定を見直しましょう。"
    return True, ""


def _g_wifi_driver(d):
    return (d["wifi"]["driver"] == "ok", "無線LANのドライバーがまだ使えません。dmesg の firmware の行を確認しましょう。")


def _g_wifi_combo(d):
    ok = not d["wifi"]["soft"] and _unit_on(d, "wpa_supplicant") and d["wifi"]["active"] == "HomeNet"
    return ok, "ブロック解除・wpa_supplicant の起動・HomeNet への接続がそろっていません。"


def _g_bt_powered(d):
    b = d["bt"]
    return (b["powered"] and not b["soft"], "アダプターの電源が入っていません。")


def _g_bt_buds(d):
    dev = d["bt"]["devices"][0]
    return (dev["paired"] and dev["trusted"] and dev["connected"], "Dojo Buds が ペアリング・信頼・接続の3つともそろっていません。")


def _g_bt_svc_buds(d):
    ok, msg = _g_bt_buds(d)
    return (ok and _unit_on(d, "bluetooth") and d["bt"]["powered"], "サービスの起動と、Dojo Buds の接続が必要です。")


def _g_bt_kbd(d):
    dev = d["bt"]["devices"][1]
    return (dev["paired"] and dev["trusted"] and dev["connected"], "K380 Keyboard が ペアリング・信頼・接続の3つともそろっていません。")


def _g_bt_audio(d):
    s = _default_sink(d)
    card = next((c for c in d["audio"]["cards"] if c["kind"] == "bluez"), None)
    ok = bool(card and card["profile"] == "a2dp-sink" and s and s["name"].startswith("bluez_output")
              and not d["audio"]["cfg"][s["name"]]["mute"])
    return ok, "ヘッドセットの音声（a2dp）が既定の出力になっていません。"


def _g_bt_reconnect(d):
    dev = d["bt"]["devices"][0]
    return (dev["paired"] and dev["connected"] and not dev["stale"], "Dojo Buds を、いったん削除してから組み直す必要があります。")


def _g_audio_analog(d):
    s = _default_sink(d)
    return (bool(s and s["name"] == ANALOG), "既定の出力先が内蔵スピーカー（analog-stereo）になっていません。")


def _g_audio_audible(d):
    s = _default_sink(d)
    if not s or s["name"] != ANALOG:
        return False, "既定の出力先が内蔵スピーカーになっていません。"
    cfg = d["audio"]["cfg"][s["name"]]
    return (not cfg["mute"] and 20 <= cfg["vol"] <= 100, "ミュートまたは音量が小さすぎます（20〜100% にします）。")


def _g_audio_unmuted(d):
    s = _default_sink(d)
    return (bool(s and not d["audio"]["cfg"][s["name"]]["mute"]), "既定の出力先がミュートのままです。")


def _g_audio_wp(d):
    s = _default_sink(d)
    return (_unit_on(d, "wireplumber") and bool(s and s["name"] == ANALOG), "wireplumber が動いていないか、出力先が見つかりません。")


def _g_audio_pulse(d):
    return (_unit_on(d, "pipewire-pulse"), "pipewire-pulse が動いていません（pactl info が繋がるように）。")


def _g_audio_alsa(d):
    al = d["audio"]["alsa"]
    return (not al["Master"]["mute"] and not al["Speaker"]["mute"], "ALSA の Master と Speaker の両方のミュートを解除します。")


def _g_audio_dock(d):
    s = _default_sink(d)
    if not s or s["name"] != ANALOG:
        return False, "既定の出力先が内蔵スピーカーになっていません。"
    cfg = d["audio"]["cfg"][ANALOG]
    return (not cfg["mute"] and cfg["vol"] >= 30, "ミュート解除と、音量 30% 以上が必要です。")


def _g_pr_default(d):
    return (_effective_default(d["print"]) == "Office-Laser", "実際に使われる既定のプリンターが Office-Laser になっていません。")


def _g_pr_job_done(d):
    done = _hist(d, id=12, state="completed")
    return (bool(done), "ジョブ 12 がまだ印刷されていません（削除せず印刷させます）。")


def _g_pr_new_done(d):
    return (bool(_hist(d, printer="Office-Laser", file="report.txt", state="completed")), "Office-Laser で report.txt がまだ印刷されていません。")


def _g_pr_added(d):
    p = d["print"]
    pr = p["printers"].get("Office-Laser")
    if not pr or not pr["enabled"] or not pr["accepting"] or pr["model"] == "raw":
        return False, "Office-Laser が（有効・受付中・ドライバー指定ありで）追加されていません。"
    if _effective_default(p) != "Office-Laser":
        return False, "既定のプリンターが Office-Laser になっていません。"
    return (bool(_hist(d, printer="Office-Laser", file="report.txt", state="completed")), "テスト印刷（report.txt）がまだです。")


def _g_pr_options(d):
    done = _hist(d, printer="Office-Laser", state="completed")
    ok = any(j["copies"] == 2 and j["opts"].get("sides") == "two-sided-long-edge" for j in done)
    return ok, "2部・両面（長辺とじ）で印刷されたジョブがありません。"


def _g_pr_requeue(d):
    p = d["print"]
    stuck = [j for j in p["jobs"] if j["printer"] == "Photo-Inkjet"]
    if stuck:
        return False, "Photo-Inkjet のキューにジョブが残っています。"
    return _g_pr_new_done(d)


GOALS = {
    "wifi_unblocked": _g_wifi_unblocked, "wifi_home": _g_wifi_home, "wifi_lab": _g_wifi_lab, "wifi_staff": _g_wifi_staff,
    "wifi_priority": _g_wifi_priority, "wifi_driver": _g_wifi_driver, "wifi_combo": _g_wifi_combo,
    "bt_powered": _g_bt_powered, "bt_buds": _g_bt_buds, "bt_svc_buds": _g_bt_svc_buds, "bt_kbd": _g_bt_kbd,
    "bt_audio": _g_bt_audio, "bt_reconnect": _g_bt_reconnect, "audio_analog": _g_audio_analog,
    "audio_audible": _g_audio_audible, "audio_unmuted": _g_audio_unmuted, "audio_wp": _g_audio_wp,
    "audio_pulse": _g_audio_pulse, "audio_alsa": _g_audio_alsa, "audio_dock": _g_audio_dock, "pr_default": _g_pr_default,
    "pr_job_done": _g_pr_job_done, "pr_new_done": _g_pr_new_done, "pr_added": _g_pr_added, "pr_options": _g_pr_options,
    "pr_requeue": _g_pr_requeue,
}


@on_prepare
def prepare(terminal, step):
    terminal.progress.pop("desktop", None)
    name = step.get("desktop")
    if not name:
        return
    terminal.progress["desktop"] = _build(name)
    _sync_cups(terminal, terminal.progress["desktop"])


@on_check
def check(scenario, terminal):
    goal = scenario.get("desktop_goal")
    if not goal:
        return None
    d = _st(terminal, create=False)
    if d is None:
        return False, "模擬の状態がありません。reset で課題を最初から用意しましょう。"
    ok, message = GOALS[goal](d)
    return None if ok else (False, message)
