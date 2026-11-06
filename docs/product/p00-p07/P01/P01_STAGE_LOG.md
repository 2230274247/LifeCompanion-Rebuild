# P01_STAGE_LOG

日期：2026-11-03，Asia/Hong_Kong  
阶段结论：**PARTIAL**  
目标仓库：`H:\AI For research institute\LifeCompanion-Rebuild`  
执行工作树：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103`  
分支：`feat/rebuild-p00-p07-20261103`  
开始与结束 HEAD：`e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`（未提交、未推送）

## 阶段门禁

每个操作先执行 `python scripts/verify_rebuild_workspace.py`，核对结果为 PASS。隔离 Compose project 为 `lcr-acceptance-20261103`；测试库为 `LibreChatAcceptance`、工作树内 SQLite 与独立 Memos/Vikunja/ntfy 数据目录。没有访问 canonical Rebuild 的 SQLite、生产 `.env`、正式用户数据或旧 Silver 数据库执行读写测试。

P01 真实测试在现有已配置 Zhipu glm-4.7 上完成 1 次合成用户 UI 聊天；P00 基线另有 4 次真实聊天，不重复计算。P01 未发起图片、地图、语音或新供应商调用。单次调用的账单费用未提供，不能填入金额。Windows 输入法使用浏览器 CompositionEvent 负路径模拟，未连接/声称完成原生 IME 测试。

## 功能与修复

1. Markdown 记忆引用此前被当成外链，打开弹窗并把原始业务路径显示为标签。为已识别、格式正确的业务详情 URL 增加 React Router Link，实际点击记忆详情、刷新、浏览器返回均通过，且无顶层 document 请求。
2. 实际停止本轮隔离 LibreChat 容器制造真实网关故障，首轮发现发送失败文本未保留且错误 JSON 暴露 `UPSTREAM_UNAVAILABLE`。修复失败后草稿回填和本地化错误呈现；第二轮实测输入仍在编辑器中、刷新后仍在、内部代码不可见且没有假提醒成功文案。
3. 通过 P01 真实浏览器输入 Enter 调用现有云模型，GLM-4.7 回复“已收到”；本轮真实 Mongo 查询确认用户行和助手行以同一会话 ID 持久化。随后另开浏览器验证该保存会话刷新后同时恢复两行。准确证据为 `evidence/p01/enter-real-chat-mongo.txt` 与 `evidence/p01/enter-real-chat-persisted.json`。
4. 合成用户 A 选择 09:00 Chip；真实 Vikunja 提醒详情与真实来源消息链接可打开，刷新和返回成功，无整张日期表单。
5. 账户 B–H 分别尝试读取 A 的两个记忆详情和真实提醒详情，每次返回 HTTP 404；无效令牌返回 HTTP 401。结果见 `evidence/p01/identity-e2e-final.txt`。

## 运行与检查记录

| 命令 / 运行 | 结果 | 证据 |
|---|---:|---|
| `node scripts/acceptance_p01_drill.cjs`（停止隔离容器） | exit 0；详情、刷新、返回、真实故障恢复、friendly copy 通过 | `evidence/p01/drill/ui-drill.json`、`final-console.txt` |
| `node scripts/acceptance_p01_enter.cjs` | 1 次真实 provider 调用；模拟 composition Enter 未发送；真实 Enter 输入清空 | `evidence/p01/enter-real-chat.json` |
| `docker exec … mongosh … LibreChatAcceptance` | exit 0；同一新会话的用户与 GLM-4.7 助手消息均已持久化、无错误/未完成状态 | `evidence/p01/enter-real-chat-mongo.txt` |
| `node scripts/acceptance_p01_saved_chat.cjs` | exit 0；真实已保存会话再次加载，用户消息和独立助手回复可见，编辑框为空；0 provider call | `evidence/p01/enter-real-chat-persisted.json` |
| `python services/life-core/.venv/Scripts/python.exe scripts/acceptance_p01.py identities` | exit 0；七个账号的记忆/提醒越权共 21 次 HTTP 404；伪造 token HTTP 401 | `evidence/p01/identity-e2e-final.txt` |
| `npm --prefix products/librechat-custom/client run test:ci -- --runInBand --coverage=false src/components/Messages/Content/__tests__/Error.spec.tsx` | exit 0；1 suite，142 tests passed | `evidence/p01/error-copy-regression.txt` |
| `npm --prefix products/librechat-custom/client run test:ci -- --runInBand --coverage=false src/hooks/SSE/__tests__/useEventHandlers.spec.ts` | exit 0；1 suite，37 tests passed | `evidence/p01/recovery-regression.txt` |
| P01 UI/input/Markdown regression selection | exit 0；7 suites，33 tests passed | `evidence/p01/jest-regression.txt` |
| `npm --prefix products/librechat-custom/client run typecheck` | exit 0 | `evidence/p01/final-typecheck-2-exit.txt` |
| `npm --prefix products/librechat-custom run frontend` | exit 0；Vite/PWA production build成功，有 chunk 大小与既有 Moment 动态导入告警 | `evidence/p01/final-build-exit.txt`、`infra/runtime/p00/frontend-p01-final-build.txt` |

此前一次 typecheck 捕获 `TResData` 未声明 `metadata.streamStartFailed`；已按运行负载做显式类型收窄，随后完整前端类型检查通过。之前第一次浏览器等待回复时误将用户提示中的“已收到”当成助手回复；没有把该误判当成功，后续由 Mongo 真实消息行与新浏览器独立恢复证据校正。

## 验收状态与限制

- `CHAT-01` PASS：P00 四真实云聊；P01 再以真实浏览器 Enter、云端回复、Mongo 数据和独立刷新恢复核验。
- `CHAT-02` PARTIAL：真实隔离应用停服/网关故障不会丢输入、不会报假业务成功；尚未独立实测模型 429 与超时各自的 UI 分支。
- `NAV-01` PASS；`NAV-02` PASS；`NAV-03` BLOCKED_CONSENT：账号 image_consent=false，未生成或伪造回忆图；`NAV-04` PASS（限定已测试 SPA 路由、深链接与五视口）。
- `AUTH-01` PARTIAL：8 个现有合成映射以及记忆/提醒详情 owner 授权验证；全新用户的普通自助开通、注销、token 刷新、撤权生命周期未完整覆盖。
- `UX-01` PARTIAL：实际 Enter 发送、composition Enter 抑制、Markdown 与错误状态已测；Windows 原生中文 IME 和所有 thinking/无效按钮场景没有逐项验收。
- `REM-*` 的完整语义、通知时刻和调度恢复归 P03，不能因本轮一条提醒真实创建而整体 PASS。

Docker Desktop 在第一次最终构建/证据写入后停止。重新启动时，Docker 按已有策略恢复了其他项目容器。没有对那些服务做请求、迁移或测试；仍无法证明启动带来的数据库维护写入不存在，所以 P00 `ROOT-02` 继续 PARTIAL。当前隔离服务已重新启动并保持可用。

## 下一阶段接口

进入 P02 前，继续使用 `librechat_user_id → life_user_id` owner 映射、真实 LibreChat `conversation_id/message_id` 作为唯一来源链接、SQLite 业务事实/证据为权威记录。LangMem/Neo4j 尚未接入；Graphiti 没有获批 Embedding，原生能力必须保留 `BLOCKED_EMBEDDING`。P02 必须在隔离 Rebuild 运行态真实集成并以证据完成或如实阻塞。
