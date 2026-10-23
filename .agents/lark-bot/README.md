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

## 安装

```bash
# 仓库根目录执行
./setup.sh

# 或手动
mkdir -p ~/.agents/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.example.env ~/.agents/lark-bot/config.env
ln -sfn "$PWD/.agents/lark-bot/bin/lark-bot" ~/.local/bin/lark-bot
```

编辑 `~/.agents/lark-bot/config.env`，至少填写：

```bash
OWNER_ID=ou_xxx
WORKDIR=/home/horizon/workspace
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
部署到 `~/.omp/lark-bot`（local-omp）：

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

## systemd

`setup.sh` 会把 unit 安装到 `~/.config/systemd/user/lark-bot.service`。启用：

```bash
systemctl --user enable --now lark-bot
systemctl --user status lark-bot
```

如果不使用 systemd，`lark-bot start/stop` 使用 `setsid` 后台运行。

## 测试

```bash
python3 -m unittest discover -s .agents/lark-bot/tests -v
```

假集成测试使用 `tests/fakes/codex`，不会访问真实飞书。

## 安全边界

- 只响应 `OWNER_ID`；群聊默认关闭。
- 忽略 `sender_type != user`，避免机器人自回复。
- 默认 `workspace-write`；高风险命令应在回复中先确认。
- `config.env` 0600，日志不记录 token。
