# Upstream Diff

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
