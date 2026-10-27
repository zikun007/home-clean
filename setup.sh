#!/usr/bin/env bash

# ==============================================================================
# home-clean 环境部署脚本
# 跨平台支持：Ubuntu Linux 与 macOS (Apple Silicon)，自动检测系统并适配
# ==============================================================================

set -u

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$HOME/.dotfiles_backup/$(date +%Y%m%d_%H%M%S)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ==========================================
# 系统检测
# ==========================================
OS="$(uname -s)"
IS_LINUX=""
IS_MACOS=""
case "$OS" in
  Linux)  IS_LINUX=1 ;;
  Darwin) IS_MACOS=1 ;;
  *) echo -e "${RED}不支持的系统: $OS (仅支持 Ubuntu Linux 与 macOS)${NC}"; exit 1 ;;
esac

# ==========================================
# 命令行参数：可选组件由用户决定
# ==========================================
WITH_LARK_BOT="auto"   # auto | yes | no
WITH_OMP_BOT="auto"    # auto | yes | no
INTERACTIVE="auto"     # auto | yes | no
SUMMARY=""

usage() {
    cat <<'EOF'
用法: ./setup.sh [选项]

可选组件（可重复执行，随时改选；跳过不会卸载已有安装）：
  --with-lark-bot      安装/更新 Codex 版 lark-bot
  --without-lark-bot   跳过 lark-bot
  --with-omp-bot       安装/更新 omp-lark-bot（需已有 ~/.omp）
  --without-omp-bot    跳过 omp-lark-bot

运行模式：
  --interactive        强制进入交互选择
  --non-interactive    强制非交互（不安装任何可选组件，除非显式 --with-*）
  -h, --help           显示本帮助

默认行为：
  stdin 是终端时交互询问；已安装默认 Y，未安装默认 N。
  非终端（脚本/CI）默认不安装可选组件。

已有 config.env、日志、数据库、会话数据不会被覆盖。
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --with-lark-bot)    WITH_LARK_BOT="yes" ;;
        --without-lark-bot) WITH_LARK_BOT="no" ;;
        --with-omp-bot)     WITH_OMP_BOT="yes" ;;
        --without-omp-bot)  WITH_OMP_BOT="no" ;;
        --interactive)      INTERACTIVE="yes" ;;
        --non-interactive|--yes|-y) INTERACTIVE="no" ;;
        -h|--help)          usage; exit 0 ;;
        *)
            echo -e "${RED}未知参数: $1${NC}" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$INTERACTIVE" = "auto" ]; then
    if [ -t 0 ]; then
        INTERACTIVE="yes"
    else
        INTERACTIVE="no"
    fi
fi

echo -e "${BLUE}>>> 开始部署 home-clean 环境配置 ($([[ -n "$IS_MACOS" ]] && echo macOS || echo Ubuntu Linux))...${NC}"

ask_yes_no() {
    # $1=问题  $2=默认值 (y/n)；返回 0=是，1=否
    local prompt="$1" default="$2" answer hint
    if [ "$default" = "y" ]; then hint="[Y/n]"; else hint="[y/N]"; fi
    while true; do
        printf "  %s %s " "$prompt" "$hint"
        if ! IFS= read -r answer; then
            answer=""
        fi
        answer="${answer:-$default}"
        case "$answer" in
            y|Y|yes|YES|Yes) return 0 ;;
            n|N|no|NO|No) return 1 ;;
            *) echo "  请输入 y 或 n" ;;
        esac
    done
}

LARK_BOT_HOME="$HOME/.agents/lark-bot"
OMP_BOT_HOME="$HOME/.omp/lark-bot"

lark_bot_installed() {
    [ -f "$LARK_BOT_HOME/config.env" ] || [ -L "$HOME/.local/bin/lark-bot" ] \
        || [ -f "$HOME/.config/systemd/user/lark-bot.service" ]
}

omp_bot_installed() {
    [ -f "$OMP_BOT_HOME/config.env" ] || [ -L "$HOME/.local/bin/omp-lark-bot" ] \
        || [ -f "$HOME/.config/systemd/user/omp-lark-bot.service" ]
}

# 决定是否处理某个可选组件：结果写入 DECIDED (yes/no)
decide_component() {
    local choice="$1" installed="$2" label="$3"
    DECIDED="no"
    case "$choice" in
        yes) DECIDED="yes"; return ;;
        no)  DECIDED="no"; return ;;
    esac
    # choice=auto
    [ "$INTERACTIVE" = "yes" ] || return
    if [ "$installed" = "1" ]; then
        if ask_yes_no "[可选] 更新 $label ?" y; then DECIDED="yes"; fi
    else
        if ask_yes_no "[可选] 安装 $label ?" n; then DECIDED="yes"; fi
    fi
}

# 生成并加载 launchd LaunchAgent（macOS）
# $1=标签 $2=运行时目录
install_launchagent() {
    local label="$1" bot_home="$2"
    local plist="$HOME/Library/LaunchAgents/$label.plist"
    mkdir -p "$HOME/Library/LaunchAgents" "$bot_home/logs"
    sed -e "s|__LABEL__|$label|g" \
        -e "s|__HOME__|$HOME|g" \
        -e "s|__BOT_HOME__|$bot_home|g" \
        "$DOTFILES_DIR/.agents/lark-bot/launchd/lark-bot.plist" > "$plist"
    # 先卸载旧实例，再按新 plist 加载
    launchctl bootout "gui/$UID/$label" 2>/dev/null || true
    if launchctl bootstrap "gui/$UID" "$plist" 2>/dev/null; then
        echo -e "${GREEN}  [OK] LaunchAgent 已加载: $label（登录自启 + 崩溃自动重启）${NC}"
    else
        echo -e "${YELLOW}  [提示] 已写入 $plist，重新登录后生效；或手动 launchctl bootstrap gui/$UID $plist${NC}"
    fi
}

install_lark_bot() {
    echo -e "\n${BLUE}>>> 4. 部署 .agents/lark-bot 运行时...${NC}"
    mkdir -p "$LARK_BOT_HOME/logs" "$LARK_BOT_HOME/memory"
    if [ ! -f "$LARK_BOT_HOME/config.env" ]; then
        install -m 600 "$DOTFILES_DIR/.agents/lark-bot/config.example.env" "$LARK_BOT_HOME/config.env"
        echo -e "${YELLOW}  [提示] 已生成 $LARK_BOT_HOME/config.env，请填写 OWNER_ID 后启动${NC}"
    else
        echo -e "${GREEN}  [保留] $LARK_BOT_HOME/config.env${NC}"
    fi
    mkdir -p "$HOME/.local/bin"
    ln -sfn "$DOTFILES_DIR/.agents/lark-bot/bin/lark-bot" "$HOME/.local/bin/lark-bot"
    echo -e "${GREEN}  [链接] ~/.local/bin/lark-bot${NC}"

    if [ -n "$IS_MACOS" ]; then
        install_launchagent "com.home-clean.lark-bot" "$LARK_BOT_HOME"
    elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        mkdir -p "$HOME/.config/systemd/user"
        install -m 644 "$DOTFILES_DIR/.agents/lark-bot/systemd/lark-bot.service" \
            "$HOME/.config/systemd/user/lark-bot.service"
        systemctl --user daemon-reload 2>/dev/null || true
        echo -e "${YELLOW}  [提示] 可执行 systemctl --user enable --now lark-bot 启动${NC}"
    fi
}

install_omp_bot() {
    echo -e "\n${BLUE}>>> 4b. 部署 omp-lark-bot 运行时...${NC}"
    mkdir -p "$OMP_BOT_HOME/logs" "$OMP_BOT_HOME/memory"
    if [ ! -f "$OMP_BOT_HOME/config.env" ]; then
        install -m 600 "$DOTFILES_DIR/.agents/lark-bot/config.omp.example.env" \
            "$OMP_BOT_HOME/config.env"
        echo -e "${YELLOW}  [提示] 已生成 $OMP_BOT_HOME/config.env，请填写 OWNER_ID / LARK_PROFILE${NC}"
    else
        echo -e "${GREEN}  [保留] $OMP_BOT_HOME/config.env${NC}"
    fi
    ln -sfn "$DOTFILES_DIR/.agents/lark-bot/bin/lark-bot" "$HOME/.local/bin/omp-lark-bot"
    echo -e "${GREEN}  [链接] ~/.local/bin/omp-lark-bot${NC}"
    if [ -n "$IS_MACOS" ]; then
        install_launchagent "com.home-clean.omp-lark-bot" "$OMP_BOT_HOME"
    elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        mkdir -p "$HOME/.config/systemd/user"
        install -m 644 "$DOTFILES_DIR/.agents/lark-bot/systemd/omp-lark-bot.service" \
            "$HOME/.config/systemd/user/omp-lark-bot.service"
        systemctl --user daemon-reload 2>/dev/null || true
        echo -e "${YELLOW}  [提示] 可执行 systemctl --user enable --now omp-lark-bot 启动${NC}"
    fi
}

# ==========================================
# 0. 安装系统依赖
# ==========================================
install_deps_linux() {
    echo -e "\n${BLUE}>>> 0. 安装基础系统依赖 (需要 sudo 权限)...${NC}"
    # 先检测缺失的包，避免每次全量 sudo apt update
    local missing=""
    local pkg
    # 基础工具；fzf 供 .zshrc 的 fzf/fzf-tab 插件使用
    local aliases=(zsh:zsh tmux:tmux vim:vim git:git curl:curl wget:wget xclip:xclip fontconfig:fontconfig \
        fzf:fzf eza:eza fd-find:fd-find bat:bat ripgrep:ripgrep btop:btop)
    # C++ 工具链：编译器 + 构建 + 调试 + 静态分析 + 格式化
    aliases+=(build-essential:build-essential cmake:cmake ninja-build:ninja-build \
        gdb:gdb clang:clang clangd:clangd clang-format:clang-format clang-tidy:clang-tidy \
        ccache:ccache pkg-config:pkg-config lcov:lcov)
    for pkg in "${aliases[@]}"; do
        command -v "${pkg%%:*}" &>/dev/null || dpkg -s "${pkg##*:}" &>/dev/null || missing+=" ${pkg##*:}"
    done
    if [ -n "$missing" ]; then
        sudo apt update
        # 逐个安装：批量装时只要有一个包在源里不存在（如 22.04 的 eza），
        # 整条 apt install 会失败，导致 cmake/clang 这类关键包也装不上。
        local failed=""
        for pkg in $missing; do
            if ! sudo apt install -y "$pkg"; then
                failed+=" $pkg"
            fi
        done
        [ -n "$failed" ] && echo -e "${YELLOW}  [提示] 以下包安装失败（可能需第三方源）:$failed${NC}" >&2
    else
        echo -e "${GREEN}  [OK] 系统依赖已全部安装${NC}"
    fi
}

install_deps_macos() {
    echo -e "\n${BLUE}>>> 0. 安装基础系统依赖 (通过 Homebrew)...${NC}"
    # 脚本里通常没跑过 shellenv，brew 可能装了但不在 PATH
    if ! command -v brew &> /dev/null && [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}  [安装] 未检测到 Homebrew，正在安装...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    if ! command -v brew &> /dev/null; then
        echo -e "${RED}  [失败] Homebrew 不可用，请手动安装后重跑${NC}" >&2
        return 1
    fi
    # 国内直连 ghcr.io 拉 bottle 经常只有几十 KB/s，换镜像可快 2-3 个数量级。
    # 已显式设置过的用户不覆盖。
    if [ -z "${HOMEBREW_BOTTLE_DOMAIN:-}" ]; then
        export HOMEBREW_BOTTLE_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles"
    fi
    # 只装缺失的，避免每次全量升级
    local missing=()
    local formula
    # C++ 工具链。macOS CLT 已提供 clang / clang++ / clangd / lldb / make，
    # 这里只补 CLT 没有的：cmake/ninja 构建、clang-format 格式化、ccache 加速。
    # 不要装 llvm：那是整套 1.8GB 的 clang，而 clang-format 独立包只有 3.8MB。
    for formula in zsh tmux vim git wget fzf eza fd bat ripgrep btop fontconfig \
        cmake ninja clang-format ccache pkg-config; do
        brew list --formula "$formula" &>/dev/null || missing+=("$formula")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        brew install "${missing[@]}"
    else
        echo -e "${GREEN}  [OK] 系统依赖已全部安装${NC}"
    fi
    # Xcode CLT 必须先装，否则 clang/clang++/make 全都不存在
    if ! xcode-select -p >/dev/null 2>&1; then
        echo -e "${YELLOW}  [提示] 未安装 Xcode Command Line Tools，执行:xcode-select --install${NC}" >&2
    fi
}

if [[ -n "$IS_LINUX" ]]; then
    install_deps_linux
else
    install_deps_macos
fi

# zoxide (新一代 cd 命令)
if ! command -v zoxide &> /dev/null; then
    echo -e "${YELLOW}  [安装] 正在获取 zoxide...${NC}"
    curl -sS https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | bash
else
    echo -e "${GREEN}  [OK] zoxide 已安装${NC}"
fi

# ==========================================
# 准备目标基础目录
# ==========================================
mkdir -p "$HOME/.config" "$HOME/.local"

# ==========================================
# 核心函数：安全备份并创建软链接
# ==========================================
safe_link() {
    local src="$1"
    local dest="$2"

    if [ ! -e "$src" ]; then
        echo -e "${YELLOW}  [跳过] 源文件不存在: $src${NC}"
        return
    fi

    if [ -e "$dest" ] || [ -L "$dest" ]; then
        if [ "$(readlink "$dest")" == "$src" ]; then
            echo -e "${GREEN}  [OK] 已经链接: $dest${NC}"
            return
        fi

        mkdir -p "$BACKUP_DIR"
        echo -e "${YELLOW}  [备份] 发现现有配置，移动 $dest -> $BACKUP_DIR/${NC}"
        mv "$dest" "$BACKUP_DIR/"
    fi

    ln -s "$src" "$dest"
    echo -e "${GREEN}  [链接] $src -> $dest${NC}"
}

# ==========================================
# 1. 处理 .config 下的内容
# 目录整目录软链；点文件（如 .clang-format）单独链接，否则会被漏掉
# ==========================================
echo -e "\n${BLUE}>>> 1. 部署 .config 目录...${NC}"
for folder in "$DOTFILES_DIR"/.config/*; do
    if [ -d "$folder" ]; then
        base_name=$(basename "$folder")
        safe_link "$folder" "$HOME/.config/$base_name"
    fi
done
# clang-format 只从源文件目录向上查找 .clang-format（不读 XDG），
# 所以必须放到 $HOME 才能在任意项目里生效
safe_link "$DOTFILES_DIR/.config/.clang-format" "$HOME/.clang-format"

# ==========================================
# 2. 处理 .local 下的内容：复制（非软链）
# .local 存放数据/资产（字体），部署时从仓库复制到 ~/.local；
# 本地已有内容不覆盖（用户数据优先）；仅复制叶子条目，不碰 share 整目录
# ==========================================
echo -e "\n${BLUE}>>> 2. 部署 .local 目录 (复制)...${NC}"
for item in "$DOTFILES_DIR"/.local/* "$DOTFILES_DIR"/.local/share/*; do
    [ -e "$item" ] || continue
    rel="${item#"$DOTFILES_DIR"/.local/}"
    # 跳过中间层目录本身（如 share）：.local/share 是用户数据目录
    # （keyrings/Trash/应用数据等），绝不能整目录替换
    [ "$rel" = "share" ] && continue
    dest="$HOME/.local/$rel"
    if [ -d "$item" ]; then
        mkdir -p "$dest"
        # 逐文件复制，已存在则跳过（保留本地运行时数据）
        for f in "$item"/* "$item"/.[!.]*; do
            [ -e "$f" ] || continue
            fname=$(basename "$f")
            if [ -e "$dest/$fname" ]; then
                echo -e "${GREEN}  [OK] 已存在: ~/.local/$rel/$fname${NC}"
            else
                cp -r "$f" "$dest/$fname"
                echo -e "${GREEN}  [复制] ~/.local/$rel/$fname${NC}"
            fi
        done
    else
        mkdir -p "$(dirname "$dest")"
        if [ -e "$dest" ]; then
            echo -e "${GREEN}  [OK] 已存在: ~/.local/$rel${NC}"
        else
            cp "$item" "$dest"
            echo -e "${GREEN}  [复制] ~/.local/$rel${NC}"
        fi
    fi
done

# ==========================================
# 3. 处理根目录的单文件
# ==========================================
echo -e "\n${BLUE}>>> 3. 部署根目录配置文件...${NC}"
safe_link "$DOTFILES_DIR/.zshenv" "$HOME/.zshenv"

# npm 全局前缀：官方 pkg 装的 node 前缀是 /usr/local（root 所有），
# 不加这一步 `npm i -g` 必然 EACCES。只补 prefix，不动已有的 registry 设置。
NPMRC="$HOME/.config/npm/npmrc"
if [ ! -f "$NPMRC" ]; then
    mkdir -p "$(dirname "$NPMRC")"
    printf 'prefix=${HOME}/.local\n' > "$NPMRC"
    echo -e "${GREEN}  [写入] $NPMRC (prefix=\${HOME}/.local)${NC}"
elif ! grep -q '^prefix=' "$NPMRC"; then
    printf 'prefix=${HOME}/.local\n' >> "$NPMRC"
    echo -e "${GREEN}  [追加] $NPMRC (prefix=\${HOME}/.local)${NC}"
else
    echo -e "${GREEN}  [OK] 已存在: $NPMRC${NC}"
fi

# ==========================================
# 4. 可选组件：lark-bot（Codex 版）
# 仓库只保存源码；配置/状态/日志/记忆放在 ~/.agents/lark-bot
# ==========================================
if lark_bot_installed; then lark_installed=1; else lark_installed=0; fi
decide_component "$WITH_LARK_BOT" "$lark_installed" "Codex 版 lark-bot"
if [ "$DECIDED" = "yes" ]; then
    install_lark_bot
    SUMMARY="${SUMMARY}  lark-bot       : 已部署 (~/.agents/lark-bot)\n"
else
    echo -e "\n${YELLOW}>>> 4. [跳过] 本次不安装 lark-bot（已有安装不受影响；--with-lark-bot 可强制安装）${NC}"
    SUMMARY="${SUMMARY}  lark-bot       : 已跳过\n"
fi

# ==========================================
# 4b. 可选组件：omp-lark-bot（local-omp）
# 仅在用户已有 ~/.omp 时适用，使用独立配置目录和 lark-cli profile
# ==========================================
if [ -d "$HOME/.omp" ]; then
    if omp_bot_installed; then omp_installed=1; else omp_installed=0; fi
    decide_component "$WITH_OMP_BOT" "$omp_installed" "omp-lark-bot"
    if [ "$DECIDED" = "yes" ]; then
        install_omp_bot
        SUMMARY="${SUMMARY}  omp-lark-bot   : 已部署 (~/.omp/lark-bot)\n"
    else
        echo -e "\n${YELLOW}>>> 4b. [跳过] 本次不安装 omp-lark-bot${NC}"
        SUMMARY="${SUMMARY}  omp-lark-bot   : 已跳过\n"
    fi
elif [ "$WITH_OMP_BOT" = "yes" ]; then
    echo -e "\n${YELLOW}>>> 4b. [跳过] 未检测到 ~/.omp，无法部署 omp-lark-bot${NC}"
    SUMMARY="${SUMMARY}  omp-lark-bot   : 未检测到 ~/.omp，跳过\n"
else
    SUMMARY="${SUMMARY}  omp-lark-bot   : 不适用（无 ~/.omp）\n"
fi

# ==========================================
# 5. 字体注册
# Linux: ~/.local/share/fonts + fc-cache
# macOS: 系统只扫描 ~/Library/Fonts，额外复制一份过去
# ==========================================
FONT_SRC_DIR="$HOME/.local/share/fonts"
if ls "$FONT_SRC_DIR"/*.ttf &>/dev/null; then
    if [ -n "$IS_MACOS" ]; then
        echo -e "\n${BLUE}>>> 5. 注册字体到 ~/Library/Fonts (macOS)...${NC}"
        mkdir -p "$HOME/Library/Fonts"
        # -n 保留本地已有文件
        cp -n "$FONT_SRC_DIR"/*.ttf "$HOME/Library/Fonts/" && echo -e "${GREEN}  [完成] 字体已注册${NC}"
    elif command -v fc-cache &>/dev/null; then
        fc-cache -f >/dev/null 2>&1
        echo -e "\n${BLUE}>>> 5. 字体已部署，缓存已刷新${NC}"
    else
        echo -e "\n${YELLOW}>>> 5. [提示] 未安装 fontconfig，跳过 fc-cache${NC}"
    fi
    echo -e "${YELLOW}  [注意] 已运行的终端启动时才加载字体列表，请完全退出后重新打开${NC}"
else
    echo -e "\n${YELLOW}>>> 5. [提示] $FONT_SRC_DIR 无字体文件${NC}"
fi

# ==========================================
# 6. 安装 TPM（tmux 插件管理器本体）
# 其余插件由 TPM 管理：首次进入 tmux 后按 prefix + I 安装
# ==========================================
TMUX_PLUGIN_DIR="$HOME/.local/share/tmux"
install_tpm() {
    command -v git &>/dev/null || { echo -e "${YELLOW}  [跳过] 无 git，请稍后手动安装 TPM${NC}"; return; }
    if [ -x "$TMUX_PLUGIN_DIR/tpm/tpm" ]; then
        echo -e "${GREEN}  [OK] TPM 已安装${NC}"
        return
    fi
    mkdir -p "$TMUX_PLUGIN_DIR"
    echo -e "${YELLOW}  [安装] clone TPM...${NC}"
    if git clone --depth 1 -q https://github.com/tmux-plugins/tpm.git "$TMUX_PLUGIN_DIR/tpm"; then
        echo -e "${GREEN}  [OK] TPM 安装完成；首次进入 tmux 后按 prefix + I 安装其余插件${NC}"
    else
        echo -e "${YELLOW}  [提示] TPM 下载失败(可能需代理)，可稍后手动 clone 或用 proxy_on 后重跑${NC}"
    fi
}
if command -v tmux &>/dev/null; then
    echo -e "\n${BLUE}>>> 6. 安装 TPM...${NC}"
    install_tpm
else
    echo -e "\n${YELLOW}>>> 6. [跳过] 未安装 tmux${NC}"
fi

# ==========================================
# 7. 切换默认 Shell
# ==========================================
ZSH_BIN="$(command -v zsh)"
# 用 python3 解析真实路径：BSD readlink 的 -f 在旧 macOS 上不可靠
real_path() {
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1" 2>/dev/null || printf '%s' "$1"
}
if [ -n "$ZSH_BIN" ] && [ "$(real_path "$SHELL")" != "$(real_path "$ZSH_BIN")" ]; then
    ZSH_REAL="$(real_path "$ZSH_BIN")"
    echo -e "${YELLOW}>>> 将 Zsh 设置为默认 Shell...${NC}"
    if [ -n "$IS_MACOS" ]; then
        # macOS 只接受 /etc/shells 白名单内的 shell；brew 的 zsh 默认不在其中
        if [[ "$ZSH_REAL" == /opt/homebrew/* ]] && ! grep -qx "$ZSH_REAL" /etc/shells; then
            echo -e "${YELLOW}  需要先执行: echo $ZSH_REAL | sudo tee -a /etc/shells${NC}"
        else
            chsh -s "$ZSH_REAL"
        fi
    else
        sudo chsh -s "$ZSH_REAL" "$USER"
    fi
    echo -e "${GREEN}  设置完成，重新登录后生效。${NC}"
fi

# ==========================================
# 完成提示
# ==========================================
if [ -n "$SUMMARY" ]; then
    echo -e "\n${BLUE}>>> 可选组件状态${NC}"
    echo -e "$SUMMARY"
    echo -e "  ${YELLOW}提示: 可随时重跑 ./setup.sh 重新选择${NC}"
fi
echo -e "\n${GREEN}>>> 🎉 部署完成！${NC}"
if [ -d "$BACKUP_DIR" ] && [ "$(ls -A "$BACKUP_DIR")" ]; then
    echo -e "所有被替换的旧系统配置已安全备份至: ${YELLOW}$BACKUP_DIR${NC}"
fi
echo -e "请执行 ${YELLOW}source ~/.zshenv${NC} 或直接重启终端以加载新环境。"
