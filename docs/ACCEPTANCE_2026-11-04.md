# Acceptance 2026-11-04

验收日期：2026-11-02（为 2026-11-04 现场演示准备）

## 结果总览

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| 两个上游仓库真实克隆、固定版本、保留 LICENSE/Git 历史 | PASS | `docs/UPSTREAM_MANIFEST.md` |
| LibreChat 原版可运行、登录、聊天、历史回看 | PASS | `evidence/baseline-librechat.png` |
| Memos 原版可运行、时间轴、私有记录 | PASS | `evidence/baseline-memos.png` |
| 统一产品入口可进入两套真实页面 | PASS | `evidence/portal-1440x900.png`、`portal-1920x1080.png`、`portal-390x844.png` |
| DeepSeek 真实中文聊天 | PASS | `evidence/vertical-slice-librechat.png`、`evidence/deepseek-model-check.txt` |
| 刷新后对话历史仍在 | PASS | 浏览器刷新后同一会话与两条消息仍显示 |
| 新聊天自动进入 `life-core` 事件 | PASS | 当前代码自动复测 `evt_64881871ce06443c4eab0e55`；任务书原句 `evt_432007786bef74a099f08b6d` |
| 事件以 PRIVATE 形式写入 Memos | PASS | `evidence/vertical-slice-memos.png`、`memos/50405b33-8532-5334-b0a3-3c92c4955082` |
| 相同来源重试不重复写入 | PASS | `evidence/vertical-slice-verification.json` |
| 原版与二次开发差异可追溯 | PASS | `docs/UPSTREAM_DIFF.md`、LibreChat 本地提交 `7c2365cb3` |
| 1440×900 / 1920×1080 / 390×844 入口检查 | PASS | `evidence/portal-*.png` |
| 自动化 API/过滤/幂等/隔离测试 | PASS | `7 passed`，见 `tests/RESULTS.md` |
| 真实图片生成供应商链路 | BLOCKED | 无图片供应商凭据；见 `docs/BLOCKERS.md` |
| 提醒后端最小模型 | PARTIAL | 创建/列表接口已实现，未完成独立提醒 UI/推送 |
| 长期记忆跨天召回 | NOT STARTED | 不属于已完成 P0 |
| Android APK | NOT STARTED | 仅有 `docs/ANDROID_PLAN.md`，不宣称已交付 |

## 关键纵向切片

用户消息：

```text
今天下午去公园散步，看见秋天的银杏树，感觉特别放松。
```

真实的跨模块引用：

| 字段 | 值 |
| --- | --- |
| LibreChat UI message id | `f22bce04-5d1a-4158-ad77-58be8b9c8c07` |
| LibreChat Mongo message `_id` | `6ae856469bf7d8d5b8091536` |
| Conversation id | `05cb4a43-fd2b-5209-ae4f-a06608e6c6e5` |
| Event id | `evt_432007786bef74a099f08b6d` |
| Idempotency key | `chat:6ae856469bf7d8d5b8091536` |
| Memos ref | `memos/21b178b7-5dc4-58ca-83b8-e83901bce463` |
| Memos visibility | `PRIVATE` |
| Memos creator | `users/life-admin` |
| Event status | `published` |
| Publish task status | `succeeded` |

当前代码的第二次自动复测：

| 字段 | 值 |
| --- | --- |
| UI message id | `f16a8d90-2746-4543-ab20-f28ebc0d10c5` |
| Event id | `evt_64881871ce06443c4eab0e55` |
| Source message id | `6ae857869bf7d8d5b8091538` |
| Memos ref | `memos/50405b33-8532-5334-b0a3-3c92c4955082` |
| Log | `[LifeCompanion] event ingest completed` |
| Retry | 同事件、同 Memo |

## 已实际执行的检查

```text
GET https://api.deepseek.com/v1/models    -> 200
DeepSeek model ids                         -> deepseek-flash, deepseek-v4-pro
LibreChat real message + model response    -> PASS
LibreChat reload + history                 -> PASS
LifeCompanion event ingest completed       -> PASS
Memos API visibility                       -> PRIVATE
Repeated same-source ingest                -> same event + same memo ref
Current-build automatic ingest probe        -> PASS (evt_64881871ce06443c4eab0e55)
life-core pytest                          -> 7 passed
node --check BaseClient.js                -> PASS
node --check portal server/client         -> PASS
Docker Compose config validation          -> PASS with infra/.env
```

## 截图口径

- 原版基线：`evidence/baseline-*.png`
- 改造版聊天与时间轴：`evidence/vertical-slice-librechat.png`、
  `evidence/vertical-slice-memos.png`
- 自有入口三种视口：`evidence/portal-1440x900.png`、
  `evidence/portal-1920x1080.png`、`evidence/portal-390x844.png`

## 未完成而不是伪造的部分

- 没有图片供应商 Key，因此没有“真实生成成功”的截图。
- 产品入口明确说明两个上游应用目前分别登录，没有 SSO。
- 没有 Android APK、推送、语音、相册或离线交付。
- 没有把模拟提醒状态当成站内通知已送达。
