# 引き継ぎ書（LinuxQuest 教材拡張）

最終更新: 2026-11-21 / ブランチ: `learning-expansion` / 状態を変えたら必ずこの表も更新する。

## 🔰 再開手順（別のAI／別セッションはまずここから）
1. `git status` と `git log --oneline | head` を見る。作業は `learning-expansion` ブランチ。**未コミットの課題ファイルがディスク上に残っていることがある**（コミットはStage全体の統合テスト後にまとめて行う運用のため）。
2. `python3 tools/stage_status.py` を実行する。**この出力が正**で、下の表より優先する。
   - `STUB`（1行だけ）= 未作成。作成を割り当て直す。サブエージェントが作成中の可能性もあるので、ファイルの更新時刻（`ls -l curriculum/`）が直近なら数分待つ。
   - `WRITTEN` = 課題あり。ただし**検証済みとは限らない**。必ず `python3 tests/test_all_missions.py <ID...>` で確認。
3. 課題ファイルを書くときの仕様は `docs/STAGE_BRIEF.md`（共通指示）。新Stageの配線は下の「配線の仕組み」。
4. 統合が済んだら: `tests/test_progress.py` の総問数・ステージ別内訳・ランク境界を更新 → `python3 -m unittest discover -s tests` → README更新 → コミット。
   - 注意: 課題が増えたら `test_progress.py` の件数を実態に合わせる。現在の期待値は501問。
5. 常用コースは `docs/LINUX_DAILY_USE.md` と `docs/coverage.md` を読み、`python3 -m engine.toolbox audit` で参照を検査する。`python3 tools/audit_coverage.py --list` は名前の出現確認だけなので、未登場の数合わせでStageを増やさない。
6. この文書の表を更新してコミットする。

### サブエージェントの使い方（今回のやり方）
- 1Stage = 1エージェント。担当ファイル以外は編集させない（配線は親が先に済ませる）。
- 指示は `docs/STAGE_BRIEF.md` ＋ 担当Stageの「必須キーワード一覧」。キーワードが課題内に名前で出ているか、最後に grep で検証する。
- エージェントの自己報告は鵜呑みにせず、親が全体テストを再実行する。他エージェントが書き途中のファイルがあると一時的に import エラーになる（待って再実行）。

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

## 目的
Linuxを学ぶうえで「使うもの・使わなくても必要なもの」を網羅した実践課題を用意する。
エンジニアが普通に入れて使う道具（Git・Vim・SSH・tmux・jq など）の**使い方**まで含める。

## 現在地（一目で）
| 区分 | 状態 | 備考 |
|---|---|---|
| Stage 1〜13（102問） | ✅ 完了・コミット済 `f7feabe` | 全問 PASS を確認済み |
| Stage 14〜18（62問） | ✅ 完了・コミット済 `e833997` | 実践は計164問、unittest 246件 OK |
| ui.clear のスクロールバック消去 | ✅ 実装済（`e833997`） | **実端末での目視は未確認** |
| Stage 19〜34（337問） | ✅ 統合テスト済み | 全501問 PASS（130.8秒）。Stage 30も28問すべてPASS |
| 統合テスト・READMEの問数更新・コミット | ✅ 完了 | 全501問 PASS、unittest 246件 OK、compileall・diff --check OK。README・進捗テストは501問 |
| 資格試験の公式範囲との全項目対応表 | ⏳ 未着手 | LPIC/LinuC/RHCSA 範囲 ↔ 課題ID |
| 「必要ツール」宣言の仕組み | ✅ 常用20実習に実装 | 既存501問への一律適用は未実施 |
| 常用コース・対応表・実機検証 | ✅ 追加 | 上の「常用コースの追加」を参照 |

## Stage 一覧（ID・内容・状態）
状態の凡例: ✅統合テスト済 / 📝作成済(未統合テスト) / 🔄作成中 / ⏳未着手。2026-11-21に全501問の初期状態・誤答拒否・想定解・メタデータを実行検証済み。記録診断や静的検査の限界は下表に残す。

| Stage | 内容 | 目安問数 | 状態 |
|---|---|---|---|
| 14 | ブート・カーネル・ハード | 12 | ✅ |
| 15 | ストレージ構築 | 12 | ✅（実機mkfsは未使用、記録診断中心） |
| 16 | SELinux/ACL/属性/資源制限 | 12 | ✅ |
| 17 | ネットワーク管理・共有・パッケージ・バイナリ調査 | 12 | ✅（iconv/rsync/xxd に実依存） |
| 18 | プロセス・GPG・コンテナ基盤・Ansible ほか | 14 | ✅ |
| 19 | 補完（tune2fs・hexdump・firewall-cmd・ausearch 等） | 16 | ✅ 統合テストPASS（16/16 PASS） |
| 20 | 暗号化・VPN・SSHトンネル | 16 | ✅ 統合テストPASS（16/16 PASS） |
| 21 | DNS・DHCP・メール・LDAP・負荷分散 | 16 | ✅ 統合テストPASS（16/16 PASS。21-2/21-16 は複数話題を統合） |
| 22 | 仮想化・NAT・Kubernetes・IaC・監視 | 16 | ✅ 統合テストPASS（22-6/22-10は模範解答を記録から解析してJSONを作る方式に修正し、個別テストPASS。Ansibleは対比のみ） |
| 23 | バックアップ・DB・ストレージ応用・ログ運用 | 16 | ✅ 統合テストPASS（16/16 PASS。実ツールは使わず記録/設定検査） |
| 24 | 正規表現・シェル上級・パッケージ作成・カーネルビルド | 18 | ✅ 統合テストPASS（24-10〜15 の一部はトークン検査のみ=コマンドを実行しない） |
| 25 | ハッシュ・テキスト・シェル組み込みの総ざらい | 24 | ✅ 統合テストPASS（xzless/zless/znew は名前のみで未実行） |
| 26 | ファイルシステム・ブロックデバイス工具 | 22 | ✅ 統合テストPASS（22/22 PASS。エージェント報告は「pending」だけだったが成果は有効） |
| 27 | プロセス・資源・システム情報 | 24 | ✅ 統合テストPASS |
| 28 | ユーザー管理・systemd周辺・kmod・/etc設定 | 24 | ✅ 統合テストPASS（実行せず記録・設定の検査のみ） |
| 29 | 低レベルネットワーク・パッケージ・man・SSH補助 | 24 | ✅ 統合テストPASS（実行せず記録・設定の検査のみ。ssh-add/tldr は軽い扱い） |
| 30 | Git実践 | 28 | ✅ 統合テストPASS（28/28。APIエラー後もファイルは残存） |
| 31 | Vim・nano・Emacs | 20 | ✅ 統合テストPASS（emacs/ctags は無く記録診断。`:%s///gc` と `"+` は説明のみで非実行） |
| 32 | 開発者ツールボックス（jq/curl/fzf/rg ほか） | 26 | ✅ 統合テストPASS（fd/fzf/bat/tree/ncdu などは1問に統合。yq/sqlite3/stow は無くフォールバック） |
| 33 | 言語環境・ビルド・デバッグ・品質ツール | 22 | ✅ 統合テストPASS（gcc/make/cmake/gdb/valgrind/shellcheck 等は実行せず静的検査・記録診断のみ） |
| 34 | SSH・tmux・リモート作業 | 25 | ✅ 統合テストPASS（tmux/sshd/sshfs は実行せず記録・設定検査。ssh 不在時のフォールバックは未検証。34-3 は Stage 20 と一部重複） |

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
