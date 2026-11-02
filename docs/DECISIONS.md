# Decisions

## D001：保留两个独立上游 Git 仓库

LibreChat 与 Memos 各自保留 `.git`、`origin`、tag 和完整历史；根仓库只保存
总装、自研服务和文档。这样能直接查看真实上游提交与本地差异，不把上游源码
复制成失去历史的单体目录。

## D002：聊天接入放在服务端消息持久化后

选择在 LibreChat `BaseClient.js` 的小范围持久化路径调用 `life-core`，而不是
扫描全库或信任浏览器上报。请求携带服务端令牌，失败不阻断聊天。

## D003：使用单用户显式映射起步

`librechat_user_id -> life_user_id -> memos_user_id` 由内部 bootstrap 建立。
当前只允许明确测试用户，避免多用户内容共享到管理员账户。

## D004：Memos 只走官方 API

使用 Memos 26.10.0 `/api/memos`，服务端 PAT 授权，写入 `PRIVATE` 条目。
不直接改 Memos 数据库，不依赖旧版 `/api/v1` 路径。

## D005：事件采用确定性幂等键

事件幂等键为 `source_type:source_message_id`；Memo 发布任务再按
`memo_publish:<event_id>` 幂等。Memos memoId 由事件 ID 的 UUID5 派生。

## D006：不因图片功能阻塞 P0

未找到合法可用的图片供应商凭据。DeepSeek 文本模型不当作图片模型；
图片功能记录为 `BLOCKED_IMAGE_PROVIDER`，不生成假成功状态。

## D007：统一入口不强行 iframe

LibreChat 与 Memos 保持各自原生页面，通过薄入口和清晰导航进入；当前不声称
SSO。以后单点登录需要独立认证设计和安全测试。

## D008：Android 先定 API 边界

自研业务统一通过受保护 HTTP API，认证不能依赖 LibreChat 浏览器私有状态。
本周不交付 APK，后续可在 Capacitor 与 Flutter/原生之间按真实验证结果选择。
