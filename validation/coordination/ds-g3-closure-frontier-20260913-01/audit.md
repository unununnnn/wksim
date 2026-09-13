# G3 Prometheus 场景收口：独立只读审计

范围：open **#29**（AC2/AC3）与 **#102** 轨迹/场景准入合同。
基线：requested HEAD `0a1caa1`；架构提交 `f333316` 祖先校验通过。
所有结论均可用本目录 `check_g3_closure.py` 重跑（56/56 checks pass）。

本审计**只读**：未运行 native/构建/ROS/飞控/模型/UE/MATLAB，未操作进程，未修改 issue，
未改动任何既有文件，未 git add/commit/push。唯一写入目录为本目录。

---

## 0. 环境与基线（含并发写入事实）

| 项 | 值 |
| --- | --- |
| cwd | `C:\Users\PC\Documents\odid编译\wksim` |
| requested base HEAD | `0a1caa116e31700155a7abb567176c48668c0e8e` |
| `f333316` 是 HEAD 祖先 | 是（`merge-base --is-ancestor` exit 0，每次观测均成立） |
| head 观测于运行时 | `027cf43018bded896aadfebace98e60e3afbba01` |
| Python | 3.13.11 |

**并发写入事实（必须记录）：** 审计期间 HEAD 被另一写入者推进两次：
`0a1caa1`（2026-09-13T22:50:03）→ `287f8ec`（22:53:39）→ `027cf430`（22:55:58）。
两个新提交只在 `validation/coordination/` 下**新增**证据目录，未触碰本审计引用的任何文件。
`git diff --name-only 0a1caa1 HEAD -- <13 个被引产物>` 输出为空，
故本审计结论对 requested base 成立；`audit_commit_is_ancestor_of_head` 与
`cited_artifacts_unchanged_since_audit_commit` 均由脚本断言通过。

**上下文文件核对：** 本 checkout **不存在** `CONTEXT-MAP.md`（仅历史文档引用它），
且**不存在** `docs/adr/`——与 `docs/plan/2026-09-08-output-phase-review.md:22` 等
文档自身的陈述一致。`CONTEXT.md` 存在，并由 `f333316` 重写（当前版 72 行词汇表）。

**派发策略说明：** AGENTS 要求非 `gpt-6-astra` 派发的子代理必须使用
`gpt-5.6-luna` / `xhigh` / Fast，而本会话接口无法选择与验证这些设置，
故按 AGENTS「在 main agent 内完成并报告该限制」执行，未做委派。

---

## 1. Issue 状态（gh 只读）

| Issue | 状态 | 标签 | 备注 |
| --- | --- | --- | --- |
| **#29** 坡面与障碍场景的物理反馈 | **OPEN** | `ready-for-agent` | `closedAt=null`，updated 2026-09-11T19:06:07Z |
| #79 / #80 / #81 | CLOSED | `wayfinder:task` | #29 的三个子票 |
| #9 可选模型插件与场景反馈接口决策 | **OPEN** | `wayfinder:grilling` | #29 blocked-by，ABI NO-GO |
| #17 / #23 | CLOSED | `ready-for-agent` | #29 另两个 blocked-by |
| **#102** 接入规划器并验证一个真实绕障场景 | **OPEN** | `wayfinder:task` | body = `lunar-slice:39-planner-flight:v1`，父票 #39 |
| #39 单机规划绕障到真实飞行 | **OPEN** | `ready-for-agent` | #102 的父验收 |

注意：`docs/plan/102-trajectory-scene-admission-contract.md` 是**文件编号**，
其正文声明「does not close #102 or #39」；issue #102 的完成条件（真实
map→planner→public control→flight 证据）与本文件所述的 offline 准入 seam **不是同一件事**。
不得以本文的 seam 证据代替 issue #102/#39 的真实飞行验收。

---

## 2. 被引原件与 SHA256（工作区文件字节）

`kind` 含义：`pre-arch` = 作者提交早于 `f333316`；`seam` = 准入 seam 本体；
`dep` = seam 的依赖（合同写成后才改动）；`consumer` / `transport` / `test` / `29-evidence`。

| kind | path | SHA256 | 最后提交 |
| --- | --- | --- | --- |
| pre-arch | `docs/plan/29-terrain-closure-report.md` | `edff1cd2d9a77ea218937616b512a964deb40e42d47a91b6c7a24392ff1cfcd6` | `2847c51` 2026-09-11T17:13:43 |
| pre-arch | `docs/plan/102-trajectory-scene-admission-contract.md` | `cf0042f4db2aa32de82bc7725362403eb24b240bb2d2651ca2ff74fff9ab5b24` | `c049954` 2026-09-12T04:10:54 |
| seam | `Simulator/wksim_planning/ego_scene_admission.py` | `6671bc6f4b9654a2ed4fae7c4f0d3c32937da94a8c7fed10c875783feec8c40b` | `c049954` |
| seam | `Simulator/wksim_planning/scene_profile.py` | `5a34e036194372241577b7187107eecc2c6be1777a7f51a4f189f87a6205f84c` | `f627d19` 2026-09-12T01:37:45 |
| seam | `Simulator/wksim_planning/ego_bspline_bridge.py` | `c696f936208ed9faed2575a9df1b6aa5e13acfd6c96f21a5d48b8d71a11aaa51` | `d5c2efc` 2026-09-11T16:55:37 |
| seam | `Simulator/wksim_planning/ego_evaluator.py` | `ad91915c5f61625c05497a9e64ece596c4aa336e03723e96efb2104b7ff9b1e2` | `97d40da` 2026-09-11T14:10:40 |
| seam | `Simulator/wksim_runtime/planner_scene_binding.py` | `da45997ec4caceb45cd6652717b71973d8be041e94f690ba89b7011e6ea1a0cf` | `7a08bd5` 2026-09-12T02:51:36 |
| dep | `Simulator/wksim_planning/ego_trajectory_adapter.py` | `1ebd161181e8dfe8d0388e1eaa307385df34b7247935a6da321d17a2243c515d` | `68cc1d1` 2026-09-12T15:03:50 |
| dep | `Simulator/wksim_planning/trajectory_session.py` | `8887ec11edfc67e0aed8faf3e8768aec90bcdf9138d1f4c4b80733a847317df0` | `042fef3` 2026-09-12T13:34:33 |
| consumer | `Simulator/wksim_runtime/planner_transport_pump.py` | `30e48e08801c22b7a2f7684ca154fa086f0f4dab3c6f60c8a8e4aa258ca76da5` | `a379917` 2026-09-12T14:42:04 |
| transport | `Simulator/wksim_runtime/bspline_tcp_envelope.py` | `f0dffe7fe3e8717a2ca4e3af7ac2d740266c89fa534b9a1a8dde814af8ee59a3` | `a379917` |
| test | `validation/test_ego_scene_admission.py` | `3d9d00281fcae64afd654ba65036e819bea973145ec36284cdcb57667d777188` | `c049954` |
| 29-evidence | `validation/lunar-29-terrain-reset-c8f05c6e/result.json` | `2c55cc62ae594210bbd5189015b3acbcbf3d35f295a23cb25e923871f3a08fe8` | `b8d141c` 2026-09-11T17:00:34 |

关键点：seam 本体 4 个文件 + 绑定 + 测试**自作者提交以来字节未变**；
`ego_scene_admission.py` 的文件 SHA256 `6671bc6f…` 与已提交证据
`validation/33-final-combo-luna/*/{control-build,result}.json` 中 pin 的值一致，
说明那些证据包 pin 的正是 HEAD 的同一份 seam 字节。

---

## 3. 证据三级分类

### 3.1 当前架构证据（post-f333316，本次在 HEAD 实际重跑）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| #80 静态接触夹具独立审计 | `python -B validation/lunar-29-static-contact/audit.py` | exit 0，`{"assertions":85,"cases":13,"skipped":0,"status":"pass"}` |
| #81 可视场景/反馈记录独立审计 | `python -B validation/lunar-29-live-contact/audit.py` | exit 0，`{"assertions":30895,"rows":3253,"skipped":0,"status":"pass"}` |
| #102 准入合同提交测试套件 | in-process `unittest` on `validation/test_ego_scene_admission.py` | `tests_run=22, failures=0, errors=0, skipped=0` |
| 准入合同已发布身份 | `check_g3_closure.py` §C | 11 项身份/常量断言全部通过 |

两个 `audit.py` 仅导入 `hashlib/json/sys/pathlib`（纯标准库），只读取冻结数据文件，
因此**与架构解耦**，其结论在 HEAD 仍然成立。`run.py` 会写 `results.jsonl`，**未运行**。

同时须知：`validation/test_ego_scene_admission.py` 的通过是在**依赖已改动**之后取得的——
`ego_trajectory_adapter.py`（`68cc1d1`）与 `trajectory_session.py`（`042fef3`）都在
合同提交 `c049954` 之后被修改（含 `_trajectory_end_tick` 舍入语义、`stop()` 原子化改写），
而 22 个测试（含「失败时零适配器调用、零 session 变更」与「单次激活」断言）
**在新依赖下仍全部通过**。这是准入合同仍具当前架构效力的直接证据。

### 3.2 pre-f333316 历史证据（冻结产物，无法从 HEAD 复现）

- `docs/plan/29-terrain-closure-report.md`：自述基线「地形证据截至 `b8d141c`；
  主代理在 `ff6fc47` 上完成复核」——`b8d141c`(09-11 17:00)、`ff6fc47`(09-11 17:07)
  均为祖先但**早于 `f333316`(09-13 17:51)**。
- `docs/plan/102-trajectory-scene-admission-contract.md`：作者提交 `c049954`(09-12 04:10)，
  早于 `f333316`。
- `validation/lunar-29-terrain-reset-c8f05c6e/result.json`：产出于 `b8d141c`，早于 `f333316`。

### 3.3 未验证声称 / 无法由本次静态证据补足

- #29 AC2 的坡度/真实飞行接触动力学、接触力/冲量/刚度/阻尼/摩擦、侧碰、动态对象、
  FC 闭环——需 native/飞控。
- #29 AC3 的实际 UE5.5 显示断开/重连运行，以及 UE/WSL/FC/ROS2/DDS 联合时钟闭环。
- #102/#39 的真实 planner→公开控制→飞行到达/无接触/clearance/取消重规划证据。
- #9 的厂商 DLL/插件 ABI（`wayfinder:grilling`，NO-GO）。

---

## 4. #29 AC2 / AC3 逐项裁决

### AC2「在坡面/接触工况中检查高度、接触位置与模型反应，重置后按批准预算可复核」→ **PARTIAL**

**已证明（当前架构，可复跑）**
- #80：平面/盒顶/侧面/中心棱带/表面/自由空间的接触点、法线、穿透深度，以及
  fresh/stale/future/foreign-epoch/scene-hash-mismatch 反馈时效语义（13 cases / 85 assertions）。
- #81：逐 3253 条记录检查 contact/no-contact 与显式 freeze/recover。
- 场景身份：静态夹具 `static-plane-box-v1`，scene SHA-256 `60ae5097…`（#80/#81 与
  `display-manifest.json` 共用）。

**仅历史，且已漂移（见 §5）**
- 「生成模型 terrain ingress、状态反应、elevated 冷重置精确重放」三项声称的唯一载体是
  `result.json`（`b8d141c`）。该产物 pin 的 10 个源中有 2 个（`wksim_core/model.py`、
  `wksim_core/worker.py`）与 HEAD 字节不同，且 `worker.py` 的改动发生在 `f333316` 之后的
  `1abf5f3`(09-13 12:15)。**该产物无法从 HEAD 复现，属历史证据，不构成当前架构证据。**

**未证明**
- 坡度/真实飞行接触动力学；接触力/冲量/刚度/阻尼/摩擦；侧碰；动态对象；FC 闭环。
- probe 的 native I/O 为确定性 ACK / 4 ms barrier stub（报告陈述，本次未运行 native 复核）。

### AC3「显示断开及反馈过期按批准契约处理，不能永久复用旧反馈或依赖渲染帧推进物理」→ **PARTIAL**

**已证明（当前架构，可复跑）**
- `validation/lunar-29-live-contact/`：`run-config.json` 声明 `1 ms` frame 与
  `30000 < frame <= 30020` 缺必需反馈；`events.json` 记录 `freeze` 于 frame 30019、
  `boundary_step=29999`，frame 30039 由 fresh feedback 显式恢复；审计器逐行核对 epoch、
  步号、时间、单步有效区间与 manifest 绑定（30895 assertions）。
- `display-manifest.json` 明确 `authority`: physics 在 WSL，manifest 仅 display-only，
  不能修改 physics；证明「不依赖渲染帧推进物理」的**契约层**存在。

**未证明**
- 实际 UE5.5 显示断开/重连运行；UE/WSL/FC/ROS2/DDS 联合时钟闭环。
- 因此记录式 truth/manifest 审计**不能**提升为实际产品链路证明。

### 两个 hash 层不可混写
`60ae5097…`（#80/#81 冻结静态夹具与 display manifest，盒心 `[2,0,0.5]` m）与
`4889e2ea…`（真实生成模型 probe 依 elevated tick-0 ENU 生成的场景身份）是**不同层**。
把二者合并成「UE 已显示并驱动物理」不成立。

---

## 5. 精确原件与 SHA：terrain-reset 产物源身份漂移（新发现）

原件：`validation/lunar-29-terrain-reset-c8f05c6e/result.json`
SHA256 `2c55cc62ae594210bbd5189015b3acbcbf3d35f295a23cb25e923871f3a08fe8`，
`.status=passed`，`.ticks=50`，`.library.sha256=e59ab914e3ff8225ff303e05a885f8fa1eaedb05a95443f097920ca60a7f1c0b`。

其 `source_sha256` 共 pin 10 个源。与 HEAD 逐字节比对：

**一致（8）**：`wksim_core/joint.py`、`wksim_core/model.cpp`、`wksim_core/static_contact.py`、
`wksim_runtime/contact_observer.py`、`wksim_runtime/scene_clock.py`、
`wksim_runtime/static-scene-v1.json`、`wksim_runtime/terrain_feedback.py`、
`tools/probe_joint_terrain_feedback.py`。

**漂移（2）**：

| path | pinned（与产出提交 `b8d141c` 一致） | HEAD | HEAD 最后改动提交 |
| --- | --- | --- | --- |
| `Simulator/wksim_core/model.py` | `a88f4405cca87fa02d3dbaa66d280397f9d57aa269f5941059ddd80ef0c7ba0b` | `3b0ae6f40594a30997fa66beba11466ca88f0c1a3b88c2322d4fee10f1ce4d41` | `0b1828a` |
| `Simulator/wksim_core/worker.py` | `dae21abdff34e887f65e6df4e0ecd0c004638cc1fcc16705acba0ebd78687c1c` | `38f34a8f68efe8353f99703ec3ce1a18749ec7798933587f349b480dd638060c` | `1abf5f3` 2026-09-13T12:15:59（`f333316` 之后） |

两者 `pin_matched_at_producing_commit = true`，即**在产出基线 `b8d141c` 上 pin 是精确的**，
漂移发生在之后。结论：`artifact_reproducible_from_head = false`。
按 AGENTS 连续性规则，该产物属**历史比较**，其结果**不验证新架构**；
#29 报告中关于 terrain ingress / 冷重置复现的 AC2 支撑因此降级为历史证据。

---

## 6. #102 准入合同：逐条核对结果

合同自述为 “offline geometry-admission slice only… does not close #102 or #39”。
本次在 HEAD 逐条核对（脚本 §C/§D/§I，56/56 通过）：

**已证明（当前架构）**
- 身份：`scene_id=ego-single-box-v1`；`scene_hash=40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba`；
  `profile_hash=49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7`；
  `geometry_id=ego-single-box-v1:obstacle`；障碍 AABB min `(-0.5,-1.0,0.0)` / max `(0.5,1.0,5.5)`；
  map bounds min `(-10,-6,0)` / max `(10,6,6)`；`vehicle_radius=0.35`；`required_clearance=0.30`。
- `clearance_margin`：合同刊载 `0.65`，实际浮点和为 `0.6499999999999999`（低 1 ulp）。
  纯表述差异，无行为影响，脚本以 `abs_tol=1e-12` 断言并单独记录该事实。
- 常量：`evidence_kind="sampled_segment_checked"`；admitted 报告的 `continuous_proof is False`；
  默认网格 `0.010 s`；`MAX_ADMISSION_SAMPLES=1_000_000`；11 个 reason code；
  `non_claims` 明确声明 sampled-only 边界。
- 网格边界：`duration == (MAX-1)*step` 被接受且样本数恰为 `MAX`；首项字面 `0.0`、
  末项字面 `duration`；再大 1 ulp 即 `invalid_grid` fail-closed。
- 提交测试套件：22 tests，0 failures。
- **接线（重要）**：seam 确有运行时消费者——`Simulator/wksim_runtime/planner_transport_pump.py`
  导入并在 `:223` 构造 `TrajectorySceneAdmission`，把 `clearance_violation` 映射为
  `rejected_clearance`（`:95`）。该 pump 自身在 `:111-112` 声明
  “no continuous-curve or flight-safety claim”。另有
  `ros2/src/prometheus_control/CMakeLists.txt`、`tools/build-joint-control.sh` 引用（native/ROS 路径，未执行）。
- 与已提交证据的身份一致性：见 §2 的 `6671bc6f…`。

**未证明**
- 连续曲线安全（合同以 `continuous_proof=False` 自述，且本次证明了该声明是**实质性的**，见 §7）。
- UE/SITL/ROS/socket/planner/wall-clock/物理力响应；真实绕障飞行（属 issue #102/#39）。

---

## 7. 最高价值缺口（P1）：sampled-PASS 可掩盖真实 clearance 侵入

**缺口**：准入门的障碍 clearance 只对 10 ms 采样折线成立，`continuous_proof` 是硬编码 False。
本次构造出**决定性反例**（脚本 §G，`checks.json.continuous_gap`）：

- 结点间隔 `h = 0.005 s`；203 个交替控制点 `x ∈ {0.85, 1.45}`，`y=0`，`z=2`；duration ≈ 1.0 s。
- 曲线 x 方向周期 `2h = 0.010 s`，**恰等于默认采样步长**，故每个采样点都落在曲线峰值上：
  采样 x 恒为 `1.25`。
- `assess_spline_clearance` → `admitted=True`，`violation=None`，
  `min_obstacle_clearance = 0.39999999999999913`（干净 PASS，高出 0.30 阈值 0.10 m）。
- 曲线在采样**中间**下探到 `x = 1.05`。独立 40 万点连续扫描得
  `true_min_obstacle_clearance = 0.19999999999999984`。
- 侵入量 = **`0.10000000000000014 m` = 需求 `0.30 m` 的 33.3%**。
  载具中心线距盒面 0.55 m，而合同要求 0.65 m。
- 该载荷对 bridge 结构合法（`order=3`、`len(knots)==len(pos_pts)+4`、结点有限严格递增、
  `drone_id=0`、yaw 空），bridge 不设幅度/运动学上限，故**经普通 decode→bridge 输入路径可达**。

**定级：P1，非 P0。** 现有产物均未把 PASS 宣称成「无碰撞」：模块、合同文档、
transport pump 都显式免责，因此当前没有任何组件在说谎。但 `clearance_violation → rejected_clearance`
意味着 PASS 就是「clearance 已满足」的**操作性信号**，用于把轨迹提交进 session；
而该免责声明在数量上是**承重**的：采样门可以给出 0.40 m，同时载具已在 margin 内 0.10 m。

### 互斥的最小实现包（无需 native，可直接编码并测试）

**A. 最小实现包（纯 Python，建议 main 独占）**
1. 新增 `Simulator/wksim_planning/ego_scene_admission_continuous.py`（**新文件，不改冻结 seam**）：
   `sound_span_certificate(spline, *, binding) -> ContinuousClearanceCertificate`。
   依据 B-spline 凸包性质：在结点区间 `[u_k, u_{k+1})` 上曲线落在活动控制点
   `P_{k-p}..P_k` 的凸包内；以该凸包的 AABB 作**可靠外包**，逐区间要求
   `aabb_gap(control_bbox, obstacle) - vehicle_radius >= required_clearance`，
   并要求全部控制点位于内缩 map AABB 内。
   输入畸形时 fail-closed，复用既有 reason 词汇。
   仅当**每个**区间都通过才置 `continuous_proof=True`；`evidence_kind` 用新值
   （如 `"convex_hull_span_certified"`），使既有 `"sampled_segment_checked"` 消费者不受影响。
2. 接线：在 `TrajectorySceneAdmission.admit` 增加**可选、默认开启**的严格通道
   （显式构造参数），并新增 1 个 reason code（如 `continuous_clearance_unproven`），
   使既有 reason→outcome 映射保持全覆盖，pump 可自行选择 fail-closed 或 advisory。
   *若维护者不接受改动 `ego_scene_admission.py` 而使 `6671bc6f…` pin 失效，
   则改为由 pump 直接调用新模块，seam 保持冻结。*
3. 测试：把 §7 反例固化为回归（证书必须 **REJECT**），并覆盖阈值等值、+1 cm 余量、
   envelope 违例、以及与密集扫描的可靠性交叉核对。
4. 文档：更新合同 “Honest evidence”、reason 表与 `non_claims`；**不得**静默去掉
   sampled 路径的 `continuous_proof=False`。

**原型已在本审计内验证可用**（`checks.json.sound_certificate_prototype`，200 区间）：

| 用例 | `min_obstacle_net_clearance` | `continuous_proof` |
| --- | --- | --- |
| 反例（sampled 误判 PASS） | `-1.1102230246251565e-16` | **False（正确拒绝）** |
| 常量 +1 cm 余量 | `0.30999999999999994` | True |
| 小幅安全正弦 | `0.31001973271571714` | True |

即证书**可靠且能区分采样门混淆的两种情况**。它是保守的（会拒绝部分真实安全曲线）；
后续可用精确凸包↔AABB 距离或 Bézier 细分收紧——仍无需 native。

**B. main 独占 native 包（本次不得尝试）**
1. 清除 §5 漂移：在 HEAD 重跑 `tools/probe_joint_terrain_feedback.py`，重新 pin 全部 10 个源哈希，
   重产 `validation/lunar-29-terrain-reset-*`。
2. #29 AC3：真实 UE5.5 显示断开/重连 + UE/WSL/FC/ROS2/DDS 联合时钟闭环证据。
3. #29 AC2：坡度/侧碰接触动力学与力/冲量/刚度/阻尼/摩擦（受 #9 ABI OPEN 与 #23 边界阻塞）。
4. #102/#39：真实 planner→public control→flight 到达/无接触/clearance/取消重规划证据。

### P1 最小补丁边界
1. **新增** `Simulator/wksim_planning/ego_scene_admission_continuous.py`（仅新文件）。
2. 仅在维护者接受 pin 失效时，才改 `ego_scene_admission.py`（1 个可选构造参数 + 1 个 reason code）。
3. 在 `validation/` 扩充测试。
4. 更新 `docs/plan/102-trajectory-scene-admission-contract.md` 的 Honest evidence / reason 表 / non_claims。

**本次审计未改动任何共享代码。**

---

## 8. 复跑方式

```bash
cd <repo root>
python -B validation/coordination/ds-g3-closure-frontier-20260913-01/check_g3_closure.py
```

期望输出：`{"failed": [], "passed": 56, "total": 56}`，并写出同目录 `checks.json`。
脚本纯 Python、只读仓库、不启 native/ROS/SITL/UE/MATLAB、不操作进程，
唯一写入为 `checks.json` 及（临时、随即删除的）审计目录内捕获文件。

## 9. 结论摘要

- `f333316` 祖先校验通过；本审计的 13 个被引原件在 HEAD 推进两次期间**均未改变**。
- #29 应**保持 OPEN**：AC2/AC3 均为 PARTIAL。AC1/AC4 的**夹具层**证据在 HEAD 可复跑成立；
  AC2 的「生成模型 terrain ingress / 冷重置精确重放」因 `model.py`、`worker.py` 源漂移
  降级为 pre-f333316 历史证据；AC3 的 UE/联合闭环仍缺失。
- #102 准入合同的**已声明范围**在 HEAD 逐条成立（22/22 测试通过，身份常量一致，接线存在）。
- **新发现的 P1 缺口**：sampled 准入会把一条真实侵入 margin 0.10 m（需求的 33.3%）的
  合法形状载荷判为 PASS；`continuous_proof=False` 不是形式免责而是承重声明。
  已给出无需 native、可直接编码并测试的最小实现包 A（含已验证的可靠凸包证书原型），
  与 main 独占 native 包 B 互斥。
