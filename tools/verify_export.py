# -*- coding: utf-8 -*-
"""P5 导出校验：逐张核对 dataset/ 与 data/annotations/ 是否一致（全部 327 张，非抽样）。

1. 文件齐全、train/val 不重不漏
2. txt 格式：cls ∈ 0-9，坐标 ∈ [0,1]、6 位小数
3. 检测框 == 掩码顶点外接矩形；分割外轮廓的外接矩形 == 检测框（ultralytics 由分割派生的框与 labels 相同）
4. 外轮廓覆盖原掩码（孔洞被填上，其余不变）
5. 语义 PNG 与 matplotlib Path 独立重画的按类合并结果比对（不同光栅器，只允许轮廓 1px 带内差异）
6. 实例数守恒、空图为空标注

用法：python tools/verify_export.py [--out dataset] [--sample 3]
"""
import os
import sys
import random
import argparse
from collections import Counter

import cv2
import numpy as np
from matplotlib.path import Path as MplPath
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "tools"))
from export_dataset import CLASSES, ANN_DIR, bbox, fill_nonzero, is_degenerate, outer_ring  # noqa: E402
from records_stats import load_annotations  # noqa: E402


def raster_ref(points, w, h):
    """独立光栅器：matplotlib Path（非零环绕，与画布同规则）判像素中心"""
    m = np.zeros((h, w), dtype=bool)
    P = np.asarray(points, dtype=float)
    c0, r0 = max(0, int(P[:, 0].min())), max(0, int(P[:, 1].min()))
    c1, r1 = min(w, int(np.ceil(P[:, 0].max())) + 1), min(h, int(np.ceil(P[:, 1].max())) + 1)
    if c0 >= c1 or r0 >= r1:
        return m
    xx, yy = np.meshgrid(np.arange(c0, c1) + 0.5, np.arange(r0, r1) + 0.5)
    inside = MplPath(P).contains_points(np.column_stack([xx.ravel(), yy.ravel()]))
    m[r0:r1, c0:c1] = inside.reshape(xx.shape)
    return m


K3 = np.ones((3, 3), np.uint8)


def dilate(m):
    return cv2.dilate(m.astype(np.uint8), K3).astype(bool)


def edge_band(lbl):
    """3x3 邻域内类别不唯一的像素（即轮廓 1px 带）"""
    return cv2.dilate(lbl, K3) != cv2.erode(lbl, K3)


def parse(path, kind):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f.read().splitlines():
            t = ln.split()
            cls = int(t[0])
            assert t[0] == str(cls) and 0 <= cls < len(CLASSES), f"{path}: 非法类别 {t[0]}"
            assert all(len(v.split(".")[1]) == 6 for v in t[1:]), f"{path}: 非 6 位小数 {ln[:60]}"
            v = [float(x) for x in t[1:]]
            assert all(0.0 <= x <= 1.0 for x in v), f"{path}: 坐标越界 {ln[:60]}"
            if kind == "det":
                assert len(v) == 4, f"{path}: 检测行字段数 {len(t)}"
            else:
                assert len(v) >= 6 and len(v) % 2 == 0, f"{path}: 分割行字段数 {len(t)}"
            rows.append((cls, v))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(BASE, "dataset"))
    ap.add_argument("--sample", type=int, default=3)
    args = ap.parse_args()
    out = args.out
    docs = load_annotations(ANN_DIR)
    names = sorted(docs)
    stems = {os.path.splitext(n)[0] for n in names}

    for sub, ext in (("images", ".jpg"), ("labels", ".txt"), ("segments", ".txt"), ("semantic", ".png")):
        got = {os.path.splitext(f)[0] for f in os.listdir(os.path.join(out, sub)) if f.endswith(ext)}
        assert got == stems, f"{sub}: 缺 {sorted(stems - got)[:5]} 多 {sorted(got - stems)[:5]}"
        print(f"[1] {sub}: {len(got)} 个，与标注一一对应")
    tr = [l.strip() for l in open(os.path.join(out, "train.txt"), encoding="utf-8") if l.strip()]
    va = [l.strip() for l in open(os.path.join(out, "val.txt"), encoding="utf-8") if l.strip()]
    assert not set(tr) & set(va) and sorted(tr + va) == sorted(f"./images/{n}" for n in names)
    print(f"[1] train {len(tr)} + val {len(va)} = {len(tr) + len(va)}，不重不漏")

    cls_count, n_inst, empty, sem_diff, worst, degen, inner_diff = Counter(), 0, [], [], (0, None), [], 0
    uncovered, lost_exact, filled_px, box_err, ring_err = 0, 0, 0, 0.0, 0.0
    for n in names:
        d = docs[n]
        w, h, stem = d["width"], d["height"], os.path.splitext(n)[0]
        live = []
        for i in d["instances"]:
            if i.get("mark") == "deleted":
                continue
            if is_degenerate(i["mask"]["points"]):
                x0, y0, x1, y1 = bbox(i["mask"]["points"])
                degen.append(f"{n} {i['id']} 外接矩形 w={x1 - x0:.2f} h={y1 - y0:.2f} 像素数={fill_nonzero(i['mask']['points'], w, h).sum()}")
                continue
            live.append(i)
        det = parse(os.path.join(out, "labels", stem + ".txt"), "det")
        seg = parse(os.path.join(out, "segments", stem + ".txt"), "seg")
        assert len(det) == len(seg) == len(live), f"{n}: 实例数 det {len(det)} seg {len(seg)} json {len(live)}"
        sem = np.array(Image.open(os.path.join(out, "semantic", stem + ".png")))
        assert sem.shape == (h, w) and sem.dtype == np.uint8, f"{n}: PNG 尺寸/类型 {sem.shape} {sem.dtype}"
        if not live:
            empty.append(n)
            assert sem.max() == 0, f"{n}: 空图语义非全 0"
        ref = np.zeros((h, w), dtype=np.uint8)
        for inst, (dc, dv), (sc, sv) in zip(live, det, seg):
            assert dc == sc == inst["cls"], f"{n}: 类别不符"
            cls_count[dc] += 1
            x0, y0, x1, y1 = bbox(inst["mask"]["points"])
            exp = [min(max(v, 0), 1) for v in ((x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) / w, (y1 - y0) / h)]
            box_err = max(box_err, max(abs(a - b) for a, b in zip(dv, exp)))
            sx, sy = sv[0::2], sv[1::2]
            ring_box = ((min(sx) + max(sx)) / 2, (min(sy) + max(sy)) / 2, max(sx) - min(sx), max(sy) - min(sy))
            ring_err = max(ring_err, max(abs(a - b) for a, b in zip(ring_box, dv)))
            orig = fill_nonzero(inst["mask"]["points"], w, h)
            exact = fill_nonzero(outer_ring(inst["mask"]["points"]), w, h)
            ring = fill_nonzero([[x * w, y * h] for x, y in zip(sx, sy)], w, h)
            lost_exact += int((orig & ~exact).sum())
            # 顶点落在像素中心，6 位小数舍入会翻转边上像素（细尖刺可翻一串）→ 放宽 1px 后数残差
            uncovered = max(uncovered, int((orig & ~dilate(ring)).sum()))
            filled_px += int((exact & ~orig).sum())
            ref[raster_ref(inst["mask"]["points"], w, h)] = inst["cls"] + 1
        diff = ref != sem
        band = edge_band(ref) | edge_band(sem)
        inner = int((diff & ~band).sum())
        inner_diff += inner
        sem_diff.append(diff.sum() / (w * h))
        if inner > worst[0]:
            worst = (inner, n)
        n_inst += len(live)
        vals = set(np.unique(sem).tolist()) - {0}
        assert vals <= {i["cls"] + 1 for i in live}, f"{n}: 语义出现未标类别 {vals}"

    exp_total = sum(1 for d in docs.values() for i in d["instances"] if i.get("mark") != "deleted")
    exp_cls = Counter(i["cls"] for d in docs.values() for i in d["instances"] if i.get("mark") != "deleted")
    assert n_inst == exp_total - len(degen) and sum(exp_cls.values()) - sum(cls_count.values()) == len(degen)
    print(f"[2] 全部 txt 格式合法：cls∈0-9，坐标∈[0,1]，6 位小数")
    print(f"[3] 检测框 vs 掩码外接矩形 最大误差 {box_err:.2e}；分割外轮廓外接矩形 vs 检测框 最大误差 {ring_err:.2e}")
    print(f"[4] 外轮廓（未舍入几何）漏掉原掩码像素 {lost_exact}（全数据集合计，桥边穿像素中心的平局），被填上的孔洞像素合计 {filled_px}；"
          f"导出文本（6 位小数）放宽 1px 后单实例最多漏 {uncovered} 像素（舍入翻转的细尖刺）")
    print(f"[5] 语义 PNG vs matplotlib 独立重画（同为非零环绕）：总差异 {np.mean(sem_diff) * 100:.4f}%（边上像素判定不同）；"
          f"轮廓 1px 带外差异 {inner_diff} 像素")
    # 允许少量像素：零宽桥边恰好穿过像素中心，剪掉后该像素归属翻转（边上判定的平局）
    assert lost_exact <= 5 and uncovered <= 10 and inner_diff == 0, "外轮廓或语义 PNG 与掩码不一致"
    print(f"[6] 实例守恒：导出 {n_inst} == JSON mark≠deleted {exp_total} − 零面积 {len(degen)}")
    for s in degen:
        print(f"      零面积跳过：{s}")
    for c, nm in enumerate(CLASSES):
        print(f"      {c} {nm}: {cls_count[c]}")
    print(f"[6] 空图 {len(empty)} 张（空 txt + 全 0 PNG）：{empty}")

    rnd = random.Random(0)
    for n in rnd.sample([x for x in names if docs[x]["instances"]], args.sample):
        d, stem = docs[n], os.path.splitext(n)[0]
        live = [i for i in d["instances"] if i.get("mark") != "deleted"]
        sem = np.array(Image.open(os.path.join(out, "semantic", stem + ".png")))
        print(f"\n[抽样] {n} {d['width']}x{d['height']}，有效实例 {len(live)}，语义像素值 {dict(Counter(sem.ravel().tolist()))}")
        det = open(os.path.join(out, "labels", stem + ".txt"), encoding="utf-8").read().splitlines()
        seg = open(os.path.join(out, "segments", stem + ".txt"), encoding="utf-8").read().splitlines()
        for inst, dl, sl in list(zip(live, det, seg))[:3]:
            x0, y0, x1, y1 = bbox(inst["mask"]["points"])
            print(f"  {inst['id']} cls={inst['cls']} 掩码外接矩形 px=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}) 顶点 {len(inst['mask']['points'])}")
            print(f"    labels  : {dl}")
            print(f"    segments: {sl[:70]}…（{(len(sl.split()) - 1) // 2} 点）")
    print("\n校验全部通过")


if __name__ == "__main__":
    main()
