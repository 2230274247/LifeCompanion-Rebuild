# Architecture

**当前增量：2026-11-06 V0.3 多账号协作，候选版本。**
在 V0.2/V0.2.1 的单用户记忆、回忆与提醒之上，新增好友、空间、共享回忆、
共享状态与可用时段、授权、直接消息与通知，并保持按 `life_user_id` 的数据隔离。
实现细节见 [V03_COLLABORATION.md](architecture/V03_COLLABORATION.md)。
下文保留 V0.2 基线结构；其中“单用户映射”“未实现多用户自助开户”的历史描述
已由 V0.3 增量文档更新。

## V0.3 多账号模型

```text
LibreChat account (login)
  -> LibreChat user id (JWT "id")
  -> life_user_id (life-core users table)
  -> 私有数据：memories / events / reminders / moments（按 life_user_id 隔离）
  -> 协作数据：friends / spaces / shared-memories / grants（显式双向确认）
```

身份仍以 LibreChat 的 HS256 JWT 为准，`life-core` 用共享 `JWT_SECRET` 校验签名与
`exp`。每个 `life_user_id` 只读自己的记忆、提醒、时刻与私人数据；跨用户可见性
必须经过好友请求、空间邀请或共享回忆邀请的显式接受。内部接口继续只接受
`X-Internal-Token`，网关仅放行 `server.mjs` 中白名单的公开路由。

## 目标

保留 LibreChat 的成熟聊天体验，在同一个 React SPA 中展示回忆；Memos 提供后端存储，用独立的
`life-core` 服务承载身份映射、事件抽取、授权、幂等和未来的回忆任务。

## 运行组件

```text
浏览器 -> 同源网关 :3001
  ├── /、/c/*、/memories/*、/api/* -> LibreChat :3080（统一 React SPA、聊天、用户、SSE）
  └── /life-api/api/v1/memories* -> life-core :8010 -> Memos :5230（服务端 PAT）

LibreChat API
  └── 服务端内部 HTTP + X-Internal-Token
        └── life-core :8010
              ├── SQLite（事件、映射、任务、提醒、授权）
              └── Memos 官方 HTTP API（服务端 PAT）
```

三个数据库边界保持独立：

- LibreChat 的 MongoDB 由 LibreChat 管理。
- Memos 的数据库由 Memos 管理。
- `life-core` 使用独立 SQLite 文件，保存业务索引和任务状态。

## 身份与授权

当前为明确标注的单用户内测映射：

```text
LibreChat user id
  -> life_user_id
  -> Memos resource / users/<username>
```

LibreChat 服务端从已认证请求中取得用户 ID，再通过内部令牌调用 `life-core`。
浏览器不能自行声明用户身份。`life-core` API 接受 LibreChat JWT，并在
`users` 表中确认映射；只接受带有效签名及未过期 exp 的 Bearer access token，
不接受 refreshToken Cookie。上游 Axios 认证恢复流程负责刷新访问令牌。
内部接入 API 只接受服务端令牌，网关禁止暴露内部接口。
Memos 写入前核对 `/api/auth/me` 与映射用户，读取时核对 Memo creator、PRIVATE 与 NORMAL 状态。

每条事件记录：

- `event_id`
- `user_id`
- `source_type`
- `source_message_ids`
- `conversation_id`
- `occurred_at`
- `title`
- `summary`
- `confidence`
- `consent_state`
- `status`
- `memo_ref`
- `idempotency_key`
- `attempts`
- `error_message`
- 创建与更新时间

## 主数据流

1. 用户在 LibreChat 发送新消息。
2. LibreChat 持久化用户消息。
3. `BaseClient.js` 通过服务端内部请求把消息交给 `life-core`。
4. `life-core` 过滤未来计划、否定、问句和无生活事件信号的内容。
5. 通过后生成事件；若用户未授权，状态为 `pending_consent`，不写 Memos。
6. 用户已授权时，通过官方 API 写入 `PRIVATE` Memo。
7. 事件状态改为 `published`，保存 Memos 引用和任务执行记录。
8. 同来源消息重试时，返回同一业务事件和同一 Memo 引用。

## 当前 API

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| `GET` | `/health` | 无 |
| `GET` | `/api/v1/me` | LibreChat JWT |
| `PATCH` | `/api/v1/me/settings` | LibreChat JWT |
| `POST` | `/api/v1/events/extract` | LibreChat JWT |
| `GET` | `/api/v1/events` | LibreChat JWT |
| `POST` | `/api/v1/memories/publish` | LibreChat JWT |
| `GET` | `/api/v1/memories` | LibreChat JWT |
| `GET` | `/api/v1/memories/{event_id}` | LibreChat JWT、当前用户归属 |
| `POST` | `/api/v1/reminders` | LibreChat JWT |
| `GET` | `/api/v1/reminders` | LibreChat JWT |
| `POST` | `/internal/v1/events/ingest` | `X-Internal-Token` |
| `POST` | `/internal/v1/users/bootstrap` | `X-Internal-Token` |

回忆列表兼容保留 `memories` 字段，新增 `page`、`page_size`、`total`、`has_more`。
筛选为 q（标题与摘要）、on_date（香港日期）、order（asc/desc），最大每页 50 条。
仅读取当前用户的已发布事件对应 Memo，不开放任意 Memo ID 或其他用户的记录。
返回的 content 与 tags 来自 Memos 官方 API；Memos 不可用时返回 502，不能冒充空列表。
本轮没有提供无 life-core 事件索引的手写 Memo 浏览能力。

生图任务 API 尚未实现，因此没有用文本模型冒充图片模型。

## 幂等与恢复

- 新事件幂等键为 `life_user_id:source_type:source_message_id`，避免跨用户同来源 ID 冲突。
- 既有事件与键不迁移：按原用户与来源 ID 查 ingest_attempts，旧记录仍返回原事件和 Memo。
- 同一用户、同一来源消息的接入尝试记录在 `ingest_attempts`。
- Memo 写入任务按 `memo_publish:<event_id>` 记录在 `task_runs`。
- Memos Memo ID 由事件 ID 的 UUID5 稳定派生。
- 状态机目前为 `pending` / `pending_consent` / `published` / `failed`。
- 网络失败记录 failed 与安全原因；同来源重试会重试失败发布，稳定 Memo ID 防止重复创建。
- 不同消息描述同一事件尚未语义归并；没有新增分组字段或数据库迁移。

## 数据最小化

- 事件只保留用于回顾的标题、摘要和来源引用，不复制完整会话。
- 内部请求日志只记录事件状态和来源 ID，不记录令牌。
- LLM Key 和 Memos PAT 仅在服务端环境变量中使用。
- 浏览器只持有 LibreChat 登录态；Memos PAT、DeepSeek Key、内部令牌不进入前端。

## 已知边界

- 用户交互统一为一个 React SPA 与一次 LibreChat 登录；Memos 原生页仅供维护。
- 无单独的身份服务或 Memos 浏览器登录交换。已签发的 access JWT 沿用上游到期语义，
  未增加跨服务即时撤销列表；登出清除客户端登录态，不应宣称具备即时 JWT 吊销。
- 单用户映射已有模型，但尚未实现完整多用户自助开户。
- 图片生成、长期记忆召回和移动推送尚未完成。
- Android 只能复用 HTTP API 和业务语义，不能直接把整个 Web 应用当作已交付 APK。
