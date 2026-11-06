# P00 选择性移植矩阵

旧 intelligence source_commit 均为 `093627936776da2a78fce09ef7b174a0793f82f0`
加本地未提交修改。没有继承旧测试成绩，没有复制旧业务源码。

| source_repo/src | license | risk / Rebuild overlap | decision | target / required_test / final_result |
|---|---|---|---|---|
| Silver-economy/.work/intelligence-20261103/services/api/app/intelligence/contracts.py | 原业务源码许可待核实 | 旧 ORM 字段、实体模型不同；Rebuild 有 Candidate | DEFER 原码，参考 schema 约束 | P02；否定/实体消歧/来源；未移植 |
| 同目录 graphiti_native.py | 原业务源码许可待核实；Graphiti 独立许可 | 导入旧 get_settings/ProviderFailure，不能原样复用 | REIMPLEMENT_WITH_FRAMEWORK | P02 正式适配器；无 embedder 不出网；未实现 |
| 同目录 scheduler.py / reminders.py | 原业务源码许可待核实 | 旧业务主库、通知/任务重复 | REJECT 整体移植 | P03 在 Rebuild 原任务 API 上扩展；未复制 |
| 同目录 recollections.py | 原业务源码许可待核实 | 旧回忆域与当前 Moments 重叠 | DEFER，参考评分测试设计 | P04；真事件候选/隐私/幂等；未复制 |
| services/api/tests/test_intelligence_memory.py | 原业务源码许可待核实 | 引用旧数据库夹具 | ADAPT 测试思路，不复制源码 | P02 新写跨会话/公司/修订用例；未实施 |
| services/api/tests/test_intelligence_workflow.py | 原业务源码许可待核实 | 旧 LangGraph 状态与确认策略不同 | ADAPT 测试思路 | P03 重启/恢复/拒绝/重复确认；未实施 |
| 旧 ORM、Vue 整页、Compose、env、数据库、账号/素材 | 不适用 | 跨项目身份和数据风险 | REJECT | 不进入 Rebuild |
| research/repositories 中 LangMem/LangGraph/Graphiti/APScheduler | 逐仓库上游许可 | 有重复克隆；不是 Rebuild 当前安装证据 | DEFER 直接复制 | 从批准版本官方 API/包集成；P02-P03 单独锁版本 |

当前阶段最终移植业务源码文件数：0。安全守卫、隔离环境及验收脚本为本轮 Rebuild 新增。
