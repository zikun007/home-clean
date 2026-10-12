<div align="right">
  <strong>中文</strong> | <a href="README_en.md">English</a>
</div>

# 🛠️ home-clean: High-Efficiency Cross-Platform Development Environment

[![OS](https://img.shields.io/badge/OS-Ubuntu%20%7C%20macOS%20(M系)-orange?logo=ubuntu)](https://ubuntu.com/)
[![Shell](https://img.shields.io/badge/Shell-Zsh-blue?logo=gnu-bash)](https://www.zsh.org/)
[![Editor](https://img.shields.io/badge/Editor-Vim-green?logo=vim)](https://www.vim.org/)
[![Multiplexer](https://img.shields.io/badge/Multiplexer-Tmux-black?logo=tmux)](https://github.com/tmux/tmux)

`home-clean` 是一个专为 **SLAM、机器人开发及高性能 C++ 工程师** 打造的跨平台环境快速配置方案，同时支持 **Ubuntu Linux** 与 **macOS (Apple Silicon)**。它将原本混乱的 `$HOME` 目录变得整洁有序，通过高度自动化的脚本，一键安装系统依赖并构建基于 `Zsh + Tmux + Vim` 的硬核开发流。

## 🌟 核心特性 (Key Features)

- **跨平台自适应:** `setup.sh` 自动检测操作系统——Ubuntu 使用 `apt`，macOS 使用 `Homebrew`；`.zshrc` 中通过 `IS_MACOS` / `IS_LINUX` 自动切换平台专属配置（Homebrew、CUDA、ROS2 等），一套配置走天下。
- **一键部署 (One-Click Setup):** 自动安装必备软件（Zsh, Tmux, Vim, Zoxide, eza, fd, bat, ripgrep, btop 等），处理极客字体与中文字体，并完成软链接映射。
- **高效 Shell 体验:** 基于 Zsh + Oh My Zsh，预装语法高亮、自动建议补全、fzf-tab 与 Vi Mode，配合 `zoxide` 实现目录秒级智能跳转。
- **现代终端工具链:** 自动用 `eza` 接管 `ls`、`fd` 接管 `find`、`bat` 接管 `cat`、`rg` 接管 `grep`、`btop` 接管 `top`，并兼容 Ubuntu 打包名（`fdfind` / `batcat`）。
- **终端复用:** 精心配置的 Tmux 方案，支持鼠标操作、一键分屏及会话保持，极大提升远程调试效率。
- **轻量级编辑:** 针对 C++ 开发优化的纯 Vim 配置，支持基础语法高亮，拒绝臃肿。
- **SLAM 友好:** 包含常用的 CMake、GDB 调试别名及 ROS2 环境变量快速加载脚本（仅在检测到 `/opt/ros` 时生效）。

## 📂 仓库结构 (Directory Structure)

```text
home-clean/
├── LICENSE
├── README.md
├── README_en.md
├── .config/            # 存放应用核心配置（XDG 规范布局）
│   ├── fonts/           # 终端字体 (FiraCode Nerd Font、宋体)
│   ├── git/             # git 详细配置
│   ├── tmux/            # Tmux 详细配置与插件
│   ├── vim/             # Vim 纯净版配置
│   └── zsh/             # Zsh 主题、Oh My Zsh 与插件
├── .local/              # 存放本地数据与状态
│   └── share/zsh/
├── .zshenv              # Zsh 环境变量入口
└── setup.sh             # 跨平台部署与安装脚本
```

## 🚀 快速开始 (Quick Start)

> **警告:** 执行前建议备份原有的 `.zshrc` 或 `.tmux.conf`。

注意: setup.sh 会自动请求权限以安装系统依赖（Ubuntu 需 sudo，macOS 使用 Homebrew）。脚本内置安全机制，会自动将你原有的配置备份到 ~/.dotfiles_backup 目录下，不会产生破坏性覆盖。

```bash
# 1. 克隆仓库
git clone https://github.com/ZiKun007/home-clean.git
cd home-clean

# 2. 开始自动部署（脚本自带执行权限）
./setup.sh
```

部署完成后，重新登录终端（或执行 `source ~/.zshenv`）即可享受全新的开发环境。

## 🔧 平台差异说明

| 功能 | Ubuntu Linux | macOS (Apple Silicon) |
|---|---|---|
| 包管理 | `apt` | `Homebrew` (/opt/homebrew) |
| PATH 增强 | CUDA、Conda、ROS2 | Homebrew、VS Code CLI、Conda |
| 字体缓存 | `fc-cache` 手动刷新 | 系统自动扫描用户字体目录 |
| bat / fd 命令名 | `batcat` / `fdfind`（已自动 alias） | `bat` / `fd` |
| du 别名 | `--max-depth=1` | `-d 1` |
