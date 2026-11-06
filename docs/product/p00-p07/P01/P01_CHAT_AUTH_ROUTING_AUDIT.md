# P01 聊天、身份與路由审计

日期：2026-11-03（Asia/Hong_Kong）
目标：`LifeCompanion-Rebuild` 隔离工作树 `feat/rebuild-p00-p07-20261103`

## 能力分类

| 能力 | 分类 | 本轮证据与结论 |
|---|---|---|
| LibreChat 真模型聊天与持久消息 | ALREADY_WORKING | P00 使用现有 Zhipu glm-4.7 完成 4 条真实会话；消息经真实 API 保存并重读。P01 增加浏览器 Enter 验收，结果见 `evidence/p01/enter-real-chat.json`。 |
| 统一 Shell 与 React 路由 | ALREADY_WORKING | 五视口登录截图、路由 200、无水平溢出；业务详情用 SPA 路由。 |
| Markdown 业务链接 | PRESENT_BUT_BROKEN → FIXED | 普通 Markdown `<a target="_blank">` 会开弹窗并显示原始 href；限制在已知业务详情 ID 的 `Link` 改为 React Router，浏览器实测无新文档请求且刷新/返回成功。 |
| 发送失败后输入恢复 | PRESENT_BUT_BROKEN → FIXED | 实际停止隔离 LibreChat 容器后，网关真实返回不可用；输入原文恢复至编辑框，刷新后仍存在。仅在草稿和待发送草稿都为空、普通首次发送时回填，避免覆盖用户新输入。 |
| 网关故障文案 | PRESENT_BUT_BROKEN → FIXED | 错误 JSON `{error: UPSTREAM_UNAVAILABLE}` 原样显示内部码；现按错误负载显示本地化暂时不可用提示。浏览器复测确认内部码不可见。 |
| 跨服务用户关联 | PRESENT_BUT_BROKEN / PARTIAL | LibreChat 与 life-core 的 8 个合成用户映射独立；身份由认证主体决定。七个其他用户对账户 A 的记忆和提醒详情请求均真实返回 404，伪造令牌返回 401。普通注册后的全自动 Memos/Vikunja 开通、注销/刷新生命周期尚未覆盖。 |
| Memos 独立用户身份 | PRESENT_BUT_UNVERIFIED | 8 个合成 Memos 用户及 PAT 在 P00 人工创建并隔离；本阶段没有验证用户自助生命周期或撤权。 |
| 回忆详情与图片 | NOT_IMPLEMENTED / BLOCKED_CONSENT | 测试账号 image_consent=false；没有调用生图服务，也不以空白路由或设置页冒充真实回忆资产。 |
| 原生系统 IME | UNVERIFIED | 浏览器测试模拟了 `compositionstart` / `isComposing` Enter / `compositionend`；没有声称验证 Windows 原生中文输入法。 |

## 修改

- `products/librechat-custom/client/src/components/Chat/Messages/Content/MarkdownComponents.tsx`：只把合规的 `/knowledge`、`/memories`、`/moments`、`/reminders` 真实 ID 链接渲染为 SPA Link；未知链接继续原行为。
- `products/librechat-custom/client/src/hooks/SSE/useEventHandlers.ts`：传输启动失败时，将首次普通用户输入写回当前会话草稿；已有/新草稿均优先保留。
- `products/librechat-custom/client/src/components/Messages/Content/Error/index.tsx` 与 locales：将已知网关不可用错误呈现为本地化用户文案。

## 证据索引

- 真实云端聊天、来源记忆与草稿基线：`evidence/p00/live-baseline.json`。
- 真实 Markdown 记忆详情 SPA 导航、刷新、返回：`evidence/p01/p01-after/browser-baseline.json`、`evidence/p01/p01-after/memory-detail.png`。
- 真实提醒时间 Chip、Vikunja 任务详情、刷新、来源返回和断网恢复：`evidence/p01/drill/ui-drill.json`、`evidence/p01/drill/reminder-created.png`、`evidence/p01/drill/reminder-detail.png`、`evidence/p01/drill/real-upstream-outage.png`、`evidence/p01/drill/outage-recovery-reload.png`。
- 八账号隔离：`evidence/p01/identity-e2e-final.txt`。
- 错误组件回归：`evidence/p01/error-copy-regression.txt`，142 tests。
- 前端构建与类型检查：`evidence/p01/final-build-exit.txt`、`evidence/p01/final-typecheck-2-exit.txt`。

## 阶段边界

P01 总体保持 PARTIAL：没有经授权的真实生图资产，因此回忆详情无法通过；系统级 IME 和完整登录/注销生命周期尚未实测；故障测试覆盖真实应用服务不可用，不能外推为所有模型超时、429 均通过。P02 及以后业务不以本阶段 UI 入口存在为完成依据。
