"""システム情報のコマンド（uname / date / uptime / id）。見本を兼ねた小さな追加コマンド。"""
from engine.commands import command
from engine.guided import Result

# 実際の PC の情報は読まず、練習用の固定値を返す。
_NOW = "2026-01-15 09:30:00"


@command("uname")
def uname(terminal, rest, stdin=None, admin=False):
    if rest == []:
        return Result("Linux")
    if rest == ["-a"]:
        return Result(f"Linux {terminal.hostname} 6.8.0-training #1 SMP x86_64 GNU/Linux")
    if rest == ["-r"]:
        return Result("6.8.0-training")
    return None


@command("date")
def date(terminal, rest, stdin=None, admin=False):
    if rest == []:
        return Result("Thu Jan 15 09:30:00 JST 2026")
    if rest == ["+%Y-%m-%d"]:
        return Result(_NOW.split()[0])
    return None


@command("uptime")
def uptime(terminal, rest, stdin=None, admin=False):
    return Result(" 09:30:00 up 3 days,  2:14,  1 user,  load average: 0.08, 0.03, 0.01") if rest in ([], ["-p"]) else None


@command("id")
def user_id(terminal, rest, stdin=None, admin=False):
    if rest == []:
        return Result("uid=1000(learner) gid=1000(learner) groups=1000(learner),27(sudo)")
    if rest == ["-un"]:
        return Result("learner")
    return None
