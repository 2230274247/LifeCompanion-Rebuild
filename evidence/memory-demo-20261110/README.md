# 丰富历史账户与自行验收（2026-11-10）

状态：PASS（本轮账户、120条合成历史、3次真实问答和指定页面）；整体P5仍PARTIAL。

- `dataset.json`：120条合成历史均通过当前账户手动抽取API发布；12个月×10类主题，2025-11-02至2026-10-20。采用离线抽取，不是120条DeepSeek抽取测试；无伪造AI回复/历史会话。
- `first-row.json`：单条导入与日期、Memos正文读回探针。
- `acceptance.json`：真实登录、health、分页、日期与详情、真实DeepSeek3次持久化回复。125条API每页50条读3页，无重复；120条具有明确发生日的合成历史。
- `page-2.png/yml`、`page-2-state.json`：真实UI点击下一页，页码2、共125段，无横向溢出（1249px视口）。
- `date-filter.png/yml`、`detail.png/yml`：10月2日筛选仅1条，打开实际详情。
- `october-chat.png/yml`、`october-chat-state.json`：真实10月回顾，10条记录、10个来源引用，说明合成数据与覆盖边界。
- `ui-network.txt`：记忆列表/详情的实际life-api 200；页面导航有被取消的请求，保留原始观察。
- `browser-errors.txt`：既有`/api/tags`403，未将全站声称为零错误。

三次新会话实际回答：

| 输入 | 核验事实 | 耗时 |
| --- | --- | --- |
| 2026年10月2日，我和林晓去了哪里？ | 杭州龙井村，有引用 | 7.31秒 |
| 2025年11月，我在读书会分享了哪本书？ | 《小王子》、11月6日，有引用 | 7.22秒 |
| 请回顾2026年10月的生活记录，按活动整理，并说明本次查到了多少条。 | 按日期列出10条，含龙井村/栗子烧鸡/苏东坡传/手冲咖啡等，10个引用，说明可能不完整 | 6.19秒 |

以上都是少量验收样本，不是系统全量准确率或平均延迟。没有完成P5原矩阵重跑、长期稳定/成本、提醒联网跨工作树整合。

## 复现

服务沿用本机隔离网关3001、聊天3810、核心8010、Memos15231、Mongo27019；不改变正式主库。账户信息只保留在既有gitignored文件中，没有将登录口令或服务凭据复制进证据。

```bash
python scripts/prepare-memory-demo.py --output evidence/memory-demo-20261110/dataset.json
```

导入使用固定来源ID，可重复提交，遵循产品原有幂等/撤回规则，不会强行覆盖已撤回来源。它只调用127.0.0.1的认证用户API，不直写数据库、不读服务密钥。

```bash
python scripts/acceptance-memory-demo.py --output evidence/memory-demo-20261110/acceptance.json
```

后者会进行3次真实DeepSeek聊天。账户/口令与操作说明见 [自行验收指南](../../docs/development/MEMORY_MANUAL_ACCEPTANCE.md)。本轮没有改变产品/上游源码；不需要新的上游补丁。
