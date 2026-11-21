#!/usr/bin/env python3
"""LinuxQuest メインメニュー・ダッシュボード・進行管理。"""
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
        return input(c(prompt, "bold", "bwhite")).strip()
    except EOFError:
        return "q"


def pause(msg="Enter でメニューに戻る"):
    try:
        input(c(f"\n  {msg} ", "gray"))
    except EOFError:
        pass


def all_missions():
    return runner.load_curriculum()


def docker_mode_label():
    from engine import docker_backend
    return "本物の Docker" if docker_backend.detect_mode() == "real" else "シミュレーション"


# ------------------------------------------------------------------ header / title
def header():
    d = save.load()
    mode = guided.selected_mode()
    if mode != "practice":
        course = guided.lessons(mode)
        progress = d["learning"][mode]
        completed = set(progress["completed"]) & {step["id"] for step in course}
        step = guided.current_step(mode, progress)
        return box([save.activity_line(d), "", f"学習モード: {guided.MODE_NAMES[mode]}",
                    f"進み具合 {ui.progress_bar(len(completed) / len(course), 20)} {len(completed)}/{len(course)} レッスン",
                    f"続き: {step['title']}", "ヒント・解答は何度見ても減点なし。自分のペースで進めましょう。"], color="green")
    ms = all_missions()
    n = len([m for m in ms if m.id in d["cleared"]])
    rank = save.rank_of(n)
    nxt = save.next_rank(n)
    lines = [save.activity_line(d), "",
        f"{c('ランク', 'gray')} {c(rank[1], 'bold', 'byellow')} {c(rank[2], 'bold', 'bwhite')}"
        + (c(f"   次の {nxt[1]} {nxt[2]} まであと {nxt[0] - n} 問", "gray") if nxt else c("   全ミッション制覇！", "bmagenta")),
        f"{c('進捗  ', 'gray')} {ui.progress_bar(n / len(ms), 20)} {c(f'{n}/{len(ms)} 問', 'bold')}  "
        f"{c('総スコア', 'gray')} {c(save.total_score(d), 'bold', 'bgreen')} pt  "
        f"{c('称号', 'gray')} {len(d['titles'])}/{len(save.STAGE_TITLES)}",
    ]
    return box(lines, color="blue")


def title_screen():
    ui.clear()
    print(ui.title_art())
    print(c("        〜 はじめの一文字から学ぶ Linux 教材 〜", "bold", "bwhite"))
    print(c(f"                                                     v{VERSION}", "gray"))
    peng = ui.PENGUIN.strip("\n").split("\n")
    talk = ["", "  Linux が初めてでも大丈夫。文字の入力から始めよう。",
            "  はじめて → 基礎 → 応用 → 達人 → 実践の5モード。",
            "  モードごとに保存して、次回は続きから学べます。",
            "", f"  実践では本物の bash で {len(all_missions())} 問に挑戦！"
            + ("" if runner.practice_supported() else "（Windows では WSL で利用）"), ""]
    for i in range(max(len(peng), len(talk))):
        left = peng[i] if i < len(peng) else ""
        right = talk[i] if i < len(talk) else ""
        print(c(ui.pad(left, 20), "bwhite") + c(right, "bcyan"))
    try:
        input(c("\n                    ▶ Enter キーでスタート", "bold", "blink", "byellow"))
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
    print()
    print(c(f"  {st[2]}  {st[0]}「{st[1]}」", "bold", "bcyan"))
    print(c(f"  MISSION {m.id}  {m.title}", "bold", "bmagenta"))
    print(ui.hr())
    print(c("  ⏳ サンドボックスを準備しています…", "gray"))
    if m.docker:
        print(c(f"  🐳 Docker モード: {docker_mode_label()}", "gray"))
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
            print(c(f"\n  ❌ ミッションの準備に失敗しました: {type(e).__name__}: {e}", "bred"))
            if m.docker:
                print(c("  Docker 関連のエラーの場合、設定メニューで Docker モードを「シミュレーション」にすると遊べます。", "yellow"))
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
    print()
    print(box([c(f"{st[2]} {st[0]}「{st[1]}」", "bold", "bwhite"),
               f"達成率 {ui.progress_bar(done / len(ids), 16)} {done}/{len(ids)}",
               "", c(f"次は {nst[2]} {nst[0]}「{nst[1]}」へ進みます！", "bold", "bcyan")],
              title="STAGE COMPLETE", color="yellow", title_color="byellow"))
    pause("Enter で次のステージへ")


def ending():
    ui.clear()
    d = save.load()
    n = len(d["cleared"])
    print(ui.clear_art())
    print(box([c("最後のミッションまで到達しました！ お疲れさまでした！", "bold", "bgreen"), "",
               f"クリア数: {n}/{len(all_missions())}   総スコア: {save.total_score(d)} pt",
               f"ランク: {' '.join(save.rank_of(n)[1:])}", "",
               "未クリアの問題はステージ選択から再挑戦できます。",
               "ヒントなしでの再クリアでスコアを伸ばしてみよう！"], title="THANK YOU FOR PLAYING", color="magenta"))
    pause()


# ------------------------------------------------------------------ screens
def stage_select():
    while True:
        ui.clear()
        print(header())
        d = save.load()
        print(c("\n  🗺  ステージ選択\n", "bold", "bwhite"))
        for s, (name, desc, icon) in runner.STAGES.items():
            ms = runner.missions_of(s)
            done = len([m for m in ms if m.id in d["cleared"]])
            key = "x" if s == runner.EXTRA else str(s)
            pct = int(100 * done / len(ms)) if ms else 0
            print(f"   {c(f'[{key}]', 'bold', 'bcyan')} {icon} {ui.pad(name, 8)} {ui.pad(desc, 44)} "
                  f"{ui.progress_bar(done / len(ms), 8)} {pct:>3}%  {c(f'{done}/{len(ms)}', 'gray')}")
        print(c("\n   [b] 戻る", "gray"))
        k = ask("\n  ステージ番号 > ").lower()
        if k in ("b", "q", ""):
            return
        s = runner.EXTRA if k == "x" else (int(k) if k.isdigit() else None)
        if s in runner.STAGES:
            if mission_select(s) == "menu":
                return "menu"


def mission_select(stage):
    while True:
        ui.clear()
        print(header())
        d = save.load()
        name, desc, icon = runner.STAGES[stage]
        print(c(f"\n  {icon} {name}「{desc}」\n", "bold", "bwhite"))
        ms = runner.missions_of(stage)
        for i, m in enumerate(ms, 1):
            cl = d["cleared"].get(m.id)
            mark = c("✔", "bold", "bgreen") if cl else c("○", "gray")
            score = c(f"{cl['score']:>3}pt", "byellow") if cl else c("  ---", "gray")
            dk = " 🐳" if m.docker else ""
            print(f"   {c(f'[{i}]', 'bold', 'bcyan')} {mark} {c(m.id, 'gray'):<6} {ui.pad(m.title, 50)} {score}{dk}")
        print(c("\n   [b] 戻る   （Enter のみで、この中の最初の未クリア問題から開始）", "gray"))
        k = ask("\n  問題番号 > ").lower()
        if k in ("b", "q"):
            return
        if k == "":
            todo = [m for m in ms if m.id not in d["cleared"]] or ms
            if play(todo[0]) == "menu":
                return "menu"
            continue
        if k.isdigit() and 1 <= int(k) <= len(ms):
            if play(ms[int(k) - 1]) == "menu":
                return "menu"


def fmt_time(sec):
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}時間{m:02d}分" if h else f"{m}分"


def dashboard():
    ui.clear()
    print(header())
    d = save.load()
    print(c("\n  📊 進捗ダッシュボード\n", "bold", "bwhite"))
    rows = []
    for s, (name, desc, icon) in runner.STAGES.items():
        ms = runner.missions_of(s)
        done = [m for m in ms if m.id in d["cleared"]]
        sc = sum(d["cleared"][m.id]["score"] for m in done)
        mx = sum(m.points for m in ms)
        rows.append([f"{icon} {name}", desc, ui.progress_bar(len(done) / len(ms), 10) + f" {int(100 * len(done) / len(ms)):>3}%",
                     f"{len(done)}/{len(ms)}", f"{sc}/{mx}"])
    print(ui.table(["ステージ", "内容", "達成率", "クリア", "スコア"], rows))
    st = d["stats"]
    n = len(d["cleared"])
    print(c("\n  🎖  ランク", "bold", "bwhite"))
    for th, lv, nm in save.rank_table():
        cur = save.rank_of(n)[1] == lv
        mark = c("▶", "byellow", "bold") if cur else (c("✔", "bgreen") if n >= th else c("・", "gray"))
        print(f"    {mark} {c(lv, 'bold' if cur else 'gray'):<8} {c(nm, 'byellow' if cur else ('white' if n >= th else 'gray'))}"
              + c(f"  ({th}問クリア)", "gray"))
    print(c("\n  🏅 称号", "bold", "bwhite"))
    if d["titles"]:
        for t in d["titles"]:
            print("    " + c(t, "bmagenta"))
    else:
        print(c("    （ステージを全問クリアすると称号が手に入ります）", "gray"))
    from engine import security_progress
    print("\n" + "\n".join(security_progress.lines(d)))
    perfect = len([v for v in d["cleared"].values() if v.get("hints", 0) == 0 and not v.get("answer")])
    print(c("\n  📈 プレイ統計", "bold", "bwhite"))
    print(f"    総プレイ時間 {c(fmt_time(d['player'].get('play_seconds', 0)), 'bcyan')}   "
          f"プレイ回数 {c(d['player'].get('sessions', 0), 'bcyan')}   "
          f"ノーヒントクリア {c(perfect, 'bcyan')} 問")
    print(f"    check 実行 {c(st.get('checks', 0), 'bcyan')} 回   ヒント閲覧 {c(st.get('hints', 0), 'bcyan')} 回   "
          f"解答閲覧 {c(st.get('answers', 0), 'bcyan')} 回   リセット {c(st.get('resets', 0), 'bcyan')} 回")
    pause()


def tips_catalog():
    from curriculum.extra_tips import TIPS
    while True:
        ui.clear()
        print(c("\n  📖 小ネタ図鑑 ― 現場で一目置かれる Linux 時短テクニック 10選\n", "bold", "bwhite"))
        for i, t in enumerate(TIPS, 1):
            print(f"   {c(f'[{i:>2}]', 'bold', 'bcyan')} {t['title']}")
        print(c("\n   [p] 実践モード（ミニ課題5問）に挑戦   [b] 戻る", "gray"))
        k = ask("\n  番号 > ").lower()
        if k in ("b", "q", ""):
            return
        if k == "p":
            if mission_select(runner.EXTRA) == "menu":
                return
            continue
        if k.isdigit() and 1 <= int(k) <= len(TIPS):
            show_tip(int(k) - 1, TIPS)


def show_tip(i, tips):
    while True:
        t = tips[i]
        ui.clear()
        lines = [fmt(x) for x in t["body"].strip().split("\n")]
        lines += ["", c("▼ 試してみよう（ゲーム内シェルや普段のターミナルで）", "bold", "bgreen")]
        lines += ["  " + c(x, "bcyan") for x in t["example"].split("\n")]
        print()
        print(box(lines, title=f"小ネタ {i + 1}/{len(tips)}  {t['title']}", color="cyan", title_color="bcyan"))
        k = ask("\n  [n] 次へ  [p] 前へ  [b] 一覧へ > ").lower()
        if k == "n":
            i = (i + 1) % len(tips)
        elif k == "p":
            i = (i - 1) % len(tips)
        else:
            return


def how_to_play():
    if guided.selected_mode() != "practice":
        ui.clear()
        print(box(["まず [1] 続きから を選び、表示された説明を読みましょう。",
                   "入力待ちの $ は入力しません。その後ろにコマンドを書いて Enter を押します。",
                   "英数字と記号・スペースは半角で入力します。大文字と小文字は区別されます。",
                   "Backspace で消して入力し直せます。急がず1つずつ試しましょう。",
                   "hint: 入力例を表示 / lesson: 説明を再表示 / reset: 課題を復元",
                   "menu: 保存してメニューへ。途中でやめても現在の課題から再開できます。",
                   "はじめて・基礎練習は模擬ターミナル。sudo や apt も実際の PC を変更しません。",
                   "ヒントや解答を見ても減点はありません。繰り返し練習しましょう。",
                   "[2] で復習するレッスンを選択、[7] でモードを切り替えられます。"], title="初めての遊び方", color="green"))
        pause()
        return
    ui.clear()
    lines = [
        c("① ミッションを選ぶと、専用のサブシェル（本物の bash）が起動します。", "bold"),
        "   プロンプトは " + c(" LQ 1-1 ", "bold", "bwhite", "on_magenta") + " " + c("workspace/stage_01", "bblue") + c(" $", "bgreen") + " のような表示です。",
        "   ここでは普段どおり ls / cd / grep / パイプ / リダイレクト / Tab 補完 / Ctrl+R が使えます。",
        "",
        c("② 問題文の「達成条件」を満たすように、実際にコマンドを実行してください。", "bold"),
        "   判定エンジンが、ファイルの中身・パーミッション・リンク・プロセス・環境変数・",
        "   コマンド履歴・終了コードなどの「実際の状態」を検査します。",
        "",
        c("③ ゲーム内コマンド（サブシェル内でいつでも使えます）", "bold"),
        "   " + c("mission", "bcyan") + "        問題文・達成条件を再表示",
        "   " + c("hint", "bcyan") + "           段階的ヒント（1:考え方 → 2:使うコマンド → 3:具体例）",
        "   " + c("answer", "bcyan") + "         模範解答と徹底解説（スコア半減）",
        "   " + c("check", "bcyan") + "          達成判定。クリアなら解説を表示して次の問題へ",
        "   " + c("submit <答え>", "bcyan") + "  調べた値（合言葉・ポート番号など）を提出",
        "   " + c("reset_mission", "bcyan") + "  サンドボックスを初期状態に戻す（壊しても安心）",
        "   " + c("skip", "bcyan") + "           次の問題へ飛ばす",
        "   " + c("menu", "bcyan") + "           メインメニューへ戻る（exit / Ctrl+D でも可）",
        "",
        c("④ スコアとランク", "bold"),
        "   1問 100pt。ヒント1段階ごとに -10pt、解答閲覧で半分。クリア数に応じてランクが上がり、",
        "   ステージを全問クリアすると称号が手に入ります。進捗は save_data.json に自動保存されます。",
        "",
        c("⚠ 注意", "bold", "byellow"),
        "   サブシェルは本物の bash です。作業は workspace/ の中で行いましょう（外に出るとプロンプトが赤くなります）。",
        f"   Stage 5 の Docker は現在「{docker_mode_label()}」モードです（設定メニューで変更可）。",
    ]
    print()
    print(box(lines, title="❓ 遊び方", color="green", title_color="bgreen"))
    pause()


def settings():
    if guided.selected_mode() != "practice":
        ui.clear()
        print(box(["進み具合は自動で保存されます。終了するだけで保存できます。",
                   "モードを切り替えるときはメインメニューの [7] を選びます。",
                   "[r] は全モードの進捗と実践のクリア実績を消します。復習するだけなら [2] を使いましょう。"], title="初心者モードの設定", color="green"))
        value = ask("  [r] 全進捗の初期化 / Enter: 戻る > ").lower()
        if value == "r" and ask("  全モードの進捗を消す場合だけ yes と入力 > ") == "yes":
            d = save.empty()
            d["settings"] = save.load()["settings"]
            save.store(d)
            print("進捗を初期化しました。はじめてモードから学び直せます。")
            pause()
        return
    from engine import docker_backend
    while True:
        ui.clear()
        d = save.load()
        cur = d["settings"].get("docker_mode", "auto")
        print(c("\n  ⚙  設定\n", "bold", "bwhite"))
        real_ok = docker_backend.real_available()
        print(f"   Docker デーモン: {c('利用可能', 'bgreen') if real_ok else c('利用不可（未インストール or 権限なし）', 'yellow')}")
        print(f"   現在の Docker モード: {c(cur, 'bold', 'bcyan')}  → 実際の動作: {c(docker_mode_label(), 'bold')}\n")
        print(f"   {c('[1]', 'bold', 'bcyan')} Docker モード: auto（使えれば本物、ダメならシミュレーション）")
        print(f"   {c('[2]', 'bold', 'bcyan')} Docker モード: mock（常にシミュレーション。実環境を汚さない）")
        print(f"   {c('[3]', 'bold', 'bcyan')} Docker モード: real（本物の Docker を使う）")
        print(f"   {c('[r]', 'bold', 'bred')} セーブデータを初期化する")
        print(c("\n   [b] 戻る", "gray"))
        k = ask("\n  > ").lower()
        if k in ("b", "q", ""):
            return
        if k in ("1", "2", "3"):
            d["settings"]["docker_mode"] = {"1": "auto", "2": "mock", "3": "real"}[k]
            save.store(d)
            docker_backend._MODE = None
            os.environ.pop("LQ_DOCKER_MODE", None)
            if k == "3" and not real_ok:
                print(c("  ⚠ Docker デーモンが使えないため、実際にはシミュレーションモードで動作します。", "yellow"))
                pause("Enter で続ける")
        if k == "r":
            yn = ask(c("  本当に全ての進捗を消去しますか？ 消去するなら yes と入力 > ", "bred"))
            if yn == "yes":
                s = save.empty()
                s["settings"] = d["settings"]
                save.store(s)
                print(c("  セーブデータを初期化しました。", "bgreen"))
                pause("Enter で続ける")


def practice_resume():
    d = save.load()
    mission_id = d["learning"]["practice"].get("mission")
    if mission_id and mission_id not in d["cleared"]:
        for mission in all_missions():
            if mission.id == mission_id:
                return mission
    return first_uncleared()


def mode_select():
    while True:
        ui.clear()
        d = save.load()
        print(box(["どこから学ぶか、自分で選べます。いつでも変更できます。",
                   "[1] はじめてモード（おすすめ）: 文字を入力して Enter を押すところから。",
                   "    コマンドの意味を1つずつ説明し、一緒に練習します。",
                   "[2] 基礎練習モード: ファイル操作・検索・権限・ソフト追加・vim を反復。",
                   "    入力例は hint でいつでも表示できます。減点はありません。",
                   "[3] 応用練習モード: ワイルドカード・パイプ・集計・環境変数・プロセス・vim 編集。",
                   "    コマンドを組み合わせて、目的の結果を自分で作ります。",
                   "[4] 達人モード: アーカイブ・検索・ネットワーク・ユーザー・Git・スクリプト・テキスト加工・サービス。",
                   "    答えは書いていません。hint を段階的に使いながら自力で解きます。",
                   f"[5] 実践モード: 本物の bash で{len(all_missions())}問。Linux 運用からセキュリティ監査・報告へ。",
                   "    はじめて・基礎練習の sudo / apt は安全な模擬操作です。",
                   "    実践モードではコマンドが実際に動きます。",
                   "モードごとに続きの位置を保存します。既存の実践クリア実績も残ります。"], title="学習モードを選ぶ", color="green"))
        value = ask("  [1 / 2 / 3 / 4 / 5] 選択 / b: 戻る > ").lower()
        if value in ("b", "q", ""):
            return
        if value == "5" and not runner.practice_supported():
            windows_practice_notice()
            continue
        if value in ("1", "2", "3", "4", "5"):
            d["learning"]["mode"] = {"1": "intro", "2": "basic", "3": "advanced", "4": "expert", "5": "practice"}[value]
            save.store(d)
            return


def windows_practice_notice():
    ui.clear()
    print(box(["実践モードは本物の Linux（bash）でコマンドを動かすため、WSL が必要です。",
               "はじめて・基礎練習モードは、このまま Windows で学べます。",
               "",
               "WSL を使う手順（1回だけ）:",
               "  1. PowerShell を「管理者として実行」で開く",
               "  2. wsl --install と入力して Enter、終わったら PC を再起動",
               "  3. Ubuntu の初期設定（ユーザー名とパスワード）を済ませる",
               "  4. Ubuntu で sudo apt install python3 を実行する",
               "  5. もう一度 start.bat をダブルクリック（自動で WSL 版が起動します）",
               "",
               "進み具合は Windows 版と WSL 版で共通です。"], title="実践モードを使うには", color="yellow"))
    pause("Enter で戻る")


def command_dictionary():
    ui.clear()
    print(box(["ターミナル: 文字でコンピューターへ指示を出す画面。",
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
               "模擬モードは説明した一部の書式を練習する環境。本物の bash の全機能は使えません。"], title="はじめての用語・コマンド辞典", color="cyan"))
    pause()


def learning_dashboard(mode):
    ui.clear()
    print(header())
    print("\n  モードごとの進み具合\n")
    d = save.load()
    for key in guided.GUIDED_MODES:
        course = guided.lessons(key)
        done = len(set(d["learning"][key]["completed"]) & {s["id"] for s in course})
        print(f"  {guided.MODE_NAMES[key]}: {done}/{len(course)} レッスン")
    done = len([m for m in all_missions() if m.id in d["cleared"]])
    print(f"  実践モード: {done}/{len(all_missions())} 問")
    from engine import readiness
    print()
    for line in readiness.mastery_lines(d):
        print("  " + line)
    print("\n  [7] モード選択で切り替えられます。レッスンの復習は [2]、課題まつりは [8] から。")
    pause()


def main_menu():
    while True:
        ui.clear()
        print(ui.title_art())
        print(header())
        mode = guided.selected_mode()
        nxt = practice_resume() if mode == "practice" else None
        cont = f"続きから  {c('→ ' + nxt.id + ' ' + nxt.title, 'gray')}" if nxt else "続きから  " + c("（全問クリア済み！）", "gray")
        if mode != "practice":
            step = guided.current_step(mode)
            cont = "続きから → " + step["title"]
            if guided.completed_course(mode) and not guided.progress_for(mode).get("reviewing"):
                cont = "このモードは学習完了！ → 次のモードを選ぶ（復習は [2]）"
        items = [("1", "▶ ", cont), ("2", "🗺 ", "ステージ選択"), ("3", "📊", "進捗ダッシュボード"),
                 ("4", "📖", "小ネタ図鑑（Extra 閲覧モード）"), ("5", "❓", "遊び方・操作コマンド一覧"),
                 ("6", "⚙ ", "設定（Docker モード / セーブ初期化）"),
                 ("7", "🌱", "モード選択（はじめて / 基礎 / 応用 / 達人 / 実践）"),
                 ("8", "🎪", "課題まつり（総合復習）・自由自在マップ"),
                 ("9", "🔧", "Linux常用コース（目的検索・本物のツール実習）"), ("q", "🚪", "終了")]
        if mode != "practice":
            beginner_labels = {"2": "レッスン選択・復習", "4": "用語・コマンド辞典", "6": "設定（進捗の初期化）"}
            items = [(key, icon, beginner_labels.get(key, label))
                     for key, icon, label in items]
        print()
        for k, icon, label in items:
            print(f"   {c(f'[{k}]', 'bold', 'bcyan')} {icon} {label}")
        k = ask("\n  メニュー番号 > ").lower()
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
            ui.clear()
            d = save.load()
            print(c("\n  またね！ 今日の学びが明日のトラブル対応を救う。🐧\n", "bold", "bcyan"))
            if mode != "practice":
                print("  学習の続きは保存済みです。次回も [1] 続きから で再開できます。\n")
                return
            print(f"  現在のランク: {' '.join(save.rank_of(len(d['cleared']))[1:])}   総スコア: {save.total_score(d)} pt\n")
            return


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
        print("LinuxQuest は対話型のゲームです。ターミナルから ./start.sh で起動してください。")
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
            print(c("\n\n  中断しました。進捗は保存されています。またね！🐧\n", "bcyan"))
            return 0
        except Exception:
            import traceback
            log = runner.WORKSPACE / "error.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n") + traceback.format_exc() + "\n")
            print(c(f"\n  ⚠ 予期せぬエラーが発生しました（詳細: {log}）。メニューに戻ります。", "bred"))
            pause("Enter で続ける")


if __name__ == "__main__":
    sys.exit(main())
