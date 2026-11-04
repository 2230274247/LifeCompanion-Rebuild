# 上游补丁归档

## P00-P07 当前完整归档（2026-11-04）

`librechat-v0.8.8-rebuild-p00-p07-20261104.patch` 是当前可部署的完整
LibreChat 工作树快照，共 68 个文件、257739 bytes，基点仍为原版
`e8f3be08623663d4ad7f7241e693c94469b63bb0`。

SHA-256：

```text
25531395ba1548c4fe57f0e2ef91500b5d07f4eaba2ca3dcdac574a14df35f3f
```

使用独立临时 index 对原版 commit 执行 `git apply --cached --check` 通过，
真实暂存区未改变。补丁包含继承的 P00-P07 前端、记忆、提醒、工具卡与生图
UI 差异，不是单次提交的纯增量。补丁不含真实 Key、运行账号、数据库、上传
或编译产物。

新机器应从原版 commit 开始：

```powershell
git clone --branch v0.8.8 --single-branch https://github.com/LibreChat-AI/LibreChat.git products\librechat-custom
git -C products\librechat-custom checkout -b lifecompanion-baseline
git -C products\librechat-custom apply --check patches\librechat-v0.8.8-rebuild-p00-p07-20261104.patch
git -C products\librechat-custom apply patches\librechat-v0.8.8-rebuild-p00-p07-20261104.patch
```

Ubuntu 将反斜杠改为 `/`。推荐直接运行
`scripts/bootstrap-lifecompanion.ps1` 或 `scripts/bootstrap-lifecompanion.sh`，
脚本会固定版本、预检补丁、构建前端并创建 Python venv。

## Rebuild P00-P04 当前累计归档

`librechat-v0.8.8-rebuild-p00-p04-20261104.patch` 保存截至本轮的60份上游源码/
配置差异，包括继承的原有修改，不是仅P04的diff。基点仍为原版
`e8f3be08623663d4ad7f7241e693c94469b63bb0`；
临时index执行 `git apply --cached --check` 通过，真实index摘要未变。
只包含代码及使用环境变量占位符的配置，无运行凭据、数据库、构建产物。
SHA-256和文件清单：`evidence/p04/upstream-patch-delivery.json`。
首次遇到原版忽略librechat.yaml；确认Key为环境占位符后，仅对此文件
在临时index使用-f，未改.gitignore或真实暂存区。旧补丁继续保留。
本归档不表示P04完整通过；图像provider/模型评分仍有缺口。

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

仅在上述原版 commit 的干净独立检出中执行（从仓库根目录运行）：

```powershell
git -C products\librechat-custom apply --check patches\librechat-v0.8.8-lifecompanion-v02.patch
git -C products\librechat-custom apply patches\librechat-v0.8.8-lifecompanion-v02.patch
Set-Location products\librechat-custom
npm ci --ignore-scripts --no-audit --no-fund
npm run frontend
```

现有 `products/librechat-custom` 已包含这些修改，不要重复应用。
构建和运行使用 `docs/RUNBOOK.md` 中的 Compose 叠加配置；每次构建成功后重启
LibreChat，使 Express 重新读取入口 HTML。不得因此升级锁定依赖或删除数据库。
本轮补丁使用独立临时 Git index 对原版 commit 执行 `git apply --cached --check`，
没有暂存或覆盖实际工作树。

密钥、运行账号、数据库及构建产物不属于补丁。Memos 源码未修改，无补丁。
