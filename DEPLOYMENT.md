# Deployment

本文描述从另一个目录或另一台主机重建 LifeCompanion-Rebuild 的可复现流程。
仓库不含真实密钥、用户数据库、聊天、上传图片或运行卷。GitHub clone 只得到
代码、测试、配置模板和固定上游补丁。

## 1. 组件与部署边界

默认采用混合部署：

| 组件 | 运行方式 | 持久数据 |
| --- | --- | --- |
| LibreChat | Docker 固定 tag | `infra/volumes/librechat-mongo`、uploads |
| Memos | Docker 固定 tag | `infra/volumes/memos` |
| Meilisearch | Docker 固定 tag | `infra/volumes/librechat-meili` |
| life-core + worker | 宿主机 Python venv | `services/life-core/data/` |
| 同源网关 | 宿主机 Node.js | 无业务数据库 |
| Vikunja / ntfy | 可选 Docker Compose | `infra/runtime/reminders/` |

`life-core` 内的两个后台线程分别处理事件/通知和回忆评分/生图任务。
`LIFE_MOMENT_WORKERS_ENABLED=true` 时不能遗漏该进程；如果需要独立调度，
使用 `LIFE_MOMENT_SCHEDULER_EXTERNAL=true` 并同时运行兼容 worker。

默认端口只绑定 loopback。公网部署应在网关前增加 HTTPS 反向代理，且不要把
MongoDB、Meilisearch、SQLite、Memos 管理端口直接暴露到互联网。

## 2. Windows

### 2.1 安装先决条件

- Git
- Docker Desktop（启用 Linux containers）
- Node.js 22.12+，推荐 Node.js 24 LTS
- Python 3.12

### 2.2 clone 和密钥

```powershell
cd <parent-directory>
git clone <authorized-repository-url> LifeCompanion-Rebuild
cd LifeCompanion-Rebuild
Copy-Item model_api_keys.env.example ..\model_api_keys.env
```

如果父目录文件已存在，不要覆盖。真实 Key 只能填写在父目录文件中。
使用管理员 PowerShell 收紧 ACL：

```powershell
$file = (Resolve-Path ..\model_api_keys.env).Path
icacls $file /inheritance:r
icacls $file /grant:r "$env:USERNAME:(R)"
icacls $file /grant:r "SYSTEM:(F)"
icacls $file /grant:r "BUILTIN\Administrators:(F)"
attrib -H -S $file
```

运行服务的账户必须能读取该文件，其他普通账户不应有读权限。

### 2.3 初始化

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-lifecompanion.ps1
```

脚本仅在缺失时创建 `infra\.env`、上游 `.env` 和父目录密钥文件；不会覆盖
已有非占位值。它还会为内部令牌、Memos 初始管理员、JWT、凭据加密和
Meilisearch 生成本机随机值。Memos 初始管理员为 `lifecompanion-admin`，
其密码只写入被忽略的 `infra\.env`；LibreChat 本地密钥写入同样被忽略的
`products\librechat-custom\.env`。随后脚本克隆 LibreChat `v0.8.8`、
应用补丁、执行 `npm ci`、`npm run frontend`，并安装 Python 依赖。

### 2.4 启动和检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-lifecompanion.ps1
powershell -ExecutionPolicy Bypass -File scripts\check-health.ps1
```

日志：

```text
infra\runtime\launcher-life-core.out.log
infra\runtime\launcher-life-core.err.log
infra\runtime\launcher-gateway.out.log
infra\runtime\launcher-gateway.err.log
```

## 3. Ubuntu

### 3.1 先决条件

以 Ubuntu 24.04 为例，安装 Git、Docker Engine/Compose、curl、Node.js 和
Python 3.12。Node 建议通过受信任的 NodeSource 或版本管理器安装。

```bash
sudo apt-get update
sudo apt-get install -y git curl python3 python3-venv
node --version
npm --version
docker --version
docker compose version
```

如果当前用户没有 Docker 权限，按组织安全策略把该用户加入 `docker` 组；
生产环境更推荐 rootless Docker 或受控服务账户。

### 3.2 clone 和密钥

```bash
cd <parent-directory>
git clone <authorized-repository-url> LifeCompanion-Rebuild
cd LifeCompanion-Rebuild
cp model_api_keys.env.example ../model_api_keys.env
chmod 600 ../model_api_keys.env
```

父目录密钥文件应属于运行服务的账户，例如：

```bash
chown "$USER":"$USER" ../model_api_keys.env
chmod 600 ../model_api_keys.env
```

### 3.3 初始化、启动和检查

```bash
bash scripts/bootstrap-lifecompanion.sh
bash scripts/start-lifecompanion.sh
bash scripts/check-health.sh
```

Linux 上容器通过 Compose 的 `host.docker.internal:host-gateway` 访问宿主机
`life-core`。防火墙只需允许实际反向代理访问网关端口；不要公开容器内部端口。

## 4. 非敏感配置

```bash
cp .env.example infra/.env
cp products/librechat-custom/.env.example products/librechat-custom/.env
```

至少检查：

- `LIFE_INTERNAL_TOKEN`
- `MEMOS_API_TOKEN`
- LibreChat JWT / refresh secret
- `MEILI_MASTER_KEY`
- `LIFE_ALLOWED_ORIGINS`
- `LIFE_TIMEZONE`
- 各模型请求预算与生图开关

如果直接复制模板而不是运行 bootstrap，必须手动替换 `JWT_SECRET`、
`JWT_REFRESH_SECRET`、`CREDS_KEY`、`CREDS_IV`、`MEMOS_BOOTSTRAP_ADMIN_PASSWORD`
等占位值。`CREDS_KEY` 使用 64 个十六进制字符，`CREDS_IV` 使用 32 个。

字段说明见 `CONFIGURATION.md`。不要使用 `docker compose config` 直接打印
展开后的完整环境；只使用 `config --quiet` 做校验。

## 5. 数据库初始化和迁移

`life-core` 启动时调用 `Store.initialize()`，在目标 SQLite 中创建缺失表并
执行兼容迁移。现有表、用户映射、回忆和媒体文件不会被清空。新环境得到空库；
应用不会自动导入真实用户数据。

Memos 和 LibreChat 使用官方镜像的首次初始化流程。MongoDB 与 Memos 数据在
`infra/volumes/` 持久化。备份前应先停止对应写服务。

## 6. 备份、恢复和升级

### Windows

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "..\_backups\lifecompanion-$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
docker compose -f infra\compose.baseline.yaml stop
Copy-Item -Recurse infra\volumes $backup\volumes
Copy-Item -Recurse services\life-core\data $backup\life-core-data
Copy-Item ..\model_api_keys.env $backup\model_api_keys.env
Get-FileHash -Algorithm SHA256 (Get-ChildItem $backup -File -Recurse) |
  Out-File $backup\SHA256SUMS.txt
```

### Ubuntu

```bash
stamp="$(date +%Y%m%d-%H%M%S)"
backup="../_backups/lifecompanion-$stamp"
mkdir -p "$backup"
(cd infra && docker compose --env-file .env -f compose.baseline.yaml stop)
cp -a infra/volumes services/life-core/data "$backup/"
cp -a ../model_api_keys.env "$backup/model_api_keys.env"
(cd "$backup" && find . -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt)
```

密钥备份必须置于加密介质，不得进入 Git 或普通云盘共享目录。恢复时停止服务、
核对 SHA256、恢复数据目录后再启动。不要用空白卷覆盖非空持久卷。

## 7. 运行验证

健康检查全部返回 200 只说明进程就绪。还需验证：

1. LibreChat 登录与新建会话。
2. 发送一条合成测试消息，确认消息持久化。
3. `/memories` 能读取当前用户的私有回忆。
4. 重启后账号、会话、SQLite 和媒体仍存在。
5. `/health` 的模型状态只显示 `SET` / `MISSING`。
6. 缺 Key 时文本、本地回忆和其他非云功能仍可用；云调用明确降级。
7. 有授权凭证时执行一次受预算限制的真实模型或生图调用。

## 8. 常见问题

- `model_api_keys.env` 不存在：云功能为 `MISSING`，本地功能可运行。
- Linux 容器无法访问 `life-core`：确认 Compose 配置含
  `host.docker.internal:host-gateway`。
- 页面启动但静态资源为旧版本：重新执行前端构建，再重启 LibreChat。
- 端口冲突：启动脚本会拒绝接管未知进程，不会按端口误杀其他项目。
- 前端白屏：查看 LibreChat 容器日志并确认 `client/dist` 已成功构建。
- SQLite 锁等待：确认只有一个 worker 写同一数据库，或按队列方案拆分。

## 9. 发布状态

截至 2026-11-04，本仓库没有配置授权 GitHub remote，无法执行真实 GitHub
clone/push。本地 release-equivalent clone 演练结果记录在
`docs/maintenance/PORTABILITY_AUDIT.md`。在提供仓库地址和权限前，
GitHub 上传状态为 `BLOCKED_REMOTE`。
