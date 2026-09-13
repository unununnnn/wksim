# 独立复核：manager 目标 FIFO 50 → 99 候选（2026-09-13）

复核目录：`validation/coordination/ds-manager99-review-20260913-01`（唯一写入目录）。
只读作者候选与冻结基线；**假 os 账本**执行；**未执行任何真实调度**；无新框架/模型/ROS/编译；未改动作者文件或 `tools/run_joint_flight.py`。

被审对象（只读）：

| 对象 | sha256 / 说明 |
| --- | --- |
| `ds-manager99-candidate-20260913-01/candidate.py.txt` | `9b97c124cc75c582aabaf72db2051f96f2b4777855f39645f5a75fb2d2d1e839`（98 579 B，1 564 行） |
| `candidate.json` / `candidate.diff` | `1c45ca1d0f3d35c1cbaacb66e2f9e5c0b9eeefb1f8a49eb054c7b02538201661` / `668475ec8d68e884253537e5ca7190448bbe82945c59b37ce44a32e5c15b5c7a` |
| `build_candidate.py` | `76e7594965625e9ec0aab2e5a2cf758913457346a2a0df217f8d0b33c14f8c75` |
| 冻结基线 v3 快照 | `1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373` |

候选已到场（未轮询等待）。判定基于**独立测量**，不采用候选自述。

## 结论

| 复核项 | 结果 |
| --- | --- |
| 只变 manager 目标 | **成立**：全文件仅 1 处语义改动，即 `scheduling()` 内 manager 分支的 FIFO 目标值 50 → 99 |
| model / FC 设置 | **未变**：仍为 40，实测账本逐调用一致 |
| nice | **未变**：manager/model/fc = −10，其余 = −5，逐角色一致 |
| RESET_ON_FORK | **未变**：`role in ('manager','model') and async_model_evidence`，策略位实测一致 |
| 时钟/回调/阈值/命令 | **未变**：改动仅落在 `scheduling()` 的一个赋值语句，其余 1 500+ 行逐字节相同 |
| 仅正确 PID 被调度 | **成立**：所有系统调用只带调用方自己的 `pid`，无第二个 PID |
| EPERM 等失败原样 | **成立**：`nice_error` / `scheduler_error` 以 `repr(error)` 原样记录，不吞、不重排、不转成功 |

**未发现需要阻塞候选的代码缺陷。** 但发现 3 项与候选自述/证据边界有关的问题（F2、F3、F4），其中 F2 是**注释与事实不符**，建议改字。

## 1. 源码级独立比对

`difflib` 独立重算，与作者 `candidate.diff` 逐行一致（`test_declared_diff_is_reproducible_from_the_two_sources`）：

- 被改动的快照行只有 **2 行**：189（赋值）与 192（注释里写着 `FIFO/50`）；
- 新增行 4 条均为注释，唯一非注释新增行是
  `value['target_fifo_priority'] = 99 if role=='manager' else 40`；
- `scheduling()` 内 `target_fifo_priority` 赋值：基线恰为 `50 … else 40`，候选恰为 `99 … else 40`；
- 基线快照仍匹配钉住哈希 `1c600d7f…`（1 560 行），候选 1 564 行 —— 行数差 4 = 新增注释行；
- 候选与基线除该 hunk 外逐行相等（`removed_line_numbers == [189, 192]`）。

`candidate.json` 中 `candidate_sha256/snapshot.sha256/diff_sha256/change.old/new_expression/edited_snapshot_lines/roles_*` 与我的实测值全部一致（仅字段命名与 `build_candidate.py` 源码里的变量名不同，内容无冲突）。

## 2. 假 os 账本：调用面与差异

把候选的 `scheduling()` 原文 `exec` 进一个只记账、不触内核的 `FakeOS`（`setpriority/getpriority/sched_setscheduler/sched_getscheduler/sched_getparam` + 常量），逐角色 × `async_model_evidence∈{False,True}` 对比基线与候选账本：

- `manager`：账本差异**恰好 1 处**，即 `sched_setscheduler(pid, SCHED_FIFO, 50)` → `(pid, SCHED_FIFO, 99)`；其余调用（`setpriority`/`getpriority`/`sched_getscheduler`/`sched_getparam`）参数完全相同；
- `model`、`fc`、`task`、`agent`、`service`：账本与返回值**逐项完全相同**（含 model/fc 的 FIFO 40）；
- 调用序列 `setpriority → getpriority → sched_setscheduler → sched_getscheduler → sched_getparam` 在成功路径上与基线一致；
- 结果字典键集合随分支精确变化：非 FIFO 角色无 `target_fifo_priority`/`actual_*`；`reset_on_fork` 键仅在 `role∈{manager,model} and async_model_evidence` 时出现。

## 3. 仅正确 PID 被调度（只读核验）

- `pid∈{1, 4242, 99999}` × 全角色：账本的每一次调用参数里都含有该 `pid`，且**从不出现**另一个 PID（`4243` 永不出现）；
- `setpriority`/`getpriority` 的第一参数恒为 `os.PRIO_PROCESS`（per-process，非 per-thread、非 per-group）；
- AST 核验：`scheduling()` 内所有属性访问都以注入的 `os` 对象为宿主，`os.*` 属性集合恰为 `{setpriority, getpriority, PRIO_PROCESS, SCHED_FIFO, SCHED_RESET_ON_FORK, sched_setscheduler, sched_getscheduler, sched_getparam, sched_param}`，唯一非 `os` 属性是 `…sched_getparam(pid).sched_priority`；函数体内**无** `Popen`/`fork(`/`spawn`/`system(`（注释中的 "Popen" 不参与）。

## 4. EPERM 等失败原样记录

| 场景 | 实测 |
| --- | --- |
| nice 被拒 `EPERM` | `nice_error="PermissionError(1, 'Operation not permitted')"`；`actual_nice` 缺失；**FIFO 请求仍执行**；`getpriority` 与 `setpriority` 同处一个 `try`，故一并跳过——与源码一致 |
| scheduler 被拒 `EPERM` | `scheduler_error` 原样记录；`actual_policy`/`actual_priority` 缺失；`actual_nice` 仍为 −10（nice 已生效）；`sched_getscheduler` 未被调用 |
| 两者同时失败 | `nice_error` 与 `scheduler_error` 各自独立记录，无覆盖 |
| 回读被拒 | `sched_getscheduler` 成功后 `sched_getparam` 抛错 → `scheduler_error` 记录、`actual_priority` 缺失、`actual_policy` 保留 |
| 失败时键集合 | `{target_nice, actual_nice, target_fifo_priority, scheduler_error}`，无任何"成功"字段被伪造 |

成功路径的 `actual_policy`/`actual_priority` 来自内核回读（账本状态），**不是**目标值的回显。

## 5. 已捕获策略与边界分析（只读真实快照）

数据源：成功捕获 `last-callbacks-run-20260913-01/flight/`（`before` 228 813 B / `after` 331 637 B，`validated: true`，boot `2e7caa0c…`）。该运行结果 `status=failed`，且 `source_sha256['tools/run_joint_flight.py'] = 1c600d7f…`（即冻结基线，未用候选）。捕获到的实际策略：

- **manager**（pid 812，`python3`）leader：`SCHED_FIFO` / `rt_priority=50` / `nice=-10`，**before 与 after 完全相同**；同进程另 30 个线程为 `SCHED_OTHER`。
- model / fc：`SCHED_FIFO` / 40（未变项在真实数据中亦如此）。
- 该主机观测到的实时优先级集合：`{50, 55, 74, 90, 98, 99}`，最高 99。

**F2（注释与事实不符，建议改字）** 候选注释写 "raise the manager target to FIFO/99, **just below** the 99-priority work-queue/hrtimer service threads observed on this host"。但 99 就是观测到的最高值：manager 若设 99，是与那些线程**同级（平级）**，不是"低于"。证据中处于该级的线程共 16 个，全部位于 `px4-fc`（pid 2083）：

```
wkr_hrt, wq:manager, wq:lp_default, sim_rcv, sim_send, wq:hp_default, wq:rate_ctrl,
wq:INS0, wq:INS1, wq:INS2   (rt=99)          hpwork   (rt=98)
```

**F3（边界，非缺陷）** 同为 FIFO/99 时不存在优先级抢占差：同优先级 SCHED_FIFO 线程只能按 FIFO 次序轮流，**不会互相抢占**。因此把 manager 提到 99 的收益只能来自"越过 50→98 这一段被抢占的区间"，对 99/98 线程本身没有优先级优势（也不会被它们抢占）。此外证据只给出优先级与 `comm`，**没有 CPU 亲和性/占用时长**，无法从快照推断是否与这些线程争用同一核。

**F4（证据边界）** 该捕获是**单次运行、单主机、单 boot**（`uptime 91.6 s`，`sched_rt_runtime_us=950000`，`sched_schedstats=0`）。98/99 线程存在于系统（wrapper 级）进程 `px4-fc` 中，并非 runner 自身线程；快照是只读观测，不能作为"改到 99 会更快"的证据。

**明确不主张**：候选带来的任何性能/时延收益、R1/formal 通过、以及"99 更优"的结论。候选自述的 `not_done` 与此一致。

## 6. 残余与建议

- **R1**：`scheduling()` 有 3 个出口（nice 失败、FIFO 失败、成功），但没有任何一处校验"实际生效值"，manager=99 是否真的落地只能靠 `actual_priority` 回读；建议后续运行时把 `actual_policy/actual_priority` 与目标值一起断言记录（不改代码也可在结果里核对）。
- **R2**：`nice` 与 `sched` 两段失败**互不阻断**——nice 被拒时仍会升 FIFO，反之亦然。这是基线既有语义（本次未改），但 99 场景下值得在报告中显式说明。
- **R3**：`candidate.json` 的 `change.diff_is_authoritative` 已声明 opcode 仅作指示；实测 opcode 与 `candidate.diff` 一致，无冲突。
- **F2 改字建议**：把 "just below the 99-priority … service threads" 改为 "level with the observed 99-priority threads（`wkr_hrt`、`wq:*`、`sim_rcv/sim_send`，位于 px4-fc）"，并删去未经证据支持的 "work-queue/hrtimer" 因果表述。

## 7. 未做 / 边界

未执行任何真实调度（无 `sched_setscheduler`/`setpriority` 真实调用）；未启动 runner、未跑模型/ROS；未使用或改动 `tools/run_joint_flight.py`、helper、运行时；未把源码或快照当作性能收益。假账本只建模上述五个调用与三种 OSError 场景，不建模内核带宽限流、CPU 亲和性与套接字层。

## 8. 复现

```
python -B validation/coordination/ds-manager99-review-20260913-01/test_manager99_candidate.py
python -B validation/coordination/ds-manager99-review-20260913-01/run_manager99_review.py
```

第一条：27 tests，`OK`（含 3 项"本复核未触真实调度"的自证）。第二条：生成 `evidence/manager99-review.json`（源码比对、账本差异、失败透传、捕获策略边界）。哈希见 `sha-receipt-20260913-10.json`。
