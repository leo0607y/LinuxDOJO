#!/usr/bin/env python3
"""この環境にインストール済みのコマンドのうち、教材に一度も出てこないものを列挙する。

使い方: python3 tools/audit_coverage.py [--list]
カバー判定は「教材・エンジンのソースにコマンド名が単語として現れるか」。名前が出ることと
身につくことは別なので、これは下限の目安。実際の到達目標・判定方式は docs/coverage.md で管理し、
python3 -m engine.toolbox audit で課題・実習への参照を確認する。
"""
import glob
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = """coreutils util-linux procps findutils grep sed gawk iproute2 systemd kmod e2fsprogs mount login passwd
login shadow bsdutils diffutils tar gzip bzip2 xz-utils less net-tools iputils-ping openssh-client openssh-server curl wget
lvm2 mdadm parted fdisk cron rsync apt dpkg man-db psmisc lsof strace ethtool dnsutils iptables nftables sudo kbd udev
tcpdump traceroute git vim tmux jq""".split()


def installed_commands():
    names = set()
    for p in PACKAGES:
        out = subprocess.run(["dpkg", "-L", p], capture_output=True, text=True).stdout
        for line in out.splitlines():
            m = re.fullmatch(r"/(?:usr/)?s?bin/([^/]+)", line)
            if m:
                names.add(m.group(1))
    return sorted(names)


def corpus():
    parts = []
    for pat in ("curriculum/**/*.py", "engine/**/*.py"):
        for f in glob.glob(str(ROOT / pat), recursive=True):
            parts.append(Path(f).read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def main():
    text = corpus()
    cmds = installed_commands()
    miss = [c for c in cmds if not re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", text)]
    print(f"{len(cmds) - len(miss)}/{len(cmds)} commands mentioned ({len(miss)} missing)")
    if "--list" in sys.argv or miss:
        print(" ".join(miss))


if __name__ == "__main__":
    main()
