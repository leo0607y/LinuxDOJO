#!/usr/bin/env python3
"""/course/ 用の静的データを JSON にまとめる (読み取り専用・決定的・日時なし)。

入力: curriculum/toolbox_catalog.py, curriculum/toolbox_labs.py (+ native 実習の題名),
      docs/LINUX_DAILY_USE.md (学習目標), docs/objectives_matrix.md (集計表),
      labs/vm/guest/modules/*.sh (VM 実習の題名)。
出力: web/danganlog/public/course-data.json と course-search.json (git 管理外)。
検証状況の文言は下の表で手書きし、根拠は docs/coverage.md / docs/HANDOFF.md に置く。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "web" / "danganlog" / "public" / "course-data.json"
FORMAT = 1

# native 実習の検証状況 (docs/coverage.md の「実装と検証記録」)。
NATIVE_VERIFIED = "ネイティブ実機検証済み"
NATIVE_UNIT = "ネイティブ: 実ツールの単体テスト通過、実機検証の記録は未整理"
NATIVE_NEW = "ネイティブ: 追加直後、実機での検証記録は未整理"
NATIVE_STATUS = {"logrotate": ("unit", NATIVE_UNIT), "cron": ("new", NATIVE_NEW), "trap": ("new", NATIVE_NEW),
                 "tcpdump": ("new", NATIVE_NEW), "debbuild": ("new", NATIVE_NEW)}
NATIVE_REAL = {"shell", "find", "archive", "rsync", "git", "vim", "jq", "rg", "curl", "ssh", "tmux",
               "sqlite", "python", "build", "fzf", "tls", "incident", "release", "docker", "python-packages", "safe-cleanup"}

# VM 実習の検証状況。追加分の実出力は docs/vm_verification/ を参照。
VM_REAL = {"boot", "storage", "packages", "permissions", "software", "ssh", "network", "performance", "webstack",
           "sshd", "mounts", "journald", "sysctl", "limits", "ftp", "firewall", "users", "lynis"}
VM_STATIC = { "netconfig", "restore", "osupdate"}
VM_NEW = {"timesync", "guard"}
VM_LABEL = {"real": "VM: 実VMで検証済み",
            "static": "VM: 静的検証のみ、実VM未実施",
            "new": "VM: 追加直後、静的検査のみで実VM未実施"}

# 話題と VM 実習の対応 (編集者が選んだ関連づけ。網羅性の主張ではない)。
VM_FOR = {
    "packages": ["packages", "osupdate"], "permissions": ["permissions"], "users": ["users"],
    "network": ["network", "netconfig"], "ssh": ["ssh", "sshd"], "services": ["software", "boot"],
    "web": ["webstack"], "tls": ["webstack"], "database": ["webstack"], "storage": ["storage", "mounts"],
    "logging": ["journald", "timesync"], "process": ["performance", "limits"],
    "recovery": ["restore", "boot"], "backup": ["restore"], "automation": ["software"],
    "security": ["firewall", "guard", "sshd"], "infrastructure": ["netconfig", "firewall", "sysctl"],
}


def vm_status(module):
    kind = "real" if module in VM_REAL else "static" if module in VM_STATIC else "new"
    return kind, VM_LABEL[kind]


def native_status(lab):
    return NATIVE_STATUS.get(lab, ("verified", NATIVE_VERIFIED) if lab in NATIVE_REAL else ("new", NATIVE_NEW))


def split_sections(text):
    """<a id="x"></a> から次のアンカー/次の見出しまでの本文を id 別に返す。"""
    parts = re.split(r'^<a id="([a-z0-9-]+)"></a>\s*$', text, flags=re.M)
    sections = {}
    for i in range(1, len(parts), 2):
        body = re.split(r"^## (?!#)", parts[i + 1].lstrip("\n"), flags=re.M)
        # 先頭は自分の見出し (## は分割で消える)。次の無アンカー見出し以降は捨てる。
        first = parts[i + 1].lstrip("\n")
        m = re.match(r"## (.+)\n", first)
        heading = m.group(1).strip() if m else parts[i]
        rest = first[m.end():] if m else first
        rest = re.split(r"^## ", rest, flags=re.M)[0]
        sections[parts[i]] = (heading, rest.strip("\n"))
    return sections


def parse_blocks(markdown):
    blocks, para, items, fence = [], [], [], None

    def flush():
        nonlocal para, items
        if para:
            blocks.append({"t": "p", "x": "".join(para)}); para = []
        if items:
            blocks.append({"t": "ul", "x": items}); items = []
    for line in markdown.split("\n"):
        if fence is not None:
            if line.startswith("```"):
                blocks.append({"t": "pre", "x": "\n".join(fence)}); fence = None
            else:
                fence.append(line)
        elif line.startswith("```"):
            flush(); fence = []
        elif not line.strip():
            flush()
        elif line.startswith("|"):
            flush()
        elif re.match(r"^(?:- |\d+\. )", line):
            if para:
                flush()
            items.append(re.sub(r"^(?:- |\d+\. )", "", line))
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return blocks


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("`", "")


def matrix_summary(text):
    """四区分の集計表と各目標行を照合する。未検証を検証済みに混ぜない。"""
    block = text.split("## 集計", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in block.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[1].isdigit():
            rows.append({"exam": cells[0], "rows": int(cells[1]), "covered": int(cells[2]),
                         "unverified": int(cells[3]), "partial": int(cells[4]), "missing": int(cells[5])})
    exams = [r for r in rows if not r["exam"].startswith("合計")]
    total = next((r for r in rows if r["exam"].startswith("合計")), None)
    if total is None:
        raise ValueError("objectives_matrix.md に四区分の集計表がありません")
    keys = ("covered", "unverified", "partial", "missing")
    total = {k: total[k] for k in ("rows", *keys)}
    if total != {k: sum(r[k] for r in exams) for k in total}:
        raise SystemExit("objectives_matrix.md の集計表の合計が各行の和と一致しません")
    counted = {}
    section = None
    for line in text.split("## 集計")[0].split("\n"):
        h = re.match(r"^## (LPIC-1|LPIC-2|LFCS|RHCSA)", line)
        if h:
            section = h.group(1)
        m = re.match(r"^\| .*? \| (COVERED-REAL|IMPLEMENTED-UNVERIFIED|PARTIAL|MISSING) \|", line)
        if m and section:
            c = counted.setdefault(section, dict.fromkeys(keys, 0))
            key = {"COVERED-REAL": "covered", "IMPLEMENTED-UNVERIFIED": "unverified"}.get(m.group(1), m.group(1).lower())
            c[key] += 1
    for exam in exams:
        if sum(exam[k] for k in keys) != exam["rows"] or counted.get(exam["exam"]) != {k: exam[k] for k in keys}:
            raise ValueError(f"objectives_matrix.md の {exam['exam']} の集計と目標行が一致しません")
    notes = block.strip().split("\n")[-1]
    return {"exams": exams, "total": total, "counted": counted,
            "note": plain(notes) if not notes.startswith("|") else ""}


def build(root=ROOT):
    sys.path.insert(0, str(root))
    from curriculum.toolbox_catalog import TOPICS
    from curriculum.toolbox_labs import LABS
    native_titles = {k: v["title"] for k, v in LABS.items()}
    try:
        from curriculum.toolbox_containers import LABS as c
        from curriculum.toolbox_python import LABS as p
        for source in (c, p):
            native_titles.update({k: v["title"] for k, v in source.items()})
    except ImportError:
        pass
    daily = (root / "docs" / "LINUX_DAILY_USE.md").read_text(encoding="utf-8")
    sections = split_sections(daily)
    vm_titles = {}
    for path in sorted((root / "labs" / "vm" / "guest" / "modules").glob("*.sh")):
        m = re.search(r"^# title: (.+)$", path.read_text(encoding="utf-8"), re.M)
        vm_titles[path.stem] = m.group(1).strip() if m else path.stem
    topics, search = [], []
    for t in TOPICS:
        anchor = t["guide"].lstrip("#")
        if anchor not in sections:
            raise SystemExit("LINUX_DAILY_USE.md にアンカー %s がありません" % anchor)
        heading, body = sections[anchor]
        blocks = parse_blocks(body)
        goal = ""
        for b in blocks:
            if b["t"] == "p" and b["x"].startswith("到達確認"):
                goal = plain(b["x"]); break
        if not goal:
            goal = next((plain(b["x"]) for b in blocks if b["t"] == "p"), "")
        labs = []
        for lab in t["labs"]:
            kind, label = native_status(lab)
            labs.append({"id": lab, "title": native_titles.get(lab, lab), "kind": kind, "status": label})
        vms = []
        for module in VM_FOR.get(t["id"], []):
            if module in vm_titles:
                kind, label = vm_status(module)
                vms.append({"id": module, "title": vm_titles[module], "kind": kind, "status": label})
        topic = {"id": t["id"], "title": t["title"], "category": t["category"], "level": t["level"],
                 "commands": t["commands"], "missions": t["missions"], "anchor": anchor,
                 "heading": heading, "goal": goal, "blocks": blocks, "native": labs, "vm": vms,
                 "keywords": t["keywords"]}
        topics.append(topic)
        text = " ".join([t["title"], t["category"], " ".join(t["commands"]), " ".join(t["keywords"]),
                         goal, " ".join(plain(b["x"]) for b in blocks if b["t"] == "p")])
        search.append({"id": t["id"], "title": t["title"], "category": t["category"],
                       "level": t["level"], "goal": goal, "commands": t["commands"],
                       "keywords": t["keywords"], "text": text})
    matrix = matrix_summary((root / "docs" / "objectives_matrix.md").read_text(encoding="utf-8"))
    return {"format": FORMAT, "topics": topics, "coverage": matrix, "search": search,
            "vmModules": sorted(vm_titles), "vmTitles": vm_titles,
            "statusLegend": {"native": [NATIVE_VERIFIED, NATIVE_UNIT, NATIVE_NEW], "vm": list(VM_LABEL.values())}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    data = build()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    # 検索用の軽い索引は別ファイルにして、クライアントが必要な時だけ取得する。
    index = out.with_name("course-search.json")
    index.write_text(json.dumps({"format": FORMAT, "entries": data["search"]}, ensure_ascii=False,
                                sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print("wrote %s (%d topics, %d bytes)" % (out, len(data["topics"]), out.stat().st_size))


if __name__ == "__main__":
    main()
