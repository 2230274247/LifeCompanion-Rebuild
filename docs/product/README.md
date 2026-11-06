# 产品文档索引

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
