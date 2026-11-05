# V0.3 B0 Kolors Provider 最小接入设计

## 状态

`DESIGN ONLY / NOT CONNECTED`。本文件不表示生产已接入 Kolors，也不启动
真实用户聊天、Moments 自动任务或生产调度。

独立可运行参考实现位于 `tests/v03-b0-kolors/provider.py`；
它只在 B0 测试目录内，不被 `services/life-core` 导入。

## 现有边界

| 现有组件 | 当前行为 | B0 兼容方式 |
| --- | --- | --- |
| FastAPI `create_app()` | 创建 `Moments` 和后台线程 | 未来仅注入 Provider；不新增公开生图路由 |
| `Moments.run_one()` | 原子领取 queued；调用一次 `generate(caption)`；处理 timeout/HTTP/校验错误 | 把 `generate` 内 CogView 硬编码替换为注入的 `ImageProvider.generate()` |
| `main.py` 的 `moment-generation` 线程 | 定时 `schedule()`/`run_one()` | 保留现有 Worker，不新建第二套任务框架 |
| `moments` SQLite 表 | 保存状态、错误码和图片 BLOB | 阶段 B 完整实现时再补 job/media 元数据，本 B0 不改表 |

## 最小契约

```python
class ImageProvider(Protocol):
    def generate(
        self, request: GenerationRequest, trace_id: str
    ) -> GeneratedImage: ...
```

`GenerationRequest` 携带已由业务层构造的 prompt、尺寸和生成参数。
`GeneratedImage` 只返回已完整解码和校验的数据及元数据：
bytes、MIME、格式、宽高、SHA-256、供应商 trace ID、耗时和图片 host。

Provider 不处理：

- 用户同意、来源撤回和 owner 权限；
- Moments 状态机、SQLite 写事务和重试预算；
- FastAPI 路由、前端 URL 或长期任务调度；
- 费用账本和多用户配额。

这些仍由既有业务边界负责，避免一个 Provider 变成平行服务。

Provider 失败必须携带阶段化、脱敏诊断：至少区分请求、供应商响应、下载、
完整解码、MIME 一致性、尺寸和质量检查。真实请求计数在请求尝试时写入，
不能等完整校验成功后才写；下载完成数也按实际下载结果记录。

## 未来接入步骤

1. 将参考实现迁入 `services/life-core/app/image_provider.py`，保留显式
   `REAL`/`MOCK` 类型，不根据是否联网猜分类。
2. 在 `config.py` 增加独立 `image_api_key`，只从
   `IMAGE_PROVIDER_API_KEY` 读取；不得回退到 DeepSeek/智谱聊天 Key。
3. 在 `create_app()` 构造 Provider 并注入 `Moments(store, settings, memory, image_provider)`。
4. `Moments.generate(caption)` 仅构建结构化 prompt 并调用 Provider，
   `run_one()` 的 authorized-before/after 双检查不变。
5. 超时或结果不确定保持 `unknown`/`PROVIDER_RESULT_UNKNOWN`；共享 HTTP
   client 不得自动重试生图 POST。
6. 成功后先把媒体写为 owner 私有待发布资产，再关联现有 moment；
   原始供应商 URL 与 Key 不下发前端。
7. 只有接入完成并再次完成真实烟测、私有读取和越权拒绝后，才可把 B
   真实验收从 `BLOCKED` 改为 `PASS`。

## 错误映射

| Provider 条件 | Moments 建议状态/错误码 |
| --- | --- |
| 独立 Key 缺失、账户 401/403、模型不可见 | `pending_provider / IMAGE_PROVIDER_UNAVAILABLE` |
| 价格不再免费或超出硬预算 | 不发送请求，`pending_provider / IMAGE_BUDGET_BLOCKED` |
| 429 | `failed / IMAGE_RATE_LIMITED`，有界退避需单独预算门禁 |
| timeout、结果不确定的 5xx | `unknown / PROVIDER_RESULT_UNKNOWN`，不自动重发 |
| 下载/解码/尺寸/MIME/SHA 校验失败 | `failed / IMAGE_VALIDATION_FAILED` |
| 成功并通过全部校验 | `generated`，再执行发布事务 |

