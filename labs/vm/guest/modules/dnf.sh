#!/bin/bash
# title: dnf/rpm でローカルrepo(署名付き)から導入・更新・巻き戻し・検証・依存の回復 (RHEL系)
# roles: app
# Guest-only, RHEL family only (dnf4: RHEL/Rocky/Alma 8-10). Builds its own tiny noarch rpms; touches only dojo-* packages,
# /srv/dojo-repo, /etc/yum.repos.d/dojo-lab.repo (learner-created), /etc/pki/rpm-gpg/RPM-GPG-KEY-dojo-lab and the throwaway gpg key in $LAB_STATE.

_dn_ctx() {
    [[ ${LAB_ID:-} == dnf && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/dnf ]] || { echo 'dnf: unexpected lab context' >&2; return 1; }
    local id
    id=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-unknown}")
    case $id in
        rocky|almalinux|rhel|centos) ;;
        *) echo "${id:-unknown}: this lab needs a RHEL-family VM" >&2; return 1 ;;
    esac
    DN_REPO=/srv/dojo-repo
    DN_KEYFILE=/etc/pki/rpm-gpg/RPM-GPG-KEY-dojo-lab
    DN_REPOFILE=/etc/yum.repos.d/dojo-lab.repo
    DN_GNUPG=${LAB_STATE:?}/gnupg
    DN_PKGS="dojo-hello dojo-lib dojo-plugin"
    DN_DNFQ=(dnf --disablerepo='*' --enablerepo=dojo-lab)
    [[ ! -L $DN_REPO && ! -L $DN_KEYFILE && ! -L $DN_REPOFILE ]] || { echo 'dnf: unexpected lab context (symlink)' >&2; return 1; }
}

# $1 name $2 version $3 Requires line (may be empty)
_dn_build() {
    local name=$1 ver=$2 req=$3 top=${LAB_STATE:?}/rpmbuild
    mkdir -p "$top"/{SPECS,BUILD,RPMS,SRPMS,BUILDROOT}
    {
        echo "Name: $name"
        echo "Version: $ver"
        echo 'Release: 1'
        echo "Summary: LinuxDOJO lab package $name"
        echo 'License: MIT'
        echo 'BuildArch: noarch'
        [[ -n $req ]] && echo "$req"
        echo '%description'
        echo "LinuxDOJO dnf lab package $name $ver."
        echo '%install'
        case $name in
            dojo-lib)
                echo 'mkdir -p %{buildroot}/usr/lib/dojo'
                echo "printf 'dojo-lib $ver\\n' > %{buildroot}/usr/lib/dojo/dojo-lib.sh"
                echo '%files'
                echo '/usr/lib/dojo/dojo-lib.sh' ;;
            dojo-hello)
                echo 'mkdir -p %{buildroot}/usr/bin %{buildroot}/etc'
                echo "printf '#!/bin/sh\\ncat /usr/lib/dojo/dojo-lib.sh\\necho dojo-hello $ver\\n' > %{buildroot}/usr/bin/dojo-hello"
                echo 'chmod 755 %{buildroot}/usr/bin/dojo-hello'
                echo "printf 'greeting=hello\\n' > %{buildroot}/etc/dojo-hello.conf"
                echo '%files'
                echo '%attr(0755,root,root) /usr/bin/dojo-hello'
                echo '%config(noreplace) /etc/dojo-hello.conf' ;;
            dojo-plugin)
                echo 'mkdir -p %{buildroot}/usr/lib/dojo'
                echo "printf 'dojo-plugin $ver\\n' > %{buildroot}/usr/lib/dojo/plugin.sh"
                echo '%files'
                echo '/usr/lib/dojo/plugin.sh' ;;
        esac
    } > "$top/SPECS/$name-$ver.spec"
    rpmbuild --quiet --define "_topdir $top" -bb "$top/SPECS/$name-$ver.spec" >/dev/null || return 1
}

lab_setup() {
    _dn_ctx || return 1
    local c
    for c in dnf rpm rpmbuild rpmsign createrepo_c gpg curl python3; do
        command -v "$c" >/dev/null || { echo "$c が必要です (dnf install rpm-build rpm-sign createrepo_c gnupg2 python3-dnf-plugin-versionlock)。" >&2; return 1; }
    done
    dnf versionlock --help >/dev/null 2>&1 || { echo 'dnf versionlock プラグインが必要です (python3-dnf-plugin-versionlock)。' >&2; return 1; }
    [[ ! -e $DN_REPO && ! -e $DN_KEYFILE && ! -e $DN_REPOFILE ]] || [[ -f $LAB_STATE/created ]] || { echo '専用パス(/srv/dojo-repo など)が既にあります。上書きしません。' >&2; return 1; }
    if rpm -q $DN_PKGS >/dev/null 2>&1; then echo 'dojo-* パッケージが既に導入されています。先に reset してください。' >&2; return 1; fi
    chmod 755 "$LAB_ROOT" "$LAB_ROOT/state" 2>/dev/null || true
    : > "$LAB_STATE/created"
    install -d -m 700 "$DN_GNUPG"
    GNUPGHOME=$DN_GNUPG gpg --batch --passphrase '' --quick-generate-key 'dojo-lab-key' rsa2048 sign never >/dev/null 2>&1 || { echo '使い捨て鍵の生成に失敗しました。' >&2; return 1; }
    local fpr keyid
    fpr=$(GNUPGHOME=$DN_GNUPG gpg --with-colons --list-keys dojo-lab-key | awk -F: '$1=="fpr"{print $10; exit}')
    keyid=${fpr: -16}
    printf '%s\n' "${keyid,,}" > "$LAB_STATE/keyid"
    install -d -m 755 "$DN_REPO"
    GNUPGHOME=$DN_GNUPG gpg --batch --export --armor dojo-lab-key > "$DN_KEYFILE"
    chmod 644 "$DN_KEYFILE"
    _dn_build dojo-lib 1.0 '' && _dn_build dojo-lib 2.0 '' \
        && _dn_build dojo-hello 1.0 'Requires: dojo-lib' && _dn_build dojo-hello 2.0 'Requires: dojo-lib >= 2.0' \
        && _dn_build dojo-plugin 1.0 'Requires: dojo-lib < 2.0' || { echo 'rpmbuild に失敗しました。' >&2; return 1; }
    cp "$LAB_STATE"/rpmbuild/RPMS/noarch/*.rpm "$DN_REPO/" || return 1
    rpmsign --define "_gpg_name $keyid" --define "_gpg_path $DN_GNUPG" --addsign "$DN_REPO"/*.rpm >/dev/null 2>&1 || { echo 'rpmsign に失敗しました。' >&2; return 1; }
    createrepo_c --quiet "$DN_REPO" || return 1
    GNUPGHOME=$DN_GNUPG gpg --batch --yes --detach-sign --armor -u "$keyid" -o "$DN_REPO/repodata/repomd.xml.asc" "$DN_REPO/repodata/repomd.xml" || return 1
    chmod -R a+rX "$DN_REPO"
    cat > "$LAB_STATE/TASKS.txt" <<TASKS
ローカル repo $DN_REPO (署名付き: パッケージとメタデータ) と公開鍵 $DN_KEYFILE を用意しました。
パッケージ: dojo-lib / dojo-hello (どちらも 1.0 と 2.0)、dojo-plugin (1.0 のみ。dojo-lib < 2.0 に依存)
他の repo を使うとネットワークに依存するので、操作は --disablerepo='*' --enablerepo=dojo-lab で行うこと。
1. $DN_REPOFILE を自分で書く。repo id は dojo-lab、baseurl は file://$DN_REPO、
   gpgcheck=1 と repo_gpgcheck=1、gpgkey は file://$DN_KEYFILE。dnf repolist で見えることを確認
   (gpgcheck=0 や --nogpgcheck は不合格)
2. dnf info / repoquery で各パッケージを調べ、sudo dojo-vm-lab dnf break を実行
   (1.0 を導入したあとで、ファイルを壊します)
3. rpm -qa / -qi / -ql / -qf / -V / --verify で壊れた箇所を特定し (rpm -V の記号 S 5 T M と missing を読む)、dnf reinstall で直す
4. dnf upgrade dojo-hello を試す。依存の衝突エラーを読む (plugin が lib < 2.0 を要求)。
   解決策を選ぶ (--allowerasing は何を消すか確認すること)。upgrade 後 dojo-hello は 2.0 になる
5. dnf history で履歴を見て、undo か downgrade で 1.0 へ戻し、plugin も含め元の組に復元する
6. dojo-hello に dnf versionlock を掛け、dnf check-update で 2.0 が提示されないことを確認
7. sudo dojo-vm-lab dnf check
TASKS
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _dn_ctx || return 1
    [[ -f $LAB_STATE/created && -d $DN_REPO/repodata ]] || { echo '先に setup を実行してください。' >&2; return 1; }
    if ! "${DN_DNFQ[@]}" repolist 2>/dev/null | grep -q '^dojo-lab'; then
        echo "dojo-lab repo が使えません。$DN_REPOFILE を作って dnf repolist で確認してから break してください。" >&2; return 1
    fi
    if rpm -q $DN_PKGS >/dev/null 2>&1; then echo 'dojo-* が既に導入済みです。reset してやり直してください。' >&2; return 1; fi
    "${DN_DNFQ[@]}" -y install dojo-hello-1.0-1 dojo-lib-1.0-1 dojo-plugin-1.0-1 || { echo '導入に失敗しました(repo の署名設定を確認)。' >&2; return 1; }
    rm -f /usr/lib/dojo/dojo-lib.sh
    printf '# tampered\n' >> /usr/bin/dojo-hello
    chmod 777 /usr/lib/dojo/plugin.sh
    : > "$LAB_STATE/broken"
    echo '壊しました: dojo-lib のファイル削除、dojo-hello の改変、plugin のモード変更。rpm -V で調べてください。'
}

lab_check() {
    _dn_ctx || return 1
    [[ -f $LAB_STATE/broken ]] || { echo 'break済みの記録がありません。先に break を実行してください。' >&2; return 1; }
    local v out keyid rc
    keyid=$(cat "$LAB_STATE/keyid")
    python3 - "$DN_REPO" <<'PY' || { echo "[dojo-lab] の設定が要件を満たしません(baseurl/gpgcheck=1/repo_gpgcheck=1/gpgkey)。" >&2; return 1; }
import configparser, glob, sys
repo = sys.argv[1]
ok = False
for f in glob.glob('/etc/yum.repos.d/*.repo'):
    c = configparser.RawConfigParser(strict=False)
    try: c.read(f)
    except configparser.Error: continue
    if c.has_section('dojo-lab'):
        s = c['dojo-lab']
        ok = (s.get('baseurl', '').strip() == 'file://' + repo and s.get('gpgcheck', '0').strip() == '1'
              and s.get('repo_gpgcheck', '0').strip() == '1' and s.get('enabled', '1').strip() == '1'
              and 'RPM-GPG-KEY-dojo-lab' in s.get('gpgkey', ''))
raise SystemExit(0 if ok else 1)
PY
    "${DN_DNFQ[@]}" repolist 2>/dev/null | grep -q '^dojo-lab' || { echo 'dnf repolist で dojo-lab が見えません。' >&2; return 1; }
    for v in $DN_PKGS; do
        rpm -q "$v" >/dev/null 2>&1 || { echo "$v が導入されていません。" >&2; return 1; }
    done
    [[ $(rpm -q --qf '%{VERSION}' dojo-hello) == 1.0 && $(rpm -q --qf '%{VERSION}' dojo-lib) == 1.0 && $(rpm -q --qf '%{VERSION}' dojo-plugin) == 1.0 ]] \
        || { echo '最終状態は dojo-hello / dojo-lib / dojo-plugin すべて 1.0 のはずです。' >&2; return 1; }
    out=$(rpm -V dojo-hello dojo-lib dojo-plugin 2>&1)
    [[ -z $out ]] || { echo "rpm -V がまだ差分を報告しています: $out" >&2; return 1; }
    /usr/bin/dojo-hello 2>/dev/null | grep -qx 'dojo-hello 1.0' || { echo 'dojo-hello が実際に動作しません。' >&2; return 1; }
    rpm -q --qf '%{SIGPGP:pgpsig}\n' dojo-hello | grep -qi "$keyid" || { echo 'dojo-hello の署名が使い捨て鍵のものではありません。' >&2; return 1; }
    rpm -q gpg-pubkey --qf '%{SUMMARY}\n' 2>/dev/null | grep -q 'dojo-lab-key' || { echo '公開鍵が rpm に取り込まれていません。' >&2; return 1; }
    local id hit=0
    while read -r id; do
        if dnf -q history info "$id" 2>/dev/null | grep -q 'dojo-hello-2.0'; then hit=1; break; fi
    done < <(dnf -q history list 2>/dev/null | awk '$1 ~ /^[0-9]+$/ {print $1}')
    [[ $hit == 1 ]] || { echo 'dojo-hello 2.0 を扱った履歴がありません。upgrade を体験してから戻してください。' >&2; return 1; }
    dnf versionlock list 2>/dev/null | grep -q '^dojo-hello' || { echo 'dojo-hello の versionlock がありません。' >&2; return 1; }
    "${DN_DNFQ[@]}" -q check-update dojo-hello >/dev/null 2>&1 && rc=0 || rc=$?
    [[ $rc -eq 0 ]] || { echo "dojo-hello に更新候補が残っています(versionlock が効いていません, rc=$rc)。" >&2; return 1; }
    echo '署名付き repo、1.0 への復元、rpm -V の正常化、履歴、versionlock をすべて実状態で確認しました。'
}

lab_reset() {
    _dn_ctx || return 1
    dnf versionlock delete dojo-hello dojo-lib dojo-plugin >/dev/null 2>&1 || true
    local p k
    for p in $DN_PKGS; do
        if rpm -q "$p" >/dev/null 2>&1; then rpm -e --nodeps "$p" 2>/dev/null || true; fi
    done
    for k in $(rpm -qa gpg-pubkey --qf '%{NAME}-%{VERSION}-%{RELEASE} %{SUMMARY}\n' 2>/dev/null | awk '/dojo-lab-key/ {print $1}'); do
        rpm -e "$k" 2>/dev/null || true
    done
    if [[ -f $DN_REPOFILE ]] && grep -q '^\[dojo-lab\]' "$DN_REPOFILE"; then rm -f "$DN_REPOFILE"; fi
    if [[ -f $LAB_STATE/created ]]; then
        rm -rf "${DN_REPO:?}"
        rm -f "$DN_KEYFILE"
    fi
    rm -rf "${DN_GNUPG:?}" "${LAB_STATE:?}/rpmbuild"
    rm -f "${LAB_STATE:?}/created" "${LAB_STATE:?}/broken" "${LAB_STATE:?}/keyid" "${LAB_STATE:?}/TASKS.txt"
    dnf clean all >/dev/null 2>&1 || true
    echo 'dojo-* パッケージ・専用repo・使い捨て鍵・取り込んだ公開鍵を削除しました。'
}
