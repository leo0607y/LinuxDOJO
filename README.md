# LinuxDOJO (LinuxQuest)

Linux を初めて使う人向けの、ターミナルで遊ぶ学習教材です。日本語で書かれています。
「説明を読む、1つ入力する、結果を確かめる」の順で、ファイル操作からサーバー運用まで段階的に学びます。
本体は Python 3 標準ライブラリと bash だけで動き、外部ライブラリは不要です。

## 用語

- Linux: パソコンやサーバーを動かす基本ソフト (OS) の一つです。
- ターミナル: 文字でコンピューターに指示を出す画面です。
- コマンド: ターミナルに入力する指示です。

例: `echo こんにちは` と入力して Enter を押すと、「こんにちは」と表示されます。
`$` や `>` は入力できる場所を示す目印(プロンプト)で、入力する文字には含めません。

## クイックスタート

### Linux (Ubuntu など)

Python 3.8 以上が必要です。教材のフォルダで次を実行します。

```bash
bash start.sh
```

次回から `start` だけで起動したい場合は、起動コマンドを登録します。`sudo` は不要です。

```bash
bash install-start.sh              # 登録先: ~/.local/bin/start
start                              # 以後の起動
bash install-start.sh --uninstall  # 登録の解除(教材と進捗は残る)
```

- 登録後も教材のフォルダは移動・削除しないでください。移動する場合は、先に解除してから移動し、再登録します。
- `start` が見つからない場合は、`export PATH="$HOME/.local/bin:$PATH"` を実行します。シェルの設定ファイルは書き換えません。
- すでに別の `start` がある場合は上書きせず中止します。そのときは `bash start.sh` で起動できます。
- alias や関数の `start` がある場合は、`type start` でどれが使われるか確認してください。

### Windows

教材フォルダの `start.bat` をダブルクリックします。

| 環境 | 使えるモード |
|---|---|
| WSL に python3 がある | 全モード(自動で WSL 版が起動) |
| WSL がなく、Windows に Python 3.8 以上がある | はじめて、基礎練習、応用練習、達人、総合復習(模擬ターミナルのみ) |

- 実践モードは本物の bash を使うため WSL が必要です。PowerShell で `wsl --install` を実行します。
- WSL があっても Windows 版で起動する場合は `start.bat --windows` を使います。
- Python は https://www.python.org/downloads/ から入れます。インストール時に「Add python.exe to PATH」にチェックを入れます。
- 進捗 (`save_data.json`) は Windows 版と WSL 版で共通です。

### 起動オプション (start.sh)

| コマンド | 内容 |
|---|---|
| `./start.sh` | ゲームを起動 |
| `./start.sh --check` | 必要なコマンドが入っているか確認 |
| `./start.sh --test` | 実践モードの全ミッションを自動テスト |

## 使い方

タイトル画面で Enter を押すとメインメニューが開きます。初めての人は「はじめてモード」から始めてください。

### メインメニュー

| 番号 | 内容 |
|---|---|
| 1 | 続きから。選んでいるモードの保存位置から再開 |
| 2 | ステージ選択(はじめて等のモードでは「レッスン選択・復習」) |
| 3 | 進捗ダッシュボード。モードごとの進み具合と全体の達成度 |
| 4 | 小ネタ図鑑 (Extra)(はじめて等のモードでは「用語・コマンド辞典」) |
| 5 | 遊び方・操作コマンド一覧 |
| 6 | 設定。Docker モードの切り替えとセーブの初期化(はじめて等のモードでは進捗の初期化のみ) |
| 7 | モード選択(はじめて、基礎練習、応用練習、達人、実践) |
| 8 | 課題まつり(総合復習)と自由自在マップ |
| 9 | Linux常用コース(目的検索と、本物のツールを使う実習) |
| q | 終了 |

モードを切り替えても、ほかのモードの進捗は消えません。

### 5つのモード

| モード | 数 | 内容 | 実行環境 |
|---|---|---|---|
| はじめて | 24 レッスン | 入力と Enter、現在地、ファイル、`sudo`、`apt` | 模擬ターミナル |
| 基礎練習 | 66 レッスン | ファイル操作、検索、権限、調べ方、SSH と転送、vim | 模擬ターミナル |
| 応用練習 | 46 レッスン | ワイルドカード、パイプと集計、正規表現、環境変数、プロセス、容量 | 模擬ターミナル |
| 達人 | 246 レッスン | 検索と復元、ネットワーク、ユーザー、Git、スクリプト、サービス | 模擬ターミナル |
| 実践 | 501 ミッション | Linux 運用、Docker、セキュリティ、障害復旧、性能、ネットワーク | 本物の bash |

別枠として、メニュー [8] の課題まつりが 228 課題あります。目的だけを読んで手順を自分で組み立てる課題で、難しさは 3 段階です。
上の数値はコードから数えた値です。

### 学習の流れ

1. 問題(説明と課題)が表示されます。
2. コマンドを入力します。
3. 判定され、結果と解説が表示されます。正解なら次へ進みます。

間違えたときは、問題文が画面上部に固定されたまま、フィードバックだけが下にスクロールします。問題を見直しながら、何度でも入力し直せます。

正解は1つとは限りません。同じ結果になる別の書き方も正解になります。

### 補助コマンド(模擬ターミナルのモード)

| コマンド | 内容 |
|---|---|
| `lesson` | 今の説明と課題を再表示 |
| `hint` | 考え方、道具、入力例の順に1段階ずつ表示(減点なし) |
| `answer` | 入力例を表示(減点なし) |
| `reset` | 今の課題を初期状態からやり直す |
| `menu` | 進捗を保存してメニューへ戻る |

### 実践モード

ミッションを選ぶと、専用のサブシェル(本物の bash)が起動します。作業は `workspace/` の中で行います。
タブ補完、パイプ、リダイレクト、`Ctrl+R`、ジョブ制御など、普段の bash の機能が使えます。

```text
LQ 2-7  workspace/stage_02 $ awk '$9 == 500 {print $1}' access.log | sort | uniq -c | sort -rn > report.txt
LQ 2-7  workspace/stage_02 $ check
```

| コマンド | 内容 |
|---|---|
| `mission` | 問題文と達成条件を再表示 |
| `hint` | 段階的ヒント。`hint 2` のように段階を指定できる |
| `answer` | 模範解答と解説(獲得スコアが半分になる) |
| `check` | 達成を判定 |
| `submit <答え>` | 調べた値(PID、ポート番号など)を提出して判定 |
| `reset_mission` | この問題の作業場所を初期状態に戻す |
| `skip` | この問題を飛ばす |
| `menu` | メインメニューへ戻る (`exit` や `Ctrl+D` でも可) |
| `lqhelp` | コマンド一覧 |

スコアとランク:

- 1問 100 点です。ヒントを見るたびに 10 点減り(最大 30 点)、`answer` を見ると 50 点になります。
- クリア数に応じてランクが上がり、ステージを全問クリアすると称号が得られます。
- 進捗は `save_data.json` に自動保存されます。

## コース構成

### 実践モードのステージ(全 501 問)

| Stage | 分野 |
|---|---|
| 1 | ファイルシステムと基本操作 (8) |
| 2 | テキスト処理、検索、パイプとリダイレクト (8) |
| 3 | パーミッション、プロセス、環境変数、監視 (8) |
| 4 | ネットワーク、通信デバッグ、アーカイブ (8) |
| 5 | Docker とコンテナ (7) |
| 6 | シェルスクリプトと自動化 (8) |
| 7 | サーバー運用と Docker 応用 (7) |
| 8 | Web の認証・認可・設定検証 (6) |
| 9 | Linux セキュリティ監査と修正 (7) |
| 10 | 証拠保全、インシデント調査、報告 (6) |
| 11 | ストレージ、起動、復旧の診断 (8) |
| 12 | 性能調査、更新、高度な権限 (8) |
| 13 | ネットワーク設定、TLS、DB 運用 (8) |
| 14-34 | システム管理と開発の実践(合計 399 問) |
| Extra | 現場で役立つ小ネタと時短術 |

Stage 14-34 の内訳は、ブート・ストレージ・SELinux、ネットワークサービス、暗号と VPN、DNS・メール、仮想化と Kubernetes、バックアップと DB、正規表現とシェル上級、各種コマンドの総ざらい、Git、エディタ (Vim・nano・Emacs)、開発者ツール、言語環境、SSH と tmux です。

Git の課題はローカルの使い捨てリポジトリで実行します。課題によって `git`、`vim`、`jq`、`openssl`、`rsync` などが必要です。`./start.sh --check` で確認できます。

### Linux 常用コース (メニュー [9])

日常のファイル操作、調査、開発環境、リモート作業、小規模なサービス運用を、根拠を持って行えるようになるためのコースです。
目的やコマンド名から、既存の課題と実習を探せます。学習順と手順は [docs/LINUX_DAILY_USE.md](docs/LINUX_DAILY_USE.md) にあります。
実習は 2 種類あり、通常の実践 501 問のスコアとは別枠です。

| 種類 | 内容 | 場所 |
|---|---|---|
| 本物の道具の実習(ネイティブ) | 普通のユーザー権限で、本物のコマンドを実行して結果を検査する | `python3 -m engine.toolbox` |
| 使い捨て VM の実習 | 管理者権限が必要な操作を、専用 VM で実際に行う | [labs/vm/README.md](labs/vm/README.md) |

## ネイティブ実習 (engine.toolbox)

リポジトリのルートで実行します。実習は 40 種類(コード上の登録とツール確認の一覧から数えた値)です。
未導入のツールは自動では入れず、その実習は合格扱いになりません。

| コマンド | 内容 |
|---|---|
| `python3 -m engine.toolbox list [検索語]` | 目的やコマンド名から学習経路を検索 |
| `python3 -m engine.toolbox doctor [実習ID]` | 必要なツールの有無を確認(未導入なら終了コード 2) |
| `python3 -m engine.toolbox start <実習ID>` | 実習を開始 |
| `python3 -m engine.toolbox check --directory <フォルダ>` | 作業フォルダの成果物を検査 |
| `python3 -m engine.toolbox cleanup` | Docker など、実習専用のリソースを解除 |
| `python3 -m engine.toolbox audit` | 課題 ID、実習 ID、手引きの参照整合性を検証 |

例:

```bash
python3 -m engine.toolbox doctor
python3 -m engine.toolbox start shell
```

ほかに `setup <実習ID> --directory <新しいフォルダ>` と `solution <実習ID> --directory <フォルダ>` があります。
実習はOSの隔離機能ではなく、普通のユーザー権限で動きます。未導入ツールのテストは明示的にskipし、全実習を検証済みとは扱いません。

`python3 -m engine.toolbox start safe-cleanup` では、扱いにくいファイル名をNUL区切りで列挙し、リンクを追跡せず、変更前の退避・チェックサム確認・隔離移動・別の場所への復元まで練習します。

## VM 実習 (labs/vm)

ユーザー管理、永続ネットワーク、ファイアウォール、別 VM への復元など、模擬では再現しにくい管理操作を、使い捨ての Ubuntu 24.04 VM (Multipass) で行います。
通常の進捗とは別で、VM で `check` を通すまでは修了扱いにしません。
既存のサーバーや普段使いの Linux には、ゲスト用スクリプトを実行しないでください。

教材のエクスポートは、ファイルを書き出すだけです。Multipass の導入や VM の起動は自動では行いません。

```bash
python3 -m engine.vm_labs list
python3 -m engine.vm_labs export --output ./vm-lab-bundle
```

VM 内では、1 課題ずつ次の順で進めます。

```text
sudo dojo-vm-lab <課題ID> setup
sudo dojo-vm-lab <課題ID> check
sudo dojo-vm-lab <課題ID> break
(調査して修正する)
sudo dojo-vm-lab <課題ID> check
```

VM の作成、スナップショット、復元の具体的な手順は [labs/vm/README.md](labs/vm/README.md) を読んでください。

### モジュールと検証状況

| モジュール | 内容 | 実 VM での検証 |
|---|---|---|
| storage | 専用 ext4 の inode 枯渇と再起動後のマウント | 実施済み |
| boot | 専用 systemd サービスの故障と復旧 | 実施済み |
| network | 2 台での DNS と HTTP の切り分け | 実施済み |
| performance | 実測とサービス設定の故障調査 | 実施済み |
| permissions | ACL の実効権限と既定 ACL | 実施済み |
| webstack | Nginx、TLS、SQLite、502 の復旧 | 実施済み |
| packages | deb の導入、更新、故障復旧、remove、purge | 実施済み |
| software | systemd の service と timer、ログ、撤去 | 実施済み |
| ssh | 鍵認証、ホスト鍵照合、scp と rsync、権限障害 | 実施済み |
| users | ユーザー、グループ、sudo 最小権限と事故復旧 | 未実施(最近追加) |
| netconfig | NIC、固定 IP、静的経路、DNS クライアント、IPv6 | 未実施(最近追加) |
| firewall | nftables の適用と、接続を保った復旧 | 未実施(最近追加) |
| restore | バックアップから別 VM へのサービス全体の復元 | 未実施(最近追加) |
| osupdate | 署名エラーと依存不整合からの復旧 | 未実施(最近追加) |
| sshd | 専用 sshd の堅牢化(鍵のみ、root 禁止、ProxyJump) | 未実施(最近追加) |
| mounts | fstab 誤記、swap、LVM の拡張(ループバック上) | 未実施(最近追加) |
| journald | journald の永続化と保存量、時間・優先度での絞り込み | 未実施(最近追加) |
| sysctl | sysctl の永続化、カーネルモジュールの blacklist | 未実施(最近追加) |
| limits | MemoryMax と LimitNOFILE の故障調査(OOM kill) | 未実施(最近追加) |
| timesync | タイムゾーン、NTP、ロケール | 未実施(最近追加) |
| guard | fail2ban の自動 ban と auditd の監査ルール | 未実施(最近追加) |
| dnsserver | BIND の権威ゾーンと AXFR 制限 | 未実施(最近追加) |
| mailserver | Postfix の専用インスタンスとリレー拒否 | 未実施(最近追加) |
| fileshare | NFS の export とマウント(2 台) | 未実施(最近追加) |
| apache | Apache の仮想ホスト、.htaccess、Basic 認証 | 未実施(最近追加) |
| netlink | ブリッジ、VLAN、bond、ポリシールーティング(namespace 内) | 未実施(最近追加) |
| pam | PAM スタックと faillock、pwquality | 未実施(最近追加) |
| podman | rootless Podman と Quadlet | 未実施(最近追加) |
| ldap | 専用 slapd と ACL | 未実施(最近追加) |
| samba | 専用 smbd の共有と権限 | 未実施(最近追加) |
| libvirt | libvirt のテスト用ドライバーで domain・snapshot・network | 未実施(最近追加) |
| tuned | tuned のカスタムプロファイル | 未実施(最近追加) |
| kbuild | カーネルモジュールのビルドとロード | 未実施(最近追加) |
| grubrescue | ループバック上の GRUB 導入と設定修復 | 未実施(最近追加) |
| selinux | SELinux の fcontext と boolean(RHEL 系 VM 専用) | 未実施(最近追加) |
| dnf | dnf と rpm、署名付きローカルリポジトリ(RHEL 系 VM 専用) | 未実施(最近追加) |
| firewalld | firewalld の zone と rich rule(RHEL 系 VM 専用) | 未実施(最近追加) |

注意: 表の「未実施(最近追加)」のモジュール 28 件は、静的なテスト(生成物と構文、ガードの検査、非特権部分の単体テスト)だけを行っています。実際の VM ではまだ動かしていません。実行すると失敗する可能性があります。初回に確認する項目は [labs/vm/FIRST_RUN.md](labs/vm/FIRST_RUN.md) にまとめています。selinux、dnf、firewalld は RHEL 系 VM が必要で、Ubuntu の VM では常に拒否されます([labs/vm/RHEL.md](labs/vm/RHEL.md))。
実施済みのモジュールも、検証したのは特定の環境(専用の Ubuntu 24.04 KVM VM)です。詳細は [docs/coverage.md](docs/coverage.md) にあります。

## 補足

### Docker モード

起動時に `docker info` を確認します。使えない場合は、学習用の模擬 `docker` コマンドが自動で使われます。
メニュー [6] の設定で `auto`、`mock`(常に模擬)、`real`(本物)を切り替えられます。自分の Docker 環境を汚したくない場合は `mock` を選びます。
本物の Docker では、`lq-` で始まる名前と `lq=1` ラベルのコンテナだけを操作します。

### オフラインでの利用

ゲーム本体は外部通信をしません。必要な Linux コマンドを事前に入れておけば、実践モードの全ミッションをオフラインで遊べます。

```bash
./start.sh --check
sudo apt install curl iputils-ping dnsutils rsync zip unzip lsof openssh-client procps iproute2 jq vim
```

- Stage 4 のサーバーは `127.0.0.1` だけで待ち受けます。
- Stage 4-6 の `dig` は、DNS に届かない環境では結果が変わります。その場合は `submit NXDOMAIN` でクリアできます。
- 本物の Docker (`real`) をオフラインで使うなら、課題で使うイメージを先に取得しておきます。オフラインで遊ぶなら `mock` が確実です。

### 注意事項

- 実践モードのサブシェルは本物の bash です。`rm -rf` などは実際に効くので、`workspace/` の外では慎重に操作してください。
- はじめて、基礎練習、応用練習、達人モードの `sudo`、`apt`、SSH、転送は模擬です。実際の OS や外部サーバーは操作しません。
- Stage 4 の SSH 設定は作業ディレクトリ内の `.ssh/` を使い、本物の `~/.ssh` は変更しません。
- 予期しないエラーは `workspace/error.log` に記録され、メニューに戻ります。

## ブラウザ版 (web/danganlog)

Next.js の静的書き出しで、学習処理はブラウザ内の Pyodide が実行します。サーバー側の実行や従量課金のサービスは使いません。ビルド、ローカル確認、Cloudflare Pages への配置手順は [web/danganlog/README.md](web/danganlog/README.md) を参照してください。`next build` と、実際の Pyodide 上での worker の通し実行は確認済みです。実ブラウザでの表示確認と Cloudflare Pages への実デプロイは未実施です。

## 開発とテスト

全ユニットテスト:

```bash
python3 -m unittest discover -s tests
```

主なテスト:

| コマンド | 内容 |
|---|---|
| `./start.sh --test` | 実践モード全 501 問(初期状態は未達成、惜しい誤答は未達成、模範解答で達成、説明の欠落なし) |
| `./start.sh --test 2-7 5-5` | 指定した問題だけ |
| `python3 -m unittest discover -s tests -p 'test_toolbox*.py'` | ネイティブ実習。未導入のツールは skip と表示される |
| `python3 -m unittest discover -s tests -p 'test_vm*.py'` | VM 教材の生成物、ゲストスクリプトの構文、ガード |
| `python3 -m engine.toolbox audit` | 常用コースの参照整合性 |

VM のテストは静的な検査です。VM 内での導入、再起動、復旧が成功することは、VM で `check` を実行して確認します。
Docker の実機テストには本物のデーモンが必要です。

### 主なディレクトリ

| パス | 内容 |
|---|---|
| `engine/` | メニュー、模擬ターミナル、判定エンジン、`toolbox.py`、`vm_labs.py` |
| `curriculum/` | 各モードのレッスン、実践ステージ、課題まつり、`toolbox_labs.py` |
| `bin/mock/`, `bin/sim/` | 模擬の docker、crontab、systemctl など |
| `labs/vm/` | VM 実習のゲスト用スクリプトと手順書 |
| `tests/` | 自動テスト |
| `docs/` | ドキュメント(下記) |
| `workspace/` | 実践用の作業場所(自動生成。リセット可能) |
| `save_data.json` | 進捗の自動保存 |

### ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/LINUX_DAILY_USE.md](docs/LINUX_DAILY_USE.md) | Linux 常用コースの学習順と操作手順 |
| [labs/vm/README.md](labs/vm/README.md) | VM 実習の手順 |
| [docs/coverage.md](docs/coverage.md) | 網羅性の対応表と検証記録 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 開発の引き継ぎ。教材拡張の進捗 |
| [docs/STAGE_BRIEF.md](docs/STAGE_BRIEF.md) | ステージ作成の指針 |

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| 文字化けする | 端末の文字コードを UTF-8 にします。`echo $LANG` が `ja_JP.UTF-8` か `C.UTF-8` であることを確認します |
| 罫線がずれる | 端末の「曖昧な幅の文字」を「半角」に設定します |
| 色を消したい | `NO_COLOR=1 ./start.sh` で起動します |
| `dig` や `lsof` がない | `sudo apt install dnsutils lsof` を実行します(`./start.sh --check` で確認) |
| `start` が見つからない | `export PATH="$HOME/.local/bin:$PATH"` を実行します。または `bash start.sh` を使います |
| 進捗をリセットしたい | メニュー [6] の設定から初期化するか、`save_data.json` を削除します |
| Python がないと表示される | `sudo apt install python3` を実行します。教材が自動で `sudo` を使うことはありません |
