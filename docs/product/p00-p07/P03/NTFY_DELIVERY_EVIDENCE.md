# P03 通知真实证据

2026-11-04；服务端接受 PASS；浏览器系统通知与 Android 设备实际收到 UNKNOWN。

验收实例为隔离 ntfy：`127.0.0.1:8097`，Compose
`lcr-acceptance-20261103`。新建合成用户使用独立鉴权 topic。
不使用旧 `lifecompanion-ntfy` 的 8087 或 Silver 通知服务。

运行 `0f6f567301144310`：

| 证据 | 实际值 |
| --- | --- |
| 正式提醒 ID | rem_af42ead2bfe5441ea4703bb9db4e9cf3 |
| Vikunja task ID | 4 |
| 计划时刻 | 2026-11-04 00:46:00 Asia/Hong_Kong |
| 实际上游 notification.created | 2026-11-03T16:46:00Z |
| 第一次投递 | attempts=1，pending，NTFY_DELIVERY_FAILED，有 next_attempt_at |
| Core + scheduler 重启后 | attempts=2，accepted |
| 服务端接受记录时间 | 2026-11-04 00:46:32.863320 +08:00 |
| ntfy 缓存 | 一条，sequence_id 与 outbox 一致，标题与合成任务一致 |
| 重放两次 reconciliation | 无新增通知 |
| 匿名读取私有 topic | 403 |
| 本人站内 inbox | 一条真实消息 |
| 换账号读取 reminder_id | 404 |
| 模型请求 | 0，验收配置无模型 key，memory_model_calls=0 |

来源：`evidence/p03/delivery-recovery-0f6f567301144310.json` 和
`evidence/p03/delivery-recovery-live-console.txt`。私有 topic 和凭据未写入报告。

本次 PASS 证明 ntfy 服务端接受且本人可在站内取回消息。没有获取浏览器系统
Push 回执、Android 真机后台回执或用户确认，因此设备状态保留 UNKNOWN。

2026-11-04业务编排增量没有新增终端送达证据。新浏览器截图明确显示
“设备送达状态未知”，本次真实创建/取消与Core重载不能提升设备送达结论。
