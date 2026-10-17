# CONTEXT.md — 多 Agent 交接事实源

> 本文件是多个 AI 工具（Trae / Qoder / WorkBuddy / CodeBuddy）之间的唯一事实源。
> **任何工具开工前必须先读本文件**；本文件只写"事实"，不写"情绪"。
> 每次换工具、每完成一个重要节点，都必须更新本文件并 git commit。

---

## 0. 一句话项目目标

人机协同图像标注系统：150 张室内图，YOLO-World/YOLO26n-seg 预标注 → 人工过审修正 → 导出三格式 → 训练 best.pt → 新模型回标迭代。截止 2026-11-03 22:00。

## 1. 当前状态（每次切换工具前更新）

- [x] 当前阶段：P1 数据准备 **进行中** —— 候选图已下载压缩完毕，**停在人工筛选暂停点**（2026-10-17）
- [ ] 最近一次 git commit：见 `git log`（P1: 候选图下载与压缩、筛选材料生成）
- [ ] 上一步完成：P0 全部（环境 imglabel / Python 3.10.22 / 阿里云源 / 私有仓库 beilun1/imglabel）
- [ ] 本步已完成：
  - 数据通道：VOC2012 走 PaddleSeg 百度云镜像（官方站 0.03MB/s 不可用，镜像 12.8MB/s）；COCO val 走 hf-mirror parquet（7.9MB/s）
  - 机器初筛 + 压缩：VOC 3229 张 + COCO 249 张 → 3478 张候选，长边≤960 / JPG85 全部合规，失败 0
  - 分层抽样后候选池 **354 张**，十类全覆盖，每类 ≥50 张
  - 筛选材料：`data/review/`（candidates.csv、category_hints.csv、preview/index.html 共 10 批）
- [ ] **下一步待办（阻塞中）**：等用户回话给保留清单 → 再执行第六步续（统计保留数、整理数据集、写提交信息.txt、git 提交）
- [ ] 卡住的坑（如有）：① 清华 PyPI 源 403，用阿里云镜像；② conda 不在 PATH，用 `C:\Users\H\miniforge3\envs\imglabel\python.exe`；③ 系统 `py` 启动器损坏，禁用；④ **Roboflow 403、GitHub 超时**，勿再尝试；⑤ VOC 里沙发标签是 `sofa` 不是 `couch`，做词表映射时务必别名；⑥ 工作区曾出现 `.gitignore`、`P0-提示词.md` 被移入 `p0/` 的情况，已恢复根目录原文件（内容逐字节一致），`p0/` 保留作归档

### P1 数据统计（截至暂停点）

| 项目 | 数量 |
|---|---|
| 原始候选（机器初筛后） | 3478（VOC 3229 / COCO 249） |
| 压缩输出 `data/images/` | 3478，失败 0，超规格 0，398.7MB→155.3MB |
| 送审候选池 | 354，10 批预览 |
| 待用户给出 | 保留清单（目标 ≥150 张 / ≥6 类 / 每类 ≥15） |


## 2. 阶段清单（P0 开工 → P7 收尾）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 环境 + git 仓库 | ✅ 已完成（2026-10-17） |
| P1 | 数据 150 张 / ≥6类 / 每类≥15张 | 🟡 进行中（候选已就绪，待人工筛选） |
| P2 | flask UI 骨架 + 画布三模式 | 未开始 |
| P3 | 预标注（YOLO-World / YOLO26n-seg） | 未开始 |
| P4 | 逐张过审 + 修正 ≥60 条（必须真人） | 未开始 |
| P5 | 三格式导出 + 训练 best.pt | 未开始 |
| P6 | 新模型回标 + R1 对比 | 未开始 |
| P7 | README / demo / 打包上传 FTP | 未开始 |

## 3. 不可更改项（红线，改了计零分）

- 十类词表（英文为模型调用名，顺序即类别编号，不得改）：
  0 person 人 · 1 chair 椅子 · 2 dining table 桌子 · 3 couch 沙发 · 4 tv 电视 ·
  5 laptop 笔记本电脑 · 6 cup 杯子 · 7 bottle 瓶子 · 8 potted plant 盆栽 · 9 bed 床
- 三种导出格式：YOLO txt / 实例掩码 / 语义 PNG
- train.py 只接受平台导出数据集（别改成吃别的格式）
- 任务书要求全部条目（http://10.4.16.13 见 README 源任务书）

## 4. 关键约定

- **数据规格**：室内场景，长边 ≤960px，JPG 质量 85；总量 ≥150，≥6 类，每类 ≥15。
- **目录结构**（提交包必须一致）：
  - 源码根：app.py、canvas/、prelabel.py + 启动.bat + requirements.txt
  - dataset/（三格式导出数据集）· model/best.pt · records/ · demo/ · ai_log.md · 提交信息.txt · README.md
- **环境**：conda 环境名 `imglabel`（python 3.10），核心依赖 ultralytics / flask / psutil，清华源安装。
- **启动方式**：flask 开发服务器，端口约定 ______（默认 5000；改端口先更新本文件）。
- **修正统计**：仅计"实际修改的框或掩码"，仅确认不计；埋点口径见 P4。
- **训练**：CPU 可训（慢）；AutoDL 4090 约 1.88 元/小时，5 元内，训练完立即关机。
- **模型**：YOLO-World（检测草稿）、YOLO26n-seg（分割草稿）；训练后 best.pt 为新模型。

## 5. Git 交接协议（每个工具开工/收工各做一次）

```bash
# —— 开工前（拿到接力棒）——
git pull                 # 拉最新
git status               # 看有没有未提交改动
git log --oneline -5     # 看别人最近做了什么
# 读本 CONTEXT.md 更新"当前状态"

# —— 收工前（交棒）——
git add -A
git commit -m "Px: 一句话说明本次改动"
git push                 # 推到私有仓库异地备份
# 更新 CONTEXT.md 的"当前状态"后再次 commit（CONTEXT 本身也要留痕）
```

## 6. 交接物落盘规则

- 脚本、数据集、修复的 bug：**必须写进项目目录 + git commit 后**，另一个工具才看得到。
- **禁止口头转述**给下一个工具；下一个工具只认本文件和仓库里已提交的内容。
- 大文件（权重、原始图片包）不进 git（见 .gitignore），交接时在 CONTEXT 里注明存放路径。

## 6.1 P1 新增目录约定（重要，别搞混）

| 路径 | 内容 | 是否进 git |
|---|---|---|
| `data/images/` | 全部候选图（3478 张，长边≤960、JPG85） | 否（158MB，脚本可重生成） |
| `data/review/` | 筛选材料：清单 csv/md、类别提示、预览 html | 是（thumbs 与分页 html 除外） |
| `data/review/source_log.md` | 数据来源与筛选过程一手记录（写提交信息.txt 的唯一依据） | 是 |
| `tools/` | 数据流水线脚本（extract_voc / extract_coco / compress_images / make_review） | 是 |
| `dataset/` | **平台导出的三种标注格式**（任务书要求） | 是（后续 P5 生成） |

> ⚠️ `data/images/` 与 `dataset/` 是两回事：前者是待标注的原始图片，后者是标注导出结果。
> 原始下载包与原始分辨率候选图在 **项目外** `D:\imglabel_raw\`。


## 7. 测试/验证命令（换工具后先跑，确认环境没坏）

```bash
conda activate imglabel
python -c "import ultralytics, flask, psutil; print('环境 OK')"
python app.py            # 起服务，浏览器打开确认页面
```
