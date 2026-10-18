# 橡皮擦图层级 验收示例（非人工过审成果）

橡皮擦改为"只擦当前选中实例"后，在 5001 隔离服务（临时标注/记录目录）上**真实操作、程序自动生成**的产物：

- 图片 coco_76731.jpg：A = p1 laptop，B = p0 dining table，笔迹同时经过 A、B
- 操作序列：选中 A → 橡皮局部擦（记 `erase_mask`，B 不变）→ 取消选中再擦（只出提示「请先点选要擦除的实例」，无记录、无撤销步）→ 再选中 A 擦光（记 `delete`，tool=eraser，A 标 deleted，选中清空）→ 保存
- `修正记录.json` / `修正统计.json` / `修正统计.md`：上述 2 条记录及统计
- `annotations/coco_76731.json`：保存后的标注 JSON（p1 mark=deleted，p0 mark=unchanged）

用户真实的 `data/annotations/`、`data/records/修正记录.json` 未被触碰。**这 2 条不计入目标 60 条。**

复核：`python -c "import sys; sys.path.insert(0,'tools'); import records_stats as rs; print(rs.check_consistency(rs.load_records('data/records/验收示例/橡皮擦图层级'), rs.load_annotations('data/records/验收示例/橡皮擦图层级/annotations')))"`
