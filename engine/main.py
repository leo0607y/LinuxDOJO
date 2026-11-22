#!/usr/bin/env python3
"""LinuxDOJO メインメニュー・ダッシュボード・進行管理。"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import guided, runner, save, ui  # noqa: E402
from engine.ui import c, fmt, box  # noqa: E402

VERSION = "1.2.0"


def ask(prompt="> "):
    try:
        return input(c(prompt, "bold", "accent")).strip()
    except EOFError:
        return "q"


def pause(msg="Enter でメニューに戻る"):
    try:
        input(c(f"\n  {msg} ", "dim"))
    except EOFError:
        pass


def all_missions():
    return runner.load_curriculum()


def docker_mode_label():
    from engine import docker_backend
    return "本物の Docker" if docker_backend.detect_mode() == "real" else "シミュレーション"


# ------------------------------------------------------------------ header / title
def mode_name():
    return guided.MODE_NAMES[guided.selected_mode()]


def summary_lines(d=None):
    """メインメニュー用の 2 行サマリー（ランク・スコア・学習 XP）。"""
    d = d or save.load()
    mode = guided.selected_mode()
    if mode != "practice":
        step = guided.current_step(mode, d["learning"][mode])
        return [f"  {c('続き', 'dim')}  {step['title']}",
                "  " + c("ヒント・解答は何度見ても減点なし。自分のペースで進めましょう。", "dim"),
                "  " + c(ui.clip(save.activity_line(d), ui.term_width() - 6), "dim")]
    n = len([m for m in all_missions() if m.id in d["cleared"]])
    rank = save.rank_of(n)
    nxt = save.next_rank(n)
    tail = c(f"次の {nxt[1]} まであと {nxt[0] - n} 問", "dim") if nxt else c("全ミッション制覇", "bold")
    return [f"  {c('ランク', 'dim')}  {c(rank[1], 'bold', 'accent')} {rank[2]}   {tail}",
            f"  {c('スコア', 'dim')}  {c(save.total_score(d), 'bold')} pt   "
            f"{c('称号', 'dim')} {len(d['titles'])}/{len(save.STAGE_TITLES)}",
            "  " + c(ui.clip(save.activity_line(d), ui.term_width() - 6), "dim")]


def page_size(reserved):
    """端末の高さに収まる 1 ページの行数（最小 5）。"""
    return max(5, ui.term_rows() - reserved)


def pager_line(page, pages):
    return c(f"ページ {page + 1}/{pages}", "dim") if pages > 1 else ""


def show_doc(title, lines, color="cyan", crumbs=()):
    """長い説明を、端末の高さに合わせてページ分割した枠で見せる（スクロールバックは消えるため）。"""
    inner = ui.term_width() - 6
    body = []
    for ln in lines:
        for seg in str(ln).split("\n"):
            body.extend(ui.wrap(seg, inner))
    size = page_size(9)
    pages = max(1, -(-len(body) // size))
    size = max(1, -(-len(body) // pages))  # ページ間で行数を均等にし、数行だけの最終ページを作らない
    chunks = [body[i:i + size] for i in range(0, len(body), size)] or [[]]
    for i, chunk in enumerate(chunks):
        ui.clear()
        print(header(*crumbs))
        print()
        ttl = title if len(chunks) == 1 else f"{title}  {i + 1}/{len(chunks)}"
        print(box(chunk, title=ttl, color=color))
        last = i == len(chunks) - 1
        print()
        print(ui.footer(("Enter", "戻る" if last else "次のページ")))
        try:
            input(c("\n  > ", "bold", "accent"))
        except EOFError:
            return


def stage_state(done, total, is_next):
    if total and done >= total:
        return c(ui.DONE, "green", "bold")
    return c(ui.NEXT, "bold", "accent") if is_next else c(ui.TODO, "dim")


def dashboard_pages(d):
    """ダッシュボードを、端末の高さに合わせて分けられる行のかたまりとして返す。"""
    ms = all_missions()
    n = len([m for m in ms if m.id in d["cleared"]])
    st = d["stats"]
    rank = save.rank_of(n)
    nxt = save.next_rank(n)
    perfect = len([v for v in d["cleared"].values() if v.get("hints", 0) == 0 and not v.get("answer")])
    key = lambda s: c(s, "dim")  # noqa: E731
    top = [ui.rule("サマリー"),
           f"  {key('クリア')}  {ui.progress_bar(n / len(ms), 20)}  {c(f'{n}/{len(ms)} 問', 'bold')}  ({int(100 * n / len(ms))}%)",
           f"  {key('スコア')}  {c(save.total_score(d), 'bold')} pt     {key('称号')}  {len(d['titles'])}/{len(save.STAGE_TITLES)}"
           f"     {key('ノーヒント')}  {perfect} 問",
           f"  {key('ランク')}  {c(rank[1], 'bold', 'accent')} {rank[2]}"
           + (c(f"   次の {nxt[1]} {nxt[2]} まであと {nxt[0] - n} 問", "dim") if nxt else c("   全ミッション制覇", "bold")),
           "", ui.rule("プレイ統計"),
           f"  {key('総プレイ時間')} {fmt_time(d['player'].get('play_seconds', 0))}   "
           f"{key('プレイ回数')} {d['player'].get('sessions', 0)}   {key('check')} {st.get('checks', 0)} 回",
           f"  {key('ヒント閲覧')} {st.get('hints', 0)} 回   {key('解答閲覧')} {st.get('answers', 0)} 回   "
           f"{key('リセット')} {st.get('resets', 0)} 回"]
    if d["titles"]:
        top += ["", ui.rule("称号"), "  " + c("  ".join(d["titles"][-6:]), "bold")]
    from engine import security_progress
    sec = security_progress.lines(d)
    secb = ["", ui.rule(sec[0])] + [c(x, "dim") if x.startswith("  ") and "Stage" not in x else x for x in sec[1:]]
    rows = []
    for s, (name, desc) in runner.STAGES.items():
        sm = runner.missions_of(s)
        done = [m for m in sm if m.id in d["cleared"]]
        sc = sum(d["cleared"][m.id]["score"] for m in done)
        mx = sum(m.points for m in sm)
        rows.append([name, ui.clip(desc, max(10, ui.term_width() - 62)),
                     ui.progress_bar(len(done) / max(1, len(sm)), 8) + f" {int(100 * len(done) / max(1, len(sm))):>3}%",
                     f"{len(done)}/{len(sm)}", f"{sc}/{mx}"])
    return top, secb, rows


def header(*crumbs):
    """全画面共通のコンパクトな見出し 2 行（製品名 › モード › 現在地 と進捗）。"""
    d = save.load()
    mode = guided.selected_mode()
    if mode != "practice":
        course = guided.lessons(mode)
        done = len(set(d["learning"][mode]["completed"]) & {step["id"] for step in course})
        right = f"{ui.progress_bar(done / len(course), 8)} {done}/{len(course)} レッスン"
    else:
        total = len(all_missions())
        n = len([m for m in all_missions() if m.id in d["cleared"]])
        right = f"{ui.progress_bar(n / total, 8)} {n}/{total} 問"
    return ui.header([mode_name(), *crumbs], right)


def title_screen():
    ui.clear()
    print()
    print(ui.title_art())
    print()
    print("  " + c("はじめの一文字から学ぶ Linux 教材", "bold") + c(f"    v{VERSION}", "dim"))
    print(c("  " + "─" * 40, "dim"))
    lines = ["Linux が初めてでも大丈夫。文字の入力から始められます。",
             "はじめて → 基礎 → 応用 → 達人 → 実践の 5 モード。進捗はモードごとに保存。",
             f"実践では本物の bash で {len(all_missions())} 問に挑戦"
             + ("" if runner.practice_supported() else "（Windows では WSL で利用）")]
    for line in lines:
        for part in ui.wrap(line, ui.term_width() - 4):
            print("  " + c(part, "dim"))
    try:
        input(c("\n  Enter キーでスタート ", "bold", "accent"))
    except EOFError:
        pass


# ------------------------------------------------------------------ play
def next_after(m):
    ms = all_missions()
    i = [x.id for x in ms].index(m.id)
    return ms[i + 1] if i + 1 < len(ms) else None


def first_uncleared():
    d = save.load()
    for m in all_missions():
        if m.id not in d["cleared"]:
            return m
    return None


def briefing_splash(m):
    ui.clear()
    st = runner.STAGES[m.stage]
    idx = [x.id for x in runner.missions_of(m.stage)].index(m.id) + 1
    print(header(f"{st[0]}", f"第 {idx} 問"))
    print()
    print("  " + c(f"MISSION {m.id}", "bold", "accent") + "  " + c(m.title, "bold"))
    print(c(f"  {st[1]}", "dim"))
    print()
    print(ui.status_line("info", "サンドボックスを準備しています…"))
    if m.docker:
        print(ui.status_line("info", f"Docker モード: {docker_mode_label()}"))
    sys.stdout.flush()


def play(m):
    d = save.load()
    d["player"]["sessions"] = d["player"].get("sessions", 0) + 1
    if not d["player"].get("created"):
        d["player"]["created"] = time.strftime("%Y-%m-%d %H:%M")
    save.store(d)
    while m:
        d = save.load()
        d["learning"]["practice"]["mission"] = m.id
        save.store(d)
        token = runner.new_token()
        briefing_splash(m)
        try:
            runner.prepare(m, token)
        except Exception as e:
            print("\n" + ui.status_line("ng", "ミッションの準備に失敗しました", f"{type(e).__name__}: {e}"))
            if m.docker:
                print(c("  Docker 関連のエラーの場合、設定メニューで Docker モードを「シミュレーション」にすると遊べます。", "dim"))
            runner.kill_session(token)
            pause()
            return
        ui.clear()
        t0 = time.time()
        try:
            intent = runner.launch_shell(m, token)
        except KeyboardInterrupt:
            intent = "menu"
        finally:
            runner.kill_session(token)
            d = save.load()
            d["player"]["play_seconds"] = d["player"].get("play_seconds", 0) + int(time.time() - t0)
            save.store(d)
        if intent == "next":
            nm = next_after(m)
            if nm is None:
                ending()
                return
            if nm.stage != m.stage:
                stage_clear_splash(m.stage, nm)
            m = nm
            continue
        return "menu"


def stage_clear_splash(stage, nm):
    ui.clear()
    d = save.load()
    ids = [m.id for m in runner.missions_of(stage)]
    done = len([i for i in ids if i in d["cleared"]])
    st = runner.STAGES[stage]
    nst = runner.STAGES[nm.stage]
    print(header("ステージ完了"))
    print()
    print(box([c(f"{ui.OK} {st[0]}「{st[1]}」を修了しました", "bold", "green"), "",
               f"達成率  {ui.progress_bar(done / len(ids), 20)}  {done}/{len(ids)}", "",
               c("次のステージ  ", "dim") + c(f"{nst[0]}「{nst[1]}」", "bold")],
              title="STAGE COMPLETE", color="ok"))
    pause("Enter で次のステージへ")


def ending():
    ui.clear()
    d = save.load()
    n = len(d["cleared"])
    print()
    art = ui.clear_art()
    if art:
        print(art + "\n")
    print(box([c("最後のミッションまで到達しました。お疲れさまでした。", "bold", "green"), "",
               f"クリア数  {n}/{len(all_missions())}     総スコア  {save.total_score(d)} pt",
               f"ランク    {' '.join(save.rank_of(n)[1:])}", "",
               c("未クリアの問題はステージ選択から再挑戦できます。", "dim"),
               c("ヒントなしの再クリアでスコアを伸ばせます。", "dim")], title="THANK YOU FOR PLAYING", color="ok"))
    pause()


# ------------------------------------------------------------------ screens
def stage_select():
    page = 0
    while True:
        ui.clear()
        d = save.load()
        print(header("ステージ選択"))
        stats = []
        for s, (name, desc) in runner.STAGES.items():
            ms = runner.missions_of(s)
            stats.append((s, name, desc, len([m for m in ms if m.id in d["cleared"]]), len(ms)))
        nxt = next((s for s, _, _, done, total in stats if done < total), None)
        size = page_size(11)
        pages = -(-len(stats) // size)
        page = max(0, min(page, pages - 1))
        w = ui.term_width() - 2
        desc_w = max(12, w - 44)
        print("\n  " + c("ステージを選んでください", "bold") + "   " + pager_line(page, pages))
        print()
        for s, name, desc, done, total in stats[page * size:(page + 1) * size]:
            key = "x" if s == runner.EXTRA else str(s)
            pct = int(100 * done / total) if total else 0
            print(f" {stage_state(done, total, s == nxt)} {ui.pad(c(f'[{key}]', 'bold', 'accent'), 5)}"
                  f"{ui.pad(name, 9)}{ui.pad(ui.clip(desc, desc_w), desc_w)}  "
                  f"{ui.progress_bar(done / total if total else 0, 8)} {pct:>3}%  {c(f'{done}/{total}', 'dim')}")
        print()
        keys = [("番号", "開く"), ("b", "戻る")]
        if pages > 1:
            keys.insert(1, ("n / p", "ページ送り"))
        print(ui.footer(*keys))
        print(ui.take_flash(), end="")
        k = ask("\n  > ").lower()
        if k in ("b", "q", ""):
            return
        if k == "n" and pages > 1:
            page = (page + 1) % pages
            continue
        if k == "p" and pages > 1:
            page = (page - 1) % pages
            continue
        s = runner.EXTRA if k == "x" else (int(k) if k.isdigit() else None)
        if s in runner.STAGES:
            if mission_select(s) == "menu":
                return "menu"
        else:
            ui.invalid_choice(k, "一覧の番号（x は Extra）か b")


def mission_select(stage):
    page = 0
    while True:
        ui.clear()
        d = save.load()
        name, desc = runner.STAGES[stage]
        print(header(name))
        ms = runner.missions_of(stage)
        nxt = next((m for m in ms if m.id not in d["cleared"]), None)
        done = len([m for m in ms if m.id in d["cleared"]])
        size = page_size(11)
        pages = -(-len(ms) // size)
        page = max(0, min(page, pages - 1))
        ttl_w = max(16, ui.term_width() - 2 - 34)
        print(f"\n  {c(desc, 'bold')}")
        print("  " + ui.progress_bar(done / len(ms) if ms else 0, 16) + f" {done}/{len(ms)}   " + pager_line(page, pages))
        print()
        for i, m in enumerate(ms, 1):
            if not page * size < i <= (page + 1) * size:
                continue
            cl = d["cleared"].get(m.id)
            mark = c(ui.DONE, "green", "bold") if cl else (c(ui.NEXT, "bold", "accent") if m is nxt else c(ui.TODO, "dim"))
            score = f"{cl['score']:>3}pt" if cl else c("  ---", "dim")
            dk = c(" Docker", "dim") if m.docker else ""
            print(f" {mark} {ui.pad(c(f'[{i}]', 'bold', 'accent'), 5)}{ui.pad(c(m.id, 'dim'), 6)}"
                  f"{ui.pad(ui.clip(m.title, ttl_w), ttl_w)} {score}{dk}")
        print()
        keys = [("番号", "開始"), ("Enter", "次の未クリアから"), ("b", "戻る")]
        if pages > 1:
            keys.insert(2, ("n / p", "ページ送り"))
        print(ui.footer(*keys))
        print(ui.take_flash(), end="")
        k = ask("\n  > ").lower()
        if k in ("b", "q"):
            return
        if k == "n" and pages > 1:
            page = (page + 1) % pages
            continue
        if k == "p" and pages > 1:
            page = (page - 1) % pages
            continue
        if k == "":
            todo = [m for m in ms if m.id not in d["cleared"]] or ms
            if play(todo[0]) == "menu":
                return "menu"
            continue
        if k.isdigit() and 1 <= int(k) <= len(ms):
            if play(ms[int(k) - 1]) == "menu":
                return "menu"
        else:
            ui.invalid_choice(k, f"1〜{len(ms)} の番号か b")


def fmt_time(sec):
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}時間{m:02d}分" if h else f"{m}分"


def dashboard():
    d = save.load()
    top, secb, rows = dashboard_pages(d)
    pages = []
    if ui.term_rows() >= len(top) + len(secb) + 7:
        pages.append(top + secb)
    else:
        pages += [top, [x for x in secb[1:]]]
    size = page_size(10)
    table = ui.table(["ステージ", "内容", "達成率", "クリア", "スコア"], rows).split("\n")
    head, body = table[:2], table[2:]
    for i in range(0, len(body), max(3, size - 2)):
        pages.append(["  " + x for x in head] + ["  " + x for x in body[i:i + max(3, size - 2)]])
    for i, lines in enumerate(pages):
        ui.clear()
        print(header("ダッシュボード"))
        print()
        for ln in lines:
            print("\n".join(ui.wrap(ln, ui.term_width() - 2)))
        print()
        suffix = "" if len(pages) == 1 else f"  ({i + 1}/{len(pages)})"
        print(ui.footer(("Enter", ("戻る" if i == len(pages) - 1 else "次のページ") + suffix)))
        try:
            input(c("\n  > ", "bold", "accent"))
        except EOFError:
            return


def tips_catalog():
    from curriculum.extra_tips import TIPS
    while True:
        ui.clear()
        print(header("小ネタ図鑑"))
        print("\n  " + c("現場で一目置かれる Linux 時短テクニック", "bold") + "\n")
        size = page_size(10)
        for i, t in enumerate(TIPS[:size], 1):
            print(ui.menu_row(i, t["title"], key_w=4))
        print()
        print(ui.footer(("番号", "読む"), ("p", "ミニ課題 5 問に挑戦"), ("b", "戻る")))
        print(ui.take_flash(), end="")
        k = ask("\n  > ").lower()
        if k in ("b", "q", ""):
            return
        if k == "p":
            if mission_select(runner.EXTRA) == "menu":
                return
            continue
        if k.isdigit() and 1 <= int(k) <= len(TIPS):
            show_tip(int(k) - 1, TIPS)
        else:
            ui.invalid_choice(k, f"1〜{len(TIPS)} の番号か p・b")


def show_tip(i, tips):
    while True:
        t = tips[i]
        ui.clear()
        lines = [fmt(x) for x in t["body"].strip().split("\n")]
        lines += ["", c("試してみよう（ゲーム内シェルや普段のターミナルで）", "bold")]
        lines += ["  " + c(x, "accent") for x in t["example"].split("\n")]
        title = f"小ネタ {i + 1}/{len(tips)}  {t['title']}"
        wrapped = sum(len(ui.wrap(seg, ui.term_width() - 6)) for ln in lines for seg in ln.split("\n"))
        if wrapped > page_size(9):
            show_doc(title, lines, crumbs=("小ネタ図鑑",))  # 画面に収まらないときはページ分割
            print(ui.footer(("n", "次の小ネタ"), ("p", "前の小ネタ"), ("Enter / b", "一覧へ戻る")))
        else:
            print(header("小ネタ図鑑"))
            print()
            print(box(lines, title=title))
            print()
            print(ui.footer(("n", "次へ"), ("p", "前へ"), ("Enter / b", "一覧へ戻る")))
        k = ask("\n  > ").lower()
        if k == "n":
            i = (i + 1) % len(tips)
        elif k == "p":
            i = (i - 1) % len(tips)
        else:
            return


def how_to_play():
    if guided.selected_mode() != "practice":
        show_doc("初めての遊び方", [
            "まず [1] 続きから を選び、表示された説明を読みましょう。",
            "入力待ちの $ は入力しません。その後ろにコマンドを書いて Enter を押します。",
            "英数字と記号・スペースは半角で入力します。大文字と小文字は区別されます。",
            "Backspace で消して入力し直せます。急がず 1 つずつ試しましょう。", "",
            c("画面内で使うコマンド", "bold"),
            "  " + c("hint", "accent") + "    入力例を表示          " + c("lesson", "accent") + "  説明を再表示",
            "  " + c("reset", "accent") + "   課題を復元            " + c("menu", "accent") + "    保存してメニューへ", "",
            "はじめて・基礎練習は模擬ターミナル。sudo や apt も実際の PC を変更しません。",
            "ヒントや解答を見ても減点はありません。繰り返し練習しましょう。",
            "[2] で復習するレッスンを選択、[7] でモードを切り替えられます。"], crumbs=("遊び方",))
        return
    cmd = lambda name, text: "  " + c(ui.pad(name, 15), "accent") + text  # noqa: E731
    lines = [
        c("1. ミッションを選ぶ", "bold"),
        "   専用のサブシェル（本物の bash）が起動します。プロンプトは次のような表示です。",
        "   " + c("LQ 1-1", "bold", "accent") + " " + c("workspace/stage_01", "dim") + c(" $", "bold", "accent"),
        "   ls / cd / grep / パイプ / リダイレクト / Tab 補完 / Ctrl+R が普段どおり使えます。", "",
        c("2. 達成条件を満たす", "bold"),
        "   問題文の「達成条件」を満たすように実際にコマンドを実行します。判定エンジンが、ファイルの中身・パーミッション・リンク・プロセス・環境変数・履歴などの実際の状態を検査します。", "",
        c("3. ゲーム内コマンド（サブシェル内でいつでも使えます）", "bold"),
        cmd("mission", "問題文・達成条件を再表示"),
        cmd("hint", "段階的ヒント（1:考え方 → 2:使うコマンド → 3:具体例）"),
        cmd("answer", "模範解答と徹底解説（スコア半減）"),
        cmd("check", "達成判定。クリアなら解説を表示して次の問題へ"),
        cmd("submit <答え>", "調べた値（合言葉・ポート番号など）を提出"),
        cmd("reset_mission", "サンドボックスを初期状態に戻す（壊しても安心）"),
        cmd("skip", "次の問題へ飛ばす"),
        cmd("menu", "メインメニューへ戻る（exit / Ctrl+D でも可）"), "",
        c("4. スコアとランク", "bold"),
        "   1 問 100pt。ヒント 1 段階ごとに -10pt、解答閲覧で半分。クリア数に応じてランクが上がり、ステージを全問クリアすると称号が手に入ります。進捗は save_data.json に自動保存されます。", "",
        c(f"{ui.WARN} 注意", "bold", "yellow"),
        "   サブシェルは本物の bash です。作業は workspace/ の中で行いましょう（外に出るとプロンプトが赤くなります）。",
        f"   Stage 5 の Docker は現在「{docker_mode_label()}」モードです（設定メニューで変更可）。",
    ]
    show_doc("遊び方", lines, crumbs=("遊び方",))


def settings():
    if guided.selected_mode() != "practice":
        ui.clear()
        print(header("設定"))
        print()
        print(box(["進み具合は自動で保存されます。終了するだけで保存できます。",
                   "モードを切り替えるときはメインメニューの [7] を選びます。",
                   "[r] は全モードの進捗と実践のクリア実績を消します。復習するだけなら [2] を使いましょう。"],
                  title="初心者モードの設定"))
        print()
        print(ui.footer(("r", "全進捗の初期化"), ("Enter", "戻る")))
        value = ask("\n  > ").lower()
        if value == "r" and ask("  全モードの進捗を消す場合だけ yes と入力 > ") == "yes":
            d = save.empty()
            d["settings"] = save.load()["settings"]
            save.store(d)
            print(ui.status_line("ok", "進捗を初期化しました。はじめてモードから学び直せます。"))
            pause()
        elif value == "r":
            ui.flash("初期化は行いませんでした（消す場合だけ yes と入力します）。")
        return
    from engine import docker_backend
    while True:
        ui.clear()
        d = save.load()
        cur = d["settings"].get("docker_mode", "auto")
        print(header("設定"))
        real_ok = docker_backend.real_available()
        print("\n  " + c("Docker", "bold"))
        print(f"    {c('デーモン', 'dim')}  " + (c("利用可能", "green") if real_ok else c("利用不可（未インストール or 権限なし）", "yellow")))
        print(f"    {c('設定', 'dim')}      {c(cur, 'bold', 'accent')}   {c('実際の動作', 'dim')}  {c(docker_mode_label(), 'bold')}")
        print()
        for key, label, desc, mark in (("1", "auto", "使えれば本物、ダメならシミュレーション", cur == "auto"),
                                       ("2", "mock", "常にシミュレーション。実環境を汚さない", cur == "mock"),
                                       ("3", "real", "本物の Docker を使う", cur == "real")):
            print(ui.menu_row(key, label, desc, label_w=8, strong=mark, tag="現在" if mark else "", tag_w=4))
        print()
        print(ui.menu_row("r", "初期化", "セーブデータをすべて消す", label_w=8, tag_w=4))
        print()
        print(ui.footer(("1 / 2 / 3", "Docker モード"), ("r", "初期化"), ("b", "戻る")))
        print(ui.take_flash(), end="")
        k = ask("\n  > ").lower()
        if k in ("b", "q", ""):
            return
        if k not in ("1", "2", "3", "r"):
            ui.invalid_choice(k, "1・2・3・r・b")
        if k in ("1", "2", "3"):
            d["settings"]["docker_mode"] = {"1": "auto", "2": "mock", "3": "real"}[k]
            save.store(d)
            ui.flash(f"{ui.OK} Docker モードを {d['settings']['docker_mode']} にしました。")
            docker_backend._MODE = None
            os.environ.pop("LQ_DOCKER_MODE", None)
            if k == "3" and not real_ok:
                print(ui.status_line("warn", "Docker デーモンが使えないため、実際にはシミュレーションモードで動作します。"))
                pause("Enter で設定へ戻る")
        if k == "r":
            yn = ask(c("  本当に全ての進捗を消去しますか？ 消去するなら yes と入力 > ", "red"))
            if yn == "yes":
                s = save.empty()
                s["settings"] = d["settings"]
                save.store(s)
                print(ui.status_line("ok", "セーブデータを初期化しました。"))
                pause("Enter で設定へ戻る")
            else:
                ui.flash("初期化は行いませんでした（消す場合だけ yes と入力します）。")


def practice_resume():
    d = save.load()
    mission_id = d["learning"]["practice"].get("mission")
    if mission_id and mission_id not in d["cleared"]:
        for mission in all_missions():
            if mission.id == mission_id:
                return mission
    return first_uncleared()


def mode_select():
    modes = (("1", "intro", "はじめて", "おすすめ。文字入力の第一歩から",
              "コマンドの意味を 1 つずつ説明して練習"),
             ("2", "basic", "基礎練習", "ファイル操作・検索・権限・vim を反復",
              "入力例は hint でいつでも表示。減点なし"),
             ("3", "advanced", "応用練習", "ワイルドカード・パイプ・集計・プロセス",
              "コマンドを組み合わせて結果を自分で作る"),
             ("4", "expert", "達人", "アーカイブ・通信・Git・スクリプト・サービス",
              "答えは非表示。hint を使って自力で解く"),
             ("5", "practice", "実践", f"本物の bash で {len(all_missions())} 問。運用から監査まで",
              "コマンドが実際に動く（sudo / apt の模擬は前 2 モード）"))
    while True:
        ui.clear()
        d = save.load()
        current = d["learning"].get("mode")
        print(header("モード選択"))
        print("\n  " + c(ui.clip("どこから学ぶか選べます。いつでも変更でき、進捗はモードごとに保存されます。", ui.term_width() - 6), "dim") + "\n")
        for key, mid, label, desc, more in modes:
            now = mid == current
            print(ui.menu_row(key, label, desc, label_w=8, strong=now, tag="現在" if now else "", tag_w=4))
            print(" " * 22 + c(ui.clip(more, ui.term_width() - 26), "dim"))
        print()
        print(ui.footer(("1〜5", "モードを選ぶ"), ("b", "戻る")))
        print(ui.take_flash(), end="")
        value = ask("\n  > ").lower()
        if value in ("b", "q", ""):
            return
        if value == "5" and not runner.practice_supported():
            windows_practice_notice()
            continue
        if value in ("1", "2", "3", "4", "5"):
            d["learning"]["mode"] = {"1": "intro", "2": "basic", "3": "advanced", "4": "expert", "5": "practice"}[value]
            save.store(d)
            return
        ui.invalid_choice(value, "1〜5 か b")


def windows_practice_notice():
    ui.clear()
    print(header("実践モードを使うには"))
    print()
    print(box(["実践モードは本物の Linux（bash）でコマンドを動かすため、WSL が必要です。",
               "はじめて・基礎練習モードは、このまま Windows で学べます。",
               "",
               c("WSL を使う手順（1 回だけ）", "bold"),
               "  1. PowerShell を「管理者として実行」で開く",
               "  2. wsl --install と入力して Enter、終わったら PC を再起動",
               "  3. Ubuntu の初期設定（ユーザー名とパスワード）を済ませる",
               "  4. Ubuntu で sudo apt install python3 を実行する",
               "  5. もう一度 start.bat をダブルクリック（自動で WSL 版が起動します）",
               "",
               c("進み具合は Windows 版と WSL 版で共通です。", "dim")], title="WSL が必要です", color="warn"))
    pause("Enter で戻る")


def command_dictionary():
    show_doc("はじめての用語・コマンド辞典", [
        "ターミナル: 文字でコンピューターへ指示を出す画面。",
        "コマンド: 指示する道具の名前。Enter で実行します。",
        "引数: コマンドに渡す対象。cat note.txt の note.txt が対象ファイルです。",
        "オプション: 動作を変える指定。ls -a の -a は隠しファイルも表示します。",
        "フォルダ（ディレクトリ）: ファイルをまとめる場所。パスはその住所です。",
        "pwd: 今いる場所を表示 / ls: 名前一覧 / cd: フォルダ移動",
        "cat: 内容を読む / echo: 文字を表示 / touch: 空ファイル作成",
        "mkdir: フォルダ作成 / cp: コピー / mv: 移動・名前変更 / rm: 削除",
        ">: 出力でファイルを上書き / >>: 末尾に追加（実践では本当に書き換わります）",
        "grep: 一致する行を探す / wc -l: 行数 / chmod: 読む・書く・実行の権限を変える",
        "sudo: 後ろのコマンドを管理者の権限で動かす。普段は必要な場合だけ使います。",
        "インストール: ソフトを使えるように追加すること。削除はアンインストール。",
        "apt: Ubuntu/Debian のソフト管理の道具。他の Linux では別の道具を使うこともあります。",
        "apt update: ソフトの一覧更新 / apt install tree: tree というソフトを追加",
        "install はここでは apt のサブコマンド（具体的な操作の指定）です。",
        "update と upgrade（導入済みソフトの更新）は別操作です。",
        "vim: ターミナルで使うテキストエディタ。i で入力モード、Esc で戻る、:wq で保存して終了、:q! で保存せず終了。",
        "模擬モードは説明した一部の書式を練習する環境。本物の bash の全機能は使えません。"], crumbs=("用語・コマンド辞典",))


def learning_dashboard(mode):
    ui.clear()
    print(header("ダッシュボード"))
    print()
    print(ui.rule("モードごとの進み具合"))
    d = save.load()
    for key in guided.GUIDED_MODES:
        course = guided.lessons(key)
        done = len(set(d["learning"][key]["completed"]) & {s["id"] for s in course})
        print(f"  {ui.pad(guided.MODE_NAMES[key], 16)}{ui.progress_bar(done / len(course), 16)}  {done}/{len(course)} レッスン")
    done = len([m for m in all_missions() if m.id in d["cleared"]])
    print(f"  {ui.pad(guided.MODE_NAMES['practice'], 16)}{ui.progress_bar(done / len(all_missions()), 16)}  {done}/{len(all_missions())} 問")
    from engine import readiness
    mastery = readiness.mastery_lines(d)
    print("\n" + ui.rule("Linux 自由自在度"))
    print("  " + mastery[0])
    print(c("  " + ui.clip(mastery[-2].strip().split("（")[0], ui.term_width() - 6), "dim"))
    print()
    print(ui.footer(("Enter", "戻る"), ("d", "分野別の習熟度を見る")))
    if ask("\n  > ").lower() == "d":
        show_doc("分野別の習熟度", mastery[1:-2], crumbs=("ダッシュボード",))


def main_menu():
    while True:
        ui.clear()
        print(header())
        mode = guided.selected_mode()
        nxt = practice_resume() if mode == "practice" else None
        cont = (nxt.id + "  " + nxt.title) if nxt else "全問クリア済み"
        if mode != "practice":
            step = guided.current_step(mode)
            cont = step["title"]
            if guided.completed_course(mode) and not guided.progress_for(mode).get("reviewing"):
                cont = "このモードは学習完了。次のモードを選べます"
        items = [("1", "続きから", cont), ("2", "ステージ選択", f"全 {len(runner.STAGES) - 1} ステージ + Extra"),
                 ("3", "進捗ダッシュボード", "ランク・スコア・統計"),
                 ("4", "小ネタ図鑑", "現場で使える時短テクニック"),
                 ("5", "遊び方", "操作とゲーム内コマンドの一覧"),
                 ("6", "設定", "Docker モード・セーブ初期化"),
                 ("7", "モード選択", "はじめて / 基礎 / 応用 / 達人 / 実践"),
                 ("8", "課題まつり", "総合復習・自由自在マップ"),
                 ("9", "Linux 常用コース", "目的検索・本物のツール実習"), ("q", "終了", "進捗は自動保存")]
        if mode != "practice":
            beginner = {"2": ("レッスン選択", "好きなレッスンを選んで復習"), "4": ("用語・コマンド辞典", "はじめて出会う言葉の説明"),
                        "6": ("設定", "進捗の初期化")}
            items = [(key, *beginner.get(key, (label, desc))) for key, label, desc in items]
        print()
        for line in summary_lines():
            print(line)
        print()
        for k, label, desc in items:
            print(ui.menu_row(k, label, desc, label_w=20, strong=(k == "1")))
        print()
        print(ui.footer(("番号", "選択"), ("Enter", "= [1] 続きから"), ("q", "終了")))
        print(ui.take_flash(), end="")
        k = ask("\n  > ").lower()
        if k in ("1", ""):
            if mode != "practice":
                if guided.completed_course(mode) and not guided.progress_for(mode).get("reviewing"):
                    mode_select()
                else:
                    guided.play(mode)
            elif nxt:
                play(nxt)
            else:
                stage_select()
        elif k == "2":
            if mode == "practice":
                stage_select()
            else:
                guided.lesson_select(mode)
        elif k == "3":
            if mode == "practice":
                dashboard()
            else:
                learning_dashboard(mode)
        elif k == "4":
            if mode == "practice":
                tips_catalog()
            else:
                command_dictionary()
        elif k == "5":
            how_to_play()
        elif k == "6":
            settings()
        elif k == "7":
            mode_select()
        elif k == "8":
            from engine import readiness
            readiness.run()
        elif k == "9":
            from engine import toolbox
            toolbox.menu()
        elif k in ("q", "quit", "exit"):
            goodbye(mode)
            return
        else:
            ui.invalid_choice(k, "1〜9 か q")


def goodbye(mode):
    """終了時の一画面。進捗が保存済みであること、次回の再開方法だけを短く伝える。"""
    ui.clear()
    d = save.load()
    print()
    print(ui.header(["またね"], ""))
    print("\n  " + c("今日の学びが、明日のトラブル対応を救う。", "bold"))
    print()
    if mode != "practice":
        print("  学習の続きは保存済みです。次回も [1] 続きから で再開できます。")
    else:
        n = len(d["cleared"])
        print(f"  {c('ランク', 'dim')}  {' '.join(save.rank_of(n)[1:])}    {c('総スコア', 'dim')}  {save.total_score(d)} pt")
        print("  進捗は自動で保存済みです。次回は ./start.sh（または start）で再開できます。")
    print()


def setup_windows_console():
    """Windows のコンソールで日本語と色を表示できるようにする。"""
    if os.name != "nt":
        return
    os.system("")  # 仮想端末シーケンス（ANSI カラー）を有効にする
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    setup_windows_console()
    if not sys.stdin.isatty():
        print("LinuxDOJO は対話型のゲームです。ターミナルから ./start.sh で起動してください。")
        return 1
    runner.WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        title_screen()
    except KeyboardInterrupt:
        return 0
    while True:
        try:
            main_menu()
            return 0
        except KeyboardInterrupt:
            print("\n\n" + ui.status_line("info", "中断しました。進捗は保存されています。またね。") + "\n")
            return 0
        except Exception:
            import traceback
            log = runner.WORKSPACE / "error.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n") + traceback.format_exc() + "\n")
            print("\n" + ui.status_line("ng", "予期せぬエラーが発生しました。メニューに戻ります。", f"詳細: {log}"))
            pause("Enter で続ける")


if __name__ == "__main__":
    sys.exit(main())
