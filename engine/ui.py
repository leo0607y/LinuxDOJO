"""ANSI カラー表示・アスキーアート・プログレスバー・テーブル描画ユーティリティ。

標準ライブラリのみで動作する。NO_COLOR 環境変数が設定されている場合は色を付けない。
日本語（全角文字）の表示幅を考慮して罫線を揃える。
"""
import os
import re
import shutil
import signal
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

# 画面共通のテキストマーカー（絵文字は使わない）。表示は必ずここの定数を使う。
OK = "[OK]"          # 成功・達成
NG = "[NG]"          # 失敗・不一致
WARN = "[!]"         # 注意・警告
HINT = "[ヒント]"    # ヒント
INFO = "[i]"         # 補足・進行中の通知
HEAD = "■"           # セクション見出しの先頭
DONE = "[x]"         # 完了済みの一覧マーク
TODO = "[ ]"         # 未完了の一覧マーク
FOOT_BACK = "Enter: 戻る"
FOOT_QUIT = "q: 戻る"


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
        elif ch in "\u200b\ufe0f":
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


def clip(s, w):
    """表示幅 w に収まるよう末尾を「…」で切り詰める（ANSI を含まない文字列用）。"""
    if width(s) <= w:
        return s
    out, cw = "", 0
    for ch in s:
        chw = width(ch)
        if cw + chw > w - 1:
            break
        out += ch
        cw += chw
    return out + "…"


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


_FLASH = []


def flash(message):
    """次に描画するメニューの入力欄の上へ出す一行メッセージを予約する。"""
    _FLASH.append(str(message))


def take_flash():
    """予約済みのメッセージを返して消す（なければ空文字）。"""
    text = "\n".join(_FLASH)
    del _FLASH[:]
    return c("  " + text.replace("\n", "\n  "), "yellow") + "\n" if text else ""


def term_rows():
    return shutil.get_terminal_size((100, 30)).lines


def invalid_choice(value, choices):
    """メニューで選べない入力をしたときのメッセージを予約する。"""
    shown = value if width(value) <= 20 else clip(value, 20)
    flash(f"{WARN} 「{shown}」は選べません。{choices} のいずれかを入力して Enter を押します。")


def clear():
    """画面とスクロールバックの両方を消す。前の画面まで遡ってスクロールできないようにする。"""
    if sys.stdout.isatty():
        sys.stdout.write("\x1b[H\x1b[2J\x1b[3J")
        sys.stdout.flush()


class QuestionScreen:
    """Keep the question above an independently scrolling response area.

    Use ``with QuestionScreen(lines, summary=[title, task]) as screen`` and call
    ``screen.refresh()`` before each prompt. A long explanation may give way to
    the complete summary, but the task is never silently shortened. Terminals
    too small for that summary, redirected output and TERM=dumb use plain output.
    This context owns no input handling and restores the normal scroll region on
    every exit, including exceptions and KeyboardInterrupt.
    """

    def __init__(self, header_lines, summary=None, min_body=8, color="green"):
        self.header_lines = list(header_lines)
        self.summary = list(summary) if summary is not None else self.header_lines
        self.min_body = max(4, min_body)
        self.color = color
        self.active = False
        self._size = None
        self._entered = False
        self._previous_resize = None
        self._resize_installed = False

    def _dimensions(self):
        try:
            return os.get_terminal_size(sys.stdout.fileno())
        except (AttributeError, OSError, ValueError):
            return shutil.get_terminal_size((80, 24))

    def _supported(self):
        return (sys.stdout.isatty() and sys.stdin.isatty()
                and os.environ.get("TERM", "") not in ("", "dumb"))

    def _lines(self, source, columns):
        return box(source, w=columns, color=self.color).splitlines()

    def _draw(self):
        dimensions = self._dimensions()
        self._size = dimensions
        columns, rows = dimensions
        # Leave the last column unused to avoid automatic wrapping in the header.
        usable = max(1, columns - 1)
        lines = self._lines(self.header_lines, usable)
        budget = rows - self.min_body
        if len(lines) > budget:
            lines = self._lines(self.summary, usable)
        if columns < 30 or budget < 2 or len(lines) > budget:
            if self.active:
                sys.stdout.write("\x1b[r\x1b[H\x1b[2J")
                self.active = False
            print("\n".join(self.header_lines))
            sys.stdout.flush()
            return
        sys.stdout.write("\x1b[r\x1b[H\x1b[2J")
        for row, line in enumerate(lines, 1):
            sys.stdout.write(f"\x1b[{row};1H" + line)
        top = len(lines) + 1
        sys.stdout.write(f"\x1b[{top};{rows}r\x1b[{top};1H")
        sys.stdout.flush()
        self.active = True

    def __enter__(self):
        self._entered = True
        if self._supported():
            self._draw()
            if hasattr(signal, "SIGWINCH"):
                try:
                    self._previous_resize = signal.getsignal(signal.SIGWINCH)
                    signal.signal(signal.SIGWINCH, self._on_resize)
                    self._resize_installed = True
                except (OSError, ValueError):
                    # Signal ownership is unavailable outside the main Python thread.
                    pass
        else:
            print(box(self.header_lines, color=self.color))
        return self

    def _on_resize(self, signum, frame):
        self.refresh()
        if callable(self._previous_resize):
            self._previous_resize(signum, frame)

    def refresh(self):
        """Reflow the fixed question after a terminal resize, not after an error."""
        if self._entered and self._supported() and self._dimensions() != self._size:
            self._draw()

    def __exit__(self, exc_type, exc_value, traceback):
        if self._resize_installed:
            signal.signal(signal.SIGWINCH, self._previous_resize)
            self._resize_installed = False
        if self.active:
            # Reset margins before returning control to a menu or the caller's shell.
            rows = self._dimensions().lines
            sys.stdout.write(f"\x1b[r\x1b[{rows};1H\n")
            sys.stdout.flush()
        self.active = False
        self._entered = False
        return False


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
