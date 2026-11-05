# 拾光视觉与交互规范

V0.3 审计说明（2026-11-04）：附件的赤陶/Ember 概念图只用于图文布局参考，
下表与既有 `Life/theme.ts` 仍为当前视觉依据。优先复用上游 Image/DialogImage，
触屏与认证媒体适配待阶段 C 验收；V0.3 不实现微光/镭射动效。
见 [审计](../product/v0.3/仓库审计报告.md) 与 [实施计划](../product/v0.3/实施计划.md)。

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

## Otis 应用内宠物（2026-11-05）

- 交付形态是**页面内**角色：只在聊天路由出现，`position: fixed` 在右下
  （右 16 / 下 136），200×256，位于输入框下方之外；< 900px 隐藏。
- 形象来自作品集原版 Otis：钴蓝圆盘 `#2f4bf0`、暖橙色头发与芥末黄高领毛衣；
  200px 脸居中，底部是 184px 半透明心情条，折叠后为 54px 圆头像。
- 角色**保留 Otis 自己的配色**，不套主产品的雾青苔绿 Token；心情条本身用语义类
  （`bg-surface-primary/85`、`border-border-light`、`text-text-primary`、
  `text-text-secondary`），深浅色主题都成立。
- 心情条上下两行：8px 大写字距标签 `CURRENT MOOD` + 11px 心情词；
  耐心条 4px，颜色随耐心从钴蓝过渡到红。
- “pull my face” 手写体提示旋转 6°，放在脸的左上方空白处（避开深色头发），
  第一次成功拉拽后淡出。
- 表情切换由原引擎的 90ms 交叉淡入完成；抓取、回弹、脸红与耐心都在 WebGL2
  片元/顶点层，不用 CSS 动画伪造。`prefers-reduced-motion` 下关闭提示、
  抓取圆环与耐心条过渡。
- 纯指针交互，不做键盘焦点环，也不为宠物增加额外按钮层级；折叠/关闭按钮
  是真实 `<button>` 并带 `aria-label`。
- 上一轮的 380×420 Electron 桌面窗是可选实验，设计记录保留在
  [桌面宠物置顶窗](../architecture/PET_WINDOW.md)，不再作为交付形态。

V0.2.1 额外约束：

- 阅读区、弹窗、输入区通过既有语义 Token 统一；深色继承上游模式。
- 原始模型推理不渲染；当前没有可公开处理摘要 Provider，不显示空的摘要入口。
- 单一可用模型显示身份，不要求再选择；普通侧栏不显示 Agents/Skills/Prompts/原生 Memory。
- “记忆与权限”管理事实与分目的授权；“我的回忆”只展示已发布生活事件。
- 提醒主要从聊天创建；手动表单默认折叠，仅保留事项和时间；用户不选择唯一通知通道。
- 任务完成、取消、到期和 ntfy 接受分别展示；不得以“已提交”冒充设备送达。
- 真实五视口、暗色和弹窗截图见 `evidence/v02-memory-reminders/`。
  本轮没有系统中文 IME、真实手机键盘、全量键盘遍历或系统通知权限验收。
