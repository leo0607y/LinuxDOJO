"""Bounded fixture validators for host-security training.

These parsers do not replace sshd -t, visudo, or systemd-analyze verify. They
validate the deliberately small configuration language used by the exercises.
No configuration is applied to the machine running the course.
"""
import hashlib
import json
from pathlib import PurePosixPath
import shlex
import tarfile


def confined_file(ctx, name):
    path = ctx.p(name)
    try:
        resolved = path.resolve()
        is_file = path.is_file()
    except OSError:
        ctx.fail(f"{name} を調べられません。ディレクトリの探索権限も確認してください。")
    ctx.require(ctx.work.resolve() in resolved.parents and not path.is_symlink(),
                f"{name}: 教材内の通常ファイルを使ってください。")
    ctx.require(is_file, f"{name} がありません。")
    return path


def read_json(ctx, name):
    path = confined_file(ctx, name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        ctx.fail(f"{name} を正しい JSON として保存してください。")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ssh_values(text):
    """First global value wins. Match/Include are outside this exercise's scope."""
    values = {}
    for line in text.splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        key = words[0].lower()
        if key in ("match", "include") or len(words) < 2:
            raise ValueError("この演習では Match/Include を追加せず、全体設定を編集します。")
        values.setdefault(key, " ".join(words[1:]))
    return values


def service_values(text):
    """Small systemd fixture subset; scalar directives use their final value."""
    section, values = None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line or line.endswith("\\"):
            raise ValueError("この演習の unit は1行1項目の key=value 形式です。")
        key, value = [part.strip() for part in line.split("=", 1)]
        if section == "Service":
            if key in values and key in ("ExecStart", "ReadWritePaths", "AmbientCapabilities"):
                raise ValueError("この演習ではリスト型項目を複数行に分けません。")
            values[key] = value
    return values


def archive_texts(path):
    """Read a bounded regular-file archive without extracting any members."""
    result = {}
    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()
        if len(members) > 100 or sum(m.size for m in members) > 1024 * 1024:
            raise ValueError("演習用アーカイブの容量上限を超えています。")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk():
                raise ValueError("リンクや範囲外パスを含むアーカイブは提出できません。")
            if member.isdir():
                continue
            key = str(name)
            if not member.isfile() or key in result:
                raise ValueError("通常ファイルを重複なく格納してください。")
            result[key] = archive.extractfile(member).read().decode("utf-8")
    return result
