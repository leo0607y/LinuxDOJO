# title: tuned プロファイルの切替とカスタムプロファイル(tuned-adm)
# roles: app
# Guest-only. Records the original profile, adds only /etc/tuned/dojo-lab, and reset switches back and removes it.

_tu_paths() {
    [[ ${LAB_ID:-} == tuned && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/tuned ]] || { echo 'tuned: unexpected lab context' >&2; return 1; }
    TU_NAME=dojo-lab
    TU_DIR=/etc/tuned/$TU_NAME
    TU_CONF=$TU_DIR/tuned.conf
    TU_SWAP=15
    TU_SOMAX=2048
    [[ ! -L /etc/tuned && ! -L $TU_DIR && ! -L $TU_CONF ]] || { echo 'tuned: unexpected lab context (symlink)' >&2; return 1; }
}

_tu_active() { tuned-adm active 2>/dev/null | sed -n 's/^Current active profile:[[:space:]]*//p' | head -1; }

lab_setup() {
    _tu_paths || return 1
    command -v tuned-adm >/dev/null || { echo 'tuned-adm がありません。次を実行してから再度setupしてください:'; echo '  sudo apt-get install -y tuned'; return 1; }
    [[ ! -e $TU_DIR ]] || { echo "$TU_DIR が既にあります。既存データを上書きしません。"; return 1; }
    systemctl is-active --quiet tuned || { echo 'tuned サービスが動いていません。sudo systemctl enable --now tuned を実行してください。'; return 1; }
    local orig; orig=$(_tu_active)
    tuned-adm list 2>/dev/null | grep -q 'throughput-performance' || { echo 'throughput-performance プロファイルがありません。'; return 1; }
    printf '%s\n' "$orig" > "$LAB_STATE/orig.profile"
    sysctl -n vm.swappiness > "$LAB_STATE/orig.swappiness" && sysctl -n net.core.somaxconn > "$LAB_STATE/orig.somaxconn" || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
この課題はapp VMで root (sudo) で操作する。元のプロファイル「${orig:-なし}」は記録済み(resetで戻る)。

1. tuned-adm list / active / recommend を実行し、違いを説明できるようにする。
2. tuned-adm profile で別の組込プロファイルへ切替え、active と tuned-adm verify を見る。
3. $TU_CONF にカスタムプロファイル $TU_NAME を書く:
   [main] で throughput-performance を include、[sysctl] で
   vm.swappiness = $TU_SWAP と net.core.somaxconn = $TU_SOMAX、さらに無害な [cpu] か [script] 等を1つ。
   (ディレクトリ名がプロファイル名になる。tuned-adm list に出ることを確認)
4. tuned-adm profile $TU_NAME で適用。tuned-adm active / tuned-adm verify と sysctl -n で実値を確認。
5. sudo dojo-vm-lab tuned break  (誤ったプロファイルを入れる。verify・ログ(journalctl -u tuned)を読んで直す)
6. sudo dojo-vm-lab tuned check
7. sudo dojo-vm-lab tuned reset  (元プロファイルへ切替え、$TU_DIR を削除)
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudo cat で読めます)。"
    cat "$LAB_STATE/TASKS.txt"
    touch "$LAB_STATE/setup-done"
}

lab_break() {
    _tu_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo '既に故障状態です。'; return 1; }
    [[ -f $TU_CONF && ! -L $TU_CONF ]] || { echo "まず $TU_CONF を作成します。"; return 1; }
    [[ $(_tu_active) == "$TU_NAME" && $(sysctl -n vm.swappiness) == "$TU_SWAP" && $(sysctl -n net.core.somaxconn) == "$TU_SOMAX" ]] || { echo 'まず dojo-lab を適用し、実値を期待値にします。'; return 1; }
    cp -- "$TU_CONF" "$LAB_STATE/bak.tuned.conf"
    cat > "$TU_CONF" <<'CONF'
# LinuxDOJO tuned lab (fault injected)
[main]
sumary=broken dojo profile
include=throughput-performence

[sysctl
vm.swappiness = 15
net.core.somaxconn = lots
CONF
    tuned-adm profile "$TU_NAME" >"$LAB_STATE/break-apply.log" 2>&1 || true
    if ! tuned-adm verify >>"$LAB_STATE/break-apply.log" 2>&1 || [[ $(sysctl -n net.core.somaxconn) != "$TU_SOMAX" ]]; then
        touch "$LAB_STATE/fault"
        echo 'プロファイルを壊して適用し直しました。tuned-adm verify・active・journalctl -u tuned と sysctl -n で原因を調べて直してください。'
    else
        cp -- "$LAB_STATE/bak.tuned.conf" "$TU_CONF"; tuned-adm profile "$TU_NAME" >/dev/null 2>&1 || true
        rm -f -- "$LAB_STATE/bak.tuned.conf"; echo '故障を再現できませんでした(元に戻しました)。'; return 1
    fi
}

lab_check() {
    _tu_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まず完成させ、breakで障害を作ります。'; return 1; }
    [[ -f $LAB_STATE/orig.profile ]] || { echo '元プロファイルの記録がありません(setupからやり直してください)。'; return 1; }
    local orig; orig=$(cat "$LAB_STATE/orig.profile")
    [[ $orig != "$TU_NAME" ]] || { echo '記録された元プロファイルが不正です。'; return 1; }
    [[ -f $TU_CONF && ! -L $TU_CONF ]] || { echo "$TU_CONF が必要です。"; return 1; }
    tuned-adm list 2>/dev/null | grep -q -- "- $TU_NAME" || { echo "tuned-adm list に $TU_NAME が出ません(設定の構文を確認)。"; return 1; }
    # re-apply so the judged state comes from the current file, not a stale daemon state
    tuned-adm profile "$TU_NAME" >"$LAB_STATE/check-apply.log" 2>&1 || { echo "tuned-adm profile $TU_NAME が失敗します。"; tail -n 3 "$LAB_STATE/check-apply.log"; return 1; }
    [[ $(_tu_active) == "$TU_NAME" ]] || { echo "tuned-adm active が $TU_NAME ではありません。"; return 1; }
    tuned-adm verify >"$LAB_STATE/check-verify.log" 2>&1 || { echo 'tuned-adm verify が失敗します。'; tail -n 3 "$LAB_STATE/check-verify.log"; return 1; }
    [[ $(sysctl -n vm.swappiness) == "$TU_SWAP" ]] || { echo "実際の vm.swappiness が $TU_SWAP ではありません。"; return 1; }
    [[ $(sysctl -n net.core.somaxconn) == "$TU_SOMAX" ]] || { echo "実際の net.core.somaxconn が $TU_SOMAX ではありません。"; return 1; }
    echo 'PASS: tuned-adm active/verify と実際の sysctl 値を確認しました。元プロファイルの記録も保持されています。'
}

lab_reset() {
    _tu_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'この課題が作成した状態ではありません。'; return 1; }
    local orig; orig=$(cat "$LAB_STATE/orig.profile" 2>/dev/null || true)
    if [[ -n $orig && $orig != "$TU_NAME" ]]; then tuned-adm profile "$orig" >/dev/null 2>&1 || echo "元プロファイル $orig へ戻せませんでした。手動で tuned-adm profile $orig してください。"
    elif [[ $(_tu_active) == "$TU_NAME" ]]; then tuned-adm off >/dev/null 2>&1 || true; fi
    rm -f -- "${TU_CONF:?}"; rmdir -- "${TU_DIR:?}" 2>/dev/null || true
    local f
    for f in setup-done fault TASKS.txt orig.profile orig.swappiness orig.somaxconn bak.tuned.conf break-apply.log check-apply.log check-verify.log; do rm -f -- "${LAB_STATE:?}/$f"; done
    echo "元のプロファイル(${orig:-なし})へ戻し、$TU_DIR を削除しました。"
}
