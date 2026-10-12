---
name: ml-debug
description: 调试机器学习训练脚本时使用。排查 loss NaN/不收敛、梯度异常、CUDA OOM、数据泄漏、随机性不可复现等问题。
---

# ML 训练调试流程

按以下顺序系统排查,不要跳步:

## 1. 数据检查(最先做)
- Shape / dtype / 值域:`x.shape, x.dtype, x.min(), x.max(), x.mean()`
- NaN/Inf 来源定位:在 DataLoader 输出处先检查,再查增强/归一化代码
- 数据泄漏:确认 train/val split 无重叠、无时序穿越、GroupShuffle 用于需按实体划分的数据

## 2. 模型与前向
- 参数初始化是否合理(全零初始化、embedding padding 未冻结)
- `model.eval()` 与 `model.train()` 状态:Dropout/BN 在验证时必须 eval
- 用 `torch.autograd.set_detect_anomaly(True)` 或逐层 hook 定位 NaN 产生的层

## 3. 训练循环
- 梯度:`torch.nn.utils.clip_grad_norm_` 上限、检查 `grad is None`(未参与 loss 的参数)
- 学习率:先用 1/10 的小 batch 过拟合单个样本验证学习能力
- AMP 混合精度下使用 `torch.isnan` 检查、GradScaler 状态

## 4. CUDA OOM
- `torch.cuda.memory_summary()`、`del` + `torch.cuda.empty_cache()` 只在调参间隙用
- 优先方案:梯度累积 > 更省显存的实现(如 flash-attention、checkpointing)> 减小 batch
- 排查隐藏引用:`nvidia-smi` 与进程内张量数、循环中累积 loss(未 `.item()` 导致计算图滞留)

## 5. 可复现性
```python
import torch, numpy as np, random
seed = 42
random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
# DataLoader 用 generator + worker_init_fn;注意 torch.use_deterministic_algorithms
```

## 6. 性能剖析
- 先 `torch.profiler` 找热点,再优化;DataLoader 通常用 `pin_memory=True, num_workers=4~8, persistent_workers=True`
- GPU 利用率低 → IO/预处理瓶颈;GPU 高但慢 → kernel 效率问题
