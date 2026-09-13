# omp-perf-stream-review-20260913-01：perf 流记录完整性边界审查（合同级，更正版）

对象：`docs/coordination/perf-stream-contract-20260913.md`（D 实现尚未到场，仅审合同，不轮询）。主要证据：torvalds/linux v6.6 `kernel/events/ring_buffer.c`、`core.c`、`include/linux/perf_event.h` 实源行号。**更正**：旧版"哨兵闭合"结论撤回——`sched_yield` 不保证真实切换；完整性结论由"非阻断"改为**阻断**。

## 三个焦点问题

### 1. 近满保守 guard 不能识别"最终尚未 emit 的 LOST"（实证，维持）

v6.6 `ring_buffer.c::__perf_output_begin`：空间不足走 `fail:`（256–262 行）仅 `local_inc(&rb->lost)` 后 `-ENOSPC`，**head 不前进**（cmpxchg 在其后），ring 无字节痕迹；LOST 记录只在**下一次成功** output 时补发（`have_lost` 185–187 行，`local_xchg(&rb->lost, 0)` 248 行清零，243–253 行写记录）；DISABLE 不冲刷（`perf_pending_irq` core.c:6732 起仅 wakeup）；rb->lost 用户态不可见。故"末尾丢弃+其后无成功 output"对用户态不可检。

### 2. head/tail 内存序——合同正确

`perf_event.h` 661–675 与 `ring_buffer.c` 204–217（"userspace SHOULD issue full memory barrier after reading the data and before storing the new tail"）与合同的 acquire-head/校验/copy/有序-tail 逐点对应。✓

### 3. 停止顺序——合同正确

disable → final drain → join → 用存储/unmap（合同 28–31 行）。disable 无 output 副作用，顺序调换无补漏效果。✓

## 候选协议（送审形态）：drain-first 哨兵

原计时段关闭后、owner stop 内：

1. 先等 reader drain 并确认 ring 足够空余（近满 guard 早于哨兵，而非止于收尾）；
2. **仍 enabled** 时记录 `sentinel_before_ns`（CLOCK_MONOTONIC）；
3. 有界 nanosleep；
4. 记录 `sentinel_after_ns`；
5. 随后 disable + final drain + join。

离线验收：**在 [sentinel_before_ns, sentinel_after_ns] 内必须看到真实的本线程 out/in 对**——没有即失败（不假定 nanosleep 必然产生记录）；**任何位置**出现 LOST/LOST_SAMPLES 即拒；**可验证窗口只能 end ≤ sentinel_before_ns**——哨兵之后至 disable 的未观测尾段不作任何"无损"宣称，前窗口之外同样不宣称。

### v6.6 单 producer 语义是否足以让哨兵 output 带出既有 rb->lost

**足够（限于本 ring）**：self-thread 单事件单 rb；`__perf_output_begin` 每次成功路径先查 `have_lost`（185 行）并随本次 output 预置 LOST 记录（243–253 行，`local_xchg` 清零）。因此只要哨兵记录本身成功落 ring，此前的丢失必然先以 LOST 记录出现在哨兵之前——离线顺序可判。

### 仍然存在的缺口（写明，不闭合）

- 哨兵 output 本身在空间不足时同样被丢（head 不动、lost 再增）——此时离线看不到哨兵对 → 按协议失败。该情形自闭合为拒绝，非缺口。
- **真正缺口 A**：哨兵对落 ring 之后、disable 之前的新丢失不可见（无后续 output 带出）；协议以"窗口 end ≤ sentinel_before_ns"显式排除该尾段——这是声明范围的收缩，不是检测。
- **真正缺口 B**：步骤 1 的"足够空余"判定与哨兵 output 之间是竞态（producer 持续）；guard 只能降低概率。哨兵对缺席时无法区分"未发生切换"与"记录被丢"——两者都失败处理，无歧义输出。
- nanosleep 的 EINTR 早醒须重启剩余间隔（D v2 探针已有此形态），但最终以"界内见到真实 out/in 对"为准，不以 sleep 语义为准。

## main 可采用的精确元数据与验收条件

metadata 增补字段：`sentinel_before_ns`、`sentinel_after_ns`（CLOCK_MONOTONIC）、`drain_confirmed_free_bytes`、`sentinel_pair_observed`（bool）、`lost_records`、`lost_samples_records`、`verifiable_window_end_ns`（== sentinel_before_ns）。

验收（离线）：① `sentinel_pair_observed == true` 且该对 timestamps ∈ [before, after]；② `lost_records == 0 and lost_samples_records == 0`；③ 一切窗口交集/结论只用 `end_ns ≤ verifiable_window_end_ns` 的数据；④ head/tail 单调、无 CPU_WIDE/未知/截断记录；⑤ lifecycle 四布尔全真。任一不满足 → capture invalid。

## 结论

**完整性仍阻断**：§1 不可检情形经源码确认；哨兵协议把"不可检"收缩为"哨兵后的尾段不宣称"，并以界内对+LOST 显式失败作为可测拒绝条件。满足上述元数据与验收后，仅协议覆盖范围内可降为条件性非阻断。内存序与停止顺序两项维持原判正确。
