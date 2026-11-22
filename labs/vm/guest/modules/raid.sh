# title: mdadmソフトウェアRAID1（ループバック）: 障害・交換・再同期・設定永続化
# roles: app
# Guest-only. Every member is a sparse file under the lab state dir attached with losetup. Never touches real disks or the root fs.
# Dispatcher-guarded. No device argument is ever accepted; only lab loop devices are ever passed to mdadm/mkfs.

_raid_paths() {
    [[ ${LAB_ID:-} == raid && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/raid ]] || { echo 'raid: unexpected lab context' >&2; return 1; }
    RAID_NAME=dojo0
    RAID_MD=/dev/md/dojo0
    RAID_MNT="$LAB_STATE/mnt"
    RAID_IMGS=(disk-a.img disk-b.img disk-c.img)
    RAID_CONF=/etc/mdadm/mdadm.conf
    RAID_BEGIN='# BEGIN linuxdojo-raid (LinuxDOJO lab block; safe to remove)'
    RAID_END='# END linuxdojo-raid'
    [[ ! -L $LAB_STATE && ! -L $RAID_MNT ]] || { echo 'raid: symbolic paths rejected' >&2; return 1; }
    local i
    for i in "${RAID_IMGS[@]}"; do [[ ! -L $LAB_STATE/$i ]] || { echo 'raid: symbolic paths rejected' >&2; return 1; }; done
}

_raid_tools() {
    local t missing=0
    for t in mdadm losetup mkfs.ext4 findmnt sha256sum; do
        command -v "$t" >/dev/null 2>&1 || missing=1
    done
    (( missing == 0 )) || { echo 'raid: mdadm が未導入です。次を実行してから再試行してください: sudo apt install -y mdadm' >&2; return 1; }
}

# $1 = /dev/loopN. True only if it is backed by one of this lab's image files.
_raid_is_lab_loop() {
    local dev=$1 back i
    [[ $dev =~ ^/dev/loop[0-9]+$ ]] || return 1
    back="$(losetup --noheadings --output BACK-FILE "$dev" 2>/dev/null)" || return 1
    back="$(readlink -f -- "$back" 2>/dev/null)" || return 1
    for i in "${RAID_IMGS[@]}"; do [[ $back == "$LAB_STATE/$i" ]] && return 0; done
    return 1
}

# $1 = image name. Prints attached loop devices for it.
_raid_loops_of() { losetup --associated "$LAB_STATE/$1" --noheadings --output NAME 2>/dev/null || true; }

# Prints member devices (any state) of the lab array, one per line.
_raid_members() {
    mdadm --detail "$RAID_MD" 2>/dev/null | awk '$1 ~ /^[0-9-]+$/ && $NF ~ /^\/dev\// {print $NF}'
}

_raid_md_real() { readlink -f -- "$RAID_MD"; }

_raid_detail_field() { # $1 label
    mdadm --detail "$RAID_MD" 2>/dev/null | sed -n "s/^ *$1 *: *//p" | head -n 1
}

_raid_members_all_lab() {
    local m n=0
    while read -r m; do
        [[ -n $m ]] || continue
        _raid_is_lab_loop "$m" || return 1
        n=$((n+1))
    done < <(_raid_members)
    (( n > 0 ))
}

_raid_conf_block() { # prints lines strictly between markers
    [[ -f $RAID_CONF ]] || return 0
    awk -v b="$RAID_BEGIN" -v e="$RAID_END" '$0==e{f=0} f{print} $0==b{f=1}' "$RAID_CONF"
}

_raid_conf_markers_ok() {
    [[ -f $RAID_CONF ]] || return 1
    [[ $(grep -cxF -- "$RAID_BEGIN" "$RAID_CONF") -eq 1 && $(grep -cxF -- "$RAID_END" "$RAID_CONF") -eq 1 ]] || return 1
    local bl el
    bl="$(grep -nxF -- "$RAID_BEGIN" "$RAID_CONF" | cut -d: -f1)"
    el="$(grep -nxF -- "$RAID_END" "$RAID_CONF" | cut -d: -f1)"
    (( bl < el ))
}

_raid_write_tasks() {
    local a b c
    a="$(_raid_loops_of disk-a.img | head -n1)"; b="$(_raid_loops_of disk-b.img | head -n1)"; c="$(_raid_loops_of disk-c.img | head -n1)"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
LinuxDOJO RAID実習 (すべて教材用ループデバイス。実ディスクとルート領域には触れません)
  メンバーA: $a   メンバーB: $b   交換用: $c   マウント先: $RAID_MNT
1. RAID1を作成する。名前は --name=$RAID_NAME 、デバイスは $RAID_MD 。A と B だけを使う
   (mdadm --create ... --level=1 --raid-devices=2)。既存のmdは再利用しない。
2. cat /proc/mdstat と mdadm --detail $RAID_MD で初期同期を観察する
3. $RAID_MD にext4を作成し $RAID_MNT へマウントする
4. $RAID_MNT/data.bin へ数MBのデータを書き、sha256sum を控える (sync も忘れずに)
5. dojo-vm-lab raid break  -> メンバーが1本故障して縮退 (degraded) します
6. 縮退を mdadm --detail で確認し、故障メンバーを --remove で外す
7. 交換用 $c を --add し、/proc/mdstat で再同期(recovery)が終わるまで観察する
8. データのsha256が変わっていないことを確認する
9. $LAB_STATE/answers.txt を埋める (RAID5/RAID10の知識。調べて数値を書く)
10. 設定を永続化する: 次のマーカー行で囲んだブロックだけに mdadm --detail --scan の ARRAY 行を入れる
      $RAID_BEGIN
      ARRAY ...
      $RAID_END
    ($RAID_CONF の他の行は変更しない。update-initramfs は実習では実行しない。なぜ通常は必要かを answers.txt に書く)
11. dojo-vm-lab raid check
reset は教材のarray・ループ・マーカーブロックだけを片付けます。
TASK
}

lab_setup() {
    _raid_paths
    _raid_tools
    local i
    for i in "${RAID_IMGS[@]}"; do
        [[ ! -e $LAB_STATE/$i ]] || { echo 'raid: already configured; use reset first' >&2; return 1; }
    done
    [[ ! -e $RAID_MD ]] || { echo "raid: $RAID_MD が既に存在します。既存のmdは再利用しません" >&2; return 1; }
    if mdadm --detail --scan 2>/dev/null | grep -qE "(/dev/md/$RAID_NAME|name=[^ ]*:$RAID_NAME)( |\$)"; then
        echo "raid: 名前 $RAID_NAME のmdが既に存在します" >&2; return 1
    fi
    mkdir -p "$RAID_MNT"
    local dev
    for i in "${RAID_IMGS[@]}"; do
        truncate -s 128M "$LAB_STATE/$i"
        chmod 600 "$LAB_STATE/$i"
        [[ -f $LAB_STATE/$i && ! -b $LAB_STATE/$i ]] || return 1
        dev="$(losetup --find --show "$LAB_STATE/$i")" || { echo 'raid: losetup failed' >&2; return 1; }
        _raid_is_lab_loop "$dev" || { echo 'raid: unexpected loop mapping' >&2; return 1; }
    done
    cat > "$LAB_STATE/answers.txt" <<'ANS'
# 数値だけを書く。調べて埋める。
raid5_min_disks=
raid10_min_disks=
raid5_usable_disks_of_4=
raid5_survives_failures=
raid1_survives_failures_of_2=
initramfs_command=
ANS
    _raid_write_tasks
    printf '実習手順: %s/TASKS.txt\n準備完了。手順1から始めてください。\n' "$LAB_STATE"
}

lab_break() {
    _raid_paths
    _raid_tools
    [[ -f $LAB_STATE/disk-a.img && -f $LAB_STATE/disk-b.img && -f $LAB_STATE/disk-c.img ]] || { echo 'raid: 先に setup を実行してください。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo 'raid: 既に故障済みです。reset してやり直してください。'; return 1; }
    [[ -e $RAID_MD ]] || { echo "raid: $RAID_MD がありません。手順1-4を先に完了してください。"; return 1; }
    _raid_members_all_lab || { echo 'raid: 教材ループ以外のメンバーが含まれます。中止します。'; return 1; }
    local md; md="$(_raid_md_real)"
    [[ $(findmnt -rn -M "$RAID_MNT" -o SOURCE 2>/dev/null) == "$md" ]] || { echo "raid: $RAID_MNT に $RAID_MD がマウントされていません。"; return 1; }
    [[ -s $RAID_MNT/data.bin ]] || { echo "raid: $RAID_MNT/data.bin を書いてください。"; return 1; }
    [[ $(_raid_detail_field 'Active Devices') == 2 && $(_raid_detail_field 'Failed Devices') == 0 ]] || { echo 'raid: まず健全な2台構成にしてください。'; return 1; }
    if mdadm --detail "$RAID_MD" | grep -Eq 'resync|recovering'; then echo 'raid: 初期同期の完了後に実行してください。'; return 1; fi
    sync
    sha256sum "$RAID_MNT/data.bin" | cut -d' ' -f1 > "$LAB_STATE/data.sha256"
    local victim dev
    victim=disk-b.img
    dev="$(_raid_loops_of "$victim" | head -n1)"
    _raid_members | grep -qxF "$dev" || { victim=disk-a.img; dev="$(_raid_loops_of "$victim" | head -n1)"; }
    _raid_members | grep -qxF "$dev" || { echo 'raid: 故障させるメンバーが見つかりません。'; return 1; }
    mdadm "$RAID_MD" --fail "$dev" >/dev/null
    printf '%s\n' "$victim" > "$LAB_STATE/failed"
    printf 'member-failed\n' > "$LAB_STATE/fault"
    printf 'メンバー %s が故障しました。arrayは縮退(degraded)です。\ndata.bin はまだ読めるはずです。mdadm --detail と /proc/mdstat で状況を調べ、手順6から復旧してください。\n' "$dev"
}

_raid_ans() { sed -n "s/^$1=//p" "$LAB_STATE/answers.txt" | head -n1 | tr -d ' \r'; }

_raid_check_answers() {
    [[ -f $LAB_STATE/answers.txt ]] || { echo 'answers.txt がありません。'; return 1; }
    [[ $(_raid_ans raid5_min_disks) == 3 ]] || { echo 'answers.txt: raid5_min_disks が違います。'; return 1; }
    [[ $(_raid_ans raid10_min_disks) == 4 ]] || { echo 'answers.txt: raid10_min_disks が違います。'; return 1; }
    [[ $(_raid_ans raid5_usable_disks_of_4) == 3 ]] || { echo 'answers.txt: raid5_usable_disks_of_4 が違います。'; return 1; }
    [[ $(_raid_ans raid5_survives_failures) == 1 ]] || { echo 'answers.txt: raid5_survives_failures が違います。'; return 1; }
    [[ $(_raid_ans raid1_survives_failures_of_2) == 1 ]] || { echo 'answers.txt: raid1_survives_failures_of_2 が違います。'; return 1; }
    [[ $(sed -n 's/^initramfs_command=//p' "$LAB_STATE/answers.txt" | head -n1) =~ ^[[:space:]]*(sudo[[:space:]]+)?update-initramfs([[:space:]]+-u)?[[:space:]]*$ ]] || { echo 'answers.txt: initramfs_command (起動時にarrayを認識させる更新コマンド)を書いてください。'; return 1; }
}

_raid_check_conf() {
    _raid_conf_markers_ok || { echo "$RAID_CONF に所定のマーカーブロックが1組ありません。"; return 1; }
    local uuid lines
    uuid="$(_raid_detail_field 'UUID')"
    [[ -n $uuid ]] || return 1
    lines="$(_raid_conf_block | grep -E '^[[:space:]]*ARRAY' || true)"
    [[ $(printf '%s\n' "$lines" | grep -c .) -eq 1 ]] || { echo 'マーカーブロック内のARRAY行は1行だけにしてください。'; return 1; }
    [[ $lines == *"UUID=$uuid"* ]] || { echo 'ARRAY行のUUIDが実際のarrayと一致しません。mdadm --detail --scan の出力を使ってください。'; return 1; }
    [[ $lines == *"$RAID_NAME"* ]] || { echo "ARRAY行に $RAID_NAME が含まれていません。"; return 1; }
}

lab_check() {
    _raid_paths
    _raid_tools
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/failed && -f $LAB_STATE/data.sha256 ]] || { echo '先にbreakで故障を発生させてください。'; return 1; }
    [[ -e $RAID_MD ]] || { echo "$RAID_MD がありません。"; return 1; }
    local md state level failed_img m n=0 have_c=0 back
    md="$(_raid_md_real)"
    failed_img="$(cat "$LAB_STATE/failed")"
    local name; name="$(_raid_detail_field 'Name')"
    [[ $name == *":$RAID_NAME"* || $name == "$RAID_NAME"* ]] || { echo "arrayの名前が $RAID_NAME ではありません。"; return 1; }
    level="$(_raid_detail_field 'Raid Level')"
    [[ $level == raid1 ]] || { echo 'RAID1ではありません。'; return 1; }
    state="$(_raid_detail_field 'State')"
    if ! [[ $state =~ (^|, )(clean|active)(,|$) ]] || [[ $state =~ degraded|resync|recover|check|repair|FAILED ]]; then
        echo "arrayが健全ではありません (State: $state)。"; return 1
    fi
    [[ $(_raid_detail_field 'Active Devices') == 2 && $(_raid_detail_field 'Working Devices') == 2 && $(_raid_detail_field 'Failed Devices') == 0 && $(_raid_detail_field 'Spare Devices') == 0 ]] || { echo '稼働2台・故障0・スペア0になっていません。'; return 1; }
    while read -r m; do
        [[ -n $m ]] || continue
        _raid_is_lab_loop "$m" || { echo "教材ループ以外のメンバー $m があります。"; return 1; }
        n=$((n+1))
        back="$(losetup --noheadings --output BACK-FILE "$m")"
        [[ $back == */disk-c.img ]] && have_c=1
        if [[ $back == */"$failed_img" ]]; then echo '故障したメンバーがまだ構成に残っています。'; return 1; fi
    done < <(_raid_members)
    (( n == 2 )) || { echo 'メンバー数が2ではありません。'; return 1; }
    (( have_c == 1 )) || { echo '交換用メンバー(disk-c)が参加していません。'; return 1; }
    [[ $(mdadm --detail "$RAID_MD" | grep -c 'active sync') -eq 2 ]] || { echo '2台とも active sync になっていません。再同期の完了を待ってください。'; return 1; }
    if grep -Eq '(resync|recovery|reshape|check) *=' /proc/mdstat; then echo '/proc/mdstat に再同期が進行中です。完了を待ってください。'; return 1; fi
    [[ $(findmnt -rn -M "$RAID_MNT" -o SOURCE 2>/dev/null) == "$md" && $(findmnt -rn -M "$RAID_MNT" -o FSTYPE) == ext4 ]] || { echo "$RAID_MNT に $RAID_MD のext4がマウントされていません。"; return 1; }
    [[ -f $RAID_MNT/data.bin && $(sha256sum "$RAID_MNT/data.bin" | cut -d' ' -f1) == "$(cat "$LAB_STATE/data.sha256")" ]] || { echo 'data.bin のチェックサムが一致しません。'; return 1; }
    _raid_check_answers || return 1
    _raid_check_conf || return 1
    echo '達成: 故障メンバーを交換して再同期を完了し、データと設定ブロックを確認しました。(update-initramfs は実習では未実行)'
}

lab_reset() {
    _raid_paths
    local i dev h md s ok
    # Stop whichever md array holds a lab loop (any name), but only if ALL its slaves are lab loops.
    for i in "${RAID_IMGS[@]}"; do
        while read -r dev; do
            [[ -n $dev ]] || continue
            _raid_is_lab_loop "$dev" || continue
            for h in /sys/block/"${dev#/dev/}"/holders/md*; do
                [[ -e $h ]] || continue
                md="/dev/$(basename "$h")"
                ok=1
                for s in /sys/block/"$(basename "$h")"/slaves/*; do
                    [[ -e $s ]] || continue
                    _raid_is_lab_loop "/dev/$(basename "$s")" || ok=0
                done
                (( ok == 1 )) || { echo "raid: $md に教材外のメンバーがあります。停止しません。" >&2; return 1; }
                if findmnt -rn -S "$md" >/dev/null 2>&1; then
                    [[ $(findmnt -rn -S "$md" -o TARGET | head -n1) == "$RAID_MNT" ]] || { echo "raid: $md は教材外の場所にマウントされています。" >&2; return 1; }
                    umount "$RAID_MNT"
                fi
                mdadm --stop "$md" >/dev/null
            done
        done < <(_raid_loops_of "$i")
    done
    if mountpoint -q "$RAID_MNT" 2>/dev/null; then
        echo 'raid: マウントが残っているため中止します。' >&2; return 1
    fi
    for i in "${RAID_IMGS[@]}"; do
        while read -r dev; do
            [[ -n $dev ]] || continue
            _raid_is_lab_loop "$dev" || return 1
            mdadm --zero-superblock "$dev" >/dev/null 2>&1 || true
            losetup --detach "$dev"
        done < <(_raid_loops_of "$i")
        rm -f -- "${LAB_STATE:?}/${i:?}"
    done
    if [[ -f $RAID_CONF ]] && grep -qxF -- "$RAID_BEGIN" "$RAID_CONF"; then
        _raid_conf_markers_ok || { echo "raid: $RAID_CONF のマーカーが不正です。手動で確認してください。" >&2; return 1; }
        local bl el
        bl="$(grep -nxF -- "$RAID_BEGIN" "$RAID_CONF" | cut -d: -f1)"
        el="$(grep -nxF -- "$RAID_END" "$RAID_CONF" | cut -d: -f1)"
        sed -i "${bl},${el}d" "$RAID_CONF"
    fi
    rm -f -- "${LAB_STATE:?}/fault" "${LAB_STATE:?}/failed" "${LAB_STATE:?}/data.sha256" "${LAB_STATE:?}/TASKS.txt" "${LAB_STATE:?}/answers.txt"
    rmdir -- "$RAID_MNT" 2>/dev/null || true
    echo '教材のarray・ループ・設定ブロックを片付けました。setupから再開できます。'
}
