"""Offline, real pip/venv lifecycle. No host pip installs or downloaded code."""
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import zipfile


def _run(root, *command):
    env = dict(os.environ, PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONNOUSERSITE="1")
    result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise ValueError("実行失敗: " + " ".join(map(str, command)) + "\n" + result.stderr[-700:])
    return result.stdout


def _wheel(root, version, value):
    dist = "dojo_demo-" + version + ".dist-info"
    files = {
        "dojo_demo/__init__.py": (
            '__version__ = ' + repr(version) + '\n'
            'def value():\n    return ' + repr(value) + '\n'
        ).encode(),
        dist + "/METADATA": (
            "Metadata-Version: 2.1\nName: dojo-demo\nVersion: " + version + "\n"
            "Summary: Disposable offline LinuxDOJO exercise\nRequires-Python: >=3.8\n\n"
        ).encode(),
        dist + "/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: LinuxDOJO\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode(),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + digest, str(len(data))])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = record.getvalue().encode()
    destination = root / "wheels" / ("dojo_demo-" + version + "-py3-none-any.whl")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, data in files.items():
            wheel.writestr(name, data)
    return destination


def setup(root):
    # Command existence alone cannot detect Debian's separately packaged ensurepip.
    try:
        _run(root, "python3", "-m", "ensurepip", "--version")
    except (OSError, ValueError) as error:
        raise ValueError("pip付きvenvを作る機能がありません。Ubuntu/Debianでは "
                         "sudo apt install python3-venv を確認します。模擬pipへは切り替えません。") from error
    _run(root, sys.executable, "-I", "-c",
         "import importlib.util; assert importlib.util.find_spec('dojo_demo') is None, "
         "'OS Python already contains dojo_demo; use a clean exercise environment'")
    (root / "wheels").mkdir()
    token = secrets.token_hex(12)
    originals = {}
    for version in ("1.0", "2.0"):
        wheel = _wheel(root, version, token + ":" + version)
        originals[wheel.relative_to(root).as_posix()] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (root / "requirements.txt").write_text("dojo-demo==1.0\n", encoding="utf-8")
    originals["requirements.txt"] = hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()
    (root / ".python-fixture.json").write_text(
        json.dumps({"token": token, "originals": originals}), encoding="utf-8")


def check(root):
    fixture = json.loads((root / ".python-fixture.json").read_text(encoding="utf-8"))
    for name, digest in fixture["originals"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(name + " は配布した原本のまま保持します。")
    interpreter = root / ".venv/bin/python"
    if not interpreter.is_file() or not (root / ".venv/pyvenv.cfg").is_file():
        raise ValueError("python3 -m venv .venv でpip付きの仮想環境を作ります。")
    info = json.loads(_run(root, str(interpreter), "-I", "-c",
        "import json,sys,dojo_demo; "
        "print(json.dumps({'prefix':sys.prefix,'base':sys.base_prefix,"
        "'file':dojo_demo.__file__,'version':dojo_demo.__version__,'value':dojo_demo.value()}))"))
    if (Path(info["prefix"]).resolve() != (root / ".venv").resolve()
            or info["prefix"] == info["base"]):
        raise ValueError("OS Pythonではなく、この実習の.venvを使います。")
    if not Path(info["file"]).resolve().is_relative_to((root / ".venv").resolve()):
        raise ValueError("実際のvenv内へインストールしたパッケージを読み込みます。")
    if info["version"] != "2.0" or info["value"] != fixture["token"] + ":2.0":
        raise ValueError("ローカルwheelからdojo-demoを2.0へ更新し、実際にimportします。")
    for filename, version in (("v1.txt", "1.0"), ("v2.txt", "2.0")):
        if (root / filename).read_text(encoding="utf-8").strip() != fixture["token"] + ":" + version:
            raise ValueError(filename + " にその版のdojo_demo.value()の実行結果を保存します。")
    show = _run(root, str(interpreter), "-m", "pip", "show", "dojo-demo")
    if "Version: 2.0\n" not in show:
        raise ValueError("pip showでインストール済みの版を確認します。")
    freeze = _run(root, str(interpreter), "-m", "pip", "freeze").strip()
    locked = (root / "requirements.lock").read_text(encoding="utf-8").strip()
    if freeze != "dojo-demo==2.0" or locked != freeze:
        raise ValueError("pip freezeの結果をrequirements.lockへ保存し、更新した版を固定します。")
    _run(root, sys.executable, "-I", "-c",
         "import importlib.util; assert importlib.util.find_spec('dojo_demo') is None, "
         "'dojo_demo must not be installed into OS Python'")


LABS = {
    "python-packages": {
        "title": "Pythonのvenvとpipで導入・利用・更新・版固定を行う",
        "tools": ["bash", "python3"],
        "packages": ["bash", "python3", "python3-venv"],
        "task": (
            "本物のvenvとpipを使います。教材が作ったwheels内の2つのwheelだけを使い、ネット接続は不要です。\n"
            "1. python3 -m venv .venv でpip付き仮想環境を作る。activateは省略して.venv/bin/pythonを明示しても同じです。\n"
            "2. .venvのpipで --no-index --find-links wheels -r requirements.txt を使いdojo-demo 1.0を導入。\n"
            "   .venvのPythonで import dojo_demo; print(dojo_demo.value()) の結果をv1.txtへ。\n"
            "3. 同じローカルwheel置場からdojo-demo==2.0へ更新し、実行結果をv2.txtへ。\n"
            "4. pip showで版と導入先を確認。pip freezeをrequirements.lockへ保存し、2.0への更新を固定。\n"
            "5. OSのPythonへdojo_demoを追加していないことを確認。原本wheelとrequirements.txtは変更禁止。\n"
            "未導入ならUbuntu/Debianではpython3-venvを導入。pipはOSへsudoで追加せず.venv内で使います。\n"
            "check完了後の撤去練習: .venv/bin/python -m pip uninstall dojo-demo → import失敗を確認。\n"
            "再現練習: 同じpipで --no-index --find-links wheels -r requirements.lock を再導入してcheck。\n"
            "アンインストール前にcheckしてください。検査時は2.0が.venv内に導入されている必要があります。"
        ),
        "setup": setup,
        "check": check,
        "solution": """set -euo pipefail
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --no-index --find-links wheels -r requirements.txt
.venv/bin/python -I -c 'import dojo_demo; print(dojo_demo.value())' > v1.txt
.venv/bin/python -m pip --isolated install --no-index --find-links wheels dojo-demo==2.0
.venv/bin/python -I -c 'import dojo_demo; print(dojo_demo.value())' > v2.txt
.venv/bin/python -m pip --isolated show dojo-demo
.venv/bin/python -m pip --isolated freeze > requirements.lock
""",
        "wrong": [
            "python3 -m venv .venv; .venv/bin/python -m pip --isolated install --no-index --find-links wheels -r requirements.txt; "
            ".venv/bin/python -I -c 'import dojo_demo; print(dojo_demo.value())' > v1.txt; cp v1.txt v2.txt; "
            ".venv/bin/python -m pip --isolated freeze > requirements.lock"
        ],
    }
}
