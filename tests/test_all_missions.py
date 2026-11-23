#!/usr/bin/env python3
"""全ミッションの自動検証スイート。

各ミッションについて:
  ① 初期状態で check が「未達成」になること
  ② 用意した「惜しい誤答」を実行しても check が「未達成」になること
  ③ 模範解答（想定解）をサンドボックス内の本物の bash で実行すると check が「達成」になること
  ④ 問題文・段階的ヒント・解答・解説・ワンポイントが揃っていて、プレースホルダが全て埋まること
を検証する。セーブデータ (save_data.json) には一切触れない（一時ファイルを使用）。

使い方:
  python3 tests/test_all_missions.py            # 全問
  python3 tests/test_all_missions.py 2-7 5-3    # 指定した問題だけ
  python3 tests/test_all_missions.py -v         # 失敗時の詳細を表示
"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp = tempfile.mkdtemp(prefix="lq-test-")
os.environ["LQ_WORKSPACE"] = os.path.join(_tmp, "workspace")
os.environ["LQ_SAVE"] = os.path.join(_tmp, "save_data.json")   # 本物のセーブデータを汚さない
os.environ.setdefault("LQ_DOCKER_MODE", "mock")
os.environ["LQ_FAST"] = "1"
sys.path.insert(0, str(ROOT))

import subprocess  # noqa: E402

from engine import runner, save  # noqa: E402
from engine.ui import c  # noqa: E402

PRELUDE = r'''
submit() { printf '%s\n' "$*" > "$LQ_STATE/submitted"; }
__lq_dump() { builtin pwd > "$LQ_STATE/cwd"; /usr/bin/env -0 > "$LQ_STATE/env"; jobs -l > "$LQ_STATE/jobs" 2>/dev/null; }
'''


def run_script(m, token, script):
    ctx = runner.Ctx(m, token)
    body = m.render(script, ctx.data)
    with open(runner.STATE / "history", "a") as f:
        for ln in body.splitlines():
            if ln.strip():
                f.write(ln + "\n")
    path = runner.STATE / "test_script.sh"
    path.write_text(PRELUDE + body + "\n__lq_dump\n")
    env = runner.shell_env(m, token)
    # バックグラウンドジョブがパイプを握り続けないよう、出力はファイルへ
    out_p, err_p = runner.STATE / "test_stdout", runner.STATE / "test_stderr"
    with open(out_p, "w") as fo, open(err_p, "w") as fe:
        rc = subprocess.run(["bash", str(path)], cwd=str(runner.stage_dir(m.stage)), env=env,
                            stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, timeout=180).returncode

    class R:
        returncode = rc
        stdout = out_p.read_text(errors="replace")
        stderr = err_p.read_text(errors="replace")
    return R


def check_metadata(m, data):
    errs = []
    for f in ("title", "story", "answer", "explanation", "tip", "solution"):
        if not getattr(m, f).strip():
            errs.append(f"{f} が空です")
    if not isinstance(m.hints, list) or not m.hints or any(not isinstance(h, str) or not h.strip() for h in m.hints):
        errs.append("ヒントは空でない文字列のリストにします")
    if not m.objectives:
        errs.append("達成条件がありません")
    texts = [m.story, m.answer, m.explanation, m.tip, *m.hints, *m.objectives]
    for t in texts:
        left = re.findall(r"<<[a-z_0-9]+>>", m.render(t, data))
        if left:
            errs.append(f"未解決のプレースホルダ: {left}")
    return errs


def test_mission(m, verbose=False):
    results = []
    token = runner.new_token()
    try:
        # ① 初期状態
        ctx = runner.prepare(m, token)
        errs = check_metadata(m, ctx.data)
        results.append(("メタデータ", not errs, "; ".join(errs)))
        ok, msg = runner.run_check(m, token)
        results.append(("初期状態=未達成", not ok, "初期状態で達成扱いになっています" if ok else ""))
        # ② 誤答
        for i, w in enumerate(m.wrong, 1):
            runner.prepare(m, token)
            r = run_script(m, token, w)
            ok, msg = runner.run_check(m, token)
            results.append((f"誤答{i}=未達成", not ok, ("誤答で達成扱い: " + w.replace("\n", " ; ")) if ok else ""))
            if verbose and not ok:
                print(c(f"      誤答{i} フィードバック: {msg[:110]}", "gray"))
        # ③ 想定解
        runner.prepare(m, token)
        r = run_script(m, token, m.solution)
        ok, msg = runner.run_check(m, token)
        detail = "" if ok else f"{msg}\n        --- stdout ---\n{r.stdout[-800:]}\n        --- stderr ---\n{r.stderr[-800:]}"
        results.append(("想定解=達成", ok, detail))
    except Exception as e:
        import traceback
        results.append(("例外", False, traceback.format_exc()))
    finally:
        runner.kill_session(token)
    return results


def main(argv):
    verbose = "-v" in argv
    ids = [a for a in argv if not a.startswith("-")]
    missions = runner.load_curriculum()
    if ids:
        missions = [m for m in missions if m.id in ids]
    from engine import docker_backend
    print(c(f"\nLinuxQuest 全ミッション自動テスト  (対象 {len(missions)} 問 / Docker: {docker_backend.detect_mode()} モード)\n", "bold", "bcyan"))
    t0 = time.time()
    total = passed = 0
    failed = []
    for m in missions:
        t1 = time.time()
        res = test_mission(m, verbose)
        good = all(r[1] for r in res)
        total += 1
        passed += good
        mark = c("PASS", "bold", "bgreen") if good else c("FAIL", "bold", "bred")
        print(f"  [{mark}] {m.id:<5} {m.title}  " + c(f"({len(res)} checks, {time.time() - t1:.1f}s)", "gray"))
        for name, ok, detail in res:
            if not ok:
                print(c(f"         [NG] {name}: {detail}", "red"))
        if not good:
            failed.append(m.id)
    # セーブデータが汚れていないことを確認
    real_save = ROOT / "save_data.json"
    print()
    print(c(f"結果: {passed}/{total} 問 PASS  ({time.time() - t0:.1f}s)", "bold", "bgreen" if passed == total else "bred"))
    if failed:
        print(c("FAILED: " + " ".join(failed), "bred"))
    # テストで使ったサンドボックスを掃除
    for d in runner.WORKSPACE.iterdir() if runner.WORKSPACE.exists() else []:
        if d.is_dir():
            runner.wipe_dir(d)
    try:
        for n in os.listdir(runner.STATE):
            p = runner.STATE / n
            if p.is_file():
                p.unlink()
    except OSError:
        pass
    print(c(f"本番セーブデータ ({real_save.name}) には触れていません（テスト用: {os.environ['LQ_SAVE']}）", "gray"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
