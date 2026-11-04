# LifeCompanion-Rebuild 可移植性与空目录部署审计

审计时间：2026-11-04 21:52（Asia/Hong_Kong）

最终状态：**PASS（本地 release-equivalent clone）/ BLOCKED_REMOTE（GitHub）**

## 结论

项目已能从空目录克隆固定提交并完成初始化、启动和真实功能验证。由于项目
所有者尚未提供授权 GitHub 仓库 URL，且 `WORKSPACE_LOCK.json` 明确
`git_push_allowed=false`，本次使用的是本地 Git 仓库克隆，不是 GitHub clone，
也没有执行 push。

## 来源与目标

| 项目 | 值 |
| --- | --- |
| 源工作树 | `H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103` |
| 分支 | `feat/rebuild-p00-p07-20261103` |
| 验证提交 | `4efe3ccef00520b8d94df22189a78251db55b683` |
| 空目录目标 | `H:\AI For research institute\_release-clone-final-20261104-2128` |
| 克隆来源 | `H:\AI For research institute\LifeCompanion-Rebuild`（本地 Git） |
| 目标 HEAD | `4efe3ccef00520b8d94df22189a78251db55b683` |
| Compose project | `lifecompanion-release-final-20261104d` |

目标目录没有复用源工作树的 `node_modules`、Python 虚拟环境、数据库、媒体、
运行卷、真实 `.env` 或真实密钥。父目录密钥通过独立文件提供。

## 部署结果

以下步骤在隔离目录实际执行并返回成功：

1. 本地 `git clone` 固定提交。
2. Windows bootstrap 创建非敏感配置、固定 LibreChat 基线、应用补丁。
3. `npm ci` 和 LibreChat 前端生产构建。
4. 创建 Python venv 并安装锁定依赖。
5. Compose 配置校验和 Memos 声明式配置校验。
6. 启动 gateway、life-core、LibreChat、Memos。
7. 使用合成隔离账号执行真实浏览器登录、模型聊天和回忆发布。
8. 重启后复核账号、MongoDB 消息、SQLite 事件、Memos 内容与媒体状态。

健康检查：

| 服务 | 地址 | 结果 |
| --- | --- | --- |
| gateway | `http://127.0.0.1:34001/health` | HTTP 200 |
| life-core | `http://127.0.0.1:28030/health` | HTTP 200 |
| LibreChat | `http://127.0.0.1:34080/health` | HTTP 200 |
| Memos | `http://127.0.0.1:35240/healthz` | HTTP 200 |

## 功能与回归证据

- 真实浏览器登录：PASS。
- 真实 DeepSeek 聊天及非空助手回复持久化：PASS。
- 合成消息“今天傍晚我在阳台上给茉莉花浇水，风很凉快。”：PASS。
- 自动事件提取并发布到私有 Memos：PASS，事件
  `evt_231fb6d29e93965c1412ef3c`。
- 所有者可见、对等账号列表为 0、对等账号直接读取返回 404：PASS。
- 重启后健康、登录、MongoDB 消息、SQLite 事件、Memos 回忆和隔离：PASS。
- 后端完整测试：`319 passed, 1 warning`。
- 网关测试：`4 passed`。
- Node 语法检查：PASS。
- PowerShell 5.1 解析：PASS。
- Ubuntu 24.04 `bash -n`：PASS。
- Compose config：PASS。

可核对证据：

- `evidence/final-deploy-drill/health-and-test-summary.txt`
- `evidence/final-deploy-drill/real-chat-flow.json`
- `evidence/final-deploy-drill/realtime-memory-result.json`
- `evidence/final-deploy-drill/restart-persistence-result.json`
- `evidence/final-deploy-drill/chat-desktop-1440.png`

## 依赖与运行门槛

最终演练主机使用 Node.js `22.22.0` 和 npm `10.9.4`。LibreChat 前端安装与
构建实际成功，但 `@librechat/agents@4.0.1` 产生 `EBADENGINE`，其 `engines`
要求 Node.js 24+。因此：

- 受支持部署基线统一为 Node.js 24 LTS+。
- Windows/Ubuntu bootstrap 在 Node 低于 24 时给出明确警告，并提示升级；
  不再把低版本静默视为受支持环境。
- 本轮 Node 22 成功记录保留为历史兼容证据，不据此宣称 Node 22 受支持。

## 密钥与发布安全

云模型密钥只位于项目母目录
`H:\AI For research institute\model_api_keys.env`。空目录部署通过后端读取，
前端 bundle、浏览器存储和报告均不包含密钥值。已知 Key 值对工作树和历史
blob 的精确扫描通过，Gitleaks 历史扫描通过；证据位于
`evidence/maintenance/release-secret-scan-final.json` 和
`evidence/maintenance/gitleaks-final.json`。

## 未完成与限制

- **BLOCKED_REMOTE**：没有授权 GitHub remote，未执行 GitHub clone/push。
- Ubuntu 本轮验证为 Shell 语法和 Compose 配置，不是完整 Ubuntu 运行演练。
- 自动生图后的第二次视觉模型复核仍为 `NOT_TESTED`；真实 Kolors 三例由
  人工核对通过。
- Git clone 不包含真实用户数据库、聊天、Memos 内容、上传媒体或密钥；
  生产数据迁移仍需独立加密备份与恢复流程。

## 解除 GitHub 阻塞所需输入

1. 项目所有者确认目标 GitHub 仓库 URL。
2. 确认仓库可见性和许可证策略。
3. 提供推送授权。
4. 对最终提交重新执行精确 Key 扫描和 Gitleaks。
5. 普通 push 后，从 GitHub 地址重复一次空目录 clone 与启动验证。
