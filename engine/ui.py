"""ANSI カラー表示・アスキーアート・プログレスバー・テーブル描画ユーティリティ。

標準ライブラリのみで動作する。NO_COLOR 環境変数が設定されている場合は色を付けない。
日本語（全角文字）の表示幅を考慮して罫線を揃える。
"""
import os
import re
import shutil
import sys
import unicodedata

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if os.environ.get("LQ_FORCE_COLOR"):
    USE_COLOR = True

CODES = {
    "reset": "0", "bold": "1", "dim": "2", "italic": "3", "under": "4", "blink": "5", "rev": "7",
    "black": "30", "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "white": "37", "gray": "90",
    "bred": "91", "bgreen": "92", "byellow": "93", "bblue": "94",
    "bmagenta": "95", "bcyan": "96", "bwhite": "97",
    "on_blue": "44", "on_magenta": "45", "on_green": "42", "on_red": "41", "on_gray": "100",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def c(text, *styles):
    """文字列に ANSI スタイルを付与する。"""
    styles = [s for s in styles if s in CODES]
    if not USE_COLOR or not styles:
        return str(text)
    seq = ";".join(CODES[s] for s in styles)
    return f"\x1b[{seq}m{text}\x1b[0m"


def strip_ansi(s):
    return ANSI_RE.sub("", s)


def width(s):
    """端末上の表示幅（全角=2）を返す。"""
    w = 0
    for ch in strip_ansi(s):
        if unicodedata.combining(ch):
            continue
        ea = unicodedata.east_asian_width(ch)
        if ea in ("W", "F"):
            w += 2
        elif ch in "​️":
            continue
        else:
            w += 1
    return w


def pad(s, w, align="left"):
    gap = max(0, w - width(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def term_width():
    return max(60, min(shutil.get_terminal_size((100, 30)).columns, 110))


def wrap(line, w):
    """表示幅ベースで1行を折り返す（ANSI を含まないテキスト前提だが、含んでいても崩れにくい）。"""
    if width(line) <= w:
        return [line]
    out, cur, cw = [], "", 0
    i = 0
    indent = len(line) - len(line.lstrip(" "))
    while i < len(line):
        m = ANSI_RE.match(line, i)
        if m:
            cur += m.group(0)
            i = m.end()
            continue
        ch = line[i]
        chw = width(ch)
        if cw + chw > w:
            out.append(cur)
            cur, cw = " " * indent, indent
        cur += ch
        cw += chw
        i += 1
    if cur.strip():
        out.append(cur)
    return out


def fmt(text):
    """簡易マークアップ: `code` → シアン, **bold** → 太字黄色。"""
    text = re.sub(r"`([^`]+)`", lambda m: c(m.group(1), "bcyan"), text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: c(m.group(1), "bold", "byellow"), text)
    return text


def box(lines, title=None, color="cyan", w=None, title_color=None):
    """全角文字を考慮した罫線ボックスを描画して文字列で返す。"""
    w = w or term_width() - 2
    inner = w - 4
    body = []
    for ln in lines:
        for seg in str(ln).split("\n"):
            body.extend(wrap(seg, inner))
    out = []
    if title:
        t = f" {title} "
        rest = max(0, w - 2 - width(t) - 2)
        out.append(c("╭──", color) + c(t, title_color or color, "bold") + c("─" * rest + "╮", color))
    else:
        out.append(c("╭" + "─" * (w - 2) + "╮", color))
    for ln in body:
        out.append(c("│ ", color) + pad(ln, inner) + c(" │", color))
    out.append(c("╰" + "─" * (w - 2) + "╯", color))
    return "\n".join(out)


def progress_bar(ratio, n=10, full="■", empty="□", color="bgreen"):
    ratio = max(0.0, min(1.0, ratio))
    k = int(round(ratio * n))
    return "[" + c(full * k, color) + c(empty * (n - k), "gray") + "]"


def table(headers, rows, colors=None):
    ws = [width(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            ws[i] = max(ws[i], width(str(cell)))
    sep = "  "
    out = [sep.join(c(pad(h, ws[i]), "bold", "white") for i, h in enumerate(headers))]
    out.append(c(sep.join("─" * x for x in ws), "gray"))
    for r in rows:
        out.append(sep.join(pad(str(cell), ws[i]) for i, cell in enumerate(r)))
    return "\n".join(out)


def clear():
    """画面とスクロールバックの両方を消す。前の画面まで遡ってスクロールできないようにする。"""
    if sys.stdout.isatty():
        sys.stdout.write("\x1b[H\x1b[2J\x1b[3J")
        sys.stdout.flush()


def hr(ch="─", color="gray"):
    return c(ch * (term_width() - 2), color)


TITLE_ART = r"""
  ██╗     ██╗███╗   ██╗██╗   ██╗██╗  ██╗     ██████╗ ██╗   ██╗███████╗███████╗████████╗
  ██║     ██║████╗  ██║██║   ██║╚██╗██╔╝    ██╔═══██╗██║   ██║██╔════╝██╔════╝╚══██╔══╝
  ██║     ██║██╔██╗ ██║██║   ██║ ╚███╔╝     ██║   ██║██║   ██║█████╗  ███████╗   ██║
  ██║     ██║██║╚██╗██║██║   ██║ ██╔██╗     ██║▄▄ ██║██║   ██║██╔══╝  ╚════██║   ██║
  ███████╗██║██║ ╚████║╚██████╔╝██╔╝ ██╗    ╚██████╔╝╚██████╔╝███████╗███████║   ██║
  ╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝     ╚══▀▀═╝  ╚═════╝ ╚══════╝╚══════╝   ╚═╝
"""

TITLE_ART_SMALL = r"""
   _     _                    ___                  _
  | |   (_)_ __  _   ___  __ / _ \ _   _  ___  ___| |_
  | |   | | '_ \| | | \ \/ /| | | | | | |/ _ \/ __| __|
  | |___| | | | | |_| |>  < | |_| | |_| |  __/\__ \ |_
  |_____|_|_| |_|\__,_/_/\_\ \__\_\\__,_|\___||___/\__|
"""

PENGUIN = r"""
       .--.
      |o_o |
      |:_/ |
     //   \ \
    (|     | )
   /'\_   _/`\
   \___)=(___/
"""

GRADIENT = ["bmagenta", "magenta", "bblue", "blue", "bcyan", "cyan"]


def title_art():
    art = TITLE_ART if term_width() >= 92 else TITLE_ART_SMALL
    lines = art.strip("\n").split("\n")
    return "\n".join(c(ln, GRADIENT[i % len(GRADIENT)], "bold") for i, ln in enumerate(lines))


CLEAR_ART = r"""
   __  __ ___ ____ ____ ___ ___  _   _    ____ _     _____    _    ____  _
  |  \/  |_ _/ ___/ ___|_ _/ _ \| \ | |  / ___| |   | ____|  / \  |  _ \| |
  | |\/| || |\___ \___ \| | | | |  \| | | |   | |   |  _|   / _ \ | |_) | |
  | |  | || | ___) |__) | | |_| | |\  | | |___| |___| |___ / ___ \|  _ <|_|
  |_|  |_|___|____/____/___\___/|_| \_|  \____|_____|_____/_/   \_\_| \_(_)
"""


def clear_art():
    lines = CLEAR_ART.strip("\n").split("\n")
    cols = ["byellow", "yellow", "bgreen", "green", "bcyan"]
    return "\n".join(c(ln, cols[i % len(cols)], "bold") for i, ln in enumerate(lines))
