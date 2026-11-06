# V0.4 Android 原生客户端架构

> 状态：规划（DESIGN ONLY，2026-11-06）。代码尚未创建，本文件描述技术选型、分层、
> 认证策略与可复用 API 面，供 P0 探针与后续阶段对齐。实施见
> [V0.4 实施计划](../product/v0.4/实施计划.md)。

## 1. 定位

在既有 Web（LibreChat React SPA + life-core + Memos）之外，新增一个**原生 Android 客户端**，
只复用现有网关 API（`:3001` 的 `/api` 与 `/life-api`），不修改后端。客户端承载聊天、回忆、
提醒、时刻与 V0.3 协作，界面采用 Meta Muse 的陪伴式消息心智模型。

## 2. 分层架构

```text
Compose UI (Screen / Component)
  └── ViewModel (UiState + Flow)
        └── Repository (domain)
              ├── DataStore / EncryptedPrefs  (会话与偏好)
              ├── Room                        (离线缓存 / 待发送队列)
              └── DataSource (Retrofit / OkHttp / SSE)
                    └── 网关 :3001
                          ├── /api/*      -> LibreChat（登录 / 聊天 / 流式）
                          └── /life-api/* -> life-core（回忆 / 提醒 / 协作）
```

- 单向数据流：UI 只订阅 `UiState`，事件经 ViewModel → Repository → DataSource。
- 依赖注入用 Hilt；异步统一 Coroutines + Flow；错误在 Repository 层转成稳定的
  UI 错误码，不透传原始异常 / 令牌 / 请求体。

## 3. 网络与流式

- REST：Retrofit + OkHttp + kotlinx.serialization（或 Moshi）。
- 流式：SSE 用 `okhttp-sse`（或 Ktor Client 的 SSE），**逐段渲染、不缓冲整段**；
  处理分段结束标记、超时、中断与恢复。
- 拦截器：统一注入 `Authorization: Bearer <access_token>`；401 时触发刷新或重登，
  不把凭据写日志。

## 4. 认证与安全存储

```text
POST /api/auth/login  { email, password }
  -> { token (HS256 access JWT), user }
```

- `token` 即 life-core 也认的 access JWT；后续请求带 `Authorization: Bearer <token>`。
- 安全存储：access / refresh 用 **EncryptedSharedPreferences 或 Android Keystore** 加密，
  禁止明文 SharedPreferences；登出清除。
- 关键风险（P0 验证）：登录中间件含 `requireSameOrigin`、登录限流；`POST /api/auth/refresh`
  是 Cookie 会话机制。原生无 Origin / Cookie，需验证能否通过登录与续期；若不能，定
  「短会话重登」策略或回到「最小后端调整」决策点。

## 5. 离线与幂等

- 待发送消息进 Room 队列，WorkManager 重试；复用服务端 `client_message_id` 幂等，
  重复提交返回同一条消息，避免弱网重发产生重复消息 / 事件 / memo。
- 离线只做「发送队列 + 只读缓存」，不做把后端语义复制到客户端的离线全文检索。

## 6. 可复用 API 面

认证与聊天（LibreChat，经 `/api`）：

```text
POST /api/auth/login | refresh | logout | register
会话 / 消息 / SSE 流式（具体端点由 P0 实测确认）
```

业务与协作（life-core，经 `/life-api`，仅公开白名单路由）：

```text
/api/v1/me  /api/v1/me/settings
/api/v1/memories  /api/v1/memories/{event_id}
/api/v1/knowledge  /api/v1/knowledge/recall  /api/v1/knowledge/{memory_id}
/api/v1/reminders  /api/v1/reminders/{reminder_id}  /api/v1/reminder-notifications
/api/v1/moments  /api/v1/moments/{moment_id}  /api/v1/moment-settings
/api/v1/friends  /api/v1/friends/requests  /api/v1/blocks
/api/v1/spaces  /api/v1/spaces/{id}/messages  /api/v1/direct-messages/{peer}
/api/v1/shared-memories  /api/v1/shared-memories/{id}
/api/v1/grants  /api/v1/grants/requests
/api/v1/availability  /api/v1/shared-status  /api/v1/notifications
/api/v1/care/forward-requests
```

完整路由以 `apps/product-portal/server.mjs` 白名单与 `docs/product/v0.3/collaboration/API_CONTRACT.md`
为准；内部接口与 `X-Internal-Token` 不出网。

## 7. 技术栈清单

| 关注点 | 选型 |
| --- | --- |
| 语言 / UI | Kotlin + Jetpack Compose + Material3 |
| 架构 / DI | MVVM + Repository，Hilt |
| 网络 / 流式 | Retrofit + OkHttp + okhttp-sse（或 Ktor Client） |
| 序列化 | kotlinx.serialization |
| 图片 | Coil |
| 安全存储 | EncryptedSharedPreferences / Android Keystore |
| 轻量 KV | DataStore |
| 离线缓存 / 队列 | Room + WorkManager |
| 导航 / 异步 | Compose Navigation + Coroutines / Flow |

## 8. 建议目录结构

```text
apps/android/
  app/                     # 应用模块
    src/main/java/...
      ui/                  # Compose Screen / Component（chat / memories / reminders / collab / pet）
      viewmodel/           # UiState + ViewModel
      data/                # Repository + DataSource + dto + db + prefs
      di/                  # Hilt 模块
      auth/                # 登录 / token 管理 / 拦截器
    src/main/res/          # 资源与主题（雾青苔绿 + 银杏黄）
  gradle/libs.versions.toml
  build.gradle.kts / settings.gradle.kts
```
