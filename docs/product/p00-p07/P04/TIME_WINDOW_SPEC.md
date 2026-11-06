# P04时间窗实际边界

2026-11-04，Asia/Hong_Kong；状态PARTIAL。

复用 `app/moments.py` 与 `moment_settings`。配置默认关闭，独立记忆、生图授权
均开启后才可保存enabled=true。IANA时区及三个递增HH:mm结束时刻持久化；
11:00、17:00、23:00为初始建议，未保存前为proposed配置。

第一窗从前一天晚窗结束至当天早窗结束；默认相当于23:00至次日11:00，
包括夜间与05:00后的早间消息。第二窗11:00至17:00，第三窗17:00至23:00。
均按半开区间 `[start,end)`，消息以memory_evidence.message_at归窗，
没有该列值的历史数据才回退created_at。首次启用前的消息不追溯进入窗口。
事件发生时刻、消息来源时刻与任务created_at不同，不用模型猜日期。

Core后台线程每20秒扫描结束窗口并执行queued任务，浏览器关闭不影响。
SQLite唯一键(user_id,window_end)及稳定moment_id防止同窗重复落库；
Core停止期间依照最后window_end补扫。后台线程依赖Core进程存活，
不等于已交付独立常驻调度服务。

本轮真实时钟已验证自定义结束时刻，未通过改系统时钟或直接调用未来schedule
伪装自动触发。运行记录位于 `evidence/p04/privacy-*/privacy-live.json`；
完整成功运行见MOMENT_E2E.md。默认11:00实际结算、跨日期/DST、
配置更改后的旧任务处理与长期停机仍待完整验收。

2026-11-04评分增量后，窗口先写`awaiting_score`并独立claim评分，完成/失败/
unknown后不会被下一轮`schedule()`重新创建。真实03:02窗口的三条来源
`message_at`均在窗口内；事件`occurred_at`仅作为事件语义字段，不用于替代
消息归窗。默认11:00、跨日期、DST和长期离线仍待补充。
