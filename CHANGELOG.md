# Changelog

## 2026-11-04

### Added

- 父目录统一云模型密钥加载，服务端 `SET` / `MISSING` 脱敏诊断。
- `moment-evidence-v1` 生图证据链、图片幂等键和非空唯一索引。
- 晨跑、浇花、家人做饭三例真实 Kolors 调用与人工一致性验收。
- Windows PowerShell / Ubuntu shell 初始化、启动和健康检查脚本。
- `DEPLOYMENT.md`、`CONFIGURATION.md`、`SECURITY.md` 与第三方许可说明。
- 当前 LibreChat `v0.8.8` 累计补丁及固定基线应用检查。

### Changed

- 自动生图不再让 LLM 自由扩写用户事实，改为从原文可追踪证据生成提示词。
- `event_at`、`message_at`、`generated_at`、`display_slot` 分离存储。
- Compose 端口、项目名、容器绑定地址和 life-core 地址可配置。
- Linux 容器通过 `host.docker.internal:host-gateway` 访问宿主机服务。
- 网关目标和 life-core 监听地址可由环境变量配置。
- 初始化门槛调整为 Node.js 24 LTS+，与上游依赖声明一致。

### Fixed

- 生图主体被商铺、住宅外立面或静物替换的问题。
- 浇水事件只出现绿植和水壶、没有浇水动作的问题。
- 事件发生时间被错误写成消息或图片生成时间的问题。
- 历史合成测试回忆造成 UI 选择器歧义的问题。
- `.gitignore` 未覆盖嵌套 `evidence/**/runtime/` 和 SQLite 运行文件的问题。

### Security

- 云模型 Key 从非敏感 `.env.example` 移除，集中到项目母目录专用文件。
- 前端保持不读取云模型 Key；服务端健康检查不返回密钥值。
- 数据库、媒体、环境文件、运行证据和本地工作区锁不进入 Git。

### Validation

- `services/life-core`：`319 passed, 1 warning`
- Gateway：`4 passed`
- 真实 Kolors：3/3 HTTP 200，人工核对 PASS
- 当前新图 UI：聊天与回忆页 PASS，检查期间 0 个新付费生图请求
- 本地 release-equivalent 空目录 clone、初始化、真实聊天、记忆发布、
  用户隔离和重启持久化 PASS

### Known limitations

- 生成后视觉模型自动复核尚未实现，状态为 `NOT_TESTED`。
- GitHub remote 未配置，真实 clone/push 状态为 `BLOCKED_REMOTE`。
- 空目录演练使用本地 Git 仓库克隆，不是 GitHub clone；Ubuntu 本轮只完成
  24.04 `bash -n` 语法检查，未在 Ubuntu 主机执行完整运行演练。
- 主仓库尚未由项目所有者声明开源许可证。
