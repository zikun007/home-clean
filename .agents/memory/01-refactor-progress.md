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
