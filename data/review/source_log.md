# P1 数据获取过程记录（原始事实）

> 本文件是 P1 数据来源的一手记录，后续写入 `提交信息.txt` 的数字必须以此为唯一依据，不得改动。
> 生成时间：2026-10-17

## 一、通道选择（含踩坑，如实记录）

| 数据源 | 任务书给定地址 | 本机实测 | 结论 |
|---|---|---|---|
| Pascal VOC 2012 | host.robots.ox.ac.uk（官方包 2GB） | 可连，但下载 0.03 MB/s（需十余小时） | 改用 **PaddleSeg 百度云镜像** `https://paddleseg.bj.bcebos.com/dataset/VOCtrainval_11-May-2012.tar`，12.8 MB/s，2GB 用时 2m36s。文件为官方原包（解包后为 `VOCdevkit/VOC2012/`） |
| COCO 2017 | cocodataset.org | 同上 0.03 MB/s（val2017 815MB） | 改用 **HuggingFace 国内镜像 hf-mirror.com** 的 `detection-datasets/coco`，7.9 MB/s。该数据集是 COCO 2017 原样封装（原图 + bbox 标注，图片本身未改动），取 val 分 2 个 parquet 分片 |
| Roboflow Universe | roboflow.com/universe | HTTP 403 | 未使用（前两个来源已足量） |
| GitHub | —— | 连接超时 | 相关资源均未走 GitHub |

## 二、下载量（原始数据）

| 来源 | 下载内容 | 体积 | 含标注图片总数 |
|---|---|---|---|
| Pascal VOC 2012 | VOCtrainval_11-May-2012.tar | 1,999,639,040 B（约 1.86 GB） | 17,125 张 |
| COCO 2017 val | val-00000 / val-00001 两个 parquet 分片 | 403,698,375 + 403,728,505 B（约 770 MB） | 4,952 张 |

## 三、筛选规则（机器初筛，仍须人眼终审）

**VOC（`tools/extract_voc.py`）**
- 保留条件：标注中含七类目标（person / chair / dining table / couch / tv / bottle / potted plant 之一）
  且含室内强指示物（家具、家电、厨餐用品等）；
- 排除：含户外强指示物（car / bus / animal / …）且无家具类证据；仅有 person 这类弱指示物的图。
- 命中：3,229 张。丢弃：仅弱室内指示 5,974、疑似户外 2,170、不含目标类别 5,752。

**COCO（`tools/extract_coco.py`）**
- 仅取三类：laptop / cup / bed（补齐 VOC 缺的三类）；
- 同样要求室内强指示物，排除户外；
- 每类上限 90 张。命中：249 张（bed 90 / laptop 91 / cup 106，一图可含多类）。

**VOC 已知坑**：VOC 中「沙发」标签为 `sofa`，词表写 `couch`，未做别名时该类统计为 0（已修，见脚本注释）。

## 四、压缩规格

`tools/compress_images.py`：长边 ≤960 等比缩放（只缩不放）、转 RGB、JPG 质量 85、剥离 EXIF。
- 输入 3,478 张 → 输出 3,478 张，失败 0，超规格 0。
- 输出目录 `data/images/`（与任务书的 `dataset/` 标注目录分开）。
- 报告：`data/images/_compress_report.md`。

## 五、候选池（分层抽样，供人眼筛选）

`tools/make_review.py`：COCO 三类全留（稀缺），VOC 按类配额，同类别组合最多取 2 张避免画面重复。
- 3,478 → **354 张**候选池，10 批预览。

| 编号 | 类别 | 候选张数 |
|---|---|---|
| 0 | person | 66 |
| 1 | chair | 76 |
| 2 | dining table | 56 |
| 3 | couch | 53 |
| 4 | tv | 53 |
| 5 | laptop | 91 |
| 6 | cup | 106 |
| 7 | bottle | 55 |
| 8 | potted plant | 50 |
| 9 | bed | 90 |

> 注：一图可覆盖多类，故合计 696 大于 354。
> 十类全部覆盖，每类均 ≥50 张候选，远超「每类 ≥15」硬门槛的 3 倍余量。

## 六、原始文件存放

- 原始图片与下载包：`D:\imglabel_raw\`（项目外，不进 git）
  - `_download\` 下载的原始压缩包/parquet
  - `candidates\voc\`、`candidates\coco\` 原始分辨率候选图 + `_meta_*.json`
- 保留数量待用户筛选后统计。
