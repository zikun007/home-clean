---
name: exp-tracking
description: 设计和管理机器学习实验时使用。规范实验命名、超参记录、指标对比与结论沉淀,保证实验可追溯、可对比。
---

# 实验追踪规范

## 实验命名
`{日期}_{项目}_{实验组}_{变体}_{seed}`,例:`1025_retina_cls_baseline_cosine_lr0.1_seed42`

## 每次实验必须记录
1. **意图**:这次实验验证什么假设(一句话)
2. **改动**:相对 baseline 的唯一变量(一次只改一个)
3. **结果**:主指标 + 关键辅助指标(loss 曲线、PR 曲线)
4. **结论**:支持/推翻假设,下一步方向

## 对比实验设计
- 变量唯一:控制其他超参不变,否则结论不可信
- 多 seed:关键实验至少 3 个 seed,报告 mean ± std
- 统一评估:相同的验证集划分与指标计算代码,不允许多版本混用

## 结果沉淀
- 一次性结论 → 追加到项目 `EXPERIMENTS.md`,格式:
  ```
  ## exp-014 (2026-10-25) cos schedule vs constant
  - hypothesis: cosine 退火提升 final acc
  - result: 76.2±0.3 vs 75.1±0.4 (3 seeds)
  - conclusion: 采纳;lr warmup 5 epoch 配合
  ```
- 大方向结论 → 写入 memory MCP(knowledge graph),便于跨会话检索
