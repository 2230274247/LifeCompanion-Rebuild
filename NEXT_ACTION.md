# 下一执行点

## 人工暂停检查点：2026-11-04

**PAUSED_FOR_USER_REVIEW**

唯一主项目`H:\AI For research institute\LifeCompanion-Rebuild`；
实际工作树`.work\p00-p07-20261103`，分支`feat/rebuild-p00-p07-20261103`。
用户已将本轮边界改为“完成当前P05天气收尾及进度报告后立即暂停”。
**未经下一次明确授权不得自动恢复，不开发路线、搜索、语音、主动回访、
P06或P07。下方旧计划仅为历史记录，不是当前执行指令。**

- 先读[当前开发进度与遗留问题审计报告](docs/product/LifeCompanion-Rebuild_当前开发进度与遗留问题审计报告_2026-11-04.md)。
- 天气1440/390真实选择/结果/刷新/清除通过；后端167、前端9、
  原生桥接最终7、网关/日志安全5通过。完整模型聊天新轮次仍未验。
- 最终审计`evidence/p05/chat-delivery-audit-r2.json`；
  累计补丁以`patches/librechat-v0.8.8-rebuild-p00-p05-weather-chat-r2-20261104.patch`为准。
- 固定库`infra/runtime/p05/tools-acceptance.sqlite3`累计公开HTTP **6/6**，
  不是旧记录中的4。交互已cancelled、正文清空，额度不退回；
  不可直接重跑`--resume-source`或换库重置预算。
- 原DeepSeek地址/Key不变；去重成功账本13次，输入35119/输出2236 tokens；
  天气增量及本次审计新增模型0。精确费用/当前余额UNKNOWN。
- 无残留验收进程/运行天气工具，稳定隔离服务和数据保留。
  常用Provider仍默认关闭、预算0，不是生产天气已开放。
- 经授权后先继续P05天气完整发送聊天、日期/故障/预算浏览器验收；
  入口`docs/product/p00-p07/P05/P05_E2E.md`、
  `services/life-core/app/tool_chat.py`和嵌套`ToolCards.tsx`。
  需要新真实请求时先明确累计小额预算。

## 以下为暂停前历史检查点

当前项目：`H:\AI For research institute\LifeCompanion-Rebuild`  
当前阶段：P04安全与真实八维评分增量已验收，状态PARTIAL；
P00-P03尚有未关闭项，P05-P07未完成。

下一优先执行：P05原生LibreChat工具/语音/回访审计与开发，复用现有
Tool Registry、Agent/MCP与P03调度/outbox。P04的图像Provider、100候选人工
复核和跨日长期验收单独保留，不将全阶段宣布完成。
继续使用既有DeepSeek；人物关系12次预算不复跑。P04评分已新增1次请求
（1,363 input/457 output token），截图/回归复用结果不重复调用。
没有授权图像provider时不调用旧智谱聊天Key生图、不新开付费账户。

1. 浏览器Chip最终已PASS：桌面键盘/390px触摸、取消刷新和重登；权限矩阵9项已PASS。
   此脚本阻断生成端点，使用合成Mongo原话/助手夹具，不等同于真实发送聊天。
   后续补原生聊天发送全链路时，需明确小请求预算。
2. LangGraph版本2业务编排已真实验收：补信息/授权/创建/改期/取消及unknown恢复；
   business-workflow-a27b9a639da042f9.json、新后端UI和8031重载已有证据。
   11条负向排除/2条正向真实HTTP通过，完整后端108 passed；本轮新增模型调用0。
   后续继续验证多进程竞态，不能将有限并发当作完整压力验收。
3. REM-02/03真实API时间语义已通过，补完整浏览器日期Chip与实际聊天来源路径；
   继续潜在日程/拒绝/第三人、多同名与改期、多进程矩阵。
   补200人工标注意图评测，未经人工复核的标签不能宣称人工标注。
4. 完成历史通知分页、上游读取失败审计、长期离线、取消与发送竞态和常驻调度部署验收；
   `LIFE_REMINDER_SCHEDULER_EXTERNAL=true` 只能在独立进程实际存活时启用。
5. 补 P02 LibreChat 记忆问答/来源点击、100事实+100检索及删除传播。
   人物/公司12天真实时序、乱序、重放和Core重启已通过，不重复消耗模型验收额度。
6. 既有 DeepSeek 地址/key不变，普通测试0模型请求；若必须真实生成，先设置小请求硬预算。
   当前真实关系验收已用12次，预算保护已证明后续HTTP发送0。精确费用UNKNOWN。
7. P04安全首轮已过：privacy-6be8c1bc45c34d49九项真实检查PASS；
   可配置真实时钟文字任务、Memos、重启unknown/409、1440/390px、撤权刷新已验。
   旧cancelled残留/空skipped卡片补查已修复并真实HTTP通过，最终完整后端118 passed，
   8031已加载最终代码；不要再次重做已通过时钟/UI验收浪费资源。
   继续八维模型评分、100候选评测、原消息点击、真实文件/哈希和provider适配；
   现有四维关键词不能据此通过MOM-01/10。DeepSeek聊天配置不是图像授权。
   原始状态词、文字/图片标题、取消态提示和时段日期格式仍需完善。
   Lighthouse LCP/TBT仍FAIL，Graphiti仍`BLOCKED_EMBEDDING`，终端通知仍UNKNOWN。
   保留缺口并继续P04-P07，不能宣布总体完成。

每个 shell 命令前在本 worktree 运行 `python scripts/verify_rebuild_workspace.py` 并确认退出码为 0。隔离 core 由 `scripts/acceptance_environment.py core-service` 启动；P02 Neo4j 由 `infra/compose.p02.yaml` 管理。旧 Silver 服务和数据只读。

构建前端后必须核验3091返回的脚本与client/dist/index.html一致；
Express缓存旧HTML时，只能在再次核验Compose标签/工作目录后重载隔离LibreChat。
不要用旧HTML的404误判业务逻辑；不要为聚焦Jest收集整个前端覆盖率。
P04/当前源码补丁：patches/librechat-v0.8.8-rebuild-p00-p04-20261104.patch，
其为累计差异而非本轮独有，真实index未改变。

02:37:39最终复核见evidence/p04/final-delivery-audit.json，源码12份哈希、
6份运行报告与常用服务健康均一致。这是01:55任务的历史检查点。

08:04后最新检查点：

- 八维真实批次：scoring-7352368da5744a1b，真实03:02后台3候选/1入选；
  硬预算2实际使用1次，重启和重放不增。MOM-01为PASS。
- 最终后端144通过，前端8项、最终typecheck/build/scoped lint通过。
- scoring-e8286ecbbce14cce真实桌面/手机/原消息点击、撤权及故障注入
  skipped窗口exclude API通过；重放Core预算0，新增模型调用0。
- 常用8031已核验监听PID/DB后重载，原配置未变、模型账本0→0，
  图像授权用户0；MOM-05仍BLOCKED，MOM-10仍UNVERIFIED。
- 下一从P05继续：已确认上游有Tool Registry、web_search、MCP和STT/TTS，
  当前固定DeepSeek custom endpoint，未配置mcpServers/speech/webSearch。
  必须先盘点provider与费用；上游源码存在不等于产品可用。
- 最新累计补丁：
  patches/librechat-v0.8.8-rebuild-p00-p04-scoring-20261104.patch，
  60文件/208236字节，SHA-256
  99ee49154b129c6555676671c5b1c7d311c296df11fb8cb6875556acccaf8eee；
  临时索引应用PASS，真实index未变。保留旧补丁，不再复跑评分请求。

08:35 P05执行检查点（优先继续此处）：

- 新增`app/tools.py`只读目录/执行/回执/删除API，Schema/出网约束、
  持久预算/幂等、24小时清除、在途删除/过期保护。默认provider空、预算0。
- 上游已有原生Tool Registry、web_search、MCP和speech；当前custom
  DeepSeek没有配置工具。Python MCP SDK未安装，不要误认为已有MCP服务。
- 固定库`infra/runtime/p05/tools-acceptance.sqlite3`已用4次公开GET：
  天气首次503、显式恢复天气1、路线1、地点1；没有任何模型调用。
  真实证据`evidence/p05/tools-live-f7efdd3a740b40bf.json`。
  公共API仅隔离研究，Open-Meteo非商业条款、OSRM无交通/SLA已记录。
- 完整后端157通过（tools-backend-regression.txt），后补在途删除/过期2项
  聚焦通过。不要把新2项计入157；无需重复已过完整回归。
- 地点实际返回多个Shanghai（包含其他国家），必须让用户选具体地点，
  不能自动选第一条。当前place_search明确requires_user_selection=true。
- 下一实际开发：复用`packages/api/src/memory/life.ts`持久消息业务边界，
  接入Core工具决策和回执，补地点/缺起点选择及来源卡、天气/路线→提醒草稿。
  不改DeepSeek地址/Key，不新造聊天引擎。普通聊天不弹工具卡。
- 目前临时API测试用户是`p05-public-landmark-tester`，并非LibreChat账号A；
  不能将其历史回执改owner后冒充真实登录/聊天E2E。新UI验收必须真实身份绑定。
  同库预算4已用完；现有回执可不出网回放，任何新公开API验收需明确少量
  新请求上限并保留累计账本，不能另建库重置预算。真实DeepSeek调用仍只新增1次评分。
- 搜索Provider、语音和回访未完成。六份P05文档/矩阵与独立日志已写；
  P05总体PARTIAL，不能因API通过宣布产品完成。
- 常用8031仍P04最终代码，不是P05；不要因磁盘有新端点就声称服务已部署。
  P04评分源码哈希快照为历史检查点；本次修改main/config/.env.example已知且有前快照。
- 独立日志：docs/development-log/2026-11-04_08-10_P05只读工具执行与真实Provider_开发验收.md。
