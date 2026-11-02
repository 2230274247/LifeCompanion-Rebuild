# Test Results

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
