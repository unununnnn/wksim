# OMP ArUco 原生 MOVE 审计器（BODY 速度 → 原生设定值）

日期：2026-09-11。范围：仅新增 `tools/audit_aruco_native_moves.py`、
`validation/test_aruco_native_moves.py` 与本文；不改任何已有源码/审计器；
不改 tracking-08 的 failed 判定；不运行节点/仿真/构建/压缩/重索引；不 nested。
本切片只回答 BODY 速度 MOVE 是否成为预期原生设定值，不含 HOLD/飞行判定。

## 时序推导的源码实读核验（未被推翻）

- `command.py:87-96`：yaw 由归一化 `state.attitude_q` 经 atan2 得出 ✓
- `command.py` step：BODY 命令首次 resolve_move 后缓存 body_reference ✓；
  resolve_move 对 XYZ_VEL_BODY 用 rotate_xy(yaw)、z 不旋转 ✓
- `shaping.py:87-91`：yaw_rate_mode=True 直接返回速度 + float32 rate 并 reset，
  不走 deadband ✓
- `node.py:538-` on_command 只 accept 不 drive ✓；tick 先 native.state → drive
  （发原生设定值）→ 再 publish SessionState（`:672-702`），SessionState 含
  uint64 sequence ✓
- 原生归窗：按 RMW source_timestamp 归到 [本请求参照 state, 下一已执行请求参照
  state)（含 hover 等任意已执行请求闭窗，非只看 MOVE）；参照 state = 该 rid 首个
  SessionState，要求相邻序号连续、同 control_epoch、时间有序 ✓

## 实现要点

- 独立旋转/量化实现（自写 quaternion_yaw/rotate/NED 换算），不调用生产
  resolve_move/shaping 自证。
- 只接受冻结场景：MOVE(4)/XYZ_VEL_BODY(4)/yaw_rate_mode=True/yaw_rate_ref=0，
  其它命令排除不判。
- PX4：TrajectorySetpoint NED f32 速度、position/acceleration/jerk/yaw 全 NaN、
  yawspeed=-rate（-0.0）；f32 位级精确比较。AP：cmd_vel TwistStamped/map ENU
  double 精确比较。无任意物理容差。
- 每个已证明 MOVE ≥1 原生样本且窗口内全部一致；无样本/无参照 state/合并未执行
  → unresolved，不造匹配。
- 原始链：按 aruco_raw_capture 的 canonical-JSON 规则独立重算 record_sha256 并核对
  prev 链接（断链/篡改均拒绝）；核对 run/epoch/uav/request/command ID 单调与一致；
  原生发布者 GID 唯一性。**唯一观测 GID ≠ 全图发布者排他性**——列入 uncovered。
- 状态：failed（有违规）> pass（≥1 证明且无 unresolved）> unresolved。
- 已知证据边界：tracking-08 的 AP 侧 raw 捕获无 `/ap/cmd_vel` 行（要么未发布要么
  未订阅）——审计将如实给 unresolved，不作证。

## 测试（实际命令与结果）

WSL 真实消息类（仅构造/序列化，无节点无 DDS participant）：
```sh
source /opt/ros/humble/setup.bash; source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash
python3 -B -m unittest validation.test_aruco_native_moves -v
```
**9/9 OK**。Windows：**9 skipped**（无消息 overlay，明示）。
覆盖：坐标轴/偏航公式、单 MOVE 位级通过、1 ulp 漂移即拒绝、无原生样本→
unresolved、合并未执行→unresolved、SessionState 序号缺口→失败、哈希链断→失败、
双发布者 GID→失败、非冻结命令变体排除。

## r2 退修与真实运行结果（2026-09-11 跟进）

主审定点修复（仅工具/测试/本文）：
1. `quaternion_yaw` 改用 `math.hypot` 归一化（与 command.py update_state 数值一致，
   非 sqrt 平方和），保持 double 位级一致、无容差。
2. 原生样本严格上下界：previous_state.source < sample.source < following_state.source；
   等号为歧义样本，记录为 unresolved 从不归属；bisect 定位替代全扫描。
3. control_epoch 取命令/SessionState 证据（控制会话代次），与 raw start 的场景 epoch
   明确区分；uav_id 接受 int/str（真实捕获为 int）。
4. AP 期望轴向不交换（生产直接写 target.velocity 进 Twist.linear）；归窗改为逐样本
   映射到同 tick 随后的 SessionState 归属 last_request_id，覆盖首帧/末帧错位。

真实实跑（x 模式新文件，旧失败输出保留）：
- `omp-native-moves-10-v2.json`（PX4 选中，epoch e77b1ed4…）：**pass，72 MOVE 证明，
  0 失败 0 未决**；PX4 原生样本 1281、GID 唯一；AP peer 无 MOVE 无样本（正确）。
- `omp-native-moves-13-v2.json`（AP 选中，epoch 3662bc05…）：**pass，74 MOVE 证明，
  0 失败 0 未决**；AP cmd_vel 637、GID 唯一；PX4 peer 无 MOVE（正确）。
- 回归：WSL 真实消息类 **14/14 OK**；Windows 14 skipped（明示）。
- 早前 `omp-native-moves-10.json`（v1 审计器，control_epoch 误配 + uav 类型假阳性）
  保留作失败演进证据。

身份 SHA256：工具 `1192209a…`、测试 `46d8c4a2…`、10-v2 `5446bc52…`、13-v2 `cbce943b…`。
末尾 HOLD/LAND 的证明属主会话补齐范围，不影响本 MOVE 判定；tracking-08/10/13 的
整体运行判定均未改。

夹具要点（实现纪律）：yaw 必须取四元数归一化反推值（名义值差 1 ulp 即拒绝）；
velocity_ref 是 float32 线上类型，期望值必须从 f32 化输入计算。

## 身份

- `tools/audit_aruco_native_moves.py` SHA256 见下
- `validation/test_aruco_native_moves.py` SHA256 见下

主会话可在第十场结束后运行：
`python3 -B tools/audit_aruco_native_moves.py <epoch_dir> --output <新文件.json>`

主会话最终复核：补充审计器及逐raw文件SHA256，关闭文件句柄，并拒绝SessionState相同source_timestamp。14项真实ROS消息检查通过；对10/13重新运行分别72/74 MOVE逐字段pass、0失败0未决，新输出aruco-10-native-moves-final.json和aruco-13-ap-native-moves-final.json。此工具必须与550f0f6的同run完整raw/provenance审计配套使用；不把本工具的单一观察GID视为发布者发现图证明，末尾HOLD缺口也不在MOVE范围。
