# 注册功能与桌面启动脚本 · 验收矩阵

生成时间：2026-11-06 10:05（Asia/Hong_Kong）

## 后端测试

| 项 | 命令 | 状态 |
| --- | --- | --- |
| 注册/校验/登录策略单测 | `npx jest server/services/AuthService.spec.js strategies/validators.spec.js strategies/localStrategy.spec.js --ci --silent` | PASS（3 suites / 103 tests） |
| 用户名注册 | `POST /api/auth/register` username+password+confirm | PASS（200，role=USER，占位邮箱，token+user） |
| 用户名登录 | `POST /api/auth/login` email=username | PASS（200） |
| 重复用户名 | 同接口再次提交同名 | PASS（409，`Username is already in use.`） |
| 普通用户访问管理接口 | `GET /api/admin/users` Bearer 普通用户 token | PASS（403 Forbidden） |
| 服务器错误脱敏 | AuthService.spec 断言 | PASS（不泄露密码） |

## 前端测试

| 项 | 命令 | 状态 |
| --- | --- | --- |
| 注册/登录表单单测 | `npx jest src/components/Auth/__tests__/Registration.spec.tsx src/components/Auth/__tests__/LoginForm.spec.tsx --ci --coverage=false --silent` | PASS（2 suites / 6 tests） |
| 桌面注册页截图 | Playwright 1440×900 | PASS |
| 移动注册页截图 | Playwright 390×844 | PASS |
| 注册后已登录截图 | Playwright UI 注册 → `/c/new` | PASS |

## 启动器

| 项 | 命令 | 状态 |
| --- | --- | --- |
| 语法检查 | PowerShell Parser::ParseFile | PASS |
| 已运行服务复用 | `start-lifecompanion.ps1 -NoBrowser` | PASS（四健康检查通过，未打开浏览器） |
| 前端过期 + 跳过重建 | `start-lifecompanion.ps1 -NoBrowser -SkipBuild` | PASS（明确报错停止） |
| 前端重建 | `npm run frontend` | PASS（build 成功） |
| 未启动冷启动 | 未执行（当前服务已运行） | BLOCKED |
| 部分服务缺失 | 未执行（避免破坏运行环境） | BLOCKED |
| 无关端口占用 | 未执行（避免占用真实端口） | BLOCKED |
| 依赖缺失 | 未执行（本机依赖齐全） | BLOCKED |
| 数据库不可用 | 未执行（避免停库） | BLOCKED |

## 数据库

| 项 | 状态 |
| --- | --- |
| Mongo 备份 | PASS（`infra/runtime/backup/20261106-username-index/librechat.archive`） |
| life-core SQLite 备份 | PASS（同目录 `life-core.sqlite3`） |
| username 唯一索引 | PASS（部分唯一索引 `{username:1, tenantId:1}`） |

## 说明

- 标记 BLOCKED 的启动器场景需要破坏当前运行环境，未在本机自动化；对应逻辑已实现并在代码中体现。
- 真实邮箱验证（`emailEnabled=true`）依赖 SMTP，未在本机验证；当前部署 `emailEnabled=false`。
