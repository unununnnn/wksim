# DS-B · 独立启动开销调查（修订 v2）—— 已证 / 未排除 / 仍需测量

席位：DS-B（独立）。上一版为 v1，本版按评审意见**逐条撤回并重写**结论层，只保留有代码或数据支撑的部分。
对象：`/root/wksim-release-acceptance-fe3` 的
`joint-public-flight-vwen35gc`（PV+C1，**无**探针，anchor tick 44，21763 组，`RateUnmet` @ tick 87096，lateness 100485315 ns）、
`joint-public-flight-ztdsk269`（PV+C1，**带**两探针，anchor tick 40，24146 组，@ tick 96624，lateness 100129488 ns）、
对照 `joint-public-flight-7bdfxkb_`（PV 基线，anchor tick 40，27434 组）。

只读：未编辑 runner / `Simulator/wksim_core` / `Simulator/wksim_runtime` / A 的分析器 / 旧 B 的文件；未跑 native/ROS/SITL；未编译；未加载模型；未嵌套代理；未提交 Git。

**终态 SHA（本轮实际读取的源，未改动）**

| 文件 | sha256 |
|---|---|
| `Simulator/wksim_core/joint.py` | `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50` |
| `Simulator/wksim_core/worker.py` | `0becd1f3214b53c6169fb61ae010a969fb57a4ccbe26fb3ed3c3652c26ef7fab` |
| `Simulator/wksim_runtime/joint_rate.py` | `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4` |
| `tools/run_joint_flight.py` | `fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246` |
| `tools/analyze_joint_rate_intervals.py`（fe3 私有副本，**非**已提交工具） | `14ed9d64bb0daf0fb2ef9f4e21028a4ec164bb1255f98701542b59a68d2538a8` |
| `validation/joint-public-flight-ztdsk269/rate.jsonl` | `9c79867222989eac6f627dafa115a6c5f214a418412be2aec89f3f28a0f9cb92` |
| `validation/joint-public-flight-vwen35gc/rate.jsonl` | `e8c1c9e343dec468cdfa7de7708a9f499bb2dfffa54185b6c56695944236e0d8` |
| `validation/joint-public-flight-7bdfxkb_/rate.jsonl` | `484016e746bfad78ef5d46f0d85d19e1761ebea30fea2d22e63649ea57e07d0b` |
| `validation/joint-public-flight-ztdsk269/joint-wire.jsonl` | `843edc94be6e8930e4960157ad4ccb909bc082fbc80d6f726061a542d12f4841` |
| `validation/joint-public-flight-vwen35gc/joint-wire.jsonl` | `6a6f9498a0908d8474e22a03b4ddb04e8181e80f892de2fc19911359e8bed631` |
| `validation/joint-public-flight-7bdfxkb_/joint-wire.jsonl` | `9035a4af48d8fba172cfbfe3868319cd87f9740c1005306f19462bfbdf98cf0e` |

（后两个 `rate.jsonl` 与主会话已记录值一致；`analyze_joint_rate_intervals.py` 的 fe3 副本已过期，v3 的 `phase_partition` 只在已提交 `c3ba9de8…` 中，本报告只引用其**已有输出值**，未运行任何分析器。）

---

## 0. v1 的五项撤回（评审有效）

| # | v1 的错误说法 | 修正后的准确说法 |
|---|---|---|
| 1 | 「`initialized.json` + `ros_time_ns==0` 证明 Control/task 已就绪、所有懒初始化已结束」 | **不能推出**。见 §2：该门只证明 **Task 侧具名订阅图**（`setup`/`command` 各恰好 2 个 endpoint，名字与 GID 校验）就绪且时钟为 0；它**不**覆盖 Control 进程内部的后台活动。 |
| 2 | 「tick 0 的 `initial` 请求取到 120 值首态」 | **该请求在这两场根本没发生**。见 §2：`receive_worker(...,snapshot=True)` 是**只读快照**，响应 `state=None`；120 值只存在于 `JointPhysics.initialize_states` 走的 `initial_request` 路径，而 runner 从不调用它。 |
| 3 | 「wire 条数/字节逐位相同 ⇒ 排除日志刷盘、I/O 阻塞」 | **不成立**。见 §4：记录条数只说明**到达了哪些 record 调用点**；写盘发生在缓冲刷新/关闭时刻，wire 的 `wall` 是**构造记录时**的墙钟，二者不同时刻。排除需要每阶段 CPU/阻塞测量。 |
| 4 | 「`final_spin_other` 900–960 µs ⇒ 释放环少测了一段」 | **不成立**。见 §3：该量与 `remaining<=1ms` 分支（睡眠后残余 spun 掉）**完全相容**，是设计的产物；探针的 `observed_elapsed` 已闭合 entry→terminal 整段。 |
| 5 | 「两场尖峰不同 tick ⇒ 排除宿主周期事件」 | **不成立**。见 §4：两场开始时间不同、时间域未建立映射，缺同期证据≠无积压/无周期源。 |

「250 区间 = 头 2 秒」也已撤回（§3 末）：250 只是**本报告选的任意测量块**，与已提交 `phase_partition` 的
`steady_after` 真实分区（**ztdsk269 early 246 / vwen35gc early 248 / 基线 early 249**）**不是同一口径**，不得混称为「逐位吻合」。

---

## 1. 已证（有代码位置或已存 raw 支撑）

### 1.1 rate 计时从「已跑起来」的阶段开始

`rate.reanchor(clock.tick,'synchronized_boundary')` 只在
`tools/run_joint_flight.py:916-919` 的 `clock.tick%4==0 and clock.synchronized and clock.phase=='running'` 下触发；
`clock.synchronized` 由 `Simulator/wksim_runtime/scene_clock.py:63-72` 的 `barrier(..., synchronized=True)` 置真，
而该参数要求 PX4 已发出 stamp 等于当前 tick 的 `HIL_ACTUATOR_CONTROLS`
（`Simulator/wksim_core/joint.py:157-170, 256-267`）。
**已证事实**：anchor 组开始时，AP 与 PX4 的逐 tick 输入闭环已经在工作。

### 1.2 可核对的初始化调用点（相对 anchor 的先后）

| 阶段 | 代码位置 | 调用时刻 | 相对 anchor |
|---|---|---|---|
| AP UDP 套接字、监听 TCP、`common.MAVLink` 取用、`gc.callbacks` 安装 | `joint.py:32-67` | `run_joint_flight.py:818` 构造 `JointPhysics` | 之前 |
| wire / clock / rate 三个 writer（65536 缓冲） | `run_joint_flight.py:801, 812, 813` | 进入循环前 | 之前 |
| `record('connected')`、`wait_ap` 首帧、`decode_servos` 首次 | `joint.py:102-129`（经 `physics.connect()`，`run_joint_flight.py:911`） | wire 首条 `actuator`/`connected` 的 `tick` 字段为 **0** | 之前 |
| PX4 startup 4 ms 轮询窗 | `joint.py:143-149`（`startup = self.px_time is None`） | wire 首条 `barrier` @ tick **4** | 之前 |
| 首个 `HIL_SENSOR` 编码/发送 | `joint.py:202-206` | `tick%4==0`，即 tick 4 起 | 之前 |
| model worker 的 `Model(library)`（`CDLL`/`wk_model_create`/argtypes/输出缓冲） | `worker.py:198` → `model.py:111-136` | worker 进程启动 | 之前 |
| worker 证据 writer | `worker.py:166-170` | `Model` 之前 | 之前 |
| 首个 worker RPC（含 `os.set_blocking`、`select` 读写环、帧校验） | `worker.py:297-374` | 首个模型步，`tick` 1 | 之前 |

以上是**关于调用顺序的已证事实**。它们**不足以**推出「anchor 之后不存在任何首次代价」——见 §5。

### 1.3 逐 tick 的 manager 侧工作账（来自已提交探针，仅 ztdsk269）

`rate_timing_probe` 每组一条**闭合**记录：`observed_elapsed = entry_to_initial_health + loop_health + sleep_elapsed + final_spin_other`，
另有 `release_excess = terminal − earliest`。对该场全部 24147 组求和：**Σ `release_excess` = 100.129 ms**，
与被记录的 latch `lateness 100129488` 一致；**手算** creep/work_over/release_excess = 99.688 / 33.372 / 66.315 ms，
与已记录值一致（vwen35gc 99.637 / 34.869 / 64.768；基线 99.718 / 25.704 / 74.014）。这是**已证**的算术事实。

### 1.4 wire 事件序列（单一时间域内自洽）

同一字段内，wire 的 `tick` 与 `wall`（相对 runner `started` 的秒）给出可靠序列：
`connected`/`actuator` 自 `tick 0`、`sensor`/`step` 自 `tick 1`、`barrier` 自 `tick 4`（每 4 tick 一次）、`gps` 自 `tick 100`（每 100 tick）。
两场都是这个序列。**仅此而已**；跨域映射见 §4。

---

## 2. 「Control 就绪」与「首态 120 值」的准确语义（v1 错误来源）

- **`initialized.json` 的真实含义**：由 `tools/run_joint_flight.py:296-305` 在
  `while not task.request_graph_ready()` 之后写；`request_graph_ready`（`tools/pv_trajectory_task.py:40-52`）
  校验的是 **`setup_pub`/`command_pub` 在 `v2/setup`、`v2/command` 上的订阅者恰为 2 个**，且
  `{node_name} == {'wksim_joint_<stack>_control', recorder_name}`、命名空间为 `/`、两个 endpoint GID 非空且互异。
  它**只**证明这套**具名订阅图**已被 Control 节点与实验记录节点建立，且 `ros_time_ns==0`。
  **不证明** Control 进程内部的后台活动（执行器/timer/callback 首次运行、分配器/缓存预热、DDS 线程）已经结束。
- **runner 在 tick 0 实际发的请求**：`run_joint_flight.py:901-903`
  `receive_worker(worker, dict(version=1, epoch=..., snapshot=True), ...)`。
  该形状走 `worker.py:88-92` 的**只读快照**分支（`step_request` 返回 `None`），响应是
  `dict(version=1, epoch=..., tick=model.ticks, state=None)`，由 `worker.py:151-152` 单独放行 `tick==0 and state is None`。
- **120 值首态并不在这两场发生**：取值路径是 `joint.py:69-93` 的 `initialize_states` ← `worker.py:109-125` 的
  `initial_request` ← `worker.py:211-221` 调 `model.initial_state()` / `model.py:198-217`。
  代码库里 `initialize_states` 的调用者只有 `Simulator/wksim_runtime/joint_runtime.py:705` 与
  `tools/probe_joint_terrain_feedback.py:716`；`tools/run_joint_flight.py`、`tools/joint_pause_probe.py`、
  `tools/run-joint-flight.sh` 中**出现次数为 0**，runner 也不 import `joint_runtime`。
  佐证：两场归档里**没有** `*-truth.jsonl.initial.jsonl`（该 sidecar 只在 `worker.py:238-245` 的 `initial` 分支写）。

**结论（本节）**：tick 0 的请求是「不写、不步进、state 为 None」的只读快照；首态 120 值路径在本轮两场未被执行。
v1 在这一点上是错的。

---

## 3. `final_spin_other` 与释放环：为什么 v1 的「少测」判断不成立

`Simulator/wksim_runtime/joint_rate.py:89-130`（`begin_group`）：
`earliest` 确定后，`while True` 里 `now = self.now()` 并计算 `remaining = earliest - now`：

- `remaining <= 1_000_000` → **纯 spin** `while now < earliest: now = self.now()`，然后 `check`、`break`；
- 否则 → `remaining > 1ms` 时 `self.sleep(min((remaining-1_000_000)/1e9, .002))`；
- 注释明确：「Final 1ms uses only the monotonic clock; it adds no health, sleep, or record work before the release edge」。

**准确的时间归属**（按代码，不靠推断）：

| 量 | 覆盖区间 | 是否含 `rate_group_start` 记录写入 |
|---|---|---|
| 探针 `observed_elapsed` | probe **entry**（`begin_group` 第一条语句之前）→ **terminal**（= `actual_start_ns`，spin 退出时的 `now`） | **否**（记录写在其后） |
| `final_spin_other` | `observed − entry_to_initial_health − loop_health − sleep_elapsed` = 「spin 墙钟 + 未被分类器包住的耗时」 | 否 |
| `release_excess` | `terminal − earliest`（与是否睡眠无关，比 `final_spin_other` 更稳） | 否 |
| 本报告 §1.3 的组工作 `work_ns` | `actual_start_ns` → **配对** `rate_group_end.actual_end_ns` | **是**（起点记录之后到终点） |

由于「最后一次 sleep 只被批准在 `remaining > 1 ms` 时发出，且请求 `remaining − 1 ms`」，**spin 的期望长度就是约 1 ms**；
`min(..., .002)` 的 2 ms 上限、以及 `sleep_max_overshoot_ns`（两组实测均值 93 µs（前 250 组）/ 49.5 µs（5000–6000 组））
都说明睡眠可以越过部分余量。因此实测的 `final_spin_other` ≈ **900–960 µs/组**
（5000–6000 组区间均值 955.1 µs）**与代码设计完全相容**，不能作为「少测一段」的证据。
v1 的该判断撤回。

可保留的**已证**部分：`release_excess` 是比 `final_spin_other` 更可靠的释放环指标
（探针全场合计 100.129 ms，与 latch 一致）；而 1.4 节所述「起点记录写入属于下一组的 `work_ns`」是
**按代码读出的归属**，不是测得的时间缺口。

**关于「250 区间」**：0.5× 下 4 tick = 8 ms 是**理想墙钟**；250 区间只是本报告选的块。
已提交 `phase_partition` 的真实 `steady_after` 分区是 early **246（ztdsk269）/ 248（vwen35gc）/ 249（基线）**，
本报告的 250 块与之**不同口径**，不得混称吻合。

---

## 4. 未排除（v1 曾误称已排除）

1. **日志/flush 与 I/O 阻塞**：wire 记录条数与字节数只反映到达了哪些 record 调用点并序列化了多少字节；
   `wire.write(...)` 是 65536 缓冲的文件对象写入，**真正落盘发生在缓冲满或 close 时**，`wall` 字段是**构造记录时**读的
   `time.monotonic()`（`run_joint_flight.py:814-816`）。因此「尖峰组与相邻组条数/字节相同」**不能**排除
   写盘阻塞、内核页缓存的间歇性抖动、或同一进程内线程竞争。要排除需要每段的阻塞/CPU 测量。
2. **解码与序列化 CPU 波动**：字节数相同不代表解码代价相同（丢包重传、`parse_buffer` 分片、JSON 编码热点等）。
   唯一可用的证据是 `diagnostic_step_cpu_timing` 的 `wall/cpu` 分列，但它**是条件采样**
   （`wall_end−wall_start > 2 ms` 或 `tick%250==0`，`joint.py:215`），**不是普查**；
   在本报告关注的窗口里 ztdsk269 只留下 22 条（tick 40–1200），**不足以**做排除。
3. **宿主周期事件**：两场的 rate 绝对单调值相差约 6.47×10¹¹ ns（`1218406571925` vs `571735907115`），
   但**本轮没有建立两场时间域的共同映射**（也没有共同的采样标记），因此「尖峰落在不同 tick」**不能**排除
   宿主周期性因素；只能说**本轮证据不足以判定**。要判定需要同宿主的共同时间参考或专门的周期采样证据。
4. **`health()` 在热路径的代价**：`rate.begin_group(clock.tick, physics_health)`（`run_joint_flight.py:919`）
   把 manager 的 `physics_health`（`run_joint_flight.py:570-583`：遍历子进程 `poll()`、`pause_probe.pump()`、
   `lifecycle.periodic()`、看门狗）传进释放环，环内每约 2 ms 调一次。该函数的真实代价**未被测量**
   （探针只包了它在 `begin_group` 内的调用次数与累计墙钟，未分项）。
5. **anchor 之后的首次代价**：§1.2 只证明「这些调用点发生在 anchor 之前」，**不证明**
   「anchor 之后不存在任何首次执行」。未排除的具体候选：Control 内部的首次执行器/回调/timer、
   DDS 线程首次唤醒、`pause_probe.pump()` 里某个订阅的首次回调、`record_native_maps` 之外的其他 `/proc` 读取路径。

---

## 5. 仍需测量（最小、可检验，且不新增仪表）

- **M1（零 native 成本）**：直接读已提交工具已经产出的 `phase_partition`（early/crossing/steady 的
  creep/work_over/release_excess 与逐类 top-interval），在两场与基线上比较 **early 类**的每区间值。
  这能判定：开局亏损是「early 类内的一次性」还是「与 steady 同形的持续小额超付」。
  **本报告不扩展该分析器**（A 正在改它），只把它当权威口径使用。
- **M2（零 native 成本）**：用同场 `rate_group_start.actual_start_ns` 与 `counted groups` 复算
  「每 250 组的 creep / work_over / release_excess」，只在**报告内**标注这是任意块，不作分区声称。
- **M3（需一次带探针的场次）**：在 `begin_group` 释放环**最外层**记录 3 个时刻
  （进入、最后一次 `health()` 返回、spin 退出）以把 `final_spin_other` 拆成
  「设计 spin ≈1 ms」与「被调度/阻塞吃掉的额外部分」。**注意**：这不是 v1 所说的
  「零开销仪表」——它会读取时间并改变被测代码，属需评审的诊断改动，本报告**不实施**、也不替代 A 的工作。

**不建议**：放宽 `LATE_LIMIT_NS`、0.5 速率、8 ms 周期、4-tick 屏障或任何 health 界限；
在未分离上述未排除项前做同配置盲重复。

---

## 6. 与本报告排除结论无关的旁注：热路径上的重复构造（只指出，不修改）

按现有真实源，以下构造在每个 tick / 每个 RPC 轮都被重建（仅陈述事实，未运行、未改）：

- `joint.py:197-199`：每 tick 重建 `sensor_fields` 返回的 dict 与其 `state[64:67]`、`state[61:64]`、
  `state[6:9]`、`state[12:16]`、`state[3:6]` 五个切片列表
  （`Simulator/wksim_core/ap_json.py:37-41`），随后每 tick 一次 `json.dumps(..., allow_nan=False)` + `encode('ascii')`。
- `worker.py:182-193`：每 RPC 轮重建 `requests[name] = (worker, req)`、`req` dict，以及
  `self.states = {name: list(response['state']) ...}` 的 120 元素列表**拷贝**；
  `worker.py:228-236` 再重建 `response`、`commands`、`input`、`request`、`extras` 多个 dict。
- `run_joint_flight.py:963-967`：每个 tick 在循环体内 `import math` 并重建 `summaries[name]` 行的更新。
- `run_joint_flight.py:750-757` 等：`Path(...)` 构造在每个 tick 的循环体内重复（一旦进入这些分支）。

主会话正在把其中「重复 `Path` 构造移到循环外」作为 **C2 候选**由 A 处理；
本条与本报告的「未排除」结论无关，也不构成本报告的任何因果判断。

---

## 7. 未做 / 未宣称

- 未运行任何 native/ROS/SITL；未编译；未加载模型；未编辑 runner、`wksim_core`、`wksim_runtime`、A 的分析器或旧 B 的比较器；未提交 Git；未嵌套代理；未接管旧 B 的未验收比较器。
- **不宣称**运行时已修，**不宣称**任何排他归因（宿主 / 飞控 / GC / 探针）。
- 本报告只区分三类：**已证**（§1）、**未排除**（§4）、**仍需测量**（§5）。
