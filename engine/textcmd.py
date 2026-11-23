"""模擬ターミナルのテキスト処理コマンド（grep / sort / uniq / cut / wc / head / tail）。

入力は行のリスト、出力は (表示する文字列, 終了コード)。ファイルは読まない。
本物の GNU coreutils の主なオプションだけを、同じ表示形式で再現する。
"""
import re


class UsageError(ValueError):
    """書式が練習の対象外。メッセージは学習者向けの説明。"""


def split_flags(args, allowed, with_value=()):
    """-in のようにまとめた短いオプションも分解する。値を取るオプションは辞書で返す。"""
    flags, values, rest = set(), {}, []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            rest.extend(args[index + 1:])
            break
        if arg.startswith("-") and len(arg) > 1 and not arg[1:].isdigit():
            body = arg[1:]
            position = 0
            while position < len(body):
                letter = body[position]
                if letter in with_value:
                    value = body[position + 1:]
                    if not value:
                        index += 1
                        if index >= len(args):
                            raise UsageError(f"-{letter} の後ろに値を書きます。")
                        value = args[index]
                    values[letter] = value
                    break
                if letter not in allowed:
                    raise UsageError(f"-{letter} はこの練習では使えないオプションです。")
                flags.add(letter)
                position += 1
        else:
            rest.append(arg)
        index += 1
    return flags, values, rest


def grep(flags, pattern, lines, label=None):
    try:
        regex = re.compile(pattern, re.IGNORECASE if "i" in flags else 0)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE if "i" in flags else 0)
    found = []
    for number, line in enumerate(lines, 1):
        hit = bool(regex.search(line))
        if hit != ("v" in flags):
            prefix = (f"{label}:" if label else "") + (f"{number}:" if "n" in flags else "")
            found.append(prefix + line)
    if "c" in flags:
        return ((f"{label}:" if label else "") + str(len(found))), 0 if found else 1
    if "l" in flags:
        return (label or "(standard input)") if found else "", 0 if found else 1
    return "\n".join(found), 0 if found else 1


def _number_key(line):
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", line)
    return float(match.group(1)) if match else 0.0


def sort(flags, lines, values=None):
    """sort [-r -n -u] [-t 区切り] [-k 列番号]。"""
    values = values or {}
    delimiter = values.get("t")
    column = values.get("k")
    if column is not None:
        column = column.split(",")[0].rstrip("nr")
        if not column.isdigit() or int(column) < 1:
            raise UsageError("-k は列の番号で指定します。例: sort -t , -k 2 data.csv")
        column = int(column)

    def field(line):
        if column is None:
            return line
        parts = line.split(delimiter) if delimiter else line.split()
        return parts[column - 1] if column <= len(parts) else ""

    if "n" in flags:
        result = sorted(lines, key=lambda line: (_number_key(field(line)), line))
    else:
        result = sorted(lines, key=lambda line: (field(line), line))
    if "r" in flags:
        result.reverse()
    if "u" in flags:
        unique = []
        for line in result:
            if not unique or field(unique[-1]) != field(line):
                unique.append(line)
        result = unique
    return "\n".join(result), 0


def uniq(flags, lines):
    groups = []
    for line in lines:
        if groups and groups[-1][1] == line:
            groups[-1][0] += 1
        else:
            groups.append([1, line])
    if "c" in flags:
        return "\n".join(f"{count:>7} {line}" for count, line in groups), 0
    return "\n".join(line for _, line in groups), 0


def _field_numbers(spec):
    numbers = []
    for part in spec.split(","):
        if "-" in part:
            start, _, end = part.partition("-")
            start = start or "1"
            end = end or "999"  # 2- は「2列目から最後まで」
            if not (start.isdigit() and end.isdigit()):
                raise UsageError("-f は 2 や 1,3 や 2-3 や 2- のように番号で指定します。")
            numbers.extend(range(int(start), int(end) + 1))
        elif part.isdigit() and int(part) > 0:
            numbers.append(int(part))
        else:
            raise UsageError("-f は 2 や 1,3 や 2-3 のように番号で指定します。")
    return numbers


def cut(values, lines):
    if "f" not in values:
        raise UsageError("cut は -d 区切り文字 -f 列番号 で使います。例: cut -d , -f 2 users.csv")
    delimiter = values.get("d", "\t")
    if len(delimiter) != 1:
        raise UsageError("-d の区切り文字は1文字です。例: -d , や -d ' '")
    numbers = _field_numbers(values["f"])
    output = []
    for line in lines:
        if delimiter not in line:
            output.append(line)
            continue
        fields = line.split(delimiter)
        output.append(delimiter.join(fields[n - 1] for n in numbers if n <= len(fields)))
    return "\n".join(output), 0


def wc(flags, text, label=None):
    counts = {"l": text.count("\n"), "w": len(text.split()), "c": len(text.encode("utf-8"))}
    chosen = [key for key in "lwc" if key in flags] or ["l", "w", "c"]
    numbers = " ".join(str(counts[key]) for key in chosen)
    return (f"{numbers} {label}" if label else numbers), 0


def head_tail(command, count, lines, from_start=False):
    if command == "head":
        return "\n".join(lines[:count]), 0
    if from_start:  # tail -n +2 は「2行目から最後まで」（見出し行を飛ばす定番）
        return "\n".join(lines[max(count, 1) - 1:]), 0
    return "\n".join(lines[-count:] if count else []), 0


def line_count(args):
    """head / tail の -n 3 / -3 / -n3 / -n +2 を読み取り、(行数, 先頭から数えるか, 残りの引数) を返す。"""
    count, from_start, rest, index = 10, False, [], 0
    while index < len(args):
        arg = args[index]
        if arg == "-n" and index + 1 < len(args) and args[index + 1].lstrip("+").isdigit():
            from_start = args[index + 1].startswith("+")
            count = int(args[index + 1].lstrip("+"))
            index += 2
            continue
        if arg.startswith("-n") and arg[2:].lstrip("+").isdigit():
            from_start = arg[2:].startswith("+")
            count = int(arg[2:].lstrip("+"))
        elif arg.startswith("-") and arg[1:].isdigit():
            count = int(arg[1:])
        elif arg.startswith("-"):
            raise UsageError("行数は -n 3 のように指定します。")
        else:
            rest.append(arg)
        index += 1
    return count, from_start, rest


def diff(old_name, old_lines, new_name, new_lines):
    """GNU diff の標準形式（2c2 / 3a4 / 5d4）で違いを返す。同じなら終了コード 0。"""
    import difflib
    output = []

    def span(start, end):
        return str(start + 1) if end - start == 1 else f"{start + 1},{end}" if end > start else str(start)

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            output.append(f"{span(i1, i2)}c{span(j1, j2)}")
        elif tag == "delete":
            output.append(f"{span(i1, i2)}d{j1}")
        else:
            output.append(f"{i1}a{span(j1, j2)}")
        output += ["< " + x for x in old_lines[i1:i2]]
        if tag == "replace":
            output.append("---")
        output += ["> " + x for x in new_lines[j1:j2]]
    return "\n".join(output), 1 if output else 0
