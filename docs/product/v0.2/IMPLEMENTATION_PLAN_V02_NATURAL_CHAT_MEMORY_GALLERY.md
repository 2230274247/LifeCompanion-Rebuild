# 拾光 V0.2 自然聊天与图文影集 · 文件级实施计划

日期：2026-11-05  
依据：`docs/product/v0.2/AUDIT_V02_NATURAL_CHAT_MEMORY_GALLERY.md`

## 总体策略

按 S1 → S2 → S3 → S4 增量实施。每一阶段先做最小代码改动，再运行目标测试和实际页面检查。
不使用 Mock 数据替代真实 API 验收；演示素材不写入正式库；不执行 Git Push、公网部署或破坏性数据库操作。

## S1 聊天自然化

目标：普通生活分享自然、简短、只基于用户明确事实；明确创作请求仍可执行；后台抽取/生图不进入聊天输出。

| 文件 | 变更 | 验证 |
| --- | --- | --- |
| `products/librechat-custom/librechat.yaml` | 为两个拾光模型规范加入同一版本化 `promptPrefix` | YAML 解析、配置检查 |
| `docs/product/v0.2/prompts/life-companion-chat.v1.md` | 自然聊天系统提示词版本源 | 与 YAML 内容一致性检查 |
| `docs/product/v0.2/chat-quality-evaluation.v1.json` | 50 条脱敏输入、模式与断言 | 样本数、分类覆盖、禁止词检查 |
| `scripts/check-life-chat-quality.mjs` | 静态质量门禁：样本、Prompt 关键约束、管理员接口测试路径 | Node 脚本退出码 |
| 现有消息渲染三处 | 只在服务端确认管理员时显示测试组件；不改变普通消息结构 | 前端相关测试 |

不在本阶段：重写模型调用框架、把记忆抽取合并进聊天回复、真实付费模型批量调用。

## S2 图文影集

目标：打开 `/memories` 直接看到日期分组下的图文卡片；搜索/日期/排序可组合；详情展示大图、正文、来源与 AI 声明；移动端单列。

| 文件 | 变更 | 验证 |
| --- | --- | --- |
| `packages/data-provider/src/life.ts` | 增加向后兼容的 `media` 与图片元数据字段 | 数据提供器类型检查 |
| `client/src/components/Life/Memories.tsx` | 移除首屏任务列表，改为影集、日期分组、轻量工具栏、高级筛选 | Jest 列表/空态/错误/筛选 |
| `client/src/components/Life/MemoryCard.tsx` | 新增图文卡片、图片失败降级、AI 标注、framer-motion 进入 | 组件测试、键盘焦点 |
| `client/src/components/Life/MemoryDetail.tsx` | 新增详情结构与大图查看 | 详情测试 |
| `client/src/components/Life/MemoryImageDialog.tsx` | 复用 Radix Dialog 做图片放大、Esc、焦点恢复 | Dialog 测试 |
| `client/locales/en/translation.json` | 增加影集相关本地化 key | 本地化 key 检查 |
| `client/src/components/Life/__tests__/Memories.spec.tsx` | 更新真实数据、无图、图片失败、详情与移动端语义测试 | Jest |

保留 `/memories/:memoryId` 路由与 URL 筛选状态；`MomentList` 只在设置/管理入口保留，
不删除既有生成管理能力。

## S3 后台自动发布与媒体关联

目标：生成成功后自动发布到现有私有 Memos/事件链路；同一事件幂等；授权撤销、Provider 失败和 Memos 失败均不产生假成功。

| 文件 | 变更 | 验证 |
| --- | --- | --- |
| `services/life-core/app/moments.py` | Provider 懒重建；生成后记录宽高/缩略图；触发发布；按事件读取媒体 | 单元测试、幂等测试 |
| `services/life-core/app/main.py` | 把现有 `publish_event` 作为发布回调注入；读取回忆时附加媒体对象 | API 测试 |
| `services/life-core/app/store.py` | 仅在需要时 additive migration；不触碰真实库 | 临时 SQLite |
| `services/life-core/tests/test_v023_moments.py` | 更新自动发布、失败重试、撤销与媒体测试 | pytest |
| `services/life-core/tests/test_api.py` | 覆盖列表/详情媒体契约与用户隔离 | pytest |

迁移与回滚：

- 新增 `moments.thumbnail BLOB`、`thumbnail_mime TEXT`、`image_width INTEGER`、
  `image_height INTEGER`，均允许旧行空值。
- 回滚只停止读取新字段；不删除列、不删除图片、不修改事件与 Memos。
- 不自动回填历史生成图；历史图在读取时按需生成缩略图。

## S4 质量与证据

目标：实际运行目标测试、配置检查、构建/类型检查，并在隔离浏览器会话中检查 390、430、768、
1440、1920；只使用合成账号和隔离数据库。

| 文件/产出 | 内容 |
| --- | --- |
| `scripts/` 或现有浏览器脚本 | 隔离截图与交互检查 |
| `evidence/shiguang-v02/` | 桌面/移动截图、运行 JSON、问题清单 |
| `docs/development-log/2026-11-05_...` | 中文验收日志、命令、结果、证据、遗留风险 |
| `docs/product/README.md` | 索引更新 |

截图必须来自真实运行页面。若无法使用真实 Memos 数据，则明确标注 `PARTIAL`，不能以本地假卡片冒充。

## 验收门槛

- S1：50 条样本结构和 Prompt 门禁 PASS；真实模型回归未执行时状态为 PARTIAL。
- S2：真实列表/详情/空态/筛选/失败/无图/详情交互测试 PASS；五个视口无横向溢出。
- S3：生成→发布→影集可见链路测试 PASS；重复触发不重复生成/发布；用户隔离 PASS。
- S4：仅在实际完成的检查上写 PASS；外部条件缺失写 BLOCKED 或 NOT TESTED。
