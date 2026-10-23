<div align="right">
  <a href="README.md">中文</a> | <strong>English</strong>
</div>

# 🛠️ home-clean: High-Efficiency Cross-Platform Development Environment

[![OS](https://img.shields.io/badge/OS-Ubuntu%20%7C%20macOS%20(Apple%20Silicon)-orange?logo=ubuntu)](https://ubuntu.com/)
[![Shell](https://img.shields.io/badge/Shell-Zsh-blue?logo=gnu-bash)](https://www.zsh.org/)
[![Editor](https://img.shields.io/badge/Editor-Vim-green?logo=vim)](https://www.vim.org/)
[![Multiplexer](https://img.shields.io/badge/Multiplexer-Tmux-black?logo=tmux)](https://github.com/tmux/tmux)

`home-clean` is a fast, automated, cross-platform environment configuration solution designed specifically for **SLAM researchers, robotics developers, and high-performance C++ engineers**. It supports both **Ubuntu Linux** and **macOS (Apple Silicon)**, transforming a chaotic `$HOME` directory into an organized workspace and building a hardcore development workflow based on `Zsh + Tmux + Vim` via a one-click deployment script.

## 🌟 Key Features

- **Cross-Platform Auto-Detection:** `setup.sh` detects the OS automatically — `apt` on Ubuntu, `Homebrew` on macOS; `.zshrc` switches platform-specific configs (Homebrew, CUDA, ROS2, etc.) via `IS_MACOS` / `IS_LINUX` flags. One config, every machine.
- **One-Click Setup:** Automatically installs dependencies (Zsh, Tmux, Vim, Zoxide, eza, fd, bat, ripgrep, btop, etc.), configures Nerd Font & SimSun, and safely establishes symlinks.
- **Efficient Shell Experience:** Zsh + Oh My Zsh with syntax highlighting, auto-suggestions, fzf-tab and Vi Mode. Integrated with `zoxide` for smart, sub-second directory jumping.
- **Modern CLI Toolchain:** Automatically replaces `ls` with `eza`, `find` with `fd`, `cat` with `bat`, `grep` with `rg`, and `top` with `btop`, with Ubuntu package names (`fdfind` / `batcat`) handled transparently.
- **Terminal Multiplexing:** Carefully crafted Tmux configuration supporting mouse operations, quick pane splitting, and session persistence, significantly boosting remote debugging efficiency.
- **Lightweight Editing:** A pure Vim configuration optimized for C++ development with essential syntax highlighting, strictly rejecting bloat.
- **SLAM-Friendly:** Includes common aliases for CMake, GDB debugging, and quick-load scripts for ROS2 workspaces (only activated when `/opt/ros` is detected).

## 📂 Directory Structure

```text
home-clean/
├── LICENSE
├── README.md           # Chinese Documentation
├── README_en.md        # English Documentation
├── .config/            # Core configurations (XDG-compliant layout)
│   ├── fontconfig/     # Aliases for legacy font family names
│   ├── git/            # Git configuration
│   ├── tmux/           # Tmux configs and plugins
│   ├── vim/            # Pure Vim setup
│   └── zsh/            # Zsh themes, Oh My Zsh and plugins
├── .local/             # Local data and assets (copied to ~/.local)
│   ├── share/fonts/    # FiraCode Nerd Font Mono & SimSun
│   └── share/zsh/      # Zsh history
├── .zshenv             # Zsh environment variables entry
└── setup.sh            # Cross-platform deployment script
```

## 🚀 Quick Start

Note: setup.sh will prompt for privileges to install system packages (`sudo` on Ubuntu, Homebrew on macOS). The script features a built-in safety mechanism that automatically backs up your existing configurations to ~/.dotfiles_backup to prevent any destructive overwrites.

```bash
# 1. Clone the repository
git clone https://github.com/ZiKun007/home-clean.git
cd home-clean

# 2. Run the automated deployment
./setup.sh
```

After deployment, log out and back in (or run `source ~/.zshenv`) to enjoy your new environment.

## 🔧 Platform Differences

| Feature | Ubuntu Linux | macOS (Apple Silicon) |
|---|---|---|
| Package manager | `apt` | `Homebrew` (/opt/homebrew) |
| PATH enhancements | CUDA, Conda, ROS2 | Homebrew, VS Code CLI, Conda |
| Font cache | Refresh via `fc-cache` | Auto-scanned by the system |
| bat / fd command names | `batcat` / `fdfind` (aliased automatically) | `bat` / `fd` |
| du alias | `--max-depth=1` | `-d 1` |
