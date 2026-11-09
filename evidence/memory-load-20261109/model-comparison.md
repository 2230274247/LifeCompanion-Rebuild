# 本地语义模型对比记录

日期：2026-11-09。全部输入为合成语料，不读取服务凭据或真实用户资料。实验仅使用本地ONNX推理，模型下载与校验是显式离线准备步骤，查询不会下载模型。

100条不同日常陈述各配一个独立改写问题，另有24个语料未包含的经历问题。阈值只影响是否返回，并不能修正排序。指标按预设单一gold严格计算，某些宽泛问题可能有多个合理相关答案；没有为了提高指标而改写gold。

| 模型与配置 | 正例第一名 | 正例前8名 | 24负例误返回 |
| --- | ---: | ---: | ---: |
| BGE-small-zh，0.58 | 39 | 40 | 0 |
| BGE-small-zh，0.52 | 62 | 71 | 0 |
| BGE-small-zh，0.40 | 66 | 91 | 14 |
| BGE-small-zh加标准检索指令，0.48 | 60 | 72 | 0 |
| multilingual-e5-small量化，0.86 | 71 | 92 | 12 |
| BGE中文cross-encoder，置信度0.1，仅向量前8候选 | 37 | 43 | 0 |
| BGE-large-zh量化，0.48 | 82 | 87 | 0 |
| BGE-large-zh量化，0.46 | 86 | 92 | 1 |

最终选择BGE-large-zh量化、默认阈值0.48，并再次通过真实网关对原144题和额外负例验收。上述100正例及24负例参与了模型/阈值选择，属于校准证据，不能宣称独立盲测或生产准确率。

## 固定公开来源

- 大模型：Xenova/bge-large-zh-v1.5，revision `a48549b3259a6165364f226599cd91f39923d5d5`；上游BAAI/bge-large-zh-v1.5。量化ONNX为327,363,707字节，1024维，CLS池化。各文件下载按固定revision，校验HuggingFace LFS SHA256或Git blob SHA1；逐文件SHA256见 `bge-large-score-audit.json`。
- E5实验：Xenova/multilingual-e5-small，revision `761b726dd34fb83930e26aab4e9ac3899aa1fa78`。384维，mean池化，标准query/passage前缀；未接入生产。
- 重排实验：Xenova/bge-reranker-base，revision `280bcc27a84e0b898c251e06fddb25171bd9b101`；未接入生产。

模型权重、分词器、临时下载和运行缓存不进入Git。对应源模型采用MIT许可；本轮未改变fastembed==0.7.4及onnxruntime依赖版本。许可证来源与准备步骤仍须随部署机器一同保留。

## 失败与兼容性

- 直接联网未使用环境代理时，HuggingFace连接被拒；正常环境代理路径可达，后续固定revision下载成功。
- BGE-large上游tokenizer_config中的model_max_length使用超过平台整数范围的哨兵值，fastembed加载报OverflowError。保留下载原件，另生成context-512运行目录，只将分词长度固定为模型支持的512；ONNX通过硬链接复用，原文件未改。
- 旧BGE-small的144题真实HTTP首轮仅44题命中，完整保存为 `recall-baseline-058.json`。实验结论没有覆盖或删除这一失败记录。
