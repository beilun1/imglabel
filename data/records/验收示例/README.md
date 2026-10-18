# P4 埋点验收示例（非人工过审成果）

本目录是 P4 开发自测时，由画布在 5001 端口**真实操作、程序自动生成**的产物，仅用于证明埋点链路可用：

- `修正记录.json` / `修正统计.json` / `修正统计.md`：10 条记录，覆盖 create / reclass / move / resize / delete / erase_mask / polygon / modify 全部类型，含一次"保存后撤销再保存"的会话替换与跨会话累计
- `annotations/`：对应 3 张图当时的标注 JSON（coco_10092 / coco_102707 / coco_106389），用于复核记录 ↔ mark 一致性

自测结束后，`data/annotations/` 已还原为预标草稿状态，正式 `data/records/修正记录.json` 从 0 开始，由用户在画布上逐张过审真实产生。**这 10 条不计入目标 60 条。**

复核：`python -c "import sys; sys.path.insert(0,'tools'); import records_stats as rs; print(rs.check_consistency(rs.load_records('data/records/验收示例'), rs.load_annotations('data/records/验收示例/annotations')))"`
