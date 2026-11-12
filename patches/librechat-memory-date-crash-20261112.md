# 回忆页日期崩溃修复（2026-11-12）

## 问题
打开「我的回忆」页面时前端崩溃，React 错误边界显示 `RangeError: Invalid time value`。

## 根因
后端对「无具体日期」的记忆（occurrence_precision != "day"）把 occurred_at 序列化为空字符串（public_event / collaboration._source_snapshot）。前端多处 `new Date("")` 得到 Invalid Date，Intl.DateTimeFormat.format 抛 `RangeError: Invalid time value`，导致整个回忆页渲染中断。触发数据：/shared-memories 的 sources[0].occurred_at 为空字符串。

## 修复（前端防护，不改后端契约）
- SharedMemoryCard.tsx：occurred_at 空字符串回退到 shared.created_at。
- Memories.tsx groupMemories()：无日期记忆归入 undated 组，标签「日期不详」。
- MemoryCard.tsx / MemoryDetail.tsx：occurred_at 为空时显示「日期不详」。
- en/translation.json：新增 com_life_undated: 「日期不详」。

构建：cd products/librechat-custom/client && npm run build（52s）。生效：docker restart lifecompanion-librechat。

## 验证
浏览器 /memories（管理员）：正常渲染，0 console 错误；共同回忆时间显示「11月6日 10:52」（回退 created_at）；5 段无日期回忆归入「日期不详」组；/memories 与 /shared-memories 均 200。
