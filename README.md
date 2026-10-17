# 人机协同图像标注系统

室内场景图像标注迭代工具：支持目标检测、实例分割、语义分割三种标注模式；YOLO 预标注 → 人工过审修正 → 导出标准数据集 → 训练自训模型 → 新模型回标迭代。

> 结算目标：30 分钟内完成 150 张室内图的三种模式标注。

## 快速开始（三条命令）

```bash
# 1. 一次性：建环境 + 装依赖
conda create -n imglabel python=3.10 -y && conda activate imglabel && pip install ultralytics flask psutil -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动程序
python app.py

# 3. 浏览器打开
#    http://127.0.0.1:5000
```

> 未配置过的新电脑：装好 Miniforge → 依次执行三行即可，全程 ≤10 分钟。也可双击根目录 `启动.bat` 一键启动。

## 目录结构

```
├─ app.py │ canvas/ │ prelabel.py │ 启动.bat │ requirements.txt  源码
├─ dataset/   平台导出的三种格式（YOLO txt / 实例掩码 / 语义 PNG）
├─ model/     自训权重 best.pt
├─ records/   修正记录 + 对比结果.csv（平台自动导出）
├─ demo/      演示录屏（≤3min）或 3 张关键截图
├─ ai_log.md  AI 使用记录（时间|工具|用途）
├─ 提交信息.txt  姓名/学号/联系方式、数据来源、迭代轮次与 mAP/修正率
├─ CONTEXT.md 开发协作交接事实源（多 agent 切换时先读）
└─ README.md
```

## 环境要求

- Windows 10 x64 / 8GB 内存 / 20GB 磁盘
- Miniforge（或 Miniconda）、Python 3.10
- 核心依赖：ultralytics / flask / psutil
- 无独显可用 CPU 训练（较慢）；可选 AutoDL 云算力

## 数据规格

室内场景照片，长边 ≤960px、JPG 质量 85；总量 ≥150 张、≥6 类、每类 ≥15 张。十类词表（类别编号不可改）：0 person · 1 chair · 2 dining table · 3 couch · 4 tv · 5 laptop · 6 cup · 7 bottle · 8 potted plant · 9 bed。

## 提交

整包压缩为「姓名-人机协同图像标注系统.zip」，上传 FTP（地址见任务书第五/六部分）。本 README 一页，按要求三命令可复现。