"""学習用 root 権限コマンド・シミュレーター（Stage 7: サーバー運用）。

本物の systemctl / journalctl / useradd などには一切触れず、root 権限も使わない。
  ・システム領域   … $LQ_WORK/sysroot/ 以下を「/」とみなす（/etc/passwd → sysroot/etc/passwd）
  ・サービス状態   … $LQ_STATE/sim_ops.json（ユニットの稼働状態・ロード済み設定・ジャーナル）
  ・root 権限      … 模擬 sudo が環境変数 LQ_SIM_ROOT=1 を付けて実行したものだけ「root」として扱う

対応コマンド: systemctl, journalctl, useradd, adduser, usermod, groupadd, groupdel, userdel, gpasswd,
             passwd, id, groups, getent, sudo
"""
import fnmatch
import getpass
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

W = None   # 作業ディレクトリ（$LQ_WORK）
S = None   # 状態ファイル

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PRIOS = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
UNIT_DIRS = ["/etc/systemd/system", "/run/systemd/system", "/usr/lib/systemd/system", "/lib/systemd/system"]
SIM_CMDS = {"systemctl", "journalctl", "useradd", "adduser", "usermod", "groupadd", "groupdel", "userdel",
            "gpasswd", "passwd", "id", "groups", "getent", "sudo"}
SIMBIN = Path(__file__).resolve().parent.parent / "bin" / "sim"


def configure(work=None, state=None):
    global W, S
    W = Path(work or os.environ.get("LQ_WORK") or os.getcwd())
    S = Path(state or os.environ.get("LQ_STATE") or (W / ".lq_state")) / "sim_ops.json"


def R(path=""):
    """模擬システムの絶対パス → サンドボックス上の実パス。"""
    return W / "sysroot" / str(path).lstrip("/")


def is_root():
    return os.environ.get("LQ_SIM_ROOT") == "1"


def dim(msg):
    if sys.stderr.isatty():
        return f"\x1b[2m{msg}\x1b[0m"
    return msg


def err(msg):
    sys.stderr.write(msg.rstrip("\n") + "\n")


def sudo_hint():
    err(dim("[LinuxQuest 模擬] この操作には root 権限が必要です。先頭に `sudo` を付けて実行しましょう。"))


# ------------------------------------------------------------------ state
def load():
    try:
        st = json.loads(S.read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("host", "web01")
    st.setdefault("boots", [{"id": hashlib.md5(b"lq").hexdigest(), "start": time.time() - 3600}])
    st.setdefault("journal", [])
    st.setdefault("units", {})
    st.setdefault("pids", [])
    return st


def save(st):
    S.parent.mkdir(parents=True, exist_ok=True)
    tmp = S.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False))
    os.replace(tmp, S)


def new_pid(st):
    used = set(st.get("pids", []))
    for _ in range(500):
        pid = random.randint(700, 39000)
        if pid not in used and not os.path.exists(f"/proc/{pid}"):
            st.setdefault("pids", []).append(pid)
            return pid
    return random.randint(700, 39000)


def log(st, unit, ident, pid, msg, prio=6, ts=None, boot=None):
    st["journal"].append({"ts": ts if ts is not None else time.time(), "unit": unit, "ident": ident, "pid": pid,
                          "prio": prio, "msg": msg, "boot": len(st["boots"]) - 1 if boot is None else boot})


# ------------------------------------------------------------------ time formatting
def tz():
    return time.strftime("%Z") or "JST"


def ts_short(ts):
    t = time.localtime(ts)
    return f"{MONTHS[t.tm_mon - 1]} {t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"


def ts_long(ts):
    t = time.localtime(ts)
    return f"{WDAYS[t.tm_wday]} {time.strftime('%Y-%m-%d %H:%M:%S', t)} {tz()}"


def ago(ts):
    s = int(max(0, time.time() - ts))
    if s < 60:
        return f"{s}s ago"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}min {s}s ago" if m < 10 else f"{m}min ago"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}min ago"
    d, h = divmod(h, 24)
    return f"{d} day{'s' if d > 1 else ''} {h}h ago"


# ------------------------------------------------------------------ unit files
def uname(n):
    n = n.strip().split("/")[-1]
    if re.search(r"\.(service|socket|timer|target|mount|path|slice|scope)$", n):
        return n
    return n + ".service"


def unit_file(name):
    for d in UNIT_DIRS:
        p = R(d) / name
        if os.path.lexists(p):
            return f"{d}/{name}", p
    return None, None


def is_masked(name):
    p = R("/etc/systemd/system") / name
    return p.is_symlink() and os.readlink(p) == "/dev/null"


def disk_text(name):
    if is_masked(name):
        return None
    _, p = unit_file(name)
    if p is None:
        return None
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None


def parse_unit(text):
    """{'sections': {name: [(key, value, lineno)]}, 'errors': [(lineno, msg)]}"""
    secs, errs, cur = {}, [], None
    buf, start = "", 0
    for no, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if buf:
            line = buf + line
            buf = ""
        else:
            start = no
        if not line or line.startswith(("#", ";")):
            continue
        if line.endswith("\\"):
            buf = line[:-1] + " "
            continue
        if line.startswith("["):
            if not line.endswith("]"):
                errs.append((start, f"Invalid section header '{line}'"))
                continue
            cur = line[1:-1].strip()
            secs.setdefault(cur, [])
            continue
        if "=" not in line:
            errs.append((start, f"Missing '=', ignoring line."))
            continue
        if cur is None:
            errs.append((start, "Assignment outside of section. Ignoring."))
            continue
        k, _, v = line.partition("=")
        secs[cur].append((k.strip(), v.strip(), start))
    return {"sections": secs, "errors": errs}


def uget(cfg, sec, key, default=None):
    vals = [v for k, v, _ in cfg["sections"].get(sec, []) if k == key]
    return vals[-1] if vals else default


def ugetall(cfg, sec, key):
    out = []
    for k, v, _ in cfg["sections"].get(sec, []):
        if k == key:
            if v == "":
                out = []
            else:
                out += v.split()
    return out


def uline(cfg, sec, key):
    lines = [n for k, _, n in cfg["sections"].get(sec, []) if k == key]
    return lines[-1] if lines else 0


def exec_path(cmdline):
    tok = (cmdline or "").split()
    if not tok:
        return ""
    return tok[0].lstrip("-@:+!")


# ------------------------------------------------------------------ unit records
def ensure(st, name):
    u = st["units"].get(name)
    if u is None:
        path, p = unit_file(name)
        if p is None:
            return None
        u = {"path": path, "loaded": disk_text(name), "active": "inactive", "sub": "dead", "result": "success",
             "pid": 0, "since": None, "status": None, "nrestarts": 0, "behavior": {}, "bad": None}
        st["units"][name] = u
    if u.get("loaded") is None and not is_masked(name):
        t = disk_text(name)
        if t is not None:
            u["loaded"] = t
            u["path"] = unit_file(name)[0]
    return u


def install_targets(name, text=None):
    text = disk_text(name) if text is None else text
    if text is None:
        return []
    cfg = parse_unit(text)
    return ugetall(cfg, "Install", "WantedBy") + ugetall(cfg, "Install", "RequiredBy")


def enabled_state(name):
    if is_masked(name):
        return "masked"
    text = disk_text(name)
    if text is None:
        return None
    wants = list(R("/etc/systemd/system").glob(f"*.wants/{name}")) + list(R("/etc/systemd/system").glob(f"*.requires/{name}"))
    if wants:
        return "enabled"
    if not install_targets(name, text):
        return "static"
    return "disabled"


def changed_on_disk(name, u):
    d = disk_text(name)
    return u is not None and u.get("loaded") is not None and d is not None and d != u["loaded"]


def desc_of(name, u):
    cfg = parse_unit(u.get("loaded") or "")
    d = uget(cfg, "Unit", "Description")
    return f"{name} - {d}" if d else name


def daemon_reload(st):
    for name, u in list(st["units"].items()):
        t = disk_text(name)
        u["loaded"] = t
        u["bad"] = None
        if t is not None:
            u["path"] = unit_file(name)[0]


def validate_exec(cfg, u, name):
    """設定ミス（bad-setting）のチェック。journal メッセージのリストを返す（問題なければ []）。"""
    msgs = []
    for ln, m in cfg["errors"]:
        msgs.append(f"{u['path']}:{ln}: {m}")
    es = uget(cfg, "Service", "ExecStart")
    if not es:
        msgs.append(f"{name}: Service has no ExecStart=, ExecStop=, or SuccessAction=. Refusing.")
        return msgs
    exe = exec_path(es)
    if not exe.startswith("/"):
        if "/" in exe:
            msgs.append(f"{u['path']}:{uline(cfg, 'Service', 'ExecStart')}: Neither a valid executable name nor an absolute path: {exe}")
            msgs.append(f"{name}: Unit configuration has fatal error, unit will not be started.")
            return msgs
        for d in ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"):
            if (R(d) / exe).is_file():
                return msgs
        msgs.append(f"{name}: Unable to locate executable '{exe}': No such file or directory")
        msgs.append(f"{name}: Unit configuration has fatal error, unit will not be started.")
        return msgs
    rs = uget(cfg, "Service", "Restart")
    if rs and rs not in ("no", "on-success", "on-failure", "on-abnormal", "on-watchdog", "on-abort", "always"):
        msgs.append(f"{u['path']}:{uline(cfg, 'Service', 'Restart')}: Failed to parse service restart specifier, ignoring: {rs}")
    return msgs if msgs and any("fatal" in m or "Refusing" in m for m in msgs) else []


def users_db():
    return {r[0]: r for r in read_db("passwd")}


def runtime_failure(st, cfg, u, name):
    """起動時に失敗する原因があれば (status, [(ident, prio, msg)]) を返す。"""
    es = uget(cfg, "Service", "ExecStart")
    exe = exec_path(es)
    if not exe.startswith("/"):
        for d in ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"):
            if (R(d) / exe).is_file():
                exe = f"{d}/{exe}"
                break
    user = uget(cfg, "Service", "User")
    if user and R("/etc/passwd").exists() and user not in users_db():
        return "217/USER", [("systemd", 3, f"{name}: Failed to determine user credentials: No such process"),
                            ("systemd", 3, f"{name}: Failed at step USER spawning {exe}: No such process")]
    wd = uget(cfg, "Service", "WorkingDirectory")
    if wd and not wd.startswith("~") and not R(wd.lstrip("-")).is_dir() and not wd.startswith("-"):
        return "200/CHDIR", [("systemd", 3, f"{name}: Changing to the requested working directory failed: No such file or directory"),
                             ("systemd", 3, f"{name}: Failed at step CHDIR spawning {exe}: No such file or directory")]
    p = R(exe)
    if not p.is_file():
        return "203/EXEC", [("systemd", 3, f"{name}: Failed to locate executable {exe}: No such file or directory"),
                            ("systemd", 3, f"{name}: Failed at step EXEC spawning {exe}: No such file or directory")]
    if not os.access(p, os.X_OK):
        return "203/EXEC", [("systemd", 3, f"{name}: Failed to execute {exe}: Permission denied"),
                            ("systemd", 3, f"{name}: Failed at step EXEC spawning {exe}: Permission denied")]
    beh = u.get("behavior") or {}
    for other in beh.get("conflicts", []):
        o = st["units"].get(other)
        if o and o.get("active") == "active":
            ident = beh.get("ident") or os.path.basename(exe)
            return "1/FAILURE", [(ident, int(x[0]), fmt_beh(x[1], cfg)) for x in beh.get("fail_log", [[3, "fatal error"]])]
    return None


def fmt_beh(msg, cfg):
    es = uget(cfg, "Service", "ExecStart") or ""
    m = re.search(r"--port[= ](\d+)", es)
    return msg.replace("{port}", m.group(1) if m else "8080")


def do_start(st, name):
    u = ensure(st, name)
    if is_masked(name):
        return 1, f"Failed to start {name}: Unit {name} is masked."
    if u is None or u.get("loaded") is None:
        return 5, f"Failed to start {name}: Unit {name} not found."
    if u["active"] == "active":
        return 0, ""
    cfg = parse_unit(u["loaded"])
    desc = desc_of(name, u)
    typ = uget(cfg, "Service", "Type", "simple")
    bad = validate_exec(cfg, u, name)
    if bad:
        for m in bad:
            log(st, name, "systemd", 1, m, prio=3)
        u["bad"] = "bad-setting"
        return 1, f"Failed to start {name}: Unit {name} has a bad unit file setting.\nSee system logs and 'systemctl status {name}' for details."
    u["bad"] = None
    log(st, name, "systemd", 1, f"Starting {desc}...")
    pid = new_pid(st)
    fail = runtime_failure(st, cfg, u, name)
    beh = u.get("behavior") or {}
    ident = beh.get("ident") or os.path.basename(exec_path(uget(cfg, "Service", "ExecStart")))
    if fail is None:
        u.update(active="active", sub="running", pid=pid, since=time.time(), result="success", status=None,
                 run_text=u["loaded"])
        for pr, msg in beh.get("ok_log", []):
            log(st, name, ident, pid, fmt_beh(msg, cfg), prio=int(pr))
        log(st, name, "systemd", 1, f"Started {desc}.")
        return 0, ""
    status, lines = fail
    if typ == "simple":
        log(st, name, "systemd", 1, f"Started {desc}.")
    restart = uget(cfg, "Service", "Restart", "no")
    attempts = 6 if restart in ("on-failure", "always", "on-abnormal") else 1
    for i in range(attempts):
        for idn, pr, msg in lines:
            log(st, name, idn, pid if idn != "systemd" else 1, msg, prio=pr)
        log(st, name, "systemd", 1, f"{name}: Main process exited, code=exited, status={status}", prio=5)
        log(st, name, "systemd", 1, f"{name}: Failed with result 'exit-code'.", prio=4)
        if i < attempts - 1:
            log(st, name, "systemd", 1, f"{name}: Scheduled restart job, restart counter is at {i + 1}.")
            log(st, name, "systemd", 1, f"Stopped {desc}.")
            log(st, name, "systemd", 1, f"Starting {desc}...")
            pid = new_pid(st)
            if typ == "simple":
                log(st, name, "systemd", 1, f"Started {desc}.")
    if attempts > 1:
        log(st, name, "systemd", 1, f"{name}: Start request repeated too quickly.", prio=4)
        log(st, name, "systemd", 1, f"{name}: Failed with result 'exit-code'.", prio=4)
    if typ != "simple" or attempts > 1:
        log(st, name, "systemd", 1, f"Failed to start {desc}.", prio=3)
    u.update(active="failed", sub="failed", pid=pid, since=time.time(), result="exit-code", status=status,
             nrestarts=attempts - 1, exec_line=uget(cfg, "Service", "ExecStart"))
    if typ == "simple":
        return 0, ""   # Type=simple は fork した時点で「起動成功」扱い（その後すぐ落ちても start は成功を返す）
    return 1, (f"Job for {name} failed because the control process exited with error code.\n"
               f"See \"systemctl status {name}\" and \"journalctl -xeu {name}\" for details.")


def do_stop(st, name):
    u = ensure(st, name)
    if u is None:
        return 5, f"Failed to stop {name}: Unit {name} not loaded."
    desc = desc_of(name, u)
    if u["active"] == "active":
        log(st, name, "systemd", 1, f"Stopping {desc}...")
        log(st, name, "systemd", 1, f"{name}: Deactivated successfully.")
        log(st, name, "systemd", 1, f"Stopped {desc}.")
        u.update(active="inactive", sub="dead", pid=0, since=time.time(), result="success", status=None)
    return 0, ""


def rel_link(target_abs, link_path):
    return os.path.relpath(R(target_abs), link_path.parent)


def do_enable(st, name, out):
    if is_masked(name):
        return 1, f"Failed to enable unit: Unit file /etc/systemd/system/{name} is masked."
    path, p = unit_file(name)
    if p is None:
        return 1, f"Failed to enable unit: Unit file {name} does not exist."
    targets = install_targets(name)
    if not targets:
        out.append(f"The unit files have no installation config (WantedBy=, RequiredBy=, UpheldBy=,\n"
                   f"Also=, or Alias= settings in the [Install] section, and DefaultInstance= for\n"
                   f"template units). This means they are not meant to be enabled or disabled using systemctl.\n"
                   f" \nPossible reasons for having these kinds of units are:\n"
                   f"• A unit may be statically enabled by being symlinked from another unit's\n"
                   f"  .wants/, .requires/, or .upholds/ directory.\n"
                   f"• A unit's purpose may be to act as a helper for some other unit which has\n"
                   f"  a requirement dependency on it.\n"
                   f"• A unit may be started when needed via activation (socket, path, timer,\n"
                   f"  D-Bus, udev, scripted systemctl call, ...).\n"
                   f"• In case of template units, the unit is meant to be enabled with some\n"
                   f"  instance name specified.")
        return 0, ""
    for t in targets:
        d = R("/etc/systemd/system") / f"{t}.wants"
        d.mkdir(parents=True, exist_ok=True)
        link = d / name
        if not os.path.lexists(link):
            os.symlink(rel_link(path, link), link)
            out.append(f"Created symlink /etc/systemd/system/{t}.wants/{name} → {path}.")
    return 0, ""


def do_disable(st, name, out):
    for link in sorted(list(R("/etc/systemd/system").glob(f"*.wants/{name}")) + list(R("/etc/systemd/system").glob(f"*.requires/{name}"))):
        rel = "/" + str(link.relative_to(R()))
        link.unlink()
        out.append(f'Removed "{rel}".')
    return 0, ""


# ------------------------------------------------------------------ systemctl
def proc_tree(name, u, cfg):
    beh = u.get("behavior") or {}
    exe = uget(cfg, "Service", "ExecStart") or ""
    kids = beh.get("children")
    lines = [f'{u["pid"]} "{beh.get("comm_line", exe)}"' if beh.get("comm_line") else f"{u['pid']} {exe}"]
    for i, k in enumerate(kids or []):
        lines.append(f'{u["pid"] + 1 + i} "{k}"')
    out = []
    for i, ln in enumerate(lines):
        out.append(("└─" if i == len(lines) - 1 else "├─") + ln)
    return out


def bullet(state):
    color = sys.stdout.isatty()
    if state == "active":
        return "\x1b[0;1;32m●\x1b[0m" if color else "●"
    if state == "failed":
        return "\x1b[0;1;31m×\x1b[0m" if color else "×"
    return "○"


def journal_lines_for(st, name, n=10):
    ents = sorted([e for e in st["journal"] if e.get("unit") == name], key=lambda e: e["ts"])[-n:]
    return [fmt_entry(st, e, "short") for e in ents]


def status_one(st, name, full=True):
    out = []
    u = ensure(st, name)
    if is_masked(name):
        out += [f"○ {name}", f"     Loaded: masked (Reason: Unit {name} is masked.)", "     Active: inactive (dead)"]
        return 3, out
    if u is None or u.get("loaded") is None:
        return 4, None
    cfg = parse_unit(u["loaded"])
    desc = uget(cfg, "Unit", "Description")
    out.append(f"{bullet(u['active'])} {name}" + (f" - {desc}" if desc else ""))
    en = enabled_state(name) or "disabled"
    if u.get("bad"):
        out.append(f"     Loaded: bad-setting (Reason: Unit {name} has a bad unit file setting.)")
    else:
        out.append(f"     Loaded: loaded ({u['path']}; {en}; preset: enabled)")
    since = f" since {ts_long(u['since'])}; {ago(u['since'])}" if u.get("since") else ""
    if u["active"] == "active":
        out.append(f"     Active: active (running){since}")
    elif u["active"] == "failed":
        out.append(f"     Active: failed (Result: {u.get('result', 'exit-code')}){since}")
    else:
        out.append(f"     Active: inactive (dead){since}")
    docs = uget(cfg, "Unit", "Documentation")
    if docs:
        out.append(f"       Docs: {docs}")
    if u["active"] == "failed" and u.get("pid"):
        out.append(f"    Process: {u['pid']} ExecStart={u.get('exec_line') or uget(cfg, 'Service', 'ExecStart')} (code=exited, status={u.get('status')})")
        out.append(f"   Main PID: {u['pid']} (code=exited, status={u.get('status')})")
        out.append("        CPU: 12ms")
    if u["active"] == "active":
        beh = u.get("behavior") or {}
        comm = beh.get("comm") or os.path.basename(exec_path(uget(cfg, "Service", "ExecStart")))
        out.append(f"   Main PID: {u['pid']} ({comm})")
        out.append(f"      Tasks: {1 + len(beh.get('children') or [])} (limit: 4558)")
        out.append(f"     Memory: {beh.get('memory', '6.4M')} (peak: {beh.get('memory_peak', '8.1M')})")
        out.append("        CPU: 41ms")
        out.append(f"     CGroup: /system.slice/{name}")
        out += ["             " + x for x in proc_tree(name, u, cfg)]
    if changed_on_disk(name, u):
        out.append("")
        out.append(f"Warning: The unit file, source configuration file or drop-ins of {name} changed on disk. Run 'systemctl daemon-reload' to reload units.")
    jl = journal_lines_for(st, name)
    if jl:
        out.append("")
        out += jl
    return (0 if u["active"] == "active" else 3), out


def warn_changed(st, name):
    u = st["units"].get(name)
    if changed_on_disk(name, u):
        err(f"Warning: The unit file, source configuration file or drop-ins of {name} changed on disk. Run 'systemctl daemon-reload' to reload units.")


SHOW_PROPS = ["Type", "Restart", "MainPID", "Result", "NRestarts", "ExecStart", "ActiveState", "SubState",
              "UnitFileState", "LoadState", "FragmentPath", "Description", "User", "WantedBy", "NeedDaemonReload"]


def show_props(st, name):
    u = ensure(st, name)
    if u is None:
        return {"Id": name, "LoadState": "not-found", "ActiveState": "inactive", "SubState": "dead", "MainPID": "0"}
    cfg = parse_unit(u.get("loaded") or "")
    es = uget(cfg, "Service", "ExecStart") or ""
    return {
        "Id": name, "Type": uget(cfg, "Service", "Type", "simple"), "Restart": uget(cfg, "Service", "Restart", "no"),
        "MainPID": str(u["pid"] if u["active"] == "active" else 0), "Result": u.get("result", "success"),
        "NRestarts": str(u.get("nrestarts", 0)),
        "ExecStart": f"{{ path={exec_path(es)} ; argv[]={es} ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }}" if es else "",
        "ActiveState": u["active"], "SubState": u["sub"], "UnitFileState": enabled_state(name) or "",
        "LoadState": "masked" if is_masked(name) else ("bad-setting" if u.get("bad") else "loaded"),
        "FragmentPath": u.get("path", ""), "Description": uget(cfg, "Unit", "Description", name),
        "User": uget(cfg, "Service", "User", ""), "WantedBy": " ".join(install_targets(name)),
        "NeedDaemonReload": "yes" if changed_on_disk(name, u) else "no",
    }


def all_unit_names(st):
    names = set(st["units"])
    for d in UNIT_DIRS:
        p = R(d)
        if p.is_dir():
            for f in p.iterdir():
                if re.search(r"\.(service|timer|socket)$", f.name) and not f.is_dir():
                    names.add(f.name)
    return sorted(names)


SYSTEMCTL_HELP = """systemctl [OPTIONS...] COMMAND ...

Query or send control commands to the system manager.（LinuxQuest 模擬版）

Unit Commands:
  list-units [PATTERN...]             List units currently in memory
  status [PATTERN...|PID...]          Show runtime status of one or more units
  show [PATTERN...|JOB...]            Show properties of one or more units
  cat PATTERN...                      Show files and drop-ins of specified units
  start UNIT...                       Start (activate) one or more units
  stop UNIT...                        Stop (deactivate) one or more units
  reload UNIT...                      Reload one or more units
  restart UNIT...                     Start or restart one or more units
  is-active PATTERN...                Check whether units are active
  is-failed PATTERN...                Check whether units are failed
  reset-failed [PATTERN...]           Reset failed state for all, one, or more units

Unit File Commands:
  list-unit-files [PATTERN...]        List installed unit files
  enable [UNIT...|PATH...]            Enable one or more unit files
  disable UNIT...                     Disable one or more unit files
  is-enabled UNIT...                  Check whether unit files are enabled
  mask UNIT...                        Mask one or more units
  unmask UNIT...                      Unmask one or more units
  edit UNIT...                        Edit one or more unit files

Manager State Commands:
  daemon-reload                       Reload systemd manager configuration

Options:
     --now        Start or stop unit after enabling or disabling it
  -t --type=TYPE  List units of a particular type
     --state=STATE  List units with particular LOAD or SUB or ACTIVE state
     --failed     Shortcut for --state=failed
  -p --property=NAME  Show only properties by this name
     --value      When showing properties, only print the value
"""

MUTATING = {"start", "stop", "restart", "reload", "try-restart", "reload-or-restart", "enable", "disable",
            "mask", "unmask", "daemon-reload", "reset-failed", "edit", "kill", "daemon-reexec"}


def systemctl(argv):
    opts = {"now": False, "props": [], "value": False, "type": None, "state": None, "all": False, "quiet": False}
    words = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(SYSTEMCTL_HELP)
            return 0
        if a == "--version":
            print("systemd 255 (255.4-1ubuntu8-lq)\n+PAM +AUDIT +SELINUX +APPARMOR (LinuxQuest simulation)")
            return 0
        if a == "--now":
            opts["now"] = True
        elif a in ("--value",):
            opts["value"] = True
        elif a in ("-p", "--property"):
            i += 1
            opts["props"] += argv[i].split(",") if i < len(argv) else []
        elif a.startswith("--property="):
            opts["props"] += a.split("=", 1)[1].split(",")
        elif a.startswith("-p") and len(a) > 2:
            opts["props"] += a[2:].split(",")
        elif a in ("-t", "--type"):
            i += 1
            opts["type"] = argv[i] if i < len(argv) else None
        elif a.startswith("--type="):
            opts["type"] = a.split("=", 1)[1]
        elif a.startswith("--state="):
            opts["state"] = a.split("=", 1)[1]
        elif a == "--failed":
            opts["state"] = "failed"
        elif a in ("-a", "--all"):
            opts["all"] = True
        elif a in ("-q", "--quiet"):
            opts["quiet"] = True
        elif a == "--user":
            err("Failed to connect to bus: No medium found")
            err(dim("[LinuxQuest 模擬] --user（ユーザー単位のサービス）はこの訓練では扱いません。--user を外しましょう。"))
            return 1
        elif a in ("--no-pager", "-l", "--full", "--no-legend", "--plain", "--no-block", "--no-reload", "-f",
                   "--force", "--no-ask-password", "--system", "-n0"):
            pass
        elif a.startswith("-n") or a.startswith("--lines"):
            if a in ("-n", "--lines"):
                i += 1
        elif a.startswith("-") and len(a) > 1:
            err(f"systemctl: unrecognized option '{a}'")
            return 1
        else:
            words.append(a)
        i += 1
    cmd = words[0] if words else "list-units"
    args = words[1:]
    st = load()
    if cmd in MUTATING and not is_root():
        what = {"daemon-reload": "Failed to reload daemon", "enable": "Failed to enable unit", "disable": "Failed to disable unit",
                "mask": "Failed to mask unit", "unmask": "Failed to unmask unit", "edit": "Failed to edit"}
        if cmd in what:
            err(f"{what[cmd]}: Access denied")
        else:
            for a in args[:1] or [""]:
                err(f"Failed to {cmd} {uname(a) if a else ''}: Interactive authentication required.\nSee system logs and 'systemctl status {uname(a) if a else ''}' for details.")
        sudo_hint()
        return 1
    code = 0
    out = []

    def need_args():
        if not args:
            err(f"Too few arguments.")
            return False
        return True

    if cmd == "daemon-reload":
        daemon_reload(st)
    elif cmd in ("start", "restart", "stop", "reload", "try-restart", "reload-or-restart"):
        if not need_args():
            return 1
        for a in args:
            n = uname(a)
            warn_changed(st, n)
            if cmd == "stop":
                c, m = do_stop(st, n)
            elif cmd in ("restart", "reload-or-restart"):
                if ensure(st, n) is None and not is_masked(n):
                    c, m = 5, f"Failed to restart {n}: Unit {n} not found."
                else:
                    do_stop(st, n)
                    c, m = do_start(st, n)
                    m = m.replace("Failed to start", "Failed to restart")
            elif cmd == "try-restart":
                u = ensure(st, n)
                c, m = 0, ""
                if u and u["active"] == "active":
                    do_stop(st, n)
                    c, m = do_start(st, n)
            elif cmd == "reload":
                u = ensure(st, n)
                if u is None:
                    c, m = 5, f"Failed to reload {n}: Unit {n} not found."
                elif not uget(parse_unit(u.get("loaded") or ""), "Service", "ExecReload"):
                    c, m = 1, f"Failed to reload {n}: Job type reload is not applicable for unit {n}."
                elif u["active"] != "active":
                    c, m = 1, f"Failed to reload {n}: Unit {n} is not active."
                else:
                    log(st, n, "systemd", 1, f"Reloading {desc_of(n, u)}...")
                    log(st, n, "systemd", 1, f"Reloaded {desc_of(n, u)}.")
                    c, m = 0, ""
            else:
                c, m = do_start(st, n)
            if m:
                err(m)
            code = code or c
    elif cmd in ("enable", "disable", "reenable"):
        if not need_args():
            return 1
        for a in args:
            n = uname(a)
            if cmd in ("disable", "reenable"):
                c, m = do_disable(st, n, out)
                if c == 0 and opts["now"] and cmd == "disable":
                    do_stop(st, n)
            if cmd in ("enable", "reenable"):
                c, m = do_enable(st, n, out)
                if m:
                    for ln in out:
                        print(ln)
                    out = []
                    err(m)
                    code = 1
                    continue
            daemon_reload(st)   # enable/disable は暗黙に daemon-reload する（本物と同じ）
            if cmd == "enable" and opts["now"]:
                c2, m2 = do_start(st, n)
                if m2:
                    for ln in out:
                        print(ln)
                    out = []
                    err(m2)
                    code = code or c2
    elif cmd in ("mask", "unmask"):
        if not need_args():
            return 1
        for a in args:
            n = uname(a)
            link = R("/etc/systemd/system") / n
            if cmd == "mask":
                if os.path.lexists(link) and not is_masked(n):
                    err(f"Failed to mask unit: File /etc/systemd/system/{n} already exists.")
                    code = 1
                    continue
                if not is_masked(n):
                    link.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink("/dev/null", link)
                    out.append(f"Created symlink /etc/systemd/system/{n} → /dev/null.")
            else:
                if is_masked(n):
                    link.unlink()
                    out.append(f'Removed "/etc/systemd/system/{n}".')
            daemon_reload(st)
    elif cmd == "reset-failed":
        for n in ([uname(a) for a in args] or list(st["units"])):
            u = st["units"].get(n)
            if u and u["active"] == "failed":
                u.update(active="inactive", sub="dead", result="success")
    elif cmd == "status":
        if not args:
            failed = [n for n, u in st["units"].items() if u["active"] == "failed"]
            dot = "\x1b[0;1;31m●\x1b[0m" if failed and sys.stdout.isatty() else "●"
            out += [f"{dot} {st['host']}", f"    State: {'degraded' if failed else 'running'}", "    Units: 241 loaded (incl. loaded aliases)",
                    "     Jobs: 0 queued", f"   Failed: {len(failed)} units", f"    Since: {ts_long(st['boots'][-1]['start'])}; {ago(st['boots'][-1]['start'])}",
                    "  systemd: 255.4-1ubuntu8", "   CGroup: /", "           ├─init.scope", "           │ └─1 /sbin/init", "           └─system.slice"]
            for n, u in sorted(st["units"].items()):
                if u["active"] == "active":
                    out.append(f"             ├─{n}")
                    out.append(f"             │ └─{u['pid']} {uget(parse_unit(u.get('loaded') or ''), 'Service', 'ExecStart') or ''}")
        else:
            blocks = []
            for a in args:
                n = uname(a)
                c, lines = status_one(st, n)
                if lines is None:
                    err(f"Unit {n} could not be found.")
                    code = code or 4
                    continue
                blocks.append(lines)
                code = code or c
            for k, b in enumerate(blocks):
                if k:
                    out.append("")
                out += b
    elif cmd in ("is-active", "is-failed", "is-enabled"):
        if not need_args():
            return 1
        code = None
        for a in args:
            n = uname(a)
            if cmd == "is-enabled":
                s = enabled_state(n)
                if s is None:
                    err(f"Failed to get unit file state for {n}: No such file or directory")
                    c = 1
                else:
                    out.append(s)
                    c = 0 if s in ("enabled", "static", "alias", "indirect", "generated") else 1
            else:
                u = st["units"].get(n) or ensure(st, n)
                s = u["active"] if u else "inactive"
                out.append(s)
                if cmd == "is-active":
                    c = 0 if s == "active" else (4 if u is None else 3)
                else:
                    c = 0 if s == "failed" else 1
            code = c if code is None else (code if code != 0 else c)
        if opts["quiet"]:
            out = []
        code = code or 0
    elif cmd in ("list-units", "list-unit-files"):
        names = all_unit_names(st)
        if opts["type"]:
            names = [n for n in names if n.endswith("." + opts["type"])]
        if args:
            names = [n for n in names if any(fnmatch.fnmatch(n, p) or fnmatch.fnmatch(n, uname(p)) for p in args)]
        if cmd == "list-units":
            rows = []
            for n in names:
                u = ensure(st, n)
                if not u:
                    continue
                if u["active"] == "inactive" and not opts["all"] and opts["state"] not in ("inactive", "dead"):
                    continue
                if opts["state"] and opts["state"] not in (u["active"], u["sub"]):
                    continue
                d = uget(parse_unit(u.get("loaded") or ""), "Unit", "Description", n)
                mark = "●" if u["active"] == "failed" else " "
                rows.append((mark, n, "loaded", u["active"], u["sub"], d))
            w = max([len(r[1]) for r in rows] + [4]) + 1
            out.append(f"  {'UNIT':<{w}} LOAD   ACTIVE   SUB     DESCRIPTION")
            for r in rows:
                out.append(f"{r[0]} {r[1]:<{w}} {r[2]:<6} {r[3]:<8} {r[4]:<7} {r[5]}")
            out += ["", "Legend: LOAD   → Reflects whether the unit definition was properly loaded.",
                    "        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.",
                    "        SUB    → The low-level unit activation state, values depend on unit type.", "",
                    f"{len(rows)} loaded units listed." + ("" if opts["all"] else " Pass --all to see loaded but inactive units, too.")]
        else:
            w = max([len(n) for n in names] + [9]) + 1
            out.append(f"{'UNIT FILE':<{w}} STATE    PRESET")
            k = 0
            for n in names:
                s = enabled_state(n)
                if s is None:
                    continue
                if opts["state"] and s != opts["state"]:
                    continue
                k += 1
                out.append(f"{n:<{w}} {s:<8} enabled")
            out += ["", f"{k} unit files listed."]
    elif cmd == "cat":
        if not need_args():
            return 1
        for k, a in enumerate(args):
            n = uname(a)
            t = disk_text(n)
            if t is None:
                err(f"No files found for {n}." if not is_masked(n) else f"Unit {n} is masked.")
                code = 1
                continue
            warn_changed(st, n)
            if k:
                out.append("")
            out.append(f"# {unit_file(n)[0]}")
            out += t.rstrip("\n").splitlines()
    elif cmd == "show":
        if not args:
            out += [f"Version=255.4-1ubuntu8", f"Architecture=x86-64", f"SystemState=running"]
        for k, a in enumerate(args):
            n = uname(a)
            props = show_props(st, n)
            keys = opts["props"] or list(props)
            if k:
                out.append("")
            for key in keys:
                v = props.get(key, "")
                out.append(v if opts["value"] else f"{key}={v}")
    elif cmd == "edit":
        if not need_args():
            return 1
        n = uname(args[0])
        path, p = unit_file(n)
        if p is None:
            if "--force" not in argv and "--full" not in argv:
                err(f"Run 'systemctl edit --force --full {n}' to create a new unit.")
                return 1
            p = R("/etc/systemd/system") / n
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not str(path).startswith("/etc/"):
            dst = R("/etc/systemd/system") / n
            if not dst.exists():
                shutil.copy(p, dst)
            p = dst
        editor = os.environ.get("SYSTEMD_EDITOR") or os.environ.get("EDITOR") or os.environ.get("VISUAL") or (
            shutil.which("nano") and "nano") or "vi"
        err(dim(f"[LinuxQuest 模擬] {editor} で sysroot{('/etc/systemd/system/' + n)} を編集します（保存して終了すると自動で daemon-reload されます）"))
        subprocess.call([*editor.split(), str(p)])
        daemon_reload(st)
    elif cmd == "list-timers":
        out.append("NEXT LEFT LAST PASSED UNIT ACTIVATES\n\n0 timers listed.")
    elif cmd in ("poweroff", "reboot", "halt", "suspend"):
        err(dim(f"[LinuxQuest 模擬] 訓練サーバーなので {cmd} は実行しません 😉"))
        return 1
    else:
        err(f"Unknown command verb '{cmd}'.")
        return 1
    save(st)
    for ln in out:
        print(ln)
    return code


# ------------------------------------------------------------------ journalctl
def fmt_entry(st, e, mode="short", host=True):
    ident = e["ident"]
    if ident == "kernel":
        src = "kernel"
    else:
        src = f"{ident}[{e['pid']}]"
    h = f"{st['host']} " if host else ""
    if mode == "cat":
        return e["msg"]
    if mode == "json":
        return json.dumps({"__REALTIME_TIMESTAMP": str(int(e["ts"] * 1e6)), "_HOSTNAME": st["host"],
                           "PRIORITY": str(e["prio"]), "SYSLOG_IDENTIFIER": ident, "_PID": str(e["pid"]),
                           "_SYSTEMD_UNIT": e.get("unit") or "", "MESSAGE": e["msg"],
                           "_BOOT_ID": st["boots"][e["boot"]]["id"]}, ensure_ascii=False)
    if mode == "short-iso":
        t = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(e["ts"]))
        return f"{t} {h}{src}: {e['msg']}"
    if mode == "short-precise":
        return f"{ts_short(e['ts'])}.{int((e['ts'] % 1) * 1e6):06d} {h}{src}: {e['msg']}"
    return f"{ts_short(e['ts'])} {h}{src}: {e['msg']}"


def parse_time(s, now=None):
    now = now or time.time()
    s0 = s.strip()
    s = s0.lower()
    today = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "now":
        return now
    if s == "today":
        return today.timestamp()
    if s == "yesterday":
        return (today - timedelta(days=1)).timestamp()
    if s == "tomorrow":
        return (today + timedelta(days=1)).timestamp()
    units = {"s": 1, "sec": 1, "second": 1, "seconds": 1, "secs": 1, "m": 60, "min": 60, "mins": 60, "minute": 60,
             "minutes": 60, "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600, "d": 86400, "day": 86400,
             "days": 86400, "w": 604800, "week": 604800, "weeks": 604800}
    m = re.fullmatch(r"([+-])?\s*((?:\d+\s*[a-z]+\s*)+)(ago)?", s)
    if m and (m.group(1) or m.group(3)):
        total = 0
        for num, u in re.findall(r"(\d+)\s*([a-z]+)", m.group(2)):
            if u not in units:
                return None
            total += int(num) * units[u]
        return now + total if m.group(1) == "+" and not m.group(3) else now - total
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s0, fmt).timestamp()
        except ValueError:
            pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s0, fmt)
            return today.replace(hour=t.hour, minute=t.minute, second=t.second).timestamp()
        except ValueError:
            pass
    return None


def parse_prio(s):
    def one(x):
        x = x.strip().lower()
        if x.isdigit() and 0 <= int(x) <= 7:
            return int(x)
        if x in PRIOS:
            return PRIOS.index(x)
        if x in ("error",):
            return 3
        if x in ("warn",):
            return 4
        return None
    if ".." in s:
        a, b = s.split("..", 1)
        lo, hi = one(a) if a else 0, one(b) if b else 7
        if lo is None or hi is None:
            return None
        return (min(lo, hi), max(lo, hi))
    v = one(s)
    return None if v is None else (0, v)


def journalctl(argv):
    o = {"units": [], "prio": None, "n": None, "since": None, "until": None, "boot": None, "reverse": False,
         "follow": False, "mode": "short", "ident": [], "grep": None, "kernel": False, "list_boots": False,
         "host": True, "pager_end": False, "disk": False}
    WITH_ARG = {"u": "unit", "p": "priority", "t": "identifier", "g": "grep", "o": "output", "S": "since", "U": "until"}
    OPTIONAL = {"n": "lines", "b": "boot"}

    def setopt(key, val):
        if key == "unit":
            o["units"].append(val)
        elif key == "priority":
            pr = parse_prio(val)
            if pr is None:
                raise ValueError(f"Failed to parse priority value: {val}")
            o["prio"] = pr
        elif key == "identifier":
            o["ident"].append(val)
        elif key == "grep":
            o["grep"] = val
        elif key == "output":
            if val not in ("short", "short-iso", "short-precise", "cat", "json", "verbose", "short-full", "json-pretty", "with-unit"):
                raise ValueError(f"Unknown output format '{val}'.")
            o["mode"] = {"verbose": "short", "short-full": "short", "json-pretty": "json", "with-unit": "short"}.get(val, val)
        elif key in ("since", "until"):
            t = parse_time(val)
            if t is None:
                raise ValueError(f"Failed to parse timestamp: {val}")
            o[key] = t
        elif key == "lines":
            if val in (None, "", "all"):
                o["n"] = 10 if val is None else None
            else:
                if not re.fullmatch(r"\+?\d+", val):
                    raise ValueError(f"Failed to parse lines '{val}'")
                o["n"] = int(val.lstrip("+"))
        elif key == "boot":
            o["boot"] = "0" if val in (None, "") else val

    try:
        i = 0
        while i < len(argv):
            a = argv[i]
            nxt = argv[i + 1] if i + 1 < len(argv) else None
            if a in ("-h", "--help"):
                print("journalctl [OPTIONS...] [MATCHES...]\n\nQuery the journal.（LinuxQuest 模擬版）\n\n"
                      "  -u --unit=UNIT          Show logs from the specified unit\n"
                      "  -p --priority=RANGE     Show entries with the specified priority (emerg..debug / err / 3)\n"
                      "  -S --since=DATE         Show entries not older than the specified date\n"
                      "  -U --until=DATE         Show entries not newer than the specified date\n"
                      "  -b --boot[=ID]          Show current boot or the specified boot (-b -1 = previous)\n"
                      "     --list-boots         Show terse information about recorded boots\n"
                      "  -n --lines[=INTEGER]    Number of journal entries to show\n"
                      "  -r --reverse            Show the newest entries first\n"
                      "  -f --follow             Follow the journal\n"
                      "  -e --pager-end          Immediately jump to the end in the pager\n"
                      "  -x --catalog            Add message explanations where available\n"
                      "  -o --output=STRING      Change journal output mode (short, short-iso, cat, json, ...)\n"
                      "  -t --identifier=STRING  Show entries with the specified syslog identifier\n"
                      "  -g --grep=PATTERN       Show entries with MESSAGE matching PATTERN\n"
                      "  -k --dmesg              Show kernel message log from the current boot\n"
                      "     --no-pager           Do not pipe output into a pager\n"
                      "     --disk-usage         Show total disk usage of all journal files")
                return 0
            if a.startswith("--"):
                key, eq, val = a[2:].partition("=")
                if key in WITH_ARG.values():
                    if not eq:
                        if nxt is None:
                            raise ValueError(f"journalctl: option '--{key}' requires an argument")
                        val = nxt
                        i += 1
                    setopt(key, val)
                elif key in OPTIONAL.values():
                    if not eq:
                        val = None
                        if nxt is not None and (re.fullmatch(r"[+-]?\d+", nxt) or re.fullmatch(r"[0-9a-f]{32}", nxt) or nxt == "all"):
                            val = nxt
                            i += 1
                    setopt(key, val)
                elif key == "reverse":
                    o["reverse"] = True
                elif key == "follow":
                    o["follow"] = True
                elif key == "pager-end":
                    o["pager_end"] = True
                elif key == "dmesg":
                    o["kernel"] = True
                elif key == "list-boots":
                    o["list_boots"] = True
                elif key == "no-hostname":
                    o["host"] = False
                elif key == "disk-usage":
                    o["disk"] = True
                elif key in ("no-pager", "catalog", "quiet", "all", "utc", "no-tail", "merge", "system", "full"):
                    pass
                elif key in ("vacuum-size", "vacuum-time", "rotate"):
                    print(dim(f"[LinuxQuest 模擬] --{key} は訓練サーバーでは実行しません（本番ではジャーナルの容量削減に使います）"))
                    return 0
                else:
                    raise ValueError(f"journalctl: unrecognized option '--{key}'")
                i += 1
                continue
            if a.startswith("-") and len(a) > 1:
                j = 1
                while j < len(a):
                    ch = a[j]
                    rest = a[j + 1:]
                    if ch in WITH_ARG:
                        if rest:
                            val = rest
                        else:
                            if nxt is None:
                                raise ValueError(f"journalctl: option requires an argument -- '{ch}'")
                            val = nxt
                            i += 1
                        setopt(WITH_ARG[ch], val)
                        break
                    if ch in OPTIONAL:
                        if rest:
                            setopt(OPTIONAL[ch], rest)
                            break
                        val = None
                        if nxt is not None and (re.fullmatch(r"[+-]?\d+", nxt) or re.fullmatch(r"[0-9a-f]{32}", nxt) or nxt == "all"):
                            val = nxt
                            i += 1
                        setopt(OPTIONAL[ch], val)
                        break
                    if ch == "r":
                        o["reverse"] = True
                    elif ch == "f":
                        o["follow"] = True
                    elif ch == "e":
                        o["pager_end"] = True
                    elif ch == "k":
                        o["kernel"] = True
                    elif ch in ("x", "q", "a", "m", "l"):
                        pass
                    else:
                        raise ValueError(f"journalctl: invalid option -- '{ch}'")
                    j += 1
                i += 1
                continue
            # MATCHES (例: _SYSTEMD_UNIT=nginx.service, /usr/sbin/nginx)
            if a.startswith("_SYSTEMD_UNIT=") or a.startswith("UNIT="):
                o["units"].append(a.split("=", 1)[1])
            elif a.startswith("SYSLOG_IDENTIFIER="):
                o["ident"].append(a.split("=", 1)[1])
            elif a.startswith("PRIORITY="):
                v = int(a.split("=", 1)[1])
                o["prio"] = (v, v)
            else:
                o["ident"].append(os.path.basename(a))
            i += 1
    except ValueError as e:
        err(str(e))
        return 1
    st = load()
    if o["disk"]:
        print("Archived and active journals take up 48.0M in the file system.")
        return 0
    boots = st["boots"]
    if o["list_boots"]:
        print("IDX BOOT ID                          FIRST ENTRY                  LAST ENTRY")
        for k, b in enumerate(boots):
            ents = [e["ts"] for e in st["journal"] if e["boot"] == k] or [b["start"]]
            print(f"{k - len(boots) + 1:>3} {b['id']} {ts_long(min(ents))} {ts_long(max(ents))}")
        return 0
    ents = sorted(st["journal"], key=lambda e: e["ts"])
    if o["kernel"]:
        ents = [e for e in ents if e["ident"] == "kernel" and e["boot"] == len(boots) - 1]
    if o["boot"] is not None:
        b = o["boot"]
        if re.fullmatch(r"[0-9a-f]{32}", b):
            idx = next((k for k, x in enumerate(boots) if x["id"] == b), None)
        else:
            off = int(b)
            idx = len(boots) - 1 + off if off <= 0 else off - 1
        if idx is None or not (0 <= idx < len(boots)):
            err(f"Data from the specified boot ({b}) is not available: No such boot ID in journal")
            return 1
        ents = [e for e in ents if e["boot"] == idx]
    if o["units"]:
        pats = [uname(u) for u in o["units"]]
        ents = [e for e in ents if e.get("unit") and any(fnmatch.fnmatch(e["unit"], p) for p in pats)]
    if o["ident"]:
        ents = [e for e in ents if e["ident"] in o["ident"]]
    if o["prio"]:
        lo, hi = o["prio"]
        ents = [e for e in ents if lo <= e["prio"] <= hi]
    if o["since"] is not None:
        ents = [e for e in ents if e["ts"] >= o["since"]]
    if o["until"] is not None:
        ents = [e for e in ents if e["ts"] <= o["until"]]
    if o["grep"]:
        flags = 0 if re.search(r"[A-Z]", o["grep"]) else re.I
        try:
            rx = re.compile(o["grep"], flags)
        except re.error as e:
            err(f"Bad pattern \"{o['grep']}\": {e}")
            return 1
        ents = [e for e in ents if rx.search(e["msg"])]
    n = o["n"]
    if n is None and (o["follow"] or o["pager_end"]):
        n = 10 if o["follow"] else 1000
    if n is not None:
        ents = ents[-n:] if n > 0 else []
    if o["reverse"]:
        ents = list(reversed(ents))
    if not ents:
        print("-- No entries --")
    prev_boot = None
    try:
        for e in ents:
            if prev_boot is not None and e["boot"] != prev_boot and o["mode"] not in ("cat", "json"):
                print(f"-- Boot {boots[e['boot']]['id']} --")
            prev_boot = e["boot"]
            print(fmt_entry(st, e, o["mode"], o["host"]))
    except BrokenPipeError:
        return 0
    if o["follow"]:
        print(dim("[LinuxQuest 模擬] -f (follow) は本来、新しいログを待ち続けます（Ctrl+C で終了）。模擬環境ではここで終了します。"))
    return 0


# ------------------------------------------------------------------ users / groups
DB_FIELDS = {"passwd": 7, "group": 4, "shadow": 9}


def read_db(kind):
    p = R(f"/etc/{kind}")
    try:
        text = p.read_text()
    except OSError:
        return []
    rows = []
    for ln in text.splitlines():
        if ln.strip() and not ln.startswith("#"):
            f = ln.split(":")
            f += [""] * (DB_FIELDS[kind] - len(f))
            rows.append(f)
    return rows


def write_db(kind, rows):
    p = R(f"/etc/{kind}")
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o640 if kind == "shadow" else 0o644
    p.write_text("".join(":".join(r) + "\n" for r in rows))
    try:
        os.chmod(p, mode)
    except OSError:
        pass


def groups_of(user, pw=None, gr=None):
    pw = pw if pw is not None else read_db("passwd")
    gr = gr if gr is not None else read_db("group")
    u = next((r for r in pw if r[0] == user), None)
    if not u:
        return None
    prim = next((g for g in gr if g[2] == u[3]), None)
    out = [(prim[0], prim[2])] if prim else [(u[3], u[3])]
    for g in gr:
        if user in [x for x in g[3].split(",") if x] and (g[0], g[2]) not in out:
            out.append((g[0], g[2]))
    return out


def user_info(user):
    pw = read_db("passwd")
    u = next((r for r in pw if r[0] == user), None)
    if not u:
        return None
    return {"name": u[0], "uid": int(u[2]), "gid": int(u[3]), "gecos": u[4], "home": u[5], "shell": u[6],
            "groups": [g for g, _ in groups_of(user, pw)]}


VALID_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")


def next_id(used, lo=1000, hi=59999, system=False):
    if system:
        for i in range(999, 99, -1):
            if i not in used:
                return i
    cand = [x for x in used if lo <= x <= hi]
    n = max(cand) + 1 if cand else lo
    while n in used:
        n += 1
    return n


def _lock_fail(prog, f="/etc/passwd", code=1):
    err(f"{prog}: Permission denied.\n{prog}: cannot lock {f}; try again later.")
    sudo_hint()
    return code


def copy_skel(home, uid, gid):
    hp = R(home)
    if hp.exists():
        return False
    hp.mkdir(parents=True)
    skel = R("/etc/skel")
    if skel.is_dir():
        for f in skel.iterdir():
            if f.is_file():
                shutil.copy(f, hp / f.name)
    return True


def parse_short(argv, with_val, flags, long_map):
    """useradd/usermod 系の getopt 風パーサー。(opts, positional) / 失敗で ValueError。"""
    opts, pos, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            pos += argv[i + 1:]
            break
        if a.startswith("--"):
            key, eq, val = a[2:].partition("=")
            short = long_map.get(key)
            if short is None:
                raise ValueError(f"unrecognized option '--{key}'")
            if short in with_val:
                if not eq:
                    i += 1
                    if i >= len(argv):
                        raise ValueError(f"option '--{key}' requires an argument")
                    val = argv[i]
                opts[short] = val
            else:
                opts[short] = True
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            j = 1
            while j < len(a):
                ch = a[j]
                if ch in with_val:
                    val = a[j + 1:]
                    if not val:
                        i += 1
                        if i >= len(argv):
                            raise ValueError(f"option requires an argument -- '{ch}'")
                        val = argv[i]
                    opts[ch] = val
                    break
                if ch in flags:
                    opts[ch] = True
                else:
                    raise ValueError(f"invalid option -- '{ch}'")
                j += 1
            i += 1
            continue
        pos.append(a)
        i += 1
    return opts, pos


USERADD_USAGE = """Usage: useradd [options] LOGIN
       useradd -D
       useradd -D [options]

Options:
  -c, --comment COMMENT         GECOS field of the new account
  -d, --home-dir HOME_DIR       home directory of the new account
  -g, --gid GROUP               name or ID of the primary group of the new account
  -G, --groups GROUPS           list of supplementary groups of the new account
  -m, --create-home             create the user's home directory
  -M, --no-create-home          do not create the user's home directory
  -N, --no-user-group           do not create a group with the same name as the user
  -r, --system                  create a system account
  -s, --shell SHELL             login shell of the new account
  -u, --uid UID                 user ID of the new account
  -U, --user-group              create a group with the same name as the user
"""


def useradd(argv, prog="useradd"):
    try:
        opts, pos = parse_short(argv, set("cdgGsueKpf"), set("mMNrUDlo"),
                                {"comment": "c", "home-dir": "d", "gid": "g", "groups": "G", "shell": "s", "uid": "u",
                                 "create-home": "m", "no-create-home": "M", "no-user-group": "N", "system": "r",
                                 "user-group": "U", "expiredate": "e", "password": "p", "help": "h"})
    except ValueError as e:
        err(f"{prog}: {e}")
        err(USERADD_USAGE)
        return 2
    if opts.get("D"):
        print("GROUP=100\nHOME=/home\nINACTIVE=-1\nEXPIRE=\nSHELL=/bin/sh\nSKEL=/etc/skel\nCREATE_MAIL_SPOOL=no")
        return 0
    if len(pos) != 1:
        err(USERADD_USAGE)
        return 2
    if not is_root():
        return _lock_fail(prog)
    name = pos[0]
    if not VALID_NAME.match(name):
        err(f"{prog}: invalid user name '{name}': use --badname to ignore")
        return 3
    pw, gr, sh = read_db("passwd"), read_db("group"), read_db("shadow")
    if any(r[0] == name for r in pw):
        err(f"{prog}: user '{name}' already exists")
        return 9
    gnames = {g[0]: g for g in gr}
    gids = {g[2]: g for g in gr}
    supp = [x for x in (opts.get("G") or "").split(",") if x] if opts.get("G") else []
    for g in supp:
        if g not in gnames and g not in gids:
            err(f"{prog}: group '{g}' does not exist")
            return 6
    used_uids = {int(r[2]) for r in pw if r[2].isdigit()}
    used_gids = {int(g[2]) for g in gr if g[2].isdigit()}
    system = bool(opts.get("r"))
    if opts.get("u"):
        if not opts["u"].isdigit():
            err(f"{prog}: invalid user ID '{opts['u']}'")
            return 3
        if int(opts["u"]) in used_uids:
            err(f"{prog}: UID {opts['u']} is not unique")
            return 4
        uid = int(opts["u"])
    else:
        uid = next_id(used_uids, system=system)
    if opts.get("g"):
        g = gnames.get(opts["g"]) or gids.get(opts["g"])
        if not g:
            err(f"{prog}: group '{opts['g']}' does not exist")
            return 6
        gid = g[2]
    elif opts.get("N"):
        gid = "100"
    else:
        if name in gnames:
            err(f"{prog}: group {name} exists - if you want to add this user to that group, use -g.")
            return 9
        gid = str(uid if uid not in used_gids else next_id(used_gids, system=system))
        gr.append([name, "x", gid, ""])
    home = opts.get("d") or f"/home/{name}"
    shell = opts.get("s") or "/bin/sh"
    pw.append([name, "x", str(uid), gid, opts.get("c", ""), home, shell])
    sh.append([name, "!", str(int(time.time() // 86400)), "0", "99999", "7", "", "", ""])
    for g in gr:
        if g[0] in supp or g[2] in supp:
            mem = [x for x in g[3].split(",") if x]
            if name not in mem:
                mem.append(name)
            g[3] = ",".join(mem)
    write_db("passwd", pw)
    write_db("group", gr)
    write_db("shadow", sh)
    if opts.get("m") and not opts.get("M"):
        if not copy_skel(home, uid, gid):
            err(f"{prog}: warning: the home directory {home} already exists.\n{prog}: Not copying any file from skel directory into it.")
    return 0


def adduser(argv):
    """Debian の adduser（対話型の高水準ラッパー）。`adduser USER GROUP` でグループ追加にもなる。"""
    flags = [a for a in argv if a.startswith("-")]
    pos = [a for a in argv if not a.startswith("-")]
    gecos = None
    if "--gecos" in argv:
        k = argv.index("--gecos")
        if k + 1 < len(argv):
            gecos = argv[k + 1]
            if gecos in pos:
                pos.remove(gecos)
    if not pos:
        err("adduser: Only one or two names allowed.")
        return 1
    if not is_root():
        err("fatal: Only root may add a user or group to the system.")
        sudo_hint()
        return 1
    if len(pos) == 2:
        user, group = pos
        gr = read_db("group")
        if not any(r[0] == user for r in read_db("passwd")):
            err(f"fatal: The user `{user}' does not exist.")
            return 1
        g = next((x for x in gr if x[0] == group), None)
        if not g:
            err(f"fatal: The group `{group}' does not exist.")
            return 1
        mem = [x for x in g[3].split(",") if x]
        if user in mem:
            print(f"info: The user `{user}' is already a member of `{group}'.")
            return 0
        print(f"info: Adding user `{user}' to group `{group}' ...")
        mem.append(user)
        g[3] = ",".join(mem)
        write_db("group", gr)
        return 0
    name = pos[0]
    shell = "/bin/bash"
    if "--shell" in argv:
        k = argv.index("--shell")
        shell = argv[k + 1] if k + 1 < len(argv) else shell
        if shell in pos:
            pos.remove(shell)
    if any(r[0] == name for r in read_db("passwd")):
        err(f"fatal: The user `{name}' already exists.")
        return 1
    print(f"info: Adding user `{name}' ...")
    print(f"info: Selecting UID/GID from range 1000 to 59999 ...")
    code = useradd(["-m", "-s", shell, "-c", gecos or "", name], prog="adduser")
    if code:
        return code
    info = user_info(name)
    print(f"info: Adding new group `{name}' ({info['gid']}) ...")
    print(f"info: Adding new user `{name}' ({info['uid']}) with group `{name} ({info['gid']})' ...")
    print(f"info: Creating home directory `/home/{name}' ...")
    print(f"info: Copying files from `/etc/skel' ...")
    if "--disabled-password" not in flags:
        r = passwd([name], quiet_hint=True)
        if r:
            return r
    if gecos is None and sys.stdin.isatty():
        print(f"Changing the user information for {name}\nEnter the new value, or press ENTER for the default")
        try:
            full = input("\tFull Name []: ")
            for lab in ("Room Number", "Work Phone", "Home Phone", "Other"):
                input(f"\t{lab} []: ")
            input("Is the information correct? [Y/n] ")
        except EOFError:
            full = ""
        if full:
            pw = read_db("passwd")
            for r in pw:
                if r[0] == name:
                    r[4] = full + ",,,"
            write_db("passwd", pw)
    print(f"info: Adding user `{name}' to supplemental / extra groups `users' ...")
    gr = read_db("group")
    for g in gr:
        if g[0] == "users":
            mem = [x for x in g[3].split(",") if x]
            if name not in mem:
                mem.append(name)
            g[3] = ",".join(mem)
    write_db("group", gr)
    return 0


USERMOD_USAGE = """Usage: usermod [options] LOGIN

Options:
  -a, --append                  append the user to the supplemental GROUPS
                                mentioned by the -G option without removing
                                the user from other groups
  -c, --comment COMMENT         new value of the GECOS field
  -d, --home HOME_DIR           new home directory for the user account
  -g, --gid GROUP               force use GROUP as new primary group
  -G, --groups GROUPS           new list of supplementary GROUPS
  -l, --login NEW_LOGIN         new value of the login name
  -L, --lock                    lock the user account
  -m, --move-home               move contents of the home directory to the
                                new location (use only with -d)
  -s, --shell SHELL             new login shell for the user account
  -U, --unlock                  unlock the user account
"""


def usermod(argv):
    try:
        opts, pos = parse_short(argv, set("cdgGlseu"), set("amLUr"),
                                {"append": "a", "comment": "c", "home": "d", "gid": "g", "groups": "G", "login": "l",
                                 "lock": "L", "move-home": "m", "shell": "s", "unlock": "U", "uid": "u", "remove": "r"})
    except ValueError as e:
        err(f"usermod: {e}")
        err(USERMOD_USAGE)
        return 2
    if len(pos) != 1 or not opts:
        err(USERMOD_USAGE)
        return 2
    if (opts.get("a") or opts.get("r")) and "G" not in opts:
        err(f"usermod: {'-a' if opts.get('a') else '-r'} flag is ONLY allowed with the -G flag")
        err(USERMOD_USAGE)
        return 2
    if not is_root():
        return _lock_fail("usermod")
    name = pos[0]
    pw, gr, sh = read_db("passwd"), read_db("group"), read_db("shadow")
    u = next((r for r in pw if r[0] == name), None)
    if not u:
        err(f"usermod: user '{name}' does not exist")
        return 6
    gnames = {g[0]: g for g in gr}
    gids = {g[2]: g for g in gr}
    if "G" in opts:
        want = [x for x in opts["G"].split(",") if x]
        for g in want:
            if g not in gnames and g not in gids:
                err(f"usermod: group '{g}' does not exist")
                return 6
        want_names = {(gnames.get(g) or gids.get(g))[0] for g in want}
        for g in gr:
            mem = [x for x in g[3].split(",") if x]
            if g[0] in want_names:
                if opts.get("r"):
                    mem = [x for x in mem if x != name]
                elif name not in mem:
                    mem.append(name)
            elif not opts.get("a") and not opts.get("r"):
                mem = [x for x in mem if x != name]   # -a なしの -G は「置き換え」: 列挙しなかったグループからは外れる
            g[3] = ",".join(mem)
    if "g" in opts:
        g = gnames.get(opts["g"]) or gids.get(opts["g"])
        if not g:
            err(f"usermod: group '{opts['g']}' does not exist")
            return 6
        u[3] = g[2]
    if "s" in opts:
        u[6] = opts["s"]
    if "c" in opts:
        u[4] = opts["c"]
    if "d" in opts:
        old = u[5]
        u[5] = opts["d"]
        if opts.get("m") and R(old).exists():
            R(opts["d"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(R(old)), str(R(opts["d"])))
    if "l" in opts:
        new = opts["l"]
        if any(r[0] == new for r in pw):
            err(f"usermod: user '{new}' already exists")
            return 9
        for g in gr:
            g[3] = ",".join(new if x == name else x for x in g[3].split(",") if x)
        for s in sh:
            if s[0] == name:
                s[0] = new
        u[0] = new
    for s in sh:
        if s[0] == u[0]:
            if opts.get("L") and not s[1].startswith("!"):
                s[1] = "!" + s[1]
            if opts.get("U") and s[1].startswith("!"):
                if s[1] == "!":
                    err("usermod: unlocking the user's password would result in a passwordless account.\n"
                        "You should set a password with usermod -p to unlock this user's password.")
                else:
                    s[1] = s[1][1:]
    write_db("passwd", pw)
    write_db("group", gr)
    write_db("shadow", sh)
    return 0


def groupadd(argv):
    try:
        opts, pos = parse_short(argv, set("gK"), set("rfo"), {"gid": "g", "system": "r", "force": "f"})
    except ValueError as e:
        err(f"groupadd: {e}")
        return 2
    if len(pos) != 1:
        err("Usage: groupadd [options] GROUP\n\nOptions:\n  -g, --gid GID                 use GID for the new group\n  -r, --system                  create a system account")
        return 2
    if not is_root():
        err("groupadd: Permission denied.\ngroupadd: cannot lock /etc/group; try again later.")
        sudo_hint()
        return 10
    name = pos[0]
    if not VALID_NAME.match(name):
        err(f"groupadd: '{name}' is not a valid group name")
        return 3
    gr = read_db("group")
    if any(g[0] == name for g in gr):
        if opts.get("f"):
            return 0
        err(f"groupadd: group '{name}' already exists")
        return 9
    used = {int(g[2]) for g in gr if g[2].isdigit()}
    if opts.get("g"):
        if int(opts["g"]) in used:
            err(f"groupadd: GID '{opts['g']}' already exists")
            return 4
        gid = int(opts["g"])
    else:
        gid = next_id(used, system=bool(opts.get("r")))
    gr.append([name, "x", str(gid), ""])
    write_db("group", gr)
    return 0


def groupdel(argv):
    pos = [a for a in argv if not a.startswith("-")]
    if len(pos) != 1:
        err("Usage: groupdel [options] GROUP")
        return 2
    if not is_root():
        err("groupdel: Permission denied.\ngroupdel: cannot lock /etc/group; try again later.")
        sudo_hint()
        return 10
    gr = read_db("group")
    g = next((x for x in gr if x[0] == pos[0]), None)
    if not g:
        err(f"groupdel: group '{pos[0]}' does not exist")
        return 6
    prim = [r[0] for r in read_db("passwd") if r[3] == g[2]]
    if prim:
        err(f"groupdel: cannot remove the primary group of user '{prim[0]}'")
        return 8
    gr.remove(g)
    write_db("group", gr)
    return 0


def userdel(argv):
    remove = "-r" in argv or "--remove" in argv
    pos = [a for a in argv if not a.startswith("-")]
    if len(pos) != 1:
        err("Usage: userdel [options] LOGIN\n\nOptions:\n  -r, --remove                  remove home directory and mail spool")
        return 2
    if not is_root():
        return _lock_fail("userdel")
    name = pos[0]
    pw, gr, sh = read_db("passwd"), read_db("group"), read_db("shadow")
    u = next((r for r in pw if r[0] == name), None)
    if not u:
        err(f"userdel: user '{name}' does not exist")
        return 6
    pw.remove(u)
    sh = [s for s in sh if s[0] != name]
    for g in gr:
        g[3] = ",".join(x for x in g[3].split(",") if x and x != name)
    gr = [g for g in gr if not (g[0] == name and g[2] == u[3] and not g[3])]
    write_db("passwd", pw)
    write_db("group", gr)
    write_db("shadow", sh)
    if remove:
        err(f"userdel: {name} mail spool (/var/mail/{name}) not found")
        if R(u[5]).exists():
            shutil.rmtree(R(u[5]), ignore_errors=True)
    return 0


def gpasswd(argv):
    if len(argv) == 3 and argv[0] in ("-a", "--add", "-d", "--delete"):
        user, group = argv[1], argv[2]
        if not is_root():
            err("gpasswd: Permission denied.")
            sudo_hint()
            return 3
        if not any(r[0] == user for r in read_db("passwd")):
            err(f"gpasswd: user '{user}' does not exist")
            return 3
        gr = read_db("group")
        g = next((x for x in gr if x[0] == group), None)
        if not g:
            err(f"gpasswd: group '{group}' does not exist in /etc/group")
            return 3
        mem = [x for x in g[3].split(",") if x]
        if argv[0] in ("-a", "--add"):
            print(f"Adding user {user} to group {group}")
            if user not in mem:
                mem.append(user)
        else:
            if user not in mem:
                err(f"gpasswd: user '{user}' is not a member of '{group}'")
                return 3
            print(f"Removing user {user} from group {group}")
            mem.remove(user)
        g[3] = ",".join(mem)
        write_db("group", gr)
        return 0
    err("Usage: gpasswd [option] GROUP\n\nOptions:\n  -a, --add USER                add USER to GROUP\n  -d, --delete USER             remove USER from GROUP")
    return 2


def passwd(argv, quiet_hint=False):
    pos = [a for a in argv if not a.startswith("-")]
    flags = [a for a in argv if a.startswith("-")]
    if not pos:
        print(dim("[LinuxQuest 模擬] 訓練環境では自分自身のパスワードは変更しません。`sudo passwd ユーザー名` で模擬ユーザーのパスワードを設定できます。"))
        return 0
    name = pos[0]
    if not is_root():
        err(f"passwd: You may not view or modify password information for {name}.")
        sudo_hint()
        return 1
    sh = read_db("shadow")
    s = next((x for x in sh if x[0] == name), None)
    if not s:
        err(f"passwd: user '{name}' does not exist")
        return 1
    if "-l" in flags or "--lock" in flags:
        if not s[1].startswith("!"):
            s[1] = "!" + s[1]
        write_db("shadow", sh)
        print("passwd: password changed.")
        return 0
    if "-S" in flags or "--status" in flags:
        state = "L" if s[1].startswith("!") else ("NP" if not s[1] else "P")
        print(f"{name} {state} {time.strftime('%Y-%m-%d')} 0 99999 7 -1")
        return 0
    try:
        if sys.stdin.isatty():
            p1 = getpass.getpass("New password: ")
            p2 = getpass.getpass("Retype new password: ")
        else:
            p1 = sys.stdin.readline().rstrip("\n")
            p2 = sys.stdin.readline().rstrip("\n")
    except (EOFError, KeyboardInterrupt):
        err("passwd: Authentication token manipulation error\npasswd: password unchanged")
        return 10
    if p1 != p2:
        err("Sorry, passwords do not match.\npasswd: Authentication token manipulation error\npasswd: password unchanged")
        return 10
    if not p1:
        err("No password has been supplied.\npasswd: Authentication token manipulation error\npasswd: password unchanged")
        return 10
    salt = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    # shadow の見た目を再現する教材用の値。実際の yescrypt ハッシュではなく、OS 認証には使えません。
    s[1] = "$y$j9T$" + salt + "$" + hashlib.sha256((salt + p1).encode()).hexdigest()[:43]
    s[2] = str(int(time.time() // 86400))
    write_db("shadow", sh)
    print("passwd: password updated successfully")
    return 0


def real_exec(prog, argv):
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if Path(p).resolve() != SIMBIN.resolve())
    exe = shutil.which(prog, path=path)
    if not exe:
        err(f"{prog}: command not found")
        return 127
    os.execv(exe, [prog, *argv])


def cmd_id(argv):
    pos = [a for a in argv if not a.startswith("-")]
    flags = "".join(a.lstrip("-") for a in argv if a.startswith("-"))
    if not pos or not R("/etc/passwd").exists():
        return real_exec("id", argv)
    info = user_info(pos[0])
    if not info:
        if pos[0] in (os.environ.get("USER"), getpass.getuser()):
            return real_exec("id", argv)
        err(f"id: '{pos[0]}': no such user")
        return 1
    gl = groups_of(pos[0])
    if "G" in flags:
        print(" ".join(g if "n" in flags else gid for g, gid in gl))
    elif "u" in flags:
        print(info["name"] if "n" in flags else info["uid"])
    elif "g" in flags:
        print(gl[0][0] if "n" in flags else info["gid"])
    else:
        print(f"uid={info['uid']}({info['name']}) gid={info['gid']}({gl[0][0]}) groups=" + ",".join(f"{gid}({g})" for g, gid in gl))
    return 0


def cmd_groups(argv):
    if not argv or not R("/etc/passwd").exists():
        return real_exec("groups", argv)
    code = 0
    for name in argv:
        gl = groups_of(name)
        if gl is None:
            err(f"groups: '{name}': no such user")
            code = 1
            continue
        print(f"{name} : " + " ".join(g for g, _ in gl))
    return code


def cmd_getent(argv):
    if not argv or argv[0] not in ("passwd", "group", "shadow") or not R("/etc/passwd").exists():
        return real_exec("getent", argv)
    db = argv[0]
    if db == "shadow" and not is_root():
        return 2
    rows = read_db(db)
    keys = argv[1:]
    if not keys:
        for r in rows:
            print(":".join(r))
        return 0
    code = 0
    for k in keys:
        hit = next((r for r in rows if r[0] == k or (db != "shadow" and r[2] == k)), None)
        if hit:
            print(":".join(hit))
        else:
            code = 2
    return code


# ------------------------------------------------------------------ sudo
REWRITE_PREFIX = ("/etc/", "/opt/", "/srv/", "/home/", "/var/log/", "/usr/lib/systemd/", "/usr/local/bin/",
                  "/usr/local/sbin/", "/root")


def sudo(argv):
    me = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
    st_host = "web01"
    try:
        st_host = load()["host"]
    except Exception:
        pass
    target = "root"
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a == "--":
            i += 1
            break
        if a in ("-u", "--user"):
            target = argv[i + 1] if i + 1 < len(argv) else "root"
            i += 2
            continue
        if a.startswith("-u") and len(a) > 2:
            target = a[2:]
            i += 1
            continue
        if a in ("-l", "--list"):
            print(f"Matching Defaults entries for {me} on {st_host}:\n    env_reset, mail_badpass,\n"
                  f"    secure_path=/usr/local/sbin\\:/usr/local/bin\\:/usr/sbin\\:/usr/bin\\:/sbin\\:/bin, use_pty\n\n"
                  f"User {me} may run the following commands on {st_host}:\n    (ALL : ALL) ALL")
            return 0
        if a in ("-k", "-K", "-v", "--validate", "--reset-timestamp", "--remove-timestamp"):
            return 0
        if a in ("-V", "--version"):
            print("Sudo version 1.9.15p5 (LinuxQuest simulation)")
            return 0
        if a in ("-h", "--help"):
            print("usage: sudo -h | -K | -k | -V\nusage: sudo -v [-ABknS] [-g group] [-h host] [-p prompt] [-u user]\n"
                  "usage: sudo -l [-ABknS] [-g group] [-h host] [-p prompt] [-U user] [-u user] [command [arg ...]]\n"
                  "usage: sudo [-ABbEHknPS] [-C num] [-D directory] [-g group] [-h host] [-p prompt] [-R directory] [-T timeout] [-u user] [VAR=value] [-i | -s] [command [arg ...]]")
            return 0
        if a in ("-i", "-s", "--login", "--shell", "-su", "-is"):
            err(dim("[LinuxQuest 模擬] 訓練環境では root シェルには入りません。`sudo コマンド` の形で1つずつ実行しましょう"
                    "（本番でも root シェルに入りっぱなしは事故のもとです）。"))
            return 1
        if a in ("-E", "-H", "-n", "-S", "-b", "-P", "-A", "--preserve-env", "--non-interactive", "--stdin"):
            i += 1
            continue
        err(f"sudo: invalid option -- '{a.lstrip('-')[:1]}'")
        return 1
    cmd = argv[i:]
    if not cmd:
        err("usage: sudo -h | -K | -k | -V\nusage: sudo [-ABbEHknPS] [-u user] [command [arg ...]]")
        return 1
    if cmd[0] in ("su", "bash", "sh", "zsh") and (len(cmd) == 1 or cmd[1] in ("-", "-l", "-i", "root")):
        err(dim("[LinuxQuest 模擬] 訓練環境では root シェルには入りません。`sudo コマンド` の形で1つずつ実行しましょう。"))
        return 1
    env = dict(os.environ)
    env["LQ_SIM_ROOT"] = "1" if target == "root" else "0"
    env["SUDO_USER"] = me
    env["SUDO_COMMAND"] = " ".join(cmd)
    if cmd[0] not in SIM_CMDS and (W / "sysroot").is_dir():
        home = os.path.expanduser("~")
        new = []
        changed = []
        for a in cmd[1:]:
            key, eq, val = a.partition("=") if a.startswith("--") else ("", "", a)
            p = val if eq else a
            if p.startswith(REWRITE_PREFIX) and not (home and p.startswith(home.rstrip("/") + "/")):
                rp = str(R(p))
                changed.append((p, "sysroot" + p))
                new.append(f"{key}={rp}" if eq else rp)
            else:
                new.append(a)
        if changed:
            err(dim("[LinuxQuest 模擬] 訓練サーバーのシステム領域へ読み替えて実行: " + ", ".join(f"{a} → {b}" for a, b in changed[:3])))
        cmd = [cmd[0]] + new
    exe = shutil.which(cmd[0], path=env.get("PATH"))
    if not exe:
        err(f"sudo: {cmd[0]}: command not found")
        return 1
    try:
        os.execve(exe, cmd, env)
    except OSError as e:
        err(f"sudo: unable to execute {exe}: {e.strerror}")
        return 1


# ------------------------------------------------------------------ setup helpers (ミッションの setup/check から使う)
BASE_PASSWD = """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
sync:x:4:65534:sync:/bin:/bin/sync
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
systemd-network:x:998:998:systemd Network Management:/:/usr/sbin/nologin
syslog:x:104:111::/nonexistent:/usr/sbin/nologin
sshd:x:105:65534::/run/sshd:/usr/sbin/nologin
"""
BASE_GROUP = """root:x:0:
daemon:x:1:
bin:x:2:
sys:x:3:
adm:x:4:syslog
www-data:x:33:
sudo:x:27:
users:x:100:
nogroup:x:65534:
systemd-journal:x:999:
systemd-network:x:998:
syslog:x:111:
docker:x:988:
"""
SKEL = {".bashrc": "# ~/.bashrc: executed by bash(1) for non-login shells.\ncase $- in *i*) ;; *) return;; esac\nHISTCONTROL=ignoreboth\nalias ll='ls -alF'\n",
        ".profile": "# ~/.profile: executed by the command interpreter for login shells.\nif [ -n \"$BASH_VERSION\" ]; then\n    [ -f \"$HOME/.bashrc\" ] && . \"$HOME/.bashrc\"\nfi\n",
        ".bash_logout": "# ~/.bash_logout: executed by bash(1) when login shell exits.\n"}

SSH_UNIT = """[Unit]
Description=OpenBSD Secure Shell server
Documentation=man:sshd(8) man:sshd_config(5)
After=network.target auditd.service

[Service]
ExecStartPre=/usr/sbin/sshd -t
ExecStart=/usr/sbin/sshd -D
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
Type=notify

[Install]
WantedBy=multi-user.target
"""
CRON_UNIT = """[Unit]
Description=Regular background program processing daemon
Documentation=man:cron(8)
After=remote-fs.target nss-user-lookup.target

[Service]
ExecStart=/usr/sbin/cron -f $EXTRA_OPTS
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
JOURNALD_UNIT = """[Unit]
Description=Journal Service
Documentation=man:systemd-journald.service(8) man:journald.conf(5)

[Service]
ExecStart=/usr/lib/systemd/systemd-journald
Restart=always
Type=notify
"""


def fake_bin(path, mode=0o755):
    p = R(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"#!/bin/sh\n# LinuxQuest 模擬バイナリ: {path}\nexit 0\n")
    os.chmod(p, mode)
    return p


def init_system(work, state, host="web01", boot_ago=None, prev_boot_ago=None, users=True):
    """sysroot と模擬 systemd/journal の初期状態を作る。"""
    configure(work, state)
    root = R()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    for d in ("/etc/systemd/system/multi-user.target.wants", "/usr/lib/systemd/system", "/opt", "/srv", "/home",
              "/var/log", "/etc/skel", "/usr/sbin", "/usr/bin", "/usr/local/bin", "/root"):
        R(d).mkdir(parents=True, exist_ok=True)
    if users:
        R("/etc/passwd").write_text(BASE_PASSWD)
        R("/etc/group").write_text(BASE_GROUP)
        write_db("shadow", [[r[0], "*" if r[0] != "root" else "!", "19700", "0", "99999", "7", "", "", ""] for r in read_db("passwd")])
        for k, v in SKEL.items():
            (R("/etc/skel") / k).write_text(v)
    R("/etc/hostname").write_text(host + "\n")
    now = time.time()
    boot_ago = boot_ago if boot_ago is not None else random.randint(30, 45) * 60
    prev_boot_ago = prev_boot_ago if prev_boot_ago is not None else 86400 + random.randint(1, 5) * 3600
    st = {"host": host, "boots": [{"id": hashlib.md5(os.urandom(8)).hexdigest(), "start": now - prev_boot_ago},
                                  {"id": hashlib.md5(os.urandom(8)).hexdigest(), "start": now - boot_ago}],
          "journal": [], "units": {}, "pids": []}
    for b, bs in enumerate(st["boots"]):
        t = bs["start"]
        log(st, None, "kernel", 0, "Linux version 6.8.0-49-generic (buildd@lcy02-amd64-103) #49-Ubuntu SMP PREEMPT_DYNAMIC", ts=t, boot=b)
        log(st, None, "kernel", 0, "Command line: BOOT_IMAGE=/vmlinuz-6.8.0-49-generic root=/dev/mapper/ubuntu--vg-root ro", ts=t + 0.01, boot=b)
        log(st, None, "systemd", 1, "systemd 255.4-1ubuntu8 running in system mode (+PAM +AUDIT +SELINUX +APPARMOR)", ts=t + 1.2, boot=b)
        log(st, None, "systemd", 1, f"Hostname set to <{host}>.", ts=t + 1.3, boot=b)
    fake_bin("/usr/sbin/sshd")
    fake_bin("/usr/sbin/cron")
    fake_bin("/usr/lib/systemd/systemd-journald")
    save(st)
    add_unit("ssh.service", SSH_UNIT, enabled=True, active=True, at_boot=True, behavior={"comm": "sshd", "comm_line": "sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups"})
    add_unit("cron.service", CRON_UNIT, enabled=True, active=True, at_boot=True, behavior={"comm": "cron"})
    add_unit("systemd-journald.service", JOURNALD_UNIT, active=True, at_boot=True, behavior={"comm": "systemd-journal"})
    st = load()
    # 背景ノイズ: cron や sshd のログ
    for b, bs in enumerate(st["boots"]):
        end = st["boots"][b + 1]["start"] - 60 if b + 1 < len(st["boots"]) else now
        t = bs["start"] + 300
        k = 0
        while t < end:
            if k % 3 == 0:
                log(st, "cron.service", "CRON", random.randint(2000, 9000), "(root) CMD (cd / && run-parts --report /etc/cron.hourly)", ts=t, boot=b)
            else:
                ip = f"10.0.{random.randint(0, 3)}.{random.randint(2, 250)}"
                log(st, "ssh.service", "sshd", random.randint(2000, 9000), f"Accepted publickey for deploy from {ip} port {random.randint(40000, 60000)} ssh2: ED25519 SHA256:{hashlib.sha256(ip.encode()).hexdigest()[:20]}", ts=t, boot=b)
            t += random.randint(900, 2400)
            k += 1
    save(st)
    return st


def add_unit(name, text, where="/usr/lib/systemd/system", enabled=False, active=False, behavior=None, at_boot=False,
             failed_status=None, since=None, load_text=None):
    """ユニットファイルを置き、ロード済み状態として登録する。active: True / False / 'failed'"""
    p = R(where) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    st = load()
    cfg = parse_unit(load_text if load_text is not None else text)
    u = {"path": f"{where}/{name}", "loaded": load_text if load_text is not None else text, "active": "inactive",
         "sub": "dead", "result": "success", "pid": 0, "since": None, "status": None, "nrestarts": 0,
         "behavior": behavior or {}, "bad": None}
    st["units"][name] = u
    boot_t = st["boots"][-1]["start"] + random.uniform(2, 6)
    desc = desc_of(name, u)
    if active is True:
        u.update(active="active", sub="running", pid=new_pid(st), since=since or boot_t, run_text=u["loaded"])
        if at_boot:
            log(st, name, "systemd", 1, f"Starting {desc}...", ts=u["since"] - 0.2)
            for pr, msg in (behavior or {}).get("ok_log", []):
                log(st, name, (behavior or {}).get("ident") or os.path.basename(exec_path(uget(cfg, "Service", "ExecStart"))),
                    u["pid"], fmt_beh(msg, cfg), prio=int(pr), ts=u["since"] - 0.1)
            log(st, name, "systemd", 1, f"Started {desc}.", ts=u["since"])
    elif active == "failed":
        u.update(active="failed", sub="failed", pid=new_pid(st), since=since or boot_t, result="exit-code",
                 status=failed_status or "1/FAILURE", exec_line=uget(cfg, "Service", "ExecStart"))
    if enabled:
        for t in install_targets(name, text):
            d = R("/etc/systemd/system") / f"{t}.wants"
            d.mkdir(parents=True, exist_ok=True)
            link = d / name
            if not os.path.lexists(link):
                os.symlink(rel_link(f"{where}/{name}", link), link)
    save(st)
    return u


def unit_state(name):
    st = load()
    u = st["units"].get(name)
    return {"active": u["active"] if u else "inactive", "pid": u["pid"] if u else 0,
            "enabled": enabled_state(name), "loaded": u.get("loaded") if u else None,
            "disk": disk_text(name), "bad": u.get("bad") if u else None,
            "reload_needed": changed_on_disk(name, u), "run_text": u.get("run_text") if u else None}


# ------------------------------------------------------------------ main
def main(prog, argv):
    configure()
    table = {"systemctl": systemctl, "journalctl": journalctl, "useradd": useradd, "adduser": adduser,
             "usermod": usermod, "groupadd": groupadd, "groupdel": groupdel, "userdel": userdel, "gpasswd": gpasswd,
             "passwd": passwd, "id": cmd_id, "groups": cmd_groups, "getent": cmd_getent, "sudo": sudo}
    fn = table.get(prog)
    if not fn:
        err(f"{prog}: not simulated")
        return 127
    try:
        return fn(argv) or 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
