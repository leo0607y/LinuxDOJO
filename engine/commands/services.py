"""サービス管理の模擬コマンド（systemctl / journalctl / dmesg / crontab / apt-get / dpkg / top / htop / lsof）。

実際の PC のサービス・ログ・パッケージ・プロセスには一切触れない。すべて固定の架空データと
terminal.progress["services"] の状態だけで動く。出力は Ubuntu 24.04 の書式に寄せている。

課題の初期状態は step の "services" で変えられる:
    services={"nginx": {"active": "active", "enabled": True}, "cron": ["0 3 * * * /bin/true"], "upgradable": False}
（ユニット名のキーは active / enabled を上書き。"cron" は登録済み crontab の行。None で未登録）
"""
import datetime
import fnmatch
import re

from engine import guided
from engine.commands import command, on_check, on_prepare, register_package
from engine.guided import Result

NOW = datetime.datetime(2026, 1, 15, 9, 30, 0)
BOOT = datetime.datetime(2026, 1, 12, 7, 15, 58)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# name: 説明, 主プロセス, ポート, 本物の主プロセス名, 初期状態
UNITS = {
    "ssh": {"desc": "OpenBSD Secure Shell server", "pid": 512, "port": 22, "proc": "sshd", "user": "root",
            "cmd": "/usr/sbin/sshd -D", "active": "active", "enabled": True, "since": "Mon 2026-01-12 07:16:05 JST", "ago": "3 days ago"},
    "cron": {"desc": "Regular background program processing daemon", "pid": 845, "port": None, "proc": "cron", "user": "root",
             "cmd": "/usr/sbin/cron -f", "active": "active", "enabled": True, "since": "Mon 2026-01-12 07:16:04 JST", "ago": "3 days ago"},
    "rsyslog": {"desc": "System Logging Service", "pid": 701, "port": None, "proc": "rsyslogd", "user": "syslog",
                "cmd": "/usr/sbin/rsyslogd -n -iNONE", "active": "active", "enabled": True, "since": "Mon 2026-01-12 07:16:03 JST", "ago": "3 days ago"},
    "nginx": {"desc": "A high performance web server and a reverse proxy server", "pid": 3100, "port": 80, "proc": "nginx", "user": "root",
              "cmd": "nginx: master process /usr/sbin/nginx -g daemon on; master_process on;", "active": "inactive", "enabled": False,
              "since": "", "ago": ""},
    "demo-app": {"desc": "Demo App (training)", "pid": 3342, "port": 8080, "proc": "demo-app", "user": "learner",
                 "cmd": "/usr/local/bin/demo-app --port 8080", "active": "failed", "enabled": True,
                 "since": "Thu 2026-01-15 08:41:12 JST", "ago": "49min ago"},
}

# (日時, ユニット, 優先度 0-7, 識別名, PID, 本文)。優先度: 3=err 4=warning 5=notice 6=info
JOURNAL = [
    ("2026-01-14 22:05:11", "ssh", 6, "sshd", 512, "Accepted publickey for learner from 192.0.2.10 port 51022 ssh2"),
    ("2026-01-14 23:40:02", "cron", 6, "CRON", 2790, "(root) CMD (   cd / && run-parts --report /etc/cron.hourly)"),
    ("2026-01-15 02:17:44", "ssh", 4, "sshd", 3011, "Failed password for invalid user admin from 198.51.100.23 port 40122 ssh2"),
    ("2026-01-15 02:17:49", "ssh", 4, "sshd", 3011, "Failed password for invalid user admin from 198.51.100.23 port 40122 ssh2"),
    ("2026-01-15 02:17:55", "ssh", 3, "sshd", 3011, "error: maximum authentication attempts exceeded for invalid user admin from 198.51.100.23 port 40122 ssh2 [preauth]"),
    ("2026-01-15 03:00:01", "cron", 6, "CRON", 3120, "(root) CMD (/usr/local/bin/backup.sh)"),
    ("2026-01-15 03:00:03", "cron", 3, "CRON", 3120, "(root) MAIL (mailed 1 byte of output; but got status 0x0001)"),
    ("2026-01-15 06:30:00", "rsyslog", 6, "rsyslogd", 701, "[origin software=\"rsyslogd\" swVersion=\"8.2312.0\" x-pid=\"701\"] rsyslogd was HUPed"),
    ("2026-01-15 08:40:55", "demo-app", 6, "demo-app", 3342, "listening on 0.0.0.0:8080"),
    ("2026-01-15 08:41:10", "demo-app", 3, "demo-app", 3342, "fatal: cannot open database file /var/lib/demo-app/data.db: disk quota exceeded"),
    ("2026-01-15 08:41:12", "demo-app", 3, "systemd", 1, "demo-app.service: Main process exited, code=exited, status=1/FAILURE"),
    ("2026-01-15 08:41:12", "demo-app", 3, "systemd", 1, "demo-app.service: Failed with result 'exit-code'."),
    ("2026-01-15 09:12:03", "ssh", 6, "sshd", 3201, "Accepted publickey for learner from 192.0.2.10 port 51888 ssh2"),
    ("2026-01-15 09:20:31", "cron", 6, "CRON", 3260, "(learner) CMD (/home/learner/bin/cleanup.sh)"),
]
BOOT_LINES = {
    "ssh": [("2026-01-12 07:16:05", 6, "systemd", 1, "Started ssh.service - OpenBSD Secure Shell server."),
            ("2026-01-12 07:16:05", 6, "sshd", 512, "Server listening on 0.0.0.0 port 22.")],
    "cron": [("2026-01-12 07:16:04", 6, "systemd", 1, "Started cron.service - Regular background program processing daemon.")],
    "rsyslog": [("2026-01-12 07:16:03", 6, "systemd", 1, "Started rsyslog.service - System Logging Service.")],
}

# カーネルメッセージ（起動からの秒数, 優先度 0-7, 本文）
DMESG = [
    (0.000000, 6, "Linux version 6.8.0-training (buildd@training) (gcc 13.2.0) #1 SMP PREEMPT_DYNAMIC"),
    (0.004211, 6, "Command line: BOOT_IMAGE=/vmlinuz-6.8.0-training root=/dev/sda1 ro quiet splash"),
    (0.310552, 6, "ACPI: Core revision 20230628"),
    (1.204118, 6, "NET: Registered PF_INET protocol family"),
    (1.882004, 4, "ACPI BIOS Warning (bug): Optional FADT field Pm2ControlBlock has valid Length but zero Address"),
    (2.410917, 6, "sd 0:0:0:0: [sda] 41943040 512-byte logical blocks: (21.5 GB/20.0 GiB)"),
    (3.015632, 6, "EXT4-fs (sda1): mounted filesystem with ordered data mode. Quota mode: none."),
    (5.771340, 3, "ata2.00: failed command: READ DMA"),
    (5.771902, 3, "blk_update_request: I/O error, dev sdb, sector 2048 op 0x0:(READ) flags 0x0 phys_seg 1 prio class 2"),
    (8.120441, 6, "e1000: eth0 NIC Link is Up 1000 Mbps Full Duplex, Flow Control: RX"),
    (12.440018, 4, "systemd[1]: /usr/lib/systemd/system/demo-app.service:6: Unknown key name 'Restrt' in section 'Service', ignoring."),
    (183512.402115, 6, "usb 1-1: new high-speed USB device number 4 using xhci_hcd"),
    (183512.730881, 6, "usb-storage 1-1:1.0: USB Mass Storage device detected"),
    (250102.118774, 3, "Out of memory: Killed process 3188 (stress) total-vm:2097152kB, anon-rss:1843200kB, file-rss:0kB"),
]

# dpkg -l に出す基本のパッケージ (名前, 版, 説明)
BASE_PACKAGES = [
    ("bash", "5.2.21-2ubuntu4", "GNU Bourne Again SHell"),
    ("coreutils", "9.4-3ubuntu6", "GNU core utilities"),
    ("cron", "3.0pl1-184ubuntu2", "process scheduling daemon"),
    ("grep", "3.11-4build1", "GNU grep, egrep and fgrep"),
    ("libc6", "2.39-0ubuntu8.3", "GNU C Library: Shared libraries"),
    ("nginx", "1.24.0-2ubuntu7", "small, powerful, scalable web/proxy server"),
    ("openssh-server", "1:9.6p1-3ubuntu13.5", "secure shell (SSH) server, for secure access from remote machines"),
    ("openssl", "3.0.13-0ubuntu3.4", "Secure Sockets Layer toolkit - cryptographic utility"),
    ("rsyslog", "8.2312.0-3ubuntu9", "reliable system and kernel logging daemon"),
    ("systemd", "255.4-1ubuntu8.4", "system and service manager"),
]
UPGRADES = {"libc6": "2.39-0ubuntu8.4", "openssl": "3.0.13-0ubuntu3.5", "openssh-server": "1:9.6p1-3ubuntu13.6"}


def _fresh():
    return {
        "units": {n: {"active": u["active"], "enabled": u["enabled"], "since": u["since"], "ago": u["ago"]} for n, u in UNITS.items()},
        "cron": None,
        "journal": [],
        "ticks": 0,
        "upgradable": True,
        "upgraded": [],
    }


def _state(terminal):
    state = terminal.progress.get("services")
    if not isinstance(state, dict) or "units" not in state:
        state = terminal.progress["services"] = _fresh()
    return state


def _sync_processes(terminal):
    """起動中のユニットを ps / pgrep / kill が見るプロセス一覧へ反映する（ssh と cron は最初から載っている）。"""
    state = _state(terminal)
    procs = [p for p in terminal.progress["processes"] if not p.get("service")]
    for name in ("nginx", "demo-app"):
        if state["units"][name]["active"] == "active":
            unit = UNITS[name]
            procs.append({"pid": unit["pid"], "user": unit["user"], "cmd": unit["cmd"], "cpu": 0.0, "mem": 0.4, "service": name})
    terminal.progress["processes"] = procs


@on_prepare
def prepare(terminal, step):
    state = terminal.progress["services"] = _fresh()
    for key, value in step.get("services", {}).items():
        if key in state["units"] and isinstance(value, dict):
            state["units"][key].update(value)
        elif key == "cron":
            state["cron"] = list(value) if value is not None else None
        else:
            state[key] = value
    _sync_processes(terminal)


@on_check
def check(scenario, terminal):
    state = _state(terminal)
    for name, expected in scenario.get("expected_services", {}).items():
        current = state["units"].get(name)
        if current is None or any(current.get(key) != value for key, value in expected.items()):
            return False, f"サービス {name} の起動状態・自動起動設定を確認しましょう。"
    if "expected_cron" in scenario and state["cron"] != scenario["expected_cron"]:
        return False, "定期実行の予定表が目的の内容になっていません。crontab で確認しましょう。"
    return None


def _unit_name(text):
    return text[:-8] if text.endswith(".service") else text


def _stamp(dt):
    return f"{MONTHS[dt.month - 1]} {dt.day:2d} {dt:%H:%M:%S}"


def _log(terminal, unit, prio, ident, pid, text):
    state = _state(terminal)
    state["ticks"] += 1
    when = NOW + datetime.timedelta(seconds=10 + state["ticks"] * 2)
    state["journal"].append([when.strftime("%Y-%m-%d %H:%M:%S"), unit, prio, ident, pid, text])


def _entries(terminal):
    rows = [list(x) for x in JOURNAL]
    for name, lines in BOOT_LINES.items():
        rows += [[ts, name, prio, ident, pid, msg] for ts, prio, ident, pid, msg in lines]
    rows += _state(terminal)["journal"]
    return sorted(rows, key=lambda r: r[0])


def _journal_line(terminal, row):
    when = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    return f"{_stamp(when)} {terminal.hostname} {row[3]}[{row[4]}]: {row[5]}"


# ---------------------------------------------------------------- systemctl
_SERVICE_WORD = {"active": "active (running)", "inactive": "inactive (dead)", "failed": "failed (Result: exit-code)"}
_NEEDS_ADMIN = ("start", "stop", "restart", "reload", "enable", "disable", "reset-failed", "daemon-reload")


def _status_text(terminal, name):
    unit, st = UNITS[name], _state(terminal)["units"][name]
    mark = {"active": "●", "inactive": "○", "failed": "×"}[st["active"]]
    enabled = "enabled" if st["enabled"] else "disabled"
    lines = [f"{mark} {name}.service - {unit['desc']}",
             f"     Loaded: loaded (/usr/lib/systemd/system/{name}.service; {enabled}; preset: enabled)"]
    if st["active"] == "inactive" and not st["since"]:
        lines.append("     Active: inactive (dead)")
    else:
        lines.append(f"     Active: {_SERVICE_WORD[st['active']]} since {st['since']}; {st['ago']}")
    if st["active"] == "failed":
        lines.append(f"    Process: {unit['pid']} ExecStart={unit['cmd'].split()[0]} (code=exited, status=1/FAILURE)")
        lines.append(f"   Main PID: {unit['pid']} (code=exited, status=1/FAILURE)")
    elif st["active"] == "active":
        lines += [f"   Main PID: {unit['pid']} ({unit['proc']})", "      Tasks: 1 (limit: 4557)", "     Memory: 3.4M (peak: 4.1M)",
                  "        CPU: 120ms", f"     CGroup: /system.slice/{name}.service", f"             └─{unit['pid']} {unit['cmd']}"]
    rows = [r for r in _entries(terminal) if r[1] == name][-8:]
    lines += [""] + [_journal_line(terminal, r) for r in rows]
    return "\n".join(lines)


def _set_active(terminal, name, active, text, pid=None):
    state = _state(terminal)
    st = state["units"][name]
    st["active"] = active
    _log(terminal, name, 6, "systemd", 1, text)
    if active == "active":
        st["since"] = f"Thu {state['journal'][-1][0]} JST"
        st["ago"] = "1s ago"
    _sync_processes(terminal)


def _units_table(terminal, failed_only, all_units):
    rows = []
    for name, unit in UNITS.items():
        st = _state(terminal)["units"][name]
        if failed_only and st["active"] != "failed":
            continue
        if not failed_only and not all_units and st["active"] != "active":
            continue
        sub = {"active": "running", "inactive": "dead", "failed": "failed"}[st["active"]]
        mark = "● " if st["active"] == "failed" else "  "
        rows.append((mark, f"{name}.service", "loaded", st["active"], sub, unit["desc"]))
    width = max([len(r[1]) for r in rows] + [4])
    out = [f"  {'UNIT':<{width}} LOAD   ACTIVE   SUB     DESCRIPTION"]
    out += [f"{m}{u:<{width}} {l:<6} {a:<8} {s:<7} {d}" for m, u, l, a, s, d in rows]
    out += ["", "LOAD   = Reflects whether the unit definition was properly loaded.",
            "ACTIVE = The high-level unit activation state, i.e. generalization of SUB.",
            "SUB    = The low-level unit activation state, values depend on unit type.", "",
            f"{len(rows)} loaded units listed."]
    return "\n".join(out)


@command("systemctl", sudo=True)
def systemctl(terminal, rest, stdin=None, admin=False):
    flags = [a for a in rest if a.startswith("-")]
    words = [a for a in rest if not a.startswith("-")]
    known_flags = {"--failed", "--state=failed", "--no-pager", "--all", "--now", "--type=service", "-t", "-a", "-l", "--full"}
    if "-t" in flags:  # -t service
        if words[:1] and words[0] == "service" and rest.index("-t") + 1 < len(rest) and rest[rest.index("-t") + 1] == "service":
            words = words[1:]
        else:
            return None
    if any(f not in known_flags for f in flags):
        return None
    if not words and "--failed" in flags:
        words = ["list-units"]
    if not words:
        words = ["list-units"]
    action, names = words[0], [_unit_name(w) for w in words[1:]]
    if action == "list-units":
        if names:
            return None
        return Result(_units_table(terminal, any(f in flags for f in ("--failed", "--state=failed")), "--all" in flags or "-a" in flags))
    if action == "reset-failed" or (action == "daemon-reload" and not names):
        if not admin:
            return Result(f"Failed to {'reload daemon' if action == 'daemon-reload' else 'reset failed state'}: Interactive authentication required.", 1)
        if action == "reset-failed":
            missing = next((name for name in names if name not in UNITS), None)
            if missing:
                return Result(f"Failed to reset failed state of unit {missing}.service: Unit {missing}.service not loaded.", 1)
            for name, st in _state(terminal)["units"].items():
                if names and name not in names:
                    continue
                if st["active"] == "failed":
                    st["active"] = "inactive"
                    st["since"] = ""
                    st["ago"] = ""
        return Result()
    if action not in ("status", "start", "stop", "restart", "reload", "enable", "disable", "is-active", "is-enabled", "is-failed") or not names:
        return None
    if "--failed" in flags or ("--now" in flags and action not in ("enable", "disable")):
        return None
    state = _state(terminal)
    if action in ("is-active", "is-enabled", "is-failed"):
        outputs, code = [], 0
        for name in names:
            if name not in UNITS:
                outputs.append("inactive" if action == "is-active" else "")
                code = 4
                continue
            st = state["units"][name]
            if action == "is-active":
                outputs.append(st["active"])
                code = code or (0 if st["active"] == "active" else 3)
            elif action == "is-enabled":
                outputs.append("enabled" if st["enabled"] else "disabled")
                code = code or (0 if st["enabled"] else 1)
            else:
                outputs.append("failed" if st["active"] == "failed" else st["active"])
                code = code or (0 if st["active"] == "failed" else 1)
        return Result("\n".join(o for o in outputs if o), code)
    if action == "status":
        blocks, code = [], 0
        for name in names:
            if name not in UNITS:
                blocks.append(f"Unit {name}.service could not be found.")
                code = 4
            else:
                blocks.append(_status_text(terminal, name))
                if state["units"][name]["active"] != "active":
                    code = code or 3
        return Result("\n\n".join(blocks), code)
    missing = next((n for n in names if n not in UNITS), None)
    if not admin:
        verb = {"enable": "enable unit", "disable": "disable unit"}.get(action, action)
        return Result(f"Failed to {verb} {names[0]}.service: Interactive authentication required.\n"
                      f"See system logs and 'systemctl status {names[0]}.service' for details.", 1)
    if missing:
        if action in ("enable", "disable"):
            return Result(f"Failed to {action} unit: Unit file {missing}.service does not exist.", 1)
        return Result(f"Failed to {action} {missing}.service: Unit {missing}.service not found.", 5)
    out = []
    for name in names:
        st = state["units"][name]
        unit = UNITS[name]
        if action == "start":
            if st["active"] != "active":
                _set_active(terminal, name, "active", f"Started {name}.service - {unit['desc']}.")
        elif action == "stop":
            if st["active"] == "active":
                _set_active(terminal, name, "inactive", f"Stopped {name}.service - {unit['desc']}.")
        elif action == "restart":
            if st["active"] == "active":
                _log(terminal, name, 6, "systemd", 1, f"Stopping {name}.service - {unit['desc']}...")
            _set_active(terminal, name, "active", f"Started {name}.service - {unit['desc']}.")
        elif action == "reload":
            if st["active"] != "active":
                return Result(f"Failed to reload {name}.service: Unit {name}.service is not active.", 1)
            _log(terminal, name, 6, "systemd", 1, f"Reloaded {name}.service - {unit['desc']}.")
        elif action == "enable":
            if not st["enabled"]:
                out.append(f"Created symlink /etc/systemd/system/multi-user.target.wants/{name}.service → /usr/lib/systemd/system/{name}.service.")
            st["enabled"] = True
            if "--now" in flags and st["active"] != "active":
                _set_active(terminal, name, "active", f"Started {name}.service - {unit['desc']}.")
        elif action == "disable":
            if st["enabled"]:
                out.append(f"Removed \"/etc/systemd/system/multi-user.target.wants/{name}.service\".")
            st["enabled"] = False
            if "--now" in flags and st["active"] == "active":
                _set_active(terminal, name, "inactive", f"Stopped {name}.service - {unit['desc']}.")
    return Result("\n".join(out))


# ---------------------------------------------------------------- journalctl
_PRIORITIES = {"emerg": 0, "alert": 1, "crit": 2, "err": 3, "warning": 4, "notice": 5, "info": 6, "debug": 7}


def _parse_when(text, default=NOW):
    text = text.strip().strip("'\"")
    if text == "today":
        return NOW.replace(hour=0, minute=0, second=0)
    if text == "yesterday":
        return NOW.replace(hour=0, minute=0, second=0) - datetime.timedelta(days=1)
    if text == "now":
        return NOW
    match = re.fullmatch(r"(\d+)\s*(second|sec|minute|min|hour|day)s?\s+ago", text)
    if match:
        unit = {"second": "seconds", "sec": "seconds", "minute": "minutes", "min": "minutes", "hour": "hours", "day": "days"}[match.group(2)]
        return NOW - datetime.timedelta(**{unit: int(match.group(1))})
    for fmt, base in (("%Y-%m-%d %H:%M:%S", None), ("%Y-%m-%d %H:%M", None), ("%Y-%m-%d", None), ("%H:%M:%S", "t"), ("%H:%M", "t")):
        try:
            value = datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
        if base:
            value = NOW.replace(hour=value.hour, minute=value.minute, second=value.second)
        return value
    raise ValueError(text)


def _parse_priority(text):
    if text.isdigit() and 0 <= int(text) <= 7:
        return int(text)
    return _PRIORITIES.get(text)


@command("journalctl", sudo=True)
def journalctl(terminal, rest, stdin=None, admin=False):
    units, count, since, until, prio, follow, reverse = [], None, None, None, None, False, False
    args = []
    for arg in rest:
        # Common compact spelling: -fu ssh or -fushared.service.
        if arg.startswith("-fu") and not arg.startswith("--"):
            args.extend(["-f", "-u"] + ([arg[3:]] if arg[3:] else []))
        else:
            args.append(arg)
    try:
        while args:
            arg = args.pop(0)
            value = None
            if arg in ("-u", "--unit", "-n", "--lines", "--since", "--until", "-p", "--priority"):
                if not args:
                    return Result(f"journalctl: option '{arg}' requires an argument", 1)
                value = args.pop(0)
            elif arg.startswith("--") and "=" in arg:
                arg, value = arg.split("=", 1)
            elif re.fullmatch(r"-[unp]\S+", arg):
                arg, value = arg[:2], arg[2:]
            if arg in ("-u", "--unit"):
                units.append(_unit_name(value))
            elif arg in ("-n", "--lines"):
                if not re.fullmatch(r"\d+", value):
                    return Result(f"Failed to parse lines '{value}'", 1)
                count = int(value)
            elif arg == "--since":
                since = _parse_when(value)
            elif arg == "--until":
                until = _parse_when(value)
            elif arg in ("-p", "--priority"):
                prio = _parse_priority(value)
                if prio is None:
                    return Result(f"Unknown log level {value}", 1)
            elif arg in ("-f", "--follow"):
                follow = True
            elif arg in ("-r", "--reverse"):
                reverse = True
            elif arg in ("--no-pager", "-b", "-e", "-x", "-xe"):
                pass
            else:
                return None
    except ValueError as error:
        return Result(f"Failed to parse timestamp: {error}", 1)
    rows = _entries(terminal)
    if units:
        rows = [r for r in rows if r[1] in units]
    if prio is not None:
        rows = [r for r in rows if r[2] <= prio]
    if since is not None:
        rows = [r for r in rows if datetime.datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") >= since]
    if until is not None:
        rows = [r for r in rows if datetime.datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") <= until]
    if count is None and follow:
        count = 10
    if count is not None:
        rows = rows[len(rows) - count:] if count else []
    if reverse:
        rows = rows[::-1]
    lines = [_journal_line(terminal, r) for r in rows] or ["-- No entries --"]
    if follow:
        lines.append("（-f は新しい行が増えるのを待ち続けます。本物は Ctrl+C で止めます。模擬では今ある最後の部分だけ表示しました）")
    return Result("\n".join(lines))


# ---------------------------------------------------------------- dmesg
@command("dmesg", sudo=True)
def dmesg(terminal, rest, stdin=None, admin=False):
    human, levels = False, None
    args = list(rest)
    while args:
        arg = args.pop(0)
        if arg == "-T":
            human = True
        elif arg in ("-l", "--level") and args:
            levels = args.pop(0)
        elif arg.startswith("--level="):
            levels = arg.split("=", 1)[1]
        else:
            return None
    if not admin:
        return Result("dmesg: read kernel buffer failed: Operation not permitted", 1)
    wanted = None
    if levels is not None:
        wanted = set()
        for word in levels.split(","):
            if word not in _PRIORITIES:
                return Result(f"dmesg: unknown level '{word}'", 1)
            wanted.add(_PRIORITIES[word])
    lines = []
    for seconds, prio, text in DMESG:
        if wanted is not None and prio not in wanted:
            continue
        if human:
            when = BOOT + datetime.timedelta(seconds=int(seconds))
            stamp = f"{DAYS[when.weekday()]} {MONTHS[when.month - 1]} {when.day:2d} {when:%H:%M:%S %Y}"
        else:
            stamp = f"{seconds:>12.6f}"
        lines.append(f"[{stamp}] {text}")
    return Result("\n".join(lines))


# ---------------------------------------------------------------- crontab
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_FIELD_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


def _valid_field(text, low, high):
    for part in text.split(","):
        step = None
        if "/" in part:
            part, step = part.split("/", 1)
            if not step.isdigit() or int(step) == 0:
                return False
        if part == "*":
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            return False
        a, b = int(match.group(1)), int(match.group(2) or match.group(1))
        if not (low <= a <= high and low <= b <= high and a <= b):
            return False
    return True


def _check_crontab(text):
    """問題があれば説明の文字列、なければ None。"""
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
            continue
        if line.startswith("@"):
            if line.split()[0] not in ("@reboot", "@hourly", "@daily", "@weekly", "@monthly", "@yearly") or len(line.split()) < 2:
                return f"\"-\":{number}: bad special time"
            continue
        fields = line.split(None, 5)
        if len(fields) < 6:
            return f"\"-\":{number}: bad command（時刻の5項目の後ろにコマンドが必要です）"
        for index, field in enumerate(fields[:5]):
            if not _valid_field(field, *_RANGES[index]):
                return f"\"-\":{number}: bad {_FIELD_NAMES[index]}"
    return None


@command("crontab")
def crontab(terminal, rest, stdin=None, admin=False):
    state = _state(terminal)
    if rest == ["-l"]:
        if state["cron"] is None:
            return Result("no crontab for learner", 1)
        return Result("\n".join(state["cron"]))
    if rest == ["-r"]:
        if state["cron"] is None:
            return Result("no crontab for learner", 1)
        state["cron"] = None
        return Result()
    if rest == ["-e"]:
        return Result("この模擬ターミナルでは編集画面（crontab -e）は開けません。\n"
                      "代わりに、cron の行を書いたファイルを作って、そのファイル名を crontab に渡して登録します。", 1)
    if len(rest) == 1 and not rest[0].startswith("-"):
        path = terminal.path(rest[0])
        if not path.is_file():
            return Result(f"{rest[0]}: No such file or directory", 1)
        text = path.read_text(encoding="utf-8")
        problem = _check_crontab(text)
        if problem:
            return Result(f"crontab: errors in crontab file, can't install.\n{problem}", 1)
        state["cron"] = text.splitlines()
        return Result()
    return None


# ---------------------------------------------------------------- パッケージ（apt-get / dpkg）
def _installed(terminal):
    rows = {n: (v, d) for n, v, d in BASE_PACKAGES}
    for name in terminal.progress.get("packages", []):
        if name in guided.PACKAGES:
            desc, version = guided.PACKAGES[name]
            rows[name] = (version, desc)
    state = _state(terminal)
    for name in state["upgraded"]:
        if name in rows:
            rows[name] = (UPGRADES[name], rows[name][1])
    return dict(sorted(rows.items()))


def _pending(terminal):
    state = _state(terminal)
    if not terminal.progress.get("apt_updated") or not state["upgradable"]:
        return []
    return [n for n in UPGRADES if n not in state["upgraded"]]


@command("apt-get", sudo=True)
def apt_get(terminal, rest, stdin=None, admin=False):
    flags = [a for a in rest if a.startswith("-")]
    words = [a for a in rest if not a.startswith("-")]
    if any(f not in ("-y", "-s", "--simulate", "--dry-run") for f in flags) or len(words) != 1 or words[0] not in ("update", "upgrade"):
        return None
    simulate = any(f in ("-s", "--simulate", "--dry-run") for f in flags)
    action = words[0]
    if not admin and not (simulate and action == "upgrade"):
        return Result(f"E: Could not open lock file /var/lib/apt/lists/lock - open (13: Permission denied)\n"
                      f"E: Unable to lock directory /var/lib/apt/lists/\n先頭に sudo を付けます。この画面の apt-get は訓練専用です。", 100)
    if action == "update":
        terminal.progress["apt_updated"] = True
        return Result("Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease\n"
                      "Get:2 http://security.ubuntu.com/ubuntu noble-security InRelease [126 kB]\n"
                      "Fetched 126 kB in 1s (141 kB/s)\nReading package lists... Done\n"
                      "3 packages can be upgraded. Run 'apt list --upgradable' to see them.")
    pending = _pending(terminal)
    if not pending:
        return Result("Reading package lists... Done\nCalculating upgrade... Done\n"
                      "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.")
    if simulate:
        body = "\n".join(f"Inst {n} [{_installed(terminal)[n][0]}] ({UPGRADES[n]} Ubuntu:24.04/noble-updates [amd64])" for n in pending)
        return Result(f"Reading package lists... Done\nCalculating upgrade... Done\n{body}\n（-s は試すだけで、実際には何も更新しません）")
    _state(terminal)["upgraded"] += pending
    return Result("Reading package lists... Done\nCalculating upgrade... Done\n"
                  f"The following packages will be upgraded:\n  {' '.join(pending)}\n"
                  f"{len(pending)} upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
                  "（模擬）更新しました。実際の PC は変更していません。")


@command("dpkg")
def dpkg(terminal, rest, stdin=None, admin=False):
    if not rest:
        return None
    installed = _installed(terminal)
    if rest[0] in ("-l", "--list"):
        patterns = rest[1:]
        names = [n for n in installed if not patterns or any(fnmatch.fnmatch(n, p) for p in patterns)]
        if not names:
            return Result(f"dpkg-query: no packages found matching {patterns[0]}", 1)
        header = ["Desired=Unknown/Install/Remove/Purge/Hold",
                  "| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend",
                  "|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)",
                  "||/ Name           Version                 Architecture Description",
                  "+++-==============-=======================-============-========================"]
        rows = [f"ii  {n:<14} {installed[n][0]:<23} amd64        {installed[n][1]}" for n in names]
        return Result("\n".join(header + rows))
    if rest[0] in ("-s", "--status") and len(rest) == 2:
        name = rest[1]
        if name not in installed:
            return Result(f"dpkg-query: package '{name}' is not installed and no information is available", 1)
        version, desc = installed[name]
        return Result(f"Package: {name}\nStatus: install ok installed\nPriority: optional\nArchitecture: amd64\nVersion: {version}\nDescription: {desc}")
    return None


# ---------------------------------------------------------------- top / htop / lsof
def _snapshot(terminal):
    procs = sorted(terminal.progress["processes"], key=lambda p: (-p["cpu"], -p["mem"], p["pid"]))
    rows = [f"top - 09:30:00 up 3 days,  2:14,  1 user,  load average: {0.08 + sum(p['cpu'] for p in procs) / 100:.2f}, 0.03, 0.01",
            f"Tasks: {len(procs) + 1:>3} total,   1 running, {len(procs):>3} sleeping,   0 stopped,   0 zombie",
            "%Cpu(s):  1.0 us,  0.5 sy,  0.0 ni, 98.3 id,  0.1 wa,  0.0 hi,  0.1 si,  0.0 st",
            "MiB Mem :   3891.0 total,   1126.4 free,   1228.8 used,   1536.0 buff/cache",
            "MiB Swap:   1024.0 total,   1024.0 free,      0.0 used.   2457.6 avail Mem ", "",
            "    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND"]
    for p in procs:
        state = "R" if p["cpu"] >= 50 else "S"
        rows.append(f"{p['pid']:>7} {p['user']:<9} 20   0  {int(p['mem'] * 20000):>6}  {int(p['mem'] * 8000):>5}   3200 {state} {p['cpu']:>5.1f} {p['mem']:>5.1f}   0:01.20 {p['cmd'].split()[0].rstrip(':').rsplit('/', 1)[-1]}")
    return "\n".join(rows)


@command("top")
def top(terminal, rest, stdin=None, admin=False):
    if rest in (["-b", "-n", "1"], ["-bn1"], ["-bn", "1"], ["-n", "1", "-b"], ["-b", "-n1"], ["-n1", "-b"]):
        return Result(_snapshot(terminal))
    if rest == []:
        return Result(_snapshot(terminal) + "\n（本物の top は画面が更新され続け、q で終了します。模擬では1回分だけ表示しました）")
    return None


@command("htop")
def htop(terminal, rest, stdin=None, admin=False):
    if "htop" not in terminal.progress.get("packages", []):
        return Result("Command 'htop' not found, but can be installed with:\nsudo apt install htop", 127)
    if rest:
        return None
    return Result(_snapshot(terminal).replace("top - ", "htop（模擬の静止画）- ", 1) + "\n（本物の htop は色付きで更新され続け、F10 か q で終了します）")


_PORT_NAMES = {22: "ssh", 80: "http", 8080: "http-alt"}
_OPEN_FILES = {"/var/log/syslog": "rsyslog", "/var/log/auth.log": "rsyslog", "/var/log/nginx/access.log": "nginx"}


def _lsof_rows(terminal):
    """(COMMAND, PID, USER, FD, TYPE, NODE, NAME, ポート, ファイル)"""
    rows = []
    for name, unit in UNITS.items():
        if _state(terminal)["units"][name]["active"] != "active":
            continue
        pid, user, proc = unit["pid"], unit["user"], unit["proc"]
        if unit["port"]:
            label = _PORT_NAMES.get(unit["port"], str(unit["port"]))
            rows.append((proc, pid, user, "3u", "IPv4", "TCP", f"*:{label} (LISTEN)", unit["port"], None))
            if name == "ssh":
                rows.append((proc, pid, user, "4u", "IPv6", "TCP", f"*:{label} (LISTEN)", unit["port"], None))
        for path, owner in _OPEN_FILES.items():
            if owner == name:
                rows.append((proc, pid, user, "7w", "REG", "REG", path, None, path))
    rows.append(("bash", 2001, "learner", "0u", "CHR", "CHR", "/dev/pts/0", None, "/dev/pts/0"))
    return rows


@command("lsof", sudo=True)
def lsof(terminal, rest, stdin=None, admin=False):
    rows = _lsof_rows(terminal)
    selector = None
    args = list(rest)
    while args:
        arg = args.pop(0)
        if arg in ("-i", "-p", "-u") or re.fullmatch(r"-[ipu]\S+", arg):
            value = arg[2:]
            if not value and args and (arg != "-i" or args[0].startswith(":") or args[0].lower().startswith(("tcp", "udp"))):
                value = args.pop(0)
            selector = (arg[1], value)
        elif not arg.startswith("-") and arg.startswith("/"):
            selector = ("f", arg)
        else:
            return None
    if selector is None:
        return None
    kind, value = selector
    if kind == "i":
        port = re.search(r":(\d+)$", value)
        if value and not re.fullmatch(r"(?i)(tcp|udp)?(:\d+)?", value):
            return None
        rows = [r for r in rows if r[7] is not None and (not port or r[7] == int(port.group(1)))]
    elif kind == "p":
        if not value.isdigit():
            return None
        rows = [r for r in rows if r[1] == int(value)]
    elif kind == "u":
        rows = [r for r in rows if r[2] == value]
    else:
        rows = [r for r in rows if r[8] == value]
    if not admin:
        rows = [r for r in rows if r[2] == "learner"]
    if not rows:
        return Result("", 1)
    header = "COMMAND   PID    USER   FD   TYPE DEVICE SIZE/OFF NODE NAME"
    body = [f"{r[0]:<9} {r[1]:<6} {r[2]:<7}{r[3]:<4} {r[4]:<5} 12345      0t0  {r[5]:<4} {r[6]}" for r in rows]
    return Result("\n".join([header] + body))


register_package("htop", "プロセスを色付きで見やすく表示する top の上位互換", "3.3.0-training")
