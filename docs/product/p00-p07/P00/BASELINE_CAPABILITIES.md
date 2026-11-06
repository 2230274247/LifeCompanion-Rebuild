# P00 真实能力基线

证据等级：本轮 REBUILD_RUNTIME_VERIFIED；不继承历史 PASS。

| 能力 | 分类 | 本轮事实 |
|---|---|---|
| LibreChat/GLM 聊天 | ALREADY_WORKING | 四个新会话真实调用并保存，重读历史成功 |
| 绿色 U盘/雨伞跨会话召回 | ALREADY_WORKING（限定场景） | 两条来源在第三会话同时召回，包含非银色条件 |
| 八账号身份 | ALREADY_WORKING（人工测试开通） | 官方 API 注册、独立 Memos 身份；未证明普通用户全自动开通 |
| 提醒时间 Chip | ALREADY_WORKING（草稿） | 仅缺 event_time，实际返回 08/09/10:00；本阶段未创建正式任务 |
| 账号隔离 | 部分实测 | 四个会话他人不可读，合法格式的草稿越权修改返回 404 |
| 前端 | 部分实测 | Chrome 登录；五视口无横向溢出；四个深链接 HTTP 200；JS pageerror 0 |
| LangMem/Neo4j/Graphiti | NOT_IMPLEMENTED | 当前 requirements 和源码未接入；不把规则检索冒充图谱 |
| LangGraph/APScheduler | NOT_IMPLEMENTED | 当前任务为本服务线程及 Vikunja webhook；没有指定框架接入 |
| 自动回忆 | PRESENT_BUT_UNVERIFIED | 有 moments 表、窗口线程及 provider 路径；未允许生图调用 |
| 搜索/路线/回访/家庭/后台 | 尚未验收 | 进入对应阶段审计，不能依据上游可能具备而声明完成 |

后端 63 passed、网关 2 passed、身份守卫 7 passed，均有本轮原始日志。
它们属于各自测试层，不能相加宣传产品验收通过数。
实际 provider：existing Zhipu glm-4.7；本轮基线新聊天 4 次、图像调用 0 次。
聊天链路用时 29.39 秒；未取得完整费用账单，不填造费用/P95。
Android 真机通知 UNKNOWN；完整任务创建/取消/重启、图片文件、IME 和错误恢复未在 P00 验收。
