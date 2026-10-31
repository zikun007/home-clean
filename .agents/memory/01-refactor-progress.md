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

## 2026-10-28 · 移除 brew zsh（macOS 用系统自带）

用户要求：macOS 自带 `/bin/zsh`，不再安装 brew zsh，也不做默认 Shell 切换。

- `setup.sh` macOS formula 清单去掉 `zsh`（Linux 清单保留，Ubuntu 默认是 bash）。
- 第 7 节改为：macOS 只检测 `$SHELL` 是否 `/bin/zsh` 并打印提示，绝不 `chsh`；
  Linux 仍是 `sudo chsh`（已是 zsh 时也打印 OK）。
- 顺带修掉原代码的 bash 花括号 bug：`"...为 $SHELL，macOS..."` 会把全角逗号吞进变量名，
  输出成乱码 → 改 `${SHELL}`。
- 根因补充：两套 zsh（5.9 与 5.9.2）共用 `ZSH_COMPDUMP` 和 p10k 的 `.zwc`，
  导致 `zrecompile: zcompile:99: zwc file has wrong version`。

已执行：`brew uninstall zsh`（1,613 文件 / 16.2MB）。`/etc/shells` 未含 brew 路径，
`UserShell` 一直是 `/bin/zsh`，无需回滚。卸载后 fpath 中 homebrew 条目为 0，
zwc 头部版本为 `5.9`，fzf-tab 的 Tab 补全（mock fzf 捕获到 1 次调用、0 报错）正常。

验证：`bash -n setup.sh`；用 stub `brew`/`sudo` 跑真实函数分支——macOS 两分支只打提示、
Linux 两分支分别执行/跳过 chsh；formula 安装列表为
`tmux vim git wget fzf eza fd bat ripgrep btop fontconfig cmake ninja clang-format ccache pkg-config`（无 zsh）。

## 2026-10-28 · macOS 上双飞书实例（local-omp + local-codex）

用户反馈 Ubuntu 上两个智能体能同时用，macOS 上不行。实查结论：app 一直在，坏的是配置与包装脚本。

- 真实映射：`cli_aa5f5b5787f9dc01` = **local-omp**；`cli_aa59f1470ab8dc18` = **local-codex**。
  事件总线按 appId 隔离（`~/.lark-cli/events/<appId>/`），本就互不冲突。
- `~/.omp/lark-bot/config.env` 是 Linux 遗留：`WORKDIR=/home/horizon/workspace`、
  `AGENT_BIN=/home/horizon/.local/bin/omp`、`OWNER_ID=ou_xxx…` 占位、`LARK_PROFILE=omp-bot`（不存在）。
  lark-cli 的 profile 原名就是 appId，已 `profile rename cli_aa5f5b5787f9dc01 omp-bot` 对齐。
- **包装脚本 bug（关键）**：`bin/lark-bot` 的 `BOT_HOME`/`SERVICE_NAME` 默认值写死，
  `omp-lark-bot status/stop/restart` 全落到 local-codex 的 home 与 launchd 标签上，
  `stop` 会把另一个实例停掉。改为按 `$0` 名字推断（`omp-lark-bot` → `~/.omp/lark-bot` +
  `com.home-clean.omp-lark-bot`）。
- launchd 模板新增 `__BIN__` / `__SERVICE__` 占位符，`install_launchagent` 增加第 3 个参数；
  plist 现在显式写入 `LARK_BOT_SERVICE`，否则 stop 仍会退化。
- 修掉 `install_launchagent` 里两处 `$var（` 被 bash 吞字符的老问题（全角括号前必须 `${var}`）。

验证：`omp-lark-bot check` 全绿（workdir/owner/profile 正确，`event_bus: available`）；
直接跑 bridge 的 `_build_args` + 输出解析，omp 返回 `rc=0`、捕获 thread、解析出答复「好」；
两个 LaunchAgent 同时 running（74490 / 74552），各自 consuming 自己的 app；
重启其一不影响另一个；`omp-lark-bot status` 在干净环境下返回正确的 pid；
34 项单测通过；`bash -n` 与 `plutil -lint` 通过。

## 2026-10-31 · 本机 zsh 切换到仓库配置

- `setup.sh` 已在本机执行，旧配置备份在 `~/.dotfiles_backup/20261031_191513/`。
- 回归：新 `.zshrc` 丢了旧配置里的 `/opt/homebrew/sbin`、`~/.pixi/bin`、`~/.lmstudio/bin`、
  VS Code `code`、OrbStack `init.zsh`。已补回：目录存在才追加到 PATH 末尾，OrbStack init 在
  oh-my-zsh（compinit）之前 source；同时预留 `/Library/TeX/texbin`（tmux 等非登录 shell 用）。
- 验证方法：`env -i` + python `pty.fork` 起交互 shell。直接 `zsh -i -c` 无 TTY 会报
  `can't change option: zle` 和 gitstatus 初始化失败，属于测试假象。
- 未迁移的旧 `.zshrc` 内容：`proxy_on` 旧地址 127.0.0.1:7890、uv/pixi 补全、`CPATH`/`LIBRARY_PATH`、
  `zoxide --cmd cd`、`cat→bat`/`find→fd` 别名，待用户决定。

### LaTeX：OrbStack 容器 → 本机 MacTeX

- 删除 OrbStack 容器 `utex2`、镜像 `latex:u22`、卷 `Latex`；项目复制到 `~/Workspace/Latex`，
  按文档类分为 `PPT/`（beamer）、`Book/`（book）、`Article/`（article / ctexart / gmcmthesis）。
- **`brew install --cask mactex-no-gui` 在 macOS 14 上不可用**：Homebrew 已不为 macOS 14 构建 bottle，
  cask 依赖的 Homebrew ghostscript 会拉 38 个依赖全部源码编译（卡在 raw.githubusercontent.com）。
  改为 `sudo installer -pkg … -applyChoiceChangesXML`：装 `org.tug.mactex.texlive2026` +
  pkg 自带 `ghostscript10.07.0`，关 `gui2026`。同理 setup.sh 中 `fontconfig` 也没装上（无 `fc-list`）。
- XeTeX 在 macOS 走 CoreText，只认系统登记的字体（TeX Live 自带的 Fandol 也找不到）。
  已复制到 `~/Library/Fonts`：Fandol 6 款（来自 TeX Live）、`KaiTi.ttf`/`FangSong.ttf`（来自 kdocker）。
  注意 `SimKai.ttf` 的家族名是 `KaiTi_GB2312`，不是 `KaiTi`。
- tcolorbox 6.9 不再接受 `xcolor={dvipsnames}`：LatexBeamer 改为 `\documentclass[8pt,xcolor={dvipsnames}]{beamer}`。
- 5 个项目 `latexmk -xelatex` 均通过（22 / 34 / 16 / 32 / 79 页）。

### `/etc` 恢复出厂

- `/etc/zprofile` 曾被改成"设环境变量 + `source $ZDOTDIR/.zshrc`"，且删掉了 `path_helper`：
  导致登录 shell 里 `.zshrc` 执行两次、`/usr/local/bin`（MacTeX 的 `gs`）和 `/etc/paths.d` 不生效。
  `/etc/zshrc` 注释掉了 HISTFILE 三行。两者已从 `/System/Library/Templates/Data/private/etc/` 恢复，
  原文件备份在 `~/.dotfiles_backup/20261031_191513/etc/`。bash/csh 相关文件均为出厂版本，保留
  （root 的 `/bin/sh` 实为 bash，依赖 `/etc/profile`）。
- `zprofile` 中有用的变量迁入仓库 `.zshenv`：`XDG_STATE_HOME`、`PIP_CONFIG_FILE`、`IPYTHONDIR`、`CONAN_HOME`。
- Homebrew 镜像：实测 TUNA/USTC/阿里/腾讯 API 均 5~6MB/s（带宽上限），官方源不通；
  PyPI 包下载 TUNA 5.1、USTC 4.4、腾讯 1.8、阿里 1.3 MB/s。用户选定 TUNA（与 setup.sh、uv.toml 一致）。
- 登录 shell 启动约 0.13s。

### `~` 隐藏目录整理

- 删除：`~/.local/bin/omp.old`、`~/.config/fonts`（与 `~/Library/Fonts` 逐字节相同）、`~/.config/iterm2`、
  fish 全部数据、`~/.xmake`、空的 `~/.SuiteSparse`、`~/package*.json`；`brew uninstall fish xmake`。
- `.zshenv` 新增重定向并按"配置 / 缓存 / 状态"分组：`npm_config_cache`、`MPLCONFIGDIR`、
  `TLDR_CACHE_DIR`、`GRAPHBLAS_CACHE_PATH`、`ROS_HOME`；对应目录已移入 `~/.cache`、`~/.config`、`~/.local/state`。
- tldr（C 客户端 1.6.1）：`TLDR_CACHE_DIR` 是父目录，客户端自己拼 `/.tldrc`，所以缓存在 `~/.cache/.tldrc`。
  缓存是整个 tldr 仓库的 main.zip（149M，40 种语言），从 GitHub 下载；缓存不存在时会强制下载，国内会卡住。
- 不挪：`.cargo`/`.rustup`（用户要求）、`.docker`（OrbStack 管理）、`.codex`（launchd 启动的 lark-bot 不读 .zshenv）、
  `.lmstudio`（需在 App 内改）、其余为路径写死的工具目录。
- `~/.viminfo` 来自 `sudo vim` 编辑 `/etc`：sudo 清掉 `VIMINIT` 但保留 `HOME`。改系统文件请用 `sudo -e`。
