# Life Companion Rebuild

**2026-11-02 V0.2.1 本机增量：总体 PARTIAL。** 已加入授权长期事实召回、
同主题生活事件归并，以及真实 Vikunja + ntfy 单次提醒和 React 提醒页。
两个合成账号的提醒/通知隔离已实测；普通用户自动开通、固定周期提醒、系统后台/手机推送、
生图和 APK 尚未交付。详见 [本轮证据](evidence/v02-memory-reminders/README.md)
与 [实际架构边界](docs/architecture/V02_1_MEMORY_REMINDERS.md)。
下文保留此前 V0.2 基线说明。

基于真实 LibreChat 与 Memos 源码的“AI 生活伙伴 + 人生回忆录”纵向切片。
V0.2 将 LibreChat React 前端作为统一聊天与回忆 SPA，面向 2026-11-04 本地演示，
保留两个上游项目各自的 Git 历史、
许可证与核心功能，没有用静态页面冒充上游应用。

## 已跑通的能力

- LibreChat `v0.8.8` 运行于 http://localhost:3080
- Memos `26.10.0` 运行于 http://localhost:5230
- `life-core` 运行于 http://127.0.0.1:8010
- 统一 SPA 与同源网关运行于 http://127.0.0.1:3001
- DeepSeek 自定义端点 `deepseek-flash` 已完成真实中文对话与刷新持久化
- 新聊天经服务端身份校验、事件抽取、授权检查后写入私有 Memos
- 相同来源消息重试不会创建第二条事件或第二条 Memo

用户在统一入口登录 LibreChat 后即可访问聊天和回忆；回忆页通过 life-core 读取
真实私有 Memos 内容，不再要求用户登录 Memos 原生页面。当前仍为显式单用户映射，
没有多用户自助开户。本周没有交付 Android APK 或真实图片生成。
实际验收与限制见 `docs/development-log/README.md`、`docs/BLOCKERS.md`。

## 目录

```text
apps/product-portal/       同源 HTTP/SSE 网关
apps/otis-pet/             Electron 桌宠实验（可选；正式形态是聊天页内 Otis）
products/librechat-custom/ 真实 LibreChat 克隆与本地补丁
products/memos-custom/     真实 Memos 克隆，无本地补丁
services/life-core/        事件、授权、幂等、Memos 适配
infra/                     Compose override 与本地运行状态
docs/                      上游、架构、运行、验收和阻断说明
evidence/                  已验证截图与脱敏证据
patches/                   独立上游仓库的可复现本地补丁
tests/                     测试与结果索引
fixtures/                  仅包含合成测试数据说明
```

## 首次准备

以下命令均在 PowerShell 中执行，项目根目录为
`H:\AI For research institute\LifeCompanion-Rebuild`。

1. 克隆固定版本的上游源码（首次搭建时）：

```powershell
git clone --branch v0.8.8 --single-branch https://github.com/LibreChat-AI/LibreChat.git products\librechat-custom
git clone --branch 26.10.0 --single-branch https://github.com/usememos/memos.git products\memos-custom
git -C products\librechat-custom checkout -b lifecompanion-baseline
git -C products\memos-custom checkout -b lifecompanion-baseline
```

2. 创建本地密钥文件。`infra\.env` 和
   `products\librechat-custom\.env` 已被 Git 忽略。

```powershell
Copy-Item .env.example infra\.env
Copy-Item products\librechat-custom\.env.example products\librechat-custom\.env
```

至少填写：

- `LIFE_INTERNAL_TOKEN`：LibreChat 与 `life-core` 之间的服务端令牌
- `MEMOS_API_TOKEN`：Memos 个人访问令牌
- `DEEPSEEK_API_KEY`：DeepSeek 服务端 Key
- LibreChat 官方模板要求的 JWT 密钥

3. 创建 `life-core` 独立虚拟环境：

```powershell
python -m venv services\life-core\.venv
services\life-core\.venv\Scripts\python.exe -m pip install -r services\life-core\requirements.txt
```

如果 PyPI 直连失败，可在确认镜像可信后显式使用镜像，例如：

```powershell
services\life-core\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r services\life-core\requirements.txt
```

## V0.2 前端构建

已有本地补丁的仓库无需再次应用。新克隆后按 `patches/README.md` 恢复 V0.2 改动。
依赖使用现有 lockfile，推荐上游要求的 Node 24+：

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\products\librechat-custom"
npm ci --ignore-scripts --no-audit --no-fund
npm run frontend
```

## 启动

桌面双击 `启动拾光.cmd` 可一键启动容器、`life-core` 和统一入口，并打开
http://127.0.0.1:3001。脚本会复用已在运行的服务，不删除容器或数据；
本机服务日志保存到 `infra\runtime\launcher-*.log`。

临时公网演示可双击桌面 `拾光公网启动.cmd`：先启动本机服务，再启动独立的
cpolar HTTPS 隧道，显示并打开公网地址。重复执行会复用健康的现有隧道；
关闭启动窗口后继续运行，电脑需保持开机、联网且不休眠。
最新地址保存在 `infra\runtime\public\public-url.txt`，隧道重新建立后地址可能变化。
双击桌面 `停止拾光公网.cmd` 仅关闭拾光公网隧道，本机服务继续运行。
隧道程序与凭据位于已忽略的 `infra\runtime\public\`，不提交到仓库；
计划任务 `ShiguangPublicTunnel` 没有开机或登录触发器。
临时演示管理员由操作者单独发放，账号密码不得写入代码、Git 或公开文档；
公网演示结束后应停止隧道并更换密码。

终端 1：启动 LibreChat、Memos 及其基础依赖。

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" -f "compose.spa.yaml" up -d
```

终端 2：启动业务服务。

```powershell
.\services\life-core\run.ps1 -Python "H:\AI For research institute\LifeCompanion-Rebuild\services\life-core\.venv\Scripts\python.exe"
```

终端 3：启动统一入口。

```powershell
.\apps\product-portal\run.ps1 -Port 3001
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-WebRequest http://127.0.0.1:3001/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:3080/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:5230/healthz -UseBasicParsing
```

打开 http://127.0.0.1:3001 进入统一应用，聊天路由为 `/c/new`，回忆为 `/memories`。
3080 和 5230 保留为本机维护端口，普通用户无需访问。
每次重新构建前端后执行同一 Compose 配置的 `restart librechat`，
使 Express 重新读取入口 HTML；构建失败时不要重启加载不完整产物。

## 测试

```powershell
Push-Location services\life-core
..\..\services\life-core\.venv\Scripts\python.exe -m pytest -q tests
Pop-Location

node --check apps\product-portal\server.mjs
node --test tests\gateway.test.mjs
node --check apps\product-portal\portal.js
node --check products\librechat-custom\api\app\clients\BaseClient.js
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" config --quiet
```

## 文档索引

- `docs/development/GIT_WORKTREE_POLICY.md`：永久 Git、Worktree、自动提交与安全边界规范
- `docs/UPSTREAM_MANIFEST.md`：上游 URL、tag、commit、许可证和运行镜像
- `docs/UPSTREAM_BASELINE.md`：原版启动与基线证据
- `docs/UPSTREAM_DIFF.md`：相对上游的真实改动
- `docs/ARCHITECTURE.md`：组件、数据流、权限边界和 API
- `docs/RUNBOOK.md`：启动、停止、排障与备份
- `docs/ANDROID_PLAN.md`：Android 路线和剩余风险
- `docs/ACCEPTANCE_2026-11-04.md`：V0.1 历史演示准备验收（2026-11-02 为 11 月 4 日准备）
- `docs/BLOCKERS.md`：未完成项和阻断原因
- `docs/development-log/README.md`：每次开发的独立验收日志
- `docs/DEVELOPMENT_LOG_POLICY.md`：永久日志制度
- `docs/architecture/README.md`、`docs/product/README.md`、`docs/design/README.md`：长期文档索引
- `tests/RESULTS.md`：本轮自动化测试摘要

## 工程治理入口

开始任何开发、合并或整理任务前，先执行只读检查：

```powershell
git status --short --branch
git worktree list --porcelain
git remote -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/inspect-workspace.ps1
```

阶段提交必须显式列出本任务文件，禁止全量暂存：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/checkpoint.ps1 `
  -Message "feat(collab): describe the verified change" `
  -Path "path/to/source", "path/to/test"
```

Worktree 审查和治理回归测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/worktree-audit.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/git-governance.ps1
```

完整规则见 `docs/development/GIT_WORKTREE_POLICY.md`。

## 证据

- `evidence/baseline-librechat.png`
- `evidence/baseline-memos.png`
- `evidence/portal-1440x900.png`
- `evidence/portal-1920x1080.png`
- `evidence/portal-390x844.png`
- `evidence/vertical-slice-librechat.png`
- `evidence/vertical-slice-memos.png`
- `evidence/vertical-slice-verification.json`
- `evidence/deepseek-model-check.txt`
- `evidence/v02-tests/README.md`：V0.2 测试、构建、补丁和最终截图索引
- `evidence/v02-live-verification.json`：V0.2 真实聊天到私有回忆链路

所有账号、测试映射和完整日志均位于被忽略的 `infra/runtime/` 或容器内部；
不应把密钥、访问令牌或真实用户数据加入 Git 或演示材料。

