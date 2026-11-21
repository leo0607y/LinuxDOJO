"""模擬ターミナルの追加コマンド。1つのテーマを1ファイルにまとめ、この中で登録する。

使い方（engine/commands/archive.py など）:

    from engine.commands import command, on_prepare, on_check, register_package
    from engine.guided import Result, TrainingError

    @command("tar", sudo=False)
    def tar(terminal, rest, stdin=None, admin=False):
        ...                     # Result を返す。対応しない書式なら None（「未対応」と表示）
        return Result("...", 0)

    @on_prepare
    def prepare(terminal, step):    # レッスン・課題の初期状態。step は課題の辞書
        terminal.progress["archive"] = ...

    @on_check
    def check(scenario, terminal):  # 課題まつりの追加判定。問題があれば (False, "説明") を返す
        return None

    register_package("dnsutils", "dig や nslookup を使えるようにする", "9.18-training")

- ファイルは必ず terminal.path("名前") で解決する（練習フォルダの外に出ない）。
- 状態は terminal.progress["テーマ名"] に保存する（JSON にできる値だけ）。
- 実際の PC のコマンド・通信・プロセスは使わない（subprocess / socket / os.kill 禁止）。
- "./script.sh" のような「パスでの実行」は名前 "__path__" で登録する。
- 組み込みのコマンドが処理しなかった書式（例: find -size）もここへ回ってくる。
"""
import importlib
import pkgutil

_COMMANDS = {}
_SUDO = set()
_PREPARE = []
_CHECKS = []
_PACKAGES = {}
_loaded = False
_COMMAND_PACKAGES = {"git": "git", "curl": "curl", "wget": "wget", "dig": "dnsutils",
                     "nslookup": "dnsutils", "traceroute": "traceroute", "htop": "htop"}


def command(name, sudo=False):
    def register(function):
        previous = _COMMANDS.get(name)
        if previous is None:
            _COMMANDS[name] = function
        else:
            # getent など、複数分野の書式を持つコマンドは未対応時だけ前の担当へ渡す。
            def dispatch(*args, **kwargs):
                result = function(*args, **kwargs)
                return previous(*args, **kwargs) if result is None else result
            _COMMANDS[name] = dispatch
        if sudo:
            _SUDO.add(name)
        return function
    return register


def on_prepare(function):
    _PREPARE.append(function)
    return function


def on_check(function):
    _CHECKS.append(function)
    return function


def register_package(name, description, version):
    _PACKAGES[name] = (description, version)


def load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if not info.name.startswith("_"):
            importlib.import_module(f"{__name__}.{info.name}")
    from engine import guided
    for name, value in _PACKAGES.items():
        guided.PACKAGES.setdefault(name, value)


def lookup(name):
    load()
    if "/" in name and name not in _COMMANDS:
        return _COMMANDS.get("__path__")
    return _COMMANDS.get(name)


def names():
    load()
    return [n for n in _COMMANDS if not n.startswith("__")]


def available(name, packages):
    load()
    return name in _COMMANDS and (_COMMAND_PACKAGES.get(name) is None
                                  or _COMMAND_PACKAGES[name] in packages)


def sudo_allowed(name):
    load()
    return name in _SUDO


def prepare(terminal, step):
    load()
    for function in _PREPARE:
        function(terminal, step)


def check(scenario, terminal):
    load()
    for function in _CHECKS:
        problem = function(scenario, terminal)
        if problem:
            return problem
    return None
