# LinuxDOJO

# 🐧 LinuxQuest — ターミナルで鍛える実践型 Linux & Docker 学習RPG

**本物の bash** でコマンドを打ちながら、サーバーで起きるリアルなトラブル（ログ調査・権限ミス・暴走プロセス・ポート競合・落ちるコンテナ…）を解決していく対話型 CLI 教材です。
文字列一致の「なんちゃって判定」ではなく、実行後の **ファイル構造・中身・パーミッション・シンボリックリンク・プロセス状態・環境変数・コマンド履歴・終了コード** を Python の判定エンジンが実際に検査します。

- 全 **59 ミッション**（Stage 1〜7 で 54 問 ＋ Extra 実践 5 問）＋ **小ネタ図鑑 10 選**
- ゲーム本体は Python 3 標準ライブラリ ＋ bash（各課題で使う Linux コマンドは `--check` で確認）
- 段階的ヒント3段階・模範解答と徹底解説・クリア時の「実務ワンポイント解説」
- ランク（Lv.1 ターミナル見習い → Lv.MAX 伝説のシェル仙人）・称号・スコア・進捗ダッシュボード
- Docker が無い環境でも Stage 5・7 の Docker 課題は **シミュレーションモード** で自動的に遊べる

---

## 🚀 起動方法

```bash
./start.sh
```

これだけです。タイトル画面 → Enter → `[1] 続きから` で最初のミッションが始まります。

| コマンド | 内容 |
|---|---|
| `./start.sh` | ゲームを起動 |
| `./start.sh --test` | 全ミッションの自動テストを実行 |
| `./start.sh --check` | 必要コマンドと Docker が使えるかを確認 |

動作確認環境: Ubuntu 24.04 / bash 5 / Python 3.12（Python 3.8 以上で動作）

---

## 🎮 遊び方

ミッションを選ぶと、**専用のサブシェル（本物の bash）** が起動します。

```
 LQ 2-7  workspace/stage_02 $ awk '$9 == 500 {print $1}' access.log | sort | uniq -c | sort -rn > report.txt
  ✨ 達成条件を満たしたようです！ check と入力して判定しましょう。
 LQ 2-7  workspace/stage_02 $ check
```

タブ補完・パイプ・リダイレクト・`Ctrl+R` 履歴検索・`Ctrl+Z`/`bg`/`fg` のジョブ制御など、普段の bash の機能がそのまま使えます。

### ゲーム内コマンド（サブシェル内でいつでも使えます）

| コマンド | 説明 |
|---|---|
| `mission` | 問題文・達成条件・作業ディレクトリを再表示 |
| `hint` | 段階的ヒント。1回目: 考え方 → 2回目: 使うコマンド → 3回目: 具体的なオプション例（`hint 2` で段階指定） |
| `answer` | 模範解答と、そのコマンドが何をしているかの徹底解説（獲得スコア半減） |
| `check` | 達成判定。クリアすると演出＋実務ワンポイント解説が出て、Enter で次の問題へ |
| `submit <答え>` | 調べた値（合言葉・PID・ポート番号・エラーコードなど）を提出して判定 |
| `reset_mission` | この問題のサンドボックスを初期状態に戻す（壊しても一発で復元） |
| `skip` | この問題を飛ばして次へ |
| `menu` | メインメニューへ戻る（`exit` / `Ctrl+D` でも可） |
| `lqhelp` | コマンド一覧 |

### スコア・ランク・称号

- 1問 100pt。ヒントを見るたびに 1段階 -10pt（最大 -30pt）、`answer` 閲覧で 50pt
- クリア数でランクアップ: Lv.1 ターミナル見習い → Lv.2 ディレクトリ探検家 → Lv.3 パイプライン職人 → Lv.4 パーミッションの番人 → Lv.5 サーバー守護神 → Lv.6 ネットワーク航海士 → Lv.7 コンテナ魔術師 → Lv.8 自動化の達人（44問）→ Lv.9 本番運用マスター（52問）→ **Lv.MAX 伝説のシェル仙人**（全59問）
- ステージを全問クリアすると称号を獲得
- 進捗は `save_data.json` に自動保存（メニューの「設定」から初期化可能）

---

## 📚 カリキュラム

### 📁 Stage 1：超基礎・ファイルシステムと基本操作（8問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 1-1 | 現在地と隠しファイル | `pwd` `ls -la` `cat` |
| 1-2 | 倉庫で宝探し（cd の極意） | `cd`（相対/絶対/`cd -`）`ls -R` |
| 1-3 | 最後に更新されたログはどれ？ | `ls -lht` `ls -t \| head` |
| 1-4 | プロジェクトの雛形を一撃で作れ | `mkdir -p` `touch` |
| 1-5 | 作業前のバックアップは命綱 | `cp -r` `cp`（入れ子の罠） |
| 1-6 | rm -rf は慎重に | `rm -rf` glob の確認 |
| 1-7 | 巨大ログの覗き見術 | `head -n` `tail -n` `less`（`/` 検索） |
| 1-8 | 【実践】散らかった機密ファイルの整理 | 隠しファイル探索 `mkdir -p` `mv` |

### 🔍 Stage 2：テキスト処理・検索・パイプとリダイレクト（8問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 2-1 | リダイレクトの使い分け | `>` `>>` `2>&1` `2>/dev/null` |
| 2-2 | 大文字も小文字もまとめて grep | `grep -i` `grep -c` `wc -l` |
| 2-3 | ソースコードに埋まった秘密を暴け | `grep -rl` `2>/dev/null` |
| 2-4 | コメントと空行を取り除け | `grep -Ev '^\s*(#\|$)'` 正規表現 |
| 2-5 | 障害の『前後』を読む | `grep -C` `-A` `-B` |
| 2-6 | find で探して、古いものを片付ける | `find -type f -name -size -mtime -delete` |
| 2-7 | 【実践】500エラーの犯人IPランキング | `awk` `sort` `uniq -c` `sort -rn` |
| 2-8 | CSV の列抽出と設定の一括置換 | `awk -F,` `cut` `sed -i 's///g'` |

### 🛡️ Stage 3：パーミッション・プロセス・環境変数・監視（8問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 3-1 | パーミッションを数字で操る | `chmod 755/644/600` `umask` |
| 3-2 | 記号モードで差分だけ変更する | `chmod u+x` `chmod o-w` |
| 3-3 | リンクで切り替えるデプロイ術 | `ln -sfn` リンク切れ修復・ハードリンク `ls -li` |
| 3-4 | 環境変数と PATH の仕組み | `export` `PATH` `env` `which` |
| 3-5 | 言うことを聞かない暴走プロセス | `ps aux \| grep` `pgrep` `kill` → `kill -9` |
| 3-6 | ジョブ制御: 端末を手放さずに待つ | `&` `Ctrl+Z` `bg` `fg` `jobs` |
| 3-7 | サーバーの健康診断レポート | `df -h` `free -h` `uptime` |
| 3-8 | 【実践】ディスク逼迫と起動しないアプリ | `du -sh` `sort -h` `chmod +x` `&` |

### 🌐 Stage 4：ネットワーク・通信デバッグ・アーカイブ（8問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 4-1 | tar で固める・覗く | `tar czvf` `tar tzvf` |
| 4-2 | 展開先を指定せよ | `tar xzvf -C` `zip -r` `unzip -d` |
| 4-3 | curl で API を叩く（GET とヘッダ確認） | `curl -s -o` `curl -I` |
| 4-4 | curl で JSON を POST せよ | `curl -X POST -H -d` |
| 4-5 | Address already in use を解決せよ | `ss -tlnp` `lsof -i :PORT` `kill` |
| 4-6 | 疎通確認と名前解決 | `ping -c` `dig`（NXDOMAIN）`getent hosts` |
| 4-7 | SSH の設定と rsync の差分同期 | `~/.ssh/config` `ssh -G` `chmod 600` `rsync -avz --delete` |
| 4-8 | 【実践】隠されたサーバーからトークンを奪取せよ | `ss` → `curl` → `tar czf` |

### 🐳 Stage 5：Docker & コンテナ実践テクニック（7問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 5-1 | はじめてのコンテナ起動 | `docker run -d --name -p` `docker ps` |
| 5-2 | 消えたコンテナの死因を探れ | `docker ps -a` `docker logs` `docker rm` |
| 5-3 | コンテナの中に潜入せよ | `docker exec -it ... sh` `docker inspect` |
| 5-4 | ボリュームと環境変数、そして使い捨てコンテナ | `-v` `-e` `--rm` |
| 5-5 | 壊れた Dockerfile を直してビルドせよ | `docker build -t` 軽量イメージ・レイヤーキャッシュ |
| 5-6 | docker compose で複数コンテナを束ねる | `docker compose up -d / ps / logs` |
| 5-7 | 【実践】起動直後に落ちるコンテナを救え | `docker logs` `docker inspect` 環境変数不足・ポート違い |

### ⚙️ Stage 6：シェルスクリプトと自動化（8問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 6-1 | 初めてのシェルスクリプト | shebang `chmod +x` `$1` `$#` `"$@"` `${VAR:-default}` |
| 6-2 | 条件分岐と終了コード | `if` `[[ ]]` `-f` `-s` `exit 1` `>&2` |
| 6-3 | ループで一括処理 | `for f in *.JPG` `while IFS= read -r` `${f%.JPG}` |
| 6-4 | 関数と set -euo pipefail | 関数 `local` `set -euo pipefail` `${1:?}` |
| 6-5 | awk と jq でデータを集計・抽出する | `awk -F, '{s[$1]+=...}'` `sort -k2nr` `jq -r 'select(...)'` |
| 6-6 | vim で設定ファイルを直す | `vim` `:%s/old/new/g` `dd` `o` `:wq` |
| 6-7 | cron で定期実行を仕込む | `crontab -l / -e` `*/5 * * * 1-5` `>> log 2>&1`（模擬 crontab で安全に練習） |
| 6-8 | 【実践】ローテーション付きバックアップスクリプト | `tar czf` `date +%Y%m%d_%H%M%S` 世代管理・エラー処理 |

### 🏭 Stage 7：サーバー運用と Docker 応用（7問）
| # | ミッション | 主なコマンド |
|---|---|---|
| 7-1 | systemctl でサービスを切り替えよ | `systemctl status / start / stop / enable / disable` `--now` |
| 7-2 | journalctl で障害の真犯人を突き止めろ | `journalctl -u` `-b` `-p` `--since` |
| 7-3 | ユニットファイルを書いて常駐サービス化せよ | `[Unit]` `[Service]` `[Install]` `daemon-reload` |
| 7-4 | 新メンバーのアカウントを作成せよ | `groupadd` `useradd -m -s -G` `passwd` `usermod -aG` |
| 7-5 | 専用ネットワークでコンテナをつなげ | `docker network create / connect / inspect` コンテナ名による名前解決 |
| 7-6 | マルチステージビルドで実行イメージを軽量化せよ | `FROM ... AS` `COPY --from` `CGO_ENABLED=0` `scratch` |
| 7-7 | ヘルスチェックと再起動ポリシーで運用を固めよ | `--health-cmd` `--health-interval` `--restart unless-stopped` `docker inspect` |

7-1〜7-4 は **管理コマンドのシミュレーター** で練習します。`systemctl` / `journalctl` / `useradd` などは訓練用の模擬コマンドに切り替わり、サービス状態やユーザー情報は作業ディレクトリの `sysroot/` に保存されます。
模擬 `sudo` で `sudo cat /etc/passwd` などと指定すると `sysroot/etc/passwd` へ読み替えます。実際の root 権限は不要です。通常の bash コマンドはそのまま実行されるため、編集先は各課題の作業ディレクトリと問題文を確認してください。

### ✨ Extra：現場で一目置かれる小ネタ・時短術
**閲覧モード（メニュー →「小ネタ図鑑」）: 解説10選**
1. 履歴の爆速再利用（`!!` `!$` `!*` `Ctrl+R`） 2. ブレース展開 3. `xargs` と `find -print0 | xargs -0` 4. `tee`
5. 終了ステータス `$?` と `&&` / `||` 6. `watch -n 1` 7. `diff -u` と `patch` 8. プロセス置換 `<(cmd)`
9. `nohup` と `tmux` / `screen` 10. Readline キーバインド（`Ctrl+A/E/W/U`…）

**実践モード: ミニ課題5問**
| # | ミッション | 主なコマンド |
|---|---|---|
| EX-1 | ブレース展開で一撃作成 | `cp f{,.bak}` `mkdir -p app/{src,test,docs}` `{01..05}` |
| EX-2 | スペース入りファイル名の罠 | `find -print0 \| xargs -0` |
| EX-3 | tee で見ながら残す | `cmd \| tee file \| grep -c` |
| EX-4 | 終了ステータスと && / \|\| の連鎖 | `$?` `a && b && c \|\| d` |
| EX-5 | diff と patch、そしてプロセス置換 | `diff -u` `patch` `diff <(sort a) <(sort b)` |

---

## 🐳 Docker モードについて

起動時に `docker info` を自動チェックします。

| 状況 | 動作 |
|---|---|
| Docker デーモンが使える | 本物の Docker でコンテナを起動・検証（`lq-` で始まる名前・`lq=1` ラベルのコンテナだけを操作します） |
| 未インストール / 権限なし | **シミュレーションモード**：学習用の模擬 `docker` コマンドが自動で使われます。`run / ps / logs / exec -it / inspect / build / images / rm / prune / compose / network` などを本物と同じ書式・出力・エラーメッセージで再現。Dockerfile の構文エラーやレイヤーキャッシュ（CACHED 表示）、compose.yaml の検証、ポート衝突や名前衝突、ユーザー定義ネットワークと名前解決、マルチステージビルド、ヘルスチェックと再起動ポリシーもシミュレートします |

メニューの「設定」で `auto` / `mock`（常にシミュレーション）/ `real` を切り替えられます。
自分の Docker 環境を汚したくない場合は `mock` がおすすめです。

---

## 📴 オフラインでの利用

**インターネットに接続していなくても、全59ミッションを最後まで遊べます。**
必要な Linux コマンドを事前に導入しておけば、追加のダウンロードや `pip install` は不要です。ゲーム本体は Python 3 標準ライブラリと bash で動作し、Docker は必須ではありません。

### なぜオフラインで動くのか

| 要素 | オフライン時の動作 |
|---|---|
| ゲーム本体・判定エンジン | Python 3 標準ライブラリのみ。外部ライブラリ・外部 API への通信は一切ありません |
| Stage 1〜3 | ローカルのファイル・プロセス・環境変数だけを扱うので影響なし |
| Stage 4 の HTTP / ポート / `curl` 問題 | 練習用サーバーを **`127.0.0.1`（自分自身）** に立てて使うため、ネットが無くても動きます |
| Stage 4 の `ping` | 宛先は `127.0.0.1`（ループバック）なのでオフラインでも応答します |
| Stage 4 の `dig`（4-6） | 下記「4-6 の注意」を参照。オフラインでもクリアできるよう判定を調整済み |
| Stage 4 の `ssh` / `rsync` / `tar` / `zip` | すべてローカル内で完結（`ssh -G` で設定を解析するだけで、実際の接続はしません） |
| Stage 5・7（Docker） | **シミュレーションモードなら完全オフライン**で動作します（模擬 `docker` コマンドはイメージのダウンロードを行いません） |
| Stage 6・Stage 7 の管理課題 | ローカルのファイルと模擬 `crontab`・管理コマンドだけで動作します（`jq`・`vim` などは事前に導入） |
| 進捗の保存 | ローカルの `save_data.json` に書き込むだけ |

### 4-6（ping / dig）の注意

`dig nonexistent-penguin.invalid` は DNS サーバーへの問い合わせです。オフライン時の結果は環境によって変わります。

- **systemd-resolved が動いている一般的な Ubuntu**：`.invalid` はローカルで処理されるため、オフラインでも通常どおり `status: NXDOMAIN` が表示されます。
- **DNS サーバーに届かない環境**：`;; connection timed out; no servers could be reached` と表示され、status 行が出ません。
  この場合でも、「`.invalid` は存在しないドメイン → 正常なら `NXDOMAIN`」という知識で `submit NXDOMAIN` すればクリアできます（`check` 時にも案内が表示されます）。
- DNS サーバーが `SERVFAIL` を返す環境では、その PC で `dig` が実際に返したステータスも正解として扱います。

### Docker を本物で使う場合（`real` モード）のみ注意

本物の Docker で Stage 5・7 を遊ぶ場合、`nginx` / `alpine` / `python:3.12-slim` / `golang:1.23` など、課題が指定するイメージが必要です。Stage 7 の Go アプリはビルド用コンテナ内でコンパイルするため、ホストへの Go のインストールは不要です。
手元にイメージが無い状態でオフラインになると `docker run` がイメージを取得できず失敗します。

- オフラインで遊ぶ予定なら、**メニュー →「設定」で Docker モードを `mock` にする**のが確実です（`auto` でも Docker が無ければ自動で `mock` になります）。
- オンラインのうちに 課題で使うイメージをすべて取得しておく必要があります。例: `for image in nginx alpine python:3.12-slim golang:1.23; do docker pull "$image"; done`。課題内で生成するイメージも、必要なら事前にビルドしてください。

### 事前に入れておくと安心なコマンド

オフラインになると `apt install` ができないので、事前に `./start.sh --check` で不足コマンドを確認してください。
不足がある場合はオンラインのうちに以下を実行しておきます。

```bash
sudo apt install curl iputils-ping dnsutils rsync zip unzip lsof openssh-client procps iproute2 jq vim
```

`--check` の結果がすべて ✔ なら、あとはネットワークを切っても問題ありません。

---

## 🧪 自動テスト

```bash
./start.sh --test          # 全59問
./start.sh --test 2-7 5-5  # 指定した問題だけ
./start.sh --test -v       # 誤答時のフィードバックも表示
python3 tests/test_docker_backend.py # 実Docker応答の正規化（デーモン不要）
python3 tests/test_simulators.py  # 管理系・Docker シミュレーターの回帰テスト
python3 tests/test_progress.py    # 59問の登録・ランク境界・旧セーブ互換性
```

各ミッションについて次を検証します（専用の一時ディレクトリを使うため、既存のセーブデータとプレイ用 `workspace/` は保持されます）:
1. **初期状態** では check が「未達成」になる
2. **惜しい誤答**（`-n` 忘れ、`2>&1` の順番違い、`-p` の向き逆など、各問 1〜4 パターン）を実行しても「未達成」になる
3. **模範解答** を本物の bash でサンドボックス内で実行すると「達成」になる
4. 問題文・3段階ヒント・解答・解説・ワンポイントが揃っていて、プレースホルダが全て埋まる

---

## 📂 ディレクトリ構成

```text
.
├── start.sh                 # 起動ランチャー
├── README.md
├── engine/
│   ├── main.py              # メインメニュー・ダッシュボード・進行管理
│   ├── runner.py            # サンドボックス構築・サブシェル起動・状態判定エンジン
│   ├── ui.py                # カラー表示・アスキーアート・プログレスバー・テーブル描画
│   ├── cli.py               # サブシェル内コマンド（mission/hint/answer/check/submit/reset）
│   ├── shellrc.bash         # サブシェル用 rc（プロンプト・ゲーム内コマンド・状態記録）
│   ├── save.py              # セーブデータ・ランク・称号・スコア
│   ├── servers.py           # Stage 4 用のローカル HTTP サーバー（127.0.0.1 のみ）
│   ├── docker_backend.py    # Docker 判定（本物 / シミュレーションの切替）
│   ├── dockermock.py        # 模擬 docker CLI 本体
│   ├── sim_cron.py          # 模擬 crontab
│   └── sim_ops.py           # 模擬 systemd・journal・ユーザー管理
├── bin/mock/                # シミュレーションモード用の docker / docker-compose コマンド
├── bin/sim/                 # 模擬 crontab・systemctl・journalctl・ユーザー管理・sudo
├── curriculum/
│   ├── stage1_basics.py     # Stage 1（8問）
│   ├── stage2_text_pipe.py  # Stage 2（8問）
│   ├── stage3_sys_perm.py   # Stage 3（8問）
│   ├── stage4_net_arch.py   # Stage 4（8問）
│   ├── stage5_docker.py     # Stage 5（7問）
│   ├── stage6_script_auto.py # Stage 6（8問）
│   ├── stage7_ops_docker.py  # Stage 7（7問）
│   └── extra_tips.py        # Extra（解説10選 ＋ ミニ課題5問）
├── workspace/               # プレイ用サンドボックス（stage_01〜07, stage_EX。自動生成・リセット可能）
├── save_data.json           # 進捗の自動保存
└── tests/
    └── test_all_missions.py # 全ミッション自動検証スイート
```

### 判定の仕組み（runner.py）
サブシェルの `PROMPT_COMMAND` が、コマンドを実行するたびに **カレントディレクトリ・環境変数・ジョブ一覧・終了コード・履歴** を `workspace/.lq_state/` に記録します。
`check` を打つと、各ミッションの検証関数がファイルシステムやプロセス（`/proc`）とあわせてそれらを検査し、
「何が足りないか」を具体的な日本語でフィードバックします（例:「標準エラー出力が入っていません。`2>&1` を使いましょう」）。

---

## ⚠ 注意事項

- サブシェルは **本物の bash** です。作業は `workspace/` の中で行ってください（外に出るとプロンプトに赤字で警告が出ます）。
  `rm -rf` などは実際に効くので、サンドボックスの外では慎重に！
- ミッション用のバックグラウンドプロセス（暴走プロセス役・HTTPサーバー役）は、ミッション終了時に自動で停止されます。
- Stage 4 のサーバーはすべて `127.0.0.1` のみで待ち受け、外部には公開されません。`ping` / `dig` も自分自身（ループバック）とローカルの DNS リゾルバにしか問い合わせません。
- 4-7 の SSH 設定は作業ディレクトリ内の `.ssh/` で練習するため、本物の `~/.ssh` は変更しません。
- 予期せぬエラーが起きた場合は `workspace/error.log` に詳細が記録され、メニューに戻ります。

## 🛠 トラブルシューティング

| 症状 | 対処 |
|---|---|
| 文字化けする | 端末の文字コードを UTF-8 に。`echo $LANG` が `ja_JP.UTF-8` か `C.UTF-8` であること |
| 罫線がずれる | 端末の「曖昧な幅の文字」を「半角」に設定してください |
| 色が付かない / 消したい | `NO_COLOR=1 ./start.sh` で色なし表示 |
| `dig` や `lsof` が無い | `sudo apt install dnsutils lsof`（`./start.sh --check` で確認） |
| 進捗をリセットしたい | メニュー →「設定」→ `[r]`、または `save_data.json` を削除 |
