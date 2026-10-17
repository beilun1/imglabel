# -*- coding: utf-8 -*-
"""
P1 · 第 2 轮复核页生成器（可勾选、可导出剔除清单）

与第 1 轮 preview 的区别：
  - 不是分页的只读九宫格，而是**单页滚动 + 可点击标记**；
  - 点卡片即标记为"剔除"（红框 + 置灰），再点取消；
  - 顶部实时显示"剩余 N 张 / 已标 M 张"和各维度余量；
  - 底部生成"复制剔除清单"按钮，一键把文件名列表复制出来（或下载 txt），
    直接把这段贴回对话即可，不用手抄文件名。

排序策略：把"最可能该删"的排在前面
  1. 场景可疑（非真实室内照：油画/插图/纯人像特写/目标占比极小）
  2. 画质可疑（低分辨率/发灰/暗光/模糊）
  3. 其余按类别分组、文件名顺序

用法：
  python tools/make_review2.py
产出：
  data/review/review2.html   （单文件，双击即可用）
"""
import base64
import csv
import html
import io
import json
import os

from PIL import Image

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REV = os.path.join(PROJ, "data", "review")
IMG = os.path.join(PROJ, "data", "images")

SIZES = ["person", "chair", "dining table", "couch", "tv",
         "laptop", "cup", "bottle", "potted plant", "bed"]

# 人工看图后认定应剔除的（第 2 轮抽查发现的非真实/非场景图），写死便于留痕。
# 注意：MANUAL_DROP 已在 Python 端从待复核列表里剔除，不会出现在页面上；
# 页面打开时用 PREMARK 预勾选"建议删"的图，用户可直接取消。
MANUAL_DROP = {
    "coco_110999.jpg": "静物油画，非真实室内照片（数据集标注有误）",
    "coco_137106.jpg": "被子局部+一只手，无卧室场景",
    "coco_232684.jpg": "暗光下笔记本，画面近全黑",
}
MANUAL_RISK = {
    "voc_2008_004778.jpg": "母婴合影，床/椅仅为背景",
    "voc_2008_002098.jpg": "人物大头照，非室内场景照",
}
# 页面打开时预勾选为"剔除"的（仍可点击取消）
PREMARK = set(MANUAL_RISK)


def load_deleted():
    deleted = set()
    p = os.path.join(REV, "keep_del_user_round1.txt")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            ln = ln.split("#")[0].strip()
            if ln:
                deleted.add(ln)
    deleted |= set(MANUAL_DROP)
    return deleted


def thumb_data_uri(path, side=260):
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((side, side), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=78, optimize=True)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def main():
    rows = list(csv.DictReader(open(os.path.join(REV, "candidates.csv"), encoding="utf-8-sig")))
    score = {r["文件名"]: r for r in
             csv.DictReader(open(os.path.join(REV, "review_round2.csv"), encoding="utf-8-sig"))}
    deleted = load_deleted()
    keep = [r for r in rows if r["文件名"] not in deleted]
    print(f"原始候选 {len(rows)} · 已剔除 {len(deleted)} · 待复核 {len(keep)}")

    def rank(r):
        fn = r["文件名"]
        if fn in MANUAL_DROP:
            return (0, 0)
        if fn in MANUAL_RISK:
            return (0, 1)
        s = float(score.get(fn, {}).get("风险分") or 0)
        return (1 if s >= 1.2 else 2, -s)

    keep.sort(key=lambda r: (rank(r), r["类别提示"], r["文件名"]))

    items = []
    for i, r in enumerate(keep, 1):
        fn = r["文件名"]
        sc = score.get(fn, {})
        note = MANUAL_DROP.get(fn) or MANUAL_RISK.get(fn) or sc.get("疑点", "")
        items.append({
            "i": i, "f": fn, "src": r["来源"], "w": r["宽"], "h": r["高"],
            "cls": r["类别提示"], "note": note,
            "risk": float(sc.get("风险分") or 0),
            "pre": 1 if fn in PREMARK else 0,
            "uri": thumb_data_uri(os.path.join(IMG, fn)),
        })

    payload = json.dumps(items, ensure_ascii=False)
    page = HTML_TPL.replace("__DATA__", payload) \
                   .replace("__CLS__", json.dumps(SIZES, ensure_ascii=False)) \
                   .replace("__TOTAL__", str(len(keep))) \
                   .replace("__DROP__", ", ".join(f"{k}（{v}）" for k, v in MANUAL_DROP.items()))
    out = os.path.join(REV, "review2.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"已生成 {out}（{os.path.getsize(out)/1048576:.1f} MB）")
    return 0


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P1 第2轮复核 · 勾选剔除</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;
background:#f7f8fa;color:#1a1d21}
header{position:sticky;top:0;z-index:50;background:#fff;border-bottom:1px solid #dfe4ea;
padding:10px 18px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0}
.stat{font-size:13px;color:#4a5462}
.stat b{color:#0a7d32;font-size:16px}
.stat .mark{color:#c0392b}
button{font:inherit;font-size:13px;padding:5px 12px;border-radius:6px;cursor:pointer;
border:1px solid #c9d1da;background:#fff}
button:hover{background:#f0f3f6}
button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
button.primary:hover{background:#1d4ed8}
.warn{background:#fff8e6;border:1px solid #f0d9a0;border-radius:6px;padding:6px 10px;
font-size:12px;color:#7a5b00;width:100%}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;padding:14px 18px 90px}
@media(max-width:1500px){.grid{grid-template-columns:repeat(5,1fr)}}
@media(max-width:900px){.grid{grid-template-columns:repeat(3,1fr)}}
.card{background:#fff;border:2px solid #e3e8ee;border-radius:8px;overflow:hidden;
cursor:pointer;user-select:none;transition:.12s}
.card:hover{border-color:#2563eb}
.card img{display:block;width:100%;height:132px;object-fit:cover;background:#eef1f4}
.card .m{padding:4px 6px;font-size:10.5px;line-height:1.45}
.card .fn{font-weight:600;word-break:break-all}
.card .s{color:#8a929c}
.card .t{margin-top:2px}
.tag{display:inline-block;background:#e8f0fe;color:#1a56db;border-radius:3px;
padding:0 4px;margin:1px 2px 0 0;font-size:9.5px}
.note{margin-top:3px;color:#b45309;font-size:9.5px;line-height:1.35}
.card.dropped{border-color:#c0392b;background:#fdecea;opacity:.62}
.card.dropped img{filter:grayscale(1) contrast(.8)}
.card.dropped::after{content:"剔除";position:absolute}
.card.dropped .fn{text-decoration:line-through;color:#c0392b}
footer{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #dfe4ea;
padding:10px 18px;display:flex;gap:12px;align-items:center;z-index:60;flex-wrap:wrap}
textarea{position:fixed;left:-9999px}
.hint{font-size:12px;color:#5b6470}
</style></head><body>
<header>
  <h1>P1 第 2 轮复核</h1>
  <span class="stat">待复核 <b id="left">__TOTAL__</b> 张 · 已标剔除 <b class="mark" id="mark">0</b> 张</span>
  <span class="stat" id="clsstat"></span>
  <button onclick="clearAll()">清空标记</button>
</header>
<div style="padding:10px 18px 0"><div class="warn">
  <b>用法：</b>点卡片 = 标记剔除，再点一次取消。<b>默认已预标</b>下图中几张明确不合格的（__DROP__），
  你可以取消或追加。排在最前的是"最可能该删"的。排完点右下角
  <b>「复制剔除清单」</b>，把剪贴板内容直接贴回对话即可，不用手抄文件名。
</div></div>
<div class="grid" id="grid"></div>
<footer>
  <button class="primary" onclick="copyList()">复制剔除清单</button>
  <button onclick="downloadList()">下载 txt</button>
  <span class="hint" id="msg"></span>
  <textarea id="ta"></textarea>
</footer>
<script>
const DATA = __DATA__;
const CLS = __CLS__;
const dropped = new Set();
const grid = document.getElementById('grid');
DATA.forEach(it=>{
  const d=document.createElement('div');
  d.className='card'+(it.note?' hasnote':'');
  d.dataset.f=it.f;
  const tags=it.cls.split(' | ').map(c=>`<span class="tag">${c}</span>`).join('');
  d.innerHTML=`<img src="${it.uri}" loading="lazy" alt="">
    <div class="m"><div class="fn">${it.f}</div>
    <div class="s">${it.w}×${it.h} · ${it.src.replace(' ','&nbsp;')}</div>
    <div class="t">${tags}</div>${it.note?`<div class="note">⚑ ${it.note}</div>`:''}</div>`;
  d.onclick=()=>{
    if(dropped.has(it.f)){dropped.delete(it.f);d.classList.remove('dropped');}
    else{dropped.add(it.f);d.classList.add('dropped');}
    update();
  };
  grid.appendChild(d);
  it._el=d;
});
// 预勾选（仍是普通标记，点一下即可取消）
DATA.filter(it=>it.pre).forEach(it=>{dropped.add(it.f);it._el.classList.add('dropped');});
function update(){
  document.getElementById('left').textContent = DATA.length - dropped.size;
  document.getElementById('mark').textContent = dropped.size;
  const c={};CLS.forEach(x=>c[x]=0);
  DATA.forEach(it=>{if(!dropped.has(it.f))it.cls.split(' | ').forEach(x=>c[x]=(c[x]||0)+1)});
  const bad=CLS.filter(x=>c[x]<15);
  document.getElementById('clsstat').innerHTML =
    CLS.map(x=>`<span style="color:${c[x]<15?'#c0392b':'#4a5462'}">${x.slice(0,7)}:${c[x]}</span>`).join(' · ')
    + (bad.length?` <b style="color:#c0392b">⚠ ${bad.join(',')} 不足15</b>`:'');
}
function listText(){return Array.from(dropped).sort().join('\n');}
function copyList(){
  const t=listText();
  if(!t){msg.textContent='还没标记任何图';return;}
  navigator.clipboard.writeText(t).then(()=>{msg.textContent=`已复制 ${dropped.size} 个文件名，去对话里粘贴即可`;})
   .catch(()=>{const ta=document.getElementById('ta');ta.value=t;ta.select();document.execCommand('copy');
     msg.textContent='已复制（兼容模式）';});
}
function downloadList(){
  const t=listText(); if(!t){msg.textContent='还没标记任何图';return;}
  const b=new Blob([t],{type:'text/plain;charset=utf-8'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(b); a.download='drop_list.txt'; a.click();
  msg.textContent='已下载 drop_list.txt';
}
function clearAll(){
  dropped.clear(); DATA.forEach(it=>it._el.classList.remove('dropped')); update();
  msg.textContent='已清空（含预标项）';
}
update();
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
