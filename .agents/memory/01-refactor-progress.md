# 01 · `.pi` → `.agents` 重构进度

## 2026-10-23

- 用户确认方案：Python 3、删除旧 `~/.pi`、仅保留 C++ 规范、其余按推荐项。
- 完成仓库迁移：`.pi` → `.agents`，删除 `.pi/agent`，迁移 C++ 规范。
- 完成 lark-bot 重写：
  - `bridge.py`：事件消费、过滤/去重、SQLite 队列、Codex 调用、进度、分片回复。
  - `bin/lark-bot`：run/start/stop/restart/status/check/logs。
  - `systemd/lark-bot.service`：已启用。
  - `tests/`：31 项测试通过。
- 运行时：`~/.agents/lark-bot/{config.env,state.db,logs,memory}`。
- 真实冒烟：`/help`、`/status`、`/pwd` 均正常；`/pwd` 回复当前目录。
- 已实现 `/pwd`、`/cd <path>`，命令只识别 `/xxx`；每个目录独立 thread。
- 进度消息按批合并（默认 10 条 / 60 秒），最终批随任务结束发送。
- 最终回复和命令回复均使用飞书 Markdown（`msg_type=post`）。
## 2026-10-23 · omp 双后端与 local-omp 部署

- `bridge.py` 支持 `AGENT_KIND=codex|omp`：
  - omp 新会话 `omp --mode json <prompt>`，续聊 `--resume <session_id>`。
  - 解析 `session.id` / `message_end` / `agent_end` / 工具执行事件。
  - 新增 `LARK_PROFILE`，lark-cli 自动带 `--profile`。
  - 兼容旧键 `OMP_WORKDIR`、`OMP_BIN`、`LARK_BIN`。
- local-omp 部署：
  - 配置：`~/.omp/lark-bot/config.env`（0600）
  - 后端：`omp`，profile：`omp-bot`，工作区：`/home/horizon/workspace/open_nav`
  - 服务：`omp-lark-bot.service`（替换旧 `omp-dispatch.sh`）
  - 旧配置备份：`config.env.bak-20261023-212106`
  - 验证：check ok、websocket connected、发送者 `local-omp`、`msg_type=post`
- 测试 31 项通过；local-codex `lark-bot` 已重启加载新代码。
- 用户已批准提交；待办：按需开启群聊/附件。

## 2026-10-24 · setup.sh 可选组件安装

- 新增参数：`--with-lark-bot` / `--without-lark-bot`、`--with-omp-bot` / `--without-omp-bot`、
  `--interactive` / `--non-interactive`（`--yes`/`-y`）、`--help`。
- 默认交互（仅 stdin 为 TTY）：已安装默认 Y，未安装默认 N；非交互默认不安装。
- 跳过不卸载；每次执行重新询问，配置/日志/状态/会话不覆盖；结束打印组件状态摘要。
- `install_lark_bot()` / `install_omp_bot()` 抽取为函数，第 4/4b 节按选择调用。
- 同步文档：`README.md`、`README_en.md`、`.agents/lark-bot/README.md`。

## 2026-10-27 · macOS 兼容性修复

平台检测缺失是根因：README 声称 `.zshrc` 用 `IS_MACOS`/`IS_LINUX` 切换，实际文件里根本
没有这两个变量。补上后逐项修掉硬编码 Linux 假设：

- `.zshrc`：开头按 `uname` 导出 `IS_MACOS`/`IS_LINUX`。
- PATH：Homebrew 提到最前（`/opt/homebrew` + `/usr/local`，覆盖 Intel），且只在 macOS 生效。
- CUDA / `LD_LIBRARY_PATH` 整块收进 `IS_LINUX`。
- `bat`/`fd`：按 `commands[batcat]`/`commands[fdfind]` 是否存在决定别名，macOS 用原生名。
- `du`：macOS 用 `-d 1`，Linux 用 `--max-depth=1`（BSD du 不认后者）。
- `py`：优先 `python`，回退 `python3`（macOS 无 `python`）。
- ROS2 / colcon 别名收进 `IS_LINUX`。
- `ll`/`lt`：`eza` 的 `-F` 是可选参数，`-alFh` 会被解析成 `-F h` 报错 →
  改 `ll='ls -al --header'`、`lt='ls -l --sort=oldest --header'`。这是跨平台通用 bug。
- `.config/vim/vimrc`：`set clipboard+=unnamedplus` 加 `has('clipboard')` 守卫。
- `setup.sh`：macOS 字体改为复制到 `~/Library/Fonts`（系统不扫描 `~/.local/share/fonts`）；
  brew 缺失时先试 `brew shellenv` 再从 `/opt/homebrew` `/usr/local` 探测；只装缺失 formula；
  默认 shell 切换用 `python3 realpath` 代替 BSD 无 `-f` 的 `readlink`，brew zsh 先补 `/etc/shells`。

验证：`bash -n setup.sh`、`zsh -n .zshrc` 通过；macOS 分支实测 `du`/`bat`/`fd`/`py`/`ll`/`lt`
全部可用；Linux 分支用覆盖 `uname` 函数模拟，得到 `du --max-depth=1`、`cb` 等结果正确；
`vimrc` 与 `tmux.conf` 加载无错；lark-bot 34 项测试通过。

## 2026-10-27 · 跨机迁移审计（沙箱实测）

用临时 `HOME=/tmp/sb/home` 真实跑了一遍 `setup.sh`，暴露并修掉 5 个会让新机器
"重建不出同样环境"的缺口：

1. **`.config/.clang-format` 从未部署**：第 1 节只软链 `.config` 下的目录，文件被漏掉。
   而且 clang-format 不读 XDG，只从源文件目录向上找 `.clang-format` → 改为软链到 `~/.clang-format`。
2. **`fzf` 从未安装**：`.zshrc` 的 `fzf` / `fzf-tab` 插件依赖它，但两个平台的清单里都没有。
3. **npm 全局 prefix 未配置**：`shellenv` 只设 `NPM_CONFIG_USERCONFIG`，新机器 `npm i -g`
   必然 EACCES（`/usr/local` 归 root）。改为首次运行时写入 `prefix=${HOME}/.local`，
   已有 npmrc 的话只追加、不覆盖 registry。
4. **`nvm` 默认版本写死 `v24.21.0`**：新机器版本不同就找不到 node。改为 `sort -V | tail -1`
   自动选最高版本（顺带发现字母序会错选 `v9.11.2`）。
5. **`alias ls='eza'` 无条件**：Ubuntu 22.04 官方源没有 eza，装不上时 `ls` 全坏。
   改为检测到 eza 才接管，否则回退系统 `ls -alFh` / `ls -ltrh`。

顺带修掉的两个真实 bug：

- `apt install -y $missing` 批量安装：22.04 缺 `eza` 会让整条命令失败，`cmake`/`clang` 也装不上 → 改为逐包安装并汇总失败项。
- `pkill -f 'brew install'` 会匹配自身命令行，导致 brew 反复重启（排查时踩到）。

## 2026-10-27 · C++ 工具链

- Linux：`build-essential`、`cmake`、`ninja-build`、`gdb`、`clang`、`clangd`、`clang-format`、
  `clang-tidy`、`ccache`、`pkg-config`、`lcov`。
- macOS：复用 CLT 的 `clang`/`clang++`/`clangd`/`lldb`/`make`，只补 `cmake`、`ninja`、
  `clang-format`、`ccache`、`pkg-config`。**不装 `llvm`**：整套 1.8GB，而 `clang-format`
  独立包只有 3.8MB（用户明确指出不该装 llvm，已卸载验证）。
- Homebrew 镜像：未设置 `HOMEBREW_BOTTLE_DOMAIN` 时用 TUNA。实测直连 ghcr 下载 20 秒 0 字节，
  镜像 4.6MB/s，cmake 从"几分钟无进展"变成 5 秒装完。

验证：`cmake -G Ninja` 真实编译并运行 C++17 程序成功；`clang-format --style=file` 读到仓库样式
（Tab 缩进）；沙箱 HOME 下新 shell 正确加载 `ZDOTDIR`/`IS_MACOS`/别名。
