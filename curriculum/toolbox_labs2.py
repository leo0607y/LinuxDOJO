"""追加のネイティブ実習(第2群)。toolbox_labs.py の add とヘルパーを使う。"""
from curriculum.toolbox_labs import add, put, read, require, run, remember, fixture  # noqa: F401

import datetime
import os
import random
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def clean_env(**extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}
    env.update(extra)
    return env


def launch(argv, cwd, env, stdin_data=None, timeout=8):
    """プロセスグループごと起動し、時間切れなら殺す。(returncode, stdout, stderr, timed_out)"""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = proc.communicate(stdin_data, timeout=timeout)
        timed = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        out, err = proc.communicate()
        timed = True
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"), timed


# ---------------------------------------------------------------- (1) script
SCRIPT_STARTER = r'''#!/bin/bash
# tool.sh [-m MIN] [-t TAG] [-v] FILE
# FILE は「パス<TAB>サイズ」の行。仕様は task を参照。以下は書きかけ。
usage() {
  # TODO: 標準エラーへ "usage: ..." を出して終了コード2
  :
}

# TODO: 引数が数字だけなら成功(0)、違えば失敗(1)を return する。local を使う。
is_num() {
  :
}

# TODO: パスの最上位ディレクトリ(スラッシュが無ければ . )を echo する。${var%%/*} を使う。
top_of() {
  :
}

min=0
tag=""
verbose=0
# TODO: getopts で -m MIN / -t TAG / -v を処理する。

# TODO: FILE を mapfile で読み、各行を IFS=$'\t' read -r で分解する。
# TODO: 連想配列で最上位ディレクトリごとに合計し、キー順は process substitution + sort -z で出す。
'''


def script_valid_args(argv):
    pass


def script_reference(content, minimum, tag, verbose):
    """独立した参照実装。(終了コード, 標準出力)。"""
    data = content.split(b"\n")
    if data and data[-1] == b"":
        data.pop()
    lines = [l.decode("utf-8") for l in data]
    items, totals, longest, bad, count = [], {}, 0, False, 0
    for line in lines:
        if line == "":
            continue
        count += 1
        path, sep, size = line.partition("\t")
        if not sep or not size.isascii() or not size.isdigit():
            bad = True
            continue
        if int(size) < minimum:
            continue
        base = path.rsplit("/", 1)[-1]
        top = path.split("/", 1)[0] if "/" in path else "."
        items.append(f"{tag or 'item'}:{base}:{size}")
        totals[top] = totals.get(top, 0) + int(size)
        longest = max(longest, len(base))
    out = items + [f"={k}\t{totals[k]}" for k in sorted(totals, key=lambda s: s.encode())]
    out.append(f"longest={longest}")
    if verbose:
        out.append(f"lines={count}")
    return (1 if bad else 0), "".join(x + "\n" for x in out)


SCRIPT_NAMES = ["a", "report final", "日本語ファイル", "naïve café", "back\\slash", "x  y", "  lead", "trail  ",
                "tab-free", "ünï", "sp ace.txt", "emoji-free_名前", "$HOME", "*", "'q'", "-dash"]
SCRIPT_DIRS = ["", "docs/", "my docs/", "日本語/", "a b/c d/", "src/", "x/y/z/", "ß/", "-opt/"]


def script_content(rng):
    rows = []
    for _ in range(rng.randint(0, 9)):
        roll = rng.random()
        path = rng.choice(SCRIPT_DIRS) + rng.choice(SCRIPT_NAMES)
        size = rng.choice(["0", "7", "008", "010", "123", "99999", "1000", "42", "09"])
        if roll < 0.10:
            rows.append("")
        elif roll < 0.18:
            rows.append(path + "\tabc")
        elif roll < 0.24:
            rows.append(path)
        elif roll < 0.30:
            rows.append(path + "\t5\textra")
        else:
            rows.append(path + "\t" + size)
    text = "\n".join(rows)
    if rows and rng.random() < 0.7:
        text += "\n"
    return text.encode("utf-8")


def script_cases(rng):
    """(argv_options, content, expected_kind)。kind は 'ok' / 'usage' / 'nofile'。"""
    cases = []
    for i in range(30):
        mode = rng.choice(["plain", "m", "mt", "bundle", "v", "tspace", "tempty", "m0", "dd"])
        content = script_content(rng)
        minimum = rng.choice([0, 5, 10, 100, 1000])
        opts, tag, verbose, m = [], "", False, 0
        if mode == "m":
            opts, m = ["-m", str(minimum)], minimum
        elif mode == "mt":
            tag = rng.choice(["x", "日本", "a b", "T"])
            opts, m = ["-m" + str(minimum), "-t", tag], minimum
        elif mode == "bundle":
            opts, verbose, m = ["-vm" + str(minimum)], True, minimum
        elif mode == "v":
            opts, verbose = ["-v"], True
        elif mode == "tspace":
            tag = "two words"
            opts = ["-t", tag, "-v"]
            verbose = True
        elif mode == "tempty":
            opts = ["-t", ""]
        elif mode == "m0":
            opts, m = ["-m", rng.choice(["08", "09", "010"])], None
            m = int(opts[1], 10)
        elif mode == "dd":
            opts = ["--"]
        cases.append(("ok", opts, content, dict(minimum=m, tag=tag, verbose=verbose)))
    for opts in (["-x"], ["-m"], ["-m", "abc"], ["-m", "-5"], ["-t"], ["-m", "5x"], ["-m", ""], ["-v", "-z"]):
        cases.append(("usage", opts, b"a\t1\n", {}))
    cases.append(("usage2", [], b"a\t1\n", {}))
    return cases


def script_check(root):
    data = fixture(root)
    tool = root / "tool.sh"
    require(tool.is_file() and os.access(tool, os.X_OK), "tool.sh は実行可能にします。")
    original = (root / "tool.orig.sh").read_bytes()
    require(tool.read_bytes() != original, "tool.sh を完成させていません。")
    run(root, "bash", "-n", "tool.sh")
    source = tool.read_text()
    require("getopts" in source, "引数は getopts で解析します(手書き解析は不可)。")
    require("mapfile" in source or "readarray" in source, "FILE の読み込みに mapfile を使います。")
    rng = random.Random(secrets.randbelow(10**9))
    with tempfile.TemporaryDirectory(prefix="dojo-script-") as scratch:
        base = Path(scratch)
        env = clean_env()
        for kind, opts, content, params in script_cases(rng):
            fname = "-weird name.tsv" if opts == ["--"] else "in put.tsv"
            (base / fname).write_bytes(content)
            if kind == "usage2":
                argv_sets = [[], ["a.tsv", "b.tsv"]]
            else:
                argv_sets = [opts + [fname]] if kind == "ok" else [opts + [fname]]
            for argv in argv_sets:
                code, out, err, timed = launch(["bash", str(tool)] + argv, base, env)
                label = "引数 " + repr(argv)
                require(not timed, label + ": 終了しません。")
                if kind == "ok":
                    ecode, eout = script_reference(content, params["minimum"] or 0, params["tag"], params["verbose"])
                    require(out == eout, f"{label}\n期待:\n{eout!r}\n実際:\n{out!r}\n入力:{content!r}")
                    require(code == ecode, f"{label}: 終了コードは {ecode}(不正な行があれば1)。実際 {code}。入力:{content!r}")
                else:
                    require(code == 2, f"{label}: 使い方の誤りは終了コード2(実際 {code})。")
                    require(out == "" and err.startswith("usage:"), label + ": 標準出力は空・標準エラーは usage: で始めます。")
        for argv, want in ((["no-such-file.tsv"], 3), ([str(base)], 3)):
            code, out, err, timed = launch(["bash", str(tool)] + argv, base, env)
            require(code == want and out == "" and err.strip(), f"読めない FILE は標準エラーに診断を出し終了コード{want}。")
        (base / "in put.tsv").write_bytes(b"")
        code, out, err, timed = launch(["bash", str(tool), "-v", "in put.tsv"], base, env)
        require(out == "longest=0\nlines=0\n" and code == 0, "空ファイルは longest=0 / lines=0 のみ。")


add("script", "bashスクリプト実践: getopts・配列・連想配列・mapfile・パラメータ展開", "bash sort", "bash coreutils",
    "tool.sh(書きかけ。原本は tool.orig.sh)を完成させます。tool.sh [-m MIN] [-t TAG] [-v] FILE\n"
    "FILE は「パス<TAB>サイズ」の行(パスに空白・日本語・バックスラッシュを含みうる。空行あり、最終行に改行が無い場合あり)。\n"
    "-m MIN は数字のみ(08 や 010 も10進として扱う。既定0)。-t TAG は既定 item(空文字を渡しても item)。-v は末尾に lines=N。\n"
    "出力(標準出力): サイズ>=MIN の各行を `TAG:ベース名:サイズ(原文のまま)`、続けて最上位ディレクトリ(スラッシュ無しは .)ごとの合計を\n"
    "キーのバイト順で `=キー<TAB>合計`、続けて `longest=最長ベース名の文字数`(該当なしは0)、-v なら `lines=空でない行数`。\n"
    "サイズが数字でない・TAB無しの行は標準エラーに警告して読み飛ばし、全体は終了コード1。\n"
    "引数エラー(未知のフラグ・値欠落・MINが数字でない・FILE が0または2個以上)は標準出力に何も出さず、標準エラーに `usage:` で始まる文を出して終了コード2。\n"
    "FILE が読めなければ終了コード3。使うべき機能: getopts / 関数の local と return / [[ ]] / ${tag:-item} ${path%%/*} ${path##*/} ${#base} /\n"
    "mapfile / IFS=$'\\t' read -r / declare -A / 連想配列キーを sort -z へ渡す process substitution。\n"
    "判定は生成した多数の入力(空白・空・日本語・欠落改行・不正行)で tool.sh を実行し、チェッカー内の別実装の出力と完全一致を見る。",
    lambda root: (put(root, "tool.sh", SCRIPT_STARTER, 0o755), put(root, "tool.orig.sh", SCRIPT_STARTER, 0o644),
                  remember(root, {}, ["tool.orig.sh"])),
    script_check,
    r'''cat > tool.sh <<'SCRIPT'
#!/bin/bash
usage() { echo "usage: tool.sh [-m MIN] [-t TAG] [-v] FILE" >&2; exit 2; }
is_num() { local v=$1; [[ $v =~ ^[0-9]+$ ]]; }
top_of() { local p=$1; if [[ $p == */* ]]; then printf '%s' "${p%%/*}"; else printf '.'; fi; }
min=0 tag="" verbose=0
while getopts ':m:t:v' opt; do
  case $opt in
    m) is_num "$OPTARG" || usage; min=$((10#$OPTARG)) ;;
    t) tag=$OPTARG ;;
    v) verbose=1 ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
(( $# == 1 )) || usage
file=$1
[[ -f $file && -r $file ]] || { echo "tool.sh: cannot read $file" >&2; exit 3; }
tag=${tag:-item}
declare -A total=()
bad=0 longest=0 count=0
mapfile -t lines < "$file"
for line in "${lines[@]}"; do
  [[ -z $line ]] && continue
  count=$((count + 1))
  IFS=$'\t' read -r path size <<< "$line"
  if [[ $line != *$'\t'* ]] || ! is_num "$size"; then
    echo "tool.sh: skip: $line" >&2; bad=1; continue
  fi
  (( 10#$size >= min )) || continue
  base=${path##*/}
  printf '%s:%s:%s\n' "$tag" "$base" "$size"
  d=$(top_of "$path")
  total[$d]=$(( ${total[$d]:-0} + 10#$size ))
  (( ${#base} > longest )) && longest=${#base}
done
if (( ${#total[@]} )); then
  while IFS= read -r -d '' d; do
    printf '=%s\t%s\n' "$d" "${total[$d]}"
  done < <(printf '%s\0' "${!total[@]}" | LC_ALL=C sort -z)
fi
echo "longest=$longest"
(( verbose )) && echo "lines=$count"
exit "$bad"
SCRIPT
chmod +x tool.sh''',
    ["printf '#!/bin/bash\\necho hi\\n' > tool.sh; chmod +x tool.sh",
     "cat > tool.sh <<'S'\n#!/bin/bash\n# ignores options and getopts mapfile\nfor f in $(cat \"$1\"); do echo $f; done\nS\nchmod +x tool.sh",
     "cat > tool.sh <<'S'\n#!/bin/bash\n# getopts mapfile\nwhile getopts 'm:t:v' o; do :; done\nshift $((OPTIND-1))\nmapfile -t L < \"$1\"\nfor l in \"${L[@]}\"; do echo \"item:${l%%$'\\t'*}:0\"; done\nS\nchmod +x tool.sh"])


# ---------------------------------------------------------------- (2) regex
RX_MSGS = ["timeout after 30s", "retry 3 of 5", "disk error on /dev/sda1", "error-free run", "terror alert",
           "cache miss key=abc123", "DEBUG flag set", "connection reset by 10.0.0.9", "slow query 250ms",
           "Timeout while reading", "error: bad token", "all good", "upstream v1.2.3 ok", "user='bob' denied",
           "restart in 5s then 12s", "ERROR text in message", "mystery30s value"]
RX_PATHS = ["/api/v1/items/123", "/static/app.js", "/static/site.css?v=3", "/img/logo.png", "/login?next=/home&id=7",
            "/search?user=alice&q=x", "/files/report.pdf", "/api/v2/jsx", "/a.js.map", "/health", "/x/y.png?z=1"]
RX_USERS = ["alice", "bob", "carol", "dave", "-"]
RX_SVC = ["api", "auth", "web", "cache-1"]


def rx_dataset(rng, n):
    rows = []
    for _ in range(n):
        msg = rng.choice(RX_MSGS)
        if rng.random() < 0.15:
            msg = "retry retry " + msg
        elif rng.random() < 0.1:
            msg = msg + " " + msg.split()[0]
        status = rng.choice([200, 200, 200, 301, 404, 500, 503, 204])
        ip = ".".join(str(rng.randint(1, 254)) for _ in range(4))
        rows.append(dict(
            ts=f"20{rng.randint(20, 26)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}T"
               f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z",
            level=rng.choice(["INFO", "INFO", "WARN", "ERROR", "DEBUG"]), svc=rng.choice(RX_SVC),
            pid=rng.randint(100, 99999), ip=ip, user=rng.choice(RX_USERS),
            method=rng.choice(["GET", "POST", "PUT", "DELETE"]), path=rng.choice(RX_PATHS),
            status=status, size=rng.randint(1000, 99999), msg=msg))
    return rows


def rx_line(r):
    return (f'{r["ts"]} {r["level"]} {r["svc"]}[{r["pid"]}] {r["ip"]} user={r["user"]} '
            f'"{r["method"]} {r["path"]} HTTP/1.1" {r["status"]} {r["size"]} msg="{r["msg"]}"')


def rx_ref(rows):
    """各タスクの正解。正規表現に頼らず行を構造として解析して求める(独立実装)。"""
    import re as _re
    exp = {}
    wb = lambda w: _re.compile(r"(?<!\w)" + _re.escape(w) + r"(?!\w)")
    lines = [rx_line(r) for r in rows]
    nl = lambda xs: "".join(x + "\n" for x in xs)
    exp["t01"] = nl(rx_line(r) for r in rows if r["level"] in ("ERROR", "WARN"))
    ips = []
    for r, line in zip(rows, lines):
        ips.append(r["ip"])
        for m in _re.finditer(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])", r["msg"]):
            ips.append(m.group(1))
    exp["t02"] = nl(ips)
    exp["t03"] = nl(l for r, l in zip(rows, lines) if wb("error").search(r["msg"]))
    exp["t04"] = nl(l for r, l in zip(rows, lines) if r["level"] != "DEBUG" and r["user"] != "-")
    exp["t05"] = nl(f'{r["method"]} {r["path"].split("?")[0]}' for r in rows)
    exp["t06"] = nl(l for r, l in zip(rows, lines)
                    if any(a == b for a, b in zip(l.split(" "), l.split(" ")[1:])))
    exp["t07"] = nl(f'{r["method"]} {r["path"]} HTTP/1.1' for r in rows)
    exp["t08"] = nl(r["msg"] for r in rows)
    exp["t09"] = nl(f'{r["svc"]} {r["pid"]}' for r in rows)
    counts = {}
    for r in rows:
        counts[str(r["status"])] = counts.get(str(r["status"]), 0) + 1
    exp["t10"] = nl(f"{k} {counts[k]}" for k in sorted(counts))
    exp["t11"] = nl(l for r, l in zip(rows, lines) if r["path"].split("?")[0].endswith((".js", ".css", ".png")))
    exp["t12"] = nl(l.replace(f' user={r["user"]} ', " user=*** ", 1) for r, l in zip(rows, lines))
    exp["t13"] = nl(f'{r["ts"][8:10]}/{r["ts"][5:7]}/{r["ts"][0:4]} {r["ts"][11:16]} {r["level"]}' for r in rows)
    durs = []
    for r, l in zip(rows, lines):
        durs.extend(m.group(0) for m in _re.finditer(r"(?<!\w)\d+s(?!\w)", l))
    exp["t14"] = nl(durs)
    exp["t15"] = str(sum(1 for r in rows if "timeout" in r["msg"].lower())) + "\n"
    return exp


RX_STARTER = '''# 各タスク N は関数 tNN。第1引数がログファイル。標準出力に結果を出す1コマンド(パイプ可)を書く。
# 使えるのは grep sed awk sort uniq cut tr head tail wc など。python/perl は使えない。
# 各行の形: 2024-03-05T14:22:07Z INFO api[1234] 203.0.113.5 user=alice "GET /x?id=4 HTTP/1.1" 200 5120 msg="timeout after 30s"
t01() { :; }   # レベルが ERROR または WARN の行を、そのまま出す(msg 内の語に惑わされない)
t02() { :; }   # 行内のIPv4アドレス(msg 内のものを含む)を、出現順に1行1つ(v1.2.3 のようなものは対象外)
t03() { :; }   # msg の中に単語 error(小文字、単語として。terror や ERROR は除く)を含む行
t04() { :; }   # レベルが DEBUG でなく、かつ user が - でない行(msg に DEBUG という語があっても行は残す)
t05() { :; }   # 各行の「メソッド パス」(クエリ ?... は除く) 例: GET /x
t06() { :; }   # 同じ単語が連続している(retry retry など)行を、そのまま出す(後方参照)
t07() { :; }   # 最初の二重引用符で囲まれた文字列(引用符は除く) 例: GET /x?id=4 HTTP/1.1  (最短一致)
t08() { :; }   # msg="..." の中身だけ(行末の引用符対)
t09() { :; }   # 「サービス名 PID」(例: api 1234)。正規表現の区切り文字 awk -F で
t10() { :; }   # ステータスごとの件数を「ステータス 件数」で、ステータス昇順(awk と sort)
t11() { :; }   # リクエストのパス(クエリ除く)が .js .css .png で終わる行をそのまま
t12() { :; }   # 行頭側の user=名前 だけを user=*** に置換した全行(クエリ内の user= は触らない)
t13() { :; }   # 「DD/MM/YYYY HH:MM レベル」へ並べ替え(sed -E の捕獲グループ)
t14() { :; }   # 行内の「数字+s」(30s、12s)を1行1つ(5ms や mystery30s は対象外。単語境界)
t15() { :; }   # msg に timeout が(大文字小文字を問わず)含まれる行の件数だけ(grep -i と注意)
'''

RX_SOLUTION = r'''cat > answers.sh <<'SCRIPT'
t01() { grep -E '^[^ ]+ (ERROR|WARN) ' "$1"; }
t02() { grep -oE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b' "$1"; }
t03() { grep -E 'msg="(.*[^[:alnum:]_])?error([^[:alnum:]_].*)?"$' "$1"; }
t04() { grep -vE -e '^[^ ]+ DEBUG ' -e ' user=- ' "$1"; }
t05() { sed -E 's/.*"([A-Z]+) ([^ ?]+)[^ ]* HTTP[^"]*".*/\1 \2/' "$1"; }
t06() { grep -E '(^| )([^ ]+) \2( |$)' "$1"; }
t07() { sed -E 's/^[^"]*"([^"]*)".*/\1/' "$1"; }
t08() { sed -E 's/.*msg="([^"]*)"$/\1/' "$1"; }
t09() { awk -F'[][ ]+' '{print $3, $4}' "$1"; }
t10() { awk -F'"' '{split($3, a, " "); c[a[1]]++} END {for (s in c) print s, c[s]}' "$1" | LC_ALL=C sort; }
t11() { grep -E '"[A-Z]+ [^ ?]*\.(js|css|png)(\?[^ ]*)? HTTP' "$1"; }
t12() { sed -E 's/^([^ ]+ [^ ]+ [^ ]+ [^ ]+ )user=[^ ]+ /\1user=*** /' "$1"; }
t13() { sed -E 's/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}:[0-9]{2}):[0-9]{2}Z ([A-Z]+) .*/\3\/\2\/\1 \4 \5/' "$1"; }
t14() { grep -oE '(^|[^[:alnum:]_])[0-9]+s([^[:alnum:]_]|$)' "$1" | grep -oE '[0-9]+s'; }
t15() { sed -nE 's/.*msg="([^"]*)"$/\1/p' "$1" | grep -ci 'timeout'; }
SCRIPT'''


def rx_setup(root):
    rng = random.Random(secrets.randbelow(10**9))
    rows = rx_dataset(rng, 60)
    put(root, "access.log", "".join(rx_line(r) + "\n" for r in rows))
    put(root, "answers.sh", RX_STARTER, 0o644)
    put(root, "answers.orig.sh", RX_STARTER, 0o644)
    remember(root, {}, ["access.log", "answers.orig.sh"])


RX_TOOLS = "grep sed awk sort uniq cut tr head tail wc cat paste tee tac rev expand fold comm join nl basename dirname xargs env true false".split()


def rx_bin(base):
    bindir = base / "bin"
    bindir.mkdir()
    for name in RX_TOOLS:
        found = shutil.which(name)
        if found:
            (bindir / name).symlink_to(found)
    return bindir


def rx_check(root):
    fixture(root)
    source = read(root, "answers.sh")
    require(source != read(root, "answers.orig.sh"), "answers.sh に回答を書いていません。")
    run(root, "bash", "-n", "answers.sh")
    visible = (root / "access.log").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="dojo-regex-") as scratch:
        base = Path(scratch)
        bindir = rx_bin(base)
        env = {"PATH": str(bindir), "LC_ALL": "C", "LANG": "C"}
        script = base / "answers.sh"
        script.write_text(source, encoding="utf-8")
        failed = []
        datasets = []
        rng = random.Random(secrets.randbelow(10**9))
        for i in range(2):
            rows = rx_dataset(rng, 45 + i * 20)
            datasets.append(("hidden%d.log" % i, rows))
        # 見える方のデータも同じ判定にかける(行を解析し直さず、再生成した同じ表で比較できないため、隠しデータ中心)。
        for name, rows in datasets:
            (base / name).write_text("".join(rx_line(r) + "\n" for r in rows), encoding="utf-8")
            expected = rx_ref(rows)
            for task in sorted(expected):
                code, out, err, timed = launch(["/bin/bash", "-c", 'source "$0"; ' + task + ' "$1"', str(script), name],
                                               base, env, timeout=10)
                if timed:
                    failed.append(f"{task}: 終了しません。")
                elif code not in (0, 1):
                    failed.append(f"{task}: コマンド失敗(終了コード{code}) {err.strip()[:120]}")
                elif out != expected[task]:
                    failed.append(f"{task}: 隠しデータの出力が違います({name})。")
        failed = sorted(set(f.split(":")[0] + ":" + f.split(":", 1)[1] for f in failed))
        require(not failed, "不合格のタスク:\n" + "\n".join(failed[:6]) + ("\n..." if len(failed) > 6 else ""))
        # 見えているデータでの出力が隠しデータ用の固定出力でないことも確認(引数のファイルを読む)。
        (base / "empty.log").write_text("")
        for task in sorted(expected):
            code, out, err, timed = launch(["/bin/bash", "-c", 'source "$0"; ' + task + ' "$1"', str(script), "empty.log"],
                                           base, env, timeout=10)
            want = "0\n" if task == "t15" else ""
            require(out == want, task + ": 空のログに対して固定の出力をしています。")


add("regex", "正規表現の梯子: grep -E/-o/-w/-v・sed -E 後方参照・awk -F 正規表現区切り", "bash grep sed awk sort", "bash grep sed gawk coreutils",
    "access.log(見えるデータ)を見て、answers.sh の t01〜t15 に1コマンドずつ書く(各関数は第1引数のログに対して標準出力へ結果)。\n"
    "題目は answers.sh のコメントにある: grep -E の選択・アンカー・文字クラス、-o、-w、-v、sed -E の捕獲グループと後方参照、\n"
    "貪欲と最短一致([^\"]*)、単語境界、awk -F の正規表現区切り、grep -i の落とし穴(クエリや行頭側の同名語に惑わされない)。\n"
    "-P は使わなくても全題が解ける(使えるなら使ってよい)。判定は別に生成した隠しデータ2つに全関数を実行し、チェッカー内の別実装の結果と完全一致を見る。\n"
    "PATH は grep sed awk sort uniq cut tr head tail wc など最小限のみ(python/perl 不可)。固定出力の埋め込みは隠しデータと空ファイルで落ちる。",
    rx_setup, rx_check, RX_SOLUTION,
    ["printf 'x\\n' > /dev/null",
     "cat > answers.sh <<'S'\nt01() { cat \"$1\"; }\nt02() { cat \"$1\"; }\nt15() { echo 3; }\nS",
     "sed -E 's/^t01\\(\\) \\{ :; \\}/t01() { grep -E \"ERROR|WARN\" \"$1\"; }/' answers.orig.sh > answers.sh"])


# ---------------------------------------------------------------- (3) dotfiles
DOT_PROFILE = '''# ~/.bash_profile (ログインシェル用)。
export PATH="$HOME/bin:$PATH"
'''
DOT_PLAIN_PROFILE = '''# ~/.profile: sh 系のログインシェル用。ただし ~/.bash_profile があると bash は読まない。
umask 0002
export XDG_CONFIG_HOME=$HOME/.config
'''
DOT_BASHRC = '''# ~/.bashrc
PATH=$HOME/.local/bin:$PATH
echo "loading bashrc"
alias ll='ls -l'
HISTSIZE=100
until [ -e "$HOME/.cache/ready" ]; do :; done
if [ -d "$HOME/bin" ] then
  PATH=$HOME/bin:$PATH
fi
'''


def dot_setup(root):
    spec = {"HIST_SIZE": secrets.choice([3000, 4000, 5000, 7000, 9000]),
            "UMASK": secrets.choice(["0027", "0077", "0037"]),
            "EDITOR_NAME": secrets.choice(["nano", "vim", "vi", "emacs"]),
            "PROMPT_TAG": "dojo-" + secrets.token_hex(2)}
    put(root, "spec.env", "".join(f"{k}={v}\n" for k, v in spec.items()))
    home = root / "home"
    home.mkdir()
    put(home, ".bash_profile", DOT_PROFILE)
    put(home, ".profile", DOT_PLAIN_PROFILE)
    put(home, ".bashrc", DOT_BASHRC)
    for name in (".bash_profile", ".profile", ".bashrc"):
        put(root, "orig/" + name, (home / name).read_text())
    remember(root, dict(spec=spec), ["orig/.bash_profile", "orig/.profile", "orig/.bashrc", "spec.env"])


def dot_run(home, args, script=None, stdin=None, extra=None, timeout=6):
    env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin", "TERM": "dumb", "LC_ALL": "C", "LANG": "C"}
    env.update(extra or {})
    argv = ["/bin/bash"] + args + ([script] if script is not None else [])
    code, out, err, timed = launch(argv, str(home), env, stdin_data=stdin, timeout=timeout)
    require(not timed, "bash " + " ".join(args) + " が終了しません(無限ループ。rc を読む時に待ち続けていませんか)。")
    return code, out, err


def dot_marks(out):
    return {l[2:].split("=", 1)[0]: l[2:].split("=", 1)[1] for l in out.splitlines() if l.startswith("@@") and "=" in l}


def dot_check(root):
    data = fixture(root)
    spec = data["spec"]
    home = root / "home"
    for name in (".bash_profile", ".profile", ".bashrc"):
        if (home / name).exists():
            run(root, "bash", "-n", str(home / name))
    require(not (home / ".cache/ready").exists(), "待ち条件のファイルを作って誤魔化さず、rc の無限ループ自体を直します。")
    require(((home / ".bashrc").read_text() != (root / "orig/.bashrc").read_text()), ".bashrc を直していません。")
    dirs0 = "/usr/local/bin:/usr/bin:/bin"
    want_head = [str(home / ".local/bin"), str(home / "bin")]

    def path_ok(text, label):
        parts = text.strip().split(":")
        require(parts[:2] == want_head, f"{label}: PATH の先頭は $HOME/.local/bin, $HOME/bin の順(実際 {parts[:3]})。")
        require(len(parts) == len(set(parts)), f"{label}: PATH に重複があります: {text.strip()}")
        tail = [p for p in parts if p in dirs0.split(":")]
        require(tail == dirs0.split(":"), f"{label}: 元のシステム PATH の順序を保ちます。")

    # 1) 非対話(BASH_ENV 経由で rc を読む)でも静かで、対話専用の設定を持ち込まない。
    code, out, err = dot_run(home, ["-c", 'echo ok; type -t ll || true; echo "[${PS1-unset}]"'],
                             extra={"BASH_ENV": str(home / ".bashrc")})
    require(out == "ok\n[unset]\n" and not err.strip(),
            "非対話シェルで rc を読んでも何も出力せず・alias も PS1 も作りません(対話ガード)。実際: " + repr(out + err))
    # 2) ログインシェル(非対話)の環境。
    code, out, err = dot_run(home, ["-l", "-c", 'echo "$PATH"'])
    require(len(out.strip().splitlines()) == 1 and not err.strip(), "bash -l の出力は PATH の1行のみ(rc から出力しない)。実際: " + repr(out + err))
    path_ok(out, "bash -l")
    code, out, err = dot_run(home, ["-l", "-c", '. ~/.bash_profile; . ~/.bash_profile; echo "$PATH"'])
    path_ok(out, "二重読み込み")
    code, out, err = dot_run(home, ["-l", "-c", 'bash -i -c \'echo "@@PATH=$PATH"\' 2>/dev/null'])
    path_ok(dot_marks(out).get("PATH", ""), "ログイン→対話の入れ子")
    code, out, err = dot_run(home, ["-l", "-c", "umask; echo @@E=$EDITOR"])
    marks = dot_marks(out)
    require(out.splitlines()[0] == spec["UMASK"], f"ログインシェルの umask は {spec['UMASK']}(実際 {out.splitlines()[0]!r})。")
    require(marks.get("E") == spec["EDITOR_NAME"], f"ログインシェルの EDITOR は {spec['EDITOR_NAME']}。")
    xdg = 'echo "@@X=$XDG_CONFIG_HOME:$XDG_DATA_HOME:$XDG_STATE_HOME:$XDG_CACHE_HOME"'
    code, out, err = dot_run(home, ["-l", "-c", xdg])
    h = str(home)
    require(dot_marks(out).get("X") == f"{h}/.config:{h}/.local/share:{h}/.local/state:{h}/.cache",
            "ログインシェルで XDG_* を既定値(~/.config ~/.local/share ~/.local/state ~/.cache)に設定して export。")
    code, out, err = dot_run(home, ["-l", "-c", xdg], extra={"XDG_STATE_HOME": "/custom/state"})
    require(dot_marks(out).get("X") == f"{h}/.config:{h}/.local/share:/custom/state:{h}/.cache",
            "既に設定済みの XDG_* は上書きしません(${VAR:-既定})。")
    # 3) 対話シェル(非ログイン)。
    probe = r'''
echo "@@LL=$(type -t ll)"; echo "@@MKCD=$(type -t mkcd)"
ll -d . >/dev/null; echo "@@LLRUN=$?"
echo "@@HS=$HISTSIZE"; echo "@@HF=$HISTFILESIZE"; echo "@@HC=$HISTCONTROL"; echo "@@HFILE=$HISTFILE"
echo "@@PS1=$PS1"; echo "@@E=$EDITOR"
shopt -q histappend && echo "@@APPEND=1"; shopt -q globstar && echo "@@GLOBSTAR=1"
echo "@@DASH=$-"
mkcd "sp ace/dir"; echo "@@PWD=$PWD"
'''
    code, out, err = dot_run(home, ["-i", "-c"], probe)
    m = dot_marks(out)
    require(m.get("LL") == "alias" and m.get("LLRUN") == "0", "ll は alias(ls -alF など)として使えること。")
    require(m.get("MKCD") == "function", "mkcd は関数(引数を使うので alias では書けない)。")
    require(m.get("PWD") == f"{h}/sp ace/dir" and (home / "sp ace/dir").is_dir(), "mkcd DIR はディレクトリを作って移動(空白入りでも)。")
    require(m.get("HS") == str(spec["HIST_SIZE"]) and m.get("HF") == str(2 * spec["HIST_SIZE"]),
            f"HISTSIZE={spec['HIST_SIZE']}、HISTFILESIZE はその2倍。")
    control = set(m.get("HC", "").split(":"))
    require("ignoreboth" in control or {"ignoredups", "ignorespace"} <= control, "HISTCONTROL は重複と先頭空白の行を除外。")
    require(m.get("HFILE") == f"{h}/.local/state/bash/history", "HISTFILE は ${XDG_STATE_HOME:-$HOME/.local/state}/bash/history。")
    require(spec["PROMPT_TAG"] in m.get("PS1", "") and "\\w" in m["PS1"] and m["PS1"].rstrip().endswith("\\$"),
            f"PS1 に [{spec['PROMPT_TAG']}] と \\w を含み \\$ で終える。実際 {m.get('PS1')!r}")
    require(m.get("E") == spec["EDITOR_NAME"], "対話シェルでも EDITOR を設定。")
    require(m.get("APPEND") == "1" and m.get("GLOBSTAR") == "1", "shopt -s histappend globstar を対話シェルで有効に。")
    require("C" in m.get("DASH", ""), "対話シェルで set -o noclobber。")
    code, out, err = dot_run(home, ["-i", "-c"], 'echo "@@HFILE=$HISTFILE"', extra={"XDG_STATE_HOME": str(root / "xstate")})
    require(dot_marks(out).get("HFILE") == str(root / "xstate/bash/history"), "XDG_STATE_HOME が設定済みならそれに従う。")
    # 4) 履歴が実際に保存される(重複・先頭空白は保存されず、追記される)。
    tag1, tag2, hid = ("m" + secrets.token_hex(4) for _ in range(3))
    hist = home / ".local/state/bash/history"
    dot_run(home, ["-i"], stdin=f"echo {tag1}\necho {tag1}\n echo {hid}\nexit\n".encode(), timeout=8)
    dot_run(home, ["-i"], stdin=f"echo {tag2}\nexit\n".encode(), timeout=8)
    text = hist.read_text() if hist.is_file() else ""
    require(text.count(f"echo {tag1}") == 1 and hid not in text, "同一コマンドの連続重複と先頭空白の行は履歴に残さない。")
    require(f"echo {tag2}" in text and f"echo {tag1}" in text, "2回目のセッションが履歴を上書きしている(histappend)。")


DOT_SOLUTION = r'''. ./spec.env
cat > home/.bash_profile <<'SCRIPT'
umask @UMASK@
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
pathadd() { case ":$PATH:" in *":$1:"*) ;; *) PATH="$1:$PATH" ;; esac; }
pathadd "$HOME/bin"
pathadd "$HOME/.local/bin"
export PATH
[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"
SCRIPT
cat > home/.bashrc <<'SCRIPT'
export EDITOR=@EDITOR@
case $- in *i*) ;; *) return ;; esac
HISTFILE="${XDG_STATE_HOME:-$HOME/.local/state}/bash/history"
mkdir -p "${HISTFILE%/*}"
HISTSIZE=@HIST@
HISTFILESIZE=$((@HIST@ * 2))
HISTCONTROL=ignoreboth
shopt -s histappend globstar checkwinsize
set -o noclobber
alias ll='ls -alF'
mkcd() { mkdir -p -- "$1" && cd -- "$1"; }
PS1='[@TAG@] \u@\h:\w\$ '
SCRIPT
sed -i -e "s/@UMASK@/$UMASK/" home/.bash_profile
sed -i -e "s/@EDITOR@/$EDITOR_NAME/" -e "s/@HIST@/$HIST_SIZE/g" -e "s/@TAG@/$PROMPT_TAG/" home/.bashrc
rm -f home/.profile'''

add("dotfiles", "シェル起動と環境: ログイン/対話/非対話・PATH・履歴・umask・XDG", "bash", "bash",
    "home/ が実験用の HOME(実際の ~ には触れない)。spec.env の値に従い home/.bash_profile と home/.bashrc を直す。\n"
    "実験: env -i HOME=$PWD/home PATH=/usr/bin:/bin bash -l -c 'echo $PATH' / bash -i -c '...' / bash -c '...' を比べる。\n"
    "要件: ログインシェルで umask=UMASK、XDG_*_HOME を既定値で(設定済みなら尊重)export、EDITOR=EDITOR_NAME、PATH 先頭を $HOME/.local/bin, $HOME/bin の順にして重複させない(何度読んでも)。\n"
    "~/.bash_profile が ~/.profile を隠すことと、ログインシェルが ~/.bashrc を自動では読まないことを理解して接続する。\n"
    "対話シェルのみ: alias ll、関数 mkcd(引数を取る)、PS1 に PROMPT_TAG と \\w、HISTSIZE=HIST_SIZE・HISTFILESIZE=2倍・HISTCONTROL=ignoreboth・HISTFILE=XDG_STATE_HOME 配下 bash/history(ディレクトリも作る)、\n"
    "shopt histappend globstar、set -o noclobber。非対話シェルが rc を読んでも(BASH_ENV)出力せず・停止せず・alias を作らない。\n"
    "壊れた rc(構文エラー・無限ループ・PATH 二重追加・echo)を直す。判定は実際に bash -l / -i / -c を HOME=home で起動し、タイムアウト付きで観測する。orig/ は原本。",
    dot_setup, dot_check,
    DOT_SOLUTION.replace("@UMASK@", "@UMASK@"),
    ["printf '' > home/.bashrc",
     "sed -i '/^until/d;s/\\[ -d \"$HOME\\/bin\" \\] then/[ -d \"$HOME\\/bin\" ]; then/' home/.bashrc",
     "printf 'umask 0000\\n[ -f ~/.bashrc ] && . ~/.bashrc\\n' > home/.bash_profile; printf 'case $- in *i*) ;; *) return;; esac\\nalias ll=\"ls\"\\n' > home/.bashrc"])


# ---------------------------------------------------------------- (4) manpages
MAN_PAGES = ["find", "grep", "sort", "date", "cut"]
MAN_DENY = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
MAN_FIND_VARIANTS = ["size", "mmin", "empty"]


def man_setup(root):
    missing = [p for p in MAN_PAGES
               if subprocess.run(["man", "-w", p], capture_output=True, timeout=15, env=clean_env()).returncode]
    require(not missing, "man ページが未導入です: " + " ".join(missing) + "(sudo apt install man-db manpages)。このラボは実物の man を読むので導入が必要です。")
    variant = secrets.choice(MAN_FIND_VARIANTS)
    k = secrets.randbelow(40000) + 6000
    mins = secrets.choice([20, 45, 90, 150])
    date_var = secrets.choice(["V", "j", "u", "U"])
    cut_var = secrets.choice(["delim", "complement"])
    delim = secrets.choice([";", "|", "#", "+"])
    strip = secrets.randbelow(3) + 1
    find_text = {
        "size": f"find: 通常ファイルだけで、サイズが {k} バイトより大きいものを選ぶ式(find . の後ろに並べる)。",
        "mmin": f"find: 通常ファイルだけで、最終更新が {mins} 分より新しい(未満)ものを選ぶ式。",
        "empty": "find: 空のファイルと空のディレクトリだけを選ぶ式。",
    }[variant]
    date_text = {
        "V": "date: 日時を ISO 8601 の週番号(01..53)で表示する書式指定(例 %X の1つ)。",
        "j": "date: 日時を年内通算日(001..366)で表示する書式指定。",
        "u": "date: 曜日を 1..7(月曜=1、日曜=7)で表示する書式指定。",
        "U": "date: 年の第何週か(日曜始まり、00..53)で表示する書式指定。",
    }[date_var]
    cut_text = {
        "delim": f"cut: 出力時の区切りを入力区切りと別の「{delim}」にするオプション(1語で。値まで含める)。",
        "complement": "cut: 指定した列を除いた残りを出すオプション(1語)。",
    }[cut_var]
    put(root, "questions.txt",
        "実物の man / --help を読んで答える(ネット不要)。値は answers.txt の Q番号= の右に書く。\n"
        f"Q1 {find_text}\n"
        "Q2 grep: 一致なしの終了コードと、ファイルが読めない等のエラー時の終了コードを「一致なし エラー」の順に空白区切りで。\n"
        "Q3 sort: 追加オプションなしの sort は安定ソートか。yes か no。(man sort の -s を読む)\n"
        f"Q4 {date_text}\n"
        f"Q5 tar: 展開時に先頭 {strip} 階層のパスを取り除くオプション(例: --xxx=値 の形で1語)。tar --help も参照。\n"
        f"Q6 {cut_text}\n")
    put(root, "answers.txt", "".join(f"Q{i}=\n" for i in range(1, 7)))
    remember(root, dict(variant=variant, k=k, mins=mins, date_var=date_var, cut_var=cut_var, delim=delim,
                        strip=strip), ["questions.txt"])


def man_answers(root):
    answers = {}
    for line in read(root, "answers.txt").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            answers[key.strip()] = value.strip()
    return answers


def man_tokens(value, label, limit=4):
    import shlex
    try:
        tokens = shlex.split(value)
    except ValueError:
        raise ValueError(label + ": 引用符が閉じていません。")
    require(tokens and len(tokens) <= limit, f"{label}: 回答が空か長すぎます。")
    for token in tokens:
        require(token not in MAN_DENY and re.fullmatch(r"[-+A-Za-z0-9._=,;|#:@%/]+", token) is not None,
                f"{label}: 使えない語があります: {token!r}")
    return tokens


def man_check(root):
    data = fixture(root)
    answers = man_answers(root)
    for i in range(1, 7):
        require(answers.get(f"Q{i}"), f"Q{i} の回答がありません。")
    env = clean_env()
    with tempfile.TemporaryDirectory(prefix="dojo-man-") as scratch:
        base = Path(scratch)
        # Q1: find の式を実際の find にかけ、集合を独立計算と照合
        tree = base / "tree"
        tree.mkdir()
        now = time.time()
        k, mins = data["k"], data["mins"]
        specs = {"big": k + 1, "exact": k, "less": k - 1, "huge": k + 5000, "tiny": 3, "zero": 0}
        for name, size in specs.items():
            (tree / name).write_bytes(b"x" * size)
        stamps = {"big": mins * 60 - 300, "exact": mins * 60 + 300, "less": 30, "huge": mins * 60 * 4, "tiny": 5,
                  "zero": mins * 60 + 600}
        for name, age in stamps.items():
            os.utime(tree / name, (now - age, now - age))
        (tree / "emptydir").mkdir()
        (tree / "fulldir").mkdir()
        (tree / "fulldir" / "f").write_text("data")
        want = {"size": {"big", "huge"}, "mmin": {n for n, a in stamps.items() if a < mins * 60} | {"fulldir/f"},
                "empty": {"zero", "emptydir"}}[data["variant"]]
        want = {"./" + n for n in want}
        tokens = man_tokens(answers["Q1"], "Q1")
        code, out, err, timed = launch(["find", ".", *tokens], tree, env)
        require(code == 0 and not timed, "Q1: find がエラーになりました: " + err.strip()[:150])
        require(set(out.splitlines()) == want, f"Q1: その式では選ばれる集合が違います。選ばれたもの: {sorted(out.splitlines())}")
        # Q2: 実際の grep の終了コード
        (base / "t.txt").write_text("alpha\n")
        miss = subprocess.run(["grep", "zzz-nomatch", "t.txt"], cwd=base, capture_output=True, env=env).returncode
        broke = subprocess.run(["grep", "alpha", "no-such-file"], cwd=base, capture_output=True, env=env).returncode
        require(answers["Q2"].split() == [str(miss), str(broke)], "Q2: grep の終了コード(一致なし / エラー)が違います。man grep の EXIT STATUS を読む。")
        # Q3: sort が既定で安定かを実際に実行して決める
        sample = "b 2\na 1\nb 1\na 0\nb 0\n"
        plain = subprocess.run(["sort", "-k1,1"], input=sample, capture_output=True, text=True, env=env).stdout
        stable = subprocess.run(["sort", "-s", "-k1,1"], input=sample, capture_output=True, text=True, env=env).stdout
        truth = "yes" if plain == stable else "no"
        require(answers["Q3"].lower() == truth,
                "Q3: sort の既定は安定ではありません(同じキーなら全体の比較で決まる)。man sort の -s を読む。" if truth == "no"
                else "Q3: 回答が実際の挙動と違います。")
        # Q4: date の書式指定を本物の date で試す
        spec = answers["Q4"].lstrip("+")
        require(re.fullmatch(r"%[A-Za-z]", spec), "Q4: %V のような書式指定を1つだけ書きます。")
        for stamp in (1700000000, 1735603200, 1709164800, 1767225600):
            t = time.gmtime(stamp)
            y0 = t.tm_yday - 1
            expected = {"V": f"{datetime.date(t.tm_year, t.tm_mon, t.tm_mday).isocalendar()[1]:02d}",
                        "j": f"{t.tm_yday:03d}", "u": str(t.tm_wday + 1),
                        "U": f"{(y0 + 7 - (t.tm_wday + 1) % 7) // 7:02d}"}[data["date_var"]]
            got = subprocess.run(["date", "-u", "-d", f"@{stamp}", "+" + spec], capture_output=True, text=True, env=env).stdout.strip()
            require(got == expected, f"Q4: その書式では {stamp} が {got!r} になります(期待 {expected!r})。")
        # Q5: tar --strip-components を実際に使って展開
        src = base / "src" / "a" / "b" / "c"
        src.mkdir(parents=True)
        (src / "file.txt").write_text("hi")
        run(base, "tar", "-C", str(base / "src"), "-cf", "t.tar", "a")
        tokens = man_tokens(answers["Q5"], "Q5", 2)
        out_dir = base / "out"
        out_dir.mkdir()
        code, out, err, timed = launch(["tar", "-xf", str(base / "t.tar"), "-C", str(out_dir), *tokens], base, env)
        require(code == 0, "Q5: tar がエラーになりました: " + err.strip()[:150])
        names = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file())
        parts = ["a", "b", "c", "file.txt"][data["strip"]:]
        require(names == ["/".join(parts)], f"Q5: 展開結果が違います(実際 {names})。")
        # Q6: cut のオプション
        tokens = man_tokens(answers["Q6"], "Q6", 1)
        if data["cut_var"] == "delim":
            args, expect = ["-d,", "-f1,3"], "a" + data["delim"] + "c\n"
        else:
            args, expect = ["-d,", "-f2"], "a,c,d\n"
        got = subprocess.run(["cut", *args, *tokens], input="a,b,c,d\n", capture_output=True, text=True, env=env)
        require(got.returncode == 0 and got.stdout == expect, f"Q6: その指定では {got.stdout!r}(期待 {expect!r})。")


MAN_SOLUTION = r'''q1=$(grep '^Q1' questions.txt)
case $q1 in
  *"より大きい"*) k=$(printf '%s' "$q1" | grep -oE '[0-9]+ バイト' | grep -oE '[0-9]+'); a1="-type f -size +${k}c" ;;
  *"分より新しい"*) m=$(printf '%s' "$q1" | grep -oE '[0-9]+ 分' | grep -oE '[0-9]+'); a1="-type f -mmin -$m" ;;
  *) a1="-empty" ;;
esac
q4=$(grep '^Q4' questions.txt)
case $q4 in *ISO*) a4='%V' ;; *年内通算*) a4='%j' ;; *月曜=1*) a4='%u' ;; *) a4='%U' ;; esac
q5=$(grep '^Q5' questions.txt | grep -oE '先頭 [0-9]+' | grep -oE '[0-9]+')
q6=$(grep '^Q6' questions.txt)
case $q6 in
  *"除いた"*) a6='--complement' ;;
  *) a6="--output-delimiter=$(printf '%s' "$q6" | sed -E 's/.*「(.)」.*/\1/')" ;;
esac
cat > answers.txt <<ANS
Q1=$a1
Q2=1 2
Q3=no
Q4=$a4
Q5=--strip-components=$q5
Q6=$a6
ANS'''

add("manpages", "オフラインで調べる: man / --help を読んで実物の挙動で裏取りする", "bash man find grep sort date tar cut", "bash man-db manpages findutils grep coreutils tar",
    "questions.txt の Q1〜Q6 を、man や --help を読んで調べ、answers.txt の `Qn=回答` に書く(ネットは使わない)。\n"
    "判定は回答を実際の find / grep / sort / date / tar / cut に与えて挙動を観測する(例: find の式で選ばれる集合、grep の終了コード、sort の安定性、date の書式、tar の展開結果、cut の出力)。\n"
    "回答は1つの式・オプションとして実行される(-exec や -delete など危険な語は拒否)。man が無い、または該当ページ(find grep sort date cut)が無い環境では開始時に導入を求める。",
    man_setup, man_check, MAN_SOLUTION,
    ["printf 'Q1=-type f\\nQ2=0 1\\nQ3=yes\\nQ4=%%V\\nQ5=--strip-components=9\\nQ6=--complement\\n' > answers.txt",
     "printf 'Q1=-delete\\nQ2=1 2\\nQ3=no\\nQ4=%%j\\nQ5=--strip-components=1\\nQ6=--complement\\n' > answers.txt"])
