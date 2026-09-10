# Claude：连续原生 setpoint 的"原生 ACK / 动作完成"边界（只读核对）

约束：真实 run 14-ap（session36716）进行中，本片纯只读核对，未运行任何测试/构建，
未改 runtime/auditor/test，未嵌套，未 commit。

## 原条款（逐字）

- #104 运行合同 `docs/plan/40-aruco-run-contract.md`：
  - :7 / :97 「#104 完成条件要求两栈同场真实证据」。
  - :24-29 HOLD 语义：「控制处理器每周期重新解算最近一次接受的 MOVE 命令……
    不发布不会停车」，故 HOLD 必须显式发布 CURRENT_POS_HOVER。
  - :92-93 「同场证据绑定：图像、目标、CDR 控制记录、物理真值必须共享同一
    run/epoch/step；回放只能做接口测试（#40 AC4）。」
  - :100-101 独立原始审计器从原始证据重建四阶段，「拒绝重放帧、跨 epoch
    拼接与诊断速度冒充命令」。
- `docs/plan/goal-objective.md:40` 项 4：「命令受理、原生ACK、任务接管、动作完成
  分别报告；拒绝不能悄悄降级为另一种控制能力。」
- `docs/coordination/omp-aruco-public-commands.md:66`：「`ack_scope` 明确指公共
  `command_accepted`，不是原生飞控 ACK 或动作完成。」
- 现有 raw auditor UNCOVERED 逐字（`tools/audit_aruco_tracking_raw.py:69-70`）：
  `native_fc_ack_or_action_completion: only public TextInfo acceptance is proven; no native FC ACK or action completion is claimed`

## 源码事实：连续 setpoint 没有可要求的原生 ACK

- PX4（`native_px4.py`）：VehicleCommandAck 只挂在**离散 VehicleCommand** 上——
  订阅表 :50-55 中唯一 ACK 通道 `('ack', VehicleCommandAck, 'vehicle_command_ack')`；
  匹配带严格身份与防回退（`unmatched_ack` :70、`old_ack_source` :74、
  `regressed_ack_progress` :81，按 command+timestamp+(target_system,target_component)
  挂 pending，结果 `native_result_<n>` :325 / `native_ack_timeout` :328）。
  连续流 `send()` :233-254 / `send_global()` :256-267 只 publish
  OffboardControlMode + TrajectorySetpoint/VehicleAttitudeSetpoint，发布侧无任何
  ACK 等待；docstring :5 自述「matching native ACK; actual mode/arming completion
  is separately observed.」
- AP（`native_arducopter.py`）：订阅只有 Status 与 WksimState（:70-72）；
  `cmd_gps_pose`(GlobalPosition)/`cmd_vel`(TwistStamped) 为纯发布（:73-74），
  fire-and-forget。原生确认仅存在于离散 ROS 服务 ArmMotors/ModeSwitch/Takeoff
  （:75-77），`poll_request` 返回 `native_service_accepted/rejected/failed` 或
  `native_ack_timeout`（:370-390）。
- **结论**：ArUco 跟踪 MOVE 流的连续速度/位置 setpoint（PX4 TrajectorySetpoint /
  AP cmd_gps_pose+cmd_vel）在协议上不存在原生 ACK 通道。"等待连续 setpoint 的
  原生 ACK"是不可能被满足的要求，不得凭空新增；公共 `command_accepted` 仅是受理，
  不得改述为 native ACK。

## 原合同应如何被现有证据满足（按 goal-objective 项 4 分层报告）

1. **受理**：公共 `command_accepted`/TextInfo——已有，`ack_scope` 已界定。
2. **原生下发**：raw CDR 中真实 native setpoint 与请求逐字段一致——
   `tools/audit_aruco_native_holds.py` 已在真实 10/13-ap 中段证明
   （AP 11 段/169 样本、PX4 14 段/165 样本字段级精确，单 publisher GID）。
3. **飞控执行/动作完成**：逐 tick 1ms 物理真值 + 飞控反馈（PX4
   vehicle_local_position、AP wksim/local_state_v1、SessionState CDR）共享同一
   run/epoch/step，收敛/保持以反馈与物理真值判定。这正是 :92-93 同场绑定与
   :100-101 审计器重建的既有语义——**不需要、也不存在一个额外的 "setpoint ACK"**。
4. 末尾 HOLD 已由 83a8f90 的 boundary<native<state 次序补严
   （见 `claude-final-hold-review.md`）。

## 尚需证据（不新增要求，只在下次真实运行补齐）

- 14-ap（进行中）结束后：末尾 HOLD 段原生窗口按 83a8f90 语义闭合——10 的末尾
  HOLD91 有 SessionState 无 native 样本、13-ap 的 HOLD90 被同 tick LAND91 替代，
  两处 pending 需新运行覆盖。
- PX4 setpoint 载荷内 `timestamp` 未另行比对（native_holds 以 RMW
  source_timestamp 归属样本），仍 pending。
- graph 范围 publisher 排他身份另行验收，不在本片。
