#!/usr/bin/env python3
"""各Stageの実態を自動判定する（引き継ぎ書の表より、こちらを信頼する）。

状態: STUB=雛形のみ(未作成/作成中) / WRITTEN=課題あり。WRITTEN でも検証済みとは限らない。
検証は: python3 tests/test_all_missions.py <ID...>
使い方: python3 tools/stage_status.py
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import runner  # noqa: E402

counts = Counter(m.stage for m in runner.load_curriculum())
files = sorted((ROOT / "curriculum").glob("stage[0-9]*.py"), key=lambda p: int(re.match(r"stage(\d+)", p.name).group(1)))
total = 0
for f in files:
    n = int(re.match(r"stage(\d+)", f.name).group(1))
    lines = len(f.read_text(encoding="utf-8").splitlines())
    state = "STUB" if lines <= 3 and counts[n] == 0 else "WRITTEN"
    print(f"Stage {n:>2}  {f.name:<42} missions={counts[n]:>3}  lines={lines:>4}  {state}")
    total += counts[n]
print(f"total missions (loaded): {len(runner.load_curriculum())}")
