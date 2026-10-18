# -*- coding: utf-8 -*-
"""P3 预标注：YOLO26n-seg 实例分割（真值源）+ YOLO-World 开放词汇检测（补漏）

输出 data/annotations/{图名}.json，字段与画布 load/save 完全一致：
  {"image", "width", "height", "instances": [...], "modified_count": 0, "source": "prelabel", ...}
实例：{"id", "cls", "mark": "unchanged", "auto": true, "conf", "src": "seg"|"det",
       "mask": {"type": "polygon", "points": [[x, y], ...]}}
  - mark 用 "unchanged"：画布 markModified 只会把非 created 的实例改成 modified，
    这样人工改过的草稿实例能被识别出来
  - src="det"：分割没覆盖、YOLO-World 补上的框，掩码是框矩形占位，需人工细化
已存在 JSON 的图一律跳过（幂等，不覆盖人工成果）。

用法：
  python prelabel.py --limit 3        # 先跑 3 张子集
  python prelabel.py                  # 全量（已有 JSON 的跳过）
  python prelabel.py --conf 0.3
"""
import os
import sys
import json
import time
import argparse
import threading
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "data", "curated", "images")
ANN_DIR = os.path.join(BASE, "data", "annotations")
WEIGHTS = os.path.join(BASE, "weights")
SEG_WEIGHT = os.path.join(WEIGHTS, "yolo26n-seg.pt")
WORLD_WEIGHT = os.path.join(WEIGHTS, "yolov8s-worldv2.pt")

CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]  # 顺序即编号，不得改

DEFAULT_CONF = 0.25
MIN_AREA = 25          # px²，与画布橡皮的碎块阈值一致
SAME_CLS_IOU = 0.5     # YOLO-World 框与同类分割框 IoU ≥ 此值 → 视为已覆盖
ANY_CLS_IOU = 0.8      # 与任意类分割框几乎重合 → 也视为已覆盖（避免同一物体出两个类）

_models = None
_models_lock = threading.Lock()


def _load_models():
    global _models
    with _models_lock:
        if _models is None:
            for w in (SEG_WEIGHT, WORLD_WEIGHT):
                if not os.path.exists(w):
                    raise FileNotFoundError(
                        f"缺少权重 {w}。请开 Watt Toolkit 加速 GitHub 后重试，或手动下载放到 weights/")
            import ultralytics.nn.text_model as tm
            tm.WEIGHTS_DIR = Path(WEIGHTS)       # CLIP 文本编码器放 weights/clip/，不随 cwd 漂移
            from ultralytics import YOLO
            seg = YOLO(SEG_WEIGHT)
            seg_map = {k: CLASSES.index(v) for k, v in seg.names.items() if v in CLASSES}
            assert len(seg_map) == len(CLASSES), f"分割模型缺类：{seg_map}"
            world = YOLO(WORLD_WEIGHT)
            world.set_classes(CLASSES)
            _models = (seg, seg_map, world)
    return _models


def ann_path(name):
    return os.path.join(ANN_DIR, os.path.splitext(name)[0] + ".json")


def list_images():
    return [f for f in sorted(os.listdir(IMG_DIR)) if f.lower().endswith((".jpg", ".jpeg", ".png"))]


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _signed_area(p):
    return sum(p[j][0] * p[i][1] - p[i][0] * p[j][1] for i, j in zip(range(len(p)), range(-1, len(p) - 1))) / 2


def _bridge(poly, hole):
    """孔洞反向绕行 + 零宽桥缝进外轮廓（与画布 bridgeHole 同一表示）"""
    best, bi, bj = None, 0, 0
    for i, p in enumerate(poly):
        for j, q in enumerate(hole):
            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
            if best is None or d < best:
                best, bi, bj = d, i, j
    return poly[:bi + 1] + hole[bj:] + hole[:bj + 1] + poly[bi:]


def mask_to_polygon(mask, w, h):
    """二值掩码 → 单环多边形：取最大连通块，≥MIN_AREA 的孔洞保留。返回 (points, 丢弃碎块数)"""
    import cv2
    import numpy as np
    m = (mask > 0.5).astype(np.uint8)
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, 0
    outers = [i for i in range(len(cnts)) if hier[0][i][3] < 0]
    big = [i for i in outers if cv2.contourArea(cnts[i]) >= MIN_AREA]
    if not big:
        return None, 0
    top = max(big, key=lambda i: cv2.contourArea(cnts[i]))

    def ring(c, positive):
        c = cv2.approxPolyDP(c, 1.0, True).reshape(-1, 2)
        pts = [[round(min(max(float(x) + 0.5, 0), w), 1), round(min(max(float(y) + 0.5, 0), h), 1)] for x, y in c]
        if len(pts) < 3:
            return None
        if (_signed_area(pts) > 0) != positive:
            pts.reverse()
        return pts

    poly = ring(cnts[top], True)
    if poly is None:
        return None, 0
    child = hier[0][top][2]
    while child >= 0:
        if cv2.contourArea(cnts[child]) >= MIN_AREA:
            hole = ring(cnts[child], False)
            if hole:
                poly = _bridge(poly, hole)
        child = hier[0][child][0]
    return poly, len(big) - 1


def prelabel_image(path, conf=DEFAULT_CONF):
    """单张图 → 标注文档（不落盘）"""
    seg, seg_map, world = _load_models()
    r = seg.predict(path, conf=conf, classes=list(seg_map), retina_masks=True, verbose=False)[0]
    h, w = r.orig_shape
    insts, seg_boxes, dropped = [], [], 0
    if r.masks is not None:
        masks = r.masks.data.cpu().numpy()
        for k in range(len(r.boxes)):
            pts, extra = mask_to_polygon(masks[k], w, h)
            if pts is None:
                continue
            dropped += extra
            cls = seg_map[int(r.boxes.cls[k])]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            seg_boxes.append((cls, (min(xs), min(ys), max(xs), max(ys))))
            insts.append({"cls": cls, "conf": round(float(r.boxes.conf[k]), 3), "src": "seg", "points": pts})

    q = world.predict(path, conf=conf, verbose=False)[0]
    for k in range(len(q.boxes)):
        cls = int(q.boxes.cls[k])
        x0, y0, x1, y1 = [float(v) for v in q.boxes.xyxy[k]]
        x0, x1 = round(max(0.0, x0), 1), round(min(float(w), x1), 1)
        y0, y1 = round(max(0.0, y0), 1), round(min(float(h), y1), 1)
        if (x1 - x0) * (y1 - y0) < MIN_AREA:
            continue
        box = (x0, y0, x1, y1)
        if any(_iou(box, b) >= (SAME_CLS_IOU if c == cls else ANY_CLS_IOU) for c, b in seg_boxes):
            continue
        seg_boxes.append((cls, box))   # 同一张图 YOLO-World 自身重复框也只补一次
        insts.append({"cls": cls, "conf": round(float(q.boxes.conf[k]), 3), "src": "det",
                      "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]})

    instances = [{"id": f"p{i}", "cls": it["cls"], "mark": "unchanged", "auto": True,
                  "conf": it["conf"], "src": it["src"],
                  "mask": {"type": "polygon", "points": it["points"]}}
                 for i, it in enumerate(insts)]
    return {"image": os.path.basename(path), "width": w, "height": h,
            "instances": instances, "modified_count": 0,
            "source": "prelabel",
            "prelabel": {"seg": os.path.basename(SEG_WEIGHT), "det": os.path.basename(WORLD_WEIGHT),
                         "conf": conf, "dropped_fragments": dropped,
                         "time": time.strftime("%Y-%m-%d %H:%M:%S")}}


def run(names=None, conf=DEFAULT_CONF, on_progress=None):
    """批量预标注。on_progress(event, **info)：event ∈ loading / start / image / done"""
    names = list_images() if names is None else names
    os.makedirs(ANN_DIR, exist_ok=True)
    stats = {"total": len(names), "done": 0, "created": 0, "skipped": 0, "instances": 0,
             "seg": 0, "det": 0, "errors": []}
    emit = on_progress or (lambda *a, **k: None)
    emit("loading", **stats)
    _load_models()
    emit("start", **stats)
    for n in names:
        emit("image", current_file=n, **stats)
        try:
            if os.path.exists(ann_path(n)):
                stats["skipped"] += 1
            else:
                doc = prelabel_image(os.path.join(IMG_DIR, n), conf)
                try:
                    with open(ann_path(n), "x", encoding="utf-8") as f:   # "x"：期间若被人工保存则不覆盖
                        json.dump(doc, f, ensure_ascii=False, indent=1)
                except FileExistsError:
                    stats["skipped"] += 1
                else:
                    stats["created"] += 1
                    stats["instances"] += len(doc["instances"])
                    for it in doc["instances"]:
                        stats[it["src"]] += 1
        except Exception as e:
            stats["errors"].append(f"{n}: {type(e).__name__}: {e}")
        stats["done"] += 1
    emit("done", current_file=None, **stats)
    return stats


def main():
    ap = argparse.ArgumentParser(description="P3 预标注（已有 JSON 的图跳过）")
    ap.add_argument("--conf", type=float, default=DEFAULT_CONF, help="置信度阈值（分割与检测共用）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 张（子集验证）")
    ap.add_argument("names", nargs="*", help="指定图片文件名（默认全部）")
    a = ap.parse_args()
    names = a.names or list_images()
    if a.limit:
        names = names[:a.limit]
    t0 = time.time()

    def show(ev, **s):
        if ev == "loading":
            print(f"加载模型…（共 {s['total']} 张）", flush=True)
        elif ev == "image" and (s["done"] % 20 == 0 or s["total"] <= 20):
            print(f"  [{s['done'] + 1}/{s['total']}] {s['current_file']}", flush=True)

    s = run(names, a.conf, show)
    avg = s["instances"] / s["created"] if s["created"] else 0
    print(f"完成：新建 {s['created']} 张 / 跳过 {s['skipped']} 张 / 错误 {len(s['errors'])}，"
          f"实例 {s['instances']}（分割 {s['seg']} + 检测补框 {s['det']}），平均 {avg:.2f} 个/张，"
          f"用时 {time.time() - t0:.1f}s")
    for e in s["errors"]:
        print("  错误：", e)
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
