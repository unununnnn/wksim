> Main integration, 2026-09-13: current acceptance is 84 consumer checks and 17 independent CLI fixtures, all passing. Earlier self-check counts did not prove the fixture ABI. See ../perf-stream-offline-acceptance-20260913-03/main-verdict.json. This is synthetic decoding acceptance; complete capture/flight acceptance remains unproven.

# Synthetic perf switch-stream fixtures — `ds-perf-stream-fixtures-20260913-01`

独立验收夹具子任务。唯一写入目录即本目录。**未读、未 import、未镜像任何 consumer/producer 实现**：
全部二进制 record 由本目录 `build_fixtures.py` 用标准库 `struct` 按合同字节定义直接构造
（`header8 + TID/TIME/CPU24 = 精确 32 字节 SWITCH record`，little-endian x86_64）。

- 合同来源：`docs/coordination/perf-stream-contract-20260913.md`
- 夹具性质：**全部 synthetic**。每份 `metadata.json` 带 `synthetic=true` + `synthetic_note`，
  `fixtures/index.json` 亦标注 `synthetic=true`。**没有任何夹具伪造真实飞行证据。**
- 运行环境：纯 Python 标准库；不编译、不运行 native、不动模型/ROS/生产文件、不派嵌套。

## 运行

```bash
python build_fixtures.py          # 重新生成 fixtures/ 与 index.json（确定性）
python build_fixtures.py --check  # 独立重新解码磁盘上的夹具并复核 expected.json
```

`--check` 会逐文件重算 `index.json` 的 SHA256、按合同规则重新解码 `raw.bin`、重算窗口整数交集，
再与各 `expected.json` 逐键比对；当前结果 `cases=17  mismatches=0`。
连续两次生成的 `index.json` SHA 相同（确定性已验证）。

## 目录布局

```text
fixtures/
  index.json                 # schema + 每个 case 的文件 SHA256/字节数
  <case>/raw.bin             # 原始 record 拼接（无归一化、无过滤）
  <case>/metadata.json       # wksim.perf_switch_stream.v1，含 synthetic 标记
  <case>/windows.json        # 可选：wksim.perf_windows.v1
  <case>/expected.json       # 断言：rejected / checksum_ok / pairs / errors / intersections_ns
```

`expected.json` 字段语义（供独立验收器逐键比对）：

| 字段 | 语义 |
| --- | --- |
| `rejected` | 该夹具是否**必须被拒绝**（任一 violation 存在即为 true） |
| `checksum_ok` | 元数据整数字段类型正确**且** `captured_bytes == len(raw.bin)`；与完整性/采集错误独立 |
| `pairs` | 保留的完整 out→in 配对数量；被拒夹具一律 0 |
| `errors` | 必须出现的 violation 码集合（见下表） |
| `intersections_ns` | 每个窗口与 observed span 的**精确整数**交集（仅声明该键的夹具参与比对） |

## 夹具清单（17）

| case | 期望 | 覆盖点 |
| --- | --- | --- |
| `normal_two_pairs` | 接受，2 对，交集 `[150000,0,100000]` | 正常两 pair + 跨窗口精确整数（含真 0 交集窗口） |
| `window_intersection_integers` | 同上，显式钉住整数交集 | 交集不得被四舍五入或丢弃空窗口 |
| `foreign_tid` | 拒绝 `foreign_tid` | 非 owner TID 记录 |
| `lost` | 拒绝 `lost_record` | `PERF_RECORD_LOST` |
| `lost_samples` | 拒绝 `lost_samples_record` | `PERF_RECORD_LOST_SAMPLES` |
| `zero_and_backwards_time` | 拒绝 `nonincreasing_time`+`zero_length_span` | 零长 span、时间回退 |
| `double_out` | 拒绝 `unpaired_out`+`unpaired_in` | 连续两个 out（第二个无配对），随后 in 又多于 out |
| `trailing_out` | 拒绝 `unpaired_out` | 末尾只有 out，无配对 in |
| `truncated` | 拒绝 `truncated_record` | 头部声明 32 字节但只剩 24 |
| `unknown_record_type` | 拒绝 `unknown_record_type` | `PERF_RECORD_SWITCH_CPU_WIDE` 等不接受的类型 |
| `malformed_record_size` | 拒绝 `malformed_record_size` | 声明 size=24，非精确 32 |
| `illegal_preempt_on_in` | 拒绝 `illegal_preempt_on_in` | 无打开 out 时出现 in |
| `raw_length_mismatch` | 拒绝 `raw_length_mismatch`，`checksum_ok=false` | record 本身可解，元数据字节数不符 |
| `false_complete_flag` | 拒绝 `collector_incomplete` | `collector_complete=false` |
| `collector_errors` | 拒绝 `collector_errors`+`collector_incomplete` | `collector_errors` 非空 |
| `other_boot_windows` | 拒绝 `windows_boot_mismatch` | 窗口文件对不同 boot |
| `bool_as_int` | 拒绝 `captured_bytes_not_int`+`owner_tid_not_int`+`foreign_tid`，`checksum_ok=false` | Python `bool` 冒充整数 |

violation 码集合：`truncated_header`、`truncated_record`、`malformed_record_size`、`unknown_record_type`、
`lost_record`、`lost_samples_record`、`foreign_tid`、`nonpositive_time`、`nonincreasing_time`、
`zero_length_span`、`unpaired_out`、`illegal_preempt_on_in`、`raw_length_mismatch`、
`captured_bytes_not_int`、`owner_tid_not_int`、`reader_policy_not_int0`、`collector_incomplete`、
`collector_errors`、`lifecycle_<field>`、`windows_boot_mismatch`、`windows_owner_mismatch`、
`windows_clock_mismatch`、`windows_reversed`。

合同同步（本版）：`reader_policy` 现明确必须为 **Linux plain int `0`（SCHED_OTHER）**；所有 synthetic
metadata 已从字符串 `"SCHED_OTHER"` 改为 `0`，独立 `evaluate()` 同步新增
`reader_policy_not_int0` 类型/取值检查（字符串或其他取值一律拒绝）。

## 范围与不得主张的边界

本版夹具**只验证现有 binary / metadata / windows 规则**：record 精确 32 字节解码、类型与 misc 合法性、
owner 身份、时间单调性与正值、out/in 配对、原始长度一致、完整性/采集错误标志、生命周期布尔、
窗口与 capture 的 boot/owner/clock 绑定与整数交集。

**本版夹具不能证明"没有末尾 pending loss"**：`stop` 完整性哨兵合同（采集结束前最后一段 ring 是否仍可能有
未发布的 pending 记录）**仍在审查中**，尚无冻结的哨兵语义可钉。因此本目录不构造、也不声称任何
"尾部无丢失"夹具；`collector_complete=true` 只代表元数据标志本身，不是尾部完整性的证明。
同样，本目录不主张：调度延迟/CPU 归因、谁真正运行、历史飞行缺失数据的补齐。
这些判断属于消费方与合同审查，不属于夹具。
