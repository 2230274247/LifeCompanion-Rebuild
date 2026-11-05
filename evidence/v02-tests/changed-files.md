# V0.2 实际修改文件清单

统计时间：2026-11-02T19:57:27.858897+08:00。由 Git porcelain（包含未跟踪的逐文件）生成；不含忽略的运行日志、账号、dist 和数据库。
根仓库中的完整补丁是独立源码改动的归档表示，不再计入独立应用源码数量。

## 根仓库

共 **48** 个实际新增/修改文件。文档/规范 14；代码/配置/测试 9；证据 23；上游补丁归档 2。

| 状态 | 实际路径 | 分类 |
| --- | --- | --- |
| ` M` | `README.md` | 文档/规范 |
| ` M` | `apps/product-portal/server.mjs` | 代码/配置/测试 |
| ` M` | `docs/ARCHITECTURE.md` | 文档/规范 |
| ` M` | `docs/BLOCKERS.md` | 文档/规范 |
| ` M` | `docs/RUNBOOK.md` | 文档/规范 |
| ` M` | `docs/UPSTREAM_DIFF.md` | 文档/规范 |
| ` M` | `services/life-core/app/auth.py` | 代码/配置/测试 |
| ` M` | `services/life-core/app/main.py` | 代码/配置/测试 |
| ` M` | `services/life-core/app/memos.py` | 代码/配置/测试 |
| ` M` | `services/life-core/tests/test_api.py` | 代码/配置/测试 |
| ` M` | `tests/RESULTS.md` | 文档/规范 |
| `??` | `AGENTS.md` | 文档/规范 |
| `??` | `docs/DEVELOPMENT_LOG_POLICY.md` | 文档/规范 |
| `??` | `docs/V02_IMPLEMENTATION.md` | 文档/规范 |
| `??` | `docs/architecture/README.md` | 文档/规范 |
| `??` | `docs/design/README.md` | 文档/规范 |
| `??` | `docs/development-log/2026-11-02_18-12_统一前端与回忆集成_开发验收.md` | 文档/规范 |
| `??` | `docs/development-log/README.md` | 文档/规范 |
| `??` | `docs/product/README.md` | 文档/规范 |
| `??` | `evidence/v02-before-original.png` | 证据 |
| `??` | `evidence/v02-chat-1440.png` | 证据 |
| `??` | `evidence/v02-chat-390.png` | 证据 |
| `??` | `evidence/v02-detail-1440.png` | 证据 |
| `??` | `evidence/v02-empty-390.png` | 证据 |
| `??` | `evidence/v02-error-390.png` | 证据 |
| `??` | `evidence/v02-live-verification.json` | 证据 |
| `??` | `evidence/v02-memories-1440.png` | 证据 |
| `??` | `evidence/v02-memories-1920.png` | 证据 |
| `??` | `evidence/v02-memories-390.png` | 证据 |
| `??` | `evidence/v02-memories-430.png` | 证据 |
| `??` | `evidence/v02-memories-768.png` | 证据 |
| `??` | `evidence/v02-mobile-drawer-390.png` | 证据 |
| `??` | `evidence/v02-tests/README.md` | 证据 |
| `??` | `evidence/v02-tests/automated-results.md` | 证据 |
| `??` | `evidence/v02-tests/changed-files.md` | 证据 |
| `??` | `evidence/v02-tests/final-checks.json` | 证据 |
| `??` | `evidence/v02-tests/jest-sidebar-before-v02.txt` | 证据 |
| `??` | `evidence/v02-tests/patch-final.json` | 证据 |
| `??` | `evidence/v02-tests/static-and-build.md` | 证据 |
| `??` | `evidence/v02-tests/v02-regression-before.txt` | 证据 |
| `??` | `evidence/v02-ui-final.json` | 证据 |
| `??` | `evidence/v02-viewports.json` | 证据 |
| `??` | `infra/compose.spa.yaml` | 代码/配置/测试 |
| `??` | `patches/README.md` | 上游补丁归档 |
| `??` | `patches/librechat-v0.8.8-lifecompanion-v02.patch` | 上游补丁归档 |
| `??` | `services/life-core/tests/test_memos.py` | 代码/配置/测试 |
| `??` | `tests/gateway.test.mjs` | 代码/配置/测试 |
| `??` | `tests/live-v02.py` | 代码/配置/测试 |

## 独立 LibreChat

共 **20** 个实际新增/修改文件。代码/配置/测试 20。

| 状态 | 实际路径 | 分类 |
| --- | --- | --- |
| ` M` | `products/librechat-custom/client/index.html` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/App.jsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/components/Auth/AuthLayout.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/components/UnifiedSidebar/ExpandedPanel.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/components/UnifiedSidebar/__tests__/ExpandedPanel.spec.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/components/UnifiedSidebar/mobile/Header.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/components/UnifiedSidebar/mobile/__tests__/Header.spec.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/locales/en/translation.json` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/routes/Root.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/client/src/routes/index.tsx` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/librechat.yaml` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/packages/data-provider/src/index.ts` | 代码/配置/测试 |
| ` M` | `products/librechat-custom/packages/data-provider/src/keys.ts` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/public/assets/life.svg` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/src/components/Life/Header.tsx` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/src/components/Life/Memories.tsx` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/src/components/Life/Navigation.tsx` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/src/components/Life/__tests__/Memories.spec.tsx` | 代码/配置/测试 |
| `??` | `products/librechat-custom/client/src/components/Life/theme.ts` | 代码/配置/测试 |
| `??` | `products/librechat-custom/packages/data-provider/src/life.ts` | 代码/配置/测试 |

## 独立 Memos

共 **0** 个实际新增/修改文件。。

| 状态 | 实际路径 | 分类 |
| --- | --- | --- |
