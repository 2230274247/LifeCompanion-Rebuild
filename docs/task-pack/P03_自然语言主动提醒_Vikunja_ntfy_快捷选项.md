# P03｜真正能创建、修改、取消与投递的对话式提醒

## 产品目标

用户不应该像使用企业工单系统一样填写“标题、时间、时区、内容、标签、优先级”。系统要**从日常语言中提取已经知道的信息，只补缺失信息**；但每个真实提醒必须在权威业务系统被创建，并且时钟到了能由实际渠道投递。

## 强制保留/复用的成熟上游

- 已发现并可用时优先使用 **Vikunja** 作为正式任务/提醒服务，透过版本锁定的 API 适配器，不直接改 Vikunja 镜像或造第二个任务平台。
- 优先使用已存在的 **ntfy** 或 Rebuild 现有渠道执行站内/Web Push/设备端通知；通知 provider 返回接受不等于设备确实已收到。
- **LangGraph** 执行持久化的提议、缺信息、授权、创建、改期、取消的确认工作流；**APScheduler** 独立 scheduler 负责时间到期、恢复、重试和幂等执行；事件与计划时间不同。
- Vikunja 2.7.x 若真实版本核实成立，优先依据其实际 OpenAPI v2 文档编写客户端，不凭旧 v1 端点猜 API。上游：<https://vikunja.io/docs/api-v2/>。

## 03-01. 先把“语言”变成可验证的事项草稿

解析字段：`intent`、`target_user`、`title`、`negated_constraints`、`source_message_ids`、`event_at`、`remind_at`、`lead_minutes`、`timezone (IANA)`、`time_precision`、`location`、`confidence`、`missing_fields`、`reminder_id?`、`proposal_id`、`state`。当前日期由后端**可验证时间+用户 IANA 时区**解析，不能凭模型猜“今天”。

意图：`NO_ACTION/FUTURE_EVENT/EXPLICIT_REMINDER/TASK_INTENT/EDIT/CANCEL/QUOTED_THIRD_PARTY/UNCERTAIN`。支持过去时、否定、引用他人、周五、跨月跨年、凌晨、日期不明确、多个待办同时出现、事件与提醒时刻不同。

## 03-02. 交互决策（消解任务书冲突）

- **明确授权的命令**： “明天早上提醒我带绿色 U 盘，不是银色的。”只有小时缺失，只显示“明天几点提醒？”与 `8:00/9:00/10:00/其他时间` 等 2～4 Chip；点击后就创建，若会话权限/既有设置要求再次确认则将选择本身视为明确确认动作，不可强迫重复填表。若有材料变动则在卡片中清晰展示最终值。
- **时间完整的明确命令**：“明天下午 3 点开会，早上 9 点提醒我”可直接创建，不再出现大表单；必要时显示简洁可撤销的成功卡。
- **仅提潜在计划**：“明天下午 3 点去医院”只能询问是否要设提醒；用户明确选择后才可创建。不要从这句话推断“15:00就是提醒时间”。
- **日期缺失**：“到杭州后 17:00 在学校开会，提前 2 小时提醒”只问哪一天，给日期 Chip/日期选择器；日期确定后自动算出 15:00，展示已确认值。
- **否定/第三人**：“朋友明天有会”“不用提醒我”不自动创建。
- **改期/取消**：“把刚才那个改到周五”“取消刚才的提醒”必须通过现有 reminder_id+授权定位目标，显示必要变更，持久化状态、取消调度与前端同步；若存在两个同名提醒先问哪一个。
- **已拒绝的建议**：同一事项短期内不连续反复提示；支持“稍后/不再提示”，有个性化频率设置。

## 03-03. 状态系统与持久化

`DETECTED→PROPOSED→COLLECT_MISSING→READY→CONFIRMED→COMMITTING→ACTIVE→DUE→ATTEMPTED→ACCEPTED/DELIVERED_CONFIRMED/UNKNOWN/FAILED`；取消 `CANCELLED`，修改通过原 ID 版本迭代。服务端是权威状态，不把 LangGraph checkpoint 当业务主库，不把候选卡当正式提醒。

- 使用持久 checkpoint、稳定 thread_id、interrupt/resume 或版本等价功能；刷新、后端重启能恢复。
- 生成和持久化幂等键：同用户/事件/动作/版本；双击和网络重试不能重复建正式任务或重复投递。
- APScheduler 应单独部署，锁定实际 API 主版本（3.x/4.x 不可混配）。以权威任务状态与可恢复 job store 保证任务重启不丢、不重复；所有调度决定写审计记录。
- ntfy 接受、Web Push 服务器已推送、浏览器/Android 真正收到是不同状态；Android 后台通知若无真机证据就是 `UNKNOWN`。
- 存在兼容性/网络故障时保留草稿并展示“保存失败，可重试”，不能 AI 说“已经安排好了”。

## 03-04. 页面与安全

- 复用 P01 统一聊天卡、提醒列表、提醒详情；每张卡指向真实 `reminder_id`，含“查看提醒”“取消”“查看原话”；取消后重登仍显示取消。
- 快捷 Chip 支持键盘、触摸、焦点与小屏。只显示必要选项，不重复设置时区或全部字段。
- 按 Rebuild 用户授权来选择实际通知通道；初次开启明确说明权限。不要通过普通用户共用的 Vikunja 全权账号直接暴露其他人的任务。

## 测试矩阵与硬门槛

| ID | 真实场景 | PASS 条件 |
|---|---|---|
| REM-01 | 明天早上绿色 U 盘（非银色） | 只补时间，点击选项后真正建任务，限定词完整 |
| REM-02 | 15:00 开会/09:00 提醒 | 不重复表单，两时刻存储与显示正确 |
| REM-03 | 到杭州后 17:00，提前120分钟 | 只缺日期，选定后15:00通知 |
| REM-04 | 明天出门带雨伞 | 没出门时刻时不假定9点，可选定 |
| REM-05 | 取消刚才提醒 | Vikunja/权威库、scheduler、卡片、跨会话四处一致 |
| REM-06 | 双击/网络重试/重启 | 0重复正式提醒，0无意重复投递 |
| REM-07 | 今天/明天/跨年/其他时区 | 使用后端时钟和 IANA 时区、无猜测日期 |
| REM-08 | 只是提计划、拒绝、第三人转述 | 0未经授权任务创建 |
| REM-09 | 两个同名提醒/模糊改期 | 仅补必要歧义，不误操作别人的任务 |
| REM-10 | 实际定时触发 | 有真实投递适配器和状态证据；终端送达单独验收 |
| REM-11 | 换账号尝试访问提醒 ID | 403/404，不泄漏数据 |
| REM-12 | ≥200 人工标注意图案例 | 宏 F1 目标≥0.85；真实错误样例和评测成本可追溯 |

## 交付

`REMINDER_INTENT_SCHEMA.md`、`VIKUNJA_API_ADAPTER.md`、`LANGGRAPH_STATE_MACHINE.md`、`SCHEDULER_RELIABILITY.md`、`NTFY_DELIVERY_EVIDENCE.md`、`REMINDER_E2E.md`、`P03_STAGE_LOG.md`。

## 给 Codex 的提示词

> 只在通过 P00 身份门禁的 Rebuild 中实施 P03。先确认已有 Vikunja/ntfy 实例及 API，在 Rebuild 原生 Chat Shell 内完成无需全表单的对话式提醒；已明确命令优先靠快捷选项一次补齐，潜在计划仅建议不擅自创建。LangGraph checkpoint+APScheduler 独立持久调度+正式 Vikunja 记录+真实 ntfy/站内通知，统一状态与权限。一次完成保存、取消、改期、重启恢复、跨会话查看的端到端测试，不能以旧项目 200 条/571 个 PASS 顶替。

---

## 全阶段共同执行规则（本阶段必须实际遵守）

- 开始前真实执行 P00 的项目身份校验；记录 `canonical_root / git common-dir / branch / HEAD / worktree / active Compose project / test DB`。只有已核实的 Rebuild 隔离开发工作区可写。旧 `Silver-economy`、`Silver-economy-research`、`.work/intelligence-20261103` 全部只读。
- 先读 Rebuild 现有 README、AGENTS.md、设计规范、测试、迁移和用户授权；未知路径不可凭旧方案猜测；以 Rebuild 实际代码做增量变更。
- 能复用上游成熟开源组件时优先通过受控版本的 API/适配器集成；不直接改上游镜像源码、不重复创建同功能主系统；clone 只是获得代码，不等于集成完成。第三方必须记录许可证、版本、NOTICE、可能的传染性义务及安全公告。
- 禁止擅自使用生产用户数据做测试、批量重写数据库、覆盖原素材、泄露密钥、修改授权、未授权付费、打开公网、推送 Git、合并主分支。测试采用独立环境、合成用户、经过校验的备份和可回滚迁移。
- 真实云端模型只用 Rebuild 已验证可用的供应商和后端 Key；不下载 Qwen/Laya/Embedding 本地权重，不默认新增百炼 Key。明确预算与调用限额；API 未配置或余额不足时用 `BLOCKED_API_CONFIG` 报告真实云调用未验收。
- 每个任务保持 `证据→假设→修复→单测→真实集成→Playwright/浏览器→回归→记录`。不得仅依据页面文案、Mock、内存变量、接口 200、旧项目测试数字写 PASS。
- 每阶段**新增独立 Markdown 开发日志**，提供命令、退出码、前后 Git Diff、真实请求/响应（脱敏）、DB 验证查询、截图/录屏、成本和依赖版本。只用 `PASS/PARTIAL/FAIL/BLOCKED/UNKNOWN/UNVERIFIED`。
