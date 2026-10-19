# 训练记录（R1）

## 训练结果（R1，train.py 自动生成）

- 完成时间：2026-10-19 13:35:04 · 设备 CPU · 用时 32.2 分钟
- 起点权重 `weights/yolo26n-seg.pt` · epochs 30（实际 16）· imgsz 640 · batch 4 · workers 2 · patience 15 · seed 42
- 数据：`dataset/data.yaml`（train 292 / val 32，分割标签 `dataset/segments/`）
- 最优权重：`model/best.pt`（来自 `runs\segment\r1`，第 1 轮）

| val 指标（best.pt 重新验证） | 值 |
|---|---|
| 检测 mAP50 | 0.7598 |
| 检测 mAP50-95 | 0.6250 |
| 分割 mAP50 | 0.7020 |
| 分割 mAP50-95 | 0.4975 |

| 类别 | 检测 mAP50-95 | 分割 mAP50-95 |
|---|---|---|
| person | 0.7313 | 0.6133 |
| chair | 0.5096 | 0.3619 |
| dining table | 0.5311 | 0.2710 |
| couch | 0.7993 | 0.7783 |
| tv | 0.8395 | 0.7150 |
| laptop | 0.7826 | 0.6995 |
| cup | 0.5241 | 0.3169 |
| bottle | 0.1752 | 0.0985 |
| potted plant | 0.5662 | 0.3914 |
| bed | 0.7908 | 0.7297 |
