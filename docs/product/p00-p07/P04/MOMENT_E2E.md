# P04真实验收与未通过项

2026-11-04；总体PARTIAL，真实图像Provider阻塞。

本轮仅在Rebuild隔离服务和合成账号/独立SQLite执行。
模型与图像Key在临时Core为空，未发起云模型/生图请求。

后端完整回归115 passed、1上游弃用警告；
另补“关闭自动设置保留已授权历史/撤权再清除”后相关11项聚焦通过。
之后补旧取消行遗留正文和skipped空卡片两个复现并修复，
最终完整回归118 passed、1上游弃用警告（privacy-final-backend-regression.txt）。
前端6项聚焦测试正常退出；client typecheck、正式build、
data-provider build、改动文件ESLint/Prettier均退出0。
关闭无关全前端覆盖率收集重跑，保留首次进程中止记录。

实际脚本：`scripts/acceptance_p04_privacy.py`与
`scripts/acceptance_p04_privacy_ui.cjs`。验收内容包括真实Memos读回、
自定义时刻由Core后台按真实时钟触发、无图像配置文字状态、
跨账号拒绝、注入在途状态后重启unknown、409拒绝重提、
桌面/手机页面、撤权后清除及再次重启。
注入在途状态不是实际供应商超时；内部合成来源不是浏览器真实聊天。

首次脚本在未映射第二账号上错误期待404；补齐映射后实际读/重试/删除均404。
第二次浏览器因构建后未重载Express、引用旧JS 404而失败；
保留 `frontend-cache-before-reload.json`，仅重载隔离LibreChat修复。
第三次桌面通过，手机按innerText检查完整原文失败；
改用可见文本等待及textContent核验源文字，保留原报告。
最终整轮运行 `6be8c1bc45c34d49` 退出0、九项检查PASS：
`evidence/p04/privacy-6be8c1bc45c34d49/privacy-live.json`。
配置结束时刻02:23/02:25/02:27，实际02:23:07观察到第一窗文字任务，
随后实际Core重启、unknown防重提、1440/390px浏览器与撤权刷新通过。
截图unknown-1440.png、unknown-390.png、revoked-390.png均已实际打开查看，
无图片元素、无重试按钮、手机无横向溢出，撤权后原回忆正文不再显示。
这证明真实文字/安全路径，不证明智能评分、真实图片或供应商计费行为。
model_call_rows=0、cleanup_errors为空，临时Core/网关/浏览器已退出。

常用隔离8031也已安全重载最终兼容修复，证据 `evidence/p04/core-reload-privacy-final.json`：
DeepSeek配置文件未变，模型调用账本0→0、记忆任务5条均succeeded、
图像授权用户0；不是生产或独立scheduler部署。

最终旧行补查：`evidence/p04/legacy-privacy-5ca76114f3244c63.json`。
在已核验测试库注入旧cancelled正文及空skipped行，经真实HTTP读回清理，
重复撤权后skipped不出现于列表；模型账本0，未插入假图片。
首次失败分别保存在privacy-legacy-before.txt和privacy-skipped-before.txt。

| ID | 当前状态 | 实际边界 |
| --- | --- | --- |
| MOM-01 | PARTIAL | 来源门可运行；四维关键词不是八维模型评分，未通过候选智能筛选 |
| MOM-02 | PARTIAL | “晚安”真实拒绝；完整无内容时窗/混淆集待验 |
| MOM-03 | PARTIAL | 授权前启用403、撤权同步清除；真实图像Provider调用边界仍BLOCKED |
| MOM-04 | PARTIAL | 自定义时刻真实后台触发；默认11点/跨日/DST/常驻仍待补 |
| MOM-05 | BLOCKED | 没有真实文件、哈希和供应商元数据 |
| MOM-06 | PARTIAL | moments代码没有通知调用；真实图像完成后的静默体验未验 |
| MOM-07 | PARTIAL | 文字详情与来源记忆ID；真实图像和完整原消息点击待验 |
| MOM-08 | PARTIAL | 实际SQLite/Core重启unknown、409防重提；供应商幂等/重试未验 |
| MOM-09 | PARTIAL | 设置撤权及来源失效清理；物理图片/删除消息传播仍待验 |
| MOM-10 | UNVERIFIED | 无100条已复核评分评测 |

仍有界面文案缺口：列表/详情尚直接显示部分内部状态词，
取消态的无图提示、文字版/图像版标题与时段日期格式仍需改进；
本次截图只证明上述安全行为与可读性，不把产品文案验收提升为PASS。

## 2026-11-04 八维评分真实增量

新增脚本`scripts/acceptance_p04_scoring.py`与
`scripts/acceptance_p04_scoring_ui.cjs`。首个真实运行
`evidence/p04/scoring-7352368da5744a1b/scoring-live.json`包含5项后端PASS：

1. 三条消息由隔离Mongo持久化，经LibreChat认证消息API确认owner、原文和
   user消息身份，再经真实Memos接口读回来源。
2. 配置窗口03:02/03:04/03:06由Core真实后台时钟结算，不是直接调用未来schedule。
3. 真实DeepSeek返回3个八维候选，1个入选；候选理由、来源message ID、
   精确原话在独立候选表与详情中可复查。
4. 跨账号详情404。
5. Core重启保持结果，同窗口及达到持久上限的后续尝试被拒绝；
   scoring账本新增1，记忆抽取/图像调用0。

浏览器运行使用持久账本的SQLite备份，避免撤权验证破坏额度证据；
它不发生评分或聊天模型请求，并核验1440/390px可读性、3候选/24维度、
1入选、无图片、无内部状态词、无横向溢出、知识详情到原消息对话跳转、
撤权后正文和候选证据清除。截图包括`scored-1440.png`、
`scored-390.png`、`scoring-revoked-390.png`。

本轮后MOM-01为PASS；MOM-07的来源到原消息浏览器路径已补验，
但真实图像文件、图像供应商回执及真实图片详情仍使MOM-07保持PARTIAL。
MOM-05仍BLOCKED，MOM-10仍UNVERIFIED。
