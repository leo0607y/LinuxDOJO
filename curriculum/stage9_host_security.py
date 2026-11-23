"""Stage 9: authorized host-security assessment using workspace fixtures only."""
import hashlib
import json
import random
import secrets
import stat
import tarfile

from engine.runner import register
from engine.security_checks import (archive_texts, confined_file, read_json,
                                    service_values, sha256, ssh_values)

S = 9
NOTE = ("対象はこの課題の作業フォルダだけです。sysroot/ は架空のシステム設定で、"
        "本物の /etc やサービスには変更を加えません。sudo は不要です。"
        "設定の判定は教材で指定した書式の範囲です。実機への適用前にはネイティブの検証と復旧手段が必要です。")


def base(ctx):
    ctx.write("LAB_SCOPE.txt", NOTE + "\n")


def same(ctx, path, expected):
    ctx.require(confined_file(ctx, path).read_text() == expected,
                f"{path} の必要な内容を失っています。削除やダミーへの置き換えでは修正になりません。")


def report(ctx, expected):
    data = read_json(ctx, "findings.json")
    ctx.require(isinstance(data, dict), "findings.json は JSON オブジェクトで提出してください。")
    for key, value in expected.items():
        ctx.require(data.get(key) == value, f"findings.json の {key} を実際の対象・結果に合わせて記録してください。")


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, hints):
    return register(id=f"9-{n}", stage=S, title=title, story=story + "\n\n" + NOTE,
                    objectives=objectives, hints=hints, answer=solution, explanation=explanation,
                    tip="現状と影響を記録し、最小限の変更後に正常な利用も確認します。テストの実行範囲と、未検証の範囲を報告へ残しましょう。",
                    setup=setup, check=check, solution=solution, wrong=wrong)


def s91(ctx):
    base(ctx)
    case = "ASSESS-" + secrets.token_hex(3)
    asset = "dojo-" + str(random.randint(100, 999))
    ctx.data.update(case=case, asset=asset)
    ctx.write("engagement.json", json.dumps({"case": case, "authorized_by": "Dojo Training Owner",
        "allowed_assets": [asset], "forbidden_assets": ["production.example.invalid"],
        "allowed_actions": ["read-fixtures", "change-fixtures", "verify-fixtures"],
        "stop_conditions": ["unexpected-real-data", "target-outside-scope"],
        "data_handling": "redact-secrets"}, indent=2))
    ctx.write("submission-schema.txt", "acceptance.json: case, assets, actions, stop_conditions, data_handling を engagement.json に従って記録。\n"
              "候補に production.example.invalid があっても追加しない。許可書を変更しない。\n")
    ctx.data["authorization_hash"] = sha256(ctx.p("engagement.json"))


def c91(ctx):
    ctx.require(sha256(confined_file(ctx, "engagement.json")) == ctx.data["authorization_hash"], "許可書そのものは変更しないでください。")
    actual = read_json(ctx, "acceptance.json")
    expected = {"case": ctx.data["case"], "assets": [ctx.data["asset"]],
                "actions": ["read-fixtures", "change-fixtures", "verify-fixtures"],
                "stop_conditions": ["unexpected-real-data", "target-outside-scope"], "data_handling": "redact-secrets"}
    ctx.require(actual == expected, "許可された対象・操作・停止条件・秘匿方法をすべて正しく記録してください。範囲を広げてはいけません。")


S91 = """cat engagement.json
python3 - <<'PY'
import json
p=json.load(open('engagement.json'))
json.dump(dict(case=p['case'],assets=p['allowed_assets'],actions=p['allowed_actions'],stop_conditions=p['stop_conditions'],data_handling=p['data_handling']),open('acceptance.json','w'),indent=2)
PY"""
mission(1, "診断の許可範囲と停止条件", "調査開始前に許可書を読み、実施できる対象と行動を確定します。",
        ["許可書は変更せず読む", "提出形式の資料に従って acceptance.json を作成し、許可のない対象を含めない"],
        s91, c91, S91, ["echo '{}' > acceptance.json", S91 + "\npython3 - <<'PY'\nimport json\np=json.load(open('acceptance.json'));p['assets'].append('production.example.invalid');json.dump(p,open('acceptance.json','w'))\nPY"],
        "最初の成果物は許可範囲です。対象の所有者、許可された操作、停止条件とデータの扱いを明記し、候補一覧と許可一覧を区別します。",
        ["調査の前に、許可されたことと停止すべき条件を確定します。", "cat で許可書を読み、JSON の必要な項目だけを対応する名前で保存します。", S91])


def s92(ctx):
    base(ctx)
    name = "app-" + secrets.token_hex(2)
    secret = "TRAINING_ONLY_" + secrets.token_hex(8)
    ctx.data.update(app=name, secret=secret)
    ctx.write(f"deploy/{name}/private/token.env", "API_TOKEN=" + secret + "\n", mode=0o666)
    ctx.p(f"deploy/{name}/private").chmod(0o777)
    ctx.write(f"deploy/{name}/bin/serve.sh", "#!/bin/sh\nprintf '%s\\n' ready\n", mode=0o777)
    ctx.write(f"deploy/{name}/public/index.html", "<h1>Dojo</h1>\n", mode=0o644)
    ctx.write("report-schema.txt", "findings.json: secret_path（相対パス）, original_mode（666）, cause（world-readable-secret）, remediation（owner-only）\n")


def c92(ctx):
    root = f"deploy/{ctx.data['app']}"
    same(ctx, root + "/private/token.env", "API_TOKEN=" + ctx.data["secret"] + "\n")
    same(ctx, root + "/public/index.html", "<h1>Dojo</h1>\n")
    same(ctx, root + "/bin/serve.sh", "#!/bin/sh\nprintf '%s\\n' ready\n")
    for name, mode in (("private", 0o700), ("private/token.env", 0o600), ("bin/serve.sh", 0o750), ("public/index.html", 0o644)):
        path = ctx.p(root + "/" + name)
        ctx.require(not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == mode, f"{name} の権限が要件と違います。")
    report(ctx, {"secret_path": root + "/private/token.env", "original_mode": "666", "cause": "world-readable-secret", "remediation": "owner-only"})
    ctx.require(ctx.data["secret"] not in ctx.need_file("findings.json"), "報告書にトークンの生値を残さず、パスと問題を報告してください。")


S92 = """find deploy -printf '%m %p\\n'
chmod 700 deploy/<<app>>/private
chmod 600 deploy/<<app>>/private/token.env
chmod 750 deploy/<<app>>/bin/serve.sh
python3 - <<'PY'
import json
from pathlib import Path
p=next(Path('deploy').glob('*/private/token.env'))
json.dump(dict(secret_path=str(p),original_mode='666',cause='world-readable-secret',remediation='owner-only'),open('findings.json','w'))
PY"""
mission(2, "秘密情報と実行ファイルの権限監査", "デプロイ済みファイルに公開範囲の広すぎる秘密情報と書き換え可能なスクリプトが混在しています。",
        ["秘密情報のディレクトリは700、秘密の環境ファイルは600、公開用スクリプトは750へ修正", "公開ページの644と全ファイル内容を維持", "報告形式の資料に従って findings.json を作り、秘密の値は記録しない"],
        s92, c92, S92, ["chmod -R 600 deploy", "find deploy -name token.env -delete"],
        "読み取り可能な秘密と、他者が書き換えられる実行ファイルは別の問題です。ディレクトリの探索権限も含めて必要な範囲を設定し、公開ファイルの利用を壊さないことを確認します。",
        ["一括で権限を狭めると公開ページや実行も壊れます。種類ごとに考えます。", "find の権限表示と chmod を使い、秘密の値ではなく場所と原因を JSON へ記録します。", S92])


def s93(ctx):
    base(ctx)
    port = random.randint(2200, 2299)
    ctx.data["ssh_port"] = port
    ctx.write("sysroot/etc/ssh/sshd_config", f"# Dojo fixture: global directives only\nPort {port}\nPermitRootLogin yes\nPasswordAuthentication yes\nKbdInteractiveAuthentication yes\nAuthenticationMethods any\nPubkeyAuthentication yes\nAllowUsers learner deploy\n", mode=0o644)
    ctx.write("requirements.txt", "既存 Port を維持。root ログインとパスワード認証・keyboard-interactive を禁止し、AuthenticationMethods は publickey のみ。公開鍵認証を維持。許可ユーザーは learner のみ。\n"
              "findings.json: control=ssh-authentication, port=元の番号（整数）, root_login=no, passwords=no, allowed_users=[learner]\n")


def c93(ctx):
    path = confined_file(ctx, "sysroot/etc/ssh/sshd_config")
    try:
        values = ssh_values(path.read_text())
    except ValueError as error:
        ctx.fail(str(error))
    expected = {"port": str(ctx.data["ssh_port"]), "permitrootlogin": "no", "passwordauthentication": "no", "kbdinteractiveauthentication": "no", "authenticationmethods": "publickey", "pubkeyauthentication": "yes", "allowusers": "learner"}
    ctx.require(all(values.get(k, "").lower() == v for k, v in expected.items()), "SSH の実効的な全体設定が要件と違います。先に書かれた値、Port、許可ユーザーも確認してください。")
    ctx.require(set(values) == set(expected), "演習外の設定を追加せず、元の全体設定を修正してください。")
    report(ctx, {"control": "ssh-authentication", "port": ctx.data["ssh_port"], "root_login": "no", "passwords": "no", "allowed_users": ["learner"]})


S93 = """cat sysroot/etc/ssh/sshd_config
python3 - <<'PY'
from pathlib import Path
import json
p=Path('sysroot/etc/ssh/sshd_config')
s=p.read_text().replace('PermitRootLogin yes','PermitRootLogin no').replace('PasswordAuthentication yes','PasswordAuthentication no').replace('KbdInteractiveAuthentication yes','KbdInteractiveAuthentication no').replace('AuthenticationMethods any','AuthenticationMethods publickey').replace('AllowUsers learner deploy','AllowUsers learner')
p.write_text(s)
port=int(next(x.split()[1] for x in s.splitlines() if x.startswith('Port ')))
json.dump(dict(control='ssh-authentication',port=port,root_login='no',passwords='no',allowed_users=['learner']),open('findings.json','w'))
PY"""
mission(3, "SSH 認証を壊さずに絞る", "SSH の設定控えを、公開鍵認証を維持したまま強化します。本物の SSH サービスは操作しません。",
        ["要件書に沿って作業フォルダ内のSSH設定控えを修正", "findings.json に元の Port と変更後の認証制限を記録", "Match/Include などの設定は追加しない"],
        s93, c93, S93, ["printf '\\nPermitRootLogin no\\nPasswordAuthentication no\\n' >> sysroot/etc/ssh/sshd_config", "sed -i 's/PubkeyAuthentication yes/PubkeyAuthentication no/' sysroot/etc/ssh/sshd_config"],
        "SSH 設定は同じ全体項目を末尾へ追記するだけでは先の値が優先される場合があります。PasswordAuthentication の禁止だけで keyboard-interactive も禁止されたとは限らないため、認証経路を明示します。一次資料: https://man.openbsd.org/sshd_config.5 。この課題は小さな全体設定だけを扱います。実運用では Match/Include を含む実効設定を調べ、鍵による別接続と復旧経路を確保してからネイティブ検証します。",
        ["入口を閉じる前に、残す認証経路と接続番号を確認します。", "既存行を編集します。項目を末尾へ足すだけでは、先にある値が残ります。", S93])


def s94(ctx):
    base(ctx)
    account = "release" + str(random.randint(10, 99))
    ctx.data["release_user"] = account
    ctx.write("sysroot/etc/sudoers.d/dojo-release", f"# bounded training fixture; not installed\n{account} ALL=(root) NOPASSWD: ALL\n", mode=0o644)
    ctx.write("requirements.txt", f"{account} に許可するのは root として /usr/bin/systemctl restart dojo-web.service を実行する操作だけ。NOPASSWD は可。\n"
              "sudoers 控えの権限は440。ALL のコマンド、ワイルドカード、シェル、複数コマンドは不要。\n"
              "findings.json: account=対象名, risk=unrestricted-root-command, allowed_command=/usr/bin/systemctl restart dojo-web.service\n")


def c94(ctx):
    path = confined_file(ctx, "sysroot/etc/sudoers.d/dojo-release")
    lines = [x.strip() for x in path.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
    expected = f"{ctx.data['release_user']} ALL=(root) NOPASSWD: /usr/bin/systemctl restart dojo-web.service"
    ctx.require(lines == [expected], "この演習では1人に1つの完全指定コマンドだけを許可します。ALL・*・追加コマンドを残さないでください。")
    ctx.require(stat.S_IMODE(path.stat().st_mode) == 0o440, "sudoers 控えは440にしてください。")
    report(ctx, {"account": ctx.data["release_user"], "risk": "unrestricted-root-command", "allowed_command": "/usr/bin/systemctl restart dojo-web.service"})


S94 = """cat sysroot/etc/sudoers.d/dojo-release
python3 - <<'PY'
from pathlib import Path
import json
p=Path('sysroot/etc/sudoers.d/dojo-release')
user=next(x.split()[0] for x in p.read_text().splitlines() if x and not x.startswith('#'))
command='/usr/bin/systemctl restart dojo-web.service'
p.write_text(user+' ALL=(root) NOPASSWD: '+command+'\\n')
p.chmod(0o440)
json.dump(dict(account=user,risk='unrestricted-root-command',allowed_command=command),open('findings.json','w'))
PY"""
mission(4, "sudo の権限を1つの操作へ限定", "リリース担当には Web サービスの再起動だけが必要なのに、すべての root コマンドが許可されています。",
        ["要件書の1コマンドだけを許可する sudoers 控えへ変更", "控えの440と findings.json の正しい対象名を確認", "本物の sudoers を編集・適用しない"],
        s94, c94, S94, ["chmod 440 sysroot/etc/sudoers.d/dojo-release", "sed -i 's@NOPASSWD: ALL@NOPASSWD: /usr/bin/systemctl *@' sysroot/etc/sudoers.d/dojo-release"],
        "権限の最小化は、利用者だけでなく実行するコマンドと引数も制約します。この教材は指定した単一行の表記を判定します。本番ではエディタの設定を含めた管理手順と visudo の構文検証が別途必要です。",
        ["ファイルの読み取り権限と、sudo が許可する操作の範囲は別の問題です。", "許可行のコマンド部分を絶対パスと完全な引数へ置き換え、chmod で控えを保護します。", S94])


def s95(ctx):
    base(ctx)
    ctx.write("sysroot/etc/systemd/system/dojo-web.service", "[Unit]\nDescription=Dojo Web\n[Service]\nUser=root\nExecStart=/opt/dojo-app/bin/server\nNoNewPrivileges=false\nPrivateTmp=false\nProtectSystem=false\nReadWritePaths=/\nAmbientCapabilities=CAP_SYS_ADMIN\n[Install]\nWantedBy=multi-user.target\n")
    ctx.write("requirements.txt", "Service の User=dojo-app、ExecStart 維持、NoNewPrivileges=true、PrivateTmp=true、ProtectSystem=strict、ReadWritePaths=/var/lib/dojo-app、AmbientCapabilities は空へ。\n"
              "findings.json: service=dojo-web.service, risk=overprivileged-service, run_as=dojo-app, writable_path=/var/lib/dojo-app\n")


def c95(ctx):
    try:
        values = service_values(confined_file(ctx, "sysroot/etc/systemd/system/dojo-web.service").read_text())
    except ValueError as error:
        ctx.fail(str(error))
    expected = {"User": "dojo-app", "ExecStart": "/opt/dojo-app/bin/server", "NoNewPrivileges": "true", "PrivateTmp": "true", "ProtectSystem": "strict", "ReadWritePaths": "/var/lib/dojo-app", "AmbientCapabilities": ""}
    ctx.require(values == expected, "[Service] 内の実行者・保護設定・書込先・capability が要件と違います。サービスの実行先は保ってください。")
    report(ctx, {"service": "dojo-web.service", "risk": "overprivileged-service", "run_as": "dojo-app", "writable_path": "/var/lib/dojo-app"})


S95 = """cat sysroot/etc/systemd/system/dojo-web.service
python3 - <<'PY'
from pathlib import Path
import json
p=Path('sysroot/etc/systemd/system/dojo-web.service')
s=p.read_text()
for old,new in [('User=root','User=dojo-app'),('NoNewPrivileges=false','NoNewPrivileges=true'),('PrivateTmp=false','PrivateTmp=true'),('ProtectSystem=false','ProtectSystem=strict'),('ReadWritePaths=/\\n','ReadWritePaths=/var/lib/dojo-app\\n'),('AmbientCapabilities=CAP_SYS_ADMIN','AmbientCapabilities=')]:
    s=s.replace(old,new)
p.write_text(s)
json.dump(dict(service='dojo-web.service',risk='overprivileged-service',run_as='dojo-app',writable_path='/var/lib/dojo-app'),open('findings.json','w'))
PY"""
mission(5, "サービスの最小権限と書き込み範囲", "Web サービスが root と広い capability で起動する設定になっています。機能の起動先を保ち、設定控えを強化します。",
        ["要件書に従って unit の [Service] を修正", "ExecStart を保持し、機能を削除して問題を隠さない", "findings.json にリスクと必要な書込先を記録"],
        s95, c95, S95, ["sed -i 's/User=root/User=dojo-app/' sysroot/etc/systemd/system/dojo-web.service", "sed -i 's@ExecStart=.*@ExecStart=/bin/true@' sysroot/etc/systemd/system/dojo-web.service"],
        "実行するアカウントを変えるだけでなく、権限の追加、ファイル書込先、実行環境の分離も調べます。この課題は設定控えの評価です。対象プログラムと systemd の版による対応、実際の起動・更新・復旧は別途検証します。",
        ["不要な権限を減らしながら、サービスが必要とする実行先と保存先を残します。", "[Service] の User と保護設定を編集します。別セクションへ追記しても Service の設定にはなりません。", S95])


def s96(ctx):
    base(ctx)
    marker = secrets.token_hex(4)
    ctx.data["release_marker"] = marker
    ctx.write("release/public/index.html", "<h1>Dojo release " + marker + "</h1>\n")
    ctx.write("release/app/config.example", "API_TOKEN=REPLACE_ME\n")
    ctx.write("release/.env", "API_TOKEN=TRAINING_ONLY_" + secrets.token_hex(8) + "\n")
    ctx.write("release/.ssh/id_ed25519", "TRAINING_ONLY_FAKE_PRIVATE_KEY\n")
    ctx.write("requirements.txt", "bundle.tar.gz へ公開用のHTMLと設定見本だけを相対パスで格納。元の全ファイルは保持。\n"
              "findings.jsonには risk='secret-in-release-artifact', excluded=[秘密を含むファイルの相対パス], verified=true を記録。全ファイルを調べ、作成したアーカイブの中身を確認してから記録する。\n")
    ctx.data["release_hashes"] = {str(p.relative_to(ctx.work)): sha256(p) for p in ctx.p("release").rglob("*") if p.is_file()}


def c96(ctx):
    for name, digest in ctx.data["release_hashes"].items():
        ctx.require(sha256(confined_file(ctx, name)) == digest, "元の配布元を削除・変更せず、格納対象を選んでください。")
    path = confined_file(ctx, "bundle.tar.gz")
    ctx.require(path.read_bytes()[:2] == b"\x1f\x8b", "gzip 圧縮した tar を作成してください。")
    try:
        contents = archive_texts(path)
    except (OSError, ValueError, tarfile.TarError) as error:
        ctx.fail("アーカイブを安全に検査できません: " + str(error))
    expected = {"public/index.html": "<h1>Dojo release " + ctx.data["release_marker"] + "</h1>\n", "app/config.example": "API_TOKEN=REPLACE_ME\n"}
    ctx.require(contents == expected, "配布物は指定した2ファイルだけを内容を維持して格納します。秘密情報や余分なパスを含めないでください。")
    report(ctx, {"risk": "secret-in-release-artifact", "excluded": [".env", ".ssh/id_ed25519"], "verified": True})


S96 = """find release -type f
 tar -czf bundle.tar.gz -C release public/index.html app/config.example
 tar -tzf bundle.tar.gz
python3 - <<'PY'
import json
json.dump(dict(risk='secret-in-release-artifact',excluded=['.env','.ssh/id_ed25519'],verified=True),open('findings.json','w'))
PY"""
mission(6, "配布アーカイブから秘密を除外", "配布元には公開ページと設定見本のほか、環境ファイルや秘密鍵の控えもあります。公開してよいファイルだけを梱包します。",
        ["元の配布元を全て保ち、必要な2ファイルだけを bundle.tar.gz に格納", "格納した内容を確認し、findings.json に除外した秘密ファイルを記録", "tar のファイル内容まで検証されるので空の偽ファイルでは達成しない"],
        s96, c96, S96, ["tar -czf bundle.tar.gz -C release .", "rm release/.env release/.ssh/id_ed25519\ntar -czf bundle.tar.gz -C release public/index.html app/config.example"],
        "隠しファイルも含めた一括梱包は、環境ファイルや秘密鍵の流出につながります。公開用ディレクトリや明示的な許可リストを使い、作ったアーカイブを検査します。元データを削除することは除外設定の代わりになりません。",
        ["配布元の削除ではなく、配布物へ入れる対象を限定します。", "tar の -C で基点を選び、許可された相対パスを指定して圧縮し、-t で中身を読みます。", S96])


def s97(ctx):
    base(ctx)
    value = "version=" + secrets.token_hex(4) + "\nport=8080\n"
    ctx.data["backup_text"] = value
    ctx.write("live/app.conf", "version=broken\nport=0\n")
    ctx.write("backup/app.conf", value)
    digest = sha256(ctx.p("backup/app.conf"))
    ctx.data["expected_digest"] = digest
    ctx.write("approved.sha256", digest + "  backup/app.conf\n")
    ctx.data["manifest_hash"] = sha256(ctx.p("approved.sha256"))
    ctx.write("requirements.txt", "approved.sha256 は承認済みの期待値です。変更せず照合してから backup/app.conf を live/app.conf へ復元。\n"
              "復元前の live は evidence/before.conf に残す。restore.sha256 で復元後の live を再照合できるようにする。\n"
              "findings.json: integrity=sha256-matched, restored=live/app.conf, preserved=evidence/before.conf\n")


def c97(ctx):
    ctx.require(sha256(confined_file(ctx, "approved.sha256")) == ctx.data["manifest_hash"], "承認済みの期待値を書き換えてはいけません。")
    same(ctx, "backup/app.conf", ctx.data["backup_text"])
    same(ctx, "evidence/before.conf", "version=broken\nport=0\n")
    same(ctx, "live/app.conf", ctx.data["backup_text"])
    checks = ctx.need_file("restore.sha256").splitlines()
    ctx.require(checks == [ctx.data["expected_digest"] + "  live/app.conf"], "restore.sha256 は復元した live/app.conf と承認済みの digest を対応させてください。")
    report(ctx, {"integrity": "sha256-matched", "restored": "live/app.conf", "preserved": "evidence/before.conf"})


S97 = """sha256sum -c approved.sha256
mkdir -p evidence
cp live/app.conf evidence/before.conf
cp backup/app.conf live/app.conf
sha256sum live/app.conf > restore.sha256
sha256sum -c restore.sha256
python3 - <<'PY'
import json
json.dump(dict(integrity='sha256-matched',restored='live/app.conf',preserved='evidence/before.conf'),open('findings.json','w'))
PY"""
mission(7, "期待値と照合してから復元", "バックアップがあるだけでは安全に戻せません。承認済みのハッシュを使って照合し、変更前も残して復元します。",
        ["承認済みハッシュの原本は変更せず、バックアップの設定ファイルを照合", "変更前を evidence/before.conf に退避し、稼働側の設定ファイルを復元", "restore.sha256 と findings.json を作り、復元した内容も照合"],
        s97, c97, S97, ["cp backup/app.conf live/app.conf", "mkdir -p evidence\ncp live/app.conf evidence/before.conf\necho 'version=guessed' > live/app.conf\nsha256sum live/app.conf > restore.sha256"],
        "ハッシュは期待値が信頼できるときに整合性確認へ使えます。復元後だけ自分でハッシュを作っても、正しいバックアップかは分かりません。承認済みの期待値を保ち、変更前のデータと復元後の両方を記録します。",
        ["比較対象の期待値と、比較したいデータを同時に書き換えてはいけません。", "sha256sum -c で既存の期待値と照合し、cp で変更前を残してから復元します。", S97])
