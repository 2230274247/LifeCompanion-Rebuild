# Runbook

## 前置条件

- Windows PowerShell
- Docker Desktop / Docker Engine 与 Compose
- Node.js 24+（上游依赖要求；本轮本机 Node 22.22.0 构建通过但有 engine 警告）
- Python 3.12
- 可用端口：`3001`、`3080`、`5230`、`8010`
- `infra\.env` 与 `products\librechat-custom\.env` 已存在且未纳入 Git

## 启动顺序

日常本机启动可直接双击桌面的 `启动拾光.cmd`。它调用
`scripts\start-lifecompanion.ps1`，检查 Docker、按需启动 Compose 容器、
`life-core` 与 3001 网关，等待四个健康检查通过后打开统一入口。
重复执行不会重启已健康的服务，也不会清理容器或数据库。
本机进程日志位于 `infra\runtime\launcher-life-core.*.log` 和
`infra\runtime\launcher-gateway.*.log`。

### 1. 上游容器

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" -f "compose.spa.yaml" up -d
docker ps --filter "name=lifecompanion-"
```

不要执行 `docker compose down -v`，除非已经完成备份并明确要删除测试数据。

### 2. 业务服务

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild"
.\services\life-core\run.ps1 -Python "H:\AI For research institute\LifeCompanion-Rebuild\services\life-core\.venv\Scripts\python.exe"
```

### 3. 统一入口

新开终端：

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild"
.\apps\product-portal\run.ps1 -Port 3001
```

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health | ConvertTo-Json
(Invoke-WebRequest http://127.0.0.1:3001/health -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:3080/health -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:5230/healthz -UseBasicParsing).StatusCode
```

统一入口直接服务 LibreChat React SPA，登录后访问 `/c/new` 与 `/memories`。
原静态导航页面和 `/api/services/status` 不再作为产品 UI；维护时使用上述真实健康检查。
`/life-api` 只代理已列出的公开 GET 接口，禁止内部 ingest/bootstrap。

### 重新构建与加载新前端

在 `products/librechat-custom` 运行 `npm run frontend`，成功后在 infra 运行：

```powershell
docker compose --env-file ".env" -f "compose.baseline.yaml" -f "compose.spa.yaml" restart librechat
```

Express 会缓存入口 HTML；只替换 dist 而不重启可能继续引用旧的哈希文件。
新会话可能短暂等待缓存更新，必要时刷新页面。不要通过删除数据库解决静态资产问题。
3001 网关无需因前端构建重启。修改网关或 Python 服务后，用对应 run.ps1 重新启动。

## 测试

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\services\life-core"
..\..\services\life-core\.venv\Scripts\python.exe -m pytest -q tests
```

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild"
node --check apps\product-portal\server.mjs
node --test tests\gateway.test.mjs
node --check apps\product-portal\portal.js
node --check products\librechat-custom\api\app\clients\BaseClient.js
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" config --quiet
```

V0.2 组合配置校验应另加 `-f "compose.spa.yaml"`。前端类型检查、Jest、ESLint
和 Lighthouse 的完整命令与实际结果见本次独立开发日志。
`tests/live-v02.py` 需要现有本地测试账号，可对指定真实会话执行回忆读取和同来源重试，
仅使用 `infra/runtime/test-accounts.json` 与服务端密钥文件；不输出密码或令牌。

## 排障

### LibreChat 页面空白

等待 React 完成加载后刷新。查看后端：

```powershell
docker logs --since 10m lifecompanion-librechat
docker logs --since 10m lifecompanion-mongo
```

重点搜索：

```text
[LifeCompanion] event ingest completed
[LifeCompanion] event ingest rejected
```

### 事件未写入 Memos

1. 查 `GET http://127.0.0.1:8010/health`，确认
   `memos_configured` 和 `internal_auth_configured` 为 `true`。
2. 查 `life-core` 终端错误。
3. 确认 `infra\.env` 中的 `MEMOS_API_TOKEN` 属于映射的 `life-admin`。
4. 查 `events.status`、`events.error_message`、`task_runs.last_error`。
5. 用同一来源消息重试；不应生成重复 Memo。

### 时区错误

确认 `life-core` 环境的 `tzdata` 已安装，并设置：

```text
LIFE_TIMEZONE=Asia/Hong_Kong
```

Windows Python 的 `zoneinfo` 需要 `tzdata` 包；依赖已锁定在
`services/life-core/requirements.txt`。

### 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 3001,3080,5230,8010 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

不要直接停止未知服务；先核对进程命令行，避免影响 Silver Economy 或 Open WebUI。

## 停止

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" stop
```

`life-core` 和产品入口可用各自终端的 `Ctrl+C` 停止。

## 备份

建议先停止容器，再复制数据；不要在容器运行中直接移动或清空卷：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Compress-Archive -Path "infra\volumes" -DestinationPath "infra\runtime\lifecompanion-volumes-$stamp.zip"
Copy-Item "services\life-core\data\life-core.sqlite3" "infra\runtime\life-core-$stamp.sqlite3"
```

备份与恢复先在测试环境验证。不得对未知目录执行递归删除或强制覆盖。

## 安全

- 不提交 `infra\.env`、`products\librechat-custom\.env`、
  `infra\runtime\test-accounts.json` 或数据库。
- 不在浏览器控制台、截图和日志中显示 Key、PAT、JWT 或密码。
- 不推送到 LibreChat/Memos 官方上游。
# V0.2.1 本地增量运行说明（2026-11-02）

原有运行说明保留在后文。当前集成边界见
`docs/architecture/V02_1_MEMORY_REMINDERS.md`。

1. 在根目录执行 `powershell -ExecutionPolicy Bypass -File scripts/start-lifecompanion.ps1 -NoBrowser`。
   启动器存在 `infra/.env.reminders` 时启动原版提醒容器；不会清理原数据卷。
2. 统一入口为 `http://127.0.0.1:3001/`。聊天、回忆、`/memory-settings`、`/reminders`
   共用 LibreChat 登录；用户不登录上游管理台。
3. 自动整理、使用既有事实及敏感类别在“记忆与权限”单独开启；
   主动通知在“提醒”开启。只有授权后的信息才参与相应用途。
4. 已映射的隔离账号可说“明天九点提醒我喝茶”。后端确认后列表出现真实事项。
   列表可修改、办完或取消；含秒时间向后归整到分钟，以页面实际时间为准。
5. 目前仅明确配置的合成账号已接提醒。普通账号提示未连接；这不是自动开户产品。
   测试账号登录资料只在 ignored runtime，禁止复制到文档或截图。

配置模板为 `infra/reminders.env.example`；实际镜像 digest 固定于 `.env.reminders`。
`LIFE_VIKUNJA_USERS_FILE` 指向服务端 JSON，按 life_user_id 配置 `api_token`、
`project_id`、`vikunja_user_id`、`webhook_secret`、`ntfy_base_url`、
`ntfy_topic`、`ntfy_user`、`ntfy_password`。每人独立身份和 ACL，禁止共享管理员 token。
合成 A/B 的映射在 `infra/runtime/reminders/users.json`，不是可公开下载的配置。
受限 token 有效七天，后续需服务端续期。不得打印 `docker compose config` 的展开密钥；
验证配置仅用 `config --quiet`。

上游回调直接到 life-core 的 `/api/v1/webhooks/vikunja`，要求 HMAC；
3001 不公开 webhook/internal。Windows Docker 使用 `host.docker.internal:8010`。
当前允许 nonroutable outbound 仅为本机隔离测试，不能直接搬到公网。

源码重建后需重启 `lifecompanion-librechat` 让 Express 重读 HTML；
修改 life-core/gateway 代码或服务端映射需核对项目进程再定向重启。
启动器会复用健康实例，不等于自动载入新代码。严禁按端口批量杀其他项目。

回归证据统一在 `evidence/v02-memory-reminders/`。
系统通知、关页后台、手机、固定周期提醒和图片生成尚不可作为可用能力演示。
