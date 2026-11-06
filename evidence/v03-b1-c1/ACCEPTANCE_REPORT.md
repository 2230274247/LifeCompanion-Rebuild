# LifeCompanion V0.3 B1 + C1 独立验收报告

验收日期：2026-11-04  
工作树：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103`  
分支：`feat/rebuild-p00-p07-20261103`  
基线提交：`e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`

## 结论

| 验收项 | 结果 | 说明 |
| --- | --- | --- |
| 工程闭环 | **PASS** | 真实 B0 PNG 已进入隔离私有媒体目录，完成鉴权读取、缩略图、原图、删除和元数据持久化。 |
| 页面展示 | **PASS** | “我的回忆”页面可见首张真实 Kolors 图文回忆卡；桌面端和移动端均通过浏览器验收。 |
| 自动生图调度 | **NOT ENABLED** | 自动图片生成、Worker 和外部调度在本轮验收进程中均关闭。 |
| 真实生图请求 | **0** | 本轮复用已经验收的 B0 图片，没有再次调用 Kolors 或 DeepSeek。 |
| 生产用户接入 | **未启用** | 使用合成用户、合成回忆和隔离数据库，不涉及真实用户数据。 |

本轮未出现需要标记为 `BLOCKED` 的交付项。

## 证据分类

- **REAL**：B0 已验收的 Kolors PNG 字节、FastAPI 鉴权媒体读取、网关转发、浏览器中的真实图片显示。
- **SYNTHETIC / MOCK**：测试用户、回忆记录、隔离 SQLite、Playwright 登录壳以及不可用 Memos 的隔离上游响应。
- **NOT ENABLED**：自动图片生成、正式 Worker、生产调度、真实用户自动创建回忆。
- **BLOCKED**：无。

## 真实图片与私有存储

首张图文回忆卡的私有原图：

`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\moment-media\b8f91103c130cce5\mom_101010101010101010101010\c46d710f6f2c449a80ef23d8f30fe9e5.png`

原图校验结果：

| 字段 | 值 |
| --- | --- |
| Pillow 实际格式 | PNG |
| 像素尺寸 | 960 x 1280 |
| 字节数 | 1,978,187 |
| SHA-256 | `9bbd0cb588f51cbf579235547f7e55aa4d8c06e09912f9c0881fabdfd31e240b` |
| moment_id | `mom_101010101010101010101010` |
| user_id | `life_d2748fbe6951d47379a8` |
| provider / model | `SiliconFlow` / `Kwai-Kolors/Kolors` |
| trace id | `ti_1u95f5u974melfugf5` |
| policy status | `PRIVATE_TEXT` |

API 下载副本：

`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\api-download.png`

API 下载副本与 B0 来源图、上述私有原图三者均为 960 x 1280 PNG、1,978,187 字节，SHA-256 完全一致。

缩略图：

`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\moment-media\b8f91103c130cce5\mom_101010101010101010101010\c46d710f6f2c449a80ef23d8f30fe9e5.thumb.jpg`

缩略图经 Pillow 完整解码为 JPEG，尺寸 640 x 853，97,977 字节，SHA-256 为 `fd6b78f966da5adfab7afb9dce73adf259d0868e76380e00094df5ad4fa3bf8f`。

## 工程闭环

- 复用现有 FastAPI、Moments、Worker、React 和 policy 体系，没有新增平行服务。
- `moment_media` 记录图片与 `moment_id`、`user_id` 的绑定，并保存 provider、model、MIME、尺寸、字节数、SHA-256、trace id、创建时间、Prompt 摘要和 policy 状态。
- 原图与缩略图写入隔离私有媒体根目录；写入采用同目录原子替换，读取时再次核对 SHA-256。
- `/api/v1/moments/{moment_id}/image` 和 `/thumbnail` 仅允许当前认证所有者读取。
- 媒体响应使用私有缓存策略、`nosniff`、inline 文件名和 ETag。
- 删除回忆会删除媒体记录及原图、缩略图文件；授权撤回路径会清理所属用户图片。
- 图片卡仅对 `generated` 状态且存在有效媒体、policy 未被隐藏的回忆开放。
- 纯文字卡仅对非空 `private_text`、`PRIVATE_TEXT` policy 和 `TEXT_ONLY` / `SAFE_SCENE` imageability 开放。
- `SKIP`、`PRIVATE_SKIP`、`NOT_APPLICABLE` 不会作为正式回忆卡展示。

## 页面验收

- “我的回忆”以图片为主、文字为辅展示首张真实 Kolors 图文卡，并保留“AI 生成 / AI 创作画面”标识。
- 支持本人认证缩略图、原图灯箱、原图查看和下载控件。
- 纯文字回忆卡正常显示。
- `PRIVATE_SKIP` 卡片未渲染。
- 桌面端无横向溢出：`scrollWidth=1440`、`clientWidth=1440`。
- 移动端无横向溢出：`scrollWidth=390`、`clientWidth=390`。
- 浏览器无 console error、无 page error、无 SiliconFlow/Chat provider 对外请求，自动生图请求数为 0。

浏览器视觉证据：

- 桌面回忆页：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\memories-desktop-1440.png`
- 移动回忆页：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\memories-mobile-390.png`
- 桌面详情：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\moment-detail-desktop-1440.png`
- 桌面原图灯箱：`H:\AI For research institute\LifeCompanion-Rebuild\.work\p00-p07-20261103\evidence\v03-b1-c1\runtime\acceptance-20261104-01\moment-original-desktop-1440.png`

已实际打开图片进行视觉检查：画面为清晨厨房、虚构人物为薄荷浇水，并有白瓷杯与吐司；主体和生活场景清晰，AI 标识可见。人物手部与浇注动作存在轻微合成痕迹，但不影响本轮工程闭环验收。

## 自动化与接口结果

- API 验收：PASS，详见 `api-probe.json`。
- 浏览器验收：PASS，详见 `browser-verification.json`。
- 未认证列表读取返回 401。
- 本人原图与缩略图读取返回 200。
- 跨用户原图读取返回 404。
- 删除测试同时移除 2 个媒体文件。
- 后端相关回归：25 passed。
- `Memories.spec.tsx`：7 passed。
- TypeScript 类型检查：PASS。
- data-provider 构建：PASS。
- client 生产构建：PASS。
- Gateway 测试：3 passed。
- `git diff --check`：PASS。

## 运行边界与未完成项

- 本轮自动生图、Worker 和外部调度均未启用：
  - `LIFE_MOMENT_IMAGE_GENERATION_ENABLED=false`
  - `LIFE_MOMENT_WORKERS_ENABLED=false`
  - `LIFE_MOMENT_SCHEDULER_EXTERNAL=true`
- Playwright 登录使用合成认证壳，未修改或验证正式 LibreChat 生产登录。
- Memos 在当前隔离环境不可用，相关回忆列表使用隔离 mock 响应；该部分明确属于 MOCK。
- 稀有卡、镭射卡、三时段自动正式上线、真实用户自动调度与生产监控留待后续阶段。
- 未读取、打印或记录 API Key，未修改真实用户数据。
- 未提交、未合并分支、未部署公网。
- 本轮启动的隔离服务已关闭，`8011`、`3002`、`4175` 均不再监听。
