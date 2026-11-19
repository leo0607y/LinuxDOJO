"""Docker 判定バックエンド。

本物の Docker デーモンが使えれば real モード、使えなければ mock モード（模擬 docker CLI）。
どちらのモードでも、ミッションの setup/check は同じ API で状態を扱える。

正規化されたコンテナ dict:
  {id, name, image, running, status, exit_code, ports{"80/tcp": "8080"}, mounts[{src,dst}],
   env{}, labels{}, cmd[]}
"""
import json
import os
import shutil
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_MODE = None


def _save_mode():
    try:
        from engine import save
        return save.load()["settings"].get("docker_mode", "auto")
    except Exception:
        return "auto"


def detect_mode():
    """'real' or 'mock'。LQ_DOCKER_MODE 環境変数 > セーブ設定 > 自動判定。"""
    global _MODE
    if _MODE:
        return _MODE
    env_mode = os.environ.get("LQ_DOCKER_MODE")
    if env_mode in ("mock", "real") and os.environ.get("LQ_SESSION"):
        _MODE = env_mode   # ゲームシェル内: 起動時に解決済みのモードを信頼（毎回 docker info しない）
        return _MODE
    want = env_mode or _save_mode() or "auto"
    if want in ("mock", "real"):
        _MODE = want
        if want == "real" and not real_available():
            _MODE = "mock"
        return _MODE
    _MODE = "real" if real_available() else "mock"
    return _MODE


def real_available():
    exe = shutil.which("docker", path=os.environ.get("PATH", "").replace(str(ROOT / "bin" / "mock") + ":", ""))
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=6)
        return r.returncode == 0 and r.stdout.strip() != b""
    except (OSError, subprocess.TimeoutExpired):
        return False


def backend(ctx):
    return RealDocker(ctx) if detect_mode() == "real" else MockDocker(ctx)


# ------------------------------------------------------------------ mock
class MockDocker:
    mode = "mock"

    def __init__(self, ctx):
        self.ctx = ctx
        from engine import dockermock
        self.dm = dockermock
        self.dm.STATE_DIR = ctx.state / "docker"

    def reset(self):
        shutil.rmtree(self.ctx.state / "docker", ignore_errors=True)

    def add_container(self, name, image, cmd=None, running=True, exit_code=0, logs="", files=None,
                      env=None, ports=None, labels=None, real_cmd=None, mounts=None):
        st = self.dm.load()
        self.dm.ensure_image(st, image)
        labels = dict(labels or {})
        labels.setdefault("lq", "1")
        c = self.dm.new_container(st, name, image, cmd or [], env or {}, ports or {}, mounts or [], labels)
        c["status"] = "running" if running else "exited"
        c["exit_code"] = exit_code
        c["logs"] = logs
        c["fs"].update(files or {})
        self.dm.save(st)

    def add_image(self, ref, behavior=None, files=None):
        st = self.dm.load()
        self.dm.ensure_image(st, ref)
        if behavior:
            img = st["images"][self.dm.norm_ref(ref)]
            img["behavior"] = behavior
            img["kind"] = "server"
            if behavior.get("expose"):
                img["expose"] = behavior["expose"]
            if behavior.get("cmd"):
                img["cmd"] = behavior["cmd"]
        if files:
            st["images"][self.dm.norm_ref(ref)]["fs"].update(files)
        self.dm.save(st)

    def containers(self):
        st = self.dm.load()
        return [self.dm.normalize(c, st) for c in st["containers"].values()]

    def images(self):
        st = self.dm.load()
        return {k: v for k, v in st["images"].items()}

    def exec(self, name, *cmd):
        st = self.dm.load()
        c = self.dm.find_container(st, name)
        if not c or c["status"] != "running":
            return "container is not running", 1
        out, code, _ = self.dm.MiniShell(st, c).run_line(shlex.join(cmd))
        return out, code

    def image_details(self, ref):
        return self.images().get(self.dm.norm_ref(ref))

    def image_created(self, ref):
        img = self.images().get(self.dm.norm_ref(ref))
        return img.get("created") if img else None


# ------------------------------------------------------------------ real
class RealDocker:
    mode = "real"

    def __init__(self, ctx):
        self.ctx = ctx

    def _run(self, *args, check=False, timeout=300, input=None):
        r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, input=input)
        if check and r.returncode != 0:
            raise RuntimeError(f"docker {' '.join(args)} failed: {r.stderr.strip()}")
        return r

    def reset(self):
        ids = set()
        for f in ("label=lq=1", "name=^lq-", "label=com.docker.compose.project=stage_05"):
            r = self._run("ps", "-aq", "--filter", f)
            ids |= set(r.stdout.split())
        if ids:
            self._run("rm", "-f", *ids)
        self._run("rmi", "-f", "lq-app:1.0", "lq-api:small")
        nets = self._run("network", "ls", "--filter", "label=lq=1", "--format", "{{.Name}}").stdout.split()
        for name in nets:
            if name.startswith("lq-"):
                self._run("network", "rm", name)

    def add_container(self, name, image, cmd=None, running=True, exit_code=0, logs="", files=None,
                      env=None, ports=None, labels=None, real_cmd=None, mounts=None):
        args = ["run", "-d", "--name", name, "--label", "lq=1"]
        for k, v in (labels or {}).items():
            args += ["--label", f"{k}={v}"]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        for cport, hport in (ports or {}).items():
            args += ["-p", f"{hport}:{cport.split('/')[0]}"]
        args.append(image)
        args += list(real_cmd or cmd or [])
        self._run(*args, check=True)
        if not running:
            self._run("wait", name, timeout=60)

    def add_image(self, ref, behavior=None, files=None):
        """real モードでは behavior から小さな alpine ベースのイメージをビルドする。"""
        if not behavior:
            self._run("pull", ref)
            return
        d = Path(tempfile.mkdtemp(prefix="lq-img-"))
        try:
            (d / "entry.sh").write_text(behavior.get("real_script", "#!/bin/sh\nsleep 3600\n"))
            os.chmod(d / "entry.sh", 0o755)
            (d / "Dockerfile").write_text(
                "FROM alpine:3.20\nCOPY entry.sh /entry.sh\nEXPOSE %s\nCMD [\"/entry.sh\"]\n"
                % behavior.get("listen", 8080))
            self._run("build", "-t", ref, str(d), check=True, timeout=600)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def containers(self):
        ids = self._run("ps", "-aq").stdout.split()
        if not ids:
            return []
        r = self._run("inspect", *ids)
        try:
            data = json.loads(r.stdout or "[]")
        except ValueError:
            return []
        out = []
        for c in data:
            pb = (c.get("HostConfig") or {}).get("PortBindings") or {}
            ports = {k: (v[0].get("HostPort") if v else "") for k, v in pb.items()}
            env = {}
            for e in (c.get("Config") or {}).get("Env") or []:
                if "=" in e:
                    k, v = e.split("=", 1)
                    env[k] = v
            stt = c.get("State") or {}
            out.append({
                "id": c.get("Id", "")[:12], "name": c.get("Name", "").lstrip("/"),
                "image": (c.get("Config") or {}).get("Image", ""),
                "running": bool(stt.get("Running")), "status": stt.get("Status", ""),
                "exit_code": stt.get("ExitCode", 0), "ports": ports,
                "mounts": [{"src": m.get("Source", ""), "dst": m.get("Destination", "")} for m in c.get("Mounts") or []],
                "env": env, "labels": (c.get("Config") or {}).get("Labels") or {},
                "cmd": (c.get("Config") or {}).get("Cmd") or [],
                "autoremove": bool((c.get("HostConfig") or {}).get("AutoRemove")),
                "networks": sorted(((c.get("NetworkSettings") or {}).get("Networks") or {}).keys()),
                "restart_policy": ((c.get("HostConfig") or {}).get("RestartPolicy") or {}).get("Name", "no"),
                "restart_count": c.get("RestartCount", 0),
                "health": (stt.get("Health") or {}).get("Status"),
                "healthcheck": {"test": ((c.get("Config") or {}).get("Healthcheck") or {}).get("Test", [])},
            })
        return out

    def images(self):
        r = self._run("images", "--format", "{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}")
        out = {}
        for ln in r.stdout.splitlines():
            ref = ln.split("\t")[0]
            out[ref] = {"created": None}
        return out

    def exec(self, name, *cmd):
        r = self._run("exec", name, *cmd, timeout=15)
        return r.stdout, r.returncode

    def image_details(self, ref):
        r = self._run("image", "inspect", ref)
        if r.returncode:
            return None
        data = json.loads(r.stdout)[0]
        return {"size_bytes": data.get("Size", 0)}

    def image_created(self, ref):
        r = self._run("image", "inspect", ref, "--format", "{{.Created}}")
        if r.returncode != 0:
            return None
        from datetime import datetime
        s = r.stdout.strip()
        try:
            s = s[:26].rstrip("Z") if "." in s else s.rstrip("Z")
            return datetime.fromisoformat(s.split(".")[0]).timestamp() + _utc_offset()
        except ValueError:
            return 1e18  # 解析できなければ「存在する」扱い


def _utc_offset():
    import time
    return -time.timezone if not time.daylight else -time.altzone


# ------------------------------------------------------------------ helpers for checks
def find(containers, name):
    for c in containers:
        if c["name"] == name:
            return c
    return None


def image_matches(image, base):
    """'nginx' は 'nginx', 'nginx:latest', 'nginx:1.27', 'docker.io/library/nginx' にマッチ。"""
    img = image.split("@")[0]
    for pre in ("docker.io/library/", "library/", "docker.io/"):
        if img.startswith(pre):
            img = img[len(pre):]
    repo = img.rsplit(":", 1)[0] if ":" in img.split("/")[-1] else img
    return repo == base
