# P7 指令：画布选中实例面板「ID 栏」改为展示序号 + 真实 id 悬停

> 目标：让画布「选中实例」面板的 ID 栏不再直接显示底层 id（人工新建实例会是 `imvdm...` 时间戳+随机串，观感像乱码），改为显示与画布脚标一致的 `#序号`，并把真实底层 id 放到 title 悬停中，信息不丢。
> 范围：只动 `canvas/app.js`（前端展示层），**不碰任何数据文件、不碰 uid()/落盘结构/修正记录/撤销/导出逻辑、不碰后端**。
> 定位：纯显示优化，零数据迁移风险。底层 `id` 字段原样保留，重启/换工具/导出训练不受影响。

## 角色
你是本项目的资深前端工程师，熟悉 V2 视觉规范，负责一处极小的展示层改动。

## 必读
1. `canvas/app.js` 中 `syncClassUI()`（选实例时刷新右侧面板）
2. `canvas/app.js` 中 `selectedInst()`、`state.instances` 结构、实例 `id` 字段
3.（了解即可）`uid()` 生成人工新建实例 id 的规则，理解为什么会出现 `imvdm...`

## 背景：现状与目标
- 现状：`inspector.id.textContent = sel ? sel.id : "—"`，人工新建实例时 ID 直接弹出 `imvdm...`（`"i"+时间戳36进制+随机串36进制`），与画布 `#16` 脚标对不上，观感像乱码。
- 目标：面板 ID 栏显示 `#序号`（与画布脚标同源，用 `state.instances.indexOf(sel)`），并把真实底层 id 放 `title` 悬停。

## 任务：改造 ID 栏展示（canvas/app.js 的 syncClassUI 内）
仅改动 `syncClassUI()` 中这段：
```js
inspector.id.textContent = sel ? sel.id : "—";
```
改为：
```js
if (sel) {
  const seqIdx = state.instances.indexOf(sel);
  inspector.id.textContent = "#" + seqIdx;
  inspector.id.title = "底层 id: " + sel.id;
} else {
  inspector.id.textContent = "—";
  inspector.id.title = "";
}
```

要点与边界：
1. **序号与画布脚标同源**：必须用 `state.instances.indexOf(sel)`，禁止另起一套计数。这样面板 `#16` 与画布 `#16` 永远一致，不穿帮。
2. **真实 id 不丢**：通过 `title` 属性携带（如 `title="底层 id: imvdm01sfn0m4"`），鼠标悬停可查，不占面板主视觉，对账/调试可用。
3. **仅改展示**：`sel.id` 本身、`state.instances` 结构、落盘 JSON 的 id 字段一律不动；`uid()`、撤销快照、修正记录、导出逻辑都不要碰。`p0~p15` 这类预标注实例也统一显示 `#序号`（不必区分来源，保持展示统一）。
4. **空态**：未选中时 ID 仍显示 `—`（或与现有「未选择」一致的占位），并清空 title。
5. 若 inspector ID 元素支持 `title`（普通文本节点改/设属性即可），无需新增 DOM；如该元素当前不是可承载 title 的容器，用 JS 设置 `elem.title` 即可。

## 明确不动
- 所有 `data/annotations/*.json`、修正记录、对比结果、`uid()`、`p` 前缀语义
- 后端 app.py、其他页面、骨架屏、首页可视化
- 不引第三方库

## 自测清单（5001 端口隔离目录实测，逐项过）
1. 打开任一张含人工新建实例的图（如 `coco_10707.jpg`），点选该实例：面板 ID 显示 `#序号`，与画布脚标一致
2. 鼠标悬停面板 ID：出现 `底层 id: imvdm...` 提示，与 JSON 中真实 id 相同
3. 点选预标注实例（如 `p0`）：面板同样显示 `#序号`，而非 `p0`
4. 未选中任意实例：ID 栏显示 `—`，无残留 title
5. 删除一个实例后，后续实例序号前移，面板与画布脚标仍一致（序号可变是预期行为）
6. 撤销/重做后序号正确，无错位
7. 保存后再刷新，序号显示不变、底层 id 与落盘一致
8. 回归：`data/annotations/`、`data/records/`、`dataset/`、`对比结果.csv` 的 md5 前后一致；对比页、列表页、画布其余功能正常

## 收工
1. commit（信息说明：画布选中面板 ID 栏改为序号展示 + 底层 id 悬停）→ push
2. 更新 CONTEXT.md 当前状态（记一笔 + 提交哈希）→ commit → push
3. 汇报：改动点（具体到行）、新建/预标注实例两种展示效果、自测 8 项结果、git 提交哈希
4. 提醒用户：重启 5000 服务 + Ctrl+F5 强刷后生效