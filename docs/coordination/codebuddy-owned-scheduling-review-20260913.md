# 独立审查：owned-scheduling 只读快照 — 2026-09-13

独立审查，非实现方（作者 390d430a 正在修）。只读源码 + 纯 fixture 小测试 + 真实 /proc 只读字段核对；未跑 native/模型/ROS/构建、未改实现、无嵌套、未用 Git。
**结论：CRLF/schedstats=0/kernel_prio-vs-RT/身份变化丢弃 四项均已修复并有测试；另发现 2 项低危边界问题。**

## 1. 版本（实际读到字节）

| 文件 | SHA256 | size |
|---|---|---|
| tools/capture_owned_scheduling.py | `a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e` | 20901 |
| validation/test_owned_scheduling.py | `a0e747d3c6fa93f4f68cb08591d8d83708164b8fef261136b042abc908e71319` | 22401 |

## 2. 已修复项（逐条核验）

- **CRLF 原始字节 hash — 已修复。** `_parse_children` 先 `read_bytes()`，`hashlib.sha256(raw)`（`:327-331`）后才 `raw.decode`（`:333`）；`children.sha256` 取原始字节。测试 `test_crlf_children_file_hashes_raw_bytes` 断言 `sha256(raw) != sha256(raw.replace(b"\r\n",b"\n"))`。
- **schedstats=0 不是 0 — 已修复。** `_read_schedstat`（`:193-216`）仅在 `sched_schedstats=="1"` 时有效；否则 `runqueue_ns`/`timeslices`=null，`runqueue_counters_valid=False`，`runqueue_invalid_reason` 区分 `disabled`/`unreadable`，同时保留始终有效的 `run_ns`(sum_exec_runtime) 与 `raw`。测试 `test_schedstats_disabled_keeps_exec_and_nulls_runqueue`、`test_missing_host_knobs_are_null` 覆盖。
- **kernel_prio 与 RT priority 区分 — 已修复。** `/proc/<tid>/sched` 的 `prio` 改名 `kernel_prio`（`_read_sched` `:218-225`）；`rt_priority`/`policy` 取自 `stat` 字段 40/41（索引 37/38，`:72-73,290-298`）。测试 `test_kernel_prio_is_not_rt_priority`、`test_short_stat_leaves_rt_priority_and_policy_null` 覆盖，且断言 `"priority" not in sched`。
- **身份变化丢弃线程数据 — 已修复。** 线程 `stat` 前后重读，`(start_ticks,pgid)` 不一致即整行置 `unavailable` 且所有指标为 null、`missing=["thread_identity_changed"]`（`read_thread` `:266-278`）；进程级 `identity_before/after` 不一致则整进程 `unavailable` 并记 `thread_rows_discarded`（`:414-418`）。测试 `test_thread_identity_change_discards_untrusted_metrics`、`test_identity_change_after_read_discards_thread_rows` 覆盖。

## 3. 独立核验（非复述规范）

- **真实 stat 字段位置**：在 WSL 用真实 `/proc/self/stat` 解析比对（同一 `_split_stat` 切分方式）——`idx0`=state、`idx2`=pgrp 且 == `os.getpgid(0)`、`idx17`=num_threads 且 == `/proc/self/status Threads`、`idx19`=starttime 存在、`idx37`/`idx38` 存在、`len(after)=50`。与工具索引完全一致（state 0 / pgid 2 / utime 11 / stime 12 / priority 15 / nice 16 / num_threads 17 / starttime 19 / rt_priority 37 / policy 38）。
- **PID/PGID/start_ticks 前后比较**：`_identity_problem`（`:379-389`）比较 pid+pgid+start_ticks 并额外判定 Z/X 退出；线程级比较 start_ticks+pgid。
- **普通 CPU 计数/线程数增长不误判复用**：身份比较只含 pid/pgid/start_ticks，不含 utime/stime/num_threads/comm。测试 `test_counter_growth_is_not_pid_reuse` 直接增长 `num_threads` 与 `comm`，仍判 `captured`。
- **缺字段/禁用指标 null**：缺失指标为 `None` 且入 `missing`，从不写 0（`_read_*` 与 `read_thread` 全程无 0 默认）。测试 `test_missing_fields_are_null_never_zero` 断言 `schedstat != 0`。
- **输出 exclusive 不覆盖**：`self.output.open("x", ...)`（`:462`）。测试 `test_output_is_exclusive_and_never_overwrites` 断言第二次 `FileExistsError` 且首次字节不变。
- **无调度/affinity/kill/进程 spawn**：全文件 grep 无 `subprocess`/`os.sched*`/`setpriority`/`os.nice`/`affinity`/`os.kill`/`signal`/`Popen`/`fork`/`exec`（仅 docstring 提及）。工具不集成 runner、不后台轮询、无性能裁决（`performance_verdict="not_evaluated"` `:458`）。

## 4. 低危边界问题

- **M1 — rt_priority/policy 的长度门 off-by-one。** `:290` 用单一 `if len(after) > STAT_POLICY_INDEX:`（即 `len>38`）同时门控 `rt_priority`(索引37) 与 `policy`(索引38)。若某行恰好 38 个字段（含索引 37 而无 38），`rt_priority` 会被误报为缺失。真实 `/proc` 为 50 字段，不可达；建议改为按字段独立判定（`len > STAT_RT_PRIORITY_INDEX` / `len > STAT_POLICY_INDEX`）。
- **M2 — 输出目标为已存在目录时的异常类型未覆盖。** `open("x")` 对已存在目录抛 `IsADirectoryError`（非 `FileExistsError`），测试 `test_output_is_exclusive_and_never_overwrites` 只覆盖已存在文件。行为仍为拒绝且不覆盖，仅异常类型与测试面差一档。

其余无新问题；`_split_stat` 用 `index("(")`+`rindex(")")`，对 comm 含括号/空格亦正确。

## 5. 测试证据

`python -m pytest validation/test_owned_scheduling.py -q`（Windows，纯 fixture，注入 `proc_root` 与假时钟）→ **31 passed**。覆盖：正常捕获、进程消失、PID 复用、越界身份拒绝、非法 proc 路径、CRLF、缺字段 null、缺 host knob、schedstats 禁用、kernel_prio vs RT、短 stat、exclusive 输出、进程/线程身份变化丢弃、线程 churn、CPU 计数增长。非 native 证据，不得据此下性能结论。

## 6. 交接

- 本报告仅覆盖第 1 节两个 SHA 的字节。
- 接续项：early probe 修订审查（R1 `Region` 缺 `end_tick`/epoch、R2 `diagnostic_errors` 无上限）需在其实现者文件稳定后按其新 SHA 复验。
