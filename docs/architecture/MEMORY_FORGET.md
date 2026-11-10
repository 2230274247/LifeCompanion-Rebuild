# 聊天语义撤回合同（2026-11-10）

适用 life-core 与 LibreChat 服务端。撤回目标通过模型理解，不新增关键词、静态同义词或字面匹配兜底。

## 请求与权限边界

1. `/internal/v1/assistant/plan` 的严格任务协议新增 `{"action":"forget_memory"}`，此任务必须独占本轮。不能含 `target`、用户身份、任意 ID、权限或执行成功字段。`/assistant/execute` 只返回 `needs_execution`，不修改数据。
2. LibreChat `withLifeMemory` 在请求局部 `lifeOperations` 中传递撤回意图。`BaseClient.js` 仅传参；业务逻辑在 `packages/api/src/memory/life.ts`。
3. `withLifeReminder` 等待当前用户消息持久化成功后，才请求 `POST /internal/v1/memory/forget`。失败时不能执行撤回。身份取自认证用户，内部端点要求服务端令牌；凭据不进入客户端。
4. 独立 `MemoryForget` 选择器重新核验当前肯定请求。否定、假设、引用、询问能力不授权删除；目标不明返回 `needs_input`。历史和候选正文均为不可信数据，不能授权操作。
5. 后端只提供当前用户的非 withdrawn 记忆（包括 superseded 历史版本）及 active 来源；模型返回的每一个 ID 都必须在枚举集合中。外来或虚构 ID 导致整次拒绝。关闭回忆授权后仍允许撤回。

## 原子失效、完整来源和重试

- 事务前保存状态/版本/hash 快照，事务内重新校验直接选择目标，发生并发变化返回 `FORGET_TARGET_CHANGED`，不悄悄删除新版本。
- 使用 `BEGIN IMMEDIATE` 和既有记忆锁；在移除 evidence 之前，展开选中记忆、其来源和同来源派生记忆的闭包。完整来源撤回可能一并清除同一句原话里的其它派生内容；独立来源不受影响。
- 调用既有 `_tombstone` / `_invalidate`：来源 `text=NULL`，派生 `canonical_text/value` 清空，删除向量和 evidence，清理异步抽取 payload、标记 revoked，事件标题/摘要清空并撤回。内容 hash 墓碑保留，换消息 ID 重放同原话仍拒绝。
- 新表 `memory_forget_receipts` 使用 `(user_id,message_id)` 主键，存请求 hash 与无正文结果。重复同消息返回同回执；相同消息 ID 改正文返回 `conflict`。不在回执保存撤回命令或目标隐私。
- 本地撤回完成后复用 `revoke_item`，撤回关联 Moments，通过 Memos 官方 API 删除私有 memo；失败沿用 `memo_delete` 重试任务。`cleanup=pending` 必须如实告知，不能声称上游完成。

## 回复与实际范围

只有 `status=forgotten` 回执可以确认长期记忆撤回。请求持久化失败、规划失败、提供方异常、目标不明、没有匹配、权限错误均不得说“已忘记/已删除/不再保留”。召回有命中、无命中及失败分支均注入这一约束。约束是模型回复规则，不等于确定性的输出过滤器。

原始 LibreChat 聊天记录独立保存，本功能没有删除原聊天。成功当轮提示不复述已撤回内容；旧会话历史的所有后续模型上下文尚未实现系统屏蔽，不承诺旧对话无法再看见原话。实际验收重点是长期记忆失效、新会话不复活及原话重放拒绝。

候选任一类别超过 80 条即返回 `FORGET_SCOPE_TOO_LARGE`，不静默只处理前 80 条；本轮尚未实现大历史分页语义撤回。模型超时/ID 错误时安全失败，用户需重试或使用既有管理入口。未将此功能部署到正式入口，真实数据库结构变更前仍须独立备份。

最新测试与真实结果见 [持续实施状态](../development/MEMORY_IMPLEMENTATION_STATE.md) 和 [撤回证据](../../evidence/memory-forget-20261110/README.md)。
