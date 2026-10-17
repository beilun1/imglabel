# -*- coding: utf-8 -*-
"""
P1 · 第 2 轮复核辅助：对筛选后的剩余候选做"可能该删"的风险打分。

为什么需要：第一轮按文件名删除是盲删。第二轮的复核重点是**画质与画面质量**
（模糊、过曝过暗、目标极小、画面杂乱），这些只能看图判断，本脚本只把"最可能出问题"
的图排到前面，降低过图成本，不代替人眼。

打分依据（纯启发式，写在报告里可追溯）：
  1. 分辨率低 —— 长边 < 480px，放大后模糊，不适合作为标注/训练图
  2. 文件体积小 —— KB/像素 偏低，通常是模糊或大面积纯色
  3. 目标占比小 —— 用数据集原始 bbox（VOC xml / COCO bbox）算目标面积占比，占比过小说明
     主体在图里只有一小块，标注价值低
  4. 对比度/清晰度低 —— 灰度标准差低（发灰）、拉普拉斯方差低（模糊）

用法：
  python tools/score_candidates.py --limit 333
产出：
  data/review/review_round2.csv / .md   按风险分从高到低排序的待复核清单
"""
import argparse
import csv
import io
import json
import os
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np
from PIL import Image, ImageFilter

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REV = os.path.join(PROJ, "data", "review")
IMG = os.path.join(PROJ, "data", "images")
RAW = "D:/imglabel_raw"
VOC_TAR = os.path.join(RAW, "_download", "VOCtrainval_11-May-2012.tar")

SIZES = ["person", "chair", "dining table", "couch", "tv",
         "laptop", "cup", "bottle", "potted plant", "bed"]
VOC_ALIAS = {"diningtable": "dining table", "pottedplant": "potted plant",
             "tvmonitor": "tv", "sofa": "couch"}


def load_target_ratio_voc():
    """从 tar 里解析每张图的目标框面积占比（取图中最大目标的面积/图面积）"""
    out = {}
    if not os.path.exists(VOC_TAR):
        return out
    with tarfile.open(VOC_TAR, "r") as tf:
        for m in tf:
            if "/Annotations/" not in m.name or not m.name.endswith(".xml"):
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            try:
                root = ET.fromstring(f.read())
            except ET.ParseError:
                continue
            iid = "voc_" + os.path.splitext(os.path.basename(m.name))[0] + ".jpg"
            size = root.find("size")
            if size is None:
                continue
            try:
                W = float(size.findtext("width")); H = float(size.findtext("height"))
            except (TypeError, ValueError):
                continue
            best = 0.0
            for o in root.findall("object"):
                b = o.find("bndbox")
                if b is None:
                    continue
                try:
                    x1, y1, x2, y2 = (float(b.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
                except (TypeError, ValueError):
                    continue
                best = max(best, max(0.0, (x2 - x1)) * max(0.0, (y2 - y1)) / (W * H + 1e-6))
            out[iid] = best
    return out


def load_target_ratio_coco():
    """COCO parquet 里已算好每框 area，取最大目标占比"""
    import glob
    import pyarrow.parquet as pq
    out = {}
    for fp in sorted(glob.glob(os.path.join(RAW, "_download", "val-*.parquet"))):
        pf = pq.ParquetFile(fp)
        for batch in pf.iter_batches(batch_size=32):
            for row in batch.to_pylist():
                objs = row.get("objects") or {}
                areas = objs.get("area") or []
                W, H = row.get("width") or 1, row.get("height") or 1
                if areas:
                    out[f"coco_{row['image_id']}.jpg"] = max(areas) / (float(W) * H)
    return out


def image_stats(path):
    with Image.open(path) as im:
        im = im.convert("L")
        a = np.asarray(im, dtype=np.float32)
    # 对比度：灰度标准差
    contrast = float(a.std())
    # 清晰度：拉普拉斯方差（越小越糊）
    lap = np.asarray(im.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    sharp = float(lap.var())
    return contrast, sharp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=333)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(REV, "candidates.csv"), encoding="utf-8-sig")))
    deleted = set()
    p = os.path.join(REV, "keep_del_user_round1.txt")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            ln = ln.split("#")[0].strip()
            if ln:
                deleted.add(ln)
    rows = [r for r in rows if r["文件名"] not in deleted]
    print(f"剩余候选 {len(rows)} 张")

    print("解析 VOC 目标框 ...")
    ratio = {}
    ratio.update(load_target_ratio_voc())
    print(f"  VOC {len(ratio)} 条")
    try:
        r2 = load_target_ratio_coco()
        ratio.update(r2)
        print(f"  COCO {len(r2)} 条")
    except Exception as e:
        print("  COCO 目标框解析失败（跳过该项）:", e)

    out_rows = []
    for r in rows:
        fn = r["文件名"]
        path = os.path.join(IMG, fn)
        w, h = int(r["宽"]), int(r["高"])
        kb = os.path.getsize(path) / 1024.0
        px = w * h
        bpp = kb * 1024 / px          # 每像素字节，越低越可能糊
        contrast, sharp = image_stats(path)
        tr = ratio.get(fn, None)

        flags, score = [], 0.0
        if max(w, h) < 480:
            flags.append("分辨率低"); score += 3
        if bpp < 0.10:
            flags.append("体积/像素偏低"); score += 1.5
        elif bpp < 0.14:
            score += 0.6
        if sharp < 60:
            flags.append("边缘弱(疑糊)"); score += 2
        elif sharp < 120:
            score += 0.8
        if contrast < 38:
            flags.append("发灰/低对比"); score += 1.2
        if tr is not None and tr < 0.02:
            flags.append("目标极小(<2%)"); score += 2.5
        elif tr is not None and tr < 0.05:
            flags.append("目标偏小(<5%)"); score += 1.0

        out_rows.append({
            "文件名": fn, "来源": r["来源"], "宽": w, "高": h,
            "类别提示": r["类别提示"],
            "最大目标占比": "" if tr is None else round(tr, 4),
            "KB": round(kb, 1), "KB/千像素": round(bpp * 1000, 2),
            "对比度": round(contrast, 1), "清晰度": round(sharp, 1),
            "风险分": round(score, 1), "疑点": "、".join(flags),
        })

    out_rows.sort(key=lambda x: -x["风险分"])
    out_rows = out_rows[:args.limit]

    csv_path = os.path.join(REV, "review_round2.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # 分档统计
    bins = Counter()
    for x in out_rows:
        s = x["风险分"]
        bins["≥5 高疑点" if s >= 5 else "3~5 中疑点" if s >= 3 else "1~3 低疑点" if s >= 1 else "0 无明显疑点"] += 1
    md = os.path.join(REV, "review_round2.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 第 2 轮复核清单（按疑点程度排序）\n\n")
        f.write(f"剩余候选 **{len(rows)}** 张，下表按风险分从高到低排列。\n\n")
        f.write("> 风险分是**启发式提示**（分辨率 / 体积比 / 清晰度 / 对比度 / 目标占比），"
                "不是判决。分数高只代表「更可能有问题」，仍需你看图确认。\n\n")
        f.write("| 分档 | 张数 |\n|---|---|\n")
        for k in ("≥5 高疑点", "3~5 中疑点", "1~3 低疑点", "0 无明显疑点"):
            f.write(f"| {k} | {bins[k]} |\n")
        f.write("\n## 高疑点明细（风险分 ≥3）\n\n")
        f.write("| 文件名 | 类别 | 尺寸 | 最大目标占比 | 清晰度 | 对比度 | 分 | 疑点 |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for x in out_rows:
            if x["风险分"] >= 3:
                f.write(f"| {x['文件名']} | {x['类别提示']} | {x['宽']}×{x['高']} | "
                        f"{x['最大目标占比']} | {x['清晰度']} | {x['对比度']} | {x['风险分']} | {x['疑点']} |\n")

    print(f"\n分档: {dict(bins)}")
    print(f"清单: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
