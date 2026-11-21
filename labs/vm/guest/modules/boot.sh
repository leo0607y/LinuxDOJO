# title: 専用systemdサービスの起動失敗から復旧し、再起動後も確認する
# The guest root filesystem, bootloader and real fstab are never modified.

_boot_paths() {
    [[ ${LAB_ID:-} == boot && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/boot ]] || { echo 'boot: unexpected lab context' >&2; return 1; }
    BOOT_UNIT=/etc/systemd/system/dojo-recovery.service
    [[ ! -L $BOOT_UNIT && ! -L $LAB_STATE/config.ini && ! -L $LAB_STATE/backup.ini ]] || { echo 'boot: symbolic paths rejected' >&2; return 1; }
}

lab_setup() {
    _boot_paths
    [[ ! -e $BOOT_UNIT ]] || { echo 'boot: dedicated unit already exists; reset first' >&2; return 1; }
    printf 'mode=training\ninstance=%s\n' "$(cat /proc/sys/kernel/random/uuid)" > "$LAB_STATE/backup.ini"
    cp -- "$LAB_STATE/backup.ini" "$LAB_STATE/config.ini"
    chmod 600 "$LAB_STATE/backup.ini" "$LAB_STATE/config.ini"
    cat > "$BOOT_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated recovery exercise
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/usr/bin/cmp -s $LAB_STATE/backup.ini $LAB_STATE/config.ini
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$BOOT_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-recovery.service
    cat > "$LAB_STATE/README.txt" <<TASK
対象: dojo-recovery.service と $LAB_STATE/config.ini だけ
1. dojo-vm-lab boot break
2. systemctl status dojo-recovery.service と journalctl -u dojo-recovery.service -b を読む
3. systemctl cat dojo-recovery.service で検証対象のファイルを確認
4. $LAB_STATE/backup.ini を config.ini へ復元。権限600と内容を確認
5. systemctl restart dojo-recovery.service と systemctl is-active dojo-recovery.service で確認
6. この使い捨てVMを再起動
7. dojo-vm-lab boot check
unitのExecStartをtrueへ変更する方法は不正解です。必要な設定を戻します。
この実習は専用サービスの復旧です。OS自体の起動不能・GRUB復旧を再現してはいません。
TASK
    printf '実習手順: %s/README.txt\n' "$LAB_STATE"
    echo '準備完了。dojo-vm-lab boot break で専用サービスだけを故障させます。'
}

lab_break() {
    _boot_paths
    [[ -f $BOOT_UNIT && -f $LAB_STATE/backup.ini ]] || return 1
    rm -f -- "$LAB_STATE/config.ini"
    if systemctl restart dojo-recovery.service; then
        echo 'boot: expected dedicated service failure not observed' >&2
        return 1
    fi
    cat /proc/sys/kernel/random/boot_id > "$LAB_STATE/broken-boot-id"
    printf 'missing-configuration\n' > "$LAB_STATE/fault"
    printf 'systemctl status dojo-recovery.service と journalctl -u dojo-recovery.service で原因を調べます。\nbackup.ini の内容を config.ini に戻し、権限600を保って専用サービスを復旧してください。\nunitを変更して成功を装わず、復旧後は使い捨てVMを再起動して確認します。\n'
}

lab_check() {
    _boot_paths
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/broken-boot-id ]] || { echo '先にbreakを実行してください。'; return 1; }
    [[ -f $BOOT_UNIT && $(sha256sum "$BOOT_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || { echo '専用unitの検証を無効にせず設定を復元します。'; return 1; }
    cmp -s "$LAB_STATE/backup.ini" "$LAB_STATE/config.ini" || { echo '設定本文がバックアップと一致しません。'; return 1; }
    [[ $(stat -c %a "$LAB_STATE/config.ini") == 600 ]] || { echo '設定の権限を600にします。'; return 1; }
    systemctl is-active --quiet dojo-recovery.service || { echo '専用サービスが稼働していません。'; return 1; }
    systemctl is-enabled --quiet dojo-recovery.service || return 1
    [[ $(cat /proc/sys/kernel/random/boot_id) != $(cat "$LAB_STATE/broken-boot-id") ]] || { echo '復旧後、この使い捨てVMを再起動してください。'; return 1; }
    echo '達成: 故障を調査し、設定を戻し、再起動後も専用サービスが動くことを確認しました。'
}

lab_reset() {
    _boot_paths
    if [[ -f $BOOT_UNIT ]]; then
        systemctl disable --now dojo-recovery.service
        rm -f -- "$BOOT_UNIT"
        systemctl daemon-reload
        systemctl reset-failed dojo-recovery.service 2>/dev/null || true
    fi
    rm -f -- "$LAB_STATE/backup.ini" "$LAB_STATE/config.ini" "$LAB_STATE/unit.sha256" "$LAB_STATE/fault" "$LAB_STATE/broken-boot-id" "$LAB_STATE/README.txt"
    echo '専用サービスと教材設定を解除しました。'
}
