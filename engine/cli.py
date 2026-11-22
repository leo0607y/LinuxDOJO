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


def footer_line():
    """どの画面でも同じキー案内。ミッション中はこの 1 行を共通の足場にする。"""
    return ui.footer(("mission", "問題"), ("hint", "ヒント"), ("answer", "解答"), ("check", "判定"),
                     ("menu", "戻る"), ("lqhelp", "一覧"))


def _shown_path(path):
    """教材フォルダ内なら相対表示。LQ_WORKSPACE が外にある場合は絶対パスのまま表示する。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def cmd_mission(brief=False):
    m = _mission()
    d = _data()
    lv = _hint_level()
    sname = runner.STAGES[m.stage][0]
    idx = [x.id for x in runner.missions_of(m.stage)].index(m.id) + 1
    lines = [c(f"{sname}  第 {idx} / {len(runner.missions_of(m.stage))} 問   ヒント {lv}/3", "dim"),
             c(runner.STAGES[m.stage][1], "dim"), ""]
    lines += [fmt(x) for x in m.render(m.story, d).strip().split("\n")]
    lines += ["", ui.rule("達成条件", w=ui.term_width() - 6)]
    for i, o in enumerate(m.objectives, 1):
        lines.append("  " + c(f"{i}.", "bold", "accent") + " " + fmt(m.render(o, d)))
    lines += ["", c("作業場所  ", "dim") + c(_shown_path(runner.stage_dir(m.stage)) + "/", "accent")]
    if m.docker:
        from engine import docker_backend
        mode = docker_backend.detect_mode()
        if mode == "mock":
            lines.append(c("Docker    ", "dim") + "シミュレーションモード" +
                         c("（模擬 docker CLI で動作中）", "dim"))
        else:
            lines.append(c("Docker    ", "dim") + "本物の Docker デーモンを使用中")
    print()
    print(box(lines, title=f"MISSION {m.id}  {m.title}"))
    print(footer_line())
    print()


def cmd_intro():
    """サブシェル起動直後の 1 行案内（問題文は上部に固定表示されている）。"""
    print()
    print(footer_line())
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
    print(ui.rule("ゲーム内コマンド", w=ui.term_width() - 2))
    print("\n".join("  " + x for x in ui.table(["コマンド", "説明"], [(c(a, "accent"), b) for a, b in rows]).split("\n")))
    print(c("\n  それ以外は普通の bash です。タブ補完・パイプ・Ctrl+R なども使えます。", "dim"))
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
    labels = ["考え方", "使うコマンド", "具体的なオプション例"]
    lines = []
    for i in range(target):
        lines.append(c(f"{ui.HINT} {i + 1}. {labels[i]}", "bold", "accent"))
        lines += ["  " + fmt(x) for x in m.render(m.hints[i], d).strip().split("\n")]
        lines.append("")
    if target < 3:
        lines.append(c("さらにヒントが欲しければ、もう一度 hint と入力してください。", "dim"))
    else:
        lines.append(c("それでも分からなければ answer で模範解答を見られます（獲得スコアは半分）。", "dim"))
    print()
    print(box(lines, title=f"HINT {target}/3"))
    print(footer_line())
    print()


def show_answer(m, d):
    lines = [ui.rule("模範解答", w=ui.term_width() - 6)]
    lines += ["  " + c(x, "accent") for x in m.render(m.answer, d).strip().split("\n")]
    lines += ["", ui.rule("徹底解説", w=ui.term_width() - 6)]
    lines += [fmt(x) for x in m.render(m.explanation, d).strip().split("\n")]
    print()
    print(box(lines, title="ANSWER"))
    print(footer_line())
    print()


def cmd_answer():
    m = _mission()
    if not _answer_viewed() and _tty():
        try:
            yn = input(c(f"{ui.WARN} 模範解答を表示するとこの問題の獲得スコアが半分になります。表示しますか？ [y/N] ", "yellow"))
        except EOFError:
            yn = ""
        if yn.strip().lower() not in ("y", "yes"):
            print(ui.status_line("info", "キャンセルしました。hint も活用してみましょう。"))
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
    art = ui.clear_art()
    if art:
        print(art + "\n")
    hinted = _hint_level()
    lines = [c(f"{ui.OK} MISSION {m.id}「{m.title}」 クリア", "bold", "green"), "",
             f"{c('獲得スコア', 'dim')}  {c(str(res['score']), 'bold')} / {m.points} pt"
             + (c("   ヒント使用", "dim") if hinted else "") + (c("   解答閲覧", "dim") if _answer_viewed() else "")]
    if res["activity"]["earned"]:
        lines.append(f"{c('学習XP', 'dim')}      +{res['activity']['earned']}")
    lines.append(c(ui.clip(save.activity_line(save.load()), ui.term_width() - 8), "dim"))
    w = ui.term_width() - 6
    lines += ["", ui.rule("実務ワンポイント解説", w=w)]
    lines += [fmt(x) for x in m.render(m.tip, d).strip().split("\n")]
    lines += ["", ui.rule("模範解答の一例", w=w)]
    lines += ["  " + c(x, "accent") for x in m.render(m.answer, d).strip().split("\n")]
    print(box(lines, title="CLEAR", color="ok"))
    if res["titles"] and not already:
        for t in res["titles"]:
            print("\n  " + c("称号を獲得しました", "dim") + "  " + c(t, "bold", "accent"))
    if res["rankup"] and not already:
        r = res["rankup"]
        print("\n  " + c("ランクアップ", "dim") + "  " + c(f"{r[1]} {r[2]}", "bold", "accent") + " に昇格しました")
    print()
    if not _tty():
        return 0
    try:
        print(ui.footer(("Enter", "次の問題へ"), ("s", "この問題に残る"), ("m", "メニューへ")))
        ans = input(c("\n  > ", "bold", "accent"))
    except EOFError:
        return 0
    ans = ans.strip().lower()
    if ans == "s":
        print(ui.status_line("info", "この問題に残ります。次へ進むときは skip、メニューは menu です。"))
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
        print(box([c(f"{ui.NG} まだ達成条件を満たしていません", "bold", "red"), "", *[fmt(x) for x in msg.split("\n")]],
                  title="CHECK  未達成", color="ng"))
        print(footer_line())
        print()
    return 1


def cmd_submit(args):
    text = " ".join(args).strip()
    if not text:
        print(ui.status_line("warn", "使い方: submit <答え>", "例: submit 8080"))
        return 1
    (STATE / "submitted").write_text(text + "\n")
    print(ui.status_line("info", f"「{text}」を提出しました。判定します…"))
    return cmd_check()


def cmd_reset():
    m = _mission()
    token = os.environ.get("LQ_SESSION") or runner.new_token()
    runner.prepare(m, token)
    save.bump("resets")
    print("\n" + ui.status_line("ok", f"ミッション {m.id} のサンドボックスを初期状態に戻しました"))
    cmd_mission()
    return 0


def cmd_autocheck():
    if (STATE / "cleared").exists() or (STATE / "notified").exists():
        return 0
    m = _mission()
    ok, _ = runner.run_check(m)
    if ok:
        (STATE / "notified").write_text("1")
        print(ui.status_line("ok", "達成条件を満たしたようです。") + "  " + c("check", "bold", "accent")
              + " と入力して判定しましょう。")
    return 0


def main(argv):
    if not argv:
        cmd_help()
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "mission":
        cmd_mission()
        return 0
    if cmd == "intro":
        cmd_intro()
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
