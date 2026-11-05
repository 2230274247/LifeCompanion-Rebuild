# V0.3 数据授权矩阵

默认 deny-all。只有资源所有者明确创建 grant 后才放行；`family`/`partner` 等
身份标签不自动变成读取私密数据的权限。

## 资源类型

| 资源 | 所有者 | 授权后可见范围 | Agent 可查条件 |
| --- | --- | --- | --- |
| profile.basic | 本人 | 头像/显示名（搜索与列表） | 无需敏感授权 |
| status.shared | 本人 | 主动发布的近况 | grant `read` |
| availability.declared | 本人 | 本人声明的空闲窗口 | grant `read` + `agent_allowed=true` |
| photo / memory | 本人 | 指定资源 ID 或共享关联快照 | 不直接读原始私人全文 |
| space.memory.ids | 本人 | 指定回忆进入该空间共享容器 | 仅在共享容器内整理 |
| notification.forward | 接收者 | 允许指定好友转达关怀 | 需显式 `consent_to_forward` |

## 边界

- 私人对话、私人记忆、原始照片永不因好友关系或 Space 成员身份自动开放。
- 共享回忆只存来源指针与主动贡献，不复制原始私人全文。
- 群体 AI 回答以所有接收者可见范围的最小集合为准；否则只给请求者本人。
- 撤销立即影响后续读取、AI 查询与事件订阅，必要时缓存/检索均二次过滤。
