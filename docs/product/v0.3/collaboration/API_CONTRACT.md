# V0.3 协作 API 合约

前缀：统一网关 `http://127.0.0.1:3001/life-api`（容器内 life-core
`http://127.0.0.1:8010`）。身份一律来自服务端 JWT 会话，`actor_user_id`
不接受前端 body 传值。

## 身份与授权模型

```text
HTTP/Socket 请求
  -> validate_authenticated_session()
  -> actor_id := session.user.id          # 不从前端 body 读
  -> authorize(actor, resource, action, scope, now)
  -> load_only_authorized_records()
  -> AI tools receive minimal authorized data
  -> audit allow/deny
```

好友关系、Space 成员、共享回忆成员、direct 会话、事件订阅 scope 都必须在
服务端验权；`_can_read` 同时校验好友/成员关系、资源 owner、grant 的
resource_kind、resource_ids、有效期、撤销状态、agent_allowed 与拉黑。

## 关键路由

```text
GET    /api/v1/collaboration/me
PATCH  /api/v1/collaboration/me
GET    /api/v1/users/search
GET    /api/v1/friends
POST   /api/v1/friends/requests
POST   /api/v1/friends/requests/{request_id}/accept|reject|cancel
DELETE /api/v1/friends/{other_user_id}
POST   /api/v1/blocks/{other_user_id}
DELETE /api/v1/blocks/{other_user_id}

GET/POST /api/v1/spaces
GET    /api/v1/spaces/{space_id}
POST   /api/v1/spaces/{space_id}/invites
POST   /api/v1/space-invites/{invite_id}/accept|reject|cancel
PATCH  /api/v1/spaces/{space_id}/owner
POST   /api/v1/spaces/{space_id}/leave
DELETE /api/v1/spaces/{space_id}
GET/POST /api/v1/spaces/{space_id}/messages
PATCH/DELETE /api/v1/spaces/{space_id}/messages/{message_id}
POST   /api/v1/spaces/{space_id}/messages/{message_id}/reactions
GET/POST /api/v1/direct-messages/{peer_user_id}
GET    /api/v1/collaboration/events?scope_key=&after_id=&wait_seconds=

GET/POST /api/v1/grants
DELETE /api/v1/grants/{grant_id}
GET/POST /api/v1/grants/requests
POST   /api/v1/grants/requests/{request_id}/reject|cancel

GET/POST /api/v1/availability
DELETE /api/v1/availability/{window_id}
GET    /api/v1/shared-availability/{owner_user_id}
GET/POST /api/v1/shared-status

GET/POST /api/v1/shared-memories/invites
POST   /api/v1/shared-memories/invites/{invite_id}/accept|reject|cancel
POST   /api/v1/shared-memory-joins/{invite_id}/accept|reject
GET    /api/v1/shared-memories
GET    /api/v1/shared-memories/by-source
GET    /api/v1/shared-memories/{shared_id}
POST   /api/v1/shared-memories/{shared_id}/contributions|messages|invites|leave
POST   /api/v1/shared-memories/{shared_id}/messages/{message_id}/reactions

POST   /api/v1/spaces/{space_id}/agent/query
POST   /api/v1/shared-memories/{shared_id}/agent/query

GET    /api/v1/notifications
PATCH  /api/v1/notifications/{notification_id}
POST   /api/v1/care/forward-requests
```

## 关键失败语义（均有回归断言）

- 自加好友/自邀/自转达：400；重复好友申请：409。
- 非收件人接受邀请、跨群读写、跨用户读取私有记忆：403/404，且不泄露存在性。
- grant 撤销后旧请求重放：404/403，即时生效，不走缓存绕过。
- 消息写入使用 `client_message_id` 幂等；重复提交返回同一条消息。
- 关怀转达去重：同一授权下的重复请求返回同一条 notification。
