# -*- coding: utf-8 -*-
"""人机协同图像标注系统 - Flask 主程序（P2：UI 骨架 + 画布三模式；P3：预标注后台任务）

数据流：画布编辑 → 每图一个 JSON（data/annotations/{图名}.json）
        → P5 从这里导出三种格式（YOLO txt / 实例掩码 / 语义 PNG）
"""
import os
import re
import sys
import json
import time
import socket
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "data", "curated", "images")
ANN_DIR = os.path.join(BASE, "data", "annotations")
REC_DIR = os.path.join(BASE, "data", "records")
REC_PATH = os.path.join(REC_DIR, "修正记录.json")
CANVAS_DIR = os.path.join(BASE, "canvas")

# 十类词表：顺序即类别编号，红线不可改
CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]

PORT = 5000

# 修正轮次：0 = R0 人工过审（默认）；P6 回标时以 IMGLABEL_ROUND=1 启动服务
ROUND = int(os.environ.get("IMGLABEL_ROUND", "0"))
TARGET = 60
REC_TYPES = {"create", "modify", "delete", "move", "resize", "reclass",
             "add_mask", "erase_mask", "polygon"}
_rec_lock = threading.Lock()

app = Flask(__name__)
# 非 debug 模式下 Jinja 默认缓存模板：改了 templates/ 不重启就会"新 JS + 旧模板"
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.after_request
def no_cache(resp):
    """开发阶段：页面与前端资源禁用缓存，改完代码普通刷新即可生效"""
    p = request.path
    if p == "/" or p.startswith("/canvas/") or p.startswith("/annotate/"):
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


def list_images():
    """返回 data/curated/images 下全部图片文件名（按文件名排序）"""
    names = [f for f in sorted(os.listdir(IMG_DIR))
             if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    return names


def ann_path(name):
    """图片名 → 标注 JSON 路径（{图名}.json，与图片同名不同扩展）"""
    return os.path.join(ANN_DIR, os.path.splitext(name)[0] + ".json")


def safe_name(name):
    """防路径穿越：只取 basename 且必须在图片目录中存在，否则返回 None"""
    name = os.path.basename(name or "")
    if not name or not os.path.exists(os.path.join(IMG_DIR, name)):
        return None
    return name


def load_ann(name):
    """读标注 JSON；不存在返回空标注"""
    p = ann_path(name)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"image": name, "width": None, "height": None,
            "instances": [], "modified_count": 0}


def ann_status(name):
    """列表页状态标记：未标（无 JSON）/ 已过审（显式保存过）/ 预标（模型草稿，未经人工保存）/ 已修改 / 已标 / 已标(空)"""
    p = ann_path(name)
    if not os.path.exists(p):
        return "未标"
    doc = load_ann(name)
    if doc.get("reviewed"):
        return "已过审"
    live = [x for x in doc.get("instances", []) if x.get("mark") != "deleted"]
    if doc.get("modified_count", 0) > 0:
        return "已修改"
    if doc.get("source") == "prelabel":   # 画布保存时不带 source，人工保存过即不再是"预标"
        return "预标"
    if live:
        return "已标"
    return "已标(空)"


# ---------- P4 修正记录：data/records/修正记录.json ----------
def write_json_atomic(path, obj, indent=1):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def load_records():
    if not os.path.exists(REC_PATH):
        return []
    with open(REC_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def clean_records(raw, name, session):
    """校验画布上报的记录；image / round / session 一律以服务端为准"""
    if not isinstance(raw, list):
        raise ValueError("records 必须是数组")
    out = []
    ncls = len(CLASSES)
    for i, r in enumerate(raw):
        if not isinstance(r, dict) or r.get("type") not in REC_TYPES:
            raise ValueError(f"第 {i} 条记录 type 非法")
        subj = r.get("subject")
        if not isinstance(subj, str) or not _ID_RE.fullmatch(subj):
            raise ValueError(f"第 {i} 条记录 subject 非法")
        cls = {}
        for k in ("cls_before", "cls_after"):
            v = r.get(k)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < ncls):
                raise ValueError(f"第 {i} 条记录 {k} 非法")
            cls[k] = v
        t = r.get("time")
        rec = {"image": name,
               "time": t if isinstance(t, str) and _TIME_RE.fullmatch(t) else time.strftime("%Y-%m-%d %H:%M:%S"),
               "type": r["type"], "subject": subj, **cls,
               "auto": bool(r.get("auto")), "round": ROUND, "session": session, "seq": i}
        if r.get("tool") in ("eraser", "brush"):
            rec["tool"] = r["tool"]
        if isinstance(r.get("split_from"), str) and _ID_RE.fullmatch(r["split_from"]):
            rec["split_from"] = r["split_from"]
        out.append(rec)
    return out


def update_stats(records):
    tools_dir = os.path.join(BASE, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import records_stats
        records_stats.write_stats(CLASSES, ROUND, REC_DIR, ANN_DIR, records=records)
    except Exception as e:                  # 统计失败不能让保存失败，可再用 tools/records_stats.py 重跑
        print(f"[警告] 修正统计生成失败：{type(e).__name__}: {e}")


# ---------- P3 预标注：后台线程 + 状态轮询 ----------
PRELABEL = {"running": False, "phase": "idle", "done": 0, "total": 0, "current_file": None,
            "created": 0, "skipped": 0, "instances": 0, "errors": [],
            "started_at": None, "finished_at": None}
_prelabel_lock = threading.Lock()


def _prelabel_worker(conf):
    def on_progress(event, **s):
        with _prelabel_lock:
            PRELABEL.update({k: s[k] for k in ("done", "total", "created", "skipped", "instances")})
            PRELABEL["errors"] = list(s["errors"])
            PRELABEL["current_file"] = s.get("current_file")
            PRELABEL["phase"] = {"loading": "loading", "done": "done"}.get(event, "running")
    try:
        import prelabel                     # 延迟导入：ultralytics 很重，不拖慢服务启动
        prelabel.run(conf=conf, on_progress=on_progress)
    except Exception as e:
        with _prelabel_lock:
            PRELABEL["errors"].append(f"{type(e).__name__}: {e}")
            PRELABEL["phase"] = "failed"
    finally:
        with _prelabel_lock:
            PRELABEL["running"] = False
            PRELABEL["current_file"] = None
            PRELABEL["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


@app.route("/api/prelabel", methods=["POST"])
def api_prelabel_start():
    body = request.get_json(force=True, silent=True) or {}
    try:
        conf = float(body.get("conf", 0.25))
    except (TypeError, ValueError):
        conf = 0.25
    conf = min(max(conf, 0.01), 0.99)
    with _prelabel_lock:
        if PRELABEL["running"]:
            return jsonify({"ok": False, "msg": "预标注运行中，请等待完成", **PRELABEL}), 409
        PRELABEL.update({"running": True, "phase": "loading", "done": 0, "total": len(list_images()),
                         "current_file": None, "created": 0, "skipped": 0, "instances": 0,
                         "errors": [], "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                         "finished_at": None})
        snap = dict(PRELABEL)
    threading.Thread(target=_prelabel_worker, args=(conf,), daemon=True).start()
    return jsonify({"ok": True, **snap})


@app.route("/api/prelabel/status")
def api_prelabel_status():
    with _prelabel_lock:
        return jsonify(dict(PRELABEL, errors=list(PRELABEL["errors"])))


@app.route("/")
def index():
    """列表页：全部图片 + 缩略图 + 状态标记"""
    names = list_images()
    items = []
    for i, n in enumerate(names):
        try:
            status = ann_status(n)
        except Exception:
            status = "异常"
        items.append({"name": n, "status": status})
    try:
        rec_total = sum(1 for r in load_records() if r.get("round", 0) == ROUND)
    except Exception:
        rec_total = 0
    return render_template("index.html", items=items, total=len(names),
                           reviewed=sum(1 for it in items if it["status"] == "已过审"),
                           rec_total=rec_total, target=TARGET)


@app.route("/annotate/<name>")
def annotate(name):
    """标注页（画布）"""
    name = safe_name(name)
    if name is None:
        abort(404)
    names = list_images()
    try:
        idx = names.index(name)
    except ValueError:
        abort(404)
    return render_template("annotate.html", name=name, idx=idx,
                           total=len(names), classes=CLASSES, round=ROUND, target=TARGET)


@app.route("/api/images")
def api_images():
    """列表页/导航用的图片清单与标注状态（避免重复读盘）"""
    names = list_images()
    ann = {}
    for n in names:
        try:
            ann[n] = {"status": ann_status(n)}
        except Exception:
            ann[n] = {"status": "异常"}
    return jsonify({"names": names, "annotations": ann})


@app.route("/api/annotation/<name>", methods=["GET"])
def get_annotation(name):
    name = safe_name(name)
    if name is None:
        abort(404)
    return jsonify(load_ann(name))


@app.route("/api/annotation/<name>", methods=["POST"])
def save_annotation(name):
    """保存画布 JSON，并把本会话修正记录同步落盘到 data/records/修正记录.json。

    同一会话（session）每次保存整体替换该会话的旧记录：保存后又撤销再保存，
    记录随之回退，始终与 JSON 的 mark / modified_count 一致。"""
    name = safe_name(name)
    if name is None:
        abort(404)
    doc = request.get_json(force=True, silent=True)
    if not isinstance(doc, dict):
        abort(400)
    session = doc.pop("session", None)
    raw_recs = doc.pop("records", None)
    review = bool(doc.pop("review", False))
    if raw_recs is not None:
        if not isinstance(session, str) or not _ID_RE.fullmatch(session):
            return jsonify({"ok": False, "msg": "session 非法"}), 400
        try:
            recs = clean_records(raw_recs, name, session)
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400

    with _rec_lock:
        old = load_ann(name) if os.path.exists(ann_path(name)) else {}
        # 保留预标来源元数据与过审状态；source 照旧丢弃（人工保存后不再是"预标"）
        for k in ("prelabel", "reviewed", "reviewed_at"):
            if k in old and k not in doc:
                doc[k] = old[k]
        doc["image"] = name
        doc.setdefault("width", None)
        doc.setdefault("height", None)
        doc.setdefault("instances", [])
        doc.setdefault("modified_count", 0)
        doc["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if review:
            doc["reviewed"] = True
            doc["reviewed_at"] = doc["updated_at"]
        os.makedirs(ANN_DIR, exist_ok=True)
        write_json_atomic(ann_path(name), doc)

        records = load_records()
        changed = False
        if raw_recs is not None:
            kept = [r for r in records if not (r.get("session") == session and r.get("image") == name)]
            if recs or len(kept) != len(records):
                records = kept + recs
                os.makedirs(REC_DIR, exist_ok=True)
                write_json_atomic(REC_PATH, records)
                changed = True
        if changed or review:
            update_stats(records)
        round_total = sum(1 for r in records if r.get("round", 0) == ROUND)
    return jsonify({"ok": True, "round_total": round_total, "reviewed": bool(doc.get("reviewed"))})


@app.route("/api/records/summary")
def records_summary():
    """累计修正进度（画布计数条 / 列表页用）"""
    with _rec_lock:
        records = load_records()
    rr = [r for r in records if r.get("round", 0) == ROUND]
    return jsonify({"round": ROUND, "total": len(rr), "target": TARGET,
                    "images": len({r["image"] for r in rr}), "all_rounds": len(records)})


@app.route("/image/<path:name>")
def image(name):
    """原图直出（列表页缩略图直接复用，靠 CSS 缩放 + lazy 加载）"""
    name = safe_name(name)
    if name is None:
        abort(404)
    return send_from_directory(IMG_DIR, name)


@app.route("/canvas/<path:fn>")
def canvas_static(fn):
    """前端 JS/CSS（提交包结构要求 canvas/ 在源码根）"""
    fn = os.path.basename(fn)
    return send_from_directory(CANVAS_DIR, fn)


def port_in_use(port):
    """Windows 上 Werkzeug 用 SO_REUSEADDR，旧服务没关时新服务也能"启动成功"，
    但请求仍被旧进程接走，所以启动前主动探测"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    os.makedirs(ANN_DIR, exist_ok=True)
    if port_in_use(PORT):
        print(f"[错误] 端口 {PORT} 已被占用——很可能是之前打开的标注服务窗口还没关。")
        print("       请先关闭旧的服务窗口（或在任务管理器结束旧的 python.exe），再重新启动。")
        sys.exit(1)
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
