# P05 工具注册与执行边界

2026-11-04；PARTIAL，已运行Core只读执行层，聊天/前端接入尚未完成。

已调查LibreChat原生`packages/api/src/tools/registry/definitions.ts`、
`tools/classification.ts`、`mcp`和`api/server/services/Tools/search.js`。
当前产品固定DeepSeek custom endpoint，未启用MCP/Agent工具或webSearch配置；
不能把上游源文件存在计为工具可用。既有业务适配入口是
`packages/api/src/memory/life.ts`，应在其持久消息边界接入工具回执，
保留原聊天系统和DeepSeek地址/Key。

Core新增`app/tools.py`作为产品权限、预算和执行审计层，当前注册四个只读
适配器：`place_search`、`weather`、`route`、`search`。
`GET /api/v1/tools`返回Pydantic参数Schema、只读属性、出网字段和超时；
`POST /api/v1/tools/execute`只接受登记名称及Schema参数，额外URL等参数拒绝。
执行记录经`/api/v1/tool-executions`按认证用户读取和删除，换用户ID无效。

默认`LIFE_TOOL_REQUEST_BUDGET=0`；Provider也默认未配置。额度按持久
`tool_executions.network_requests`总和计算，失败、删除、过期及重启不退还。
`BEGIN IMMEDIATE`在HTTP前原子预留；稳定owner/idempotency_key重复返回同一
回执，参数改变409。不自动重试网络，超时unknown，明确503/429保留失败。
首次真实503未伪造天气，操作员在同一库中只做一次明确恢复，总上限4请求。

出网只包含用户明确提供的查询或坐标，不发送JWT、用户ID、聊天全文、记忆
或服务Key。地址固定到公开Provider；搜索只接受管理员配置的127.0.0.1
HTTP SearXNG，客户端不能指定访问URL。响应上限256KiB，不跟随重定向，
禁用环境代理。日志保存稳定错误码，不保存供应商错误正文。

回执正文24小时到期清除、保留最小配额账本；本人删除及在途删除不允许恢复
内容。普通结果不包含内部SearXNG查询地址。源消息删除传播、管理员指标、
完整速率限制及生产数据治理仍需P07继续验收。

真实证据：`evidence/p05/tools-live-f7efdd3a740b40bf.json`。尚无聊天入口、
浏览器Receipt、搜索Provider、语音或回访，不宣布P05完成。
# 天气聊天交互补充（2026-11-04）

在原LibreChat消息持久化业务边界中识别窄范围的显式天气请求；
不新增规划模型调用，原DeepSeek聊天配置不变。只把显式城市名发往地点服务，
不自动读取家庭住址、设备定位或记忆中的地点。

SQLite `tool_chats`保存owner、源消息、会话、请求hash、revision、
24小时期限及候选/执行引用。状态为needs_place→running→choose_place→
running→succeeded/blocked/failed/unknown；另有no_places/cancelled/expired。
缺城市只问城市；同名地点必须选择持久候选索引，不接受客户端注入坐标。
选项更新以事务和revision约束；重复点击回放原结果，过期/外账号/旧版本拒绝。
取消和过期清除地点、天气正文及源关联；网络晚回包不能恢复被清除内容。
额度仍由原tool_executions预留，清除正文不返还或重置额度。

新增内部`POST /internal/v1/tools/chat`只接受服务端Token；
公开列表`GET /api/v1/tool-chats?conversation_id=...`、
选项`POST /api/v1/tool-chats/tc_<28hex>/select`及DELETE均要求当前用户身份。
网关只放行上述三个公开方法/路径，剥离Cookie和内部Token，不放行内部hook。
原生桥接只能在消息已持久化后调用；结果只加入模型输入副本。

当前意图识别不是通用自然语言规划。相同名称/州级区域的候选仍可能显示近似标签，
后续应补更细行政区以改善选择；不得把当前UI当成任意地名定位已验收。
天气forecast_date分支有本地测试，真实浏览器本轮只验证当前天气。
外部服务超时/失败不自动重试，关闭页面后通过刷新读取持久状态。

