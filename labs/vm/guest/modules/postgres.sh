# title: PostgreSQL専用クラスタ: 最小権限・pg_hba・reload/restart・pg_dump/restore・pg_basebackup
# roles: app
# Dedicated cluster "16/dojo" on port 5433 (own data dir). The default "main" cluster is never touched.
# postgresql / postgresql-client are NOT part of the base image: setup refuses with an install instruction when missing.

_pg_paths() {
    [[ ${LAB_ID:-} == postgres && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/postgres ]] || { echo 'postgres: unexpected lab context' >&2; return 1; }
    PG_VER=16
    PG_NAME=dojo
    PG_PORT=5433
    PG_BIN=/usr/lib/postgresql/$PG_VER/bin
    PG_DATA=/var/lib/postgresql/$PG_VER/$PG_NAME
    PG_CONF=/etc/postgresql/$PG_VER/$PG_NAME
    PG_LAB=/var/lib/dojo-pg
    PG_DUMP=$PG_LAB/shop.dump
    PG_BASE=$PG_LAB/base
    [[ ! -L $PG_LAB && ! -L $PG_DATA && ! -L $PG_CONF ]] || return 1
}

_pg_tools() {
    local missing=() t
    for t in pg_createcluster pg_dropcluster pg_ctlcluster pg_lsclusters runuser; do
        command -v "$t" >/dev/null || missing+=("$t")
    done
    for t in psql pg_dump pg_restore pg_basebackup pg_verifybackup pg_controldata; do
        [[ -x $PG_BIN/$t ]] || missing+=("$t")
    done
    if ((${#missing[@]})); then
        echo "必要なコマンドがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get install -y postgresql postgresql-client'
        return 1
    fi
    getent passwd postgres >/dev/null || { echo 'postgresユーザーがありません。'; return 1; }
}

# Real SQL against the dedicated cluster over the unix socket as OS user postgres (peer).
_pg_psql() {
    runuser -u postgres -- "$PG_BIN/psql" -X -v ON_ERROR_STOP=1 -qAt -h /var/run/postgresql -U postgres -p "$PG_PORT" "$@"
}
_pg_sql() { _pg_psql -d "$1" -c "$2"; }

# $1=role $2=db $3=sql ; runs inside a rolled-back transaction as that role. Returns psql status.
_pg_as() {
    _pg_psql -d "$2" -f - <<SQL 2>"$LAB_STATE/last-err"
BEGIN;
SET LOCAL lc_messages = 'C';
SET LOCAL ROLE $1;
$3;
ROLLBACK;
SQL
}

_pg_allowed() { # $1=role $2=db $3=sql $4=message
    _pg_as "$1" "$2" "$3" >/dev/null || { echo "$4"; return 1; }
}

_pg_denied() { # $1=role $2=db $3=sql $4=message
    if _pg_as "$1" "$2" "$3" >/dev/null; then echo "$4"; return 1; fi
    grep -Eq 'permission denied|must be owner' "$LAB_STATE/last-err" || { echo "$4 (拒否の理由が権限エラーではありません: $(head -n 1 "$LAB_STATE/last-err"))"; return 1; }
}

_pg_fingerprint() { # $1=db -> "count:md5"
    _pg_sql "$1" "select count(*) || ':' || md5(string_agg(id || '/' || item || '/' || qty, ',' order by id)) from shop.orders"
}

# Connection attempts without any credential. An optional third argument restricts the auth method.
_pg_noauth_connect() { # $1=user $2=host $3=require_auth
    runuser -u postgres -- env -i PATH=/usr/bin:/bin PGPASSFILE=/dev/null PGCONNECT_TIMEOUT=3 \
        ${3:+PGREQUIREAUTH="$3"} LC_ALL=C \
        "$PG_BIN/psql" -X -w -qAt -h "$2" -p "$PG_PORT" -U "$1" -d shopdb -c 'select 1'
}

_pg_verify() {
    local v conn bad want got sysid backup_sysid u
    pg_lsclusters -h | awk -v n="$PG_NAME" -v ver="$PG_VER" '$1==ver && $2==n {print $3, $4}' | grep -qx "$PG_PORT online" \
        || { echo "クラスタ $PG_VER/$PG_NAME がポート$PG_PORTでonlineではありません。pg_lsclustersとpg_ctlclusterを確認します。"; return 1; }
    # active (not just file) settings: restart-only settings must really be applied
    v=$(_pg_sql postgres "select name || '=' || setting || '/' || source from pg_settings where name in ('listen_addresses','password_encryption','max_connections') order by 1") || return 1
    grep -qx 'listen_addresses=localhost/configuration file' <<<"$v" || { echo 'listen_addressesをlocalhostだけに、postgresql.confで明示し、restartで反映します。'; return 1; }
    grep -qx 'max_connections=50/configuration file' <<<"$v" || { echo 'max_connectionsを50にして、restartで反映します（reloadでは変わりません）。'; return 1; }
    grep -qx 'password_encryption=scram-sha-256/configuration file' <<<"$v" || { echo 'password_encryptionをscram-sha-256にします。'; return 1; }
    [[ $(_pg_sql postgres 'select count(*) from pg_settings where pending_restart') == 0 ]] || { echo '再起動待ちの設定があります。restartで反映します。'; return 1; }
    # pg_hba.conf: file content and live behaviour
    bad=$(_pg_sql postgres "select count(*) from pg_hba_file_rules where error is not null") || return 1
    [[ $bad == 0 ]] || { echo 'pg_hba.confに構文エラーがあります。'; return 1; }
    [[ $(_pg_sql postgres "select count(*) from pg_hba_file_rules where auth_method = 'trust'") == 0 ]] || { echo 'pg_hba.confにtrustが残っています。'; return 1; }
    [[ $(_pg_sql postgres "select count(*) from pg_hba_file_rules where type like 'host%' and not coalesce((address = '127.0.0.1' and netmask = '255.255.255.255') or (address = '::1' and netmask = 'ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'), false)") == 0 ]] || { echo 'ループバック以外を許可するhost行があります。'; return 1; }
    [[ $(_pg_sql postgres "select count(*) from pg_hba_file_rules where type like 'host%' and auth_method <> 'scram-sha-256'") == 0 ]] || { echo 'host行の認証方式をscram-sha-256にします。'; return 1; }
    [[ $(_pg_sql postgres "select count(*) from pg_hba_file_rules where type like 'host%' and address = '127.0.0.1' and auth_method = 'scram-sha-256'") -ge 1 ]] || { echo '127.0.0.1のhost行をscram-sha-256にします。'; return 1; }
    for u in shop_app shop_ro postgres; do
        if _pg_noauth_connect "$u" 127.0.0.1 >/dev/null 2>&1; then echo "パスワード無しでTCP接続できます($u)。pg_hba.confを直し、reloadします。"; return 1; fi
    done
    for u in shop_app shop_ro; do
        if _pg_noauth_connect "$u" /var/run/postgresql >/dev/null 2>&1; then echo "$uがパスワード無しでソケット接続できます。"; return 1; fi
    done
    # roles
    v=$(_pg_sql postgres "select rolname from pg_authid where rolname in ('shop_app','shop_ro')
        and rolcanlogin and not (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls)
        and rolpassword like 'SCRAM-SHA-256$%'") || return 1
    for u in shop_app shop_ro; do
        grep -qx "$u" <<<"$v" || { echo "$uはログイン可・最小権限・パスワードはSCRAM保存にします。"; return 1; }
        if conn=$(_pg_noauth_connect "$u" 127.0.0.1 scram-sha-256 2>&1) || ! grep -q 'fe_sendauth: no password supplied' <<<"$conn"; then
            echo "$u のループバック接続に有効なSCRAM認証設定がありません。pg_hba.confを確認し、reloadします。"
            return 1
        fi
    done
    # least privilege, tested by acting as the roles
    _pg_allowed shop_app shopdb "select count(*) from shop.orders; insert into shop.orders(item, qty) values ('probe', 1); update shop.orders set qty = qty where id = 1" 'shop_appはshop.ordersを読み書きできる必要があります(シーケンス権限も)。' || return 1
    _pg_denied shop_app shopdb 'select * from private.secrets' 'shop_appがprivateスキーマを読めます。' || return 1
    _pg_denied shop_app shopdb 'drop table shop.orders' 'shop_appがテーブルを削除できます。' || return 1
    _pg_denied shop_app shopdb 'truncate shop.orders' 'shop_appがTRUNCATEできます。' || return 1
    _pg_denied shop_app shopdb 'delete from shop.orders' 'shop_appがDELETEできます。' || return 1
    _pg_denied shop_app shopdb 'create table shop.evil(x int)' 'shop_appがshopスキーマにテーブルを作れます。' || return 1
    _pg_denied shop_app shopdb 'create table public.evil(x int)' 'shop_appがpublicスキーマに作れます。' || return 1
    _pg_allowed shop_ro shopdb 'select count(*) from shop.orders' 'shop_roがshop.ordersを読めません。' || return 1
    _pg_denied shop_ro shopdb "insert into shop.orders(item, qty) values ('x', 1)" 'shop_roがINSERTできます。' || return 1
    _pg_denied shop_ro shopdb 'update shop.orders set qty = 0' 'shop_roがUPDATEできます。' || return 1
    _pg_denied shop_ro shopdb 'delete from shop.orders' 'shop_roがDELETEできます。' || return 1
    _pg_denied shop_ro shopdb 'select * from private.secrets' 'shop_roがprivateスキーマを読めます。' || return 1
    # Check the effective default grants on a table created by the fixture owner.
    v=$(_pg_psql -d shopdb -f - 2>"$LAB_STATE/last-err" <<'SQL'
BEGIN;
CREATE TABLE shop.dp_probe(x int);
SELECT has_table_privilege('shop_ro', 'shop.dp_probe', 'SELECT')
   AND NOT has_table_privilege('shop_ro', 'shop.dp_probe', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER');
ROLLBACK;
SQL
    ) || return 1
    [[ $v == t ]] || { echo 'ALTER DEFAULT PRIVILEGESで、今後作る表にもshop_roのSELECT権限だけを付与します。'; return 1; }
    # logical backup + restore into a NEW database
    [[ -f $PG_DUMP ]] || { echo "$PG_DUMP にpg_dump -Fcのダンプがありません。"; return 1; }
    v=$(runuser -u postgres -- "$PG_BIN/pg_restore" --list "$PG_DUMP" 2>/dev/null) || { echo 'ダンプがpg_dump -Fcのカスタム形式ではありません。'; return 1; }
    grep -q 'TABLE DATA shop orders' <<<"$v" || { echo 'ダンプがshop.ordersのデータを含みません。'; return 1; }
    runuser -u postgres -- "$PG_BIN/pg_restore" --file=/dev/null "$PG_DUMP" 2>/dev/null || { echo 'ダンプを最後まで読み取れません。pg_dumpをやり直します。'; return 1; }
    want=$(cat "$LAB_STATE/fixture.txt")
    got=$(_pg_fingerprint shopdb) || return 1
    [[ $got == "$want" ]] || { echo "元のshopdbのデータが変わっています($got)。"; return 1; }
    [[ $(_pg_sql postgres "select count(*) from pg_database where datname = 'shop_restore'") == 1 ]] || { echo 'リストア先データベースshop_restoreがありません。'; return 1; }
    got=$(_pg_fingerprint shop_restore 2>/dev/null) || { echo 'shop_restoreにshop.ordersがありません。pg_restore -dの指定先を確認します。'; return 1; }
    [[ $got == "$want" ]] || { echo "shop_restoreの件数/チェックサムが一致しません: $got (期待 $want)"; return 1; }
    [[ $(_pg_sql postgres "select count(*) from information_schema.schemata where schema_name in ('shop','private')") == 0 ]] || { echo '管理用のpostgresデータベースにshop/privateスキーマが紛れ込んでいます。間違った先へのリストアを片付けます。'; return 1; }
    # physical base backup
    [[ -f $PG_BASE/backup_manifest && -f $PG_BASE/PG_VERSION ]] || { echo "$PG_BASE にpg_basebackup(-Fp)のバックアップがありません。"; return 1; }
    sysid=$(_pg_sql postgres 'select system_identifier from pg_control_system()') || return 1
    runuser -u postgres -- "$PG_BIN/pg_verifybackup" "$PG_BASE" >"$LAB_STATE/verifybackup.txt" 2>&1 || { echo 'pg_verifybackupが失敗します:'; cat "$LAB_STATE/verifybackup.txt"; return 1; }
    # PostgreSQL 16's version-1 manifest contains no cluster system identifier.
    backup_sysid=$(runuser -u postgres -- env LC_ALL=C "$PG_BIN/pg_controldata" "$PG_BASE" | awk -F ': *' '$1 == "Database system identifier" {print $2}') || return 1
    [[ -n $sysid && $backup_sysid == "$sysid" ]] || { echo 'バックアップがこのクラスタのものではありません。'; return 1; }
}

lab_setup() {
    _pg_paths || return 1
    _pg_tools || return 1
    [[ ! -e $PG_LAB && ! -e $PG_DATA && ! -e $PG_CONF && ! -e $LAB_STATE/owns-cluster ]] || { echo '専用クラスタが既にあります。resetせず既存データを上書きしません。'; return 1; }
    pg_lsclusters -h | awk -v n="$PG_NAME" -v ver="$PG_VER" '$1==ver && $2==n' | grep -q . && { echo "クラスタ $PG_VER/$PG_NAME が既にあります。"; return 1; }
    if (ss -Hltn 2>/dev/null || true) | grep -q ":$PG_PORT "; then echo "ポート$PG_PORTは使用中です。"; return 1; fi
    echo "$PG_VER $PG_NAME $PG_PORT" > "$LAB_STATE/owns-cluster"
    # A learner shell may export an uninstalled locale (e.g. LC_ALL=ja_JP.UTF-8 forwarded over ssh), which makes
    # pg_createcluster abort; the cluster is created with the always-present C.UTF-8 instead.
    if ! LC_ALL=C.UTF-8 LANG=C.UTF-8 pg_createcluster "$PG_VER" "$PG_NAME" --port "$PG_PORT"; then
        [[ -d $PG_DATA && -f $PG_DATA/dojo-lab-marker ]] || rm -f -- "$LAB_STATE/owns-cluster"
        return 1
    fi
    echo 'LinuxDOJO lab cluster' > "$PG_DATA/dojo-lab-marker"
    chown postgres:postgres "$PG_DATA/dojo-lab-marker"
    # deliberately weak starting configuration for the learner to fix
    cat >> "$PG_CONF/postgresql.conf" <<'CONF'

# --- LinuxDOJO initial values (learner changes these) ---
max_connections = 200
password_encryption = md5
CONF
    sed -i -E 's/^(host\s+.*)scram-sha-256\s*$/\1md5/' "$PG_CONF/pg_hba.conf"
    pg_ctlcluster "$PG_VER" "$PG_NAME" start || return 1
    install -d -o postgres -g postgres -m 0750 "$PG_LAB"
    _pg_sql postgres 'create database shopdb' || return 1
    _pg_sql shopdb "
create schema shop; create schema private;
create table shop.orders(id serial primary key, item text not null, qty int not null);
insert into shop.orders(item, qty) select 'item-' || md5(i::text), i % 17 + 1 from generate_series(1, 1000) i;
create table private.secrets(token text);
insert into private.secrets values ('do-not-read');" || return 1
    _pg_fingerprint shopdb > "$LAB_STATE/fixture.txt" || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用PostgreSQLクラスタ $PG_VER/$PG_NAME (ポート$PG_PORT, 設定 $PG_CONF, データ $PG_DATA)。標準のmainクラスタは触らない。
操作: sudo -u postgres psql -p $PG_PORT shopdb （unixソケット、peer認証）。shopdbにはshop.orders(1000行)とprivate.secretsがある。
1. ロールshop_app(アプリ用)とshop_ro(読み取り専用)をLOGIN付きで作る。パスワードはSCRAM保存で。
   現在password_encryptionがmd5になっている。設定を直してからパスワードを設定し直すこと。
2. 最小権限: shop_appはshop.ordersの読み書きだけ(SELECT/INSERT/UPDATE+シーケンス)。DROP/TRUNCATE/CREATE/privateは不可。
   shop_roはshopスキーマのSELECTのみ。ALTER DEFAULT PRIVILEGESで、今後作る表にも反映する。superuserは使わない。
3. $PG_CONF/postgresql.conf: listen_addresses='localhost'を明示、max_connections=50 (末尾の初期値行を直す)。
   $PG_CONF/pg_hba.conf: host行はループバックのscram-sha-256のみ。replicationのlocal行は残す。
   reloadで足りる変更とrestartが必要な変更を区別: pg_ctlcluster $PG_VER $PG_NAME reload / restart。
   SHOW max_connections; と pg_settings.pending_restart で反映を確かめる。
4. 論理バックアップ: sudo -u postgres pg_dump -Fc -p $PG_PORT -f $PG_DUMP shopdb
   新DB shop_restore を作り pg_restore -d shop_restore。件数とチェックサム(md5(string_agg(...)))を元と照合。
5. 物理バックアップ: sudo -u postgres pg_basebackup -p $PG_PORT -D $PG_BASE -Fp ; 続けてpg_verifybackup $PG_BASE
6. sudo dojo-vm-lab postgres break （全部できてから）。故障: trust設定・superuserのアプリ用ロール・誤ったDBへのリストア。
   調査して直す。trustのまま、またはsuperuserのまま通すのは不正解。
7. sudo dojo-vm-lab postgres check ; 終了後 reset （専用クラスタとバックアップのみ削除）
TASK
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _pg_paths || return 1
    [[ -f $LAB_STATE/owns-cluster && -f $LAB_STATE/fixture.txt ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -e $LAB_STATE/fault ]] || { echo '既に故障状態です。直してcheckします。'; return 1; }
    _pg_verify || { echo 'break前に、手順1〜5を正しく完了させます。'; return 1; }
    cp -p "$PG_CONF/pg_hba.conf" "$LAB_STATE/pg_hba.before-break"
    { printf 'host all all 127.0.0.1/32 trust\nhost all all ::1/128 trust\n'; cat "$LAB_STATE/pg_hba.before-break"; } > "$PG_CONF/pg_hba.conf"
    _pg_sql postgres 'alter role shop_app superuser' || return 1
    pg_ctlcluster "$PG_VER" "$PG_NAME" reload || return 1
    _pg_sql postgres 'drop database shop_restore' || return 1
    runuser -u postgres -- "$PG_BIN/pg_restore" -h /var/run/postgresql -U postgres -p "$PG_PORT" -d postgres \
        --no-owner --single-transaction "$PG_DUMP" || return 1
    touch "$LAB_STATE/fault"
    echo '故障を入れました: pg_hbaがtrust、shop_appがsuperuser、ダンプが管理DB(postgres)に復元され、shop_restoreが無い。見つけて直します(元のpg_hbaに丸ごと戻すだけでなく原因を理解すること)。'
}

lab_check() {
    _pg_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで故障を作ります。'; return 1; }
    _pg_verify || return 1
    echo 'PASS: SCRAM/loopback/最小権限・実SQLでの読み書き拒否・pg_dump/pg_restoreの件数とチェックサム・pg_verifybackupを確認しました。'
}

lab_reset() {
    _pg_paths || return 1
    [[ -f $LAB_STATE/owns-cluster && $(cat "$LAB_STATE/owns-cluster") == "$PG_VER $PG_NAME $PG_PORT" ]] || { echo 'この課題が作成したクラスタではありません。'; return 1; }
    if [[ -d $PG_DATA ]]; then
        [[ -f $PG_DATA/dojo-lab-marker && ! -L $PG_DATA/dojo-lab-marker ]] || { echo 'データディレクトリにlabマーカーがありません。削除しません。'; return 1; }
        pg_dropcluster "$PG_VER" "$PG_NAME" --stop || return 1
    fi
    [[ ! -L $PG_LAB ]] && rm -rf -- "${PG_LAB:?}"
    rm -f -- "$LAB_STATE/owns-cluster" "$LAB_STATE/fault" "$LAB_STATE/fixture.txt" "$LAB_STATE/last-err" "$LAB_STATE/verifybackup.txt" "$LAB_STATE/pg_hba.before-break" "$LAB_STATE/TASKS.txt"
    echo '専用クラスタとバックアップを削除しました。mainクラスタとパッケージは変更していません。'
}
