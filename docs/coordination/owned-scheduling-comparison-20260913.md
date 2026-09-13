# Owned-process 调度快照对比 — 2026-09-13

只读对比工具，接在已冻结的 `tools/capture_owned_scheduling.py` 之后，比较同一 run 的
两份快照（计时前/后）。不改 capture 模块、不启动/停止任何进程、不改调度、不接 runner、
不后台、无嵌套/Git。新增文件：

- `tools/compare_owned_scheduling.py`
- `validation/test_compare_owned_scheduling.py`
- 本文件

## 1. CLI

```bash
python3 -B tools/compare_owned_scheduling.py \
  --before <RUN>/owned-scheduling-before.json \
  --after  <RUN>/owned-scheduling-after.json \
  --output <RUN>/owned-scheduling-delta.json
```

输出 `open("x")` 独占创建；已存在则 `FileExistsError`，不覆盖、不删除。输入只读。
退出码：bound = 0，unbound = 1（报告仍写出）。

## 2. 先绑定，再比较

以下任一不成立即 `binding.status="unbound"`（`reasons` 列出），`roles` 置空、不产出
任何 delta，只写绑定报告。缺证（缺失/类型错）一律不接受，绝不由“两边都缺”推导相等：

- 两份 `children.sha256` 均为 64 位十六进制字符串且相同：非法/缺失 →
  `children_sha256_unavailable`，均为合法 hex 但不同 → `children_sha256_mismatch`；
- 两份 `host.boot_id` 均为非空字符串且相同：否则 `boot_id_unavailable`；
  均为有效字符串但不同 → `boot_id_mismatch`；**PID 复用绝不跨 boot 拼接**；
- `after.captured.monotonic_ns` 严格大于 before，且两份都是非负 plain int（bool/
  浮点/字符串/负值/缺失 → `monotonic_unavailable`；不递增 → `monotonic_not_increasing`）；
- 每个 role 的 `expected` 为对象且 `pid`/`pgid`/`start_ticks` 均为合法 plain int：
  任一缺失或类型错 → 该 role `identity_unavailable`（**不做等价比较**）；均为合法
  int 但不同 → `identity_mismatch`。

## 3. 逐线程 delta 规则（不填 0、不 clamp）

只对**两份都 `status=="captured"` 且 `tid`/`start_ticks` 相同**的线程出 delta：

```
delta = {utime_ticks, stime_ticks,            # stat（CPU 运行，ticks）
         run_ns,                              # schedstat sum_exec_runtime（始终有效）
         runqueue_ns, timeslices,             # 仅两侧 sched_schedstats=1 才有效
         voluntary_ctxt_switches, nonvoluntary_ctxt_switches}   # proc_status
delta_unavailable = {metric: 原因字符串}      # 缺失/禁用/负值
negative_counters = [metric, ...]
```

- 线程匹配要求两份都有合法 plain-int `tid`（`≥1`）与 `start_ticks`（`≥0`）：`tid`
  非法 → `thread_tid_invalid_before/after`；任一侧 `start_ticks` 缺失/类型错 →
  `thread_identity_unavailable`（**不把两个缺失当同一线程**）。
- 线程消失 / 新增 / 身份不稳 / 任一侧 `unavailable`：该线程 `status="unavailable"` +
  `unavailable_reason`（`thread_vanished_after`、`thread_added_after`、
  `thread_reuse_not_stitched`、`thread_unavailable_before/after`），**没有 delta 字段**。
- 任一侧进程 `partial`：role `status="partial"`，只比较两侧都可用的线程，其余照上。
- runqueue/timeslices 需要**两侧 host `sched_schedstats=="1"` 且两侧行 flag 为真**；
  只信行 flag 不够。host 为 0/缺失但行 flag 仍为 True 的矛盾输入按不可用处理：值置
  `null`、原因含 `host_sched_schedstats_not_enabled(...)`（必要时并上
  `runqueue_counters_invalid(...)`）；**CPU run（`run_ns`）差值照常保留**，不得当 0。
- 负 counter 差（计数器回退/重置）：值置 `null`、记入 `negative_counters`、原因
  `negative_counter_delta`，**绝不 clamp 成 0**。
- 两侧读数都存在且相同时 delta 为真实 `0`（例如无新增 CPU/切换），与“缺失”区分。

## 4. 优先级/policy/affinity 变化

每个比较线程附 `transitions`：`state`、`priority`、`nice`、`rt_priority`、`policy`、
`kernel_prio`、`cpus_allowed_list`，各含 `before`/`after`/`changed`。其中：

- 与 runner 的 FIFO/RT 优先级比较用 **`rt_priority`（stat 字段 40）** 与 `policy`
  （stat 字段 41；`/proc` policy 为不含 `SCHED_RESET_ON_FORK` 的基础值）。
- `kernel_prio`（`/proc/<tid>/sched` 的 `prio`）是内核内部优先级（CFS `120+nice`、
  RT `99-rt_priority`），**不是 RT 优先级**，只作变化记录，附 `note`。

## 5. 报告边界

输出含 `performance_verdict="not_evaluated"` 与 `attribution="not_evaluated"`；两次采样点
的总差值**不归因于任何单个事件**（例如某次 15 ms 尖峰）。工具只给绑定事实与逐线程
差值，解释由主会话结合其它证据完成。

## 6. 测试与证据界限

`validation/test_compare_owned_scheduling.py` 用真实 capture 工具对临时 `/proc` 形状
fixture 生成两份真实 schema 快照（复用 capture 的测试 fixture，未修改），覆盖：手算
delta、children SHA 不一致、boot_id 变化/不可读、monotonic、线程复用不拼接、
schedstats 禁用置 null、负差不变 0、线程增删、partial、进程消失、独占输出与输入不被
改动、非法 schema 拒绝，以及在真实 capture 形状上做字段删除/类型错误/矛盾 flag：
非 64hex 的 children SHA、空/非串 boot_id、负/bool/串/浮点/缺失 monotonic、两份
`expected` 缺失不被当一致、`tid`/`start_ticks` 缺失或类型错不被当同线程、host
`sched_schedstats=0`/缺失但行 flag 为 True 时 runqueue 置 null 而 CPU run 保留。
这些是**纯逻辑测试，不是 native 证据**：没有真实进程被采样。native 证据只来自对活动
run 用第 1 节 CLI 的真实对比。
# 主会话收口补记

2026-09-13：独立审查后补上畸形stat/schedstat计数保护：bool、字符串、浮点、负原始计数不参与相减，记null与invalid_counter_value；runqueue有效标志仅接受True。身份与有效自产数据的差值计算不变。主会话定向比较器与烟测安全测试共88passed/1skip；Linux烟测安全测试16passed，包含真实符号链接拒绝。当前比较器SHA13a61a7ffd92880571613c69d3d31736f1982e75ff03b365e2602338c928ec6f；历史真实烟测绑定的033d8af8原字节保存于validation/coordination/owned-scheduling-e2e-20260913/source-compare-v1.py，不改旧证据pin。以下记录保留其历史版本语境。
