# ds-perf-mixed-hook-audit-20260913-01：PerfStreamCapture 接入实际新架构 MIXED rate window 的只读接线审计

status: **read-only audit complete（设计/接线审计，未实施、未验收）**。本轮没有修改 `tools/run_joint_flight.py`、`Simulator/wksim_runtime/perf_capture.py`、`Simulator/wksim_runtime/joint_rate.py`、任何审计器/测试/共享账本；没有编译，没有运行 native、ROS、飞控、模型、UE、MATLAB。只写本目录的 `audit.md`、`audit.json`、`.gitattributes`。

## 0. 开工核验（本合同格式）

```text
工作类别：new-development（只读设计/接线审计；不实施、不接受正式门）
实际 cwd、分支：C:/Users/PC/Documents/odid编译/wksim，main
HEAD：审计开始 abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18；
      审计期间被主会话并发推进 0779f4372ac576138eb20011c626c812f020b8ff →
      7e1e137879a779f2b051b384c044e6e936878d53（只新增他人证据目录，未触碰本审计引用的文件）
架构祖先检查退出码：git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD
      → abf1ac3 下 0；0779f43 下 0；7e1e137 下 0。abf1ac3 亦为当前 HEAD 祖先（0）。
已读：AGENTS.md、docs/architecture-implementation-20260912.md、
      docs/coordination/architecture-continuation-20260913.md、
      docs/coordination/module-delivery-policy-20260912.md、
      docs/coordination/perf-stream-contract-20260913.md、
      docs/2026-09-13-perf-python-adapter.md、docs/2026-09-13-perf-kernel-loss-counter.md、
      Simulator/wksim_runtime/perf_capture.py、tools/run_joint_flight.py、Simulator/wksim_runtime/joint_rate.py
本次 module / interface：Simulator/wksim_runtime/perf_capture.py（PerfStreamCapture）接入
      tools/run_joint_flight.py 的 MIXED task profile 计时窗口；只读依赖 joint_rate.py、
      scene_clock.py、evidence.host_boot_id()、runtime.digest()、perf_stream_consumer.py 合同。
独占文件：validation/coordination/ds-perf-mixed-hook-audit-20260913-01/{audit.md,audit.json,.gitattributes}
不在本次范围的接线：run_joint_flight.py 本体（main 所有）、joint_profile.py、audit_*、任何测试、共享账本。
交付：稳定 SHA（§1）、实际检查/纯测试（§10）、阻断项（§8）、可直接实施的变更清单（§6）；交付后停止写入。
```

工作树中他人未提交改动（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）与本审计无关；§1 的文件在审计开始、中途、结束三次观测 SHA 全部相同。

## 1. 稳定身份

| 对象 | SHA256 |
| --- | --- |
| HEAD（审计开始 / 结束） | `abf1ac39…` / `7e1e1378…`（并发推进，见 §0） |
| `tools/run_joint_flight.py` | `5527063f04db296d91818a46842207fb5e7ad449651ce23518b6522c0dc011b5` |
| `Simulator/wksim_runtime/perf_capture.py` | `c196616fe8324eed2d8b294ef52aaec1f982eb5330abbeb7ee17094399f32e0f` |
| `Simulator/wksim_runtime/joint_rate.py` | `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4` |
| `Simulator/wksim_runtime/joint_profile.py` | `575adb530944f48fa164a127a88b5abb76991e522ee1dbb8e54ef10ccc6bf5a2` |
| `Simulator/wksim_runtime/experiment_bundle.py` | `efa7a06128289b6ef3edcaf6f97454dc56b4919be5a3b2cd5f8ea4ff26ffaaf8` |
| `Simulator/wksim_runtime/evidence.py` | `4f7f2e601ce3c2edfe54c1c48ed35d41133304c2b1fa56a969148c6ccbbfcb7a` |
| `Simulator/wksim_runtime/runtime.py` | `11b9b326ff9972b999f3d22ecb053329afc9f443f623826d934b2c7154c136d2` |
| `Simulator/wksim_runtime/scene_clock.py` | `a6dc143abf0f9119568090a5aaa0bf06a7fa5e617f107e9606fc6489819add3f` |
| `tools/mixed_control_task.py` | `76adbd47fbe70c4fda4deabd893cc368b9fbd0ceeaabe4a6b7a59e597ed358fc` |
| `tools/audit_mixed_control.py` | `f7f8816674f9526d48c808cfb10a31ca47fa7d08c6263ff531fb13edddb40234` |
| `tools/audit_pv_trajectory.py` | `920aab3cb52220229567e8a56d28adae69ea0adaa9ee45019b1f64c74b56423c` |
| `tools/audit_joint_rate.py` | `fa4e55ae887d57aaafd2dd1fb431d2f967400737d4c5ee64d6a3649404b3276e` |
| `validation/test_perf_capture.py` | `f4d95ae49478729e2f4c3a508f9ef452d3f6b5acffd0c8a3301bc72155d4f3c3` |
| `validation/test_joint_profile.py` | `4a7ce076f24f92ac6b69f72d3308575db40ac1670b04973cacbcdb77111485a0` |
| `validation/test_mixed_profile_admission.py` | `c0c5d11af216bd294a9c4a4b32f108d351c11ef153c10ae6ac366ccd5fa1efcc` |
| `validation/test_delivery_entry_contract.py` | `682f3b20b29a1312becad6ec519fdb8434ff09270af118e55c23e3986cdcc808` |
| `validation/test_joint_rate_probe.py` | `c3bfd1cdd4328c5a084bd7c5f9b9acfec774d008bc9b7ef448b69b2050bf47cb` |
| recorder 源码 `ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c` | `aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2` |
| recorder 头 `…/wksim_perf_stream.h` | `ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823` |
| strict consumer `ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py` | `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc` |
| 已 pin 库 `/root/wksim-perf-python-admission-apup9qju/libwksim_perf_stream.so`（WSL，只读核对） | `37d9651282bce0da059828056796683b94e780461f7918e60c3e1e77e2130020` |

只读 WSL 核对（`\\wsl$\Ubuntu-22.04`，无进程启动）：库文件存在且 SHA 等于 build receipt 与 python-admission run receipt 的 pin；新架构候选 worktree `/root/wksim-architecture-acceptance-20260913` 的 `tools/run_joint_flight.py` 逐字节等于 Windows `5527063f…`，且候选内 `perf_capture.py`（`c196616f…`）、`joint_rate.py`（`0b53a16a…`）、recorder C/H、consumer、`validation/test_perf_capture.py` 均与 Windows 相同。该 worktree 的 HEAD 记录指向 `abf1ac3`（`git worktree list`），候选 HEAD 的权威值须由 main 在准入时重新核验。

## 2. 结论摘要

1. **最小生命周期 seam 是三个点，不是三处控制流重构**：`run()` 主线程内（a）构造于子进程创建之前，(b) `start()` 于 `physics.connect()` 之后、`while clock.tick < MAX_TICKS` 之前，(c) `stop()` 于外层 `finally` 顶部、`cleanup_children()` 之前。`run()` 不创建线程、不 spin（§3.1），三点天然同一 native 线程，满足 `perf_capture` 的 owner 校验。
2. **窗口边界只读 `JointRate` 状态导出**：`start_ns = rate.last_summary['anchor']['wall_ns']`，`end_ns = rate.last_end`（最后一个完整 4-tick 组的实际结束），id `mixed_rate_segment_<segment_id>`。这与 `audit_pv_trajectory.rate_windows()` 校验的同一段一一对应（`segment['groups'][-1]['end_tick'] == result['final_authority']['tick']`），且两端严格落在捕获的 inner span 内。`joint_rate.py` 一行不改。
3. **CLI 走既有 runner 的 manifest/SHA 配对风格**：`--perf-library` + `--perf-library-sha256`，仅 MIXED 允许。新架构 deployment 文档**不能**承载该 pin（`experiment_bundle.resolve` 对文档与 release 字段做精确集合校验），因此不得把 pin 塞进 `local-deployment.json`，也不得在 runner 内另造部署解析体系。
4. **输出落在本次 run 的 `live` 目录**（fresh `mkdtemp`，天然满足"输出不存在 + 父目录存在"）：`perf-switch.raw`、`perf-switch.meta.json`、`perf-windows.json`，随后由既有 `shutil.copytree(live, archive)` 进入 archive。
5. **失败策略是 fail-closed**：请求了捕获而 start/stop/窗口/密封/库身份任一不完整 → 该 run 不得为 `pass`；绝不允许"捕获不完整但 run 通过"。stop 在 `cleanup_children()` 之前，任何 teardown 失败/挂起都不能吞掉原始证据。
6. **源码归档身份**：请求时把 `Simulator/wksim_runtime/perf_capture.py`（及 recorder C/H，建议）加入 `sources`，从而进入 `result['source_sha256']`、`source__*.txt`、`source_unchanged`；库本身不进 repo 归档，只记路径 + SHA + kernel + boot，并在 stop 后重算确认未变。
7. **严格 consumer 在 runner 之外、archive 之上由 main 运行**，带 `--require-kernel-counter --windows`，输出到 archive 内的新文件名；这是"独立解码"，不能由 runner 自证。
8. **正式门目前不拒绝 perf 诊断 marker**：`Simulator/wksim_runtime/joint_profile.py:274-276` 的存在性拒绝元组只有 `rate_timing_probe`/`group_work_timing`。在该元组加入 perf marker、并补齐对应纯测试之前，任何 instrumented MIXED run 都可能被当作正式 MIXED/PV 证据接纳。这是本轮唯一的实施阻断项（§8 B1）。**本审计不声称正式门允许诊断 marker。**

## 3. 现状事实（逐行核对）

### 3.1 `run()` 的单线程生命周期（`tools/run_joint_flight.py`，SHA `5527063f…`）

| 行 | 事实 |
| --- | --- |
| 24-47 | `REPO` 入 `sys.path`；模块顶部导入 `JointRate`（33）、`joint_rate_probe` 系列（34-40）、`MIXED_PROFILE`（47）。无 `ctypes`/线程导入。 |
| 52-54 | `make_joint_rate(...)` 按 `diagnostic` 选 `JointRateTimingProbe` 或 `JointRate`；**diagnostic 只由环境变量 `WKSIM_JOINT_RATE_TIMING_PROBE` 控制**（`timing_probe_enabled()`，326）。 |
| 325-334 | `run(args)` 入口；`timing_probe`/`async_model_evidence`/`model_promotion_flight` 三个既有诊断/候选开关。 |
| 348-352 | `SIGTERM` → `InterruptedError`；要求私有 mount namespace。 |
| 353-354 | `archive = mkdtemp(dir=REPO/'validation')`；`live = mkdtemp(dir='/root')`。两者都是全新空目录。 |
| 382 | `pause_probe = lifecycle = rate = messages = None`——外层 `try`（422）之前唯一的本地状态初始化。 |
| 383-418 | `sources` 列表；`candidate`（MIXED/PV）追加 `candidate_rate_sources()`= `joint_rate.py`/`joint_rate_probe.py`（57-61、402）。 |
| 419-421 | `result['source_sha256'] = {name: digest(REPO/name) …}`；同时把每个源文件写入 `live/source__<name with __>.txt`。 |
| 431-444 | 候选准入 `admit_candidate(...)`；`result['mixed_admission']`；`activate_candidate_imports`。 |
| 757-758 | `rate = make_joint_rate(clock.epoch, .5, record_rate, diagnostic=timing_probe)`；`record_rate('rate_bootstrap', …)`。MIXED 速率**固定 0.5**，runner 从不调用 `rate.set_rate`（全仓 grep 仅在旧 `joint_runtime.py` 与测试中出现）。 |
| 777-779 | `result['manager_scheduling'] = scheduling(0,'manager', …)`：把**当前线程**设为 nice −10 / `SCHED_FIFO` 50（`scheduling()` 102-129，`pid=0`）。 |
| 780-827 | 逐个 `subprocess.Popen` 创建 8 个子进程（model×2、agent×2、fc×2、control×2）与 2 个 task。 |
| 829-851 | 候选初始化（`initialized.json`、worker 快照、`record_native_maps('running')`）。 |
| 852 | `physics.connect()`。 |
| 855-877 | `advance()`：速率组在 `clock.tick%4==0 and clock.synchronized and clock.phase=='running'` 时 reanchor/begin_group（857-860）；`physics.advance()`；`end_group`（875-876）。 |
| 878-955 | 主 tick 循环；退出条件 `len(result['tasks'])==2 and clock.tick%4==0`（954-955）。 |
| 969-972 | `rate.check_boundary(clock.tick)`；`rate.close_segment('completed', clock.tick)`；`result['rate'] = rate.last_summary`。 |
| 973-980 | `clock.request(stop)`、`terminal_transition`、`record_native_maps('completed')`、关闭两个 model worker stdin 并等待。 |
| 981 | `result['status']='pass'`。 |
| 982-988 | `except PauseProbeComplete` / `except BaseException`（记 error/traceback/faulted_authority）。 |
| 989-1042 | 唯一外层 `finally`：`cleanup_children`（990）、子进程返回码（992-993）、async 证据（994-1000）、`unowned_ap_after`/`source_unchanged`（1001-1002）、control/native/model 变更复核（1003-1026）、`control_shutdown_clean`（1027-1030）、状态归约（1031-1035）、`flight_completed`（1036）、`wall_seconds`、`save(live/'result.json')`（1038）、`copytree`（1039）、print（1040）、返回码（1042）。 |

线程事实：`run()`（325-1042）内除 `subprocess.Popen` 外没有任何 `threading.Thread`/`concurrent.futures`/`rclpy.spin*`；`rclpy.spin_once` 只出现在 `task_main`（267、274），即子进程角色。`rclpy.init`（740）与 `create_node`（743）不 spin。分布式时钟由 `ClockPublisher`/`SceneClock` 直接发布，`JointPhysics` 通过子进程管道工作。⇒ `start()`/`stop()` 与速率窗口驱动必然在同一 launcher 主线程上，`perf_capture._check_owner()` 的 `(os.getpid(), threading.get_native_id())` 在两次调用间不会变化。

### 3.2 速率窗口的真实边界（`joint_rate.py`，SHA `0b53a16a…`）

- `RATES=(0.5,1.0)`，`LATE_LIMIT_NS=100_000_000`（5-6）；`period_ns = int(4_000_000/rate)`（33-35）；`SceneClock.STEP_NS, MACRO_TICKS = 1_000_000, 4`（scene_clock.py:14）。
- `reanchor()`（43-57）在 `tick%4==0` 建立 `anchor=dict(tick, wall_ns=self.now(), transition)`，并重置 `completed/last_end/worst_lateness_ns`；`begin_group()`（89-130）用 `earliest = max(ideal, previous_start+period)`（93）实现**无追赶**；`end_group()`（132-143）在恰好 4 tick 后设 `self.last_end = now` 并 `check(lateness)`。
- `close_segment()`（37-41）把 `snapshot(tick)` 存入 `self.last_summary`，随后 `anchor=group=None`；`last_end` 保留。`snapshot()`（145-155）含 `anchor`（同 dict 引用）、`completed_groups`、`worst_lateness_ns`、`measured_rate`，**不含 `last_end`**。
- ⇒ MIXED run 的"实际 rate window"= `[anchor['wall_ns'], rate.last_end]`，与 `audit_pv_trajectory.rate_windows()`（801-837）读取的 `rate.jsonl` 同一段：`len(segments)==1`、`anchor['requested_rate']==.5`、`segment['groups'][-1]['end_tick'] == result['final_authority']['tick']`、10 s/60 s 完整滑窗与 2%/1% 预算、`rate_boundary_check` 先于显式 stop。
- 时间域一致：`rate` 用 `time.monotonic_ns`，recorder 用 `CLOCK_MONOTONIC`（consumer `CLOCK_ID='CLOCK_MONOTONIC'`，consumer:47）。`record_rate`（752-756）还给每行加 `issued_monotonic_ns`，因此窗口可与 `rate.jsonl` 逐行对读。

### 3.3 `PerfStreamCapture` 的所有权语义（`perf_capture.py`，SHA `c196616f…`）

- 构造（26-63）：要求 `platform.system()=='Linux'` **且** `platform.release()==TESTED_KERNEL_RELEASE`（14，`6.6.87.2-microsoft-standard-WSL2`）；库必须是已存在的**绝对** `.so`；`library_sha256` 必须 64 位小写十六进制且逐字节匹配；两个输出路径必须绝对、父目录已存在、**当前不存在**（`os.path.lexists`）、且 `resolve()` 后互不相同；记录 `owner_pid/owner_tid`（50）后才 `CDLL`（51）。构造失败会抛 `PerfCaptureError`，不建落任何 native 资源。
- `start()`（87-100）：owner 校验 → 只允许一次尝试（`_attempted`）→ 再次确认输出未出现 → C `wksim_perf_start`。非 0 抛错，错误文本含 `retained=<owns_handle>`；成功但句柄为 NULL 也抛错。
- `stop()`（102-114）：owner 校验 → 必须有活句柄 → C `wksim_perf_stop(&handle, raw, meta)`；非 0 抛错（可能 `retained=True`）；返回 0 但句柄仍活也抛错；`_stop_ok = _start_ok`（113）⇒ **失败 start 的清理 stop 永远不会变成成功捕获**。
- 无 `__del__`/上下文管理器/`atexit`/回调（review.md 第 5 项复核）。`owns_handle`/`stop_completed` 是 launcher 唯一可用的显式状态。
- C 侧（recorder `wksim_perf_stream.c`）：`owner_pid=getpid()`、`owner_tid=syscall(SYS_gettid)`（679-680）、`boot_id` 读 `/proc/sys/kernel/random/boot_id` 并在首个 `\n`/`\r` 截断（358-385），与 Python `threading.get_native_id()`、`Simulator/wksim_runtime/evidence.py:host_boot_id()` 同语义同格式（36 字符带连字符 UUID）。`stop` 写 raw/meta 用 `O_CREAT|O_EXCL`；语义失败（如无完整 switch pair）在独占创建**之前**判定（review.md Revision 2 已由 `collision2-receipt.json` 孤立证明）。

### 3.4 严格 consumer 的合同（`perf_stream_consumer.py`，SHA `dee9a3b5…`）

- 必填元数据字段（67-73）与精确 `config`（58-66，`read_format=16`）；`reader_policy` 必须是整数 0（224-226）；`collector_complete is True` 且 `collector_errors == []`（240-246）；四个 lifecycle 布尔全 True（248-255）。
- `kernel_lost_*` 四字段必须齐全、`read_ok True`、`read_bytes==16`、`errno==0`、`count==0`（147-166）；`--require-kernel-counter` 时缺任一即 `kernel_loss_counter_required`（497-498）。⇒ **每次完整性依赖的调用都必须带该 flag**（契约 112-113）。
- raw 长度必须精确等于 `captured_bytes`（218-220）；记录必须全是 32 字节 SWITCH、成对交替且闭合、至少一对（docstring 16-24、`build_pairs` 379-393）。
- windows（396-451）：`wksim.perf_windows.v1`，必须绑定 `boot_id`/`owner_pid`/`owner_tid`/`clock_id`，id 非空唯一，`0 <= start_ns < end_ns`，且 `start >= enable_after_ns`、`end <= disable_before_ns`（**inner span**，445-449）。
- 输出必须是不存在的新文件（492-493、582）；工具自身 `full_acceptance=False`、`flight_conclusion=None`（519-520）。

### 3.5 现有源码归档与身份机制

- `sources`（383-418）→ `result['source_sha256']`（419）→ `live/source__*.txt`（421）→ `finally` 中 `source_unchanged`（1002，候选另加 control/native 源，1003-1012）。
- `audit_mixed_control.retained_identity()`（113-146）：`mandatory <= sources.keys()`（142）且 **`{source__*} 文件名集合 == {source__+name for name in sources}`（143-144）**，随后逐个比对归档字节（145-146）。⇒ "sources 加什么就必须写入什么 `source__` 文件"；runner 由同一 dict 生成两者，安全；但**不得**在任何一侧单独增删。
- `audit_pv_trajectory`（300-308）同构；`joint_profile._mixed_proofs`（329-342）要求 `required ⊆ sources` 且每个 source 都在 audit 的 `evidence_sha256` 中被封存；`audit['evidence_sha256']` 是该 archive 目录 `rglob('*')` 的全文件摘要（audit_mixed_control.py:822），因此额外的 perf 证据文件会被自动纳入，不会破坏集合关系。
- `result['bounds']` 被精确比对（audit_mixed_control.py:123-124）⇒ perf 信息**不得**写进 `bounds`。
- 候选准入在**同一进程内**以当前字节计算 `identities.source_sha256`（ap_mixed_candidate.py:135-150、ap_pv_candidate.py 同构），没有硬编码 runner SHA；但 `audit_pv_trajectory`（316-317）要求 flight sources ⊇ admission sources 且值相等 ⇒ admission 与 flight 必须来自同一份源码字节。
- `validation/test_joint_rate_probe.py:28` 硬 pin `joint_rate.py = 0b53a16a…`；`docs/coordination/ds-architecture-mixed-migration-20260913.md` 记录 runner `5527063f…` 在 Windows 与候选两侧相同，且 `docs/coordination/ds-startup-cost-evidence-20260912.*`、`docs/plan/33-rate-next-diagnostic-20260912.md` 记录 `joint_rate.py` 同一 SHA。

### 3.6 正式门对诊断 marker 的现存拒绝机制

- `Simulator/wksim_runtime/joint_profile.py:274-276`：

  ```python
  for marker in ('rate_timing_probe', 'group_work_timing'):
      if marker in flight:
          raise ValueError('Formal mixed/PV evidence cannot include '+marker)
  ```

  语义是**键存在即拒绝**（与取值无关），位于 `_mixed_proofs()` 的最前面（277 之前）。这是正式 MIXED/PV 证据"不得携带诊断 marker"的唯一实现点。
- 纯测试覆盖：`validation/test_joint_profile.py:355-370`（`add_probe_record` 与 `marker=('group_work_timing', True/False/None/{})`）、`validation/test_mixed_profile_admission.py:203-217`（`rate_timing_probe` 取 `None/{}/False/'enabled'/dict` 全部拒绝，且 `raw.assert_not_called()`）。
- 原始飞行审计（`tools/audit_mixed_control.py`、`tools/audit_pv_trajectory.py`）**不**拒绝 `rate_timing_probe`；`audit_mixed_control.py:132-134` 的 `Unexpected alternate workflow` 循环只包含 `pause_probe_requested`/`scene_lifecycle_requested`/`scene_lease_loss_requested`/`dds_loss_requested`/`diagnostic_land_step_period_s`。⇒ 既有先例是"原始审计容忍诊断 marker，正式证明门按存在性拒绝"。perf marker 应完全照此办理（§6 C7），从而 instrumented run 仍可被原始审计复核，"instrumented run 依然满足全部未改动的物理/速率/身份门"这一结论可得，但它**永远不能成为正式 MIXED/PV 证据**。

### 3.7 CLI / deployment 输入现状

- `run_joint_flight.py` 的 run 子命令（1049-1075）用显式 `--<name>-manifest/--<name>-sha256` 对（1067-1072），并在 `main()` 里对每一对做完整性校验（1128-1131），对 task profile 做互斥校验（1092-1113）。
- MIXED 分支（1100-1106）当前只拒绝"另一族 manifest/探针"；增加可选的 perf 对不会改变既有组合的接受/拒绝结果。
- `experiment_bundle.resolve()`（54-100）对 deployment 文档做精确集合校验：`set(deployment) == {'schema_version','firmware_releases'}`（61），每个 release `set(release) == {'family','target','vehicle_model','manifest_linux','manifest_sha256'}`（67-69）。⇒ 新架构的部署文档**没有**诊断库的位置；把 perf pin 写进 `local-deployment.json` 会直接使 `resolve` 抛 `Unsupported deployment document`/`Firmware deployment must declare target, vehicle and pinned receipt`。`run_joint_flight.py` 也从不消费该文档。
- 结论：MIXED perf 的部署 pin 必须走 runner 自己的 CLI 对（与 `--px4-manifest/--px4-sha256` 同级），运行结果内记录实际路径/SHA/kernel/boot；真正的构建来源绑定仍由 main 的既有 build receipt（`perf-python-native-admission-20260913-01/build-receipt.json`，`library_sha256=37d96512…`、`source_sha256={aa807f3b…, ef1eabf2…}`）承担。若将来要让 deployment 文档承载该 pin，那是一次显式的 `experiment_bundle` 接口演进（含自己的纯测试），不属于本次接线，且**不得**在 runner 内另造并行解析。

### 3.8 运行环境前置（已由既接纳证据覆盖）

- 内核 `6.6.87.2-microsoft-standard-WSL2`、`perf_event_paranoid=2` 下自线程软件 DUMMY + `context_switch` 的可行性、`exclude_kernel=1` 的必要性见 `validation/coordination/omp-perf-scope-review-20260913-01/REPORT.md`；调用边界已由 `perf-python-native-admission-20260913-01/run-receipt.json` 原生验证（9 项 mocked 边界 + 真实调用、`--require-kernel-counter` 通过）。
- 适配器只依赖调用线程与库；不会改动 sysctl、affinity、resource limit 或其他线程的调度。**reader 线程由 C 显式设为 SCHED_OTHER 并回读校验（G7）**，因此 manager 的 FIFO/50 不会被继承。
- `isolate_temporary_files()`（isolation.py:14-72）会把 `/tmp` 换成私有 overlay；放在 `/tmp` 下的 `.so` 会在运行期不可见。部署 pin 必须位于 overlay 之外（当前 pin 在 `/root/...`）。

## 4. 只读验证到的接线风险点

| 编号 | 风险 | 证据 | 处理 |
| --- | --- | --- | --- |
| R1 | 正式门不拒绝 perf marker | joint_profile.py:274-276 | §6 C7，阻断项 B1 |
| R2 | Windows runner 改动后与候选 runner 分叉 | `git worktree list` + `\\wsl$` 只读核对：候选 runner == `5527063f…` | §8 B2：同步候选并重记身份 |
| R3 | 新 CLI 参数破坏既有 selector 纯测试 | test_mixed_control_task.py:14-46（`main()` 接受/`SystemExit(2)`）、:68-78（真实子进程 exit 2） | perf 对必须可选；不得改变既有组合结论 |
| R4 | `joint_rate.py` 被纯测试与文档硬 pin | test_joint_rate_probe.py:28；ds-startup-cost-evidence-20260912.* | 接线一行不改 `joint_rate.py` |
| R5 | `{source__*} == sources.keys()` 强等式 | audit_mixed_control.py:143-146；audit_pv_trajectory.py:305-308 | sources 与归档写必须同源（现状已同源） |
| R6 | `result['bounds']` 精确相等 | audit_mixed_control.py:123-124 | perf 元信息不得写入 bounds |
| R7 | 与 `WKSIM_JOINT_RATE_TIMING_PROBE=1` 叠加会测量被自己改写的路径 | run_joint_flight.py:326-328、52-54；joint_rate_probe.py | §6 C1：二者互斥（fail fast） |
| R8 | reader 继承 FIFO 的可能性 | C 显式 SCHED_OTHER + 回读（G7）；runner 在 778 才提升为 FIFO/50 | start 放在提升之后：既实测"未继承"，失败即 fail-closed |
| R9 | `/tmp` overlay 隐藏部署库 | isolation.py:38-39 | 库路径必须在 overlay 之外；当前 pin 在 `/root` |
| R10 | 事件 fd 与 fork | 契约（inherit=0、CLOEXEC、per-CPU 无）；MIXED 与 dds-loss/scene-lifecycle 互斥（1101-1106） | stop 置于 `cleanup_children` 之前，任何 teardown 之前封存 |
| R11 | 启动突发压低 512 KiB ring 的 4096 B headroom | 契约 24-27；recorder G6 | start 放在子进程创建与候选初始化之后 |
| R12 | 捕获体积上界 | `WALL_LIMIT=900`、`MAX_TICKS=180000`、rate 0.5 ⇒ 墙钟 ~360 s；既有 360 s/8 ms 合成实测 raw 2,880,064 B / 90,002 records / 0 loss（`perf-overhead-long-20260913-01`） | 远低于 128 MiB storage；但**合成测量不等于真实窗口开销**，不得据此给真实结论 |

## 5. 必须保持不变的既有门（接线不得触碰）

- **1 ms tick**：`SceneClock.STEP_NS=1_000_000`、`begin_step`/`commit` 的 tick 证明；接线不新增步进。
- **4-tick 组**：`MACRO_TICKS=4`、`clock.tick%4` 边界与 `begin_group/end_group` 的"恰好四 tick"断言。
- **无追赶**：`earliest=max(ideal, previous_start+period)` 与 `previous_start` 语义。
- **100 ms 晚限**：`LATE_LIMIT_NS` 与 `check()` 的 latch 语义；perf start/stop 不得插入 `advance()`/`check()` 路径。
- **完整窗口**：`audit_pv_trajectory.rate_windows()` 的 10 s/60 s 完整滑窗、2%/1% 预算、`boundary_tick == final_authority.tick`、`len(segments)==1`。
- **身份与物理门**：`sources`/`source_unchanged`、manifest/control/message 身份、`control_shutdown_clean`、`cleanup_errors`、`unowned_ap_before==after`、`truth_summary` 边界、native maps 检查——一律不放宽、不参与 perf 枚举。
- **正式门**：`joint_profile._mixed_proofs` 的存在性拒绝只增不减；instrumented run 不是正式 MIXED/PV 证据。

## 6. 变更清单（main 可直接实施；精确到锚点）

> 只允许 main 在 `tools/run_joint_flight.py` / `joint_profile.py` / 测试内实施；本审计不实施。以下行号均对 `tools/run_joint_flight.py` SHA `5527063f…`。

**C1 CLI 与请求判定（`main()`，1049-1075 与 1087-1133）**
1. 在 run 子命令增加 `--perf-library`、`--perf-library-sha256`（可选，默认 None）。
2. 在 `task` 子命令**不**增加（task 是子进程角色，绝不持有 recorder）。
3. 在 `main()` 的 run 校验区新增：`if (args.perf_library is None) != (args.perf_library_sha256 is None): parser.error('Perf switch capture requires both --perf-library and --perf-library-sha256')`。
4. 新增：`if args.perf_library is not None and args.task_profile != MIXED_PROFILE: parser.error('Perf switch capture is only allowed for the MIXED task profile')`（先于 1100 的 mixed 分支亦可，语义等价）。
5. 在 `run()` 内、`timing_probe = timing_probe_enabled()`（326）之后互斥：`if args.perf_library is not None and timing_probe: raise ValueError('Perf switch capture and WKSIM_JOINT_RATE_TIMING_PROBE are mutually exclusive diagnostics')`（对应 R7）。
6. 不改变任何既有组合的接受/拒绝结论（R3）：perf 缺失时新校验全部为 no-op。

**C2 源码归档身份（383-421）**
7. 在 `if async_model_evidence:` 块（405-406）之后追加：

   ```python
   if args.perf_library is not None:
       sources += ['Simulator/wksim_runtime/perf_capture.py',
                   'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c',
                   'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h']
   ```

   （三者都是被执行的 Python 适配器与库的来源字节；419-421 会自动摘要并写 `source__*.txt`，保持 R5 的强等式。若 main 认为 C/H 归属部署 receipt 而不入 run 归档，可只保留第一项——但那样 run 的 source 身份就不覆盖库来源，须在 result 内显式记录 receipt 路径/SHA 以补足。）
8. `candidate_rate_sources(_diagnostic)`（57-61）忽略入参的既有瑕疵不在本次范围，不要顺手改。

**C3 早期构造（`run()`，382 与 757-758 之后、780 之前）**
9. `382` 改为 `pause_probe = lifecycle = rate = messages = capture = None`。
10. 在 758 的 `record_rate('rate_bootstrap', …)` 之后、780 的子进程循环之前：

    ```python
    if args.perf_library is not None:
        capture = PerfStreamCapture(args.perf_library, args.perf_library_sha256,
                                    live/'perf-switch.raw', live/'perf-switch.meta.json')
    ```

    理由：kernel/路径/SHA/输出不存在四项前置在任何子进程创建之前 fail-fast；`live` 是 fresh `mkdtemp`，天然满足"输出不存在 + 父目录存在 + raw≠meta"；构造不启动 recorder，也不受 owner-thread 约束（该约束只在 start/stop）。

**C4 请求 marker（359-377 之后）**
11. 在 `result['async_model_evidence_requested'] = async_model_evidence`（375）附近、`try`（422）之前追加（**仅当请求时**出现）：

    ```python
    if args.perf_library is not None:
        result['perf_switch_capture'] = dict(
            classification='diagnostic_only', full_acceptance=False, requested=True,
            library=str(Path(args.perf_library)), library_sha256=args.perf_library_sha256,
            kernel_release=platform.release(), boot_id=host_boot_id(), status='not_started')
    ```

    要求：`import platform`（新）与 `from Simulator.wksim_runtime.evidence import host_boot_id`（复用既有 helper，勿新造 boot 读取）。marker 名称固定为 `perf_switch_capture`，与 C7 的拒绝元组必须逐字一致。marker 只在请求时出现，保证未 instrumented 的 run 照旧通过正式门（274-276 是存在性判断）。
    同时在模块顶部导入 `from Simulator.wksim_runtime.perf_capture import PerfCaptureError, PerfStreamCapture`（导入期无 native 动作；纯测试可 patch）。

**C5 start 的最小 seam（852-878）**
12. 在 `physics.connect()`（852）与主循环之间、`while clock.tick < MAX_TICKS:`（878）正上方：

    ```python
    if capture is not None:
        capture.start()
        result['perf_switch_capture']['owner_pid'] = capture.owner_pid
        result['perf_switch_capture']['owner_tid'] = capture.owner_tid
    ```

    位置理由：在 `scheduling(0,'manager')`（778）之后 ⇒ 若 reader 继承了 FIFO，C 的 SCHED_OTHER 回读会令 start 失败（R8）；在子进程创建与候选初始化之后 ⇒ 避开 spawn/ROS 突发对 512 KiB ring 的 4096 B headroom 压力（R11）；在循环之前 ⇒ 捕获完整覆盖 rate window 与 teardown 尾部。

    **不要**把 start 放进 `advance()` 或 `rate.reanchor()`：那会把 native 调用塞进被 pacing 的闭包，且窗口由 `--windows` 收窄已足够；最小 seam 是"循环前一次 start + finally 一次 stop"。

**C6 finally 内的 stop、窗口导出、密封与状态归约（989-1035）**
13. 在 `finally:`（989）之后、`cleanup_children(...)`（990）**之前**插入一个自包含块，全部用 `try/except BaseException` 包裹，绝不向外抛（避免覆盖正在传播的原始异常）：

    a. `if capture is not None and capture.owns_handle and not capture.stop_completed: capture.stop()`；捕获 `PerfCaptureError` 记入 `perf['error']`；无论成功失败都记 `perf['stop_completed']=capture.stop_completed`、`perf['owns_handle_after']=capture.owns_handle`。
    b. 窗口：`if rate is not None and rate.last_summary and rate.last_summary.get('anchor') and rate.last_end is not None:` 且 `last_summary['anchor']['transition'] is False` 且 `0 < start < end` ⇒
       `window = dict(id='mixed_rate_segment_%d' % rate.last_summary['segment_id'], start_ns=start, end_ns=end)`，其中 `start = rate.last_summary['anchor']['wall_ns']`、`end = rate.last_end`；用 `save(live/'perf-windows.json', dict(schema='wksim.perf_windows.v1', boot_id=host_boot_id(), owner_pid=capture.owner_pid, owner_tid=capture.owner_tid, clock_id='CLOCK_MONOTONIC', windows=[window]))`。
       （`boot_id` 必须复用**同一** `host_boot_id()` 调用结果与 metadata 比对；若要与 C 写出的 metadata 交叉核对，只允许读取 `perf-switch.meta.json` 的 `boot_id/owner_pid/owner_tid` 做**等值断言**，不得用 metadata 反向定义窗口身份。）
    c. 密封：`raw`/`meta`/`windows` 三个文件都必须存在且 raw 非空，记录 `digest()`（`runtime.digest` 已在 32 行导入）与 raw 字节数。
    d. 库身份：重新 `digest(Path(args.perf_library))` 并要求等于 `args.perf_library_sha256`，记 `library_unchanged`。
    e. 判定：仅当 start 成功、`stop_completed is True`、三文件齐备且摘要已记、`library_unchanged is True`、窗口已导出时 `perf['status']='complete'`；否则 `perf['status']='failed'` 并填 `error`。
    f. 把 `perf` 合并回 `result['perf_switch_capture']`（保留 C4 的 marker 与身份字段）。

14. 状态归约（1031-1035）追加一项：`or (result.get('perf_switch_capture') and result['perf_switch_capture'].get('status') != 'complete')` ⇒ `result['status']='failed'`。语义：请求了捕获却拿不到完整、可独立解码的窗口证据时，该 run 不得为 `pass`（含 `flight_completed` 随之 False）。
15. 顺序不变部分：`cleanup_children`（990）及其之后的所有既有检查（992-1035）保持原样；`save(live/'result.json')`（1038）与 `copytree`（1039）自然带上 marker、摘要与三个证据文件。
16. `result['bounds']` 保持精确不变（R6）。

**C7 正式门拒绝 perf marker（`Simulator/wksim_runtime/joint_profile.py:274`）**
17. `for marker in ('rate_timing_probe', 'group_work_timing'):` → `for marker in ('rate_timing_probe', 'group_work_timing', 'perf_switch_capture'):`（保持"键存在即拒绝"的既有语义）。
18. 原始审计容忍策略**保持**（照 `rate_timing_probe` 先例）：不要往 `audit_mixed_control.py:132-134` / `audit_pv_trajectory.py:297-299` 的 "Unexpected alternate workflow" 循环里加该键——那会阻止 main 对 instrumented flight 做原始复核，而"instrumented flight 仍满足全部未改动门"这一结论只能由原始审计给出；正式性由 C7.17 的正式门单独保证。若 main 选择更严（原始审计也拒绝），则必须接受"instrumented run 无原始审计"的代价，且不得把该 run 当作任何门通过。
19. 补纯测试（见 §9 T2/T3），逐字断言 `cannot include perf_switch_capture` 与"取值真/假/None/{} 全部拒绝"。

**C8 运行期身份与前置记录**
20. marker 内记录 `kernel_release`、`boot_id`、库路径与 SHA；run 结束时 `library_unchanged` 必为 True（C6.d）。
21. 可选但推荐：把 `--perf-library-sha256` 与 main 的 build receipt（`library_sha256`、`source_sha256`）在准入前比对一次，失败即 fail-fast；这属于 main 的部署准入，不改变 runner 的 CLI 形状。

**C9 不实施项**
22. 不改 `joint_rate.py`、`scene_clock.py`、`joint.py`（R4）；不改 `perf_capture.py`（其审查结论为无缺陷）；不改 consumer；不改其它审计器阈值；不改共享账本与派发 JSON。

## 7. 严格 consumer 的后处理位置

1. **位置**：runner 进程退出之后，由 main 在 **archive 目录**上运行，不在 runner 内调用（独立解码是契约要求；契约 88-92 亦规定 native 验证由 main coordinator 执行）。
2. **输入**：`--raw <archive>/perf-switch.raw`、`--metadata <archive>/perf-switch.meta.json`、`--windows <archive>/perf-windows.json`、`--require-kernel-counter`；`--output <archive>/perf-decoded.json`（必须是新文件；工具拒绝覆盖，重复解码要换名）。
3. **独立性 pin**：consumer 用固定字节 `dee9a3b5…`；其 `inputs.raw_sha256/metadata_sha256/windows_sha256` 必须与 runner 在 `result['perf_switch_capture']` 内密封的摘要逐字相等（否则说明 archive 被替换）。
4. **与飞行审计的先后**：先 consumer、后 `tools/audit_mixed_control.py <archive>`。理由：`audit.json.evidence_sha256` 是该目录全文件摘要（audit_mixed_control.py:822），这样 `perf-decoded.json` 会被飞行审计一并封存；反过来则不被封存。
5. **不要**把 `perf-decoded.json` 或其任何派生值写入 `result.json`；解码结论属于事后证据，不能回填成飞行结果的一部分。
6. **结论边界**：consumer 只输出 `stream_completeness_proven`（覆盖 inner span 内的配置事件捕获）与窗口交集；它不证明因果调度、不证明精度、不构成 MIXED/G6/Full 通过。`full_acceptance=false`、`flight_conclusion=null` 必须原样保留。

## 8. 阻断项与残余风险

**B1（实施前必须解决，否则禁止运行 instrumented MIXED）**：正式门当前不拒绝 perf marker。`joint_profile._mixed_proofs:274-276` 只拒绝 `rate_timing_probe`/`group_work_timing`。在 C7.17 与该门的纯测试落地前，instrumented run 可被当作正式 MIXED/PV 证据接纳，等于让诊断 marker 通过正式门。本审计**不**声称正式门允许诊断 marker。

**B2（native 准入前置）**：Windows `tools/run_joint_flight.py` 目前 `5527063f…`，与新架构候选 worktree 内的 runner 逐字节相同（只读核对）。实施 C1-C6 后两者必然分叉；main 必须在运行前把候选/运行检出同步到同一新 runner 字节并在证据中重记其 SHA，否则 instrumented 证据指向旧 runner（准入虽会因进程内自算 `source_sha256` 而不会静默通过，但归档身份与实际执行不符）。候选内 `perf_capture.py`/`joint_rate.py`/recorder C/H/consumer/test 已与 Windows 同 SHA，不存在缺源码问题。

**G1（非阻断，残余）**：`PerfStreamCapture` 的原生 owner 样本只有主线程（`owner_pid==owner_tid==765`）；本接线正好使用 launcher 主线程（pid==tid），与该证据适用范围一致，但"非主线程 owner"仍未覆盖。

**G2（非阻断）**：本审计未运行 native（禁止），因此以下未实测：真实 MIXED 窗口下 recorder 对 100 ms 晚限/完整滑窗的影响、真实 raw 体积、recorder 与 FIFO manager 的共存表现。它们只能由 main 的一次带前检的实际运行回答；本轮合成 360 s/8 ms 证据**不是**真实窗口开销。

**G3（非阻断）**：`perf_capture` 的 kernel 硬校验使本接线绑定 `6.6.87.2-microsoft-standard-WSL2`；内核变化需重新验证（契约 100-103）。

**G4（非阻断）**：C2 是否把 recorder C/H 纳入 `sources` 是身份完备性与改动面之间的取舍；无论哪种选择，库来源都必须由 main 的 build receipt pin 承担。

## 9. 受影响测试与 native 验收

**纯测试（Windows 侧可运行，无 ROS/native）**

| 编号 | 测试 | 现状（本轮实测） | 实施后要求 |
| --- | --- | --- | --- |
| T0 | `python -B -m unittest validation.test_perf_capture -v` | 9/9 pass（0.023 s） | 必须继续 9/9（适配器不改） |
| T1 | `python -B -m unittest validation.test_delivery_entry_contract -v` | 9/9 pass（0.021 s） | 必须继续通过；建议把 `--perf-library` 字面与新配对错误文本纳入 `EntryParserTests`/`PairingEnforcementTests` 的静态断言（该文件的自述职责就是"真实 parser 里必须存在被记录的开关"） |
| T2 | `validation/test_joint_profile.py::MixedProofPacerBindingTests` | 现有 `rate_timing_probe`/`group_work_timing` 两个 marker 测试 | 新增 `perf_switch_capture` 的"任意取值均拒绝"用例（复用 `marker=(name,value)` fixture，值取 `True/False/None/{}` 与一个填充 dict） |
| T3 | `validation/test_mixed_profile_admission.py::test_mixed_result_with_rate_timing_probe_is_rejected` | 现有 | 照抄一份 `perf_switch_capture` 版本，并断言 `raw.assert_not_called()` |
| T4 | `validation/test_mixed_control_task.py`（selector/CLI） | 需 ROS 环境 | 必须仍接受既有合法组合、仍对缺 pair/交错族返回 exit 2（perf 参数缺席时零影响） |
| T5 | `validation/test_joint_rate_probe.py` | 硬 pin `joint_rate.py=0b53a16a…` | 必须继续通过（C9 不改 `joint_rate.py`） |
| T6（建议新增） | 纯窗口导出测试 | 无 | 用合成 `rate.last_summary`/`last_end` 断言 `perf-windows.json` 的 schema/id/边界，以及"无完整组 ⇒ 不导出 + status failed"的 fail-closed 行为 |
| T7（建议新增） | 纯 CLI 校验测试 | 无 | `--perf-library` 单侧出现 ⇒ `parser.error`（可 patch `runner.run` 断言未调用） |

**native 验收（只有 main 可执行，必须沿用既有前检/启动规则）**

1. 前置：两 WSL 前检 `found=[]`、同 boot、私有 net/ipc/mnt namespace、同一启动器内完成；库 SHA 与 build receipt pin 相等（`37d96512…`），kernel `6.6.87.2-microsoft-standard-WSL2`。
2. 一次 instrumented MIXED run，`--ap-mixed-*`/`--message-*`/`--control-*` 与现行正式候选完全相同，仅新增 `--perf-library/--perf-library-sha256`；`--async-model-evidence` 视现行正式配置而定（perf 与其无冲突：async 证据在子进程内，retire 发生在 perf stop 之后）。
3. 该 run 必须仍然通过**未改动的**门：`rate/` 10 s/60 s 完整滑窗与 2%/1% 预算、100 ms 晚限不 latch、`segment['groups'][-1]['end_tick']==final_authority.tick`、`source_unchanged`、`control_shutdown_clean`、`cleanup_errors` 空、`unowned_ap` 不变、物理 truth 边界、native maps/identity。运行 `tools/audit_mixed_control.py <archive>`（原始审计**容忍** marker）与 `tools/audit_joint_rate.py <archive>`。
4. strict consumer：`--require-kernel-counter --windows` 必须 exit 0、`stream_completeness_proven=true`、`kernel_lost_count=0`、至少一个完整 pair、窗口交集非空；写 `perf-decoded.json`（新文件名）；再跑一次飞行审计以封存它。
5. **正式性**：该 archive **不得**提交为正式 MIXED/PV 证据（B1 落地后 `joint_profile._mixed_proofs` 会按 marker 存在性拒绝，这是预期行为，不是缺陷）。正式 MIXED/PV 证据仍须来自无 marker 的 run。
6. 失败即记录：start/stop/窗口/consumer 任一失败，保留 raw/meta 供诊断，但不得出现"run pass + 捕获不完整"的组合；不得改写已冻结的旧证据。

## 10. 本轮实际执行（read-only）

- `git rev-parse --abbrev-ref HEAD` / `git rev-parse HEAD` / `git status --porcelain` / `git merge-base --is-ancestor f333316e… HEAD`（exit 0）/ `git worktree list`：见 §0、§1。
- `python -B -m unittest validation.test_perf_capture -v` → **Ran 9 tests, OK**。
- `python -B -m unittest validation.test_delivery_entry_contract -v` → **Ran 9 tests, OK**。
- 对 §1 全部对象本地重算 SHA256（开始/中途/结束三次，全部一致）。
- 只读 WSL 文件核对（无进程启动）：库文件存在且 SHA 命中 pin；候选 worktree 的 runner/perf_capture/joint_rate/recorder C/H/consumer/test SHA 核对；候选 `.git` 是 Windows 仓的 worktree（`gitdir: /mnt/c/.../wksim/.git/worktrees/wksim-architecture-acceptance-20260913`）。
- 未执行：native、编译、ROS、SITL、模型、UE、MATLAB、任何后台调度或进程清理。

## 11. 交付与停止

交付即本节与 `audit.json`。本目录写入在 `audit.md`/`audit.json`/`.gitattributes` 三个文件完成后**停止**；未改共享账本、未改任何实现或测试、未提交。
