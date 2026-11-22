# 外部試験目標との対応マトリクス（LPIC-1/2・LFCS・RHCSA）と、試験範囲外の実務領域

作成日: 2026-11-22。再監査: 同日（第 2 版）。目的: 公開されている試験範囲の各行に対して、このリポジトリが何を「実システムに対する操作」として検証しているかを、厳格な基準で判定する。資格対策教材ではない。第 1 部が試験マトリクス、第 2 部が試験範囲外の実務領域。

## 情報源と限界

| 試験 | 取得元 | 取得状況 |
|---|---|---|
| LPIC-1 101/102 (v5.0) | https://www.lpi.org/our-certifications/exam-101-objectives/ | 取得できた。大項目（101.1 など）の一覧。小項目（Key Knowledge Areas）は取得していないので、各行の粒度は大項目 |
| LPIC-2 201/202 | https://www.lpi.org/our-certifications/exam-201-objectives/ | 201 ページに 200.x〜212.x の全項目が出た。202 の個別 URL は取得失敗（トップページが返った）が、項目は上記ページで確認 |
| LFCS | https://training.linuxfoundation.org/certification/linux-foundation-certified-sysadmin-lfcs/ | 5 ドメイン・34 行を取得（25/25/20/20/10%）。LF は頻繁に改訂するため、最新版との差は未確認 |
| RHCSA EX200 | https://www.redhat.com/en/services/training/ex200-red-hat-certified-system-administrator-rhcsa-exam | 取得した要約は「59 項目」と言いつつ列挙は 62 行で数が合わず、特に「Manage security」の項目数が不整合。したがって RHCSA 一覧は取得文と私の記憶の混合で、粒度と数に誤差がある（重複 1 行 = 55 は削除し 61 行として数える）。**RHCSA は信頼度が最も低い** |

## 判定基準（第 2 版、厳格化）

- **COVERED-REAL**: native 実習（ホストの実ツールで動かし成果物を検査）、または実 VM で実行済みの VM モジュール。従来9モジュールに加え、`sshd mounts journald sysctl limits ftp firewall` の実出力を `docs/vm_verification/` に記録済み。再起動後の確認など各記録の未検証範囲は残る。
- **IMPLEMENTED-UNVERIFIED**: 実状態を判定する実習がディスク上に存在するが、実 VM で一度も実行していない（`bash -n`、誤文脈拒否のガード試験、静的な内容試験しか通っていない）。判定コードの出力形式・パッケージ名・タイミングが実機で正しい保証はない。
- **PARTIAL**: 採取済み出力や設定例を読むだけのミッション、行の一部しか判定しない実習、またはモックでしか動かない実習。
- **MISSING**: 該当する実習・ミッションがない、または名前が出るだけ。
- 第 1 版の「VM静的」は誤り（実習は実状態を判定している）。今回、28 の未実行モジュールのコード（lab_check と検証関数）を読み、実状態を判定していることを確認したうえで IMPLEMENTED-UNVERIFIED とした。主要操作が判定されない行、別製品を要求する行（RHCSA の chrony・NetworkManager など）は PARTIAL に下げた。
- native 実習 23 本（curriculum/toolbox_labs.py: shell find archive rsync git vim jq rg curl ssh tmux sqlite python build fzf tls incident release logrotate cron trap tcpdump debbuild）と、toolbox_containers.py の docker、toolbox_python.py の python-packages は、ホストの実ツールで実行して判定する（docker は daemon が必要）。ただし cron は自前の crontab パーサで評価して実 cron デーモンは動かさず、tcpdump は用意済み pcap を読む形式で実キャプチャは判定しない。
- 種別: N = native、V = 使い捨て VM が必要。数字はミッション ID（501 問）。
- 「VM未実行」と書いた旧記述は、旧根拠の引用として残している。「実装済み」は旧版の「進行中」を置き換えたもの。

## LPIC-1（101/102 v5.0。104.4 は削除済みで除外、42 行）

| 目標 | 状態 | 根拠・再判定 | 昇格条件／閉じる演習 | 種別 |
|---|---|---|---|---|
| 101.1 ハードウェア設定 | PARTIAL | 14-7（lspci/lsusb/dmidecode 読解）、14-11（udev ルール編集のみ） | 実 VM で udev ルール適用→`udevadm test`→名前固定を確認 | V |
| 101.2 ブート | PARTIAL | 14-1, 14-2, 14-8 読解。VM boot は unit 起動失敗と再起動確認のみで BIOS/UEFI・ブートローダ操作ではない | VM で initramfs・カーネル引数を変えて再起動 | V |
| 101.3 ランレベル/ターゲット・停止 | PARTIAL | 14-12, 28-24, 28-17 読解。VM boot/software は再起動後の確認を含むが `set-default`/`isolate` は未実行 | VM で `systemctl set-default`/`isolate rescue` を実行し再起動 | V |
| 102.1 ディスクレイアウト設計 | PARTIAL | mounts は fstab/swap/LVM のみ。パーティション設計・/boot・/home 分離は判定しない。（旧記述: 11-1, 15-1, 15-2, 26-20, 29-23（FHS）読解のみ） | ループデバイスで /, /boot, swap, 別 /home を作り fstab 構成 | N(要root)/V |
| 102.2 ブートマネージャ導入 | IMPLEMENTED-UNVERIFIED | ループ上の MBR+core.img・grub-probe UUID・再生成 grub.cfg を判定。実際の再起動は判定しない。（旧記述: 14-1（GRUB 設定の編集のみ。`grub-install`・`update-grub` は未実行）） | 実VMで grubrescue を初回通過させ、判定の実出力を確認 | V |
| 102.3 共有ライブラリ | PARTIAL | 17-9（ldd）、29-19（ld.so.conf/ldconfig）はいずれも作業フォルダ内の読解/設定例 | 自作 .so を ld.so.conf.d 経由で見つけさせ `ldconfig -p` で確認 | N(要root)/V |
| 102.4 Debian パッケージ管理 | COVERED-REAL | VM packages（実 dpkg/apt の導入・更新・remove・purge）、VM osupdate（静的）、24-12, 29-11〜29-16 | native debbuild は実装済み（deb 自作） | V |
| 102.5 RPM/YUM | IMPLEMENTED-UNVERIFIED | RHEL系 VM 限定。署名付きローカル repo・rpm -V・dnf history・versionlock を判定。（旧記述: 17-8（rpm/dpkg 記録の読解）、29-13（sources.list と yum.repos.d の対応づけ）、24-12（rpmbuild 読解）。実 rpm/dnf は一度も動かさない） | 実VMで dnf を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| 102.6 仮想化ゲスト | PARTIAL | 27-24（systemd-detect-virt）、22-1〜22-4 読解 | 優先度低。VM 上で `systemd-detect-virt`・machine-id 再生成を確認 | V |
| 103.1 コマンドライン | COVERED-REAL | native shell、1-1、25-19〜25-24 | なし | N |
| 103.2 テキストフィルタ | COVERED-REAL | 2-1〜2-8、24-1〜24-6、25-x（作業フォルダで実ツールの出力を検査） | なし | N |
| 103.3 ファイル管理 | COVERED-REAL | native find/archive、1-2〜1-8、EX-2 | なし | N |
| 103.4 ストリーム・パイプ・リダイレクト | COVERED-REAL | native shell、2-1、EX-3、25-20 | なし | N |
| 103.5 プロセスの作成・監視・終了 | COVERED-REAL | 3-5（SIGTERM を無視する実プロセスを kill -9）、3-6（ジョブ制御）、27-10（nohup/disown）、VM performance | なし | N |
| 103.6 プロセス優先度 | PARTIAL | 27-8, 16-9（nice/renice/ionice 読解）。実プロセスで renice して効果を測る課題なし | native: 実 CPU 負荷 2 本に nice 差を付け `ps` で配分を確認 | N |
| 103.7 正規表現 | COVERED-REAL | 2-4, 24-1〜24-3, 24-10 | なし | N |
| 103.8 基本編集 | COVERED-REAL | native vim、6-6、31-1〜31-20 | なし | N |
| 104.1 パーティション・ファイルシステム作成 | PARTIAL | mounts は pvcreate/mkswap/resize2fs まで。GPT 作成と XFS/VFAT の mkfs は判定しない。（旧記述: VM storage（専用 ext4 の inode 枯渇とマウント）、26-12（mke2fs をイメージに）。GPT パーティション操作、XFS/VFAT/swap 作成の実操作なし） | ループ/VM ディスクで `sgdisk`→`mkfs.ext4/xfs/vfat`→`mkswap` | V |
| 104.2 ファイルシステム整合性 | PARTIAL | 15-7, 26-4, 26-5, 26-14 読解。VM storage は inode のみ | 壊したループ img に `e2fsck -fn/-p`、`xfs_repair` | N(img)/V |
| 104.3 マウント制御 | COVERED-REAL | UUID 指定 fstab・nofail・findmnt --verify・mount -a を実判定。ループ ext4 のみ、再起動後の自動マウントは未検証。（旧記述: VM storage（再起動後マウント確認）、11-2, 15-8, 26-20 読解。fstab 誤記→復旧の実操作なし。VM mounts は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| 104.5 パーミッション・所有権 | COVERED-REAL | 3-1, 3-2, 16-6, VM permissions（ACL、実機検証済み） | なし | N/V |
| 104.6 ハード/シンボリックリンク | COVERED-REAL | 3-3, 1-x, native find | なし | N |
| 104.7 システムファイルの検索・配置 | COVERED-REAL | 19-1, 29-23, native find | なし | N |
| 105.1 シェル環境のカスタマイズ | PARTIAL | 3-4, 24-16, 28-19, 32-25（作業フォルダ内の rc/profile 編集。実ログインシェルでの反映確認なし） | 専用ユーザーで `su -l` し profile/skel の反映を確認 | V |
| 105.2 簡単なスクリプト | COVERED-REAL | 6-1〜6-8, 24-7〜24-9, 17-11 | trap の native 実習は実装済み | N |
| 106.1 X11 の導入・設定 | MISSING | なし | 実習価値は低い（ヘッドレス VM では検証困難） | - |
| 106.2 グラフィカルデスクトップ | MISSING | なし | 同上。手動確認項目として扱うのが妥当 | - |
| 106.3 アクセシビリティ | MISSING | なし | 手動確認 | - |
| 107.1 ユーザー・グループ管理 | IMPLEMENTED-UNVERIFIED | getent/id/chage/sudo -l による実状態判定。（旧記述: VM users（VM未実行。実 VM 未実行）、7-4, 28-1〜28-5 読解） | 実VMで users を初回通過させ、判定の実出力を確認 | V |
| 107.2 ジョブのスケジューリング | PARTIAL | native cron は crontab を自前パーサで評価し、実 cron デーモンは動かさない。at/atd は未実習。VM software の systemd timer は実機。（旧記述: 6-7, 23-15, 29-20, 19-11（cron/at の記述・読解）。VM software は systemd timer を実際に動かす（cron/at は未）。native cron は実装済み） | native cron（実装済み）、at/atd の実投入と `atq` 確認 | N/V |
| 107.3 ローカライズ | IMPLEMENTED-UNVERIFIED | ロケール生成・localectl の実効値・locale 警告なしを判定。タイムゾーンも判定。（旧記述: 17-7, 24-16, 28-18） | 実VMで timesync を初回通過させ、判定の実出力を確認 | V |
| 108.1 システム時刻 | IMPLEMENTED-UNVERIFIED | timesyncd の実効 NTP/Fallback と TZ を判定。chrony/ntpd は対象外。（旧記述: 17-6, 19-15, 29-24, 24-18（読解）。VM timesync は実装済み） | 実VMで timesync を初回通過させ、判定の実出力を確認 | V |
| 108.2 システムログ | PARTIAL | journald 永続化（g2実VM確認済み）と logrotate（native 実機）はあるが、rsyslog のルールと logger 経由の振り分けは判定しない。（旧記述: native logrotate（実ログ回転）、7-2, 23-14, 17-12 は読解。VM software はジャーナルから設定故障を読む。rsyslog・journald 永続化の実設定なし。VM journald は実装済み） | VM journald（実装済み）、`logger` と rsyslog ルールの実動作 | V |
| 108.3 MTA 基礎 | IMPLEMENTED-UNVERIFIED | 専用 Postfix で実 SMTP: Maildir 配送・エイリアス・リレー拒否・滞留メール・キュー空を判定。（旧記述: 21-8, 21-9, 21-10（Postfix 設定・キュー・SPF/DKIM 読解）） | 実VMで mailserver を初回通過させ、判定の実出力を確認 | V |
| 108.4 印刷 | PARTIAL | 課題まつり desktop_hw でCUPSのキュー・受入/停止・ジョブを模擬操作。実cupsd/プリンターは未検証 | 実CUPS/印刷機器での確認 | V |
| 109.1 インターネットプロトコルの基礎 | PARTIAL | native tcpdump は用意済み pcap を実 tcpdump で読む（実キャプチャは判定しない）。IP/TCP/UDP の基礎そのものを実測させる課題はない。（旧記述: 4-6, 13-6, 22-6, 29-7, 32-15 読解/診断） | native: loopback で `ss`/`tcpdump`（実装済み）を使い TCP/UDP/ICMP を観測 | N |
| 109.2 永続的ネットワーク設定 | IMPLEMENTED-UNVERIFIED | networkd の .network と適用中の ip/resolvectl を両方判定。dummy NIC のみ。（旧記述: VM netconfig（VM未実行、dummy NIC のみ）、17-1, 13-1 読解） | 実VMで netconfig を初回通過させ、判定の実出力を確認 | V |
| 109.3 ネットワーク障害の切り分け | COVERED-REAL | VM network（2 台でDNS/HTTP 切り分け、実機検証済み）、4-5, 4-6, 13-x | なし | V |
| 109.4 クライアント側 DNS | COVERED-REAL | VM network（名前解決誤りを実機で修正）、13-2、VM netconfig（静的） | なし | V |
| 110.1 セキュリティ管理 | PARTIAL | 16-6（SUID 監査読解）、9-2、VM users（静的） | native: 専用ツリーで SUID/SGID を `find` し実際に落とす／`ulimit`・`last`・`sudo -l` を実機で | N/V |
| 110.2 ホストセキュリティ | PARTIAL | guard（fail2ban）は IU だが、inetd/xinetd・hosts.allow・不要サービス停止は判定しない。（旧記述: 29-19（hosts.allow/deny）、9-3〜9-5、VM firewall（静的）。xinetd/inetd は MISSING） | 実 VM で不要サービス停止と `ss -tlnp` での確認 | V |
| 110.3 暗号によるデータ保護 | COVERED-REAL | native ssh（鍵作成・実効値）、native tls（openssl の証明書・鍵・期限）、18-4（GPG） | LUKS は 20-1, 20-2 が読解のみ（11 参照） | N |

## LPIC-2（201/202、41 行）

| 目標 | 状態 | 根拠・再判定 | 昇格条件／閉じる演習 | 種別 |
|---|---|---|---|---|
| 200.1 リソース使用の測定・障害 | COVERED-REAL | VM performance（実測と設定故障、実機検証済み）、12-1〜12-3, 19-6 | なし | V |
| 200.2 将来のリソース予測 | PARTIAL | 19-6（sar/vmstat 履歴）、12-6, 23-16 | sar/`sadf` で傾向から枯渇日を算出する native 演習 | N |
| 201.1 カーネルコンポーネント | IMPLEMENTED-UNVERIFIED | 実ビルドした .ko を insmod/rmmod/depmod/modprobe し、lsmod・dmesg・/sys パラメータで判定。（旧記述: 14-4, 14-9, 28-16 読解） | 実VMで kbuild を初回通過させ、判定の実出力を確認 | V |
| 201.2 カーネルのコンパイル | PARTIAL | kbuild は out-of-tree モジュールのビルド。カーネル本体の config/make/導入は answers.txt のキーワード照合だけ。（旧記述: 24-13（手順の読解）。native build は gcc/make の小規模ビルドのみで、カーネル設定→ビルド→導入の実操作はない） | VM で `make localmodconfig`→`bindeb-pkg`→導入→再起動（重い。モジュール 1 個のビルドに縮小可） | V |
| 201.3 カーネル実行時管理 | COVERED-REAL | sysctl --system の適用順・実行値・modprobe -c の blacklist/install を判定。（旧記述: 14-5（sysctl 恒久/一時の読解）、14-6, 19-12。VM sysctl は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| 202.1 システム起動のカスタマイズ | COVERED-REAL | VM boot, VM software（systemd unit/timer の作成・故障復旧・再起動）、28-20〜28-23。SysV init は MISSING だが現行 LPI は systemd 中心 | なし | V |
| 202.2 システム復旧 | PARTIAL | grubrescue は GRUB 修復を判定するが、rescue/rd.break/chroot 修復は answers.txt のキーワード照合で、実際のレスキュー起動は判定対象外。（旧記述: 14-3, 14-10, 11-5, 11-8 読解、VM boot（unit 復旧のみ）。レスキュー/emergency、GRUB 復旧、chroot 修復の実操作なし） | VM でスナップショット前提の rescue 起動・fstab 修復・chroot（高リスク） | V |
| 202.3 代替ブートローダ | MISSING | なし（syslinux、PXE、UEFI の扱いは GRUB 読解も含め未出） | 優先度低 | V |
| 203.1 ファイルシステムの運用 | PARTIAL | storage（実機）と mounts（g2実VM確認済み）は ext4 とループのみ。XFS/btrfs の運用は判定しない。（旧記述: VM storage、26-x, 15-x） | ループで ext4/XFS/btrfs の作成・マウント・オプション確認 | N(要root)/V |
| 203.2 ファイルシステムの保守 | PARTIAL | 15-7, 26-4〜26-8 読解（debugfs/e2image 等） | 壊した img に fsck→復旧を native で | N |
| 203.3 ファイルシステムオプション | PARTIAL | 15-8, 23-11, 20-1（autofs・暗号化の読解） | VM autofs で自動マウント・タイムアウト確認 | V |
| 204.1 RAID | PARTIAL | 15-5（/proc/mdstat 読解のみ） | VM で `mdadm` により loop 3 本から RAID1 を作り、1 本を fail→re-add | V |
| 204.2 ストレージアクセス調整 | PARTIAL | 19-14（hdparm/fio 結果の読解）、23-10（multipath/iSCSI 読解）、26-18 | 優先度低 | V |
| 204.3 LVM | COVERED-REAL | ループ上の PV 追加・vgextend・lvextend・resize2fs とデータ sha256 を判定。スナップショットは対象外。（旧記述: 11-4, 15-3, 15-4（手順設計・読解のみ。実 `pvcreate/lvextend` は一度も実行しない）） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| 205.1 基本ネットワーク設定 | IMPLEMENTED-UNVERIFIED | IP/経路/DNS/IPv6 は netconfig、bridge/VLAN/bond は netlink。（旧記述: VM netconfig（VM未実行）、22-8（netns+veth）） | 実VMで netconfig, netlink を初回通過させ、判定の実出力を確認 | V |
| 205.2 高度なネットワーク設定 | IMPLEMENTED-UNVERIFIED | 専用 netns 内で bridge・802.1Q VLAN・active-backup bond（フェイルオーバ実測）・ポリシールーティングを判定。永続化は構文確認のみ。（旧記述: 17-3, 17-4, 22-5, 22-7, 29-1〜29-3（読解/設定例）） | 実VMで netlink を初回通過させ、判定の実出力を確認 | V |
| 205.3 ネットワーク障害対応 | COVERED-REAL | VM network, 13-1〜13-6, 4-5, 4-6, 32-13 | native tcpdump は実装済み | V |
| 206.1 ソースからのビルド | COVERED-REAL | native build（gcc+make のビルド・再構築）、24-11, 24-13, 33-13, 33-14 | なし | N |
| 206.2 バックアップ | COVERED-REAL | native archive, native rsync, VM restore（VM未実行）、23-1〜23-4（restic/borg は読解）。restore は IU、restic/borg は読解 | restic/borg の native 実行は未 | N |
| 206.3 ユーザーへの通知 | PARTIAL | 27-23（wall/mesg 読解） | 優先度低。VM で `wall`、/etc/issue・motd 変更を確認 | V |
| 207.1 DNS サーバ基本設定 | IMPLEMENTED-UNVERIFIED | 専用 named、named-checkconf、rndc reload、dig の権威応答(aa)を判定。（旧記述: 21-1, 21-3（named.conf・dig 読解/検査）。実 BIND は起動しない） | 実VMで dnsserver を初回通過させ、判定の実出力を確認 | V |
| 207.2 DNS ゾーン作成・保守 | IMPLEMENTED-UNVERIFIED | ゾーン検査・シリアル増加・稼働中 SOA との一致・A/AAAA/CNAME/MX/TXT/PTR を判定。（旧記述: 21-2（SOA・ゾーンファイル読解）） | 実VMで dnsserver を初回通過させ、判定の実出力を確認 | V |
| 207.3 DNS サーバの保護 | PARTIAL | dnsserver は AXFR の allow-transfer 制限のみ判定。TSIG・chroot・DNSSEC は対象外。（旧記述: 21-3（DNSSEC 基礎のみ）） | VM で allow-transfer/chroot/TSIG の確認 | V |
| 208.1 Apache 基本設定 | IMPLEMENTED-UNVERIFIED | 専用 Apache の vhost・.htaccess（外して 404 になることまで確認）・Basic 認証・301 書換・vhost 別ログを実 HTTP で判定。（旧記述: 21-15（httpd.conf/VirtualHost/mod_rewrite の読解）） | 実VMで apache を初回通過させ、判定の実出力を確認 | V |
| 208.2 Apache HTTPS | PARTIAL | apache モジュールは HTTP のみで mod_ssl を扱わない。TLS は native tls と webstack(Nginx)。（旧記述: native tls（openssl）、VM webstack（Nginx の TLS）、20-14。Apache の mod_ssl は読解止まり） | VM で Apache+自己署名 TLS | V |
| 208.3 Squid | PARTIAL | 21-16（設定読解） | 優先度低 | V |
| 208.4 Nginx | COVERED-REAL | VM webstack（Nginx リバースプロキシ・TLS・502 修復・再起動後確認）、21-14 | なし | V |
| 209.1 Samba | IMPLEMENTED-UNVERIFIED | 専用 smbd に smbclient で匿名/誤パス/非メンバ/メンバを試し、所有者・モードまで判定。（旧記述: 17-5, 19-16（smb.conf・testparm 相当の読解）） | 実VMで samba を初回通過させ、判定の実出力を確認 | V |
| 209.2 NFS サーバ | IMPLEMENTED-UNVERIFIED | exportfs -v・nfs4 実マウント・soft/timeo・fstab(_netdev,nofail)・root_squash を 2 台構成で判定。（旧記述: 17-5, 15-8, 23-11（exports・fstab の読解）） | 実VMで fileshare を初回通過させ、判定の実出力を確認 | V |
| 210.1 DHCP | PARTIAL | 21-4, 21-5（dnsmasq/ISC dhcpd 設定とリース読解） | netns で dnsmasq DHCP を動かしリースを取得 | N(要root)/V |
| 210.2 PAM 認証 | IMPLEMENTED-UNVERIFIED | 専用 PAM サービスに pamtester で faillock・access.conf・listfile・pwquality を実認証して判定。（旧記述: 16-11（faillock/pwquality の読解）） | 実VMで pam を初回通過させ、判定の実出力を確認 | V |
| 210.3 LDAP クライアント | PARTIAL | ldap は slapd 側のみ。SSSD/nsswitch/getent によるクライアント側は判定しない。（旧記述: 21-6, 21-7（LDIF・ldapsearch・SSSD 読解）） | VM 2 台（LDAP サーバ+クライアント）で `getent passwd` | V |
| 210.4 OpenLDAP サーバ | IMPLEMENTED-UNVERIFIED | 専用 slapd: DIT 7 エントリ・bind(err 49)・匿名の userPassword 拒否・ACL・slapcat 突合。（旧記述: 21-6（LDIF のみ）） | 実VMで ldap を初回通過させ、判定の実出力を確認 | V |
| 211.1 メールサーバ | PARTIAL | 21-8, 21-9, 21-10 読解 | VM Postfix のローカル配送・キュー | V |
| 211.2 メール配送管理 | PARTIAL | mailserver は alias とキューまで。仮想ドメイン・procmail/sieve は対象外。（旧記述: 21-9（キュー・ログ読解）。procmail/sieve は MISSING） | VM で alias・仮想ドメイン・`postqueue` | V |
| 211.3 メールボックスアクセス | PARTIAL | 21-11（Dovecot 設定読解） | VM Dovecot で IMAPS ログイン | V |
| 212.1 ルータ設定 | PARTIAL | netlink は経路制御と bridge まで。ip_forward+MASQUERADE の NAT は判定しない。（旧記述: 22-5, 22-7, 22-8, 17-2（NAT・転送の読解/設定例）。VM firewall は静的） | netns で 3 ノード構成、`ip_forward`+MASQUERADE を実適用 | N(要root)/V |
| 212.2 FTP サーバ | COVERED-REAL | VM ftp: vsftpd専用インスタンスで認証・匿名/リスト外拒否・chroot・PASV・チェックサム付き往復転送・resetを確認。[実出力](vm_verification/g8-ftp.md) | FTPSは発展課題で判定外 | V |
| 212.3 SSH | COVERED-REAL | native ssh, VM ssh（専用 sshd・認証・転送・権限障害を実機検証）、20-6〜20-9, 34-x。VM sshd（堅牢化）は実装済み | なし（sshd 堅牢化は実装済み） | N/V |
| 212.4 セキュリティタスク | IMPLEMENTED-UNVERIFIED | fail2ban-regex・実際の ban/unban・findtime、auditd の auditctl/ausearch/aureport を判定。nmap は未判定。（旧記述: 16-12（fail2ban 読解）、9-x、16-1〜16-3。nmap は 4-x/32-x に名前のみ。侵入検知（auditd/ausearch は読解 19-13）） | 実VMで guard を初回通過させ、判定の実出力を確認 | V |
| 212.5 OpenVPN | PARTIAL | 20-5（server.conf/client.ovpn 読解）、20-3, 20-4（WireGuard 読解） | VM 2 台でトンネル確立（native でも netns で可能） | V |

## LFCS（34 行）

| 目標 | 状態 | 根拠・再判定 | 昇格条件／閉じる演習 | 種別 |
|---|---|---|---|---|
| 運用: カーネルパラメータ（一時・恒久） | COVERED-REAL | sysctl の一時・恒久と適用順を判定。（旧記述: 14-5 読解、14-6。VM sysctl は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| 運用: プロセスとサービスの診断・管理 | COVERED-REAL | VM software, VM boot, VM performance, 3-5, 7-1〜7-3 | なし | V |
| 運用: コマンド実行ジョブの管理・スケジュール | COVERED-REAL | native cron（実環境で job.sh を最小環境・多重起動で実行）と VM software の systemd timer（実機）。at は未実習。（旧記述: VM software（systemd timer 実機）、6-7, 23-15 読解。cron は実装済み） | native cron（実装済み）、`at` | N |
| 運用: パッケージ・リポジトリ | COVERED-REAL | VM packages（deb）、VM osupdate（静的、署名付きローカル repo）。RPM は MISSING（102.5 参照） | RPM 系は別途 | V |
| 運用: ハード/OS/FS 障害からの復旧 | PARTIAL | boot（実機）は unit 復旧のみ。grubrescue は IU だがレスキュー起動は判定対象外。（旧記述: 14-3, 14-10, 11-8 読解、VM boot（unit のみ）、VM restore（静的）） | VM rescue 実習（202.2 参照） | V |
| 運用: libvirt による VM 管理 | PARTIAL | libvirt モジュールは virsh の test:///default（モック）ドライバで、実ハイパーバイザのドメイン・ディスク・ブリッジは扱わない。実 VM 通過後も PA のまま。（旧記述: 22-1〜22-3（virsh XML・qemu-img 読解）。実 virsh は不可（本機に qemu なし）） | ネスト仮想化できる環境でのみ | V |
| 運用: コンテナエンジンの設定と管理 | COVERED-REAL | docker は native 実習（実 daemon が必要）。podman rootless/Quadlet は IU(podman)。（旧記述: native docker（構築・故障調査・再作成・volume 保持。ホストに daemon が必要）、5-x, 7-5〜7-7, 22-15。podman は 18-10 の読み替え読解のみ） | podman の rootless 実行 | N(要daemon) |
| 運用: SELinux の強制 | IMPLEMENTED-UNVERIFIED | RHEL系 VM 限定。Enforcing のまま fcontext・restorecon・setsebool -P・AVC なしを判定。（旧記述: 16-1, 16-2（モード・コンテキスト・AVC 読解）。Ubuntu では SELinux 非標準。実操作ゼロ） | 実VMで selinux を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| ネットワーク: IPv4/IPv6・ホスト名解決 | IMPLEMENTED-UNVERIFIED | IPv4/IPv6 の静的設定と resolvectl を判定。ホスト名解決は network（実機）。（旧記述: VM netconfig（VM未実行）、VM network（名前解決は実機）、17-7） | 実VMで netconfig を初回通過させ、判定の実出力を確認 | V |
| ネットワーク: 時刻サーバでの時刻同期 | IMPLEMENTED-UNVERIFIED | timesyncd の実効 NTP を判定。（旧記述: 17-6, 19-15, 21-16。VM timesync は実装済み） | 実VMで timesync を初回通過させ、判定の実出力を確認 | V |
| ネットワーク: 監視・障害対応 | COVERED-REAL | VM network, 13-1〜13-6, 32-12, 32-13, 32-16 | tcpdump の native 実習は実装済み | V |
| ネットワーク: OpenSSH サーバ/クライアント | COVERED-REAL | native ssh, VM ssh, 34-x | sshd 堅牢化は実装済み | N/V |
| ネットワーク: パケットフィルタ・ポートリダイレクト・NAT | PARTIAL | firewall（IU）は nft の input フィルタのみ。ポートリダイレクト・NAT は判定しない。（旧記述: VM firewall（nft 実適用。VM未実行）、17-2, 22-5, 22-7） | 実 VM で firewall 検証、NAT/DNAT を netns で | V |
| ネットワーク: 静的ルーティング | IMPLEMENTED-UNVERIFIED | 静的経路 2 本と ip route get による経路選択を判定。（旧記述: VM netconfig（VM未実行）、13-1） | 実VMで netconfig を初回通過させ、判定の実出力を確認 | N(要root)/V |
| ネットワーク: ブリッジ・ボンディング | IMPLEMENTED-UNVERIFIED | bridge と active-backup bond の切替を実測。（旧記述: 17-3, 22-8 読解/設定例） | 実VMで netlink を初回通過させ、判定の実出力を確認 | V |
| ネットワーク: リバースプロキシ・ロードバランサ | PARTIAL | VM webstack（Nginx 実機）、21-12（HAProxy）, 21-13（keepalived）, 21-14 は読解 | VM で HAProxy 2 backend のヘルスチェック切替 | V |
| ストレージ: LVM | COVERED-REAL | ループ上の LVM 拡張とデータ保持。（旧記述: 11-4, 15-3, 15-4） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| ストレージ: 仮想ファイルシステムの設定 | PARTIAL | 14-6（/proc,/sys 読解）、26-21（bind/tmpfs/overlay 読解） | native 可能: tmpfs/bind/overlay を unshare -m 内で実マウント | N(要root)/V |
| ストレージ: FS の作成・管理・障害対応 | PARTIAL | VM storage（inode 枯渇）、15-7, 26-x。VM mounts は実装済み | 104.1 / 104.3 参照 | V |
| ストレージ: リモート FS・ネットワークブロックデバイス | IMPLEMENTED-UNVERIFIED | NFSv4 のみ。NBD/iSCSI は対象外。（旧記述: 15-8, 17-5, 23-10 読解。実 NFS/iSCSI/NBD なし） | 実VMで fileshare を初回通過させ、判定の実出力を確認 | V |
| ストレージ: スワップ | COVERED-REAL | swapfile の mkswap/swapon/fstab とサイズ判定。（旧記述: 15-6（swapfile+swappiness 設定の読解）、26-16） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| ストレージ: オートマウンタ | PARTIAL | 23-11（auto.master 読解） | VM autofs | V |
| ストレージ: ストレージ性能の監視 | PARTIAL | VM performance（CPU/IO 中心）、12-3, 19-14, 32-11 | iostat/fio を VM で実行し原因特定 | V |
| 基本コマンド: 基本 Git | COVERED-REAL | native git, 30-1〜30-28 | なし | N |
| 基本コマンド: サービスの作成・設定・障害対応 | COVERED-REAL | VM software, VM boot, 7-3, 28-20〜28-23 | なし | V |
| 基本コマンド: サービス・性能の監視と障害対応 | COVERED-REAL | VM performance, 12-1〜12-4, 27-x | なし | V |
| 基本コマンド: アプリ・サービス固有の制約 | COVERED-REAL | systemd の MemoryMax/LimitNOFILE をドロップインで直し、実プロセスの /proc/PID/limits と cgroup memory.max で判定。（旧記述: 16-8, 16-9, 18-2, 27-13（ulimit/cgroup 読解）。VM limits は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| 基本コマンド: ディスク容量の問題 | COVERED-REAL | VM storage（inode 枯渇）、11-3, 11-7, 3-8, 15-10 | なし | V |
| 基本コマンド: SSL 証明書 | COVERED-REAL | native tls, 13-3, 20-10〜20-12, 20-16 | certbot/ACME の実動作は読解のみ | N |
| ユーザー: ローカルユーザー・グループ | IMPLEMENTED-UNVERIFIED | ユーザー・グループ・sudoers の実状態。（旧記述: VM users（VM未実行）、7-4, 28-1〜28-5） | 実VMで users を初回通過させ、判定の実出力を確認 | V |
| ユーザー: 個人/システム全体の環境プロファイル | PARTIAL | 28-19, 3-4, 24-16（作業フォルダ内の編集のみ） | `su -l` で反映確認（105.1 参照） | V |
| ユーザー: ユーザー資源制限 | PARTIAL | limits は systemd サービスの制限。ユーザー対象の limits.conf/ulimit/PAM は判定しない。（旧記述: 16-8（limits.conf/ulimit 読解）。VM limits は実装済み） | VM limits（実装済み） | V |
| ユーザー: ACL | COVERED-REAL | VM permissions（ACL、実機検証済み）、12-7, 16-4 | なし | V |
| ユーザー: LDAP ユーザー・グループ | IMPLEMENTED-UNVERIFIED | slapd 側の DIT/ACL/bind。クライアント側 NSS は対象外。（旧記述: 21-6, 21-7 読解） | 実VMで ldap を初回通過させ、判定の実出力を確認 | V |

## RHCSA EX200（61 行、信頼度低、上記注意参照）

| 目標 | 状態 | 根拠・再判定 | 昇格条件／閉じる演習 | 種別 |
|---|---|---|---|---|
| R1 シェルでコマンド実行 | COVERED-REAL | native shell | なし | N |
| R2 入出力リダイレクト | COVERED-REAL | native shell, 2-1, EX-3 | なし | N |
| R3 grep と正規表現 | COVERED-REAL | 2-2〜2-4, 24-1 | なし | N |
| R4 SSH でリモート接続 | COVERED-REAL | native ssh, VM ssh | なし | N/V |
| R5 マルチユーザーターゲットでのログイン・ユーザー切替 | PARTIAL | 27-20（runuser/sulogin 読解） | VM users で `su -`/`sudo -i`（静的のみ） | V |
| R6 tar/gzip/bzip2 | COVERED-REAL | native archive, 4-1, 4-2 | なし | N |
| R7 テキスト編集 | COVERED-REAL | native vim, 31-x | なし | N |
| R8 ファイル/ディレクトリ操作 | COVERED-REAL | 1-2〜1-8, native find | なし | N |
| R9 ハード/ソフトリンク | COVERED-REAL | 3-3 | なし | N |
| R10 標準パーミッションの確認・変更 | COVERED-REAL | 3-1, 3-2, VM permissions | なし | N |
| R11 ドキュメント（man/info/doc） | PARTIAL | 29-17, 29-18（索引・出力読解） | 優先度低 | N |
| R12 RPM リポジトリへのアクセス設定 | IMPLEMENTED-UNVERIFIED | 署名付き .repo（gpgcheck/repo_gpgcheck/gpgkey）を実判定。RHEL系 VM 限定。（旧記述: 29-13（yum.repos.d の対応づけ読解のみ）） | 実VMで dnf を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R13 RPM の導入・削除 | IMPLEMENTED-UNVERIFIED | dnf install/upgrade/history undo と rpm -V を判定。（旧記述: 17-8（rpm 記録の読解）。実 rpm/dnf は動かさない） | 実VMで dnf を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R14 Flatpak リポジトリ設定 | MISSING | 18-6 は権限出力の監査のみで repo 設定は扱わない | `flatpak remote-add` 実習 | N/V |
| R15 Flatpak の導入・削除 | MISSING | 同上 | `flatpak install/uninstall` | N/V |
| R16 if/test/[ ] | COVERED-REAL | 6-2, 24-7 | なし | N |
| R17 ループ | COVERED-REAL | 6-3, 24-7 | なし | N |
| R18 スクリプト引数 $1/$2 | COVERED-REAL | 6-1, 6-4, 17-11 | なし | N |
| R19 コマンド出力の利用 | COVERED-REAL | 6-x, 24-7 | なし | N |
| R20 通常の起動・再起動・停止 | PARTIAL | VM boot（再起動を含む検証）。shutdown/reboot 手順自体の課題なし | VM で `systemctl reboot` 後の確認（boot で近似） | V |
| R21 特定ターゲットへの手動起動 | PARTIAL | 14-12, 28-24 読解 | VM で `systemctl isolate`/カーネル引数 `systemd.unit=` | V |
| R22 起動を中断してアクセス回復（rd.break） | PARTIAL | grubrescue は answers.txt に rd.break 等のキーワードを書かせるだけ（実際の rd.break は未実習）。（旧記述: 14-3（emergency でのパスワード・fstab 修正の読解）） | VM で GRUB 編集→rd.break→root PW 変更（SELinux relabel 含む） | V |
| R23 CPU/メモリ重いプロセスの特定・停止 | COVERED-REAL | 3-5, VM performance, 12-1, 12-2 | なし | N/V |
| R24 プロセスのスケジューリング優先度 | PARTIAL | 27-8, 16-9 読解 | 103.6 参照 | N |
| R25 tuned プロファイル管理 | IMPLEMENTED-UNVERIFIED | tuned-adm active/verify と実 sysctl 値。RHEL 系を前提とするが tuned は Debian でも導入可。（旧記述: `tuned` は 2 回言及（stage2）が操作課題ではない） | 実VMで tuned を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R26 ログとジャーナルの検索 | COVERED-REAL | 7-2, VM software（journalctl で設定故障を特定） | なし | N/V |
| R27 ジャーナルの永続化 | COVERED-REAL | /var/log/journal の永続化と実書込みを判定。（旧記述: 23-14（読解）。VM journald は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R28 ネットワークサービスの開始・停止・状態 | COVERED-REAL | VM software, VM webstack, 7-1 | なし | V |
| R29 システム間の安全なファイル転送 | COVERED-REAL | native rsync, native ssh, VM ssh（scp/rsync 実機） | なし | N/V |
| R30 GPT ディスクのパーティション作成・一覧・削除 | PARTIAL | 15-1, 26-2, 26-3 読解/dry-run | ループデバイスで `parted/sgdisk` を実操作 | N(要root)/V |
| R31 PV の作成・削除 | COVERED-REAL | pvcreate（2 本目の PV）を実判定。（旧記述: 15-3, 11-4 読解） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R32 PV を VG へ割り当て | COVERED-REAL | vgextend を判定。（旧記述: 同上） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R33 LV の作成・削除 | PARTIAL | mounts は LV 拡張が中心で、LV の新規作成・削除は setup 側。。（旧記述: 同上） | 同上 | V |
| R34 UUID/ラベルでの起動時マウント | COVERED-REAL | UUID 指定の fstab 行を findmnt で判定。（旧記述: 11-2, 26-9, 26-20 読解。VM mounts は実装済み） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R35 データを失わずにパーティション/LV/swap を追加 | COVERED-REAL | 稼働データの sha256 を保ったまま拡張。（旧記述: 15-6, 15-4 読解） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R36 VFAT/ext4/XFS の作成・マウント・利用 | PARTIAL | ext4 のみ。XFS（mkfs.xfs/xfs_growfs）と VFAT は未実習。（旧記述: VM storage（ext4 のみ実機）。XFS（`mkfs.xfs`）と VFAT は未出） | XFS/VFAT の mkfs・mount・`xfs_growfs` | V |
| R37 NFS 共有のマウント・アンマウント | IMPLEMENTED-UNVERIFIED | NFSv4 の実マウントと書き込み。（旧記述: 15-8, 17-5 読解） | 実VMで fileshare を初回通過させ、判定の実出力を確認 | V |
| R38 autofs 設定 | PARTIAL | 23-11 読解 | VM autofs | V |
| R39 既存 LV の拡張 | COVERED-REAL | lvextend + resize2fs（FS が LV の 95% 以上）を判定。（旧記述: 11-4, 15-4 読解） 実出力: [g2記録](vm_verification/g2-system.md)。 | 初回通過確認済み。再起動の未検証範囲はg2記録を参照 | V |
| R40 ファイルパーミッション問題の診断・修正 | COVERED-REAL | VM permissions, 3-x, 11-6, 12-7 | なし | N/V |
| R41 at/cron/systemd timer | PARTIAL | native cron は自前パーサ、timer は VM software 実機。at は未実習。（旧記述: VM software（timer は実機）。cron/at は読解（6-7, 23-15）。native cron は実装済み） | native cron（実装済み）、at | N/V |
| R42 サービスの起動・停止・自動起動 | COVERED-REAL | VM software, VM boot, 7-1 | なし | V |
| R43 既定ターゲットの設定 | PARTIAL | 14-12, 28-24 読解 | VM で `set-default` と再起動 | V |
| R44 時刻サービスのクライアント設定 | PARTIAL | RHCSA は chrony。timesync は systemd-timesyncd のみで chronyc を判定しない。（旧記述: 17-6, 19-15 読解。VM timesync は実装済み） | VM timesync（実装済み） | V |
| R45 Red Hat CDN・リモートリポジトリ・ローカルメディアからの導入/更新 | PARTIAL | dnf はローカル repo のみ。subscription-manager/CDN は未実習。（旧記述: `subscription-manager` はコーパスに出ない。VM osupdate は apt（Debian 系）） | RHEL 系: 購読登録（Developer Subscription）と `dnf update`、ローカル ISO repo | V（RHEL 系） |
| R46 ブートローダの変更 | PARTIAL | grubrescue は Debian 系 grub-mkconfig。grubby/grub2-mkconfig は未実習。（旧記述: 14-1（GRUB 設定読解）。`grubby`/`grub2-mkconfig` は MISSING） | VM で GRUB 引数変更→再起動 | V |
| R47 IPv4/IPv6 アドレス設定 | PARTIAL | netconfig は systemd-networkd。RHCSA が求める NetworkManager(nmcli) は判定しない。（旧記述: VM netconfig（VM未実行）、17-1, 29-7。`nmcli` による永続化は読解） | 実 VM + RHEL 系 NetworkManager | V |
| R48 ホスト名解決の設定 | COVERED-REAL | VM network, VM netconfig（静的）、13-2 | なし | V |
| R49 ネットワークサービスの自動起動 | COVERED-REAL | VM software/webstack（enable＋再起動後確認） | なし | V |
| R50 firewalld/firewall-cmd によるアクセス制限 | IMPLEMENTED-UNVERIFIED | permanent を --reload で再読込しても実接続で許可・reject を確認。RHEL系 VM 限定。（旧記述: 19-10（firewall-cmd 出力の読解）、VM firewall は nftables（VM未実行）で firewalld ではない） | 実VMで firewalld を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R51 ローカルユーザーの作成・削除・変更 | IMPLEMENTED-UNVERIFIED | ユーザー作成・シェル・UID/GID 維持を判定。（旧記述: VM users（VM未実行）、7-4, 28-1） | 実VMで users を初回通過させ、判定の実出力を確認 | V |
| R52 パスワード変更・有効期限 | PARTIAL | users は chage -l でアカウントが期限切れでないことを見るだけ。有効期限の設定課題ではない。（旧記述: 16-11（chage の読解）、VM users（静的）） | `chage -l/-M` を実 VM で | V |
| R53 ローカルグループとメンバーシップ | IMPLEMENTED-UNVERIFIED | 補助グループとメンバーシップ。（旧記述: VM users（静的）、28-2） | 実VMで users を初回通過させ、判定の実出力を確認 | V |
| R54 sudo 設定 | IMPLEMENTED-UNVERIFIED | sudoers(0440/visudo) と sudo -l による最小権限。（旧記述: VM users（静的。`sudo -n -l` 判定）、9-4, 16-10, 28-6） | 実VMで users を初回通過させ、判定の実出力を確認 | V |
| R56 既定パーミッション（umask） | PARTIAL | 3-x, 28-19 に umask 言及。独立した実習なし | 専用ユーザーで umask を変えて作成ファイルのモード確認 | N |
| R57 鍵認証 SSH | COVERED-REAL | native ssh, VM ssh, 34-5〜34-8 | なし | N/V |
| R58 SELinux enforcing/permissive | IMPLEMENTED-UNVERIFIED | getenforce と /etc/selinux/config を判定。RHEL系 VM 限定。（旧記述: 16-1 読解のみ。Ubuntu では動かせない） | 実VMで selinux を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R59 SELinux のファイル/プロセスコンテキスト | IMPLEMENTED-UNVERIFIED | httpd_t での実行と restorecon -Fn による文脈判定。（旧記述: 16-1, 16-2 読解（`ls -Z`/`ps -Z` の出力）） | 実VMで selinux を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R60 既定コンテキストの復元（restorecon） | IMPLEMENTED-UNVERIFIED | 永続 fcontext + restorecon が差分ゼロ。（旧記述: 16-1, 28-7 に名前と読解のみ） | 実VMで selinux を初回通過させ、判定の実出力を確認 | V（RHEL 系） |
| R61 SELinux ポートラベル（semanage port） | PARTIAL | selinux モジュールは fcontext とブール値。semanage port は判定しない。（旧記述: 16-1 に `semanage` 名前あり、読解のみ） | RHEL 系 VM で非標準ポートの httpd を `semanage port -a` | V（RHEL 系） |
| R62 SELinux ブール値（setsebool） | IMPLEMENTED-UNVERIFIED | httpd_can_network_connect の現在値と -P 永続化を判定。（旧記述: `setsebool` はコーパスに出ない） | 実VMで selinux を初回通過させ、判定の実出力を確認 | V（RHEL 系） |

## 集計（実VM再開後）

| 試験 | 行数 | COVERED-REAL | IMPLEMENTED-UNVERIFIED | PARTIAL | MISSING |
|---|---|---|---|---|---|
| LPIC-1 | 42 | 16 | 7 | 16 | 3 |
| LPIC-2 | 41 | 10 | 11 | 19 | 1 |
| LFCS | 34 | 16 | 8 | 10 | 0 |
| RHCSA | 61 | 28 | 12 | 19 | 2 |
| 合計（試験間の重複行を含む） | 178 | 70 | 38 | 64 | 6 |

実VM通過記録のあるg2の13行とFTPを反映。印刷は模擬実習のためPARTIAL。未実行モジュールは昇格させていない。

LFCS/RHCSA/LPIC は重複が大きい（シェル・ssh・パーミッション・systemd・ストレージ・ネットワーク）ので、合計を独立した目標数として扱わないこと。

### モジュール別: 再開前の昇格候補（履歴）

以下は第2版時点の履歴。mounts/sysctl/journald/limitsは上の現行表へ反映済み。第2版のIMPLEMENTED-UNVERIFIED の行を、必要なモジュール別に数えた。複数モジュールが必要な行は、各モジュールに数える（その行は全部が通るまで昇格しない: 205.1 は netconfig と netlink）。昇格は「判定が実機で正しく動く」ことが前提で、判定の誤りが見つかればモジュールを直してから再実行になる。

| モジュール | 昇格する行数 | 行 |
|---|---|---|
| mounts | 9 | LPIC-1 104.3、LPIC-2 204.3、LFCS ストレージ: LVM、LFCS ストレージ: スワップ、RHCSA R31 PV の作成・削除、RHCSA R32 PV を VG へ割り当て、RHCSA R34 UUID/ラベルでの起動時マウント、RHCSA R35 データを失わずにパーティション/LV/swa、RHCSA R39 既存 LV の拡張 |
| selinux | 5 | LFCS 運用: SELinux の強制、RHCSA R58 SELinux enforcing/perm、RHCSA R59 SELinux のファイル/プロセスコンテキ、RHCSA R60 既定コンテキストの復元（restorecon、RHCSA R62 SELinux ブール値（setsebool |
| users | 5 | LPIC-1 107.1、LFCS ユーザー: ローカルユーザー・グループ、RHCSA R51 ローカルユーザーの作成・削除・変更、RHCSA R53 ローカルグループとメンバーシップ、RHCSA R54 sudo 設定 |
| netconfig | 4 | LPIC-1 109.2、LPIC-2 205.1、LFCS ネットワーク: IPv4/IPv6・ホスト名解決、LFCS ネットワーク: 静的ルーティング |
| dnf | 3 | LPIC-1 102.5、RHCSA R12 RPM リポジトリへのアクセス設定、RHCSA R13 RPM の導入・削除 |
| fileshare | 3 | LPIC-2 209.2、LFCS ストレージ: リモート FS・ネットワークブロックデ、RHCSA R37 NFS 共有のマウント・アンマウント |
| netlink | 3 | LPIC-2 205.1、LPIC-2 205.2、LFCS ネットワーク: ブリッジ・ボンディング |
| timesync | 3 | LPIC-1 107.3、LPIC-1 108.1、LFCS ネットワーク: 時刻サーバでの時刻同期 |
| dnsserver | 2 | LPIC-2 207.1、LPIC-2 207.2 |
| ldap | 2 | LPIC-2 210.4、LFCS ユーザー: LDAP ユーザー・グループ |
| sysctl | 2 | LPIC-2 201.3、LFCS 運用: カーネルパラメータ（一時・恒久） |
| apache | 1 | LPIC-2 208.1 |
| firewalld | 1 | RHCSA R50 firewalld/firewall-cmd |
| grubrescue | 1 | LPIC-1 102.2 |
| guard | 1 | LPIC-2 212.4 |
| journald | 1 | RHCSA R27 ジャーナルの永続化 |
| kbuild | 1 | LPIC-2 201.1 |
| limits | 1 | LFCS 基本コマンド: アプリ・サービス固有の制約 |
| mailserver | 1 | LPIC-1 108.3 |
| pam | 1 | LPIC-2 210.2 |
| samba | 1 | LPIC-2 209.1 |
| tuned | 1 | RHCSA R25 tuned プロファイル管理 |
| libvirt | 0 | test:///default のモックのため、実 VM で通っても LFCS libvirt 行は PARTIAL のまま |

全モジュールが通った場合の最大: 行ベースで IMPLEMENTED-UNVERIFIED 51 行がすべて COVERED-REAL になり、COVERED-REAL は 107 行になる（重複行を含む延べ数）。最初に実機で回す価値が高い順は mounts（9）、users（5）、selinux（5、RHEL 系 VM が必要）、netconfig（4）。

### 28 の未実行モジュールの判定の質（コードを読んだ所見）

- 強い（実プロセス・実通信・実状態を判定）: sshd（sshd -T、実ログイン、ProxyJump、ログ確認）、dnsserver、mailserver（実 SMTP）、fileshare（nfs4 実マウント）、apache、samba、pam（pamtester）、ldap、guard（実 ban と ausearch）、netlink（実 ping・bond 切替）、limits、journald、sysctl、timesync、mounts、netconfig、restore、osupdate、podman、users、firewall、firewalld、selinux、dnf。
- 弱い／部分的: grubrescue（grub.cfg・MBR は実判定だが、実際の再起動と rd.break は判定せず、answers.txt はキーワード照合）、kbuild（ビルドと insmod は実判定だが、手順の answers.txt はキーワード照合）、libvirt（モックドライバで実ハイパーバイザではない。ドメインは接続ごとに消えるため session.virsh を再生して判定）、samba の testparm 警告は表示だけで失敗にならない。
- 共通の未確認点: 全モジュールが「再起動後も保たれるか」を実際に再起動して確かめてはいない（fstab・unit の内容は静的に確認）。実機で最初に壊れやすいのは、sleep の長さ・出力文字列の言語依存・apt/dnf のパッケージ名。

## 実質的な未達領域（第 2 版。重複排除・優先順）

1. **検証作業そのもの**。28 モジュールは実 VM で一度も走っていない。新規実装より、`labs/vm/FIRST_RUN.md` に沿った初回通過が最も得点が大きい（上の表）。RHEL 系の 3 モジュールは Rocky/Alma の VM が別途必要で、環境も未整備（`labs/vm/RHEL.md`）。
2. **ブート・レスキューの実操作**。再起動を伴う GRUB 引数変更・rd.break・emergency/rescue・`systemctl isolate/set-default`（101.2, 101.3, 202.2, R21, R22, R43）。grubrescue はループ上の導入までで、実起動は判定対象外。
3. **ストレージの残り**。GPT 作成、XFS/VFAT、RAID(mdadm)、autofs、スナップショット、btrfs/ZFS（104.1, 203.x, 204.1, R30, R36, R38）。mounts は ext4+LVM+swap+fstab のみ。
4. **NAT・DHCP・ルータ・VPN**。ip_forward+MASQUERADE、DHCP サーバ、WireGuard/OpenVPN の実トンネル（212.1, 210.1, 212.5, LFCS ファイアウォール NAT）。
5. **メール・DNS・ディレクトリの残り**。Dovecot、procmail/sieve、DNSSEC/TSIG、SSSD クライアント、Squid、FTP（211.2, 211.3, 207.3, 210.3, 208.3, 212.2）。
6. **RHEL 系固有**。subscription-manager、grubby、NetworkManager(nmcli)、chrony、Flatpak（R14, R15, R44, R45, R46, R47）。Ubuntu 基準のままでは閉じない。
7. **周辺・低優先**。X11/デスクトップ/アクセシビリティ（106.x）、印刷（108.4）、SysV init、代替ブートローダ（202.3）。手動確認項目として扱うのが妥当。

## 構造的な所見

- 501 問の大半（Stage 11〜29）は採取済み出力・設定例を読む方式のため、「実システムに対する操作」の目標では PARTIAL にしか数えない。実ツールを動かして成果物を検査するのは Stage 1〜10 と 24〜25、30〜34 の一部、23 本の native 実習、9 つの実機検証済み VM モジュールだけ。
- 判定コードが強くても、未実行は未実行。今回の再判定は「コードを読んで判定が弱くない」ことの確認であり、「動く」ことの確認ではない。
- 「名前が出る」ことと「操作させる」ことは別。例: `lynis`、`cupsd`、`xinetd`、`bluetoothctl`、`pactl`、`aide` はコーパスに一度も出ない。
- このリポジトリは Ubuntu/Debian 前提のため、RHCSA は構造的に満たせない。Rocky/Alma の VM が用意されるまで、RHCSA の RHEL 固有行は IMPLEMENTED-UNVERIFIED か PARTIAL のまま。

---

# 第 2 部: 試験範囲外の実務領域（働く Linux ユーザー／小規模サーバ運用者向け）

調査方法: 501 ミッション（`engine.runner.REGISTRY` から ID とタイトルを列挙）、`curriculum/toolbox_catalog.py`、native 実習 23 本、VM モジュール 37 本（`labs/vm/guest/modules/`）をキーワードと実コードで照合。判定基準は第 1 部と同じ。Stage 11〜29 の多くは「採取済み出力・設定ファイルを読む」方式なので、実ツールを動かさない限り PARTIAL とする。一度も実機でツールを動かす実習がない領域は、ミッションがあっても COVERED-REAL にしない。

## 領域別判定

| 領域 | 状態 | 根拠（ID・モジュール） | 実際に足りないもの |
|---|---|---|---|
| Kubernetes / kubectl 基礎 | PARTIAL | 22-10（kubectl get/describe/logs の出力読解）、22-11（Deployment/Service/Ingress の YAML）、22-12（Helm values）、32-4（yq）。クラスタは起動しない | 実クラスタでの apply/rollout/describe。kind か k3s が必要 |
| Ansible / IaC | PARTIAL | 18-13, 18-14（インベントリ・playbook・`--check` 出力の読解）、22-9（Vagrantfile）。ansible は一度も実行しない | `ansible-playbook -c local --check` の実行と冪等性の実測 |
| Terraform | PARTIAL | 22-13（plan/apply 出力・state・drift の読解のみ） | init/plan/apply の実行。local provider だけなら無権限・オフラインで可能 |
| CI/CD | PARTIAL | 22-16（GitHub Actions の YAML 読解と秘密情報の扱い）、native git（CI ではない） | パイプラインを実際に回す課題はない。ローカルでの git hook・act などもない |
| 監視（Prometheus・node_exporter・Grafana・ログ） | PARTIAL | 22-14（scrape 設定・alert rule・PromQL の読解）、12-1〜12-4, 19-6（性能の読解）、VM performance は実機だが CPU/IO の切り分け、journald は IMPLEMENTED-UNVERIFIED。Loki/Alertmanager は MISSING | node_exporter と Prometheus を実際に起動し、メトリクスを取得し、alert を発火させる課題 |
| PostgreSQL / MariaDB / Redis のサーバ運用とバックアップ | PARTIAL | 23-5〜23-9（mysqldump・GRANT・pg_dump/pg_restore・pg_hba・Redis 永続化の読解）。native sqlite（サーバではない）は COVERED-REAL。MariaDB は 2 行の言及のみ | DB サーバを実際に起動し、バックアップと復元を判定する課題。PostgreSQL は initdb/pg_ctl を非特権で動かせる |
| WireGuard / OpenVPN | PARTIAL | 20-3, 20-4（wg0.conf・wg show の読解）、20-5（OpenVPN 設定の読解） | 実トンネル（2 ノード）と疎通確認 |
| HAProxy / リバースプロキシ | PARTIAL（Nginx の部分は COVERED-REAL） | VM webstack（Nginx リバースプロキシ・TLS・502 修復、実機検証済み）。HAProxy は 21-12（読解）、21-13（keepalived 読解） | HAProxy のバックエンド切替・ヘルスチェック・ACL の実動作 |
| バックアップツール（borg / restic） | PARTIAL | 23-1（restic）、23-2（borg）、23-3（rsync --link-dest）は読解。native archive・rsync は COVERED-REAL。VM restore は IMPLEMENTED-UNVERIFIED | restic/borg のローカルリポジトリを実際に作り、復元と prune を検査する課題 |
| TLS 自動化（certbot / ACME） | PARTIAL | 20-12（certbot renew --dry-run の失敗出力の読解）。native tls（自己署名・期限）は COVERED-REAL | ACME の実発行・更新（pebble 等のテスト CA が必要） |
| Docker Compose・ネットワーク・セキュリティ | PARTIAL（Docker 基本は COVERED-REAL） | native docker（実 daemon。構築・故障調査・再作成・volume 保持）、5-1〜5-5, 5-7, 7-5〜7-7 は作業フォルダでの操作。Compose は 5-6, 22-15、ネットワークは 7-5、セキュリティ（rootless・capability）は 18-10, 19-13 で読解中心。VM podman は IMPLEMENTED-UNVERIFIED | Compose の実起動、docker network、ユーザー名前空間/seccomp の実測 |
| クラウド CLI 基礎（aws / gcloud / az） | MISSING | `toolbox_catalog.py` の一覧と 6-x の説明文に名前が出るだけ。操作も出力読解もない | アカウントが必要なため native 化は難しい。JSON 出力を jq で扱う課題（jq は COVERED-REAL）で近似できる |
| Python / Go / Node 開発環境 | PARTIAL（Python は COVERED-REAL） | native python（venv）、python-packages（toolbox_python）、build（gcc/make）は COVERED-REAL。Go は 33-9、Node は 33-6, 33-8、Rust は 33-10 が出力読解で、実際の go build/npm install は動かさない | Go と Node のビルド・依存解決の実行課題 |
| シェルスクリプトの深さ（getopts・配列・プロセス置換） | COVERED-REAL | native trap と shell、17-11（getopts+trap）、24-8, 24-17（プロセス置換・coproc）、25-23（mapfile・readarray・coproc）。これらは bash を実行して出力を比較する（一部は文字列の存在確認も併用） | ミッションごとの判定の強さは未確認（下の「確認できなかったこと」） |
| 正規表現 | COVERED-REAL | 2-4, 24-1〜24-3, 24-10（grep・sed・perl を実行して判定） | なし |
| 性能ツール（perf・sar・iostat・vmstat・htop） | PARTIAL | 19-6（sar/vmstat 履歴）、19-8（perf/bpftrace）、32-11（htop/btop/iotop）、33-17（strace/ltrace/perf）は読解。VM performance（実機）は top/vmstat 相当の切り分けで、perf/sar/iostat の実行は必須ではない | 実負荷を作って vmstat/iostat を取る native 課題 |
| ディスク健康（smartctl） | PARTIAL | 15-12（smartctl 出力から交換判断）、14-8、26-1（badblocks 出力）。読解のみ | 仮想ディスクには SMART がないため実機では動かせない。読解で完結させるのが現実的 |
| RAID（mdadm）の実演習 | PARTIAL | 15-5（/proc/mdstat の読解のみ）。mdadm コマンドの操作課題は 0 | loop 3 本で RAID1 を作り fail/re-add する VM 課題 |
| ZFS / btrfs | PARTIAL | 23-12（スナップショットと zfs list の読解）、26-22（FS 選択基準）。実操作ゼロ | VM で btrfs を作りスナップショットと subvolume を操作（ZFS は導入が重い） |
| systemd 応用（ソケット起動・テンプレート・サンドボックス） | PARTIAL | 28-21（socket/path ユニットの作成。作業フォルダ内の設定判定）、28-11（systemd-socket-activate）、9-5（NoNewPrivileges・ProtectSystem の設定を直す。デーモンは動かさない）、18-2（systemd-run）。VM software（unit/timer）は COVERED-REAL。VM limits（MemoryMax・LimitNOFILE の実プロセス判定）は IMPLEMENTED-UNVERIFIED。テンプレートユニット（`foo@.service`）は MISSING | `systemd-analyze security` の点数改善、テンプレートの実起動。user マネージャ（`systemd-run --user`）なら無権限で試せる |
| cron と timer の使い分け | COVERED-REAL | native cron（最小環境・`%`・flock・多重起動）、VM software（systemd timer 実機）、23-15（at・anacron の読解）。cron デーモン自体は動かさない（自前パーサ）、at は読解のみ | at の実投入 |
| セキュリティ堅牢化（CIS 風・lynis・ssh・audit） | IMPLEMENTED-UNVERIFIED（ssh/audit/fail2ban）、MISSING（lynis・CIS・自動更新） | VM sshd（sshd -T・鍵のみ・ProxyJump）、VM guard（fail2ban・auditd）、VM users（最小権限 sudo）、VM pam、VM sysctl は未実行。作業フォルダでの 9-2〜9-5, 20-8（ssh 設定の編集）は設定ファイル判定。`lynis`・`aide`・`unattended-upgrades` はコーパスに出ない | 堅牢化スキャンの実行と指摘対応、無人更新の設定。VM 向け |
| インシデント対応 | COVERED-REAL（ログ法医学）、PARTIAL（稼働中ホストの調査） | native incident（失敗再現→根拠を残し復旧）、10-1〜10-6（証拠保全・時系列・認証調査・報告書。作業フォルダのログを実ツールで集計）、VM guard（auditd による証跡、未実行） | 稼働中の不審プロセス・接続を `ss`/`lsof`/`ps` で追い、遮断する実機課題 |
| ハードウェア・USB・udev | PARTIAL | 14-7（lspci/lsusb/dmidecode の読解）、14-11（udev ルールの設定判定）、14-8 | 実際に udev ルールを適用し `udevadm test` で確認する VM 課題。USB の実機接続は自動化できない |
| デスクトップ Linux（パッケージ GUI・Wi-Fi・Bluetooth・音声・印刷・画面） | MISSING（Wi-Fi の設定のみ PARTIAL） | 17-1（nmcli プロファイルの読解）、18-6（Flatpak/Snap の権限出力）。bluetoothctl・pactl/wpctl・cups・xrandr/wayland はほぼ出ない | ヘッドレス VM では判定できない。手動確認チェックリストとして扱うのが妥当 |
| WSL | PARTIAL | 34-17（Windows/WSL からの ssh、CRLF と権限）のみ。`wsl.exe`・systemd の有効化・Windows との連携は MISSING | Windows 上でしか確認できない。読解のみ |
| dotfiles とシェル（zsh・fish） | PARTIAL（bash のみ）、MISSING（zsh・fish・dotfiles 管理） | 24-16（ロケールと環境変数・~/.profile と ~/.bashrc）、3-4, 28-19。zsh は 28/24 に数回言及のみ、fish は言及のみ。stow や bare repo による dotfiles 管理はない | zsh の補完・プロンプト設定の課題と dotfiles を git で管理する課題（native で可能） |
| man / info の使い方 | PARTIAL | 29-17（mandb・whatis・apropos・manpath の出力読解）。man ページを引いて答えを探す課題や `info` の操作課題はない | 手元の man ページから特定のオプションを探させる native 課題 |
| エディタ（vim 以外: nano・emacs） | PARTIAL（vim は COVERED-REAL） | native vim、31-1〜31-20。nano は 31-19（Ctrl キーと .nanorc の読解）、emacs は 31-20（基本キーと `emacs --batch`）。実際の編集操作は自動判定しにくい | 低優先。`emacs --batch` と `nano --rcfile` 程度なら native 化できる |
| 端末と tmux の詳細 | COVERED-REAL（tmux）、PARTIAL（screen/byobu） | native tmux（専用ソケットで分割・capture-pane）、34-19〜34-23（tmux 自動化・ls の読解・.tmux.conf・長時間ジョブの使い分け）。34-22（screen/byobu）は読解 | なし（screen は低優先） |
| Unicode・ロケール | IMPLEMENTED-UNVERIFIED | VM timesync（ロケール生成・localectl・`locale` の警告なしを実判定）。17-7（locale・文字コード変換）、33-19（EditorConfig・LF/CRLF）は読解中心 | 正規化・`iconv`・`LC_COLLATE` による並び順の違いを実測する native 課題 |

## 優先順位付きギャップ（最大 15 件）

「N」は、非特権のホストで実行できる（追加パッケージは必要な場合がある）。「V」は VM（root・実デーモン・カーネル機能）が必要。

| # | ギャップ | 理由・影響 | 実行環境 |
|---|---|---|---|
| 1 | DB サーバ（PostgreSQL / MariaDB / Redis）の実運用とバックアップ復元 | 小規模サーバ運用で最頻の障害対応。現状は読解のみ | N（PostgreSQL は initdb/pg_ctl で非特権、Redis も可。MariaDB は mysqld --user の指定が必要で難しい） |
| 2 | restic / borg の実バックアップ | 「バックアップは復元できて初めてバックアップ」。native archive/rsync の延長で作れる | N（restic は単一バイナリ） |
| 3 | 監視の実起動（node_exporter・Prometheus・alert 発火） | 監視は 22-14 の読解のみ。実サーバを立てて取得・alert を確認させたい | N（高位ポートで非特権起動）／V |
| 4 | Ansible・Terraform の実行（local / check モード） | IaC の実体験がなく、読解では冪等性の実感がない | N（ansible-core、terraform の local provider。ネットワーク不要） |
| 5 | systemd 応用: テンプレートユニット・ソケット起動・`systemd-analyze security` | 28-21, 9-5 は設定判定のみ。limits は未実行 | N（`systemd-run --user`・ユーザーマネージャ）／V |
| 6 | WireGuard/OpenVPN の実トンネル | 20-3〜20-5 は読解のみ。VPN は小規模運用で頻出 | N（root の netns）／V |
| 7 | HAProxy のロードバランシングとヘルスチェック | webstack は Nginx のみ。HAProxy は 21-12 の読解 | N（高位ポート・非特権）／V |
| 8 | mdadm RAID の fail/re-add と btrfs/ZFS | RAID は 15-5 の mdstat の読解だけ。mdadm 課題は 0 | V（root・ループデバイス） |
| 9 | certbot/ACME の実発行 | 20-12 は失敗出力の読解のみ | N（pebble 等のテスト CA）／V |
| 10 | セキュリティ堅牢化の診断（lynis・CIS・unattended-upgrades） | 堅牢化は sshd/guard が IU、診断ツールは出ない | V |
| 11 | 性能ツールの実測（vmstat・iostat・sar・perf）と負荷の再現 | 19-6, 19-8, 32-11 は読解 | N（vmstat・iostat は非特権で可。perf は perf_event_paranoid の設定次第） |
| 12 | Kubernetes の実クラスタ操作 | 22-10〜22-12 は出力読解のみ | V（kind/k3s は docker か root が必要） |
| 13 | CI/CD の実行（ローカルでのパイプライン・git hook） | 22-16 は YAML 読解のみ | N |
| 14 | Go/Node の実ビルドと依存解決 | 33-6〜33-10 は出力読解。Python と C だけが実行課題 | N（ネットワークが必要な場合あり。オフラインなら vendor・ローカル registry を同梱） |
| 15 | 稼働中ホストのインシデント調査（ss・lsof・ps）、zsh/dotfiles、man/info の探索、cloud CLI（JSON）、デスクトップ周辺は手動チェックリスト | 低優先をまとめた項目。デスクトップ（Wi-Fi・Bluetooth・音声・印刷・画面）はヘッドレスでは検証不能 | N（zsh・dotfiles・man 探索）／手動（デスクトップ） |

## 確認できなかったこと

- 28 の未実行モジュール、全体の「実機で動くか」。今回は判定コードを読んだだけで、実行していない。
- 第 2 部の COVERED-REAL としたシェルスクリプト系・正規表現系のミッション（17-11, 24-8, 24-17, 25-23, 2-4, 24-1〜24-3, 24-10, 10-1〜10-6）は、タイトルとコードの抜き読み（bash を実行して出力を比較する）までで、全ミッションの判定の強さは未確認。
- native 実習の「実ホストでの実行」は、依頼文の説明に従った。今回は再実行していない。
- Stage 11〜29 のミッションが「採取済み出力を読む」方式であることは、各ステージのヘッダと代表ミッションで確認した。全 501 問を 1 問ずつ読んではいない。
- 試験の公式目標一覧（特に RHCSA と LFCS の最新版）は第 1 版のまま。再取得していない。
