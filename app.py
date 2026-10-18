# -*- coding: utf-8 -*-
"""人机协同图像标注系统 - Flask 主程序（P2：UI 骨架 + 画布三模式；P3：预标注后台任务）

数据流：画布编辑 → 每图一个 JSON（data/annotations/{图名}.json）
        → P5 从这里导出三种格式（YOLO txt / 实例掩码 / 语义 PNG）
"""
import os
import sys
import json
import time
import socket
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "data", "curated", "images")
ANN_DIR = os.path.join(BASE, "data", "annotations")
CANVAS_DIR = os.path.join(BASE, "canvas")

# 十类词表：顺序即类别编号，红线不可改
CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]

PORT = 5000

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
    """列表页状态标记：未标（无 JSON）/ 预标（模型草稿，未经人工保存）/ 已修改 / 已标 / 已标(空)"""
    p = ann_path(name)
    if not os.path.exists(p):
        return "未标"
    doc = load_ann(name)
    live = [x for x in doc.get("instances", []) if x.get("mark") != "deleted"]
    if doc.get("modified_count", 0) > 0:
        return "已修改"
    if doc.get("source") == "prelabel":   # 画布保存时不带 source，人工保存过即不再是"预标"
        return "预标"
    if live:
        return "已标"
    return "已标(空)"


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
    return render_template("index.html", items=items, total=len(names))


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
                           total=len(names), classes=CLASSES)


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
    name = safe_name(name)
    if name is None:
        abort(404)
    doc = request.get_json(force=True, silent=True)
    if not isinstance(doc, dict):
        abort(400)
    doc["image"] = name
    doc.setdefault("width", None)
    doc.setdefault("height", None)
    doc.setdefault("instances", [])
    doc.setdefault("modified_count", 0)
    doc["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(ANN_DIR, exist_ok=True)
    with open(ann_path(name), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return jsonify({"ok": True})


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
