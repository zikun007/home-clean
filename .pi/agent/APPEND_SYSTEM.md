# 终端工具偏好(用户自定义指令)

## 优先使用现代化的终端工具,替代传统命令

执行 shell 命令时,遵守以下替换规则。注意:本机实际命令名是 `fdfind` 和 `batcat`(Debian 打包名),zsh 交互 alias(`fd=fdfind`、`bat=batcat`)在非交互 shell 中不生效,不要依赖 alias——直接使用真实命令名。

| 传统命令 | 优先使用 | 说明 |
|---|---|---|
| `ls -la` | `eza -la --git --icons=auto` | 更清晰的列表,含 git 状态 |
| `ls` 树状查看 | `eza -T --git --icons=auto` | 替代 `tree` |
| `grep -rn` | `rg` | ripgrep,默认递归、忽略 .gitignore、更快 |
| `find` | `fdfind` | fd 的 Debian 打包名,默认递归、忽略隐藏/忽略文件,语法简单 |
| `cat` | `batcat` | bat 的 Debian 打包名,语法高亮,行号 |
| `cd` 多次跳转 | `z` (zoxide) | 已知目录智能跳转 |
| `top` | `btop` | 交互式资源监控(CPU/GPU/内存) |

## 使用约定

- **rg 用法要点**:`rg pattern -l` 列文件;`rg -t py pattern` 按类型过滤;`rg -F "literal"` 固定字符串;`rg --files | fzf` 快速定位文件。
- **fdfind 用法要点**:`fdfind pattern` 默认递归且忽略 .gitignore;`fdfind -e py` 按扩展名;`fdfind -H` 含隐藏文件。
- **不要把 eza/rg 的输出再用管道过滤一遍**再人工读,直接利用其原生选项。
- **fzf 组合**:`fzf` 用于交互式选择;脚本/非交互场景不要用 fzf(它会阻塞等待 TTY)。
- **jq 处理 JSON**:解析 API 响应、实验配置、JSONL 日志时用 `jq`,不要用 grep 脚本拼凑。
- **危险操作前确认**:`rm -rf`、`git reset --hard`、批量移动前,先列出受影响文件清点数量。
- **长任务用 tmux**:预计超过 2 分钟的命令(训练、大文件下载、索引构建)建议在 tmux 会话中运行,或用 `nohup ... &` 后台化,避免会话中断丢失进度。
- **查看文档/用法**:`tldr <command>` 通常比 `man` 更快得到可用示例。

## Python 环境管理(优先级从高到低)

1. **优先用 uv**:`uv` 是本机首选的 Python 环境与依赖管理器。
   - 新项目优先 `uv init` / `uv venv` + `uv add`;临时装包用 `uv pip install`;跑脚本优先 `uv run python ...`(自动同步环境);一次性脚本可用 `uv run --with numpy script.py`
   - uv 管理的虚拟环境在项目 `.venv/`,锁定依赖在 `uv.lock`,提交到 git
2. **其次用 conda**:仅当(1)项目已有 conda 环境(`environment.yml`,或 `~/miniconda3/envs/` 下已有对应环境),或(2)需要非 Python 系统依赖(CUDA、MKL 等)时使用。用 `conda activate <env>` 或绝对路径 `~/miniconda3/envs/<env>/bin/python`。
3. **禁止**:往 conda base 环境装包;同一项目里混用两套管理器(先 uv 又 conda 装依赖)。
4. **uv 尚未安装**(当前机器未装):需要时运行 `curl -LsSf https://astral.sh/uv/install.sh | sh` 安装到 `~/.local/bin`(免 root);装不装、何时装遵循用户当时的指示。
- Node.js 通过 nvm 管理(`/home/horizon/.config/nvm/`),当前默认 v24。
