#!/bin/bash
# title: udevルールで仮想デバイスに固定名・ENV・TAG・RUNを設定する
# roles: app
# Guest-only. Only a lab loop device and a lab dummy NIC are used. No scsi_debug, no real hardware.

_ud_ctx() {
    if [[ ${LAB_ID:-} != udev || ${LAB_VM_ROLE:-} != app || ${LAB_STATE:-} != /var/lib/linuxdojo-vm-lab/state/udev || ${LAB_ROOT:-} != /var/lib/linuxdojo-vm-lab ]]; then
        echo 'udev: unexpected lab context' >&2; return 1
    fi
    [[ ! -L $LAB_STATE ]] || { echo 'udev: unexpected lab context' >&2; return 1; }
    UD_RULES=/etc/udev/rules.d/90-dojo.rules
    UD_NIC=dojoud0
    [[ ! -L $UD_RULES ]] || { echo 'refusing symlinked rules file' >&2; return 1; }
}

_ud_tools() {
    local t
    for t in udevadm losetup ip python3 truncate; do
        command -v "$t" >/dev/null 2>&1 || { echo "missing tool: $t (sudo apt-get install -y udev mount iproute2)" >&2; return 1; }
    done
}

# Re-run udev only for the two lab devices.
_ud_trigger() {
    local action=$1 loop nic
    loop=$(cat "$LAB_STATE/loopdev" 2>/dev/null) || return 0
    [[ $loop == /dev/loop[0-9]* ]] && udevadm trigger --action="$action" --subsystem-match=block --sysname-match="${loop#/dev/}" || true
    [[ -d /sys/class/net/$UD_NIC ]] && udevadm trigger --action="$action" --subsystem-match=net --sysname-match="$UD_NIC" || true
    udevadm settle --timeout=10 || true
}

# Resolve the lab NIC (possibly renamed by a NAME= rule) via its recorded ifindex.
_ud_nic_name() {
    local idx name
    idx=$(cat "$LAB_STATE/nic-ifindex" 2>/dev/null) || return 1
    name=$(ip -o link | awk -F': ' -v i="$idx" '$1==i {sub(/@.*/,"",$2); print $2}')
    [[ -n $name ]] && printf '%s\n' "$name"
}

lab_setup() {
    _ud_ctx || return 1
    _ud_tools || return 1
    if [[ -e $UD_RULES && ! -f $LAB_STATE/owns-rules ]]; then
        echo "$UD_RULES は別用途で存在します。変更しません。" >&2; return 1
    fi
    install -d -m 0700 "$LAB_STATE"
    install -d -m 0755 "$LAB_STATE/run"
    if [[ ! -f $LAB_STATE/loopdev ]]; then
        truncate -s 8M "$LAB_STATE/disk.img"
        losetup --find --show "$LAB_STATE/disk.img" > "$LAB_STATE/loopdev"
    fi
    if [[ ! -f $LAB_STATE/nic-ifindex ]]; then
        ip link show "$UD_NIC" >/dev/null 2>&1 && { echo "$UD_NIC already exists; refusing" >&2; return 1; }
        ip link add "$UD_NIC" type dummy
        cat "/sys/class/net/$UD_NIC/ifindex" > "$LAB_STATE/nic-ifindex"
    fi
    local loop; loop=$(cat "$LAB_STATE/loopdev")
    cat > "$LAB_STATE/TASKS.txt" <<EOF2
実習デバイス: ループデバイス $loop (バッキングファイル $LAB_STATE/disk.img) とダミーNIC $UD_NIC。これ以外には触れません。
1. sudo dojo-vm-lab udev break で壊れたルール /etc/udev/rules.d/90-dojo.rules を作ります。
2. 観察: udevadm info -a -n $loop | less / udevadm info -q property -n $loop / udevadm monitor --udev --property (別端末で trigger)
3. ルールを直します(先頭のコメント行は残す)。構文エラー1つとマッチキーの誤り2つがあります。
   ループ側: 一致条件は実在する属性で、バッキングファイルが $LAB_STATE/disk.img のデバイスだけに限る。
             SYMLINK+="dojo-disk"、ENV{DOJO_ROLE}="lab"、TAG+="dojo"、RUN+= で $LAB_STATE/run/ 配下のファイルを touch するだけ。
   NIC側: $UD_NIC だけに一致し、ENV{DOJO_NIC}="lab" を付ける(NAME の変更は任意)。
4. 検証: udevadm test /sys/class/block/${loop#/dev/} (副作用に注意) / udevadm control --reload /
   udevadm trigger --action=add --subsystem-match=block --attr-match=loop/backing_file=$LAB_STATE/disk.img
5. sudo dojo-vm-lab udev check。checkは自分で同じ範囲にtriggerし、シンボリックリンクとudevadm infoの値、RUNの実行を確認します。
RUNで使えるのは $LAB_STATE/run/ 配下への touch、または同ディレクトリへの echo >> だけです。PROGRAM/IMPORT{program}は不可。
EOF2
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _ud_ctx || return 1
    [[ -f $LAB_STATE/loopdev && -f $LAB_STATE/nic-ifindex ]] || { echo 'run setup first' >&2; return 1; }
    if [[ -e $UD_RULES && ! -f $LAB_STATE/owns-rules ]]; then
        echo "$UD_RULES は別用途で存在します。変更しません。" >&2; return 1
    fi
    rm -f -- "$LAB_STATE"/run/*
    cat > "$UD_RULES" <<EOF2
# LinuxDOJO VM module: udev (lab devices only)
# BUG: syntax error (missing comma), wrong match key
SUBSYSTEM=="block", ATTR{loop/backing_files}=="$LAB_STATE/disk.img" SYMLINK+="dojo-disk", ENV{DOJO_ROLE}="lab"
SUBSYSTEM=="net", KERNEL=="dojo-ud0", ENV{DOJO_NIC}="lab"
EOF2
    touch "$LAB_STATE/owns-rules"
    udevadm control --reload || true
    _ud_trigger add
    touch "$LAB_STATE/broken-at"
    echo "壊れたルールを作成しました: $UD_RULES (/dev/dojo-disk はまだ存在しません)"
}

lab_check() {
    _ud_ctx || return 1
    [[ -f $LAB_STATE/broken-at && -f $UD_RULES && -f $LAB_STATE/owns-rules ]] || { echo 'run break and repair first' >&2; return 1; }
    local loop nic
    loop=$(cat "$LAB_STATE/loopdev") || return 1
    [[ $(losetup -j "$LAB_STATE/disk.img" | cut -d: -f1) == "$loop" ]] || { echo 'lab loop device is gone; run reset and setup' >&2; return 1; }
    nic=$(_ud_nic_name) || { echo 'lab NIC is gone; run reset and setup' >&2; return 1; }
    python3 - "$UD_RULES" "$LAB_STATE" "$loop" <<'PY' || return 1
import re, sys
from pathlib import Path
rules, state, loop = sys.argv[1], sys.argv[2], sys.argv[3]
lines, buf = [], ''
for raw in Path(rules).read_text().splitlines():
    s = raw.rstrip()
    if s.endswith('\\'):
        buf += s[:-1] + ' '; continue
    s = (buf + s).strip(); buf = ''
    if s and not s.startswith('#'): lines.append(s)
tok = re.compile(r'\s*(\w+(?:\{[^}]+\})?)\s*(==|!=|\+=|-=|:=|=)\s*"([^"]*)"\s*(?:,|$)')
lab_match = {('ATTR{loop/backing_file}', state + '/disk.img'), ('KERNEL', loop[5:]), ('KERNEL', 'dojoud0'), ('KERNEL', 'dojo-nic0')}
allowed = ('SYMLINK', 'ENV', 'TAG', 'RUN', 'NAME')
safe = [re.compile(r'^(/usr/bin/touch|/bin/touch) ' + re.escape(state) + r'/run/[A-Za-z0-9._-]+$'),
        re.compile(r"^/bin/sh -c 'echo [A-Za-z0-9 ._%{}$:=/-]* >> " + re.escape(state) + r"/run/[A-Za-z0-9._-]+'$")]
errs = []
if not lines: errs.append('no rules in the file')
for ln in lines:
    pos, items = 0, []
    while pos < len(ln):
        m = tok.match(ln, pos)
        if not m: errs.append('syntax error near: ' + ln[pos:pos + 50]); break
        items.append(m.groups()); pos = m.end()
    else:
        if not any(op == '==' and (k, v) in lab_match for k, op, v in items):
            errs.append('rule is not restricted to a lab device: ' + ln[:70])
        for k, op, v in items:
            if op in ('==', '!='): continue
            if k.split('{')[0] not in allowed: errs.append('assignment not allowed in this lab: ' + k)
            if k == 'RUN' or k.startswith('RUN{'):
                if k != 'RUN' or not any(p.match(v) for p in safe):
                    errs.append('RUN must only touch/echo into the lab run directory: ' + v)
if errs:
    print('FAIL: ' + '; '.join(errs), file=sys.stderr); sys.exit(1)
PY
    if udevadm verify --help >/dev/null 2>&1; then
        udevadm verify "$UD_RULES" >/dev/null 2>&1 || { echo 'FAIL: udevadm verify reports errors in the rules' >&2; return 1; }
    fi
    # Statically safe: now exercise it for the lab devices only.
    rm -f -- "$LAB_STATE"/run/*
    udevadm control --reload || true
    local t0; t0=$(date +%s.%N)
    sleep 1
    _ud_trigger add
    nic=$(_ud_nic_name) || { echo 'FAIL: lab NIC vanished' >&2; return 1; }
    local link=/dev/dojo-disk
    [[ -L $link && $(readlink -f "$link") == "$loop" ]] || { echo "FAIL: $link must be a symlink to $loop" >&2; return 1; }
    local props
    props=$(udevadm info -q property -n "$link") || return 1
    grep -qx 'DOJO_ROLE=lab' <<<"$props" || { echo 'FAIL: DOJO_ROLE=lab missing in udevadm info' >&2; return 1; }
    grep -Eq '^TAGS=.*:dojo:' <<<"$props" || { echo 'FAIL: tag dojo missing in udevadm info' >&2; return 1; }
    udevadm info -q property -p "/sys/class/net/$nic" | grep -qx 'DOJO_NIC=lab' || { echo "FAIL: DOJO_NIC=lab missing on $nic" >&2; return 1; }
    python3 - "$LAB_STATE/run" "$t0" <<'PY' || { echo 'FAIL: RUN did not execute (nothing written under run/ after the check trigger)' >&2; return 1; }
import sys
from pathlib import Path
t0 = float(sys.argv[2])
files = [p for p in Path(sys.argv[1]).iterdir() if p.is_file()]
sys.exit(0 if any(p.stat().st_mtime >= t0 for p in files) else 1)
PY
    echo "PASS: $link -> $loop, properties/tag set, NIC $nic labelled, RUN fired, rules confined to lab devices"
}

lab_reset() {
    _ud_ctx || return 1
    local loop
    if [[ -f $LAB_STATE/owns-rules && -f $UD_RULES ]]; then
        rm -f -- "$UD_RULES"
        udevadm control --reload || true
        _ud_trigger add
    fi
    if loop=$(cat "$LAB_STATE/loopdev" 2>/dev/null) && [[ $loop == /dev/loop[0-9]* ]] \
        && [[ $(losetup -j "$LAB_STATE/disk.img" 2>/dev/null | cut -d: -f1) == "$loop" ]]; then
        losetup -d "$loop" || true
    fi
    local nic
    if nic=$(_ud_nic_name) && ip -d link show "$nic" 2>/dev/null | grep -qw dummy; then
        ip link del "$nic" || true
    fi
    [[ -L /dev/dojo-disk && ! -e /dev/dojo-disk ]] && rm -f /dev/dojo-disk
    rm -rf -- "$LAB_STATE"
    echo 'udev: removed only the rules file, lab devices, symlink and state'
}
