# title: 専用ext4のinode枯渇と、再起動後のマウント確認
# Sourced only after the root-owned VM dispatcher guard. Never accepts a device argument.

_storage_paths() {
    [[ ${LAB_ID:-} == storage && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/storage ]] || { echo 'storage: unexpected lab context' >&2; return 1; }
    STORAGE_IMAGE="$LAB_STATE/data.img"
    STORAGE_MOUNT="$LAB_STATE/mnt"
    STORAGE_UNIT="$(systemd-escape --path --suffix=mount "$STORAGE_MOUNT")"
    [[ ! -L $STORAGE_IMAGE && ! -L $STORAGE_MOUNT ]] || { echo 'storage: symbolic paths rejected' >&2; return 1; }
}

_storage_source() {
    local source backing
    source="$(findmnt -rn -M "$STORAGE_MOUNT" -o SOURCE)" || return 1
    [[ $source =~ ^/dev/loop[0-9]+$ ]] || return 1
    backing="$(losetup --noheadings --output BACK-FILE "$source")" || return 1
    [[ $(readlink -f "$backing") == "$STORAGE_IMAGE" ]] || { echo 'storage: mount is not backed by the lab image' >&2; return 1; }
}

_storage_free_inodes() {
    # --output selects inode columns itself; GNU df rejects combining it with -i.
    df --output=iavail "$STORAGE_MOUNT" | tail -n 1 | tr -d ' '
}

lab_setup() {
    _storage_paths
    [[ ! -e $STORAGE_IMAGE && ! -e /etc/systemd/system/$STORAGE_UNIT ]] || { echo 'storage: already configured; use reset first' >&2; return 1; }
    mkdir -p "$STORAGE_MOUNT"
    truncate -s 32M "$STORAGE_IMAGE"
    chmod 600 "$STORAGE_IMAGE"
    # The sole formatting target is this newly created regular file, never a block device.
    [[ -f $STORAGE_IMAGE && ! -b $STORAGE_IMAGE ]] || return 1
    mkfs.ext4 -q -F -N 256 "$STORAGE_IMAGE"
    cat > "/etc/systemd/system/$STORAGE_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated loop-backed ext4 training mount
[Mount]
What=$STORAGE_IMAGE
Where=$STORAGE_MOUNT
Type=ext4
Options=loop,nodev,nosuid
[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now "$STORAGE_UNIT"
    _storage_source
    printf 'LinuxDOJO preserve this report\n' > "$STORAGE_MOUNT/keep.txt"
    cat > "$LAB_STATE/README.txt" <<TASK
対象: $STORAGE_MOUNT (32MiBの教材image。VMのルート領域ではありません)
1. dojo-vm-lab storage break
2. df -h $STORAGE_MOUNT と df -i $STORAGE_MOUNT を比較
3. find $STORAGE_MOUNT -maxdepth 1 -type f -name 'fill-*' -empty で候補を確認
4. 対象を確認してから同じfindの末尾へ -delete を追加。keep.txt は残す
5. 新しいファイルを作って消せることを確認し、systemctl is-enabled $STORAGE_UNIT を確認
6. この使い捨てVMを再起動
7. dojo-vm-lab storage check
reset は専用マウント・image・unitだけを解除します。ルートディスクへmkfsしません。
TASK
    printf '実習手順: %s/README.txt\n専用マウント: %s\n' "$LAB_STATE" "$STORAGE_MOUNT"
    printf '準備完了。dojo-vm-lab storage break で専用領域のinodeを枯渇させます。\n'
}

lab_break() {
    _storage_paths
    _storage_source
    local number=0
    while (( number < 4096 )); do
        if ! touch "$STORAGE_MOUNT/fill-$number" 2>/dev/null; then
            break
        fi
        number=$((number+1))
    done
    (( number < 4096 )) || { echo 'storage: expected inode exhaustion not observed' >&2; return 1; }
    cat /proc/sys/kernel/random/boot_id > "$LAB_STATE/broken-boot-id"
    printf '%s\n' 'inode-exhaustion-created' > "$LAB_STATE/fault"
    printf 'df -h と df -i、find で対象を調査してください。\n削除してよいのは専用マウント内の fill-* という空ファイルだけです。keep.txt を保持します。\n復旧後にこの使い捨てVMを再起動し、check で永続マウントとデータを確認してください。\n'
}

lab_check() {
    _storage_paths
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/broken-boot-id ]] || { echo '先にbreakで故障を発生させてください。'; return 1; }
    _storage_source || { echo '専用領域が正しいimageからマウントされていません。'; return 1; }
    systemctl is-enabled --quiet "$STORAGE_UNIT" || return 1
    [[ $(cat "$STORAGE_MOUNT/keep.txt") == 'LinuxDOJO preserve this report' ]] || { echo '保持対象の内容が失われています。'; return 1; }
    local available
    available="$(_storage_free_inodes)"
    [[ $available =~ ^[0-9]+$ ]] && (( available >= 16 )) || { echo 'inodeの余裕が不足しています。'; return 1; }
    [[ $(find "$STORAGE_MOUNT" -maxdepth 1 -type f -name 'fill-*' -printf x | wc -c) -eq 0 ]] || { echo '不要なfillファイルが残っています。'; return 1; }
    [[ $(cat /proc/sys/kernel/random/boot_id) != $(cat "$LAB_STATE/broken-boot-id") ]] || { echo '復旧後、この使い捨てVMを再起動して永続設定を確認してください。'; return 1; }
    echo '達成: inodeを復旧し、再起動後の専用マウントと保持データを確認しました。'
}

lab_reset() {
    _storage_paths
    if mountpoint -q "$STORAGE_MOUNT"; then
        _storage_source || return 1
    fi
    if [[ -f /etc/systemd/system/$STORAGE_UNIT ]]; then
        systemctl disable --now "$STORAGE_UNIT"
        rm -f -- "/etc/systemd/system/$STORAGE_UNIT"
        systemctl daemon-reload
    fi
    if mountpoint -q "$STORAGE_MOUNT"; then
        echo 'storage: mount remains active; refusing to remove its image' >&2
        return 1
    fi
    if [[ -f $STORAGE_IMAGE ]]; then
        local loop backing
        while read -r loop; do
            [[ -n $loop ]] || continue
            [[ $loop =~ ^/dev/loop[0-9]+$ ]] || return 1
            backing="$(losetup --noheadings --output BACK-FILE "$loop")"
            [[ $(readlink -f "$backing") == "$STORAGE_IMAGE" ]] || return 1
            losetup --detach "$loop"
        done < <(losetup --associated "$STORAGE_IMAGE" --noheadings --output NAME)
        rm -f -- "$STORAGE_IMAGE"
    fi
    rm -f -- "$LAB_STATE/fault" "$LAB_STATE/broken-boot-id"
    rm -f -- "$LAB_STATE/README.txt"
    rmdir -- "$STORAGE_MOUNT" 2>/dev/null || true
    echo '専用imageとマウント設定を解除しました。setupから再開できます。'
}
