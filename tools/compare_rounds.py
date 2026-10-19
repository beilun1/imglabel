# -*- coding: utf-8 -*-
"""P6 R0/R1 对比：自动生成 data/records/对比结果.csv（UTF-8 BOM，Excel 直接打开；程序生成，勿手改）

数据源（全部程序读取，不手填）：
  - mAP 四项：model/train_metrics_r{N}.json（train.py --round N 写入；R0 = P5 初训，已冻结）
  - 修正条数 / 过审张数 / 涉及图数 / 整体修正率 / auto 修正率：
    data/records/修正记录.json 按 round 过滤 + data/annotations/*.json，口径同 tools/records_stats.py
状态列如实标注：R1 还没有人工修正记录 → 待人工修正；R1 训练早于最后一条 R1 记录或未训练 → 待重训。

用法：python tools/compare_rounds.py [--rounds 0 1]
"""
import os
import sys
import csv
import json
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "tools"))
from prelabel import CLASSES  # noqa: E402
import records_stats as rs  # noqa: E402

MODEL_DIR = os.path.join(BASE, "model")

MODEL_ZH = {0: "R0 初训：yolo26n-seg.pt 在 R0 数据（P3 预标草稿 + P4 人工过审修正）上微调",
            1: "R1 重训：R0 best.pt 回标未过审图 + R1 人工修正后，同参数重训"}
DRAFT_ZH = {0: "P3 YOLO26n-seg 分割 + YOLO-World 补框", 1: "P6 model/best.pt（R0）回标"}
METRICS = [("mAP50_det", "box_map50"), ("mAP50-95_det", "box_map50_95"),
           ("mAP50_seg", "seg_map50"), ("mAP50-95_seg", "seg_map50_95")]
COLUMNS = ["round", "best_model", "草稿来源", "训练完成时间", "train/val", "epochs(实际/设定)", "best_epoch",
           *[c for c, _ in METRICS], "修正条数", "过审张数", "涉及图数",
           "整体修正率", "整体修正实例/实例总数", "auto修正率", "auto修正实例/auto实例总数", "状态"]


def load_metrics(r):
    p = os.path.join(MODEL_DIR, f"train_metrics_r{r}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        m = json.load(f)
    if m.get("round", r) != r:
        raise ValueError(f"{p} 的 round={m.get('round')} 与文件名不符")
    return m


def row_of(r, records, docs):
    s = rs.compute(records, docs, CLASSES, r)
    m = load_metrics(r)
    o = s["overall"]
    rr = [x for x in records if x.get("round", 0) == r]
    last_rec = max((x["time"] for x in rr), default=None)
    if not rr:
        status = "待人工修正"
    elif m is None or (last_rec and m["time"] < last_rec):
        status = "待重训（训练早于最后一条本轮修正记录）" if m else "待重训"
    else:
        status = "完成"
    fmt = lambda v: "" if v is None else f"{v:.4f}"  # noqa: E731
    met = (m or {}).get("metrics", {})
    use_m = m is not None and (r == 0 or status == "完成")   # 过期的 R1 训练指标不填，避免张冠李戴
    return {
        "round": r, "best_model": MODEL_ZH.get(r, f"R{r}"), "草稿来源": DRAFT_ZH.get(r, ""),
        "训练完成时间": m["time"] if use_m else "",
        "train/val": f"{m['n_train']}/{m['n_val']}" if use_m else "",
        "epochs(实际/设定)": f"{m['epochs_run']}/{m['epochs']}" if use_m else "",
        "best_epoch": m["best_epoch"] if use_m else "",
        **{c: fmt(met.get(k)) if use_m else "" for c, k in METRICS},
        "修正条数": s["total"], "过审张数": s["images_reviewed"], "涉及图数": s["images_with_records"],
        "整体修正率": fmt(o["rate"]), "整体修正实例/实例总数": f"{o['instances_modified']}/{o['instances_total']}",
        "auto修正率": fmt(o["auto_rate"]), "auto修正实例/auto实例总数": f"{o['auto_modified']}/{o['auto_total']}",
        "状态": status,
    }


def main():
    ap = argparse.ArgumentParser(description="生成 data/records/对比结果.csv")
    ap.add_argument("--rounds", type=int, nargs="+", default=[0, 1])
    a = ap.parse_args()
    records, docs = rs.load_records(rs.REC_DIR), rs.load_annotations(rs.ANN_DIR)
    out = os.path.join(rs.REC_DIR, "对比结果.csv")
    cons = rs.check_consistency(records, docs)
    if not cons["ok"]:
        for x in cons["issues"]:
            print("  [不一致]", x)
        sys.exit("修正记录与标注 JSON 不一致，不生成对比结果（先排查）")
    rows = [row_of(r, records, docs) for r in a.rounds]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"→ {out}")
    for r in rows:
        print("  " + " · ".join(f"{k}={r[k]}" for k in COLUMNS if k not in ("best_model", "草稿来源")))


if __name__ == "__main__":
    main()
