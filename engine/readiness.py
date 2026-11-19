"""基本操作を組み合わせて解く総合復習。実践59問とは別枠で進捗を保存する。"""
from pathlib import Path
import shlex
import shutil
import stat

from engine import guided, runner, save, ui


def scenarios():
    from curriculum.readiness import SCENARIOS
    return SCENARIOS


def prepare(scenario, root, progress=None):
    directory = Path(root) / scenario["id"]
    if directory.is_symlink():
        raise guided.TrainingError("復習フォルダにシンボリックリンクは使えません。")
    if directory.exists():
        shutil.rmtree(directory)
    state = progress if progress is not None else {}
    state.clear()
    terminal = guided.Terminal(directory, state)
    guided.prepare_step(terminal, {"cwd": ".", "remote": False,
                                  "files": scenario["files"], "remote_files": scenario["remote_files"]})
    return terminal


def check(scenario, terminal):
    try:
        if scenario["require_disconnected"] and terminal.progress["remote"]:
            return False, "まだ接続先にいます。exit で手元へ戻りましょう。"
        for name, content in scenario["expected_files"].items():
            path = terminal._side_path("/home/learner/" + name, False)
            if not path.is_file():
                return False, f"{name} がありません。目的文の保存先を確認しましょう。"
            if path.read_text() != content:
                return False, f"{name} の内容が要件と違います。cat で確認しましょう。"
        for name, mode in scenario["expected_modes"].items():
            if stat.S_IMODE(terminal._side_path("/home/learner/" + name, False).stat().st_mode) != mode:
                return False, f"{name} の権限が要件と違います。ls -l と chmod を確認しましょう。"
        for name in scenario["absent"]:
            if terminal._side_path("/home/learner/" + name, False).exists():
                return False, f"{name} がまだ残っています。削除対象を確認しましょう。"
        for package in scenario["packages"]:
            if package not in terminal.progress["packages"]:
                return False, f"{package} がまだ追加されていません。情報一覧の更新と本体追加は別の操作です。"
        for command in scenario["checks_commands"]:
            events = terminal.progress.get("command_events", [])
            host = "training-server" if scenario["id"] == "ready-06" and command in ("hostname", "cat server-note.txt") else "dojo-local"
            if not any(event["code"] == 0 and event["host"] == host and shlex.split(event["line"]) == shlex.split(command) for event in events):
                return False, "目的文にある作業後の確認がまだです。接続先や結果を確かめましょう。"
        return True, "目的に合う状態にできました。"
    except (OSError, ValueError, guided.TrainingError):
        return False, "ファイルの場所や種類を確認しましょう。reset で課題を最初から復元できます。"


def record_result(scenario, assisted):
    d = save.load()
    progress = d["learning"].setdefault("readiness", {"completed": {}, "sessions": {}})
    completed = progress.setdefault("completed", {})
    old = completed.get(scenario["id"])
    if old is None or not assisted:
        completed[scenario["id"]] = {"assisted": bool(assisted)}
    save.store(d)


def persist(scenario, terminal, assisted):
    d = save.load()
    progress = d["learning"].setdefault("readiness", {"completed": {}, "sessions": {}})
    progress["active"] = scenario["id"]
    progress.setdefault("sessions", {})[scenario["id"]] = {"terminal": terminal.progress, "assisted": assisted}
    save.store(d)


def play(scenario):
    root = runner.WORKSPACE / "learning_readiness"
    d = save.load()
    previous = d["learning"].get("readiness", {}).get("sessions", {}).get(scenario["id"])
    if previous and (root / scenario["id"]).is_dir():
        terminal = guided.Terminal(root / scenario["id"], previous["terminal"])
        assisted = previous["assisted"]
    else:
        terminal = prepare(scenario, root)
        assisted = False
    hint_level = 0
    ui.clear()
    print(ui.box([scenario["title"], scenario["brief"], "",
                  "目的に合わせて複数のコマンドを組み合わせ、check で判定します。",
                  "ヒントなしでできるか試してみましょう。hint / answer も使えます。",
                  "模擬環境なので実際の PC やサーバーは操作しません。",
                  "mission: 目的再表示 / hint: ヒント / answer: 手順 / reset: やり直し / menu: 保存して戻る"], color="green"))
    persist(scenario, terminal, assisted)
    while True:
        try:
            line = input(f"\n 復習 learner@{terminal.hostname} {terminal.display_cwd} $ ").strip()
        except (EOFError, KeyboardInterrupt):
            persist(scenario, terminal, assisted)
            return
        if line in ("menu", "quit"):
            persist(scenario, terminal, assisted)
            return
        if line == "mission":
            print(scenario["brief"])
            continue
        if line == "reset":
            terminal = prepare(scenario, root)
            hint_level = 0
            assisted = False
            persist(scenario, terminal, assisted)
            print("この課題の作業場所を初期状態に戻しました。")
            continue
        if line == "hint":
            assisted = True
            print(scenario["hints"][min(hint_level, 2)])
            hint_level += 1
            persist(scenario, terminal, assisted)
            continue
        if line == "answer":
            assisted = True
            print("\n".join(scenario["solution"]))
            persist(scenario, terminal, assisted)
            continue
        if line == "check":
            good, message = check(scenario, terminal)
            print(message)
            if good:
                record_result(scenario, assisted)
                print(ui.c("✓ 総合復習クリア！ " + ("手本ありで達成。reset で自力の復習もできます。" if assisted else "ヒントなしで達成できました。"), "bgreen"))
                print(scenario["explanation"])
                print("本物の bash で試す次の問題: " + " / ".join(scenario["practice"]))
            continue
        result = terminal.execute(line)
        if result.output:
            print(result.output)
        persist(scenario, terminal, assisted)


ROADMAP = [
    ("現在地・ファイル・退避", "1-1", "1-4", "1-5", "1-8"),
    ("ログ検索・パイプ・保存", "2-1", "2-2", "2-6", "2-7"),
    ("権限・環境変数・プロセス", "3-1", "3-4", "3-5", "3-6"),
    ("CPU・メモリ・ディスク調査", "3-7", "3-8"),
    ("圧縮・通信・名前解決・SSH設定", "4-1", "4-3", "4-5", "4-6", "4-7"),
    ("編集・スクリプト・定期実行", "6-1", "6-2", "6-6", "6-7", "6-8"),
    ("サービス・ログ・ユーザー管理", "7-1", "7-2", "7-3", "7-4"),
    ("コンテナ運用", "5-1", "5-2", "5-5", "5-6", "7-5", "7-7"),
]


def run():
    while True:
        ui.clear()
        d = save.load()
        progress = d["learning"].get("readiness", {})
        completed = progress.get("completed", {})
        print(ui.box(["知っているだけから、目的に合わせて操作できるへ。",
                      "総合復習では目的だけを読み、自分で手順を組み立てます。",
                      "ヒント利用あり・なしを分けて記録し、何度でも復習できます。",
                      "この確認は基礎の目安です。修了だけで全 Linux の管理を保証するものではありません。"], title="総合復習・学習ロードマップ", color="green"))
        for index, scenario in enumerate(scenarios(), 1):
            result = completed.get(scenario["id"])
            label = "未達成" if result is None else "手本あり達成" if result["assisted"] else "自力達成"
            print(f"  [{index}] {scenario['title']} — {label}")
        print("\n  本物の環境での練習につなぐロードマップ（実践モードの問題番号）")
        for name, *ids in ROADMAP:
            done = sum(mid in d["cleared"] for mid in ids)
            print(f"  {name}: {done}/{len(ids)}  " + " / ".join(ids))
        try:
            choice = input("\n  課題番号 / Enter: 前回の課題 / b: メニューへ > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice in ("b", "q", "menu"):
            return
        if choice == "":
            active = progress.get("active")
            target = next((s for s in scenarios() if s["id"] == active), scenarios()[0])
            play(target)
        elif choice.isdigit() and 1 <= int(choice) <= len(scenarios()):
            play(scenarios()[int(choice) - 1])
