"""追加のネイティブ実習(第5群): クラウドCLI(ローカルエミュレータ)、zsh、fish、dotfiles。"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import time

from curriculum.toolbox_labs import add, put, read, require, run, remember, fixture  # noqa: F401

SAFE_PROXY = "http://127.0.0.1:9"  # 万一の実エンドポイント接続を必ず失敗させる行き止まり


def _proc(root, command, env=None, timeout=30, input=None):
    return subprocess.run(command, cwd=root, env=env, input=input, text=True,
                          capture_output=True, timeout=timeout,
                          stdin=None if input is not None else subprocess.DEVNULL)


# ---------------------------------------------------------------- AWS CLI

def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop_emulator(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, TypeError):
        pass


def _start_emulator(root):
    old = root / ".fixture.json"
    if old.is_file():
        try:
            _stop_emulator(json.loads(old.read_text()).get("pid"))
        except ValueError:
            pass
    port = _free_port()
    log = open(root / "emulator.log", "w")
    process = subprocess.Popen(["timeout", "7200", "moto_server", "-H", "127.0.0.1", "-p", str(port)],
                               cwd=root, stdout=log, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(150):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return port, process.pid
        except OSError:
            time.sleep(0.1)
    _stop_emulator(process.pid)
    raise ValueError("ローカルエミュレータ(moto_server)が起動しません。")


def _aws_env(root, port, own_config=True):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("AWS_") and k.lower() not in ("http_proxy", "https_proxy", "no_proxy", "all_proxy")}
    env.update(HOME=str(root), AWS_ENDPOINT_URL="http://127.0.0.1:%d" % port,
               AWS_EC2_METADATA_DISABLED="true", AWS_PAGER="", AWS_MAX_ATTEMPTS="1",
               HTTPS_PROXY=SAFE_PROXY, HTTP_PROXY=SAFE_PROXY, NO_PROXY="127.0.0.1")
    if own_config:
        env.update(AWS_CONFIG_FILE=str(root / "aws/config"),
                   AWS_SHARED_CREDENTIALS_FILE=str(root / "aws/credentials"))
    else:
        env.update(AWS_CONFIG_FILE="/dev/null", AWS_SHARED_CREDENTIALS_FILE="/dev/null",
                   AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE", AWS_SECRET_ACCESS_KEY="dojo-fake-secret",
                   AWS_DEFAULT_REGION="us-east-1")
    return env


def _aws(root, port, *args, own_config=False, ok=True):
    """エミュレータ(127.0.0.1)だけに向けてawsを実行する。SQSは--endpoint-urlが必要。"""
    command = ["aws", *args]
    if args and args[0] == "sqs":
        command += ["--endpoint-url", "http://127.0.0.1:%d" % port]
    result = _proc(root, command, _aws_env(root, port, own_config))
    if ok and result.returncode:
        raise ValueError("aws失敗: " + " ".join(args) + "\n" + result.stderr[-400:])
    return result


def _env_sh(port):
    return f'''# 実AWSには接続しません。127.0.0.1のエミュレータ専用です。 . ./env.sh で読み込みます。
export AWS_CONFIG_FILE="$PWD/aws/config" AWS_SHARED_CREDENTIALS_FILE="$PWD/aws/credentials"
export AWS_ENDPOINT_URL=http://127.0.0.1:{port} AWS_EC2_METADATA_DISABLED=true AWS_PAGER= AWS_MAX_ATTEMPTS=1
export HTTPS_PROXY={SAFE_PROXY} HTTP_PROXY={SAFE_PROXY} NO_PROXY=127.0.0.1
unset AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_DEFAULT_REGION
'''


def _no_real_endpoint(root, port):
    for name in ("aws/config", "aws/credentials"):
        text = read(root, name)
        require("amazonaws.com" not in text, name + " に実AWSのエンドポイントがあります。")
        for url in re.findall(r"endpoint_url\s*=\s*(\S+)", text):
            require(url.startswith("http://127.0.0.1:%d" % port),
                    name + " のendpoint_urlはローカルエミュレータ以外を指せません。")


def _keys(root):
    return json.loads(read(root, "keys.json"))


def awss3_setup(root):
    port, pid = _start_emulator(root)
    token = secrets.token_hex(3)
    keys = {"dojo": ["AKIA" + secrets.token_hex(8).upper(), secrets.token_hex(16)],
            "audit": ["AKIA" + secrets.token_hex(8).upper(), secrets.token_hex(16)]}
    put(root, "keys.json", json.dumps(keys, indent=1))
    put(root, "env.sh", _env_sh(port))
    put(root, "site/index.html", f"<h1>dojo {token}</h1>\n")
    put(root, "site/css/main.css", "body { margin: 0 }\n")
    put(root, "site/old.txt", "remove me\n")
    remember(root, {"port": port, "pid": pid, "bucket": "dojo-" + token, "missing": "nobucket-" + token,
                    "index": hashlib.sha256((root / "site/index.html").read_bytes()).hexdigest()},
             ["keys.json", "env.sh"])


def awss3_check(root):
    data = fixture(root)
    port, bucket = data["port"], data["bucket"]
    _no_real_endpoint(root, port)
    keys = _keys(root)
    conf, cred = configparser.ConfigParser(), configparser.ConfigParser()
    conf.read_string(read(root, "aws/config"))
    cred.read_string(read(root, "aws/credentials"))
    for name, region, output in (("dojo", "ap-northeast-1", "json"), ("audit", "us-east-1", "table")):
        section = "profile " + name
        require(conf.has_section(section), "aws/config に [%s] が必要です(configでは profile 接頭辞を付けます)。" % section)
        require(conf.get(section, "region", fallback="") == region and conf.get(section, "output", fallback="") == output,
                "[%s] は region=%s output=%s にします。" % (section, region, output))
        require(cred.has_section(name) and cred.get(name, "aws_access_key_id", fallback="") == keys[name][0]
                and cred.get(name, "aws_secret_access_key", fallback="") == keys[name][1],
                "aws/credentials の [%s] にkeys.jsonの鍵を書きます(credentialsでは profile 接頭辞なし)。" % name)
    for name, region in (("dojo", "ap-northeast-1"), ("audit", "us-east-1")):
        got = _aws(root, port, "configure", "get", "region", "--profile", name, own_config=True).stdout.strip()
        require(got == region, "aws configure get region --profile %s が %s になりません。" % (name, region))
    require(_aws(root, port, "s3api", "get-bucket-location", "--bucket", bucket, "--profile", "dojo",
                 "--query", "LocationConstraint", "--output", "text", own_config=True).stdout.strip() == "ap-northeast-1",
            "バケットをdojoプロファイル(ap-northeast-1)で作成します。")
    site = root / "site"
    local = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    require("old.txt" not in local, "site/old.txt をローカルから削除します。")
    require(hashlib.sha256(local.get("index.html", b"")).hexdigest() != data["index"], "site/index.html を更新します。")
    keys_remote = json.loads(_aws(root, port, "s3api", "list-objects-v2", "--bucket", bucket, "--output", "json",
                                  "--query", "Contents[].Key", own_config=False).stdout or "null") or []
    require(sorted(keys_remote) == sorted("site/" + k for k in local),
            "S3の内容がsite/と一致しません(--delete付きsyncで削除も反映します)。")
    for name, body in local.items():
        got = _aws(root, port, "s3", "cp", "s3://%s/site/%s" % (bucket, name), "-").stdout
        require(got.encode() == body, name + " の中身がS3側と違います。")
    require("(dryrun) delete: s3://%s/site/old.txt" % bucket in read(root, "dryrun.txt"),
            "dryrun.txt は削除後・実sync前の sync --delete --dryrun の出力です。")
    require(read(root, "account.txt").strip() == "123456789012", "account.txt は sts get-caller-identity のAccountです。")
    require(read(root, "buckets.txt").split() == [bucket], "buckets.txt は list-buckets --query ... --output text の結果です。")
    require("NoSuchBucket" in read(root, "error.txt"),
            "error.txt は存在しないバケットへのs3api list-objects-v2のstderrです。")
    require(read(root, "error-code.txt").strip() == "NoSuchBucket", "error-code.txt にはエラーコードだけを書きます。")
    require(read(root, "denied-code.txt").strip() == "AccessDenied",
            "権限不足で返るコードは AccessDenied です(バケット不在は NoSuchBucket)。denied-code.txt に書きます。")
    _stop_emulator(data["pid"])


add("awscli-s3", "AWS CLIのプロファイルとS3 syncをローカルエミュレータで練習する", "bash aws moto_server python3", "bash awscli moto",
    "実AWSは使いません。127.0.0.1のmotoエミュレータが起動済みです。先に `. ./env.sh`。keys.json は偽の鍵です。\n"
    "(gcloud/az も考え方は同じ: 認証情報・設定・リソース操作・--format、ただしここでは実行しません)\n"
    "1) aws/config に [profile dojo](region=ap-northeast-1, output=json)と [profile audit](us-east-1, table)、\n"
    "   aws/credentials に [dojo] [audit](keys.jsonの鍵)。2) バケット(名前は.fixture.jsonのbucket)を dojo で作成し、\n"
    "   site/ を s3://BUCKET/site/ へ sync。3) site/old.txt を削除し index.html を更新、`sync --delete --dryrun` の出力を dryrun.txt、\n"
    "   その後 本当に sync --delete。4) account.txt: sts get-caller-identity のAccount(--query/--output text)、\n"
    "   buckets.txt: list-buckets のBucket名(--query ... --output text)。5) 存在しないバケット(.fixture.jsonのmissing)に\n"
    "   s3api list-objects-v2 してstderrを error.txt、コードだけを error-code.txt。権限不足で返るコードを denied-code.txt。",
    awss3_setup, awss3_check,
    '''. ./env.sh
B=$(python3 -c 'import json;d=json.load(open(".fixture.json"));print(d["bucket"])')
M=$(python3 -c 'import json;d=json.load(open(".fixture.json"));print(d["missing"])')
mkdir -p aws
python3 - <<'PY'
import json
k = json.load(open("keys.json"))
open("aws/config", "w").write("[profile dojo]\\nregion = ap-northeast-1\\noutput = json\\n\\n[profile audit]\\nregion = us-east-1\\noutput = table\\n")
open("aws/credentials", "w").write("".join("[%s]\\naws_access_key_id = %s\\naws_secret_access_key = %s\\n\\n" % (n, v[0], v[1]) for n, v in k.items()))
PY
aws s3 mb "s3://$B" --profile dojo
aws s3 sync site "s3://$B/site/" --profile dojo
rm site/old.txt
echo "<p>updated</p>" >> site/index.html
aws s3 sync site "s3://$B/site/" --delete --dryrun --profile dojo > dryrun.txt
aws s3 sync site "s3://$B/site/" --delete --profile dojo
aws sts get-caller-identity --profile dojo --query Account --output text > account.txt
aws s3api list-buckets --profile dojo --query 'Buckets[].Name' --output text > buckets.txt
aws s3api list-objects-v2 --bucket "$M" --profile dojo 2> error.txt || true
grep -o 'NoSuchBucket' error.txt | head -n 1 > error-code.txt
echo AccessDenied > denied-code.txt''',
    ["echo x"])


def awsq_setup(root):
    port, pid = _start_emulator(root)
    token = secrets.token_hex(3)
    put(root, "env.sh", _env_sh(port))
    put(root, "aws/config", "[profile audit]\nregion = us-east-1\noutput = json\n")
    put(root, "aws/credentials", "[audit]\naws_access_key_id = AKIA%s\naws_secret_access_key = %s\n"
        % (secrets.token_hex(8).upper(), secrets.token_hex(16)))
    put(root, "policy.json", json.dumps({"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "arn:aws:s3:::dojo-%s/*" % token}]}))
    envs = ["prod", "dev", "prod", "stage", "prod"]
    ids = {}
    for env_name in envs:
        out = _aws(root, port, "ec2", "run-instances", "--image-id", "ami-12c6146b", "--tag-specifications",
                   "ResourceType=instance,Tags=[{Key=Env,Value=%s}]" % env_name,
                   "--query", "Instances[0].InstanceId", "--output", "text").stdout.strip()
        ids.setdefault(env_name, []).append(out)
    queues = sorted("jobs-%s-%s" % (n, token) for n in ("a", "b", "c"))
    for q in queues:
        _aws(root, port, "sqs", "create-queue", "--queue-name", q)
    users = ["svc-%s-%d" % (token, i) for i in range(4)]
    for u in users:
        _aws(root, port, "iam", "create-user", "--user-name", u)
    remember(root, {"port": port, "pid": pid, "token": token, "prod": sorted(ids["prod"]),
                    "all_ids": sorted(i for v in ids.values() for i in v), "queues": queues, "users": users},
             ["env.sh", "policy.json"])


def awsq_check(root):
    data = fixture(root)
    port, token = data["port"], data["token"]
    _no_real_endpoint(root, port)
    require(sorted(read(root, "prod-ids.txt").split()) == data["prod"], "prod-ids.txt はEnv=prodのインスタンスIDだけです(--query + --output text)。")
    table = read(root, "table.txt")
    require("DescribeInstances" in table and all(i in table for i in data["all_ids"]) and "|" in table,
            "table.txt は describe-instances の --output table の出力です。")
    require(read(root, "queues.txt").split() == data["queues"], "queues.txt はキュー名(URL末尾)を昇順で1行ずつ。")
    user, policy = "deploy-" + token, "read-" + token
    require(_aws(root, port, "iam", "get-user", "--user-name", user, "--query", "User.UserName", "--output", "text").stdout.strip() == user,
            "IAMユーザー %s を作成します。" % user)
    arn = "arn:aws:iam::123456789012:policy/" + policy
    attached = _aws(root, port, "iam", "list-attached-user-policies", "--user-name", user, "--query",
                    "AttachedPolicies[].PolicyArn", "--output", "text").stdout.split()
    require(attached == [arn], "ポリシー %s をユーザーへアタッチします。" % policy)
    doc = json.loads(_aws(root, port, "iam", "get-policy-version", "--policy-arn", arn, "--version-id", "v1",
                          "--query", "PolicyVersion.Document", "--output", "json").stdout)
    require(doc == json.loads(read(root, "policy.json")), "ポリシー本文は policy.json (file://)から作ります。")
    names = sorted(data["users"] + [user])
    require(read(root, "all-users.txt").split() == names, "all-users.txt は全ページを辿った全ユーザー名(昇順)です。")
    require(read(root, "pages.txt").strip() == str(-(-len(names) // 2)),
            "pages.txt は --max-items 2 で取得したページ数です(NextTokenが無くなるまで)。")
    require(read(root, "dryrun-code.txt").strip() == "DryRunOperation", "--dry-run のエラーコードは DryRunOperation です。")
    count = len(json.loads(_aws(root, port, "ec2", "describe-instances", "--query", "Reservations[].Instances[].InstanceId",
                                "--output", "json").stdout))
    require(count == len(data["all_ids"]), "--dry-run でインスタンスを実際に起動してはいけません。")
    _stop_emulator(data["pid"])


add("awscli-query", "AWS CLIの--query・--output・ページング・IAM・--dry-runを練習する", "bash aws moto_server jq python3", "bash awscli moto jq",
    "実AWSは使いません(`. ./env.sh` でローカルエミュレータ向け)。profile audit を使います。EC2・SQS・IAMが投入済み。\n"
    "SQSだけは --endpoint-url \"$AWS_ENDPOINT_URL\" が必要です(CLIの実装上、環境変数を見ないため)。\n"
    "1) prod-ids.txt: tag Env=prod のインスタンスID(--query JMESPath + --output text)。\n"
    "2) table.txt: describe-instances の ID/Env を --output table で。3) queues.txt: SQSキュー名を昇順(jq併用)。\n"
    "4) IAMユーザー deploy-TOKEN と、policy.json(file://)から作るポリシー read-TOKEN を作成しアタッチ(TOKENは.fixture.jsonのtoken)。\n"
    "5) iam list-users を --max-items 2 と --starting-token で全ページ辿り、全ユーザー名を all-users.txt、ページ数を pages.txt。\n"
    "6) ec2 run-instances --image-id ami-12c6146b --dry-run のエラーコードを dryrun-code.txt(起動はしない)。",
    awsq_setup, awsq_check,
    '''. ./env.sh
export AWS_PROFILE=audit
T=$(python3 -c 'import json;print(json.load(open(".fixture.json"))["token"])')
aws ec2 describe-instances --query 'Reservations[].Instances[?Tags[?Key==`Env`&&Value==`prod`]].InstanceId' --output text | tr '\\t' '\\n' | sort > prod-ids.txt
aws ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Env`]|[0].Value]' --output table > table.txt
aws sqs list-queues --endpoint-url "$AWS_ENDPOINT_URL" --query QueueUrls --output json | jq -r '.[] | split("/")[-1]' | sort > queues.txt
aws iam create-user --user-name "deploy-$T" > /dev/null
arn=$(aws iam create-policy --policy-name "read-$T" --policy-document file://policy.json --query Policy.Arn --output text)
aws iam attach-user-policy --user-name "deploy-$T" --policy-arn "$arn"
: > all-users.txt; pages=0; token=""
while :; do
  if [ -z "$token" ]; then out=$(aws iam list-users --max-items 2 --output json)
  else out=$(aws iam list-users --max-items 2 --starting-token "$token" --output json); fi
  pages=$((pages+1))
  echo "$out" | jq -r '.Users[].UserName' >> all-users.txt
  token=$(echo "$out" | jq -r '.NextToken // empty')
  [ -n "$token" ] || break
done
sort -o all-users.txt all-users.txt
echo "$pages" > pages.txt
aws ec2 run-instances --image-id ami-12c6146b --dry-run 2> dry.err || true
grep -o 'DryRunOperation' dry.err | head -n 1 > dryrun-code.txt''',
    ["echo x"])


# ---------------------------------------------------------------- zsh

def _zsh_env(root):
    (root / "zhome").mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("ZDOTDIR",) and not k.startswith("HIST")}
    env.update(HOME=str(root / "zhome"), ZDOTDIR=str(root / "zdot"), TERM="dumb", USER="dojo", LOGNAME="dojo")
    return env


def zsh_setup(root):
    put(root, "zdot/.zshrc", '''# bash流の書き方が混ざっていて、zshで読むとエラーになる
shopt -s globstar
PS1='\\u@\\h:\\w\\$ '
arr=(one two three)
export FIRST=${arr[0]}
compinit
HISTSIZE=100
''')
    put(root, "env.sh", 'export HOME="$PWD/zhome" ZDOTDIR="$PWD/zdot"\n# 試す: zsh -i / zsh -l / zsh -c "..."\n')
    names = [secrets.token_hex(2) for _ in range(3)]
    put(root, "vars.zsh", "arr=(%s)\nphrase=\"one two three\"\n" % " ".join(names))
    files = {"tree/a.txt": 1, "tree/b.md": 2, "tree/sub/c.txt": 5, "tree/sub/deep/d.txt": 3,
             "tree/sub/deep/e.log": 4}
    extra = secrets.randbelow(3)
    for i in range(extra):
        files["tree/more%d.txt" % i] = 6 + i
    newest = None
    base = 1_700_000_000
    for name, order in files.items():
        put(root, name, name + "\n")
        os.utime(root / name, (base + order * 100, base + order * 100))
    newest = max(files, key=files.get)
    os.symlink("a.txt", root / "tree/link.txt")
    expected = [names[0], names[2], "1", str(1 + sum(1 for n in files if n.endswith(".txt"))),
                str(sum(1 for n in files if n.count("/") == 1)), Path(newest).name, "3"]
    remember(root, {"expected": expected}, ["vars.zsh", "env.sh"])


def _zsh_order(root, env, args):
    log = root / "zdot/order.log"
    log.write_text("")
    result = _proc(root, ["zsh", *args], env)
    require(not result.stderr.strip(), "zsh起動時にエラーが出ています: " + result.stderr.strip()[:300])
    return log.read_text().split()


def zsh_check(root):
    data = fixture(root)
    env = _zsh_env(root)
    zdot = root / "zdot"
    for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin"):
        require((zdot / name).is_file(), "zdot/%s がありません(各ファイルが `print env >> $ZDOTDIR/order.log` 等を記録)。" % name)
    require(_zsh_order(root, env, ["-c", "true"]) == ["env"], "zsh -c は .zshenv だけを読みます(order.logにenv)。")
    require(_zsh_order(root, env, ["-i", "-c", "true"]) == ["env", "rc"], "zsh -i は .zshenv → .zshrc の順です。")
    require(_zsh_order(root, env, ["-l", "-c", "true"]) == ["env", "profile", "login"],
            "zsh -l は .zshenv → .zprofile → .zlogin(.zshrcは対話時のみ)。")
    require(_zsh_order(root, env, ["-l", "-i", "-c", "true"]) == ["env", "profile", "rc", "login"],
            "ログイン+対話は env → profile → rc → login です。マーカー名は env/profile/rc/login。")
    probe = ('print -r -- $options[histignorealldups] $options[sharehistory] $options[autocd] $options[beep] '
             '$HISTSIZE $SAVEHIST ${HISTFILE:t} ${${HISTFILE:h}:t}; print -r -- "$PROMPT"; '
             'print -r -- $+functions[compdef] $+_comps[git] $+_comps[ls]; zstyle -L ":completion:*" menu; print -rP -- "$PROMPT"')
    out = _proc(root, ["zsh", "-i", "-c", probe], env)
    require(not out.stderr.strip(), ".zshrc がエラーを出しています(shopt/PS1/compinit/配列添字を直します): " + out.stderr.strip()[:300])
    lines = out.stdout.splitlines()
    first = lines[0].split()
    require(first[:4] == ["on", "on", "on", "off"], "setopt HIST_IGNORE_ALL_DUPS SHARE_HISTORY AUTO_CD、unsetopt BEEP にします。")
    require(int(first[4]) >= 5000 and int(first[5]) >= 5000, "HISTSIZE と SAVEHIST は5000以上に。")
    require(first[6:] == [".zsh_history", "zdot"], "HISTFILE は $ZDOTDIR/.zsh_history にします。")
    require("%n" in lines[1] and re.search(r"%\d*~|%[dc/]", lines[1]) and "%#" in lines[1] and "\\u" not in lines[1],
            "PROMPT はzsh記法(%n、%~、%#)で書きます。bashの\\u\\wは使えません。")
    require(lines[2].split() == ["1", "1", "1"], "autoload -Uz compinit && compinit -d $ZDOTDIR/.zcompdump で補完を有効にします。")
    require("menu select" in lines[3], "zstyle ':completion:*' menu select を設定します。")
    require("@" in lines[4] and "%" not in lines[4].replace("% ", "").replace("%", "", 1) and "%n" not in lines[4], "PROMPT を展開するとユーザー名@ホストが出ます。")
    script = read(root, "diff.zsh")
    require(re.search(r"\*\*/", script) and re.search(r"\(\.", script) and "om[1]" in script and "${=" in script,
            "diff.zsh は **/、(.)、(om[1])、${=phrase} を使って書きます。")
    require("find " not in script and "ls " not in script, "find/lsを使わず、zshのグロブだけで書きます。")
    result = _proc(root, ["zsh", "-f", "diff.zsh"], env)
    require(result.returncode == 0 and result.stdout.split() == data["expected"],
            "diff.zsh の出力(7行)が期待と違います。期待される内容を確認:\n" + (result.stderr or result.stdout)[:300])


add("zsh", "zshの起動ファイル順・setopt・プロンプト・補完・グロブを実機で確認する", "bash zsh", "bash zsh",
    "zdot/ が ZDOTDIR です(`. ./env.sh`)。zdot/.zshrc は bash流で壊れています。直して実機の zsh で確認:\n"
    "1) .zshenv .zprofile .zshrc .zlogin を作り、各ファイルが `print -r -- env >> $ZDOTDIR/order.log`(env/profile/rc/login)を追記。\n"
    "   zsh -c / -i -c / -l -c / -l -i -c で読まれる順序を観察します。\n"
    "2) .zshrc: setopt HIST_IGNORE_ALL_DUPS SHARE_HISTORY AUTO_CD、unsetopt BEEP、HISTSIZE/SAVEHISTは5000以上、\n"
    "   HISTFILE=$ZDOTDIR/.zsh_history、PROMPT='%n@%m %~ %# '、compinit(-d $ZDOTDIR/.zcompdump)、zstyle ':completion:*' menu select。\n"
    "3) diff.zsh を書く(zsh -f diff.zsh で実行)。vars.zshをsourceして1行ずつ出力: 配列の最初の要素(添字は1から)、最後の要素、\n"
    "   for w in $phrase の反復回数(分割されない)、tree/**/*.txt の数(再帰グロブ)、tree/*(.) の数(通常ファイルのみ)、\n"
    "   tree/**/*(.om[1]) の最新ファイル名(:t)、${=phrase} の単語数。",
    zsh_setup, zsh_check,
    '''. ./env.sh
cd zdot
printf 'print -r -- env >> $ZDOTDIR/order.log\\n' > .zshenv
printf 'print -r -- profile >> $ZDOTDIR/order.log\\n' > .zprofile
printf 'print -r -- login >> $ZDOTDIR/order.log\\n' > .zlogin
cat > .zshrc <<'RC'
print -r -- rc >> $ZDOTDIR/order.log
setopt HIST_IGNORE_ALL_DUPS SHARE_HISTORY AUTO_CD
unsetopt BEEP
HISTSIZE=10000
SAVEHIST=10000
HISTFILE=$ZDOTDIR/.zsh_history
PROMPT='%n@%m %~ %# '
autoload -Uz compinit
compinit -u -d $ZDOTDIR/.zcompdump
zstyle ':completion:*' menu select
RC
cd ..
cat > diff.zsh <<'Z'
source ./vars.zsh
print -r -- ${arr[1]}
print -r -- ${arr[-1]}
n=0; for w in $phrase; do (( n++ )); done; print -r -- $n
files=(tree/**/*.txt); print -r -- ${#files}
top=(tree/*(.)); print -r -- ${#top}
newest=(tree/**/*(.om[1]:t)); print -r -- $newest
words=(${=phrase}); print -r -- ${#words}
Z''',
    ["cd zdot; echo env > .zshenv; echo profile > .zprofile; echo rc > .zshrc; echo login > .zlogin"])


# ---------------------------------------------------------------- fish

def _fish_env(root):
    for d in ("fhome", "xdgdata", "xdgstate", "xdgcache"):
        (root / d).mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "fish_", "dojo_"))}
    env.update(HOME=str(root / "fhome"), XDG_CONFIG_HOME=str(root / "xdg"), XDG_DATA_HOME=str(root / "xdgdata"),
               XDG_STATE_HOME=str(root / "xdgstate"), XDG_CACHE_HOME=str(root / "xdgcache"), TERM="dumb")
    env.pop("EDITOR", None)
    env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
    return env


def fish_setup(root):
    token = secrets.token_hex(2)
    put(root, "xdg/fish/config.fish", '''# bash流で書かれていてfishでは動かない
export EDITOR=vim
[[ -d $HOME/.local/bin ]] && PATH=$PATH:$HOME/.local/bin
alias ll='ls -l'
if [ $? -eq 0 ]; then
  echo ready
fi
''')
    (root / "fhome/.local/bin").mkdir(parents=True, exist_ok=True)
    put(root, "bin/dojo", "#!/bin/sh\necho dojo \"$@\"\n", 0o755)  # 補完はコマンドが実在して初めて読み込まれる
    put(root, "env.sh", 'export HOME="$PWD/fhome" XDG_CONFIG_HOME="$PWD/xdg" XDG_DATA_HOME="$PWD/xdgdata" PATH="$PWD/bin:$PATH"\n')
    major, minor, patch = secrets.randbelow(9) + 1, secrets.randbelow(40), secrets.randbelow(9)
    put(root, "input.txt", "v%d.%d.%d-rc1\n" % (major, minor, patch))
    remember(root, {"token": token, "expected": ["%d.%d" % (major, minor), "2", "1", "DOJO" + token.upper(),
                                                    "script", "port.fish", "6"]}, ["input.txt", "env.sh", "bin/dojo"])


def fish_check(root):
    data = fixture(root)
    env = _fish_env(root)
    conf = root / "xdg/fish"

    def fish(*args, interactive=False):
        return _proc(root, ["fish", *(["-i"] if interactive else []), "-c", *args], env)

    result = fish("exit")
    require(not result.stderr.strip() and not result.stdout.strip(),
            "config.fish がエラーか出力を出しています(POSIX構文・echoを直す): " + (result.stderr or result.stdout).strip()[:300])
    text = read(root, "xdg/fish/config.fish")
    require(re.search(r"fish_add_path\s+(?:\S+\s+)*?(-[a-zA-Z]*g[a-zA-Z]*|--global)\b", text),
            "config.fish では fish_add_path -g を使います(既定の -U は universal変数に永続保存されます)。")
    require("dojo_theme" not in text, "universal変数は config.fish に書かず、set -U で一度だけ設定します。")
    path = fish('string join \\n $PATH').stdout.splitlines()
    require(str(root / "fhome/.local/bin") in path, "$HOME/.local/bin を fish_add_path -g でPATHへ。")
    environment = fish("env").stdout.splitlines()
    require("EDITOR=vim" in environment, "set -gx EDITOR vim でexportします。")
    require(fish("echo $dojo_flag").stdout.strip() == "1" and not any(l.startswith("dojo_flag=") for l in environment),
            "config.fish で set -g dojo_flag 1(exportしないグローバル変数)。")
    require(fish("echo $dojo_theme").stdout.strip() == "ocean"
            and re.search(r"^SETUVAR dojo_theme:ocean$", read(root, "xdg/fish/fish_variables"), re.M),
            "set -U dojo_theme ocean を一度だけ実行します(fish_variablesに保存されます)。")
    require((conf / "functions/mkcd.fish").is_file() and "mkcd" not in text, "functions/mkcd.fish に関数を置きます(自動ロード)。")
    work = root / "mkcd-work"
    work.mkdir(exist_ok=True)
    got = fish("cd %s; mkcd a/b; pwd" % work).stdout.strip()
    require(got == str(work / "a/b"), "mkcd は mkdir -p して cd します。")
    require(fish("functions -q ll; echo $status").stdout.strip() == "0", "alias ll は常に使える形(対話ガードの外)で定義します。")
    require(fish("abbr -q gs; echo $status").stdout.strip() == "1"
            and fish("abbr -q gs; echo $status", interactive=True).stdout.strip() == "0"
            and "git status" in fish("abbr --show", interactive=True).stdout,
            "abbr -a gs 'git status' は `if status is-interactive` の中で定義します。")
    require((conf / "completions/dojo.fish").is_file(), "completions/dojo.fish を作ります。")
    comp = fish('complete -C "dojo "').stdout.split()
    require({"build", "test", "deploy"} <= set(comp), "dojo の補完に build test deploy を complete -c dojo -a で登録します。")
    script = read(root, "port.fish")
    require("string " in script and "$(" not in script and "$((" not in script and "[[" not in script,
            "port.fish は string組み込みを使い、POSIX構文($(...) [[ ]])を使いません。")
    out = _proc(root, ["fish", "port.fish", "dojo" + data["token"]], env)
    require(out.returncode == 0 and out.stdout.split() == data["expected"],
            "port.fish の出力が期待と違います: " + (out.stderr or out.stdout)[:300])


add("fish", "fishのconfig.fish・関数・abbr・universal変数・stringを実機で確認する", "bash fish", "bash fish",
    "XDG_CONFIG_HOME=./xdg がfishの設定場所です(`. ./env.sh`)。xdg/fish/config.fish はbash流で壊れています。\n"
    "1) config.fishを直す: set -gx EDITOR vim、fish_add_path -g $HOME/.local/bin、set -g dojo_flag 1(export無し)、\n"
    "   alias ll 'ls -l' は常に、abbr -a gs 'git status' は if status is-interactive の中。標準出力は何も出さない。\n"
    "2) `set -U dojo_theme ocean` を一度だけ実行(universal変数: fish_variablesに保存、config.fishには書かない)。\n"
    "3) functions/mkcd.fish(mkdir -p して cd)、completions/dojo.fish(dojo の補完に build test deploy)。\n"
    "4) port.fish(`fish port.fish dojoXXXX` で実行、引数は.fixture.jsonのtoken付き): 7行出力\n"
    "   input.txt のバージョンの major.minor(string replace -r)、printf 'x y\\nz\\n' をコマンド置換した要素数、\n"
    "   test -d nosuch の$status、string upper で引数1を大文字、対話か(`status is-interactive`ならinteractive、違えばscript)、\n"
    "   `status filename` のファイル名部分、for+mathで1から3の和。",
    fish_setup, fish_check,
    '''. ./env.sh
mkdir -p xdg/fish/functions xdg/fish/completions
cat > xdg/fish/config.fish <<'F'
set -gx EDITOR vim
fish_add_path -g $HOME/.local/bin
set -g dojo_flag 1
alias ll 'ls -l'
if status is-interactive
    abbr -a gs 'git status'
end
F
fish -c 'set -U dojo_theme ocean'
printf 'function mkcd\\n    mkdir -p $argv[1]; and cd $argv[1]\\nend\\n' > xdg/fish/functions/mkcd.fish
printf "complete -c dojo -f -a 'build test deploy'\\n" > xdg/fish/completions/dojo.fish
cat > port.fish <<'F'
string replace -r '^v(\\d+)\\.(\\d+).*' '$1.$2' (cat input.txt)
set lines (printf 'x y\\nz\\n')
count $lines
test -d nosuch; echo $status
string upper -- $argv[1]
if status is-interactive
    echo interactive
else
    echo script
end
string replace -r '.*/' '' (status filename)
set total 0
for i in (seq 3)
    set total (math $total + $i)
end
echo $total
F''',
    ["mkdir -p xdg/fish; echo 'export EDITOR=vim' > xdg/fish/config.fish"])


# ---------------------------------------------------------------- dotfiles

def _dot_env(root):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "STOW_"))}
    env.update(HOME=str(root / "home"), GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
    return env


def _dot(root, *command, ok=True):
    result = _proc(root, list(command), _dot_env(root))
    if ok and result.returncode:
        raise ValueError("実行失敗: " + " ".join(command) + "\n" + result.stderr[-400:])
    return result


def dotfiles_setup(root):
    token = secrets.token_hex(4)
    home = root / "home"
    original = {".bashrc": "# original bashrc %s\nalias ll='ls -l'\n" % token,
                ".gitconfig": "[user]\n\tname = dojo\n\temail = dojo@example.invalid\n[core]\n\teditor = nano\n"}
    for name, value in original.items():
        put(home, name, value)
    put(home, ".config/other/keep.txt", "keep\n")
    put(home, ".tmux.conf", "set -g mouse on\n")
    put(home, ".inputrc", "set bell-style none\n")
    repo = home / "dotfiles"
    put(repo, "shell/.bashrc", "# managed bashrc %s\n" % token)
    put(repo, "shell/.profile", "export PATH=$HOME/bin:$PATH\n")
    put(repo, "git/.gitconfig", "[user]\n\tname = dojo\n\temail = dojo@example.invalid\n[core]\n\teditor = vim\n")
    put(repo, "vim/.vimrc", "set number\n")
    put(repo, "vim/.config/nvim/init.vim", "set number\n")
    put(repo, "legacy/.legacyrc", "old\n")
    put(root, "env.sh", 'export HOME="$PWD/home"   # 実際のホームではなく練習用ホーム\n')
    env = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1"}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                ["git", "-c", "user.name=dojo", "-c", "user.email=d@example.invalid", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, env=env, check=True, capture_output=True)
    subprocess.run(["stow", "-d", "home/dotfiles", "-t", "home", "legacy"], cwd=home.parent, env=env, check=True, capture_output=True)
    remember(root, {"token": token, "managed": read(repo, "shell/.bashrc"), "orig": original},
             ["env.sh", "home/.tmux.conf", "home/.inputrc", "home/dotfiles/shell/.profile", "home/dotfiles/vim/.vimrc"])


def dotfiles_check(root):
    data = fixture(root)
    home, repo = root / "home", root / "home/dotfiles"
    for name, value in data["orig"].items():
        require((home / "backup" / name).is_file() and not (home / "backup" / name).is_symlink()
                and (home / "backup" / name).read_text() == value, "home/backup/%s に元の実ファイルをコピーで退避します。" % name)
    require("conflicts" in read(root, "dry.txt") and "existing target" in read(root, "dry.txt"),
            "dry.txt は競合のある状態で stow -n -v を実行した出力(2>&1)です。")
    expected = {".bashrc": "shell/.bashrc", ".profile": "shell/.profile", ".vimrc": "vim/.vimrc",
                ".bash_aliases": "shell/.bash_aliases", ".config/nvim/init.vim": "vim/.config/nvim/init.vim"}
    for name, target in expected.items():
        path = home / name
        require(path.exists() and (path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink()),
                "~/%s が stow のシンボリックリンクになっていません。" % name)
        require(path.resolve() == (repo / target).resolve(), "~/%s のリンク先が dotfiles/%s ではありません。" % (name, target))
    require((home / ".config/other/keep.txt").is_file() and not (home / ".config").is_symlink(), "既存の ~/.config を壊していません。")
    require(not (home / ".legacyrc").exists() and not (home / ".legacyrc").is_symlink(), "stow -D legacy で .legacyrc を外します。")
    gitconfig = home / ".gitconfig"
    require(gitconfig.is_file() and not gitconfig.is_symlink() and gitconfig.read_text() == data["orig"][".gitconfig"],
            "git パッケージを stow -D してから、backup の .gitconfig を実ファイルとして戻します。")
    require(repo.joinpath("shell/.bashrc").read_text() == data["managed"],
            "dotfiles 内のファイルが書き換わっています(stow --adopt は既存ファイルでリポジトリを上書きします)。")
    status = _dot(root, "git", "-C", str(repo), "status", "--porcelain").stdout.strip()
    require(not status, "リポジトリに未コミットの変更があります(.bash_aliases をコミット): " + status)
    require("shell/.bash_aliases" in _dot(root, "git", "-C", str(repo), "ls-files").stdout.split(), "shell/.bash_aliases をコミットします。")
    for current, dirs, files in os.walk(home):
        dirs[:] = [d for d in dirs if d not in (".git", ".dot")]
        for name in dirs + files:
            link = Path(current, name)
            if link.is_symlink():
                require(not os.readlink(link).startswith("/"), "%s が絶対パスのリンクです(stow -t は相対リンクを作ります)。" % link.relative_to(home))
                require(link.exists(), "%s は壊れたリンクです。" % link.relative_to(home))
    bare = home / ".dot"
    git = ["git", "--git-dir", str(bare), "--work-tree", str(home)]
    require(_dot(root, "git", "--git-dir", str(bare), "rev-parse", "--is-bare-repository").stdout.strip() == "true",
            "~/.dot は git init --bare で作ります。")
    require(_dot(root, *git, "config", "--get", "status.showUntrackedFiles", ok=False).stdout.strip() == "no",
            "bare方式では status.showUntrackedFiles no を設定します($HOME全体が未追跡になるため)。")
    require(_dot(root, *git, "ls-tree", "-r", "--name-only", "HEAD").stdout.split() == [".tmux.conf"],
            "bare方式では ~/.tmux.conf だけを add してコミットします。")


add("stow", "GNU stowとbareリポジトリでdotfilesを管理する", "bash stow git", "bash stow git",
    "練習用ホームは ./home(`. ./env.sh` で HOME を向ける)。~/dotfiles がgitリポジトリで、shell git vim legacy のパッケージがあり、\n"
    "legacy は導入済み。~/.bashrc と ~/.gitconfig には既に実ファイルがあります。\n"
    "1) 元の .bashrc/.gitconfig を ~/backup へ cp -a で退避。2) `stow -n -v -d dotfiles -t home shell git vim` の出力(2>&1)を\n"
    "   dry.txt へ(競合を確認、何も変更されない)。--adopt は既存ファイルでリポジトリを上書きするので使いません。\n"
    "3) 競合する実ファイルを退避済みなので消し、stow -d dotfiles -t home shell git vim。リンクは相対で作られます。\n"
    "4) dotfiles/shell/.bash_aliases を追加してコミットし stow -R shell で再配置。5) stow -D legacy で撤去。\n"
    "6) git パッケージを stow -D し、backup の .gitconfig を実ファイルとして ~ に戻す。\n"
    "7) bare方式: git init --bare ~/.dot、status.showUntrackedFiles no、`git --git-dir=$HOME/.dot --work-tree=$HOME` で\n"
    "   ~/.tmux.conf だけを add/commit。",
    dotfiles_setup, dotfiles_check,
    '''. ./env.sh
cd home
mkdir -p backup
cp -a .bashrc .gitconfig backup/
cd ..
stow -n -v -d home/dotfiles -t home shell git vim > dry.txt 2>&1 || true
rm home/.bashrc home/.gitconfig
stow -d home/dotfiles -t home shell git vim
echo "alias gs='git status'" > home/dotfiles/shell/.bash_aliases
git -C home/dotfiles add -A
git -C home/dotfiles commit -q -m aliases
stow -R -d home/dotfiles -t home shell
stow -D -d home/dotfiles -t home legacy
stow -D -d home/dotfiles -t home git
cp -a home/backup/.gitconfig home/.gitconfig
git init -q --bare home/.dot
dot() { git --git-dir="$PWD/home/.dot" --work-tree="$PWD/home" "$@"; }
dot config status.showUntrackedFiles no
dot add .tmux.conf
dot -c user.name=dojo -c user.email=d@example.invalid commit -q -m tmux''',
    ["mkdir -p home/backup; cp -a home/.bashrc home/backup/; stow -n -d home/dotfiles -t home shell > dry.txt 2>&1 || true; stow --adopt -d home/dotfiles -t home shell git vim"])
