# title: カーネルモジュールのビルド・ロード・modprobe導入（kbuild／LPIC-2カーネル）
# roles: app
# Out-of-tree module only. No full kernel compile, no Secure Boot bypass, no signing-key handling.

_kb_paths() {
    [[ ${LAB_ID:-} == kbuild && ${LAB_VM_ROLE:-} == app && ${LAB_STATE:-} == /var/lib/linuxdojo-vm-lab/state/kbuild ]] || { echo 'kbuild: unexpected lab context' >&2; return 1; }
    KB_WORK=/home/ubuntu/dojo-kbuild
    KB_MOD=dojo_hello
    KB_REL=$(uname -r)
    KB_EXTRA=/lib/modules/$KB_REL/extra
    [[ ! -L $KB_WORK ]] || return 1
}

_kb_prereq() {
    local missing=()
    [[ -d /lib/modules/$KB_REL/build ]] || missing+=("linux-headers-$KB_REL")
    command -v gcc >/dev/null || missing+=(gcc)
    command -v make >/dev/null || missing+=(make)
    command -v depmod >/dev/null || missing+=(kmod)
    if ((${#missing[@]})); then
        echo "不足: ${missing[*]}"
        echo "sudo apt install ${missing[*]}   を実行してから再度setupしてください（何も作成していません）。"
        return 1
    fi
}

_kb_lockdown() {
    # Never bypass: report and stop.
    if grep -qE '\[(integrity|confidentiality)\]' /sys/kernel/security/lockdown 2>/dev/null \
        || [[ $(cat /sys/module/module/parameters/sig_enforce 2>/dev/null) == Y ]]; then
        echo 'このカーネルは未署名モジュールを拒否します（Secure Boot/lockdown/sig_enforce）。署名の回避はこの実習では行いません。署名無効のVMイメージで実施してください。'
        return 1
    fi
}

_kb_rmbuild() {
    [[ -n ${KB_BUILD:-} && $KB_BUILD == /var/tmp/dojo-kbuild.* ]] && rm -rf -- "${KB_BUILD:?}"
    KB_BUILD=
}

# Copy source dir (regular files only) to a private dir, build as nobody. Sets KB_BUILD.
_kb_build() {
    local src=$1
    [[ -d $src && ! -L $src ]] || { echo "$src がありません。"; return 1; }
    [[ -z $(find "$src" -type l -print -quit) ]] || { echo 'シンボリックリンクは使えません。'; return 1; }
    [[ $(find "$src" -type f | wc -l) -le 50 ]] || return 1
    KB_BUILD=$(mktemp -d /var/tmp/dojo-kbuild.XXXXXX) || return 1
    cp -r --no-dereference -T "$src" "$KB_BUILD" || return 1
    chown -R nobody:nogroup "$KB_BUILD"
    chmod 0700 "$KB_BUILD"
    if ! runuser -u nobody -- env PATH=/usr/bin:/bin:/usr/sbin:/sbin bash -c 'cd "$1" && exec timeout 300 make' _ "$KB_BUILD" > "$LAB_STATE/build.log" 2>&1; then
        echo 'makeが失敗しました。出力（末尾）:'
        tail -n 15 "$LAB_STATE/build.log"
        return 1
    fi
    [[ -f $KB_BUILD/$KB_MOD.ko ]] || { echo "$KB_MOD.ko が生成されていません。"; return 1; }
}

_kb_loaded() { lsmod | awk '{print $1}' | grep -qx "$KB_MOD"; }

_kb_rm_extra() {
    local target="${KB_EXTRA:?}/${KB_MOD:?}.ko"
    if [[ -f $target && ! -L $target ]]; then
        rm -f -- "$target"
        rmdir --ignore-fail-on-non-empty "$KB_EXTRA" 2>/dev/null || true
        depmod -a "$KB_REL"
    fi
}

_kb_cfg() { # print config value of $1 from the running kernel config
    local f line
    for f in "/boot/config-$KB_REL" "/lib/modules/$KB_REL/build/.config"; do
        [[ -r $f ]] || continue
        line=$(grep -E "^(# )?$1[= ]" "$f" | head -n 1)
        case $line in
            "$1="*) echo "${line#*=}" ;;
            "# $1 is not set") echo n ;;
            *) echo unset ;;
        esac
        return 0
    done
    return 1
}

lab_setup() {
    _kb_paths || return 1
    _kb_prereq || return 1
    getent passwd ubuntu >/dev/null || return 1
    [[ ! -e $KB_WORK ]] || { echo '作業ディレクトリが既にあります。既存データは上書きしません。'; return 1; }
    ! _kb_loaded || { echo "$KB_MOD が既にロード中です。"; return 1; }
    [[ ! -e $KB_EXTRA/$KB_MOD.ko ]] || { echo "$KB_EXTRA/$KB_MOD.ko が既にあります。"; return 1; }
    local token
    token=dojo-$(tr -d - < /proc/sys/kernel/random/uuid | head -c 10)
    install -d -o ubuntu -g ubuntu -m 0755 "$KB_WORK" "$KB_WORK/hello"
    : > "$KB_WORK/.dojo-kbuild-lab"
    printf '%s\n' "$token" > "$LAB_STATE/token"
    touch "$LAB_STATE/created"
    cat > "$LAB_STATE/TASKS.txt" <<'TASKS'
カーネルモジュール課題（app VMのubuntuで操作。作業場所は ~/dojo-kbuild）
ラボトークン: @TOKEN@
モジュール名は dojo_hello 固定。

A. 自作モジュール（~/dojo-kbuild/hello に dojo_hello.c と Makefile を書く）
 1. uname -r と /boot/config-$(uname -r) を見て、CONFIG_MODULES と CONFIG_MODULE_SIG の値を調べる。
    ~/dojo-kbuild/facts.txt に次の形式で記録する（実際の値）:
      release=<uname -r>
      CONFIG_MODULES=<値>
      CONFIG_MODULE_SIG=<値。# ... is not set なら n、行が無ければ unset>
 2. dojo_hello.c: init で printk(pr_info)し、トークンと count パラメータを同一行に出す
    （例の形: "dojo_hello: <トークン> count=%d"）。module_param(count,int,0444)、
    MODULE_LICENSE("GPL")、MODULE_DESCRIPTION を付ける。exit でも何か出力する。
 3. Makefile は kbuild 形式（obj-m）。ビルド本体は
      make -C /lib/modules/$(uname -r)/build M=$PWD modules
    レシピ行の先頭はTab。
 4. make 後、modinfo ./dojo_hello.ko で license/parm/vermagic を確認。
 5. sudo insmod dojo_hello.ko count=7 → lsmod | grep dojo、sudo dmesg | tail（journalctl -k も）、
    cat /sys/module/dojo_hello/parameters/count → sudo rmmod dojo_hello。
 6. 導入: sudo install -D -m 0644 dojo_hello.ko /lib/modules/$(uname -r)/extra/dojo_hello.ko
    sudo depmod -a → modprobe -n -v dojo_hello → sudo modprobe dojo_hello count=3 → sudo modprobe -r dojo_hello。
    確認後は /lib/modules/.../extra/dojo_hello.ko を削除し depmod -a（resetも削除します）。
B. 障害修理: A が動いたら  sudo dojo-vm-lab kbuild break
    ~/dojo-kbuild/broken にコンパイルエラー・Makefileの誤り・不適切なライセンスを含む一式が出る。
    make のエラーを読んで全て直す。GPL以外の宣言やタイント回避の細工は不可。
C. 知識確認（実際のカーネルビルドは行いません。キーワード判定の確認問題です）
    ~/dojo-kbuild/answers.txt に、フルカーネルビルドの手順を、設定（defconfig/menuconfig系）、
    並列ビルド(-j)、modules_install、install、initramfs、ブートローダ更新（update-grub等）の
    順で自分の言葉で書く。
D. sudo dojo-vm-lab kbuild check （ビルド→ロード→dmesg確認→modprobe→アンロード→lsmod確認）
E. sudo dojo-vm-lab kbuild reset
Secure Boot/署名必須のカーネルでは insmod が拒否されます。回避は行わず、署名なしVMで実施してください。
TASKS
    sed -i "s/@TOKEN@/$token/" "$LAB_STATE/TASKS.txt"
    install -o ubuntu -g ubuntu -m 0644 "$LAB_STATE/TASKS.txt" "$KB_WORK/TASKS.txt"
    _kb_lockdown || echo '(警告) 上記のためロード課題は実行できない可能性があります。'
    cat "$LAB_STATE/TASKS.txt"
}

lab_break() {
    _kb_paths || return 1
    [[ -f $LAB_STATE/created && -f $KB_WORK/.dojo-kbuild-lab ]] || { echo '先にsetupしてください。'; return 1; }
    [[ -f $KB_WORK/facts.txt && -f $KB_WORK/answers.txt ]] || { echo 'facts.txtとanswers.txtを先に作成してください。'; return 1; }
    [[ ! -e $KB_WORK/broken ]] || { echo 'brokenは既にあります。'; return 1; }
    if ! _kb_build "$KB_WORK/hello"; then
        echo '自作のhelloがビルドできる状態でbreakします。'; _kb_rmbuild; return 1
    fi
    _kb_rmbuild
    local token
    token=$(cat "$LAB_STATE/token")
    install -d -o ubuntu -g ubuntu -m 0755 "$KB_WORK/broken"
    cat > "$KB_WORK/broken/dojo_hello.c" <<SRC
#include <linux/module.h>
#include <linux/init.h>
#include <linux/moduleparam.h>

static int count = 1;
module_param(count, int, 0444);
MODULE_PARM_DESC(count, "lab counter");

static int __init dojo_hello_init(void)
{
	pr_info("dojo_hello: $token count=%d\n", cnt)
	return 0;
}

static void __exit dojo_hello_exit(void)
{
	pr_info("dojo_hello: bye\n");
}

module_init(dojo_hello_init);
module_exit(dojo_hello_exit);
MODULE_LICENSE("Proprietary");
MODULE_DESCRIPTION("LinuxDOJO kbuild lab");
SRC
    cat > "$KB_WORK/broken/Makefile" <<'MK'
obj-m := dojo_hello.o
KDIR := /lib/modules/$(shell uname -r)/buld

all:
    $(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
    $(MAKE) -C $(KDIR) M=$(PWD) clean
MK
    chown ubuntu:ubuntu "$KB_WORK/broken/dojo_hello.c" "$KB_WORK/broken/Makefile"
    touch "$LAB_STATE/fault"
    echo "~/dojo-kbuild/broken で make が失敗します。エラーを順に読んで直し、sudo dojo-vm-lab kbuild check で確認します。"
}

lab_check() {
    _kb_paths || return 1
    [[ -f $LAB_STATE/fault && -f $KB_WORK/broken/Makefile ]] || { echo '先にbreakで障害を作り、修理してください。'; return 1; }
    local token nonce nonce2 f c k tainted0 tainted1
    token=$(cat "$LAB_STATE/token")
    # --- facts (real values from this kernel) ---
    [[ -f $KB_WORK/facts.txt && ! -L $KB_WORK/facts.txt ]] || { echo 'facts.txt がありません。'; return 1; }
    [[ $(sed -n 's/^release=//p' "$KB_WORK/facts.txt" | head -n 1) == "$KB_REL" ]] || { echo 'facts.txt: release が uname -r と一致しません。'; return 1; }
    for k in CONFIG_MODULES CONFIG_MODULE_SIG; do
        c=$(_kb_cfg "$k") || { echo 'カーネル設定ファイルを読めません。'; return 1; }
        [[ $(sed -n "s/^$k=//p" "$KB_WORK/facts.txt" | head -n 1) == "$c" ]] || { echo "facts.txt: $k の値が実際の設定と違います。"; return 1; }
    done
    # --- knowledge check (keywords only; not a live kernel build) ---
    [[ -f $KB_WORK/answers.txt && ! -L $KB_WORK/answers.txt ]] || { echo 'answers.txt がありません。'; return 1; }
    for f in 'defconfig|menuconfig|oldconfig|olddefconfig' '(^|[[:space:]])-j' 'modules_install' 'make[[:space:]]+install' 'initramfs|initrd|mkinitcpio|dracut' 'update-grub|grub-mkconfig|grub2-mkconfig'; do
        grep -qiE -- "$f" "$KB_WORK/answers.txt" || { echo "answers.txt: 手順の要素が不足: $f"; return 1; }
    done
    # --- static sanity (the real judgement is the build and load below) ---
    if grep -qE 'MODULE_INFO|add_taint|intree|MODULE_LICENSE\("(Proprietary|proprietary)' "$KB_WORK/broken/dojo_hello.c"; then
        echo 'ライセンス偽装・タイント回避の記述は不可です。MODULE_LICENSE("GPL")を使います。'; return 1
    fi
    ! _kb_loaded || { echo "$KB_MOD が既にロード中です。先に rmmod してください。"; return 1; }
    _kb_lockdown || return 1
    # --- build in a private copy ---
    _kb_build "$KB_WORK/broken" || { _kb_rmbuild; return 1; }
    k=$KB_BUILD/$KB_MOD.ko
    local ok=1
    modinfo -F license "$k" | grep -qxE 'GPL|GPL v2|Dual BSD/GPL|Dual MIT/GPL|Dual MPL/GPL' || { echo 'MODULE_LICENSE がGPL系ではありません。'; ok=0; }
    if [[ $ok == 1 && -z $(modinfo -F description "$k") ]]; then echo 'MODULE_DESCRIPTION がありません。'; ok=0; fi
    if [[ $ok == 1 ]]; then modinfo -F parm "$k" | grep -q '^count:' || { echo 'module_param count がありません。'; ok=0; }; fi
    if [[ $ok == 1 && $(modinfo -F vermagic "$k" | awk '{print $1}') != "$KB_REL" ]]; then echo 'vermagic が実行中カーネルと一致しません（KDIRを確認）。'; ok=0; fi
    if [[ $ok == 1 ]]; then
        tainted0=$(cat /proc/sys/kernel/tainted)
        nonce=$((RANDOM % 9000 + 1000))
        if ! insmod "$k" count=$nonce; then
            echo 'insmod に失敗しました。dmesg | tail を確認:'; dmesg | tail -n 5; ok=0
        else
            _kb_loaded || { echo 'lsmod に現れません。'; ok=0; }
            dmesg | grep -F -- "$token" | grep -qE "count=$nonce([^0-9]|$)" || { echo "dmesg に「$token」と count=<渡した値> を含む行がありません。"; ok=0; }
            [[ $(cat "/sys/module/$KB_MOD/parameters/count" 2>/dev/null) == "$nonce" ]] || { echo '/sys/module/.../parameters/count が渡した値ではありません（perm 0444?）。'; ok=0; }
            tainted1=$(cat /proc/sys/kernel/tainted)
            (( (tainted1 & 3) == (tainted0 & 3) )) || { echo 'プロプライエタリ／強制ロードのタイントが付きました。'; ok=0; }
            rmmod "$KB_MOD" || ok=0
            ! _kb_loaded || { echo 'rmmod 後も lsmod に残っています。'; ok=0; }
        fi
    fi
    if [[ $ok == 1 ]]; then
        # modprobe path; fully reversed below
        nonce2=$((RANDOM % 9000 + 1000))
        install -D -m 0644 "$k" "$KB_EXTRA/$KB_MOD.ko" && depmod -a "$KB_REL" \
            && modprobe "$KB_MOD" count=$nonce2 \
            && [[ $(cat "/sys/module/$KB_MOD/parameters/count" 2>/dev/null) == "$nonce2" ]] \
            || { echo 'depmod/modprobe 経由のロードに失敗しました。'; ok=0; }
        if _kb_loaded; then modprobe -r "$KB_MOD"; fi
        _kb_rm_extra
        ! _kb_loaded || { echo 'modprobe -r 後も残っています。'; ok=0; }
    fi
    _kb_rmbuild
    [[ $ok == 1 ]] || return 1
    echo 'PASS: 実ビルド・insmod・dmesgトークン・パラメータ・rmmod・depmod/modprobe・lsmodクリーンを確認しました。answers.txtはキーワード判定の知識確認（実カーネルビルドではありません）。'
}

lab_reset() {
    _kb_paths || return 1
    [[ -f $LAB_STATE/created ]] || { echo 'この課題が作成したものではありません。'; return 1; }
    if _kb_loaded; then rmmod "$KB_MOD" || return 1; fi
    _kb_rm_extra
    if [[ -f $KB_WORK/.dojo-kbuild-lab ]]; then rm -rf -- "${KB_WORK:?}"; fi
    rm -rf -- /var/tmp/dojo-kbuild.??????
    rm -f -- "${LAB_STATE:?}/created" "${LAB_STATE:?}/fault" "${LAB_STATE:?}/token" "${LAB_STATE:?}/TASKS.txt" "${LAB_STATE:?}/build.log"
    echo 'kbuild実習のモジュール・作業ディレクトリを削除しました。'
}
