# title: journaldの永続化・容量制御・journalctl絞り込み
# roles: app
# Drop-in only (/etc/systemd/journald.conf.d/50-dojo.conf). The main journald.conf is never edited.

_jd_paths() {
    [[ ${LAB_ID:-} == journald && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/journald ]] || { echo 'journald: unexpected lab context' >&2; return 1; }
    JD_DIR=/etc/systemd/journald.conf.d
    JD_DROPIN=$JD_DIR/50-dojo.conf
    JD_WORK=/home/ubuntu/dojo-journald
    JD_TAG=dojo-j
    JD_FAULT_MARK='# dojo-journald fault'
    [[ ! -L $JD_DIR && ! -L $JD_DROPIN && ! -L $JD_WORK ]] || return 1
}

# Judge the effective configuration (systemd-analyze cat-config) and the running journald.
_jd_effective() {
    [[ -f $JD_DROPIN && ! -L $JD_DROPIN ]] || { echo "$JD_DROPIN を作成します（本体のjournald.confは編集しない）。"; return 1; }
    ! grep -qF "$JD_FAULT_MARK" "$JD_DROPIN" || { echo '故障版の設定が残っています。'; return 1; }
    [[ $(sha256sum /etc/systemd/journald.conf | cut -d ' ' -f 1) == $(cat "$LAB_STATE/main.sha256") ]] || { echo '本体のjournald.confは変更せずdrop-inで設定します。'; return 1; }
    local eff fs_bytes
    eff=$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null) || return 1
    fs_bytes=$(df -B1 --output=size /var/log | tail -n 1 | tr -d ' ')
    python3 - "$JD_DROPIN" "$fs_bytes" "$eff" <<'PY' || return 1
import re, sys
path, fs, eff = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    # 1. drop-in syntax: journald silently ignores malformed lines
    section = None
    for n, raw in enumerate(open(path).read().splitlines(), 1):
        s = raw.strip()
        if not s or s[0] in '#;':
            continue
        if s.startswith('['):
            assert s.endswith(']'), f'{n}行目: セクション行が不正'
            section = s
            continue
        assert section == '[Journal]', f'{n}行目: [Journal]セクションの外です'
        assert '=' in s, f'{n}行目: Key=Value形式ではないためjournaldに無視されます'
    # 2. effective values (later files / lines win)
    vals, sec = {}, None
    for raw in eff.splitlines():
        s = raw.strip()
        if not s or s[0] in '#;':
            continue
        if s.startswith('['):
            sec = s
        elif sec == '[Journal]' and '=' in s:
            k, v = s.split('=', 1)
            vals[k.strip()] = v.strip()
    assert vals.get('Storage') == 'persistent', 'Storage=persistent が実効値になっていません'
    m = re.fullmatch(r'(\d+)\s*([KMGT]?)', vals.get('SystemMaxUse', ''))
    assert m, 'SystemMaxUseが未設定か書式が不正です'
    smax = int(m[1]) * {'': 1, 'K': 1 << 10, 'M': 1 << 20, 'G': 1 << 30, 'T': 1 << 40}[m[2]]
    assert 16 << 20 <= smax <= 1 << 30, 'SystemMaxUseは16M以上1G以下にします'
    assert smax <= fs // 2, 'SystemMaxUseが/var/logの容量の半分を超えています'
    units = {'': 1, 's': 1, 'sec': 1, 'm': 60, 'min': 60, 'h': 3600, 'hour': 3600, 'd': 86400, 'day': 86400,
             'w': 604800, 'week': 604800, 'month': 2629800, 'y': 31557600, 'year': 31557600}
    rest = vals.get('MaxRetentionSec', '')
    assert rest, 'MaxRetentionSecが未設定です'
    assert re.fullmatch(r'(\s*\d+\s*[a-z]*)+', rest), 'MaxRetentionSecの書式が不正です'
    total = 0
    for num, unit in re.findall(r'(\d+)\s*([a-z]*)', rest):
        assert unit in units, 'MaxRetentionSecの単位が不正です'
        total += int(num) * units[unit]
    assert 86400 <= total <= 365 * 86400, 'MaxRetentionSecは1日以上1年以下にします'
except AssertionError as exc:
    print(exc)
    sys.exit(1)
PY
    # 3. journald must have been restarted after the drop-in was written
    local started
    started=$(date -d "$(systemctl show -P ExecMainStartTimestamp systemd-journald.service)" +%s 2>/dev/null) || return 1
    (( started >= $(stat -c %Y "$JD_DROPIN") )) || { echo '設定後にsystemd-journaldを再起動していません。'; return 1; }
}

lab_setup() {
    _jd_paths || return 1
    [[ ! -e $JD_DROPIN && ! -e $JD_WORK && ! -e $LAB_STATE/token ]] || { echo '既に構成があります。resetせず上書きしません。'; return 1; }
    getent passwd ubuntu >/dev/null && command -v logger >/dev/null && command -v systemd-analyze >/dev/null || return 1
    local token err crit warn=2 info=3 i
    token=$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')  # no tr|head pipe: SIGPIPE + pipefail aborts setup
    err=$((2 + RANDOM % 3)); crit=$((1 + RANDOM % 2))
    sha256sum /etc/systemd/journald.conf | cut -d ' ' -f 1 > "$LAB_STATE/main.sha256"
    printf '%s\n' "$token" > "$LAB_STATE/token"
    for ((i = 0; i < err; i++)); do logger -t "$JD_TAG" -p user.err "$token err-$i"; done
    for ((i = 0; i < crit; i++)); do logger -t "$JD_TAG" -p user.crit "$token crit-$i"; done
    for ((i = 0; i < warn; i++)); do logger -t "$JD_TAG" -p user.warning "$token warn-$i"; done
    for ((i = 0; i < info; i++)); do logger -t "$JD_TAG" -p user.info "$token info-$i"; done
    # noise under another tag: must not be counted
    logger -t dojo-other -p user.err "$token other-tag-noise"
    printf '%s\n' "$((err + crit))" > "$LAB_STATE/expect-err"
    printf '%s\n' "$((err + crit + warn + info))" > "$LAB_STATE/expect-total"
    install -d -o ubuntu -g ubuntu -m 0755 "$JD_WORK"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
journald永続化・容量制御（app VM。root権限が要る操作はsudo）
識別トークン: $token  （タグ $JD_TAG と dojo-other のテスト行に含まれています）
1. 現在の実効設定とジャーナルの場所を確認: systemd-analyze cat-config systemd/journald.conf / ls /var/log/journal /run/log/journal
   本体 /etc/systemd/journald.conf は編集しない。/etc/systemd/journald.conf.d/50-dojo.conf を作る。
2. drop-inの [Journal] に Storage=persistent、SystemMaxUse（現実的な上限）、MaxRetentionSec（保持期間）を書く。
   /var/log/journal を安全な所有者・権限（systemd-journal グループ、他者書込不可）で用意する。詳細は man journald.conf。
3. systemd-journald を再起動（必要なら journalctl --flush）。journalctl --disk-usage で使用量を確認。
4. 絞り込み練習: journalctl -t $JD_TAG / -p err / --since '-1h' / -u systemd-journald / -o json
   自分でも logger -t $JD_TAG で行を追加してみる。
5. 回答: $JD_WORK/answer.txt に2行書く（実際のジャーナルで検証される）
   err=<トークン付き・タグ $JD_TAG・priority が err 以上(0〜3)の件数>
   total=<トークン付き・タグ $JD_TAG の全件数>
6. sudo dojo-vm-lab journald break の後、設定を直して sudo dojo-vm-lab journald check
   （checkはjournalctl --rotateを実行し、ローテート後もトークン行が残るか確認します）
7. sudo dojo-vm-lab journald reset （drop-inと専用状態のみ削除。ジャーナル本体は消さない）
注意: --vacuum-size を極端に小さくするとトークン行も消えます。その場合はresetしてsetupし直す。
TASK
    cp "$LAB_STATE/TASKS.txt" "$JD_WORK/TASKS.txt"; chown ubuntu:ubuntu "$JD_WORK/TASKS.txt"
    echo "手順: $LAB_STATE/TASKS.txt （写し: $JD_WORK/TASKS.txt）"
}

lab_break() {
    _jd_paths || return 1
    [[ -f $LAB_STATE/token ]] || { echo '先にsetupしてください。'; return 1; }
    _jd_effective || { echo 'まず正しい設定を完成させ、再起動してからbreakします。'; return 1; }
    cat > "$JD_DROPIN" <<CONF
$JD_FAULT_MARK
[Journal]
Storage=volatile
SystemMaxUse=64G
MaxRetentionSec 1week
CONF
    touch "$LAB_STATE/fault"
    systemctl restart systemd-journald.service
    echo '設定が壊れました（永続化されない・上限が不適切・構文エラー）。実効設定を調べて直してください。'
}

lab_check() {
    _jd_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/token ]] || { echo 'まずbreakで障害を作ります。'; return 1; }
    _jd_effective || return 1
    local mid token jdir mode
    mid=$(cat /etc/machine-id); token=$(cat "$LAB_STATE/token"); jdir=/var/log/journal/$mid
    [[ -d $jdir && ! -L $jdir && -f $jdir/system.journal ]] || { echo "$jdir と system.journal がありません。"; return 1; }
    mode=$(stat -c %a "$jdir")
    [[ $(stat -c %G /var/log/journal) == systemd-journal && $(stat -c %G "$jdir") == systemd-journal && $(stat -c %U "$jdir") == root ]] \
        && (( (8#$mode & 8#002) == 0 )) || { echo '/var/log/journal の所有グループ(systemd-journal)と権限を確認します。'; return 1; }
    journalctl --disk-usage >/dev/null || return 1
    # prove new entries really land in persistent storage
    # probe must NOT contain the token, or repeated checks would inflate the learner-visible counts
    local probe="dojo-probe-$RANDOM$RANDOM"
    logger -t "$JD_TAG" -p user.info "$probe"
    journalctl --sync
    journalctl --directory="$jdir" -t "$JD_TAG" -o cat | grep -qF "$probe" || { echo '新しいログが永続ジャーナルに書かれていません。'; return 1; }
    journalctl --rotate
    local err total
    read -r err total < <(journalctl --directory="$jdir" -t "$JD_TAG" -o json | python3 -c '
import json, sys
tok = open(sys.argv[1]).read().strip()
err = total = 0
for line in sys.stdin:
    e = json.loads(line)
    m = e.get("MESSAGE")
    if not isinstance(m, str) or tok not in m:
        continue
    total += 1
    err += int(e.get("PRIORITY", 6)) <= 3
print(err, total)' "$LAB_STATE/token")
    [[ $err == "$(cat "$LAB_STATE/expect-err")" && $total == "$(cat "$LAB_STATE/expect-total")" ]] \
        || { echo 'ローテート後にトークン行が失われています（vacuumのしすぎ等）。resetしてsetupし直してください。'; return 1; }
    local ans=$JD_WORK/answer.txt norm
    [[ -f $ans && ! -L $ans ]] || { echo "$ans に err=N と total=N を書いてください。"; return 1; }
    norm=$(head -c 200 "$ans" | tr -d ' \r')
    [[ $(grep -cx "err=$err" <<<"$norm") == 1 && $(grep -cx "total=$total" <<<"$norm") == 1 ]] \
        || { echo '回答が実際のジャーナルの件数と一致しません。-t と -p と -o json で数え直します。'; return 1; }
    echo 'PASS: 実効設定・永続保存・ローテート後の保持・絞り込み集計を確認しました。'
}

lab_reset() {
    _jd_paths || return 1
    [[ -f $LAB_STATE/token ]] || { echo '専用状態がありません。何も削除しません。'; return 1; }
    rm -f -- "${JD_DROPIN:?}"
    rmdir --ignore-fail-on-non-empty "${JD_DIR:?}" 2>/dev/null || true
    if [[ -d $JD_WORK ]]; then
        rm -f -- "${JD_WORK:?}/TASKS.txt" "${JD_WORK:?}/answer.txt"
        rmdir --ignore-fail-on-non-empty "$JD_WORK"
    fi
    local f
    for f in token fault main.sha256 expect-err expect-total TASKS.txt; do rm -f -- "${LAB_STATE:?}/$f"; done
    systemctl restart systemd-journald.service
    echo 'drop-inと専用状態を削除しました。ジャーナル本体と本体設定は変更していません。'
}
