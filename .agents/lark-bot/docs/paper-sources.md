# 论文数据源记录（S2 / HuggingFace TODO）

当前默认只使用 **arXiv API**。以下两个源已预留接口和配置项，等主人补充访问方式后再启用。

## Semantic Scholar（S2）

状态：**TODO，未启用**

- 已探测：无 API key 直接调用返回 `429 Too Many Requests`。
- 计划用途：
  - 引用数、 influential citation 作为质量信号；
  - 会议/期刊元数据交叉验证；
  - 相关论文推荐（论文库扩展）。
- 预留配置：
  ```bash
  PAPER_S2_API_KEY=
  ```
- 需要主人补充：API key（或代理/镜像地址）。
- 接入点：`papers.py` 的 `PaperService.score()` 质量信号；新增
  `S2Fetcher` 并在 `fetch_candidates()` 中合并。
- 注意：S2 有速率限制，批量查询要缓存；不要把 key 写入日志或飞书消息。

## HuggingFace Daily Papers

状态：**TODO，未启用**

- 已探测：本机直连 `huggingface.co` 被拒绝（connection refused）；企业代理
  `<proxy-host>:<port>` 可能可用，但尚未验证。
- 计划用途：
  - 社区热度（upvotes）作为质量/时效信号；
  - 补足 arXiv 分类抓取漏掉的热门论文。
- 预留配置：
  ```bash
  PAPER_HF_ENABLED=0
  # 需要时再补：
  # PAPER_HF_API=https://huggingface.co/api/daily_papers
  # HTTPS_PROXY=http://<proxy-host>:<port>
  ```
- 需要主人补充：是否允许走代理、是否有 HF token、镜像地址。
- 注意：HF 论文去重必须用 arXiv ID，避免与 arXiv 源重复推送。

## 记录位置

运行时共享库：`$PAPER_HOME/papers.db` 的 `source_todo` 表。
机器人发送 `/paper-status` 时会显示这两个待补充项。

本文档也会在生成论文笔记/速递时作为飞书文档上传。若飞书提示缺少
`docx:document:create`，先补授权（应用后台 + 用户设备授权都要）：

```bash
lark-cli auth login --profile omp --scope "docx:document:create" --no-wait --json
# 打开 verification_url 确认后：
lark-cli auth login --profile omp --device-code <device_code>
```

应用侧还需要在开发者后台勾选 `docx:document` 与 `docx:document:create`；
未授权时笔记只保存在本地，并在回复里给出路径。
