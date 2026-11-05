# V0.3 多账号协作架构

> 状态：候选版本（`v0.3.0-deploy-rc1`）。单元测试通过，完整浏览器/API 回归
> 未在本轮打包中重跑，详见开发日志与 `deploy/ubuntu/README.md`。

## 1. 目标

在 V0.2 的单用户记忆/回忆/提醒之上，加入真正的多账号：

- 多用户注册、登录、退出与会话管理（复用 LibreChat 账号体系）
- 不同用户的数据与权限隔离
- 好友、空间、共享回忆、共享状态/可用时段、授权、直接消息与通知
- 服务重启后账号与业务数据保留（SQLite + MongoDB + 命名卷）

## 2. 组件与数据流

```text
浏览器 -> gateway :3001
  ├── /、/api/*、/c/*         -> LibreChat :3080（登录、聊天、用户、SSE）
  └── /life-api/api/v1/*      -> life-core :8010（协作、记忆、提醒、共享回忆）

LibreChat 服务端
  └── X-Internal-Token -> life-core /internal/v1/*（记忆抽取、提醒执行）
```

`server.mjs` 是唯一入口，只放行白名单内的 `/life-api` 公开路由，内部接口与
`X-Internal-Token` 不出网。SSE 与模型流式响应经 `pipe` 直通，不缓冲。

## 3. 身份与隔离

LibreChat 签发 HS256 JWT；`life-core` 用共享 `JWT_SECRET` 校验签名与 `exp`，
从 `id` 得到 `life_user_id`。核心表按 `life_user_id` / `owner_user_id` 隔离：

- `users`：LibreChat → life-core → Memos 的映射与授权
- `events` / `memories` / `reminders` / `moments`：私有数据
- `collab_*`：好友、空间、共享回忆、授权、状态、可用时段、消息、反应

跨用户可见性必须经过显式确认（好友请求接受、空间邀请接受、共享回忆邀请接受）。
`blocks` 表提供单向屏蔽；`grants` 提供可撤销的资源级授权。

## 4. 协作能力

- 好友：搜索用户、发送/接受/拒绝请求、删除好友、屏蔽
- 空间：创建、邀请、加入、离开、转让 owner、成员消息与反应
- 共享回忆：按来源共享、邀请/接受、成员贡献、消息与反应、代理问答
- 状态与可用时段：共享状态、可用时段、按用户读取
- 直接消息：一对一消息与反应
- 授权：资源级 grant 与 grant 请求
- 通知：协作事件通知、已读标记

## 5. 与 V0.2 的关系

V0.2 的记忆抽取、回忆、提醒与图片生成保持独立；V0.3 在其上增加协作表与
`collaboration_router`，没有删除或禁用 V0.2 能力。旧 SQLite 数据通过
`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` 兼容迁移。

## 6. 部署

Ubuntu 24.04 Docker Compose 部署见 `deploy/ubuntu/`：

- `gateway`：Node 24，代理前端与 `/life-api`
- `life-core`：Python 3.12，FastAPI + SQLite
- `librechat`：上游 v0.8.8 镜像 + V0.3 自定义前端/API 产物
- `mongo` / `meili`：LibreChat 数据与搜索
- `memos`：V0.2 记忆召回上游（可选）
- `vikunja` / `ntfy`：定时提醒与推送
