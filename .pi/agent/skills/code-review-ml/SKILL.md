---
name: code-review-ml
description: 审查机器学习/深度学习代码时使用。检查随机种子、设备管理、评估模式、实验可追溯性等 ML 特有问题。
---

# ML 代码审查清单

在常规代码审查(正确性、边界、可读性)之外,额外检查:

## 正确性
- [ ] 训练/验证切换:`model.eval()` / `model.train()` 配对,with torch.no_grad() 包裹验证
- [ ] `loss.backward()` 前清理梯度,或使用 optimizer.zero_grad(set_to_none=True)
- [ ] 验证集指标计算无数据泄漏(归一化参数只用训练集拟合)
- [ ] 推理/导出路径与训练路径一致(预处理、tokenizer、输入尺寸)

## 可复现性
- [ ] 设置了全局种子并记录(seed 写入 config/日志)
- [ ] DataLoader 有 generator 和 worker_init_fn
- [ ] 需要时启用确定性算法并记录性能代价

## 工程化
- [ ] 配置与代码分离:超参来自 config 文件/CLI,不硬编码
- [ ] checkpoint 保存/恢复完整:模型、optimizer、scheduler、step 数、rng 状态
- [ ] 实验记录:每次运行写入统一格式(时间、git commit、config hash、最终指标)
- [ ] .pth/.ckpt/数据集大文件在 .gitignore 中

## 资源管理
- [ ] 张量释放:长生命周期容器里不存带计算图的 loss
- [ ] 保存/加载指定 `map_location`,CPU 推理不会因 GPU 不可用而崩溃
- [ ] 数据迭代使用正确的设备转移时机(异步 prefetch,不要在循环中逐个 .to(device))
