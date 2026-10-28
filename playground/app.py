import sys

sys.dont_write_bytecode = True

import copy
import io
import json
import math
import os
import threading
import uuid
import warnings
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
UPLOADS = BASE / "uploads"
RESULTS = BASE / "_tmp_results"
CACHE = RESULTS / "cache"
for directory in (UPLOADS, RESULTS, CACHE):
    directory.mkdir(parents=True, exist_ok=True)

for key, subdir in {
    "YOLO_CONFIG_DIR": "ultralytics",
    "TORCH_HOME": "torch",
    "XDG_CACHE_HOME": "xdg",
    "MPLCONFIGDIR": "matplotlib",
    "TEMP": "temp",
    "TMP": "temp",
    "TMPDIR": "temp",
}.items():
    path = CACHE / subdir
    path.mkdir(exist_ok=True)
    os.environ[key] = str(path)
os.environ["YOLO_AUTOINSTALL"] = "false"


def _protect_project(event, args):
    if event == "open":
        path, mode, flags = args
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if not writing:
            return
        paths = (path,)
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
        paths = args[:1]
    elif event in {"os.rename", "os.link", "os.symlink"}:
        paths = args[:2]
    else:
        return
    for path in paths:
        if not isinstance(path, (str, bytes, os.PathLike)):
            continue
        target = Path(os.fsdecode(path)).resolve()
        if target.is_relative_to(PROJECT) and not target.is_relative_to(BASE):
            raise PermissionError("演示台禁止写入主项目：" + str(target))


# prelabel 的绝对图片路径会绕过 ANN_DIR，除路径重定向外再禁止主项目写操作。
sys.addaudithook(_protect_project)

from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

# Ultralytics 会替换 Image.open，损坏图片不应触发其可选 HEIF 依赖加载。
_open_image = Image.open

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000

_tasks = {}
_tasks_lock = threading.Lock()
_inference_lock = threading.Lock()
_r1_model = None


def _snapshot(task_id):
    with _tasks_lock:
        return copy.deepcopy(_tasks.get(task_id))


def _update(task_id, **values):
    with _tasks_lock:
        _tasks[task_id].update(values)


def _inference_modules():
    if str(PROJECT) not in sys.path:
        sys.path.append(str(PROJECT))
    import prelabel
    import reback
    return prelabel, reback


def _result(image, width, height, instances, classes, model):
    output = []
    for index, instance in enumerate(instances):
        points = instance["mask"]["points"]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        area = abs(sum(
            points[j][0] * points[i][1] - points[i][0] * points[j][1]
            for i, j in zip(range(len(points)), range(-1, len(points) - 1))
        )) / 2
        cls = instance["cls"]
        output.append({
            "id": f"p{index}" if model == "R0" else f"r1{index}",
            "cls": cls, "cls_name": classes[cls], "conf": instance["conf"],
            "bbox": [min(xs), min(ys), max(xs), max(ys)], "mask": points,
            "area": round(area, 1), "src": instance.get("src", "seg"),
        })
    return {"image": image["filename"], "name": image["name"],
            "width": width, "height": height, "instances": output}


def _run_r0(task_id, images, conf, prelabel):
    required = (Path(prelabel.SEG_WEIGHT), Path(prelabel.WORLD_WEIGHT),
                Path(prelabel.WEIGHTS) / "clip" / "ViT-B-32.pt")
    for weight in required:
        if not weight.is_file():
            raise FileNotFoundError(f"缺少只读模型文件：{weight}；演示台不会自动下载权重")
    output_dir = RESULTS / task_id / uuid.uuid4().hex
    output_dir.mkdir(parents=True)
    originals = (prelabel.IMG_DIR, prelabel.ANN_DIR, prelabel.ann_path)
    prelabel.IMG_DIR = str(UPLOADS)
    prelabel.ANN_DIR = str(output_dir)
    prelabel.ann_path = lambda name: str(output_dir / (Path(name).stem + ".json"))

    def on_progress(event, **stats):
        count = stats["done"]
        completed = []
        for image in images[:count]:
            path = output_dir / (Path(image["filename"]).stem + ".json")
            if path.exists():
                doc = json.loads(path.read_text(encoding="utf-8"))
                completed.append(_result(image, doc["width"], doc["height"],
                                         doc["instances"], prelabel.CLASSES, "R0"))
            else:
                completed.append({"image": image["filename"], "name": image["name"],
                                  "width": image["width"], "height": image["height"],
                                  "instances": [], "error": "该图片推理失败，请查看任务错误"})
        _update(task_id, phase="loading" if event == "loading" else "image",
                results=completed, errors=list(stats["errors"]),
                progress={"done": count, "total": len(images),
                          "current_file": images[count]["name"] if count < len(images) else None})

    try:
        prelabel.run(names=[str(UPLOADS / image["filename"]) for image in images],
                     conf=conf, on_progress=on_progress)
    finally:
        prelabel.IMG_DIR, prelabel.ANN_DIR, prelabel.ann_path = originals


def _run_r1(task_id, images, conf, prelabel, reback):
    global _r1_model
    if _r1_model is None:
        _r1_model = reback.load_model()
        _r1_model.overrides.update(save=False, save_txt=False, project=str(CACHE / "predict"))
    completed, errors = [], []
    for index, image in enumerate(images):
        _update(task_id, phase="image", progress={"done": index, "total": len(images),
                                                 "current_file": image["name"]})
        try:
            width, height, instances, _ = reback.reback_image(
                _r1_model, str(UPLOADS / image["filename"]), conf)
            completed.append(_result(image, width, height, instances, prelabel.CLASSES, "R1"))
        except Exception as error:
            message = f"{image['name']}: {type(error).__name__}: {error}"
            errors.append(message)
            completed.append({"image": image["filename"], "name": image["name"],
                              "width": image["width"], "height": image["height"],
                              "instances": [], "error": message})
        _update(task_id, results=list(completed), errors=list(errors),
                progress={"done": index + 1, "total": len(images), "current_file": None})


def _detect_worker(task_id, images, model, conf):
    try:
        with _inference_lock:
            _update(task_id, phase="loading")
            prelabel, reback = _inference_modules()
            if model == "R0":
                _run_r0(task_id, images, conf, prelabel)
            else:
                _run_r1(task_id, images, conf, prelabel, reback)
    except Exception as error:
        _update(task_id, errors=[f"{type(error).__name__}: {error}"])
    finally:
        _update(task_id, status="done", phase="done",
                progress={"done": len(images), "total": len(images), "current_file": None})


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.before_request
def check_origin():
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(msg="不接受跨站请求"), 403


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(error):
    return jsonify(msg="上传总大小不能超过 32 MB"), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/upload")
def upload():
    files = request.files.getlist("files")
    if not 1 <= len(files) <= 20:
        return jsonify(msg="请选择 1–20 张图片"), 400
    with _tasks_lock:
        if len(_tasks) >= 100:
            return jsonify(msg="演示任务已达上限，请重启演示台后继续"), 429
    images, saved = [], []
    try:
        for uploaded in files:
            name = (uploaded.filename or "图片").replace("\\", "/").rsplit("/", 1)[-1][:200]
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with _open_image(io.BytesIO(uploaded.read())) as original:
                    if original.format not in {"JPEG", "PNG", "WEBP", "BMP"}:
                        raise ValueError("仅支持 JPG、PNG、WebP、BMP 静态图片")
                    if original.width * original.height > Image.MAX_IMAGE_PIXELS:
                        raise ValueError("图片不能超过 2000 万像素")
                    normalized = ImageOps.exif_transpose(original).convert("RGB")
                    width, height = normalized.size
            filename = uuid.uuid4().hex + ".jpg"
            target = UPLOADS / filename
            saved.append(target)
            normalized.save(target, format="JPEG", quality=95)
            images.append({"filename": filename, "name": name,
                           "url": "/uploads/" + filename, "width": width, "height": height})
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        for path in saved:
            path.unlink(missing_ok=True)
        return jsonify(msg=f"图片无法读取：{error}"), 400
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {"task_id": task_id, "status": "pending", "phase": "queued",
                           "images": images, "results": [], "errors": [],
                           "progress": {"done": 0, "total": len(images), "current_file": None},
                           "model": None, "conf": None}
    return jsonify(task_id=task_id, images=images), 201


@app.post("/api/detect")
def detect():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(msg="请求必须为 JSON 对象"), 400
    task_id, model = body.get("task_id"), body.get("model", "R0")
    conf_value = body.get("conf", 0.25)
    try:
        if isinstance(conf_value, bool):
            raise ValueError
        conf = float(conf_value)
        if not math.isfinite(conf) or not 0.05 <= conf <= 0.9:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return jsonify(msg="置信度阈值须为 0.05–0.9"), 400
    if not isinstance(task_id, str) or model not in ("R0", "R1"):
        return jsonify(msg="任务编号或模型参数无效"), 400
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return jsonify(msg="任务不存在，请重新上传"), 404
        if task["status"] == "running":
            return jsonify(msg="该任务正在检测"), 409
        images = copy.deepcopy(task["images"])
        task.update(status="running", phase="queued", results=[], errors=[], model=model, conf=conf,
                    progress={"done": 0, "total": len(images), "current_file": None})
        snapshot = copy.deepcopy(task)
    threading.Thread(target=_detect_worker, args=(task_id, images, model, conf), daemon=True).start()
    return jsonify(snapshot), 202


@app.get("/api/progress/<task_id>")
def progress(task_id):
    snapshot = _snapshot(task_id)
    if snapshot is None:
        return jsonify(msg="任务不存在"), 404
    return jsonify(snapshot)


@app.get("/uploads/<filename>")
def uploaded_image(filename):
    if len(filename) != 36 or not filename.endswith(".jpg"):
        return jsonify(msg="图片不存在"), 404
    try:
        uuid.UUID(filename[:-4])
    except ValueError:
        return jsonify(msg="图片不存在"), 404
    return send_from_directory(UPLOADS, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=False)
