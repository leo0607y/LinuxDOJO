# 導入したソフトを使い、更新・故障復旧・撤去まで行う

この2実習は専用のUbuntu VM内で、本物のapt/dpkg、systemd、journalctlを使います。
ホスト側で `sudo` を実行しません。VMの作成方法は同梱のREADME.mdを先に読みます。
`setup` は教材を用意する操作で、ソフトの導入や修了を代行しません。
各 `check` は現在の段階を検証して次へ進みます。出力に「未修了」とあれば、その実習は途中です。

## パッケージの一生：packages

VMの中で始めます。

```bash
sudo dojo-vm-lab packages setup
sudo cat /var/lib/linuxdojo-vm-lab/state/packages/TASK.txt
```

教材は、依存がPython 3だけのローカルDebianパッケージ `dojo-example` の1.0版と2.0版を生成します。
学習用コマンドと `/etc/dojo-example.conf` 以外の既存ソフトは変更しません。
実習中のdeb導入自体には外部リポジトリやダウンロードが不要です。

| 段階 | 利用者が行う操作 | checkが本物の状態で確認するもの |
|---|---|---|
| 導入 | `dpkg-deb -I/-c` で内容確認、`apt install ./...1.0...deb` | dpkgの導入状態とバージョン、実行ファイル、既定設定による実出力 |
| 設定 | `sudoedit` で指定されたmessageを設定 | 指定した設定でコマンドが正常動作する |
| 更新 | `apt ... install ./...2.0...deb`、設定を保持する選択 | 本体は2.0、利用者の設定は更新後も保持 |
| 故障復旧 | `packages break` の後、stderr・終了コード・設定を調べて修正 | 故障が実際に発生し、プログラムを改変せず設定だけで復旧 |
| remove | `apt remove dojo-example` | 実行ファイルは消え、conffileとdpkgのconfig-files状態は残る |
| purge | `apt purge dojo-example` | パッケージ本体と設定を削除し、全段階を経て初めて修了 |

最初からパッケージがない状態でcheckしても、purge達成にはなりません。
導入・設定・更新・故障復旧・removeの確認を順番に通る必要があります。

### 操作の見本

まずTASK.txtを読んで自分で試し、詰まったら見本を使います。
この見本は **VM内** で実行します。最初のsetupは1回だけです。

```bash
sudo -i
cd /var/lib/linuxdojo-vm-lab/state/packages
dpkg-deb -I debs/dojo-example_1.0_all.deb
dpkg-deb -c debs/dojo-example_1.0_all.deb
apt install ./debs/dojo-example_1.0_all.deb
command -v dojo-example
dpkg-query -W dojo-example
dojo-example
dojo-vm-lab packages check

printf 'message=%s\n' "$(cat message)" > /etc/dojo-example.conf
dojo-example
dojo-vm-lab packages check

apt -o Dpkg::Options::=--force-confold install ./debs/dojo-example_2.0_all.deb
dojo-example --version
dojo-example
dojo-vm-lab packages check

dojo-vm-lab packages break
dojo-example
echo "$?"
cat /etc/dojo-example.conf
cat failure.stderr
printf 'message=%s\n' "$(cat message)" > /etc/dojo-example.conf
dojo-example
dojo-vm-lab packages check

apt remove dojo-example
dpkg-query -W -f='${Status}\n' dojo-example
test -f /etc/dojo-example.conf
dojo-vm-lab packages check

apt purge dojo-example
test ! -e /etc/dojo-example.conf
dojo-vm-lab packages check
exit
```

`--force-confold` はこの課題で「自分の設定を保持する」という選択を明示するために使います。
実際の更新では新旧設定の差を調べ、保持・置換・手動統合を判断します。
aptの履歴は `/var/log/apt/history.log`、dpkgの履歴は `/var/log/dpkg.log` で読みます。
ローカルdebについて `_apt` がファイルを読めずsandbox外で取得したという通知が出る場合があります。
この実習の保存先はroot専用です。通知を消すためにシステム全体の権限やapt設定を緩める必要はありません。

## 定期実行ソフトの運用：software

```bash
sudo dojo-vm-lab software setup
sudo cat /var/lib/linuxdojo-vm-lab/state/software/TASK.txt
```

専用のPythonプログラム、設定ファイル、service、timerを読み、利用者自身が導入します。
教材の保存先はroot専用なので、TASK.txtを読んだ後、この専用VM内で `sudo -i` を実行してから
`cd /var/lib/linuxdojo-vm-lab/state/software` へ移動して操作します。作業を終えたら `exit` でubuntuのシェルへ戻ります。
プログラムは `DynamicUser=yes` の専用の非rootユーザーで動き、systemdが用意するStateDirectoryへレポートを書きます。
実際のjournalに正常時と異常時のログが残ります。

| 段階 | 利用者が行う操作 | checkの確認 |
|---|---|---|
| 導入 | ファイル配置、`systemd-analyze verify`、`daemon-reload`、timer有効化 | 指定したunit/実行ファイル/設定、実timerの稼働と自動起動、非rootプロセスによる実レポート |
| 調査 | `software break`、`status` と `journalctl`、設定修正、再起動 | 故障後に新しく作った正常レポート、プログラムやunitの検査回避がないこと |
| 再起動 | 使い捨てVMを再起動 | 起動IDの変化、timer有効化、今回の起動後の成功ログ |
| 撤去 | timer停止・無効化、unit/プログラム/設定の削除、daemon-reload | 実際の停止・無効化とファイル撤去。ここで修了 |

### 運用で確認するコマンド

```bash
sudo systemctl cat dojo-software.service dojo-software.timer
sudo systemctl status dojo-software.service dojo-software.timer
sudo systemctl list-timers --all dojo-software.timer
sudo journalctl -u dojo-software.service -b --no-pager
sudo cat /var/lib/dojo-software/report.json
```

`enable` は次回起動時などの起動関係を作る操作、`start` は現在起動する操作です。
unitの定義を変更した場合は `daemon-reload` が必要です。
この課題は起動するたびに設定を読むoneshotプログラムなので、設定修正後はサービスを起動し直します。
長時間稼働する別のソフトでは、そのソフトが `reload` に対応しているかを調べて使い分けます。

`break` は専用timerを停止し、設定を壊して実サービスの失敗を記録します。
復旧時は設定を `config.example` と同じに戻し、サービスとtimerを起動してください。
復旧checkの次にVMを再起動します。timerの初回実行は数秒後なので、起動直後のcheckが失敗したらログを読み、数秒後に再確認します。

撤去checkを通した後も `/var/lib/dojo-software` のレポートは証拠として残ります。
`reset` はこの教材のunit・設定・実行ファイルと実習状態を解除する操作で、証拠レポートを消しません。

## 到達点と検証範囲

packagesはローカルdebとconffileを使う実習です。リポジトリ署名・鍵更新、RPMの実操作、依存競合の複雑な解消まで修了した扱いにはしません。
softwareは実systemd service/timerを使う実習です。常駐WebサービスのreloadとTLSは既存のwebstack実習で扱います。

開発環境の自動テストでは、専用の一時dpkgルートで実際にdebの導入・設定保持更新・remove・purgeを検証し、生成プログラムの正常系と設定エラーを実行します。
ホストのパッケージDBとsystemdは変更しません。VM内のroot操作、起動後のtimer実行、再起動を含む修了checkは、専用VMで実際に行うまで「実行確認済み」には数えません。

## 参照した公式資料

- [Debian Policy: Configuration files](https://www.debian.org/doc/debian-policy/ch-files.html#configuration-files)：conffileを更新・削除時にどう扱うか。
- [Debian dpkg-deb manual](https://manpages.debian.org/bookworm/dpkg/dpkg-deb.1.en.html)：debの構築・内容確認・展開。展開だけでは導入になりません。
- [Ubuntu Server: Install and manage packages](https://documentation.ubuntu.com/server/how-to/software/package-management/)：aptとdpkgの基本操作。
- [systemd.timer manual](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)：timerによるserviceの起動と周期。

### 2026-11-21の実VM検証

公式cloud imageのSHA256を照合したUbuntu 24.04.5の専用KVM VMで、packagesの実apt導入・設定保持更新・故障復旧・remove/purge、softwareの実service/timer・非root実行・設定エラーログ・復旧・VM再起動・撤去まで実行し、修了checkが成功しました。検証後のVMは停止済みです。教材テストの成功とは別に、学習者自身も各段階を確認します。
