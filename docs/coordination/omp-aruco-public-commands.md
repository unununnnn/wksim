# OMP ArUco 接缝 → 公共 UAVCommand 适配器（514743f 切片，r2）

日期：2026-09-11。范围：仅改本切片三个文件；`aruco_tracking_input.py` 与
`target_intent.py`（主会话修订，36 项回归已过）只读未动；joint.py（Claude Code
独占）、模型生成驱动（agy 独占）及其余 control/runtime 文件未动。未启动 SITL/UE/
ROS 节点/仿真/DDS participant；未 commit/push；未改 Issue；未嵌套。

## 交付

| 文件 | SHA256 | 角色 |
| --- | --- | --- |
| `Simulator/wksim_runtime/aruco_task.py` | 见下 | `ArucoCommandAdapter` r2：接缝记录 → 真实公共 UAVCommand |
| `validation/test_aruco_public_commands.py` | 见下 | 15 项离线合同测试（WSL 真实消息类 + Windows stub） |
| 本文 | — | 身份、结果、剩余调用点 |

## 本轮 4 项审查修复

1. **首个 HOLD 不再抑制**：`_last_sent` 初值 None 时首个 HOLD 明确发送
   CURRENT_POS_HOVER（宿主 Task 可能在本适配器创建前已发过 MOVE，该设定值在
   control `step` 中持续生效）；只有本适配器自己确认发过 hover 且其间无新命令时，
   重复 HOLD 才记 `suppressed_hold`。原"首个 HOLD 抑制"测试已替换为接手旧 MOVE 的
   回归（`test_first_hold_sends_hover_replacing_a_possible_host_move`）。
2. **当前权威时间**：`process(record, *, authority_step)` 为必需参数（调用者提供，
   回退即 ValueError，不猜测）。MOVE 按 intent 的 capture step/`valid_until_step`
   校验：捕获步在未来 → 拒绝；当前步已超有效期 → **不发布**，降级为 hover 路径
   （`expired_move:<原reason>`）。重复处理同一记录步 → `duplicate_record` 幂等不发；
   更早记录步 → 重放拒绝。HOLD 按自身记录步判定，不继承旧 MOVE 有效期。
3. **command_id 高水位**：构造必需 `last_command_id`（宿主已用高水位，显式校验非
   bool/int≥0），首个发送从 high-water+1 起；与 session request_id 无关。回归：
   宿主已用 7 → 适配器首发 8。
4. **发送失败留痕**：`Task.send` 已发布但 ACK 等待异常时，关联记录保留
   `command_id` + `send_failed`/`ack_unconfirmed` + error，序号已消耗不复用，异常
   原样传播；成功路径记录 `ack_unconfirmed:false`。外来/非法记录在构造消息/消耗
   id 之前拒绝（`test_send_failure_keeps_the_consumed_id_and_propagates`、
   `test_foreign_or_illegal_records_rejected_before_any_id_spend`）。

保持：真实枚举（MOVE=4/XYZ_VEL_BODY=4/CURRENT_POS_HOVER=2/DEFAULT_CONTROL=0）、
`Task.send` 复用（session_v1 请求号、control_epoch、ACK、原始日志）、无飞行默认值、
不起飞/落地/运行器/桥接逻辑。

## 测试结果（实际命令）

WSL（真实 ROS 消息类，仅构造消息，未启动节点/仿真）：

```sh
cd /mnt/c/Users/PC/Documents/odid编译/wksim
export PYTHONPATH="/root/wksim-ros2-MUlZd0/install/prometheus_msgs/local/lib/python3.10/dist-packages:/opt/ros/humble/lib/python3.10/site-packages:/opt/ros/humble/local/lib/python3.10/dist-packages:$PWD"
python3 -B -m unittest validation.test_aruco_public_commands
```

结果：`ROS_MESSAGES: True`；**15/15 OK（0.014s）**。
Windows stub（显式非 ROS 运行）：**15/15 OK**。

## 剩余调用点（主会话合入）

1. 联合任务内：`ArucoCommandAdapter(self, seam, scene_epoch=<joint epoch>,
   last_command_id=<宿主已用高水位>)`；每权威步
   `adapter.process(seam.update(...), authority_step=<当前权威step>)`；
   `send` 的 ACK/超时语义沿用 Task。
2. `adapter.actions`（含失败留痕）并入任务报告，供独立审计对齐
   原始图像/目标/CDR/真值与 command_id。
3. profile 白名单/任务工厂接线按 `docs/plan/40-aruco-run-contract.md` 既有清单，
   无新增需求。
# 主会话最终复核补充

主会话补齐了缓存 MOVE 到期仍触发悬停（去重不能先于过期检查）、重复处理也推进当前权威时间高水位、ACK 未定的 MOVE 后重新要求悬停、畸形 MOVE 字段拒绝且不消耗序号，以及 uint32 内层 command_id 禁止回绕。`ack_scope` 明确指公共 `command_accepted`，不是原生飞控 ACK 或动作完成。

Windows 编排检查与 WSL 消息构造检查各19项通过；最终源码/记录由主会话提交。调用方仅在新图像目标或明确丢失事件时更新 TargetIntent；无新帧时可让发送器在当前权威步检查缓存记录的有效期，不应反复把同一图像当新目标送入 TargetIntent。真实跟踪运行器、联合 profile/任务工厂与独立物理审计仍未完成。
