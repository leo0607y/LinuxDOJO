# title: カーネルパラメータ(sysctl)とカーネルモジュール(modprobe)の永続化とブラックリスト
# roles: app
# Guest-only. Touches only vm.swappiness / vm.vfs_cache_pressure and the harmless softdog module; originals are restored by reset.

_sc_paths() {
    [[ ${LAB_ID:-} == sysctl && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/sysctl ]] || { echo 'sysctl: unexpected lab context' >&2; return 1; }
    SC_CONF=/etc/sysctl.d/60-dojo.conf
    SC_OVERRIDE=/etc/sysctl.d/99-dojo-override.conf
    SC_BLACKLIST=/etc/modprobe.d/dojo-blacklist.conf
    SC_MOD=softdog
    SC_KEYS=(vm.swappiness vm.vfs_cache_pressure)
    SC_WANT_SWAPPINESS=10
    SC_WANT_CACHE=50
    [[ ! -L $SC_CONF && ! -L $SC_OVERRIDE && ! -L $SC_BLACKLIST && ! -L /etc/sysctl.d && ! -L /etc/modprobe.d ]] || { echo 'sysctl: unexpected lab context (symlink)' >&2; return 1; }
}

_sc_loaded() { lsmod | awk -v m="$SC_MOD" '$1 == m {found=1} END {exit !found}'; }

lab_setup() {
    _sc_paths || return 1
    [[ ! -e $SC_CONF && ! -e $SC_OVERRIDE && ! -e $SC_BLACKLIST ]] || { echo '専用ファイルが既にあります。既存データを上書きしません。'; return 1; }
    command -v sysctl >/dev/null && command -v modprobe >/dev/null && command -v lsmod >/dev/null && command -v modinfo >/dev/null || { echo 'sysctl/kmodコマンドがありません(procps, kmod)。'; return 1; }
    local key
    for key in "${SC_KEYS[@]}"; do
        sysctl -n "$key" >/dev/null || { echo "$key を読めません。"; return 1; }
        printf '%s\n' "$(sysctl -n "$key")" > "$LAB_STATE/orig.$key"
    done
    modinfo "$SC_MOD" >/dev/null 2>&1 || { echo "このカーネルに $SC_MOD モジュールがありません(linux-modules-extra等が必要な場合があります)。"; return 1; }
    if _sc_loaded; then echo "$SC_MOD は既にロード済みです。実習を開始できません。"; return 1; fi
    cat > "$LAB_STATE/TASKS.txt" <<'TASK'
この課題はapp VMで root (sudo) で操作する。安全な値だけを使う:
  vm.swappiness と vm.vfs_cache_pressure、およびモジュール softdog。ip_forward等は触らない。

[パラメータ]
1. 現在値を sysctl -n で読む。メモする。
2. sysctl -w で vm.swappiness を 10 に一時変更。/proc/sys/vm/ の対応ファイルとも見比べる。
3. 再起動で消える。永続化: /etc/sysctl.d/60-dojo.conf に
   vm.swappiness = 10 と vm.vfs_cache_pressure = 50 を書く。
4. sysctl --system で再適用。出力の "Applying" の順序を観察し、sysctl -n で実行値を確認。
5. sudo dojo-vm-lab sysctl break を実行。設定を追加された状態で再度 sysctl --system を実行し、
   エラー出力と実行値を比較する。適用順(ファイル名のソート)と綴りを調べ、直す。
   60-dojo.conf の値を実行値に合わせるために書き換えたり、別の値で妥協するのは不正解。

[モジュール]
6. modinfo softdog で情報を見て、modprobe softdog でロード。lsmod で確認。
7. modprobe -r softdog でアンロード。
8. /etc/modprobe.d/dojo-blacklist.conf に softdog を禁止する設定を書く。
   blacklist だけでは modprobe softdog の直接指定を止められない点を man modprobe.d で確認し、
   install 行でリダイレクトする。modprobe -c と modprobe -n -v softdog で効果を確認。
9. sudo dojo-vm-lab sysctl check
10. 終了後 sudo dojo-vm-lab sysctl reset (記録した元の実行値に戻し、専用ファイルのみ削除)
TASK
    echo "手順: $LAB_STATE/TASKS.txt (sudo cat で読めます)。"
    cat "$LAB_STATE/TASKS.txt"
    touch "$LAB_STATE/setup-done"
}

lab_break() {
    _sc_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -e $SC_OVERRIDE ]] || { echo '既に故障状態です。'; return 1; }
    [[ -f $SC_CONF && ! -L $SC_CONF ]] || { echo "まず $SC_CONF を作成します。"; return 1; }
    [[ $(sysctl -n vm.swappiness) == "$SC_WANT_SWAPPINESS" && $(sysctl -n vm.vfs_cache_pressure) == "$SC_WANT_CACHE" ]] || { echo 'まず設定を永続化し sysctl --system で適用して、実行値を期待値にします。'; return 1; }
    cat > "$SC_OVERRIDE" <<'CONF'
# LinuxDOJO sysctl lab (fault injected)
vm.swapiness = 5
vm.swappiness = 100
vm.vfs_cache_pressure = 500
CONF
    sysctl --system > "$LAB_STATE/break-apply.log" 2>&1 || true
    if [[ $(sysctl -n vm.swappiness) == 100 && $(sysctl -n vm.vfs_cache_pressure) == 500 ]]; then
        touch "$LAB_STATE/fault"
        echo '再起動相当(sysctl --system)で値が書き換わりました。出力と適用順を調べて直してください。'
    else
        rm -f -- "$SC_OVERRIDE"; echo '故障を再現できませんでした。'; return 1
    fi
}

lab_check() {
    _sc_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずパラメータを永続化し、breakで障害を作ります。'; return 1; }
    [[ -f $SC_CONF && ! -L $SC_CONF ]] || { echo "$SC_CONF が必要です。"; return 1; }
    local out
    out=$(sysctl --system 2>&1) || true
    printf '%s\n' "$out" > "$LAB_STATE/check-apply.log"
    grep -q 'swapiness' <<<"$out" && { echo 'sysctl --system に綴り違いのキーのエラーが残っています。'; return 1; }
    local n60 n99
    n60=$(grep -n -F -- '/etc/sysctl.d/60-dojo.conf' <<<"$out" | head -1 | cut -d: -f1)
    [[ -n $n60 ]] || { echo 'sysctl --system が 60-dojo.conf を適用していません。'; return 1; }
    n99=$(grep -n -F -- "$SC_OVERRIDE" <<<"$out" | head -1 | cut -d: -f1)
    if [[ -n $n99 && $n99 -lt $n60 ]]; then echo '適用順が不正です。'; return 1; fi
    [[ $(sysctl -n vm.swappiness) == "$SC_WANT_SWAPPINESS" ]] || { echo "再適用後の vm.swappiness が $SC_WANT_SWAPPINESS ではありません。"; return 1; }
    [[ $(sysctl -n vm.vfs_cache_pressure) == "$SC_WANT_CACHE" ]] || { echo "再適用後の vm.vfs_cache_pressure が $SC_WANT_CACHE ではありません。"; return 1; }
    [[ -f $SC_BLACKLIST && ! -L $SC_BLACKLIST ]] || { echo "$SC_BLACKLIST が必要です。"; return 1; }
    local conf
    conf=$(modprobe -c 2>/dev/null) || return 1
    grep -Eq "^blacklist[[:space:]]+${SC_MOD}\$" <<<"$conf" || { echo 'modprobe -c に blacklist softdog がありません。'; return 1; }
    grep -Eq "^install[[:space:]]+${SC_MOD}[[:space:]]+/bin/(false|true)" <<<"$conf" || { echo 'modprobe -c に softdog の install リダイレクトがありません。'; return 1; }
    ! _sc_loaded || { echo 'softdog がロードされたままです。modprobe -r してください。'; return 1; }
    modprobe "$SC_MOD" >/dev/null 2>&1 || true
    if _sc_loaded; then
        modprobe -r "$SC_MOD" >/dev/null 2>&1 || true
        echo 'modprobe softdog で実際にロードできてしまいます。直接指定も止めてください。'; return 1
    fi
    modprobe -n -v "$SC_MOD" 2>&1 | grep -Eq '^install /bin/(false|true)' || { echo 'modprobe -n -v がインストールリダイレクトを示していません。'; return 1; }
    echo 'PASS: 実行値・sysctl.d の適用順と綴り・modprobe のブラックリストとリダイレクトを確認しました。'
}

lab_reset() {
    _sc_paths || return 1
    [[ -f $LAB_STATE/setup-done ]] || { echo 'この課題が作成した状態ではありません。'; return 1; }
    rm -f -- "$SC_CONF" "$SC_OVERRIDE" "$SC_BLACKLIST"
    if _sc_loaded; then modprobe -r "$SC_MOD" >/dev/null 2>&1 || rmmod "$SC_MOD" >/dev/null 2>&1 || true; fi
    local key
    for key in "${SC_KEYS[@]}"; do
        [[ -f $LAB_STATE/orig.$key ]] && sysctl -w "$key=$(cat "$LAB_STATE/orig.$key")" >/dev/null || true
        rm -f -- "$LAB_STATE/orig.$key"
    done
    rm -f -- "$LAB_STATE/setup-done" "$LAB_STATE/fault" "$LAB_STATE/TASKS.txt" "$LAB_STATE/break-apply.log" "$LAB_STATE/check-apply.log"
    echo '専用ファイルを削除し、実行値を元に戻しました。他のsysctl.d/modprobe.dは変更していません。'
}
