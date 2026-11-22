# 引き継ぎ書（LinuxQuest 教材拡張）

最終更新: 2026-11-22 / ブランチ: `learning-expansion` / 状態を変えたら必ずこの表も更新する。

## 最短の再開手順（次の担当はここから）
1. `git status --short` と `git log -12 --oneline`。ブランチは `learning-expansion`。完了単位で検証して細かくコミットする。**未コミットを一括で追加しない**（下の担当別ファイルを確認）。pushとデプロイはまだしない。
2. この文書の「最新チェックポイント」を読む。前Claudeのバックグラウンド担当は終了しており、その完了待ちをしない。新セッションでCodex担当も消えていれば、ディスクとVMから続行する。
3. 実VMの合格根拠は `docs/vm_verification/*.md` の実出力。`tools/vmtest/scenarios/*.sh` は再現手順。`python3 tools/vmtest/verify_scenario.py VM tools/vmtest/scenarios/MOD.sh /tmp/MOD.log`。setup→checkだけでは通常不合格で、学習者操作とbreak・修復を含める。
4. `python3 -m engine.toolbox audit`。全体検証は `python3 -m unittest discover -s tests`。NodeがPATHになければ下のNodeパスを追加してからサイトのbuild/test/E2Eを実行する。未導入によるskipを合格に数えない。
5. 機能単位の確認後、担当ファイルとこの文書だけを追加してコミット。検証前の作業保存は `WIP` と明記し、実VM未検証を維持する。

## 最新チェックポイント（2026-11-22 / 利用上限に備えた保存）

### 確定しているもの
- 周辺機器の模擬31問: `2ce3477`。初期未達成・正解・罠拒否・ホスト操作禁止の11テスト成功。実機の証明ではない。
- FTP/ACL: `a5bec87`。実VMで正常・故障/抜け道拒否・reset、2周目setup/reset成功。ACLのgetfacl誤判定を修正。
- 講座の4区分対応: `623c379`。未検証を独立表示し、集計と目標行を照合。生成済みデータもbuildのたびに更新する。
- firewall: `381b0bc`。実nft/netns、HTTP部分受信の誤判定を修正。通信・抜け道拒否・再読込・専用資源の撤去を確認。
- localca: `045a20b`。実TLSテストのpipe未closeを修正。ResourceWarningをerrorにして4テスト成功。
- 前担当の途中修正保存: `5e93b15`。guard/libvirt/netlink/pam/podman/postgres/systemdadv/tunedは、この時点では**実VM未検証**。その後の個別完了記録を優先する。
- Git30-13: 固定HEAD~5を誤答としていたが、ランダムな故障位置と一致する場合があった。誤答を必ず正常なgoodタグへ変更（採点条件は変更なし）。個別検証後、全501問を再実行: `/tmp/training-release-missions.log`。
- Vim31-17: ERROR行をFIXマーカーで上書きした際の期待件数を修正。生成後の実内容で集計。ERROR行/INFO行の両ケースの回帰テストと実Vim操作31-17成功。
- ターミナル起動: `b91a92f`。ペンギンと青/紫/シアン、瞬き・ウインク・笑顔。`LQ_NO_ANIMATION=1`で静止。NO_COLOR/非TTYでも静止。PTYで起動とEnter終了を確認。関連10テスト成功。
- Podman: `170ae81`。rootless Quadlet、公開範囲・実bind mount/heartbeat、UID/GID対応・起動失敗修復・user manager再起動・2周の専用資源撤去を確認。実出力 `g7-podman.md`。
- PostgreSQL: `1b1704c`。実VM検証と修正を取り込み。ロール属性・SCRAM・実効HBA/再起動設定・最小権限・論理復元・物理backupの由来を確認。`g6-postgres.md`に公式runner実出力。
- 常用の安全操作: `ffed7f8`。native `safe-cleanup`（40本目）、NUL区切り・特殊ファイル名・リンク非追跡・退避・隔離移動・復元。実ツール3テスト成功。toolbox関連42テスト成功/skip14。
- users/lynis: `aabd59d`。最小sudo復旧、Lynis実監査59→60・対象警告消失・誤設定拒否・reset。実出力は `g1-users.md`, `g8-lynis.md`。
- サイトUI: `4497b0f`。`docs/UI_REVIEW.md`に設計と実画面確認を記録。単調な配色・角丸カード・偽ウィンドウ操作を廃し、説明/端末の2ペインと索引へ。デプロイは未実行。
- 全体テスト直近: 618件成功/skip48（192.6秒）、サイトbuild成功、npm7件、講座Node4件、E2E14件成功。**その後のUI・新課題は再実行が必要**。

### いま進行中・取り込み待ち
| 担当 | 所有ファイル | 再開地点 |
|---|---|---|
| site_ui (Astra) | web/danganlog/app と components | 完了。4ページ×3幅の実画面確認、axe8画面0件。親も画像確認、build/npm7件/course4件/E2E14件成功。利用者の見た目確認待ち。dev3106 |
| vm_postgres (Sol) | postgres.sh / scenarios/postgres.sh / g6-postgres.md | 完了。公式runner exit0、親で単体4件成功。標準mainを保ち2周の専用資源撤去を確認。物理復元からの起動/OS再起動は未検証 |
| vm_podman (Sol) | podman.sh / test_vm_podman.py / scenarios/podman.sh / g7-podman.md | 完了。公式runner exit0、親で単体4件成功。ユーザーsystemd再起動後に自動復帰、2周の残骸なし。OS再起動は未検証 |

### 次に着手する順
1. 上の3担当は完了・親で取り込み確認済み。最終623 unittest成功/skip48（175.7秒）。501問は500成功、31-17のランダムfixtureの件数誤りを発見して修正。回帰テストと31-17実Vim操作は成功。修正後の全体を再実行中: `/tmp/training-final-python.log`, `/tmp/training-final-missions.log`。結果を確認し保存する。
2. `docs/DAILY_USE_AUDIT.md` の常用時の抜けを実操作課題で補う（単なるコマンド名追加にしない）。
3. 未完了VMモジュールの再検証。guard/libvirt/netlink/pam/systemdadv/tunedなどはWIP保存済みでも通過扱いにしない。RHEL3本はRHEL VM未用意。
4. 変更が止まったら全Python、サイトbuild/npm/course/E2Eを1回通し、結果とskipを記録。見た目の利用者確認前にデプロイしない。

- daily_cron担当は制限残25%のため設計確認だけで停止。リポジトリ/VM変更なし。実装は未着手で、次回はDAILY_USE_AUDITの方針から開始する。

### 環境とログの場所
- Node 22: `<node-dir>/bin` をPATHへ追加。消えていれば別途用意する。
- VM: `~/.cache/linuxdojo-vm/vms/`。g1-app/client、g3-app〜g8-appを保持。`up NAME` で停止済みを再開できる。g6/g7の担当作業は完了し、専用資源は撤去済み。記録を確認して再利用する。
- `vmtest.py install` は共有 `bundle/` を書き換えるため並列実行しない。VM内の試験自体は別VMなら並列可。
- 一時ログ: `/tmp/training-*.log`。**実VM通過ログはdocsへ保存するまで完了としない**。画像: `/tmp/dangan-{terminal,course,detail,coverage}-{1280,375,320}.png`。
- サイトdev `http://127.0.0.1:3106` はUI担当用。既存3000は変更しない。開発サーバーは公開デプロイではない。

### サブエージェントの使い方（今回のやり方）
- 1Stage = 1エージェント。担当ファイル以外は編集させない（配線は親が先に済ませる）。
- 指示は `docs/STAGE_BRIEF.md` ＋ 担当Stageの「必須キーワード一覧」。キーワードが課題内に名前で出ているか、最後に grep で検証する。
- エージェントの自己報告は鵜呑みにせず、親が全体テストを再実行する。他エージェントが書き途中のファイルがあると一時的に import エラーになる（待って再実行）。

## 追加実習・サイト版の状況（2026-11-22、随時更新）

### いまの状態（最優先で読む）
- ブランチ `learning-expansion`。**大量の変更が未コミット、または直前コミット以降に追加されたものです。** まず `git status` と `git log --oneline | head -5` を確認し、`python3 -m unittest discover -s tests` を流して現状を把握する。他のエージェントが作業中の場合、一時的な失敗が出ることがある。
- 利用者の方針（守ること）:
  - 絵文字を使わない（コード、資料、サイト、起動スクリプトすべて）。
  - 検証していないものを「検証済み」と書かない。実VMで通ったものだけを実VM検証済みとする。
  - サイトの**デプロイは、利用者が開発サーバーで見た目を確認してから**。それまで `wrangler deploy` や `pages deploy` を実行しない（自動許可の判定でも拒否された）。
  - 不足（未対応）を0にする方針。`docs/objectives_matrix.md` の MISSING を減らし続ける。
  - 引き継ぎ書をこまめに更新する。
  - 完了した小単位ごとに検証し、細かく定期的にコミットする。push は確認後。

### 利用者の追加要望（Codex再開後）
- サブエージェントとモデルを適切に使って効率化する。UI担当 Astra、VM検証担当 Sol で分担。
- サイトは単調な色・角丸・定型AI風カードを避け、情報設計と文字組みを整える。実画面で確認してから反映する。
- 日常Linuxで知らないと困る操作の抜けを監査し、実操作できる課題で補う。名前だけ増やさない。
- ターミナル版のスタートは以前のペンギンとカラフルな文字を戻し、動き・表情を付ける。

### 検証の読み方
- 実VM通過済みの追加分は上の最新チェックポイントと `docs/vm_verification/` を参照。WIP保存時点の未検証ラベルより、後の個別通過記録を優先する。
- `guard libvirt netlink pam systemdadv tuned` など、通過記録のない追加分は未検証のまま。全VM検証8グループが完了したわけではない。
- native40件は登録数。未導入ツールは合格にせずskipする。safe-cleanupは実ツール3テスト成功。
- 再開前の記録は以下に履歴として残す。件数やステータスが違う場合、先頭の最新チェックポイントを優先する。

### 実装済みの範囲
- VMモジュール: 合計51（`labs/vm/guest/modules/*.sh`、`ls` で数える）。既存9（packages software ssh permissions network performance storage boot webstack）は以前の実VMで検証済み。追加分は下記の実VM検証を進行中。RHEL系3本（selinux dnf firewalld）は RHEL 系 VM が必要で、`labs/vm/RHEL.md` に手動手順がある。Ubuntu VMでは常に拒否される。
- ネイティブ実習: 合計40（`curriculum/toolbox_labs.py` と `toolbox_labs2.py`〜`toolbox_labs6.py`）。`add` は ID の重複で例外を出す。
- 模擬の周辺機器実習（Wi-Fi・Bluetooth・音声・印刷）: `engine/commands/desktop.py` と `curriculum/stage35_desktop_hw.py`（前担当は中断。課題まつりの `desktop_hw` パック31問として取り込み、実践Stageへの登録は行わない）。模擬であり、実機の技能の証明ではない。
- ターミナル版のUI: `engine/ui.py` に配色・記号・共通部品（header、menu_row、footer など）を定義。ターミナル風の見た目に刷新済み。

### 実VMでの検証（重要）
- この環境に qemu も sudo も無いが、`/dev/kvm` は利用者が読み書きでき、root なしの検証土台を作った: `tools/vmtest/vmtest.py`。qemu は `apt-get download` と `dpkg -x` で `~/.cache/linuxdojo-vm/` に展開、公式 Ubuntu 24.04 イメージは SHA256 と gpg 署名を照合して使う。
- 使い方: `python3 tools/vmtest/vmtest.py prepare` → `up NAME --role app|client` → `install NAME` → `run-module NAME MOD --steps setup,check,reset` → `destroy NAME`。2台構成は `VMTEST_LINK_PORT` を VM の組ごとに変える。
- 1モジュールの setup、check、reset は約4秒。VMの起動と cloud-init は約80秒。
- 検証担当を8グループに分けて実行した（g1〜g8）。結果は `docs/vm_verification/g*.md`。**これが実VMでの通過記録の正。** 通ったものだけが「実VM検証済み」。失敗や未検証はそのまま残っている。
- 検証結果を `docs/coverage.md`、`docs/objectives_matrix.md`、`labs/vm/README.md` の表、`labs/vm/FIRST_RUN.md` に反映する作業が残っている。

### サイト版（danganlog.com 向け）
- `web/danganlog`: Next.js 15 の静的書き出し（`output: 'export'`）。サーバー実行なし、従量課金のサービスなし。Pyodide は自前配信。UI は Ubuntu 端末風（画面全体が端末、課題は1行固定、出力だけスクロール）。
- 起動: Node 22 が必要（この環境ではスクラッチパッドに展開したもの）。`cd web/danganlog && npm ci && npm run dev -- -p 3000`。ビルド: `npm run build`（`tools/build_web.py` が `python-source.json` を生成）。
- テスト: `npm test`（node）、`npm run test:e2e`（Playwright、実ブラウザ。14件通過を確認済み）。
- `/course/`: 32トピックの講座ページ（`tools/build_course_data.py` が生成）。見た目を Ubuntu 端末風に揃える作業が未確認。
- Cloudflare: `wrangler login` 済み。アカウントには別の既存プロジェクトがあり、**触らない**。新規プロジェクト名は `danganlog` の予定。デプロイは利用者の見た目確認後。手順は `web/danganlog/README.md`。

### 残りの作業（優先順）
1. 実VM検証の結果（`docs/vm_verification/`）を、各表に反映し、`FIRST_RUN.md` を「実VMで確認した事項」に更新する。
2. 全テスト実行（`python3 -m unittest discover -s tests`、`npm test`、`npm run test:e2e`）。失敗は他エージェントの作業の途中状態かを確認する。
3. `docs/objectives_matrix.md` を再集計し、未対応の行を0に近づける（未対応の内訳はその表を参照）。
4. 模擬の周辺機器実習の取り込み確認（`tests/test_desktop_sim.py`）。
5. サイト版: 利用者の見た目確認 → 指摘の修正 → 確認後にデプロイ。
6. RHEL 系 VM（Rocky/Alma）での `selinux` `dnf` `firewalld` の実機検証（`tools/vmtest` は Ubuntu 専用。拡張が必要）。
7. コミットと push（`git -c user.name=... -c user.email=...` で既存の作者を使う。末尾に Co-Authored-By を付ける。`.gitignore` は許可リスト方式なので、新規ファイルは allowlist を確認する）。

## 常用コースの追加（2026-11-21）

利用者の「Linuxを普段使いし、主要ソフトを導入後も扱える教材」という依頼で追加。Stageの問数を増やすより、既存501問を目的別につなぎ、実機での経験を補う方式。

- 入口: ゲームの **[9] Linux常用コース**、または `python3 -m engine.toolbox list`。
- `curriculum/toolbox_catalog.py`: 27コア目標＋5拡張分野、主要159コマンド。日本語の目的検索、正確な課題ID・実習ID・手引きアンカー。
- `curriculum/toolbox_labs.py` / `toolbox_python.py` / `toolbox_containers.py`: 本物のツールを動かす20実習。`start ID`、`doctor [ID]`、`check --directory PATH`、`cleanup --directory PATH`。必要ツールなしでは開始・合格にせず、未完了setupの再開も拒否する。
- 実習シェル: `task` / `check` / `answer` / `cleanup` / `exit`。進捗は専用フォルダの `.dojo/state.json`。既存501問のスコア・称号・セーブとは別枠。
- `docs/LINUX_DAILY_USE.md`: 最短経路、導入・操作・設定・検証・障害切り分け・更新・撤去、手本なし総合確認。
- `docs/coverage.md`: 実ツール・模擬・記録・VM・手動を区別した対応表と修了基準。資格試験・全機器・全クラウドの網羅を意味しない。
- VM教材は `.gitignore` の許可対象から漏れていたため今回追跡する。既存6本＋ `packages` / `software` / `ssh` = 9モジュール。`SOFTWARE.md` もexportに含める。
- 実VM試験でstorageの `df -i --output=iavail` がGNU dfで両立しない不具合を発見し、`df --output=iavail` に修正。SSHの内部接続には `-n` を追加し、呼出し元の標準入力を消費しない。また、再起動時に `/run/sshd` がまだ存在せず専用sshdが失敗する問題を発見し、unitのExecStartPreでディレクトリを作成するよう修正。新規setupから実SSH操作と再起動を再検証した。

検証（最終結果は下の記録と `docs/coverage.md` を参照）:

- 既存ミッション: **501/501 PASS、137.7秒**（Dockerは従来のmockモードを含む）。
- 全unittest: **299件、失敗0、skip1、54.0秒**。ホストのDockerデーモンがないため統合1件は明示skip。未導入のtmux/sqlite/gcc/make/fzfはUbuntu公式debを `/tmp` へ展開して実ツールで検証し、ホストOSへインストールしていない。
- 実pip: オフラインwheelを本物のvenvへ導入→利用→更新→版固定、アンインストール→再導入まで検証。OSのPythonは変更なし。
- 専用Ubuntu 24.04 KVM VMを実際に作成（公式cloud imageのSHA256照合）、実aptの導入・設定保持更新・remove/purge、systemd service/timer・障害・ログ・再起動・撤去、実SSHの認証・scp/rsync・権限障害を確認。
- 同VMでpermissions/performance、network app側、boot/storage/webstackの故障拒否→修復、後者3本はVM再起動後のcheckまでPASS。
- 2台の実Ubuntu KVM VMでclient→appのDNS/HTTP正常、DNS故障時のcheck拒否とIP直指定HTTP成功、DNS修復後の双方PASSまで検証。
- 同VMの実Dockerでイメージ構築・設定エラー・非root HTTP・コンテナ再作成・volume保持・専用資源削除までPASS。ホストのDocker skipを模擬成功で置き換えていない。
- 同VMの通常ubuntuユーザーでも18実習＋pipの23テストを実行し、skipなしPASS（21.1秒）。全実ツール20実習を実行確認済み。検証用VM2台は終了後に停止した。

従来のStageの静的検査や、各拡張分野がすべて実機化されたわけではない。常用コースの全項目を手本なしで再現・説明するのが学習者の到達確認であり、教材テストの成功だけで習得済みにはしない。

## 常用コースの再監査

2026-11-21、別の監査担当2本で実装を再照合。日常CLI基礎・主要道具は広いが、27到達目標すべての実操作を網羅した状態ではないことを確認。特にユーザー/sudo管理、NIC/経路/DNSクライアントの永続設定、基本firewall、別VMへのサービス全体復元が不足。次点は外部repo/OS更新障害と実logrotate。`docs/coverage.md` の「再監査で確認したコア内の不足」を正本とする。「全20実習がPASS」を「Linuxのほとんどを網羅」と言い換えない。

既存の有用な24-16（起動ファイル・環境継承）と17-7（文字コード変換）が常用索引から漏れていたため、shell/textの経路へ追加した。

## 目的
Linuxを学ぶうえで「使うもの・使わなくても必要なもの」を網羅した実践課題を用意する。
エンジニアが普通に入れて使う道具（Git・Vim・SSH・tmux・jq など）の**使い方**まで含める。

## 現在地（一目で）
| 区分 | 状態 | 備考 |
|---|---|---|
| Stage 1〜13（102問） | 完了・コミット済 `f7feabe` | 全問 PASS を確認済み |
| Stage 14〜18（62問） | 完了・コミット済 `e833997` | 実践は計164問、unittest 246件 OK |
| ui.clear のスクロールバック消去 | 実装済（`e833997`） | **実端末での目視は未確認** |
| Stage 19〜34（337問） | 統合テスト済み | 全501問 PASS（130.8秒）。Stage 30も28問すべてPASS |
| 統合テスト・READMEの問数更新・コミット | 完了 | 全501問 PASS、unittest 246件 OK、compileall・diff --check OK。README・進捗テストは501問 |
| 資格試験の公式範囲との全項目対応表 | ⏳ 未着手 | LPIC/LinuC/RHCSA 範囲 ↔ 課題ID |
| 「必要ツール」宣言の仕組み | 常用20実習に実装 | 既存501問への一律適用は未実施 |
| 常用コース・対応表・実機検証 | 追加 | 上の「常用コースの追加」を参照 |

## Stage 一覧（ID・内容・状態）
状態の凡例: 統合テスト済 / 作成済(未統合テスト) / 作成中 / ⏳未着手。2026-11-21に全501問の初期状態・誤答拒否・想定解・メタデータを実行検証済み。記録診断や静的検査の限界は下表に残す。

| Stage | 内容 | 目安問数 | 状態 |
|---|---|---|---|
| 14 | ブート・カーネル・ハード | 12 | |
| 15 | ストレージ構築 | 12 | （実機mkfsは未使用、記録診断中心） |
| 16 | SELinux/ACL/属性/資源制限 | 12 | |
| 17 | ネットワーク管理・共有・パッケージ・バイナリ調査 | 12 | （iconv/rsync/xxd に実依存） |
| 18 | プロセス・GPG・コンテナ基盤・Ansible ほか | 14 | |
| 19 | 補完（tune2fs・hexdump・firewall-cmd・ausearch 等） | 16 | 統合テストPASS（16/16 PASS） |
| 20 | 暗号化・VPN・SSHトンネル | 16 | 統合テストPASS（16/16 PASS） |
| 21 | DNS・DHCP・メール・LDAP・負荷分散 | 16 | 統合テストPASS（16/16 PASS。21-2/21-16 は複数話題を統合） |
| 22 | 仮想化・NAT・Kubernetes・IaC・監視 | 16 | 統合テストPASS（22-6/22-10は模範解答を記録から解析してJSONを作る方式に修正し、個別テストPASS。Ansibleは対比のみ） |
| 23 | バックアップ・DB・ストレージ応用・ログ運用 | 16 | 統合テストPASS（16/16 PASS。実ツールは使わず記録/設定検査） |
| 24 | 正規表現・シェル上級・パッケージ作成・カーネルビルド | 18 | 統合テストPASS（24-10〜15 の一部はトークン検査のみ=コマンドを実行しない） |
| 25 | ハッシュ・テキスト・シェル組み込みの総ざらい | 24 | 統合テストPASS（xzless/zless/znew は名前のみで未実行） |
| 26 | ファイルシステム・ブロックデバイス工具 | 22 | 統合テストPASS（22/22 PASS。エージェント報告は「pending」だけだったが成果は有効） |
| 27 | プロセス・資源・システム情報 | 24 | 統合テストPASS |
| 28 | ユーザー管理・systemd周辺・kmod・/etc設定 | 24 | 統合テストPASS（実行せず記録・設定の検査のみ） |
| 29 | 低レベルネットワーク・パッケージ・man・SSH補助 | 24 | 統合テストPASS（実行せず記録・設定の検査のみ。ssh-add/tldr は軽い扱い） |
| 30 | Git実践 | 28 | 統合テストPASS（28/28。APIエラー後もファイルは残存） |
| 31 | Vim・nano・Emacs | 20 | 統合テストPASS（emacs/ctags は無く記録診断。`:%s///gc` と `"+` は説明のみで非実行） |
| 32 | 開発者ツールボックス（jq/curl/fzf/rg ほか） | 26 | 統合テストPASS（fd/fzf/bat/tree/ncdu などは1問に統合。yq/sqlite3/stow は無くフォールバック） |
| 33 | 言語環境・ビルド・デバッグ・品質ツール | 22 | 統合テストPASS（gcc/make/cmake/gdb/valgrind/shellcheck 等は実行せず静的検査・記録診断のみ） |
| 34 | SSH・tmux・リモート作業 | 25 | 統合テストPASS（tmux/sshd/sshfs は実行せず記録・設定検査。ssh 不在時のフォールバックは未検証。34-3 は Stage 20 と一部重複） |

## 配線の仕組み（新しいStageを足すとき）
1. `curriculum/stageNN_xxx.py` を作り `curriculum/__init__.py` に import を足す
2. `engine/runner.py` のステージ名表、`engine/save.py` の称号表、`engine/readiness.py` の `_practice("NN-")` を足す
3. `tests/test_progress.py` の総問数・ステージ別内訳・ランク境界を更新（Stage追加のたびに必須）
4. `README.md` の問数と章を更新
5. 検証: `python3 tests/test_all_missions.py [ID...]` と `python3 -m unittest discover -s tests`
- `.gitignore` は許可リスト方式。新しい最上位ディレクトリは追加が必要（`docs/` `tools/` は追加済み）。
- コミットは `-c user.name="LinuxDOJO contributors" -c user.email="noreply@users.noreply.github.com"`。プッシュは確認してから。

## 網羅性の測り方
- `python3 tools/audit_coverage.py --list`: 環境にインストール済みのコマンドのうち教材に一度も出ないものを列挙
  - 最新監査（Stage 19〜34 作成後）: **428/528 が登場、100 が未登場**（この環境のインストール済みコマンド基準）
  - 注意: 名前が出る＝身につく、ではない。下限の目安でしかない。
- 別途やること: LPIC-1/2・LinuC-1/2・RHCSA/RHCE の試験範囲表を作り、各項目を課題IDに対応づける（空欄＝未カバー）

## 既知の課題・リスク
- **ツール依存**: Stage 17 は `iconv` `rsync` `xxd` を実際に呼ぶ。ツールが無い環境で失敗する。課題に「必要ツール」を宣言し、無ければスキップ表示する仕組みが無い。
- この環境に `tmux` `sqlite3` `make` `gcc` は無い。該当課題は記録診断で作成（実機での練習にならない）。
- `ui.clear()` の変更は未確認（実端末が無かった）。長い画面がターミナル高を超える場合は従来どおり上へスクロールできる。
- サブエージェントの課題は、wrong（誤答）が確実に失敗するか・値が毎回ランダムかを、統合後に抜き取りレビューする必要がある。
- テスト時間: この環境では501問で130.8秒。CIでは分割が必要になる可能性。
- サブエージェントのテスト実行でリポジトリ直下にゴミファイルが出た（削除済み）。課題の cwd が workspace 外だった可能性があり、再発するなら要調査。

## 追加で必要そうなもの（未着手・提案段階）
1. **総合演習（キャップストーン）**: 複数原因が絡む障害を、ログ・設定・ネットワークから一から切り分ける長めの課題
2. **ネットワーク理論**: OSI/TCPの3ウェイ、サブネット計算・CIDR、ルーティング、ARP、NAT の手計算課題
3. **OS内部**: システムコール、仮想メモリとページキャッシュ、スケジューラ、ジャーナリングFS
4. **クラウドCLI**: aws/gcloud/az の出力読解、IAM・VPC の基礎
5. **セキュリティ演習の拡張**: nmap・脆弱性スキャン結果の読み方、ログからの攻撃検知
6. **環境差分**: macOS/BSD/WSL とLinuxの違い、BusyBox/Alpine（musl）
7. **資格模擬**: LPIC/LinuC/RHCSA 形式の確認問題
8. **UI**: 数百問のメニュー操作（検索・分野別絞り込み・必要ツール表示・折りたたみ）
9. **英語のman/ドキュメントの読み方、OSSライセンス、コミュニティの作法**
10. **実VM実習（labs/vm）の拡張**: 実際の mkfs/LVM/SELinux/nginx を試せる環境

## 次の一手（この順）
1. Stage 24ほか静的検査の課題を、ツールがある環境での実行検証へ段階的に強化する
2. 常用コースで実装した必要ツール・未導入案内・目的検索を、必要に応じて既存501問へ拡張
3. 未登場100コマンドの必要性を評価する（別名・内部用コマンドを数合わせで追加しない）
4. 常用対応表 `docs/coverage.md` とは別に、資格試験の公式範囲との対応表を必要時に作る
5. 上の「追加で必要そうなもの」を優先度付けして着手
