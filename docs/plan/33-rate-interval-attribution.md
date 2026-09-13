# 33 · zzmg3k47 组间区间归因

2026-09-11。`tools/analyze_joint_rate_intervals.py` 对保留的
`validation/joint-public-flight-zzmg3k47/rate.jsonl` 做纯离线、失败即停的区间分析。
工具不改 production、不运行 SITL，也不改变 1 ms 步长、单锚、无追赶或累计 100 ms
门槛。

## 输入与闭合结果

输入有 24,665 对 `rate_group_start` / `rate_group_end`，epoch 为
`1a4e2ccf023f4bb8bb880bbd2ea96926`，只有 `(segment_id=1,
request_id=config, requested_rate=0.5, transition=false)` 这一种身份；tick 从 40
连续到 98,700。分析器校验记录顺序、成对字段、8 ms 组周期、四 tick 跨度、理想
时序连续、实际释放边界、无组重叠和无追赶。

每个相邻区间按前一组计算：

`creep = current_start - previous_start - 8 ms`

`previous_work_over = max(0, previous_end - previous_start - 8 ms)`

`release_excess = creep - previous_work_over`

24,664 个相邻区间精确闭合为：

| 可观测量 | 总计 |
| --- | ---: |
| start-to-start creep | 99,881,013 ns |
| 前一组 work-over | 14,535,828 ns |
| release excess | 85,345,185 ns |

最后一组没有后继区间，其 work-over 为 0，所以这里的 14,535,828 ns 与此前全组统计
完全一致。

## 分布

release excess 分布如下；零值 86 个，非零值 24,578 个：

| 区间 | 数量 | 合计 |
| --- | ---: | ---: |
| 0–10 us | 23,827 | 10,236,140 ns |
| 10–100 us | 429 | 17,989,350 ns |
| 100–500 us | 319 | 54,343,233 ns |
| 0.5–1 ms | 2 | 1,375,232 ns |
| 1–2 ms | 1 | 1,401,230 ns |
| >2 ms | 0 | 0 ns |

最大单次 release excess 是 tick 16,384→16,388 的 1,401,230 ns。最大的 20 个
区间合计 8,594,605 ns，只占 release excess 的 10.07%；它不是少数极端长尾可单独
解释的故障。原始 trace 没有 `timing_probe` 字段，因此现有证据只能观察组体 work、
组间 interval 和释放超额，不能再把 85,345,185 ns 可靠拆成 health 检查、记录写入、
sleep 过冲与操作系统调度。

## 判定

这次归因排除了“同一组 work 与同一组 creep 配对”的错误算法，也确认 85.345185 ms
主要由大量分散的组间释放超额累积。它仍不支持修改 production 或再次真实飞行。
下一候选应先在保留原合同的前提下，对 `begin_group` 的 entry、initial health、循环
health、每次 sleep 与最终 release 分段记录单调时钟；形成测量支持后再决定是否有可
封存的减负候选。

验证：`python -B -m unittest validation.test_joint_rate_intervals`，7/7 通过。

- 输入 SHA256：`62596ed95ce9fc631e42a4fb09bbce44cd6571ab2c808f3a3b65732b4ec4ca57`
- 分析器 SHA256：`14ed9d64bb0daf0fb2ef9f4e21028a4ec164bb1255f98701542b59a68d2538a8`
