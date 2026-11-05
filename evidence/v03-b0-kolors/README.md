# V0.3 B0 Kolors 证据索引

## 当前结论

- B0 技术验证：`REAL PASS`
- 本次隔离尝试真实生图请求：1 次
- 本次图片下载：1 次
- 自动重试：0 次
- 预算上限：`¥0.00`
- 模型：`Kwai-Kolors/Kolors`
- 图片：PNG，960 × 1280，1,978,187 bytes
- SHA-256：
  `9bbd0cb588f51cbf579235547f7e55aa4d8c06e09912f9c0881fabdfd31e240b`
- 手工视觉完整性：PASS
- Prompt 人工对齐：PARTIAL
- P04 语义评测：NOT RUN
- MOCK 合同测试：13/13 PASS，只证明代码路径，不是真实生成结果

真实 PNG 保存在被 `.gitignore` 覆盖的私有运行目录：

`H:\AI For research institute\LifeCompanion-Rebuild\evidence\runtime\v03-b0-kolors-fixed-attempt-02\kolors-b0-real.png`

脱敏验收清单：
[fixed-attempt-02/manifest.json](fixed-attempt-02/manifest.json)。

## 官方资料

- [现行接口字段、错误码与响应合同](official-api-contract.md)
- [MIME 错配脱敏诊断](diagnostics/mime-mismatch-2026-11-04.json)
- [修复后第一次真实调用诊断](diagnostics/fixed-attempt-01-2026-11-04.json)
- [旧临时图片 URL 恢复检查](diagnostics/old-image-recovery-2026-11-04.json)
- [MIME 错配修复验收](../../docs/development-log/2026-11-04_14-15_Kolors_MIME错配诊断与修复_开发验收.md)
- [B0 REAL 验收](../../docs/development-log/2026-11-04_14-26_Kolors真实生图B0_REAL验收_开发验收.md)
- [Provider/FastAPI/Moments/Worker 最小接入设计](../../docs/architecture/V03_B0_KOLORS_PROVIDER.md)
- [开发验收日志](../../docs/development-log/2026-11-04_14-00_Kolors真实生图B0_开发验收.md)

读取时的官方页面 SHA-256：

| 页面 | SHA-256 |
| --- | --- |
| `https://api-docs.siliconflow.cn/docs/api/images-generations-post` | `c3a4d60d0acf401d1330a0cd0e21351d4447a8f190df14c4f6f8a60cb58aac94` |
| `https://www.siliconflow.cn/pricing`（首次抓取） | `359bf11359a4cf0e545820ba116713bff62975557a2c2dd21683a69f689d92ce` |
| `https://api-docs.siliconflow.cn/docs/release-notes/overview` | `482bd513f50a0734b47508ffd19779f61a346f08eaea6f5057854a4f2d0bfac8` |
| `https://api-docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation` | `bbf26840dbfe7bacb1c63fa327048c5044c637241974fa8a0419f10449eb335a` |

页面为动态渲染，重新抓取可能因 nonce/构建数据不同产生不同哈希。

## 运行证据

脱敏请求、响应记录、错误日志和最终校验位于被 `.gitignore` 覆盖的私有运行目录：

`evidence/runtime/v03-b0-kolors/`

其中 `history/preflight-301/` 保留了价格页初始 301 被安全门禁拒绝的记录；
该次仍为生图请求 0 次。

`history/mime-mismatch-2026-11-04T06-09-26Z/` 保留了一次真实响应已进入图片校验、
但旧计数器误报为 0 的原始证据。诊断见
[mime-mismatch-2026-11-04.json](diagnostics/mime-mismatch-2026-11-04.json)。

原目录和修复前尝试的一次性账本均已使用，禁止原地重跑。新的隔离尝试已完成
一次真实请求并通过技术验收，没有覆盖旧账本或旧失败证据。

修复后的无 Key 门禁复验位于 [post-fix-blocked/](post-fix-blocked/manifest.json)。

修复后真实调用证据位于 [fixed-attempt-01/](fixed-attempt-01/manifest.json)：
图片请求 1 次、下载 1 次、未重试；下载头为
`application/octet-stream`，Pillow 检测为有效 PNG `960x1280`，严格 MIME
一致性门禁拒绝，未生成通过验收的 PNG 文件。

在用户明确批准受限通用二进制 MIME 回退及一次新请求后，新目录
[fixed-attempt-02/](fixed-attempt-02/manifest.json) 完成：

- API HTTP 200，下载 HTTP 200；
- 声明 `application/octet-stream`，Pillow 实际 PNG；
- `TRUSTED_GENERIC_BINARY_FALLBACK` 仅对可信 SiliconFlow HTTPS 来源生效；
- 请求 1 次、下载 1 次、自动重试 0 次；
- 图片完整解码、960 × 1280、SHA-256 和保存后复算均通过。

此前的 BLOCKED 和 FAIL 脱敏副本继续保留；`blocked/`、
`fixed-attempt-01/` 和诊断目录均未被覆盖。

## 结果分类

| 分类 | 内容 | 结论 |
| --- | --- | --- |
| REAL | 新隔离尝试的真实 Kolors API 请求与图片 | 1 次请求、1 次下载、0 重试；`REAL PASS` |
| MOCK | 格式一致性、损坏图片、单图、诊断、门禁、账本、文件 Key 读取、拒绝字节隔离 | 13/13 PASS |
| REAL | 修复前历史请求 | `FAIL / IMAGE_MIME_FORMAT_MISMATCH`，原证据保留 |
| REAL | Prompt 人工对齐 | PARTIAL；未运行 P04 |
| BLOCKED | 后续真实生图 | 未获新授权；本轮已停止 |

