# A+ 真实语义评估证据入口

本目录全部用户内容为合成文本。评分为真实DeepSeek，生图调用0；整体PARTIAL。
参考由代理拟定、待真人复核。P04权重和Prompt未改，不以特定活动必须胜出为目标。

- [中文报告及逐场景对照](中文评估报告.md)
- [交互审查页面](review.html)：筛选S03、S11/S23、S12、S33查看关键案例
- [完整结构化对照](comparison.json)
- [独立中文开发验收](../../docs/development-log/2026-11-04_13-27_V03Aplus真实语义选择评估_开发验收.md)
- [冻结参考](frozen-cases.json)、[冻结清单](freeze-manifest.json)
- [调用前决策](decision-before-holdout.json)
- [后端225项日志](backend-final.log)、[JUnit](backend-final.xml)
- [工作区7项测试](workspace-guard.log)
- [浏览器检查](browser-checks.json)、[完整性检查](integrity-checks.json)
- [交付校验及文件哈希](delivery-manifest.json)

`request-budget.sqlite3`保存108个真实请求及响应（36基线、36复测、36两轴），
含请求ID、HTTP200、token usage，不含认证头；预算已耗尽，无自动重试。
`baseline/`、`retest/`和`axes/`保存逐场景输入和校验后的结果。
两轴4项非逐字视觉短语在原始校验中被拒，原始响应仍在账本，证据门处理在comparison中。

`harness-errors-before-egress/`、`red-*.log`及中途失败日志保留，不能当成模型准确率数据。
`before/`、`engineering-before.json`、`git-before.txt`、`librechat-before.txt`
用于保留原始业务基线与状态。

离线重生成报告：从指定工作树运行 `python scripts/report_v03_semantic_eval.py`。
浏览器截图：`node evidence/v03-stage-a-plus/capture-review.cjs`。
证据检查：`python evidence/v03-stage-a-plus/verify-evidence.py`。
Python使用项目既有P02虚拟环境；不删除账本，不用重复请求刷新评分。
