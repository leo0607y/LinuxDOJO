# title: GRUBの導入・grub.cfg生成・障害切り分けとレスキュー手順(ループバックディスクで安全に実習)
# roles: app
# Guest-only. Works ONLY on a dedicated sparse disk image attached with losetup. The VM's real /boot, ESP, grub.cfg and root disk are never written.
# What is real: partition table, ext4, grub-install (i386-pc, MBR + embedded core.img), grub-mkconfig/grub-probe/grub-script-check output.
# What is NOT real: the kernel/initrd files are small placeholders (the image is not bootable). Real rescue boots are manual (TASKS.txt).

_gr_paths() {
    [[ ${LAB_ID:-} == grubrescue && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/grubrescue ]] || { echo 'grubrescue: unexpected lab context' >&2; return 1; }
    GR_IMG=$LAB_STATE/grublab.img
    GR_MNT=$LAB_STATE/root
    GR_CHROOT=$LAB_STATE/grub-chroot
    GR_DEFAULT=$GR_MNT/etc/default/grub
    GR_CUSTOM=$GR_MNT/etc/grub.d/40_custom
    GR_CFG=$GR_MNT/boot/grub/grub.cfg
    GR_ANS=$LAB_STATE/answers.txt
    GR_BAD_UUID=11111111-2222-3333-4444-555555555555
    GR_VER_NEW=6.8.0-1-dojo
    GR_VER_OLD=6.8.0-0-dojo
    [[ ! -L $LAB_STATE && ! -L $GR_IMG && ! -L $GR_MNT ]] || { echo 'grubrescue: unexpected lab context (symlink)' >&2; return 1; }
}

# Loop device currently backing OUR image (empty if none). Never trusts a stored name alone.
_gr_loop() { losetup -j "$GR_IMG" -n -O NAME 2>/dev/null | head -1; }

_gr_teardown() {
    local loop
    if findmnt -n -M "$GR_MNT" >/dev/null 2>&1; then umount "$GR_MNT" || return 1; fi
    loop=$(_gr_loop)
    [[ -z $loop ]] || losetup -d "$loop" || return 1
    return 0
}

# Parse a grub.cfg: "E<TAB>title<TAB>nlinux<TAB>ninitrd", "L<TAB>title<TAB>line", "I<TAB>title<TAB>path"
_gr_entries() {
    awk '
    function emit() { if (t != "") printf "E\t%s\t%d\t%d\n", t, nl, ni }
    /^[[:space:]]*menuentry[[:space:]]/ {
        emit(); nl = 0; ni = 0; t = ""
        if (match($0, /[\047"][^\047"]*[\047"]/)) t = substr($0, RSTART + 1, RLENGTH - 2); else t = "?"
        next }
    /^[[:space:]]*linux(16|efi)?[[:space:]]/ { nl++; line = $0; gsub(/[ \t]+/, " ", line); sub(/^ /, "", line); printf "L\t%s\t%s\n", t, line; next }
    /^[[:space:]]*initrd(16|efi)?[[:space:]]/ { ni++; printf "I\t%s\t%s\n", t, $2; next }
    END { emit() }' "$1"
}

lab_setup() {
    _gr_paths || return 1
    local c
    for c in losetup sfdisk mkfs.ext4 blkid lsblk findmnt unshare file dd awk grub-install grub-mkconfig grub-probe grub-script-check; do
        command -v "$c" >/dev/null || { echo "$c がありません。grub2-common / grub-pc-bin / util-linux / e2fsprogs が必要です。"; return 1; }
    done
    [[ -d /usr/lib/grub/i386-pc ]] || { echo '/usr/lib/grub/i386-pc がありません。sudo apt-get install grub-pc-bin が必要です。'; return 1; }
    [[ ! -e $GR_IMG && ! -e $GR_MNT && ! -e $GR_CHROOT ]] || { echo '専用ファイルが既にあります。既存データを上書きしません。'; return 1; }
    if [[ -e /boot/grub/grub.cfg ]]; then sha256sum /boot/grub/grub.cfg > "$LAB_STATE/host-cfg.sha256" || return 1; else : > "$LAB_STATE/host-cfg.sha256"; fi
    local loop part v
    truncate -s 256M "$GR_IMG" || return 1
    printf 'label: dos\nstart=2048, type=83\n' | sfdisk -q "$GR_IMG" >/dev/null || { rm -f -- "$GR_IMG"; return 1; }
    loop=$(losetup -f -P --show "$GR_IMG") || { rm -f -- "$GR_IMG"; return 1; }
    part=${loop}p1
    udevadm settle 2>/dev/null || true
    for c in 1 2 3 4 5 6 7 8 9 10; do [[ -b $part ]] && break; sleep 0.5; done
    if [[ ! -b $part ]] || ! mkfs.ext4 -q -F -L dojoboot "$part"; then
        losetup -d "$loop"; rm -f -- "$GR_IMG"; echo "$part を作れませんでした。"; return 1
    fi
    mkdir -p "$GR_MNT"
    if ! mount "$part" "$GR_MNT"; then losetup -d "$loop"; rm -f -- "$GR_IMG"; rmdir "$GR_MNT"; return 1; fi
    (
        set -e
        cd "$GR_MNT"
        rm -rf lost+found
        mkdir -p boot/grub etc/default etc/grub.d dev proc sys usr tmp root
        ln -s usr/bin bin; ln -s usr/sbin sbin; ln -s usr/lib lib; ln -s usr/lib64 lib64
        cp /etc/os-release etc/os-release
        for v in 00_header 10_linux 40_custom; do cp -p "/etc/grub.d/$v" "etc/grub.d/$v"; done
        for v in "$GR_VER_OLD" "$GR_VER_NEW"; do
            printf 'DOJO PLACEHOLDER kernel %s (not bootable)\n' "$v" > "boot/vmlinuz-$v"
            printf 'DOJO PLACEHOLDER initrd %s (not bootable)\n' "$v" > "boot/initrd.img-$v"
        done
        cat > etc/default/grub <<'DEF'
# Lab copy of /etc/default/grub (the real one is not used here)
GRUB_DEFAULT=0
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="DojoLinux"
GRUB_CMDLINE_LINUX_DEFAULT="quiet"
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_OS_PROBER=false
DEF
    ) || { _gr_teardown; rm -rf -- "$GR_IMG"; echo 'ステージングに失敗しました。'; return 1; }
    cat > "$GR_CHROOT" <<'HELPER'
#!/bin/bash
# Enters the lab root in a PRIVATE mount namespace (nothing leaks to the VM). /usr is bound read-only.
[[ $EUID == 0 ]] || { echo 'root(sudo)で実行してください。' >&2; exit 1; }
R=$(dirname "$(readlink -f "$0")")/root
findmnt -n -M "$R" >/dev/null || { echo 'ラボのルートがマウントされていません。' >&2; exit 1; }
exec unshare -m bash -c '
set -e
mount --make-rprivate /
R=$1; shift
mount --rbind /dev "$R/dev"; mount --rbind /proc "$R/proc"; mount --rbind /sys "$R/sys"
mount --bind /usr "$R/usr"; mount -o remount,bind,ro "$R/usr"
[[ $# -gt 0 ]] || set -- /bin/bash
exec chroot "$R" "$@"
' grub-chroot "$R" "$@"
HELPER
    chmod 700 "$GR_CHROOT"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
この課題はapp VMで root (sudo) で操作する。実習は専用のループバックディスクだけを使う:
  イメージ: $GR_IMG (256MB, MBR + ext4 1パーティション)
  ラボのルート(マウント済み): $GR_MNT  ・ラボの /etc/default/grub: $GR_DEFAULT
VMの本物の /boot, /boot/efi, /boot/grub/grub.cfg, ルートディスクには触らない(checkが本物のgrub.cfgの改変を検出する)。
[正直な注意] カーネル/initrdは小さなダミーでこのイメージは実際には起動しない。grub-install/grub-mkconfigの出力は本物。

[ディスクを観察する]
1. losetup -j $GR_IMG でループデバイスを調べ、lsblk -f と blkid -p でパーティションのUUID・ファイルシステムを記録する。
2. grub-probe -t fs_uuid -d <ループのパーティション> と blkid の値を見比べる。
[ブートローダの導入]
3. grub-install --target=i386-pc --boot-directory=$GR_MNT/boot --modules="part_msdos ext2" <ループデバイス全体>
   ※ 渡すのはループデバイスだけ。VMの /dev/sda や /dev/vda を指定してはならない。--removable が何のオプションか(EFI用)も man で確認。
4. MBR(先頭512B)と直後のセクタ(core.img埋め込み)を dd で読み、$GR_MNT/boot/grub/i386-pc/ の boot.img/core.img と照らす。
[設定とgrub.cfg生成]
5. $GR_DEFAULT を編集: GRUB_TIMEOUT=7, GRUB_CMDLINE_LINUX に console=ttyS0,115200n8, GRUB_DISABLE_OS_PROBER=true。
6. $GR_MNT/etc/grub.d/40_custom に、タイトルが "Dojo rescue" で始まるメニューエントリを追加
   (linux行に systemd.unit=rescue.target、initrd行も書く。root は set root か search で指定)。
7. grub-mkconfig は /etc と / 固定で動くため、ラボのルートに chroot して実行する:
     sudo $GR_CHROOT grub-mkconfig -o /boot/grub/grub.cfg     (chrootの中のパス)
   ($GR_CHROOT は私設マウント名前空間で /dev /proc /sys をbindし /usr を読み取り専用で見せる。終了すれば消える)
   生成された $GR_CFG の menuentry/submenu 構造、search行、linux/initrd行を読む。grub-script-check で構文確認。
[障害対応]
8. sudo dojo-vm-lab grubrescue break を実行。設定とgrub.cfgが壊れる。
9. grub-script-check と各エントリを読み、原因(UUID不一致・initrd欠落・不正なカーネル引数・括弧・既定ファイルの綴りと値)を特定する。
   手でgrub.cfgを書き換えるのではなく、既定ファイルを直して grub-mkconfig で再生成すること(checkは生成物であることを確認する)。
10. 手順5・6の内容を再度満たす状態にする。
[知識の回答]
11. $GR_ANS に自分の言葉で次を書く(キーワードで機械判定される):
    (a) 単一ユーザ/レスキュー: init=/bin/bash と systemd.unit=rescue.target の違い、emergency.target との違い
    (b) RHEL系の rd.break: どの段階で止まるか、/sysroot を rw で再マウントして chroot し、SELinuxの .autorelabel を作る流れ
    (c) chroot修復の手順: ルートをmount、/dev /proc /sys を --bind/--rbind、chroot、grub-install と update-grub(grub-mkconfig)
12. sudo dojo-vm-lab grubrescue check
13. 終了後 sudo dojo-vm-lab grubrescue reset (ループデバイスを解除し、専用ファイルだけ削除)

[手動(自動判定しない): VMコンソールでの本物のレスキュー起動]
  このラボでは判定されない。VMのシリアル/グラフィックコンソールで、起動時に GRUB で e を押し、
  linux行の末尾に systemd.unit=rescue.target を足して Ctrl-x、次に init=/bin/bash で再度試す。
  (Ubuntuは rd.break ではなく break=premount 等。RHEL系なら rd.break)。いずれも起動後に
  mount -o remount,rw / を忘れずに。必ず変更前のスナップショットを取ってから試し、終わったら元に戻す。
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudo cat で読めます)。"
    cat "$LAB_STATE/TASKS.txt"
    touch "$LAB_STATE/setup-done"
}

lab_break() {
    _gr_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo '既に故障状態です。'; return 1; }
    local loop part uuid
    loop=$(_gr_loop); part=${loop}p1
    [[ -n $loop && $(findmnt -n -o SOURCE -M "$GR_MNT" 2>/dev/null) == "$part" ]] || { echo 'ラボのイメージがマウントされていません。'; return 1; }
    [[ -f $GR_MNT/boot/grub/i386-pc/core.img ]] || { echo 'まず grub-install (手順3) を実施します。'; return 1; }
    grep -q 'Dojo rescue' "$GR_CUSTOM" || { echo 'まず 40_custom に Dojo rescue エントリを書きます(手順6)。'; return 1; }
    uuid=$(blkid -p -s UUID -o value "$part") || return 1
    cat > "$GR_DEFAULT" <<'DEF'
# LinuxDOJO grubrescue lab (fault injected)
GRUB_DEFAULT=0
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMOUT=ten
GRUB_DISTRIBUTOR="DojoLinux"
GRUB_CMDLINE_LINUX_DEFAULT="quiet"
GRUB_CMDLINE_LINUX="init=/sbin/nonexistent"
GRUB_DISABLE_OS_PROBER=false
DEF
    cat > "$GR_CFG" <<CFG
set default=0
set timeout=ten
menuentry 'DojoLinux' --class gnu-linux {
	insmod ext2
	search --no-floppy --fs-uuid --set=root $GR_BAD_UUID
	linux	/boot/vmlinuz-$GR_VER_NEW root=UUID=$GR_BAD_UUID ro quiet init=/sbin/nonexistent
}
menuentry 'DojoLinux (old)' --class gnu-linux {
	insmod ext2
	search --no-floppy --fs-uuid --set=root $uuid
	linux	/boot/vmlinuz-$GR_VER_OLD root=UUID=$uuid ro
	initrd	/boot/initrd.img-$GR_VER_OLD
CFG
    touch "$LAB_STATE/fault"
    echo 'grub.cfg と既定ファイルが壊れました。grub-script-check と各エントリを調べ、既定ファイルを直して grub-mkconfig で再生成してください。'
}

lab_check() {
    _gr_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで障害を作ります。'; return 1; }
    local loop part uuid
    loop=$(_gr_loop); part=${loop}p1
    [[ -n $loop && -b $part && $(findmnt -n -o SOURCE -M "$GR_MNT" 2>/dev/null) == "$part" ]] || { echo 'ラボのイメージがループデバイスにマウントされていません。'; return 1; }
    if [[ -s $LAB_STATE/host-cfg.sha256 ]] && ! sha256sum -c --quiet "$LAB_STATE/host-cfg.sha256" >/dev/null 2>&1; then
        echo 'VMの本物の /boot/grub/grub.cfg が変更されています。ラボ以外に書き込んではいけません。'; return 1
    fi
    uuid=$(blkid -p -s UUID -o value "$part") || { echo 'blkidでUUIDを取得できません。'; return 1; }
    [[ $(grub-probe -t fs_uuid -d "$part" 2>/dev/null) == "$uuid" ]] || { echo 'grub-probe のUUIDと blkid が一致しません。'; return 1; }
    [[ $(grub-probe -t fs -d "$part" 2>/dev/null) == ext2 ]] || { echo 'grub-probe がext2系ファイルシステムと判定しません。'; return 1; }
    # bootloader really installed on the loop device
    dd if="$loop" bs=512 count=1 status=none 2>/dev/null | grep -aq 'Geom' || { echo 'MBRに GRUB の boot.img がありません。grub-install を実行しましたか。'; return 1; }
    cmp -s -n 512 <(dd if="$loop" bs=512 skip=1 count=1 status=none 2>/dev/null) /dev/zero && { echo 'MBR直後に core.img が埋め込まれていません。'; return 1; }
    local core=$GR_MNT/boot/grub/i386-pc/core.img
    [[ -f $core && $(stat -c %s "$core") -gt 20000 ]] || { echo 'core.img がありません。'; return 1; }
    [[ -f $GR_MNT/boot/grub/i386-pc/boot.img || -f $GR_MNT/boot/grub/i386-pc/normal.mod ]] || { echo '/boot/grub/i386-pc にモジュールがありません。'; return 1; }
    # default file (file-only items)
    local timeout osp cmd
    timeout=$(grep -E '^GRUB_TIMEOUT=' "$GR_DEFAULT" | tail -1 | cut -d= -f2- | tr -d "\"'")
    osp=$(grep -E '^GRUB_DISABLE_OS_PROBER=' "$GR_DEFAULT" | tail -1 | cut -d= -f2- | tr -d "\"'")
    cmd=$(grep -E '^GRUB_CMDLINE_LINUX=' "$GR_DEFAULT" | tail -1)
    [[ $timeout == 7 ]] || { echo '既定ファイルの GRUB_TIMEOUT が 7 ではありません。'; return 1; }
    [[ $osp == true ]] || { echo 'GRUB_DISABLE_OS_PROBER=true にしてください。'; return 1; }
    grep -q 'console=ttyS0,115200n8' <<<"$cmd" && ! grep -q 'init=/sbin/nonexistent' <<<"$cmd" || { echo 'GRUB_CMDLINE_LINUX が不正です。'; return 1; }
    grep -Eq '^GRUB_TIMOUT' "$GR_DEFAULT" && { echo '既定ファイルに綴りの誤ったキーが残っています。'; return 1; }
    # generated config
    [[ -f $GR_CFG ]] || { echo 'grub.cfg がありません。'; return 1; }
    grep -q '^### BEGIN /etc/grub.d/10_linux ###' "$GR_CFG" || { echo 'grub.cfg が grub-mkconfig で再生成されていません。'; return 1; }
    grub-script-check "$GR_CFG" 2>"$LAB_STATE/check-script.log" || { echo 'grub-script-check が失敗しました。'; return 1; }
    grep -Eq '^[[:space:]]*set timeout=7[[:space:]]*$' "$GR_CFG" || { echo 'grub.cfg の timeout が 7 ではありません。'; return 1; }
    local parsed kind a b c n_e=0 custom=0 n_kernel=0 root bad
    parsed=$(_gr_entries "$GR_CFG")
    while IFS=$'\t' read -r kind a b c; do
        case $kind in
            E) n_e=$((n_e + 1))
               [[ $b == 1 && $c -ge 1 ]] || { echo "メニューエントリ '$a' に linux 行/initrd 行が揃っていません。"; return 1; }
               [[ $a != "Dojo rescue"* ]] || custom=1 ;;
            L) n_kernel=$((n_kernel + 1))
               local path=${b#* }; path=${path%% *}
               [[ -f $GR_MNT$path ]] || { echo "linux 行のカーネル $path がイメージ内に存在しません。"; return 1; }
               root=$(grep -o ' root=[^ ]*' <<<" $b")
               [[ $(wc -l <<<"$root") == 1 && -n $root ]] || { echo "'$a' の root= 引数が一つではありません。"; return 1; }
               [[ ${root# root=} == "UUID=$uuid" || ${root# root=} == "$part" ]] || { echo "'$a' の root= が実際の blkid UUID($uuid)と一致しません。"; return 1; }
               grep -q 'init=/sbin/nonexistent' <<<"$b" && { echo "'$a' に不正な init= があります。"; return 1; }
               if [[ $a == "Dojo rescue"* ]]; then
                   grep -q 'systemd.unit=rescue.target' <<<"$b" || { echo 'Dojo rescue の linux 行に systemd.unit=rescue.target がありません。'; return 1; }
               else
                   grep -q 'console=ttyS0,115200n8' <<<"$b" || { echo "'$a' に console=ttyS0,115200n8 がありません。"; return 1; }
               fi ;;
            I) [[ -f $GR_MNT$b ]] || { echo "initrd $b がイメージ内に存在しません。"; return 1; } ;;
        esac
    done <<<"$parsed"
    [[ $n_e -ge 3 && $n_kernel -ge 3 ]] || { echo 'メニューエントリが少なすぎます(カーネル2本の標準+recovery+Dojo rescueが必要)。'; return 1; }
    [[ $custom == 1 ]] || { echo 'grub.cfg に "Dojo rescue" エントリがありません。40_custom を確認してください。'; return 1; }
    bad=$(grep -E '^[[:space:]]*search .*--set=root' "$GR_CFG" | grep -v -- "--fs-uuid --set=root $uuid" | grep -F -- '--fs-uuid' || true)
    [[ -z $bad ]] || { echo 'search --fs-uuid の UUID が実際の blkid と一致しない行があります。'; return 1; }
    grep -q -- "$GR_BAD_UUID" "$GR_CFG" && { echo '壊れたUUIDが残っています。'; return 1; }
    # knowledge answers
    [[ -f $GR_ANS ]] || { echo "$GR_ANS を書いてください(手順11)。"; return 1; }
    local miss=''
    _gr_kw() { grep -Eiq -- "$1" "$GR_ANS" || miss+=" [$2]"; }
    _gr_kw 'init=/bin/bash' 'init=/bin/bash'
    _gr_kw 'systemd\.unit=rescue\.target' 'systemd.unit=rescue.target'
    _gr_kw 'emergency' 'emergency.target との違い'
    _gr_kw 'rd\.break' 'rd.break'
    _gr_kw 'initramfs|initrd' 'initramfs の段階'
    _gr_kw '/sysroot' '/sysroot'
    _gr_kw 'remount[, ]+rw|mount +-o +remount' 'rw 再マウント'
    _gr_kw 'autorelabel' 'SELinux .autorelabel'
    _gr_kw 'chroot' 'chroot'
    _gr_kw '(--r?bind|-o +r?bind)' '--bind/--rbind'
    _gr_kw '/dev' '/dev'
    _gr_kw '/proc' '/proc'
    _gr_kw '/sys' '/sys'
    _gr_kw 'grub-install' 'grub-install'
    _gr_kw 'update-grub|grub-mkconfig|grub2-mkconfig' 'update-grub/grub-mkconfig'
    [[ -z $miss ]] || { echo "answers.txt に不足している要点:$miss"; return 1; }
    echo 'PASS: ループデバイス上のGRUB導入(MBR+core.img)、grub-probe/blkidのUUID一致、再生成されたgrub.cfgの構文・エントリ・カーネル引数、レスキュー知識を確認しました。'
    echo '(VMコンソールでの本物のレスキュー起動は自動判定の対象外です)'
}

lab_reset() {
    _gr_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'この課題が作成した状態ではありません。'; return 1; }
    _gr_teardown || { echo 'umount/losetup -d に失敗しました。chroot等で使用中のシェルを閉じてください。'; return 1; }
    rm -f -- "$GR_IMG" "$GR_CHROOT" "$LAB_STATE/host-cfg.sha256" "$LAB_STATE/check-script.log" "$GR_ANS"
    rmdir -- "$GR_MNT" 2>/dev/null || true
    rm -f -- "$LAB_STATE/setup-done" "$LAB_STATE/fault" "$LAB_STATE/TASKS.txt"
    echo 'ループデバイスを解除し、専用イメージとファイルだけを削除しました。VMの /boot は変更していません。'
}
