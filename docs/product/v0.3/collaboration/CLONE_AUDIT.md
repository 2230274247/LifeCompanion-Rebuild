# Clone-first 第三方开源依赖与许可证审计

审计日期：2026-11-05。原则：优先克隆/复用成熟开源项目，不自行重写成熟的
聊天、权限、通知与记忆框架；不改动上游源码后破坏升级路径。

## 已锁定并实际使用的上游

| 对象 | 上游 | 固定版本/tag | 本地 HEAD | 许可证 | 复用方式 |
| --- | --- | --- | --- | --- | --- |
| LibreChat | https://github.com/LibreChat-AI/LibreChat | v0.8.8（tag `chart-2.0.17` 基线 `e8f3be08`） | `e48d5f745` | MIT | 账号、聊天、React 18 前端底座；本地只读挂载 + 5 个本地补丁提交 |
| Memos | https://github.com/usememos/memos | 26.10.0（tag） | `651657e72`（与上游完全一致） | MIT | 官方 REST API，不修改源码 |
| Vikunja | https://github.com/go-vikunja/vikunja | v2.7.1 | `5619c4a9f` | AGPL-3.0-or-later | 提醒/任务上游，独立部署 |
| ntfy | https://github.com/binwiederhier/ntfy | v2.36.0 | `2d5516069` | Apache-2.0 / GPLv2 组件 | 通知上游，独立部署 |

完整锁文件：`docs/UPSTREAM_MANIFEST.md`、`evidence/v02-memory-reminders/upstream-lock.json`。

## 策略引擎与实时通道的复用判断

| 对象 | 许可证 | 结论 |
| --- | --- | --- |
| pycasbin/casbin | Apache-2.0 | 已评估。本项目权限模型以“资源所有者 + 显式 grant + 有效期 + 撤销”为核心，规模下不需要引入独立策略引擎，避免冲突；业务层 `_can_read`/`_active_grant_rows` 实现资源级授权并审计 |
| socket.io / python-socketio | MIT | LibreChat 已有消息链路；life-core 使用 HTTP 长轮询 `/api/v1/collaboration/events`，按 scope 鉴权后返回事件。未启动第二套 WebSocket 栈 |
| OpenFGA | Apache-2.0 | 未引入独立服务，P03 不阻塞 |
| Graphiti / LangGraph | Apache-2.0 / MIT | 沿用本地既有集成，不重造记忆引擎 |

## Parlor 版权边界

Parlor 来自 https://supply.madebyoversight.com/sections，是供应网站的
section，**不是**确认的公开 Git 仓库，不伪造 clone URL。用户提供的原始
提示与源码仅作为本项目内部视觉参考，不公开再分发。React 19/Vite 原稿已
按 React 18 迁移为具名作用域组件，禁止替换宿主 `body`/`#root` 全局样式。

## 未引入的组件

- 不升级 LibreChat 主版本；不引入 Matrix Synapse（AGPL-3.0 完整通讯服务器）。
- 不用页面隐藏代替服务端鉴权；所有资源读取最终都由 life-core 校验 owner/space/grant。
