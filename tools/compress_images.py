# -*- coding: utf-8 -*-
"""
P1 · 图片压缩脚本（任务书二(二)3 规格：室内场景照片，长边 ≤960px，JPG 质量 85）

功能：
  1. 从原始候选目录读取图片，按长边 960 等比缩放（只缩不放）；
  2. 统一转 RGB 后以 JPG 质量 85 保存，剥离 EXIF 等元数据（减小体积、避免方向错乱）；
  3. 输出到项目内 data/images/（注意：不是 dataset/ —— dataset/ 是平台导出的
     三种标注格式目录，图片与标注必须分开存放）；
  4. 生成处理报告：处理前/后张数、尺寸变化、失败清单（data/images/_compress_report.md + .json）。

用法：
  # 处理全部（VOC + COCO 候选）
  python tools/compress_images.py \
      --input D:/imglabel_raw/candidates/voc D:/imglabel_raw/candidates/coco \
      --output data/images

  # 只处理指定清单（用户筛选后重跑时用）
  python tools/compress_images.py --input D:/imglabel_raw/candidates/voc --output data/images \
      --only-file data/review/keep_list.txt
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

from PIL import Image, ImageOps

MAX_SIDE = 960          # 长边上限（任务书：不超过 960 像素）
JPG_QUALITY = 85        # 任务书：质量 85
EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def iter_images(paths):
    for p in paths:
        if os.path.isfile(p):
            if p.lower().endswith(EXTS):
                yield p
            continue
        for root, _dirs, files in os.walk(p):
            for fn in sorted(files):
                if fn.lower().endswith(EXTS):
                    yield os.path.join(root, fn)


def fit_long_side(w, h, max_side=MAX_SIDE):
    """长边缩到 max_side（等比、只缩不放），返回 (new_w, new_h)"""
    long_side = max(w, h)
    if long_side <= max_side:
        return w, h
    scale = max_side / float(long_side)
    return max(1, round(w * scale)), max(1, round(h * scale))


def process_one(src, dst):
    """返回 (ok, info_dict)"""
    with Image.open(src) as im:
        # 按 EXIF 方向摆正（手机拍摄的图常见）
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        ow, oh = im.size
        nw, nh = fit_long_side(ow, oh)
        if (nw, nh) != (ow, oh):
            im = im.resize((nw, nh), Image.LANCZOS)
        # 统一 RGB（PNG 可能带 alpha、灰度、调色板）
        if im.mode != "RGB":
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, "JPEG", quality=JPG_QUALITY, optimize=True, progressive=True)
    return True, {"orig_w": ow, "orig_h": oh, "new_w": nw, "new_h": nh}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", required=True, help="原始图片目录/文件")
    ap.add_argument("--output", default="data/images", help="输出目录")
    ap.add_argument("--only-file", default=None,
                    help="可选：只处理该清单中列出的文件名（每行一个）")
    ap.add_argument("--flat", action="store_true", default=True,
                    help="扁平输出到 output 根目录（默认开启）")
    args = ap.parse_args()

    only = None
    if args.only_file:
        with open(args.only_file, encoding="utf-8") as f:
            only = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}

    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    srcs = list(iter_images(args.input))
    if only is not None:
        srcs = [s for s in srcs if os.path.basename(s) in only]
    total = len(srcs)
    print(f"[输入] 待处理 {total} 张 -> {out_dir}", flush=True)

    records, failed, dup = [], [], []
    seen_names = {}
    scaled = unchanged = 0
    bytes_in = bytes_out = 0

    for i, src in enumerate(srcs, 1):
        base = os.path.basename(src)
        stem, _ = os.path.splitext(base)
        dst_name = stem + ".jpg"
        # 同名冲突（不同来源目录同名文件）加后缀，绝不覆盖
        if dst_name in seen_names:
            k = 2
            while f"{stem}_{k}.jpg" in seen_names:
                k += 1
            dst_name = f"{stem}_{k}.jpg"
            dup.append((src, seen_names[stem + ".jpg"], dst_name))
        seen_names[dst_name] = src
        dst = os.path.join(out_dir, dst_name)

        try:
            ok, info = process_one(src, dst)
        except Exception as e:
            failed.append({"file": src, "error": f"{type(e).__name__}: {e}"})
            print(f"  [失败] {base}: {e}", flush=True)
            continue

        if (info["new_w"], info["new_h"]) != (info["orig_w"], info["orig_h"]):
            scaled += 1
        else:
            unchanged += 1
        bytes_in += os.path.getsize(src)
        bytes_out += os.path.getsize(dst)
        records.append({"filename": dst_name, "source_path": src.replace("\\", "/"),
                        **info, "size_kb": round(os.path.getsize(dst) / 1024, 1)})
        if i % 100 == 0 or i == total:
            print(f"  ... {i}/{total}", flush=True)

    ok_n = len(records)
    dur = time.time() - t0

    # 校验：确认没有超规格的图
    over = [r for r in records if max(r["new_w"], r["new_h"]) > MAX_SIDE]

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spec": {"max_long_side": MAX_SIDE, "jpg_quality": JPG_QUALITY, "format": "JPG"},
        "input_count": total,
        "output_count": ok_n,
        "failed_count": len(failed),
        "resized_count": scaled,
        "unchanged_size_count": unchanged,
        "over_limit_count": len(over),
        "total_bytes_in": bytes_in,
        "total_bytes_out": bytes_out,
        "output_dir": out_dir,
        "elapsed_sec": round(dur, 1),
        "failed": failed,
        "records": records,
    }

    json_path = os.path.join(out_dir, "_compress_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    md_path = os.path.join(out_dir, "_compress_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# P1 图片压缩处理报告\n\n")
        f.write(f"- 生成时间：{summary['generated_at']}\n")
        f.write(f"- 规格：长边 ≤{MAX_SIDE}px（等比）、JPG 质量 {JPG_QUALITY}\n")
        f.write(f"- 输出目录：`{out_dir}`\n")
        f.write(f"- 耗时：{dur:.1f} 秒\n\n")
        f.write("## 张数统计\n\n| 项目 | 数量 |\n|---|---|\n")
        f.write(f"| 处理前（输入） | {total} |\n")
        f.write(f"| 处理后（成功输出） | {ok_n} |\n")
        f.write(f"| 其中：发生缩放 | {scaled} |\n")
        f.write(f"| 其中：原图已达标未缩放 | {unchanged} |\n")
        f.write(f"| 失败 | {len(failed)} |\n")
        f.write(f"| 超规格（> {MAX_SIDE}px） | {len(over)} |\n\n")
        f.write(f"体积：{bytes_in/1048576:.1f} MB → {bytes_out/1048576:.1f} MB\n\n")
        f.write("## 失败清单\n\n")
        if failed:
            f.write("| 文件 | 原因 |\n|---|---|\n")
            for it in failed:
                f.write(f"| `{it['file']}` | {it['error']} |\n")
        else:
            f.write("无。全部图片处理成功。\n")
        if dup:
            f.write("\n## 重名处理\n\n| 源文件 | 原同名文件 | 改名 |\n|---|---|---|\n")
            for s, o, d in dup:
                f.write(f"| `{s}` | `{o}` | `{d}` |\n")

    print(f"\n=== 完成：输入 {total} / 输出 {ok_n} / 失败 {len(failed)} / 超规格 {len(over)}")
    print(f"报告：{md_path}")
    return 0 if not failed and not over else 0


if __name__ == "__main__":
    sys.exit(main())
