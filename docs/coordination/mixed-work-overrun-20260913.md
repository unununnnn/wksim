# mixed-work-overrun-20260913：oxv29042 工作超额分解

范围：只读分析已失败场次 `joint-public-flight-oxv29042`（RateUnmet，latched tick 131760，lateness 100,034,744 ns）。不改动实现；本结果**不构成全场通过**。

## 输入与身份（SHA-256）

| 输入 | SHA-256 | 核对 |
|---|---|---|
| raw `rate.jsonl` | `8725b63c…edee8b91` | 与 bundle-manifest、main-rate-analysis `trace_sha256` 一致 |
| raw `joint-wire.jsonl` | `20d0634e…f3504c50` | 本场唯一 wire |
| `joint.py` 快照 | `f5433c2e…e0241d50` | wire kinds/字段/程序顺序按此核对 |
| `joint_rate.py` 快照 | `0b53a16a…a6da25c4` | 与 Windows 选包内同名字节一致 |
| `run_joint_flight.py` 快照 | `65c7a867…c56d8161` | 与 manifest 一致；wire `record()` 在其 829 行 |

复跑：`validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py --rate-analysis <选包>/main-rate-analysis.json --output <out.json>`（WSL Ubuntu-22.04，纯标准库）。脚本 SHA `e5a0db2b…d81595fe`，输出 `mixed-work-overrun.json`。

## 方法要点

- rate 组：`actual_start_ns`/`actual_end_ns` 为 `time.monotonic_ns()`；wire `wall` 为同进程 `time.monotonic()-started`。单一时钟偏移 S 由程序顺序约束（组start < 组内首条 interior wire、末条 < 组end）在全部 32,930 组上交出非空区间 **[S_lo, S_hi]，宽 436,151 ns**，0 违例。
- tick 对齐反控：真实映射 P+1..P+4 非空；错误映射 P..P+3 与 P+2..P+5 均**被判空拒绝**（`wrong_alignments_rejected: true`）。自测试 3/3 通过。
- 与留存分析交叉核对：creep/work_over/release_excess 总额（99,780,808 / 15,139,984 / 84,640,824 ns）全部逐项一致。

## 数值结果


**work>period（8ms）的组共 7 个，总超额精确为 15,139,984 ns**（与留存 `work_over_total_ns` 一致）。最大组：**start_tick 127,940，work 13,140,957 ns，超额 5,140,957 ns**。

| start_tick | work_ns | over_ns | native并集 | AP per-stack | PX4 per-stack | 最大wire间隙 |
|---|---|---|---|---|---|---|
| 1,996 | 10,322,358 | 2,322,358 | 6,571,583 | 836,653 | 5,945,464 | actuator→actuator@2000, 5.73ms |
| 5,500 | 9,220,281 | 1,220,281 | 6,242,375 | 1,002,964 | 5,424,296 | actuator→actuator@5504, 5.24ms |
| 47,736 | 8,452,778 | 452,778 | 1,328,072 | 987,175 | 516,516 | step@47737→sensor@47738, 1.18ms |
| 57,452 | 10,196,259 | 2,196,259 | 2,753,595 | 2,544,580 | 492,090 | step@57454→sensor@57455, 2.70ms |
| 87,640 | 11,311,134 | 3,311,134 | 2,406,756 | 2,250,922 | 315,851 | step@87642→sensor@87643, 3.52ms |
| 119,280 | 8,496,217 | 496,217 | 2,458,547 | 2,306,658 | 996,599 | step@119283→sensor@119284, 1.85ms |
| 127,940 | 13,140,957 | 5,140,957 | 8,165,479 | 7,785,574 | 513,704 | sensor→actuator@127943, 6.87ms |

两类主导形态：早期 2 组（1996/5500）与最大组（127940）由 native 输入等待主导（分别 PX4≈5.9ms、AP≈7.8ms per-stack）；中间 4 组由 step→sensor 的 tick 间区主导（1.18–3.52ms），native 并集仅 1.3–2.8ms。

## 下一处值得测的具体代码区域

`Simulator/wksim_core/joint.py` 的 `advance()` 已带 `WKSIM_JOINT_CPU_TIMING` 分段括号（marks 三段：`health_and_models` / `encode_send` / `native_inputs`）与 `_native_wait` 的 wait_ap/wait_px4 精确 bracket，但现有记录是抽样的（>2ms 或 tick%250）。建议：复跑混合场景时对该诊断开**全量普查**（仅诊断、diagnostic_only，不改生产阈值），覆盖上述 7 个组的 tick 窗口——即可把 step→sensor 区拆成模型 RPC（`receive_workers`/commit）与 encode_send，把 sensor→actuator 区拆出纯 wait 与 acknowledge/barrier 开销。归因前不得声称任一区为 OS/CPU 原因。

## 限度

- pre/post 边界拆分是区间且跨组相关；两栈区间有重叠，per-stack 不可相加，仅并集可减。
- wire 内部段含记录/序列化/I/O 等待/可能被换出；残余未归因 OS。
- 单场失败分解，非全场验收；`performance_pass=false`，`full_run_acceptance=false`。
