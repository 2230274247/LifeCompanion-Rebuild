# P03 LangGraph 状态机现状

2026-11-04；持久业务节点真实集成 PASS，P03 总体仍 PARTIAL。

已安装 LangGraph 1.2.19、langgraph-checkpoint-sqlite 3.1.3；
`ReminderWorkflow` 使用 SqliteSaver，thread_id 为 `reminder:<owner>:<draft>`。
同一进程内使用 RLock 避免并发 SQLite 初始化/同线程 checkpoint 写入冲突。
组件身份和许可证元数据见 `evidence/p03/dependency-metadata.json`。

当前 `workflow_version=2` 已替换旧的纯 `record_transition` 图。真实节点包括：
`load_authority`、`collect_missing`、`await_confirmation`、`apply_patch`、
`authorize`、`commit`、`active`、`update`、`cancel`、`unknown`、`reconcile`。
补字段、待确认、已创建和结果未知使用 `interrupt`，请求使用
`Command(resume=...)` 恢复。一次时间选择可完成补字段、授权检查和创建。
取消进入终态。非草稿正式任务使用 `reminder-task:<owner>:<reminder>` 线程。

SQLite 草稿、提交表和正式任务投影仍是业务权威，每次操作重新核验 owner、
revision 和授权。checkpoint 不代替业务数据库。旧图或失败节点从权威状态恢复，
不自动重放旧的远程写入。未知提交必须查询 Vikunja 的幂等标记恢复。
同一任务改期保留 ID，递增正式任务 revision，并同步草稿预览；
相同参数重试不重复 PUT、不递增版本。

真实证据：`evidence/p03/business-workflow-a27b9a639da042f9.json`：
跨 Core 重启的缺字段暂停、关闭授权403、三次并发确认仅一个真实任务、
改期幂等、取消重启终态，以及真实 SQLite trigger 注入本地投影失败后
unknown/reconcile 不新增上游任务，共八项检查通过。初始消息为隔离 Mongo
合成持久来源，经实际 LibreChat API 校验，无聊天生成请求。

新后端浏览器证据：`evidence/p03/business-ui-995bd011bc444bc0/`；
桌面键盘/390px触摸创建、取消、刷新、独立重登通过，两个线程均为版本2且已取消。
截图已查看；没有浏览器实际发送云端聊天。完整后端108项通过，模型请求0。
常用隔离8031已重载，见 `core-reload-business-workflow.json`。

后续仍需验证多进程同时操作、完整自然语言/歧义和同名选择、
长期通知边界、200人工标注；这些未由本次有限并发测试替代。
