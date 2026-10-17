# Agent 工作规范

## Vibe Coding 项目开发工作流

### Agent 开发要求

- 项目必须采用 **git 管理**，commit 提交遵循**统一的提交规范**(Conventional Commits)。
- **提交 git commit 之前必须先获得用户审批**，不得擅自提交或推送。

### memory 存储(全栈开发工程师角色)

主文件夹:`<workspace>/.agents/memory`,负责数据持久化和项目进度跟踪:

- 根据 `<workspace>/.agents/project` 中规划的方案选择工具进行开发;
- 跟踪各模块开发进度,记录 bug、调试结果和当前进展;
- memory 数据过长时,及时清理最旧的数据,保持上下文精炼。

### project 架构(项目经理角色)

主文件夹:`<workspace>/.agents/project`,负责整体设计、规划和方案确定:

- 根据用户需求,制定合理且可执行的项目方案;
- 有层次化地组织方案与文档,与开发工程师(memory 侧)对接需求及解决方案;
- **只有经过审核确认之后的方案**才能存入 `<workspace>/.agents/project`;
- 待确认的方案先在 `<workspace>/docs` 目录下创建和修改,审核通过后再归档。

### 工作流总览

```text
用户需求
   │
   ▼
[项目经理] 制定方案 ──▶ <workspace>/docs (待审核)
   │                        │ 用户审核确认
   ▼                        ▼
[项目经理] 归档方案 ──▶ <workspace>/.agents/project
   │
   ▼
[开发工程师] 执行开发 ──▶ <workspace>/.agents/memory (进度/bug/调试记录)
   │
   ▼
git 提交 ──▶ 用户审批 ──▶ commit (统一规范)
```

## 终端工具偏好

本机已安装现代终端工具(eza/fd/bat/rg/zoxide/fzf/btop/jq/tldr),优先使用它们替代传统命令。注意:本机实际命令名是 `fdfind` 和 `batcat`(Debian 打包名),非交互 shell 中无 zsh alias,不要依赖 alias。

- 非交互场景不要用 fzf(会阻塞等待 TTY);长任务(训练、下载、索引构建)用 tmux 或 `nohup ... &` 后台化。
- 危险操作(`rm -rf`、`git reset --hard`、批量移动)前,先列出受影响文件清点数量。