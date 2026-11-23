# 引き継ぎ書（LinuxQuest 教材拡張）

最終更新: 2026-11-23（Codex 作業継続） / ブランチ: `learning-expansion` / 状態を変えたら必ずこの表も更新する。

## 2026-11-23 最新チェックポイント（この節を優先）

- 利用者の最新指示: 作業を続け、進捗ごとにコミットしてpushする。コミット `6a0f7f1 Add answer review flow and flexible hints` と `30b0fa5 Review lesson wording across curriculum` は作成済み。pushは拒否された。fetch後、origin/learning-expansion が `a7458d6` から `aabd59d` に更新され、ローカルにない18コミットとローカル固有42コミットがあり、通常のmergeは大規模な競合になった。mergeは中止し作業ツリーを復元済み。新コミット後も通常pushはnon-fast-forwardで拒否。force pushは許可されていないため実行しない。最新変更はローカルブランチにある。
- 以前依頼された05:00 JSTのタイマーは起動したが、この会話スレッドが動作中でresumeに失敗した。run.logにthread-store競合が記録され、タイマーによる作業再開は行われていない。
- **レッスン全体の逐読監査は完了**: intro/basic、practice stages 1–34とExtra、advanced/readiness/festivalを分担して確認し、発見箇所を修正。既習コマンドで調べられる既存ファイル名・隠し場所・手順は課題文や事前説明から外してヒントへ。接続先、ユーザー、ポート、新規出力名、要件値は課題文に残す。新概念の説明は維持する。basic18、readiness07、Stage15-3/9など監査中に見つかった個別の問題も修正。
- `engine/guidance.py` で、説明文に埋め込まれた完全解答（複数コマンド列を含む）をヒントから除外。guided/practice/readinessで共有し、静的走査では完全解答の漏れ0件。
- 検証: 全Python suiteは654件成功、50 skip（Stage15-9の最後の文面変更より前）。その後 `test_all_missions`, `test_readiness`, `test_guided_ssh`, `test_lesson_self_contained` を43件成功。Stage15-9変更後にpy_compileとdiff --check成功。Webはbuild成功、npm test 8件成功、E2E 17件成功。E2Eでworkerに画面側専用の`review`コマンドを直接送っていた期待値を、保存データのreview状態確認に修正した。
- デプロイはしていない。作業ツリーはコミット済み。
- これより下の2026-11-22節には再開前の予定・未完了リストが含まれる。事実として残すため削除しないが、上の最新チェックポイントで更新された状態を優先する。

## 2026-11-23 アプリ不足の確認と次の作業

- 保存の実証範囲: 既存E2Eは達成数のリロード保持だけを確認していた。`web/danganlog/tests/e2e/app.test.mjs` に追加し、同じbrowser context（同じlocalStorageプロファイル）でタブを閉じて新しいページを開き直し、選択中レッスン・未完了状態・作業ファイル `memo.txt` の復元を確認。実ブラウザーで成功。`localStorage`のため別端末・別ブラウザープロファイルとの自動同期はない。学習データのJSON export/importは別E2Eで成功。
- 実Linux導線: `/course/real-linux/` を新設。ページ冒頭にサイト内入力欄とPC上のターミナルの違いを説明し、WindowsのPowerShell→Ubuntu、MacのSpotlight→Terminal、Linuxデスクトップのアプリ一覧/一般的なショートカットを案内。その後Windows 10 2004/build 19041以降またはWindows 11向けのWSL 2 + Ubuntu手順と、MacのUTM + Ubuntu Server仮想マシン手順を同じ見出し・敬体・手順形式で記載。Windows・Mac・模擬/実Linux/専用VMの使い分け、公式リンクを付け、共通ナビから移動可能。初心者・日常CLI・開発・サーバー運用の学習経路も記載。
- **残る学習推薦の課題**: 上記の経路は目標別の案内であり、現在の進捗や復習履歴から個人ごとに「次にこれ」を選ぶ推薦機能はまだない。既存データの完了/復習状態のどれを習熟の根拠にするか、到達目標・前提関係と既存レッスン/ネイティブ/VM課題の対応を整理してから実装する。
- 実環境カバレッジの監査: `docs/vm_verification/` にあるVM実証記録とcoverage表の確認は可能。この開発環境には `/dev/kvm` は見えるが、`multipass`、`qemu-system-x86_64`、`virt-install` が見つからず、現状はVMを立ち上げて新しい実動確認を実施できない。実証記録がない項目は引き続き未確認として扱う。
- 追加検証: Web build成功、npm test 8件成功、E2E 19件成功。新規の「閉じて再オープン」永続化テストとWindows/Mac/Linux向け環境案内E2Eを含む。

## 2026-11-22 夜・利用者指示で一時停止（ここを最優先）

利用者は5時間制限を心配して一旦停止し、11月23日05:00（日本時間）からの自動再開を依頼。ユーザーsystemdの一回限りのタイマー codex-training-resume-20261123.timer を有効化し、NEXT=2026-11-23 05:00:00 JST を確認済み。codex exec resume でこのスレッドを再開する。実行ログはユーザーの .local/state/codex-training-resume-20261123/run.log。PC停止やログアウト中は動かず、Persistent設定で次回稼働時に遅延実行する。下記は未コミットのWIP。元の先頭節の「全コミット済み」「これから監査」はこの追記より古い。

### 今回合意した仕様
- 既習の道具を組み合わせれば分かる操作・既存の名前/場所は、課題文だけでなく出題前の説明にも先回りして書かずヒントへ。新概念の説明は必要。
- 1ヶ月後にその問題から再開できるよう、サーバー名・ユーザー名・ポート、新規作成/保存名など調べても分からない指定は残す。
- hintは3段階固定にしない。必要なだけ段階的な助言を示し、最終コマンドはanswerで表示。answer閲覧時点で未クリアでも復習対象へ自動登録し、reset後にhint/answerなしで達成すれば解除。
- force push / push / 本番デプロイは許可待ち。今回も行わない。

### 実施済み・WIPの状態
- 入門24・基礎66・応用46を親が逐読して修正。basic43は鍵名の説明内漏れも削除し、5段階の助言を追加。
- 実践501問（Stage1〜18=159、19〜34=337、Extra=5）を担当が逐読。変更は90+41+5問。合格後だけの解説は維持。
- 達人246・課題まつり251を逐読。文言変更は達人103・まつり182（合計285）問。まつりincidentの鍵、scenarios27の鍵、config06/16の隠し設定等を探索へ。必要なlearner宛先も補足。
- **範囲漏れ: curriculum/readiness.py の ready-01〜08 は未監査・未変更。** 次に読む。
- engine/save.pyにreview辞書、mark_review/finish_review/review_idsを追加。旧実践セーブのanswer=Trueはreview未作成時に一度だけ移行する処理も追加（最後の移行変更は未検証）。
- guided/readiness/実践cli/mainの任意hint・answer即登録・復習一覧・自力再挑戦解除を実装。guidedは選択画面rで絞込、実践とまつりもr。入力例そのもののhintは表示時に除外。
- reset後も正解状態が残るex-users15/32/33とex-services41を修正。同じTerminalで全goal207問を解く→reset→無関係入力拒否を確認しtests/test_guided_reset.pyに追加。fresh時command_eventsも初期化。
- **Webは実装途中・未検証**: public/worker.jsのreview永続化/validation/answer登録/reset後自力解除/review要求、lib/core.jsのreviewItems、components/Dojo.jsxのreview一覧/再開/helpまで担当が編集。新規Webテスト、衝突確認、build/npm/e2eは未実施。
- 作業途中で**別の作業によるTab補完変更**がengine/guided.py、Dojo.jsx、worker.js、e2e、tests/test_completion.py等に入っている。保持する。今回担当の変更と一括で混ぜてコミットしない。初回statusはcleanだった。
- コミット/push/deployは今回未実施。新規tests/test_guided_review.py、test_guided_reset.py、test_practice_assistance.pyも未追跡なので漏らさない。

### 再開時に先に直す点（独立レビュー指摘・未修正）
1. basic18はrmの初出だが、親が説明からrmの名前/書式まで消している。新概念の説明を戻す。
2. basic24のapt removeも入門では未学習なので、新規書式説明を戻す。
3. basic18は元とコピーが同内容。単独再開時にどちらが元か識別できる手がかりを調整（答えのパスの先回りに戻さない）。
4. intro01/20/basic01等の「hintで入力例」という案内を助言/answer分離に揃える。README等にも固定3段階の記載がないか必要範囲を点検。
5. 親の文言修正の独立再レビューはintro24とbasic01〜33/adv01〜21途中まで。basic34〜66とadv後半の見直しを終える。既習説明を削りすぎて新概念まで消さない。
6. Web復習機能のレビュー/テストを追加し、reviewコマンドが教材と衝突しないか確認。旧データimport/export、未クリアanswer→再読込、reset→自力解除、hint使用時は解除しない、vim内answer、任意段階を検証。
7. 全Pythonと501問の統合テスト、サイトbuild/npm/e2eを実行。画像でも代表的な変更問題を確認。検証済み単位で文言/CLI機能/Webを分けて小さくコミットし、HANDOFFを更新。

### 検証の正確な状態
- 親: 初期の既存69件成功。その後guided_review/units/guided/self_contained計52件成功、統合のguided_review/guided_reset/units/readiness/practice/self_contained計45件成功（最後の移行変更/選択Enter調整/Web途中変更より前）。
- 担当: Stage1〜18の159/159、Extra5/5成功。Stage19〜34変更41問の個別テスト成功。readiness/festival26件成功。practice関連35件成功/既存skip1。reset関連28件成功。
- 全Pythonと501問は実行途中で、利用者の停止指示によりSIGINTで止めた。**全体成功とは扱わない**。ログ: /tmp/training-review-python-all.log、/tmp/training-review-missions-all.log。
- Web build/npm test/e2eは今回まだ一度も再実行していない。
- 達人/まつり変更ID作業用JSONは /tmp/expert_audit_changed_ids.json（280件、fes-desktop_hw-11〜15の5件を足すと285）。再集計して正規の監査記録をdocsへ残す作業も未実施。

## Codexへ: いますぐやること（2026-11-22 最新・最優先。ここだけ読めば再開できる）

### 0. 最初に確認する
- `git status --short`（この引き継ぎ書を書いた時点では全てコミット済み）と `git log -12 --oneline`。ブランチ `learning-expansion`。
- Node 22.12 以上が必要（wrangler の要件）。`~/.local/node22/bin` に入れて PATH を通す。無ければ公式の tarball を取得し、チェックサムを検証して展開する。
- サイトのプレビュー: `cd web/danganlog && npm run build && python3 -m http.server 3107 -d out`。ブラウザは `Ctrl+Shift+R` で強制再読み込み。
- テストの実行方法: `tests/` に `__init__.py` は無い。`python3 -m unittest tests.test_xxx ...` と名前を並べる（`discover` は使えない）。`test_all_missions` は長いので別実行。サイトは `cd web/danganlog && npm test` と `npm run test:e2e`（14件）。バックグラウンド実行時に `pkill -f` を使うと自分のシェルも落ちるので使わない。

### 1. 課題文の書き方の原則（利用者の明確な方針。新規・修正のすべてで守る）
- **書かない**: 既習の道具（`ls`、`ls -a`、`cd`、`cat` など）で見つけられること。例: 鍵が隠しフォルダ `.ssh` にあること、既に存在するファイル・フォルダの名前や場所。見つけさせるのが練習になるので、課題文には書かない。迷ったときの導線は、`_HINTS`（基礎）のヒント1・2で、既習の道具を名指しして示す。
- **必ず書く**: 調べても分からないこと。接続先のサーバー名、ユーザー名、ポート番号、保存先として自分で決める名前（出力ファイル名）、作る物の名前など。途中から再開した人が、課題文だけで答えを組み立てられること。
- 実施済み: basic-43（課題文から鍵の場所・名前を外し、ヒントを `ls -a` 誘導に変更）、SSH系（basic-36〜48 の接続先・ユーザー・ポート）、11-6（保存先 verification.txt）。`tests/test_lesson_self_contained.py` が、`user@host`・`-p` のポート・リダイレクト先/`-o` の出力名を検査する（既存ファイルの名前は検査しない）。
- 残り: 全レッスンの課題文・説明を同じ原則で見直す。既習の応用でできることが課題文に書かれていたら削る（候補の洗い出しは正規表現では足りない。人が1問ずつ読むこと）。

### 1.5 最後に確認できていないこと（先に実行して確かめる）
- 最後の教材修正（basic-43 の課題文・ヒント、names.txt などの課題文の差し戻し）の後、**サイトの `npm test` と `npm run test:e2e` は再実行していない**。サイトは教材を `tools/build_web.py` でバンドルするため、`cd web/danganlog && npm run build && npm test && npm run test:e2e`（e2e は15件のはず）で必ず確かめる。
- Python 側は `tests.test_lesson_self_contained tests.test_guided_ssh tests.test_guided tests.test_learning_integration`（64件）が通っている。全体（`test_all_missions` を除く625件）は、課題文を直す前の時点で通過。直した後の全体再実行は未実施。
- サイト版の `ls` 不具合は、公開中の danganlog.com にまだ残っている（最新のビルドを `scripts/deploy.sh` で反映するまで）。

### 1.6 サイト版（web/danganlog）の修正まとめ（Claude 担当分。全てコミット済み。公開は最初の版のまま）

**公開の状態**: Cloudflare Pages のプロジェクト `danganlog`（`https://danganlog.pages.dev/` と `danganlog.com`）には、**最初のデザインの版**が公開されている。以下の修正はすべて未公開。公開は `cd web/danganlog && scripts/deploy.sh`（利用者が実画面を見てから）。

**A. 不具合の修正（教材の動作）**
1. `ls` が道場の「レッスン一覧」に横取りされ、ファイル一覧を使うレッスンが進めなかった。`components/Dojo.jsx` の `case 'menu': case 'ls': ...` から `ls` を削除（一覧は `menu` / `lessons`）。e2e に「レッスン04で `ls` を実行するとファイル名が出て達成になる」テストを追加。サイト独自コマンド（help clear theme simple data course modes progress goto open next prev hint answer reset check menu lessons）が、基礎・応用・ミッションの正解コマンドと衝突しないことは確認済み（`21-12` の `mode http` は別コマンドの引数なので無関係）。新しい別名を足したら必ず再確認する。
2. 課題を達成した後、**何も入力せず Enter で次の問題へ進む**（`submit` で空入力かつ `hasNext` のとき `runLocal('next')`）。達成前の空Enterは何もしない。案内文は「達成済み。Enter で次の問題へ進めます。」。
3. プロンプトの色分け: `Ps` の正規表現が `learner@dojo-local:~` のコロン区切りに合わず全体が緑になっていた。`user@host` を太字の緑、パスを太字の青にする（`:` と `$` は通常色）。
4. 説明文は段落ごとに `<p>` に分割して描画（以前は1つのブロックで `white-space: pre-wrap`）。
5. **Tab 補完を実装（オプション、初期は切）**。利用者の方針: 補完は打つ練習を減らすので、あくまで任意。`completion on|off`（別名 `tab`）または画面下の「Tab補完」ボタンで切り替え、`localStorage`（`dangan-log:prefs:v1` の `completion`）に保存。切のあいだ Tab は通常のフォーカス移動で、スマホの「Tab」ボタンも出さない。候補の計算は Python 側 `engine/guided.py` の `Terminal.complete(line)`（最初の語はコマンド名、2語目以降はいまの場所のファイル・フォルダ。隠しファイルは `.` で始めたときだけ。引用符・記号・オプション・エディター操作中は補完しない。状態は変えない）。ワーカーに `type: 'complete'` を追加（`public/worker.js`）、画面側は `components/Dojo.jsx` の `complete()`（候補が1つなら補完、複数なら共通部分まで補完して一覧を出す。最初の語は道場のコマンドも候補に加える）。テスト: `tests/test_completion.py`（5件）と e2e 2件。`he` は `head` と `help` の両方に当たるので補完されない（本物のシェルと同じ）。
6. **最初の画面の「困ったときの操作」一覧（hint/answer/menu）を削除**（利用者の方針: いらないものは極力省く）。`help` と「? 操作ヘルプ」ボタンで同じ説明が出る。

**B. デザイン（最終版 `ead16d7`。これが現在のソース）**
- 方針: 実際の Ubuntu 24.04 の GNOME Terminal を基準にする（利用者の指示）。この環境の実設定を読み取って寄せた: フォント Ubuntu Sans Mono 13pt、プロンプトは `01;32m`（緑）の `user@host` と `01;34m`（青）のパス、GNOME のパレット。角丸・装飾・定型AI風カードは使わない。行間は1.25、段落の余白と見出し・太字なし。出力の直後に入力行が続き、ナビとステータスは画面下の小さな文字。
- フォント: `public/fonts/ubuntu-sans-mono-latin.woff2`（Latin のみ、可変ウェイト）と `UFL-Ubuntu.txt`（ライセンス）を同梱。`@font-face` は `local("Ubuntu Sans Mono")` を先に試す。日本語は `Noto Sans Mono CJK JP`（このPCの `fc-match` が端末で実際に選ぶフォント）。`.gitignore` は `public/fonts/*.woff2` と `UFL-*.txt` を許可済み。
- 配色（`app/globals.css` の `:root`、`light-dark()`）: ダーク = 背景 `#300a24`、文字 `#ffffff`、緑 `#33da7a`、青 `#62a0ea`、黄 `#e9ad0c`、赤 `#f66151`。ライトは白地。**背景 `#300a24` は推定**（テーマ連動のため端末の設定から読めなかった）。実際の端末と見比べて、違えば `--bg` `--panel` `--raise` `--line` を直す。既定は `color-scheme: dark`（利用者の端末が Yaru-dark のため）。
- 一画面に収める: PC幅（1280×720）ではページのスクロールが出ない。幅が狭いと、説明ペインの中だけがスクロールする。
- 検証: スクリーンショットは、1280×720（ライト/ダーク）と 375×700 で目視。e2e 15件（旧14 + `ls` 1件）が、最終デザインで通過していた。

**C. 経緯と、作り直しの背景（無駄を繰り返さないため）**
- 利用者は、最初の版（茶色・紫・クリーム色の混在、左右分割、色付きボタン）を「ダサい」と言い、ミニマル、AIチャット風、ゲーム風、ハッカー風などを試した末、「実際のLinuxのターミナルをそのまま」と指示した。**色や雰囲気を推測して変えても外れる。実際の端末（この環境で `gsettings` と `fc-match` が読める）を基準にすること。** 「ダサい」の正体は、行間が広い・Markdown風の見出し/太字・角丸・ボタン・帯などの Web ページらしさだった。
- 利用者の最後の指摘: 「日本語のフォントにもAI感が強い」「色やフォントも実際の端末に似ていない」。後者は、色の読み取り（上のB）とフォント同梱で対処したが、**利用者による再確認は未了**。前者は未対応（現在の日本語は本物の端末と同じ Noto Sans Mono CJK JP）。

**D. 既知の宿題・技術的負債（優先順）**
1. （対応済み）`app/globals.css` を1本に整理した。整理の前後で、12枚のスクリーンショット（PC/スマホ/タブレット、ライト/ダーク、シンプル表示、ダイアログ、講座ページ）が0ピクセル差、e2eも全通過。今後も、CSS を触ったら同様に前後比較する（画像と、全要素の計算済みスタイルの比較）。
2. **アクセシビリティ検査（axe、light/dark × 375/1280）の制約**: 文字色のコントラスト 4.5:1 以上。これまでに落ちた例は、ライトのバッジ文字、ダークの Enter ボタン文字。配色を変えると必ず再実行する。また、キーボード操作のテストは `.field:focus-within` に **`box-shadow` が `none` でない**ことを要求する（現在は薄い下線）。
3. 講座ページ、シンプル表示、ダイアログ、ライトテーマ、スマホ幅は、新デザインで目視確認済み（崩れなし）。スマホの前後移動の行は「問題 …」と省略表示になっていて、読みにくい（未対応）。
4. 狭い幅（375px）では、説明ペインが画面の約半分を占め、最後の行が切れる。説明を折りたたむなどの改善余地がある。
5. 左右の広告枠を入れる場合は、`.workbench > *` の `max-width: 110ch` の外側（左右の余白）に置く。端末の入力欄・操作ボタンの近くには置かない。
6. 公開前に必ず `cd web/danganlog && npm run build && npm test && npm run test:e2e`。教材（`curriculum/`・`engine/`）を変えたら、サイトのバンドル（`tools/build_web.py`）が変わるので同じく再実行。

### 2. 利用者の指摘と、残りの作業（優先順）
1. **「正しい答えなのに次へ進まない」問題の洗い出し**: 判定は `engine/guided.py` の `matches()` が、入力を `shlex.split` した語の並びを、`command` と `accept` のどれかと**完全一致**で比べている（`goal` がある課題は状態で判定）。そのため、オプションの順序違い（例: `ssh -i 鍵 -p 2222 ...` と `ssh -p 2222 -i 鍵 ...`）や、等価な書き方が不正解になる。
   - 基礎66問と応用46問を見直し、順序が入れ替わっても正しい入力は `accept` に追加するか、`goal`（結果で判定）に切り替える。特に ssh / scp / chmod / grep / sort などの複数オプション。
   - 実際に起きた例: 利用者が接続先を `training-serve`（r抜け）と入力して先へ進めなかった。課題文に接続先が無かったため（修正済み）。エラー文は入力値を示す形に改善済み。
2. **既習の道具で探させる問題の見直し**: 上の原則1に沿って、課題文で場所を教えすぎている問題を削り、ヒント1・2で `ls -a` や `ls` フォルダ名 など既習の道具へ誘導する。候補は `basic-18`（notes/archive.txt）、`intro-07`（.memo）、`adv-38`（logs/old-*.log）。全問の `_HINTS`（基礎）と応用の hints を見直し、1つ目は考え方、2つ目は使う道具、3つ目で答え、の段階を守る。
3. **課題文だけで再開できること**（実施済みの範囲と、残り）:
   - 基礎・応用136問の監査は完了（SSH系の接続先・ユーザー・ポート、11-6の保存先）。再発防止のテストは上の原則1のとおり。
   - ミッション形式（stage系、501問）も同じ観点で調べた。本当に不足していたのは 11-6 のみ（上の1）。検出された他の16件は、一時ファイル名、gitの設定キー、SQLの別名などの誤検出だった。監査の方法: 各ミッションを `runner.prepare` で用意し、問題文・達成条件・作業フォルダ内のテキストに、想定解の `user@host`・IP・`-p` のポート・ファイル名が出てくるかを見る。その後、名前を別の名前に置き換えて想定解を実行し、判定が落ちるかで必須かどうかを判定する（置き換えは疑似的に壊れることがあるので、判定コードも読んで確認する）。このスクリプトは作業用の場所にあり、リポジトリには未収録。必要なら `tools/` に再作成する。
4. **サイトのデザイン**（コミット済み、未公開）:
   - 現在の版（`ead16d7`）は、実際の Ubuntu 24.04 の GNOME Terminal の設定を読み取って寄せたもの。フォントは Ubuntu Sans Mono（`web/danganlog/public/fonts/` に同梱、ライセンス文書つき）、色は GNOME のパレット、行間は1.25、プロンプトの `user@host` は太字の緑、パスは太字の青。ナビとステータスは画面下部の小さな文字。
   - **未確認の仮定**: 背景色は Ubuntu 標準の `#300a24` と推定（テーマ連動のため設定から読めなかった）。利用者に実際の端末の色と見比べてもらう。
   - 利用者の最後の指摘は「日本語フォントにAI感が強い」。現在の日本語は Noto Sans Mono CJK JP（fc-match が実際の端末で選ぶフォントと同じ）。別の日本語等幅フォント（IPAゴシック系、BIZ UDゴシック、ドットフォントなど）を試すなら、サイト同梱（OFLなど再配布可能なもの）で、`unicode-range` で分割して容量を抑える。
   - **サイト版で `ls` が道場のメニューに横取りされていた不具合を修正済み**（`components/Dojo.jsx` の別名から `ls` を削除、e2eテスト追加）。サイト独自のコマンド名（help、clear、theme、simple、data、course、modes、progress、goto、open、next、prev、hint、answer、reset、check、menu、lessons）が、レッスンの正解コマンドと衝突しないことを、基礎・応用・ミッションの全問で確認済み（衝突は ミッション 21-12 の `mode http` のみで、これは別のコマンドの引数なので問題なし）。新しい別名を足すときは必ず再確認する。
   - Enter で次の問題へ進む機能は実装・確認済み（課題を達成した後、空のEnterで進む。`components/Dojo.jsx` の `submit`）。
   - 利用者は、角丸・定型のAI風カード・グラデーションを嫌う。実際の端末の見た目を基準にする。
5. **デプロイ**: `cd web/danganlog && scripts/deploy.sh`（`--dry-run` あり）。設定は `.env.deploy`（Git管理外）。Pages のプロジェクト `danganlog` は作成済みで、`https://danganlog.pages.dev/` に最初の版が公開済み。独自ドメイン `danganlog.com` はこのプロジェクトに割り当て済み（以前そこにあった別のサイトは外した）。**最新のデザインと教材修正は未公開**。利用者が見た目に満足してから実行する。
   - 利用者の Cloudflare 認証（`wrangler login`）は DNS の編集権限を持たない。DNS レコードの追加・変更は、利用者がダッシュボードで行う。
6. **公開履歴の書き換えの反映**: 公開リポジトリの履歴から、個人のドメイン、ローカルの絶対パス、認証情報の保存場所の記述を `git filter-branch` で除去した（ローカルのみ）。GitHub に反映するには `main` と `learning-expansion` の force push（`--force-with-lease`）が必要。**利用者の明示的な許可が出るまで push しない**。許可が出ていない点を、必ず確認すること。force push しても、古いコミットのSHAは GitHub 上にしばらく残り、既存のクローンやフォークにも残る。
7. **収益化（保留）**: 広告は、デザインと公開が固まってから。AdSense は審査があり、プライバシーポリシー、運営者情報、外部送信の公表、同意表示が必要。`web/danganlog/README.md` の「第三者へ接続しない」記述も変わる。端末の入力欄や操作ボタンの近くに広告を置かない（誤クリック扱いの規約違反になる）。左右の余白に置く案が出ている。

### 3. 利用者の方針（再掲・厳守）
- 絵文字を使わない。検証していないものを検証済みと書かない。失敗は失敗と報告する。
- このサイトの公開先は danganlog.com のみ。利用者の他のサイト・ドメイン・他のプロジェクトには触れず、文書にも書かない。ローカルの絶対パスや個人情報も、公開リポジトリには書かない。
- コミットは小さく頻繁に。作者は既存の `LinuxDOJO contributors`（`git -c user.name=... -c user.email=...`）。コミット末尾に Co-Authored-By を付ける。`.gitignore` は許可リスト方式で、新規ファイルは allowlist を確認する。
- 利用者は質問を重ねられるのを嫌う。確認が必要な破壊的操作（force push、本番デプロイ、削除）以外は、決めて進め、実画面のスクリーンショットで確認してから報告する。

## 最短の再開手順（次の担当はここから）
1. `git status --short` と `git log -12 --oneline`。ブランチは `learning-expansion`。完了単位で検証して細かくコミットする。**未コミットを一括で追加しない**（下の担当別ファイルを確認）。pushとデプロイはまだしない。
2. この文書の「最新チェックポイント」を読む。前Claudeのバックグラウンド担当は終了しており、その完了待ちをしない。新セッションでCodex担当も消えていれば、ディスクとVMから続行する。
3. 実VMの合格根拠は `docs/vm_verification/*.md` の実出力。`tools/vmtest/scenarios/*.sh` は再現手順。`python3 tools/vmtest/verify_scenario.py VM tools/vmtest/scenarios/MOD.sh /tmp/MOD.log`。setup→checkだけでは通常不合格で、学習者操作とbreak・修復を含める。
4. `python3 -m engine.toolbox audit`。全体検証は `python3 -m unittest discover -s tests`。NodeがPATHになければ下のNodeパスを追加してからサイトのbuild/test/E2Eを実行する。未導入によるskipを合格に数えない。
5. 機能単位の確認後、担当ファイルとこの文書だけを追加してコミット。検証前の作業保存は `WIP` と明記し、実VM未検証を維持する。

## 最新チェックポイント（2026-11-22 / 全変更コミット・最終検証完了）

- 利用者の追加UI指摘は `Dojo.jsx` / `globals.css` で対応し、操作導線の記録を `docs/UI_REVIEW.md` に追加。問題移動（前の問題/次の問題/問題一覧）を常時表示し、達成前の次ボタンは無効化して理由も表示。初回の道場操作とLinuxコマンドを分けて説明。新規ブラウザーで初期問題を回答→達成→「次の問題へ」→問題02まで手動確認。1280px/375pxで横はみ出しなし。スクリーンショット `/tmp/dangan-next-redesign-ready.png`, `/tmp/dangan-next-redesign-375.png`, `/tmp/dangan-next-redesign-02.png`。今回の自動テスト/buildは未実行。プレビューは `http://127.0.0.1:3106/`。デプロイ・push禁止は継続。

### 確定しているもの
- 周辺機器の模擬31問: `2ce3477`。初期未達成・正解・罠拒否・ホスト操作禁止の11テスト成功。実機の証明ではない。
- FTP/ACL: `a5bec87`。実VMで正常・故障/抜け道拒否・reset、2周目setup/reset成功。ACLのgetfacl誤判定を修正。
- 講座の4区分対応: `623c379`。未検証を独立表示し、集計と目標行を照合。生成済みデータもbuildのたびに更新する。
- firewall: `381b0bc`。実nft/netns、HTTP部分受信の誤判定を修正。通信・抜け道拒否・再読込・専用資源の撤去を確認。
- localca: `045a20b`。実TLSテストのpipe未closeを修正。ResourceWarningをerrorにして4テスト成功。
- 前担当の途中修正保存: `5e93b15`。guard/libvirt/netlink/pam/podman/postgres/systemdadv/tunedは、この時点では**実VM未検証**。その後の個別完了記録を優先する。
- Git30-13: 固定HEAD~5を誤答としていたが、ランダムな故障位置と一致する場合があった。誤答を必ず正常なgoodタグへ変更（採点条件は変更なし）。個別検証後、全501問PASS: `/tmp/training-release-missions.log`。
- Vim31-17: ERROR行をFIXマーカーで上書きした際の期待件数を修正。生成後の実内容で集計。ERROR行/INFO行の両ケースの回帰テストと実Vim操作31-17成功。
- ターミナル起動: `b91a92f`。ペンギンと青/紫/シアン、瞬き・ウインク・笑顔。`LQ_NO_ANIMATION=1`で静止。NO_COLOR/非TTYでも静止。PTYで起動とEnter終了を確認。関連10テスト成功。
- Podman: `170ae81`。rootless Quadlet、公開範囲・実bind mount/heartbeat、UID/GID対応・起動失敗修復・user manager再起動・2周の専用資源撤去を確認。実出力 `g7-podman.md`。
- PostgreSQL: `1b1704c`。実VM検証と修正を取り込み。ロール属性・SCRAM・実効HBA/再起動設定・最小権限・論理復元・物理backupの由来を確認。`g6-postgres.md`に公式runner実出力。
- 常用の安全操作: `ffed7f8`。native `safe-cleanup`（40本目）、NUL区切り・特殊ファイル名・リンク非追跡・退避・隔離移動・復元。実ツール3テスト成功。toolbox関連42テスト成功/skip14。
- users/lynis: `aabd59d`。最小sudo復旧、Lynis実監査59→60・対象警告消失・誤設定拒否・reset。実出力は `g1-users.md`, `g8-lynis.md`。
- サイトUI: `4497b0f`。`docs/UI_REVIEW.md`に設計と実画面確認を記録。単調な配色・角丸カード・偽ウィンドウ操作を廃し、説明/端末の2ペインと索引へ。デプロイは未実行。
- 最終検証: Python624件成功/skip48（181.446秒）、実践501/501 PASS（135.5秒）、サイトbuild/npm7件/course4件/E2E14件成功。`docs/VALIDATION_2026-11-22.md`。

### 担当別の完了記録（すべて取り込み済み）
| 担当 | 所有ファイル | 再開地点 |
|---|---|---|
| site_ui (Astra) | web/danganlog/app と components | 完了。4ページ×3幅の実画面確認、axe8画面0件。親も画像確認、build/npm7件/course4件/E2E14件成功。利用者の見た目確認待ち。dev3106 |
| vm_postgres (Sol) | postgres.sh / scenarios/postgres.sh / g6-postgres.md | 完了。公式runner exit0、親で単体4件成功。標準mainを保ち2周の専用資源撤去を確認。物理復元からの起動/OS再起動は未検証 |
| vm_podman (Sol) | podman.sh / test_vm_podman.py / scenarios/podman.sh / g7-podman.md | 完了。公式runner exit0、親で単体4件成功。ユーザーsystemd再起動後に自動復帰、2周の残骸なし。OS再起動は未検証 |

### 次に着手する順
1. **最終検証は完了**: Python624件成功/skip48、実践501/501 PASS、サイトbuild/npm7件/course4件/E2E14件成功。`docs/VALIDATION_2026-11-22.md` を参照。次は利用者のUI確認と、下記未完了項目から始める。
2. `docs/DAILY_USE_AUDIT.md` の常用時の抜けを実操作課題で補う（単なるコマンド名追加にしない）。
3. 未完了VMモジュールの再検証。guard/libvirt/netlink/pam/systemdadv/tunedなどはWIP保存済みでも通過扱いにしない。RHEL3本はRHEL VM未用意。
4. 今回の最終テストは上記のとおり完了。今後新たに変更した範囲の検証を行い、必要な時に全体を再実行する。見た目の利用者確認前にデプロイしない。

- daily_cron担当は制限残25%のため設計確認だけで停止。リポジトリ/VM変更なし。実装は未着手で、次回はDAILY_USE_AUDITの方針から開始する。

### 環境とログの場所
- Node 22 (20.9以上) を PATH に用意する（無ければ別途導入）。
- VM: `~/.cache/linuxdojo-vm/vms/`。g1-app/client、g3-app〜g8-appを保持。`up NAME` で停止済みを再開できる。g6/g7の担当作業は完了し、専用資源は撤去済み。記録を確認して再利用する。
- `vmtest.py install` は共有 `bundle/` を書き換えるため並列実行しない。VM内の試験自体は別VMなら並列可。
- 一時ログ: `/tmp/training-*.log`。**実VM通過ログはdocsへ保存するまで完了としない**。画像: `/tmp/dangan-{terminal,course,detail,coverage}-{1280,375,320}.png`。
- サイトdev `http://127.0.0.1:3106` は親担当で起動しHTTP200確認済み。既存3000は変更しない。開発サーバーは公開デプロイではない。

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
- Cloudflare: `wrangler login` 済みの前提。デプロイは `web/danganlog/scripts/deploy.sh`（設定は `.env.deploy`、Git管理外。手順は `web/danganlog/README.md`）。利用者の見た目確認後に実行する。

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
