# =========================================================
# ~/.zshenv
# 最早加载：只放最基础、最稳定的环境变量
# =========================================================

# XDG 目录
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"

# Zsh 配置目录
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"

# Vim（8.2 无原生 XDG 支持，用 VIMINIT 指向 XDG 路径；vim 9.1+ 可删掉这行）
export VIMINIT='let $MYVIMRC="$XDG_CONFIG_HOME/vim/vimrc" | source $MYVIMRC'

# npm 不认 ~/.config/npm/npmrc，用 NPM_CONFIG_USERCONFIG 指向 XDG 路径
export NPM_CONFIG_USERCONFIG="$XDG_CONFIG_HOME/npm/npmrc"

# 创建基础目录
typeset -gU _xdg_dirs=(
  "$XDG_CONFIG_HOME"
  "$XDG_CACHE_HOME"
  "$XDG_DATA_HOME"
  "$XDG_DATA_HOME/zsh"
  "$XDG_CACHE_HOME/zsh"
)

for dir in $_xdg_dirs; do
  [[ -d "$dir" ]] || mkdir -p "$dir"
done

unset _xdg_dirs