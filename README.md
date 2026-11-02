# Life Companion Rebuild

基于真实 LibreChat 与 Memos 源码的“AI 生活伙伴 + 人生回忆录”纵向切片。
当前版本面向 2026-11-04 本地桌面演示，保留两个上游项目各自的 Git 历史、
许可证与核心功能，没有用静态页面冒充上游应用。

## 已跑通的能力

- LibreChat `v0.8.8` 运行于 http://localhost:3080
- Memos `26.10.0` 运行于 http://localhost:5230
- `life-core` 运行于 http://127.0.0.1:8010
- 统一产品入口运行于 http://127.0.0.1:3001
- DeepSeek 自定义端点 `deepseek-flash` 已完成真实中文对话与刷新持久化
- 新聊天经服务端身份校验、事件抽取、授权检查后写入私有 Memos
- 相同来源消息重试不会创建第二条事件或第二条 Memo

当前仍未完成的内容见 `docs/BLOCKERS.md`。LibreChat 与 Memos 目前分别登录，
没有实现 SSO；本周没有交付 Android APK 或真实图片生成。

## 目录

```text
apps/product-portal/       自有统一入口
products/librechat-custom/ 真实 LibreChat 克隆与本地补丁
products/memos-custom/     真实 Memos 克隆，无本地补丁
services/life-core/        事件、授权、幂等、Memos 适配
infra/                     Compose override 与本地运行状态
docs/                      上游、架构、运行、验收和阻断说明
evidence/                  已验证截图与脱敏证据
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

## 启动

终端 1：启动 LibreChat、Memos 及其基础依赖。

```powershell
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" up -d
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

打开 http://127.0.0.1:3001 进入统一入口，再进入 LibreChat 或 Memos。

## 测试

```powershell
Push-Location services\life-core
..\..\services\life-core\.venv\Scripts\python.exe -m pytest -q tests
Pop-Location

node --check apps\product-portal\server.mjs
node --check apps\product-portal\portal.js
node --check products\librechat-custom\api\app\clients\BaseClient.js
Set-Location "H:\AI For research institute\LifeCompanion-Rebuild\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" config --quiet
```

## 文档索引

- `docs/UPSTREAM_MANIFEST.md`：上游 URL、tag、commit、许可证和运行镜像
- `docs/UPSTREAM_BASELINE.md`：原版启动与基线证据
- `docs/UPSTREAM_DIFF.md`：相对上游的真实改动
- `docs/ARCHITECTURE.md`：组件、数据流、权限边界和 API
- `docs/RUNBOOK.md`：启动、停止、排障与备份
- `docs/ANDROID_PLAN.md`：Android 路线和剩余风险
- `docs/ACCEPTANCE_2026-11-04.md`：逐项验收结果
- `docs/BLOCKERS.md`：未完成项和阻断原因
- `tests/RESULTS.md`：本轮自动化测试摘要

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

所有账号、测试映射和完整日志均位于被忽略的 `infra/runtime/` 或容器内部；
不应把密钥、访问令牌或真实用户数据加入 Git 或演示材料。

