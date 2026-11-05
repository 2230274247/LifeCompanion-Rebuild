# LifeCompanion V0.3 Ubuntu 部署说明（候选版本）

本目录把 `feat/v03-collaboration-20261105` 的最新可交付代码打包为
Ubuntu 24.04 LTS 的 Docker Compose 部署。多账号协作（好友、空间、共享回忆、
权限与数据隔离）由 `life-core` 提供，聊天前端由 LibreChat 承载，网关统一入口。

> 状态：候选部署版本（`v0.3.0-deploy-rc1`）。核心代码已通过单元测试与前端
> typecheck，但完整浏览器/API 回归未在本轮打包流程中重新执行。

## 1. 目录结构

```text
deploy/ubuntu/
  compose.yaml              # 全栈编排：gateway + life-core + LibreChat + 依赖
  Dockerfile.gateway        # 网关镜像（Node 24）
  Dockerfile.life-core      # life-core 镜像（Python 3.12）
  .env.example              # 环境变量模板（无真实密钥）
  build-librechat.sh        # 从补丁重建 LibreChat 自定义产物（Node 24）
  scripts/                  # 一键安装、启停、备份、恢复、迁移、健康检查、测试账号
  librechat-custom/         # LibreChat 自定义构建产物（打包时生成，不入库）
  volumes/                  # 运行时数据（启动后生成，不入库）
```

## 2. 前置条件（Ubuntu 24.04 LTS）

- Docker Engine 24+ 与 `docker compose` 插件
- `curl`、`openssl`、`git`
- 若需从源码重建前端：Node 24+（见 `build-librechat.sh`）

## 3. 一键安装

```bash
cd deploy/ubuntu
cp .env.example .env
chmod 600 .env
# 编辑 .env，至少填入 DEEPSEEK_API_KEY；其余密钥可先用 install.sh 自动生成
vim .env
./install.sh
```

`install.sh` 会：

1. 若 `.env` 不存在，从模板生成并填入 `openssl rand -hex` 随机密钥；
2. 检查 LibreChat 自定义产物与 Docker 环境；
3. `docker compose up -d --build` 启动全部服务；
4. 通过 `ntfy user add --role=admin` 初始化推送管理账号；
5. 执行健康检查。

## 4. 服务与端口

| 服务 | 容器 | 用途 | 端口 |
| --- | --- | --- | --- |
| gateway | lifecompanion-gateway | 统一入口，代理前端与 `/life-api` | 3001（对外） |
| life-core | lifecompanion-life-core | 多账号协作、记忆、提醒、共享回忆 | 8010（内网） |
| librechat | lifecompanion-librechat | 聊天前端与账号体系 | 3080（内网） |
| mongo / meili | — | LibreChat 数据与搜索 | 内网 |
| memos | lifecompanion-memos | V0.2 记忆召回上游（可选） | 内网 |
| vikunja / ntfy | — | 定时提醒与推送 | 内网 |

访问地址：`http://<服务器IP>:3001`

## 5. 常用操作

```bash
./scripts/start.sh       # 启动（保留数据）
./scripts/stop.sh        # 停止（保留命名卷）
./scripts/healthcheck.sh # 检查 gateway / life-core / librechat
./scripts/backup.sh      # 备份到 backups/backup-时间戳.tar.gz
./scripts/restore.sh backups/backup-*.tar.gz
./scripts/migrate.sh     # 触发 life-core SQLite 结构升级并校验
./scripts/init-test-accounts.sh  # 生成管理员 + 普通用户测试账号
./scripts/update.sh      # git pull + 重建 + 迁移 + 重启，保留数据
```

## 6. 环境变量要点

- `JWT_SECRET`：LibreChat 与 life-core 共享，用于跨服务身份识别。
- `LIFE_INTERNAL_TOKEN`：life-core 内部接口令牌，LibreChat 调用时使用。
- `LIFE_CREDENTIAL_MASTER_KEY`：Linux 下加密提醒账号凭据的 Fernet 主密钥。
- `LIFE_NTFY_ADMIN_USER` / `LIFE_NTFY_ADMIN_PASSWORD`：life-core 通过 ntfy
  管理 HTTP API 创建每用户推送账号（容器内无 Docker socket 时的替代方案）。
- `DEEPSEEK_API_KEY`：聊天与记忆抽取使用的模型密钥。

## 7. 数据持久化

所有状态写入 `deploy/ubuntu/volumes/`（已被 `.gitignore` 排除）：

- `life-core-data/life-core.sqlite3`：用户映射、记忆、协作关系、提醒
- `librechat-mongo`：聊天账号、会话、消息
- `librechat-uploads`：上传图片
- `memos` / `vikunja*` / `ntfy-*`：各上游数据

`stop.sh` 只停容器、不删卷；`update.sh` 重建镜像也不触碰这些目录，因此
账号、记忆、图片和业务数据在重启与升级后仍然保留。

## 8. 常见问题

- **`CREDENTIAL_MASTER_KEY_REQUIRED`**：`.env` 缺少
  `LIFE_CREDENTIAL_MASTER_KEY`，或该值仍为 `change_me_*`。
- **`NTFY_PROVISIONING_UNAVAILABLE`**：ntfy 未启动或 `.env` 中
  `LIFE_NTFY_ADMIN_USER/PASSWORD` 与 install.sh 初始化的管理员不一致。
- **`USER_NOT_MAPPED`**：LibreChat 账号尚未在 life-core 完成映射。首次在
  “拾光”界面连接记忆/提醒时会自动创建映射。
- **Mongo 未就绪**：LibreChat 等待 mongo 健康检查通过；首次拉取镜像较慢属正常。
- **80/3001 被占用**：修改 `.env` 的 `GATEWAY_PORT` 后重新 `install.sh`。

## 9. 安全说明

- 不要把 `.env`、`test-accounts.env`、`volumes/`、`librechat-custom/` 提交到仓库。
- 数据库默认 `--noauth`，仅应监听内网；不要将 27017 暴露到公网。
- 生产环境请为 `gateway` 前加 HTTPS 反向代理（Caddy/Nginx）并限制来源。
