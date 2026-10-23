# =========================================================
# ~/.config/zsh/.zshrc
# Optimized for WSL
# =========================================================

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

path=(
  "$HOME/.local/bin"
  "$HOME/bin"
  "$HOME/.cargo/bin"
  $path
)

# uv / pip 用户级路径兜底
[[ -d "$HOME/.local/share/uv/tools" ]] && path=("$HOME/.local/share/uv/tools" $path)

# Conda 路径兜底
[[ -d "$HOME/miniconda3/bin" ]] && path=("$HOME/miniconda3/bin" $path)
[[ -d "/opt/miniconda3/bin" ]] && path=("/opt/miniconda3/bin" $path)

export PATH=${(j.:.)path}

# ---------------------------------------------------------
# 开发环境变量
# ---------------------------------------------------------

# ---------------------------------------------------------
# nvm —— 惰性加载：首次调用 nvm/node/npm 等命令时才真正加载 nvm.sh
# 默认版本 bin 目录直接注入 PATH，node/npm 立即可用；--no-use 跳过 nvm_auto 自动切换
# ---------------------------------------------------------

export NVM_DIR="$HOME/.config/nvm"
export NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node

_nvm_default_bin="$NVM_DIR/versions/node/v24.21.0/bin"
[[ -d "$_nvm_default_bin" ]] && path=("$_nvm_default_bin" $path)
unset _nvm_default_bin

_nvm_lazy() {
  unset -f nvm node npm npx pnpm yarn corepack
  [[ -s "$NVM_DIR/nvm.sh" ]] && \source "$NVM_DIR/nvm.sh" --no-use
  [[ -s "$NVM_DIR/bash_completion" ]] && \source "$NVM_DIR/bash_completion"
}
for _cmd in nvm node npm npx pnpm yarn corepack; do
  eval "${_cmd}() { _nvm_lazy; ${_cmd} \$@; }"
done
unset _cmd


# CUDA
export CUDA_HOME=/usr/local/cuda
if [[ -d "$CUDA_HOME/bin" ]]; then
  path=("$CUDA_HOME/bin" $path)
fi
if [[ -d "$CUDA_HOME/lib64" ]]; then
  export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

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
alias l='ls -al'
alias ll='ls -alFh'
alias lt='ls -ltrh'
alias cls='clear'

alias fd='fdfind'
alias bat='batcat'
alias ls='eza'

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

# process / disk
alias psg='ps aux | grep -i'
alias df='df -h'
alias du='du -h --max-depth=1'

# ROS / colcon
alias cw='cd ~/ros2_ws'
alias cs='cd ~/ros2_ws/src'
alias cb='colcon build --symlink-install'
alias cbs='colcon build --symlink-install --packages-select'
alias sb='source ~/ros2_ws/install/setup.zsh'

# Python / uv
alias py='python'
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
