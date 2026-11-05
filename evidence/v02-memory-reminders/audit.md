# 本轮只读基线审计

实际开始：2026-11-02T20:52:33.528367+08:00。原始记录为 `baseline.json`。

- 根仓库 `main` / `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`；
  LibreChat `lifecompanion-baseline` / `7c2365cb376b48acb1591e48a6ef91e5c47c78e6`。
  两者开始即有大量修改、未跟踪源码、日志和截图，均未重置或清理。
- Memos 位于独立仓库，HEAD `651657e7211901393e2501ae7e3e202c8e56f73a`，开始干净。
- 基线健康检查：3001 网关、3080 LibreChat、5230 Memos、8010 life-core 均返回 200。
- 原 life-core 行数：users 1、events 6、ingest_attempts 8、reminders 0、task_runs 6。
  只是开始时快照；本轮没有清空这些表或原 Mongo/Memos 卷。
- 基线容器挂载和全部端口见 `baseline.json`；Silver-economy 其他容器仅观察，未操作。
- Git 原差异、未跟踪文件哈希、SQLite 在线备份保存到被忽略的
  `infra/runtime/v02-memory-reminders/`。不将用户数据库或真实凭据归档到公开 evidence。
- 基线复跑退出 0：16 后端 + 115 前端 + 1 网关 = 132。命令与时间分别见
  `baseline-backend.*`、`baseline-frontend.*`、`baseline-gateway.*`。

## 根因与实施顺序

1. 原事件筛选主要是规则式；只按同来源幂等，没有长期事实召回与跨消息聚合。
   先写失败测试 `memory-before.*`，再实现统一 life-core 管线，保留原发布/重试链路。
2. 原 UI 主题的 presentation/chat/dialog 未完整映射，中央读区出现纯白；
   思考区域会读取历史展开偏好，原生菜单/单模型选择增加不必要步骤。
   修前五视口 `before-chat-*.jpg`，修改通过既有语义 Token 和能力配置完成。
3. 新提醒必须成熟上游。原版完整 clone、运行和真实 API 到期通过后，
   才接 life-core v2，再开发 React `/reminders`。
4. 保留完整失败证据；最终局部成功不等于总体完成。阶段日志和当前限制见索引。

新增 Vikunja/ntfy 使用独立端口和 runtime 卷。对已有 SQLite 仅追加表/兼容列，
未升级 LibreChat/Memos、未覆盖旧补丁、未提交、未 push、未公网发布。
