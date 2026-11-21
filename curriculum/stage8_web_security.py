"""Stage 8: scoped defensive HTTP configuration and authorization verification.

No external targets or exploit endpoints are used. HTTP behavior is real;
configuration and credentials exist only inside this exercise's workspace.
"""
import json
import secrets
import sys
import urllib.error
import urllib.request

from engine.runner import ROOT, free_port, register, wait_port
from engine.security_lab import SECURE_HEADERS, secure_config

S = 8
NOTE = ("\n対象はこの課題が起動した 127.0.0.1 の URL だけです。scope.json に範囲、accounts.json に架空のテスト用資格情報があります。"
        "外部への診断は行いません。lab_config.json は要求ごとに読み直され、再起動は不要です。"
        "これは設定とHTTP応答の検証であり、脆弱性診断や実務能力全体の認定ではありません。\n")
BASE = "http://127.0.0.1:<<port>>"
EDIT_HEADERS = "python3 -c \"import json; p='lab_config.json'; c=json.load(open(p)); c['headers']=json.load(open('header_policy.json')); open(p,'w').write(json.dumps(c))\""
EDIT_AUTH = "python3 -c \"import json; p='lab_config.json'; c=json.load(open(p)); c['require_auth']=True; c['enforce_ownership']=True; open(p,'w').write(json.dumps(c))\""
EDIT_COOKIE = "python3 -c \"import json; p='lab_config.json'; c=json.load(open(p)); c['cookie']={'secure':True,'httponly':True,'samesite':'Strict'}; open(p,'w').write(json.dumps(c))\""
ALICE = "$(python3 -c \"import json; print(json.load(open('accounts.json'))['alice'])\")"
BOB = "$(python3 -c \"import json; print(json.load(open('accounts.json'))['bob'])\")"


def setup(number):
    def prepare(ctx):
        run = secrets.token_hex(10)
        ctx.data.update(run=run, port=free_port())
        fixture = {"run": run, "accounts": {"alice": "alice-" + secrets.token_hex(12), "bob": "bob-" + secrets.token_hex(12)},
                   "documents": {"alice-note": {"owner": "alice", "content": "synthetic alice note " + run},
                                 "bob-note": {"owner": "bob", "content": "synthetic bob note " + run}}}
        ctx.data["fixture"] = fixture
        config = secure_config()
        if number in (3, 6):
            config["headers"] = {}
        if number in (4, 6):
            config["enforce_ownership"] = False
        if number in (5, 6):
            config["cookie"] = {"secure": False, "httponly": False, "samesite": "Lax"}
        ctx.write("lab_config.json", json.dumps(config, indent=2) + "\n")
        ctx.write("fixture.json", json.dumps(fixture, indent=2) + "\n")
        ctx.write("accounts.json", json.dumps(fixture["accounts"], indent=2) + "\n", mode=0o600)
        ctx.write("header_policy.json", json.dumps(SECURE_HEADERS, indent=2) + "\n")
        scope = {"run": run, "target": f"http://127.0.0.1:{ctx.data['port']}",
                 "allowed": ["GET", "HEAD"], "excluded": ["external targets", "load tests", "credential guessing"],
                 "accounts": ["alice", "bob"], "data": "synthetic only"}
        ctx.data["approved_scope"] = scope
        ctx.write("scope.json", json.dumps(scope, indent=2) + "\n")
        ctx.spawn("security-http", argv=[sys.executable, str(ROOT / "engine/security_lab.py"), "--port", str(ctx.data["port"]),
                                       "--config", str(ctx.p("lab_config.json")), "--fixture", str(ctx.p("fixture.json"))])
        if not wait_port(ctx.data["port"], 5):
            raise RuntimeError("local security fixture did not start")
    return prepare


def read_json(ctx, path):
    try:
        value = json.loads(ctx.need_file(path))
    except ValueError:
        ctx.fail(f"{path} は JSON として読めません。")
    ctx.require(isinstance(value, dict), f"{path} は JSON オブジェクトで保存します。")
    return value


def saved_headers(ctx, name, status=200):
    text = ctx.need_file(name)
    lines = text.splitlines()
    ctx.require(lines and len(lines[0].split()) >= 2 and lines[0].split()[1] == str(status), f"{name} の HTTP 状態が {status} ではありません。")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    ctx.require(headers.get("x-lab-run") == ctx.data["run"], f"{name} は今回の演習サーバーの応答ではありません。")
    return headers


def request(ctx, path, user=None):
    headers = {}
    if user:
        headers["Authorization"] = "Bearer " + ctx.data["fixture"]["accounts"][user]
    req = urllib.request.Request(f"http://127.0.0.1:{ctx.data['port']}" + path, headers=headers)
    # Do not inherit external proxy configuration for a loopback exercise.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(req, timeout=2)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError):
        ctx.fail("課題のローカルサーバーへ接続できません。reset で復元できます。")
    with response:
        return response.status, dict(response.headers), json.loads(response.read().decode())


def current_headers(ctx):
    status, headers, body = request(ctx, "/health")
    ctx.require(status == 200 and body.get("run") == ctx.data["run"], "正常性確認が成功していません。")
    for key, value in SECURE_HEADERS.items():
        ctx.require(headers.get(key) == value, f"実際の応答の {key} が合意したポリシーと違います。")


def verify_access(ctx):
    for path, user, expected in (("/documents/alice-note", "alice", 200), ("/documents/bob-note", "bob", 200),
                                 ("/documents/bob-note", "alice", 403), ("/documents/alice-note", "bob", 403),
                                 ("/documents/alice-note", None, 401)):
        status, _, body = request(ctx, path, user)
        ctx.require(status == expected, f"{user or '未認証'} の {path} が {expected} になりません。許可と拒否の両方を確認しましょう。")
        if expected == 200:
            expected_doc = ctx.data["fixture"]["documents"][path.rsplit("/", 1)[1]]
            ctx.require(body.get("content") == expected_doc["content"], "許可された本人の文書を壊さずに保ってください。")


def verify_cookie(ctx, filename="session.headers"):
    headers = saved_headers(ctx, filename)
    value = headers.get("set-cookie", "")
    attrs = {part.strip().lower() for part in value.split(";")[1:]}
    ctx.require({"secure", "httponly", "samesite=strict", "path=/"} <= attrs, "Cookie の Secure・HttpOnly・SameSite=Strict・Path=/ を確認しましょう。")
    status, live, _ = request(ctx, "/session", "alice")
    ctx.require(status == 200, "認証済みの要求が成功しません。")
    attrs = {part.strip().lower() for part in live.get("Set-Cookie", "").split(";")[1:]}
    ctx.require({"secure", "httponly", "samesite=strict"} <= attrs, "保存ファイルだけでなく、現在の応答にも Cookie 属性が必要です。")


def c1(ctx):
    record = read_json(ctx, "authorization.json")
    scope = read_json(ctx, "scope.json")
    ctx.require(scope == ctx.data["approved_scope"], "依頼側の scope.json は変更せず、承認された範囲を記録してください。")
    for key in ("run", "target", "allowed", "excluded", "accounts", "data"):
        ctx.require(record.get(key) == scope[key], f"authorization.json の {key} が依頼範囲と違います。")
    ctx.require(record.get("decision") == "authorized-local-only", "対象・許可操作・除外事項を確認し、decision を authorized-local-only と記録してください。")


def c2(ctx):
    saved_headers(ctx, "health.headers")
    health = read_json(ctx, "health.json")
    catalog = read_json(ctx, "catalog.json")
    ctx.require(health.get("run") == ctx.data["run"] and health.get("status") == "ok", "正常性応答の本文を保存しましょう。")
    ctx.require(catalog.get("run") == ctx.data["run"] and set(catalog.get("paths", [])) == {"/health", "/catalog", "/session", "/documents/alice-note", "/documents/bob-note"}, "公開された一覧の応答を catalog.json に保存しましょう。")


def c3(ctx):
    before = saved_headers(ctx, "before.headers")
    ctx.require(all(key.lower() not in before for key in SECURE_HEADERS), "変更前の不足していた応答ヘッダーを before.headers に残してください。")
    after = saved_headers(ctx, "after.headers")
    for key, value in SECURE_HEADERS.items():
        ctx.require(after.get(key.lower()) == value, f"after.headers に {key} が不足しています。")
    current_headers(ctx)


def c4(ctx):
    for name, code in (("alice-own.headers", 200), ("bob-own.headers", 200), ("alice-other.headers", 403),
                       ("bob-other.headers", 403), ("anonymous.headers", 401)):
        saved_headers(ctx, name, code)
    verify_access(ctx)


def c5(ctx):
    before = saved_headers(ctx, "session-before.headers")
    old = {p.strip().lower() for p in before.get("set-cookie", "").split(";")[1:]}
    ctx.require("secure" not in old and "httponly" not in old, "変更前の Cookie 属性を session-before.headers に残しましょう。")
    verify_cookie(ctx)


def c6(ctx):
    current_headers(ctx)
    verify_access(ctx)
    verify_cookie(ctx)
    report = read_json(ctx, "verification.json")
    ctx.require(report.get("run") == ctx.data["run"] and report.get("target") == f"http://127.0.0.1:{ctx.data['port']}", "報告には今回の run と対象 URL が必要です。")
    ctx.require(report.get("limitations") == ["loopback-http", "synthetic-accounts", "no-browser-or-tls-validation"], "演習の制約も報告してください。")
    findings = report.get("findings", [])
    ctx.require(isinstance(findings, list) and len(findings) == 3, "headers・authorization・cookie の3項目を報告しましょう。")
    by_area = {item["area"]: item for item in findings
               if isinstance(item, dict) and isinstance(item.get("area"), str)}
    for area in ("headers", "authorization", "cookie"):
        item = by_area.get(area, {})
        impact, remediation = item.get("impact"), item.get("remediation")
        ctx.require(item.get("result") == "verified" and isinstance(impact, str) and len(impact.strip()) >= 12
                    and isinstance(remediation, str) and len(remediation.strip()) >= 12,
                    f"{area} の結果・影響・対策を具体的に記録しましょう。")
    c4(ctx)


SCOPE_SOLUTION = "python3 -c \"import json; d=json.load(open('scope.json')); d['decision']='authorized-local-only'; open('authorization.json','w').write(json.dumps(d))\""
INVENTORY = f"curl --noproxy '*' -sS -D health.headers -o health.json {BASE}/health\ncurl --noproxy '*' -sS {BASE}/catalog > catalog.json"
HEADER_SOLUTION = f"curl --noproxy '*' -sS -D before.headers -o /dev/null {BASE}/health\n{EDIT_HEADERS}\ncurl --noproxy '*' -sS -D after.headers -o /dev/null {BASE}/health"
ACCESS_EVIDENCE = "\n".join(
    f"curl --noproxy '*' -sS -D {name}.headers -o /dev/null " + (f'-H "Authorization: Bearer {token}" ' if token else '') + BASE + path
    for name, path, token in (("alice-own", "/documents/alice-note", ALICE), ("bob-own", "/documents/bob-note", BOB),
                              ("alice-other", "/documents/bob-note", ALICE), ("bob-other", "/documents/alice-note", BOB),
                              ("anonymous", "/documents/alice-note", None)))
COOKIE_CAPTURE = f"curl --noproxy '*' -sS -D session.headers -o /dev/null -H \"Authorization: Bearer {ALICE}\" {BASE}/session"
COOKIE_SOLUTION = COOKIE_CAPTURE.replace("session.headers", "session-before.headers") + "\n" + EDIT_COOKIE + "\n" + COOKIE_CAPTURE
REPORT = "python3 -c \"import json; s=json.load(open('scope.json')); d={'run':s['run'],'target':s['target'],'limitations':['loopback-http','synthetic-accounts','no-browser-or-tls-validation'],'findings':[{'area':a,'result':'verified','impact':i,'remediation':r} for a,i,r in [('headers','Missing browser defense policies reduce defense in depth.','Apply and verify the agreed response header policies.'),('authorization','A user must not read another test account document.','Enforce authentication and document ownership on the server.'),('cookie','Missing flags expose sessions to additional browser risks.','Set Secure HttpOnly SameSite attributes; separately validate HTTPS.')]]}; open('verification.json','w').write(json.dumps(d))\""


def add(number, title, story, objectives, thinking, tools, solution, check, wrong, explanation):
    register(id=f"8-{number}", stage=S, title=title, story=story + NOTE, objectives=objectives,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip="許可範囲、観察した応答、対策、再検証、制約をまとめて初めて第三者が確認できる記録になります。",
             setup=setup(number), check=check, solution=solution, wrong=wrong)


add(1, "診断の許可範囲を記録する", "作業を始める前に scope.json を読んで、対象と許可された操作・除外事項を確認します。",
    ["scope.json の全項目を authorization.json に保存する", "decision に authorized-local-only を追加する"],
    "調べられることと、依頼で調べてよいことは同じではありません。対象と除外事項を先に確定します。",
    "cat で範囲を読み、JSON の各値を保ったまま判断を追加します。", SCOPE_SOLUTION, c1,
    ["cp scope.json authorization.json", "echo '{}' > authorization.json",
     "python3 -c \"import json; d=json.load(open('scope.json')); d['target']='https://outside.invalid'; d['allowed'].append('POST'); open('scope.json','w').write(json.dumps(d)); d['decision']='authorized-local-only'; open('authorization.json','w').write(json.dumps(d))\""],
    "対象 URL と操作方法だけでなく、除外事項と利用するアカウントも記録しました。この演習の許可は外部システムには適用されません。")
add(2, "HTTP の応答と公開一覧を記録する", "依頼範囲内で正常性確認と、公開されたエンドポイントの一覧を取得してください。",
    ["/health のヘッダーを health.headers、本文を health.json に保存する", "/catalog の本文を catalog.json に保存する"],
    "まず通常の要求が正常に返るかを基準として残します。", "curl の -D はヘッダー、-o は本文の保存先です。--noproxy '*' でプロキシを経由しません。",
    INVENTORY, c2, [f"curl --noproxy '*' -sS {BASE}/health > health.json", "echo '{}' > catalog.json"],
    "状態コード、ヘッダー、本文、公開されたパスを区別して記録しました。この公開一覧だけで全資産を発見したとは判断できません。")
add(3, "合意したレスポンスヘッダーを適用する", "応答にセキュリティヘッダーがありません。変更前の応答を保存し、header_policy.json のポリシーを適用して再検証します。",
    ["変更前を before.headers、変更後を after.headers に保存する", "lab_config.json の headers を header_policy.json と同じ値にする", "現在の HTTP 応答にも設定が反映されていること"],
    "設定ファイルを書いただけでは完了ではありません。実際の応答を比較します。", "curl -D と JSON の編集を使います。ポリシーには nosniff・CSP・Referrer-Policy があります。",
    HEADER_SOLUTION, c3, [EDIT_HEADERS, f"curl --noproxy '*' -sS -D before.headers -o /dev/null {BASE}/health"],
    "ヘッダーは防御の一部です。CSP はアプリの資源利用と整合させます。このAPI用ポリシーを一般のWebサイトへそのままコピーする課題ではありません。")
add(4, "テストアカウントの認可を回帰検証する", "Alice と Bob が互いの文書を読める設定になっています。所有者の制限を有効にし、許可する要求と拒否する要求を両方記録してください。",
    ["require_auth と enforce_ownership を true にする", "本人の文書は200、別ユーザーの文書は403、未認証は401にする", "alice-own・bob-own・alice-other・bob-other・anonymous の .headers を保存する"],
    "ログインできることと、その文書を読む権限があることは別の検査です。全拒否では正常な利用も壊れます。", "accounts.json の架空トークンを Authorization: Bearer で渡し、通常の文書要求を検証します。",
    EDIT_AUTH + "\n" + ACCESS_EVIDENCE, c4, [ACCESS_EVIDENCE, EDIT_AUTH],
    "サーバー側で本人と所有者を照合し、本人の正当な利用を保ったまま他人の利用を拒否しました。UIで隠すだけでは認可になりません。")
add(5, "Cookie 属性を変更前後で確認する", "セッション応答に返す Cookie の属性を検証します。これは属性の演習であり、本番の認証・TLS・ブラウザー動作は実装していません。",
    ["変更前を session-before.headers、変更後を session.headers に保存する", "Secure・HttpOnly・SameSite=Strict・Path=/ を実際の応答で確認する"],
    "属性の意図を理解し、設定と応答が一致するか確認します。", "cookie の secure と httponly は true、samesite は Strict にします。認証済みで /session を要求します。",
    COOKIE_SOLUTION, c5, [EDIT_COOKIE, COOKIE_CAPTURE],
    "Secure はHTTPSでの送信、HttpOnlyはスクリプトからのアクセス制限、SameSiteはクロスサイト送信の制御に関係します。ここではローカルHTTP応答の属性だけを検証します。")
add(6, "修正・回帰確認・制約を報告する", "ヘッダー・文書の認可・Cookie 属性をまとめて修正し、正常利用と拒否の結果、および確認していない範囲を報告してください。",
    ["ヘッダー・認可・Cookie を修正し、5種類の文書応答と session.headers を保存する", "verification.json に run・target・limitations・findings を記録する", "findings は headers・authorization・cookie の3件。各件に result=verified、具体的な impact と remediation を記す", "limitations は loopback-http、synthetic-accounts、no-browser-or-tls-validation の3項目"],
    "対策を設定したこと、実際に動作したこと、調べていないことを分けて報告します。", "既出の設定変更と HTTP 検証を組み合わせます。報告の run と target は scope.json から読みます。",
    EDIT_HEADERS + "\n" + EDIT_AUTH + "\n" + EDIT_COOKIE + "\n" + ACCESS_EVIDENCE + "\n" + COOKIE_CAPTURE + "\n" + REPORT,
    c6, [REPORT, EDIT_HEADERS + "\n" + EDIT_AUTH + "\n" + EDIT_COOKIE],
    "再現可能な応答と修正後の回帰結果、影響、対策、制約を残しました。これは防御設定と認可テストの基礎であり、専門職としての独立した診断を保証する認定ではありません。")
