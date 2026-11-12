# 记忆召回压力验收证据

本目录存放2026-11-09的合成历史召回与泛化验收证据。全部内容为合成语料，不含真实用户聊天、个人资料、服务凭据、JWT或密码。运行账号口令与token只位于gitignored的 `infra/runtime/memory-load/`。

## 数据与账号

- `dataset.json`：400条合成生活/工作/学习记忆，四时段各100条；40个历史会话；144个主验收问题（120个带日期改写、24个不限日期）；每条含唯一key、记忆与事件ID、来源会话ID、gold问题。回忆候选用 `selected_for_publication` 标记，与实际发布状态 `published` 区分。
- `accounts.json` 不在此目录；它位于运行时目录，含隔离owner/outsider账号凭据。

## 检索与召回

- `recall-baseline-058.json`：BGE-small模型、0.58阈值首轮真实HTTP结果。144题命中44题，作为校准前失败基线保留。
- `recall-large-before-time-normalization.json`：BGE-large、0.48阈值、日期未与语义内容分离时的结果，命中92/144。
- `recall-report.json`：最终144题，top1=120、top8=121（84.0%）；四时段各25/30，不限日期21/24；上下文指代3/4、相对时间4/4；10个无关问题误返回0；556项机制与权限检查无失败。P50=1257.21ms、P95=2200.84ms。23题未命中仍保留；检查通过不等于召回质量满分。
- `source-api-report.json`：四时段各一条来源会话，通过真实 `GET /api/messages/:conversationId` 确认来源消息可读，每会话10条。
- `real-chat-report.json`：最终串行实测，隔离owner通过真实DeepSeek在两个新对话分别询问一天前、一个月前的记录；2/2含对应事实与可点击来源链接，新会话ID不同于原历史会话。
- `real-chat-concurrent-timeout.json`：完整回归并行占用CPU期间的失败记录，2题中1题召回超时（遥测3606ms），模型未获得事实；保留该失败，不以之后串行成功覆盖高负载风险。
- `verification-summary.json`：后端253通过/1跳过、网关3通过、Git治理24通过，以及浏览器401认证边界实测；无全量云端输入抓包。
- `publication-report.json`：32条候选经真实 `POST /api/v1/memories/publish` 发布尝试，32/32返回502 `MEMOS_PUBLISH_FAILED`；底层错误为 `MEMOS_WRITER_MISMATCH`（owner没有逐用户Memos PAT，life-core回退到全局管理员token，身份不匹配）。逐条事件已置为 `failed`，召回不受影响，重试可恢复。

## 模型与阈值

- `model-comparison.md`：三模型（BGE-small、multilingual-e5-small、BGE-large）与cross-encoder在100正例+24负例上的离线比较；说明校准边界、固定revision、许可证、兼容性修复和保留的失败记录。
- `bge-large-score-audit.json`：选定模型逐题分数与top8，含阈值扫描。
- `e5-score-audit.json`、`reranker-score-audit.json`：未接入生产的对照实验，完整保留。
- `model-licenses.json`：各模型官方license与revision。

## 状态边界

- `published=0`、`selected=32`：32条回忆候选已选且SQLite事件存在，但发布尝试因 `MEMOS_WRITER_MISMATCH` 失败。要正式发布需为隔离owner开通逐用户Memos PAT（`scripts/provision-memory-load-memos.py`），该操作需管理员服务凭据并写入共享令牌文件，被自动审批以 `Sensitive-Source Provenance`、`Secret-Store Writes`、`Credential Exploration` 拒绝。未绕过；发布完成前不可标记为已发布。
- 历史来源会话endpoint字段修正受到 `Modify Shared Resources` 自动审批拒绝；40个合成历史会话仍保留旧标签。四时段来源API均返回200，每个抽查会话10条消息；不将此等同于旧会话可直接继续聊天的验收。
- 当前真实聊天诊断 `extractor_configured=false`；本轮采用系统注入，不能证明云端多事实抽取已在运行环境配置完成。
- 本目录只提交合成内容与无秘密报告；模型权重、运行账号、真实数据库和聊天事件原文不进入Git。
- 整体状态为PARTIAL。模型校准与主验收题集有重叠，不能宣传为独立盲测准确率。
