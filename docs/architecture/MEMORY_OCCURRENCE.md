# 事件发生日期与记录时间合同

更新：2026-11-10。配套 [实施状态](../development/MEMORY_IMPLEMENTATION_STATE.md) 与 [真实合成验收](../../evidence/memory-occurrence-20261110/README.md)。

## 日期的含义

`memory_items.valid_from`、`memory_evidence.message_at` 与来源的 `recorded_at` 仍表示消息/记录时间。`created_at` 是数据库写入时间。它们都不能作为事件发生日期的缺省值。

`memory_items` 与 `events` 各增加三列：

| 字段 | 含义 |
| --- | --- |
| occurrence_start | 用户时区下的日历起始日期，YYYY-MM-DD；未知为 NULL |
| occurrence_end | 日历结束日期，包含当天；未知为 NULL |
| occurrence_precision | day / week / month / year / unknown |

范围为**包含首尾的日期区间**。月份精度不表示在首日发生，周/年同理。未知日期不能进入日期限定的事件概览；仍可通过纯语义检索找到。

兼容字段 `events.occurred_at` 保留原 NOT NULL 结构。只有 day 精度写用户时区零点，其他写空字符串；零点仅作兼容日期载体，不代表真实发生时刻。公开 API 与 UI 依赖三项 occurrence 元数据，不显示推测时分。

## 抽取与日历算术

模型输出严格 `Occurrence`：`expression/unit/offset/weekday/year/month/day`。expression 必须是该候选原话证据的子串。模型负责理解表达，后端负责日期算术；相对时间锚定原始消息时刻并转为用户时区，不锚定后台执行时间。周一为周起点，weekday 为 0–6。

例如消息时间为 2026-11-02：

| 原话 | 符号表达 | 保存结果 |
| --- | --- | --- |
| 上周六 | week, offset=-1, weekday=5 | 2026-10-31，day |
| 上个月 | month, offset=-1 | 2026-10-01 至 10-31，month |
| 距离这条消息三个月之前 | month, offset=-3 | 2026-08-01 至 08-31，month |
| 去年 | year, offset=-1 | 2025-01-01 至 12-31，year |
| 我参观了陶艺展览 | unknown | NULL / NULL / unknown |

已有离线抽取器使用 `explicit_occurrence` 支持明确日历语法；它用于解析时间，不参与内容召回，不是关键词或同义词兜底。复杂表达依赖真实模型输出符号协议；不可靠或超出协议能力时保留 unknown。相对月同时指定 day 等不受支持的组合严格拒绝。未来起点不作为已经发生的事件日期。

## 写入、索引与消费

- 新事件 semantic_key 的日期部分来自 occurrence。未知/范围附消息锚点摘要，减少不同消息中的未知事件错误合并。
- 事件行与记忆行同时保存相同日期元数据。直存管理测试入口同样不默认发生于消息当天。
- 时间筛选按 `event_start <= query_end AND event_end >= query_start` 判断相交。月份记录可能与某日相交，但证据与回答必须保留月份精度，不能说该日确实发生。
- 概览 total_count 只统计窗口内可分页的事件；未确定日期的事件和原话覆盖单列 undated_count。已知但窗外的事件不进入 undated。
- 聊天证据将事件消息时间标为 recorded_at，透传 occurrence；禁止以旧 since、semantic_key 或 recorded_at 推断发生日。
- 回忆列表、详情及共同回忆显示日期/月/年/周范围或“发生日期不详”。共同回忆来源现查实际事件；Moments 生成窗口仅是 recording_window_start，不表示发生日期。好友、成员与共享权限机制保持原有边界。
- 撤回清空新日期列和兼容 occurred_at，避免正文清除后新增元数据残留。

## 旧数据、升级与回滚

迁移只幂等追加列，不重建表，不修改旧正文、旧 semantic_key 或原 occurred_at。旧记录新列默认 unknown，因为旧日期可能正是消息日期污染，不能把它认定为已核验发生日。

本轮只升级临时测试数据库与全新隔离合成数据库，没有迁移真实用户数据库，也没有批量重新抽取历史原话。历史记录将显示日期不详，直到有独立核验/受控重抽取。不得宣称本轮已修复所有历史日期。

正式使用前：停止写入并独立备份 SQLite 及其有状态关联，校验备份可读；部署后端、共享类型和前端一致版本；核对旧数据 unknown 与新日期测试。旧程序能忽略追加列，但会恢复旧日期解释缺陷；回滚时恢复匹配版本与已验证备份，不通过删除列或重写正文倒退。

## 验证边界

真实 worker → DeepSeek → SQLite → 官方 Memos API，以及真实规划/概览/语义查询已验收。正式 `withLifeMemory` 包入口接实时 life-core 再调用 DeepSeek 验证了日期回答，此项属于包级集成。

现有聊天容器重建被自动审批拒绝，理由为干扰运行中的工作负载；没有换方式重启该容器。包级集成不能替代完整持久化聊天、正式入口登录或生产部署验收。UI 使用本工作树真实组件和明确的合成 API 夹具，具体证据以独立日志为准。
