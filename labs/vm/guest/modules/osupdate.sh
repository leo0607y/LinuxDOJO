# title: 署名付きリポジトリの署名エラーと依存不整合から復旧する
# roles: app
# No action is permitted outside the dispatcher-provisioned app VM.

_osu_guard() {
    [[ ${LAB_ID:-} == osupdate && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/osupdate ]] || { echo 'osupdate: unexpected lab context' >&2; return 1; }
    [[ ! -L $LAB_STATE && ! -L /etc/apt/sources.list.d/dojo-update.sources && ! -L /etc/apt/keyrings/dojo-update.gpg ]] || { echo 'osupdate: symbolic target rejected' >&2; return 1; }
}

_osu_source=/etc/apt/sources.list.d/dojo-update.sources
_osu_keyring=/etc/apt/keyrings/dojo-update.gpg
_osu_pkgs='dojo-lib dojo-hello'

# Unprivileged-testable builder: base must be a new directory owned by the caller.
_osu_build() {
    local base=$1 version name tree dep
    [[ -d $base && ! -L $base && ! -e $base/build && ! -e $base/debs ]] || return 1
    mkdir -m 0755 -- "$base/build" "$base/debs" || return 1
    for name in dojo-lib dojo-hello; do
        for version in 1.0 2.0; do
            tree="$base/build/${name}_$version"
            mkdir -p -- "$tree/DEBIAN" "$tree/usr/share/$name" || return 1
            dep=
            [[ $name != dojo-hello ]] || dep="Depends: dojo-lib (>= $version)"
            {
                printf 'Package: %s\nVersion: %s\nArchitecture: all\n' "$name" "$version"
                printf 'Maintainer: LinuxDOJO contributors <noreply@users.noreply.github.com>\n'
                [[ -z $dep ]] || printf '%s\n' "$dep"
                printf 'Description: Disposable LinuxDOJO OS update exercise (%s)\n' "$name"
                printf ' Used only inside the dedicated disposable training VM.\n'
            } > "$tree/DEBIAN/control"
            printf '%s %s\n' "$name" "$version" > "$tree/usr/share/$name/version"
            chmod 0644 "$tree/DEBIAN/control" "$tree/usr/share/$name/version"
            dpkg-deb --root-owner-group --build "$tree" "$base/debs/${name}_${version}_all.deb" >/dev/null || return 1
        done
    done
}

# Create a disposable signing key in a dedicated GNUPGHOME and print its fingerprint.
_osu_genkey() {
    local home=$1 label=$2
    install -d -m 0700 -- "$home" || return 1
    gpg --homedir "$home" --batch --quiet --passphrase '' \
        --quick-generate-key "LinuxDOJO $label <noreply@users.noreply.github.com>" ed25519 sign never >/dev/null 2>&1 || return 1
    gpg --homedir "$home" --batch --with-colons --fingerprint 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}'
}

# publish <repo> <debs> <gnupghome> <version>...  : flat repo with signed InRelease.
_osu_publish() {
    local repo=$1 debs=$2 home=$3 name version file
    shift 3
    install -d -m 0755 -- "$repo" || return 1
    rm -f -- "${repo:?}"/*.deb "${repo:?}/Packages" "${repo:?}/Release" "${repo:?}/InRelease"
    : > "$repo/Packages"
    for version in "$@"; do
        for name in dojo-lib dojo-hello; do
            file="${name}_${version}_all.deb"
            cp -- "$debs/$file" "$repo/$file" || return 1
            chmod 0644 "$repo/$file"
            {
                dpkg-deb -f "$repo/$file"
                printf 'Filename: ./%s\nSize: %s\nSHA256: %s\n\n' "$file" "$(stat -c %s "$repo/$file")" "$(sha256sum "$repo/$file" | cut -d' ' -f1)"
            } >> "$repo/Packages"
        done
    done
    {
        printf 'Origin: LinuxDOJO\nLabel: dojo-update\nSuite: stable\nCodename: dojo-update\n'
        printf 'Date: %s\nArchitectures: all\n' "$(LC_ALL=C date -u '+%a, %d %b %Y %H:%M:%S UTC')"
        printf 'SHA256:\n %s %s Packages\n' "$(sha256sum "$repo/Packages" | cut -d' ' -f1)" "$(stat -c %s "$repo/Packages")"
    } > "$repo/Release"
    gpg --homedir "$home" --batch --quiet --yes --passphrase '' --digest-algo SHA256 --clearsign -o "$repo/InRelease" "$repo/Release" || return 1
    rm -f -- "${repo:?}/Release"
    chmod 0644 "$repo/Packages" "$repo/InRelease"
}

# Primary fingerprints (one per line) of a key file, without touching any real keyring.
_osu_fprs() {
    local scratch out
    scratch=$(mktemp -d) || return 1
    out=$(GNUPGHOME=$scratch gpg --batch --quiet --show-keys --with-colons --fingerprint "$1" 2>/dev/null | awk -F: '$1=="pub"{p=1;next} $1=="fpr"&&p{print $10;p=0}')
    rm -rf -- "${scratch:?}"
    printf '%s\n' "$out"
}

# apt-get update restricted to our source only, so unrelated repositories never matter.
_osu_update() {
    LC_ALL=C apt-get update -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/var/lib/linuxdojo-vm-lab/state/osupdate/only-source -o APT::Get::List-Cleanup=0 2>&1
}

_osu_status() { dpkg-query -W -f='${Status}|${Version}' "$1" 2>/dev/null || true; }

lab_setup() {
    _osu_guard || return 1
    local tool p fpr decoy_fpr real=a other=b
    for tool in gpg dpkg-deb apt-get apt-mark sha256sum; do command -v "$tool" >/dev/null || { echo "osupdate: $tool がありません" >&2; return 1; }; done
    [[ ! -e $LAB_STATE/marker && ! -e $LAB_STATE/repo && ! -e $LAB_STATE/build && ! -e $LAB_STATE/gnupg ]] || { echo '既存の実習があります。resetしてください。'; return 1; }
    [[ ! -e $_osu_source && ! -e $_osu_keyring ]] || { echo 'dojo-update の source/keyring が既にあります。上書きしません。'; return 1; }
    for p in $_osu_pkgs; do [[ -z $(_osu_status "$p") ]] || { echo "$p が既にあります。上書きしません。"; return 1; }; done
    chmod 0755 "$LAB_STATE" || return 1
    printf 'created\n' > "$LAB_STATE/marker"
    _osu_build "$LAB_STATE" || return 1
    fpr=$(_osu_genkey "$LAB_STATE/gnupg" 'Update Signing') || return 1
    [[ $fpr =~ ^[0-9A-F]{40}$ ]] || return 1
    decoy_fpr=$(_osu_genkey "$LAB_STATE/decoy-gnupg" 'Decoy') || return 1
    [[ $decoy_fpr != "$fpr" ]] || return 1
    install -d -m 0755 "$LAB_STATE/keys"
    # Randomise which candidate is genuine; the learner must match fingerprints.
    (( RANDOM % 2 )) || { real=b; other=a; }
    gpg --homedir "$LAB_STATE/gnupg" --batch --armor --export > "$LAB_STATE/keys/candidate-$real.asc" || return 1
    gpg --homedir "$LAB_STATE/decoy-gnupg" --batch --armor --export > "$LAB_STATE/keys/candidate-$other.asc" || return 1
    chmod 0644 "$LAB_STATE"/keys/*.asc
    rm -rf -- "${LAB_STATE:?}/decoy-gnupg"
    printf '%s\n' "$fpr" > "$LAB_STATE/fingerprint.raw"
    printf '%s\n' "$fpr" | sed 's/.\{4\}/& /g; s/ $//' > "$LAB_STATE/FINGERPRINT.txt"
    chmod 0644 "$LAB_STATE/FINGERPRINT.txt"
    _osu_publish "$LAB_STATE/repo" "$LAB_STATE/debs" "$LAB_STATE/gnupg" 1.0 || return 1
    install -d -m 0755 /etc/apt/keyrings "$LAB_STATE/only-source"
    gpg --homedir "$LAB_STATE/gnupg" --batch --export > "$_osu_keyring" || return 1
    chmod 0644 "$_osu_keyring"
    cat > "$_osu_source" <<SRC
Types: deb
URIs: file://$LAB_STATE/repo
Suites: ./
Signed-By: $_osu_keyring
SRC
    chmod 0644 "$_osu_source"
    ln -s "$_osu_source" "$LAB_STATE/only-source/dojo-update.sources"
    cp -- "$_osu_source" "$LAB_STATE/sources.orig"
    _osu_update >/dev/null || { echo '初期の apt-get update に失敗しました。'; return 1; }
    apt-get install -y dojo-lib=1.0 dojo-hello=1.0 >/dev/null || { echo '1.0 の導入に失敗しました。'; return 1; }
    printf 'installed\n' > "$LAB_STATE/phase"
    cat > "$LAB_STATE/TASKS.txt" <<TASK
専用VM実習: 署名付きリポジトリ(dojo-update)の更新が止まりました。
まず sudo dojo-vm-lab osupdate break で故障を起こします。その後 sudo -i で作業します。

1. 症状を読む
   apt-get update を実行し、E:/W: の行(NO_PUBKEY・署名検証・The repository ... is not signed 等)を読む。
   dojo-lib/dojo-hello の現在版は dpkg-query -W、apt-mark showhold、apt-cache policy で確認。
2. 鍵を信用してよいか確かめる
   $LAB_STATE/keys/ に候補の公開鍵が2つあります(どちらが本物かは名前から分かりません)。
   $LAB_STATE/FINGERPRINT.txt は信頼できる経路で得た指紋です。
   gpg --show-keys --with-fingerprint <候補ファイル> で指紋を見比べ、一致する方だけ使う。
3. keyring を復元する
   source の Signed-By が指すファイル(/etc/apt/keyrings/dojo-update.gpg)はバイナリ形式です。
   armor形式の鍵を変換して置く(gpg --dearmor)。権限は apt が読める 0644。
   apt-get update が警告もエラーもなく終わるまで確認。
4. 依存・holdを直す
   apt list --upgradable、apt-mark showhold を読み、dojo-hello だけ上げると何が起きるか確認。
   holdの理由を判断して解除し、apt-get upgrade 等で dojo-lib と dojo-hello を 2.0 にする。
5. 確認: dpkg --audit が空、apt-get check が成功。 sudo dojo-vm-lab osupdate check

禁止: sourceに trusted=yes や allow-insecure を書く、--allow-unauthenticated を使う等の署名検証の回避。
check はそれらを検出します。この実習の鍵は手順練習用の使い捨てで、本物の鍵管理ではありません。
TASK
    echo "setup完了(1.0導入済み)。次に break してから $LAB_STATE/TASKS.txt を読みます。"
}

lab_break() {
    _osu_guard || return 1
    [[ -f $LAB_STATE/marker && -f $LAB_STATE/phase && $(cat "$LAB_STATE/phase") == installed && ! -e $LAB_STATE/broken ]] || { echo '先にsetupしてください(既にbreak済みの場合はresetから)。'; return 1; }
    [[ $(_osu_status dojo-lib) == 'install ok installed|1.0' && $(_osu_status dojo-hello) == 'install ok installed|1.0' && -f $_osu_keyring ]] || { echo '想定した導入状態ではありません。'; return 1; }
    _osu_publish "$LAB_STATE/repo" "$LAB_STATE/debs" "$LAB_STATE/gnupg" 1.0 2.0 || return 1
    rm -f -- "$_osu_keyring"
    apt-mark hold dojo-lib >/dev/null || return 1
    (wc -l < /var/log/apt/history.log 2>/dev/null || echo 0) > "$LAB_STATE/histlines"
    printf 'broken\n' > "$LAB_STATE/phase"
    printf 'broken\n' > "$LAB_STATE/broken"
    echo '故障を投入しました。apt-get update のエラーを読むところから始めます。'
}

lab_check() {
    _osu_guard || return 1
    [[ -f $LAB_STATE/marker && -f $LAB_STATE/broken && -f $LAB_STATE/fingerprint.raw && -f $LAB_STATE/FINGERPRINT.txt ]] || { echo '先に setup と break を実行してください。'; return 1; }
    local p out fpr found hist n
    # 1) the keyring must be a real key whose fingerprint matches the trusted one.
    [[ -f $_osu_keyring && ! -L $_osu_keyring ]] || { echo "keyring $_osu_keyring がありません。"; return 1; }
    fpr=$(tr -d ' \n' < "$LAB_STATE/FINGERPRINT.txt")
    [[ $fpr == "$(cat "$LAB_STATE/fingerprint.raw")" ]] || { echo 'FINGERPRINT.txt が変更されています。'; return 1; }
    found=$(_osu_fprs "$_osu_keyring")
    [[ $found == "$fpr" ]] || { echo 'keyring の指紋が FINGERPRINT.txt と一致しません(偽の鍵や余分な鍵は不可)。'; return 1; }
    # 2) verification must not be bypassed.
    cmp -s "$_osu_source" "$LAB_STATE/sources.orig" || { echo 'source ファイルが変更されています。鍵を直し、sourceは元のままにします。'; return 1; }
    if grep -Eiq 'trusted|insecure|allow-weak|allow-downgrade' "$_osu_source"; then return 1; fi
    if grep -rEhis 'allowunauthenticated|allowinsecure|allowdowngradetoinsecure|allow-insecure|trusted' /etc/apt/apt.conf /etc/apt/apt.conf.d 2>/dev/null | grep -Eiv '^\s*(//|#)' | grep -Eiq 'true|yes|1'; then
        echo '署名検証を弱める apt 設定があります。'; return 1
    fi
    if apt-config dump 2>/dev/null | grep -Ei 'unauthenticated|insecure|trusted' | grep -Eq '"(true|1|yes)"'; then
        echo '署名検証を弱める apt 設定が有効です。'; return 1
    fi
    n=$(cat "$LAB_STATE/histlines" 2>/dev/null || echo 0)
    hist=$(tail -n +"$((n + 1))" /var/log/apt/history.log 2>/dev/null | grep '^Commandline:' || true)
    if grep -Eiq 'allow-unauthenticated|allow-insecure|trusted=yes|AllowUnauthenticated' <<<"$hist"; then
        echo '署名検証を回避したaptコマンドの履歴があります。resetしてやり直してください。'; return 1
    fi
    # 3) real apt-get update must succeed with no warnings or errors.
    out=$(_osu_update) || { echo 'apt-get update が失敗します。'; printf '%s\n' "$out" | grep -E '^(E|W):' | head -5; return 1; }
    if grep -Eq '^(E|W):|WARNING|NO_PUBKEY|not signed|Err:' <<<"$out"; then echo 'apt-get update にまだ警告があります。'; return 1; fi
    # 4) both packages at 2.0, content matches the signed build, no hold.
    for p in dojo-lib dojo-hello; do
        [[ $(_osu_status "$p") == 'install ok installed|2.0' ]] || { echo "$p が 2.0 に更新されていません。"; return 1; }
    done
    [[ -z $(apt-mark showhold 2>/dev/null | grep -E '^dojo-(lib|hello)$' || true) ]] || { echo 'hold が残っています。'; return 1; }
    [[ $(cat /usr/share/dojo-lib/version) == 'dojo-lib 2.0' && $(cat /usr/share/dojo-hello/version) == 'dojo-hello 2.0' ]] || { echo '導入内容が2.0と一致しません。'; return 1; }
    # 5) package database consistency.
    [[ -z $(dpkg --audit 2>&1) ]] || { echo 'dpkg --audit に問題があります。'; return 1; }
    apt-get check >/dev/null 2>&1 || { echo 'apt-get check が失敗します。'; return 1; }
    printf 'complete\n' > "$LAB_STATE/phase"
    echo '修了: 鍵の指紋を照合してkeyringを復元し、holdを解除して2.0へ更新しました。'
}

lab_reset() {
    _osu_guard || return 1
    [[ -f $LAB_STATE/marker ]] || { echo 'この実習が作った状態の証拠がありません。自動削除しません。'; return 1; }
    local p
    apt-mark unhold dojo-lib dojo-hello >/dev/null 2>&1 || true
    for p in dojo-hello dojo-lib; do
        [[ -z $(_osu_status "$p") ]] || dpkg --purge "$p" >/dev/null 2>&1 || true
    done
    rm -f -- "$_osu_source" "$_osu_keyring"
    rm -f -- /var/lib/apt/lists/*linuxdojo-vm-lab_state_osupdate_repo_* 2>/dev/null || true
    local d
    for d in repo build debs gnupg decoy-gnupg keys only-source; do rm -rf -- "${LAB_STATE:?}/$d"; done
    for d in marker broken phase TASKS.txt FINGERPRINT.txt fingerprint.raw sources.orig histlines; do rm -f -- "${LAB_STATE:?}/$d"; done
    echo '教材パッケージ・source・keyring・状態を解除しました。'
}
