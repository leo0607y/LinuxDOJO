#!/usr/bin/env bash
# LinuxDOJO を「start」だけで起動するユーザー用コマンドを登録する。
# sudo やシェル設定ファイルの書き換えは行わない。
set -eu

usage() {
  printf '%s\n' '使い方: bash install-start.sh [--uninstall]' \
    '初回だけ登録すると、以後は start だけで起動できます。' \
    '登録先: $HOME/.local/bin/start（他の start は上書きしません）。'
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  ''|--uninstall) ;;
  *) usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then usage >&2; exit 2; fi
if [ -z "${HOME:-}" ] || [[ "$HOME" != /* ]]; then
  printf '%s\n' 'HOME が絶対パスで設定されていません。登録を中止します。' >&2
  exit 1
fi
project_dir="$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")"
launcher="$project_dir/start.sh"
if [ ! -f "$launcher" ]; then
  printf '%s\n' '同じフォルダに start.sh が見つかりません。教材を展開したフォルダで実行してください。' >&2
  exit 1
fi
command_dir="$HOME/.local/bin"
command_file="$command_dir/start"

launcher_text() {
  printf '%s\n' '#!/usr/bin/env bash' '# LinuxDOJO start launcher (managed by install-start.sh)'
  printf 'exec bash %q "$@"\n' "$launcher"
}

is_our_launcher() {
  [ -f "$command_file" ] && [ ! -L "$command_file" ] && cmp -s "$command_file" <(launcher_text)
}

if [ "${1:-}" = '--uninstall' ]; then
  if is_our_launcher; then
    rm -- "$command_file"
    printf '%s\n' 'LinuxDOJO の start 登録だけを解除しました。教材と進捗は残っています。'
    exit 0
  fi
  if [ ! -e "$command_file" ] && [ ! -L "$command_file" ]; then
    printf '%s\n' 'この教材の start は登録されていません。'
    exit 0
  fi
  printf '%s\n' '別の start があるため削除しませんでした。内容を確認してください。' >&2
  exit 1
fi

if [ -e "$command_file" ] || [ -L "$command_file" ]; then
  if ! is_our_launcher; then
    printf '%s\n' '登録先に別の start があるため上書きしません。bash start.sh で起動できます。' >&2
    exit 1
  fi
fi
existing_start="$(command -v start || true)"
if [ -n "$existing_start" ] && { [ "$existing_start" != "$command_file" ] || ! is_our_launcher; }; then
  printf '%s\n' 'すでに別の start コマンドや関数があります。上書きせず登録を中止しました。bash start.sh で起動できます。' >&2
  exit 1
fi
if ! is_our_launcher; then
  mkdir -p -- "$command_dir"
  temporary_launcher="$(mktemp "$command_dir/.linuxdojo-start.XXXXXX")"
  trap 'rm -f -- "$temporary_launcher"' EXIT
  launcher_text > "$temporary_launcher"
  chmod 700 "$temporary_launcher"
  # ln は登録先を上書きしない。確認後に別ファイルが作られても保護する。
  if ! ln -- "$temporary_launcher" "$command_file"; then
    printf '%s\n' 'start の登録に失敗しました。既存ファイルは上書きしていません。' >&2
    exit 1
  fi
fi
# 再登録時に自分のラッパーの実行権限だけを復元する。
chmod 700 "$command_file"
printf '%s\n' '登録できました。次回からは start で起動できます。教材のフォルダは移動・削除せず残してください。'
case ":${PATH:-}:" in
  *":$command_dir:"*) ;;
  *) printf '%s\n' '今のターミナルでは、まず次の1行を実行してください。シェル設定は変更していません。' \
       'export PATH="$HOME/.local/bin:$PATH"' \
       '次回のターミナルでも start が見つからない場合は、この行をもう一度実行します。' ;;
esac
printf '%s\n' 'type start で、この教材の起動コマンドが選ばれるか確認できます。' \
  '以前から自分で設定した start の別名(alias)や関数がある場合は、そちらが優先されることがあります。' \
  '登録解除: bash install-start.sh --uninstall'
