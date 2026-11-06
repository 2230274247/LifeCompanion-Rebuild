# P04现有作业状态与安全修复

2026-11-04；状态PARTIAL。

| 状态 | 真实含义 |
| --- | --- |
| skipped | 已结算窗口没有被现有规则选中的候选；不出现在回忆列表 |
| queued | 已记录来源与文字，尚未执行 |
| generating | 原子claim后处理中；不是图片成功 |
| pending_provider | 没有可用图像配置，只有文字；不伪造图片 |
| generated | 旧代码已保存返回图片BLOB；真实文件/哈希验收尚未通过 |
| failed | 已知错误；是否能重试由服务端retry_allowed决定 |
| unknown | 可能已经被供应商接受，需查询原请求；禁止再次提交 |
| cancelled | 停用/撤权/来源失效/用户删除等终态 |

Core重启将generating转为unknown，不自动重提。
本轮retry API对unknown返回409 IMAGE_RESULT_RECONCILIATION_REQUIRED，
对其他不安全重试返回409 IMAGE_RETRY_UNSAFE。前端仅在retry_allowed=true时显示按钮；
旧服务端缺少字段时默认不显示，unknown有明确暂停/额度保护说明。

撤回memory_consent或image_consent时，同一设置请求同步取消本人回忆并清空
image/mime/caption/selection。列表和详情重新核查来源/授权，防止漏掉失效钩子。
来源删除、失效或改为敏感后，衍生内容也清除；在途返回不得恢复已撤权内容。
source_memory_ids保留为本人范围的审计引用，不保留已清除的正文。

旧cancelled行若仍有残留正文/selection/图片，读取时同样清除，
不会因已经是终态而跳过。撤权保持skipped状态，避免无内容窗口变成空相册卡片；
有真实HTTP故障注入验证，见legacy-privacy-5ca76114f3244c63.json。

仅关闭自动设置阻止后续任务；在独立授权仍有效时，已生成历史可以保留。
撤销生图/记忆授权则清除历史衍生内容。这两种用户行为分别测试。

当前作业、候选和图片仍共用moments行，独立候选/生成任务/资产、
调用成本、provider回执/安全恢复、文件生命周期及跨进程竞态仍须继续实现。

## 2026-11-04 评分作业增量

窗口现在先持久化为`awaiting_score`，再由`score_one()`原子claim为`scoring`；
同一窗口只允许一条`recollection_model_calls`记录。候选已拆分至
`recollection_candidates`（window/memory主键，来源revision、input hash、
八维、分数、eligible、理由、selected、版本），正文不重复存账本。

| 状态 | 新增含义 |
| --- | --- |
| awaiting_score | 有已核验候选，等待评分；无实际模型回执 |
| scoring | 已claim评分，重启时视为结果未知，不重提 |
| blocked_scoring | 预算关闭/达到、provider配置或输入上限阻断 |
| score_failed | 明确失败；本窗口已尝试，不在重启时自动重发 |
| score_unknown | 评分请求可能已被接受；需核查原请求 |

预算为0默认禁用付费评分，不降级关键词。预算按持久数据库全部
`recollection_model_calls`行计数，失败、超时、重启和重跑均占用额度；
同一窗口永远只有一个调用行。`BEGIN IMMEDIATE`在HTTP前预留，两个并发窗口
不能同时越过上限。

评分结果写回前再次比对全部候选当前revision/input hash、当前授权和权重；
撤权、撤回来源或窗口内任务删除会清空候选；在途结果不得复活正文。
未入选来源被撤回时，待评分窗口不变成空卡片。真实8031状态见独立日志，
图像`unknown`和计费回执仍未验收。
