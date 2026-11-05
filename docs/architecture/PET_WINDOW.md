# 桌面宠物置顶窗架构（Otis，可选实验）

> 状态：**非交付形态**。用户最终要求的是“放进软件页面里、打开才显示”，
> 交付实现见 [应用内宠物](PET_IN_APP.md)。本文保留 Electron 常驻置顶窗的
> 设计与实测记录，作为本机可选实验；不再作为产品功能维护。

2026-11-05 增量。对应验收记录见
[Otis 应用内宠物](../development-log/2026-11-05_11-50_Otis应用内宠物_开发验收.md)
与截图 `evidence/otis-pet/01..09`。
上一版 murmur 玻璃球实现已被 Otis 取代；其文件仍在磁盘上（删除请求被权限策略
拦截），历史记录见
[桌面宠物置顶窗（murmur）](../development-log/2026-11-05_10-18_桌面宠物置顶窗_开发验收.md)。

## 定位

独立桌面表面，不接入 Life Companion 的聊天、回忆与提醒链路。宠物是 Otis：
一颗钴蓝圆盘上会跟随鼠标、能被抓住拉长的人脸。当前为本机手工启动，
不是对外交付物。

## 进程与边界

```text
Electron main (electron/main.cjs)
  ├─ BrowserWindow 380×420, transparent, alwaysOnTop:'floating', skipTaskbar
  ├─ 回环静态服务器 127.0.0.1:<随机端口> → apps/otis-pet/dist
  ├─ Tray + Menu（显示/隐藏、完整页面、置顶、穿透、归位、重载、退出）
  ├─ 单实例锁、位置持久化（userData/otis-pet.json）
  └─ ipcMain.on('pet:menu') ── 打开同一份菜单
        ▲
        │ contextBridge.showMenu()
  preload (electron/preload.cjs)   ← 只暴露一个方法
        ▲
        │ window.pet.showMenu()
  renderer (pet.html → src/pet.tsx)
  └─ FaceCanvas + FaceEngine（原样复用） + 心情/耐心条
```

渲染层 `contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`，
页面含 CSP；主进程只加载本地构建产物，不加载远程内容。

## 窗口决策

| 参数 | 值 | 理由 |
| --- | --- | --- |
| 尺寸 | 380×420，不可缩放 | 320px 脸 + 心情条 + 留白 |
| 边框 | `frame: false` | 无窗框 |
| 透明 | `transparent: true` + `#00000000` | 只显示圆盘、人脸与心情条 |
| 置顶 | `alwaysOnTop: true, 'floating'` | 盖在浏览器与 IDE 上 |
| 任务栏 | `skipTaskbar: true` | 不占任务栏 |
| 阴影 | `hasShadow: false` | 透明窗不需要系统阴影 |
| 显示 | `showInactive()` | 启动不抢焦点 |

## 为什么需要回环 HTTP 服务

Otis 源码用绝对路径加载 `/faces/*.webp`。`file://` 下这些路径会解析到磁盘根目录，
直接改 `base` 又会偏离原源码。主进程在 `127.0.0.1` 的随机端口起一个只读静态服务，
把 `dist/` 作为根目录，并做路径穿越检查；这样源码保持原样，也不需要暴露端口。

## 脸与交互

`src/face/engine.ts` 是原 Otis 的 WebGL2 引擎：128×128 网格、4 个抓取槽、
高斯衰减、阻尼弹簧、14 张表情贴图交叉淡入、片元着色器做脸红与耐心衰减。
`src/pet.tsx` 只负责外层，不修改引擎。

- 抓头发 / 脸颊 / 下巴分别进入 `g_ouch`、`g_squish`、`g_grimace`；
- 拉拽时顶点被拖成长管，松手回弹并切换一张 release 表情；
- 快速点击（<240ms、位移<8px）触发惊吓表情与轻戳回弹；
- 持续拉扯会累积 `flush`，耐心条下降，归零后松手进入 `x_dizzy`；
- 空闲时眼睛跟随光标，光标停在鼻子附近会变成斗鸡眼；
- 第一次成功拉拽后隐藏 “pull my face” 提示。

抓取只认有像素的皮肤/头发/五官：命中层是 320×320 的方框，剩余区域通过
基础表情贴图的 alpha 掩码切换成 `-webkit-app-region: drag`，因此按在空气上
可以直接搬运窗口，按在脸上则是拉脸，两者不冲突。心情条本身也可拖动窗口。

## 上游与资产

- 来源：用户提供的 `otis.zip`（Otis — Stretchable-Face Portfolio Hero，
  参考站点 `https://www.scrolltide.co/#t-otis`）
- 复制方式：`src/`、`public/faces/`、`index.html`、`tsconfig.json`、`vite.config.ts`
  原样进入 `apps/otis-pet/`，未改上游文件；新增 `pet.html`、`src/pet.tsx`、
  `src/pet.css`、`src/pet-env.d.ts` 与 `electron/` 外壳。
- 溯源与升级步骤：[patches/otis-portfolio-lifecompanion-pet.md](../../patches/otis-portfolio-lifecompanion-pet.md)
- **授权未明**：压缩包与站点未附 LICENSE，人脸贴图的再分发权利不清晰。
  因此当前只做本机个人使用，不进入对外交付或公开仓库发布。

## 运行与数据

```text
cd apps/otis-pet
npm install
npm start                 # 构建 + 启动
..\..\scripts\start-pet.ps1   # 已有 dist 时直接启动
```

- 构建产物：`apps/otis-pet/dist/`
- 位置状态：`%APPDATA%\otis\otis-pet.json`
- `node_modules` 与 `dist` 均已忽略，不进入版本库。

## 已知边界

- Electron 常驻 Working Set ~377MB / Private ~294MB（本机实测）。
- WebGL 脸持续绘制；本轮未测长时间 GPU、电池与多显示器 DPI。
- 无安装包、无开机自启、无与聊天/提醒状态联动。
- “鼠标穿透”只在托盘菜单提供；开启后右键与脸都会失效，只能从托盘关闭。
- 完整作品集页面保留在托盘“打开完整页面”，本轮未做多尺寸回归。
