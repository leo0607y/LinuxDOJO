#!/usr/bin/env python3
"""学習用 crontab シミュレーター。

本物のユーザー crontab には一切触れず、テーブルを $LQ_STATE/sim_crontab に保存する。
  crontab -l          … 登録内容を表示
  crontab -e          … $VISUAL / $EDITOR (既定 vi) で編集し、文法チェックしてから登録
  crontab FILE        … ファイルの内容で **丸ごと置き換え**
  crontab -           … 標準入力の内容で **丸ごと置き換え**
  crontab -r          … 全削除
判定用に parse() / day_matches() をステージ6のミッションからも利用する。
"""
import getpass
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FIELDS = ["minute", "hour", "dom", "month", "dow"]
FIELD_JA = {"minute": "分", "hour": "時", "dom": "日", "month": "月", "dow": "曜日"}
RANGES = {"minute": (0, 59), "hour": (0, 23), "dom": (1, 31), "month": (1, 12), "dow": (0, 7)}
NAMES = {
    "month": {n: i for i, n in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)},
    "dow": {n: i for i, n in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])},
}
MACROS = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
          "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *"}
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")


class CronError(ValueError):
    pass


def _num(tok, kind):
    t = tok.lower()
    if kind in NAMES and t in NAMES[kind]:
        return NAMES[kind][t]
    if not t.isdigit():
        raise CronError(f"bad {kind}")
    return int(t)


def parse_field(text, kind):
    lo, hi = RANGES[kind]
    out = set()
    for part in text.split(","):
        if not part:
            raise CronError(f"bad {kind}")
        step, has_step = 1, False
        if "/" in part:
            part, s = part.split("/", 1)
            if not s.isdigit() or int(s) == 0:
                raise CronError(f"bad {kind}")
            step, has_step = int(s), True
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            a, b = _num(x, kind), _num(y, kind)
        else:
            a = _num(part, kind)
            b = hi if has_step else a
        if not (lo <= a <= hi and lo <= b <= hi) or a > b:
            raise CronError(f"bad {kind}")
        out.update(range(a, b + 1, step))
    if kind == "dow" and 7 in out:
        out.discard(7)
        out.add(0)
    return out


def parse_entry(line):
    """1行（ジョブ行）を解析して dict を返す。"""
    s = line.strip()
    if s.startswith("@"):
        macro, _, cmd = s.partition(" ")
        if macro.lower() == "@reboot":
            return {"reboot": True, "command": cmd.strip(), "line": line}
        if macro.lower() not in MACROS:
            raise CronError("bad time specifier")
        s = MACROS[macro.lower()] + " " + cmd
    parts = s.split(None, 5)
    if len(parts) < 6:
        if len(parts) == 5 and all(re.fullmatch(r"[\w*/,\-]+", p) for p in parts):
            raise CronError("bad command（実行するコマンドがありません）")
        raise CronError("bad minute" if len(parts) < 5 else "bad command")
    e = {"line": line, "command": parts[5].strip(), "raw": parts[:5], "reboot": False}
    for f, raw in zip(FIELDS, parts[:5]):
        e[f] = parse_field(raw, f)
    e["dom_star"] = parts[2].startswith("*")
    e["dow_star"] = parts[4].startswith("*")
    return e


def parse(text):
    """crontab 全体を解析し (entries, envs, errors) を返す。errors は [(行番号, メッセージ)]。"""
    entries, envs, errors = [], [], []
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ENV_RE.match(s):
            envs.append(s)
            continue
        try:
            e = parse_entry(line)
            e["lineno"] = no
            entries.append(e)
        except CronError as ex:
            errors.append((no, str(ex)))
    return entries, envs, errors


def day_matches(e, date):
    """cron の「日」と「曜日」の判定（両方が * 以外なら OR になる仕様も再現）。"""
    dom_ok = date.day in e["dom"]
    dow_ok = ((date.weekday() + 1) % 7) in e["dow"]
    if e["dom_star"] or e["dow_star"]:
        return dom_ok and dow_ok
    return dom_ok or dow_ok


# ------------------------------------------------------------------ CLI
def _store():
    st = os.environ.get("LQ_STATE")
    if not st:
        print("crontab(シミュレーター): LQ_STATE が未設定のため動作できません（ゲーム内シェルから実行してください）。",
              file=sys.stderr)
        sys.exit(1)
    return Path(st) / "sim_crontab"


def _user():
    try:
        return getpass.getuser()
    except Exception:
        return "user"


def _install(text, label="-"):
    if text and not text.endswith("\n"):
        print(f'new crontab file is missing newline before EOF, can\'t install.', file=sys.stderr)
        return 1
    _, _, errors = parse(text)
    if errors:
        for no, msg in errors:
            print(f'"{label}":{no}: {msg}', file=sys.stderr)
        print("errors in crontab file, can't install.", file=sys.stderr)
        return 1
    _store().write_text(text)
    print("（学習用シミュレーター: 本物の crontab は変更していません。`crontab -l` で確認できます）", file=sys.stderr)
    return 0


def usage():
    print("""usage:  crontab [file | -]
        crontab -l   （一覧）
        crontab -e   （エディタで編集）
        crontab -r   （全削除）
※ 学習用シミュレーターです。本物の crontab には触れません。""", file=sys.stderr)
    return 1


def main(argv):
    args = [a for a in argv if a != "-i"]
    if "-u" in args:
        print("crontab(シミュレーター): -u（他ユーザーの crontab 操作）は学習環境では使えません。", file=sys.stderr)
        return 1
    store = _store()
    if not args:
        print("crontab: usage error: file name or - (for stdin) must be specified", file=sys.stderr)
        return usage()
    a = args[0]
    if a == "-l":
        if not store.exists():
            print(f"no crontab for {_user()}", file=sys.stderr)
            return 1
        sys.stdout.write(store.read_text())
        return 0
    if a == "-r":
        if not store.exists():
            print(f"no crontab for {_user()}", file=sys.stderr)
            return 1
        store.unlink()
        return 0
    if a == "-e":
        old = store.read_text() if store.exists() else ""
        fd, tmp = tempfile.mkstemp(prefix="crontab.", dir=str(store.parent))
        with os.fdopen(fd, "w") as f:
            f.write(old)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        try:
            rc = subprocess.call(["sh", "-c", editor + ' "$1"', "sh", tmp])
            new = Path(tmp).read_text()
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if rc != 0:
            print(f"crontab: \"{editor}\" exited with status {rc}", file=sys.stderr)
            return 1
        if new == old:
            print("crontab: no changes made to crontab", file=sys.stderr)
            return 0
        r = _install(new, Path(tmp).name)
        if r:
            print("（編集内容は破棄されました。もう一度 `crontab -e` で修正してください）", file=sys.stderr)
        return r
    if a.startswith("-") and a != "-":
        print(f"crontab: invalid option -- '{a.lstrip('-')}'", file=sys.stderr)
        return usage()
    if a == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(a).read_text()
        except OSError as ex:
            print(f"crontab: {a}: {ex.strerror}", file=sys.stderr)
            return 1
    return _install(text, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
