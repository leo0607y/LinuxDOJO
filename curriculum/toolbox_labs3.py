"""追加のネイティブ実習(第3群): restic / ローカルCA / ansible / kubectl(オフライン)。

実ツールだけで判定する。未導入なら tools 宣言により実習は skip され、模擬は使わない。
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import tempfile
import time

from curriculum.toolbox_labs import add, put, read, require, run, remember, fixture  # noqa: F401


def _proc(root, command, env=None, timeout=60, ok=True):
    """検証用の実行。ok=True なら失敗を ValueError にする。"""
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=timeout,
                            stdin=subprocess.DEVNULL, env=dict(os.environ, **(env or {})))
    if ok and result.returncode:
        raise ValueError("実行失敗: " + " ".join(map(str, command)) + "\n" + (result.stderr or result.stdout)[-600:])
    return result


def _tree(path):
    path = Path(path)
    require(path.is_dir(), str(path.name) + " がありません。")
    out = {}
    for p in sorted(path.rglob("*")):
        if p.is_symlink():
            raise ValueError("シンボリックリンクは対象外です。")
        if p.is_file():
            out[str(p.relative_to(path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------- backup (restic)

def _bk_files(tok, n):
    notes = tok["note"] + "\n"
    files = {"notes.txt": notes, "old.txt": tok["old"] + "\n", "base-only.bin": tok["big"],
             "keep.txt": tok["keep"] + "\n"}
    if n >= 1:
        files["notes.txt"] += "update1 " + tok["u1"] + "\n"
        del files["old.txt"], files["base-only.bin"]
        files["new1.txt"] = tok["n1"] + "\n"
    if n >= 2:
        files["notes.txt"] += "update2 " + tok["u2"] + "\n"
        del files["new1.txt"]
        files["new2.txt"] = tok["n2"] + "\n"
    return files


def _bk_hashes(tok, n):
    return {k: _sha(v) for k, v in _bk_files(tok, n).items()}


def _restored(base, data):
    """restic の版により復元先の階層が違う(絶対パス全体 / 末尾のdataだけ)。両方を許す。"""
    full = Path(base) / str(data).lstrip("/")
    return full if full.is_dir() else Path(base) / data.name


def backup_setup(root):
    tok = {k: secrets.token_hex(6) for k in ("note", "old", "keep", "u1", "u2", "n1", "n2")}
    tok["big"] = secrets.token_hex(60000)
    for name, text in _bk_files(tok, 0).items():
        put(root, "data/" + name, text)
    put(root, "password.txt", secrets.token_hex(8) + "\n", 0o600)
    put(root, "update.sh", f'''set -eu
cd "$(dirname "$0")/data"
case "${{1:-}}" in
1) printf 'update1 %s\\n' {tok["u1"]} >> notes.txt; rm old.txt base-only.bin
   printf '%s\\n' {tok["n1"]} > new1.txt ;;
2) printf 'update2 %s\\n' {tok["u2"]} >> notes.txt; rm new1.txt
   printf '%s\\n' {tok["n2"]} > new2.txt ;;
*) echo "usage: bash update.sh 1|2" >&2; exit 2 ;;
esac
''')
    remember(root, {"tok": tok}, ["password.txt", "update.sh"])


def _rs(root, *args, repo="repo", ok=True):
    env = {"RESTIC_PASSWORD_FILE": str(root / "password.txt"), "RESTIC_REPOSITORY": str(root / repo)}
    return _proc(root, ["restic", "--no-cache", *args], env=env, ok=ok, timeout=90)


def backup_check(root):
    tok = fixture(root)["tok"]
    require((root / "repo/config").is_file(), "repo に restic リポジトリがありません。")
    _rs(root, "check", "--read-data")
    snaps = sorted(json.loads(_rs(root, "snapshots", "--json").stdout), key=lambda s: s["time"])
    require(len(snaps) == 2, "forget --keep-last 2 --prune 後はスナップショットがちょうど2つ残ります。")
    require([s.get("tags") for s in snaps] == [["v1"], ["v2"]], "残るのはタグ v1 と v2 の2つです。")
    data = (root / "data").resolve()
    for s, n in zip(snaps, (1, 2)):
        require([str(Path(p).resolve()) for p in s["paths"]] == [str(data)], "data ディレクトリをバックアップします。")
        with tempfile.TemporaryDirectory(prefix="dojo-bk-") as tmp:
            _rs(root, "restore", s["id"], "--target", tmp)
            require(_tree(_restored(tmp, data)) == _bk_hashes(tok, n),
                    f"スナップショット v{n} の内容が想定の状態と違います。")
    require(_tree(data) == _bk_hashes(tok, 2), "data は update.sh 1,2 を適用した最終状態のはずです。")
    pruned = _rs(root, "prune", "--dry-run").stdout
    require(re.search(r"to delete:\s+0 blobs", pruned) and re.search(r"this removes:\s+0 blobs", pruned),
            "forget の後に --prune で不要データを物理削除していません。")
    require(_tree(_restored(root / "restore-full", data)) == _bk_hashes(tok, 2),
            "restore-full に最新スナップショットを全体復元します。")
    one = _tree(root / "restore-one")
    require(len(one) == 1 and list(one)[0].endswith("/notes.txt") and list(one.values()) == [_bk_hashes(tok, 2)["notes.txt"]],
            "restore-one には notes.txt だけを復元します。")
    diff = read(root, "diff.txt")
    require(re.search(r"^\+\s+\S*/new2\.txt$", diff, re.M) and re.search(r"^-\s+\S*/new1\.txt$", diff, re.M)
            and re.search(r"^M\s+\S*/notes\.txt$", diff, re.M) and "keep.txt" not in diff,
            "diff.txt は restic diff v1 v2 の出力で、追加・削除・変更を含みます。")
    require((root / "repo-broken/config").is_file(), "repo-broken は repo の複製です。")
    _rs(root, "snapshots", repo="repo-broken")
    require(_rs(root, "check", "--read-data", repo="repo-broken", ok=False).returncode != 0,
            "repo-broken を壊して check --read-data が失敗する状態にします。")
    require(_tree(root / "repo-broken") != _tree(root / "repo"), "repo-broken が repo と同一です。")
    code = read(root, "broken-check.exit").strip()
    require(code.isdigit() and int(code) != 0, "壊れたリポジトリの check 終了コード(非0)を broken-check.exit に保存します。")


add("backup", "restic: 世代バックアップ・保持ポリシー・復元・破損検知", "bash restic python3", "bash restic python3",
    "password.txt をパスワードに ./repo へ restic リポジトリを作る(RESTIC_PASSWORD_FILE/RESTIC_REPOSITORY)。\n"
    "data を backup(タグ base)→ bash update.sh 1 → backup(タグ v1)→ bash update.sh 2 → backup(タグ v2)。\n"
    "restic forget --keep-last 2 --prune で古い世代を消し、v1 と v2 だけ残す。\n"
    "最新を restore-full へ全体復元、notes.txt だけを restore-one へ復元(--include '*/notes.txt')。\n"
    "restic diff v1 v2 を diff.txt へ。repo を repo-broken へコピー(chmod -R u+w)して\n"
    "パックファイルを1つ壊し、restic check --read-data の終了コードを broken-check.exit へ。\n"
    "restic は実ツールで判定。クラウド保存先は使わずローカルディレクトリだけ。",
    backup_setup, backup_check,
    '''export RESTIC_PASSWORD_FILE=password.txt RESTIC_REPOSITORY=repo
restic init -q
restic backup -q --tag base data
bash update.sh 1
restic backup -q --tag v1 data
bash update.sh 2
restic backup -q --tag v2 data
restic forget --keep-last 2 --prune -q
restic restore -q latest --target restore-full
restic restore -q latest --target restore-one --include '*/notes.txt'
id() { restic snapshots --tag "$1" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["short_id"])'; }
restic diff "$(id v1)" "$(id v2)" > diff.txt
cp -r repo repo-broken
chmod -R u+w repo-broken
pack=$(find repo-broken/data -type f | head -n 1)
printf 'corruption' >> "$pack"
set +e
restic -r repo-broken check --read-data > /dev/null 2>&1
echo $? > broken-check.exit
set -e''',
    ['''export RESTIC_PASSWORD_FILE=password.txt RESTIC_REPOSITORY=repo
restic init -q
restic backup -q --tag base data
restic backup -q --tag v1 data
restic forget --keep-last 2 -q
echo 1 > broken-check.exit''',
     '''export RESTIC_PASSWORD_FILE=password.txt RESTIC_REPOSITORY=repo
restic init -q
restic backup -q --tag base data
bash update.sh 1
restic backup -q --tag v1 data
bash update.sh 2
restic backup -q --tag v2 data
restic forget --keep-last 2 -q
restic restore -q latest --target restore-full
restic diff "$(restic snapshots --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["short_id"])')" latest > diff.txt
cp -r repo repo-broken; echo 1 > broken-check.exit'''])


# ---------------------------------------------------------------- localca (openssl)

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


CA_CNF = '''[ca]
default_ca = CA_default
[CA_default]
dir = .
database = $dir/index.txt
new_certs_dir = $dir/newcerts
serial = $dir/serial
crlnumber = $dir/crlnumber
certificate = $dir/ca.crt
private_key = $dir/ca.key
default_md = sha256
default_days = 30
default_crl_days = 7
unique_subject = no
policy = policy_any
[policy_any]
commonName = supplied
[req]
distinguished_name = dn
[dn]
[ca_ext]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
[client_ext]
basicConstraints = CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = clientAuth
'''


def localca_setup(root):
    name = "svc-" + secrets.token_hex(3) + ".corp.test"
    put(root, "hostname.txt", name + "\n")
    put(root, "ca.cnf", CA_CNF)
    put(root, "port.txt", str(_free_port()) + "\n")
    remember(root, {"name": name}, ["hostname.txt", "ca.cnf"])


def _ossl(root, *args, ok=True, input=None):
    result = subprocess.run(["openssl", *args], cwd=root, text=True, capture_output=True,
                            timeout=20, input=input if input is not None else "")
    if ok and result.returncode:
        raise ValueError("openssl " + " ".join(args[:3]) + " が失敗: " + (result.stderr or result.stdout)[-300:])
    return result


def _pub(root, cert=None, key=None):
    if cert:
        return _ossl(root, "x509", "-in", cert, "-pubkey", "-noout").stdout
    return _ossl(root, "pkey", "-in", key, "-pubout").stdout


def _tls_handshake(root, name, host, cert, key, extra_client=(), extra_server=(), expect_ok=True):
    port = _free_port()
    server = subprocess.Popen(["openssl", "s_server", "-accept", str(port), "-cert", cert, "-key", key,
                               "-naccept", "1", "-quiet", *extra_server], cwd=root,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        # 上の接続確認が naccept を消費するため、確認用接続の後にもう一度待ち受けさせる。
    finally:
        server.kill()
        server.wait()
    server = subprocess.Popen(["openssl", "s_server", "-accept", str(port), "-cert", cert, "-key", key,
                               "-naccept", "1", "-quiet", *extra_server], cwd=root,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.6)
        result = _ossl(root, "s_client", "-connect", f"127.0.0.1:{port}", "-servername", name,
                       "-CAfile", "ca.crt", "-verify_return_error", "-verify_hostname", host,
                       *extra_client, ok=False, input="Q\n")
    finally:
        server.kill()
        server.wait()
    good = result.returncode == 0 and "Verify return code: 0 (ok)" in result.stdout
    require(good == expect_ok, "TLS接続の結果が想定と違います(" + host + ")。\n" + result.stderr[-300:])


def localca_check(root):
    name = fixture(root)["name"]
    for key in ("ca.key", "server.key", "client.key"):
        require((root / key).is_file() and stat.S_IMODE((root / key).stat().st_mode) == 0o600,
                key + " の権限を600にします。")
    ca = _ossl(root, "x509", "-in", "ca.crt", "-noout", "-subject", "-issuer", "-ext", "basicConstraints,keyUsage").stdout
    require("CA:TRUE" in ca and "Certificate Sign" in ca and "CRL Sign" in ca, "CA証明書は CA:TRUE と keyCertSign/cRLSign が必要です。")
    require(_pub(root, "ca.crt") == _pub(root, key="ca.key"), "ca.crt と ca.key が対応しません。")
    base = ("verify", "-CAfile", "ca.crt")
    # サーバ証明書: SAN・チェーン・名前・用途
    san = _ossl(root, "x509", "-in", "server.crt", "-noout", "-ext", "subjectAltName", ok=False).stdout
    require("DNS:" + name in san, "server.crt に SAN(DNS:" + name + ") が必要です。SAN 無しは現代のクライアントに拒否されます。")
    require(_pub(root, "server.crt") == _pub(root, key="server.key"), "server.crt と server.key が対応しません。")
    require(_pub(root, "client.crt") == _pub(root, key="client.key"), "client.crt と client.key が対応しません。")
    _ossl(root, *base, "-purpose", "sslserver", "-verify_hostname", name, "server.crt")
    require(_ossl(root, *base, "-purpose", "sslserver", "-verify_hostname", "other.corp.test", "server.crt", ok=False).returncode != 0,
            "別ホスト名では検証が失敗しなければなりません。")
    require(_ossl(root, *base, "-purpose", "sslclient", "server.crt", ok=False).returncode != 0,
            "server.crt はクライアント認証に使えない(EKU=serverAuth)必要があります。")
    _ossl(root, *base, "-purpose", "sslclient", "client.crt")
    require(_ossl(root, *base, "-purpose", "sslserver", "client.crt", ok=False).returncode != 0,
            "client.crt はサーバ用途に使えない(EKU=clientAuth)必要があります。")
    # 失効
    crl = ("-crl_check", "-CRLfile", "ca.crl")
    _ossl(root, "crl", "-in", "ca.crl", "-CAfile", "ca.crt", "-noout", "-verify")
    _ossl(root, *base, "-purpose", "sslclient", "revoked.crt")
    revoked = _ossl(root, *base, *crl, "-purpose", "sslclient", "revoked.crt", ok=False)
    require(revoked.returncode != 0 and "revoked" in revoked.stdout + revoked.stderr,
            "revoked.crt は CRL で失効と判定されなければなりません。")
    _ossl(root, *base, *crl, "-purpose", "sslclient", "client.crt")
    _ossl(root, *base, *crl, "-purpose", "sslserver", "server.crt")
    serial = _ossl(root, "x509", "-in", "revoked.crt", "-noout", "-serial").stdout.strip().split("=")[1]
    other = _ossl(root, "x509", "-in", "client.crt", "-noout", "-serial").stdout.strip().split("=")[1]
    listing = _ossl(root, "crl", "-in", "ca.crl", "-noout", "-text").stdout
    require(serial in listing and other not in listing, "CRL には失効させた証明書だけを載せます。")
    # 期限切れ
    expired = _ossl(root, *base, "-purpose", "sslserver", "expired.crt", ok=False)
    require(expired.returncode != 0 and "expired" in expired.stdout + expired.stderr,
            "expired.crt は期限切れで拒否されなければなりません。")
    _ossl(root, *base, "-no_check_time", "-purpose", "sslserver", "expired.crt")
    # 実際のTLS接続
    _tls_handshake(root, name, name, "server.crt", "server.key")
    _tls_handshake(root, name, "other.corp.test", "server.crt", "server.key", expect_ok=False)
    _tls_handshake(root, name, name, "server.crt", "server.key", extra_server=("-Verify", "1", "-CAfile", "ca.crt"),
                   extra_client=("-cert", "client.crt", "-key", "client.key"))
    require("Verify return code: 0 (ok)" in read(root, "handshake.txt"),
            "handshake.txt は s_client -verify_return_error の成功出力です。")


add("localca", "openssl: 私設CAでサーバ/クライアント証明書・失効・期限を扱う", "bash openssl", "bash openssl",
    "ca.cnf(原本)を使い、ネットワーク無しで私設CAを構築する。newcerts/index.txt/serial/crlnumber を用意。\n"
    "ca.key(600)と ca.crt(CA:TRUE, keyCertSign, cRLSign)。server.key/client.key も600。\n"
    "hostname.txt の名前を SAN に持つ server.crt を CSR から発行(自分で書いた拡張ファイル server.ext に SAN と EKU=serverAuth を入れ -extfile)。\n"
    "client.crt(client_ext)、失効させる revoked.crt、期限切れの expired.crt(-startdate/-enddate が過去)も発行。\n"
    "openssl ca -revoke と -gencrl で ca.crl を作る。verify の -crl_check で revoked だけが失敗すること、\n"
    "s_server(port.txt のポート)と s_client -verify_return_error -verify_hostname の成功出力を handshake.txt へ。",
    localca_setup, localca_check,
    '''umask 077
mkdir newcerts; : > index.txt; echo 1000 > serial; echo 1000 > crlnumber
name=$(cat hostname.txt)
printf 'basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s\n' "$name" > server.ext
for n in ca server client revoked expired; do
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out $n.key
done
openssl req -x509 -new -key ca.key -config ca.cnf -extensions ca_ext -days 30 -subj "/CN=Dojo Local CA" -out ca.crt
openssl req -new -key server.key -subj "/CN=$name" -out server.csr
openssl req -new -key client.key -subj "/CN=alice" -out client.csr
openssl req -new -key revoked.key -subj "/CN=mallory" -out revoked.csr
openssl req -new -key expired.key -subj "/CN=$name" -out expired.csr
openssl ca -batch -notext -config ca.cnf -extfile server.ext -in server.csr -out server.crt
openssl ca -batch -notext -config ca.cnf -extensions client_ext -in client.csr -out client.crt
openssl ca -batch -notext -config ca.cnf -extensions client_ext -in revoked.csr -out revoked.crt
openssl ca -batch -notext -config ca.cnf -extfile server.ext -startdate 20200101000000Z -enddate 20200102000000Z -in expired.csr -out expired.crt
openssl ca -batch -config ca.cnf -revoke revoked.crt
openssl ca -batch -config ca.cnf -gencrl -out ca.crl
openssl verify -CAfile ca.crt -crl_check -CRLfile ca.crl -purpose sslclient revoked.crt && exit 1 || true
port=$(cat port.txt)
openssl s_server -accept "$port" -cert server.crt -key server.key -naccept 1 -quiet > /dev/null 2>&1 &
sleep 1
echo Q | openssl s_client -connect "127.0.0.1:$port" -servername "$name" -CAfile ca.crt -verify_return_error -verify_hostname "$name" > handshake.txt 2>&1
wait''',
    ['''umask 077
name=$(cat hostname.txt)
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -keyout server.key -out server.crt -subj "/CN=$name" -addext "subjectAltName=DNS:$name"
cp server.key ca.key; cp server.crt ca.crt; echo ok > handshake.txt''',
     '''umask 077
name=$(cat hostname.txt)
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out ca.key
openssl req -x509 -new -key ca.key -subj "/CN=Dojo Local CA" -days 30 -out ca.crt
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out server.key
openssl req -new -key server.key -subj "/CN=$name" -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 30 -out server.crt'''])


# ---------------------------------------------------------------- ansible (connection=local)

def _an_tokens():
    return {"app": "app" + secrets.token_hex(2), "port": 20000 + secrets.randbelow(20000),
            "motd": "welcome-" + secrets.token_hex(3),
            "sites": ["s" + secrets.token_hex(2) for _ in range(3)]}


def _an_files(root, tok):
    put(root, "ansible.cfg", "[defaults]\ninventory = inventory.ini\nretry_files_enabled = False\n"
                             "host_key_checking = False\ninterpreter_python = auto_silent\nnocolor = True\n")
    put(root, "inventory.ini", "[local]\nlocalhost ansible_connection=local ansible_python_interpreter="
                               + (shutil.which("python3") or "/usr/bin/python3") + "\n")
    put(root, "vars.yml", json.dumps({"app_name": tok["app"], "app_port": tok["port"], "motd": tok["motd"],
                                      "sites": tok["sites"]}, indent=1) + "\n")
    put(root, "app.conf.j2", "# managed by ansible\nname={{ app_name }}\nlisten={{ app_port }}\n"
                             "sites={{ sites | join(',') }}\n")
    put(root, "target/settings.ini", "debug=true\nlog=info\n")


def ansible_setup(root):
    tok = _an_tokens()
    _an_files(root, tok)
    put(root, "site.yml", "---\n- hosts: all\n  gather_facts: false\n  vars_files: [vars.yml]\n"
                          "  vars:\n    target: \"{{ playbook_dir }}/target\"\n  tasks: []\n  # TODO: file / template / copy / lineinfile / loop / handlers\n")
    remember(root, {"tok": tok}, ["ansible.cfg", "inventory.ini", "vars.yml", "app.conf.j2"])


def _an_play(root, *flags):
    env = {"ANSIBLE_CONFIG": str(root / "ansible.cfg"), "ANSIBLE_NOCOLOR": "1", "ANSIBLE_FORCE_COLOR": "0",
           "ANSIBLE_LOCALHOST_WARNING": "False"}
    result = _proc(root, ["ansible-playbook", "site.yml", *flags], env=env, timeout=120, ok=False)
    require(result.returncode == 0, "ansible-playbook が失敗しました。\n" + (result.stdout + result.stderr)[-700:])
    return result.stdout


def _recap(output):
    m = re.search(r"ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)", output)
    require(m, "PLAY RECAP がありません。")
    return dict(zip(("ok", "changed", "unreachable", "failed"), map(int, m.groups())))


def _an_expect(root, tok):
    t = root / "target"
    require(stat.S_IMODE((t / "conf.d").stat().st_mode) == 0o750, "conf.d はモード 0750 のディレクトリです。")
    require(read(t, "app.conf") == f"# managed by ansible\nname={tok['app']}\nlisten={tok['port']}\nsites={','.join(tok['sites'])}\n",
            "app.conf は app.conf.j2 を変数で展開した内容です。")
    require(read(t, "motd") == tok["motd"] + "\n", "motd は変数 motd の内容です。")
    require(read(t, "settings.ini") == f"debug=false\nlog=info\nport={tok['port']}\n",
            "settings.ini は debug を置換し、port を追記し、他の行は保持します。")
    require(sorted(p.name for p in (t / "conf.d").iterdir()) == sorted(s + ".conf" for s in tok["sites"]),
            "conf.d には sites の各要素ごとのファイルだけを作ります。")
    for s in tok["sites"]:
        f = t / "conf.d" / (s + ".conf")
        require(f.read_text() == f"site={s}\n" and stat.S_IMODE(f.stat().st_mode) == 0o640,
                s + ".conf の内容かモード(0640)が違います。")


def _handler_count(root):
    path = root / "target/handler.log"
    return path.read_text().count("reload\n") if path.is_file() else 0


def ansible_check(root):
    tok = fixture(root)["tok"]
    site = read(root, "site.yml")
    # 利用者の作業領域の成果物
    _an_expect(root, tok)
    require(_handler_count(root) == 1, "handler は変更があった初回だけ1回走ります(handler.log の reload が1行)。")
    check = read(root, "check.txt")
    require("PLAY RECAP" in check and _recap(check)["changed"] > 0 and ("+++ after" in check or "--- before" in check),
            "check.txt は --check --diff の出力(差分つき・変更あり)です。")
    second = _recap(read(root, "second.txt"))
    require(second["changed"] == 0 and second["failed"] == 0, "second.txt: 2回目は changed=0 でなければ冪等ではありません。")
    # 新しい乱数の環境で、利用者の site.yml だけを持ち込んで実行して判定する
    with tempfile.TemporaryDirectory(prefix="dojo-ansible-") as tmp:
        fresh = Path(tmp)
        tok2 = _an_tokens()
        _an_files(fresh, tok2)
        put(fresh, "site.yml", site)
        before = _tree(fresh / "target")
        out = _an_play(fresh, "--check", "--diff")
        require(_recap(out)["changed"] > 0, "--check で変更予定が出ません。")
        require(_tree(fresh / "target") == before, "--check が実際にファイルを変更しています(check_mode 違反)。")
        first = _an_play(fresh)
        require(_recap(first)["changed"] > 0, "初回適用で変更が出ません。")
        _an_expect(fresh, tok2)
        require(_handler_count(fresh) == 1, "handler は初回に1回だけ走ります。")
        again = _recap(_an_play(fresh))
        require(again["changed"] == 0 and _handler_count(fresh) == 1, "新環境の2回目で changed=0 かつ handler 不発になりません。")
        tok2["port"] += 1
        put(fresh, "vars.yml", json.dumps({"app_name": tok2["app"], "app_port": tok2["port"], "motd": tok2["motd"],
                                          "sites": tok2["sites"]}, indent=1) + "\n")
        _an_play(fresh)
        _an_expect(fresh, tok2)
        require(_handler_count(fresh) == 2, "テンプレートが変わった時だけ handler が再び走ります。")


add("ansible", "ansible-core: ローカル接続のPlaybookを --check --diff で確認して冪等に適用", "bash ansible-playbook", "bash ansible",
    "ansible-core。接続は local のみで外部ホストは使わない(inventory.ini/ansible.cfg は原本)。\n"
    "site.yml の tasks を完成させる。作業先は {{ target }}(= ./target)。変数は vars.yml。\n"
    "1) conf.d を file モジュールで mode 0750 のディレクトリに。2) app.conf.j2 を template で target/app.conf に\n"
    "(変更時に handler 'reload app' を notify。handler は target/handler.log へ reload の1行を追記)。\n"
    "3) copy(content)で target/motd に motd 変数+改行。4) lineinfile で settings.ini の debug= を debug=false に置換し\n"
    "port=<app_port> を追記。5) loop で sites ごとに conf.d/<名前>.conf(site=<名前>, mode 0640)。\n"
    "ansible-playbook site.yml --check --diff の出力を check.txt、適用後の2回目の出力を second.txt へ(tee)。\n"
    "2回目は changed=0。判定は別の変数値の新環境でも site.yml を実行して確認する。",
    ansible_setup, ansible_check,
    '''cat > site.yml <<'YAML'
---
- hosts: all
  gather_facts: false
  vars_files: [vars.yml]
  vars:
    target: "{{ playbook_dir }}/target"
  tasks:
    - name: conf.d directory
      ansible.builtin.file:
        path: "{{ target }}/conf.d"
        state: directory
        mode: "0750"
    - name: render app.conf
      ansible.builtin.template:
        src: app.conf.j2
        dest: "{{ target }}/app.conf"
        mode: "0644"
      notify: reload app
    - name: motd
      ansible.builtin.copy:
        content: "{{ motd }}\\n"
        dest: "{{ target }}/motd"
        mode: "0644"
    - name: debug off
      ansible.builtin.lineinfile:
        path: "{{ target }}/settings.ini"
        regexp: '^debug='
        line: debug=false
    - name: port line
      ansible.builtin.lineinfile:
        path: "{{ target }}/settings.ini"
        line: "port={{ app_port }}"
        regexp: '^port='
    - name: per-site files
      ansible.builtin.copy:
        content: "site={{ item }}\\n"
        dest: "{{ target }}/conf.d/{{ item }}.conf"
        mode: "0640"
      loop: "{{ sites }}"
  handlers:
    - name: reload app
      ansible.builtin.shell: echo reload >> "{{ target }}/handler.log"
YAML
ansible-playbook site.yml --check --diff | tee check.txt
ansible-playbook site.yml
ansible-playbook site.yml | tee second.txt''',
    ['''cat > site.yml <<'YAML'
---
- hosts: all
  gather_facts: false
  vars_files: [vars.yml]
  tasks:
    - ansible.builtin.shell: |
        mkdir -p {{ playbook_dir }}/target/conf.d
        echo hardcoded > {{ playbook_dir }}/target/motd
YAML
ansible-playbook site.yml --check --diff | tee check.txt
ansible-playbook site.yml
ansible-playbook site.yml | tee second.txt'''])


# ---------------------------------------------------------------- kubectl (offline manifests)

def kubectl_setup(root):
    spec = {"APP": "web" + secrets.token_hex(2), "IMAGE": "registry.example.test/dojo/app" + secrets.token_hex(2),
            "TAG": f"1.{secrets.randbelow(30) + 10}.{secrets.randbelow(9)}", "PORT": str(8000 + secrets.randbelow(900)),
            "PROD_REPLICAS": str(secrets.randbelow(4) + 3), "LOG_LEVEL": "lvl-" + secrets.token_hex(3),
            "HEALTH": "/healthz"}
    put(root, "spec.env", "".join(f"{k}={v}\n" for k, v in spec.items()))
    remember(root, {"spec": spec}, ["spec.env"])


def _kc(root, args, input=None):
    env = {"KUBECONFIG": str(root / ".no-cluster-kubeconfig")}   # 存在しない設定。クラスタには接続しない。
    result = subprocess.run(["kubectl", *args], cwd=root, text=True, capture_output=True, input=input,
                            timeout=60, env=dict(os.environ, **env))
    if result.returncode:
        raise ValueError("kubectl " + " ".join(args[:2]) + " が失敗: " + result.stderr[-500:])
    return result.stdout


def _k8s_objects(root, text):
    """kubectl の --local デコード(サーバ不要)で YAML を JSON オブジェクトにする。"""
    raw = _kc(root, ["annotate", "--local", "-f", "-", "dojo.test/seen=1", "--overwrite", "-o", "json"], input=text)
    decoder, pos, items = json.JSONDecoder(), 0, []
    while pos < len(raw):   # 複数文書は JSON が連結して出力される
        if raw[pos].isspace():
            pos += 1
            continue
        obj, pos = decoder.raw_decode(raw, pos)
        items += obj["items"] if obj.get("kind") == "List" else [obj]
    for item in items:
        item["metadata"].get("annotations", {}).pop("dojo.test/seen", None)
    return items


def _k8s_verify(objs, spec, prefix, replicas, where):
    kinds = sorted(o["kind"] for o in objs)
    require(kinds == ["ConfigMap", "Deployment", "Service"], where + ": Deployment/Service/ConfigMap が1つずつ必要です。")
    by = {o["kind"]: o for o in objs}
    dep, svc, cm = by["Deployment"], by["Service"], by["ConfigMap"]
    app = spec["APP"]
    require(dep["metadata"]["name"] == prefix + app, where + ": Deployment 名は " + prefix + app + " です。")
    require(dep["spec"].get("replicas") == replicas, where + f": replicas は {replicas} です。")
    match = dep["spec"]["selector"].get("matchLabels") or {}
    pod = dep["spec"]["template"]["metadata"].get("labels") or {}
    require(match and all(pod.get(k) == v for k, v in match.items()), where + ": selector.matchLabels が Pod ラベルと一致しません。")
    containers = dep["spec"]["template"]["spec"]["containers"]
    require(len(containers) == 1, where + ": コンテナは1つです。")
    c = containers[0]
    require(c["image"] == f"{spec['IMAGE']}:{spec['TAG']}" and not c["image"].endswith(":latest"),
            where + ": image は spec.env の IMAGE:TAG(latest 不可)です。")
    ports = c.get("ports") or []
    require(any(p.get("containerPort") == int(spec["PORT"]) for p in ports), where + ": containerPort が PORT と違います。")
    names = {p.get("name") for p in ports if p.get("containerPort") == int(spec["PORT"]) and p.get("name")}
    res = c.get("resources") or {}
    for kind in ("requests", "limits"):
        for key in ("cpu", "memory"):
            require((res.get(kind) or {}).get(key), where + f": resources.{kind}.{key} が必要です。")
    for probe in ("readinessProbe", "livenessProbe"):
        http = (c.get(probe) or {}).get("httpGet") or {}
        require(http.get("path") == spec["HEALTH"] and (http.get("port") == int(spec["PORT"]) or http.get("port") in names),
                where + f": {probe} は httpGet {spec['HEALTH']} がコンテナポートを指す必要があります。")
    require(cm["metadata"]["name"] == prefix + app + "-config" and (cm.get("data") or {}).get("LOG_LEVEL") == spec["LOG_LEVEL"],
            where + ": ConfigMap 名と LOG_LEVEL を確認してください。")
    refs = [e["configMapRef"]["name"] for e in c.get("envFrom") or [] if "configMapRef" in e]
    refs += [e["valueFrom"]["configMapKeyRef"]["name"] for e in c.get("env") or []
             if (e.get("valueFrom") or {}).get("configMapKeyRef")]
    require(refs and set(refs) == {cm["metadata"]["name"]}, where + ": Deployment が ConfigMap を参照している必要があります。")
    require(svc["metadata"]["name"] == prefix + app, where + ": Service 名が違います。")
    sel = svc["spec"].get("selector") or {}
    require(sel and all(pod.get(k) == v for k, v in sel.items()), where + ": Service の selector が Pod ラベルと一致しません。")
    sp = svc["spec"].get("ports") or []
    require(len(sp) == 1 and sp[0].get("port") == 80 and (sp[0].get("targetPort") == int(spec["PORT"]) or sp[0].get("targetPort") in names),
            where + ": Service は 80 → コンテナポートです。")


def kubectl_check(root):
    spec = fixture(root)["spec"]
    expect = {"base/deployment.yaml": "Deployment", "base/service.yaml": "Service", "base/configmap.yaml": "ConfigMap"}
    for name, kind in expect.items():
        objs = _k8s_objects(root, read(root, name))
        require([o["kind"] for o in objs] == [kind], name + " は " + kind + " 1つだけを書きます。")
    require("../../base" in read(root, "overlays/prod/kustomization.yaml"), "overlay は ../../base を resources に取ります。")
    base = _k8s_objects(root, _kc(root, ["kustomize", "base"]))
    _k8s_verify(base, spec, "", 1, "base")
    prod = _k8s_objects(root, _kc(root, ["kustomize", "overlays/prod"]))
    _k8s_verify(prod, spec, "prod-", int(spec["PROD_REPLICAS"]), "overlays/prod")
    for path in (root / "base").glob("*.yaml"):
        require(":latest" not in path.read_text(), path.name + " に latest タグがあります。")


add("kubectl", "kubectl/kustomize: マニフェストをオフラインで書き、overlayで本番化(クラスタ不使用)", "bash kubectl", "bash kubectl",
    "クラスタには接続しない(KUBECONFIG は存在しない設定)。kubectl create --dry-run=client -o yaml と\n"
    "kubectl kustomize(どちらもサーバ不要)、kubectl annotate --local での検証だけを使う。apply/create -f はサーバが要るため使わない。\n"
    "spec.env(原本)の値で base/ に deployment.yaml・service.yaml・configmap.yaml・kustomization.yaml を作る。\n"
    "Deployment: 名前 APP、replicas 1、selector と Pod ラベル一致、image IMAGE:TAG(latest 禁止)、containerPort PORT、\n"
    "requests/limits の cpu・memory、readiness/liveness の httpGet HEALTH、envFrom で ConfigMap(名前 APP-config, LOG_LEVEL)。\n"
    "Service: 80 → PORT、selector は Pod ラベル。overlays/prod/kustomization.yaml は ../../base を取り、\n"
    "namePrefix prod- と replicas: で PROD_REPLICAS にする。kubectl kustomize overlays/prod の結果で判定。",
    kubectl_setup, kubectl_check,
    '''. ./spec.env
mkdir -p base overlays/prod
cat > base/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $APP
  labels: {app: $APP}
spec:
  replicas: 1
  selector:
    matchLabels: {app: $APP}
  template:
    metadata:
      labels: {app: $APP}
    spec:
      containers:
        - name: $APP
          image: $IMAGE:$TAG
          ports:
            - {name: http, containerPort: $PORT}
          envFrom:
            - configMapRef: {name: $APP-config}
          resources:
            requests: {cpu: 100m, memory: 64Mi}
            limits: {cpu: 500m, memory: 128Mi}
          readinessProbe:
            httpGet: {path: $HEALTH, port: http}
          livenessProbe:
            httpGet: {path: $HEALTH, port: http}
EOF
cat > base/service.yaml <<EOF
apiVersion: v1
kind: Service
metadata:
  name: $APP
spec:
  selector: {app: $APP}
  ports:
    - {port: 80, targetPort: http}
EOF
cat > base/configmap.yaml <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: $APP-config
data:
  LOG_LEVEL: $LOG_LEVEL
EOF
cat > base/kustomization.yaml <<EOF
resources: [deployment.yaml, service.yaml, configmap.yaml]
EOF
cat > overlays/prod/kustomization.yaml <<EOF
resources: [../../base]
namePrefix: prod-
replicas:
  - {name: $APP, count: $PROD_REPLICAS}
EOF
kubectl kustomize overlays/prod > /dev/null''',
    ['''. ./spec.env
mkdir -p base overlays/prod
cat > base/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata: {name: $APP}
spec:
  replicas: $PROD_REPLICAS
  selector: {matchLabels: {app: $APP}}
  template:
    metadata: {labels: {app: web}}
    spec:
      containers:
        - {name: c, image: "$IMAGE:latest"}
EOF
printf 'apiVersion: v1\\nkind: Service\\nmetadata: {name: %s}\\nspec: {selector: {app: other}, ports: [{port: 80}]}\\n' $APP > base/service.yaml
printf 'apiVersion: v1\\nkind: ConfigMap\\nmetadata: {name: x}\\n' > base/configmap.yaml
printf 'resources: [deployment.yaml, service.yaml, configmap.yaml]\\n' > base/kustomization.yaml
printf 'resources: [../../base]\\n' > overlays/prod/kustomization.yaml'''])
