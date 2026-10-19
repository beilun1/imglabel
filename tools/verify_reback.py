# -*- coding: utf-8 -*-
"""P6 回标校验：python tools/verify_reback.py [--ann-dir 回标后目录] [--before 回标前目录或 md5 清单]

1. 非回标图（已过审 / 人工改过）文件字节与回标前完全一致（--before 给出时）
2. 回标图结构：顶层 image/width/height/instances/modified_count=0/source=reback；
   实例 id 唯一、cls 0-9、mark=unchanged、auto=true、0<conf≤1、src=reback、
   mask.type=polygon、≥3 点、坐标在图内、面积 > 0
3. 统计：回标张数、实例数、按类、空图；随机抽 3 张打印
"""
import os
import sys
import json
import random
import hashlib
import argparse
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from prelabel import CLASSES, ANN_DIR  # noqa: E402


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def area(p):
    return abs(sum(p[j][0] * p[i][1] - p[i][0] * p[j][1] for i, j in zip(range(len(p)), range(-1, len(p) - 1)))) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ann-dir", default=ANN_DIR)
    ap.add_argument("--before", help="回标前标注目录副本，或 `md5sum *.json` 清单文件")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.ann_dir) if f.endswith(".json"))
    docs = {}
    for fn in files:
        with open(os.path.join(a.ann_dir, fn), encoding="utf-8") as f:
            docs[fn] = json.load(f)
    reback = [fn for fn, d in docs.items() if d.get("source") == "reback"]
    others = [fn for fn in files if fn not in set(reback)]

    errs = []
    if a.before:
        if os.path.isdir(a.before):
            ref = {fn: md5(os.path.join(a.before, fn)) for fn in os.listdir(a.before) if fn.endswith(".json")}
        else:
            ref = {}
            for line in open(a.before, encoding="utf-8"):
                h, fn = line.split(maxsplit=1)
                ref[os.path.basename(fn.strip().lstrip("*"))] = h
        changed = [fn for fn in others if ref.get(fn) != md5(os.path.join(a.ann_dir, fn))]
        missing = sorted(set(ref) - set(files))
        print(f"[1] 非回标图 {len(others)} 张：字节变化 {len(changed)}，缺失 {len(missing)}")
        errs += [f"{fn}: 非回标图被改动" for fn in changed] + [f"{fn}: 文件缺失" for fn in missing]
        reviewed_changed = [fn for fn in changed if docs[fn].get("reviewed")]
        print(f"    其中已过审 {sum(1 for fn in others if docs[fn].get('reviewed'))} 张，字节变化 {len(reviewed_changed)}")

    by_cls, n_inst, empty = Counter(), 0, []
    for fn in reback:
        d = docs[fn]
        W, H = d.get("width"), d.get("height")
        if d.get("modified_count") != 0 or d.get("reviewed") or not isinstance(W, int) or not isinstance(H, int):
            errs.append(f"{fn}: 顶层字段异常")
        insts = d.get("instances", [])
        if not insts:
            empty.append(d["image"])
        ids = [i.get("id") for i in insts]
        if len(set(ids)) != len(ids):
            errs.append(f"{fn}: 实例 id 重复")
        for i in insts:
            pts = i.get("mask", {}).get("points", [])
            ok = (isinstance(i.get("cls"), int) and 0 <= i["cls"] < len(CLASSES) and i.get("mark") == "unchanged"
                  and i.get("auto") is True and i.get("src") == "reback" and 0 < i.get("conf", 0) <= 1
                  and i.get("mask", {}).get("type") == "polygon" and len(pts) >= 3
                  and all(0 <= x <= W and 0 <= y <= H for x, y in pts) and area(pts) > 0)
            if not ok:
                errs.append(f"{fn}: 实例 {i.get('id')} 非法")
            else:
                by_cls[CLASSES[i["cls"]]] += 1
                n_inst += 1
    print(f"[2] 回标图 {len(reback)} 张 · 合法实例 {n_inst} · 空图 {len(empty)} {empty[:10]}")
    print("    按类：" + " · ".join(f"{c} {by_cls.get(c, 0)}" for c in CLASSES))

    print("[3] 随机抽 3 张：")
    for fn in random.Random(a.seed).sample(reback, min(3, len(reback))):
        d = docs[fn]
        print(f"  {fn}: keys={sorted(d)} · {d['width']}x{d['height']} · 实例 {len(d['instances'])}")
        for i in d["instances"][:2]:
            print(f"    {json.dumps({k: (v if k != 'mask' else {'type': v['type'], 'points': v['points'][:3] + ['…'], 'n': len(v['points'])}) for k, v in i.items()}, ensure_ascii=False)}")

    for e in errs[:20]:
        print("  [错误]", e)
    print("校验" + ("通过" if not errs else f"失败：{len(errs)} 项"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
