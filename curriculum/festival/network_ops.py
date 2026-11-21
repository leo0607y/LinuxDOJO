"""ネットワークとサービスの総合課題。目的と制約から手順を組み立てる。"""
PACK_TITLE = "ネットワークとサービスの運用"


def S(n, title, brief, solution, thinking, tool, explanation, **extra):
    return {"id": f"fes-network_ops-{n:02d}", "level": 3, "title": title, "brief": brief,
            "files": {}, "solution": solution,
            "hints": [thinking, tool, "入力例: " + " → ".join(solution)],
            "explanation": explanation, "practice": ["4-3", "7-1"], **extra}


SCENARIOS = [
    S(1, "通信を層ごとに確かめる",
      "アプリ確認の記録を作ります。まず自分のアドレスと経路を表示してください。example.com の IPv4 の DNS 回答だけを dns.txt に、"
      "http://app.test:8080/health の本文を health.txt に保存し、両方のファイルを読み返してください。ソフトは導入済みです。",
      ["ip -br addr", "ip route", "dig +short example.com A > dns.txt", "curl -s http://app.test:8080/health > health.txt", "cat dns.txt", "cat health.txt"],
      "自分の接続、名前の変換、アプリの応答を分けて調べて記録します。", "アドレスと経路は ip、DNS は dig、HTTP は curl、読み返す道具は cat です。",
      "DNS の成功だけでアプリの正常性は分かりません。層を分け、実際の応答も保存すると引き継ぎに役立ちます。",
      initial_packages=["dnsutils", "curl"], expected_files={"dns.txt": "203.0.113.10\n", "health.txt": "OK\n"},
      checks_commands=[["ip -br addr", "ip addr", "ip a"], ["ip route", "ip r", "ip route show"], "cat dns.txt", "cat health.txt"],
      alt_solutions=[["ip addr", "ip route show", "dig example.com A +short > dns.txt", "curl -s -o health.txt http://app.test:8080/health", "cat dns.txt", "cat health.txt"]],
      traps=[["dig +short example.com A > dns.txt", "curl -s http://app.test:8080/health > health.txt"]]),
    S(2, "管理用の入口を守る",
      "現在、ファイアウォールは停止中です。受信の既定を拒否にし、TCP 22 番はすべての送信元から、TCP 8080 番は 192.0.2.10 からだけ許可してください。"
      "22 番を許可してから有効化し、最後に詳しい状態を表示してください。他の許可ルールは不要です。",
      ["sudo ufw default deny incoming", "sudo ufw allow 22/tcp", "sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw enable", "sudo ufw status verbose"],
      "管理用の接続を確保してから有効化します。アプリは必要な送信元だけに公開します。", "ufw の default・allow・enable・status を使います。from と proto で条件を絞れます。",
      "必要な入口だけを許可し、現在の接続を失わない順序も確認しました。実運用では別接続での確認と復旧経路も用意します。",
      expected_ufw={"active": True, "incoming": "deny", "rules": [["22/tcp", "ALLOW", "Anywhere"], ["8080/tcp", "ALLOW", "192.0.2.10"]]},
      ordered_commands=[["sudo ufw allow 22/tcp", "sudo ufw allow ssh"], "sudo ufw enable"], checks_commands=["sudo ufw status verbose"],
      alt_solutions=[["sudo ufw allow ssh", "sudo ufw default deny incoming", "sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw enable", "sudo ufw status verbose"]],
      traps=[["sudo ufw allow 22/tcp", "sudo ufw allow 8080/tcp", "sudo ufw enable", "sudo ufw status verbose"],
             ["sudo ufw enable", "sudo ufw allow 22/tcp", "sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw status verbose"]]),
    S(3, "不要な公開だけを閉じる",
      "ファイアウォールは有効ですが、TCP 8080 番が全世界へ公開されています。これを 192.0.2.10 からだけに限定してください。"
      "全世界からの TCP 22 番許可と受信の既定拒否は保ち、最後に詳しい状態を表示してください。",
      ["sudo ufw delete allow 8080/tcp", "sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw status verbose"],
      "狭い許可を追加しても広い許可が残ると、公開範囲は狭まりません。", "ufw の delete allow で広いルールを消し、from を指定した許可を作ります。",
      "狭いルールの追加だけでは解決しない点を確認しました。不要な公開を取り除き、管理用の入口は維持します。",
      ufw={"active": True, "rules": [["22/tcp", "ALLOW", "Anywhere"], ["8080/tcp", "ALLOW", "Anywhere"]]},
      expected_ufw={"active": True, "incoming": "deny", "rules": [["22/tcp", "ALLOW", "Anywhere"], ["8080/tcp", "ALLOW", "192.0.2.10"]]},
      checks_commands=["sudo ufw status verbose"],
      alt_solutions=[["sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw delete allow 8080/tcp", "sudo ufw status verbose"]],
      traps=[["sudo ufw allow from 192.0.2.10 to any port 8080 proto tcp", "sudo ufw status verbose"], ["sudo ufw disable", "sudo ufw status verbose"]]),
    S(4, "Web サービスの起動と自動起動",
      "nginx は停止していて、自動起動も無効です。今すぐ稼働させ、次回起動時も動く設定にしてください。SSH は稼働と自動起動を維持します。"
      "最後に nginx の状態と自動起動設定をそれぞれ確認してください。",
      ["sudo systemctl start nginx", "sudo systemctl enable nginx", "systemctl is-active nginx", "systemctl is-enabled nginx"],
      "今動いていることと、次回も動くことは別の設定です。", "systemctl の start と enable、確認には is-active と is-enabled を使います。",
      "起動だけでは再起動後に戻らないことがあります。実際の障害対応ではログや要求への応答も併せて確認します。",
      expected_services={"nginx": {"active": "active", "enabled": True}, "ssh": {"active": "active", "enabled": True}},
      checks_commands=["systemctl is-active nginx", "systemctl is-enabled nginx"],
      alt_solutions=[["sudo systemctl enable --now nginx", "systemctl is-enabled nginx", "systemctl is-active nginx"]],
      traps=[["sudo systemctl start nginx", "systemctl is-active nginx"], ["sudo systemctl enable nginx", "systemctl is-enabled nginx"]]),
    S(5, "定期処理の時刻を変更する",
      "毎日 3 時の /usr/local/bin/backup.sh を毎日 2 時 15 分へ変更します。schedule.txt に時刻の 5 項目と実行先を 1 行で書き、"
      "定期実行へ登録してください。最後に登録済みの内容を表示します。",
      ["echo '15 2 * * * /usr/local/bin/backup.sh' > schedule.txt", "crontab schedule.txt", "crontab -l"],
      "分・時・日・月・曜日の順に書きます。ファイルを作るだけでは登録されません。", "時刻は分が 15、時が 2、残りが * です。crontab へファイルを渡し、-l で確認します。",
      "定期処理では実行時刻だけでなく、絶対パス・実行権限・実行環境・失敗通知も実運用で確認します。",
      services={"cron": ["0 3 * * * /usr/local/bin/backup.sh"]},
      expected_files={"schedule.txt": "15 2 * * * /usr/local/bin/backup.sh\n"}, expected_cron=["15 2 * * * /usr/local/bin/backup.sh"],
      checks_commands=["crontab -l"], traps=[["echo '15 2 * * * /usr/local/bin/backup.sh' > schedule.txt", "crontab -l"]]),
    S(6, "失敗したサービスの証拠を残す",
      "demo-app が失敗しています。状態を表示し、そのサービスのエラー以上のログだけを incident.txt に保存してください。"
      "保存した内容を読み返し、容量制限のメッセージを調べる材料として残します。再起動してごまかす作業ではありません。",
      ["systemctl status demo-app", "journalctl -u demo-app -p err > incident.txt", "cat incident.txt"],
      "最初に現状を確認し、対象と深刻度を絞った証拠を残します。", "systemctl status と journalctl の -u・-p を使います。err はエラー以上の深刻度です。",
      "ログにある disk quota exceeded は容量制限の調査が必要な証拠です。再起動成功だけで原因が直ったとは判断しません。",
      expected_codes={"systemctl status demo-app": 3}, min_lines={"incident.txt": 3},
      checks_commands=["cat incident.txt", ["journalctl -u demo-app -p err > incident.txt", "journalctl --unit demo-app --priority err > incident.txt"]],
      expected_services={"demo-app": {"active": "failed"}},
      alt_solutions=[["systemctl status demo-app", "journalctl --unit demo-app --priority err > incident.txt", "cat incident.txt"]],
      traps=[["echo fake > incident.txt", "cat incident.txt"], ["sudo systemctl restart demo-app", "journalctl -u demo-app -p err > incident.txt", "cat incident.txt"]]),
]
