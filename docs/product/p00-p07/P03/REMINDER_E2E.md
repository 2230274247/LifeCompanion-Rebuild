# P03 端到端验收

2026-11-04；总体 PARTIAL。

仅以当前 Rebuild 隔离运行作证据。单测辅助定位问题，不代替产品路径验收。

| 场景 | 当前结论 | 证据或缺口 |
| --- | --- | --- |
| REM-01 绿色 U 盘仅补时间 | PARTIAL | draft-live.json + chips-live-ui.json：真实 Chip 键盘/触摸创建、限定词、取消与重登；原话/助手为持久化夹具，尚非浏览器实际发送 |
| REM-02 事件 15:00 / 提醒 09:00 | PARTIAL | business-workflow-a27b9a639da042f9.json：真实 API/图/Vikunja 字段分别正确；完整实时 UI 场景待验 |
| REM-03 缺日期 / 提前 120 分钟 | PARTIAL | 同上：真实 select 恢复图，17:00减120分钟得到15:00；浏览器日期 Chip 待验 |
| REM-04 潜在日程不得擅自创建 | PARTIAL | 现有规则及单测不足以证明所有真实语言路径 |
| REM-05 改期取消全处一致 | PARTIAL | 真实 API、Vikunja、重启状态与原时间不投递已验；完整新会话改期 UI 待验 |
| REM-06 幂等 | PARTIAL | 三次真实并发确认仅一个任务；SQLite故障后unknown重启/reconcile不重复POST；完整多进程压力待验 |
| REM-07 IANA/跨年 | PARTIAL | 后端校验存在，周五等解析尚有缺口 |
| REM-08 拒绝/第三人 | PARTIAL | intent-guard-live-c35a53792bc046b9.json：11条负向0草稿/任务、2条正向真实创建；不是完整语言矩阵 |
| REM-09 同名/模糊目标 | PARTIAL | 尚无完整真实歧义矩阵 |
| REM-10 真实定时渠道 | PASS | delivery-recovery-0f6f567301144310.json；设备送达 UNKNOWN |
| REM-11 任务隔离 | PASS | permissions-live.json：跨账号读/修改/取消正式任务及操作草稿均拒绝，owner 状态未变；ntfy 匿名 403 |
| REM-12 200 人工标注意图 | UNVERIFIED | 无经人工复核的 200 条数据与 Macro F1 报告，不用自造标签冒充 |

真实脚本及最新结果：

- `acceptance_p03_live.py`：HTTP 创建、更新、取消、重复取消、Core 重启、跨账号。
- `acceptance_p03_chat_draft.py`：真实 LibreChat 登录与来源读取、草稿、正式任务、来源回溯。
- `acceptance_p03_delivery_recovery.py`：真实到期、Core 停机、通知故障、独立 scheduler 重启。
- `acceptance_p03_chips_ui.cjs`：浏览器键盘/触摸/取消/新登录恢复；结果以 chips-live-ui.json 为准。
- `acceptance_p03_business_workflow.py`：持久业务图、并发确认、改期取消、真实故障与重启恢复。
- `acceptance_p03_business_ui.py`：新后端及独立网关的桌面/手机真实浏览器操作。
- `acceptance_p03_intent_guard.py`：真实内部桥接HTTP/Vikunja，否定与第三人排除及正向对照；输入ID合成，非完整浏览器聊天来源证明。
- 最新 `pytest services/life-core/tests -q`：108 passed，1 个上游 trustcall 弃用警告；
  `business-and-intent-final-regression.txt`。原88项结果保留为历史证据。

首次 Chip 浏览器尝试未显示合成消息卡片，保留
`chips-live-ui-first-failure.json`。验收夹具原来把独立根消息追加到已有会话，
不在当前选中分支；第二次改为独立会话仍缺助手消息，卡片实际挂载在助手
parentMessageId 下。第三次卡片已通过选择、取消与刷新，但测试直接读取详情漏了
网关 `/life-api` 前缀而失败。修复这些夹具/测试路径后最终重跑 PASS：
桌面 Tab/Enter、390px 触摸、44px 目标、无横向溢出、取消后刷新和独立登录均通过。
生成端点被阻断，generation_attempts=0。截图已人工查看移动视口。

权限矩阵首次调用不存在的 GET draft 单项端点收到 405；这不是越权成功。
依据真实路由改用按会话列表（仅返回本人草稿），重测后 9 项检查 PASS，
其中8个跨账号读写操作返回404，列表返回空，原 owner 标题/时间/状态保持不变。
初次失败保存在 permissions-first-failure.json。

本轮已补真正的 LangGraph 业务编排；新图浏览器证据在
`business-ui-995bd011bc444bc0`，使用独立临时 Core，模型请求0。
当前8031已安全重载新代码，配置未变、调用账本未增长。
尚未达到阶段完成门槛：所有自然语言场景、200 人工标注、
完整多进程/投递并发与终端通知。P04-P07 尚未完成。
