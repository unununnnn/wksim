# OMP 联合 ArUco 跟踪 Task（514743f 后续切片，r2）

日期：2026-09-11。仅改本切片三文件；冻结的 UE 四文件、aruco_task.py（071c7fc）、
aruco_tracking_input.py、target_intent.py 未动；factory/admission 未改；profile 数值未改。
未运行 ROS 节点/SITL/UE/MATLAB/编译；未 commit/push；未嵌套；raw RCTake 仍未安装。

## r2 主审修复（6 点）

1. 前缀 cmd 序列用真实枚举锁定：`[SET_PX4_MODE, ARMING, SET_CONTROL_MODE] = [1, 0, 3]`
   （WSL 真实 UAVSetup 实测 0/1/3），`test_prefix_sends_the_real_setup_enum_sequence`
   验证实际发送序列、字段与默认值，非字符串比对。
2. 常驻 latest 文件：同 sequence 且内容逐字节相同 → 不喂 seam、不重发 MOVE，仅用当前
   step 让 adapter 复查缓存过期；同 sequence 内容变化 = 篡改拒绝；序号回退拒绝。
   缺文件且无缓存记录 → 显式 HOLD（seam.update(None)+hover，重复抑制），MOVE 不遗留。
3. `_authority_step` 改用 joint ROS clock 原始 nanoseconds 整除 1e6（舍位不四舍五入），
   回退即 RuntimeError；测试用真实 ns 值（101000000→101，101999999→101，回退拒绝）。
4. send 覆盖只对 `aruco-tracking-` 前缀标签注入 profile 受理超时 0.5s；
   setup/arm/LAND 等保留 Task 默认 10 与显式 40（LAND 超时回归已锁定）。
5. `_validate_observation` 增核：target.step == capture_step、target.frame_id ==
   外层 frame_id（容忍 Consumer 的十进制字符串形态，拒绝 bool）；generation 严格
   int（True 伪 1 拒绝）；binding 的 first_step 不得处于当前权威未来、
   episode_end 不得溢出 MAX_STEP；binding/observation 读取经 `read_bounded_json`
   （拒绝 symlink/非常规文件、>64KiB 拒绝）。
6. 构造核实 flight_stack 与固定 joint uav_id 映射一致（arducopter→1/px4→2）。

## 测试（实际命令）

- Windows stub（非 ROS 运行）：`python -B -m unittest validation.test_aruco_joint_task`
  → **19 ran，OK（skipped=1：symlink 创建在 Windows 主机无权限）**。
- WSL 真实 ROS 消息类（仅构造消息）：`ROS_MESSAGES: True`，**19/19 OK**（含 symlink 负例）。
- 邻居回归：test_aruco_tracking_input + test_aruco_public_commands **46/46 OK**。

## 身份

- `Simulator/wksim_runtime/aruco_joint_task.py` SHA256 `5ae3b0210c918b0f2e1289a440e52a8ea71afdd47f6d27d9bae25ff2797b25ea`
- `validation/test_aruco_joint_task.py` SHA256 `5b55fc2dd85420b2714603be45009d913e9ad8d5b282e6f17dee026ede32c774`

## 仍未完成

真实飞行、raw-CDR 链、独立同场审计器、factory/admission/profile 接线（主会话）。
adapter 的 `last_command_id=0` 假设（前缀不消耗公共 command_id）保持不变并由测试锁定。
不称 #104 完成。
