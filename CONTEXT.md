# CONTEXT.md — 多 Agent 交接事实源

> 本文件是多个 AI 工具（Trae / Qoder / WorkBuddy / CodeBuddy）之间的唯一事实源。
> **任何工具开工前必须先读本文件**；本文件只写"事实"，不写"情绪"。
> 每次换工具、每完成一个重要节点，都必须更新本文件并 git commit。

---

## 0. 一句话项目目标

人机协同图像标注系统：150 张室内图，YOLO-World/YOLO26n-seg 预标注 → 人工过审修正 → 导出三格式 → 训练 best.pt → 新模型回标迭代。截止 2026-11-03 22:00。

## 1. 当前状态（每次切换工具前更新）

- [x] 当前阶段：P0 开工准备 已完成（2026-10-17）
- [ ] 最近一次 git commit：见 `git log`（P0: 环境搭建与git仓库配置完成）
- [ ] 上一步完成：P0 全部——conda 环境 imglabel 创建（Python 3.10.22）、依赖安装并验证「环境 OK」、.gitignore 完善、GitHub 私有仓库关联（beilun1/imglabel）
- [ ] 下一步待办：P1 数据获取——150 张室内图 / ≥6 类 / 每类≥15 张，长边≤960px、JPG 质量 85（来源写进提交信息.txt）
- [ ] 卡住的坑（如有）：① 清华 PyPI 源在本机返回 403 被拦，已改用阿里云镜像 `https://mirrors.aliyun.com/pypi/simple/`（任务书写的清华源不可用，装依赖时直接走阿里云）；② conda 不在 PATH，统一用绝对路径 `C:\Users\H\miniforge3\Scripts\conda.exe` 或 `C:\Users\H\miniforge3\envs\imglabel\python.exe` 调用；③ 系统 `py` 启动器损坏（指向 D:\ 无效路径），别用 py，用 `python`（3.11.9）

## 2. 阶段清单（P0 开工 → P7 收尾）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 环境 + git 仓库 | ✅ 已完成（2026-10-17） |
| P1 | 数据 150 张 / ≥6类 / 每类≥15张 | 未开始 |
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

## 7. 测试/验证命令（换工具后先跑，确认环境没坏）

```bash
conda activate imglabel
python -c "import ultralytics, flask, psutil; print('环境 OK')"
python app.py            # 起服务，浏览器打开确认页面
```
