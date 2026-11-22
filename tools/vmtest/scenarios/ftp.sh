# Run only through verify_scenario.py in a dedicated app VM.
set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}
lab() { dojo-vm-lab ftp "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/ftp
if test -f "$state/owns-account"; then lab reset; fi
baseline=$(systemctl is-active vsftpd.service || true)
expect 1 before-setup lab check
expect 0 setup lab setup
expect 1 before-break lab check
expect 0 break lab break
expect 1 broken lab check
conf=/etc/dojo-ftp/vsftpd.conf
sed -i 's/anonymous_enable=YES/anonymous_enable=NO/;s/userlist_deny=YES/userlist_deny=NO/' "$conf"
printf 'pasv_min_port=30000\npasv_max_port=30010\npasv_address=127.0.0.1\n' >> "$conf"
expect 1 writable-root lab check
chown root:root /srv/dojo-ftp
chmod 755 /srv/dojo-ftp
systemctl restart dojo-ftp.service
expect 0 repaired lab check
printf 'allow_writeable_chroot=YES\n' >> "$conf"
systemctl restart dojo-ftp.service
expect 1 writable-chroot-shortcut lab check
sed -i '/^allow_writeable_chroot=/d' "$conf"
printf 'dojo-ftp2\n' >> /etc/dojo-ftp/user_list
systemctl restart dojo-ftp.service
expect 1 extra-user lab check
sed -i '/^dojo-ftp2$/d' /etc/dojo-ftp/user_list
sed -i '/^pasv_address=/d' "$conf"
systemctl restart dojo-ftp.service
expect 1 missing-pasv-address lab check
printf 'pasv_address=127.0.0.1\n' >> "$conf"
systemctl restart dojo-ftp.service
expect 0 repaired-again lab check
expect 0 reset lab reset
test ! -e /etc/dojo-ftp
test ! -e /srv/dojo-ftp
test ! -e /srv/dojo-ftp2
test ! -e /etc/systemd/system/dojo-ftp.service
! getent passwd dojo-ftp
! getent passwd dojo-ftp2
! ss -Hltn | grep -q ':2121 '
test -z "$(find "$state" -mindepth 1 -print -quit)"
test "$(systemctl is-active vsftpd.service || true)" = "$baseline"
echo 'ASSERT cleanup: no dedicated files/accounts/listener/state; OS service unchanged'
expect 0 second-setup lab setup
expect 0 second-reset lab reset
