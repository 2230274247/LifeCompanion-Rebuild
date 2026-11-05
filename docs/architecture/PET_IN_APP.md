# 应用内宠物架构（Otis）

2026-11-05 增量。对应验收日志：
[Otis 应用内宠物](../development-log/2026-11-05_11-50_Otis应用内宠物_开发验收.md)。

## 定位

宠物是 Life Companion 页面的一部分：只在聊天路由渲染，随页面打开而出现、
关闭而消失，不创建任何常驻窗口，也不接入聊天、回忆或提醒的数据链路。
形象为原作品集 Otis 的可拉伸脸，用户可捏、拉、点击。

上一轮的 Electron 常驻置顶窗（[PET_WINDOW.md](PET_WINDOW.md)）保留为可选实验，
不是交付入口。

## 结构

```text
products/librechat-custom/client/src/
  components/Life/OtisPet/
    OtisPet.tsx        外壳：布局、折叠、提示、心情/耐心条、指针穿透
    otis-pet.css       布局与动效；颜色由语义类负责
    content.ts         原 Otis 内容（贴图改为 Vite 静态导入）
    face/engine.ts     原 WebGL2 引擎，逐字复用
    face/FaceCanvas.tsx原画布组件 + ariaLabel + 兜底色
    faces/*.webp       14 张表情贴图，2.5MB
  routes/ChatRoute.tsx 挂载点：<OtisPet /> 与 <ChatView /> 同级
  locales/en/translation.json  com_ui_otis_* 5 个键
```

挂载点选在 `ChatRoute` 而非 `Root`：`Root` 覆盖全部已登录路由，
宠物会出现在 `/memories` 并压住“查询回忆”筛选按钮。聊天路由是唯一的
“陪伴对话”场景，其余页面不需要它。

## 渲染与交互

`FaceCanvas` 保持原 Otis 的行为不变：128×128 网格、4 个抓取槽、高斯衰减、
阻尼弹簧、片元着色器做脸红与耐心衰减、14 张表情贴图 90ms 交叉淡入。
外壳只负责：

- **指针穿透**：画布命中层是 200×200 方框。`useFacePassthrough()` 从
  `faces.base.src` 生成 256px alpha 掩码，在 `pointermove` 时切换命中层的
  `pointer-events`。脸以外的像素不拦截点击，页面其余部分照常可操作。
- **布局**：`position: fixed; right: 16px; bottom: 136px; 200×256`，
  让开输入框与发送按钮；`.otis-pet-face` 200×200，心情条 184px 在下方。
- **折叠**：`localStorage['life-otis-pet-collapsed']` 记录状态，折叠为 54px
  圆头像按钮，可再次展开。
- **提示**：首拉后淡出，位置在脸的左上方空白处，避开深色头发以保证对比度。
- **响应式**：视口 < 900px 时整只宠物 `display: none`。
- **动效降级**：`prefers-reduced-motion` 下关闭过渡。

## 主题

心情条只用语义类：`bg-surface-primary/85`、`border-border-light`、
`text-text-primary`、`text-text-secondary`、`bg-border-light`。
角色自身固定色：钴蓝圆盘 `#2f4bf0`、暖橙头发、芥末黄毛衣——不套主产品的
雾青苔绿 Token，因为这是角色而不是界面表面。深色主题实测：
心情条 `rgba(13,13,13,0.85)`、文字 `rgb(236,236,236)`。

## 文案

所有界面文案走 `useLocalize()`，按上游贡献规范只写
`client/src/locales/en/translation.json`；其他语言回退英文。
宠物台词（`pull my face`、`chill`、`being squeezed`）是原设计的一部分，
刻意保留英文，不算漏翻。

## 构建与发布

客户端产物由容器挂载：

```text
products/librechat-custom/client/dist  →  lifecompanion-librechat
```

修改后必须：

```text
cd products/librechat-custom
npm run build
docker restart lifecompanion-librechat
```

容器会缓存 `index.html`；只重建不重启时，浏览器仍拿到旧的入口包。

## 与上游的差异

- `content.ts`：`/faces/*.webp` 绝对路径 → Vite 静态导入。
- `FaceCanvas.tsx`：新增 `ariaLabel`；兜底圆盘 `bg-disc` → 内联 `backgroundColor`
  （原作品集的自定义 Tailwind 主题在定制端不存在）。
- `engine.ts`：无改动。

## 已知边界

- 纯指针交互，无键盘入口；触摸屏未适配。
- 心情与耐心不持久化，刷新回到 `chill`。
- 首次进入聊天页加载 2.5MB 贴图；WebGL 持续绘制，未测长时 GPU/电池。
- 贴图来自用户提供的 `otis.zip`，未附 LICENSE，再分发权利不明；
  溯源见 [patches/otis-portfolio-lifecompanion-pet.md](../../patches/otis-portfolio-lifecompanion-pet.md)。
