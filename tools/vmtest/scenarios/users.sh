set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}
lab() { dojo-vm-lab users "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/users
if test -f "$state/owns-group"; then lab reset; fi
expect 1 before-setup lab check
expect 0 setup lab setup
expect 1 incomplete lab check
useradd -m -s /bin/bash -G dojo-ops dojo-alice
write_policy() {
    printf 'dojo-alice ALL=(root) NOPASSWD: /usr/bin/systemctl is-active ssh\n' > "$state/policy"
    visudo -cf "$state/policy"
    install -o root -g root -m 0440 "$state/policy" /etc/sudoers.d/dojo-users
    rm "$state/policy"
}
write_policy
expect 1 before-break lab check
expect 0 break lab break
expect 1 broken lab check
usermod -s /bin/bash -aG dojo-ops dojo-alice
expect 1 sudo-all-shortcut lab check
write_policy
expect 0 repaired lab check
usermod -aG sudo dojo-alice
expect 1 admin-group lab check
gpasswd -d dojo-alice sudo
chmod 644 /etc/sudoers.d/dojo-users
expect 1 bad-mode lab check
chmod 440 /etc/sudoers.d/dojo-users
chage -E 1 dojo-alice
expect 1 expired-account lab check
chage -E -1 dojo-alice
expect 0 repaired-again lab check
expect 0 reset lab reset
! getent passwd dojo-alice
! getent group dojo-ops
test ! -e /home/dojo-alice
test ! -e /etc/sudoers.d/dojo-users
test -z "$(find "$state" -mindepth 1 -print -quit)"
visudo -c
echo 'ASSERT cleanup: account/group/home/sudoers/state removed, global sudoers valid'
