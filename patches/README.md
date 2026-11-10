# 上游补丁归档

## 发生日期与真实记忆页收尾（2026-11-10）

`librechat-memory-occurrence-ui-20261110.patch` 归档从 `ff42cacdaa11bbcbe0730c94591d746068585b77` 到 `4b83c57a16d3db1f7ef9425d7c6a395037cc87c7` 的增量，包含 `4b193f81e` 发生日期包实现及本轮7文件前端收尾。30,247 bytes，SHA256 `e8428dcab4a1bb5af47f2735d6d14447719210156de83ce793ad37f6c71b6a1d`；当前树反向应用检查PASS。必须配套父仓库发生日期后端使用，已含上述提交的上游不要重复应用。本轮18项组件测试、client tsc/ESLint/build、真实DeepSeek完整聊天与记忆页通过，详见[本轮证据](../evidence/memory-chat-ui-20261110/README.md)。

## 聊天语义撤回增量（2026-11-10）

`librechat-semantic-forget-20261110.patch` 对应独立上游提交
`ff42cacdaa11bbcbe0730c94591d746068585b77`，基点
`d0dc65d240d833772c7eb7361529375b7ed6db5b`；只包含 `BaseClient.js` 参数接线、
`packages/api/src/memory/life.ts` 和其测试三个文件。消息持久化后才请求语义撤回，
没有 confirmed forgotten 回执不得确认删除。配套 life-core 代码必须一同使用。
57 项 memory 测试、tsc、build 和修改 TS 的 ESLint 均通过；真实合成验收见
[撤回证据](../evidence/memory-forget-20261110/README.md)。已包含该提交的树不得重复应用；
补丁不含凭据、数据库、依赖或 dist。

## 记忆注入增量（2026-11-09）

`librechat-memory-context-7cf65d5-20261109.patch` 仅归档独立聊天仓库已提交的
`7cf65d5fc428d3f308104ea871383603c523a91d`（8个文件），基点是该提交的父提交。
它取消召回固定提示词门槛，传递当前会话最近用户上下文，分离profile/items预算，
并增加脱敏记忆诊断页面。不要把它直接应用到未具备其父提交的原版上游，也不要在
已经含该提交的当前聊天树重复应用。本轮未混入聊天仓库13个既有认证文件改动。
产品后端纯语义检索和400条合成验收由根仓库源码及独立日志追溯。

## V0.3 最新归档（2026-11-06）

`librechat-v0.8.8-v03-collaboration-20261106.patch` 是从原版 LibreChat
`e8f3be08623663d4ad7f7241e693c94469b63bb0` 到当前 V0.3 协作版本的累计补丁，
包含 V0.1/V0.2 基础、V0.3 多账号协作、Parlor、共享回忆和 Otis 应用内宠物。
补丁同时覆盖当前嵌套仓库 HEAD `0c4fc4031` 和两个未跟踪测试脚本。

- 文件大小：3,686,492 bytes
- SHA256：`B2F2D391C22510EAD1F282B779B6E1E098CF9C8C5C3D93A80E87C9C05AE99797`
- 反向应用检查：PASS（当前工作树可精确还原到固定上游基点）
- 不得把该补丁重复应用到已含改动的 `products/librechat-custom`

重建时在固定上游 commit 的干净检出中执行：

```bash
git apply --check /path/to/librechat-v0.8.8-v03-collaboration-20261106.patch
git apply /path/to/librechat-v0.8.8-v03-collaboration-20261106.patch
```

## V0.2.1 最新归档

`librechat-v0.8.8-lifecompanion-v021-memory-reminders.patch` 是当前完整源码补丁，
包含前轮已提交/未提交的 V0.1/V0.2 基础与本轮记忆、UI、提醒、测试增量，
共 41 个文件，含原未跟踪新源码。仍以原版
`e8f3be08623663d4ad7f7241e693c94469b63bb0` 为基点。
应用步骤同后文，但替换为这个新文件名；现有工作树不要重复应用。
已在临时 index 对原版执行 `git apply --cached --check`，真实 index 哈希未改变。
SHA256 与完整文件清单见 `evidence/v02-memory-reminders/patch-delivery.json`。
旧补丁保留，Vikunja/ntfy/Memos 源码未改，无额外上游补丁。

## V0.2 历史归档

`librechat-v0.8.8-lifecompanion-v02.patch` 是相对原版 LibreChat
`e8f3be08623663d4ad7f7241e693c94469b63bb0` 的完整补丁，包含 V0.1
已提交的消息接入钩子及 V0.2 未提交的统一前端修改。
根仓库不跟踪 `products/` 中独立仓库的源码，必须同步维护此归档。

仅在上述原版 commit 的干净独立检出中执行：

```powershell
git apply --check "H:\AI For research institute\LifeCompanion-Rebuild\patches\librechat-v0.8.8-lifecompanion-v02.patch"
git apply "H:\AI For research institute\LifeCompanion-Rebuild\patches\librechat-v0.8.8-lifecompanion-v02.patch"
npm ci --ignore-scripts --no-audit --no-fund
npm run frontend
```

现有 `products/librechat-custom` 已包含这些修改，不要重复应用。
构建和运行使用 `docs/RUNBOOK.md` 中的 Compose 叠加配置；每次构建成功后重启
LibreChat，使 Express 重新读取入口 HTML。不得因此升级锁定依赖或删除数据库。
本轮补丁使用独立临时 Git index 对原版 commit 执行 `git apply --cached --check`，
没有暂存或覆盖实际工作树。

密钥、运行账号、数据库及构建产物不属于补丁。Memos 源码未修改，无补丁。
