# 语义撤回真实验收证据（2026-11-10）

本目录只归档隔离合成资料及经复核结果，不含密钥、令牌、账号配置、原始运行日志或数据库。真实使用已有 DeepSeek 配置、固定 H 盘 BGE 缓存、当前工作树 life-core 与 LibreChat 服务端；绑定本机回环。原 P5 证据保持不变。

- [复核结论](reviewed-results.json)：A5 本轮撤回复测 PASS，整套 P5 仍 PARTIAL；受控、真实模型及未测试范围分别列明。
- [最终逐项证据](final-cases.json)：9 个实际步骤，含住址/茶偏好前后回复、否定/假设/引用、撤回后新会话、原话重放，以及合成数据库快照。
- [Memos 官方接口核验](memos-check.json)：撤回前事件已发布并有 memo_ref，撤回后带所属用户认证的 GET 返回 404。
- [首次失败](first-attempt.json)：规划输出含非法 `target`，没有执行删除却出现文字承诺。修复严格输出形状，并对召回所有结果分支增加无回执不得确认的约束。
- [第二轮结果](second-attempt.json)：撤回及重放验证成功；宽泛“我平常喝什么饮料”没有命中仍保留的龙井偏好。未修此语义召回差异；最终改用相同茶类问题做撤回前后对照，不能把该宽泛查询当成已通过。

最终数据库：新旧住址、乔迁事件共 3 条派生记忆和 3 个来源撤回；来源正文清空，派生内容/事件摘要清空，独立茶偏好仍 active，向量只保留茶偏好，抽取任务 payload 全部清空。新消息 ID 重放住址原文返回 `SOURCE_REVOKED`。

本轮没有删除原始 LibreChat 聊天记录，没有为所有旧会话后续上下文实现系统屏蔽。候选任一类超过 80 条返回 `FORGET_SCOPE_TOO_LARGE`；分页撤回未实现。真实 Moments 内容撤回、Memos 故障重试注入、正式部署、浏览器聊天操作及性能审计未验证。浏览器仅渲染登录页，观察到 locale/ServiceWorker 资源请求失败，不能标成浏览器验收通过。

可复现自动化：`services/life-core/tests/test_memory_forget.py`、`test_forget_api.py`、`test_assistant_plan.py`；LibreChat memory 套件及补丁见 [补丁索引](../../patches/README.md)。完整合同见 [语义撤回架构](../../docs/architecture/MEMORY_FORGET.md)。
