# C1 独立代码审查（manager GC freeze 候选）— 2026-09-12

独立审查，非实现方。只读源码 + 纯 mock 测试；未运行 native / 编译 / ROS / 模型加载。
本报告不采用原线程旧设计报告；所有权结论以本轮实测源码为准。

## 1. 审核对象与版本（含 SHA）

- 执行源码根：Ubuntu-22.04 `/root/wksim-release-acceptance-fe3`（经 wsl 只读读取）
- 仓库 HEAD：`d71febbfa45fc9df93cd12edb7e72721f94414eb`（2026-09-12 20:23 +0900）
- 工作区：` M tools/run_joint_flight.py`；`tools/manager_gc_candidate.py`、`validation/test_manager_gc_candidate.py` 为未跟踪新文件。
- 执行 runner 仅为 `tools/run_joint_flight.py`；Windows `Simulator/wksim_runtime/joint_runtime.py` 未作为执行 runner 评估。
- 审核时刻：`2026-09-12T13:37:39Z`（WSL 22:37 +09:00）。

实际审核版本 SHA256：

| 文件 | SHA256 | size | mtime(+09:00) |
|---|---|---|---|
| tools/run_joint_flight.py | `fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246` | 78247 | 2026-09-12 22:33:39 |
| tools/manager_gc_candidate.py | `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66` | 11254 | 2026-09-12 22:33:39 |
| validation/test_manager_gc_candidate.py | `637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad` | 15726 | 2026-09-12 22:34:14 |
| validation/test_gc_candidate_entry.py | **不存在**（审核期间 `ls` 仍 No such file） | — | — |

`validation/test_gc_candidate_entry.py` 缺失：该入口级覆盖无法审核（见 D2）。

## 2. 结论总览

| # | 判据 | 结论 |
|---|---|---|
| 1 | prepare 在全部 Task 初始化/tick0 校验后、physics.connect/首 anchor 前 | 有边界的通过（O1） |
| 2 | 成功 freeze 立即保存所有权，取样异常仍能 unfreeze | 通过（O3 残余窗口） |
| 3 | prepare 重查 enabled/threshold/freeze_count，拒绝他人图 | 通过（D1 为生命周期后段未覆盖） |
| 4 | 全部异常路径 native cleanup / ExitStack 回调去除后仍 restore，无关流写日志 | 有边界的通过（O2） |
| 5 | default 完全不接触 GC，1ms/4tick/100ms/no-catchup 门保留 | 通过 |

真实缺陷：**D1（所有权，条件性）、D2（缺失入口测试）**。其余为边界/加固观察 O1–O4。
所有权问题按用户要求返给 A。

## 3. 判据逐项

### 判据 1 — prepare 时序（通过，有边界）

`tools/run_joint_flight.py`：
- `manager_gc.arm()` — L468（进入外层 `try` 后，L466）。
- 全部 Task 初始化/tick0 校验 — L879–L908（`if candidate:` 块）：等待两个 stack 的 `initialized.json`（L881–885）、校验 version/run_id/scene_epoch/uav_id/task_profile/`ros_time_ns==0`（L887–892）、`receive_worker` 快照（L901–903）、`if clock.tick!=0 … raise`（L904）、`record_native_maps('running')`（L906）。
- `manager_gc.prepare(monotonic_ns=…, clock_tick=clock.tick)` — L909–910。
- `physics.connect()` — L911。
- 首 anchor：`rate.reanchor(...)` — L918（仅在 L937 主循环首次经 `advance()` 触发）。

文本顺序 `arm(468) < init/tick0(879–908) < prepare(909) < connect(911) < reanchor(918)` 成立，且 `prepare` 与 init 块同缩进层级（均在 `with ExitStack` 内、`if candidate` 之后）。CLI 入口以 L1186 强制 `--manager-gc-freeze` 仅 PV/MIXED，而 `candidate = pv or mixed`（L388），故真实 CLI 路径下 init/tick0 块必然先于 prepare。判为通过，附 O1。

### 判据 2 — 成功后立即保存所有权；取样异常仍能 unfreeze（通过）

`tools/manager_gc_candidate.py`：
- `collect()` — L198；`freeze()` — L200。
- **`self._we_froze = True` — L204，紧接 `freeze()` 返回、先于任何可抛异常的取样**。
- 风险取样 `self._snapshot("after")` — L205（`get_freeze_count`/`get_count` 均未加 try），可抛。
- `restore()`：`if not self._we_froze: … noop_not_owner`（L223–228），否则 `unfreeze()`（L233）。

`prepare` 在 L205 抛异常时，`_prepared` 仍为 False 但 `_we_froze=True`，runner finally 的 `restore()` 会真正解冻。测试 `test_freeze_ownership_survives_a_failing_post_snapshot`（validation/test_manager_gc_candidate.py:153–169）断言 `mutators == ["collect","freeze"]`、`freeze_count==7`、`froze_own_graph==True`，随后 restore 得到 `[…, "unfreeze"]`、`freeze_count==0`，已实测通过。判为通过，附 O3。

### 判据 3 — prepare 重查外部漂移，拒绝他人图（通过；后段见 D1）

`_revalidate()` — L151–183：重读 `isenabled()`（L160）、`get_freeze_count()`（L161）、`get_threshold()`（L162），写入 `_prepare_check`（L164），与 `arm()` 记录的 `_original`（L128–134）比较：
- 收集器被禁用 → 拒绝（L166–170）；
- `freeze_count` 非零（他人永久代出现）→ 拒绝，不 un freeze 他人（L171–175）；
- thresholds 改变 → 拒绝（L176–182）。

以上任一拒绝都发生在 `collect()/freeze()` 之前，故 `mutators()` 保持为空。`arm()` 本身也在预置状态非己时拒绝（L135–144）。对应测试 `test_external_freeze_between_arm_and_prepare_is_refused`、`test_external_disable_…`、`test_external_threshold_change_…`、`test_preexisting_freeze_is_refused_and_foreign_state_is_not_released`（validation/test_manager_gc_candidate.py:173–223）全部通过。

**D1（见第 4 节）**：重查只覆盖 `arm→prepare` 窗口；`prepare→restore` 窗口内若出现第二次 `freeze()`，`restore()` 的全局 `unfreeze()` 不会区分归属。

### 判据 4 — 异常路径 native cleanup / ExitStack 去除 GC 回调后仍 restore（有边界的通过）

`tools/run_joint_flight.py`：
- 外层 `finally`（L1048）把原 cleanup 整体包进 `try`（L1049–1060），并在其内层 `finally`（L1061）中调用 `manager_gc.restore()`（L1064–1069）。
- 因此即便 `cleanup_children(...)`（L1050，含 `retire_model_workers` 与 `stop_children`）抛异常，`restore()` 仍执行；`restore()` 自身异常被捕获记入 `manager_gc_candidate_error`（L1067–1068），随后 `report()` 与写盘（L1069–1073）照常。
- `with ExitStack() as resources:`（L791–1040）在异常时先于 L1041 的 `except` 与 L1048 的 `finally` 退出，故全部 ExitStack 回调（`rclpy.shutdown` L792、`destroy_node` L794、`publisher.close` L796、`pause_probe.close` L800/811、rate/clock/wire 日志 L801/812/813）都已运行/关闭，restore 才执行。
- GC 未注册为 ExitStack 回调：源码无 `resources.callback(manager_gc`/`enter_context(manager_gc`，测试 `test_gc_work_is_not_registered_as_an_exitstack_callback`（同文件 L370–373）通过。
- 无关流写日志：`restore()` 后仅 `save(live/'manager-gc-candidate.json', …)`（L1071）写一个独立新文件，不触碰已关闭的 wire/rate/clock 流；随后 L1126 `copytree(live,archive)` 会把它带入归档。判为通过，附 O2。

异常路径枚举：arm 之后任何 in-process 异常（含 `except BaseException` L1043、`PauseProbeComplete` L1041、以及 except 处理器自身抛错）都会经过 L1048 外层 finally 与 L1061 内层 finally，restore 必然执行；`arm()` 位于 L468（L466 `try` 内），arm 自身失败也会走 finally（此时 `_we_froze=False`，noop）。仅 SIGKILL/`os._exit` 不在覆盖内。

### 判据 5 — default 不接触 GC，原门保留（通过）

- default 下 `manager_gc` 恒为 `None`：构造受 `getattr(args,'manager_gc_freeze',False)`（L461）约束；`arm`（L467）、`prepare`（L909）、`restore`（L1064）均以 `manager_gc is not None` 守卫；`manager_gc_candidate.py` 仅在 flag 为真时被 import（L462），默认进程根本不 import 该模块，也从不读写 `gc` 状态。
- 未提交 diff（`git diff tools/run_joint_flight.py`）仅落在 L452–461、L909–911、L1046–1073、L1152–1158、L1183–1188 五处 GC 相关 hunk，未触碰 `advance()`/主循环。
- 原门保留且所在文件未被修改（`git status` 对这些文件为空）：
  - 1 ms 物理步 pacing：`run_joint_flight.py:929`；
  - 4-tick 单锚/分组：`run_joint_flight.py:916,921,934,946,1013`；
  - 100 ms 严格迟限：`Simulator/wksim_runtime/joint_rate.py:6` `LATE_LIMIT_NS=100_000_000`、`:83` `if lateness>LATE_LIMIT_NS`；
  - no-catch-up：`joint_rate.py` 以 `max(0,now-ideal)` 计算迟量并在超限 fail-closed，无补偿/追赶逻辑（文件未改）。
- 额外完整性：flag 时 `tools/manager_gc_candidate.py` 被纳入 `source_sha256`（L456），运行尾 L1075 重算 `source_unchanged`，改文件会导致 run 判负。

## 4. 真实缺陷

### D1 — restore() 的全局 unfreeze 不校验归属（所有权；条件性真实缺陷）

- 位置：`tools/manager_gc_candidate.py:232-244`（`restore()`），报告字段 `235-240`。
- 事实：`restore()` 读 `count_before = get_freeze_count()` 后直接 `gc.unfreeze()`；CPython 的 `unfreeze()` 会清空**整个**永久代（`freeze_count→0`），并非只释放本对象冻结的图。随后 `restored_to_original` 仅比较 `count_after == self._before["freeze_count"]`（=0==0），恒为真。
- 影响：若在 `prepare()` 之后、`restore()` 之前有第二个 `gc.freeze()`（他人图），`restore()` 会把他人永久代一并释放到 0，并仍上报 `restored_to_original=True`，与模块自述边界 “We never unfreeze somebody else's object graph”（`manager_gc_candidate.py:25-27`）矛盾。
- 可达性：本轮全仓检索，manager 进程内除 `manager_gc_candidate.py` 外无任何 `gc.freeze/unfreeze/disable/set_threshold` 调用者（`grep -rn "gc\.(freeze|unfreeze|disable|set_threshold|enable)"` 排除候选与测试后为空），唯一 import 方为 `run_joint_flight.py`。故当前 runner 内**不可达**，判为潜在/复用风险，非当前运行缺陷。
- 归属：按用户要求，所有权问题返给 A。建议 A 在 `restore()` 前校验 `count_before == self._after["freeze_count"]`（即本对象冻结量），不符则拒绝 `unfreeze()` 并上报，而不是无条件全量解冻。

### D2 — 缺少 validation/test_gc_candidate_entry.py（交付缺口）

- 位置：`/root/wksim-release-acceptance-fe3/validation/test_gc_candidate_entry.py`（不存在；审核期间复核仍缺失，OMP 可能仍在编写）。
- 影响：入口级（runner 端到端接线/CLI 门）覆盖无法审核；本轮判据 1/5 的 runner 侧仅依赖 `test_manager_gc_candidate.py` 的 `RunnerWiringTests`（文本断言）与人工阅读。交付完整性未达“含入口测试”的预期。
- 处理：文件出现后需对其重算 SHA 并补充入口级审查，本报告结论不覆盖之。

## 5. 边界与加固观察（非阻断）

- **O1 — 程序化入口的防御缺口**：`run_joint_flight.py:461` 用 `getattr(...,False)` 取 flag，L909 仅以 `manager_gc is not None` 守卫 prepare；若以合成 namespace 直接调用 `run()`（绕过 L1186 parser 门）且 `manager_gc_freeze=True, task_profile='position'`，则 `candidate=False`，L879–908 的 init/tick0 块被跳过，prepare 将在无 tick0 校验下执行。CLI 真实路径不受影响。属纵深防御。
- **O2 — restore 失败不置 run 失败**：`run_joint_flight.py:1064-1069` 仅记 `manager_gc_candidate_error`，不强制 `status='failed'`。因该候选非性能结论，flight 状态可保持 pass 而 unfreeze 失败；审计应以 `restored=False`/`manager_gc_candidate_error` 为 disqualifier。建议显式降级。
- **O3 — freeze 与置位之间的信号窗口**：`manager_gc_candidate.py:200-204`，`gc.freeze()` 返回到 `self._we_froze=True` 之间若投递 SIGTERM（runner 在 L380 注册了将其转为 `InterruptedError` 的处理器）/KeyboardInterrupt，则冻结发生但所有权未登记，`restore()` 走 noop，永久代在进程余下生命周期内未释放。窗口极窄、进程退出即回收；属残余风险。
- **O4 — RunnerWiringTests 为文本断言**：`validation/test_manager_gc_candidate.py:343-381` 以 `source.index(...)` 校验源码文本顺序，不执行 runner 分支，不能证明运行期可达性。作为顺序证据可接受，但与行为证明不等价。

## 6. 测试证据（仅纯 mock，符合限制）

在审核版本上运行 `python3 validation/test_manager_gc_candidate.py`：**23/23 OK**（`Ran 23 tests in 0.017s`）。覆盖：
- 默认/禁用路径不读不写 GC（`test_disabled_option_never_touches_the_collector`，断言 `gc.calls==[]`）；
- collect→freeze 顺序与 arm 不改 GC（L113–127）；
- freeze 后置位先于风险取样（L153–169）；
- 预置 freeze/禁用收集器/阈值漂移/arm→prepare 外部漂移的拒绝且不触碰他人状态（L173–223）；
- collect 失败不 freeze、restore 为 noop（L235–247）；
- 独立解释器真实 `gc` API 往返（L296–332，`restored_to_original` 为真）；
- runner 接线文本断言（L335–381）。

未执行：native、编译、ROS、SITL、模型加载、`Simulator/wksim_runtime/joint_runtime.py`。

## 7. 证据边界（明确非结论）

- 本轮**不**验证 freeze-only 假说的性能有效性；不 disable、不改 threshold。纯 mock 通过不等于性能通过；该候选 `classification=candidate_not_performance_pass`、`performance_pass=False`（`manager_gc_candidate.py:44,252-253`）。
- 背景观察 `7bdfxkb` tick107572 的 GC CPU 24.33ms 嵌于 manager PX4 等待窗口，仅为上下文，本审查不能据此宣称归因或收益。
- 判据 1/5 的 runner 侧依赖源码顺序 + 文本断言 + 人工阅读；无端到端执行证据。

## 8. 末尾 SHA 重算（确认实际审核版本）

审核完成时对执行源重算（见第 1 节表）。重算结果与本次实际读取/审查的字节版本一致，未发现审核过程中被 A 改写：

```
REVIEW_COMMIT d71febbfa45fc9df93cd12edb7e72721f94414eb
fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246  tools/run_joint_flight.py
cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66  tools/manager_gc_candidate.py
637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad  validation/test_manager_gc_candidate.py
(test_gc_candidate_entry.py: absent)
```

- 若 A 末轮修复发生在上述 SHA 之后，则本报告**不覆盖**该差异；须以新 SHA 复核 D1/D2 与判据 1–5。
- 本报告文件自身 SHA256 见交付回执（写入后计算）。
