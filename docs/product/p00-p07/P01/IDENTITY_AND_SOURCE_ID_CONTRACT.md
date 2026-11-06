# 身份与消息来源 ID 契约

## 主体映射

```text
LibreChat JWT sub / authenticated user id
  └─ life-core users.librechat_user_id (unique)
       └─ life_user_id (opaque internal owner id)
            ├─ Memos user id / per-user PAT mapping
            └─ Vikunja user id / per-user token mapping
```

前端传入的 `source_user_id` 不作为授权主体。用户路由通过已验证的 LibreChat bearer token 得到 `librechat_user_id`，再由 life-core 查唯一映射；资源 SQL 以 `life_user_id` 作为 owner 条件。内部摄取路由另需隔离部署的 `X-Internal-Token`，不能从公网网关访问。

## 消息与派生记录

| 字段 | 来源 | 用途 |
|---|---|---|
| `librechat_user_id` | 已验证 JWT | 认证主体映射键 |
| `life_user_id` | life-core 用户映射表 | 隔离业务记录 owner |
| `conversation_id` | LibreChat 持久会话 | 回溯定位会话 |
| `message_id` | LibreChat 持久用户消息 | 证据来源与聊天深链接 |
| `memory_id` / `reminder_id` | life-core 业务记录 | 被鉴权的详情资源 ID |
| `source_message_id` | life-core 请求体，随后由 LibreChat API复核 | 写入前确认该用户确实拥有未删除的原始用户消息且文本相同 |

外部来源校验使用同一 Bearer token 请求 `/api/messages/{conversation_id}/{message_id}`。跨账号请求不会因客户端自行替换业务 ID 而获得资源。

## 页面链接

- 记忆详情：`/knowledge/{memory_id}`；来源原话：`/c/{conversation_id}?message={message_id}`。
- 提醒详情：`/reminders/{reminder_id}`；来源原话同上。
- 回忆详情：`/moments/{moment_id}`。只有真实 owner 可访问且存在持久图片资产时才算已实现。
- 支持稳定 ID 的业务路径通过 React Router；未经识别的外部 URL 仍走原 Markdown 安全策略。

## 当前验证界限

8 个合成 LibreChat 账户均有独立映射和 Memos 身份。除 A 外的 B–H 对 A 的两个记忆 ID 和一个真实提醒 ID 均得到 HTTP 404；无效 bearer token 得到 HTTP 401。以上只证明该资源和身份路径，不等同于全 API、安全审计、生产账号自动开通或原生 IME 完成。
