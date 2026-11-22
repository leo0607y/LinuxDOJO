"""基礎・応用レッスンは、途中から再開しても答えを組み立てられること。

調べても分からないもの（ユーザー名@接続先、ポート番号、保存先として自分で決める名前）は、
課題文・説明文・題名のどれかに書く。
一方、既に存在するファイルやフォルダの名前・場所は、ls や ls -a など既習の道具で見つけられるので、
課題文に書かなくてよい（書いてしまうと、道具を使う練習の機会を奪う）。
"""
import re
import shlex
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curriculum import beginner_lessons as bl  # noqa: E402

HOST = re.compile(r"^[\w.-]+@[\w.-]+")
FILE = re.compile(r"^[A-Za-z][\w-]*\.[A-Za-z]{2,4}$")


def lessons():
    seen = set()
    for name in ("BASIC", "INTRO", "ADVANCED"):
        for item in getattr(bl, name):
            if item["id"] not in seen:
                seen.add(item["id"])
                yield item


class LessonSelfContained(unittest.TestCase):
    def test_names_in_answer_are_stated(self):
        problems = []
        for item in lessons():
            text = item["task"] + item["explanation"] + item["title"]
            try:
                tokens = shlex.split(item["command"])
            except ValueError:
                tokens = item["command"].split()
            for index, token in enumerate(tokens):
                if token.startswith("-") or "*" in token:
                    continue
                if HOST.match(token):
                    host = token.split("@", 1)[1].split(":", 1)[0]
                    user = token.split("@", 1)[0]
                    if host not in text or user not in text:
                        problems.append((item["id"], token))
                elif FILE.match(token) and index > 0 and tokens[index - 1] in (">", ">>", "-o") and token not in text:
                    problems.append((item["id"], token))
            for flag, value in zip(tokens, tokens[1:]):
                if flag in ("-p", "-P") and value.isdigit() and value not in text:
                    problems.append((item["id"], flag + " " + value))
        self.assertEqual(problems, [], "課題文に書かれていない名前があります")


if __name__ == "__main__":
    unittest.main()
