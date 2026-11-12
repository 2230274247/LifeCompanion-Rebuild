# LibreChat Life 主题 token 同步开发验收

## 1. 基础信息

- 任务：把 LibreChat SPA 的 Life 主题 token 同步到入口页重设计后的品牌色
- 日期：2026-11-12
- 版本：V0.3 候选
- 分支：`feat/v03-collaboration-20261105`
- 修改文件：`products/librechat-custom/client/src/components/Life/theme.ts`（独立上游仓库，归档 patches/）

## 2. 目标与边界

- 入口页按三 skill 重设计后建立新品牌 token（墨色 `#1c2b24`、次级 `#55665d`、
  纸张 `#faf9f5`/`#f2efe7`、品牌绿 `#2e5745`/`#1d3a2e`、银杏黄 `#e9cd7f`），
  但 LibreChat SPA 的 theme.ts 仍映射早期初稿色值。逐值同步。
- 仅外观，接口与功能未动；theme.ts 改动为纯字符串字面量，类型安全。

## 3. 修改明细

- light 模式 26 个色值、dark 模式 4 个色值同步到新 token。
- 主要组件（Memories/Reminders/Moments 等）均使用语义 token，同步后自动生效。
- 剩余硬编码色值（Navigation 未读红、Connections 关系分类色、OtisPet 自身配色）
  为有意语义色，不改。

## 4. 归档

- `patches/librechat-theme-tokens-20261112.patch`（3,226 bytes，SHA256
  `3bf5630d73fb1e737b4d9b2f80083a406a8a0d69489cd7448ac675bc06af3d6b`），反向应用检查通过。

## 5. 结论

- 状态：PASS（主题 token 同步完成，纯外观，类型安全）。
- 未验证：未在真实 LibreChat 容器做视觉回归（需前端预览）。
- 后续：逐组件的布局/动效打磨需三 skill 逐组件审查 + 前端预览验证。
