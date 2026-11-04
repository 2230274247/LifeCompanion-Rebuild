# 拾光视觉与交互规范

沿用已有 `apps/product-portal/portal.css` 的品牌视觉；统一 React 应用通过
`products/librechat-custom/client/src/components/Life/theme.ts` 将其映射到现有主题注册表。
优先复用 `@librechat/client` 的 Button、Spinner、侧栏与焦点行为，不引入新 UI 依赖。

| 角色 | 既有值 | 统一应用中的用途 |
| --- | --- | --- |
| 正文墨色 | `#1d2b25` | text-primary |
| 次级正文 | `#53635b` | text-secondary |
| 纸张 | `#f1ecdc` | surface-primary-alt |
| 浅纸张 | `#faf6ea` | surface-primary、聊天背景 |
| 阅读底色 | `#faf8f1` | presentation |
| 墨绿 | `#315a48` | 提交、强调、品牌标识 |
| 深墨绿 | `#203e32` | 强调悬停 |
| 银杏黄 | `#dfa61b` | 品牌图标 |
| 浅银杏黄 | `#f3d88b` | 导航选中态 |

正文优先 Aptos / Microsoft YaHei / PingFang SC；标题使用现有 serif 语义类。
中文品牌文案通过上游本地化入口维护，本轮新键只添加至 English fallback 文件，
保持上游 AGENTS 的本地化修改边界。

交互要求：

- 导航使用 React Router Link，保持同页路由，不新开标签、不嵌 iframe。
- 上游聊天保留加载、发送锁、中文组合输入、草稿、错误与滚动逻辑。
- 回忆区提供真实加载、空、失败重试、列表、详情及来源会话入口。
- 筛选写入 URL，列表滚动按当前用户与筛选条件保留在当前标签会话中。
- 桌面保留原侧栏；手机复用原移动抽屉，并在回忆页提供打开入口。
- 支持上游深色/高对比度模式，不新增非必要动画，保留 reduced-motion 行为。
- 按 390、430、768、1440、1920 CSS 像素检查布局；截图必须等待断点与抽屉动画稳定。

验收截图见 `evidence/v02-*.png`；具体通过状态与仍未验证的项目见独立开发日志。

V0.2.1 额外约束：

- 阅读区、弹窗、输入区通过既有语义 Token 统一；深色继承上游模式。
- 原始模型推理不渲染；当前没有可公开处理摘要 Provider，不显示空的摘要入口。
- 单一可用模型显示身份，不要求再选择；普通侧栏不显示 Agents/Skills/Prompts/原生 Memory。
- “记忆与权限”管理事实与分目的授权；“我的回忆”只展示已发布生活事件。
- 提醒主要从聊天创建；手动表单默认折叠，仅保留事项和时间；用户不选择唯一通知通道。
- 任务完成、取消、到期和 ntfy 接受分别展示；不得以“已提交”冒充设备送达。
- 真实五视口、暗色和弹窗截图见 `evidence/v02-memory-reminders/`。
  本轮没有系统中文 IME、真实手机键盘、全量键盘遍历或系统通知权限验收。

P04评分增量：普通用户看到中文任务状态、八维分数与理由，不显示原始
selection JSON；文字记录与AI图片标题分开。1440/390px及原消息跳转已实测，
撤权清除正文/候选；证据见`evidence/p04/scoring-55d9917195da4873/`。

P05天气卡增量：复用现有语义Token、Button和React Query，缺地点单字段，
同名候选由用户选择；结果展示天气估算说明、来源与查询时间。1440/390截图
见`evidence/p05/chat-7d8e052b61534996/`；真实失败截图保留在
`chat-76f66fdb58724835/`。未完成五视口、深色主题和真实设备IME验收。
