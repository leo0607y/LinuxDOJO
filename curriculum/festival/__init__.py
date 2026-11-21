"""課題まつり：目的だけを読んで、自分で手順を組み立てる状態判定型の課題パック。

1つのテーマを1ファイルにまとめる。各ファイルは次の2つを定義する。
    PACK_TITLE = "テーマ名"
    SCENARIOS = [ {...}, ... ]   # 形式は curriculum/readiness.py と同じ

追加のキー（任意）
    level          1〜3（★の数。1=基本、2=組み合わせ、3=総合）
    alt_solutions  solution とは別の正解手順のリスト（テストで達成できることを確かめる）
    traps          正解にならない手順のリスト（テストで達成できないことを確かめる）
    expected_codes {コマンド: 終了コード}。0 以外が正しい手順（grep の不一致、no の回答など）

判定に使えるキー（engine/readiness.py の check()）
    expected_files / absent / expected_modes / min_lines   手元側のファイル
    remote_expected_files / remote_absent                  サーバー側のファイル
    packages / packages_absent                             入っている・入っていないソフト
    expected_env {名前: 値}（値が None なら「消えていること」）
    process_gone / process_kept                            止める・止めないプロセス
    checks_commands / checks_remote_commands               手元・サーバーで実行した確認コマンド
    ordered_commands                                       この順番で実行したか（候補はリストで書ける）
    require_disconnected                                   最後に手元へ戻っているか
課題の初期状態には modes {パス: 0o600} で権限も指定できる。
"""
import importlib
import pkgutil

_DEFAULTS = {"expected_files": {}, "expected_modes": {}, "packages": [], "remote_files": {},
             "require_disconnected": False, "checks_commands": [], "absent": [], "expected_env": {},
             "process_gone": [], "process_kept": [], "min_lines": {}, "alt_solutions": [], "traps": [],
             "level": 1, "files": {}}


# 学ぶ順番。ここにないパックは後ろに名前順で並ぶ。
ORDER = ["drills", "files", "logs", "config", "system", "sample_ops", "incident", "scenarios",
         "backup_ops", "network_ops", "operations", "scripting"]


def _rank(name):
    return (ORDER.index(name) if name in ORDER else len(ORDER), name)


def packs(only=None):
    """(パックの識別名, タイトル, 課題リスト) を学ぶ順番に返す。only でパックを1つに絞れる。"""
    found = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: _rank(m.name)):
        if info.name.startswith("_") or (only and info.name != only):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        for scenario in module.SCENARIOS:
            for key, value in _DEFAULTS.items():
                scenario.setdefault(key, type(value)() if isinstance(value, (dict, list)) else value)
            scenario["pack"] = info.name
        found.append((info.name, module.PACK_TITLE, module.SCENARIOS))
    return found
