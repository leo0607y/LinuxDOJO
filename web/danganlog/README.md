# DANGAN LOG / Linux道場 (ブラウザー版)

Next.js の完全な静的書き出し (`output: 'export'`) です。サーバー実行、API、ミドルウェア、画像最適化は使いません。
学習ロジックはすべてブラウザー内の Web Worker (`public/worker.js`) が Pyodide 0.27.7 上で実行します。
Pyodide も同じサイトから配信するため、実行時に第三者のサービスへは接続しません。
従量課金の対象になるサービスは使いません。

## 構成

- `app/`, `components/Dojo.jsx`: 画面 (学習画面のみクライアントコンポーネント)
- `lib/core.js`: 画面に依存しないロジック (worker との通信、保存、履歴、コース一覧)
- `public/worker.js`: Pyodide を読み込み、教材を実行する worker (メッセージ仕様: `init / select / execute / hint / answer / reset / export / import`)
- `scripts/prepare-assets.mjs`: ビルド前に `public/pyodide/` (npm の pyodide から5ファイル) と `public/python-source.json` (`tools/build_web.py` が生成) を用意
- `public/_headers`: Cloudflare Pages 用のキャッシュ設定

生成物 (`public/pyodide/`, `public/python-source.json`, `node_modules/`, `.next/`, `out/`) は Git に入れません。

## ビルドとローカル確認

Node.js 20.9 以上 (推奨 22。wrangler でデプロイするなら 22.12 以上) と Python 3.9 以上が必要です。リポジトリ全体 (`engine/`, `curriculum/`, `tools/`) が手元にある状態で実行してください。

```
cd web/danganlog
npm ci
npm run build                      # out/ に静的ファイルを書き出す
python3 -m http.server 8080 -d out # http://localhost:8080/ で確認
```

`npm run dev` でも確認できます。`file://` で開くと worker が読み込めないため、必ずHTTP経由で開きます。

## テスト

```
python3 -m unittest tests.test_web_bundle     # リポジトリ直下から。教材バンドルと静的サイト設定
cd web/danganlog && npm test                  # node: core.test.mjs と、実際の Pyodide で worker を通す worker-e2e.mjs
```

`node` や `node_modules` が無い環境では node のテストは skip されます。

## Cloudflare Pages へのデプロイ (無料の静的アセットのみ)

Cloudflare にログインできる人が、ダッシュボードで設定します。この README の手順では自動公開は行いません。

1. Workers & Pages で「Create application」から Pages を選び、Git リポジトリを接続します。
2. ビルド設定:
   - Framework preset: Next.js (Static HTML Export) または None
   - Root directory: `web/danganlog`
   - Build command: `npm ci && npm run build`
   - Build output directory: `out`
   - 環境変数: `NODE_VERSION` = `22` (`.node-version` でも指定済み)
3. ビルドには `engine/` などのリポジトリ全体と Python 3 が必要です (Pages のビルド環境に含まれます。使えない場合は `PYTHON_VERSION` を設定)。
4. デプロイ後は `https://<プロジェクト名>.pages.dev/` (無料) で公開されます。独自ドメインを使う場合のみ、自分が所有するドメインを Pages プロジェクトの「Custom domains」に追加します (任意)。
5. Functions、KV、D1、R2、Workers、Analytics は有効にしないでください。静的ファイルの配信だけで動きます。

最大のファイルは `pyodide.asm.wasm` (約10MB) で、Pages の1ファイル25MiB制限に収まります。

## スクリプトでデプロイする (wrangler)

```
cd web/danganlog
cp .env.deploy.example .env.deploy    # CLOUDFLARE_PAGES_PROJECT などを記入 (.env.deploy は Git に入りません)
npx wrangler@4.166.0 login            # ブラウザ認証。API トークン方式なら .env.deploy に CLOUDFLARE_API_TOKEN を記入
scripts/deploy.sh --dry-run           # 実行内容の確認だけ
scripts/deploy.sh                     # テスト → ビルド → out/ を Pages へアップロード
```

`--skip-build` `--skip-test` も使えます。初回のみ Pages プロジェクトを作る必要があります (`npx wrangler@4.166.0 pages project create <名前> --production-branch main`)。
トークンは「Cloudflare Pages: Edit」だけの権限で作成し、リポジトリ・チャット・Issue には貼らないでください。

## 容量

`out/` 全体で約16MB (Pyodide 約14MB、教材 Python 約1.4MB)。初回アクセスで Pyodide を読み込み、以降はブラウザーにキャッシュされます。

## 正直な制限

- ブラウザー版は模擬ターミナルです。本物の bash を使う実践ミッションと VM 実習は含まれません (教材をダウンロードして使います)。
- 進捗は `localStorage` にだけ保存されます。ブラウザーのデータを消すと失われるため、「学習データの管理」から JSON を書き出して保管してください。
- 初回は Pyodide と教材の読み込みに数秒から十数秒かかります。読み込めないときは画面に理由と「再読み込み」が出ます。
- 実機のブラウザー表示 (レイアウト、スマートフォン、ダークテーマ) は、この環境では未確認です。
