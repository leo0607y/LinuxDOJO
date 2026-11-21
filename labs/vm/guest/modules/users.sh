# title: ユーザー・グループ・sudo最小権限と事故からの復旧
# roles: app
# Guest-only. Creates one dedicated group; the learner creates dojo-alice and a sudoers.d drop-in.
# Allowed-command checks use `sudo -l` only: the permitted command is never actually executed.

_users_paths() {
    [[ ${LAB_ID:-} == users && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/users ]] || { echo 'users: unexpected lab context' >&2; return 1; }
    U_USER=dojo-alice
    U_GROUP=dojo-ops
    U_SUDOERS=/etc/sudoers.d/dojo-users
    U_HOME=/home/dojo-alice
}

_users_sudo_allows() { runuser -u "$U_USER" -- timeout 10 sudo -n -l "$@" >/dev/null 2>&1; }

# Account facts: real getent/id/chage output, not file contents.
_users_account_ok() {
    local entry uid gid home shell groups g
    entry=$(getent passwd "$U_USER") || { echo "$U_USER が存在しません。useradd -m -s /bin/bash -G $U_GROUP で作成します。"; return 1; }
    IFS=: read -r _ _ uid gid _ home shell <<<"$entry"
    (( uid >= 1000 && gid != 0 )) || { echo 'UID/GIDが通常ユーザーの範囲ではありません。'; return 1; }
    [[ $home == "$U_HOME" && -d $U_HOME && ! -L $U_HOME && $(stat -c %u "$U_HOME") == "$uid" ]] || { echo 'ホームディレクトリの存在と所有者を確認します。'; return 1; }
    [[ $shell == /bin/bash ]] || { echo "ログインシェルが /bin/bash ではありません: $shell"; return 1; }
    grep -qx -- "$shell" /etc/shells || return 1
    groups=" $(id -nG "$U_USER") "
    [[ $groups == *" $U_GROUP "* ]] || { echo "$U_GROUP グループに所属していません。"; return 1; }
    for g in sudo admin wheel root adm docker lxd; do
        [[ $groups != *" $g "* ]] || { echo "管理者系グループ $g に所属しています。"; return 1; }
    done
    chage -l "$U_USER" | grep -q '^Account expires.*: never' || { echo 'アカウントが期限切れ/無効化されています。'; return 1; }
}

_users_sudoers_ok() {
    [[ -f $U_SUDOERS && ! -L $U_SUDOERS ]] || { echo "$U_SUDOERS がありません。"; return 1; }
    [[ $(stat -c '%a %U %G' "$U_SUDOERS") == '440 root root' ]] || { echo 'sudoersは 0440 root:root にします。'; return 1; }
    visudo -cf "$U_SUDOERS" >/dev/null 2>&1 || { echo 'sudoersの構文が不正です。visudo -cf で確認します。'; return 1; }
    visudo -c >/dev/null 2>&1 || { echo 'sudoers全体の構文検査(visudo -c)に失敗しています。'; return 1; }
    _users_sudo_allows /usr/bin/systemctl is-active ssh || { echo '許可すべきコマンドが sudo -l で許可されていません。'; return 1; }
    local denied
    for denied in '/usr/bin/id' '/bin/bash' '/usr/bin/systemctl' '/usr/bin/systemctl stop ssh' '/usr/bin/systemctl is-active ssh extra'; do
        # shellcheck disable=SC2086
        ! _users_sudo_allows $denied || { echo "許可が広すぎます: $denied も実行できる設定です。"; return 1; }
    done
    ! runuser -u "$U_USER" -- timeout 10 sudo -n -l 2>/dev/null | grep -Eq '\) (NOPASSWD: )?ALL$' || { echo 'ALL を許可する規則が残っています。'; return 1; }
}

lab_setup() {
    _users_paths || return 1
    if getent group "$U_GROUP" >/dev/null || getent passwd "$U_USER" >/dev/null || [[ -e $U_SUDOERS || -L $U_SUDOERS ]]; then
        echo '同名のグループ/ユーザー/sudoersが既にあります。既存のものは使わず変更もしません。'; return 1
    fi
    command -v visudo >/dev/null && command -v runuser >/dev/null && [[ -d /etc/sudoers.d ]] || return 1
    visudo -c >/dev/null || { echo '先にsudoの既存設定エラーを直してください。'; return 1; }
    groupadd "$U_GROUP"
    getent group "$U_GROUP" | cut -d: -f3 > "$LAB_STATE/ops.gid"
    touch "$LAB_STATE/owns-group"
    cat > "$LAB_STATE/TASKS.txt" <<'TASK'
app VMのubuntuユーザーで、sudo を付けて操作する。
1. 専用グループ dojo-ops は作成済み (getent group dojo-ops)。
2. ユーザー dojo-alice を作成: ホームあり・シェルは /bin/bash・dojo-ops に所属。
   (useradd のオプション -m -s -G。sudo/adminグループには入れない)
3. /etc/sudoers.d/dojo-users を作る。dojo-alice に「systemctl is-active ssh」だけ
   パスワードなしで許可する。ファイルは root:root 0440。
   直接編集せず、一時ファイルを visudo -cf で検証してから install で置く。
   構文エラーを置くと sudo 全体が壊れる。必ず visudo -cf / visudo -c を使う。
4. 確認: id dojo-alice / getent passwd dojo-alice / sudo -l -U dojo-alice
   sudo runuser -u dojo-alice -- sudo -n -l /usr/bin/id  (許可されないはず)
5. sudo dojo-vm-lab users break   (権限の事故を再現: 何が変わったか自分で調べる)
6. 調査と修復: シェル・グループ・sudoersを元の最小権限に戻す。ALLのまま放置は不正解。
   sudo dojo-vm-lab users check
7. 終了後 sudo dojo-vm-lab users reset (dojo-alice・dojo-ops・sudoersを削除)
checkは許可コマンドを実行せず sudo -l で判定する。
TASK
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _users_paths || return 1
    [[ -f $LAB_STATE/owns-group && ! -e $LAB_STATE/fault ]] || { echo 'setup済みで未breakの状態から実行します。'; return 1; }
    [[ $(getent group "$U_GROUP" | cut -d: -f3) == "$(cat "$LAB_STATE/ops.gid")" ]] || return 1
    _users_account_ok || return 1
    _users_sudoers_ok || return 1
    getent passwd "$U_USER" | cut -d: -f3,4 | tr ':' ' ' > "$LAB_STATE/alice.ids"
    local tmp="$LAB_STATE/sudoers.broken"
    printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$U_USER" > "$tmp"
    visudo -cf "$tmp" >/dev/null || { rm -f -- "$tmp"; return 1; }
    usermod -s /usr/sbin/nologin "$U_USER"
    gpasswd -d "$U_USER" "$U_GROUP" >/dev/null
    install -o root -g root -m 0440 "$tmp" "$U_SUDOERS"
    rm -f -- "$tmp"
    visudo -c >/dev/null || { echo 'sudoers構文を確認できません。'; return 1; }
    touch "$LAB_STATE/fault"
    echo "事故が発生しました。$U_USER のシェル・グループ・sudo権限を調べて最小権限に戻します。"
}

lab_check() {
    _users_paths || return 1
    [[ -f $LAB_STATE/fault && -f $LAB_STATE/alice.ids ]] || { echo 'まずuserを作成・sudo設定し、breakで事故を作ります。'; return 1; }
    local ids; ids=$(getent passwd "$U_USER" | cut -d: -f3,4 | tr ':' ' ') || true
    [[ $ids == "$(cat "$LAB_STATE/alice.ids")" ]] || { echo 'ユーザーを作り直さず、既存のdojo-aliceを修復します。'; return 1; }
    [[ $(getent group "$U_GROUP" | cut -d: -f3) == "$(cat "$LAB_STATE/ops.gid")" ]] || return 1
    _users_account_ok || return 1
    _users_sudoers_ok || return 1
    echo 'PASS: アカウント・グループ・シェル・sudoers(0440/visudo)・最小権限(sudo -lで判定)の復旧を確認しました。'
}

lab_reset() {
    _users_paths || return 1
    [[ -f $LAB_STATE/owns-group ]] || { echo 'この課題が作成したグループがありません。'; return 1; }
    local gid; gid=$(cat "$LAB_STATE/ops.gid")
    if getent passwd "$U_USER" >/dev/null; then
        [[ -f $LAB_STATE/alice.ids ]] || { echo "$U_USER の同一性を確認できません(breakの前)。自分で作成したなら手動で userdel -r してから再実行します。"; return 1; }
        [[ $(getent passwd "$U_USER" | cut -d: -f3,4 | tr ':' ' ') == "$(cat "$LAB_STATE/alice.ids")" ]] || { echo '記録したUID/GIDと違うため削除しません。'; return 1; }
        [[ ! -e $U_SUDOERS || -f $U_SUDOERS && ! -L $U_SUDOERS ]] || return 1
        rm -f -- "$U_SUDOERS"
        userdel --remove "$U_USER" || return 1
    else
        [[ ! -f $U_SUDOERS || -L $U_SUDOERS ]] || rm -f -- "$U_SUDOERS"
    fi
    if getent group "$U_GROUP" >/dev/null; then
        [[ $(getent group "$U_GROUP" | cut -d: -f3) == "$gid" ]] || { echo 'GIDが記録と違うためグループは削除しません。'; return 1; }
        groupdel "$U_GROUP" || return 1
    fi
    visudo -c >/dev/null || { echo 'sudoersに問題が残っています。visudo -cで確認してください。'; return 1; }
    rm -f -- "$LAB_STATE/owns-group" "$LAB_STATE/fault" "$LAB_STATE/ops.gid" "$LAB_STATE/alice.ids" "$LAB_STATE/sudoers.broken" "$LAB_STATE/TASKS.txt"
    echo '専用のユーザー・グループ・sudoersを削除しました。他のアカウントは変更していません。'
}
