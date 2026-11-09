# P5 真实模型验收证据（2026-11-09）

本目录仅保留隔离合成账号的脱敏证据。真实密钥、账号材料、JWT、PAT、数据库、原始运行日志均不纳入版本控制。

## 运行边界

- 产品代码：父工作树 `claude/epic-goldwasser-ad14c0`，起点 `8202ff137c5f73e96b7570b638c71fa440934c2a`；本轮变更限于抽取器与对应测试、文档/证据。
- LibreChat：独立嵌套仓库 `d0dc65d240d833772c7eb7361529375b7ed6db5b`；本轮未改动上游源码。
- 聊天与记忆抽取/规划使用已有 DeepSeek 配置；智谱生成配额不足，不作为本轮验收提供者。没有打印或归档密钥。
- life-core：`127.0.0.1:8010`；独立 SQLite `infra/runtime/p5/core-data-r3/life-core.sqlite3`。
- LibreChat：`127.0.0.1:3810`；Mongo：`127.0.0.1:27019`，专用 `LibreChatP5` 数据库；Memos：`127.0.0.1:15231`，专用容器/卷。
- 嵌入模型：H 盘既有固定修订 BGE-large 中文量化文件，1024 维；完整 Python 环境已装 fastembed 0.7.4。离线预热实际返回 `ready`，未下载权重。
- 复用已有好友模块、LibreChat 聊天组件和 Memos 官方 API；未替换或清理正式服务。

## 已确认的修复与验证

1. 抽取器请求 `response_format=json_object` 时明确要求返回 JSON，修复 DeepSeek 返回 400 的协议不匹配。
2. 同批结构合法候选中，仅拒绝无法落地到原话的候选，保留其余通过 grounding 的候选；全部被拒仍返回 `MEMORY_UNGROUNDED_OUTPUT`。格式/模式非法仍按原合同整批拒绝。
3. 验收环境原 Python 缺少 fastembed；改用 H 盘已有完整环境，不修改主工作树的虚拟环境。恢复后实测 9 条记忆对应 9 条 1024 维向量。
4. 验收驱动依照服务端实际生成的用户消息 ID 关联助手回复，且多轮请求使用上一条助手消息为 parent。最初两轮的回复复用/超时误判全部废弃。
5. 真实 A2 暴露 `/assistant/execute` 丢掉 profile 类语义命中：修复为把 `profile_match_ids` 中对应的已授权资料送入任务 `items`，不传无关背景资料。保持原证据格式，无需修改 LibreChat 上游。真实复测正确回答“龙井茶”并附来源；跨会话纠正正确回答“上海徐汇区”。
6. 最终 life-core 全量回归：`302 passed, 1 skipped, 1 warning in 73.61s`；抽取模块：`84 passed`；执行接口：`5 passed`；Git 治理：`24 passed, 0 failed`。warning 为既有 Starlette/httpx 弃用提示。

## 判定方法与限制

- `api-matrix.json` 保存最终聊天矩阵原始自动标记，`reviewed-results.json` 才是依据完整证据复核后的正式判定；两者不可互换。
- `supplement.json` 保存修复资料传递前完整 `/assistant/execute` 响应、本轮聊天回复、执行时间与消息 token_count；`profile-retest.json` 保存该修复后的 A2/A4/A5 新会话、所有者引用读取和最终库状态。独立执行探针和聊天内部执行是不同请求，不能伪称同一 planner 回执。
- 权限状态读取 `results[].status`，分页读取 `results[].retrieval`；顶层 `executed` 仅表示完成调度。
- A5 要求后端实际 `withdrawn` 且新会话不复活；单次回复未说出地址不足以通过。
- D1 必须检查链接确实对应授权记忆；D2 必须真正触发截断/下一页，普通概览不算分页验收。
- token_count 为 LibreChat 保存的消息计数，不是提供方完整 usage。未取得完整输入/输出 token 与计费回执，不估算人民币成本。
- 当前安装的浏览器预览无法附加外部 URL，浏览器交互与截图记为 `NOT TESTED`。后端由 preview 工具启动并检查日志，真实用户入口通过聊天 HTTP 协议运行。
- 测试初次从根目录运行缺少 PYTHONPATH（收集失败），随后补齐导入路径；新增测试第一次使用非法夹具键 `habit` 导致两项失败，改为合法键 `interest` 后完成上述全量回归。没有隐去失败过程。

## 重现入口

本机 gitignored 的 `infra/runtime/p5/` 包含隔离启动、合成账号创建和真实聊天驱动，不得直接提交这个运行目录。重现时先读 `docs/development/GIT_WORKTREE_POLICY.md`，使用隔离数据与既有密钥，确认 4 个端口只绑定回环；用完整 Python 环境启动 `serve_core.py`，再运行 `run_p5.py` 与 `supplement.py`。这套环境以本机 H 盘路径为前提，不能当作通用部署包。

回归命令需设置 `PYTHONPATH` 指向本工作树的 `services/life-core`，然后执行 Python 的 `-m pytest services/life-core/tests -q`。Git 治理使用 `powershell -NoProfile -File tests/git-governance.ps1`。

最终复核为 7 PASS、3 FAIL、3 PARTIAL、1 NOT TESTED，整体 PARTIAL。自然语言撤回未实际撤回、发生日混淆、混合提醒规划不可用均保留为失败。

本机验收后端已通过 preview_stop 停止；停止三个 p5 容器被自动审批以 Interfere With Workloads 拒绝，仍保留在 127.0.0.1 的 3810/15231/27019，未删除容器或数据卷。完整收尾与 Git 检查点信息见 [中文验收日志](../../docs/development-log/2026-11-09_21-29_已有密钥真实记忆P5验收_开发验收.md)。
