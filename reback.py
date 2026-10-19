# -*- coding: utf-8 -*-
"""P6 回标：用自训模型 model/best.pt 对 R0 未过审的预标草稿重新生成草稿（R1）

只回标同时满足以下条件的图（其余一律不碰，文件字节不变）：
  - JSON 存在且 source == "prelabel"（画布保存会丢弃 source → 人工保存过的图不回标）
  - 无 reviewed:true
  - modified_count == 0 且全部实例 mark == "unchanged"
  - 不含 src == "reback" 的实例、无 reback 元数据（幂等：已回标的图跳过，含回标结果为空的图）

输出与 P3 同一约定（画布 load/save 兼容）：
  {"image", "width", "height", "instances", "modified_count": 0, "source": "reback", "reback": {...}}
  实例 {"id": "p0..", "cls", "mark": "unchanged", "auto": true, "conf", "src": "reback",
        "mask": {"type": "polygon", "points"}}   ≥25px² 孔洞用零宽桥缝进外轮廓（prelabel.mask_to_polygon）

用法：
  python reback.py --dry-run          # 只列目标/跳过统计
  python reback.py --limit 3          # 先跑 3 张
  python reback.py                    # 全部目标图
  python reback.py --ann-dir D:/tmp/ann   # 自测用隔离目录
"""
import os
import sys
import json
import time
import hashlib
import argparse
from collections import Counter

from prelabel import CLASSES, IMG_DIR, ANN_DIR, DEFAULT_CONF, mask_to_polygon

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE, "model", "best.pt")

SKIP_ZH = {"reviewed": "已过审", "not_prelabel": "非预标草稿（人工保存过）",
           "modified": "有人工修改", "reback": "已回标"}


def skip_reason(doc):
    insts = doc.get("instances", [])
    if doc.get("source") == "reback" or "reback" in doc or any(i.get("src") == "reback" for i in insts):
        return "reback"
    if doc.get("reviewed"):
        return "reviewed"
    if doc.get("source") != "prelabel":
        return "not_prelabel"
    if doc.get("modified_count", 0) or any(i.get("mark", "unchanged") != "unchanged" for i in insts):
        return "modified"
    return None


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_model():
    if not os.path.exists(MODEL):
        raise FileNotFoundError(f"缺少 {MODEL}（P5 训练产物）")
    from ultralytics import YOLO
    m = YOLO(MODEL)
    names = [m.names[i] for i in range(len(m.names))]
    if names != CLASSES:
        raise ValueError(f"model/best.pt 类别与十类词表不符：{names}")
    return m


def reback_image(model, path, conf):
    r = model.predict(path, conf=conf, retina_masks=True, verbose=False)[0]
    h, w = r.orig_shape
    insts, dropped = [], 0
    if r.masks is not None:
        masks = r.masks.data.cpu().numpy()
        for k in range(len(r.boxes)):
            pts, extra = mask_to_polygon(masks[k], w, h)
            if pts is None:
                continue
            dropped += extra
            insts.append({"id": f"p{len(insts)}", "cls": int(r.boxes.cls[k]), "mark": "unchanged", "auto": True,
                          "conf": round(float(r.boxes.conf[k]), 3), "src": "reback",
                          "mask": {"type": "polygon", "points": pts}})
    return w, h, insts, dropped


def run(ann_dir=ANN_DIR, names=None, conf=DEFAULT_CONF, limit=0, dry_run=False, log=print):
    files = sorted(f for f in os.listdir(ann_dir) if f.endswith(".json"))
    if names:
        want = {os.path.splitext(n)[0] for n in names}
        files = [f for f in files if os.path.splitext(f)[0] in want]
    targets, skipped = [], Counter()
    for fn in files:
        with open(os.path.join(ann_dir, fn), encoding="utf-8") as f:
            doc = json.load(f)
        why = skip_reason(doc)
        if why:
            skipped[why] += 1
        else:
            targets.append((fn, doc))
    if limit:
        targets = targets[:limit]
    st = {"scanned": len(files), "targets": len(targets), "skipped": dict(skipped), "created": 0,
          "instances": 0, "replaced": 0, "by_class": Counter(), "dropped_fragments": 0, "errors": []}
    if dry_run or not targets:
        return st

    model = load_model()
    model_md5 = md5(MODEL)
    for k, (fn, old) in enumerate(targets):
        p = os.path.join(ann_dir, fn)
        try:
            before = md5(p)
            img = os.path.join(IMG_DIR, old["image"])
            w, h, insts, dropped = reback_image(model, img, conf)
            if (old.get("width"), old.get("height")) != (w, h):
                raise ValueError(f"尺寸 {w}x{h} 与 JSON {old.get('width')}x{old.get('height')} 不符")
            doc = {"image": old["image"], "width": w, "height": h, "instances": insts, "modified_count": 0,
                   "source": "reback",
                   "reback": {"model": "model/best.pt", "model_md5": model_md5, "conf": conf,
                              "dropped_fragments": dropped, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                              "replaced": {"instances": len(old.get("instances", [])),
                                           **Counter(i.get("src") for i in old.get("instances", []))}}}
            if md5(p) != before:      # 推理期间被画布保存过 → 不覆盖人工成果
                skipped["changed_during_run"] += 1
                continue
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
            st["created"] += 1
            st["instances"] += len(insts)
            st["replaced"] += len(old.get("instances", []))
            st["dropped_fragments"] += dropped
            st["by_class"].update(CLASSES[i["cls"]] for i in insts)
        except Exception as e:
            st["errors"].append(f"{fn}: {type(e).__name__}: {e}")
        if (k + 1) % 20 == 0 or k + 1 == len(targets):
            log(f"  [{k + 1}/{len(targets)}] {fn}")
    st["skipped"] = dict(skipped)
    return st


def main():
    ap = argparse.ArgumentParser(description="P6 用 model/best.pt 回标 R0 未过审草稿（已过审/人工改过/已回标的图跳过）")
    ap.add_argument("--conf", type=float, default=DEFAULT_CONF)
    ap.add_argument("--limit", type=int, default=0, help="只回标前 N 张目标图")
    ap.add_argument("--ann-dir", default=ANN_DIR, help="标注目录（自测用隔离副本）")
    ap.add_argument("--dry-run", action="store_true", help="只统计目标与跳过，不推理不写盘")
    ap.add_argument("names", nargs="*", help="只处理指定图片")
    a = ap.parse_args()
    t0 = time.time()
    s = run(a.ann_dir, a.names, a.conf, a.limit, a.dry_run)
    sk = "，".join(f"{SKIP_ZH.get(k, k)} {v}" for k, v in s["skipped"].items()) or "无"
    print(f"扫描 {s['scanned']} 张 · 目标 {s['targets']} 张 · 跳过：{sk}")
    if a.dry_run:
        return 0
    avg = s["instances"] / s["created"] if s["created"] else 0
    print(f"回标 {s['created']} 张 · 实例 {s['instances']}（替换 R0 草稿实例 {s['replaced']}）· 平均 {avg:.2f} 个/张 · "
          f"丢弃碎块 {s['dropped_fragments']} · 错误 {len(s['errors'])} · 用时 {time.time() - t0:.1f}s")
    if s["by_class"]:
        print("按类：" + " · ".join(f"{c} {s['by_class'].get(c, 0)}" for c in CLASSES))
    for e in s["errors"]:
        print("  错误：", e)
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
