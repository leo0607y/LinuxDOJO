# 常用Linuxの網羅性と検証範囲

## 2026-11-22 再開後の実VM確認

追加モジュールは一律未検証ではなく、実出力の記録で区別します。

| 対象 | 確認したこと | 記録 |
|---|---|---|
| sshd / mounts / journald / sysctl / limits | 正解・故障/抜け道拒否・reset（再起動は未確認） | docs/vm_verification/g2-system.md |
| ftp | 認証・chroot・PASV・往復転送・不正状態拒否・reset・再setup/reset | docs/vm_verification/g8-ftp.md |
| permissions（再確認） | 既存/新規ファイルのACL・不正状態拒否・reset・再setup/reset | docs/vm_verification/permissions-recheck.md |
| firewall | 実nft/netns通信・確立済み接続・再読込/重複拒否・reset | docs/vm_verification/g1-firewall.md |

前セッションの他担当は中断済みです。これ以外の追加モジュールは、途中変更やVMが残っていても検証済みとはしません。RHEL系の3本も未検証です。最新の根拠は `docs/vm_verification/` を参照してください。

再現はリポジトリの `tools/vmtest/verify_scenario.py` と `tools/vmtest/scenarios/*.sh` を使います。ホストでシナリオのシェルを直接実行せず、専用VMに対して実行します。


この表は「日常のCLI操作・開発・小規模サーバー運用」を対象にした教材の対応表です。27のコア到達目標と5つの拡張分野を分けます。全コマンド、全ディストリビューション、あらゆる業務・機器を網羅した認定ではありません。学習順と実際のコマンド例は[常用コース](LINUX_DAILY_USE.md)、検索用の正本は `curriculum/toolbox_catalog.py` です。

## 判定の読み方

| 表示 | 実際に行うこと | この表示だけでは証明しないこと |
|---|---|---|
| 実ツール | 通常のbashと実行ファイルで処理し、生成物・内容・原本保持などを検査 | 別の環境でも操作できること、学習者の独力習得 |
| 模擬 | 教材専用のコマンドやターミナルを操作 | 本物のOS・サービス・Dockerでの成功 |
| 記録・設定 | 採取済み出力を解析、設定や手順を編集。課題により静的検査も含む | 対象ツールや管理操作を実行した経験 |
| VM実習 | 専用の使い捨てVMで実OS・サービス・パッケージを操作しcheck | このリポジトリの通常テストだけでVMの起動・再起動まで検証したこと |
| 手動確認 | 明示した操作・成果物を学習者が実機で確認 | 自動判定の実装・実行済みの証拠 |

既存501問は問題ごとに方式が違います。下表の「既存課題」は学習の入口であり、列挙した全問が実ツール方式という意味ではありません。新しいnative実習は必要ツールがなければ実行不可を表示し、記録読解へ黙って置き換えません。ツール存在確認の成功と、実習の成功も別です。

`audit_coverage.py` の428/528は教材ソースに名前が出た割合です。本表の159コマンドも到達目標の検索語であり、名前の数だけでは網羅率を計算しません。`engine.toolbox audit` は参照先の整合性を検査します。理解や実機修了の判定ではありません。

## 再監査で見つかった不足と対応状況

2026-11-21の再監査で、27分野への案内があることと、その全到達目標を実操作で検証できることは一致していないと判明しました。見つかった6件に、次の実習を追加しました。**追加したVM実習5件は、この開発機に qemu も sudo が無いため、構文検査・誤った文脈での拒否・静的な安全確認までしか行っていません。実VMでの実行は未実施です。** 実VMで初回に確認する項目は `labs/vm/README.md` に記載しています。

| 不足していた実操作 | 追加した実習 | 検証状況 |
|---|---|---|
| ユーザー・グループ・sudoの作成→反映→許可/拒否→撤去 | VM `users` | 静的のみ。`sudo -n -l` で許可/拒否を判定し、拒否側のコマンドは実行しない |
| NIC・固定IP・経路・DNSクライアント・IPv6の適用と永続化 | VM `netconfig` | 静的のみ。dummy NIC `dojo0` だけを操作し、既定経路と本線は変更しない |
| 基本ファイアウォールの実適用・許可/拒否・接続を保った復旧 | VM `firewall` | 静的のみ。専用nftテーブルと netns+veth で判定し、自動ロールバック付き適用スクリプトを用意 |
| バックアップから別VMへサービス全体を復元 | VM `restore`（app と client の2台） | 静的のみ。UIDがVM間で異なる状況を固定して再現 |
| OS更新・リポジトリ署名・依存不整合からの復旧 | VM `osupdate` | 静的のみ。ローカルの署名付きaptリポジトリを使い、署名回避は不合格 |
| ログ保存量・実ローテーション・書込み継続の確認 | native `logrotate` | ホストの実 logrotate/gzip で実行し、単体テストが通過（logrotate が無い環境ではskip） |

この表は「不足を実装した」記録であり、「小規模サーバー管理まで網羅した」という評価ではありません。実CPU/OOM/I/O障害の切り分け、実cron、対話的なtmuxのdetach/attach、デスクトップの日本語入力・無線・音声・アプリ関連付けは、引き続き実習の深さが足りません。後掲の修了確認には、手動確認で補う項目が含まれています。

## 追加監査の結果と第2弾の実装状況

`objectives_matrix.md`（LPIC-1/2、LFCS、RHCSA の試験範囲178行との突き合わせ）の結果、第1弾の時点では COVERED 55、PARTIAL 112、MISSING 11 でした。その後、次を追加しました。いずれも作成直後で、**実VMでの実行は未実施**です（ネイティブ実習は実機で実行済み）。

| 領域 | 追加した実習 | 検証状況 |
|---|---|---|
| 実cron、bash堅牢化、tcpdump、deb自作 | native `cron`、`trap`、`tcpdump`、`debbuild` | ホストの実ツールで実行しテスト通過。実cronデーモンと実キャプチャ（権限不足のためpcap再生で代替）は未検証 |
| sshd堅牢化、fstab/swap/LVM、journald、sysctl、cgroup/OOM、時刻/ロケール、fail2ban/auditd | VM `sshd`、`mounts`、`journald`、`sysctl`、`limits`、`timesync`、`guard` | 静的のみ、実VM未実施 |
| DNS/メール/NFS/Apache/Samba/LDAP | VM `dnsserver`、`mailserver`、`fileshare`、`apache`、`samba`、`ldap` | 静的のみ、実VM未実施。サーバー系パッケージは setup が導入コマンドを案内 |
| bridge/VLAN/bond、PAM、podman、libvirt、tuned | VM `netlink`、`pam`、`podman`、`libvirt`、`tuned` | 静的のみ、実VM未実施 |
| カーネル、GRUB | VM `kbuild`、`grubrescue` | 静的のみ、実VM未実施。カーネル全体のビルドと実機のレスキュー起動は自動判定しない |
| RHEL系（SELinux、dnf/rpm、firewalld） | VM `selinux`、`dnf`、`firewalld` | 静的のみ、RHEL系VMでは未実施。現行の書き出しはUbuntu専用で、手動手順は `labs/vm/RHEL.md` |

これらは「実装した」記録であり、実VMで通るまでは「検証済み」に数えません。初回確認項目は `labs/vm/FIRST_RUN.md`、集計は `docs/objectives_matrix.md`（再集計は第2弾の実装後に行う）を参照します。

## 追加監査で見つかった未対応の領域

上の6件とは別に、2026-11-21の監査で次の領域は「実操作の課題がない、または読解止まり」と判定しました。既存501問の多くは採取済み出力や設定を読む方式のため、語が教材に出ることは実操作の証拠としていません。優先度順です。

| 優先 | 領域 | 現状 | 追加するなら |
|---|---|---|---|
| 1 | sshdの堅牢化（鍵のみ、root禁止、ProxyJump） | 読解止まり | 専用sshdを別ポートで立て、`sshd -t`→reload→許可/拒否を確認（VM） |
| 2 | fstab誤記・LVM・swap・LUKS | storageは容量/inodeのみ | ループバックで作成→fstab誤記→`nofail`で復旧（VM） |
| 3 | 実cron / at | 実cronは深さ不足、atは課題なし | 専用ユーザーのcrontabでPATH・環境・flock・ログを検証（native可） |
| 4 | journaldの永続化と保存制限 | 設定検査のみ | `Storage=persistent`と`SystemMaxUse`を設定し再起動後を確認（VM） |
| 5 | sysctl・カーネルモジュール | 読解のみ | `sysctl.d`で永続化、modprobeのblacklist（VM） |
| 6 | GRUB/initramfs・レスキュー | bootはunit復旧のみ | VMのスナップショット前提で手動実習（高リスク） |
| 7 | cgroup・ulimit・OOM | 読解のみ | `MemoryMax`付きunitをOOM killさせ、journal/dmesgで特定（VM） |
| 8 | bash堅牢化（`set -euo pipefail`、trap） | trapは記録止まり | 失敗注入下のスクリプト修正（native可、最も低コスト） |
| 9 | NTP/chrony・timezone・locale | timedatectlの手順のみ | 時刻ずれを再現し同期へ戻す（VM） |
| 10 | fail2ban・auditd・AppArmor/SELinux | 実習なし | ログイン失敗の自動ban、監査ルールと`ausearch`（VM） |

他にtcpdump（loopbackでnative可）、debの自作、MTA、tmuxの対話的なdetach/attach、`at`が浅いか未対応です。これらが埋まるまで、「Linuxの不足はない」とは言えません。

## コアの到達目標と課題

native欄のIDは `python3 -m engine.toolbox start ID` で開始します。VMはエクスポートした専用VM内の `dojo-vm-lab` で実行します。

| 到達目標 | できるようにすること | 既存課題ID | native実習ID | 管理操作・判定方式 |
|---|---|---|---|---|
| [端末・ヘルプ・PATH・クォート・終了コード](LINUX_DAILY_USE.md#shell) | パイプ、クォート、PATH、失敗を説明 | 1-1、3-4、25-19、25-20、25-21、29-18 | `shell` | 実ツール |
| [ファイル整理・リンク・空白入りファイル名](LINUX_DAILY_USE.md#files) | 空白/改行入りの名前とリンクを安全に扱う | 1-2、1-4、1-5、1-6、3-3、EX-2 | `find` | 実ツール |
| [ログ・CSV・テキストを抽出して集計](LINUX_DAILY_USE.md#text) | 原本を保全してログ/CSVを抽出・集計 | 1-7、2-2、2-5、2-7、2-8、24-4、24-5、EX-5 | `shell` | 実ツール |
| [find・ripgrep・jqで必要な情報を探す](LINUX_DAILY_USE.md#search) | 検索範囲・条件・出力構造を選ぶ | 2-3、2-6、6-5、32-1、32-2、32-3、32-9 | `find`, `rg`, `jq` | 実ツール、一部既存は代替検査 |
| [Vim・nanoで編集し、保存・取消・復旧](LINUX_DAILY_USE.md#editor) | 対話編集・保存・取消・復旧 | 6-6、31-1、31-3、31-7、31-13、31-15、31-16、31-18、31-19 | `vim` | Vim実ツール、nano等は手動/記録 |
| [圧縮・展開・チェックサム・配布物の検証](LINUX_DAILY_USE.md#archive) | 内容・権限・秘密除外を検証して復元 | 4-1、4-2、9-6、25-2、25-12、25-13 | `archive`, `release` | 実ツール |
| [同期・世代管理・別の場所への復元](LINUX_DAILY_USE.md#backup) | dry-run、差分、除外、別の場所へ復元 | 6-8、9-7、11-6、13-8、17-10、23-3、23-4 | `rsync`, `archive` | 実ツール、計画課題は記録 |
| [OSを識別して導入・更新・削除・提供元を確認](LINUX_DAILY_USE.md#packages) | 実deb導入→設定→更新→修復→remove/purge | 12-5、17-8、24-12、29-11、29-12、29-13、29-14 | —（VM/手動） | 既存は記録/設定、VM packages |
| [所有者・グループ・権限・ACLを直す](LINUX_DAILY_USE.md#permissions) | 許可と拒否の両方を別利用者で確認 | 3-1、3-2、9-2、9-4、12-7、16-4、16-6、16-10 | —（VM/手動） | 通常modeは実ツール、ACL/利用者はVM permissions |
| [ユーザー・グループ・ログインとsudo](LINUX_DAILY_USE.md#users) | 専用利用者・グループ・sudoを管理 | 7-4、16-10、16-11、28-1、28-2、28-3、28-4 | —（VM） | 7-4は模擬、他は記録/設定。VM `users`（静的検証のみ、実VM未実施）がuseradd/visudo/sudo許可拒否を扱う |
| [プロセス・ジョブ・資源・シグナル](LINUX_DAILY_USE.md#process) | 対象PID、通常終了、資源、失敗を区別 | 3-5、3-6、3-7、12-1、12-2、12-3、12-4、27-1、27-9、27-10 | `incident` | 実ツール+記録、VM performance |
| [IP・経路・DNS・待受を順に調べる](LINUX_DAILY_USE.md#network) | IP・経路・DNS・待受・応答を切り分け | 4-5、4-6、13-1、13-2、13-6、17-1、29-7、32-15 | `curl` | localhost実ツール+記録、VM networkはDNS/HTTP、VM `netconfig` がNIC・固定IP・経路・IPv6（静的検証のみ、実VM未実施） |
| [curlで取得・API・HTTPエラーを確認](LINUX_DAILY_USE.md#http) | 正常/失敗応答、本文、終了コードを分ける | 4-3、4-4、8-2、32-5、32-6、32-7、32-8 | `curl` | localhost実ツール |
| [TLSの名前・期限・信頼・鍵を検証](LINUX_DAILY_USE.md#tls) | 信頼・名前・期限・鍵対応を検証 | 13-3、20-10、20-11、20-12、20-14、20-16 | `tls` | 実OpenSSL+記録、VM webstack |
| [SSH接続・鍵・転送・踏み台・認証失敗](LINUX_DAILY_USE.md#ssh) | 鍵・ホスト識別・接続・転送・拒否を確認 | 4-7、9-3、20-6、20-9、34-1、34-5、34-6、34-10、34-11、34-12、34-18 | `ssh` | 実鍵/ssh -G+記録、VM sshは実認証/転送 |
| [tmuxで分割・切断・再接続・長時間処理](LINUX_DAILY_USE.md#tmux) | 分割、detach/attach、copy、終了 | 34-19、34-20、34-21、34-23、34-25 | `tmux` | 既存は記録/設定、nativeは実tmux |
| [Gitで変更・分岐・統合・履歴・復旧](LINUX_DAILY_USE.md#git) | 分岐・統合・別clone・履歴復旧 | 30-1、30-2、30-4、30-6、30-7、30-11、30-12、30-17、30-21、30-28 | `git` | ローカル実Git |
| [Pythonの仮想環境・依存・実行・テスト](LINUX_DAILY_USE.md#python) | 隔離、依存導入、再構築、テスト | 33-1、33-2、33-3、33-4、33-5、33-22 | `python`, `python-packages` | 既存は記録/設定、nativeは実venv/pip |
| [CとMakeでビルド・テスト・警告を直す](LINUX_DAILY_USE.md#build) | 依存に基づくビルド・実行・clean | 24-11、24-13、33-12、33-13、33-14、33-15、33-18 | `build` | 既存は記録/設定、nativeは実gcc/make |
| [SQLiteの検索・更新・退避・復元](LINUX_DAILY_USE.md#database) | transaction、退避、復元、整合性確認 | 13-5、32-24 | `sqlite` | 既存は記録、nativeは実sqlite3 |
| [Nginxの設定検証・公開・502・TLS](LINUX_DAILY_USE.md#web) | 構文検査、proxy、TLS、502復旧、再起動 | 13-4、20-14、21-14 | —（VM/手動） | 既存は記録/設定、VM webstack |
| [systemdで起動・停止・自動起動・復旧](LINUX_DAILY_USE.md#services) | service/timer、ログ、復旧、自動起動、撤去 | 7-1、7-2、7-3、11-5、14-2、18-2、28-20、28-22、28-23 | —（VM/手動） | Stage7は模擬、他は記録/設定、VM boot/software |
| [ログを時間・サービスで絞り、保存を制御](LINUX_DAILY_USE.md#logging) | 時間・unit・保存量を絞って調べる | 7-2、10-2、17-6、17-12、23-13、23-14、29-24 | `logrotate` | 実logrotate+記録、VM software/performance |
| [シェル・cron・timer・失敗時の後始末](LINUX_DAILY_USE.md#automation) | 限定環境、終了コード、重複、trap、ログ | 6-1、6-2、6-3、6-4、6-7、17-11、24-8、24-9、28-20、29-20 | `shell`, `incident` | 実bash、cron/systemdは模擬/設定、VM software |
| [容量・inode・マウント・UUID・fstab](LINUX_DAILY_USE.md#storage) | 容量とinode、UUID、マウント、保持データ | 3-8、11-1、11-2、11-3、11-7、15-2、15-10、26-9、26-20 | —（VM/手動） | 記録/設定、VM storageは実ext4イメージ |
| [Dockerを実機で導入し構築・運用・撤去](LINUX_DAILY_USE.md#containers) | 実daemonでbuild/compose/volumeと復旧 | 5-1、5-2、5-3、5-4、5-5、5-6、5-7、7-5、7-6、7-7、22-15 | `docker` | 実Docker/模擬を切替 |
| [総合障害を根拠から切り分けて復旧](LINUX_DAILY_USE.md#recovery) | 根拠保全、原因切り分け、復元、再起動 | 3-8、5-7、6-8、10-6、11-8、12-4、13-7、13-8 | `incident`, `release` | 実ツール+記録、VM各モジュール |

## 導入後のライフサイクル

各ソフトについて最低限、導入・基本操作・設定・結果確認・故障対応・更新/撤去をつなぎます。CLIソフトの「起動」はコマンド実行であり、常駐サービスの起動とは区別します。

| 対象 | 導入・更新・削除 | 使い方と設定 | 結果確認・故障対応 | 実機での追加確認 |
|---|---|---|---|---|
| Git | OSパッケージ手順 | Stage 30 / native `git` | branch・merge・reflogとrepo状態 | 別cloneで再現。実リモートへのpushは利用先の権限も確認 |
| Vim / nano | OSパッケージ手順 | Stage 31 / native `vim` | 保存・差分・取消・swap | キー操作を実端末で試す。nanoは手動 |
| tmux | OSパッケージ手順 | Stage 34 / native `tmux` | 実ペイン・capture・専用socket | detach/attach・copy modeを実端末で試す |
| jq / rg | OSパッケージ手順 | Stage 32 / native `jq`・`rg` | 別入力・該当なし・原本保持 | 自分のJSON/ソースでも再実行 |
| curl / wget | OSパッケージ手順 | Stage 4 / 32、native `curl` | localhost応答・HTTP失敗 | プロキシ・実TLS環境は各環境で確認 |
| rsync / tar | OSパッケージ手順 | Stage 4 / 17、native `rsync`・`archive` | dry-run・除外・別フォルダ復元 | 実SSH越し転送・所有者/ACLはVMで確認 |
| SSH | クライアント/サーバーを分離 | Stage 34 / native `ssh` | 実鍵・`ssh -G`、記録診断 | VM sshでloopback実ログイン・拒否・転送。別VM間も手動確認 |
| Python | OS本体とvenvの依存を分離 | Stage 33 / native `python`・`python-packages` | interpreter隔離・実pip導入→利用→更新→freeze | ローカルwheelの削除・同版再導入もguideで確認 |
| gcc / Make | OSパッケージ手順 | Stage 33 / native `build` | 実ビルド・成果物・clean | gdbの対話操作・他のビルド方式は追加確認 |
| SQLite | OSパッケージ手順 | Stage 13 / 32、native `sqlite` | 実CLIでtransaction・backup/restore | 他DBサーバーの権限・WAL・冗長化は対象外 |
| OpenSSL / TLS | OSパッケージ手順 | Stage 20 / native `tls` | 実証明書・信頼・名前検証 | VM `webstack` で実HTTPS。公開CA更新は手動 |
| Nginx | 専用VMで導入、停止、撤去 | Stage 13 / 21、VM `webstack` | 構文検査・502・TLS・再起動 | VM実行ログが修了の証拠 |
| systemd / timer | VM `software` で構築と撤去 | Stage 7 / 28、VM `boot`・`software` | 実ログ・設定故障・再起動後 | ホストの模擬systemctl成功で代替しない |
| OSパッケージ | VM `packages` | 実debのv1→v2、conffile | 故障→修復、remove→purge | VM実行が必要。私有dpkg rootテストは実VMとは別 |
| Docker / Compose | 公式のOS別導入手順 | Stage 5 / 7の実Dockerモード、native `docker` | 実build・故障ログ・非root・HTTP・volume保持 | 実daemon・image取得が必要。cleanupは専用資源のみ |
| fd/fzf/bat/tree/ncdu | OSパッケージ手順 | Stage 32-10 / native `fzf`、guide | ignore・pager・候補・容量 | 便利機能の選択科目。対話UIは実端末確認 |

一般的なパッケージ操作は、実debで導入・更新・remove/purgeまで検証するVM `packages` と、導入後の各ツール実習を組み合わせます。各ツールを自動でホストへインストールする仕組みではありません。サービスの設定・データをパッケージ本体と分け、更新前の退避、更新後の確認、撤去後に残すものまでguideで扱います。

## コマンドの基準一覧

下記は27コア到達目標の重複を除いた159コマンドです。組み込み・外部コマンド・パッケージの補助ツールを含みます。課題・実機確認の割当は上表とcatalogで追跡し、名前を足しただけでは到達済みにしません。

| 分野 | 主要コマンド（重複は最初の分野へ掲載） |
|---|---|
| shell | `bash` `man` `info` `help` `type` `command` `pwd` `cd` `history` `env` `export` `printf` `read` `test` `true` `false` |
| files | `ls` `mkdir` `touch` `cp` `mv` `rm` `ln` `stat` `file` `readlink` `realpath` `basename` `dirname` |
| text | `cat` `less` `head` `tail` `grep` `sed` `awk` `cut` `sort` `uniq` `wc` `tr` `tee` `paste` `join` `comm` `diff` `patch` `iconv` |
| search | `find` `xargs` `rg` `jq` |
| editor | `vim` `vimtutor` `view` `vimdiff` `nano` |
| archive | `tar` `gzip` `gunzip` `zcat` `zgrep` `xz` `unzip` `zip` `sha256sum` |
| backup | `rsync` `cmp` |
| packages | `apt` `apt-cache` `dpkg` `dpkg-query` `dpkg-deb` `dnf` `rpm` |
| permissions | `id` `chmod` `chown` `chgrp` `umask` `getfacl` `setfacl` `namei` `sudo` `sudoedit` |
| users | `whoami` `getent` `useradd` `usermod` `userdel` `groupadd` `passwd` `chage` `visudo` |
| process | `ps` `pgrep` `top` `free` `uptime` `kill` `pkill` `jobs` `fg` `bg` `nohup` `timeout` `nice` `renice` `lsof` `strace` |
| network | `ip` `ss` `ping` `dig` `resolvectl` `traceroute` |
| http | `curl` `wget` |
| tls | `openssl` |
| ssh | `ssh` `ssh-keygen` `ssh-agent` `ssh-add` `ssh-copy-id` `scp` `sftp` |
| tmux | `tmux` `script` |
| git | `git` |
| python | `python3` `pip` `pytest` |
| build | `gcc` `make` `gdb` `pkg-config` |
| database | `sqlite3` |
| web | `nginx` |
| services | `systemctl` `systemd-analyze` `systemd-run` `journalctl` |
| logging | `logger` `logrotate` `date` `timedatectl` |
| automation | `crontab` `flock` `shellcheck` |
| storage | `df` `du` `lsblk` `blkid` `findmnt` `mount` `umount` `fsck` `losetup` |
| containers | `docker` |

## 拡張分野と明示した境界

| 拡張分野 | 入口の課題 | 実機までの不足 |
|---|---|---|
| [fd・fzf・bat・tree・ncduで日常を効率化](LINUX_DAILY_USE.md#productivity) | 32-10、32-20、32-25、32-26 | fzf絞り込み以外の対話UI・個別設定は手動確認 |
| [MAC・監査・暗号化・最小公開](LINUX_DAILY_USE.md#security) | 9-1、9-5、16-1、16-2、16-3、16-7、17-2、18-4、19-10、20-1 | 実MAC・firewall・鍵管理の変更、業務手順は追加実習 |
| [VM・LVM・RAID・VPN・ネットワーク構築](LINUX_DAILY_USE.md#infrastructure) | 15-3、15-4、15-5、20-3、20-4、22-1、22-2、22-3、22-8 | 実LVM/RAID・物理ディスク・起動不能復旧・VPNの構築 |
| [クラウド・Kubernetes・IaC・監視](LINUX_DAILY_USE.md#cloud) | 18-13、18-14、22-10、22-11、22-12、22-13、22-14、22-16 | 実クラスタ・クラウドCLI/IAM/課金/stateの運用 |
| [デスクトップ・周辺機器・アプリと環境差](LINUX_DAILY_USE.md#desktop) | 14-7、14-8、18-6、29-23、34-17 | GUI、無線/GPU/周辺機器/省電力の実機検証 |

特に次は、常用コアとは分けて実機・サービス別の追加学習が必要です。

- **OSの新規インストール・ブート不能復旧**：cloud-init VM作成や専用service故障と、ISO導入・GRUB/initramfs復旧は別。VM READMEの手動実習で扱います。
- **物理ストレージ、LVM/RAID、NAS**：既存課題は記録中心。storage VMの専用ext4イメージだけで実機全体の保守経験とはしません。
- **デスクトップ固有の機器**：無線/GPU/Bluetooth/プリンター/音声/省電力/デュアルブートは自動実習なし。ハードウェアとOSの公式手順が必要です。
- **商用DBと大規模運用**：MySQL/PostgreSQL/Redis、レプリケーション、容量設計、DRは記録読解の先に実環境が必要です。
- **クラウド・Kubernetes・IaC**：既存は主に設定・出力読解。aws/gcloud/azは未実装の拡張検索語で、実課題の提供を意味しません。
- **資格試験**：この表はLPIC/LinuC/RHCSA等の公式出題範囲との全項目対応表ではありません。試験対策を名乗る際は別に公式範囲と照合します。

## 学習者の修了確認

[常用コースの総合確認](LINUX_DAILY_USE.md#recovery)を手本なしで行い、次を残します。

1. OS・版・導入元・実体を確認し、自分の道具を用意できる。
2. 入力値やパスが変わっても、検索・集計・編集・梱包・転送ができる。
3. Gitと依存宣言で作業を別の場所へ再現できる。
4. SSH・tmuxで実機へ接続し、切断後も作業を継続できる。
5. サービス・ネットワーク・権限・ログ・ストレージを区別して故障を調べられる。
6. 退避→変更→正常/異常確認→復元→再起動→更新/撤去まで実施できる。

### 手本なしで残す成果物と合格条件

全501問を先に終える必要はありません。guideの必修経路を進めたあと、手本を閉じ、新しい作業フォルダと専用VMで次の成果物を作ります。`completion/` は自分で作る記録用フォルダです。教材の自動採点とは別の最終確認として扱います。

| 実作業 | 残す成果物の例 | 合格条件 |
|---|---|---|
| 自分の作業環境を用意 | `completion/environment.md`、導入前後のパッケージ一覧 | OS・版・導入元・実行ファイルの場所・設定の保存先が分かる。更新予定と撤去後の残存物を説明できる |
| ファイルとログを処理 | `completion/process-logs.sh`、`errors.csv`、原本の`SHA256SUMS` | 空白/改行入りファイル名、該当なし、失敗した入力も処理。原本のハッシュを保ち、別入力でも正しく集計 |
| 編集して配布 | Git repo、`release.tar.gz`、チェックサム、差分 | 元の設定へ戻せる。別cloneでビルド/実行でき、秘密・不要な生成物をアーカイブへ混ぜない |
| バックアップして戻す | `backup/`、別の`restored/`、比較結果 | 原本の変更/欠損を作ってから別の場所へ復元。本文・必要なmode・隠しファイルを照合し、除外と保持方針を説明 |
| PythonとDBを再現 | 依存lock、テスト結果、DB退避と復元先 | 新しいvenvで同版を再導入。SQL誤更新をrollbackし、確定後もbackupから別DBへ戻して整合性と値を確認 |
| リモート作業を継続 | `completion/ssh.md`、転送前後ハッシュ、tmuxの状態記録 | 信頼したホスト鍵で実接続し、正しい鍵だけを許可。転送内容が一致し、detach後にattachして作業を継続 |
| サービスを構築 | 専用unit/timer、アプリ設定、正常応答、journal抜粋 | 最小権限で起動。TLS検証を無効にせず応答し、再起動後も動作。ログとデータの保存先を説明 |
| 故障を切り分ける | `completion/incident.md`、故障時/修正後の証拠 | 設定・権限・DNS・待受・容量などから原因を絞る。検査を外して成功に見せず修復し、正常系と拒否も再確認 |
| Dockerで再作成 | Dockerfile、実HTTP、故障/稼働ログ、volume保持の証拠 | 実daemonで非rootアプリをbuild/run。設定故障を修正し、コンテナを削除・再作成してもデータが残る |
| 更新・撤去・再構築 | `completion/change.md`、復旧手順、専用資源の確認結果 | 退避→更新→回帰確認→戻し方を実施。停止・削除後に残すデータを確認し、設定/依存から構築し直せる |

`completion/README.md` に実施日、環境、参照した資料、手本を見た項目、各成果物へのリンク、まだ再現できない項目を書きます。秘密鍵・認証情報・個人情報を記録へ混ぜません。次の3条件を満たした項目だけを完了にします。

1. 指定された正常状態だけでなく、少なくとも1つの故障・拒否条件も確認した。
2. 新しいフォルダまたは再作成した専用VMで、入力やポートが変わっても再現できた。
3. コマンドの目的、根拠、影響範囲、戻し方を自分の言葉で説明できた。

受講者がこれらを完了して初めて、この教材が定める「日常CLI・開発・小規模サービス運用のコア」を自力で行えたと判断します。全教材テストPASSを、そのまま受講者の修了に置き換えません。

## 実装と検証記録

- 既存501問：今回も全501問PASS（137.7秒、Dockerは従来のmockモードを含む）。方式の限界はHANDOFFと本表に明示。
- native実習：本物のツールだけを使う20実習を追加（実Dockerと実pipを含む）。未導入のツールは実行不可で表示し、模擬結果による合格はなし。
- VM：既存6モジュールに、導入・版更新・remove/purgeの `packages`、service/timer・再起動・撤去の `software`、実鍵認証・scp/rsync転送・権限障害復旧の `ssh` を追加。
- `packages` は私有dpkg rootで実パッケージの導入・更新・削除の回帰テストを実行。実VMのroot/systemd/再起動を行った検証とは区別する。
- 全unittest：299件、失敗0、skip1（54.0秒）。ホストにDockerデーモンがないため統合1件は明示skipし、同じ実習を実VMの実Dockerで別途検証した。
- 実ツール20実習を実行確認：ホストの実バイナリ（一部は公式debを一時展開）と、専用Ubuntu 24.04.5 KVM VMの実ツールを使用。VMの通常ユーザーでも18実習＋pipの23テストがskipなしPASS（21.1秒）。Dockerは実daemonでbuild→故障ログ→非root HTTP→再作成→volume保持→限定cleanupまでPASS。
- 実VM 9モジュール：packages・software・sshの全段階、permissions・performance、boot・storage・webstackの故障復旧と再起動後のcheckまで実施。networkは2台の実VMで正常→DNS故障を拒否（IP直指定HTTPは成功）→修復後双方PASS。
- 実VM試験で発見したstorageのGNU dfオプション不整合と、専用sshdの起動時ディレクトリ不在を修正。修正後のcheck、SSHの新規setup・再起動、追加回帰テストを実行した。
- 検証は2026-11-21。VMは公式cloud imageのSHA256を照合して作成し、終了後に停止。ホストのOSパッケージ・systemd・ネットワーク設定を変更していない。追加の記録はHANDOFFへ記載。

参照の検査は `python3 -m engine.toolbox audit`、依存確認は `doctor`、既存ミッションは `python3 tests/test_all_missions.py` を使います。新実習の実行確認では、利用できない依存をスキップした数も併記します。実ツールを追加導入して全実習を検証できた場合も、その環境と実VM未実施部分を分けて報告します。
