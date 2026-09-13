> Main integration, 2026-09-13: current acceptance is 84 consumer checks and 17 independent CLI fixtures, all passing. Earlier self-check counts did not prove the fixture ABI. See ../perf-stream-offline-acceptance-20260913-03/main-verdict.json. This is synthetic decoding acceptance; complete capture/flight acceptance remains unproven.

# ds-perf-stream-consumer-20260913-01：严格离线 switch 流 consumer

唯一写入本目录。Python 标准库实现，纯离线；未运行 native/编译/模型/ROS，未解析既有 rate 原件（窗口由后续主会话提供）。

## CLI

```text
python -B perf_stream_consumer.py --raw <raw.bin> --metadata <meta.json> \
        [--windows <windows.json>] --output <out.json>
```

- 退出码：`0` 成功；`3` 合同拒绝（stderr 输出 `{ok:false, reason, detail}`）；`4` IO 错误。
- **拒绝覆盖**：`--output` 已存在即 `output_exists_refusing_overwrite`（以 `x` 模式独占创建）。
- 成功时 stdout 输出一行 `{ok:true, output, pairs, records, windows, raw_sha256, metadata_sha256}`；输出文件含完整解码 pairs 与可选窗口相交、以及原文件 SHA。

## 窗口 JSON 格式（`--windows`，与 metadata 绑定）

```json
{
  "schema": "wksim.perf_windows.v1",
  "boot_id": "<同 metadata.boot_id>",
  "owner_pid": 0,
  "owner_tid": 0,
  "clock_id": "CLOCK_MONOTONIC",
  "windows": [{"id": "w1", "start_ns": 0, "end_ns": 0}]
}
```

绑定与校验：`boot_id`/`owner_pid`/`owner_tid`/`clock_id` 必须与 metadata 完全一致；`id` 非空且唯一；`0 <= start_ns < end_ns` 且整段落在 `[enable_after_ns, disable_before_ns]` 内；整数纳秒，布尔不算整数。

## 拒绝的合同异常（全部显式失败，不跳过）

metadata：schema/classification/full_acceptance、owner pid/tid（正整数、非布尔）、boot_id、clock_id、四个时钟界顺序、ring_bytes（2 的幂且 ≥40）、storage_capacity、`captured_bytes == 原文件长度`、reader_policy、config 六项精确匹配、`collector_complete=true`、`collector_errors=[]`、四个 lifecycle 布尔、缺字段。

字节流：长度必须是 32 的整数倍且非空；每条记录必须是 `PERF_RECORD_SWITCH`、`size==32`、misc 仅允许 `SWITCH_OUT|SWITCH_OUT_PREEMPT`；LOST / LOST_SAMPLES / CPU_WIDE / 未知类型一律拒绝；身份必须是 owner pid+ tid 且为正；时间严格递增且落在捕获界内；out/in 严格交替、无尾随 out、至少一对完整 pair；switch-in 带 preempt 拒绝。

窗口：schema/boot/owner/clock 绑定、列表非空、id 合法唯一、界为正整数且落在捕获界内。

## 输出内容

`pairs[]`：`sequence/out_index/in_index/out_time_ns/in_time_ns/duration_ns/out_cpu/in_cpu/out_preempt/cpu_changed`；
`windows[]`：每个窗口的 `window_duration_ns/intersecting_pairs/intersection_total_ns/intersections[{sequence,start_ns,end_ns,duration_ns}]`（整数纳秒相交）；
另有 `capture`（metadata 回显）、`decoded`（记录/pair 计数、首末时间、观测跨度、pair 时长合计与最大、CPU 集合、preempt 计数）、`inputs.*_sha256`。

`classification=diagnostic_only`、`full_acceptance=false`、`flight_conclusion=null`：本工具只给边界观测，**不生成任何真实飞行结论**。

## 纯 Python 合成测试

```text
python -B test_perf_stream_consumer.py
```

58 项检查、0 失败：2 项成功路径（无窗口 / 3 个窗口且相交时长逐一核对）、覆盖拒绝清单的 40+ 负例、以及"同一坏输入两次给出同一 reason"的确定性检查。全部夹具在本文件内合成，标注为 synthetic，不含飞行数据。

## SHA-256

见 `manifests.json`（含 `perf_stream_consumer.py`、`test_perf_stream_consumer.py` 自身）。
