"""サンドボックス環境構築・サブシェル起動・状態判定エンジン。

- ミッション定義 (Mission) とレジストリ
- 判定用コンテキスト (Ctx): ファイル・パーミッション・リンク・プロセス・環境変数・履歴・終了コードなどを検査
- サンドボックス (workspace/stage_XX) の初期化 / リセット
- 本物の bash サブシェルの起動
"""
import json
import os
import random
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("LQ_WORKSPACE", ROOT / "workspace"))
STATE = WORKSPACE / ".lq_state"
SHELLRC = ROOT / "engine" / "shellrc.bash"
BIN = ROOT / "bin"
MOCKBIN = ROOT / "bin" / "mock"
SIMBIN = ROOT / "bin" / "sim"   # systemctl / journalctl などの学習用シミュレーター（Mission.sim=True の時だけ PATH に入る）

EXTRA = 99  # Extra ステージの内部番号（メニューでは [x]）

STAGES = {
    1: ("Stage 1", "超基礎・ファイルシステムと基本操作", "📁"),
    2: ("Stage 2", "テキスト処理・検索・パイプとリダイレクト", "🔍"),
    3: ("Stage 3", "パーミッション・プロセス・環境変数・監視", "🛡️"),
    4: ("Stage 4", "ネットワーク・通信デバッグ・アーカイブ", "🌐"),
    5: ("Stage 5", "Docker & コンテナ実践テクニック", "🐳"),
    6: ("Stage 6", "シェルスクリプトと自動化", "⚙️"),
    7: ("Stage 7", "サーバー運用と Docker 応用", "🏭"),
    8: ("Stage 8", "Web の認証・認可・設定検証", "🔐"),
    9: ("Stage 9", "Linux セキュリティ監査と修正", "🛡️"),
    10: ("Stage 10", "証拠保全・インシデント調査・報告", "🔎"),
    11: ("Stage 11", "ストレージ・起動・復旧の診断", "💾"),
    12: ("Stage 12", "性能調査・更新・高度な権限", "📈"),
    13: ("Stage 13", "ネットワーク設定・TLS・DB運用", "🔗"),
    14: ("Stage 14", "ブート・カーネル・ハードウェア", "🧬"),
    15: ("Stage 15", "ストレージ構築・LVM・RAID", "🗄️"),
    16: ("Stage 16", "SELinux・ACL・属性・資源制限", "🛂"),
    17: ("Stage 17", "ネットワーク管理・共有・パッケージ・バイナリ調査", "🌐"),
    18: ("Stage 18", "プロセス管理・暗号・コンテナ基盤・構成管理", "🧰"),
    19: ("Stage 19", "補完・性能計測・ログ・暗号基盤の総点検", "🔧"),
    20: ("Stage 20", "暗号化・VPN・SSHトンネル", "🔐"),
    21: ("Stage 21", "DNS・DHCP・メール・LDAP・負荷分散", "📡"),
    22: ("Stage 22", "仮想化・NAT・Kubernetes・IaC・監視", "☁️"),
    23: ("Stage 23", "バックアップ・DB・ストレージ応用・ログ運用", "🗃️"),
    24: ("Stage 24", "正規表現・シェル上級・パッケージ作成・カーネルビルド", "🛠️"),
    25: ("Stage 25", "ハッシュ・テキスト・シェル組み込みの総ざらい", "🔡"),
    26: ("Stage 26", "ファイルシステム・ブロックデバイス工具の総ざらい", "💽"),
    27: ("Stage 27", "プロセス・資源・システム情報の総ざらい", "🔬"),
    28: ("Stage 28", "ユーザー管理・systemd周辺・カーネルモジュール・設定ファイルの総ざらい", "👥"),
    29: ("Stage 29", "ネットワーク低レベル・パッケージ・マニュアル・SSH補助の総ざらい", "📚"),
    30: ("Stage 30", "Git実践（衝突・rebase・bisect・復旧・運用）", "🌿"),
    31: ("Stage 31", "Vim・nano・Emacsの実践", "📝"),
    32: ("Stage 32", "開発者ツールボックス（jq・curl・fzf・rg ほか）", "🧰"),
    33: ("Stage 33", "言語環境・ビルド・デバッグ・品質ツール", "🔨"),
    34: ("Stage 34", "SSH・tmux・リモート作業の実践", "🖥️"),
    EXTRA: ("Extra", "現場で一目置かれる小ネタ・時短術 (実践)", "✨"),
}


def practice_supported() -> bool:
    """実践モードは本物の bash と Linux コマンドを使う。Windows では WSL 上で起動する。"""
    return os.name != "nt"


def stage_dir(stage: int) -> Path:
    name = "stage_EX" if stage == EXTRA else f"stage_{stage:02d}"
    return WORKSPACE / name


# ---------------------------------------------------------------- Mission
class Fail(Exception):
    """判定失敗。メッセージはプレイヤーへのフィードバックとして表示される。"""


@dataclass
class Mission:
    id: str
    stage: int
    title: str
    story: str
    objectives: List[str]
    hints: List[str]            # 3段階: 考え方 → 使うコマンド → 具体的なオプション例
    answer: str                 # 模範解答コマンド
    explanation: str            # 模範解答の徹底解説
    tip: str                    # クリア時の実務ワンポイント
    setup: Callable
    check: Callable
    solution: str               # 自動テスト用の想定解 (bash)
    wrong: List[str] = field(default_factory=list)  # 自動テスト用の「惜しい誤答」(bash)
    docker: bool = False
    sim: bool = False           # True: bin/sim を PATH 先頭に追加（root 権限が必要なコマンドを安全に模擬）
    points: int = 100

    def render(self, text, data):
        for k, v in (data or {}).items():
            text = text.replace(f"<<{k}>>", str(v))
        return text


REGISTRY: List[Mission] = []


def register(**kw) -> Mission:
    m = Mission(**kw)
    if any(x.id == m.id for x in REGISTRY):
        raise ValueError(f"duplicate mission id {m.id}")
    REGISTRY.append(m)
    return m


_loaded = False


def load_curriculum():
    global _loaded
    if not _loaded:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import curriculum  # noqa: F401  (各ステージモジュールが register する)
        _loaded = True
    return REGISTRY


def get_mission(mid) -> Optional[Mission]:
    for m in load_curriculum():
        if m.id == mid:
            return m
    return None


def missions_of(stage):
    return [m for m in load_curriculum() if m.stage == stage]


# ---------------------------------------------------------------- process utils
def proc_alive(pid) -> bool:
    try:
        pid = int(pid)
        with open(f"/proc/{pid}/stat") as f:
            st = f.read().rsplit(")", 1)[1].split()[0]
        return st not in ("Z", "X")
    except (OSError, ValueError, IndexError, TypeError):
        return False


def proc_cmdline(pid) -> str:
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except (OSError, ValueError):
        return ""


def _ancestors():
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def kill_session(token):
    """LQ_SESSION=token を環境変数に持つプロセス（ミッション用プロセスやユーザーのジョブ）を全て停止。"""
    if not token:
        return
    needle = f"LQ_SESSION={token}".encode()
    skip = _ancestors()
    victims = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        pid = int(d)
        if pid in skip:
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = f.read().split(b"\0")
        except OSError:
            continue
        if needle in env:
            victims.append(pid)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        if sig == signal.SIGTERM and victims:
            time.sleep(0.15)


def free_port(lo=20000, hi=29999):
    for _ in range(200):
        port = random.randint(lo, hi)
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("free port not found")


def port_in_use(port) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", int(port)))
            return False
        except OSError:
            return True


def wait_port(port, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- sandbox
def _force_rmtree(path: Path):
    def onerr(func, p, exc):
        try:
            os.chmod(os.path.dirname(p), 0o700)
            os.chmod(p, 0o700)
        except OSError:
            pass
        try:
            func(p)
        except OSError:
            pass
    # 権限を剥奪されたディレクトリも消せるよう先に権限を戻す
    for dp, dns, fns in os.walk(path, onerror=lambda e: None):
        for n in dns:
            try:
                p = os.path.join(dp, n)
                if not os.path.islink(p):
                    os.chmod(p, 0o700)
            except OSError:
                pass
    shutil.rmtree(path, onerror=onerr)


def wipe_dir(d: Path):
    d = Path(d)
    assert WORKSPACE in d.parents or d == WORKSPACE, f"unsafe wipe: {d}"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o755)
    for child in d.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        else:
            _force_rmtree(child)


class Ctx:
    """setup / check から使う操作・検証 API。"""

    def __init__(self, mission: Mission, token=None):
        self.m = mission
        self.work = stage_dir(mission.stage)
        self.state = STATE
        self.token = token or self._session().get("token")
        self.data = self._load_json("data.json", {})

    # --- internal
    def _load_json(self, name, default):
        try:
            return json.loads((self.state / name).read_text())
        except (OSError, ValueError):
            return default

    def _session(self):
        return self._load_json("session.json", {})

    def save_data(self):
        (self.state / "data.json").write_text(json.dumps(self.data, ensure_ascii=False))

    # --- path / file helpers
    def p(self, rel) -> Path:
        return self.work / rel

    def write(self, rel, text="", mode=None, age_days=None, binary=False):
        path = self.p(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            path.write_bytes(text)
        else:
            path.write_text(text)
        if mode is not None:
            os.chmod(path, mode)
        if age_days is not None:
            self.age(rel, age_days)
        return path

    def sparse(self, rel, size_bytes, age_days=None):
        """実ディスクをほとんど消費しない巨大ファイル（du では見かけ上大きく見えないため、実データで書く）。"""
        path = self.p(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        chunk = b"\0" * 65536
        with open(path, "wb") as f:
            left = size_bytes
            while left > 0:
                n = min(left, len(chunk))
                f.write(chunk[:n])
                left -= n
        if age_days is not None:
            self.age(rel, age_days)
        return path

    def age(self, rel, days):
        t = time.time() - days * 86400
        os.utime(self.p(rel), (t, t), follow_symlinks=False)

    def mkdir(self, rel, mode=None):
        path = self.p(rel)
        path.mkdir(parents=True, exist_ok=True)
        if mode is not None:
            os.chmod(path, mode)
        return path

    def read(self, rel):
        try:
            return self.p(rel).read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            return None

    def lines(self, rel):
        t = self.read(rel)
        if t is None:
            return None
        return t.splitlines()

    def exists(self, rel):
        return os.path.lexists(self.p(rel))

    def isfile(self, rel):
        return self.p(rel).is_file()

    def isdir(self, rel):
        return self.p(rel).is_dir() and not self.p(rel).is_symlink()

    def mode(self, rel):
        return stat.S_IMODE(os.lstat(self.p(rel)).st_mode)

    # --- assertions
    def fail(self, msg):
        raise Fail(msg)

    def require(self, cond, msg):
        if not cond:
            raise Fail(msg)

    def need_file(self, rel, what=None):
        if not self.exists(rel):
            raise Fail(f"`{rel}` が見つかりません。{what or ''}")
        if self.isdir(rel):
            raise Fail(f"`{rel}` はディレクトリです。ファイルとして作成してください。")
        return self.read(rel) or ""

    # --- runtime state captured by the game shell (PROMPT_COMMAND)
    def submitted(self):
        try:
            return (self.state / "submitted").read_text().strip()
        except OSError:
            return None

    def need_submit(self, expected, label="答え", normalize=lambda s: s.strip()):
        s = self.submitted()
        if s is None or s == "":
            raise Fail(f"{label}をまだ提出していません。`submit <{label}>` で提出してください。")
        if normalize(s) != normalize(str(expected)):
            raise Fail(f"提出された{label}「{s}」は正しくありません。もう一度調べてみましょう。")

    def cwd(self):
        try:
            return Path((self.state / "cwd").read_text().strip())
        except OSError:
            return None

    def env(self):
        try:
            raw = (self.state / "env").read_bytes()
        except OSError:
            return {}
        out = {}
        for item in raw.split(b"\0"):
            if b"=" in item:
                k, v = item.split(b"=", 1)
                out[k.decode(errors="replace")] = v.decode(errors="replace")
        return out

    def history(self):
        try:
            return [ln for ln in (self.state / "history").read_text(errors="replace").splitlines()
                    if ln and not ln.startswith("#")]
        except OSError:
            return []

    def used(self, *words):
        """コマンド履歴にいずれかの語が含まれるか。"""
        hist = self.history()[self.data.get("_hist_start", 0):]
        return any(w in ln for ln in hist for w in words)

    def jobs(self):
        try:
            return (self.state / "jobs").read_text()
        except OSError:
            return ""

    def statuses(self):
        try:
            return [int(x) for x in (self.state / "statuses").read_text().split()]
        except (OSError, ValueError):
            return []

    # --- processes
    def spawn(self, name, body=None, argv=None, cwd=None, extra_env=None):
        """setsid + 二重 fork でミッション用のバックグラウンドプロセスを起動し PID を返す。
        body を渡すと state/procs/<name> にスクリプトを書き出して実行する (comm 名 = name)。"""
        if argv is None:
            procs = self.state / "procs"
            procs.mkdir(parents=True, exist_ok=True)
            script = procs / name
            script.write_text(body)
            os.chmod(script, 0o755)
            argv = [str(script)]
        env = dict(os.environ)
        env["LQ_SESSION"] = self.token or "none"
        env.update(extra_env or {})
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:  # child
            try:
                os.close(r)
                os.setsid()
                gpid = os.fork()
                if gpid == 0:  # grandchild
                    os.chdir(cwd or self.work)
                    fd = os.open(os.devnull, os.O_RDWR)
                    for i in (0, 1, 2):
                        os.dup2(fd, i)
                    os.closerange(3, 1024)
                    os.execvpe(argv[0], argv, env)
                os.write(w, str(gpid).encode())
            finally:
                os._exit(0)
        os.close(w)
        data = os.read(r, 64)
        os.close(r)
        os.waitpid(pid, 0)
        gpid = int(data.decode())
        self.data.setdefault("_pids", []).append(gpid)
        return gpid

    def alive(self, pid):
        return proc_alive(pid)

    def free_port(self, lo=20000, hi=29999):
        return free_port(lo, hi)

    # --- docker
    @property
    def docker(self):
        from engine import docker_backend
        return docker_backend.backend(self)

    # --- misc
    def rand(self, n=6, alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"):
        return "".join(secrets.choice(alphabet) for _ in range(n))


# ---------------------------------------------------------------- mission lifecycle
def prepare(mission: Mission, token: str):
    """ミッションのサンドボックスを初期化して setup を実行する。"""
    STATE.mkdir(parents=True, exist_ok=True)
    old = {}
    try:
        old = json.loads((STATE / "session.json").read_text())
    except (OSError, ValueError):
        pass
    if old.get("token") and old.get("token") != token:
        kill_session(old["token"])
    kill_session(token)
    # state をクリーンに（session/history は保持しつつ作り直す）
    for name in ("submitted", "cwd", "env", "jobs", "statuses", "data.json", "hints.json",
                 "cleared", "intent", "answer_viewed", "notified"):
        try:
            (STATE / name).unlink()
        except OSError:
            pass
    procs = STATE / "procs"
    if procs.exists():
        shutil.rmtree(procs, ignore_errors=True)
    if mission.docker:
        shutil.rmtree(STATE / "docker", ignore_errors=True)
    work = stage_dir(mission.stage)
    wipe_dir(work)
    (STATE / "session.json").write_text(json.dumps({
        "token": token, "mission": mission.id, "started": time.time(),
        "docker_mode": os.environ.get("LQ_DOCKER_MODE", ""),
    }))
    ctx = Ctx(mission, token)
    hist = STATE / "history"
    if not hist.exists():
        hist.write_text("")
    ctx.data["_hist_start"] = len(ctx.history())
    mission.setup(ctx)
    ctx.save_data()
    return ctx


def run_check(mission: Mission, token=None):
    ctx = Ctx(mission, token)
    try:
        mission.check(ctx)
        return True, ""
    except Fail as e:
        return False, str(e)
    except Exception as e:  # 予期せぬ状態（ファイルが壊れている等）も不正解扱い
        return False, f"判定中に想定外の状態を検出しました: {type(e).__name__}: {e}"


def new_token():
    # ローカルの学習セッションとプロセスを識別する値。外部 API の認証情報ではありません。
    return secrets.token_hex(8)


def shell_env(mission: Mission, token: str):
    env = dict(os.environ)
    path = env.get("PATH", "/usr/bin:/bin")
    from engine import docker_backend
    if mission.docker and docker_backend.detect_mode() == "mock":
        path = f"{MOCKBIN}:{path}"
    if mission.sim:
        path = f"{SIMBIN}:{path}"
    env.update({
        "PATH": path,
        "LQ_HOME": str(ROOT),
        "LQ_STATE": str(STATE),
        "LQ_WORKSPACE": str(WORKSPACE),
        "LQ_WORK": str(stage_dir(mission.stage)),
        "LQ_MISSION": mission.id,
        "LQ_SESSION": token,
        "LQ_DOCKER_MODE": docker_backend.detect_mode() if mission.docker else env.get("LQ_DOCKER_MODE", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LQ_PYTHON": sys.executable,
    })
    env.pop("PROMPT_COMMAND", None)
    return env


def launch_shell(mission: Mission, token: str) -> str:
    """本物の bash を専用 rc で起動。終了後に intent (next/menu/quit) を返す。"""
    env = shell_env(mission, token)
    try:
        (STATE / "intent").unlink()
    except OSError:
        pass
    subprocess.call(["bash", "--rcfile", str(SHELLRC), "-i"], cwd=str(stage_dir(mission.stage)), env=env)
    try:
        return (STATE / "intent").read_text().strip()
    except OSError:
        return "menu"
