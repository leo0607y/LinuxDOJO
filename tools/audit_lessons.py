#!/usr/bin/env python3
"""全課題を、ブラウザー版と同じ橋渡し（worker.js 内の Python）経由で実際に動かして検査する。

検査項目（課題ごと）:
  fresh     : 選んだ直後（初期状態）で達成扱いになっていない
  solve     : 代表の正解を入力して達成になる / 正解入力の出力にエラーらしい文言が無い
  hints     : hint を最後まで進め、空・重複・完全解答の漏れ・answer案内の欠落が無い
  answer    : answer を見て、その入力で達成し、復習対象に入り、reset→自力達成で外れる
  variants  : 同じ意味の別の書き方（空白・引用符・オプション順/分割）が受理される
  wrong     : 末尾引数を落とす・コマンドを別物にする誤答が達成にならない
  cross     : 前の課題の正解が、この課題を達成にしてしまわない

使い方: python3 tools/audit_lessons.py [--mode intro,basic,advanced,expert,festival] [--only ID,...] [--json out.json]
結果は標準出力に要約を出し、問題点を一覧する。終了コードは問題点があれば 1。
"""
import argparse
import json
import re
import shlex
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

ERROR_PATTERNS = re.compile(
    r"command not found|No such file or directory|Permission denied|未対応|対応していません|"
    r"Traceback|invalid option|unrecognized option|cannot access|usage:|Usage:|"
    r"そのようなファイル", re.I)
VALUE_FLAGS = {"-p", "-i", "-o", "-f", "-n", "-c", "-k", "-t", "-d", "-e", "-m", "-u", "-g", "-s", "-b", "-A", "-B",
               "-C", "-L", "-R", "-l", "-P", "-D"}


def load():
    from test_web_bridge import _load_bridge
    tmp = tempfile.TemporaryDirectory()
    ns = _load_bridge(Path(tmp.name) / "session")
    return ns, tmp


def lines_of(command):
    cmds = [command] if isinstance(command, str) else list(command)
    out = []
    for c in cmds:
        out.extend(c.split("\n"))
    return out


def run_lines(req, lines):
    view = None
    for line in lines:
        view = req({"type": "execute", "line": line})
    return view


def leak(hint, answers):
    """ヒントに完全な正解（2語以上の行）がそのまま入っていないか。"""
    for a in answers:
        for line in lines_of(a):
            line = line.strip()
            if len(line.split()) >= 2 and line in hint:
                return line
    return None


def variants(command):
    """正解の1行から、同じ意味の別の書き方を作る（複数行・パイプ等を含むものは対象外）。"""
    if not isinstance(command, str) or "\n" in command or re.search(r"[|;&<>$`\\]", command):
        return {}
    try:
        words = shlex.split(command)
    except ValueError:
        return {}
    if len(words) < 2:
        return {}
    out = {}
    no_space = all(" " not in w for w in words)
    if no_space:
        out["空白が多い"] = "  ".join(words)
        out["タブ区切り"] = "\t".join(words)
    plain = [w for w in words[1:] if re.fullmatch(r"[A-Za-z0-9_./~@:=+,-]+", w) and not w.startswith("-")]
    if plain:
        out["引用符付き"] = " ".join([words[0]] + [f"'{w}'" if w in plain else w for w in words[1:]])
        out["二重引用符付き"] = " ".join([words[0]] + [f'"{w}"' if w in plain else w for w in words[1:]])
    groups, i = [], 1
    while i < len(words) and words[i].startswith("-") and len(words[i]) > 1:
        if words[i] in VALUE_FLAGS and i + 1 < len(words) and not words[i + 1].startswith("-"):
            groups.append([words[i], words[i + 1]]); i += 2
        else:
            groups.append([words[i]]); i += 1
    rest = words[i:]
    if len(groups) >= 2:
        rev = [w for g in reversed(groups) for w in g]
        out["オプション順を逆"] = " ".join([words[0]] + rev + rest)
    if words[0] in ("ip", "find", "java", "ssh", "openssl"):
        return {k: v for k, v in out.items() if v and v != command}
    short = [g[0] for g in groups if len(g) == 1 and re.fullmatch(r"-[A-Za-z]+", g[0])]
    if short and len(groups) == len(short):
        letters = "".join(f[1:] for f in short)
        if len(short) >= 2 or len(letters) >= 2:
            out["オプションを結合"] = " ".join([words[0], "-" + letters] + rest)
            out["オプションを分割"] = " ".join([words[0]] + ["-" + c for c in letters] + rest)
    return {k: v for k, v in out.items() if v and v != command}


def wrongs(command):
    if not isinstance(command, str) or "\n" in command:
        return []
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    out = []
    if words[0] == "echo":
        return [("末尾の語を落とす", " ".join(shlex.quote(w) for w in words[:-1]))] if len(words) >= 3 else []
    if len(words) >= 2:
        out.append(("末尾の語を落とす", " ".join(shlex.quote(w) for w in words[:-1])))
    out.append(("コマンドを別物にする", "echo " + " ".join(shlex.quote(w) for w in words[1:])))
    return out


def audit(mode_filter=None, only=None):
    ns, tmp = load()
    req = lambda d: json.loads(ns["browser_request"](json.dumps(d)))
    L = dict(ns["LESSONS"])
    L["festival"] = ns["_web_scenarios"]
    problems, stats = [], {}
    prev_answer = {}
    for mode, items in L.items():
        if mode_filter and mode not in mode_filter:
            continue
        s = stats.setdefault(mode, {"total": 0, "bad": 0})
        for i, step in enumerate(items):
            if only and step["id"] not in only:
                continue
            s["total"] += 1
            sid = step["id"]
            found = []

            def bad(kind, detail):
                found.append((kind, detail))

            festival = mode == "festival"
            solution = step["solution"] if festival else step["command"]
            try:
                req({"type": "select", "mode": mode, "index": i})
                reset = req({"type": "reset"})
                if reset.get("completed"):
                    bad("fresh", "初期状態で達成扱い")
                outs = []
                v = None
                for line in lines_of(solution):
                    v = req({"type": "execute", "line": line})
                    outs.append(v.get("output", ""))
                if festival:
                    v = req({"type": "execute", "line": "check"})
                    outs.append(v.get("output", ""))
                if not v.get("completed"):
                    last = outs[-1].strip().splitlines()
                    bad("solve", "代表の正解で達成にならない: " + (last[-1] if last else "(出力なし)"))
                text = "\n".join(outs)
                m = None if festival else ERROR_PATTERNS.search(text)
                if m and not step.get("expected_code"):
                    bad("output", "正解入力の出力にエラーらしい文言「%s」: %s" % (m.group(0), text.strip()[:140].replace("\n", " | ")))
                # ヒント
                req({"type": "reset"})
                answers = list(ns["guided"].answers(step)) if not festival else (
                    list(step["solution"]) if isinstance(step["solution"], list) else [step["solution"]])
                seen = []
                for _ in range(40):
                    t = req({"type": "hint"})["output"]
                    if t in seen:
                        break
                    seen.append(t)
                if not seen or all(not h.strip() for h in seen):
                    bad("hints", "ヒントが空")
                for h in seen:
                    lk = leak(h, answers)
                    if lk:
                        bad("hints", f"ヒントに完全な正解が出ている: {lk}")
                        break
                if len(seen) < 2 and not festival:
                    bad("hints", "ヒントが1段階しかない")
                if seen and "answer" not in seen[-1]:
                    bad("hints", "最後のヒントに answer の案内がない")
                # answer と復習
                req({"type": "reset"})
                av = req({"type": "answer"})
                if not av.get("output"):
                    bad("answer", "answer の出力が空")
                for line in lines_of(solution):
                    v = req({"type": "execute", "line": line})
                if festival:
                    v = req({"type": "execute", "line": "check"})
                if not v.get("completed"):
                    bad("answer", "answer 後に入力しても達成にならない")
                if (mode + ":" + sid) not in req({"type": "export"})["state"].get("review", {}):
                    bad("review", "answer 後に復習対象へ入らない")
                req({"type": "reset"})
                for line in lines_of(solution):
                    req({"type": "execute", "line": line})
                if festival:
                    req({"type": "execute", "line": "check"})
                if (mode + ":" + sid) in req({"type": "export"})["state"].get("review", {}):
                    bad("review", "reset 後に自力達成しても復習対象が外れない")
                # 別の書き方・誤答・他課題の答え（入力一致で判定する課題のみ）
                if not festival and step.get("goal") is None and isinstance(step["command"], str):
                    for label, line in variants(step["command"]).items():
                        req({"type": "reset"})
                        if not run_lines(req, [line]).get("completed"):
                            bad("variant", f"同じ意味の書き方が通らない [{label}]: {line}")
                    for label, line in wrongs(step["command"]):
                        req({"type": "reset"})
                        if run_lines(req, [line]).get("completed"):
                            bad("wrong", f"誤答が達成になる [{label}]: {line}")
                    pa = prev_answer.get(mode)
                    if pa and pa not in answers:
                        req({"type": "reset"})
                        if run_lines(req, lines_of(pa)).get("completed"):
                            bad("cross", f"前の課題の正解が通る: {pa}")
                if not festival and isinstance(step["command"], str):
                    prev_answer[mode] = step["command"]
            except Exception as e:  # noqa: BLE001
                bad("exception", f"{type(e).__name__}: {e}")
            if found:
                s["bad"] += 1
                for kind, detail in found:
                    problems.append({"mode": mode, "id": sid, "index": i, "kind": kind, "detail": detail})
    return stats, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="intro,basic,advanced,expert,festival")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    stats, problems = audit(set(args.mode.split(",")), set(filter(None, args.only.split(","))))
    for mode, s in stats.items():
        print(f"{mode}: {s['total']}問 / 問題あり {s['bad']}問")
    kinds = {}
    for p in problems:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print("種類別:", kinds)
    for p in problems[:500]:
        print(f"[{p['kind']}] {p['mode']} {p['id']}: {p['detail']}")
    if args.json:
        Path(args.json).write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
