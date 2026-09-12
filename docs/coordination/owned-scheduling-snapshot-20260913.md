# Owned-process 调度快照 — 2026-09-13（收口修订）

独立只读诊断工具，用于在计时前/后采集主会话自己启动的 children，避免把计时差异
凭空归因到 WSL boot 或线程调度。工具不启动 native、不改优先级/亲和性/内核、不发
信号、不接 runner、不后台轮询、不产出性能结论。文件：

- `tools/capture_owned_scheduling.py`
- `validation/test_owned_scheduling.py`
- 本文件

## 1. 用途与边界

- 输入是已有 `children-start.json` 形状（顶层 role → `identity{pid,pgid,start_ticks,argv}`）。
  只采集 **pid ∧ pgid ∧ start_ticks 精确匹配** 的进程；不匹配、PID 复用、已消失
  一律记为 `unavailable` 并写明原因，绝不写成 0，也不给 pass。
- `children.sha256` 对文件**原始字节**计算后再 decode 解析；CRLF 文件不会被统一成
  LF 后哈希。
- 进程在读取前后各复核身份；两次之间身份变化的进程，线程行全部丢弃并整进程
  `unavailable`。
- 线程 `stat` 在其它读取前后各读一次。**同一线程身份（start_ticks/pgid）变化时，
  该线程先读到的 stat/schedstat/sched/proc_status 全部置 null**，线程标
  `unavailable`（理由 `thread_identity_changed`），进程标 `partial`；不稳定行绝不
  以 captured 或 0 形式出现。
- 逐线程采集：`stat`（含 `rt_priority`/`policy`）、`schedstat`、`sched`、
  `proc_status`（原 `/proc/<tid>/status`）。
- 全局只读值：`boot_id`、`uptime`、`CLK_TCK`、`sched_rt_runtime_us`、
  `sched_rt_period_us`、`sched_schedstats`，以及采样时刻。
- 读不到的字段 = `null` + `missing` 列表项，**不是 0**。输出含
  `"performance_verdict": "not_evaluated"`。
- 输出是单个新 JSON 文件，`open("x")` 独占创建；已存在则 `FileExistsError`，不覆盖、
  不删除。

## 2. 主会话可直接执行的两次命令

在 WSL 的 `wksim` 根目录执行（`<RUN>` 为该场 run 目录）：

```bash
# 计时开始前
python3 -B tools/capture_owned_scheduling.py \
  --children <RUN>/children-start.json \
  --output <RUN>/owned-scheduling-before.json --phase before

# 计时结束后（children-start.json 用同一份，identity 不变）
python3 -B tools/capture_owned_scheduling.py \
  --children <RUN>/children-start.json \
  --output <RUN>/owned-scheduling-after.json --phase after
```

两次用同一份 `--children`；输出互不覆盖；同一 phase 重复写同一路径被拒绝，需换新
路径。命令是**一次性**的，不含循环。

## 3. 输出结构（关键字段）

```
schema = wksim.owned-scheduling-snapshot.v1
phase, scope, children{path,sha256(raw bytes),roles}, output,
captured{wall_utc,monotonic_ns,boottime_ns}
host{boot_id, uptime_seconds, clock_ticks_per_second,
     sched_rt_runtime_us, sched_rt_period_us, sched_schedstats}
procs.<role> = status(captured|partial|unavailable), expected{pid,pgid,start_ticks},
               identity_before/after, thread_count, threads_captured,
               threads_unavailable, partial_reason?, threads[]
               （进程身份失败：unavailable_reason, threads=[], thread_rows_discarded）
threads[] = tid, status(captured|unavailable), unavailable_reason,
            start_ticks, comm, read_consistent,
            stat{state,pgid,priority,nice,rt_priority,policy,utime_ticks,stime_ticks} | null,
            schedstat{run_ns,runqueue_ns,timeslices,raw{...},
                      runqueue_counters_valid,runqueue_invalid_reason} | null,
            sched{kernel_prio} | null,
            proc_status{cpus_allowed_list,voluntary_ctxt_switches,
                        nonvoluntary_ctxt_switches} | null,
            missing[]
summary{requested,captured,partial,unavailable}, performance_verdict="not_evaluated",
sampler_sha256
```

进程 `unavailable_reason`：`vanished_*`、`exited_*`、`identity_mismatch_before_read`、
`thread_inventory_unreadable`、`identity_mismatch_after_read`。
线程 `unavailable_reason`：`thread_stat_unreadable`、`thread_identity_changed`。

## 4. 优先级与 runqueue 的正确读法（关键，勿误用）

- `stat.rt_priority`（stat 第 40 字段，索引 37）与 `stat.policy`（第 41 字段，索引
  38）来自 `stat`，是线程真实的 `sched_getparam`/`sched_getscheduler` 值；stat 行过短
  则为 `null` + `missing`，不是 0。
- `sched.kernel_prio`（原 `/proc/<tid>/sched` 的 `prio`）是**内核内部优先级**
  `task->prio`：CFS 为 `120 + nice`，RT 为 `99 - rt_priority`。**它不是 FIFO/RR 的
  调度优先级，不能拿它当 RT priority。**
- 与 runner 实际 FIFO 优先级比较：runner 记录的 `scheduling.actual_priority`（例如
  FIFO 40）应对齐 **`stat.rt_priority`**（应为 40）与 **`stat.policy`**（SCHED_FIFO
  = 1；注意 `/proc` 的 policy 是不含 `SCHED_RESET_ON_FORK` 的基础值，runner 的
  `1073741825` = `0x40000000|1`）。FIFO 40 的 `kernel_prio` 恰为 59，**不得把 59
  读成 FIFO 59，也不得把 kernel_prio 与 runner 的 49/40 直接等号比较**。
- `schedstat`：`run_ns`（sum_exec_runtime）始终有效，保留。`runqueue_ns`/`timeslices`
  只有在 `sched_schedstats=1` 时才是当前有效指标；为 `0` 时有效值置 `null`，理由
  `sched_schedstats_disabled`（内核未统计），`raw` 仍保留读数供审计。读不到开关时理由
  `sched_schedstats_unreadable`。**不得用 0 证明“无 runqueue 等待”。**
- `runqueue_ns` 只是 runnable-but-waiting，不等于全部 off-CPU。

## 5. 前后对照怎么用（工具不判）

- 先按 role 对齐 `procs`，只比较两次都 `status=="captured"`（且线程
  `status=="captured"`）的样本；任一侧 `unavailable`/`partial` 的线程不用于性能归因。
- 两次之间的 `policy`/`rt_priority`/`nice`/`Cpus_allowed_list`/runqueue 变化是事实
  记录，解释由主会话结合其它证据决定；工具不生成 pass/fail。

## 6. 成本与局限

- 单次成本随线程数增长：每线程约 4 次小文件读（stat×2、schedstat、sched、status），
  进程级另有 stat×2；一次性、短时、不驻留、不后台。
- 竞争窗口：线程读取中途退出 → 该线程 `unavailable`（`thread_stat_unreadable`），
  进程 `partial`；进程两次身份核对之间退出 → 整进程 `unavailable`。均为显式标注。
- 临时线程增删或普通 CPU 计数/`num_threads` 变化**不是** PID 复用：只有
  pid/pgid/start_ticks 变化才拒。
- `/proc/<tid>/sched` 依赖 `CONFIG_SCHED_DEBUG`；不可用时 `sched` 为 `null`，但
  `stat.rt_priority`/`stat.policy` 仍可记录。
- 只读：路径安全校验拒绝非整数/越界/含分隔符的 pid/pgid/tid；不写任何内核开关。

## 7. mock 与 native 的界限

`validation/test_owned_scheduling.py` 用临时 `/proc` 形状目录 + 注入时钟与 mock 读，
覆盖：正常记录、消失、PID 复用、越界身份拒绝、越界路径拒绝、CRLF 原始字节哈希、
缺字段（null 非 0）、`sched_schedstats=0`/不可读时 runqueue 置 null、`kernel_prio`
与 `rt_priority` 区分、stat 过短、线程身份变化丢弃指标、线程增删/计数增长不算复用、
独占输出不覆盖。这些是**纯逻辑测试，不是 native 证据**：没有真实进程被采样，绝不能
用它们证明性能或调度行为。native 证据只来自第 2 节命令对活动 run 的真实采集。
