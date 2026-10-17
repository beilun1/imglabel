# CONTEXT.md — 多 Agent 交接事实源

> 本文件是多个 AI 工具（Trae / Qoder / WorkBuddy / CodeBuddy）之间的唯一事实源。
> **任何工具开工前必须先读本文件**；本文件只写"事实"，不写"情绪"。
> 每次换工具、每完成一个重要节点，都必须更新本文件并 git commit。

---

## 0. 一句话项目目标

人机协同图像标注系统：150 张室内图，YOLO-World/YOLO26n-seg 预标注 → 人工过审修正 → 导出三格式 → 训练 best.pt → 新模型回标迭代。截止 2026-11-03 22:00。

## 1. 当前状态（每次切换工具前更新）

- [x] 当前阶段：**P2 画布修复完成 + 标注页图片不显示已修复**（2026-10-17，Qoder），等待用户二次试用；下一阶段 P3 预标注
- [x] 图片不显示根因（F12 实测）：5000 端口上同时有 2 个 python 进程（21:12 旧进程 + 23:27 新进程），请求全被旧进程接走；旧进程缓存了旧模板（无 #btnHand），新 app.js 第 873 行 `btnHand.addEventListener` 抛 TypeError → `load()` 未执行 → 画布无图。非浏览器缓存（app.js 本就是 no-cache+ETag）、非图片 404、非布局塌陷。修复：app.py 开 TEMPLATES_AUTO_RELOAD + after_request 禁缓存 + 启动前检测端口占用；app.js 缺元素/脚本错误/图片加载失败均显式红条+画布提示，失败时禁止保存防覆盖
- [ ] 最近一次 git commit：见 `git log`（P2: 修复画布交互缺陷 + 浅色主题）
- [ ] 上一步完成（Qoder 修复用户试用反馈，浏览器实测 30 项全过）：
  - 平移：新增抓手工具（H / ✋ 按钮）；保留空格+左键、中键；语义模式左键拖=平移；box 模式空白拖=新建框不变
  - 检测框：修 `isRectPoly` 顶点顺序错（新框从不被识别为矩形 → 无把手、拖角变整框平移）、n/s 把手改错顶点；
    改为"选中框把手优先 + 重叠取最小框"；框缩放时掩码按比例同步；移动/缩放真动了才计修改和入撤销栈；空画布中央提示
  - 画笔：笔触按真实粗细栅格化 → Moore 轮廓追踪 → 多边形（原来只存中心线，直线笔画被简化成 2 点直接丢弃）；
    单击 = 16 点圆；同类实例内起笔 = 合并扩展；画笔光标圈显示粗细，`[`/`]` 调粗细，滑块旁显示数值
  - 快捷键：仅文本输入框吞快捷键；焦点在下拉框/滑块/按钮时 W/E/P/1/2/3 等照常生效并阻止下拉框字母跳选；空格 preventDefault
  - 浅色主题：style.css 全套变量、画布底色 #e9ebef、选中高亮橙 #ffb020 + 深色衬底、标签字色按底色亮度自动黑/白、
    语义模式改为白色 50% 提亮原图 + 同类合并填充 0.7；修 `.legend{display:grid}` 覆盖 hidden 导致图例常显
  - 保存链路实测：画笔/框 → 保存 → `data/annotations/*.json` 落盘 → 刷新后标注仍在（后端无需改动）；测试 JSON 已删除，未入库
  - 新增顶部快捷键提示条（counterbar 右侧）、"已选中 #n：下拉改其类别"提示
- [x] 空画布引导提示改为自动淡出（2026-10-18）：标注读取完成且无实例时显示，2.4s 不透明 + 0.6s 线性淡出，本张图会话内只出现一次（缩放/切模式/平移/删光实例都不再出现），刷新或换图重新出现；修掉了已标图在图片与标注加载间隙闪现提示的问题；错误提示仍常驻
- [ ] **下一步待办**：用户二次试用确认 → P3 预标注（prelabel.py）
- [ ] 卡住的坑（如有）：① 清华 PyPI 源 403，用阿里云镜像；② conda 不在 PATH，用 `C:\Users\H\miniforge3\envs\imglabel\python.exe`；③ 系统 `py` 启动器损坏，禁用；④ **Roboflow 403**，勿再尝试；⑤ VOC 里沙发标签是 `sofa` 不是 `couch`，做词表映射时务必别名；⑥ 工作区曾出现 `.gitignore`、`P0-提示词.md` 被移入 `p0/` 的情况，已恢复根目录原文件（内容逐字节一致），`p0/` 保留作归档；⑦ GitHub 平时可 push，但**大文件并发下载时会超时**，需等下载结束再 push；⑧ **数据集自带标注不可信**：人工抽查发现 COCO/VOC 里有静物油画、极暗近全黑、目标仅占 1.2% 的图，**P3 预标注前不要相信数据集标签，必须人眼复核**；⑨ 列表页状态判定：无 JSON 文件须显示「未标」——「文件不存在」与「空标注 JSON」是两回事，空 JSON 才显示「已标(空)」（此 bug 已在初版修复）；⑩ **快捷键焦点失效**：键盘处理器对 select/input 一律 return，点过类别下拉框后所有快捷键失效——只对文本输入框跳过，其他控件要 preventDefault 防止下拉框按字母跳选项；⑪ **单击/直线笔画无法保存**：画笔只存笔触中心线，`strokePts<2` 丢弃单击、Douglas-Peucker 把直线简化成 2 点再被 `<3` 丢弃——必须按笔刷粗细栅格化取轮廓；⑫ Flask 非 debug 模式会**缓存模板**，改 templates/ 后必须重启服务才生效（JS/CSS 不缓存）；⑬ 5000 端口常被用户手动开的旧服务占用，自测用 `python -c "import app; app.app.run(port=5001)"`，不要改 app.py 端口；⑭ **假性故障「标注页没图」**：不是浏览器缓存——是旧服务进程没关，Windows 上 Werkzeug 用 SO_REUSEADDR，新进程也能绑同一端口却收不到请求，旧进程缓存的旧模板 + 磁盘上的新 JS 不匹配导致脚本崩溃。现已加：启动前端口占用检测（占用即报错退出）、模板热重载、页面/前端资源 no-store、模板与脚本版本不一致红条提示；⑮ **图片加载失败必须显式提示**：原 `img.onerror` 也 resolve，imgW=0 时只画底色、静默空白；现画布中央显示「图片加载失败：文件名（HTTP 状态）」，且禁止保存以免空标注覆盖已有 JSON；⑯ 测试图片加载失败**不要改坏 data/curated/images 里的真实图片**（已被安全策略拦截），用不存在的文件名在浏览器里调 load() 测

### P1 最终数据统计

| 项目 | 数量 |
|---|---|
| 原始候选（机器初筛后） | 3,478（VOC 3,229 / COCO 249） |
| 压缩输出 `data/images/`（不进 git） | 3,478，失败 0，超规格 0，398.7MB→155.3MB |
| 送审候选池 | 354 |
| 人工剔除 | 26（用户点名 21 + 复核发现 3 + 非场景照 2） |
| **最终保留 `data/curated/images/`** | **328 张 / 10 类，18.1MB，进 git** |

**类别分布（硬门槛：≥150 张 / ≥6 类 / 每类 ≥15）**

| 编号 | 类别 | 张数 | | 编号 | 类别 | 张数 |
|---|---|---|---|---|---|---|
| 0 | person | 61 | | 5 | laptop | 86 |
| 1 | chair | 74 | | 6 | cup | 98 |
| 2 | dining table | 53 | | 7 | bottle | 53 |
| 3 | couch | 51 | | 8 | potted plant | 48 |
| 4 | tv | 52 | | 9 | bed | 80 |

来源：Pascal VOC 2012 保留 100 张 · COCO 2017 val 保留 228 张。



## 2. 阶段清单（P0 开工 → P7 收尾）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 环境 + git 仓库 | ✅ 已完成（2026-10-17） |
| P1 | 数据 150 张 / ≥6类 / 每类≥15张 | ✅ 已完成（328 张 / 10 类，2026-10-17） |
| P2 | flask UI 骨架 + 画布三模式 | ✅ 已完成（初版 Trae + 试用反馈修复 Qoder，2026-10-17） |
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
| `data/curated/images/` | **最终保留的 328 张**（P3 预标注直接吃这里） | **是（必须随包提交）** |
| `data/curated/filelist.txt` `stats.md` `stats.json` | 最终清单与统计 | 是 |
| `data/review/` | 筛选材料：清单 csv/md、类别提示、预览 html | 是（thumbs 与分页 html 除外） |
| `data/review/source_log.md` | 数据来源与筛选过程一手记录（写提交信息.txt 的唯一依据） | 是 |
| `tools/` | 数据流水线脚本（extract_voc / extract_coco / compress_images / make_review / score_candidates / make_review2 / finalize_dataset） | 是 |
| `dataset/` | **平台导出的三种标注格式**（任务书要求） | 是（后续 P5 生成） |

> ⚠️ `data/curated/images/` 与 `dataset/` 是两回事：前者是待标注原图，后者是标注导出结果。
> 最终数据集目录**故意不叫 dataset_final**，避免与任务书的 `dataset/` 混淆。
> 原始下载包与原始分辨率候选图在 **项目外** `D:\imglabel_raw\`。


## 6.2 阶段文件归属速查表（每任务"哪些文件归它 / 哪些不许动"）

**三条总规则（任何阶段通用）：**
- **提交包结构不许动**：app.py、canvas/、prelabel.py、train.py、dataset/、model/、records/、demo/、ai_log.md、提交信息.txt、README.md——必须按任务书结构留在源码根，不管哪个阶段都不许移。
- **开发辅助可归档**：`P*-提示词.md`、`执行打卡看板.html` 是"人用"文档，agent 不依赖，可归档到对应阶段文件夹（p0/、p1/……）。
- **根目录常驻不许动**：CONTEXT.md、README.md、任务书.docx、.gitignore——任何阶段不许移，agent 交接必读；.gitignore 禁止在子目录留副本。

| 阶段 | 该阶段产出/相关文件 | 可否归档 |
|---|---|---|
| P0 | P0-提示词.md | ✅ 可入 p0/ |
| | .gitignore（根目录版） | ❌ 留根目录，勿复制副本 |
| P1 | P1-提示词.md | ✅ 可入 p1/ |
| | tools/（extract_voc/extract_coco/compress_images/make_review） | ✅ 保持 tools/ |
| | data/images/、data/review/、source_log.md | ✅ 保持 data/（images 在 P3-P5 复用） |
| P2 | app.py、canvas/、启动.bat、requirements.txt | ❌ 提交包结构，留源码根 |
| P3 | prelabel.py；权重 yoloworld.pt/yolo26n-seg.pt（不进 git） | ❌ 源码留根；权重路径记于本文件 |
| P4 | records/（修正记录） | ❌ 提交包结构 |
| P5 | train.py、dataset/（三格式）、model/best.pt | ❌ 提交包结构 |
| P6 | R1 对比结果（平台导出） | ❌ 归 records/ 或提交包 |
| P7 | demo/、ai_log.md、提交信息.txt、README.md 最终版 | ❌ 提交包结构 |

> 归档动作 = `git mv`（或移动后 git add -A）并更新本表；移动过、复制过、恢复过都要在"当前状态"记一笔（见 6 节第 ⑦ 条教训）。

## 7. 测试/验证命令（换工具后先跑，确认环境没坏）

```bash
conda activate imglabel
python -c "import ultralytics, flask, psutil; print('环境 OK')"
python app.py            # 起服务，浏览器打开确认页面
```
