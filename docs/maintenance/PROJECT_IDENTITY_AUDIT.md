# LifeCompanion-Rebuild 项目身份审计

审计时间：2026-11-04 19:20（Asia/Hong_Kong）

最终状态：**PASS**

## 结论

当前操作对象确实是 **LifeCompanion-Rebuild**，不是旧工程
`Silver-economy`、`Silver-economy-research` 或其他研究副本。

项目采用一个 Git 仓库、两个本地工作树：

| 角色 | 实际路径 | 分支 | HEAD |
| --- | --- | --- | --- |
| 根工作树 | `H:\AI For research institute\LifeCompanion-Rebuild` | `main` | `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1` |
| 当前增量工作树 | `H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103` | `feat/rebuild-p00-p07-20261103` | `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1` |

两个工作树共用
`H:\AI For research institute\LifeCompanion-Rebuild\.git`。当前产品代码、
V0.3 回忆任务、Kolors Provider、测试和开发证据位于增量工作树，因此本任务以
该工作树为实际实现基线；根工作树保留较早的 V0.2.1 工作区改动。

工作树身份守卫 `python scripts/verify_rebuild_workspace.py` 返回：

```json
{"status":"PASS","project_id":"LifeCompanion-Rebuild","branch":"feat/rebuild-p00-p07-20261103","head":"e2711c7b87367b39b0e2acdc88f4fb9fde01edf1"}
```

## Git 与远端

- Git 顶层：`H:/AI For research institute/LifeCompanion-Rebuild`
- 当前分支：`feat/rebuild-p00-p07-20261103`
- 最近提交：`e2711c7 feat(portal): add focused Life Companion entry`
- `git remote -v`：无输出，**没有已配置的本项目 GitHub remote**
- 因此 GitHub 上传状态为 `BLOCKED_REMOTE`。没有擅自创建或指向
  `Silver-economy` 仓库。
- 工作区存在大量此前未提交源码、文档、证据和测试。所有改动均视为用户成果，
  未执行 `reset`、`checkout --`、`clean` 或覆盖式恢复。

旧工程 `Silver-economy` 的 remote 为
`https://github.com/2230274247/Silver-economy.git`，该信息不用于当前项目，
也未向该仓库执行任何操作。

## 实际技术栈

| 层 | 实际实现 |
| --- | --- |
| 统一前端 | LibreChat `v0.8.8` React SPA，固定上游 commit `e8f3be08623663d4ad7f7241e693c94469b63bb0` |
| 同源网关 | Node.js `apps/product-portal/server.mjs` |
| 聊天后端 | LibreChat Node/Express 容器与 MongoDB 8.0.20 |
| 搜索 | Meilisearch 1.35.1 |
| 回忆存储 | Memos `26.10.0`，固定 commit `651657e7211901393e2501ae7e3e202c8e56f73a` |
| 业务服务 | Python 3.12 + FastAPI `0.162.0` + SQLite |
| 提醒 | Vikunja `v2.7.1` + ntfy `v2.36.0` |
| 图片生成 | SiliconFlow Kolors Provider，模型 `Kwai-Kolors/Kolors` |
| 媒体存储 | `life-core` 私有文件目录 + SQLite 元数据与 SHA256 |
| 文本模型 | DeepSeek 或智谱，后端服务端调用 |

## 当前运行架构

```text
Browser
  -> product-portal gateway
       -> LibreChat React / API / SSE
       -> life-core FastAPI
            -> SQLite business state
            -> Memos private memory API
            -> DeepSeek / 智谱 text model
            -> SiliconFlow Kolors
            -> private moment-media directory
       -> Vikunja / ntfy reminder services
```

当前隔离验收实例：

- `life-core`: `http://127.0.0.1:8032/health`，HTTP 200
- 网关: `http://127.0.0.1:3031/health`，HTTP 200
- LibreChat: `http://127.0.0.1:3091`
- 本机基线实例：3001、3080、5230、8010 仍健康；未停止或清空其数据

## 启动与依赖来源

- 现有日常启动入口：`scripts/start-lifecompanion.ps1`
- 业务服务入口：`services/life-core/run.ps1`
- 网关入口：`apps/product-portal/run.ps1`
- Compose：`infra/compose.baseline.yaml`、`compose.spa.yaml`、
  `compose.acceptance.yaml`、`compose.reminders.yaml`、`compose.p02.yaml`
- Python 依赖：`services/life-core/requirements.txt`
- 上游 Node 依赖由各独立上游仓库的 lockfile 管理

当前启动脚本仍含绝对路径，并有“服务复用即视为新代码已加载”的风险；这些属于
阶段 4 的可移植性问题，不改变阶段 1 的项目身份结论。

## 代码与功能证据

- 回忆任务与 Provider 位于
  `services/life-core/app/moments.py`、`image_provider.py`、
  `moment_media.py`、`recollection_prompt.py`。
- 回忆 API 和 worker 入口位于 `services/life-core/app/main.py`。
- UI 中“我的回忆 / 时段回忆 / AI生成”证据位于
  `evidence/v03-b2-direct-test/runtime/unlimited-20261104-01/`。
- 真实 Kolors 技术调用证据位于根工作树
  `evidence/v03-b0-kolors/fixed-attempt-02/`。

## 基线测试

正确入口：

```powershell
Set-Location services\life-core
..\..\infra\runtime\p02\venv\Scripts\python.exe -m pytest -q tests
```

结果：**284 passed，1 warning，170.03s**。警告来自上游
`trustcall` 的 LangGraph 弃用导入，不是失败。

网关：

```powershell
node --check apps\product-portal\server.mjs
node --test tests\gateway.test.mjs
```

结果：语法检查通过，**4 passed**。

首次从仓库根目录执行 `pytest services\life-core\tests` 时出现 28 个
`ModuleNotFoundError: app`，原因是错误工作目录，不是业务回归。保留该结果，
正确入口重跑后全部通过。

## 未决身份问题

- `BLOCKED_REMOTE`：没有用户指定的 LifeCompanion GitHub 仓库 URL 和授权。
- 根工作树与 `.work` 工作树都有未提交、未追踪成果；后续只提交明确属于本任务
  的精确路径，不批量吞并未知修改。
