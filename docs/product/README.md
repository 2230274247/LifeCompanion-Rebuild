# 产品文档索引

- [V0.3 A++ 纪念价值、图像资格与隐私授权解耦](../development-log/2026-11-04_14-20_V03Aplusplus纪念价值图像资格与授权解耦_开发验收.md)：工程合同 PASS；真实模型语义评估 NOT PASS（本轮未验收）、真人参考 NOT REVIEWED、阶段 B NO，总体 PARTIAL。
- [V0.3 A+真实语义选择评估](../development-log/2026-11-04_13-27_V03Aplus真实语义选择评估_开发验收.md)：PARTIAL；36冻结合成场景、真实DeepSeek基线/复测及独立两轴；[评估口径](V03_Aplus_语义评估口径.md)、[逐场景报告](../../evidence/v03-stage-a-plus/中文评估报告.md)、[交互审查](../../evidence/v03-stage-a-plus/review.html)。参考待真人复核，暂不进入B。
- [V0.3 阶段 A 窗口聚合与幂等结算](../development-log/2026-11-04_12-31_V03阶段A窗口聚合与幂等结算_开发验收.md)：功能/合同 PASS，真实语义多场景准确率 NOT TESTED，总体 PARTIAL；未经确认不进入阶段 B。
- [当前开发进度与遗留问题审计报告（2026-11-04）](LifeCompanion-Rebuild_当前开发进度与遗留问题审计报告_2026-11-04.md)：PAUSED_FOR_USER_REVIEW；仅完成P05天气收尾，未经用户明确授权不恢复。
- [版本入口说明](../../README.md)
- [逐次开发验收记录](../development-log/README.md)
- [V0.1 演示准备验收](../ACCEPTANCE_2026-11-04.md)（2026-11-02 为 11 月 4 日演示准备）
- [尚未完成的功能与上线阻塞](../BLOCKERS.md)
- [Android 后续边界](../ANDROID_PLAN.md)
- [P00-P07 当前验收矩阵](p00-p07/11_跨阶段总验收矩阵.md)
- [P03 真实提醒阶段记录](p00-p07/P03/P03_STAGE_LOG.md)
- [P04回忆安全与真实文字管线阶段记录](p00-p07/P04/P04_STAGE_LOG.md)
- [P04真实八维评分与费用边界](p00-p07/P04/EVENT_SCORING_EVAL.md)
- [P05只读工具与当前阶段边界](p00-p07/P05/P05_STAGE_LOG.md)
- [P05天气聊天卡与真实浏览器证据](p00-p07/P05/P05_E2E.md)（整体PARTIAL；新增模型调用0）

V0.2 范围：统一登录入口、复用真实聊天、回忆列表与详情、聊天到回忆链路、
权限边界、响应式及可追溯工程日志。功能状态以对应开发日志的实际测试为准。
V0.2.1 增量见 [实际范围与限制](../architecture/V02_1_MEMORY_REMINDERS.md)、
[本轮证据](../../evidence/v02-memory-reminders/README.md)。
当前仍为明确映射的本地内测。两个合成账号已验证提醒与通知隔离；
有限事实的跨会话召回、单次提醒及真实站内消息可用。多用户自助开户、
固定周期提醒、关页/手机推送、生图和 APK 均未交付。总体 PARTIAL。
