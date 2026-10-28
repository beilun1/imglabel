# CONTEXT.md — 多 Agent 交接事实源

> 本文件是多个 AI 工具（Trae / Qoder / WorkBuddy）之间的唯一事实源。其中 WorkBuddy 仅用于 P1 数据准备，P2 及之后均由 Trae 与 Qoder 完成。
> **任何工具开工前必须先读本文件**；本文件只写"事实"，不写"情绪"。
> 每次换工具、每完成一个重要节点，都必须更新本文件并 git commit。

---

## 0. 一句话项目目标

人机协同图像标注系统：150 张室内图，YOLO-World/YOLO26n-seg 预标注 → 人工过审修正 → 导出三格式 → 训练 best.pt → 新模型回标迭代。截止 2026-11-03 22:00。

## 1. 当前状态（每次切换工具前更新）

> 本节按阶段倒序排列（最新在上）：P7 → P6 → P5 → P4 → P3 → P2；P1 数据统计见 §2 之后。

- [x] **P7 交付收尾（平台侧）完成**（2026-10-19，Qoder，`6c41d4f`）：
  - 根目录 `records/` 建立：从 `data/records/` **复制**（不移动，md5 逐个一致）6 个文件：修正记录.json、修正统计.json/.md、修正统计_r1.json/.md、对比结果.csv；`data/records/` 仍是平台写入目录，**之后若再产生修正或重跑统计/对比，须重新复制到 records/**
  - 交付物校验全过：dataset/ images/labels/segments/semantic 各 324、train 292 / val 32、data.yaml；model/best.pt（R1）+ train_metrics*.json；源码齐全；环境 OK
  - `提交信息.txt` 回填：数据集 328→324 说明（4 张非室内剔除）、类别分布按剔除后重算（laptop 85 / cup 97 / bed 78，合计 652）、迭代轮次、R0/R1 mAP 与修正率（取自 对比结果.csv）及口径说明；**姓名/学号/联系方式仍为占位，待用户本人填写**
  - `ai_log.md` 新建：P0–P7 按时间列出 Trae / Qoder / WorkBuddy 分工（含 P3 账号 B→A、P4/P6 用户人工过审）
- [x] **预标注限张**（2026-10-19，Qoder，`900a79e`）：`POST /api/prelabel` 可选 `limit`（正整数）= 只处理**无 JSON 的未标图**（按文件名排序）前 limit 张，`total` 为实际处理张数；省略 / 0 / 负数 / 非数字 / true → 全量，行为与旧版一致（已有 JSON 跳过）。列表页「开始预标注」左侧加「本次张数（留空=全部）」输入框。prelabel.py 未改，无暂停/取消。5001 隔离目录自测 8 项全过，真实 data/annotations 与 修正记录.json md5 不变。**改了 templates/，5000 服务需重启 + Ctrl+F5**
- [x] **预标注标签精简**（2026-10-19，Qoder，`4441751`）：列表页标签「本次张数（留空=全部）」→「本次张数」，输入框 placeholder 仍为「全部」；仅改 templates/index.html 一行，后端与 JS 未动
- [x] **专业多页面 UI 改版**（2026-10-22，Qoder，`fdf1bc7`）：按 `P7指令/UI设计稿.html` 的 V2 克制风统一六项深色侧栏；新增仪表盘 `/`、图片列表 `/annotate`、预标注 `/prelabel`、R0/R1 对比 `/compare`、三格式导出 `/export`，并重排 `/annotate/<name>` 标注工作台。指标读取真实 JSON/CSV/dataset 报告；新增只读 dashboard/compare/export-status API 与临时目录导出校验 API；预标注可选 R0/R1，既有 API 返回字段不变。`canvas/app.js` 只增加 10 行选中实例检查器显示，不改三模式、工具、`countEdit`、撤销重做和保存加载
  - 5001 浏览器验收六页、筛选/分页、三模式、R1 请求体与真实临时导出均通过，控制台无错；5002 临时目录完成新建框→撤销→重做→保存；项目 Python 真实 R1 推理 1 张成功（9 实例）。保护目录最终校验：annotations 325 / records 18 / curated 327 / dataset 1301，四组 MD5 与改版前完全一致
- [x] **切页短 TTL 缓存优化**（2026-10-22，Qoder，`1801479`）：`image_items()` 与无显式 `items` 的 `site_summary()` 增加进程内 2 秒弱缓存；显式传入 `items` 时保持不缓存；标注与修正记录事务全部落盘后清空两项缓存，保存后列表/仪表盘立即读新数据。`no_cache`、API 结构、标注行为与数据格式均未改
  - 5001 临时 annotations/records 副本验收 8 项通过：2 秒内重复调用不再读盘、过期重读；仪表盘/列表连续三轮与十次切页均正常；三模式、新建→撤销→重做→S 保存正常，实例 4→5、modified_count 1→2、修正记录 381→382 且字段不变；预标注/对比/导出数据正确，控制台无错。真实 annotations 325 文件 MD5 `44dbd3c5a2b93209034d24a8d56f01c1`、修正记录 MD5 `df4705e315ed80b29b6377a207fdc767` 前后不变
- [x] **首页数据可视化 + 全站骨架屏**（2026-10-26，Qoder，`3c03ae6`）：`site_summary()` 新增 `rate_history`（读 `对比结果.csv` 实际列名 `round`/`整体修正率`，兼容 `轮次`/`overall_rate`，解析失败返回 `[]`）与 `class_counts`（遍历 `ANN_DIR/*.json` 存活实例按 cls 计数，`_class_cache` 2 秒 TTL，`_cache_clear()` 连带清空），其余字段不变。首页新增 `dashboard-viz`：R0/R1 修正率 SVG 对比柱（23.75% / 15.22% / ▼ 8.53pp）、已过审 SVG 进度环、十类 CSS 横向条形，全部 Jinja 服务端渲染、无第三方库，空/单行/坏 CSV、缺字段均显示「暂无数据」/「等待 R1 对比数据」。`base.html` 内容区加 `#pageSkeleton` shimmer 骨架层（DOMContentLoaded + 两帧后淡出移除，3 秒兜底，noscript 隐藏），五个继承 base 的页面生效（画布页为独立模板不受影响）；列表页缩略图 `.thumb-placeholder` 灰底，加载后淡入。样式均内联在模板中，`canvas/` 未改
  - 5001 临时副本验收 8 项通过：API 两行修正率、class_counts 求和 2333 == 存活实例；三块可视化数值与进度环 236/324=72.8% 正确；空数据兜底不白屏；骨架出现→淡出移除；画布 addInstance+saveCurrent 保存后 2 秒内首页「床」74→75、其余不变；刷新 3 次计数稳定；对比/列表/预标注/导出/画布三模式回归正常、控制台无错。annotations / data/records / dataset / records / 对比结果.csv 五组 MD5 前后一致（基线含用户在途的 coco_10092 与修正统计改动，均未提交、未触碰）
- [x] **首页操作入口上移合并 + 迭代对比去重**（2026-10-26，Qoder，`02a66bd`）：首页 `.intro-actions` 改为 4 入口「进入图片列表(主)/模型预标注/逐张过审/迭代对比」（两个 /annotate 为既有设计，保留），加 `flex-wrap:wrap;justify-content:flex-end`；删除底部「操作入口」面板与 `.quick-list` 样式，`.dashboard-grid` 改单列使「标注进度」整行；可视化标题「人工修正率 · 迭代对比」改为「人工修正率 · R0 vs R1」以去重（图表逻辑不变）。app.py、数据、其他 5 页未动
  - 5001 临时副本验收 6 项通过：4 入口跳转正确且目标均 200；内容区「迭代对比」仅 1 处（侧栏导航为全局导航保留 1 处）；无操作入口面板、标注进度整行；统计卡/三块可视化/骨架屏正常、控制台无错；390/760px 下按钮换行不溢出；列表/预标注/对比/导出/画布三模式回归正常。五组 MD5 前后一致
- [x] **画布选中面板 ID 栏改为序号展示 + 底层 id 悬停**（2026-10-26，Qoder，`2aca1ea`）：`canvas/app.js` `syncClassUI()` 中 `inspector.id` 由 `sel.id` 改为 `"#" + state.instances.indexOf(sel)`（与画布脚标同源），`title="底层 id: <id>"`；未选中显示 `—` 并清空 title。`sel.id`、`uid()`、落盘 JSON、撤销/修正记录/导出均未动
  - 5001 临时副本验收：coco_10707 人工新建 `imvdm01sfn0m4` 面板 `#16` = 画布 `couch #16`，悬停 `底层 id: imvdm01sfn0m4`；预标注 `p0`/`p5` 显示 `#0`/`#5`；未选中 `—` 且 title 为空；删除为 `mark="deleted"` 保留在数组（落盘也保留），故后续序号**不前移**，但面板与画布始终一致；撤销/重做、保存+刷新后序号与底层 id 不变；控制台无错，各页 200；五组 MD5 前后一致
- [x] **画布选中面板底层 id 改为始终可见小字**（2026-10-26，Qoder，`0aff986`）：`annotate.html` ID 行下新增 `.ins-sub` 子行（`#insRawId`）；`app.js` `inspector.rawId` + `syncClassUI()` 写入 `sel.id`/`—` 与 title；`style.css` 新增 `.inspect-box>.ins-sub` 灰色 10.5px 等宽小字、max-width 120px 省略号截断（加 `.inspect-box>` 前缀是为压过 `.inspect-box>div` 的特异性）。主行 `#序号` 与悬停 title 保留
  - 5001 临时副本 + 1440px 无头 Edge 实测：新建实例 `#16` 下方灰字 `imvdm01sfn0m4`，预标注 `#0` 下方 `p0`；未选中两行均 `—`、title 清空；13 位 id 宽 75px 完整显示，超长串 120px 处省略号截断不换行；各状态面板高度恒 133px，置信度/掩码点数行位置不变；删除/撤销/重做后主行与小字同步；控制台无错，各页 200、画布三模式在；五组 MD5 前后一致
- [x] **5001 隔离沙箱脚本**（2026-10-26，Qoder，`fc83b61`）：`P7指令/5001隔离沙箱/` 下 `5001隔离启动.bat [demo-展示|demo-预标注]`（robocopy 到 `%TEMP%\isolated_5001`，排除 weights/data/dataset/runs/__pycache__/.git/.workbuddy；5001 被占即报错退出、不杀进程）、`5001隔离reset.bat`（清副本 annotations/records 的 JSON）、`读取副本统计.ps1`（阈值/实例数/conf min·avg·max）、`说明.md`
  - 展示模式：前 20 图 + 同名 JSON、records 空、不拷权重；预标注模式：前 8 图、标注/记录空、拷 weights 全部（含 `clip/ViT-B-32.pt`，YOLO-World 离线必需）
  - 三种用法：A 阈值对比（0.1→reset→0.25→reset→0.6，靠 reset 删 JSON 绕过预标注幂等跳过）；B 展示模式画布自测；C demo 录制（OBS/系统录屏，预标注演示每次先 reset，录完 `rd /s /q %TEMP%\isolated_5001`）
  - 实测限 2 张：实例数 15/5/2，min(conf) 0.153/0.329/0.671 均 ≥ 阈值；端口占用报错 exit 1 且占用方存活；删副本后五组 MD5 一致
  - 两个 .bat 刻意存 GBK(936) 且不 chcp 65001（cmd 按 UTF-8 读批处理中文会错位成乱码命令），勿另存 UTF-8
- [ ] **demo/ 待用户录制**：录屏 ≤3 分钟（启动 → 三模式标注 → 导出 → 对比结果）或 3 张关键截图，用户提供后放入 `demo/` 并提交；目录目前不存在，不得用非平台产物占位
- [ ] **最终 zip 待用户确认后打包**（截止 2026-11-03 22:00 前、由用户定日期）：打包前重新 `export_dataset.py` 生成 dataset/；zip 名 `姓名-人机协同图像标注系统.zip`，zip 根 = 项目根（含 `.git`、根 `.gitignore`）；排除 weights/、runs/、data/images/、data/review/thumbs/、__pycache__/、.workbuddy/、docs/；FTP 上传由用户本人完成
- [ ] **下一步待办**：用户填姓名/学号/联系方式 → 录 demo → 打包 zip → 上传 FTP
- [x] **P6 提示词已生成**（2026-10-19，Trae）：`P6指令/P6-提示词.md`（Qoder 执行）
- [x] **P6 平台侧完成**（2026-10-19，Qoder）：
  - `reback.py`：用 `model/best.pt`（R0 训练）回标 R0 未过审草稿（条件：source=prelabel、未过审、全部 mark=unchanged、无 reback 痕迹），实例 `src="reback"`、顶层 `source="reback"` + `reback{model, model_md5, conf, replaced…}` 元数据；先 md5 再推理、写前复核 md5（期间被人工保存则跳过），原子写；幂等
  - 真实回标：**174 张 / 1560 实例 / 0 错误**（替换 R0 草稿实例 1368，平均 8.97 个/张，空图 2：coco_60835、coco_776）；按类 person 290 · chair 380 · dining table 130 · couch 73 · tv 77 · laptop 50 · cup 323 · bottle 117 · potted plant 94 · bed 26
  - 校验 `tools/verify_reback.py --before <md5 列表>`：**已过审 153 张字节不变**、回标结构合法；重跑 reback 0 张（幂等）；`修正记录.json` md5 不变，R0 统计不变（285 条 / 153 过审 / 0.2375 / auto 0.1813，一致性通过）
  - round 口径：`IMGLABEL_ROUND=1` 启动后新记录 round=1（5001 隔离目录实测，round 0 的 285 条逐条不变）；过审改为分轮 `reviewed_rounds`（旧 reviewed:true 视为 [0]）；R1 统计写 `修正统计_r1.json/.md`，R0 文件不受影响；列表页新增「回标草稿」徽章与「本轮过审 N」
  - `train.py --round N`：指标另存 `model/train_metrics_r{N}.json`（R0 已冻结，`--round 0` 需 `--force`），`model/best_r{N}.pt` 本地副本（不入库）；起点权重仍为 yolo26n-seg.pt，保证两轮可比
  - `tools/compare_rounds.py` → `data/records/对比结果.csv`（UTF-8 BOM）：R0 行完成（mAP50 det 0.7619 / seg 0.6930，修正率 0.2375 / auto 0.1813）；**R1 行状态「待人工修正」，数值留空**（不伪造）。R1 记录晚于 R1 指标时自动标「待重训」
  - 注意：R1 val 集里未过审图的标签来自 R0 模型回标草稿，R1 mAP 与 R0 并非严格同一测试集；174 张原 R0 草稿 JSON 已被回标覆盖（git 历史 `8108dc8` 之前可找回）
- [x] **P6 剔除第 3 张非室内图**（2026-10-19，Trae）：R1 过审中发现 `coco_76547.jpg`（火车站台：有顶棚但四面开放、直接暴露自然光、背景可见外部建筑与天空，COCO 惯例归 outdoor），已剔除（图片+标注 JSON，R1 回标 4 实例未过审、无修正记录），同步 filelist/stats（**数据集现 324 张**）；10 类覆盖保留（person 实例张数 463→462，≥15 满足）；records 无该图条目
- [x] **P6 剔除第 2 张非室内图**（2026-10-19，Trae）：R1 过审中发现 `coco_63047.jpg`（公园式户外售货亭：可见天空/树木/开阔人行道，无室内围合），已剔除（图片+标注 JSON，R1 回标 4 实例未过审、无 R0/R1 修正记录），同步 filelist/stats（**数据集现 325 张**）；person 类实例张数 467→463（≥15 满足）；10 类覆盖保留；修正统计_r1 总数仍 326 一致；records 无该图条目
- [x] **P6 剔除 1 张非室内图**（2026-10-19，Trae）：R1 过审中发现 `coco_60835.jpg`（户外铁丝犬笼+泥土草地，非室内），已剔除（图片+标注 JSON，无 R0/R1 修正记录；该图为 R1 回标空图），同步更新 filelist/stats（**数据集现 326 张**）；修正统计_r1 的 images_total 327→326；对比结果.csv 不含该图数字无需改；person 类仍 60 张（≥15 满足）
- [x] **P6 R1 真人过审完成**（2026-10-19，用户）：`IMGLABEL_ROUND=1` 生效中（records 中 round=1 共 96 条：delete 70 · create 10 · move 6 · reclass 7 · resize 3，50 张有修改，**83 张已过审**）；修正统计_r1.json/.md 已生成；**R1 记录全部 round=1，R0 285 条未受污染**；数据集 324 张（P6 剔除 3 张非室内图）
- [x] **P6 R1 收尾完成**（2026-10-19，Qoder）：
  - R1 统计 `records_stats.py --round 1`：**96 条 / 50 张有修正 / 83 张过审，整体修正率 0.1522（93/611），auto 修正率 0.1381（83/601）**，一致性通过；R0 `修正统计.json/.md`、`修正记录.json` md5 不变，round 0 的 285 条与 153 张 R0 过审 JSON 内容对 `8108dc8` 逐项不变
  - 重导出 `export_dataset.py`：**324 张 / 2331 实例**（JSON 存活 2333 − 零面积 2：coco_10707、coco_116208 两个人工零宽框），train 292 / val 32，空图 1 张 coco_14831（P5 的 coco_776 在 R1 人工补了 couch，coco_99428 回标出 laptop 并经 R1 过审）；`verify_export.py` 全部通过
  - verify_export [4] 修正：R1 回标图 voc_2008_005257 p11 有细尖刺，像素中心恰在原多边形边上（y=158.5），6 位小数舍入翻转一串 11 像素超阈值 10；改为只统计中心不在原边上的残差（实测 0），阈值不变
  - 重训 `train.py --round 1`（30 轮设定，早停于 16 轮，best_epoch 1，32 分钟，起点仍 yolo26n-seg.pt）：**val det mAP50 0.7598 / mAP50-95 0.6250 · seg mAP50 0.7020 / mAP50-95 0.4975**；`model/best.pt` 现为 R1 模型（入库），`model/train_metrics_r1.json` 入库，`best_r1.pt` 本地不入库；R0 权重见 git 历史 `8108dc8` 的 `model/best.pt`（本地另有 `best_r0.pt`）
  - `对比结果.csv` 两行均「完成」：R0 0.7619/0.6150/0.6930/0.4435 · 修正率 0.2375 / auto 0.1813；R1 0.7598/0.6250/0.7020/0.4975 · 修正率 0.1522 / auto 0.1381
  - **结论**：R1 草稿（R0 自训模型回标）人工修正率 0.2375→0.1522、auto 修正率 0.1813→0.1381，均下降，说明自训模型草稿质量优于 P3 通用预标；mAP 除 det mAP50 基本持平（−0.002）外三项上升（seg mAP50-95 +0.054）。注意 R1 val 里未过审图的标签来自回标草稿，两轮 mAP 不是严格同一测试集；两轮都在第 1 轮取得最优，小数据集微调很快过拟合
- [x] **P5 全部完成**（2026-10-18，Qoder）：脚本 `effc664`，训练记录 `50149da`，已 push
  - **导出** `python export_dataset.py [--out dataset] [--seed 42]`：先跑 records_stats 一致性，不通过就退出；每次删掉重建，结果确定
  - **输出到 `dataset/`**（被 .gitignore 排除，不进 git，用脚本重新生成）：
    - `images/`
    - `labels/`：YOLO 检测 txt，框 = 掩码外接矩形
    - `segments/`：YOLO 分割 txt，只写外轮廓，孔洞和零宽桥已剪掉
    - `semantic/`：L 模式 PNG，像素值 = cls+1，背景 0，nonzero 填充，同类合并，后画的覆盖先画的
    - `train.txt` / `val.txt`、`data.yaml`（nc=10，无 path 键）
    - `export_report.md`：导出统计 + 训练段
  - **导出统计**：327 张，有效实例 **2207**（总 2345 − deleted 136 − 零面积 2），平均 6.75 个/张
    - 两个零面积实例：coco_10707、coco_116208，用户在图像边缘点画笔被夹到 x=0，成了 2 点线段；导出时跳过并写进报告，可在画布里删掉
    - 空图 3 张：coco_14831、coco_776、coco_99428，导出为空 txt + 全 0 PNG。P3 时是 4 张，coco_274687 在 P4 人工补了 2 个实例
    - train **294** / val **33**（9:1，seed 42）
    - 各类：person 514 · chair 350 · dining table 205 · couch 115 · tv 133 · laptop 120 · cup 328 · bottle 250 · potted plant 112 · bed 80
    - 掩码来源：分割 1554 · det 矩形占位 590 · 人工 63；带孔洞/桥的轮廓 202 个；过审图 153 张、草稿 174 张
  - **全量校验** `tools/verify_export.py`（327 张全过）：
    - 格式：cls 0-9、6 位小数、坐标在 [0,1] 内
    - 检测框与掩码外接矩形最大误差 5e-7；分割外接矩形 == 检测框
    - 语义 PNG 与 nonzero 参考栅格在 1px 边缘带以内的差异为 0
    - 实例守恒，逐类核对
  - **训练** `train.py`：
    - 只读 `dataset/data.yaml`；重写了 `YOLODataset.get_label_files`，改从 `dataset/segments/` 读分割标签，`labels/` 留作纯检测格式
    - 起点 `weights/yolo26n-seg.pt`；参数按设备自动选：CPU epochs 30 · imgsz 640 · batch 4 · patience 15，GPU epochs 80 · batch 16
    - 输出 `model/best.pt`（进 git）+ `model/train_report.md` + `model/train_metrics.json`；过程留在 `runs/segment/p5`（不进 git）
  - **训练结果**（CPU 47 分钟，在第 16/30 轮 early stop，best = 第 1 轮）：val 检测 mAP50 **0.7619** / mAP50-95 **0.6150**，分割 mAP50 **0.6930** / mAP50-95 **0.4435**
    - val mAP 在第 1 轮最高，随后学习率 warmup 上升就开始掉：小数据集，而且标注大多是同一个 COCO 预训练模型自己的草稿
    - 分割 mAP 偏低还有一个原因：590 个 det 实例的掩码是矩形占位
    - P6 想提升可以试 `lr0` 调小、冻结 backbone，或者等更多人工修正以后重训
- [x] **P4 全部完成**（2026-10-18，Trae 收尾）：用户真人过审 **153 张**（≥150 达标），真实修正 **285 条**（≥60 达标，86 张图有修正），整体修正率 **23.75%**，`python tools/records_stats.py` 一致性 **通过**（每图记录条数 == modified_count，被记录实例 id 集合 == mark≠unchanged 集合）。剩余未过审图（约 174 张）P5 导出直接用预标草稿，P6 回标时再迭代修正。成果提交 `a08f4e9`（121 张标注 JSON + 修正记录/统计），已 push
- [x] **P4 剔除 1 张非室内图**（2026-10-18，Trae）：过审中发现 `coco_235399.jpg`（货运卡车车厢+户外庭院）非室内场景，已剔除（图片+标注 JSON+该图 1 条修正记录），同步更新 filelist/stats，提交 `c2be0b1`。**数据集现 327 张**，person 类 60 张（≥15 仍满足）
- [x] 修正记录分布（285 条）：delete 136 · create 56 · reclass 28 · move 18 · erase_mask 17 · modify 12 · resize 11 · add_mask 7；涉及图片 86 张
- [x] 用户确认**无需审完 328 张**：任务书 P4 硬指标仅"修正记录 ≥60 条"；剩余图 P5 以预标草稿导出，P6 回标时再迭代修正
- [x] P4 埋点（代码 `8471fba`，示例 `3afc017`）：
  - **唯一计数入口** `countEdit(type, inst, cls_before, cls_after)`（canvas/app.js）：替换原 9 处 `modifiedCount++`，每次实际修改 +1 并生成一条记录；记录在撤销快照里，**撤销/重做同步增减**
  - type 映射：框新建 `create` · 多边形 `polygon` · 画笔新建 `add_mask` · 画笔同类内起笔扩展 `modify`(tool=brush) · 橡皮部分擦除 `erase_mask` · 橡皮擦出的分块新实例 `erase_mask`(split_from=原 id，cls_before=null) · 橡皮擦光 `delete`(tool=eraser) · Del 删除 `delete` · 框/掩码移动 `move` · 框把手缩放 `resize` · 下拉换类 `reclass`
  - 不计数：查看/缩放/平移/切模式/抓手、单击选中不拖动、下拉选同一类、移动工具单击不拖、仅保存（"仅确认"）——浏览器实测均 0 记录
  - **records 结构** `data/records/修正记录.json`（数组）：`{image, time, type, subject(实例id), cls_before, cls_after, auto, round, session, seq, [tool], [split_from]}`；`cls_before=null` = 新建，`cls_after=null` = 删除；`round` 由服务端强制（默认 0，P6 回标用环境变量 `IMGLABEL_ROUND=1` 启动服务）；image/round/session 以服务端为准，type/cls/subject 非法 → 400
  - 落盘：每次保存（含翻页自动保存）随 JSON 一起提交本会话记录，服务端加锁 + 原子写，**同一 session+image 的旧记录整体替换**（保存后再撤销再保存也一致）；不变化时不重写文件
  - **一致性不变式**（P5 导出前校验）：每图记录条数 == JSON `modified_count`；被记录的实例 id 集合 == `mark≠unchanged` 的实例集合。`python tools/records_stats.py` 会打印不一致项
  - 统计：`tools/records_stats.py [--round 0]`（保存后服务端也自动调用）→ `data/records/修正统计.json` + `.md`：总数/目标、按类型、按类别、换类明细、按图、修正率、一致性
  - **修正率分母口径**：图级修正率 = 该图本轮被修正过的**不同实例数** / 该图 JSON **实例总数**（auto 预标 + 人工新建，**含 mark=deleted**，即 `len(instances)`）；整体修正率 = Σ分子/Σ分母，范围 = 本轮有修正记录或已过审的图；另给 **auto 修正率** = 被修正的 auto 实例数 / auto 实例总数（P6 对比预标质量用这个）
  - 过审：只有**显式保存**（保存 / 保存并下一张 / S）写 `reviewed:true` + `reviewed_at`；翻页自动保存不置过审（浏览不会误标过审）。列表页状态优先级：已过审(实心绿) > 已修改 > 预标 > 已标 > 已标(空)；顶栏显示「已过审 X/328 · 累计修正 M/60」
  - 计数条：「本图修改 N 条」= 该图 JSON `modified_count`（跨会话累计，原文案"本次修改"不准确已改）；「累计修正 M / 目标 60」= 本轮全部记录（`GET /api/records/summary`）+ 本页未保存的记录，≥60 变绿
  - 保存时保留 JSON 的 `prelabel` 元数据与 reviewed 状态；`source` 照旧丢弃（P3 约定不变）
  - 验收示例 `data/records/验收示例/`：自测真实操作产生的 10 条（3 张图），**不计入 60**；自测后 `data/annotations/` 已还原为预标草稿，正式 `修正记录.json` 尚不存在，用户第一次修改时生成
- [x] **橡皮擦改为图层级**（2026-10-18，Qoder，`cef87ad`）：`eraseStroke` 只对 `selectedInst()` 做「掩码 − 笔迹」布尔差，笔迹经过的其他实例一律不动；分块/擦光/计数/撤销/语义与派生框联动逻辑不变
  - 无选中时按下橡皮：不擦、无记录、不入撤销栈、不画红色笔迹，画布中央显示普通提示「请先点选要擦除的实例」（`flashHint`，1.5s 不透明 + 0.5s 淡出，与空画布引导同样式，非错误红条）
  - 用法：掩码模式先按 **V 点选**实例（或在框模式点选）→ 按 E 擦；擦光后选中自动清空
  - 自测在 5001 隔离目录（临时 ANN/REC 目录）完成，记录归档 `data/records/验收示例/橡皮擦图层级/`（erase_mask + delete 各 1，不计入 60）；用户真实 `data/annotations/`（含 9 张已过审修改）与 `data/records/修正记录.json` 经 md5 比对未被触碰。该次提交**只按路径提交**，没用 `git add -A`，避免把用户在途的真实标注/记录混进代码提交
  - 用户需重启 5000 服务并 Ctrl+F5 刷新才生效
- [x] **框模式命中改为掩码级**（2026-10-18，Qoder，`b1f7a9b`）：用户反馈床上漏检的笔记本无法新建框（框内按下永远变成移动床框）。根因 `hitTestBox` 用外接矩形判命中。现改为：点在掩码内或距掩码边 ≤3px（参数 `maskTol=3`，图像坐标）才 `box-move`；框内非掩码区域 → 走 `box-create` 新建；重叠取外接矩形面积最小者、选中框把手优先，均不变；hover 光标同步（框内空隙为十字）。新建/移动/缩放流程、计数、记录、掩码模式均未动
  - 自测在 5001 隔离目录（`%TEMP%/boxhit_test`，复制的标注 + 空记录）完成：coco_222299 删去临时副本里的笔记本模拟漏检 → 床框内掩码外拖拽新建（`create`）；掩码上拖 = `move`；边外 1/2/2.9px 命中、4/6px 新建；把手缩放 `resize`；撤销/重做逐步回退；保存刷新后 modified_count=3=记录 3 条；coco_142620 杯/椅/桌三掩码重叠处点选 = 杯子。测试记录只留在临时目录，未归档入库；用户真实标注与记录 md5 比对 331 个文件不变，只按路径提交
  - 用户需重启 5000 服务并 Ctrl+F5 刷新才生效
- [x] **框模式拆分「移动 / 新建框」两工具**（2026-10-18，Qoder，`c7bfaed`）：掩码级命中后，物体上（床掩码上的笔记本）按下仍判为移动大框，无法新建。新增 `state.boxTool`：
  - `move`（默认，🖱️ 移动 / V）：`hitTestBox` 掩码级命中 → 移动/把手缩放；**点空白只取消选中、不再新建框**（与旧行为不同）
  - `create`（➕ 新建框 / N）：跳过命中判定，任意位置（含物体/掩码上）直接 `box-create`；hover 光标十字
  - 快捷键：框模式 V = 框移动；掩码/语义模式 V 仍 = 掩码移动工具；N 在任何模式都切到框模式 + 新建框（与 W/E/P 自动切掩码模式一致）；select 焦点下 N/V 照常生效并 preventDefault（坑 ⑩）；切 boxTool 退出抓手
  - 模板新增 `#boxTools`（已加入 REQUIRED_IDS，旧模板会红条提示）；快捷键提示条与底部 nav-hint 已更新；空画布引导改为两行（`drawCenterText` 支持 `\n`，单行提示不变）
  - box-create 收尾/`addInstance`/计数/撤销/records/掩码与语义模式均未改动
  - 自测（5001 隔离目录 `%TEMP%/boxtool_test`，coco_222299 / coco_14831）：新建工具在笔记本掩码上、床掩码上、框内空白拖拽均 `create`；移动工具拖掩码 = `move`、点空白取消选中且 0 新建 0 记录；把手缩放 `resize`；撤销/重做 5 步逐步回退；按钮/N/V 切换高亮与光标正确；空格/中键/抓手两工具下均平移且 0 记录；保存刷新后 modified_count=3=记录 3 条、id 一致。测试记录只留临时目录未入库；用户真实标注与记录 md5 比对 331 个文件不变，只按路径提交
  - 用户需重启 5000 服务并 Ctrl+F5 刷新才生效（模板改了，旧进程缓存旧模板会红条报缺 #boxTools）
- [x] **重叠框连续点击循环切换选中**（2026-10-18，Qoder，`e9a1712`）：小框完全在大框内时难以选中大框。
  - 命中**改回外接矩形包含**（用户确认；`b1f7a9b` 的掩码级命中作废，删 `segDist`/`nearPoly`）；有了 N 新建工具后，大框内建框用 N
  - `hitTestBox` 返回按外接矩形面积升序的全部命中，选中框把手仍优先（单独返回 resize）
  - 轮换规则：1 个命中 → 选它；≥2 个且当前选中在列表中 → 下一个（更大，最大后回最小）；否则选最小者
  - 拖拽目标：当前选中者在命中列表里时，按下仍拖它（循环到大框后可直接拖大框）；只有单击不拖才在弹起时切到下一个。Alt+按下 = 立即切到下一个
  - 选中信息提示「（此处 N 个框重叠，单击切换）」（`state.overlap`）
  - 移动工具下点大框内空白现在会选中大框（外接矩形命中），不再是取消选中
  - 新建工具、移动/缩放计数、records、撤销/重做、N/V、掩码/语义模式均未动
  - 自测（5001 隔离目录 `%TEMP%/cycle_test`）：
    - 2 框重叠 小→大→小；3 框 小→中→大→小；非重叠区直接选中；框外空白取消选中
    - 循环到大框后拖拽只移动大框（`move|p0`）；单击轮换 0 记录 0 撤销步
    - 把手缩放 `resize`；N 在笔记本上新建 `create`；撤销/重做 3 步；空格/中键/抓手两工具下平移 0 记录
    - 保存刷新后 modified_count=3=记录 3 条、id 一致
    - 用户真实标注与记录 md5 比对 331 个文件不变，只按路径提交
  - 用户需重启 5000 服务并 Ctrl+F5 刷新才生效
  - ⚠ 提交包结构要求源码根 `records/`，当前落在 `data/records/`（按 P4 提示词）。P7 打包时把 `data/records/` 拷到 `records/`（或届时统一改路径）
- [x] P3 阶段（2026-10-18，Qoder，含账号切换交接）已完成
- [x] P3 账号交接事实（2026-10-18）：会员充在账号 A，账号 B 先干活。**账号 B 实际只跑了 3 张子集**（不是续跑说明里估计的 150-200 张），交接时无 python 进程在跑；B 留下未提交的 prelabel.py + app.py 后端 API（原样保留未重写），前端进度条未做；B 还误给 `启动.bat` 首行加了第二个 BOM，已 `git checkout` 恢复。账号 A 补前端 + CLI 续跑 17 张 + 网页进度条跑剩余 308 张 + 9 项验收
- [x] P3 产出：`data/annotations/` **328 个 JSON**（= 328 张图），实例 **2279**（YOLO26n-seg 分割 1625 + YOLO-World 补漏框 654），**平均 6.95 个/张，错误 0**；空草稿 4 张（coco_14831 / coco_274687 / coco_776 / coco_99428，模型未检出，P4 需人工补）。CPU 约 0.4s/张，全量约 2 分钟
  - 各类实例数：person 578 · chair 368 · dining table 200 · couch 122 · tv 140 · laptop 120 · cup 312 · bottle 240 · potted plant 110 · bed 89
- [x] P3 JSON 约定（P4/P5 必读）：顶层 `image/width/height/instances/modified_count` 与画布 save 一致（**是 width/height 不是 w/h**），另有 `source:"prelabel"` + `prelabel{seg,det,conf,dropped_fragments,time}`；实例 `id:"p0.."`、`cls`、`mark:"unchanged"`、`auto:true`、`conf`、`src:"seg"|"det"`、`mask:{type:"polygon",points}`。
  - mark 用 `unchanged` 而非 `created`：画布 `markModified` 只把非 created 的改成 modified，这样人工改过的草稿能识别；P4 计数可按 `auto && mark==modified/deleted` 判定
  - `src:"det"` 是框矩形占位掩码（4 点），需人工细化；`≥25px²` 孔洞用零宽桥缝进外轮廓（与画布同一表示）
  - 列表页状态：`source=="prelabel"` 且 `modified_count==0` → 「预标」（蓝徽章）；画布保存时不带 source，人工保存过即变「已标」/「已修改」
- [x] P3 功能：`prelabel.py`（`--limit N` 子集 / 全量 / `--conf`，已有 JSON 跳过，写文件用 `"x"` 模式防覆盖人工保存）；`POST /api/prelabel` 后台线程（运行中重复触发 409「预标注运行中，请等待完成」）、`GET /api/prelabel/status`；列表页「开始预标注」按钮 + 进度条（0.7s 轮询，完成后自动刷新），顶栏改为可换行
- [x] P3 验收 9 项全过：CLI 3 张子集（跳过、md5 不变）→ 20 张 → 全量；328 JSON 无崩溃；随机 3 张结构正确且 2279 实例逐条校验（auto/mark/conf/多边形≥3 点/坐标在图内）0 异常；画布 coco_106389 三模式显示正常（框/掩码含孔洞/语义）、保存后实例逐字段不变、刷新仍在、控制台无错（测试后已恢复原 JSON）；进度条 0%→51%→100% 递增、最大帧间隔 50ms、完成自动刷新 328 张变「预标」；重复点击/POST 均 409；全量重跑 328 跳过、全部 JSON md5 不变；权重被 `*.pt` 忽略，status 无 `weights/`、`data/images/`
- [x] **权重路径**（不进 git）：`weights/yolo26n-seg.pt`（分割）、`weights/yolov8s-worldv2.pt`（YOLO-World，任务书里叫 yoloworld.pt）、`weights/clip/ViT-B-32.pt`（YOLO-World 文本编码器，prelabel.py 把 ultralytics WEIGHTS_DIR 指到 weights/，不随 cwd 漂移）
- [x] P2 全部完成（2026-10-18，Qoder）
- [x] 图片不显示根因（F12 实测）：5000 端口上同时有 2 个 python 进程（21:12 旧进程 + 23:27 新进程），请求全被旧进程接走；旧进程缓存了旧模板（无 #btnHand），新 app.js 第 873 行 `btnHand.addEventListener` 抛 TypeError → `load()` 未执行 → 画布无图。非浏览器缓存（app.js 本就是 no-cache+ETag）、非图片 404、非布局塌陷。修复：app.py 开 TEMPLATES_AUTO_RELOAD + after_request 禁缓存 + 启动前检测端口占用；app.js 缺元素/脚本错误/图片加载失败均显式红条+画布提示，失败时禁止保存防覆盖
- [ ] 最近一次 git commit：见 `git log`（P5 脚本 `effc664` / 训练记录 `50149da`；P4 完成 `a08f4e9` / 埋点代码 `8471fba` / 验收示例 `3afc017`）
- [ ] P2 阶段记录（Qoder 修复用户试用反馈，浏览器实测 30 项全过）：
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
- [x] 调色板更换（2026-10-18）：`PALETTE` 换为 `#e5484d #2563eb #f97316 #14b8a6 #8b5cf6 #16a34a #ec4899 #eab308 #84cc16 #92400e`（类别名与顺序未动）；全项目仅 canvas/app.js 一处定义，图例/笔触预览/掩码/框标签/语义都引用它
- [x] 橡皮擦改为按区域擦除（2026-10-18；**后已改为图层级，只擦选中实例，见 P4 段**）：每个相交实例做「掩码 − 笔迹圆盘序列」布尔差（离屏栅格 + destination-out，与红色预览同一几何）→ 8 连通分块 → 轮廓追踪 + simplifyClosed；最大块保留原 id，其余块成同类新实例（各 +1）；<25px² 碎块/孔洞丢弃；擦光 = mark="deleted"（+1）；一次擦除一条撤销记录，没擦到东西不计数不入栈。
  内部 ≥25px² 的孔洞会保留（孔洞反向绕行 + 零宽桥缝进外轮廓，nonzero 填充与 pointInPoly 都视为空），画笔合并也走同一套。语义视图按实例统一绕向后再同类合并，修掉了两实例绕向相反时重叠区被抵消的潜在 bug
- [x] P2 收尾（2026-10-18）：选中高亮 `SEL_COLOR` 改白色 `#ffffff`（`SEL_SHADOW` 不变），形成"深色衬底 + 白色主线"，不再撞桌子橙/瓶子黄；选中标签白底深字（textOn 自动）；多边形打点首点也变白，仅靠尺寸更大区分
- [x] 清空测试标注（2026-10-18）：删除 `data/annotations/coco_10092.json`（P2 试用残留），P3 开工前目录仅剩 `.gitkeep`（P3 后已有 328 个预标注 JSON）
- [x] 提示词文档归档到 `P0指令/`、`P1指令/`、`P2指令/`（用户整理，git 识别为重命名），原 `p0/` 已删除。整理过程中根目录 `.gitignore` 再次被旧版 `p0/.gitignore`（10-17 19:00 版）覆盖、丢了 P1 规则（`data/images/` 158MB 差点进库），已从 git 恢复——见坑 ⑥

- [ ] 卡住的坑（如有）：① 清华 PyPI 源 403，用阿里云镜像；② conda 不在 PATH，用 `C:\Users\H\miniforge3\envs\imglabel\python.exe`；③ 系统 `py` 启动器损坏，禁用；④ **Roboflow 403**，勿再尝试；⑤ VOC 里沙发标签是 `sofa` 不是 `couch`，做词表映射时务必别名；⑥ 工作区曾出现 `.gitignore`、`P0-提示词.md` 被移入 `p0/` 的情况，已恢复根目录原文件（内容逐字节一致），`p0/` 保留作归档（**2026-10-18 再犯一次**：整理归档时根 `.gitignore` 又被旧副本覆盖。现已无 `p0/`，**任何子目录都不许留 .gitignore 副本**；`git add -A` 前先看 `git status` 里有没有 `data/images/`）；⑦ GitHub 平时可 push，但**大文件并发下载时会超时**，需等下载结束再 push；⑧ **数据集自带标注不可信**：人工抽查发现 COCO/VOC 里有静物油画、极暗近全黑、目标仅占 1.2% 的图，**P3 预标注前不要相信数据集标签，必须人眼复核**；⑨ 列表页状态判定：无 JSON 文件须显示「未标」——「文件不存在」与「空标注 JSON」是两回事，空 JSON 才显示「已标(空)」（此 bug 已在初版修复）；⑩ **快捷键焦点失效**：键盘处理器对 select/input 一律 return，点过类别下拉框后所有快捷键失效——只对文本输入框跳过，其他控件要 preventDefault 防止下拉框按字母跳选项；⑪ **单击/直线笔画无法保存**：画笔只存笔触中心线，`strokePts<2` 丢弃单击、Douglas-Peucker 把直线简化成 2 点再被 `<3` 丢弃——必须按笔刷粗细栅格化取轮廓；⑫ Flask 非 debug 模式会**缓存模板**，改 templates/ 后必须重启服务才生效（JS/CSS 不缓存）；⑬ 5000 端口常被用户手动开的旧服务占用，自测用 `python -c "import app; app.app.run(port=5001)"`，不要改 app.py 端口；⑭ **假性故障「标注页没图」**：不是浏览器缓存——是旧服务进程没关，Windows 上 Werkzeug 用 SO_REUSEADDR，新进程也能绑同一端口却收不到请求，旧进程缓存的旧模板 + 磁盘上的新 JS 不匹配导致脚本崩溃。现已加：启动前端口占用检测（占用即报错退出）、模板热重载、页面/前端资源 no-store、模板与脚本版本不一致红条提示；⑮ **图片加载失败必须显式提示**：原 `img.onerror` 也 resolve，imgW=0 时只画底色、静默空白；现画布中央显示「图片加载失败：文件名（HTTP 状态）」，且禁止保存以免空标注覆盖已有 JSON；⑯ 测试图片加载失败**不要改坏 data/curated/images 里的真实图片**（已被安全策略拦截），用不存在的文件名在浏览器里调 load() 测

## 2. 阶段清单（P0 开工 → P7 收尾）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 环境 + git 仓库 | ✅ 已完成（2026-10-17） |
| P1 | 数据 150 张 / ≥6类 / 每类≥15张 | ✅ 已完成（328 张 / 10 类，2026-10-17） |
| P2 | flask UI 骨架 + 画布三模式 | ✅ 已完成（初版 Trae + 试用反馈修复/调色板/橡皮布尔差/收尾 Qoder，2026-10-18） |
| P3 | 预标注（YOLO-World / YOLO26n-seg） | ✅ 已完成（328 张 / 2279 实例 / 0 错误，账号 B→A 交接，2026-10-18） |
| P4 | 逐张过审 + 修正 ≥60 条（必须真人） | ✅ 已完成（修正 285/60，153 张过审，2026-10-18） |
| P5 | 三格式导出 + 训练 best.pt | ✅ 已完成（327 张 / 2207 实例导出；best.pt 检测 mAP50 0.762 / 分割 mAP50 0.693，2026-10-18） |
| P6 | 新模型回标 + R1 对比 | ✅ 已完成（回标 174 张 / R1 过审 83 张 / 修正 96 条；修正率 0.2375→0.1522；R1 seg mAP50 0.702，2026-10-19） |
| P7 | README / demo / 打包上传 FTP | 🟡 平台侧完成（records/ + 提交信息回填 + ai_log，2026-10-19）；demo 待用户录制，zip/FTP 待用户优化后打包 |


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
- **开发辅助可归档**：`P*-提示词.md`、`执行打卡看板.html` 是"人用"文档，agent 不依赖，可归档到对应阶段文件夹（`P0指令/`、`P1指令/`、`P2指令/`……）。
- **根目录常驻不许动**：CONTEXT.md、README.md、任务书.docx、.gitignore——任何阶段不许移，agent 交接必读；.gitignore 禁止在子目录留副本。

| 阶段 | 该阶段产出/相关文件 | 可否归档 |
|---|---|---|
| P0 | P0-提示词.md | ✅ 已入 P0指令/ |
| | .gitignore（根目录版） | ❌ 留根目录，勿复制副本 |
| P1 | P1-提示词.md | ✅ 已入 P1指令/ |
| | tools/（extract_voc/extract_coco/compress_images/make_review） | ✅ 保持 tools/ |
| | data/images/、data/review/、source_log.md | ✅ 保持 data/（images 在 P3-P5 复用） |
| P2 | app.py、canvas/、启动.bat、requirements.txt | ❌ 提交包结构，留源码根 |
| P3 | prelabel.py；权重 weights/yolov8s-worldv2.pt（=yoloworld.pt）/ yolo26n-seg.pt / clip/ViT-B-32.pt（不进 git） | ❌ 源码留根；权重路径记于本文件 |
| P4 | data/records/（修正记录.json / 修正统计.json/.md，验收示例/）、tools/records_stats.py、P4指令/ | ❌ 提交包结构（P7 拷到根 records/） |
| P5 | export_dataset.py、tools/verify_export.py、train.py、dataset/（三格式，不进 git，脚本再生成；P7 打包时导出）、model/best.pt + train_report.md | ❌ 提交包结构 |
| P6 | R1 对比结果（平台导出） | ❌ 归 records/ 或提交包 |
| P7 | demo/、ai_log.md、提交信息.txt、README.md 最终版 | ❌ 提交包结构 |

> 归档动作 = `git mv`（或移动后 git add -A）并更新本表；移动过、复制过、恢复过都要在"当前状态"记一笔（见 6 节第 ⑦ 条教训）。

## 7. 测试/验证命令（换工具后先跑，确认环境没坏）

```bash
conda activate imglabel
python -c "import ultralytics, flask, psutil; print('环境 OK')"
python app.py            # 起服务，浏览器打开确认页面
```
