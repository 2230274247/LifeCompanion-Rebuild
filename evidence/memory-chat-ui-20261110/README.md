# P5 完整聊天与真实记忆页验收（2026-11-10）

本目录只记录隔离合成账号。结论：本轮两项验收 PASS；不代表原 P5 全矩阵、正式部署、长期稳定性或计费已通过。

## 真实运行结果

- [第一轮三次持久化回复](results.json)：真实 DeepSeek，首轮叙述、同会话追问、新会话召回均完成；`error=false`、`unfinished=false`。约 5.30 / 6.22 / 4.12 秒。
- [归档启动器复现](reproduction-results.json)：重启到 `scripts/serve-memory-acceptance.py` 后再跑三轮，PASS；约 7.23 / 6.20 / 4.12 秒。健康接口明确 `extractor=deepseek`，不是规则抽取。
- [浏览器实际发送与重读](browser-turn.json)：真实输入框填写并 Enter，回复“昨天我参观了上海科技馆，并看到了有趣的机器人展览。”；聊天 API 重读确认持久化。来源记忆 GET 200，Memos 官方 `/api/memos/...` GET 200，正文与 life-api 相等。
- [记忆页](memories-desktop.png)、[详情桌面](memory-detail-desktop.png)、[详情移动端](memory-detail-mobile.png)、[聊天](chat-browser.png)。日期为发生日 2026-11-09，记录日在 2026-11-10。
- [列表结构](memories-desktop.yml)、[详情结构](memory-detail.yml)、[聊天结构](chat-browser.yml)、[网络](memory-network.txt)、[390px 布局](mobile-layout.json)。移动端文档宽度和视口均 390，无横向溢出；测试后恢复桌面尺寸。

数据路径：`infra/runtime/p5/core-data-e2e-chat/life-core.sqlite3`，仅合成数据。Mongo 使用已有 `LibreChatP5`（127.0.0.1:27019），Memos 使用已有隔离实例 127.0.0.1:15231。容器 p5-librechat 仅映射 127.0.0.1:3810；life-core 127.0.0.1:8010；网关 127.0.0.1:3001。未接触正式用户库；好友/空间模块保留。

## 根因与修正

原终态错误不是记忆模块未能保存。LibreChat 日志在相同请求前报告 `Invalid conversation ID: occ-real-8d215bc1`，随后 `saveMessage` 返回空，终态控制器据此拒绝发布完成。上游要求完整 UUID。使用 UUID 后原消息和回复均正常持久化，未放宽产品校验。

验收脚本另需按实际协议处理：桌面 User-Agent、服务端分配的用户消息 ID、结构化 `content[].text`、新会话消息 GET 的 404。否则会出现已生成回复但验收脚本误判超时。持久化脚本用服务器返回的行与父子关系校验，不把请求 HTTP 成功当作回复完成。

初次临时启动器错误地让基础文件中的空 DeepSeek 配置屏蔽后加载的有效配置，健康状态显示 rules。修正后才执行最终两轮真实抽取验收；早期香山事件只作为诊断保留，不作为真实 DeepSeek 抽取证据。

## 可复现入口

1. 保留已有隔离 p5-mongo / p5-memos 和合成账号映射，账号文件只留 `infra/runtime/p5/lc-account.json`（email/password）。先按项目既有 bootstrap 接口映射该合成账号到隔离 Memos 身份。勿复制正式数据库。
2. 上游固定 HEAD 为 `4b83c57a16d3db1f7ef9425d7c6a395037cc87c7`，工作树源码及 client/dist 均取 epic；本轮修正了旧配置误挂 elegant/client/dist 的问题。若需重建，在该上游工作区运行 `npm run frontend`。
3. `infra/compose.memory-acceptance.yaml` 是可移植配置。设置 P5_SOURCE_ROOT 为当前工作树、P5_CONFIG_ROOT 为已有凭据配置根目录，通过 Compose 的 `--env-file` 安全读取 LIFE_INTERNAL_TOKEN；不要输出完整 `docker compose config`，只用 `config --quiet`。该模板已做配置校验，本轮实际重建使用等价的本地 `infra/runtime/p5/compose.p5.yaml`。
4. life-core 使用 H 盘已有完整 Python venv 与离线 embedding-models。示例（在工作树内；启动服务时本会话使用 `.claude/launch.json` 的 preview_start）：

```bash
"H:/AI For research institute/LifeCompanion-Rebuild/.claude/worktrees/elegant-visvesvaraya-f65860/services/life-core/.venv/Scripts/python.exe" scripts/serve-memory-acceptance.py --config-root "H:/AI For research institute/LifeCompanion-Rebuild" --embedding-cache "H:/AI For research institute/LifeCompanion-Rebuild/.claude/worktrees/elegant-visvesvaraya-f65860/services/life-core/data/embedding-models"
```

启动器仅导入所需 JWT/internal/DeepSeek 配置，数据库必须位于当前工作树 p5 runtime，启动前在线备份已有合成 SQLite；不下载模型，也不继承正式 Memos/提醒账号映射或生图密钥。网关使用现有 `apps/product-portal/server.mjs`，环境为 PORT=3001、HOST=127.0.0.1、LIFE_CHAT_TARGET=http://127.0.0.1:3810、LIFE_CORE_TARGET=http://127.0.0.1:8010。

5. 服务就绪后运行（会调用真实付费模型，仅写隔离合成账号）：

```bash
python scripts/acceptance-memory-chat.py --account-file infra/runtime/p5/lc-account.json --output evidence/memory-chat-ui-20261110/reproduction-results.json
```

脚本登录后使用真实会话 JWT，依次发送、重读持久化消息、轮询记忆列表/详情并新开会话召回；不伪造 JWT、不直接写数据库。重复同一合成事件可能合并来源，因此 event.conversation_id 可保留首次会话；source_message_ids 必须包含本次真实写入消息。

## 验证与边界

- Memories Jest：18 passed；client `tsc --noEmit` PASS；改动 TS/TSX ESLint PASS；client production build PASS。
- Git 治理回归：24 passed；上游 `git diff --check` PASS；归档补丁反向应用检查 PASS；Compose `config --quiet` PASS。
- 浏览器已有 `/api/tags` 403（BOOKMARKS 权限），未影响聊天或记忆；重启 life-core 时出现过一次通知请求 502，恢复后 200。未声称全站零错误。
- 原 P5 14 项未重跑，提醒/联网属于另一个工作树成果，未合并、不计入本次通过项；未做长时间压力、多账号权限全回归、真实图片生成、完整账单或正式部署验收。
- `npm run lighthouse` 未运行：本轮交付源码是发生日期展示及验收工具，没有改变启动、认证、配置加载产品链路或消息加载实现。
- 上游包级发生日期实现 `4b193f81e` 与本轮 UI `4b83c57a1` 一并归档于 [增量补丁](../../patches/librechat-memory-occurrence-ui-20261110.patch)。基点 `ff42cacdaa11bbcbe0730c94591d746068585b77`，30,247 bytes，SHA256 `e8428dcab4a1bb5af47f2735d6d14447719210156de83ce793ad37f6c71b6a1d`。不要重复应用到已有提交的上游树。
