"""初心者向けの段階学習と模擬ターミナル。ホストのシェル・sudo・apt は実行しない。"""
from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil
import stat

from engine import runner, save, ui

MODE_NAMES = {"intro": "はじめてモード", "basic": "基礎練習モード", "practice": "実践モード"}
PACKAGES = {
    "tree": ("フォルダの構造を枝分かれの図で表示するコマンド", "2.1.1-training"),
    "curl": ("URL からデータを取得するコマンド", "8.5.0-training"),
    "jq": ("JSON 形式のデータを読みやすく整理するコマンド", "1.7-training"),
}


@dataclass
class Result:
    output: str = ""
    code: int = 0


class TrainingError(Exception):
    pass


class Terminal:
    """限定した書式を解釈する練習環境。外部コマンドの実行や実環境の参照はしない。"""
    def __init__(self, root, progress):
        if Path(root).is_symlink():
            raise TrainingError("練習フォルダにシンボリックリンクは使えません。")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress = progress
        self.progress.setdefault("cwd", ".")
        self.progress.setdefault("packages", [])
        self.progress.setdefault("apt_updated", False)
        original_cwd = self.progress["cwd"]
        self.progress["cwd"] = "."
        for name, content in {"welcome.txt": "LinuxDOJOへようこそ！\n", ".memo": "見つけました！\n"}.items():
            path = self.path(name)
            if not path.exists():
                path.write_text(content)
        self.progress["cwd"] = original_cwd
        try:
            if not self.path(".").is_dir():
                self.progress["cwd"] = "."
        except TrainingError:
            self.progress["cwd"] = "."

    @property
    def cwd(self):
        return self.progress["cwd"]

    @property
    def display_cwd(self):
        return "/home/learner" + ("/" + self.cwd if self.cwd != "." else "")

    def path(self, value):
        if value.startswith("/"):
            if value == "/home/learner":
                value = "."
            elif value.startswith("/home/learner/"):
                value = value[len("/home/learner/"):]
            else:
                raise TrainingError("この練習では /home/learner の中だけを使います。pwd で現在地を確認しましょう。")
            path = self.root / value
        else:
            path = self.root / self.cwd / value
        # 自動生成した教材ファイル以外のリンクをたどって、実環境を操作しない。
        if any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent):
            raise TrainingError("この模擬ターミナルではシンボリックリンクを扱いません。")
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise TrainingError("練習フォルダの外には移動できません。cd /home/learner で練習の開始位置へ戻れます。")
        return resolved

    def ensure_directory(self, path):
        """教材のディレクトリと同名の練習ファイルがあっても復元する。"""
        current = self.root
        for part in path.relative_to(self.root).parts:
            current = self.path("/home/learner/" + str((current / part).relative_to(self.root)))
            if current.exists() and not current.is_dir():
                current.unlink()
            current.mkdir(exist_ok=True)

    def restore_file(self, name, content):
        target = self.path(name)
        self.ensure_directory(target.parent)
        if target.is_dir():
            shutil.rmtree(target)
        target.write_text(content)
        target.chmod(0o644)

    def execute(self, line):
        try:
            if "\u3000" in line:
                return Result("全角スペースが入っています。コマンドと対象の間は、半角スペースで区切りましょう。", 1)
            args = shlex.split(line)
            if not args:
                return Result("コマンドを入力して Enter を押してください。", 1)
            if args[0] in ("$", "#") or args[0].endswith("$"):
                return Result("$ は入力待ちの印です。$ を除いたコマンドだけ入力しましょう。", 1)
            if any(a in ("|", "||", "&&", ";", "&", "<", "2>") for a in args):
                return Result("ここでは1回に1つのコマンドを練習します。パイプや複数コマンドは実践モードで扱います。", 1)
            return self._execute(args)
        except (TrainingError, OSError, ValueError) as error:
            if isinstance(error, FileNotFoundError):
                message = "ファイルまたはフォルダが見つかりません。ls で名前を確認しましょう。"
            elif isinstance(error, FileExistsError):
                message = "同じ名前がすでにあります。ls で確認しましょう。"
            elif isinstance(error, IsADirectoryError):
                message = "これはフォルダです。cat はファイルの内容を読むコマンドです。"
            elif isinstance(error, OSError):
                message = "その操作はできません。名前と、ファイルかフォルダかを ls で確認しましょう。"
            else:
                message = str(error)
            return Result(message, 1)

    def _execute(self, args, admin=False):
        cmd, rest = args[0], args[1:]
        if cmd == "sudo":
            if not rest:
                raise TrainingError("sudo の後ろに実行するコマンドをスペースで続けます。例: sudo whoami")
            if rest[0] not in ("whoami", "apt"):
                raise TrainingError("練習用 sudo は whoami と apt のみに使えます。実際の管理者権限は使いません。")
            return self._execute(rest, admin=True)
        if cmd == "echo":
            redirect = next((i for i, a in enumerate(rest) if a in (">", ">>")), None)
            if redirect is not None:
                if len(rest) != redirect + 2:
                    raise TrainingError("保存先を1つ指定します。例: echo hello > note.txt")
                dest = self.path(rest[-1])
                with dest.open("a" if rest[redirect] == ">>" else "w") as f:
                    f.write(" ".join(rest[:redirect]) + "\n")
                return Result()
            return Result(" ".join(rest))
        if cmd == "pwd" and not rest:
            return Result(self.display_cwd)
        if cmd == "whoami" and not rest:
            return Result("root" if admin else "learner")
        if cmd == "cd" and len(rest) <= 1:
            dest = self.path(rest[0] if rest else "/home/learner")
            if not dest.is_dir():
                raise TrainingError("移動先のフォルダがありません。ls で確認しましょう。")
            self.progress["cwd"] = str(dest.relative_to(self.root))
            return Result()
        if cmd == "ls":
            flags = [x for x in rest if x.startswith("-")]
            if any(not set(x[1:]) <= set("alh") or x == "-" for x in flags):
                raise TrainingError("この練習で使える ls のオプションは -a、-l、-h です。")
            options = "".join(flags)
            targets = [x for x in rest if not x.startswith("-")] or ["."]
            output = []
            for value in targets:
                p = self.path(value)
                if not p.exists():
                    raise FileNotFoundError()
                items = sorted(p.iterdir()) if p.is_dir() else [p]
                for item in items:
                    if item.is_symlink():
                        continue
                    if item.name.startswith(".") and "a" not in options:
                        continue
                    label = item.name + ("/" if item.is_dir() else "")
                    if "l" in options:
                        label = f"{stat.filemode(item.stat().st_mode)} learner {item.stat().st_size:>4} {label}"
                    output.append(label)
            return Result("\n".join(output))
        if cmd == "cat" and rest:
            return Result("".join(self.path(x).read_text() for x in rest).rstrip("\n"))
        if cmd == "mkdir" and rest:
            parents = "-p" in rest
            for value in rest:
                if value == "-p":
                    continue
                if value.startswith("-"):
                    raise TrainingError("mkdir のオプションは -p が使えます。")
                self.path(value).mkdir(parents=parents, exist_ok=parents)
            return Result()
        if cmd == "touch" and rest:
            for value in rest:
                self.path(value).touch()
            return Result()
        if cmd in ("cp", "mv") and len(rest) == 2:
            source, dest = (self.path(x) for x in rest)
            if source.is_dir():
                raise TrainingError("この練習ではファイルを1つずつコピー・移動します。")
            if dest.is_dir():
                dest = self.path("/home/learner/" + str((dest / source.name).relative_to(self.root)))
            if cmd == "cp":
                shutil.copyfile(source, dest)
            else:
                source.rename(dest)
            return Result()
        if cmd == "rm" and rest:
            if any(x.startswith("-") for x in rest):
                raise TrainingError("この練習の rm はファイルのみ削除します。-r や -f は使いません。")
            for value in rest:
                self.path(value).unlink()
            return Result()
        if cmd == "chmod" and len(rest) == 2:
            mode, filename = rest
            p = self.path(filename)
            if mode in ("u+x", "+x"):
                p.chmod(p.stat().st_mode | stat.S_IXUSR)
            elif mode in ("644", "755", "600"):
                p.chmod(int(mode, 8))
            else:
                raise TrainingError("この練習では chmod u+x、644、755、600 を使えます。")
            return Result()
        if cmd == "grep" and len(rest) in (2, 3):
            ignore_case = len(rest) == 3 and rest[0] == "-i"
            if len(rest) == 3 and not ignore_case:
                raise TrainingError("この練習では grep 文字列 ファイル、または grep -i を使います。")
            pattern, filename = rest[-2:]
            lines = self.path(filename).read_text().splitlines()
            matches = [s for s in lines if (pattern.lower() in s.lower() if ignore_case else pattern in s)]
            return Result("\n".join(matches), 0 if matches else 1)
        if cmd == "wc" and len(rest) == 2 and rest[0] == "-l":
            return Result(f"{self.path(rest[1]).read_text().count(chr(10))} {rest[1]}")
        if cmd == "tree" and len(rest) <= 1:
            if "tree" not in self.progress["packages"]:
                return Result("tree: コマンドがまだ入っていません。sudo apt install tree で追加できます（訓練用）。", 127)
            root = self.path(rest[0] if rest else ".")
            if not root.is_dir():
                raise TrainingError("tree はフォルダを指定してください。")
            lines = ["."]
            def visit(p, depth=0):
                if depth > 12:
                    return
                for child in sorted(p.iterdir()):
                    if child.is_symlink() or child.name.startswith("."):
                        continue
                    lines.append("  " * depth + "└── " + child.name)
                    if child.is_dir():
                        visit(child, depth + 1)
            visit(root)
            return Result("\n".join(lines))
        if cmd == "apt":
            return self._apt(rest, admin)
        raise TrainingError(f"{cmd}: この模擬ターミナルでは未対応の入力です。スペルを確認し、hint で今回のコマンドを見てみましょう。")

    def _apt(self, rest, admin):
        if rest == ["--version"]:
            return Result("apt 2.7 (LinuxDOJO 訓練用シミュレーター)")
        if not rest:
            return Result("apt: ソフトを追加・削除する道具です。search / show / update / install / remove を練習できます。")
        action = rest[0]
        if action in ("update", "install", "remove") and not admin:
            return Result("E: Permission denied（管理者権限が必要です）。先頭に sudo を付けます。例: sudo apt update\nこの画面の apt は訓練専用で、実際の PC は変更しません。", 100)
        if action == "update" and len(rest) == 1:
            self.progress["apt_updated"] = True
            return Result("取得できるソフトの一覧を更新しました（模擬）。ソフト自体を更新する upgrade とは別です。")
        if action == "search" and len(rest) == 2:
            return Result("\n".join(f"{name} - {desc}" for name, (desc, _) in PACKAGES.items() if rest[1] in name))
        if action == "show" and len(rest) == 2 and rest[1] in PACKAGES:
            name = rest[1]
            desc, version = PACKAGES[name]
            return Result(f"Package: {name}\nVersion: {version}\n説明: {desc}")
        if action in ("install", "remove") and len(rest) == 2 and rest[1] in PACKAGES:
            name = rest[1]
            if action == "install":
                if not self.progress["apt_updated"]:
                    return Result("先に sudo apt update で一覧を更新しましょう（模擬）。", 100)
                if name not in self.progress["packages"]:
                    self.progress["packages"].append(name)
                return Result(f"{name} を追加しました（模擬）。実際の PC にはインストールしていません。")
            if name in self.progress["packages"]:
                self.progress["packages"].remove(name)
            return Result(f"{name} を削除しました（模擬）。")
        raise TrainingError("対応する例: apt search tree / apt show tree / sudo apt update / sudo apt install tree / sudo apt remove tree")


def lessons(mode):
    from curriculum.beginner_lessons import LESSONS
    return LESSONS[mode]


def selected_mode():
    return save.load()["learning"]["mode"]


def progress_for(mode):
    return save.load()["learning"][mode]


def remember(mode, progress):
    # 別モードの進捗と既存の59問のクリア情報を保持して更新する。
    d = save.load()
    d["learning"][mode] = progress
    save.store(d)


def current_step(mode, progress=None):
    course = lessons(mode)
    progress = progress if progress is not None else progress_for(mode)
    cursor = progress.get("cursor", course[0]["id"])
    return next((s for s in course if s["id"] == cursor), course[0])


def completed_course(mode, progress=None):
    progress = progress if progress is not None else progress_for(mode)
    return {step["id"] for step in lessons(mode)} <= set(progress.get("completed", []))


def matches(line, step):
    try:
        return shlex.split(line) == shlex.split(step["command"])
    except ValueError:
        return False


def prepare_step(terminal, step):
    # 各課題は教材用の初期ファイルを復元する。学習者の本来のファイルには触れない。
    for name, content in {"welcome.txt": "LinuxDOJOへようこそ！\n", ".memo": "見つけました！\n"}.items():
        terminal.restore_file("/home/learner/" + name, content)
    if "cwd" in step:
        target = terminal.path("/home/learner/" + step["cwd"].lstrip("/"))
        terminal.ensure_directory(target)
        terminal.progress["cwd"] = str(target.relative_to(terminal.root))
    for name in step.get("remove", []):
        target = terminal.path(name)
        if target == terminal.root or target in terminal.path(".").parents or target == terminal.path("."):
            raise TrainingError("課題の開始場所や練習のルートは削除できません。")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for name in step.get("dirs", []):
        terminal.ensure_directory(terminal.path(name))
    if "packages" in step:
        terminal.progress["packages"] = list(step["packages"])
    if "apt_updated" in step:
        terminal.progress["apt_updated"] = step["apt_updated"]
    for name, content in step.get("files", {}).items():
        terminal.restore_file(name, content)
    for name, mode in step.get("modes", {}).items():
        terminal.path(name).chmod(mode)


def play(mode, start=None):
    course = lessons(mode)
    progress = progress_for(mode)
    if start is not None:
        progress["cursor"] = course[start]["id"]
        progress["reviewing"] = True
        # 復習でも同じ開始位置で練習できるよう、課題側の開始場所を使う。
        progress["cwd"] = "."
    terminal = Terminal(runner.WORKSPACE / ("learning_" + mode), progress)
    step = current_step(mode, progress)
    index = course.index(step)
    while index < len(course):
        step = course[index]
        progress["cursor"] = step["id"]
        prepare_step(terminal, step)
        remember(mode, progress)
        ui.clear()
        print(ui.box([f"{MODE_NAMES[mode]}  {index + 1}/{len(course)}  {step['title']}", "",
                      *step["explanation"].splitlines(), "", "やってみよう: " + step["task"]], color="green"))
        if mode == "intro":
            print("\n  入力するコマンド: " + ui.c(step["command"], "bcyan"))
        print("\n  訓練用の模擬ターミナルです。実際の sudo・apt・シェルは実行しません。")
        print("  hint: 入力例 / lesson: 説明を再表示 / reset: この課題を復元 / menu: 保存して戻る")
        while True:
            try:
                line = input(f"\n 練習 {terminal.display_cwd} $ ").strip()
            except (EOFError, KeyboardInterrupt):
                remember(mode, progress)
                return
            if line in ("menu", "exit", "quit"):
                remember(mode, progress)
                return
            if line in ("hint", "answer", "help"):
                print(f"  入力例: {step['command']}\n  ヒントや解答を何度見ても減点はありません。")
                continue
            if line in ("lesson", "mission"):
                print(step["explanation"] + "\nやってみよう: " + step["task"])
                continue
            if line == "reset":
                prepare_step(terminal, step)
                print("課題のファイルと開始場所を復元しました。もう一度試せます。")
                continue
            result = terminal.execute(line)
            if result.output:
                print(result.output)
            remember(mode, progress)
            expected_code = step.get("expected_code", 100 if step["command"] == "apt update" else 0)
            if not matches(line, step) or result.code != expected_code:
                if result.code == 0:
                    print("  実行できました。今回の課題も試しましょう。hint で入力例を見られます。")
                continue
            print(ui.c("\n  ✓ できました！ " + step["success"], "bgreen"))
            completed = progress.setdefault("completed", [])
            if step["id"] not in completed:
                completed.append(step["id"])
            index += 1
            progress["cursor"] = course[index]["id"] if index < len(course) else step["id"]
            if index == len(course):
                progress["reviewing"] = False
            remember(mode, progress)
            try:
                choice = input("\n  Enter: 次の練習へ / menu: 保存して戻る > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if choice in ("menu", "q", "exit"):
                return
            break
    print(ui.box([f"{MODE_NAMES[mode]}を最後まで学習しました！", "何度でもレッスン選択から復習できます。",
                  "はじめてモードの次は基礎練習、基礎練習の次は実践へ進めます。", "メインメニューの [7] モード選択で切り替えましょう。"], color="green"))
    try:
        input("Enter でメニューへ > ")
    except (EOFError, KeyboardInterrupt):
        pass


def lesson_select(mode):
    while True:
        ui.clear()
        progress = progress_for(mode)
        course = lessons(mode)
        print(f"\n  {MODE_NAMES[mode]} — レッスン選択（復習に減点はありません）\n")
        for index, step in enumerate(course, 1):
            mark = "✓" if step["id"] in progress.get("completed", []) else "・"
            print(f"  [{index}] {mark} {step['title']}")
        try:
            value = input("\n  番号 / Enter: 続きから / b: 戻る > ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if value in ("b", "q"):
            return
        if value == "":
            play(mode)
        elif value.isdigit() and 1 <= int(value) <= len(course):
            play(mode, int(value) - 1)
