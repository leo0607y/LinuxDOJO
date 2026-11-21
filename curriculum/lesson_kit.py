"""教材データを書くための部品。lesson() と、結果の状態で判定する goal の部品。

goal の引数は engine.guided.Terminal。
"""


def lesson(key, title, explanation, task, command, success, **extra):
    """command は代表的な入力例。accept に別の正解例、goal に結果の判定を書ける。

    goal がある課題は、書き方ではなく「目的の状態になったか」で判定する。
    """
    return dict(id=key, title=title, explanation=explanation, task=task,
                command=command, success=success, **extra)


# ---- 結果の状態で判定するための小さな部品（引数は guided.Terminal）
def is_dir(name):
    return lambda t: t.path(name).is_dir()


def is_file(name):
    return lambda t: t.path(name).is_file()


def absent(name):
    return lambda t: not t.path(name).exists()


def content(name, text):
    return lambda t: t.path(name).read_text(encoding="utf-8") == text


def cwd_is(value):
    return lambda t: t.cwd == value


def executable(name):
    return lambda t: bool(t.mode_of(t.path(name)) & 0o100)


def has_package(name):
    return lambda t: name in t.progress["packages"]


def editor(predicate=lambda e: True):
    return lambda t: bool(t.progress.get("editor")) and predicate(t.progress["editor"])


def editor_closed(t):
    return not t.progress.get("editor")


def all_of(*goals):
    return lambda t: all(goal(t) for goal in goals)


LS_VIEW = ["ls -a", "ls -l", "ls -la", "ls -al", "ls ."]
