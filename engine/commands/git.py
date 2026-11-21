"""模擬の git（実際の git は一切動かさない。履歴は terminal.progress["git"] にだけ持つ）。

対応: --version / config / init / status(-s,-sb) / add / commit(-m,-a,-am,--amend) / log(--oneline,-n,--graph)
      diff(--staged) / show / branch / switch / checkout / merge(fast-forward のみ) / restore / reset / rm / mv
      check-ignore / remote -v / clone（example.com の固定のサンプルだけ）。.gitignore も働く。
作業ツリーの実ファイルは練習フォルダの中だけ。履歴（コミット・ブランチ・ステージ）は JSON で保存する。
"""
import datetime
import difflib
import fnmatch
import hashlib
import json
import posixpath
import re

from engine.commands import command, on_check, on_prepare, register_package
from engine.guided import Result, TrainingError

register_package("git", "分散型のバージョン管理システム（変更の履歴を残す）", "1:2.43.0-training")

HOME = "/home/learner"
REMOTE_URL = "https://example.com/team/sample-repo.git"
BASE_TIME = datetime.datetime(2026, 1, 15, 9, 30, 0)
_CURRENT_HEAD = object()


class Fatal(Exception):
    def __init__(self, message, code=128):
        super().__init__(message)
        self.code = code


class Unsupported(Exception):
    pass


# ---------------------------------------------------------------- 状態
def state(terminal):
    return terminal.progress.setdefault("git", {"config": {}, "repos": {}})


def new_repo(branch="main"):
    return {"head": branch, "branches": {}, "commits": {}, "index": {}, "clock": 0,
            "config": {}, "remote": None, "remote_refs": {}, "upstream": {}}


def find_repo(terminal):
    """現在地から上へたどって、いちばん近いリポジトリ (ルートの相対パス, repo) を返す。"""
    if terminal.progress["remote"]:
        raise Unsupported()
    repos = state(terminal)["repos"]
    cwd = terminal.cwd
    while True:
        if cwd in repos:
            return cwd, repos[cwd]
        if cwd == ".":
            raise Fatal("fatal: not a git repository (or any of the parent directories): .git")
        cwd = posixpath.dirname(cwd) or "."


def root_path(terminal, key):
    return terminal.active_root if key == "." else terminal.active_root / key


def blob(text):
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def head_id(repo):
    return repo["branches"].get(repo["head"])


def tree_of(repo, cid):
    return dict(repo["commits"][cid]["tree"]) if cid else {}


def commit_date(n):
    when = BASE_TIME + datetime.timedelta(minutes=5 * n)
    return when.strftime("%a %b ") + str(when.day) + when.strftime(" %H:%M:%S %Y +0900")


def make_commit(repo, message, name, email, parent=_CURRENT_HEAD, tree=None):
    parent = head_id(repo) if parent is _CURRENT_HEAD else parent
    tree = dict(repo["index"] if tree is None else tree)
    repo["clock"] += 1
    body = json.dumps([parent, message, sorted(tree.items()), name, email, repo["clock"]], ensure_ascii=False)
    cid = hashlib.sha1(body.encode("utf-8")).hexdigest()
    repo["commits"][cid] = {"parent": parent, "msg": message, "tree": tree, "author": name,
                            "email": email, "date": commit_date(repo["clock"])}
    repo["branches"][repo["head"]] = cid
    return cid


def short(cid):
    return cid[:7]


def history(repo, cid):
    out = []
    while cid:
        out.append(cid)
        cid = repo["commits"][cid]["parent"]
    return out


def resolve(repo, text):
    match = re.fullmatch(r"(.+?)((?:~\d*|\^)*)", text)
    base, suffix = (match.group(1), match.group(2)) if match else (text, "")
    if base == "HEAD":
        cid = head_id(repo)
    elif base in repo["branches"]:
        cid = repo["branches"][base]
    elif base in repo["remote_refs"]:
        cid = repo["remote_refs"][base]
    else:
        found = [c for c in repo["commits"] if len(base) >= 4 and c.startswith(base)]
        cid = found[0] if len(found) == 1 else None
    for token in re.findall(r"~\d*|\^", suffix):
        steps = 1 if token == "^" or token == "~" else int(token[1:])
        for _ in range(steps):
            cid = repo["commits"][cid]["parent"] if cid else None
    return cid


def need_commit(repo, text):
    cid = resolve(repo, text)
    if not cid:
        raise Fatal(f"fatal: ambiguous argument '{text}': unknown revision or path not in the working tree.\n"
                    "Use '--' to separate paths from revisions, like this:\n"
                    "'git <command> [<revision>...] -- [<file>...]'")
    return cid


# ---------------------------------------------------------------- 作業ツリー
def scan(terminal, key):
    """作業ツリーのファイル {リポジトリ内パス: 内容}。.git の中は見ない。"""
    base = root_path(terminal, key)
    files = {}
    for item in sorted(base.rglob("*")):
        rel = item.relative_to(base)
        if ".git" in rel.parts or item.is_symlink() or not item.is_file():
            continue
        files[rel.as_posix()] = item.read_text(encoding="utf-8", errors="replace")
    return files


def write_work(terminal, key, rel, text):
    target = root_path(terminal, key) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def remove_work(terminal, key, rel):
    base = root_path(terminal, key)
    target = base / rel
    if target.is_file():
        target.unlink()
    parent = target.parent
    while parent != base and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def ignore_rules(work):
    rules = []
    for line in work.get(".gitignore", "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        line = line[1:] if negated else line
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = "/" in line
        rules.append((line.lstrip("/"), negated, dir_only, anchored))
    return rules


def is_ignored(rules, rel):
    parts = rel.split("/")
    for i in range(len(parts)):
        candidate = "/".join(parts[:i + 1])
        is_dir = i < len(parts) - 1
        state_ = False
        for pattern, negated, dir_only, anchored in rules:
            if dir_only and not is_dir:
                continue
            subject = candidate if anchored else parts[i]
            if fnmatch.fnmatchcase(subject, pattern):
                state_ = not negated
        if state_:
            return True
    return False


def pathspec(terminal, key, arg):
    """引数 → リポジトリ内パス。'.' はリポジトリ全体なら ''（全部）。"""
    absolute = terminal.path(arg)
    base = root_path(terminal, key).resolve()
    if absolute != base and base not in absolute.parents:
        raise Fatal(f"fatal: {arg}: '{arg}' is outside repository at '{HOME}/{key}'".replace("/.'", "'"))
    rel = absolute.relative_to(base).as_posix()
    return "" if rel == "." else rel


def matching(paths, spec):
    return [p for p in paths if spec == "" or p == spec or p.startswith(spec + "/")]


# ---------------------------------------------------------------- 差分
def line_counts(old, new):
    a, b = (old or "").splitlines(), (new or "").splitlines()
    ins = dele = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            dele += i2 - i1
        if tag in ("replace", "insert"):
            ins += j2 - j1
    return ins, dele


def changed_paths(old, new):
    return sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def summary(old, new, paths):
    ins = dele = 0
    for p in paths:
        i, d = line_counts(old.get(p), new.get(p))
        ins, dele = ins + i, dele + d
    text = f" {plural(len(paths), 'file')} changed"
    if ins or not dele:
        text += f", {plural(ins, 'insertion')}(+)"
    if dele or not ins:
        text += f", {plural(dele, 'deletion')}(-)"
    return text


def stat_block(old, new):
    paths = changed_paths(old, new)
    width = max(len(p) for p in paths)
    lines = []
    for p in paths:
        i, d = line_counts(old.get(p), new.get(p))
        n = i + d
        if n > 50:
            i, d = max(1, round(i * 50 / n)) if i else 0, max(1, round(d * 50 / n)) if d else 0
        lines.append(f" {p.ljust(width)} | {n} {'+' * i}{'-' * d}")
    return lines, summary(old, new, paths)


def mode_lines(old, new):
    out = []
    for p in changed_paths(old, new):
        if p not in old:
            out.append(f" create mode 100644 {p}")
        elif p not in new:
            out.append(f" delete mode 100644 {p}")
    return out


def diff_text(old, new, paths=None):
    out = []
    for p in changed_paths(old, new):
        if paths is not None and p not in paths:
            continue
        a, b = old.get(p), new.get(p)
        out.append(f"diff --git a/{p} b/{p}")
        if a is None:
            out.append("new file mode 100644")
        elif b is None:
            out.append("deleted file mode 100644")
        ha = blob(a)[:7] if a is not None else "0000000"
        hb = blob(b)[:7] if b is not None else "0000000"
        out.append(f"index {ha}..{hb}" + (" 100644" if a is not None and b is not None else ""))
        out.append("--- " + (f"a/{p}" if a is not None else "/dev/null"))
        out.append("+++ " + (f"b/{p}" if b is not None else "/dev/null"))
        lines = list(difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), n=3, lineterm=""))
        out.extend(lines[2:])
    return "\n".join(out)


# ---------------------------------------------------------------- 状態表示
def status_data(terminal, key, repo):
    work = scan(terminal, key)
    head = tree_of(repo, head_id(repo))
    index = repo["index"]
    staged = {p: ("new file" if p not in head else "deleted" if p not in index else "modified")
              for p in changed_paths(head, index)}
    unstaged = {}
    for p in sorted(index):
        if p not in work:
            unstaged[p] = "deleted"
        elif work[p] != index[p]:
            unstaged[p] = "modified"
    rules = ignore_rules(work)
    tracked = set(index) | set(head)
    untracked = set()
    for p in work:
        if p in index or is_ignored(rules, p):
            continue
        parts = p.split("/")
        shown = p
        for i in range(1, len(parts)):
            folder = "/".join(parts[:i]) + "/"
            if not any(t.startswith(folder) for t in tracked):
                shown = folder
                break
        untracked.add(shown)
    return staged, unstaged, sorted(untracked), work


def ahead_count(repo):
    upstream = repo["upstream"].get(repo["head"])
    if not upstream or upstream not in repo["remote_refs"]:
        return None, None
    remote = repo["remote_refs"][upstream]
    mine = history(repo, head_id(repo))
    return upstream, (mine.index(remote) if remote in mine else len(mine))


def rel_display(terminal, key, path):
    cwd = terminal.cwd
    inside = "." if key == "." else key
    sub = cwd[len(inside) + 1:] if key != "." and cwd != key else ("" if cwd == key else cwd)
    return posixpath.relpath(path, sub or ".") if sub else path


def status_long(terminal, key, repo):
    staged, unstaged, untracked, _ = status_data(terminal, key, repo)
    show = lambda p: rel_display(terminal, key, p)  # noqa: E731
    unborn = head_id(repo) is None
    header = f"On branch {repo['head']}"
    spaced = False
    upstream, ahead = ahead_count(repo)
    if upstream:
        spaced = True
        if ahead:
            header += (f"\nYour branch is ahead of '{upstream}' by {plural(ahead, 'commit')}.\n"
                       "  (use \"git push\" to publish your local commits)")
        else:
            header += f"\nYour branch is up to date with '{upstream}'."
    if unborn:
        spaced = True
        header += "\n\nNo commits yet"
    blocks = []
    if staged:
        undo = '"git rm --cached <file>..."' if unborn else '"git restore --staged <file>..."'
        blocks.append(f"Changes to be committed:\n  (use {undo} to unstage)\n"
                      + "\n".join(f"\t{kind + ':':<12}{show(p)}" for p, kind in staged.items()))
    if unstaged:
        blocks.append("Changes not staged for commit:\n  (use \"git add <file>...\" to update what will be committed)\n"
                      "  (use \"git restore <file>...\" to discard changes in working directory)\n"
                      + "\n".join(f"\t{kind + ':':<12}{show(p)}" for p, kind in unstaged.items()))
    if untracked:
        blocks.append("Untracked files:\n  (use \"git add <file>...\" to include in what will be committed)\n"
                      + "\n".join(f"\t{show(p)}" for p in untracked))
    if staged:
        footer = None
    elif unstaged:
        footer = 'no changes added to commit (use "git add" and/or "git commit -a")'
    elif untracked:
        footer = 'nothing added to commit but untracked files present (use "git add" to track)'
    elif unborn:
        footer = 'nothing to commit (create/copy files and use "git add" to track)'
    else:
        footer = "nothing to commit, working tree clean"
    if footer:
        blocks.append(footer)
    return header + ("\n\n" if spaced else "\n") + "\n\n".join(blocks) if blocks else header


def status_short(terminal, key, repo, branch):
    staged, unstaged, untracked, _ = status_data(terminal, key, repo)
    code = {"new file": "A", "modified": "M", "deleted": "D"}
    lines = [f"## {repo['head']}" + ("" if head_id(repo) else (" (No commits yet on " + repo["head"] + ")"))] if branch else []
    if branch and head_id(repo):
        upstream, ahead = ahead_count(repo)
        if upstream:
            lines[0] += f"...{upstream}" + (f" [ahead {ahead}]" if ahead else "")
    if branch and not head_id(repo):
        lines[0] = f"## No commits yet on {repo['head']}"
    for p in sorted(set(staged) | set(unstaged)):
        lines.append(f"{code.get(staged.get(p), ' ')}{code.get(unstaged.get(p), ' ')} {rel_display(terminal, key, p)}")
    lines += [f"?? {rel_display(terminal, key, p)}" for p in untracked]
    return "\n".join(lines)


# ---------------------------------------------------------------- 設定
def identity(terminal, repo):
    cfg = {**state(terminal)["config"], **repo["config"]}
    name, email = cfg.get("user.name"), cfg.get("user.email")
    if not name or not email:
        raise Fatal("Author identity unknown\n\n*** Please tell me who you are.\n\nRun\n\n"
                    "  git config --global user.email \"you@example.com\"\n"
                    "  git config --global user.name \"Your Name\"\n\n"
                    "to set your account's default identity.\nOmit --global to set the identity only in this repository.\n\n"
                    "fatal: unable to auto-detect email address (got 'learner@dojo-local.(none)')")
    return name, email


def cmd_config(terminal, rest):
    scope = "local"
    args = []
    for a in rest:
        if a == "--global":
            scope = "global"
        elif a == "--local":
            scope = "local"
        else:
            args.append(a)
    global_cfg = state(terminal)["config"]

    def local():
        try:
            return find_repo(terminal)[1]["config"]
        except Fatal:
            raise Fatal("fatal: --local can only be used inside a git repository") from None

    store = lambda: global_cfg if scope == "global" else local()  # noqa: E731
    if args in (["--list"], ["-l"]):
        merged = dict(global_cfg)
        if scope != "global":
            try:
                merged.update(find_repo(terminal)[1]["config"])
            except Fatal:
                pass
        return Result("\n".join(f"{k}={v}" for k, v in merged.items()))
    if args and args[0] == "--unset" and len(args) == 2:
        s = store()
        if s.pop(args[1].lower(), None) is None:
            return Result("", 5)
        return Result()
    if args and args[0] == "--get" and len(args) == 2:
        args = args[1:]
    if len(args) == 1 and not args[0].startswith("-"):
        key = args[0].lower()
        value = None
        if scope == "global":
            value = global_cfg.get(key)
        else:
            try:
                value = find_repo(terminal)[1]["config"].get(key, global_cfg.get(key))
            except Fatal:
                value = global_cfg.get(key)
        return Result(value, 0) if value is not None else Result("", 1)
    if len(args) == 2 and not args[0].startswith("-"):
        key = args[0].lower()
        if "." not in key:
            return Result(f"error: key does not contain a section: {args[0]}", 1)
        if scope == "local":
            try:
                find_repo(terminal)
            except Fatal:
                raise Fatal("fatal: not in a git directory") from None
        store()[key] = args[1]
        return Result()
    raise Unsupported()


# ---------------------------------------------------------------- 作業ツリーの切り替え
def checkout_tree(terminal, key, repo, target, what):
    """今の HEAD から target ツリーへ作業ツリー・ステージを移す。上書きされる変更があれば Fatal。"""
    current = tree_of(repo, head_id(repo))
    work = scan(terminal, key)
    index = repo["index"]
    changes = changed_paths(current, target)
    dirty = [p for p in changes if p in index and (index.get(p) != current.get(p) or work.get(p) != index.get(p))]
    if dirty:
        verb = "checkout" if what == "checkout" else what
        tail = "switch branches" if what in ("checkout", "switch") else what
        raise Fatal(f"error: Your local changes to the following files would be overwritten by {verb}:\n"
                    + "\n".join(f"\t{p}" for p in dirty)
                    + f"\nPlease commit your changes or stash them before you {tail}.\nAborting", 1)
    clash = [p for p in changes if p in target and p not in index and p in work and work[p] != target[p]]
    if clash:
        raise Fatal(f"error: The following untracked working tree files would be overwritten by {what}:\n"
                    + "\n".join(f"\t{p}" for p in clash) + "\nPlease move or remove them before you switch branches.\nAborting", 1)
    for p in changes:
        if p in target:
            write_work(terminal, key, p, target[p])
            index[p] = target[p]
        else:
            if p in work:
                remove_work(terminal, key, p)
            index.pop(p, None)
    carried = []
    for p in sorted(index):
        if p in target and (index[p] != target[p]):
            carried.append(("A" if p not in target else "M", p))
    for p in sorted(index):
        if work.get(p) is None and p not in changes and p in index:
            carried.append(("D", p))
        elif work.get(p) is not None and work[p] != index[p] and p not in changes:
            carried.append(("M", p))
    return carried


def cmd_switch(terminal, key, repo, name, rest):
    create = force_new = False
    args = []
    for a in rest:
        if a in ("-c", "--create", "-b"):
            create = True
        elif a in ("-C", "--force-create"):
            create = force_new = True
        else:
            args.append(a)
    legacy = name == "checkout"
    if create:
        if not args:
            raise Fatal("fatal: missing branch name; try -c" if not legacy else "fatal: switch `b' requires a value")
        new = args[0]
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", new) or new.endswith("/") or ".." in new:
            raise Fatal(f"fatal: '{new}' is not a valid branch name")
        if new in repo["branches"] and not force_new:
            raise Fatal(f"fatal: a branch named '{new}' already exists")
        if head_id(repo) is None and len(args) == 1:
            repo["head"] = new
            return Result(f"Switched to a new branch '{new}'")
        start = need_commit(repo, args[1]) if len(args) > 1 else head_id(repo)
        carried = checkout_tree(terminal, key, repo, tree_of(repo, start), name)
        repo["branches"][new] = start
        repo["head"] = new
        return Result(f"Switched to a new branch '{new}'")
    if len(args) != 1:
        raise Unsupported()
    target = args[0]
    if target == repo["head"]:
        return Result(f"Already on '{target}'")
    track = f"origin/{target}"
    if target not in repo["branches"]:
        if track in repo["remote_refs"] and target != "HEAD":
            cid = repo["remote_refs"][track]
            checkout_tree(terminal, key, repo, tree_of(repo, cid), name)
            repo["branches"][target] = cid
            repo["upstream"][target] = track
            repo["head"] = target
            return Result(f"branch '{target}' set up to track 'origin/{target}'.\nSwitched to a new branch '{target}'")
        if legacy:
            raise Fatal(f"error: pathspec '{target}' did not match any file(s) known to git", 1)
        raise Fatal(f"fatal: invalid reference: {target}")
    carried = checkout_tree(terminal, key, repo, tree_of(repo, repo["branches"][target]), name)
    repo["head"] = target
    lines = [f"{k}\t{p}" for k, p in carried] if legacy else []
    return Result("\n".join(lines + [f"Switched to branch '{target}'"]))


# ---------------------------------------------------------------- サブコマンド
def cmd_init(terminal, rest):
    branch = state(terminal)["config"].get("init.defaultbranch", "main")
    target = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-b", "--initial-branch") and i + 1 < len(rest):
            branch = rest[i + 1]
            i += 1
        elif a.startswith("--initial-branch="):
            branch = a.split("=", 1)[1]
        elif a in ("-q", "--quiet"):
            pass
        elif not a.startswith("-") and target is None:
            target = a
        else:
            raise Unsupported()
        i += 1
    base = terminal.path(target or ".")
    if target:
        terminal.ensure_directory(base)
    key = "." if base == terminal.active_root else base.relative_to(terminal.active_root).as_posix()
    repos = state(terminal)["repos"]
    (base / ".git").mkdir(exist_ok=True)
    shown = f"{HOME}/{key}/.git/" if key != "." else f"{HOME}/.git/"
    if key in repos:
        return Result(f"Reinitialized existing Git repository in {shown}")
    repos[key] = new_repo(branch)
    return Result(f"Initialized empty Git repository in {shown}")


def cmd_status(terminal, key, repo, rest):
    flags = [a for a in rest if a.startswith("-")]
    if any(a not in ("-s", "--short", "-b", "--branch", "-sb") for a in flags) or [a for a in rest if not a.startswith("-")]:
        raise Unsupported()
    if any(a in ("-s", "--short", "-sb") for a in flags):
        return Result(status_short(terminal, key, repo, any(a in ("-b", "--branch", "-sb") for a in flags)))
    return Result(status_long(terminal, key, repo))


def stage_paths(terminal, key, repo, specs, update_only=False):
    work = scan(terminal, key)
    rules = ignore_rules(work)
    index = repo["index"]
    ignored_hit = []
    for spec_arg in specs:
        spec = pathspec(terminal, key, spec_arg)
        names = matching(set(work) | set(index), spec)
        if not names and spec != "":
            raise Fatal(f"fatal: pathspec '{spec_arg}' did not match any files")
        for p in names:
            if p in work:
                if p not in index:
                    if update_only:
                        continue
                    if is_ignored(rules, p):
                        if spec != "" and (p == spec):
                            ignored_hit.append(p)
                        continue
                index[p] = work[p]
            else:
                index.pop(p, None)
    if ignored_hit:
        raise Fatal("The following paths are ignored by one of your .gitignore files:\n" + "\n".join(ignored_hit)
                    + "\nhint: Use -f if you really want to add them.\nhint: Turn this message off by running\n"
                    "hint: \"git config advice.addIgnoredFile false\"", 1)


def cmd_add(terminal, key, repo, rest):
    update = False
    specs = []
    for a in rest:
        if a in ("-A", "--all"):
            specs = specs or ["."]
        elif a in ("-u", "--update"):
            update = True
            specs = specs or ["."]
        elif a == "--":
            continue
        elif a.startswith("-"):
            raise Unsupported()
        else:
            specs.append(a)
    if not specs:
        return Result("Nothing specified, nothing added.\nhint: Maybe you wanted to say 'git add .'?\n"
                      "hint: Turn this message off by running\nhint: \"git config advice.addEmptyPathspec false\"", 0)
    stage_paths(terminal, key, repo, specs, update)
    return Result()


def cmd_commit(terminal, key, repo, rest):
    messages, auto, amend = [], False, False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "-m" and i + 1 < len(rest):
            messages.append(rest[i + 1])
            i += 1
        elif a.startswith("-m") and len(a) > 2 and not a.startswith("--"):
            messages.append(a[2:])
        elif a.startswith("--message="):
            messages.append(a.split("=", 1)[1])
        elif a in ("-a", "--all"):
            auto = True
        elif a == "-am" and i + 1 < len(rest):
            auto = True
            messages.append(rest[i + 1])
            i += 1
        elif a == "--amend":
            amend = True
        else:
            raise Unsupported()
        i += 1
    name, email = identity(terminal, repo)
    if auto:
        work = scan(terminal, key)
        for p in list(repo["index"]):
            if p in work:
                repo["index"][p] = work[p]
            else:
                repo["index"].pop(p)
    head = head_id(repo)
    if amend and head is None:
        raise Fatal("fatal: You have nothing to amend.")
    parent_tree = tree_of(repo, repo["commits"][head]["parent"]) if amend and head else tree_of(repo, head)
    old_tree = tree_of(repo, head)
    if not amend and repo["index"] == old_tree:
        return Result(status_long(terminal, key, repo), 1)
    if not messages:
        if amend and head:
            messages = [repo["commits"][head]["msg"]]
        else:
            return Result("エディタが開く操作は、この練習では未対応です。-m に続けてメッセージを付けましょう。\n"
                          "Aborting commit due to empty commit message.", 1)
    message = "\n\n".join(messages)
    if not message.strip():
        return Result("Aborting commit due to empty commit message.", 1)
    base_parent = repo["commits"][head]["parent"] if amend and head else head
    cid = make_commit(repo, message, name, email, parent=base_parent)
    label = "root-commit" if base_parent is None else None
    first = message.splitlines()[0]
    tag = f"{repo['head']} ({label})" if label else repo["head"]
    out = [f"[{tag} {short(cid)}] {first}"]
    paths = changed_paths(parent_tree, repo["index"])
    if paths:
        out.append(summary(parent_tree, repo["index"], paths))
        out += mode_lines(parent_tree, repo["index"])
    return Result("\n".join(out))


def decorations(repo, cid):
    names = []
    if head_id(repo) == cid:
        names.append(f"HEAD -> {repo['head']}")
    names += [b for b, c in sorted(repo["branches"].items()) if c == cid and b != repo["head"]]
    names += [r for r, c in sorted(repo["remote_refs"].items()) if c == cid and r != "origin/HEAD"]
    if repo["remote_refs"].get("origin/HEAD") == cid:
        names.append("origin/HEAD")
    names = sorted(set(names), key=names.index)
    return f" ({', '.join(names)})" if names else ""


def cmd_log(terminal, key, repo, rest):
    oneline = graph = False
    limit = None
    revs = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--oneline":
            oneline = True
        elif a == "--graph":
            graph = True
        elif a == "-n" and i + 1 < len(rest) and rest[i + 1].isdigit():
            limit = int(rest[i + 1])
            i += 1
        elif re.fullmatch(r"-\d+", a):
            limit = int(a[1:])
        elif a.startswith("--max-count="):
            limit = int(a.split("=", 1)[1])
        elif a.startswith("-"):
            raise Unsupported()
        else:
            revs.append(a)
        i += 1
    if len(revs) > 1:
        raise Unsupported()
    if revs:
        start = need_commit(repo, revs[0])
    else:
        start = head_id(repo)
        if start is None:
            raise Fatal(f"fatal: your current branch '{repo['head']}' does not have any commits yet")
    chain = history(repo, start)[:limit]
    out = []
    for cid in chain:
        c = repo["commits"][cid]
        deco = decorations(repo, cid)
        if oneline:
            out.append(("* " if graph else "") + f"{short(cid)}{deco} {c['msg'].splitlines()[0]}")
        else:
            body = "\n".join("    " + line if line else "" for line in c["msg"].splitlines())
            out.append(f"commit {cid}{deco}\nAuthor: {c['author']} <{c['email']}>\nDate:   {c['date']}\n\n{body}\n")
    return Result("\n".join(out).rstrip("\n") if oneline else "\n".join(out).rstrip("\n"))


def cmd_diff(terminal, key, repo, rest):
    staged = False
    names = []
    args = list(rest)
    while args:
        a = args.pop(0)
        if a in ("--staged", "--cached"):
            staged = True
        elif a == "--":
            names += args
            args = []
        elif a.startswith("-"):
            raise Unsupported()
        else:
            names.append(a)
    revs = []
    while names and resolve(repo, names[0]) is not None and not terminal.path(names[0]).exists():
        revs.append(names.pop(0))
    specs = [pathspec(terminal, key, n) for n in names]
    work = scan(terminal, key)
    head = tree_of(repo, head_id(repo))
    index = repo["index"]
    if len(revs) == 2:
        old, new = tree_of(repo, resolve(repo, revs[0])), tree_of(repo, resolve(repo, revs[1]))
    elif len(revs) == 1:
        old = tree_of(repo, resolve(repo, revs[0]))
        new = staged and index or {p: work[p] for p in work if p in index or p in old}
    elif staged:
        old, new = head, index
    else:
        old, new = index, {p: work[p] for p in index if p in work}
    if specs:
        paths = {p for p in set(old) | set(new) if matching([p], specs[0]) or any(matching([p], s) for s in specs)}
        return Result(diff_text(old, new, paths))
    return Result(diff_text(old, new))


def cmd_show(terminal, key, repo, rest):
    if len(rest) > 1 or any(a.startswith("-") for a in rest):
        raise Unsupported()
    cid = need_commit(repo, rest[0] if rest else "HEAD") if (rest or head_id(repo)) else None
    if cid is None:
        raise Fatal("fatal: your current branch 'main' does not have any commits yet")
    c = repo["commits"][cid]
    body = "\n".join("    " + line if line else "" for line in c["msg"].splitlines())
    text = f"commit {cid}{decorations(repo, cid)}\nAuthor: {c['author']} <{c['email']}>\nDate:   {c['date']}\n\n{body}\n"
    diff = diff_text(tree_of(repo, c["parent"]), c["tree"])
    return Result(text + ("\n" + diff if diff else "").rstrip("\n"))


def cmd_branch(terminal, key, repo, rest):
    rest = [{"--all": "-a", "--remotes": "-r"}.get(a, a) for a in rest]
    flags = [a for a in rest if a.startswith("-")]
    names = [a for a in rest if not a.startswith("-")]
    if not flags and not names or flags in (["-v"], ["-a"], ["-r"], ["--list"], ["-vv"]) and not names:
        local = sorted(repo["branches"])
        if not local:
            local = []
        remote = sorted(r for r in repo["remote_refs"] if r != "origin/HEAD") if flags and flags[0] in ("-a", "-r") else []
        if flags == ["-r"]:
            local = []
        verbose = flags in (["-v"], ["-vv"])
        rows = [(("* " if b == repo["head"] else "  ") + b, repo["branches"][b]) for b in local]
        if repo["head"] not in repo["branches"] and flags != ["-r"]:
            rows.insert(0, ("* " + repo["head"], None))
        if flags == ["-a"] or flags == ["-r"]:
            rows += [(f"  remotes/{r}", repo["remote_refs"][r]) for r in remote]
        if flags == ["-r"]:
            rows = [(f"  {r}", repo["remote_refs"][r]) for r in remote]
        if verbose:
            width = max((len(r[0]) for r in rows), default=0)
            return Result("\n".join(f"{n.ljust(width)} {short(c)} {repo['commits'][c]['msg'].splitlines()[0]}" for n, c in rows if c))
        return Result("\n".join(n for n, _ in rows))
    if flags == ["--show-current"]:
        return Result(repo["head"])
    if flags in (["-d"], ["-D"], ["--delete"]) and names:
        out = []
        for n in names:
            if n not in repo["branches"]:
                raise Fatal(f"error: branch '{n}' not found.", 1)
            if n == repo["head"]:
                raise Fatal(f"error: Cannot delete branch '{n}' checked out at '{HOME}/{key if key != '.' else ''}'".replace("/'", "'"), 1)
            tip = repo["branches"][n]
            if flags != ["-D"] and tip not in history(repo, head_id(repo)):
                raise Fatal(f"error: The branch '{n}' is not fully merged.\nIf you are sure you want to delete it, run 'git branch -D {n}'.", 1)
            del repo["branches"][n]
            repo["upstream"].pop(n, None)
            out.append(f"Deleted branch {n} (was {short(tip)}).")
        return Result("\n".join(out))
    if flags in (["-m"], ["-M"]) and 1 <= len(names) <= 2:
        old, new = (repo["head"], names[0]) if len(names) == 1 else names
        if old not in repo["branches"] and old != repo["head"]:
            raise Fatal(f"error: refname refs/heads/{old} not found", 1)
        if new in repo["branches"] and flags != ["-M"]:
            raise Fatal(f"fatal: a branch named '{new}' already exists")
        if old in repo["branches"]:
            repo["branches"][new] = repo["branches"].pop(old)
        if repo["head"] == old:
            repo["head"] = new
        return Result()
    if not flags and 1 <= len(names) <= 2:
        new = names[0]
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", new) or new.endswith("/") or ".." in new:
            raise Fatal(f"fatal: '{new}' is not a valid branch name")
        if new in repo["branches"]:
            raise Fatal(f"fatal: a branch named '{new}' already exists")
        start = resolve(repo, names[1]) if len(names) == 2 else head_id(repo)
        if start is None:
            raise Fatal(f"fatal: not a valid object name: '{names[1] if len(names) == 2 else repo['head']}'")
        repo["branches"][new] = start
        return Result()
    raise Unsupported()


def cmd_merge(terminal, key, repo, rest):
    names = [a for a in rest if a != "--ff-only" and a != "--ff"]
    if any(a.startswith("-") for a in names) or len(names) != 1:
        raise Unsupported()
    target = names[0]
    tip = resolve(repo, target)
    if tip is None:
        return Result(f"merge: {target} - not something we can merge", 1)
    current = head_id(repo)
    if current is None:
        raise Fatal("fatal: 現在のブランチにまだコミットがありません。")
    if tip == current or tip in history(repo, current):
        return Result("Already up to date.")
    if current not in history(repo, tip):
        raise Fatal("hint: Diverging branches can't be fast-forwarded.\n"
                    "fatal: Not possible to fast-forward, aborting.\n"
                    "（この練習の merge は fast-forward のみ対応です。履歴が分かれたときの本物の merge はマージコミットを作ります）")
    old_tree, new_tree = tree_of(repo, current), tree_of(repo, tip)
    checkout_tree(terminal, key, repo, new_tree, "merge")
    repo["branches"][repo["head"]] = tip
    lines, total = stat_block(old_tree, new_tree)
    return Result("\n".join([f"Updating {short(current)}..{short(tip)}", "Fast-forward", *lines, total, *mode_lines(old_tree, new_tree)]))


def cmd_restore(terminal, key, repo, rest):
    staged = worktree = False
    source = None
    specs = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("--staged", "-S"):
            staged = True
        elif a in ("--worktree", "-W"):
            worktree = True
        elif a.startswith("--source="):
            source = a.split("=", 1)[1]
        elif a in ("-s", "--source") and i + 1 < len(rest):
            source = rest[i + 1]
            i += 1
        elif a.startswith("-"):
            raise Unsupported()
        else:
            specs.append(a)
        i += 1
    if not specs:
        raise Fatal("fatal: you must specify path(s) to restore")
    if not staged:
        worktree = True
    head = tree_of(repo, head_id(repo))
    src_id = need_commit(repo, source) if source else None
    src = tree_of(repo, src_id) if source else (head if staged else repo["index"])
    index = repo["index"]
    work = scan(terminal, key)
    for arg in specs:
        spec = pathspec(terminal, key, arg)
        names = matching(set(src) | set(index) | set(head) | (set(work) if False else set()), spec)
        if not names:
            raise Fatal(f"error: pathspec '{arg}' did not match any file(s) known to git", 1)
        for p in names:
            if staged:
                if p in src:
                    index[p] = src[p]
                else:
                    index.pop(p, None)
            if worktree:
                origin = src if (source or not staged) else index
                if p in origin:
                    write_work(terminal, key, p, origin[p])
                elif p in work:
                    remove_work(terminal, key, p)
    return Result()


def cmd_reset(terminal, key, repo, rest):
    mode = "mixed"
    args = []
    for a in rest:
        if a in ("--soft", "--mixed", "--hard"):
            mode = a[2:]
        elif a.startswith("-"):
            raise Unsupported()
        else:
            args.append(a)
    target = None
    if args and (resolve(repo, args[0]) is not None or args[0] == "HEAD") and not (len(args) == 1 and terminal.path(args[0]).exists() and args[0] != "HEAD"):
        target = resolve(repo, args.pop(0))
    head = head_id(repo)
    if args:  # パス指定: ステージから外す
        src = tree_of(repo, target or head)
        for arg in args:
            spec = pathspec(terminal, key, arg)
            names = matching(set(src) | set(repo["index"]), spec)
            if not names:
                raise Fatal(f"fatal: ambiguous argument '{arg}': unknown revision or path not in the working tree.", 128)
            for p in names:
                if p in src:
                    repo["index"][p] = src[p]
                else:
                    repo["index"].pop(p, None)
        return Result(unstaged_report(terminal, key, repo))
    if target is None:
        target = head
    if target is None:
        repo["index"].clear()
        return Result()
    new_tree = tree_of(repo, target)
    if mode != "soft":
        old_index = dict(repo["index"])
        repo["index"] = dict(new_tree)
        if mode == "hard":
            for p in set(old_index) | set(new_tree):
                if p in new_tree:
                    write_work(terminal, key, p, new_tree[p])
                else:
                    remove_work(terminal, key, p)
    repo["branches"][repo["head"]] = target
    if mode == "hard":
        return Result(f"HEAD is now at {short(target)} {repo['commits'][target]['msg'].splitlines()[0]}")
    return Result(unstaged_report(terminal, key, repo) if mode == "mixed" else "")


def unstaged_report(terminal, key, repo):
    _, unstaged, _, _ = status_data(terminal, key, repo)
    if not unstaged:
        return ""
    return "Unstaged changes after reset:\n" + "\n".join(f"{'M' if k == 'modified' else 'D'}\t{p}" for p, k in unstaged.items())


def cmd_rm(terminal, key, repo, rest):
    cached = force = False
    specs = []
    for a in rest:
        if a == "--cached":
            cached = True
        elif a in ("-f", "--force"):
            force = True
        elif a in ("-r",):
            pass
        elif a.startswith("-"):
            raise Unsupported()
        else:
            specs.append(a)
    if not specs:
        raise Unsupported()
    work = scan(terminal, key)
    index = repo["index"]
    targets = []
    for arg in specs:
        names = matching(set(index), pathspec(terminal, key, arg))
        if not names:
            raise Fatal(f"fatal: pathspec '{arg}' did not match any files")
        targets += names
    if not cached and not force:
        dirty = [p for p in targets if p in work and work[p] != index[p]]
        if dirty:
            raise Fatal("error: the following file has local modifications:\n" + "\n".join(f"    {p}" for p in dirty)
                        + "\n(use --cached to keep the file, or -f to force removal)", 1)
    out = []
    for p in targets:
        index.pop(p, None)
        if not cached and p in work:
            remove_work(terminal, key, p)
        out.append(f"rm '{p}'")
    return Result("\n".join(out))


def cmd_mv(terminal, key, repo, rest):
    if len(rest) != 2 or any(a.startswith("-") for a in rest):
        raise Unsupported()
    src, dst = pathspec(terminal, key, rest[0]), pathspec(terminal, key, rest[1])
    if src not in repo["index"]:
        raise Fatal(f"fatal: not under version control, source={src}, destination={dst}")
    if terminal.path(rest[1]).is_dir():
        dst = f"{dst}/{posixpath.basename(src)}" if dst else posixpath.basename(src)
    work = scan(terminal, key)
    if dst in work or dst in repo["index"]:
        raise Fatal(f"fatal: destination exists, source={src}, destination={dst}")
    write_work(terminal, key, dst, work.get(src, repo["index"][src]))
    if src in work:
        remove_work(terminal, key, src)
    repo["index"][dst] = repo["index"].pop(src)
    return Result()


def cmd_check_ignore(terminal, key, repo, rest):
    verbose = "-v" in rest
    names = [a for a in rest if not a.startswith("-")]
    if not names:
        raise Unsupported()
    work = scan(terminal, key)
    rules = ignore_rules(work)
    hits = [n for n in names if is_ignored(rules, pathspec(terminal, key, n)) and pathspec(terminal, key, n) not in repo["index"]]
    if verbose:
        raise Unsupported()
    return Result("\n".join(hits), 0 if hits else 1)


def cmd_remote(terminal, key, repo, rest):
    if rest in ([], ["-v"]):
        url = repo["remote"]
        if not url:
            return Result()
        if rest == ["-v"]:
            return Result(f"origin\t{url} (fetch)\norigin\t{url} (push)")
        return Result("origin")
    raise Unsupported()


# ---------------------------------------------------------------- clone（example.com の固定サンプルだけ）
SAMPLE = [
    ("Add README", {"README.md": "# sample-repo\n\nこれは練習用のサンプルリポジトリです。\n"}),
    ("Add greeting script", {"greet.sh": "#!/bin/bash\necho \"Hello, Git!\"\n"}),
    ("Add TODO list", {"TODO.txt": "- git の履歴を読む\n- ブランチを作る\n"}),
]
SAMPLE_FEATURE = ("Add usage guide", {"docs/guide.md": "# Guide\n\nブランチで作業してから main に取り込みます。\n"})


def build_sample(repo):
    repo["clock"] = 0
    tree = {}
    cid = None
    repo["head"] = "main"
    for message, files in SAMPLE:
        tree.update(files)
        cid = make_commit(repo, message, "Example Team", "team@example.com", parent=cid, tree=tree)
    main = cid
    tree2 = {**tree, **SAMPLE_FEATURE[1]}
    feature = make_commit(repo, SAMPLE_FEATURE[0], "Example Team", "team@example.com", parent=main, tree=tree2)
    repo["branches"] = {"main": main}
    repo["head"] = "main"
    repo["remote_refs"] = {"origin/main": main, "origin/HEAD": main, "origin/feature-docs": feature}
    repo["upstream"] = {"main": "origin/main"}
    repo["remote"] = REMOTE_URL
    repo["index"] = dict(repo["commits"][main]["tree"])


def cmd_clone(terminal, rest):
    args = [a for a in rest if not a.startswith("-")]
    if len(args) not in (1, 2) or len(args) != len(rest):
        raise Unsupported()
    url = args[0]
    match = re.fullmatch(r"https?://([^/]+)/(.+?)/?", url)
    if not match:
        raise Fatal(f"fatal: repository '{url}' does not exist")
    host, path = match.groups()
    if host != "example.com":
        raise Fatal(f"fatal: unable to access '{url.rstrip('/')}/': Could not resolve host: {host}")
    if re.sub(r"\.git$", "", path) != "team/sample-repo":
        raise Fatal(f"remote: Repository not found.\nfatal: repository '{url.rstrip('/')}/' not found")
    name = args[1] if len(args) == 2 else "sample-repo"
    base = terminal.path(name)
    if base.exists() and (not base.is_dir() or any(base.iterdir())):
        raise Fatal(f"fatal: destination path '{name}' already exists and is not an empty directory.")
    terminal.ensure_directory(base)
    key = base.relative_to(terminal.active_root).as_posix()
    repo = new_repo()
    build_sample(repo)
    state(terminal)["repos"][key] = repo
    (base / ".git").mkdir(exist_ok=True)
    for p, text in repo["commits"][repo["branches"]["main"]]["tree"].items():
        write_work(terminal, key, p, text)
    shown = posixpath.basename(name.rstrip("/"))
    return Result(f"Cloning into '{shown}'...\nremote: Enumerating objects: 9, done.\n"
                  "remote: Counting objects: 100% (9/9), done.\nremote: Compressing objects: 100% (6/6), done.\n"
                  "remote: Total 9 (delta 1), reused 0 (delta 0), pack-reused 0\n"
                  "Receiving objects: 100% (9/9), done.\nResolving deltas: 100% (1/1), done.")


# ---------------------------------------------------------------- 入口
REPO_COMMANDS = {
    "status": cmd_status, "add": cmd_add, "commit": cmd_commit, "log": cmd_log, "diff": cmd_diff,
    "show": cmd_show, "branch": cmd_branch, "merge": cmd_merge, "restore": cmd_restore, "reset": cmd_reset,
    "rm": cmd_rm, "mv": cmd_mv, "check-ignore": cmd_check_ignore, "remote": cmd_remote,
}
KNOWN_UNSUPPORTED = {"push", "pull", "fetch", "stash", "tag", "rebase", "cherry-pick", "revert", "bisect", "blame",
                      "reflog", "submodule", "clean", "worktree", "apply", "grep", "describe", "shortlog"}


def sync_head(terminal):
    """.git/HEAD を模擬の状態に合わせる（cat で中身を見られる）。"""
    for key, repo in state(terminal)["repos"].items():
        folder = root_path(terminal, key) / ".git"
        if folder.is_dir():
            (folder / "HEAD").write_text(f"ref: refs/heads/{repo['head']}\n", encoding="utf-8")


@on_check
def check_scenario(scenario, terminal):
    for key, expected in scenario.get("expected_git", {}).items():
        repo = state(terminal)["repos"].get(key)
        if repo is None:
            return False, f"{key} にリポジトリがありません。"
        if "branch" in expected and repo["head"] != expected["branch"]:
            return False, "最後に作業するブランチを確認しましょう。"
        if any(name not in repo["branches"] for name in expected.get("branches", [])):
            return False, "必要な作業ブランチがありません。"
        tips = [repo["branches"].get(name) for name in expected.get("same_tip", [])]
        if tips and (None in tips or len(set(tips)) != 1):
            return False, "作業ブランチの内容が本流に取り込まれていません。"
        if "messages" in expected:
            actual = [repo["commits"][c]["msg"] for c in history(repo, head_id(repo))]
            if actual != expected["messages"]:
                return False, "履歴の内容やコミット数が要件と違います。git log で確認しましょう。"
        tree = tree_of(repo, head_id(repo))
        for name, text in expected.get("tracked", {}).items():
            if tree.get(name) != text:
                return False, f"{name} の必要な内容がコミットされていません。"
        if any(name in tree or name in repo["index"] for name in expected.get("untracked", [])):
            return False, "履歴に含めてはいけないファイルが追加されています。"
        work = scan(terminal, key)
        rules = ignore_rules(work)
        if any(not is_ignored(rules, name) for name in expected.get("ignored", [])):
            return False, "秘密情報やログを除外する設定が足りません。"
        if expected.get("clean") and (repo["index"] != tree or
                any(work.get(p) != text for p, text in tree.items()) or
                any(p not in tree and not is_ignored(rules, p) for p in work)):
            return False, "未記録の変更があります。git status で確認しましょう。"
    return None


@command("git")
def git(terminal, rest, stdin=None, admin=False):
    if not rest:
        return Result("usage: git [--version] [--help] <command> [<args>]\n\n"
                      "よく使うコマンド: init / clone / status / add / commit / log / diff / branch / switch / merge / restore", 1)
    sub, args = rest[0], rest[1:]
    try:
        if sub in ("--version", "version") and not args:
            return Result("git version 2.43.0")
        if sub == "config":
            return cmd_config(terminal, args)
        if sub == "init":
            result = cmd_init(terminal, args)
        elif sub == "clone":
            result = cmd_clone(terminal, args)
        elif sub in REPO_COMMANDS:
            key, repo = find_repo(terminal)
            result = REPO_COMMANDS[sub](terminal, key, repo, args)
        elif sub in ("switch", "checkout"):
            key, repo = find_repo(terminal)
            if sub == "checkout" and ("--" in args or (len(args) >= 1 and not args[0].startswith("-")
                                                        and args[0] not in repo["branches"]
                                                        and f"origin/{args[0]}" not in repo["remote_refs"]
                                                        and terminal.path(args[0]).exists())):
                result = cmd_restore(terminal, key, repo, [a for a in args if a != "--"])
            else:
                result = cmd_switch(terminal, key, repo, sub, args)
        elif sub in KNOWN_UNSUPPORTED:
            return None
        elif sub.startswith("-"):
            return None
        else:
            return Result(f"git: '{sub}' is not a git command. See 'git --help'.", 1)
        sync_head(terminal)
        return result
    except Unsupported:
        return None
    except Fatal as error:
        return Result(str(error), error.code)


# ---------------------------------------------------------------- 課題の初期状態
def wipe_children(terminal):
    base = terminal.path(".")
    if base == terminal.active_root:
        raise TrainingError("git の課題は練習フォルダの下の作業フォルダ（cwd）で開始します。")
    import shutil
    for item in base.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


@on_prepare
def prepare(terminal, step):
    """step["git"] = {"identity": bool, "ops": [...]} から、課題ごとに履歴と作業ツリーを作り直す。

    ops: {"init": True} {"write": {path: text}} {"commit": msg, "files": {path: text|None}}（ファイルを書いて全部ステージして
    コミット）{"branch": name}（作って移動）{"switch": name} {"stage": [paths]|True} {"clone": True}（作業フォルダ自体を example.com のサンプルのクローンにする）{"config": {k: v}}
    """
    spec = step.get("git")
    if spec is None:
        return
    git_state = {"config": {}, "repos": {}}
    terminal.progress["git"] = git_state
    if spec.get("identity", True):
        git_state["config"] = {"user.name": "Learner", "user.email": "learner@example.com"}
    wipe_children(terminal)
    key = terminal.cwd
    for op in spec.get("ops", []):
        if "init" in op:
            (terminal.path(".") / ".git").mkdir(exist_ok=True)
            git_state["repos"][key] = new_repo(op.get("branch", "main"))
        elif "clone" in op:
            repo = new_repo()
            build_sample(repo)
            git_state["repos"][key] = repo
            (terminal.path(".") / ".git").mkdir(exist_ok=True)
            for p, text in repo["commits"][repo["branches"]["main"]]["tree"].items():
                write_work(terminal, key, p, text)
        elif "write" in op:
            for p, text in op["write"].items():
                write_work(terminal, op.get("repo", key), p, text)
        elif "commit" in op:
            repo = git_state["repos"][key]
            work = scan(terminal, key)
            for p, text in op.get("files", {}).items():
                if text is None:
                    remove_work(terminal, key, p)
                    repo["index"].pop(p, None)
                else:
                    write_work(terminal, key, p, text)
                    repo["index"][p] = text
            for p in list(repo["index"]):
                if p in work and p not in op.get("files", {}):
                    repo["index"][p] = work[p]
            make_commit(repo, op["commit"], "Learner", "learner@example.com")
        elif "branch" in op:
            repo = git_state["repos"][key]
            repo["branches"][op["branch"]] = head_id(repo)
            repo["head"] = op["branch"]
        elif "switch" in op:
            repo = git_state["repos"][key]
            target = tree_of(repo, repo["branches"][op["switch"]])
            work = scan(terminal, key)
            for p in set(work) & (set(repo["index"]) | set(target)):
                if p not in target:
                    remove_work(terminal, key, p)
            for p, text in target.items():
                write_work(terminal, key, p, text)
            repo["index"] = dict(target)
            repo["head"] = op["switch"]
        elif "stage" in op:
            repo = git_state["repos"][key]
            work = scan(terminal, key)
            names = work if op["stage"] is True else op["stage"]
            for p in names:
                repo["index"][p] = work[p]
        elif "config" in op:
            git_state["config"].update(op["config"])
    sync_head(terminal)
