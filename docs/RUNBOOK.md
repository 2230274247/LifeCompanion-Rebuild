# Runbook

## 前置条件

- Windows PowerShell
- Docker Desktop / Docker Engine 与 Compose
- Node.js 22+
- Python 3.12
- 可用端口：`3001`、`3080`、`5230`、`8010`
- `infra\.env` 与 `products\librechat-custom\.env` 已存在且未纳入 Git

## 启动顺序

### 1. 上游容器

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" up -d
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

产品入口 `/api/services/status` 会实时探测三个服务，不用伪造静态状态。

## 测试

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\services\life-core"
..\..\services\life-core\.venv\Scripts\python.exe -m pytest -q tests
```

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild"
node --check apps\product-portal\server.mjs
node --check apps\product-portal\portal.js
node --check products\librechat-custom\api\app\clients\BaseClient.js
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" config --quiet
```

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
