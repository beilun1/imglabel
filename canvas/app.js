/* =========================================================
 * 人机协同图像标注系统 - 画布核心（P2）
 * 设计原则：实例掩码是唯一真值源；检测框 = 掩码外接矩形；
 * 语义图 = 实例按类合并。改一处，三处同步。
 * ========================================================= */
"use strict";

const CONF = window.APP_CONF;
const CLASSES = CONF.classes;          // 十类，顺序即编号（红线）
const CLASSES_ZH = ["人", "椅子", "桌子", "沙发", "电视", "笔记本电脑", "杯子", "瓶子", "盆栽", "床"];
const PALETTE = ["#e5484d", "#2563eb", "#f97316", "#14b8a6", "#8b5cf6", "#16a34a", "#ec4899", "#eab308", "#84cc16", "#92400e"];
const BG_CANVAS = "#e9ebef";
const SEL_COLOR = "#ffffff";
const SEL_SHADOW = "rgba(0,0,0,.75)";

const state = {
  name: CONF.name, idx: CONF.idx, total: CONF.total,
  imgW: 0, imgH: 0,
  instances: [],                 // {id, cls, mark, mask:{type:'polygon',points:[[x,y]..]}}
  modifiedCount: 0,              // 本图累计修正条数（落盘于 JSON.modified_count，跨会话）
  records: [],                   // 本会话修正记录（与 modifiedCount 同步增减，随撤销/重做回退）
  session: "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
  recBase: null,                 // 本轮除本会话外已落盘的修正总数（累计进度 = recBase + records.length）
  reviewed: false,
  mode: "box",                   // box | mask | semantic
  tool: "brush",                 // brush | eraser | polygon | move
  boxTool: "move",               // 框模式工具：move（移动/选中/缩放）| create（新建框）
  hand: false,                   // 抓手工具（任意模式下左键拖动 = 平移）
  brushSize: 10,
  curCls: 0,
  selectedId: null,
  overlap: null,                 // 框模式重叠点选 {id, n}：选中者所在点有 n 个框重叠（选中信息提示用）
  pendingPts: [],                // 多边形打点中
  strokePts: [],                 // 画笔/橡皮当前笔触
  drawing: false,
  dragKind: null,                // box-resize | box-move | box-create | inst-move | pan
  dragHandle: null,              // nw/n/ne/e/se/s/sw/w
  editRect: null,                // 新建框预览 {x0,y0,x1,y1}
  hover: null,                   // 鼠标所在图像坐标（笔刷光标 / 多边形橡皮筋）
  undoStack: [], redoStack: [],
  scale: 1, ox: 0, oy: 0,
  spaceHeld: false,
  hintStart: 0,                  // 空画布引导提示开始时间（0 = 不显示），本张图只显示一次
  flash: null,                   // 操作提示 {text, start}（如橡皮无选中实例）
};
const HINT_HOLD = 2400, HINT_FADE = 600;

/* ---------- 致命错误：页面顶部红条显式提示，不再静默空白 ---------- */
function showFatal(msg) {
  let bar = document.getElementById("fatalBar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "fatalBar"; bar.className = "fatal-bar";
    document.body.prepend(bar);
  }
  bar.textContent = "⚠ " + msg;
}
window.addEventListener("error", e => {
  if (!document.getElementById("fatalBar"))
    showFatal(`脚本错误：${e.message}（${(e.filename || "").split("/").pop()}:${e.lineno}）`);
});
window.addEventListener("unhandledrejection", e =>
  showFatal(`脚本错误：${(e.reason && e.reason.message) || e.reason}`));

// 模板与脚本版本不一致（如旧服务进程缓存了旧模板）时，缺元素会让整页脚本崩溃
const REQUIRED_IDS = ["cvMain", "cvCompare", "boxMain", "boxLeft", "canvasArea", "classSel", "selInfo",
  "cntMod", "cntTotal", "cntTarget", "legend", "overlayLabel", "brushSize", "brushVal", "btnHand", "boxTools", "maskTools", "btnFit",
  "btnUndo", "btnRedo", "btnSave", "btnCompare", "btnSaveNext", "btnSaveNext2", "btnPrev", "btnNext"];
const missingIds = REQUIRED_IDS.filter(id => !document.getElementById(id));
if (missingIds.length) {
  const msg = `页面模板与脚本版本不一致（缺少 #${missingIds.join(", #")}）。` +
              "多半是旧的服务窗口还开着：请关闭所有标注服务窗口，重新运行 启动.bat 后刷新本页。";
  showFatal(msg);
  throw new Error(msg);
}

/* ---------- DOM ---------- */
const cvMain = document.getElementById("cvMain");
const cvComp = document.getElementById("cvCompare");
const ctxMain = cvMain.getContext("2d");
const ctxComp = cvComp.getContext("2d");
const boxMain = document.getElementById("boxMain");
const boxLeft = document.getElementById("boxLeft");
const area = document.getElementById("canvasArea");
const classSel = document.getElementById("classSel");
const selInfo = document.getElementById("selInfo");
const cntMod = document.getElementById("cntMod");
const cntTotal = document.getElementById("cntTotal");
const ROUND = CONF.round || 0;
const TARGET = CONF.target || 60;
document.getElementById("cntTarget").textContent = TARGET;
const legend = document.getElementById("legend");
const overlayLabel = document.getElementById("overlayLabel");
const brushInput = document.getElementById("brushSize");
const brushVal = document.getElementById("brushVal");
const btnHand = document.getElementById("btnHand");
const inspector = {
  cls: document.getElementById("insClass"), id: document.getElementById("insId"),
  conf: document.getElementById("insConf"), points: document.getElementById("insPoints"),
};

/* ---------- 类别下拉 ---------- */
function buildClassSel() {
  classSel.innerHTML = "";
  CLASSES.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = `${i} ${c}（${CLASSES_ZH[i]}）`;
    classSel.appendChild(opt);
  });
  classSel.value = state.curCls;
}

/* ---------- 坐标变换 ---------- */
const toScreen = (x, y) => ({ x: x * state.scale + state.ox, y: y * state.scale + state.oy });
const toImg = (sx, sy) => ({ x: (sx - state.ox) / state.scale, y: (sy - state.oy) / state.scale });
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const clampImg = w => ({ x: clamp(w.x, 0, state.imgW), y: clamp(w.y, 0, state.imgH) });

function fit() {
  const cw = cvMain.clientWidth, ch = cvMain.clientHeight;
  if (!state.imgW || !cw) return;
  state.scale = Math.min(cw / state.imgW, ch / state.imgH) * 0.98;
  state.ox = (cw - state.imgW * state.scale) / 2;
  state.oy = (ch - state.imgH * state.scale) / 2;
}

function zoomAt(factor, sx, sy) {
  const w = toImg(sx, sy);
  state.scale = Math.min(Math.max(state.scale * factor, 0.02), 64);
  state.ox = sx - w.x * state.scale;
  state.oy = sy - w.y * state.scale;
}

/* ---------- 几何工具 ---------- */
function ptsBBox(points) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  points.forEach(p => { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]);
                         x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); });
  return { x0, y0, x1, y1 };
}
function pointInPoly(pt, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
    if (((yi > pt[1]) !== (yj > pt[1])) &&
        (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function perpDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (!len) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / len;
}
function simplify(pts, eps) {
  if (pts.length < 3) return pts.slice();
  let dmax = 0, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = perpDist(pts[i], pts[0], pts[pts.length - 1]);
    if (d > dmax) { dmax = d; idx = i; }
  }
  if (dmax > eps) {
    const l = simplify(pts.slice(0, idx + 1), eps);
    const r = simplify(pts.slice(idx), eps);
    return l.slice(0, -1).concat(r);
  }
  return [pts[0], pts[pts.length - 1]];
}
function simplifyClosed(pts, eps) {
  if (pts.length < 4) return pts.slice();
  return simplify(pts.concat([pts[0]]), eps).slice(0, -1);
}
function circlePts(c, r, n = 16) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    out.push([clamp(c[0] + r * Math.cos(a), 0, state.imgW), clamp(c[1] + r * Math.sin(a), 0, state.imgH)]);
  }
  return out;
}
function uid() { return "i" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function textOn(hex) {
  const n = parseInt(hex.slice(1), 16);
  const lum = 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
  return lum > 150 ? "#1f2328" : "#ffffff";
}

/* ---------- 栅格化：笔触(+已有实例) → 外轮廓多边形 ----------
 * 笔触按 brushSize 真实粗细画到离屏画布，再用 Moore 邻域追踪取外轮廓，
 * 保证保存下来的掩码 = 屏幕上看到的涂抹区域。 */
const DX = [-1, -1, 0, 1, 1, 1, 0, -1], DY = [0, -1, -1, -1, 0, 1, 1, 1];
const DIR_INDEX = [1, 2, 3, 0, -1, 4, 7, 6, 5];
function traceContour(grid, W, H) {
  let start = -1;
  for (let i = 0; i < grid.length; i++) if (grid[i]) { start = i; break; }
  if (start < 0) return [];
  const fg = (x, y) => x >= 0 && y >= 0 && x < W && y < H && grid[y * W + x] === 1;
  const sx = start % W, sy = (start / W) | 0;
  const out = [[sx, sy]];
  let cx = sx, cy = sy, bdir = 0, firstMove = -1;
  for (let guard = 0; guard < 4 * W * H + 8; guard++) {
    let found = -1;
    for (let k = 1; k <= 8; k++) {
      const d = (bdir + k) % 8;
      if (fg(cx + DX[d], cy + DY[d])) { found = d; break; }
    }
    if (found < 0) break;
    if (cx === sx && cy === sy) {
      if (firstMove === -1) firstMove = found;
      else if (found === firstMove) break;
    }
    const prevD = (found + 7) % 8;
    const nx = cx + DX[found], ny = cy + DY[found];
    const bx = cx + DX[prevD] - nx, by = cy + DY[prevD] - ny;
    cx = nx; cy = ny; bdir = DIR_INDEX[(by + 1) * 3 + (bx + 1)];
    out.push([cx, cy]);
  }
  if (out.length > 1) out.pop();
  return out;
}
const MIN_PIECE = 25;              // px²，更小的碎块/孔洞直接丢弃（填平）
function signedArea(p) {
  let s = 0;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) s += p[j][0] * p[i][1] - p[i][0] * p[j][1];
  return s / 2;
}
function rasterCanvas(bb, pad) {
  const bx0 = Math.max(0, Math.floor(bb.x0 - pad)), by0 = Math.max(0, Math.floor(bb.y0 - pad));
  const bx1 = Math.min(state.imgW, Math.ceil(bb.x1 + pad)), by1 = Math.min(state.imgH, Math.ceil(bb.y1 + pad));
  const W = bx1 - bx0, H = by1 - by0;
  if (W <= 0 || H <= 0) return null;
  const oc = document.createElement("canvas");
  oc.width = W; oc.height = H;
  const c = oc.getContext("2d", { willReadFrequently: true });
  c.translate(-bx0, -by0);
  c.fillStyle = c.strokeStyle = "#000";
  return { c, bx0, by0, W, H };
}
function readGrid(rc) {
  const data = rc.c.getImageData(0, 0, rc.W, rc.H).data;
  const grid = new Uint8Array(rc.W * rc.H);
  let count = 0;
  for (let i = 0; i < grid.length; i++) if (data[i * 4 + 3] >= 128) { grid[i] = 1; count++; }
  return { grid, count };
}
// 与笔触预览完全同一套几何（圆头圆角线 / 单点圆盘）
function paintStroke(c, stroke, size) {
  if (stroke.length === 1) {
    c.beginPath(); c.arc(stroke[0][0], stroke[0][1], size / 2, 0, Math.PI * 2); c.fill();
  } else {
    c.lineWidth = size; c.lineCap = "round"; c.lineJoin = "round";
    c.beginPath(); c.moveTo(stroke[0][0], stroke[0][1]);
    for (let i = 1; i < stroke.length; i++) c.lineTo(stroke[i][0], stroke[i][1]);
    c.stroke();
  }
}
function loopFromGrid(grid, w, h, ox, oy, positive) {
  const contour = traceContour(grid, w, h).map(p => [p[0] + ox + 0.5, p[1] + oy + 0.5]);
  const pts = simplifyClosed(contour, 0.8);
  if (pts.length < 3) return null;
  if ((signedArea(pts) > 0) !== positive) pts.reverse();
  return pts;
}
// 孔洞反向绕行并用零宽"桥"缝进外轮廓：nonzero 填充与 pointInPoly 都把孔洞视为空
function bridgeHole(poly, hole) {
  let best = Infinity, bi = 0, bj = 0;
  for (let i = 0; i < poly.length; i++)
    for (let j = 0; j < hole.length; j++) {
      const d = (poly[i][0] - hole[j][0]) ** 2 + (poly[i][1] - hole[j][1]) ** 2;
      if (d < best) { best = d; bi = i; bj = j; }
    }
  return poly.slice(0, bi + 1).concat(hole.slice(bj), hole.slice(0, bj + 1), poly.slice(bi));
}
function componentPolygon(idxs, x0, y0, x1, y1, W, ox, oy) {
  const w = x1 - x0 + 3, h = y1 - y0 + 3;          // 外扩 1px，保证边框一圈都是背景
  const sub = new Uint8Array(w * h);
  idxs.forEach(i => { sub[(((i / W) | 0) - y0 + 1) * w + (i % W) - x0 + 1] = 1; });
  const sox = ox + x0 - 1, soy = oy + y0 - 1;
  let poly = loopFromGrid(sub, w, h, sox, soy, true);
  if (!poly) return null;
  const seen = new Uint8Array(w * h);
  const flood = (s, out) => {
    const st = [s]; seen[s] = 1;
    while (st.length) {
      const i = st.pop(); if (out) out.push(i);
      const x = i % w, y = (i / w) | 0;
      const nb = [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1];
      for (const k of nb) if (k >= 0 && !sub[k] && !seen[k]) { seen[k] = 1; st.push(k); }
    }
  };
  flood(0, null);
  for (let s = 0; s < w * h; s++) {
    if (sub[s] || seen[s]) continue;
    const holeIdx = [];
    flood(s, holeIdx);
    if (holeIdx.length < MIN_PIECE) continue;
    const hg = new Uint8Array(w * h);
    holeIdx.forEach(i => { hg[i] = 1; });
    const hole = loopFromGrid(hg, w, h, sox, soy, false);
    if (hole) poly = bridgeHole(poly, hole);
  }
  return poly;
}
// 栅格 → 8 连通块（含孔洞）多边形，按面积降序
function maskComponents(grid, W, H, ox, oy, minArea) {
  const label = new Uint8Array(W * H);
  const pieces = [];
  for (let s = 0; s < W * H; s++) {
    if (!grid[s] || label[s]) continue;
    const idxs = [], st = [s];
    label[s] = 1;
    let x0 = W, y0 = H, x1 = -1, y1 = -1;
    while (st.length) {
      const i = st.pop(); idxs.push(i);
      const x = i % W, y = (i / W) | 0;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      for (let d = 0; d < 8; d++) {
        const nx = x + DX[d], ny = y + DY[d];
        if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
        const k = ny * W + nx;
        if (grid[k] && !label[k]) { label[k] = 1; st.push(k); }
      }
    }
    if (idxs.length < minArea) continue;
    const points = componentPolygon(idxs, x0, y0, x1, y1, W, ox, oy);
    if (points) pieces.push({ area: idxs.length, points });
  }
  return pieces.sort((a, b) => b.area - a.area);
}
function rasterizeUnion(basePoly, stroke, size) {
  const rc = rasterCanvas(ptsBBox(stroke.concat(basePoly || [])), size / 2 + 2);
  if (!rc) return null;
  if (basePoly) { tracePath(rc.c, basePoly); rc.c.fill(); }
  paintStroke(rc.c, stroke, size);
  const pieces = maskComponents(readGrid(rc).grid, rc.W, rc.H, rc.bx0, rc.by0, 1);
  return pieces.length ? pieces[0].points : null;
}
// 橡皮（图层级）：只擦当前选中实例 = 其掩码 − 笔迹圆盘序列（布尔差）；笔迹经过的其他实例不动
function eraseStroke(stroke, size) {
  const inst = selectedInst();
  if (!inst) { flashHint("请先点选要擦除的实例"); return; }
  const r = size / 2, sb = ptsBBox(stroke);
  const ib = ptsBBox(inst.mask.points);
  if (ib.x1 < sb.x0 - r || ib.x0 > sb.x1 + r || ib.y1 < sb.y0 - r || ib.y0 > sb.y1 + r) return;
  const rc = rasterCanvas(ib, 2);
  if (!rc) return;
  tracePath(rc.c, inst.mask.points); rc.c.fill();
  const before = readGrid(rc).count;
  rc.c.globalCompositeOperation = "destination-out";
  paintStroke(rc.c, stroke, size);
  const after = readGrid(rc);
  if (after.count === before) return;
  pushUndo();
  const pieces = maskComponents(after.grid, rc.W, rc.H, rc.bx0, rc.by0, MIN_PIECE);
  if (!pieces.length) {
    inst.mark = "deleted";
    countEdit("delete", inst, inst.cls, null, { tool: "eraser" });
    state.selectedId = null;
    return;
  }
  inst.mask.points = pieces[0].points;
  markModified(inst);
  countEdit("erase_mask", inst, inst.cls, inst.cls);
  pieces.slice(1).forEach(pc => {
    const piece = { id: uid(), cls: inst.cls, mark: "created",
                    mask: { type: "polygon", points: pc.points } };
    state.instances.push(piece);
    countEdit("erase_mask", piece, null, inst.cls, { split_from: inst.id });
  });
}

/* ---------- 命中测试 ---------- */
const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const HANDLE_CURSOR = { nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize",
                        n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize" };
const liveInstances = () => state.instances.filter(i => i.mark !== "deleted");
const selectedInst = () => state.instances.find(i => i.id === state.selectedId && i.mark !== "deleted") || null;

function handlePos(bb, h) {
  const cx = (bb.x0 + bb.x1) / 2, cy = (bb.y0 + bb.y1) / 2;
  const map = { nw: [bb.x0, bb.y0], n: [cx, bb.y0], ne: [bb.x1, bb.y0],
               e: [bb.x1, cy], se: [bb.x1, bb.y1], s: [cx, bb.y1],
               sw: [bb.x0, bb.y1], w: [bb.x0, cy] };
  return map[h];
}
// 返回命中列表：选中框把手 → 单个 box-resize；否则外接矩形包含该点的全部框，按面积升序（小框在前）
function hitTestBox(sx, sy, tol = 9) {
  const sel = selectedInst();
  if (sel) {
    const bb = ptsBBox(sel.mask.points);
    for (const h of HANDLES) {
      const hp = toScreen(...handlePos(bb, h));
      if (Math.abs(hp.x - sx) <= tol && Math.abs(hp.y - sy) <= tol)
        return [{ kind: "box-resize", inst: sel, handle: h }];
    }
  }
  const w = toImg(sx, sy);
  const hits = [];
  for (const inst of liveInstances()) {
    const bb = ptsBBox(inst.mask.points);
    if (w.x >= bb.x0 && w.x <= bb.x1 && w.y >= bb.y0 && w.y <= bb.y1)
      hits.push({ kind: "box-move", inst, area: (bb.x1 - bb.x0) * (bb.y1 - bb.y0) });
  }
  return hits.sort((a, b) => a.area - b.area);
}
function hitTestMaskImg(x, y, cls = null) {
  const live = liveInstances();
  for (let k = live.length - 1; k >= 0; k--)
    if ((cls === null || live[k].cls === cls) && pointInPoly([x, y], live[k].mask.points)) return live[k];
  return null;
}

/* ---------- 撤销/重做 ---------- */
function snapshot() {
  return { instances: JSON.parse(JSON.stringify(state.instances)),
           modifiedCount: state.modifiedCount, records: state.records.slice(),
           selectedId: state.selectedId };
}
function commitUndo(snap) {
  state.undoStack.push(snap);
  if (state.undoStack.length > 100) state.undoStack.shift();
  state.redoStack = [];
}
const pushUndo = () => commitUndo(snapshot());
function restore(s) {
  state.instances = s.instances; state.modifiedCount = s.modifiedCount;
  state.records = s.records;
  state.selectedId = s.selectedId; state.pendingPts = [];
  draw();
}
function undo() {
  if (!state.undoStack.length) return;
  state.redoStack.push(snapshot());
  restore(state.undoStack.pop());
}
function redo() {
  if (!state.redoStack.length) return;
  state.undoStack.push(snapshot());
  restore(state.redoStack.pop());
}

/* ---------- 实例操作 ---------- */
const markModified = inst => { if (inst.mark !== "created") inst.mark = "modified"; };
function nowStr() {
  const d = new Date(), p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
// 唯一计数入口：每次实际修改 +1 条并生成一条修正记录（cls_before=null 表示新建，cls_after=null 表示删除）
function countEdit(type, inst, clsBefore, clsAfter, extra) {
  state.modifiedCount++;
  state.records.push(Object.assign({
    image: state.name, time: nowStr(), type, subject: inst.id,
    cls_before: clsBefore, cls_after: clsAfter, auto: !!inst.auto,
    round: ROUND, session: state.session, seq: state.records.length,
  }, extra || {}));
}
function addInstance(points, cls, select, type) {
  pushUndo();
  const inst = { id: uid(), cls, mark: "created",
                 mask: { type: "polygon", points } };
  state.instances.push(inst);
  countEdit(type, inst, null, cls);
  if (select) state.selectedId = inst.id;
  draw();
}
function deleteInstance(id) {
  const inst = state.instances.find(i => i.id === id);
  if (!inst || inst.mark === "deleted") return;
  pushUndo();
  inst.mark = "deleted";            // 保留记录（供 records 导出），渲染时过滤
  countEdit("delete", inst, inst.cls, null);
  if (state.selectedId === id) state.selectedId = null;
  draw();
}
function changeClass(id, cls) {
  const inst = state.instances.find(i => i.id === id);
  if (!inst || inst.cls === cls) return;
  pushUndo();
  const before = inst.cls;
  inst.cls = cls; markModified(inst);
  countEdit("reclass", inst, before, cls);
  draw();
}

/* ---------- 绘制 ---------- */
function draw() {
  resizeCanvases();
  drawOne(ctxMain, true);
  if (document.body.classList.contains("compare")) drawOne(ctxComp, false);
  updateCounter();
  syncClassUI();
  updateCursor();
}

function resizeCanvases() {
  const w = boxMain.clientWidth, h = boxMain.clientHeight;
  if (cvMain.width !== w) cvMain.width = w;
  if (cvMain.height !== h) cvMain.height = h;
  const wl = boxLeft.clientWidth, hl = boxLeft.clientHeight;
  if (cvComp.width !== wl) cvComp.width = wl;
  if (cvComp.height !== hl) cvComp.height = hl;
}

function tracePath(ctx, pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
}

// 选中高亮：深色衬底 + 橙色主线，浅色/深色图上都清晰
function strokeSelected(ctx, drawPath, width) {
  ctx.strokeStyle = SEL_SHADOW; ctx.lineWidth = (width + 2.5) / state.scale;
  drawPath(); ctx.stroke();
  ctx.strokeStyle = SEL_COLOR; ctx.lineWidth = width / state.scale;
  drawPath(); ctx.stroke();
}

function drawTag(ctx, text, x, y, col) {
  const s = state.scale;
  ctx.font = `600 ${13 / s}px "Segoe UI", "Microsoft YaHei", sans-serif`;
  const tw = ctx.measureText(text).width;
  const h = 18 / s, pad = 4 / s;
  const ty = Math.max(y - h, 0);
  ctx.fillStyle = col;
  ctx.fillRect(x, ty, tw + pad * 2, h);
  ctx.fillStyle = textOn(col);
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + pad, ty + h / 2);
  ctx.textBaseline = "alphabetic";
}

function drawOne(ctx, withOverlay) {
  const w = ctx.canvas.width, h = ctx.canvas.height;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = BG_CANVAS; ctx.fillRect(0, 0, w, h);
  if (!state.imgW) {
    if (withOverlay) drawCenterText(ctx, state.loadError || "图片加载中…", !!state.loadError);
    return;
  }
  ctx.setTransform(state.scale, 0, 0, state.scale, state.ox, state.oy);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(state.img, 0, 0, state.imgW, state.imgH);
  if (!withOverlay) return;

  const live = liveInstances();

  if (state.mode === "semantic") {
    // 语义：原图提亮淡化，再按类合并着色（同类一次填充，重叠处不叠色）
    ctx.fillStyle = "rgba(255,255,255,.5)";
    ctx.fillRect(0, 0, state.imgW, state.imgH);
    CLASSES.forEach((_, c) => {
      const ofCls = live.filter(i => i.cls === c);
      if (!ofCls.length) return;
      ctx.beginPath();
      ofCls.forEach(inst => {
        // 统一绕向：否则同类两实例绕向相反时，nonzero 会把重叠区抵消成空洞
        const p = signedArea(inst.mask.points) < 0 ? inst.mask.points.slice().reverse() : inst.mask.points;
        ctx.moveTo(p[0][0], p[0][1]);
        for (let i = 1; i < p.length; i++) ctx.lineTo(p[i][0], p[i][1]);
        ctx.closePath();
      });
      ctx.fillStyle = PALETTE[c];
      ctx.globalAlpha = 0.7; ctx.fill("nonzero"); ctx.globalAlpha = 1;
    });
  } else if (state.mode === "box") {
    live.forEach(inst => drawBox(ctx, inst, false));
    const sel = selectedInst();
    if (sel) drawBox(ctx, sel, true);
  } else {
    live.forEach(inst => drawMask(ctx, inst, false));
    const sel = selectedInst();
    if (sel) drawMask(ctx, sel, true);
  }

  // 画笔/橡皮当前笔触
  if (state.strokePts.length) {
    const col = state.tool === "eraser" ? "#ff3355" : PALETTE[state.curCls];
    ctx.globalAlpha = state.tool === "eraser" ? 0.5 : 0.65;
    ctx.strokeStyle = ctx.fillStyle = col;
    if (state.strokePts.length === 1) {
      ctx.beginPath();
      ctx.arc(state.strokePts[0][0], state.strokePts[0][1], state.brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.lineWidth = state.brushSize;
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(state.strokePts[0][0], state.strokePts[0][1]);
      for (let i = 1; i < state.strokePts.length; i++)
        ctx.lineTo(state.strokePts[i][0], state.strokePts[i][1]);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  // 多边形打点 + 到鼠标的橡皮筋
  if (state.mode === "mask" && state.pendingPts.length) {
    const pts = state.pendingPts.slice();
    if (state.hover) pts.push([state.hover.x, state.hover.y]);
    const path = () => {
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    };
    ctx.strokeStyle = SEL_SHADOW; ctx.lineWidth = 3.5 / state.scale; path(); ctx.stroke();
    ctx.strokeStyle = PALETTE[state.curCls]; ctx.lineWidth = 1.8 / state.scale; path(); ctx.stroke();
    state.pendingPts.forEach((p, i) => {
      ctx.beginPath(); ctx.arc(p[0], p[1], (i === 0 ? 5 : 3.5) / state.scale, 0, Math.PI * 2);
      ctx.fillStyle = i === 0 ? SEL_COLOR : "#ffffff"; ctx.fill();
      ctx.strokeStyle = "#1f2328"; ctx.lineWidth = 1.2 / state.scale; ctx.stroke();
    });
  }
  // 新建框预览
  if (state.editRect) {
    const r = state.editRect;
    const x = Math.min(r.x0, r.x1), y = Math.min(r.y0, r.y1);
    const rw = Math.abs(r.x1 - r.x0), rh = Math.abs(r.y1 - r.y0);
    ctx.setLineDash([6 / state.scale, 4 / state.scale]);
    ctx.strokeStyle = SEL_SHADOW; ctx.lineWidth = 3.5 / state.scale; ctx.strokeRect(x, y, rw, rh);
    ctx.strokeStyle = PALETTE[state.curCls]; ctx.lineWidth = 2 / state.scale; ctx.strokeRect(x, y, rw, rh);
    ctx.setLineDash([]);
  }
  // 画笔/橡皮光标圈：直观显示当前粗细
  if (state.mode === "mask" && (state.tool === "brush" || state.tool === "eraser") &&
      state.hover && !state.hand && !state.spaceHeld && state.dragKind !== "pan") {
    const r = state.brushSize / 2;
    ctx.beginPath(); ctx.arc(state.hover.x, state.hover.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2.5 / state.scale; ctx.stroke();
    ctx.strokeStyle = state.tool === "eraser" ? "#ff3355" : "#1f2328";
    ctx.lineWidth = 1.2 / state.scale; ctx.stroke();
  }

  if (state.flash) drawFlashHint(ctx);
  else if (!live.length && !state.strokePts.length && !state.pendingPts.length && !state.editRect)
    drawEmptyHint(ctx);
}

// 操作提示（非错误）：中央显示约 2 秒后淡出，与空画布引导同一样式
const FLASH_HOLD = 1500, FLASH_FADE = 500;
function flashHint(text) {
  const first = !state.flash;
  state.flash = { text, start: performance.now() };
  if (first) requestAnimationFrame(tickFlash);
}
function drawFlashHint(ctx) {
  const t = performance.now() - state.flash.start;
  ctx.globalAlpha = t <= FLASH_HOLD ? 1 : Math.max(0, 1 - (t - FLASH_HOLD) / FLASH_FADE);
  drawCenterText(ctx, state.flash.text, false);
  ctx.globalAlpha = 1;
}
function tickFlash() {
  if (!state.flash) return;
  if (performance.now() - state.flash.start >= FLASH_HOLD + FLASH_FADE) { state.flash = null; draw(); return; }
  draw();
  requestAnimationFrame(tickFlash);
}

function drawEmptyHint(ctx) {
  if (!state.hintStart) return;
  const t = performance.now() - state.hintStart;
  if (t >= HINT_HOLD + HINT_FADE) { state.hintStart = 0; return; }
  const tips = {
    box: "移动工具：点按掩码拖动/缩放手柄调整框\n新建框工具（N）：任意位置拖拽创建新框",
    mask: "按 W 用画笔涂抹 / 按 P 多边形打点，创建实例掩码",
    semantic: "暂无实例：语义图由实例掩码按类合并生成",
  };
  ctx.globalAlpha = t <= HINT_HOLD ? 1 : 1 - (t - HINT_HOLD) / HINT_FADE;
  drawCenterText(ctx, tips[state.mode], false);
  ctx.globalAlpha = 1;
}

function tickHint() {
  if (!state.hintStart) return;
  if (liveInstances().length) { state.hintStart = 0; draw(); return; }
  draw();
  requestAnimationFrame(tickHint);
}

function drawCenterText(ctx, text, isError) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.font = `600 15px "Segoe UI", "Microsoft YaHei", sans-serif`;
  const lines = text.split("\n"), LH = 22;
  const tw = Math.max(...lines.map(l => ctx.measureText(l).width));
  const cx = ctx.canvas.width / 2, cy = ctx.canvas.height / 2;
  const h = 40 + (lines.length - 1) * LH, top = cy - h / 2;
  ctx.fillStyle = isError ? "rgba(255,238,238,.96)" : "rgba(255,255,255,.88)";
  ctx.fillRect(cx - tw / 2 - 16, top, tw + 32, h);
  ctx.strokeStyle = isError ? "#e5484d" : "#d9dde3"; ctx.lineWidth = 1;
  ctx.strokeRect(cx - tw / 2 - 16 + 0.5, top + 0.5, tw + 32, h);
  ctx.fillStyle = isError ? "#b4232a" : "#1f2328"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  lines.forEach((l, i) => ctx.fillText(l, cx, cy + (i - (lines.length - 1) / 2) * LH));
  ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
}

function drawBox(ctx, inst, sel) {
  const bb = ptsBBox(inst.mask.points);
  const col = PALETTE[inst.cls];
  // 底层掩码淡显（体现"框=掩码外接矩形"联动）
  ctx.fillStyle = col; ctx.globalAlpha = sel ? 0.28 : 0.18;
  tracePath(ctx, inst.mask.points); ctx.fill(); ctx.globalAlpha = 1;

  const rectPath = () => { ctx.beginPath(); ctx.rect(bb.x0, bb.y0, bb.x1 - bb.x0, bb.y1 - bb.y0); };
  if (sel) strokeSelected(ctx, rectPath, 2.6);
  else {
    ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.lineWidth = 3.2 / state.scale; rectPath(); ctx.stroke();
    ctx.strokeStyle = col; ctx.lineWidth = 1.8 / state.scale; rectPath(); ctx.stroke();
  }

  drawTag(ctx, `${CLASSES[inst.cls]} #${state.instances.indexOf(inst)}`, bb.x0, bb.y0, sel ? SEL_COLOR : col);

  if (sel) {
    const hs = 8 / state.scale;
    ctx.fillStyle = "#ffffff"; ctx.strokeStyle = "#1f2328"; ctx.lineWidth = 1.4 / state.scale;
    for (const h of HANDLES) {
      const [hx, hy] = handlePos(bb, h);
      ctx.beginPath(); ctx.rect(hx - hs / 2, hy - hs / 2, hs, hs);
      ctx.fill(); ctx.stroke();
    }
  }
}

function drawMask(ctx, inst, sel) {
  const col = PALETTE[inst.cls];
  ctx.fillStyle = col; ctx.globalAlpha = sel ? 0.6 : 0.5;
  tracePath(ctx, inst.mask.points); ctx.fill(); ctx.globalAlpha = 1;
  if (sel) strokeSelected(ctx, () => tracePath(ctx, inst.mask.points), 2.4);
  else { ctx.strokeStyle = col; ctx.lineWidth = 1.6 / state.scale; tracePath(ctx, inst.mask.points); ctx.stroke(); }
  if (sel) {
    const bb = ptsBBox(inst.mask.points);
    drawTag(ctx, `${CLASSES[inst.cls]} #${state.instances.indexOf(inst)}`, bb.x0, bb.y0, SEL_COLOR);
  }
}

function updateCounter() {
  cntMod.textContent = state.modifiedCount;
  const total = state.recBase === null ? null : state.recBase + state.records.length;
  cntTotal.textContent = total === null ? "…" : total;
  cntTotal.classList.toggle("ok", total !== null && total >= TARGET);
}

// 下拉框：有选中实例时显示其类别（改下拉=改该实例），否则显示新建类别
function syncClassUI() {
  const sel = selectedInst();
  const v = String(sel ? sel.cls : state.curCls);
  if (classSel.value !== v) classSel.value = v;
  selInfo.textContent = sel ? `已选中 #${state.instances.indexOf(sel)}：下拉改其类别` +
    (state.mode === "box" && state.overlap && state.overlap.id === sel.id ? `（此处 ${state.overlap.n} 个框重叠，单击切换）` : "")
    : "新建类别";
  selInfo.classList.toggle("on", !!sel);
  if (inspector.cls) {
    inspector.cls.textContent = sel ? CLASSES[sel.cls] : "未选择";
    if (sel) {
      const seqIdx = state.instances.indexOf(sel);
      inspector.id.textContent = "#" + seqIdx;
      inspector.id.title = "底层 id: " + sel.id;
    } else {
      inspector.id.textContent = "—";
      inspector.id.title = "";
    }
    inspector.conf.textContent = sel && typeof sel.conf === "number" ? `${sel.conf.toFixed(3)} · ${sel.auto ? "自动" : "人工"}` : "—";
    inspector.points.textContent = sel && sel.mask ? sel.mask.points.length : "—";
  }
}

function updateCursor() {
  let c = "crosshair";
  if (state.dragKind === "pan") c = "grabbing";
  else if (state.spaceHeld || state.hand || state.mode === "semantic") c = "grab";
  else if (state.dragKind === "box-move" || state.dragKind === "inst-move") c = "move";
  else if (state.dragKind === "box-resize") c = HANDLE_CURSOR[state.dragHandle];
  else if (state.mode === "box" && state._hoverCursor) c = state._hoverCursor;
  else if (state.mode === "mask" && state.tool === "move") c = "move";
  if (cvMain.style.cursor !== c) cvMain.style.cursor = c;
}

/* ---------- 保存 / 导航 ---------- */
// review=true：显式保存（保存 / 保存并下一张 / S）= 本图已过审；翻页自动保存不置过审
async function saveCurrent(review) {
  if (!state.annLoaded) return false;
  const sent = state.records.slice();
  const doc = { image: state.name, width: state.imgW, height: state.imgH,
                instances: state.instances, modified_count: state.modifiedCount,
                session: state.session, records: sent, review: !!review };
  try {
    const r = await fetch("/api/annotation/" + encodeURIComponent(state.name), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc),
    });
    if (!r.ok) return false;
    const d = await r.json();
    if (typeof d.round_total === "number") state.recBase = d.round_total - sent.length;
    if (review) state.reviewed = true;
    draw();
    return true;
  } catch (_) { return false; }
}
async function goImage(newIdx) {
  if (newIdx < 0 || newIdx >= state.total) return;
  if (state.annLoaded && !(await saveCurrent(false))) { flashSave(false); return; }
  window.location.href = "/annotate/" + encodeURIComponent(names[newIdx]);
}
async function saveAndNext() {
  if (!state.annLoaded) { flashSave(false); return; }
  const ok = await saveCurrent(true);
  flashSave(ok);
  if (ok && state.idx + 1 < state.total)
    window.location.href = "/annotate/" + encodeURIComponent(names[state.idx + 1]);
}

/* ---------- 事件：指针 ---------- */
function evPos(e) {
  const r = cvMain.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
// 平移：中键 / 按住空格 / 抓手工具 / 语义模式（只读）下左键
function canPan(e) { return e.button === 1 || state.spaceHeld || state.hand || state.mode === "semantic"; }

cvMain.addEventListener("mousedown", e => { if (e.button === 1) e.preventDefault(); });

cvMain.addEventListener("pointerdown", e => {
  if (e.button !== 0 && e.button !== 1) return;
  if (!state.imgW) return;
  const p = evPos(e);
  cvMain.setPointerCapture(e.pointerId);

  if (canPan(e)) {
    state.dragKind = "pan";
    state._panStart = { x: p.x, y: p.y, ox: state.ox, oy: state.oy };
    updateCursor(); return;
  }

  if (state.mode === "box") {
    const hits = state.boxTool === "move" ? hitTestBox(p.x, p.y) : [];
    if (hits.length) {
      // 重叠轮换：已选中者在命中列表里 → 按下仍拖它，单击弹起才换到下一个（更大，最大后回最小）；
      // 否则选最小者。Alt+按下 = 立即换到下一个
      const k = hits.findIndex(h => h.inst.id === state.selectedId);
      const next = hits.length > 1 && k >= 0 ? hits[(k + 1) % hits.length] : null;
      const hit = k < 0 ? hits[0] : (next && e.altKey ? next : hits[k]);
      state.dragKind = hit.kind; state.dragHandle = hit.handle || null;
      state.selectedId = hit.inst.id;
      state.overlap = hits.length > 1 ? { id: hit.inst.id, n: hits.length } : null;
      state._moveStart = { x: p.x, y: p.y, inst: hit.inst, moved: false, snap: snapshot(),
                           pts: hit.inst.mask.points.map(pt => pt.slice()),
                           bb: ptsBBox(hit.inst.mask.points),
                           cycleTo: next && !e.altKey ? next.inst : null };
    } else if (state.boxTool === "create") {
      state.dragKind = "box-create";
      const w = clampImg(toImg(p.x, p.y));
      state.editRect = { x0: w.x, y0: w.y, x1: w.x, y1: w.y };
      state.selectedId = null; state.overlap = null;
    } else {
      state.selectedId = null; state.overlap = null;
    }
    draw(); return;
  }

  // mask 模式
  const w = toImg(p.x, p.y);
  if (state.tool === "brush" || state.tool === "eraser") {
    if (state.tool === "eraser" && !selectedInst()) { flashHint("请先点选要擦除的实例"); return; }
    state.drawing = true;
    state.strokePts = [[w.x, w.y]];
  } else if (state.tool === "polygon") {
    // 点击靠近首点 → 闭合（该次点击不再新增点）
    if (state.pendingPts.length > 2) {
      const first = toScreen(...state.pendingPts[0]);
      if (Math.hypot(first.x - p.x, first.y - p.y) <= 10) { closePolygon(); return; }
    }
    const c = clampImg(w);
    state.pendingPts.push([c.x, c.y]);
  } else { // move
    const hit = hitTestMaskImg(w.x, w.y);
    if (hit) {
      state.dragKind = "inst-move";
      state.selectedId = hit.id;
      state._moveStart = { x: p.x, y: p.y, inst: hit, moved: false, snap: snapshot(),
                           pts: hit.mask.points.map(pt => pt.slice()), bb: ptsBBox(hit.mask.points) };
    } else {
      state.selectedId = null;
      state.dragKind = "pan";
      state._panStart = { x: p.x, y: p.y, ox: state.ox, oy: state.oy };
    }
  }
  draw();
});

cvMain.addEventListener("pointermove", e => {
  const p = evPos(e);
  state.hover = toImg(p.x, p.y);
  if (state.dragKind === "pan") {
    state.ox = state._panStart.ox + (p.x - state._panStart.x);
    state.oy = state._panStart.oy + (p.y - state._panStart.y);
    draw(); return;
  }
  if (state.dragKind === "box-create") {
    const w = clampImg(state.hover);
    state.editRect.x1 = w.x; state.editRect.y1 = w.y;
    draw(); return;
  }
  if (state.dragKind === "box-resize") {
    const ms = state._moveStart, o = ms.bb, h = state.dragHandle;
    const w = clampImg(state.hover);
    let x0 = o.x0, y0 = o.y0, x1 = o.x1, y1 = o.y1;
    if (h.includes("n")) y0 = w.y;
    if (h.includes("s")) y1 = w.y;
    if (h.includes("w")) x0 = w.x;
    if (h.includes("e")) x1 = w.x;
    const nx0 = Math.min(x0, x1), nx1 = Math.max(x0, x1), ny0 = Math.min(y0, y1), ny1 = Math.max(y0, y1);
    if (nx1 - nx0 < 1 || ny1 - ny0 < 1) return;
    // 框缩放 → 掩码按比例同步缩放（框始终 = 掩码外接矩形）
    const kx = (nx1 - nx0) / ((o.x1 - o.x0) || 1), ky = (ny1 - ny0) / ((o.y1 - o.y0) || 1);
    ms.inst.mask.points = ms.pts.map(pt => [nx0 + (pt[0] - o.x0) * kx, ny0 + (pt[1] - o.y0) * ky]);
    ms.moved = true;
    draw(); return;
  }
  if (state.dragKind === "box-move" || state.dragKind === "inst-move") {
    const ms = state._moveStart, o = ms.bb;
    const ws = toImg(ms.x, ms.y);
    const dx = clamp(state.hover.x - ws.x, -o.x0, state.imgW - o.x1);
    const dy = clamp(state.hover.y - ws.y, -o.y0, state.imgH - o.y1);
    if (!ms.moved && Math.hypot(p.x - ms.x, p.y - ms.y) < 2) return;
    ms.inst.mask.points = ms.pts.map(pt => [pt[0] + dx, pt[1] + dy]);
    ms.moved = true;
    draw(); return;
  }
  if (state.drawing) {
    const last = state.strokePts[state.strokePts.length - 1];
    const minStep = Math.max(1, state.brushSize * 0.15);
    if (Math.hypot(state.hover.x - last[0], state.hover.y - last[1]) >= minStep)
      state.strokePts.push([state.hover.x, state.hover.y]);
    draw(); return;
  }
  if (state.mode === "box") {
    const hit = state.boxTool === "move" ? hitTestBox(p.x, p.y)[0] : null;
    state._hoverCursor = hit ? (hit.kind === "box-resize" ? HANDLE_CURSOR[hit.handle] : "move") : null;
    updateCursor();
    return;
  }
  if (state.mode === "mask") draw();
});

cvMain.addEventListener("pointerleave", () => {
  if (state.dragKind || state.drawing) return;
  state.hover = null; draw();
});

function endPointer() {
  if (state.dragKind === "box-create") {
    const r = state.editRect;
    if (r && Math.abs(r.x1 - r.x0) * state.scale > 4 && Math.abs(r.y1 - r.y0) * state.scale > 4) {
      const x0 = Math.min(r.x0, r.x1), y0 = Math.min(r.y0, r.y1);
      const x1 = Math.max(r.x0, r.x1), y1 = Math.max(r.y0, r.y1);
      state.editRect = null;
      addInstance([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], state.curCls, true, "create");
    }
    state.editRect = null;
  }
  if (["box-resize", "box-move", "inst-move"].includes(state.dragKind)) {
    const ms = state._moveStart;
    if (ms.moved) {           // 只有真的动了才计修改、才进撤销栈
      commitUndo(ms.snap);
      markModified(ms.inst);
      countEdit(state.dragKind === "box-resize" ? "resize" : "move", ms.inst, ms.inst.cls, ms.inst.cls);
    } else if (ms.cycleTo) {  // 重叠处单击：轮换到下一个框
      state.selectedId = ms.cycleTo.id;
      state.overlap.id = ms.cycleTo.id;
    }
    state._moveStart = null;
  }
  if (state.drawing) finalizeStroke();
  state.drawing = false; state.dragKind = null; state.dragHandle = null;
  state.strokePts = [];
  draw();
}
cvMain.addEventListener("pointerup", endPointer);
cvMain.addEventListener("pointercancel", endPointer);

function finalizeStroke() {
  const raw = state.strokePts;
  if (!raw.length) return;
  const r = state.brushSize / 2;
  if (state.tool === "eraser") { eraseStroke(raw, state.brushSize); return; }
  // 画笔：起点落在同类实例内部 → 合并扩展该实例；否则新建实例
  const hit = hitTestMaskImg(raw[0][0], raw[0][1], state.curCls);
  let pts;
  if (raw.length === 1 && !hit) pts = circlePts(raw[0], r, 16);
  else pts = rasterizeUnion(hit ? hit.mask.points : null, raw, state.brushSize);
  if (!pts) return;
  if (hit) {
    pushUndo();
    hit.mask.points = pts;
    markModified(hit);
    countEdit("modify", hit, hit.cls, hit.cls, { tool: "brush" });
  } else {
    addInstance(pts, state.curCls, false, "add_mask");
  }
}

function closePolygon() {
  if (state.pendingPts.length < 3) { state.pendingPts = []; draw(); return; }
  const pts = simplifyClosed(state.pendingPts, 0.5);
  state.pendingPts = [];
  if (pts.length >= 3) addInstance(pts, state.curCls, false, "polygon");
  else draw();
}

/* ---------- 滚轮缩放 ---------- */
cvMain.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  const p = evPos(e);
  zoomAt(factor, p.x, p.y);
  draw();
}, { passive: false });

/* ---------- 键盘 ----------
 * 只有文本输入框吞掉快捷键；焦点在下拉框/滑块/按钮上时快捷键照常生效，
 * 下拉框保留方向键切换类别（方向键不做画布快捷键）。 */
function isTextField(el) {
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === "textarea" || el.isContentEditable) return true;
  if (tag !== "input") return false;
  return !["range", "checkbox", "radio", "button", "submit", "reset", "color"].includes((el.type || "text").toLowerCase());
}
function setBrushSize(v) {
  state.brushSize = clamp(Math.round(v), +brushInput.min, +brushInput.max);
  brushInput.value = state.brushSize;
  brushVal.textContent = state.brushSize;
  draw();
}

document.addEventListener("keydown", e => {
  if (isTextField(e.target)) return;
  if (e.code === "Space") {
    e.preventDefault();               // 防止空格触发聚焦按钮 / 展开下拉框
    if (!state.spaceHeld) { state.spaceHeld = true; draw(); }
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if (k === "y") { e.preventDefault(); redo(); }
    return;
  }
  if (e.altKey) return;
  let handled = true;
  switch (e.key) {
    case "1": setMode("box"); break;
    case "2": setMode("mask"); break;
    case "3": setMode("semantic"); break;
    case "w": case "W": setMode("mask"); setTool("brush"); break;
    case "e": case "E": setMode("mask"); setTool("eraser"); break;
    case "p": case "P": setMode("mask"); setTool("polygon"); break;
    case "v": case "V":
      if (state.mode === "box") setBoxTool("move"); else { setMode("mask"); setTool("move"); }
      break;
    case "n": case "N": setMode("box"); setBoxTool("create"); break;
    case "h": case "H": setHand(!state.hand); break;
    case "[": setBrushSize(state.brushSize - 2); break;
    case "]": setBrushSize(state.brushSize + 2); break;
    case "s": case "S": saveAndNext(); break;
    case "Enter":
      if (state.mode === "mask" && state.pendingPts.length) closePolygon(); else handled = false;
      break;
    case "Delete": case "Backspace":
      if (state.selectedId) deleteInstance(state.selectedId);
      break;
    case "Escape":
      if (state.pendingPts.length) state.pendingPts = [];
      else if (state.hand) setHand(false);
      else state.selectedId = null;
      draw();
      break;
    default: handled = false;
  }
  if (handled) e.preventDefault();    // 阻止下拉框按字母/数字跳选项
});
document.addEventListener("keyup", e => {
  if (e.code === "Space" && state.spaceHeld) { state.spaceHeld = false; draw(); }
});
window.addEventListener("blur", () => { state.spaceHeld = false; });
cvMain.addEventListener("dblclick", () => {
  if (state.mode === "mask" && state.tool === "polygon") closePolygon();
});

/* ---------- 模式 / 工具 ---------- */
function setMode(m) {
  if (state.mode !== m) state.pendingPts = [];
  state.mode = m;
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.mode === m));
  document.getElementById("boxTools").style.display = m === "box" ? "flex" : "none";
  document.getElementById("maskTools").style.display = m === "mask" ? "flex" : "none";
  legend.hidden = m !== "semantic";
  overlayLabel.textContent = m === "semantic" ? "语义着色（只读，左键拖动平移）" : "标注叠加";
  draw();
}
function setTool(t) {
  if (state.tool !== t) state.pendingPts = [];
  state.tool = t;
  setHand(false);
  document.querySelectorAll(".tool[data-tool]").forEach(b => b.classList.toggle("active", b.dataset.tool === t));
  draw();
}
function setBoxTool(t) {
  state.boxTool = t;
  state._hoverCursor = null;
  setHand(false);
  document.querySelectorAll(".tool[data-boxtool]").forEach(b => b.classList.toggle("active", b.dataset.boxtool === t));
  updateCursor();
}
function setHand(on) {
  state.hand = on;
  btnHand.classList.toggle("active", on);
  draw();
}
document.querySelectorAll(".tab").forEach(b =>
  b.addEventListener("click", () => setMode(b.dataset.mode)));
document.querySelectorAll(".tool[data-tool]").forEach(b =>
  b.addEventListener("click", () => setTool(b.dataset.tool)));
document.querySelectorAll(".tool[data-boxtool]").forEach(b =>
  b.addEventListener("click", () => setBoxTool(b.dataset.boxtool)));
btnHand.addEventListener("click", () => setHand(!state.hand));

classSel.addEventListener("change", () => {
  const v = parseInt(classSel.value, 10);
  if (state.selectedId) changeClass(state.selectedId, v);
  state.curCls = v;
  draw();
});

brushInput.addEventListener("input", e => setBrushSize(parseInt(e.target.value, 10)));
document.getElementById("btnFit").addEventListener("click", () => { fit(); draw(); });
document.getElementById("btnUndo").addEventListener("click", undo);
document.getElementById("btnRedo").addEventListener("click", redo);
document.getElementById("btnSave").addEventListener("click", async () => flashSave(await saveCurrent(true)));
document.getElementById("btnCompare").addEventListener("click", () => {
  document.body.classList.toggle("compare");
  draw();
});
document.getElementById("btnSaveNext").addEventListener("click", saveAndNext);
document.getElementById("btnSaveNext2").addEventListener("click", saveAndNext);
document.getElementById("btnPrev").addEventListener("click", () => goImage(state.idx - 1));
document.getElementById("btnNext").addEventListener("click", () => goImage(state.idx + 1));
// 点完工具栏按钮/下拉框后把焦点交还页面，避免空格等键作用到按钮上
document.querySelectorAll(".toolbar button, .navbar button").forEach(b =>
  b.addEventListener("mouseup", () => b.blur()));

function flashSave(ok) {
  const btn = document.getElementById("btnSave");
  if (!btn.dataset.label) btn.dataset.label = btn.textContent;
  btn.textContent = ok ? "✓ 已保存" : "✗ 保存失败";
  btn.style.background = ok ? "var(--acc2)" : "var(--err)";
  btn.style.borderColor = btn.style.background;
  clearTimeout(flashSave._t);
  flashSave._t = setTimeout(() => {
    btn.textContent = btn.dataset.label; btn.style.background = ""; btn.style.borderColor = "";
  }, ok ? 900 : 2500);
}

/* ---------- 语义图例 ---------- */
function buildLegend() {
  legend.innerHTML = "";
  CLASSES.forEach((c, i) => {
    const d = document.createElement("div");
    d.className = "li";
    d.innerHTML = `<span class="sw" style="background:${PALETTE[i]}"></span>${i} ${c}`;
    legend.appendChild(d);
  });
}

/* ---------- 加载 ---------- */
let names = [CONF.name];
async function load() {
  buildClassSel(); buildLegend();
  setBrushSize(state.brushSize);
  setMode(state.mode);
  try {
    const r = await fetch("/api/images");
    const d = await r.json();
    names = d.names;
  } catch (_) {}
  try {
    const r = await fetch("/api/records/summary?round=" + ROUND, { cache: "no-store" });
    if (r.ok) state.recBase = (await r.json()).total;
  } catch (_) {}
  const img = new Image();
  img.src = "/image/" + encodeURIComponent(CONF.name);
  const loaded = await new Promise(res => { img.onload = () => res(true); img.onerror = () => res(false); });
  if (!loaded || !img.naturalWidth) {
    let why = "文件无法解码";
    try {
      const h = await fetch(img.src, { method: "HEAD", cache: "no-store" });
      if (!h.ok) why = `HTTP ${h.status}`;
    } catch (e) { why = "服务未响应"; }
    state.loadError = `图片加载失败：${CONF.name}（${why}）`;
    showFatal(state.loadError + "，已禁止保存以免覆盖已有标注。");
    draw();
    return;
  }
  state.img = img; state.imgW = img.naturalWidth; state.imgH = img.naturalHeight;
  fit(); draw();
  try {
    const r = await fetch("/api/annotation/" + encodeURIComponent(CONF.name));
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const doc = await r.json();
    state.instances = doc.instances || [];
    state.modifiedCount = doc.modified_count || 0;
    state.reviewed = !!doc.reviewed;
    state.annLoaded = true;
    if (!liveInstances().length) { state.hintStart = performance.now(); requestAnimationFrame(tickHint); }
    draw();
  } catch (e) {
    showFatal(`标注读取失败（${e.message}），已禁止保存以免覆盖已有标注。`);
    draw();
  }
}

new ResizeObserver(() => draw()).observe(area);
load();
