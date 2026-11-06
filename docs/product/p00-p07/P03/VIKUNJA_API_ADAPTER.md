# P03 Vikunja 适配器

2026-11-04；状态 PARTIAL。

隔离实例：`lcr-acceptance-20261103-vikunja-1`，仅本机端口 3461，
API 前缀 `/api/v2`。镜像锁定
`sha256:f7dc8428d10aef17f3075886d3c1c022f566ec456f88985f02c137f4fc534576`；
版本身份沿用 P00 实测记录，不凭任务书中的版本猜测端点。

`app/reminders.py` 通过实际 v2 API 操作：

- POST `/projects/{project_id}/tasks`：创建，包含 reminders 和幂等恢复标记。
- GET `/tasks`、GET `/tasks/{id}`：同步正式状态。
- PUT `/tasks/{id}`：原 task ID 修改；对应 Life-core reminder_id 保持不变。
- DELETE `/tasks/{id}`：取消；重复取消由本地终态返回，不再重复远程删除。
- GET `/notifications`：找回停机期间产生的 `task.reminder`。

`app/provisioning.py` 为每个 Rebuild owner 创建独立 Vikunja 用户、项目、作用域 token、
webhook 和 ntfy 私有 topic。凭据由既有 DPAPI 保护，仅保存在已忽略的隔离运行目录。
正式 API 响应不暴露 API token、ntfy 密码或 webhook secret。

远程时刻以 UTC 写入；Vikunja 按分钟调度，非整分钟输入向后取整，避免提前提醒。
Life-core 的事件时刻与提醒时刻分开存于草稿预览。生产配置、旧数据库与上游镜像未修改。

真实验收：`live-reminder-lifecycle.json` 覆盖创建、更新、取消、重复取消、
跨账号 404 和重启恢复；`delivery-recovery-0f6f567301144310.json` 进一步验证真实时钟、
改期、取消后原时刻无消息、ntfy 私有读权限和停机恢复。证据位于 `evidence/p03/`。

仍缺：分页通知历史恢复的完整验证、上游变更与本地并发改期/取消竞态、
完整版本/安全公告复核。真实接口可用不等于所有调度边界均已验收。

2026-11-04增补：`business-workflow-a27b9a639da042f9.json`证明三次并发
确认只创建一个任务；真实SQLite trigger使远程成功/本地投影失败后，
跨Core重启reconcile查回原任务，不再次创建。改期保持原ID且revision递增，
同值重试不增加版本。取消时远程已404可恢复本地终态。负向排除与正向
对照的实际API证据见 `intent-guard-live-c35a53792bc046b9.json`。
