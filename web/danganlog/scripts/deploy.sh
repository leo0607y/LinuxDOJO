#!/usr/bin/env bash
# Cloudflare Pages へ静的サイトをデプロイする。
# 使い方:  web/danganlog/scripts/deploy.sh [--dry-run] [--skip-build] [--skip-test]
# 事前準備: .env.deploy.example を .env.deploy にコピーして値を入れる (.env.deploy は Git に入らない)。
set -euo pipefail

cd "$(dirname "$0")/.."
WRANGLER_VERSION="4.166.0"

DRY_RUN=0; SKIP_BUILD=0; SKIP_TEST=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    --skip-test) SKIP_TEST=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "不明な引数: $arg" >&2; exit 2 ;;
  esac
done

if [ -f .env.deploy ]; then
  set -a; . ./.env.deploy; set +a
fi

: "${CLOUDFLARE_PAGES_PROJECT:?CLOUDFLARE_PAGES_PROJECT が未設定です (.env.deploy を確認)}"
BRANCH="${CLOUDFLARE_PAGES_BRANCH:-main}"
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] && [ "$DRY_RUN" -eq 0 ]; then
  echo "CLOUDFLARE_API_TOKEN が未設定です。.env.deploy に書くか、 'npx wrangler login' 済みか確認してください。" >&2
  echo "(ログイン済みなら続行します)" >&2
fi

command -v node >/dev/null || { echo "node (20.9以上) が必要です" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 が必要です" >&2; exit 1; }

if [ "$SKIP_BUILD" -eq 0 ]; then
  [ -d node_modules ] || npm ci
  if [ "$SKIP_TEST" -eq 0 ]; then npm test; fi
  npm run build
fi

[ -f out/index.html ] || { echo "out/index.html がありません。ビルドしてください" >&2; exit 1; }

# 公開物に秘密情報らしきファイルが混ざっていないか確認する
if find out -type f \( -name '.env*' -o -name '*.pem' -o -name '*.key' -o -name '.dev.vars' -o -name 'id_rsa*' \) | grep -q .; then
  echo "out/ に秘密情報の可能性があるファイルがあります。中止します。" >&2; exit 1
fi

CMD=(npx --yes "wrangler@${WRANGLER_VERSION}" pages deploy out --project-name "$CLOUDFLARE_PAGES_PROJECT" --branch "$BRANCH")
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 実行予定: ${CMD[*]}"; exit 0
fi
"${CMD[@]}"
