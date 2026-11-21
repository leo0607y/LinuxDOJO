"""テキスト加工のコマンド（awk / sed / tr / xargs / tee / paste / join / nl / rev / tac / column）。

どれもパイプ（前のコマンドの結果）とファイルの両方から読める。実際の PC は操作せず、練習フォルダの中だけを使う。
対応しない書式は None を返し、「未対応」と表示される。
"""
import re

from engine.commands import command
from engine.guided import Result, TrainingError


def _read(terminal, cmd, files, stdin):
    """入力を (行のリスト) で返す。ファイルがあればファイル、なければパイプの入力。"""
    texts = []
    for name in files:
        if name == "-" and stdin is not None:
            texts.append(stdin + "\n" if stdin else "")
            continue
        try:
            texts.append(terminal.path(name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise TrainingError(f"{cmd}: {name}: そのようなファイルはありません。ls で名前を確認しましょう。")
        except IsADirectoryError:
            raise TrainingError(f"{cmd}: {name}: これはフォルダです。")
    if not files:
        if stdin is None:
            raise TrainingError(f"{cmd} の後ろにファイル名を書くか、| で前のコマンドの結果を渡します。")
        texts.append(stdin + "\n" if stdin else "")
    return "".join(texts).splitlines()


def _out(lines, code=0):
    return Result("\n".join(lines), code)


def _split_options(args, valued=""):
    """'-x' 形式の短いオプションを分ける。値をとる文字は valued に書く。戻り値は (オプション辞書, 残り)。"""
    options, rest, index = {}, [], 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            rest.extend(args[index + 1:])
            break
        if arg.startswith("-") and len(arg) > 1 and (not arg[1:].isdigit() or arg[1] in valued):
            body, position = arg[1:], 0
            while position < len(body):
                letter = body[position]
                if letter in valued:
                    value = body[position + 1:]
                    if not value:
                        index += 1
                        if index >= len(args):
                            raise TrainingError(f"-{letter} の後ろに値を書きます。")
                        value = args[index]
                    options[letter] = value
                    break
                options[letter] = True
                position += 1
        else:
            rest.append(arg)
        index += 1
    return options, rest


# ---------------------------------------------------------------- nl / rev / tac / tee / paste / column / join
@command("rev")
def rev(terminal, rest, stdin=None, admin=False):
    if any(a.startswith("-") for a in rest):
        return None
    return _out([line[::-1] for line in _read(terminal, "rev", rest, stdin)])


@command("tac")
def tac(terminal, rest, stdin=None, admin=False):
    if any(a.startswith("-") for a in rest):
        return None
    return _out(_read(terminal, "tac", rest, stdin)[::-1])


@command("nl")
def nl(terminal, rest, stdin=None, admin=False):
    try:
        options, files = _split_options(rest, "b")
    except TrainingError:
        raise
    if set(options) - {"b"} or options.get("b", "t") not in ("t", "a"):
        return None
    number_all = options.get("b") == "a"
    lines, count, out = _read(terminal, "nl", files, stdin), 0, []
    for line in lines:
        if line or number_all:
            count += 1
            out.append(f"{count:>6}\t{line}")
        else:
            out.append(" " * 7)
    return _out(out)


@command("tee")
def tee(terminal, rest, stdin=None, admin=False):
    options, files = _split_options(rest)
    if set(options) - {"a"}:
        return None
    if stdin is None:
        raise TrainingError("tee は | で前のコマンドの結果を受け取り、画面とファイルの両方に出します。")
    if not files:
        return Result(stdin)
    text = stdin + "\n" if stdin else ""
    for name in files:
        terminal._write_output(name, text, bool(options.get("a")))
    return Result(stdin)


@command("paste")
def paste(terminal, rest, stdin=None, admin=False):
    options, files = _split_options(rest, "d")
    if set(options) - {"d", "s"} or not files:
        return None
    delimiter = str(options.get("d", "\t")).replace("\\t", "\t")
    columns = [_read(terminal, "paste", [name], stdin) for name in files]
    if options.get("s"):
        return _out([delimiter.join(column) for column in columns])
    height = max(len(column) for column in columns)
    return _out([delimiter.join(column[i] if i < len(column) else "" for column in columns) for i in range(height)])


@command("column")
def column(terminal, rest, stdin=None, admin=False):
    options, files = _split_options(rest, "s")
    if set(options) - {"t", "s"} or "t" not in options:
        return None
    separator = options.get("s")
    rows = [line.split(separator) if separator else line.split() for line in _read(terminal, "column", files, stdin)]
    widths = [0] * max((len(r) for r in rows), default=0)
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    return _out(["  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip() for row in rows])


@command("join")
def join(terminal, rest, stdin=None, admin=False):
    options, files = _split_options(rest, "t12")
    if set(options) - {"t", "1", "2"} or len(files) != 2:
        return None
    try:
        key1, key2 = int(options.get("1", 1)) - 1, int(options.get("2", 1)) - 1
    except ValueError:
        raise TrainingError("-1 / -2 の後ろには列の番号を書きます。")
    separator = options.get("t")

    def table(name, key):
        rows = {}
        for line in _read(terminal, "join", [name], stdin):
            fields = line.split(separator) if separator else line.split()
            if key < len(fields):
                rows.setdefault(fields[key], []).append(fields[:key] + fields[key + 1:])
        return rows

    left, right = table(files[0], key1), table(files[1], key2)
    glue = separator or " "
    out = [glue.join([key, *a, *b]) for key in left if key in right for a in left[key] for b in right[key]]
    return _out(out)


# ---------------------------------------------------------------- tr
_CLASSES = {"upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "lower": "abcdefghijklmnopqrstuvwxyz",
            "digit": "0123456789", "space": " \t\n\r\f\v", "blank": " \t", "punct": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"}
_CLASSES["alpha"] = _CLASSES["upper"] + _CLASSES["lower"]
_CLASSES["alnum"] = _CLASSES["alpha"] + _CLASSES["digit"]


def _expand_set(text):
    chars, index = [], 0
    while index < len(text):
        if text.startswith("[:", index) and ":]" in text[index:]:
            end = text.index(":]", index)
            name = text[index + 2:end]
            if name not in _CLASSES:
                raise TrainingError(f"tr: 不明な文字クラス [:{name}:] です。")
            chars.extend(_CLASSES[name])
            index = end + 2
            continue
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            char = {"n": "\n", "t": "\t", "\\": "\\", "r": "\r"}.get(text[index + 1], text[index + 1])
            index += 1
        if index + 2 < len(text) and text[index + 1] == "-":
            end_char = text[index + 2]
            if ord(end_char) < ord(char):
                raise TrainingError("tr: 範囲の終わりが始まりより前になっています（例: a-z）。")
            chars.extend(chr(c) for c in range(ord(char), ord(end_char) + 1))
            index += 3
            continue
        chars.append(char)
        index += 1
    return chars


@command("tr")
def tr(terminal, rest, stdin=None, admin=False):
    options, sets = _split_options(rest)
    if set(options) - {"d", "s", "c"}:
        return None
    if stdin is None:
        raise TrainingError("tr はファイルを直接読めません。cat ファイル | tr ... のように、| で渡します。")
    delete, squeeze, complement = options.get("d"), options.get("s"), options.get("c")
    if delete and not squeeze and len(sets) != 1 or (not delete and not sets) or len(sets) > 2:
        raise TrainingError("tr の書式: tr 変換前 変換後 / tr -d 消す文字 / tr -s 詰める文字")
    first = _expand_set(sets[0])
    text = stdin + "\n" if stdin else ""
    if complement:
        members = set(first)
        first_test = lambda ch: ch not in members  # noqa: E731
    else:
        first_test = set(first).__contains__
    if delete:
        text = "".join(ch for ch in text if not first_test(ch))
        if squeeze and len(sets) == 2:
            squeezed = set(_expand_set(sets[1]))
            text = _squeeze(text, squeezed.__contains__)
    elif len(sets) == 2:
        second = _expand_set(sets[1])
        if not second:
            raise TrainingError("tr: 変換後の文字が空です。")
        if complement:
            text = "".join(second[-1] if first_test(ch) else ch for ch in text)
            squeezed_test = set(second).__contains__
        else:
            second += [second[-1]] * (len(first) - len(second))
            mapping = {}
            for a, b in zip(first, second):
                mapping.setdefault(a, b)
            text = "".join(mapping.get(ch, ch) for ch in text)
            squeezed_test = set(second).__contains__
        if squeeze:
            text = _squeeze(text, squeezed_test)
    elif squeeze:
        text = _squeeze(text, first_test)
    else:
        raise TrainingError("tr: 変換後の文字（2つ目の指定）が必要です。")
    return Result(text[:-1] if text.endswith("\n") else text)


def _squeeze(text, test):
    out = []
    for ch in text:
        if out and out[-1] == ch and test(ch):
            continue
        out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------- xargs
@command("xargs")
def xargs(terminal, rest, stdin=None, admin=False):
    split = next((i for i, a in enumerate(rest) if not a.startswith("-")), len(rest))
    while split < len(rest) and split > 0 and rest[split - 1] in ("-n", "-I"):
        split += 1  # -n 1 のように値が別の語のとき、値は xargs 自身のオプション
        split = next((i for i in range(split, len(rest)) if not rest[i].startswith("-")), len(rest))
    options, _ = _split_options(rest[:split], "nI")
    args = rest[split:]
    if set(options) - {"n", "I", "r"}:
        return None
    if stdin is None:
        raise TrainingError("xargs は | で前のコマンドの結果を受け取り、それを引数にしてコマンドを実行します。")
    base = args or ["echo"]
    if base[0] in ("xargs", "sudo", "ssh", "scp"):
        raise TrainingError("この練習では xargs から xargs / sudo / ssh は使えません。")
    tokens = stdin.split()
    if "I" in options:
        placeholder = options["I"]
        batches = [[arg.replace(placeholder, line.strip()) for arg in base] for line in stdin.splitlines() if line.strip()]
    elif "n" in options:
        try:
            size = int(options["n"])
        except ValueError:
            raise TrainingError("-n の後ろには、1回に渡す個数（数字）を書きます。")
        if size < 1:
            raise TrainingError("-n は 1 以上にします。")
        batches = [base + tokens[i:i + size] for i in range(0, len(tokens), size)]
    else:
        batches = [base + tokens]
    if not tokens and not options.get("r") and "I" not in options:
        batches = [base]
    elif not tokens:
        batches = []
    outputs, code = [], 0
    for batch in batches:
        result = terminal._execute(terminal.expand_globs(batch))
        if result.output:
            outputs.append(result.output)
        if result.code:
            code = 123
    return Result("\n".join(outputs), code)


# ---------------------------------------------------------------- sed
_POSIX = {"alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z",
          "space": r"\s", "blank": r" \t", "punct": r"!-/:-@\[-`{-~"}


def _regex(pattern, extended, ignore_case=False):
    out, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if char == "[":
            end = index + 1
            if end < len(pattern) and pattern[end] == "^":
                end += 1
            if end < len(pattern) and pattern[end] == "]":
                end += 1
            while end < len(pattern) and pattern[end] != "]":
                end += 2 if pattern.startswith("[:", end) and ":]" in pattern[end:] and False else 1
                if pattern.startswith("[:", end - 1):
                    close = pattern.find(":]", end)
                    if close != -1:
                        end = close + 2
            body = pattern[index:end + 1]
            body = re.sub(r"\[:(\w+):\]", lambda m: _POSIX.get(m.group(1), m.group(0)), body)
            body = body.replace("\\", "\\\\") if "\\" in body and "\\s" not in body else body
            out.append(body)
            index = end + 1
            continue
        if char == "\\" and index + 1 < len(pattern):
            nxt = pattern[index + 1]
            index += 2
            if not extended and nxt in "(){}|+?":
                out.append(nxt)
            elif nxt in "<>":
                out.append(r"\b")
            elif nxt == "/":
                out.append("/")
            else:
                out.append("\\" + nxt)
            continue
        if not extended and char in "(){}|+?":
            out.append("\\" + char)
        elif char == "*" and not out:
            out.append("\\*")
        else:
            out.append(char)
        index += 1
    try:
        return re.compile("".join(out), re.IGNORECASE if ignore_case else 0)
    except re.error:
        raise TrainingError(f"sed: 正規表現 {pattern!r} が正しくありません。")


def _parse_sed(script, extended):
    """スクリプトを [(アドレス1, アドレス2, 否定, コマンド, 引数)] にする。未対応なら None。"""
    commands, index, length = [], 0, len(script)

    def address():
        nonlocal index
        if index >= length:
            return None
        if script[index].isdigit():
            start = index
            while index < length and script[index].isdigit():
                index += 1
            return ("n", int(script[start:index]))
        if script[index] == "$":
            index += 1
            return ("$", None)
        if script[index] == "/":
            index += 1
            start = index
            while index < length and script[index] != "/":
                index += 2 if script[index] == "\\" else 1
            text = script[start:index]
            index += 1
            ignore = False
            if index < length and script[index] == "I":
                ignore, index = True, index + 1
            return ("re", _regex(text, extended, ignore))
        return None

    while index < length:
        while index < length and script[index] in " \t;\n":
            index += 1
        if index >= length:
            break
        first = address()
        second = None
        if first and index < length and script[index] == ",":
            index += 1
            second = address()
            if second is None:
                return None
        while index < length and script[index] == " ":
            index += 1
        negate = False
        if index < length and script[index] == "!":
            negate, index = True, index + 1
        if index >= length:
            raise TrainingError("sed: コマンドがありません（例: 2p, 3d, s/古/新/）。")
        name = script[index]
        index += 1
        if name in "pdq":
            commands.append((first, second, negate, name, None))
        elif name == "s":
            if index >= length:
                raise TrainingError("sed: s の後ろに区切り文字が必要です（例: s/古/新/）。")
            delimiter = script[index]
            index += 1
            parts = []
            for _ in range(2):
                start = index
                while index < length and script[index] != delimiter:
                    index += 2 if script[index] == "\\" else 1
                if index >= length:
                    raise TrainingError("sed: s/古い/新しい/ の区切り（/）が足りません。")
                parts.append(script[start:index].replace("\\" + delimiter, delimiter))
                index += 1
            start = index
            while index < length and script[index] not in ";\n }":
                index += 1
            flags = script[start:index]
            if set(flags) - set("gpI0123456789"):
                return None
            number = re.search(r"\d+", flags)
            commands.append((first, second, negate, "s",
                             (_regex(parts[0], extended, "I" in flags), parts[1], "g" in flags,
                              "p" in flags, int(number.group()) if number else 1)))
        elif name == "y":
            delimiter = script[index]
            index += 1
            parts = []
            for _ in range(2):
                end = script.find(delimiter, index)
                if end == -1:
                    raise TrainingError("sed: y/変換前/変換後/ の区切りが足りません。")
                parts.append(script[index:end])
                index = end + 1
            if len(parts[0]) != len(parts[1]):
                raise TrainingError("sed: y の変換前と変換後は同じ長さにします。")
            commands.append((first, second, negate, "y", dict(zip(parts[0], parts[1]))))
        else:
            return None
    return commands


def _substitute(line, spec):
    regex, replacement, every, _, number = spec
    count = 0

    def build(match):
        nonlocal count
        count += 1
        if not every and count != number:
            return match.group(0)
        if every and count < number:
            return match.group(0)
        out, i = [], 0
        while i < len(replacement):
            ch = replacement[i]
            if ch == "\\" and i + 1 < len(replacement):
                nxt = replacement[i + 1]
                if nxt.isdigit():
                    try:
                        out.append(match.group(int(nxt)) or "")
                    except (IndexError, re.error):
                        raise TrainingError("sed: 置換先の \\1 に対応する ( ) がありません。")
                else:
                    out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                i += 2
                continue
            out.append(match.group(0) if ch == "&" else ch)
            i += 1
        return "".join(out)

    return regex.sub(build, line), count > 0


def _sed_run(commands, lines, quiet):
    out, active = [], {}
    total = len(lines)
    for number, line in enumerate(lines, 1):
        deleted, printed_extra, quit_now = False, [], False

        def hit(ref):
            kind, value = ref
            return (number == value) if kind == "n" else (number == total) if kind == "$" else bool(value.search(line))

        for position, (first, second, negate, name, arg) in enumerate(commands):
            if first is None:
                selected = True
            elif second is None:
                selected = hit(first)
            else:
                if active.get(position):
                    selected = True
                    if (second[0] == "n" and number >= second[1]) or (second[0] != "n" and hit(second)):
                        active[position] = False
                elif hit(first):
                    selected = True
                    active[position] = not (second[0] == "n" and second[1] <= number) and not (second[0] == "$" and number == total)
                else:
                    selected = False
            if selected == negate:
                continue
            if name == "d":
                deleted = True
                break
            if name == "p":
                printed_extra.append(line)
            elif name == "s":
                line, changed = _substitute(line, arg)
                if changed and arg[3]:
                    printed_extra.append(line)
            elif name == "y":
                line = "".join(arg.get(ch, ch) for ch in line)
            elif name == "q":
                quit_now = True
                break
        out.extend(printed_extra)
        if not deleted and not quiet:
            out.append(line)
        if quit_now:
            break
    return out


@command("sed")
def sed(terminal, rest, stdin=None, admin=False):
    options, args, index = {}, [], 0
    scripts = []
    while index < len(rest):
        arg = rest[index]
        if arg in ("-n", "-E", "-r"):
            options["n" if arg == "-n" else "E"] = True
        elif arg == "-e":
            index += 1
            if index >= len(rest):
                raise TrainingError("-e の後ろにスクリプトを書きます。")
            scripts.append(rest[index])
        elif arg == "--in-place" or arg.startswith("--in-place="):
            options["i"] = arg.partition("=")[2] or True
        elif arg.startswith("-i"):
            options["i"] = arg[2:] or True
        elif arg.startswith("-") and len(arg) > 1 and set(arg[1:]) <= set("nEr"):
            for letter in arg[1:]:
                options["n" if letter == "n" else "E"] = True
        elif arg.startswith("-") and len(arg) > 1:
            return None
        else:
            args.append(arg)
        index += 1
    if not scripts:
        if not args:
            raise TrainingError("sed の書式: sed 's/古い/新しい/' ファイル  /  sed -n '2p' ファイル")
        scripts.append(args.pop(0))
    parsed = _parse_sed("\n".join(scripts), bool(options.get("E")))
    if parsed is None:
        return None
    if options.get("i"):
        if not args:
            raise TrainingError("sed -i は書き換えるファイル名が必要です（パイプでは使えません）。")
        for name in args:
            lines = _read(terminal, "sed", [name], None)
            if isinstance(options["i"], str):
                terminal._write_output(name + options["i"], "".join(x + "\n" for x in lines), False)
            result = _sed_run(parsed, lines, bool(options.get("n")))
            terminal._write_output(name, "".join(x + "\n" for x in result), False)
        return Result()
    return _out(_sed_run(parsed, _read(terminal, "sed", args, stdin), bool(options.get("n"))))


# ---------------------------------------------------------------- awk
_TOKEN = re.compile(r"""\s*(?:(?P<num>\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|(?P<str>"(?:\\.|[^"\\])*")|(?P<name>[A-Za-z_]\w*)"""
                    r"""|(?P<op>\+\+|--|\+=|-=|\*=|/=|%=|==|!=|<=|>=|&&|\|\||!~|[-+*/%^<>=!~?:,;(){}\[\]$]))""")


class _Unsupported(Exception):
    pass


class _Next(Exception):
    pass


class _Exit(Exception):
    pass


class _Lit(str):
    """プログラム中の文字列リテラル（フィールドの数字と違い、常に文字として比べる）。"""


def _tokenize(source):
    tokens, index, length = [], 0, len(source)
    while index < length:
        if source[index] in " \t\r":
            index += 1
            continue
        if source[index] == "\n":
            tokens.append(("op", ";"))
            index += 1
            continue
        if source[index] == "#":
            while index < length and source[index] != "\n":
                index += 1
            continue
        previous = tokens[-1] if tokens else None
        if source[index] == "/" and (previous is None or (previous[0] == "op" and previous[1] not in (")", "]", "++", "--"))):
            end = index + 1
            while end < length and source[end] != "/":
                end += 2 if source[end] == "\\" else 1
            if end >= length:
                raise TrainingError("awk: 正規表現の終わりの / がありません。")
            tokens.append(("re", source[index + 1:end]))
            index = end + 1
            continue
        match = _TOKEN.match(source, index)
        if not match or match.end() == index:
            raise TrainingError(f"awk: 読み取れない文字があります: {source[index:index + 8]!r}")
        kind = match.lastgroup
        text = match.group(kind)
        if kind == "str":
            text = _Lit(re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}.get(m.group(1), m.group(1)), text[1:-1]))
        tokens.append((kind, text))
        index = match.end()
    return tokens


def _num(value):
    if isinstance(value, float):
        return value
    match = re.match(r"\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", str(value))
    return float(match.group()) if match else 0.0


def _looks_numeric(value):
    return isinstance(value, float) or (not isinstance(value, _Lit) and bool(re.fullmatch(r"\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*", value)))


def _str(value):
    if isinstance(value, float):
        return str(int(value)) if value == int(value) and abs(value) < 1e16 else "%.6g" % value
    return value


def _truth(value):
    if isinstance(value, float):
        return value != 0
    if isinstance(value, _Lit) or not _looks_numeric(value):
        return value != ""
    return _num(value) != 0


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.position, self.no_gt = tokens, 0, False

    def peek(self, offset=0):
        i = self.position + offset
        return self.tokens[i] if i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.position += 1
        return token

    def at(self, value):
        return self.peek()[0] in ("op", "name") and self.peek()[1] == value and self.peek()[0] != "str"

    def expect(self, value):
        if not self.at(value):
            raise TrainingError(f"awk: {value!r} が必要です。{{ }} や ( ) の閉じ忘れがないか確認しましょう。")
        self.position += 1

    def skip(self):
        while self.at(";"):
            self.position += 1

    # ---- program
    def program(self):
        items = []
        self.skip()
        while self.peek()[0] is not None:
            pattern = None
            if self.at("BEGIN") or self.at("END"):
                pattern = self.take()[1]
            elif not self.at("{"):
                pattern = ("expr", self.expression())
            body = None
            if self.at("{"):
                body = self.block()
            items.append((pattern, body))
            self.skip()
        return items

    def block(self):
        self.expect("{")
        statements = []
        self.skip()
        while not self.at("}"):
            if self.peek()[0] is None:
                raise TrainingError("awk: { に対応する } がありません。")
            statements.append(self.statement())
            self.skip()
        self.expect("}")
        return statements

    def statement(self):
        if self.at("{"):
            return ("block", self.block())
        if self.at("print") or self.at("printf"):
            kind = self.take()[1]
            args = []
            self.no_gt = True
            if not (self.at(";") or self.at("}")):
                args.append(self.expression())
                while self.at(","):
                    self.take()
                    args.append(self.expression())
            self.no_gt = False
            if self.at(">") or self.at(">>") or self.at("|"):
                raise _Unsupported
            return (kind, args)
        if self.at("if"):
            self.take()
            self.expect("(")
            condition = self.expression()
            self.expect(")")
            self.skip()
            then = self.statement()
            self.skip()
            other = None
            if self.at("else"):
                self.take()
                self.skip()
                other = self.statement()
            return ("if", condition, then, other)
        if self.at("while"):
            self.take()
            self.expect("(")
            condition = self.expression()
            self.expect(")")
            self.skip()
            return ("while", condition, self.statement())
        if self.at("for"):
            self.take()
            self.expect("(")
            if self.peek()[0] == "name" and self.peek(1) == ("name", "in") and self.peek(3) == ("op", ")"):
                variable, array = self.peek()[1], self.peek(2)[1]
                self.position += 4
                self.skip()
                return ("forin", variable, array, self.statement())
            init = self.statement()
            self.expect(";")
            condition = self.expression()
            self.expect(";")
            step = self.statement()
            self.expect(")")
            self.skip()
            return ("for", init, condition, step, self.statement())
        if self.at("next"):
            self.take()
            return ("next",)
        if self.at("exit"):
            self.take()
            return ("exit",)
        return ("expr", self.expression())

    # ---- expressions
    def expression(self):
        return self.ternary()

    def ternary(self):
        left = self.assignment()
        if self.at("?"):
            self.take()
            a = self.ternary()
            self.expect(":")
            return ("cond", left, a, self.ternary())
        return left

    def assignment(self):
        left = self.logic_or()
        for op in ("=", "+=", "-=", "*=", "/=", "%="):
            if self.at(op) and left[0] in ("var", "index", "field"):
                self.take()
                return ("assign", op, left, self.assignment())
        return left

    def logic_or(self):
        left = self.logic_and()
        while self.at("||"):
            self.take()
            left = ("or", left, self.logic_and())
        return left

    def logic_and(self):
        left = self.match()
        while self.at("&&"):
            self.take()
            left = ("and", left, self.match())
        return left

    def match(self):
        left = self.compare()
        while self.at("~") or self.at("!~"):
            op = self.take()[1]
            left = ("match", op == "!~", left, self.compare())
        return left

    def compare(self):
        left = self.concat()
        for op in ("<", "<=", "==", "!=", ">=", ">"):
            if self.at(op) and not (op == ">" and self.no_gt):
                self.take()
                return ("cmp", op, left, self.concat())
        return left

    def concat(self):
        left = self.additive()
        while True:
            kind, value = self.peek()
            starts = kind in ("num", "str", "re") or (kind == "name" and value not in ("in", "print", "printf", "if", "else", "for", "while", "next", "exit")) \
                or (kind == "op" and value in ("$", "("))
            if not starts:
                return left
            left = ("concat", left, self.additive())

    def additive(self):
        left = self.term()
        while self.at("+") or self.at("-"):
            op = self.take()[1]
            left = ("arith", op, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while self.at("*") or self.at("/") or self.at("%"):
            op = self.take()[1]
            left = ("arith", op, left, self.unary())
        return left

    def unary(self):
        if self.at("!"):
            self.take()
            return ("not", self.unary())
        if self.at("-"):
            self.take()
            return ("neg", self.unary())
        if self.at("+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        base = self.postfix()
        if self.at("^"):
            self.take()
            return ("arith", "^", base, self.unary())
        return base

    def postfix(self):
        if self.at("++") or self.at("--"):
            op = self.take()[1]
            target = self.postfix()
            return ("assign", "+=" if op == "++" else "-=", target, ("num", 1.0))
        node = self.primary()
        if (self.at("++") or self.at("--")) and node[0] in ("var", "index", "field"):
            op = self.take()[1]
            return ("post", "+=" if op == "++" else "-=", node)
        return node

    def primary(self):
        kind, value = self.take()
        if kind == "num":
            return ("num", float(value))
        if kind == "str":
            return ("str", value)
        if kind == "re":
            return ("re", re.compile(self.fix_regex(value)))
        if kind == "op" and value == "(":
            saved, self.no_gt = self.no_gt, False
            node = self.expression()
            self.no_gt = saved
            self.expect(")")
            return ("group", node)
        if kind == "op" and value == "$":
            return ("field", self.postfix_no_incr())
        if kind == "name":
            if self.at("("):
                self.take()
                args = []
                saved, self.no_gt = self.no_gt, False
                if not self.at(")"):
                    args.append(self.expression())
                    while self.at(","):
                        self.take()
                        args.append(self.expression())
                self.no_gt = saved
                self.expect(")")
                return ("call", value, args)
            if self.at("["):
                self.take()
                key = self.expression()
                self.expect("]")
                return ("index", value, key)
            return ("var", value)
        raise TrainingError("awk: 式が正しくありません。{print $1} のように { } の中に print を書きます。")

    def postfix_no_incr(self):
        return self.primary()

    @staticmethod
    def fix_regex(text):
        text = text.replace("\\/", "/")
        return re.sub(r"\[:(\w+):\]", lambda m: _POSIX.get(m.group(1), m.group(0)), text)


class _Awk:
    def __init__(self, items, separator, assigns):
        self.items, self.fs = items, separator
        self.vars = {"OFS": " ", "ORS": "\n", "NR": 0.0, "NF": 0.0, "FS": separator or " "}
        self.vars.update(assigns)
        self.arrays, self.fields, self.output = {}, [""], []
        self.steps = 0

    def set_record(self, line):
        self.fields = [line, *self.split(line)]
        self.vars["NF"] = float(len(self.fields) - 1)

    def split(self, text, separator=None):
        separator = self.vars["FS"] if separator is None else separator
        if separator == " ":
            return text.split()
        if text == "":
            return []
        if len(separator) == 1:
            return text.split(separator)
        try:
            return re.split(separator, text)
        except re.error:
            return text.split(separator)

    def rebuild(self):
        self.fields[0] = self.vars["OFS"].join(self.fields[1:])

    def get_field(self, index):
        index = int(_num(index))
        if index < 0:
            raise TrainingError("awk: フィールド番号は 0 以上です。")
        return self.fields[index] if index < len(self.fields) else ""

    def set_field(self, index, value):
        index = int(_num(index))
        if index == 0:
            self.set_record(_str(value))
            return
        while len(self.fields) <= index:
            self.fields.append("")
        self.fields[index] = _str(value)
        self.vars["NF"] = float(len(self.fields) - 1)
        self.rebuild()

    def tick(self):
        self.steps += 1
        if self.steps > 200000:
            raise TrainingError("awk: 処理が終わらないので止めました（無限ループになっていませんか）。")

    # ---- evaluation
    def value(self, node):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "group":
            return self.value(node[1])
        if kind == "var":
            name = node[1]
            if name == "NF":
                return float(len(self.fields) - 1)
            if name == "$0":
                return self.fields[0]
            return self.vars.get(name, "")
        if kind == "field":
            return self.get_field(self.value(node[1]))
        if kind == "index":
            return self.arrays.get(node[1], {}).get(_str(self.value(node[2])), "")
        if kind == "re":
            return 1.0 if node[1].search(self.fields[0]) else 0.0
        if kind == "not":
            return 0.0 if _truth(self.value(node[1])) else 1.0
        if kind == "neg":
            return -_num(self.value(node[1]))
        if kind == "arith":
            a, b = _num(self.value(node[2])), _num(self.value(node[3]))
            op = node[1]
            if op in "/%" and b == 0:
                raise TrainingError("awk: 0 で割ることはできません。")
            return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b,
                    "%": lambda: float(__import__("math").fmod(a, b)), "^": lambda: a ** b}[op]()
        if kind == "concat":
            return _str(self.value(node[1])) + _str(self.value(node[2]))
        if kind == "cmp":
            a, b = self.value(node[2]), self.value(node[3])
            if _looks_numeric(a) and _looks_numeric(b):
                a, b = _num(a), _num(b)
            else:
                a, b = _str(a), _str(b)
            return 1.0 if {"<": a < b, "<=": a <= b, "==": a == b, "!=": a != b, ">": a > b, ">=": a >= b}[node[1]] else 0.0
        if kind == "match":
            regex = self.regex_of(node[3])
            hit = bool(regex.search(_str(self.value(node[2]))))
            return 1.0 if hit != node[1] else 0.0
        if kind == "and":
            return 1.0 if _truth(self.value(node[1])) and _truth(self.value(node[2])) else 0.0
        if kind == "or":
            return 1.0 if _truth(self.value(node[1])) or _truth(self.value(node[2])) else 0.0
        if kind == "cond":
            return self.value(node[2]) if _truth(self.value(node[1])) else self.value(node[3])
        if kind == "assign":
            op, target = node[1], node[2]
            new = self.value(node[3])
            if op != "=":
                old = _num(self.value(target))
                new = _num(new)
                if op in ("/=", "%=") and new == 0:
                    raise TrainingError("awk: 0 で割ることはできません。")
                new = {"+=": old + new, "-=": old - new, "*=": old * new, "/=": old / new if new else 0, "%=": old % new if new else 0}[op]
            self.store(target, new)
            return new
        if kind == "post":
            old = _num(self.value(node[2]))
            self.store(node[2], old + (1 if node[1] == "+=" else -1))
            return old
        if kind == "call":
            return self.call(node[1], node[2])
        raise _Unsupported

    def regex_of(self, node):
        if node[0] == "re":
            return node[1]
        text = _str(self.value(node))
        try:
            return re.compile(text)
        except re.error:
            return re.compile(re.escape(text))

    def store(self, target, value):
        if target[0] == "var":
            self.vars[target[1]] = value
        elif target[0] == "index":
            self.arrays.setdefault(target[1], {})[_str(self.value(target[2]))] = value
        elif target[0] == "field":
            self.set_field(self.value(target[1]), value)

    def call(self, name, args):
        values = [self.value(a) for a in args]
        if name == "length":
            if not args:
                return float(len(self.fields[0]))
            if args[0][0] == "var" and args[0][1] in self.arrays:
                return float(len(self.arrays[args[0][1]]))
            return float(len(_str(values[0])))
        if name == "toupper" and len(values) == 1:
            return _str(values[0]).upper()
        if name == "tolower" and len(values) == 1:
            return _str(values[0]).lower()
        if name == "int" and len(values) == 1:
            return float(int(_num(values[0])))
        if name == "substr" and len(values) in (2, 3):
            text, start = _str(values[0]), int(_num(values[1]))
            begin = max(start, 1)
            end = len(text) + 1 if len(values) == 2 else start + int(_num(values[2]))
            return text[begin - 1:max(end - 1, 0)]
        if name == "index" and len(values) == 2:
            return float(_str(values[0]).find(_str(values[1])) + 1)
        if name == "sprintf" and values:
            return self.format(_str(values[0]), values[1:])
        if name == "split" and len(args) in (2, 3) and args[1][0] == "var":
            sep = _str(values[2]) if len(values) == 3 else None
            parts = self.split(_str(values[0]), sep)
            self.arrays[args[1][1]] = {str(i): p for i, p in enumerate(parts, 1)}
            return float(len(parts))
        if name in ("sub", "gsub") and len(args) in (2, 3):
            regex = self.regex_of(args[0])
            target = args[2] if len(args) == 3 else ("field", ("num", 0.0))
            if target[0] not in ("var", "field", "index"):
                raise _Unsupported
            replacement = _str(values[1])

            def swap(m):
                return re.sub(r"\\&", "&", re.sub(r"(?<!\\)&", m.group(0).replace("\\", "\\\\"), replacement))
            new, count = regex.subn(swap, _str(self.value(target)), count=0 if name == "gsub" else 1)
            if count:
                self.store(target, new)
            return float(count)
        raise _Unsupported

    def format(self, template, values):
        values, position = list(values), [0]

        def spec(match):
            flags, width, precision, conv = match.group(1), match.group(2), match.group(3), match.group(4)
            if conv == "%":
                return "%"
            raw = values[position[0]] if position[0] < len(values) else ""
            position[0] += 1
            body = "%" + flags + width + (("." + precision) if precision is not None else "")
            if conv in "di":
                return (body + "d") % int(_num(raw))
            if conv in "feEgG":
                return (body + conv) % _num(raw)
            if conv in "xXo":
                return (body + conv) % int(_num(raw))
            if conv == "c":
                text = chr(int(_num(raw))) if isinstance(raw, float) else _str(raw)[:1]
                return (body.replace(".", "") + "s") % text
            return (body + "s") % _str(raw)

        template = re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "\\": "\\"}.get(m.group(1), m.group(0)), template)
        return re.sub(r"%([-+ 0#]*)(\d*)(?:\.(\d+))?([diouxXeEfgGcs%])", spec, template)

    # ---- statements
    def run(self, statements):
        for statement in statements:
            self.execute(statement)

    def execute(self, statement):
        self.tick()
        kind = statement[0]
        if kind == "print":
            args = statement[1]
            text = self.vars["OFS"].join(_str(self.value(a)) for a in args) if args else self.fields[0]
            self.output.append(text + self.vars["ORS"])
        elif kind == "printf":
            if not statement[1]:
                raise TrainingError("awk: printf には書式が必要です。例: printf \"%s\\n\", $1")
            values = [self.value(a) for a in statement[1]]
            text = self.format(_str(values[0]), values[1:])
            self.output.append(text)
        elif kind == "expr":
            self.value(statement[1])
        elif kind == "block":
            self.run(statement[1])
        elif kind == "if":
            if _truth(self.value(statement[1])):
                self.execute(statement[2])
            elif statement[3]:
                self.execute(statement[3])
        elif kind == "while":
            while _truth(self.value(statement[1])):
                self.tick()
                self.execute(statement[2])
        elif kind == "for":
            self.execute(statement[1])
            while _truth(self.value(statement[2])):
                self.tick()
                self.execute(statement[4])
                self.execute(statement[3])
        elif kind == "forin":
            for key in list(self.arrays.get(statement[2], {})):
                self.vars[statement[1]] = key
                self.execute(statement[3])
        elif kind == "next":
            raise _Next
        elif kind == "exit":
            raise _Exit


def _awk_lines(output):
    text = "".join(output)
    return text[:-1] if text.endswith("\n") else text


@command("awk")
def awk(terminal, rest, stdin=None, admin=False):
    separator, assigns, args, index = None, {}, [], 0
    while index < len(rest):
        arg = rest[index]
        if arg == "-F":
            index += 1
            if index >= len(rest):
                raise TrainingError("-F の後ろに区切り文字を書きます。例: -F,")
            separator = rest[index]
        elif arg.startswith("-F") and len(arg) > 2:
            separator = arg[2:]
        elif arg == "-v":
            index += 1
            name, _, value = (rest[index] if index < len(rest) else "").partition("=")
            if not name:
                raise TrainingError("-v の後ろは 変数=値 の形で書きます。")
            assigns[name] = float(value) if re.fullmatch(r"-?\d+(\.\d+)?", value) else _Lit(value)
        elif arg.startswith("-") and len(arg) > 1:
            return None
        else:
            args.append(arg)
        index += 1
    if not args:
        raise TrainingError("awk の書式: awk '{print $1}' ファイル  /  awk -F, '{print $2}' ファイル")
    if separator == "t":
        separator = "\t"
    program, files = args[0], args[1:]
    try:
        items = _Parser(_tokenize(program)).program()
        engine = _Awk(items, separator, assigns)
        only_begin = all(pattern == "BEGIN" for pattern, _ in items)
        lines = [] if (only_begin and not files and stdin is None) else _read(terminal, "awk", files, stdin)
        begin = [body for pattern, body in items if pattern == "BEGIN"]
        end = [body for pattern, body in items if pattern == "END"]
        main = [(pattern, body) for pattern, body in items if pattern not in ("BEGIN", "END")]
        try:
            for body in begin:
                engine.run(body or [])
            for line in (lines if (main or end) else []):
                engine.vars["NR"] += 1
                engine.set_record(line)
                try:
                    for pattern, body in main:
                        if pattern is None or _truth(engine.value(pattern[1])):
                            engine.run(body if body is not None else [("print", [])])
                except _Next:
                    continue
            for body in end:
                engine.run(body or [])
        except _Exit:
            pass
    except _Unsupported:
        return None
    except RecursionError:
        raise TrainingError("awk: 式が複雑すぎます。")
    return Result(_awk_lines(engine.output))
