# V0.3 审计证据

2026-11-04。本目录只证明仓库审计与既有基线，不代表 A/B/C/D 已交付。

## 结果

| 项目 | 结果 | 原始记录 |
| --- | --- | --- |
| canonical 后端 | 63 passed，38.83s | [日志](pytest.txt)、[JUnit](pytest.xml) |
| 当前开发树后端与目录守卫 | 174 passed，119.62s | [日志](active-pytest.txt)、[JUnit](active-pytest.xml) |
| 当前开发树前端 | 6 suites / 27 passed，32.523s | [日志](active-frontend.txt) |
| canonical 网关 | 2 passed | [日志](gateway.txt) |
| 当前开发树网关/日志安全 | 5 passed | [日志](active-gateway.txt) |
| 6 个 V0.3 差距回放 | 缺口全部复现；不是功能通过 | [结果](gap-replays.json)、[输出](gap-replays.txt)、[脚本](reproduce-gaps.py) |
| 服务与源码归属 | 六服务 200，匿名 401，内部路由 404；dist 引用一致 | [结果](active-runtime.json) |
| 原始附件 | 1 Markdown + 7 PNG 按字节复制 | [哈希](source-manifest.json) |
| 匿名页面 | 1440/390 登录重定向；未进入账户 | [桌面](anonymous-1440.jpg)、[手机](anonymous-390.jpg)、[范围](browser-baseline.json) |
| 真实 Kolors | BLOCKED；请求 0，无真实图片 | 配置存在性见 active-runtime.json；真实供应商接口/条款待核验 |

第一次 canonical pytest 从错误目录启动，11 个收集错误，退出码 2：
[失败日志](pytest-initial-wrong-cwd.txt)、[失败 XML](pytest-initial-wrong-cwd.xml)。
修正工作目录后退出码 0；失败证据保留。

前端 console.error 来自既有合成故障用例，整套退出码为 0。
canonical 后端含 Starlette/httpx 弃用 warning，当前树有 LangGraph Send 弃用 warning。
本轮没有构建、全量 TSC、Lighthouse、真实手机或 V0.3 五视口验收。

## 复核命令

canonical 后端的正确工作目录为仓库 `services/life-core`：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests --junitxml=../../evidence/v03-audit/pytest.xml
```

当前开发树命令的工作目录为 `.work/p00-p07-20261103`；
每个 shell 执行前先运行目录守卫并检查退出码：

```powershell
python scripts/verify_rebuild_workspace.py
# 只有退出码 0 才继续下列命令。
$env:PYTHONPATH = Join-Path (Get-Location) 'services/life-core'
.\infra\runtime\p02\venv\Scripts\python.exe -m pytest -q services/life-core/tests tests/test_workspace_guard.py
node --test tests/gateway.test.mjs tests/lighthouse-errors.test.cjs
```

前端在当前开发树的 `products/librechat-custom` 运行：

```powershell
npm run test:ci --workspace=@librechat/frontend -- --runInBand --coverage=false --watch=false src/components/Life/__tests__
```

缺口回放脚本由当前开发树虚拟环境运行；只建临时合成库，
httpx.MockTransport 替代 HTTP，没有真实模型/图像请求：

```powershell
.\infra\runtime\p02\venv\Scripts\python.exe "H:/AI For research institute/LifeCompanion-Rebuild/evidence/v03-audit/reproduce-gaps.py"
```

## 保存边界

- `git-before.txt`、`librechat-git-before.txt` 是首次 canonical 基线快照；
  `canonical/active/active-librechat-git-status.txt` 区分不同仓库。
- `*-source-hashes.json` 覆盖指定业务目录及当前上游 Life/桥接文件，范围见 JSON 键。
  最终复核只据此声明这些源码未改，不声明数据库或整个文件系统未发生背景变化。
- 图片为真实浏览器截图；附件概念图不作为实际产品页面证据。
- 凭据检查只存字段存在与是否已配置，没有 token/password/key 值。
- 所有新 V0.3 用例仍待实施后执行；历史 P04 真实模型证据留在原工作树。
