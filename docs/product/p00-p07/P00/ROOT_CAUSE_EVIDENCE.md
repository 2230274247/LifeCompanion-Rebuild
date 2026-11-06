# P00 架构与故障证据

## 已由源码及实际请求互证

1. 浏览器 `:3031` → `apps/product-portal/server.mjs:createGateway`：
   `/api/*` 转发独立 LibreChat `:3091`，`/life-api/*` 白名单转发 core `:8031`。
   浏览器内部令牌头会删除，internal 路由不可经网关公开访问。
2. 聊天 → LibreChat `api/app/clients/BaseClient.js` 与
   `packages/api/src/memory/life.ts`：用户消息入 Mongo 后连接 life-core；
   四会话通过官方聊天/stream/messages API 读回，原件没有写到旧库。
3. `services/life-core/app/auth.py:identity_from_request` 验证 LibreChat JWT，
   `main.py:current_identity` → `store.py:users` 绑定 life_user_id/Memos 用户。
   八个合成账号有八个不同 LibreChat/Memos ID。
4. `memory.py:enqueue/run_one/classify/recall` →
   memory_jobs / memory_items / memory_evidence；来源归属当前用户。
   当前 classify 有规则及 httpx LLM 路径，recall 有字词/双字匹配；
   此事实不等于 LangMem 或图谱已集成。
5. `memos.py:MemosClient.create_private_memo` 使用用户 PAT 和官方 API，
   写前核对 writer/PRIVATE 归属；Memos 不是完整长期记忆实现。
6. `reminder_drafts.py:create/patch/select` → reminder_drafts/submissions；
   `reminders.py:ReminderService` → Vikunja v2；`provisioning.py` → 每用户账号，
   ntfy 使用独立通道。P00 仅证明草稿和隔离拒绝，正式投递仍待 P03。
7. `moments.py:Moments.schedule/select/run_one` → moments 表/图像 BLOB；
   `main.py:moment_work` 为 API 内线程，不是独立 APScheduler。
   当前评分有关键词/规则，未证明结构化模型评分。图像未实测、未伪造。
8. React 路由位于 `products/librechat-custom/client/src/routes/index.tsx`；
   `components/Life/ChatSources.tsx` 与 ReminderCards 使用业务 ID 和来源入口。
   深链接真实返回可访问页面，点击往返和实体详情在 P01 继续实测。

## 本轮故障与恢复

- 首次 pytest 从外层运行缺 PYTHONPATH，出现 11 个收集错误；
  设置本工作树 services/life-core 后 63 passed，没有修改断言。
- 第六个合成账号注册触发上游默认 5 次限流，HTTP 429；
  仅隔离 Compose 设置 REGISTER_MAX=20，随后八账号全部真实创建。
- 第一次 Playwright 缺指定 Chromium 缓存；改用机器已安装 Chrome，
  无下载/安装新浏览器，随后真实浏览器脚本通过。
- 草稿越权测试首次缺 If-Match，返回 422，不能计作权限通过；
  补全合法请求后返回 404，保留首次和复测结果。
- 原项目数据库授权行的历史差异本轮不回滚，不把历史解释当已查明根因。
