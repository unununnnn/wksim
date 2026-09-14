# C2 慢组与 Task/飞控启动阶段的相位关联 — 2026-09-13

独立只读分析。未启动 native/ROS/模型/构建，未改运行时/参数/固件，未嵌套委派，未用 Git。
唯一新增：`validation/coordination/c2-phase-correlation-20260913/`（脚本 + 结果）与本文件。
raw：`/root/wksim-release-acceptance-fe3/validation/joint-public-flight-lcgv0yte`。

## 当前结论边界（2026-09-14）

下文的相位表是历史 C2 场的**已证时序、未证因果**。它不改变 1ms / native 屏障 / 无追赶 / 100ms / 完整窗口，也不把不同 boot 单样本升级为修复结论。

- **#83 不重跑**（`1w6dru32` PV 已 CLOSED）。
- **MIXED / G6 / Full 未通过**。
- **99 不满足倍率门**（`oayggl_s` / `RateUnmet`）；停止重复 99。
- **下一 native 场仅主会话执行**。
- `oayggl_s` / `x39qjvkw` / `5lfbcy43` / `rfw9nmbb` 不得受控配对；比较器拒绝不同 boot、不同源码、缺完整窗口、缺失诊断标记、overflow/lost 与时基/身份不一致。
- **类型门**：整数时钟/计数/lost·overflow 必须是非负 `int` 且拒绝 `bool`；GC `end < start`、负时钟、倒序窗口不得进入 `compared`。CPU/代价/比例/持续时间必须有限，拒绝 `NaN`/`Infinity`/字符串/`bool`；CLI 对无效输入写稳定 `unavailable`/`rejected` JSON，不靠 `allow_nan`。
- **结构门**：`result.json`、source map、metadata 必须是 object；数组/空/字符串不得抛 `AttributeError`。
- **pairing 身份**：已知场不得对匿名 run；双方空 `source_sha256` 不得 `controlled_pairing`。四个已知场互配仍拒绝。`causal` 恒 false。

**一句话结论**：两条进程内时钟可**证明同源**（host `CLOCK_MONOTONIC`），因此能把每个慢组放到飞控事件的绝对时间轴上。据此：早期四个慢组落在**窄的启动窗口**（AP 的 GPS/里程计尚未有效、PX4 里程计刚变有效）；164.4 s 附近的三个慢组只落在**很宽的 AP `odom_valid=False` 窗口**内、附近 ±4.7 s 无任何 EKF 复位或模式切换事件；43840 组处于**已解锁/起飞**阶段。以上均为**已证时序、未证因果**：没有任何事件落在慢组窗口之内，且无法排除 I/O 等待或调度。

## 1. 时钟域（均按源码确认，不臆测）

| 量 | 时钟域 | 来源 |
|---|---|---|
| runner wire `wall` / rate `actual_start_ns` | host `CLOCK_MONOTONIC` | `record()`：`wall=time.monotonic()-started`；`JointRate`：`now=time.monotonic_ns` |
| FC 控制事件 `emitted_monotonic_ns` | host `CLOCK_MONOTONIC` | `prometheus_control/node.py` `event()` 用 `time.monotonic_ns()` |
| FC 状态 `published_monotonic_s` | host `CLOCK_MONOTONIC` | `node.py:44 self.wall=time.monotonic` → `node.py:704` |
| `ros_time_ns` / `header.stamp` | 场景时钟 `tick*1e6` ns（ROS 仿真时间） | `scene_clock` 发布 `/clock` |
| `source_clock='fc_boot'` | 飞控自身 boot 计数，**非** host 时钟 | `node.py:702` 标注；仅用于排序 |
| FC `result.json` 的 `wall` | 各自 task 进程相对起点，**两栈不同源** | AP 与 PX4 同相位分别 82.2 s / 5.9 s，故不做跨栈/跨 runner 比较 |

`isolation.py` 只要求私有 net/ipc/mount 命名空间，**不建 time 命名空间** → 各进程共享同一 host `CLOCK_MONOTONIC`。

**同源实证**（`result.json.alignment_check`）：把“仿真 tick→绝对时间”用 rate 组的 `actual_start_ns` 建映射，再与飞控事件自带的仿真参考比对：

| 参考 | 仿真参考 | rate 组映射绝对时间 | 飞控事件单调时间 | 残差 |
|---|---:|---:|---:|---:|
| AP `arming_completed` | 41101 ms | 169.562 s | 169.564 s | −2.1 ms |
| AP `armed` takeover | 41098 ms | 169.554 s | 169.566 s | −12.1 ms |
| AP GUIDED control_state | 47592 ms | 182.554 s | 182.554 s | +0.1 ms |
| PX4 `armed` takeover | 41432 ms | 170.226 s | 170.264 s | −38.0 ms |

残差 ≤38 ms、远小于事件间距 → 时间域可直接换算。

## 2. 慢组在飞控时间轴上的相位

采样飞控 `prometheus.jsonl`（控制节点 `published_monotonic_s`）在每组窗口末的状态。state 用锁步坐标；`simlag` = 组 tick 与该状态 `stamp` 之差（即 Task 所见 ROS 时间的滞后，声明于此）。

| 组(tick) | 窗口(s) | AP：armed/mode/odom/gps/gen | PX4：armed/mode/odom/gps/gen | 最近飞控事件 |
|---:|---|---|---|---|
| 1996 | 91.278–91.288 | False/STABILIZE/**False/0**/0 | False/AUTO.LOITER/**False**/3/3 | PX4 `native_input_rejected` −0.89 s；PX4 yaw 复位 +1.34 s |
| 2764 | 92.817–92.840 | False/STABILIZE/**False/0**/0 | False/AUTO.LOITER/**False**/3/5 | **PX4 yaw 复位 −0.17 s**；AP position 复位 +2.37 s |
| 2772 | 92.848–92.863 | False/STABILIZE/**False/0**/0 | False/AUTO.LOITER/**False**/3/5 | **PX4 yaw 复位 −0.20 s**；AP position 复位 +2.34 s |
| 2928 | 93.168–93.186 | False/STABILIZE/**False/0**/0 | False/AUTO.LOITER/True/3/5 | PX4 yaw 复位 −0.52 s；AP position 复位 +2.02 s |
| 38520 | 164.388–164.399 | False/STABILIZE/**False/6**/3 | False/AUTO.LOITER/True/3/5 | AP 上次复位 −38.03 s；下次 +4.75 s |
| 38528 | 164.408–164.420 | False/STABILIZE/**False/6**/3 | False/AUTO.LOITER/True/3/5 | AP 上次复位 −38.05 s；下次 +4.73 s |
| 38564 | 164.485–164.494 | False/STABILIZE/**False/6**/3 | False/AUTO.LOITER/True/3/5 | AP 上次复位 −38.13 s；下次 +4.66 s |
| 43840 | 175.044–175.056 | **True/GUIDED**/True/6/5 | **True/AUTO.TAKEOFF**/True/3/5 | AP native_ack −5.27 s；yaw 复位 +5.49 s |

状态滞后：`published−received` 约 7–60 ms；状态 `stamp` 相对组 tick 滞后约 1–20 ms。

**优先目标复核**：
- **tick2766 的 AP 长 s→a（15.596 ms）**在 2764 组窗口内（绝对 ≈92.820 s）：AP 处于 `STABILIZE`、未解锁、`odom_valid=False`、`gps_status=0`；PX4 的 yaw 复位观测在其前 0.17 s。
- **tick2930 的 AP 长 s→a（11.134 ms）**在 2928 组窗口内（绝对 ≈93.176 s）：PX4 `odom_valid` 刚在 92.917 s 变 True（前 0.26 s）；AP 仍 `odom_valid=False`。
- **2772 的 pre-sensor 8.320 ms（step@2775→sensor@2776）**在 2772 组窗口内（绝对 ≈92.857 s），同早期启动窗口。
- **38528 的 pre-sensor ≥5.301 ms**在 164.408–164.420 s：AP `gps_status=6` 但 `odom_valid=False`（直到 169.194 s 才变 True，晚 4.73 s）；窗口内/邻近无 EKF 复位或模式切换。

## 3. 可对齐的 EKF/传感器初始化、模式切换事件（绝对单调时间）

**AP**（`arducopter-control.log`，`emitted_monotonic_ns`）：
87.157 `started`；95.207 reset[position]；98.097 reset[yaw]；126.357 reset[home]；169.153 reset[position]；169.213 `native_ack`；169.364 mode→AUTO.LOITER/LOITER；169.393 reset[home] active；169.564 arm；169.566 takeover（`source_boot_ns=41.098 s`）；169.583 external ack；169.773 takeoff ack；180.543 reset[yaw] active；182.554 COMMAND_CONTROL/GUIDED；192.555 起 1 Hz 指令。

**PX4**（`px4-control.log`）：
87.207 `started`；88.297、90.387 `native_input_rejected(unmatched_ack)`；88.757/89.317/89.757 reset[position]；92.627/92.647 reset[yaw]；169.207/169.234 mode→AUTO.LOITER；170.245/170.264 arm；170.271 takeover（`source_boot_ns=41.432 s`）；170.314 takeoff；182.603/182.623 reset[yaw] active；190.274 COMMAND_CONTROL/OFFBOARD；200.276 起 1 Hz 指令。

**状态转折**（`prometheus.jsonl`，绝对 s→仿真 s）：
AP：91.177→1.945 connected；105.917→9.294 gps=1；106.327→9.497 gps=6；**169.194→40.913 odom_valid=True**；169.364 LOITER；169.564 armed；169.764 GUIDED。
PX4：90.477→1.592 connected；**92.917→2.792 odom_valid=True**；170.264 armed；170.664 AUTO.TAKEOFF；190.274 OFFBOARD。

**Task 相位里程碑**（`result.json.phases`，`ros_time_ns`）：AP `joint_public_ready` 40.916 s / `armed` 41.103 s / `task_control_ready` 47.592 s；PX4 `joint_public_ready` 2.803 s / `armed` 41.452 s / `takeoff_reached` 51.452 s。

## 4. 相位基率（防止把共现当因果）

| 相位窗口（仿真 ms） | 覆盖组数/总组数 | 占比 | 含前 8 慢组 |
|---|---:|---:|---:|
| **AP `odom_valid=False`** | 1945–40913 | 9742/18292 | **53.3%** | **7/8** |
| AP `gps_status=0` | 1945–9294 | 1837/18292 | 10.0% | 4/8 |
| **PX4 `odom_valid=False`** | 1592–2792 | 301/18292 | **1.6%** | **3/8** |

`odom_valid=False` 覆盖 53% 的组 → **共现不具判别力**；早期 4 组同时落在更窄的 `gps_status=0`（10%）与 PX4 `odom_valid=False`（1.6%）窗口内，是较紧的共现，但 301 个组里仍有 3 个慢组、其余 298 个非慢。

## 5. 已证时序 / 未证因果

**已证（时序）**：
- runner 与飞控控制进程共享 host `CLOCK_MONOTONIC`（来源 + 残差 ≤38 ms）。
- 8 个慢组的绝对窗口及其在该窗口内的飞控相位/模式/有效性状态。
- 早期 4 个慢组处于 AP GPS 无效、PX4 里程计刚有效的启动窗口；PX4 yaw 复位观测在 2764/2772 组前 0.17–0.20 s、在 2928 组前 0.52 s；AP position 复位在其后 2.0–2.4 s。
- 164.4 s 三个慢组与 43840 组的相位（前者 AP `odom_valid=False`，后者已解锁/起飞）。

**未证（因果）**：
- **没有任何飞控事件落在任一慢组窗口之内**（最小间距 0.17 s；164.4 s 组 ≥4.7 s）→ 只有邻接，没有窗口内重合。
- `odom_valid=False` 基率 53%，不能据此解释慢组；PX4 `odom_valid=False` 窗口较窄但仍含 298 个非慢组。
- **不能仅凭“初始化文字”排除 I/O 与调度**：本场无 CPU/队列探针（wire 与飞控流均无 CPU 采样），无法区分“在运行”与“在等待”；pre-sensor 段仍可能由记录/序列化/I-O 等待/调度延迟构成，不作排他归因。

## 6. 缺口（没有时间对齐证据的地方，如实列出）

1. **164.4 s 三组**：窗口 ±4.7 s 内无任何 `native_reset_observed` 或模式切换事件；最近事件在 38 s 前 / 4.7 s 后。无法把其 pre-sensor 大段与某次初始化/模式事件在时间上绑定。
2. **`fc.log`（AP/PX4）无时间戳**，只有 SITL stdout 行；**不使用其行顺序假造时间戳**，故不可对齐。
3. **EKF 复位的“发生时刻”没有原生单调时间戳**：`native_reset_observed` 是控制节点**收到状态后**打的时间，含传输与处理滞后；缺少飞控侧的单调时间。
4. **无 CPU/runqueue/节流采样** → running vs waiting 不可分。
5. 早期窗口较窄（10%/1.6%）但仍非唯一解释；需要在这 301 个（PX4 无效窗口）组内做逐组对照，才能判断是否有判别力。

## 7. 确切下一测量 / 源码问题

**源码问题（只读）**：
- Q1：AP `local_state` 的 `odom_valid` 究竟由哪个条件置位（EKF 健康？GPS？home？）？`odom_valid=False` 时 AP 桥/监督者是否做额外工作（重算、分配、重订阅）？
- Q2：`yaw_reset_ms / position_ne_reset_ms / position_down_reset_ms` 的变化对应飞控的哪个 EKF 复位标志？发生复位时 AP 桥是否在接收路径上做重初始化（可能阻塞监督者）？
- Q3：pre-sensor 段（group_start→首条 sensor）中，`receive_workers`（模型 RPC）占多少、监督者自身开销占多少？——需要单独括测。
- Q4：PX4 `odom_valid` False→True（仿真 2.792 s）或 yaw 复位是否触发 DDS 重建/重订阅，从而可能拖累 I/O？

**下一测量（不需要现在重跑，仅列出）**：
- M1：在有界场次开启 `WKSIM_JOINT_CPU_TIMING=1`，取 `diagnostic_step_cpu_timing`（`health_and_models`/`encode_send`/`native_inputs`）与 `diagnostic_native_input_timing`，把"运行/等待"按阶段分开。
- M2：监督者侧单独括测 `receive_workers`（模型 RPC），以拆解 pre-sensor 段。
- M3：慢组窗口期间的主机 CPU/runqueue 与 cgroup 节流采样。
- M4：在 AP/PX4 复位事件上补**飞控侧单调时间戳**（现仅控制节点收报时刻）。

## 8. 输入与产物 SHA256

| 文件 | SHA256 |
|---|---|
| `joint-public-flight-lcgv0yte/rate.jsonl` | `a1fe39d4aed3450e87975e1717f70c641427429ca6b628651b415f90e5afb13f` |
| `joint-public-flight-lcgv0yte/arducopter-control.log` | `e7ec7158959a1faa1b49d37a74fe1369de1b84851d04a97d112c314ac6906f05` |
| `joint-public-flight-lcgv0yte/px4-control.log` | `0b220f5999322b354bbfd985f0fc7e9a94daf76a27532411f8a2b51f232f08ae` |
| `joint-public-flight-lcgv0yte/arducopter/result.json` | `67b148f02cb684ce784651905e151e8580c9c316331396d875ab2b8112485504` |
| `joint-public-flight-lcgv0yte/px4/result.json` | `aaf63f972735ae93b2f4af6816ab0fd64a87a219d36f28350a9c50aa4040dc7e` |
| `joint-public-flight-lcgv0yte/arducopter/prometheus.jsonl` | `1831af277e9477b65e821a840be6d339ddb915b6cfe8fdb51009d2d11f70b44b` |
| `joint-public-flight-lcgv0yte/px4/prometheus.jsonl` | `f565844f0aeca5716f76770633357ed526ede006a60fc97ba678ae4f357901e6` |
| `joint-public-flight-lcgv0yte/arducopter-fc.log` | `55c6cbf861934d0890a4c962495a6b27f7f7164039b6568edfaaeb49751fb8d9` |
| `joint-public-flight-lcgv0yte/px4-fc.log` | `7a37bff6422e36952511cf81a60ab6579edd8359e5ec6a75657384137a50a0c1` |
| 本报告脚本 `analyze_phase_correlation.py` | `aa49c7fe829a0176129aedfcb9ae2d349d44910d976a5ba3769c7a5f2ba04909` |
| 本报告结果 `result.json` | `0425dc670457aef84dc6713677164a58bb05ebf7048d09662bf10577f906ae8d` |

**对上一报告 `c2-gap-bounds-20260913.md` 的来源更正**（已在该文件加一条说明，其余冻结结果未改）：此前所称“分析器 SHA 不一致”有歧义——`14ed9d64…` 只是 WSL 私有旧副本；真正产生 `main-rate-analysis.json` 的是主 Windows 仓库 `tools/analyze_joint_rate_intervals.py`，SHA `1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7`，与记录一致，**来源链明确，并非未知执行源**。

## 9. 复现

```
python3 -u validation/coordination/c2-phase-correlation-20260913/analyze_phase_correlation.py \
  --raw /root/wksim-release-acceptance-fe3/validation/joint-public-flight-lcgv0yte \
  --output validation/coordination/c2-phase-correlation-20260913/result.json
```

完整逐组邻接事件、状态采样、状态转折、相位基率与限界见 `result.json`。
