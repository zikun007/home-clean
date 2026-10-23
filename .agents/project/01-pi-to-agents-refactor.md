# 01 · `.pi` → `.agents` 重构方案

## 执行结果（2026-10-23）

- 仓库 `.pi/` 已重命名为 `.agents/`，`.pi/agent/` 已清理。
- `.pi/agent/rules/cpp-code-rule.md` 已迁到 `.agents/rules/01-cpp-code-rule.md`。
- `.agents/lark-bot/` 已重写为 Python 3 + `codex exec` 版本。
- 运行时迁到 `~/.agents/lark-bot/`，旧 `~/.pi` 已移除。
- `lark-bot.service` 已启用并运行，飞书事件监听 `ready`、WebSocket `connected`。
- 单元/假集成测试 31 项通过。
- 真实链路冒烟：飞书 `/pwd` → Codex 执行 → local-codex 回复
  `当前目录：/home/horizon/workspace`。
- 新增原生命令 `/pwd`、`/cd <path>`：命令只识别 `/xxx`，中文不再触发；
  工作目录按 chat 持久化，每个目录使用独立 Codex thread。
- 进度消息改为按批合并（默认 10 条或 60 秒），任务结束时补发最后一批；
  不再每条命令发一条消息。
- 最终回复、命令回复均使用飞书 Markdown（`msg_type=post`）渲染。
- 同一 `bridge.py` 支持 `AGENT_KIND=codex|omp`；omp 使用
  `omp --mode json [--resume <session_id>]`，local-omp 部署于
  `~/.omp/lark-bot`（profile `omp-bot`，服务 `omp-lark-bot`）。

- 状态：已完成（2026-10-23）
- 日期：2026-10-23
- 建议分支：`refactor/agents`
- 原则：先迁移、后重写；旧运行时归档不直接删除；每一步可回滚

## 1. 目标

1. 仓库内 `.pi/` 重命名为 `.agents/`，保留 git 历史。
2. 删除 `.pi/agent/`（pi coding agent 专用配置），不迁移其运行时。
3. 保留并重建 `.agents/lark-bot/`，从 `pi` 驱动改为 `codex exec` 驱动。
4. 与根目录 `AGENTS.md` 约定对齐：`.agents/memory`、`.agents/project`、`.agents/rules`。
5. 家目录 `~/.pi` 运行时迁移到 `~/.agents/lark-bot`；旧目录归档，不直接删除。

## 2. 现状盘点

### 仓库内

```text
.pi/agent/        30 个受版本控制文件（agents/extensions/prompts/rules/skills/配置）
.pi/lark-bot/     config.example.sh + dispatch.sh
```

当前未提交内容：

- `.pi/agent/agents/{planner,reviewer,scout,worker}.md` 有模型名修改（将被删除，先备份 patch）。
- `.pi/lark-bot/dispatch.sh` 有未提交修改（旧 pi 版调度器，将被替换）。
- `.config/vim/vimrc`、`.config/zsh/.zshrc`、`.zshenv` 有无关修改，重构不触碰。
- 根目录 `AGENTS.md` 未跟踪，建议本次纳入版本管理。

### 家目录

```text
~/.pi/agent/      多为指向仓库 .pi/agent 的软链；含真实 sessions/、auth.json 等
~/.pi/lark-bot/   真实运行目录：config.sh、bot.log、events.ndjson、state.json、queue.txt
```

注意：只重命名仓库目录会让 `~/.pi/agent/*` 软链悬空，因此仓库和运行时必须一起迁移。

## 3. 目标结构

```text
.agents/
├── lark-bot/
│   ├── README.md
│   ├── config.example.env
│   ├── bridge.py                 # 单文件 Python 3，仅标准库
│   ├── bin/lark-bot              # start/stop/restart/status/logs/run
│   ├── systemd/lark-bot.service
│   └── tests/
│       ├── test_bridge.py
│       └── fakes/{lark-cli,codex}
├── memory/                       # 开发进度记忆（按 AGENTS.md 编号）
│   └── 01-refactor-progress.md
├── project/                      # 已审批方案
│   └── 01-lark-bot-refactor.md
└── rules/
    └── 01-cpp-code-rule.md       # 从 .pi/agent/rules 迁移

AGENTS.md                         # 纳入版本管理

~/.agents/lark-bot/               # 运行时，不入库
├── config.env                    # 0600
├── state.db                      # SQLite：去重/会话/任务
├── logs/
└── memory/                       # 按 chat 的长期记忆
```

代码与运行时分离：仓库保存源码；`~/.agents/lark-bot` 只放配置、状态、日志和记忆。

## 4. 迁移步骤

### Phase 0：冻结与备份

```bash
# 停止旧机器人（若在运行）
pkill -f 'lark-bot/dispatch.sh' 2>/dev/null || true

# 保存当前未提交差异
git diff > /tmp/home-clean-before-agents-$(date +%Y%m%d-%H%M%S).patch

# 归档运行时（不删除）
mv ~/.pi ~/.pi.bak-$(date +%Y%m%d-%H%M%S)

# 新建分支
git switch -c refactor/agents
```

### Phase 1：仓库重命名与清理

```bash
git mv .pi .agents
git rm -r .agents/agent
```

在删除 `.agents/agent` 前先回收两类资产：

- `rules/cpp-code-rule.md` → `.agents/rules/01-cpp-code-rule.md`（建议保留）。
- `skills/{code-review-ml,exp-tracking,ml-debug}` → 默认随目录删除，git 历史可找回；如需保留，移到 `.agents/skills/`。

旧 lark-bot：

```bash
git rm .agents/lark-bot/dispatch.sh .agents/lark-bot/config.example.sh
```

然后新增 `.agents/lark-bot/` 新实现。旧版仍可从 git 历史取回。

同步修改：

- `.gitignore`：改为 `.agents/lark-bot/{config.env,state.db*,logs/,memory/}` 等。
- `setup.sh`：删除第 4 节 `.pi/agent` 软链逻辑；改为创建 `~/.agents/lark-bot` 运行时、复制配置模板、安装 `~/.local/bin/lark-bot`。
- `README.md` / `README_en.md`：补充 `.agents` 与 lark-bot 使用说明。
- 根 `AGENTS.md`：`git add AGENTS.md`。

### Phase 2：实现 Codex 版 lark-bot

见第 5 节。

### Phase 3：运行时迁移

```bash
mkdir -p ~/.agents/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.example.env ~/.agents/lark-bot/config.env
# 按旧 config.sh 填写 OWNER_ID，再编辑 WORKDIR / SANDBOX / MODEL
```

- 旧 `config.sh` 中的 `OWNER_ID` 复制到新 `config.env`。
- 旧 `bot.log` / `events.ndjson` 保留在 `~/.pi.bak-*` 中，不导入新库，避免事件重放。
- 旧 `sessions/` 是 pi 格式，不迁移；Codex 会话在 `~/.codex/sessions`，由 bridge 记录 thread_id。

### Phase 4：测试与切换

先在 `~/.agents/lark-bot` 用 `run --once`/fake 测试，再启动真实监听；通过后合并 `refactor/agents`。

## 5. lark-bot 设计

### 5.1 进程模型

```text
lark-cli event consume im.message.receive_v1 --as bot
        │ NDJSON
        ▼
EventConsumer（监督/重连/ready marker）
        ▼
Filter + Dedupe（SQLite message_id）
        ▼
SQLite 任务队列（默认全局串行，可配并发）
        ▼
CodexRunner（codex exec --json，按会话 resume）
        ├── 进度事件 → 飞书
        └── 最终文本 → 分片回复
```

- 常驻 supervisor：consumer 退出后指数退避重连；认证错误通知主人一次。
- 默认 `MAX_CONCURRENCY=1`，保证同一时间只有一个 Codex 任务；可按 chat 串行扩展。
- 所有状态落 SQLite（WAL），重启后去重、会话、队列不丢。

### 5.2 消息过滤

- 默认只处理 `chat_type=p2p` 且 `sender_id=OWNER_ID`。
- 忽略 `sender_type != user`，防止机器人自回复死循环。
- 用 `message_id` 去重（不用 `event_id`），保留 7 天。
- 忽略启动前 60 秒以前的历史消息，避免事件重放。
- 群聊默认关闭；开启后要求 `@机器人` + `ALLOWED_CHATS` 白名单，且默认只响应主人。
- 支持从 `thread_id` / `root_id` 取会话键，话题内可独立续聊。

### 5.3 会话与记忆

- `sessions` 表：`session_key`、`thread_id`、`cwd`、`model`、`updated_at`。
- 首条消息：`codex exec`，从 `thread.started` 捕获 thread_id。
- 后续消息：`codex exec resume <thread_id>`；resume 失败则自动新开并告知。
- `/new` 清除该 chat 的 thread_id，但保留 `~/.agents/lark-bot/memory/`。
- 长期记忆按 chat 存 `memory/<chat_id>.md`，由 Codex 按需读写；不整段注入，避免上下文膨胀。

### 5.4 Codex 调用

```bash
codex exec --json --skip-git-repo-check \
  -C "$WORKDIR" \
  -s "$SANDBOX" \
  -c approval_policy=never \
  -c model="$CODEX_MODEL" \
  -o "$last_message_file" \
  --add-dir "$BOT_HOME" \
  "$prompt"
```

续聊：

```bash
codex exec resume "$THREAD_ID" --json ... "$prompt"
```

- 默认 `SANDBOX=workspace-write`，不读终端审批，避免无头模式卡死。
- `danger-full-access` 需显式配置 `ALLOW_DANGER=1`，启动时打印警告。
- 任务超时默认 1800 秒；超时/`/stop` 用进程组 SIGTERM，宽限后 SIGKILL。
- 飞书子进程单独设置 `NO_PROXY`（feishu.cn 等）；Codex 继承正常代理环境。

### 5.5 进度与回复

从 `codex exec --json` 事件映射：

| Codex 事件 | 飞书进度 |
|---|---|
| `item.completed` + `command_execution` | `✅ 执行：<command>`（非 0 退出码标记 ⚠️） |
| `item.completed` + `file_change` | `📝 修改：<paths>` |
| `item.completed` + `mcp_tool_call` | `🔌 调用：<server>.<tool>` |

进度事件不会逐条发送：默认攒够 `PROGRESS_BATCH_ITEMS=10` 条或
`PROGRESS_BATCH_SECONDS=60` 秒发送一条“执行摘要”，任务结束时强制补发。
| `item.completed` + `agent_message` | 记录为最终候选 |
| `turn.completed` | 结束并发送最终答复 |

- 进度消息节流 2 秒，相同内容去重。
- 最终答复优先用 `-o` 文件，其次取最后一条 `agent_message`。
- 用 `im +messages-reply` 回复原消息；失败回退 `+messages-send`。
- 长文本按 UTF-8 字节安全切分（≤3500 字节），加 `[1/N]` 前缀。
- 429/5xx 指数退避重试。

### 5.6 飞书内命令

| 命令 | 行为 |
|---|---|
| `/help` | 命令说明 |
| `/status` | 当前任务、队列长度、线程、运行时长 |
| `/new` | 清除当前 chat 的会话 |
| `/stop` | 终止当前任务 |
| 普通文本 | 入队执行 |

### 5.7 配置模板

```bash
# ~/.agents/lark-bot/config.env  (chmod 600)
OWNER_ID=ou_xxxxxxxxxxxxxxxx
WORKDIR=/home/horizon/workspace
CODEX_MODEL=HORIZON-DeepSeek
SANDBOX=workspace-write
MAX_CONCURRENCY=1
TASK_TIMEOUT=1800
GROUP_MODE=owner          # off | owner | mention | all
ALLOWED_CHATS=
PROGRESS=1
PROGRESS_INTERVAL=2
REPLY_FORMAT=markdown
ALLOW_DANGER=0
```

### 5.8 服务与运维

- `bin/lark-bot start|stop|restart|status|logs|run`。
- 优先 `systemd --user`（`Restart=always`）；不可用时 `setsid` + PID 文件兜底。
- 日志 `~/.agents/lark-bot/logs/bridge.log`，10MB × 5 轮转。
- 启动时检查：`lark-cli` / `codex` / 配置 / 目录权限 / 事件订阅连通性。

## 6. 测试与验收

### 自动化

- 单元测试：UTF-8 分片、消息过滤、去重、Codex 事件解析、配置解析。
- 假集成：fake `lark-cli` 发一条事件，fake `codex` 返回 NDJSON；断言只发一次回复、任务状态正确。
- 不依赖真实飞书，避免测试刷屏。

### 真实冒烟

1. 主人私聊发 `/status`，收到状态。
2. 发 `ping`，收到回复。
3. 发 `运行 echo hi`，先收到进度，再收到结果。
4. 同一事件重放，不重复执行。
5. 重启 bridge，继续对话仍能 resume 同一 thread。
6. 发 `/new` 后 thread 重置。
7. 长回复 >3500 字节，正确分片。
8. `/stop` 能终止长任务。
9. 群聊 @ 机器人（若开启）正常；机器人不回复自己。

### 验收命令

```bash
git grep -nE '(^|[^A-Za-z0-9_])\.pi/' -- ':!docs' ':!.gitignore' || true
python3 -m unittest discover -s .agents/lark-bot/tests -v
~/.local/bin/lark-bot status
```

## 7. 风险与回滚

| 风险 | 处理 |
|---|---|
| 事件重复/重放 | SQLite `message_id` 去重 + 时间窗过滤 |
| 机器人自回复循环 | 过滤 `sender_type != user`，只响应主人 |
| Codex thread 失效 | 捕获 resume 失败，自动新开并通知 |
| 长任务阻塞队列 | 超时 + `/stop` + 可配并发 |
| 误删/误改工作区 | 默认 workspace-write；任务前 git 快照（可选 Phase 5）；`/undo` |
| 群成员提示注入 | 默认群聊关闭；开启后白名单 + 默认只响应主人 |
| 密钥/日志泄露 | `config.env` 0600，日志脱敏，不入库 |
| `~/.pi` 迁移影响 pi CLI | 预期停用；归档目录可完整回滚 |
| systemd 不可用 | `setsid` 兜底 |

回滚：

```bash
# 代码
git switch main   # 或重构前 commit
# 运行时
mv ~/.agents/lark-bot ~/.agents/lark-bot.failed
mv ~/.pi.bak-<timestamp> ~/.pi
```

## 8. 待确认项（默认值）

1. **实现语言**：Python 3 单文件（默认）还是 Bash。Python 更适合 JSON 流、SQLite、并发和测试。
2. **旧运行时**：归档 `~/.pi`（默认）还是直接删除。
3. **`.pi/agent` 资产**：迁移 `cpp-code-rule.md`（默认）；3 个 skills 默认不迁移。
4. **群聊**：默认关闭，先跑通私聊；需要时再开 `GROUP_MODE=mention`。
5. **服务方式**：systemd user + setsid 兜底（默认）。
