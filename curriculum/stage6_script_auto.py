"""Stage 6: シェルスクリプトと自動化（8問）

判定はプレイヤーが書いたスクリプトを **実際に実行** して確かめる。
実行は毎回ランダムに作ったテスト用データ（$LQ_STATE 配下の一時ディレクトリ）に対して行い、
HOME も一時ディレクトリに差し替えるので、間違ったスクリプトでも本物の環境は壊れない。
"""
import datetime
import errno
import json
import os
import random
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time

from engine.runner import register
from engine import sim_cron

S = 6

SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"


# ------------------------------------------------------------------ helpers
class _Sandbox:
    """判定用の使い捨てディレクトリ（with 文で自動削除）。"""

    def __init__(self, ctx):
        ctx.state.mkdir(parents=True, exist_ok=True)
        self.path = tempfile.mkdtemp(prefix="lq6check-", dir=str(ctx.state))

    def __enter__(self):
        return self.path

    def __exit__(self, *a):
        for dp, dns, _ in os.walk(self.path):
            for n in dns:
                try:
                    os.chmod(os.path.join(dp, n), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.path, ignore_errors=True)


def _need_script(ctx, rel):
    """スクリプトの存在・shebang・改行コード・実行権限を確認して本文を返す。"""
    if not ctx.exists(rel):
        ctx.fail(f"`{rel}` がまだありません。エディタ（vim など）や `cat > {rel} <<'EOF'` で作成しましょう。")
    if ctx.isdir(rel):
        ctx.fail(f"`{rel}` がディレクトリになっています。スクリプトはファイルとして作りましょう。")
    text = ctx.read(rel) or ""
    if not text.strip():
        ctx.fail(f"`{rel}` が空っぽです。")
    first = text.splitlines()[0].strip()
    if not first.startswith("#!"):
        ctx.fail(f"`{rel}` の **1行目** に shebang（`#!/bin/bash`）がありません。どのプログラムで実行するかを OS に伝える大事な行です。")
    if "bash" not in first:
        ctx.fail(f"`{rel}` の shebang が `{first}` です。このステージでは bash の機能（`[[ ]]` など）を使うので `#!/bin/bash` または `#!/usr/bin/env bash` にしましょう。")
    if "\r" in text:
        ctx.fail(f"`{rel}` の改行コードが Windows 形式（CRLF）です。`sed -i 's/\\r$//' {rel}` で LF に直しましょう。")
    if not os.access(ctx.p(rel), os.X_OK):
        ctx.fail(f"`{rel}` に実行権限がありません（`./{rel}` で実行できない状態）。`chmod +x {rel}` を忘れずに。")
    return text


def _run(ctx, rel, args=(), cwd=None, env_extra=None, home=None, timeout=6):
    """プレイヤーのスクリプトを ./script と同じように直接実行し (rc, stdout, stderr) を返す。"""
    env = {"PATH": SAFE_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TERM": "dumb",
           "HOME": home or cwd or str(ctx.work), "USER": os.environ.get("USER", "penguin"),
           "LQ_SESSION": ctx.token or "none"}
    env.update(env_extra or {})
    try:
        p = subprocess.Popen([str(ctx.p(rel)), *map(str, args)], cwd=cwd or str(ctx.work), env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
    except PermissionError:
        ctx.fail(f"`{rel}` を実行できません（Permission denied）。`chmod +x {rel}` で実行権限を付けましょう。")
    except OSError as e:
        if e.errno == errno.ENOEXEC:
            ctx.fail(f"`{rel}` を実行できません（Exec format error）。1行目を `#!/bin/bash` にしましょう。")
        ctx.fail(f"`{rel}` を実行できません: {e.strerror}")
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        ctx.fail(f"`{rel}` が {timeout} 秒たっても終わりません。無限ループや、標準入力（キーボード）待ちになっていませんか？")
    return p.returncode, out.decode(errors="replace"), err.decode(errors="replace")


def _show(args):
    return " ".join(shlex.quote(str(a)) for a in args) if args else "（引数なし）"


def _nonempty(text):
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


# ------------------------------------------------------------------ 6-1
NAMES61 = ["Tux", "Penguin", "Alice", "Bob", "Sato", "Suzuki", "Yamada", "Linus", "Ken", "Dennis"]
SPACED61 = ["Tux Penguin", "Linux Taro", "Shell Hanako", "Bash Jiro"]
GREETS61 = ["Konnichiwa", "Hi", "Yo", "Hola", "Bonjour", "Ohayo"]

GREET_SOL = r"""#!/bin/bash
greeting="${GREETING:-Hello}"
echo "引数の数: $#"
for name in "$@"; do
  echo "$greeting, $name!"
done"""


def s61(ctx):
    ctx.write("README.txt", "greet.sh を作ってください。詳しくは `mission` で確認できます。\n")


def _greet_expect(args, greet):
    return [f"引数の数: {len(args)}"] + [f"{greet}, {a}!" for a in args]


def c61(ctx):
    _need_script(ctx, "greet.sh")
    rnd = random.Random()
    cases = [
        (rnd.sample(NAMES61, 2) + [rnd.choice(SPACED61)], None),
        ([rnd.choice(SPACED61)] + rnd.sample(NAMES61, rnd.randint(1, 3)), rnd.choice(GREETS61)),
        ([], None),
    ]
    with _Sandbox(ctx) as tmp:
        for args, greet in cases:
            extra = {"GREETING": greet} if greet else None
            rc, out, err = _run(ctx, "greet.sh", args, cwd=tmp, env_extra=extra)
            got = _nonempty(out)
            want = _greet_expect(args, greet or "Hello")
            label = f"`./greet.sh {_show(args)}`" + (f"（環境変数 GREETING={greet}）" if greet else "")
            if rc != 0:
                ctx.fail(f"{label} が終了コード {rc} で失敗しました。エラー: {err.strip()[:150]}")
            if not got or not re.fullmatch(rf"引数の数\s*[:：]\s*{len(args)}", got[0].strip()):
                ctx.fail(f"{label} の1行目は `引数の数: {len(args)}` になるはずですが、`{got[0] if got else '(出力なし)'}` でした。引数の個数は `$#` で取れます。")
            if got[1:] == want[1:]:
                continue
            if greet and got[1:] == _greet_expect(args, "Hello")[1:]:
                ctx.fail(f"{label} でも `Hello` と表示されました。挨拶の言葉を変数にして、環境変数 GREETING があればそれを使う（`${{GREETING:-Hello}}`）ようにしましょう。")
            spaced = [a for a in args if " " in a]
            if spaced and any(ln.endswith(f", {spaced[0].split()[0]}!") for ln in got[1:]):
                ctx.fail(f"{label} で、空白を含む名前「{spaced[0]}」が2つに分かれてしまいました。`for name in \"$@\"` のように **ダブルクォート付きの `\"$@\"`** を使いましょう。")
            if len(got) - 1 < len(args):
                ctx.fail(f"{label} で {len(args)} 人分の挨拶が出ていません（{len(got) - 1} 行）。`$1` だけでなく、全部の引数をループで処理しましょう。")
            ctx.fail(f"{label} の出力が期待と違います。\n  期待: {' / '.join(want)}\n  実際: {' / '.join(got)}")


register(
    id="6-1", stage=S, title="初めてのシェルスクリプト",
    story="""
毎日同じコマンドを手で打っていないだろうか？ 手順を **ファイルに書いて実行できる** ようにしたものがシェルスクリプトだ。
手始めに、渡された名前全員に挨拶するスクリプト `greet.sh` を作ってみよう。
引数（`./greet.sh Tux "Linux Taro"`）の受け取り方、変数、そして「実行できるファイル」にするための作法を身に付けるのが目標だ。
""",
    objectives=["`greet.sh` を作成し、1行目に shebang `#!/bin/bash` を書き、実行権限を付ける（`./greet.sh` で動くこと）",
                "1行目に `引数の数: N`（N は引数の個数）を出力する",
                "続けて、引数1つにつき1行 `Hello, 名前!` を出力する（`\"Linux Taro\"` のような **空白入りの名前も1人** として扱う）",
                "挨拶の言葉は変数に入れ、環境変数 `GREETING` が設定されていればそれを使う（例: `GREETING=Hi ./greet.sh Tux` → `Hi, Tux!`）"],
    hints=["スクリプトは「コマンドを並べたテキストファイル」です。1行目の `#!` で実行するプログラムを指定し、`chmod +x` で実行可能にします。",
           "引数の個数は `$#`、全引数は `\"$@\"`（1個ずつ正しく分けてくれる）。`for name in \"$@\"; do ...; done` でループ。"
           "既定値付きの変数展開は `${GREETING:-Hello}`（未設定なら Hello）。",
           "`vim greet.sh` で次を書いて `chmod +x greet.sh`:\n  #!/bin/bash\n  greeting=\"${GREETING:-Hello}\"\n  echo \"引数の数: $#\"\n  for name in \"$@\"; do echo \"$greeting, $name!\"; done"],
    answer="cat > greet.sh <<'EOF'\n" + GREET_SOL + "\nEOF\nchmod +x greet.sh\n./greet.sh Tux \"Linux Taro\"\nGREETING=Hi ./greet.sh Alice",
    explanation="""
・**shebang**（`#!/bin/bash`）… 1行目に書く「このファイルは bash で実行してね」という指定。無いと `./greet.sh` で意図しないシェルが使われます
・**実行権限** … `chmod +x greet.sh` で `./greet.sh` として起動できる（無ければ `bash greet.sh` で読ませることは可能）
・**変数** … `name=値`（`=` の前後にスペースを入れない！）、参照は `"$name"`
・**位置パラメータ** … `$0`=スクリプト名、`$1` `$2`…=各引数、`$#`=引数の個数
・`"$@"` … 全引数を「1個ずつ」正しく展開。`$@` や `$*` をクォートなしで使うと `Linux Taro` が `Linux` と `Taro` に分裂します
・`${VAR:-既定値}` … VAR が未設定（または空）なら既定値を使う。設定の上書きを環境変数で受け付ける定番パターン
・`GREETING=Hi ./greet.sh` … そのコマンド1回だけに環境変数を渡す書き方
""",
    tip="""
スクリプトの変数は **基本すべてダブルクォート** で囲む（`"$var"`）のがプロの習慣です。ファイル名に空白が入っていた途端に壊れる…
という事故の大半はクォート忘れが原因。`shellcheck greet.sh` という静的解析ツールを入れておくと、こうしたミスを自動で指摘してくれます。
""",
    setup=s61, check=c61,
    solution="cat > greet.sh <<'EOF'\n" + GREET_SOL + "\nEOF\nchmod +x greet.sh",
    wrong=["cat > greet.sh <<'EOF'\n" + GREET_SOL + "\nEOF",
           "cat > greet.sh <<'EOF'\n" + GREET_SOL.replace('"$@"', "$@") + "\nEOF\nchmod +x greet.sh",
           "cat > greet.sh <<'EOF'\n" + GREET_SOL.replace('${GREETING:-Hello}', 'Hello') + "\nEOF\nchmod +x greet.sh",
           "cat > greet.sh <<'EOF'\n" + GREET_SOL.split("\n", 1)[1] + "\nEOF\nchmod +x greet.sh"],
)


# ------------------------------------------------------------------ 6-2
CHECK_SOL = r"""#!/bin/bash
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 FILE" >&2
  exit 1
fi
file=$1
if [[ ! -e $file ]]; then
  echo "NG: $file は存在しません"
  exit 2
elif [[ ! -s $file ]]; then
  echo "EMPTY: $file は空です"
  exit 3
else
  echo "OK: $file"
fi"""


def s62(ctx):
    ctx.write("samples/access.log", "GET / 200\nGET /login 200\n")
    ctx.write("samples/empty.log", "")
    ctx.write("README.txt", "check_file.sh を作り、samples/ の中のファイルで試してみましょう。\n")


def c62(ctx):
    _need_script(ctx, "check_file.sh")
    tag = ctx.rand(4).lower()
    with _Sandbox(ctx) as tmp:
        ok_name, empty_name = f"report_{tag}.log", f"empty_{tag}.log"
        sp_empty, sp_ok, sp_none = f"empty file {tag}.txt", f"my report {tag}.txt", f"no such {tag}.txt"
        for n, body in ((ok_name, "line1\nline2\n"), (empty_name, ""), (sp_empty, ""), (sp_ok, "hello\n")):
            with open(os.path.join(tmp, n), "w") as f:
                f.write(body)
        cases = [
            ([], 1, None), ([ok_name, empty_name], 1, None),
            ([ok_name], 0, "OK"), ([f"missing_{tag}.log"], 2, "NG"), ([empty_name], 3, "EMPTY"),
            ([sp_ok], 0, "OK"), ([sp_empty], 3, "EMPTY"), ([sp_none], 2, "NG"),
        ]
        for args, want_rc, word in cases:
            rc, out, err = _run(ctx, "check_file.sh", args, cwd=tmp)
            label = f"`./check_file.sh {_show(args)}`"
            if word is None:  # 使い方エラー
                if rc != 1:
                    ctx.fail(f"{label} の終了コードが {rc} でした。引数の数が1つでないときは使い方を表示して `exit 1` しましょう。")
                if not re.search(r"usage|使い方", err, re.I):
                    if re.search(r"usage|使い方", out, re.I):
                        ctx.fail(f"{label} の使い方メッセージが **標準出力** に出ています。エラーメッセージは `>&2` で標準エラー出力に出しましょう。")
                    ctx.fail(f"{label} で、標準エラー出力に `Usage: ...` という使い方の表示がありません。")
                continue
            first = (_nonempty(out) or [""])[0]
            spaced = " " in args[0]
            if rc != want_rc or not first.startswith(word):
                extra = ""
                if spaced and "argument" in err:
                    extra = "（`too many arguments` エラーが出ています。空白入りのファイル名でも壊れないよう `[[ ]]` を使うか、`\"$1\"` をダブルクォートで囲みましょう）"
                elif word == "EMPTY" and first.startswith("OK"):
                    extra = "（空のファイルも OK になっています。`-s`（サイズが0より大きい）でのチェックを追加しましょう）"
                ctx.fail(f"{label} は `{word}: ...` を出力して終了コード {want_rc} になるはずですが、"
                         f"出力「{first or '(なし)'}」・終了コード {rc} でした。{extra}")
            if args[0] not in first:
                ctx.fail(f"{label} のメッセージにファイル名「{args[0]}」が含まれていません。")


register(
    id="6-2", stage=S, title="条件分岐と終了コードで「壊れにくい」スクリプトに",
    story="""
運用チームから「ログファイルの状態を確認するスクリプトが欲しい。**監視ツールから呼ぶので、結果は終了コードで返してほしい**」と依頼された。
スクリプトの世界では「`0` = 成功、`0` 以外 = 何かあった」がお約束。引数の付け忘れにも、使い方を教えてあげる親切設計にしよう。
""",
    objectives=["`check_file.sh` を作成（shebang + 実行権限）。引数はファイル名1つ",
                "引数が1つでない → 標準エラー出力に `Usage: ...` を表示して **終了コード 1**",
                "ファイルが存在しない → `NG: ファイル名 ...` を表示して **終了コード 2**",
                "ファイルが空（0バイト） → `EMPTY: ファイル名 ...` を表示して **終了コード 3**",
                "それ以外 → `OK: ファイル名` を表示して **終了コード 0**（`my report.txt` のような空白入りの名前でも正しく動くこと）"],
    hints=["`if 条件; then ...; elif 条件; then ...; else ...; fi` で分岐、`exit 数字` で終了コードを返します。直前のコマンドの終了コードは `echo $?` で確認できます。",
           "テスト演算子: `[[ $# -ne 1 ]]`（数値が等しくない）、`[[ -e $f ]]`（存在する）、`[[ -s $f ]]`（サイズが0より大きい）、`!` で否定。標準エラーへは `echo ... >&2`。",
           "if [[ $# -ne 1 ]]; then echo \"Usage: $0 FILE\" >&2; exit 1; fi\n  if [[ ! -e $1 ]]; then echo \"NG: $1\"; exit 2\n  elif [[ ! -s $1 ]]; then echo \"EMPTY: $1\"; exit 3\n  else echo \"OK: $1\"; fi"],
    answer="cat > check_file.sh <<'EOF'\n" + CHECK_SOL + "\nEOF\nchmod +x check_file.sh\n./check_file.sh; echo \"終了コード: $?\"\n./check_file.sh samples/access.log; echo $?\n./check_file.sh samples/empty.log; echo $?",
    explanation="""
・**終了コード** … `exit N` で返す。`$?` で直前の値を確認。`0`=成功、`1`〜`255`=失敗（意味はスクリプトごとに決める）
・`[ ]`（test コマンド）と `[[ ]]`（bash の拡張）:
  ・`-e` 存在する ／ `-f` 通常ファイル ／ `-d` ディレクトリ ／ `-s` 空でない ／ `-x` 実行可能
  ・数値比較 `-eq -ne -lt -le -gt -ge`、文字列比較 `==` `!=`、`[[ ]]` なら `=~` で正規表現も使える
  ・注意: `[ -e $1 ]` は空白入りのファイル名で `too many arguments` になる。`[ -e "$1" ]` とクォートするか、
    単語分割されない `[[ ]]` を使うのが安全です
・`echo "..." >&2` … 標準エラー出力へ。エラーや使い方は stderr に出すと、`./x.sh > out.txt` しても画面で気付けます
・`$0` … 実行されたスクリプト名。Usage 表示に使うと名前を変えても表示が追従します
・短く書くなら `[[ -s $f ]] || { echo "EMPTY"; exit 3; }` のような `&&` / `||` の連結も定番です
""",
    tip="""
監視ツール（Nagios / Zabbix / Kubernetes の liveness probe など）や CI は、まさに **終了コードだけ** を見て成否を判断します。
`if ./check_file.sh app.log; then ...` のように、自作スクリプトを他のコマンドと同じ感覚で組み合わせられるのが終了コードを正しく返す最大の利点。
`grep -q` / `test` / `curl -f` など「終了コードで答えるコマンド」を知っておくとスクリプトが一気に書きやすくなります。
""",
    setup=s62, check=c62,
    solution="cat > check_file.sh <<'EOF'\n" + CHECK_SOL + "\nEOF\nchmod +x check_file.sh",
    wrong=["cat > check_file.sh <<'EOF'\n" + CHECK_SOL.replace("  exit 1\n", "  exit 0\n") + "\nEOF\nchmod +x check_file.sh",
           "cat > check_file.sh <<'EOF'\n" + CHECK_SOL.replace('-s $file', '-e $file') + "\nEOF\nchmod +x check_file.sh",
           "cat > check_file.sh <<'EOF'\n" + CHECK_SOL.replace("[[ ! -e $file ]]", "[ ! -e $file ]").replace("[[ ! -s $file ]]", "[ ! -s $file ]") + "\nEOF\nchmod +x check_file.sh",
           "cat > check_file.sh <<'EOF'\n" + CHECK_SOL.replace('FILE" >&2', 'FILE"') + "\nEOF\nchmod +x check_file.sh"],
)


# ------------------------------------------------------------------ 6-3
ROLES63 = ["admin", "developer", "operator", "viewer", "designer"]
USERS63 = ["sato", "suzuki", "takahashi", "tanaka", "ito", "watanabe", "yamamoto", "nakamura", "kobayashi", "kato"]


def s63(ctx):
    n = random.randint(8, 13)
    nums = random.sample(range(1000, 9990), n)
    jpgs = [f"IMG_{x}.JPG" for x in nums]
    spaced = [f"Trip Day{i} {ctx.rand(3)}.JPG" for i in range(1, random.randint(3, 4))]
    for name in jpgs + spaced:
        ctx.write(f"photos/{name}", f"jpeg-data {name}\n")
    ctx.write("photos/IMG_0001.jpg", "already lower\n")
    ctx.write("photos/raw_IMG.JPG.bak", "backup\n")
    ctx.write("photos/memo.txt", "旅行の写真\n")
    ctx.data["photos_want"] = sorted([n[:-4] + ".jpg" for n in jpgs + spaced] +
                                     ["IMG_0001.jpg", "raw_IMG.JPG.bak", "memo.txt"])
    ctx.data["jpg_count"] = len(jpgs) + len(spaced)

    users = random.sample(USERS63, random.randint(5, 7))
    roles = {u: random.choice(ROLES63) for u in users}
    lines = ["# 新メンバー一覧（名前 ロール）", ""]
    for i, u in enumerate(users):
        lines.append(f"{u} {roles[u]}")
        if i == 2:
            lines.append("# --- ここから第2陣 ---")
    lines.append("")
    ctx.write("members.txt", "\n".join(lines) + "\n")
    ctx.data["roles"] = roles


def c63(ctx):
    want = ctx.data["photos_want"]
    if not ctx.isdir("photos"):
        ctx.fail("`photos/` ディレクトリが消えています。`reset_mission` でやり直しましょう。")
    got = sorted(os.listdir(ctx.p("photos")))
    if got != want:
        left = [g for g in got if g.endswith(".JPG")]
        if any(g.lower() == g and g.startswith("img_") for g in got):
            ctx.fail("ファイル名全体が小文字になっています（`img_1234.jpg`）。変えるのは **拡張子だけ** です。`${f%.JPG}.jpg` を使いましょう。")
        if any(g.startswith("Trip") and g.endswith(".JPG") for g in left):
            ctx.fail("空白を含むファイル（`Trip Day1 ....JPG`）がリネームされていません。`for f in photos/*.JPG` と `\"$f\"` のクォートで、空白入りの名前も1つとして扱いましょう。")
        if left:
            ctx.fail(f"まだ拡張子が `.JPG` のファイルが {len(left)} 個残っています（例: `{left[0]}`）。")
        if "raw_IMG.jpg.bak" in got or "raw_IMG.JPG.bak" not in got:
            ctx.fail("`raw_IMG.JPG.bak` は `.JPG` で **終わらない** ので変更対象外です。元に戻しましょう（`reset_mission` も可）。")
        missing = sorted(set(want) - set(got))
        extra = sorted(set(got) - set(want))
        ctx.fail(f"`photos/` の中身が期待と違います。足りない: {missing[:3]} / 余計: {extra[:3]}")

    roles = ctx.data["roles"]
    if not ctx.isdir("accounts"):
        ctx.fail("`accounts/` ディレクトリがありません。`members.txt` を1行ずつ読んで `accounts/名前/profile.txt` を作りましょう。")
    entries = sorted(os.listdir(ctx.p("accounts")))
    extra = [e for e in entries if e not in roles]
    if extra:
        if any(e.startswith("#") for e in extra) or "profile.txt" in extra:
            ctx.fail(f"`accounts/` に余計なもの（{extra[0]!r}）ができています。`#` で始まるコメント行と空行は **読み飛ばし** ましょう（`[[ -z $name || $name == \\#* ]] && continue`）。")
        ctx.fail(f"`accounts/` に members.txt に無い名前があります: {extra[:3]}")
    for u, r in roles.items():
        prof = ctx.read(f"accounts/{u}/profile.txt")
        if prof is None:
            ctx.fail(f"`accounts/{u}/profile.txt` がありません（全 {len(roles)} 人分作りましょう）。")
        if prof.strip() != f"role={r}":
            ctx.fail(f"`accounts/{u}/profile.txt` の内容が「{prof.strip()[:40]}」です。`role={r}` の1行にしましょう。")


register(
    id="6-3", stage=S, title="ループで一括処理: 大量リネームとアカウント作成",
    story="""
デジカメから取り込んだ写真の拡張子が大文字 `.JPG` で、Web システムが受け付けてくれない。しかも <<jpg_count>> 枚もある！
さらに人事からは「`members.txt` の新メンバー全員分、`accounts/名前/profile.txt` を作って」と頼まれた。
1つずつ手でやるのは時間の無駄。**ループ** で一気に片付けよう。
""",
    objectives=["`photos/` の中の `*.JPG` を、名前はそのままで拡張子だけ `.jpg` に変える（空白入りの名前も含む。`raw_IMG.JPG.bak` や `memo.txt` は対象外）",
                "`members.txt`（`名前 ロール` の形式）を1行ずつ読み、メンバーごとに `accounts/名前/profile.txt` を作って `role=ロール` と書く",
                "`#` で始まるコメント行と空行は読み飛ばす"],
    hints=["ファイルの一括処理は `for` ループ、ファイルの各行を処理するなら `while read` ループが定番です。",
           "`for f in photos/*.JPG; do mv -- \"$f\" \"${f%.JPG}.jpg\"; done`（`${変数%パターン}` で末尾を削除）。"
           "行の読み込みは `while read -r name role; do ...; done < members.txt`。",
           "while read -r name role; do\n    [[ -z $name || $name == \\#* ]] && continue\n    mkdir -p \"accounts/$name\" && echo \"role=$role\" > \"accounts/$name/profile.txt\"\n  done < members.txt"],
    answer="""for f in photos/*.JPG; do
  mv -v -- "$f" "${f%.JPG}.jpg"
done
while read -r name role; do
  [[ -z $name || $name == \\#* ]] && continue   # 空行とコメントを飛ばす
  mkdir -p "accounts/$name"
  echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt
ls photos; cat accounts/*/profile.txt""",
    explanation="""
・`for 変数 in リスト; do ...; done` … リストの要素ごとに繰り返し。`photos/*.JPG` のグロブは空白入りの名前も **1要素** として扱ってくれる
  注意: `for f in $(ls photos)` は空白でファイル名が分裂するので NG。ファイルの列挙は必ずグロブで
・**パラメータ展開** … `${f%.JPG}` 末尾の `.JPG` を削る ／ `${f#photos/}` 先頭を削る ／ `${f/old/new}` 置換 ／ `${f,,}` 小文字化
・`mv -- "$f" ...` … `--` は「ここから先はオプションではない」の印。`-` で始まるファイル名対策
・`while read -r a b; do ...; done < file` … 1行ずつ読み、空白区切りで変数に入れる（余りは最後の変数へ）。`-r` はバックスラッシュをそのまま読む
・`[[ $name == \\#* ]]` … `==` の右辺はパターン。`#` で始まるか判定（`#` はコメント記号なのでエスケープ）
・`continue` で次の周へ、`break` でループを抜ける。`for i in {1..10}` や `for ((i=0; i<5; i++))` という書き方もあります
""",
    tip="""
一括リネームは **まず echo で予行演習** が鉄則: `for f in photos/*.JPG; do echo mv "$f" "${f%.JPG}.jpg"; done` で
実行されるコマンドを目で確認してから `echo` を外します。Perl 版の `rename 's/\\.JPG$/.jpg/' *.JPG` や
`mmv` というツールもありますが、for + パラメータ展開はどの Linux でも使える最強の基本技です。
""",
    setup=s63, check=c63,
    solution="""for f in photos/*.JPG; do mv -- "$f" "${f%.JPG}.jpg"; done
while read -r name role; do
  [[ -z $name || $name == \\#* ]] && continue
  mkdir -p "accounts/$name"
  echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt""",
    wrong=["""for f in $(ls photos/*.JPG); do mv "$f" "${f%.JPG}.jpg"; done
while read -r name role; do
  [[ -z $name || $name == \\#* ]] && continue
  mkdir -p "accounts/$name"; echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt""",
           """cd photos; for f in *.JPG; do mv -- "$f" "$(echo "$f" | tr A-Z a-z)"; done; cd ..
while read -r name role; do
  [[ -z $name || $name == \\#* ]] && continue
  mkdir -p "accounts/$name"; echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt""",
           """for f in photos/*.JPG; do mv -- "$f" "${f%.JPG}.jpg"; done
while read -r name role; do
  mkdir -p "accounts/$name"; echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt""",
           """for f in photos/*JPG*; do mv -- "$f" "${f/JPG/jpg}"; done
while read -r name role; do
  [[ -z $name || $name == \\#* ]] && continue
  mkdir -p "accounts/$name"; echo "role=$role" > "accounts/$name/profile.txt"
done < members.txt"""],
)


# ------------------------------------------------------------------ 6-4
CLEANUP_ORIG = """#!/bin/bash
# 一時ファイル掃除スクリプト（※危険なバージョン）
#   使い方: ./cleanup.sh 掃除するディレクトリ
target=$1
cd $target
rm -f *.tmp
echo "cleanup done: $target"
"""

CLEANUP_SOL = r"""#!/bin/bash
set -euo pipefail

log() {
  echo "[INFO] $*"
}

main() {
  local target=$1
  cd "$target"
  rm -f -- *.tmp
  log "cleanup done: $target"
}

main "$@"
""".rstrip("\n")


def s64(ctx):
    ctx.write("cleanup.sh", CLEANUP_ORIG, mode=0o755)
    ctx.write("work area/a.tmp", "tmp\n")
    ctx.write("work area/b.tmp", "tmp\n")
    ctx.write("work area/result.csv", "id,value\n1,42\n")
    ctx.write("INCIDENT.txt", """【障害報告】cleanup.sh による誤削除
  原因: ディレクトリ名を打ち間違えたまま実行 → cd に失敗したのに処理が続行し、
        **カレントディレクトリ** の *.tmp（作業中のデータ）が消えた。
  対策: 失敗したら即座に止まる「安全なスクリプト」に直すこと。
""")


def _set_flags(text):
    flags = set()
    for ln in text.splitlines():
        m = re.match(r"\s*set\s+(.*)", ln)
        if not m:
            continue
        toks = m.group(1).split("#")[0].split()
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "-o" and i + 1 < len(toks):
                flags.add(toks[i + 1])
                i += 1
            elif re.fullmatch(r"-[a-zA-Z]+", t):
                letters = t[1:]
                if letters.endswith("o") and i + 1 < len(toks):
                    flags.update(letters[:-1])
                    flags.add(toks[i + 1])
                    i += 1
                else:
                    flags.update(letters)
            i += 1
    alias = {"errexit": "e", "nounset": "u"}
    return {alias.get(f, f) for f in flags}


def c64(ctx):
    text = _need_script(ctx, "cleanup.sh")
    flags = _set_flags(text)
    miss = [name for key, name in (("e", "-e（エラーで即終了）"), ("u", "-u（未定義変数をエラーに）"),
                                   ("pipefail", "-o pipefail（パイプ途中の失敗も検出）")) if key not in flags]
    if miss:
        ctx.fail(f"`cleanup.sh` に `set -euo pipefail` が足りません。不足: {'、'.join(miss)}。shebang の直後に書きましょう。")
    if not re.search(r"^\s*(function\s+log\b|log\s*\(\s*\))", text, re.M):
        ctx.fail("`log` 関数が定義されていません。`log() { echo \"[INFO] $*\"; }` のように定義しましょう。")
    with _Sandbox(ctx) as tmp:
        home, here, tgt = (os.path.join(tmp, d) for d in ("home", "here", "old logs"))
        for d in (home, here, tgt):
            os.makedirs(d)
        for p in (os.path.join(home, "keep_me.tmp"), os.path.join(here, "important.tmp"),
                  os.path.join(tgt, "a.tmp"), os.path.join(tgt, "b c.tmp")):
            with open(p, "w") as f:
                f.write("data\n")
        with open(os.path.join(tgt, "report.csv"), "w") as f:
            f.write("keep\n")

        def survived(label):
            if not os.path.exists(os.path.join(home, "keep_me.tmp")):
                ctx.fail(f"{label} で、**ホームディレクトリ** の *.tmp が消えてしまいました！ 引数なしの `cd` はホームに移動します。"
                         "`set -u` で未定義の `$1` を即エラーにしましょう（`${1:-}` で回避しないこと）。")
            if not os.path.exists(os.path.join(here, "important.tmp")):
                ctx.fail(f"{label} で、**カレントディレクトリ** の important.tmp が消えてしまいました！ 失敗した `cd` の後も処理が続いています。")

        rc, out, err = _run(ctx, "cleanup.sh", [], cwd=here, home=home)
        survived("`./cleanup.sh`（引数なし）")
        if rc == 0:
            ctx.fail("`./cleanup.sh`（引数なし）が終了コード 0（成功）で終わりました。引数が無いときは失敗として止まるべきです。")
        bad = f"no_such_dir_{ctx.rand(4)}"
        rc, out, err = _run(ctx, "cleanup.sh", [bad], cwd=here, home=home)
        survived(f"`./cleanup.sh {bad}`（存在しないディレクトリ）")
        if rc == 0:
            ctx.fail(f"`./cleanup.sh {bad}` が成功扱い（終了コード 0）になりました。`cd` の失敗で即終了させましょう（`set -e`）。")
        rc, out, err = _run(ctx, "cleanup.sh", [tgt], cwd=here, home=home)
        left = sorted(n for n in os.listdir(tgt) if n.endswith(".tmp"))
        if rc != 0 or left:
            hint = ""
            if "argument" in err or "No such file" in err:
                hint = "空白入りのディレクトリ名で `cd` に失敗しています。`cd \"$target\"` のように **ダブルクォート** で囲みましょう。"
            ctx.fail(f"`./cleanup.sh \"old logs\"`（正しい空白入りディレクトリ）で掃除できていません（終了コード {rc}、残った tmp: {left}）。{hint}"
                     + (f"\n  エラー: {err.strip()[:150]}" if err.strip() else ""))
        if not os.path.exists(os.path.join(tgt, "report.csv")):
            ctx.fail("`*.tmp` 以外のファイル（report.csv）まで消えています。")
        survived("`./cleanup.sh \"old logs\"`")
        if not re.search(r"^\[INFO\]", out + "\n" + err, re.M):
            ctx.fail("正常終了時に `[INFO] ...` というログが出ていません。完了メッセージは `log` 関数で出しましょう。")


register(
    id="6-4", stage=S, title="関数と set -euo pipefail で安全なスクリプト",
    story="""
昨日、`cleanup.sh` のせいで作業中のデータが消える事故が起きた（`INCIDENT.txt` を参照）。
原因は「`cd` に失敗したのに、何事もなかったかのように `rm` が実行された」こと。
bash は **エラーが起きても止まらない** のが標準動作なのだ。スクリプトを「失敗したら即止まる」安全な作りに直そう。
""",
    objectives=["`cleanup.sh` の先頭（shebang の次）に `set -euo pipefail` を書く",
                "`log` 関数を定義し（`[INFO] メッセージ` を出力）、完了メッセージを `log` で出す",
                "引数なし・存在しないディレクトリ指定のときは、何も消さずに **0 以外の終了コード** で止まる",
                "`./cleanup.sh \"work area\"` のような **空白入りのディレクトリ** も正しく掃除できる（変数はダブルクォート）"],
    hints=["`set -e` はコマンドが失敗した時点でスクリプトを終了、`set -u` は未定義変数の参照をエラーに、`set -o pipefail` はパイプの途中の失敗も失敗扱いにします。",
           "関数は `名前() { 処理; }` で定義し、`名前 引数...` で呼びます。関数内の引数も `$1` や `$*`。`cd $target` は `cd \"$target\"` に。",
           "#!/bin/bash\n  set -euo pipefail\n  log() { echo \"[INFO] $*\"; }\n  target=$1\n  cd \"$target\"\n  rm -f -- *.tmp\n  log \"cleanup done: $target\""],
    answer="vim cleanup.sh     # 以下の内容に修正\n" + CLEANUP_SOL + "\n\n# 動作確認\n./cleanup.sh; echo $?            # unbound variable で止まる\n./cleanup.sh nodir; echo $?      # cd に失敗して止まる\n./cleanup.sh \"work area\"; ls \"work area\"",
    explanation="""
・`set -e`（errexit）… 失敗したコマンドがあった時点で終了。`cd` 失敗後の `rm` 暴走を防ぐ
・`set -u`（nounset）… 未定義変数の参照をエラーに。`$1` が無いまま `cd $target` → **ホームディレクトリに移動** して削除…という事故を防ぐ
  （意図的に省略可能にしたい変数は `${1:-既定値}` と書く）
・`set -o pipefail` … `cmd1 | cmd2` で cmd1 が失敗しても通常は cmd2 の結果で成功扱い。これを「失敗」として検出する
・**関数** … `log() { echo "[INFO] $*"; }`。`local 変数` で関数内だけの変数に。最後に `main "$@"` と書いて全体を関数にまとめる流儀も人気
・`rm -f -- *.tmp` … `--` で `-rf.tmp` のような名前もオプション扱いされない
・注意: `set -e` の落とし穴: `if` の条件・`&&` `||` の左側・`!` 付きのコマンドは失敗しても止まりません。
  「失敗してもよい」コマンドには `cmd || true` と明示します
・エラー時の後片付けは `trap 'rm -f "$tmpfile"' EXIT` のように trap で登録できます
""",
    tip="""
`#!/bin/bash` の直後に `set -euo pipefail` は「Bash Strict Mode」と呼ばれ、現場のスクリプトでは事実上の標準です。
それでも `rm -rf "$DIR/"*` のように変数を使った削除は、`${DIR:?DIR が未設定です}`（未設定ならエラーで止まる）で二重に守るのがベテランの作法。
`bash -n script.sh` で文法チェック、`bash -x script.sh` で1行ずつ実行内容を表示しながらデバッグできます。
""",
    setup=s64, check=c64,
    solution="cat > cleanup.sh <<'EOF'\n" + CLEANUP_SOL + "\nEOF",
    wrong=["cat > cleanup.sh <<'EOF'\n" + CLEANUP_SOL.replace("set -euo pipefail", "set -e") + "\nEOF",
           "cat > cleanup.sh <<'EOF'\n" + CLEANUP_SOL.replace("local target=$1", "local target=${1:-}") + "\nEOF",
           "cat > cleanup.sh <<'EOF'\n" + CLEANUP_SOL.replace('cd "$target"', "cd $target") + "\nEOF",
           "cat > cleanup.sh <<'EOF'\n#!/bin/bash\nset -euo pipefail\ntarget=$1\ncd \"$target\"\nrm -f -- *.tmp\necho \"[INFO] cleanup done\"\nEOF"],
)


# ------------------------------------------------------------------ 6-5
STORES65 = ["shibuya", "shinjuku", "ikebukuro", "yokohama", "umeda", "sapporo", "hakata", "sendai"]
ITEMS65 = {"coffee": 480, "tea": 420, "cake": 650, "sandwich": 580, "cookie": 220, "juice": 380}

REPORT_SOL = r"""#!/bin/bash
set -euo pipefail
csv=$1
awk -F, 'NR > 1 { sum[$2] += $4 * $5 } END { for (s in sum) printf "%-10s %10d\n", s, sum[s] }' "$csv" | sort -k2,2nr
awk -F, 'NR > 1 { t += $4 * $5 } END { printf "%-10s %10d\n", "TOTAL", t }' "$csv"
""".rstrip("\n")


def _gen_sales(rnd):
    while True:
        stores = rnd.sample(STORES65, rnd.randint(3, 5))
        rows, tot, qty = [], {}, {}
        for _ in range(rnd.randint(25, 40)):
            s, (item, price) = rnd.choice(stores), rnd.choice(list(ITEMS65.items()))
            q = rnd.randint(1, 30)
            day = f"2025-11-{rnd.randint(1, 30):02d}"
            rows.append(f"{day},{s},{item},{q},{price}")
            tot[s] = tot.get(s, 0) + q * price
            qty[s] = qty.get(s, 0) + q
        if len(set(tot.values())) == len(tot) and len(tot) == len(stores):
            break
    text = "date,store,item,qty,price\n" + "\n".join(sorted(rows)) + "\n"
    want = sorted(tot.items(), key=lambda kv: -kv[1])
    return text, want, sum(tot.values()), qty


def _gen_servers(rnd):
    servers, envs = [], ["prod", "prod", "stg", "dev"]
    roles = ["web", "api", "db", "batch", "cache"]
    used = set()
    while len(servers) < rnd.randint(9, 13):
        name = f"{rnd.choice(roles)}-{rnd.randint(1, 30):02d}"
        if name in used:
            continue
        used.add(name)
        servers.append({"name": name, "env": rnd.choice(envs),
                        "status": "down" if rnd.random() < 0.35 else "up",
                        "ip": f"10.{rnd.randint(0, 3)}.{rnd.randint(0, 255)}.{rnd.randint(2, 254)}",
                        "cpu": rnd.randint(1, 99), "tags": rnd.sample(["linux", "docker", "nginx", "mysql", "redis"], 2)})
    # 必ず「prod の down」を2台以上、「stg の down」「prod の up」を1台以上含める
    servers[0].update(env="prod", status="down")
    servers[3].update(env="prod", status="down")
    servers[1].update(env="stg", status="down")
    servers[2].update(env="prod", status="up")
    rnd.shuffle(servers)
    return {"datacenter": "tokyo-1", "updated_at": "2025-11-18T09:00:00+09:00", "servers": servers}


def s65(ctx):
    rnd = random.Random()
    text, want, total, _ = _gen_sales(rnd)
    ctx.write("sales.csv", text)
    inv = _gen_servers(rnd)
    ctx.write("servers.json", json.dumps(inv, indent=2, ensure_ascii=False) + "\n")
    ctx.data["down_prod"] = [f"{s['name']} {s['ip']}" for s in inv["servers"]
                             if s["env"] == "prod" and s["status"] == "down"]


def c65(ctx):
    _need_script(ctx, "sales_report.sh")
    rnd = random.Random()
    text, want, total, qty = _gen_sales(rnd)
    with _Sandbox(ctx) as tmp:
        csv = os.path.join(tmp, f"check_{ctx.rand(4).lower()}.csv")
        with open(csv, "w") as f:
            f.write(text)
        rc, out, err = _run(ctx, "sales_report.sh", [csv], cwd=tmp)
    label = "`./sales_report.sh 別のCSV`"
    if rc != 0:
        ctx.fail(f"{label} が終了コード {rc} で失敗しました。{err.strip()[:150]}")
    lines = _nonempty(out)
    if not lines:
        ctx.fail(f"{label} の出力が空です。CSV のパスは `$1` で受け取りましょう（`sales.csv` 決め打ちは NG）。")
    rows = []
    for ln in lines:
        parts = ln.split()
        if len(parts) < 2:
            ctx.fail(f"出力行「{ln}」の形式が違います。`店舗名 金額` の形にしましょう。")
        try:
            rows.append((parts[0].rstrip(":："), int(parts[-1].replace(",", ""))))
        except ValueError:
            ctx.fail(f"出力行「{ln}」の金額が整数になっていません（`printf \"%d\"` などで整数表示に）。")
    if rows[-1][0].upper() != "TOTAL":
        ctx.fail("最後の行が `TOTAL 総売上` になっていません。")
    body, (_, got_total) = rows[:-1], rows[-1]
    names = [r[0] for r in body]
    if "store" in names:
        ctx.fail("ヘッダー行（`date,store,...`）まで集計されています。`NR > 1` で1行目を飛ばしましょう。")
    if sorted(names) != sorted(s for s, _ in want):
        ctx.fail(f"店舗の一覧が違います（期待 {len(want)} 店舗 / 出力 {len(names)} 行）。店舗ごとに1行ずつ出力しましょう。")
    got = dict(body)
    if got == qty:
        ctx.fail("数量（qty）の合計になっています。売上は **qty × price** の合計です（`$4 * $5`）。")
    if got != dict(want):
        s = next(s for s, v in want if got.get(s) != v)
        ctx.fail(f"店舗 `{s}` の売上が {got.get(s)} になっていますが、正しくは {dict(want)[s]} です。各行の qty × price を店舗ごとに足しましょう。")
    if [r[0] for r in body] != [s for s, _ in want]:
        ctx.fail("店舗の並びが **売上の多い順** になっていません（`sort -k2,2nr` など）。TOTAL 行は最後に。")
    if got_total != total:
        ctx.fail(f"TOTAL が {got_total} ですが、正しくは {total} です。")

    want_j = ctx.data["down_prod"]
    got_j = ctx.lines("down_prod.txt")
    if got_j is None:
        ctx.fail("`down_prod.txt` がまだありません。jq で servers.json から抽出しましょう。")
    got_j = [ln.strip() for ln in got_j if ln.strip()]
    if any('"' in ln for ln in got_j):
        ctx.fail("`down_prod.txt` に `\"` が付いています。jq の `-r`（raw 出力）オプションで文字列のクォートを外しましょう。")
    norm = [" ".join(ln.split()) for ln in got_j]
    if norm != want_j:
        if len(norm) > len(want_j):
            ctx.fail(f"`down_prod.txt` が {len(norm)} 行あります（正しくは {len(want_j)} 行）。`env` が `prod` **かつ** `status` が `down` のサーバーだけに絞りましょう。")
        ctx.fail(f"`down_prod.txt` の内容が違います。`名前 IP` の形で、servers.json に出てくる順に {len(want_j)} 行です。")


register(
    id="6-5", stage=S, title="awk と jq でデータを集計・抽出する",
    story="""
月末。店長会議用に「**店舗別の売上ランキング**」を毎月出してほしいと頼まれた。来月以降も使うので **スクリプト化** しておこう。
ついでにインフラ担当から「監視 API が吐いた `servers.json` から、**本番(prod)で停止中(down)** のサーバーを洗い出して」と。
CSV は awk、JSON は jq ── データ処理の二大ツールの出番だ。
""",
    objectives=["`sales_report.sh CSVファイル` で、CSV（`date,store,item,qty,price`）を店舗ごとに集計するスクリプトを作る（shebang + 実行権限）",
                "各行 `店舗名 売上合計`（売上 = qty × price）を **売上の多い順** に出力し、最後の行に `TOTAL 総売上` を出力する（ヘッダー行は集計しない）",
                "※ 判定では `sales.csv` とは別のランダムな CSV で実行して確かめます",
                "`servers.json` の `.servers` から `env` が `prod` かつ `status` が `down` のサーバーを `名前 IP` の形で1行ずつ `down_prod.txt` に保存する（クォートなし）"],
    hints=["awk は「列で区切って行ごとに処理し、最後に END でまとめて出力」が得意。jq は JSON を `.キー` や `.[]` でたどり、`select()` で絞り込みます。",
           "`awk -F, 'NR>1 { sum[$2] += $4*$5 } END { for (s in sum) printf \"%s %d\\n\", s, sum[s] }' \"$1\" | sort -k2,2nr`。"
           "jq は `jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"'`。",
           "sales_report.sh の中身:\n  #!/bin/bash\n  awk -F, 'NR>1{s[$2]+=$4*$5} END{for(k in s) printf \"%-10s %10d\\n\",k,s[k]}' \"$1\" | sort -k2,2nr\n"
           "  awk -F, 'NR>1{t+=$4*$5} END{printf \"%-10s %10d\\n\",\"TOTAL\",t}' \"$1\"\n"
           "jq: `jq -r '.servers[] | select(.env==\"prod\" and .status==\"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt`"],
    answer="cat > sales_report.sh <<'EOF'\n" + REPORT_SOL + "\nEOF\nchmod +x sales_report.sh\n./sales_report.sh sales.csv\n\n"
           "jq '.servers[0]' servers.json        # まず構造を確認\n"
           "jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt\ncat down_prod.txt",
    explanation="""
**awk** … 1行ずつ読んで `$1` `$2`… の列に分解する小さなプログラミング言語
・`-F,` 区切り文字の指定 ／ `NR` 現在の行番号（`NR > 1` でヘッダーを飛ばす）／ `NF` 列数
・`sum[$2] += $4 * $5` … **連想配列** に店舗名ごとの合計を貯める（グループ別集計の定番）
・`END { ... }` … 全行を読み終えた後に1回だけ実行。`for (k in sum)` で配列を回す（順番は不定なので sort で並べる）
・`printf "%-10s %10d\\n"` … `%-10s` 左寄せ10桁の文字列、`%10d` 右寄せ10桁の整数で表のように整形
・`sort -k2,2nr` … 2列目を数値(n)として降順(r)に並べる
**jq** … JSON 用の sed/awk
・`.servers[]` 配列を1要素ずつ展開 ／ `select(条件)` 条件に合うものだけ通す ／ `and` `or` `not`
・`"\\(.name) \\(.ip)"` 文字列埋め込み。`[.name, .ip] | @tsv` や `@csv` も便利
・`-r` … 文字列を `"` なしで出力（他のコマンドに渡すときは必須）
・`jq '.servers | length'`、`jq 'map(select(.cpu > 80))'`、`jq '.servers | group_by(.env) | map({env: .[0].env, n: length})'` など集計もお手の物
""",
    tip="""
`curl -s https://api.example.com/items | jq -r '.items[].id'` のように、API の JSON を jq で捌くのはクラウド運用の日常です
（`aws` / `gcloud` / `kubectl get -o json` の出力も JSON）。awk は「ログから特定列の合計・平均」を出すときの最速の道具。
`awk '{s+=$10} END {print s/NR}' access.log` でレスポンスサイズの平均が一発で出せます。
""",
    setup=s65, check=c65,
    solution="cat > sales_report.sh <<'EOF'\n" + REPORT_SOL + "\nEOF\nchmod +x sales_report.sh\n"
             "jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt",
    wrong=["cat > sales_report.sh <<'EOF'\n" + REPORT_SOL.replace("NR > 1 ", "") + "\nEOF\nchmod +x sales_report.sh\n"
           "jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt",
           "cat > sales_report.sh <<'EOF'\n" + REPORT_SOL.replace("$4 * $5", "$4") + "\nEOF\nchmod +x sales_report.sh\n"
           "jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt",
           "cat > sales_report.sh <<'EOF'\n" + REPORT_SOL.replace('"$csv"', "sales.csv") + "\nEOF\nchmod +x sales_report.sh\n"
           "jq -r '.servers[] | select(.env == \"prod\" and .status == \"down\") | \"\\(.name) \\(.ip)\"' servers.json > down_prod.txt",
           "cat > sales_report.sh <<'EOF'\n" + REPORT_SOL + "\nEOF\nchmod +x sales_report.sh\n"
           "jq '.servers[] | select(.status == \"down\") | .name' servers.json > down_prod.txt"],
)


# ------------------------------------------------------------------ 6-6
def s66(ctx):
    a, b = random.sample(range(1, 10), 2)
    old, new = f"legacy-db0{a}", f"prod-db0{b}"
    n = random.choice([128, 256, 512, 1024])
    lines = [
        "# Penguin Shop アプリケーション設定",
        "app_name = penguin-shop",
        f"db_host = {old}",
        "db_port = 5432",
        f"db_replica = {old}:5433",
        "debug_mode = on",
        "log_level = info",
        f"allowed_hosts = {old}, {old}.internal",
        "timeout = 30",
    ]
    ctx.write("app.conf", "\n".join(lines) + "\n")
    want = [ln.replace(old, new) for ln in lines if ln != "debug_mode = on"] + [f"max_clients = {n}"]
    ctx.data.update(old=old, new=new, maxc=n, vim_want=want)


def c66(ctx):
    if ctx.exists(".app.conf.swp"):
        ctx.fail("`.app.conf.swp`（vim のスワップファイル）があります。vim がまだ開いたまま（Ctrl+Z で止めた等）か、異常終了しています。"
                 "`fg` で戻って `:wq` するか、残骸なら `rm .app.conf.swp` しましょう。")
    t = ctx.read("app.conf")
    if t is None:
        ctx.fail("`app.conf` が見つかりません。`reset_mission` でやり直しましょう。")
    got = [ln.rstrip() for ln in t.splitlines()]
    while got and not got[-1]:
        got.pop()
    want = ctx.data["vim_want"]
    old, new, n = ctx.data["old"], ctx.data["new"], ctx.data["maxc"]
    if got != want:
        if old in t:
            if any(ln.count(new) == 1 and ln.count(old) == 1 for ln in got):
                ctx.fail(f"1行に2回出てくる `{old}` の2つ目が置換されていません。`:%s/{old}/{new}/g` の **g**（行内すべて）を付けましょう。")
            ctx.fail(f"まだ `{old}` が残っています。`:%s/{old}/{new}/g` で **ファイル全体** を置換しましょう（`%` が全行の意味）。")
        if any(ln.startswith("debug_mode") for ln in got):
            ctx.fail("`debug_mode = on` の行が残っています。その行にカーソルを合わせて `dd` で削除しましょう。")
        if not got or got[-1] != f"max_clients = {n}":
            if any(f"max_clients = {n}" in ln for ln in got):
                ctx.fail(f"`max_clients = {n}` が最終行にありません。`G` で最終行へ移動し、`o` で下に新しい行を開いて入力しましょう。")
            ctx.fail(f"最終行に `max_clients = {n}` を追記してください。")
        ctx.fail("`app.conf` に指示以外の変更が入っています。`reset_mission` で元に戻してやり直しましょう（`u` で取り消しもできます）。")
    hist = ctx.history()[ctx.data.get("_hist_start", 0):]
    if not any(re.search(r"(^|[\s;&|(])(n?vim?|vimdiff|view|ex)(\s|$)", ln) for ln in hist):
        ctx.fail("ファイルの内容は正しいですが、このミッションは **vim の練習** です。`vim app.conf` で編集してみましょう（`reset_mission` で元に戻せます）。")


register(
    id="6-6", stage=S, title="vim で設定ファイルを直す",
    story="""
本番サーバーに SSH したら、エディタは **vim（vi）しか入っていない**。サーバー作業では「vim で設定ファイルを直せること」は必須スキルだ。
DB サーバーが `<<old>>` から `<<new>>` に移行したので `app.conf` を書き換えたい。
「`i` で入力、`Esc` で戻る、`:wq` で保存して終了」── まずはこれだけ覚えれば戦える。
""",
    objectives=["`vim app.conf` で開いて編集する",
                "`<<old>>` をファイル内 **すべて** `<<new>>` に置換する（1行に2つある箇所もあり）",
                "`debug_mode = on` の行を削除する",
                "最終行の後に `max_clients = <<maxc>>` という行を追加して、保存して終了する（`:wq`）"],
    hints=["vim には「ノーマルモード（移動・コマンド）」と「挿入モード（文字入力）」があります。迷ったら `Esc` でノーマルモードへ。保存せず逃げるなら `:q!`。",
           "置換は `:%s/旧/新/g`（% = 全行、g = 行内すべて）。行の削除は `dd`。`G` で最終行へ、`o` で下に行を追加して挿入モード。`/文字列` で検索。",
           "`vim app.conf` → `:%s/<<old>>/<<new>>/g` Enter → `/debug_mode` Enter → `dd` → `G` → `o` → `max_clients = <<maxc>>` → `Esc` → `:wq` Enter"],
    answer="vim app.conf\n# ↓ vim の中で入力するキー\n:%s/<<old>>/<<new>>/g     (Enter)  全置換\n/debug_mode              (Enter)  検索して移動\ndd                                その行を削除\nG                                 最終行へ\no                                 下に行を追加して挿入モード\nmax_clients = <<maxc>>\nEsc                               ノーマルモードへ\n:wq                      (Enter)  保存して終了\n\ncat app.conf",
    explanation="""
**モード** が vim 最大の特徴です。
・ノーマルモード（起動直後）… `h j k l` 移動、`gg` 先頭 / `G` 末尾、`dd` 行削除、`yy` 行コピー、`p` 貼り付け、`u` 取り消し、`Ctrl+r` やり直し
・挿入モード … `i` カーソル位置 / `a` 直後 / `o` 下に新しい行 / `O` 上に新しい行 から入力。`Esc` で戻る
・コマンドラインモード（`:`）… `:w` 保存 ／ `:q` 終了 ／ `:wq` か `:x` 保存して終了 ／ `:q!` 保存せず終了 ／ `:set number` 行番号表示
・検索 `/文字列`（`n` で次、`N` で前）、置換 `:%s/旧/新/g`（`gc` にすると1件ずつ確認）、`:10,20s/...` で範囲指定
・`:g/パターン/d` … パターンに一致する行をまとめて削除
注意: vim を開いたまま SSH が切れると `.app.conf.swp` が残り、次回「スワップファイルが見つかりました」と聞かれます。
  `(R)ecover` で復元、不要なら `(D)elete` で消して OK。
""",
    tip="""
`vimtutor` コマンドで 30 分の公式チュートリアルが始まります。手が覚えるまでやると一生ものです。
`crontab -e` や `git commit`、`visudo` もデフォルトで vi/vim が開くことが多いので、
最低限「`i` → 入力 → `Esc` → `:wq`」と「困ったら `Esc` → `:q!`」だけは確実に。好みのエディタは `export EDITOR=nano` で変えられます。
""",
    setup=s66, check=c66,
    solution="vim -Es -u NONE -i NONE -c '%s/<<old>>/<<new>>/g' -c 'g/^debug_mode = on$/d' -c 'call append(\"$\", \"max_clients = <<maxc>>\")' -c 'wq' app.conf",
    wrong=["vim -Es -u NONE -i NONE -c '%s/<<old>>/<<new>>/' -c 'g/^debug_mode = on$/d' -c 'call append(\"$\", \"max_clients = <<maxc>>\")' -c 'wq' app.conf",
           "vim -Es -u NONE -i NONE -c '%s/<<old>>/<<new>>/g' -c 'call append(\"$\", \"max_clients = <<maxc>>\")' -c 'wq' app.conf",
           "sed -i 's/<<old>>/<<new>>/g; /^debug_mode = on$/d' app.conf\necho 'max_clients = <<maxc>>' >> app.conf",
           "vim -Es -u NONE -i NONE -c '%s/<<old>>/<<new>>/g' -c 'g/^debug_mode = on$/d' -c 'call append(0, \"max_clients = <<maxc>>\")' -c 'wq' app.conf"],
)


# ------------------------------------------------------------------ 6-7
CRON_INITIAL = """# Penguin Shop 定期ジョブ（既存のジョブは消さないこと）
MAILTO=""
0 0 * * 0 /usr/bin/find /tmp/penguin-cache -type f -mtime +7 -delete
"""
_YEAR = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(366)]


def s67(ctx):
    ctx.write("scripts/backup.sh", "#!/bin/bash\necho \"$(date '+%F %T') backup start\"\necho \"warn: disk 81%\" >&2\n", mode=0o644)
    ctx.write("scripts/healthcheck.sh", "#!/bin/bash\necho \"$(date '+%F %T') health OK\"\n", mode=0o644)
    ctx.mkdir("logs")
    (ctx.state / "sim_crontab").write_text(CRON_INITIAL)
    h, m, k = random.choice([1, 2, 3, 4, 5]), random.choice([0, 10, 15, 20, 30, 40, 45]), random.choice([5, 10, 15, 20])
    ctx.data.update(bk_h=h, bk_m=m, bk_time=f"{h}:{m:02d}", hc_k=k, work=str(ctx.work))


def _words(cmd):
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _abs_same(tok, target):
    p = os.path.expanduser(tok.replace("$HOME", "~").replace("${HOME}", "~"))
    return os.path.isabs(p) and os.path.realpath(p) == os.path.realpath(str(target))


def _check_job(ctx, entries, script, log, label):
    hits = [e for e in entries if not e.get("reboot") and os.path.basename(script) in e["command"]]
    if not hits:
        ctx.fail(f"{label}（`{os.path.basename(script)}`）が crontab に登録されていません。`crontab -l` で確認しましょう。")
    if len(hits) > 1:
        ctx.fail(f"{label}が {len(hits)} 行も登録されています。1行だけにしましょう（`crontab -e` で整理）。")
    e = hits[0]
    cmd = e["command"]
    words = _words(cmd)
    tok = next((w for w in words if w.endswith(os.path.basename(script))), "")
    if not tok.startswith(("/", "~", "$HOME", "${HOME}")):
        ctx.fail(f"{label}のスクリプトが相対パス（`{tok}`）です。cron はホームディレクトリから最小限の環境で実行するので **絶対パス** で書きましょう（`{ctx.p(script)}`）。")
    if not _abs_same(tok, ctx.p(script)):
        ctx.fail(f"{label}のパス `{tok}` が `{ctx.p(script)}` を指していません。")
    if re.search(r"&>", cmd):
        ctx.fail(f"{label} で `&>` / `&>>` が使われています。cron は **/bin/sh** で実行するので bash 専用の書き方は使えません。`>> ログ 2>&1` と書きましょう。")
    m = re.search(r"(?<![0-9&>])1?>>\s*(\S+)\s+2>&1", cmd)
    if not m:
        if re.search(r"2>&1\s*1?>>", cmd):
            ctx.fail(f"{label}のリダイレクトの順番が逆です。`2>&1 >> log` だと標準エラーは画面（=メール）行きのまま。**`>> log 2>&1`** の順に書きましょう。")
        if re.search(r"(?<![>&0-9])>\s*[^>&\s]", cmd) and ">>" not in cmd:
            ctx.fail(f"{label}が `>`（上書き）になっています。実行のたびにログが消えないよう `>>`（追記）にしましょう。")
        ctx.fail(f"{label}の出力をログに残していません。コマンドの後ろに `>> {ctx.p(log)} 2>&1` を付け、標準出力もエラーも追記しましょう。")
    lp = m.group(1).strip("'\"")
    if not lp.startswith(("/", "~", "$HOME", "${HOME}")):
        ctx.fail(f"{label}のログファイルが相対パス（`{lp}`）です。cron では絶対パス `{ctx.p(log)}` で書きましょう。")
    if not _abs_same(lp, ctx.p(log)):
        ctx.fail(f"{label}のログの出力先 `{lp}` が `{ctx.p(log)}` ではありません。")
    return e


def _sched_msg(label, field, how):
    return f"{label}の「{sim_cron.FIELD_JA[field]}」の指定が違います。{how}"


def c67(ctx):
    store = ctx.state / "sim_crontab"
    if not store.exists():
        ctx.fail("crontab が空になっています（`crontab -r` しましたか？）。`reset_mission` で元に戻してやり直しましょう。")
    entries, envs, errors = sim_cron.parse(store.read_text())
    if not any(not e.get("reboot") and "/tmp/penguin-cache" in e["command"] and e["minute"] == {0}
               and e["hour"] == {0} and e["dow"] == {0} for e in entries):
        ctx.fail("既存のジョブ（`0 0 * * 0 /usr/bin/find /tmp/penguin-cache ...`）が消えています！ "
                 "`echo ... | crontab -` は **丸ごと上書き** です。既存分を残すには `crontab -e` か `(crontab -l; echo ...) | crontab -`。`reset_mission` でやり直しましょう。")
    for f in ("scripts/backup.sh", "scripts/healthcheck.sh"):
        if not os.access(ctx.p(f), os.X_OK):
            ctx.fail(f"`{f}` に実行権限がありません。cron から直接起動できるよう `chmod +x` しましょう。")
    h, m, k = ctx.data["bk_h"], ctx.data["bk_m"], ctx.data["hc_k"]
    allmon = set(range(1, 13))

    e = _check_job(ctx, entries, "scripts/backup.sh", "logs/backup.log", "バックアップ")
    lb = "バックアップ"
    if e["minute"] != {m}:
        ctx.fail(_sched_msg(lb, "minute", f"毎日 {h}:{m:02d} なので1列目（分）は `{m}` です。"))
    if e["hour"] != {h}:
        ctx.fail(_sched_msg(lb, "hour", f"毎日 {h}:{m:02d} なので2列目（時）は `{h}` です。"))
    if e["month"] != allmon or not all(sim_cron.day_matches(e, d) for d in _YEAR):
        ctx.fail(f"{lb}が「毎日」になっていません。日・月・曜日（3〜5列目）は `* * *` にしましょう。")

    e = _check_job(ctx, entries, "scripts/healthcheck.sh", "logs/health.log", "ヘルスチェック")
    lb = "ヘルスチェック"
    if e["minute"] != set(range(0, 60, k)):
        ctx.fail(_sched_msg(lb, "minute", f"{k} 分ごとなら1列目は `*/{k}` です（`{k}` だけだと「毎時 {k} 分」の1回になります）。"))
    if e["hour"] != set(range(9, 19)):
        ctx.fail(_sched_msg(lb, "hour", "9時台〜18時台なので2列目は `9-18` です。"))
    if e["month"] != allmon:
        ctx.fail(_sched_msg(lb, "month", "毎月なので4列目は `*` です。"))
    if not all(sim_cron.day_matches(e, d) == (d.weekday() < 5) for d in _YEAR):
        if not e["dom_star"] and not e["dow_star"]:
            ctx.fail(f"{lb}の「日」と「曜日」が両方 `*` 以外になっています。cron では両方指定すると **OR**（どちらかに合えば実行）になるので、3列目は `*`、5列目を `1-5` にしましょう。")
        ctx.fail(_sched_msg(lb, "dow", "平日（月〜金）なので5列目は `1-5`（または `mon-fri`）です。0 と 7 が日曜日です。"))


register(
    id="6-7", stage=S, title="cron で定期実行を仕込む",
    story="""
「毎晩のバックアップ」や「数分おきの死活監視」を、人が手で実行し続けるわけにはいかない。Linux で定期実行と言えば **cron** だ。
次の2つのジョブを crontab に登録してほしい。ただし **既存のジョブを消さないこと**（前任者がやらかしたらしい…）。
※ この問題の `crontab` は学習用シミュレーターです。本物の crontab は変更されません。
""",
    objectives=["`scripts/backup.sh` と `scripts/healthcheck.sh` に実行権限を付ける",
                "`backup.sh` を **毎日 <<bk_time>>** に実行し、出力（標準出力・標準エラー）を `logs/backup.log` に **追記** する",
                "`healthcheck.sh` を **平日（月〜金）の 9時台〜18時台に <<hc_k>> 分ごと** に実行し、出力を `logs/health.log` に追記する",
                "スクリプトもログも **絶対パス** で書く（このディレクトリは `<<work>>`）。既存のジョブは残すこと"],
    hints=["crontab の1行は「分 時 日 月 曜日 コマンド」。`crontab -l` で表示、`crontab -e` でエディタ編集。cron は最小限の環境で動くので、パスは絶対パスで。",
           "`*` 毎回、`*/5` 5つおき、`9-18` 範囲、`1-5` 月〜金（0/7=日曜）。出力を残すなら `コマンド >> /絶対パス/log 2>&1`。今いる場所の絶対パスは `pwd` で確認。",
           "`chmod +x scripts/*.sh` → `crontab -e` で末尾に2行追加:\n  <<bk_m>> <<bk_h>> * * * <<work>>/scripts/backup.sh >> <<work>>/logs/backup.log 2>&1\n  */<<hc_k>> 9-18 * * 1-5 <<work>>/scripts/healthcheck.sh >> <<work>>/logs/health.log 2>&1"],
    answer="""chmod +x scripts/*.sh
crontab -l                      # 既存のジョブを確認
crontab -e                      # vim が開くので末尾に以下の2行を追記して :wq
<<bk_m>> <<bk_h>> * * * <<work>>/scripts/backup.sh >> <<work>>/logs/backup.log 2>&1
*/<<hc_k>> 9-18 * * 1-5 <<work>>/scripts/healthcheck.sh >> <<work>>/logs/health.log 2>&1

# （別解: エディタを使わずに追記する）
(crontab -l; echo '...1行目...'; echo '...2行目...') | crontab -
crontab -l""",
    explanation="""
crontab の書式: `分(0-59) 時(0-23) 日(1-31) 月(1-12) 曜日(0-7, 0と7が日曜) コマンド`
・`*` すべて ／ `*/15` 15ごと ／ `9-18` 範囲 ／ `1,15` 列挙 ／ `mon-fri` 名前も可。`@daily` `@reboot` などの略記もある
・例: `30 2 * * *` 毎日2:30 ／ `0 */6 * * *` 6時間ごと ／ `0 9 1 * *` 毎月1日9:00 ／ `*/5 9-18 * * 1-5` 平日日中5分ごと
・注意: 「日」と「曜日」を両方指定すると **OR** 条件になる（`0 0 13 * 5` は「13日の金曜」ではなく「毎月13日と毎週金曜」）
**cron の環境はログインシェルと違う** のが最大の落とし穴:
・カレントディレクトリはホーム、PATH は `/usr/bin:/bin` 程度、`.bashrc` も読まれない → **絶対パス** で書く
・コマンドは `/bin/sh` で実行される → `&>>` など bash 専用の書き方は不可
・出力は既定でメール送信（大抵は捨てられる）→ `>> /path/log 2>&1` でファイルへ。順番は「先に stdout をファイルへ、次に stderr を stdout と同じ先へ」
・コマンド中の `%` は改行扱いになるので `date +\\%F` のようにエスケープが必要
`crontab ファイル` / `echo ... | crontab -` は **全体の置き換え** なので、既存分を残すには `crontab -e` か `(crontab -l; echo 新しい行) | crontab -`。
""",
    tip="""
「cron に登録したのに動かない」の9割は **PATH・カレントディレクトリ・環境変数の違い** です。まず `>> log 2>&1` でエラーを拾うのが調査の第一歩。
時刻指定に迷ったら crontab.guru（Web サイト）で日本語のように読み下せます。
最近は systemd の **timer**（`systemctl list-timers`）で定期実行する方法も増えており、ログが journalctl で見られる・失敗時の再実行がしやすい、という利点があります。
重い処理が重複起動しないよう `flock -n /tmp/backup.lock スクリプト` で多重起動を防ぐのもプロの小技です。
""",
    setup=s67, check=c67, sim=True,
    solution="""chmod +x scripts/*.sh
W=$(pwd)
(crontab -l; echo "<<bk_m>> <<bk_h>> * * * $W/scripts/backup.sh >> $W/logs/backup.log 2>&1"
 echo "*/<<hc_k>> 9-18 * * mon-fri $W/scripts/healthcheck.sh >> $W/logs/health.log 2>&1") | crontab -
crontab -l""",
    wrong=["""chmod +x scripts/*.sh
W=$(pwd)
{ echo "<<bk_m>> <<bk_h>> * * * $W/scripts/backup.sh >> $W/logs/backup.log 2>&1"
  echo "*/<<hc_k>> 9-18 * * 1-5 $W/scripts/healthcheck.sh >> $W/logs/health.log 2>&1"; } | crontab -""",
           """chmod +x scripts/*.sh
(crontab -l; echo "<<bk_m>> <<bk_h>> * * * scripts/backup.sh >> logs/backup.log 2>&1"
 echo "*/<<hc_k>> 9-18 * * 1-5 scripts/healthcheck.sh >> logs/health.log 2>&1") | crontab -""",
           """chmod +x scripts/*.sh
W=$(pwd)
(crontab -l; echo "<<bk_m>> <<bk_h>> * * * $W/scripts/backup.sh 2>&1 >> $W/logs/backup.log"
 echo "*/<<hc_k>> 9-18 * * 1-5 $W/scripts/healthcheck.sh >> $W/logs/health.log 2>&1") | crontab -""",
           """chmod +x scripts/*.sh
W=$(pwd)
(crontab -l; echo "<<bk_m>> <<bk_h>> * * * $W/scripts/backup.sh >> $W/logs/backup.log 2>&1"
 echo "*/<<hc_k>> 9-18 1-31 * 1-5 $W/scripts/healthcheck.sh >> $W/logs/health.log 2>&1") | crontab -"""],
)


# ------------------------------------------------------------------ 6-8
BACKUP_SOL = r"""#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: $0 SRC_DIR DEST_DIR [KEEP]" >&2
  exit 1
}
log() { echo "[INFO] $*"; }

[[ $# -ge 2 && $# -le 3 ]] || usage
src=$1
dest=$2
keep=${3:-3}

if [[ ! $keep =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: KEEP は1以上の整数で指定してください: $keep" >&2
  exit 1
fi
if [[ ! -d $src ]]; then
  echo "ERROR: バックアップ元がありません: $src" >&2
  exit 2
fi

mkdir -p "$dest"
name="backup_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$dest/$name" -C "$src" .
log "created: $dest/$name"

# 新しい順に並べて KEEP 個目より後ろを削除
find "$dest" -maxdepth 1 -type f -name 'backup_*.tar.gz' -printf '%f\n' | sort -r |
  tail -n +"$((keep + 1))" | while read -r old; do
    rm -f -- "$dest/$old"
    log "removed: $old"
  done"""

_ARCH_RE = re.compile(r"^backup_(\d{8})_(\d{6})\.tar\.gz$")


def _old_archives(rnd, n):
    base = datetime.datetime(2025, rnd.randint(1, 6), rnd.randint(1, 28), 3, 0, 0)
    out, t = [], base
    for _ in range(n):
        t += datetime.timedelta(days=rnd.randint(1, 9), minutes=rnd.randint(0, 59), seconds=rnd.randint(0, 59))
        out.append((f"backup_{t:%Y%m%d_%H%M%S}.tar.gz", t.timestamp()))
    return out


def s68(ctx):
    ctx.write("data/index.html", "<h1>Penguin Shop</h1>\n")
    ctx.write("data/conf/app.conf", "db_host = prod-db01\n")
    ctx.write("data/uploads/item 001.png", "PNG...\n")
    for name, ts in _old_archives(random.Random(), 4):
        ctx.write(f"backups/{name}", "(dummy archive)\n")
        os.utime(ctx.p(f"backups/{name}"), (ts, ts))
    ctx.write("backups/README.txt", "バックアップ置き場（このファイルは消さないこと）\n")


def c68(ctx):
    _need_script(ctx, "backup.sh")
    rnd = random.Random()
    token = ctx.rand(8)
    with _Sandbox(ctx) as tmp:
        src = os.path.join(tmp, "site data")
        files = {"index.html": f"<h1>{token}</h1>\n", "conf/app.conf": "port = 8080\n",
                 "uploads/photo 01.png": "PNG\n", f"notes_{token.lower()}.txt": "memo\n"}
        for rel, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(src, rel)), exist_ok=True)
            with open(os.path.join(src, rel), "w") as f:
                f.write(body)
        decoys = ["README.txt", "backup_memo.txt", "keep_me.tar.gz"]

        def make_dest(name, n_old):
            d = os.path.join(tmp, name)
            os.makedirs(d)
            olds = _old_archives(rnd, n_old)
            for fn, ts in olds:
                with open(os.path.join(d, fn), "w") as f:
                    f.write("old\n")
                os.utime(os.path.join(d, fn), (ts, ts))
            for fn in decoys:
                with open(os.path.join(d, fn), "w") as f:
                    f.write("decoy\n")
            return d, [fn for fn, _ in olds]

        def archives(d):
            return sorted(n for n in os.listdir(d) if _ARCH_RE.match(n)) if os.path.isdir(d) else []

        # ① 引数なし
        rc, out, err = _run(ctx, "backup.sh", [], cwd=tmp, home=tmp, timeout=10)
        if rc != 1 or not re.search(r"usage|使い方", err, re.I):
            ctx.fail(f"`./backup.sh`（引数なし）は標準エラー出力に `Usage: ...` を出して終了コード 1 になるべきですが、終了コード {rc} でした。")
        # ② バックアップ元が無い
        d2, olds2 = make_dest("dest missing src", 2)
        rc, out, err = _run(ctx, "backup.sh", ["no_such_src", "dest missing src"], cwd=tmp, home=tmp, timeout=10)
        if rc != 2:
            ctx.fail(f"`./backup.sh no_such_src 保存先` は存在しないバックアップ元なので終了コード 2 になるべきですが、{rc} でした。")
        if not err.strip():
            ctx.fail("バックアップ元が無いときのエラーメッセージが標準エラー出力に出ていません（`>&2`）。")
        if archives(d2) != sorted(olds2):
            ctx.fail("バックアップ元が無いのに、保存先のバックアップが作成・削除されました。チェックは処理の **前** に行いましょう。")
        # ③ KEEP が不正
        d3, olds3 = make_dest("dest bad keep", 4)
        rc, out, err = _run(ctx, "backup.sh", ["site data", "dest bad keep", "abc"], cwd=tmp, home=tmp, timeout=10)
        if rc != 1 or archives(d3) != sorted(olds3):
            ctx.fail(f"`./backup.sh 元 先 abc`（KEEP が数字でない）は何もせず終了コード 1 になるべきですが、終了コード {rc}"
                     + ("、しかもバックアップが作成・削除されました" if archives(d3) != sorted(olds3) else "") + " でした。`[[ $keep =~ ^[1-9][0-9]*$ ]]` で検証しましょう。")
        # ④ 正常系（KEEP 指定、空白入りパス）
        keep = rnd.randint(2, 4)
        d4, olds4 = make_dest("my backups", keep + rnd.randint(2, 3))
        t0 = time.time()
        rc, out, err = _run(ctx, "backup.sh", ["site data", "my backups", keep], cwd=tmp, home=tmp, timeout=15)
        label = f"`./backup.sh \"site data\" \"my backups\" {keep}`"
        if rc != 0:
            ctx.fail(f"{label} が終了コード {rc} で失敗しました。空白入りのパスは `\"$src\"` のようにクォートしましょう。\n  エラー: {err.strip()[:200]}")
        lost = [d for d in decoys if not os.path.exists(os.path.join(d4, d))]
        if lost:
            ctx.fail(f"ローテーション対象外のファイル `{lost[0]}` まで消しています。対象は `backup_*.tar.gz` だけです。")
        now = archives(d4)
        new = [n for n in now if n not in olds4]
        if not new:
            bad = [n for n in os.listdir(d4) if n not in olds4 and n not in decoys]
            ctx.fail(f"{label} で新しいバックアップ `backup_YYYYmmdd_HHMMSS.tar.gz` が作られていません。" + (f"（作られたファイル: {bad[:2]}）" if bad else ""))
        if len(new) > 1:
            ctx.fail(f"{label} で新しいバックアップが {len(new)} 個できています。1回の実行で1個です。")
        new = new[0]
        md = _ARCH_RE.match(new)
        stamp = datetime.datetime.strptime(md.group(1) + md.group(2), "%Y%m%d%H%M%S").timestamp()
        if abs(stamp - t0) > 86400 * 1.1:
            ctx.fail(f"新しいバックアップ名 `{new}` の日時が現在時刻になっていません。`date +%Y%m%d_%H%M%S` を使いましょう。")
        try:
            with tarfile.open(os.path.join(d4, new), "r:gz") as tf:
                members = {os.path.normpath(m.name).split(os.sep)[-1]: m for m in tf.getmembers() if m.isfile()}
                missing = [r for r in files if os.path.basename(r) not in members]
                if missing:
                    ctx.fail(f"バックアップ `{new}` に `{missing[0]}` が含まれていません。バックアップ元のディレクトリ全体を tar で固めましょう。")
                body = tf.extractfile(members["index.html"]).read().decode(errors="replace")
                if token not in body:
                    ctx.fail(f"バックアップ内の index.html の中身がバックアップ元と違います。")
        except (tarfile.TarError, OSError, EOFError):
            ctx.fail(f"`{new}` が正しい tar.gz ではありません。`tar -czf 保存先/ファイル名 -C 元 .` で作りましょう。")
        want = sorted([new] + sorted(olds4)[-(keep - 1):] if keep > 1 else [new])
        if now != want:
            if len(now) == len(olds4) + 1:
                ctx.fail(f"{label} で古いバックアップが削除されていません（{len(now)} 個のまま）。新しいものを含めて {keep} 個だけ残しましょう。")
            if len(now) == keep + 1:
                ctx.fail(f"{label} で {keep + 1} 個残っています。**今回作ったものを含めて** {keep} 個です（`tail -n +$((keep + 1))`）。")
            if new not in now or set(now) != set(want):
                ctx.fail(f"{label} の後、残すべきは新しい順に {keep} 個 {want} ですが、実際は {now} でした。")
        if new not in out:
            ctx.fail(f"{label} の標準出力に、作成したファイル名（`{new}`）が表示されていません。`log \"created: ...\"` のように表示しましょう。")
        # ⑤ KEEP 省略（既定 3）
        d5, olds5 = make_dest("default keep", 5)
        rc, out, err = _run(ctx, "backup.sh", ["site data", "default keep"], cwd=tmp, home=tmp, timeout=15)
        if rc != 0 or len(archives(d5)) != 3:
            ctx.fail(f"`./backup.sh 元 先`（KEEP 省略）では既定値 3 個を残すはずですが、終了コード {rc}・残り {len(archives(d5))} 個でした。`keep=${{3:-3}}` で既定値を。")
        # ⑥ 保存先が無ければ作る
        rc, out, err = _run(ctx, "backup.sh", ["site data", "brand new/nested", "2"], cwd=tmp, home=tmp, timeout=15)
        if rc != 0 or len(archives(os.path.join(tmp, "brand new/nested"))) != 1:
            ctx.fail(f"保存先ディレクトリ（`brand new/nested`）が存在しない場合は `mkdir -p` で作ってからバックアップしましょう（終了コード {rc}）。")


register(
    id="6-8", stage=S, title="【実践】ローテーション付きバックアップスクリプト",
    story="""
いよいよ本番。Webサイトのデータを毎晩バックアップしたいが、全部残すとディスクがあふれる。
「**最新 N 世代だけ残して古いものは自動削除**（ローテーション）」するスクリプト `backup.sh` を作ってほしい。
cron から無人で動くので、**引数ミスや異常は終了コードで知らせ、絶対に余計なものを消さない** こと。
判定では、ランダムに作ったテスト用ディレクトリに対してあなたのスクリプトを実際に何度も実行して確かめます。
""",
    objectives=["使い方: `./backup.sh バックアップ元 保存先 [残す数KEEP]`（KEEP 省略時は 3）。shebang + 実行権限",
                "引数が2〜3個でない → 標準エラーに `Usage: ...`、終了コード **1** ／ KEEP が正の整数でない → 何もせず終了コード **1** ／ バックアップ元が無い → 標準エラーにメッセージ、終了コード **2**",
                "保存先が無ければ作成し、`保存先/backup_YYYYmmdd_HHMMSS.tar.gz`（現在日時）にバックアップ元の中身を tar.gz で固め、そのファイル名を標準出力に表示する",
                "保存先の `backup_*.tar.gz` を、今回の分を含めて **新しい順に KEEP 個だけ** 残して削除する（他のファイルには触れない）",
                "空白入りのパス（`\"site data\"` `\"my backups\"`）でも正しく動くこと。`data/` と `backups/` で試せます"],
    hints=["これまでの総まとめです。`set -euo pipefail` → 引数チェック（`$#`、`[[ ]]`、`exit`）→ 本処理（`tar`）→ ローテーション（一覧を新しい順に並べて余りを削除）の順に組み立てましょう。",
           "既定値は `keep=${3:-3}`、整数チェックは `[[ $keep =~ ^[1-9][0-9]*$ ]]`。日時は `date +%Y%m%d_%H%M%S`、固めるのは `tar -czf \"$dest/$name\" -C \"$src\" .`。"
           "名前に日時が入っているので、名前の降順 `sort -r` が新しい順。`tail -n +$((keep + 1))` で KEEP+1 個目以降を取り出せます。",
           "ローテーション部分の例:\n  ls -1 \"$dest\" | grep -E '^backup_[0-9]{8}_[0-9]{6}\\.tar\\.gz$' | sort -r | tail -n +$((keep + 1)) |\n    while read -r f; do rm -f -- \"$dest/$f\"; echo \"removed: $f\"; done\n"
           "全体は `answer` で確認できます。`./backup.sh data backups 2; ls backups` で動作確認を。"],
    answer="cat > backup.sh <<'EOF'\n" + BACKUP_SOL + "\nEOF\nchmod +x backup.sh\n\n./backup.sh; echo $?                 # → Usage, 1\n./backup.sh nodir backups; echo $?   # → 2\n./backup.sh data backups 2 && ls backups",
    explanation="""
このスクリプトは Stage 6 で学んだ技の集大成です。
・`set -euo pipefail` … 途中で失敗したら即停止（中途半端な状態で削除処理に進まない）
・`usage()` / `log()` 関数 … 繰り返し使う処理をまとめる。使い方エラーは stderr へ出して `exit 1`
・`${3:-3}` … 引数省略時の既定値 ／ `[[ $keep =~ ^[1-9][0-9]*$ ]]` … 正規表現で入力検証（`0` や `abc`、`-1` を弾く）
・**チェックはすべて処理の前に**。「元が無いのに古いバックアップだけ消えた」は最悪の事故です
・`tar -czf 出力 -C 元 .` … `-C` で元ディレクトリに移動してから固めるので、アーカイブ内のパスが `./index.html` のように短くなる
・ローテーション: 名前に `YYYYmmdd_HHMMSS` を入れておくと **名前順 = 時系列順** になり、`sort -r | tail -n +$((keep+1))` で「新しい方から KEEP 個を除いた残り」が取れる
  （`ls -t` で更新時刻順に並べる方法もあります）
・`find ... -printf '%f\\n'` や `while read -r` を使うと空白入りのファイル名でも安全。`for f in $(ls)` は空白で壊れます
・`rm -f -- "$dest/$old"` … 変数をクォート、`--` 付き。削除系は特に慎重に
""",
    tip="""
本番では、これを cron に `0 3 * * * /opt/scripts/backup.sh /var/www /backup 7 >> /var/log/backup.log 2>&1` のように登録し、
**終了コードが 0 以外なら通知**（`|| curl -X POST Slack の Webhook ...`）する仕組みまで作ると完璧です。
そして最も大事なのは「**バックアップは復元できて初めて意味がある**」こと。`tar -tzf` で中身を確認し、定期的に復元テストをしましょう。
さらに本格的には rsync の `--link-dest` による差分バックアップや、別サーバー・クラウドストレージへの転送（3-2-1 ルール）も検討します。
""",
    setup=s68, check=c68,
    solution="cat > backup.sh <<'EOF'\n" + BACKUP_SOL + "\nEOF\nchmod +x backup.sh",
    wrong=["cat > backup.sh <<'EOF'\n" + BACKUP_SOL.replace('tail -n +"$((keep + 1))"', 'tail -n +"$((keep + 2))"') + "\nEOF\nchmod +x backup.sh",
           "cat > backup.sh <<'EOF'\n" + BACKUP_SOL.replace("  exit 2\n", "  exit 0\n") + "\nEOF\nchmod +x backup.sh",
           "cat > backup.sh <<'EOF'\n" + BACKUP_SOL.replace("-name 'backup_*.tar.gz'", "-name '*'") + "\nEOF\nchmod +x backup.sh",
           "cat > backup.sh <<'EOF'\n" + BACKUP_SOL.replace('tar -czf "$dest/$name" -C "$src" .', 'tar -czf $dest/$name -C $src .') + "\nEOF\nchmod +x backup.sh"],
)
