# =========================================================
# ~/.zshenv
# 最早加载：只放最基础、最稳定的环境变量
# =========================================================

# XDG 目录
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"

# Zsh 配置目录
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"

# 创建基础目录
typeset -gU _xdg_dirs=(
  "$XDG_CONFIG_HOME"
  "$XDG_CACHE_HOME"
  "$XDG_DATA_HOME"
  "$XDG_STATE_HOME"
  "$XDG_DATA_HOME/zsh"
  "$XDG_STATE_HOME/zsh"
  "$XDG_CACHE_HOME/zsh"
)

for dir in $_xdg_dirs; do
  [[ -d "$dir" ]] || mkdir -p "$dir"
done

unset _xdg_dirs