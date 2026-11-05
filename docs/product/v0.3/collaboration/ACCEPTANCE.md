# V0.3 多人协作与共享记忆验收报告

验收日期：2026-11-05（Asia/Hong_Kong）。唯一基线：
`H:\AI For research institute\LifeCompanion-Rebuild`。以下结论全部来自真实运行
的 LibreChat、life-core、Memos、MongoDB 与真实模型 API，没有用页面假数据、
单账户多窗口或前端 mock 冒充通过。

## 一句话结论

- 核心业务闭环（好友 → 空间 → 群聊 → 共享回忆 → Parlor → @AI 受控查询 →
  关怀转达 → 站内通知 → 撤销即时生效）为 **PASS**。
- 新增服务端安全回归（越权媒体、跨群隔离、事件订阅鉴权、撤销后 Agent 上下文）
  为 **PASS**。
- 历史业务的聊天、回忆生图、提醒、Memos 全量回归尚未在本轮重跑，故
  P00–P08 阶段整体标记为 **PARTIAL**，待回归完成后升级。

## 阶段结论

| 阶段 | 结论 | 依据 |
| --- | --- | --- |
| P00 现状与许可证审计 | PASS | 根分支 `feat/v03-collaboration-20261105`；上游 LibreChat v0.8.8 MIT、Memos 26.10.0 MIT；工作树与 remote 已实查 |
| P01 多账户好友 | PASS | 独立账户 D/E/F；好友申请/接受/越权拒绝均有断言 |
| P02 Space 与多人聊天 | PASS | family/friends/team 统一模型；消息持久化、实时读取、退出后阻断 |
| P03 授权与撤销 | PASS | grant 即时撤销后 HTTP 404；Agent 查询同受控 |
| P04 指定回忆共享 | PASS | 只分享指定回忆，原私有事件不被改写，成员补充独立保存 |
| P05 Team Agent 与 @AI | PASS | 真实模型调用；工具上下文服务端过滤；无授权回答 DENIED |
| P06 亲友关怀与通知 | PASS | 转达需显式授权，通知持久化、去重、payload 最小化 |
| P07 Parlor 与亲友圈 UI | PASS（视觉冒烟）/ PARTIAL（全视口像素对比） | 桌面悬浮窗、移动端抽屉可用；完整 768/1440/1920 像素级对比待录屏 |
| P08 跨用户 E2E 与安全 | PASS（新增安全回归）/ PARTIAL（历史业务全量回归） | 浏览器 21/21、API 26/26、life-core 77 passed；历史回归见下 |

## 测试证据（本轮实测）

| 测试 | 结果 | 时间 | 位置 |
| --- | --- | --- | --- |
| 三账户浏览器全链路 UI | 21/21 passed | 2026-11-05 | `evidence/v03-acceptance/browser-fullflow/summary.json` |
| 协作 API 全链路 | 26/26 passed | 2026-11-05 | `evidence/v03-acceptance/collaboration.json` |
| Parlor 视觉/越权冒烟 | 4/4 passed | 2026-11-05 | `evidence/v03-acceptance/browser/summary.json` |
| life-core 全量 pytest | 77 passed, 1 warning | 2026-11-05 | 本地执行日志 |
| 前端 Life 相关 jest | 28 passed（6 套件） | 2026-11-05 | 本地执行日志 |

浏览器全链路使用三个独立 `browser.newContext()` 隔离上下文，分别代表
发起人 D、亲友 E 和越权路人 F；所有步骤均通过真实 UI 点击与服务端断言。
新增回归覆盖：跨群消息/事件隔离、非成员读取 moment 图片被阻断、
`/api/v1/collaboration/events` 订阅鉴权、撤销后 Agent 上下文为空。

## 尚未完成（如实标记）

- 历史聊天、记忆检索、回忆生图、提醒、Memos 的既有业务回归测试需要重跑，
  未跑完前不将 P00–P08 整体升级为 PASS。
- ntfy/手机后台系统推送的“真实送达”分级未验证，当前 PASS 的是可靠站内通知。
- 768/1440/1920 全视口像素级对比和录屏尚未补齐，移动端 390/430 已冒烟。
- 自动共同经历候选匹配、高频并发与性能压测未在单晚范围内验收。

## 版本与提交

- 根仓库分支：`feat/v03-collaboration-20261105`
- 根仓库 HEAD：`bd266bc3f414db09d740aef3fd6820d45b2b26a4`
- LibreChat 本地分支：`lifecompanion-baseline`
- LibreChat HEAD：`e48d5f745979a978ad01092a28ffaab76de07e11`
- 推送状态：`LOCAL_COMMITTED / PUSH_BLOCKED_NO_REMOTE`（根仓库无 remote）
