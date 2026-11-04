# Configuration

配置分为三层：

1. 仓库代码与模板。
2. 本机非敏感环境文件 `infra/.env`、`products/librechat-custom/.env`。
3. 项目母目录唯一云模型密钥文件 `model_api_keys.env`。

真实密钥不得写入仓库文件、Compose 构建参数、`VITE_*`、`NEXT_PUBLIC_*`、
浏览器存储或普通日志。

## 云模型密钥

默认路径：

```text
<parent-directory>/model_api_keys.env
```

可由后端绝对路径覆盖：

```dotenv
LIFECOMPANION_KEYS_FILE=/absolute/path/to/model_api_keys.env
```

相对路径会被拒绝。`life-core` 在进程启动时加载文件，非空值覆盖同名环境变量。
系统按以下供应商标记 `SET` / `MISSING`：

| Provider | 变量 | 用途 |
| --- | --- | --- |
| DeepSeek | `DEEPSEEK_API_KEY` | 记忆分类、评分、工具对话 |
| Zhipu | `ZHIPU_API_KEY` | 可替代文本模型 |
| DashScope | `DASHSCOPE_API_KEY` | 保留供应商入口 |
| Moonshot | `MOONSHOT_API_KEY` | 保留供应商入口 |
| OpenAI | `OPENAI_API_KEY` | 保留供应商入口 |
| SiliconFlow / Kolors | `IMAGE_PROVIDER_API_KEY` 或 `SILICONFLOW_API_KEY` | 图片生成 |

`IMAGE_PROVIDER_API_KEY` 优先。未使用其他供应商时无需购买或填写。

## 文本模型

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `LIFE_LLM_PROVIDER` | `deepseek` | 当前只接受 `deepseek` / `zhipu` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 文本模型 |
| `ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | 智谱端点 |
| `ZHIPU_MODEL` | `glm-4.7` | 智谱模型 |
| `MEMORY_LLM_MAX_TOKENS` | `2048` | 单次请求上限 |
| `MEMORY_LLM_REQUEST_BUDGET` | `0` | 数据库累计请求上限，`0` 关闭 |

## 回忆和生图

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `LIFE_MOMENT_WINDOWS_V03` | `false` | 新回忆窗口开关 |
| `LIFE_MOMENT_WORKERS_ENABLED` | `true` | 启动回忆后台线程 |
| `LIFE_MOMENT_IMAGE_GENERATION_ENABLED` | `false` | 自动生图显式开关 |
| `LIFE_MOMENT_IMAGE_PROVIDER` | 空 | 当前使用 `kolors` |
| `LIFE_MOMENT_IMAGE_MODEL` | `Kwai-Kolors/Kolors` | 生图模型 |
| `LIFE_MOMENT_IMAGE_REQUEST_BUDGET` | `0` | 持久化请求硬上限 |
| `LIFE_MOMENT_MEDIA_ROOT` | life-core data 下 | 私有图片目录 |
| `LIFE_MOMENT_SCORING_REQUEST_BUDGET` | `0` | 评分预算 |
| `LIFE_MOMENT_SCORING_MAX_CANDIDATES` | `8` | 单轮候选上限 |
| `LIFE_MOMENT_SCORE_LEASE_SECONDS` | `120` | 防并发租约 |

提示词版本固定为 `moment-evidence-v1`。正式自动生图以用户原文证据为唯一
事实依据，不从文本模型接收自由扩写提示词。证据不足时 `image_eligible=false`。

模型超时、5xx 或未知结果不会无限重试；失败会进入可审计状态。生成后视觉
一致性自动复核尚未实现，当前由受控人工验收，状态为 `NOT_TESTED`。

## 内部服务与存储

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `LIFE_INTERNAL_TOKEN` | 空 | LibreChat 到 life-core 的服务端令牌 |
| `JWT_SECRET` | 空 | LibreChat access token 签名与校验 |
| `JWT_REFRESH_SECRET` | 空 | LibreChat refresh secret |
| `CREDS_KEY` / `CREDS_IV` | 空 | LibreChat 凭据加密密钥与 IV |
| `MEMOS_BOOTSTRAP_ADMIN_PASSWORD` | 空 | Memos 首次启动管理员密码，仅存本机环境文件 |
| `MEMOS_BASE_URL` | `http://127.0.0.1:5230` | Memos 地址 |
| `MEMOS_API_TOKEN` | 空 | 服务端 Memos PAT |
| `LIFE_DATABASE_PATH` | `services/life-core/data/life-core.sqlite3` | SQLite 路径 |
| `LIFE_TIMEZONE` | `Asia/Hong_Kong` | 用户默认时区 |
| `LIFE_ALLOWED_ORIGINS` | 本机 3001 | CORS 白名单 |
| `LIFE_LIBRECHAT_BASE_URL` | `http://127.0.0.1:3080` | 源消息所有权校验 |

## Docker / 端口

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `LIFE_COMPOSE_PROJECT` | `lifecompanion-upstream` | Compose 项目名 |
| `LIFE_BIND_ADDRESS` | `127.0.0.1` | 容器绑定地址 |
| `LIFE_LIBRECHAT_PORT` | `3080` | LibreChat 宿主端口 |
| `LIFE_MEMOS_PORT` | `5230` | Memos 宿主端口 |
| `LIFE_CORE_HOST_URL` | `http://host.docker.internal:8010` | 容器访问 life-core |
| `LIFE_NTFY_CONTAINER` | `lifecompanion-ntfy` | 提醒供应容器的受控名称 |
| `LIFE_PUBLIC_URL` | `http://127.0.0.1:3001` | LibreChat 对浏览器公开的同源入口 |
| `LIFE_CHAT_INTERNAL_URL` | `http://127.0.0.1:3080` | LibreChat 服务端内部地址 |
| `LIFE_ALLOW_REGISTRATION` | `true` | 是否允许受控新账号注册；公网开放前应评估 |

Compose 先读取 LibreChat 的 `.env`，再读取父目录 `model_api_keys.env`。
后者存在时，云模型值以后者为准；文件缺失时 Compose 仍可启动本地非云功能。

## 外部工具和提醒

| 字段 | 说明 |
| --- | --- |
| `LIFE_TOOL_REQUEST_BUDGET` | 外部工具请求上限，`0` 关闭 |
| `LIFE_TOOL_WEATHER_PROVIDER` | 仅支持受控 `open_meteo` |
| `LIFE_TOOL_ROUTE_PROVIDER` | 仅支持受控 `osrm_demo` |
| `LIFE_TOOL_SEARCH_URL` | 管理员配置的 loopback SearXNG URL |
| `LIFE_REMINDER_SCHEDULER_EXTERNAL` | 是否由独立调度器执行 |
| `LIFE_MOMENT_SCHEDULER_EXTERNAL` | 是否由外部组件生成结算意图 |

Vikunja/ntfy 为可选功能。`infra/.env.reminders` 必须使用已核验的镜像 digest，
且每用户 token、topic 与回调用永久被忽略的运行时文件，不得提交。

## 配置变更和重启

- 父目录 Key 文件：重启 `life-core`；若 LibreChat 也使用该模型，重启 LibreChat。
- `infra/.env`：重新执行 Compose；必要时重启对应容器。
- Python 服务配置：重启 `life-core`。
- 网关目标：重启 Node gateway。
- 前端配置：重新构建前端并重启 LibreChat。

当前没有声称支持密钥热更新。

`bootstrap-lifecompanion.ps1/.sh` 在首次复制环境模板后，会为
`LIFE_INTERNAL_TOKEN`、Memos 初始管理员、JWT、LibreChat 凭据加密和
Meilisearch 生成随机值；已有非占位值不会被覆盖。Memos 管理员用户名为
`lifecompanion-admin`，密码只保存在本机 `infra/.env`。JWT、凭据加密和
Meilisearch 值保存在被忽略的 `products/librechat-custom/.env`，不得提交或
粘贴到日志。
