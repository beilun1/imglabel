# P7 指令：画布「选中实例」面板底层 id 改为始终可见小字（取代 title 悬停）

> 背景：上一版已把面板 ID 栏改为 `#序号` 展示，并把真实底层 id 放在 `title` 悬停里。但原生 title 提示过于隐蔽（需鼠标静止 1~2 秒才出现、无任何视觉暗示），用户反馈"不知道悬停在哪"。本次改为：`#序号` 为主显示，其下方加一行**始终可见的灰色小字**直接展示底层 id（居中截断），不再依赖悬停。`title` 可保留但不作主要入口。
> 范围：只动 `templates/annotate.html` + `canvas/app.js`（+ `canvas/style.css` 若需样式）。**不碰任何数据文件、不碰 uid()/落盘结构/修正记录/撤销/导出逻辑、不碰后端。**
> 定位：纯展示层优化，底层 `id` 字段原样保留。

## 角色
你是本项目的资深前端工程师，熟悉 V2 视觉规范，负责把选中面板的底层 id 从"悬停"改为"始终可见小字"。

## 必读
1. `templates/annotate.html` 第 29 行 `inspect-box` 面板结构（ID 行是 `<span>ID</span><b id="insId">—</b>`）
2. `canvas/app.js` 的 `syncClassUI()`（现已在 `inspector.id.textContent`/`.title` 写入 `#序号` 与底层 id）与 `inspector` 对象（第 96-100 行）
3. `canvas/style.css` 中 `.inspect-box` 相关样式

## 任务

### 1. 模板（templates/annotate.html）
把 ID 行改为"主值 + 下方小字"双层结构：
```html
<div><span>ID</span><b id="insId">—</b></div>
```
改为：
```html
<div><span>ID</span><b id="insId">—</b></div>
<div class="ins-sub"><span class="ins-sub-fill"></span><b id="insRawId">—</b></div>
```
说明：
- `insRawId` 是新增的底层 id 小字容器；`ins-sub-fill` 用于在窄行时占位对齐（保持与上方"类别"等行同宽），如不需要可省。
- 关键：**此子行仅当有选中实例且有底层 id 时显示内容**；未选中时应为 `—`（与主 ID 一致）或留空占位，保持面板高度稳定。

### 2. JS（canvas/app.js）
- 在 `inspector` 对象（第 97-100 行区域）新增引用：`rawId: document.getElementById("insRawId")`。
- 在 `syncClassUI()` 中，选中分支追加：
```js
if (inspector.rawId) {
  inspector.rawId.textContent = sel ? sel.id : "—";
  inspector.rawId.title = sel ? "底层 id: " + sel.id : "";
}
```
  未选中分支也要置回 `—` 并清空 title，避免残留上一条数据。
- 现存的 `inspector.id.title = "底层 id: " + sel.id;` 可保留（作为次要入口），但**主要展示以 `insRawId` 小字为准**。

### 3. 样式（canvas/style.css）
给 `.ins-sub` 增加一条弱化样式，使底层 id 以小字、灰、截断表现，避免喧宾夺主：
```css
.ins-sub{display:flex;justify-content:space-between;gap:8px;padding:1px 0 3px;font-size:10.5px;color:#9aa2b3}
.ins-sub b{font:10.5px var(--mono);color:#9aa2b3;text-align:right;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
```
- 要求：小字灰色（不抢 `#序号` 主视觉）；超长（如 `imvdm01sfn0m4`）用省略号截断；与 V2 风格一致。

## 明确不动
- 所有 `data/annotations/*.json`、修正记录、对比结果、`uid()`、`p` 前缀语义
- 后端 app.py、其他页面、骨架屏、首页可视化
- 不引第三方库

## 自测清单（5001 端口隔离目录实测，逐项过）
1. 打开含人工新建实例的图（如 `coco_10707.jpg`），点选该实例：ID 主行显示 `#序号`，正下方有一行灰色小字直接显示 `imvdm...`（无需悬停即可见）
2. 点选预标注实例（如 `p0`）：主行 `#序号`，小字显示 `p0`（预标注实例底层 id 也是 `p0`，小字正常显示，不视为错误）
3. 未选中：主 ID 为 `—`，小字 `insRawId` 也为 `—`，无残留上一条
4. 人工长 id（13 位）小字被截断为省略号、不换行撑开面板
5. 面板高度稳定，新增子行不挤压下方"置信度/掩码点数"错位
6. 撤销/重做、删除后序号与小字同步更新，无错位
7. 保留悬停 title 可查（作为次要入口，若存在）
8. 回归：`data/annotations/`、`data/records/`、`dataset/`、`对比结果.csv` 的 md5 前后一致；其余 5 页 + 画布其余功能正常

## 收工
1. commit（信息说明：画布选中面板底层 id 改为始终可见小字）→ push
2. 更新 CONTEXT.md 当前状态（记一笔 + 提交哈希）→ commit → push
3. 汇报：改动点（模板/JS/样式各一处）、两种实例的小字展示效果、自测 8 项结果、git 提交哈希
4. 提醒用户：重启 5000 服务 + Ctrl+F5 强刷后生效