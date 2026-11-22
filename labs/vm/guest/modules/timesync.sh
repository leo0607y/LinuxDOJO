# title: 時刻・タイムゾーン・NTP(timesyncd)・ロケールを設定し故障から復旧する
# roles: app
# Guest-only. Never steps the clock, never disables NTP; reset restores recorded originals.

_ts_paths() {
    [[ ${LAB_ID:-} == timesync && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/timesync ]] || { echo 'timesync: unexpected lab context' >&2; return 1; }
    TS_DROPDIR=/etc/systemd/timesyncd.conf.d
    TS_DROPIN=$TS_DROPDIR/50-dojo.conf
    TS_HOME=/home/ubuntu/dojo-timesync
    TS_ANS=$TS_HOME/answers.txt
    TS_LOCALE_FILE=/etc/default/locale
    # Ubuntu 24.04: /etc/default/locale is a symlink to ../locale.conf; operate on the real file.
    if [[ -L $TS_LOCALE_FILE ]]; then
        [[ $(readlink "$TS_LOCALE_FILE") == ../locale.conf ]] || { echo 'timesync: unexpected locale symlink' >&2; return 1; }
        TS_LOCALE_FILE=/etc/locale.conf
    fi
    TS_SUPPORTED_LOCAL=/var/lib/locales/supported.d/local
    TS_LOC_GOOD=de_DE.UTF-8
    TS_LOC_BAD=es_ES.UTF-8
    [[ ! -L $TS_DROPIN && ! -L $TS_HOME && ! -L $TS_LOCALE_FILE && ! -L $TS_DROPDIR ]] || { echo 'timesync: symbolic target rejected' >&2; return 1; }
}

_ts_tz() { timedatectl show -p Timezone --value; }
_ts_has_locale() { locale -a | grep -Fxq "$(sed 's/\.UTF-8$/.utf8/' <<<"$1")"; }
_ts_lang() { sed -n 's/^LANG=//p' "$TS_LOCALE_FILE" 2>/dev/null | tail -n 1 | tr -d '"'; }
_ts_restart() { systemctl restart systemd-timesyncd.service && sleep 2; }
_ts_show() { timedatectl show-timesync -p "$1" --value 2>/dev/null; }

lab_setup() {
    _ts_paths || return 1
    [[ ! -e $LAB_STATE/owns-lab && ! -e $TS_DROPIN && ! -e $TS_HOME ]] || { echo '既に開始済みです。先にresetしてください。'; return 1; }
    command -v timedatectl >/dev/null && command -v localectl >/dev/null || { echo 'timedatectl/localectlがありません。'; return 1; }
    command -v locale-gen >/dev/null && [[ -r /usr/share/i18n/SUPPORTED ]] || { echo 'locale-gen(localesパッケージ)がありません。この実習はlocale-genが必須です。'; return 1; }
    grep -Fxq "$TS_LOC_GOOD UTF-8" /usr/share/i18n/SUPPORTED && grep -Fxq "$TS_LOC_BAD UTF-8" /usr/share/i18n/SUPPORTED || { echo '対象ロケールがSUPPORTEDにありません。'; return 1; }
    systemctl cat systemd-timesyncd.service >/dev/null 2>&1 || { echo 'systemd-timesyncdがありません(chronyだけの環境は対象外)。'; return 1; }
    systemctl is-active --quiet systemd-timesyncd.service || { echo 'systemd-timesyncdが動作していません。'; return 1; }
    [[ $(timedatectl show -p NTP --value) == yes ]] || { echo 'NTPが無効のVMです。先に有効状態へ戻してください。'; return 1; }
    ! _ts_has_locale "$TS_LOC_GOOD" && ! _ts_has_locale "$TS_LOC_BAD" || { echo '対象ロケールが既に生成済みです。'; return 1; }
    getent passwd ubuntu >/dev/null || return 1

    local orig target
    orig=$(_ts_tz)
    [[ -n $orig ]] || return 1
    if [[ $orig == Asia/Tokyo ]]; then target=America/New_York; else target=Asia/Tokyo; fi
    printf '%s\n' "$orig" > "$LAB_STATE/orig-timezone"
    printf '%s\n' "$target" > "$LAB_STATE/target-timezone"
    if [[ -e $TS_LOCALE_FILE ]]; then cp -p "$TS_LOCALE_FILE" "$LAB_STATE/orig-default-locale"; else touch "$LAB_STATE/orig-default-locale.absent"; fi
    if [[ -e $TS_SUPPORTED_LOCAL ]]; then cp -p "$TS_SUPPORTED_LOCAL" "$LAB_STATE/orig-supported-local"; else touch "$LAB_STATE/orig-supported-local.absent"; fi
    [[ -d $TS_DROPDIR ]] || touch "$LAB_STATE/created-dropdir"
    touch "$LAB_STATE/owns-lab"

    install -d -o ubuntu -g ubuntu -m 0755 "$TS_HOME"
    cat > "$TS_ANS" <<'ANS'
# 実コマンドで確かめた値を = の右に書く（例: offset=+0900）
offset=
ntp_enabled=
locale_generated=
ANS
    chown ubuntu:ubuntu "$TS_ANS"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
時刻・タイムゾーン・NTP・ロケール実習（VM内でsudoを付けて操作。元の設定は記録済みでresetで戻る）
前提: 元のタイムゾーン=$orig / 目標タイムゾーン=$target
1. date と date -u の差を確認。timedatectl set-timezone $target で変更し、timedatectl で読み戻す。
2. timedatectl show -p NTPSynchronized,NTP と timedatectl timesync-status でNTP状態を確認（NTPは無効にしない）。
3. /etc/systemd/timesyncd.conf.d/50-dojo.conf を作り [Time] に NTP=ntp.ubuntu.com と
   FallbackNTP=time.cloudflare.com time.google.com を書き、systemd-timesyncdを再起動。
   timedatectl show-timesync で実効値を確認。
4. locale -a と /usr/share/i18n/SUPPORTED を見て locale-gen $TS_LOC_GOOD でロケールを生成し、
   localectl set-locale LANG=$TS_LOC_GOOD で設定（/etc/default/locale を確認）。
5. $TS_ANS に、実コマンドで確認した値を書く:
   offset=目標TZのUTC差(date +%z形式) / ntp_enabled=yes|no / locale_generated=locale -aで出る名前
6. sudo dojo-vm-lab timesync break → 時刻・NTP・ロケールの不具合を自分で調べて直す
   （ロケール警告 "Cannot set LC_ALL" の原因、NTP実効サーバー、タイムゾーン）。
7. sudo dojo-vm-lab timesync check / 終了後 sudo dojo-vm-lab timesync reset
時計を手動で戻す・NTPを止めるなどの操作は不要で、行ってはいけません。
TASK
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _ts_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'まずsetupしてください。'; return 1; }
    [[ ! -f $LAB_STATE/fault ]] || { echo '既にbreak済みです。'; return 1; }
    local target
    target=$(cat "$LAB_STATE/target-timezone")
    # Baseline: the learner must have completed the working state first.
    [[ $(_ts_tz) == "$target" ]] || { echo 'まずタイムゾーンを目標に設定してください。'; return 1; }
    [[ $(_ts_show SystemNTPServers) == ntp.ubuntu.com && -n $(_ts_show FallbackNTPServers) ]] || { echo 'まずtimesyncdのNTP/FallbackNTPを設定し再起動してください。'; return 1; }
    [[ $(_ts_lang) == "$TS_LOC_GOOD" ]] && _ts_has_locale "$TS_LOC_GOOD" || { echo "まず $TS_LOC_GOOD を生成して設定してください。"; return 1; }
    ! _ts_has_locale "$TS_LOC_BAD" || return 1

    timedatectl set-timezone Pacific/Auckland || return 1
    install -d -m 0755 "$TS_DROPDIR"
    printf '[Time]\nNTP=ntp.dojo-bogus.invalid\nFallbackNTP=\n' > "$TS_DROPIN"
    _ts_restart || return 1
    sed -i '/^LANG=/d' "$TS_LOCALE_FILE"
    printf 'LANG=%s\n' "$TS_LOC_BAD" >> "$TS_LOCALE_FILE"
    touch "$LAB_STATE/fault"
    echo "故障を入れました。タイムゾーン・NTP実効値・ロケール(例: LANG=$TS_LOC_BAD locale)を調べて直してください。"
}

lab_check() {
    _ts_paths || return 1
    [[ -f $LAB_STATE/fault ]] || { echo 'まずbreakを実行してください。'; return 1; }
    local target tz lang eff err want
    target=$(cat "$LAB_STATE/target-timezone")
    tz=$(_ts_tz)
    [[ $tz == "$target" && $(readlink -f /etc/localtime) == /usr/share/zoneinfo/$target ]] || { echo "タイムゾーンが $target になっていません。"; return 1; }
    [[ $(timedatectl show -p NTP --value) == yes ]] || { echo 'NTPは有効のままにします。'; return 1; }
    systemctl is-active --quiet systemd-timesyncd.service || { echo 'systemd-timesyncdが停止しています。'; return 1; }
    [[ $(_ts_show SystemNTPServers) == ntp.ubuntu.com ]] || { echo 'timesyncdの実効NTPサーバーが想定と違います(show-timesyncと再起動を確認)。'; return 1; }
    eff=$(_ts_show FallbackNTPServers)
    [[ $eff == *time.cloudflare.com* && $eff != *invalid* ]] || { echo '実効FallbackNTPが想定と違います。'; return 1; }
    lang=$(_ts_lang)
    [[ $lang == "$TS_LOC_GOOD" || $lang == "$TS_LOC_BAD" ]] || { echo 'LANGは実習のロケールにしてください。'; return 1; }
    _ts_has_locale "$lang" || { echo "$lang は生成されていません(locale -a)。"; return 1; }
    err=$(env -i PATH=/usr/bin:/bin LANG="$lang" locale 2>&1 >/dev/null) || true
    [[ -z $err ]] || { echo "localeが警告を出しています: $err"; return 1; }
    localectl status | grep -Fq "LANG=$lang" || { echo 'localectlの実効値が/etc/default/localeと違います。'; return 1; }
    # Learner answers must equal real command output.
    [[ -f $TS_ANS && ! -L $TS_ANS ]] || { echo '回答ファイルがありません。'; return 1; }
    want=$(env TZ="$target" date +%z)
    [[ $(sed -n 's/^offset=//p' "$TS_ANS" | tr -d ' ') == "$want" ]] || { echo 'offsetが実際のUTC差と違います(date +%z)。'; return 1; }
    [[ $(sed -n 's/^ntp_enabled=//p' "$TS_ANS" | tr -d ' ') == yes ]] || { echo 'ntp_enabledが実際の値と違います。'; return 1; }
    want=$(sed -n 's/^locale_generated=//p' "$TS_ANS" | tr -d ' ')
    [[ -n $want ]] && locale -a | grep -Fxq "$want" && [[ $want == de_DE.utf8 || $want == es_ES.utf8 ]] || { echo 'locale_generatedがlocale -aの実在名と違います。'; return 1; }
    echo 'PASS: タイムゾーン・実効NTP・ロケール警告なし・回答の実コマンド照合を確認しました。'
}

lab_reset() {
    _ts_paths || return 1
    [[ -f $LAB_STATE/owns-lab ]] || { echo 'この課題が作成したものではありません。'; return 1; }
    local orig l f
    orig=$(cat "$LAB_STATE/orig-timezone")
    [[ -n $orig ]] && timedatectl set-timezone "$orig" || return 1
    rm -f -- "$TS_DROPIN"
    [[ ! -f $LAB_STATE/created-dropdir ]] || rmdir --ignore-fail-on-non-empty "$TS_DROPDIR" 2>/dev/null || true
    _ts_restart || true
    if [[ -f $LAB_STATE/orig-default-locale ]]; then cp -p "$LAB_STATE/orig-default-locale" "$TS_LOCALE_FILE"; else rm -f -- "$TS_LOCALE_FILE"; fi
    for l in de_DE.utf8 es_ES.utf8; do
        localedef --delete-from-archive "$l" 2>/dev/null || true
        rm -rf -- "/usr/lib/locale/${l:?}"
    done
    if [[ -f $LAB_STATE/orig-supported-local ]]; then cp -p "$LAB_STATE/orig-supported-local" "$TS_SUPPORTED_LOCAL"; else rm -f -- "$TS_SUPPORTED_LOCAL"; fi
    rm -rf -- "${TS_HOME:?}"
    for f in owns-lab fault orig-timezone target-timezone orig-default-locale orig-default-locale.absent orig-supported-local orig-supported-local.absent created-dropdir TASKS.txt; do
        rm -f -- "${LAB_STATE:?}/$f"
    done
    echo '元のタイムゾーン・NTP設定・ロケール設定に戻しました。'
}
