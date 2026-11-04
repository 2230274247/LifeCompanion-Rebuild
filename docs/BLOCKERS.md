# Blockers

## IMAGE_PROVIDER_REAL_PATH

**状态：PASS（2026-11-04）**

SiliconFlow Kolors 已通过服务端父目录密钥完成三条真实调用，HTTP 200、
960×1280 PNG，主体/动作/场景人工核对通过。自动生图只使用
`moment-evidence-v1`，不从文本模型自由扩写事实。

仍未实现的是生成后的视觉模型自动复核，状态见下节；这不是“图片接口未接通”。

## IMAGE_POST_GENERATION_REVIEW

**状态：NOT_TESTED**

当前由受控人工逐例核对，不执行第二次视觉模型调用。若后续引入自动复核，
必须设置最多一次重试、短超时和成本上限；失败不得无限重生成或覆盖用户原图。

## BLOCKED_REMOTE

**状态：BLOCKED**

当前 Git 仓库没有配置项目所有者授权的 GitHub remote，`WORKSPACE_LOCK.json`
也明确 `git_push_allowed=false`。可以先在本地提交和演练克隆，但不能宣称
GitHub clone/push 完成，也不能指向旧工程 `Silver-economy`。

解除条件：提供目标仓库 URL、确认许可证策略和推送权限，完成敏感扫描后使用
普通 push；不得强制推送或覆盖远端分支。

## V02_UNIFIED_LOGIN_AND_TOKEN_REVOCATION

**优先级：P2**

V0.2 已通过统一 React SPA 复用 LibreChat 登录，回忆通过同源 life-core API 读取，
用户无需再登录 Memos。经典的跨应用 SSO 交换不再是普通用户操作前提。
多用户自动映射尚未实现，仍只允许明确映射的本地内测；本轮增加两个合成账号隔离验证。
life-core 验证访问 JWT 的签名与到期；未增加访问 JWT 的即时撤销列表，
泄露的有效 JWT 仍可能使用至到期，不能声称退出即吊销全部已签发访问令牌。

## BLOCKED_ANDROID_APK

**优先级：P2**

只完成 API 边界与路线设计，没有 APK、真机通知、语音、相册、离线恢复或签名
分发。不得把浏览器页面或 PWA 称为 Android 应用已交付。

## PARTIAL_REMINDERS

**优先级：P1**

单次提醒现已通过原版 Vikunja v2.7.1 + ntfy v2.36.0 官方 API 实现创建、编辑、
取消、完成、真实到期、站内读取；React `/reminders` 在 API 实测后接入。
没有自写任务调度内核或推送服务器。证据见 `evidence/v02-memory-reminders/`。

仍未交付：无需完成的固定周期提醒、OS Web Push、关页后台/手机通知、
普通用户自助开通、完整手工创建请求幂等及极端积压恢复。
当前接受状态为 ntfy accepted，设备送达 unknown。整体仍为 PARTIAL。

## ENVIRONMENT_WSL

**优先级：P2**

当前机器 WSL 的 bash 无法启动（`execvpe(/bin/bash)` 失败）。本轮已改用
PowerShell 完成所有运行和测试。不要把依赖 WSL 的脚本当作可复现命令。

## LIBRECHAT_RAG_WARNING

**优先级：P2**

LibreChat 日志提示 RAG API 未运行。普通 DeepSeek 聊天和本轮事件接入不受影响，
但文件上传/检索相关高级能力可能不完整。P0 未声称已验证完整 RAG。

## MULTI_USER_ISOLATION

**优先级：P1**

两个合成账号已有 LibreChat/Memos 映射；提醒使用独立 Vikunja 用户及 ntfy ACL，
真实双向 API、通知隔离已通过。普通账号自动开通及所有 UI 正反场景尚未完整验收，
不能由此宣布可开放多人共用。

每用户 Memos PAT 文件路径已纳入正式启动脚本，默认
`infra/runtime/memos-tokens.json` 并以绝对路径传给 `life-core`。管理员仍须
通过 Memos 官方 API 为用户建立身份、创建 PAT 并在被忽略的映射文件中登记；
普通用户注册后的自动开户/映射仍未实现。

## V02_EVENT_GROUPING

本轮已验证同日同会话“加入项目组”跨消息归并为一条事件与多来源，
独立事实证据强化、纠错与撤回。仍不是任意主题通用语义归并：每条输入最多一个候选，
人物关系图谱、复杂多事件、泛化指代与真实跨自然日持续使用待验收。历史记录未迁移。

## V02_LIGHTHOUSE_WINDOWS_HARNESS

本轮已在独立 3098 修复 Windows 空格路径，临时 MongoDB 能启动；
默认 Chromium headless 未安装。改用本机 Chrome 后，隔离全局注册步骤无法找到
`Sign up`，退出 1，尚未进入三轮 LCP/CLS/TBT 测量。
不能把构建或单元测试当作性能预算通过。保留全部失败记录：
`lighthouse-isolated-final.*`、`final-lighthouse-chrome.*`。

2026-11-04 P05复核：显式隔离3098后注册和登录已通过；测量遇到NO_NAVSTART，
并发现上游execFile异常可将测试Cookie写入日志。已停止该独立测试、清理生成
报告/JWT并修复错误输出，新增两项脱敏回归通过。三轮预算仍未完成，
不能将两份部分报告计为性能通过；见`evidence/p05/chat-lighthouse-isolated.txt`。
