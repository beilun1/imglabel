# P5 导出报告（export_dataset.py 自动生成，勿手改）

生成时间：2026-10-27 13:13:19 · 随机种子 42 · 用时 10.2s

## 总览

| 项目 | 数值 |
|---|---|
| 导出图片 | 324 |
| 有效实例（已排除 mark=deleted） | 2331 |
| 排除的 deleted 实例 | 206 |
| 排除的零面积实例（面积 < 1px²） | 2：coco_10707.jpg imvdm6w7bps4m（bottle，created）；coco_116208.jpg imvdo7i9adaxv（cup，created） |
| 空图（无有效实例） | 1：coco_14831.jpg |
| train / val | 292 / 32 |
| 人工过审图 / 预标草稿图 | 236 / 88 |
| 实例来源 seg / det 框占位 / 人工新建 | 550 / 226 / 73 |
| 含孔洞（分割 txt 只导外轮廓） | 246 |

## 每类数量

| 编号 | 类别 | 实例数 | 含该类图片数 | train 实例 | val 实例 |
|---|---|---|---|---|---|
| 0 | person | 457 | 154 | 405 | 52 |
| 1 | chair | 456 | 159 | 413 | 43 |
| 2 | dining table | 199 | 157 | 182 | 17 |
| 3 | couch | 99 | 80 | 93 | 6 |
| 4 | tv | 130 | 98 | 116 | 14 |
| 5 | laptop | 112 | 84 | 98 | 14 |
| 6 | cup | 451 | 140 | 381 | 70 |
| 7 | bottle | 245 | 99 | 179 | 66 |
| 8 | potted plant | 108 | 55 | 85 | 23 |
| 9 | bed | 74 | 66 | 68 | 6 |
| | 合计 | 2331 | | 2020 | 311 |

## 格式说明

- `labels/*.txt` YOLO 检测：`cls xc yc w h`，框 = 掩码顶点外接矩形，归一化 [0,1]、6 位小数
- `segments/*.txt` YOLO 分割：`cls x1 y1 ...`，掩码外轮廓（孔洞不表达），归一化 [0,1]
- `semantic/*.png` 8 位灰度：像素值 = cls + 1（背景 0），实例按数组顺序以非零环绕规则填充（与画布一致），后画覆盖先画
- `train.txt` / `val.txt`：`./images/<图>.jpg`（相对 dataset 根），9:1 随机划分
- 类别编号 = 十类词表顺序：0 person · 1 chair · 2 dining table · 3 couch · 4 tv · 5 laptop · 6 cup · 7 bottle · 8 potted plant · 9 bed
