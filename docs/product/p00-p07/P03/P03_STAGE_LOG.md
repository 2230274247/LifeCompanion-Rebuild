# P03 阶段记录

日期：2026-11-04，Asia/Hong_Kong；状态 PARTIAL。

唯一主项目 `H:\AI For research institute\LifeCompanion-Rebuild`；
工作树 `.work\p00-p07-20261103`，分支 `feat/rebuild-p00-p07-20261103`，
HEAD `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`。各命令前身份守卫 PASS。
无 commit、push、merge、部署；旧 Silver 与生产配置/数据未写入。

实现包括既有成熟适配器上的草稿、来源 API 修正、持久 LangGraph 状态记录、
独立 APScheduler/SQLAlchemy JobStore，以及本轮四项投递恢复修复。
依赖元数据：APScheduler 3.11.3、SQLAlchemy 2.0.55、
LangGraph 1.2.19、SQLite checkpoint 3.1.3，均记录 MIT。
上游镜像、NOTICE 及安全审计仍须沿 P00/P07 门禁补全，安装不算集成验收。

隔离 Compose 为 `lcr-acceptance-20261103`：LibreChat 3091、网关 3031、
Core 8031、Vikunja 3461、ntfy 8097；恢复测试另启临时本机 Core 和独立 SQLite，
不触碰正式库。scheduler 验收进程结束后已退出，不能声称已常驻运行。

| 验收 | 结果 |
| --- | --- |
| 修复前聚焦复现 | 4 failed，保留 delivery-recovery-before.txt |
| 修复后提醒聚焦 | 15 passed |
| 修复前完整后端基线 | 84 passed，pip check 无冲突 |
| 修复后完整后端回归 | 88 passed，1 个上游弃用警告 |
| 真实提醒 CRUD / 重启 / 隔离 | PASS，live-reminder-lifecycle.json |
| 真实来源与仅补时间 | PASS 于 API 范围，draft-live.json |
| 真实到期 / 故障退避 / scheduler 重启 | PASS，delivery-recovery-0f6f567301144310.json |
| 浏览器 Chip | PASS 于合成持久消息范围；桌面键盘/390px 触摸、创建、取消、刷新、重新登录 |
| 真实跨账号读写矩阵 | PASS；permissions-live.json，9项检查、本人状态未变 |
| 本轮 DeepSeek / 生图请求 | 0 |
| 设备实际收到 | UNKNOWN |
| 完整 LangGraph 业务节点 | PARTIAL，目前只是 checkpoint 记录 |
| 200 人工标注意图评测 | UNVERIFIED |

需求逐项边界见 [REMINDER_E2E.md](REMINDER_E2E.md)，
投递状态见 [NTFY_DELIVERY_EVIDENCE.md](NTFY_DELIVERY_EVIDENCE.md)，
独立中文开发日志见 `docs/development-log/`。未达到 P03 全阶段 PASS 门槛；
继续补齐编排和产品路径，不以局部 PASS 代替全部验收。

## 2026-11-04 01:10 后续增量：业务编排与误创建排除

此节替代上文“仅 checkpoint 记录”的当前状态判断，前节保留为历史。
LangGraph版本2已用持久interrupt/resume驱动补信息、授权、提交、改期、
取消与未知结果恢复。真实业务集成八项检查通过；新后端浏览器桌面/手机
创建取消刷新重登通过。误创建缺陷先复现再修复，11条负向真实HTTP不新增
任务或草稿，2条正向真实创建。最新完整后端108 passed、1上游弃用警告。

证据：`business-workflow-a27b9a639da042f9.json`、
`business-ui-995bd011bc444bc0/business-backend-proof.json`、
`intent-guard-live-c35a53792bc046b9.json`、`business-and-intent-final-regression.txt`。
常用8031已重载，`core-reload-business-workflow.json`证明配置未变、
模型账本0→0；不是生产部署或scheduler常驻证明。初次20秒provisioning超时
保留，确认原库账号最终ready后复用原库重测通过。新增DeepSeek/生图调用0。

本阶段继续PARTIAL。独立日志：
`docs/development-log/2026-11-04_01-10_P03持久业务编排与否定误创建修复_开发验收.md`。
