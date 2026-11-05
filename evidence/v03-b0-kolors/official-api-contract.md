# SiliconFlow Kolors B0 官方接口合同

## 核验范围

- 核验时间：2026-11-04 13:57–14:01，Asia/Hong_Kong。
- 接口文档：
  <https://api-docs.siliconflow.cn/docs/api/images-generations-post>
- 当前价格：
  <https://www.siliconflow.cn/pricing>
- 速率限制：
  <https://api-docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation>
- 更新公告：
  <https://api-docs.siliconflow.cn/docs/release-notes/overview>

本文件只记录官方页面实际展示内容，不据旧博客或第三方实现猜接口。

## 创建图片请求

| 项目 | 官方现行值 |
| --- | --- |
| 方法与端点 | `POST https://api.siliconflow.cn/v1/images/generations` |
| 鉴权 | `Authorization: Bearer <账户 API Key>`，必填 |
| 水印 | `X-Enable-Watermark` 默认 `1`；只有需要下游处理时才传 `0`，并由开发者负责补充显式水印 |
| 追踪 | 可传 `X-Trace-Id`；平台也会生成响应头 `x-siliconcloud-trace-id` |
| 链路追踪 | 可传 W3C `traceparent` |

请求体：

| 字段 | 类型/约束 | B0 使用 |
| --- | --- | --- |
| `model` | string，必填 | `Kwai-Kolors/Kolors` |
| `prompt` | string，必填 | 一条虚构中文生活场景 |
| `negative_prompt` | string，可选 | 排除文字、品牌、畸形手部等 |
| `image_size` | `[width]x[height]`，Kolors 必填 | `960x1280`，官方 Kolors 推荐值 |
| `seed` | integer，`<= 9999999999` | `20261104` |
| `num_inference_steps` | 默认 `20`，范围 `1..100` | `20` |
| `guidance_scale` | 默认 `7.5`，`<= 20`，仅适用于 Kolors | `7.5` |
| `cfg` | 仅 Qwen/Qwen-Image | 不使用 |
| `image`, `image2`, `image3` | 图生图/编辑场景 | 不使用 |

文档没有列出通用 `batch_size` 字段。B0 只发一次请求，并把响应必须恰好包含
一张图片作为客户端硬约束。

## 成功响应

HTTP `200`，结构如下：

```json
{
  "images": [{"url": "string"}],
  "timings": {"inference": 0.1},
  "seed": 0
}
```

- 响应头 `x-siliconcloud-trace-id` 是平台唯一追踪标识。
- 返回图片 URL 有效期为一小时，必须立即下载。
- URL 带有时效签名，B0 证据只记录 host，不保存完整 URL。

## 已文档化错误

| HTTP | 官方响应摘要 |
| --- | --- |
| `400` | `{"code":20012,"message":"string","data":"string"}` |
| `401` | `"Invalid token"` |
| `403` | `"Forbidden"` |
| `404` | `"404 page not found"` |
| `429` | `{"message":"Request was rejected due to rate limiting...","data":"string"}` |
| `503` | `{"code":50505,"message":"Model service overloaded. Please try again later.","data":"string"}` |
| `504` | 官方在线 schema 仅示例为 `"string"`，具体正文不做猜测 |

生图接口文档没有单独列出 `500`。本 B0 不自动重试 `429`、`5xx` 或超时，
以免在结果不确定时重复请求。

## 账户、价格与预算门禁

官方价格页当前逐项显示：

`Kwai-Kolors/Kolors -> 生成图片 -> 每图片 -> 免费`

官方 Rate Limits 页面同时说明：

- 免费模型调用免费，费用账单中的调用消耗为 0。
- 使用全部免费模型需要完成实名认证。
- 图像生成类别通用上限为 `IPM: 2`、`IPD: 400`；B0 只使用 1 张。

官方 2026-08-11 公告说明 `/user/info` 已于 2026-08-14 停止服务，
替代账户信息 API 尚未上线。因此当前无法通过官方 API 自动读取余额。
B0 的处理是：

1. 动态确认官方价格仍为每图片 0 元。
2. 用独立 Key 读取账户可见模型列表，确认 Kolors 可见。
3. 把预算硬上限设为 `¥0.00`、请求上限 1、图片上限 1。
4. 任一条件不可确认即 `BLOCKED`，不调用生图接口。

