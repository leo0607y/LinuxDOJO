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
lab() { dojo-vm-lab permissions "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/permissions
if test -f "$state/users.tsv"; then lab reset; fi
expect 0 setup lab setup
expect 1 before-break lab check
expect 0 break lab break
expect 1 broken lab check
setfacl -m m::r-- "$state/reports/report.txt"
expect 1 missing-default-acl lab check
setfacl -m d:u::rwx,d:u:dojo-reader:r-x,d:g::---,d:m::r-x,d:o::--- "$state/reports"
getfacl -cpd "$state/reports"
expect 0 repaired lab check
setfacl -k "$state/reports"
expect 1 removed-default-acl lab check
setfacl -m d:u::rwx,d:u:dojo-reader:r-x,d:g::---,d:m::r-x,d:o::--- "$state/reports"
chmod o+r "$state/reports/report.txt"
chmod o+rx "$state/reports"
expect 1 exposed-report lab check
chmod o-r "$state/reports/report.txt"
chmod o-rx "$state/reports"
expect 0 repaired-again lab check
expect 0 reset lab reset
test ! -e "$state"
! getent passwd dojo-reader
! getent passwd dojo-other
! getent group dojo-reader
! getent group dojo-other
echo 'ASSERT cleanup: report directory, users and groups absent'
expect 0 second-setup lab setup
expect 0 second-reset lab reset
