# P00 依赖与许可证基线

本阶段没有升级上游版本。镜像及来源由实际容器 inspect、独立 Git HEAD 与根 LICENSE 核验；
细节见 evidence/p00/container-ownership.json、identity-before.json。

| 组件 | 固定版本/HEAD | 许可证基线 | 作用 |
|---|---|---|---|
| LibreChat | v0.8.8；本地 7c2365cb376b48acb1591e48a6ef91e5c47c78e6 加既有补丁 | MIT，保留 LICENSE | 认证、真实聊天、Mongo 历史、React |
| Memos | 26.10.0 / 651657e7211901393e2501ae7e3e202c8e56f73a | MIT | 私有事件 |
| Vikunja | v2.7.1；镜像 f7dc8428d10a… | AGPL-3.0-or-later，源码提供义务待上线复核 | 正式任务 |
| ntfy | v2.36.0；镜像 fb48c413eb11… | Apache-2.0 / GPLv2，按实际分发复核 | 通知 |
| Mongo | 8.0.20 | SSPL，部署分发门禁需独立复核 | 聊天主库 |
| FastAPI/uvicorn/httpx/pytest | 原 requirements 锁定 | 原包 metadata/上游许可，待 P07 全量扫描 | API 与测试 |
| LangMem/Neo4j/LangGraph/APScheduler/Graphiti | 当前未集成 | 不能拿旧仓库安装状态充当本项目证据 | P02-P03 后续实际锁定和调用 |

此表不是法律合规结论，也不是完整 CVE 审计。没有新付费服务、公开部署或上游推送。
