# tools/ 数据流水线（P1）

按顺序执行，即可从零重建 P1 数据。全部用 imglabel 环境的 python 绝对路径跑：

```bash
PY="C:/Users/H/miniforge3/envs/imglabel/python.exe"
```

| 步骤 | 脚本 | 作用 |
|---|---|---|
| 1 | `extract_voc.py` | 从 VOC2012 tar 中按标注流式提取室内场景候选图（不整包解压） |
| 2 | `extract_coco.py` | 从 COCO val parquet 中提取 laptop / cup / bed 候选图 |
| 3 | `compress_images.py` | **交付脚本**：长边≤960 等比缩放、JPG 质量 85，输出 `data/images/` |
| 4 | `make_review.py` | 分层抽样 + 生成候选清单、类别提示、九宫格分批预览 |

## 完整命令

```bash
# 1. VOC（下载包在 D:\imglabel_raw\_download，镜像见下）
$PY tools/extract_voc.py \
    --tar D:/imglabel_raw/_download/VOCtrainval_11-May-2012.tar \
    --raw D:/imglabel_raw

# 2. COCO
$PY tools/extract_coco.py \
    --parquet "D:/imglabel_raw/_download/val-*.parquet" \
    --raw D:/imglabel_raw --per-class 90

# 3. 压缩（任务书规格）
$PY tools/compress_images.py \
    --input D:/imglabel_raw/candidates/voc D:/imglabel_raw/candidates/coco \
    --output data/images

# 4. 生成筛选材料（--pool all 则不抽样，给全部 3478 张）
$PY tools/make_review.py
```

## 下载地址（本机实测可用）

| 数据 | 地址 | 实测速度 |
|---|---|---|
| VOC2012（2GB，官方原包） | `https://paddleseg.bj.bcebos.com/dataset/VOCtrainval_11-May-2012.tar` | 12.8 MB/s |
| COCO val 分片 1 | `https://hf-mirror.com/datasets/detection-datasets/coco/resolve/main/data/val-00000-of-00002-c4f2e391ee4aba11.parquet` | 7.9 MB/s |
| COCO val 分片 2 | `https://hf-mirror.com/datasets/detection-datasets/coco/resolve/main/data/val-00001-of-00002-7af5414a3b178949.parquet` | 7.9 MB/s |

> 官方站 host.robots.ox.ac.uk / cocodataset.org 本机仅 0.03 MB/s；Roboflow 返回 403、GitHub 超时，均不可用。

## 依赖

`Pillow`、`pyarrow`、`requests`（pyarrow 仅 COCO 提取需要）。
装包走阿里云镜像：

```bash
$PY -m pip install pyarrow -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```
