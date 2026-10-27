# lark-bot

飞书 / Lark 与本地编码助手（Codex 或 omp）之间的常驻桥接器。

```text
飞书消息
  → lark-cli event consume im.message.receive_v1
  → 过滤 + message_id 去重
  → SQLite 任务队列
  → codex exec --json 或 omp --mode json（按会话 resume）
  → 进度与最终结果回发飞书
```

## 依赖

- Python 3.10+（仅标准库）
- `lark-cli`（已登录，bot 身份 ready）
- `codex` 或 `omp`（取决于 `AGENT_KIND`）

## 安装（可选）

`setup.sh` 不强制安装 lark-bot，会作为可选组件询问：

- stdin 是终端时逐项询问：已安装默认 `Y`，未安装默认 `N`；
- 非交互（脚本/CI，或 `--non-interactive`）默认**不安装**；
- 跳过只表示本次不安装/不更新，**不会卸载**已有安装。

```bash
# 仓库根目录执行（交互选择）
./setup.sh

# 非交互：显式指定
./setup.sh --with-lark-bot                     # 安装/更新 Codex 版
./setup.sh --with-lark-bot --with-omp-bot      # 两个都装（omp 需已有 ~/.omp）
./setup.sh --without-lark-bot                  # 明确跳过

# 或手动
mkdir -p ~/.agents/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.example.env ~/.agents/lark-bot/config.env
ln -sfn "$PWD/.agents/lark-bot/bin/lark-bot" ~/.local/bin/lark-bot
```

脚本可反复执行：每次重新询问，已有 `config.env`、`logs/`、`state.db`、会话数据不覆盖；
结束时打印各组件状态（已部署 / 已跳过）。Linux 写 systemd unit（只 `daemon-reload`，不自动 `enable`），
macOS 写 launchd LaunchAgent 并立即加载。

编辑 `~/.agents/lark-bot/config.env`，至少填写：

```bash
OWNER_ID=ou_xxx
WORKDIR=~/Workspace        # 换成你的工作区
```

然后：

```bash
lark-bot check
lark-bot start
lark-bot status
lark-bot logs
```

## 飞书命令

命令只识别 `/` 开头的英文形式，中文名称不会触发命令。

| 命令 | 作用 |
|---|---|
| `/pwd` | 显示当前工作目录 |
| `/cd <path>` | 切换工作目录；每个目录使用独立会话 |
| `/status` | 当前目录、任务、队列、会话线程 |
| `/new` | 清除当前目录的会话 |
| `/stop` | 终止当前任务 |
| `/help` | 帮助 |

普通文本会作为任务交给当前助手。最终回复会引用原消息并以飞书 Markdown 渲染；
超过 3500 字节自动分片。

执行进度不会每条命令发一条消息，而是按批合并成“执行摘要”：

- 攒满 `PROGRESS_BATCH_ITEMS`（默认 10）条时发送；
- 距上一批超过 `PROGRESS_BATCH_SECONDS`（默认 60 秒）时发送；
- 任务结束时强制发送最后一批。

## Codex / omp 双后端

同一份 `bridge.py` 支持两种助手，通过 `AGENT_KIND` 切换：

| 配置 | Codex | omp |
|---|---|---|
| `AGENT_KIND` | `codex` | `omp` |
| 可执行文件 | `CODEX_BIN=codex` | `OMP_BIN=/path/to/omp` 或 `AGENT_BIN` |
| 续聊 | `codex exec resume <thread_id>` | `omp --mode json --resume <session_id>` |
| 飞书身份 | 默认 profile | `LARK_PROFILE=omp-bot` |

`omp` 版本还支持旧配置键别名：`OMP_WORKDIR`、`OMP_BIN`、`LARK_BIN`。
部署到 `~/.omp/lark-bot`（local-omp），`setup.sh` 检测到 `~/.omp` 时才会询问，也可直接
`./setup.sh --with-omp-bot` 安装；手动方式：

```bash
mkdir -p ~/.omp/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.omp.example.env ~/.omp/lark-bot/config.env
vim ~/.omp/lark-bot/config.env       # 填 OWNER_ID，确认 LARK_PROFILE=omp-bot
ln -sfn "$PWD/.agents/lark-bot/bin/lark-bot" ~/.local/bin/omp-lark-bot
install -m 644 .agents/lark-bot/systemd/omp-lark-bot.service \
    ~/.config/systemd/user/omp-lark-bot.service
systemctl --user daemon-reload
LARK_BOT_HOME=~/.omp/lark-bot LARK_BOT_SERVICE=omp-lark-bot omp-lark-bot check
systemctl --user enable --now omp-lark-bot
```

两个实例使用不同的 `LARK_BOT_HOME`、PID、数据库和 systemd 服务，互不影响。

## 配置要点

- `SANDBOX=workspace-write`：Codex 只能写工作区，默认推荐。
- `SANDBOX=danger-full-access` 必须同时设置 `ALLOW_DANGER=1`。
- `GROUP_MODE=off`：只处理主人私聊（默认）。
- `GROUP_MODE=mention`：群里必须 @机器人；需要填写 `BOT_OPEN_ID`。
- `SESSION_SCOPE=chat`：每个 chat 一个 thread；`thread` 则按话题隔离。
- `MAX_CONCURRENCY=1`：串行执行，避免多个助手进程争抢资源。
- `LARK_PROFILE`：lark-cli 身份 profile；local-omp 使用 `omp-bot`。
- `AGENT_KIND=omp` 时忽略 `SANDBOX`，由 omp 自身的工具权限策略控制。

## 状态与日志

运行时文件全部在 `~/.agents/lark-bot/`：

```text
config.env     配置（0600）
state.db       去重、会话、任务队列
logs/          bridge.log / daemon.log
memory/        按 chat 的长期记忆
bridge.pid     后台进程 PID
```

## 开机自启

两个平台各用各的托管方式，`setup.sh` 按检测结果自动安装。

**Linux（systemd）** — unit 装到 `~/.config/systemd/user/lark-bot.service`：

```bash
systemctl --user enable --now lark-bot
systemctl --user status lark-bot
```

**macOS（launchd）** — LaunchAgent 装到 `~/Library/LaunchAgents/com.home-clean.lark-bot.plist`，
登录即启动，崩溃后 10 秒内自动重启：

```bash
launchctl print gui/$UID/com.home-clean.lark-bot     # 查看运行状态
launchctl kickstart -k gui/$UID/com.home-clean.lark-bot   # 重启
```

LaunchAgent 的 PATH 里显式包含 `/opt/homebrew/bin` 和 `/usr/local/bin`：`lark-cli` 是
`#!/usr/bin/env node`，launchd 的默认 PATH 找不到 node 就会一直报
`env: node: No such file or directory`。

两种托管都就绪时，`lark-bot stop` 会连同托管一起卸载（否则 KeepAlive 立刻把进程拉回来），
`lark-bot restart` 则走托管的原生重启。不用托管时 `lark-bot start/stop` 仍然可用
（Linux 优先 `setsid`，macOS 退回 `nohup`）。

## 事件总线冲突（多机部署必读）

飞书的长连接事件总线对同一个 app **全局只允许一个消费者**。如果同一个 app 在另一台机器上
已经跑着 `lark-bot`，本机订阅会一直失败：

```text
[event] remote connection check: online_instance_cnt=1
another event bus is already connected to this app
```

关键点：`lark-cli event status` / `event stop` **只能看/停本机**的总线，对远端那台无效
（会显示 `not_running` / `no_bus`）。平台的 `online_instance_cnt` 是唯一的线索。

`lark-bot check` 会做一次 3 秒的真实订阅试探，冲突时直接报
`event_bus: occupied_by_another_host` 并写明处理方式。两种解决办法：

1. 停掉另一台机器上的消费者（`lark-bot stop`；systemd 用 `systemctl --user stop lark-bot`，
   launchd 用 `lark-bot stop` 或 `launchctl bootout gui/$UID/com.home-clean.lark-bot`），
   然后在本机 `lark-bot restart`；
2. 给本机一个独立的飞书 app（`lark-cli config init --new`），两台机器各用各的事件总线。

## 测试

```bash
python3 -m unittest discover -s .agents/lark-bot/tests -v
```

假集成测试使用 `tests/fakes/codex` 和 `tests/fakes/lark-cli`，不会访问真实飞书。

## 安全边界

- 只响应 `OWNER_ID`；群聊默认关闭。
- 忽略 `sender_type != user`，避免机器人自回复。
- 默认 `workspace-write`；高风险命令应在回复中先确认。
- `config.env` 0600，日志不记录 token。
