# LifeCompanion-Rebuild

LifeCompanion-Rebuild（拾光）是在真实 LibreChat 与 Memos 之上构建的
AI 生活伙伴与人生回忆录纵向切片。它保留上游聊天、账号与私有回忆能力，
由独立 `life-core` 服务处理事件提取、回忆窗口、提醒和图片生成。

当前状态：本地功能链路与生图一致性回归通过；GitHub 远端尚未配置，因此
发布地址与真实 GitHub clone/push 状态为 `BLOCKED_REMOTE`。

## 架构

```text
Browser
  -> product-portal / Node.js gateway :3001
       -> LibreChat React / API / SSE :3080
       -> life-core / FastAPI :8010
            -> SQLite business state
            -> private moment-media directory
            -> Memos private API :5230
            -> DeepSeek / Zhipu text models
            -> SiliconFlow Kolors
       -> optional Vikunja / ntfy reminder services
```

关键边界：

- LibreChat 管理自己的 MongoDB；Memos 管理自己的数据库。
- `life-core` 使用独立 SQLite，worker 与定时任务在同一 FastAPI 进程内运行。
- 浏览器只持 LibreChat 登录态；云模型 Key、Memos PAT 和内部令牌只在后端。
- 回忆图片属于 AI 艺术化创作，不冒充用户拍摄的真实照片。

## 目录

```text
apps/product-portal/       同源 HTTP/SSE 网关
services/life-core/        FastAPI 业务服务、worker、SQLite 与测试
infra/                     Docker Compose、模板和本机持久卷
patches/                   固定上游版本的可复现 LibreChat 补丁
scripts/                   Windows / Ubuntu 初始化、启动与健康检查
tests/                     网关、端到端与真实集成测试
docs/                      架构、配置、安全、部署和审计
evidence/maintenance/      本轮整改的可核对证据
fixtures/                  合成测试数据说明
```

## 先决条件

- Git 2.40+
- Docker Engine / Docker Desktop 与 Compose v2.24+
- Node.js 22.12+（推荐 24 LTS）及 npm
- Python 3.12
- Windows PowerShell 7 或 Ubuntu 22.04/24.04
- 默认本机端口：`3001`、`3080`、`5230`、`8010`

默认只绑定 `127.0.0.1`。若部署到公网，必须在前面增加 HTTPS 反向代理，
并单独配置域名、TLS、认证与速率限制；不要直接公开 MongoDB、Meilisearch、
SQLite 文件或内部模型端口。

详细环境说明见 [DEPLOYMENT.md](DEPLOYMENT.md) 与
[CONFIGURATION.md](CONFIGURATION.md)。

## 从空目录初始化

先取得本项目代码：

```text
git clone <authorized-repository-url> LifeCompanion-Rebuild
```

真实仓库 URL 尚未由项目所有者提供，因此当前不能给出可执行的 GitHub 地址。
不要复用旧工程 `Silver-economy` 的远端。

在项目**母目录**创建可见但受权限保护的唯一云模型密钥文件：

```text
<parent-directory>/
├── model_api_keys.env
└── LifeCompanion-Rebuild/
```

模板在仓库根目录 `model_api_keys.env.example`。真实文件不得放入仓库、
前端构建目录、浏览器存储或日志。

Windows：

```powershell
cd <parent-directory>\LifeCompanion-Rebuild
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-lifecompanion.ps1
```

Ubuntu：

```bash
cd <parent-directory>/LifeCompanion-Rebuild
bash scripts/bootstrap-lifecompanion.sh
```

初始化脚本会：

1. 仅在缺失时创建父目录 `model_api_keys.env`、`infra/.env` 与上游 `.env`。
2. 克隆固定 LibreChat `v0.8.8`，应用当前累计补丁。
3. 使用 lockfile 安装依赖并构建 React 前端。
4. 创建 `services/life-core/.venv` 并安装锁定 Python 依赖。

脚本不会覆盖已有密钥、数据库或用户数据。需要跳过耗时前端构建时可使用
Windows `-SkipFrontendBuild` 或 Ubuntu `SKIP_FRONTEND_BUILD=1`，但首次部署
不应跳过。

## 配置

非敏感配置复制到被 Git 忽略的 `infra/.env` 与
`products/librechat-custom/.env`。云模型值只从项目母目录
`model_api_keys.env` 读取。`LIFECOMPANION_KEYS_FILE` 可覆盖为绝对路径，
用于容器或密钥服务注入；相对路径会被拒绝。

服务端 `/health` 只返回每个提供商的 `SET` / `MISSING` 状态，不返回密钥值。
修改父目录密钥后需重启 `life-core` 和依赖该密钥的 LibreChat 容器。

完整字段、模型别名、预算与降级说明见 [CONFIGURATION.md](CONFIGURATION.md)。

## 启动

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-lifecompanion.ps1
```

Ubuntu：

```bash
bash scripts/start-lifecompanion.sh
```

脚本可重复执行：会复用已健康服务，不删除容器、卷或数据库。日志写入
`infra/runtime/launcher-*.log`。自定义端口示例：

```powershell
.\scripts\start-lifecompanion.ps1 -GatewayPort 13001 -CorePort 18010 -ChatPort 13080 -MemosPort 15230
```

```bash
GATEWAY_PORT=13001 CORE_PORT=18010 CHAT_PORT=13080 MEMOS_PORT=15230 \
  bash scripts/start-lifecompanion.sh
```

健康检查：

```powershell
.\scripts\check-health.ps1
```

```bash
bash scripts/check-health.sh
```

打开 `http://127.0.0.1:3001`，聊天入口为 `/c/new`，回忆为 `/memories`。

## 测试

后端：

```powershell
cd services\life-core
..\..\services\life-core\.venv\Scripts\python.exe -m pytest -q tests
```

```bash
cd services/life-core
.venv/bin/python -m pytest -q tests
```

网关与语法：

```powershell
node --check apps\product-portal\server.mjs
node --test tests\gateway.test.mjs
node --check apps\product-portal\portal.js
```

Compose 配置只做静默校验，避免展开并打印真实环境值：

```powershell
cd infra
docker compose --env-file .env -f compose.baseline.yaml -f compose.spa.yaml config --quiet
```

真实云模型与生图测试需要有效父目录密钥和明确授权。最近一次结果：

- 后端完整测试：`317 passed, 1 warning`
- 网关测试：`4 passed`
- 真实 Kolors：3/3 HTTP 200，人工一致性核对 PASS
- 当前新图聊天/回忆 UI：PASS，0 个新付费生图请求

证据与限制见
`docs/maintenance/IMAGE_FIDELITY_AUDIT.md`。

## 数据与备份

持久数据默认位于：

- `infra/volumes/librechat-mongo`
- `infra/volumes/librechat-meili`
- `infra/volumes/memos`
- `services/life-core/data/life-core.sqlite3`
- `services/life-core/data/moment-media/`
- 可选 `infra/runtime/reminders/`

这些路径都被 Git 忽略。升级或迁移前先停止写入并做一致性备份；不要使用
`docker compose down -v`、清空卷或覆盖 SQLite。备份恢复步骤见
[DEPLOYMENT.md](DEPLOYMENT.md)。

## 安全

- 唯一真实云模型密钥文件是项目母目录 `model_api_keys.env`。
- `VITE_*`、`NEXT_PUBLIC_*`、前端构建参数和浏览器 API 中不得出现 Key。
- 内部接口只由网关白名单或服务端令牌访问。
- GitHub 推送前必须扫描工作树和 Git 历史；发现历史泄露时先轮换密钥，
  不能仅删除工作树文件。

完整规则见 [SECURITY.md](SECURITY.md)。

## 文档

- `DEPLOYMENT.md`：Windows / Ubuntu 初始化、启动、重建和恢复
- `CONFIGURATION.md`：非敏感配置、模型、预算与降级
- `SECURITY.md`：密钥、隐私、日志和发布前检查
- `CHANGELOG.md`：当前整改变更
- `docs/ARCHITECTURE.md`：组件与数据流
- `docs/RUNBOOK.md`：运行排障
- `docs/UPSTREAM_MANIFEST.md`：固定上游版本与许可证
- `docs/maintenance/PROJECT_IDENTITY_AUDIT.md`：项目身份证据
- `docs/maintenance/CLEANUP_AUDIT.md`：安全清理与备份
- `docs/maintenance/IMAGE_FIDELITY_AUDIT.md`：生图链路修复与真实样例
- `docs/maintenance/PORTABILITY_AUDIT.md`：空环境迁移演练与发布状态
