# Otis 作品集源码引入说明（Life Companion 宠物）

> 2026-11-05 更新：交付形态改为**应用内**宠物，源码被复制进
> `products/librechat-custom/client/src/components/Life/OtisPet/`（见下文
> “应用内副本”）。`apps/otis-pet/` 的 Electron 实现降级为可选实验。

## 来源

- 用户提供的压缩包：`C:\Users\Administrator\Downloads\otis.zip`
- 参考站点：<https://www.scrolltide.co/#t-otis>
- 引入日期：2026-11-05
- 上游形态：一次性导出的 Vite 工程，无 git 历史、无提交号、无 LICENSE 文件。

## 复制范围（未改动）

以下文件/目录原样复制到 `apps/otis-pet/`：

```text
index.html
src/App.tsx
src/content.ts
src/hooks.ts
src/index.css
src/main.tsx
src/vite-env.d.ts
src/face/engine.ts
src/face/FaceCanvas.tsx
public/faces/*.webp        （14 张表情贴图）
tsconfig.json
vite.config.ts
```

复制的 `vite.config.ts` 后加了多入口构建（`index.html` + `pet.html`），
这是唯一的构建配置改动；`src/`、`public/` 未被修改。

## 本地新增（不属于上游）

```text
package.json                upstream 依赖 + Electron 45.2.3 + 脚本
pet.html                    宠物入口
src/pet.tsx                 宠物外层：复用 FaceCanvas，心情条与提示
src/pet.css                 透明页面、拖拽区、心情条样式
src/pet-env.d.ts            window.pet.showMenu 类型
electron/main.cjs           透明置顶窗、托盘、回环静态服务、位置持久化
electron/preload.cjs        仅暴露 showMenu()
electron/tray.png           64×64 托盘图标（本地生成）
README.md                   运行与边界说明
```

## 应用内副本（2026-11-05，交付形态）

同一份源码被复制到 LibreChat 定制端，集成在页面内部：

```text
products/librechat-custom/client/src/components/Life/OtisPet/
  content.ts              src/content.ts，唯一改动：贴图 → Vite 静态导入
  face/engine.ts          src/face/engine.ts，逐字未改
  face/FaceCanvas.tsx     src/face/FaceCanvas.tsx，新增 ariaLabel、兜底色内联
  faces/*.webp            public/faces/*.webp，原图未改
  OtisPet.tsx             本地新增：外壳、折叠、指针穿透、心情条
  otis-pet.css            本地新增：布局与动效
```

挂载点：`client/src/routes/ChatRoute.tsx`（与 `<ChatView />` 同级）。
文案键：`client/src/locales/en/translation.json` 的 `com_ui_otis_*`（5 个）。
升级时同时替换两处副本，并重跑 `docs/development-log/2026-11-05_11-50_Otis应用内宠物_开发验收.md`
里的验收命令。

## 升级步骤

1. 用新版导出的 `src/`、`public/faces/`、`index.html` 整体替换；
2. 在 `vite.config.ts` 的多入口里保留 `pet.html` / `src/pet.tsx`；
3. 重新核对 `src/content.ts` 的 `rig` 与表情键是否变化；
4. 跑 `npm run lint`、`npm run build`，并按验收日志重测抓脸、点击、耐心与拖窗；
5. 更新本说明与验收日志，不覆盖旧日志。

## 禁止事项

- 不把 `otis.zip`、贴图或构建产物提交到公开仓库，除非确认授权。
- 不把 Electron 凭据、运行时状态或本机路径写入文档。
- 不修改 `public/faces/` 的原始贴图；视觉调整放在外壳 CSS 或引擎参数里。
