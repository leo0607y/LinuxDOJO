#!/usr/bin/env python3
"""ブラウザー版が使う Python ソースを web/danganlog/dist/python-source.json にまとめる。

読み取り専用: engine/ と curriculum/ は変更しない。
worker.js と同じ手順 (curriculum を空のパッケージに差し替えて import) を別プロセスで実行し、
実際に読み込まれた自作モジュールだけを収録する。同じ入力なら出力は常に同一 (日時なし)。
save_data.json / workspace/ / bin/ / 本物の bash を起動する実践ステージは含めない。
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "web" / "danganlog" / "dist" / "python-source.json"
FORMAT = 1

# worker.js の PYTHON_BRIDGE と同じ import 手順に、遅延 import (総合復習・プラグイン) を加えたもの。
_TRACE = r"""
import json, sys, types
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
package = types.ModuleType('curriculum'); package.__path__ = [str(root / 'curriculum')]
sys.modules['curriculum'] = package
from engine import guided, readiness, vim_sim
from curriculum.beginner_lessons import LESSONS
readiness.scenarios()
from engine import commands
commands.load()
names = sorted(str(Path(m.__file__).resolve().relative_to(root)) for m in list(sys.modules.values())
               if getattr(m, '__file__', None) and Path(m.__file__).resolve().is_relative_to(root))
print(json.dumps(names))
"""

FORBIDDEN_PARTS = {"workspace", "bin", "sysroot", ".lq_state", "__pycache__"}
FORBIDDEN_NAMES = {"save_data.json", "save_data.tmp", "main.py", "cli.py"}


def module_files(root=ROOT):
    """worker が必要とする .py の相対パス (POSIX 形式、昇順)。curriculum/__init__.py は除く。"""
    out = subprocess.run([sys.executable, "-I", "-c", _TRACE, str(root)], capture_output=True, text=True,
                         check=True, cwd=str(root)).stdout
    names = [n.replace("\\", "/") for n in json.loads(out.strip().splitlines()[-1])]
    names = [n for n in names if n != "curriculum/__init__.py"]
    for name in names:
        parts = set(name.split("/"))
        if not name.endswith(".py") or parts & FORBIDDEN_PARTS or Path(name).name in FORBIDDEN_NAMES:
            raise SystemExit(f"収録できないファイルが読み込まれました: {name}")
    return sorted(set(names))


def build(root=ROOT):
    files = {name: (root / name).read_text(encoding="utf-8") for name in module_files(root)}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"format": FORMAT, "sha256": digest, "files": files}


def write(out=DEFAULT_OUT, root=ROOT):
    bundle = build(root)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    bundle = write(args.output)
    size = Path(args.output).stat().st_size
    print(f"{args.output}: {len(bundle['files'])} files, {size} bytes, sha256 {bundle['sha256'][:12]}")


if __name__ == "__main__":
    main()
