"""ユーザー・グループ・所有者のコマンド（模擬）。

id groups who w last getent stat ll getfacl umask chown chgrp su
useradd usermod userdel groupadd groupdel gpasswd passwd chpasswd visudo

状態は terminal.progress["users"] に持つ（ユーザー表・グループ表・ファイルの所有者・umask）。
実際の /etc/passwd や実在のユーザーには一切触れない。固定の架空データだけを使う。
管理者権限が必要な操作は、先頭に sudo を付けたときだけ成功する。
"""
import copy
import stat

from engine.commands import command, on_check, on_prepare
from engine.commands import sysinfo  # noqa: F401  id を先に登録させ、この後で拡張する
from engine.guided import Result

ME = "learner"
STAMP = "Jan 15 09:30"
STAT_TIME = "2026-01-15 09:30:00.000000000 +0900"

BASE_USERS = {
    "root": {"uid": 0, "gid": 0, "gecos": "root", "home": "/root", "shell": "/bin/bash", "locked": False, "pw": True},
    "daemon": {"uid": 1, "gid": 1, "gecos": "daemon", "home": "/usr/sbin", "shell": "/usr/sbin/nologin", "locked": True, "pw": False},
    "www-data": {"uid": 33, "gid": 33, "gecos": "www-data", "home": "/var/www", "shell": "/usr/sbin/nologin", "locked": True, "pw": False},
    "sshd": {"uid": 105, "gid": 65534, "gecos": "", "home": "/run/sshd", "shell": "/usr/sbin/nologin", "locked": True, "pw": False},
    "nobody": {"uid": 65534, "gid": 65534, "gecos": "nobody", "home": "/nonexistent", "shell": "/usr/sbin/nologin", "locked": True, "pw": False},
    "learner": {"uid": 1000, "gid": 1000, "gecos": "Learner", "home": "/home/learner", "shell": "/bin/bash", "locked": False, "pw": True},
    "alice": {"uid": 1001, "gid": 1001, "gecos": "Alice Example", "home": "/home/alice", "shell": "/bin/bash", "locked": False, "pw": True},
    "bob": {"uid": 1002, "gid": 1002, "gecos": "Bob Example", "home": "/home/bob", "shell": "/bin/bash", "locked": False, "pw": True},
    "deploy": {"uid": 1003, "gid": 1003, "gecos": "Deploy User", "home": "/home/deploy", "shell": "/bin/bash", "locked": False, "pw": True},
}
BASE_GROUPS = {
    "root": {"gid": 0, "members": []},
    "daemon": {"gid": 1, "members": []},
    "adm": {"gid": 4, "members": []},
    "sudo": {"gid": 27, "members": ["learner"]},
    "www-data": {"gid": 33, "members": []},
    "staff": {"gid": 50, "members": []},
    "users": {"gid": 100, "members": []},
    "nogroup": {"gid": 65534, "members": []},
    "learner": {"gid": 1000, "members": []},
    "alice": {"gid": 1001, "members": []},
    "bob": {"gid": 1002, "members": []},
    "deploy": {"gid": 1003, "members": []},
    "developers": {"gid": 2000, "members": ["alice", "bob"]},
}
WHO_ROWS = [("learner", "pts/0", "2026-01-15 09:12", "192.0.2.10"),
            ("alice", "pts/1", "2026-01-15 08:47", "198.51.100.23")]
LAST_ROWS = [
    "learner  pts/0        192.0.2.10       Thu Jan 15 09:12   still logged in",
    "alice    pts/1        198.51.100.23    Thu Jan 15 08:47   still logged in",
    "deploy   pts/0        203.0.113.5      Wed Jan 14 18:02 - 18:40  (00:38)",
    "bob      pts/2        198.51.100.77    Wed Jan 14 10:15 - 11:02  (00:47)",
    "learner  pts/0        192.0.2.10       Tue Jan 13 09:01 - 17:30  (08:29)",
    "reboot   system boot  6.8.0-training   Mon Jan 12 07:16   still running",
]


def fresh_state():
    return {"users": copy.deepcopy(BASE_USERS), "groups": copy.deepcopy(BASE_GROUPS),
            "owners": {}, "umask": 0o022, "log": []}


def state(terminal):
    data = terminal.progress.get("users")
    if not isinstance(data, dict) or "users" not in data:
        data = terminal.progress["users"] = fresh_state()
    return data


@on_prepare
def prepare(terminal, step):
    data = terminal.progress["users"] = fresh_state()
    for name, spec in step.get("owners", {}).items():
        user, _, group = spec.partition(":")
        data["owners"][_key(terminal, name)] = [user, group or user]
    if "umask" in step:
        data["umask"] = step["umask"]
    setup = step.get("users_setup")
    if setup:
        setup(data)


# ---- 状態を調べる部品（レッスンの goal からも使う）
def _key(terminal, name):
    return terminal.path(name).relative_to(terminal.root).as_posix()


def owner_of(terminal, name):
    """(所有者, グループ) を返す。記録がなければ learner:learner。"""
    return tuple(state(terminal)["owners"].get(_key(terminal, name), [ME, ME]))


def user_exists(terminal, name):
    return name in state(terminal)["users"]


def group_exists(terminal, name):
    return name in state(terminal)["groups"]


def groups_of(terminal, name):
    """ユーザーの所属グループ名（基本グループが先頭）。"""
    data = state(terminal)
    user = data["users"][name]
    primary = next((g for g, v in data["groups"].items() if v["gid"] == user["gid"]), str(user["gid"]))
    return [primary] + sorted(g for g, v in data["groups"].items() if name in v["members"] and g != primary)


def user_info(terminal, name):
    return state(terminal)["users"][name]


def umask_of(terminal):
    return state(terminal)["umask"]


@on_check
def check_scenario(scenario, terminal):
    data = state(terminal)
    for name, expected in scenario.get("expected_users", {}).items():
        actual = data["users"].get(name)
        if expected is None:
            if actual is not None:
                return False, f"{name} がまだ登録されています。"
            continue
        if actual is None:
            return False, f"{name} がまだ登録されていません。"
        for field, value in expected.items():
            if field == "groups":
                ok = set(value).issubset(groups_of(terminal, name))
            elif field == "groups_absent":
                ok = not set(value).intersection(groups_of(terminal, name))
            else:
                ok = actual.get(field) == value
            if not ok:
                return False, f"{name} の {field} が要件と違います。id や getent で確認しましょう。"
    for name, expected in scenario.get("expected_groups", {}).items():
        actual = data["groups"].get(name)
        if expected is None:
            if actual is not None:
                return False, f"{name} グループがまだ残っています。"
        elif actual is None or any(
                set(actual.get(k, [])) != set(v) if k == "members" else actual.get(k) != v
                for k, v in expected.items()):
            return False, f"{name} グループの設定が要件と違います。"
    for name, expected in scenario.get("expected_owners", {}).items():
        if owner_of(terminal, "/home/learner/" + name) != tuple(expected.split(":")):
            return False, f"{name} の所有者とグループが要件と違います。"
    return None


def _gid_of(data, group):
    return data["groups"][group]["gid"]


def _group_name(data, gid):
    return next((g for g, v in data["groups"].items() if v["gid"] == gid), str(gid))


def _user_name(data, uid):
    return next((u for u, v in data["users"].items() if v["uid"] == uid), str(uid))


def passwd_line(name, user):
    return f"{name}:x:{user['uid']}:{user['gid']}:{user['gecos']}:{user['home']}:{user['shell']}"


def group_line(name, group):
    return f"{name}:x:{group['gid']}:{','.join(group['members'])}"


def _sudo_needed(cmd):
    return Result(f"{cmd}: Permission denied.\n{cmd}: cannot lock /etc/passwd; try again later.\n"
                  f"（管理者権限が必要です。先頭に sudo を付けましょう）", 1)


# ---- id / groups / who / w / last
def _id_text(terminal, name, flags):
    data = state(terminal)
    user = data["users"][name]
    names = groups_of(terminal, name)
    gids = [_gid_of(data, g) for g in names]
    if "u" in flags:
        return name if "n" in flags else str(user["uid"])
    if "g" in flags:
        return names[0] if "n" in flags else str(user["gid"])
    if "G" in flags:
        return " ".join(names) if "n" in flags else " ".join(map(str, gids))
    shown = ",".join(f"{g}({n})" for g, n in zip(gids, names))
    return f"uid={user['uid']}({name}) gid={user['gid']}({names[0]}) groups={shown}"


@command("id", sudo=True)
def id_command(terminal, rest, stdin=None, admin=False):
    flags, names = "", []
    for item in rest:
        if item.startswith("-") and len(item) > 1:
            if not set(item[1:]) <= set("ugGn"):
                return None
            flags += item[1:]
        else:
            names.append(item)
    if len(names) > 1 or len(set(flags) & set("ugG")) > 1 or (flags and not set(flags) & set("ugG")):
        return Result("id: 使えない組み合わせです。-u -g -G のどれか1つ（と -n）を指定します。", 1)
    name = names[0] if names else ("root" if admin else ME)
    if name not in state(terminal)["users"]:
        return Result(f"id: ‘{name}’: no such user", 1)
    return Result(_id_text(terminal, name, flags))


@command("groups")
def groups_command(terminal, rest, stdin=None, admin=False):
    if len(rest) > 1 or any(x.startswith("-") for x in rest):
        return None
    if not rest:
        return Result(" ".join(groups_of(terminal, "root" if admin else ME)))
    if rest[0] not in state(terminal)["users"]:
        return Result(f"groups: ‘{rest[0]}’: no such user", 1)
    return Result(f"{rest[0]} : " + " ".join(groups_of(terminal, rest[0])))


@command("who")
def who(terminal, rest, stdin=None, admin=False):
    if rest == []:
        return Result("\n".join(f"{u:<8} {t:<12} {d} ({h})" for u, t, d, h in WHO_ROWS))
    if rest in (["am", "i"], ["-m"]):
        u, t, d, h = WHO_ROWS[0]
        return Result(f"{u:<8} {t:<12} {d} ({h})")
    if rest == ["-q"]:
        return Result("learner alice\n# users=2")
    if rest == ["-b"]:
        return Result("         system boot  2026-01-12 07:16")
    return None


@command("w")
def w(terminal, rest, stdin=None, admin=False):
    if rest not in ([], ["-h"]):
        return None
    rows = ["USER     TTY      FROM             LOGIN@   IDLE   WHAT",
            "learner  pts/0    192.0.2.10       09:12    0.00s  w",
            "alice    pts/1    198.51.100.23    08:47    12:03  vim notes.txt"]
    if rest == ["-h"]:
        return Result("\n".join(rows[1:]))
    head = " 09:30:00 up 3 days,  2:14,  2 users,  load average: 0.08, 0.03, 0.01"
    return Result("\n".join([head] + rows))


@command("last")
def last(terminal, rest, stdin=None, admin=False):
    rows = list(LAST_ROWS)
    if rest[:1] == ["-n"] and len(rest) >= 2 and rest[1].isdigit():
        rows, rest = rows[:int(rest[1])], rest[2:]
    elif rest[:1] and rest[0].startswith("-") and rest[0][1:].isdigit():
        rows, rest = rows[:int(rest[0][1:])], rest[1:]
    if len(rest) == 1 and not rest[0].startswith("-"):
        rows = [r for r in rows if r.split()[0] == rest[0]]
    elif rest:
        return None
    return Result("\n".join(rows + ["", "wtmp begins Mon Jan 12 07:16:03 2026"]))


# ---- getent
@command("getent")
def getent(terminal, rest, stdin=None, admin=False):
    if len(rest) not in (1, 2) or rest[0] not in ("passwd", "group"):
        return None
    data = state(terminal)
    table = data["users"] if rest[0] == "passwd" else data["groups"]
    render = passwd_line if rest[0] == "passwd" else group_line
    if len(rest) == 1:
        return Result("\n".join(render(n, v) for n, v in sorted(table.items(), key=lambda x: x[1].get("uid", x[1].get("gid")))))
    key = rest[1]
    if key not in table:
        by_id = next((n for n, v in table.items() if str(v.get("uid", v.get("gid"))) == key), None)
        if by_id is None:
            return Result("", 2)
        key = by_id
    return Result(render(key, table[key]))


# ---- stat / ll / getfacl
def _file_kind(path):
    return stat.S_IFDIR if path.is_dir() else stat.S_IFREG


def _entries(terminal, name):
    path = terminal.path(name)
    if not path.exists():
        return path, None
    return path, (terminal.mode_of(path), *owner_of(terminal, name))


def _owner_ids(terminal, owner, group):
    data = state(terminal)
    uid = data["users"][owner]["uid"] if owner in data["users"] else 0
    gid = data["groups"][group]["gid"] if group in data["groups"] else 0
    return uid, gid


@command("stat")
def stat_command(terminal, rest, stdin=None, admin=False):
    fmt = None
    if rest[:1] in (["-c"], ["--format"]) and len(rest) >= 3:
        fmt, rest = rest[1], rest[2:]
    elif rest and rest[0].startswith("--format="):
        fmt, rest = rest[0].split("=", 1)[1], rest[1:]
    if not rest or any(x.startswith("-") for x in rest):
        return None
    out, code = [], 0
    for name in rest:
        path, info = _entries(terminal, name)
        if info is None:
            out.append(f"stat: cannot statx '{name}': No such file or directory")
            code = 1
            continue
        mode, owner, group = info
        uid, gid = _owner_ids(terminal, owner, group)
        text = stat.filemode(_file_kind(path) | mode)
        if fmt is not None:
            values = {"%a": format(mode & 0o7777, "o"), "%A": text, "%U": owner, "%G": group, "%u": str(uid),
                      "%g": str(gid), "%n": name, "%s": str(path.stat().st_size),
                      "%F": "directory" if path.is_dir() else "regular file"}
            line = fmt
            for token, value in values.items():
                line = line.replace(token, value)
            out.append(line)
            continue
        kind = "directory" if path.is_dir() else "regular file"
        inode = 131000 + sum(map(ord, name)) % 900
        out += [f"  File: {name}",
                f"  Size: {path.stat().st_size:<9}Blocks: 8          IO Block: 4096   {kind}",
                f"Device: 8,1\tInode: {inode:<11}Links: {2 if path.is_dir() else 1}",
                f"Access: ({mode & 0o7777:04o}/{text})  Uid: ({uid:>5}/ {owner:>8})   Gid: ({gid:>5}/ {group:>8})",
                f"Access: {STAT_TIME}", f"Modify: {STAT_TIME}", f"Change: {STAT_TIME}", " Birth: -"]
    return Result("\n".join(out), code)


@command("getfacl")
def getfacl(terminal, rest, stdin=None, admin=False):
    if len(rest) != 1 or rest[0].startswith("-"):
        return None
    path, info = _entries(terminal, rest[0])
    if info is None:
        return Result(f"getfacl: {rest[0]}: No such file or directory", 1)
    mode, owner, group = info

    def triple(shift):
        bits = (mode >> shift) & 7
        return ("r" if bits & 4 else "-") + ("w" if bits & 2 else "-") + ("x" if bits & 1 else "-")
    return Result(f"# file: {rest[0]}\n# owner: {owner}\n# group: {group}\n"
                  f"user::{triple(6)}\ngroup::{triple(3)}\nother::{triple(0)}")


@command("ll")
def ll(terminal, rest, stdin=None, admin=False):
    """ls -alF 相当。所有者とグループの列も表示する。"""
    if any(x.startswith("-") for x in rest):
        return None
    targets = rest or ["."]
    rows = []
    for target in targets:
        base = terminal.path(target)
        if not base.exists():
            return Result(f"ls: cannot access '{target}': No such file or directory", 2)
        names = []
        if base.is_dir():
            parent = base if base == terminal.active_root else base.parent
            names = [(".", base), ("..", parent)] + [(p.name, p) for p in sorted(base.iterdir())]
        else:
            names = [(target, base)]
        if len(targets) > 1:
            rows.append(f"{target}:")
        block = []
        for shown, item in names:
            if item.is_symlink() or item == terminal.root / ".remote":
                continue
            if base.is_dir() and shown not in (".", ".."):
                rel_name = (target.rstrip("/") + "/" + shown) if target != "." else shown
            else:
                rel_name = target if not base.is_dir() else None
            if rel_name is not None:
                mode = terminal.mode_of(item)
                owner, group = owner_of(terminal, rel_name)
            else:
                mode, owner, group = terminal.mode_of(item), *(owner_of(terminal, target) if shown == "." else (ME, ME))
            kind = _file_kind(item)
            suffix = "/" if item.is_dir() else ("*" if mode & 0o111 else "")
            size = 4096 if item.is_dir() else item.stat().st_size
            links = 2 if item.is_dir() else 1
            block.append((f"{stat.filemode(kind | mode)} {links}", owner, group, f"{size:>5} {STAMP} {shown}{suffix}"))
        wo, wg = max(len(b[1]) for b in block), max(len(b[2]) for b in block)
        rows.append(f"total {max(4, len(block) * 4)}")
        rows += [f"{a} {o:<{wo}} {g:<{wg}} {rest_}" for a, o, g, rest_ in block]
    return Result("\n".join(rows))


# ---- umask
@command("umask")
def umask(terminal, rest, stdin=None, admin=False):
    data = state(terminal)
    if rest == []:
        return Result(f"{data['umask']:04o}")
    if rest == ["-S"]:
        perms = []
        for shift in (6, 3, 0):
            allowed = 7 & ~(data["umask"] >> shift)
            perms.append(("r" if allowed & 4 else "") + ("w" if allowed & 2 else "") + ("x" if allowed & 1 else ""))
        return Result(f"u={perms[0]},g={perms[1]},o={perms[2]}")
    if len(rest) == 1:
        value = rest[0]
        if not value.isdigit() or any(c not in "01234567" for c in value) or not 1 <= len(value) <= 4:
            return Result(f"bash: umask: {value}: octal number out of range", 1)
        data["umask"] = int(value, 8)
        return Result()
    return None


# ---- chown / chgrp
def _targets(terminal, names, recursive):
    found = []
    for name in names:
        path = terminal.path(name)
        if not path.exists():
            return None, name
        found.append(name)
        if recursive and path.is_dir():
            base = name.rstrip("/")
            for item in sorted(path.rglob("*")):
                if not item.is_symlink() and ".remote" not in item.relative_to(terminal.root).parts:
                    found.append(base + "/" + item.relative_to(path).as_posix())
    return found, None


def _ownership(cmd, terminal, rest, admin):
    recursive = False
    while rest and rest[0] in ("-R", "-r"):
        recursive, rest = True, rest[1:]
    if len(rest) < 2 or rest[0].startswith("-"):
        return None
    spec, names = rest[0], rest[1:]
    data = state(terminal)
    if cmd == "chown":
        owner, colon, group = spec.partition(":")
        if not colon and "." in spec and spec.split(".")[0] in data["users"]:
            owner, _, group = spec.partition(".")
            colon = ":"
        if not owner and not group:
            return None
    else:
        owner, colon, group = "", ":", spec
    if owner and owner not in data["users"]:
        return Result(f"chown: invalid user: ‘{spec}’", 1)
    if cmd == "chown" and colon and not group:
        group = _group_name(data, data["users"][owner]["gid"])
    if group and group not in data["groups"]:
        return Result(f"{cmd}: invalid group: ‘{spec}’", 1)
    targets, missing = _targets(terminal, names, recursive)
    if targets is None:
        return Result(f"{cmd}: cannot access '{missing}': No such file or directory", 1)
    out, code = [], 0
    for name in targets:
        key = _key(terminal, name)
        current = data["owners"].get(key, [ME, ME])
        if not admin:
            # 一般ユーザーは、自分のファイルを自分の所属グループに変える（chgrp）ことだけできる。
            allowed = (not owner or owner == current[0]) and current[0] == ME and (not group or group in groups_of(terminal, ME))
            if not allowed:
                what = "ownership" if cmd == "chown" else "group"
                out.append(f"{cmd}: changing {what} of '{name}': Operation not permitted")
                code = 1
                continue
        data["owners"][key] = [owner or current[0], group or current[1]]
    return Result("\n".join(out), code)


@command("chown", sudo=True)
def chown(terminal, rest, stdin=None, admin=False):
    return _ownership("chown", terminal, rest, admin)


@command("chgrp", sudo=True)
def chgrp(terminal, rest, stdin=None, admin=False):
    return _ownership("chgrp", terminal, rest, admin)


# ---- su
@command("su", sudo=True)
def su(terminal, rest, stdin=None, admin=False):
    args = list(rest)
    login = False
    if args[:1] == ["-"] or args[:1] == ["-l"]:
        login, args = True, args[1:]
    target = "root"
    if args and not args[0].startswith("-"):
        target, args = args[0], args[1:]
    data = state(terminal)
    if target not in data["users"]:
        return Result(f"su: user {target} does not exist or the user entry does not contain all the required fields", 1)
    if not admin:
        return Result("Password: \nsu: Authentication failure\n（他人のパスワードは知らないので失敗します。管理者権限なら sudo を付けます）", 1)
    if args[:1] != ["-c"] or len(args) != 2:
        return Result(f"（模擬）{target} に切り替えると対話シェルが開きます。この画面では、1つだけ命令を実行する -c の形を使います。", 0)
    shell = data["users"][target]["shell"]
    if shell.endswith("nologin"):
        return Result("This account is currently not available.", 1)
    inner = args[1].split()
    if inner == ["whoami"]:
        return Result(target)
    if inner[:1] == ["id"]:
        return Result(_id_text(terminal, target, ""))
    if inner == ["pwd"]:
        return Result(data["users"][target]["home"] if login else terminal.display_cwd)
    if inner == ["groups"]:
        return Result(" ".join(groups_of(terminal, target)))
    return Result(f"su: この練習で -c に使えるのは whoami・id・pwd・groups です。", 1)


# ---- useradd / usermod / userdel / groupadd / groupdel / gpasswd / passwd / chpasswd / visudo
def _next_id(data):
    used = {v["uid"] for v in data["users"].values()} | {v["gid"] for v in data["groups"].values()}
    number = 1000
    while number in used:
        number += 1
    return number


def _split_groups(data, text):
    names = [x for x in text.split(",") if x]
    for n in names:
        if n not in data["groups"]:
            return None, n
    return names, None


@command("useradd", sudo=True)
def useradd(terminal, rest, stdin=None, admin=False):
    if not admin:
        return _sudo_needed("useradd")
    data = state(terminal)
    opts, name, i = {}, None, 0
    while i < len(rest):
        item = rest[i]
        if item in ("-m", "--create-home"):
            opts["m"] = True
        elif item in ("-s", "-g", "-G", "-u", "-c", "-d") and i + 1 < len(rest):
            opts[item] = rest[i + 1]
            i += 1
        elif item.startswith("-"):
            return None
        elif name is None:
            name = item
        else:
            return None
        i += 1
    if name is None:
        return Result("Usage: useradd [options] LOGIN", 2)
    if name in data["users"]:
        return Result(f"useradd: user '{name}' already exists", 9)
    if not name[0].isalpha() and name[0] != "_" or not all(c.isalnum() or c in "-_" for c in name):
        return Result(f"useradd: invalid user name '{name}'", 3)
    number = _next_id(data)
    if "-u" in opts:
        if not opts["-u"].isdigit():
            return Result(f"useradd: invalid user ID '{opts['-u']}'", 3)
        number = int(opts["-u"])
        if any(v["uid"] == number for v in data["users"].values()):
            return Result(f"useradd: UID {number} is not unique", 4)
    if "-g" in opts:
        if opts["-g"] not in data["groups"]:
            return Result(f"useradd: group '{opts['-g']}' does not exist", 6)
        gid = data["groups"][opts["-g"]]["gid"]
    else:
        gid = number if all(v["gid"] != number for v in data["groups"].values()) else _next_id(data)
        data["groups"][name] = {"gid": gid, "members": []}
    extra = []
    if "-G" in opts:
        extra, missing = _split_groups(data, opts["-G"])
        if extra is None:
            return Result(f"useradd: group '{missing}' does not exist", 6)
    for g in extra:
        data["groups"][g]["members"].append(name)
    data["users"][name] = {"uid": number, "gid": gid, "gecos": opts.get("-c", ""), "home": opts.get("-d", f"/home/{name}"),
                           "shell": opts.get("-s", "/bin/sh"), "locked": True, "pw": False, "home_created": bool(opts.get("m"))}
    return Result()


@command("usermod", sudo=True)
def usermod(terminal, rest, stdin=None, admin=False):
    if not admin:
        return _sudo_needed("usermod")
    data = state(terminal)
    opts, append, name, i = {}, False, None, 0
    while i < len(rest):
        item = rest[i]
        if item == "-a":
            append = True
        elif item in ("-L", "-U"):
            opts[item] = True
        elif item in ("-G", "-aG", "-s", "-g", "-l", "-c", "-d") and i + 1 < len(rest):
            if item == "-aG":
                append, item = True, "-G"
            opts[item] = rest[i + 1]
            i += 1
        elif item.startswith("-"):
            return None
        elif name is None:
            name = item
        else:
            return None
        i += 1
    if name is None or not opts:
        return None
    if append and "-G" not in opts:
        return Result("usermod: -a は -G と一緒に使います。", 2)
    if name not in data["users"]:
        return Result(f"usermod: user '{name}' does not exist", 6)
    user = data["users"][name]
    if "-G" in opts:
        names, missing = _split_groups(data, opts["-G"])
        if names is None:
            return Result(f"usermod: group '{missing}' does not exist", 6)
        if not append:
            for g in data["groups"].values():
                if name in g["members"]:
                    g["members"].remove(name)
        for g in names:
            if name not in data["groups"][g]["members"]:
                data["groups"][g]["members"].append(name)
    if "-g" in opts:
        if opts["-g"] not in data["groups"]:
            return Result(f"usermod: group '{opts['-g']}' does not exist", 6)
        user["gid"] = data["groups"][opts["-g"]]["gid"]
    if "-s" in opts:
        user["shell"] = opts["-s"]
    if "-c" in opts:
        user["gecos"] = opts["-c"]
    if "-d" in opts:
        user["home"] = opts["-d"]
    if "-L" in opts:
        user["locked"] = True
    if "-U" in opts:
        user["locked"] = False
    if "-l" in opts:
        new = opts["-l"]
        if new in data["users"]:
            return Result(f"usermod: user '{new}' already exists", 9)
        data["users"][new] = data["users"].pop(name)
        for g in data["groups"].values():
            g["members"] = [new if m == name else m for m in g["members"]]
    return Result()


@command("userdel", sudo=True)
def userdel(terminal, rest, stdin=None, admin=False):
    if not admin:
        return _sudo_needed("userdel")
    remove_home = any(x in ("-r", "--remove") for x in rest)
    names = [x for x in rest if x not in ("-r", "--remove")]
    if len(names) != 1 or names[0].startswith("-"):
        return None
    data, name = state(terminal), names[0]
    if name not in data["users"]:
        return Result(f"userdel: user '{name}' does not exist", 6)
    if name == ME:
        return Result("userdel: user learner is currently used by process 2001", 8)
    user = data["users"].pop(name)
    if remove_home:
        user["home_removed"] = True
    for g in data["groups"].values():
        g["members"] = [m for m in g["members"] if m != name]
    private = data["groups"].get(name)
    if private and private["gid"] == user["gid"] and not private["members"] and not any(
            u["gid"] == user["gid"] for u in data["users"].values()):
        del data["groups"][name]
    data["log"].append(f"userdel {name}{' -r' if remove_home else ''}")
    return Result()


@command("groupadd", sudo=True)
def groupadd(terminal, rest, stdin=None, admin=False):
    if not admin:
        return Result("groupadd: Permission denied.\ngroupadd: cannot lock /etc/group; try again later.\n"
                      "（管理者権限が必要です。先頭に sudo を付けましょう）", 10)
    data, gid, names, i = state(terminal), None, [], 0
    while i < len(rest):
        if rest[i] == "-g" and i + 1 < len(rest) and rest[i + 1].isdigit():
            gid, i = int(rest[i + 1]), i + 1
        elif rest[i].startswith("-"):
            return None
        else:
            names.append(rest[i])
        i += 1
    if len(names) != 1:
        return None
    name = names[0]
    if name in data["groups"]:
        return Result(f"groupadd: group '{name}' already exists", 9)
    if gid is None:
        gid = _next_id(data)
    elif any(g["gid"] == gid for g in data["groups"].values()):
        return Result(f"groupadd: GID '{gid}' already exists", 4)
    data["groups"][name] = {"gid": gid, "members": []}
    return Result()


@command("groupdel", sudo=True)
def groupdel(terminal, rest, stdin=None, admin=False):
    if len(rest) != 1 or rest[0].startswith("-"):
        return None
    if not admin:
        return Result("groupdel: Permission denied.\ngroupdel: cannot lock /etc/group; try again later.\n"
                      "（管理者権限が必要です。先頭に sudo を付けましょう）", 10)
    data, name = state(terminal), rest[0]
    if name not in data["groups"]:
        return Result(f"groupdel: group '{name}' does not exist", 6)
    gid = data["groups"][name]["gid"]
    owner = next((u for u, v in data["users"].items() if v["gid"] == gid), None)
    if owner:
        return Result(f"groupdel: cannot remove the primary group of user '{owner}'", 8)
    del data["groups"][name]
    return Result()


@command("gpasswd", sudo=True)
def gpasswd(terminal, rest, stdin=None, admin=False):
    if len(rest) != 3 or rest[0] not in ("-a", "-d"):
        return None
    if not admin:
        return Result("gpasswd: Permission denied.", 1)
    data, (flag, user, group) = state(terminal), rest
    if group not in data["groups"]:
        return Result(f"gpasswd: group '{group}' does not exist", 3)
    if user not in data["users"]:
        return Result(f"gpasswd: user '{user}' does not exist", 3)
    members = data["groups"][group]["members"]
    if flag == "-a":
        if user not in members:
            members.append(user)
        return Result(f"Adding user {user} to group {group}")
    if user not in members:
        return Result(f"gpasswd: user '{user}' is not a member of '{group}'", 3)
    members.remove(user)
    return Result(f"Removing user {user} from group {group}")


@command("passwd", sudo=True)
def passwd(terminal, rest, stdin=None, admin=False):
    data = state(terminal)
    flag = rest[0] if rest and rest[0] in ("-l", "-u", "-S", "-e", "-d") else None
    names = rest[1:] if flag else rest
    if len(names) > 1 or any(x.startswith("-") for x in names):
        return None
    name = names[0] if names else (ME if not admin else "root")
    if name not in data["users"]:
        return Result(f"passwd: user '{name}' does not exist", 1)
    user = data["users"][name]
    if flag == "-S":
        if not admin and name != ME:
            return Result(f"passwd: Permission denied", 1)
        status = "L" if user["locked"] else ("P" if user["pw"] else "NP")
        return Result(f"{name} {status} 2026-01-10 0 99999 7 -1")
    if not admin and (name != ME or flag):
        return Result("passwd: You may not view or modify password information for " + name + ".", 1)
    if flag == "-l":
        user["locked"] = True
        return Result(f"passwd: password expiry information changed.")
    if flag == "-u":
        user["locked"] = False
        return Result("passwd: password expiry information changed.")
    if flag == "-e":
        user["expired"] = True
        return Result(f"passwd: password expiry information changed.")
    if flag == "-d":
        user["pw"] = False
        return Result("passwd: password expiry information changed.")
    user["pw"], user["locked"] = True, False
    prompt = "New password: \nRetype new password: \n" if admin or name != ME else \
        "Changing password for learner.\nCurrent password: \nNew password: \nRetype new password: \n"
    return Result(prompt + "passwd: password updated successfully\n（模擬です。実際は入力した文字が画面に出ません）")


@command("chpasswd", sudo=True)
def chpasswd(terminal, rest, stdin=None, admin=False):
    if rest:
        return None
    if not admin:
        return Result("chpasswd: Permission denied.\nchpasswd: cannot lock /etc/passwd; try again later.", 1)
    if stdin is None:
        return Result("chpasswd: 「ユーザー名:パスワード」の行を | で渡します。", 1)
    data = state(terminal)
    for number, line in enumerate(stdin.splitlines(), 1):
        user, colon, _ = line.partition(":")
        if not colon:
            return Result(f"chpasswd: line {number}: missing new password", 1)
        if user not in data["users"]:
            return Result(f"chpasswd: line {number}: user '{user}' does not exist", 1)
        data["users"][user]["pw"], data["users"][user]["locked"] = True, False
    return Result()


@command("visudo", sudo=True)
def visudo(terminal, rest, stdin=None, admin=False):
    if rest != ["-c"]:
        return None
    if not admin:
        return Result("visudo: /etc/sudoers: Permission denied", 1)
    return Result("/etc/sudoers: parsed OK\n/etc/sudoers.d/90-training: parsed OK")
