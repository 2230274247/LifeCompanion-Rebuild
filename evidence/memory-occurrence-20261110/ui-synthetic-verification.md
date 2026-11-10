# 发生日期前端 UI 合成验证（2026-11-10）

本验证只覆盖 `products/librechat-custom/client` 下的发生日期组件，使用**明确标记的合成 API 日期夹具**，
导入真实组件并包裹 `QueryClient` + `MemoryRouter`。未连接真实后端、真实模型、数据库或凭据，
**不代表真实后端验收**。真实后端证据见本目录 `live-api-results.json` 与 `model-context-results.json`。

## 预览

- 共享 launch 配置新增独立 entry `occurrence-ui-ad14c0`（端口 3917），不覆盖其它 entry。
- 预览 serverId：`40757179-69ac-4a45-a48d-71698c3abdd7`。
- 本地 harness 位于 `infra/runtime/p5/occurrence-ui/`（gitignored），不入库。

## 合成夹具

| 精度 | start | end | 期望显示 | `<time dateTime>` |
| --- | --- | --- | --- | --- |
| day | 2026-11-02 | 2026-11-02 | 2026-11-02 | 2026-11-02 |
| month | 2026-10-01 | 2026-10-31 | 2026-10 | null |
| week | 2026-10-26 | 2026-11-01 | 2026-10-26 – 2026-11-01 | null |
| unknown | null | null | 日期未知 | null |

## 浏览器结果（DOM 快照 + 求值）

- 列表：精确日、月份、跨月周范围、unknown 四种分组标签均正确；周/月/unknown 不写 `dateTime`。
- 详情（点开精确日卡片）：`<time>2026-11-02</time>` 且 `dateTime="2026-11-02"`，正文/标签/共同回忆入口正常，无崩溃。
- 共享卡（点开周范围卡）：`2026-10-26 – 2026-11-01`，`dateTime=null`，无崩溃。
- 全程未出现虚构时刻（`14:25/00:00/15:00/Invalid Date` 均未命中），无 console error。

## 截图

- `list-synthetic-dates.jpg`：列表视图（已落盘）。
- 详情/共享卡截图因 Claude 窗口最小化导致渲染超时，未落盘；以快照 + `preview_eval` 结果为证据。

## 命令与结果

- `tsc --noEmit`：PASS（0 错误）。
- 聚焦 Jest：`Memories.spec.tsx` + `V023.spec.tsx`，`--runInBand --coverage=false`，2 suites / 24 tests PASS。
- `npm run build`（client）：PASS（约 20.6s）。
- 局部 eslint（变更的 Life 组件 + occurrence.ts + 测试）：PASS（0 problems）。

## 变更文件（本次任务范围）

- `client/src/components/Life/occurrence.ts`（新增 `occurrenceDay`，加强日期合法性校验）
- `client/src/components/Life/Memories.tsx`
- `client/src/components/Life/MemoryCard.tsx`
- `client/src/components/Life/MemoryDetail.tsx`
- `client/src/components/Life/SharedMemoryCard.tsx`
- `client/src/components/Life/__tests__/Memories.spec.tsx`
- `client/src/locales/en/translation.json`（仅新增英文键）
- `.claude/launch.json`（仅新增 `occurrence-ui-ad14c0` entry）
