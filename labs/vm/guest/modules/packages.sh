# title: 本物のdebを導入・設定・更新・故障復旧・remove・purgeする
# No action is permitted outside the dispatcher-provisioned app VM.

_packages_paths() {
    [[ ${LAB_ID:-} == packages && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/packages ]] || { echo 'packages: unexpected lab context' >&2; return 1; }
    [[ ! -L /etc/dojo-example.conf && ! -L /usr/bin/dojo-example ]] || { echo 'packages: symbolic target rejected' >&2; return 1; }
}

# This builder has no privileged side effects and is also tested unprivileged.
# Its caller must supply a new directory it owns. It never installs packages.
_packages_build() {
    local base=$1 version tree message
    [[ -d $base && ! -L $base && ! -e $base/build && ! -e $base/debs ]] || return 1
    mkdir -m 0755 -- "$base/build" "$base/debs" || return 1
    for version in 1.0 2.0; do
        tree="$base/build/$version"
        mkdir -p -- "$tree/DEBIAN" "$tree/etc" "$tree/usr/bin" || return 1
        cat > "$tree/DEBIAN/control" <<CONTROL
Package: dojo-example
Version: $version
Architecture: all
Maintainer: LinuxDOJO contributors <noreply@users.noreply.github.com>
Depends: python3
Description: Disposable LinuxDOJO package lifecycle exercise
 This package is used only inside the dedicated disposable training VM.
CONTROL
        printf '/etc/dojo-example.conf\n' > "$tree/DEBIAN/conffiles"
        message=hello
        [[ $version != 2.0 ]] || message=welcome
        printf 'message=%s\n' "$message" > "$tree/etc/dojo-example.conf"
        cat > "$tree/usr/bin/dojo-example" <<'PROGRAM'
#!/usr/bin/python3
import argparse
import pathlib
import re
import sys

VERSION = "@@VERSION@@"
parser = argparse.ArgumentParser(description="LinuxDOJO disposable package")
parser.add_argument("--version", action="version", version=VERSION)
parser.add_argument("--config", default="/etc/dojo-example.conf")
args = parser.parse_args()
try:
    text = pathlib.Path(args.config).read_text(encoding="utf-8")
    match = re.fullmatch(r"message=([A-Za-z0-9_-]{1,80})\n?", text)
    if not match:
        raise ValueError("expected exactly message=<letters/digits/_/->")
except (OSError, ValueError) as error:
    print("configuration error: " + str(error), file=sys.stderr)
    sys.exit(2)
print("version=" + VERSION + " message=" + match.group(1))
PROGRAM
        sed -i "s/@@VERSION@@/$version/" "$tree/usr/bin/dojo-example"
        chmod 0755 "$tree/usr/bin/dojo-example"
        chmod 0644 "$tree/DEBIAN/control" "$tree/DEBIAN/conffiles" "$tree/etc/dojo-example.conf"
        dpkg-deb --root-owner-group --build "$tree" "$base/debs/dojo-example_${version}_all.deb" >/dev/null || return 1
    done
}

_packages_status() {
    dpkg-query -W -f='${Status}|${Version}' dojo-example 2>/dev/null || true
}

_packages_installed() {
    local version=$1 message=$2
    [[ $(_packages_status) == "install ok installed|$version" ]] || { echo "dojo-example $version が正常に導入されていません。dpkg-query -W を確認。"; return 1; }
    [[ -f /usr/bin/dojo-example && -f /etc/dojo-example.conf ]] || return 1
    [[ $(dojo-example --version) == "$version" ]] || return 1
    [[ $(dojo-example) == "version=$version message=$message" ]] || { echo '実際のコマンド出力が設定と一致しません。'; return 1; }
    # Verify packaged executable, while deliberately allowing the conffile edit.
    cmp -s /usr/bin/dojo-example "$LAB_STATE/build/$version/usr/bin/dojo-example" || { echo 'プログラム本文を変更せず設定を直します。'; return 1; }
}

lab_setup() {
    _packages_paths || return 1
    [[ ! -e $LAB_STATE/phase && ! -e $LAB_STATE/build && ! -e $LAB_STATE/debs ]] || { echo '既存の実習があります。続けるかresetしてください。'; return 1; }
    [[ -z $(_packages_status) && ! -e /etc/dojo-example.conf && ! -e /usr/bin/dojo-example ]] || { echo '同名パッケージ/ファイルが既にあります。上書きしません。'; return 1; }
    _packages_build "$LAB_STATE" || return 1
    printf 'dojo_%s\n' "$(cat /proc/sys/kernel/random/uuid | cut -c1-8)" > "$LAB_STATE/message"
    printf 'install\n' > "$LAB_STATE/phase"
    cat > "$LAB_STATE/TASK.txt" <<TASK
本物のapt/dpkgを使う専用VM実習です。対象はdojo-exampleだけです。
この専用VMの中だけで sudo -i を実行し、rootの作業シェルへ入ります。
cd $LAB_STATE
各段階の末尾で sudo dojo-vm-lab packages check を実行します。
途中のcheck成功は「その段階の確認」で、purgeまで済むまで修了ではありません。

1. 導入: dpkg-deb -I debs/dojo-example_1.0_all.deb と -c で内容/依存を確認。
   sudo apt install ./debs/dojo-example_1.0_all.deb
   command -v dojo-example; dpkg-query -W dojo-example; dojo-example; check
2. 設定: sudoedit /etc/dojo-example.conf
   message=$(cat "$LAB_STATE/message") の1行に変更。実行結果を確認; check
3. 更新: v2は既定値がwelcomeに変わっています。ローカル設定を保って更新。
   sudo apt -o Dpkg::Options::=--force-confold install ./debs/dojo-example_2.0_all.deb
   dojo-example --version; dojo-example; check
   --force-confoldはこの学習用の明示的な選択です。通常は差分を読み保持/置換を判断します。
4. 故障: sudo dojo-vm-lab packages break
   dojo-example; echo \$?; cat /etc/dojo-example.conf
   stderrの根拠を読み、message=$(cat "$LAB_STATE/message") に修正。
   実行ファイルの変更や再導入で隠さず設定だけ復旧; check
5. 削除: sudo apt remove dojo-example
   dpkg-query -W -f='\${Status}\n' dojo-example; test -f /etc/dojo-example.conf
   実行ファイルが消え設定は残ることを確認; check
6. 完全削除: sudo apt purge dojo-example
   設定も消えたことを確認; check → ここで初めて修了

パッケージDB、/var/log/apt/history.log、/var/log/dpkg.logも読み、各操作の証拠を残します。
これはローカルdebの実習です。外部リポジトリ署名・鍵更新、RPMの実操作は別範囲です。
TASK
    echo "手順: $LAB_STATE/TASK.txt。setupは導入せずローカルdebを作るだけです。"
}

lab_break() {
    _packages_paths || return 1
    [[ -f $LAB_STATE/phase && $(cat "$LAB_STATE/phase") == fault-ready ]] || { echo 'v2への更新checkまで進めてからbreakします。'; return 1; }
    _packages_installed 2.0 "$(cat "$LAB_STATE/message")" || return 1
    printf 'message has invalid syntax\n' > /etc/dojo-example.conf
    if dojo-example > "$LAB_STATE/failure.stdout" 2> "$LAB_STATE/failure.stderr"; then
        echo '期待した設定エラーが発生しませんでした。'; return 1
    fi
    grep -q 'configuration error:' "$LAB_STATE/failure.stderr" || return 1
    printf 'repair\n' > "$LAB_STATE/phase"
    echo "設定エラーを投入しました。dojo-exampleのstderrと $LAB_STATE/failure.stderr を読みます。"
}

lab_check() {
    _packages_paths || return 1
    [[ -f $LAB_STATE/phase && -f $LAB_STATE/message ]] || { echo '先にsetupしてください。'; return 1; }
    local phase message next status
    phase=$(cat "$LAB_STATE/phase")
    message=$(cat "$LAB_STATE/message")
    case "$phase" in
        install) _packages_installed 1.0 hello || return 1; next=configure ;;
        configure) _packages_installed 1.0 "$message" || return 1; next=upgrade ;;
        upgrade) _packages_installed 2.0 "$message" || return 1; next=fault-ready ;;
        fault-ready) echo '次は packages break で設定の故障を投入します。まだ修了ではありません。'; return 1 ;;
        repair)
            [[ -s $LAB_STATE/failure.stderr ]] || return 1
            _packages_installed 2.0 "$message" || return 1; next=remove ;;
        remove)
            status=$(_packages_status)
            [[ $status == 'deinstall ok config-files|2.0' && ! -e /usr/bin/dojo-example && -f /etc/dojo-example.conf ]] || { echo 'apt removeで本体を削除し、設定が残ることを確認します。'; return 1; }
            [[ $(cat /etc/dojo-example.conf) == "message=$message" ]] || return 1
            next=purge ;;
        purge|complete)
            status=$(_packages_status)
            [[ -z $status || $status == 'unknown ok not-installed|'* ]] || { echo 'apt purgeでパッケージと設定を完全削除します。'; return 1; }
            [[ ! -e /usr/bin/dojo-example && ! -e /etc/dojo-example.conf ]] || return 1
            next=complete ;;
        *) echo '実習状態が不正です。'; return 1 ;;
    esac
    printf '%s\n' "$next" > "$LAB_STATE/phase"
    printf '%s -> %s\n' "$phase" "$next" >> "$LAB_STATE/milestones"
    if [[ $next == complete ]]; then
        echo '修了: 本物のdebの導入・設定・更新・故障復旧・remove・purgeを順に検証しました。'
    else
        printf '段階確認OK（未修了）。次の段階: %s。TASK.txtを読み進めてください。\n' "$next"
    fi
}

lab_reset() {
    _packages_paths || return 1
    [[ -f $LAB_STATE/phase && -f $LAB_STATE/build/1.0/DEBIAN/control ]] || { echo 'この実習が作ったパッケージの証拠がありません。自動削除しません。'; return 1; }
    if [[ -n $(_packages_status) ]]; then dpkg --purge dojo-example; fi
    # Delete only our enumerated files; retain no completion claim after reset.
    rm -rf -- "$LAB_STATE/build" "$LAB_STATE/debs"
    rm -f -- "$LAB_STATE/phase" "$LAB_STATE/message" "$LAB_STATE/TASK.txt" "$LAB_STATE/milestones" "$LAB_STATE/failure.stdout" "$LAB_STATE/failure.stderr"
    echo '教材パッケージをpurgeし、この実習の状態を解除しました。'
}
