# #100 / 39-planner-contract — EGO 单机规划合同 v1

日期：2026-09-09。交付层级：来源审查与冻结合同。选择 Prometheus 自带 `Modules/ego_planner_swarm` 的单机 EGO rebound B-spline 规划器，限 uav1、点云输入、公共 TRAJECTORY 输出。没有规划器迁移、构建、接入或飞行成功结论。

## 准入与归属

#100 正文明确“无本票额外开放依赖”，父容器亦允许源码/合同先行；因此本次冻结离线实施切片。步骤中 “After #29/#33” 在实际接入前强制执行：查询时两票均 OPEN，#102 不可运行。#39 的 #15/#29/#33/#6 原依赖和验收保持有效。

本次只写此文件及 `validation/lunar-100-contract-20260909-01/`。#101 仅预留 `Simulator/wksim_planning/trajectory_session.py` 和 `validation/test_trajectory_session.py`。下面的上游路径都是来源阅读范围，不授予源码修改权。#102 当前只有文档和证据写权，尚不足以实现接入，须在实施前明确分配 ROS2 构建、规划节点、地图输入和任务发布适配的精确文件；不能把这份合同当作扩大 #102 写权的依据。

## 来源、路径和有意差异

上游：<https://github.com/amov-lab/Prometheus>，固定提交 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`。工作树身份、每个文件字节 SHA256、上游 Git blob 及是否相同见证据 `source-audit.json`。审查以下实际源码：

| 文件（相对 Modules/ego_planner_swarm） | 作用 |
| --- | --- |
| `plan_manage/src/ego_replan_fsm.cpp` | `callReboundReplan` 调用真实规划，成功后发布三阶 Bspline；EMERGENCY_STOP 可自动重新规划 |
| `plan_manage/src/planner_manager.cpp` | rebound 规划算法入口，后继须原算法接入，不能用预设航点替代 |
| `plan_env/src/grid_map.cpp` | PointCloud2 经 cloudCallback 写占用/膨胀图；局部裁剪，z 膨胀固定两格 |
| `bspline_opt/src/uniform_bspline.cpp` | de Boor 求值与导数来源 |
| `traj_utils/msg/Bspline.msg` | order、traj_id、start_time、knots、pos_pts；本身缺少运行/控制代次 |
| `plan_manage/src_for_prometheus/traj_server_for_prometheus.cpp` | 10ms 定时求值 p/v/a/yaw，发布 PositionCommand，再转 UAVCommand |
| `plan_manage/launch_for_prometheus/sitl_ego_planner_basic.launch` | 单机、control_flag=0、max_vel=0.8、max_acc=6、horizon=13.5 |
| `plan_manage/launch_for_prometheus/advanced_param.xml` | 0.1m 格网、0.2m 膨胀、world 坐标；ROS1 参数基线 |
| `plan_manage/CMakeLists.txt`、`plan_manage/package.xml` | catkin/roscpp/Eigen/PCL 与实际编译源关系 |

已核对的错误位于 `pub_prometheus_command`：局部 `UAVCommand uav_command` 后对默认 ID 加一，导致逐次重复 1；stop 分支写入里程计位置和零导数后，无条件赋值又恢复旧轨迹 p/v/a。`stop_bspline` 在失去控制时置真，未提供明确新代次恢复；`ego_command_status=false` 仅禁止发布，不能证明下游已清除旧目标。未来时间分支仍可能把零向量发布出去。`bsplineCallback` 没有会话身份校验。上述是静态源码发现，未声称已编译复现。

当前 wksim 接缝：`Simulator/wksim_runtime/task.py::send` 使用 `session_v1` 的 CommandRequest（run_id/control_epoch/request_id）至 `/uav1/prometheus/v2/command`，frame_id=map；`mission_task.py::command` 考虑受理事件高水位，`cancel/land` 区分取消受理、公共降落与地面解除解锁。`mission_cancel.py` 绑定 run_id/mission_id。TRAJECTORY=6、command_id 为 uint32，见 `ros2/src/prometheus_msgs/msg/UAVCommand.msg`。规划结果须经过同一公开入口与输出修整；PositionCommand 或 Bspline 发布不代表飞控接收。

## #101 纯适配会话合同

不依赖 ROS 的 `TrajectorySession`，单一串行所有者。构造绑定非空 run_id、mission_id、uav_id=1、control_epoch、planner_generation 及已核对 command_high_water。输入事件必须包含这些身份和单调事件序号；Bspline.traj_id 不能代替 command_id。轨迹求值由真实上游完成，适配器输入有限 p/v/a/yaw 样本及 trajectory_id、generation、sample_tick、valid_until_tick，不在此文件重写规划算法。

建议冻结方法：`begin_replan(identity, event_sequence)` 返回新 generation；`accept_trajectory(identity, generation, trajectory_id, start_tick, end_tick)`；`sample(identity, generation, trajectory_id, tick, position, velocity, acceleration, yaw)`；`stop(reason, identity, event_sequence, anchor)`；`next_output(tick, owns_control, state_fresh)`。拒绝返回结构化 reason 且不消费命令 ID；输出是公共命令意图字典或 None。方法实现前可补类型，不得改变以下语义。

1. 状态为 WAITING、ACTIVE、HOLD、CANCELLED、RELEASED、FAULTED。初始 WAITING 没有运动输出。接受同代新轨迹不清零任何 ID。每次实际输出分配严格大于所有已分配及合法观察高水位的 command_id，范围 1..4294967295；溢出 FAULTED，禁止绕回。request_id 由公共发布所有者独立递增，不能混用。拒绝、重试、重规划不回退高水位；对发送失败也不复用已分配 ID。
2. 同 tick 优先处理身份失效/失去控制/陈旧状态，再处理 cancel/no-route/replan，再处理轨迹样本。cancel 或 stop 立即使旧 generation 失效、清空待发样本。失去控制输出 None 并进入 RELEASED；不得发 MOVE、LAND 或模式夺回命令。陈旧状态 FAULTED 且无运动输出，由已有生命周期处理失联。
3. 正常拥有控制且状态新鲜时，no-route/replan/stop 进入 HOLD：一次锁定反馈位置与偏航，输出 XYZ_POS、零速度/加速度/偏航率；之后保持相同锚点，不每周期追随漂移。停止参考采用独占分支，不再进入轨迹字段赋值。取消进入 CANCELLED，后续运动样本全拒绝；允许移交已有任务取消/降落流程，适配器本身不解锁、不强制 disarm、不结束物理进程。
4. replan 在启动新计算前递增 generation，旧结果即使迟到也拒绝。等待期间只能 HOLD；仅显式 begin_replan 对应的新 generation、有效起止 tick、有限样本可激活。no-route 保持 HOLD；重试须显式新 generation。取消后不能以自动重规划解除，须新 mission 身份。运行/控制代次变化使旧会话永久终止；进程重启须获得新身份，不能在旧 epoch 下从 1 恢复。
5. 只接受有限向量、三阶轨迹、非空有效时间区间与严格单调样本 tick；未来/过期/重复/逆序/错误身份样本拒绝。轨迹结束切换终点 HOLD；禁止延长旧速度。样本失效时以新鲜反馈锚点 HOLD。wall-clock 状态超时继续服从产品现有检查；ROS 暂停不消除墙钟超时。
6. 单写者持有 command_id 分配权。暂停/模式外切后重获控制需要现有显式接管流程和高水位同步，不能由上游 EMERGENCY_STOP 自动恢复运动。有意差异为停止优先、代次隔离、显式恢复和 ID 持久高水位，保留 EGO 的实际轨迹数值含义。

必要单测：活动样本与 stop 同 tick；连续 stop 锚点稳定；两个轨迹之间 ID 连续；cancel 后迟到样本；no-route 后旧结果；replan A/B 乱序完成；错误运行/代次/载具；未来/过期/NaN/空轨迹；ID 最大值与发送失败；状态陈旧/模式外切；新身份重启；终点零导数保持。#101 交付后命令为 `python -m unittest validation.test_trajectory_session -v`，目前该入口尚未交付，不计通过。

## 固定地图与运行 profile：ego-single-box-v1

这是从上述真实参数接口派生的确定性输入定义，尚无已运行场景产物。ENU、米、秒、yaw 弧度；world→map 仅同原点同轴更名，禁止隐式坐标旋转。一架载具，两栈分别验证，共享同一地图/profile，不承诺多机。

- 地图原点 (-10,-6,0)，尺寸 (20,12,6)，分辨率 0.1；地面 z=0、虚拟天花板 z=5.5。起飞后规划起点 (-4,0,3)，目标 (4,0,3)。保留正常地面初始化/起飞/接管，不把机体直接放在空中。
- 唯一实心障碍 AABB [-0.5,0.5] × [-1,1] × [0,5.5]。点云为该盒内所有0.1m体素中心，按 x/y/z 索引升序；无随机地图。物理碰撞盒和点云来自同一几何定义、记录各自哈希及转换，#29 准入必须证明两者一致。
- 格网 inflation=0.8m（相对上游0.2m的预先固定有意改动），local_update_range=(9,7,6)，max_vel=0.8m/s、max_acc=6m/s²、max_jerk=4m/s³、horizon=13.5m、重规划间隔1s、control_flag=0、样条求值10ms。其他优化参数继承哈希锁定的 advanced_param.xml。关闭随机初始化/扰动路径，后继必须核实真实代码是否支持并保存展开后的参数；无法固定时视为准入失败。
- 点云输入走 cloudCallback 的世界坐标，不走 scanCallback 的局部变换。未知空间不能当作已验证自由空间；首次地图到齐前禁止接管。需验证局部裁剪和上游固定 z 膨胀实际效果。

以下是运行前固定的附加场景门槛，不替换原物理精度或 #33 倍率预算：

| 场景 | 判定 |
| --- | --- |
| 绕障到达 | 60仿真秒内真值距目标≤0.5m、速度≤0.5m/s持续2秒；全程无物理接触，机体保守包围球半径≤0.35m，球表面至障碍净空≥0.30m |
| 连续净空 | 每个物理tick检查真值扫掠线段到盒的距离减半径；漏tick或只有规划轨迹/显示数据则不通过。模型包络大于0.35m则本profile不准入，不缩小碰撞体 |
| 无路 | 新 case 将障碍改为 x∈[-0.5,0.5]、y∈[-6,6]、z∈[0,6]，封死整个截面；启动规划后5仿真秒内报告 no_route 或 planning_timeout 并 HOLD，后者只能记安全停止，不能称算法证明无路 |
| 取消 | 真值首次到 x=-2.5m 时提交绑定身份取消；消费后下一个10ms适配tick无旧轨迹输出，≤100ms墙钟进入公开停止/降落请求；实际3仿真秒内速度≤0.5m/s，仍需净空成立；最终按原降落门槛真值|z|≤0.3m且解除解锁 |
| 重规划 | 新case在x=-2.5m触发目标改为(4,2,3)，立即作废旧 generation；5仿真秒内有真实新轨迹，否则安全 HOLD 并判本case失败；乱序旧结果不得受理，到达门槛同上 |
| ID/退出 | 实际公共输出全程严格递增且无跨代重放；取消受理、公共ACK、物理完成分别记录；最终只收尾本run拥有的进程 |

连续轨迹参考50/100Hz转换、DDS开销与原100ms预算须由 #33/#102 实证，不事后放宽。`Task.send` 当前逐条等ACK，不能据其存在宣称已经支持100Hz流式轨迹。

## 证据、许可与未知项

证据输出 schema：source-audit.json 包含 head/branch/upstream/files(path,sha256,upstream_blob,upstream_equal)、源文本检查与票据快照。后继整场原始证据必须记录 run_id/mission_id/uav_id/control_epoch/generation、地图/profile/模型/二进制/ROS类型哈希、整数物理tick、真值、接触、公共请求及ACK、停止事件、规划成功/失败与原始样条。审计输出各场景单独 verdict/reasons，缺字段不得 PASS。

根 LICENSE 明示 Apache-2.0，EGO plan_manage/package.xml 却为 TODO；这仅是仓库文本事实，不能推断所有嵌入依赖均已完成许可确认。保留作者/来源；EGO 与 bspline_opt/path_searching/plan_env/traj_utils 及第三方依赖的完整许可对应关系须在迁移/再分发前核实。本次不复制或新增分发算法源码。

未验证：ROS1→ROS2安装与规划运行入口、展开launch缺省参数、确定性优化配置、实际模型包围球、物理地图绑定、无路状态输出桥、取消到原生保持/降落的延迟、两栈轨迹控制与倍率、真实绕障。#29/#33 OPEN；#102 的源码写权缺口须另行解决。没有启动 FC/model/ROS/UE 进程，R1、RateUnmet、Full及父票不因本合同改变。

本次准确复核命令：`python validation/lunar-100-contract-20260909-01/audit_source.py`。该命令只检查本合同的来源身份和静态发现，不测试规划或飞行。实际模型/推理：用户指定 gpt-6-astra/low；当前工具未提供独立会话设置核验，实际具体 ID/档位未验证；无子代理。
