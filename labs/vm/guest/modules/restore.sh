#!/bin/bash
# title: バックアップから別VMへサービス全体（設定・データ・unit・実行ユーザー）を復元する
# roles: app client
# Same module on both VMs. app builds the original service, client restores it from a transferred backup.
# The owner UID intentionally differs between VMs so tar ownership has to be handled by the learner.

RESTORE_TOKEN=DOJO-RESTORE-7f3a9c
RESTORE_INDEX_SHA=0554085e3c81c86a33c96b01e3fa96d3eb813cfe8e263cc2fce724572f7440bc
RESTORE_ROWS_SHA=b533356a2a50260147fa4e1b7839a9a9a8509fc287673e8c48e93517cde8d4e2
RESTORE_ROWS=5
RESTORE_PORT=18090

_restore_ctx() {
    [[ ${LAB_ID:-} == restore && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/restore ]] || { echo 'restore: unexpected lab context' >&2; return 1; }
    case ${LAB_VM_ROLE:-} in
        app) RESTORE_UID=981 ;;
        client) RESTORE_UID=967 ;;
        *) echo 'restore: unexpected lab context' >&2; return 1 ;;
    esac
    RESTORE_USER=dojo-restore
    RESTORE_DIR=/srv/dojo-restore
    RESTORE_UNIT=/etc/systemd/system/dojo-restore.service
    [[ ! -L $RESTORE_DIR && ! -L $RESTORE_UNIT ]] || { echo 'restore: unexpected lab context' >&2; return 1; }
    if [[ -e $RESTORE_UNIT ]] && ! grep -qx '# LinuxDOJO VM module: restore' "$RESTORE_UNIT" && [[ ! -f $LAB_STATE/owns-unit ]]; then
        echo '別用途のunitは変更しません。' >&2; return 1
    fi
}

# Deterministic content: identical bytes/rows on both VMs.
_restore_write_index() {
    printf '<!doctype html>\n<title>dojo-restore</title>\n<p>service token: %s</p>\n' "$RESTORE_TOKEN" > "$1"
}

_restore_make_db() {   # $1 path, $2 = full|stale
    python3 - "$1" "$2" <<'PY'
import sqlite3, sys
path, kind = sys.argv[1:3]
rows = [(1, 'install', 'nginx is not used; python http.server serves site'),
        (2, 'backup', 'tar keeps owner ids; sqlite needs .backup'),
        (3, 'restore', 'stop service before replacing the database'),
        (4, 'verify', 'integrity_check then count rows'),
        (5, 'token', 'DOJO-RESTORE-7f3a9c')]
if kind == 'stale':
    rows = rows[:2]
con = sqlite3.connect(path)
con.execute('CREATE TABLE notes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)')
con.executemany('INSERT INTO notes VALUES (?,?,?)', rows)
con.commit(); con.close()
PY
}

_restore_db_verify() {   # prints reason on failure
    python3 - "$1" "$RESTORE_ROWS" "$RESTORE_ROWS_SHA" <<'PY'
import hashlib, json, sqlite3, sys
path, count, digest = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    con = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    result = con.execute('PRAGMA integrity_check').fetchall()
    if result != [('ok',)]:
        print('SQLite integrity_check が ok ではありません'); sys.exit(1)
    rows = con.execute('SELECT id,title,body FROM notes ORDER BY id').fetchall()
except sqlite3.Error as error:
    print('SQLiteを開けません: %s' % error); sys.exit(1)
if len(rows) != count:
    print('notes の行数が %d ではありません（現在 %d）' % (count, len(rows))); sys.exit(1)
if hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest() != digest:
    print('notes の内容が元データと一致しません'); sys.exit(1)
PY
}

_restore_http() {
    python3 - "$1" <<'PY'
import sys, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:%s/' % sys.argv[1], timeout=3) as response:
        sys.stdout.write(response.read().decode('utf-8', 'replace'))
except Exception:
    sys.exit(1)
PY
}

# Real-state verification shared by app (original is healthy) and client (restore succeeded).
_restore_verify() {
    local uid body unit_user pid proc_user mode
    getent passwd "$RESTORE_USER" >/dev/null || { echo "ユーザー $RESTORE_USER がありません。"; return 1; }
    uid=$(id -u "$RESTORE_USER")
    [[ $uid == "$RESTORE_UID" ]] || { echo "このVMの $RESTORE_USER のUIDは $RESTORE_UID のままにしてください。"; return 1; }
    [[ $(getent passwd "$RESTORE_USER" | cut -d: -f7) == */nologin || $(getent passwd "$RESTORE_USER" | cut -d: -f7) == /bin/false ]] || { echo '実行ユーザーは nologin のままにします。'; return 1; }
    [[ -f $RESTORE_UNIT ]] || { echo 'dojo-restore.service がありません。'; return 1; }
    [[ $(systemctl show -p NeedDaemonReload --value dojo-restore.service) == no ]] || { echo 'unitの変更が未反映です。daemon-reload が必要です。'; return 1; }
    [[ $(systemctl is-active dojo-restore.service) == active ]] || { echo 'dojo-restore.service が active ではありません。'; return 1; }
    [[ $(systemctl is-enabled dojo-restore.service 2>/dev/null) == enabled ]] || { echo 'dojo-restore.service が enable されていません。'; return 1; }
    unit_user=$(systemctl show -p User --value dojo-restore.service)
    [[ $unit_user == "$RESTORE_USER" ]] || { echo "unitの User が $RESTORE_USER ではありません。"; return 1; }
    systemctl show -p EnvironmentFiles --value dojo-restore.service | grep -q "$RESTORE_DIR/conf/app.conf" || { echo 'unitが conf/app.conf を EnvironmentFile にしていません。'; return 1; }
    systemctl show -p ExecStart --value dojo-restore.service | grep -q 'http.server' || { echo 'unitの ExecStart が想定と違います。'; return 1; }
    pid=$(systemctl show -p MainPID --value dojo-restore.service)
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
    proc_user=$(ps -o user= -p "$pid" | tr -d ' ')
    [[ $proc_user == "$RESTORE_USER" ]] || { echo '実プロセスの実行ユーザーが dojo-restore ではありません。'; return 1; }
    grep -qx "PORT=$RESTORE_PORT" "$RESTORE_DIR/conf/app.conf" || { echo "conf/app.conf は PORT=$RESTORE_PORT のはずです。"; return 1; }
    body=$(_restore_http "$RESTORE_PORT") || { echo "http://127.0.0.1:$RESTORE_PORT/ に接続できません。"; return 1; }
    [[ $body == *"$RESTORE_TOKEN"* ]] || { echo 'HTTP応答に期待トークンがありません。'; return 1; }
    [[ -f $RESTORE_DIR/site/index.html && $(sha256sum "$RESTORE_DIR/site/index.html" | cut -d ' ' -f 1) == "$RESTORE_INDEX_SHA" ]] || { echo 'site/index.html のsha256が元と違います。'; return 1; }
    [[ -f $RESTORE_DIR/data/notes.db ]] || { echo 'data/notes.db がありません。'; return 1; }
    _restore_db_verify "$RESTORE_DIR/data/notes.db" || return 1
    [[ -z $(find "$RESTORE_DIR" -xdev \( ! -user "$RESTORE_USER" -o -type l \) -print -quit) ]] || { echo "$RESTORE_DIR 配下に $RESTORE_USER 以外の所有物（またはリンク）があります。"; return 1; }
    mode=$(stat -c %a "$RESTORE_DIR/data/notes.db")
    (( (8#$mode & ~8#640) == 0 )) || { echo "notes.db のmodeが $mode です。640以下にします。"; return 1; }
    (( (8#$(stat -c %a "$RESTORE_DIR/data") & 8#007) == 0 )) || { echo 'dataディレクトリが他ユーザーに開かれています。'; return 1; }
}

lab_setup() {
    _restore_ctx || return 1
    [[ ! -e $RESTORE_DIR && ! -e $RESTORE_UNIT && ! -f $LAB_STATE/owns-user ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if getent passwd "$RESTORE_USER" >/dev/null || getent passwd "$RESTORE_UID" >/dev/null || getent group "$RESTORE_UID" >/dev/null; then
        echo '専用ユーザー名またはUIDが使用済みです。'; return 1
    fi
    command -v python3 >/dev/null || return 1
    useradd --system --uid "$RESTORE_UID" --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$RESTORE_USER" || return 1
    touch "$LAB_STATE/owns-user"
    if [[ $LAB_VM_ROLE == app ]]; then
        install -d -o "$RESTORE_USER" -g "$RESTORE_USER" -m 0750 "$RESTORE_DIR" "$RESTORE_DIR/conf" "$RESTORE_DIR/data"
        install -d -o "$RESTORE_USER" -g "$RESTORE_USER" -m 0755 "$RESTORE_DIR/site"
        _restore_write_index "$RESTORE_DIR/site/index.html"
        printf 'PORT=%s\n' "$RESTORE_PORT" > "$RESTORE_DIR/conf/app.conf"
        _restore_make_db "$RESTORE_DIR/data/notes.db" full || return 1
        chown "$RESTORE_USER:$RESTORE_USER" "$RESTORE_DIR/site/index.html" "$RESTORE_DIR/conf/app.conf" "$RESTORE_DIR/data/notes.db"
        chmod 0644 "$RESTORE_DIR/site/index.html"; chmod 0640 "$RESTORE_DIR/conf/app.conf" "$RESTORE_DIR/data/notes.db"
        _restore_write_unit "$RESTORE_USER"
        systemctl daemon-reload
        systemctl enable --now dojo-restore.service || return 1
        cat > "$LAB_STATE/TASKS.txt" <<'TASK'
【app VM = 復元元】dojo-restore サービスが動いています（127.0.0.1:18090、実行ユーザー dojo-restore）。
1. 動作確認: systemctl status dojo-restore / curl 127.0.0.1:18090 / sudo dojo-vm-lab restore check
2. 何をバックアップすべきか洗い出す: 設定、サイトの内容、データ(SQLite)、systemd unit、実行ユーザー情報。
   使用中のSQLiteをcpするのは危険。sqlite3 の .backup か、停止してコピーする方法を選ぶ。
3. /root など専用ディレクトリにバックアップを作る（tarは所有者・権限を保持する。-pと--numeric-ownerの意味を調べる）。
   復元元のUIDは981。clientの dojo-restore は別のUID。この違いが復元後に何を起こすか考える。
4. バックアップに sha256 を付けてclientへ転送する（scp/rsync。ssh実習の知識を使う）。
5. client VM で TASKS.txt を読み、復元する。復元元(app)は壊さないこと。
6. 終了後 sudo dojo-vm-lab restore reset （この課題が作ったユーザー・サービス・/srv/dojo-restore を削除。/root のバックアップは各自削除）
TASK
        echo "app: 元サービスを構築・起動しました。手順: $LAB_STATE/TASKS.txt"
    else
        cat > "$LAB_STATE/TASKS.txt" <<'TASK'
【client VM = 復元先】ここには dojo-restore ユーザー(UID 967)だけがあり、サービスはまだありません。
1. app VM でバックアップを取り、このVMへ転送する。受け取ったら sha256sum で改ざん・破損がないか照合する。
2. sudo dojo-vm-lab restore break  で「古い壊れた導入」が置かれます（誤ポート、データ欠損、root所有、User=root）。
   何が壊れているか systemctl / journalctl / ss / ls -ln / sqlite3 で調べる。
3. 復元する。サービスを止めてから置き換え、次を確認する:
   - 設定 PORT が 18090、サイト内容とデータ(行数・整合性)が元と一致
   - ファイルの所有者はこのVMの dojo-restore（tarのUID 981 のまま残さない）
   - notes.db は 640 以下で他ユーザーが読めない
   - unit は User=dojo-restore、daemon-reload 済みで enable されている
   - HTTPで index が返る
   元の壊れたデータは捨てる前に退避しておく習慣をつける。
4. sudo dojo-vm-lab restore check
5. 終了後 sudo dojo-vm-lab restore reset （専用ユーザーと /srv/dojo-restore と unit を削除）
TASK
        echo "client: 専用ユーザーを作成しました。手順: $LAB_STATE/TASKS.txt"
    fi
}

_restore_write_unit() {   # $1 user
    cat > "$RESTORE_UNIT" <<UNIT
# LinuxDOJO VM module: restore
[Unit]
Description=LinuxDOJO restore exercise web service
After=network.target
[Service]
User=$1
EnvironmentFile=$RESTORE_DIR/conf/app.conf
WorkingDirectory=$RESTORE_DIR/site
ExecStart=/usr/bin/python3 -m http.server \${PORT} --bind 127.0.0.1 --directory $RESTORE_DIR/site
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    touch "$LAB_STATE/owns-unit"
}

lab_break() {
    _restore_ctx || return 1
    [[ $LAB_VM_ROLE == client ]] || { echo 'break は client VM で実行します。'; return 1; }
    [[ -f $LAB_STATE/owns-user ]] || { echo 'まず setup を実行します。'; return 1; }
    [[ ! -e $RESTORE_DIR && ! -e $RESTORE_UNIT && ! -f $LAB_STATE/fault ]] || { echo '既に古い導入があります。上書きしません。'; return 1; }
    install -d -o root -g root -m 0755 "$RESTORE_DIR" "$RESTORE_DIR/conf" "$RESTORE_DIR/data" "$RESTORE_DIR/site"
    printf '<!doctype html>\n<title>old</title>\n<p>stale install</p>\n' > "$RESTORE_DIR/site/index.html"
    printf 'PORT=18091\n' > "$RESTORE_DIR/conf/app.conf"
    _restore_make_db "$RESTORE_DIR/data/notes.db" stale || return 1
    chmod 0644 "$RESTORE_DIR/data/notes.db"
    _restore_write_unit root
    touch "$LAB_STATE/fault"
    systemctl daemon-reload
    systemctl enable --now dojo-restore.service || return 1
    echo '古い壊れた導入を置きました。誤ポート・データ欠損・root所有・User=root を調べ、appのバックアップから復元します。'
}

lab_check() {
    _restore_ctx || return 1
    if [[ $LAB_VM_ROLE == client ]]; then
        [[ -f $LAB_STATE/fault ]] || { echo 'まず break で壊れた導入を作り、復元作業を行います。'; return 1; }
    else
        [[ -f $LAB_STATE/owns-user && -f $LAB_STATE/owns-unit ]] || { echo 'まず setup を実行します。'; return 1; }
    fi
    _restore_verify || return 1
    if [[ $LAB_VM_ROLE == client ]]; then
        echo 'PASS: 設定・データ・unit・所有者・権限・HTTP応答が元サービスと一致するよう復元できました。'
    else
        echo 'PASS: 復元元サービスは正常です。'
    fi
}

lab_reset() {
    _restore_ctx || return 1
    [[ -f $LAB_STATE/owns-user ]] || { echo 'この課題が作成したユーザーではありません。'; return 1; }
    if [[ -f $LAB_STATE/owns-unit ]]; then
        systemctl disable --now dojo-restore.service || true
        rm -f -- "$RESTORE_UNIT"
        systemctl daemon-reload
    fi
    rm -rf -- "$RESTORE_DIR"
    userdel "$RESTORE_USER" 2>/dev/null || true
    getent group "$RESTORE_USER" >/dev/null && groupdel "$RESTORE_USER" 2>/dev/null || true
    rm -f -- "$LAB_STATE/owns-user" "$LAB_STATE/owns-unit" "$LAB_STATE/fault" "$LAB_STATE/TASKS.txt"
    echo '専用ユーザー・サービス・/srv/dojo-restore を削除しました。バックアップ等の学習者ファイルは削除していません。'
}
