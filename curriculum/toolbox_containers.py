"""本物のDockerデーモンで行うライフサイクル実習。

mockを拒否し、学習者が選んだ専用フォルダと一意なラベルの資源だけを使う。
ベースイメージ取得にはネット接続が必要。未導入時に成功へ代替しない。
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

LABEL = "org.linuxdojo.toolbox"


def docker(*args, cwd=None, timeout=30):
    executable = shutil.which("docker")
    if not executable or "mock" in Path(executable).resolve().parts:
        raise ValueError("本物のdocker CLIが必要です。教材の模擬dockerは利用しません。")
    result = subprocess.run([executable, *args], cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode:
        raise ValueError("docker " + " ".join(args[:3]) + " に失敗しました。\n" + result.stderr[-1000:])
    return result.stdout + (result.stderr if args and args[0] == "logs" else "")


def require(ok, message):
    if not ok:
        raise ValueError(message)



def local_context():
    """Reject TCP/SSH/npipe contexts before any daemon access or mutation.

    DOCKER_CONTEXT takes precedence over DOCKER_HOST in Docker. Reject an
    explicitly remote DOCKER_HOST too, even when a context would override it.
    """
    host = os.environ.get("DOCKER_HOST", "")
    if host and not host.startswith("unix:///"):
        raise ValueError("遠隔DOCKER_HOSTは対象外です。Linuxホスト自身のunix://ソケットを使います。")
    if host and not os.environ.get("DOCKER_CONTEXT"):
        endpoint = host
    else:
        endpoint = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").strip()
    require(endpoint.startswith("unix:///") and "\n" not in endpoint,
            "遠隔Docker contextは対象外です。Linuxホスト自身のunix://ソケットを使います。")
    # Even an explicit unix host must still reject a mock binary before setup/cleanup.
    executable = shutil.which("docker")
    require(executable and "mock" not in Path(executable).resolve().parts,
            "本物のdocker CLIが必要です。教材の模擬dockerは利用しません。")
    return endpoint


def state(root):
    data = json.loads((root / ".docker-fixture.json").read_text())
    expected = "dojo-" + data["token"]
    require(data["name"] == expected and data["image"] == expected + ":lab" and data["volume"] == expected + "-data",
            "実習資源名が専用の形式ではありません。")
    require(len(data["token"]) == 16 and all(c in "0123456789abcdef" for c in data["token"]), "実習tokenが不正です。")
    return data


def setup(root):
    # Read-only access check: no images, containers, or volumes are created here.
    endpoint = local_context()
    docker("info", "--format", "{{.ServerVersion}}")
    token = secrets.token_hex(8)
    data = {"token": token, "endpoint": endpoint, "name": "dojo-" + token, "image": "dojo-" + token + ":lab",
            "volume": "dojo-" + token + "-data", "record": "original-" + secrets.token_hex(10)}
    (root / ".docker-fixture.json").write_text(json.dumps(data, indent=2) + "\n")
    (root / ".dockerignore").write_text("*\n!Dockerfile\n!server.py\n")
    (root / "server.py").write_text('''import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
if os.environ.get('APP_MODE') != 'ready':
    raise SystemExit('configuration error: APP_MODE must be ready')
record = Path('/data/record.txt')
if not record.exists():
    record.write_text(os.environ['RECORD'])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        body = json.dumps({'record': record.read_text(), 'uid': os.getuid()}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
''')
    (root / "Dockerfile").write_text('''FROM python:3.12-alpine
WORKDIR /app
COPY server.py /app/server.py
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8080
CMD ["python", "-u", "/app/server.py"]
''')


def inspect(kind, name):
    return json.loads(docker(kind, "inspect", name))[0]


def owned(kind, name, token):
    details = inspect(kind, name)
    labels = details.get("Labels", {}) if kind == "volume" else details.get("Config", {}).get("Labels", {})
    require(labels and labels.get(LABEL) == token, "実習ラベルが違います。既存資源は変更しません。")
    return details


def check(root):
    data = state(root)
    require(local_context() == data["endpoint"], "setup時とDockerソケットが違います。元のcontextで再開します。")
    details = owned("container", data["name"], data["token"])
    image = owned("image", data["image"], data["token"])
    owned("volume", data["volume"], data["token"])
    require(details["State"]["Running"], "専用コンテナが稼働していません。logsを確認します。")
    require(details["Image"] == image["Id"], "今回ビルドした専用イメージを使用します。")
    require(details["Config"].get("User") == "10001:10001", "コンテナのアプリは非rootで実行します。")
    bindings = details["NetworkSettings"]["Ports"].get("8080/tcp", [])
    require(len(bindings) == 1 and bindings[0]["HostIp"] == "127.0.0.1", "公開先は127.0.0.1だけにします。")
    mounts = details.get("Mounts", [])
    require(any(m.get("Type") == "volume" and m.get("Name") == data["volume"] and m.get("Destination") == "/data" for m in mounts),
            "専用named volumeを/dataにマウントします。")
    first = (root / "first-container-id.txt").read_text().strip()
    require(len(first) == 64 and all(c in "0123456789abcdef" for c in first) and first != details["Id"], "一度停止・削除し、別コンテナでvolumeの保持を確認します。")
    expected_env = "RECORD=replacement-" + data["token"]
    require(expected_env in details["Config"].get("Env", []), "再作成時にRECORDを変更し、古いデータが保持されることを確認します。")
    actual = docker("exec", data["name"], "cat", "/data/record.txt").strip()
    require(actual == data["record"], "コンテナ再作成後に最初のvolumeデータが残っていません。")
    port = bindings[0]["HostPort"]
    response = subprocess.run(["curl", "--noproxy", "*", "--silent", "--show-error", "--fail", "--max-time", "5",
                               "http://127.0.0.1:" + port + "/health"], capture_output=True, text=True, timeout=8)
    require(response.returncode == 0, "ホストから公開ポートへHTTP接続できません。")
    require(json.loads(response.stdout) == {"record": data["record"], "uid": 10001}, "実HTTPの本文・実行ユーザーが違います。")
    require(json.loads((root / "health.json").read_text()) == json.loads(response.stdout), "curlの正常応答をhealth.jsonへ保存します。")
    require("configuration error: APP_MODE must be ready" in (root / "failure.log").read_text(), "故障したコンテナのログを保存して設定を修正します。")
    logs = docker("logs", data["name"])
    require("GET /health" in logs, "実コンテナのアクセスログに正常リクエストがありません。")
    require("GET /health" in (root / "service.log").read_text(), "稼働後のdocker logsもservice.logへ保存します。")


def cleanup(root):
    """Remove only exact resource names bearing this folder's random lab label."""
    data = state(root)
    require(local_context() == data["endpoint"], "setup時とDockerソケットが違います。元のcontextでcleanupします。")
    docker("info", "--format", "{{.ServerVersion}}")
    for name in (data["name"] + "-bad", data["name"]):
        probe = subprocess.run([shutil.which("docker") or "docker", "container", "inspect", name], capture_output=True, text=True, timeout=15)
        if probe.returncode == 0:
            owned("container", name, data["token"])
            docker("container", "rm", "-f", name)
    for kind, name in (("volume", data["volume"]), ("image", data["image"])):
        try:
            inspect(kind, name)
        except ValueError:
            continue
        owned(kind, name, data["token"])
        docker(kind, "rm", name)


SOLUTION = r'''set -euo pipefail
case "${DOCKER_HOST:-}" in ''|unix:///*) ;; *) echo 'Remote DOCKER_HOST is unsupported' >&2; exit 2;; esac
case "$(readlink -f "$(command -v docker)")" in */mock/*) echo 'Mock docker is unsupported' >&2; exit 2;; esac
if [ -n "${DOCKER_HOST:-}" ] && [ -z "${DOCKER_CONTEXT:-}" ]; then
  endpoint="$DOCKER_HOST"
else
  endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
fi
case "$endpoint" in unix:///*) ;; *) echo 'Remote Docker context is unsupported' >&2; exit 2;; esac
expected_endpoint=$(python3 -c 'import json; print(json.load(open(".docker-fixture.json"))["endpoint"])')
[ "$endpoint" = "$expected_endpoint" ] || { echo 'Docker endpoint changed since setup' >&2; exit 2; }
name=$(python3 -c 'import json; print(json.load(open(".docker-fixture.json"))["name"])')
token=$(python3 -c 'import json; print(json.load(open(".docker-fixture.json"))["token"])')
record=$(python3 -c 'import json; print(json.load(open(".docker-fixture.json"))["record"])')
image="$name:lab"
volume="$name-data"
label="org.linuxdojo.toolbox=$token"
# The first build may download python:3.12-alpine from Docker Hub.
docker build --label "$label" -t "$image" .
docker volume create --label "$label" "$volume"
# A deliberately broken configuration: inspect the real exit status and logs.
docker run -d --name "$name-bad" --label "$label" -e APP_MODE=broken "$image"
code=$(docker wait "$name-bad")
[ "$code" != 0 ]
docker logs "$name-bad" > failure.log 2>&1
docker rm "$name-bad"
# Correct environment, dedicated named volume and loopback-only dynamic port.
docker run -d --name "$name" --label "$label" -e APP_MODE=ready -e RECORD="$record" \
  --mount "type=volume,source=$volume,target=/data" -p 127.0.0.1::8080 "$image"
docker inspect -f '{{.Id}}' "$name" > first-container-id.txt
# Wait for initial record creation before stopping the first working container.
for i in {1..100}; do
  docker exec "$name" test -f /data/record.txt && break
  sleep 0.1
done
docker exec "$name" cat /data/record.txt
docker stop "$name"
docker rm "$name"
# A changed initialization value must not replace persistent data.
docker run -d --name "$name" --label "$label" -e APP_MODE=ready -e RECORD="replacement-$token" \
  --mount "type=volume,source=$volume,target=/data" -p 127.0.0.1::8080 "$image"
port=$(docker inspect -f '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}' "$name")
for i in {1..100}; do
  if curl --noproxy '*' --silent --show-error --fail --max-time 2 "http://127.0.0.1:$port/health" > health.json; then break; fi
  sleep 0.1
done
curl --noproxy '*' --silent --show-error --fail --max-time 3 "http://127.0.0.1:$port/health" > health.json
docker logs "$name" > service.log 2>&1
'''

TASK = '''Linuxホスト自身の本物のDocker Engineを使います（遠隔Docker contextは対象外）。
初回ビルドではpython:3.12-alpineのダウンロードが必要です。
Dockerfile/server.pyを読み、.docker-fixture.jsonの専用名・ラベルでimageとnamed volumeを作成。
1. APP_MODE=brokenで起動し、docker waitの非0終了とdocker logsをfailure.logへ記録。
2. APP_MODE=ready、RECORDに指定のrecordを設定、専用volumeを/dataへマウントして起動。
   ポート8080は -p 127.0.0.1::8080 でホストの動的ポートへ。アプリはUID10001で動作。
3. 最初の稼働コンテナIDをfirst-container-id.txtへ。データ生成を確認してstop→rm。
4. 同じvolumeで新コンテナを作り、RECORD=replacement-<token>に変更。
5. inspectで公開ポートを確認、curl /healthをhealth.jsonへ保存。最初のデータが残ることを確認。
6. docker logsをservice.logへ保存。checkが成功するまで最終コンテナは稼働させる。
終了後は専用container→volume→imageの順に削除します。教材CLIのcleanupが使える場合はそれを使用。
手動なら .docker-fixture.json のname/name-bad、volume、imageだけをinspectでラベル確認して削除。
無関係のコンテナやvolumeを巻き込むdocker system prune、docker volume pruneは使いません。
これはDocker Engineの導入・デーモン起動済み環境の実習です。導入自体は常用ガイドの公式手順へ。
'''

LABS = {"docker": {"title": "Dockerを構築・故障調査・再作成し、volumeの保持を確認する",
                   "tools": ["bash", "docker", "python3", "curl"],
                   "packages": [], "task": TASK, "setup": setup, "check": check,
                   "cleanup": cleanup, "solution": SOLUTION,
                   "wrong": ["printf '{}\\n' > health.json; printf 'configuration error: APP_MODE must be ready\\n' > failure.log"]}}
