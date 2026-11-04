# LifeCompanion-Rebuild 冗余文件清理审计

审计时间：2026-11-04 19:20（Asia/Hong_Kong）

最终状态：**PASS**

## 备份

修改前已建立项目外部备份：

`H:\AI For research institute\_backups\LifeCompanion-Rebuild-five-task-20261104-192000`

- 文件数：1,160
- 大小：35,614,502 bytes（约 34 MB）
- 内容：源码、测试、文档、脚本、补丁、证据和当前 Git 差异
- 清单：备份根目录 `SHA256SUMS.tsv`、`BACKUP_INFO.json`、
  `tracked-working-tree.patch`、`git-status.txt`
- 未复制：真实数据库、运行卷、用户媒体、真实 `.env`、密钥、
  `node_modules`、虚拟环境

## 清理前盘点

| 区域 | 文件数 | Git 跟踪数 | 大小 MiB | 处理 |
| --- | ---: | ---: | ---: | --- |
| `apps` | 7 | 7 | 0.03 | 保留，正式网关源码 |
| `docs` | 107 | 9 | 0.69 | 保留，产品与开发记录 |
| `evidence` | 1,040 | 12 | 55.32 | 保留，真实测试、失败和 UI 证据 |
| `fixtures` | 3 | 1 | 0.02 | 保留，合成测试夹具 |
| `infra` | 1,550 | 1 | 758.84 | 仅保留；绝大多数为持久运行卷 |
| `logs` | 2 | 0 | 0.001 | 保留为审计日志，停止新增普通日志入库 |
| `patches` | 7 | 0 | 0.96 | 保留，用于重建上游修改 |
| `products` | 7,949 | 0 | 204.45 | 保留，运行时依赖的固定上游源码 |
| `scripts` | 57 | 0 | 0.41 | 保留，测试与验收入口 |
| `services` | 134 | 11 | 2.27 | 保留，正式业务源码与测试 |
| `tests` | 37 | 5 | 0.24 | 保留，不得为减少报错删除 |

清理前业务区域合计约 **1,023.22 MiB**。

其中 `infra/runtime` 约占 964 MiB：

- `p02`：728.12 MiB，20,069 文件，隔离虚拟环境、Neo4j、验收数据
- `p00`：232.43 MiB，1,341 文件，Mongo/Memos/上传/通知验收数据
- `p04`：3.47 MiB
- `p05`：0.35 MiB

这些目录包含数据库、Memos 数据、测试账户、持久队列和失败恢复证据，按任务要求
保留，未删除或迁移。

## 已清理项

仅删除可再生的 Python/测试缓存：

| 路径 | 说明 |
| --- | --- |
| `.pytest_cache` | pytest 缓存 |
| `scripts\__pycache__` | Python 字节码 |
| `services\life-core\.pytest_cache` | pytest 缓存 |
| `services\life-core\app\__pycache__` | Python 字节码 |
| `services\life-core\tests\__pycache__` | Python 字节码 |
| `tests\__pycache__` | Python 字节码 |
| `tests\v03-b2-e2e\__pycache__` | Python 字节码 |

清理结果：

- 删除目标：7 个目录
- 删除文件：87 个
- 释放：1,835,186 bytes（约 1.75 MiB）
- 清理后业务区域约 **1,021.48 MiB**
- 清理清单：
  `evidence/maintenance/safe-cache-cleanup-manifest.json`
- 清单包含每个文件的原始相对路径、大小、SHA256、删除理由和外部备份位置

删除前先用 `Resolve-Path` 验证所有目标都位于当前工作树内；删除后复核 7 个目标
均不存在。没有使用 `git clean`、递归通配删除或其他跨工作区删除命令。

## Git 跟踪检查

扫描到的已跟踪图片都在 `evidence/`，属于 UI/上游基线验收证据，不是用户上传或
生成图片。未发现已跟踪的 `.env`、数据库、日志、`__pycache__`、`node_modules`
或虚拟环境。

`.gitignore` 已补充：

- `model_api_keys.env` 与 `model_api_keys.env.*`
- `.ruff_cache/`
- `.coverage`、`coverage/`
- `logs/`

原有 `.env`、`infra/runtime/`、`services/life-core/data/`、
`infra/volumes/`、`products/*-custom/` 等保护规则保留。

## 明确未清理

- 正式测试、fixtures、源码、迁移和部署脚本全部保留。
- 用户/验收数据库、Memos 数据、上传内容、生成媒体和持久卷全部保留。
- 失败日志、错误截图和真实调用证据全部保留，作为验收审计依据。
- 上游固定版本源码保留；不得为了缩小目录而删除后继续把当前运行环境当成可从
  GitHub 克隆部署。
- `node_modules`、`.venv` 和各上游构建产物保留。它们是可再生但当前运行需要的
  大目录；另可由部署文档中的脚本重建。

## 清理后回归

将在阶段 2 完成后执行：

```powershell
Set-Location services\life-core
..\..\infra\runtime\p02\venv\Scripts\python.exe -m pytest -q tests
```

并复核 8032 与 3031 健康检查。阶段完成记录追加到下方“回归结果”。

## 回归结果

清理后执行：

- `services/life-core` 完整测试：**284 passed, 1 warning, 191.13s**
- `node --check apps/product-portal/server.mjs`：PASS
- `node --test tests/gateway.test.mjs`：**4 passed**
- `life-core` 8032 与网关 3031 健康检查：HTTP 200
- LibreChat 3091 健康检查：连接被拒绝
- Memos 5241 健康检查：HTTP 200

3091 是当前隔离验收 Compose 中未启动的 LibreChat 端口，不是缓存清理造成的
回归；阶段 4 会重新核验 Compose 服务名、端口和实际容器状态。
