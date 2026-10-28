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
- **一键部署 (One-Click Setup):** 自动安装必备软件（Tmux, Vim, Zoxide, eza, fd, bat, ripgrep, btop 等；Linux 额外装 zsh，macOS 直接用系统自带 `/bin/zsh`），部署字体（Linux 到 `~/.local/share/fonts` + `fc-cache`，macOS 到 `~/Library/Fonts`），并完成 .config 软链映射与 .local 数据复制。
- **高效 Shell 体验:** 基于 Zsh + Oh My Zsh，预装语法高亮、自动建议补全、fzf-tab 与 Vi Mode，配合 `zoxide` 实现目录秒级智能跳转。
- **现代终端工具链:** 自动用 `eza` 接管 `ls`、`fd` 接管 `find`、`bat` 接管 `cat`、`rg` 接管 `grep`、`btop` 接管 `top`，并兼容 Ubuntu 打包名（`fdfind` / `batcat`）。
- **终端复用:** 精心配置的 Tmux 方案，支持鼠标操作、一键分屏及会话保持，极大提升远程调试效率。
- **C++ 工具链:** 自动安装编译器 / 构建 / 调试 / 静态分析完整链路——`build-essential`（Linux）、
  `cmake`、`ninja`、`clang`、`clangd`、`clang-format`、`clang-tidy`、`ccache`、`pkg-config`、`lcov`、`gdb`。
  仓库自带 `.clang-format` 会链接到 `~/.clang-format`（clang-format 不读 XDG，只向上查找父目录）。
  macOS 复用系统 CLT 的 clang/clangd/lldb/make，只补 CLT 缺的部件，不装 1.8GB 的 `llvm`。
- **轻量级编辑:** 针对 C++ 开发优化的纯 Vim 配置，支持基础语法高亮，拒绝臃肿。
- **SLAM 友好:** 包含常用的 CMake、GDB 调试别名及 ROS2 环境变量快速加载脚本（仅在检测到 `/opt/ros` 时生效）。

## 📂 仓库结构 (Directory Structure)

```text
home-clean/
├── LICENSE
├── README.md
├── README_en.md
├── AGENTS.md             # Agent 协作规范（memory / project / rules 三目录约定）
├── .config/              # 应用核心配置（XDG 布局，整目录软链到 ~/.config）
│   ├── .clang-format     # C++ 格式化规则（链到 ~/.clang-format，clang-format 不读 XDG）
│   ├── fontconfig/       # 旧字体家族名别名（避免升级后回退到 Noto）
│   ├── ghostty/          # Ghostty 终端（macOS 专用键在 Linux 上被忽略）
│   ├── git/              # git 详细配置
│   ├── tmux/             # Tmux 详细配置与插件
│   ├── vim/              # Vim 纯净版配置
│   └── zsh/              # Zsh 主题、Oh My Zsh 与插件
├── .agents/              # Agent 资产
│   ├── lark-bot/         # 飞书 ↔ 助手桥接（源码 / 测试 / systemd / launchd）
│   ├── memory/           # 开发进度与调试记录
│   ├── project/          # 经审核的整体方案
│   └── rules/            # 语言级编码规范
├── .local/               # 本地数据与资产（复制到 ~/.local，不覆盖已有内容）
│   ├── share/fonts/      # 终端字体 (FiraCode Nerd Font Mono、宋体)
│   └── share/zsh/        # zsh 历史
├── .zshenv               # Zsh 环境变量入口
└── setup.sh              # 跨平台部署与安装脚本
```

## 🚀 快速开始 (Quick Start)

> **警告:** 执行前建议备份原有的 `.zshrc` 或 `.tmux.conf`。

注意: setup.sh 会自动请求权限以安装系统依赖（Ubuntu 需 sudo，macOS 使用 Homebrew）。可选组件（lark-bot / omp-lark-bot）默认交互询问，非交互模式（如 CI）默认不安装，可用 `--help` 查看参数。脚本内置安全机制，会自动将你原有的配置备份到 ~/.dotfiles_backup 目录下，不会产生破坏性覆盖。

```bash
# 1. 克隆仓库
git clone https://github.com/ZiKun007/home-clean.git
cd home-clean

# 2. 开始自动部署（脚本自带执行权限）
./setup.sh
```

部署完成后，重新登录终端（或执行 `source ~/.zshenv`）即可享受全新的开发环境。

## 🤖 飞书机器人 (lark-bot)

`.agents/lark-bot/` 提供飞书 ↔ 助手的常驻桥接：监听飞书消息，调用 `codex exec` 或 `omp --mode json`，把进度和结果发回。**安装是可选项**：`setup.sh` 会逐项询问（已安装默认 Y，未安装默认 N），也可用参数直接指定；检测到 `~/.omp` 时才会询问 `omp-lark-bot`（local-omp）。

```bash
./setup.sh                         # 交互询问是否安装 lark-bot（可跳过）
./setup.sh --with-lark-bot         # 跳过询问，直接安装/更新 Codex 版
./setup.sh --without-lark-bot      # 明确跳过（不卸载已有安装）
vim ~/.agents/lark-bot/config.env  # 至少填写 OWNER_ID
lark-bot check
lark-bot start
lark-bot status
```

支持 `/pwd`、`/cd <path>`、`/status`、`/new`、`/stop`、`/help`；命令只识别 `/xxx`。默认只响应主人私聊，使用 `workspace-write` 沙箱；进度消息按批合并，回复使用飞书 Markdown。详见 `.agents/lark-bot/README.md`。

`setup.sh` 可反复执行：每次都重新询问可选组件，已有的 `config.env`、日志、数据库、会话数据不会被覆盖；跳过只是本次不安装，不会卸载。

**开机自启**：Linux 写 systemd unit（`~/.config/systemd/user/lark-bot.service`，需手动 `enable`）；
macOS 写 launchd LaunchAgent（`~/Library/LaunchAgents/com.home-clean.lark-bot.plist`）并立即加载，
登录自启、崩溃 10 秒内自动重启。`lark-bot stop` 会连同托管一起卸载，`restart` 走托管原生重启。

> **多机注意：** 飞书的事件总线对同一个 app 全局只允许一个消费者，本机 `lark-bot start` 前先确认另一台机器的 `lark-bot` 已停。`lark-bot check` 会检测并在冲突时报 `event_bus: occupied_by_another_host`。

> **双实例：** 同一台机器可同时跑 `lark-bot`（如 local-codex）和 `omp-lark-bot`（local-omp），
> 前提是两者使用**不同的飞书 app**（各自的 `LARK_PROFILE`）。事件总线按 appId 隔离，
> 所以互不冲突；共用同一个 app 才会报 `occupied_by_another_host`。
> `omp-lark-bot` 按调用名自动推断 `LARK_BOT_HOME=~/.omp/lark-bot` 和 launchd 标签
> `com.home-clean.omp-lark-bot`，两个实例的 `status` / `stop` / `restart` 互不影响。

## 🔧 平台差异说明

`.zshrc` 开头用 `uname` 设置 `IS_MACOS` / `IS_LINUX`，所有平台差异都基于它们；`setup.sh` 用同一套判断。

| 功能 | Ubuntu Linux | macOS |
|---|---|---|
| 包管理 | `apt`（`fd-find` / `bat`） | `Homebrew`（`fd` / `bat`） |
| Homebrew 路径 | — | `/opt/homebrew`（仅 Apple Silicon） |
| 字体注册 | 复制到 `~/.local/share/fonts` + `fc-cache -f` | 复制到 `~/Library/Fonts`（系统不扫描 `~/.local/share/fonts`） |
| `bat` / `fd` | 打包名 `batcat` / `fdfind`，按存在与否自动 alias | 原生名，无需 alias |
| `du` | `--max-depth=1` | `-d 1`（BSD du 不认 `--max-depth`） |
| `py` | 优先 `python`，否则 `python3` | `python3`（系统不提供 `python`） |
| CUDA / `LD_LIBRARY_PATH` | 检测 `/usr/local/cuda` 后注入 | 整个逻辑跳过 |
| ROS2 / colcon 别名 | `cw` `cs` `cb` `cbs` `sb` | 不定义（macOS 无 ROS2） |
| `ll` / `lt` | `eza -al --header` / `eza -l --sort=oldest --header` | 同左 |
| 默认 Shell | 装 `zsh` 后用 `sudo chsh` 切换 | 系统自带 `/bin/zsh`，不装 brew zsh、不改默认 Shell |
| C++ 编译器 | `build-essential`（gcc/g++） | Xcode CLT 的 `clang` / `clang++` |
| C++ 调试器 | `gdb` | `lldb`（CLT 自带，macOS 无 gdb） |
| C++ 构建 | `cmake` + `ninja-build` | `cmake` + `ninja` |
| 静态分析 / 格式化 | `clangd`、`clang-format`、`clang-tidy` | `clangd` 用 CLT，`clang-format` 单独装（不装 `llvm`） |
| Homebrew 镜像 | — | 未设置 `HOMEBREW_BOTTLE_DOMAIN` 时用 TUNA，避免 ghcr 龟速 |

`ll` 用 `--header` 而非 `-h`：`eza` 的 `-F`（`--classify[=WHEN]`）是可选参数，写成 `-alFh` 会被解析成 `-F h` 并直接报错。

`apt install` 逐步逐包执行：批量安装时只要有一个包在源里缺失（22.04 的 `eza`），整条命令会失败，
连 `cmake`、`clang` 都装不上。
