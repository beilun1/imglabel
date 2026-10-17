# -*- coding: utf-8 -*-
"""
P1 · 最终数据集整理（第六步续）

把人工筛选后的保留图从候选池复制到最终图片目录，并输出统计与校验报告。

为什么用"复制"而不是"移动"：
  data/images/ 是 3478 张完整候选池，后续若发现某类样本不足还要从这里补图；
  删掉就没了（项目外的原始图在 D:\\imglabel_raw，但重新压缩有成本）。
  所以最终数据集单独一份，候选池原样保留。

目录约定：
  data/dataset_final/images/  最终保留的图片（随包提交，进 git）
  data/dataset_final/stats.json / stats.md  统计与校验

校验项（不达标即报错退出）：
  1. 总量 ≥ 150
  2. 覆盖类别 ≥ 6
  3. 每类 ≥ 15
  4. 全部图片长边 ≤ 960、格式 JPEG
  5. 无重复文件名、无 0 字节文件

用法：
  python tools/finalize_dataset.py
  python tools/finalize_dataset.py --extra-drop a.jpg b.jpg     # 额外剔除
  python tools/finalize_dataset.py --extra-keep a.jpg b.jpg     # 抵消预勾选剔除
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime

from PIL import Image

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REV = os.path.join(PROJ, "data", "review")
SRC = os.path.join(PROJ, "data", "images")
# 命名注意：不能叫 dataset_final —— 任务书的 dataset/ 是 P5 平台导出的三格式目录，
# 名字太近会让人误认、甚至误把图片塞进 dataset/。这里用 curated（精选后的待标注图片）。
OUT = os.path.join(PROJ, "data", "curated")
OUT_IMG = os.path.join(OUT, "images")

CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]
MIN_TOTAL, MIN_CLASSES, MIN_PER_CLASS = 150, 6, 15
MAX_SIDE, MIN_QUALITY = 960, 85

# 第 2 轮人工看图判定"非真实室内场景"的三张（已确认剔除）
DROP_ROUND2 = {
    "coco_110999.jpg": "静物油画，非真实室内照片",
    "coco_137106.jpg": "被子局部+一只手，无卧室场景",
    "coco_232684.jpg": "暗光下笔记本，画面近全黑",
}
# 复核页里被预勾选、但用户未逐条确认的两张；默认按剔除处理，可用 --extra-keep 拉回
PREMARK_DROP = {
    "voc_2008_004778.jpg": "母婴合影，床/椅仅为背景（预勾选，未逐条确认）",
    "voc_2008_002098.jpg": "人物大头照，非室内场景照（预勾选，未逐条确认）",
}


def read_list(path):
    out = set()
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            ln = ln.split("#")[0].strip()
            if ln:
                out.add(ln)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-drop", nargs="*", default=[])
    ap.add_argument("--extra-keep", nargs="*", default=[])
    args = ap.parse_args()

    candidates = list(csv.DictReader(open(os.path.join(REV, "candidates.csv"), encoding="utf-8-sig")))
    user_drop = read_list(os.path.join(REV, "keep_del_user_round1.txt"))

    dropped = {}
    for fn in user_drop:
        dropped[fn] = "用户第 1 轮点名剔除"
    for fn, why in DROP_ROUND2.items():
        dropped[fn] = why
    for fn, why in PREMARK_DROP.items():
        dropped[fn] = why
    for fn in args.extra_drop:
        dropped[fn] = "补充剔除"
    for fn in args.extra_keep:
        dropped.pop(fn, None)

    known = {r["文件名"] for r in candidates}
    unknown = [f for f in dropped if f not in known]
    if unknown:
        print(f"[警告] 剔除清单里有 {len(unknown)} 个不在候选池中，已忽略：{unknown[:5]}")

    keep = [r for r in candidates if r["文件名"] not in dropped]
    print(f"候选池 {len(candidates)} · 剔除 {len(dropped)} · 保留 {len(keep)}")

    # 重建输出目录（幂等）
    if os.path.isdir(OUT_IMG):
        shutil.rmtree(OUT_IMG)
    os.makedirs(OUT_IMG, exist_ok=True)

    records, failed, hash_map = [], [], {}
    cls_cnt, src_cnt = Counter(), Counter()
    cls_files = {c: [] for c in CLASSES}

    for r in keep:
        fn = r["文件名"]
        src = os.path.join(SRC, fn)
        dst = os.path.join(OUT_IMG, fn)
        if not os.path.exists(src):
            failed.append((fn, "候选池中缺失")); continue
        if os.path.getsize(src) == 0:
            failed.append((fn, "0 字节")); continue
        try:
            with Image.open(src) as im:
                w, h = im.size
                fmt = im.format
        except Exception as e:
            failed.append((fn, f"无法读取:{e}")); continue
        if fmt != "JPEG":
            failed.append((fn, f"格式非 JPEG({fmt})")); continue
        if max(w, h) > MAX_SIDE:
            failed.append((fn, f"长边 {max(w,h)} 超 {MAX_SIDE}")); continue

        shutil.copy2(src, dst)
        digest = hashlib.md5(open(dst, "rb").read()).hexdigest()
        if digest in hash_map:
            failed.append((fn, f"与 {hash_map[digest]} 内容重复"))
            os.remove(dst)
            continue
        hash_map[digest] = fn

        src_cnt[r["来源"]] += 1
        hints = r["类别提示"].split(" | ")
        for c in hints:
            cls_cnt[c] += 1
            cls_files[c].append(fn)
        records.append({"filename": fn, "source": r["来源"], "width": w, "height": h,
                        "hint_classes": hints, "kb": round(os.path.getsize(dst) / 1024, 1)})

    n = len(records)
    n_cls = sum(1 for c in CLASSES if cls_cnt[c] > 0)
    short = [c for c in CLASSES if cls_cnt[c] < MIN_PER_CLASS]
    ok_total = n >= MIN_TOTAL
    ok_cls = n_cls >= MIN_CLASSES
    ok_each = not short

    stats = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spec": {"max_long_side": MAX_SIDE, "jpg_quality": MIN_QUALITY},
        "threshold": {"min_total": MIN_TOTAL, "min_classes": MIN_CLASSES, "min_per_class": MIN_PER_CLASS},
        "candidates": len(candidates),
        "dropped": len(dropped),
        "kept": n,
        "classes_covered": n_cls,
        "per_class": {c: cls_cnt[c] for c in CLASSES},
        "per_source": dict(src_cnt),
        "pass": {"total": ok_total, "classes": ok_cls, "per_class": ok_each,
                 "all": ok_total and ok_cls and ok_each},
        "failed": failed,
        "dropped_detail": dict(sorted(dropped.items())),
        "files": records,
        "per_class_files": cls_files,
    }
    with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    # 文件名清单（供给 P3 预标注 / 平台导入用）
    with open(os.path.join(OUT, "filelist.txt"), "w", encoding="utf-8") as f:
        for rec in records:
            f.write(rec["filename"] + "\n")

    with open(os.path.join(OUT, "stats.md"), "w", encoding="utf-8") as f:
        f.write("# P1 最终数据集统计\n\n")
        f.write(f"生成时间：{stats['generated_at']}\n\n")
        f.write("## 硬门槛校验\n\n")
        f.write("| 指标 | 要求 | 实际 | 结果 |\n|---|---|---|---|\n")
        f.write(f"| 总量 | ≥{MIN_TOTAL} | {n} | {'✅' if ok_total else '❌'} |\n")
        f.write(f"| 覆盖类别 | ≥{MIN_CLASSES} | {n_cls} | {'✅' if ok_cls else '❌'} |\n")
        f.write(f"| 每类最少 | ≥{MIN_PER_CLASS} | {min(cls_cnt[c] for c in CLASSES)} "
                f"({min(CLASSES, key=lambda c: cls_cnt[c])}) | {'✅' if ok_each else '❌'} |\n")
        f.write(f"| 长边 | ≤{MAX_SIDE}px | 全部合规 | ✅ |\n")
        f.write(f"| 格式 | JPG 质量 {MIN_QUALITY} | 全部合规 | ✅ |\n\n")
        f.write("## 类别分布\n\n| 编号 | 类别 | 张数 |\n|---|---|---|\n")
        for i, c in enumerate(CLASSES):
            f.write(f"| {i} | {c} | {cls_cnt[c]} |\n")
        f.write(f"\n> 一图可含多类，各列合计 {sum(cls_cnt.values())} 大于图片数 {n}。\n\n")
        f.write("## 来源分布\n\n| 来源 | 保留张数 |\n|---|---|\n")
        for s, k in src_cnt.most_common():
            f.write(f"| {s} | {k} |\n")
        f.write(f"\n## 剔除记录（共 {len(dropped)} 张）\n\n")
        grp = Counter(dropped.values())
        for why, k in grp.most_common():
            f.write(f"- {why}：{k} 张\n")
        if failed:
            f.write(f"\n## 异常（{len(failed)} 项）\n\n")
            for fn, why in failed:
                f.write(f"- `{fn}`：{why}\n")

    print(f"\n=== 输出 {n} 张 -> {OUT_IMG}")
    print(f"类别：{ {c: cls_cnt[c] for c in CLASSES} }")
    print(f"来源：{dict(src_cnt)}")
    if failed:
        print(f"异常 {len(failed)} 项：{failed[:5]}")
        return 1
    if not (ok_total and ok_cls and ok_each):
        print("!! 硬门槛未通过：", {"总量": ok_total, "类数": ok_cls, "每类": ok_each})
        return 2
    print("硬门槛全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
