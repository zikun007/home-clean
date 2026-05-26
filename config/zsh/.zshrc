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
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
autoload -Uz compinit
compinit -d "$XDG_CACHE_HOME/zsh/.zcompdump-$HOST"

# 自动纠错
setopt CORRECT
setopt CORRECT_ALL

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

# Vim / Neovim
export VIMINIT='let $MYVIMRC="$XDG_CONFIG_HOME/vim/.vimrc" | source $MYVIMRC'
export VIMDOTDIR="$XDG_CONFIG_HOME/vim"

# Python
export PIP_CONFIG_FILE="$XDG_CONFIG_HOME/pip/pip.conf"
export IPYTHONDIR="$XDG_CONFIG_HOME/ipython"

# Conan
export CONAN_HOME="$XDG_CONFIG_HOME/conan"

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

# ---------------------------------------------------------
# Conda
# ---------------------------------------------------------

if [[ -x "$HOME/miniconda3/bin/conda" ]]; then
  __conda_setup="$("$HOME/miniconda3/bin/conda" shell.zsh hook 2> /dev/null)"
elif [[ -x "/opt/miniconda3/bin/conda" ]]; then
  __conda_setup="$("/opt/miniconda3/bin/conda" shell.zsh hook 2> /dev/null)"
else
  __conda_setup=""
fi

if [[ -n "$__conda_setup" ]]; then
  eval "$__conda_setup"
else
  [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]] && . "$HOME/miniconda3/etc/profile.d/conda.sh"
  [[ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]] && . "/opt/miniconda3/etc/profile.d/conda.sh"
fi
unset __conda_setup

# ---------------------------------------------------------
# 外部工具集成与现代化工具接管 (Zoxide, fzf 等)
# ---------------------------------------------------------

# zoxide 智能接管 cd
if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init zsh --cmd cd)"
fi

# fzf
[[ -f "$HOME/.fzf.zsh" ]] && source "$HOME/.fzf.zsh"
[[ -f "$ZDOTDIR/.fzf.zsh" ]] && source "$ZDOTDIR/.fzf.zsh"

# ---------------------------------------------------------
# Alias & 现代命令替换
# ---------------------------------------------------------

alias ..='cd ..'
alias ...='cd ../..'
alias cls='clear'

# eza 智能接管 ls
if command -v eza >/dev/null 2>&1; then
  alias ls='eza --icons=always --color=always --group-directories-first'
  alias l='eza -al --icons=always --color=always --group-directories-first'
  alias ll='eza -alFh --icons=always --color=always --group-directories-first'
  alias lt='eza -al --sort=modified --icons=always --color=always --group-directories-first'
else
  alias l='ls -al'
  alias ll='ls -alFh'
  alias lt='ls -ltrh'
fi

# fd 智能接管 find
if command -v fd >/dev/null 2>&1; then
  alias find='fd'
fi

# bat 智能接管 cat (兼容 Ubuntu apt 安装的 batcat)
if command -v batcat >/dev/null 2>&1; then
  alias cat='batcat --style=plain --paging=never'
elif command -v bat >/dev/null 2>&1; then
  alias cat='bat --style=plain --paging=never'
fi

# ripgrep 智能接管 grep
if command -v rg >/dev/null 2>&1; then
  alias grep='rg --color=auto'
fi

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

# WSL
alias explorer='explorer.exe .'
alias clip='clip.exe'

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
# 最终整理 PATH
# ---------------------------------------------------------

export PATH=${(j.:.)path}

# uv 安装配置
if [[ -f "$HOME/.local/share/../bin/env" ]]; then
  . "$HOME/.local/share/../bin/env"
fi

# opencode
export PATH=/home/kun24/.opencode/bin:$PATH

# tmux
[ -f "$XDG_CONFIG_HOME/tmux/tmux.conf" ] && tmux source-file "$XDG_CONFIG_HOME/tmux/tmux.conf"