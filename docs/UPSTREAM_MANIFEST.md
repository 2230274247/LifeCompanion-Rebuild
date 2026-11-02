# Upstream Manifest

基线锁定日期：2026-11-02。两套源码都在各自目录保留 `.git`、`origin`、
完整历史和固定 tag。所有本地改动均在 `lifecompanion-baseline` 分支，
没有推送到官方上游。

| 项目 | 上游仓库 | 固定 tag | 上游基线 commit | 许可证 | 本地路径 |
| --- | --- | --- | --- | --- | --- |
| LibreChat | https://github.com/LibreChat-AI/LibreChat | `v0.8.8`（同一提交另有 `chart-2.0.17`） | `e8f3be08623663d4ad7f7241e693c94469b63bb0` | MIT | `products/librechat-custom` |
| Memos | https://github.com/usememos/memos | `26.10.0` | `651657e7211901393e2501ae7e3e202c8e56f73a` | MIT | `products/memos-custom` |

## 本地 Git 状态

| 项目 | 本地 HEAD | 与上游关系 |
| --- | --- | --- |
| LibreChat | `7c2365cb376b48acb1591e48a6ef91e5c47c78e6` | 基线之后 1 个本地提交 |
| Memos | `651657e7211901393e2501ae7e3e202c8e56f73a` | 与 `26.10.0` 基线完全一致 |

LibreChat 的本地提交只修改：

- `api/app/clients/BaseClient.js`
- `librechat.yaml`（上游 `.gitignore` 默认忽略，本仓库为可追溯配置显式纳入）

## 许可证核验

两个克隆根目录均包含 `LICENSE`：

| 项目 | 许可证 | LICENSE SHA-256 |
| --- | --- | --- |
| LibreChat | MIT | `958F543BED829E0CA42C35EF86F9EB06F46B8E8CEEE28C10B23BCC928E9C03D3` |
| Memos | MIT | `8785EC6EE18FD430DD32463B88C225ACC35D08AB7FACD5F26D83DE38707B3CDE` |

## 运行镜像

| 组件 | 镜像 |
| --- | --- |
| LibreChat | `ghcr.io/librechat-ai/librechat:v0.8.8` |
| LibreChat MongoDB | `mongo:8.0.20` |
| LibreChat search | `getmeili/meilisearch:v1.35.1` |
| Memos | `neosmemo/memos:26.10.0` |

LibreChat 容器把本地补丁与配置只读挂载到 `/app`，同时复用固定版本官方镜像
中的其余应用代码。

## 保留的上游能力

- LibreChat：账号认证、会话列表、聊天输入、消息持久化、附件入口、
  搜索依赖、设置入口、模型选择和历史回看。
- Memos：账号登录、时间轴、日历、标签、Memo 创建/编辑/私有可见性、
  搜索和附件入口。

## 证据

- 原版页面：`evidence/baseline-librechat.png`、`evidence/baseline-memos.png`
- 改造后页面：`evidence/vertical-slice-librechat.png`、
  `evidence/vertical-slice-memos.png`
- 详细差异：`docs/UPSTREAM_DIFF.md`

