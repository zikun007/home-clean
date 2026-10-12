# =========================================================
# ~/.config/zsh/.zshrc
# 跨平台配置：自动适配 Ubuntu Linux 与 macOS (Apple Silicon)
# =========================================================

# ---------------------------------------------------------
# 0. 系统检测
# ---------------------------------------------------------

case "$(uname -s)" in
  Darwin) IS_MACOS=1 ;;
  Linux)  IS_LINUX=1 ;;
esac

# ---------------------------------------------------------
# 1. Powerlevel10k instant prompt (必须在最前面)
# ---------------------------------------------------------

if [[ -r "$XDG_CACHE_HOME/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "$XDG_CACHE_HOME/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# ---------------------------------------------------------
# 2. 基础目录 / 缓存 / 历史
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
# 3. 历史记录优化
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
# 4. PATH 与平台专属环境
# ---------------------------------------------------------

typeset -U path

path=(
  "$HOME/.local/bin"
  "$HOME/bin"
  "$HOME/.cargo/bin"
  $path
)

# uv 用户级路径兜底
[[ -d "$HOME/.local/share/uv/tools" ]] && path=("$HOME/.local/share/uv/tools" $path)

# Conda 路径兜底
[[ -d "$HOME/miniconda3/bin" ]] && path=("$HOME/miniconda3/bin" $path)
[[ -d "/opt/miniconda3/bin" ]] && path=("/opt/miniconda3/bin" $path)

if [[ -n "$IS_MACOS" ]]; then
  # ---- macOS: Homebrew (Apple Silicon) ----
  export HOMEBREW_PREFIX="/opt/homebrew"
  export HOMEBREW_PIP_INDEX_URL="https://pypi.mirrors.ustc.edu.cn/simple"
  export HOMEBREW_API_DOMAIN="https://mirrors.ustc.edu.cn/homebrew-bottles/api"
  export HOMEBREW_BOTTLE_DOMAIN="https://mirrors.ustc.edu.cn/homebrew-bottles"

  if [[ -d "$HOMEBREW_PREFIX/bin" ]]; then
    path=("$HOMEBREW_PREFIX/bin" "$HOMEBREW_PREFIX/sbin" $path)

    # 编译相关环境变量 (C++)
    export CPATH="$HOMEBREW_PREFIX/include${CPATH:+:$CPATH}"
    export LIBRARY_PATH="$HOMEBREW_PREFIX/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
  fi

  # VS Code CLI
  [[ -d "/Applications/Visual Studio Code.app/Contents/Resources/app/bin" ]] && \
    path=("/Applications/Visual Studio Code.app/Contents/Resources/app/bin" $path)
else
  # ---- Linux: CUDA ----
  export CUDA_HOME=/usr/local/cuda
  if [[ -d "$CUDA_HOME/bin" ]]; then
    path=("$CUDA_HOME/bin" $path)
  fi
  if [[ -d "$CUDA_HOME/lib64" ]]; then
    export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
fi

export PATH=${(j.:.)path}

# ---------------------------------------------------------
# 5. 开发环境变量
# ---------------------------------------------------------

# Vim / Neovim
export VIMINIT='let $MYVIMRC="$XDG_CONFIG_HOME/vim/.vimrc" | source $MYVIMRC'
export VIMDOTDIR="$XDG_CONFIG_HOME/vim"

# Python
export PIP_CONFIG_FILE="$XDG_CONFIG_HOME/pip/pip.conf"
export IPYTHONDIR="$XDG_CONFIG_HOME/ipython"

# nvm (Node.js 版本管理，仅在安装时加载)
export NVM_DIR="$HOME/.config/nvm"
[[ -s "$NVM_DIR/nvm.sh" ]] && \. "$NVM_DIR/nvm.sh"
export NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node

# Conan
export CONAN_HOME="$XDG_CONFIG_HOME/conan"

# ---------------------------------------------------------
# 6. Oh My Zsh 核心与插件
# ---------------------------------------------------------

ZSH_THEME="powerlevel10k/powerlevel10k"
DISABLE_AUTO_UPDATE=true
ZSH_COMPDUMP="$ZSH_CACHE_DIR/.zcompdump-$HOST"

# 补全样式设置（compinit 交给 Oh My Zsh 处理）
zstyle ':completion:*' use-cache on
zstyle ':completion:*' cache-path "$XDG_CACHE_HOME/zsh/zcompcache"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}' 'r:|[._-]=* r:|=*' 'l:|=* r:|=*'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

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
# 7. 插件深度配置 (Vi Mode / Fzf / Zoxide)
# ---------------------------------------------------------

# Zsh vi mode
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

# zoxide 智能接管 cd
if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init zsh --cmd cd)"
fi

# fzf
[[ -f "$HOME/.fzf.zsh" ]] && source "$HOME/.fzf.zsh"
[[ -f "$ZDOTDIR/.fzf.zsh" ]] && source "$ZDOTDIR/.fzf.zsh"

# ---------------------------------------------------------
# 8. ROS2 Humble（只在存在时加载，避免报错）
# ---------------------------------------------------------

if [[ -f /opt/ros/humble/setup.zsh ]]; then
  source /opt/ros/humble/setup.zsh
fi

# 如果你有自己的工作空间，也可以按需加：
# if [[ -f "$HOME/ros2_ws/install/setup.zsh" ]]; then
#   source "$HOME/ros2_ws/install/setup.zsh"
# fi

# ---------------------------------------------------------
# 9. Conda 初始化
# ---------------------------------------------------------

if [[ -d "$HOME/miniconda3" ]] || [[ -d "/opt/miniconda3" ]]; then
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
fi

# ---------------------------------------------------------
# 10. 终端代理开关（按需修改为自己的代理节点）
# ---------------------------------------------------------

proxy_on() {
  export http_proxy="http://10.8.0.242:8838"
  export https_proxy="http://10.8.0.242:8838"
  export HTTP_PROXY="$http_proxy"
  export HTTPS_PROXY="$https_proxy"
  export no_proxy="localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12"
  export NO_PROXY="$no_proxy"
  print -P "%F{green}proxy on%f -> 10.8.0.242:8838"
}

proxy_off() {
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
  print -P "%F{yellow}proxy off%f"
}

# ---------------------------------------------------------
# 11. Alias & 现代命令替换
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
elif command -v fdfind >/dev/null 2>&1; then
  alias fd='fdfind'
fi

# bat 智能接管 cat (兼容 Ubuntu apt 安装的 batcat)
if command -v batcat >/dev/null 2>&1; then
  alias bat='batcat'
  alias cat='batcat --style=plain --paging=never'
elif command -v bat >/dev/null 2>&1; then
  alias cat='bat --style=plain --paging=never'
fi

# ripgrep 智能接管 grep
if command -v rg >/dev/null 2>&1; then
  alias grep='rg --color=auto'
fi

# btop 替代 top
command -v btop >/dev/null 2>&1 && alias top='btop'

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

# process / disk (macOS 的 du 不支持 --max-depth，用 -d 1)
alias psg='ps aux | grep -i'
alias df='df -h'
if [[ -n "$IS_MACOS" ]]; then
  alias du='du -h -d 1'
else
  alias du='du -h --max-depth=1'
fi

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
# 12. 最终整理 PATH（防止上面 path 更新未导出）
# ---------------------------------------------------------

export PATH=${(j.:.)path}

# uv 安装配置
if [[ -f "$HOME/.local/bin/env" ]]; then
  . "$HOME/.local/bin/env"
fi

# tmux
[ -f "$XDG_CONFIG_HOME/tmux/tmux.conf" ] && tmux source-file "$XDG_CONFIG_HOME/tmux/tmux.conf"
