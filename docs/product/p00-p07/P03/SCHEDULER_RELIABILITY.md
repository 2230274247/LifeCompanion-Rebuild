# P03 独立调度与恢复

2026-11-04；状态 PARTIAL。真实单次恢复链路 PASS，常驻部署与完整压力门槛尚未验收。

APScheduler 3.11.3 + SQLAlchemy 2.0.55 使用独立 SQLite JobStore；
稳定 job ID 为 `reminder-notification-reconciliation`，默认每 15 秒运行，
`coalesce=true`、`max_instances=1`、`misfire_grace_time=60`。
不得将 JobStore 同时交给多个 scheduler 写入。

Vikunja 是正式任务和到期事件来源；独立 scheduler 经带内部 token 的
POST `/internal/v1/reminders/reconcile` 恢复事件并投递。
`LIFE_REMINDER_SCHEDULER_EXTERNAL=true` 关闭 Core 内嵌 reconciliation 和轮询发送；
默认 false 保留现有运行兼容性。只有独立 scheduler 真实运行时才可切换为 true。
本轮没有把验收进程伪装成已经常驻部署的服务。

| 持久对象 | 用途 |
| --- | --- |
| Vikunja task / notification | 正式时间与停机期间到期事件 |
| reminder_notifications | 唯一 event_id、原子 claim、attempts、next_attempt_at、last_error |
| reminder_scheduler_runs | 每次调用开始/结束、遍历 owner 数、接受数和顶层异常码 |
| APScheduler SQLite | 稳定周期任务的独立持久 JobStore |

本轮修复：

1. 从“每个用户再全量遍历用户”改为每轮一次遍历。
2. 接受计划时刻前后一分钟内的上游通知时间，修复稍晚到达被漏掉。
3. outbox 的 not_before 不早于计划时刻，早到通知暂不发送。
4. 发送前核对 owner/task/当前 scheduled_at 对应 event_id，抑制改期旧通知。
5. 发送内容使用当前权威标题，避免旧 outbox 标题覆盖修改。

失败按既有指数退避再次进入 pending。进程重启恢复 sending 状态后，重试先查询
ntfy 缓存中的 sequence_id；同事件通过唯一键去重。本轮证明有限停机/重试范围内
一条通知，没有证明无限故障下的严格 exactly-once：缓存过期、取消与 HTTP 发送并发、
远端已接受而本地未落库等边界仍需进一步审计。

真实脚本：`scripts/acceptance_p03_delivery_recovery.py`。它使用全新隔离 SQLite、
合成账号、无模型 key、关闭内嵌调度、不可达 callback；先停 Core 等真实时钟到期，
再启动独立 scheduler。第一次 ntfy 访问真实连接失败，持久退避；重启两者后
第二次 accepted，重复 reconciliation 后缓存仍只有一条。
证据：`evidence/p03/delivery-recovery-0f6f567301144310.json`。

待补：完整一次性调度策略、历史通知分页、上游读取失败的细粒度审计、
同一 owner 大量事件、系统时钟跳变、长期离线、常驻启动与停机维护方案。

2026-11-04 01:50增补：正式任务新增revision，重复相同改期不再发PUT。
真实业务图验证改期保持原ID、取消后重启终态一致，证据
`business-workflow-a27b9a639da042f9.json`。本轮没有重做云端模型或ntfy
到期验收；既有投递证据仍按上文限定范围使用。8031 Core已安全重载，
没有启用外置调度开关，不能声称scheduler已常驻部署。
