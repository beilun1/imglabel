/* =========================================================
 * 人机协同图像标注系统 - 画布核心（P2）
 * 设计原则：实例掩码是唯一真值源；检测框 = 掩码外接矩形；
 * 语义图 = 实例按类合并。改一处，三处同步。
 * ========================================================= */
"use strict";

const CONF = window.APP_CONF;
const CLASSES = CONF.classes;          // 十类，顺序即编号（红线）
const PALETTE = ["#ff6384", "#36a2eb", "#ffce56", "#4bc0c0", "#9966ff",
                 "#ff9f40", "#2ecc71", "#e74c3c", "#27ae60", "#8e44ad"];

const state = {
  name: CONF.name, idx: CONF.idx, total: CONF.total,
  imgW: 0, imgH: 0,
  instances: [],                 // {id, cls, mark, mask:{type:'polygon',points:[[x,y]..]}}
  modifiedCount: 0,
  mode: "box",                   // box | mask | semantic
  tool: "brush",                 // brush | eraser | polygon | move
  brushSize: 10,
  curCls: 0,
  selectedId: null,
  pendingPts: [],                // 多边形打点中
  strokePts: [],                 // 画笔/橡皮当前笔触
  drawing: false,                // 是否正在涂抹/拖动
  dragKind: null,                // box-resize | box-move | box-create | inst-move | pan
  dragHandle: null,              // nw/n/ne/e/se/s/sw/w
  editRect: null,                // 新建框预览 {x0,y0,x1,y1}
  undoStack: [], redoStack: [],
  scale: 1, ox: 0, oy: 0,
  spaceHeld: false,
};

/* ---------- DOM ---------- */
const cvMain = document.getElementById("cvMain");
const cvComp = document.getElementById("cvCompare");
const ctxMain = cvMain.getContext("2d");
const ctxComp = cvComp.getContext("2d");
const boxMain = document.getElementById("boxMain");
const boxLeft = document.getElementById("boxLeft");
const area = document.getElementById("canvasArea");
const classSel = document.getElementById("classSel");
const cntMod = document.getElementById("cntMod");
const legend = document.getElementById("legend");
const overlayLabel = document.getElementById("overlayLabel");
const boxLabels = { compare: document.querySelector("#boxLeft .box-label"),
                    overlay: overlayLabel };

/* ---------- 类别下拉 ---------- */
function buildClassSel() {
  classSel.innerHTML = "";
  CLASSES.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = `${i} ${c}（${["人","椅子","桌子","沙发","电视","笔记本电脑","杯子","瓶子","盆栽","床"][i]}）`;
    classSel.appendChild(opt);
  });
  classSel.value = state.curCls;
}

/* ---------- 坐标变换 ---------- */
const toScreen = (x, y) => ({ x: x * state.scale + state.ox, y: y * state.scale + state.oy });
const toImg = (sx, sy) => ({ x: (sx - state.ox) / state.scale, y: (sy - state.oy) / state.scale });

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
function isRectPoly(inst) {
  const p = inst.mask.points;
  if (p.length !== 4) return false;
  return Math.abs(p[0][0] - p[1][0]) < 1e-6 && Math.abs(p[1][1] - p[2][1]) < 1e-6 &&
         Math.abs(p[2][0] - p[3][0]) < 1e-6 && Math.abs(p[3][1] - p[0][1]) < 1e-6;
}
function uid() { return "i" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

/* ---------- 命中测试 ---------- */
function handlePos(bb, h) {
  const cx = (bb.x0 + bb.x1) / 2, cy = (bb.y0 + bb.y1) / 2;
  const map = { nw: [bb.x0, bb.y0], n: [cx, bb.y0], ne: [bb.x1, bb.y0],
               e: [bb.x1, cy], se: [bb.x1, bb.y1], s: [cx, bb.y1],
               sw: [bb.x0, bb.y1], w: [bb.x0, cy] };
  return map[h];
}
function hitTestBox(sx, sy, tol = 9) {
  const live = state.instances.filter(i => i.mark !== "deleted");
  for (let k = live.length - 1; k >= 0; k--) {
    const inst = live[k];
    const bb = ptsBBox(inst.mask.points);
    // 先看手柄（仅矩形实例可拖角/边）
    if (isRectPoly(inst)) {
      for (const h of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
        const hp = toScreen(...handlePos(bb, h));
        if (Math.hypot(hp.x - sx, hp.y - sy) <= tol)
          return { kind: "box-resize", inst, handle: h };
      }
    }
    // 框内部
    const sp1 = toScreen(bb.x0, bb.y0), sp2 = toScreen(bb.x1, bb.y1);
    if (sx >= sp1.x && sx <= sp2.x && sy >= sp1.y && sy <= sp2.y)
      return { kind: "box-move", inst };
  }
  return null;
}
function hitTestMask(sx, sy) {
  const w = toImg(sx, sy);
  const live = state.instances.filter(i => i.mark !== "deleted");
  for (let k = live.length - 1; k >= 0; k--)
    if (pointInPoly([w.x, w.y], live[k].mask.points)) return live[k];
  return null;
}

/* ---------- 撤销/重做 ---------- */
function snapshot() {
  return { instances: JSON.parse(JSON.stringify(state.instances)),
           modifiedCount: state.modifiedCount, selectedId: state.selectedId };
}
function pushUndo() {
  state.undoStack.push(snapshot());
  if (state.undoStack.length > 100) state.undoStack.shift();
  state.redoStack = [];
}
function undo() {
  if (!state.undoStack.length) return;
  state.redoStack.push(snapshot());
  const s = state.undoStack.pop();
  state.instances = s.instances; state.modifiedCount = s.modifiedCount;
  state.selectedId = s.selectedId; state.pendingPts = [];
  draw();
}
function redo() {
  if (!state.redoStack.length) return;
  state.undoStack.push(snapshot());
  const s = state.redoStack.pop();
  state.instances = s.instances; state.modifiedCount = s.modifiedCount;
  state.selectedId = s.selectedId; state.pendingPts = [];
  draw();
}

/* ---------- 实例操作 ---------- */
function addInstance(points, cls) {
  pushUndo();
  const inst = { id: uid(), cls, mark: "created",
                 mask: { type: "polygon", points } };
  state.instances.push(inst);
  state.modifiedCount++;
  state.selectedId = inst.id;
  draw();
}
function deleteInstance(id) {
  const inst = state.instances.find(i => i.id === id);
  if (!inst || inst.mark === "deleted") return;
  pushUndo();
  inst.mark = "deleted";            // 保留记录（供 records 导出），渲染时过滤
  state.modifiedCount++;
  if (state.selectedId === id) state.selectedId = null;
  draw();
}
function changeClass(id, cls) {
  const inst = state.instances.find(i => i.id === id);
  if (!inst || inst.cls === cls) return;
  pushUndo();
  inst.cls = cls; inst.mark = inst.mark === "created" ? "created" : "modified";
  state.modifiedCount++;
  draw();
}
function moveInstance(id, dx, dy) {
  const inst = state.instances.find(i => i.id === id);
  if (!inst) return;
  inst.mask.points.forEach(p => { p[0] += dx; p[1] += dy; });
  inst.mark = inst.mark === "created" ? "created" : "modified";
}

/* ---------- 绘制 ---------- */
function draw() {
  resizeCanvases();
  drawOne(ctxMain, true);
  if (document.body.classList.contains("compare")) drawOne(ctxComp, false);
  updateCounter();
}

function resizeCanvases() {
  const w = boxMain.clientWidth, h = boxMain.clientHeight;
  if (cvMain.width !== w) cvMain.width = w;
  if (cvMain.height !== h) cvMain.height = h;
  const wl = boxLeft.clientWidth, hl = boxLeft.clientHeight;
  if (cvComp.width !== wl) cvComp.width = wl;
  if (cvComp.height !== hl) cvComp.height = hl;
}

function drawOne(ctx, withOverlay) {
  const w = ctx.canvas.width, h = ctx.canvas.height;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#0d0e11"; ctx.fillRect(0, 0, w, h);
  if (!state.imgW) return;
  ctx.setTransform(state.scale, 0, 0, state.scale, state.ox, state.oy);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(state.img, 0, 0, state.imgW, state.imgH);
  if (!withOverlay) return;

  const live = state.instances.filter(i => i.mark !== "deleted");

  if (state.mode === "semantic") {
    // 语义：按类合并着色（只读），先压暗原图
    ctx.globalAlpha = 0.35;
    ctx.drawImage(state.img, 0, 0, state.imgW, state.imgH);
    ctx.globalAlpha = 1;
    live.forEach(inst => {
      ctx.beginPath();
      ctx.moveTo(inst.mask.points[0][0], inst.mask.points[0][1]);
      for (let i = 1; i < inst.mask.points.length; i++)
        ctx.lineTo(inst.mask.points[i][0], inst.mask.points[i][1]);
      ctx.closePath();
      ctx.fillStyle = PALETTE[inst.cls];
      ctx.globalAlpha = 0.55; ctx.fill(); ctx.globalAlpha = 1;
    });
  } else if (state.mode === "box") {
    live.forEach(inst => drawBox(ctx, inst, inst.id === state.selectedId));
  } else {
    live.forEach(inst => drawMask(ctx, inst, inst.id === state.selectedId));
  }

  // 工具预览：画笔/橡皮笔触、多边形打点、新建框
  if (state.strokePts.length > 1) {
    ctx.strokeStyle = state.tool === "eraser" ? "#ff5566" : PALETTE[state.curCls];
    ctx.lineWidth = state.brushSize;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(state.strokePts[0][0], state.strokePts[0][1]);
    for (let i = 1; i < state.strokePts.length; i++)
      ctx.lineTo(state.strokePts[i][0], state.strokePts[i][1]);
    ctx.stroke();
  }
  if (state.mode === "mask" && state.pendingPts.length) {
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.5 / state.scale;
    ctx.beginPath();
    ctx.moveTo(state.pendingPts[0][0], state.pendingPts[0][1]);
    for (let i = 1; i < state.pendingPts.length; i++)
      ctx.lineTo(state.pendingPts[i][0], state.pendingPts[i][1]);
    ctx.stroke();
    state.pendingPts.forEach(p => {
      ctx.beginPath(); ctx.arc(p[0], p[1], 3 / state.scale, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff"; ctx.fill();
    });
  }
  if (state.editRect) {
    const r = state.editRect;
    ctx.strokeStyle = PALETTE[state.curCls]; ctx.lineWidth = 2 / state.scale;
    ctx.strokeRect(Math.min(r.x0, r.x1), Math.min(r.y0, r.y1),
                   Math.abs(r.x1 - r.x0), Math.abs(r.y1 - r.y0));
  }
}

function drawBox(ctx, inst, sel) {
  const bb = ptsBBox(inst.mask.points);
  const col = PALETTE[inst.cls];
  // 底层掩码淡显（体现"框=掩码外接矩形"联动）
  ctx.fillStyle = col; ctx.globalAlpha = 0.16;
  ctx.beginPath(); ctx.moveTo(inst.mask.points[0][0], inst.mask.points[0][1]);
  for (let i = 1; i < inst.mask.points.length; i++)
    ctx.lineTo(inst.mask.points[i][0], inst.mask.points[i][1]);
  ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;

  ctx.strokeStyle = sel ? "#ffffff" : col;
  ctx.lineWidth = (sel ? 2.2 : 1.6) / state.scale;
  ctx.strokeRect(bb.x0, bb.y0, bb.x1 - bb.x0, bb.y1 - bb.y0);

  // 类别 + 编号
  ctx.font = `${14 / state.scale}px "Segoe UI", sans-serif`;
  const label = `${CLASSES[inst.cls]} #${state.instances.indexOf(inst)}`;
  const tw = ctx.measureText(label).width;
  const ly = Math.max(bb.y0 - 6 / state.scale, 0);
  ctx.fillStyle = col;
  ctx.fillRect(bb.x0, ly - 14 / state.scale, tw + 8 / state.scale, 18 / state.scale);
  ctx.fillStyle = "#fff";
  ctx.fillText(label, bb.x0 + 4 / state.scale, ly);

  if (sel && isRectPoly(inst)) {
    const hs = 7 / state.scale;
    ctx.fillStyle = "#ffffff"; ctx.strokeStyle = col; ctx.lineWidth = 1.2 / state.scale;
    for (const h of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
      const [hx, hy] = handlePos(bb, h);
      ctx.beginPath(); ctx.rect(hx - hs / 2, hy - hs / 2, hs, hs);
      ctx.fill(); ctx.stroke();
    }
  }
}

function drawMask(ctx, inst, sel) {
  const col = PALETTE[inst.cls];
  ctx.fillStyle = col; ctx.globalAlpha = 0.45;
  ctx.beginPath(); ctx.moveTo(inst.mask.points[0][0], inst.mask.points[0][1]);
  for (let i = 1; i < inst.mask.points.length; i++)
    ctx.lineTo(inst.mask.points[i][0], inst.mask.points[i][1]);
  ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;
  ctx.strokeStyle = sel ? "#ffffff" : col;
  ctx.lineWidth = (sel ? 2.4 : 1.4) / state.scale;
  ctx.stroke();
  if (sel) {
    ctx.font = `${12 / state.scale}px "Segoe UI", sans-serif`;
    const label = `${CLASSES[inst.cls]} #${state.instances.indexOf(inst)}`;
    ctx.fillStyle = "#fff";
    const bb = ptsBBox(inst.mask.points);
    ctx.fillText(label, bb.x0, Math.max(bb.y0 - 4 / state.scale, 12 / state.scale));
  }
}

function updateCounter() {
  cntMod.textContent = state.modifiedCount;
  cntMod.style.color = state.modifiedCount >= 60 ? "#38c98f" : "";
}

/* ---------- 保存 / 导航 ---------- */
async function saveCurrent() {
  const doc = { image: state.name, width: state.imgW, height: state.imgH,
                instances: state.instances, modified_count: state.modifiedCount };
  const r = await fetch("/api/annotation/" + encodeURIComponent(state.name), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
  return r.ok;
}
async function goImage(newIdx) {
  if (newIdx < 0 || newIdx >= state.total) return;
  await saveCurrent();
  window.location.href = "/annotate/" + encodeURIComponent(names[newIdx]);
}
async function saveAndNext() {
  await saveCurrent();
  flashSave();
  goImage(state.idx + 1);
}

/* ---------- 事件：指针 ---------- */
function evPos(e) {
  const r = cvMain.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
function canPan(e) { return state.spaceHeld || e.button === 1; }

cvMain.addEventListener("pointerdown", e => {
  if (e.button !== 0 && e.button !== 1) return;
  const p = evPos(e);
  cvMain.setPointerCapture(e.pointerId);

  if (canPan(e)) { state.dragKind = "pan"; state._panStart = { x: p.x, y: p.y, ox: state.ox, oy: state.oy }; return; }
  if (state.mode === "semantic") return;

  if (state.mode === "box") {
    const hit = hitTestBox(p.x, p.y);
    if (hit) {
      pushUndo();
      state.dragKind = hit.kind; state.dragHandle = hit.handle;
      state.selectedId = hit.inst.id;
      state._moveStart = { x: p.x, y: p.y, inst: hit.inst,
                           pts: hit.inst.mask.points.map(pt => pt.slice()) };
      draw();
    } else {
      state.dragKind = "box-create";
      state._createStart = toImg(p.x, p.y);
      state.editRect = { x0: state._createStart.x, y0: state._createStart.y,
                         x1: state._createStart.x, y1: state._createStart.y };
      state.selectedId = null;
      draw();
    }
    return;
  }

  // mask 模式
  if (state.tool === "brush" || state.tool === "eraser") {
    state.drawing = true;
    state.strokePts = [[...Object.values(toImg(p.x, p.y))]];
  } else if (state.tool === "polygon") {
    const w = toImg(p.x, p.y);
    state.pendingPts.push([w.x, w.y]);
    // 点击靠近首点 → 闭合
    if (state.pendingPts.length > 2) {
      const first = toScreen(...state.pendingPts[0]);
      if (Math.hypot(first.x - p.x, first.y - p.y) <= 10) closePolygon();
    }
    draw();
  } else { // move
    const hit = hitTestMask(p.x, p.y);
    if (hit) {
      pushUndo();
      state.dragKind = "inst-move";
      state.selectedId = hit.id;
      state._moveStart = { x: p.x, y: p.y, inst: hit, pts: hit.mask.points.map(pt => pt.slice()) };
    } else {
      state.dragKind = "pan";
      state._panStart = { x: p.x, y: p.y, ox: state.ox, oy: state.oy };
    }
    draw();
  }
});

cvMain.addEventListener("pointermove", e => {
  const p = evPos(e);
  if (state.dragKind === "pan") {
    state.ox = state._panStart.ox + (p.x - state._panStart.x);
    state.oy = state._panStart.oy + (p.y - state._panStart.y);
    draw(); return;
  }
  if (state.dragKind === "box-create") {
    const w = toImg(p.x, p.y);
    state.editRect.x1 = w.x; state.editRect.y1 = w.y;
    draw(); return;
  }
  if (state.dragKind === "box-resize") {
    const ms = state._moveStart, bb = ptsBBox(ms.pts);
    const w = toImg(p.x, p.y);
    const p0 = ms.inst.mask.points;
    if (state.dragHandle.includes("n")) { p0[0][1] = w.y; p0[3][1] = w.y; }
    if (state.dragHandle.includes("s")) { p0[1][1] = w.y; p0[2][1] = w.y; }
    if (state.dragHandle.includes("w")) { p0[0][0] = w.x; p0[3][0] = w.x; }
    if (state.dragHandle.includes("e")) { p0[1][0] = w.x; p0[2][0] = w.x; }
    // 防止翻转：钳制
    const x0 = Math.min(p0[0][0], p0[1][0]), x1 = Math.max(p0[0][0], p0[1][0]);
    const y0 = Math.min(p0[0][1], p0[3][1]), y1 = Math.max(p0[0][1], p0[3][1]);
    p0[0] = [x0, y0]; p0[1] = [x1, y0]; p0[2] = [x1, y1]; p0[3] = [x0, y1];
    ms.inst.mark = ms.inst.mark === "created" ? "created" : "modified";
    draw(); return;
  }
  if (state.dragKind === "box-move" || state.dragKind === "inst-move") {
    const ms = state._moveStart;
    const w = toImg(p.x, p.y), ws = toImg(ms.x, ms.y);
    moveInstance(ms.inst.id, w.x - ws.x, w.y - ws.y);
    draw(); return;
  }
  if (state.drawing) {
    const w = toImg(p.x, p.y);
    const last = state.strokePts[state.strokePts.length - 1];
    if (Math.hypot(w.x - last[0], w.y - last[1]) >= 3) state.strokePts.push([w.x, w.y]);
    draw(); return;
  }
  if (state.mode === "mask" && state.tool === "polygon") draw();
});

cvMain.addEventListener("pointerup", e => {
  if (state.dragKind === "box-create") {
    const r = state.editRect;
    if (r && Math.abs(r.x1 - r.x0) > 6 / state.scale && Math.abs(r.y1 - r.y0) > 6 / state.scale) {
      const x0 = Math.min(r.x0, r.x1), y0 = Math.min(r.y0, r.y1);
      const x1 = Math.max(r.x0, r.x1), y1 = Math.max(r.y0, r.y1);
      addInstance([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], state.curCls);
    }
    state.editRect = null;
  }
  if (state.drawing) { finalizeStroke(); }
  state.drawing = false; state.dragKind = null; state.dragHandle = null;
  state.strokePts = [];
  draw();
});

function finalizeStroke() {
  if (state.strokePts.length < 2) return;
  const eps = Math.max(2, state.brushSize * 0.3);
  const pts = simplify(state.strokePts, eps);
  if (pts.length < 3) return;
  const start = pts[0];
  const hit = hitTestMask(...toScreen(start[0], start[1]));
  if (state.tool === "eraser") {
    const live = state.instances.filter(i => i.mark !== "deleted");
    const toDel = live.filter(inst => pts.some(p => pointInPoly(p, inst.mask.points)));
    if (toDel.length) {
      pushUndo();
      toDel.forEach(inst => {
        inst.mark = "deleted"; state.modifiedCount++;
        if (state.selectedId === inst.id) state.selectedId = null;
      });
    }
    return;
  }
  // 画笔：从已有实例内部开始 → 合并；否则新建
  if (hit) {
    pushUndo();
    hit.mask.points.push(...pts);
    hit.mark = hit.mark === "created" ? "created" : "modified";
    state.modifiedCount++;
    state.selectedId = hit.id;
  } else {
    addInstance(pts, state.curCls);
  }
}

function closePolygon() {
  if (state.pendingPts.length < 3) { state.pendingPts = []; draw(); return; }
  addInstance(simplify(state.pendingPts, 1.5), state.curCls);
  state.pendingPts = [];
}

/* ---------- 滚轮缩放 ---------- */
cvMain.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  const p = evPos(e);
  zoomAt(factor, p.x, p.y);
  draw();
}, { passive: false });

/* ---------- 键盘 ---------- */
document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") {
    if (e.key === "Escape" && state.pendingPts.length) { state.pendingPts = []; draw(); }
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    return;
  }
  switch (e.key) {
    case "1": setMode("box"); break;
    case "2": setMode("mask"); break;
    case "3": setMode("semantic"); break;
    case "w": case "W": setTool("brush"); break;
    case "e": case "E": setTool("eraser"); break;
    case "p": case "P": setTool("polygon"); break;
    case "v": case "V": setTool("move"); break;
    case "s": case "S": saveAndNext(); break;
    case "Delete": case "Backspace":
      if (state.selectedId) deleteInstance(state.selectedId);
      break;
    case "Escape":
      if (state.pendingPts.length) { state.pendingPts = []; draw(); }
      break;
  }
});
document.addEventListener("keydown", e => {
  if (e.code === "Space" && !e.repeat) state.spaceHeld = true;
});
document.addEventListener("keyup", e => {
  if (e.code === "Space") state.spaceHeld = false;
});
cvMain.addEventListener("dblclick", e => {
  if (state.mode === "mask" && state.tool === "polygon") closePolygon();
});

/* ---------- 模式 / 工具 ---------- */
function setMode(m) {
  state.mode = m;
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.mode === m));
  document.getElementById("maskTools").style.display = m === "mask" ? "flex" : "none";
  legend.hidden = m !== "semantic";
  overlayLabel.textContent = m === "semantic" ? "语义着色（只读）" : "标注叠加";
  state.pendingPts = [];
  draw();
}
function setTool(t) {
  state.tool = t;
  document.querySelectorAll(".tool").forEach(b => b.classList.toggle("active", b.dataset.tool === t));
  state.pendingPts = [];
  draw();
}
document.querySelectorAll(".tab").forEach(b =>
  b.addEventListener("click", () => setMode(b.dataset.mode)));
document.querySelectorAll(".tool").forEach(b =>
  b.addEventListener("click", () => setTool(b.dataset.tool)));

classSel.addEventListener("change", () => {
  const v = parseInt(classSel.value, 10);
  if (state.selectedId) changeClass(state.selectedId, v);
  state.curCls = v;
  draw();
});

document.getElementById("brushSize").addEventListener("input", e => {
  state.brushSize = parseInt(e.target.value, 10);
});
document.getElementById("btnFit").addEventListener("click", () => { fit(); draw(); });
document.getElementById("btnUndo").addEventListener("click", undo);
document.getElementById("btnRedo").addEventListener("click", redo);
document.getElementById("btnSave").addEventListener("click", async () => {
  await saveCurrent();
  flashSave();
});
document.getElementById("btnCompare").addEventListener("click", () => {
  document.body.classList.toggle("compare");
  draw();
});
document.getElementById("btnSaveNext").addEventListener("click", saveAndNext);
document.getElementById("btnSaveNext2").addEventListener("click", saveAndNext);
document.getElementById("btnPrev").addEventListener("click", () => goImage(state.idx - 1));
document.getElementById("btnNext").addEventListener("click", () => goImage(state.idx + 1));

function flashSave() {
  const btn = document.getElementById("btnSave");
  const old = btn.textContent;
  btn.textContent = "✓ 已保存"; btn.style.background = "var(--acc2)";
  setTimeout(() => { btn.textContent = old; btn.style.background = ""; }, 800);
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
  setMode(state.mode);
  // 图片清单（供导航）
  try {
    const r = await fetch("/api/images");
    const d = await r.json();
    names = d.names;
  } catch (_) {}
  // 原图
  const img = new Image();
  img.src = "/image/" + encodeURIComponent(CONF.name);
  await new Promise(res => { img.onload = res; img.onerror = res; });
  state.img = img; state.imgW = img.naturalWidth; state.imgH = img.naturalHeight;
  fit(); draw();
  // 标注 JSON
  try {
    const r = await fetch("/api/annotation/" + encodeURIComponent(CONF.name));
    const doc = await r.json();
    state.instances = doc.instances || [];
    state.modifiedCount = doc.modified_count || 0;
    state.imgW = doc.width || state.imgW;
    state.imgH = doc.height || state.imgH;
    fit(); draw();
  } catch (_) { draw(); }
}

new ResizeObserver(() => draw()).observe(area);
load();
