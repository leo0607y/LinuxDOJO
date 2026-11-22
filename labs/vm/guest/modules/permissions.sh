# LinuxDOJO VM module: permissions
# title: ACLの実効権限と既定ACLの実習
# Source only through the VM-guarded dojo-vm-lab dispatcher.
_permissions_require() {
    [ "${LAB_VM_ROLE:-}" = app ] || { echo 'permissions is an app VM exercise' >&2; return 1; }
    [ "${LAB_STATE:-}" = "${LAB_ROOT:-}/state/permissions" ] && [ "${LAB_ROOT:-}" = /var/lib/linuxdojo-vm-lab ] || return 1
    [ ! -L "$LAB_STATE" ] || { echo 'state must not be a symlink' >&2; return 1; }
}
_permissions_users() {
    [ -f "$LAB_STATE/users.tsv" ] || return 1
    while read -r name expected_uid expected_gid; do
        case "$name" in dojo-reader|dojo-other) ;; *) return 1 ;; esac
        [ "$(id -u "$name")" = "$expected_uid" ] && [ "$(id -g "$name")" = "$expected_gid" ] || {
            echo 'lab user identity changed; refusing to modify it' >&2; return 1;
        }
    done < "$LAB_STATE/users.tsv"
    [ "$(wc -l < "$LAB_STATE/users.tsv")" -eq 2 ] || [ "${1:-}" = partial ]
}
lab_setup() {
    _permissions_require || return 1
    chmod 0755 "$LAB_ROOT" "$LAB_ROOT/state"
    install -d -m 0755 "$LAB_STATE"
    if [ -f "$LAB_STATE/users.tsv" ]; then
        _permissions_users || return 1
    else
        # Refuse collisions: do not take ownership of unrelated existing users/groups.
        for name in dojo-reader dojo-other; do
            if getent passwd "$name" >/dev/null || getent group "$name" >/dev/null; then
                echo "refusing existing unrelated account/group: $name" >&2; return 1
            fi
        done
        : > "$LAB_STATE/users.tsv"
        chmod 0600 "$LAB_STATE/users.tsv"
        for name in dojo-reader dojo-other; do
            useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$name"
            printf '%s %s %s\n' "$name" "$(id -u "$name")" "$(id -g "$name")" >> "$LAB_STATE/users.tsv"
        done
    fi
    install -d -m 0700 "$LAB_STATE/reports"
    printf 'synthetic report: preserve this content\n' > "$LAB_STATE/reports/report.txt"
    chmod 0600 "$LAB_STATE/reports/report.txt"
    setfacl -b "$LAB_STATE/reports" "$LAB_STATE/reports/report.txt"
    setfacl -k "$LAB_STATE/reports"
    setfacl -m u:dojo-reader:r-x,m::r-x "$LAB_STATE/reports"
    setfacl -m u:dojo-reader:r--,m::r-- "$LAB_STATE/reports/report.txt"
    rm -f "$LAB_STATE/broken-at"
    cat > "$LAB_STATE/TASKS.txt" <<EOF
This app VM module creates only dojo-reader/dojo-other and module-owned report files.
1. Run dojo-vm-lab permissions break to make the named user's read permission ineffective.
2. Inspect getfacl $LAB_STATE/reports/report.txt and compare named user vs mask.
3. Restore only dojo-reader's read permission via ACL/mask, preserving owner rw and denying other.
4. Add default ACL to reports: owner rwx; dojo-reader r-x; group ---; mask r-x; other ---.
5. Confirm reader can read but cannot write; dojo-other must not read. Run the module check.
Do not solve this by chmod777, making users root, or disabling permission controls.
EOF
    echo 'setup complete; read TASKS.txt then run break'
}
lab_break() {
    _permissions_require && _permissions_users || return 1
    setfacl -m m::--- "$LAB_STATE/reports/report.txt"
    setfacl -k "$LAB_STATE/reports"
    touch "$LAB_STATE/broken-at"
    echo 'ACL mask now blocks the named reader; future files also need a default ACL'
}
lab_check() (
    _permissions_require && _permissions_users || exit 1
    [ -f "$LAB_STATE/broken-at" ] || { echo 'run break and repair first' >&2; exit 1; }
    file="$LAB_STATE/reports/report.txt"
    [ ! -L "$file" ] && [ "$(cat "$file")" = 'synthetic report: preserve this content' ] || exit 1
    [ "$(stat -c %u "$file")" -eq 0 ] || { echo 'keep the root owner; grant read via ACL' >&2; exit 1; }
    runuser -u dojo-reader -- test -r "$file" || { echo 'reader cannot read existing report' >&2; exit 1; }
    if runuser -u dojo-reader -- test -w "$file"; then echo 'reader must not write' >&2; exit 1; fi
    if runuser -u dojo-other -- test -r "$file"; then echo 'other user must not read' >&2; exit 1; fi
    fresh="$LAB_STATE/reports/.inheritance-check-$$"
    [ ! -e "$fresh" ] && [ ! -L "$fresh" ] || exit 1
    trap 'rm -f -- "$fresh"' EXIT
    python3 - "$fresh" <<'PY'
import os, sys
os.umask(0)  # mode 0640: only a default ACL (not umask/other bits) can let the reader in
fd = os.open(sys.argv[1], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
with os.fdopen(fd, 'w', encoding='utf-8') as stream:
    stream.write('new synthetic report\n')
PY
    # -d strips the default: prefix; inspect the full ACL to distinguish inheritance from access.
    getfacl -cp "$LAB_STATE/reports" | grep -qx 'default:user:dojo-reader:r-x' || { echo 'default ACL on reports must give dojo-reader r-x' >&2; exit 1; }
    runuser -u dojo-reader -- test -r "$fresh" || { echo 'default ACL is missing or ineffective for new files' >&2; exit 1; }
    if runuser -u dojo-reader -- test -w "$fresh"; then echo 'default ACL grants unnecessary write' >&2; exit 1; fi
    if runuser -u dojo-other -- test -r "$fresh"; then echo 'new report is exposed to other user' >&2; exit 1; fi
    getfacl -cp "$file"
    getfacl -cp "$LAB_STATE/reports"
    echo 'PASS: existing and newly created files allow reader-only access'
)
lab_reset() {
    _permissions_require || return 1
    if [ -f "$LAB_STATE/users.tsv" ]; then
        _permissions_users partial || return 1
        while read -r name expected_uid expected_gid; do
            userdel "$name"
            # userdel may already remove the private group on some distributions.
            if getent group "$name" >/dev/null; then
                [ "$(getent group "$name" | cut -d: -f3)" = "$expected_gid" ] || return 1
                groupdel "$name"
            fi
        done < "$LAB_STATE/users.tsv"
    fi
    rm -rf -- "$LAB_STATE"
    echo 'Only module report files and recorded lab users were removed'
}
