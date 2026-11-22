# title: Lynis監査とハードニング: 自動更新(APT::Periodic)・ログインバナー・umask 027で指標を上げる
# roles: app
# Runs lynis with its OWN report/log files under the lab state (host /var/log/lynis*.{dat,log} are not overwritten).
# Only three lab-listed, harmless fixes are judged: apt.conf.d drop-in, /etc/issue.net banner, /etc/profile.d umask drop-in.
# lynis is NOT part of the base image: setup prints the apt line and exits without writing when missing.

_ly_paths() {
    [[ ${LAB_ID:-} == lynis && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/lynis ]] || { echo 'lynis: unexpected lab context' >&2; return 1; }
    LY_APT=/etc/apt/apt.conf.d/52dojo-auto-upgrades
    LY_UMASK=/etc/profile.d/dojo-umask.sh
    LY_ISSUE=/etc/issue.net
    LY_TARGETS_ALLOWED='BANN-7130 PKGS-7420'
    [[ ! -L $LY_APT && ! -L $LY_UMASK && ! -L $LY_ISSUE ]] || return 1
}

_ly_tools() {
    command -v lynis >/dev/null && command -v python3 >/dev/null && command -v apt-config >/dev/null || {
        echo 'lynis がありません。次を実行してから、もう一度setupしてください: sudo apt-get update && sudo apt-get install -y lynis'
        return 1
    }
}

# $1 = report file, $2 = log file
_ly_run() {
    rm -f -- "${1:?}"
    timeout 600 lynis audit system --quick --no-colors --quiet --report-file "$1" --logfile "$2" >"$LAB_STATE/lynis-stdout.txt" 2>&1 || true
    [[ -s $1 ]] || { echo "lynis のレポート $1 が作られませんでした(lynis-stdout.txt を確認)。"; return 1; }
}

# $1 = report.dat -> JSON {index, warnings, suggestions, executed}
_ly_summary() {
    python3 - "$1" <<'PY'
import json, sys
index, warn, sugg, execd = None, [], [], []
for line in open(sys.argv[1], errors='replace'):
    line = line.rstrip('\n')
    key, _, val = line.partition('=')
    if key == 'hardening_index' and val.strip().isdigit(): index = int(val)
    elif key == 'warning[]': warn.append(val.split('|')[0])
    elif key == 'suggestion[]': sugg.append(val.split('|')[0])
    elif key == 'tests_executed': execd = [x for x in val.split('|') if x]
print(json.dumps({'index': index, 'warnings': sorted(set(warn)), 'suggestions': sorted(set(sugg)), 'executed': sorted(set(execd))}))
PY
}

# $1 = baseline json, $2 = after json, $3 = targets (space separated). Exit 0 only when all conditions hold.
_ly_compare() {
    python3 - "$1" "$2" "$3" <<'PY'
import json, sys
base, after, targets = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3].split()
bad = []
if base['index'] is None or after['index'] is None: bad.append('hardening_index を読めません')
elif after['index'] < base['index'] + 1: bad.append('hardening_index が基準値 %s から +1 以上上がっていません(現在 %s)' % (base['index'], after['index']))
new = sorted(set(after['warnings']) - set(base['warnings']))
if new: bad.append('新しい warning が増えています: ' + ', '.join(new))
for t in targets:
    if t not in after['executed']: bad.append('%s が実行されていません(スキップ?)' % t)
    elif t in after['suggestions'] or t in after['warnings']: bad.append('%s がまだ suggestion/warning に残っています' % t)
for b in bad: print(b)
sys.exit(1 if bad else 0)
PY
}

_ly_check_apt() {
    [[ -f $LY_APT ]] || { echo "$LY_APT を作成します(apt.conf.d のドロップイン)。"; return 1; }
    dpkg -s unattended-upgrades 2>/dev/null | grep -q '^Status: install ok installed' || { echo 'unattended-upgrades パッケージが入っていません。'; return 1; }
    local dump k
    dump=$(apt-config dump) || return 1
    for k in 'APT::Periodic::Update-Package-Lists "1";' 'APT::Periodic::Download-Upgradeable-Packages "1";' 'APT::Periodic::Unattended-Upgrade "1";' 'APT::Periodic::AutocleanInterval "7";'; do
        grep -qF "$k" <<<"$dump" || { echo "apt-config dump に ${k} がありません(実効値)。"; return 1; }
    done
    grep -qE '^[[:space:]]*APT::Periodic::' "$LY_APT" || { echo "$LY_APT に APT::Periodic 設定を書きます。"; return 1; }
}

_ly_check_banner() {
    python3 - "$LY_ISSUE" <<'PY'
import re, sys
try: t = open(sys.argv[1]).read()
except OSError: print('/etc/issue.net がありません。'); sys.exit(1)
lines = [l for l in t.splitlines() if l.strip()]
if len(lines) < 2 or not re.search(r'authori[sz]ed|unauthori[sz]ed|legal|prohibit|monitor|権限|禁止', t, re.I):
    print('/etc/issue.net に、無許可利用の警告を含む2行以上のバナーを書きます。'); sys.exit(1)
if re.search(r'\\[SrmvsnlL]|ubuntu|\d+\.\d+', t, re.I):
    print('バナーにOS名・バージョンなどの情報を入れません。'); sys.exit(1)
PY
}

_ly_check_umask() {
    [[ -f $LY_UMASK ]] || { echo "$LY_UMASK を作成します(profile.d のドロップイン)。"; return 1; }
    local got
    got=$(env -i HOME=/root PATH=/usr/bin:/bin bash -l -c umask 2>/dev/null) || return 1
    [[ $got == 0027 || $got == 027 ]] || { echo "ログインシェルの umask が 027 になっていません(現在: ${got:-?})。"; return 1; }
}

lab_setup() {
    _ly_paths || return 1
    _ly_tools || return 1
    [[ ! -e $LY_APT && ! -e $LY_UMASK ]] || { echo '同名のドロップインが既にあります。既存を上書きしません。'; return 1; }
    touch "$LAB_STATE/owns-lab"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
lynis(監査ツール)の結果を見ながら、ホスト全体に影響しない安全な3項目だけを直す。
1. sudo dojo-vm-lab lynis break  : 現在の状態でlynisを実行し、基準(hardening_index・suggestion・warning)を記録する(数分かかる)
2. 自動更新: unattended-upgrades を入れ、$LY_APT に APT::Periodic の
   Update-Package-Lists=1 / Download-Upgradeable-Packages=1 / Unattended-Upgrade=1 / AutocleanInterval=7 を書く(apt-config dump で実効値確認)
3. ログインバナー: $LY_ISSUE に無許可利用の警告(OS名・バージョンを含めない2行以上)を書く(元ファイルは reset で戻る)。
   Lynisは警告の語彙も検査する。BANN-7130 が残る場合は専用ログで一致語数を確認し、legal warning / authorized access / prohibited / monitored / logged 等を意味のある文章で記す。
4. umask: $LY_UMASK で umask 027 を設定。確認: env -i bash -l -c umask
5. 自分でも sudo lynis audit system --quick --report-file /tmp/x.dat して suggestion[] を読み、指標の動きを確かめる(判定は専用レポートで行う)
6. 判定: sudo dojo-vm-lab lynis check  (lynisを再実行し、hardening_indexが基準+1以上・新規warningなし・対象テストIDが suggestion から消えたことを確認)
やらないこと: sshdの設定変更、コンパイラの制限、カーネルや認証系の変更。lynisの全suggestionを潰すのは目的ではない。
reset はこの課題が置いたファイルだけを消します(unattended-upgradesパッケージは削除しない)。
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudoで読む)。次に sudo dojo-vm-lab lynis break"
}

lab_break() {
    _ly_paths || return 1
    [[ -f $LAB_STATE/owns-lab && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで、未breakの状態で実行します。'; return 1; }
    [[ ! -e $LY_APT && ! -e $LY_UMASK ]] || { echo '対象ドロップインが既にあります。resetからやり直します。'; return 1; }
    if [[ -e $LY_ISSUE ]]; then cp -p -- "$LY_ISSUE" "$LAB_STATE/issue.net.orig"; touch "$LAB_STATE/issue.existed"; fi
    touch "$LAB_STATE/banner-saved"
    _ly_run "$LAB_STATE/baseline.dat" "$LAB_STATE/baseline.log" || return 1
    _ly_summary "$LAB_STATE/baseline.dat" > "$LAB_STATE/baseline.json" || return 1
    python3 - "$LAB_STATE/baseline.json" "$LY_TARGETS_ALLOWED" > "$LAB_STATE/targets.txt" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
print(' '.join(t for t in sys.argv[2].split() if t in b['suggestions']))
PY
    cat >> "$LAB_STATE/TASKS.txt" <<TASK

--- 基準値(break時に記録) ---
hardening_index: $(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['index'])" "$LAB_STATE/baseline.json")
suggestion から消すべきテストID(このVMで該当するもの): $(cat "$LAB_STATE/targets.txt")  (空の場合は対応済みで、ID判定は行わない)
TASK
    touch "$LAB_STATE/fault"
    echo "基準を記録しました。対象ID: $(cat "$LAB_STATE/targets.txt")。TASKS.txt を確認してください。"
}

lab_check() {
    _ly_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/baseline.json && -f $LAB_STATE/owns-lab ]] || { echo 'まず break で基準を記録します。'; return 1; }
    _ly_check_apt || return 1
    _ly_check_banner || return 1
    _ly_check_umask || return 1
    _ly_run "$LAB_STATE/after.dat" "$LAB_STATE/after.log" || return 1
    _ly_summary "$LAB_STATE/after.dat" > "$LAB_STATE/after.json" || return 1
    _ly_compare "$LAB_STATE/baseline.json" "$LAB_STATE/after.json" "$(cat "$LAB_STATE/targets.txt")" || return 1
    echo 'PASS: 3項目の実効値とlynis再実行(指標+1以上・新規warningなし・対象テストIDがsuggestionから消えた)を確認しました。'
}

lab_reset() {
    _ly_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    rm -f -- "$LY_APT" "$LY_UMASK"
    if [[ -f $LAB_STATE/banner-saved ]]; then
        if [[ -f $LAB_STATE/issue.existed ]]; then cp -p -- "$LAB_STATE/issue.net.orig" "$LY_ISSUE"; else rm -f -- "$LY_ISSUE"; fi
    fi
    local f
    for f in owns-lab fault banner-saved issue.existed issue.net.orig baseline.dat baseline.log baseline.json after.dat after.log after.json targets.txt lynis-stdout.txt TASKS.txt; do
        rm -f -- "${LAB_STATE:?}/${f:?}"
    done
    echo '専用ドロップインを削除し、/etc/issue.net を元に戻しました。unattended-upgrades/lynis パッケージは残します。'
}
