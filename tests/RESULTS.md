# Test Results

## 2026-11-02 V0.2.1 实跑增量

总体 PARTIAL。最新前端 122、life-core 30、LibreChat API 包 78、网关 2 项通过，
为限定范围共 232 个测试，不是覆盖率或全量测试。真实记忆、原版提醒、
life-core v2 全链路和双用户通知隔离另有独立验收，不混入单元测试数。
TypeScript、定向 ESLint、生产构建、两套 Compose quiet 校验通过。
Lighthouse 隔离注册前置步骤失败，尚无性能指标。
命令、精确时间、失败与重测见 [证据索引](../evidence/v02-memory-reminders/README.md)。

以下保留历史 V0.1/V0.2 结果。

日期：2026-11-02  
环境：Windows 11 本地、PowerShell、Docker Desktop、Python 3.12.10、Node.js 22.22.0

## 自动化测试

```text
Command: services\life-core\.venv\Scripts\python.exe -m pytest -q tests
Result: 7 passed
```

覆盖：

- 真实过去事件可抽取；
- 未来计划被拒绝；
- 否定表达被拒绝；
- 普通聊天被拒绝；
- 同来源消息幂等；
- 用户隔离；
- 内部令牌拒绝。

## 静态与集成检查

| 检查 | 结果 |
| --- | --- |
| `node --check products\librechat-custom\api\app\clients\BaseClient.js` | PASS |
| `node --check apps\product-portal\server.mjs` | PASS |
| `node --check apps\product-portal\portal.js` | PASS |
| Docker Compose config + `infra\.env` | PASS |
| LibreChat `/health` | HTTP 200 |
| Memos `/healthz` | HTTP 200 |
| `life-core /health` | HTTP 200 |
| 产品入口 `/health` | HTTP 200 |

## 真实链路

真实聊天、事件、Memos 私有写入、刷新持久化与同来源重试见
`evidence/vertical-slice-verification.json`。

## 未验证

- 真实图片 Provider（`BLOCKED_IMAGE_PROVIDER`）
- Android 真机/APK
- SSO
- 浏览器站内通知和手机推送

## V0.2 增量验收（2026-11-02）

上文保留 V0.1 历史结果；V0.2 当前结果为 life-core 16 条、网关 1 条、
前端限定回归 115 条通过，共 132 条，不代表全库测试覆盖率。
类型、lint、构建、真实链路及前后失败修复证据见
`evidence/v02-tests/README.md`。

统一 SPA 复用 LibreChat 登录；当前仍为显式单用户映射，
不是跨应用身份平台或多人开户交付。Lighthouse 因 Windows harness 空格路径启动失败
标记 BLOCKED，不能声称性能预算通过。完整记录见
`docs/development-log/2026-11-02_18-12_统一前端与回忆集成_开发验收.md`。
