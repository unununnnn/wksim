# 自有进程调度快照端到端烟测 — 2026-09-13

对冻结的 capture+compare 做一次最小真实自有进程端到端验证。仅涉及本验证器自身 pid
与它自建的 1 个普通 Python 子进程（spinner）；未启动/触碰 SITL、native 模型、ROS
节点、飞控、UE、MATLAB，未构建，未改全局调度，未用 Git，未嵌套代理。产物仅在
`validation/coordination/owned-scheduling-e2e-20260913/` 与本文件。

## 1. 环境

- WSL `Ubuntu-22.04`，Python `3.10.12`，内核 `6.6.87.2-microsoft-standard-WSL2`。
- `boot_id = 5791bb33-c3b3-46b0-a393-8c5a01cfec42`，`sched_schedstats = 0`
  （故 runqueue/timeslice 在本内核不可有效测量）。
- 冻结源：capture `a3f3badd…`、compare `033d8af8…`（运行中未被修改）。

## 2. 复跑命令（Linux/WSL，约 1 秒）

复跑必须给一个**尚不存在**的新目录；此前的 `…-20260913/` 是**只读历史**，不再作为
输出目录。

```bash
cd "/mnt/c/Users/PC/Documents/odid编译/wksim"
timeout 10 python3 -B validation/coordination/owned-scheduling-e2e-20260913/run_e2e.py \
  --output-dir /mnt/c/Users/PC/Documents/odid编译/wksim/validation/coordination/owned-scheduling-e2e-<新后缀>
```

`run_e2e.py` 在进程内调用 capture（before/after）与 compare，主会话可见的只有
`verifier`（脚本自身 pid）与 `spinner`（自建子进程）两个目标。子进程先有界烧 CPU
`1.5 s` 再睡眠，验证器在两次快照之间做 `0.8 s` 有界 CPU 工作；结束对子进程发
`SIGTERM` 并 `wait` 回收。

**复跑安全（审计修复）**：`--output-dir` 为必填，且必须为新路径。脚本先用单次原子
`os.mkdir`（`exist_ok=False`）创建目录，失败（已存在目录/文件/symlink/并发抢建/
父目录缺失/权限）即以退出码 `3` 拒绝，**在任何子进程启动之前**；所有产物一律在该新
目录内以独占模式（`"x"`）写入。因此旧烟测的 `children-start.json`、before/after/
delta、`result.json` 不会被覆盖或触碰。旧版执行脚本已按字节保存为
`source-run-e2e-v1.py`（SHA `b2e691cd…`）。

## 3. 实测结果（verdict = pass，总耗时 0.873 s）

```
checks（全部 true）:
  bound, same_children_sha256, same_boot_id, same_identity_both_roles,
  spinner_compared, verifier_compared, spinner_start_ticks_matches,
  nonneg_cpu_run_delta, cpu_work_observed,
  wait_counters_disabled_are_null, wait_null_reason_recorded

binding: status=bound, reasons=[], monotonic_delta_ns=812329867
spinner : tid 826, start_ticks 5363, delta{utime=80, stime=1, run_ns=810107421,
          vol=11, nonvol=1, runqueue_ns=null, timeslices=null}
verifier: tid 825, start_ticks 5335, delta{utime=80, stime=1, run_ns=806160525,
          vol=72, nonvol=0, runqueue_ns=null, timeslices=null}
runqueue_ns/timeslices 均为 null，原因：
  host_sched_schedstats_not_enabled(before=0;after=0)
  ;runqueue_counters_invalid(before=sched_schedstats_disabled;
                             after=sched_schedstats_disabled)
CPU run（run_ns）差值保留且为正（≈0.81 s / ≈0.81 s）；未把 null 当 0。
comparison 报告 performance_verdict=not_evaluated, attribution=not_evaluated。
```

子进程清理证据：`child_pid=826, returncode=0, reaped=true`。**该 0 是受控终止**：脚本
给子进程装了 `SIGTERM -> exit(0)` 处理器，验证器主动 `terminate()+wait()`，不是子进程
自发/自然结束（v1 `result.json` 中的 `normal_exit` 字段是旧措辞，含义即此受控终止；
新版改称 `controlled_termination`，并把 `cleanup_ok` 纳入 verdict）。

以上证明：真实 `/proc` 上能绑定同一 boot/children 原始字节 SHA/pid/pgid/start_ticks，
对稳定同线程给出非负 CPU run 差值，并在 `sched_schedstats=0` 时把 wait/timeslice 记
为 null + 原因。

## 4. 产物与 SHA256

```
validation/coordination/owned-scheduling-e2e-20260913/
  run_e2e.py                       （可复跑脚本 v2，新增必填 --output-dir / 独占创建）
  source-run-e2e-v1.py             （旧执行脚本按字节副本，SHA b2e691cd…，只读留证）
  test_run_e2e.py                  （纯行为测试：拒绝先于 Popen、旧树不变）
  children-start.json              （仅 verifier/spinner 两个自有目标；历史，未改）
  owned-scheduling-before.json     （capture 真实形状原始快照；历史，未改）
  owned-scheduling-after.json      （历史，未改）
  owned-scheduling-delta.json      （compare 结果；历史，未改）
  result.json                      （检查项/delta/清理/源 SHA；历史，未改）

源冻结 SHA（历史运行读取，未改）:
  tools/capture_owned_scheduling.py  a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e
  tools/compare_owned_scheduling.py  033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d
  source-run-e2e-v1.py               b2e691cd8da081e7e93087d8158098dff6905f101922bd873fb344b3f49b9ef2
```

（脚本每次复跑会现场重算并写入新目录的 `result.json.source_sha256`。）

## 5. 不可比较路径

若子进程在 after 前退出或身份变化，compare 会给出 `unavailable`/`partial`，脚本
`verdict="not_comparable"`、退出码 2，并保留 before/after/delta 原始件与
`unavailable_reason_if_any`；不会伪造 pass，也不会有 CPU delta。

## 6. 剩余阻断与局限

- 本内核 `sched_schedstats=0`，runqueue/timeslice 无法有效测量；开启需要改内核开关
  （属全局调度修改，本任务禁止），故该指标在本机维持“不可用”而非 0。
- 这是管道烟测，不是 wksim run 行为证据：目标是普通 Python 验证器与子进程，不是
  SITL/模型；不得据此推断飞控或模型时序。
- 单点两点比较，`performance_verdict` 恒为 `not_evaluated`，不归因任何单次事件；
  测试本身也不构成性能结论。
- 需要 Linux `/proc`（Windows 宿主不能直接跑）；`/proc/<tid>/sched` 的 `kernel_prio`
  是内核内部优先级（本机 spinner=`120`），不是 RT 优先级，勿与 runner FIFO 优先级比较。
- 本轮**未重跑成功烟测**，也未启动新子进程或 WSL 负载；`run_e2e.py` 的复跑安全由纯
  行为测试证明（`test_run_e2e.py`，Windows 纯 mock/临时目录）。
- 宿主（Windows）创建 symlink 需特权（`WinError 1314`），故真实 symlink 用例被 skip；
  symlink/existing 类的拒绝由「单次原子 `os.mkdir` → `FileExistsError` → `Refused`」
  契约与 `FileExistsError`/`OSError` mock 用例覆盖，均在 Popen 之前。
- 未运行全库测试、未做构建、未启动任何被禁组件。
