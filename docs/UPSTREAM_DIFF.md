# Upstream Diff

2026-11-09 增补：已归档聊天提交 `7cf65d5fc428d3f308104ea871383603c523a91d`
为 `patches/librechat-memory-context-7cf65d5-20261109.patch`（8文件增量，基于该提交的父提交）。
该提交为前一阶段记忆注入修复，本轮归档不包含13个既有认证工作区改动；
本轮纯向量检索、历史注入与泛化验收发生在根仓库life-core、网关及scripts。
当前聊天支持DeepSeek/deepseek-chat；后文V0.1的deepseek-flash是历史记录。

基线：2026-11-02。以下差异均可通过两个独立上游 Git 仓库与根仓库历史追溯。

## LibreChat

本地补丁提交：

```text
7c2365cb376b48acb1591e48a6ef91e5c47c78e6
feat(lifecompanion): ingest persisted user messages
```

相对上游 `e8f3be08623663d4ad7f7241e693c94469b63bb0`：

| 文件 | 类型 | 用途 |
| --- | --- | --- |
| `api/app/clients/BaseClient.js` | 修改 | 用户消息持久化后调用 `life-core` 内部接入接口 |
| `librechat.yaml` | 新增配置 | DeepSeek OpenAI 兼容自定义端点 |

具体行为：

1. 只处理 `message.isCreatedByUser === true` 的服务端已持久化消息。
2. 携带 `savedMessage._id`、LibreChat 用户 ID、会话 ID、原始文本和服务端时间。
3. 使用仅服务端可见的 `LIFE_INTERNAL_TOKEN` 调用内部 API。
4. 4 秒超时；接入失败写警告，不阻断 LibreChat 本身的消息保存或模型回复。
5. 不在浏览器请求中暴露 `LIFE_INTERNAL_TOKEN`、Memos 令牌或 DeepSeek Key。

DeepSeek 配置：

- Base URL：`https://api.deepseek.com/v1`
- 模型：`deepseek-flash`
- 模型名通过官方 `GET /v1/models` 核验，见
  `evidence/deepseek-model-check.txt`
- Key 使用 `${DEEPSEEK_API_KEY}` 占位，仅真实值保存在被忽略的 `.env`

## Memos

没有修改 Memos 源码。集成通过 Memos 26.10.0 官方 API：

```text
POST /api/memos?memoId=<stable-uuid>
GET  /api/memos/<id>
```

写入使用服务端 Bearer PAT，`visibility` 固定为 `PRIVATE`，Memo ID 由业务事件
UUID5 稳定派生。

## 根仓库新增

- `services/life-core/`：FastAPI 业务服务、SQLite 持久化、事件抽取、
  授权、幂等和 Memos 适配。
- `apps/product-portal/`：零外部依赖的薄入口，用服务端健康探测显示真实状态。
- `infra/compose.baseline.yaml`：固定镜像、端口、本地卷、补丁挂载和内部网络配置。
- `tests/`、`docs/`、`evidence/`、`fixtures/`：测试、可追溯说明和脱敏证据。

## 明确没有做

- 没有把 LibreChat 与 Memos 数据库合并。
- 没有通过直接修改 Memos SQL 数据库写入回忆。
- 没有实现 SSO。
- 没有把 API Key 或 Memos PAT 写入前端或 Git。
- 没有修改、清理或迁移 `Silver-economy`。

## V0.2 增量（2026-11-02）

以上是 V0.1 的历史记录；本轮统一登录由 LibreChat React SPA 复用现有登录实现，
普通用户不再需要分别登录 Memos。不是新增跨服务身份提供商。

完整归档：`patches/librechat-v0.8.8-lifecompanion-v02.patch`，
应用基点仍为上述原版 commit；已包含 V0.1 钩子。应用说明见 `patches/README.md`。
本轮没有创建新 commit；不能把 V0.1 commit 当作 V0.2 的提交。

| LibreChat 路径 | V0.2 内容 |
| --- | --- |
| `client/index.html`、`client/public/assets/life.svg` | 拾光标题、页面元信息与已有银杏图标 |
| `client/src/App.jsx` | 使用既有主题注册表；隐藏音频改用 audio 元素 |
| `client/src/components/Auth/AuthLayout.tsx` | 登录页品牌统一 |
| `client/src/components/Life/` | 共用页头、导航、品牌主题、真实回忆列表/详情及组件测试 |
| `client/src/components/UnifiedSidebar/ExpandedPanel.tsx` | 共用产品导航及关闭按钮事件边界 |
| `client/src/components/UnifiedSidebar/mobile/Header.tsx` | 关闭按钮不把点击事件传作动画回调 |
| `client/src/components/UnifiedSidebar/**/__tests__/` | 桌面/手机开关参数回归测试 |
| `client/src/routes/Root.tsx`、`client/src/routes/index.tsx` | 保留原聊天路由和 Provider，加入回忆路由 |
| `client/src/locales/en/translation.json` | 按上游约定增加产品本地化 fallback 键 |
| `packages/data-provider/src/life.ts`、`index.ts`、`keys.ts` | 共用回忆契约、同源服务与查询键 |
| `librechat.yaml` | 保留 DeepSeek 配置，统一欢迎文案 |

根仓库的 Node 入口变为 SSE 流式网关；life-core 增加真实 Memos 读取、
分页/搜索/日期/详情、访问 JWT 验证、写入前 PAT 归属校验和用户作用域幂等。
没有迁移数据库、修改 Memos 源码或升级上游依赖。完整文件清单及实际验收见
`docs/development-log/README.md`。
# V0.2.1 当前归档说明

最新完整 LibreChat 补丁：
`patches/librechat-v0.8.8-lifecompanion-v021-memory-reminders.patch`，41 个文件。
基点仍为原版 `e8f3be08623663d4ad7f7241e693c94469b63bb0`；
包含所有新源码并保留原有差异。临时 index 应用检查通过，未触碰真实暂存区。
Vikunja/ntfy 完整克隆、固定 tag/digest、上游源码无差异；
Memos 仍无源码修改。版本与 API 证据见 `evidence/v02-memory-reminders/README.md`。
全部工作保持未提交，旧补丁与以下历史说明保留。

## Otis 应用内宠物（2026-11-05）

LibreChat 定制端新增一个聊天页内角色，未改动上游任何既有行为：

| LibreChat 路径 | 内容 |
| --- | --- |
| `client/src/components/Life/OtisPet/` | 新增目录：外壳、样式、原 Otis 引擎与 14 张表情贴图（2.5MB） |
| `client/src/routes/ChatRoute.tsx` | 引入并渲染 `<OtisPet />`，与 `<ChatView />` 同级 |
| `client/src/locales/en/translation.json` | 新增 5 个 `com_ui_otis_*` 键 |

`OtisPet/face/engine.ts` 与上游作品集逐字一致；`content.ts` 只把贴图路径改为
Vite 静态导入，`FaceCanvas.tsx` 只增加 `ariaLabel` 与兜底色。
溯源、文件清单与升级步骤见
`patches/otis-portfolio-lifecompanion-pet.md`；验收见
`docs/development-log/2026-11-05_11-50_Otis应用内宠物_开发验收.md`。
当前交付已把该改动和 V0.3 协作源码归档到
`patches/librechat-v0.8.8-v03-collaboration-20261106.patch`；补丁以 LibreChat
`e8f3be08623663d4ad7f7241e693c94469b63bb0` 为固定基点，并覆盖当前嵌套仓库
HEAD 与未跟踪测试脚本。
