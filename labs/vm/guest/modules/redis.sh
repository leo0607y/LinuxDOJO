# title: Redis専用インスタンス: 認証・ACL・maxmemory・永続化(AOF)・運用調査
# roles: app
# Dedicated redis-server on 127.0.0.1:6380 with its own config (/etc/dojo-redis) and unit (dojo-redis.service).
# The OS redis-server.service is never touched. redis-server/redis-tools are NOT in the base image: setup refuses with an install instruction.

_rd_paths() {
    [[ ${LAB_ID:-} == redis && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/redis ]] || { echo 'redis: unexpected lab context' >&2; return 1; }
    RD_CONF_DIR=/etc/dojo-redis
    RD_CONF=$RD_CONF_DIR/redis.conf
    RD_DATA=/var/lib/dojo-redis
    RD_UNIT=/etc/systemd/system/dojo-redis.service
    RD_PORT=6380
    RD_MARK='# LinuxDOJO lab instance (do not remove this line)'
    [[ ! -L $RD_CONF_DIR && ! -L $RD_CONF && ! -L $RD_DATA && ! -L $RD_UNIT ]] || return 1
}

_rd_tools() {
    local missing=() t
    for t in redis-server redis-cli systemctl ss timeout; do
        command -v "$t" >/dev/null || missing+=("$t")
    done
    if ((${#missing[@]})); then
        echo "必要なコマンドがありません: ${missing[*]}"
        echo '次を実行してから、もう一度setupしてください: sudo apt-get install -y redis-server redis-tools'
        return 1
    fi
    getent passwd redis >/dev/null || { echo 'redisユーザーがありません。'; return 1; }
}

_rd_cli() { timeout 10 redis-cli -h 127.0.0.1 -p "$RD_PORT" --no-auth-warning "$@" 2>&1; }
_rd_admin() { REDISCLI_AUTH=$(<"$LAB_STATE/admin.pw") _rd_cli "$@"; }
_rd_viewer() { REDISCLI_AUTH=$(<"$LAB_STATE/viewer.pw") _rd_cli --user viewer "$@"; }
_rd_cfg() { _rd_admin CONFIG GET "$1" | sed -n 2p; }

_rd_wait() {
    local i
    for i in $(seq 1 20); do
        _rd_cli PING | grep -Eq 'PONG|NOAUTH' && return 0
        sleep 0.5
    done
    echo 'dojo-redisが応答しません。sudo journalctl -u dojo-redis -n 30 を確認します。'
    return 1
}

# Behaviour of the running server (called before and after a real restart).
_rd_live() { # $1 = label for messages
    local out listeners l mem pol
    _rd_cli PING | grep -q NOAUTH || { echo "$1: 認証無しのコマンドがNOAUTHになりません。requirepassを設定します。"; return 1; }
    out=$(REDISCLI_AUTH=wrong-password _rd_cli PING) || true
    ! grep -q PONG <<<"$out" || { echo "$1: 間違ったパスワードで通ります。"; return 1; }
    [[ $(_rd_admin PING) == PONG ]] || { echo "$1: $LAB_STATE/admin.pw のパスワードでdefaultユーザーが認証できません。"; return 1; }
    [[ $(_rd_viewer ACL WHOAMI) == viewer ]] || { echo "$1: ACLユーザーviewer($LAB_STATE/viewer.pw)で認証できません。"; return 1; }
    out=$(_rd_viewer SET dojo:viewer-write x) || true
    grep -q NOPERM <<<"$out" || { echo "$1: viewerがSETできます(または拒否がNOPERMではありません: $out)。"; return 1; }
    out=$(_rd_viewer CONFIG SET maxmemory 0) || true
    grep -q NOPERM <<<"$out" || { echo "$1: viewerがCONFIG SETできます。"; return 1; }
    listeners=$(ss -Hltn "sport = :$RD_PORT" | awk '{print $4}')
    [[ -n $listeners ]] || { echo "$1: ポート$RD_PORTで待ち受けていません。"; return 1; }
    for l in $listeners; do
        [[ $l == 127.0.0.1:$RD_PORT || $l == "[::1]:$RD_PORT" ]] || { echo "$1: ループバック以外($l)で待ち受けています。bindを直します。"; return 1; }
    done
    mem=$(_rd_cfg maxmemory); pol=$(_rd_cfg maxmemory-policy)
    [[ $mem =~ ^[0-9]+$ ]] && ((mem >= 1048576 && mem <= 536870912)) || { echo "$1: maxmemoryを1MB〜512MBの範囲で設定します(現在 ${mem:-?})。"; return 1; }
    [[ $pol != noeviction && -n $pol ]] || { echo "$1: maxmemory-policyがnoevictionです。用途に合う退避方針にします。"; return 1; }
    [[ $(_rd_cfg appendonly) == yes ]] || { echo "$1: appendonlyがyesではありません。"; return 1; }
    [[ $(_rd_cfg appendfsync) == everysec ]] || { echo "$1: appendfsyncがeverysecではありません。"; return 1; }
}

_rd_verify() {
    local probe
    systemctl is-active --quiet dojo-redis.service || { echo 'dojo-redis.serviceが動いていません。'; return 1; }
    [[ $(sha256sum "$RD_UNIT" | cut -d ' ' -f 1) == $(cat "$LAB_STATE/unit.sha256") ]] || { echo 'unitファイルは変更せず、設定ファイルで直します。'; return 1; }
    _rd_wait || return 1
    _rd_live '再起動前' || { echo '(CONFIG SETで反映してから、設定ファイルにも書きます)'; return 1; }
    probe=$(cat /proc/sys/kernel/random/uuid)
    [[ $(_rd_admin SET dojo:check:probe "$probe") == OK ]] || { echo 'adminでSETできません。'; return 1; }
    systemctl restart dojo-redis.service || { echo 'dojo-redisの再起動に失敗しました。設定ファイルの構文を確認します。'; return 1; }
    _rd_wait || return 1
    _rd_live '再起動後' || { echo '(再起動で設定が戻りました。CONFIG SETだけでなくredis.confにも書いたか確認します)'; return 1; }
    [[ $(_rd_admin GET dojo:check:probe) == "$probe" ]] || { echo '再起動後にキーが消えました。AOFが有効になってから書いたデータだけが残ります。'; return 1; }
    _rd_admin DEL dojo:check:probe >/dev/null
}

lab_setup() {
    _rd_paths || return 1
    _rd_tools || return 1
    [[ ! -e $RD_CONF_DIR && ! -e $RD_DATA && ! -e $RD_UNIT && ! -e $LAB_STATE/owns-instance ]] || { echo '専用構成が既にあります。resetせず既存データを上書きしません。'; return 1; }
    if ss -Hltn | awk '{print $4}' | grep -Eq ":$RD_PORT\$"; then echo "ポート$RD_PORTは使用中です。"; return 1; fi
    touch "$LAB_STATE/owns-instance"
    install -d -o root -g redis -m 0750 "$RD_CONF_DIR"
    install -d -o redis -g redis -m 0750 "$RD_DATA"
    (umask 077; tr -d '-' < /proc/sys/kernel/random/uuid > "$LAB_STATE/admin.pw"
     cat /proc/sys/kernel/random/uuid | tr -d '-' > "$LAB_STATE/viewer.pw")
    # deliberately weak starting configuration for the learner to fix
    cat > "$RD_CONF" <<CONF
$RD_MARK
port $RD_PORT
bind 127.0.0.1
protected-mode yes
daemonize no
dir $RD_DATA
dbfilename dump.rdb
save ""
appendonly no
slowlog-log-slower-than 10000
CONF
    chown root:redis "$RD_CONF"; chmod 0640 "$RD_CONF"
    cat > "$RD_UNIT" <<UNIT
[Unit]
Description=LinuxDOJO dedicated Redis exercise (127.0.0.1:$RD_PORT)
After=network.target
[Service]
User=redis
Group=redis
ExecStart=$(command -v redis-server) $RD_CONF
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=$RD_DATA
[Install]
WantedBy=multi-user.target
UNIT
    sha256sum "$RD_UNIT" | cut -d ' ' -f 1 > "$LAB_STATE/unit.sha256"
    systemctl daemon-reload
    systemctl enable --now dojo-redis.service || return 1
    _rd_wait || return 1
    { seq 1 500 | sed 's/.*/SET dojo:key:& value-&/'
      printf 'RPUSH dojo:biglist'; seq -s ' ' 1 3000 | sed 's/^/ /'
      printf 'SET dojo:blob %s\n' "$(head -c 150000 /dev/zero | tr '\0' x)"; } | _rd_cli >/dev/null || return 1
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用Redis(127.0.0.1:$RD_PORT, 設定 $RD_CONF, データ $RD_DATA, unit dojo-redis.service)。OS標準のredisは触らない。
今は認証なし・永続化なし・メモリ上限なしの危険な状態。redis-cli -p $RD_PORT で操作する。
1. 調査: INFO server / INFO memory / INFO persistence / INFO clients ; redis-cli -p $RD_PORT --bigkeys ;
   MEMORY USAGE dojo:biglist ; SLOWLOG GET ; CONFIG GET maxmemory*
2. 認証: defaultユーザーのrequirepassに $LAB_STATE/admin.pw の値を設定。
   読み取り専用ACLユーザーviewer(パスワードは $LAB_STATE/viewer.pw)を ACL SETUSER で作る(+@read、全キー可、書き込み不可)。
   ACL LIST / ACL WHOAMI で確認。認証無しのPINGがNOAUTHになること。
3. bindは127.0.0.1のみ。protected-modeは有効のまま。
4. maxmemory(1MB〜512MB)と退避方針(noeviction以外。キャッシュ用途ならallkeys-lru/lfu等)。INFO memory / evicted_keysで確認。
5. 永続化: RDB(save)とAOFの違いを調べ、appendonly yes と appendfsync everysec にする。
6. CONFIG SETは実行時のみ。再起動で消える。redis.confに同じ内容を書く（ACLユーザーはuser行かaclfile）。
   設定の反映は sudo systemctl restart dojo-redis で確認。
7. sudo dojo-vm-lab redis break （上記を全部終えてから）。 認証・bind・永続化・maxmemoryが外れた状態になる。調査して再設定。
8. sudo dojo-vm-lab redis check （checkが実際に再起動してキーが残るか確認します）。終了後 reset。
TASK
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _rd_paths || return 1
    [[ -f $LAB_STATE/owns-instance && -f $LAB_STATE/unit.sha256 ]] || { echo 'まずsetupします。'; return 1; }
    [[ ! -e $LAB_STATE/fault ]] || { echo '既に故障状態です。直してcheckします。'; return 1; }
    _rd_verify || { echo 'break前に、手順2〜6を正しく完了させます。'; return 1; }
    cp -p "$RD_CONF" "$LAB_STATE/redis.conf.before-break"
    # Drop every learner hardening line, then re-add weak ones. "bind" widens only to a second LOOPBACK address
    # (stand-in for 0.0.0.0): nothing outside this VM can ever reach it.
    { grep -Ev '^\s*(requirepass|masterauth|user|aclfile|bind|include|maxmemory[a-z-]*|appendonly|appendfsync|appendfilename|appenddirname|save)\b' "$LAB_STATE/redis.conf.before-break"
      printf 'bind 127.0.0.1 127.0.0.2\nsave ""\nappendonly no\n'; } > "$RD_CONF"
    rm -rf -- "${RD_DATA:?}/appendonlydir" "$RD_DATA/dump.rdb"
    systemctl restart dojo-redis.service || return 1
    _rd_wait || return 1
    _rd_cli PING | grep -q PONG || { echo '故障状態を確認できません。'; return 1; }
    touch "$LAB_STATE/fault"
    echo '故障を入れました: 認証なし・bindが拡張・永続化なし・maxmemoryなし(bindは安全のためループバックの別アドレス)。INFOとCONFIG GETで調べて再設定します。'
}

lab_check() {
    _rd_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakで故障を作ります。'; return 1; }
    _rd_verify || return 1
    echo 'PASS: NOAUTH・読み取り専用ACL(NOPERM)・loopback bind・maxmemory/退避方針・AOF・実再起動後のキー保持を確認しました。'
}

lab_reset() {
    _rd_paths || return 1
    [[ -f $LAB_STATE/owns-instance ]] || { echo 'この課題が作成した構成ではありません。'; return 1; }
    if [[ -f $RD_CONF ]]; then
        [[ $(head -n 1 "$RD_CONF") == "$RD_MARK" ]] || { echo '設定ファイルのlabマーカーがありません。削除しません。'; return 1; }
    fi
    systemctl disable --now dojo-redis.service || true
    rm -f -- "$RD_UNIT"
    systemctl daemon-reload
    rm -rf -- "${RD_CONF_DIR:?}" "${RD_DATA:?}"
    rm -f -- "$LAB_STATE/owns-instance" "$LAB_STATE/fault" "$LAB_STATE/unit.sha256" "$LAB_STATE/admin.pw" "$LAB_STATE/viewer.pw" "$LAB_STATE/redis.conf.before-break" "$LAB_STATE/TASKS.txt"
    echo '専用Redisを削除しました。OS標準のredis-serverとパッケージは変更していません。'
}
