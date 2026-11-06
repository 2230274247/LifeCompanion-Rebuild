# Rebuild 持续开发记录

日期：2026-11-04，Asia/Hong_Kong。

当前阶段：P04已完成首轮回忆安全修复与真实文字管线验收，整体PARTIAL；
结构化评分、真实图片及P05-P07仍须继续，P00-P03遗留门禁保留。

- 已完整读取 00、01、10、11、P00-P07、四份历史参考任务书和用户目标附件。
- 任务包 17 个清单文件的 SHA-256 全部匹配。
- 主仓库 `H:\AI For research institute\LifeCompanion-Rebuild`，Git common-dir 为其 `.git`。
- 主仓库 HEAD `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`，无 remote。
- 独立工作树 `.work\p00-p07-20261103`，分支 `feat/rebuild-p00-p07-20261103`。
- 保留原主仓库开始前的 82 条状态记录和 LibreChat 原有改动，未提交、未推送。
- 已实现 Python/PowerShell 身份守卫，并真实拒绝旧仓库和原工作区数据写入目标。
- 旧项目 551 个源码/文档、旧 intelligence 工作树 467 个源码/文档已记录哈希；
  research 根不是 Git 仓库，集合内部仓库仍需补全抽样清单。
- 现有后端本轮重跑 63 passed，网关 2 passed；不作为产品全流程 PASS。
- Docker 初始停止，启动后恢复了原 restart 策略容器。没有向旧服务执行测试、
  迁移或用户数据操作，但不能保证引擎恢复前后旧数据库字节未变化。
- 建立独立 Compose project `lcr-acceptance-20261103`；独立 Mongo、Memos、
  Vikunja、ntfy、LibreChat，独立网关 3031、core 8031，空数据库、全新应用密钥。
- 只复用 Rebuild 已配置模型供应商；未开通新账户或付费服务，未开启生图授权。
- 新增真实合成账号脚本；第六个注册触发上游默认 5 次限流，已在隔离 Compose
  将 REGISTER_MAX 明确设为 20，保留首次失败日志，原有配置不变。
- P00 独立验收日志与 73 项矩阵已完成；ROOT-02 仍 PARTIAL。
- P01 修复业务 Markdown 的整页/弹窗导航、传输失败后输入丢失及网关内部码展示。
- P01 使用真实 Zhipu glm-4.7 浏览器 Enter 发送 1 条合成消息；SQLite/Mongo 无关，LibreChat Mongo 查询确认用户/助手同会话持久行；刷新后独立浏览器可见。
- 五视口、记忆/提醒详情路由、停服故障恢复、八账号跨记忆/提醒详情 404 与非法令牌 401 均有实时证据。
- P01 前端错误组件 142 测试、SSE error handlers 37 测试、聚焦 UI 回归 33 测试、类型检查和正式前端构建通过。
- P01 总体 PARTIAL：没有授权回忆图资产；原生 Windows IME、所有模型 429/超时分支与完整登录生命周期未验收。
- Docker Desktop 曾再次停止；现已恢复隔离 Compose。它自动恢复旧项目容器的副作用限制 ROOT-02，旧数据库字节未获证明。

## 2026-11-03 P02 进度

- 已在 P02 专属虚拟环境安装 LangMem 0.0.30、LangChain OpenAI 1.7.3、Neo4j driver 6.4.1、Graphiti Core 0.31.2；`pip check` 退出码 0。
- 已启动 P02 独立 Neo4j Community 5.26.32（本机 `127.0.0.1:7688` Bolt、`:7475` HTTP）；认证、Cypher 查询和三项唯一约束实测通过。
- Life-core 真实使用现有 Zhipu `glm-4.7` 经 LangMem 结构化提取，来源原文校验通过；精确 token/费用不可得，记录 UNKNOWN。
- 增加 SQLite 实体、关系和图 outbox；Neo4j 投影、来源边、关键词候选检索、用户 namespace、撤回清除经真实隔离数据验证。
- P02 Live acceptance 实测跨会话 U盘/雨伞、否定限定词、未来计划纠正和历史保留、账户召回隔离、Core 重启恢复、Neo4j 撤回传播均通过。
- 一次真实查询暴露 U盘检索错误命中雨伞，已增加 topic filter；修复后完整 Live acceptance 通过。另一次 Neo4j Cypher错误也已修复。
- GraphitiProvider 已明确 fail closed；无 embedding 时状态 `BLOCKED_EMBEDDING`，没有制造向量或调用新 Provider。
- P02 仍 PARTIAL：LibreChat 用户聊天与来源点击、完整人员/公司 12 天时序、乱序/重放、消息删除/撤权全链路、100 事实+100 自然查询指标未完成。
- P02 日志、E2E、Schema、图一致性和 Graphiti 状态位于 `docs/product/p00-p07/P02/`；运行证据在 `evidence/p02/`。
- 独立隔离 core 已切换至 P02 venv 并在 `127.0.0.1:8031` 健康；其他 P00 隔离服务仍保留。旧 Silver 容器只读，未向其发请求或执行控制。
- 未 commit/push/deploy，无生产数据库/原始用户数据迁移。
- P02 增补真实 Neo4j 恢复测试：图撤回无孤立 evidence/entity/relation、跨 owner 保留、旧回执不覆盖新 generation、running 重启恢复、认证失败后恢复，共 7 项检查 PASS，无模型调用，见 `evidence/p02/graph-recovery.json`。

证据：`evidence/p00/`、`evidence/p01/`；密码、令牌和运行配置只在已忽略的 `infra/runtime/p00/`。

## 2026-11-04 DeepSeek 与 P03 调度恢复

- 大模型继续使用既有 DeepSeek 地址和原 key，当前隔离模型 `deepseek-flash`。
  未新建供应商、账户或付费服务；智谱历史失败记录保留。
- P02 人物/公司/邀请/就职六条真实 LangMem 事实、12天时序、乱序历史、
  重放、Neo4j 与 HTTP Core 重启验证通过。累计12次请求，
  输入33,756/输出1,779 tokens；精确费用 UNKNOWN。
- 数据库预算12达到后，第13次在HTTP前拒绝；本轮不新增模型生成调用。
- Lighthouse 性能门槛仍 FAIL：LCP 中位6,836.668ms >4,500ms，TBT也超预算。
- P03 新增持久 LangGraph checkpoint、APScheduler 3.x 独立 JobStore，
  真实CRUD/取消/更新/隔离和Core重启已有证据；LangGraph完整业务编排仍PARTIAL。
- 本轮先复现4项调度缺陷（4 failed），修复后聚焦15 passed、完整后端88 passed。
- 真实时钟到期时Core关闭，Vikunja通知保留；Core与独立scheduler恢复后，
  ntfy首次真实连接失败持久退避；再次重启后attempts=2 accepted。
  重放两次后ntfy缓存仍一条，改期/取消任务原时刻无投递。
- 设备实际收到 UNKNOWN；常驻scheduler尚未部署。全部P03脚本本轮模型调用0。
- 桌面Tab/Enter及390px触摸Chip真实创建、取消、刷新和独立重新登录通过；
  初始消息/助手为持久化合成夹具，生成端点未请求，不能冒充聊天全链路。
- 真实跨账号读写9项检查通过：8个正式任务/草稿操作返回404，列表返回空，
  原owner标题/时刻/状态不变。初始测试脚本路由错误保留，修正后重测。
- 独立日志：
  `docs/development-log/2026-11-04_00-55_P03提醒投递恢复与DeepSeek额度边界_开发验收.md`；
  七份P03交付位于 `docs/product/p00-p07/P03/`。P03整体PARTIAL，
  不把单次恢复或Mock结果作为全阶段完成。

## 2026-11-04 P03持久业务编排与否定误创建修复

- LangGraph从纯记录升级为版本2真实业务节点，interrupt/resume跨Core重启恢复。
  SQLite权威、授权、owner/revision、远程幂等和unknown查询恢复保留。
- 真实八项检查通过：3次并发确认仅1任务、改期原ID/版本、同值幂等、
  取消重启、两个时间语义、SQLite trigger真实故障后查询恢复不重复POST。
- 首次新用户provisioning20秒超时，核查原库最终ready后复用原库、等待45秒重测成功；
  不隐去失败，不重复开通。
- 新后端真实浏览器桌面键盘/390px触摸创建取消刷新重登通过，截图已查看；
  初始聊天为合成持久消息，没有浏览器实际发送云端聊天。
- 自动入口原先误处理否定/第三人，先复现9失败及补充2失败后修复。
  11负向真实内部HTTP零草稿/任务、2正向真实任务创建/清理通过。
- 最终完整后端108 passed、1上游弃用警告。新增DeepSeek/生图调用0。
- 隔离8031已核验监听PID和脚本后安全重载，新revision列生效；
  原DeepSeek配置文件未变，模型调用账本0→0，无待模型任务、无图像授权。
- 证据：evidence/p03/business-workflow-a27b9a639da042f9.json、
  business-ui-995bd011bc444bc0、intent-guard-live-c35a53792bc046b9.json、
  core-reload-business-workflow.json。P03仍PARTIAL；200人工标注、多进程、
  常驻scheduler、完整自然语言/浏览器聊天与终端送达仍未全部验收。
- 独立日志：docs/development-log/2026-11-04_01-10_P03持久业务编排与否定误创建修复_开发验收.md。
  未commit/push/merge/公网部署，保留既有改动，Silver与生产数据只读。

## 2026-11-04 P04回忆撤权与未知请求额度保护

- 先复现6项安全失败，修复授权撤回即时清空image/mime/caption/selection、
  列表/详情读取复核来源、敏感记忆授权不外溢到自动生图、在途结果不复活。
- unknown、HTTP408/5xx不再盲目重提；服务端409并返回retry_allowed，
  桌面/手机无重试按钮，有防重复额度说明。关闭自动设置和撤回授权区别处理。
- 完整后端115 passed，后补相关11项聚焦通过；前端6项、typecheck、build、
  data-provider构建、scoped ESLint/Prettier通过。新增依赖0。
- 最终又复现并修复旧cancelled行残留正文、撤权后skipped变空卡片；
  实际HTTP补查5ca76114f3244c63通过，最终完整后端118 passed，
  最终8031重载见core-reload-privacy-final.json。
- 真实运行6be8c1bc45c34d49九项PASS：Memos写入读回、来源、晚安拒绝、
  自定义02:23真实时钟后台结算、跨账号404、注入在途状态后Core重启unknown、
  409、防重提UI、撤权清空及再次重启一致。不是模型评分或真实图像证明。
- 保留首次未映射账号脚本错误、构建后未重载导致旧JS404、手机innerText
  换行断言失败，修复相应验收/运行问题后重跑通过；没有放宽业务权限。
- 全部P04运行模型/图像调用0。当前DeepSeek原地址/Key不变；
  8031已安全重载，配置摘要未变、账本0→0、图像授权用户0。
- P04仍PARTIAL，图像BLOCKED_IMAGE_PROVIDER；四维关键词不等于八维模型，
  100样本评测、独立候选/job/文件资产、图像Provider适配与原消息点击待补。
- 上游累计60文件补丁已归档并在临时index检查通过；继承原修改，真实index不变。
- 独立日志：docs/development-log/2026-11-04_01-55_P04回忆撤权与未知请求额度保护_开发验收.md。

## 2026-11-04 P04八维评分与持久额度

- 去掉四维关键词排序，新增recollection-v1八维、精确引用与质量门、独立
  候选表/请求账本、默认预算0、同窗只尝试一次及跨重启持久预算。
- 真实Mongo来源经LibreChat认证API与Memos读回，03:02后台真实时钟处理3候选，
  1件完成手写回忆录入选；DeepSeek新增1次、input1363/output457，图像调用0。
- 第一次完整回归143通过；后续中断只有50%不能计PASS。恢复后先复现
  “撤回无原话历史来源把skipped变空卡”失败，修复保留skipped后最终144通过。
- 前端8项、最终typecheck、正式build、data-provider、scoped lint通过。
  1440/390px候选维度、无图/可读状态、原消息跳转、撤权清除通过。
  真实exclude HTTP故障注入补查通过，重放预算0，新增模型调用0。
- 常用8031核验监听PID/隔离DB后重载，原DeepSeek配置文件未变，
  记忆模型账本0→0，5条任务succeeded，图像授权用户0。
- 上游累计补丁60文件/208236字节，临时索引应用PASS、真实index不变。
- MOM-01 PASS；P04总体PARTIAL，真实图像BLOCKED、100人工评测UNVERIFIED。
  不重复调用评分，继续P05工具/语音/回访，P06/P07未完成。
- 独立日志：docs/development-log/2026-11-04_03-06_P04八维评分与持久额度保护_开发验收.md。

## 2026-11-04 P05只读工具API增量

- 盘点上游原生工具/MCP/speech，当前Rebuild未配置搜索与音频Provider。
- 实现Core只读place_search/weather/route/search目录、严格参数、JWT隔离、
  固定出网、原子持久预算、幂等、脱敏错误、24小时清理与在途删除/过期保护。
- 真实天气首个HTTP503保留失败；同持久库显式一次恢复后天气/路线/地点成功，
  共4次公开GET，Core重启、同请求回放及预算/越权拒绝真实通过。
  地点多个同名候选须用户选择，未自动猜家庭位置。
- 后端完整157通过、1上游警告；新增2项在途删除/过期聚焦通过。
  新增DeepSeek/记忆抽取/回忆评分/图像调用0，没有付费账户或本地模型。
- 未触碰P04已过前端；P05暂无聊天/页面/来源卡/提醒联动、搜索、语音或回访。
  常用8031仍P04代码，P05只在临时Core验收。
- P05总体PARTIAL，独立日志和六份阶段文档/矩阵已更新；
  下一继续原聊天工具接入及地点选择，不把API增量替代完整目标。
- 独立日志：docs/development-log/2026-11-04_08-10_P05只读工具执行与真实Provider_开发验收.md。

## 2026-11-05 V0.3 UI/UX UI-1 至 UI-6

- 按最新纠偏边界仅处理 UI/UX，未扩展业务开发、历史 Bug、数据库或部署。
- 统一 Life Header 与四入口导航，完成聊天、回忆、提醒、设置及自动回忆设置视觉重构。
- 新增轻量倾斜追光图片组件，复用现有 React/Lucide/Tailwind/LibreChat 组件，新增依赖 0。
- 修复移动抽屉选择 Life 目标后不关闭的回归；聚焦 Jest 10 suites / 48 tests、
  typecheck、scoped ESLint、Prettier、production build 均通过。
- 浏览器五视口 25 个路由检查、26 张截图：Header 失败 0、横向溢出 0、
  错误边界 0、页面错误 0。
- 总体 PARTIAL：Life Core 8023 未监听，真实回忆图片、提醒列表和权限保存未联机；
  `/api/tags` 既有 403 保留记录。未 commit/push/merge/deploy。
- 测试报告：`evidence/v03-ui-refresh/UIUX_TEST_REPORT_zh-CN.md`。
