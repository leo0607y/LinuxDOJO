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
import subprocess
import tarfile

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
