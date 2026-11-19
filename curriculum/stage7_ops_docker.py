"""Stage 7: サーバー運用と Docker 応用（7問）

7-1〜7-4 … root 権限が必要な管理コマンド（systemctl / journalctl / useradd / usermod ...）を
           bin/sim の模擬コマンドで安全に練習する（Mission.sim=True）。
           システム領域は作業ディレクトリの sysroot/ を「/」とみなす。
7-5〜7-7 … Docker 応用（ネットワーク・マルチステージビルド・ヘルスチェックと再起動ポリシー）。
           stage5 と同じく本物の Docker / 模擬 docker のどちらでも同じ判定コードで動く。
"""
import random
import time

from engine import sim_ops
from engine.docker_backend import find, image_matches
from engine.runner import register
from curriculum.stage5_docker import need_running

S = 7

SYSROOT_NOTE = ("## この訓練サーバーについて\n"
                "本物の /etc などを壊さないよう、システム領域は作業ディレクトリの `sysroot/` に置いてあります。\n"
                "  /etc/passwd             → sysroot/etc/passwd\n"
                "  /etc/systemd/system/... → sysroot/etc/systemd/system/...\n"
                "  /opt/...                → sysroot/opt/...\n"
                "systemctl / journalctl / useradd などは訓練用の模擬コマンドで、本物と同じ書式で動きます。\n"
                "`sudo` を付けて /etc/... などを指定すると、自動的に sysroot/ 側に読み替えて実行されます\n"
                "（例: `sudo cat /etc/passwd`、`sudo nano /etc/systemd/system/xxx.service`）。\n")


def ops(ctx):
    sim_ops.configure(ctx.work, ctx.state)
    return sim_ops


def host_name(prefix):
    return f"{prefix}{random.randint(1, 19):02d}"


def shift_new_logs(st, start_idx, t0, step=0.35):
    """直前に追加されたジャーナルを過去の時刻 t0 からの出来事として並べ直す。"""
    for k, e in enumerate(st["journal"][start_idx:]):
        e["ts"] = t0 + k * step


# ================================================================== 7-1
NGINX_UNIT = """[Unit]
Description=A high performance web server and a reverse proxy server
Documentation=man:nginx(8)
After=network-online.target remote-fs.target nss-lookup.target
Wants=network-online.target

[Service]
Type=forking
PIDFile=/run/nginx.pid
ExecStartPre=/usr/sbin/nginx -t -q -g 'daemon on; master_process on;'
ExecStart=/usr/sbin/nginx -g 'daemon on; master_process on;'
ExecReload=/usr/sbin/nginx -g 'daemon on; master_process on;' -s reload
ExecStop=-/sbin/start-stop-daemon --quiet --stop --retry QUIT/5 --pidfile /run/nginx.pid
TimeoutStopSec=5
KillMode=mixed

[Install]
WantedBy=multi-user.target
"""
APACHE_UNIT = """[Unit]
Description=The Apache HTTP Server
After=network.target remote-fs.target nss-lookup.target
Documentation=https://httpd.apache.org/docs/2.4/

[Service]
Type=forking
Environment=APACHE_STARTED_BY_SYSTEMD=true
ExecStart=/usr/sbin/apachectl start
ExecStop=/usr/sbin/apachectl graceful-stop
ExecReload=/usr/sbin/apachectl graceful
KillMode=mixed
PrivateTmp=true
Restart=on-abort

[Install]
WantedBy=multi-user.target
"""
NGINX_BEH = {"ident": "nginx", "comm": "nginx", "comm_line": "nginx: master process /usr/sbin/nginx -g daemon on; master_process on;",
             "children": ["nginx: worker process", "nginx: worker process"], "memory": "5.2M", "memory_peak": "6.0M",
             "conflicts": ["apache2.service"],
             "fail_log": [[2, "nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)"],
                          [2, "nginx: [emerg] bind() to [::]:80 failed (98: Address already in use)"],
                          [2, "nginx: [emerg] still could not bind()"]]}
APACHE_BEH = {"ident": "apachectl", "comm": "apache2", "comm_line": "/usr/sbin/apache2 -k start",
              "children": ["/usr/sbin/apache2 -k start", "/usr/sbin/apache2 -k start"], "memory": "18.4M", "memory_peak": "21.0M",
              "ok_log": [[6, "AH00558: apache2: Could not reliably determine the server's fully qualified domain name, using 127.0.1.1."]]}


def s71(ctx):
    so = ops(ctx)
    host = host_name("web")
    ctx.data["host"] = host
    so.init_system(ctx.work, ctx.state, host=host)
    so.fake_bin("/usr/sbin/nginx")
    so.fake_bin("/usr/sbin/apachectl")
    so.add_unit("apache2.service", APACHE_UNIT, enabled=True, active=True, at_boot=True, behavior=APACHE_BEH)
    so.add_unit("nginx.service", NGINX_UNIT, behavior=NGINX_BEH)
    ctx.write("README.md", SYSROOT_NOTE + "\n## 作業依頼\n"
              "Web サーバーを Apache (apache2) から nginx へ移行済み。切り替え作業をお願いします。\n"
              "  ・apache2 は今後使わない（停止 + 自動起動の解除）\n"
              "  ・nginx を起動し、サーバー再起動後も自動で起動するようにする\n"
              "  ・作業後、nginx のメインプロセスの PID を報告（submit）\n")


def c71(ctx):
    so = ops(ctx)
    a = so.unit_state("apache2.service")
    n = so.unit_state("nginx.service")
    if n["active"] != "active":
        if n["active"] == "failed":
            if a["active"] == "active":
                ctx.fail("nginx の起動に失敗しています。`systemctl status nginx` の下に出るログを読むと…「80番ポートが使用中」。"
                         "まだ動いている apache2 が80番を握っているようです。先に apache2 を止めましょう。")
            ctx.fail("nginx が failed 状態です。apache2 を止めたなら、もう一度 `sudo systemctl start nginx` してみましょう。")
        ctx.fail("nginx がまだ起動していません。`systemctl status nginx` で状態を確認し、`sudo systemctl start nginx` で起動しましょう。")
    if a["active"] == "active":
        ctx.fail("apache2 がまだ動いています（`systemctl is-active apache2`）。")
    if a["enabled"] == "enabled":
        ctx.fail("apache2 は停止しましたが、自動起動が有効なままです（`systemctl is-enabled apache2` → enabled）。"
                 "このままだと次の再起動で apache2 が先に80番を取り、nginx が起動に失敗します。`sudo systemctl disable apache2` で解除しましょう。")
    if n["enabled"] != "enabled":
        ctx.fail("nginx は動いていますが、自動起動が無効です（`systemctl is-enabled nginx` → disabled）。"
                 "`start` は「今すぐ起動」、`enable` は「起動時に自動起動」で別物です。`sudo systemctl enable nginx` も実行しましょう。")
    ctx.need_submit(str(n["pid"]), "nginx の Main PID")


register(
    id="7-1", stage=S, title="systemctl でサービスを切り替えよ", sim=True,
    story="""
Web サーバーを **Apache から nginx へ移行** することになった。設定ファイルの準備は済んでいるが、サーバー `<<host>>` 上では
まだ古い `apache2` が動いていて、`nginx` は止まったままだ。
**systemd**（`systemctl`）を使ってサービスを切り替え、**サーバーを再起動しても nginx が自動で立ち上がる** 状態にしてほしい。

📝 この訓練サーバーでは、root 権限が必要なコマンドは本物そっくりの模擬コマンドで動きます（作業ディレクトリの `README.md` 参照）。
""",
    objectives=["`systemctl status nginx` / `systemctl status apache2` で現在の状態（Active / Loaded の enabled・disabled）を確認する",
                "`apache2` を **停止** し、**自動起動も解除** する",
                "`nginx` を **起動** し、**自動起動を有効化** する（`is-active` / `is-enabled` で確認）",
                "`systemctl status nginx` に表示される nginx の `Main PID` を `submit` する"],
    hints=["サービスの「今の状態」(active/inactive) と「起動時に自動で立ち上がるか」(enabled/disabled) は別々に管理されています。状態を変える操作には root 権限が必要です。",
           "`sudo systemctl stop` / `start` で今の状態、`sudo systemctl disable` / `enable` で自動起動を切り替えます。`--now` を付けると両方を同時に行えます。",
           "`sudo systemctl disable --now apache2` → `sudo systemctl enable --now nginx` → `systemctl status nginx` の Main PID を `submit`"],
    answer="systemctl status nginx apache2          # nginx: inactive/disabled, apache2: active/enabled\nsudo systemctl disable --now apache2     # 停止 + 自動起動解除\nsudo systemctl enable --now nginx        # 自動起動有効化 + 起動\nsystemctl is-active nginx; systemctl is-enabled nginx\nsystemctl status nginx                   # Main PID: の数字を確認\nsubmit \"$(systemctl show -p MainPID --value nginx)\"",
    explanation="""
systemd が管理するサービスには **2つの独立した状態** があります。
  ・**active / inactive / failed** … 今動いているか（`start` / `stop` / `restart` で変える）
  ・**enabled / disabled** … OS 起動時に自動で立ち上がるか（`enable` / `disable` で変える）
よくある事故は「`start` だけして `enable` を忘れ、夜中のカーネル更新で再起動したらサービスが上がってこない」パターン。
逆に「`disable` しただけで止めたつもり」も、実はまだ動き続けています。`--now` を付けると両方まとめて操作できます。
  ・`systemctl status 名前` … Loaded 行に enabled/disabled、Active 行に稼働状態、Main PID、直近のログ10行
  ・`systemctl is-active 名前` / `is-enabled 名前` … 状態を1単語で表示（終了コードも 0/非0 になるのでスクリプト向き）
  ・`systemctl show -p MainPID --value 名前` … プロパティだけを取り出す
  ・`systemctl list-units --type=service --failed` … 失敗しているサービスの一覧
今回は apache2 が 80 番ポートを使っていたため、その状態で nginx を起動すると `Address already in use` で失敗します。
**止める → 自動起動を外す → 新しい方を起動 → 自動起動を付ける** が移行の定石です。
""",
    tip="""
`systemctl enable` は `/etc/systemd/system/multi-user.target.wants/` にシンボリックリンクを作るだけの操作です
（`ls -l sysroot/etc/systemd/system/multi-user.target.wants/` で確認してみましょう）。
二度と起動させたくないサービスは `systemctl mask` で `/dev/null` へのリンクにして「手動 start すら不可」にできます。
本番で設定変更したら、`sudo nginx -t` のような構文チェック → `systemctl reload`（プロセスを止めずに設定再読込）が安全です。
""",
    setup=s71, check=c71,
    solution='systemctl status nginx\nsudo systemctl disable --now apache2\nsudo systemctl enable --now nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
    wrong=['sudo systemctl start nginx\nsudo systemctl enable nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
           'sudo systemctl stop apache2\nsudo systemctl start nginx\nsudo systemctl enable nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
           'sudo systemctl disable apache2\nsudo systemctl enable --now nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
           'systemctl disable --now apache2\nsystemctl enable --now nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
           'sudo systemctl disable --now apache2\nsudo systemctl start nginx\nsubmit "$(systemctl show -p MainPID --value nginx)"',
           'sudo systemctl disable --now apache2\nsudo systemctl enable --now nginx\nsubmit 1'],
)


# ================================================================== 7-2
ORDER_UNIT = """[Unit]
Description=Order API server
After=network-online.target
Wants=network-online.target

[Service]
User=orderapi
ExecStart=/opt/order-api/bin/order-api --port {port} --config /etc/order-api/config.yaml
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
MOCK_UNIT = """[Unit]
Description=Payment API mock server (development only)
After=network.target

[Service]
ExecStart=/opt/payment-mock/mock-server --listen 0.0.0.0:{port}
Restart=always

[Install]
WantedBy=multi-user.target
"""


def s72(ctx):
    so = ops(ctx)
    host = host_name("app")
    port = random.randint(8100, 8899)
    old = random.choice([p for p in range(7000, 7999, 7) if abs(p - port) > 50])
    ctx.data.update(host=host, port=port, old=old)
    st = so.init_system(ctx.work, ctx.state, host=host)
    so.fake_bin("/opt/order-api/bin/order-api")
    so.fake_bin("/opt/payment-mock/mock-server")
    pw, gr = so.read_db("passwd"), so.read_db("group")
    pw.append(["orderapi", "x", "997", "997", "Order API", "/opt/order-api", "/usr/sbin/nologin"])
    gr.append(["orderapi", "x", "997", ""])
    so.write_db("passwd", pw)
    so.write_db("group", gr)
    ctx.write("sysroot/etc/order-api/config.yaml", f"listen_port: {port}\ndatabase: db01.internal:5432\n")
    st = so.load()
    b_prev, b_now = st["boots"][0]["start"], st["boots"][1]["start"]
    now = time.time()
    # ---- 前回のブート（昨日）: 一時的な bind エラー → 自動復旧 → 設定変更
    t = now - random.randint(21, 23) * 3600
    J = lambda ts, unit, ident, pid, msg, prio=6: so.log(st, unit, ident, pid, msg, prio=prio, ts=ts, boot=0)  # noqa: E731
    p1 = random.randint(1200, 1900)
    J(b_prev + 5, "order-api.service", "systemd", 1, "Started order-api.service - Order API server.")
    J(b_prev + 5.4, "order-api.service", "order-api", p1, f"HTTP server listening on 0.0.0.0:{old}")
    J(t, "order-api.service", "order-api", p1, f"listen tcp 0.0.0.0:{old}: bind: address already in use", 3)
    J(t + 0.1, "order-api.service", "order-api", p1, "FATAL: cannot start HTTP server", 2)
    J(t + 0.2, "order-api.service", "systemd", 1, "order-api.service: Main process exited, code=exited, status=1/FAILURE", 5)
    J(t + 0.3, "order-api.service", "systemd", 1, "order-api.service: Failed with result 'exit-code'.", 4)
    J(t + 3.3, "order-api.service", "systemd", 1, "order-api.service: Scheduled restart job, restart counter is at 1.")
    J(t + 3.5, "order-api.service", "order-api", p1 + 40, f"HTTP server listening on 0.0.0.0:{old}")
    t2 = t + random.randint(2, 3) * 3600
    J(t2, None, "sudo", 3100, "   dev-yamada : TTY=pts/1 ; PWD=/home/dev-yamada ; USER=root ; COMMAND=/usr/bin/systemctl enable --now payment-mock", 5)
    J(t2 + 1, "payment-mock.service", "systemd", 1, "Started payment-mock.service - Payment API mock server (development only).")
    J(t2 + 1.2, "payment-mock.service", "mock-server", 3120, f"mock server listening on 0.0.0.0:{port}")
    J(t2 + 1.3, "payment-mock.service", "mock-server", 3120, "WARNING: this is a development mock. Do not run in production!", 4)
    J(t2 + 2400, None, "sudo", 3311, "   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/usr/bin/vim /etc/order-api/config.yaml", 5)
    J(t2 + 2460, "order-api.service", "order-api", p1 + 40, f"config file changed: listen_port {old} -> {port} (will be applied on next restart)", 4)
    J(t2 + 5000, "backup.service", "backup.sh", 4100, "ERROR: rsync to nas01 failed: connection timed out (code 30)", 3)
    so.save(st)
    # ---- 今回のブート: payment-mock が先に起動 → order-api が bind 失敗を繰り返して諦める
    so.add_unit("payment-mock.service", MOCK_UNIT.format(port=port), where="/etc/systemd/system", enabled=True,
                active=True, at_boot=True, since=b_now + 4,
                behavior={"ident": "mock-server", "comm": "mock-server",
                          "ok_log": [[6, f"mock server listening on 0.0.0.0:{port}"],
                                     [4, "WARNING: this is a development mock. Do not run in production!"]]})
    so.add_unit("order-api.service", ORDER_UNIT.format(port=port), where="/etc/systemd/system", enabled=True,
                behavior={"ident": "order-api", "comm": "order-api", "conflicts": ["payment-mock.service"],
                          "fail_log": [[6, "order-api v2.4.1 starting"], [6, "connecting to database db01.internal:5432 ... ok"],
                                       [3, "listen tcp 0.0.0.0:{port}: bind: address already in use"],
                                       [2, "FATAL: cannot start HTTP server"]],
                          "ok_log": [[6, "order-api v2.4.1 starting"], [6, "connecting to database db01.internal:5432 ... ok"],
                                     [6, "HTTP server listening on 0.0.0.0:{port}"]]})
    st = so.load()
    n0 = len(st["journal"])
    so.log(st, None, "kernel", 0, "ACPI Error: AE_NOT_FOUND, While resolving a named reference package element (20230628/dspkginit-438)", prio=3, ts=b_now + 0.5, boot=1)
    so.do_start(st, "order-api.service")
    shift_new_logs(st, n0 + 1, b_now + 6)
    st["units"]["order-api.service"]["since"] = st["journal"][-1]["ts"]
    so.log(st, "cron.service", "CRON", 5120, "(root) CMD (/usr/local/bin/healthcheck.sh)", ts=now - 120)
    so.save(st)
    ctx.write("README.md", SYSROOT_NOTE + f"\n## 障害チケット #{random.randint(3000, 3999)}\n"
              f"今朝のメンテナンス再起動のあと、{host} の注文API (order-api.service) が上がってこない。\n"
              "原因を特定し、再発しない形で復旧してください。\n")


def c72(ctx):
    so = ops(ctx)
    ctx.need_submit(ctx.data["port"], "ポート番号")
    m = so.unit_state("payment-mock.service")
    o = so.unit_state("order-api.service")
    if m["active"] == "active":
        ctx.fail(f"ポート番号は正解！ そのポートを握っているのは開発用の `payment-mock` です（`journalctl -u payment-mock` を見てみよう）。"
                 "本番サーバーでは不要なので停止しましょう。")
    if m["enabled"] == "enabled":
        ctx.fail("payment-mock は止まりましたが、自動起動が有効なままです。次の再起動でまた同じ障害が起きてしまいます。`disable` しましょう。")
    if o["active"] != "active":
        ctx.fail("原因は取り除けました。order-api は起動を諦めた状態（failed）のままなので、`sudo systemctl restart order-api` で起動し直しましょう。")


register(
    id="7-2", stage=S, title="journalctl で障害の真犯人を突き止めろ", sim=True,
    story="""
🚨 今朝のメンテナンス再起動のあと、サーバー `<<host>>` の **注文API（order-api.service）が上がってこない**！
サービスのログは **systemd のジャーナル** に集約されている。ただし昨日にも別のトラブルがあったらしく、ログには新旧の
エラーが混ざっている。**今回の起動以降** のエラーに絞り込んで原因を突き止め、再発しない形で復旧せよ。
""",
    objectives=["`systemctl status order-api` で状態を確認する（failed になっている）",
                "`journalctl` を **ユニット(-u)・ブート(-b)・優先度(-p)** で絞り込み、今回の起動で order-api が失敗した原因を読む",
                "競合している **ポート番号** を `submit` する",
                "原因となっているサービスを止めて自動起動も解除し、order-api を起動し直す"],
    hints=["`journalctl` だけだと全サービスの全期間のログが出てきます。「どのサービスの」「いつの」「どの重要度の」ログが欲しいのかで絞り込みましょう。",
           "`-u ユニット名` でサービス、`-b` で今回の起動以降（`-b -1` は前回）、`-p err` でエラー以上、`--since \"1 hour ago\"` で時刻。`--no-pager` でページャ無し。",
           "`journalctl -u order-api -b -p err` → `address already in use` のポート番号を submit → `journalctl -b | grep 0.0.0.0:番号` で犯人を探す → `sudo systemctl disable --now 犯人` → `sudo systemctl restart order-api`"],
    answer="systemctl status order-api                  # failed / Start request repeated too quickly\njournalctl -u order-api -b -p err --no-pager  # 今回の起動以降のエラーだけ\n#  → listen tcp 0.0.0.0:<<port>>: bind: address already in use\nsubmit <<port>>\njournalctl -b --no-pager | grep ':<<port>>'     # 同じポートで待ち受けているのは…\nsystemctl status payment-mock                # 開発用モックが enable されていた！\nsudo systemctl disable --now payment-mock\nsudo systemctl restart order-api\nsystemctl status order-api                   # active (running)",
    explanation="""
`journalctl` は systemd が集めた全ログ（各サービスの標準出力/標準エラー + syslog + カーネル）を検索するコマンドです。
  ・`-u order-api` … ユニットで絞る（複数指定OK）　・`-b` / `-b -1` … 今回 / 前回の起動　・`--list-boots` … 起動履歴
  ・`-p err` … 優先度 err(3) 以上（emerg 0 / alert 1 / crit 2 / err 3 / warning 4 / notice 5 / info 6 / debug 7）
  ・`--since "2025-11-19 09:00" --until "10 min ago"` / `--since today` … 時刻で絞る
  ・`-n 50` … 末尾50行　・`-r` … 新しい順　・`-f` … 追従（`tail -f` 相当）　・`-o cat` … メッセージ本文だけ
  ・`-x` … 説明文付き / `-e` … 末尾へジャンプ。`journalctl -xeu order-api` は「直近のエラーを詳しく」の定番
今回 `journalctl -p err | grep port` のように期間を絞らずに探すと、**昨日の別件のエラー（ポート <<old>>）** に騙されます。
「再起動後に」起きた問題なら `-b`、時刻が分かっているなら `--since` で範囲を切るのが鉄則です。
原因は開発者が検証用に `enable --now` した `payment-mock` が同じ <<port>> 番を使っていたこと。
再起動時に mock が先に起動してポートを取ったため、order-api は `Restart=on-failure` で何度か再試行した末に諦めていました
（`Start request repeated too quickly`）。**止めるだけでなく disable しないと、次の再起動で再発** します。
""",
    tip="""
ポートを誰が使っているかは、本物のサーバーなら `sudo ss -tlnp | grep :<<port>>` で PID とプロセス名まで一発で分かります。
`Type=simple` のサービスは、プロセスを起動した時点で `systemctl start` が成功を返すため、直後に落ちても何も表示されません。
**start/restart の後は必ず `systemctl status` か `is-active` で確認** する癖を付けましょう。
ジャーナルが肥大化したら `journalctl --disk-usage` で確認し、`sudo journalctl --vacuum-time=2weeks` で古いものを削除できます。
""",
    setup=s72, check=c72,
    solution='systemctl status order-api\njournalctl -u order-api -b -p err --no-pager\nsubmit "$(journalctl -u order-api -b -p err -o cat | grep -o "tcp 0.0.0.0:[0-9]*" | head -1 | cut -d: -f2)"\njournalctl -b --no-pager | grep ":<<port>>"\nsudo systemctl disable --now payment-mock\nsudo systemctl restart order-api\nsystemctl is-active order-api',
    wrong=['submit "$(journalctl -p err -o cat | grep -o "tcp 0.0.0.0:[0-9]*" | head -1 | cut -d: -f2)"\nsudo systemctl disable --now payment-mock\nsudo systemctl restart order-api',
           "submit <<port>>\nsudo systemctl restart order-api",
           "submit <<port>>\nsudo systemctl stop payment-mock\nsudo systemctl restart order-api",
           "submit <<port>>\nsudo systemctl disable --now payment-mock",
           "submit <<port>>\nsystemctl disable --now payment-mock\nsystemctl restart order-api"],
)


# ================================================================== 7-3
REPORT_DRAFT = """[Unit]
Description=Daily report web server

[Service]
ExecStart=report-server --port 8000
User=report
"""


def s73(ctx):
    so = ops(ctx)
    host = host_name("batch")
    port = random.randint(9100, 9499)
    ctx.data.update(host=host, port=port)
    so.init_system(ctx.work, ctx.state, host=host)
    so.fake_bin("/opt/report/bin/report-server")
    ctx.write("sysroot/opt/report/README", "report-server: 日次レポートを HTTP で配信する常駐プログラム\n"
              "  usage: /opt/report/bin/report-server --port PORT\n")
    pw, gr = so.read_db("passwd"), so.read_db("group")
    pw.append(["report", "x", "996", "996", "report service", "/opt/report", "/usr/sbin/nologin"])
    gr.append(["report", "x", "996", ""])
    so.write_db("passwd", pw)
    so.write_db("group", gr)
    so.add_unit("report.service", REPORT_DRAFT, where="/etc/systemd/system",
                behavior={"ident": "report-server", "comm": "report-server",
                          "ok_log": [[6, "report-server 1.3.0 starting"], [6, "serving reports on 0.0.0.0:{port}"]]})
    st = so.load()
    n0 = len(st["journal"])
    so.do_start(st, "report.service")
    shift_new_logs(st, n0, time.time() - random.randint(600, 1500))
    so.save(st)
    ctx.write("依頼メモ.txt",
              "report-server を systemd のサービスとして常駐させたい。前任者の書きかけ: /etc/systemd/system/report.service\n"
              "（訓練サーバーでは sysroot/etc/systemd/system/report.service）\n\n"
              "要件:\n"
              f"  ・実行ファイルは /opt/report/bin/report-server、ポートは {port}（--port {port}）\n"
              "  ・実行ユーザーは report\n"
              "  ・ネットワークが使えるようになってから起動する（After=network.target）\n"
              "  ・異常終了したら自動で再起動する（Restart=on-failure）\n"
              "  ・サーバー起動時に自動で起動する（multi-user.target）\n"
              "  ・今すぐ起動もしておくこと\n")
    ctx.write("README.md", SYSROOT_NOTE)


def c73(ctx):
    so = ops(ctx)
    port = str(ctx.data["port"])
    text = ctx.read("sysroot/etc/systemd/system/report.service")
    if text is None:
        ctx.fail("`sysroot/etc/systemd/system/report.service` が見つかりません（消してしまった場合は作り直しましょう）。")
    cfg = so.parse_unit(text)
    secs = cfg["sections"]
    for sec in ("Unit", "Service", "Install"):
        if sec not in secs:
            ctx.fail(f"ユニットファイルに `[{sec}]` セクションがありません。" + (
                "`[Install]` が無いと `systemctl enable` で自動起動を設定できません（`WantedBy=multi-user.target`）。" if sec == "Install" else ""))
    es = so.uget(cfg, "Service", "ExecStart") or ""
    exe = so.exec_path(es)
    if not exe.startswith("/"):
        ctx.fail(f"`ExecStart={es}` のコマンドが絶対パスではありません。systemd は PATH を当てにできないので `/opt/report/bin/report-server` のように **フルパス** で書きましょう。")
    if exe != "/opt/report/bin/report-server":
        ctx.fail(f"ExecStart の実行ファイルが `{exe}` になっています。依頼メモの `/opt/report/bin/report-server` を指定しましょう。")
    toks = es.split()
    if not ("--port" in toks and toks.index("--port") + 1 < len(toks) and toks[toks.index("--port") + 1] == port) and f"--port={port}" not in toks:
        ctx.fail(f"ExecStart のポート指定が要件と違います（要件: `--port {port}`）。")
    if (so.uget(cfg, "Service", "User") or "") != "report":
        ctx.fail("実行ユーザーが `report` になっていません（`[Service]` に `User=report`）。")
    if "network.target" not in " ".join(so.ugetall(cfg, "Unit", "After")):
        ctx.fail("`[Unit]` に `After=network.target` がありません（ネットワークが使えるようになってから起動させる）。")
    if so.uget(cfg, "Service", "Restart") != "on-failure":
        ctx.fail("異常終了時の自動再起動が設定されていません。`[Service]` に `Restart=on-failure` を書きましょう。")
    if "multi-user.target" not in so.ugetall(cfg, "Install", "WantedBy"):
        ctx.fail("`[Install]` に `WantedBy=multi-user.target` がありません。")
    s = so.unit_state("report.service")
    if s["reload_needed"]:
        ctx.fail("ユニットファイルを書き換えた後、systemd がまだ古い内容を覚えています（`systemctl status report` に Warning が出ているはず）。"
                 "`sudo systemctl daemon-reload` で読み込み直しましょう。")
    if s["active"] != "active":
        ctx.fail("report.service が起動していません。`sudo systemctl start report` し、`systemctl status report` で確認しましょう。")
    if s["run_text"] != text:
        ctx.fail("ユニットファイルは読み込み直されましたが、動いているプロセスは古い設定のまま起動したものです。`sudo systemctl restart report` で再起動しましょう。")
    if s["enabled"] != "enabled":
        ctx.fail("report.service は動いていますが、自動起動が無効です。`sudo systemctl enable report` しましょう。")


REPORT_OK = """[Unit]
Description=Daily report web server
After=network.target

[Service]
ExecStart=/opt/report/bin/report-server --port <<port>>
User=report
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

register(
    id="7-3", stage=S, title="ユニットファイルを書いて常駐サービス化せよ", sim=True,
    story="""
自作のレポート配信プログラム `report-server` を、**systemd のサービスとして常駐** させたい。
前任者がユニットファイル `report.service` を書きかけたまま異動してしまい、起動しようとしても失敗する状態だ。
`依頼メモ.txt` の要件どおりにユニットファイルを完成させ、**今すぐ起動 & 再起動後も自動起動** にせよ。
""",
    objectives=["`systemctl status report` / `journalctl -u report` で、前任者のユニットファイルが起動できない理由を確認する",
                "`sysroot/etc/systemd/system/report.service` を要件どおりに直す（`[Unit]` `[Service]` `[Install]` の3セクション）",
                "変更を systemd に読み込ませる（`daemon-reload`）",
                "サービスを起動し、自動起動も有効にする（`systemctl status report` が active (running)・enabled）"],
    hints=["ユニットファイルは INI 形式。`[Unit]` に説明と起動順序、`[Service]` に実行コマンドと動作、`[Install]` に「どのタイミングで自動起動するか」を書きます。systemd は書き換えただけでは新しい内容を読みません。",
           "`ExecStart=` は **絶対パス**、`Restart=on-failure`、`User=report`、`After=network.target`、`[Install]` に `WantedBy=multi-user.target`。編集後は `sudo systemctl daemon-reload`。",
           "`nano sysroot/etc/systemd/system/report.service`（または `sudo nano /etc/systemd/system/report.service`）で書き直し → `sudo systemctl daemon-reload` → `sudo systemctl enable --now report` → `systemctl status report`"],
    answer="systemctl status report        # bad-setting: Unable to locate executable 'report-server'\ncat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK + "EOF\nsudo systemctl daemon-reload\nsudo systemctl enable --now report\nsystemctl status report        # active (running) / enabled",
    explanation="""
自作プログラムを常駐させるユニットファイルの基本形です（置き場所は `/etc/systemd/system/名前.service`）。
  ・`[Unit]` … `Description=`（status に出る説明）、`After=network.target`（ネットワーク起動後に起動）
  ・`[Service]` … `ExecStart=` 実行コマンド（**絶対パス必須**。シェルではないので `cd` やパイプ、`~` は使えない）
                `User=` 実行ユーザー（root で動かさないのが安全）、`Restart=on-failure` 異常終了時に自動再起動、`RestartSec=5` 再起動までの待ち
                `Environment=KEY=value` / `EnvironmentFile=` 環境変数、`WorkingDirectory=` 作業ディレクトリ
  ・`[Install]` … `WantedBy=multi-user.target`（通常のサーバー起動時に自動起動）。**これが無いと enable できない**
前任者のファイルは `ExecStart=report-server`（相対パス）・`Restart` 無し・`[Install]` 無しの3つの問題がありました。
ユニットファイルを編集したら **`sudo systemctl daemon-reload`** で systemd に読み込ませるまで、古い内容のまま動きます
（`systemctl status` に `changed on disk. Run 'systemctl daemon-reload'` という Warning が出るのが合図）。
※ `systemctl enable` / `disable` は内部で daemon-reload も行いますが、`restart` だけでは読み込まれません。
""",
    tip="""
`systemctl cat report` で systemd が認識しているユニット内容、`systemctl show report -p Restart,User,ExecStart` で解釈後の値を確認できます。
パッケージ付属のユニット（`/usr/lib/systemd/system/`）を直接書き換えるとアップデートで上書きされるので、
`sudo systemctl edit nginx` で **drop-in**（`/etc/systemd/system/nginx.service.d/override.conf`）を作って差分だけ上書きするのが定石です。
cron の代わりに `.timer` ユニットで定期実行する方法もあり、ログが journalctl に残る・依存関係を書けるなどの利点があります。
""",
    setup=s73, check=c73,
    solution="systemctl status report\ncat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK + "EOF\nsudo systemctl daemon-reload\nsudo systemctl enable --now report\nsystemctl status report",
    wrong=["cat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK + "EOF\nsudo systemctl restart report",
           "cat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK.split("[Install]")[0] + "EOF\nsudo systemctl daemon-reload\nsudo systemctl enable --now report",
           "cat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK.replace("/opt/report/bin/report-server", "report-server") + "EOF\nsudo systemctl daemon-reload\nsudo systemctl enable --now report",
           "cat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK.replace("Restart=on-failure\n", "") + "EOF\nsudo systemctl daemon-reload\nsudo systemctl enable --now report",
           "sudo systemctl enable --now report\ncat > sysroot/etc/systemd/system/report.service <<'EOF'\n" + REPORT_OK + "EOF\nsudo systemctl daemon-reload"],
)


# ================================================================== 7-4
NEW_USERS = ["kobayashi", "yamamoto", "nakamura", "matsumoto", "inoue", "kimura", "hayashi", "shimizu"]
TEAM = ["sato", "suzuki", "takahashi", "watanabe"]
PROJECTS = ["proj-atlas", "proj-nova", "proj-orion", "proj-vega", "proj-lyra"]


def s74(ctx):
    so = ops(ctx)
    host = host_name("dev")
    newu = random.choice(NEW_USERS)
    team = random.sample(TEAM, 3)
    u2 = team[0]
    proj = random.choice(PROJECTS)
    ctx.data.update(host=host, newu=newu, u2=u2, proj=proj)
    so.init_system(ctx.work, ctx.state, host=host)
    pw, gr = so.read_db("passwd"), so.read_db("group")
    pw.append(["deploy", "x", "1000", "1000", "Deploy user,,,", "/home/deploy", "/bin/bash"])
    gr.append(["deploy", "x", "1000", ""])
    for k, u in enumerate(team, 1):
        pw.append([u, "x", str(1000 + k), str(1000 + k), f"{u.capitalize()},,,", f"/home/{u}", "/bin/bash"])
        gr.append([u, "x", str(1000 + k), ""])
        so.copy_skel(f"/home/{u}", 0, 0)
    so.copy_skel("/home/deploy", 0, 0)
    gr.append(["developers", "x", "1100", ",".join(team)])
    gr.append(["release", "x", "1101", f"{u2},deploy"])
    for g in gr:
        if g[0] == "sudo":
            g[3] = "deploy"
        if g[0] == "docker":
            g[3] = ",".join(t for t in team[1:])
    so.write_db("passwd", pw)
    so.write_db("group", gr)
    so.write_db("shadow", [[r[0], "$y$j9T$lqsaltlqsalt$" + "x" * 43 if int(r[2]) >= 1000 and r[0] != "nobody" else "*",
                            "19700", "0", "99999", "7", "", "", ""] for r in pw])
    ctx.data["u2_before"] = sorted(so.user_info(u2)["groups"])
    ctx.write("README.md", SYSROOT_NOTE)
    ctx.write("アカウント申請.txt",
              f"■ 申請1: 新メンバー {newu} さんのアカウント作成\n"
              f"  ・ログイン名: {newu}\n  ・ホームディレクトリを作成すること（/home/{newu}）\n"
              "  ・ログインシェル: /bin/bash\n"
              f"  ・所属グループ: developers, {proj}\n"
              "  ・初期パスワードを設定すること（何でも可）\n\n"
              f"■ 申請2: 新プロジェクト用グループ {proj} の作成\n\n"
              f"■ 申請3: 既存メンバー {u2} さんの権限追加\n"
              f"  ・docker グループと {proj} グループに **追加** してほしい\n"
              f"  ・今の所属（{', '.join(ctx.data['u2_before'])}）はそのまま維持すること！\n")


def c74(ctx):
    so = ops(ctx)
    d = ctx.data
    newu, u2, proj = d["newu"], d["u2"], d["proj"]
    if not any(g[0] == proj for g in so.read_db("group")):
        ctx.fail(f"グループ `{proj}` がありません。`sudo groupadd {proj}` で作成しましょう（`getent group {proj}` で確認）。")
    info = so.user_info(newu)
    if not info:
        ctx.fail(f"ユーザー `{newu}` がまだ存在しません（`id {newu}`）。存在しないグループを -G に指定すると useradd はエラーで中断します。")
    if not ctx.isdir(f"sysroot/home/{newu}") or not ctx.exists(f"sysroot/home/{newu}/.bashrc"):
        ctx.fail(f"`{newu}` のホームディレクトリ /home/{newu} が作られていません。useradd は **`-m` を付けないとホームを作りません**。"
                 f"`sudo userdel {newu}` で一度消して、`-m` 付きで作り直しましょう。")
    if info["shell"] != "/bin/bash":
        ctx.fail(f"`{newu}` のログインシェルが `{info['shell']}` です（`getent passwd {newu}` の最後の欄）。"
                 f"useradd の既定値は /bin/sh なので `-s /bin/bash` が必要です。`sudo usermod -s /bin/bash {newu}` で直せます。")
    for g in ("developers", proj):
        if g not in info["groups"]:
            ctx.fail(f"`{newu}` が `{g}` グループに入っていません（`id {newu}`）。`sudo usermod -aG {g} {newu}` で追加しましょう。")
    sh = next((s for s in so.read_db("shadow") if s[0] == newu), None)
    if not sh or sh[1].startswith("!") or sh[1] in ("", "*"):
        ctx.fail(f"`{newu}` の初期パスワードが未設定です（useradd 直後はロック状態）。`sudo passwd {newu}` で設定しましょう。")
    i2 = so.user_info(u2)
    if not i2:
        ctx.fail(f"`{u2}` さんのアカウントが消えています…！ `reset_mission` でやり直しましょう。")
    lost = [g for g in d["u2_before"] if g not in i2["groups"]]
    if lost:
        ctx.fail(f"🚨 `{u2}` さんが元々の所属グループ（{', '.join(lost)}）から外れてしまっています！ `usermod -G` は **`-a` を付けないと"
                 f"「指定したグループだけ」に置き換え** ます。`sudo usermod -aG {','.join(lost)} {u2}` で戻しましょう。")
    for g in ("docker", proj):
        if g not in i2["groups"]:
            ctx.fail(f"`{u2}` さんが `{g}` グループに入っていません（`id {u2}`）。")


register(
    id="7-4", stage=S, title="新メンバーのアカウントを作成せよ", sim=True,
    story="""
開発サーバー `<<host>>` に新メンバー **<<newu>>** さんが加わる。さらに新プロジェクトの共有グループ `<<proj>>` を作り、
既存メンバーの **<<u2>>** さんにも Docker とプロジェクトの権限を追加してほしい、という申請が届いた（`アカウント申請.txt`）。
ユーザー・グループ管理は root 権限の仕事。**既存メンバーの権限を壊さないよう** 慎重に作業しよう。
""",
    objectives=["`sudo groupadd` でグループ `<<proj>>` を作成する",
                "`sudo useradd` で `<<newu>>` を作成する（ホームディレクトリあり・シェル /bin/bash・グループ developers と <<proj>>）",
                "`sudo passwd <<newu>>` で初期パスワードを設定する",
                "`<<u2>>` さんを `docker` と `<<proj>>` グループに **追加** する（今の所属グループは維持）",
                "`id ユーザー名` / `getent passwd` / `getent group` で結果を確認する"],
    hints=["ユーザーは /etc/passwd、グループのメンバーは /etc/group に記録されます（`sudo cat /etc/group` や `getent group developers` で見られる）。useradd の既定値は意外と不親切です。",
           "useradd は `-m`（ホーム作成）・`-s /bin/bash`（シェル）・`-G g1,g2`（補助グループ）を明示。既存ユーザーへのグループ追加は `usermod -aG`（**-a を忘れると置き換え**）。",
           "`sudo groupadd <<proj>>` → `sudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>` → `sudo passwd <<newu>>` → `sudo usermod -aG docker,<<proj>> <<u2>>` → `id <<newu>>; id <<u2>>`"],
    answer="sudo groupadd <<proj>>\nsudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nsudo passwd <<newu>>                     # 2回入力\nsudo usermod -aG docker,<<proj>> <<u2>>   # -a を忘れずに！\nid <<newu>>\nid <<u2>>\ngetent group <<proj>>\nls -la sysroot/home/<<newu>>",
    explanation="""
  ・`useradd [オプション] 名前` … 低レベルなユーザー作成コマンド。**既定ではホームを作らず、シェルは /bin/sh**（Debian/Ubuntu）
      `-m` ホーム作成（/etc/skel の .bashrc などをコピー）、`-s /bin/bash` シェル、`-G a,b` 補助グループ、`-g` 主グループ、`-c "氏名"` コメント
      ※ Debian/Ubuntu の `adduser 名前` は対話式の高水準版で、ホーム作成・bash・パスワード設定までまとめて行う
  ・`passwd 名前` … パスワード設定。useradd 直後はパスワードがロック（/etc/shadow が `!`）でログインできない
  ・`groupadd 名前` … グループ作成。存在しないグループを `-G` に書くと useradd は **何も作らずにエラー終了** する
  ・`usermod -aG グループ 名前` … 補助グループに **追加**。**`-a` を忘れて `-G` だけにすると、列挙したグループ以外から外される**
      （「docker を足したら sudo が使えなくなった」という事故の定番）。`gpasswd -a 名前 グループ` でも1つずつ追加できる
  ・確認: `id 名前`、`groups 名前`、`getent passwd 名前`、`getent group グループ`
グループの変更は **次回ログインから** 有効になります。本人には「一度ログアウトして入り直してください」と伝えましょう（`newgrp docker` で即時反映も可）。
""",
    tip="""
`docker` グループに入れると `sudo` なしで Docker を操作できますが、これは **実質 root 権限を渡すのと同じ** です
（`docker run -v /:/host` でホスト全体を書き換えられるため）。付与は慎重に。
sudo 権限は `sudo`（Ubuntu）/`wheel`（RHEL 系）グループで付与し、細かい制御は `sudo visudo` で /etc/sudoers.d/ に書きます。
共有ディレクトリは `sudo chgrp <<proj>> /srv/<<proj>> && sudo chmod 2775 /srv/<<proj>>`（setgid）にすると、中で作ったファイルが自動でグループ所有になります。
""",
    setup=s74, check=c74,
    solution="sudo groupadd <<proj>>\nsudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nprintf '%s\\n%s\\n' 'Init#2026' 'Init#2026' | sudo passwd <<newu>>\nsudo usermod -aG docker,<<proj>> <<u2>>\nid <<newu>>\nid <<u2>>",
    wrong=["sudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nprintf 'a\\na\\n' | sudo passwd <<newu>>\nsudo groupadd <<proj>>\nsudo usermod -aG docker,<<proj>> <<u2>>",
           "sudo groupadd <<proj>>\nsudo useradd -G developers,<<proj>> <<newu>>\nprintf 'a\\na\\n' | sudo passwd <<newu>>\nsudo usermod -aG docker,<<proj>> <<u2>>",
           "sudo groupadd <<proj>>\nsudo useradd -m -G developers,<<proj>> <<newu>>\nprintf 'a\\na\\n' | sudo passwd <<newu>>\nsudo usermod -aG docker,<<proj>> <<u2>>",
           "sudo groupadd <<proj>>\nsudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nprintf 'a\\na\\n' | sudo passwd <<newu>>\nsudo usermod -G docker,<<proj>> <<u2>>",
           "sudo groupadd <<proj>>\nsudo useradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nsudo usermod -aG docker,<<proj>> <<u2>>",
           "groupadd <<proj>>\nuseradd -m -s /bin/bash -G developers,<<proj>> <<newu>>\nusermod -aG docker,<<proj>> <<u2>>"],
)


# ================================================================== 7-5

def s75(ctx):
    ctx.docker.reset()
    ctx.docker.add_container("lq-front", "alpine", cmd=["sleep", "3600"])
    ctx.docker.add_container("lq-back", "nginx:alpine")
    ctx.write("依頼メモ.txt", "既存の lq-front と lq-back を lq-app-net に接続。\n"
              "ホストへポートを公開せず、lq-front から http://lq-back/ にアクセスできるようにする。\n")


def c75(ctx):
    front = need_running(ctx, "lq-front")
    back = need_running(ctx, "lq-back")
    for c in (front, back):
        if "lq-app-net" not in c.get("networks", []):
            ctx.fail(f"`{c['name']}` が lq-app-net に接続されていません。network create / connect を確認しましょう。")
        if c["ports"]:
            ctx.fail("内部通信なのでホストへのポート公開は不要です。-p なしで起動しましょう。")
    _, code = ctx.docker.exec("lq-front", "wget", "-qO-", "http://lq-back/")
    if code:
        ctx.fail("lq-front から lq-back への HTTP 通信に失敗します。名前解決と Web サーバーの稼働を確認しましょう。")


NET_SOLUTION = "docker network create --label lq=1 lq-app-net\ndocker network connect lq-app-net lq-front\ndocker network connect lq-app-net lq-back\ndocker exec lq-front wget -qO- http://lq-back/"
register(
    id="7-5", stage=S, title="専用ネットワークでコンテナをつなげ", docker=True,
    story="フロントとバックエンドが別々のコンテナで動いているが、名前で通信できない。既存の2台を専用ネットワークにつなぎ、内部 HTTP 通信を復旧しよう。",
    objectives=["lq-app-net というユーザー定義ネットワークを作る", "lq-front と lq-back を両方接続する", "ホストにポートを公開せず、lq-front から http://lq-back/ を取得する"],
    hints=["デフォルトの bridge ではコンテナ名による名前解決ができません。専用のネットワークを作ります。", "docker network create で作成し、docker network connect ネットワーク コンテナ で既存コンテナを接続します。", "docker network create --label lq=1 lq-app-net → 両方に network connect → docker exec lq-front wget -qO- http://lq-back/"],
    answer=NET_SOLUTION,
    explanation="ユーザー定義 bridge には組み込み DNS があり、同じネットワークにいるコンテナを名前で参照できます。network connect は実行中のコンテナにも使えます。内部通信に -p は不要です。network inspect で接続先、exec で実際の HTTP 応答を確認しましょう。",
    tip="Compose ではプロジェクト用ネットワークが自動作成され、サービス名で通信できます。不要になった専用ネットワークは、コンテナを切り離してから docker network rm で削除します。",
    setup=s75, check=c75, solution=NET_SOLUTION,
    wrong=["docker exec lq-front wget -qO- http://lq-back/", "docker network create --label lq=1 lq-app-net\ndocker network connect lq-app-net lq-front", NET_SOLUTION + "\ndocker network disconnect lq-app-net lq-back"],
)


# ================================================================== 7-6
GO_SOURCE = '''package main
import ("fmt"; "net/http")
func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "LinuxQuest API ready") })
    http.ListenAndServe(":8080", nil)
}
'''
MULTI_OK = '''FROM golang:1.23 AS builder
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/api .
FROM scratch
COPY --from=builder /out/api /api
EXPOSE 8080
CMD ["/api"]
'''


def s76(ctx):
    ctx.docker.reset()
    ctx.write("go.mod", "module linuxquest/api\n\ngo 1.23\n")
    ctx.write("main.go", GO_SOURCE)
    ctx.write("Dockerfile", 'FROM golang:1.23\nWORKDIR /src\nCOPY go.mod main.go ./\nRUN go build -o /api .\nEXPOSE 8080\nCMD ["/api"]\n')
    ctx.write("依頼メモ.txt", "ビルド用ツールを実行イメージから外すこと。\n"
              "マルチステージで静的バイナリを scratch にコピーし lq-api:small をビルド。\n"
              "完成イメージは30MB未満。lq-small としてバックグラウンド起動する。\n")


def c76(ctx):
    import re
    df = ctx.read("Dockerfile")
    if len(re.findall(r"^\s*FROM\s", df, re.M | re.I)) < 2 or not re.search(r"^\s*COPY\s+--from=", df, re.M | re.I):
        ctx.fail("Dockerfile をマルチステージにし、COPY --from= でビルド成果物を実行ステージへコピーしましょう。")
    if not re.search(r"^\s*FROM\s+scratch\s*$", df, re.M | re.I):
        ctx.fail("最後の実行用ステージには scratch を使いましょう。")
    img = ctx.docker.image_details("lq-api:small")
    if not img:
        ctx.fail("lq-api:small がありません。docker build -t lq-api:small . を実行しましょう。")
    if img.get("size_bytes", 0) >= 30_000_000:
        ctx.fail("イメージが30MB以上あります。ビルド用ツールやソースを実行イメージへコピーしていませんか？")
    c = need_running(ctx, "lq-small")
    if c["image"] != "lq-api:small":
        ctx.fail("lq-small は lq-api:small から起動しましょう。")
    # scratch にはシェルがないため、実バイナリの存在・起動はコンテナ状態で検証する。


MULTI_SOLUTION = "cat > Dockerfile <<'EOF'\n" + MULTI_OK + "EOF\ndocker build -t lq-api:small .\ndocker run -d --name lq-small --label lq=1 lq-api:small"
register(
    id="7-6", stage=S, title="マルチステージビルドで実行イメージを軽量化せよ", docker=True,
    story="Go 製 API の Dockerfile が開発ツールを丸ごと含み、大きすぎる。ビルドと実行を別ステージに分け、scratch で動く軽量イメージに改善しよう。Go のソース編集は不要です。",
    objectives=["ビルドステージと scratch の実行ステージを分け、COPY --from= でバイナリだけ渡す", "lq-api:small を30MB未満でビルドする", "lq-small を完成イメージからバックグラウンド起動する"],
    hints=["Go コンパイラは実行時には不要です。FROM を2つ書き、成果物だけを次のステージへコピーします。", "FROM golang:1.23 AS builder でビルドし、FROM scratch へ COPY --from=builder します。scratch には共有ライブラリもシェルもありません。", "CGO_ENABLED=0 go build -ldflags=\"-s -w\" -o /out/api . → FROM scratch → COPY --from=builder /out/api /api → CMD [\"/api\"]"],
    answer=MULTI_SOLUTION,
    explanation="マルチステージビルドはステージ間で必要な成果物だけを渡す仕組みです。CGO_ENABLED=0 で C ライブラリに依存しない Go バイナリを作り、scratch にコピーします。scratch には /bin/sh がないので CMD は JSON 形式を使います。docker images でサイズ、docker logs と docker ps で起動状態を確認します。",
    tip="scratch には CA 証明書やタイムゾーン情報もありません。HTTPS 通信するアプリには証明書をコピーするか、必要な実行ファイルを備えた distroless を検討します。",
    setup=s76, check=c76, solution=MULTI_SOLUTION,
    wrong=["docker build -t lq-api:small .\ndocker run -d --name lq-small lq-api:small", MULTI_SOLUTION.replace("CGO_ENABLED=0", "CGO_ENABLED=1"), MULTI_SOLUTION.replace('CMD ["/api"]', 'CMD ["/missing"]')],
)


# ================================================================== 7-7
HEALTH_SOLUTION = "docker rm -f lq-health\ndocker run -d --name lq-health --label lq=1 --restart unless-stopped --health-cmd 'curl -f http://localhost/ || exit 1' --health-interval 1s --health-retries 2 nginx\nfor i in {1..30}; do [ \"$(docker inspect -f '{{.State.Health.Status}}' lq-health)\" = healthy ] && break; sleep 1; done\ndocker inspect lq-health"


def s77(ctx):
    ctx.docker.reset()
    ctx.docker.add_container("lq-health", "nginx")
    ctx.write("依頼メモ.txt", "lq-health を nginx で稼働。HTTP によるヘルスチェックを付け healthy にし、\n"
              "再起動ポリシー unless-stopped を設定する。ホストへの公開は不要。\n")


def c77(ctx):
    c = need_running(ctx, "lq-health")
    if not image_matches(c["image"], "nginx"):
        ctx.fail("このサービスは nginx イメージを使って起動してください。")
    if c.get("restart_policy") != "unless-stopped":
        ctx.fail("再起動ポリシーが unless-stopped ではありません。--restart unless-stopped を指定しましょう。")
    test = (c.get("healthcheck") or {}).get("test", [])
    command = " ".join(test[1:])
    if not any(tool in command for tool in ("curl", "wget")) or not any(url in command for url in ("http://localhost", "http://127.0.0.1")):
        ctx.fail("ヘルスチェックはローカル HTTP 応答を検査するコマンドにしましょう。true だけではアプリの障害を検出できません。")
    if c.get("health") != "healthy":
        ctx.fail("ヘルスチェックが healthy ではありません。docker inspect の State.Health.Log でコマンドの失敗理由を調べましょう。設定直後なら少し待って再判定してください。")
    _, code = ctx.docker.exec("lq-health", "curl", "-f", "http://localhost/")
    if code:
        ctx.fail("nginx の HTTP 応答を取得できません。サービスの稼働を確認しましょう。")


register(
    id="7-7", stage=S, title="ヘルスチェックと再起動ポリシーで運用を固めよ", docker=True,
    story="コンテナが Up でもアプリが応答しているとは限らない。nginx に HTTP ヘルスチェックと再起動ポリシーを設定し、運用監視に備えよう。",
    objectives=["lq-health を nginx で起動する", "HTTP ヘルスチェックを設定して healthy にする", "再起動ポリシーを unless-stopped にする"],
    hints=["docker ps の Up はプロセスが生きているという意味です。HTTP 応答を監視するヘルスチェックを追加します。", "--health-cmd と --health-interval で監視、--restart unless-stopped で異常終了後の再起動方針を設定します。", "--health-cmd 'curl -f http://localhost/ || exit 1' --health-interval 1s --restart unless-stopped を付けて作り直し、docker inspect で healthy を確認しましょう。"],
    answer=HEALTH_SOLUTION,
    explanation="HEALTHCHECK は終了コード0を成功、それ以外を失敗として状態を healthy/unhealthy にします。curl -f は HTTP エラーでも失敗します。再起動ポリシーはメインプロセスが終了した時に適用されます。unhealthy になっただけで Docker が自動再起動するわけではありません。unless-stopped は明示的に停止したコンテナを停止状態のままにします。",
    tip="障害対応では docker logs、inspect の State.Health.Log、RestartCount を組み合わせます。起動が遅いアプリは --health-start-period で準備期間を設け、無用な unhealthy 判定を避けましょう。",
    setup=s77, check=c77, solution=HEALTH_SOLUTION,
    wrong=["docker rm -f lq-health\ndocker run -d --name lq-health --restart unless-stopped nginx", HEALTH_SOLUTION.replace("--restart unless-stopped", "--restart no"), HEALTH_SOLUTION.replace("curl -f http://localhost/ || exit 1", "true"), HEALTH_SOLUTION.replace("http://localhost/", "http://localhost:9999/").replace('{1..30}', '{1..2}')],
)
