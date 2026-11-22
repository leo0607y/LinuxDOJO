# title: rootless Podman・Quadlet常駐・ボリュームのsubuid所有権障害の復旧
# roles: app
# Guest-only. Dedicated user dojo-pod; no image pull (rootfs tarball built locally); no registry access.

_pod_paths() {
    [[ ${LAB_ID:-} == podman && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/podman ]] || { echo 'podman: unexpected lab context' >&2; return 1; }
    POD_USER=dojo-pod
    POD_HOME=/home/dojo-pod
    POD_DATA=$POD_HOME/dojo-data
    POD_IMG=$POD_HOME/dojo-image
    POD_QUADLET=$POD_HOME/.config/containers/systemd/dojo-app.container
    POD_PORT=18080
    [[ ! -L $POD_HOME ]] || return 1
}

# Run a command as dojo-pod with a usable user-systemd environment.
_pod_run() {
    local uid
    uid=$(id -u "$POD_USER") || return 1
    ( cd "$POD_HOME" && runuser -u "$POD_USER" -- env HOME="$POD_HOME" XDG_RUNTIME_DIR="/run/user/$uid" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" "$@" )
}

_pod_subuid_start() { awk -F: -v u="$POD_USER" '$1==u {print $2; exit}' /etc/subuid; }
_pod_subuid_count() { awk -F: -v u="$POD_USER" '$1==u {print $3; exit}' /etc/subuid; }

lab_setup() {
    _pod_paths || return 1
    if ! command -v podman >/dev/null; then
        echo 'podmanが入っていません。次を実行してから、もう一度setupしてください:'
        echo '  sudo apt-get install -y podman'
        return 1
    fi
    local bb='' c
    for c in /usr/bin/busybox /bin/busybox; do
        if [[ -x $c ]] && ldd "$c" 2>&1 | grep -q 'not a dynamic' && "$c" --list | grep -qx httpd; then bb=$c; break; fi
    done
    [[ -n $bb ]] || { echo '静的busybox(httpd付き)がありません: sudo apt-get install -y busybox-static'; return 1; }
    local need
    for need in newuidmap runuser loginctl curl tar; do
        command -v "$need" >/dev/null || { echo "$need が必要です (uidmap等を導入)。"; return 1; }
    done
    [[ ! -e $POD_HOME ]] && ! getent passwd "$POD_USER" >/dev/null || { echo '専用ユーザーまたはホームが既にあります。既存データは上書きしません。'; return 1; }
    useradd --create-home --home-dir "$POD_HOME" --shell /bin/bash "$POD_USER" || return 1
    touch "$LAB_STATE/owns-account"
    if ! grep -q "^$POD_USER:" /etc/subuid; then usermod --add-subuids 200000-265535 "$POD_USER" || return 1; fi
    if ! grep -q "^$POD_USER:" /etc/subgid; then usermod --add-subgids 200000-265535 "$POD_USER" || return 1; fi
    loginctl enable-linger "$POD_USER" || return 1
    local uid i
    uid=$(id -u "$POD_USER")
    for i in $(seq 1 30); do [[ -S /run/user/$uid/bus || -d /run/user/$uid ]] && break; sleep 1; done
    # Pull-free image source: a tiny rootfs with a static busybox, no shell in /bin beyond busybox itself.
    local token root=$LAB_STATE/rootfs
    token=$(cat /proc/sys/kernel/random/uuid)
    printf '%s\n' "$token" > "$LAB_STATE/token"
    install -d "$root/bin" "$root/www" "$root/data" "$root/tmp"
    install -m 0755 "$bb" "$root/bin/busybox"
    printf 'dojo-pod-ok %s\n' "$token" > "$root/www/index.html"
    cat > "$root/start.sh" <<'APP'
#!/bin/busybox sh
# Writes a heartbeat into /data (the bind-mounted volume) and serves /www on :8080.
( while :; do /bin/busybox date +%s > /data/heartbeat || echo 'ERROR: cannot write /data' >&2; /bin/busybox sleep 2; done ) &
echo 'dojo app started' >&2
exec /bin/busybox httpd -f -p 8080 -h /www
APP
    chmod 0755 "$root/start.sh"
    install -d -o "$POD_USER" -g "$POD_USER" -m 0755 "$POD_IMG"
    tar --numeric-owner --owner=0 --group=0 -C "$root" -cf "$POD_IMG/rootfs.tar" . || return 1
    chown "$POD_USER:$POD_USER" "$POD_IMG/rootfs.tar"
    rm -rf -- "$root"
    install -d -o "$POD_USER" -g "$POD_USER" -m 0755 "$POD_DATA"
    install -d -o "$POD_USER" -g "$POD_USER" -m 0755 "$POD_HOME/.config/containers/systemd"
    cat > "$POD_HOME/TASKS.txt" <<TASK
専用ユーザー dojo-pod のrootless Podman課題。レジストリには接続しない(pull不要)。
入る: sudo -iu dojo-pod ; export XDG_RUNTIME_DIR=/run/user/\$(id -u)
1. 前提を確認: podman info (rootless, graphRoot) / grep dojo-pod /etc/subuid /etc/subgid
   loginctl show-user dojo-pod -p Linger / podman unshare cat /proc/self/uid_map
2. ~/dojo-image/rootfs.tar からイメージを作る(importでCMDを指定。CMDは /bin/busybox sh /start.sh)。
   名前は localhost/dojo-app:1
3. まず手で試す: podman run -d --name t -p 127.0.0.1:18080:8080 -v ~/dojo-data:/data localhost/dojo-app:1
   curl 127.0.0.1:18080 / podman ps / logs / inspect / exec t cat /data/heartbeat
   試し用コンテナは podman rm -f t で消す(system pruneは専用環境内でのみ使う)。
4. Quadlet化: ~/.config/containers/systemd/dojo-app.container を作る
   ([Container] ContainerName=dojo-app / Image / PublishPort=127.0.0.1:18080:8080 / Volume=%h/dojo-data:/data、
    [Install] WantedBy=default.target)。systemctl --user daemon-reload && systemctl --user start dojo-app.service
   生成されたunitの確認: systemctl --user cat dojo-app.service。:Zや--privilegedは使わない。
5. sudo dojo-vm-lab podman break  (別のsudoシェルから)
   journalctl/systemctl --user status/podman logs で原因を2系統見つける(起動しない原因と、書き込めない原因)。
   ボリュームはホストuidとコンテナ内uidの対応(podman unshare ls -ldn ~/dojo-data)で考える。chmod 777は不正解。
6. sudo dojo-vm-lab podman check   終了後 sudo dojo-vm-lab podman reset
TASK
    chown "$POD_USER:$POD_USER" "$POD_HOME/TASKS.txt"
    cp "$POD_HOME/TASKS.txt" "$LAB_STATE/TASKS.txt"
    echo "手順: $POD_HOME/TASKS.txt (sudo -iu dojo-pod で操作)"
}

_pod_ctr_field() { _pod_run podman inspect --format "$1" dojo-app 2>/dev/null; }

lab_break() {
    _pod_paths || return 1
    [[ -f $LAB_STATE/owns-account && -f $LAB_STATE/token ]] || { echo '先にsetupしてください。'; return 1; }
    [[ -f $POD_QUADLET && ! -L $POD_QUADLET ]] || { echo 'まず dojo-app.container を作って常駐させます。'; return 1; }
    _pod_run systemctl --user is-active --quiet dojo-app.service || { echo 'dojo-app.service を起動してから break します。'; return 1; }
    [[ $(curl -fsS --max-time 3 "http://127.0.0.1:$POD_PORT/") == "dojo-pod-ok $(cat "$LAB_STATE/token")" ]] || { echo 'まず公開ポートで応答させます。'; return 1; }
    local start
    start=$(_pod_subuid_start)
    [[ -n $start && $(_pod_subuid_count) -ge 65536 ]] || { echo 'subuid範囲が不足しています。'; return 1; }
    cat > "$POD_QUADLET" <<'Q'
[Unit]
Description=dojo app (broken)

[Container]
ContainerName=dojo-app
Image=localhost/dojo-app:9
PublishPort=127.0.0.1:18081:8080
Volume=%h/dojo-data:/data

[Install]
WantedBy=default.target
Q
    chown "$POD_USER:$POD_USER" "$POD_QUADLET"
    # A container uid 1000 owner => host uid subuid_start+999; container root cannot write.
    chown -R "$((start + 999)):$((start + 999))" "$POD_DATA"
    touch "$LAB_STATE/fault"
    _pod_run systemctl --user daemon-reload || true
    _pod_run systemctl --user restart dojo-app.service >/dev/null 2>&1 || true
    if curl -fsS --max-time 3 "http://127.0.0.1:$POD_PORT/" >/dev/null 2>&1; then
        echo '故障を確認できません。'; rm -f "$LAB_STATE/fault"; return 1
    fi
    echo '障害を入れました。unitが起動せず、直しても書き込めない状態です。原因を調べてください。'
}

lab_check() {
    _pod_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずQuadlet常駐を成功させ、breakで障害を作ります。'; return 1; }
    local uid token
    uid=$(id -u "$POD_USER") || return 1
    token=$(cat "$LAB_STATE/token")
    [[ -f $POD_QUADLET && ! -L $POD_QUADLET ]] || { echo 'Quadletファイルがありません。'; return 1; }
    grep -Eq '^WantedBy=(default|multi-user)\.target' "$POD_QUADLET" || { echo '[Install] WantedBy=default.target が必要です(再ログイン後も起動するため)。'; return 1; }
    [[ $(loginctl show-user "$POD_USER" -p Linger --value 2>/dev/null) == yes ]] || { echo 'lingerが無効です。'; return 1; }
    # Data directory: container root must map to dojo-pod; no world-writable shortcut.
    [[ $(stat -c %u "$POD_DATA") == "$uid" ]] || { echo "ボリュームの所有者が dojo-pod ではありません: $(stat -c %u "$POD_DATA")"; return 1; }
    [[ $(( 8#$(stat -c %a "$POD_DATA") & 8#002 )) == 0 ]] || { echo '全員書き込み可は解決ではありません。'; return 1; }
    [[ $(_pod_run podman unshare stat -c '%u:%g' "$POD_DATA") == 0:0 ]] || { echo 'podman unshare で見たボリュームがコンテナ内root(0:0)になっていません。'; return 1; }
    # Reload from files and restart so we judge what survives a restart, not a lucky leftover.
    _pod_run systemctl --user daemon-reload || return 1
    _pod_run systemctl --user restart dojo-app.service || { echo 'dojo-app.service を起動できません。'; return 1; }
    local i ok=
    for i in 1 2 3 4 5 6 7 8; do
        if [[ $(curl -fsS --max-time 2 "http://127.0.0.1:$POD_PORT/" 2>/dev/null) == "dojo-pod-ok $token" ]]; then ok=1; break; fi
        sleep 1
    done
    [[ -n $ok ]] || { echo "127.0.0.1:$POD_PORT が応答しません。Image名とPublishPortを確認します。"; return 1; }
    _pod_run systemctl --user is-active --quiet dojo-app.service || return 1
    [[ $(_pod_ctr_field '{{.State.Running}}') == true ]] || return 1
    [[ $(_pod_ctr_field '{{.ImageName}}') == localhost/dojo-app:1 ]] || { echo 'イメージは localhost/dojo-app:1 を使います。'; return 1; }
    [[ $(_pod_ctr_field '{{.HostConfig.Privileged}}') == false ]] || { echo '--privilegedは使いません。'; return 1; }
    [[ $(_pod_run podman ps --filter name=dojo-app --format '{{.Names}}') == dojo-app ]] || return 1
    # The app must actually write a fresh heartbeat into the volume.
    local before after
    rm -f -- "$POD_DATA/heartbeat" 2>/dev/null || true
    sleep 4
    [[ -f $POD_DATA/heartbeat ]] || { echo 'コンテナがボリュームに書き込めていません(podman logs dojo-app)。'; return 1; }
    before=$(cat "$POD_DATA/heartbeat"); sleep 3; after=$(cat "$POD_DATA/heartbeat")
    [[ $before =~ ^[0-9]+$ && $after =~ ^[0-9]+$ && $after -gt $before ]] || { echo 'heartbeatが更新されていません。'; return 1; }
    (( $(date +%s) - after < 10 )) || return 1
    [[ $(stat -c %u "$POD_DATA/heartbeat") == "$uid" ]] || return 1
    echo 'PASS: rootless Quadlet常駐・公開ポート応答・再起動後の復帰・subuid所有権の修復・実書き込みを確認しました。'
}

lab_reset() {
    _pod_paths || return 1
    [[ -f $LAB_STATE/owns-account ]] || { echo 'この課題が作成したアカウントではありません。'; return 1; }
    if getent passwd "$POD_USER" >/dev/null; then
        [[ $(getent passwd "$POD_USER" | cut -d: -f6) == "$POD_HOME" ]] || return 1
        _pod_run systemctl --user stop dojo-app.service >/dev/null 2>&1 || true
        rm -f -- "$POD_QUADLET"
        _pod_run podman rm -f -a >/dev/null 2>&1 || true
        _pod_run podman system reset --force >/dev/null 2>&1 || true
        loginctl disable-linger "$POD_USER" 2>/dev/null || true
        loginctl terminate-user "$POD_USER" 2>/dev/null || true
        sleep 1
        userdel --remove "$POD_USER" || return 1
    fi
    [[ ! -e $POD_HOME ]] || rm -rf -- "$POD_HOME"
    rm -rf -- "$LAB_STATE/rootfs"
    rm -f -- "$LAB_STATE/owns-account" "$LAB_STATE/fault" "$LAB_STATE/token" "$LAB_STATE/TASKS.txt"
    echo '専用ユーザー dojo-pod とそのコンテナ・イメージを削除しました。'
}
