# 架构文档索引

- [当前架构与 API](../ARCHITECTURE.md)
- [V0.2 代码审计与实施方案](../V02_IMPLEMENTATION.md)
- [历史技术决策](../DECISIONS.md)
- [上游版本清单](../UPSTREAM_MANIFEST.md)
- [上游改动与补丁](../UPSTREAM_DIFF.md)
- [运行与恢复](../RUNBOOK.md)
- [V0.2.1 记忆与成熟提醒服务实际边界](V02_1_MEMORY_REMINDERS.md)
- [P03 独立调度与真实恢复](../product/p00-p07/P03/SCHEDULER_RELIABILITY.md)
- [P03 LangGraph 持久业务编排与实际边界](../product/p00-p07/P03/LANGGRAPH_STATE_MACHINE.md)
- [P04回忆作业、撤权与未知结果保护](../product/p00-p07/P04/RECOLLECTION_JOB_STATES.md)
- [P04八维模型评分、来源质量门与持久请求预算](../product/p00-p07/P04/EVENT_SCORING_EVAL.md)
- [P05受控只读工具、出网字段与持久配额](../product/p00-p07/P05/TOOL_REGISTRY_AND_SAFETY.md)
- [V0.3 A++纪念价值、图像资格与外发授权分离](V03_Aplusplus_RECOLLECTION_SEPARATION.md)：合同实现PASS；真实模型/真人参考/生图未验收，不进入B。
- 天气交互复用原消息持久化桥接和工具账本；同名地点选择、revision及取消清除边界见上述P05文档。

当前选择：LibreChat React 前端承载统一产品 Shell；Memos 通过官方 API 提供私有存储；
life-core 处理用户映射、事件、来源关联、授权与幂等。三个数据库保留原有边界。
3001 为正式本机入口，统一代理聊天与 `/life-api`，不嵌套 Vue 或 iframe。
V0.2.1 在 life-core 增加有界事实召回与同主题事件归并，并通过独立 Vikunja/ntfy
官方接口接入单次提醒。合并数据库、更换聊天内核和无条件重复日程不在当前交付内。
