"""基本操作を組み合わせて解く総合復習。実践ミッションとは別枠で進捗を保存する。"""
from pathlib import Path
import shlex
import shutil

from engine import guided, runner, save, ui


def scenarios():
    """総合復習の8課題と、課題まつりの全パックの課題。"""
    from curriculum.readiness import SCENARIOS
    from curriculum.festival import packs
    return SCENARIOS + [scenario for _, _, items in packs() for scenario in items]


def prepare(scenario, root, progress=None):
    directory = Path(root) / scenario["id"]
    if directory.is_symlink():
        raise guided.TrainingError("復習フォルダにシンボリックリンクは使えません。")
    if directory.exists():
        shutil.rmtree(directory)
    state = progress if progress is not None else {}
    state.clear()
    terminal = guided.Terminal(directory, state)
    guided.prepare_step(terminal, {**scenario, "cwd": scenario.get("cwd", "."), "remote": False,
                                  "files": scenario["files"], "remote_files": scenario["remote_files"],
                                  "packages": scenario.get("initial_packages", []),
                                  "apt_updated": scenario.get("apt_updated", False),
                                  "processes": scenario.get("processes", []), "env": scenario.get("env", {}),
                                  "modes": scenario.get("modes", {})})
    return terminal


def _ordered(terminal, steps):
    """steps（文字列か候補のリスト）が、成功したコマンドの中でこの順番に現れたか。"""
    events = [e for e in terminal.progress.get("command_events", []) if e["code"] == 0 and e["host"] == "dojo-local"]
    position = 0
    for step in steps:
        options = [step] if isinstance(step, str) else step
        while position < len(events):
            try:
                typed = shlex.split(events[position]["line"])
            except ValueError:
                typed = None
            position += 1
            if typed is not None and any(typed == shlex.split(option) for option in options):
                break
        else:
            return False
    return True


def _ran(terminal, alternatives, host):
    """確認用のコマンドを、成功する形で実行したか。alternatives は1つの文字列か候補のリスト。"""
    options = [alternatives] if isinstance(alternatives, str) else alternatives
    for event in terminal.progress.get("command_events", []):
        if event["code"] != 0 or event["host"] != host:
            continue
        try:
            typed = shlex.split(event["line"])
        except ValueError:
            continue
        if any(typed == shlex.split(option) for option in options):
            return True
    return False


def check(scenario, terminal):
    try:
        if terminal.progress.get("editor"):
            return False, "vim がまだ開いています。:wq で保存して閉じてから check しましょう。"
        from engine import commands
        problem = commands.check(scenario, terminal)
        if problem:
            return problem
        if scenario["require_disconnected"] and terminal.progress["remote"]:
            return False, "まだ接続先にいます。exit で手元へ戻りましょう。"
        for name, content in scenario["expected_files"].items():
            path = terminal._side_path("/home/learner/" + name, False)
            if not path.is_file():
                return False, f"{name} がありません。目的文の保存先を確認しましょう。"
            if path.read_text(encoding="utf-8") != content:
                return False, f"{name} の内容が要件と違います。cat で確認しましょう。"
        for name, count in scenario["min_lines"].items():
            path = terminal._side_path("/home/learner/" + name, False)
            if not path.is_file():
                return False, f"{name} がありません。目的文の保存先を確認しましょう。"
            if len([x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]) < count:
                return False, f"{name} の内容が足りません。{count}行以上書きましょう。"
        for name, mode in scenario["expected_modes"].items():
            if terminal.mode_of(terminal._side_path("/home/learner/" + name, False)) != mode:
                return False, f"{name} の権限が要件と違います。ls -l と chmod を確認しましょう。"
        for name in scenario["absent"]:
            if terminal._side_path("/home/learner/" + name, False).exists():
                return False, f"{name} がまだ残っています。削除対象を確認しましょう。"
        for package in scenario["packages"]:
            if package not in terminal.progress["packages"]:
                return False, f"{package} がまだ追加されていません。情報一覧の更新と本体追加は別の操作です。"
        for package in scenario.get("packages_absent", []):
            if package in terminal.progress["packages"]:
                return False, f"{package} がまだ入っています。不要なソフトは apt remove で取り除きます。"
        for name, content in scenario.get("remote_expected_files", {}).items():
            path = terminal._side_path("/home/learner/" + name, True)
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                return False, f"サーバー側の {name} が要件と違います。ssh で入って確かめましょう。"
        for name in scenario.get("remote_absent", []):
            if terminal._side_path("/home/learner/" + name, True).exists():
                return False, f"サーバー側の {name} がまだ残っています。"
        for name, value in scenario["expected_env"].items():
            # value が None なら「その環境変数が残っていないこと」を確かめる。
            if terminal.progress["env"].get(name) != value:
                if value is None:
                    return False, f"環境変数 {name} がまだ残っています。unset で消しましょう。"
                return False, f"環境変数 {name} が要件と違います。export と env で確認しましょう。"
        running = [p["cmd"] for p in terminal.progress["processes"]]
        for name in scenario["process_gone"]:
            if any(name in cmd for cmd in running):
                return False, f"{name} がまだ動いています。ps aux で確かめましょう。"
        for name in scenario["process_kept"]:
            if not any(name in cmd for cmd in running):
                return False, f"止めてはいけない {name} まで止まっています。reset でやり直しましょう。"
        for command in scenario["checks_commands"]:
            host = "training-server" if scenario["id"] == "ready-06" and command in ("hostname", "cat server-note.txt") else "dojo-local"
            if not _ran(terminal, command, host):
                return False, "目的文にある作業後の確認がまだです。接続先や結果を確かめましょう。"
        for command in scenario.get("checks_remote_commands", []):
            if not _ran(terminal, command, "training-server"):
                return False, "接続先での確認がまだです。ssh で入ってから確かめましょう。"
        if scenario.get("ordered_commands") and not _ordered(terminal, scenario["ordered_commands"]):
            return False, "手順の順番が要件と違います。何を先にするべきか、目的文をもう一度読みましょう。"
        return True, "目的に合う状態にできました。"
    except (OSError, ValueError, guided.TrainingError):
        return False, "ファイルの場所や種類を確認しましょう。reset で課題を最初から復元できます。"


def record_result(scenario, assisted):
    d = save.load()
    progress = d["learning"].setdefault("readiness", {"completed": {}, "sessions": {}})
    completed = progress.setdefault("completed", {})
    old = completed.get(scenario["id"])
    if old is None or not assisted:
        completed[scenario["id"]] = {"assisted": bool(assisted)}
    save.store(d)


def persist(scenario, terminal, assisted):
    d = save.load()
    progress = d["learning"].setdefault("readiness", {"completed": {}, "sessions": {}})
    progress["active"] = scenario["id"]
    progress.setdefault("sessions", {})[scenario["id"]] = {"terminal": terminal.progress, "assisted": assisted}
    save.store(d)


def play(scenario):
    root = runner.WORKSPACE / "learning_readiness"
    d = save.load()
    previous = d["learning"].get("readiness", {}).get("sessions", {}).get(scenario["id"])
    if previous and (root / scenario["id"]).is_dir():
        terminal = guided.Terminal(root / scenario["id"], previous["terminal"])
        assisted = previous["assisted"]
    else:
        terminal = prepare(scenario, root)
        assisted = False
    hint_level = 0
    header = [scenario["title"], scenario["brief"], "",
              "目的に合わせて複数のコマンドを組み合わせ、check で判定します。",
              "ヒントなしでできるか試してみましょう。hint / answer も使えます。",
              "模擬環境なので実際の PC やサーバーは操作しません。",
              "mission: 目的再表示 / hint: ヒント / answer: 手順 / reset: やり直し / menu: 保存して戻る"]
    with ui.QuestionScreen(header, summary=[scenario["title"], scenario["brief"]]) as screen:
        persist(scenario, terminal, assisted)
        while True:
            screen.refresh()
            try:
                raw = input("\n 復習 " + terminal.prompt_text())
            except (EOFError, KeyboardInterrupt):
                persist(scenario, terminal, assisted)
                return
            line = raw.strip()
            if line in ("menu", "quit"):
                persist(scenario, terminal, assisted)
                return
            if line == "mission":
                print(scenario["brief"])
                continue
            if line == "reset":
                terminal = prepare(scenario, root)
                hint_level = 0
                assisted = False
                persist(scenario, terminal, assisted)
                print("この課題の作業場所を初期状態に戻しました。")
                continue
            if line == "hint":
                assisted = True
                print(scenario["hints"][min(hint_level, 2)])
                hint_level += 1
                persist(scenario, terminal, assisted)
                continue
            if line == "answer":
                assisted = True
                print("\n".join(scenario["solution"]))
                persist(scenario, terminal, assisted)
                continue
            if line == "check":
                good, message = check(scenario, terminal)
                print(message)
                if good:
                    record_result(scenario, assisted)
                    print(ui.c(f"{ui.OK} 総合復習クリア！ " + ("手本ありで達成。reset で自力の復習もできます。" if assisted else "ヒントなしで達成できました。"), "bgreen"))
                    print(scenario["explanation"])
                    print("本物の bash で試す次の問題: " + " / ".join(scenario["practice"]))
                continue
            result = terminal.execute(raw.rstrip("\r") if terminal.progress.get("editor") else line)
            if result.output:
                print(result.output)
            persist(scenario, terminal, assisted)


# ---------------------------------------------------------------- 自由自在マップ
def _lesson_ids(mode, first=None, last=None, unit=None):
    ids = []
    for step in guided.lessons(mode):
        number = int(step["id"].rsplit("-", 1)[1])
        if unit is not None and step.get("unit") != unit:
            continue
        if first is not None and not first <= number <= last:
            continue
        ids.append(step["id"])
    return ids


def _practice(*prefixes):
    from engine.main import all_missions
    return [m.id for m in all_missions() if m.id.startswith(prefixes)]


def _pack(name):
    from curriculum.festival import packs
    return [s["id"] for pack, _, items in packs() if pack == name for s in items]


def _expert(*units):
    return [s["id"] for s in guided.lessons("expert")
            if s["id"].startswith(tuple(f"ex-{unit}-" for unit in units))]


def mastery_areas():
    """(分野名, レッスンID, 総合復習・課題まつりのID, 実践ミッションID) の一覧。"""
    from curriculum import advanced_lessons as adv
    return [
        ("ファイルとフォルダを自在に整理する",
         _lesson_ids("intro") + _lesson_ids("basic", 1, 19) + _lesson_ids("advanced", unit=adv._WILD) + _expert("archive_find"),
         ["ready-01", "ready-04"] + _pack("files"), _practice("1-")),
        ("ログやデータを検索・集計する",
         _lesson_ids("basic", 25, 32) + _lesson_ids("advanced", unit=adv._PIPE) + _lesson_ids("advanced", unit=adv._GREP) + _expert("textproc"),
         ["ready-02", "ready-07"] + _pack("logs"), _practice("2-", "EX-3", "EX-5")),
        ("vim で設定ファイルを書き換える",
         _lesson_ids("basic", 49, 66) + _lesson_ids("advanced", unit=adv._VIM),
         ["ready-03"] + _pack("config"), _practice("6-6", "3-1", "3-2")),
        ("プロセス・容量・環境・ソフトを管理する",
         _lesson_ids("basic", 20, 24) + _lesson_ids("advanced", unit=adv._ENV) + _lesson_ids("advanced", unit=adv._PROC)
         + _lesson_ids("advanced", unit=adv._DISK) + _expert("sample_unit"),
         ["ready-05", "ready-08"] + _pack("system") + _pack("sample_ops"), _practice("3-3", "3-4", "3-5", "3-6", "3-7", "3-8")),
        ("リモート作業と障害対応",
         _lesson_ids("basic", 33, 48) + _expert("network"), ["ready-06"] + _pack("incident"), _practice("4-")),
        ("自動化・サービス・コンテナ（実践）",
         _expert("services", "scripting"), [], _practice("5-", "6-1", "6-2", "6-3", "6-4", "6-5", "6-7", "6-8", "7-", "EX-1", "EX-2", "EX-4")),
        ("ユーザー・グループ・アクセス権を管理する", _expert("users"), [], []),
        ("Git で変更を記録・復旧する", _expert("git"), [], []),
        ("目的から手順を組み立てる総合演習", [],
         _pack("drills") + _pack("scenarios") + _pack("operations") + _pack("network_ops") + _pack("scripting") + _pack("backup_ops"), []),
        ("Web の認証・認可・設定を検証する", [], [], _practice("8-")),
        ("Linux の安全性を監査・修正する", [], [], _practice("9-")),
        ("証拠を保全して調査・報告する", [], [], _practice("10-")),
        ("ストレージ・起動・復旧を診断する", [], [], _practice("11-")),
        ("性能・更新・高度な権限を調べる", [], [], _practice("12-")),
        ("通信・TLS・データと構成を管理する", [], [], _practice("13-")),
        ("ブート・カーネル・ハードウェアを実践する", [], [], _practice("14-")),
        ("ストレージ構築・LVM・RAIDを実践する", [], [], _practice("15-")),
        ("SELinux・ACL・属性・資源制限を実践する", [], [], _practice("16-")),
        ("ネットワーク管理・共有・パッケージ・バイナリ調査を実践する", [], [], _practice("17-")),
        ("プロセス管理・暗号・コンテナ基盤・構成管理を実践する", [], [], _practice("18-")),
        ("補完・性能計測・ログ・暗号基盤の総点検を実践する", [], [], _practice("19-")),
        ("暗号化・VPN・SSHトンネルを実践する", [], [], _practice("20-")),
        ("DNS・DHCP・メール・LDAP・負荷分散を実践する", [], [], _practice("21-")),
        ("仮想化・NAT・Kubernetes・IaC・監視を実践する", [], [], _practice("22-")),
        ("バックアップ・DB・ストレージ応用・ログ運用を実践する", [], [], _practice("23-")),
        ("正規表現・シェル上級・パッケージ作成・カーネルビルドを実践する", [], [], _practice("24-")),
        ("ハッシュ・テキスト・シェル組み込みの総ざらいを実践する", [], [], _practice("25-")),
        ("ファイルシステム・ブロックデバイス工具の総ざらいを実践する", [], [], _practice("26-")),
        ("プロセス・資源・システム情報の総ざらいを実践する", [], [], _practice("27-")),
        ("ユーザー管理・systemd周辺・カーネルモジュール・設定ファイルの総ざらいを実践する", [], [], _practice("28-")),
        ("ネットワーク低レベル・パッケージ・マニュアル・SSH補助の総ざらいを実践する", [], [], _practice("29-")),
        ("Git実践（衝突・rebase・bisect・復旧・運用）を実践する", [], [], _practice("30-")),
        ("Vim・nano・Emacsを実践する", [], [], _practice("31-")),
        ("開発者ツールボックス（jq・curl・fzf・rg ほか）を実践する", [], [], _practice("32-")),
        ("言語環境・ビルド・デバッグ・品質ツールを実践する", [], [], _practice("33-")),
        ("SSH・tmux・リモート作業を実践する", [], [], _practice("34-")),
    ]


def mastery(d=None):
    """分野ごとの (名前, 達成数, 全体数) と全体の割合。"""
    d = d or save.load()
    lessons_done = set()
    for mode in guided.GUIDED_MODES:
        lessons_done |= set(d["learning"].get(mode, {}).get("completed", []))
    challenges_done = set(d["learning"].get("readiness", {}).get("completed", {}))
    cleared = set(d["cleared"])
    rows, done_all, total_all = [], 0, 0
    for name, lessons, challenges, missions in mastery_areas():
        done = len(set(lessons) & lessons_done) + len(set(challenges) & challenges_done) + len(set(missions) & cleared)
        total = len(lessons) + len(challenges) + len(missions)
        rows.append((name, done, total))
        done_all += done
        total_all += total
    return rows, (done_all / total_all if total_all else 0.0)


def mastery_lines(d=None):
    d = d or save.load()
    rows, ratio = mastery(d)
    lines = [f"Linux 自由自在度  {ui.progress_bar(ratio, 20)} {ratio * 100:.0f}%"]
    for name, done, total in rows:
        lines.append(f"  {ui.pad(ui.clip(name, 40), 40)} {ui.progress_bar(done / total if total else 0, 10)} {done}/{total}")
    records = d["learning"].get("readiness", {}).get("completed", {})
    challenge_ids = {s["id"] for s in scenarios()}
    independent = sum(records.get(key, {}).get("assisted") is False for key in challenge_ids)
    lines.append(f"  手本なしで解けた総合課題: {independent}/{len(challenge_ids)}（hint / answer を使った課題は復習できます）")
    if ratio >= 1 and independent == len(challenge_ids):
        lines.append(ui.c("すべて制覇！ Linux 自由自在マスターです。", "bold", "bmagenta"))
    else:
        lines.append("全分野の学習と、手本なしの総合課題に取り組み、実践モードで本物の bash でも確かめましょう。")
    return lines


# ---------------------------------------------------------------- 課題まつりのメニュー
def _groups():
    from curriculum.festival import packs
    from curriculum.readiness import SCENARIOS
    return [("基本の総合復習", SCENARIOS)] + [(title, items) for _, title, items in packs()]


def _status(completed, scenario_id):
    result = completed.get(scenario_id)
    return "・未達成" if result is None else "△手本あり" if result["assisted"] else "◎自力達成"


def _choose_in_group(title, items):
    while True:
        ui.clear()
        completed = save.load()["learning"].get("readiness", {}).get("completed", {})
        print(f"\n  {title} — * は難しさ（* 基本 / ** 組み合わせ / *** 総合）\n")
        for index, scenario in enumerate(items, 1):
            stars = "*" * scenario.get("level", 1)
            print(f"  [{index:>2}] {ui.pad(stars, 4)} {ui.pad(scenario['title'], 44)} {_status(completed, scenario['id'])}")
        try:
            choice = input("\n  課題番号 / Enter: 次の未達成 / b: 戻る > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice in ("b", "q", "menu"):
            return
        if choice == "":
            target = next((s for s in items if s["id"] not in completed), None)
            if target is None:
                print("  このパックはすべて達成済みです。番号を選んで復習できます。")
                continue
            play(target)
        elif choice.isdigit() and 1 <= int(choice) <= len(items):
            play(items[int(choice) - 1])


def run():
    while True:
        ui.clear()
        d = save.load()
        progress = d["learning"].get("readiness", {})
        completed = progress.get("completed", {})
        groups = _groups()
        total = sum(len(items) for _, items in groups)
        solo = sum(1 for _, items in groups for s in items if completed.get(s["id"], {"assisted": True})["assisted"] is False)
        print(ui.box(["目的だけを読み、自分で手順を組み立てる力試しです。正解の手順は1つではありません。",
                      f"全 {total} 課題（自力達成 {solo}）。hint や answer を使った達成は △ で記録します。", "",
                      *mastery_lines(d)], title="課題まつり・Linux 自由自在マップ", color="green"))
        for index, (title, items) in enumerate(groups, 1):
            done = sum(1 for s in items if s["id"] in completed)
            mine = sum(1 for s in items if s["id"] in completed and not completed[s["id"]]["assisted"])
            print(f"  [{index}] {ui.pad(title, 36)} {ui.progress_bar(done / len(items), 10)} {done}/{len(items)}（自力 {mine}）")
        try:
            choice = input("\n  パック番号 / Enter: 前回の課題 / b: メニューへ > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice in ("b", "q", "menu"):
            return
        if choice == "":
            active = progress.get("active")
            target = next((s for s in scenarios() if s["id"] == active), scenarios()[0])
            play(target)
        elif choice.isdigit() and 1 <= int(choice) <= len(groups):
            _choose_in_group(*groups[int(choice) - 1])
