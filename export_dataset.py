# -*- coding: utf-8 -*-
"""P5 三格式导出：data/annotations/*.json + data/curated/images/ → dataset/

  dataset/images/<图>.jpg       原图副本
  dataset/labels/<图>.txt       YOLO txt（检测）：cls xc yc w h，框 = 掩码外接矩形
  dataset/segments/<图>.txt     实例掩码（YOLO seg）：cls x1 y1 x2 y2 ...，只导外轮廓
  dataset/semantic/<图>.png     语义 PNG（8 位灰度）：像素值 = cls + 1，背景 0
  dataset/train.txt / val.txt   9:1 随机划分（行 = ./images/<图>.jpg，相对 dataset 根）
  dataset/data.yaml             ultralytics 数据配置（nc=10，names=十类词表）
  dataset/export_report.md      导出统计

规则：跳过 mark=="deleted"；空图导出空 txt + 全 0 PNG；坐标归一化后 clip 到 [0,1]、6 位小数。
前置：修正记录一致性校验不通过则拒绝导出。

用法：python export_dataset.py [--out dataset] [--seed 42]
"""
import os
import sys
import json
import time
import shutil
import random
import argparse
from collections import Counter

import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "tools"))
from prelabel import CLASSES, IMG_DIR, ANN_DIR  # noqa: E402
from records_stats import load_records, load_annotations, check_consistency  # noqa: E402

VAL_RATIO = 0.1
SUBDIRS = ("images", "labels", "segments", "semantic")
MIN_AREA = 1.0   # px²；画笔在图像边缘单击会被钳成一条零宽线，框宽/高为 0，不是有效目标


def signed_area(p):
    if len(p) < 3:
        return 0.0
    a = np.asarray(p, dtype=float)
    x, y = a[:, 0], a[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def outer_ring(points):
    """去掉零宽桥缝进来的孔洞，返回外轮廓。

    画布/预标注把孔洞反向绕行，经桥点 A 缝进外环：... A, H.., H, A ...（A、H 各出现两次）。
    两个重复顶点之间的子环若面积与整体反号（孔洞）或为 0（桥的来回），就剪掉；
    同号子环是贴点相连的另一块（8 连通），保留。
    """
    pts = [tuple(p) for p in points]
    pts = [p for i, p in enumerate(pts) if p != pts[i - 1]] if len(pts) > 1 else pts
    sign = 1.0 if signed_area(pts) >= 0 else -1.0
    changed = True
    while changed:
        changed = False
        seen = {}
        for j, p in enumerate(pts):
            i = seen.get(p)
            if i is not None and signed_area(pts[i:j]) * sign <= 0:
                pts = pts[:i] + pts[j:]
                changed = True
                break
            seen[p] = j
    return [list(p) for p in pts]


def fill_nonzero(points, w, h):
    """多边形 → (h, w) 布尔掩码，非零环绕规则（与画布 fill 一致），按像素中心采样。"""
    m = np.zeros((h, w), dtype=bool)
    P = np.asarray(points, dtype=float)
    if len(P) < 3:
        return m
    Q = np.roll(P, -1, axis=0)
    r0 = max(0, int(np.floor(P[:, 1].min())))
    r1 = min(h, int(np.ceil(P[:, 1].max())) + 1)
    if r0 >= r1:
        return m
    cy = np.arange(r0, r1)[:, None] + 0.5
    y0, y1, x0, x1 = P[:, 1], Q[:, 1], P[:, 0], Q[:, 0]
    up = (y0 <= cy) & (y1 > cy)
    down = (y0 > cy) & (y1 <= cy)
    dy = np.where(y1 != y0, y1 - y0, 1.0)
    xs = x0 + (cy - y0) * (x1 - x0) / dy
    for k, row in enumerate(range(r0, r1)):
        sel = up[k] | down[k]
        if not sel.any():
            continue
        x = xs[k][sel]
        d = np.where(up[k][sel], 1, -1)
        order = np.argsort(x, kind="stable")
        x, wind = x[order], np.cumsum(d[order])
        for a, b, wn in zip(x[:-1], x[1:], wind[:-1]):
            if wn != 0:
                c0 = max(0, int(np.ceil(a - 0.5)))
                c1 = min(w, int(np.ceil(b - 0.5)))
                if c1 > c0:
                    m[row, c0:c1] = True
    return m


def bbox(points):
    a = np.asarray(points, dtype=float)
    return a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()


def fmt(v):
    return f"{min(max(v, 0.0), 1.0):.6f}"


def is_degenerate(points):
    return abs(signed_area(outer_ring(points))) < MIN_AREA


def export_one(doc, out, skipped):
    name, w, h = doc["image"], int(doc["width"]), int(doc["height"])
    stem = os.path.splitext(name)[0]
    shutil.copyfile(os.path.join(IMG_DIR, name), os.path.join(out, "images", name))

    det_lines, seg_lines, kept = [], [], []
    sem = np.zeros((h, w), dtype=np.uint8)
    for inst in doc["instances"]:
        if inst.get("mark") == "deleted":
            continue
        cls, pts = int(inst["cls"]), inst["mask"]["points"]
        ring = outer_ring(pts)
        if abs(signed_area(ring)) < MIN_AREA:
            skipped.append((name, inst["id"], CLASSES[cls], inst.get("mark")))
            continue
        x0, y0, x1, y1 = bbox(pts)
        det_lines.append(" ".join([str(cls), fmt((x0 + x1) / 2 / w), fmt((y0 + y1) / 2 / h),
                                   fmt((x1 - x0) / w), fmt((y1 - y0) / h)]))
        seg_lines.append(" ".join([str(cls)] + [f"{fmt(x / w)} {fmt(y / h)}" for x, y in ring]))
        sem[fill_nonzero(pts, w, h)] = cls + 1      # 数组顺序绘制，后画覆盖先画
        kept.append({"cls": cls, "src": inst.get("src"), "auto": bool(inst.get("auto")),
                     "ring_pts": len(ring), "pts": len(pts), "area": abs(signed_area(ring))})

    for sub, lines in (("labels", det_lines), ("segments", seg_lines)):
        with open(os.path.join(out, sub, stem + ".txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(l + "\n" for l in lines))
    Image.fromarray(sem, mode="L").save(os.path.join(out, "semantic", stem + ".png"))
    return kept


def split(names, seed):
    names = sorted(names)
    random.Random(seed).shuffle(names)
    n_val = round(len(names) * VAL_RATIO)
    return sorted(names[n_val:]), sorted(names[:n_val])


def write_report(out, seed, docs, per_img, skipped, train, val, elapsed):
    cls_inst = Counter(k["cls"] for ks in per_img.values() for k in ks)
    cls_img = Counter(c for ks in per_img.values() for c in {k["cls"] for k in ks})
    split_inst = {s: Counter(k["cls"] for n in names for k in per_img[n]) for s, names in (("train", train), ("val", val))}
    empty = sorted(n for n, ks in per_img.items() if not ks)
    total = sum(cls_inst.values())
    src = Counter(k["src"] or "manual" for ks in per_img.values() for k in ks)
    reviewed = sum(1 for d in docs.values() if d.get("reviewed"))
    deleted = sum(1 for d in docs.values() for i in d["instances"] if i.get("mark") == "deleted")
    holes = sum(1 for ks in per_img.values() for k in ks if k["ring_pts"] < k["pts"])

    L = ["# P5 导出报告（export_dataset.py 自动生成，勿手改）", "",
         f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')} · 随机种子 {seed} · 用时 {elapsed:.1f}s", "",
         "## 总览", "",
         "| 项目 | 数值 |", "|---|---|",
         f"| 导出图片 | {len(per_img)} |",
         f"| 有效实例（已排除 mark=deleted） | {total} |",
         f"| 排除的 deleted 实例 | {deleted} |",
         f"| 排除的零面积实例（面积 < {MIN_AREA:g}px²） | {len(skipped)}：" +
         ("；".join(f"{n} {i}（{c}，{m}）" for n, i, c, m in skipped) or "无") + " |",
         f"| 空图（无有效实例） | {len(empty)}：{', '.join(empty) or '无'} |",
         f"| train / val | {len(train)} / {len(val)} |",
         f"| 人工过审图 / 预标草稿图 | {reviewed} / {len(per_img) - reviewed} |",
         f"| 实例来源 seg / det 框占位 / 人工新建 | {src.get('seg', 0)} / {src.get('det', 0)} / {src.get('manual', 0)} |",
         f"| 含孔洞（分割 txt 只导外轮廓） | {holes} |", "",
         "## 每类数量", "",
         "| 编号 | 类别 | 实例数 | 含该类图片数 | train 实例 | val 实例 |", "|---|---|---|---|---|---|"]
    for c, n in enumerate(CLASSES):
        L.append(f"| {c} | {n} | {cls_inst[c]} | {cls_img[c]} | {split_inst['train'][c]} | {split_inst['val'][c]} |")
    L += [f"| | 合计 | {total} | | {sum(split_inst['train'].values())} | {sum(split_inst['val'].values())} |", "",
          "## 格式说明", "",
          "- `labels/*.txt` YOLO 检测：`cls xc yc w h`，框 = 掩码顶点外接矩形，归一化 [0,1]、6 位小数",
          "- `segments/*.txt` YOLO 分割：`cls x1 y1 ...`，掩码外轮廓（孔洞不表达），归一化 [0,1]",
          "- `semantic/*.png` 8 位灰度：像素值 = cls + 1（背景 0），实例按数组顺序以非零环绕规则填充（与画布一致），后画覆盖先画",
          "- `train.txt` / `val.txt`：`./images/<图>.jpg`（相对 dataset 根），9:1 随机划分",
          "- 类别编号 = 十类词表顺序：" + " · ".join(f"{i} {n}" for i, n in enumerate(CLASSES)), ""]
    with open(os.path.join(out, "export_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    return {"images": len(per_img), "instances": total, "per_class": {CLASSES[c]: cls_inst[c] for c in range(len(CLASSES))},
            "empty": empty, "train": len(train), "val": len(val), "deleted": deleted, "skipped": skipped}


def main():
    ap = argparse.ArgumentParser(description="三格式导出到 dataset/")
    ap.add_argument("--out", default=os.path.join(BASE, "dataset"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    out = os.path.abspath(args.out)

    docs = load_annotations(ANN_DIR)
    cons = check_consistency(load_records(), docs)
    if not cons["ok"]:
        print("一致性校验未通过，拒绝导出：")
        for s in cons["issues"]:
            print("  -", s)
        sys.exit(1)
    missing = [n for n in docs if not os.path.exists(os.path.join(IMG_DIR, n))]
    if missing:
        sys.exit(f"标注缺原图：{missing}")

    t0 = time.time()
    for sub in SUBDIRS:
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
        os.makedirs(os.path.join(out, sub))
    skipped = []
    per_img = {name: export_one(doc, out, skipped) for name, doc in sorted(docs.items())}

    train, val = split(per_img, args.seed)
    for fn, names in (("train.txt", train), ("val.txt", val)):
        with open(os.path.join(out, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"./images/{n}\n" for n in names))
    with open(os.path.join(out, "data.yaml"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# export_dataset.py 生成；不写 path，ultralytics 以本文件所在目录为数据集根\n"
                "train: train.txt\nval: val.txt\n"
                f"nc: {len(CLASSES)}\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASSES)))

    s = write_report(out, args.seed, docs, per_img, skipped, train, val, time.time() - t0)
    print(f"导出 {s['images']} 张 → {out}")
    print(f"有效实例 {s['instances']}（排除 deleted {s['deleted']}，零面积 {len(skipped)}：{skipped}）")
    print(f"空图 {len(s['empty'])} {s['empty']}")
    print(f"train {s['train']} / val {s['val']}")
    for i, (n, c) in enumerate(s["per_class"].items()):
        print(f"  {i} {n}: {c}")


if __name__ == "__main__":
    main()
