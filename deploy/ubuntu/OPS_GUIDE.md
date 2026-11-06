# LifeCompanion Ubuntu 运维指南

本文档覆盖：首次部署、每次更新、GitHub 公开与否、公网发布与日常运维。
部署分支：`feat/v03-collaboration-20261105`。

## 一、GitHub 要不要公开

不是必须公开，有两种做法。

### 方案 A：公开仓库（最简单）

把仓库设为 Public，服务器直接 `git clone` / `git pull`，无需任何凭据。
代价：全部源码、补丁、验收截图和测试数据对所有人可见。

### 方案 B：保持私有 + 只读 Deploy Key（推荐）

在 Ubuntu 服务器上生成密钥：

```bash
ssh-keygen -t ed25519 -C "lifecompanion-deploy" -f ~/.ssh/lifecompanion_deploy -N ""
cat ~/.ssh/lifecompanion_deploy.pub
```

把输出的公钥贴到 GitHub 仓库 `Settings -> Deploy keys -> Add deploy key`，
只勾选只读（不要勾 Allow write access），然后用 SSH 地址克隆：

```bash
cd /opt
git clone git@github.com:2230274247/LifeCompanion-Rebuild.git
```

结论：只想给部分人发链接、但源码不想暴露，用方案 B；不在乎源码公开，用方案 A。

## 二、首次部署（Ubuntu 服务器第一次）

```bash
# 1) 安装运行时
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git curl python3 python3-venv ca-certificates
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"          # 执行后重新登录一次

# 2) 安装 Node 24（LibreChat 前端构建需要）
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3) 拉取项目（公开仓库用 https；私有仓库用上面的 SSH 地址）
cd /opt
git clone https://github.com/2230274247/LifeCompanion-Rebuild.git
cd LifeCompanion-Rebuild
git checkout feat/v03-collaboration-20261105

# 4) 构建 LibreChat 自定义前端（只做一次，耗时长属正常）
bash deploy/ubuntu/build-librechat.sh

# 5) 生成密钥、启动、填模型 Key
cd deploy/ubuntu
./install.sh
vim .env                              # 填 DEEPSEEK_API_KEY=sk-xxx
                                        # 生图还要填 IMAGE_PROVIDER_API_KEY=sk-xxx
                                        # 记忆召回/发布还要填 MEMOS_API_TOKEN=memos_pat_xxx
sed -i 's|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=http://你的公网IP:3001|' .env
sed -i 's|^LIFE_ALLOWED_ORIGINS=.*|LIFE_ALLOWED_ORIGINS=http://你的公网IP:3001|' .env
./scripts/start.sh
./scripts/healthcheck.sh               # 应看到 gateway / life-core / librechat 全 OK

# 让现有管理员账号 admin@shiguang.test 获得一键纳入回忆/一键生图测试能力：
./scripts/bootstrap-admin.sh admin@shiguang.test
```

关键点：`PUBLIC_ORIGIN` 和 `LIFE_ALLOWED_ORIGINS` 必须改成公网地址，
否则从公网访问时登录/CORS 会异常。

## 三、每次更新后的操作

### 本地（Windows 开发机）

每次开发完成后在项目根目录执行：

```powershell
git status
git add <改动的文件>
git commit -m "feat: 描述"
git push origin feat/v03-collaboration-20261105
```

### 服务器（Ubuntu）

```bash
cd /opt/LifeCompanion-Rebuild
git pull --ff-only

# 判断：本次更新是否改了 LibreChat 前端/补丁（patches/*.patch）？
#  是 -> 先重建前端（耗时长）
bash deploy/ubuntu/build-librechat.sh

# 常规更新（重建网关/后端镜像 + 迁移 + 重启 + 健康检查）
cd deploy/ubuntu
./scripts/update.sh
```

`update.sh` 会自动：`git pull` -> 重建 `gateway` 和 `life-core` 镜像 ->
执行数据库迁移 -> `docker compose up -d` -> 健康检查。
数据卷不会被删除，账号、记忆、图片都保留。

判断是否要先跑 `build-librechat.sh` 的简单规则：如果改动涉及 `patches/`、
LibreChat 聊天/注册页面，或明确被告知「改了前端」，就先跑第 4 步再跑
`update.sh`；纯后端改动只跑 `update.sh`。

## 四、部署到公网

1. 开放端口：

```bash
sudo ufw allow 3001/tcp
```

2. 让公网能访问到主机：

- 主机有公网 IP：直接访问 `http://公网IP:3001`。
- 主机在路由器后面：在路由器后台做端口转发，把公网 `3001`（或 `80`）
  转到 Ubuntu 主机内网 IP 的 `3001`。

3. 想直接用 80 端口访问：

```bash
cd /opt/LifeCompanion-Rebuild/deploy/ubuntu
sed -i 's/^GATEWAY_PORT=.*/GATEWAY_PORT=80/' .env
docker compose up -d
```

之后访问 `http://公网IP`（80 端口）。

## 五、永久运行

- 所有容器已配 `restart: unless-stopped`，崩溃自动恢复。
- Docker 已 `systemctl enable --now docker`，主机重启后会自动拉起容器。
- 可选，再加一层 systemd 保险：

```bash
sudo tee /etc/systemd/system/lifecompanion.service >/dev/null <<'EOF'
[Unit]
Description=LifeCompanion stack
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/LifeCompanion-Rebuild/deploy/ubuntu
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now lifecompanion.service
```

## 六、日常运维速查

```bash
cd /opt/LifeCompanion-Rebuild/deploy/ubuntu

./scripts/healthcheck.sh                 # 健康检查
docker compose ps                        # 看容器状态
docker compose logs -f life-core         # 看后端日志
docker compose logs -f librechat         # 看聊天服务日志
./scripts/stop.sh                        # 停止（保留数据）
./scripts/start.sh                       # 启动
./scripts/backup.sh                      # 备份到 backups/backup-时间戳.tar.gz
./scripts/restore.sh backups/xxx.tar.gz  # 恢复
./scripts/init-test-accounts.sh          # 生成测试账号（密码写入 test-accounts.env，权限 600）
./scripts/bootstrap-admin.sh admin@shiguang.test  # 将现有账号提升为管理员测试账号
cat test-accounts.env                    # 查看测试账号密码
```

## 七、常见问题

- 能打开页面但聊天报错：`.env` 里 `DEEPSEEK_API_KEY` 没填或填错。
- 公网登录跳回 127.0.0.1：`PUBLIC_ORIGIN` 没改成公网地址。
- 注册不了账号：确认 `.env` 里 `ALLOW_REGISTRATION=true`。
- 管理员测试卡片不出现：运行
  `./scripts/bootstrap-admin.sh admin@shiguang.test`，然后重新登录；该脚本会
  自动写入 `LIFE_DIRECT_MOMENT_TEST_ENABLED/USERNAME/USER_ID/UNLIMITED` 并重建
  `life-core`。
- 一键生图提示“生图 Provider 未配置”：`.env` 里没有 `IMAGE_PROVIDER_API_KEY`。
- 改完代码服务器没变化：确认本地已 `git push`，服务器已 `git pull`，
  且需要时跑过 `build-librechat.sh`。
- 端口访问不通：检查 UFW 和路由器端口转发。
