# 架构文档索引

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
