# 拾光 V0.2 自然聊天与图文影集 · 仓库审计

审计日期：2026-11-05  
审计方式：只读阅读设计包、仓库代码、测试与当前工作区状态；未修改业务代码或真实数据库。

## 1. 结论摘要

设计包假设的是 Vue 3 工程，但本仓库实际可运行的统一产品入口是
`products/librechat-custom` 下的 React 18 + LibreChat，后端业务服务是
`services/life-core` 的 FastAPI。仓库内没有可与之对应的 Vue 3 生活陪伴前端。

因此本轮采用以下工作假设：

- 保留现有 React + FastAPI 技术栈，不重写为 Vue。
- 把设计包的 Motion for Vue / Radix Vue / Reka UI 建议映射到仓库已安装的
  `framer-motion` 与 `@radix-ui/react-dialog`。
- 不新增 PhotoSwipe；当前没有该依赖，单图详情先使用现有 Radix Dialog 能力并复用
  浏览器原生图片缩放语义，避免双查看器体系。多图真实照片接入时再评估 PhotoSwipe。
- 现有视觉 Token、侧栏、Header、Button、Spinner、主题注册表和本地化边界保持不动。

## 2. 实际调用链

### 2.1 聊天

1. `products/librechat-custom/client/src` 渲染 LibreChat 消息。
2. `products/librechat-custom/librechat.yaml` 的 `life-companion` 模型规范只声明
   DeepSeek 端点与模型，没有自然聊天 system instructions。
3. `products/librechat-custom/packages/api/src/memory/life.ts` 在用户消息持久化后异步
   调用 life-core 入队记忆提取，并在明确回忆/提醒请求时增加业务结果消息。
4. 后台 `Memory` / `Moments` 与前台自然语言回复不共用输出通道，但缺少显式提示词边界，
   模型会把普通分享自由改写成第一人称散文。

### 2.2 “我的回忆”

1. 路由：`client/src/routes/index.tsx` 中的 `/memories` 与 `/memories/:memoryId`。
2. 页面：`client/src/components/Life/Memories.tsx`。
3. 当前首屏先渲染 `MomentList`，把排队、生成、失败等任务卡片放在真实回忆之前。
4. 已发布事件来自 `GET /api/v1/memories`，后端读取 Memos 私有正文，但没有返回媒体对象。
5. 列表是 `max-w-4xl` 单列文本卡片，没有图片、日期分组或影集布局。
6. 详情只显示文本；图片只存在于 `moments` 表，未与已发布事件关联。

### 2.3 后台生成

1. `services/life-core/app/moments.py` 按现有 `11:00 / 17:00 / 23:00` 配置选择候选。
2. 候选必须有授权、过去发生、可配图，且按评分阈值择优；没有合格事件时记录 `skipped`。
3. 图像 Provider 成功后状态为 `generated`，图片存于 `moments.image` BLOB。
4. 当前不自动发布；管理员还要调用 `/api/v1/moments/{id}/publish` 才会写入 Memos。
5. 列表 API 只返回 `events.status = published`，所以生成完成但未手动发布的内容不会出现。

## 3. 根因

| 问题 | 根因 | 最小修复方向 |
| --- | --- | --- |
| 普通聊天被写成第一人称故事 | 模型规范缺少明确事实边界和输出模式 | 增加版本化 `promptPrefix`，普通聊天与后台任务职责分离 |
| 回忆页像任务面板 | `Memories` 首屏渲染 `MomentList` | 移出主内容，只保留已发布影集；设置入口放次级页 |
| 回忆没有图片 | 列表契约没有媒体字段，`moments` 与 `events` 未在读取时关联 | 从来源 memory/event 关联当前有效生成图，返回缩略图与 AI 声明 |
| 后台生成后不出现 | `run_one()` 只到 `generated` | 图文通过校验后自动调用现有发布链路，保留失败可重试 |
| 普通用户可能看到调试区 | 调试组件挂在三个消息渲染路径，靠状态接口隐藏 | 保留服务端管理员校验；前端仍只让已确认管理员看到，并加回归测试 |

## 4. 可复用能力

- `@radix-ui/react-dialog`：现有 Dialog、焦点管理与 Esc 行为。
- `framer-motion`：已安装，可做轻量进入动画并尊重 reduced motion。
- `@librechat/client` 的 `Button`、`Spinner`、主题 Token。
- `DialogImage` 的缩放/拖动实现可参考，但其界面语义绑定生图参数，不直接复用于回忆详情。
- `Moments` 已有幂等、窗口、授权校验、Provider MIME 校验与失败状态，可增量复用。

## 5. 数据与迁移边界

- 不修改 `events` 现有业务字段和真实数据库。
- `moments` 仅做 additive migration：增加缩略图、宽高字段；旧数据仍可读取。
- 不批量回填历史聊天，不为旧事件自动生成图片。
- Mock 数据只允许放在测试或独立演示目录，不进入正式列表 API。
- 发布仍使用现有 Memos 私有 memo 链路，不新增公网图片 URL。

## 6. 基线测试

2026-11-05 实测：

- 后端目标测试：`13 passed, 2 failed`。失败项为既有
  `test_v023_moments.py` 中在替换 settings 后没有同步重建 Provider，
  实际仍得到 `pending_provider`，与测试预期 `unknown/cancelled` 不符。
- 前端 `Memories.spec.tsx` 与 `V023.spec.tsx` 均显示 PASS；Jest 进程未自行退出，
  需用强制退出作为 CI 收尾，属于既有测试运行器问题。

基线失败不计为本轮功能通过；S3 会一并修正 Provider 重建问题并重跑。

## 7. 风险

- 真实模型质量不能用静态 Prompt 断言替代，本轮最多完成 50 条样本与本地结构校验；
  未获授权不发起付费模型调用。
- 现有 Memos 是已发布正文的唯一来源，发布失败时图片仍可保留在 `moments`，但影集不会出现。
- 真实图片/多图上传尚未存在；本轮只标注 AI 画面，不把生成图冒充现场照片。
- 工作区已有大量未提交改动，所有编辑必须保持局部，不能回退或整理无关文件。
