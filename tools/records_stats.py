# -*- coding: utf-8 -*-
"""P4 修正统计：data/records/修正记录.json + data/annotations/*.json
→ data/records/修正统计.json / 修正统计.md

口径（任务书红线：只计实际修改，仅查看/仅确认不计）：
- 修正条数 = 修正记录条数（画布每次实际修改写一条；撤销会同步撤掉记录）
- 图级修正率 = 该图本轮被修正过的不同实例数 / 该图 JSON 实例总数
  （分母 = auto 预标实例 + 人工新建实例，含标记为 deleted 的，即 len(instances)）
- 整体修正率 = Σ分子 / Σ分母，范围 = 本轮有修正记录或本轮已过审的图（过审轮次见 JSON reviewed_rounds）
- 另给 auto 修正率 = 被修正的 auto 实例数 / auto 实例总数（衡量预标草稿质量，P6 对比用）

用法：python tools/records_stats.py [--round 0]
  round 0 → 修正统计.json/.md；round N≥1 → 修正统计_rN.json/.md
"""
import os
import sys
import json
import time
import argparse
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC_DIR = os.path.join(BASE, "data", "records")
ANN_DIR = os.path.join(BASE, "data", "annotations")
REC_FILE = "修正记录.json"
TARGET = 60

TYPE_ZH = {"create": "新建框", "polygon": "多边形新建", "add_mask": "画笔新建掩码",
           "modify": "画笔扩展掩码(改形)", "erase_mask": "橡皮擦除掩码", "move": "移动",
           "resize": "缩放框(改形)", "reclass": "换类", "delete": "删除"}


def load_records(rec_dir=REC_DIR):
    p = os.path.join(rec_dir, REC_FILE)
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_annotations(ann_dir=ANN_DIR):
    docs = {}
    for fn in sorted(os.listdir(ann_dir)):
        if fn.endswith(".json"):
            with open(os.path.join(ann_dir, fn), "r", encoding="utf-8") as f:
                d = json.load(f)
            docs[d.get("image") or fn] = d
    return docs


def rate(a, b):
    return round(a / b, 4) if b else None


def reviewed_in(d, round_):
    """该图是否在 round_ 轮显式过审；R0 旧 JSON 只有 reviewed:true 无 reviewed_rounds，视为 [0]"""
    if not d.get("reviewed"):
        return False
    return round_ in (d.get("reviewed_rounds") or [0])


def compute(records, docs, classes, round_=0):
    cname = lambda c: classes[c] if isinstance(c, int) and 0 <= c < len(classes) else None
    rr = [r for r in records if r.get("round", 0) == round_]

    by_type = Counter(r["type"] for r in rr)
    by_class = Counter()
    involved = set()
    reclass_pairs = Counter()
    for r in rr:
        for c in (r.get("cls_before"), r.get("cls_after")):
            if cname(c):
                involved.add(c)
        main = r.get("cls_after") if r.get("cls_after") is not None else r.get("cls_before")
        if cname(main):
            by_class[cname(main)] += 1
        if r["type"] == "reclass":
            reclass_pairs[f"{cname(r['cls_before'])} → {cname(r['cls_after'])}"] += 1

    rec_by_img = defaultdict(list)
    for r in rr:
        rec_by_img[r["image"]].append(r)

    by_image, tot = [], Counter()
    scope = sorted(set(rec_by_img) | {n for n, d in docs.items() if reviewed_in(d, round_)})
    for name in scope:
        d = docs.get(name, {"instances": []})
        insts = d.get("instances", [])
        auto_ids = {i["id"] for i in insts if i.get("auto")}
        subj = {r["subject"] for r in rec_by_img.get(name, [])}
        row = {"image": name, "reviewed": reviewed_in(d, round_),
               "records": len(rec_by_img.get(name, [])),
               "by_type": dict(Counter(r["type"] for r in rec_by_img.get(name, []))),
               "instances_modified": len(subj), "instances_total": len(insts),
               "rate": rate(len(subj), len(insts)),
               "auto_modified": len(subj & auto_ids), "auto_total": len(auto_ids),
               "auto_rate": rate(len(subj & auto_ids), len(auto_ids))}
        by_image.append(row)
        for k in ("records", "instances_modified", "instances_total", "auto_modified", "auto_total"):
            tot[k] += row[k]

    all_auto = sum(1 for d in docs.values() for i in d.get("instances", []) if i.get("auto"))
    all_inst = sum(len(d.get("instances", [])) for d in docs.values())

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "round": round_,
        "target": TARGET,
        "total": len(rr),
        "progress": f"{len(rr)}/{TARGET}",
        "reached": len(rr) >= TARGET,
        "images_with_records": len(rec_by_img),
        "images_reviewed": sum(1 for d in docs.values() if reviewed_in(d, round_)),
        "images_total": len(docs),
        "by_type": dict(by_type.most_common()),
        "by_class": dict(by_class.most_common()),
        "classes_involved": [classes[c] for c in sorted(involved)],
        "reclass_pairs": dict(reclass_pairs.most_common()),
        "overall": {
            "scope": "本轮有修正记录或本轮已过审的图",
            "images": len(scope),
            "instances_modified": tot["instances_modified"], "instances_total": tot["instances_total"],
            "rate": rate(tot["instances_modified"], tot["instances_total"]),
            "auto_modified": tot["auto_modified"], "auto_total": tot["auto_total"],
            "auto_rate": rate(tot["auto_modified"], tot["auto_total"]),
        },
        "dataset": {"instances_total": all_inst, "auto_total": all_auto},
        "definition": {
            "修正条数": "修正记录.json 条数：每次实际修改（新增/删除/移动/改形/换类）一条；仅查看/缩放/切模式/仅确认保存不计",
            "图级修正率": "该图本轮被修正过的不同实例数 / 该图 JSON 实例总数（auto 预标 + 人工新建，含 deleted 标记）",
            "整体修正率": "Σ分子 / Σ分母，范围 = 本轮有修正记录或本轮已过审的图",
            "auto修正率": "被修正的 auto 实例数 / 该范围内 auto 实例总数",
        },
        "by_image": by_image,
        "consistency": check_consistency(records, docs),
    }


def check_consistency(records, docs):
    """修正记录 ↔ 画布 JSON：每图记录条数 = modified_count；被记录实例集合 = mark≠unchanged 的实例集合"""
    rec_by_img = defaultdict(list)
    for r in records:
        rec_by_img[r["image"]].append(r)
    issues = []
    for name in sorted(set(rec_by_img) | set(docs)):
        d = docs.get(name)
        recs = rec_by_img.get(name, [])
        if d is None:
            issues.append(f"{name}: 有 {len(recs)} 条记录但无标注 JSON")
            continue
        mc = d.get("modified_count", 0)
        if mc != len(recs):
            issues.append(f"{name}: modified_count={mc} ≠ 记录条数 {len(recs)}")
        marked = {i["id"] for i in d.get("instances", []) if i.get("mark", "unchanged") != "unchanged"}
        subj = {r["subject"] for r in recs}
        if marked != subj:
            only_m, only_r = sorted(marked - subj), sorted(subj - marked)
            issues.append(f"{name}: mark 与记录不一致（仅 mark: {only_m[:5]}；仅记录: {only_r[:5]}）")
    return {"ok": not issues, "issues": issues}


def to_md(s):
    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"
    o = s["overall"]
    L = [f"# 修正统计（round {s['round']}）", "",
         f"生成时间：{s['generated_at']}　·　数据源：`data/records/修正记录.json` + `data/annotations/*.json`（程序自动生成，勿手改）", "",
         "## 总览", "",
         "| 指标 | 值 |", "|---|---|",
         f"| 总修正条数 | **{s['total']}** / 目标 {s['target']}（{'已达标' if s['reached'] else '未达标'}） |",
         f"| 有修正的图 | {s['images_with_records']} 张 |",
         f"| 已过审的图 | {s['images_reviewed']} / {s['images_total']} 张 |",
         f"| 整体修正率 | {pct(o['rate'])}（{o['instances_modified']} / {o['instances_total']} 实例，范围 {o['images']} 张图） |",
         f"| auto 修正率 | {pct(o['auto_rate'])}（{o['auto_modified']} / {o['auto_total']} 个预标实例） |",
         f"| 涉及类别 | {', '.join(s['classes_involved']) or '—'} |",
         f"| 一致性校验（记录 ↔ JSON mark） | {'通过' if s['consistency']['ok'] else '**不一致**'} |", "",
         "## 按类型", "", "| 类型 | 含义 | 条数 |", "|---|---|---|"]
    L += [f"| {t} | {TYPE_ZH.get(t, '')} | {n} |" for t, n in s["by_type"].items()] or ["| — | | 0 |"]
    L += ["", "## 按类别（换类/新建计 cls_after，删除计 cls_before）", "", "| 类别 | 条数 |", "|---|---|"]
    L += [f"| {c} | {n} |" for c, n in s["by_class"].items()] or ["| — | 0 |"]
    if s["reclass_pairs"]:
        L += ["", "## 换类明细", "", "| 原类 → 新类 | 条数 |", "|---|---|"]
        L += [f"| {k} | {n} |" for k, n in s["reclass_pairs"].items()]
    L += ["", "## 按图", "", "| 图片 | 过审 | 修正条数 | 修正实例 / 实例总数 | 修正率 | auto 修正率 | 类型分布 |",
          "|---|---|---|---|---|---|---|"]
    for r in sorted(s["by_image"], key=lambda r: -r["records"]):
        bt = ", ".join(f"{k}×{v}" for k, v in r["by_type"].items()) or "—"
        L.append(f"| {r['image']} | {'✓' if r['reviewed'] else ''} | {r['records']} | "
                 f"{r['instances_modified']} / {r['instances_total']} | {pct(r['rate'])} | {pct(r['auto_rate'])} | {bt} |")
    if not s["by_image"]:
        L.append("| — | | 0 | | | | |")
    L += ["", "## 口径", ""] + [f"- **{k}**：{v}" for k, v in s["definition"].items()]
    if s["consistency"]["issues"]:
        L += ["", "## 一致性问题", ""] + [f"- {x}" for x in s["consistency"]["issues"]]
    return "\n".join(L) + "\n"


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def stats_name(round_):
    """R0 沿用 P4 文件名；R1 起分轮落盘，不覆盖已验收的 R0 统计"""
    return "修正统计" if round_ == 0 else f"修正统计_r{round_}"


def write_stats(classes, round_=0, rec_dir=REC_DIR, ann_dir=ANN_DIR, records=None):
    if records is None:
        records = load_records(rec_dir)
    s = compute(records, load_annotations(ann_dir), classes, round_)
    os.makedirs(rec_dir, exist_ok=True)
    _atomic_write(os.path.join(rec_dir, stats_name(round_) + ".json"), json.dumps(s, ensure_ascii=False, indent=1))
    _atomic_write(os.path.join(rec_dir, stats_name(round_) + ".md"), to_md(s))
    return s


def main():
    ap = argparse.ArgumentParser(description="生成 data/records/修正统计.json / .md")
    ap.add_argument("--round", type=int, default=0, help="统计轮次：0=R0 人工过审，1=P6 回标")
    args = ap.parse_args()
    sys.path.insert(0, BASE)
    from app import CLASSES
    s = write_stats(CLASSES, args.round)
    print(f"round {s['round']}: 修正 {s['progress']} 条 · 有修正的图 {s['images_with_records']} 张 · "
          f"已过审 {s['images_reviewed']} 张 · 整体修正率 {s['overall']['rate']} · "
          f"一致性 {'通过' if s['consistency']['ok'] else '不一致'}")
    for x in s["consistency"]["issues"]:
        print("  [不一致]", x)


if __name__ == "__main__":
    main()
