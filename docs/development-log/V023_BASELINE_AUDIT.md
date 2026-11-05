# V0.2.3 只读基线审计

日期：2026-11-03 14:35 起，Asia/Hong_Kong。阶段 A，不代表功能已修复。

完整读取用户任务书及本仓库开发、设计、产品、架构规范。任务书的截图推断作为待验证问题，
不作为根因或授权证据。根仓库 main/`e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`，
LibreChat `7c2365cb376b48acb1591e48a6ef91e5c47c78e6`；两者均有历史未提交修改，
未回滚、暂存、提交、push。基线哈希及文件状态见 `evidence/v023/baseline-audit.json`。

审计阶段只读源码、SQLite（mode=ro）和状态；SQLite backup API 将一致快照保存到
ignored `infra/runtime/v023/*-before.sqlite3`。不调用授权设置、创建提醒或历史补写接口。
生产库为 `services/life-core/data/life-core.sqlite3`，不是上一轮隔离库。

数据库确认：生产库 7 个事件、2 条 memory_items（1 事实、1 生活事件）、10 个提醒草稿、
6 条提醒；隔离库没有 memory_items。只统计行数/哈希，不输出聊天内容或用户凭证。
Memos/Vikunja/ntfy 的独立源码仓库均存在且干净，上一轮“没有源码仓库”的说法不准确。

本轮使用既有 `.venv/Scripts/python.exe` 在 life-core 目录运行 pytest：
49 passed，9.09s，1 条 Starlette 弃用警告。先前“缺少依赖”来自选错解释器，
不是项目环境永久阻断。后续阶段仍须重新验证改动。

只读复现：直接调用现有纯解析函数，不初始化数据库、不调用 LLM，输入任务书 A 与 MEM
示例。A 的 title/date/time/timezone 均为 null；两个未来携带事项均被分类为 future_plan
并退出。结果见 `evidence/v023/baseline-reproduction.json`。浏览器旧截图只是历史证据，
本阶段尚未重录 UI，不将其称为本轮截图。

历史授权异常：V0.2.2 的备份比较只证明一条 users.updated_at 和一条 memory_permissions
变化，不能证明“两个权限行”变化。旧服务没有授权审计事件表，不能可靠归因；保持原值。
本轮以新快照为边界对比，新增审计只能覆盖后续操作，不能追认旧操作。

实施顺序：

1. B：稳定实体详情、聊天来源入口；服务端仅补缺失项与一次选择提交；用隔离账号验真。
2. C：未来计划与已发生事件分型持久化，用户级多项检索、来源详情、删除/纠正一致性。
3. D：仅对已授权的真实持久化事件选择三时段候选，可靠任务与真实状态；缺少图片提供商
   时呈现待生成，不伪造图片、不启用真实用户授权。
4. E：本轮回归、浏览器、真实服务联调、数据差异、补丁与逐项验收。

阶段 A 结论：PASS（审计与纯函数复现）；浏览器复现未执行，功能仍未修复。
