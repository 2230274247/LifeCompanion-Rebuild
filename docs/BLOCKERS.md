# Blockers

## BLOCKED_IMAGE_PROVIDER

**优先级：P1**

当前环境未发现合法、可用的图片生成供应商 Key。DeepSeek 文本 API 不是图片
API，因此没有创建真实图片任务或把静态图片伪装成生成结果。

解除条件：

- 配置一种明确支持的图片供应商 Key；
- 在工作服务器端保存，不进入浏览器或 Git；
- 实现 provider adapter、任务状态、AI 生成标记、Memos 图片引用；
- 使用生产同一流程手动触发并验证。

## BLOCKED_SSO

**优先级：P2**

LibreChat 与 Memos 当前分别登录，统一入口已明确提示。未实现：

- 统一账号；
- 跨应用会话交换；
- 统一退出与授权撤回；
- 多用户自动映射。

这不在本次桌面 P0 中冒险修改。

## BLOCKED_ANDROID_APK

**优先级：P2**

只完成 API 边界与路线设计，没有 APK、真机通知、语音、相册、离线恢复或签名
分发。不得把浏览器页面或 PWA 称为 Android 应用已交付。

## PARTIAL_REMINDERS

**优先级：P1**

`life-core` 已有提醒创建/列表和状态字段，但没有：

- 独立提醒 UI；
- 后台调度器；
- 浏览器站内通知；
- 手机推送；
- 时区/到期执行的可视化测试。

当前只可称为数据模型和 API 最小准备，不是完整提醒交付。

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

数据模型和负面 API 测试已有用户隔离，但当前运行验收是单用户映射。
在完成多用户 broker/账户开通流程、Memos 多账号映射和审计前，不应开放多人共用。
