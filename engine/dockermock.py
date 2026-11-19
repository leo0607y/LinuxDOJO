"""学習用の模擬 docker CLI（Docker 未導入/権限なし環境向けシミュレーションモード）。

本物の docker CLI と同じ書式のコマンド・出力・エラーメッセージをできるだけ再現する。
状態は $LQ_STATE/docker/state.json に保存される。
対応: run / ps / logs / exec / inspect / stop / start / restart / kill / rm / rmi / images / pull /
      build / port / top / system prune / container prune / image prune / volume ls / network ls /
      compose (up/down/ps/logs/stop/start/restart/config) / version / info
"""
import fnmatch
import hashlib
import json
import os
import random
import re
import shlex
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("LQ_STATE", "/tmp")) / "docker"

# ------------------------------------------------------------------ image catalog
NGINX_LOGS = """/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
/docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
/docker-entrypoint.sh: Configuration complete; ready for start up
{ts} [notice] 1#1: using the "epoll" event method
{ts} [notice] 1#1: nginx/1.27.2
{ts} [notice] 1#1: start worker processes
"""
DEBIAN_OS = 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nNAME="Debian GNU/Linux"\nVERSION_ID="12"\nID=debian\n'
ALPINE_OS = 'NAME="Alpine Linux"\nID=alpine\nVERSION_ID=3.20.3\nPRETTY_NAME="Alpine Linux v3.20"\n'
UBUNTU_OS = 'PRETTY_NAME="Ubuntu 24.04.1 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n'

CATALOG = {
    "nginx": {"kind": "server", "expose": ["80/tcp"], "cmd": ["nginx", "-g", "daemon off;"], "size": "192MB",
              "logs": NGINX_LOGS,
              "fs": {"/etc/os-release": DEBIAN_OS,
                     "/usr/share/nginx/html/index.html": "<!DOCTYPE html>\n<html><head><title>Welcome to nginx!</title></head>\n<body><h1>Welcome to nginx!</h1></body></html>\n",
                     "/etc/nginx/nginx.conf": "user  nginx;\nworker_processes  auto;\nevents { worker_connections 1024; }\nhttp { include /etc/nginx/conf.d/*.conf; }\n",
                     "/etc/nginx/conf.d/default.conf": "server {\n    listen       80;\n    location / { root /usr/share/nginx/html; index index.html; }\n}\n"}},
    "httpd": {"kind": "server", "expose": ["80/tcp"], "cmd": ["httpd-foreground"], "size": "148MB",
              "logs": "AH00558: httpd: Could not reliably determine the server's fully qualified domain name\n[mpm_event:notice] AH00489: Apache/2.4.62 (Unix) configured -- resuming normal operations\n",
              "fs": {"/etc/os-release": DEBIAN_OS, "/usr/local/apache2/htdocs/index.html": "<html><body><h1>It works!</h1></body></html>\n"}},
    "redis": {"kind": "server", "expose": ["6379/tcp"], "cmd": ["redis-server"], "size": "117MB",
              "logs": "1:C * oO0OoO0OoO0Oo Redis is starting oO0OoO0OoO0Oo\n1:M * Server initialized\n1:M * Ready to accept connections tcp\n",
              "fs": {"/etc/os-release": DEBIAN_OS}},
    "postgres": {"kind": "server", "expose": ["5432/tcp"], "cmd": ["postgres"], "size": "435MB",
                 "require_env": ["POSTGRES_PASSWORD"],
                 "fail_log": "Error: Database is uninitialized and superuser password is not specified.\n       You must specify POSTGRES_PASSWORD to a non-empty value for the\n       superuser. For example, \"-e POSTGRES_PASSWORD=password\" on \"docker run\".\n",
                 "logs": "PostgreSQL init process complete; ready for start up.\nLOG:  database system is ready to accept connections\n",
                 "fs": {"/etc/os-release": DEBIAN_OS}},
    "mysql": {"kind": "server", "expose": ["3306/tcp"], "cmd": ["mysqld"], "size": "586MB",
              "require_env": ["MYSQL_ROOT_PASSWORD"],
              "fail_log": "[ERROR] [Entrypoint]: Database is uninitialized and password option is not specified\n    You need to specify one of the following as an environment variable:\n    - MYSQL_ROOT_PASSWORD\n",
              "logs": "[Server] /usr/sbin/mysqld: ready for connections. port: 3306\n", "fs": {"/etc/os-release": DEBIAN_OS}},
    "alpine": {"kind": "os", "cmd": ["/bin/sh"], "size": "7.8MB", "fs": {"/etc/os-release": ALPINE_OS}},
    "busybox": {"kind": "os", "cmd": ["sh"], "size": "4.3MB", "fs": {"/etc/os-release": 'NAME="BusyBox"\n'}},
    "ubuntu": {"kind": "os", "cmd": ["/bin/bash"], "size": "78MB", "fs": {"/etc/os-release": UBUNTU_OS}},
    "debian": {"kind": "os", "cmd": ["bash"], "size": "117MB", "fs": {"/etc/os-release": DEBIAN_OS}},
    "python": {"kind": "os", "cmd": ["python3"], "size": "1.02GB", "fs": {"/etc/os-release": DEBIAN_OS}},
    "node": {"kind": "os", "cmd": ["node"], "size": "1.1GB", "fs": {"/etc/os-release": DEBIAN_OS}},
    "hello-world": {"kind": "oneshot", "cmd": ["/hello"], "size": "13.3kB", "libc": None,
                    "logs": "\nHello from Docker!\nThis message shows that your installation appears to be working correctly.\n"},
    "golang": {"kind": "os", "cmd": ["bash"], "size": "814MB", "variants": {"alpine": "247MB"},
               "env": {"GOPATH": "/go", "PATH": "/go/bin:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
               "fs": {"/etc/os-release": DEBIAN_OS, "/usr/local/go/bin/go": "\x7fELF go toolchain\n"}},
    "static-debian12": {"kind": "os", "cmd": [], "size": "1.99MB", "libc": None, "noshell": True,
                        "fs": {"/etc/os-release": 'PRETTY_NAME="Distroless"\n'}},
    "base-debian12": {"kind": "os", "cmd": [], "size": "20.7MB", "noshell": True,
                      "fs": {"/etc/os-release": 'PRETTY_NAME="Distroless"\n'}},
}
SIZE_HINT = {"slim": "131MB", "alpine": "57MB"}
MUSL = ("alpine", "busybox")
# ヘルスチェックのコマンドとして「そのイメージに入っている」とみなすもの
HEALTH_TOOLS = {"postgres": {"pg_isready", "psql"}, "redis": {"redis-cli"}, "mysql": {"mysqladmin", "mysql"},
                "nginx": {"curl"}, "httpd": {"curl"}, "alpine": {"wget", "nc"}, "busybox": {"wget", "nc"}}
COMMON_TOOLS = {"true", "false", "exit", "test", "[", "cat", "ls", "echo", "sh", "bash", "kill", "grep", "pgrep"}


def size_to_bytes(s):
    m = re.fullmatch(r"([\d.]+)\s*([kKMG]?B)", str(s).strip())
    if not m:
        return 0
    mul = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9}[m.group(2)]
    return int(float(m.group(1)) * mul)


def human_size(b):
    """docker と同じ 10 進単位・有効数字3桁（例: 7.8MB, 192MB, 1.02GB）。"""
    b = float(b)
    for unit, mul in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if b >= mul:
            return f"{b / mul:.3g}{unit}"
    return f"{int(b)}B"

NAMES_A = ["admiring", "brave", "clever", "dazzling", "eager", "focused", "gifted", "happy", "jolly", "keen",
           "lucid", "modest", "nifty", "quirky", "serene", "sharp", "trusting", "vibrant", "wizardly", "zen"]
NAMES_B = ["torvalds", "ritchie", "thompson", "hopper", "lovelace", "turing", "knuth", "babbage", "wozniak",
           "stallman", "pike", "kernighan", "hamilton", "liskov", "dijkstra", "matsumoto"]


def die(msg, code=1):
    sys.stderr.write(msg.rstrip("\n") + "\n")
    sys.exit(code)


# ------------------------------------------------------------------ state
def load():
    try:
        st = json.loads((STATE_DIR / "state.json").read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("containers", {})
    st.setdefault("images", {})
    st.setdefault("build_cache", {})
    if not st.get("networks"):
        st["networks"] = {n: {"id": hexid("net" + n), "driver": d, "created": time.time() - 86400 * 30, "builtin": True,
                              "subnet": "172.17.0.0/16" if n == "bridge" else "", "next": 2, "labels": {}}
                          for n, d in (("bridge", "bridge"), ("host", "host"), ("none", "null"))}
    if not st["images"]:
        for i, ref in enumerate(("nginx:latest", "alpine:latest", "python:3.12-slim", "redis:7")):
            _add_image(st, ref, created=time.time() - 86400 * (5 + 4 * i))
    return st


def save(st):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    os.replace(tmp, STATE_DIR / "state.json")


def norm_ref(ref):
    ref = ref.strip()
    for pre in ("docker.io/library/", "library/"):
        if ref.startswith(pre):
            ref = ref[len(pre):]
    last = ref.split("/")[-1]
    if ":" not in last and "@" not in last:
        ref += ":latest"
    return ref


def base_name(ref):
    r = norm_ref(ref).rsplit(":", 1)[0]
    return r.split("/")[-1]


def hexid(seed=None):
    return hashlib.sha256((seed or f"{time.time()}{random.random()}").encode()).hexdigest()


def _add_image(st, ref, **extra):
    ref = norm_ref(ref)
    cat = CATALOG.get(base_name(ref), {})
    tag = ref.rsplit(":", 1)[1]
    size = cat.get("size", "88MB")
    for k, v in SIZE_HINT.items():
        if k in tag:
            size = cat.get("variants", {}).get(k, v)
    libc = cat.get("libc", "glibc")
    if base_name(ref) in MUSL or "alpine" in tag:
        libc = "musl"
    img = {"id": hexid(ref), "created": time.time(), "size": size, "size_bytes": size_to_bytes(size),
           "cmd": cat.get("cmd", ["sh"]), "kind": cat.get("kind", "server"),
           "expose": cat.get("expose", []), "fs": dict(cat.get("fs", {})), "env": dict(cat.get("env", {})), "workdir": "/",
           "behavior": {}, "libc": libc, "noshell": cat.get("noshell", False)}
    img.update(extra)
    st["images"][ref] = img
    return img


def valid_ref(ref):
    return re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*(?::[\w][\w.-]{0,127})?", ref) is not None


def ensure_image(st, ref, quiet=True):
    ref_n = norm_ref(ref)
    if ref_n in st["images"]:
        return st["images"][ref_n]
    if not valid_ref(ref):
        die(f'docker: invalid reference format: repository name ({ref}) must be lowercase.\n'
            "See 'docker run --help'.", 125)
    if not quiet:
        tag = ref_n.rsplit(":", 1)[1]
        print(f"Unable to find image '{ref_n}' locally")
        print(f"{tag}: Pulling from library/{base_name(ref_n)}")
        print(f"{hexid(ref_n)[:12]}: Pull complete")
        print(f"Digest: sha256:{hexid(ref_n + 'd')}")
        print(f"Status: Downloaded newer image for {ref_n}")
    return _add_image(st, ref_n)


def find_container(st, key):
    if key in st["containers"]:
        return st["containers"][key]
    for c in st["containers"].values():
        if c["name"] == key or c["name"] == key.lstrip("/"):
            return c
    hits = [c for c in st["containers"].values() if c["id"].startswith(key)]
    if len(hits) == 1:
        return hits[0]
    return None


def net_ip(st, net):
    n = st["networks"].setdefault(net, {"id": hexid("net" + net), "driver": "bridge", "created": time.time(),
                                        "builtin": False, "subnet": "", "next": 2, "labels": {}})
    if not n.get("subnet"):
        k = sum(1 for x in st["networks"].values() if not x.get("builtin")) + 17
        n["subnet"] = f"172.{min(k, 31)}.0.0/16"
    base = n["subnet"].split(".0.0/")[0]
    ip = f"{base}.0.{n['next']}"
    n["next"] += 1
    return ip


def new_container(st, name, image, cmd, env, ports, mounts, labels, autoremove=False, workdir=None,
                  network=None, aliases=None, restart="no", healthcheck=None, links=None):
    cid = hexid()
    img = st["images"][norm_ref(image)]
    fs = dict(img.get("fs", {}))
    fs.setdefault("/etc/hostname", cid[:12] + "\n")
    full_env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    full_env.update(img.get("env", {}))
    full_env.update(env)
    net = network or "bridge"
    nets = {}
    if net != "none":
        nets[net] = {"ip": net_ip(st, net) if net != "host" else "", "aliases": list(aliases or [])}
    hc = healthcheck if healthcheck is not None else img.get("healthcheck")
    c = {"id": cid, "name": name, "image": image, "image_ref": norm_ref(image), "cmd": cmd or img.get("cmd", []),
         "user_cmd": bool(cmd), "created": time.time(), "started": time.time(), "finished": None,
         "status": "created", "exit_code": 0, "ports": ports, "mounts": mounts, "env": full_env,
         "labels": labels, "logs": "", "fs": fs, "autoremove": autoremove,
         "workdir": workdir or img.get("workdir", "/"),
         "ip": nets.get("bridge", {}).get("ip", "") or next((v["ip"] for v in nets.values()), ""),
         "networks": nets, "restart": restart or "no", "restart_count": 0, "healthcheck": hc or None,
         "links": dict(links or {}), "ready_at": 0}
    st["containers"][cid] = c
    return c


def restart_name(c):
    return (c.get("restart") or "no").split(":")[0]


def health_status(st, c):
    """None（ヘルスチェック無し）/ starting / healthy / unhealthy"""
    hc = c.get("healthcheck")
    if not hc or not hc.get("test") or hc["test"][0] == "NONE":
        return None
    if c["status"] != "running":
        return c.get("health_last") or "unhealthy"
    ok, _ = health_eval(st, c)
    if not ok:
        return "unhealthy"
    if time.time() < c.get("ready_at", 0):
        return "starting"
    return "healthy"


def health_eval(st, c):
    """(成功?, 出力) — テストコマンドがそのイメージで実行できるかを簡易判定する。"""
    test = c["healthcheck"]["test"]
    if test[0] == "CMD-SHELL":
        line = " ".join(test[1:])
        words = shlex.split(line.split("||")[0].split("&&")[0]) if line.strip() else []
    elif test[0] == "CMD":
        words = test[1:]
    else:
        words = shlex.split(" ".join(test))
    if not words:
        return False, "empty healthcheck"
    prog = words[0].split("/")[-1]
    base = base_name(c["image_ref"])
    img = st["images"].get(c["image_ref"], {})
    tools = set(COMMON_TOOLS) | HEALTH_TOOLS.get(base, set()) | set((img.get("behavior") or {}).get("tools", []))
    if img.get("noshell") and test[0] == "CMD-SHELL":
        return False, 'OCI runtime exec failed: exec failed: unable to start container process: exec: "/bin/sh": stat /bin/sh: no such file or directory: unknown'
    if prog not in tools:
        if test[0] == "CMD-SHELL":
            return False, f"/bin/sh: 1: {prog}: not found"
        return False, f'OCI runtime exec failed: exec failed: unable to start container process: exec: "{prog}": executable file not found in $PATH: unknown'
    if prog in ("curl", "wget"):
        url = next((w for w in words if "://" in w or w.startswith(("localhost", "127.0.0.1"))), "")
        m = re.match(r"(?:\w+://)?([^/:]+)(?::(\d+))?", url)
        if m:
            port = m.group(2) or "80"
            listen = [p.split("/")[0] for p in (img.get("expose") or [])] or ["80"]
            if m.group(1) in ("localhost", "127.0.0.1") and port not in listen:
                return False, f"curl: (7) Failed to connect to localhost port {port} after 0 ms: Couldn't connect to server"
    if prog == "false" or (prog == "exit" and words[1:2] != ["0"]):
        return False, ""
    if prog == "pg_isready":
        if time.time() < c.get("ready_at", 0):
            return False, "/var/run/postgresql:5432 - rejecting connections"
        return True, "/var/run/postgresql:5432 - accepting connections"
    return True, ""


def normalize(c, st=None):
    return {"id": c["id"][:12], "name": c["name"], "image": c["image"], "running": c["status"] == "running",
            "status": c["status"], "exit_code": c["exit_code"], "ports": dict(c["ports"]),
            "mounts": [{"src": m["src"], "dst": m["dst"]} for m in c["mounts"]], "env": dict(c["env"]),
            "labels": dict(c["labels"]), "cmd": list(c["cmd"]), "autoremove": c.get("autoremove", False),
            "networks": sorted((c.get("networks") or {"bridge": {}}).keys()),
            "restart_policy": restart_name(c), "restart_count": c.get("restart_count", 0),
            "health": health_status(st, c) if st is not None else None,
            "healthcheck": c.get("healthcheck")}


def ago(ts):
    s = int(time.time() - ts)
    if s < 2:
        return "Less than a second"
    if s < 60:
        return f"{s} seconds"
    if s < 3600:
        m = s // 60
        return "About a minute" if m == 1 else f"{m} minutes"
    if s < 86400:
        h = s // 3600
        return "About an hour" if h == 1 else f"{h} hours"
    return f"{s // 86400} days"


def status_text(c, st=None):
    if c["status"] == "running":
        h = health_status(st, c) if st is not None else None
        suffix = {"starting": " (health: starting)", "healthy": " (healthy)", "unhealthy": " (unhealthy)"}.get(h, "")
        return f"Up {ago(c['started'])}{suffix}"
    if c["status"] == "created":
        return "Created"
    if c["status"] == "restarting":
        return f"Restarting ({c['exit_code']}) {ago(c['finished'] or c['created'])} ago"
    return f"Exited ({c['exit_code']}) {ago(c['finished'] or c['created'])} ago"


def ports_text(c):
    out = []
    for cport, hport in c["ports"].items():
        if c["status"] == "running" and hport:
            out.append(f"0.0.0.0:{hport}->{cport}")
    img_expose = []
    return ", ".join(out + img_expose)


def resolve(st, c, host):
    """コンテナ c から見た名前解決。ユーザー定義ネットワーク上の稼働中コンテナ名/エイリアス、--link のみ解決できる
    （デフォルトの bridge ネットワークには組み込み DNS が無い＝本物と同じ）。"""
    host = host.strip().lower()
    if host in ("localhost", "127.0.0.1", c["name"].lower(), c["id"][:12]):
        return c
    for alias, target in (c.get("links") or {}).items():
        if host == alias.lower():
            o = find_container(st, target)
            if o and o["status"] == "running":
                return o
    for net in (c.get("networks") or {}):
        if net in ("bridge", "host", "none"):
            continue
        for o in st["containers"].values():
            if o["id"] == c["id"] or o["status"] != "running" or net not in (o.get("networks") or {}):
                continue
            names = {o["name"].lower(), o["id"][:12]} | {a.lower() for a in o["networks"][net].get("aliases", [])}
            if host in names:
                return o
    return None


def ip_of(o, c=None):
    nets = o.get("networks") or {}
    if c is not None:
        for n in nets:
            if n in (c.get("networks") or {}) and nets[n].get("ip"):
                return nets[n]["ip"]
    return next((v["ip"] for v in nets.values() if v.get("ip")), o.get("ip", ""))


# ------------------------------------------------------------------ mini shell (exec / run -it)
class MiniShell:
    """コンテナ内の簡易シェル。よく使う閲覧系コマンドのみ再現する。"""

    def __init__(self, st, c):
        self.st, self.c = st, c
        self.cwd = c.get("workdir") or "/"
        self.crash = None   # kill 1 などでメインプロセスが落ちた場合のシグナル名

    def _net_cmd(self, cmd, args):
        target = [a for a in args if not a.startswith("-")]
        if cmd == "kill":
            sig = "TERM"
            for a in args:
                if a.startswith("-") and len(a) > 1:
                    sig = {"9": "KILL", "15": "TERM", "2": "INT", "1": "HUP"}.get(a[1:].upper().replace("SIG", "").replace("S ", ""), a[1:].upper().replace("SIG", ""))
            pids = [a for a in target if a.isdigit()]
            if not pids:
                return "kill: usage: kill [-s sigspec | -n signum | -sigspec] pid | jobspec ... or kill -l [sigspec]", 2
            if pids[0] == "1":
                self.crash = sig
                return "", 0
            return f"sh: can't kill pid {pids[0]}: No such process", 1
        if cmd in ("pg_isready",):
            if base_name(self.c["image_ref"]) != "postgres":
                return "sh: pg_isready: not found", 127
            return "/var/run/postgresql:5432 - accepting connections", 0
        if cmd in ("curl", "wget"):
            url = next((a for a in target if "://" in a or "." in a or ":" in a or a == "localhost"), "")
            if not url:
                return f"{cmd}: no URL specified!" if cmd == "curl" else "BusyBox wget: missing URL", 2
            m = re.match(r"(?:\w+://)?([^/:]+)(?::(\d+))?", url)
            host = m.group(1) if m else url
            o = resolve(self.st, self.c, host)
            if o is None and not re.fullmatch(r"[\d.]+", host):
                return (f"curl: (6) Could not resolve host: {host}" if cmd == "curl" else f"wget: bad address '{host}'"), 6
            port = (m.group(2) if m else None) or "80"
            image = self.st["images"].get(o["image_ref"], {}) if o else {}
            listening = {p.split("/")[0] for p in image.get("expose", [])}
            if o is None or o["status"] != "running" or port not in listening:
                return f"{cmd}: (7) Failed to connect to {host} port {port}: Connection refused", 7
            return f"[LinuxQuest 模擬] {host} ({ip_of(o, self.c)}) に接続できました（HTTP 200 OK）", 0
        if not target:
            return f"{cmd}: missing host operand" if cmd != "getent" else "", 2
        host = target[-1] if cmd != "getent" else (target[1] if len(target) > 1 else "")
        if cmd == "getent" and target[0] != "hosts":
            return "", 2
        o = resolve(self.st, self.c, host)
        if o is None:
            if cmd == "ping":
                return f"ping: bad address '{host}'", 1
            if cmd == "nslookup":
                return f"Server:\t\t127.0.0.11\nAddress:\t127.0.0.11:53\n\n** server can't find {host}: NXDOMAIN", 1
            return "", 2
        ip = ip_of(o, self.c)
        if cmd == "ping":
            return (f"PING {host} ({ip}): 56 data bytes\n64 bytes from {ip}: seq=0 ttl=64 time=0.081 ms\n"
                    f"\n--- {host} ping statistics ---\n1 packets transmitted, 1 packets received, 0% packet loss"), 0
        if cmd == "nslookup":
            return f"Server:\t\t127.0.0.11\nAddress:\t127.0.0.11:53\n\nNon-authoritative answer:\nName:\t{host}\nAddress: {ip}", 0
        return f"{ip:<15} {host}", 0

    def _abs(self, p):
        if not p.startswith("/"):
            p = (self.cwd.rstrip("/") + "/" + p)
        parts = []
        for seg in p.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(seg)
        return "/" + "/".join(parts)

    def _mount_for(self, p):
        for m in sorted(self.c["mounts"], key=lambda m: -len(m["dst"])):
            if m.get("type") == "bind" and (p == m["dst"] or p.startswith(m["dst"].rstrip("/") + "/")):
                return m
        return None

    def _read(self, p):
        m = self._mount_for(p)
        if m:
            hp = Path(m["src"]) / p[len(m["dst"]):].lstrip("/")
            if hp.is_file():
                return hp.read_text(errors="replace")
            return None
        return self.c["fs"].get(p)

    def _isdir(self, p):
        if p == "/":
            return True
        m = self._mount_for(p)
        if m:
            return (Path(m["src"]) / p[len(m["dst"]):].lstrip("/")).is_dir()
        pre = p.rstrip("/") + "/"
        return any(k.startswith(pre) for k in self.c["fs"]) or any(
            mm["dst"].startswith(pre) or mm["dst"] == p for mm in self.c["mounts"])

    def _list(self, p):
        m = self._mount_for(p)
        names = set()
        if m:
            hp = Path(m["src"]) / p[len(m["dst"]):].lstrip("/")
            if hp.is_dir():
                names |= {x.name for x in hp.iterdir()}
            return sorted(names)
        pre = p.rstrip("/") + "/"
        for k in list(self.c["fs"]) + [mm["dst"] for mm in self.c["mounts"]]:
            if k.startswith(pre):
                names.add(k[len(pre):].split("/")[0])
        if p == "/":
            names |= {"bin", "dev", "etc", "home", "proc", "root", "tmp", "usr", "var"}
        return sorted(n for n in names if n)

    def run_line(self, line):
        """1行を実行。(出力, 終了コード, exitフラグ) を返す。"; " と "&&" に簡易対応。"""
        out, code = [], 0
        for seg in re.split(r"\s*;\s*", line):
            for part in re.split(r"\s*&&\s*", seg):
                if not part.strip():
                    continue
                o, code, ex = self.run(part)
                if o:
                    out.append(o)
                if ex:
                    return "\n".join(out), code, True
                if code != 0:
                    break
        return "\n".join(out), code, False

    def run(self, cmdline):
        redirect = None
        m = re.match(r"(.*?)\s*>\s*(\S+)\s*$", cmdline)
        if m:
            cmdline, redirect = m.group(1), m.group(2)
        try:
            argv = shlex.split(cmdline)
        except ValueError as e:
            return f"sh: syntax error: {e}", 2, False
        if not argv:
            return "", 0, False
        out, code, ex = self._dispatch(argv)
        if redirect is not None:
            self.c["fs"][self._abs(redirect)] = (out + "\n") if out else ""
            out = ""
        return out, code, ex

    def _dispatch(self, argv):
        cmd, args = argv[0], argv[1:]
        cmd = cmd.split("/")[-1]
        env = self.c["env"]
        args = [env.get(a[1:], "") if a.startswith("$") else a for a in args]
        if cmd in ("exit", "logout"):
            return "", int(args[0]) if args and args[0].isdigit() else 0, True
        if cmd in ("sh", "bash", "ash") and args[:1] == ["-c"] and len(args) > 1:
            out, code, _ = self.run_line(args[1])
            return out, code, False
        if cmd == "pwd":
            return self.cwd, 0, False
        if cmd == "cd":
            p = self._abs(args[0] if args else "/root")
            if not self._isdir(p):
                return f"sh: cd: can't cd to {args[0] if args else '~'}: No such file or directory", 2, False
            self.cwd = p
            return "", 0, False
        if cmd == "ls":
            long_ = any(a.startswith("-") and "l" in a for a in args)
            paths = [a for a in args if not a.startswith("-")] or [self.cwd]
            out = []
            for a in paths:
                p = self._abs(a)
                if self._read(p) is not None:
                    out.append(a)
                    continue
                if not self._isdir(p):
                    return f"ls: {a}: No such file or directory", 1, False
                names = self._list(p)
                if long_:
                    for n in names:
                        full = p.rstrip("/") + "/" + n
                        isd = self._isdir(full)
                        size = len(self._read(full) or "") if not isd else 4096
                        out.append(f"{'d' if isd else '-'}rw{'x' if isd else '-'}r-{'x' if isd else '-'}r-{'x' if isd else '-'}    1 root     root    {size:>8} Nov 19 09:00 {n}")
                else:
                    out.append("  ".join(names))
            return "\n".join(out), 0, False
        if cmd in ("cat", "head", "tail", "more", "less"):
            files = [a for a in args if not a.startswith("-")]
            if not files:
                return "", 0, False
            out = []
            for a in files:
                t = self._read(self._abs(a))
                if t is None:
                    if self._isdir(self._abs(a)):
                        return f"{cmd}: read error: Is a directory", 1, False
                    return f"{cmd}: can't open '{a}': No such file or directory", 1, False
                out.append(t.rstrip("\n"))
            return "\n".join(out), 0, False
        if cmd == "echo":
            return " ".join(args), 0, False
        if cmd in ("env", "printenv"):
            if cmd == "printenv" and args:
                v = env.get(args[0])
                return (v, 0, False) if v is not None else ("", 1, False)
            return "\n".join(f"{k}={v}" for k, v in env.items()), 0, False
        if cmd == "hostname":
            return self.c["id"][:12], 0, False
        if cmd == "whoami":
            return "root", 0, False
        if cmd == "id":
            return "uid=0(root) gid=0(root) groups=0(root)", 0, False
        if cmd == "uname":
            return ("Linux " + self.c["id"][:12] + " 6.8.0 #1 SMP x86_64 Linux") if "-a" in args else "Linux", 0, False
        if cmd == "date":
            return time.strftime("%a %b %d %H:%M:%S UTC %Y", time.gmtime()), 0, False
        if cmd == "ps":
            lines = ["PID   USER     TIME  COMMAND", f"    1 root      0:00 {' '.join(self.c['cmd'])}",
                     "   12 root      0:00 sh", "   18 root      0:00 ps"]
            return "\n".join(lines), 0, False
        if cmd == "touch":
            for a in args:
                self.c["fs"].setdefault(self._abs(a), "")
            return "", 0, False
        if cmd == "mkdir":
            for a in args:
                if not a.startswith("-"):
                    self.c["fs"][self._abs(a).rstrip("/") + "/.keep"] = ""
            return "", 0, False
        if cmd in ("sleep", "true", ":"):
            return "", 0, False
        if cmd == "false":
            return "", 1, False
        if cmd in ("ping", "nslookup", "getent", "curl", "wget", "kill", "pg_isready"):
            o, code = self._net_cmd(cmd, args)
            return o, code, False
        if cmd in ("apt", "apt-get", "apk", "pip", "pip3", "yum", "dnf", "vi", "vim", "nano",
                   "python", "python3", "node", "nginx", "top"):
            return f"[LinuxQuest 模擬環境] `{cmd}` はシミュレーションモードでは実行されません（本物の Docker では実行できます）", 0, False
        if cmd == "help":
            return "模擬シェルで使えるコマンド: ls cat head tail cd pwd echo env printenv hostname whoami id ps uname date touch mkdir exit", 0, False
        return f"sh: {cmd}: not found", 127, False

    def interactive(self):
        prompt_ch = "#"
        host = self.c["id"][:12]
        print("\x1b[2m[LinuxQuest 模擬コンテナシェル] help で使えるコマンド一覧、exit で抜けます\x1b[0m")
        code = 0
        while True:
            try:
                if base_name(self.c["image_ref"]) in ("alpine", "busybox"):
                    line = input(f"{self.cwd} {prompt_ch} ")
                else:
                    line = input(f"root@{host}:{self.cwd}{prompt_ch} ")
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            out, code, ex = self.run_line(line)
            if out:
                print(out)
            if ex:
                break
        return code


# ------------------------------------------------------------------ container lifecycle
def evaluate_start(st, c, interactive=False, attach=False):
    """コンテナ起動時の振る舞いを決める（イメージの種類・環境変数・コマンドに応じて）。"""
    img = st["images"].get(c["image_ref"], {})
    cat = CATALOG.get(base_name(c["image_ref"]), {})
    beh = dict(cat)
    beh.update(img.get("behavior") or {})
    kind = img.get("kind", "server")
    cmd = c["cmd"]
    c["started"] = time.time()
    c["finished"] = None
    c["ready_at"] = time.time() + float(beh.get("init_secs", 0))
    ts = time.strftime("%Y/%m/%d %H:%M:%S")

    def exited(code, logs_add=""):
        c["status"] = "exited"
        c["exit_code"] = code
        c["finished"] = time.time()
        c["logs"] += logs_add
        pol = restart_name(c)
        if pol in ("always", "unless-stopped") or (pol == "on-failure" and code != 0):
            c["status"] = "restarting"   # 再起動ポリシーにより再起動を繰り返している状態
            c["restart_count"] = c.get("restart_count", 0) + 1

    if img.get("has_elf"):
        bad = exec_problem(img, cmd)
        if bad:
            exited(bad[0], bad[1])
            return c["logs"]

    shellish = bool(cmd) and cmd[0].split("/")[-1] in ("sh", "bash", "ash") and len(cmd) == 1
    if c["user_cmd"] or kind in ("os", "oneshot"):
        if shellish and interactive:
            c["status"] = "running"
            save(st)
            sh = MiniShell(st, c)
            code = sh.interactive()
            st2 = load()
            c2 = st2["containers"].get(c["id"])
            if c2 is not None:
                c2["fs"] = c["fs"]
                c2["status"], c2["exit_code"], c2["finished"] = "exited", code, time.time()
                st["containers"][c["id"]] = c2
            return ""
        if shellish:
            exited(0)
            return ""
        if cmd and cmd[0] in ("sleep", "tail") or (cmd and " ".join(cmd).startswith("sh -c") and "sleep" in " ".join(cmd)):
            out = ""
            if cmd[0] in ("sh", "bash"):
                pre = " ".join(cmd[2:]).split("sleep")[0]
                out, _, _ = MiniShell(st, c).run_line(pre.rstrip("; &"))
                if out:
                    c["logs"] += out + "\n"
            c["status"] = "running"
            return out
        if kind == "oneshot" and not c["user_cmd"]:
            exited(0, beh.get("logs", ""))
            return beh.get("logs", "")
        if cmd and cmd[0].split("/")[-1] in ("python", "python3", "node") and len(cmd) == 1:
            exited(0)
            return ""
        out, code, _ = MiniShell(st, c).run_line(shlex.join(cmd) if not (cmd[0] in ("sh", "bash") and cmd[1:2] == ["-c"]) else cmd[2] if len(cmd) > 2 else "")
        exited(code, out + ("\n" if out else ""))
        return out
    # server kind
    missing = [e for e in beh.get("require_env", []) if not c["env"].get(e)]
    if missing:
        exited(beh.get("fail_code", 1), beh.get("fail_log", f"FATAL: {missing[0]} is not set\n").format(ts=ts, missing=missing[0]))
        return c["logs"]
    want_port = beh.get("must_publish")
    if want_port and want_port not in c["ports"]:
        pass  # ポート違いでも起動はする（外から繋がらないだけ）— check 側で判定
    nh = beh.get("needs_host_env")
    if nh:
        host = c["env"].get(nh, "")
        o = resolve(st, c, host) if host else None
        if o is None:
            exited(1, beh.get("boot_log", "").format(host=host) + beh.get("dns_fail_log", "FATAL: could not resolve {host}\n").format(host=host))
            return c["logs"]
        if beh.get("needs_ready") and time.time() < o.get("ready_at", 0):
            exited(1, beh.get("boot_log", "").format(host=host) + beh.get("notready_log", "FATAL: connection refused ({host})\n").format(host=host))
            return c["logs"]
    c["status"] = "running"
    c["logs"] += beh.get("logs", f"[{ts}] {base_name(c['image_ref'])}: started\n").format(ts=ts, **{k: v for k, v in c["env"].items() if k.isidentifier()})
    return c["logs"]


def exec_problem(img, cmd):
    """ビルドした Go バイナリが実行できるか（動的リンクの libc がイメージに無い等）。問題があれば (code, log)。"""
    if not cmd:
        return 127, "docker: Error response from daemon: no command specified\n"
    fs = img.get("fs", {})
    has_shell = not img.get("noshell") and img.get("libc") is not None
    prog = cmd[0]
    if prog.split("/")[-1] in ("sh", "bash") and cmd[1:2] == ["-c"]:
        if not has_shell:
            return 127, f'exec {prog}: no such file or directory\n'
        inner = shlex.split(cmd[2]) if len(cmd) > 2 else []
        if not inner:
            return None
        prog = inner[0]
    if prog.startswith("/"):
        cands = [os.path.normpath(prog)]
    elif "/" in prog:
        cands = [os.path.normpath((img.get("workdir") or "/").rstrip("/") + "/" + prog)]
    else:
        path = (img.get("env") or {}).get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        cands = [d.rstrip("/") + "/" + prog for d in path.split(":")]
    hit = next((p for p in cands if p in fs), None)
    if hit is None:
        if prog.split("/")[-1] in ("sh", "bash", "ash", "echo", "cat", "ls", "sleep") and has_shell:
            return None
        return 127, (f'docker: Error response from daemon: failed to create task for container: failed to create shim task: '
                     f'OCI runtime create failed: runc create failed: unable to start container process: '
                     f'exec: "{prog}": {"stat " + prog + ": no such file or directory" if "/" in prog else "executable file not found in $PATH"}: unknown\n')
    data = fs[hit]
    m = re.search(r"libc=(\w+)", data) if data.startswith("\x7fELF") else None
    need = m.group(1) if m else "static"
    if need != "static" and need != img.get("libc"):
        return 255, f"exec {hit}: no such file or directory\n"
    return None


def parse_port(spec):
    parts = spec.split(":")
    proto = "tcp"
    if "/" in parts[-1]:
        parts[-1], proto = parts[-1].split("/", 1)
    if len(parts) == 1:
        return f"{parts[0]}/{proto}", str(random.randint(32768, 60999))
    if len(parts) == 2:
        return f"{parts[1]}/{proto}", parts[0]
    return f"{parts[2]}/{proto}", parts[1]


def parse_volume(spec, cwd):
    parts = spec.split(":")
    if len(parts) < 2:
        return {"type": "volume", "src": f"/var/lib/docker/volumes/{hexid()[:16]}/_data", "dst": parts[0], "name": hexid()[:16]}
    src, dst = parts[0], parts[1]
    if src.startswith(("/", "./", "../", "~")) or src in (".", ".."):
        src = os.path.abspath(os.path.expanduser(src if src.startswith(("/", "~")) else os.path.join(cwd, src)))
        return {"type": "bind", "src": src, "dst": dst}
    return {"type": "volume", "src": f"/var/lib/docker/volumes/{src}/_data", "dst": dst, "name": src}


def check_port_conflict(st, ports, exclude=None):
    for cport, hport in ports.items():
        for o in st["containers"].values():
            if o["id"] != exclude and o["status"] == "running" and hport and hport in o["ports"].values():
                return hport
    return None


# ------------------------------------------------------------------ commands
def parse_flags(args, spec_with_value, spec_bool):
    """docker 風のオプション解析。(opts, rest) を返す。最初の非オプションで停止。"""
    opts, i = {}, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a.startswith("--"):
            key, _, val = a[2:].partition("=")
            if key in spec_with_value:
                if not _:
                    i += 1
                    if i >= len(args):
                        die(f"flag needs an argument: --{key}", 125)
                    val = args[i]
                opts.setdefault(key, []).append(val)
            elif key in spec_bool:
                opts[key] = True
            else:
                die(f"unknown flag: --{key}\nSee 'docker --help'.", 125)
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            j = 1
            while j < len(a):
                ch = a[j]
                if ch in spec_with_value:
                    val = a[j + 1:]
                    if not val:
                        i += 1
                        if i >= len(args):
                            die(f"flag needs an argument: '{ch}' in -{ch}", 125)
                        val = args[i]
                    opts.setdefault(spec_with_value[ch], []).append(val)
                    break
                if ch in spec_bool:
                    opts[spec_bool[ch]] = True
                else:
                    die(f"unknown shorthand flag: '{ch}' in {a}\nSee 'docker --help'.", 125)
                j += 1
            i += 1
            continue
        break
    return opts, args[i:]


RUN_VAL = {"name": "name", "p": "publish", "publish": "publish", "v": "volume", "volume": "volume", "e": "env",
           "env": "env", "l": "label", "label": "label", "w": "workdir", "workdir": "workdir", "network": "network",
           "restart": "restart", "env-file": "env-file", "u": "user", "user": "user", "entrypoint": "entrypoint",
           "hostname": "hostname", "h": "hostname", "memory": "memory", "m": "memory", "cpus": "cpus",
           "platform": "platform", "mount": "mount", "net": "network", "network-alias": "network-alias",
           "alias": "network-alias", "link": "link", "health-cmd": "health-cmd", "health-interval": "health-interval",
           "health-retries": "health-retries", "health-timeout": "health-timeout",
           "health-start-period": "health-start-period"}
RUN_BOOL = {"d": "detach", "detach": "detach", "i": "interactive", "interactive": "interactive", "t": "tty",
            "tty": "tty", "rm": "rm", "P": "publish-all", "publish-all": "publish-all", "privileged": "privileged",
            "init": "init", "no-healthcheck": "no-healthcheck"}
RESTART_RE = re.compile(r"(no|always|unless-stopped|on-failure(:\d+)?)")


def _split_spec(spec):
    vals = {k: k for k in spec if len(k) > 1}
    vals.update({k: v for k, v in spec.items()})
    return vals


def cmd_run(args, from_compose=None):
    sv = {k: v for k, v in RUN_VAL.items() if len(k) == 1}
    sv.update({k: v for k, v in RUN_VAL.items() if len(k) > 1})
    sb = {k: v for k, v in RUN_BOOL.items()}
    opts, rest = parse_flags(args, sv, sb)
    if not rest:
        die('"docker run" requires at least 1 argument.\nSee \'docker run --help\'.\n\nUsage:  docker run [OPTIONS] IMAGE [COMMAND] [ARG...]', 1)
    image, cmd = rest[0], rest[1:]
    st = load()
    name = (opts.get("name") or [None])[-1]
    if name:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
            die(f'docker: Error response from daemon: Invalid container name ({name}), only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed.', 125)
        o = find_container(st, name)
        if o and o["name"] == name:
            die(f'docker: Error response from daemon: Conflict. The container name "/{name}" is already in use by container "{o["id"]}". You have to remove (or rename) that container to be able to reuse that name.\nSee \'docker run --help\'.', 125)
    else:
        name = f"{random.choice(NAMES_A)}_{random.choice(NAMES_B)}"
    ensure_image(st, image, quiet=False)
    env = {}
    for e in opts.get("env", []):
        k, eq, v = e.partition("=")
        env[k] = v if eq else os.environ.get(k, "")
    for f in opts.get("env-file", []):
        try:
            for ln in Path(f).read_text().splitlines():
                if ln.strip() and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    env[k.strip()] = v.strip()
        except OSError:
            die(f"docker: open {f}: no such file or directory.", 125)
    ports = {}
    for p in opts.get("publish", []):
        cport, hport = parse_port(p)
        ports[cport] = hport
    if opts.get("publish-all"):
        for cport in st["images"][norm_ref(image)].get("expose", []):
            ports[cport] = str(random.randint(32768, 60999))
    mounts = [parse_volume(v, os.getcwd()) for v in opts.get("volume", [])]
    for m in mounts:
        if m["type"] == "bind" and not os.path.exists(m["src"]):
            os.makedirs(m["src"], exist_ok=True)  # 本物の docker もホスト側にディレクトリを自動作成する
    labels = {}
    for lb in opts.get("label", []):
        k, _, v = lb.partition("=")
        labels[k] = v
    if from_compose:
        labels.update(from_compose)
    restart = (opts.get("restart") or ["no"])[-1]
    if not RESTART_RE.fullmatch(restart):
        die(f"docker: invalid restart policy format: {restart}\nSee 'docker run --help'.", 125)
    if restart != "no" and opts.get("rm"):
        die("docker: Conflicting options: --restart and --rm.\nSee 'docker run --help'.", 125)
    network = (opts.get("network") or [None])[-1]
    if network and network not in st["networks"]:
        die(f"docker: Error response from daemon: network {network} not found.\nSee 'docker run --help'.", 125)
    aliases = opts.get("network-alias", [])
    if aliases and (not network or network in ("bridge", "host", "none")):
        die("docker: Error response from daemon: network-scoped alias is supported only for containers in user defined networks.", 125)
    links = {}
    for lk in opts.get("link", []):
        tgt, _, alias = lk.partition(":")
        if not find_container(st, tgt):
            die(f"docker: Error response from daemon: could not get container for {tgt}: No such container: {tgt}.", 125)
        if network and network not in ("bridge",):
            pass
        links[alias or tgt] = tgt
    hc = None
    if opts.get("no-healthcheck"):
        hc = {"test": ["NONE"]}
    elif opts.get("health-cmd"):
        hc = {"test": ["CMD-SHELL", opts["health-cmd"][-1]], "interval": (opts.get("health-interval") or ["30s"])[-1],
              "retries": (opts.get("health-retries") or ["3"])[-1]}
    conflict = check_port_conflict(st, ports)
    c = new_container(st, name, image, cmd, env, ports, mounts, labels, autoremove=bool(opts.get("rm")),
                      workdir=(opts.get("workdir") or [None])[-1], network=network, aliases=aliases,
                      restart=restart, healthcheck=hc, links=links)
    if conflict:
        c["status"] = "created"
        save(st)
        die(f"docker: Error response from daemon: driver failed programming external connectivity on endpoint {name} ({c['id'][:12]}): Bind for 0.0.0.0:{conflict} failed: port is already allocated.", 125)
    interactive = bool(opts.get("interactive") and opts.get("tty"))
    if interactive and not sys.stdin.isatty():
        interactive = False
    detach = bool(opts.get("detach"))
    out = evaluate_start(st, c, interactive=interactive and not detach)
    if c["exit_code"] == 127 and c["logs"].startswith("docker: Error response"):
        msg = c["logs"]
        c["status"], c["logs"], c["restart_count"] = "created", "", 0
        if c.get("autoremove"):
            st["containers"].pop(c["id"], None)
        save(st)
        die(msg, 127)
    if c["status"] == "exited" and c.get("autoremove"):
        st["containers"].pop(c["id"], None)
    save(st)
    if detach:
        print(c["id"])
        return 0
    if interactive:
        return c["exit_code"]
    if c["status"] == "running":
        sys.stdout.write(c["logs"])
        print("\x1b[2m[LinuxQuest 模擬] 本物の Docker ならここでフォアグラウンドに張り付き、Ctrl+C でコンテナが停止します。\n"
              "                 Ctrl+C を押したものとして停止しました。バックグラウンドで動かすには -d を付けましょう。\x1b[0m")
        st = load()
        cc = st["containers"].get(c["id"])
        if cc:
            cc["status"], cc["exit_code"], cc["finished"] = "exited", 0, time.time()
            if cc.get("autoremove"):
                st["containers"].pop(c["id"], None)
        save(st)
        return 0
    if out:
        print(out.rstrip("\n"))
    else:
        sys.stdout.write(c["logs"] if not out else "")
    return c["exit_code"]


def match_filters(c, filters):
    for f in filters:
        k, _, v = f.partition("=")
        if k == "status" and c["status"] != v:
            return False
        if k == "name" and not re.search(v.replace("^/", "^"), c["name"]):
            return False
        if k == "label":
            lk, eq, lv = v.partition("=")
            if lk not in c["labels"] or (eq and c["labels"][lk] != lv):
                return False
        if k == "ancestor" and base_name(c["image"]) != base_name(v) and norm_ref(c["image"]) != norm_ref(v):
            return False
        if k == "id" and not c["id"].startswith(v):
            return False
        if k == "exited" and not (c["status"] == "exited" and str(c["exit_code"]) == v):
            return False
        if k == "network" and v not in (c.get("networks") or {}):
            return False
    return True


def go_format(tmpl, obj):
    def ev(expr):
        expr = expr.strip()
        as_json = False
        if expr.startswith("json "):
            as_json, expr = True, expr[5:].strip()
        if expr == ".":
            val = obj
        else:
            val = obj
            for part in expr.lstrip(".").split("."):
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
        if as_json:
            return json.dumps(val, ensure_ascii=False)
        if isinstance(val, dict):
            return "map[" + " ".join(f"{k}:{v}" for k, v in val.items()) + "]"
        if isinstance(val, list):
            return "[" + " ".join(str(x) for x in val) + "]"
        if isinstance(val, bool):
            return "true" if val else "false"
        return "<no value>" if val is None else str(val)
    tmpl = tmpl.replace("\\t", "\t").replace("\\n", "\n")
    return re.sub(r"\{\{(.*?)\}\}", lambda m: ev(m.group(1)), tmpl)


def ps_row(c, st=None):
    cmd = " ".join(c["cmd"])
    cmd = '"' + (cmd[:17] + "…" if len(cmd) > 18 else cmd) + '"'
    return {"ID": c["id"][:12], "Image": c["image"], "Command": cmd, "CreatedAt": ago(c["created"]) + " ago",
            "RunningFor": ago(c["created"]) + " ago", "Status": status_text(c, st), "Ports": ports_text(c),
            "Names": c["name"], "State": c["status"], "Labels": ",".join(f"{k}={v}" for k, v in c["labels"].items())}


def cmd_ps(args):
    opts, rest = parse_flags(args, {"f": "filter", "filter": "filter", "format": "format", "n": "last"},
                             {"a": "all", "all": "all", "q": "quiet", "quiet": "quiet", "no-trunc": "no-trunc",
                              "s": "size", "l": "latest"})
    st = load()
    cs = sorted(st["containers"].values(), key=lambda c: -c["created"])
    if not opts.get("all"):
        cs = [c for c in cs if c["status"] in ("running", "restarting")]
    cs = [c for c in cs if match_filters(c, opts.get("filter", []))]
    if opts.get("quiet"):
        for c in cs:
            print(c["id"][:12])
        return 0
    fmt = (opts.get("format") or [None])[-1]
    rows = [ps_row(c, st) for c in cs]
    if fmt:
        table = fmt.startswith("table")
        body = fmt[5:].strip() if table else fmt
        if table:
            hdr = re.sub(r"\{\{\s*\.(\w+)\s*\}\}", lambda m: {"ID": "CONTAINER ID"}.get(m.group(1), m.group(1).upper()), body)
            print(hdr.replace("\\t", "   "))
        for r in rows:
            print(go_format(body, r).replace("\t", "   "))
        return 0
    cols = [("CONTAINER ID", "ID"), ("IMAGE", "Image"), ("COMMAND", "Command"), ("CREATED", "CreatedAt"),
            ("STATUS", "Status"), ("PORTS", "Ports"), ("NAMES", "Names")]
    ws = [max([len(h)] + [len(r[k]) for r in rows]) + 3 for h, k in cols]
    print("".join(h.ljust(w) for (h, _), w in zip(cols, ws)).rstrip())
    for r in rows:
        print("".join(r[k].ljust(w) for (_, k), w in zip(cols, ws)).rstrip())
    return 0


def need(st, key, cmd):
    c = find_container(st, key)
    if not c:
        die(f"Error response from daemon: No such container: {key}", 1)
    return c


def cmd_logs(args):
    opts, rest = parse_flags(args, {"n": "tail", "tail": "tail", "since": "since", "until": "until"},
                             {"f": "follow", "follow": "follow", "t": "timestamps", "timestamps": "timestamps",
                              "details": "details"})
    if not rest:
        die('"docker logs" requires exactly 1 argument.', 1)
    st = load()
    c = need(st, rest[0], "logs")
    lines = c["logs"].splitlines()
    tail = (opts.get("tail") or ["all"])[-1]
    if tail != "all":
        try:
            lines = lines[-int(tail):] if int(tail) > 0 else []
        except ValueError:
            die(f'invalid value "{tail}" for flag --tail', 125)
    for ln in lines:
        if opts.get("timestamps"):
            ln = time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z ", time.gmtime(c["started"])) + ln
        print(ln)
    if opts.get("follow"):
        print("\x1b[2m[LinuxQuest 模擬] -f (follow) は本来ログを追いかけ続けます（Ctrl+C で終了）。模擬環境ではここで終了します。\x1b[0m")
    return 0


def cmd_exec(args):
    opts, rest = parse_flags(args, {"e": "env", "env": "env", "u": "user", "user": "user", "w": "workdir",
                                    "workdir": "workdir"},
                             {"i": "interactive", "interactive": "interactive", "t": "tty", "tty": "tty",
                              "d": "detach", "detach": "detach", "privileged": "privileged"})
    if len(rest) < 2:
        die('"docker exec" requires at least 2 arguments.\nSee \'docker exec --help\'.\n\nUsage:  docker exec [OPTIONS] CONTAINER COMMAND [ARG...]', 1)
    st = load()
    c = need(st, rest[0], "exec")
    if c["status"] != "running":
        die(f"Error response from daemon: container {c['id']} is not running", 1)
    sh = MiniShell(st, c)
    if (opts.get("workdir") or [None])[-1]:
        sh.cwd = opts["workdir"][-1]
    cmd = rest[1:]
    name = cmd[0].split("/")[-1]
    if name in ("sh", "bash", "ash") and len(cmd) == 1:
        if name == "bash" and base_name(c["image_ref"]) in ("alpine", "busybox"):
            die('OCI runtime exec failed: exec failed: unable to start container process: exec: "bash": executable file not found in $PATH: unknown', 126)
        if not (opts.get("interactive") and opts.get("tty")):
            return 0  # -it なしのシェルは即終了する（本物と同じ挙動）
        if not sys.stdin.isatty():
            die("the input device is not a TTY", 1)
        code = sh.interactive()
        if sh.crash:
            crash_container(st, c, sh.crash)
        save(st)
        return code
    out, code, _ = sh.run_line(shlex.join(cmd) if name not in ("sh", "bash") else " ".join(cmd[2:]) if cmd[1:2] == ["-c"] else shlex.join(cmd))
    if out:
        print(out)
    if sh.crash:
        crash_container(st, c, sh.crash)
    save(st)
    return code


def crash_container(st, c, sig):
    """コンテナのメインプロセス(PID 1)が落ちた。再起動ポリシーがあれば自動で起動し直す。"""
    img = st["images"].get(c["image_ref"], {})
    beh = dict(CATALOG.get(base_name(c["image_ref"]), {}))
    beh.update(img.get("behavior") or {})
    code = 137 if sig == "KILL" else int(beh.get("term_exit", 143))
    c["logs"] += beh.get("crash_log", "")
    c["status"], c["exit_code"], c["finished"] = "exited", code, time.time()
    c["health_last"] = "unhealthy"
    pol = restart_name(c)
    if pol in ("always", "unless-stopped") or (pol == "on-failure" and code != 0):
        c["restart_count"] = c.get("restart_count", 0) + 1
        evaluate_start(st, c)


def inspect_obj(c, st=None):
    return {
        "Id": c["id"], "Created": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(c["created"])),
        "Path": c["cmd"][0] if c["cmd"] else "", "Args": c["cmd"][1:],
        "State": {"Status": c["status"], "Running": c["status"] == "running", "Paused": False,
                  "Restarting": c["status"] == "restarting", "OOMKilled": False, "Dead": False, "Pid": 4242 if c["status"] == "running" else 0,
                  "ExitCode": c["exit_code"], "Error": "",
                  "StartedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(c["started"])),
                  "FinishedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(c["finished"])) if c["finished"] else "0001-01-01T00:00:00Z"}
        | ({"Health": {"Status": health_status(st, c), "FailingStreak": 0 if health_status(st, c) != "unhealthy" else 3,
                       "Log": [{"ExitCode": 0 if health_eval(st, c)[0] else 1, "Output": health_eval(st, c)[1]}]}}
           if st is not None and health_status(st, c) else {}),
        "Image": "sha256:" + hexid(c["image_ref"]), "Name": "/" + c["name"],
        "RestartCount": c.get("restart_count", 0), "Driver": "overlay2", "Platform": "linux",
        "HostConfig": {"Binds": [f"{m['src']}:{m['dst']}" for m in c["mounts"] if m["type"] == "bind"] or None,
                       "NetworkMode": next(iter(c.get("networks") or {"bridge": 0})) if c.get("networks") else "none",
                       "Links": [f"/{t}:/{c['name']}/{a}" for a, t in (c.get("links") or {}).items()] or None,
                       "PortBindings": {k: [{"HostIp": "", "HostPort": v}] for k, v in c["ports"].items()},
                       "RestartPolicy": {"Name": restart_name(c), "MaximumRetryCount": int(c["restart"].split(":")[1]) if ":" in (c.get("restart") or "") else 0},
                       "AutoRemove": c.get("autoremove", False)},
        "Mounts": [{"Type": m["type"], "Source": m["src"], "Destination": m["dst"], "Mode": "", "RW": True,
                    "Propagation": "rprivate" if m["type"] == "bind" else ""} | ({"Name": m["name"]} if m.get("name") else {})
                   for m in c["mounts"]],
        "Config": {"Hostname": c["id"][:12], "Env": [f"{k}={v}" for k, v in c["env"].items()], "Cmd": c["cmd"],
                   "Image": c["image"], "WorkingDir": c.get("workdir", "/"), "Labels": c["labels"],
                   "ExposedPorts": {k: {} for k in c["ports"]},
                   **({"Healthcheck": {"Test": c["healthcheck"]["test"]}} if c.get("healthcheck") else {})},
        "NetworkSettings": {"IPAddress": c["ip"] if c["status"] == "running" else "",
                            "Ports": {k: [{"HostIp": "0.0.0.0", "HostPort": v}] for k, v in c["ports"].items()} if c["status"] == "running" else {},
                            "Gateway": "172.17.0.1" if c["status"] == "running" else "",
                            "Networks": {n: {"NetworkID": (st["networks"].get(n, {}).get("id", "") if st else ""),
                                             "IPAddress": v.get("ip", "") if c["status"] == "running" else "",
                                             "Aliases": v.get("aliases") or None,
                                             "DNSNames": ([c["name"], c["id"][:12]] + list(v.get("aliases") or [])) if n not in ("bridge", "host", "none") else None}
                                         for n, v in (c.get("networks") or {}).items()}},
    }


def image_obj(ref, img):
    repo, tag = ref.rsplit(":", 1)
    return {"Id": "sha256:" + img["id"], "RepoTags": [ref], "Created": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(img["created"])),
            "Size": img.get("size_bytes") or size_to_bytes(img["size"]), "Config": {"Cmd": img.get("cmd"), "Env": [f"{k}={v}" for k, v in img.get("env", {}).items()],
                                            "WorkingDir": img.get("workdir", "/"), "ExposedPorts": {p: {} for p in img.get("expose", [])}}}


def cmd_inspect(args):
    opts, rest = parse_flags(args, {"f": "format", "format": "format", "type": "type"}, {"s": "size", "size": "size"})
    if not rest:
        die('"docker inspect" requires at least 1 argument.', 1)
    st = load()
    objs, err = [], 0
    for key in rest:
        c = find_container(st, key)
        if c:
            objs.append(inspect_obj(c, st))
            continue
        ref = norm_ref(key)
        if ref in st["images"]:
            objs.append(image_obj(ref, st["images"][ref]))
            continue
        sys.stderr.write(f"Error: No such object: {key}\n")
        err = 1
    fmt = (opts.get("format") or [None])[-1]
    if fmt:
        for o in objs:
            print(go_format(fmt, o))
    else:
        print(json.dumps(objs, indent=4, ensure_ascii=False))
    return err


def cmd_simple(action, args):
    opts, rest = parse_flags(args, {"t": "time", "time": "time", "s": "signal", "signal": "signal"},
                             {"f": "force", "force": "force", "v": "volumes", "volumes": "volumes",
                              "a": "attach", "attach": "attach", "i": "interactive"})
    if not rest:
        die(f'"docker {action}" requires at least 1 argument.', 1)
    st = load()
    code = 0
    for key in rest:
        c = find_container(st, key)
        if not c:
            sys.stderr.write(f"Error response from daemon: No such container: {key}\n")
            code = 1
            continue
        if action in ("stop", "kill"):
            if c["status"] in ("running", "restarting"):
                c["status"], c["exit_code"], c["finished"] = "exited", (137 if action == "kill" else 0), time.time()
                if c.get("autoremove"):
                    st["containers"].pop(c["id"], None)
        elif action in ("start", "restart"):
            if action == "restart" or c["status"] != "running":
                hp = check_port_conflict(st, c["ports"], exclude=c["id"])
                if hp:
                    sys.stderr.write(f"Error response from daemon: driver failed programming external connectivity on endpoint {c['name']}: Bind for 0.0.0.0:{hp} failed: port is already allocated\n")
                    code = 1
                    continue
                evaluate_start(st, c)
        elif action == "rm":
            if c["status"] == "restarting" and not opts.get("force"):
                sys.stderr.write(f"Error response from daemon: cannot remove container \"/{c['name']}\": container is restarting: stop the container before removing or force remove\n")
                code = 1
                continue
            if c["status"] == "running" and not opts.get("force"):
                sys.stderr.write(f"Error response from daemon: cannot remove container \"/{c['name']}\": container is running: stop the container before removing or force remove\n")
                code = 1
                continue
            st["containers"].pop(c["id"], None)
        print(key)
    save(st)
    return code


def cmd_images(args):
    opts, rest = parse_flags(args, {"f": "filter", "filter": "filter", "format": "format"},
                             {"a": "all", "all": "all", "q": "quiet", "quiet": "quiet", "no-trunc": "no-trunc"})
    st = load()
    items = sorted(st["images"].items(), key=lambda kv: -kv[1]["created"])
    if rest:
        items = [(r, i) for r, i in items if fnmatch.fnmatch(r.rsplit(":", 1)[0], rest[0]) or r == norm_ref(rest[0])]
    for f in opts.get("filter", []):
        if f == "dangling=true":
            items = [(r, i) for r, i in items if r.startswith("<none>")]
    if opts.get("quiet"):
        for r, i in items:
            print(i["id"][:12])
        return 0
    fmt = (opts.get("format") or [None])[-1]
    rows = []
    for r, i in items:
        repo, tag = r.rsplit(":", 1) if not r.startswith("<none>") else ("<none>", "<none>")
        rows.append({"Repository": repo, "Tag": tag, "ID": i["id"][:12], "CreatedSince": ago(i["created"]) + " ago",
                     "Size": i["size"]})
    if fmt:
        body = fmt[5:].strip() if fmt.startswith("table") else fmt
        for row in rows:
            print(go_format(body, row).replace("\t", "   "))
        return 0
    cols = [("REPOSITORY", "Repository"), ("TAG", "Tag"), ("IMAGE ID", "ID"), ("CREATED", "CreatedSince"), ("SIZE", "Size")]
    ws = [max([len(h)] + [len(r[k]) for r in rows]) + 3 for h, k in cols]
    print("".join(h.ljust(w) for (h, _), w in zip(cols, ws)).rstrip())
    for row in rows:
        print("".join(row[k].ljust(w) for (_, k), w in zip(cols, ws)).rstrip())
    return 0


def cmd_rmi(args):
    opts, rest = parse_flags(args, {}, {"f": "force", "force": "force"})
    st = load()
    code = 0
    for key in rest:
        ref = norm_ref(key)
        hit = ref if ref in st["images"] else next((r for r, i in st["images"].items() if i["id"].startswith(key)), None)
        if not hit:
            sys.stderr.write(f"Error response from daemon: No such image: {key}\n")
            code = 1
            continue
        users = [c for c in st["containers"].values() if c["image_ref"] == hit]
        if users and not opts.get("force"):
            sys.stderr.write(f"Error response from daemon: conflict: unable to remove repository reference \"{key}\" (must force) - container {users[0]['id'][:12]} is using its referenced image {st['images'][hit]['id'][:12]}\n")
            code = 1
            continue
        st["images"].pop(hit)
        print(f"Untagged: {hit}\nDeleted: sha256:{hexid(hit)}")
    save(st)
    return code


def cmd_pull(args):
    _, rest = parse_flags(args, {"platform": "platform"}, {"q": "quiet", "a": "all-tags"})
    if not rest:
        die('"docker pull" requires exactly 1 argument.', 1)
    st = load()
    ref = norm_ref(rest[0])
    if ref in st["images"]:
        print(f"{ref.rsplit(':', 1)[1]}: Pulling from library/{base_name(ref)}\nDigest: sha256:{hexid(ref + 'd')}\nStatus: Image is up to date for {ref}")
    else:
        ensure_image(st, rest[0], quiet=True)
        print(f"{ref.rsplit(':', 1)[1]}: Pulling from library/{base_name(ref)}\n{hexid(ref)[:12]}: Pull complete\nDigest: sha256:{hexid(ref + 'd')}\nStatus: Downloaded newer image for {ref}\ndocker.io/library/{ref}")
    save(st)
    return 0


def confirm(msg):
    sys.stdout.write(msg + " [y/N] ")
    sys.stdout.flush()
    try:
        return sys.stdin.readline().strip().lower() in ("y", "yes")
    except Exception:
        return False


def cmd_prune(scope, args):
    opts, rest = parse_flags(args, {"filter": "filter"}, {"f": "force", "force": "force", "a": "all", "all": "all",
                                                           "volumes": "volumes"})
    st = load()
    if not opts.get("force"):
        if scope == "system":
            msg = ("WARNING! This will remove:\n  - all stopped containers\n  - all networks not used by at least one container\n"
                   + ("  - all images without at least one container associated to them\n" if opts.get("all") else "  - all dangling images\n")
                   + "  - unused build cache\n\nAre you sure you want to continue?")
        elif scope == "container":
            msg = "WARNING! This will remove all stopped containers.\nAre you sure you want to continue?"
        else:
            msg = ("WARNING! This will remove all images without at least one container associated to them.\nAre you sure you want to continue?"
                   if opts.get("all") else "WARNING! This will remove all dangling images.\nAre you sure you want to continue?")
        if not confirm(msg):
            return 0
    filters = opts.get("filter", [])
    removed = []
    if scope in ("system", "container"):
        for cid, c in list(st["containers"].items()):
            if c["status"] != "running" and match_filters(c, filters):
                removed.append(cid)
                st["containers"].pop(cid)
        if removed or scope == "container":
            print("Deleted Containers:" if removed else "")
            for cid in removed:
                print(cid)
    img_removed = []
    if scope in ("system", "image"):
        used = {c["image_ref"] for c in st["containers"].values()}
        for ref in list(st["images"]):
            dangling = ref.startswith("<none>")
            if (dangling or opts.get("all")) and ref not in used:
                img_removed.append(ref)
                st["images"].pop(ref)
        if img_removed:
            print("\nDeleted Images:")
            for r in img_removed:
                print(f"untagged: {r}" if not r.startswith("<none>") else f"deleted: sha256:{hexid(r)}")
    if scope == "system":
        st["build_cache"] = {}
    save(st)
    total = len(removed) * 1.2 + len(img_removed) * 85.3
    print(f"\nTotal reclaimed space: {total:.1f}MB")
    return 0


# ------------------------------------------------------------------ build
DF_INSTR = {"FROM", "RUN", "CMD", "LABEL", "MAINTAINER", "EXPOSE", "ENV", "ADD", "COPY", "ENTRYPOINT", "VOLUME",
            "USER", "WORKDIR", "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL"}


def parse_dockerfile(text):
    """(lineno, INSTR, args) のリストを返す。構文エラーは ValueError(行番号, メッセージ)。"""
    out, buf, start = [], "", 0
    lines = text.splitlines()
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not buf and (not s or s.startswith("#")):
            continue
        if not buf:
            start = i
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        word, _, rest = buf.strip().partition(" ")
        instr = word.upper()
        if instr not in DF_INSTR:
            raise ValueError(start, f"unknown instruction: {word}")
        out.append((start, instr, rest.strip()))
        buf = ""
    if buf:
        word, _, rest = buf.strip().partition(" ")
        out.append((start, word.upper(), rest.strip()))
    return out


def _glob_rx(p):
    out, i = "", 0
    while i < len(p):
        ch = p[i]
        if p.startswith("**", i):
            out += ".*"
            i += 2
            if i < len(p) and p[i] == "/":
                i += 1
            continue
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch == "[" and "]" in p[i:]:
            j = p.index("]", i)
            out += p[i:j + 1]
            i = j + 1
            continue
        else:
            out += re.escape(ch)
        i += 1
    return re.compile(out + "$")


def ignore_patterns(ctxdir):
    """.dockerignore を (否定?, 正規表現) のリストにする。本物と同じく `*` は `/` をまたがない（`**` はまたぐ）。"""
    di = Path(ctxdir) / ".dockerignore"
    pats = []
    if di.exists():
        for ln in di.read_text(errors="replace").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            neg = ln.startswith("!")
            if neg:
                ln = ln[1:].strip()
            ln = os.path.normpath(ln.lstrip("/")) if ln.strip("/") else "."
            if ln.startswith("./"):
                ln = ln[2:]
            pats.append((neg, _glob_rx(ln)))
    return pats


def is_ignored(rel, pats):
    parts = rel.split("/")
    prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
    res = False
    for neg, rx in pats:
        if any(rx.match(p) for p in prefixes):
            res = not neg
    return res


def context_files(ctxdir, pats):
    files, total = [], 0
    ctxdir = Path(ctxdir)
    has_neg = any(n for n, _ in pats)
    for dp, dns, fns in os.walk(ctxdir):
        reld = os.path.relpath(dp, ctxdir)
        reld = "" if reld == "." else reld + "/"
        if not has_neg:
            dns[:] = [d for d in dns if not is_ignored(reld + d, pats)]
        dns.sort()
        for fn in sorted(fns):
            rel = reld + fn
            if is_ignored(rel, pats) and rel not in ("Dockerfile",):
                continue
            p = Path(dp) / fn
            if p.is_file():
                files.append(rel)
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return files, total


def _fs_text(path):
    try:
        size = path.stat().st_size
    except OSError:
        return "", 0
    if size > 65536:
        return f"<binary data: {size} bytes>", size
    return path.read_bytes().decode(errors="replace"), size


def _from_image_state(st, base):
    if base.lower() == "scratch":
        return {"fs": {}, "sizes": {}, "env": {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
                "workdir": "/", "cmd": None, "entrypoint": None, "expose": [], "base_bytes": 0, "added": 0,
                "libc": None, "noshell": True, "healthcheck": None, "layers": [], "has_elf": False,
                "ref": "scratch"}
    img = ensure_image(st, base, quiet=True)
    ref = norm_ref(base)
    sb = img.get("size_bytes") or size_to_bytes(img.get("size", "0B"))
    return {"fs": dict(img.get("fs", {})), "sizes": dict(img.get("sizes", {})), "env": dict(img.get("env", {})),
            "workdir": img.get("workdir", "/"), "cmd": img.get("cmd"), "entrypoint": None,
            "expose": list(img.get("expose", [])), "base_bytes": sb, "added": 0, "libc": img.get("libc", "glibc"),
            "noshell": img.get("noshell", False), "healthcheck": img.get("healthcheck"),
            "layers": list(img.get("layers") or [[f"/bin/sh -c #(nop) ADD file:{hexid(ref)[:24]} in / ", sb]]),
            "has_elf": img.get("has_elf", False), "ref": ref}


def _parse_hc(a):
    if a.strip().upper() == "NONE":
        return {"test": ["NONE"]}
    toks = a.split()
    opts = {}
    while toks and toks[0].startswith("--"):
        k, _, v = toks.pop(0)[2:].partition("=")
        opts[k] = v
    if not toks or toks[0].upper() != "CMD":
        return None
    rest = a[a.upper().index("CMD", len(a) - len(" ".join(toks)) - 1) + 3:].strip()
    if rest.startswith("["):
        try:
            return {"test": ["CMD"] + json.loads(rest), **opts}
        except ValueError:
            return None
    return {"test": ["CMD-SHELL", rest], **opts}


def cmd_build(args):
    opts, rest = parse_flags(args, {"t": "tag", "tag": "tag", "f": "file", "file": "file",
                                    "build-arg": "build-arg", "target": "target", "platform": "platform",
                                    "progress": "progress"},
                             {"q": "quiet", "no-cache": "no-cache", "pull": "pull", "rm": "rm"})
    if not rest:
        die('ERROR: "docker buildx build" requires exactly 1 argument.\nSee \'docker buildx build --help\'.\n\nUsage:  docker buildx build [OPTIONS] PATH | URL | -', 1)
    ctxdir = Path(rest[0]).resolve()
    if not ctxdir.is_dir():
        die(f'ERROR: unable to prepare context: path "{rest[0]}" not found', 1)
    dfpath = Path((opts.get("file") or [str(ctxdir / "Dockerfile")])[-1])
    if not dfpath.is_absolute() and opts.get("file"):
        dfpath = Path.cwd() / dfpath
    t0 = time.time()
    print("[+] Building 0.0s (0/0)                                                docker:default")
    if not dfpath.exists():
        die(f"ERROR: failed to solve: failed to read dockerfile: open {dfpath.name}: no such file or directory", 1)
    print(f" => [internal] load build definition from {dfpath.name}")
    df_lines = dfpath.read_text().splitlines()
    try:
        instrs = parse_dockerfile(dfpath.read_text())
    except ValueError as e:
        ln, msg = e.args
        die(f"Dockerfile:{ln}\n--------------------\n  {ln} | >>> {df_lines[ln - 1]}\n--------------------\n"
            f"ERROR: failed to solve: dockerfile parse error on line {ln}: {msg}", 1)
    if not instrs:
        die("ERROR: failed to solve: file with no instructions", 1)
    firsts = [x for x in instrs if x[1] != "ARG"]
    if not firsts or firsts[0][1] != "FROM":
        ln = firsts[0][0] if firsts else 1
        die(f"ERROR: failed to solve: no build stage in current context (line {ln}: Dockerfile は FROM で始まる必要があります)", 1)
    for ln, ins, a in instrs:
        if ins in ("COPY", "ADD", "FROM", "WORKDIR", "EXPOSE", "USER") and not a:
            die(f"Dockerfile:{ln}\nERROR: failed to solve: dockerfile parse error on line {ln}: {ins} requires at least one argument", 1)
        if ins in ("COPY", "ADD") and len([x for x in shlex.split(a) if not x.startswith("--")]) < 2:
            die(f"Dockerfile:{ln}\nERROR: failed to solve: dockerfile parse error on line {ln}: {ins} requires at least two arguments, but only one was provided. Destination could not be determined", 1)
    st = load()
    pats = ignore_patterns(ctxdir)
    files, ctx_bytes = context_files(ctxdir, pats)
    # ---- ステージに分割
    stages = []
    for ln, ins, a in instrs:
        if ins == "FROM":
            toks = [t for t in a.split() if not t.startswith("--platform")]
            name = None
            if len(toks) == 3 and toks[1].lower() == "as":
                name = toks[2]
            elif len(toks) != 1:
                die(f"Dockerfile:{ln}\nERROR: failed to solve: dockerfile parse error on line {ln}: FROM requires either one or three arguments", 1)
            stages.append({"ln": ln, "base": toks[0], "name": name, "ins": []})
        elif stages:
            stages[-1]["ins"].append((ln, ins, a))
    target = (opts.get("target") or [None])[-1]
    if target:
        idx = next((k for k, s_ in enumerate(stages) if (s_["name"] or "").lower() == target.lower()), None)
        if idx is None:
            die(f'ERROR: failed to solve: target stage "{target}" could not be found', 1)
        stages = stages[:idx + 1]
    multi = len(stages) > 1
    first_base = stages[0]["base"]
    print(f" => [internal] load metadata for docker.io/library/{norm_ref(first_base) if first_base != 'scratch' else 'scratch'}")
    print(" => [internal] load .dockerignore\n => => transferring context: " + ("%dB" % (di_size(ctxdir))))
    print(f" => [internal] load build context\n => => transferring context: {human_size(ctx_bytes) if ctx_bytes else '2B'}")
    done = {}
    final = None
    for si, sd in enumerate(stages):
        label_name = sd["name"] or f"stage-{si}"
        steps = 1 + sum(1 for _, i, _ in sd["ins"] if i in ("RUN", "COPY", "ADD", "WORKDIR"))
        lab = (lambda k, _ln=label_name, _n=steps: f"[{_ln} {k}/{_n}]" if multi else f"[{k}/{_n}]")
        bkey = sd["base"].lower()
        if bkey in done:
            S = json.loads(json.dumps(done[bkey]))
            S["base_bytes"], S["added"] = S["base_bytes"] + S["added"], 0
            print(f" => {lab(1)} FROM {bkey}")
            chain = hashlib.sha256(("FROM-STAGE " + S["chain"]).encode()).hexdigest()
        else:
            S = _from_image_state(st, sd["base"])
            if S["ref"] != "scratch":
                print(f" => {lab(1)} FROM docker.io/library/{S['ref']}")
            chain = hashlib.sha256(("FROM " + S["ref"]).encode()).hexdigest()
        k = 1
        cache_ok = not opts.get("no-cache")
        for ln, ins, a in sd["ins"]:
            fs, sizes = S["fs"], S["sizes"]
            workdir = S["workdir"]
            if ins == "ENV":
                if "=" in a.split()[0]:
                    for kv in shlex.split(a):
                        kk, _, vv = kv.partition("=")
                        S["env"][kk] = vv
                else:
                    kk, _, vv = a.partition(" ")
                    S["env"][kk] = vv.strip()
                continue
            if ins in ("CMD", "ENTRYPOINT"):
                try:
                    val = json.loads(a) if a.startswith("[") else ["/bin/sh", "-c", a]
                except ValueError:
                    die(f"Dockerfile:{ln}\nERROR: failed to solve: {ins} の JSON 配列形式が不正です（\"\" ダブルクォートを使っていますか？）: {a}", 1)
                if ins == "CMD":
                    S["cmd"] = val
                else:
                    S["entrypoint"] = val
                    S["cmd"] = None
                continue
            if ins == "EXPOSE":
                S["expose"] += [p if "/" in p else p + "/tcp" for p in a.split()]
                continue
            if ins == "HEALTHCHECK":
                hc = _parse_hc(a)
                if hc is None:
                    die(f"Dockerfile:{ln}\nERROR: failed to solve: dockerfile parse error on line {ln}: HEALTHCHECK の書式が不正です（例: HEALTHCHECK --interval=30s CMD curl -f http://localhost/ || exit 1）", 1)
                S["healthcheck"] = hc
                continue
            if ins == "WORKDIR":
                S["workdir"] = a if a.startswith("/") else workdir.rstrip("/") + "/" + a
                chain = hashlib.sha256((chain + "WORKDIR " + a).encode()).hexdigest()
                k += 1
                print(f" => {lab(k)} WORKDIR {a}")
                continue
            delta = 0
            if ins in ("COPY", "ADD"):
                toks = shlex.split(a)
                flags = {x[2:].partition("=")[0]: x.partition("=")[2] for x in toks if x.startswith("--")}
                parts = [x for x in toks if not x.startswith("--")]
                srcs, dst = parts[:-1], parts[-1]
                dst_abs = dst if dst.startswith("/") else workdir.rstrip("/") + "/" + dst
                content_hash = hashlib.sha256()
                if "from" in flags:
                    src_key = flags["from"].lower()
                    if src_key in done:
                        SRC = done[src_key]
                    elif src_key.isdigit() and int(src_key) < si:
                        SRC = done[(stages[int(src_key)]["name"] or f"#{src_key}").lower()]
                    else:
                        SRC = _from_image_state(st, flags["from"])
                    for s_ in srcs:
                        p_ = os.path.normpath("/" + s_.lstrip("/")) if not s_.startswith("/") else os.path.normpath(s_)
                        matched = [f for f in SRC["fs"] if f == p_ or f.startswith(p_.rstrip("/") + "/") or fnmatch.fnmatch(f, p_)]
                        if not matched:
                            die(f" => ERROR {lab(k + 1)} {ins} {a}\n------\n > {lab(k + 1)} {ins} {a}:\n------\nDockerfile:{ln}\n--------------------\n"
                                f"  {ln} | >>> {df_lines[ln - 1]}\n--------------------\n"
                                f"ERROR: failed to solve: failed to compute cache key: failed to calculate checksum of ref {hexid()[:26]}::{hexid()[:26]}: \"{p_}\": not found", 1)
                        for f in matched:
                            data = SRC["fs"][f]
                            if f == p_:
                                target = dst_abs.rstrip("/") + "/" + os.path.basename(f) if dst.endswith("/") or len(srcs) > 1 else dst_abs
                            else:
                                target = dst_abs.rstrip("/") + "/" + f[len(p_.rstrip("/")) + 1:]
                            target = os.path.normpath(target)
                            fs[target] = data
                            sz = SRC["sizes"].get(f, len(data))
                            sizes[target] = sz
                            delta += sz
                            if data.startswith("\x7fELF LinuxQuest"):
                                S["has_elf"] = True
                            content_hash.update(f.encode() + data.encode())
                else:
                    for s_ in srcs:
                        s_norm = s_.lstrip("./") if s_ not in (".", "./") else "."
                        if s_norm == ".":
                            matched = files
                        else:
                            matched = [f for f in files if fnmatch.fnmatch(f, s_norm) or f.startswith(s_norm.rstrip("/") + "/")]
                        if not matched:
                            hidden = (ctxdir / s_norm).exists()
                            die(f" => ERROR {lab(k + 1)} {ins} {a}\n------\n > {lab(k + 1)} {ins} {a}:\n------\nDockerfile:{ln}\n"
                                f"ERROR: failed to solve: failed to compute cache key: failed to calculate checksum of ref: \"/{s_norm}\": not found"
                                + ("\n（このファイルは .dockerignore で除外されています）" if hidden else ""), 1)
                        for f in matched:
                            data, sz = _fs_text(ctxdir / f)
                            content_hash.update(f.encode() + data.encode() + str(sz).encode())
                            if s_norm == "." or s_norm.endswith("/") or (ctxdir / s_norm).is_dir():
                                rel = f[len(s_norm.rstrip('/')) + 1:] if s_norm != "." else f
                                target = dst_abs.rstrip("/") + "/" + rel
                            else:
                                target = dst_abs.rstrip("/") + "/" + os.path.basename(f) if (dst.endswith("/") or len(matched) > 1 or dst in (".", "./")) else dst_abs
                            target = os.path.normpath(target)
                            fs[target] = data
                            sizes[target] = sz
                            delta += sz
                chain = hashlib.sha256((chain + ins + a + content_hash.hexdigest()).encode()).hexdigest()
            elif ins == "RUN":
                chain = hashlib.sha256((chain + "RUN " + a).encode()).hexdigest()
                if S["noshell"] and not a.startswith("["):
                    die(f" => ERROR {lab(k + 1)} RUN {a}\n------\n > {lab(k + 1)} RUN {a}:\n------\nDockerfile:{ln}\n"
                        f"ERROR: failed to solve: process \"/bin/sh -c {a}\" did not complete successfully: runc run failed: unable to start container process: "
                        f"exec: \"/bin/sh\": stat /bin/sh: no such file or directory\n（このベースイメージにはシェルがありません。RUN はビルド用ステージで実行しましょう）", 1)
                m = re.search(r"pip3? install[^&;|]*-r\s+(\S+)", a)
                if m:
                    req = m.group(1)
                    req_abs = req if req.startswith("/") else workdir.rstrip("/") + "/" + req
                    if os.path.normpath(req_abs) not in fs:
                        die(f" => ERROR {lab(k + 1)} RUN {a}\n0.912 ERROR: Could not open requirements file: [Errno 2] No such file or directory: '{req}'\n------\n"
                            f"Dockerfile:{ln}\nERROR: failed to solve: process \"/bin/sh -c {a}\" did not complete successfully: exit code: 1", 1)
                    delta += 28_400_000
                gm = re.search(r"\bgo\s+build\b([^&;|]*)", a)
                if gm:
                    def go_fail(msg, code=1):
                        die(f" => ERROR {lab(k + 1)} RUN {a}\n0.{random.randint(100, 999)} {msg}\n------\nDockerfile:{ln}\n--------------------\n"
                            f"  {ln} | >>> {df_lines[ln - 1]}\n--------------------\n"
                            f"ERROR: failed to solve: process \"/bin/sh -c {a}\" did not complete successfully: exit code: {code}", 1)
                    if "/usr/local/go/bin/go" not in fs:
                        go_fail("/bin/sh: 1: go: not found", 127)
                    wd = workdir.rstrip("/") or ""
                    gomod = next((p_ for p_ in (wd + "/go.mod", "/go.mod") if p_ in fs), None)
                    if not gomod:
                        go_fail("go: go.mod file not found in current directory or any parent directory; see 'go help modules'")
                    if not any(f.startswith(wd + "/") and f.endswith(".go") for f in fs):
                        go_fail(f"no Go files in {workdir}")
                    mm = re.search(r"^module\s+(\S+)", fs[gomod], re.M)
                    modname = (mm.group(1) if mm else "app").split("/")[-1]
                    om = re.search(r"-o[= ]\s*(\S+)", gm.group(1))
                    if om:
                        o_ = om.group(1)
                        o_abs = o_ if o_.startswith("/") else wd + "/" + o_
                        if o_.endswith("/"):
                            o_abs = o_abs.rstrip("/") + "/" + modname
                    else:
                        o_abs = wd + "/" + modname
                    o_abs = os.path.normpath(o_abs)
                    cgo = S["env"].get("CGO_ENABLED", "1")
                    im = re.search(r"CGO_ENABLED=(\d)", a.split("go build")[0] + gm.group(0))
                    if im:
                        cgo = im.group(1)
                    lib = "static" if cgo == "0" or S["libc"] is None else S["libc"]
                    sz = 8_900_000 if re.search(r"-ldflags[= ]?['\"]?[^'\"]*-s", a) else 12_600_000
                    fs[o_abs] = f"\x7fELF LinuxQuest-Go-binary libc={lib}\n"
                    sizes[o_abs] = sz
                    delta += sz
                    S["has_elf"] = True
                if re.search(r"\bgo\s+mod\s+download\b", a):
                    delta += 41_300_000
                if re.search(r"\bapk\s+add\b", a):
                    delta += 9_600_000
                if re.search(r"\bapt(-get)?\s+install\b", a):
                    delta += 96_000_000 if "rm -rf /var/lib/apt/lists" not in a else 71_000_000
                if re.search(r"\bnpm\s+(ci|install)\b", a):
                    delta += 145_000_000
            else:
                continue
            k += 1
            hit = cache_ok and chain in st["build_cache"]
            if not hit:
                cache_ok = False
            label = "CACHED " if hit else ""
            dur = "" if hit else f"  {random.uniform(0.1, 9.0) if ins == 'RUN' else random.uniform(0.0, 0.3):.1f}s"
            print(f" => {label}{lab(k)} {ins} {a}{dur}")
            st["build_cache"][chain] = time.time()
            S["added"] += delta
            S["layers"].append([f"{ins} {a}" if ins != "RUN" else f"RUN /bin/sh -c {a} # buildkit", delta])
        S["chain"] = chain
        done[(sd["name"] or f"#{si}").lower()] = S
        done[f"#{si}"] = S
        final = S
    tags = opts.get("tag") or []
    iid = hexid(final["chain"] + str(time.time()))
    for t in tags:
        if not valid_ref(t):
            die(f'ERROR: invalid tag "{t}": repository name must be lowercase', 1)
    print(" => exporting to image\n => => exporting layers\n => => writing image sha256:" + iid)
    total = final["base_bytes"] + final["added"]
    cmd = (final["entrypoint"] or []) + (final["cmd"] or []) if final["entrypoint"] else final["cmd"]
    expose = final["expose"]
    port = expose[0].split("/")[0] if expose else "8000"
    if final["has_elf"]:
        logs = f"{time.strftime('%Y/%m/%d %H:%M:%S')} server started: listening on :{port}\n"
    else:
        logs = f"Starting app ({' '.join(cmd or [])})...\nListening on 0.0.0.0:{port}\n"
    rec = {"id": iid, "created": time.time(), "size": human_size(total), "size_bytes": total, "cmd": cmd,
           "kind": "server", "expose": expose, "fs": final["fs"], "sizes": final["sizes"], "env": final["env"],
           "workdir": final["workdir"], "libc": final["libc"], "noshell": final["noshell"],
           "healthcheck": final["healthcheck"], "built": True, "has_elf": final["has_elf"],
           "stages": [s_["name"] or f"stage-{i}" for i, s_ in enumerate(stages)], "base": stages[-1]["base"],
           "context_files": files[:2000], "context_bytes": ctx_bytes, "layers": final["layers"],
           "behavior": {"logs": logs}}
    for t in tags:
        ref = norm_ref(t)
        old = st["images"].get(ref)
        if old and old.get("id") != iid and not any(c["image_ref"] == ref for c in st["containers"].values()):
            pass
        st["images"][ref] = dict(rec)
        print(f" => => naming to docker.io/library/{ref}")
    if not tags:
        st["images"][f"<none>:<none>-{iid[:8]}"] = dict(rec)
    save(st)
    nsteps = sum(1 + sum(1 for _, i, _ in s_["ins"] if i in ("RUN", "COPY", "ADD", "WORKDIR")) for s_ in stages)
    print(f"[+] Building {time.time() - t0 + random.uniform(1, 4):.1f}s ({nsteps}/{nsteps}) FINISHED")
    return 0


def di_size(ctxdir):
    try:
        return (Path(ctxdir) / ".dockerignore").stat().st_size
    except OSError:
        return 2


def cmd_history(args):
    opts, rest = parse_flags(args, {"format": "format"}, {"H": "human", "q": "quiet", "no-trunc": "no-trunc"})
    if not rest:
        die('"docker history" requires exactly 1 argument.', 1)
    st = load()
    ref = norm_ref(rest[0])
    img = st["images"].get(ref)
    if not img:
        die(f"Error response from daemon: No such image: {ref}", 1)
    layers = img.get("layers") or [[f"/bin/sh -c #(nop) ADD file:{hexid(ref)[:24]} in / ", img.get("size_bytes", 0)]]
    print(f"{'IMAGE':<15}{'CREATED':<16}{'CREATED BY':<52}{'SIZE':<10}COMMENT")
    for k, (by, sz) in enumerate(reversed(layers)):
        iid = img["id"][:12] if k == 0 else "<missing>"
        by = by if len(by) <= 48 else by[:45] + "…"
        print(f"{iid:<15}{ago(img['created']) + ' ago':<16}{by:<52}{human_size(sz) if sz else '0B':<10}{'buildkit.dockerfile.v0' if img.get('built') and k < len(layers) - 1 else ''}")
    return 0


# ------------------------------------------------------------------ compose (minimal YAML)
class YamlError(Exception):
    pass


def _scalar(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if s in ("true", "false"):
        return s == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def _strip_comment(line):
    out, q = "", None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out += ch
    return out.rstrip()


def parse_yaml(text):
    rows = []
    for no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"yaml: line {no}: found character that cannot start any token（インデントにタブ文字が使われています。スペースを使ってください）")
        line = _strip_comment(raw)
        if not line.strip():
            continue
        rows.append((no, len(line) - len(line.lstrip(" ")), line.strip()))
    pos = [0]

    def parse_block(indent):
        if pos[0] >= len(rows):
            return None
        no, ind, txt = rows[pos[0]]
        if txt.startswith("- ") or txt == "-":
            lst = []
            while pos[0] < len(rows):
                no, ind2, txt = rows[pos[0]]
                if ind2 < indent:
                    break
                if ind2 > indent:
                    raise YamlError(f"yaml: line {no}: did not find expected '-' indicator（インデントがずれています）")
                if not (txt.startswith("- ") or txt == "-"):
                    raise YamlError(f"yaml: line {no}: did not find expected '-' indicator")
                item = txt[2:].strip() if txt != "-" else ""
                pos[0] += 1
                if not item:
                    lst.append(parse_block(rows[pos[0]][1]) if pos[0] < len(rows) and rows[pos[0]][1] > indent else None)
                elif re.match(r"^[\w.-]+:\s", item + " ") and not item.startswith(("'", '"')):
                    k, _, v = item.partition(":")
                    d = {k.strip(): _scalar(v) if v.strip() else None}
                    sub_ind = indent + 2
                    if pos[0] < len(rows) and rows[pos[0]][1] >= sub_ind:
                        more = parse_block(rows[pos[0]][1])
                        if isinstance(more, dict):
                            d.update(more)
                    lst.append(d)
                else:
                    lst.append(_scalar(item))
            return lst
        dct = {}
        while pos[0] < len(rows):
            no, ind2, txt = rows[pos[0]]
            if ind2 < indent:
                break
            if ind2 > indent:
                raise YamlError(f"yaml: line {no}: mapping values are not allowed in this context（インデントが揃っていません）")
            m = re.match(r"^([^:]+?):(\s+(.*))?$", txt)
            if not m:
                raise YamlError(f"yaml: line {no}: could not find expected ':'（`キー: 値` の形式になっていません）")
            key, val = m.group(1).strip().strip("\"'"), m.group(3)
            pos[0] += 1
            if val is None or val == "":
                if pos[0] < len(rows) and rows[pos[0]][1] > indent:
                    dct[key] = parse_block(rows[pos[0]][1])
                elif pos[0] < len(rows) and rows[pos[0]][1] == indent and rows[pos[0]][2].startswith("- "):
                    dct[key] = parse_block(indent)
                else:
                    dct[key] = None
            else:
                dct[key] = _scalar(val)
        return dct

    if not rows:
        return {}
    res = parse_block(rows[0][1])
    if pos[0] < len(rows):
        raise YamlError(f"yaml: line {rows[pos[0]][0]}: did not find expected key")
    return res


COMPOSE_FILES = ["compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"]


def load_compose(files):
    if not files:
        for f in COMPOSE_FILES:
            if Path(f).exists():
                files = [f]
                break
    if not files:
        die("no configuration file provided: not found", 1)
    try:
        doc = parse_yaml(Path(files[0]).read_text())
    except OSError:
        die(f"open {Path(files[0]).resolve()}: no such file or directory", 1)
    except YamlError as e:
        die(f"{files[0]}: {e}", 15)
    if not isinstance(doc, dict) or not isinstance(doc.get("services"), dict):
        die(f"{files[0]}: services must be a mapping", 15)
    for name, svc in doc["services"].items():
        if not isinstance(svc, dict):
            die(f"services.{name} must be a mapping", 15)
        if not svc.get("image") and not svc.get("build"):
            die(f"service \"{name}\" has neither an image nor a build context specified: invalid compose project", 1)
        for key in svc:
            if key not in ("image", "build", "ports", "environment", "volumes", "depends_on", "container_name",
                           "command", "restart", "env_file", "networks", "expose", "healthcheck", "working_dir",
                           "labels", "entrypoint", "hostname", "user"):
                die(f"validating {files[0]}: services.{name} additional properties '{key}' not allowed", 15)
    return doc


def compose_project():
    return re.sub(r"[^a-z0-9_-]", "", Path.cwd().name.lower())


def cmd_compose(args):
    files, i, project = [], 0, None
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-f", "--file"):
            files.append(args[i + 1])
            i += 2
        elif args[i] in ("-p", "--project-name"):
            project = args[i + 1]
            i += 2
        else:
            i += 1
    args = args[i:]
    if not args:
        print("Usage:  docker compose [OPTIONS] COMMAND\n\nCommands:\n  up  down  ps  logs  stop  start  restart  config")
        return 0
    sub, rest = args[0], args[1:]
    project = project or compose_project()
    st = load()

    def svc_containers():
        return [c for c in st["containers"].values() if c["labels"].get("com.docker.compose.project") == project]

    if sub == "version":
        print("Docker Compose version v2.29.7 (LinuxQuest mock)")
        return 0
    if sub == "ls":
        projs = {c["labels"].get("com.docker.compose.project") for c in st["containers"].values()} - {None}
        print("NAME      STATUS      CONFIG FILES")
        for p in projs:
            print(f"{p}   running")
        return 0
    if sub in ("ps",):
        cs = svc_containers()
        if "-a" not in rest and "--all" not in rest:
            cs = [c for c in cs if c["status"] == "running"]
        print(f"{'NAME':<22}{'IMAGE':<20}{'SERVICE':<10}{'STATUS':<22}PORTS")
        for c in cs:
            print(f"{c['name']:<22}{c['image']:<20}{c['labels'].get('com.docker.compose.service', ''):<10}{status_text(c):<22}{ports_text(c)}")
        return 0
    if sub == "logs":
        names = [a for a in rest if not a.startswith("-")]
        for c in svc_containers():
            svc = c["labels"].get("com.docker.compose.service")
            if names and svc not in names:
                continue
            for ln in c["logs"].splitlines():
                print(f"{svc + '-1':<8}| {ln}")
        return 0
    if sub == "down":
        cs = svc_containers()
        for c in cs:
            print(f" ✔ Container {c['name']}  Removed")
            st["containers"].pop(c["id"])
        print(f" ✔ Network {project}_default  Removed")
        save(st)
        return 0
    if sub in ("stop", "start", "restart"):
        for c in svc_containers():
            if sub == "stop":
                c["status"], c["finished"] = "exited", time.time()
            else:
                evaluate_start(st, c)
            print(f" ✔ Container {c['name']}  {'Stopped' if sub == 'stop' else 'Started'}")
        save(st)
        return 0
    doc = load_compose(files)
    if sub == "config":
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0
    if sub != "up":
        die(f"unknown docker command: \"compose {sub}\"", 1)
    detach = "-d" in rest or "--detach" in rest
    print(f"[+] Running {len(doc['services']) + 1}/{len(doc['services']) + 1}")
    print(f" ✔ Network {project}_default  Created")
    order = list(doc["services"])
    for name in list(order):
        deps = doc["services"][name].get("depends_on") or []
        for d in (deps if isinstance(deps, list) else list(deps)):
            if d in order and order.index(d) > order.index(name):
                order.remove(d)
                order.insert(order.index(name), d)
    for name in order:
        svc = doc["services"][name]
        image = svc.get("image") or f"{project}-{name}"
        if not svc.get("image"):
            ensure_image(st, image)
        ensure_image(st, image, quiet=True)
        env = {}
        e = svc.get("environment") or {}
        if isinstance(e, list):
            for kv in e:
                k, _, v = str(kv).partition("=")
                env[k] = v
        else:
            env = {k: str(v) for k, v in e.items()}
        ports = {}
        for p in svc.get("ports") or []:
            cport, hport = parse_port(str(p))
            ports[cport] = hport
        mounts = [parse_volume(str(v), os.getcwd()) for v in svc.get("volumes") or []]
        cname = svc.get("container_name") or f"{project}-{name}-1"
        cmd = svc.get("command")
        cmd = shlex.split(cmd) if isinstance(cmd, str) else (cmd or [])
        labels = {"com.docker.compose.project": project, "com.docker.compose.service": name, "lq": "1"}
        old = find_container(st, cname)
        conf = json.dumps([image, env, ports, [m["dst"] for m in mounts], cmd], sort_keys=True)
        if old and old.get("compose_conf") == conf and old["status"] == "running":
            print(f" ✔ Container {cname}  Running")
            continue
        if old:
            st["containers"].pop(old["id"])
        hp = check_port_conflict(st, ports)
        if hp:
            save(st)
            die(f"Error response from daemon: driver failed programming external connectivity on endpoint {cname}: Bind for 0.0.0.0:{hp} failed: port is already allocated", 1)
        c = new_container(st, cname, image, cmd, env, ports, mounts, labels)
        c["compose_conf"] = conf
        evaluate_start(st, c)
        print(f" ✔ Container {cname}  {'Recreated' if old else 'Started'}")
    save(st)
    if not detach:
        for c in svc_containers():
            for ln in c["logs"].splitlines():
                print(f"{c['labels'].get('com.docker.compose.service')}-1  | {ln}")
        print("\x1b[2m[LinuxQuest 模擬] -d なしの up は本来ログに張り付きます（Ctrl+C で全停止）。模擬環境ではそのまま起動状態を保ちます。\n"
              "                 実務ではバックグラウンド起動の `docker compose up -d` が基本です。\x1b[0m")
    return 0


# ------------------------------------------------------------------ main
HELP = """
Usage:  docker [OPTIONS] COMMAND

LinuxQuest 模擬 Docker CLI（シミュレーションモード）

Common Commands:
  run         Create and run a new container from an image
  exec        Execute a command in a running container
  ps          List containers
  build       Build an image from a Dockerfile
  pull        Download an image from a registry
  images      List images
  logs        Fetch the logs of a container
  inspect     Return low-level information on Docker objects
  compose     Docker Compose
  stop/start/restart/kill/rm/rmi/port/top
  system prune / container prune / image prune
"""


def main(argv):
    if not argv or argv[0] in ("--help", "-h", "help"):
        print(HELP)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd in ("-v", "--version"):
        print("Docker version 27.3.1, build lq-mock (LinuxQuest simulation)")
        return 0
    if cmd == "version":
        print("Client:\n Version:    27.3.1 (LinuxQuest mock)\n\nServer: LinuxQuest Simulated Engine\n Engine:\n  Version:   27.3.1-sim")
        return 0
    if cmd == "info":
        st = load()
        run = sum(1 for c in st["containers"].values() if c["status"] == "running")
        print(f"Client: Docker Engine - LinuxQuest mock\nServer:\n Containers: {len(st['containers'])}\n  Running: {run}\n  Stopped: {len(st['containers']) - run}\n Images: {len(st['images'])}\n Server Version: 27.3.1-sim\n Storage Driver: overlay2")
        return 0
    if cmd == "container":
        if not args:
            print("Usage: docker container COMMAND")
            return 0
        sub, args = args[0], args[1:]
        cmd = {"ls": "ps", "list": "ps"}.get(sub, sub)
        if cmd == "prune":
            return cmd_prune("container", args)
    if cmd == "image":
        if not args:
            print("Usage: docker image COMMAND")
            return 0
        sub, args = args[0], args[1:]
        cmd = {"ls": "images", "list": "images", "rm": "rmi"}.get(sub, sub)
        if cmd == "prune":
            return cmd_prune("image", args)
    if cmd == "system":
        if args and args[0] == "prune":
            return cmd_prune("system", args[1:])
        if args and args[0] == "df":
            st = load()
            print("TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE")
            print(f"Images          {len(st['images']):<10}{len({c['image_ref'] for c in st['containers'].values()}):<10}1.2GB     800MB (66%)")
            print(f"Containers      {len(st['containers']):<10}{sum(1 for c in st['containers'].values() if c['status'] == 'running'):<10}12kB      4kB (33%)")
            print(f"Build Cache     {len(st['build_cache']):<10}0         120MB     120MB")
            return 0
        print("Usage: docker system [df|prune]")
        return 0
    if cmd == "network":
        return cmd_network(args)
    if cmd == "volume":
        if args and args[0] in ("ls", "list"):
            print("DRIVER    VOLUME NAME")
            st = load()
            seen = set()
            for c in st["containers"].values():
                for m in c["mounts"]:
                    if m["type"] == "volume" and m.get("name") not in seen:
                        seen.add(m.get("name"))
                        print(f"local     {m.get('name')}")
            return 0
        print(f"[LinuxQuest 模擬] docker {cmd} {' '.join(args)} はシミュレーションでは省略されています")
        return 0
    table = {
        "run": lambda: cmd_run(args), "ps": lambda: cmd_ps(args), "logs": lambda: cmd_logs(args),
        "exec": lambda: cmd_exec(args), "inspect": lambda: cmd_inspect(args),
        "stop": lambda: cmd_simple("stop", args), "start": lambda: cmd_simple("start", args),
        "restart": lambda: cmd_simple("restart", args), "kill": lambda: cmd_simple("kill", args),
        "rm": lambda: cmd_simple("rm", args), "rmi": lambda: cmd_rmi(args), "images": lambda: cmd_images(args),
        "pull": lambda: cmd_pull(args), "build": lambda: cmd_build(args), "compose": lambda: cmd_compose(args),
        "history": lambda: cmd_history(args),
        "port": lambda: cmd_port(args), "top": lambda: cmd_top(args), "ls": lambda: cmd_ps(args),
    }
    if cmd in table:
        return table[cmd]()
    die(f"docker: unknown command: docker {cmd}\n\nRun 'docker --help' for more information", 1)


def cmd_network(args):
    if not args or args[0] in ("--help", "-h"):
        print("Usage:  docker network COMMAND\n\nManage networks\n\nCommands:\n  connect     Connect a container to a network\n"
              "  create      Create a network\n  disconnect  Disconnect a container from a network\n"
              "  inspect     Display detailed information on one or more networks\n  ls          List networks\n"
              "  prune       Remove all unused networks\n  rm          Remove one or more networks")
        return 0
    sub, rest = args[0], args[1:]
    st = load()
    nets = st["networks"]

    def users(n):
        return [c for c in st["containers"].values() if n in (c.get("networks") or {})]

    if sub in ("ls", "list"):
        opts, _ = parse_flags(rest, {"f": "filter", "filter": "filter", "format": "format"}, {"q": "quiet", "quiet": "quiet", "no-trunc": "no-trunc"})
        items = sorted(nets.items(), key=lambda kv: kv[0])
        if opts.get("quiet"):
            for n, v in items:
                print(v["id"][:12])
            return 0
        fmt = (opts.get("format") or [None])[-1]
        if fmt:
            for n, v in items:
                print(go_format(fmt, {"ID": v["id"][:12], "Name": n, "Driver": v["driver"], "Scope": "local"}))
            return 0
        w = max(len(n) for n in nets) + 3
        print(f"{'NETWORK ID':<15}{'NAME':<{w}}{'DRIVER':<10}SCOPE")
        for n, v in items:
            print(f"{v['id'][:12]:<15}{n:<{w}}{v['driver']:<10}local")
        return 0
    if sub == "create":
        opts, pos = parse_flags(rest, {"d": "driver", "driver": "driver", "subnet": "subnet", "gateway": "gateway",
                                       "label": "label", "o": "opt", "opt": "opt", "ip-range": "ip-range"},
                                {"internal": "internal", "attachable": "attachable"})
        if len(pos) != 1:
            die('"docker network create" requires exactly 1 argument.\nSee \'docker network create --help\'.\n\nUsage:  docker network create [OPTIONS] NETWORK', 1)
        n = pos[0]
        if n in nets:
            die(f"Error response from daemon: network with name {n} already exists", 1)
        drv = (opts.get("driver") or ["bridge"])[-1]
        if drv not in ("bridge", "overlay", "macvlan", "ipvlan"):
            die(f"Error response from daemon: plugin \"{drv}\" not found", 1)
        nets[n] = {"id": hexid("net" + n + str(time.time())), "driver": drv, "created": time.time(), "builtin": False,
                   "subnet": (opts.get("subnet") or [""])[-1], "next": 2, "internal": bool(opts.get("internal")),
                   "labels": dict(x.partition("=")[::2] for x in opts.get("label", []))}
        net_ip(st, n)
        nets[n]["next"] = 2
        save(st)
        print(nets[n]["id"])
        return 0
    if sub == "rm" or sub == "remove":
        if not rest:
            die('"docker network rm" requires at least 1 argument.', 1)
        code = 0
        for n in rest:
            key = n if n in nets else next((k for k, v in nets.items() if v["id"].startswith(n)), None)
            if not key:
                sys.stderr.write(f"Error response from daemon: network {n} not found\n")
                code = 1
                continue
            if nets[key].get("builtin"):
                sys.stderr.write(f"Error response from daemon: {key} is a pre-defined network and cannot be removed\n")
                code = 1
                continue
            if users(key):
                sys.stderr.write(f"Error response from daemon: error while removing network: network {key} id {nets[key]['id']} has active endpoints\n")
                code = 1
                continue
            nets.pop(key)
            print(n)
        save(st)
        return code
    if sub == "prune":
        removed = [n for n, v in nets.items() if not v.get("builtin") and not users(n)]
        for n in removed:
            nets.pop(n)
        save(st)
        if removed:
            print("Deleted Networks:\n" + "\n".join(removed))
        return 0
    if sub == "inspect":
        opts, pos = parse_flags(rest, {"f": "format", "format": "format"}, {"v": "verbose"})
        out, code = [], 0
        for n in pos:
            key = n if n in nets else next((k for k, v in nets.items() if v["id"].startswith(n)), None)
            if not key:
                sys.stderr.write(f"Error response from daemon: network {n} not found\n")
                code = 1
                continue
            v = nets[key]
            out.append({"Name": key, "Id": v["id"], "Created": time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z", time.gmtime(v["created"])),
                        "Scope": "local", "Driver": v["driver"], "EnableIPv6": False,
                        "IPAM": {"Driver": "default", "Config": [{"Subnet": v.get("subnet", ""), "Gateway": v.get("subnet", "").replace(".0.0/16", ".0.1")}] if v.get("subnet") else []},
                        "Internal": v.get("internal", False), "Attachable": False,
                        "Containers": {c["id"]: {"Name": c["name"], "IPv4Address": c["networks"][key].get("ip", "") + "/16"}
                                       for c in users(key) if c["status"] == "running"},
                        "Options": {}, "Labels": v.get("labels", {})})
        fmt = (opts.get("format") or [None])[-1]
        if fmt:
            for o in out:
                print(go_format(fmt, o))
        else:
            print(json.dumps(out, indent=4, ensure_ascii=False))
        return code
    if sub in ("connect", "disconnect"):
        opts, pos = parse_flags(rest, {"alias": "alias", "ip": "ip", "link": "link"}, {"f": "force", "force": "force"})
        if len(pos) != 2:
            die(f'"docker network {sub}" requires exactly 2 arguments.\nSee \'docker network {sub} --help\'.\n\nUsage:  docker network {sub} [OPTIONS] NETWORK CONTAINER', 1)
        n, key = pos
        if n not in nets:
            die(f"Error response from daemon: network {n} not found", 1)
        c = find_container(st, key)
        if not c:
            die(f"Error response from daemon: No such container: {key}", 1)
        c.setdefault("networks", {})
        if sub == "connect":
            if n in c["networks"]:
                die(f"Error response from daemon: endpoint with name {c['name']} already exists in network {n}", 1)
            if "host" in c["networks"] or n == "host":
                die("Error response from daemon: container cannot be disconnected from host network or connected to host network", 1)
            if opts.get("alias") and n == "bridge":
                die("Error response from daemon: network-scoped alias is supported only for containers in user defined networks", 1)
            c["networks"][n] = {"ip": net_ip(st, n), "aliases": list(opts.get("alias", []))}
        else:
            if n not in c["networks"]:
                die(f"Error response from daemon: container {c['id'][:12]} is not connected to network {n}", 1)
            c["networks"].pop(n)
        save(st)
        return 0
    die(f"docker: unknown command: docker network {sub}\n\nRun 'docker network --help' for more information", 1)


def cmd_port(args):
    st = load()
    if not args:
        die('"docker port" requires at least 1 argument.', 1)
    c = need(st, args[0], "port")
    for cport, hport in c["ports"].items():
        if c["status"] == "running":
            print(f"{cport} -> 0.0.0.0:{hport}")
    return 0


def cmd_top(args):
    st = load()
    if not args:
        die('"docker top" requires at least 1 argument.', 1)
    c = need(st, args[0], "top")
    if c["status"] != "running":
        die(f"Error response from daemon: container {c['id']} is not running", 1)
    print("UID    PID    PPID   C   STIME   TTY   TIME       CMD")
    print(f"root   4242   4220   0   09:00   ?     00:00:00   {' '.join(c['cmd'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]) or 0)
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
