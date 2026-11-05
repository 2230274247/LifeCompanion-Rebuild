# Otis — 桌面小宠物（可选实验）

> 交付形态已经改为**应用内**宠物：`products/librechat-custom/client/src/components/Life/OtisPet/`，
> 只在聊天页出现。本目录保留为可选的本机实验，不再默认启动，也不随产品交付。
> 架构说明见 `docs/architecture/PET_IN_APP.md` 与 `docs/architecture/PET_WINDOW.md`。

Otis 的可拉伸脸，由原作品集源码（React 19 + Vite 6 + TypeScript + Tailwind 4 +
原生 WebGL2 脸引擎）加一个 Electron 透明置顶壳组成。作品集页面仍然保留，
托盘菜单可打开；默认启动的是 380×420 的桌面宠物窗。

## 运行

```powershell
cd apps/otis-pet
npm install
npm start           # vite build + electron .
npm run electron    # 已有 dist 时直接启动
```

日常启动也可以从仓库根目录运行 `scripts/start-pet.ps1`。

## 操作

- 抓头发 / 脸颊 / 下巴并拖动：拉长脸，松手回弹。
- 快速点一下脸：惊吓与轻戳回弹。
- 持续拉扯：耐心条下降，归零后“眼冒金星”。
- 空闲时眼睛跟随光标；光标停在鼻子上会斗鸡眼。
- 拖动窗口：按在脸周围的空白处或底部心情条上；按在脸上是拉脸，不搬窗。
- 右键或托盘：显示/隐藏、打开完整页面、置顶、鼠标穿透、回到右下角、
  重新载入、退出。

## 目录

```text
index.html, src/, public/faces/   原 Otis 作品集源码（未改动）
pet.html, src/pet.tsx, src/pet.css  宠物入口与外壳
electron/main.cjs                 透明窗、托盘、回环静态服务、位置记忆
electron/preload.cjs              仅 showMenu() 的 contextBridge
```

## 边界与风险

- 人脸贴图与源码来自用户提供的 `otis.zip`，未附 LICENSE，**再分发权利不明**；
  当前仅本机个人使用。
- Electron 常驻内存明显高于原生方案；WebGL 持续绘制，未测长期 GPU/电池。
- 无安装包、无开机自启；“鼠标穿透”开启后只能从托盘关闭。
- 上游源码未改；升级时整体替换 `src/` 与 `public/faces/`，再补回宠物外壳文件。
  溯源见 `patches/otis-portfolio-lifecompanion-pet.md`。
