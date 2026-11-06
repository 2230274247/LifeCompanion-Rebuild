# A++ 对历史固定输出的合同回放

不是新模型调用；只是将旧P04分数交给新分离合同，P04八维数值原样保留。

| 阶段 | 合理选择 | S33 | S18 | S14–S16图像状态 |
| --- | --- | --- | --- | --- |
| baseline | 36/36 | PRIVATE_TEXT / TEXT_ONLY | SKIP / PRIVATE_SKIP | S14:NOT_APPLICABLE、S15:NOT_APPLICABLE、S16:NOT_APPLICABLE |
| retest | 34/36 | PRIVATE_TEXT / TEXT_ONLY | SKIP / PRIVATE_SKIP | S14:NOT_APPLICABLE、S15:NOT_APPLICABLE、S16:NOT_APPLICABLE |

失败场景保留供审查：S12、S36

限制：本地规则对S12的“第一次训练”等歧义不作自动裁决；正式语义质量仍需新的真实模型调用及真人复核。