# P00 项目身份审计

核验时间：2026-11-03T21:27:57.452234+08:00；本阶段结论 PARTIAL，审计与隔离环境已建立。

唯一主项目：`H:\AI For research institute\LifeCompanion-Rebuild`。
Git common-dir：`H:\AI For research institute\LifeCompanion-Rebuild\.git`。
开发工作树：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103`；分支 `feat/rebuild-p00-p07-20261103`；
开始/结束 HEAD 均为 `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`，没有创建提交。
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

# P00 真实能力基线

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
实际 provider：existing Zhipu glm-4.7；本轮基线新聊天 4 次、图像调用 0 次。
聊天链路用时 29.39 秒；未取得完整费用账单，不填造费用/P95。
Android 真机通知 UNKNOWN；完整任务创建/取消/重启、图片文件、IME 和错误恢复未在 P00 验收。

## 修改明细和验收命令

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
