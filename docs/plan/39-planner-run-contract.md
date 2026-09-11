# #102 规划运行合同 — 离线 B-spline→TrajectorySession 适配接缝

2026-09-11。本切片交付 issue #102 的最小**离线前置接缝**：把一条**显式供给**的 EGO uniform B-spline payload 纯确定性地转成 TrajectorySession（`Simulator/wksim_planning/trajectory_session.py`，issue #101 合同）接受的 10 ms / 整数 1 ms-tick 轨迹样本。它在 agy 已完成的源码复核之上实现，复用 #101 已冻结的会话语义，**不**新增任何执行/物理/ROS 能力。

## 交付物（仅 4 个文件）

- `Simulator/wksim_planning/ego_evaluator.py` — 纯 de Boor uniform B-spline 求值器（无 ROS/planner/SITL 依赖），仅 position/velocity/acceleration，仅 order 3。
- `Simulator/wksim_planning/ego_trajectory_adapter.py` — 纯确定性适配器：EgoSpline payload → TrajectorySession 样本流；yaw 为强制显式 fallback。
- `validation/test_ego_trajectory_adapter.py` — 35 项单元测试，纯 Python，无 MATLAB/build/SITL/UE。
- 本文档。

不改 `trajectory_session.py`、不改 #59 三文件、不碰任何现有 dirty 文件。

## 离线边界（严格收窄，永不外推）

**本接缝是纯离线求值/适配，绝不**：

- 启动或接入任何 **ROS / ROS2 EGO planner**——不声明 ROS2 planner 存在；
- 读取 **point cloud**、占用图或任何传感器输入；
- 运行 **SITL / UE / MATLAB / build**；
- 读取墙钟（wall clock）或真实飞行数据；
- 拥有或铸造 public `request_id`——`request_id` 归 public command publisher，本适配器只向会话喂轨迹样本；
- 分配 public `command_id`——`command_id` 由 `TrajectorySession` 唯一分配（1..4294967295，溢出→FAULTED）。

**坐标/单位**：仅接受 ENU `map` 帧（metres / seconds / radians）。无隐式坐标旋转或帧转换；任何非 `map` 帧在适配器构造期即拒绝。

**求值网格**：会话消费整数 1 ms tick；上游 traj_server 的求值定时器是 10 ms。适配器每个样本推进 `SAMPLE_STRIDE_TICKS=10` 个整数 tick，`seconds_to_tick` 拒绝任何不落 1 ms 网格的时间。

## 求值器数学（对齐上游，含非均匀 knots）

复现上游 `Modules/ego_planner_swarm/bspline_opt/src/uniform_bspline.cpp`（pinned `5dcd8cfa764d`）：

- 初始 knots：order p、N 控制点，n=N-1、m=n+p+1；`u(i)=(i-p)*interval (i<=p)` 否则 `u(i)=u(i-1)+interval`；
- 域 `[u(p), u(m-p)]`；de Boor 夹取+p 级 corner-cutting；`evaluate_t(t)=evaluate(t+u(p))`；
- **真实 EGO 输出并非常为初始均匀布局**：`lengthenTime(ratio)`（`planner_manager.cpp:642`）就地修改内部 knots，traj_server 的 `bsplineCallback` 又 `setKnot(msg->knots)` 整体替换。因此求值器**接受并使用**任何**恰为 m+1 长、全有限、严格递增**的供给 knot 向量（对应上游 setKnot），用于求值与导数；否则 fail closed。重复/非单调/错长/非有限 knot 均拒绝（否则上游 de Boor/导数分母为 0 或 span 退化）。
- **导数复现 `getDerivative`**：控制点 `Q_i = p*(P_{i+1}-P_i)/(u(i+p+1)-u(i+1))` 用**当前 knots** 计算，order p-1；导数的 knot 向量是父 knots **掐头去尾**（`u_.segment(1, rows-2)`），绝不重发均匀布局。对均匀输入此变化位元等价；对非均匀（lengthened）输入则正确反映被移动的 knot。
- **仅 order 3**：只接受真实 EGO 的 order 3（`EGO_ORDER`），在求值器构造期即拒绝其他 order，避免 order 1 等到适配器 acceleration 二阶导数时才失败。
- **yaw 不从轨迹求值**：上游 traj_server 只对 **position** `setKnot`，并由 `calculate_yaw` 基于 position/`last_yaw`/**墙钟** 算 yaw（其 publisher 当前也未填 `yaw_pts`）。本离线接缝无墙钟，**故移除 yaw 曲线求值路径**，只暴露 position/velocity/acceleration；适配器改为一律要求显式有限 fallback yaw。

## 适配器合同（复用 #101 会话语义，不在此重定义）

- **生成隔离**：`activate` 前必须 `begin_replan`（生成号 bump）；payload 的 generation ≠ 会话当前 generation → 会话以 stale replan 拒绝。
- **identity 校验（每个公共方法）**：`step`/`next_output`/`begin_replan`/`activate`/`cancel`/`hold` 在**任何求值/喂样本/状态改变/tick 推进之前**用公开 `Identity.from_value` + `session.identity`/`session.generation` 校验稳定四元组与当前 generation；错误 identity 一律 fail 且不喂样本/不改状态/不推进 tick。适配器**绝不调用会话私有方法/字段**。
- **适配器自持 tick high-water**：每次 `step`/`next_output` 在任何求值/喂样本前拒绝 tick 非严格递增，防止 `session.sample` 先写入后 `next_output` 才拒绝；**失控/状态过期等安全路径在会话成功返回后同样记录该 tick 到 high-water**，之后重复或回退 tick 在适配器层拒绝。新 `activate` 的 `start_tick` 必须**严格大于**已观察到的最高 tick（含 step 与 query 及安全路径走过者）——允许相等会令 `_next_tick` 指向已消费的 tick，后续严格递增的 step 永远无法命中首样本。
- **显式 start_tick**：每次 `activate` 必须显式给当前 authority tick；replan **不能复用**更早或相等的 tick（authority tick 单调不复位）。
- **position 维度**：`EgoSpline` 构造期即确认 `position.dimension == 3`（ENU 3 向量）；标量/1 向量/2 向量 control points 在构造期 fail-closed，不会等到 step 才失败。
- **上游 trajectory_id 显式保留**：调用方供 Bspline.msg `traj_id`。注意 Bspline.msg 中 `traj_id` 是 **int64**；此处 uint32 上限来自 **#101 TrajectorySession 的有意收窄**（`MAX_COMMAND_ID`），并非上游字段本身宽度。它必须在 uint32 内**严格递增**；适配器**绝不本地铸造**无关 ID。非递增（stale）或 > uint32（overflow）均拒绝。
- **安全优先**：`step()` 先校验 identity 与 tick，再检查 `owns_control`/`state_fresh`（必须为 bool）；失控或状态过期时**绝不求值、绝不喂/改样本**，只转发会话的 RELEASED/FAULTED 转移。仅在仍持有控制且状态新鲜时才求值并喂当前 tick 的样本，再读会话单一写者意图——因此每条发出的轨迹都带**本 tick 求值**的样本，绝不发陈旧样本。
- **yaw 一律强制 fallback**：本接缝不求值 yaw 曲线（见上节）；`activate` 必须给**显式有限 fallback yaw**，适配器**绝不静默发明 yaw=0**。
- **单调 command_id**：由会话单调分配、溢出→FAULTED；跨 replan（tick 单调不复位）仍严格递增。
- **过期→HOLD**：每样本 `valid_until = min(tick+10, end_tick)`；漏喂→会话转 HOLD。轨迹结束（`tick > valid_until` 且过 end）→ HOLD，**绝不延伸末速度**（`velocity_ref=[0,0,0]`）。
- **fail closed**：畸形/非有限 knots 或控制点、错长/非单调 knot、order≠3、**标量/非 3 向量 position**、off-grid 时间、stale generation、stale/overflow traj_id、回退或等于已观察 tick 的 start_tick、缺/非有限 fallback yaw、非 bool 安全标志、错误 identity、tick 重复/回退——全部拒绝。适配器**绝不读会话私有 `_trajectory`**。

## 测试

```powershell
python -B -m unittest validation.test_ego_trajectory_adapter -v
python -B -m unittest validation.test_trajectory_session -v
```

`test_ego_trajectory_adapter` 38 项全部通过、`test_trajectory_session` 8 项全部通过。覆盖：求值器端点/内部值（恒定/线性/非对称曲线路径）、**非均匀 lengthened knots 接受且求值/导数正确**（导数掐头去尾、用当前 knots、被移动 knot 处求值/导数改变）、畸形/非有限/错长/非单调 knot 与控制点拒绝、**order≠3 构造期拒绝**、**标量/非 3 向量 position 构造期拒绝**；激活需显式 start_tick/ID/**强制有限 fallback yaw**、帧不匹配拒绝、轨迹结束→HOLD；**更高单调 tick 的迟到 replan**、**走过 tick100 后 replan start=100 拒绝（相等会指向已消费 tick）、start=110 接受且 step(110) 发出 trajectory**、stale generation 拒绝、样本过期→HOLD、取消（迟到样本拒绝+无输出）；**失控喂零样本**（适配器喂游标不动、会话 RELEASED）、状态过期→FAULTED、安全标志须 bool、**安全路径把已观察 tick 记入 high-water、之后重复/回退 tick 在适配器层拒绝**；**错误 identity 在 stride/non-stride/lost-control/next_output 前均 fail 且不喂样本/不改状态/不推进 tick**、**step 重复/回退 tick 在喂样本前拒绝**、next_output 推进 tick high-water；traj_id 严格递增/uint32 overflow 拒绝、跨 replan command_id 严格单调、command_id 溢出→FAULTED。

## 仍未交付 / 保持开启

- **真实 ROS2 EGO planner**：未接入、未声明存在。
- **point cloud / 占用图**：未读取。
- **#29 / #33**：接触观察者与状态估计接缝保持开启，不在本切片闭合。
- **public flight**：真实飞行验证保持开启。
- **issue #102**：本切片仅交付离线前置接缝；#102 整体仍开启，待真实 planner/point cloud/#29/#33/public flight 各自闭合。

未 git 提交/推送/issue 写入；未运行 SITL/UE/MATLAB/build。
