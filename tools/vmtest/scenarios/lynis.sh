set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}
lab() { dojo-vm-lab lynis "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/lynis
if test -f "$state/owns-lab"; then lab reset; fi
original=$(sha256sum /etc/issue.net)
expect 0 setup lab setup
expect 1 before-break lab check
expect 0 baseline lab break
expect 1 incomplete lab check
cat > /etc/apt/apt.conf.d/52dojo-auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
printf 'Legal warning: authorized users only.\nUnauthorized access is prohibited; activity is monitored and logged.\n' > /etc/issue.net
printf 'umask 027\n' > /etc/profile.d/dojo-umask.sh
expect 0 repaired lab check
printf 'umask 022\n' > /etc/profile.d/dojo-umask.sh
expect 1 wrong-umask lab check
printf 'umask 027\n' > /etc/profile.d/dojo-umask.sh
printf 'Ubuntu 24.04\nAuthorized users only\n' > /etc/issue.net
expect 1 leaking-os-banner lab check
printf 'Legal warning: authorized users only.\nUnauthorized access is prohibited; activity is monitored and logged.\n' > /etc/issue.net
cp /etc/apt/apt.conf.d/52dojo-auto-upgrades "$state/good-apt"
printf '// APT::Periodic::Update-Package-Lists "1";\n' > /etc/apt/apt.conf.d/52dojo-auto-upgrades
expect 1 commented-apt lab check
mv "$state/good-apt" /etc/apt/apt.conf.d/52dojo-auto-upgrades
expect 0 repaired-again lab check
cat "$state/baseline.json" "$state/after.json"
expect 0 reset lab reset
test "$(sha256sum /etc/issue.net)" = "$original"
test ! -e /etc/apt/apt.conf.d/52dojo-auto-upgrades
test ! -e /etc/profile.d/dojo-umask.sh
test -z "$(find "$state" -mindepth 1 -print -quit)"
echo 'ASSERT cleanup: original banner restored; drop-ins and state removed; packages retained as documented'
