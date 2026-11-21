"""Script authoring capstones; source/permissions are checked here, execution in Stage 6."""
from curriculum.units.scripting import LESSONS, write_command

PACK_TITLE = "自動化スクリプトの準備"


def _scenario(number, title, source_step, brief, explanation):
    name, source = source_step["source_file"], source_step["source"]
    create = write_command(name, source)
    solution = [create, "chmod 755 " + name, "cat " + name]
    return {
        "id": f"fes-scripting-{number:02d}", "level": 3, "title": title,
        "brief": brief + "\nこの課題は保存内容・権限・確認操作の判定です。"
                 "スクリプトは模擬環境では実行しません。実行して検証する練習は実践 Stage 6 で行います。",
        "files": {name: "#!/bin/bash\n# TODO\n"},
        "modes": {name: 0o644},
        "expected_files": {name: source}, "expected_modes": {name: 0o755},
        "checks_commands": ["cat " + name],
        "solution": solution,
        "alt_solutions": [[create, "chmod u=rwx,go=rx " + name, "cat " + name]],
        "traps": [["chmod 755 " + name, "cat " + name],
                  [create, "cat " + name],
                  [create, "chmod 755 " + name]],
        "hints": ["入力の検証、通常処理、失敗時の扱いを先に整理し、保存してから権限と内容を確認します。",
                  "達人モードのスクリプト作成を組み合わせます。保存後に chmod で所有者を rwx、グループと他の人を rx にし、cat で読み直します。",
                  "入力例: " + " → ".join(solution)],
        "explanation": explanation + " 文面の確認と実行時の検証は別です。Stage 6 で実際の入力と終了コードを確認しましょう。",
        "practice": ["6-1", "6-2"],
    }


SCENARIOS = [
    _scenario(1, "ログ報告スクリプトをレビューできる状態にする", LESSONS[16],
              "report.sh を作成してください。先頭はBash用のshebangにします。"
              "引数が1個でなければ2、指定先が通常ファイルでなければ1で終了します。"
              "ERRORを含む行を抽出し、検索の終了コードを status に保存します。"
              "status が1より大きければその値で終了し、それ以外は0で終了してください。"
              "権限を755にし、保存後の本文を読んで確認してください。",
              "引数の誤り、存在しないファイル、検索結果0件、検索処理の失敗を整理したスクリプトです。"),
    _scenario(2, "空白入り引数を壊さない処理を用意する", LESSONS[3],
              "arguments.sh を作成してください。先頭はBash用のshebangにします。"
              "全引数を受け取り、item を繰り返し変数として、1引数につき1行ずつ表示します。"
              "引数の境界を保つ展開と、引用した変数の表示を使ってください。"
              "権限を755にし、保存後の本文を読んで確認してください。",
              "引数ごとの区切りを保つことで、空白やワイルドカード文字を含むファイル名も安全に渡せる形になります。"),
]
