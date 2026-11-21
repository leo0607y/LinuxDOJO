"""Small, explicit printf subset for authoring scripts without running a shell.

The supported format is %s\\n. The format is repeated for all arguments,
as with the real printf command. Source text is always treated as data.
"""
from engine.commands import command
from engine.guided import Result, TrainingError


@command("printf")
def printf(terminal, rest, stdin=None, admin=False):
    if not rest:
        raise TrainingError("printf の後ろに書式と表示する値を書きます。例: printf '%s\\n' hello")
    format_string, *values = rest
    if format_string != "%s\\n":
        raise TrainingError("この模擬ターミナルの printf は書式 %s\\n に対応します。"
                            "表示する本文は書式と分けて引数に渡してください。")
    separator = "\n"
    output = "".join(value + separator for value in (values or [""]))
    # Training command outputs omit one terminal newline; redirect/pipeline handling restores it.
    if output.endswith("\n"):
        output = output[:-1]
    return Result(output)
