# 人机协同图像标注系统

室内场景图像标注迭代工具：支持目标检测、实例分割、语义分割三种标注模式；YOLO 预标注 → 人工过审修正 → 导出标准数据集 → 训练自训模型 → 新模型回标迭代。

> 结算目标：30 分钟内完成 150 张室内图的三种模式标注。

## 评审从这里看

| 看什么 | 直接打开 | 说明 |
|---|---|---|
| 演示视频（主片） | [demo/演示录屏.mp4](demo/演示录屏.mp4) | 2 分 54 秒：启动 → 预标注 → 三模式标注 → 导出 → R0/R1 对比 |
| 演示视频（5002 短片） | [demo/5002-任意图检测.mp4](demo/5002-任意图检测.mp4) | 43 秒：拖入数据集外的任意图，实时检测并切换三模式 |
| 三格式数据集 | [dataset/](dataset/) · [export_report.md](dataset/export_report.md) | YOLO txt / 实例掩码 / 语义 PNG，324 张，train:val = 9:1 |
| 自训模型 | [model/best.pt](model/best.pt) · [train_report.md](model/train_report.md) | R1 权重 6.3MB，含各轮训练指标 |
| 迭代结果 | [records/对比结果.csv](records/对比结果.csv) · [修正统计.md](records/修正统计.md) | R0/R1 的 mAP 与人工修正率 |
| 交付说明 | [提交信息.txt](提交信息.txt) · [ai_log.md](ai_log.md) · [CONTEXT.md](CONTEXT.md) | 数据来源与类别分布、AI 使用记录、开发交接 |
| 整包下载 | [Download ZIP](https://github.com/beilun1/imglabel/archive/refs/heads/master.zip) | 约 100MB，含全部源码、数据、权重与演示视频 |

> 公开仓库，无需登录即可浏览与下载；想在本机跑起来请看下面的「快速开始」。

## 快速开始（三条命令）

```bash
# 1. 一次性：建环境 + 装依赖
conda create -n imglabel python=3.10 -y && conda activate imglabel && pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 2. 启动主程序
python app.py

# 3. 浏览器打开
#    http://127.0.0.1:5000
```

> 也可双击根目录 `启动.bat` 一键启动。首次运行会联网下载 YOLO-World 的 CLIP 文本编码器（`weights/clip/ViT-B-32.pt`，约 354MB，仅首次）。

## 三个可运行入口

| 端口 | 入口 | 作用 | 启动方式 |
|---|---|---|---|
| 5000 | 正式环境 | 全量 324 张标注、预标注、导出、对比页 | `python app.py` 或 `启动.bat` |
| 5001 | 隔离沙箱 | 在 `%TEMP%` 建项目副本，随意预标注/改标注/录屏，真实数据零污染 | `5001沙箱/5001隔离启动.bat` |
| 5002 | 任意图演示台 | 拖入数据集外的任意室内图，实时检测并切换三模式 | `5002演示台/启动.bat` |

> 5001 沙箱脚本开头的 `PY=` 优先用本机 conda 路径，路径不存在时自动回退到 `python`（需 python 已在 PATH）；参数可选 `demo-展示`（取 20 张带标注的图，可看仪表盘/列表/画布）或 `demo-预标注`（取 8 张图、标注留空，可跑预标注），缺省 `demo-预标注`。
> 三个入口互不干扰，可同时开；5002 只读复用主项目权重与推理函数，临时文件仅存于 `5002演示台/` 内部。

**换机运行注意（评审/复现）**

- **首次联网**：CLIP 文本编码器约 354MB，超过 GitHub 单文件上限未随仓库提供，首次在 5002 选 R0 或预标注页选 R0 时自动下载到 `weights/clip/`。**离线环境选 R1**（`model/best.pt`，本地权重）即可完整演示预标注与检测。
- **端口占用**：5000/5001/5002 互不冲突；若提示占用，说明上次窗口未关，关闭后重试，脚本不会结束任何进程。
- **页面内容未更新**：浏览器缓存所致，Ctrl+F5 强制刷新。
- **双击 bat 闪退**：多为缺依赖或 python 不在 PATH，改在 cmd 里手动 `python app.py` 查看报错。
- **5001 是沙箱**：项目复制到 `%TEMP%\isolated_5001`，真实数据只读；清理执行 `rd /s /q %TEMP%\isolated_5001`。
- **演示预标注要用 5001**：5000 的 324 张已全部标注，预标注页点开始会全部跳过（页面会提示）；要看预标注效果请开 `5001沙箱/5001隔离启动.bat demo-预标注`，那里的标注目录是空的。

## 目录结构

```
├─ app.py │ prelabel.py │ reback.py │ train.py │ export_dataset.py   主程序源码
├─ canvas/ │ templates/ │ 启动.bat │ requirements.txt                 画布 / 页面 / 启动 / 依赖
├─ 5002演示台/  5002 任意图检测演示台（独立 Flask 应用，端口 5002）
├─ 5001沙箱/    5001 隔离沙箱脚本（%TEMP% 项目副本，真实数据零污染）
├─ data/
│   ├─ curated/images/   324 张室内原图
│   ├─ annotations/      每张图的标注 JSON（三模式同源）
│   └─ records/          修正记录与统计
├─ dataset/    平台导出的三种格式（YOLO txt / 实例掩码 / 语义 PNG），train:val = 9:1
├─ model/      自训权重 best.pt + 各轮训练指标
├─ weights/    预标注所用官方权重（yolo26n-seg.pt / yolov8s-worldv2.pt）
├─ records/    根目录交付版修正记录 + 对比结果.csv
├─ demo/       演示录屏：演示录屏.mp4（2:54，启动→预标注→三模式→导出→对比）+ 5002-任意图检测.mp4（0:43）
├─ tools/      数据准备 / 导出校验 / 统计对比脚本（extract_*、finalize_dataset、verify_export、records_stats、compare_rounds 等）
├─ ai_log.md   AI 使用记录（时间|工具|用途）
├─ 提交信息.txt  姓名/学号/联系方式、数据来源、迭代轮次与 mAP/修正率
├─ CONTEXT.md  开发协作交接事实源（多 agent 切换时先读）
├─ .gitattributes  *.bat / *.ps1 按原样存储，保证仓库内为 CRLF
└─ README.md
```

## 环境要求

- Windows 10 x64 / 8GB 内存 / 20GB 磁盘
- Miniforge（或 Miniconda）、Python 3.10
- 核心依赖：ultralytics / flask / psutil
- 无独显可用 CPU 训练（较慢）；可选 AutoDL 云算力

## 数据规格

室内场景照片，长边 ≤960px、JPG 质量 85；总量 ≥150 张、≥6 类、每类 ≥15 张。十类词表（类别编号不可改）：0 person · 1 chair · 2 dining table · 3 couch · 4 tv · 5 laptop · 6 cup · 7 bottle · 8 potted plant · 9 bed。

实际交付：324 张，覆盖全部 10 类，每类 ≥48 张。

## 迭代结果

| 轮次 | det mAP50 | det mAP50-95 | seg mAP50 | seg mAP50-95 | 人工修正率 |
|---|---|---|---|---|---|
| R0（官方权重预标注） | 0.7619 | 0.6150 | 0.6930 | 0.4435 | 0.2375 |
| R1（自训 best.pt 回标） | 0.7598 | 0.6250 | 0.7020 | 0.4975 | 0.1522 |

修正率 0.2375 → 0.1522，人工需修改的对象占比下降约 8.5 个百分点；数据源为平台自动导出的 `records/对比结果.csv`，未手改。

## 提交

- GitHub 仓库：https://github.com/beilun1/imglabel（公开，评审可直接浏览、单文件下载或整包 zip 下载）
