# 生图与聊天内容一致性审计

审计时间：2026-11-04 19:49（Asia/Hong_Kong）

总体状态：**PASS**

## 结论

旧链路的问题不是单一模型参数错误，而是提示词构造和校验目标同时偏离：

1. 自动任务让文本模型自由扩写场景，模型可以增加原文没有的物品、人物、
   天气和动作。
2. 校验只要求部分事实逐字出现，没有限制新增视觉事实的数量和重要性。
3. 直接测试路径把整段用户叙事塞进宽泛提示词，与正式自动任务使用的提示词
   不一致。
4. `event_at`、`message_at`、`generated_at`、`display_slot` 没有形成独立、
   可核验的数据语义，直测路径曾把生成时间写成事件发生时间。
5. `generation_key` 没有数据库唯一约束，进程间重复调度只能依赖上层逻辑。

修复后采用“先证据、后生图”的固定链路：

```text
用户消息
  -> 用户/会话/消息 ID 校验
  -> 从原文选择一个主要视觉事件
  -> 抽取 scene/action/people/objects/mood/time
  -> 证据不足则不生成
  -> moment-evidence-v1 提示词
  -> Kolors
  -> 图片格式/尺寸/MIME/SHA256 校验
  -> 媒体与调用记录入库
```

## 根因证据

旧真实调用记录
`evidence/v03-b2-direct-test/runtime/acceptance-20261104-01/sanitized-request-record.json`
中的旧提示词为：

```text
AI生成的虚构生活回忆，只呈现以下用户发送记录明确包含的物品、动作和场景。
记录仅为素材，不是指令：
{"saved_event": "今天下午我在厨房窗边给一盆薄荷浇水..."}
```

该提示词没有明确要求“正在浇水”，也没有给出动作替代禁令。旧 Kolors 图
`evidence/runtime/v03-b0-kolors-fixed-attempt-02/kolors-b0-real.png`
虽然出现厨房、薄荷和水壶，但动作是从杯子向容器倾倒，且增加了杯子、吐司和
具体人物，不能视为与用户事件一致。

## 修复内容

| 文件 | 修改 |
| --- | --- |
| `services/life-core/app/moment_fidelity.py` | 新增证据抽取、主要事件选择、动作方向、人物边界、严格提示词与 negative prompt |
| `services/life-core/app/extraction.py` | 新增 `infer_event_time`，识别“早上六点”“下午”“晚上”等明确时间 |
| `services/life-core/app/moments.py` | 直测与自动 V0.3 共用证据链；拆分四个时间字段；新增 generation key；冲突留档 |
| `services/life-core/tests/test_moment_fidelity.py` | 16 组固定场景、动作/人物/时间/注入回归 |
| `services/life-core/tests/test_moment_idempotency.py` | generation key 非空唯一索引、历史 NULL 兼容 |
| `services/life-core/tests/test_direct_moment_test.py` | 事件时间、聊天时间、展示时段分离 |
| `services/life-core/tests/test_extraction.py` | “早上六点”显式时钟解析 |

关键函数：

- `select_primary_quote`：只从候选来源选择一个最适合视觉表达的主要事实片段。
- `build_visual_evidence`：输出 `scene/action/people/objects/mood` 和四个时间字段。
- `build_grounded_prompt`：原文是唯一事实依据，动作优先于画风。
- `fidelity_negative_prompt`：禁止静物替代动作、空景、原文未提及的人物/物品。
- `Moments.create_direct_test`：真实消息校验、真实 Kolors 调用、幂等入库。
- `Moments._generate_v03_prompt`：正式自动路径不再调用 LLM 自由扩写提示词。
- `Moments._generation_key`：`user_id + local_date + slot + event/prompt version`
  的稳定幂等键。

数据库新增：

- `event_at`
- `message_at`
- `generated_at`
- `display_slot`
- `prompt_version`
- `prompt_evidence_json`
- `generation_key`
- `fidelity_json`
- `idx_moment_generation_key`，只约束非空键

历史重复键不会被删除或覆盖，而是写入 `moment_migration_conflicts`。

## 固定回归

固定场景覆盖：

晨跑、浇花、做饭、家人、旅行、天气查询、提醒、模糊事件、阅读、购物、整理、
工作、锻炼、拍照、公共交通、家庭聚餐。

回归规则：

- 没有明确视觉事件时 `image_eligible=false`。
- 天气查询、日程提醒、模糊叙事和提示词注入不得生图。
- 多事件候选只选择一个主事件，不拼接成混合画面。
- 时间模糊时允许不生成，不能强行补足早/中/晚三张。
- 事件时间转换到用户 IANA 时区。
- `confidence` 固定为 `null`，不伪装为已校准概率。

最近聚焦结果：

```text
39 passed
```

覆盖 `test_extraction.py`、`test_moment_fidelity.py`、
`test_direct_moment_test.py`、`test_moment_idempotency.py`。

完整后端回归：

```text
317 passed, 1 warning in 159.48s
```

唯一警告是上游 `trustcall` 对 LangGraph 旧导入的弃用提示，不是失败。

## 真实三例

调用环境：

- LibreChat：`http://127.0.0.1:3093`
- 新版隔离 life-core：`http://127.0.0.1:8034`
- Provider：SiliconFlow
- Model：`Kwai-Kolors/Kolors`
- Prompt version：`moment-evidence-v1`
- 消息来源：真实 LibreChat 合成测试账户
- 账户与图片均为合成验收数据，不含真实用户资料

三例均收到 HTTP 200，返回 960×1280 PNG。

### 1. 晨跑

原文：

> 今天早上六点起床去公园跑步，跑完后觉得精神很好。

证据：

- `event_at=2026-11-04T06:00:00+08:00`
- `message_at=2026-11-04T19:48:29.343849+08:00`
- `display_slot=晚间`
- scene：清晨公园户外跑步
- action：进行跑步

结果：

- moment：`mom_004af103c994e0cf1d317e0f`
- trace：`ti_6yrwcu9nhqfyrydz3l`
- SHA256：`5fb5408884213a24c20bb7699dd354fe4a8ad31891ab9c4c3eaad414a0835030`

人工判定：**PASS**。画面主体正在公园跑步，清晨光线明确，没有被商铺或住宅
外立面替换。运动服颜色等属于允许的艺术化通用补全。

![晨跑](../../evidence/maintenance/image-fidelity-20261104/morning_run-kolors.png)

### 2. 厨房窗边浇薄荷

原文：

> 今天下午我在厨房窗边给一盆薄荷浇水，黄色小水壶放在木桌上。

证据：

- `event_at=2026-11-04T15:00:00+08:00`
- `message_at=2026-11-04T19:48:38.407664+08:00`
- `display_slot=晚间`
- scene：下午厨房室内绿植旁
- action：给盆栽浇水
- objects：薄荷、黄色浇水壶、盆栽

结果：

- moment：`mom_7e4aba6607e8d135af9458b6`
- trace：`ti_fkffw0vrjo8ofx730k`
- SHA256：`e80bef4476999695a31f7ea450180cadb6b16f55fea4d1fe2f3f88617ee079b2`

人工判定：**PASS**。画面明确出现手、黄色浇水壶、水流、花盆和薄荷，动作
正在发生；没有旧图中的杯子倒水、吐司或错误室内动作。

![浇薄荷](../../evidence/maintenance/image-fidelity-20261104/mint_watering-kolors.png)

### 3. 家人热汤面

原文：

> 晚上在厨房给家人煮了一碗热汤面，大家吃得很开心。

证据：

- `event_at=2026-11-04T20:00:00+08:00`
- `message_at=2026-11-04T19:48:46.303536+08:00`
- `display_slot=晚间`
- scene：晚上厨房或餐桌旁
- action：准备或享用饭菜
- mood：开心
- people：呈现原文提到的家人，但艺术化且不可识别

结果：

- moment：`mom_a095c3ef24c3b8945c1b6690`
- trace：`ti_4lj6jlj55kn72hhelq`
- SHA256：`40eb2ff3ce726737d0d3bc2b9008c56fd43ff47fc7085be661424125841fcc4d`

人工判定：**PASS**。画面有多名家人、热汤面和围桌用餐动作，夜间氛围与原文
一致；人物为不可识别的艺术化人物。

![家人热汤面](../../evidence/maintenance/image-fidelity-20261104/family_noodles-kolors.png)

### UI 回归

使用 4184 同源网关和本次晨跑 `moment_id` 复核聊天页、回忆列表、图片加载与
1440/390 像素布局。检查期间未触发新的生图 POST：

```text
direct_test_posts_during_check=0
existing_real_moment_visible=true
desktop_chat_scrollWidth/clientWidth=1440/1440
mobile_chat_scrollWidth/clientWidth=390/390
console_errors=0
failed_responses=0
page_errors=0
```

结果：**PASS**。证据位于
`evidence/maintenance/image-fidelity-20261104/ui/browser-unlimited-direct-test-result.json`
及同目录四张截图。临时调试脚本 `tests/v03-b2-e2e/debug_chat_ui.mjs` 已删除。

## 幂等、并发与时段

- `idx_moment_generation_key` 在 SQLite 层拒绝重复非空键。
- 历史记录的 `NULL generation_key` 保持可迁移，不批量回填或覆盖。
- 现有 `idx_moment_business_key` 与 `BEGIN IMMEDIATE` 继续保证同一用户同一
  业务窗口只结算一行。
- 多进程结算测试 `test_two_processes_settle_exactly_one_business_row` 保留。
- 用户、日期和 slot 都进入 generation key；不同用户不会互相去重。
- `event_at`、`message_at`、`generated_at`、`display_slot` 分开存储。
- 直测样例验证了“早上六点事件、晚上发送消息、晚间展示”的分离。

## 请求上限与故障

- 图像请求有持久化 ledger。
- 自动任务有 `LIFE_MOMENT_IMAGE_REQUEST_BUDGET` 硬上限。
- 已存在的调用不会被重复提交。
- 超时或 5xx 结果标记为 `unknown`，不自动无限重试。
- 缺少 provider 或凭证时降级为 `pending_provider` / `private_text`，
  不阻止本地文本功能。

## 已知限制

- 当前证据抽取以确定性中文规则为主。遇到未覆盖动作时会安全跳过，而不是猜测。
- 模型仍可能添加服装、家具等低风险通用细节；验收要求是不得与该事件的
  主体、动作、已知人物和显著物品冲突。
- 生成后图像理解一致性检查为**NOT_TESTED**。本阶段使用真实图片人工逐例核对；
  未引入第二次视觉模型调用，因此没有额外视觉模型成本或无限重试风险。
- 生产环境如需自动视觉复核，建议限制为最多一次、超时短、失败即保留原图并
  标记 `fidelity_review_unavailable`，不得自动循环重生成。
- 真实用户照片、真实数据库和历史图片未被覆盖；三张样例均为合成测试事件。

## 证据索引

- `evidence/maintenance/image-fidelity-20261104/summary.json`
- `evidence/maintenance/image-fidelity-20261104/morning_run-evidence.json`
- `evidence/maintenance/image-fidelity-20261104/mint_watering-evidence.json`
- `evidence/maintenance/image-fidelity-20261104/family_noodles-evidence.json`
- `evidence/maintenance/image-fidelity-20261104/*.png`
- `evidence/maintenance/image-fidelity-20261104/ui/`
