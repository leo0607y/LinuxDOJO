#!/usr/bin/env bash
# ============================================================
#  LinuxQuest 起動ランチャー
#    start               初回登録後、どこからでも起動
#    bash install-start.sh  start コマンドを登録（sudo 不要）
#    ./start.sh          ゲームを起動
#    ./start.sh --test   全ミッションの自動テストを実行
#    ./start.sh --check  動作環境チェックのみ
# ============================================================
set -u
cd "$(dirname "$(readlink -f "$0")")" || exit 1

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    PY="$(command -v "$cand")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Python 3.8 以上が見つかりません。'sudo apt install python3' でインストールしてください。" >&2
  exit 1
fi

# 日本語表示のためにUTF-8ロケールを確保
case "${LANG:-}${LC_ALL:-}" in
  *UTF-8*|*utf8*) ;;
  *) export LANG=C.UTF-8 ;;
esac

# WSL で Windows 側のフォルダ (/mnt/c など) から起動すると Linux の権限が正しく働かない。
# 練習用の作業場所だけ WSL 側に置く（進捗の save_data.json は Windows 版と共通）。
if [ -z "${LQ_WORKSPACE:-}" ] && [[ "$PWD" == /mnt/* ]] && grep -qi microsoft /proc/version 2>/dev/null; then
  export LQ_WORKSPACE="${XDG_DATA_HOME:-$HOME/.local/share}/linuxdojo/workspace"
fi

chmod +x bin/mock/* bin/sim/* 2>/dev/null
mkdir -p "${LQ_WORKSPACE:-workspace}"

check_env() {
  echo "🔎 動作環境チェック"
  for c in bash "$PY" grep sed awk find tar gzip curl ss ping dig rsync zip unzip lsof ssh watch jq vim; do
    if command -v "$c" >/dev/null 2>&1; then printf "  ✔ %s\n" "$c"; else printf "  ✖ %s （一部の問題で必要です: sudo apt install で導入してください）\n" "$c"; fi
  done
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "  🐳 Docker: 本物の Docker デーモンが使えます"
  else
    echo "  🐳 Docker: 使えないため Stage 5・7 はシミュレーションモードで動作します"
  fi
}

case "${1:-}" in
  --test)  shift; exec "$PY" tests/test_all_missions.py "$@" ;;
  --check) check_env; exit 0 ;;
  -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
esac

exec "$PY" engine/main.py
