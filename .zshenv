# =========================================================
# ~/.zshenv
# 所有 zsh（含脚本、非交互 shell）最先加载：只放环境变量，不放别名和输出
# =========================================================

# ---------------------------------------------------------
# XDG 基础目录
# ---------------------------------------------------------
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"

for _d in "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" \
          "$XDG_DATA_HOME/zsh" "$XDG_CACHE_HOME/zsh"; do
  [[ -d "$_d" ]] || mkdir -p "$_d"
done
unset _d

# Zsh：.zshrc / .p10k.zsh 等都放在 ~/.config/zsh
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"

# ---------------------------------------------------------
# 不读 XDG 的工具：用环境变量重定向，避免在 ~ 下生成点目录
# 注意：从 Dock 启动的 GUI 应用不读本文件
# ---------------------------------------------------------

# 配置
export VIMINIT='let $MYVIMRC="$XDG_CONFIG_HOME/vim/vimrc" | source $MYVIMRC'  # vim 9.1 前不读 ~/.config/vim
export NPM_CONFIG_USERCONFIG="$XDG_CONFIG_HOME/npm/npmrc"    # 默认 ~/.npmrc
export PIP_CONFIG_FILE="$XDG_CONFIG_HOME/pip/pip.conf"
export IPYTHONDIR="$XDG_CONFIG_HOME/ipython"                  # 默认 ~/.ipython
export CONAN_HOME="$XDG_CONFIG_HOME/conan"                    # 默认 ~/.conan2
export MPLCONFIGDIR="$XDG_CONFIG_HOME/matplotlib"             # 默认 ~/.matplotlib

# 缓存
export npm_config_cache="$XDG_CACHE_HOME/npm"                 # 默认 ~/.npm
export TLDR_CACHE_DIR="$XDG_CACHE_HOME"                       # tldr 会在其下建 .tldrc；默认 ~/.tldrc
export GRAPHBLAS_CACHE_PATH="$XDG_CACHE_HOME/graphblas"       # SuiteSparse JIT；默认 ~/.SuiteSparse

# 状态 / 日志
export ROS_HOME="$XDG_STATE_HOME/ros"                         # ROS 2 日志；默认 ~/.ros

# ---------------------------------------------------------
# Homebrew 镜像（TUNA，与 setup.sh、uv.toml 一致）；外部已设置时不覆盖
# 放在 .zshenv：非交互脚本里的 brew 也需要；国内官方源基本不可用
# ---------------------------------------------------------
: ${HOMEBREW_API_DOMAIN:=https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles/api}
: ${HOMEBREW_BOTTLE_DOMAIN:=https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles}
: ${HOMEBREW_BREW_GIT_REMOTE:=https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git}
: ${HOMEBREW_PIP_INDEX_URL:=https://pypi.tuna.tsinghua.edu.cn/simple}
export HOMEBREW_API_DOMAIN HOMEBREW_BOTTLE_DOMAIN HOMEBREW_BREW_GIT_REMOTE HOMEBREW_PIP_INDEX_URL