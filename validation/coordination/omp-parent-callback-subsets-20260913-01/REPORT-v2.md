# omp-parent-callback-subsets-20260913-01 v2：双口径重算与结论收敛

**本版更正并取代同目录 REPORT.md（v1 与其 JSON/脚本全部保留）**。更正：① 双零子集仅 29 组，其观测上限是**子集局部**读数，不能排除含回调组尾段内的轮询/被换出；回调在场 ≠ 回调致迟。② v1 误用 release_excess≥10µs 作门槛；本版两个过滤器**分列同名**报告，不做静默替换。③ 末回调时间戳的价值是**无论成因地定位尾段**，不推断回调责任。④ 末完整字段候选实为 **5 标量**（sleep before/after/requested + loop-health before/after），非 1。

## 双口径结果（22,523 行 started + 1 行 rate_unmet@90132）

| 过滤器 | 选中 | 子集 | 选中行 | remaining 合计 | remaining 最大 |
|---|---|---:|---:|---:|---:|
| `release_excess_ge_10us`（v1 口径） | 699 | sleep=0,loop=0 | 18 | 33,033 ns | 3,147 ns |
| | | sleep≠0,loop≠0 | 637 | 50,341,257 ns | 284,613 ns |
| | | sleep≠0,loop=0 | 44 | 4,801,407 ns | 565,285 ns |
| `remaining_begin_ge_10us`（任务口径） | 681 | sleep=0,loop=0 | **0** | 0 | 0 |
| | | sleep≠0,loop≠0 | 637 | 50,341,257 ns | 284,613 ns |
| | | sleep≠0,loop=0 | 44 | 4,801,407 ns | 565,285 ns |

两口径差异恰为"entry 已晚但 begin 内无迟尾"的 18 行双零组。最大 remaining：tick 50304（565µs）、49240（485µs）、2124（285µs），全部 sleep≠0。末行 rate_unmet@90132：remaining 197,487ns，sleep×2/loop_health×1，尾段归属不可由聚合判定。

## 判定的收敛表述

- 双零子集观测上限 3,147ns 仅为**该 29 组内**读数；不含"纯轮询普遍无责"结论。
- 含回调 681 行的 55.1ms 尾段在聚合层面不可分；5 标量候选（sleep 前/后/请求值 + loop-health 前/后）可在下一诊断场把尾段定位于"末回调前/后"，**无论成因**；这不建立回调责任，也不作 OS/CPU 归因。

## 证据与 SHA-256

- 输入 rate.jsonl `cfbf8b98…b5436f0`；probe 源钉 `a8bac9ac…` 逐字一致；无新 raw 场。
- 脚本 `inspect_parent_subsets_v2.py` 与输出 `parent-subsets-uy9ov56b-v2.json` 的 SHA 见交付消息；v1 三件保留未动。
