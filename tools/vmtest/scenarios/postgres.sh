# Run through verify_scenario.py in a dedicated Ubuntu 24.04 app VM with PostgreSQL 16.
set -euo pipefail
test "$(hostname -s)" = linuxdojo-app
grep -qx 'role=app' /etc/linuxdojo-vm-lab

expect() {
    local want=$1 label=$2 rc=0
    shift 2
    "$@" || rc=$?
    echo "ASSERT $label expected=$want actual=$rc"
    test "$rc" -eq "$want"
}

lab() { dojo-vm-lab postgres "$@"; }
state=/var/lib/linuxdojo-vm-lab/state/postgres
conf=/etc/postgresql/16/dojo
data=/var/lib/postgresql/16/dojo
backup=/var/lib/dojo-pg
dump=$backup/shop.dump
base=$backup/base
bin=/usr/lib/postgresql/16/bin
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

psql_admin() {
    runuser -u postgres -- "$bin/psql" -X -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -p 5433 "$@"
}

sql() { psql_admin -d "$1" -c "$2"; }

main_baseline() {
    pg_lsclusters -h | awk '$1 == 16 && $2 == "main"'
    if test -d /etc/postgresql/16/main; then
        sha256sum /etc/postgresql/16/main/{postgresql.conf,pg_hba.conf}
        if test -f /var/lib/postgresql/16/main/postmaster.pid; then
            head -n 1 /var/lib/postgresql/16/main/postmaster.pid
        fi
    fi
}

cluster_settings() {
    sed -i -E "s/^max_connections = 200$/max_connections = 50/;s/^password_encryption = md5$/password_encryption = 'scram-sha-256'/" "$conf/postgresql.conf"
    printf "\nlisten_addresses = 'localhost'\n" >> "$conf/postgresql.conf"
    sed -i -E 's/^(host[[:space:]]+.*)md5$/\1scram-sha-256/' "$conf/pg_hba.conf"
}

roles() {
    app_password=$(openssl rand -hex 24)
    ro_password=$(openssl rand -hex 24)
    psql_admin -d shopdb <<SQL
CREATE ROLE shop_app LOGIN PASSWORD '$app_password';
CREATE ROLE shop_ro LOGIN PASSWORD '$ro_password';
GRANT USAGE ON SCHEMA shop TO shop_app, shop_ro;
GRANT SELECT, INSERT, UPDATE ON shop.orders TO shop_app;
GRANT USAGE ON SEQUENCE shop.orders_id_seq TO shop_app;
GRANT SELECT ON ALL TABLES IN SCHEMA shop TO shop_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA shop GRANT SELECT ON TABLES TO shop_ro;
SQL
}

dump_shop() {
    runuser -u postgres -- "$bin/pg_dump" -h /var/run/postgresql -U postgres -p 5433 -Fc -f "$dump" shopdb
}

restore_shop() {
    sql postgres 'CREATE DATABASE shop_restore';
    runuser -u postgres -- "$bin/pg_restore" -h /var/run/postgresql -U postgres -p 5433 --exit-on-error -d shop_restore "$dump"
}

basebackup() {
    runuser -u postgres -- "$bin/pg_basebackup" -h /var/run/postgresql -U postgres -p 5433 -D "$base" -Fp --checkpoint=fast
}

tcp_sql() {
    PGPASSWORD="$2" PGREQUIREAUTH=scram-sha-256 PGPASSFILE=/dev/null PGCONNECT_TIMEOUT=3 \
        runuser -u postgres -- "$bin/psql" -X -w -qAt -h 127.0.0.1 -U "$1" -p 5433 -d shopdb -c 'SELECT current_user || chr(58) || count(*) FROM shop.orders'
}

assert_cleanup() {
    test ! -e "$conf"
    test ! -e "$data"
    test ! -e "$backup"
    test ! -e /var/log/postgresql/postgresql-16-dojo.log
    test ! -S /var/run/postgresql/.s.PGSQL.5433
    test -z "$(pg_lsclusters -h | awk '$1 == 16 && $2 == "dojo"')"
    test -z "$(ss -Hltn 'sport = :5433')"
    test -z "$(find "$state" -mindepth 1 -print -quit)"
    test "$(main_baseline)" = "$baseline"
    echo 'ASSERT cleanup: dedicated configuration, data, backups, log, listener and state removed; main unchanged'
}

baseline=$(main_baseline)
printf 'Guest %s, %s\n' "$(. /etc/os-release; echo "$PRETTY_NAME")" "$(systemd-detect-virt --vm)"
"$bin/psql" --version
if test -f "$state/owns-cluster"; then expect 0 reset-interrupted lab reset; fi
expect 1 before-setup lab check
expect 0 setup lab setup
expect 1 duplicate-setup lab setup
expect 1 before-break lab check
expect 1 incomplete lab break
cluster_settings
pg_ctlcluster 16 dojo reload
for attempt in {1..30}; do
    if test "$(sql postgres "SELECT pending_restart FROM pg_settings WHERE name = 'max_connections'")" = t; then break; fi
    sleep 0.1
done
test "$(sql postgres "SELECT setting || ':' || pending_restart FROM pg_settings WHERE name = 'max_connections'")" = 200:true
echo 'ASSERT reload keeps max_connections=200 and marks pending_restart'
expect 1 reload-only lab break
pg_ctlcluster 16 dojo restart
test "$(sql postgres "SELECT setting || ':' || pending_restart FROM pg_settings WHERE name = 'max_connections'")" = 50:false
echo 'ASSERT restart activates max_connections=50 and clears pending_restart'
expect 1 missing-roles lab break
roles
expect 1 missing-dump lab break
dump_shop
expect 1 missing-restore lab break
restore_shop
expect 1 missing-basebackup lab break
basebackup
runuser -u postgres -- "$bin/pg_verifybackup" "$base"
expect 0 break lab break
test "$(sql postgres "SELECT count(*) FROM shop.orders")" = 1000
test -z "$(sql postgres "SELECT datname FROM pg_database WHERE datname = 'shop_restore'")"
test "$(sql postgres "SELECT rolsuper FROM pg_roles WHERE rolname = 'shop_app'")" = t
echo 'ASSERT break restored 1000 rows into postgres, removed shop_restore and elevated shop_app'
expect 1 broken lab check
sed -i '/^host .* trust$/d' "$conf/pg_hba.conf"
expect 1 hba-edited-without-reload lab check
pg_ctlcluster 16 dojo reload
for attempt in {1..30}; do
    if ! env -i PATH=/usr/bin:/bin PGPASSFILE=/dev/null "$bin/psql" -X -w -qAt -h 127.0.0.1 -U shop_app -p 5433 -d shopdb -c 'SELECT 1' >/dev/null 2>&1; then break; fi
    sleep 0.1
done
expect 1 still-superuser lab check
sql postgres 'ALTER ROLE shop_app NOSUPERUSER'
expect 1 no-restored-database lab check
restore_shop
expect 1 still-restored-into-postgres lab check
sql postgres 'DROP SCHEMA shop CASCADE; DROP SCHEMA private CASCADE'
expect 0 repaired lab check
test "$(tcp_sql shop_app "$app_password")" = 'shop_app:1000'
test "$(tcp_sql shop_ro "$ro_password")" = 'shop_ro:1000'
echo 'ASSERT both learner roles authenticated with SCRAM over TCP and read 1000 fixture rows'

cp "$conf/pg_hba.conf" "$work/pg_hba.conf"
sed -i -E 's/^(host[[:space:]]+all[[:space:]]+)all([[:space:]]+)/\1postgres\2/' "$conf/pg_hba.conf"
pg_ctlcluster 16 dojo restart
expect 1 scram-rule-for-wrong-role lab check
cp "$work/pg_hba.conf" "$conf/pg_hba.conf"
pg_ctlcluster 16 dojo restart
sql shopdb 'GRANT DELETE ON shop.orders TO shop_app'
expect 1 overprivileged-app lab check
sql shopdb 'REVOKE DELETE ON shop.orders FROM shop_app'
sql shopdb 'ALTER DEFAULT PRIVILEGES IN SCHEMA shop GRANT INSERT ON TABLES TO shop_ro'
expect 1 overprivileged-future-tables lab check
sql shopdb 'ALTER DEFAULT PRIVILEGES IN SCHEMA shop REVOKE INSERT ON TABLES FROM shop_ro'
sql shop_restore 'UPDATE shop.orders SET qty = qty + 1 WHERE id = 1'
expect 1 mismatched-restore lab check
sql shop_restore 'UPDATE shop.orders SET qty = qty - 1 WHERE id = 1'
cp "$dump" "$work/shop.dump"
truncate -s -256 "$dump"
expect 1 truncated-dump lab check
cat "$work/shop.dump" > "$dump"
printf 'bad\n' >> "$base/PG_VERSION"
expect 1 corrupt-basebackup lab check
truncate -s -4 "$base/PG_VERSION"
expect 0 repaired-again lab check

mv "$base" "$work/base"
expect 0 reset lab reset
assert_cleanup
expect 0 second-setup lab setup
cluster_settings
pg_ctlcluster 16 dojo restart
roles
dump_shop
restore_shop
mv "$work/base" "$base"
runuser -u postgres -- "$bin/pg_verifybackup" "$base"
expect 1 valid-backup-from-previous-cluster lab break
mv "$base" "$work/base"
basebackup
expect 0 second-break lab break
expect 0 second-reset lab reset
assert_cleanup
