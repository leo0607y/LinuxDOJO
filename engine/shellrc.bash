# ============================================================
#  LinuxQuest ゲーム用サブシェル rc ファイル
#  本物の bash です。タブ補完・パイプ・リダイレクト・ジョブ制御・
#  Ctrl+R 履歴検索など、普段の bash の機能がそのまま使えます。
# ============================================================

# Ubuntu の標準設定（command-not-found など）を読み込む
if [ -f /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi
# タブ補完（bash-completion があれば）
if ! shopt -oq posix && [ -f /usr/share/bash-completion/bash_completion ]; then
  . /usr/share/bash-completion/bash_completion 2>/dev/null
fi

export HISTFILE="$LQ_STATE/history"
HISTSIZE=10000
HISTFILESIZE=10000
HISTCONTROL=ignoredups
shopt -s histappend checkwinsize
history -c; history -r

alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias ll='ls -alF'

# ---------------- ゲーム内コマンド ----------------
__lq() { "${LQ_PYTHON:-/usr/bin/python3}" "$LQ_HOME/engine/cli.py" "$@"; }
__lq_after() {
  case "$1" in
    10) echo next > "$LQ_STATE/intent"; builtin exit 0 ;;
    11) echo menu > "$LQ_STATE/intent"; builtin exit 0 ;;
  esac
  return 0
}
mission()       { __lq mission; }
hint()          { __lq hint "$@"; }
answer()        { __lq answer; }
check()         { __lq check; __lq_after $?; }
submit()        { __lq submit "$*"; __lq_after $?; }
reset_mission() { __lq reset && builtin cd "$LQ_WORK"; }
skip()          { echo next > "$LQ_STATE/intent"; builtin exit 0; }
menu()          { echo menu > "$LQ_STATE/intent"; builtin exit 0; }
lqhelp()        { __lq help; }

# ---------------- 状態の記録（判定エンジン用） ----------------
__lq_prompt() {
  local e=$?
  echo "$e" >> "$LQ_STATE/statuses"
  history -a
  builtin pwd > "$LQ_STATE/cwd"
  /usr/bin/env -0 > "$LQ_STATE/env" 2>/dev/null
  jobs -l > "$LQ_STATE/jobs" 2>/dev/null
  __lq autocheck
  return $e
}
PROMPT_COMMAND=__lq_prompt

__lq_ps1_path() {
  case "$PWD" in
    "$LQ_HOME"/workspace|"$LQ_HOME"/workspace/*) printf '%s' "${PWD#$LQ_HOME/}" ;;
    *) printf '\001\e[1;31m\002(サンドボックス外) %s' "$PWD" ;;
  esac
}
PS1='\[\e[1;97;45m\] LQ ${LQ_MISSION} \[\e[0m\] \[\e[1;94m\]$(__lq_ps1_path)\[\e[0m\] \[\e[1;92m\]\$\[\e[0m\] '

builtin cd "$LQ_WORK" 2>/dev/null
__lq mission
