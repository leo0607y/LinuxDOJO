"""達人モードのユニット。1テーマ1ファイルで、ここに置くだけで自動的に読み込まれる。

各ファイルは次を定義する（見本: curriculum/units/sample_unit.py）。
    UNIT_TITLE = "ユニット名"            # レッスン選択に出る見出し。unit キーにも入る
    ORDER = 10                            # 小さいほど先に学ぶ
    LESSONS = [lesson(...), ...]          # curriculum.lesson_kit.lesson で作る
レッスン id は "ex-<ファイル名>-NN"（NN は 01 から）にする。
"""
import importlib
import pkgutil


def expert_lessons():
    units = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        units.append((getattr(module, "ORDER", 100), info.name, module))
    lessons = []
    for _, name, module in sorted(units, key=lambda x: (x[0], x[1])):
        for step in module.LESSONS:
            step.setdefault("unit", module.UNIT_TITLE)
            step.setdefault("cwd", ".")
            step.setdefault("remote", False)
            step.setdefault("ssh_known", False)
            step.setdefault("ssh_pending", False)
            lessons.append(step)
    return lessons
