# lark-bot

飞书 / Lark 与本地编码/研究助手（Codex、omp 或 Claude Code）之间的常驻桥接器。

```text
飞书消息
  → lark-cli event consume im.message.receive_v1
  → 过滤 + message_id 去重
  → SQLite 任务队列
  → codex exec --json / omp --mode json / claude -p --output-format stream-json
  → 进度与最终结果回发飞书
```

## 依赖

- Python 3.10+（仅标准库）
- `lark-cli`（已登录，bot 身份 ready）
- `codex`、`omp` 或 `claude`（取决于 `AGENT_KIND`）

## 安装（可选）

`setup.sh` 不强制安装 lark-bot，会作为可选组件询问：

- stdin 是终端时逐项询问：已安装默认 `Y`，未安装默认 `N`；
- 非交互（脚本/CI，或 `--non-interactive`）默认**不安装**；
- 跳过只表示本次不安装/不更新，**不会卸载**已有安装。

```bash
# 仓库根目录执行（交互选择）
./setup.sh

# 非交互：显式指定
./setup.sh --with-codex-bot                     # 安装/更新 Codex 版
./setup.sh --with-codex-bot --with-omp-bot      # 两个都装（omp 需已有 ~/.omp）
./setup.sh --with-claude-bot                   # Claude 版（需已安装 claude）
./setup.sh --without-codex-bot                  # 明确跳过

# 或手动
mkdir -p ~/.codex/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.codex.example.env ~/.codex/lark-bot/config.env
ln -sfn "$PWD/.agents/lark-bot/bin/lark-bot" ~/.local/bin/codex-lark-bot
```

脚本可反复执行：每次重新询问，已有 `config.env`、`logs/`、`state.db`、会话数据不覆盖；
结束时打印各组件状态（已部署 / 已跳过）。Linux 写 systemd unit（只 `daemon-reload`，不自动 `enable`），
macOS 写 launchd LaunchAgent 并立即加载。

编辑 `~/.codex/lark-bot/config.env`，至少填写：

```bash
OWNER_ID=ou_xxx
WORKDIR=~/Workspace        # 换成你的工作区
```

然后：

```bash
codex-lark-bot check
codex-lark-bot start
codex-lark-bot status
codex-lark-bot logs
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
| `/paper-start` | 启用本实例的每日论文推送 |
| `/paper-stop` | 关闭本实例的每日论文推送 |
| `/paper-status` | 论文方向、今日状态、共享库与数据源 TODO |
| `/help` | 帮助 |

普通文本会作为任务交给当前助手。最终回复会引用原消息并以飞书 Markdown 渲染；
超过 3500 字节自动分片。

执行进度不会每条命令发一条消息，而是按批合并成“执行摘要”：

- 攒满 `PROGRESS_BATCH_ITEMS`（默认 10）条时发送；
- 距上一批超过 `PROGRESS_BATCH_SECONDS`（默认 60 秒）时发送；
- 任务结束时强制发送最后一批。

## Codex / omp / Claude 三后端

同一份 `bridge.py` 支持三种助手，通过 `AGENT_KIND` 切换：

| 配置 | Codex | omp | Claude Code |
|---|---|---|---|
| `AGENT_KIND` | `codex` | `omp` | `claude` |
| 可执行文件 | `CODEX_BIN=codex` | `OMP_BIN=/path/to/omp` 或 `AGENT_BIN` | `CLAUDE_BIN=claude` 或 `AGENT_BIN` |
| 续聊 | `codex exec resume <thread_id>` | `omp --mode json --resume <session_id>` | `claude -p --resume <session_id>` |
| 飞书身份 | `LARK_PROFILE=codex` | `LARK_PROFILE=omp` | `LARK_PROFILE=claude` |
| 网络 | `sandbox_workspace_write.network_access=true` | 内置 `web_search` / 联网工具 | 权限模式放行 WebSearch/WebFetch/Bash |
| 默认超时 | `TASK_TIMEOUT=7200` | 同左 | 同左 |

Claude 版使用 `--output-format stream-json --verbose` 解析过程与最终结果；
`CLAUDE_PERMISSION_MODE` 默认 `bypassPermissions`（非交互机器人需要联网、读写素材和笔记）。
`omp` 版本还支持旧配置键别名：`OMP_WORKDIR`、`OMP_BIN`、`LARK_BIN`。

各实例的部署目录：

| 可执行名 | 运行时目录 | launchd 标签 |
|---|---|---|
| `codex-lark-bot` | `~/.codex/lark-bot` | `com.home-clean.codex-lark-bot` |
| `omp-lark-bot` | `~/.omp/lark-bot` | `com.home-clean.omp-lark-bot` |
| `claude-lark-bot` | `~/.claude/lark-bot` | `com.home-clean.claude-lark-bot` |

`bin/lark-bot` 按**被调用的名字**推断实例默认值。这样才能在同一台机器上同时跑
codex-lark-bot、omp-lark-bot 和 claude-lark-bot 而不互相 `stop`。`LARK_BOT_HOME` / `LARK_BOT_SERVICE` /
`LARK_BOT_LAUNCHD_LABEL` 仍可显式覆盖。macOS 上 `setup.sh` 会把这些写进 LaunchAgent 的
`EnvironmentVariables`。

三个实例使用不同的 `LARK_BOT_HOME`、PID、数据库、launchd 标签，互不影响。前提是各自绑定
**不同的飞书 app**——事件总线按 appId 隔离（`~/.lark-cli/events/<appId>/`），同一个 app 会冲突。
Claude 实例需要先用 `lark-cli config init --new` 建一个独立 app，并把 `LARK_PROFILE` 指向它。

手动安装示例（omp）：

```bash
mkdir -p ~/.omp/lark-bot/{logs,memory}
install -m 600 .agents/lark-bot/config.omp.example.env ~/.omp/lark-bot/config.env
vim ~/.omp/lark-bot/config.env       # 填 OWNER_ID，确认 LARK_PROFILE=omp
ln -sfn "$PWD/.agents/lark-bot/bin/lark-bot" ~/.local/bin/omp-lark-bot
install -m 644 .agents/lark-bot/systemd/omp-lark-bot.service \
    ~/.config/systemd/user/omp-lark-bot.service
systemctl --user daemon-reload
omp-lark-bot check
systemctl --user enable --now omp-lark-bot
```

Claude 只需把上面的 `~/.omp` 换成 `~/.claude`、配置模板换成
`config.claude.example.env`、可执行名换成 `claude-lark-bot`。

## 配置要点

- `SANDBOX=workspace-write`：Codex 只能写工作区，默认推荐。
- `SANDBOX=danger-full-access` 必须同时设置 `ALLOW_DANGER=1`。
- `GROUP_MODE=off`：只处理主人私聊（默认）。
- `GROUP_MODE=mention`：群里必须 @机器人；需要填写 `BOT_OPEN_ID`。
- `SESSION_SCOPE=chat`：每个 chat 一个 thread；`thread` 则按话题隔离。
- `MAX_CONCURRENCY=1`：串行执行，避免多个助手进程争抢资源。
- `LARK_PROFILE`：lark-cli 身份 profile，按实例绑定：`codex-lark-bot` → `codex`，
  `omp-lark-bot` → `omp`，`claude-lark-bot` → `claude`。
- `AGENT_KIND=omp` 时忽略 `SANDBOX`，由 omp 自身的工具权限策略控制。
- `AGENT_KIND=claude` 时用 `CLAUDE_PERMISSION_MODE`（默认 `bypassPermissions`）。
- `TASK_TIMEOUT` 默认 7200 秒（2 小时），适合论文精读、批量对比等长任务。
- Codex 新会话和 resume 都会带 `sandbox_workspace_write.network_access=true`，
  并把 `PAPER_HOME` 加入可写目录；omp/Claude 本身可联网。

## 论文推送与精读

所有 lark-bot 实例共用同一套论文功能（`papers.py` + `PAPER_HOME`），通过飞书命令控制：

- `/paper-start`：启用**本实例**的每日推送；
- `/paper-stop`：关闭本实例的每日推送；
- `/paper-status`：查看关注方向、今日状态、共享库、文档 profile 和 S2/HF TODO。

每天 `PAPER_PUSH_TIME`（默认 08:30）从 arXiv 抓取 `topics.json` 里的分类/关键词，
按关键词、会议、开源、时效等规则打分，去重后交给助手挑选 **4～8 篇**高质量论文，
生成中文速递并推送。多个 bot 共用 `digest_runs` 表做原子抢占，**同一天只会有一个实例推送**，
不会重复轰炸。`PAPER_LOOKBACK_HOURS` 默认 96 小时，覆盖 arXiv 的公告延迟和周末。
arXiv export API 返回 429/5xx 时，抓取会自动退回 `/list/<category>/new` 和 `/abs/<id>`
页面解析，不依赖 API 配额。

默认布局：

```text
~/.agents/papers/papers.db      共享论文库、推送去重、笔记文档索引
~/.agents/papers/topics.json    关注方向（所有实例共享，可直接编辑）
~/.agents/papers/library/<id>/  元数据、PDF、fulltext.txt
~/.agents/papers/digests/       每日候选包与速递草稿
~/.agents/papers/notes/         精读笔记（上传飞书前的本地副本）
```

单篇能力：

- 发 arXiv 链接/ID：bridge 会预取元数据、arXiv HTML/PDF 全文和摘要，再交给助手；
- 说“帮我精读/做笔记”：使用 `paper-deep-note`，笔记自动创建为飞书文档；
- “对比这几篇/抽取 benchmark”：使用 `paper-benchmark`；
- “找这个方向的 gap”：使用 `research-gap-finder`。

技能说明在 `.agents/lark-bot/skills/`，三种后端都能通过绝对路径读取。
论文笔记创建飞书文档时需要 `--as user`，所以 `PAPER_DOC_PROFILE` 必须指向有已登录用户的
profile。推荐与实例 profile 保持一致：`claude-lark-bot` 使用 `claude`，
`omp-lark-bot` 使用 `omp`；`codex-lark-bot` 的 `codex` 目前没有用户登录，
可暂时借用 `omp`。文档默认放到主人的“我的空间”；
`PAPER_DOC_FOLDER` 可填云文档文件夹 token，也可填**知识库节点 token 或完整 wiki URL**。
每日速递会以 `YYYY-MM-DD 论文速递` 为标题，作为该节点的**子文档**创建，例如当前配置：

```bash
PAPER_DOC_FOLDER=P90xxxxxxxxxxxxxxxx
# 等价于 https://your-tenant.feishu.cn/wiki/P90xxxxxxxxxxxxxxxx
```

创建成功后，还会在父文档末尾追加一份按月份/日期组织的大纲：

```markdown
## 2026-11 论文速递

### 2026-11-03 论文速递

[📄 打开当日速递](https://your-tenant.feishu.cn/docx/xxxx)

- [ ] P1 · [ForceLDM: ...](https://arxiv.org/abs/2611.03294)：一句话结论
- [ ] P2 · [Rollout then Recycle: ...](https://arxiv.org/abs/2611.03168)：一句话结论
```

月份用 H2，每天用 H3；每天下面按推荐优先级（P1=精读、P2=速读、P3=暂缓）
列出飞书勾选框，每项包含论文链接和一句话结论。同一子文档 URL 或当天 H3
已存在时自动跳过，重试不会产生重复条目。

用户身份需要以下 scope（应用后台和用户授权都要有）：

```text
docx:document:create
docx:document:write_only
docx:document:readonly
wiki:node:retrieve
wiki:node:create
wiki:node:read
wiki:space:read
```

设备授权示例（把 `<profile>` 换成实例对应的 profile）：

```bash
lark-cli auth login --profile <profile> --scope "docx:document:create docx:document:write_only docx:document:readonly wiki:node:retrieve wiki:node:create wiki:node:read wiki:space:read" --no-wait --json
# 打开返回的 verification_url，确认后再执行：
lark-cli auth login --profile <profile> --device-code <device_code>
```

应用管理员还需要在开发者后台为对应 app 勾选同样的 scope 并发布版本；
错误信息里会给出带 clientID 的申请链接。
未授权时功能不会中断：会退回机器人身份创建文档，并授予当前用户 full_access；
若两个身份都没有权限，则只把笔记留在本地并在回复里给出路径。

S2 / HuggingFace 数据源尚未启用，记录见 [`docs/paper-sources.md`](docs/paper-sources.md)，
运行时也会显示在 `/paper-status` 里。

PDF 全文提取优先用 `pdftotext`；没有时退回 arXiv HTML，再退回摘要。建议安装：

```bash
brew install poppler          # macOS
sudo apt install poppler-utils  # Ubuntu
```

## 状态与日志

运行时文件全部在各自实例的 `LARK_BOT_HOME/`（Codex 默认 `~/.codex/lark-bot`：
config.env、state.db、logs/、memory/、bridge.pid）。共享论文数据在 `PAPER_HOME`。

## 开机自启

两个平台各用各的托管方式，`setup.sh` 按检测结果自动安装。

**Linux（systemd）** — unit 装到 `~/.config/systemd/user/codex-lark-bot.service`：

```bash
systemctl --user enable --now codex-lark-bot
systemctl --user status codex-lark-bot
```

**macOS（launchd）** — 每个实例一个 LaunchAgent，标签随可执行名走：
`com.home-clean.codex-lark-bot`（Codex）、`com.home-clean.omp-lark-bot`（omp）和
`com.home-clean.claude-lark-bot`（Claude），分别装到
`~/Library/LaunchAgents/<label>.plist`，登录即启动、崩溃后 10 秒内自动重启：

```bash
launchctl print gui/$UID/com.home-clean.omp-lark-bot        # 查看运行状态
launchctl kickstart -k gui/$UID/com.home-clean.omp-lark-bot # 重启
```

plist 里显式写入 `LARK_BOT_HOME`、`LARK_BOT_SERVICE` 和 `ProgramArguments` 指向的可执行名，
缺了 `LARK_BOT_SERVICE` 时 `stop` 会退化成 `codex-lark-bot` 而误停另一个实例。

LaunchAgent 的 PATH 里显式包含 `/opt/homebrew/bin` 和 `/usr/local/bin`：`lark-cli` 是
`#!/usr/bin/env node`，launchd 的默认 PATH 找不到 node 就会一直报
`env: node: No such file or directory`。

两种托管都就绪时，`codex-lark-bot stop` 会连同托管一起卸载（否则 KeepAlive 立刻把进程拉回来），
`codex-lark-bot restart` 则走托管的原生重启。不用托管时 `codex-lark-bot start/stop` 仍然可用
（Linux 优先 `setsid`，macOS 退回 `nohup`）。

## 事件总线冲突（多机部署必读）

飞书的长连接事件总线对同一个 app **全局只允许一个消费者**。如果同一个 app 在另一台机器上
已经跑着 `codex-lark-bot`，本机订阅会一直失败：

```text
[event] remote connection check: online_instance_cnt=1
another event bus is already connected to this app
```

关键点：`lark-cli event status` / `event stop` **只能看/停本机**的总线，对远端那台无效
（会显示 `not_running` / `no_bus`）。平台的 `online_instance_cnt` 是唯一的线索。

`codex-lark-bot check` 会做一次 3 秒的真实订阅试探，冲突时直接报
`event_bus: occupied_by_another_host` 并写明处理方式。两种解决办法：

1. 停掉另一台机器上的消费者（`codex-lark-bot stop`；systemd 用
   `systemctl --user stop codex-lark-bot`，launchd 用 `codex-lark-bot stop` 或
   `launchctl bootout gui/$UID/com.home-clean.codex-lark-bot`），
   然后在本机 `codex-lark-bot restart`；
2. 给本机一个独立的飞书 app（`lark-cli config init --new`），两台机器各用各的事件总线。

## 测试

```bash
cd .agents/lark-bot && python3 -m unittest discover -s tests -v
```

假集成测试使用 `tests/fakes/codex` 和 `tests/fakes/lark-cli`，不会访问真实飞书。

## 安全边界

- 只响应 `OWNER_ID`；群聊默认关闭。
- 忽略 `sender_type != user`，避免机器人自回复。
- 默认 `workspace-write`；高风险命令应在回复中先确认。
- 论文功能会联网抓取 arXiv，并可能把笔记创建到飞书云文档；`PAPER_DOC_PROFILE`
  应使用有用户授权的 profile。
- Claude 默认 `bypassPermissions`，只建议在主人私聊、受控机器上使用；如需更严格，
  可改为 `acceptEdits` 并自行补全工具白名单。
- `config.env` 0600，日志不记录 token；S2 key、HF token 同样不得写入日志或消息。
