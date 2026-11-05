# 拾光 V0.2.1 实际验收证据

开发：2026-11-02；最终复核：2026-11-03 凌晨，Asia/Hong_Kong。**总体 PARTIAL**。
仅本地服务与合成账号；未提交、未 push、未公网部署。
下列测试为限定范围，不是全量覆盖率。历史失败保留，不用后续成功覆盖原始失败文件。

## 阶段与门槛

| 阶段 | 实际证据 | 状态与范围 |
| --- | --- | --- |
| 0 基线 | [baseline.json](baseline.json)、[审计](audit.md) | PASS：20:52:33 保存状态、原数据与差异，重跑 16 后端 + 115 前端 + 1 网关 = 132 |
| 1 记忆 | [真实 DeepSeek/Memos](live-memory.json)、`memory-before.*`、`memory-final-unit.*` | PARTIAL：有限事实、授权、跨消息归并、纠错/撤回已通过；通用多候选未完成 |
| 2 UI | `before-chat-{390,430,768,1440,1920}.jpg`、`chat-recall-*`、`memory-settings-*`、[控件审计](controls.md) | PARTIAL：温暖背景、隐藏原始思考、单模型、精简导航；IME/真机未测 |
| 3 原版上游 | [版本与镜像锁](upstream-lock.json)、[真实原版 API](upstream-live-api.json)、[OpenAPI](vikunja-openapi.json) | PASS：完整 Git 历史、许可证、固定镜像与原版到期触发 |
| 4 API | [全链路](life-core-live-api.json)、[双已配置账号](spa-two-user-live.json) | PARTIAL：单次提醒真实闭环；周期/系统后台/手机未交付 |
| 5 React 融合 | `chat-reminder-created-1440.jpg`、`delivery-reminders-*`、`reminder-completed-1440.jpg` | PARTIAL：真实聊天→提醒→站内消息；设备是否收到 unknown |

原版与 API 成功先于提醒 UI：`upstream-live-api.json` → `reminders-api-v2-live.json`
（22:32:44–22:34:17，退出 0）→ `reminders-ui-build.json`（22:55:18 开始）。
后续自然语言与恢复扩展失败另行修复，不把失败阶段称为全部完成。

## 最终限定回归

每个命令证据均含 `.json` 的目录/参数/起止时间/退出码及同名 `.txt` 输出。

| 范围 | 证据前缀 | 结果 |
| --- | --- | --- |
| life-core pytest | `delivery-backend-final` | 30 passed；1 条上游 Starlette/httpx 弃用警告 |
| React 11 suites | `delivery-client-regression` | 122 passed；保留预期错误测试的 console 输出 |
| LibreChat API 包 2 suites | `delivery-api-tests` | 78 passed |
| 网关 | `final-gateway` | 2 passed |
| 合计 | 以上四个不重叠集合 | **232 个测试通过**；新增与原有并非同一统计口径，不是“132 的覆盖率” |
| client TypeScript | `delivery-client-types` | 退出 0 |
| API TypeScript | `final-api-types` | 退出 0 |
| data-provider TypeScript | `final-data-provider-types` | 退出 0 |
| 定向 ESLint | `delivery-final-full-lint` | 退出 0 |
| data-provider / API / client 构建 | `reminders-data-provider-delivery`、`final-api-build`、`delivery-client-build` | 退出 0；保留 Vite/Tailwind 上游 warning，不等同类型检查 |
| Compose quiet 验证 | `final-compose-reminders`、`final-compose-spa` | 退出 0，未输出展开密钥 |
| 完整源码补丁 | [patch-delivery.json](patch-delivery.json) | 41 个源码文件；原版临时 index 应用检查通过，真实 index 未改变 |

实际 API 检查是独立场景，不与单元数量相加：

- `live-memory.json`：真实 LLM 事实、检索、两签名身份、PRIVATE Memo、跨消息归并、撤回清理。
- `upstream-live-api.json`：原版身份、Webhook、任务创建/修改、真实 ntfy 接收与任务 ID 对齐。
- `life-core-live-api.json`：16 项检查，包括 v2 CRUD、签名回调、真实推送、取消后不发送、
  丢 Webhook 的官方 inbox 恢复、自然语言创建/同源重试/取消。
- `spa-two-user-live.json`：5 项检查；两个已配置账号各自可用、互相 404、ACL 403、
  B 的真实到期只出现在 B、真实上游完成；只清理新建合成任务。
- `reminder-withdrawal-live.json`：真实 LLM 在撤回通知授权后仍可取消本轮新建的合成提醒，
  最终读取状态 cancelled，测试后恢复原授权。

## 浏览器实际记录

隔离 A 正常中文聊天；新会话召回龙井；项目组两条消息在时间轴只显示一段回忆；
聊天创建 23:23 提醒，刷新仍在，编辑真实标题，到期读取 ntfy，UI 办完成功。

| 截图 | 说明 |
| --- | --- |
| `chat-reminder-created-1440.jpg` | 后端确认后聊天回复实际安排时间 |
| `chat-recall-{390,430,768,1440,1920}.jpg` | 新会话召回长期偏好、无原始思考区域 |
| `memories-{390,430,768,1440,1920}.jpg` | 一条已发布事件 |
| `memory-detail-1440.jpg` | 初次详情检查，发现生成审计尾注进入阅读区，保留修前证据 |
| `delivery-memory-detail-*` | 最终阅读正文移除生成的内部尾注，原 Memos 和来源入口保留 |
| `memory-settings-{390,430,768,1440,1920}.jpg` | 独立授权与事实管理 |
| `reminders-*` | 编辑后等待提醒的早期视口截图 |
| `delivery-reminders-{390,430,768,1440,1920}.jpg` | 最终构建、已完成、真实收到消息及 accepted/unknown 文案 |
| `chat-dark-1440.jpg`、`reminders-dark-1440.jpg` | 暗色兼容，测试后恢复原浅色 |
| `settings-dialog-light-1440.jpg` | 设置弹窗使用统一背景 |
| `browser-viewport-checks.json` | 真实 DOM 观测；早期 diff 的 titleVisible 不作为断言，后续使用完整树 |

截图只展示合成资料。390–1920 为浏览器视口测试，不等于真实手机系统验收。
NOT TESTED：系统中文 IME、手机键盘、系统级缩放/通知权限、关页通知、APK、
全量键盘焦点遍历、持续多自然日真实使用。错误/空态组件测试通过，
没有把组件 Mock 冒充浏览器断网实测。

## 失败、修复与残留

- `memory-before.*`：先复现缺失记忆管线，再实现并复测；早期 API 类型错误修复，保留原文件。
- `reminders-ui-tests.*`：状态文本包含日期，精确匹配失败；改为验证状态语义，
  后续真实 UI 与 122 项回归通过，未降低业务断言。
- `reminders-recovery-live.*`：真实 LLM key 读取配置不完整；改读非空服务端配置。
- `reminders-recovery-final.*`：模型返回合法意图但 `clarification:null` 被拒。
  增 nullable 字段和针对性测试，`final-reminders-live.*` 全链路退出 0。
- `final-scoped-lint.*`：4 处失败；移除嵌套三元、修正 const，定向复测通过。
- `consent-cancel-before.*`：复现撤回通知授权会阻断聊天取消；改为仅创建/编辑需要该授权，
  真实取消实测通过。`delivery-backend-consent.*` 曾有 1 项并发测试失败：
  测试启动的后台 worker 抢先消费 outbox。改用独立 Store 验证两线程竞争和重启恢复，
  保留原断言，最终 `delivery-backend-final.*` 30 项通过。
- Lighthouse 早期 Windows 空格路径/Mongo 下载/缺 Chromium 问题分别留档。
  最后 `final-lighthouse-chrome.*` 使用本机 Chrome，隔离 3098/Mongo 正常启动，
  全局注册 `Sign up` 定位超时，退出 1。**FAIL：没有 LCP/CLS/TBT 结果**。
- 固定周期提醒、OS Web Push/手机、普通用户开户、生图 Provider 未交付。
  ntfy cache 之外的 exactly-once、手工请求完整幂等、极端积压和未知上游结果仍有限制。

完整阶段中文日志见 [日志索引](../../docs/development-log/README.md)；
架构见 [V0.2.1 实际边界](../../docs/architecture/V02_1_MEMORY_REMINDERS.md)；
文件清单见 `changed-files.md`，补丁见 `patches/`。

## 跨日收尾复核

- `delivery-live-health.json`：六个服务全部 200，合成 A 一条真实生活事件有两条来源，授权召回和 ntfy 消息读回通过。
- `data-preservation.json`：逐行核对 SQLite 备份中的原用户/事件/接入/执行记录全部保留。
- `upstream-vikunja-login.jpg`、`upstream-ntfy-home.jpg`：原版启动截图；没有原生管理台任务操作浏览器验收。
- `secret-scan.json`：已知真实密钥字面值扫描，不能代替完整安全审计。

逐项门槛见 [任务书验收矩阵](acceptance-matrix.md)。最终 API 复跑为 `delivery-api-tests.*`，78 passed。

补充：`delivery-whitespace-root.*` / `delivery-whitespace-librechat.*` 退出 0；`contrast.json` 六组指定浅色 Token 对比度通过，非全站无障碍审计。
