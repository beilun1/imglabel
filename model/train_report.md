# P5 训练记录

## 训练结果（train.py 自动生成）

- 完成时间：2026-10-18 21:54:17 · 设备 CPU · 用时 47.2 分钟
- 起点权重 `weights/yolo26n-seg.pt` · epochs 30（实际 16）· imgsz 640 · batch 4 · workers 2 · patience 15 · seed 42
- 数据：`dataset/data.yaml`（train 294 / val 33，分割标签 `dataset/segments/`）
- 最优权重：`model/best.pt`（来自 `runs\segment\p5`，第 1 轮）

| val 指标（best.pt 重新验证） | 值 |
|---|---|
| 检测 mAP50 | 0.7619 |
| 检测 mAP50-95 | 0.6150 |
| 分割 mAP50 | 0.6930 |
| 分割 mAP50-95 | 0.4435 |

| 类别 | 检测 mAP50-95 | 分割 mAP50-95 |
|---|---|---|
| person | 0.7371 | 0.6037 |
| chair | 0.6571 | 0.3846 |
| dining table | 0.5666 | 0.2193 |
| couch | 0.8095 | 0.6402 |
| tv | 0.8091 | 0.7467 |
| laptop | 0.7713 | 0.6218 |
| cup | 0.5713 | 0.4406 |
| bottle | 0.3732 | 0.2481 |
| potted plant | 0.2023 | 0.1496 |
| bed | 0.6519 | 0.3803 |
