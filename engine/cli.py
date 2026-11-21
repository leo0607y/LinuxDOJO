#!/usr/bin/env python3
"""ゲーム用サブシェル内から呼ばれるサポートコマンド群。

mission / hint / answer / check / submit / reset / autocheck / help
終了コード: 10 = 次の問題へ, 11 = メニューへ, それ以外 = サブシェルに留まる
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import save, ui  # noqa: E402
from engine.ui import c, fmt, box  # noqa: E402
from engine import runner  # noqa: E402

STATE = runner.STATE


def _mission():
    mid = os.environ.get("LQ_MISSION")
    if not mid:
        try:
            mid = json.loads((STATE / "session.json").read_text())["mission"]
        except (OSError, ValueError, KeyError):
            mid = None
    m = runner.get_mission(mid) if mid else None
    if not m:
        print(c("現在のミッションが特定できません。`menu` でメインメニューに戻ってください。", "red"))
        sys.exit(1)
    return m


def _data():
    try:
        return json.loads((STATE / "data.json").read_text())
    except (OSError, ValueError):
        return {}


def _hint_level():
    try:
        return json.loads((STATE / "hints.json").read_text()).get("level", 0)
    except (OSError, ValueError):
        return 0


def _set_hint_level(n):
    (STATE / "hints.json").write_text(json.dumps({"level": n}))


def _answer_viewed():
    return (STATE / "answer_viewed").exists()


def _tty():
    return sys.stdin.isatty() and sys.stdout.isatty()


def stage_label(m):
    s = runner.STAGES[m.stage]
    idx = [x.id for x in runner.missions_of(m.stage)].index(m.id) + 1
    total = len(runner.missions_of(m.stage))
    return f"{s[0]}「{s[1]}」 第{idx}問 / 全{total}問"


def _shown_path(path):
    """教材フォルダ内なら相対表示。LQ_WORKSPACE が外にある場合は絶対パスのまま表示する。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def cmd_mission(brief=False):
    m = _mission()
    d = _data()
    lines = [c(stage_label(m), "gray"), ""]
    lines += [fmt(x) for x in m.render(m.story, d).strip().split("\n")]
    lines += ["", c(f"{ui.HEAD} 達成条件", "bold", "byellow")]
    for o in m.objectives:
        lines.append("  " + c("▶ ", "byellow") + fmt(m.render(o, d)))
    lines += ["", c(f"{ui.HEAD} 作業ディレクトリ: ", "bold") + c(_shown_path(runner.stage_dir(m.stage)) + "/", "bcyan")]
    if m.docker:
        from engine import docker_backend
        mode = docker_backend.detect_mode()
        if mode == "mock":
            lines.append(c(f"{ui.INFO} Docker: シミュレーションモード", "bold", "bmagenta") +
                         c("（docker 未導入/権限なしのため、学習用の模擬 docker CLI で動作中）", "gray"))
        else:
            lines.append(c(f"{ui.INFO} Docker: 本物の Docker デーモンを使用中", "bold", "bgreen"))
    print()
    print(box(lines, title=f"MISSION {m.id}  {m.title}", color="magenta", title_color="bmagenta"))
    cmds = ["mission", "hint", "answer", "check", "submit <答>", "reset_mission", "menu", "skip", "lqhelp"]
    # 幅に収まるよう手で折り返す（コマンド名だけ色を付ける）
    line, w = c("  コマンド: ", "gray"), 12
    for x in cmds:
        if w + ui.width(x) + 2 > ui.term_width() - 2:
            print(line)
            line, w = "            ", 12
        line += c(x, "bcyan") + "  "
        w += ui.width(x) + 2
    print(line)
    print()


def cmd_help():
    rows = [
        ("mission", "問題文・達成条件・作業ディレクトリを再表示"),
        ("hint", "段階的ヒント (1:考え方 → 2:使うコマンド → 3:具体的なオプション例)"),
        ("hint 2", "指定した段階までのヒントを表示"),
        ("answer", "模範解答と徹底解説を表示（スコアは半分になります）"),
        ("check", "達成条件を満たしているか判定（クリアで次の問題へ）"),
        ("submit <答え>", "調べた答え（合言葉・PID・ポート番号など）を提出"),
        ("reset_mission", "この問題のサンドボックスを初期状態に戻す"),
        ("skip", "この問題を飛ばして次の問題へ"),
        ("menu / exit", "メインメニューへ戻る（Ctrl+D でも可）"),
    ]
    print()
    print(ui.table(["コマンド", "説明"], [(c(a, "bcyan"), b) for a, b in rows]))
    print(c("\n  ※ それ以外は普通の bash です。タブ補完・パイプ・Ctrl+R なども使えます。", "gray"))
    print()


def cmd_hint(args):
    m = _mission()
    d = _data()
    lv = _hint_level()
    if args and args[0].isdigit():
        target = max(1, min(3, int(args[0])))
    else:
        target = min(3, lv + 1)
    if target > lv:
        _set_hint_level(target)
        save.bump("hints")
    labels = [f"{ui.HINT} 1: 考え方", f"{ui.HINT} 2: 使うコマンド", f"{ui.HINT} 3: 具体的なオプション例"]
    lines = []
    for i in range(target):
        lines.append(c(labels[i], "bold", "byellow"))
        lines += ["  " + fmt(x) for x in m.render(m.hints[i], d).strip().split("\n")]
        lines.append("")
    if target < 3:
        lines.append(c("さらにヒントが欲しければ、もう一度 `hint` と入力してください。".replace("`", ""), "gray"))
    else:
        lines.append(c("それでも分からなければ answer で模範解答を見られます（獲得スコアは半分）。", "gray"))
    print()
    print(box(lines, title="HINT", color="yellow", title_color="byellow"))
    print()


def show_answer(m, d):
    lines = [c("▼ 模範解答", "bold", "bgreen")]
    lines += ["  " + c(x, "bcyan") for x in m.render(m.answer, d).strip().split("\n")]
    lines += ["", c("▼ 徹底解説", "bold", "bgreen")]
    lines += [fmt(x) for x in m.render(m.explanation, d).strip().split("\n")]
    print()
    print(box(lines, title="ANSWER", color="green", title_color="bgreen"))
    print()


def cmd_answer():
    m = _mission()
    if not _answer_viewed() and _tty():
        try:
            yn = input(c("模範解答を表示するとこの問題の獲得スコアが半分になります。表示しますか？ [y/N] ", "yellow"))
        except EOFError:
            yn = ""
        if yn.strip().lower() not in ("y", "yes"):
            print(c("キャンセルしました。hint も活用してみましょう！", "gray"))
            return 0
    if not _answer_viewed():
        (STATE / "answer_viewed").write_text("1")
        save.bump("answers")
    show_answer(m, _data())
    return 0


def celebrate(m):
    d = _data()
    try:
        started = json.loads((STATE / "session.json").read_text()).get("started", time.time())
    except (OSError, ValueError):
        started = time.time()
    already = (STATE / "cleared").exists()
    res = save.record_clear(m, _hint_level(), _answer_viewed(), time.time() - started)
    (STATE / "cleared").write_text("1")
    print()
    print(ui.clear_art())
    print()
    lines = [c(f"MISSION {m.id}「{m.title}」 クリア！", "bold", "bgreen"), ""]
    lines.append(f"獲得スコア: {c(str(res['score']), 'bold', 'byellow')} / {m.points} pt"
                 + (c("  (ヒント使用)", "gray") if _hint_level() else "")
                 + (c("  (解答閲覧)", "gray") if _answer_viewed() else ""))
    lines += ["", c(f"{ui.HEAD} 実務ワンポイント解説", "bold", "bcyan")]
    lines += [fmt(x) for x in m.render(m.tip, d).strip().split("\n")]
    lines += ["", c(f"{ui.HEAD} 模範解答の一例", "bold", "bcyan")]
    lines += ["  " + c(x, "bcyan") for x in m.render(m.answer, d).strip().split("\n")]
    print(box(lines, title="CLEAR", color="green", title_color="byellow"))
    if res["activity"]["earned"]:
        print(c(f"\n  +{res['activity']['earned']} XP！", "bold", "byellow"))
    print("  " + save.activity_line(save.load()))
    if res["titles"] and not already:
        for t in res["titles"]:
            print(c(f"\n  称号を獲得しました: {t}", "bold", "bmagenta"))
    if res["rankup"] and not already:
        r = res["rankup"]
        print(c(f"\n  ランクアップ！ {r[1]} {r[2]} に昇格しました！", "bold", "byellow"))
    print()
    if not _tty():
        return 0
    try:
        ans = input(c("  Enter: 次の問題へ  /  s: この問題に残る  /  m: メニューへ  > ", "bold", "white"))
    except EOFError:
        return 0
    ans = ans.strip().lower()
    if ans == "s":
        print(c("  この問題に残ります。次へ進むときは skip、メニューは menu です。", "gray"))
        return 0
    if ans == "m":
        return 11
    return 10


def cmd_check(quiet_fail=False):
    m = _mission()
    save.bump("checks")
    ok, msg = runner.run_check(m)
    if ok:
        return celebrate(m)
    if not quiet_fail:
        print()
        print(box([c(f"{ui.NG} まだ達成条件を満たしていません。", "bold", "bred"), "", *[fmt(x) for x in msg.split("\n")]],
                  title="CHECK: 未達成", color="red", title_color="bred"))
        print(c("  ヒントが必要なら hint 、条件の確認は mission 、やり直しは reset_mission\n", "gray"))
    return 1


def cmd_submit(args):
    text = " ".join(args).strip()
    if not text:
        print(c("使い方: submit <答え>   例: submit 8080", "yellow"))
        return 1
    (STATE / "submitted").write_text(text + "\n")
    print(c(f"  {ui.INFO} 「{text}」を提出しました。判定します…", "gray"))
    return cmd_check()


def cmd_reset():
    m = _mission()
    token = os.environ.get("LQ_SESSION") or runner.new_token()
    runner.prepare(m, token)
    save.bump("resets")
    print(c(f"\n  {ui.OK} ミッション {m.id} のサンドボックスを初期状態に戻しました。", "bold", "bgreen"))
    cmd_mission()
    return 0


def cmd_autocheck():
    if (STATE / "cleared").exists() or (STATE / "notified").exists():
        return 0
    m = _mission()
    ok, _ = runner.run_check(m)
    if ok:
        (STATE / "notified").write_text("1")
        print(c(f"  {ui.OK} 達成条件を満たしたようです！ ", "bold", "byellow") + c("check", "bold", "bcyan")
              + c(" と入力して判定しましょう。", "bold", "byellow"))
    return 0


def main(argv):
    if not argv:
        cmd_help()
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "mission":
        cmd_mission()
        return 0
    if cmd == "help":
        cmd_help()
        return 0
    if cmd == "hint":
        cmd_hint(args)
        return 0
    if cmd == "answer":
        return cmd_answer()
    if cmd == "check":
        return cmd_check()
    if cmd == "submit":
        return cmd_submit(args)
    if cmd == "reset":
        return cmd_reset()
    if cmd == "autocheck":
        try:
            return cmd_autocheck()
        except Exception:
            return 0
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
