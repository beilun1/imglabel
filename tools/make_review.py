# -*- coding: utf-8 -*-
"""
P1 · 筛选辅助材料生成器

产出（全部在 data/review/ 下，预览用相对路径，在任何机器上都能直接打开）：
  1. candidates.csv / candidates.md   候选清单：文件名、来源、宽高、处理后路径、类别提示
  2. category_hints.csv              按图片内容给出的类别提示（id 编号对照十类词表）
  3. preview/index.html + page_XX.html  分批九宫格预览（每页 36 张，本地双击即可看）
  4. thumbs/                          预览用缩略图
  5. 分层抽样：候选池按类别配额抽取，控制人工过图总量

分层抽样规则（可 --pool all 跳过）：
  - COCO 三类（laptop / cup / bed）全量保留 —— 稀缺类，不砍；
  - VOC 七类每类目标 current * group 张；
  - 优先选「一图多类」的图（同样的图覆盖更多类别，过图效率高），再按类别补足。
  抽样只决定"给你看哪些候选"，最终保留/剔除由你人眼决定。

用法：
  python tools/make_review.py
  python tools/make_review.py --pool all       # 不抽样，3478 张全给
"""
import argparse
import csv
import html
import json
import os
import random
from collections import Counter, defaultdict

from PIL import Image

CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}

# 每类目标张数（分层抽样）
PER_CLASS_TARGET = 50
KEEP_ALL_SOURCES = {"COCO 2017 val"}   # 这三类稀缺，不抽样

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMG_DIR = os.path.join(PROJ, "data", "images")
REV_DIR = os.path.join(PROJ, "data", "review")
THUMB_DIR = os.path.join(REV_DIR, "thumbs")
PAGE_DIR = os.path.join(REV_DIR, "preview")
THUMB_SIDE = 300
PER_PAGE = 36


def load_meta():
    """读取两个来源的 _meta_*.json，合并成统一列表"""
    out = []
    for name in ("voc", "coco"):
        p = os.path.join("D:/imglabel_raw/candidates", name, f"_meta_{name}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for it in d["meta"]:
            out.append({"filename": it["filename"], "source": it["source"],
                        "hint": sorted(set(it["hint_classes"]), key=lambda c: CLASS_ID.get(c, 99))})
    return out


def stratified_pick(items, per_class=PER_CLASS_TARGET, max_per_combo=2):
    """分层抽样：稀缺来源全留；其余按类别配额，优先一图多类。

    坑（已踩）：只按"类别数降序"排，会导致某几张 4 类同框的图被反复选中，
    候选池里出现大量重复画面、多样性不足。故限制同一类别组合最多取 max_per_combo 张，
    再用来源目录做轮转，保证两类来源都均匀渗入。
    """
    must = [it for it in items if it["source"] in KEEP_ALL_SOURCES]
    rest = [it for it in items if it["source"] not in KEEP_ALL_SOURCES]
    # 多类优先（类别数降序），同类内按文件名稳定排序
    rest.sort(key=lambda x: (-len(x["hint"]), x["filename"]))

    picked, cnt = list(must), Counter()
    for it in must:
        for c in it["hint"]:
            cnt[c] += 1
    for c in CLASSES:
        if c not in cnt:
            cnt[c] = 0

    combo_seen = Counter()
    for it in must:
        combo_seen[tuple(it["hint"])] += 1

    # 两轮：第一轮严格限制同组合重复，第二轮放宽补齐缺口
    for strict in (True, False):
        for it in rest:
            if it in picked:
                continue
            useful = [c for c in it["hint"] if cnt[c] < per_class]
            if not useful:
                continue
            combo = tuple(it["hint"])
            if strict and combo_seen[combo] >= max_per_combo:
                continue
            picked.append(it)
            combo_seen[combo] += 1
            for c in it["hint"]:
                cnt[c] += 1
        if all(cnt[c] >= per_class for c in CLASSES):
            break
    return picked, cnt


def safe_name(fn):
    return fn.replace("/", "_").replace("\\", "_")


def build_thumbs(rows):
    os.makedirs(THUMB_DIR, exist_ok=True)
    ok = 0
    for r in rows:
        src = r["path"]
        dst = os.path.join(THUMB_DIR, safe_name(r["filename"]).rsplit(".", 1)[0] + ".jpg")
        if os.path.exists(dst):
            ok += 1
            continue
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                w, h = im.size
                s = THUMB_SIDE / float(max(w, h))
                if s < 1:
                    im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
                im.save(dst, "JPEG", quality=80, optimize=True)
            ok += 1
        except Exception as e:
            print(f"  缩略图失败 {r['filename']}: {e}")
    return ok


def write_lists(rows, cls_cnt, total_raw):
    csv_path = os.path.join(REV_DIR, "candidates.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "文件名", "来源", "宽", "高", "处理后路径", "类别提示", "类别编号"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["filename"], r["source"], r["w"], r["h"],
                        "data/images/" + r["filename"],
                        " | ".join(r["hint"]),
                        " | ".join(str(CLASS_ID[c]) for c in r["hint"])])

    hint_path = os.path.join(REV_DIR, "category_hints.csv")
    with open(hint_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "来源", "类别提示(英文)", "类别编号", "说明"])
        for r in rows:
            w.writerow([r["filename"], r["source"], " | ".join(r["hint"]),
                        " | ".join(str(CLASS_ID[c]) for c in r["hint"]),
                        "依据数据集自带标注推断，仅作提示，最终以人眼为准"])

    md_path = os.path.join(REV_DIR, "candidates.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# P1 候选图清单\n\n")
        f.write(f"- 候选池：**{len(rows)}** 张（原始候选 {total_raw} 张，分层抽样后）\n")
        f.write("- 图片目录：`data/images/`（长边 ≤960px、JPG 质量 85）\n")
        f.write("- 类别提示来自数据集自带标注，**仅作提示，最终以人眼为准**\n\n")
        f.write("## 按类别计数（一图可覆盖多类，故合计大于张数）\n\n")
        f.write("| 编号 | 类别 | 张数 |\n|---|---|---|\n")
        for c in CLASSES:
            f.write(f"| {CLASS_ID[c]} | {c} | {cls_cnt[c]} |\n")
        f.write("\n## 按来源计数\n\n| 来源 | 张数 |\n|---|---|\n")
        for s, n in Counter(r["source"] for r in rows).most_common():
            f.write(f"| {s} | {n} |\n")

    return csv_path, md_path, hint_path


PAGE_CSS = """
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;padding:18px 22px;
background:#f7f8fa;color:#1a1d21}
h1{font-size:19px;margin:0 0 6px}
.sub{color:#5b6470;font-size:13px;margin-bottom:14px;line-height:1.7}
.bar{position:sticky;top:0;background:#f7f8fa;padding:10px 0;margin-bottom:10px;
border-bottom:1px solid #e2e6ea;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:9}
.bar b{font-size:14px}
.nav a{color:#2563eb;text-decoration:none;font-size:13px;margin-right:10px}
.nav a:hover{text-decoration:underline}
.grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
@media(max-width:1200px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{background:#fff;border:1px solid #e2e6ea;border-radius:8px;overflow:hidden}
.card img{display:block;width:100%;height:150px;object-fit:cover;background:#eef1f4}
.meta{padding:6px 7px;font-size:11px;line-height:1.5}
.fn{font-weight:600;color:#1a1d21;word-break:break-all}
.src{color:#8a929c}
.tags{margin-top:3px}
.tag{display:inline-block;background:#e8f0fe;color:#1a56db;border-radius:4px;
padding:1px 5px;margin:1px 2px 0 0;font-size:10px}
.tag.c{background:#fdf0e6;color:#b45309}
.keep{color:#0a7d32;font-weight:600;letter-spacing:.5px;font-family:monospace}
"""


def write_previews(rows):
    os.makedirs(PAGE_DIR, exist_ok=True)
    pages = [rows[i:i + PER_PAGE] for i in range(0, len(rows), PER_PAGE)]
    for pi, page in enumerate(pages, 1):
        cards = []
        for r in page:
            thumb = "../thumbs/" + safe_name(r["filename"]).rsplit(".", 1)[0] + ".jpg"
            tags = "".join(
                f'<span class="tag{" c" if c in ("laptop", "cup", "bed") else ""}">'
                f'{CLASS_ID[c]} {html.escape(c)}</span>' for c in r["hint"])
            cards.append(f"""<div class="card"><img src="{thumb}" loading="lazy" alt="">
<div class="meta"><div class="fn">{html.escape(r['filename'])}</div>
<div class="src">{html.escape(r['source'])} · {r['w']}×{r['h']}</div>
<div class="tags">{tags}</div></div></div>""")
        nav = []
        if pi > 1:
            nav.append(f'<a href="page_{pi-1:02d}.html">← 上一批</a>')
        nav.append(f'<a href="index.html">总览</a>')
        if pi < len(pages):
            nav.append(f'<a href="page_{pi+1:02d}.html">下一批 →</a>')
        doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>第 {pi} 批 / 共 {len(pages)} 批</title><style>{PAGE_CSS}</style></head><body>
<div class="bar"><b>第 {pi} / {len(pages)} 批</b>
<span class="sub" style="margin:0">本批 {len(page)} 张 · 全池 {len(rows)} 张</span>
<span class="nav">{''.join(nav)}</span></div>
<div class="grid">{''.join(cards)}</div></body></html>"""
        with open(os.path.join(PAGE_DIR, f"page_{pi:02d}.html"), "w", encoding="utf-8") as f:
            f.write(doc)

    # 总览页
    idx_rows = []
    for pi, page in enumerate(pages, 1):
        names = "、".join(r["filename"].replace("voc_", "").replace("coco_", "").rsplit(".", 1)[0]
                          for r in page[:3])
        idx_rows.append(f'<tr><td><a href="page_{pi:02d}.html">第 {pi} 批</a></td>'
                        f'<td>{len(page)}</td><td>{html.escape(names)} …</td></tr>')
    doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>候选图筛选预览 · 总览</title><style>{PAGE_CSS}
table{{border-collapse:collapse;font-size:13px;background:#fff}}
td,th{{border:1px solid #e2e6ea;padding:6px 12px;text-align:left}}
th{{background:#eef1f4}}
a{{color:#2563eb;text-decoration:none}}
.rule{{background:#fff;border:1px solid #e2e6ea;border-radius:8px;padding:14px 18px;
font-size:13px;line-height:1.85;margin-bottom:16px}}
.rule code{{background:#eef1f4;padding:1px 5px;border-radius:4px;font-size:12px}}
.rule li{{margin-bottom:4px}}
</style></head><body>
<h1>P1 候选图筛选预览</h1>
<div class="sub">共 {len(rows)} 张，分 {len(pages)} 批，每批 {PER_PAGE} 张。点批次进入九宫格逐张过图。</div>
<div class="rule"><b>怎么用</b>
<ol>
<li>点「第 1 批」开始，浏览器里按 <code>Ctrl + 点击</code> 可以看大图。</li>
<li>每张卡片下方是<b>文件名</b>、来源与尺寸，蓝色标签是<b>类别提示</b>（来自数据集自带标注，
<b>仅作提示，最终以你人眼判断为准</b>）。</li>
<li>把要<b>剔除</b>的文件名记下来（或反过来记要保留的），回话时直接贴给我即可。</li>
<li>硬门槛：总量 ≥150 张、覆盖 ≥6 类、每类 ≥15 张；建议留足余量（如 160~170 张）。</li>
</ol></div>
<table><tr><th>批次</th><th>张数</th><th>本批前几张</th></tr>{''.join(idx_rows)}</table>
</body></html>"""
    with open(os.path.join(PAGE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return len(pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=["sample", "all"], default="sample")
    ap.add_argument("--per-class", type=int, default=PER_CLASS_TARGET)
    args = ap.parse_args()

    os.makedirs(REV_DIR, exist_ok=True)
    meta = load_meta()
    meta = [m for m in meta if os.path.exists(os.path.join(IMG_DIR, m["filename"]))]
    print(f"元数据可用 {len(meta)} 张")

    if args.pool == "all":
        picked = meta
        cnt = Counter()
        for it in picked:
            for c in it["hint"]:
                cnt[c] += 1
    else:
        picked, cnt = stratified_pick(meta, args.per_class)
        print(f"分层抽样：{len(meta)} -> {len(picked)} 张")

    rows = []
    for it in picked:
        p = os.path.join(IMG_DIR, it["filename"])
        try:
            with Image.open(p) as im:
                w, h = im.size
        except Exception:
            continue
        rows.append({"filename": it["filename"], "source": it["source"],
                     "w": w, "h": h, "hint": it["hint"], "path": p})

    rows.sort(key=lambda r: (r["hint"][0] if r["hint"] else "~", r["filename"]))
    cls_cnt = Counter()
    for r in rows:
        for c in r["hint"]:
            cls_cnt[c] += 1

    print("生成缩略图 ...")
    n_thumb = build_thumbs(rows)
    print(f"  缩略图 {n_thumb}/{len(rows)}")

    csv_path, md_path, hint_path = write_lists(rows, cls_cnt, len(meta))
    n_pages = write_previews(rows)

    print("\n=== 筛选材料已生成 ===")
    print(f"候选池 {len(rows)} 张，{n_pages} 批预览")
    for c in CLASSES:
        print(f"  {CLASS_ID[c]} {c:14s} {cls_cnt[c]:4d}")
    print(f"清单: {csv_path}")
    print(f"预览: {os.path.join(PAGE_DIR, 'index.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
