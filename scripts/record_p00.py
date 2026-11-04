"""Assemble the P00 report from this run's evidence, without inheriting old PASS."""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from verify_rebuild_workspace import ROOT, verify

verify(ROOT)
evidence = ROOT / "evidence/p00"
docs = ROOT / "docs/product/p00-p07/P00"
docs.mkdir(parents=True, exist_ok=True)
before = json.loads((evidence / "identity-before.json").read_text(encoding="utf-8"))
after = json.loads((evidence / "identity-after.json").read_text(encoding="utf-8"))
live = json.loads((evidence / "live-baseline.json").read_text(encoding="utf-8"))
browser = json.loads((evidence / "browser/browser-baseline.json").read_text(encoding="utf-8"))
now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
source_equal = before["source_sha256"] == after["source_sha256"]
db_equal = before["existing_databases"][0]["sha256"] == after["existing_databases"][0]["sha256"]
if not source_equal or not db_equal:
    raise SystemExit("UNEXPECTED_SOURCE_OR_ORIGINAL_DATABASE_CHANGE: stop and investigate")

identity = f"""# P00 项目身份审计

核验时间：{now.isoformat()}；本阶段结论 PARTIAL，审计与隔离环境已建立。

唯一主项目：`{before['canonical']['path']}`。
Git common-dir：`{after['workspace']['git_common_dir']}`。
开发工作树：`{ROOT}`；分支 `{after['workspace']['branch']}`；
开始/结束 HEAD 均为 `{after['workspace']['head']}`，没有创建提交。
Rebuild 没有 origin remote，不能擅自关联历史 Silver-economy 远端。
原工作区开始前有 82 条 porcelain 状态记录；原 LibreChat 有独立历史和未提交补丁。
本工作树叠加当前 Rebuild 代码，排除原运行环境、密钥、数据库、历史用户素材和历史证据。

旧 Silver-economy HEAD `093627936776da2a78fce09ef7b174a0793f82f0`，
其 intelligence 工作树共享旧 `.git`，与 Rebuild 不同源。
本轮旧工作树 324 条状态记录，不继承“119 文件”的历史计数。
research 根是仓库集合，无顶层 Git。旧项目 551 个、旧工作树 467 个
被盘点源码/文档的前后 SHA-256 完全一致。此范围不包括所有二进制素材及数据库。
原 Rebuild life-core SQLite 的 SHA-256 及 schema/行数前后不变。

## 真实服务归属

`evidence/p00/container-ownership.json` 记录原容器 Compose labels、镜像、
只含变量名/存在性的配置和实际挂载。原 `lifecompanion-upstream` 与
`lifecompanion-reminders` 的 working_dir 均指向 canonical Rebuild/infra。
初始无关键服务监听、Docker daemon 停止。启动 Docker Desktop 后，其原 restart
策略也恢复了旧项目容器。未向旧服务执行测试或迁移；无法证明该恢复过程没有产生
数据库内部维护写入，因此 ROOT-02 为 PARTIAL，不能把源码哈希等同于所有旧数据不变。

本轮 project `lcr-acceptance-20261103` 使用独立网络、空数据库和运行目录：

| 服务 | 地址 | 权威数据 |
|---|---|---|
| 统一网关 | 127.0.0.1:3031 | 无数据库 |
| LibreChat | 127.0.0.1:3091 | 独立 Mongo / LibreChatAcceptance |
| life-core | 127.0.0.1:8031 | 本工作树 infra/runtime/p00/life-core.sqlite3 |
| Memos | 127.0.0.1:5241 | 本工作树 infra/runtime/p00/memos |
| Vikunja | 127.0.0.1:3461 | 本工作树 infra/runtime/p00/vikunja |
| ntfy | 127.0.0.1:8097 | 独立认证和缓存目录 |

不连接原用户数据库进行验收。新应用 JWT、内部令牌和加密密钥独立生成；
只复用既有已批准的 Zhipu 模型配置，值不进入报告。
"""

capabilities = f"""# P00 真实能力基线

证据等级：本轮 REBUILD_RUNTIME_VERIFIED；不继承历史 PASS。

| 能力 | 分类 | 本轮事实 |
|---|---|---|
| LibreChat/GLM 聊天 | ALREADY_WORKING | 四个新会话真实调用并保存，重读历史成功 |
| 绿色 U盘/雨伞跨会话召回 | ALREADY_WORKING（限定场景） | 两条来源在第三会话同时召回，包含非银色条件 |
| 八账号身份 | ALREADY_WORKING（人工测试开通） | 官方 API 注册、独立 Memos 身份；未证明普通用户全自动开通 |
| 提醒时间 Chip | ALREADY_WORKING（草稿） | 仅缺 event_time，实际返回 08/09/10:00；本阶段未创建正式任务 |
| 账号隔离 | 部分实测 | 四个会话他人不可读，合法格式的草稿越权修改返回 404 |
| 前端 | 部分实测 | Chrome 登录；五视口无横向溢出；四个深链接 HTTP 200；JS pageerror 0 |
| LangMem/Neo4j/Graphiti | NOT_IMPLEMENTED | 当前 requirements 和源码未接入；不把规则检索冒充图谱 |
| LangGraph/APScheduler | NOT_IMPLEMENTED | 当前任务为本服务线程及 Vikunja webhook；没有指定框架接入 |
| 自动回忆 | PRESENT_BUT_UNVERIFIED | 有 moments 表、窗口线程及 provider 路径；未允许生图调用 |
| 搜索/路线/回访/家庭/后台 | 尚未验收 | 进入对应阶段审计，不能依据上游可能具备而声明完成 |

后端 63 passed、网关 2 passed、身份守卫 7 passed，均有本轮原始日志。
它们属于各自测试层，不能相加宣传产品验收通过数。
实际 provider：{live['provider']}；本轮基线新聊天 4 次、图像调用 0 次。
聊天链路用时 {live['elapsed_seconds']} 秒；未取得完整费用账单，不填造费用/P95。
Android 真机通知 UNKNOWN；完整任务创建/取消/重启、图片文件、IME 和错误恢复未在 P00 验收。
"""

chain = """# P00 架构与故障证据

## 已由源码及实际请求互证

1. 浏览器 `:3031` → `apps/product-portal/server.mjs:createGateway`：
   `/api/*` 转发独立 LibreChat `:3091`，`/life-api/*` 白名单转发 core `:8031`。
   浏览器内部令牌头会删除，internal 路由不可经网关公开访问。
2. 聊天 → LibreChat `api/app/clients/BaseClient.js` 与
   `packages/api/src/memory/life.ts`：用户消息入 Mongo 后连接 life-core；
   四会话通过官方聊天/stream/messages API 读回，原件没有写到旧库。
3. `services/life-core/app/auth.py:identity_from_request` 验证 LibreChat JWT，
   `main.py:current_identity` → `store.py:users` 绑定 life_user_id/Memos 用户。
   八个合成账号有八个不同 LibreChat/Memos ID。
4. `memory.py:enqueue/run_one/classify/recall` →
   memory_jobs / memory_items / memory_evidence；来源归属当前用户。
   当前 classify 有规则及 httpx LLM 路径，recall 有字词/双字匹配；
   此事实不等于 LangMem 或图谱已集成。
5. `memos.py:MemosClient.create_private_memo` 使用用户 PAT 和官方 API，
   写前核对 writer/PRIVATE 归属；Memos 不是完整长期记忆实现。
6. `reminder_drafts.py:create/patch/select` → reminder_drafts/submissions；
   `reminders.py:ReminderService` → Vikunja v2；`provisioning.py` → 每用户账号，
   ntfy 使用独立通道。P00 仅证明草稿和隔离拒绝，正式投递仍待 P03。
7. `moments.py:Moments.schedule/select/run_one` → moments 表/图像 BLOB；
   `main.py:moment_work` 为 API 内线程，不是独立 APScheduler。
   当前评分有关键词/规则，未证明结构化模型评分。图像未实测、未伪造。
8. React 路由位于 `products/librechat-custom/client/src/routes/index.tsx`；
   `components/Life/ChatSources.tsx` 与 ReminderCards 使用业务 ID 和来源入口。
   深链接真实返回可访问页面，点击往返和实体详情在 P01 继续实测。

## 本轮故障与恢复

- 首次 pytest 从外层运行缺 PYTHONPATH，出现 11 个收集错误；
  设置本工作树 services/life-core 后 63 passed，没有修改断言。
- 第六个合成账号注册触发上游默认 5 次限流，HTTP 429；
  仅隔离 Compose 设置 REGISTER_MAX=20，随后八账号全部真实创建。
- 第一次 Playwright 缺指定 Chromium 缓存；改用机器已安装 Chrome，
  无下载/安装新浏览器，随后真实浏览器脚本通过。
- 草稿越权测试首次缺 If-Match，返回 422，不能计作权限通过；
  补全合法请求后返回 404，保留首次和复测结果。
- 原项目数据库授权行的历史差异本轮不回滚，不把历史解释当已查明根因。
"""

porting = """# P00 选择性移植矩阵

旧 intelligence source_commit 均为 `093627936776da2a78fce09ef7b174a0793f82f0`
加本地未提交修改。没有继承旧测试成绩，没有复制旧业务源码。

| source_repo/src | license | risk / Rebuild overlap | decision | target / required_test / final_result |
|---|---|---|---|---|
| Silver-economy/.work/intelligence-20261103/services/api/app/intelligence/contracts.py | 原业务源码许可待核实 | 旧 ORM 字段、实体模型不同；Rebuild 有 Candidate | DEFER 原码，参考 schema 约束 | P02；否定/实体消歧/来源；未移植 |
| 同目录 graphiti_native.py | 原业务源码许可待核实；Graphiti 独立许可 | 导入旧 get_settings/ProviderFailure，不能原样复用 | REIMPLEMENT_WITH_FRAMEWORK | P02 正式适配器；无 embedder 不出网；未实现 |
| 同目录 scheduler.py / reminders.py | 原业务源码许可待核实 | 旧业务主库、通知/任务重复 | REJECT 整体移植 | P03 在 Rebuild 原任务 API 上扩展；未复制 |
| 同目录 recollections.py | 原业务源码许可待核实 | 旧回忆域与当前 Moments 重叠 | DEFER，参考评分测试设计 | P04；真事件候选/隐私/幂等；未复制 |
| services/api/tests/test_intelligence_memory.py | 原业务源码许可待核实 | 引用旧数据库夹具 | ADAPT 测试思路，不复制源码 | P02 新写跨会话/公司/修订用例；未实施 |
| services/api/tests/test_intelligence_workflow.py | 原业务源码许可待核实 | 旧 LangGraph 状态与确认策略不同 | ADAPT 测试思路 | P03 重启/恢复/拒绝/重复确认；未实施 |
| 旧 ORM、Vue 整页、Compose、env、数据库、账号/素材 | 不适用 | 跨项目身份和数据风险 | REJECT | 不进入 Rebuild |
| research/repositories 中 LangMem/LangGraph/Graphiti/APScheduler | 逐仓库上游许可 | 有重复克隆；不是 Rebuild 当前安装证据 | DEFER 直接复制 | 从批准版本官方 API/包集成；P02-P03 单独锁版本 |

当前阶段最终移植业务源码文件数：0。安全守卫、隔离环境及验收脚本为本轮 Rebuild 新增。
"""

licenses = """# P00 依赖与许可证基线

本阶段没有升级上游版本。镜像及来源由实际容器 inspect、独立 Git HEAD 与根 LICENSE 核验；
细节见 evidence/p00/container-ownership.json、identity-before.json。

| 组件 | 固定版本/HEAD | 许可证基线 | 作用 |
|---|---|---|---|
| LibreChat | v0.8.8；本地 7c2365cb376b48acb1591e48a6ef91e5c47c78e6 加既有补丁 | MIT，保留 LICENSE | 认证、真实聊天、Mongo 历史、React |
| Memos | 26.10.0 / 651657e7211901393e2501ae7e3e202c8e56f73a | MIT | 私有事件 |
| Vikunja | v2.7.1；镜像 f7dc8428d10a… | AGPL-3.0-or-later，源码提供义务待上线复核 | 正式任务 |
| ntfy | v2.36.0；镜像 fb48c413eb11… | Apache-2.0 / GPLv2，按实际分发复核 | 通知 |
| Mongo | 8.0.20 | SSPL，部署分发门禁需独立复核 | 聊天主库 |
| FastAPI/uvicorn/httpx/pytest | 原 requirements 锁定 | 原包 metadata/上游许可，待 P07 全量扫描 | API 与测试 |
| LangMem/Neo4j/LangGraph/APScheduler/Graphiti | 当前未集成 | 不能拿旧仓库安装状态充当本项目证据 | P02-P03 后续实际锁定和调用 |

此表不是法律合规结论，也不是完整 CVE 审计。没有新付费服务、公开部署或上游推送。
"""

for filename, content in {
    "PROJECT_IDENTITY_AUDIT.md": identity,
    "BASELINE_CAPABILITIES.md": capabilities,
    "ROOT_CAUSE_EVIDENCE.md": chain,
    "SELECTIVE_PORTING_MATRIX.md": porting,
    "DEPENDENCY_LICENSE_MATRIX.md": licenses,
    "UPSTREAM_BASELINE.md": "# 只读上游基线\n\n" + licenses,
}.items():
    (docs / filename).write_text(content, encoding="utf-8")

log = identity + "\n" + capabilities + "\n" + """## 修改明细和验收命令

新增：WORKSPACE_LOCK.json；scripts/verify_rebuild_workspace.py/.ps1；
audit_rebuild.py、acceptance_environment.py、acceptance_p00.py、acceptance_browser.cjs、
record_p00.py；infra/compose.acceptance.yaml；tests/test_workspace_guard.py；
WORK_LOG.md、NEXT_ACTION.md、本阶段报告/证据。原主工作区业务源码未修改。
原 Rebuild 未提交改动在隔离树中保留为基线，不能把全部 git diff 归因本轮。

| 命令 | 实际结果 | 证据 |
|---|---|---|
| verify_rebuild_workspace.py | 正确目标退出0，错误目标退出2 | guard-tests.txt / 7 passed |
| pytest -q -p no:cacheprovider services/life-core/tests | 退出0；63 passed，1 warning | pytest-baseline.txt |
| node --test tests/gateway.test.mjs | 退出0；2 passed | gateway-baseline.txt |
| docker compose … config --quiet / up -d --pull never | 退出0；独立五服务启动 | compose-start.txt |
| acceptance_p00.py setup | 首次429；调整隔离注册额度后退出0 | account-setup*.txt |
| acceptance_p00.py run | 退出0；四真实云端会话；基线总体 PARTIAL | live-baseline.json |
| node scripts/acceptance_browser.cjs | 首次缺缓存；已安装Chrome复测退出0 | browser/browser-baseline.json |
| audit_rebuild.py before/after | 退出0；1018个源码/文档一致；原core DB一致 | identity-before/after.json |

## 尚未通过与下一阶段

ROOT-02 完整旧数据库不变证明 PARTIAL；未审计全部历史素材。P00 不承诺正式提醒、
图片、完整关系图谱、家庭连接或手机通知已交付。P01 将完成业务详情点击、
路由往返、输入/Markdown/故障恢复与身份回归；之后 P02-P07 按顺序实施。
不需要把风险阻断扩大为停止其他可安全完成的工作。
"""
(docs / "P00_STAGE_LOG.md").write_text(log, encoding="utf-8")
logname = now.strftime("%Y-%m-%d_%H-%M") + "_P00项目身份锁定与真实基线_开发验收.md"
(ROOT / "docs/development-log" / logname).write_text(log, encoding="utf-8")
index = ROOT / "docs/development-log/README.md"
with index.open("a", encoding="utf-8") as file:
    file.write(f"\n## P00-P07 持续开发\n\n- {now.date()} "
               f"[P00 项目身份与真实基线]({logname})：PARTIAL；独立服务及基线实测，"
               "旧数据库完整不变证明未取得。\n")
matrix = (ROOT / "docs/task-pack/11_跨阶段总验收矩阵.md").read_text(encoding="utf-8")
rows = []
for line in matrix.splitlines():
    if line.startswith("| ROOT-"):
        cells = line.split("|")
        identifier = cells[1].strip()
        cells[5] = " PARTIAL " if identifier == "ROOT-02" else " PASS "
        cells[6] = " P00/P00_STAGE_LOG.md + ../../../../evidence/p00/ "
        line = "|".join(cells)
    rows.append(line)
(docs.parent / "11_跨阶段总验收矩阵.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
print(json.dumps({"stage": "P00", "status": "PARTIAL", "stage_log": str(docs / "P00_STAGE_LOG.md"),
                  "source_sha_unchanged": source_equal, "original_core_db_unchanged": db_equal}))
