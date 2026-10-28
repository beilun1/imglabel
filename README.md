# 人机协同图像标注系统

室内场景图像标注迭代工具：支持目标检测、实例分割、语义分割三种标注模式；YOLO 预标注 → 人工过审修正 → 导出标准数据集 → 训练自训模型 → 新模型回标迭代。

> 结算目标：30 分钟内完成 150 张室内图的三种模式标注。

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

> 5001 沙箱脚本开头的 `PY=` 变量默认指向本机 conda 环境，换机器运行时改成自己的 `python.exe` 路径即可。
> 三个入口互不干扰，可同时开；5002 只读复用主项目权重与推理函数，临时文件仅存于 `5002演示台/` 内部。

## 目录结构

```
├─ app.py │ canvas/ │ prelabel.py │ 启动.bat │ requirements.txt  主程序源码
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
├─ demo/       演示录屏（≤3min）或 3 张关键截图
├─ ai_log.md   AI 使用记录（时间|工具|用途）
├─ 提交信息.txt  姓名/学号/联系方式、数据来源、迭代轮次与 mAP/修正率
├─ CONTEXT.md  开发协作交接事实源（多 agent 切换时先读）
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

- GitHub 仓库：https://github.com/beilun1/imglabel
- 整包压缩为「姓名-人机协同图像标注系统.zip」，上传 FTP（地址见任务书第五/六部分）。
