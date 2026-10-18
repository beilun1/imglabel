# -*- coding: utf-8 -*-
"""P5 训练：YOLO26n-seg 在平台导出数据集 dataset/ 上微调 → model/best.pt

任务书红线：只接受平台导出数据集。本脚本只读 dataset/（export_dataset.py 的产物），
没有 --data 参数，不读 data/annotations/ 或任何其他格式。

  检测 + 分割一次训练完成（YOLO26n-seg 双头）。ultralytics 的分割训练从多边形派生检测框，
  而 export_dataset 保证 segments 外轮廓的外接矩形 == labels 检测框（tools/verify_export.py [3] 校验），
  所以训练读 dataset/segments/，检测监督与 dataset/labels/ 逐框相同。语义 PNG 只作交付物，不参与训练。

用法：
  python train.py --epochs 1        # 先过一遍数据链路
  python train.py                   # 正式训练（参数按设备自动选择）
"""
import os
import sys
import json
import time
import shutil
import argparse

BASE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE, "dataset")
DATA_YAML = os.path.join(DATASET, "data.yaml")
INIT_WEIGHTS = os.path.join(BASE, "weights", "yolo26n-seg.pt")   # 微调起点（本地权重，不联网下载）
MODEL_DIR = os.path.join(BASE, "model")
RUNS = os.path.join(BASE, "runs", "segment")
CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]  # 顺序即编号，不得改
REPORT_MARK = "<!-- P5-TRAIN -->"

# ADR：按设备自动选参数
# - CPU（本机 16 核、无 CUDA）：nano 模型 640 输入，batch 4 一步约 1s 量级；294 张训练图 30 轮约 1 小时，
#   能收敛出可用 best.pt；batch 再大内存/单步时间涨而收益小。workers 2：CPU 训练算力是瓶颈，多开加载进程反抢核
# - GPU（如 AutoDL 4090）：显存充裕 → batch 16、80 轮，小数据集多轮次靠早停（patience）截断
# - 两者都用 imgsz 640（与 yolo26n-seg 预训练分辨率一致；导出图长边 ≤960）
CPU_CFG = dict(epochs=30, imgsz=640, batch=4, workers=2, patience=15)
GPU_CFG = dict(epochs=80, imgsz=640, batch=16, workers=8, patience=25)
SEED = 42


def use_segments_dir():
    """分割训练读 dataset/segments/ 而非 ultralytics 默认的同级 labels/（labels/ 是检测格式，无多边形）。"""
    from ultralytics.data import dataset as yds
    from ultralytics.data.utils import img2label_paths

    def get_label_files(self):
        self.label_files = img2label_paths(self.im_files, label_dir="segments")
        return self.label_files

    yds.YOLODataset.get_label_files = get_label_files


def check_dataset():
    import yaml
    with open(DATA_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    names = cfg["names"]
    names = [names[i] for i in range(len(names))] if isinstance(names, dict) else list(names)
    if cfg.get("nc") != len(CLASSES) or names != CLASSES:
        sys.exit(f"data.yaml 类别与十类词表不符：{names}")
    for split in ("train", "val"):
        with open(os.path.join(DATASET, cfg[split]), encoding="utf-8") as f:
            imgs = [l.strip() for l in f if l.strip()]
        for p in imgs:
            stem = os.path.splitext(os.path.basename(p))[0]
            for sub, ext in (("images", os.path.splitext(p)[1]), ("segments", ".txt"), ("labels", ".txt")):
                if not os.path.exists(os.path.join(DATASET, sub, stem + ext)):
                    sys.exit(f"{split}: 缺 dataset/{sub}/{stem}{ext}，请先运行 python export_dataset.py")
        print(f"{split}: {len(imgs)} 张")


def metrics_of(m):
    return {"box_map50": float(m.box.map50), "box_map50_95": float(m.box.map),
            "seg_map50": float(m.seg.map50), "seg_map50_95": float(m.seg.map)}


def write_reports(info):
    met = info["metrics"]
    rows = [("检测 mAP50", "box_map50"), ("检测 mAP50-95", "box_map50_95"),
            ("分割 mAP50", "seg_map50"), ("分割 mAP50-95", "seg_map50_95")]
    L = [REPORT_MARK, "## 训练结果（train.py 自动生成）", "",
         f"- 完成时间：{info['time']} · 设备 {info['device']} · 用时 {info['minutes']:.1f} 分钟",
         f"- 起点权重 `weights/yolo26n-seg.pt` · epochs {info['epochs']}（实际 {info['epochs_run']}）· imgsz {info['imgsz']} · "
         f"batch {info['batch']} · workers {info['workers']} · patience {info['patience']} · seed {SEED}",
         f"- 数据：`dataset/data.yaml`（train {info['n_train']} / val {info['n_val']}，分割标签 `dataset/segments/`）",
         f"- 最优权重：`model/best.pt`（来自 `{info['run_dir']}`，第 {info['best_epoch']} 轮）", "",
         "| val 指标（best.pt 重新验证） | 值 |", "|---|---|"]
    L += [f"| {zh} | {met[k]:.4f} |" for zh, k in rows]
    L += ["", "| 类别 | 检测 mAP50-95 | 分割 mAP50-95 |", "|---|---|---|"]
    L += [f"| {c} | {b:.4f} | {s:.4f} |" for c, b, s in info["per_class"]]
    section = "\n".join(L) + "\n"

    rp = os.path.join(DATASET, "export_report.md")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            old = f.read().split(REPORT_MARK)[0].rstrip() + "\n\n"
        with open(rp, "w", encoding="utf-8", newline="\n") as f:
            f.write(old + section)
    with open(os.path.join(MODEL_DIR, "train_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# P5 训练记录\n\n" + section.split("\n", 1)[1])
    with open(os.path.join(MODEL_DIR, "train_metrics.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)


def main():
    import torch
    gpu = torch.cuda.is_available()
    cfg = dict(GPU_CFG if gpu else CPU_CFG)
    ap = argparse.ArgumentParser(description="在 dataset/ 上微调 YOLO26n-seg（不接受其他数据源）")
    for k in ("epochs", "imgsz", "batch", "workers", "patience"):
        ap.add_argument(f"--{k}", type=int, default=cfg[k])
    ap.add_argument("--name", default="p5")
    args = ap.parse_args()
    cfg.update({k: getattr(args, k) for k in cfg})
    device = 0 if gpu else "cpu"
    print(f"设备 {'GPU ' + torch.cuda.get_device_name(0) if gpu else 'CPU'} · 参数 {cfg}")

    check_dataset()
    use_segments_dir()
    from ultralytics import YOLO

    t0 = time.time()
    model = YOLO(INIT_WEIGHTS)
    model.train(data=DATA_YAML, task="segment", device=device, project=RUNS, name=args.name,
                seed=SEED, deterministic=True, plots=True, **cfg)
    run_dir = str(model.trainer.save_dir)
    best = os.path.join(run_dir, "weights", "best.pt")
    os.makedirs(MODEL_DIR, exist_ok=True)
    shutil.copyfile(best, os.path.join(MODEL_DIR, "best.pt"))

    m = YOLO(os.path.join(MODEL_DIR, "best.pt")).val(data=DATA_YAML, split="val", device=device,
                                                    imgsz=cfg["imgsz"], batch=cfg["batch"], plots=False,
                                                    project=RUNS, name=args.name + "_val")
    met = metrics_of(m)
    names = m.names
    per_class = [(names[c], float(m.box.maps[c]), float(m.seg.maps[c])) for c in range(len(CLASSES))]

    import csv
    with open(os.path.join(run_dir, "results.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fit = lambda r: 0.1 * float(r["metrics/mAP50(B)"]) + 0.9 * float(r["metrics/mAP50-95(B)"])  # noqa: E731
    best_epoch = int(float(max(rows, key=fit)["epoch"])) if rows else None

    with open(DATA_YAML, encoding="utf-8") as f:
        import yaml
        dcfg = yaml.safe_load(f)
    count = lambda s: sum(1 for l in open(os.path.join(DATASET, dcfg[s]), encoding="utf-8") if l.strip())  # noqa: E731
    info = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "device": "GPU" if gpu else "CPU",
            "minutes": (time.time() - t0) / 60, "epochs_run": len(rows), "run_dir": os.path.relpath(run_dir, BASE),
            "best_epoch": best_epoch, "n_train": count("train"), "n_val": count("val"),
            "metrics": met, "per_class": per_class, **cfg}
    write_reports(info)
    print("\nval 指标（model/best.pt）：")
    for k, v in met.items():
        print(f"  {k}: {v:.4f}")
    print(f"model/best.pt ← {best}")


if __name__ == "__main__":
    main()
