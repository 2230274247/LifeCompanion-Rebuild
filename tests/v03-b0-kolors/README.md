# B0 Kolors 真实生图隔离验证

本目录是 V0.3 B0 的独立技术验证区，不修改或启动 A++ 业务代码。
真实烟测只允许一次 `Kwai-Kolors/Kolors` 请求，一张 `960x1280` 图片，
并使用独立的 `SILICONFLOW_API_KEY` 环境变量。

也可以把 Key 填入本目录下被 Git 忽略的 `.env.local`：

```text
tests/v03-b0-kolors/.env.local
```

脚本优先读取环境变量；环境变量为空时才读取该文件。Key 不会打印，
也不会写入请求、响应、错误或验收日志。

## 真实烟测

```powershell
$env:SILICONFLOW_API_KEY = '<set-outside-files>'
python .\tests\v03-b0-kolors\verify_kolors.py
```

默认输出目录为 `evidence/runtime/v03-b0-kolors/`，该目录已被 `.gitignore`
覆盖。脚本不会输出密钥或带签名的图片 URL。

执行门禁：

1. 动态读取官方价格页，确认 Kolors 当前“每图片 / 免费”。
2. 使用独立 Key 请求账户模型列表，确认 Kolors 对当前账户可见。
3. 硬预算为 `¥0.00`，最多一次生图请求、一张图片，不重试、不换模型。
4. 在请求前原子写入一次性账本；超时或 5xx 后不再自动重试。
5. 图片下载仅允许 HTTPS 公网地址、无跳转、最大 20 MB。
6. 保存后执行 Pillow 完整解码、尺寸、格式、MIME 和 SHA-256 校验。

SiliconFlow 当前真实下载可能把 PNG 声明为 `application/octet-stream`。受限
兼容回退默认关闭，只可在明确批准后对本次验证显式开启：

```powershell
$env:SILICONFLOW_ALLOW_GENERIC_BINARY_MIME='1'
```

回退仍只接受可信 `*.siliconflow.cn` HTTPS 来源，并要求 magic bytes 与 Pillow
实际格式一致、格式属于 PNG/JPEG/WebP 白名单、完整 `verify()`/`load()`、
精确尺寸、像素/字节限制、非空白检查和 SHA-256。缺失 `Content-Type`、任何
不匹配的 `image/*`、不可信 host、伪造、损坏或截断图片继续拒绝。

没有 Key、账户模型权限不可确认或免费价格不可确认时，脚本输出
`BLOCKED`，生图请求数保持为 0。

如果输出目录已经存在 `attempt-ledger.json`，脚本拒绝原地重跑，避免覆盖证据
或产生第二次请求。修复后需要新的证据目录时，显式传入新路径；该路径仍执行
相同的 ¥0、单请求、单图硬门禁：

```powershell
python .\tests\v03-b0-kolors\verify_kolors.py .\evidence\runtime\v03-b0-kolors-fixed-attempt-01
```

失败记录会区分 `preflight`、`provider_response`、`image_download`、
`image_decode`、`image_mime_validation`、尺寸和质量校验阶段。记录中只保存
声明 MIME、Pillow 格式、维度、字节数、magic bytes、供应商 trace ID；
不保存 Key、完整签名 URL 或原始图片内容。

## Mock 合同测试

```powershell
python -m unittest discover -s .\tests\v03-b0-kolors -v
```

Mock 结果只验证 Provider 合同与解码路径，不能作为真实 Kolors 验收证据。

当前结果：13/13 PASS。真实图片请求已在另一个新的隔离目录完成并停止，
没有自动重试。

REAL 结果与证据：

```text
evidence/runtime/v03-b0-kolors-fixed-attempt-02/kolors-b0-real.png
evidence/v03-b0-kolors/fixed-attempt-02/manifest.json
```

PNG `960x1280`，SHA-256
`9bbd0cb588f51cbf579235547f7e55aa4d8c06e09912f9c0881fabdfd31e240b`。
本次生图请求 1 次、下载 1 次、自动重试 0 次。人工检查的技术视觉完整性为
PASS，Prompt 对齐为 PARTIAL，P04 语义评测未运行。

## 最小接入点

- `provider.py` 的 `ImageProvider` 可注入现有 `Moments`，替换当前
  `generate(caption)` 内硬编码的 CogView 调用。
- 现有 `Moments.run_one()` 可保留状态机；Provider 只负责一次请求、可信下载、
  完整校验并返回不可变结果，不负责用户同意、数据库或调度。
- 现有 `main.py` 的 `moment-generation` 线程继续调用 `Moments.run_one()`；
  本轮不启动它，也不改变生产配置。
- 后续私有媒体路由应按 `moment.user_id` 鉴权；Provider URL 和 Key 不返回前端。

