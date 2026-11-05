# 拾光 V0.2 自然聊天与图文影集 · 验收结论

验收日期：2026-11-05  
验收范围：普通聊天自然化、后台回忆/生图任务分离、我的回忆图文影集、自动生成后静默展示  
实际技术栈：React 18 + LibreChat + FastAPI + SQLite/Memos

## 总体结论

| 阶段 | 状态 | 结论 |
| --- | --- | --- |
| S1 聊天自然化 | PARTIAL | Prompt、配置和 50 条静态质量门禁 PASS；真实付费模型 50 条回归未执行 |
| S2 图文影集 | PASS | 9 个影集 Jest 用例、6 个 V023 用例、类型检查、生产构建和五视口浏览器验收通过 |
| S3 自动发布与媒体关联 | PASS（自动化） | 27 个后端目标测试通过；生成后自动发布、Memos 失败重试、媒体关联和账户隔离有测试覆盖 |
| S3 真实生图时段链路 | PARTIAL | 本轮未发起真实付费生图；隔离影集使用显式合成素材验证展示和交互 |
| S4 本地视觉与可访问性 | PASS | 390/430/768/1440/1920 无横向溢出，触控目标不小于 44px，axe 无 serious/critical 项 |

总体状态：**PARTIAL**。产品代码和本地隔离验收已完成，但不能把 Mock Provider 测试或合成素材截图等同于真实模型质量和真实付费生图验收。

## 关键结果

### S1 聊天自然化

- 两个拾光模型规范均使用版本化 `life-companion-chat.v1` Prompt。
- Prompt 明确区分普通聊天、记忆抽取、回忆生图和定时任务。
- 普通生活分享要求 1–3 句自然回应；不得用第一人称假扮用户、补写人物/服饰/对话/地点等未提供事实。
- 明确创作请求仍可创作，但创作细节不得回流为用户经历。
- 未验证后端成功状态时，聊天不得声称“已保存 / 已生成 / 已提醒”。
- 50 条评测样本覆盖 11 类输入，静态门禁实际输出：
  `PASS: 50 samples across 11 categories; prompt and model specs match v1 guardrails.`

### S2 图文影集

- `/memories` 首屏不再显示生成任务卡，直接显示日期分组、图片、标题和摘要。
- 支持搜索、日期筛选、时间排序、分页、详情和返回原筛选状态。
- 卡片与详情都标注“AI画面 · 非现场照片”；AI 图声明没有伪装为现场照片。
- 无图和图片失败时保留文字内容，不制造占位事实。
- 图片详情复用现有 Radix Dialog，支持 Esc、关闭按钮和焦点恢复。
- Motion 使用已安装的 `framer-motion`，并尊重 reduced motion。
- 响应式结果：390/430 为 1 列，768 为 2 列，1440/1920 为 3 列。
- 本机统一入口 `http://127.0.0.1:3001/memories` 已复核：3 张真实记录卡片中
  2 张读取到已有关联图片，1 张无图记录保留文字，旧“时段回忆”任务墙不再显示。

### S3 自动发布与媒体关联

- 图片生成成功后生成可解码缩略图和宽高，并通过现有私有 Memos 发布链路静默关联。
- 同一候选按现有窗口和幂等键去重，不重复生成或发布。
- Memos 发布失败时保留已生成图片并记录 `MEMOS_PUBLISH_FAILED`，后台可重试。
- 回忆列表只返回缩略图；详情才包含大图数据。
- 历史数据不回填，新字段采用 additive migration，旧行允许空值。

## 测试与证据

| 检查 | 命令或方式 | 实际结果 |
| --- | --- | --- |
| 聊天 Prompt 门禁 | `node scripts/check-life-chat-quality.mjs` | PASS，50 条 / 11 类 |
| 后端目标套件 | `pytest tests/test_v023_moments.py tests/test_direct_moment_test.py tests/test_v023_memory.py tests/test_memory_pipeline.py tests/test_api.py` | PASS，27 passed |
| 影集组件测试 | `jest Memories.spec.tsx` | PASS，9 tests |
| V023 交互测试 | `jest V023.spec.tsx` | PASS，6 tests |
| TypeScript | `npm run typecheck -- --pretty false` | PASS，退出码 0 |
| 前端构建 | `npm run frontend` | PASS |
| 真实浏览器验收 | `node scripts/capture-v02-gallery.mjs` | PASS，5 视口、筛选、详情、Dialog、空态、无图降级 |
| axe 扫描 | 影集 `main` 区域，390 与 1440 | 无 serious/critical 项 |

完整运行数据：[gallery-live-verification.json](../../../evidence/shiguang-v02/gallery-live-verification.json)  
合成数据清单：[synthetic-gallery-seed.json](../../../evidence/shiguang-v02/synthetic-gallery-seed.json)

截图：

- [桌面 1440](../../../evidence/shiguang-v02/memories-1440.png)
- [桌面 1920](../../../evidence/shiguang-v02/memories-1920.png)
- [平板 768](../../../evidence/shiguang-v02/memories-768.png)
- [手机 430](../../../evidence/shiguang-v02/memories-430.png)
- [手机 390](../../../evidence/shiguang-v02/memories-390.png)
- [手机回忆详情](../../../evidence/shiguang-v02/memory-detail-430.png)
- [手机图片 Dialog](../../../evidence/shiguang-v02/memory-image-dialog-430.png)
- [无图回忆降级](../../../evidence/shiguang-v02/memory-no-image-430.png)
- [搜索空态](../../../evidence/shiguang-v02/search-empty-430.png)
- [本机统一入口 3001 复核](../../../evidence/shiguang-v02/unified-entry-3001-memories-1440.png)

## 问题清单

| 级别 | 问题 | 状态与处理 |
| --- | --- | --- |
| P0 | 未发现阻断问题 | 本地隔离链路通过 |
| P1 | 未执行真实模型 50 条付费回归 | PARTIAL；Prompt 静态门禁不能替代真实回答质量 |
| P1 | 未发起真实付费生图验证“时段任务 → 生成 → 静默发布” | PARTIAL；自动化测试以受控 Provider 覆盖状态与发布逻辑 |
| P2 | Jest 完成后进程未自行退出 | 已确认测试为 PASS，随后强制结束测试进程；属既有测试运行器问题 |
| P2 | 当前回忆数据只有单张 AI 画面，没有真实照片/多图上传链路 | 本轮未伪装为真实照片；单图以 Radix Dialog 承载 |
| NOT TESTED | Safari/Firefox、性能压测、真实用户照片 EXIF/超大数据 | 后续上线前补齐 |

## 数据安全与边界

- 合成数据只写入 `infra/runtime/v023/life-core.sqlite3` 和隔离合成 Memos 用户。
- 种子脚本硬限制只接受上述隔离数据库路径；运行报告为 `production_database_touched: false`。
- 未修改真实原始数据，未批量回填历史事件，未执行破坏性数据库操作。
- 未 Git Push、未公网部署、未上传真实用户图片。
- 设计包假设 Vue 3；仓库实际为 React 18 + LibreChat，因此保留现有技术栈，并将
  Motion for Vue / Radix Vue 映射到现有 `framer-motion` / Radix Dialog。

## 后续验收建议

1. 在获得明确付费授权后，对两个模型运行 50 条真实回归并人工评分。
2. 在隔离环境运行一次真实时段生图，核对预算、候选选择、Memos 发布和影集静默出现。
3. 若接入真实多图上传，再评估 PhotoSwipe；当前单图不需要引入第二套查看器。
4. 完成 Safari/Firefox 和真实手机设备回归后再申请公网发布。
