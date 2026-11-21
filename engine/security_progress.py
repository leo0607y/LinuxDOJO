"""実践のセキュリティ分野を、クリアと手本なしの検証に分けて表示する。"""
from engine import runner, save

SECURITY_STAGES = (8, 9, 10)


def progress(data=None):
    data = data if data is not None else save.load()
    cleared = data.get("cleared", {})
    rows = []
    for stage in SECURITY_STAGES:
        ids = {m.id for m in runner.missions_of(stage)}
        completed = ids & cleared.keys()
        independent = {mid for mid in completed
                       if cleared[mid].get("hints") == 0 and cleared[mid].get("answer") is False}
        rows.append({"stage": stage, "name": runner.STAGES[stage][1], "total": len(ids),
                     "completed": len(completed), "independent": len(independent)})
    return rows


def lines(data=None):
    rows = progress(data)
    output = ["セキュリティ実践（許可された教材環境で検証）"]
    for row in rows:
        output.append(f"  Stage {row['stage']}: {row['name']}  "
                      f"クリア {row['completed']}/{row['total']}・手本なし {row['independent']}/{row['total']}")
    total = sum(row["total"] for row in rows)
    independent = sum(row["independent"] for row in rows)
    if total and independent == total:
        output.append("  セキュリティ演習をすべて手本なしで修了しました。調査・修正・再検証・報告の成果物も読み返しましょう。")
    else:
        output.append("  ヒントや解答を使った課題は、あとで手本なしでもう一度検証できます。")
    return output
