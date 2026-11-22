"""本物の道具で行う日常Linux実習と、目的から探す学習経路。

python3 -m engine.toolbox list [検索語]
python3 -m engine.toolbox doctor [実習ID]
python3 -m engine.toolbox start <実習ID>
python3 -m engine.toolbox setup <実習ID> --directory <新しいフォルダ>
python3 -m engine.toolbox check --directory <フォルダ>

実習は普通のユーザー権限で動く。OSの隔離機能ではない。
パッケージの導入は行わず、未導入の道具は合格扱いにしない。
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORMAT = "linuxdojo-native-v1"


def labs():
    from curriculum.toolbox_labs import LABS as native
    from curriculum.toolbox_containers import LABS as containers
    from curriculum.toolbox_python import LABS as python_packages
    result = {}
    for group in (native, containers, python_packages):
        if result.keys() & group.keys():
            raise ValueError("実習IDが重複しています。")
        result.update(group)
    return result


def topics():
    from curriculum.toolbox_catalog import TOPICS
    return TOPICS


def search(query=""):
    terms = query.casefold().split()
    return [topic for topic in topics()
            if all(term in json.dumps(topic, ensure_ascii=False).casefold() for term in terms)]


def missing_tools(lab):
    return [tool for tool in lab["tools"] if not shutil.which(tool)]


def dependency_message(lab):
    missing = missing_tools(lab)
    if not missing:
        return "実行可能（コマンドの存在を確認。サービス稼働や習得の判定ではありません）"
    if not lab["packages"]:
        return ("未導入: " + ", ".join(missing) + "\n"
                "docs/LINUX_DAILY_USE.md の導入手順と公式のOS別手順を確認します。導入は自動では行いません。")
    packages = " ".join(shlex.quote(name) for name in lab["packages"])
    return ("未導入: " + ", ".join(missing) + "\n"
            "Ubuntu/Debianで導入する場合: sudo apt update && sudo apt install " + packages + "\n"
            "コマンド名とパッケージ名は異なる場合があります。導入は自動では行いません。")


def default_directory(lab_id):
    return Path(os.environ.get("LQ_WORKSPACE", str(ROOT / "workspace"))) / "toolbox" / lab_id


def _lab(lab_id):
    if lab_id not in labs():
        raise ValueError("不明な実習ID: " + lab_id)
    return labs()[lab_id]


def _directory(path):
    path = Path(path).expanduser().absolute()
    # Reject symlinked ancestors as well as the final path before creating state.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("実習フォルダと親フォルダにシンボリックリンクは使えません。")
    return path


def _state(path):
    directory = _directory(path)
    state_path = directory / ".dojo" / "state.json"
    if (directory / ".dojo").is_symlink() or state_path.is_symlink():
        raise ValueError("実習状態にシンボリックリンクは使えません。")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("format") != FORMAT or state.get("lab") not in labs():
        raise ValueError("このコースで作成した実習フォルダではありません。")
    return directory, state


def _store(directory, state):
    (directory / ".dojo" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def setup(lab_id, directory):
    lab = _lab(lab_id)
    if missing_tools(lab):
        raise ValueError(dependency_message(lab))
    directory = _directory(directory)
    if directory.exists():
        raise ValueError("既存のフォルダは上書きしません。startで再開するか、新しい出力先を選びます。")
    directory.mkdir(parents=True)
    (directory / ".dojo").mkdir()
    state = {"format": FORMAT, "lab": lab_id, "answer_viewed": False, "passed": False, "prepared": False}
    _store(directory, state)
    try:
        lab["setup"](directory)
        (directory / "TASK.txt").write_text(lab["task"] + "\n", encoding="utf-8")
        state["prepared"] = True
        _store(directory, state)
    except Exception:
        # Keep the partially built directory for diagnosis; never remove unrelated paths.
        raise
    return directory


def check(directory):
    directory, state = _state(directory)
    lab = _lab(state["lab"])
    state["passed"] = False
    if not state.get("prepared"):
        _store(directory, state)
        return False, "準備が完了していません。setup時のエラーを解消し、新しいフォルダでやり直します。"
    if missing_tools(lab):
        _store(directory, state)
        return False, dependency_message(lab)
    try:
        lab["check"](directory)
    except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        _store(directory, state)
        return False, str(error) or "成果物が条件を満たしていません。TASK.txtを確認します。"
    state["passed"] = True
    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    _store(directory, state)
    assisted = "解答参照あり" if state.get("answer_viewed") else "この実習内での解答参照なし"
    return True, "実機検査PASS（" + assisted + "）。理由を説明できるか、別のデータでも復習してください。"


def solution(lab_id, directory=None):
    lab = _lab(lab_id)
    if directory is not None:
        directory, state = _state(directory)
        if state["lab"] != lab_id:
            raise ValueError("実習IDとフォルダのIDが一致しません。")
        state["answer_viewed"] = True
        _store(directory, state)
    return lab["solution"]


def cleanup(directory):
    directory, state = _state(directory)
    lab = _lab(state["lab"])
    if "cleanup" not in lab:
        return "この実習に常駐リソースはありません。作業ファイルは復習用に残します。"
    state["passed"] = False
    _store(directory, state)
    lab["cleanup"](directory)
    return "この実習が作成した専用リソースを解除しました。作業ファイルは残します。"


def start(lab_id, directory=None):
    lab = _lab(lab_id)
    directory = _directory(directory or default_directory(lab_id))
    if missing_tools(lab):
        raise ValueError(dependency_message(lab))
    if directory.exists():
        directory, state = _state(directory)
        if state["lab"] != lab_id:
            raise ValueError("指定先は別の実習です。")
        if not state.get("prepared"):
            raise ValueError("準備が途中で失敗しています。原因を解消して新しいフォルダでsetupします。")
    else:
        setup(lab_id, directory)
    command = " ".join(shlex.quote(str(x)) for x in (sys.executable, Path(__file__).resolve()))
    args = " --directory " + shlex.quote(str(directory))
    rc = directory / ".dojo" / "shell.bash"
    rc.write_text(
        "HISTFILE=" + shlex.quote(str(directory / ".dojo" / "history")) + "\n"
        "PS1='toolbox:\\w\\$ '\n"
        "check() { " + command + " check" + args + "; }\n"
        "task() { cat " + shlex.quote(str(directory / "TASK.txt")) + "; }\n"
        "answer() { " + command + " solution " + shlex.quote(lab_id) + args + "; }\n",
        encoding="utf-8")
    with rc.open("a", encoding="utf-8") as stream:
        stream.write("cleanup() { " + command + " cleanup" + args + "; }\n")
    from engine import ui
    title = f"常用コース  {lab_id}  {lab['title']}"
    summary = [title, "", "やってみよう: " + lab["task"].splitlines()[0],
               "task: 課題全文 / check: 判定 / answer: 手本 / exit: 戻る"]
    with ui.QuestionScreen([title, "", *lab["task"].splitlines()], summary=summary):
        print(ui.c("\n  作業先: " + str(directory), "gray"))
        print("  check: 判定 / task: 課題文 / answer: 手本 / cleanup: 専用リソース解除 / exit: 戻る")
        print(ui.c("  本物のbashです。操作対象はこの実習フォルダです。", "gray"))
        subprocess.run(["bash", "--noprofile", "--rcfile", str(rc), "-i"], cwd=directory, check=False)
    return directory


def validate_catalog():
    from engine import runner
    mission_ids = {mission.id for mission in runner.load_curriculum()}
    ids = set()
    guide = (ROOT / "docs" / "LINUX_DAILY_USE.md").read_text(encoding="utf-8")
    for topic in topics():
        for key in ("id", "title", "category", "commands", "missions", "labs", "guide", "level"):
            if key not in topic:
                raise ValueError("対応表に項目がありません: " + key)
        if topic["id"] in ids:
            raise ValueError("対応表のIDが重複: " + topic["id"])
        ids.add(topic["id"])
        if topic["level"] not in ("core", "extension"):
            raise ValueError("対応表のlevelが不正")
        if not set(topic["missions"]) <= mission_ids:
            raise ValueError("存在しないミッション: " + topic["id"])
        if not set(topic["labs"]) <= set(labs()):
            raise ValueError("存在しない実機実習: " + topic["id"])
        anchor = topic["guide"].removeprefix("#")
        if not anchor or f'id="{anchor}"' not in guide:
            raise ValueError("存在しない手引きアンカー: " + topic["id"])
        if topic["level"] == "core" and not (topic["missions"] or topic["labs"]):
            raise ValueError("中核分野に演習がありません: " + topic["id"])
    return len(ids)


def show_topics(query=""):
    show_topics_list(search(query))


def show_topics_list(found):
    for topic in found:
        print(f"{topic['id']}: {topic['title']} [{topic['category']}/{topic['level']}]")
        print("  コマンド: " + " ".join(topic["commands"]))
        print("  既存課題: " + (", ".join(topic["missions"]) or "なし"))
        print("  実機実習: " + (", ".join(topic["labs"]) or "VM/既存課題・手引きを参照"))
        print("  手引き: docs/LINUX_DAILY_USE.md" + topic["guide"])


def menu():
    """既存ゲームの進捗とは別枠。検索・実機実習・必要ツールをひとつの入口に。"""
    from engine import ui
    while True:
        ui.clear()
        print(ui.header(["Linux 常用コース"], ""))
        print("\n  " + ui.c("目的から課題を探し、本物の道具で練習します。", "bold"))
        print(ui.c("  実践モードとは別に、専用フォルダへ保存します。", "dim"))
        print()
        for key, label, desc in (("1", "目的・コマンドから探す", "例: ログ、ディスク、ssh"),
                                 ("2", "実機実習を選んで始める", "本物のツールで操作"),
                                 ("3", "必要なツールの確認", "実習に必要な道具が入っているか"),
                                 ("4", "学習ガイドを読む", "q で閉じる"), ("b", "戻る", "メインメニューへ")):
            print(ui.menu_row(key, label, desc, label_w=22))
        print()
        print(ui.footer(("番号", "選択"), ("b", "戻る")))
        print(ui.take_flash(), end="")
        try:
            choice = input(ui.c("\n  > ", "bold", "accent")).strip().lower()
            if choice in ("b", "q", ""):
                return
            if choice == "1":
                found = search(input("\n  目的・コマンド・分野（空欄で全件） > "))
                if not found:
                    print("\n" + ui.status_line("warn", "該当する分野がありません。別の言葉（例: ログ、ディスク、ssh）で探し直せます。")
                          + ui.c("\n  空欄で Enter を押すと全件を表示します。", "dim"))
                else:
                    show_topics_list(found)
                    print(ui.c("\n  実機実習は、メニューの [2] で「実機実習」に出た名前を入力すると始められます。", "dim"))
                mid = input("\n  取り組む既存課題ID（例 7-4。空欄で戻る） > ").strip() if found else ""
                if mid:
                    from engine import runner
                    from engine.main import play
                    mission = runner.get_mission(mid)
                    if mission:
                        play(mission)
                    else:
                        print("\n" + ui.status_line("warn", f"課題ID「{mid}」はありません。上の「既存課題」に並ぶ ID（例 7-4）を入力します。"))
            elif choice in ("2", "3"):
                print()
                for key, lab in labs().items():
                    availability = "未導入: " + ",".join(missing_tools(lab)) if missing_tools(lab) else "実行可能"
                    status_color = "yellow" if missing_tools(lab) else "dim"
                    print("  " + ui.pad(ui.c(f"[{key}]", "bold", "accent"), 12) + f" {lab['title']} " + ui.c(f"({availability})", status_color))
                what = "始める" if choice == "2" else "確認する"
                key = input(f"\n  {what}実習の名前（[ ] の中の文字。空欄で戻る） > ").strip()
                if key:
                    if key not in labs():
                        print("\n" + ui.status_line("warn", f"「{key}」という実習はありません。一覧の [ ] の中の文字をそのまま入力します。"))
                    elif choice == "3":
                        print("\n  " + dependency_message(_lab(key)).replace("\n", "\n  "))
                    else:
                        start(key)
                        print("\n" + ui.status_line("info", "実習から戻りました。作業フォルダは残っています。同じ名前でもう一度始めると続きから再開できます。"))
            elif choice == "4":
                import pydoc
                pydoc.pager((ROOT / "docs" / "LINUX_DAILY_USE.md").read_text(encoding="utf-8"))
            else:
                ui.invalid_choice(choice, "1〜4 か b")
                continue
        except (EOFError, KeyboardInterrupt):
            print()
            return
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print("\n" + ui.status_line("ng", str(error)))
            print(ui.c("  Enter で常用コースへ戻り、別の選択肢を試せます。", "dim"))
        try:
            input(ui.c("\n  Enter で常用コースのメニューへ戻る > ", "dim"))
        except (EOFError, KeyboardInterrupt):
            return


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="目的・コマンドから学習経路を検索")
    listing.add_argument("query", nargs="*", default=[])
    doctor = commands.add_parser("doctor", help="実機実習に必要なツール。未導入時は終了コード2")
    doctor.add_argument("id", nargs="?")
    for name in ("setup", "start", "solution"):
        sub = commands.add_parser(name)
        sub.add_argument("id")
        sub.add_argument("--directory", type=Path)
    checking = commands.add_parser("check")
    checking.add_argument("--directory", type=Path, default=Path.cwd())
    cleaning = commands.add_parser("cleanup", help="Dockerなどこの実習専用のリソースを解除")
    cleaning.add_argument("--directory", type=Path, default=Path.cwd())
    commands.add_parser("audit", help="対応表の課題ID・実習ID・手引きの整合性を検証")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            show_topics(" ".join(args.query))
        elif args.command == "audit":
            print(f"対応表 {validate_catalog()} 分野: 参照整合性OK（技能習得の認定ではありません）")
        elif args.command == "doctor":
            selected = {args.id: _lab(args.id)} if args.id else labs()
            for key, lab in selected.items():
                print(key + ": " + dependency_message(lab))
            return 2 if any(missing_tools(lab) for lab in selected.values()) else 0
        elif args.command == "setup":
            path = setup(args.id, args.directory or default_directory(args.id))
            print(_lab(args.id)["task"] + "\n作業先: " + str(path))
        elif args.command == "start":
            start(args.id, args.directory)
        elif args.command == "solution":
            print(solution(args.id, args.directory))
        elif args.command == "check":
            ok, message = check(args.directory)
            print(message)
            return 0 if ok else 1
        elif args.command == "cleanup":
            print(cleanup(args.directory))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
