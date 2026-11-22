"""実ツールの常用実習。模擬コマンドや未導入時の代替実装は使わない。

setup/check の対象は利用者が明示して作成した専用フォルダだけ。check は
成果物・元データの保持・実ツールによる検証を行い、操作履歴だけでは合格にしない。
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import re
import subprocess
import tempfile
import tarfile
import time

LABS = {}


def put(root, name, value, mode=None):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def read(root, name):
    path = root / name
    if not path.is_file():
        raise ValueError(name + " がありません。")
    return path.read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(root, *command, input=None):
    result = subprocess.run(command, cwd=root, input=input, text=True,
                            capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("実行失敗: " + " ".join(command) + "\n" + result.stderr[-500:])
    return result.stdout


def remember(root, values, originals=()):
    values["originals"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                           for name in originals}
    put(root, ".fixture.json", json.dumps(values))


def fixture(root):
    values = json.loads(read(root, ".fixture.json"))
    for name, digest in values["originals"].items():
        path = root / name
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                name + " の原本を変更していませんか。")
    return values



def check_checksum(root, archive, sidecar):
    parts = read(root, sidecar).strip().split()
    require(len(parts) == 2 and parts[1].lstrip("*") == archive,
            sidecar + " は対象アーカイブ1つのチェックサムを記録します。")
    require(parts[0] == hashlib.sha256((root / archive).read_bytes()).hexdigest(),
            archive + " のチェックサムが一致しません。")
    run(root, "sha256sum", "-c", sidecar)


def check_tar(root, archive, expected):
    with tarfile.open(root / archive, "r:gz") as tar:
        actual = {}
        for member in tar.getmembers():
            if member.isdir():
                continue
            name = member.name.removeprefix("./")
            require(member.isfile() and name not in actual, "アーカイブに重複・特殊ファイルがあります。")
            actual[name] = member
        require(set(actual) == set(expected), "アーカイブ内のファイルが要件と違います。")
        for name, source in expected.items():
            require(tar.extractfile(actual[name]).read() == (root / source).read_bytes(),
                    "アーカイブの本文が原本と一致しません。")
            require(stat.S_IMODE(actual[name].mode) == stat.S_IMODE((root / source).stat().st_mode),
                    "アーカイブの権限が原本と一致しません。")


def add(id, title, tools, packages, task, setup, check, solution, wrong):
    if id in LABS:
        raise ValueError("実習IDが重複しています: " + id)
    LABS[id] = dict(title=title, tools=tools.split(), packages=packages.split(),
                    task=task, setup=setup, check=check,
                    solution="set -euo pipefail\n" + solution.strip() + "\n", wrong=wrong)


def shell_setup(root):
    rows = [("api", 500, secrets.randbelow(90) + 10), ("worker", 200, 8),
            ("api", 503, secrets.randbelow(90) + 10), ("web", 200, 9),
            ("worker", 500, secrets.randbelow(90) + 10)]
    put(root, "requests.log", "service status latency\n" + "".join(f"{a} {b} {c}\n" for a,b,c in rows))
    remember(root, {"expected": "\n".join(sorted({a for a,b,c in rows if b >= 500})) + "\n"}, ["requests.log"])


def shell_check(root):
    data = fixture(root)
    require(read(root, "errors.txt") == data["expected"], "5xx のサービス名だけを重複なし・昇順で保存します。")
    require(read(root, "pipeline-status.txt").strip() == "1", "pipefail の失敗終了を確認してください。")
    require(read(root, "stderr.txt").strip() == "diagnostic", "標準エラーと標準出力を別ファイルへ保存します。")


add("shell", "パイプ・終了コード・標準エラーを扱う", "bash awk sort", "bash coreutils gawk",
    "requests.log の5xxのサービス名を errors.txt に重複なし昇順で保存。\n"
    "bash の pipefail を使い false | cat の終了コードを pipeline-status.txt に保存。\n"
    "printf diagnostic >&2 の標準エラーだけを stderr.txt に保存。成功と失敗を区別できることが目標。",
    shell_setup, shell_check,
    '''awk 'NR>1 && $2>=500 {print $1}' requests.log | sort -u > errors.txt
set +e
set -o pipefail
false | cat
printf '%s\\n' "$?" > pipeline-status.txt
set -e
{ printf 'diagnostic\\n' >&2; } 2>stderr.txt''',
    ["awk 'NR>1 {print $1}' requests.log | sort -u > errors.txt; echo 0 > pipeline-status.txt; echo diagnostic > stderr.txt"])


def find_setup(root):
    names = ["space name.tmp", "line\nbreak.tmp", "--dash.tmp"]
    for name in names:
        put(root, "input/" + name, secrets.token_hex(6))
    put(root, "input/keep.txt", secrets.token_hex(8))
    remember(root, {"names": names, "moved_hashes": {name: hashlib.sha256((root / "input" / name).read_bytes()).hexdigest() for name in names}}, ["input/keep.txt"])


def find_check(root):
    data = fixture(root)
    require(not list((root / "input").glob("*.tmp")), "改行や空白入りの .tmp もすべて移動します。")
    require(sorted(p.name for p in (root / "quarantine").iterdir()) == sorted(data["names"]), "対象だけ quarantine へ移します。")
    for name, digest in data["moved_hashes"].items():
        require(hashlib.sha256((root / "quarantine" / name).read_bytes()).hexdigest() == digest, "移動したファイルの本文が保持されていません。")
    require(read(root, "count.txt").strip() == "3", "移動件数が違います。")


add("find", "空白・改行入りの名前を安全に整理する", "bash find xargs mv", "bash findutils coreutils",
    "input 直下の .tmp だけ quarantine へ移動し、keep.txt は残す。移動件数を count.txt に保存。\n"
    "ファイル名には空白・改行・先頭ハイフンがあります。find -print0 / xargs -0 と -- を使います。",
    find_setup, find_check,
    '''mkdir -p quarantine
find input -maxdepth 1 -type f -name '*.tmp' -print0 | xargs -0 -r mv -t quarantine --
find quarantine -type f -printf x | wc -c > count.txt''',
    ["mkdir -p quarantine; find input -name '*.tmp' | xargs -r mv -t quarantine --; echo 3 > count.txt"])


def archive_setup(root):
    put(root, "source/config.ini", "instance=" + secrets.token_hex(9) + "\n", 0o640)
    put(root, "source/data/notes.txt", secrets.token_hex(20))
    put(root, "source/cache/temporary", "exclude me")
    remember(root, {}, ["source/config.ini", "source/data/notes.txt", "source/cache/temporary"])


def archive_check(root):
    fixture(root)
    check_checksum(root, "backup.tar.gz", "backup.sha256")
    listing = run(root, "tar", "-tzf", "backup.tar.gz")
    require("source/config.ini" in listing and "source/cache" not in listing, "圧縮バックアップに設定を含め、cacheを除外します。")
    check_tar(root, "backup.tar.gz", {"source/config.ini": "source/config.ini", "source/data/notes.txt": "source/data/notes.txt"})
    for name in ("config.ini", "data/notes.txt"):
        require((root / "source" / name).read_bytes() == (root / "restore/source" / name).read_bytes(), "復元内容が一致しません。")
    require(stat.S_IMODE((root / "restore/source/config.ini").stat().st_mode) == 0o640, "復元した権限が640ではありません。")


add("archive", "バックアップを作り、検証して復元する", "bash tar sha256sum", "bash tar coreutils",
    "source を backup.tar.gz に圧縮。cache は除外。backup.sha256 を作り検証後、restore へ展開。\n"
    "原本と復元した設定・データが一致し、config.ini の640権限が維持されることを確認。",
    archive_setup, archive_check,
    '''tar --exclude=source/cache -czf backup.tar.gz source
sha256sum backup.tar.gz > backup.sha256
sha256sum -c backup.sha256
mkdir -p restore
tar -xzf backup.tar.gz -C restore''',
    ["tar -czf backup.tar.gz source; sha256sum backup.tar.gz > backup.sha256; mkdir -p restore; tar -xzf backup.tar.gz -C restore"])


def rsync_setup(root):
    put(root, "source/settings.ini", "token=" + secrets.token_hex(10) + "\n", 0o640)
    put(root, "source/data/my notes.txt", secrets.token_hex(12))
    put(root, "source/cache/transient", "do not copy")
    put(root, "mirror/stale.txt", "remove")
    remember(root, {}, ["source/settings.ini", "source/data/my notes.txt", "source/cache/transient"])


def rsync_check(root):
    fixture(root)
    require("stale.txt" in read(root, "dry-run.txt"), "削除を伴う同期の前に --dry-run --itemize-changes の結果を保存します。")
    require(not (root / "mirror/stale.txt").exists(), "専用mirror内の古いファイルが残っています。")
    require(not (root / "mirror/cache").exists(), "cache がコピーされています。")
    for name in ("settings.ini", "data/my notes.txt"):
        require((root / "source" / name).read_bytes() == (root / "mirror" / name).read_bytes(), "同期内容が一致しません。")
    require(stat.S_IMODE((root / "mirror/settings.ini").stat().st_mode) == 0o640, "設定の権限を保持します。")


add("rsync", "差分同期を予行してから適用する", "bash rsync", "bash rsync",
    "source/ の中身を mirror/ に同期。cache/ を除外、mirror の stale.txt を削除、権限維持。\n"
    "最初に rsync -ani --delete の予行結果を dry-run.txt へ。--delete の対象はこの専用mirrorだけ。",
    rsync_setup, rsync_check,
    '''rsync -ani --delete --exclude=cache/ source/ mirror/ > dry-run.txt
rsync -ai --delete --exclude=cache/ source/ mirror/''',
    ["rsync -ani --delete source/ mirror/ > dry-run.txt; rsync -a source/ mirror/"])


def git_setup(root):
    repo = root / "repo"
    repo.mkdir()
    run(repo, "git", "init", "-q", "-b", "main")
    run(repo, "git", "config", "user.name", "DOJO learner")
    run(repo, "git", "config", "user.email", "learner@example.invalid")
    text = "instance=" + secrets.token_hex(8) + "\nmode=draft\n"
    put(repo, "config.ini", text)
    run(repo, "git", "add", "config.ini")
    run(repo, "git", "commit", "-qm", "initial")
    remember(root, {"expected": text.replace("draft", "ready")})


def git_check(root):
    data = fixture(root)
    repo = root / "repo"
    require(read(repo, "config.ini") == data["expected"], "元のinstanceを保ち mode=ready にします。")
    require(run(repo, "git", "status", "--porcelain").strip() == "", "未コミットの変更・削除が残っています。")
    parents = run(repo, "git", "rev-list", "--parents", "-n", "1", "HEAD").split()
    require(len(parents) == 3, "mainへ --no-ff でマージし、履歴に分岐を残します。")
    require(run(repo, "git", "branch", "--show-current").strip() == "main", "mainへ戻ります。")
    require(run(repo, "git", "show", "HEAD:config.ini") == data["expected"], "コミット内容が違います。")


add("git", "Gitで変更を分離し、統合して誤削除から戻す", "bash git sed", "bash git sed",
    "repo の feature ブランチで config.ini の mode=draft を mode=ready に変更しコミット。\n"
    "main に --no-ff でマージ。config.ini を誤って消した場面を再現し git restore で復元。\n"
    "最終状態はmain・作業ツリーがクリーン・マージコミットあり。ユーザー設定はrepo内だけ。",
    git_setup, git_check,
    '''cd repo
git switch -c feature
sed -i 's/mode=draft/mode=ready/' config.ini
git add config.ini
git commit -m 'prepare config'
git switch main
git merge --no-ff feature -m 'merge feature'
rm -- config.ini
git restore config.ini''',
    ["cd repo; sed -i 's/mode=draft/mode=ready/' config.ini; git add config.ini; git commit -m direct"])


def vim_setup(root):
    token = secrets.token_hex(8)
    put(root, "service.conf", f"# {token}\nport=8080\nmode=debug\nmode=debug\n")
    remember(root, {"expected": f"# {token}\nport=9090\nmode=production\nmode=production\n"})


def vim_check(root):
    data = fixture(root)
    require(read(root, "service.conf") == data["expected"], "コメントを保ってポートとすべてのmodeを直します。")
    require(read(root, "service.conf.before").replace("8080", "9090").replace("debug", "production") == data["expected"], "編集前バックアップを残します。")


add("vim", "Vimで設定を検索・置換して保存する", "bash vim cp", "bash vim coreutils",
    "service.conf を service.conf.before にバックアップ。portを9090、全行のdebugをproductionへ。\n"
    "対話なら vim service.conf → /port → :%s/8080/9090/ → :%s/debug/production/g → :wq。\n"
    "iで入力、Escで通常モード、uで取消、:q!で破棄。模範解答は同じVimのExモードを使用。",
    vim_setup, vim_check,
    '''cp -- service.conf service.conf.before
vim -Nu NONE -n -es service.conf <<'VIM'
%s/8080/9090/
%s/debug/production/g
wq
VIM''',
    ["cp service.conf service.conf.before; sed -i 's/8080/9090/' service.conf"])


def jq_setup(root):
    rows = [{"id": secrets.token_hex(3), "state": state, "total": 10 + secrets.randbelow(90)}
            for state in ("paid", "pending", "paid", "refunded", "paid")]
    put(root, "orders.json", json.dumps({"orders": rows}))
    remember(root, {"expected": sorted([r["id"] for r in rows if r["state"] == "paid"])}, ["orders.json"])


def jq_check(root):
    data = fixture(root)
    result = run(root, "jq", "-e", "-f", "filter.jq", "orders.json")
    require(json.loads(result) == data["expected"], "jqフィルタを実行するとpaidのID配列が昇順になるようにします。")
    require(json.loads(read(root, "paid.json")) == data["expected"], "paid.json の出力も確認します。")


add("jq", "jqのフィルタを保存してJSONを加工する", "bash jq", "bash jq",
    "orders.json のpaidのidだけを昇順配列へ。再利用できるフィルタを filter.jq、結果を paid.json へ保存。\n"
    ".orders、map、select、sort を組み合わせます。jq -e の終了コードで不正な入力も調べます。",
    jq_setup, jq_check,
    '''printf '%s\\n' '.orders | map(select(.state == "paid") | .id) | sort' > filter.jq
jq -e -f filter.jq orders.json > paid.json''',
    ["echo '.orders | map(.id) | sort' > filter.jq; jq -f filter.jq orders.json > paid.json"])


def rg_setup(root):
    token = secrets.token_hex(5)
    put(root, "project/src/main.txt", f"TODO: {token}\n")
    put(root, "project/src/done.txt", "complete\n")
    put(root, "project/.hidden.txt", f"TODO: {token}\n")
    put(root, "project/vendor/ignored.txt", f"TODO: {token}\n")
    put(root, "project/.gitignore", "vendor/\n")
    # A real repository makes ignore behavior independent of parent directory.
    run(root / "project", "git", "init", "-q")
    remember(root, {}, ["project/src/main.txt", "project/src/done.txt", "project/.hidden.txt", "project/vendor/ignored.txt", "project/.gitignore"])


def rg_check(root):
    fixture(root)
    require(sorted(read(root, "todo-files.txt").splitlines()) == ["project/.hidden.txt", "project/src/main.txt"], "隠しファイルを含め、vendorと.gitを除いて検索します。")


add("rg", "ripgrepの無視規則と隠しファイルを理解する", "bash rg git sort", "bash ripgrep git coreutils",
    "project 内のTODOを含むファイル名を todo-files.txt に昇順保存。隠しファイルも対象、\n"
    "vendor は .gitignore どおり除外、.git も除外。rg --hidden -l とglobを使います。",
    rg_setup, rg_check,
    '''rg --hidden -l -g '!**/.git/**' 'TODO:' project | sort > todo-files.txt''',
    ["rg -l 'TODO:' project | sort > todo-files.txt"])


def curl_setup(root):
    token = secrets.token_hex(12)
    put(root, "payload.txt", token + "\n")
    put(root, "server.py", '''from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path == '/health':
   body = Path('payload.txt').read_bytes(); self.send_response(200)
  else:
   body = b'not found\\n'; self.send_response(404)
  self.end_headers(); self.wfile.write(body)
 def log_message(self, *args): pass
server = HTTPServer(('127.0.0.1', 0), Handler)
Path('port.txt').write_text(str(server.server_port))
server.serve_forever()
''')
    remember(root, {"token": token}, ["payload.txt", "server.py"])


def curl_check(root):
    data = fixture(root)
    require(read(root, "health.txt").strip() == data["token"], "正常URLの本文を保存します。")
    require(read(root, "http-status.txt").strip() == "404", "未存在URLのHTTPステータスを確認します。")
    require(read(root, "curl-exit.txt").strip() == "22", "--fail の404はcurl終了コード22です。HTTPコードと区別します。")


add("curl", "HTTPの本文・ステータス・通信失敗を分ける", "bash curl python3", "bash curl python3",
    "提供server.pyをこのフォルダで起動。port.txt に動的ポートが入ります。接続先は127.0.0.1だけ。\n"
    "/healthの本文をhealth.txt、/missingのHTTPコードをhttp-status.txt、\n"
    "--failで/missingを取得した終了コードをcurl-exit.txtへ。終了時に自分のサーバーだけ停止。",
    curl_setup, curl_check,
    '''python3 server.py &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT
for i in {1..100}; do [ ! -s port.txt ] || break; sleep 0.05; done
url="http://127.0.0.1:$(cat port.txt)"
curl --noproxy '*' --silent --show-error --fail --max-time 3 "$url/health" > health.txt
curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}\\n' --max-time 3 "$url/missing" > http-status.txt
set +e
curl --noproxy '*' --silent --fail --max-time 3 "$url/missing" >/dev/null
printf '%s\\n' "$?" > curl-exit.txt
set -e''',
    ["cp payload.txt health.txt; echo 404 > http-status.txt; echo 0 > curl-exit.txt"])


def ssh_setup(root):
    remember(root, {"port": 2200 + secrets.randbelow(100)})
    put(root, "connection.json", json.dumps({"host": "127.0.0.1", "user": "learner", "port": json.loads(read(root, ".fixture.json"))["port"]}))


def ssh_check(root):
    data = fixture(root)
    key = root / "keys/id_ed25519"
    require(key.is_file() and stat.S_IMODE(key.stat().st_mode) == 0o600, "専用秘密鍵は600にします。")
    pub = run(root, "ssh-keygen", "-y", "-P", "", "-f", str(key))
    require(read(root, "keys/id_ed25519.pub").split()[:2] == pub.split()[:2], "秘密鍵と公開鍵が一致しません。")
    fields = dict(line.split(" ", 1) for line in run(root, "ssh", "-G", "-F", "ssh_config", "dojo").splitlines() if " " in line)
    require(fields.get("hostname") == "127.0.0.1" and fields.get("user") == "learner" and fields.get("port") == str(data["port"]), "ssh -G の実効接続先・ユーザー・ポートを確認します。")
    require(fields.get("identitiesonly") == "yes" and fields.get("stricthostkeychecking") in ("true", "yes"), "鍵とホスト鍵検証の設定を確認します。")
    require(any("keys/id_ed25519" in value for key, value in fields.items() if key == "identityfile"), "実習専用鍵を指定します。")
    require(read(root, "fingerprint.txt").strip().startswith("256 SHA256:"), "公開鍵の指紋を記録します。")


add("ssh", "SSH鍵と接続設定を用意して実効値を確認する", "bash ssh ssh-keygen python3", "bash openssh-client python3",
    "connection.jsonに従い、keys/id_ed25519（訓練用・空パスフレーズ）とssh_configのHost dojoを作る。\n"
    "IdentityFileはこの実習の鍵、IdentitiesOnly yes、StrictHostKeyChecking yes。指紋をfingerprint.txtへ。\n"
    "ssh -G -F ssh_config dojoで実効値を確認。接続はしません。実サーバーへの接続・ホスト鍵照合はガイドの手動実習で行います。",
    ssh_setup, ssh_check,
    '''mkdir -p keys
ssh-keygen -q -t ed25519 -N '' -f keys/id_ed25519
chmod 600 keys/id_ed25519
port=$(python3 -c 'import json; print(json.load(open("connection.json"))["port"])')
cat > ssh_config <<CONF
Host dojo
    HostName 127.0.0.1
    User learner
    Port $port
    IdentityFile $PWD/keys/id_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking yes
CONF
ssh-keygen -lf keys/id_ed25519.pub > fingerprint.txt
ssh -G -F ssh_config dojo > effective.txt''',
    ["mkdir -p keys; ssh-keygen -q -t ed25519 -N '' -f keys/id_ed25519; echo 'Host dojo' > ssh_config; ssh-keygen -lf keys/id_ed25519.pub > fingerprint.txt"])


def tmux_setup(root):
    token = secrets.token_hex(8)
    put(root, "token.txt", token)
    remember(root, {"token": token, "socket": "dojo-" + token})


def tmux_check(root):
    data = fixture(root)
    rows = read(root, "panes.txt").splitlines()
    require(len(rows) == 2 and len(set(rows)) == 2 and all(row.startswith("%") for row in rows), "実tmuxの2ペインを記録します。")
    require(data["token"] in read(root, "capture.txt"), "ペイン内で出したtokenをcapture-paneで保存します。")
    result = subprocess.run(["tmux", "-L", data["socket"], "has-session"], cwd=root, capture_output=True, timeout=5)
    require(result.returncode != 0, "この課題専用tmuxサーバーを終了してください。")


add("tmux", "tmuxで分割・出力保存・専用セッションの終了", "bash tmux", "bash tmux",
    "token.txtの値を使い専用ソケット dojo-<token> でtmuxを起動。workセッションを2ペインへ。\n"
    "一方でtokenを表示、capture-paneの結果をcapture.txt、list-panesの#{pane_id}をpanes.txtへ。\n"
    "最後に専用サーバーだけ終了。対話操作はCtrl+b %で左右分割、Ctrl+b dでdetach、attachで再接続。",
    tmux_setup, tmux_check,
    '''token=$(cat token.txt)
socket="dojo-$token"
trap 'tmux -L "$socket" kill-server 2>/dev/null || true' EXIT
tmux -L "$socket" -f /dev/null new-session -d -s work 'sleep 30'
tmux -L "$socket" split-window -h -t work 'sleep 30'
tmux -L "$socket" list-panes -t work -F '#{pane_id}' > panes.txt
tmux -L "$socket" respawn-pane -k -t work:0.0 "printf '%s\\n' '$token'; sleep 30"
for i in {1..100}; do
  tmux -L "$socket" capture-pane -p -t work:0.0 > capture.txt
  grep -q "$token" capture.txt && break
  sleep 0.05
done
tmux -L "$socket" kill-server
trap - EXIT''',
    ["echo '%0' > panes.txt; cat token.txt > capture.txt"])


def sqlite_setup(root):
    values = [secrets.randbelow(90) + 10 for _ in range(3)]
    put(root, "amounts.txt", "\n".join(str(x) for x in values) + "\n")
    remember(root, {"values": values}, ["amounts.txt"])


def sqlite_check(root):
    data = fixture(root)
    for name in ("app.db", "backup.db", "restored.db"):
        require((root / name).is_file(), name + " がありません。")
        with sqlite3.connect("file:" + str(root / name) + "?mode=ro", uri=True) as db:
            require(db.execute("pragma integrity_check").fetchone() == ("ok",), "DBの整合性が不正です。")
            values = [row[0] for row in db.execute("select amount from payments order by id")]
            require(values == data["values"], name + " のデータが違います。rollback後の値を確認。")
    require(read(root, "total.txt").strip() == str(sum(data["values"])), "SQLの合計値が違います。")


add("sqlite", "SQLiteでトランザクション・バックアップ・復元", "bash sqlite3", "bash sqlite3",
    "amounts.txtの3整数をid順でpayments(id INTEGER PRIMARY KEY, amount INTEGER)へ登録。\n"
    "BEGIN後のDELETEをROLLBACKしデータを保つ。合計をtotal.txtへ、.backupでbackup.dbを作成、\n"
    "別DB restored.dbへ.restoreしてPRAGMA integrity_checkを確認。DB本体の無条件コピーと区別。",
    sqlite_setup, sqlite_check,
    '''{ echo 'CREATE TABLE payments(id INTEGER PRIMARY KEY, amount INTEGER);';
  echo 'BEGIN;';
  while IFS= read -r amount; do printf 'INSERT INTO payments(amount) VALUES(%s);\\n' "$amount"; done < amounts.txt
  echo 'COMMIT; BEGIN; DELETE FROM payments; ROLLBACK;';
} | sqlite3 app.db
sqlite3 app.db 'SELECT SUM(amount) FROM payments;' > total.txt
sqlite3 app.db '.backup backup.db'
sqlite3 restored.db '.restore backup.db'
sqlite3 restored.db 'PRAGMA integrity_check;' ''',
    ["sqlite3 app.db 'CREATE TABLE payments(id INTEGER PRIMARY KEY, amount INTEGER);'; cp app.db backup.db; cp app.db restored.db; echo 0 > total.txt"])


def python_setup(root):
    token = secrets.token_hex(10)
    put(root, "app.py", "import sys\nfrom pathlib import Path\nprint(Path('token.txt').read_text().strip())\nprint(sys.prefix)\nprint(sys.base_prefix)\n")
    put(root, "token.txt", token)
    remember(root, {"token": token}, ["app.py", "token.txt"])


def python_check(root):
    data = fixture(root)
    require((root / ".venv/pyvenv.cfg").is_file(), "python3 -m venv で専用仮想環境を作成します。")
    lines = read(root, "execution.txt").splitlines()
    require(len(lines) == 3 and lines[0] == data["token"], "app.pyの出力を保存します。")
    require(Path(lines[1]).resolve() == (root / ".venv").resolve() and lines[1] != lines[2], "OSのPythonと仮想環境のPythonを区別します。")
    require(run(root, str(root / ".venv/bin/python"), "app.py") == read(root, "execution.txt"), "仮想環境で実際に再実行できることを確認します。")


add("python", "Python仮想環境を作り実行元を確認する", "bash python3", "bash python3 python3-venv",
    "python3 -m venv --without-pip .venv で環境を作り、そのPythonでapp.pyを実行してexecution.txtへ。\n"
    "sys.prefixとsys.base_prefixの差を確認します。このオフライン課題ではpip導入は扱いません。\n"
    "実際の依存導入は通常のvenvを作り .venv/bin/python -m pip install -r requirements.txt。sudo pipは使いません。",
    python_setup, python_check,
    '''python3 -m venv --without-pip .venv
.venv/bin/python app.py > execution.txt''',
    ["python3 app.py > execution.txt"])


def build_setup(root):
    number = 100 + secrets.randbelow(900)
    put(root, "value.h", f"#define VALUE {number}\n")
    put(root, "main.c", '#include <stdio.h>\n#include "value.h"\nint main(void) { printf("%d\\n", VALUE); return 0; }\n')
    remember(root, {"number": number}, ["main.c", "value.h"])


def build_check(root):
    data = fixture(root)
    require(read(root, "output.txt").strip() == str(data["number"]), "ビルドした実行ファイルの出力が違います。")
    require((root / "hello").is_file(), "hello実行ファイルがありません。")
    require((root / "hello").read_bytes().startswith(b"\x7fELF"), "シェルで期待値を表示するだけではなくCをコンパイルします。")
    require(run(root, "make", "-s", "check").strip() == str(data["number"]), "make checkで実行できるようにします。")
    run(root, "make", "-s", "clean")
    require(not (root / "hello").exists(), "make cleanで生成物だけを削除します。")
    run(root, "make", "-s")
    require(run(root, "./hello").strip() == str(data["number"]), "clean後に再ビルドできません。")


add("build", "gccとmakeでビルド・実行・再構築する", "bash gcc make", "bash gcc make libc6-dev",
    "main.cとvalue.hを使いhelloを作るMakefileを書く。既定ターゲットはhello、checkはhello実行、\n"
    "cleanはhelloのみ削除。依存にはmain.cとvalue.hを指定。gcc -Wall -Wextra -Werrorを使用。\n"
    "make checkの出力をoutput.txtへ保存。check判定でもclean→再ビルドを実行します。",
    build_setup, build_check,
    '''printf 'hello: main.c value.h\\n\\tgcc -Wall -Wextra -Werror -o hello main.c\\n.PHONY: check clean\\ncheck: hello\\n\\t./hello\\nclean:\\n\\trm -f -- hello\\n' > Makefile
make
make -s check > output.txt''',
    ["printf 'all:\n\ttrue\ncheck:\n\techo 1\nclean:\n\ttrue\n' > Makefile; echo 1 > output.txt"])


def fzf_setup(root):
    tag = secrets.token_hex(5)
    put(root, "files.txt", f"docs/guide-{tag}.md\nsrc/main.py\ndocs/setup-{tag}.md\ntest/main.py\n")
    remember(root, {"tag": tag}, ["files.txt"])


def fzf_check(root):
    data = fixture(root)
    require(sorted(read(root, "selected.txt").splitlines()) == [f"docs/guide-{data['tag']}.md", f"docs/setup-{data['tag']}.md"], "fzfでdocsの2ファイルだけ選びます。")


add("fzf", "fzfで候補を絞り、スクリプトにも使う", "bash fzf sort", "bash fzf coreutils",
    "files.txtをfzfへ渡し、docs/で始まる候補だけselected.txtへ昇順保存。\n"
    "端末ではfzfに入力→候補を確認→Enter。自動実行では--filterを使います。\n"
    "fzfは候補の供給元ではなく選択器であることを確認します。",
    fzf_setup, fzf_check,
    '''fzf --filter='^docs/' < files.txt | sort > selected.txt''',
    ["cp files.txt selected.txt"])


def tls_setup(root):
    name = "app-" + secrets.token_hex(4) + ".dojo.test"
    put(root, "hostname.txt", name + "\n")
    remember(root, {"name": name}, ["hostname.txt"])


def tls_check(root):
    data = fixture(root)
    require(stat.S_IMODE((root / "server.key").stat().st_mode) == 0o600, "秘密鍵の権限を600にします。")
    run(root, "openssl", "verify", "-CAfile", "server.crt", "-verify_hostname", data["name"], "server.crt")
    result = subprocess.run(["openssl", "verify", "-CAfile", "server.crt", "-verify_hostname", "wrong.dojo.test", "server.crt"], cwd=root, capture_output=True, timeout=5)
    require(result.returncode != 0, "別ホスト名では検証が失敗する必要があります。")
    cert_pub = run(root, "openssl", "x509", "-in", "server.crt", "-pubkey", "-noout")
    key_pub = run(root, "openssl", "pkey", "-in", "server.key", "-pubout")
    require(cert_pub == key_pub, "証明書と秘密鍵が一致しません。")
    require("notAfter=" in read(root, "expiry.txt"), "証明書の期限を確認・記録します。")


add("tls", "OpenSSLで証明書・鍵・名前・期限を確認する", "bash openssl", "bash openssl",
    "hostname.txtをSANに持つ訓練用自己署名証明書server.crtと秘密鍵server.key(600)を作成。\n"
    "openssl verify -CAfile server.crt -verify_hostname で正しい名前だけ成功することを確認。\n"
    "openssl x509 -enddateの結果をexpiry.txtへ。公開CAの発行や自動更新はVMの次の学習範囲。",
    tls_setup, tls_check,
    '''name=$(cat hostname.txt)
umask 077
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -keyout server.key -out server.crt -subj "/CN=$name" -addext "subjectAltName=DNS:$name"
chmod 600 server.key
openssl verify -CAfile server.crt -verify_hostname "$name" server.crt
openssl x509 -in server.crt -noout -enddate > expiry.txt''',
    ["name=$(cat hostname.txt); openssl req -x509 -newkey rsa:2048 -nodes -days 2 -keyout server.key -out server.crt -subj /CN=wrong.dojo.test -addext subjectAltName=DNS:wrong.dojo.test; chmod 600 server.key; openssl x509 -in server.crt -noout -enddate > expiry.txt"])


def incident_setup(root):
    token = secrets.token_hex(8)
    put(root, "app/config.json", json.dumps({"input": "missing.json", "field": "value"}))
    put(root, "app/source.json", json.dumps({"value": token}))
    put(root, "app/service.py", '''import json
from pathlib import Path
c = json.loads(Path('config.json').read_text())
v = json.loads(Path(c['input']).read_text())
print(v[c['field']])
''')
    remember(root, {"token": token}, ["app/source.json", "app/service.py"])


def incident_check(root):
    data = fixture(root)
    require(read(root, "before.stderr").find("FileNotFoundError") >= 0, "失敗時の標準エラーを保存し、原因を調べます。")
    require(read(root, "before.exit").strip() == "1", "失敗時の終了コードを保存します。")
    config = json.loads(read(root, "app/config.json"))
    require(config == {"input": "source.json", "field": "value"}, "プログラムを変更して隠さず、入力設定だけを復旧します。")
    require(run(root / "app", "python3", "service.py").strip() == data["token"], "設定復旧後に実行が成功しません。")
    require(read(root, "after.stdout").strip() == data["token"], "修正後の出力を保存します。")
    require(read(root, "after.stderr") == "", "修正後に標準エラーが残っています。")


add("incident", "総合：失敗を再現し、根拠を残して設定を復旧", "bash python3 jq", "bash python3 jq",
    "app内でpython3 service.pyを実行し、失敗の標準エラーをbefore.stderr、終了コードをbefore.exitへ。\n"
    "エラーと設定・入力ファイルを読み、config.jsonだけを修正。コードや原本の変更は禁止。\n"
    "再実行の出力をafter.stdout、標準エラーをafter.stderrへ保存。原因と確認方法を説明できること。",
    incident_setup, incident_check,
    '''set +e
(cd app && python3 service.py) > before.stdout 2> before.stderr
printf '%s\\n' "$?" > before.exit
set -e
jq '.input="source.json"' app/config.json > app/config.fixed
mv -- app/config.fixed app/config.json
(cd app && python3 service.py) > after.stdout 2> after.stderr''',
    ["echo 1 > before.exit; echo FileNotFoundError > before.stderr; cp app/source.json after.stdout; : > after.stderr"])


def release_setup(root):
    revision = secrets.token_hex(8)
    put(root, "source/release.json", json.dumps({"version": revision, "state": "ready"}))
    put(root, "source/private.env", "DO_NOT_SHIP=" + secrets.token_hex(8))
    put(root, "source/run.sh", '#!/bin/sh\nprintf "ready\\n"\n', 0o755)
    remember(root, {"version": revision}, ["source/release.json", "source/private.env", "source/run.sh"])


def release_check(root):
    data = fixture(root)
    check_checksum(root, "release.tar.gz", "release.sha256")
    check_tar(root, "release.tar.gz", {"release.json": "source/release.json", "run.sh": "source/run.sh"})
    names = run(root, "tar", "-tzf", "release.tar.gz").splitlines()
    require(not any("private.env" in name for name in names), "配布アーカイブに秘密情報を含めません。")
    require(json.loads(read(root, "deployed/release.json"))["version"] == data["version"], "展開したリリースの版を確認します。")
    require(not (root / "deployed/private.env").exists(), "展開先に秘密情報があります。")
    for name in ("release.json", "run.sh"):
        require((root / "deployed" / name).read_bytes() == (root / "source" / name).read_bytes(), "配備ファイルと原本が一致しません。")
    require(os.access(root / "deployed/run.sh", os.X_OK), "実行権限を保持します。")
    require(run(root, "./deployed/run.sh").strip() == "ready", "展開後に実行できません。")
    require(read(root, "version.txt").strip() == data["version"], "jqで展開後の版を確認します。")


add("release", "総合：秘密を除外して梱包・検証・配備する", "bash tar sha256sum jq", "bash tar coreutils jq",
    "sourceの中身をrelease.tar.gzへ。ただしprivate.envは除外。SHA-256をrelease.sha256へ。\n"
    "検証後deployedへ展開しrun.shを実行。展開したrelease.jsonのversionをjq -rでversion.txtへ。\n"
    "原本保持、秘密除外、実行権限保持、実行確認、版確認を一通り行います。",
    release_setup, release_check,
    '''tar --exclude=private.env -czf release.tar.gz -C source .
sha256sum release.tar.gz > release.sha256
sha256sum -c release.sha256
mkdir -p deployed
tar -xzf release.tar.gz -C deployed
./deployed/run.sh
jq -r .version deployed/release.json > version.txt''',
    ["tar -czf release.tar.gz -C source .; sha256sum release.tar.gz > release.sha256; mkdir -p deployed; tar -xzf release.tar.gz -C deployed; jq -r .version deployed/release.json > version.txt"])


WRITER = """#!/usr/bin/env bash
# usage: ./writer.sh COUNT  -- app.log へ連番の行を COUNT 行追記する(開き直す通常のアプリ相当)
set -euo pipefail
n=$(cat writer.seq)
for _ in $(seq "$1"); do
  n=$((n + 1))
  printf 'seq %06d event\\n' "$n" >> app.log
done
echo "$n" > writer.seq
"""


def logrotate_setup(root):
    put(root, "writer.sh", WRITER, 0o755)
    put(root, "app.log", "".join(f"seq {n:06d} event\n" for n in range(1, 41)))
    put(root, "writer.seq", "40\n")
    remember(root, {"inode": (root / "app.log").stat().st_ino}, ["writer.sh"])


def logrotate_lines(root):
    import gzip
    names = ["app.log.3.gz", "app.log.2.gz", "app.log.1", "app.log"]
    lines = []
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if name.endswith(".gz"):
            require(data[:2] == b"\x1f\x8b", name + " が実gzipではありません。")
            try:
                data = gzip.decompress(data)
            except (OSError, EOFError):
                raise ValueError(name + " を展開できません。")
        else:
            require(data[:2] != b"\x1f\x8b", name + " は delaycompress により未圧縮のはずです。")
        lines += data.decode().splitlines()
    return lines


def logrotate_check(root):
    data = fixture(root)
    conf = read(root, "rotate.conf")
    for pattern, message in ((r"^\s*(daily|size\s+\S+)\s*$", "daily か size で回転条件を指定します。"),
                             (r"^\s*rotate\s+3\s*$", "世代は rotate 3。"),
                             (r"^\s*compress\s*$", "compress が必要です。"),
                             (r"^\s*delaycompress\s*$", "delaycompress が必要です。"),
                             (r"^\s*missingok\s*$", "missingok が必要です。"),
                             (r"^\s*notifempty\s*$", "notifempty が必要です。"),
                             (r"^\s*copytruncate\s*$", "書込み継続のため copytruncate が必要です。")):
        require(re.search(pattern, conf, re.M), message)
    require("app.log" in conf, "rotate.conf の対象に app.log を指定します。")
    require("considering log" in read(root, "dry-run.txt") and "app.log" in read(root, "dry-run.txt"),
            "logrotate -d の予行出力を dry-run.txt に保存します。")
    # 構文は実logrotateの予行で検証する。状態ファイルは使い捨てで本物の state を汚さない。
    with tempfile.TemporaryDirectory() as scratch:
        run(root, "logrotate", "-d", "-s", str(Path(scratch) / "state"), "rotate.conf")
    require((root / "state").is_file(), "-s state で実rotateの状態ファイルを作ります。")
    require((root / "app.log.1").is_file() and (root / "app.log.2.gz").is_file()
            and (root / "app.log.3.gz").is_file(), "app.log.1(非圧縮)・.2.gz・.3.gz が揃うまで回転します。")
    extra = [p.name for p in root.glob("app.log.*")
             if p.name not in ("app.log.1", "app.log.2.gz", "app.log.3.gz")]
    require(not extra, "世代が多すぎます/不要: " + ", ".join(extra))
    lines = logrotate_lines(root)
    total = int(read(root, "writer.seq"))
    seqs = []
    for line in lines:
        match = re.fullmatch(r"seq (\d{6}) event", line)
        require(match, "壊れたログ行があります: " + line[:40])
        seqs.append(int(match.group(1)))
    require(seqs and seqs == list(range(seqs[0], seqs[-1] + 1)), "ログ行の欠落・重複・順序違いがあります。")
    require(seqs[-1] == total, "最新の追記行が失われています(copytruncate中の取りこぼし)。")
    require(seqs[0] > 1, "4回以上回転して古い世代を実際に破棄するまで確認します。")
    require((root / "app.log").stat().st_ino == data["inode"], "app.log のinodeが変わっています(copytruncateで元ファイルを使い続けます)。")
    require(len((root / "app.log").read_text().splitlines()) <= 20, "app.log が最後の回転後も大きいままです。")
    require(sum(p.stat().st_size for p in root.glob("app.log*")) < 20000, "保存量が制限を超えています。")
    require(os.access(root / "app.log", os.W_OK), "app.log に書込みできません。")


add("logrotate", "logrotateで世代管理し、書込み中のログを失わず回転する", "bash logrotate gzip", "bash logrotate gzip",
    "app.log を rotate.conf で管理(対象は二重引用符付きで \"app.log\" {...} と書く)。daily(または size)・rotate 3・compress+delaycompress・missingok・notifempty・\n"
    "copytruncate を設定。logrotate -d -s state rotate.conf の出力を dry-run.txt に保存してから、\n"
    "./writer.sh 20 で追記しつつ logrotate -s state -f rotate.conf を5回実行。\n"
    "app.log.1 は非圧縮、.2.gz と .3.gz は gzip、世代は最大3、app.log の inode は維持、行の欠落なし。",
    logrotate_setup, logrotate_check,
    '''cat > rotate.conf <<'CONF'
"app.log" {
    daily
    rotate 3
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
CONF
logrotate -d -s state rotate.conf > dry-run.txt 2>&1
for i in 1 2 3 4 5; do
  ./writer.sh 20
  logrotate -s state -f rotate.conf
done
./writer.sh 5''',
    ["printf '\"app.log\" {\\n daily\\n rotate 3\\n compress\\n delaycompress\\n missingok\\n notifempty\\n create\\n}\\n' > rotate.conf; logrotate -d -s state rotate.conf > dry-run.txt 2>&1; for i in 1 2 3 4 5; do ./writer.sh 20; logrotate -s state -f rotate.conf; done",
     "printf '\"app.log\" {\\n daily\\n rotate 3\\n compress\\n delaycompress\\n missingok\\n notifempty\\n copytruncate\\n}\\n' > rotate.conf; logrotate -d -s state rotate.conf > dry-run.txt 2>&1; for i in 1 2; do ./writer.sh 20; logrotate -s state -f rotate.conf; done"])


# ---------------------------------------------------------------------------
# cron: 実cronデーモンは使わず、スケジュールを自前の解析器で検証し、登録行の
# コマンドを cron と同じ最小環境(env -i, PATH=/usr/bin:/bin, % の改行化)で実行する。
# ---------------------------------------------------------------------------
import datetime

CRON_JOB = """#!/bin/sh
# cron から呼ばれるジョブ。report-tool は tools/ にあり、cron の既定PATHには無い。
report-tool begin
sleep 1
echo "tick"
echo "warn" >&2
report-tool end
"""
CRON_TOOL = """#!/bin/sh
printf '%s %s\\n' "$1" "$$" >> "$(dirname "$0")/../work/runs.txt"
"""
CRON_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
              "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
              "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
CRON_REFERENCE = datetime.datetime(2026, 3, 6, 12, 0)  # 金曜の昼


def cron_field(text, lo, hi, names=False):
    values = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, raw = part.split("/", 1)
            require(raw.isdigit() and int(raw) > 0, "刻み幅が不正です: " + text)
            step = int(raw)

        def number(token):
            if names and token.lower() in CRON_NAMES:
                return CRON_NAMES[token.lower()]
            require(token.isdigit(), "数値でない値: " + token)
            return int(token)
        if part == "*":
            first, last = lo, hi
        elif "-" in part:
            first, last = (number(x) for x in part.split("-", 1))
        else:
            first = last = number(part)
        require(lo <= first <= last <= hi, "範囲外の値: " + text)
        values.update(range(first, last + 1, step))
    return values


def cron_parse(fields):
    require(len(fields) == 5, "スケジュールは5フィールドです。")
    minute = cron_field(fields[0], 0, 59)
    hour = cron_field(fields[1], 0, 23)
    dom = cron_field(fields[2], 1, 31)
    month = cron_field(fields[3], 1, 12, True)
    dow = {v % 7 for v in cron_field(fields[4], 0, 7, True)}
    return dict(minute=minute, hour=hour, dom=dom, month=month, dow=dow,
                dom_star=fields[2].startswith("*"), dow_star=fields[4].startswith("*"))


def cron_fires(spec, start, count):
    fires = []
    for offset in range(800):
        day = start.date() + datetime.timedelta(days=offset)
        weekday = (day.weekday() + 1) % 7
        in_dom, in_dow = day.day in spec["dom"], weekday in spec["dow"]
        if spec["dom_star"] or spec["dow_star"]:
            ok = in_dom and in_dow
        else:
            ok = in_dom or in_dow
        if not ok or day.month not in spec["month"]:
            continue
        for hour in sorted(spec["hour"]):
            for minute in sorted(spec["minute"]):
                moment = datetime.datetime(day.year, day.month, day.day, hour, minute)
                if moment > start:
                    fires.append(moment)
                    if len(fires) == count:
                        return fires
    return fires


def cron_split_percent(command):
    """cron は最初のエスケープされていない % でコマンドを切り、以降を標準入力にする。"""
    body, stdin, seen = "", "", False
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and command[index + 1:index + 2] == "%":
            if seen:
                stdin += "%"
            else:
                body += "%"
            index += 2
            continue
        if char == "%":
            if seen:
                stdin += "\n"
            seen = True
        elif seen:
            stdin += char
        else:
            body += char
        index += 1
    return body, (stdin if seen else None)


def cron_setup(root):
    minute, first = secrets.randbelow(50) + 5, secrets.randbelow(3) + 1
    last = first + secrets.randbelow(3) + 2
    put(root, "job.sh", CRON_JOB, 0o755)
    put(root, "tools/report-tool", CRON_TOOL, 0o755)
    put(root, "requirements.env", f"MINUTE={minute}\nHOUR_FROM={first}\nHOUR_TO={last}\n")
    (root / "work").mkdir()
    (root / "logs").mkdir()
    (root / "home").mkdir()
    remember(root, {"minute": minute, "first": first, "last": last},
             ["job.sh", "tools/report-tool", "requirements.env"])


def cron_entry(root):
    env, entries = {}, []
    for line in read(root, "crontab.txt").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if match:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            env[match.group(1)] = value
        else:
            entries.append(stripped)
    require(len(entries) == 1, "crontab.txt のジョブ行はちょうど1行にします。")
    parts = entries[0].split(None, 5)
    require(len(parts) == 6, "5フィールドの後にコマンドが必要です。")
    return env, parts[:5], parts[5]


def cron_launch(root, env, command):
    body, stdin = cron_split_percent(command)
    shell = env.get("SHELL", "/bin/sh")
    require(os.path.isfile(shell), "SHELL が存在しません: " + shell)
    cron_env = {"PATH": "/usr/bin:/bin", "SHELL": "/bin/sh", "HOME": str(root / "home"),
                "LOGNAME": "dojo", "LC_ALL": "C"}
    cron_env.update(env)
    argv = ["env", "-i"] + [k + "=" + v for k, v in cron_env.items()] + [shell, "-c", body]
    return subprocess.Popen(argv, cwd=root / "home", stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True), stdin


def cron_finish(proc, stdin):
    try:
        proc.communicate(stdin or "", timeout=12)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise ValueError("cron 実行がタイムアウトしました。")
    return proc.returncode


def cron_events(root):
    path = root / "work/runs.txt"
    words = [line.split()[0] for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return words.count("begin"), words.count("end")


def cron_check(root):
    data = fixture(root)
    env, fields, command = cron_entry(root)
    spec = cron_parse(fields)
    expected = []
    moment = CRON_REFERENCE
    while len(expected) < 6:
        moment += datetime.timedelta(minutes=1)
        if (moment.minute == data["minute"] and data["first"] <= moment.hour <= data["last"]
                and moment.weekday() < 5):
            expected.append(moment)
    require(cron_fires(spec, CRON_REFERENCE, 6) == expected,
            f"次回実行が要件(平日 {data['first']}-{data['last']} 時の {data['minute']} 分)と一致しません。")
    for name in ("runs.txt",):
        (root / "work" / name).unlink(missing_ok=True)
    for old in (root / "logs").glob("*"):
        old.unlink()
    # 1回目: cron の最小環境で実行して成功し、標準出力と標準エラーがログへ入ること。
    proc, stdin = cron_launch(root, env, command)
    status = cron_finish(proc, stdin)
    require(status == 0, "最小環境(PATH=/usr/bin:/bin)でコマンドが失敗しました。PATH や % の扱いを確認します。")
    require(cron_events(root) == (1, 1), "ジョブが1回だけ完走していません(PATH不足や % の切断の疑い)。")
    today = datetime.date.today().isoformat()
    logs = list((root / "logs").glob("*"))
    require(len(logs) == 1 and re.fullmatch(r"job-\d{4}-\d{2}-\d{2}\.log", logs[0].name),
            "logs/job-YYYY-MM-DD.log へ出力します(date の % は \\% にする)。")
    require(logs[0].name == f"job-{today}.log", "ログ名の日付が今日ではありません。")
    text = logs[0].read_text()
    require("tick" in text and "warn" in text, "標準出力と標準エラーの両方をログへ(>> file 2>&1)。")
    # 2回目: 重なる2起動。flock -n により片方だけが実行される。
    (root / "work/runs.txt").unlink()
    first, first_in = cron_launch(root, env, command)
    time.sleep(0.4)
    second, second_in = cron_launch(root, env, command)
    cron_finish(first, first_in)
    cron_finish(second, second_in)
    require(cron_events(root) == (1, 1), "重複起動を防げていません。flock -n でロックを取れなければ即終了します。")


add("cron", "cron: 最小環境・%・多重起動を考えて定期実行を書く", "bash flock env sleep date", "bash util-linux coreutils",
    "requirements.env の MINUTE / HOUR_FROM / HOUR_TO を使い、平日(月-金)の HOUR_FROM-HOUR_TO 時の MINUTE 分に ./job.sh を実行する\n"
    "crontab.txt を書く(ジョブ行は1行、cron デーモンは使わない)。cron の環境は PATH=/usr/bin:/bin で非常に小さい: job.sh が使う tools/report-tool に\n"
    "届くよう crontab 先頭で PATH= を設定。コマンドは絶対パス(現在のフォルダ)で書き、flock -n で重複起動を防ぎ、\n"
    "出力は logs/job-YYYY-MM-DD.log へ標準出力・標準エラーとも追記(date の % は \\% と書く)。\n"
    "判定は自前の cron 解析器で次回実行を計算し、env -i の最小環境でコマンドを実際に実行し、重なる2起動で二重実行が無いか確認する。",
    cron_setup, cron_check,
    '''. ./requirements.env
R="$PWD"
cat > crontab.txt <<EOF
PATH=$R/tools:/usr/bin:/bin
$MINUTE $HOUR_FROM-$HOUR_TO * * 1-5 flock -n $R/job.lock $R/job.sh >> $R/logs/job-\\$(date +\\%F).log 2>&1
EOF''',
    ['. ./requirements.env\nR="$PWD"\nprintf \'%s %s-%s * * 1-5 %s/job.sh >> %s/logs/job-$(date +%%F).log 2>&1\\n\' "$MINUTE" "$HOUR_FROM" "$HOUR_TO" "$R" "$R" > crontab.txt',
     '. ./requirements.env\nR="$PWD"\nprintf \'PATH=%s/tools:/usr/bin:/bin\\n* * * * * flock -n %s/job.lock %s/job.sh >> %s/logs/job-$(date +\\\\%%F).log 2>&1\\n\' "$R" "$R" "$R" "$R" > crontab.txt',
     '. ./requirements.env\nR="$PWD"\nprintf \'PATH=%s/tools:/usr/bin:/bin\\n%s %s-%s * * 1-5 flock %s/job.lock %s/job.sh >> %s/logs/job-$(date +\\\\%%F).log 2>&1\\n\' "$R" "$MINUTE" "$HOUR_FROM" "$HOUR_TO" "$R" "$R" "$R" > crontab.txt'])


# ---------------------------------------------------------------------------
# trap: 危険な bash スクリプトを、失敗注入(途中失敗・SIGINT/SIGTERM・入力欠落・
# 多重起動)の下で実際に走らせて判定する。
# ---------------------------------------------------------------------------
import signal

TRAP_UNSAFE = """#!/bin/bash
# usage: deploy.sh INPUT OUTPUT   (環境変数: WORK_ROOT 作業場所, STEP_CMD 変換コマンド)
WORK_ROOT=${WORK_ROOT:-/tmp}
STEP_CMD=${STEP_CMD:-cat}
tmp=$(mktemp -d $WORK_ROOT/build.XXXXXX)
touch $WORK_ROOT/deploy.lock
cat $1 | sort -u > $tmp/sorted
bash -c "$STEP_CMD" < $tmp/sorted > $2
rm -rf $tmp
rm -f $WORK_ROOT/deploy.lock
echo done
"""


def trap_setup(root):
    words = [secrets.token_hex(3) for _ in range(5)]
    lines = words + words[:2] + [secrets.token_hex(3)]
    secrets.SystemRandom().shuffle(lines)
    put(root, "input.txt", "".join(line + "\n" for line in lines))
    put(root, "deploy.sh", TRAP_UNSAFE, 0o755)
    put(root, "deploy.orig.sh", TRAP_UNSAFE, 0o644)
    remember(root, {"expected": "".join(w + "\n" for w in sorted(set(lines))).upper()},
             ["deploy.orig.sh", "input.txt"])


def trap_check(root):
    import tempfile as tf
    data = fixture(root)
    script = root / "deploy.sh"
    require(script.is_file() and os.access(script, os.X_OK), "deploy.sh は実行可能にします。")
    require(script.read_bytes() != (root / "deploy.orig.sh").read_bytes(), "deploy.sh を修正していません。")
    run(root, "bash", "-n", "deploy.sh")
    with tf.TemporaryDirectory(prefix="dojo-trap-") as scratch:
        base = Path(scratch)
        work, tmpdir = base / "work dir", base / "tmp dir"
        work.mkdir()
        tmpdir.mkdir()
        source, out, marker = base / "in put.txt", base / "out put.txt", base / "started"
        source.write_text((root / "input.txt").read_text())

        def start(step, args=None, group=False):
            env = {"PATH": os.environ["PATH"], "LC_ALL": "C", "WORK_ROOT": str(work),
                   "TMPDIR": str(tmpdir), "STEP_CMD": step}
            argv = ["bash", str(script)] + (args if args is not None else [str(source), str(out)])
            return subprocess.Popen(argv, cwd=base, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    start_new_session=group)

        def finish(proc):
            try:
                o, e = proc.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise ValueError("スクリプトが終了しません(シグナルでも中断できない)。")
            return proc.returncode, o, e

        def clean(label, allow=()):
            leftover = sorted(p.name for p in work.iterdir() if p.name not in allow)
            require(not leftover, label + ": 作業領域に残骸があります: " + ", ".join(leftover))
            require(not list(tmpdir.iterdir()), label + ": TMPDIR に残骸があります。")

        # 1) 正常系: 空白入りパスでも動き、出力は正しく、一時物は消える。
        code, o, e = finish(start("tr a-z A-Z"))
        require(code == 0, "正常系が失敗しました: " + e[-200:])
        require(out.read_text() == data["expected"], "正常系の出力が違います(空白入りパスは引用符で守る)。")
        clean("正常系")
        out.unlink()
        # 2) 入力欠落: 終了コード2・診断を標準エラーへ・何も作らない。
        code, o, e = finish(start("cat", [str(base / "missing.txt"), str(out)]))
        require(code == 2 and e.strip() and not out.exists(), "入力欠落は終了コード2・標準エラーに診断・出力なし。")
        clean("入力欠落")
        # 3) 入力がディレクトリ: pipefail が無いと cat の失敗が見逃される。
        code, o, e = finish(start("cat", [str(base), str(out)]))
        require(code != 0 and not out.exists(), "入力が読めないのに成功扱いです(set -o pipefail)。")
        clean("読めない入力")
        # 4) 途中失敗: 終了コードを保ち、部分出力を残さず、既存の出力は壊さない。
        out.write_text("OLD\n")
        code, o, e = finish(start("echo partial; exit 7"))
        require(code == 7, f"途中失敗の終了コードは 7 のはず(実際 {code})。")
        require(out.read_text() == "OLD\n", "失敗時に出力ファイルを壊しています(一時領域へ作って最後に mv)。")
        clean("途中失敗")
        out.unlink()
        code, o, e = finish(start("echo partial; exit 9"))
        require(code == 9 and not out.exists(), "失敗時に部分出力が残っています。")
        clean("途中失敗(新規)")
        # 5) 多重起動: 既存ロックがあれば終了コード75、他者のロックは消さない。
        (work / "deploy.lock").write_text("")
        code, o, e = finish(start("cat"))
        require(code == 75 and not out.exists(), "ロック保持中は終了コード75で何もしません。")
        require((work / "deploy.lock").exists(), "他者のロックを消してはいけません。")
        clean("ロック保持", allow=("deploy.lock",))
        (work / "deploy.lock").unlink()
        # 6) SIGINT / SIGTERM: 実行中に中断しても一時物・ロックを残さず、出力も無い。
        for sig, codes in ((signal.SIGTERM, (143, -15)), (signal.SIGINT, (130, -2))):
            marker.unlink(missing_ok=True)
            proc = start(f"touch '{marker}'; sleep 30", group=True)
            for _ in range(100):
                if marker.exists():
                    break
                time.sleep(0.05)
            require(marker.exists(), "処理が開始しませんでした。")
            os.killpg(proc.pid, sig)
            code, o, e = finish(proc)
            require(code in codes, f"{sig.name} での終了コードは {codes[0]}(実際 {code})。")
            require(not out.exists(), sig.name + " 後に出力が残っています。")
            clean(sig.name)


add("trap", "trap と set -euo pipefail で安全に後始末するスクリプトにする", "bash mktemp sort python3", "bash coreutils python3",
    "deploy.sh(INPUT OUTPUT を受け取り、WORK_ROOT 配下に一時ディレクトリとロック deploy.lock を作る)は危険な書き方です。修正して次を満たす: \n"
    "set -euo pipefail、trap cleanup EXIT で一時ディレクトリとロックを必ず削除(ただし他者のロックは消さない)、変数の引用符、\n"
    "引数/入力不足は終了コード2(標準エラーに診断)、ロック既存は終了コード75、STEP_CMD 失敗時はその終了コードを保つ、\n"
    "SIGTERM は143・SIGINT は130、出力は一時領域に作って最後に mv(失敗時に部分出力や既存出力の破壊なし)。\n"
    "判定は deploy.sh を失敗注入(途中失敗・SIGINT/SIGTERM・入力欠落・ディレクトリ入力・ロック保持・空白入りパス)の下で実際に実行する。deploy.orig.sh は原本。",
    trap_setup, trap_check,
    '''cat > deploy.sh <<'SCRIPT'
#!/bin/bash
set -euo pipefail
WORK_ROOT=${WORK_ROOT:-/tmp}
STEP_CMD=${STEP_CMD:-cat}
if [ "$#" -ne 2 ] || [ ! -r "$1" ]; then
  echo "usage: deploy.sh INPUT OUTPUT (INPUT must be readable)" >&2
  exit 2
fi
in=$1
out=$2
lock="$WORK_ROOT/deploy.lock"
tmp=""
have_lock=0
cleanup() {
  rc=$?
  trap - EXIT
  [ -z "$tmp" ] || rm -rf -- "$tmp"
  [ "$have_lock" -eq 0 ] || rm -f -- "$lock"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
if ! ( set -o noclobber; : > "$lock" ) 2>/dev/null; then
  echo "another run holds $lock" >&2
  exit 75
fi
have_lock=1
tmp=$(mktemp -d "$WORK_ROOT/build.XXXXXX")
cat -- "$in" | sort -u > "$tmp/sorted"
bash -c "$STEP_CMD" < "$tmp/sorted" > "$tmp/out"
mv -- "$tmp/out" "$out"
echo done
SCRIPT
chmod +x deploy.sh''',
    ['sed -i \'s/^WORK_ROOT=/set -e\\nWORK_ROOT=/; s#\\$WORK_ROOT#"$WORK_ROOT"#g; s#\\$1#"$1"#; s#\\$2#"$2"#; s#\\$tmp#"$tmp"#g\' deploy.sh',
     'cat > deploy.sh <<\'S\'\n#!/bin/bash\nset -euo pipefail\nWORK_ROOT=${WORK_ROOT:-/tmp}\nSTEP_CMD=${STEP_CMD:-cat}\n[ -r "$1" ] || { echo bad >&2; exit 2; }\ntmp=$(mktemp -d "$WORK_ROOT/build.XXXXXX")\ntrap \'rm -rf "$tmp"\' EXIT\ncat -- "$1" | sort -u > "$tmp/sorted"\nbash -c "$STEP_CMD" < "$tmp/sorted" > "$2"\necho done\nS']
    )


# ---------------------------------------------------------------------------
# tcpdump: ループバックの実キャプチャは CAP_NET_RAW が必要で、非特権の検証環境では
# 不可能(Operation not permitted)。そのため setup が決定的な pcap を生成し、
# 利用者は tcpdump -r で BPF フィルタ・-nn・-A・-c・-w を練習する。実キャプチャ
# (tcpdump -i lo -w)そのものは判定しない。
# ---------------------------------------------------------------------------
import struct


def _inet_checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _ip_packet(src, dst, proto, payload, ident):
    s, d = bytes(map(int, src.split("."))), bytes(map(int, dst.split(".")))
    head = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), ident, 0x4000, 64, proto, 0, s, d)
    head = head[:10] + struct.pack("!H", _inet_checksum(head)) + head[12:]
    pseudo = s + d + struct.pack("!BBH", 0, proto, len(payload))
    return head, pseudo


def _tcp(src, sport, dst, dport, seq, ack, flags, payload, ident):
    header = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 5 << 4, flags, 65535, 0, 0)
    ip, pseudo = _ip_packet(src, dst, 6, header + payload, ident)
    check = _inet_checksum(pseudo + header + payload)
    header = header[:16] + struct.pack("!H", check) + header[18:]
    return ip + header + payload


def _udp(src, sport, dst, dport, payload, ident):
    header = struct.pack("!HHHH", sport, dport, 8 + len(payload), 0)
    ip, pseudo = _ip_packet(src, dst, 17, header + payload, ident)
    check = _inet_checksum(pseudo + header + payload) or 0xFFFF
    return ip + header[:6] + struct.pack("!H", check) + payload


def _dns(name, response):
    labels = b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\0"
    body = struct.pack("!HHHHHH", 0x1234, 0x8180 if response else 0x0100, 1, 1 if response else 0, 0, 0)
    body += labels + struct.pack("!HH", 1, 1)
    if response:
        body += b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + bytes([93, 184, 216, 34])
    return body


def make_pcap(port, client, tokens, others):
    """決定的な pcap バイト列と、期待値(接続数・各フローの件数)を返す。"""
    server = "10.0.0.1"
    packets, ident, ports = [], [100], [40000]

    def add_packet(frame):
        ident[0] += 1
        packets.append(b"\0\0\0\0\0\2" + b"\0\0\0\0\0\1" + b"\x08\x00" + frame)

    def flow(host, dport, request, response):
        sport = ports[0] = ports[0] + 1
        seq, sack = 1000, 5000
        steps = [(host, sport, server, dport, seq, 0, 0x02, b""),
                 (server, dport, host, sport, sack, seq + 1, 0x12, b""),
                 (host, sport, server, dport, seq + 1, sack + 1, 0x10, b""),
                 (host, sport, server, dport, seq + 1, sack + 1, 0x18, request),
                 (server, dport, host, sport, sack + 1, seq + 1 + len(request), 0x10, b""),
                 (server, dport, host, sport, sack + 1, seq + 1 + len(request), 0x18, response),
                 (host, sport, server, dport, seq + 1 + len(request), sack + 1 + len(response), 0x10, b""),
                 (host, sport, server, dport, seq + 1 + len(request), sack + 1 + len(response), 0x11, b""),
                 (server, dport, host, sport, sack + 1 + len(response), seq + 2 + len(request), 0x11, b""),
                 (host, sport, server, dport, seq + 2 + len(request), sack + 2 + len(response), 0x10, b"")]
        for step in steps:
            ident[0] += 1
            add_packet(_tcp(*step, ident[0]))

    def get(path):
        return f"GET {path} HTTP/1.1\r\nHost: dojo.local\r\nUser-Agent: curl/8\r\n\r\n".encode()
    ok = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
    others = list(others)
    flow(client, port, get("/r/" + tokens[0]), ok)
    flow(client, 9000, get("/health"), ok)
    for index, token in enumerate(others):
        flow("10.0.0.%d" % (20 + index), port, get("/other/" + token), ok)
    for name in ("example.org", "dojo.local"):
        ident[0] += 1
        add_packet(_udp(client, 53000 + ident[0], "10.0.0.53", 53, _dns(name, False), ident[0]))
        ident[0] += 1
        add_packet(_udp("10.0.0.53", 53, client, 53000 + ident[0] - 1, _dns(name, True), ident[0]))
    for _ in range(3):
        ident[0] += 1
        add_packet(_tcp(client, 50022, server, 22, 1, 1, 0x10, b"SSH-2.0-OpenSSH_9\r\n", ident[0]))
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for number, frame in enumerate(packets):
        stamp = 1700000000 + number // 100
        out += struct.pack("<IIII", stamp, (number % 100) * 10000, len(frame), len(frame)) + frame
    return out, {"connections": 1 + len(others), "request": "GET /r/" + tokens[0] + " HTTP/1.1"}


def tcpdump_setup(root):
    port = secrets.choice([8080, 8000, 3000, 5000])
    client = "10.0.0.5"
    token = secrets.token_hex(4)
    others = [secrets.token_hex(3) for _ in range(secrets.randbelow(3) + 2)]
    data, expected = make_pcap(port, client, [token], others)
    (root / "traffic.pcap").write_bytes(data)
    put(root, "params.env", f"PORT={port}\nCLIENT={client}\n")
    remember(root, {"port": port, "client": client, **expected}, ["traffic.pcap", "params.env"])


def tcpdump_lines(root, path, *filter_args, strip_time=False, count=None):
    argv = ["tcpdump", "-nn", "-tt", "-r", path] + (["-c", str(count)] if count else []) + list(filter_args)
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=15,
                            env={"PATH": os.environ["PATH"], "LC_ALL": "C", "TZ": "UTC"})
    require(result.returncode == 0, path + " を tcpdump -r で読めません: " + result.stderr[-200:])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return [line.split(None, 1)[1] for line in lines] if strip_time else lines


def tcpdump_check(root):
    data = fixture(root)
    port = data["port"]
    web = root / "web.pcap"
    require(web.is_file() and web.read_bytes()[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"),
            "web.pcap は tcpdump -w で書いた pcap にします。")
    expected = tcpdump_lines(root, "traffic.pcap", f"tcp port {port}")
    require(len(expected) == (data["connections"]) * 10, "フィクスチャ検証: 想定パケット数と実tcpdumpの結果が違います。")
    require(tcpdump_lines(root, "web.pcap") == expected,
            f"web.pcap は traffic.pcap から tcp port {port} だけを抜き出した内容(全パケット・順序)にします。")
    require(read(root, "request-line.txt").strip() == data["request"],
            f"{data['client']} から {port} への HTTP リクエスト行だけを request-line.txt に(tcpdump -nn -A -r と BPF)。")
    require(read(root, "new-conns.txt").strip() == str(data["connections"]),
            f"ポート {port} への新規接続数(SYN のみ)を new-conns.txt に。BPF の tcpflags で SYN-ACK を除外する。")
    first = [line.split(None, 1)[1] for line in read(root, "first3.txt").splitlines() if line.strip()]
    require(first == tcpdump_lines(root, "traffic.pcap", strip_time=True, count=3),
            "先頭3パケットを -nn -c 3 -r で first3.txt に保存します(名前解決なし)。")


add("tcpdump", "tcpdump: pcap を BPF で絞り、-nn -A -c -w -r で読む", "bash tcpdump grep wc", "bash tcpdump grep coreutils",
    "注意: ループバックの実キャプチャ(tcpdump -i lo -w)は CAP_NET_RAW が必要で、非特権環境では使えないため、"
    "この実習は setup が作った traffic.pcap(Ethernet/IPv4、HTTP・DNS・SSH 混在)を tcpdump -r で読む形式です(実キャプチャは判定しません)。\n"
    "params.env の PORT と CLIENT を使い、traffic.pcap は変更せず: (1) tcp port PORT のパケットだけを -w で web.pcap に保存。\n"
    "(2) CLIENT から PORT への HTTP リクエスト行(GET ... HTTP/1.1 の1行。tcpdump は 8080 等で要約行にも同じ文字列を出すので重複は除く)を -nn -A -r と BPF で取り出し request-line.txt に。\n"
    "(3) PORT への新規接続数(SYN だけ、SYN-ACK は除く。BPF の tcp[tcpflags] を使う)を数字だけで new-conns.txt に。\n"
    "(4) 先頭3パケットを -nn -c 3 -r で first3.txt に保存。判定は実 tcpdump で web.pcap を読み戻して内容を比較する。",
    tcpdump_setup, tcpdump_check,
    '''. ./params.env
tcpdump -nn -r traffic.pcap -w web.pcap "tcp port $PORT"
tcpdump -nn -A -r traffic.pcap "src host $CLIENT and dst port $PORT" | grep -a -o 'GET [^ ]* HTTP/1.1' | sort -u > request-line.txt
tcpdump -nn -r traffic.pcap "tcp dst port $PORT and tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn" | wc -l > new-conns.txt
tcpdump -nn -c 3 -r traffic.pcap > first3.txt''',
    ['. ./params.env\ncp traffic.pcap web.pcap\ntcpdump -nn -A -r traffic.pcap "dst port $PORT" | grep -a -o "GET [^ ]* HTTP/1.1" | head -1 > request-line.txt\ntcpdump -nn -r traffic.pcap "dst port $PORT" | wc -l > new-conns.txt\ntcpdump -c 3 -r traffic.pcap > first3.txt',
     '. ./params.env\ntcpdump -nn -r traffic.pcap -w web.pcap "tcp port $PORT"\ntcpdump -nn -A -r traffic.pcap "dst port $PORT" | grep -a -o "GET [^ ]* HTTP/1.1" | tail -1 > request-line.txt\ntcpdump -nn -r traffic.pcap "tcp port $PORT" | wc -l > new-conns.txt\ntcpdump -nn -c 3 -r traffic.pcap > first3.txt'])


# ---------------------------------------------------------------------------
# debbuild: 実 .deb を dpkg-deb --build で作り、非特権の私的 dpkg ルート
# (--root + --force-not-root + --force-script-chrootless)で導入・更新・削除・purge の
# conffile 挙動を実際に確かめる。ホストの dpkg 状態には触れない。
# ---------------------------------------------------------------------------
DEB_BIN = "#!/bin/sh\n. /etc/dojo-hello.conf 2>/dev/null || true\necho \"${greeting:-hello} (%s)\"\n"
DEB_ADMIN_MARK = "# admin-local-edit"


def deb_setup(root):
    for number, version in ((1, "1.0"), (2, "1.1")):
        put(root, f"payload-v{number}/usr/bin/dojo-hello", DEB_BIN % version, 0o755)
        put(root, f"payload-v{number}/etc/dojo-hello.conf", f"greeting=hello-{secrets.token_hex(3)}\n")
    remember(root, {}, [f"payload-v{n}/{p}" for n in (1, 2) for p in ("usr/bin/dojo-hello", "etc/dojo-hello.conf")])


def deb_env():
    return {"PATH": os.environ["PATH"] + ":/usr/sbin:/sbin", "LC_ALL": "C", "LANG": "C"}


def deb_cmd(*argv, check=True):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=deb_env())
    if check:
        require(result.returncode == 0, " ".join(argv[:3]) + " が失敗: " + (result.stderr or result.stdout)[-300:])
    return result


def deb_dpkg(base, *args, check=True):
    return deb_cmd("dpkg", "--root=" + str(base / "root"), "--log=" + str(base / "dpkg.log"),
                   "--force-not-root", "--force-bad-path", "--force-depends",
                   "--force-script-chrootless", *args, check=check)


def deb_status(base):
    result = deb_cmd("dpkg-query", "--admindir=" + str(base / "root/var/lib/dpkg"),
                     "-W", "-f=${Status}|${Version}", "dojo-hello", check=False)
    return result.stdout.strip() if result.returncode == 0 else "absent"


def deb_inspect(root, deb, number, version):
    require((root / deb).is_file(), deb + " がありません(dpkg-deb --build)。")
    fields = {name: deb_cmd("dpkg-deb", "-f", str(root / deb), name, check=False).stdout.strip()
              for name in ("Package", "Version", "Architecture", "Maintainer", "Description")}
    require(fields["Package"] == "dojo-hello" and fields["Version"] == version and fields["Architecture"] == "all",
            f"{deb}: Package: dojo-hello / Version: {version} / Architecture: all にします。")
    require(re.fullmatch(r".+ <[^<>@\s]+@[^<>\s]+>", fields["Maintainer"]), deb + ": Maintainer は 名前 <メール> 形式。")
    require(fields["Description"], deb + ": Description が必要です。")
    listing = deb_cmd("dpkg-deb", "-c", str(root / deb)).stdout
    for line in listing.splitlines():
        require(" root/root " in line, deb + ": 所有者が root/root ではありません(--root-owner-group)。")
    with tempfile.TemporaryDirectory(prefix="dojo-deb-") as scratch:
        tree, control = Path(scratch) / "tree", Path(scratch) / "control"
        deb_cmd("dpkg-deb", "-x", str(root / deb), str(tree))
        deb_cmd("dpkg-deb", "-e", str(root / deb), str(control))
        for name in ("usr/bin/dojo-hello", "etc/dojo-hello.conf"):
            src = root / f"payload-v{number}" / name
            require((tree / name).is_file() and (tree / name).read_bytes() == src.read_bytes(),
                    f"{deb}: {name} の内容が payload-v{number} と違います。")
        require(os.access(tree / "usr/bin/dojo-hello", os.X_OK), deb + ": 実行ファイルの権限が失われています。")
        require((control / "conffiles").is_file() and
                (control / "conffiles").read_text().split() == ["/etc/dojo-hello.conf"],
                deb + ": DEBIAN/conffiles に /etc/dojo-hello.conf だけを書きます。")
        require(os.access(control / "postinst", os.X_OK), deb + ": postinst が実行可能ではありません。")


def deb_lifecycle(root, v1, v2, number_conf):
    conf1, conf2 = number_conf
    with tempfile.TemporaryDirectory(prefix="dojo-deb-root-") as scratch:
        base = Path(scratch)
        admin = base / "root/var/lib/dpkg"
        admin.mkdir(parents=True)
        (admin / "status").touch()
        marker = base / "root/var/lib/dojo-hello/configured"
        conf = base / "root/etc/dojo-hello.conf"
        # 無改変の conffile は更新で新しい既定値に置き換わる。
        deb_dpkg(base, "--install", str(root / v1))
        require(deb_status(base) == "install ok installed|1.0-1", "1.0-1 が導入状態になりません。")
        require(conf.read_text() == conf1 and marker.read_text().startswith("configure"),
                "導入後の conffile または postinst の結果(${DPKG_ROOT} 配下の configured)が違います。")
        deb_dpkg(base, "--install", str(root / v2))
        require(conf.read_text() == conf2, "無改変の conffile は更新で新しい内容になるはずです。")
        # 管理者が編集した conffile は --force-confold で保たれ、新既定は .dpkg-dist へ。
        deb_dpkg(base, "--purge", "dojo-hello")
        require(deb_status(base) == "absent" or "not-installed" in deb_status(base), "purge できません。")
        require(not conf.exists(), "purge 後に conffile が残っています。")
        deb_dpkg(base, "--install", str(root / v1))
        conf.write_text(conf1 + DEB_ADMIN_MARK + "\n")
        deb_dpkg(base, "--force-confold", "--install", str(root / v2))
        require(conf.read_text() == conf1 + DEB_ADMIN_MARK + "\n", "管理者の編集が更新で失われています(conffiles の宣言を確認)。")
        require((base / "root/etc/dojo-hello.conf.dpkg-dist").read_text() == conf2, "新しい既定値が .dpkg-dist に残るはずです。")
        # remove は conffile を残し、purge で消える。
        deb_dpkg(base, "--remove", "dojo-hello")
        require(deb_status(base).startswith("deinstall ok config-files"), "remove 後は config-files 状態のはずです。")
        require(conf.exists() and not (base / "root/usr/bin/dojo-hello").exists(),
                "remove は実行ファイルを消し、conffile は残します。")
        deb_dpkg(base, "--purge", "dojo-hello")
        require(not conf.exists(), "purge は conffile も消します。")


def deb_check(root):
    fixture(root)
    deb_inspect(root, "dojo-hello_1.0-1_all.deb", 1, "1.0-1")
    deb_inspect(root, "dojo-hello_1.1-1_all.deb", 2, "1.1-1")
    for name, flag in (("info.txt", "-I"), ("contents.txt", "-c")):
        deb = str(root / "dojo-hello_1.0-1_all.deb")
        accepted = {deb_cmd("dpkg-deb", flag, deb).stdout,
                    subprocess.run(["dpkg-deb", flag, deb], capture_output=True, text=True).stdout}
        require(read(root, name) in accepted, f"{name} は dpkg-deb {flag} dojo-hello_1.0-1_all.deb の出力にします。")
    confs = ((root / "payload-v1/etc/dojo-hello.conf").read_text(), (root / "payload-v2/etc/dojo-hello.conf").read_text())
    deb_lifecycle(root, "dojo-hello_1.0-1_all.deb", "dojo-hello_1.1-1_all.deb", confs)
    # 利用者自身の私的ルート sysroot/: 1.0 導入 -> 管理者編集 -> --force-confold で 1.1 へ更新した結末。
    admindir = root / "sysroot/var/lib/dpkg"
    status = deb_cmd("dpkg-query", "--admindir=" + str(admindir), "-W", "-f=${Status}|${Version}", "dojo-hello", check=False)
    require(status.stdout.strip() == "install ok installed|1.1-1", "sysroot に 1.1-1 が導入された状態にします(--root=./sysroot)。")
    conf = root / "sysroot/etc/dojo-hello.conf"
    require(conf.is_file() and DEB_ADMIN_MARK in conf.read_text() and conf.read_text().startswith(confs[0]),
            f"sysroot の conffile に管理者の編集行 {DEB_ADMIN_MARK!r} が残っていません。")
    require((root / "sysroot/etc/dojo-hello.conf.dpkg-dist").read_text() == confs[1],
            "更新で届いた新既定値が .dpkg-dist にありません(--force-confold)。")
    require((root / "sysroot/var/lib/dojo-hello/configured").is_file(), "postinst の実行結果が sysroot にありません。")


DEB_SOLUTION = '''mkpkg() { # dir version
  mkdir -p "$1/DEBIAN"
  cat > "$1/DEBIAN/control" <<EOF
Package: dojo-hello
Version: $2
Section: misc
Priority: optional
Architecture: all
Maintainer: Dojo Learner <learner@example.invalid>
Description: LinuxDOJO practice package
 Built by hand with dpkg-deb.
EOF
  echo /etc/dojo-hello.conf > "$1/DEBIAN/conffiles"
  cat > "$1/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  mkdir -p "${DPKG_ROOT:-}/var/lib/dojo-hello"
  echo "configure $2" > "${DPKG_ROOT:-}/var/lib/dojo-hello/configured"
fi
exit 0
EOF
  chmod 755 "$1/DEBIAN/postinst"
}
cp -a payload-v1 pkg1; mkpkg pkg1 1.0-1
cp -a payload-v2 pkg2; mkpkg pkg2 1.1-1
dpkg-deb --build --root-owner-group pkg1 dojo-hello_1.0-1_all.deb
dpkg-deb --build --root-owner-group pkg2 dojo-hello_1.1-1_all.deb
dpkg-deb -I dojo-hello_1.0-1_all.deb > info.txt
dpkg-deb -c dojo-hello_1.0-1_all.deb > contents.txt
mkdir -p sysroot/var/lib/dpkg; touch sysroot/var/lib/dpkg/status
d() { dpkg --root="$PWD/sysroot" --log="$PWD/dpkg.log" --force-not-root --force-bad-path --force-depends --force-script-chrootless "$@"; }
d -i dojo-hello_1.0-1_all.deb
echo '# admin-local-edit' >> sysroot/etc/dojo-hello.conf
d --force-confold -i dojo-hello_1.1-1_all.deb'''

add("debbuild", "debパッケージを自作し、私的ルートで更新・削除・purge を確かめる",
    "bash dpkg dpkg-deb dpkg-query", "bash dpkg",
    "payload-v1 / payload-v2 は配布物の中身(usr/bin/dojo-hello と設定 etc/dojo-hello.conf)。各コピーに DEBIAN/ を足して\n"
    "dojo-hello_1.0-1_all.deb と dojo-hello_1.1-1_all.deb を dpkg-deb --build --root-owner-group で作る。\n"
    "DEBIAN/control(Package/Version/Architecture: all/Maintainer 名前 <メール>/Description)、DEBIAN/conffiles(/etc/dojo-hello.conf)、\n"
    "実行可能な DEBIAN/postinst(configure 時に ${DPKG_ROOT:-}/var/lib/dojo-hello/configured へ記録)を用意。\n"
    "dpkg-deb -I の出力を info.txt、dpkg-deb -c を contents.txt(いずれも 1.0-1)へ。\n"
    "さらに私的ルート ./sysroot(var/lib/dpkg/status は空ファイル)へ dpkg --root=./sysroot --force-not-root --force-bad-path --force-depends --force-script-chrootless で\n"
    "1.0-1 を導入し、/etc/dojo-hello.conf の末尾に『# admin-local-edit』を追記してから --force-confold で 1.1-1 へ更新(編集が残り、新既定値は .dpkg-dist)。\n"
    "判定は作った .deb を別の使い捨てルートで実際に導入・更新・remove・purge して conffile の挙動を確認する。ホストの dpkg は変更しない。",
    deb_setup, deb_check, DEB_SOLUTION,
    ['cp -a payload-v1 pkg1; cp -a payload-v2 pkg2\n'
     'for p in pkg1:1.0-1 pkg2:1.1-1; do d=${p%%:*}; v=${p##*:}; mkdir -p $d/DEBIAN; '
     'printf "Package: dojo-hello\\nVersion: %s\\nArchitecture: all\\nMaintainer: A <a@b.example>\\nDescription: x\\n" $v > $d/DEBIAN/control; '
     'printf "#!/bin/sh\\nexit 0\\n" > $d/DEBIAN/postinst; chmod 755 $d/DEBIAN/postinst; '
     'dpkg-deb --build $d dojo-hello_${v}_all.deb; done\n'
     'dpkg-deb -I dojo-hello_1.0-1_all.deb > info.txt; dpkg-deb -c dojo-hello_1.0-1_all.deb > contents.txt',
     DEB_SOLUTION.replace('  echo /etc/dojo-hello.conf > "$1/DEBIAN/conffiles"\n', '')])


# 追加のネイティブ実習(別ファイルに分けて登録する)
import curriculum.toolbox_labs2  # noqa: E402,F401
import curriculum.toolbox_labs3  # noqa: E402,F401
import curriculum.toolbox_labs4  # noqa: E402,F401
import curriculum.toolbox_labs5  # noqa: E402,F401
