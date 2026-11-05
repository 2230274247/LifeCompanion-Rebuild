# Parlor 回忆协作弹窗实现说明

视觉基准：用户提供的 Parlor 原始提示与截图（`inputs/用户提供的Parlor原始提示与源码.txt`）。
落地为 React 18 具名作用域组件，不替换 LibreChat 根 App，不污染全局样式。

## 视觉实现

- 奶油底 `#fff4e0` + 22px 点阵，墨黑 `#141414` 2.5px 粗描边，5–9px 硬偏移阴影。
- 黄色头部 `#ffd23f`，表情 SVG、打字状态、消息弹入、hover 表情回应、
  `prefers-reduced-motion` 降级、键盘 focus-visible、消息 aria-live。
- 桌面端悬浮：约 400×560，右下角，可关闭后收缩为“打开共同回忆”按钮。
- 移动端：底部抽屉 sheet，输入区预留 safe-area。

## 关键文件

- `client/src/components/Life/SharedMemory.tsx`
- `client/src/components/Life/ParlorMemoryPanel.tsx`
- `client/src/components/Life/ParlorMemoryPanel.css`
- `client/src/components/Life/__tests__/ParlorMemoryPanel.spec.tsx`

## 真实业务绑定

- 消息、表情回应、成员列表、共享来源全部走 life-core API，不使用固定
  `REPLIES` 或定时器假回复；AI 回复由服务端 `_model_reply` 真实调用模型。
- 发送失败保留草稿，AI pending 禁用重复发送；断线重连事件按 scope 鉴权轮询。
- 越权用户看到的是“无法打开”而不是空聊天框。

## 视觉验收证据

- 桌面悬浮窗：`evidence/v03-acceptance/browser/b-shared-memory-desktop.png`
- 移动端抽屉：`evidence/v03-acceptance/browser/a-parlor-mobile-sheet.png`
- 越权页面：`evidence/v03-acceptance/browser/c-forbidden-shared-memory.png`

待补：768/1440/1920 全视口像素级对比与录屏。
