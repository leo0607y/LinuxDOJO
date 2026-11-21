"""Stage 10: workspace-only incident triage, evidence and professional reporting.

All accounts, sessions, addresses and approvals are invented training data. Nothing
connects to a target or changes operating-system authentication settings.
"""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone

from engine.runner import register

S = 10
SOURCE_FILES = ("case.json", "logs/auth.csv", "logs/access.csv")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rows(ctx, name):
    return list(csv.DictReader(io.StringIO(ctx.need_file(name))))


def obj(ctx, name):
    try:
        value = json.loads(ctx.need_file(name))
    except (ValueError, TypeError):
        ctx.fail(f"{name} は有効な JSON で保存しましょう。")
    ctx.require(isinstance(value, dict), f"{name} の最上位はオブジェクトです。")
    return value


def base(ctx):
    suffix = ctx.rand(5).lower()
    account, other = "analyst-" + suffix, "service-" + suffix
    asset, second = "portal-" + suffix, "archive-" + suffix
    session = "session-" + suffix
    ip = "198.51.100." + str(20 + int(suffix.encode().hex()[-2:], 16) % 200)
    case = {"case_id": "IR-" + suffix.upper(), "authorization": "training-approval-" + suffix,
            "scope": [asset, second], "window_start": "2026-11-20T23:00:00Z",
            "window_end": "2026-11-20T23:10:00Z", "source_timezone": "timestamps include explicit offsets",
            "authorized_changes": ["revoke the flagged session", "enable auth logging", "limit session age to 30 minutes"],
            "limits": "synthetic workspace records only; no external requests or attribution"}
    ctx.write("case.json", json.dumps(case, indent=2) + "\n", mode=0o600)
    auth = ("event_id,timestamp,account,source_ip,result,session\n"
            f"A01,2026-11-21T08:00:00+09:00,{account},{ip},failed,-\n"
            f"A02,2026-11-21T08:01:00+09:00,{account},{ip},failed,-\n"
            f"A03,2026-11-21T08:02:00+09:00,{account},{ip},success,{session}\n"
            f"A04,2026-11-20T23:02:30+00:00,{other},192.0.2.10,success,service-session\n"
            f"A05,2026-11-21T08:03:00+09:00,guest-{suffix},{ip},failed,-\n")
    access = ("event_id,timestamp,account,session,asset,status,action\n"
              f"W01,2026-11-20T23:02:15+00:00,{account},{session},{asset},200,read-report\n"
              f"W02,2026-11-20T23:02:20+00:00,{account},{session},{second},403,read-backup\n"
              f"W03,2026-11-20T23:02:40+00:00,{other},service-session,{second},200,scheduled-check\n")
    ctx.write("logs/auth.csv", auth, mode=0o600)
    ctx.write("logs/access.csv", access, mode=0o600)
    ctx.data.update(account=account, other=other, asset=asset, second=second, session=session, ip=ip,
                    originals={name: digest(ctx.p(name).read_bytes()) for name in SOURCE_FILES})
    ctx.write("README.txt", "このケースは架空データだけの演習です。case.json が許可範囲・期間・変更可能項目です。\n"
              "ログは追記・削除せず原本を保持します。認証成功という観測と、不正アクセスと断定する判断は分けてください。\n"
              "調査結果は指定の JSON または CSV で保存します。引用するイベント ID を必ず残します。\n")


def originals(ctx):
    for name, expected in ctx.data["originals"].items():
        ctx.require(ctx.isfile(name) and not ctx.p(name).is_symlink() and digest(ctx.p(name).read_bytes()) == expected,
                    f"原本 {name} が変わっています。reset で復元し、コピーを使って調査しましょう。")


def s1(ctx):
    base(ctx)
    ctx.write("collection-format.json", '{"case_id":"case.json の値","authorization":"case.json の値","collector":"自分の識別名","collected_at":"UTC の ISO 8601 時刻"}\n')


def c1(ctx):
    originals(ctx)
    for name in SOURCE_FILES:
        target = "evidence/" + name
        ctx.require(ctx.isfile(target) and not ctx.p(target).is_symlink(), f"{target} に原本をコピーしましょう。")
        ctx.require(digest(ctx.p(target).read_bytes()) == ctx.data["originals"][name], f"{target} は原本と一致しません。")
        ctx.require(ctx.mode(target) & 0o077 == 0, f"{target} を他の利用者から読めない権限にしましょう。")
    manifest = {}
    for line in ctx.need_file("evidence/SHA256SUMS").splitlines():
        parts = line.split(None, 1)
        ctx.require(len(parts) == 2, "SHA256SUMS の各行にはハッシュとパスを記録します。")
        manifest[parts[1].lstrip("*")] = parts[0]
    expected = {"evidence/" + name: value for name, value in ctx.data["originals"].items()}
    ctx.require(manifest == expected, "SHA256SUMS に3つの証拠ファイルの正しい SHA-256 とパスを記録しましょう。")
    case, note = obj(ctx, "case.json"), obj(ctx, "collection.json")
    ctx.require(note.get("case_id") == case["case_id"] and note.get("authorization") == case["authorization"], "取得記録にケース ID と許可番号を記録しましょう。")
    ctx.require(isinstance(note.get("collector"), str) and len(note["collector"].strip()) >= 3, "取得担当者の識別名を記録しましょう。")
    try:
        when = datetime.fromisoformat(note.get("collected_at", "").replace("Z", "+00:00"))
        ctx.require(when.utcoffset() == timezone.utc.utcoffset(when), "取得時刻を UTC で記録しましょう。")
    except (ValueError, TypeError):
        ctx.fail("collected_at に UTC の ISO 8601 時刻を記録しましょう。")


SOL1 = '''mkdir -p evidence/logs
cp case.json evidence/case.json
cp logs/auth.csv logs/access.csv evidence/logs/
chmod 600 evidence/case.json evidence/logs/*.csv
sha256sum evidence/case.json evidence/logs/auth.csv evidence/logs/access.csv > evidence/SHA256SUMS
python3 - <<'PYCODE'
import json
from datetime import datetime, timezone
case=json.load(open('case.json'))
json.dump(dict(case_id=case['case_id'],authorization=case['authorization'],collector='trainee',collected_at=datetime.now(timezone.utc).isoformat()),open('collection.json','w'))
PYCODE'''


def timeline(ctx):
    result = []
    for name in ("logs/auth.csv", "logs/access.csv"):
        for row in rows(ctx, name):
            stamp = datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            result.append({"utc": stamp, "event_id": row["event_id"], "source": name, "account": row["account"]})
    return sorted(result, key=lambda r: (r["utc"], r["event_id"]))


def c2(ctx):
    originals(ctx)
    actual = rows(ctx, "timeline.csv")
    ctx.require(actual == timeline(ctx), "timeline.csv は全8イベントを UTC へ変換し、時刻・イベント ID 順に並べましょう。原本への参照も必要です。")


SOL2 = '''python3 - <<'PYCODE'
import csv
from datetime import datetime, timezone
out=[]
for name in ('logs/auth.csv','logs/access.csv'):
    for row in csv.DictReader(open(name)):
        stamp=datetime.fromisoformat(row['timestamp']).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        out.append(dict(utc=stamp,event_id=row['event_id'],source=name,account=row['account']))
with open('timeline.csv','w') as f:
    w=csv.DictWriter(f,fieldnames=['utc','event_id','source','account']); w.writeheader()
    w.writerows(sorted(out,key=lambda r:(r['utc'],r['event_id'])))
PYCODE'''


def c3(ctx):
    originals(ctx)
    finding = obj(ctx, "triage.json")
    ctx.require(finding.get("account") == ctx.data["account"] and finding.get("source_ip") == ctx.data["ip"], "失敗後に同じ組み合わせで認証成功したアカウントと送信元を調べましょう。")
    ctx.require(finding.get("failed_events") == ["A01", "A02"] and finding.get("successful_event") == "A03", "認証失敗2件と、それに続く認証成功のイベント ID を分けて記録しましょう。")
    ctx.require(finding.get("observation") == "authentication_success_after_failures", "観測は authentication_success_after_failures と記録します。")
    ctx.require(finding.get("compromise_confirmed") is False and finding.get("attribution") == "not_determined", "このログだけでは不正利用や行為者を断定できません。未確定の点を正しく表しましょう。")


SOL3 = '''python3 - <<'PYCODE'
import csv,json
rows=list(csv.DictReader(open('logs/auth.csv')))
success=next(r for r in rows if r['event_id']=='A03')
failed=[r['event_id'] for r in rows if r['result']=='failed' and (r['account'],r['source_ip'])==(success['account'],success['source_ip'])]
json.dump(dict(account=success['account'],source_ip=success['source_ip'],failed_events=failed,successful_event=success['event_id'],observation='authentication_success_after_failures',compromise_confirmed=False,attribution='not_determined'),open('triage.json','w'))
PYCODE'''


def c4(ctx):
    originals(ctx)
    finding = obj(ctx, "correlation.json")
    ctx.require(finding.get("account") == ctx.data["account"] and finding.get("session") == ctx.data["session"], "認証ログの成功イベントから、アカウントとセッションを結び付けましょう。")
    ctx.require(finding.get("observed_access") == [{"asset": ctx.data["asset"], "event_id": "W01", "status": 200}], "同一セッションで成功したアクセスだけを observed_access に記録します。")
    ctx.require(finding.get("denied_access") == [{"asset": ctx.data["second"], "event_id": "W02", "status": 403}], "403 のイベントは拒否された試行として別に記録しましょう。")
    ctx.require(finding.get("excluded_events") == ["W03"] and finding.get("exfiltration_confirmed") is False, "別セッションの処理を除外し、読み取り成功だけで外部流出を断定しないようにします。")


SOL4 = '''python3 - <<'PYCODE'
import csv,json
s=next(r for r in csv.DictReader(open('logs/auth.csv')) if r['event_id']=='A03')
access=list(csv.DictReader(open('logs/access.csv')))
selected=[r for r in access if (r['account'],r['session'])==(s['account'],s['session'])]
def entry(r): return dict(asset=r['asset'],event_id=r['event_id'],status=int(r['status']))
json.dump(dict(account=s['account'],session=s['session'],observed_access=[entry(r) for r in selected if r['status']=='200'],denied_access=[entry(r) for r in selected if r['status']=='403'],excluded_events=[r['event_id'] for r in access if r not in selected],exfiltration_confirmed=False),open('correlation.json','w'))
PYCODE'''


def s5(ctx):
    base(ctx)
    config = {"service_enabled": True, "log_auth_events": False, "session_max_age_minutes": 1440,
              "sessions": {ctx.data["session"]: ctx.data["account"], "service-session": ctx.data["other"]}}
    ctx.write("settings.json", json.dumps(config, indent=2) + "\n")
    ctx.write("verify.py", '''import hashlib,json
from pathlib import Path
config=json.loads(Path('settings.json').read_text())
auth=list(__import__('csv').DictReader(open('logs/auth.csv')))
flagged=next(r for r in auth if r['event_id']=='A03')
result={'flagged_session_revoked':flagged['session'] not in config.get('sessions',{}),
        'service_session_preserved':config.get('sessions',{}).get('service-session')==next(r['account'] for r in auth if r['event_id']=='A04'),
        'service_enabled':config.get('service_enabled') is True,
        'auth_logging_enabled':config.get('log_auth_events') is True,
        'session_age_limited':type(config.get('session_max_age_minutes')) is int and 1<=config['session_max_age_minutes']<=30}
print(json.dumps({'checks':result,'config_sha256':hashlib.sha256(Path('settings.json').read_bytes()).hexdigest()},indent=2))
''')
    ctx.data["verifier_hash"] = digest(ctx.p("verify.py").read_bytes())


def c5(ctx):
    originals(ctx)
    config, result = obj(ctx, "settings.json"), obj(ctx, "retest.json")
    ctx.require(digest(ctx.p("verify.py").read_bytes()) == ctx.data["verifier_hash"], "検証ツールの内容を変更せず、設定を修正しましょう。")
    ctx.require(config.get("sessions") == {"service-session": ctx.data["other"]}, "対象セッションだけを失効させ、業務用セッションを維持しましょう。")
    ctx.require(config.get("service_enabled") is True and config.get("log_auth_events") is True, "業務サービスを止めず、認証ログを有効にしましょう。")
    value = config.get("session_max_age_minutes")
    ctx.require(type(value) is int and 1 <= value <= 30, "セッション有効期間は1〜30分の整数にしましょう。")
    checks = {"flagged_session_revoked": True, "service_session_preserved": True,
              "service_enabled": True, "auth_logging_enabled": True, "session_age_limited": True}
    ctx.require(result.get("checks") == checks and result.get("config_sha256") == digest(ctx.p("settings.json").read_bytes()), "修正後の設定に対して verify.py を実行し、その結果を retest.json に保存しましょう。")


SOL5 = '''python3 - <<'PYCODE'
import csv,json
c=json.load(open('settings.json'))
s=next(r['session'] for r in csv.DictReader(open('logs/auth.csv')) if r['event_id']=='A03')
c['sessions'].pop(s,None); c['log_auth_events']=True; c['session_max_age_minutes']=30
json.dump(c,open('settings.json','w'),indent=2)
PYCODE
python3 verify.py > retest.json'''


def s6(ctx):
    base(ctx)
    ctx.write("report-guide.txt", "report.json の項目:\ncase_id, authorization, scope, summary, findings, limitations, next_steps\n"
              "findings は1件。account, source_ip, authentication_event, accessed_asset, access_event, priority, confidence, impact, remediation, evidence を記録します。\n"
              "priority=investigate、confidence=observed_authentication_only。evidence はログ2件の path と sha256 の配列です。\n"
              "limitations は root_cause_not_determined / attribution_not_determined / exfiltration_not_confirmed を含む配列。\n"
              "summary・impact・remediation・next_steps は空欄や単語だけでなく、判断の限界と次の行動を文章で書きます。\n")


def c6(ctx):
    originals(ctx)
    report, case = obj(ctx, "report.json"), obj(ctx, "case.json")
    ctx.require(report.get("case_id") == case["case_id"] and report.get("authorization") == case["authorization"], "報告書にケースと許可番号を記録しましょう。")
    ctx.require(report.get("scope") == case["scope"], "報告書の対象範囲を、許可された2資産に合わせましょう。")
    findings = report.get("findings")
    ctx.require(isinstance(findings, list) and len(findings) == 1 and isinstance(findings[0], dict), "証拠に基づく所見を findings の1件としてまとめましょう。")
    finding = findings[0]
    fields = {"account": ctx.data["account"], "source_ip": ctx.data["ip"], "authentication_event": "A03",
              "accessed_asset": ctx.data["asset"], "access_event": "W01", "priority": "investigate", "confidence": "observed_authentication_only"}
    ctx.require(all(finding.get(k) == v for k, v in fields.items()), "所見の対象・証拠イベント・優先対応・確信度がログと一致しません。403 や別セッションを成功扱いにしないよう確認します。")
    expected = [{"path": name, "sha256": ctx.data["originals"][name]} for name in ("logs/auth.csv", "logs/access.csv")]
    ctx.require(finding.get("evidence") == expected, "所見から認証ログとアクセスログのパス・SHA-256 を参照しましょう。")
    limitations = report.get("limitations")
    ctx.require(isinstance(limitations, list) and set(limitations) == {"root_cause_not_determined", "attribution_not_determined", "exfiltration_not_confirmed"}, "原因・行為者・外部流出の未確認事項を明記しましょう。")
    for value, label in ((report.get("summary"), "summary"), (finding.get("impact"), "impact"),
                         (finding.get("remediation"), "remediation"), (report.get("next_steps"), "next_steps")):
        ctx.require(isinstance(value, str) and len(value.strip()) >= 24, f"{label} に具体的な文章を記録しましょう。文章の妥当性は別途レビューします。")


SOL6 = '''python3 - <<'PYCODE'
import csv,json,hashlib
case=json.load(open('case.json'))
a=next(r for r in csv.DictReader(open('logs/auth.csv')) if r['event_id']=='A03')
w=next(r for r in csv.DictReader(open('logs/access.csv')) if r['event_id']=='W01')
f=dict(account=a['account'],source_ip=a['source_ip'],authentication_event='A03',accessed_asset=w['asset'],access_event='W01',priority='investigate',confidence='observed_authentication_only',impact='A session read a report after failed logins; unauthorized use remains unconfirmed.',remediation='With owner approval, revoke the flagged session and verify legitimate service access.',evidence=[dict(path=p,sha256=hashlib.sha256(open(p,'rb').read()).hexdigest()) for p in ('logs/auth.csv','logs/access.csv')])
report=dict(case_id=case['case_id'],authorization=case['authorization'],scope=case['scope'],summary='Synthetic evidence shows authentication success after failures and one successful report read.',findings=[f],limitations=['root_cause_not_determined','attribution_not_determined','exfiltration_not_confirmed'],next_steps='Validate account-owner activity, preserve additional audit records, then retest approved remediation.')
json.dump(report,open('report.json','w'),indent=2)
PYCODE'''


def add(number, title, story, objectives, setup, check, solution, wrong, thinking, tools, explanation, tip):
    register(id=f"10-{number}", stage=S, title=title,
             story=story + "\n対象はこの作業フォルダの架空ケースだけです。case.json の許可範囲を確認してから作業します。",
             objectives=objectives, hints=[thinking, tools, "入力例（実行前に各行の対象を確認してください）:\n" + solution],
             answer=solution, explanation=explanation, tip=tip, setup=setup, check=check,
             solution=solution, wrong=wrong)


add(1, "証拠を保全し、取得記録を残す",
    "調査開始の依頼が届きました。原本を変更せず証拠用コピーと照合用ハッシュを作ります。",
    ["case.json と logs/ の2ログを evidence/ 配下の同じ相対パスへコピーする", "証拠コピーの権限を600にし、evidence/SHA256SUMS に3ファイルのハッシュを保存する", "collection-format.json を参考に collection.json へ許可番号・取得担当・UTC時刻を記録する"],
    s1, c1, SOL1, ["mkdir -p evidence; touch evidence/SHA256SUMS", SOL1 + "\nprintf 'changed\\n' >> logs/auth.csv", SOL1 + "\nchmod 644 evidence/logs/auth.csv"],
    "原本・取得したコピー・取得者の記録を分けます。ハッシュはコピーの一致と後の変化を確かめるための情報です。",
    "cp、chmod、sha256sum と UTC の日時記録を使います。case.json の許可番号も取得記録に含めます。",
    "コピーとハッシュを照合し、取得した内容の同一性を確認しました。ただしハッシュ単独では取得前の真正性や法的な証拠能力まで保証できません。",
    "取得方法・時刻・担当者・保管先・アクセス履歴を組織の手順に沿って残します。")
add(2, "タイムゾーンを揃えた時系列を作る",
    "認証ログは+09:00、アクセスログは+00:00です。文字列の並べ替えでは事象の順番を誤ります。",
    ["timeline.csv に utc,event_id,source,account の4列を作る", "ログ全8イベントをUTCの YYYY-MM-DDTHH:MM:SSZ に変換して時刻・イベントID順に並べる", "source に原本の相対パスを記録し、原本は保持する"],
    base, c2, SOL2, ["cp logs/auth.csv timeline.csv", SOL2 + "\nsed -i '/A03/d' timeline.csv"],
    "表示されている現地時刻ではなく、オフセットを含めた時刻として解釈します。変換後も元イベントへ戻れる参照が必要です。",
    "Python の csv と datetime.fromisoformat、astimezone(timezone.utc) で変換できます。",
    "時刻の基準とイベントへの参照が揃いました。実際には時計のずれやログ遅延も別の不確実性として扱います。",
    "時系列には元のタイムゾーン・変換方法・時計の精度の限界を添えます。")
add(3, "失敗と成功を区別して認証を調査する",
    "認証失敗が複数あります。失敗の数だけを数えず、その後の成功と組み合わせて調査対象を絞ります。",
    ["triage.json に account,source_ip,failed_events,successful_event を記録する", "観測は observation=authentication_success_after_failures とする", "compromise_confirmed=false、attribution=not_determined として断定を避ける"],
    base, c3, SOL3, ["printf '{}\\n' > triage.json", SOL3 + "\npython3 -c \"import json; p='triage.json'; d=json.load(open(p)); d['compromise_confirmed']=True; json.dump(d,open(p,'w'))\""],
    "同じアカウント・送信元の失敗と成功を結び付けます。別アカウントの失敗まで混ぜないでください。",
    "CSV の result と account/source_ip を比較し、イベント ID を所見に残します。",
    "ログ上の認証成功は確認できても、本人の操作か第三者の不正利用かは確定していません。観測と解釈を分けた初期所見です。",
    "IPアドレスはアクセス元の手掛かりであり、人物の身元を直接証明するものではありません。")
add(4, "セッションで資産へのアクセスを結び付ける",
    "認証イベントだけでは、その後にどの資産へアクセスできたか分かりません。アクセスログとセッションを突き合わせます。",
    ["correlation.json に account,session,observed_access,denied_access,excluded_events を記録する", "各アクセスを asset,event_id,status の形で、成功200と拒否403に分ける", "別セッションの業務処理を除外し、exfiltration_confirmed=false とする"],
    base, c4, SOL4, ["printf '{}\\n' > correlation.json", SOL4 + "\npython3 -c \"import json; p='correlation.json'; d=json.load(open(p)); d['observed_access']+=d['denied_access']; json.dump(d,open(p,'w'))\""],
    "送信元や時刻が近いという理由だけでまとめず、アカウントとセッションの一致を確認します。",
    "認証成功の session とアクセスログの session/account を結合します。status を見て成功と拒否を分けます。",
    "対象セッションの成功と拒否、無関係の業務処理を区別しました。HTTP 200や読み取りの記録だけで外部流出まで断定しません。",
    "影響範囲には「確認済み」「試行のみ」「未確認」を分けて記載します。")
add(5, "許可された対処を実施し、業務の維持も検証する",
    "所有者から対象セッションの失効・認証ログ有効化・有効期間短縮の承認を得ました。設定は教材の settings.json だけです。",
    ["認証ログA03のセッションだけを settings.json の sessions から削除する", "業務用セッションとservice_enabled=trueを保ち、log_auth_events=true、有効期間を1〜30分にする", "変更せずに verify.py を実行し、retest.json に結果を保存する"],
    s5, c5, SOL5, ["python3 verify.py > retest.json", SOL5 + "\npython3 -c \"import json; p='settings.json'; d=json.load(open(p)); d['sessions']={}; json.dump(d,open(p,'w'))\""],
    "全部停止する方法では業務を壊します。許可された対象を限定して変更し、正常な処理が残っていることも確かめます。",
    "設定をJSONとして読み書きし、対象セッションを削除します。検証は python3 verify.py の出力を保存します。",
    "対処の成立と業務用セッションの維持を確認しました。設定のハッシュも記録されるので、どの版を検証したかを追跡できます。",
    "再テストは「危険な状態が消えた」と「必要な機能が動く」の両側を確認します。")
add(6, "証拠と限界を添えた調査報告書を作る",
    "依頼者へ初期調査を報告します。断定を増やすのではなく、確かな観測・判断の限界・次の行動を伝えます。",
    ["report-guide.txt の形式で report.json を作る", "許可範囲、認証成功と読み取り成功の所見、原本のSHA-256を記録する", "未確定の原因・行為者・流出を明示し、影響・対処・次の確認を具体的に書く"],
    s6, c6, SOL6, ["printf '{}\\n' > report.json", SOL6 + "\npython3 -c \"import json; p='report.json'; d=json.load(open(p)); d['limitations']=[]; json.dump(d,open(p,'w'))\""],
    "依頼者が次の判断をできるよう、何を見て何が分かり、何は分からないのかを整理します。",
    "JSONで範囲と所見を構造化し、ログのハッシュとイベントIDを引用します。書式は report-guide.txt を読みます。",
    "自動判定は識別子・証拠参照・必須事項を確認します。文章の品質や業務上の妥当性まで自動保証はできないため、実務では担当者レビューが必要です。",
    "報告書は業務判断のための成果物です。技術所見と、その根拠・確信度・優先すべき行動を一緒に伝えます。")
