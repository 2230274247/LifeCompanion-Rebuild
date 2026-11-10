# 产品文档索引

- [发生日期独立复测（2026-11-10）](../../evidence/memory-occurrence-20261110/README.md) — 上周六精确日、月份范围、未知日期、跨年/时区/多事件真实抽取与概览；正式聊天证据包接真实模型通过，完整聊天容器重载受阻；旧历史未批量回填，整体P5仍PARTIAL。

- [聊天语义撤回复测（2026-11-10）](../../evidence/memory-forget-20261110/README.md) — A5 真实撤回通过：新旧住址和相关事件失效，新会话不复活、重放拒绝、独立偏好保留、Memos 404；原始聊天不删除，超过 80 条候选安全拒绝；整套 P5 仍 PARTIAL，未正式部署。

- [记忆与语义请求编排实施状态](../development/MEMORY_IMPLEMENTATION_STATE.md) — 长期来源、语义意图、模糊回顾、证据与业务执行的逐阶段进度。

- [已有密钥真实P5验收](../development-log/2026-11-09_21-29_已有密钥真实记忆P5验收_开发验收.md) — 隔离真实DeepSeek已验证跨年、同义、指代澄清、纠正、无命中、联网边界与引用；整体PARTIAL，撤回/发生日/混合提醒未通过。302项后端测试通过不代表正式部署通过。

- [类人记忆与语义请求编排调研（2026-11-09）](../architecture/MEMORY_AGENT_RESEARCH_2026-11-09.md) — 对应长期记忆、语义泛化、模糊回顾与意图路由诉求；调研建议，不代表产品已实现。

- [400条历史记忆与纯语义召回验收](../../evidence/memory-load-20261109/README.md) — 四时段合成资料、跨聊天实际回复与完整失败记录；32条回忆候选尚未正式发布，整体状态以本轮日志为准。

- [拾光 V0.2 自然聊天与图文影集验收](v0.2/ACCEPTANCE.md)
- [拾光 V0.2 仓库审计](v0.2/AUDIT_V02_NATURAL_CHAT_MEMORY_GALLERY.md)
- [拾光 V0.2 文件级实施计划](v0.2/IMPLEMENTATION_PLAN_V02_NATURAL_CHAT_MEMORY_GALLERY.md)
- [Otis 应用内宠物（2026-11-05 独立增量）](../development-log/2026-11-05_11-50_Otis应用内宠物_开发验收.md)
- [V0.3 原始开发规格与素材](v0.3/开发文档.md)
- [V0.3 仓库审计报告](v0.3/仓库审计报告.md)
- [V0.3 A→B→C→D 实施计划](v0.3/实施计划.md)
- [V0.3 B0 Kolors 真实生图验收](../development-log/2026-11-04_14-00_Kolors真实生图B0_开发验收.md)
- [V0.3 B0 Kolors MIME 错配诊断与修复](../development-log/2026-11-04_14-15_Kolors_MIME错配诊断与修复_开发验收.md)
- [V0.3 B0 Kolors 真实调用与严格 MIME 验收](../development-log/2026-11-04_14-21_Kolors真实调用与严格MIME验收_开发验收.md)
- [V0.3 B0 Kolors 真实生图 REAL 验收](../development-log/2026-11-04_14-26_Kolors真实生图B0_REAL验收_开发验收.md)
- [V0.4 Android 原生客户端实施计划](v0.4/实施计划.md) — 原生 Kotlin + Compose，复用现有网关 API（DESIGN ONLY）
- [V0.4 Android 原生客户端架构](../architecture/V04_ANDROID.md)

2026-11-04 V0.3：B0 已完成真实 Kolors 技术验证。在一次明确批准的新隔离尝试中，
请求 1 次、下载 1 次、自动重试 0 次，取得通过完整解码、MIME 回退、尺寸和
SHA-256 校验的 PNG。受限 `application/octet-stream` 回退仅适用于可信
SiliconFlow HTTPS 来源，默认关闭。人工视觉完整性 PASS，但 Prompt 对齐仅
PARTIAL，P04 语义评测未运行。A 整体 PARTIAL，B/C/D 尚未实施；未进入 B1。
已识别当前开发基线位于
`.work/p00-p07-20261103`，不能把本目录较早 main 代码当成 P04 最新成果。

2026-11-05 新增应用内宠物“Otis”：只在聊天路由渲染的 200×256 可拉伸脸，
复用作品集原版 WebGL2 引擎。捏脸/拉拽/松手换表情/折叠、深浅色主题、
1920 与 390 视口均已实测；`/memories` 与移动端不显示。纯指针交互，
无键盘入口，心情不持久化；人脸贴图授权未明。该增量不改变 V0.3 A–D 的
范围与上线阻塞。上一轮的 Electron 常驻置顶窗保留为可选实验；更早的
murmur 玻璃球实现已被 Otis 取代，仅保留历史日志。

- [版本入口说明](../../README.md)
- [逐次开发验收记录](../development-log/README.md)
- [V0.1 演示准备验收](../ACCEPTANCE_2026-11-04.md)（2026-11-02 为 11 月 4 日演示准备）
- [尚未完成的功能与上线阻塞](../BLOCKERS.md)
- [Android 后续边界](../ANDROID_PLAN.md)

V0.2 范围：统一登录入口、复用真实聊天、回忆列表与详情、聊天到回忆链路、
权限边界、响应式及可追溯工程日志。功能状态以对应开发日志的实际测试为准。
V0.2.1 增量见 [实际范围与限制](../architecture/V02_1_MEMORY_REMINDERS.md)、
[本轮证据](../../evidence/v02-memory-reminders/README.md)。
当前仍为明确映射的本地内测。两个合成账号已验证提醒与通知隔离；
有限事实的跨会话召回、单次提醒及真实站内消息可用。多用户自助开户、
固定周期提醒、关页/手机推送、生图和 APK 均未交付。总体 PARTIAL。
