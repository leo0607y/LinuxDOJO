"""Stage 12: interpreting captured observations and planning bounded repairs.

Files ending .txt/.log are supplied recordings, not measurements of the learner's
machine. Actual VM measurements and ACL changes belong to the VM labs.
"""
import hashlib
import json
import secrets

from engine.runner import register

S = 12
NOTICE = ("このステージは保存済みの観測データを調べる演習です。表示値はホストPCの測定結果ではありません。"
          "変更は作業フォルダ内だけで行い、実際の負荷測定・ACL操作はVM実習で確認します。")


def prepare(files, expected):
    def setup(ctx):
        case = "OPS-" + secrets.token_hex(4)
        ctx.data.update(case=case, expected=expected)
        ctx.write("case.json", json.dumps({"case": case, "mode": "recorded-observations", "scope": "workspace only"}, indent=2))
        ctx.write("README.txt", NOTICE + "\n入力資料を保存したまま、requirements.txtに従い診断と修正を提出してください。\n")
        for path, content in files.items():
            ctx.write(path, content)
        ctx.data["originals"] = {name: hashlib.sha256(ctx.p(name).read_bytes()).hexdigest()
                                  for name in ["case.json", *files] if not name.startswith("work/")}
    return setup


def report(ctx):
    for name, digest in ctx.data["originals"].items():
        ctx.require(ctx.isfile(name) and not ctx.p(name).is_symlink()
                    and hashlib.sha256(ctx.p(name).read_bytes()).hexdigest() == digest,
                    f"観測資料 {name} を変更せず残してください。")
    try:
        data = json.loads(ctx.need_file("diagnosis.json"))
    except ValueError:
        ctx.fail("diagnosis.jsonをJSONとして保存してください。")
    ctx.require(isinstance(data, dict) and data.get("case") == ctx.data["case"], "今回のcaseを診断へ記録してください。")
    for key, value in ctx.data["expected"].items():
        ctx.require(data.get(key) == value, f"diagnosis.jsonの {key} が資料の観測と一致しません。")
    return data


def solution(fields, extra=""):
    return """python3 - <<'PYCODE'
import json
case=json.load(open('case.json'))['case']
result=""" + repr(fields) + """
result['case']=case
json.dump(result,open('diagnosis.json','w'),indent=2)
PYCODE
""" + extra


def add(n, title, story, files, expected, objectives, thinking, tools, explanation, extra_check=None, extra_solution="", wrong=None):
    def check(ctx):
        report(ctx)
        if extra_check:
            extra_check(ctx)
    sol = solution(expected, extra_solution)
    register(id=f"12-{n}", stage=S, title=title, story=story + "\n\n" + NOTICE,
             objectives=objectives + ["case.jsonのcaseを含むdiagnosis.jsonを作り、元の観測資料は維持する"],
             hints=[thinking, tools, "資料の数値・対象・時刻を区別してJSONに記録します。具体例はanswerで確認できます。"],
             answer=sol, explanation=explanation,
             tip="平均値だけで結論を決めず、観測期間と別の指標を照合します。VM実習では実測と変更後の確認も行います。",
             setup=prepare(files, expected), check=check, solution=sol,
             wrong=wrong or ["printf '{}\n' > diagnosis.json", sol + "\nprintf 'changed\n' >> case.json"])


add(1, "CPU待ちとI/O待ちを分ける", "2台の観測記録から、どちらの資源が詰まっているかを切り分けます。vmstatの最初の行は起動以来の平均です。",
    {"cpu-vmstat.txt": "# 2 vCPU; vmstat 1 3; first numeric row is since-boot average\nr b swpd free buff cache si so bi bo in cs us sy id wa st\n1 0 0 900000 30000 400000 0 0 3 2 80 160 10 2 88 0 0\n7 0 0 900000 30000 400000 0 0 0 0 1100 2100 93 6 1 0 0\n8 0 0 899000 30000 400000 0 0 0 0 1100 2200 94 5 1 0 0\n",
     "io-vmstat.txt": "# 2 vCPU; vmstat 1 3\nr b swpd free buff cache si so bi bo in cs us sy id wa st\n1 0 0 900000 30000 400000 0 0 3 2 80 160 10 2 88 0 0\n1 5 0 900000 30000 400000 0 0 25000 10000 800 1800 5 4 20 71 0\n1 6 0 900000 30000 400000 0 0 27000 11000 900 1900 4 5 19 72 0\n",
     "requirements.txt": "diagnosis.json: cpu_host/io_hostをcpu-saturation・io-wait-suspectedから選ぶ。cpu_evidenceは[r,us,id]または[b,wa]、io_evidenceも同じ候補から選ぶ。first_sampleはsince-boot-averageまたはinstantaneous。next_checkはper-device-latencyまたはkill-all-workers。\n"},
    {"cpu_host": "cpu-saturation", "io_host": "io-wait-suspected", "cpu_evidence": ["r", "us", "id"], "io_evidence": ["b", "wa"], "first_sample": "since-boot-average", "next_check": "per-device-latency"},
    ["cpu-vmstat.txtとio-vmstat.txtを比較し、CPUとI/O待ちを区別する", "requirements.txtのJSON項目を記録する"],
    "r・bと、CPU時間の内訳を組み合わせます。起動以来の平均を現在値と取り違えないでください。", "catやcolumnで資料を読み、us・id・waと待機列を比較します。",
    "rがvCPU数より継続的に多く、usが高くidが小さい記録はCPU飽和を示唆します。bとwaの高い記録ではI/Oを追加調査します。wa単独では故障デバイスや根本原因を断定できません。参考: https://man7.org/linux/man-pages/man8/vmstat.8.html")

add(2, "空きメモリとOOMの証拠", "freeの小ささだけでメモリ不足と断定せず、利用可能量・スワップの動き・カーネル記録を照合します。",
    {"free.txt": "              total used free shared buff/cache available\nMem:          4096 1800 100 30 2196 2100\nSwap:         1024 0 1024\n",
     "incident-vmstat.txt": "r b swpd free buff cache si so bi bo in cs us sy id wa st\n3 0 950000 18000 8000 18000 12000 16000 16000 17000 9000 12000 70 20 3 7 0\n",
     "kernel.log": "2026-11-21T01:02:00Z kernel: Out of memory: Killed process 3188 (report-worker) total-vm:2097152kB anon-rss:1843200kB\n",
     "requirements.txt": "diagnosis.json: healthy_snapshotはavailable-memory-remainsまたはout-of-memory。incidentはmemory-pressure-with-oomまたはnormal-cache-use。killed_processはログから読む。evidenceは根拠になる資料名の配列。immediate_actionはlimit-worker-concurrencyまたはdisable-oom-killer、avoidは避ける方を選ぶ。\n"},
    {"healthy_snapshot": "available-memory-remains", "incident": "memory-pressure-with-oom", "killed_process": "report-worker", "evidence": ["incident-vmstat.txt", "kernel.log"], "immediate_action": "limit-worker-concurrency", "avoid": "disable-oom-killer"},
    ["平常時のavailableと障害時のsi/so・OOM記録を分けて説明する", "停止されたプロセスと負荷を減らす初動を記録する"],
    "キャッシュがあることと、必要な割り当てができないことは同じではありません。異なる時点の記録を混ぜずに読みます。", "freeのavailable、vmstatのsi/so、kernel.logのKilled processを比較します。",
    "平常スナップショットには利用可能メモリが残っています。障害記録はスワップの出入りとOOMによる停止を示します。OOM killerを無効化して隠すのではなく並列数・使用量・制限を調べます。スワップを増やすだけで性能問題が解決するとは限りません。")

add(3, "I/Oの遅延をデバイスへ絞る", "アプリが遅いという報告です。iostatの記録から追加調査するデバイスを選び、単一指標で物理障害を断定しない報告を作ります。",
    {"iostat.txt": "# iostat -xz 1 2; final interval shown\nDevice r/s w/s r_await w_await aqu-sz %util\nvda 4 3 1.5 2.0 0.02 4.0\nvdb 180 260 85.0 120.0 12.5 99.0\n",
     "mounts.txt": "/dev/vda1 / ext4 rw 0 0\n/dev/vdb1 /srv/reports ext4 rw 0 0\n",
     "requirements.txt": "diagnosis.json: investigate_deviceとaffected_mountは資料から読む。evidenceは[await,queue-depth]または[device-name-only]。conclusionはlatency-and-queue-observedまたはphysical-failure-proven。next_checkはper-process-io-and-baselineまたはreplace-all-disks。physical_failure_confirmedは根拠があればtrue、なければfalse。\n"},
    {"investigate_device": "vdb", "affected_mount": "/srv/reports", "evidence": ["await", "queue-depth"], "conclusion": "latency-and-queue-observed", "next_check": "per-process-io-and-baseline", "physical_failure_confirmed": False},
    ["遅延とキューが大きいデバイスを特定し、マウント先を対応付ける", "%utilだけから物理故障と断定しない"],
    "利用率に加えて応答時間と待ち列、何がそのデバイスを使うかを確認します。", "iostat.txtのawait・aqu-szとmounts.txtを照合します。",
    "この区間ではvdbの遅延とキューが目立ちます。%utilは装置の並列性などにも依存するので、100%付近というだけで物理故障や限界を断定しません。平常値と処理単位のI/Oも調べます。")


def check_config(ctx):
    ctx.require(ctx.need_file("work/worker.conf") == "input=/srv/data/jobs.csv\nworkers=2\n", "正しい入力先とworkers=2を保ってworker.confを修正してください。")

add(4, "straceから設定の参照先を追う", "プロセスは起動直後に終了します。権限を広げる前に、システムコールと設定のパスを照合します。",
    {"worker.strace": 'openat(AT_FDCWD, "/srv/data/job.csv", O_RDONLY) = -1 ENOENT (No such file or directory)\nwrite(2, "input unavailable", 17) = 17\nexit_group(1) = ?\n',
     "inventory.txt": "/srv/data/jobs.csv exists mode=0640 owner=dojo-worker\n",
     "work/worker.conf": "input=/srv/data/job.csv\nworkers=2\n",
     "requirements.txt": "diagnosis.json: syscall/errnoを記録から読む。causeはwrong-config-pathまたはunix-permissions。corrected_pathはinventory.txtから選ぶ。work/worker.confのinputだけを修正する。\n"},
    {"syscall": "openat", "errno": "ENOENT", "cause": "wrong-config-path", "corrected_path": "/srv/data/jobs.csv"},
    ["失敗した呼び出し・エラー名・正しいパスを記録する", "work/worker.confを修正しworkers=2は維持する"],
    "ENOENTとEACCESは別の原因です。設定と存在するファイル名を比較します。", "保存済みstraceのopenat行を読み、sedなどで設定の誤字だけを修正します。",
    "この記録はENOENTなので、chmod 777を試す根拠にはなりません。実測では対象プロセスと機密情報の扱いに注意してstraceを使い、修正後に正常動作も再確認します。", check_config,
    "sed -i 's@/srv/data/job.csv@/srv/data/jobs.csv@' work/worker.conf",
    ["chmod 777 work/worker.conf", solution({"syscall": "openat", "errno": "EACCES", "cause": "permissions", "corrected_path": "/srv/data/jobs.csv"})])


def check_update(ctx):
    ctx.require(ctx.need_file("work/app.conf") == "listen=127.0.0.1\nport=8080\nworkers=4\n", "待ち受けとportを維持し、合意したworkers=4だけを統合してください。")
    ctx.require(ctx.need_file("work/app.conf.before") == "listen=127.0.0.1\nport=8080\nworkers=2\n", "変更前の設定をapp.conf.beforeに保全してください。")

add(5, "ディストリビューションと更新差分", "UbuntuとFedoraの2台を更新する計画です。Fedora側では新しい設定候補が置かれています。ローカルの必要な値を残して差分を統合します。",
    {"ubuntu-os-release": 'ID=ubuntu\nVERSION_ID="24.04"\nID_LIKE=debian\n', "fedora-os-release": 'ID=fedora\nVERSION_ID="42"\n',
     "work/app.conf": "listen=127.0.0.1\nport=8080\nworkers=2\n", "app.conf.rpmnew": "listen=0.0.0.0\nport=8000\nworkers=4\n",
     "requirements.txt": "診断: ubuntu_manager/fedora_managerはapt・dnfから選ぶ。pending_fileは更新時の設定候補ファイル名。actionはreview-and-mergeまたはoverwrite-all。work/app.confを退避しworkersだけ4へ変更。listenとportは維持。ホストの更新コマンドは実行しない。\n"},
    {"ubuntu_manager": "apt", "fedora_manager": "dnf", "pending_file": "app.conf.rpmnew", "action": "review-and-merge"},
    ["os-releaseを使いパッケージ管理方法を対応付ける", "設定候補を丸ごと上書きせず、退避してworkersだけを統合する"],
    "パッケージ管理ツールと、更新後に残された設定差分は別々に確認します。", "os-releaseとdiffを読み、cpで退避してから必要な差分を編集します。",
    ".rpmnewは更新時に提供された設定候補として扱います。保存方法はパッケージの設定ファイル指定にも依存します。差分を無条件に採用せず、合意した公開範囲とポートを保ちます。参考: https://fedoraproject.org/wiki/DNF_system_upgrade", check_update,
    "cp work/app.conf work/app.conf.before\nsed -i 's/workers=2/workers=4/' work/app.conf")


def check_monitor(ctx):
    try:
        policy = json.loads(ctx.need_file("work/alerts.json"))
    except ValueError:
        ctx.fail("alerts.jsonはJSONで作ります。")
    ctx.require(policy == {"disk_used_percent": 85, "consecutive_samples": 3, "clear_below_percent": 80, "notify": "on-call"}, "警告の閾値・連続回数・解除条件・通知先を要件に合わせてください。")
    text = ctx.need_file("work/logrotate.conf")
    required = ("/var/log/dojo/app.log {", "daily", "rotate 7", "compress", "missingok", "notifempty", "create 0640 dojo-app adm", "}")
    ctx.require([line.strip() for line in text.splitlines() if line.strip()] == list(required), "指定された範囲のローテーション設定を作ってください。")

add(6, "監視の通知とログ保存を設計する", "一瞬の値で通知が連発し、ログも増え続けています。閾値・継続条件・解除条件を分け、7世代のログを残します。",
    {"policy.txt": "disk used >=85% が3回連続したらon-callへ通知し、80%未満で解除。ログはdaily、7世代、圧縮、空/欠損は無視、新規0640 dojo-app:adm。\n",
     "requirements.txt": "diagnosis: alert=duration-with-hysteresis, log_retention=daily-seven-generations。work/alerts.jsonとwork/logrotate.confを作成。設定の保存判定であり実際の通知やlogrotate実行はVM側で別途確認。\n"},
    {"alert": "duration-with-hysteresis", "log_retention": "daily-seven-generations"},
    ["policy.txtに沿って監視条件とログ保存設定を作成する", "設定の保存と実際の通知・ローテーションの確認を区別する"],
    "警告になる条件と解除する条件を同じ値にすると通知が揺れやすくなります。", "JSONに閾値と連続回数を記録し、ログの保存世代と新規作成時の権限を記述します。",
    "監視は閾値だけでなく継続時間・通知先・解除の設計が必要です。この課題は設定作成までで、実環境のlogrotateや通知を実行した証明ではありません。", check_monitor,
    r"""mkdir -p work
python3 - <<'PYCODE'
import json
json.dump(dict(disk_used_percent=85,consecutive_samples=3,clear_below_percent=80,notify='on-call'),open('work/alerts.json','w'))
open('work/logrotate.conf','w').write('/var/log/dojo/app.log {\n    daily\n    rotate 7\n    compress\n    missingok\n    notifempty\n    create 0640 dojo-app adm\n}\n')
PYCODE""")


def check_acl(ctx):
    access = ctx.need_file("work/report.acl")
    ctx.require([line.strip() for line in access.splitlines() if line.strip()] == ["user::rw-", "user:analyst:r--", "group::---", "mask::r--", "other::---"], "レポートのACLでanalystの読み取りとmask、other拒否を維持してください。")
    default = ctx.need_file("work/reports.default.acl")
    ctx.require([line.strip() for line in default.splitlines() if line.strip()] == ["default:user::rwx", "default:user:analyst:r-x", "default:group::---", "default:mask::r-x", "default:other::---"], "将来のファイルへ継承する既定ACLも設定してください。")

add(7, "ACLの実効権限と継承", "名前付きユーザーにはr--があるのに、読み取りに失敗しています。ACL maskと既定ACLの役割を区別します。",
    {"recorded-getfacl.txt": "# file: reports/report.txt\nuser::rw-\nuser:analyst:r-- #effective:---\ngroup::---\nmask::---\nother::---\n",
     "requirements.txt": "診断: denied_byはacl-maskまたはowner-mode。named_userは資料から読む。effective_afterはr--・rw-・---から選ぶ。future_filesはdefault-aclまたはcurrent-file-acl。work/report.aclとwork/reports.default.aclに課題で指定したACLを記述。現在のファイル: 所有者rw-, analyst r--, group/other---, mask r--。将来用: 所有者rwx, analyst r-x, group/other---, mask r-x。これはACLテキストの演習で、適用はVM permissions実習。\n"},
    {"denied_by": "acl-mask", "named_user": "analyst", "effective_after": "r--", "future_files": "default-acl"},
    ["名前付きユーザーの許可とmaskの共通部分が実効権限になることを説明する", "現在のファイルのACLとディレクトリの既定ACLを別々に作る"],
    "名前付きユーザーの許可だけを見ず、effectiveとmaskを読みます。将来の作成物には別の既定設定が必要です。", "getfacl形式の資料を読みます。実環境での適用と確認にはsetfacl/getfaclを使います。",
    "ACL maskは名前付きユーザー・グループなどの許可を制限します。既定ACLはディレクトリ内に新規作成するオブジェクトへの継承であり、既存ファイルのACLを後から変更するものではありません。参考: https://man7.org/linux/man-pages/man5/acl.5.html", check_acl,
    """mkdir -p work
printf '%s\n' 'user::rw-' 'user:analyst:r--' 'group::---' 'mask::r--' 'other::---' > work/report.acl
printf '%s\n' 'default:user::rwx' 'default:user:analyst:r-x' 'default:group::---' 'default:mask::r-x' 'default:other::---' > work/reports.default.acl""")


def check_mac(ctx):
    policy = ctx.need_file("work/local-profile.rules")
    ctx.require(policy == "/srv/dojo/reports/** r,\n", "必要なreportsだけを読み取り許可する規則へ限定してください。")
    service = ctx.need_file("work/service-security.json")
    ctx.require(json.loads(service) == {"User": "dojo-web", "AmbientCapabilities": ["CAP_NET_BIND_SERVICE"], "NoNewPrivileges": True, "mac_mode": "enforce"}, "非root・必要な能力のみ・MAC有効を保ってください。")

add(8, "通常権限とMAC・capabilityを分ける", "ファイルの通常権限は読める設定ですが、アプリの読み取りが拒否されています。root化やMAC停止で回避せず、根拠に沿った狭い対策を設計します。",
    {"recorded-ls.txt": "-rw-r----- dojo-web dojo-web /srv/dojo/reports/daily.txt\n",
     "recorded-audit.log": 'apparmor="DENIED" operation="open" profile="dojo-web" name="/srv/dojo/reports/daily.txt" requested_mask="r" denied_mask="r"\n',
     "requirements.txt": "診断: layerはmandatory-access-controlまたはunix-mode。evidenceは根拠になる資料名。unix_mode_change_neededはtrue/false。特権ポートを非rootでbindするためのrequired_capabilityはCAP_NET_BIND_SERVICEまたはCAP_DAC_OVERRIDEから選ぶ。work/local-profile.rulesにreports以下だけの読み取り規則を1行、work/service-security.jsonにUser=dojo-web、AmbientCapabilities=[CAP_NET_BIND_SERVICE]、NoNewPrivileges=true、mac_mode=enforce。実際のAppArmor/systemdへは適用しない。\n"},
    {"layer": "mandatory-access-control", "evidence": "recorded-audit.log", "unix_mode_change_needed": False, "required_capability": "CAP_NET_BIND_SERVICE"},
    ["通常の所有権・モードとMAC拒否の証拠を分ける", "必要なパスだけの読み取りと必要なcapabilityだけを記述する"],
    "権限が足りないと見えたら、どの制御が拒否したかを確かめます。全体の保護を無効にする必要はありません。", "audit記録のDENIED・profile・requested_maskを読み、限定した規則とサービス方針を作ります。",
    "通常のDAC、ACL、capabilities、MACは別の制御です。AppArmorの拒否には対象プロファイルと必要なパスを確認します。CAP_NET_BIND_SERVICEは特権ポートへのbindに関する能力で、任意のファイル読み取り権限ではありません。参考: https://man7.org/linux/man-pages/man7/capabilities.7.html", check_mac,
    """mkdir -p work
printf '%s\n' '/srv/dojo/reports/** r,' > work/local-profile.rules
python3 - <<'PYCODE'
import json
json.dump(dict(User='dojo-web',AmbientCapabilities=['CAP_NET_BIND_SERVICE'],NoNewPrivileges=True,mac_mode='enforce'),open('work/service-security.json','w'))
PYCODE""")
