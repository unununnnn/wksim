# 33 · release guard 候选：基准证据与不改 production 的结论

2026-09-11。对象：zzmg3k47（24,665 组，tick 98,700；真实累计 creep
99.881013 ms = 组内 work-over 14.535828 ms + 组外 85.345185 ms）。结论：本次
离线证据不足以支持把 production 的 final guard 从 1 ms 改为 2 ms；
`Simulator/wksim_runtime/joint_rate.py` 未改。

## 宿主实测

环境为 WSL Ubuntu-22.04、Python 3.10.12。对四档 `time.sleep` 各测 10,000 次，
JSON 保留全部 40,000 个过冲值：

| 请求 | median | p95 | p99 | p99.9 | max | >1 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.2 ms | 70,215 ns | 92,646 ns | 147,047 ns | 280,431 ns | 661,343 ns | 0 |
| 0.5 ms | 75,989 ns | 100,584 ns | 132,174 ns | 290,367 ns | 1,214,085 ns | 1 |
| 1.0 ms | 89,129 ns | 124,483 ns | 193,345 ns | 417,605 ns | 1,225,803 ns | 1 |
| 2.0 ms | 74,285 ns | 128,488 ns | 227,184 ns | 369,994 ns | 564,360 ns | 0 |

中位数为 70–89 us；40,000 次中只有两次超过 1 ms。尾部存在，但本次样本不能
证明其发生频率在真实联合飞行中足以支配累计拖慢。

## 确定性标注模拟

`tools/benchmark_joint_rate_release.py` 重放 zzmg3k47 的逐组真实 work 时长，并按
production 逻辑反复执行最长 2 ms 的 sleep；最终 guard 作为精确 spin。所有排序后
的实测过冲按分位秩和请求时长交错重放。模型明确不含组间 health、记录、调用方调度
及其他工作，所以它不是生产证明。

| 候选 | 模拟 creep | sleep 调用 | 越过释放边 |
| --- | ---: | ---: | ---: |
| 现有 1 ms | 14.761631 ms | 48,921 | 1 |
| 假设 2 ms | 14.535828 ms | 41,058 | 0 |

2 ms 候选在这一次确定性重放中减少 0.225803 ms，只消除了一个合成尾部越界；其余
creep 全部来自已记录的组内 work-over。这个差值仅占真实 85.345185 ms 组外拖慢的
0.27%，不能解释或可靠消除 #83 的失败。

## 判定与代价

当前证据支持继续定位 85.345185 ms 的组外区间，不支持改 production。2 ms guard
每组会比 1 ms guard 最多增加约 1 ms busy spin；24,664 个相邻区间的上界是
24.664 CPU 秒 / 197.312 墙钟秒，即单核 12.5%。实际 CPU 代价尚未测量，因此不以
这个上界声称真实性能回归，但在收益未被真实运行证明前不引入该候选。

## 边界测试与身份

`validation/test_joint_rate.py` 钉住未变合同、0.9 ms 注入过冲和重复 sleep 模拟；
全套 15/15 通过。未运行 SITL、UE 或 MATLAB。

- 输入 rate JSONL SHA256：`62596ed95ce9fc631e42a4fb09bbce44cd6571ab2c808f3a3b65732b4ec4ca57`
- 工具 SHA256：`01d3ba43913754f435172f7a8fac7e2862f70a0dacf4ec195bccd9252948dbdb`
- 证据 SHA256：`b46ad1c86212783ad3b3a32aece31b502bf6e4e1aaf14d4bd0f2cc2f6f47dcdc`
- 证据：`validation/33-rate-profile/release-spin-20260911.json`（407,200 bytes）
