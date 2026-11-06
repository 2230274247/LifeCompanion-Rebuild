# LifeCompanion-Rebuild 当前开发进度与遗留问题审计报告

审计日期：2026-11-04，Asia/Hong_Kong。最新检查时间以
[`chat-delivery-audit-r2.json`](../../evidence/p05/chat-delivery-audit-r2.json)
及各附件的 `checked_at` 为准。总体状态：**PARTIAL**。
人工验收点：**PAUSED_FOR_USER_REVIEW**。

## 1. 结论与本轮边界

本轮仅完成已经开始的 P05 天气查询收尾、交付检查、历史证据盘点和暂停归档。
没有继续开发路线、搜索、语音、主动回访、P06 或 P07。
原 P00～P07 总目标保留，未经用户下一次明确授权不得自动恢复。

天气已取得真实公开 Provider、实际编译原生桥接、真实 Core/SQLite、
认证 LibreChat 消息读取及 1440/390px 浏览器证据。
地点选择、结果、来源时间、刷新保留、清除后不恢复通过；
完整 Core 回归 167 项通过。这些证明天气增量已测路径，不代表整个 P05 完成。

天气验收使用合成用户原话及明确标识为非模型生成的助手夹具，
实际执行持久消息后的业务桥接，**未发送新的模型生成聊天轮次**。
因此“用户发送→DeepSeek→工具→回复”完整聊天仍未验收。
常用隔离服务已加载代码，但天气 Provider 默认关闭、预算默认 0；
真实 Provider 验收在独立临时服务完成，不能声称生产天气已启用。

## 2. 项目身份、Git 与未提交成果

| 项目 | 实际值 |
| --- | --- |
| 唯一主项目 | `H:\AI For research institute\LifeCompanion-Rebuild` |
| Git common-dir | `H:\AI For research institute\LifeCompanion-Rebuild\.git` |
| 实际开发工作树 | `H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103` |
| 当前分支 | `feat/rebuild-p00-p07-20261103` |
| 根 HEAD | `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1` |
| canonical 工作树 | `main`，HEAD 同上；本轮未合并 |
| 嵌套 LibreChat | 当前工作树下 `products/librechat-custom`，独立仓库 |
| 嵌套分支 / HEAD | `feat/rebuild-p00-p07-20261103` / `7c2365cb376b48acb1591e48a6ef91e5c47c78e6` |
| 累计补丁基点 | `e8f3be08623663d4ad7f7241e693c94469b63bb0`，与嵌套 HEAD 不同 |
| 本轮提交 / Push / 合并 / 生产部署 | 均未执行 |

逐路径未提交清单、worktree 列表及 diff 统计见
[`pause-git-status.json`](../../evidence/p05/pause-git-status.json)。
根仓库有数百条继承修改/未跟踪记录，包含大量文档、测试和证据；
嵌套 LibreChat 为 63 条修改/新增。精确数量以最终快照为准。
全量 dirty 不能归因天气增量，根仓库统计也不能替代嵌套源码清单。
本轮未强制重置、清库、删除成果或改动真实索引。

天气增量的 18 份业务/测试/脚本源码及 SHA-256 见 r2 审计。
主要入口为 `services/life-core/app/tool_chat.py`、`main.py`、
`apps/product-portal/server.mjs`，以及嵌套的
`packages/api/src/memory/life.ts`、`client/src/components/Life/ToolCards.tsx`。
本次另加只读审计脚本、正式报告与日志，不增加产品业务功能。

最终累计补丁为
`patches/librechat-v0.8.8-rebuild-p00-p05-weather-chat-r2-20261104.patch`，
63 文件、224,547 字节，SHA-256：
`52ef08fcbd0a2926ca884f37ab25f43e93b941a593af3691a93c3bfdd38d03d7`。
临时索引应用检查通过，真实索引未改；包含继承 P00～P05 差异，不是天气专属。
该补丁不是全项目备份，根源码与 ignored 运行数据库仍须保留工作树。
见 [`补丁证据`](../../evidence/p05/chat-upstream-patch-delivery-r2.json)。

旧 Silver-economy 仅只读参考，本次收尾未修改其代码或访问其数据库。
历史 P00 已核对限定旧源码 SHA；但 Docker 曾按既有策略恢复旧容器，
无法倒推证明旧数据库没有内部维护写入，ROOT-02 保持 PARTIAL。

## 3. 服务归属、数据库与安全暂停

| 服务 | 地址 | 权威数据 / 归属 |
| --- | --- | --- |
| 统一网关 | `127.0.0.1:3031` | 当前工作树 Node，无业务数据库 |
| LibreChat | `127.0.0.1:3091` | Compose `lcr-acceptance-20261103`，独立 Mongo `LibreChatAcceptance` |
| life-core | `127.0.0.1:8031` | 当前工作树 `infra/runtime/p00/life-core.sqlite3` |
| Memos | `127.0.0.1:5241` | `infra/runtime/p00/memos` |
| Vikunja | `127.0.0.1:3461` | `infra/runtime/p00/vikunja` |
| ntfy | `127.0.0.1:8097` | `infra/runtime/p00/ntfy-auth`、`ntfy-cache` |
| Neo4j | `127.0.0.1:7475` / `7688` | Compose `lcr-p02-20261103`，`infra/runtime/p02/neo4j` |
| 天气验收库 | 非常用 Core 库 | `infra/runtime/p05/tools-acceptance.sqlite3`，累计账本保留 |

本次新鲜烟测：Core health 200、网关 health 200、LibreChat login 200，
正确 `/life-api/api/v1/tool-chats` 无认证 401。
这些只证明存活与认证，不替代所有历史业务场景重跑。
Compose labels、挂载、监听 PID 与进程检查保存在
[`pause-services.json`](../../evidence/p05/pause-services.json)。

实际安全检查结果：

- 天气库只读 `PRAGMA quick_check=ok`，运行中工具执行 0。
- 唯一天气交互 cancelled，data 与已删除工具 result 不残留正文。
- 网络账本仍为 6；P05 记忆提取/评分账本均为 0。
- 无残留 P05、pytest、Playwright、Lighthouse、临时 Mongo 测试进程；
  性能隔离端口 3098 不再监听；稳定开发服务保留运行。
- 没有半途迁移、清库、预算重置或未结束的天气数据库操作。
  WAL/SHM 为正常运行文件，保留原状。
- 本次暂停的是后续开发；既有服务保留原后台机制。
  不将进程快照解释为所有后台能力永久关闭，或常驻提醒调度已验收。

## 4. 天气收尾实际验收

| 对象 | 结果 | 证据 / 边界 |
| --- | --- | --- |
| 地点歧义处理 | PASS | 真实服务返回多个 Shanghai，明确选择中国上海，不自动取首项 |
| 实际天气卡 | PASS | 1440/390px，数值、来源 URL、查询时间及模型估计说明 |
| 刷新/清除 | PASS | 刷新保留；清除后再次刷新不恢复，额度行保留 |
| 原生业务桥接 | PASS / 有边界 | 真实持久来源经认证HTTP核验，容器执行编译桥接；新模型聊天未验 |
| Core 回归 | PASS | `chat-backend-regression.txt`：167 passed，1项上游弃用warning |
| 天气/提醒前端 | PASS | `chat-frontend-tests.txt`：9项组件回归，不当作真实Provider证据 |
| 提醒优先级 | PASS | “提醒我查上海天气”先复现误路由，修复后最终桥接7项通过 |
| 网关/日志安全 | PASS | `chat-gateway-and-log-tests.txt`：网关3、异常脱敏2通过 |
| 类型/构建/新增模块lint | PASS | API/data-provider/client对应日志，尾审后API再次验证 |
| 旧ReminderCards全文件lint | FAIL / 既有 | 开发前快照同样存在`no-nested-ternary`，位于本次修改行外 |
| 完整性能门禁 | PARTIAL | 最近测量NO_NAVSTART，未完成三轮LCP/CLS/TBT |
| 敏感信息扫描 | PASS / 限定范围 | 天气源码、P05证据/文档、补丁、性能输出无已知实际密钥/JWT匹配 |
| 完整模型聊天/故障UI | NOT TESTED | 未发送新生成轮次；日期、实体IME、错误/限流浏览器覆盖不足 |

成功证据：
[`chat-live.json`](../../evidence/p05/chat-7d8e052b61534996/chat-live.json)、
[`ui-after.json`](../../evidence/p05/chat-7d8e052b61534996/ui-after.json)、
[`截图目录`](../../evidence/p05/chat-7d8e052b61534996/)。
修改前双视口、首次真实地点查询后的网关404与失败截图在
[`失败目录`](../../evidence/p05/chat-76f66fdb58724835/)。
资源不匹配、容器启动窗口、Windows模块加载失败记录均保留。

Lighthouse 子进程错误曾把一次性测试 Cookie/JWT 写入生成日志。
已停止其测试进程树，脱敏生成日志/报告，修复输出仅保留安全退出码；
新增两项回归通过、当前限定扫描无原令牌。JWT即时撤销仍属历史缺口，
未把日志修复或被中断测量当作性能通过。

天气成功后依验收步骤主动清除正文，当前DB不再存已清除Provider结果；
数值展示以截图复核，不为重新截图再次调用。
验证命令详见 [P05_E2E.md](p00-p07/P05/P05_E2E.md)；
其中 Provider 命令是历史记录，预算耗尽后不可直接重跑。

## 5. P00～P05 全部状态盘点

以下来自 Rebuild 历史实际证据与当前代码盘点，本次没有重跑全部历史场景。
PASS 仅针对已测场景；NOT_RUN为未执行，UNVERIFIED为规定规模/人工复核未满足。
逐ID、场景、状态及证据见
[`pause-stage-inventory.json`](../../evidence/p05/pause-stage-inventory.json)和原总矩阵。

| 阶段 | PASS | PARTIAL | BLOCKED | UNVERIFIED | NOT_RUN | 整体 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| P00 | 5 | 1 | 0 | 0 | 0 | PARTIAL |
| P01 | 4 | 3 | 1 | 0 | 0 | PARTIAL |
| P02 | 2 | 5 | 1 | 0 | 0 | PARTIAL |
| P03 | 2 | 9 | 0 | 1 | 0 | PARTIAL |
| P04 | 1 | 7 | 1 | 1 | 0 | PARTIAL |
| P05 | 0 | 3 | 2 | 0 | 4 | PARTIAL |
| 合计 | 14 | 28 | 5 | 2 | 4 | 53项 |

### P00 项目身份

ROOT-01/03/04/05/06 PASS：身份、架构链路、错误目录守卫、
选择性移植清单和真实基线。ROOT-02 PARTIAL：限定旧源码哈希不变有证据，
旧数据库全过程不变证明缺失。
证据：[P00阶段记录](p00-p07/P00/P00_STAGE_LOG.md)及 `evidence/p00/`。

### P01 聊天、路由与身份

CHAT-01、NAV-01/02/04 PASS：真实云端聊天持久化/刷新、
提醒与记忆详情及SPA切换。CHAT-02、AUTH-01、UX-01 PARTIAL：
真实429/超时、自助跨服务开通、注销/刷新/撤权、实体IME待验。
NAV-03 BLOCKED：未授权图像资产，图片详情真实性不可验。
证据：[P01阶段记录](p00-p07/P01/P01_STAGE_LOG.md)、
`evidence/p01/enter-real-chat-mongo.txt`、`identity-e2e-final.txt`、
`drill/ui-drill.json`。历史使用智谱；当前保持DeepSeek，不重写历史。

### P02 长期记忆

MEM-04/05 PASS：真实DeepSeek/LangMem六条事实、12天人物/公司时序、
两公司、就职/邀请、乱序、重放与Core重启。
MEM-01/02/03/06/07 PARTIAL：后端跨会话召回、限定词、纠错、
来源API与部分隔离/撤回已验；用户聊天问答/来源点击、全链路删除、
完整跨账号矩阵和泛化事实更新未验。MEM-08 BLOCKED：无Embedding，
Graphiti原生检索不可用。100事实+100检索评测未完成。
证据：[P02阶段记录](p00-p07/P02/P02_STAGE_LOG.md)、
`evidence/p02/live-acceptance.json`、
`relationships-97b5ef4146644c32.json`。

### P03 智能提醒

REM-10/11 PASS：真实ntfy accepted、退避恢复/独立调度重启和九项任务权限；
设备实际送达仍UNKNOWN。REM-01～09全部PARTIAL：
持久LangGraph interrupt/resume、Vikunja创建/改期/取消、桌面/手机chips、
取消刷新重登、并发确认不重复、unknown跨重启恢复、
11负向+2正向真实HTTP有证据。
真实发送聊天起点、完整日期Chip UI、同名/第三人/拒绝语言矩阵、
跨年时区解析、长期离线、多进程投递竞态、常驻scheduler部署不足。
REM-12 UNVERIFIED：缺200条人工复核意图评测。
证据：[P03阶段记录](p00-p07/P03/P03_STAGE_LOG.md)、
`evidence/p03/business-workflow-a27b9a639da042f9.json`、
`business-ui-995bd011bc444bc0/`、`permissions-live.json`、
`delivery-recovery-0f6f567301144310.json`、`intent-guard-live-c35a53792bc046b9.json`。

### P04 自动回忆与生图

MOM-01 PASS：真实DeepSeek八维评分、3候选/1入选、精确原话与拒绝理由。
MOM-02/03/04/06/07/08/09 PARTIAL：无内容拒绝、未授权拒绝、
撤权清空、真实时钟后台窗、文字Memos、桌面/手机来源点击、
预算与重启不重发已验。缺默认早中晚跨日/DST/长期运行、
完整无内容混淆集、真实图像静默相册、图像计费幂等与删除到文件传播。
MOM-05 BLOCKED：没有授权图像Provider，无真实文件/哈希。
MOM-10 UNVERIFIED：缺100条人工复核候选评测。
证据：[P04阶段记录](p00-p07/P04/P04_STAGE_LOG.md)、
`evidence/p04/privacy-6be8c1bc45c34d49/`、
`scoring-7352368da5744a1b/`、`scoring-55d9917195da4873/`、
`scoring-e8286ecbbce14cce/`。

### P05 工具、语音与回访

TOOL-02/03/04 PARTIAL：天气/路线/地点真实API、配额/重放/越权/恢复、
天气交互浏览器路径已验；完整模型聊天、路线卡/提醒联动、
完整故障/限流UI未验。TOOL-01 BLOCKED：搜索Provider未配置。
VOICE-01 BLOCKED：STT/TTS未批准和配置。
VOICE-02、FOLLOW-01/02/03 NOT_RUN：方言、事件回访、取消/静默频控、
私密事件回访未实测。证据：[P05阶段记录](p00-p07/P05/P05_STAGE_LOG.md)及第4节。

P06家庭授权10项、P07后台治理/运维10项全部NOT_RUN，本轮明确不进入。
全矩阵73项仅14项PASS；这是验收点计数，不能当作产品代码完成率。
阻断、规模评测和未测项均保留分母，不因单元测试通过提高状态。

## 6. 产品差距、故障与阻断

| 需求 / 问题 | 尚未完成 | 原因 / 实际边界 |
| --- | --- | --- |
| 可靠聊天 | 部分异常、实体IME、身份生命周期、新工具完整聊天 | 覆盖不足，合成夹具不能代替 |
| 记忆闭环 | 聊天问答/点击、规模评测、全链路删除/隔离 | 后端场景证据不足以通过全部需求 |
| Graphiti | 原生episode/hybrid检索 | 缺Embedding |
| 可靠提醒 | 全语言、多目标、长期离线/竞态、常驻调度/终端 | accepted不代表设备送达；周期提醒/OS Web Push未交付 |
| 自动生图 | 真实图片、静默相册、计费和文件生命周期 | 无明确授权Provider |
| 天气完整体验 | 新聊天、日期/失败/限流/全部地点标识 | 当前公共账本6/6耗尽，常用服务未启用Provider |
| 路线/提醒联动 | 产品卡、可编辑提醒草稿 | 本轮范围外，须恢复授权 |
| 搜索 | 可信链接与查询时间闭环 | 无已配置Provider |
| 语音/方言 | 录音授权→转写→聊天→可选朗读 | STT/TTS未获批，未实测 |
| 主动回访 | 事件依据、时间、静默/频控/撤回 | 未执行，本轮禁止新增 |
| 家庭连接 | 双向邀请、细分享、撤权、IDOR等10项 | P06未执行 |
| 后台/治理 | 指标、RBAC、备份恢复、配额告警、迁移等 | P07未执行 |
| 性能 | 完整三轮LCP/CLS/TBT | 历史缺口，最近NO_NAVSTART；部分报告不算通过 |
| 既有lint失败 | ReminderCards全文件一项规则失败 | 旧快照可复现，未改本次行外代码 |
| 多用户上线 | 自助开通、全资源隔离、访问JWT即时撤销 | 目前仅明确映射本地内测 |
| Android | APK、真机通知/语音/相册、离线与签名 | 仅计划与API边界，未交付 |
| 环境/依赖 | WSL bash失败，RAG API未运行warning | PowerShell可工作，高级上传/检索未完整验 |
| 旧数据不变证明 | 全过程数据库不变证明缺失 | 限定源码SHA无法证明数据库从未维护写入 |
| 费用审计 | 早期智谱完整次数/token与账户实际扣费 | 旧usage缺失，不能推算 |
| 历史索引证据链接 | 产品/开发日志旧索引有8处证据目标不在当前隔离工作树 | 为早于P00的v02、launcher、v022、公网演示记录；本轮不迁移旧证据或补造文件 |

详细历史见 [BLOCKERS.md](../BLOCKERS.md)及阶段记录。
本轮未为提高通过数而修复上述历史缺口，也未删失败证据。
本报告及暂停入口的新链接均单独核验；8处历史缺失链接的明细保存在
`evidence/p05/pause-handoff-validation.json`。不能由旧索引中的PASS文字
推定对应演示管理员/临时公网/启动器在当前工作树已获新验收。

## 7. 外部API额度与费用

本轮收尾只读本机SQLite/Git/Docker和本机健康HTTP，外部请求0。
原DeepSeek地址/Key保持不变，未增加供应商、收费服务或本地模型。
核对31份SQLite，按表及call_id/window_id去重，P04浏览器复制库不重复计数。
明细见 [`pause-api-usage.json`](../../evidence/p05/pause-api-usage.json)。

| 供应商 / 场景 | 可核验累计请求 | 额度 / tokens | 限制 |
| --- | ---: | --- | --- |
| DeepSeek P02关系提取 | 12成功 | 输入33756、输出1779；该库12/12 | 真实持久账本 |
| DeepSeek P04八维评分 | 1成功 | 输入1363、输出457；验收预算2已用1 | 复制库去重；不据此授权再调用 |
| 上述DeepSeek合计 | **13成功** | **输入35119、输出2236，合计37355 tokens** | 留存账本可核对量，不是账户全部活动保证 |
| 天气增量模型 | **0** | 提取、评分、聊天生成、生图均无新增 | 与历史13次分别说明 |
| P05公开工具HTTP | **6** | **硬上限6/6，余0**；天气含503共3、地点2、路线1 | 首个API增量4、天气聊天增量2；失败/清除不退回 |
| 早期智谱聊天 | 至少5 | P00四次、P01一次；完整token/费用UNKNOWN | 历史记录，当前不切回 |
| 早期智谱提取 | 成功有证据，完整次数UNKNOWN | 另有4条failed尝试账本、usage缺失 | failed不能称免费，空usage不是0 token |
| 图片生成 | 审计范围内0 | 无授权调用/计费回执 | 不对供应商全账户作零消费保证 |
| 搜索/STT/TTS/Embedding | 阶段证据未启用、无已记录调用 | 精确账户消费UNKNOWN | 不探测收费端点 |
| Memos/Vikunja/ntfy/Neo4j | 本机隔离部署 | 不属外部付费API用量 | 本机请求不混入供应商计数 |

历史DeepSeek余额曾观察到差值0.00 CNY，是账户级快照，
不是13次调用的费用归因，也不代表免费。没有重新查询当前余额。
**精确已扣金额、当前账户余额、账户剩余额度均UNKNOWN。**
历史models/balance为非生成请求，不混入13次；管理端点完整次数未统一记录。

未来经用户授权确需真实调用时，应先定验收问题与累计小额上限，
沿用原工具库，不换库绕过配额。不因报告显示评分余量便自动消费。

## 8. 建议实施顺序与下次入口

仅列建议，当前不执行：

1. 用户先审阅本报告、天气截图和日志，明确恢复授权及真实API小额预算。
2. 从P05天气缺失验收继续：完整发送聊天、日期/失败/预算浏览器覆盖，
   优先复用回执与本地测试，确认是否准许新增公共请求。
3. 安排P00～P04安全/生命周期缺口：身份/撤权、删除传播、
   常驻提醒调度/竞态/终端送达，并保留人工规模评测门槛。
4. 经授权继续P05路线卡/提醒联动；搜索/语音先确认供应商与成本，
   回访先验证静默/频控和敏感事件边界。
5. 图像Provider明确授权后闭合P04真实图片；Embedding同理补P02。
6. 按原路线推进P06家庭授权，随后P07后台/治理/备份恢复、
   全视口、性能、迁移部署与完整回归。

下次首先读 [`NEXT_ACTION.md`](../../NEXT_ACTION.md)，再读
[P05_E2E.md](p00-p07/P05/P05_E2E.md)及
[天气日志](../development-log/2026-11-04_08-46_P05天气聊天卡与受限网关_开发验收.md)。
代码入口为 `services/life-core/app/tool_chat.py`、嵌套
`packages/api/src/memory/life.ts`、`client/src/components/Life/ToolCards.tsx`。
先验证工作树身份；不直接重跑已取消且预算耗尽的验收命令。

## 9. 交付物索引

- [独立暂停审计日志](../development-log/2026-11-04_09-40_P05天气收尾与人工暂停审计_开发验收.md)
- [天气r2最终审计](../../evidence/p05/chat-delivery-audit-r2.json)
- [Git清单](../../evidence/p05/pause-git-status.json)
- [服务与进程](../../evidence/p05/pause-services.json)
- [额度明细](../../evidence/p05/pause-api-usage.json)
- [敏感信息扫描](../../evidence/p05/pause-sensitive-scan.json)
- [逐ID验收点盘点](../../evidence/p05/pause-stage-inventory.json)
- [只读审计脚本](../../evidence/p05/pause_audit_readonly.py)
- [原总矩阵](p00-p07/11_跨阶段总验收矩阵.md)

**PAUSED_FOR_USER_REVIEW**
