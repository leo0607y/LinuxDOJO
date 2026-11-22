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

USE_COLOR = (sys.stdout.isatty() and not os.environ.get("NO_COLOR")
             and os.environ.get("TERM", "") != "dumb")
if os.environ.get("LQ_FORCE_COLOR"):
    USE_COLOR = True

# パレットはここで一度だけ定義する。
#   アクセント: cyan（見出し・キー・コマンド） / 補助: dim / 成功: green / 失敗: red / 注意: yellow
# 旧来の色名（blue・magenta・bcyan など）はすべてアクセントに寄せ、画面ごとに色が散らばらないようにする。
ACCENT = "36"
CODES = {
    "reset": "0", "bold": "1", "dim": "2", "italic": "3", "under": "4", "blink": "5", "rev": "7",
    "black": "30", "red": "31", "green": "32", "yellow": "33", "white": "0",
    "gray": "2",
    "blue": ACCENT, "magenta": ACCENT, "cyan": ACCENT,
    "bred": "91", "bgreen": "92", "byellow": "33", "bblue": ACCENT,
    "bmagenta": ACCENT, "bcyan": ACCENT, "bwhite": "1",
    "accent": ACCENT, "ok": "32", "ng": "31", "warn": "33",
    "on_blue": "44", "on_magenta": "45", "on_green": "42", "on_red": "41", "on_gray": "100",
}
BORDER_TONES = {"red": "red", "yellow": "yellow", "ok": "green", "ng": "red", "warn": "yellow"}

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
NEXT = "[>]"          # 次に進む場所
PRODUCT = "LinuxDOJO"


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
    # 枠線は控えめ（dim）。赤・黄・緑は意味があるとき（NG・注意・OK）だけ。
    tone = BORDER_TONES.get(color)
    if tone:
        title_color, edge = tone, tone
    else:
        title_color, edge = "accent", "dim"
    body = []
    for ln in lines:
        for seg in str(ln).split("\n"):
            body.extend(wrap(seg, inner))
    out = []
    if title:
        t = f" {title} "
        rest = max(0, w - 2 - width(t) - 2)
        out.append(c("╭──", edge) + c(t, title_color, "bold") + c("─" * rest + "╮", edge))
    else:
        out.append(c("╭" + "─" * (w - 2) + "╮", edge))
    for ln in body:
        out.append(c("│ ", edge) + pad(ln, inner) + c(" │", edge))
    out.append(c("╰" + "─" * (w - 2) + "╯", edge))
    return "\n".join(out)


def progress_bar(ratio, n=10, full="█", empty="░", color="accent"):
    """ブロック文字の進捗バー。値がある限り最低 1 マス、100% 未満は最大でも n-1 マス。"""
    ratio = max(0.0, min(1.0, ratio))
    k = int(round(ratio * n))
    if 0 < ratio < 1:
        k = max(1, min(n - 1, k))
    return c(full * k, color) + c(empty * (n - k), "dim")


def table(headers, rows, colors=None):
    ws = [width(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            ws[i] = max(ws[i], width(str(cell)))
    sep = "  "
    out = [sep.join(c(pad(h, ws[i]), "bold") for i, h in enumerate(headers))]
    out.append(c(sep.join("─" * x for x in ws), "dim"))
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
    if sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb":
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


def hr(ch="─", color="dim", w=None):
    return c(ch * (w or term_width() - 2), color)


def rule(label=None, w=None):
    """見出し付きの区切り線。label があれば「── label ───」の形にする。w を省くと画面幅（左に 1 桁の余白）。"""
    margin = ""
    if w is None:
        w, margin = term_width() - 3, " "
    if not label:
        return margin + c("─" * w, "dim")
    return margin + c("── ", "dim") + c(label, "bold") + c(" " + "─" * max(0, w - width(label) - 4), "dim")


def header(crumbs=(), right="", w=None):
    """全画面共通のコンパクトな見出し（製品名 › 現在地 ... 右側の要約）と区切り線の 2 行。"""
    w = w or term_width() - 2
    left = " " + c(PRODUCT, "bold", "accent")
    for crumb in crumbs:
        left += c("  ›  ", "dim") + c(crumb, "bold") if crumb is crumbs[-1] else c("  ›  ", "dim") + crumb
    if right:
        room = w - width(left) - 2
        if width(strip_ansi(right)) > room:
            right = clip(strip_ansi(right), max(0, room))
        left += " " * max(2, w - width(left) - width(right) - 1) + right
    return left + "\n" + c("─" * w, "dim")


def menu_row(key, label, desc="", key_w=3, label_w=None, w=None, strong=False, tag="", tag_w=0):
    """番号キー・名前・短い説明を桁揃えした 1 行。label_w を揃えると説明が縦にそろう。

    tag（例: 現在）は名前の右に tag_w 桁の固定欄として出し、説明の位置をずらさない。
    """
    w = w or term_width() - 2
    k = pad(c(f"[{key}]", "bold", "accent"), key_w)
    lw = label_w if label_w is not None else width(label)
    lw = max(4, min(lw, w - 4 - key_w - 2 - (tag_w + 2 if tag_w else 0)))
    room = w - 4 - key_w - lw - 2 - (tag_w + 2 if tag_w else 0)
    text = pad(c(clip(label, lw), "bold") if strong else clip(label, lw), lw)
    row = f"  {k} {text}"
    if tag_w:
        row += "  " + pad(c(tag, "bold", "accent") if tag else "", tag_w)
    if desc and room >= 8:
        row += "  " + c(clip(desc, room), "dim")
    return row


def footer(*pairs):
    """画面下部のキー案内。("b", "戻る") のように並べる。全画面で同じ書式にそろえ、狭い端末では後ろの項目を省く。"""
    limit = term_width() - 4
    out = ""
    for k, v in pairs:
        item = f"{k} {v}".rstrip()
        trial = out + ("   " if out else "") + item
        if out and width(trial) > limit:
            break
        out = trial
    return c("  " + out, "dim")


def status_line(kind, text, detail=""):
    """OK / NG / 注意 / 補足 のフィードバック 1 行。色は意味に対応するときだけ付ける。"""
    marker, color = {"ok": (OK, "green"), "ng": (NG, "red"), "warn": (WARN, "yellow"),
                     "info": (INFO, "dim")}[kind]
    return "  " + c(marker, color, "bold") + " " + c(text, "bold" if kind != "info" else "dim") + (
        c("  " + detail, "dim") if detail else "")


TITLE_ART = r"""
  ██╗     ██╗███╗   ██╗██╗   ██╗██╗  ██╗    ██████╗  ██████╗      ██╗ ██████╗
  ██║     ██║████╗  ██║██║   ██║╚██╗██╔╝    ██╔══██╗██╔═══██╗     ██║██╔═══██╗
  ██║     ██║██╔██╗ ██║██║   ██║ ╚███╔╝     ██║  ██║██║   ██║     ██║██║   ██║
  ██║     ██║██║╚██╗██║██║   ██║ ██╔██╗     ██║  ██║██║   ██║██   ██║██║   ██║
  ███████╗██║██║ ╚████║╚██████╔╝██╔╝ ██╗    ██████╔╝╚██████╔╝╚█████╔╝╚██████╔╝
  ╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝    ╚═════╝  ╚═════╝  ╚════╝  ╚═════╝
"""

TITLE_ART_SMALL = r"""
  _     _                   ____   ___      _  ___
 | |   (_)_ __  _   ___  __|  _ \ / _ \    | |/ _ \
 | |   | | '_ \| | | \ \/ /| | | | | | |_  | | | | |
 | |___| | | | | |_| |>  < | |_| | |_| | |_| | |_| |
 |_____|_|_| |_|\__,_/_/\_\|____/ \___/ \___/ \___/
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


def title_art():
    art = TITLE_ART if term_width() >= 88 else TITLE_ART_SMALL
    return "\n".join(c(ln, "accent") for ln in art.strip("\n").split("\n"))


CLEAR_ART = r"""
  __  __ ___ ____ ____ ___ ___  _   _    ____ _     _____    _    ____  _
 |  \/  |_ _/ ___/ ___|_ _/ _ \| \ | |  / ___| |   | ____|  / \  |  _ \| |
 | |\/| || |\___ \___ \| | | | |  \| | | |   | |   |  _|   / _ \ | |_) | |
 | |  | || | ___) |__) | | |_| | |\  | | |___| |___| |___ / ___ \|  _ <|_|
 |_|  |_|___|____/____/___\___/|_| \_|  \____|_____|_____/_/   \_\_| \_(_)
"""


def clear_art():
    """クリア演出。大きな文字は幅が足りるときだけ。通常は 1 行の見出しにとどめる。"""
    if term_width() < 76 or term_rows() < 30:
        return ""
    return "\n".join(c(ln, "green", "bold") for ln in CLEAR_ART.strip("\n").split("\n"))
