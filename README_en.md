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
- **One-Click Setup:** Automatically installs dependencies (Tmux, Vim, Zoxide, eza, fd, bat, ripgrep, btop, etc. — plus `zsh` on Linux; macOS uses its bundled `/bin/zsh`), registers Nerd Font & SimSun (`~/.local/share/fonts` + `fc-cache` on Linux, `~/Library/Fonts` on macOS), and safely establishes symlinks.
- **Efficient Shell Experience:** Zsh + Oh My Zsh with syntax highlighting, auto-suggestions, fzf-tab and Vi Mode. Integrated with `zoxide` for smart, sub-second directory jumping.
- **Modern CLI Toolchain:** Automatically replaces `ls` with `eza`, `find` with `fd`, `cat` with `bat`, `grep` with `rg`, and `top` with `btop`, with Ubuntu package names (`fdfind` / `batcat`) handled transparently.
- **Terminal Multiplexing:** Carefully crafted Tmux configuration supporting mouse operations, quick pane splitting, and session persistence, significantly boosting remote debugging efficiency.
- **C++ Toolchain:** Installs the full compile/build/debug/analyze chain — `build-essential` (Linux), `cmake`, `ninja`, `clang`, `clangd`, `clang-format`, `clang-tidy`, `ccache`, `pkg-config`, `lcov`, `gdb`. The repo's `.clang-format` is linked to `~/.clang-format` (clang-format ignores XDG and only walks parent dirs). macOS reuses the system CLT clang/clangd/lldb/make and only adds what CLT lacks — never the 1.8 GB `llvm` formula.
- **Lightweight Editing:** A pure Vim configuration optimized for C++ development with essential syntax highlighting, strictly rejecting bloat.
- **SLAM-Friendly:** Includes common aliases for CMake, GDB debugging, and quick-load scripts for ROS2 workspaces (only activated when `/opt/ros` is detected).

## 📂 Directory Structure

```text
home-clean/
├── LICENSE
├── README.md           # Chinese Documentation
├── README_en.md        # English Documentation
├── AGENTS.md           # Agent conventions (memory / project / rules)
├── .config/            # Core configurations (XDG-compliant layout, symlinked to ~/.config)
│   ├── .clang-format   # C++ formatting rules (linked to ~/.clang-format; clang-format ignores XDG)
│   ├── fontconfig/     # Aliases for legacy font family names
│   ├── ghostty/        # Ghostty terminal (macOS-only keys are ignored on Linux)
│   ├── git/            # Git configuration
│   ├── tmux/           # Tmux configs and plugins
│   ├── vim/            # Pure Vim setup
│   └── zsh/            # Zsh themes, Oh My Zsh and plugins
├── .agents/            # Agent assets
│   ├── lark-bot/       # Feishu ↔ agent bridge (source / tests / systemd / launchd)
│   ├── memory/         # Progress notes and debugging logs
│   ├── project/        # Reviewed design documents
│   └── rules/          # Language-level coding rules
├── .local/             # Local data and assets (copied to ~/.local)
│   ├── share/fonts/    # FiraCode Nerd Font Mono & SimSun
│   └── share/zsh/      # Zsh history
├── .zshenv             # Zsh environment variables entry
└── setup.sh            # Cross-platform deployment script
```

## 🚀 Quick Start

Note: setup.sh will prompt for privileges to install system packages (`sudo` on Ubuntu, Homebrew on macOS). Optional components (lark-bot / omp-lark-bot) are asked interactively; non-interactive runs (CI) install nothing by default. See `--help`. The script features a built-in safety mechanism that automatically backs up your existing configurations to ~/.dotfiles_backup to prevent any destructive overwrites.

```bash
# 1. Clone the repository
git clone https://github.com/ZiKun007/home-clean.git
cd home-clean

# 2. Run the automated deployment
./setup.sh
```

After deployment, log out and back in (or run `source ~/.zshenv`) to enjoy your new environment.

## 🤖 Feishu Lark Bot (lark-bot)

`.agents/lark-bot/` is an always-on Feishu ↔ agent bridge: it consumes Lark messages, runs `codex exec` or `omp --mode json`, and streams progress plus the final answer back. **Installing it is optional**: `setup.sh` asks per component (default Y when already installed, N when not), or you can pass flags; `omp-lark-bot` (local-omp) is only offered when `~/.omp` exists.

```bash
./setup.sh                         # asks whether to install lark-bot (skippable)
./setup.sh --with-lark-bot         # no prompt: install/update the Codex variant
./setup.sh --without-lark-bot      # skip explicitly (existing install is kept)
vim ~/.agents/lark-bot/config.env  # set OWNER_ID
lark-bot check
lark-bot start
lark-bot status
```

Commands: `/pwd`, `/cd <path>`, `/status`, `/new`, `/stop`, `/help` (slash form only). Owner-only P2P by default; `workspace-write` sandbox; progress is batched and replies use Lark Markdown. See `.agents/lark-bot/README.md`.

`setup.sh` is re-runnable: optional components are asked again each run, existing `config.env`, logs, DB and session data are never overwritten, and skipping never uninstalls anything.

**Autostart:** Linux installs a systemd unit (`~/.config/systemd/user/lark-bot.service`, enabled manually); macOS installs and immediately loads a launchd LaunchAgent (`~/Library/LaunchAgents/com.home-clean.lark-bot.plist`) that starts at login and respawns within 10 s of a crash. `lark-bot stop` unloads the supervisor too, and `restart` goes through it.

> **Multi-host:** Feishu allows exactly one event-bus consumer per app globally. Stop the other host's `lark-bot` before starting this one; `lark-bot check` detects the conflict and reports `event_bus: occupied_by_another_host`.

> **Two instances:** `lark-bot` (e.g. local-codex) and `omp-lark-bot` (local-omp) can run side by side
> on one machine as long as each uses a **different Feishu app** (`LARK_PROFILE`). The event bus is
> isolated per appId, so they never conflict; sharing one app is what triggers `occupied_by_another_host`.
> `omp-lark-bot` infers `LARK_BOT_HOME=~/.omp/lark-bot` and the launchd label
> `com.home-clean.omp-lark-bot` from its invoked name, so `status` / `stop` / `restart` stay per-instance.

## 🔧 Platform Differences

`.zshrc` sets `IS_MACOS` / `IS_LINUX` from `uname` at the top; every platform difference keys off them, and `setup.sh` uses the same check.

| Feature | Ubuntu Linux | macOS |
|---|---|---|
| Package manager | `apt` (`fd-find` / `bat`) | `Homebrew` (`fd` / `bat`) |
| Homebrew path | — | `/opt/homebrew` (Apple Silicon only) |
| Font registration | Copy to `~/.local/share/fonts` + `fc-cache -f` | Copy to `~/Library/Fonts` (the system never scans `~/.local/share/fonts`) |
| `bat` / `fd` | Packaged as `batcat` / `fdfind`; aliased only when present | Native names, no alias needed |
| `du` | `--max-depth=1` | `-d 1` (BSD du rejects `--max-depth`) |
| `py` | `python` if present, else `python3` | `python3` (no system `python`) |
| CUDA / `LD_LIBRARY_PATH` | Injected when `/usr/local/cuda` exists | Skipped entirely |
| ROS2 / colcon aliases | `cw` `cs` `cb` `cbs` `sb` | Not defined (no ROS2 on macOS) |
| `ll` / `lt` | `eza -al --header` / `eza -l --sort=oldest --header` | Same |
| Default shell | Installs `zsh`, then `sudo chsh` | Bundled `/bin/zsh`; no brew zsh, no shell switch |
| C++ compiler | `build-essential` (gcc/g++) | Xcode CLT `clang` / `clang++` |
| C++ debugger | `gdb` | `lldb` (shipped with CLT; macOS has no gdb) |
| C++ build | `cmake` + `ninja-build` | `cmake` + `ninja` |
| Static analysis / formatting | `clangd`, `clang-format`, `clang-tidy` | `clangd` from CLT; `clang-format` installed standalone (not `llvm`) |
| Homebrew mirror | — | TUNA is used when `HOMEBREW_BOTTLE_DOMAIN` is unset, avoiding slow ghcr |

`ll` uses `--header` instead of `-h`: `eza`'s `-F` (`--classify[=WHEN]`) takes an optional argument, so `-alFh` parses as `-F h` and fails outright.

`apt install` runs package by package: a single missing package in the repo (e.g. `eza` on 22.04) makes the batched command fail, taking `cmake` and `clang` down with it.
