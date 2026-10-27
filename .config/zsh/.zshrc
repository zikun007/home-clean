# =========================================================
# ~/.config/zsh/.zshrc
# Ubuntu Linux / macOS (Apple Silicon)
# =========================================================

[[ "$(uname -s)" == Darwin ]] && export IS_MACOS=1 || export IS_LINUX=1

# ---------------------------------------------------------
# 基础目录 / 缓存 / 历史
# ---------------------------------------------------------

export ZSH="$XDG_CONFIG_HOME/zsh/oh-my-zsh"
export ZSH_CACHE_DIR="$XDG_CACHE_HOME/zsh/oh-my-zsh"

export HISTFILE="$XDG_DATA_HOME/zsh/.zsh_history"
HISTSIZE=10000
SAVEHIST=10000

export LESSHISTFILE="$XDG_CACHE_HOME/less/.less_history"
export TMUX_TMPDIR="$XDG_CACHE_HOME/tmux"
export NUGET_PACKAGES="$XDG_CACHE_HOME/nuget"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"

mkdir -p \
  "$ZSH_CACHE_DIR" \
  "$TMUX_TMPDIR" \
  "$(dirname "$HISTFILE")" \
  "$(dirname "$LESSHISTFILE")" \
  "$UV_CACHE_DIR" 2>/dev/null

# 禁用自动标题（提升性能）
export DISABLE_AUTO_TITLE=true

# 导入环境变量
[[ -f ~/.ssh/.env ]] && source ~/.ssh/.env

# ---------------------------------------------------------
# 历史记录优化
# ---------------------------------------------------------

HIST_STAMPS="yyyy-mm-dd"

setopt APPEND_HISTORY
setopt INC_APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_SAVE_NO_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt HIST_IGNORE_SPACE

# ---------------------------------------------------------
# 补全优化
# ---------------------------------------------------------

zstyle ':completion:*' use-cache on
zstyle ':completion:*' cache-path "$XDG_CACHE_HOME/zsh/zcompcache"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}' 'r:|[._-]=* r:|=*' 'l:|=* r:|=*'

# 自动纠错
#setopt CORRECT
#setopt CORRECT_ALL

# ---------------------------------------------------------
# PATH
# ---------------------------------------------------------

typeset -U path

# 顺序：用户 bin > Homebrew > 系统。brew 须在 /usr/bin 之前，否则 git/curl 用系统旧版
path=(
  "$HOME/.local/bin"
  "$HOME/bin"
  "$HOME/.cargo/bin"
  ${IS_MACOS:+/opt/homebrew/bin}
  $path
)

# uv / pip、Conda 路径兜底
[[ -d "$HOME/.local/share/uv/tools" ]] && path=("$HOME/.local/share/uv/tools" $path)
[[ -d "$HOME/miniconda3/bin" ]] && path=("$HOME/miniconda3/bin" $path)
[[ -d /opt/miniconda3/bin ]] && path=(/opt/miniconda3/bin $path)

# CUDA（仅 Linux；macOS 无 CUDA）
if [[ -n "$IS_LINUX" ]]; then
  export CUDA_HOME=/usr/local/cuda
  [[ -d "$CUDA_HOME/bin" ]] && path=("$CUDA_HOME/bin" $path)
  [[ -d "$CUDA_HOME/lib64" ]] && export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

export PATH=${(j.:.)path}

# ---------------------------------------------------------
# nvm —— 惰性加载：首次调用 nvm/node/npm 等命令时才真正加载 nvm.sh
# 默认版本 bin 目录直接注入 PATH，node/npm 立即可用；--no-use 跳过 nvm_auto 自动切换
# ---------------------------------------------------------

export NVM_DIR="$HOME/.config/nvm"
export NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node

# 把已安装的最新版本注入 PATH，node/npm 立即可用（新机器未装 nvm 时自动跳过）
if [[ -d "$NVM_DIR/versions/node" ]]; then
  _nvm_latest=$(print -l "$NVM_DIR"/versions/node/*(N/:t) | sort -V | tail -1)
  [[ -n "$_nvm_latest" && -d "$NVM_DIR/versions/node/$_nvm_latest/bin" ]] \
    && path=("$NVM_DIR/versions/node/$_nvm_latest/bin" $path)
  unset _nvm_latest
fi

_nvm_lazy() {
  unset -f nvm node npm npx pnpm yarn corepack
  [[ -s "$NVM_DIR/nvm.sh" ]] && \source "$NVM_DIR/nvm.sh" --no-use
  [[ -s "$NVM_DIR/bash_completion" ]] && \source "$NVM_DIR/bash_completion"
}
for _cmd in nvm node npm npx pnpm yarn corepack; do
  eval "${_cmd}() { _nvm_lazy; ${_cmd} \$@; }"
done
unset _cmd

# ---------------------------------------------------------
# Powerlevel10k instant prompt
# 尽量靠前，避免后面插件影响首屏速度
# ---------------------------------------------------------

if [[ -r "$XDG_CACHE_HOME/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "$XDG_CACHE_HOME/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# ---------------------------------------------------------
# Oh My Zsh
# ---------------------------------------------------------

ZSH_THEME="powerlevel10k/powerlevel10k"
DISABLE_AUTO_UPDATE=true
ZSH_COMPDUMP="$ZSH_CACHE_DIR/.zcompdump-$HOST"

plugins=(
  git
  fzf
  fzf-tab
  zsh-autosuggestions
  zsh-vi-mode
  fast-syntax-highlighting
)

# 自定义补全函数（_codex/_claude/_omp 等），必须在 compinit 之前加入 fpath
fpath=("$ZDOTDIR/completions" $fpath)

source "$ZSH/oh-my-zsh.sh"

[[ -f "$ZDOTDIR/.p10k.zsh" ]] && source "$ZDOTDIR/.p10k.zsh"

# ---------------------------------------------------------
# Zsh vi mode
# ---------------------------------------------------------

ZVM_VI_INSERT_ESCAPE_BINDKEY=jk
ZVM_KEYTIMEOUT=0.3

function zvm_config() {
  ZVM_INSERT_MODE_CURSOR=$'\e[5 q'
  ZVM_NORMAL_MODE_CURSOR=$'\e[1 q'
}

function zvm_after_init() {
  zvm_bindkey vicmd 'dL' kill-line
  zvm_bindkey vicmd 'H' beginning-of-line
  zvm_bindkey vicmd 'L' end-of-line
  zvm_bindkey visual 'H' beginning-of-line
  zvm_bindkey visual 'L' end-of-line
}

# ---------------------------------------------------------
# ROS2 Humble
# 只在存在时加载，避免报错
# ---------------------------------------------------------

if [[ -f /opt/ros/humble/setup.zsh ]]; then
  source /opt/ros/humble/setup.zsh
fi

# 如果你有自己的工作空间，也可以按需加：
# if [[ -f "$HOME/ros2_ws/install/setup.zsh" ]]; then
#   source "$HOME/ros2_ws/install/setup.zsh"
# fi

# ---------------------------------------------------------
# Conda 惰性加载：首次调用 conda 时才执行 hook
# auto_activate_base=False，base 本就不会自动激活，行为不变
# ---------------------------------------------------------
_conda_lazy() {
  unset -f conda
  local __conda_setup
  __conda_setup="$("$HOME/miniconda3/bin/conda" shell.zsh hook 2> /dev/null)"
  if [[ -n "$__conda_setup" ]]; then
    eval "$__conda_setup"
  else
    [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]] && . "$HOME/miniconda3/etc/profile.d/conda.sh"
  fi
  conda "$@"
}
if [[ -x "$HOME/miniconda3/bin/conda" ]]; then
  conda() { _conda_lazy "$@"; }
fi


# ---------------------------------------------------------
# zoxide：init 自带 z / zi / 目录追踪 hook，无需手写封装
# ---------------------------------------------------------
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"


# ---------------------------------------------------------
# fzf
# ---------------------------------------------------------
[[ -f "$HOME/.fzf.zsh" ]] && source "$HOME/.fzf.zsh"
[[ -f "$ZDOTDIR/.fzf.zsh" ]] && source "$ZDOTDIR/.fzf.zsh"


# ---------------------------------------------------------
# 终端代理开关（PAC 中的内网代理节点）
# ---------------------------------------------------------
proxy_on() {
  export http_proxy="http://10.8.0.242:8838"
  export https_proxy="http://10.8.0.242:8838"
  export HTTP_PROXY="$http_proxy"
  export HTTPS_PROXY="$https_proxy"
  export no_proxy="localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,horizon.ai,horizon.cc,hobot.cc,horizon.auto,hogpu.cc,gua.com,guasemi.com,aliyuncs.com,feishu.cn,larksuite.com,feishucdn.com"
  export NO_PROXY="$no_proxy"
  print -P "%F{green}proxy on%f -> 10.8.0.242:8838"
}

proxy_off() {
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
  print -P "%F{yellow}proxy off%f"
}

# ---------------------------------------------------------
# Alias
# ---------------------------------------------------------
alias ..='cd ..'
alias ...='cd ../..'
# 没有 eza 时退回系统 ls（Ubuntu 22.04 官方源没有 eza）
if (( $+commands[eza] )); then
  alias ls='eza'
  # eza 的 -F 是 --classify[=WHEN]，可选参数会吞掉紧跟字符，-alFh 会被当成 -F h 报错
  alias ll='ls -al --header'
  alias lt='ls -l --sort=oldest --header'
else
  alias ll='ls -alFh'
  alias lt='ls -ltrh'
fi
alias cls='clear'

# Debian/Ubuntu 打包名是 fdfind / batcat，macOS(brew) 是 fd / bat
(( $+commands[fdfind] )) && alias fd='fdfind'
(( $+commands[batcat] )) && alias bat='batcat'
(( $+commands[python] )) && alias py='python' || alias py='python3'

# zoxide 直连原生命令的别名（z/zi 已由 init 提供）
alias za='zoxide add'
alias zq='zoxide query'
alias zqi='zoxide query -i'
alias zr='zoxide remove'
alias zri='zoxide remove -i'

# tmux
alias tm='tmux'
alias tl='tmux list-sessions'
alias tkss='tmux kill-session -t'
alias ta='tmux attach -t'
alias ts='tmux new-session -s'

# config
alias zshconfig='vim "$ZDOTDIR/.zshrc"'
alias zshenvconfig='vim "$HOME/.zshenv"'
alias zshreload='source "$ZDOTDIR/.zshrc"'
alias tmuxconfig='vim "$XDG_CONFIG_HOME/tmux/tmux.conf"'
alias tmuxreload='tmux source-file "$XDG_CONFIG_HOME/tmux/tmux.conf"'

# process / disk（BSD du 只认 -d，GNU 用 --max-depth）
alias psg='ps aux | grep -i'
alias df='df -h'
[[ -n "$IS_MACOS" ]] && alias du='du -h -d 1' || alias du='du -h --max-depth=1'

# ROS / colcon（仅 Linux）
if [[ -n "$IS_LINUX" ]]; then
  alias cw='cd ~/ros2_ws'
  alias cs='cd ~/ros2_ws/src'
  alias cb='colcon build --symlink-install'
  alias cbs='colcon build --symlink-install --packages-select'
  alias sb='source ~/ros2_ws/install/setup.zsh'
fi

# Python / uv
alias venv='uv venv'
alias urun='uv run'
alias uadd='uv add'
alias usync='uv sync'

# ---------------------------------------------------------
# 最终整理 PATH（防止上面 path 更新未导出）, 以及其他命令汇总
# ---------------------------------------------------------

export PATH=${(j.:.)path}

# uv 安装配置
#. "$HOME/.local/share/../bin/env"

# tmux —— 仅在 tmux 会话内重载配置（否则每次启动都报 no server running）
if [[ -n "$TMUX" && -f "$XDG_CONFIG_HOME/tmux/tmux.conf" ]]; then
  tmux source-file "$XDG_CONFIG_HOME/tmux/tmux.conf"
fi
