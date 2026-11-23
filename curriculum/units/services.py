"""達人モードのユニット：サービス・ログ・パッケージ・プロセスの管理（systemctl / journalctl / cron / apt / top / lsof）。

状態を持つ模擬コマンドは engine/commands/services.py にある。課題は「どう打つか」ではなく
「何を達成したいか」で書き、判定は最後の状態（またはコマンドの要素）で行う。
"""
import re
import shlex

from curriculum.lesson_kit import lesson, all_of, has_package

UNIT_TITLE = "サービスとログの管理"
ORDER = 60

NGINX_ON = {"nginx": {"active": "active", "enabled": True, "since": "Thu 2026-01-15 08:00:00 JST", "ago": "1h 30min ago"}}


# ---- 判定の部品
def _tokens(t):
    """最後に入力した1行を単語に分ける（先頭の sudo は外す）。"""
    words = shlex.split(t.progress["command_events"][-1]["line"])
    return words[1:] if words[:1] == ["sudo"] else words


def typed(check):
    return lambda t: bool(check(_tokens(t)))


def _has(words, *options):
    return any(w in options or any(w.startswith(o + "=") for o in options if o.startswith("--")) for w in words)


def _after(words, *options):
    """オプションの値（-u ssh / -ussh / --unit=ssh のどれでも）を返す。"""
    values = []
    words = [piece for w in words for piece in (["-f", "-u", w[3:]] if w.startswith("-fu") and len(w) > 3 else
                                               ["-f", "-u"] if w == "-fu" else [w])]
    for i, w in enumerate(words):
        for o in options:
            if w == o and i + 1 < len(words):
                values.append(words[i + 1])
            elif w.startswith(o + "=") and o.startswith("--"):
                values.append(w.split("=", 1)[1])
            elif w.startswith(o) and not o.startswith("--") and len(w) > len(o) and not w.startswith("--"):
                values.append(w[len(o):])
    return values


def unit(name):
    return lambda t: t.progress["services"]["units"][name]


def active(name):
    return lambda t: unit(name)(t)["active"] == "active"


def inactive(name):
    return lambda t: unit(name)(t)["active"] == "inactive"


def enabled(name, value=True):
    return lambda t: unit(name)(t)["enabled"] is value


def logged(name, text):
    return lambda t: any(r[1] == name and text in r[5] for r in t.progress["services"]["journal"])


def no_process(pid):
    return lambda t: all(p["pid"] != pid for p in t.progress["processes"])


def _ssh_service(words):
    return words[:2] == ["systemctl", "status"] and words[2:] in (["ssh"], ["ssh.service"])


AUTH_LOG = (
    "Jan 15 02:17:44 training-server sshd[3011]: Failed password for invalid user admin from 198.51.100.23 port 40122 ssh2\n"
    "Jan 15 02:17:49 training-server sshd[3011]: Failed password for invalid user admin from 198.51.100.23 port 40122 ssh2\n"
    "Jan 15 02:18:02 training-server sshd[3015]: Failed password for invalid user root from 198.51.100.23 port 40130 ssh2\n"
    "Jan 15 08:55:10 training-server sudo:  learner : TTY=pts/0 ; PWD=/home/learner ; USER=root ; COMMAND=/usr/bin/systemctl restart ssh\n"
    "Jan 15 09:12:03 training-server sshd[3201]: Accepted publickey for learner from 192.0.2.10 port 51888 ssh2\n"
    "Jan 15 09:12:03 training-server systemd-logind[640]: New session 12 of user learner.\n"
    "Jan 15 09:20:00 training-server sudo:  learner : TTY=pts/0 ; PWD=/home/learner ; USER=root ; COMMAND=/usr/bin/apt update\n")
SYSLOG = (
    "Jan 15 03:00:01 training-server CRON[3120]: (root) CMD (/usr/local/bin/backup.sh)\n"
    "Jan 15 03:00:03 training-server CRON[3120]: (root) MAIL (mailed 1 byte of output; but got status 0x0001)\n"
    "Jan 15 06:30:00 training-server rsyslogd: [origin software=\"rsyslogd\"] rsyslogd was HUPed\n"
    "Jan 15 08:41:10 training-server demo-app[3342]: fatal: cannot open database file: disk quota exceeded\n"
    "Jan 15 08:41:12 training-server systemd[1]: demo-app.service: Failed with result 'exit-code'.\n"
    "Jan 15 09:20:31 training-server CRON[3260]: (learner) CMD (/home/learner/bin/cleanup.sh)\n")
MYCRON = "# 毎日 2:30 にバックアップを取る\n30 2 * * * /home/learner/bin/backup.sh\n"
BADCRON = "# 数字がおかしい\n61 25 * * * /home/learner/bin/backup.sh\n"

LESSONS = [
    lesson("ex-services-01", "サービスの状態を見る",
           "Linux のサーバーでは、Web サーバーや SSH のように裏でずっと動く仕組みを「サービス」と呼び、systemd という管理役がまとめて面倒を見ます。"
           "その管理役に話しかける道具が systemctl です。まずは様子を見るだけの安全な操作から始めましょう。",
           "SSH サーバー（ユニット名は短く ssh）が今どういう状態か、起動時刻や直近のログも含めて詳しく確認しましょう。",
           "systemctl status ssh",
           "active (running) と出ていれば元気に動いています。Loaded 行の enabled は「次回の起動時にも自動で立ち上がる」という意味で、Active とは別の話です。",
           accept=["systemctl status ssh.service"], goal=typed(_ssh_service),
           hints=["「今の状態を詳しく見る」という、読むだけの操作です。サービス管理役の道具を思い出しましょう。",
                  "道具は systemctl。その後ろにやりたいこと（状態は英語で status）とサービス名を続けます。",
                  "入力例: systemctl status ssh"]),
    lesson("ex-services-02", "動いているかだけを知る",
           "スクリプトの中でサービスの生死を判断したいときは、長い表示ではなく「一言の答え」と終了コードが便利です。"
           "systemctl には is-active という質問があり、active / inactive / failed のどれかを答えます。",
           "cron サービスが動いているかどうかを、一言で答えてもらいましょう。",
           "systemctl is-active cron",
           "active と返りました。動いていれば終了コード 0、そうでなければ 0 以外になるので、if 文の条件にも使えます。",
           accept=["systemctl is-active cron.service"],
           hints=["長い説明は要りません。「動いている？」に一言で答えてくれる質問の形を探しましょう。",
                  "systemctl の後ろに、is- で始まる質問（active かどうか）を置きます。",
                  "入力例: systemctl is-active cron"]),
    lesson("ex-services-03", "止まっているサービスの表示",
           "Web サーバーの nginx は、このサーバーではまだ起動していません。止まっているサービスの status は、○ のしるしと inactive (dead) で表示されます。"
           "なお status は状態が active でないとき、終了コード 3 を返します。エラーではなく「止まっている」という合図です。",
           "nginx のサービスの状態を確認して、止まっていることを自分の目で確かめましょう。",
           "systemctl status nginx",
           "inactive (dead) です。「止まっている」と「壊れている（failed）」は別物だと覚えておきましょう。",
           accept=["systemctl status nginx.service"], expected_code=3,
           goal=typed(lambda w: w[:2] == ["systemctl", "status"] and w[2:] in (["nginx"], ["nginx.service"])),
           hints=["最初のレッスンと同じ「状態を見る」操作を、別のサービスに対して行います。",
                  "systemctl の status にサービス名 nginx を渡します。止まっているときの終了コードは 3 です。",
                  "入力例: systemctl status nginx"]),
    lesson("ex-services-04", "失敗したサービスを探す",
           "サーバーが多くなると、全サービスを1つずつ見るわけにはいきません。systemd は「失敗（failed）状態のユニットだけ」を一覧にできます。"
           "障害対応の最初の一手として、とてもよく使われます。",
           "いま失敗状態になっているサービスの一覧を表示しましょう。",
           "systemctl list-units --failed",
           "demo-app.service が failed と分かりました。次は、なぜ失敗したのかをログで調べます。",
           accept=["systemctl --failed", "systemctl list-units --state=failed"],
           goal=typed(lambda w: w[:1] == ["systemctl"] and (_has(w, "--failed") or "failed" in _after(w, "--state"))),
           hints=["「全部」ではなく「失敗したものだけ」を絞り込んで一覧にしたいのです。",
                  "systemctl には、ユニットを一覧にする操作（list で始まる）があり、失敗に絞るオプションは英語の「失敗した」です。",
                  "入力例: systemctl list-units --failed"]),
    lesson("ex-services-05", "失敗したサービスの詳細",
           "failed のサービスの status には「どのプログラムが、どんな終了コードで終わったか」と、直近のログが表示されます。"
           "status の末尾のログは、原因を探す最初の手がかりです。",
           "失敗しているサービス demo-app の状態と、末尾のログを確認しましょう。",
           "systemctl status demo-app",
           "status=1/FAILURE は、プログラム自体が異常終了したことを示します。ログに「disk quota exceeded」とあり、ディスクの使用量制限が原因の候補だと分かります。",
           accept=["systemctl status demo-app.service"], expected_code=3,
           goal=typed(lambda w: w[:2] == ["systemctl", "status"] and w[2:] in (["demo-app"], ["demo-app.service"])),
           hints=["失敗の理由は、状態表示の中の「終了コード」と「最後のログ」に隠れています。",
                  "systemctl の status を、失敗しているサービス名 demo-app に対して使います。",
                  "入力例: systemctl status demo-app"]),
    lesson("ex-services-06", "権限がないと拒否される",
           "サービスの起動・停止はシステム全体に影響するため、一般ユーザーには許されません。"
           "管理者権限なしで試すと、認証が必要だというメッセージが出て、何も変わりません。これは正常な保護です。",
           "管理者権限を使わずに nginx を起動しようとして、拒否される様子を確かめましょう。",
           "systemctl start nginx",
           "Interactive authentication required と拒否されました。サービスの操作には sudo が必要です。",
           accept=["systemctl start nginx.service"], expected_code=1,
           goal=typed(lambda w: w[:2] == ["systemctl", "start"] and w[2:] in (["nginx"], ["nginx.service"])),
           hints=["「起動」を頼むだけです。あえて管理者権限は付けません。",
                  "systemctl に start（起動）とサービス名を渡します。sudo は付けません。",
                  "入力例: systemctl start nginx"]),
    lesson("ex-services-07", "サービスを起動する",
           'サービスの起動はシステム全体への変更なので、権限が必要です。成功しても何も表示されない場合があります。画面の文字だけでなく、変更後の状態にも注目しましょう。',
           "nginx を管理者権限で起動して、動いている状態にしましょう。",
           "sudo systemctl start nginx",
           "起動しました。成功時は無言なので、続けて status で確かめる癖をつけましょう。",
           accept=["sudo systemctl start nginx.service", "sudo systemctl restart nginx", "sudo systemctl enable --now nginx"],
           goal=active("nginx"),
           hints=["今まで止まっていたサービスを動かしたい、という状態変更です。管理者権限が必要でした。",
                  "sudo を前に付けて、systemctl の start（起動）にサービス名 nginx を渡します。",
                  "入力例: sudo systemctl start nginx"]),
    lesson("ex-services-08", "サービスを停止する",
           "動いているサービスを止めるのが stop です。メンテナンスの前や、不要なサービスを止めたいときに使います。"
           "止めても「次回起動時に自動で立ち上がる設定」はそのままなので、再起動すると戻ってくることがあります。",
           "いま動いている nginx を、管理者権限で停止しましょう。",
           "sudo systemctl stop nginx",
           "停止しました。ps や status で、もう動いていないことも確認できます。",
           accept=["sudo systemctl stop nginx.service"], services=NGINX_ON, goal=inactive("nginx"),
           hints=["動いているものを「止める」操作です。起動と対になる言葉を考えましょう。",
                  "sudo と systemctl に、停止を意味する英語（stop）とサービス名を渡します。",
                  "入力例: sudo systemctl stop nginx"]),
    lesson("ex-services-09", "再起動する",
           "設定ファイルを書き換えたあとなど、サービスを一度止めて起動し直したいときに restart を使います。"
           "止まっているサービスに使うと、そのまま起動してくれます。再起動の間は、短い時間だけ接続が切れます。",
           "動いている nginx を、いったん止めてから起動し直しましょう。",
           "sudo systemctl restart nginx",
           "再起動しました。ログにも「Stopping」と「Started」が記録されます。接続を切りたくないときは、次の reload を使います。",
           accept=["sudo systemctl restart nginx.service"], services=NGINX_ON, goal=logged("nginx", "Started nginx"),
           hints=["「止める＋起動する」を1回の操作でやってくれる動詞があります。",
                  "sudo systemctl の後ろに、英語の「再起動」を意味する語とサービス名を置きます。",
                  "入力例: sudo systemctl restart nginx"]),
    lesson("ex-services-10", "止めずに設定を読み直す",
           "reload は、サービスを止めずに設定だけ読み直させる穏やかな方法です。接続中の利用者を切らずに済みます。"
           "ただし、すべてのサービスが reload に対応しているわけではありません。対応していなければ restart を使います。",
           "nginx を止めずに、設定の読み直しだけを管理者権限で依頼しましょう。",
           "sudo systemctl reload nginx",
           "設定を読み直しました。restart と違い、プロセスは入れ替わりません。",
           accept=["sudo systemctl reload nginx.service"], services=NGINX_ON, goal=logged("nginx", "Reloaded nginx"),
           hints=["止めたくないので、再起動ではなく「読み直し」を意味する動詞を探します。",
                  "sudo systemctl の後ろに、英語の「再読み込み」を意味する語とサービス名を置きます。",
                  "入力例: sudo systemctl reload nginx"]),
    lesson("ex-services-11", "次回起動でも自動で立ち上げる",
           "start は「今」起動するだけです。サーバーを再起動したあとも自動で立ち上がってほしいなら、enable（有効化）という別の設定が必要です。"
           "「今動かす」と「起動時に自動で動かす」は別のスイッチだと覚えましょう。",
           "nginx が、サーバーの再起動後にも自動で起動するように設定しましょう（今すぐ起動する必要はありません）。",
           "sudo systemctl enable nginx",
           "enabled になりました。symlink（ショートカット）が作られ、起動時に systemd がそれをたどって立ち上げます。",
           accept=["sudo systemctl enable nginx.service", "sudo systemctl enable --now nginx"], goal=enabled("nginx"),
           hints=["今ではなく「次回以降の起動」に関する設定を変えたいのです。",
                  "sudo systemctl の後ろに、英語の「有効にする」を意味する語とサービス名を置きます。",
                  "入力例: sudo systemctl enable nginx"]),
    lesson("ex-services-12", "有効化と起動を同時に行う",
           "新しいサービスを導入するときは「今すぐ動かす」と「起動時にも動かす」の両方がほしいことが多いです。"
           "enable には、起動も一緒に行うオプション（--now）があります。",
           "nginx を、今すぐ起動し、なおかつ次回以降も自動で起動する状態にしましょう。1回の入力で済ませてみてください。",
           "sudo systemctl enable --now nginx",
           "起動と有効化が同時にできました。別々に start と enable を打っても同じ結果になります。",
           accept=["sudo systemctl enable --now nginx.service"], goal=all_of(active("nginx"), enabled("nginx")),
           hints=["2つの目的（今動かす・自動で動かす）を、1つの操作で叶えるオプションがあります。",
                  "systemctl の enable に、「今すぐ」を意味する英語のオプション（--now）を付けます。管理者権限も必要です。",
                  "入力例: sudo systemctl enable --now nginx"]),
    lesson("ex-services-13", "自動起動をやめる",
           "不要になったサービスは、停止だけでなく自動起動も外しておかないと、次の再起動でまた立ち上がってしまいます。"
           "disable は自動起動の設定だけを外し、今動いているものは止めません。止めるにも同時に行うなら --now を付けます。",
           "nginx が自動で起動しないように設定し、さらに今動いているものも止めましょう。",
           "sudo systemctl disable --now nginx",
           "停止と無効化が済みました。--now なしの disable だと、自動起動は外れても今のプロセスは動き続けます。",
           accept=["sudo systemctl disable --now nginx.service"], services=NGINX_ON,
           goal=all_of(inactive("nginx"), enabled("nginx", False)),
           hints=["enable の反対の操作を、停止まで含めて行います。",
                  "systemctl の disable を使い、停止も同時に行うオプション（--now）を付けます。管理者権限も必要です。",
                  "入力例: sudo systemctl disable --now nginx"]),
    lesson("ex-services-14", "自動起動の設定を確認する",
           "is-enabled は、自動起動が有効かどうかを一言で教えてくれます。enabled / disabled が返り、"
           "disabled のときは終了コードが 0 以外になります。",
           "nginx が、起動時に自動で立ち上がる設定になっているかを、一言で答えてもらいましょう。",
           "systemctl is-enabled nginx",
           "disabled でした。まだ設定していないので、再起動すると nginx は止まったままです。",
           accept=["systemctl is-enabled nginx.service"], expected_code=1,
           goal=typed(lambda w: w[:2] == ["systemctl", "is-enabled"] and w[2:3] in (["nginx"], ["nginx.service"])),
           hints=["「今動いている？」とは別の質問です。「自動で起動する設定？」と聞きたいのです。",
                  "is-active の仲間で、enabled かどうかを聞く質問があります。",
                  "入力例: systemctl is-enabled nginx"]),
    lesson("ex-services-15", "失敗したサービスを起動し直す",
           '失敗していた原因のディスク制限は、別の担当者が解消しました。原因が取り除かれたので、サービスを復旧させましょう。',
           "失敗状態の demo-app を、管理者権限で再び動かしましょう。",
           "sudo systemctl restart demo-app",
           "復旧しました。ただし、原因を直さずに起動し直しても、また同じ理由で落ちます。必ずログで原因を確認してから行いましょう。",
           accept=["sudo systemctl start demo-app", "sudo systemctl start demo-app.service", "sudo systemctl restart demo-app.service"],
           goal=active("demo-app"),
           hints=["failed のサービスも、起動の依頼は受け付けます。起動する操作をもう一度行いましょう。",
                  "sudo systemctl の後ろに、起動（start）か再起動（restart）を指定し、サービス名 demo-app を渡します。",
                  "入力例: sudo systemctl restart demo-app"]),
    lesson("ex-services-16", "failed の印を消す",
           "起動し直さなくても、failed の記録は残り続けます。原因を調べ終えて「もう気にしなくてよい」状態にしたいときは、"
           "reset-failed でその記録だけを消せます。サービス自体は起動しません。",
           "demo-app の failed の記録を消して、失敗一覧に載らないようにしましょう（起動はしません）。",
           "sudo systemctl reset-failed",
           "failed の印が消えました。これは記録の掃除であり、問題が直ったという意味ではありません。",
           accept=["sudo systemctl reset-failed demo-app"], goal=all_of(inactive("demo-app"), lambda t: True),
           hints=["問題を直すのではなく、「失敗した」というメモを消したいのです。",
                  "systemctl に、失敗状態を「リセット」する操作があります。管理者権限が必要です。",
                  "入力例: sudo systemctl reset-failed"]),
    lesson("ex-services-17", "ログの最後の数行を見る",
           "systemd の仕組みでは、サービスのログは journal（ジャーナル）という場所に集められ、journalctl で読みます。"
           "全部を出すと膨大なので、まずは「末尾の数行」だけ見るのが基本です。行数は -n で指定します。",
           "システム全体のログの、最後の5行だけを表示しましょう。",
           "journalctl -n 5",
           "新しい行ほど下に出ます。-n は「最後から数えて何行」という意味です。",
           accept=["journalctl -n5", "journalctl --lines=5", "journalctl --no-pager -n 5", "sudo journalctl -n 5"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and _after(w, "-n", "--lines") == ["5"] and not _after(w, "-u", "--unit")),
           hints=["膨大なログのうち、新しい部分だけを少し覗きたいのです。",
                  "ログを読む道具 journalctl に、行数を指定するオプション（-n）を付けます。",
                  "入力例: journalctl -n 5"]),
    lesson("ex-services-18", "サービスごとのログ",
           "journalctl は、-u（unit）でサービスを指定すると、そのサービスのログだけに絞れます。"
           "system 全体のログから目的のサービスの行だけを探す手間がなくなります。",
           "SSH サーバー（ssh）のログだけを表示しましょう。",
           "journalctl -u ssh",
           "ssh の記録だけが時刻順に並びました。ログイン成功や失敗が記録されているのが分かります。",
           accept=["journalctl -u ssh.service", "journalctl --unit=ssh", "journalctl --unit ssh", "journalctl --no-pager -u ssh"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and any(v in ("ssh", "ssh.service") for v in _after(w, "-u", "--unit"))),
           hints=["全体ではなく、特定のサービスの記録だけがほしいのです。",
                  "journalctl に、ユニット（サービス）を指定するオプションとサービス名 ssh を渡します。",
                  "入力例: journalctl -u ssh"]),
    lesson("ex-services-19", "サービスのログの末尾だけ",
           '障害対応では、大量の履歴よりも目的のサービスで直近に起きたことを知りたい場合があります。必要な範囲の記録だけを調べましょう。',
           "SSH サーバーのログの、最後の3行だけを表示しましょう。",
           "journalctl -u ssh -n 3",
           "絞り込みと行数の指定を組み合わせました。status の末尾ログも、実はこの仕組みを使っています。",
           accept=["journalctl -n 3 -u ssh", "journalctl -u ssh --lines=3", "journalctl -u ssh.service -n 3", "journalctl -n3 -u ssh"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and _after(w, "-n", "--lines") == ["3"]
                      and any(v in ("ssh", "ssh.service") for v in _after(w, "-u", "--unit"))),
           hints=["前の2つのレッスン（サービスで絞る・行数で絞る）を両方使います。",
                  "journalctl に、ユニット指定（-u）と行数指定（-n）を同時に付けます。",
                  "入力例: journalctl -u ssh -n 3"]),
    lesson("ex-services-20", "エラーだけを見る",
           "ログには「優先度」があり、emerg（緊急）から debug まで8段階です。-p でエラー以上の重要なものだけに絞れます。"
           "障害のときは、何千行もの普通のログより、数行のエラーのほうが重要です。",
           "システム全体のログから、エラー（err）以上の重要度のものだけを表示しましょう。",
           "journalctl -p err",
           "err 以上（err / crit / alert / emerg）だけが出ました。優先度は 3 のように数字でも指定できます。",
           accept=["journalctl -p 3", "journalctl --priority=err", "journalctl --priority err", "journalctl -p err --no-pager"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and any(v in ("err", "3") for v in _after(w, "-p", "--priority"))
                      and not _after(w, "-u", "--unit")),
           hints=["ログの「重要度」で絞り込みたいのです。オプションは priority の頭文字です。",
                  "journalctl に、重要度を指定するオプション（-p）と、エラーを意味する語（err）を渡します。",
                  "入力例: journalctl -p err"]),
    lesson("ex-services-21", "今日のログだけ",
           "古いログまで見ると目的の行が埋もれます。--since で「この時刻以降」に絞れます。"
           "today のほか、日付（2026-01-15）、時刻付きの日時、1 hour ago のような相対表現も使えます。",
           "システム全体のログのうち、今日の分（0 時以降）だけを表示しましょう。",
           "journalctl --since today",
           "昨日までのログが消え、今日の分だけが出ました。--until と組み合わせれば、「この時間帯だけ」も指定できます。",
           accept=["journalctl --since 2026-01-15", "journalctl --since=today", "journalctl --since '2026-01-15 00:00:00'"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and any(v in ("today", "2026-01-15", "2026-01-15 00:00:00", "2026-01-15 00:00")
                                                                 for v in _after(w, "--since"))),
           hints=["時間で絞り込みたいのです。「いつから」を意味する英語の前置詞を思い出しましょう。",
                  "journalctl に、--since と、「今日」を意味する英語（または日付）を渡します。",
                  "入力例: journalctl --since today"]),
    lesson("ex-services-22", "最近1時間のログ",
           "障害は「さっき」起きることが多いので、相対的な指定が便利です。--since には「1 hour ago」のように、英語で「〜前」と書けます。"
           "空白を含むので、全体を引用符で囲む点に注意してください。",
           "システム全体のログから、直近1時間のものだけを表示しましょう。",
           "journalctl --since '1 hour ago'",
           "1時間以内の行だけが出ました。'30 min ago' や '2 days ago' のようにも書けます。",
           accept=['journalctl --since "1 hour ago"', "journalctl --since '60 min ago'", "journalctl --since='1 hour ago'"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and any(re.fullmatch(r"(1 hour|60 min|60 minutes|1 hours) ago", v)
                                                                 for v in _after(w, "--since"))),
           hints=["「何時何分から」ではなく、「いまから◯時間前から」と指定したいのです。",
                  "--since の値に、英語で「1 hour ago」と書き、空白があるので引用符で囲みます。",
                  "入力例: journalctl --since '1 hour ago'"]),
    lesson("ex-services-23", "失敗の原因をログで探す",
           '失敗したサービスの原因を調べます。システム全体の正常な記録に埋もれないよう、そのサービスのエラーに注目しましょう。',
           "demo-app のログから、エラーの行だけを取り出して失敗の原因を調べましょう。",
           "journalctl -u demo-app -p err",
           "「disk quota exceeded」という原因が見つかりました。復旧の前に、必ずこうして原因を確かめます。",
           accept=["journalctl -u demo-app | grep fatal", "journalctl -u demo-app --priority=err", "journalctl -p err -u demo-app",
                   "journalctl -u demo-app | grep -i fatal"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and "demo-app" in " ".join(w)
                      and (any(v in ("err", "3") for v in _after(w, "-p", "--priority")) or "grep" in w)),
           hints=["「demo-app」に関する記録のうち、「重要なエラーだけ」を取り出したいのです。",
                  "journalctl の -u で demo-app に絞り、-p で重要度を絞ります。grep で文字を探すやり方でも構いません。",
                  "入力例: journalctl -u demo-app -p err"]),
    lesson("ex-services-24", "ログを追いかける",
           "-f（follow）を付けると、新しい行が増えるたびに画面に流れ続けます（tail -f と同じ考え方）。"
           "サービスを再起動しながら様子を見るときの定番です。本物では Ctrl+C で止めます。この練習では今ある最後の部分だけ表示されます。",
           "SSH サーバーのログを、新しい行が増えるのを追いかけながら表示しましょう。",
           "journalctl -u ssh -f",
           "実際の運用では、別の画面で -f を動かしながら、もう一方で restart などを試します。",
           accept=["journalctl -f -u ssh", "journalctl -fu ssh", "journalctl --follow -u ssh", "journalctl -u ssh --follow", "journalctl -u ssh.service -f"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and (_has(w, "-f", "--follow") or any(re.fullmatch(r"-\w*f\w*", x) and not x.startswith("--") for x in w))
                      and any(v in ("ssh", "ssh.service") for v in _after(w, "-u", "--unit"))),
           hints=["ログが「増えていく様子」をリアルタイムで見たいのです。英語の「追跡する」を思い出しましょう。",
                  "journalctl に、ssh を指定する -u と、追跡のオプション（follow の頭文字）を付けます。",
                  "入力例: journalctl -u ssh -f"]),
    lesson("ex-services-25", "ログから不審なログインを探す",
           'ログインに失敗した記録は、不審な接続元を見つける手がかりです。正常な接続の記録と区別して調べましょう。',
           "ジャーナルの中から、パスワードの入力に失敗した記録（Failed という語を含む行）だけを探しましょう。",
           "journalctl -u ssh | grep Failed",
           "198.51.100.23 という同じ IP から何度も失敗しています。ブルートフォース攻撃の疑いです。ログの調査は、このように「絞って探す」作業の繰り返しです。",
           accept=["journalctl | grep Failed", "journalctl -u ssh.service | grep Failed", "journalctl -u ssh | grep 'Failed password'",
                   "journalctl | grep 'Failed password'", "journalctl -u ssh | grep -i failed", "journalctl -p warning | grep Failed"],
           goal=typed(lambda w: w[:1] == ["journalctl"] and "|" in w and "grep" in w
                      and any("failed" in x.lower() for x in w[w.index("grep"):])),
           hints=["ログのうち「失敗」という語を含む行だけがほしいのです。2つの道具をつなぎます。",
                  "journalctl の出力を、パイプ（|）で grep に渡します。探す語は Failed です。",
                  "入力例: journalctl -u ssh | grep Failed"]),
    lesson("ex-services-26", "カーネルのメッセージ（権限なし）",
           "カーネル（OS の中心部分）は、ハードウェアの認識やエラーを「カーネルリングバッファ」に書き留めます。それを読む道具が dmesg です。"
           "最近の Ubuntu では、一般ユーザーには読ませない設定になっています。",
           "管理者権限なしで、カーネルのメッセージを読もうとして、どうなるか確かめましょう。",
           "dmesg",
           "Operation not permitted と拒否されました。カーネルのメッセージには内部情報が含まれるため、管理者だけに制限されています。",
           expected_code=1, goal=typed(lambda w: w == ["dmesg"]),
           hints=["ログではなく、OS の中心（カーネル）自身の記録を読みたいのです。",
                  "道具の名前は、「診断メッセージ」を意味する英語の短縮形です。オプションなしで使います。",
                  "入力例: dmesg"]),
    lesson("ex-services-27", "カーネルのエラーを人が読める時刻で",
           "dmesg の時刻は、通常「起動から何秒」という形で出るため分かりにくいです。-T を付けると、普通の日時に変換されます。"
           "また -l（level）で重要度を絞れます。ディスクの I/O エラーやメモリ不足でプロセスが強制終了された記録も、ここに出ます。",
           "管理者権限で、カーネルのエラー（err）だけを、人間が読める日時付きで表示しましょう。",
           "sudo dmesg -T -l err",
           "ディスクの読み込みエラーと、メモリ不足でプロセスが強制終了（OOM Killer）された記録が見つかりました。メモリ不足は、サービスが突然落ちる代表的な原因です。",
           accept=["sudo dmesg -l err -T", "sudo dmesg -T --level=err", "sudo dmesg --level=err -T", "sudo dmesg -T -l err,crit"],
           goal=typed(lambda w: w[:1] == ["dmesg"] and _has(w, "-T") and any(v.split(",")[0] == "err" for v in _after(w, "-l", "--level"))),
           hints=["権限が必要です。そのうえで、時刻を読みやすくし、エラーだけに絞る2つの調整が必要です。",
                  "sudo dmesg に、時刻変換のオプション（大文字の T）と、重要度指定（-l）を付けます。",
                  "入力例: sudo dmesg -T -l err"]),
    lesson("ex-services-28", "カーネルのログから USB を探す",
           '機器をつないだときに認識されたかどうかは、カーネルの記録から調べられます。表記の大文字・小文字がそろわない場合にも注意しましょう。',
           "カーネルのメッセージから、USB に関する行だけを探しましょう（管理者権限が必要です）。",
           "sudo dmesg | grep -i usb",
           "USB メモリが認識された記録が見つかりました。",
           accept=["sudo dmesg | grep usb", "sudo dmesg | grep -i USB", "sudo dmesg -T | grep -i usb", "sudo dmesg | grep -i 'usb'"],
           goal=typed(lambda w: w[:1] == ["dmesg"] and "|" in w and "grep" in w and any(x.lower() == "usb" for x in w[w.index("grep"):])),
           hints=["カーネルの記録から、特定の言葉を含む行だけを抜き出します。以前のレッスンと同じ発想です。",
                  "sudo dmesg の出力を、パイプで grep に渡します。大文字小文字を無視するなら -i を付けます。",
                  "入力例: sudo dmesg | grep -i usb"]),
    lesson("ex-services-29", "/var/log のファイルを読む",
           'systemd 以外の昔ながらの方法では、ログは /var/log の中のテキストファイルに保存されます。journalctl が使えない環境でも、cat や tail や grep で読めます。練習では、その写しをフォルダに用意しました。認証のログにはログインや sudo の記録が入ります。',
           '用意されたログの写しから、認証や sudo の記録を見つけ、その最後の5行だけを表示しましょう。',
           "tail -n 5 varlog/auth.log",
           "認証に関する最新の記録が見られました。本物のサーバーでは /var/log/auth.log を同じように読みます。",
           accept=["tail -5 varlog/auth.log", "tail -n5 varlog/auth.log", "tail -n 5 ./varlog/auth.log"],
           files={"varlog/auth.log": AUTH_LOG, "varlog/syslog": SYSLOG},
           goal=typed(lambda w: w[:1] == ["tail"] and any(re.fullmatch(r"-n?\s?5|-n5", x) or x == "5" for x in w) and any(x.endswith("varlog/auth.log") for x in w)),
           hints=["ファイルの「最後の部分」だけを読めば足ります。長いファイルを全部開く必要はありません。",
                  'ls で候補を探し、cat で用途や内容を確かめます。tail に行数のオプション（-n と数字）とファイル名を渡します。',
                  "入力例: tail -n 5 varlog/auth.log"]),
    lesson("ex-services-30", "ログファイルから cron の記録を探す",
           'システムログにはさまざまな出来事が混ざっています。定期実行が実際に動いたか、関係する記録を見つけて確認しましょう。',
           '用意されたシステムログの写しから、cron が動いた記録（CRON を含む行）だけを表示しましょう。',
           "grep CRON varlog/syslog",
           "バックアップスクリプトの実行記録と、メール送信に失敗した記録が見つかりました。定期実行の確認は、まずログを見ます。",
           accept=["cat varlog/syslog | grep CRON", "grep -i cron varlog/syslog", "grep -n CRON varlog/syslog", "grep -c CRON varlog/syslog"],
           files={"varlog/syslog": SYSLOG},
           goal=typed(lambda w: w[:1] in (["grep"], ["cat"]) and any(x.lower() == "cron" for x in w) and any(x.endswith("varlog/syslog") for x in w)),
           hints=["大きなテキストファイルから、特定の言葉を含む行だけを探します。",
                  'ls で候補を探し、cat で用途や内容を確かめます。ls で候補を探し、cat で用途や内容を確かめます。grep で、探す言葉（CRON）と、ファイル名（varlog の中）を渡します。',
                  "入力例: grep CRON varlog/syslog"]),
    lesson("ex-services-31", "登録済みの定期実行を確認する",
           "cron は、決まった時刻にコマンドを自動で実行する仕組みです。利用者ごとの予定表を crontab（cron table）と呼びます。"
           "予定表は -l（list）で一覧にできます。まだ何も登録していなければ、その旨が表示されます。",
           "自分の定期実行の予定表に、何が登録されているかを確認しましょう。",
           "crontab -l",
           "「no crontab for learner」は、まだ予定表がないという意味です。エラーではなく、空の状態を示す普通の表示です。",
           expected_code=1, goal=typed(lambda w: w == ["crontab", "-l"]),
           hints=["予定表を「書き換える」のではなく、「中身を見る」だけです。",
                  "crontab に、一覧（list）を意味するオプションを付けます。",
                  "入力例: crontab -l"]),
    lesson("ex-services-32", "定期実行を登録する",
           'cron の1行は「分 時 日 月 曜日 コマンド」の順に書きます。例えば 30 2 * * * は「毎日 2 時 30 分」です。* は「すべて」を意味します。実際には crontab -e で編集画面を開くのが普通ですが、書いた行をファイルにしておき、そのファイル名を crontab に渡すことでも登録できます。用意されたファイルに、毎日 2:30 にバックアップを取る行が用意されています。',
           '用意されたバックアップの定期実行用ファイルを見つけ、その内容を自分の予定表として登録しましょう。',
           "crontab mycron",
           "登録できました。次のレッスンで中身を確認します。",
           files={"mycron": MYCRON, "bin/backup.sh": "#!/bin/bash\necho backup\n"},
           goal=lambda t: t.progress["services"]["cron"] == MYCRON.splitlines(),
           hints=["予定表の行を書いたファイルがすでにあります。それを cron に取り込みたいのです。",
                  'ls で候補を探し、cat で用途や内容を確かめます。crontab に、ファイル名を1つだけ渡します（オプションは不要です）。',
                  "入力例: crontab mycron"]),
    lesson("ex-services-33", "登録内容の読み方を確かめる",
           '登録が成功しただけでは、時刻や実行先が意図どおりとは限りません。登録後の内容を読み返して確かめましょう。',
           "登録済みの予定表を表示し、設定が意図どおりか確かめましょう。",
           "crontab -l",
           "「30 2 * * *」は毎日 2:30 に実行、という設定です。*/10 なら10分ごと、0 9 * * 1 なら毎週月曜 9:00 になります。",
           services={"cron": MYCRON.splitlines()}, goal=typed(lambda w: w == ["crontab", "-l"]),
           hints=["登録した内容を確認する操作は、予定表を「見る」ための操作です。",
                  "crontab に、一覧（list）を意味するオプションを付けます。",
                  "入力例: crontab -l"]),
    lesson("ex-services-34", "書式を間違えた予定表",
           'cron は、書式が正しくない予定表を登録時に拒否します。用意されたファイルを読んで、時刻の各項目が範囲内か確かめましょう。間違った予定表が登録され、動かないまま気づかない事故を防ぐ仕組みです。',
           '用意された定期実行用ファイルを登録しようとして、書式エラーがどう報告されるか確かめましょう。',
           "crontab badcron",
           "bad minute とエラーが出て、登録されませんでした。分は 0〜59、時は 0〜23 の範囲で指定します。",
           files={"badcron": BADCRON}, expected_code=1,
           goal=typed(lambda w: w[:2] == ["crontab", "badcron"]),
           hints=["前のレッスンと同じ登録操作を、わざと間違った内容のファイルで試します。",
                  'ls と cat で予定表のファイルを見つけ、crontab にその名前を渡します。エラーなら終了コードが0以外になります。',
                  "入力例: crontab badcron"]),
    lesson("ex-services-35", "定期実行をすべて削除する",
           "不要になった予定表は削除します。-r は確認なしですべて消すので、使う前に -l で内容を確かめる癖をつけましょう。"
           "1行だけ消したいときは、-e で編集してその行を取り除きます。",
           "自分の定期実行の予定表を、すべて削除しましょう。",
           "crontab -r",
           "予定表が消えました。-r は確認を求めません。打ち間違い（-e のつもりで -r）の事故が多いので注意が必要です。",
           services={"cron": MYCRON.splitlines()}, goal=lambda t: t.progress["services"]["cron"] is None,
           hints=["登録した予定を全部なくしたいのです。「削除」を意味する英語の頭文字を探しましょう。",
                  "crontab に、削除（remove）を意味するオプションを付けます。",
                  "入力例: crontab -r"]),
    lesson("ex-services-36", "パッケージの一覧を更新する（apt-get）",
           "ソフトを追加・更新する前に、「配布元にどんなソフトの新しい版があるか」という一覧を更新します。"
           "apt には、古くからある兄弟のコマンド apt-get があり、スクリプトの中ではこちらがよく使われます。"
           "更新の最初の一手は update。これは一覧を更新するだけで、ソフト自体は変わりません。",
           "管理者権限で、取得できるパッケージの一覧を最新にしましょう。apt-get のほうを使ってください。",
           "sudo apt-get update",
           "一覧を更新しました。「3 packages can be upgraded」は、更新できるソフトが3つあるという意味です。まだ実際には更新していません。",
           accept=["sudo apt-get -y update"], apt_updated=False,
           goal=lambda t: t.progress["apt_updated"] is True and _tokens(t)[:1] == ["apt-get"],
           hints=["ソフトそのものではなく、「配布元の目録」を新しくする操作です。",
                  "sudo と、apt の兄弟コマンドの名前（apt にハイフンと get）を使い、update を渡します。",
                  "入力例: sudo apt-get update"]),
    lesson("ex-services-37", "更新を試してみる",
           "実際に更新する前に、何が起きるかを確かめたいことがあります。-s（simulate）を付けると、実際には何も変えずに、予定だけを表示します。"
           "本番のサーバーでは、まずこれで確認するのが安全です。",
           "実際には更新せずに、更新したらどうなるかを確かめましょう（apt-get を使います）。",
           "sudo apt-get -s upgrade",
           "Inst の行が、これから更新される予定です。-s なので、実際には何も変わっていません。",
           accept=["apt-get -s upgrade", "sudo apt-get --simulate upgrade", "sudo apt-get upgrade -s", "sudo apt-get --dry-run upgrade"],
           apt_updated=True,
           goal=lambda t: _tokens(t)[:1] == ["apt-get"] and _has(_tokens(t), "-s", "--simulate", "--dry-run") and "upgrade" in _tokens(t) and not t.progress["services"]["upgraded"],
           hints=["本当に更新はしたくありません。「予行演習」ができるオプションを探します。",
                  "apt-get の upgrade に、シミュレーション（simulate の頭文字）のオプションを付けます。",
                  "入力例: sudo apt-get -s upgrade"]),
    lesson("ex-services-38", "ソフトを更新する",
           "update が「目録の更新」なら、upgrade は「入っているソフトを新しい版に更新」する操作です。"
           "-y を付けると、確認の質問に自動で「はい」と答えるので、スクリプトでよく使います。",
           "入っているソフトを、更新できる最新の版にそろえましょう（一覧はすでに更新済みです）。",
           "sudo apt-get upgrade -y",
           "libc6 や openssl などが更新されました。更新後にカーネルや主要なライブラリが変わったときは、再起動が必要な場合もあります。",
           accept=["sudo apt-get -y upgrade", "sudo apt-get upgrade"], apt_updated=True,
           goal=lambda t: bool(t.progress["services"]["upgraded"]),
           hints=["目録を新しくしただけでは、ソフトは古いままです。次にするべき操作です。",
                  "apt-get の upgrade を使います。確認を自動で承諾するなら -y を付けます。管理者権限も必要です。",
                  "入力例: sudo apt-get upgrade -y"]),
    lesson("ex-services-39", "パッケージを探す",
           "インストールしたいソフトの名前を正確に知らないときは、キーワードで検索できます。"
           "名前と説明文の両方が検索の対象です。",
           "プロセスを見やすく表示するソフト htop が、配布元にあるかどうかを検索で確かめましょう。",
           "apt search htop",
           "名前と1行の説明が表示されました。見つかったら、次に show で詳細を確認し、install で追加します。",
           accept=["apt search top"], goal=typed(lambda w: w[:2] == ["apt", "search"] and len(w) == 3 and "top" in w[2]),
           hints=["名前の一部を手がかりに、配布元の目録から探したいのです。",
                  "apt に、英語の「検索」を意味する語と、探したい名前を渡します。",
                  "入力例: apt search htop"]),
    lesson("ex-services-40", "パッケージの詳細を調べる",
           "入れる前に、そのソフトの版や説明を確認すると安心です。show は、パッケージの詳しい情報を表示します。",
           "htop というパッケージの、版と説明を調べましょう。",
           "apt show htop",
           "版と説明が表示されました。入れる前に確認する習慣は、不要なソフトの混入を防ぎます。",
           goal=typed(lambda w: w == ["apt", "show", "htop"]),
           hints=["入れる前に「中身の紹介」を見たいのです。",
                  "apt に、英語の「見せる」を意味する語と、パッケージ名 htop を渡します。",
                  "入力例: apt show htop"]),
    lesson("ex-services-41", "パッケージを追加する",
           "ソフトの追加は install です。管理者権限が必要で、一覧が古いと失敗するので、直前に update しておくのが普通です。"
           "この課題では一覧の更新は済んでいます。",
           "プロセスを見やすく表示する htop を、管理者権限で追加しましょう。",
           "sudo apt install htop",
           "追加できました。次のレッスンで使ってみます。",
           accept=["sudo apt install -y htop", "sudo apt -y install htop"], packages=[], apt_updated=True, goal=has_package("htop"),
           hints=["ソフトを新しくシステムに追加します。管理者権限が必要です。",
                  "sudo apt の後ろに、追加を意味する語（install）とパッケージ名 htop を置きます。",
                  "入力例: sudo apt install htop"]),
    lesson("ex-services-42", "入っているパッケージを一覧する",
           "システムに今何が入っているかを調べたいときは、dpkg という低レベルの道具が役に立ちます。"
           "apt が配布元との窓口なのに対し、dpkg は手元に入っているソフトの管理台帳を直接見る道具です。"
           "一覧は -l で出て、行頭の ii は「正しく導入済み」を意味します。",
           "このシステムに導入済みのパッケージを、一覧で表示しましょう。",
           "dpkg -l",
           "導入済みのパッケージと、その版が表示されました。",
           accept=["dpkg --list"], goal=typed(lambda w: w[:1] == ["dpkg"] and (w[1:] in (["-l"], ["--list"]))),
           hints=["配布元ではなく、「いま手元にあるもの」の台帳を見たいのです。",
                  "dpkg に、一覧（list）を意味するオプションを付けます。",
                  "入力例: dpkg -l"]),
    lesson("ex-services-43", "特定のパッケージが入っているか確かめる",
           '導入済みの一覧は長くなりがちです。配布元で入手できるものと、すでに手元に入っているものを区別して調べましょう。',
           "導入済みパッケージの中から、ssh を名前に含むものを探しましょう。",
           "dpkg -l | grep ssh",
           "openssh-server が入っていると分かりました。一覧を grep で絞るのは、ログ調べと同じ発想です。",
           accept=["dpkg --list | grep ssh", "dpkg -l | grep -i ssh", "dpkg -l '*ssh*'", "dpkg -l | grep openssh"],
           goal=typed(lambda w: w[:1] == ["dpkg"] and (("grep" in w and any("ssh" in x for x in w[w.index("grep"):])) or any("ssh" in x for x in w[2:]))),
           hints=["長い一覧から、特定の言葉を含む行だけを探します。パイプで別の道具へ渡す方法があります。",
                  "dpkg の一覧を、パイプ（|）で grep に渡します。探す語は ssh です。",
                  "入力例: dpkg -l | grep ssh"]),
    lesson("ex-services-44", "パッケージの版を調べる",
           "脆弱性の情報が出たとき、「自分のサーバーに入っている版は対象か」を確かめるのは基本です。"
           "dpkg の -s（status）は、1つのパッケージの状態と版を教えてくれます。",
           "openssh-server が導入されているか、どの版かを調べましょう。",
           "dpkg -s openssh-server",
           "Status が install ok installed で、版が分かりました。この版を、脆弱性情報の「影響を受ける版」と見比べます。",
           accept=["dpkg --status openssh-server"], goal=typed(lambda w: w[:1] == ["dpkg"] and _has(w, "-s", "--status") and "openssh-server" in w),
           hints=["1つのパッケージの「状態」を詳しく聞きたいのです。",
                  "dpkg に、状態（status）の頭文字のオプションと、パッケージ名 openssh-server を渡します。",
                  "入力例: dpkg -s openssh-server"]),
    lesson("ex-services-45", "パッケージを削除する",
           "不要になったソフトは削除して、システムをすっきり保ちます。remove は管理者権限が必要です。"
           "設定ファイルまで消す purge という別の方法もありますが、まずは remove を覚えましょう。",
           "導入済みの htop を、管理者権限で削除しましょう。",
           "sudo apt remove htop",
           "削除できました。使わなくなったソフトは、攻撃される面を減らす意味でも削除しておくのが安全です。",
           accept=["sudo apt remove -y htop", "sudo apt -y remove htop"], packages=["htop"], apt_updated=True,
           goal=lambda t: "htop" not in t.progress["packages"],
           hints=["追加の反対の操作です。管理者権限が必要なのは追加と同じです。",
                  "sudo apt の後ろに、削除を意味する語（remove）とパッケージ名を置きます。",
                  "入力例: sudo apt remove htop"]),
    lesson("ex-services-46", "負荷の状況を一度だけ見る",
           "サーバーが重いと言われたら、まず「いま何がCPUやメモリを使っているか」を調べます。それを表示する定番の道具が top です。"
           "普通に起動すると画面が更新され続けるので、結果を保存したいときは -b（バッチ）と -n 1（1回だけ）を付けます。",
           "いまのシステムの負荷とプロセスの一覧を、画面が更新され続けない形で1回だけ表示しましょう。",
           "top -b -n 1",
           "上の数行が全体の負荷（load average や CPU）、下がプロセスごとの使用状況です。表は CPU を使っている順に並んでいます。",
           accept=["top -bn1", "top -n 1 -b", "top -b -n1", "top -n1 -b"],
           goal=typed(lambda w: w[:1] == ["top"] and (_has(w, "-b") or "-bn1" in w) ),
           hints=["画面が更新され続けるのを避け、「写真を1枚撮る」ように1回だけ出したいのです。",
                  "top に、バッチモードを意味するオプション（-b）と、回数を指定するオプション（-n と 1）を付けます。",
                  "入力例: top -b -n 1"]),
    lesson("ex-services-47", "暴走したプロセスを止める",
           'サーバーが重い原因を調べ、CPU を使い切っているプロセスだけを止めます。他の仕事を巻き込まないよう、操作対象を確認しましょう。',
           "CPU を異常に使っているプロセスを見つけて、止めましょう。このプロセスはあなたのユーザーのものです。",
           "kill 3300",
           "暴走プロセスが止まりました。kill は「強制終了」ではなく「終了のお願い」を送る道具です。応じないときだけ、強い -9 を考えます。",
           accept=["kill -15 3300", "kill -TERM 3300", "kill -9 3300"],
           processes=[{"pid": 3300, "user": "learner", "cmd": "python3 /home/learner/loop.py", "cpu": 93.0, "mem": 4.0}],
           goal=no_process(3300),
           hints=["まず、どのプロセスが原因かを特定する必要があります。CPU の使用率で並べて見られる道具があります。",
                  "特定した PID（プロセス番号）に対して、終了を依頼する道具 kill を使います。",
                  "入力例: kill 3300"]),
    lesson("ex-services-48", "htop で対話的に見る",
           "htop は top をカラフルで見やすくしたものです。カーソルキーで選んで、そのまま kill もできます。"
           "追加インストールが必要なソフトなので、入っていないと「コマンドが見つからない」と言われます。この課題では導入済みです。",
           "導入済みの対話的なプロセス表示ツールを起動して、状況を確認しましょう。",
           "htop",
           "本物の htop は、F6 で並べ替え、F9 で kill、F10 または q で終了です。",
           packages=["htop"], goal=typed(lambda w: w == ["htop"]),
           hints=["top をさらに見やすくした、別名の道具を呼び出したいのです。",
                  "道具の名前は、top の頭に h を付けた形です。オプションは不要です。",
                  "入力例: htop"]),
    lesson("ex-services-49", "どのプロセスがポートを使っているか",
           "「ポート 22 で待ち受けているのは誰か」のような疑問に答えるのが lsof（list open files）です。"
           "Linux では通信もファイルとして扱うので、ネットワークの接続も一覧にできます。"
           "ただし、他のユーザー（root など）のプロセスの情報は、管理者権限がないと見えません。",
           "管理者権限なしで、ポート 22 を使っているプロセスを調べようとして、結果がどうなるか確かめましょう。",
           "lsof -i :22",
           "何も表示されませんでした（終了コード 1）。これは「該当なし」ではなく、権限が足りず見えていないだけの場合があります。",
           accept=["lsof -i tcp:22", "lsof -iTCP:22", "lsof -i:22"], expected_code=1,
           goal=typed(lambda w: w[:1] == ["lsof"] and any(re.search(r":22$", x) for x in w) and True),
           hints=["「どのプロセスが、このポートを使っているか」を知りたいのです。まずは管理者権限なしで試します。",
                  "lsof に、ネットワークの接続を意味するオプション（-i）と、ポート指定（コロンと番号）を付けます。",
                  "入力例: lsof -i :22"]),
    lesson("ex-services-50", "管理者権限でポートの持ち主を調べる",
           "前の課題と同じ質問を、管理者権限で行います。LISTEN は「接続を待ち受けている」という意味で、サーバーのプロセスの典型的な状態です。",
           "管理者権限で、ポート 22 を待ち受けているプロセスを調べましょう。",
           "sudo lsof -i :22",
           "sshd（PID 512）が、ポート 22 で LISTEN していると分かりました。「ポートが使われていて起動できない」という障害のときの定番の調べ方です。",
           accept=["sudo lsof -i tcp:22", "sudo lsof -iTCP:22", "sudo lsof -i:22", "sudo lsof -i TCP:22"],
           goal=typed(lambda w: w[:1] == ["lsof"] and any(re.search(r":22$", x) for x in w)) ,
           hints=["前の課題と同じ質問ですが、他のユーザーのプロセスも見えるようにする必要があります。",
                  "lsof のネットワーク指定（-i とポート番号）を、管理者権限（sudo）で実行します。",
                  "入力例: sudo lsof -i :22"]),
    lesson("ex-services-51", "ファイルを開いているプロセスを探す",
           "「ファイルを削除できない」「ディスクが空かない」ときは、誰かがそのファイルを開き続けていることがあります。lsof にファイルのパスを渡すと、開いているプロセスが分かります。",
           "ログファイル /var/log/syslog を開いているプロセスを、管理者権限で調べましょう。",
           "sudo lsof /var/log/syslog",
           "rsyslogd が書き込み用（w）に開いていると分かりました。ログを書いているのは rsyslog サービスです。",
           accept=[], goal=typed(lambda w: w[:1] == ["lsof"] and "/var/log/syslog" in w),
           hints=["ファイルの名前を手がかりに、「誰がそれを使っているか」を逆引きしたいのです。",
                  "lsof にファイルのパスを渡します。他のユーザーのものも見るので管理者権限が必要です。",
                  "入力例: sudo lsof /var/log/syslog"]),
    lesson("ex-services-52", "総合：落ちたサービスを復旧して自動起動にする",
           '失敗原因のディスク制限はすでに解消されています。今の稼働状態と、次回のサーバー起動時の状態は別の設定なので、どちらも満たす必要があります。',
           "demo-app を動かし、サーバーを再起動したあとも自動で起動するように設定しましょう。",
           "sudo systemctl enable --now demo-app",
           "復旧と自動起動の両方ができました。最後に status で、Active が running で Loaded が enabled か確かめるのが仕上げです。",
           accept=["sudo systemctl enable --now demo-app.service"],
           services={"demo-app": {"enabled": False}},
           goal=all_of(active("demo-app"), enabled("demo-app")),
           hints=["今すぐ動かすことと、次回以降も自動で動かすことの、両方が必要です。",
                  "systemctl の enable には、起動も同時に行うオプション（--now）があります。管理者権限も必要です。",
                  "入力例: sudo systemctl enable --now demo-app"]),
]
