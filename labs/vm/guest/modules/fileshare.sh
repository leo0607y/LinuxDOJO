#!/bin/bash
# title: 2台でNFSを共有し、root_squash・UID対応・永続マウントを検証する
# roles: app client
# app exports /srv/dojo-share (only to the client IP) via /etc/exports.d/dojo.exports; client mounts it.
# Needs nfs-kernel-server (app) / nfs-common (client). Samba is a separate follow-up (see TASKS).

FS_SHARE=/srv/dojo-share
FS_EXPORTS=/etc/exports.d/dojo.exports
FS_MNT=/mnt/dojo-share
FS_USER=dojo-nfs
FS_UID=4711
FS_BEGIN='# BEGIN LinuxDOJO fileshare'
FS_END='# END LinuxDOJO fileshare'
FS_UNIT_MARK='# LinuxDOJO VM module: fileshare'

_fs_ctx() {
    [[ ${LAB_ID:-} == fileshare && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/fileshare ]] || { echo 'fileshare: unexpected lab context' >&2; return 1; }
    case ${LAB_VM_ROLE:-} in app|client) ;; *) echo 'fileshare: unexpected lab context' >&2; return 1 ;; esac
    [[ ! -L $FS_SHARE && ! -L $FS_EXPORTS && ! -L $FS_MNT ]] || { echo 'fileshare: unexpected lab context' >&2; return 1; }
}

_fs_valid_ip() {
    python3 - "$1" <<'PY'
import ipaddress, sys
try:
    ip = ipaddress.IPv4Address(sys.argv[1])
    ok = any(ip in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
except ValueError:
    ok = False
raise SystemExit(0 if ok else 1)
PY
}

# $1 = file under LAB_STATE holding the peer IP (client-ip on app, app-ip on client)
_fs_peer() {
    local f=$LAB_STATE/$1 ip
    [[ -f $f ]] || { echo "相手VMのプライベートIPを1行で $f に保存してください（multipass info で確認）。" >&2; return 1; }
    ip=$(head -n1 "$f" | tr -d '[:space:]')
    _fs_valid_ip "$ip" || { echo "$f にはRFC1918のIPv4を1行で書いてください。" >&2; return 1; }
    FS_PEER=$ip
}

_fs_need_pkg() {
    if [[ $LAB_VM_ROLE == app ]]; then
        command -v exportfs >/dev/null && dpkg -s nfs-kernel-server >/dev/null 2>&1 && return 0
        echo '必要なパッケージがありません。次を実行してから setup をやり直してください:' >&2
        echo '  sudo apt install -y nfs-kernel-server' >&2
    else
        [[ -x /sbin/mount.nfs || -x /usr/sbin/mount.nfs ]] && dpkg -s nfs-common >/dev/null 2>&1 && return 0
        echo '必要なパッケージがありません。次を実行してから setup をやり直してください:' >&2
        echo '  sudo apt install -y nfs-common        # autofs を試すなら autofs も追加' >&2
    fi
    return 1
}

_fs_write_exports() {   # $1 = client spec, $2 = options
    install -d -m 0755 /etc/exports.d
    printf '%s\n%s %s(%s)\n' '# LinuxDOJO fileshare' "$FS_SHARE" "$1" "$2" > "$FS_EXPORTS"
    chmod 0644 "$FS_EXPORTS"
}

lab_setup() {
    _fs_ctx || return 1
    _fs_need_pkg || return 1
    if [[ $LAB_VM_ROLE == app ]]; then _fs_peer client-ip || return 1; fi
    [[ ! -f $LAB_STATE/owns-user ]] || { echo '既にsetup済みです。やり直すには reset します。'; return 1; }
    if getent passwd "$FS_USER" >/dev/null || getent passwd "$FS_UID" >/dev/null || getent group "$FS_UID" >/dev/null; then
        echo '専用ユーザー名またはUIDが使用済みです。'; return 1
    fi
    if [[ $LAB_VM_ROLE == app ]]; then
        [[ ! -e $FS_SHARE && ! -e $FS_EXPORTS ]] || { echo "$FS_SHARE か $FS_EXPORTS が既にあります。上書きしません。"; return 1; }
    else
        [[ ! -e $FS_MNT ]] || { echo "$FS_MNT が既にあります。上書きしません。"; return 1; }
    fi
    # Same name and UID on both VMs so NFSv4 name mapping and numeric IDs agree.
    useradd --uid "$FS_UID" --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$FS_USER" || return 1
    touch "$LAB_STATE/owns-user"
    if [[ $LAB_VM_ROLE == app ]]; then
        install -d -o "$FS_USER" -g "$FS_USER" -m 0775 "$FS_SHARE"
        printf 'dojo-share original\n' > "$FS_SHARE/README.txt"
        chown "$FS_USER:$FS_USER" "$FS_SHARE/README.txt"
        touch "$LAB_STATE/owns-share"
        printf '%s\n' "$FS_PEER" > "$LAB_STATE/approved-client"
        _fs_write_exports "$FS_PEER" 'rw,sync,root_squash,no_subtree_check'
        touch "$LAB_STATE/owns-exports"
        systemctl is-active --quiet nfs-server || touch "$LAB_STATE/nfs-was-inactive"
        systemctl enable --now nfs-server || return 1
        exportfs -ra || return 1
        cat > "$LAB_STATE/TASKS.txt" <<'TASK'
【app VM = NFSサーバ】/srv/dojo-share を /etc/exports.d/dojo.exports で client のIPだけに rw, root_squash で公開しました。
（/etc/exports 本体は編集しません。共有ディレクトリの所有者は専用ユーザー dojo-nfs (UID 4711) です）
1. exportfs -v で実際の公開オプションを読む。showmount -e localhost / ss -ltn で 2049 を確認。
2. client VM の手順に進む（マウント・書き込み・UID確認）。
3. この app で break を実行すると「広すぎる公開」を体験できます:
   sudo dojo-vm-lab fileshare break  → exports が `*` + no_root_squash になる。
   何が危険か考え、元の狭い設定に戻して exportfs -ra で反映する（exportsの編集だけでは反映されない）。
4. sudo dojo-vm-lab fileshare check （exportfs -v の実際のオプションで判定）
5. 終了後 sudo dojo-vm-lab fileshare reset

発展（本課題の対象外）: Samba(smbd)の共有と smbclient での許可/拒否は別の実習で扱う予定です。
TASK
        echo "app: NFS共有を公開しました。手順: $LAB_STATE/TASKS.txt"
    else
        install -d -m 0755 "$FS_MNT"
        touch "$LAB_STATE/owns-mnt"
        cat > "$LAB_STATE/TASKS.txt" <<TASK
【client VM = NFSクライアント】
1. app のプライベートIPを1行で $LAB_STATE/app-ip に保存する（multipass info）。
2. showmount -e <app-ip> で公開を確認し、$FS_MNT に NFSv4 でマウントする（mount -t nfs4 ...）。
3. root で書き込むとどうなるか（root_squash）、専用ユーザー dojo-nfs (UID 4711) で書くとファイルの所有者はどう見えるか確認する:
   ls -ln / stat -c '%u %U' 。dojo-nfs は nologin なので runuser -u dojo-nfs -- sh -c '...' などを使う。
4. 永続化する。次のどちらか:
   a) /etc/fstab に _netdev,nofail 付きで書く。次の2行で挟んだブロックにすること（resetはこのブロックだけ消す）:
        $FS_BEGIN
        $FS_END
   b) systemd の .mount ユニット（ファイル内に「$FS_UNIT_MARK」の行を入れる）
   ネットワーク未到達時にbootが止まらない理由を説明できるようにする。
5. sudo dojo-vm-lab fileshare break  → hard・タイムアウト無指定の状態でマウントされます。
   サーバが落ちたときのプロセスの挙動を考え、soft かつ短い timeo（50以下）で再マウントし直す。
   （softは書き込み破損のリスクもある。何を引き換えにしているか調べる）
6. 任意: autofs で /mnt/dojo-share を自動マウント・タイムアウト解放にしてみる（auto.master.d + map。本課題の判定対象外）。
7. sudo dojo-vm-lab fileshare check
8. 終了後 sudo dojo-vm-lab fileshare reset
TASK
        echo "client: 準備しました。手順: $LAB_STATE/TASKS.txt"
    fi
}

lab_break() {
    _fs_ctx || return 1
    [[ -f $LAB_STATE/owns-user ]] || { echo 'まず setup を実行します。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo '既に故障投入済みです。'; return 1; }
    if [[ $LAB_VM_ROLE == app ]]; then
        [[ -f $LAB_STATE/owns-exports ]] || return 1
        _fs_write_exports '*' 'rw,sync,no_root_squash,no_subtree_check'
        exportfs -ra || return 1
        touch "$LAB_STATE/fault"
        echo "公開設定を * + no_root_squash に変えました。exportfs -v で確認し、clientのIPだけ・root_squashに戻します。"
    else
        _fs_peer app-ip || return 1
        ! mountpoint -q "$FS_MNT" || { echo "$FS_MNT が既にマウント中です。umount してから break します。"; return 1; }
        timeout 30 mount -t nfs4 -o rw,hard,vers=4 "$FS_PEER:$FS_SHARE" "$FS_MNT" || { echo 'マウントできません。appのsetupと到達性を確認します。'; return 1; }
        touch "$LAB_STATE/fault"
        echo "hard（timeo指定なし）でマウントしました。findmnt で現在のオプションを確認します。"
    fi
}

# --- app judging: live `exportfs -v` ---
_fs_check_app() {
    local approved out
    approved=$(cat "$LAB_STATE/approved-client")
    ss -ltn 2>/dev/null | grep -q ':2049 ' || { echo 'nfsd が 2049/tcp で待ち受けていません。'; return 1; }
    out=$(exportfs -v 2>&1) || { echo 'exportfs -v に失敗しました。'; return 1; }
    printf '%s\n' "$out" | python3 -c '
import re, sys
approved, share = sys.argv[1:3]
text = re.sub(r"\s+", " ", sys.stdin.read()).strip()
entries = re.findall(r"(/\S+) ([^ (]+)\(([^)]*)\)", text)
mine = [e for e in entries if e[0] == share]
if not mine:
    print("%s が exportfs -v に出ていません（exportfs -ra を実行しましたか）。" % share); sys.exit(1)
if len(mine) != 1:
    print("公開先が複数あります。client のIPだけにします。"); sys.exit(1)
_, client, opts = mine[0]
o = set(opts.split(","))
if client not in (approved, approved + "/32"):
    print("公開先が %s です。client のIP(%s)だけにします。" % (client, approved)); sys.exit(1)
if "no_root_squash" in o or "root_squash" not in o:
    print("root_squash が有効ではありません。"); sys.exit(1)
if "all_squash" in o or "rw" not in o:
    print("rw かつ all_squash でない設定にします。"); sys.exit(1)
' "$approved" "$FS_SHARE" || return 1
    echo 'PASS: exportfs -v で、clientのIPだけに rw, root_squash で公開されていることを確認しました。'
}

# --- client judging: real mount, real writes ---
_fs_persist_ok() {   # prints reason on failure
    local line unit src type opts
    line=$(awk -v b="$FS_BEGIN" -v e="$FS_END" -v t="$FS_MNT" '$0==b{f=1;next} $0==e{f=0} f&&$1!~/^#/&&$2==t{print;exit}' /etc/fstab)
    if [[ -n $line ]]; then
        read -r src _ type opts _ <<<"$line"
        [[ $src == "$FS_PEER:$FS_SHARE" ]] || { echo "fstabの対象が $FS_PEER:$FS_SHARE ではありません。"; return 1; }
        [[ $type == nfs4 ]] || { echo 'fstabの種別が nfs4 ではありません。'; return 1; }
        [[ ,$opts, == *,_netdev,* && ,$opts, == *,nofail,* ]] || { echo 'fstabのオプションに _netdev と nofail が必要です。'; return 1; }
        return 0
    fi
    unit=/etc/systemd/system/$(systemd-escape -p --suffix=mount "$FS_MNT")
    if [[ -f $unit ]] && grep -qxF "$FS_UNIT_MARK" "$unit"; then
        [[ $(systemctl show -p What --value "$(basename "$unit")") == "$FS_PEER:$FS_SHARE" ]] || { echo '.mount の What が違います。'; return 1; }
        [[ $(systemctl show -p Type --value "$(basename "$unit")") == nfs4 ]] || { echo '.mount の Type が nfs4 ではありません。'; return 1; }
        [[ $(systemctl is-enabled "$(basename "$unit")" 2>/dev/null) == enabled ]] || { echo '.mount が enable されていません。'; return 1; }
        return 0
    fi
    echo "永続化がありません。fstab の目印ブロック内（$FS_BEGIN 〜 $FS_END）か、目印行入りの .mount ユニットを作ります。"
    return 1
}

_fs_check_client() {
    local src fst opts t name probe rootfile owner
    _fs_peer app-ip || return 1
    mountpoint -q "$FS_MNT" || { echo "$FS_MNT がマウントされていません。"; return 1; }
    read -r src fst <<<"$(findmnt -n -o SOURCE,FSTYPE -M "$FS_MNT")"
    [[ $fst == nfs4 ]] || { echo "実マウントの種別が $fst です（nfs4 が必要）。"; return 1; }
    [[ $src == "$FS_PEER:$FS_SHARE" ]] || { echo "実マウント元が $src です（$FS_PEER:$FS_SHARE が必要）。"; return 1; }
    opts=$(findmnt -n -o OPTIONS -M "$FS_MNT")
    [[ ,$opts, == *,rw,* ]] || { echo 'rw でマウントされていません。'; return 1; }
    [[ ,$opts, == *,soft,* ]] || { echo '実マウントが hard のままです（サーバ停止でプロセスが固まります）。soft にします。'; return 1; }
    t=$(sed -n 's/.*,timeo=\([0-9]*\).*/\1/p' <<<",$opts")
    [[ -n $t && $t -le 50 ]] || { echo "実マウントの timeo が ${t:-不明} です。50以下にします。"; return 1; }
    _fs_persist_ok || return 1
    # Real write as the dedicated UID.
    name=dojo-check-$$-$RANDOM
    probe=$FS_MNT/$name.user
    timeout 15 runuser -u "$FS_USER" -- sh -c "echo ok > '$probe'" || { echo "dojo-nfs (UID $FS_UID) で書き込めません。"; return 1; }
    owner=$(stat -c %u "$probe" 2>/dev/null)
    rm -f -- "$probe"
    [[ $owner == "$FS_UID" ]] || { echo "書き込んだファイルの所有UIDが ${owner:-不明} です（$FS_UID が必要）。"; return 1; }
    # root must be squashed: either write is denied, or the file lands as nobody.
    rootfile=$FS_MNT/$name.root
    if timeout 15 sh -c "echo root > '$rootfile'" 2>/dev/null; then
        owner=$(stat -c %u "$rootfile" 2>/dev/null)
        rm -f -- "$rootfile"
        [[ $owner == 65534 || $owner == 4294967294 ]] || { echo "rootの書き込みがUID ${owner:-不明} になりました。root_squash が効いていません。"; return 1; }
    fi
    echo 'PASS: nfs4の実マウント(soft・短いtimeo)、永続化(_netdev,nofail)、UID 4711での書き込み、rootの書き込みがsquashされることを確認しました。'
}

lab_check() {
    _fs_ctx || return 1
    [[ -f $LAB_STATE/owns-user ]] || { echo 'まず setup を実行します。'; return 1; }
    [[ -f $LAB_STATE/fault ]] || { echo 'まず break で故障を投入し、直します。'; return 1; }
    if [[ $LAB_VM_ROLE == app ]]; then _fs_check_app; else _fs_check_client; fi
}

lab_reset() {
    _fs_ctx || return 1
    [[ -f $LAB_STATE/owns-user ]] || { echo 'この課題が作成したものがありません。'; return 1; }
    local unit f
    if [[ $LAB_VM_ROLE == app ]]; then
        if [[ -f $LAB_STATE/owns-exports ]]; then
            rm -f -- "${FS_EXPORTS:?}"
            exportfs -ra || true
        fi
        [[ ! -f $LAB_STATE/nfs-was-inactive ]] || systemctl disable --now nfs-server 2>/dev/null || true
        [[ ! -f $LAB_STATE/owns-share ]] || rm -rf -- "${FS_SHARE:?}"
    else
        if mountpoint -q "$FS_MNT"; then umount "$FS_MNT" 2>/dev/null || umount -l "$FS_MNT" || true; fi
        if grep -qxF "$FS_BEGIN" /etc/fstab && grep -qxF "$FS_END" /etc/fstab; then
            sed -i "/^${FS_BEGIN}\$/,/^${FS_END}\$/d" /etc/fstab
        fi
        unit=/etc/systemd/system/$(systemd-escape -p --suffix=mount "$FS_MNT")
        if [[ -f $unit ]] && grep -qxF "$FS_UNIT_MARK" "$unit"; then
            systemctl disable --now "$(basename "$unit")" 2>/dev/null || true
            rm -f -- "${unit:?}"
        fi
        systemctl daemon-reload
        [[ ! -f $LAB_STATE/owns-mnt ]] || rmdir "$FS_MNT" 2>/dev/null || true
    fi
    userdel "$FS_USER" 2>/dev/null || true
    getent group "$FS_USER" >/dev/null && groupdel "$FS_USER" 2>/dev/null || true
    for f in owns-user owns-share owns-exports owns-mnt nfs-was-inactive fault approved-client TASKS.txt; do
        rm -f -- "${LAB_STATE:?}/$f"
    done
    echo '専用ユーザー・共有・exports・マウント設定を削除しました（learnerが置いたIPファイルは残します）。'
}
