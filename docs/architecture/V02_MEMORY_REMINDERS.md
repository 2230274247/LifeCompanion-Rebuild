# V0.2 记忆与提醒实施边界

日期：2026-11-02。本文是实现契约与审计记录，不是完整 PASS 声明。

## 基线与顺序

实际基线见 `evidence/v02-memory-reminders/baseline.json`。根仓库和 LibreChat
均已有未提交修改，原始差异和 SQLite online backup 保存在被忽略的
`infra/runtime/v02-memory-reminders/`；没有覆盖旧日志。
6 条原事件、8 条接入记录、0 条提醒是本轮开始时的实际数量。
现有四个服务健康，Silver-economy 和 Open WebUI 容器不属于本轮操作范围。

执行：先审计和记忆，再主题与控件，再 Vikunja 原版、ntfy 原版、
官方 API，最后才允许提醒页面。补充讨论作为产品原则，不替代最新任务书的门槛顺序。

## 唯一产品记忆管线

```text
已持久化的用户消息 -> 内部 enqueue -> SQLite 有界抽取任务 -> LLM 结构校验
                                                           -> 确定性分类/授权/去重
                                 + stable_fact -> memory_items
                                 + life_event -> events -> PRIVATE Memos
                                 + future_plan/no_memory -> 不写个人记忆
模型生成前 -> 用户作用域 recall -> 最多四条相关事实 -> 不可信证据上下文
```

- 原始聊天归 LibreChat；不把完整问答复制进记忆。
- 新表用 `CREATE TABLE IF NOT EXISTS` 增加，不改写原有 6 条事件，不运行破坏性迁移。
- `memory_permissions` 的读取、敏感、通知权限默认 false；
  自动整理沿用已有 `memory_consent`，生图沿用 `image_consent`。
- 自动整理启用后，普通合格内容无需逐条确认。无写入授权不留候选正文。
  敏感内容在外发抽取前先做保守词法拦截，模型 unknown 也不能自动写入。
- 队列任务在成功或最终失败时清掉正文；未完成正文保留至多 24 小时；
  撤销自动整理清掉待处理正文；抽取不阻断聊天，重启恢复中断任务。
- 内部令牌确认消息来自服务端已保存钩子；外部用户不能经网关调用内部接口。
  手动 API 表示用户主动提交内容，不被当作已验证的另一条聊天来源。
- 同源幂等保留；规范事实按用户和事实键唯一当前版本；项目组加入事件按日期和主题归并。
  其它事件目前采用保守的规范正文键，不夸大为全面向量语义检索。
- 独立证据按日期、会话、内容散列判定；重复消息、同日/同会话、完全复制不加重要性。
  confidence 不随重复增加，importance 独立，state/valid_from/valid_until 表示时效。
- 新明确纠正使旧版本 superseded，撤回先使检索和时间轴不可见，
  然后经官方 Memos DELETE 清理；失败记录 `memo_delete`，后台有限重试，重启可恢复。
  不清空用户原有记录。
- 召回目前采用有界词法和领域相关性排序，未引入未运行的 RAG 服务或向量库。
  新会话可召回经授权的 active 事实，关闭读取立刻返回空证据。
- LibreChat `memory.disabled: true`，停用其独立产品写入；维护源码保留。

## API

| 接口 | 作用 |
| --- | --- |
| `POST /internal/v1/events/enqueue` | 持久化后的异步接入，仅内部认证 |
| `POST /internal/v1/knowledge/recall` | 按服务端认证用户检索，凭据不入前端 |
| `GET /api/v1/knowledge` | 当前用户可管理的 active 记忆 |
| `GET /api/v1/knowledge/recall?q=` | 独立读取授权、相关性、有效期过滤 |
| `PATCH /api/v1/knowledge/{id}` | 用户更正长期事实，同管线建立新版本 |
| `DELETE /api/v1/knowledge/{id}` | 先阻断，后清理衍生存储 |
| `PATCH /api/v1/me/settings` | 分目的授权，旧字段兼容 |

用户界面只在“记忆与权限”管理事实和授权，不显示检索数量、内部 ID 或令牌。
事件页只展示 published 且属于当前用户的真实 Memo。
多账号 Memos PAT 通过服务端受忽略凭据文件映射；默认 PAT 仍强制核验 creator。

## UI 根因与控件审计

`bg-presentation` 使用默认白色，Life 主题原先未覆盖 `rgb-presentation`；
新增语义 Token，不全局替换 white。正文墨色与暖白保持对比，暗色保留上游角色。
原始 THINK 没有经过安全摘要契约，拾光模式隐藏入口及旧文本思考块。
这是组件行为控制，错误/工具失败仍正常显示。

| 控件/组件 | 原行为 | 实际取舍与业务作用 |
| --- | --- | --- |
| Life Header / 桌面 rail | 同时重复聊天、回忆导航 | 桌面用 rail，移动端用顶部导航 |
| 原生 Agents/Skills/Prompts/Memory/Files 导航 | 工程菜单占据普通入口 | 拾光配置只留会话历史；上游维护源码保留 |
| 手机 Switcher | 唯一“对话历史”仍可展开 | 单项隐藏选择器 |
| 模型/预设/多会话/书签 | 单模型也提供多层选择 | 当前固定单模型，配置隐藏；保留原发送 |
| 思考默认偏好 | localStorage 可重新展开私有推理 | 拾光模式不渲染原始推理和相关开关 |
| 搜索/日期/顺序/分页/回忆卡片 | 已接真实 API | 保留，操作改变真实查询或路由 |
| 记忆与权限 | 原缺失 | 三个独立开关接真实权限，事实更正/删除接真实 API |
| 发送/停止/复制/再生/编辑/历史 | 成熟聊天能力 | 保留，验证不回归 |
| 提醒入口 | 后端只记本地 scheduled | 接通上游前不展示；未连接返回明确 503 |

## 已知实现限制

目前结构化模型每条输入最多一项保守候选；长期事实支持饮品偏好和明确居住事实，
不是任意人物关系图谱。泛化跨表达事件合并、多个候选的澄清与多语义冲突仍需专项验证。
不能将少数样例通过说成所有生活内容理解完毕。
没有图片 Provider，因此只保存独立 image_candidate，不生成假图片。
系统中文 IME、手机真机及设备通知，必须依据实际操作另记状态。
