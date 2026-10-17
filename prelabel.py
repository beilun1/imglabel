# -*- coding: utf-8 -*-
"""预标注模块占位（P3 实现：YOLO-World / YOLO26n-seg 生成标注草稿）

P2 阶段不接入预标注，仅保证提交包目录结构完整。
P3 时在此实现：调用官方预训练权重生成草稿 → 写入 data/annotations/{图名}.json。
"""

CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]  # 顺序即编号，不得改


def prelabel_image(image_path, classes=None):
    """对单张图片生成预标注草稿，返回实例列表。

    草稿实例结构（与画布 JSON 一致）：
    [{"id": "...", "cls": 0, "mark": "unchanged",
      "mask": {"type": "polygon", "points": [[x, y], ...]}}, ...]
    """
    raise NotImplementedError("P3 阶段实现：调用 YOLO-World 与 YOLO26n-seg 生成标注草稿")
