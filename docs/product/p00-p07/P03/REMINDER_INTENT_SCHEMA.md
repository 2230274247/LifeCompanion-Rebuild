# P03 提醒草稿协议

2026-11-04；状态 PARTIAL。本文描述当前代码及缺口，不代表全部任务书字段已经实现。

业务权威为 Vikunja 任务与 Life-core SQLite 投影。`reminder_drafts` 保存原话、
来源消息、会话、owner、字段、revision 和状态；`reminder_submissions` 保存创建请求的
幂等键、上游回执和正式 reminder_id。候选草稿不能被当成已经创建的提醒。

| 当前字段 | 说明 |
| --- | --- |
| draft_id / revision | 草稿标识和乐观锁版本 |
| conversation_id / source_message_id / source_text | 原话及来源；服务端通过当前用户的 LibreChat API 核验 |
| title | 保留“绿色 U 盘，不是银色”等限定词；尚无独立 negated_constraints 字段 |
| event_date / event_time | 事件日期与时刻 |
| reminder_date / reminder_time | 另行指定的提醒日期与时刻 |
| lead_minutes | 未单列提醒时刻时，从事件时刻减去提前分钟数 |
| timezone | IANA 时区；用后端时钟解析相对日期，检查夏令时缺失/歧义 |
| place | 当前地点字段 |
| missing_fields / preview / quick_choice | 缺失信息、最终时刻预览与快捷选项 |
| reminder.reminder_id | 正式任务成功并落库后才出现 |

`DraftFields` 使用 Pydantic `extra=forbid`。分钟精度、未来时间、合法 IANA 时区和
非负提前分钟数由后端检查。按用户原话中显式 IANA 时区优先，其他情况下使用既有规则。

API：POST `/api/v1/reminder-drafts`；PATCH `/{id}` 携带 `If-Match`；
POST `/{id}/select` 携带 revision 和选择字段；POST `/{id}/confirm` 携带幂等键；
DELETE `/{id}`；POST `/{id}/reconcile`。修改中/结果未知的创建只允许查询恢复，
不得直接再次向 Vikunja POST。

已验证：真实来源校验、只缺时间、限定词保留、一次选择后正式创建。
证据：`evidence/p03/draft-live.json`。该证据的原话由验收脚本直接写入隔离 Mongo，
然后用 LibreChat 官方 HTTP 接口读取；不等同于用户在浏览器发送消息的完整 E2E。

2026-11-04 增补：内部自动入口先执行 `reminder_intent.automatic_action_guard`。
明确否定返回 `NO_ACTION`，引用/第三人返回 `QUOTED_THIRD_PARTY`，
条件句或提醒他人返回 `UNCERTAIN` 并澄清，过去叙述不自动创建。
本轮发现旧入口将“不用提醒我”误建任务，复现后修复；补充的“不再/不想”
同样先复现两项失败再修复。“不是银色”“不用提前”“别忘提醒我”
和“我和朋友开会”作为正向回归；明确无需提前时 lead_minutes=0。
有限规则只作为自动执行前的保守排除，不能作为完整语义分类器。

真实内部HTTP/Vikunja结果：11条负向无草稿/任务增长，2条正向各创建一个任务，
限定词和09:00时刻保留，随后取消；`intent-guard-live-c35a53792bc046b9.json`。
该脚本使用可信内部桥接的合成输入ID，不替代浏览器发送/来源链路或200人工标注。
草稿与正式任务由版本2业务图执行，正式 reminder.revision 初始1，改期/取消递增；
相同参数重试不增加版本。

缺口：任务书的统一 intent 枚举、target_user、confidence、time_precision、
独立否定约束、多个事项、周五解析及建议拒绝频控尚未完整实现或验收；
不得据现有解析器单测宣称 REM-07/08/09/12 通过。
