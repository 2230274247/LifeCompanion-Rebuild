# murmur-web 固定版本与生命周期说明

- 上游仓库：<https://github.com/krispuckett/murmur-web>
- 固定提交：`501edfbac594b06a20cb3ca92bdf4c7a19840717`（2026-11-04）
- 上游版本：`0.1.0`，MIT License
- 本地位置：`apps/pet-window/src/murmur/`（69 个文件，含 `LICENSE`）
- 本地差异：**无**。源码按上游原样复制，未修改任何 `.ts` / `.wgsl` 文件；
  本轮只新增 `apps/pet-window/` 下的 Electron 外壳、宠物交互与样式。
- 集成方式：上游尚未发布到 npm，按 README 的“复制库源码”方式引入；
  运行时依赖 `vgpu@^0.3.1` 由 `apps/pet-window/package.json` 锁定。
- 交付时 `apps/pet-window/package-lock.json` 一并提交，用于复现依赖版本。

## 升级步骤

1. 从上述仓库拉取目标提交。
2. 用新 `src/` 覆盖 `apps/pet-window/src/murmur/`，并保留 `LICENSE`。
3. 同步更新本文件中的提交号与日期。
4. 运行 `npm run build` 与一次真实窗口验收，记录到新的开发日志。

## 禁止事项

- 不把 murmur 的示例素材（`assets/collection.png`、demo 面板）带入产品。
- 不在本目录保存任何凭证或运行时数据。
