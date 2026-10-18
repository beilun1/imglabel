# CONTEXT.md — 多 Agent 交接事实源

> 本文件是多个 AI 工具（Trae / Qoder / WorkBuddy / CodeBuddy）之间的唯一事实源。
> **任何工具开工前必须先读本文件**；本文件只写"事实"，不写"情绪"。
> 每次换工具、每完成一个重要节点，都必须更新本文件并 git commit。

---

## 0. 一句话项目目标

人机协同图像标注系统：150 张室内图，YOLO-World/YOLO26n-seg 预标注 → 人工过审修正 → 导出三格式 → 训练 best.pt → 新模型回标迭代。截止 2026-11-03 22:00。

## 1. 当前状态（每次切换工具前更新）

- [x] **P4 全部完成**（2026-10-18，Trae 收尾）：用户真人过审修正 **77 条**（≥60 达标，16 张图、涉及 15 张有修正），`python tools/records_stats.py` 一致性 **通过**（每图记录条数 == modified_count，被记录实例 id 集合 == mark≠unchanged 集合）。已过审 16 张（未过审图 P5 导出直接用预标草稿，符合任务书"预标草稿 → 人工逐张审核"流程）。成果提交 `045f26f`（16 张标注 JSON + 修正记录/统计），已 push
- [x] 修正记录分布（77 条）：delete 20 · move 14 · reclass 12 · erase_mask 10 · modify 9 · create 4 · resize 4 · add_mask 4；涉及图片 15 张
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
- [ ] 最近一次 git commit：见 `git log`（P4 完成 `045f26f` / 埋点代码 `8471fba` / 验收示例 `3afc017`）
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
- [ ] **下一步待办**：**P5 三格式导出 + 训练 best.pt**（读 `P5指令/P5-提示词.md` 执行）；P4 不要重跑预标注覆盖人工成果（prelabel 本身幂等跳过已有 JSON）
- [ ] 卡住的坑（如有）：① 清华 PyPI 源 403，用阿里云镜像；② conda 不在 PATH，用 `C:\Users\H\miniforge3\envs\imglabel\python.exe`；③ 系统 `py` 启动器损坏，禁用；④ **Roboflow 403**，勿再尝试；⑤ VOC 里沙发标签是 `sofa` 不是 `couch`，做词表映射时务必别名；⑥ 工作区曾出现 `.gitignore`、`P0-提示词.md` 被移入 `p0/` 的情况，已恢复根目录原文件（内容逐字节一致），`p0/` 保留作归档（**2026-10-18 再犯一次**：整理归档时根 `.gitignore` 又被旧副本覆盖。现已无 `p0/`，**任何子目录都不许留 .gitignore 副本**；`git add -A` 前先看 `git status` 里有没有 `data/images/`）；⑦ GitHub 平时可 push，但**大文件并发下载时会超时**，需等下载结束再 push；⑧ **数据集自带标注不可信**：人工抽查发现 COCO/VOC 里有静物油画、极暗近全黑、目标仅占 1.2% 的图，**P3 预标注前不要相信数据集标签，必须人眼复核**；⑨ 列表页状态判定：无 JSON 文件须显示「未标」——「文件不存在」与「空标注 JSON」是两回事，空 JSON 才显示「已标(空)」（此 bug 已在初版修复）；⑩ **快捷键焦点失效**：键盘处理器对 select/input 一律 return，点过类别下拉框后所有快捷键失效——只对文本输入框跳过，其他控件要 preventDefault 防止下拉框按字母跳选项；⑪ **单击/直线笔画无法保存**：画笔只存笔触中心线，`strokePts<2` 丢弃单击、Douglas-Peucker 把直线简化成 2 点再被 `<3` 丢弃——必须按笔刷粗细栅格化取轮廓；⑫ Flask 非 debug 模式会**缓存模板**，改 templates/ 后必须重启服务才生效（JS/CSS 不缓存）；⑬ 5000 端口常被用户手动开的旧服务占用，自测用 `python -c "import app; app.app.run(port=5001)"`，不要改 app.py 端口；⑭ **假性故障「标注页没图」**：不是浏览器缓存——是旧服务进程没关，Windows 上 Werkzeug 用 SO_REUSEADDR，新进程也能绑同一端口却收不到请求，旧进程缓存的旧模板 + 磁盘上的新 JS 不匹配导致脚本崩溃。现已加：启动前端口占用检测（占用即报错退出）、模板热重载、页面/前端资源 no-store、模板与脚本版本不一致红条提示；⑮ **图片加载失败必须显式提示**：原 `img.onerror` 也 resolve，imgW=0 时只画底色、静默空白；现画布中央显示「图片加载失败：文件名（HTTP 状态）」，且禁止保存以免空标注覆盖已有 JSON；⑯ 测试图片加载失败**不要改坏 data/curated/images 里的真实图片**（已被安全策略拦截），用不存在的文件名在浏览器里调 load() 测

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
| P2 | flask UI 骨架 + 画布三模式 | ✅ 已完成（初版 Trae + 试用反馈修复/调色板/橡皮布尔差/收尾 Qoder，2026-10-18） |
| P3 | 预标注（YOLO-World / YOLO26n-seg） | ✅ 已完成（328 张 / 2279 实例 / 0 错误，账号 B→A 交接，2026-10-18） |
| P4 | 逐张过审 + 修正 ≥60 条（必须真人） | ✅ 已完成（修正 77/60，16 张过审，2026-10-18） |
| P5 | 三格式导出 + 训练 best.pt | 🟡 未开始（提示词已生成，待 Qoder 执行） |
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
