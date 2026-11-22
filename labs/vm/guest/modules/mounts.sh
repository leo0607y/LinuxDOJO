# title: fstab修復・swapfile・LVM拡張（loopbackのみ）
# roles: app
# Sourced only after the root-owned VM dispatcher guard. Loop-backed regular files only;
# never touches real disks, the root filesystem, or fstab lines outside its marked block.

_mounts_paths() {
    [[ ${LAB_ID:-} == mounts && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/mounts ]] || { echo 'mounts: unexpected lab context' >&2; return 1; }
    M_IMG_A="$LAB_STATE/fstab.img"
    M_IMG_P1="$LAB_STATE/pv1.img"
    M_IMG_P2="$LAB_STATE/pv2.img"
    M_MNT_A="$LAB_STATE/mnt-fstab"
    M_MNT_C="$LAB_STATE/mnt-lvm"
    M_SWAP="$LAB_STATE/dojo.swap"
    M_VG=dojo_vg
    M_LV=dojo_lv
    M_BEGIN='# BEGIN LinuxDOJO mounts lab'
    M_END='# END LinuxDOJO mounts lab'
    local p
    for p in "$M_IMG_A" "$M_IMG_P1" "$M_IMG_P2" "$M_MNT_A" "$M_MNT_C" "$M_SWAP"; do
        [[ ! -L $p ]] || { echo 'mounts: symbolic paths rejected' >&2; return 1; }
    done
}

_mounts_loop_of() { # image -> loop device (first one), must be backed by exactly this image
    local loop
    loop="$(losetup --associated "$1" --noheadings --output NAME 2>/dev/null | head -n 1 | tr -d ' ')"
    [[ $loop =~ ^/dev/loop[0-9]+$ ]] || return 1
    [[ $(readlink -f "$(losetup --noheadings --output BACK-FILE "$loop")") == "$1" ]] || return 1
    printf '%s\n' "$loop"
}

_mounts_is_ours_loop() { # device must be a loop backed by one of the three lab images
    local back
    [[ $1 =~ ^/dev/loop[0-9]+$ ]] || return 1
    back="$(readlink -f "$(losetup --noheadings --output BACK-FILE "$1" 2>/dev/null)")" || return 1
    [[ $back == "$M_IMG_A" || $back == "$M_IMG_P1" || $back == "$M_IMG_P2" ]]
}

_mounts_block() { # print lines strictly between our markers
    awk -v b="$M_BEGIN" -v e="$M_END" '$0==e{f=0} f{print} $0==b{f=1}' /etc/fstab
}

_mounts_has_block() { grep -qxF -- "$M_BEGIN" /etc/fstab && grep -qxF -- "$M_END" /etc/fstab; }

_mounts_remove_block() {
    _mounts_has_block || return 0
    local tmp
    tmp="$(mktemp /etc/.fstab.dojo.XXXXXX)" || return 1
    awk -v b="$M_BEGIN" -v e="$M_END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' /etc/fstab > "$tmp"
    chmod --reference=/etc/fstab "$tmp"
    chown --reference=/etc/fstab "$tmp"
    mv -f -- "$tmp" /etc/fstab
}

_mounts_tab() { # write learner block (non-comment lines) to a temp tab file; print path
    local tab
    tab="$(mktemp "$LAB_STATE/tab.XXXXXX")" || return 1
    _mounts_block | grep -v '^[[:space:]]*#' | grep -v '^[[:space:]]*$' > "$tab" || true
    printf '%s\n' "$tab"
}

lab_setup() {
    _mounts_paths || return 1
    local tool
    for tool in pvcreate vgcreate lvcreate lvextend mkfs.ext4 resize2fs mkswap swapon findmnt blkid losetup tune2fs; do
        command -v "$tool" >/dev/null || { echo "mounts: $tool がありません (lvm2/e2fsprogs/util-linux が必要)" >&2; return 1; }
    done
    [[ ! -e $M_IMG_A && ! -e $M_IMG_P1 && ! -e $M_IMG_P2 && ! -e $M_SWAP && ! -e $LAB_STATE/fault ]] || { echo 'mounts: already configured; use reset first' >&2; return 1; }
    ! _mounts_has_block || { echo 'mounts: fstab に教材ブロックが残っています。reset してください' >&2; return 1; }
    ! vgs --noheadings "$M_VG" >/dev/null 2>&1 || { echo "mounts: VG $M_VG が既にあります" >&2; return 1; }
    mkdir -p "$M_MNT_A" "$M_MNT_C"
    local img
    for img in "$M_IMG_A" "$M_IMG_P1" "$M_IMG_P2"; do
        truncate -s 64M "$img"
        chmod 600 "$img"
        [[ -f $img && ! -b $img ]] || return 1
    done
    # Formatting targets are only the newly created regular file (fstab.img) and later the LV.
    mkfs.ext4 -q -F "$M_IMG_A"
    local loop_a
    loop_a="$(losetup --find --show "$M_IMG_A")" || return 1
    _mounts_is_ours_loop "$loop_a" || return 1
    mount -o nodev,nosuid "$loop_a" "$M_MNT_A"
    printf 'LinuxDOJO fstab keep\n' > "$M_MNT_A/keep.txt"
    umount "$M_MNT_A"
    losetup --find --show "$M_IMG_P1" > "$LAB_STATE/loop-pv1"
    losetup --find --show "$M_IMG_P2" > "$LAB_STATE/loop-pv2"
    touch "$LAB_STATE/setup-done"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
すべて教材専用のloopbackファイル上で行います (実ディスク・ルート領域は対象外)。
dojo-vm-lab mounts break のあと、次の3つをこなして dojo-vm-lab mounts check。

A. fstab修復 (教材ブロック: /etc/fstab の "BEGIN/END LinuxDOJO mounts lab" の間だけ編集)
   - ブロックの行は起動を止める誤ったUUIDを持つ。対象imageの本当のUUIDを blkid で調べる ($M_IMG_A のloopデバイス)
   - UUID・オプションを直し、起動を妨げないよう nofail を付ける
   - 既存の他の行は編集しない。findmnt --verify で確認し、mount -a で安全に反映する
B. swapfile ($M_SWAP, 64MiB以上)
   - 作成、権限 0600、mkswap、swapon。再起動後も有効になるよう同じ教材ブロック内に fstab の行を追加
   - swapon --show と /proc/swaps で確認
C. LVM拡張 (VG $M_VG / LV $M_LV は break が作成し $M_MNT_C にマウント済み)
   - pvs / vgs / lvs で現状を確認。未使用のloopは $(cat "$LAB_STATE/loop-pv2") (PVとして追加してVGへ)
   - LVをPV1の容量を超える64MiB以上へ拡張し、ファイルシステムも拡張する
   - $M_MNT_C/data.bin の内容が変わらないこと (sha256) を確認
reset は教材のloop・image・swap・VG・fstabブロックだけを片付けます。
TASK
    printf '実習手順: %s/TASKS.txt\n準備完了。dojo-vm-lab mounts break で故障を作ります。\n' "$LAB_STATE"
}

lab_break() {
    _mounts_paths || return 1
    [[ -f $LAB_STATE/setup-done && ! -e $LAB_STATE/fault ]] || { echo '先に setup を実行してください (または既に break 済みです)。'; return 1; }
    local loop_a loop_p1
    loop_a="$(_mounts_loop_of "$M_IMG_A")" && loop_p1="$(cat "$LAB_STATE/loop-pv1")" || { echo 'mounts: loop デバイスが見つかりません。reset→setup してください' >&2; return 1; }
    _mounts_is_ours_loop "$loop_p1" || return 1
    ! _mounts_has_block || { echo 'mounts: fstab ブロックが既にあります' >&2; return 1; }
    ! mountpoint -q "$M_MNT_A" || return 1
    # LVM base: marker first so reset knows it owns the VG.
    ! vgs --noheadings "$M_VG" >/dev/null 2>&1 || { echo "mounts: VG $M_VG が既にあります" >&2; return 1; }
    touch "$LAB_STATE/owns-vg"
    pvcreate -y -q "$loop_p1" >/dev/null
    vgcreate -q "$M_VG" "$loop_p1" >/dev/null
    lvcreate -y -q -L 32M -n "$M_LV" "$M_VG" >/dev/null
    mkfs.ext4 -q -F "/dev/$M_VG/$M_LV"
    mount -o nodev,nosuid "/dev/$M_VG/$M_LV" "$M_MNT_C"
    head -c 8M /dev/urandom > "$M_MNT_C/data.bin"
    sync
    sha256sum "$M_MNT_C/data.bin" | cut -d ' ' -f 1 > "$LAB_STATE/data.sha256"
    # fstab fault: only our marked block is appended; existing lines are untouched.
    {
        printf '%s\n' "$M_BEGIN"
        printf '# 教材: この行は誤ったUUIDのため、このまま再起動すると起動に失敗します\n'
        printf 'UUID=%s %s ext4 defaults 0 2\n' "$(cat /proc/sys/kernel/random/uuid)" "$M_MNT_A"
        printf '%s\n' "$M_END"
    } >> /etc/fstab
    printf 'fstab-uuid-and-lvm-created\n' > "$LAB_STATE/fault"
    printf 'TASKS.txt を読み、A(fstab) B(swapfile) C(LVM拡張) を行ってください。\n対象loop: %s\n' "$loop_a"
}

lab_check() {
    _mounts_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/data.sha256 ]] || { echo '先にbreakで故障を発生させてください。'; return 1; }
    _mounts_has_block || { echo 'fstab の教材ブロックがありません。'; return 1; }
    local tab uuid loop_a rows src fstype opts out
    loop_a="$(_mounts_loop_of "$M_IMG_A")" || { echo '教材imageのloopが外れています (再起動後は losetup で再接続)。'; return 1; }
    uuid="$(blkid -o value -s UUID "$loop_a")" || return 1
    [[ -n $uuid ]] || return 1
    tab="$(_mounts_tab)" || return 1
    # --- A: fstab entry validity (real findmnt verification of the learner's block) ---
    rows="$(findmnt --tab-file "$tab" -rn -o SOURCE,FSTYPE,OPTIONS --target "$M_MNT_A" 2>/dev/null || true)"
    read -r src fstype opts <<< "$rows"
    if [[ $src != "UUID=$uuid" && $src != "/dev/disk/by-uuid/$uuid" ]] || [[ $fstype != ext4 ]] || [[ ,$opts, != *,nofail,* ]]; then
        rm -f -- "$tab"; echo 'A: fstab の行が不正です (実UUID・ext4・nofail を確認)。'; return 1
    fi
    out="$(findmnt --verify --tab-file "$tab" 2>&1)" || true
    if grep -q '\[E\]' <<< "$out"; then rm -f -- "$tab"; echo 'A: findmnt --verify がエラーを報告しています。'; return 1; fi
    [[ $(findmnt -rn -M "$M_MNT_A" -o SOURCE) == "$loop_a" ]] || { rm -f -- "$tab"; echo 'A: 教材imageが fstab 経由でマウントされていません (mount -a)。'; return 1; }
    [[ $(cat "$M_MNT_A/keep.txt") == 'LinuxDOJO fstab keep' ]] || { rm -f -- "$tab"; echo 'A: データが失われています。'; return 1; }
    # --- B: swapfile live state + persistent entry inside our block ---
    if [[ ! -f $M_SWAP || $(stat -c %a:%u "$M_SWAP") != 600:0 ]]; then rm -f -- "$tab"; echo 'B: swapfile が無い、または権限が 0600 root ではありません。'; return 1; fi
    if ! { swapon --noheadings --raw --show=NAME | grep -qxF -- "$M_SWAP" && awk -v f="$M_SWAP" '$1==f' /proc/swaps | grep -q .; }; then
        rm -f -- "$tab"; echo 'B: swapfile が swapon されていません。'; return 1
    fi
    local ssize
    ssize="$(swapon --noheadings --raw --bytes --show=NAME,SIZE | awk -v f="$M_SWAP" '$1==f{print $2}')"
    [[ $ssize =~ ^[0-9]+$ ]] && (( ssize >= 64*1024*1024 - 65536 )) || { rm -f -- "$tab"; echo 'B: swap が64MiB未満です。'; return 1; }
    [[ $(findmnt --tab-file "$tab" -rn -o FSTYPE -S "$M_SWAP" 2>/dev/null | head -n 1) == swap ]] || { rm -f -- "$tab"; echo 'B: 教材ブロック内に swapfile の fstab 行がありません。'; return 1; }
    out="$(findmnt --verify --tab-file "$tab" 2>&1)" || true
    rm -f -- "$tab"
    if grep -q '\[E\]' <<< "$out"; then echo 'B: findmnt --verify がエラーを報告しています。'; return 1; fi
    # --- C: LVM extension with intact data ---
    local lvbytes pvname bad=0 count fsbytes bs bc
    lvbytes="$(lvs --noheadings --units b --nosuffix -o lv_size "$M_VG/$M_LV" 2>/dev/null | tr -d ' ')" || true
    [[ $lvbytes =~ ^[0-9]+$ ]] && (( lvbytes >= 64*1024*1024 )) || { echo 'C: LV が64MiB以上に拡張されていません。'; return 1; }
    count=0
    while read -r pvname; do
        [[ -n $pvname ]] || continue
        count=$((count+1))
        _mounts_is_ours_loop "$pvname" || bad=1
    done < <(pvs --noheadings -o pv_name -S "vg_name=$M_VG" 2>/dev/null | tr -d ' ')
    (( count >= 2 && bad == 0 )) || { echo 'C: VG に教材の2本目のPVが追加されていません。'; return 1; }
    [[ $(findmnt -rn -M "$M_MNT_C" -o SOURCE) == "/dev/mapper/$M_VG-$M_LV" ]] || { echo 'C: LV が教材のマウント先にありません。'; return 1; }
    bs="$(tune2fs -l "/dev/$M_VG/$M_LV" | awk -F: '/^Block size/{gsub(/ /,"",$2);print $2}')"
    bc="$(tune2fs -l "/dev/$M_VG/$M_LV" | awk -F: '/^Block count/{gsub(/ /,"",$2);print $2}')"
    [[ $bs =~ ^[0-9]+$ && $bc =~ ^[0-9]+$ ]] || return 1
    fsbytes=$((bs*bc))
    (( fsbytes * 100 >= lvbytes * 95 )) || { echo 'C: ファイルシステムがLVの大きさまで拡張されていません (resize2fs)。'; return 1; }
    [[ $(sha256sum "$M_MNT_C/data.bin" | cut -d ' ' -f 1) == "$(cat "$LAB_STATE/data.sha256")" ]] || { echo 'C: data.bin のチェックサムが一致しません。'; return 1; }
    echo '達成: fstab修復(nofail)・swapfile・LV/FS拡張とデータ保持を実状態で確認しました。'
}

lab_reset() {
    _mounts_paths || return 1
    local loop img back pvname pvs_list
    # 1. fstab block (only our marked lines), then live mounts/swap
    _mounts_remove_block
    if [[ -f $M_SWAP ]] && swapon --noheadings --raw --show=NAME | grep -qxF -- "$M_SWAP"; then
        swapoff -- "$M_SWAP"
    fi
    rm -f -- "$M_SWAP"
    if mountpoint -q "$M_MNT_A"; then
        _mounts_is_ours_loop "$(findmnt -rn -M "$M_MNT_A" -o SOURCE)" || { echo 'mounts: 想定外のマウントです。中止' >&2; return 1; }
        umount "$M_MNT_A"
    fi
    if mountpoint -q "$M_MNT_C"; then
        [[ $(findmnt -rn -M "$M_MNT_C" -o SOURCE) == "/dev/mapper/$M_VG-$M_LV" ]] || { echo 'mounts: 想定外のマウントです。中止' >&2; return 1; }
        umount "$M_MNT_C"
    fi
    # 2. LVM: only if we own it and every PV and LV is ours
    if [[ -f $LAB_STATE/owns-vg ]] && vgs --noheadings "$M_VG" >/dev/null 2>&1; then
        pvs_list="$(pvs --noheadings -o pv_name -S "vg_name=$M_VG" | tr -d ' ')"
        while read -r pvname; do
            [[ -n $pvname ]] || continue
            _mounts_is_ours_loop "$pvname" || { echo "mounts: $M_VG に教材外のPV($pvname)があります。中止" >&2; return 1; }
        done <<< "$pvs_list"
        while read -r back; do
            [[ -z $back || $back == "$M_LV" ]] || { echo "mounts: $M_VG に教材外のLV($back)があります。中止" >&2; return 1; }
        done < <(lvs --noheadings -o lv_name "$M_VG" | tr -d ' ')
        vgremove -f -y "$M_VG" >/dev/null
        while read -r pvname; do
            [[ -n $pvname ]] && pvremove -f -f -y "$pvname" >/dev/null
        done <<< "$pvs_list"
    fi
    # 3. loop devices and images
    for img in "$M_IMG_A" "$M_IMG_P1" "$M_IMG_P2"; do
        [[ -f $img ]] || continue
        while read -r loop; do
            [[ -n $loop ]] || continue
            _mounts_is_ours_loop "$loop" || return 1
            losetup --detach "$loop"
        done < <(losetup --associated "$img" --noheadings --output NAME)
        rm -f -- "$img"
    done
    rm -f -- "${LAB_STATE:?}/fault" "${LAB_STATE:?}/owns-vg" "${LAB_STATE:?}/setup-done" "${LAB_STATE:?}/data.sha256" \
        "${LAB_STATE:?}/loop-pv1" "${LAB_STATE:?}/loop-pv2" "${LAB_STATE:?}/TASKS.txt"
    rm -f -- "${LAB_STATE:?}"/tab.*
    rmdir -- "$M_MNT_A" "$M_MNT_C" 2>/dev/null || true
    echo '教材のloop・image・swap・VG・fstabブロックを解除しました。setupから再開できます。'
}
