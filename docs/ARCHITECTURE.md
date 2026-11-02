# Architecture

## 目标

保留 LibreChat 的成熟聊天体验和 Memos 的成熟时间轴能力，用一个独立的
`life-core` 服务承载身份映射、事件抽取、授权、幂等和未来的回忆任务。

## 运行组件

```text
浏览器
  ├── product-portal :3001
  ├── LibreChat     :3080
  └── Memos         :5230

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
`users` 表中确认映射；内部接入 API 只接受服务端令牌。

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
| `POST` | `/api/v1/reminders` | LibreChat JWT |
| `GET` | `/api/v1/reminders` | LibreChat JWT |
| `POST` | `/internal/v1/events/ingest` | `X-Internal-Token` |
| `POST` | `/internal/v1/users/bootstrap` | `X-Internal-Token` |

生图任务 API 尚未实现，因此没有用文本模型冒充图片模型。

## 幂等与恢复

- 事件按 `source_type:source_message_id` 和用户归属派生稳定 `event_id`。
- 同一用户、同一来源消息的接入尝试记录在 `ingest_attempts`。
- Memo 写入任务按 `memo_publish:<event_id>` 记录在 `task_runs`。
- Memos Memo ID 由事件 ID 的 UUID5 稳定派生。
- 状态机目前为 `pending` / `pending_consent` / `published` / `failed`。

## 数据最小化

- 事件只保留用于回顾的标题、摘要和来源引用，不复制完整会话。
- 内部请求日志只记录事件状态和来源 ID，不记录令牌。
- LLM Key 和 Memos PAT 仅在服务端环境变量中使用。
- 浏览器的产品入口只调用自己的健康状态接口，不接触密钥。

## 已知边界

- 各应用分别登录，未做 SSO。
- 单用户映射已有模型，但尚未实现完整多用户自助开户。
- 图片生成、长期记忆召回和移动推送尚未完成。
- Android 只能复用 HTTP API 和业务语义，不能直接把整个 Web 应用当作已交付 APK。
