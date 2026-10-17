# -*- coding: utf-8 -*-
"""
P1 数据获取 · 步骤 A：从 Pascal VOC 2012 中挑选"室内场景"候选图。

来源：VOCtrainval_11-May-2012.tar（PaddleSeg 国内镜像 https://paddleseg.bj.bcebos.com/dataset/，
      官方原始地址 host.robots.ox.ac.uk，本机直连仅 0.03MB/s，故用镜像；内容为官方原包）。

筛选逻辑（全部依据 XML 标注，不靠文件名猜）：
  1. 十类词表中 VOC 覆盖的 7 类：person / chair / dining table / couch / tv / bottle / potted plant
  2. 该图至少含上述 7 类中的一类；
  3. 判定为"室内"：出现"室内强指示物"（家具/家电/厨餐用品），
     且排除明显户外场景（仅在出现 person/plant 这两类弱指示物时作为反证使用）。

产出：
  <raw>/candidates/voc/*.jpg     原始分辨率原图（供后续压缩）
  <raw>/candidates/voc/_meta_voc.json   每张图的文件名、来源、命中类别

用法：
  python tools/extract_voc.py --tar D:\\imglabel_raw\\_download\\VOCtrainval_11-May-2012.tar \
                              --raw D:\\imglabel_raw
"""
import argparse
import io
import json
import os
import sys
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter

# ---- 十类词表（顺序即编号，红线，不得改） ----
CLASSES = ["person", "chair", "dining table", "couch", "tv",
           "laptop", "cup", "bottle", "potted plant", "bed"]

# VOC 2012 中我们需要的 7 类
VOC_NEEDED = {"person", "chair", "dining table", "couch", "tv", "bottle", "potted plant"}

# 室内强指示物：出现任一即基本可判定为室内（VOC 原始标签名）
INDOOR_STRONG = {
    "chair", "dining table", "couch", "tv", "bottle", "potted plant", "bed",
    "sofa", "table",
    # 以下为 VOC 其他标签，用于加强"室内"判定
    "tvmonitor", "diningtable", "pottedplant",
    "bottle", "wine glass", "cup", "knife", "fork", "spoon", "bowl",
    "microwave", "oven", "toaster", "sink", "refrigerator", "clock", "vase",
    "scissors", "teddy bear", "book", "laptop", "keyboard", "mouse", "remote",
}

# 户外强指示物：命中则一票否决（除非同时有家具类强力证据，见 should_keep）
OUTDOOR_HINTS = {
    "car", "bus", "train", "boat", "aeroplane", "bicycle", "motorbike",
    "sheep", "cow", "horse", "bird", "dog", "cat",
    "traffic light", "stop sign", "bench", "umbrella", "fire hydrant",
    "pottedplant",  # 仅作弱信号，下面单独处理
}
OUTDOOR_HARD = OUTDOOR_HINTS - {"pottedplant", "bench", "umbrella"}

# 名称归一（VOC 用 diningtable / pottedplant / tvmonitor，任务书用带空格写法）
# 注意：VOC 中「沙发」的标签名是 sofa，任务书词表写 couch，必须归一到 couch，
#       否则 couch 类会统计为 0（踩过一次坑，勿删）。
VOC_ALIAS = {
    "diningtable": "dining table",
    "pottedplant": "potted plant",
    "tvmonitor": "tv",
    "sofa": "couch",
}


def norm(name: str) -> str:
    n = name.strip().lower()
    return VOC_ALIAS.get(n, n)


def parse_annotations(tar_path):
    """一次性扫完 Annotations 目录，返回 {image_id: set(classes)} 及尺寸。"""
    ann, dims = {}, {}
    with tarfile.open(tar_path, "r") as tf:
        for m in tf:
            if "/Annotations/" not in m.name or not m.name.endswith(".xml"):
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            try:
                root = ET.fromstring(f.read())
            except ET.ParseError:
                continue
            iid = os.path.splitext(os.path.basename(m.name))[0]
            objs = set()
            for o in root.findall("object"):
                nm = o.findtext("name")
                if nm:
                    objs.add(norm(nm))
            size = root.find("size")
            if size is not None:
                try:
                    dims[iid] = (int(size.findtext("width")), int(size.findtext("height")))
                except (TypeError, ValueError):
                    pass
            ann[iid] = objs
    return ann, dims


def should_keep(objs):
    """判定是否作为候选保留。返回 (bool, 命中类别列表, 理由)"""
    hit = sorted(objs & VOC_NEEDED)
    if not hit:
        return False, [], "不含目标类别"
    hard_out = objs & OUTDOOR_HARD
    # 有家具/家电/餐具类强室内证据 -> 判室内（允许图片里同时有人/盆栽）
    strong = objs & INDOOR_STRONG
    if hard_out and not strong:
        return False, hit, "疑似户外(%s)" % ",".join(sorted(hard_out)[:3])
    if not strong:
        # 只剩 person 这类弱指示物，无法确认室内
        return False, hit, "仅弱室内指示(person)"
    return True, hit, "室内(%s)" % ",".join(sorted(strong)[:4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", required=True, help="VOCtrainval_11-May-2012.tar 路径")
    ap.add_argument("--raw", required=True, help="原始图片根目录，如 D:\\imglabel_raw")
    args = ap.parse_args()

    out_dir = os.path.join(args.raw, "candidates", "voc")
    os.makedirs(out_dir, exist_ok=True)

    print("[1/3] 解析标注 ...", flush=True)
    ann, dims = parse_annotations(args.tar)
    print(f"    VOC 共 {len(ann)} 张带标注图片", flush=True)

    keep, reasons = {}, Counter()
    for iid, objs in ann.items():
        ok, hit, why = should_keep(objs)
        if ok:
            keep[iid] = {"classes": hit, "reason": why}
        else:
            reasons[why.split("(")[0]] += 1

    print(f"[2/3] 命中候选 {len(keep)} 张；丢弃统计: {dict(reasons)}", flush=True)

    print("[3/3] 从 tar 中流式提取候选原图（不整包解压）...", flush=True)
    metas, n, failed = [], 0, []
    with tarfile.open(args.tar, "r") as tf:
        for m in tf:
            if "/JPEGImages/" not in m.name or not m.name.lower().endswith(".jpg"):
                continue
            iid = os.path.splitext(os.path.basename(m.name))[0]
            if iid not in keep:
                continue
            f = tf.extractfile(m)
            if f is None:
                failed.append((iid, "tar 读取失败"))
                continue
            dst_name = f"voc_{iid}.jpg"
            try:
                with open(os.path.join(out_dir, dst_name), "wb") as fh:
                    fh.write(f.read())
            except OSError as e:
                failed.append((iid, str(e)))
                continue
            w, h = dims.get(iid, (0, 0))
            metas.append({
                "filename": dst_name,
                "image_id": iid,
                "source": "Pascal VOC 2012",
                "width": w,
                "height": h,
                "hint_classes": keep[iid]["classes"],
            })
            n += 1
            if n % 25 == 0:
                print(f"    ... {n}", flush=True)

    meta_path = os.path.join(out_dir, "_meta_voc.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"source": "Pascal VOC 2012", "count": len(metas),
                   "meta": metas, "failed": failed}, f, ensure_ascii=False, indent=1)

    # 按类别统计
    cls_cnt = Counter()
    for it in metas:
        for c in it["hint_classes"]:
            cls_cnt[c] += 1
    print(f"\n=== VOC 提取完成：{len(metas)} 张 -> {out_dir}")
    print("按类别计数:", dict(cls_cnt))
    if failed:
        print("失败:", failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
