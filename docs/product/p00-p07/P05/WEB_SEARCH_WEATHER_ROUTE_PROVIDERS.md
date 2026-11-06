# P05 当前Provider

2026-11-04；PARTIAL。

| 能力 | 当前真实结果 | 边界 |
| --- | --- | --- |
| 地点检索 | Open-Meteo geocoding真实返回候选与来源时间 | 候选必须由用户选择，不擅自认定家庭地址 |
| 天气 | Open-Meteo真实forecast回执 | 模型天气估计，不是测站实况；时区明确，当前结果超过2小时拒绝 |
| 路线 | OSRM公开demo真实驾车距离/时长 | 没有实时交通，不能称为实时车程；无SLA |
| 通用搜索 | 未配置SearXNG，真实API返回blocked | 尚无搜索结果，不能用百科或LLM知识冒充全网搜索 |
| STT/TTS | 未配置并验收 | 不使用聊天Key试探收费音频端点 |

公开地标探测先分别返回200；正式Core第一次天气请求503，保存失败账本，
没有天气结论。随后在同一持久库设置总硬上限4，只显式恢复一次天气请求，
并完成路线与地点检索；三份回执均包含URL和取得时间。所有地点为上海公开
测试坐标，没有生产/个人数据。DeepSeek和图像调用0。

Open-Meteo免费服务条款限定非商业使用；本次仅隔离研究验收，不能据此确认
商业生产可用。正式发布须选择符合用途的已获授权服务，不新增付费账户。
OSRM demo用于合理低频测试，结果是静态道路模型；到达时间明确时可根据
实际返回时长另加15分钟规划余量，不代表交通概率或自动创建提醒。

原始官方来源：

- Open-Meteo文档：https://open-meteo.com/en/docs
- 服务条款：https://open-meteo.com/en/terms
- OSRM服务使用政策：https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy
- SearXNG API：https://docs.searxng.org/dev/search_api.html

当前真实Provider/API证明不等于聊天、提醒草稿或浏览器端到端通过。
