# V0.2 审计与实施方案

审计日期：2026-11-02。根仓库 main、LibreChat lifecompanion-baseline、Memos lifecompanion-baseline；
开发前均无未提交修改。已阅读 README、ARCHITECTURE、RUNBOOK、BLOCKERS、
ACCEPTANCE_2026-11-04、UPSTREAM_DIFF、DECISIONS、Compose 与 LibreChat AGENTS。
日期为 11 月 4 日的验收文件是未来演示准备材料，不能视为本轮验收。

## 代码审计结论

- product-portal 是 Node 静态导航页，没有 React、会话或路由能力；保留其端口并改成同源反向代理。
- LibreChat client/src/routes/index.tsx 使用 React Router；Root 已提供认证、统一侧栏、
  移动抽屉及聊天数据 Provider，适合直接作为产品 Shell。
- ChatRoute -> ChatView -> ChatForm / MessagesView，复用原会话创建、历史、复制、重新生成、
  Adaptive SSE 流式响应、草稿与滚动机制；不开发新聊天引擎。
- BaseClient.saveMessageToDatabase 在 db.saveMessage 成功后通知内部 ingest；
  内部请求有超时、错误隔离；接入仍是服务端行为。
- life-core 已有 JWT、显式用户映射、事件过滤、授权、发布任务及来源幂等。
  原 memories 仅返回 published 事件索引，不读取真实 Memo；没有分页、详情。
- 原认证允许 refreshToken Cookie，缺少 LibreChat 服务端会话撤销验证。
  本轮移除 Cookie 回退，统一使用上游自动刷新的访问令牌；剩余短时 JWT 撤销窗口必须明确记录。
- Memos 26.10.0 官方 proto/api/memo_service.proto 支持 GET/POST/PATCH/DELETE /api/memos；
  本轮仅新增读取，不修改其源码、数据库或版本。
- 当前显式单用户映射与一个服务端 PAT，不具备多用户自助开户；每条读取必须核对事件归属和 Memo creator。
- 3001 / 3080 / 5230 / 8010 均绑定本机；容器通过 host.docker.internal:8010 接入。
  现有 Compose 原样固定上游镜像。新前端构建挂载到现有 LibreChat，不迁移数据库。
- 品牌 Token 来自 apps/product-portal/portal.css：纸张 #f1ecdc / #faf6ea、墨绿 #315a48、
  银杏黄 #dfa61b、正文 #1d2b25；在现有语义主题注册表中表达。

## 执行与自检

1. 扩展真实回忆 API：用户归属、Memos 读取、分页/日期/排序/搜索/详情；以隔离、失败和真实内容测试验收。
2. 扩展原 React Shell 与路由，保留 /c/:conversationId；新增 /memories 及 /memories/:memoryId。
   聊天入口恢复上次会话，复用上游草稿；回忆筛选放 URL，滚动状态按用户保留。
3. 3001 同源代理：/life-api -> life-core；其他请求（包括 SSE）-> LibreChat；禁止代理内部 API，
   不向 life-core 传 Cookie，不注入服务端令牌。
4. 构建、类型检查、针对性测试、运行五种视口，真实聊天到 Memos 链路、退出/越权及深链接刷新。
5. 存档可复现上游补丁、更新运行文档、保存独立中文开发验收日志与真实截图。

## 事件归并边界

现有来源 ID 只能阻止同来源消息重复；不同消息的语义归并尚不存在。新增 memory_group_id
需要迁移、分组判定与来源关系契约，本轮不执行数据库迁移，也不把多个相似消息静默合并。
保留原始会话和来源关系，后续单独设计兼容方案与可撤销归并操作。
