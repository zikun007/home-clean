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
case "$OS" in
  Linux)  IS_LINUX=1 ;;
  Darwin) IS_MACOS=1 ;;
  *) echo -e "${RED}不支持的系统: $OS (仅支持 Ubuntu Linux 与 macOS)${NC}"; exit 1 ;;
esac

echo -e "${BLUE}>>> 开始部署 home-clean 环境配置 ($([[ -n "$IS_MACOS" ]] && echo macOS || echo Ubuntu Linux))...${NC}"

# ==========================================
# 0. 安装系统依赖
# ==========================================
install_deps_linux() {
    echo -e "\n${BLUE}>>> 0. 安装基础系统依赖 (需要 sudo 权限)...${NC}"
    sudo apt update
    sudo apt install -y zsh tmux vim git curl wget tree xclip fontconfig \
        eza fd-find bat ripgrep btop
}

install_deps_macos() {
    echo -e "\n${BLUE}>>> 0. 安装基础系统依赖 (通过 Homebrew)...${NC}"
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}  [安装] 未检测到 Homebrew，正在安装...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install zsh tmux vim git wget tree eza fd bat ripgrep btop fontconfig
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
mkdir -p "$HOME/.config" "$HOME/.local" "$HOME/.local/share/fonts"

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
# 1. 处理 .config 下的文件夹 (除 fonts 外)
# ==========================================
echo -e "\n${BLUE}>>> 1. 部署 .config 目录...${NC}"
for folder in "$DOTFILES_DIR"/.config/*; do
    if [ -d "$folder" ]; then
        base_name=$(basename "$folder")
        # 字体由于系统读取路径问题，我们在后面单独处理
        if [ "$base_name" == "fonts" ]; then
            continue
        fi
        safe_link "$folder" "$HOME/.config/$base_name"
    fi
done

# ==========================================
# 2. 处理 .local 下的文件夹
# ==========================================
echo -e "\n${BLUE}>>> 2. 部署 .local 目录...${NC}"
for folder in "$DOTFILES_DIR"/.local/*; do
    if [ -d "$folder" ]; then
        base_name=$(basename "$folder")
        safe_link "$folder" "$HOME/.local/$base_name"
    fi
done

# ==========================================
# 3. 处理根目录的单文件
# ==========================================
echo -e "\n${BLUE}>>> 3. 部署根目录配置文件...${NC}"
safe_link "$DOTFILES_DIR/.zshenv" "$HOME/.zshenv"

# ==========================================
# 4. 处理 .pi（pi coding agent 配置）
# 注意：auth.json / mcp-auth.json / models-store.json / sessions/ 属于
# 敏感或运行时文件，不入仓库也不覆盖本地已有文件，只做“本地不存在则链接”
# ==========================================
echo -e "\n${BLUE}>>> 4. 部署 .pi (pi coding agent) 配置...${NC}"
if [ -d "$DOTFILES_DIR/.pi/agent" ]; then
    mkdir -p "$HOME/.pi/agent"

    # 仓库内的配置项（目录与单文件逐项链接）
    for item in agents prompts skills extensions \
                APPEND_SYSTEM.md settings.json mcp.json models.json; do
        safe_link "$DOTFILES_DIR/.pi/agent/$item" "$HOME/.pi/agent/$item"
    done

    # 敏感/运行时文件：仅当本地不存在时提示，绝不覆盖
    for private in auth.json mcp-auth.json models-store.json sessions; do
        if [ ! -e "$HOME/.pi/agent/$private" ]; then
            echo -e "${YELLOW}  [提示] $HOME/.pi/agent/$private 不存在，首次使用 pi 时会自动生成${NC}"
        fi
    done
else
    echo -e "${YELLOW}  [跳过] 仓库中不存在 .pi/agent 目录${NC}"
fi

# ==========================================
# 5. 处理系统字体与缓存
# ==========================================
echo -e "\n${BLUE}>>> 5. 部署终端极客字体...${NC}"
if [ -d "$DOTFILES_DIR/.config/fonts" ]; then
    # 将字体目录软链接到标准系统用户字体路径下
    safe_link "$DOTFILES_DIR/.config/fonts" "$HOME/.local/share/fonts/home-clean-fonts"
    if [[ -n "$IS_LINUX" ]]; then
        echo -e "${YELLOW}  [刷新] 正在重置系统字体缓存，请稍候...${NC}"
        fc-cache -fv > /dev/null
        echo -e "${GREEN}  [OK] 字体缓存已刷新${NC}"
    else
        echo -e "${GREEN}  [OK] macOS 会自动扫描用户字体目录，无需手动刷新缓存${NC}"
    fi
else
    echo -e "${YELLOW}  [跳过] 未在仓库中找到 .config/fonts 目录${NC}"
fi

# ==========================================
# 6. 切换默认 Shell
# ==========================================
ZSH_BIN="$(command -v zsh)"
if [ -n "$ZSH_BIN" ] && [ "$SHELL" != "$ZSH_BIN" ]; then
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
echo -e "\n${GREEN}>>> 🎉 部署完成！${NC}"
if [ -d "$BACKUP_DIR" ] && [ "$(ls -A "$BACKUP_DIR")" ]; then
    echo -e "所有被替换的旧系统配置已安全备份至: ${YELLOW}$BACKUP_DIR${NC}"
fi
echo -e "请执行 ${YELLOW}source ~/.zshenv${NC} 或直接重启终端以加载新环境。"
