"""初心者向けの模擬 vim。1回の入力（Enter まで）を1つの操作として扱う。

本物の vim は起動しない。状態は辞書で持ち、進捗データに保存できる。
ファイルの読み書きは engine.guided.Terminal が練習フォルダの中だけで行う。
"""
import re

# 本物の vim では Esc キーを押す。Windows のコンソールなど Esc を入力できない環境のため、
# 文字の esc でも同じ扱いにする。
ESC_WORDS = {"esc", "<esc>", "[esc]", "\x1b"}

HELP = ("使える操作: i / a / o で入力モード、esc でノーマルモードへ戻る、"
        "j / k で下・上へ移動、gg / G で先頭・末尾へ、dd で行を削除、yy / p で行をコピー・貼り付け、"
        "3dd で3行削除、A で行末に書き足し、u で取り消し、/文字 で検索、"
        ":s/前/後/ で今の行を置換、:%s/前/後/g で全体を置換、:2,4s/前/後/ で範囲を置換、"
        ":w で保存、:q で終了、:wq で保存して終了、:q! で保存せずに終了")


SUBSTITUTE_RE = re.compile(r"^:(%|\d+,\d+|\d+)?s([^A-Za-z0-9\s])(.*)$")


def _substitute(st, cmd):
    """:s/前/後/[g]・:%s/前/後/[g]・:2,4s/前/後/。正規表現ではなく文字のまま置き換える。

    / の代わりに # などの記号でも区切れる（パスを置き換えるときに便利）。
    """
    usage = "置換は :s/前の文字/後の文字/ や :%s/前/後/g、:2,4s/前/後/ と書きます。"
    match = SUBSTITUTE_RE.match(cmd)
    if not match:
        return usage, 1
    where, delimiter, body = match.groups()
    parts = body.split(delimiter)
    if len(parts) < 2 or not parts[0]:
        return usage, 1
    old, new, flags = parts[0], parts[1], delimiter.join(parts[2:])
    if flags not in ("", "g"):
        return "この練習の置換で使える指定は g（行の中のすべて）だけです。", 1
    count = len(st["lines"])
    if where == "%":
        targets = range(count)
    elif where:
        first, _, last = where.partition(",")
        last = last or first
        if not 1 <= int(first) <= int(last) <= count:
            return f"E16: Invalid range（1〜{count}行目の範囲で指定します）", 1
        targets = range(int(first) - 1, int(last))
    else:
        targets = [st["cursor"]] if st["lines"] else []
    hits = [i for i in targets if old in st["lines"][i]]
    if not hits:
        return f"E486: Pattern not found: {old}（見つかりません）", 1
    _snapshot(st)
    for i in hits:
        st["lines"][i] = st["lines"][i].replace(old, new, -1 if flags == "g" else 1)
    st["cursor"] = hits[-1]
    st["modified"] = True
    return f"{len(hits)}行で置き換えました。", 0


def new_state(name, key, remote, lines, exists):
    return {"name": name, "key": key, "remote": remote, "lines": list(lines), "cursor": 0,
            "mode": "normal", "insert_at": 0, "modified": False, "undo": None, "yank": None,
            "new_file": not exists}


def _clamp(st):
    st["cursor"] = max(0, min(st["cursor"], len(st["lines"]) - 1)) if st["lines"] else 0


def _snapshot(st):
    st["undo"] = list(st["lines"])


def _enter_insert(st, key):
    if key in ("i", "I"):
        st["insert_at"] = st["cursor"]
    elif key == "O":
        st["insert_at"] = st["cursor"]
    else:  # a / A / o は今の行の後ろへ書く（この模擬では行単位で扱う）
        st["insert_at"] = st["cursor"] + 1 if st["lines"] else 0
    st["mode"] = "insert"
    st["insert_started"] = False
    # A は「今の行の最後に書き足す」。最初に入力した文字は今の行の末尾へつながる。
    st["append_line"] = st["cursor"] if key == "A" and st["lines"] else None


def _insert_line(st, text):
    if not st.get("insert_started"):
        _snapshot(st)
        st["insert_started"] = True
    if st.get("append_line") is not None:
        st["lines"][st["append_line"]] += text
        st["cursor"] = st["append_line"]
        st["append_line"] = None
        st["modified"] = True
        return
    st["lines"].insert(st["insert_at"], text)
    st["cursor"] = st["insert_at"]
    st["insert_at"] += 1
    st["modified"] = True


def handle(st, line):
    """1回の入力を処理し (メッセージ, 終了コード, 動作) を返す。

    動作は None / "write" / "quit" / "write_quit"。保存と終了は呼び出し側が行う。
    """
    if st["mode"] == "insert":
        if line.strip().lower() in ESC_WORDS:
            st["mode"] = "normal"
            _clamp(st)
            return "ノーマルモードに戻りました。", 0, None
        text, leave = (line[:-1], True) if line.endswith("\x1b") else (line, False)
        _insert_line(st, text)
        if leave:
            st["mode"] = "normal"
        return "", 0, None

    cmd = line.strip()
    lines = st["lines"]
    if cmd.lower() in ESC_WORDS:
        return "すでにノーマルモードです。ここでは入力がコマンドとして扱われます。", 0, None
    if cmd in ("i", "I", "a", "A", "o", "O"):
        _enter_insert(st, cmd)
        return "入力モードです。文字を入力して Enter、終わったら esc でノーマルモードへ戻ります。", 0, None
    if cmd in ("j", "k"):
        st["cursor"] += 1 if cmd == "j" else -1
        _clamp(st)
        return "", 0, None
    if cmd in ("gg", "G"):
        st["cursor"] = 0 if cmd == "gg" else len(lines) - 1
        _clamp(st)
        return "", 0, None
    count_dd = re.fullmatch(r"([1-9]\d*)?dd", cmd)
    if count_dd:
        if not lines:
            return "削除する行がありません。", 1, None
        number = min(int(count_dd.group(1) or 1), len(lines) - st["cursor"])
        _snapshot(st)
        st["yank"] = lines[st["cursor"]:st["cursor"] + number]
        del lines[st["cursor"]:st["cursor"] + number]
        st["modified"] = True
        _clamp(st)
        return f"{number}行削除しました。u で取り消せます。", 0, None
    if cmd == "yy":
        if not lines:
            return "コピーする行がありません。", 1, None
        st["yank"] = [lines[st["cursor"]]]
        return "1行コピーしました。p で下に貼り付けます。", 0, None
    if cmd == "p":
        if not st.get("yank"):
            return "貼り付ける内容がありません。先に yy か dd を使います。", 1, None
        _snapshot(st)
        at = st["cursor"] + 1 if lines else 0
        lines[at:at] = st["yank"]
        st["cursor"] = at
        st["modified"] = True
        return "", 0, None
    if cmd == "u":
        if st.get("undo") is None:
            return "Already at oldest change（これ以上取り消せる変更はありません）", 1, None
        st["lines"], st["undo"] = st["undo"], st["lines"]
        st["modified"] = True
        _clamp(st)
        return "変更を1つ取り消しました。", 0, None
    if cmd.startswith("/") and len(cmd) > 1:
        word = cmd[1:]
        count = len(lines)
        for step in range(1, count + 1):
            index = (st["cursor"] + step) % count
            if word in lines[index]:
                st["cursor"] = index
                return f"{word} が見つかりました（{index + 1}行目）。", 0, None
        return f"E486: Pattern not found: {word}（見つかりません）", 1, None
    if cmd in (":w", ":w!"):
        return "", 0, "write"
    if cmd in (":wq", ":wq!", ":x", "ZZ"):
        return "", 0, "write_quit"
    if cmd == ":q":
        if st["modified"]:
            return ("E37: No write since last change (add ! to override)\n"
                    "保存していない変更があります。保存するなら :wq、捨てるなら :q! です。"), 1, None
        return "", 0, "quit"
    if cmd == ":q!":
        return "", 0, "quit"
    if SUBSTITUTE_RE.match(cmd):
        message, code = _substitute(st, cmd)
        return message, code, None
    if cmd[:1] == ":" and cmd[1:].isdigit():
        st["cursor"] = int(cmd[1:]) - 1
        _clamp(st)
        return "", 0, None
    if cmd in (":set number", ":set nu"):
        return "この練習の画面では、行番号をいつも表示しています。", 0, None
    if cmd in (":help", ":h"):
        return HELP, 0, None
    if cmd[:1] in ("i", "a", "o") and len(cmd) > 1:
        # 本物と同じく、i の直後の文字は入力モードで書いた文字になる。
        _enter_insert(st, cmd[0])
        text = cmd[1:]
        if text.endswith("\x1b"):
            _insert_line(st, text[:-1])
            st["mode"] = "normal"
            return "", 0, None
        _insert_line(st, text)
        return "i の後ろの文字を入力しました。まだ入力モードです。終わったら esc。", 0, None
    if cmd.startswith(":"):
        return f"E492: Not an editor command: {cmd[1:]}\n{HELP}", 1, None
    return ("今はノーマルモードなので、入力はコマンドとして扱われます。"
            "文字を書くには、まず i を入力して入力モードにします。\n" + HELP), 1, None


def render(st, message=""):
    """画面の代わりに、カーソル付近の行とモード表示を返す。"""
    lines = st["lines"]
    top = max(0, min(st["cursor"] - 4, len(lines) - 9))
    shown = []
    inserting = st["mode"] == "insert"
    end = min(len(lines), top + 9)
    for index in range(top, end + 1):
        if inserting and index == st["insert_at"]:
            shown.append("        | ← ここに入力されます")
        if index < end:
            mark = ">" if index == st["cursor"] and not inserting else " "
            shown.append(f"  {mark}{index + 1:>3} | {lines[index]}")
    shown += ["      ~"] * max(0, 2 - len(lines))
    status = "-- INSERT --" if st["mode"] == "insert" else "NORMAL"
    flag = " [+]" if st["modified"] else ""
    shown.append(f"  [{status}] \"{st['name']}\"{flag}  {len(lines)}行")
    if message:
        shown.append("  " + message.replace("\n", "\n  "))
    return "\n".join(shown)
