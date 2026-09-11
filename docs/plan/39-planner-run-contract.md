# #39/#102 规划运行合同 — ego-single-box-v1 离线入口与 B-spline 适配接缝

2026-09-12。本合同现在覆盖三个相互独立的离线前置接缝：profile 关闭的 EGO ROS1 launch 入口、显式供给的 EGO uniform B-spline 到 `TrajectorySession` 的纯 Python 适配，以及 GridMap 动态参数回调的生命周期安全边界。它们只冻结输入、参数和静态边界，**不声明真实规划器、ROS 传输、物理飞行或验收已经完成**。

## 本次 launch/profile 与 GridMap 参数安全静态切片

- `Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/advanced_param_wksim_single_box.xml` — 从现有 `advanced_param.xml` 的参数语义派生，关闭 `ego-single-box-v1` 的地图、唯一点云输入、预设目标和实际生效的速度/加速度限制；不暴露可覆盖这些值的 launch arg。
- `Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/sitl_ego_planner_wksim_single_box.launch` — 只 include 上述 planner 参数和上游 `traj_server_for_prometheus`；不启动 ROS bridge、飞控、SITL、UE 或地图生产器。
- `validation/test_39_planner_launch_contract.py` — XML well-formed、参数/输入唯一性、profile 数值和 profile hash 交叉合同测试；纯 Python。
- `Modules/ego_planner_swarm/plan_env/src/grid_map.cpp` / `Modules/ego_planner_swarm/plan_env/include/plan_env/grid_map.h` — 修复 GridMap 动态参数回调的局部地址逃逸，并将初始化期结构参数与运行期安全参数分开处理。
- `validation/test_grid_map_param_safety.py` — 对地址不逃逸、fail-closed 解析、初始化期拒绝和运行期字段边界做纯静态合同检查。
- 本文档。

这些 launch/profile 与 GridMap 参数边界只做静态合同。未改 sender/receiver、pump 或保护文件，也未提交。

## ego-single-box-v1 固定值与坐标边界

profile 来源是 `Simulator/wksim_planning/scene_profile.py` 的 `EGO_SINGLE_BOX_V1`，不是 launch 文件重新定义的几何。launch 固定：

- ENU、米、秒、弧度；map 原点 `(-10,-6,0)`，尺寸 `(20,12,6)`，分辨率 `0.1`；障碍 AABB `[-0.5,0.5] × [-1,1] × [0,5.5]`。
- profile 的起点是运行准入中的真实 odom/接管状态 `(-4, 0, 3)`；它不是 EGO 源码读取的 planner 参数，故没有伪造 `fsm/start_*`。预设目标通过上游 `flight_type=2` 和唯一 waypoint `(4, 0, 3)` 固定；当前 overlay 的 `realworld_experiment=false` 只使 FSM 初始 `have_trigger=true`，因此免除外部 `/uav1/ego_trigger` 等待。FSM 仍要求真实 odom，并要求 `/uav1/prometheus/control_state` 的 `control_state==2` 才能离开 `WAIT_TARGET`、进入规划；本 launch 不启动该控制状态发布者。
- 唯一点云输入为仓库已有 `map_generator/global_cloud` `sensor_msgs/PointCloud2` 语义。这个 topic 绑定不证明生产者已经发布 profile 的 11,000 个体素中心；运行准入必须核对点云内容、frame 和 hash。
- `local_update_range=(9,7,6)`、`obstacles_inflation=0.8`、`virtual_ceil_height=5.5`、`max_vel=0.8`、`max_acc=6`、`planning_horizon=13.5`、重规划间隔 `1.0`，均来自已读上游参数语义或冻结 profile；上游虽读取 `manager/max_jerk`，但当前规划器不执行 jerk 约束，故 overlay 不发布该无效参数。
- 上游 grid map 的 frame 写法固定为 `world`；本合同只允许它作为 profile `map` 的**同原点同轴别名**，不允许旋转、轴交换或隐式单位变换。`world`/`map` 不一致时运行必须拒绝。

当前 `EGO_SINGLE_BOX_V1` 的静态身份为：

- `profile_hash` / `canonical_hash`: `49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7`
- `collision_hash`: `08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c`
- `voxel_hash` / profile `point_cloud_hash`: `3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638`
- 体素中心数量：`11000`，顺序 `x,y,z` 升序；物理碰撞体与点云仍需 #29 现场证据证明同源。

## 离线边界（严格收窄，永不外推）

本切片**只做静态合同**，**不启动 ROS / ROS2**，不声明真实规划器，不声明已经完成真实飞行。它不读取运行时 point cloud，不运行 SITL / UE / MATLAB / build，不拥有 public `request_id`，也不分配 public `command_id`。launch 文件描述上游 ROS1 入口的参数和 topic 接缝；它不是运行结果或 transport proof。

真实接入仍必须等待 #29 的物理/反馈/碰撞观察器、#33 的 mixed-axis/trajectory-following 控制证据，以及 ROS1→ROS2 实际传输和共享 `/clock`。离线 profile、launch XML、B-spline 求值或 synthetic payload 都不能替代这些证据。

## 已知上游不匹配和现场准入门

- 上游通用 `advanced_param.xml` 的 `obstacles_inflation=0.2`、local range `5.5/5.5/4.5` 和通用 map 默认值不符合本 profile；本切片只在新 overlay 中关闭这些差异，不修改上游源。
- `GridMap::cloudCallback` 当前源码把 z 方向膨胀步数写死为 2 个 voxel，而 XY 使用参数 `obstacles_inflation/resolution`；因此 overlay 不能单独证明真实实现已经满足 profile 对三维碰撞包络的要求。这是 P1 上游实现差异，必须由 #29 的物理几何/clearance 证据解决或另行修复。
- **GridMap 参数回调 P1，静态修复已覆盖**：`GridMap::initMap` 仍使用局部变量读取启动期的 `uav_id`、尺寸和原点，但这些变量的地址不再保存到成员指针容器；`/uav1/prometheus/param_settings` 回调对 `param_name/param_value` 数量、前缀和解析结果做 fail-closed 校验。分辨率、尺寸、原点、`pose_type`、相机内参、深度比例、`skip_pixel`、概率、地面/虚拟顶等初始化期参数明确告警并忽略；局部更新范围按初始化 `map_size_` 逐轴限幅，`local_map_margin` 按 `map_voxel_num_` 和整数算术余量限幅，膨胀距离按初始化分辨率/地图尺寸限到最多 32 个 voxel（`65^3` 个候选），深度/射线 min/max 不能越过地图对角线或形成 `min>max`。深度过滤、射线范围、超时、布尔开关和 `frame_id` 只通过显式解析与域约束更新，不重建或改写地图边界、体素数量、buffer 或订阅结构。该结论是源码/静态合同证据，尚未做 catkin/ROS 构建或运行期参数事件验证。
- `map_generator/global_cloud` 只是仓库已有 topic 名称；没有静态测试能证明其内容等于 profile 点云。发布者必须提供 11,000 点、frame、profile/voxel hash 和时间戳证据。
- `flight_type=2` 使用预设 waypoint；在当前 `realworld_experiment=false` 仿真语义下，FSM 将 `have_trigger` 初值设为 `true`，免除外部 `/uav1/ego_trigger` 等待，但仍必须有真实 odom 和 `/uav1/prometheus/control_state` 的 `control_state==2` 才能离开 `WAIT_TARGET` 并进入规划。起点只来自真实 odom，参数本身不能当作已经接管或已经起飞。

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
python -B -m unittest validation.test_39_planner_launch_contract -v
python -B -m unittest validation.test_ego_trajectory_adapter -v
python -B -m unittest validation.test_trajectory_session -v
```

本次 launch/profile 静态测试 11 项通过；测试逐项锁定两个 XML 的活动 remap、节点元数据和所有声明参数的精确值/类型，并读取上游 FSM、GridMap、planner manager、optimizer 和 planner node 源码，锁定 trigger 初值、`control_state==2` 的 `WAIT_TARGET` 门槛及有效/无效参数边界。XML 两个文件均可由 Python `ElementTree` 解析，且 `py_compile` 通过。以上只证明静态合同，不证明 ROS launch、planner、传输或飞行。

`test_ego_trajectory_adapter` 38 项全部通过、`test_trajectory_session` 8 项全部通过。覆盖：求值器端点/内部值（恒定/线性/非对称曲线路径）、**非均匀 lengthened knots 接受且求值/导数正确**（导数掐头去尾、用当前 knots、被移动 knot 处求值/导数改变）、畸形/非有限/错长/非单调 knot 与控制点拒绝、**order≠3 构造期拒绝**、**标量/非 3 向量 position 构造期拒绝**；激活需显式 start_tick/ID/**强制有限 fallback yaw**、帧不匹配拒绝、轨迹结束→HOLD；**更高单调 tick 的迟到 replan**、**走过 tick100 后 replan start=100 拒绝（相等会指向已消费 tick）、start=110 接受且 step(110) 发出 trajectory**、stale generation 拒绝、样本过期→HOLD、取消（迟到样本拒绝+无输出）；**失控喂零样本**（适配器喂游标不动、会话 RELEASED）、状态过期→FAULTED、安全标志须 bool、**安全路径把已观察 tick 记入 high-water、之后重复/回退 tick 在适配器层拒绝**；**错误 identity 在 stride/non-stride/lost-control/next_output 前均 fail 且不喂样本/不改状态/不推进 tick**、**step 重复/回退 tick 在喂样本前拒绝**、next_output 推进 tick high-water；traj_id 严格递增/uint32 overflow 拒绝、跨 replan command_id 严格单调、command_id 溢出→FAULTED。

## 仍未交付 / 保持开启

- **真实 ROS2 EGO planner**：未接入、未声明存在。
- **point cloud / 占用图**：未读取。
- **#29 / #33**：接触观察者与状态估计接缝保持开启，不在本切片闭合。
- **public flight**：真实飞行验证保持开启。
- **issue #102**：本切片仅交付离线前置接缝；#102 整体仍开启，待真实 planner/point cloud/#29/#33/public flight 各自闭合。

未 git 提交/推送/issue 写入；未运行 SITL/UE/MATLAB/build。
