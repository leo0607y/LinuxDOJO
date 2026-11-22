# title: Btrfs（ループバック）: サブボリューム・スナップショット・send/receive・ロールバック
# roles: app
# Guest-only. Two sparse images under the lab state dir, attached with losetup. Never touches real disks or the root fs.

_bt_paths() {
    [[ ${LAB_ID:-} == btrfs && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/btrfs ]] || { echo 'btrfs: unexpected lab context' >&2; return 1; }
    BT_A_IMG="$LAB_STATE/fs-a.img"
    BT_B_IMG="$LAB_STATE/fs-b.img"
    BT_A="$LAB_STATE/mnt/a"
    BT_B="$LAB_STATE/mnt/b"
    [[ ! -L $LAB_STATE && ! -L $BT_A_IMG && ! -L $BT_B_IMG && ! -L $LAB_STATE/mnt && ! -L $BT_A && ! -L $BT_B ]] || { echo 'btrfs: symbolic paths rejected' >&2; return 1; }
}

_bt_tools() {
    local t missing=0
    for t in btrfs mkfs.btrfs losetup findmnt sha256sum diff; do
        command -v "$t" >/dev/null 2>&1 || missing=1
    done
    (( missing == 0 )) || { echo 'btrfs: btrfs-progs が未導入です。次を実行してから再試行してください: sudo apt install -y btrfs-progs' >&2; return 1; }
}

# $1 = /dev/loopN backed by one of this lab's images
_bt_is_lab_loop() {
    local back
    [[ $1 =~ ^/dev/loop[0-9]+$ ]] || return 1
    back="$(losetup --noheadings --output BACK-FILE "$1" 2>/dev/null)" || return 1
    back="$(readlink -f -- "$back" 2>/dev/null)" || return 1
    [[ $back == "$BT_A_IMG" || $back == "$BT_B_IMG" ]]
}

# $1 = mountpoint, $2 = image. True if mounted from a loop device backed by that image.
_bt_mount_ok() {
    local src
    src="$(findmnt -rn -M "$1" -o SOURCE 2>/dev/null)" || return 1
    src="${src%%\[*}"
    _bt_is_lab_loop "$src" || return 1
    [[ $(readlink -f -- "$(losetup --noheadings --output BACK-FILE "$src")") == "$2" ]] &&
        [[ $(findmnt -rn -M "$1" -o FSTYPE) == btrfs ]]
}

# Deterministic content hash of a directory tree (names + contents).
_bt_tree_hash() {
    ( cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum | sha256sum | cut -d' ' -f1 )
}

_bt_subvol_field() { # $1 path, $2 label
    btrfs subvolume show "$1" 2>/dev/null | sed -n "s/^[[:space:]]*$2:[[:space:]]*//p" | head -n1
}

_bt_is_subvol() { btrfs subvolume show "$1" >/dev/null 2>&1; }
_bt_is_ro() { [[ $(btrfs property get -ts "$1" ro 2>/dev/null) == 'ro=true' ]]; }

lab_setup() {
    _bt_paths
    _bt_tools
    [[ ! -e $BT_A_IMG && ! -e $BT_B_IMG ]] || { echo 'btrfs: already configured; use reset first' >&2; return 1; }
    mkdir -p "$BT_A" "$BT_B"
    local img dev
    for img in "$BT_A_IMG" "$BT_B_IMG"; do
        truncate -s 256M "$img"
        chmod 600 "$img"
        [[ -f $img && ! -b $img ]] || return 1
        dev="$(losetup --find --show "$img")" || { echo 'btrfs: losetup failed' >&2; return 1; }
        _bt_is_lab_loop "$dev" || { echo 'btrfs: unexpected loop mapping' >&2; return 1; }
        # Sole mkfs target: the loop device just attached to a lab image.
        mkfs.btrfs -q -f -L "dojo-$(basename "$img" .img)" "$dev"
        if [[ $img == "$BT_A_IMG" ]]; then mount "$dev" "$BT_A"; else mount "$dev" "$BT_B"; fi
    done
    _bt_mount_ok "$BT_A" "$BT_A_IMG" && _bt_mount_ok "$BT_B" "$BT_B_IMG" || { echo 'btrfs: mount verification failed' >&2; return 1; }
    btrfs subvolume create "$BT_A/data" >/dev/null
    mkdir -p "$BT_A/snaps" "$BT_A/data/config"
    seq 1 20000 > "$BT_A/data/report.txt"
    printf 'mode=production\nretries=3\n' > "$BT_A/data/config/app.conf"
    yes 'LinuxDOJO compressible line' | head -n 40000 > "$BT_A/data/blob.txt"
    sync
    cat > "$LAB_STATE/TASKS.txt" <<TASK
LinuxDOJO Btrfs実習 (教材用ループのみ。ルート領域には触れません)
  ファイルシステムA: $BT_A  (サブボリューム data / スナップショット置き場 snaps)
  ファイルシステムB: $BT_B  (send/receiveの受け先)
1. btrfs filesystem show / btrfs filesystem usage $BT_A / btrfs filesystem df $BT_A で構成を確認
2. subvolume list で data がサブボリュームであることを確認
3. 読み取り専用スナップショット snaps/base を作る (-r)。書き込み可能との違いを確認
4. 全体を B へ send | receive する (btrfs send ... | btrfs receive $BT_B)
5. data に inc.txt を追加し、読み取り専用の snaps/inc を作る
6. base を親にした差分送信 (btrfs send -p) で inc を B へ送る。B側で base/inc が揃い、diff -r で一致することを確認
7. A を圧縮オプション付きでremountする (compress=zstd)。findmnt で確認
8. btrfs scrub start -B $BT_A を実行し scrub status を確認
9. クォータを有効化し (quota enable)、qgroup show を見る
10. dojo-vm-lab btrfs break  -> data が壊れます。壊れた後にもスナップショットが1つ取られます
11. snaps/ 内のどれが「壊れる前の正しい状態」かを中身で判断し、data をそのスナップショットから書き込み可能な
    サブボリュームとして復元する (壊れた data は削除してよい)
12. 復元データを sha256 で確認し、dojo-vm-lab btrfs check
reset は教材のloopマウントとimageだけを片付けます。
TASK
    printf '実習手順: %s/TASKS.txt\n準備完了。手順1から始めてください。\n' "$LAB_STATE"
}

# Verifies the send/receive part of the course; prints a reason and returns 1 when wrong.
_bt_check_replica() {
    local base_a=$BT_A/snaps/base inc_a=$BT_A/snaps/inc
    local p
    for p in "$BT_B/base" "$BT_B/inc"; do
        _bt_is_subvol "$p" || { echo "B側に受信済みのサブボリューム $p がありません。"; return 1; }
        _bt_is_ro "$p" || { echo "$p は読み取り専用の受信スナップショットのはずです。"; return 1; }
    done
    [[ $(_bt_subvol_field "$BT_B/inc" 'Received UUID') == "$(_bt_subvol_field "$inc_a" 'UUID')" ]] || { echo 'B側のincはA側のincから受信したものではありません。'; return 1; }
    [[ $(_bt_subvol_field "$BT_B/base" 'Received UUID') == "$(_bt_subvol_field "$base_a" 'UUID')" ]] || { echo 'B側のbaseはA側のbaseから受信したものではありません。'; return 1; }
    [[ $(_bt_subvol_field "$BT_B/inc" 'Parent UUID') == "$(_bt_subvol_field "$BT_B/base" 'UUID')" ]] || { echo 'incが差分送信(-p base)で受信されていません。'; return 1; }
    diff -r "$inc_a" "$BT_B/inc" >/dev/null || { echo 'A側incとB側incの内容が一致しません。'; return 1; }
    [[ $(_bt_tree_hash "$inc_a") == "$(_bt_tree_hash "$BT_B/inc")" ]] || { echo 'incのハッシュが一致しません。'; return 1; }
}

lab_break() {
    _bt_paths
    _bt_tools
    [[ -f $BT_A_IMG && -f $BT_B_IMG ]] || { echo 'btrfs: 先に setup を実行してください。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo 'btrfs: 既に故障済みです。reset してやり直してください。'; return 1; }
    _bt_mount_ok "$BT_A" "$BT_A_IMG" && _bt_mount_ok "$BT_B" "$BT_B_IMG" || { echo 'btrfs: 教材のマウントが正しくありません。'; return 1; }
    local p
    for p in "$BT_A/snaps/base" "$BT_A/snaps/inc"; do
        _bt_is_subvol "$p" && _bt_is_ro "$p" || { echo "btrfs: 読み取り専用スナップショット $p が必要です(手順3-5)。"; return 1; }
    done
    _bt_is_subvol "$BT_A/data" || { echo 'btrfs: data がサブボリュームではありません。'; return 1; }
    [[ -f $BT_A/data/inc.txt ]] || { echo 'btrfs: data/inc.txt がありません (手順5)。'; return 1; }
    local h; h="$(_bt_tree_hash "$BT_A/data")"
    [[ $h == "$(_bt_tree_hash "$BT_A/snaps/inc")" ]] || { echo 'btrfs: data と snaps/inc が一致しません。inc作成後にdataを変更しないでください。'; return 1; }
    _bt_check_replica || return 1
    sync
    printf '%s\n' "$h" > "$LAB_STATE/good.sha256"
    _bt_subvol_field "$BT_A/snaps/inc" 'UUID' > "$LAB_STATE/good.uuid"
    # The damage, then a snapshot of the damaged state.
    rm -f -- "$BT_A/data/report.txt" "$BT_A/data/inc.txt"
    : > "$BT_A/data/config/app.conf"
    printf 'corrupted\n' > "$BT_A/data/blob.txt"
    sync
    btrfs subvolume snapshot -r "$BT_A/data" "$BT_A/snaps/after-damage" >/dev/null
    printf 'data-damaged\n' > "$LAB_STATE/fault"
    printf 'data の内容が失われました。さらに snaps/after-damage が(壊れた後に)作られています。\nsnaps/ の各スナップショットの中身を比べ、正しいものを選んで data を書き込み可能なサブボリュームとして復元してください。\n'
}

lab_check() {
    _bt_paths
    _bt_tools
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/good.sha256 && -f $LAB_STATE/good.uuid ]] || { echo '先にbreakで故障を発生させてください。'; return 1; }
    _bt_mount_ok "$BT_A" "$BT_A_IMG" && _bt_mount_ok "$BT_B" "$BT_B_IMG" || { echo '教材のマウントが正しくありません。'; return 1; }
    local list; list="$(btrfs subvolume list "$BT_A" 2>/dev/null)" || { echo 'subvolume list に失敗しました。'; return 1; }
    local want
    for want in data snaps/base snaps/inc snaps/after-damage; do
        grep -qE " path (<FS_TREE>/)?$want\$" <<<"$list" || { echo "サブボリューム $want が見当たりません。"; return 1; }
    done
    _bt_is_subvol "$BT_A/data" || { echo 'data はサブボリュームである必要があります。'; return 1; }
    ! _bt_is_ro "$BT_A/data" || { echo 'data は書き込み可能にしてください(-r を付けない)。'; return 1; }
    [[ $(_bt_tree_hash "$BT_A/data") == "$(cat "$LAB_STATE/good.sha256")" ]] || { echo 'data の内容が壊れる前の状態と一致しません。別のスナップショットかもしれません。'; return 1; }
    [[ $(_bt_subvol_field "$BT_A/data" 'Parent UUID') == "$(cat "$LAB_STATE/good.uuid")" ]] || { echo 'data が正しいスナップショット(snaps/inc)から作られていません。'; return 1; }
    _bt_is_ro "$BT_A/snaps/inc" || { echo 'snaps/inc が書き換えられています(読み取り専用のままにする)。'; return 1; }
    _bt_check_replica || return 1
    findmnt -rn -M "$BT_A" -o OPTIONS | tr ',' '\n' | grep -qE '^compress(-force)?(=|$)' || { echo "$BT_A が圧縮オプション付きでマウントされていません (findmnt)。"; return 1; }
    btrfs qgroup show "$BT_A" >/dev/null 2>&1 || { echo 'クォータが有効化されていません。'; return 1; }
    local st; st="$(btrfs scrub status "$BT_A" 2>/dev/null)"
    if ! grep -qE 'Status:[[:space:]]+finished' <<<"$st" || ! grep -qE 'Error summary:[[:space:]]+no errors found' <<<"$st"; then
        echo "$BT_A のscrubが完了していません (btrfs scrub status)。"; return 1
    fi
    echo '達成: 正しいスナップショットから復元し、差分send/receive・圧縮・クォータ・scrubを確認しました。'
}

lab_reset() {
    _bt_paths
    local m img dev
    for m in "$BT_A" "$BT_B"; do
        if mountpoint -q "$m" 2>/dev/null; then
            _bt_mount_ok "$m" "$([[ $m == "$BT_A" ]] && echo "$BT_A_IMG" || echo "$BT_B_IMG")" || { echo "btrfs: $m は教材のloopではありません。解除しません。" >&2; return 1; }
            umount "$m"
        fi
    done
    for img in "$BT_A_IMG" "$BT_B_IMG"; do
        while read -r dev; do
            [[ -n $dev ]] || continue
            _bt_is_lab_loop "$dev" || return 1
            losetup --detach "$dev"
        done < <(losetup --associated "$img" --noheadings --output NAME 2>/dev/null || true)
        rm -f -- "${img:?}"
    done
    rm -f -- "${LAB_STATE:?}/fault" "${LAB_STATE:?}/good.sha256" "${LAB_STATE:?}/good.uuid" "${LAB_STATE:?}/TASKS.txt"
    rmdir -- "$BT_A" "$BT_B" "$LAB_STATE/mnt" 2>/dev/null || true
    echo '教材のloopマウントとimageを解除しました。setupから再開できます。'
}
