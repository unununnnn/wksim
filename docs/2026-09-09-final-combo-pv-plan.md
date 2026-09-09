# #33 最终 mixed/control 组合的 P+V 兼容性合同

2026-09-09。此文件冻结可执行的候选兼容性入口；没有宣称最终组合已实飞，也不修改旧 PV/mixed 飞行记录。原 PV baseline `joint-public-flight-qi66lh_y` 与 mixed nominal `joint-public-flight-zk5_nukn` 使用不同组合或开关状态，不能替代本合同。

仅接纳 AP `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`（SHA256 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`）和控制 `/root/wksim-joint-control-OEvS3W/build.json`（SHA256 `d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e`）。mixed verifier 保留完整源码快照、补丁、二进制及 mixed→PV→fixed 链核验；没有伪造 PV manifest。任务身份是 `full_xyz_pv_yaw_v1`，固件身份仍为 mixed；结果使用 `mixed_admission`。

实际 AP 控制启动同时传入 `arducopter_pv_profile:=full_xyz_pv_yaw_v1` 与 `arducopter_mixed_profile:=xy_velocity_z_position_yaw_v1`。此后 mixed 候选入口也使用相同双开关。旧 PV manifest 路线保持原单 PV 开关；旧 mixed 审计仍识别单 mixed 开关，并在 `identity.control_profiles` 如实输出，不能用它冒充双开关覆盖。

运行命令（由主任务预约串行执行；本实现阶段不启动 SITL）：

```bash
bash tools/run-joint-flight.sh \
  --task-profile full_xyz_pv_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-OEvS3W/build.json \
  --control-sha256 d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e
python3 -B tools/audit_pv_trajectory.py validation/ACTUAL_NEW_RUN --output validation/ACTUAL_NEW_AUDIT.json
```

审计命令须在项目既有 ROS/message 环境中执行；`ACTUAL_NEW_RUN`、`ACTUAL_NEW_AUDIT` 由真实运行输出替换，审计输出不得写入原始证据目录。PV 审计显式分派到真实 mixed 身份审计，再执行原 PV 逐包/原生目标/每 1ms 物理/连续倍率检查。保留 mixed-source、PV 基线构建、八份原生文件、控制安装源码与执行源封存，并记录复用 mixed 身份审计器的 SHA。

物理合同完全继承 [P+V 冻结合同](2026-09-09-pv-flight-plan.md)：两段各 12s XYZ P+V/yaw 轨迹，每 1ms 检查位置 ≤0.5m、逐轴速度 ≤0.3m/s、yaw ≤0.15rad；端点准备/保持各 2s，两次停止准备 2s/保持 4s，速度 ≤0.25m/s、漂移 ≤1m，第二段使用实际新锚点，最后显式退出绝对控制并正常 LAND。0.5×、100ms 迟到限、全部完整 10s/60s 滑窗 2%/1% 限及最终停止边界保持不变。

仅此新原始审计 PASS 才能证明最终组合的 P+V 正常场景兼容性。正式 profile/任务的准入与实跑由独立接线完成；加速度执行、yaw-rate、原生异常边界和持续 1×仍按各自合同处理，不能从本结果推出。没有安排额外 native timeout 重试或放宽任何原门槛。

首轮 `joint-public-flight-z5ediqxp` 在起飞阶段因原倍率门槛失败，全部证据保留。后续候选入口沿用正式运行器的启动顺序：两个Task先完成恰好两个具名订阅端点的传输初始化；只读worker快照须证明tick0/state=null，加载映射和完整哈希也在物理计时前完成。此阶段不授予命令权限，原ready/go仍必需。之后才连接并推进物理，唯一倍率锚仍始于首个同步屏障；没有活动段中途重锚、缩短驻留或提高迟到容差。启动等待限15墙钟秒，仍在整轮900秒上限内。
