# Upstream Diff

基线：2026-11-02。以下差异均可通过两个独立上游 Git 仓库与根仓库历史追溯。

当前可部署快照（2026-11-04）：
`patches/librechat-v0.8.8-rebuild-p00-p07-20261104.patch`，68 个文件，
SHA-256 `25531395ba1548c4fe57f0e2ef91500b5d07f4eaba2ca3dcdac574a14df35f3f`。
该补丁包含截至 P07 的继承差异，已在原版 commit
`e8f3be08623663d4ad7f7241e693c94469b63bb0` 上通过临时 index 应用检查。

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

## 2026-11-04 Rebuild累计归档

当前源码快照另存 `patches/librechat-v0.8.8-rebuild-p00-p04-20261104.patch`，
60份文件、195676字节；临时index原版应用检查通过，真实index未变。
含已有P00-P03修改及P04的retry_allowed契约、未知结果禁止重提和文案/测试，
不是本轮纯增量，也不表示P04图像能力交付。
证据 `evidence/p04/upstream-patch-delivery.json`；无Key/运行数据归档。

八维评分之后的最新累计源码补丁：
`patches/librechat-v0.8.8-rebuild-p00-p04-scoring-20261104.patch`，
60文件、208236字节；SHA-256
`99ee49154b129c6555676671c5b1c7d311c296df11fb8cb6875556acccaf8eee`。
基点仍为原版e8f3be08623663d4ad7f7241e693c94469b63bb0，临时索引应用检查
通过，真实暂存区未变。证据`evidence/p04/upstream-scoring-patch-delivery.json`；
包含继承差异，不是纯P04增量。

P05天气聊天卡之后的累计补丁：
`patches/librechat-v0.8.8-rebuild-p00-p05-weather-chat-20261104.patch`，
63文件、223838字节；SHA-256
`c68723e1cbe970babd2a6dab96238cf0e37408f5173055976fb9f8631b5fe859`。
仍以原版e8f3be08623663d4ad7f7241e693c94469b63bb0为基点；
实际嵌套工作树HEAD为历史基线7c2365cb376b48acb1591e48a6ef91e5c47c78e6，
与P00核验一致。临时索引应用检查通过，真实暂存区未变；未提交。
包含原生桥接、天气卡/测试及Lighthouse异常凭据脱敏修复；
证据`evidence/p05/chat-upstream-patch-delivery.json`。不是纯P05补丁，
不包含运行配置、认证状态、数据库、编译产物或测试Cookie。

尾审补正“提醒我查天气”的业务优先级后，最终采用
`patches/librechat-v0.8.8-rebuild-p00-p05-weather-chat-r2-20261104.patch`，
63文件、224547字节；SHA-256
`52ef08fcbd0a2926ca884f37ab25f43e93b941a593af3691a93c3bfdd38d03d7`。
同样通过临时索引应用检查且真实暂存区未变；
证据`evidence/p05/chat-upstream-patch-delivery-r2.json`。前版保留为历史快照。
