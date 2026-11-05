# 拾光 V0.3 UI/UX 专项测试报告

最终验证时间：2026-11-05 03:44（Asia/Hong_Kong）

项目：`H:\AI For research institute\LifeCompanion-Rebuild`

开发树：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103`

分支：`feat/rebuild-p00-p07-20261103`

根工作树 HEAD：`cdf3650ad595b81e64488a266a57176db37b29ba`

嵌套 LibreChat HEAD：`7c2365cb376b48acb1591e48a6ef91e5c47c78e6`

修改前备份：`H:\LifeCompanion-Rebuild-G1-Backups\20261104_230901`

## 结论

**UI-1 至 UI-6 视觉与交互专项：PASS。**

**写入型业务流程：NOT RUN，不记作 PASS。** 为避免修改真实回忆、提醒或权限数据，本轮没有触发创建、修改、取消、保存或外发授权请求；未执行项不冒充端到端业务验收。

**操作边界：PASS。** 本轮没有新增依赖、未修改 lockfile、未改 API/SSE/数据库/Vikunja/ntfy/Kolors/Agent 业务语义，未 commit、push、merge 或部署。

## Git 状态与越界核查

- 当前仍使用已登记的 V0.3 Worktree，未切换分支。
- 外层仓库仍为 `main`；实际开发位于 `feat/rebuild-p00-p07-20261103`。
- 嵌套 LibreChat 仍是原分支和原 HEAD，未执行 reset、clean、强制 checkout 或覆盖未提交文件。
- 以修改前备份逐文件 SHA-256 对比：本轮新增或变化为 **30 个 UI、测试、i18n、样式文件**。
- 按类型拆分：UI 源码/样式 **22 个**、UI 测试 **8 个**；业务逻辑修改 **0 个**；备份位于项目外，不计入源码变更。
- 嵌套 LibreChat 仍有 **48 个既存路径**相对 Git HEAD 显示修改或未跟踪，但它们与修改前备份的哈希完全一致，**不是本轮新增修改**。其中 12 个会直接影响业务协议或链路的基线文件为：
  - `api/app/clients/BaseClient.js`
  - `api/server/middleware/canDeleteAccount.js`
  - `api/server/middleware/canDeleteAccount.spec.js`
  - `client/src/hooks/Nav/useUnifiedSidebarLinks.ts`
  - `client/src/hooks/SSE/useEventHandlers.ts`
  - `packages/api/src/app/service.spec.ts`
  - `packages/api/src/app/service.ts`
  - `packages/api/src/index.ts`
  - `packages/data-provider/src/config.ts`
  - `packages/data-provider/src/index.ts`
  - `packages/data-provider/src/keys.ts`
  - `packages/data-provider/src/request.ts`
- 外层生命核心、数据脚本和 V0.3 历史成果未由本轮 UI 工作改动。

## 本轮变更文件

```text
client/src/components/Chat/ChatView.tsx
client/src/components/Chat/Header.tsx
client/src/components/Chat/Input/ChatForm.tsx
client/src/components/Chat/Landing.tsx
client/src/components/Life/Brand.tsx
client/src/components/Life/ChatSources.tsx
client/src/components/Life/Header.tsx
client/src/components/Life/Knowledge.tsx
client/src/components/Life/KnowledgeDetail.tsx
client/src/components/Life/Memories.tsx
client/src/components/Life/Moments.tsx
client/src/components/Life/MomentSettings.tsx
client/src/components/Life/Navigation.tsx
client/src/components/Life/ReminderDetail.tsx
client/src/components/Life/Reminders.tsx
client/src/components/Life/momentStatus.ts
client/src/components/Life/ui.tsx
client/src/components/Life/__tests__/Knowledge.spec.tsx
client/src/components/Life/__tests__/Memories.spec.tsx
client/src/components/Life/__tests__/MomentSettings.spec.tsx
client/src/components/Life/__tests__/Navigation.spec.tsx
client/src/components/Life/__tests__/V023.spec.tsx
client/src/components/UnifiedSidebar/ExpandedPanel.tsx
client/src/components/UnifiedSidebar/Sidebar.tsx
client/src/components/UnifiedSidebar/__tests__/ExpandedPanel.spec.tsx
client/src/components/UnifiedSidebar/__tests__/Sidebar.spec.tsx
client/src/components/UnifiedSidebar/mobile/Header.tsx
client/src/components/UnifiedSidebar/mobile/__tests__/Header.spec.tsx
client/src/locales/en/translation.json
client/tailwind.config.cjs
```

## 逐页结果

### UI-1：全局布局与导航

状态：**PASS**

- 聊天页只呈现一套 `life-chat-header`；回忆、提醒、设置只呈现一套 `life-site-header`。
- 保留原 LibreChat 移动侧栏、会话历史、会话菜单、收藏、分享、模型和后台任务能力。
- 顶部导航、桌面侧栏和移动抽屉具有不同可访问名称，避免重复 landmark 混淆。
- `moments/*` 归“我的回忆”；`moments/settings` 只归“设置”，选中状态无重复。
- 折叠桌面侧栏增加 `inert`，隐藏区域不再保留可聚焦控件。
- 移动抽屉保留 Marketplace、Switcher 和账户入口；选择 Life 目标后正常关闭。

### UI-2：聊天页面

状态：**PASS**

- 保留墨绿、纸张色和银杏黄品牌体系，未整体替换主题。
- 欢迎区改为稳定中文标题，修复多行裁切；增加品牌标识、眉题和支持文案。
- 聊天输入区域加宽，统一圆角、边框、底色和内部留白。
- 普通 LibreChat 模式继续使用原有布局和样式。
- 业务回执与状态文案做了可读化呈现；消息发送、SSE、持久化和记忆抽取逻辑未改。

### UI-3：我的回忆与图片展示

状态：**PASS**

- 回忆筛选、卡片、详情、空状态、AI 生成提示与来源区域完成视觉统一。
- 图片卡片使用约 3° 指针倾斜和径向追光；触摸端保持稳定，离开后重置。
- `prefers-reduced-motion: reduce` 下不产生 transform 或追光变量。
- 图片按装饰性内容处理，卡片或按钮已有可访问名称，避免重复朗读。
- 使用既有 image-fidelity fixture 验证真实图片布局；没有向业务库增加虚假数据。
- 实测活动态：`perspective(1100px) rotateX(0.9deg) rotateY(0.9deg) translateY(-2px)`；减少动效时 transform 为空。
- 倾斜追光只参考 [vibe-cards1](https://github.com/Jdb156158/vibe-cards1) 的交互效果，以现有 React/CSS 重新实现；没有复制源码、图片、字体或其他资源。
- 聊天来源与回忆卡片共用只读状态映射；后端枚举和 API 契约保持不变，界面将 `generated`、`pending_provider`、`private_text` 等原始值转换为中文可读文案。

### UI-4：提醒页面

状态：**UI 展示与交互 PASS；写入业务 NOT RUN**

- 提醒页头、通知授权、开通提示、创建入口、状态标签、编辑/取消按钮和详情完成统一。
- 真实提醒列表成功加载；已完成、已取消等状态可读。
- 手动添加提醒可通过键盘 Enter 展开和收起。
- 创建、修改、完成、取消、Vikunja/ntfy 投递未执行写入型测试，避免改动真实数据；原有 mutation 处理函数未改。

### UI-5：设置与自动回忆设置

状态：**UI 展示与控件 PASS；保存链路 NOT RUN**

- 记忆权限、敏感信息授权、外部处理授权和自动回忆设置完成分组与层级优化。
- 原有字段、开关语义、mutation 和查询键保持不变。
- 设置 disclosure 可用键盘 Enter 展开、再次收起。
- 接口返回不完整自动回忆配置时显示中文安全提示，不保存残缺配置。
- 真实权限保存、撤回和外部处理授权切换未执行；未据此宣称端到端功能 PASS。
- 知识详情中的原始 ISO 时间已按 `Asia/Hong_Kong` 显示；保留原始 API 值和枚举契约。
- 自动回忆设置已使用修改前备份和当前真实页面完成五个视口的前后截图。

### UI-6：响应式、动效与可访问性

状态：**PASS**

- 390、430、768、1440、1920 五个视口完成真实页面矩阵。
- 真实数据矩阵：40 个页面/详情、40 张截图。
- 图片 fixture 矩阵：10 个页面/详情、10 张截图。
- Header 重复 0、横向溢出 0、错误边界 0、页面脚本错误 0、图片失败 0。
- 最新 axe：20 次扫描、0 violations（8 个真实页面/详情 × 390/1440，以及图片回忆/详情 × 390/1440）。
- 导航 Enter 跳转成功，`aria-current` 与页面一致；移动 Tooltip 和移动抽屉开关正常。

## 最终测试

```text
focused Jest:        12 suites / 61 tests PASS
client typecheck:    PASS
scoped ESLint:       0 errors; JSON 文件仅触发“未匹配配置”忽略警告
Prettier check:      PASS
git diff --check:    PASS
production build:    PASS, 32.85s
real-data browser:   40 checks / 40 screenshots PASS
image fixture:       10 checks / 10 screenshots PASS
axe accessibility:   20 scans / 0 violations
Life API writes:     0
```

生产构建保留项目既有警告：`eval`、超大 chunk、Tailwind `ease-[…]` 歧义，以及 `Moments.tsx` 静态/动态混合导入。未归因为本轮 UI 回归，也未扩大处理。

## 截图证据

修改前基线（备份构建，不重新构建备份）：

- 真实数据页面与详情：`evidence/v03-ui-refresh/before-backup-final/`，40 张截图（脚本自动记录 36 张；旧版移动端提醒详情链接未稳定渲染，另用同一真实记录的直接路由补拍 4 张，原始 `before-report.json` 保留 36 条自动记录）。
- 图片 fixture 回忆与详情：`evidence/v03-ui-refresh/before-image-fixture-old/`，10 张截图。
- 聊天 1440：`evidence/v03-ui-refresh/before-backup-final/chat-1440x1000.png`
- 聊天 390：`evidence/v03-ui-refresh/before-backup-final/chat-390x844.png`
- 回忆图片 1440：`evidence/v03-ui-refresh/before-image-fixture-old/memories-images-1440x1000.png`
- 回忆详情 1440：`evidence/v03-ui-refresh/before-image-fixture-old/moment-detail-1440x1000.png`
- 提醒详情 390：`evidence/v03-ui-refresh/before-backup-final/reminder-detail-390x844.png`
- 知识详情 390：`evidence/v03-ui-refresh/before-backup-final/knowledge-detail-390x844.png`

修改后最终矩阵：

- 真实数据：`evidence/v03-ui-refresh/after-live-data-final-status/`
- 图片 fixture：`evidence/v03-ui-refresh/after-image-fixture-final-status/`
- 聊天 1440：`evidence/v03-ui-refresh/after-live-data-final-status/chat-1440x1000.png`
- 聊天 390：`evidence/v03-ui-refresh/after-live-data-final-status/chat-390x844.png`
- 回忆图片 1440：`evidence/v03-ui-refresh/after-image-fixture-final-status/memories-images-1440x1000.png`
- 回忆详情 1440：`evidence/v03-ui-refresh/after-image-fixture-final-status/moment-detail-1440x1000.png`
- 提醒 1440：`evidence/v03-ui-refresh/after-live-data-final-status/reminders-1440x1000.png`
- 提醒详情 1440：`evidence/v03-ui-refresh/after-live-data-final-status/reminder-detail-1440x1000.png`
- 设置 1440：`evidence/v03-ui-refresh/after-live-data-final-status/settings-1440x1000.png`
- 自动回忆设置 1440：`evidence/v03-ui-refresh/after-live-data-final-status/moment-settings-1440x1000.png`
- 知识详情 1440：`evidence/v03-ui-refresh/after-live-data-final-status/knowledge-detail-1440x1000.png`

## 开源组件、兼容性与许可

| 组件 | 已安装版本 | 许可证 | 本轮用途 |
| --- | --- | --- | --- |
| React | 18.3.1 | MIT | 现有页面与组件运行时 |
| Tailwind CSS | 3.4.1 | MIT | 品牌色、间距、响应式与状态样式 |
| Framer Motion | 12.40.0 | MIT | 受限的展开/过渡动效 |
| Lucide | 0.528.0 | ISC | 导航、按钮与页面语义图标 |
| Radix Dialog | 1.1.23 | MIT | 现有图片及弹窗交互 |
| Radix Dropdown Menu | 2.1.24 | MIT | 现有菜单交互 |
| Radix Switch | 1.2.5 | MIT | 设置和提醒开关 |
| TanStack Query | 4.36.1 | MIT | 现有只读查询、缓存与刷新 |
| `@librechat/client` | 0.4.82（本地包） | MIT（仓库 LICENSE） | 按钮、弹窗、Tooltip 等现有 UI 基础组件 |

- 新增运行时依赖：0；lockfile：未修改。
- [vibe-cards1](https://github.com/Jdb156158/vibe-cards1) 只作为“轻微倾斜 + 指针追光”的交互参考，没有复制其源码、资源、字体或依赖。
- GitHub 元数据目前显示 vibe-cards1 为 `NOASSERTION`，且仓库 `/license` 返回 404。若未来直接复用其代码或资源，必须先取得明确授权或确认许可证。
- `inert` 依赖现代浏览器实现；目标浏览器应覆盖 Chromium 102+、Safari 15.5+、Firefox 112+。旧浏览器仅影响折叠侧栏隐藏焦点，不影响页面可见布局。
- 新增 `font-display` 使用系统楷体候选链，不下载或分发字体；不同 Windows/macOS/Linux 设备的字形可能有差异。

## 遗留与风险

1. 提醒、权限、自动回忆的真实写入路径未测试，保持 **NOT RUN**；这是本轮测试边界，不是 PASS。
2. `/api/tags` 仍有既有 403，本轮矩阵出现 15 次；未隐藏，也未归因为 UI 回归。
3. 修改前构建不含本轮 `data-testid`，旧版 fixture 报告中的 `headerFailures` 表示测试钩子缺失，不是旧版视觉布局结论；截图与当前矩阵使用同一真实 fixture 数据。
4. 开发模式 React Query Devtools 可能遮挡右上角控件；矩阵仅在截图前移除该开发工具节点，生产构建默认不渲染。
5. 早前测试日志中曾出现测试凭据片段。本报告不记录具体值，但应轮换相关 fixture token 和验收环境凭据。
6. 未执行完整 SSE、MongoDB、Vikunja、ntfy、Kolors、Agent 或 P00-P07 全面业务验收。
7. Jest 控制台仍出现既有的 `act(...)`、Suspense、`asChild` 和负向网络夹具错误日志；61 项断言全部通过，但应另行清理测试夹具告警。
8. 本轮聚焦回归已纳入既有 `Life/__tests__/V023.spec.tsx`；未删除或弱化任何断言。
