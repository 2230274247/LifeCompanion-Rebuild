# 架构文档索引

- [记忆与语义请求编排实施状态](../development/MEMORY_IMPLEMENTATION_STATE.md) — 分阶段方案、验收标准、检查点和会话续接入口；以阶段实际状态为准。

- [类人记忆与语义请求编排调研（2026-11-09）](MEMORY_AGENT_RESEARCH_2026-11-09.md) — 成熟产品公开能力、开源方案、现有缺口与证据回答建议；仅调研，未实施。

- [纯语义记忆召回与历史压力验收](MEMORY_SEMANTIC_RECALL.md) — 全量持久向量、时间元数据约束、JWT公开召回接口与真实验收边界；禁止关键词兜底。

- [语义任务规划与事件时间概览（P2，2026-11-09）](../development-log/2026-11-09_17-33_记忆编排P2语义协议与概览_开发验收.md) — 模型输出严格结构化任务（answer/search_memory/overview/query_reminders/prepare_reminder/web_search/clarify），后端校验与受控执行；事件概览按发生时间窗口分页，绕过相似度阈值；内部 `/assistant/plan` 与 `/assistant/execute` 接入证据。

- [LibreChat 服务端接入语义规划器（P3，2026-11-09）](../development-log/2026-11-09_17-57_记忆编排P3服务端接入规划器_开发验收.md) — `withLifeMemory` 先走 `/assistant/plan` 与 `/assistant/execute`，收集 `search_memory`/`overview` 证据注入本次模型调用；规划器未配置回退 `/knowledge/recall`；权限与畸形响应不冒称“无记录”。

- [应用内宠物（Otis）](PET_IN_APP.md)
  — 交付形态：只在聊天路由渲染的 200×256 可拉伸脸，随页面打开；
  复用原 WebGL 引擎，alpha 掩码做指针穿透，不接入数据链路。

- [桌面宠物置顶窗（Electron + Otis，可选实验）](PET_WINDOW.md)
  — 上一轮的独立桌面表面：透明置顶、托盘/右键菜单、位置持久化；
  已被应用内形态取代，保留作为本机实验入口，不随产品交付。
  上一版 murmur 实现已被 Otis 取代，但其文件仍在磁盘上，删除请求被权限策略拦截。

- [V0.3 B0 Kolors Provider 最小接入设计](V03_B0_KOLORS_PROVIDER.md)
  — DESIGN ONLY；独立验证实现已存在，但未连接 FastAPI/Moments/Worker。

- [V0.3 双工作树实际架构与复用审计](../product/v0.3/仓库审计报告.md)
- [V0.3 分阶段最小变更与迁移计划](../product/v0.3/实施计划.md)
- [V0.4 Android 原生客户端架构](V04_ANDROID.md)
  — 规划（DESIGN ONLY）：原生 Kotlin + Compose，复用现有网关 API；认证 / SSE 边界先经 P0 探针验证。

2026-11-04 审计确认：当前 P03/P04 开发树已具备 APScheduler 持久 JobStore
和八维事件评分，位于 `.work/p00-p07-20261103`；以下正文保留早期架构说明，
V0.3 不能据此另造评分、聊天或调度系统。此次未变更业务架构。

- [当前架构与 API](../ARCHITECTURE.md)
- [V0.2 代码审计与实施方案](../V02_IMPLEMENTATION.md)
- [历史技术决策](../DECISIONS.md)
- [上游版本清单](../UPSTREAM_MANIFEST.md)
- [上游改动与补丁](../UPSTREAM_DIFF.md)
- [运行与恢复](../RUNBOOK.md)
- [V0.2.1 记忆与成熟提醒服务实际边界](V02_1_MEMORY_REMINDERS.md)

当前选择：LibreChat React 前端承载统一产品 Shell；Memos 通过官方 API 提供私有存储；
life-core 处理用户映射、事件、来源关联、授权与幂等。三个数据库保留原有边界。
3001 为正式本机入口，统一代理聊天与 `/life-api`，不嵌套 Vue 或 iframe。
V0.2.1 在 life-core 增加有界事实召回与同主题事件归并，并通过独立 Vikunja/ntfy
官方接口接入单次提醒。合并数据库、更换聊天内核和无条件重复日程不在当前交付内。
