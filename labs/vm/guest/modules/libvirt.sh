# title: 仮想化(libvirt/virsh)の基本操作 - テストドライバでドメイン・スナップショット・ネットワークを扱う
# roles: app
# Guest-only. Uses ONLY libvirt's mock "test:///default" driver through virsh: no hypervisor, no libvirtd, no root-owned libvirt state.
# Limitation: the test driver keeps state only inside ONE virsh connection and forgets it on exit. So the learner keeps a replay script
# (session.virsh) and XML files in the lab dir; replay.sh and "check" run the whole script in ONE connection and judge real virsh output.

_lv_paths() {
    [[ ${LAB_ID:-} == libvirt && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/libvirt ]] || { echo 'libvirt: unexpected lab context' >&2; return 1; }
    LV_DIR=/var/lib/dojo-libvirt-lab
    LV_DOM=dojo-web01
    LV_NET=dojo-isolated
    LV_FILES=(session.virsh web01.xml isolated.xml replay.sh)
    local f
    [[ ! -L $LV_DIR ]] || { echo 'libvirt: unexpected lab context (symlink)' >&2; return 1; }
    for f in "${LV_FILES[@]}"; do [[ ! -L $LV_DIR/$f ]] || { echo 'libvirt: unexpected lab context (symlink)' >&2; return 1; }; done
}

_lv_ip2int() { local IFS=.; set -- $1; echo $(( ($1 << 24) + ($2 << 16) + ($3 << 8) + $4 )); }

_lv_sec() { awk -v s="@@$1" '$0 == s {on=1; next} /^@@/ {on=0} on' <<<"$LV_OUT"; }

# Replays the learner's session.virsh and then probes, all in ONE test-driver connection. Sets LV_OUT / LV_RC.
_lv_run() {
    local script=$LV_DIR/session.virsh
    [[ -f $script && ! -L $script ]] || { LV_OUT="$script がありません。"; LV_RC=1; return 1; }
    LV_OUT=$({
        cat -- "$script"; echo
        cat <<PROBE
echo @@state
domstate $LV_DOM
echo @@info
dominfo $LV_DOM
echo @@xml
dumpxml $LV_DOM
echo @@snaps
snapshot-list $LV_DOM --name
echo @@netinfo
net-info $LV_NET
echo @@netxml
net-dumpxml $LV_NET
echo @@defnet
net-dumpxml default
echo @@end
PROBE
    } | (cd "$LV_DIR" && virsh -c test:///default 2>&1)) && LV_RC=0 || LV_RC=$?
    # virsh echoes each command after a 'virsh # ' prompt when stdin is a pipe; drop those so sections hold only real output
    LV_OUT=$(sed '/^virsh # /d' <<<"$LV_OUT")
    return "$LV_RC"
}

# Returns 0 and prints nothing on success; otherwise prints the first problem found.
_lv_judge() {
    _lv_run || { echo "session.virsh の再生が途中で失敗しました(virshの出力末尾):"; tail -n 6 <<<"$LV_OUT"; return 1; }
    grep -qx '@@end' <<<"$LV_OUT" || { echo 'session.virsh が quit/exit 等で判定コマンドの前に終わっています。'; return 1; }
    [[ $(_lv_sec state | head -1) == running ]] || { echo "$LV_DOM が running ではありません。"; return 1; }
    local info; info=$(_lv_sec info)
    grep -Eq '^CPU\(s\):[[:space:]]+2$' <<<"$info" || { echo "$LV_DOM の vCPU が 2 ではありません(setvcpus)。"; return 1; }
    grep -Eq '^Max memory:[[:space:]]+1048576 KiB' <<<"$info" || { echo "$LV_DOM の最大メモリが 1GiB ではありません(定義XMLのmemory)。"; return 1; }
    grep -Eq '^Used memory:[[:space:]]+786432 KiB' <<<"$info" || { echo "$LV_DOM の現在メモリが 768MiB ではありません(setmem)。"; return 1; }
    grep -Eq '^Autostart:[[:space:]]+enable' <<<"$info" || { echo "$LV_DOM の autostart が有効ではありません。"; return 1; }
    local xml; xml=$(_lv_sec xml)
    grep -q '<disk ' <<<"$xml" && grep -q '<interface ' <<<"$xml" || { echo "dumpxml に disk と interface がありません。"; return 1; }
    [[ -n $(_lv_sec snaps | tr -d '[:space:]') ]] || { echo "$LV_DOM のスナップショットがありません。"; return 1; }
    local ninfo; ninfo=$(_lv_sec netinfo)
    grep -Eq '^Active:[[:space:]]+yes' <<<"$ninfo" || { echo "$LV_NET が active ではありません(net-start)。"; return 1; }
    grep -Eq '^Autostart:[[:space:]]+yes' <<<"$ninfo" || { echo "$LV_NET の autostart が有効ではありません。"; return 1; }
    grep -Eq "<forward mode=['\"]nat['\"]" <<<"$(_lv_sec netxml)" || { echo "$LV_NET が NAT(forward mode='nat')ではありません。"; return 1; }
    local a1 m1 a2 m2 re="<ip address=['\"]([0-9.]+)['\"] netmask=['\"]([0-9.]+)['\"]"
    [[ $(_lv_sec netxml) =~ $re ]] || { echo "$LV_NET の ip address/netmask を読めません。"; return 1; }
    a1=${BASH_REMATCH[1]}; m1=${BASH_REMATCH[2]}
    [[ $(_lv_sec defnet) =~ $re ]] || { echo 'default ネットワークの範囲を読めません。'; return 1; }
    a2=${BASH_REMATCH[1]}; m2=${BASH_REMATCH[2]}
    local m=$(( $(_lv_ip2int "$m1") & $(_lv_ip2int "$m2") ))
    if (( ( $(_lv_ip2int "$a1") & m ) == ( $(_lv_ip2int "$a2") & m ) )); then
        echo "$LV_NET の範囲($a1/$m1)が default($a2/$m2)と重なっています。"; return 1
    fi
    return 0
}

lab_setup() {
    _lv_paths || return 1
    command -v virsh >/dev/null || { echo 'virsh がありません。次を実行してから再度setupしてください:'; echo '  sudo apt-get install -y libvirt-clients'; return 1; }
    virsh -c test:///default version >/dev/null 2>&1 || { echo 'virsh のテストドライバ(test:///default)に接続できません。libvirt-clients を確認してください。'; return 1; }
    [[ ! -e $LV_DIR ]] || { echo "$LV_DIR が既にあります。既存データを上書きしません。"; return 1; }
    mkdir -p -- "$LV_DIR" || return 1
    cat > "$LV_DIR/session.virsh" <<'S'
# virsh のコマンドを1行1コマンドで書く(この行はコメント)。上から順に1接続で実行される。
S
    cat > "$LV_DIR/replay.sh" <<'S'
#!/bin/bash
# session.virsh を test:///default の1接続で最初から再生する。状態は接続終了で消えるため毎回ここから作り直す。
cd "$(dirname "$0")" && exec virsh -c test:///default < session.virsh
S
    chmod 755 "$LV_DIR/replay.sh"
    if [[ -n ${SUDO_USER:-} ]] && id "$SUDO_USER" >/dev/null 2>&1; then chown -R "$SUDO_USER" -- "$LV_DIR"; fi
    cat > "$LAB_STATE/TASKS.txt" <<TASK
この課題はapp VMで行う。ハイパーバイザは使わず、libvirt の模擬ドライバ test:///default だけを使う
(接続: virsh -c test:///default)。注意: このドライバの状態は virsh を終了すると消える。
そのため作業場 $LV_DIR の session.virsh に virsh コマンドを書き、replay.sh で毎回再生する。
(実機の KVM では domain type='kvm'、接続は qemu:///system。ここでは type='test'。)

1. 対話で観察: virsh -c test:///default を起動し list --all / net-list --all / pool-list --all を見る。
2. $LV_DIR/web01.xml にドメイン $LV_DOM を書く: memory 1GiB(最大)、currentMemory 512MiB、
   vcpu は最大4で現在1(current属性)、disk(file)、interface。type='test'、<os><type>hvm</type></os>。
   virsh の dumpxml で既存ドメインの形を参考にする。
3. session.virsh に: define → start → setmem で 768MiB → setvcpus で 2 → snapshot-create-as → autostart。
   途中で suspend/resume/dominfo/dumpxml を挟んで観察してよい(出力は replay.sh で見る)。
4. $LV_DIR/isolated.xml に NAT ネットワーク $LV_NET を書く(default の範囲と重ならない /24)。
   session.virsh に net-define / net-start / net-autostart を足す。
5. $LV_DOM を shutdown/destroy/undefine する練習は、別名のドメインで行う(最終状態では $LV_DOM は起動中)。
6. sudo dojo-vm-lab libvirt break  (XML・ネットワーク範囲に故障を入れる。replay.sh の失敗を読んで直す)
7. sudo dojo-vm-lab libvirt check  (session.virsh を1接続で再生し、実際の virsh の出力で判定)
8. sudo dojo-vm-lab libvirt reset  ($LV_DIR だけ削除)
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudo cat で読めます)。"
    cat "$LAB_STATE/TASKS.txt"
    touch "$LAB_STATE/setup-done"
}

lab_break() {
    _lv_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo '既に故障状態です。'; return 1; }
    [[ -f $LV_DIR/web01.xml && -f $LV_DIR/isolated.xml ]] || { echo 'まず web01.xml と isolated.xml を作成し、正しく動くようにします。'; return 1; }
    _lv_judge >/dev/null || { echo 'まず手順どおり完成させ、check相当の状態にしてからbreakします。'; return 1; }
    cp -- "$LV_DIR/web01.xml" "$LAB_STATE/bak.web01.xml"; cp -- "$LV_DIR/isolated.xml" "$LAB_STATE/bak.isolated.xml"
    sed -i -E "0,/<memory unit=['\"][^'\"]*['\"]/s//<memory unit='MegaBytez'/; s#</devices>#</device>#" "$LV_DIR/web01.xml"
    sed -i -E "0,/<ip address=['\"][0-9.]+['\"]/s//<ip address='192.168.122.1'/" "$LV_DIR/isolated.xml"
    if grep -q MegaBytez "$LV_DIR/web01.xml" && grep -q '</device>' "$LV_DIR/web01.xml" && grep -q "192.168.122.1" "$LV_DIR/isolated.xml" && ! _lv_judge >/dev/null; then
        touch "$LAB_STATE/fault"
        echo 'web01.xml(メモリ単位・閉じタグ)と isolated.xml(default と重なる範囲)を壊しました。replay.sh を実行して読み、直してください。'
    else
        cp -- "$LAB_STATE/bak.web01.xml" "$LV_DIR/web01.xml"; cp -- "$LAB_STATE/bak.isolated.xml" "$LV_DIR/isolated.xml"
        rm -f -- "$LAB_STATE/bak.web01.xml" "$LAB_STATE/bak.isolated.xml"
        echo '故障を再現できませんでした(元に戻しました)。'; return 1
    fi
}

lab_check() {
    _lv_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まず完成させ、breakで障害を作ります。'; return 1; }
    local msg
    msg=$(_lv_judge) || { echo "$msg"; return 1; }
    echo 'PASS: session.virsh を test:///default の1接続で再生し、実際の virsh 出力でドメイン(running/2vCPU/768MiB/snapshot/autostart)とNATネットワーク(active/autostart/範囲非重複)を確認しました。'
}

lab_reset() {
    _lv_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'この課題が作成した状態ではありません。'; return 1; }
    local f
    for f in "${LV_FILES[@]}"; do rm -f -- "${LV_DIR:?}/${f:?}"; done
    rmdir -- "${LV_DIR:?}" 2>/dev/null || echo "$LV_DIR に学習者の他のファイルが残っているため、ディレクトリは残しました。"
    rm -f -- "${LAB_STATE:?}/setup-done" "${LAB_STATE:?}/fault" "${LAB_STATE:?}/TASKS.txt" "${LAB_STATE:?}/bak.web01.xml" "${LAB_STATE:?}/bak.isolated.xml"
    echo '作業場の専用ファイルだけを削除しました(libvirtの状態は接続ごとに消えるため他に残りません)。'
}
