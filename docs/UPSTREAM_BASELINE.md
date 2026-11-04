# Upstream Baseline

记录时间：2026-11-02。正式业务补丁应用前，两套应用均通过固定版本镜像启动，
并实际访问了各自原版页面。

## 运行入口

| 服务 | URL | 基线结果 |
| --- | --- | --- |
| LibreChat | http://localhost:3080 | 200，可打开原版登录/聊天界面 |
| Memos | http://localhost:5230 | 200，可打开原版时间轴 |
| LibreChat health | http://localhost:3080/health | 200 |
| Memos health | http://localhost:5230/healthz | 200 |

## 固定版本

- LibreChat tag `v0.8.8`，commit
  `e8f3be08623663d4ad7f7241e693c94469b63bb0`
- Memos tag `26.10.0`，commit
  `651657e7211901393e2501ae7e3e202c8e56f73a`

## 基线截图

- `evidence/baseline-librechat.png`
- `evidence/baseline-memos.png`

## 基线后本地变更

LibreChat 应用了 1 个服务端事件接入补丁，并加入 DeepSeek 自定义端点配置。
Memos 没有修改业务源码。详见 `docs/UPSTREAM_DIFF.md`。

## 可复现启动

```powershell
Set-Location "<project-root>\infra"
docker compose --env-file ".env" -f "compose.baseline.yaml" up -d
```

启动后容器：

- `lifecompanion-librechat`
- `lifecompanion-memos`
- `lifecompanion-mongo`
- `lifecompanion-meili`

已有 Silver Economy 容器和 Open WebUI 未被停止、删除或修改。
