# title: systemdのサービス・timerを導入し、ログから設定故障を復旧する

_software_paths() {
    [[ ${LAB_ID:-} == software && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/software ]] || { echo 'software: unexpected lab context' >&2; return 1; }
    SOFTWARE_SERVICE=/etc/systemd/system/dojo-software.service
    SOFTWARE_TIMER=/etc/systemd/system/dojo-software.timer
    SOFTWARE_SCRIPT=/usr/local/lib/linuxdojo-vm-lab/dojo-software-job.py
    SOFTWARE_CONFIG=/etc/dojo-software.conf
    local path
    for path in "$SOFTWARE_SERVICE" "$SOFTWARE_TIMER" "$SOFTWARE_SCRIPT" "$SOFTWARE_CONFIG"; do
        [[ ! -L $path ]] || { echo 'software: symbolic target rejected' >&2; return 1; }
    done
}

# Generate a user-space job without invoking systemd or modifying the host.
_software_write_job() {
    [[ ! -e $1 && ! -L $1 ]] || return 1
    cat > "$1" <<'PROGRAM'
#!/usr/bin/python3
import json
import os
import pathlib
import re
import sys
import time

try:
    text = pathlib.Path(sys.argv[1] if len(sys.argv) == 2 else "/etc/dojo-software.conf").read_text(encoding="utf-8")
    match = re.fullmatch(r"message=([A-Za-z0-9_-]{1,80})\n?", text)
    if not match:
        raise ValueError("expected exactly message=<letters/digits/_/->")
    directory = pathlib.Path(os.environ["STATE_DIRECTORY"])
    record = {"message": match.group(1), "timestamp_ns": time.time_ns(), "uid": os.getuid()}
    path = directory / "report.json"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    print("dojo-report-success " + match.group(1), flush=True)
except (OSError, ValueError, KeyError) as error:
    print("dojo-report-configuration-error: " + str(error), file=sys.stderr, flush=True)
    sys.exit(2)
PROGRAM
}

lab_setup() {
    _software_paths || return 1
    local path
    for path in "$SOFTWARE_SERVICE" "$SOFTWARE_TIMER" "$SOFTWARE_SCRIPT" "$SOFTWARE_CONFIG" "$LAB_STATE/phase"; do
        [[ ! -e $path ]] || { echo "既存の対象を上書きしません: $path"; return 1; }
    done
    printf 'report_%s\n' "$(cat /proc/sys/kernel/random/uuid | cut -c1-8)" > "$LAB_STATE/message"
    _software_write_job "$LAB_STATE/job.py" || return 1

    cat > "$LAB_STATE/dojo-software.service" <<UNIT
[Unit]
Description=LinuxDOJO dedicated report job
[Service]
Type=oneshot
DynamicUser=yes
StateDirectory=dojo-software
StateDirectoryMode=0700
ExecStart=/usr/bin/python3 $SOFTWARE_SCRIPT
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
UNIT
    cat > "$LAB_STATE/dojo-software.timer" <<'UNIT'
[Unit]
Description=LinuxDOJO dedicated report schedule
[Timer]
OnActiveSec=3s
OnUnitActiveSec=10s
AccuracySec=1s
Unit=dojo-software.service
[Install]
WantedBy=timers.target
UNIT
    printf 'message=%s\n' "$(cat "$LAB_STATE/message")" > "$LAB_STATE/config.example"
    printf 'install\n' > "$LAB_STATE/phase"
    cat > "$LAB_STATE/TASK.txt" <<TASK
対象はdojo-software.service/.timerと専用設定だけです。通常のサービスは変更しません。
この専用VMの中だけで sudo -i を実行し、rootの作業シェルへ入ります。
cd $LAB_STATE
1. job.py、unit、config.exampleを読み、ユーザー/実行先/書込先/周期を説明します。
   sudo install -m 0755 job.py $SOFTWARE_SCRIPT
   sudo install -m 0644 config.example $SOFTWARE_CONFIG
   sudo install -m 0644 dojo-software.service dojo-software.timer /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/dojo-software.service /etc/systemd/system/dojo-software.timer
   sudo systemctl daemon-reload
   sudo systemctl enable --now dojo-software.timer
   sudo systemctl start dojo-software.service
   sudo systemctl list-timers --all dojo-software.timer
   sudo journalctl -u dojo-software.service -b --no-pager
   sudo cat /var/lib/dojo-software/report.json
   sudo dojo-vm-lab software check
2. sudo dojo-vm-lab software break
   sudo systemctl status dojo-software.service; sudo journalctl -u dojo-software.service -b
   sudo cat /etc/dojo-software.conf
   設定をconfig.exampleと同じ内容へ戻します。unitやプログラムでエラーを隠しません。
   sudo systemctl restart dojo-software.service
   sudo systemctl start dojo-software.timer
   sudo dojo-vm-lab software check
3. 修正後、この使い捨てVMを再起動し、timerの自動起動とログを確認。
   sudo dojo-vm-lab software check
4. 停止と撤去:
   sudo systemctl disable --now dojo-software.timer
   sudo systemctl stop dojo-software.service
   sudo rm /etc/systemd/system/dojo-software.service /etc/systemd/system/dojo-software.timer
   sudo systemctl daemon-reload
   sudo rm $SOFTWARE_SCRIPT $SOFTWARE_CONFIG
   sudo dojo-vm-lab software check → ここまでで修了
   StateDirectoryのレポートは証拠として残ります。resetは教材ファイルだけ撤去します。
各checkは段階確認です。最初の起動だけで修了にはなりません。
TASK
    echo "手順: $LAB_STATE/TASK.txt。実際のサービスの導入は利用者が行います。"
}

_software_installed() {
    local path source
    for source in dojo-software.service dojo-software.timer; do
        path="/etc/systemd/system/$source"
        cmp -s "$LAB_STATE/$source" "$path" || { echo 'unit本文を手本と同じに保ちます。'; return 1; }
    done
    cmp -s "$LAB_STATE/job.py" "$SOFTWARE_SCRIPT" || { echo 'job.pyを書き換えて検査を回避しません。'; return 1; }
    cmp -s "$LAB_STATE/config.example" "$SOFTWARE_CONFIG" || { echo '設定本文を確認します。'; return 1; }
    systemctl is-enabled --quiet dojo-software.timer || return 1
    systemctl is-active --quiet dojo-software.timer || return 1
    [[ $(systemctl show dojo-software.service -p Result --value) == success ]] || return 1
    python3 - "$LAB_STATE/message" "$LAB_STATE/minimum-ns" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path("/var/lib/dojo-software/report.json").read_text())
assert report["message"] == pathlib.Path(sys.argv[1]).read_text().strip(), "report message mismatch"
assert report["uid"] != 0, "job must run unprivileged"
minimum = pathlib.Path(sys.argv[2])
if minimum.exists():
    assert report["timestamp_ns"] > int(minimum.read_text()), "report is from before fault injection"
PY
}

lab_break() {
    _software_paths || return 1
    [[ -f $LAB_STATE/phase && $(cat "$LAB_STATE/phase") == fault-ready ]] || { echo '導入checkを済ませてからbreakします。'; return 1; }
    _software_installed || return 1
    systemctl stop dojo-software.timer
    systemctl stop dojo-software.service
    python3 -c 'import time; print(time.time_ns())' > "$LAB_STATE/minimum-ns"
    cat /proc/sys/kernel/random/boot_id > "$LAB_STATE/fault-boot-id"
    printf 'message broken syntax\n' > "$SOFTWARE_CONFIG"
    if systemctl start dojo-software.service; then echo '期待した故障が起きませんでした。'; return 1; fi
    journalctl --sync
    journalctl -u dojo-software.service -b --no-pager -n 30 > "$LAB_STATE/failure-journal.txt"
    grep -q 'dojo-report-configuration-error:' "$LAB_STATE/failure-journal.txt" || return 1
    printf 'repair\n' > "$LAB_STATE/phase"
    echo '設定エラーでサービスが失敗しました。statusとjournalctlを読んで設定を修正します。'
}

lab_check() {
    _software_paths || return 1
    [[ -f $LAB_STATE/phase ]] || { echo '先にsetupします。'; return 1; }
    local phase next
    phase=$(cat "$LAB_STATE/phase")
    case "$phase" in
        install) _software_installed || return 1; next=fault-ready ;;
        fault-ready) echo '次はsoftware breakです。まだ修了ではありません。'; return 1 ;;
        repair) _software_installed || return 1; next=reboot ;;
        reboot)
            [[ $(cat /proc/sys/kernel/random/boot_id) != $(cat "$LAB_STATE/fault-boot-id") ]] || { echo '修正後に専用VMを再起動します。'; return 1; }
            _software_installed || return 1
            journalctl -u dojo-software.service -b --no-pager -o cat | grep -Fx "dojo-report-success $(cat "$LAB_STATE/message")" >/dev/null || { echo 'この起動後の実行ログがまだありません。数秒待って再確認します。'; return 1; }
            next=uninstall ;;
        uninstall|complete)
            [[ ! -e $SOFTWARE_SERVICE && ! -e $SOFTWARE_TIMER && ! -e $SOFTWARE_SCRIPT && ! -e $SOFTWARE_CONFIG ]] || { echo '専用unit・スクリプト・設定を撤去します。'; return 1; }
            if systemctl is-active --quiet dojo-software.timer || systemctl is-enabled --quiet dojo-software.timer || systemctl is-active --quiet dojo-software.service; then
                echo 'timerの停止/無効化とdaemon-reloadを確認します。'; return 1
            fi
            next=complete ;;
        *) echo '実習状態が不正です。'; return 1 ;;
    esac
    printf '%s\n' "$next" > "$LAB_STATE/phase"
    printf '%s -> %s\n' "$phase" "$next" >> "$LAB_STATE/milestones"
    if [[ $next == complete ]]; then
        echo '修了: 実サービスとtimerの導入・ログ調査・設定復旧・再起動・撤去を確認しました。'
    else
        printf '段階確認OK（未修了）。次: %s。TASK.txtを読み進めます。\n' "$next"
    fi
}

lab_reset() {
    _software_paths || return 1
    [[ -f $LAB_STATE/phase && -f $LAB_STATE/job.py ]] || { echo '教材を作成した証拠がありません。削除しません。'; return 1; }
    systemctl disable --now dojo-software.timer 2>/dev/null || true
    systemctl stop dojo-software.service 2>/dev/null || true
    rm -f -- "$SOFTWARE_SERVICE" "$SOFTWARE_TIMER" "$SOFTWARE_SCRIPT" "$SOFTWARE_CONFIG"
    systemctl daemon-reload
    systemctl reset-failed dojo-software.service 2>/dev/null || true
    rm -f -- "$LAB_STATE/phase" "$LAB_STATE/job.py" "$LAB_STATE/config.example" "$LAB_STATE/dojo-software.service" "$LAB_STATE/dojo-software.timer" "$LAB_STATE/message" "$LAB_STATE/TASK.txt" "$LAB_STATE/milestones" "$LAB_STATE/minimum-ns" "$LAB_STATE/fault-boot-id" "$LAB_STATE/failure-journal.txt"
    echo '専用サービスとtimerを解除しました。/var/lib/dojo-softwareの証拠レポートは残します。'
}
