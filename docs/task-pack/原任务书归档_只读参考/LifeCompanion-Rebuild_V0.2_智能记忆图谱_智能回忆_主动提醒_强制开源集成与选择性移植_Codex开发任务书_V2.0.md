# LifeCompanion-Rebuild V0.2｜智能记忆知识图谱、智能回忆筛选、自然语言主动提醒

## 强制开源集成 + 双项目隔离 + 既有成果选择性移植：Codex 完整开发任务书

> **任务书版本**：V2.0｜2026-11-03  
> **唯一目标项目**：`LifeCompanion-Rebuild`（成熟开源框架集成、适配与产品化项目）  
> **只读参考/可能的成果来源**：`Silver-economy-research`（自主实现研究项目）、历史目录 `Silver-economy` 及其 `.work/intelligence-20261103` 隔离工作树。三者间的真实 Git 关系尚待 Codex 核实。  
> **任务属性**：实际开发、运行、联调、测试、验收，不是纯调研或只写设计。  
> **模型策略**：不在本地部署任何 AI 模型；所有可用的语言模型能力调用项目中**已经配置并经实际验证可用**的云端会话模型；不默认任何新模型、API Key、额外云厂商或费用。  
> **向量策略**：目前没有经验证可用的 Embedding API，且不得安装本地 Embedding；首期必须完成**无向量的核心业务闭环**，Embedding 为独立可选增强。  
> **文件优先级**：本任务书取代此前面向旧 `Silver-economy`/未明确项目的本地 Qwen、Laya、本地 Embedding、强制百炼等指令；不得取代 Rebuild 仓库本身已经生效的更严格安全/数据/设计规范。

---

# 0. 最高优先级的禁止事项与目标声明

**首要任务不是马上写业务代码，而是先确认当前工作区究竟属于哪个项目。**

本轮严格禁止：

1. 在未确认仓库身份之前，对 `Silver-economy`、`Silver-economy-research`、`LifeCompanion-Rebuild` 中任何一个目录执行写操作。
2. 将历史路径 `H:\AI For research institute\Silver-economy` 直接当成 Rebuild；根据页面标题、Logo 或“V0.2”判断仓库归属。
3. 直接把旧项目全部源码、`node_modules`、`.venv`、数据库文件、用户聊天、资产目录或 `.env` 复制进 Rebuild。
4. 为了让旧成果可用而把 Rebuild 重构成旧项目的目录结构或技术体系。
5. 在未核实已有能力前，再建一套平行的聊天、记忆、回忆、提醒、用户、授权或调度系统。
6. 通过克隆仓库、安装 pip 包、启动 Docker 容器、编写 Mock 就宣称“框架集成完成”。
7. 下载/运行任何本地大语言模型、向量模型、Laya/Jev、Ollama、vLLM 或 GPU 推理服务。
8. 默认用户拥有阿里百炼、硅基流动、OpenAI 或其他额外平台的 API Key；擅自注册、充值、调用未批准付费接口。
9. 用聊天模型编造数值向量，或以无向量 Neo4j 检索冒充 Graphiti 原生混合检索已通过。
10. 擅自执行 `git reset --hard`、`git clean`、强制覆盖、删除工作树、覆盖设计源规范、清空数据库、格式化/清理运行卷、关闭其他项目服务、合并主分支、Push、部署公网。
11. 对现有生产用户自动开启额外云端记忆提取、主动提醒或私密回忆生图；必须检查/尊重授权与原有隐私设置。
12. 复制旧项目的测试结论当作 Rebuild 的真实验收结果。

**最终两条必须真正跑通的产品链路：**

- **A 智能记忆与回忆**：原始聊天持久化 → 事实/事件/人物提取 → LangMem 提取与合并 → 权威事实/证据入库 → Neo4j 关系与时间图谱 → 无向量结构化/全文/图查询 → 记忆重要度计算 → 时间窗回忆候选 → 云端结构化评分 → 严格证据门控 → 现有回忆页/可选生图呈现。
- **B 主动提醒**：用户自然语言表达潜在日程 → 云端会话模型判别意图 → 显示克制的建议卡 → 复用 Rebuild 已有编辑弹窗 → 用户明确确认 → LangGraph 可恢复工作流 → 正式提醒写入 → APScheduler 独立持久化调度 → 实际站内通知/已实现通知渠道 → 状态与证据可追溯。

**执行规则**：身份能明确锁定且安全基线通过，即按阶段实际实施，不要反复让用户确认已经明确的要求；若项目身份不明确、拟写入非 Rebuild 仓库、可能损坏正式数据或需要新增收费平台，立即停止相应高风险操作，只输出阻塞信息并请求一个必要确认。

---

# 1. 双项目身份及唯一写入目标：不可省略的 P0 门禁

## 1.1 三个名字的真实含义必须审计

| 标识 | 用户已经确认的定位 | 本轮权限 |
|---|---|---|
| `LifeCompanion-Rebuild` | 优先整合成熟开源框架的产品化项目 | **唯一允许实现业务修改的目标仓库**，但先锁定实际路径 |
| `Silver-economy-research` | 自主开发/纯手搓研究项目 | **默认严格只读**；仅供参考、对照、评估可移用代码 |
| `Silver-economy` | 历史工作目录/仓库名，和两个新项目的关系未确定 | **默认严格只读**；不能推断其归属 |
| `.work/intelligence-20261103` | 旧轮 Codex 产生的隔离工作树，据聊天记录曾在此开发智能记忆/提醒 | **仅供成果审计和选择性提取**；不把它视为目标项目 |

## 1.2 第一阶段必须生成 `PROJECT_IDENTITY_AUDIT.md`

Codex 需要在**实际文件系统**中只读核实：

- 每一个候选项目的绝对路径、Git 仓库根目录、仓库名、`remote origin`、当前分支、HEAD、worktree 列表、未提交及未跟踪文件状态。
- 如果项目路径中没有 `.git`，明确是否为子目录、打包快照、独立复刻或非 Git 项目。
- 三个项目之间是否共享工作区、Git remote、Docker Compose、环境文件、数据库连接或静态资源目录。
- 现在显示的 PC 和手机端页面由哪个**实际前端构建目录、进程、端口、API Base URL、容器**提供；不能只凭 UI 视觉相同判断。
- 现有运行中的数据库：地址（脱敏）、库名、迁移版本、卷归属、进程/容器归属、所服务的具体应用；严禁串连 V0.2 与其他版本库。
- 旧专项的“119 个变更文件”实际位置、状态、变更分类、是否真正已提交、是否已经被复制到其他仓库；以当前 Git/文件系统实测为准，**119 只是用户提供的历史记录，不预设今天仍为 119**。
- 给所有候选源与目标建立只读目录清单和原有文件的 SHA-256 摘要，记录修改前状态，避免迁移中丢失旧成果。

### P0 硬门禁

- **明确锁定 Rebuild 目标根路径**，并在工作记录中填入实际绝对路径、Git remote、HEAD；之后所有新代码写入必须在此路径下的独立开发分支/工作树（或项目允许的隔离副本）。
- 在审计确认前，不允许自动选择某个最像的目录作为目标。
- 不允许在这三个项目共用的现有运行容器中直接跑有风险的数据迁移。
- 为本次工作使用独立名字的测试数据库、容器/Compose project、端口、卷及工作目录，不能停止或重用其他项目的生产资源。
- **每次打开新的终端、脚本或子 Agent，先验证工作目录仍指向 Rebuild**。如果路径、Git remote 或工作树改变，必须立即报错退出。

建议维护机器可读的工作区锁定文件（字段示例，实际由审计结果填写）：

```yaml
project_id: LifeCompanion-Rebuild
canonical_root: <经实际验证的绝对路径>
git_remote: <实际 remote origin>
base_commit: <实际 HEAD>
worktree: <本次隔离工作树>
allowed_write_prefixes:
  - <本次 Rebuild 工作树路径>
read_only_source_roots:
  - <Silver-economy-research 的实际路径>
  - <Silver-economy 历史目录的实际路径>
  - <旧轮 intelligence-20261103 工作树路径>
production_data_write_allowed: false
```

**校验脚本必须在任务开始与执行危险命令前真实运行**；禁止仅写文件但不调用。

---

# 2. 先审计 Rebuild 已有架构，再决定“引入”方式

这不是把旧 `Silver-economy` 的 V0.2 目录机械搬过去。本次所有实现要**服从实际 Rebuild 架构**。

## 2.1 必须查看的 Rebuild 资产

- 根 `README`、`AGENTS.md`、产品规格、架构规范、UI/设计系统、开源许可清单、开发流程、现有任务与变更记录。
- 前端：实际框架/版本、路由、聊天页、记忆页、回忆页、提醒页、通知展示、弹窗、用户设置、移动端/桌面端样式、请求客户端、状态管理。
- 后端：语言/框架与版本、聊天和模型路由、消息表/存储层、记忆/事件/回忆/提醒服务、用户与授权、任务队列、通知提供器、日志/预算。
- 已集成的开源技术：有没有 LangGraph、LangMem、Graphiti、Neo4j、Qdrant、Mem0、其他记忆或 Agent 框架；源码及接口是否真的被线上业务调用。
- 存储系统：关系型主库是什么、图数据库是什么、现有全文检索和向量能力是什么、备份/恢复/迁移机制如何。
- Docker、Compose、Windows 开发脚本、Ubuntu 部署脚本、当前环境变量、CI 和 E2E。
- 聊天模型的**实际**配置和路由：模型 ID 是如何从用户会话配置传到后端的；后台作业在会话不活跃时如何获知模型；已有 Key 是否真实可用。**只检查配置是否存在与连通性，不输出任何 Key。**

## 2.2 需要的审计输出

1. `REBUILD_BASELINE_AUDIT.md`：真实技术栈、依赖、当前数据模型与调用链，注明每项的证据文件/函数/数据库查询。
2. `REBUILD_EXISTING_CAPABILITIES.md`：逐项标记“原生已有 / 已依赖但未用 / 部分实现 / 完全缺失 / 与本轮冲突”。
3. `REBUILD_ARCHITECTURE_DECISIONS.md`：明确哪些组件复用、扩展、替换、停用，为什么，避免再造平行系统。
4. `REBUILD_TEST_BASELINE.md`：在**Rebuild 隔离环境**实际跑一次现有测试，记录通过、失败、跳过和未配置的原因。
5. `MIGRATION_SOURCE_INVENTORY.md`：旧工作树可用功能与文件映射（见下一章）。

**禁止默认** Rebuild 已经采用 Vue3、FastAPI、MySQL、某种迁移器、某个页面路径或某个特定端口。只有审计后才可采纳。若 Rebuild 已有高质量框架接入，应优先扩展现有模块，而非再装一份同功能组件。

---

# 3. 旧成果只能“选择性移植”，绝不整体克隆覆盖

## 3.1 旧轮已报告的成果，属于待复核候选

用户提供的 Codex 历史日志报告过：

- 无向量 LangMem + Neo4j 记忆抽取/关系查询/证据回查；
- MySQL 与 Neo4j 隔离实例和迁移、outbox 同步与用户权限边界；
- 用户实体/公司实体/事件时序、重复事实合并和历史保留；
- 记忆图查询 100 组、Recall@1 以及多用户隔离测试；
- DeepSeek 200 条意图评测、宏平均 F1 约 0.924；
- LangGraph 确认流、APScheduler 调度与站内通知；
- PC/手机端建议卡、编辑弹窗和浏览器 E2E；
- 旧隔离环境后端回归 571 项通过。

**上述全是历史执行记录中的自述结果，并非对 Rebuild 的验收事实；不得直接沿用 PASS。** 必须检查文件、实际依赖、真实日志、样本和代码，独立复跑；若找不到证据，标记 `UNVERIFIED`。

## 3.2 每个可移植模块必须评估的维度

| 维度 | 核查问题 |
|---|---|
| 来源归属 | 文件实际位于哪个仓库、哪个 commit/工作树？是不是原创代码？ |
| 开源许可 | 原代码及所依赖框架的 LICENSE、NOTICE、署名要求是否可满足？ |
| 功能价值 | 是否真实解决当前痛点，而不只是 UI 或 Mock？ |
| Rebuild 重合度 | Rebuild 是否已用成熟框架解决同一件事？是否会形成重复服务？ |
| 耦合 | 是否硬绑定旧目录、旧 ORM、MySQL 特定表、旧 API、旧样式或私有依赖？ |
| 安全 | 是否包含硬编码 API Key、真实聊天、私密日志、用户 ID 或危险迁移？ |
| 测试 | 原来的单元/集成/E2E 证据是否可复现？能否在 Rebuild 中重新通过？ |
| 性能 | 是否适合目前开发机有限内存以及日后 Ubuntu 部署？ |
| 后续维护 | 能否改成 Rebuild 的接口与模块，明确责任边界？ |

## 3.3 强制提供 `SELECTIVE_PORTING_MATRIX.md`

每个候选文件/功能逐项填写：

```text
source_project | source_commit | source_path | capability
source_license | evidence | target_existing_capability
migration_decision [REUSE_AS_IS / ADAPT / REIMPLEMENT_WITH_FRAMEWORK / REJECT / DEFER]
target_path | design_reason | dependency_risk | test_plan | actual_result
```

不得只写“旧代码已迁移成功”。必须有**旧文件→目标模块→修改原因→实测结果**的逐项追溯。

## 3.4 原则性移植顺序

1. **先复用 Rebuild 已经存在且运行良好的开源模块**。
2. 对旧成果中业务逻辑清晰、耦合较低的部分（如 Pydantic Schema、评测 fixtures、时间解析的纯函数、源证据过滤规则、幂等键算法）优先做**小范围适配**。
3. 对知识图谱、记忆、提醒等核心模块，优先沿着 Rebuild 原生边界**移植算法与测试思路**，而不是复制整个旧服务。
4. 对旧 ORM、旧迁移、旧数据库连接串、旧 Compose、旧 Docker 卷、旧账号/配置、旧前端整页组件，默认**不直接移植**。若确有必要必须做单项适配说明、单独评审与隔离测试。
5. 旧项目 UI 只能作为视觉/交互参考；应使用 Rebuild 自身组件体系、主题 Token、动效/响应式规范构建必要增量。
6. 不复制真实个人记忆、原始聊天、私密素材、历史生产日志和 API Key；只用经过授权的专用匿名测试样例。

**迁移手段**：只读复制少量经批准的源码到 Rebuild 隔离工作树，或者在 Rebuild 中重写适配器；对每个移植提交记录来源、许可证、diff 和测试。未经用户明确授权不对旧来源仓库做 cherry-pick、merge 或改写历史。

## 3.5 旧成果移用验收

- 两个源仓库与旧工作树的关键文件/数据修改前后哈希一致；
- Rebuild 的原有聊天与开源框架仍保持原架构；
- 移植后没有两份并行的记忆主库/提醒主服务/配置入口；
- 旧代码的硬编码路径、账号、数据库版本、模型 ID、风格 Token 被消除；
- 旧轮评测在 Rebuild 环境**重新运行**，结果单独归档，不合格则修复，不能引用旧 PASS。

---

# 4. 强制技术栈及“真实接入”的验收含义

| 类型 | 必须采用/接入 | 真实执行职责 | 集成完成判据 |
|---|---|---|---|
| 时序知识图谱框架 | **Graphiti** | 真实接入 Rebuild 的图谱适配层；管理 episode/时间关系，保留未来标准检索能力 | 提供版本、调用路径与可运行的实际兼容验证；无 Embedding 时不能伪称全部原生功能通过 |
| 图数据库 | **Neo4j** | 保存 Person、Organization、OrganizationType、Event 及时间、来源关系 | 真实建库、增量数据、读写、隔离、历史查询、重建测试通过 |
| 记忆处理 | **LangMem** | 从聊天与已有记忆中真正提取、更新、合并、纠错，输出规范结果 | 真实云模型调用+LangMem 管理器+持久化更新，不能只引用包名 |
| 用户确认流 | **LangGraph** | 用户可恢复的提醒建议、编辑、确认/取消/改期工作流 | 真实 `interrupt/resume`、持久 checkpointer 和重启恢复测试 |
| 定时任务 | **APScheduler** | 提醒执行、必要回忆窗口调度，独立 Worker | 真实触发、持久、重启恢复、取消幂等、通知记录 |
| 无向量检索 | **Neo4j 结构化图查询 + 全文检索 + 云模型结构化意图解析** | 在没有 Embedding 时完成主要记忆问答和关系检索 | 真实关系/别名/时序/证据查询及准确率测评 |
| 云端语言理解 | **当前会话实际有效的云端模型配置** | 记忆、实体、判别、回忆评分、提醒意图 | 路由与版本可追踪，实际请求；不得写死某个 `deepseek-*` 名称 |
| 主业务数据库 | **保留 Rebuild 已有权威数据存储** | 聊天、记忆、证据、回忆、提醒、授权、通知 | 原结构审计后增量迁移，绝不因旧代码改换权威主库 |
| 部署 | **Rebuild 的现有容器/部署体系 + Docker Compose 可迁移配置** | Web、API、worker、scheduler、Neo4j 等 | Windows 可运行、Ubuntu 可复现，不依赖其他项目服务 |

可额外引入开源依赖时，必须给出：确切用途、版本、许可证、资源开销、安全评估、与现有技术是否重叠；不得以“强制开源”为由堆叠全部候选库。

## 4.1 特别规则：Graphiti 强制引入不等于伪造 Embedding

截至本次任务，用户未配置可验证的 Embedding API，并明确不要本地模型或新的付费供应商。Graphiti 的默认完整 episode 处理/混合检索通常要求 Embedding；必须尊重真实兼容性：

- **Graphiti 依赖/适配器必须进入 Rebuild 的正式架构**，锁定可用版本，检查其公开 API 和默认模型调用行为，阻止其偷偷使用 OpenAI 等未经授权的默认供应商。
- 若目标版本确实有不需要向量的官方原生入口，可以用真实功能测试证明；不得凭猜测绕过必需组件。
- 若实际调用需要向量，则保留真实 `GraphitiProvider`、episode 映射、版本、启动/兼容性测试和开关，但将相应原生功能标为 `BLOCKED_EMBEDDING`，**不允许自己生成假向量，也不允许把 Neo4j 原生查询冒称 Graphiti 原生功能**。
- **当前主要业务不能因此停工**：Neo4j 图谱写入、LangMem 合并、受控关系检索、回忆评分和提醒可以完整运行并独立验收。
- Graphiti 完整原生运行是一个**仍需完成的强制验收项目**，不能从任务书中删除、降级成“完全可选”；只允许在依赖确实未具备时明确阻塞。不得以该项阻塞否定其他已真实完成的功能。
- 未来用户明确提供经过验证的云端 Embedding 服务后，再开启 Graphiti 标准流程及向量检索，重新建索引并跑完整门禁。

## 4.2 当前明确不需要的东西

- 本地 Qwen、Laya、Jev、多模态模型和本地 Embedding 权重；
- 云端阿里百炼（尚未开通）、硅基流动、OpenAI 等任何新供应商的默认 Key；
- 为了无向量模式专门新建 Qdrant/向量库（Rebuild 若已有则保留，不删除；但不强制启用）；
- 把整个旧 `Silver-economy` 项目迁入 Rebuild 的一键全量迁移脚本。

---

# 5. 云端模型路由：严格遵照当前聊天实际模型

## 5.1 模型能力与状态必须先审计

不预设 DeepSeek 一定为唯一供应商，也不把旧轮 `deepseek-flash` 或 `deepseek-v4-pro` 当成当下永远有效的模型。审计 Rebuild 的实际模型路由、会话模型选择、API URL、Key 存在性和真实连通性。

定义后端模型入口（与现有代码结构适配）：

```text
ConversationModelRouter
  -> resolve(user_id, conversation_id, task_type, config_snapshot)
  -> ChatCompletionProvider (记忆提取/消歧/判别/回忆评分/提醒意图)
  -> StructuredOutputValidator (Pydantic/现有类型校验)
  -> UsageBudgetAuditor (配额、预算、请求状态和模型版本)
```

具体要求：

1. 有活跃会话时，语义任务**使用该会话实际启用的云端聊天模型**，不是静态硬编码别的模型。
2. 后台定时记忆整理或回忆筛选时，任务创建时保存经授权的 `provider/model_id/config_version` 快照，或根据 Rebuild 既有用户默认模型策略解析；不得在会话关闭后悄悄改变模型。
3. 若当前模型不支持所需结构化输出能力，走明确的适配/校验/有限重试流程；无法满足时 `BLOCKED_MODEL_CAPABILITY`，**不未经允许换成其他付费模型**。
4. 不凭空假定有任何模型 Key；按项目配置读取并做最小真实 Smoke Test，密钥不出现在日志、报告、前端或 Git 中。
5. Graphiti/LangMem 内部 LLM 调用要经过同一个受控路由层，禁止第三方 SDK 隐式发送用户内容到默认外部提供商。
6. 记录 `user_id`（脱敏）、`task_type`、`provider`、`model_id`、`prompt_version`、`request_id`、`token_usage`、`latency_ms`、`outcome`、`cost_estimate`；严格尊重用户授权、账本配额和并发限流。

## 5.2 Embedding 与聊天模型严格分离

- 不向 `/chat/completions` 请求“帮我生成 1024 个向量值”来假装 Embedding。
- 当前不引入新的付费 API 或本地模型。定义可插拔接口 `EmbeddingProvider`，默认状态 `DISABLED_NOT_CONFIGURED`。
- 若用户将来明确批准某个真实云向量 API，需先验证模型 ID、维度、地域、价格与接口，再启用图谱/向量索引重建。
- 在当前无向量模式不启动额外云向量请求、不产生额外费用，也不因此牺牲聊天、回忆、提醒的主流程。

---

# 6. 业务数据和证据：原始聊天、记忆、图谱、回忆必须分层

## 6.1 必须明确的五层概念

1. **聊天记录**：原始用户/助手消息，包含消息 ID、会话、发生时间、发送状态、角色及授权标记；按现有策略保存和删除，禁止被摘要覆盖。
2. **长期记忆**：稳定事实、偏好、事件、关系的压缩表达，记录归一化内容、可信度、证据来源、版本和更新时间。
3. **事件与时序关系**：谁在什么时候遇到谁、加入何种组织、邀请了谁、与公司关系何时生效/失效。
4. **知识图谱/检索投影**：Neo4j 中可从权威事实重建的实体、边和证据，不作为未经审核事实的额外主库。
5. **回忆**：从已储存且符合时间窗与授权的记忆事件中筛选出的内容；生成的文字/AI 图像必须可以追溯原始证据。

如果 Rebuild 已有不同命名或结构，应保留既有业务模型，通过字段/索引扩展来实现上述语义；不能直接照抄旧迁移。

## 6.2 必要业务属性（按实际数据库设计）

| 逻辑对象 | 必须能表达的内容 |
|---|---|
| ChatMessage | `id/user_id/conversation_id/role/content/timestamp/status/consent` |
| MemoryItem | `id/user_id/canonical_fact/type/confidence/strength/version/status/valid_time` |
| MemoryEvidence | `memory_id/source_message_id/evidence_role/observed_at` |
| MemoryEvent | `id/user_id/event_type/participants/occurred_at_start/end/source_ids` |
| Entity | `entity_id/namespace/type/canonical_name/aliases/resolution_status` |
| Relation | `subject_id/predicate/object_id/valid_from/valid_to/observed_at/source_ids` |
| RecollectionCandidate | `window/event_id/memory_ids/score_vector/gate_result/model_version` |
| Recollection | `id/user_id/source_ids/memory_ids/event_id/text/asset_id/ai_generated/status` |
| ReminderProposal | `id/user_id/source_ids/intent/event_time/remind_time/needs_confirmation/status` |
| ReminderWorkflow | `thread_id/proposal_id/user_id/checkpoint/status` |
| Reminder | `user_id/title/event_at/remind_at/timezone/confirmed_at/delivery_state` |
| DeliveryAttempt | `reminder_id/channel/attempt_id/attempted_at/provider_state/delivered_at` |

不强制所有对象都是独立新表；若 Rebuild 已有成熟表结构，优先兼容扩充，避免同义表重复。

## 6.3 图谱实体正确性案例

- `Person(老朋友甲)` / `Person(朋友乙)` 是两个人；
- `Organization(星火科技)` / `Organization(云帆智能)` 是两家企业；
- `OrganizationType(初创公司)` 是共享概念，不是第三家企业，也不是两家公司“相同”的证据；
- `INVITED_TO_JOIN` 只表示发出邀请，**不推出**用户已经加入；
- “我们的公司”如果上下文不够，应 `NEEDS_DISAMBIGUATION`，不得自动生成入职关系；
- “小王离开 A 加入 B”保留 A 的历史就职关系、B 的当前关系，回答要考虑提问时间；
- 两次同义表达只追加/修订同一个事实的证据，不新增两条相互矛盾的主事实；
- 纠正旧事实时保留可审计修订，不把先前错误当成当前事实；
- 用户删除历史消息或撤销记忆授权时，对应派生图、缓存和回忆应同步失效/重建。

## 6.4 数据一致性和恢复

- 以 Rebuild 现有业务主库为权威来源；建立 outbox 或等效可恢复任务来驱动图投影，禁止图服务故障导致聊天消息丢失。
- 任何写入有 `user_id/namespace`，查询服务端再次回查授权、业务版本、消息来源有效性；不依赖单一模型自行判定访问权限。
- 独立用户隔离，图节点、全索引、缓存、checkpoint、定时任务都不得跨用户串用。
- 提供 dry-run、增量回填、失败重试、幂等、导入中断恢复、重建与双向数量核验；旧真实数据迁移需用户单独授权。

---

# 7. LangMem：必须真正负责记忆提取与合并

把 Rebuild 已有聊天持久化成功后的事件，接入一个异步记忆处理任务（尊重授权）。

**完整过程：**

`source_message_ids → 会话上下文 → 读取已有用户记忆 → 当前模型 + LangMem 提取/修订 → Pydantic 校验 → 事实比对 → create/merge/update/historical/needs_confirmation → 业务主库存证 → outbox → Neo4j 投影`。

要求：

- 调用 LangMem 真实 memory manager/store manager API，保留已有事实上下文，不能每次“全新提取”造成无穷重复。
- 根据实际 Rebuild store/ORM 设计，统一事实写入入口；不能同时让 LangMem、Graphiti、旧手搓记忆模块分别维护三份权威记忆。
- 明确事实与推测、用户本人和他人、过去/现在、否定/转述、来源消息的关系。
- 重复记忆的权重由**独立有效证据次数、用户明确重视、最新确认、稳定性、可信度及冲突状态**共同决定；词频仅能作为弱特征。
- 把 `memory_strength` 和 `recollection_score` 永久分开；用户第一次提及的重要经历也可能有高回忆价值。
- 拒绝没有事实依据的补全；可以返回 `uncertain/ask_confirmation`。
- 提供记忆修改历史与来源追溯，支持按用户清理和索引重建。
- LangMem / 云端模型连接失败时，记录 `PENDING/RETRYABLE`，不丢失原聊天，执行有预算的重试并防止同一消息重复计费/重复写入。

---

# 8. Neo4j 无向量关系检索：本轮必须真正可用

在 Rebuild 实际部署 Neo4j（如果已有，则扩充现有正确实例，不另起平行业务图），至少实现：

- 人物、公司、类型、经历、时间、来源、别名与消歧状态；
- 关系有效时间与系统获知时间分开存储；
- 根据具体用户/租户隔离关系；
- MySQL/其他主库事实与图投影的 outbox 对账；
- 全文索引或现有检索组件的真实中文搜索能力，验收需覆盖中文分词/词组/别名；不能假设英文 Lucene 分词对中文天然可靠；
- 固定白名单、参数化、只读的查询工具，云端模型**只产出结构化查询意图**，不允许任意执行它生成的 Cypher；
- 模糊检索“邀请我创业的朋友”时结合关系路径、别名映射、时间和证据；
- 面向用户的最终回答只能使用查询返回且仍有效的授权证据，未查到应承认不知道。

必须提供真实 Neo4j 的图、关系/历史/证据查询日志及数据一致性检查。Graphiti 原生混合检索应按第 4.1 节独立状态报告。

**注意**：全文检索和图推理能满足大量明确关系问题，但不能保证无限规模、开放表达的高语义召回；必须测测召回率、误召回、P95 延时和样本限制，不能把 100 条含目标实体名的高命中率宣传成任意口语都 100% 准确。

---

# 9. 智能回忆：必须从可信记忆中筛选，而不是从聊天随意编造

## 9.1 端到端流程

`定时窗口 → 查询属于该时间段的有效 MemoryEvent → 关联 MemoryItem 和 source_message_ids → 过滤隐私/授权/重复/已发布 → 读取 memory_strength → 使用当前授权云端聊天模型作结构化价值评分 → quality gate → 选出候选 → 复用 Rebuild 既有文案与生图/展示服务 → 保存回忆证据 → 回忆页呈现`。

- 先审计 Rebuild 目前的定时规则和产品设计，不能直接套旧仓库的 11:00 等时间写死覆盖当前规则；如果不存在则以配置形式实现早/中/晚可调整窗口。
- 分数维度至少包括：个人意义、事件独特性、情绪线索、完整性、证据充分性、时间适配、隐私适宜性；模型只是评分器，不能跳过规则门禁。
- 回忆价值不是事实可信度，不可以只根据情绪强烈程度或词出现频次生图。
- 没有聊天、没有可靠事件、用户未授权或事件已经发布过时，明确跳过；**不要为了凑三张图而编造一天**。
- 同一天可能有多个有价值事件，考虑多样性，避免早中晚重复同一件事；新进展可以独立建新回忆。
- 回忆正文不能增加无来源的天气、人物姓名、行程细节等；图片需标注“AI 生成”，不要暗示是真实照片或真实肖像。
- 回忆需可回查原始消息的摘要/来源（以用户权限为准）；删除、纠错、撤销授权要处理派生回忆。
- 不强迫用户自己选择每张图；沿用用户已授权的后台自动筛选与发布策略。

## 9.2 必需的判别评测

实现 Jev 式的**结构化判别契约**，但不要求 Jev/Laya 模型本身：`choice / dimension_scores / uncertainty / evidence_message_ids / reason_codes / model_version`，云端使用当前模型路由。禁止把自由文本中的“挺重要”直接当可靠判别结果。

100 个回忆候选样本必须包含：高意义低情绪、低意义高情绪、重复日常、同一事件多时间窗、无来源、隐私禁止、事件时间冲突、需人工确认等；记录发布率、误发布、证据完整性和实际失败样例。

---

# 10. 自然语言主动提醒：必须打通从意图到真实通知的闭环

## 10.1 意图判别不是固定词触发

必须覆盖以下情况：

- “明天早上九点去医院” → 识别未来日程，建议是否设置提醒，但**九点的含义需确认**；
- “后天下午参加社区志愿服务” → 可建议创建，时间不精确则让用户选；
- “我想起明天得交材料” → 未出现“提醒我”也能建议；
- “朋友说他明天有会” → 转述他人，默认不创建用户任务；
- “不用提醒我了” → 拒绝/停止建议，不产生新任务；
- “把明天的改成周五” → 识别已有提醒修改意图，不创建第二个；
- “昨天差点忘了去医院” → 过去事件，不创建未来提醒；
- “周五下午可能要去见朋友” → 模糊、低强度，可询问但不强推；
- “我女儿周六要考试” → 其他人的事情，未经用户明确授权不能默认为用户提醒。

意图类型至少：`NO_ACTION / FUTURE_EVENT / TASK_INTENT / EXPLICIT_REMINDER / EDIT_REMINDER / CANCEL_REMINDER / QUOTED_THIRD_PARTY / UNCERTAIN`。

时间至少区分：`event_at`（事件发生/到达时间）、`remind_at`（提醒时间）、`timezone`、`time_precision`、`needs_confirmation`、`source_message_ids`。

## 10.2 前端交互必须服从 Rebuild UI

- 聊天中展示自然语言建议卡片：“需要我帮你设个提醒吗？”；
- 显示来源语句或来源摘要，支持查看原话；
- “设置提醒”打开 Rebuild **既有**提醒编辑/确认界面，预填仅可信字段；
- “先不用”/“不再提示此事”立即生效并持久化，拒绝后不得重复骚扰；
- 明确展示事件时间与提醒时间，用户自行修改、确认时区；
- 只有服务端真正保存后才能显示“已创建”；
- 保存中、保存失败、已取消、待通知、发送尝试、送达未知等状态准确可读；
- 手机端弹窗不能遮挡输入、底部导航或确认按钮；支持键盘、焦点管理、中文输入法、屏幕阅读器及减少动态效果偏好。

**用户提供的两张截图只能表明此前某个项目曾有此类交互，并不能证明 Rebuild 已有相同组件；必须在 Rebuild 真实界面实测并按其设计规范整合。**

## 10.3 LangGraph 强制真实使用

推荐状态：

`DETECTED → PROPOSED → WAITING_CONFIRMATION → EDITING → VALIDATING → COMMITTED → SCHEDULED → DUE → DELIVERY_ATTEMPTED → DELIVERED_CONFIRMED / DELIVERY_UNKNOWN / FAILED`。

- 使用真实持久化 checkpointer 与稳定 `thread_id`；实际实现 interrupt/resume、刷新恢复、服务重启恢复；
- interrupt 恢复会重新执行所在节点的前置代码，所有写业务库、扣费和发通知逻辑必须幂等并放在安全位置；
- `proposal` 是建议，`reminder` 是正式任务，两者绝不可混淆；
- 未确认或拒绝的提议不可插入可投递任务；
- 已确认任务的改期/取消应有实体定位、确认门槛和历史留存；
- `reminder_id`、`proposal_id`、`thread_id`、`delivery_key` 需正确关联，重放不重复创建。

## 10.4 APScheduler 强制真实使用

- 独立 scheduler 进程/容器，不能让多个 API worker 各运行一份相同定时器；
- 用与所选 APScheduler 版本匹配的持久 job store 或**以权威数据库任务表为准并可恢复调度**；重启不丢任务；
- 定时到期后走真实投递适配器（站内通知、已有 Web Push 或项目现有渠道），不能仅往控制台 `print`；
- 真实测试取消、改期、重复触发、延迟任务、断网恢复与服务重启；
- 明确区分 `saved / scheduled / attempted / provider_accepted / delivered_confirmed / unknown / failed`，无设备回执不能显示“已送达”；
- 不保证浏览器关闭后的站内通知自动到达手机；若项目没有真实 Web Push/移动推送通道，则将该能力独立标 `PARTIAL`，不能用站内气泡替代手机后台推送验收。

---

# 11. 开发隔离、迁移与部署约束

## 11.1 工作环境

- 仅在 Rebuild 新工作树/隔离副本中开发和执行有副作用的构建、迁移、测试；
- 旧 `Silver-economy-research`、旧 `Silver-economy` 及历史工作树严格只读；
- 为 Rebuild 测试服务设置专属 Compose 项目名、服务名、数据库名、volume、网络和不冲突端口；
- 有资源紧张（历史记录称开发机 16GB RAM）时限制容器资源/并发，不停止其他项目来让当前测试通过；
- 区分 Rebuild 开发端口、预览端口和未来正式部署地址；未经授权不暴露公网；
- 数据库迁移先在测试/克隆数据库演练，校验数量、外键、备份和回滚；不对旧项目数据库进行写入；
- 按 Rebuild 现有 Docker 与 CI 规范锁定镜像/依赖版本，提供 Windows/Ubuntu 可移植部署文档；不让迁移依赖开发机绝对盘符。

## 11.2 模型与配置安全

- 只复用**已验证实际可用**的云端聊天模型配置；新的供应商和 API Key 由用户确认后才能使用；
- `.env.example` 只列变量名及说明；不提交任何真实 Key；
- 后台按授权最小化出网信息，不向第三方默认 LLM SDK 隐式发送个人记录；
- 费用、Token、429、重试、请求超时与未知结果由服务端按任务记录；未知结果不可盲目重试造成双重扣费或重复写入；
- 如已配置预算或额度限制，所有新增 AI 子任务都经过预算检查，不绕过原有费用保护；
- 模型不存在、无权限、响应不符合 Schema 时失败保守，不编造关系、不自动建提醒、不发布无证据回忆。

## 11.3 未来 Ubuntu 部署

统一使用容器、相对路径和环境变量迁移 Web、API、memory worker、scheduler、Neo4j 与业务主库连接配置。需要提供：一键健康检查、服务依赖顺序、持久卷备份/恢复、迁移演练、日志与告警、权限边界、恢复指南。**不要求任何本地 AI 模型或 GPU 驱动**。

---

# 12. 测试设计：旧轮结果不得继承为 Rebuild PASS

## 12.1 固定测试集与样本

- 至少 8 个隔离测试用户，用于用户与图谱/提醒/检索多租户边界测试；
- 至少 100 组记忆合并、事实冲突、人物/公司消歧和时间变化 fixture；
- 至少 200 条标注的自然语言提醒意图测试（正样本、否定、转述、改期、取消、语义模糊、日期跨年等）；
- 至少 100 条回忆候选判别样本；
- 至少 100 条或 100 组无向量自然语言检索评测（包含有姓名、无姓名、同义表达、跨会话指代、历史状态、干扰实体）；
- 多用户交错、乱序聊天、重复发送、消息撤回与删除、图服务断开、模型超时/429、任务重启；
- 样本使用**隔离合成或经授权的脱敏数据**，不把真实个人聊天复制成公开 fixture；可复现、带人工标签和来源记录。

## 12.2 强制数值验收门槛（目标不是已达成）

| 项目 | 本轮验收要求 |
|---|---|
| 原始消息 | 所有已成功提交的消息可追溯，重试不会新增重复主消息；故障后保持原数据不丢失 |
| 记忆去重 | 100 组标注同义事实合并准确率 ≥ 90%，并记录误合并/漏合并 |
| 高风险实体 | 指定 fixtures 中不同朋友、不同公司误合并为同一实体 0 例 |
| 时间关系 | 指定跳槽/改期/历史查询 fixture 100% 按有效时间正确回答 |
| 来源追溯 | 发布回忆/输出个人事实的来源 ID 100% 可查且归属当前用户 |
| 无向量检索 | 报告 Precision@k、Recall@k、MRR/Recall@1、P50/P95；事先定义可行达标阈值，开放式无实体名样本单列，不以简单样本 100% 冒充泛化 |
| 主动提醒意图 | ≥200 标注样本宏 F1 ≥ 0.85；隐含日程召回率 ≥ 0.90；提供混淆矩阵和置信区间 |
| 误提醒 | 未经确认建立正式提醒 0 例；否定/转述/取消高风险样本误建 0 例 |
| 幂等 | 重试、重放、刷新、重启不产生重复正式提醒和重复通知 |
| 回忆发布 | 无来源、无授权、来源被删的候选 0 例发布；AI 生成内容明确标注 |
| 用户隔离 | 跨用户记忆、图谱、提醒、回忆、来源或工作流串读 0 例 |
| 已有功能回归 | Rebuild 原有关键聊天、导航、登录、模型调用、回忆、提醒测试无阻断回归 |
| 正式通知 | 至少一个 Rebuild 实际可用渠道到时触发并有真实投递状态，不以 Mock 假装送达 |
| Graphiti 原生能力 | 无真实向量能力时诚实标 `BLOCKED_EMBEDDING`，不能写 PASS；其余主功能单独验收 |

F1、召回等统计指标必须保存测试集和失败样例，阈值在校准集调整，不能看最终测试结果后改样本或放宽门槛。**单元 Mock 允许，真实集成和云端评测必须另做，严格区分。**

## 12.3 必做 E2E 场景

**E2E-A：人物、初创公司和时间关系**  
D1 老朋友甲；D3 甲加入星火科技并邀请用户；D5 用户明确加入；D8 团队发展；D10 朋友乙加入云帆智能；D12 甲离职并到远山科技。核查“创业的朋友有几个”“是否同事”“甲目前在哪”“最初是谁邀请”“什么时候说过”“相关事实来源”。验证未来/过去、否定与指代不明。

**E2E-B：重复和纠错**  
数次说同一事实不新增重复主记忆；后续明确纠错保留版本与来源且当前查询不返回已过期陈述。

**E2E-C：日常话语识别提醒**  
“明天下午三点去社区做志愿活动”→出现建议卡→编辑事件与提醒时间→明确确认→数据库任务→独立调度→实际站内通知；拒绝不建任务，刷新、重启、修改、取消、重复提交正确。

**E2E-D：回忆**  
有证据的首个有意义经历优先；纯寒暄不凑数；不同时间窗去重；回忆页可回查已保存记忆和聊天；删除源证据后派生内容失效；AI 图像标记真实。

**E2E-E：混合故障与安全**  
Neo4j 故障、云模型超时/限流、用户撤销授权、前端刷新、网络断开、worker 或 scheduler 重启，保持消息安全、状态可恢复和用户隔离。

## 12.4 视觉交互验收

在 Rebuild 真实前端运行 Playwright；至少验证 390、430、768、1440、1920 宽度的布局、按钮可点击、弹窗不遮挡、状态提示、焦点恢复、键盘导航、加载与失败、通知层级、聊天输入；保留截图/录屏并标注构建版本。不要把旧项目的截图直接充当 Rebuild 验收证据。

---

# 13. 阶段划分、任务并行及停止条件

| 阶段 | 实际实施任务 | 必须产出 | 门禁 |
|---|---|---|---|
| P0 项目识别 | 三项目身份、真实 Git/服务/DB 审计，锁定 Rebuild 工作树 | `PROJECT_IDENTITY_AUDIT.md` | 无法确定 Rebuild 根目录则停写 |
| P1 现状与移植审计 | Rebuild 原生功能审计、旧成果逐文件筛选、基线测试 | `SELECTIVE_PORTING_MATRIX.md`、基线报告 | 不得全量复制旧项目 |
| P2 依赖及适配 | 正式接入 LangMem、Neo4j、LangGraph、APScheduler、Graphiti 适配器，锁版本和许可 | 依赖锁定、服务健康、接口实测 | 不得以安装代替真实业务使用；Graphiti 向量另记阻塞 |
| P3 记忆闭环 | 聊天持久化、LangMem 更新、权威记忆、Neo4j 时序、证据/无向量查询 | 业务实现与图谱/来源 E2E | 不能有跨用户读取或不同公司错误合并 |
| P4 主动提醒闭环 | 意图识别、建议卡、复用编辑、LangGraph 确认、APScheduler 调度与真实通知 | 意图评分、前后端 E2E、任务恢复证据 | 无确认建任务或重复投递必须 0 |
| P5 智能回忆闭环 | 时段候选、结构化评分、来源门控、原回忆页/生成流程 | 回忆验收、错误样例、截图 | 无来源/无授权发布必须 0 |
| P6 集成验收 | 全量回归、故障测试、运行环境迁移、源仓库完整性复核 | 总验收、部署说明、剩余风险 | 不能把部分通过宣称全部完成 |

允许在 P3/P4/P5 中对不共享数据库迁移的模块并行开发，但必须有接口契约、独立测试库和最终统一验收。任何子 Agent 接任务都要继承“Rebuild 唯一写入目标”和“旧项目只读”硬门禁。

本轮不仅需要报告状态，还应实际运行。普通可恢复的兼容性问题应在 Rebuild 中修复并继续；若遇未授权的破坏性操作、新收费供应商、无法定位目标仓库或用户数据越权风险，则停止相关操作，保存证据并明确询问。

---

# 14. 结果状态必须细分：不能一条 PASS 掩盖未完成事项

所有阶段和每个框架分别标记：

- `PASS`：在 **Rebuild** 真实运行并通过对应自动化、集成及 E2E；
- `PARTIAL`：核心功能可运行，但某些指标、渠道、场景未完成；
- `BLOCKED_PROJECT_IDENTITY`：无法核实唯一目标仓库；
- `BLOCKED_API_CONFIG / BLOCKED_MODEL_CAPABILITY`：云端模型/模型契约未配置或不支持；
- `BLOCKED_EMBEDDING`：Graphiti 原生需要向量而当前未配置合法向量接口；
- `BLOCKED_COMPATIBILITY`：真实依赖/接口冲突，有最小复现与日志；
- `UNVERIFIED`：旧执行记录宣称成功但未在 Rebuild 实测；
- `FAIL`：跨用户泄漏、未确认建提醒、数据污染、权限/授权缺陷等关键问题。

**最终项目可形成“无向量业务核心 PASS + Graphiti 原生向量能力 BLOCKED_EMBEDDING”的真实组合结论，但绝对不能宣称‘所有强制框架全部通过完整原生能力验收’。** 若用户将来补充向量 API，需再进行真正的原生 Graphiti 验收。

---

# 15. 最终交付文档与代码清单

优先在 Rebuild 现有文档布局内整合，以下是内容要求而非强制覆盖目录；若没有约定，建议：

```text
LifeCompanion-Rebuild/
  docs/
    product/v0.2/intelligence/
      PROJECT_IDENTITY_AUDIT.md
      REBUILD_BASELINE_AUDIT.md
      REBUILD_EXISTING_CAPABILITIES.md
      REBUILD_ARCHITECTURE_DECISIONS.md
      SELECTIVE_PORTING_MATRIX.md
      PORTED_SOURCE_MANIFEST.md
      DATA_MODEL_AND_MIGRATION.md
      MODEL_ROUTING_AND_PRIVACY.md
      NONVECTOR_RETRIEVAL_ACCEPTANCE.md
      GRAPHITI_NATIVE_CAPABILITY_STATUS.md
      MEMORY_ACCEPTANCE.md
      RECOLLECTION_ACCEPTANCE.md
      REMINDER_ACCEPTANCE.md
      E2E_VISUAL_ACCEPTANCE.md
      FULL_REGRESSION.md
      DEPLOYMENT_WINDOWS_UBUNTU.md
      FINAL_HANDOFF_AND_RISKS.md
  <适配现有代码层级>/memory/
  <适配现有代码层级>/graph/
  <适配现有代码层级>/recollection/
  <适配现有代码层级>/reminders/
  <适配现有代码层级>/inference/
  <适配现有代码层级>/tests/
  <适配现有基础设施层级>/compose.intelligence.yml
  <适配现有脚本层级>/verify_project_identity.*
  <适配现有脚本层级>/seed_synthetic.*
  <适配现有脚本层级>/evaluate_memory.*
  <适配现有脚本层级>/evaluate_reminders.*
  <适配现有脚本层级>/verify_deployment.*
```

必须交付：

1. **唯一目标仓库的身份确认结果**、旧项目只读证明、变更前后目录/文件哈希校验；
2. Rebuild 当前架构审计、已有开源集成清单和架构选择原因；
3. 原代码来源及**逐文件移植决策**，移植差异、许可证及来源声明；
4. 真正落地的 LangMem、Neo4j、LangGraph、APScheduler 业务接口与 Rebuild E2E；
5. Graphiti 真实适配器、版本兼容性验证、原生向量能力阻塞原因与后续接入门禁；
6. 长期记忆、图谱、回忆和提醒的结构化数据与有来源的真实运行实例；
7. 当前会话云端模型路由、预算与权限检查、API 失败恢复与日志；
8. 真实前端交互、截图录屏、五种视口测试、移动端状态确认；
9. Rebuild 独立数据库迁移/备份恢复、离线测试数据和自动化测试；
10. 真实评测指标、混淆矩阵、失败样例、资源与成本统计、全量回归；
11. Windows → Ubuntu 容器化部署说明；
12. Git 变更清单、依赖版本/开源许可清单和最终 `PASS/PARTIAL/BLOCKED` 明细。

**交付方式**：只在用户指定/审计确认的 Rebuild 隔离工作树中保存新文件和测试报告。未经明确授权不向远端 Push、不合并主分支、不部署公网、不修改两个源项目。确认要提交 Git 时仅在 Rebuild 工作树提交有明确范围的变更，不包含 secrets、用户数据和临时卷。

---

# 16. 给 Codex 的最终执行指令

你当前负责的是 **`LifeCompanion-Rebuild`**，不是 `Silver-economy-research`，也不是历史路径 `Silver-economy`。首先核实这几个名称对应的真实仓库和运行服务；旧项目及旧隔离工作树只能以只读方式检查，不能继续在那里开发。

在 **Rebuild 真实代码结构**基础上，强制接入并真实使用 **LangMem + Neo4j + LangGraph + APScheduler**，为 **Graphiti** 建立正式接入、真实兼容性验证与将来启用完整能力的门禁，绝不能伪造无需 Embedding 的 Graphiti 原生混合检索已运行。首期使用**已配置的当前会话云端模型**完成所有语义任务，**不部署任何本地模型，不假定任何新的 API Key**；没有 Embedding 时用 Neo4j 关系/时间/全文检索把主要业务做通，原生 Graphiti 向量链路保留 `BLOCKED_EMBEDDING` 并诚实报告。

旧轮 Codex 在 `Silver-economy/.work/intelligence-20261103` 等位置开发的成果可以**选择性参考或移植**，但必须先对照 Rebuild 已有成熟框架、逐文件查证、评分和记录决定，优先移植纯业务逻辑、测试样本、证据约束及适配算法，不得把旧项目整体复制或覆盖 Rebuild。

真正解决两项问题：**“聊天 → 可合并且可追溯的长期图谱记忆 → 有意义且有证据的回忆”** 和 **“自然语言日程 → 主动建议 → 用户编辑确认 → 持久化提醒 → 实际通知”**。逐阶段运行、修复、回归和交付，不得用原项目历史测试数字冒充 Rebuild 验收；遇到项目归属不明、跨项目写入或用户数据风险，立即暂停相关动作并明确报告。

**以本任务书所有阶段门禁及最终可复核证据作为唯一完成依据。**

---

# 17. 官方技术参考（供 Codex 锁定实际版本后阅读）

- Graphiti：<https://github.com/getzep/graphiti>；<https://help.getzep.com/graphiti/getting-started/quick-start>
- Neo4j 全文索引与查询：<https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/>
- LangMem：<https://github.com/langchain-ai/langmem>；<https://langchain-ai.github.io/langmem/reference/memory/>
- LangGraph：<https://github.com/langchain-ai/langgraph>；<https://docs.langchain.com/oss/python/langgraph/interrupts>
- APScheduler：<https://apscheduler.readthedocs.io/en/3.x/userguide.html>
- Docker Compose：<https://docs.docker.com/compose/>

> 注意：外部项目的最新版接口、许可证、兼容版本和模型适配方式可能变化。Codex 应以**它在执行时实际锁定和测试的版本**为准，保留文档与兼容性证据，不应根据旧任务书里的固定版本盲目安装。
