# P04图像Provider实际盘点

2026-11-04；状态BLOCKED_IMAGE_PROVIDER。

当前Rebuild隔离配置的模型供应商仍为DeepSeek，原地址与Key未变。
这是聊天/记忆模型配置，不能据此认定存在可用图像API。
源码中的旧图像实现只在memory_llm_provider=zhipu且聊天Key存在时
调用images/generations；模型名cogview只是代码默认值，不是授权、
网络可用、余额、版权条款或稳定额度证明。

本轮不切换供应商、不读取/打印生产Key、不探测收费生成端点、不创建账户。
临时验收Core显式memory_llm_key=""，实际出现pending_provider/
IMAGE_PROVIDER_UNAVAILABLE，无图片数据、无模型账本增长。
这项失败态可用，不代表生成成功。当前图像余额/精确价格/区域许可UNKNOWN。

后续需要将图像凭据与聊天凭据分开，显式配置已获授权供应商；
实现submit/poll/download/metadata接口、稳定幂等键、供应商job_id、
调用预算和真实文件保存。当前尚无完整ImageProvider接口、
持久供应商回执或结果查询适配器，不能重试unknown来替代查询。

本轮已阻止unknown重提：超时、HTTP408/5xx、重启时未确认请求均保留unknown；
API重试返回409、页面不提供再次生成。明确拒绝/连接失败才允许
有限重试，仍受attempts<3限制。非法图片/不可信下载主机等失败
不允许盲目重提。真正的供应商故障、轮询、下载恢复、幂等计费仍未实测。

03:02评分增量只使用原DeepSeek聊天接口：新增评分1次，
input 1,363/output 457 token。没有任何图像请求；本Provider状态仍BLOCKED。
验收重放预算0，未切换供应商或读取新Key。
