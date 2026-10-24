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

    if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
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
    if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
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
    local aliases=(zsh:zsh tmux:tmux vim:vim git:git curl:curl wget:wget xclip:xclip fontconfig:fontconfig \
        eza:eza fd-find:fd-find bat:bat ripgrep:ripgrep btop:btop)  # tree 由 eza -T 替代
    for pkg in "${aliases[@]}"; do
        command -v "${pkg%%:*}" &>/dev/null || dpkg -s "${pkg##*:}" &>/dev/null || missing+=" ${pkg##*:}"
    done
    if [ -n "$missing" ]; then
        sudo apt update
        sudo apt install -y $missing
    else
        echo -e "${GREEN}  [OK] 系统依赖已全部安装${NC}"
    fi
}

install_deps_macos() {
    echo -e "\n${BLUE}>>> 0. 安装基础系统依赖 (通过 Homebrew)...${NC}"
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}  [安装] 未检测到 Homebrew，正在安装...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install zsh tmux vim git wget eza fd bat ripgrep btop fontconfig  # tree 由 eza -T 替代
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
# 1. 处理 .config 下的文件夹
# ==========================================
echo -e "\n${BLUE}>>> 1. 部署 .config 目录...${NC}"
for folder in "$DOTFILES_DIR"/.config/*; do
    if [ -d "$folder" ]; then
        base_name=$(basename "$folder")
        safe_link "$folder" "$HOME/.config/$base_name"
    fi
done

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
# 5. 刷新字体缓存（字体已由第 2 步从仓库复制到 ~/.local/share/fonts）
# ==========================================
if ls "$HOME"/.local/share/fonts/*.ttf &>/dev/null; then
    if command -v fc-cache &>/dev/null; then
        fc-cache -f >/dev/null 2>&1
        echo -e "\n${BLUE}>>> 5. 字体已部署，缓存已刷新${NC}"
        # fontconfig 的字体列表缓存在 gnome-terminal-server 启动时加载并常驻，
        # 只刷新磁盘缓存不会让已在运行的终端看到新字体（首选项里会显示旧名字
        # 或直接回退到 Noto）。必须重启终端服务器进程。
        echo -e "${YELLOW}  [注意] 已运行的终端不会自动感知新字体：请完全退出所有终端窗口后重新打开${NC}"
    fi
else
    echo -e "\n${YELLOW}>>> 5. [提示] ~/.local/share/fonts 无字体文件${NC}"
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
if [ -n "$ZSH_BIN" ] && [ "$(readlink -f "$SHELL")" != "$(readlink -f "$ZSH_BIN")" ]; then
    echo -e "${YELLOW}>>> 将 Zsh 设置为默认 Shell...${NC}"
    if [[ -n "$IS_MACOS" ]]; then
        # macOS 自带的 zsh 在 /etc/shells 白名单内，可直接切换
        chsh -s "$ZSH_BIN"
    else
        sudo chsh -s "$ZSH_BIN" "$USER"
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
