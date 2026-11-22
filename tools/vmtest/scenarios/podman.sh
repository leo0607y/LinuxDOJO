# Run only through verify_scenario.py in a dedicated app VM with podman, uidmap and busybox-static.
set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
source /etc/os-release
virt=$(systemd-detect-virt --vm)
printf 'OS=%s KERNEL=%s VM_TYPE=%s\n' "$PRETTY_NAME" "$(uname -r)" "$virt"
podman --version
expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}
lab() { dojo-vm-lab podman "$@"; }
user=dojo-pod
pod_home=/home/dojo-pod
state=/var/lib/linuxdojo-vm-lab/state/podman
quadlet=$pod_home/.config/containers/systemd/dojo-app.container
data=$pod_home/dojo-data
url=http://127.0.0.1:18080/
unit=dojo-app.service
image=localhost/dojo-app:1
pod() (
    cd "$pod_home" || return 1
    runuser -u "$user" -- env HOME="$pod_home" XDG_RUNTIME_DIR="/run/user/$uid" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" "$@"
)
await_http() {
    local attempt
    for attempt in {1..15}; do
        if [[ $(curl -fsS --max-time 2 "$url" 2>/dev/null) == "$body" ]]; then return 0; fi
        sleep 1
    done
    return 1
}
assert_cleanup() {
    if getent passwd "$user" || getent group "$user" || grep -q "^$user:" /etc/subuid /etc/subgid; then
        echo 'Account, group or subordinate ID mapping remains.'
        return 1
    fi
    test ! -e "$pod_home"
    test ! -e "/var/lib/systemd/linger/$user"
    test ! -e "/run/user/$uid"
    if pgrep -u "$uid"; then return 1; fi
    local listeners residue
    listeners=$(ss -Hltn '( sport = :18080 or sport = :18081 )')
    residue=$(find "$state" -mindepth 1 -print -quit)
    test -z "$listeners"
    test -z "$residue"
    echo 'ASSERT cleanup: no account, mappings, processes, home, linger, runtime, listeners or state'
}

if test -f "$state/owns-account"; then lab reset; fi
expect 1 before-setup lab check
expect 0 setup lab setup
uid=$(id -u "$user")
body="dojo-pod-ok $(cat "$state/token")"
expect 1 before-break lab check
expect 1 before-quadlet lab break
test "$(pod podman info --format '{{.Host.Security.Rootless}}')" = true
test "$(pod podman unshare stat -c '%u:%g' "$data")" = 0:0
pod podman import -q --change 'CMD ["/bin/busybox","sh","/start.sh"]' "$pod_home/dojo-image/rootfs.tar" "$image" >/dev/null
pod podman run -d --pull=never --name t -p 127.0.0.1:18080:8080 -v "$data:/data" "$image" >/dev/null
await_http
heartbeat=$(pod podman exec t /bin/busybox cat /data/heartbeat)
[[ $heartbeat =~ ^[0-9]+$ ]]
pod podman rm -f t >/dev/null
echo 'ASSERT manual rootless run: local import, loopback HTTP and container volume write'

pod tee "$quadlet" >/dev/null <<'Q'
[Container]
ContainerName=dojo-app
Image=localhost/dojo-app:1
Pull=never
PublishPort=127.0.0.1:18080:8080
Volume=%h/dojo-data:/data

[Install]
WantedBy=default.target
Q
pod systemctl --user daemon-reload
pod systemctl --user start "$unit"
await_http
expect 0 break lab break
expect 0 failed-unit pod systemctl --user is-failed --quiet "$unit"
test "$(pod podman unshare stat -c '%u:%g' "$data")" = 1000:1000
expect 1 broken lab check
pod sed -i 's@Image=localhost/dojo-app:9@Image=localhost/dojo-app:1@' "$quadlet"
expect 1 image-only-repair lab check
pod podman unshare chown -R 0:0 "$data"
expect 1 wrong-port lab check
pod sed -i 's/127\.0\.0\.1:18081/127.0.0.1:18080/' "$quadlet"
pod chmod 0777 "$data"
expect 1 world-writable lab check
pod chmod 0755 "$data"
pod sed -i 's/WantedBy=default.target/#WantedBy=default.target/' "$quadlet"
expect 1 missing-autostart lab check
pod sed -i 's/#WantedBy=/WantedBy=/' "$quadlet"
pod mkdir -p "$pod_home/.config/systemd/user"
pod tee "$pod_home/.config/systemd/user/$unit" >/dev/null <<'UNIT'
[Service]
ExecStart=/usr/bin/true
UNIT
expect 1 plain-service lab check
pod rm -- "$pod_home/.config/systemd/user/$unit"
pod sed -i '/^\[Container\]/a PodmanArgs=--privileged' "$quadlet"
expect 1 privileged lab check
pod sed -i '/^PodmanArgs=/d; s/127\.0\.0\.1:18080/0.0.0.0:18080/' "$quadlet"
expect 1 all-interfaces lab check
pod sed -i 's/0\.0\.0\.0:18080/127.0.0.1:18080/' "$quadlet"
# Isolate the next cases from the user unit's start rate limit after rapid restarts.
pod systemctl --user reset-failed "$unit"
pod sed -i 's@:/data$@:/data:ro@' "$quadlet"
expect 1 read-only-volume lab check
pod sed -i 's@:/data:ro$@:/data@' "$quadlet"
pod sed -i '/^\[Container\]/a Exec=/bin/busybox sh /no-heartbeat.sh' "$quadlet"
pod tee "$pod_home/no-heartbeat.sh" >/dev/null <<'APP'
trap 'exit 0' TERM INT
/bin/busybox httpd -f -p 8080 -h /www &
wait "$!"
APP
pod sed -i '/^\[Container\]/a Volume=%h/no-heartbeat.sh:/no-heartbeat.sh:ro' "$quadlet"
expect 1 http-without-heartbeat lab check
pod sed -i '/^Exec=/d; /no-heartbeat\.sh/d' "$quadlet"
expect 0 repaired lab check
systemctl restart "user@$uid.service"
await_http
pod systemctl --user is-active --quiet "$unit"
echo 'ASSERT user manager restart: linger starts Quadlet automatically, HTTP returns expected body'
expect 0 reset lab reset
assert_cleanup
expect 0 second-setup lab setup
uid=$(id -u "$user")
expect 0 second-reset lab reset
assert_cleanup
