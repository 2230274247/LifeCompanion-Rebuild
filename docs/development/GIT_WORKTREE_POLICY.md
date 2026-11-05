# Git、Worktree 与永久项目规范

本文件是 `LifeCompanion-Rebuild` 的永久工程治理规范。任何 Codex、开发者或自动化
Agent 在开始开发、测试、整理或提交前，都必须先阅读本文件。本规范不替代数据备份、
隐私审查或产品验收。

## 1. 唯一项目基线

- 唯一有效产品代码根目录是 `H:\AI For research institute\LifeCompanion-Rebuild`。
- 禁止使用、恢复或重新克隆已删除的旧项目。
- 新功能必须基于真实工作树和已有上游源码开发。
- 工作树不干净不是另建项目副本的理由；应识别改动来源并建立可追踪检查点。

## 2. 每个任务开始先做快速 Git 审查

只读检查，不先备份，不先清理：

```powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git worktree list --porcelain
git remote -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/inspect-workspace.ps1
```

发现未提交内容时，先按来源和类型分类：产品源码、测试、文档、验收证据、配置模板、
运行数据、敏感文件、临时产物、其他 Worktree。不得直接假定未提交代码无效，也不得
为了得到干净的 `git status` 删除文件或把它们全部忽略。

禁止因为普通 Git Dirty 状态而重复创建全量项目快照。Git 能恢复的源码不重复做文件级
备份；数据库、上传件、运行状态等 Git 无法恢复的数据仍按第 8 节独立备份。

## 3. 默认只有一个主要开发工作树

默认以项目根目录为主要开发工作区。额外 Worktree 只在确有并行隔离需求时创建，并须
记录分支、任务、负责人和生命周期。

现有 Worktree 处理顺序：

1. 记录分支、HEAD、Remote、独立提交和未提交文件。
2. 与主要分支比较 ahead/behind、提交内容、工作树差异和重复功能。
3. 先提交或另存有价值成果，再验证功能和数据来源。
4. 冲突时记录并停止有风险的自动整合，不允许任意选择一侧覆盖。
5. 只有确认没有独立成果和未提交内容后，才可安全移除 Worktree。

禁止直接删除、强制移除或覆盖任何 Worktree。

## 4. 分阶段自动提交

每完成一个可独立验证的阶段或功能，执行：

1. 检查改动来源和任务范围。
2. 排除敏感文件、真实业务数据和生成产物。
3. 运行最相关的测试、类型检查或构建。
4. 写入开发日志和验收结果，明确 PASS、PARTIAL、BLOCKED。
5. 只暂存属于当前任务的文件。
6. 创建本地 Commit。
7. 记录 Commit SHA。
8. 再检查剩余未提交文件并写明原因。

允许自动执行安全的本地 Commit，不需要逐次询问用户。推荐提交信息：

```text
feat(collab): implement shared memory conversation
fix(auth): prevent cross-user data access
test(collab): add multi-account permission regression
docs(project): update development checkpoints
chore(git): establish worktree governance
```

测试未通过时可以提交明确标记的 WIP 检查点，但必须同时在日志和提交正文写明未通过项，
绝不能把 WIP 标成 PASS 或已完成。

## 5. 应提交与禁止提交

应提交：

- 正式源码和上游补丁
- 合法且不含秘密的配置模板
- 数据库迁移脚本
- 自动化测试和测试夹具说明
- 设计规范、任务文档和验收报告
- 第三方源码清单、版本指纹和许可证记录

默认不提交：

- `.env`、API Key、密码、Token、Cookie、私钥
- 真实数据库、业务数据、用户聊天、回忆、照片、音频
- `node_modules`、Python `.venv`、依赖下载目录
- `dist`、缓存、编译产物和运行日志
- 未脱敏截图、账号配置和个人资料

`.gitignore` 只能忽略确实不应版本化的内容，不能用于掩盖真实源码或验收问题。

## 6. 安全自动提交工具

项目提供以下 PowerShell 工具：

```text
scripts/git/inspect-workspace.ps1   只读报告 Git、Worktree、Remote 和分类
scripts/git/checkpoint.ps1          按明确路径检查、暂存并创建本地 Commit
scripts/git/worktree-audit.ps1      只读报告 Worktree 独立提交和未提交修改
```

`checkpoint.ps1` 必须显式提供 `-Path`，禁止全量 `git add -A`。工具必须拒绝敏感路径、
疑似秘密内容、运行数据库、依赖目录和异常大文件。脚本不得默认执行破坏性命令。

永久禁止无条件执行：

```text
git reset --hard
git clean -fd
git push --force
git worktree remove --force
```

## 7. 本地提交与远程推送分开

每个阶段默认创建本地 Commit。只有远程仓库和 upstream 已核实有效时才按发布策略推送。
不得编造 Remote，不得因推送失败反复备份。

无 Remote 时记录：

```text
LOCAL_COMMITTED / PUSH_BLOCKED_NO_REMOTE
```

本地开发可以继续。

## 8. 大型备份与有状态数据

以下操作前必须独立备份有状态数据，并保留恢复说明、版本指纹和校验结果：

- 数据库结构变更或迁移
- 高风险依赖升级
- 大规模目录迁移
- 可能导致真实业务数据不可恢复的操作

备份应排除可重建的 `node_modules`、`.venv`、缓存和编译产物。Git Commit 不能替代
数据库备份；数据库备份也不能替代源码 Commit。

## 9. 多 Agent 协作

- 两个 Agent 不得无协调地同时改写同一工作树。
- 每个 Agent 必须有明确分支、任务和文件所有权。
- 并行结束前统一审查差异、测试和证据。
- 不得为快速合并覆盖另一 Agent 尚未提交的代码。
- 合并冲突必须人工或由有明确依据的整合步骤解决。

## 10. 任务收尾

每次任务结束必须报告：

- 当前分支和 HEAD
- 本次 Commit SHA
- 已通过和未通过的测试
- 剩余未提交文件及原因
- Worktree 与 Remote 状态
- 是否已推送
- 下一次任务应从何处继续

不得为了显示干净而强行提交、删除或回退。失败、阻塞和未验证内容必须如实保留。

## 标准检查点流程

```powershell
$root = "H:\AI For research institute\LifeCompanion-Rebuild"
Set-Location $root

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/inspect-workspace.ps1

# 运行当前阶段相关测试后，只提交本任务明确文件
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/checkpoint.ps1 `
  -Message "feat(collab): implement shared memory conversation" `
  -Path "services/life-core/app/collaboration.py", `
        "services/life-core/tests/test_collaboration.py"

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/worktree-audit.ps1
git status --short --branch
```

Governance regression tests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/git-governance.ps1
```
