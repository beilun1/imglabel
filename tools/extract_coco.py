# -*- coding: utf-8 -*-
"""
P1 数据获取 · 步骤 B：从 COCO 2017 val 中挑选室内场景候选图，补齐 laptop / cup / bed。

数据通道说明（如实记录，写入提交信息.txt）：
  任务书给的 cocodataset.org 在本机直连仅约 0.03 MB/s（val2017 共 815MB，需十余小时），不可行；
  故改走 HuggingFace 国内镜像 hf-mirror.com 上的 detection-datasets/coco：
  该数据集是 COCO 2017 的原样封装（原图 + bbox 标注，图片本身未经改动），val 分 2 个 parquet 分片。
  本脚本只取原图用于预标注，不导出标注（本项目标注由 YOLO-World / YOLO26n-seg 生成），
  标注仅用于按类别挑图。

parquet 结构（实测）：
  image_id:int64 | image:struct<bytes,path> | width | height
  objects:struct< bbox_id:list<int64>, category:list<int64>, bbox:list<[4]float>, area:list<float> >
  category 为 80 类的索引（0..79），名称表见 COCO80。

用法：
  python tools/extract_coco.py --parquet "D:\\imglabel_raw\\_download\\val-*.parquet" \
                               --raw D:\\imglabel_raw --per-class 90
"""
import argparse
import glob
import io
import json
import os
import sys
from collections import Counter

import pyarrow.parquet as pq
from PIL import Image

# ---- 十类词表（顺序即编号，红线，不得改） ----
CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]

# COCO 80 类名称表（索引顺序，来自数据集 ClassLabel.names）
COCO80 = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
          "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
          "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
          "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
          "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
          "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
          "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
          "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
          "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
          "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]

# 本次要补的三类（COCO 名称与任务书词表一致，无需别名）
COCO_NEEDED = {"laptop", "cup", "bed"}

# 室内强指示物
INDOOR_STRONG = {
    "chair", "couch", "dining table", "tv", "bed", "laptop", "cup", "bottle",
    "wine glass", "bowl", "fork", "knife", "spoon", "microwave", "oven", "toaster",
    "sink", "refrigerator", "clock", "vase", "book", "keyboard", "mouse", "remote",
    "potted plant", "teddy bear", "scissors", "toilet", "hair drier",
    "banana", "apple", "orange", "broccoli", "carrot", "sandwich", "pizza",
    "donut", "cake", "cell phone",
}
# 户外强指示物（严格判断：出现即视为户外，除非同时有家具类硬证据）
OUTDOOR_HARD = {
    "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "bench", "bird", "sheep", "cow", "horse", "elephant", "bear", "zebra", "giraffe",
    "traffic light", "fire hydrant", "stop sign", "parking meter",
    "skis", "snowboard", "surfboard", "kite", "sports ball",
}
# 家具类硬证据（与户外指示物冲突时以它为准：卧室/客厅照片里常有窗户看到车）
FURNITURE_HARD = {"bed", "couch", "dining table", "tv", "refrigerator", "oven", "microwave"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True, nargs="+")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--per-class", type=int, default=90, help="每类最多导出张数")
    args = ap.parse_args()

    files = []
    for p in args.parquet:
        files.extend(sorted(glob.glob(p)))
    if not files:
        print("未找到 parquet 文件"); return 1

    out_dir = os.path.join(args.raw, "candidates", "coco")
    os.makedirs(out_dir, exist_ok=True)

    metas, failed, skipped_outdoor = [], [], 0
    cls_cnt = Counter()
    seen = set()

    for fp in files:
        print(f"[读取] {os.path.basename(fp)}", flush=True)
        pf = pq.ParquetFile(fp)
        print(f"  行数 {pf.metadata.num_rows}", flush=True)
        got = 0
        for batch in pf.iter_batches(batch_size=32):
            for row in batch.to_pylist():
                iid = row["image_id"]
                objs = row.get("objects") or {}
                cats = objs.get("category") or []
                names = {COCO80[c] for c in cats if 0 <= c < len(COCO80)}
                hit = sorted(names & COCO_NEEDED)
                if not hit:
                    continue
                if not (names & INDOOR_STRONG):
                    continue
                if (names & OUTDOOR_HARD) and not (names & FURNITURE_HARD):
                    skipped_outdoor += 1
                    continue
                key = str(iid)
                if key in seen:
                    continue
                # 配额：全部命中类都已满则跳过
                if all(cls_cnt[c] >= args.per_class for c in hit):
                    continue
                seen.add(key)

                img = row.get("image") or {}
                raw = img.get("bytes") if isinstance(img, dict) else img
                if not raw:
                    failed.append((key, "无图片字节")); continue
                try:
                    im = Image.open(io.BytesIO(raw)); im.load()
                except Exception as e:
                    failed.append((key, f"解码失败:{e}")); continue

                fn = f"coco_{key}.jpg"
                with open(os.path.join(out_dir, fn), "wb") as fh:
                    fh.write(raw)
                for c in hit:
                    cls_cnt[c] += 1
                metas.append({"filename": fn, "image_id": key,
                              "source": "COCO 2017 val",
                              "width": im.width, "height": im.height,
                              "hint_classes": hit})
                got += 1
        print(f"  本分片导出 {got} 张，累计 {len(metas)}", flush=True)

    with open(os.path.join(out_dir, "_meta_coco.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "COCO 2017 val", "count": len(metas),
                   "meta": metas, "failed": failed}, f, ensure_ascii=False, indent=1)

    print(f"\n=== COCO 提取完成：{len(metas)} 张 -> {out_dir}")
    print("按类别计数:", dict(cls_cnt))
    print("因含户外指示物跳过:", skipped_outdoor)
    if failed:
        print("失败:", failed[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
