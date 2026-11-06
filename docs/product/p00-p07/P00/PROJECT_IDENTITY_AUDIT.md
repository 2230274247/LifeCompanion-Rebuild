# P00 项目身份审计

核验时间：2026-11-03T21:27:57.452234+08:00；本阶段结论 PARTIAL，审计与隔离环境已建立。

唯一主项目：`H:\AI For research institute\LifeCompanion-Rebuild`。
Git common-dir：`H:\AI For research institute\LifeCompanion-Rebuild\.git`。
开发工作树：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103`；分支 `feat/rebuild-p00-p07-20261103`；
开始/结束 HEAD 均为 `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`，没有创建提交。
Rebuild 没有 origin remote，不能擅自关联历史 Silver-economy 远端。
原工作区开始前有 82 条 porcelain 状态记录；原 LibreChat 有独立历史和未提交补丁。
本工作树叠加当前 Rebuild 代码，排除原运行环境、密钥、数据库、历史用户素材和历史证据。

旧 Silver-economy HEAD `093627936776da2a78fce09ef7b174a0793f82f0`，
其 intelligence 工作树共享旧 `.git`，与 Rebuild 不同源。
本轮旧工作树 324 条状态记录，不继承“119 文件”的历史计数。
research 根是仓库集合，无顶层 Git。旧项目 551 个、旧工作树 467 个
被盘点源码/文档的前后 SHA-256 完全一致。此范围不包括所有二进制素材及数据库。
原 Rebuild life-core SQLite 的 SHA-256 及 schema/行数前后不变。

## 真实服务归属

`evidence/p00/container-ownership.json` 记录原容器 Compose labels、镜像、
只含变量名/存在性的配置和实际挂载。原 `lifecompanion-upstream` 与
`lifecompanion-reminders` 的 working_dir 均指向 canonical Rebuild/infra。
初始无关键服务监听、Docker daemon 停止。启动 Docker Desktop 后，其原 restart
策略也恢复了旧项目容器。未向旧服务执行测试或迁移；无法证明该恢复过程没有产生
数据库内部维护写入，因此 ROOT-02 为 PARTIAL，不能把源码哈希等同于所有旧数据不变。

本轮 project `lcr-acceptance-20261103` 使用独立网络、空数据库和运行目录：

| 服务 | 地址 | 权威数据 |
|---|---|---|
| 统一网关 | 127.0.0.1:3031 | 无数据库 |
| LibreChat | 127.0.0.1:3091 | 独立 Mongo / LibreChatAcceptance |
| life-core | 127.0.0.1:8031 | 本工作树 infra/runtime/p00/life-core.sqlite3 |
| Memos | 127.0.0.1:5241 | 本工作树 infra/runtime/p00/memos |
| Vikunja | 127.0.0.1:3461 | 本工作树 infra/runtime/p00/vikunja |
| ntfy | 127.0.0.1:8097 | 独立认证和缓存目录 |

不连接原用户数据库进行验收。新应用 JWT、内部令牌和加密密钥独立生成；
只复用既有已批准的 Zhipu 模型配置，值不进入报告。
