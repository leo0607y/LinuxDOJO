"""初心者向けの段階学習と模擬ターミナル。ホストのシェル・sudo・apt は実行しない。"""
from dataclasses import dataclass
import fnmatch
import os
from pathlib import Path
import re
import shlex
import shutil
import stat

from engine import commands, runner, save, textcmd, ui, vim_sim

MODE_NAMES = {"intro": "はじめてモード", "basic": "基礎練習モード", "advanced": "応用練習モード",
              "expert": "達人モード", "practice": "実践モード"}
GUIDED_MODES = ("intro", "basic", "advanced", "expert")
INTRO_SHOWN_ANSWERS = 5  # はじめてモードは、最初の5課題だけ入力するコマンドを表示する
PACKAGES = {
    "tree": ("フォルダの構造を枝分かれの図で表示するコマンド", "2.1.1-training"),
    "curl": ("URL からデータを取得するコマンド", "8.5.0-training"),
    "jq": ("JSON 形式のデータを読みやすく整理するコマンド", "1.7-training"),
    "vim": ("高機能なテキストエディタ。サーバーで設定ファイルを書き換えるときによく使う", "9.1-training"),
}
# 最初から入っている扱いのコマンド（which で場所を表示できる）
BUILTIN_COMMANDS = ("echo", "pwd", "ls", "cat", "cd", "mkdir", "touch", "cp", "mv", "rm", "chmod",
                    "grep", "wc", "head", "tail", "find", "history", "hostname", "whoami", "sudo",
                    "apt", "ssh", "scp", "man", "false", "sort", "uniq", "cut", "env", "printenv",
                    "export", "unset", "ps", "kill", "pgrep", "df", "du", "free", "diff")
DEFAULT_ENV = {"HOME": "/home/learner", "USER": "learner", "SHELL": "/bin/bash",
               "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "ja_JP.UTF-8"}
# 模擬のプロセス一覧。実際の PC のプロセスは読まず、止めもしない。
DEFAULT_PROCESSES = [
    {"pid": 1, "user": "root", "cmd": "/sbin/init", "cpu": 0.0, "mem": 0.3},
    {"pid": 512, "user": "root", "cmd": "/usr/sbin/sshd -D", "cpu": 0.0, "mem": 0.2},
    {"pid": 845, "user": "root", "cmd": "/usr/sbin/cron -f", "cpu": 0.0, "mem": 0.1},
    {"pid": 2001, "user": "learner", "cmd": "-bash", "cpu": 0.0, "mem": 0.1},
]
SHELL_PID = 2001
SIGNALS = {"-9": "KILL", "-KILL": "KILL", "-SIGKILL": "KILL", "-15": "TERM", "-TERM": "TERM", "-SIGTERM": "TERM"}
VAR_RE = re.compile(r"\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GLOB_CHARS = set("*?[")
# パイプの後ろで、前のコマンドの出力を入力として読むコマンド
READS_STDIN = ("cat", "grep", "sort", "uniq", "cut", "wc", "head", "tail")


@dataclass
class Result:
    output: str = ""
    code: int = 0


class TrainingError(Exception):
    pass


class Terminal:
    """限定した書式を解釈する練習環境。外部コマンドの実行や実環境の参照はしない。"""
    # Windows はファイル権限の仕組みが Linux と違うため、権限は進捗データ上で模擬する。
    VIRTUAL_MODES = os.name == "nt"

    def __init__(self, root, progress):
        if Path(root).is_symlink():
            raise TrainingError("練習フォルダにシンボリックリンクは使えません。")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress = progress
        self.progress.setdefault("cwd", ".")
        self.progress.setdefault("packages", [])
        self.progress.setdefault("apt_updated", False)
        self.progress.setdefault("remote", False)
        self.progress.setdefault("remote_cwd", ".")
        self.progress.setdefault("ssh_known", False)
        self.progress.setdefault("ssh_pending", False)
        self.progress.setdefault("history", [])
        self.progress.setdefault("last_status", 0)
        self.progress.setdefault("command_events", [])
        self.progress.setdefault("editor", None)
        self.progress.setdefault("env", dict(DEFAULT_ENV))
        self.progress.setdefault("shell_vars", {})
        self.progress.setdefault("processes", [dict(p) for p in DEFAULT_PROCESSES])
        original_remote = self.progress["remote"]
        self.progress["remote"] = False
        original_cwd = self.progress["cwd"]
        self.progress["cwd"] = "."
        for name, content in {"welcome.txt": "LinuxDOJOへようこそ！\n", ".memo": "見つけました！\n"}.items():
            path = self.path(name)
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                self.set_mode(path, 0o644)
        self.progress["cwd"] = original_cwd
        remote_root = self.root / ".remote"
        if remote_root.is_symlink():
            raise TrainingError("模擬サーバーの保存先にシンボリックリンクは使えません。")
        if remote_root.exists() and not remote_root.is_dir():
            remote_root.unlink()
        remote_root.mkdir(exist_ok=True)
        self.progress["remote"] = True
        for name, content in {"server-note.txt": "これは練習用サーバーのファイルです。\n", "download.txt": "server download\n"}.items():
            target = self.path("/home/learner/" + name)
            if not target.exists():
                self.restore_file("/home/learner/" + name, content)
        self.progress["remote"] = original_remote
        try:
            if not self.path(".").is_dir():
                self.set_cwd(".")
        except TrainingError:
            self.set_cwd(".")

    @property
    def cwd(self):
        return self.progress["remote_cwd" if self.progress["remote"] else "cwd"]

    @property
    def active_root(self):
        return self.root / ".remote" if self.progress["remote"] else self.root

    @property
    def hostname(self):
        return "training-server" if self.progress["remote"] else "dojo-local"

    def set_cwd(self, value):
        self.progress["remote_cwd" if self.progress["remote"] else "cwd"] = value

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
            path = self.active_root / value
        else:
            path = self.active_root / self.cwd / value
        # 自動生成した教材ファイル以外のリンクをたどって、実環境を操作しない。
        if any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent):
            raise TrainingError("この模擬ターミナルではシンボリックリンクを扱いません。")
        resolved = path.resolve()
        if resolved != self.active_root and self.active_root not in resolved.parents:
            raise TrainingError("練習フォルダの外には移動できません。cd /home/learner で練習の開始位置へ戻れます。")
        if not self.progress["remote"] and (resolved == self.root / ".remote" or self.root / ".remote" in resolved.parents):
            raise TrainingError("模擬サーバーのファイルは ssh で接続するか scp で転送して扱いましょう。")
        return resolved

    def _mode_key(self, path):
        return path.relative_to(self.root).as_posix()

    def mode_of(self, path):
        """ファイルの権限 (例: 0o644) を返す。存在しなければ FileNotFoundError。"""
        if not self.VIRTUAL_MODES:
            return stat.S_IMODE(path.stat().st_mode)
        path.stat()
        default = 0o755 if path.is_dir() else 0o644
        return self.progress.setdefault("modes", {}).get(self._mode_key(path), default)

    def set_mode(self, path, mode):
        if not self.VIRTUAL_MODES:
            path.chmod(mode)
            return
        path.stat()
        modes = self.progress.setdefault("modes", {})
        if mode == (0o755 if path.is_dir() else 0o644):
            modes.pop(self._mode_key(path), None)  # 既定の権限は保存しない
        else:
            modes[self._mode_key(path)] = mode

    def created(self, path, existed, mode=0o666):
        """新規作成時だけ、模擬シェルの umask を初期権限へ適用する。"""
        if not existed:
            self.forget_mode(path)
            mask = self.progress.get("users", {}).get("umask", 0o022)
            self.set_mode(path, mode & ~mask)

    def _write_output(self, target, text, append):
        path = self.path(target)
        existed = path.exists()
        with path.open("a" if append else "w", encoding="utf-8") as stream:
            stream.write(text)
        self.created(path, existed)

    def forget_mode(self, path):
        """削除・移動したファイル（フォルダなら中身も）の模擬権限を消す。"""
        if not self.VIRTUAL_MODES:
            return {}
        modes = self.progress.setdefault("modes", {})
        key = self._mode_key(path)
        removed = {}
        for name in list(modes):
            if name == key or name.startswith(key + "/"):
                removed[name[len(key):]] = modes.pop(name)
        return removed

    def move_mode(self, source, dest):
        if not self.VIRTUAL_MODES:
            return
        self.forget_mode(dest)
        modes = self.progress.setdefault("modes", {})
        for suffix, mode in self.forget_mode(source).items():
            modes[self._mode_key(dest) + suffix] = mode

    def ensure_directory(self, path):
        """教材のディレクトリと同名の練習ファイルがあっても復元する。"""
        current = self.active_root
        for part in path.relative_to(self.active_root).parts:
            current = self.path("/home/learner/" + (current / part).relative_to(self.active_root).as_posix())
            if current.exists() and not current.is_dir():
                current.unlink()
            existed = current.exists()
            current.mkdir(exist_ok=True)
            if not existed:
                # 教材の初期配置は学習者やホストの umask に依存させない。
                self.set_mode(current, 0o755)

    def restore_file(self, name, content):
        target = self.path(name)
        self.ensure_directory(target.parent)
        if target.is_dir():
            shutil.rmtree(target)
        self.forget_mode(target)
        target.write_text(content, encoding="utf-8")
        self.set_mode(target, 0o644)

    def prompt_text(self):
        editor = self.progress.get("editor")
        if editor:
            mode = "-- INSERT --" if editor["mode"] == "insert" else "NORMAL"
            return f"vim {editor['name']} [{mode}] > "
        return f"練習 learner@{self.hostname} {self.display_cwd} $ "

    def open_editor(self, name, lines=None, **state):
        path = self.path(name)
        if path.is_dir():
            raise TrainingError("フォルダは vim で開けません。ファイル名を指定しましょう。")
        exists = path.exists()
        if lines is None:
            lines = path.read_text(encoding="utf-8").splitlines() if exists else []
        editor = vim_sim.new_state(name, path.relative_to(self.active_root).as_posix(),
                                   self.progress["remote"], lines, exists)
        editor.update(state)
        self.progress["editor"] = editor
        return editor

    def _editor_input(self, line):
        editor = self.progress["editor"]
        message, code, action = vim_sim.handle(editor, line)
        if action in ("write", "write_quit"):
            try:
                path = self._side_path("/home/learner/" + editor["key"], editor["remote"])
                if not path.parent.is_dir():
                    raise FileNotFoundError()
                existed = path.exists()
                path.write_text("".join(x + "\n" for x in editor["lines"]), encoding="utf-8")
                self.created(path, existed)
            except (TrainingError, OSError):
                return Result(vim_sim.render(editor, f'E212: Can\'t open file for writing（"{editor["name"]}" を保存できません。保存先のフォルダを確認しましょう）'), 1)
            editor.update(modified=False, new_file=False)
            message = f'"{editor["name"]}" {len(editor["lines"])}L written（保存しました）'
        if action in ("quit", "write_quit"):
            self.progress["editor"] = None
            return Result((message + "\n" if message else "") + "vim を終了して、ターミナルに戻りました。", code)
        return Result(vim_sim.render(editor, message), code)

    def _vim(self, cmd, rest):
        if "vim" not in self.progress["packages"]:
            return Result(f"Command '{cmd}' not found, but can be installed with:\n"
                          "sudo apt install vim\n"
                          "（訓練用の表示です。この練習では vim がまだ入っていません）", 127)
        if rest == ["--version"]:
            return Result("VIM - Vi IMproved 9.1（訓練用シミュレーター）")
        if len(rest) != 1 or rest[0].startswith("-"):
            raise TrainingError("この練習では vim ファイル名 の形で開きます。例: vim memo.txt")
        editor = self.open_editor(rest[0])
        note = "新しいファイルです。" if editor["new_file"] else "ファイルを開きました。"
        return Result(vim_sim.render(editor, note + "今はノーマルモードです。文字を書くには i を入力します。"))

    def execute(self, line):
        if self.progress.get("editor"):
            return self._editor_input(line)
        host = self.hostname
        result = self._execute_line(line)
        if line.strip():
            self.progress["history"].append(line.strip())
            self.progress["command_events"].append({"line": line.strip(), "code": result.code, "host": host})
        self.progress["last_status"] = result.code
        return result

    # ---- シェルの展開（変数・ワイルドカード）
    def variable(self, name):
        if name in self.progress["shell_vars"]:
            return self.progress["shell_vars"][name]
        return self.progress["env"].get(name, "")

    def expand_variables(self, line):
        """$NAME / ${NAME} を値に置き換える。'...' の中は本物と同じく置き換えない。"""
        output, quote, index = [], None, 0
        while index < len(line):
            char = line[index]
            if char == "\\" and quote != "'" and index + 1 < len(line):
                output.append(line[index:index + 2])
                index += 2
                continue
            if char in "'\"" and quote in (None, char):
                quote = None if quote == char else char
            elif char == "$" and quote != "'":
                match = VAR_RE.match(line, index)
                if match:
                    value = self.variable(match.group(1).strip("{}"))
                    if quote == '"':
                        output.append(value.replace("\\", "\\\\").replace('"', '\\"'))
                    elif value:
                        output.append(shlex.quote(value))
                    index = match.end()
                    continue
            output.append(char)
            index += 1
        return "".join(output)

    def expand_globs(self, args):
        """* ? [ ] を、練習フォルダの中で一致する名前に広げる。一致がなければそのまま。"""
        if not args or args[0] in ("find", "export", "unset"):
            return args
        output = [args[0]]
        for arg in args[1:]:
            pattern_arg = getattr(arg, "glob_pattern", arg)
            if arg.startswith("-") or not GLOB_CHARS & set(pattern_arg) or not getattr(arg, "has_glob", True):
                output.append(arg)
                continue
            head, _, pattern = pattern_arg.rpartition("/")
            if GLOB_CHARS & set(head):
                output.append(arg)
                continue
            if arg.startswith("/") and not head:
                head = "/"
            base = self.path(head or ".")
            names = []
            if base.is_dir():
                for item in sorted(base.iterdir()):
                    if item.is_symlink() or (not self.progress["remote"] and item == self.root / ".remote"):
                        continue
                    if item.name.startswith(".") and not pattern.startswith("."):
                        continue
                    if fnmatch.fnmatchcase(item.name, pattern):
                        names.append((head.rstrip("/") + "/" if head else "") + item.name)
            output.extend(names or [arg])
        return output

    def _read_input(self, cmd, files, stdin):
        if files:
            return "".join(self.path(x).read_text(encoding="utf-8") for x in files)
        if stdin is not None:
            return stdin + "\n" if stdin else ""
        raise TrainingError(f"{cmd} の後ろにファイル名を書くか、| で前のコマンドの結果を渡します。")

    def _pipeline(self, stages):
        if any(not stage for stage in stages):
            raise TrainingError("| の前と後ろにコマンドを書きます。例: cat access.log | grep 404")
        output, result = None, Result()
        for index, stage in enumerate(stages):
            args, input_file, redirect = [], None, None
            position = 0
            while position < len(stage):
                token = stage[position]
                if shell_operator(token, ("<", ">", ">>")):
                    if position + 1 >= len(stage) or shell_operator(stage[position + 1]):
                        raise TrainingError("リダイレクトの後ろにファイル名を1つ指定します。")
                    name = stage[position + 1]
                    if token == "<":
                        if input_file is not None:
                            raise TrainingError("入力元は1つ指定しましょう。")
                        input_file = name
                    else:
                        if redirect is not None:
                            raise TrainingError("保存先は1つ指定しましょう。")
                        redirect = (token, name)
                    position += 2
                else:
                    args.append(token)
                    position += 1
            if not args:
                raise TrainingError("実行するコマンドを書きましょう。")
            if redirect and index != len(stages) - 1:
                raise TrainingError("> や >> での保存は、パイプの一番最後に書きます。")
            if input_file is not None:
                text = self.path(input_file).read_text(encoding="utf-8")
                output = text[:-1] if text.endswith("\n") else text
            result = self._execute(self.expand_globs(args), stdin=output)
            output = result.output
            if redirect:
                self._write_output(redirect[1], output + ("\n" if output else ""), redirect[0] == ">>")
                result = Result(code=result.code)
        return result

    def _execute_line(self, line):
        try:
            if "\u3000" in line:
                return Result("全角スペースが入っています。コマンドと対象の間は、半角スペースで区切りましょう。", 1)
            line = self.expand_variables(line)
            segments = split_pipes(line)
            args = shell_words(line)
            if not args:
                return Result("コマンドを入力して Enter を押してください。", 1)
            if args[0] in ("$", "#") or args[0].endswith("$"):
                return Result("$ は入力待ちの印です。$ を除いたコマンドだけ入力しましょう。", 1)
            if any(shell_operator(a, ("||", "&&", ";", "&", "2>", "<<")) for a in args):
                return Result("ここでは && や ; でつなぐ複数コマンドは扱いません。1つずつ入力するか、| でつなぎましょう。実践モードでは本物の bash で使えます。", 1)
            if self.progress["ssh_pending"]:
                if args == ["no"]:
                    self.progress["ssh_pending"] = False
                    return Result("Host key verification failed. 接続を中止しました。管理者から別経路で指紋を確認しましょう。", 255)
                if args == ["yes"]:
                    self.progress.update(ssh_pending=False, ssh_known=True, remote=True, remote_cwd=".")
                    return Result("接続先の指紋を確認済みとして模擬接続しました。learner@training-server（実通信なし）")
                return Result("接続確認中です。指紋を別経路で確認できたら yes、不明なら no を入力します。", 1)
            return self._pipeline([shell_words(segment) for segment in segments])
        except (TrainingError, OSError, ValueError) as error:
            if isinstance(error, textcmd.UsageError):
                message = str(error)
            elif isinstance(error, FileNotFoundError):
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

    def _execute(self, args, admin=False, stdin=None):
        cmd, rest = args[0], args[1:]
        if ASSIGN_RE.match(cmd) and not rest:
            name, _, value = cmd.partition("=")
            if name in self.progress["env"]:
                self.progress["env"][name] = value
            else:
                self.progress["shell_vars"][name] = value
            return Result()
        handled = self._text_command(cmd, rest, stdin)
        if handled is not None:
            return handled
        handled = self._system_command(cmd, rest, admin)
        if handled is not None:
            return handled
        if cmd == "false" and not rest:
            return Result(code=1)
        if cmd == "hostname" and not rest:
            return Result(self.hostname)
        if cmd == "history" and not rest:
            return Result("\n".join(f"{i}  {value}" for i, value in enumerate(self.progress["history"] + ["history"], 1)))
        if (cmd == "ls" and rest == ["--help"]) or (cmd == "man" and rest == ["ls"]):
            return Result("LS（訓練用の要約）\n使い方: ls [オプション] [場所]\n-a 隠しファイルも表示\n-l 権限やサイズを詳しく表示\n本物の man は q で閉じます。この模擬画面は自動で入力待ちに戻ります。")
        if cmd == "find" and len(rest) == 3 and rest[1] == "-name":
            base = self.path(rest[0])
            if not base.is_dir():
                raise TrainingError("find の検索開始場所はフォルダを指定しましょう。")
            found = []
            def visit(folder, depth=0):
                if depth > 12:
                    return
                for item in sorted(folder.iterdir()):
                    if item.is_symlink() or (not self.progress["remote"] and item == self.root / ".remote"):
                        continue
                    if fnmatch.fnmatch(item.name, rest[2]):
                        prefix = "./" if rest[0] == "." else rest[0].rstrip("/") + "/"
                        found.append(prefix + item.relative_to(base).as_posix())
                    if item.is_dir():
                        visit(item, depth + 1)
            visit(base)
            return Result("\n".join(found))
        if cmd in ("vim", "vi"):
            return self._vim(cmd, rest)
        if cmd in PACKAGES and rest == ["--version"]:
            if cmd not in self.progress["packages"]:
                return Result(f"Command '{cmd}' not found, but can be installed with:\nsudo apt install {cmd}", 127)
            return Result(f"{cmd} {PACKAGES[cmd][1]}（訓練用シミュレーター）")
        if cmd == "diff" and len(rest) == 2:
            old, new = (self.path(x).read_text(encoding="utf-8").splitlines() for x in rest)
            return Result(*textcmd.diff(rest[0], old, rest[1], new))
        if cmd == "which" and rest:
            found = []
            for name in rest:
                if name in BUILTIN_COMMANDS or commands.available(name, self.progress["packages"]) or name in self.progress["packages"] or (name == "vi" and "vim" in self.progress["packages"]):
                    found.append(f"/usr/bin/{name}")
            return Result("\n".join(found), 0 if len(found) == len(rest) else 1)
        if cmd == "ssh":
            return self._ssh(rest)
        if cmd == "scp":
            return self._scp(rest)
        if cmd == "exit" and not rest:
            if self.progress["remote"]:
                self.progress["remote"] = False
                return Result("Connection to training-server closed. dojo-local に戻りました（模擬）。")
            return Result("ここは手元の模擬端末です。menu で学習メニューへ戻れます。")
        if cmd == "sudo":
            if not rest:
                raise TrainingError("sudo の後ろに実行するコマンドをスペースで続けます。例: sudo whoami")
            if rest[0] not in ("whoami", "apt", "kill") and not commands.sudo_allowed(rest[0]):
                raise TrainingError("練習用 sudo は一部のコマンドにだけ使えます。実際の管理者権限は使いません。")
            return self._execute(rest, admin=True, stdin=stdin)
        if cmd == "echo":
            if rest == ["$?"]:
                return Result(str(self.progress["last_status"]))
            redirect = next((i for i, a in enumerate(rest) if shell_operator(a, (">", ">>"))), None)
            if redirect is not None:
                if len(rest) != redirect + 2:
                    raise TrainingError("保存先を1つ指定します。例: echo hello > note.txt")
                self._write_output(rest[-1], " ".join(rest[:redirect]) + "\n", rest[redirect] == ">>")
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
            self.set_cwd(dest.relative_to(self.active_root).as_posix())
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
                    if item.is_symlink() or (not self.progress["remote"] and item == self.root / ".remote"):
                        continue
                    if item.name.startswith(".") and "a" not in options:
                        continue
                    label = item.name + ("/" if item.is_dir() else "")
                    if "l" in options:
                        kind = stat.S_IFDIR if item.is_dir() else stat.S_IFREG
                        label = f"{stat.filemode(kind | self.mode_of(item))} learner {item.stat().st_size:>4} {label}"
                    output.append(label)
            return Result("\n".join(output))
        if cmd == "mkdir" and rest:
            parents = "-p" in rest
            for value in rest:
                if value == "-p":
                    continue
                if value.startswith("-"):
                    raise TrainingError("mkdir のオプションは -p が使えます。")
                path = self.path(value)
                missing = []
                current = path
                while not current.exists() and current != self.active_root:
                    missing.append(current)
                    current = current.parent
                path.mkdir(parents=parents, exist_ok=parents)
                for directory in reversed(missing):
                    self.created(directory, False, 0o777)
            return Result()
        if cmd == "touch" and rest:
            for value in rest:
                path = self.path(value)
                existed = path.exists()
                path.touch()
                self.created(path, existed)
            return Result()
        if cmd in ("cp", "mv") and len(rest) >= 2:
            if any(x.startswith("-") for x in rest):
                raise TrainingError(f"この練習の {cmd} はオプションなしで、ファイルをコピー・移動します。")
            *sources, target = rest
            target_path = self.path(target)
            if len(sources) > 1 and not target_path.is_dir():
                raise TrainingError(f"複数のファイルを {cmd} するときは、最後に送り先のフォルダを書きます。")
            for value in sources:
                source = self.path(value)
                if source.is_dir():
                    raise TrainingError("この練習ではフォルダではなく、ファイルをコピー・移動します。")
                dest = target_path
                if dest.is_dir():
                    dest = self.path("/home/learner/" + (dest / source.name).relative_to(self.active_root).as_posix())
                if cmd == "cp":
                    existed = dest.exists()
                    shutil.copyfile(source, dest)
                    # 新規の宛先は元の権限から umask を除く。既存の宛先の権限は変えない。
                    self.created(dest, existed, self.mode_of(source))
                else:
                    os.replace(source, dest)
                    self.move_mode(source, dest)
            return Result()
        if cmd == "rm" and rest:
            if any(x.startswith("-") and x not in ("-f", "--force", "--") for x in rest):
                raise TrainingError("この練習の rm はファイルのみ削除します。フォルダの再帰削除は扱いません。")
            force = "-f" in rest or "--force" in rest
            for value in rest:
                if value in ("-f", "--force", "--"):
                    continue
                target = self.path(value)
                target.unlink(missing_ok=force)
                self.forget_mode(target)
            return Result()
        if cmd == "chmod" and len(rest) >= 2:
            spec, *names = rest
            for name in names:
                path = self.path(name)
                self.set_mode(path, chmod_mode(spec, self.mode_of(path)))
            return Result()
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
        plugin = commands.lookup(cmd)
        if plugin is not None:
            result = plugin(self, rest, stdin=stdin, admin=admin)
            if result is not None:
                return result
        raise TrainingError(f"{cmd}: この模擬ターミナルでは未対応の入力です。スペルを確認し、hint で手がかりを見てみましょう。")

    def _text_command(self, cmd, rest, stdin):
        """パイプでも使うテキスト処理。対象外のコマンドなら None。"""
        if cmd not in READS_STDIN or (cmd == "cat" and not rest and stdin is None):
            return None
        if cmd == "cat":
            flags, _, files = textcmd.split_flags(rest, "n")
            text = self._read_input(cmd, files, stdin)
            lines = text.splitlines()
            if "n" in flags:
                return Result("\n".join(f"{i:>6}\t{x}" for i, x in enumerate(lines, 1)))
            return Result(text.rstrip("\n"))
        if cmd == "grep":
            flags, _, rest = textcmd.split_flags(rest, "ivcnE")
            if not rest:
                raise TrainingError("grep の後ろに探す文字を書きます。例: grep ERROR app.log")
            pattern, files = rest[0], rest[1:]
            if len(files) > 1:
                outputs, code = [], 1
                for name in files:
                    out, found = textcmd.grep(flags, pattern, self._read_input(cmd, [name], None).splitlines(), label=name)
                    if out:
                        outputs.append(out)
                    code = min(code, found)
                return Result("\n".join(outputs), code)
            out, code = textcmd.grep(flags, pattern, self._read_input(cmd, files, stdin).splitlines())
            return Result(out, code)
        if cmd in ("head", "tail"):
            count, from_start, files = textcmd.line_count(rest)
            out, code = textcmd.head_tail(cmd, count, self._read_input(cmd, files, stdin).splitlines(), from_start)
            return Result(out, code)
        if cmd == "wc":
            flags, _, files = textcmd.split_flags(rest, "lwc")
            if len(files) > 1:
                rows = [textcmd.wc(flags, self._read_input(cmd, [name], None), name)[0] for name in files]
                rows.append(textcmd.wc(flags, self._read_input(cmd, files, None), "total")[0])
                return Result("\n".join(rows))
            label = files[0] if len(files) == 1 else None
            out, code = textcmd.wc(flags, self._read_input(cmd, files, stdin), label)
            return Result(out, code)
        if cmd == "sort":
            flags, values, files = textcmd.split_flags(rest, "rnu", with_value="tk")
            return Result(*textcmd.sort(flags, self._read_input(cmd, files, stdin).splitlines(), values))
        if cmd == "uniq":
            flags, _, files = textcmd.split_flags(rest, "c")
            return Result(*textcmd.uniq(flags, self._read_input(cmd, files, stdin).splitlines()))
        flags, values, files = textcmd.split_flags(rest, "", with_value="df")
        return Result(*textcmd.cut(values, self._read_input(cmd, files, stdin).splitlines()))

    def _system_command(self, cmd, rest, admin):
        """環境変数・プロセス・ディスクの模擬。対象外のコマンドなら None。"""
        env = self.progress["env"]
        if cmd == "export":
            if not rest:
                return Result("\n".join(f'declare -x {k}="{v}"' for k, v in sorted(env.items())))
            for item in rest:
                name, sep, value = item.partition("=")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise TrainingError("変数名は英字・数字・_ で書きます。例: export GREETING=hello")
                env[name] = value if sep else self.progress["shell_vars"].get(name, env.get(name, ""))
                self.progress["shell_vars"].pop(name, None)
            return Result()
        if cmd == "unset" and rest:
            for name in rest:
                env.pop(name, None)
                self.progress["shell_vars"].pop(name, None)
            return Result()
        if cmd == "env" and not rest:
            return Result("\n".join(f"{k}={v}" for k, v in sorted(env.items())))
        if cmd == "printenv":
            if not rest:
                return Result("\n".join(f"{k}={v}" for k, v in sorted(env.items())))
            values = [env[name] for name in rest if name in env]
            return Result("\n".join(values), 0 if len(values) == len(rest) else 1)
        processes = self.progress["processes"]
        if cmd == "ps":
            if rest in (["aux"], ["-ef"], ["-e"], ["ax"]):
                rows = ["USER         PID %CPU %MEM COMMAND"]
                rows += [f"{p['user']:<10} {p['pid']:>5} {p['cpu']:>4.1f} {p['mem']:>4.1f} {p['cmd']}" for p in processes]
                rows.append(f"{'learner':<10} {9999:>5}  0.0  0.0 ps {' '.join(rest)}")
                return Result("\n".join(rows))
            if not rest:
                rows = ["    PID TTY          TIME CMD"]
                rows += [f"{p['pid']:>7} pts/0    00:00:00 {p['cmd'].split()[0].lstrip('-').rsplit('/', 1)[-1]}"
                         for p in processes if p["user"] == "learner"]
                rows.append(f"{9999:>7} pts/0    00:00:00 ps")
                return Result("\n".join(rows))
            raise TrainingError("この練習では ps（自分の端末）と ps aux（すべて）を使えます。")
        if cmd == "pgrep" and len(rest) == 1:
            pids = [str(p["pid"]) for p in processes if rest[0] in p["cmd"]]
            return Result("\n".join(pids), 0 if pids else 1)
        if cmd == "kill":
            return self._kill(rest, admin)
        if cmd == "df" and rest in (["-h"], []):
            return Result("Filesystem      Size  Used Avail Use% Mounted on\n"
                          "/dev/sda1        20G   17G  2.1G  90% /\n"
                          "tmpfs           1.0G     0  1.0G   0% /dev/shm\n"
                          "（訓練用の固定の表示です。実際の PC のディスクは調べていません）")
        if cmd == "free" and rest in (["-h"], []):
            return Result("               total        used        free      shared  buff/cache   available\n"
                          "Mem:           3.8Gi       1.2Gi       1.1Gi        12Mi       1.5Gi       2.4Gi\n"
                          "Swap:          1.0Gi          0B       1.0Gi\n"
                          "（訓練用の固定の表示です）")
        if cmd == "du":
            flags, _, targets = textcmd.split_flags(rest, "sh")
            rows = []
            for name in targets or ["."]:
                path = self.path(name)
                items = [path] if path.is_file() else [path] + [x for x in path.rglob("*") if not x.is_symlink()
                                                                and ".remote" not in x.relative_to(self.root).parts]
                # 本物の du と同じく、ファイルやフォルダは 4K 単位の「ブロック」で数える。
                size = sum(4096 * max(1, -(-x.stat().st_size // 4096)) if x.is_file() else 4096 for x in items)
                rows.append(f"{_human(size) if 'h' in flags else size // 1024}\t{name}")
            return Result("\n".join(rows))
        return None

    def _kill(self, rest, admin):
        signal = "TERM"
        if rest[:1] == ["-s"] and len(rest) > 1:
            signal, rest = rest[1].upper().replace("SIG", ""), rest[2:]
        elif rest and rest[0].startswith("-"):
            if rest[0] not in SIGNALS:
                raise TrainingError("この練習では kill PID（TERM）と kill -9 PID（KILL）を使えます。")
            signal, rest = SIGNALS[rest[0]], rest[1:]
        if not rest or not all(x.isdigit() for x in rest):
            raise TrainingError("kill の後ろに止めたいプロセスの番号（PID）を書きます。番号は ps で調べます。")
        messages, code = [], 0
        for value in rest:
            pid = int(value)
            target = next((p for p in self.progress["processes"] if p["pid"] == pid), None)
            if target is None:
                messages.append(f"bash: kill: ({pid}) - No such process（その番号のプロセスはありません）")
                code = 1
            elif pid in (1, SHELL_PID):
                messages.append(f"kill: ({pid}) - この練習では、システムの起点と自分の端末は止めません。")
                code = 1
            elif target["user"] != "learner" and not admin:
                messages.append(f"bash: kill: ({pid}) - Operation not permitted（ほかのユーザーのプロセスです）")
                code = 1
            elif signal == "TERM" and target.get("ignores_term"):
                continue  # 本物と同じく kill 自体は成功するが、プロセスは終了しない
            else:
                self.progress["processes"].remove(target)
        return Result("\n".join(messages), code)

    def _ssh(self, rest):
        if self.progress["remote"]:
            return Result("ここでは多段接続は扱いません。exit で手元へ戻ってから接続しましょう。", 255)
        port, identity, target = "22", None, None
        index = 0
        while index < len(rest):
            value = rest[index]
            if value in ("-p", "-i") and index + 1 < len(rest):
                if value == "-p":
                    port = rest[index + 1]
                else:
                    identity = rest[index + 1]
                index += 2
            elif not value.startswith("-") and target is None:
                target = value
                index += 1
            else:
                return Result("使い方: ssh [-p ポート] [-i 練習用の鍵] learner@training-server", 255)
        if target not in ("learner@training-server", "guest@training-server"):
            return Result("この教材では training-server のみ模擬接続できます。実サーバーへの通信は行いません。", 255)
        if port not in ("22", "2222"):
            return Result(f"ssh: connect to host training-server port {port}: Connection refused（模擬）", 255)
        if target.startswith("guest@"):
            return Result("guest@training-server: Permission denied (publickey). ユーザー名と登録した公開鍵を確認しましょう（模擬）。", 255)
        if identity:
            try:
                key = self.path(identity)
                if key.read_text(encoding="utf-8").strip() != "DUMMY-NOT-A-REAL-KEY":
                    return Result("この練習では DUMMY-NOT-A-REAL-KEY という教材用の無効な鍵だけを使います。実際の秘密鍵は入力・コピーしないでください。", 255)
                if self.mode_of(key) & 0o077:
                    return Result("WARNING: UNPROTECTED PRIVATE KEY FILE! 練習用の鍵を chmod 600 で自分だけが読めるようにしましょう。", 255)
            except (TrainingError, OSError):
                return Result("Identity file を読み取れません。鍵の名前と場所を確認しましょう（模擬）。", 255)
        if not self.progress["ssh_known"]:
            self.progress["ssh_pending"] = True
            return Result("The authenticity of host 'training-server' can't be established.\nED25519 key fingerprint is SHA256:TRAINING-NOT-A-REAL-FINGERPRINT\n管理者から別経路で得た指紋と比較し、一致を確認できた場合だけ yes、不明なら no。\nこれは段階学習用の模擬確認です。実際の鍵や接続は使用しません。")
        self.progress.update(remote=True, remote_cwd=".")
        return Result("learner@training-server に模擬接続しました。hostname で接続先を確かめましょう（実通信なし）。")

    def _side_path(self, value, remote):
        original_remote = self.progress["remote"]
        original_cwd = self.progress["remote_cwd"]
        try:
            self.progress["remote"] = remote
            if remote:
                self.progress["remote_cwd"] = "."
            return self.path(value)
        finally:
            self.progress["remote"] = original_remote
            self.progress["remote_cwd"] = original_cwd

    def _scp(self, rest):
        if self.progress["remote"]:
            return Result("この練習では exit で手元の端末に戻り、そこで scp を使います。", 255)
        if len(rest) == 4 and rest[0] == "-P":
            if rest[1] not in ("22", "2222"):
                return Result(f"ssh: connect to host training-server port {rest[1]}: Connection refused（模擬）", 255)
            rest = rest[2:]
        if len(rest) != 2 or not self.progress["ssh_known"]:
            return Result("scp は確認済みの training-server との転送だけを練習します。先に ssh で接続先の指紋を確認しましょう。", 255)
        source_text, dest_text = rest
        source_remote, dest_remote = ":" in source_text, ":" in dest_text
        if source_remote == dest_remote:
            return Result("転送元と転送先の一方だけに learner@training-server: を付けましょう。", 255)
        def split(value, remote):
            if remote:
                host, value = value.split(":", 1)
                if host != "learner@training-server" or not value:
                    raise TrainingError("この練習では learner@training-server のみ使えます。")
            return self._side_path(value, remote)
        try:
            source, dest = split(source_text, source_remote), split(dest_text, dest_remote)
            if not source.is_file():
                return Result("scp: 転送元ファイルがありません。手元とサーバーのどちらにあるか確認しましょう。", 1)
            if dest.is_dir():
                dest = self._side_path((dest_text.split(":", 1)[-1].rstrip("/") + "/" + source.name), dest_remote)
            existed = dest.exists()
            shutil.copyfile(source, dest)
            self.created(dest, existed, self.mode_of(source))
        except (TrainingError, OSError):
            return Result("scp: 転送先の場所と権限を確認しましょう。練習用ホームの外やリンクへは転送できません。", 1)
        return Result("転送しました（模擬）。元のファイルは残ります。実通信は行いません。")

    def _apt(self, rest, admin):
        rest = [arg for arg in rest if arg not in ("-y", "--yes")]
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
            return Result("\n".join(f"{name} - {desc}" for name, (desc, _) in PACKAGES.items() if rest[1] in name or rest[1] in desc))
        if action == "show" and len(rest) == 2 and rest[1] in PACKAGES:
            name = rest[1]
            desc, version = PACKAGES[name]
            return Result(f"Package: {name}\nVersion: {version}\n説明: {desc}")
        names = [x for x in rest[1:] if x != "-y"]
        if action in ("install", "remove") and names and all(x in PACKAGES for x in names) and len(set(names)) == len(names):
            if action == "install":
                if not self.progress["apt_updated"]:
                    return Result("先に sudo apt update で一覧を更新しましょう（模擬）。", 100)
                for name in names:
                    if name not in self.progress["packages"]:
                        self.progress["packages"].append(name)
                return Result(f"{' '.join(names)} を追加しました（模擬）。実際の PC にはインストールしていません。")
            for name in names:
                if name in self.progress["packages"]:
                    self.progress["packages"].remove(name)
            return Result(f"{' '.join(names)} を削除しました（模擬）。")
        if action in ("install", "remove", "show") and names:
            unknown = next((x for x in names if x not in PACKAGES), names[0])
            return Result(f"E: Unable to locate package {unknown}（この練習で扱えるのは {' / '.join(PACKAGES)} です）", 100)
        raise TrainingError("対応する例: apt search vim / apt show vim / sudo apt update / sudo apt install vim / sudo apt remove vim")


class ShellWord(str):
    """A shell argument with quoting information retained for wildcard expansion."""
    def __new__(cls, value, pattern, has_glob):
        word = super().__new__(cls, value)
        word.glob_pattern, word.has_glob = pattern, has_glob
        return word


def shell_operator(word, allowed=("<", ">", ">>", "<<", "|", "||", "&&", ";", "&", "2>")):
    return not isinstance(word, ShellWord) and word in allowed


def shell_words(line):
    """Split a training shell line, distinguishing quoted literals from operators."""
    words, value, pattern = [], [], []
    quote, started, has_glob, index = None, False, False, 0

    def flush():
        nonlocal value, pattern, started, has_glob
        if started:
            words.append(ShellWord("".join(value), "".join(pattern), has_glob))
        value, pattern, started, has_glob = [], [], False, False

    def literal(char):
        value.append(char)
        pattern.append({"*": "[*]", "?": "[?]", "[": "[[]"}.get(char, char))

    while index < len(line):
        char = line[index]
        if char == "\\" and quote != "'":
            if index + 1 == len(line):
                raise TrainingError("バックスラッシュの後ろに文字が必要です。")
            following = line[index + 1]
            if quote == '"' and following not in '$`"\\\n':
                literal(char)
                index += 1
                continue
            literal(following)
            started = True
            index += 2
            continue
        if char in "'\"" and quote in (None, char):
            quote = None if quote == char else char
            started = True
            index += 1
            continue
        if quote is None and char.isspace():
            flush()
        elif quote is None and char in "<>|;&":
            # 2> is a descriptor redirect only when the 2 is unquoted and stands alone.
            descriptor = char == ">" and value == ["2"] and pattern == ["2"]
            if descriptor:
                value, pattern, started, has_glob = [], [], False, False
            flush()
            operator = ("2" if descriptor else "") + char
            if index + 1 < len(line) and line[index + 1] == char:
                operator += char
                index += 1
            words.append(operator)
        else:
            started = True
            if quote:
                literal(char)
            else:
                value.append(char)
                pattern.append(char)
                has_glob = has_glob or char in GLOB_CHARS
        index += 1
    if quote:
        raise TrainingError("引用符を閉じてください。")
    flush()
    return words


def split_pipes(line):
    """引用符の外にある | で区切る。'a|b' のように引用符の中の | は文字として残す。"""
    segments, current, quote, index = [], [], None, 0
    while index < len(line):
        char = line[index]
        if char == "\\" and quote != "'" and index + 1 < len(line):
            current.append(line[index:index + 2])
            index += 2
            continue
        if char in "'\"" and quote in (None, char):
            quote = None if quote == char else char
        elif char == "|" and quote is None:
            if line[index + 1:index + 2] == "|":
                raise TrainingError("|| でつなぐ書き方はここでは扱いません。1つずつ入力しましょう。")
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return segments


_WHO = {"u": 0o700, "g": 0o070, "o": 0o007}
_PERM = {"r": 0o444, "w": 0o222, "x": 0o111}


def chmod_mode(spec, current):
    """chmod の指定（644 / u+x / go-rw / a=r,u+w など）から新しい権限を計算する。"""
    if re.fullmatch(r"0?[0-7]{3}", spec):
        return int(spec, 8)
    mode = current
    for part in spec.split(","):
        match = re.fullmatch(r"([ugoa]*)([+\-=])([rwx]*)", part)
        if not match:
            raise TrainingError("chmod は 644 のような3桁の数字か、u+x・go-w・a=r のような記号で指定します。")
        who, op, perms = match.groups()
        # 本物では u/g/o を省略すると umask の影響を受ける。この練習では a（全員）として扱う。
        mask = sum(_WHO[w] for w in set(who.replace("a", "ugo") or "ugo"))
        bits = sum(_PERM[x] for x in set(perms)) & mask
        if op == "+":
            mode |= bits
        elif op == "-":
            mode &= ~bits
        else:
            mode = (mode & ~mask) | bits
    return mode


def _human(size):
    """du -h に近い表示。本物と同じく最小単位は K。"""
    size = max(size, 1) / 1024
    for unit in ("K", "M", "G"):
        if size < 1024 or unit == "G":
            return f"{size:.1f}{unit}" if size < 10 else f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.0f}G"


def lessons(mode):
    from curriculum.beginner_lessons import LESSONS
    return LESSONS[mode]


def selected_mode():
    mode = save.load()["learning"]["mode"]
    if mode == "practice" and not runner.practice_supported():
        # 保存されたモードは変えず、この環境で使える段階へ案内する。
        return next((m for m in GUIDED_MODES if not completed_course(m)), "advanced")
    return mode


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
    step = next((s for s in course if s["id"] == cursor), course[0])
    if not progress.get("reviewing") and step["id"] in progress.get("completed", []):
        index = course.index(step)
        return next((s for s in course[index + 1:] if s["id"] not in progress.get("completed", [])), step)
    return step


def completed_course(mode, progress=None):
    progress = progress if progress is not None else progress_for(mode)
    return {step["id"] for step in lessons(mode)} <= set(progress.get("completed", []))


def answers(step):
    """正解として受け付ける入力例（最初が代表例）。"""
    return [step["command"], *step.get("accept", [])]


def matches(line, step):
    try:
        typed = shlex.split(line)
        return any(typed == shlex.split(answer) for answer in answers(step))
    except ValueError:
        return False


def hint_text(step, level):
    """ヒントを段階的に返す。level は 0 から。課題に hints があればそれを使い、なければ自動で作る。

    1段階目は考え方、2段階目は使う道具、3段階目は入力例（答え）。
    """
    hints = step.get("hints")
    if hints is None:
        words = shlex.split(step["command"]) if step["command"] else []
        head = words[0] if words else ""
        hints = ["「やってみよう」をもう一度読みましょう。何を実現したいか → どの道具（コマンド）が合うか、の順に考えます。"
                 "lesson で説明を読み直せます。",
                 f"使う道具は「{head}」です。{len(words)} 個の言葉（道具の名前と、その対象や指定）を並べます。",
                 "入力例: " + step["command"]]
    return hints[min(level, len(hints) - 1)], min(level, len(hints) - 1) == len(hints) - 1


def expected_code(step):
    return step.get("expected_code", 100 if step["command"] == "apt update" else 0)


def accepted(line, result, step, terminal):
    """課題を達成したか。goal がある課題は、書き方ではなく結果の状態で判定する。"""
    if result.code != expected_code(step):
        return False
    if step.get("goal") is None:
        return matches(line, step)
    return goal_met(step, terminal)


def goal_met(step, terminal):
    try:
        return bool(step["goal"](terminal))
    except (TrainingError, OSError, KeyError, TypeError, IndexError):
        return False


def prepare_step(terminal, step, fresh=False):
    """課題の初期状態を用意する。

    editor に continue がある課題は、前の課題から続けて開いている vim の画面（学習者が書いた文）を
    引き継ぐ。reset（fresh=True）では必ず用意し直す。
    """
    for key in ("remote", "ssh_known", "ssh_pending", "last_status"):
        if key in step:
            terminal.progress[key] = step[key]
    if "remote_files" in step:
        original_remote = terminal.progress["remote"]
        terminal.progress["remote"] = True
        try:
            for name, content in step["remote_files"].items():
                terminal.restore_file("/home/learner/" + name, content)
        finally:
            terminal.progress["remote"] = original_remote
    # 各課題は教材用の初期ファイルを復元する。学習者の本来のファイルには触れない。
    for name, content in {"welcome.txt": "LinuxDOJOへようこそ！\n", ".memo": "見つけました！\n"}.items():
        terminal.restore_file("/home/learner/" + name, content)
    if "cwd" in step:
        target = terminal.path("/home/learner/" + step["cwd"].lstrip("/"))
        terminal.ensure_directory(target)
        terminal.set_cwd(target.relative_to(terminal.active_root).as_posix())
    for name in step.get("remove", []):
        target = terminal.path(name)
        if target == terminal.active_root or target in terminal.path(".").parents or target == terminal.path("."):
            raise TrainingError("課題の開始場所や練習のルートは削除できません。")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        terminal.forget_mode(target)
    for name in step.get("dirs", []):
        terminal.ensure_directory(terminal.path(name))
    # 環境変数とプロセスは課題ごとに用意し直す（前の課題で止めたプロセスなどを持ち越さない）。
    terminal.progress["env"] = {**DEFAULT_ENV, **step.get("env", {})}
    terminal.progress["shell_vars"] = {}
    terminal.progress["processes"] = [dict(p) for p in DEFAULT_PROCESSES + step.get("processes", [])]
    if "packages" in step:
        terminal.progress["packages"] = list(step["packages"])
    if "apt_updated" in step:
        terminal.progress["apt_updated"] = step["apt_updated"]
    for name, content in step.get("files", {}).items():
        terminal.restore_file(name, content)
    for name, mode in step.get("modes", {}).items():
        terminal.set_mode(terminal.path(name), mode)
    commands.prepare(terminal, step)
    # 前の課題で学習者が作ったファイルを使う課題。なければ代わりの内容を用意する。
    for name, content in step.get("initial_files", {}).items():
        if not terminal.path(name).is_file():
            terminal.restore_file(name, content)
    preset = step.get("editor")
    current = terminal.progress.get("editor")
    if preset is None:
        terminal.progress["editor"] = None
    elif (fresh or not preset.get("continue") or not current or current["name"] != preset["file"]
          or current["mode"] != preset.get("mode", "normal") or ("goal" in step and goal_met(step, terminal))):
        # 続きの画面でも、この課題の目的がもう済んでいるなら（復習のやり直しなど）最初から用意する。
        state = {k: v for k, v in preset.items() if k not in ("file", "lines", "continue")}
        if state.get("mode") == "insert":
            state.setdefault("insert_at", len(preset.get("lines", [])))
        terminal.open_editor(preset["file"], lines=preset.get("lines"), **state)


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
        print(ui.box([f"{MODE_NAMES[mode]}  {index + 1}/{len(course)}  {step['title']}",
                      *([f"ユニット: {step['unit']}"] if step.get("unit") else []), "",
                      *step["explanation"].splitlines(), "", "やってみよう: " + step["task"]], color="green"))
        if mode == "intro" and index < INTRO_SHOWN_ANSWERS:
            print("\n  入力するコマンド: " + ui.c(step["command"], "bcyan"))
        elif mode == "intro":
            print("\n  答えは書いてありません。まず自分で考えて入力してみましょう。")
        print("\n  訓練用の模擬ターミナルです。実際の sudo・apt・シェルは実行しません。")
        print("  hint: ヒントを1段階ずつ表示 / answer: 答えを見る / lesson: 説明を再表示 / reset: この課題を復元 / menu: 保存して戻る")
        hint_level = 0
        if terminal.progress.get("editor"):
            print("\n" + vim_sim.render(terminal.progress["editor"]))
        while True:
            try:
                raw = input("\n " + terminal.prompt_text())
            except (EOFError, KeyboardInterrupt):
                remember(mode, progress)
                return
            line = raw.strip()
            in_editor = bool(terminal.progress.get("editor"))
            if line == "menu" or (not in_editor and (line == "quit" or (line == "exit" and not terminal.progress["remote"]))):
                remember(mode, progress)
                return
            if line == "hint" or (not in_editor and line == "help"):
                text, last = hint_text(step, hint_level)
                print(f"  💡 ヒント {hint_level + 1}: {text}")
                print("  （もう一度 hint で次のヒント）" if not last else "  （これが最後のヒントです）")
                hint_level += 1
                continue
            if not in_editor and line == "answer":
                print("  入力例: " + " / ".join(answers(step)[:3]))
                print("  見ても減点はありません。答えを見たら、何も見ずにもう一度打ってみましょう。")
                continue
            if line == "lesson" or (not in_editor and line == "mission"):
                print(step["explanation"] + "\nやってみよう: " + step["task"])
                continue
            if line == "reset":
                prepare_step(terminal, step, fresh=True)
                print("課題のファイルと開始場所を復元しました。もう一度試せます。")
                continue
            # vim の入力モードでは先頭の空白も文字として残す。
            result = terminal.execute(raw.rstrip("\r") if in_editor else line)
            if result.output:
                print(result.output)
            remember(mode, progress)
            if not accepted(line, result, step, terminal):
                if result.code == 0 and not in_editor:
                    print("  実行できました。今回の課題も試しましょう。hint で入力例を見られます。")
                continue
            print(ui.c("\n  ✓ できました！ " + step["success"], "bgreen"))
            others = [answer for answer in answers(step) if not matches(line, {"command": answer})]
            if others:
                print("  ほかの書き方でも正解です: " + " / ".join(others))
            completed = progress.setdefault("completed", [])
            if step["id"] not in completed:
                completed.append(step["id"])
            index += 1
            progress["cursor"] = course[index]["id"] if index < len(course) else step["id"]
            if index == len(course):
                progress["reviewing"] = False
            remember(mode, progress)
            d = save.load()
            reward = save.record_activity(d, mode + ":" + step["id"])
            save.store(d)
            if reward["earned"]:
                print(ui.c(f"  +{reward['earned']} XP！", "byellow"))
            print("  " + save.activity_line(d))
            try:
                choice = input("\n  Enter: 次の練習へ / menu: 保存して戻る > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if choice in ("menu", "q", "exit"):
                return
            break
    print(ui.box([f"{MODE_NAMES[mode]}を最後まで学習しました！", "何度でもレッスン選択から復習できます。",
                  "はじめて → 基礎練習 → 応用練習 → 達人 → 実践 の順に進めます。", "総合復習の「課題まつり」で、手本なしの力試しもできます。", "メインメニューの [7] モード選択で切り替えましょう。"], color="green"))
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
        unit = None
        for index, step in enumerate(course, 1):
            if step.get("unit") and step["unit"] != unit:
                unit = step["unit"]
                members = [s["id"] for s in course if s.get("unit") == unit]
                done = len(set(members) & set(progress.get("completed", [])))
                print(ui.c(f"\n  ■ {unit}  {done}/{len(members)}", "bold", "bcyan"))
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
