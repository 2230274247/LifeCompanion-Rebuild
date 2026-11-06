# P04阶段记录

2026-11-04，Asia/Hong_Kong；状态PARTIAL，BLOCKED_IMAGE_PROVIDER。

主项目 `H:\AI For research institute\LifeCompanion-Rebuild`；
工作树 `.work\p00-p07-20261103`，分支feat/rebuild-p00-p07-20261103，
HEAD e2711c7b87367b39b0e2acdc88f4fb9fde01edf1。身份守卫逐命令PASS。
旧Silver、生产配置/数据库只读，未commit/push/merge/公网部署。

以下为01:55安全开发前的能力审计；当前评分状态见末节：

| 项目 | 分类 | 证据与判断 |
| --- | --- | --- |
| 持久事件/Memos/配置时间窗 | ALREADY_WORKING | SQLite、真实Memos API和本轮后台时钟触发 |
| 来源撤权清理 | PRESENT_BUT_BROKEN | 六项安全复现失败，已修复即时清理和读取复核 |
| unknown重试 | PRESENT_BUT_BROKEN | 旧接口可重提，现改409及前端无重试 |
| 八维模型评分 | NOT_IMPLEMENTED | 现有四维关键词不能冒充通过 |
| 独立图像适配器/私有文件哈希 | NOT_IMPLEMENTED | 当前仅旧直连/BLOB实现 |
| 可用已授权图像供应商 | BLOCKED | 当前DeepSeek聊天配置不是图像授权 |
| 100候选评测 | NOT_IMPLEMENTED | 未制造人工标签或成功指标 |

本轮补充权限与费用安全：独立目的授权、ordinary来源限制、撤权同步清空、
读时来源复核、在途结果不复活、unknown/5xx不盲目重提、服务端retry_allowed
控制前端。完整后端115通过，后续相关11项通过，前端6项及类型/构建/静态检查通过。
没有新增依赖或外部账户，本轮模型/图像调用0。

最终兼容补查已修复旧cancelled残留正文和skipped空卡片，
完整后端118 passed；实际HTTP证据legacy-privacy-5ca76114f3244c63.json。

真实运行证据和失败重测见MOMENT_E2E.md；
最终 `privacy-6be8c1bc45c34d49/privacy-live.json` 九项PASS、模型账本0、
清理错误为空；桌面/手机截图已查看，8031已安全重载最终兼容修复，
见core-reload-privacy-final.json。
独立中文日志：
`docs/development-log/2026-11-04_01-55_P04回忆撤权与未知请求额度保护_开发验收.md`。
不能宣布P04全阶段通过。

## 八维结构化评分增量

2026-11-04又完成`recollection-v1`：八维模型评分、精确原话/来源ID校验、
独立候选表、持久调用账本、默认预算0、失败/unknown/重启不自动重发、
旧四权重兼容、撤权/修订/删除在途丢弃。后端完整回归143 passed（1上游
弃用警告），最终增加来源撤回用例后完整144 passed；已完成聚焦38 passed；
前端8项、typecheck、data-provider、正式
build及scoped ESLint/Prettier退出0。

真实批次只新增1次DeepSeek请求：1,363 input/457 output token，3候选，
1入选，三来源经真实LibreChat HTTP与Memos读回，真实时钟03:02触发，
重启和重放未增加账本。证据见
`evidence/p04/scoring-7352368da5744a1b/scoring-live.json`。

MOM-01提升PASS；MOM-10仍UNVERIFIED；MOM-05仍BLOCKED_IMAGE_PROVIDER。
P04总体保持PARTIAL。独立日志：
`docs/development-log/2026-11-04_03-06_P04八维评分与持久额度保护_开发验收.md`。
浏览器证据`evidence/p04/scoring-55d9917195da4873/scoring-ui.json`：桌面/手机
3候选、24维度、1入选、原消息跳转与撤权清除PASS，模型生成请求0。
08:02后的最终复核见`scoring-complete-backend-regression.txt`、
`scoring-final-frontend-typecheck.txt`和
`evidence/p04/scoring-e8286ecbbce14cce/scoring-live.json`。
后者评分预算0，新增调用0；真实exclude API验证故障注入skipped窗口
不会变成空相册卡片，独立候选被清空。
