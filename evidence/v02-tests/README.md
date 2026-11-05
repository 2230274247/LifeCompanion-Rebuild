# V0.2 验收证据索引

日期：2026-11-02，香港时间。只保留脱敏结果，不提交运行账号、请求令牌、密钥或数据库。
总体状态 PARTIAL，完整说明见
`docs/development-log/2026-11-02_18-12_统一前端与回忆集成_开发验收.md`。

| 附件 | 说明 |
| --- | --- |
| `automated-results.md` | 16 后端 + 1 网关 + 115 前端限定回归通过；重复复验不重计 |
| `v02-regression-before.txt` | 用户作用域幂等、网络发布失败的修复前 FAIL |
| `jest-sidebar-before-v02.txt` | 三个侧栏开关断言修复前 FAIL；原任务默认覆盖率慢，结果输出后中止 |
| `static-and-build.md` | 最终类型、lint、构建和 Lighthouse 阻塞摘录 |
| `patch-final.json` | 独立 index 补丁应用检查及实际配置密钥值扫描；不是全面安全审计 |
| `changed-files.md` | 根仓库/独立上游逐文件数量和列表 |
| `final-checks.json` | 最终服务健康、Git 空白、Memos 状态和时间 |
| `../v02-live-verification.json` | 真实登录、Memos 内容/归属、幂等重试和负面 API 检查 |
| `../v02-viewports.json` | 五种视口根页面宽度和 iframe 计数 |
| `../v02-ui-final.json` | 最终浏览器复验与手机输入区域测量 |

## 可复现命令

在 `services/life-core`：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

在根目录：

```powershell
node --test tests/gateway.test.mjs
.\services\life-core\.venv\Scripts\python.exe tests/live-v02.py --conversation d8302b52-bc70-5bff-8445-af380c2cca52 --output evidence/v02-live-verification.json
```

在 `products/librechat-custom/client`，下列测试均限定文件，不运行全集：

```powershell
npm run test:ci -- --runInBand --coverage=false --runTestsByPath src/components/Life/__tests__/Memories.spec.tsx src/routes/__tests__/ChatRoute.spec.tsx src/components/Chat/Input/__tests__/submit.spec.ts src/hooks/Input/useComposerBindings.spec.tsx src/hooks/Messages/__tests__/useMessageScrolling.spec.tsx
npm run test:ci -- --runInBand --coverage=false --runTestsByPath src/utils/shortcuts.spec.ts
npm run test:ci -- --runInBand --coverage=false --runTestsByPath src/components/UnifiedSidebar/mobile/__tests__/Header.spec.tsx src/components/UnifiedSidebar/__tests__/ExpandedPanel.spec.tsx src/hooks/Nav/__tests__/useSidebarToggle.spec.tsx
npm run typecheck
npm run build
```

在 `products/librechat-custom`：

```powershell
.\node_modules\.bin\tsc.cmd --noEmit -p packages/data-provider/tsconfig.json
```

ESLint 对修改的前端文件运行；最终追加
`client/src/components/UnifiedSidebar/ExpandedPanel.tsx`、
`mobile/Header.tsx` 及其两个测试文件。未执行依赖升级或整个工作树格式化。

在 `infra`：

```powershell
docker compose --env-file .env -f compose.baseline.yaml -f compose.spa.yaml config --quiet
docker compose --env-file .env -f compose.baseline.yaml -f compose.spa.yaml restart librechat
```

Lighthouse 曾使用上游脚本并重试 `E2E_BASE_URL=http://localhost:3098`，
Windows 空格路径导致其隔离服务启动失败。保留 BLOCKED，不将构建成功视为性能通过。

## 真实截图

| 文件（位于 evidence） | 说明 |
| --- | --- |
| `v02-before-original.png` | 改造前入口，未固定视口 |
| `v02-chat-1440.png` | 最终桌面聊天构建 |
| `v02-memories-1440.png`、`v02-memories-390.png` | 最终构建的真实 6 条回忆 |
| `v02-memories-430.png`、`v02-memories-768.png`、`v02-memories-1920.png` | 同轮较早的真实 5 条回忆；第二条测试消息尚未发送 |
| `v02-mobile-drawer-390.png` | 最终手机抽屉，关闭回调修复后 |
| `v02-detail-1440.png` | 最新私有 Memo 详情，深链接刷新后 |
| `v02-empty-390.png` | 不存在的搜索词得到真实空结果 |
| `v02-error-390.png` | 不存在详情返回错误及重试按钮 |
| `v02-chat-390.png` | 最终手机聊天输入区域 |

未录制视频。截图中的模型回复文字不作为验收结论，实际结果以 API/测试/操作记录为准。
