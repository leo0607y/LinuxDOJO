# Linuxを常用するための実践コース

目標は、日常のファイル操作、調査、開発環境、リモート作業、小規模なサービス運用を、説明できる根拠と復旧手段を持って行えることです。159個の主要コマンドを27の到達目標にまとめ、既存501問、本物のツールを動かす実習、専用VM実習をつなぎます。コマンド名を暗記した数では修了にしません。

再監査で見つかった不足（ユーザー/sudo、永続ネットワーク、ファイアウォール、別VMへの復元、署名付きrepo更新、logrotate）には実習を追加しました。VMの5件は静的検証のみで実VM未実施です。さらに見つかった未対応の領域を含め、[coverage.md](coverage.md#再監査で見つかった不足と対応状況)にまとめています。コアの全到達目標を自動実習だけで完結できる状態ではありません。

対象の中心はUbuntu/Debian系のCLI環境です。DNF系ではパッケージ名・サービス名・設定配置の違いを確認します。GUI・GPU・無線・プリンター、全ディストリビューション、各クラウドの運用まで一律に習得できるという意味ではありません。対応の詳細と未検証部分は[網羅性の監査表](coverage.md)にあります。

## 最短の進め方

1. **端末に慣れる**：初めてなら「はじめて→基礎」、経験者はStage 1〜4を手本なしで解きます。ファイル・権限・パイプ・検索を優先します。
2. **毎日の道具を使う**：下の「日常操作」の各項目と本物のツールの実習へ進みます。特にVim/nano、Git、SSH、tmux、curl、jq、rsyncは、インストールしただけで終わらせません。
3. **自分の作業を自動化する**：Stage 6、30、32〜34の関連課題を使い、入力を変えても動くスクリプト・テスト・バックアップを作ります。
4. **VMで管理操作を経験する**：パッケージ、ユーザー、systemd、Nginx、DNS、ストレージは専用VMで実際に変更します。記録読解の正解だけで実機修了にしません。
5. **下の総合課題を手本なしで再現する**：別の新しい作業フォルダ・VMへ構築し直し、故障を直し、データを戻せれば日常運用の到達確認になります。

全501問を順番に解く必要はありません。まず次の必修経路を1周し、苦手な箇所だけ対応表から既存課題を追加します。

| 経路 | 必修の実習・確認 |
|---|---|
| 日常の作業 | `shell`→`find`→`vim`→`rg`→`jq`→`archive`→`rsync`→`git`→`curl`→`ssh`→`tmux`。Vim/nanoとtmuxの対話操作も行う |
| 開発とデータ | `python`→`python-packages`→`build`→`sqlite`→`tls`。仮想環境・依存・DBを別の場所へ再現 |
| OSとサービスの運用 | 専用VMの`packages`→`permissions`→`software`→`ssh`→`network`→`performance`→`storage`→`boot`→`webstack`。各checkと必要な再起動まで実施 |
| コンテナと総合確認 | 実Dockerの`docker`、`incident`、`release`を実行し、最後に下の手本なし総合課題を新規環境で行う |

`fzf`は追加の便利機能です。使う道具を増やすことより、上の作業を根拠付きで再現できることを優先します。

導入・更新・削除のコマンドは、意味と対象を確認して自分の環境または専用VMで実行します。教材の通常課題内でホストのOS設定を変える必要はありません。本物のbashはOSから隔離する機能ではないため、課題が指定するフォルダを使います。

## 本物のツールの実習を開始する

ゲームのメニューにある「[9] Linux常用コース（目的検索・本物のツール実習）」から選ぶか、リポジトリのルートで次を実行します。

```bash
python3 -m engine.toolbox list
python3 -m engine.toolbox list SSH
python3 -m engine.toolbox doctor
python3 -m engine.toolbox start shell
```

`doctor` は必要なコマンドがあるか確認します。未導入ならパッケージを案内し、実習を合格扱いにしません。導入は前述のパッケージ管理手順を使います。`start` で開く本物のbashでは `task` が課題、`check` が結果確認、`answer` が手本、`cleanup` が実習専用のDocker資源などの解除、`exit` が終了です。作業は `workspace/toolbox/実習ID` に保存され、再開できます。既存501問のスコアとは別に扱います。

新規フォルダを指定して練習したい場合は、次のようにします。既存の場所は上書きしません。

```bash
python3 -m engine.toolbox setup git --directory ./workspace/git-first
# 表示された作業フォルダへ移動し、課題を解く
python3 -m engine.toolbox check --directory ./workspace/git-first
python3 -m engine.toolbox solution git --directory ./workspace/git-first
python3 -m engine.toolbox audit
```

手本を見て成功させたあと、別フォルダで入力値を変えてもう一度解きます。成果物の検査は、対話キー操作や概念の理解そのものを認定する仕組みではありません。

| 順番 | 実習ID | 実際に動かす内容 |
|---|---|---|
| 1 | `shell`、`find` | パイプ・失敗・標準エラー、空白や改行入りのファイル名 |
| 2 | `vim`、`rg`、`jq` | 設定編集、ソース検索、JSONの絞り込み・整形 |
| 3 | `archive`、`rsync` | 内容・権限を保った梱包、同期、復元 |
| 4 | `git` | ローカルrepoの分岐・統合・履歴からの復旧 |
| 5 | `curl`、`tls`、`ssh` | localhost HTTP、証明書検証、鍵とSSH設定のオフライン検証 |
| 6 | `tmux` | 専用ソケットでペインを分割して出力を取得 |
| 7 | `python`、`python-packages`、`build`、`sqlite` | 仮想環境、pipの導入/更新/版固定、gcc/Make、DB退避/復元 |
| 8 | `incident`、`release` | 故障の根拠と復旧、秘密を除いた配布・検証・配備 |
| 9 | `docker` | 実Dockerのbuild・故障ログ・非root実行・volume保持・専用資源の撤去 |
| 任意 | `fzf` | 候補からの絞り込み。対話選択も別に試す |

SSH実習は鍵と最終設定、`python` 実習はpipなしの環境分離、`python-packages` は本物のpipによるオフライン導入・更新です。Vimとfzfの自動検査は非対話操作です。SSH実接続・各ツールの対話操作は各節にある追加確認まで行います。Dockerは本物のdaemonが必要で、最初のベースイメージ取得にはネット接続が必要です。

## VMで導入・運用・撤去まで実行する

[専用VMの作り方](../labs/vm/README.md)に従って新しいVMを作ります。ホストへゲストスクリプトを直接コピーして実行しません。

```bash
python3 -m engine.vm_labs list
python3 -m engine.vm_labs export --output ./vm-lab-bundle
```

VM内の `sudo dojo-vm-lab list` で利用できるモジュールを確認します。1課題ずつ `setup`、`check`、`break`、修正、`check` の順に進めます。
設定・データ・サービスは課題専用のものに限定します。管理操作は使い捨てVMで実行して初めて実機の経験になります。教材をエクスポートしただけでは修了しません。

| モジュール | 内容 | 参照 |
|---|---|---|
| `packages` | 実debの導入・設定変更・版更新・故障修復・removeとpurge | [ソフト導入・運用実習](../labs/vm/SOFTWARE.md) |
| `software` | 実systemdのservice/timer・ログ・故障復旧・再起動・撤去 | [ソフト導入・運用実習](../labs/vm/SOFTWARE.md) |
| `ssh` | VM内の専用sshdへの鍵認証・ホスト鍵照合・scp転送・権限故障の復旧・rsync取得 | `sudo dojo-vm-lab ssh setup` の後、ubuntuユーザーで `~/dojo-ssh-client/TASK.txt` を読む |
| `permissions` | ACLの実効権限と既定ACL | [VM手順](../labs/vm/README.md) |
| `network` | 2台でのDNSとHTTPの比較 | [VM手順](../labs/vm/README.md) |
| `performance` | 実測とサービス設定の故障調査 | [VM手順](../labs/vm/README.md) |
| `storage` | 専用ext4のinode枯渇と再起動後のマウント | [VM手順](../labs/vm/README.md) |
| `boot` | 専用systemdサービスの故障と復旧 | [VM手順](../labs/vm/README.md) |
| `webstack` | Nginx・TLS・SQLite・502の復旧 | [VM手順](../labs/vm/README.md) |
| `users` | ユーザー・グループ・sudoの作成と事故復旧（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `netconfig` | 固定IP・静的経路・DNSクライアント・IPv6（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `firewall` | nftablesの適用と接続を保った復旧（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `restore` | 別VMへのサービス全体の復元（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `osupdate` | 署名付きaptリポジトリと更新復旧（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `sshd` | 専用sshdの堅牢化とProxyJump（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `mounts` | fstab誤記・swap・LVM拡張（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `journald` | journaldの永続化と保存量（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `sysctl` | sysctlの永続化とmodprobe blacklist（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `limits` | MemoryMax・LimitNOFILEとOOM（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `timesync` | タイムゾーン・NTP・ロケール（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `guard` | fail2banとauditd（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `dnsserver` | BINDの権威ゾーン（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `mailserver` | Postfixの専用インスタンス（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `fileshare` | NFS（2台）（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `apache` | Apacheの仮想ホストと認証（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `netlink` | bridge・VLAN・bond・ポリシールート（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `pam` | PAMスタック（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `podman` | rootless PodmanとQuadlet（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `ldap` | 専用slapdとACL（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `samba` | 専用smbd（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `libvirt` | libvirtのテスト用ドライバー（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `tuned` | tunedのカスタムプロファイル（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `kbuild` | カーネルモジュールのビルド（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `grubrescue` | ループバック上のGRUB導入と修復（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `selinux` | SELinux（RHEL系VM専用）（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `dnf` | dnf/rpm（RHEL系VM専用）（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |
| `firewalld` | firewalld（RHEL系VM専用）（静的検証のみ、実VM未実施） | [初回確認](../labs/vm/FIRST_RUN.md) |

各 `check` は段階を区別するため、最後の状態だけ作って途中の経験を省略しません。
`ssh` は実SSH接続ですが、対象はVM内のloopbackです。別VMとの疎通は `network` で確認します。
上の順番は、`packages`、`software`、`ssh` の後に `permissions`、`network`、`performance`、`storage`、`boot`、`webstack` を進める想定です。

## ソフト導入後に共通して確認すること

各ソフトについて **導入→起動・基本操作→設定→結果確認→故障切り分け→更新・撤去** を1周します。CLIツールは常駐サービスとは違い、`systemctl start` は不要です。

| 確認 | 自分で残す証拠 |
|---|---|
| 何を入れたか | OS、パッケージ名、導入元、版、`command -v`の実体 |
| 何に使うか | 自分の入力に対して実行し、出力と終了コードを確認 |
| 設定はどこか | 作業フォルダ、ユーザー設定、システム設定を区別して控えを取る |
| 壊れたらどう調べるか | stderr、`--help`/man、必要ならログ・待受・権限を確認 |
| どう戻すか | 設定・データを別に退避し、更新後の確認と削除後の残存物を確認 |

<a id="packages"></a>
## パッケージ管理：導入・更新・撤去

まず `cat /etc/os-release` でOSを確認します。Ubuntu/Debianでは次のように、一覧更新と本体の更新を分けます。`PACKAGE` は実際に調べたパッケージ名に置き換えます。

```bash
apt search PACKAGE
apt show PACKAGE
apt-cache policy PACKAGE
sudo apt update
sudo apt install PACKAGE
command -v COMMAND
COMMAND --version
# 導入済みの版とファイルを調べる
dpkg-query -W PACKAGE
dpkg -L PACKAGE
# 更新候補と変更対象を確認してから更新する
apt list --upgradable
apt-get -s install --only-upgrade PACKAGE
sudo apt install --only-upgrade PACKAGE
# データと設定の控えを作り、まず削除予定を確認する
apt-get -s remove PACKAGE
sudo apt remove PACKAGE
```

`COMMAND` もコマンド名に置き換えます。すべてのツールが `--version` に対応するわけではなく、SSHは `ssh -V`、OpenSSLは `openssl version` です。`remove` は設定の一部を残します。`purge` はパッケージ管理下の設定も消す操作なので、必要な設定を退避した後に使います。どちらもホームやデータベースの全データを消すとは限りません。`autoremove` も候補を読んでから実行します。公式の[Ubuntuパッケージ管理](https://ubuntu.com/server/docs/how-to/software/package-management/)を参照してください。

DNF系では、`dnf search PACKAGE`、`dnf info PACKAGE`、`dnf provides '*/COMMAND'`、`sudo dnf install PACKAGE`、`dnf list --installed PACKAGE`、`rpm -ql PACKAGE`、`sudo dnf upgrade PACKAGE`、`sudo dnf remove PACKAGE` を使います。対象と依存関係を確認してからトランザクションを進めます。`dnf check-update` の終了コード100は更新候補ありを表し、通常のエラーと区別します。DNFの世代差は実機のmanと[公式コマンドリファレンス](https://dnf.readthedocs.io/en/latest/command_ref.html)で確認します。

Ubuntu/Debianの代表的なパッケージ対応は次のとおりです。全部を一括導入する必要はなく、実習の依存関係表示に従います。

| 道具 | パッケージ名 | 導入後の入口 |
|---|---|---|
| Git | `git` | `git --version`、`git status` |
| Vim / nano | `vim` / `nano` | `vimtutor`、`nano sample.txt` |
| tmux | `tmux` | `tmux -V`、`tmux new -s work` |
| JSON / ソース検索 | `jq` / `ripgrep` | `jq --version`、`rg --version` |
| HTTP / 同期 | `curl` / `rsync` | `curl --version`、`rsync --version` |
| SSHクライアント / サーバー | `openssh-client` / `openssh-server` | `ssh -V`、`sshd -t` |
| SQLite | `sqlite3` | `sqlite3 --version`、`sqlite3 work.db` |
| Python仮想環境 | `python3`、`python3-venv`、必要なら`python3-pip` | `python3 -m venv .venv` |
| C / Make / デバッグ | `build-essential`、`gdb`、`pkg-config` | `gcc --version`、`make --version` |
| シェルの検査 | `shellcheck` | `shellcheck job.sh` |
| Web | `nginx` | `nginx -v`、`sudo nginx -t` |
| DNS / IP調査 | `dnsutils` / `iproute2` | `dig`、`ip`、`ss` |
| 実行追跡 / 統計 | `strace` / `sysstat` | `strace -o trace.txt COMMAND`、`iostat` |
| ACL | `acl` | `getfacl FILE`、`setfacl` |
| 圧縮 | `zip`、`unzip`、`xz-utils` | `unzip -l archive.zip` |

`command not found` は「未導入」とは限りません。`type COMMAND`、`command -v COMMAND`、`printf '%s\n' "$PATH"` でPATH・別名・実体を確認します。証明書、DNS、プロキシ、空き容量、依存関係、署名を調べ、検証を無効にして押し通さないようにします。ロック競合では動いている更新処理を確認し、ロックファイルだけを削除しません。Stage 12-5、17-8、29-11〜14と専用VMのパッケージ実習へ進みます。

<a id="shell"></a>
## 端末・ヘルプ・PATH・終了コード

`pwd`→`ls -la`→`cd` で現在地を説明します。`man ls`、`ls --help`、`help cd`、`type cd` で外部コマンドと組み込みを区別します。`q` はless/manの終了、`Ctrl+C` は前景処理の中断、`Ctrl+D` は入力の終端です。

`printf '%s\n' "$HOME"` と `printf '%s\n' '$HOME'` の差、`"$name"` が空白を壊さない理由、`>` と `>>`、`2>`、`2>&1`、パイプ、`&&` と `||` を、入力ファイルを変えて試します。`command; printf 'rc=%s\n' "$?"` で失敗を確認します。設定を変える前に `cp ~/.bashrc ~/.bashrc.before-dojo` などで控えを作り、別の端末を開いてもPATHが正しいか確かめます。

到達確認：空白入りパスを安全に渡し、標準出力と標準エラーを分け、失敗した処理の後を止められること。Stage 3-4、24-16（profile/bashrc・export・ロケール継承の実bash検査）、25-19〜21を使います。文字コードの変換は17-7の実iconv課題も使います。

<a id="files"></a>
## ファイル・リンク・ディレクトリ

`mkdir -p project/{src,data,backup}` で作業場所を用意し、`cp -a`、`mv`、`ln -s`、`readlink -f`、`stat` でファイルとリンクの違いを確認します。隠しファイルは `ls -la`、種類は `file` で調べます。

削除前に `pwd` と対象の一覧を確認し、`rm -- 'file with spaces'` のように引数を明確にします。リンク先とリンク自体、ファイルのコピーとディレクトリ全体のコピーを実物で比べます。実習対象外のファイルをまとめて削除する必要はありません。

到達確認：指定された構成を再現し、内容・権限・リンク先を確認し、誤変更したファイルだけをバックアップから戻すこと。Stage 1、3-3、EX-2を使います。

<a id="text"></a>
## テキスト・ログ・CSV

`less` の `/語` と `n`、`head`、`tail -n`、`tail -f`、`grep -n -C 2` で巨大ログの必要な部分を読みます。`sort | uniq -c | sort -nr` で件数を集計し、`awk -F,` で単純なCSVの列を扱います。引用符内にカンマや改行を含むCSVは単純な区切り処理では壊れるので、Pythonの `csv` などを使います。

`sed -E` の置換結果はまず標準出力へ出し、`diff -u original edited` で確認してから置き換えます。`iconv` の入力・出力文字コードを明示します。文字列、数値順、ロケールの違いで結果が変わることを説明します。

到達確認：手作業の転記なしでエラー件数・上位IP・必要な列を抽出し、入力ログを保全すること。Stage 2、24-4〜6を使います。

<a id="search"></a>
## find・ripgrep・jq

ファイル名は `find . -type f -name '*.log'`、内容は `rg -n -g '*.py' 'pattern' .` で探します。ファイル名に空白や改行があっても処理できる `find ... -print0 | xargs -0 ...` を実物で試します。`rg` は無視ファイルや隠しファイルを通常省くことも確認します。

JSONでは `jq '.items[] | select(.enabled == true) | .name' input.json`、文字列出力なら `-r`、外部文字列は `--arg name "$value"` を使います。該当なしと構文エラーを区別し、空ファイル・空配列でも検証します。jqのフィルター構文は[公式マニュアル](https://jqlang.org/manual/)を参照します。

到達確認：検索対象を絞り、必要な構造だけを出力し、同じ処理を別のデータでも再利用すること。Stage 2-6、32-1〜3、32-9を使います。

<a id="editor"></a>
## Vim・nano：終了できるところから復旧まで

Vimは `vim sample.txt`→`i`→入力→`Esc`→`:wq`。保存せず終了する場合は `:q!`、取り消しは `u`、やり直しは `Ctrl+R`、検索は `/語`、置換は `:%s/old/new/gc` です。`vimtutor` を開き、`gg`、`G`、`w`、`dd`、`yy`、`p` を実際に押します。

nanoは `nano sample.txt`→編集→`Ctrl+O`→Enter→`Ctrl+X`。画面下の `^` がCtrlキーを表すことを確認します。`EDITOR`/`VISUAL` を好みのエディターへ設定し、Gitなどから起動できることも確認します。

到達確認：誤編集を取り消し、別名保存し、差分を確認できること。スワップ警告は別の編集プロセスが動いていないか調べ、必要なら `vim -r` で復旧します。Stage 6-6、31-1〜18を使います。バッチ処理の成功だけでは対話キー操作の修了にはしません。

<a id="archive"></a>
## 圧縮・展開・検証

```bash
tar -czf backup.tar.gz -C project .
tar -tzf backup.tar.gz
mkdir restored
tar -xzf backup.tar.gz -C restored
sha256sum backup.tar.gz > backup.tar.gz.sha256
sha256sum -c backup.tar.gz.sha256
```

展開先は新しい専用フォルダにします。`tar -t`、`unzip -l` で中身を確認し、バックアップから戻したファイルの内容・モード・隠しファイルを比較します。`gzip` は既定で元ファイルを置き換えるため、必要なら `gzip -c` を使います。

到達確認：壊したデータを別の場所へ復元し、元データと照合できること。チェックサムは信頼する経路で得た期待値と比較します。Stage 4-1〜2、9-6〜7、25-2を使います。

<a id="backup"></a>
## rsync：dry-runから復元まで

`rsync -av --dry-run --exclude='.cache/' source/ backup/` で変更予定を確認し、対象が正しければ `--dry-run` を外して実行します。末尾の `/` は「中身を同期する」指定です。`--delete` は送信元にないファイルを受信側から削除するため、復元先を含めたdry-runで影響を確認します。

`rsync -av -e ssh source/ host:destination/` の前にSSH接続とホスト鍵を確認します。バックアップがあるだけでは不十分です。別フォルダへ戻して、`diff -r`、`cmp`、チェックサム、必要な権限を確認します。更新するのはrsyncパッケージと運用スクリプトで、削除前にバックアップの保存先・保持期間を引き継ぎます。詳しいオプションは[rsyncの公式man](https://download.samba.org/pub/rsync/rsync.1)を参照します。

到達確認：除外した秘密やキャッシュを混ぜず、元データを壊しても戻せること。Stage 6-8、17-10、23-3〜4を使います。

<a id="permissions"></a>
## 所有者・権限・ACL

`id`、`ls -ld directory`、`stat file`、`namei -l path` で、ファイルだけでなく通過するディレクトリも確認します。`chmod 640 file`、`chmod 750 directory`、`chgrp group file`、`umask 027` の効果を説明します。実ユーザーの追加・所有者変更は専用VMで行います。

`getfacl` で通常のモードにない許可を確認し、ACLのmaskで実効権限が制限されることを別ユーザーから試します。「読めるべき利用者は読める」「読めないべき利用者は読めない」の両方を確認します。

到達確認：`chmod 777` で隠さず原因を特定し、必要な主体だけへ許可すること。Stage 3-1〜2、9-2、12-7とVM `permissions` を使います。

<a id="users"></a>
## ユーザー・グループ・sudo

専用VMで `getent passwd`、`getent group`、`id USER` を確認し、実習専用のユーザー・グループを作成します。ホーム、ログインシェル、補助グループ、パスワード期限を確認します。`usermod -aG` の `-a` を省いた場合の影響を理解します。

sudoersは `visudo` で検査し、必要なコマンドと対象を限定します。SSHを制限するときは現在の管理接続を残し、別の接続で確認してから切り替えます。削除前に専用ユーザーのプロセス、ジョブ、所有ファイル、ホームの要否を確認します。

この一連のユーザー管理は現時点では手動確認です。VM `permissions` のユーザーは教材が自動作成し、利用者の課題はACL操作に限られます。

到達確認：別ユーザーとして正しい権限で作業し、不要になった専用アカウントだけを撤去できること。Stage 7-4（模擬）、16-10〜11、28-1〜6、VM `permissions` を使います。

<a id="process"></a>
## プロセス・ジョブ・性能

`ps -ef`、`pgrep -af pattern` でPIDと実体を確認します。`jobs`、`Ctrl+Z`、`bg`、`fg` を小さな練習用処理で試し、`kill -TERM PID` で通常終了を依頼します。終了しない理由を調べ、必要な場合にだけ強制終了を選びます。

`uptime`、`top`、`free -h`、`df -h`、`ss -ltnp`、`lsof` で症状を分類します。`strace -o trace.txt COMMAND` で自分の処理の設定参照先・権限・失敗した呼び出しを追います。低いfree値だけでメモリ不足と決めず、available、OOM記録、時系列を比較します。

到達確認：対象外を止めず、CPU・メモリ・I/O・待ち受けを根拠付きで区別すること。Stage 3-5〜7、12-1〜4、27-1〜10とVM `performance` を使います。

<a id="network"></a>
## IP・DNS・ポートを分けて調べる

`ip -br address`→`ip route`→`getent hosts NAME`/`dig NAME`→`ss -ltnp`→`curl` の順で、アドレス・経路・名前・待ち受け・アプリ応答を分けます。`ping` が失敗してもHTTPが通る場合があるため、ICMPだけでサービス停止とは決めません。

DNSでは問い合わせ先、A/AAAA、TTL、`/etc/hosts`、実アプリの名前解決経路の違いを確認します。ルート変更、NetworkManager、netplan、ファイアウォールは管理接続を失う可能性があるため専用VMで練習し、設定を戻す方法を先に用意します。

到達確認：名前直指定とIP直指定の結果を比較し、誤った層を変更せず復旧すること。Stage 4-5〜6、13-1〜2、13-6、17-1とVM `network` を使います。

<a id="http"></a>
## curl・wget：取得とAPI

`curl --fail --show-error --location --output result.json URL` でファイルへ保存し、`curl -I URL` でヘッダー、`curl -v URL` で通信過程を確認します。`--connect-timeout`、`--max-time`、`--retry` は対象と再試行の影響に応じて設定します。`-I` はHEADでありGETと動作が同じとは限りません。

POSTは `curl --fail -H 'Content-Type: application/json' --data @request.json URL`。秘密をコマンド履歴や共有ログへ混ぜず、HTTPステータス・本文・終了コードを分けて見ます。wgetは `wget -O file URL`、途中再開は対象の性質を確認して `-c` を使います。[curl公式man](https://curl.se/docs/manpage.html)で手元の版にあるオプションを確認します。

到達確認：ローカル実習サーバーの正常応答と404/500を区別し、失敗を成功ファイルとして保存しないこと。Stage 4-3〜4、32-5〜8を使います。

<a id="tls"></a>
## TLS・OpenSSL

`openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName` で証明書を調べます。接続検証は `openssl s_client -connect HOST:443 -servername HOST -verify_hostname HOST -verify_return_error` などで、信頼・名前・期限を分けて確認します。

自己署名の練習用CAは専用フォルダに作り、`curl --cacert ca.crt https://...` で明示的に信頼します。`curl -k` でエラーを消した状態を修了にはしません。秘密鍵は公開証明書と区別し、モードとコピー先を制限します。更新時は期限、鍵との対応、SAN、実接続まで再確認します。

到達確認：証明書の名前不一致・未信頼・期限切れを説明し、正しい信頼設定で接続できること。Stage 13-3、20-10〜12とVM `webstack` を使います。公開CA発行・更新は別途実機手順です。

<a id="ssh"></a>
## SSH・鍵・転送

`ssh-keygen -t ed25519 -f ./dojo_key` で実習鍵を作り、`ssh-keygen -lf ./dojo_key.pub` で指紋を確認します。実際の運用鍵にはパスフレーズを設定します。サーバーへ渡すのは `.pub` 側です。`~/.ssh` は700、秘密鍵は600を目安に所有者も確認します。

`~/.ssh/config` の `Host`、`HostName`、`User`、`IdentityFile`、`IdentitiesOnly yes` を設定し、`ssh -G ALIAS` で最終設定を確認します。初回のホスト鍵は管理者など別の信頼できる経路と照合します。鍵変更警告を見て無条件にknown_hostsから消しません。`ssh -vvv ALIAS` のログでDNS・TCP・ホスト鍵・認証を分けます。

VM `ssh` でまず専用loopbackサーバーへログインし、`scp`、`rsync -e ssh`、リモートコマンドを実行します。手順は `sudo dojo-vm-lab ssh setup` 後の `~/dojo-ssh-client/TASK.txt` です。加えて別VMまたは自分が管理する接続先で、ログインと転送を確認します。サーバー設定は `sudo sshd -t` で検査し、現在の接続を残して別接続から検証します。Ubuntuのサービス名は一般に`ssh`、他OSでは`sshd`の場合があるので実機で確認します。鍵の削除は新しい鍵が使えることを確認してから行います。オプションは[OpenSSH公式man](https://man.openbsd.org/ssh)を参照します。

到達確認：接続できるだけでなく、違うホスト・違う鍵を拒否し、転送先と権限を確認すること。Stage 34-1〜18とVM `ssh` での接続確認を使います。オフラインの鍵・`ssh -G`実習だけでは接続経験の代わりになりません。

<a id="tmux"></a>
## tmux：切れても作業を続ける

`tmux new -s work` で開始します。既定prefixは `Ctrl+B`、続けて `%` で左右分割、`"` で上下分割、矢印で移動、`c` でウィンドウ作成、`d` でdetachです。`tmux ls`→`tmux attach -t work` で戻ります。`exit` はそのペインのシェル終了です。

専用セッション内でログ表示と処理を並べ、detach後も処理が続くことを確認します。`~/.tmux.conf` は控えを作ってから変更し、`tmux source-file ~/.tmux.conf` で読み込みます。更新前には必要な作業を保存し、削除前には自分の専用セッションを終了します。`tmux kill-server` は他のセッションも終了させるため普段の共有サーバーに対して使いません。[公式Getting Started](https://github.com/tmux/tmux/wiki/Getting-Started)でキー操作を復習できます。

到達確認：分割・移動・copy mode・detach・attach・終了を実際の端末で行えること。Stage 34-19〜23は記録読解なので、本物のツール実習と対話操作で補います。

<a id="git"></a>
## Git：日々の変更から復旧まで

専用リポジトリで `git init`→ローカルだけに `git config user.name` / `user.email`→編集→`git diff`→`git add`→`git diff --cached`→`git commit`→`git status` を1周します。`git switch -c feature`、`git merge`、衝突解消を経験します。

作業中の変更は `git stash push -u`、履歴の調査は `git log --oneline --graph` / `git show`、共有済みの打ち消しは `git revert`、誤った移動の調査は `git reflog`。`reset --hard` や `clean -fdx` は復旧できない未コミット作業を消すので、実習では使い捨てrepoだけで差を確認します。

`.gitignore` はすでに追跡している秘密を消しません。公開前に `git status`、差分、履歴を確認します。Git本体を更新してもリポジトリは別のデータなので、削除・バックアップを分けて扱います。操作の順序は[Git公式チュートリアル](https://git-scm.com/docs/gittutorial)も参照します。

到達確認：新しいcloneで変更を再現し、衝突を解消し、誤操作から必要なcommitを戻せること。Stage 30を使います。

<a id="python"></a>
## Python：仮想環境・依存・テスト

```bash
python3 -m venv .venv
. .venv/bin/activate
python -c 'import sys; print(sys.executable); print(sys.prefix != sys.base_prefix)'
python -m pip --version
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python -m pip freeze > installed.txt
deactivate
```

依存ファイルを持つ練習プロジェクトで行います。OS管理のPythonへ `sudo pip install` せず、仮想環境内の `python -m pip` を使います。`venv` 作成失敗は `python3-venv`、使っているPython版、ensurepipの有無を確認します。`--without-pip` の実習は環境分離だけの確認で、依存導入まで済んだことにはしません。

更新は別の仮想環境で依存を入れ直してテストし、版を管理します。撤去はdeactivateして、対象が作成した `.venv` であると確認してから仮想環境だけを削除します。ソース・データ・依存宣言は残します。[Python公式venv文書](https://docs.python.org/3/library/venv.html)を参照します。

本物のpipも、ネット接続なしで練習できます。

```bash
python3 -m engine.toolbox start python-packages
```

この課題は教材が用意するローカルwheelだけを使います。作業シェルで次を行います。

```bash
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --no-index --find-links wheels -r requirements.txt
.venv/bin/python -I -c 'import dojo_demo; print(dojo_demo.value())' > v1.txt
.venv/bin/python -m pip --isolated install --no-index --find-links wheels dojo-demo==2.0
.venv/bin/python -I -c 'import dojo_demo; print(dojo_demo.value())' > v2.txt
.venv/bin/python -m pip --isolated show dojo-demo
.venv/bin/python -m pip --isolated freeze > requirements.lock
check
```

合格後は `.venv/bin/python -m pip --isolated uninstall dojo-demo` で削除し、importが失敗することを確認します。そのあと `install --no-index --find-links wheels -r requirements.lock` で同じ版を戻し、再びcheckします。ネット上の別パッケージやOSのPythonへインストールする必要はありません。pip付きvenvが作れなければ `python3-venv` の導入を確認します。

到達確認：システムPythonと仮想環境を区別し、依存を導入・利用・更新・固定・削除し、新規環境で再実行できること。Stage 33-1〜5、`python` と `python-packages` を使います。

<a id="build"></a>
## C・Make：ビルドと失敗の調査

Ubuntuでは `build-essential` を導入し、小さなCプログラムを `gcc -Wall -Wextra -g -o app main.c` で作ります。コンパイルエラーとリンクエラーを区別し、警告も確認します。`make` の依存関係を使い、ソースを更新したときだけ再ビルドされることを確認します。

Makefileではレシピ行のタブ、ターゲットと依存、`.PHONY`、`make -n`、`make clean` を実物で確認します。`gdb ./app` の `break`、`run`、`bt`、`print` で自分のプログラムを調べます。実習で `/usr` への `sudo make install` は不要です。導入先を自作プロジェクトのフォルダに限定し、生成物とソースを分けます。

到達確認：新規フォルダでビルド・テスト・cleanができ、壊した依存関係かソースを直せること。Stage 33-12〜15は記録中心なので、本物のツール実習で補います。

<a id="database"></a>
## SQLite：更新前に退避し、戻して確認

```bash
sqlite3 work.db
```

`.help`、`.tables`、`.schema` で入口を調べ、`CREATE TABLE`、`INSERT`、`SELECT ... WHERE ... ORDER BY ...`、`BEGIN`、`UPDATE`、`ROLLBACK`/`COMMIT` を練習します。出力は `.headers on`、`.mode csv`、`.once result.csv` で保存します。

書き込み中のDBは本体ファイルの単純コピーでは一貫性を失う場合があります。CLIの `.backup backup.db` で退避し、別名のDBへ戻して `PRAGMA integrity_check;`、件数、キー、重要な値を確認します。`database is locked` では開いたトランザクションと他プロセスを調べます。SQLite CLIを削除してもDBファイルは別に残ります。[SQLite公式CLI文書](https://www.sqlite.org/cli.html)を参照します。

到達確認：誤更新をrollbackし、確定後の変更もバックアップから別の場所へ復元できること。Stage 13-5、32-24と本物のツール実習を使います。

<a id="services"></a>
## systemd：起動と自動起動は別

専用VMで `systemctl status UNIT`、`systemctl cat UNIT`、`systemctl is-active UNIT`、`systemctl is-enabled UNIT` を比較します。`start/stop/restart/reload` と `enable/disable` の違いを説明します。reloadの対応はサービスによります。

専用のサービスとtimerを作り、`sudo systemctl daemon-reload`→`sudo systemctl enable --now UNIT`→ログ確認→VM再起動→稼働確認まで進めます。ベンダーのunitは直接書き換えず `systemctl edit` のdrop-inを使います。削除時は専用unitをdisableして停止し、作成したunit/drop-inだけを解除してdaemon-reloadします。[systemctl公式man](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)で各操作を確認します。

到達確認：わざと設定を壊し、失敗の根拠を読み、検査を無効にせず復旧すること。Stage 7-1〜3は模擬操作です。実機はVM `boot` とサービス実習へ進みます。

<a id="web"></a>
## Nginx：設定を検査してから反映

専用VMで導入し、`sudo nginx -t`、`sudo systemctl status nginx`、`ss -ltnp`、`curl` を確認します。演習用の設定では既存サーバーと混ぜず、専用のserver・ポート・データを使います。

静的ファイル→Pythonバックエンドへの `proxy_pass`→TLSの順で追加します。変更前に設定を退避し、構文検査後にreloadします。403は権限と公開パス、404はlocationとroot、502は上流の起動・アドレス・ポートを確認します。`journalctl`、access log、error logの役割を区別します。

更新後は設定検査と実HTTP/TLS応答を確認し、撤去前には公開設定・証明書・データ・バックアップを分離します。nginxパッケージの削除だけで公開データがすべて消えるとは限りません。具体的な設定構文は[Nginx公式入門](https://nginx.org/en/docs/beginners_guide.html)を参照します。

到達確認：上流のポート違いによる502を直し、TLS検証を保ち、再起動後にも動作すること。Stage 13-4、21-14とVM `webstack` を使います。

<a id="logging"></a>
## ログ・時刻・保存量

`journalctl -u UNIT -b --no-pager`、`--since`、`--until`、`-p warning`、`-f` で絞り、`date -Is` と `timedatectl` で時刻とタイムゾーンを確認します。ファイルログは `tail -F`、圧縮済みは `zgrep` で扱います。

`logger` で専用の識別子を付けて記録し、journalの保存が揮発か永続か確認します。logrotateでは対象、保持数、圧縮、所有者、再オープン方法を確認します。ログ肥大化をデータの無差別削除で解決せず、原因と保持方針を直します。

到達確認：時刻をそろえて複数ログを関連付け、再現した故障をログから説明できること。Stage 7-2、10-2、23-13〜14を使います。

<a id="automation"></a>
## シェル・cron・timer

入力と出力を決め、`#!/usr/bin/env bash`、引数検査、引用符、終了コード、必要な `trap` を備えた小さなスクリプトを作ります。`bash -n job.sh`、`bash -x job.sh`、導入済みなら `shellcheck job.sh` を使います。`set -e` だけで全失敗を安全に処理できると考えず、条件式・パイプ・例外処理を確認します。

`crontab -l` で現状を控え、専用ジョブに絶対パス、明示した作業ディレクトリ・環境、ログの保存先を設定します。`flock` などで重複起動を防ぎ、意図的な失敗時の通知と後始末も試します。systemd timerでは `systemctl list-timers` とjournalを確認します。

到達確認：端末から実行したときと、限られた環境で定期実行したときの両方で動くこと。Stage 6、17-11、24-8〜9、28-20を使います。定期実行は専用VMで確認します。

<a id="storage"></a>
## 容量・inode・マウント

`df -h`、`df -i`、`du -xhd1 PATH` で容量とinodeを分けます。`lsblk -f`、`blkid`、`findmnt` でデバイス・ファイルシステム・マウント先を対応付けます。削除しても空きが戻らなければ、開いたままの削除ファイルを調べます。

mount、mkfs、fstabは専用VMの指定イメージだけで行います。新規ディスクを見たらサイズ・UUID・用途・既存データを確認し、パーティション/LVM/ファイルシステムの層を区別します。fstabは構文とUUIDを検査し、再起動後のマウントと保持データを確認します。

到達確認：容量不足とinode不足を区別し、保持すべきデータを消さずに復旧すること。Stage 11、15、26とVM `storage` を使います。物理ディスク・LVM・RAIDは拡張実習です。

<a id="containers"></a>
## Docker：本物の実行環境で1周する

Dockerはパッケージとdaemon、クライアント、イメージ、コンテナ、volumeを分けて理解します。導入はOSと版に合う[Docker公式手順](https://docs.docker.com/engine/install/ubuntu/)を使い、ディストリビューション配布版と公式リポジトリ版を混ぜません。Docker権限を持つ利用者はホストへ強い操作権限を持つことを理解し、専用VMで練習します。

導入後は `docker version`、`docker info`、`docker run --rm hello-world`。続けてStage 5、7を**本物のDockerモード**で解きます。`docker ps -a`→`docker logs`→`docker inspect`→`docker exec` の順で確認し、ローカルループバックにだけ公開したポートへcurlします。

Composeでは `docker compose config`→`up -d`→`ps`→`logs`→アプリの応答確認→`down`。停止・削除後もvolumeデータが残る場合を確認し、復元を試します。`down -v` や `prune` の範囲を読み、必要なデータは先に退避します。更新ではイメージ版を固定し、再作成後に正常系・データ・戻し方を確認します。

本物のdaemonが起動しているLinuxホストまたは専用VMでは、追加実習を開始できます。遠隔Docker contextではなく、curlから同じホストのloopbackへ接続できる環境を使います。

```bash
python3 -m engine.toolbox doctor docker
python3 -m engine.toolbox start docker
```

Docker実習のパッケージ導入欄は空です。OS別の公式導入手順で準備します。CLIが存在してもdaemonの停止や権限不足ならsetupは失敗し、模擬Dockerに置き換えません。

`TASK.txt` と `.docker-fixture.json` にある専用名・ラベルを使い、Dockerfileからbuildします。壊れた `APP_MODE` の終了とログを確認し、正しい環境変数へ直します。アプリはUID10001、ポートは `127.0.0.1` だけへ公開します。`docker inspect` で動的な公開ポートを調べてcurlし、最初のコンテナをstop→rm→再作成してもnamed volumeのデータが残ることを確認します。正常応答と故障・稼働ログを保存してcheckします。

合格後に、実習シェルの `cleanup` で専用container・volume・imageを解除します。シェルを終了した後ならリポジトリのルートで次を使います。

```bash
python3 -m engine.toolbox cleanup --directory ./workspace/toolbox/docker
```

`--directory` を指定して始めた場合は、その作業フォルダを指定します。解除は実習の名前とラベルが一致する資源に限定します。共有環境で `docker system prune` や `docker volume prune` を使う必要はありません。作業フォルダのログと設定は別に残ります。

到達確認：Dockerfileから構築し、環境変数やポート違いの障害を直し、volumeを保って作り直し、専用資源を撤去できること。模擬Dockerの合格は実Dockerの起動成功とは別です。

<a id="recovery"></a>
## 手本なしの総合確認

ここでは「指定コマンドを入力した」ではなく、成果物と復旧の結果で確認します。手本を閉じ、設定値・ファイル名・ポートを変えた新しい作業フォルダまたは専用VMで行います。

| 課題 | 合格に必要な結果 |
|---|---|
| 作業端末を用意する | OS・版・導入元を確認し、Git・エディター・SSH・tmux・jq・curlを起動。自分の設定を控え、戻せる |
| ログを整理する | 空白入りファイル名を含むログから期間・エラー・上位項目を集計。原本を保全し、入力が変わっても動く |
| 開発物を受け渡す | 新しいGit repoで分岐・統合・テスト。別cloneで再実行でき、秘密や生成物を混ぜない |
| リモート作業を続ける | VM間でSSH鍵認証し、tmuxからdetach/attach。ファイルを転送して内容・権限を確認 |
| 小さなサービスを運用する | Nginx→アプリ→SQLiteを構築。自動起動、ログ、TLSを確認。502を切り分け、再起動後も稼働 |
| 変更を戻す | データ・設定を退避し、わざと誤変更。別の場所へ復元して内容・権限・整合性を確認 |
| 定期処理を任せる | 最小限の環境でバックアップを実行。失敗を成功とせず、ログを残し重複と後始末を制御 |
| 更新して撤去する | 変更予定を確認して更新。回帰確認後、専用構成を停止・削除し、残すデータと削除物を説明 |

各課題について「対象・正常時の証拠・故障の証拠・仮説・変更内容・修正後の証拠・戻し方」を1枚の記録にします。必要な情報をmanや公式文書で調べながら解くのは構いません。解答のコピーがないと再現できない項目は再練習します。自動テストのPASSは教材の動作確認であり、受講者の独力習得はこの確認で別に見ます。

<a id="productivity"></a>
## 拡張：fd・fzf・bat・tree・ncdu・dotfiles

標準道具で目的を説明できてから導入します。Ubuntuではfdは`fd-find`パッケージの`fdfind`、batは`bat`パッケージの`batcat`の場合があります。`command -v` とパッケージのファイル一覧で実体を調べます。

| 道具 | 使い始める操作 | 確認・設定・撤去 |
|---|---|---|
| fd/fdfind | `fdfind -t f '\.log$' .` | 隠しファイル・ignoreの扱いを確認。別名はユーザー設定だけに置く |
| fzf | `find . -type f | fzf` | `Ctrl+C`で取消。空白を含む名前を後続へ安全に渡す |
| bat/batcat | `batcat --paging=never FILE` | 色・pagerを確認し、スクリプトの機械可読出力はcatと分ける |
| tree | `tree -a -L 2 .` | 隠しファイルと深さを選び、秘密を共有出力に混ぜない |
| ncdu | `ncdu -r -x PATH` | 読み取り専用で容量を調べる。削除操作を使わなくてもよい |
| direnv | `direnv status` | `.envrc`の内容を読んでから許可。解除とシェルhookの撤去も確認 |
| stow | 専用フォルダでリンク配置を試す | 既存設定の控えを取り、リンク解除後も元データが残ることを確認 |

更新・削除はパッケージ管理の節に従い、シェルのalias・hook・設定・データは別に確認します。Stage 32-10、32-20、32-25〜26は入口であり、すべての対話UIを実行検証した課題ではありません。

<a id="security"></a>
## 拡張：セキュリティ・暗号化・MAC

Stage 8〜10で権限・証拠・修正・回帰確認を学び、Stage 16〜20でSELinux/AppArmor、capability、firewall、GPG、VPN、ディスク暗号化へ進みます。設定・記録読解の課題は実ポリシーを変更しません。専用VMで「許可すべき操作が通り、拒否すべき操作が拒否される」を追加確認します。

業務システムの監査、暗号鍵の保管・失効、攻撃への対応は組織の運用手順が必要です。根拠を読み、許可範囲と復旧計画を持って変更します。

<a id="infrastructure"></a>
## 拡張：VM・LVM・RAID・VPN

Stage 14〜15、20、22を入口に、使い捨てVMと追加の空ディスクで実習します。通常のstorageモジュールは専用ext4イメージまでで、物理ディスク、実LVM/RAID、GRUB復旧を経験した扱いにはしません。`pvs/vgs/lvs`の前後比較、容量拡張、再起動、保持データの検証を追加します。

ネットワーク構築はサブネット・経路・DNS・NAT・ファイアウォールを図示し、管理接続を残して戻せるようにします。Stage 22のvirshやTerraform等は記録・設定読解であり、実インフラへの適用とは区別します。

<a id="cloud"></a>
## 拡張：クラウド・Kubernetes・IaC・他の開発言語

Kubernetes、Helm、Terraform、Ansible、監視の課題はStage 18、22、Node/Go/Rust/JavaはStage 33にあります。これらは主に設定と記録の読解です。各言語・クラウドの実環境構築、IAM・課金・可用性・state保護・実クラスタ運用まではこの常用コアの合格条件に含めません。

`aws`・`gcloud`・`az`は検索用の拡張語で、既存課題で実行を教えているという意味ではありません。必要なサービスを選んで、公式の無料/検証環境と予算・撤去手順を用意して別コースとして実習します。

<a id="desktop"></a>
## 拡張：デスクトップと環境差

GUIアプリの導入・削除、Flatpak/Snapの権限、WSLとの差、`xdg-open`の関連付けを確認します。GPU、無線、Bluetooth、プリンター、サスペンド、デュアルブートは機種とディストリビューションに依存するため、本コースの自動判定はありません。

CLI常用の達成と、あらゆるLinuxデスクトップの保守は別の範囲です。Stage 14-7〜8、18-6、34-17を入口に、対象機器の公式手順とログで調べる練習へ進みます。
