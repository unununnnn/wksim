# OMP ArUco 协调器/实验准入只读审查（主会话新接线）

日期：2026-09-11。对象：`tools/run_aruco_tracking.py`、
`Simulator/wksim_runtime/joint_aruco_profile.py` 及 config/runtime/factory 接缝。
只读审查 + 接口测试；未改任何实现；未启动 ROS/SITL/UE/原生构建；未 commit/push；未嵌套。
接口证据来自真实留存 `validation/40-aruco-flight-scene-03/`（90 帧、真实 Consumer
target、盘上场景 manifest），未重新仿真。

## 接口测试（实际命令与结果）

```powershell
work/dependencies/aruco-python/Scripts/python.exe -B -m unittest validation.test_run_aruco_tracking -v
```

**9/9 OK（0.014s）**。覆盖：协调器 `observation()` 对前 5 个真实帧产出的记录逐条通过
任务侧 `_validate_observation`（target.step/frame_id 与 capture 外层一致，真实
run/epoch/instance/stream 身份）；真实场景 manifest（case_id=5、anchor_valid、
first_step）驱动 binding；外来帧身份/篡改/错配拒绝；`episode_ready` 真实身份形状
正负例；`atomic_json` 原子替换无残留；`validate_experiment` pin 校验；
`validate_joint_config` 三角门（任务/实验 profile/pin 缺一即拒）；实验 profile
`experimental=True`、`production_admitted=False`、capabilities 仅本任务。

## 核验为正确的接线（附实际位置）

- 配置门：`joint_config.py:24-34`（ARUCO_TASK 必须配 ARUCO_PROFILE + 显式
  aruco_experiment pin；三者缺一即 ConfigError）。
- 准入分发：`preflight.py:162-163` 按 runtime_profile 走 `joint_aruco_profile.check`；
  `joint_runtime.py:275-276` capabilities 门不变。
- 任务装配：`joint_runtime.py:252-258` 给每栈 settings 注入 aruco_settings
  （profile 读自同目录冻结文件、scene_directory=WSL epoch/aruco、binding/observation
  路径在其内——与任务侧 `validate_aruco_settings` 的目录约束吻合）；`joint_task.py:44,80`
  仅该任务类型构造 JointArUcoTask。
- 跨端路径：Windows 侧 `unc()`（validate_joint_visual.py:20）把 WSL epoch_dir 映到
  `\\wsl.localhost\...`；写侧 `atomic_json` tmp+`os.replace`，WSL 任务侧
  `read_bounded_json` 拒 symlink/超大文件。两端写读均有原子/有界保护。
- 初始禁用证据链：协调器 `:129-130` 检查 `rgb_enabled False` + manifest
  `anchor_valid:false`/`first_step:-1`；真实 scene-03 初始 manifest 证实这些字段存在。
- episode 结束边界：协调器 `:186-187` 用 profile scene 四段之和（=12000）与任务侧
  `episode_steps` 同一来源，一致。
- 每轮 `reader.set_epoch`/`consumer.bind` 同绑定重入在 Reader/Consumer 既有规则下是
  no-op，不清历史。

## 需要主会话处理/决策的具体点

1. **epoch 中途切换是整运行失败而非重绑**：`run()` 的 `binding` 一旦建立不随新
   epoch 更新；新 epoch 首帧触发 `observation()`（`run_aruco_tracking.py:60-62`）
   “Cannot publish a frame from a different binding” → 失败。对有界 12s 候选这是
   安全语义，但请在 runbook/审计预期中写明，避免误判为缺陷。
2. **observation 的 generation 未对帧通知复核**：`observation()` 只核对 metadata 的
   run/epoch/instance/stream（`:60-62`）；metadata 本身无 generation 字段，真实
   generation 门在 `Reader._read`（rgb.py:86-87，对绑定代次校验通知事件）。当前
   链路成立，但 observation 记录不含通知事件身份，独立审计需从 Reader 侧
   `reader_rejected`/原始通知补 GID/代次核对——请确认审计器输入清单覆盖。
3. **image_sha256 在观测层只做格式校验**：任务侧 `_validate_observation` 无法重算
   哈希；真实完整性核对必须发生在独立审计（重算 PNG SHA 对照观测值与
   `report.frames[].image_sha256`）。当前无代码缺陷，但这是审计器的硬性输入要求。
4. **peer 观测消费无对账**：协调器只写 scene_dir/observation.json，不核实 peer 栈
   任务读到 binding；`episode_ready` 只读 tracking-ready.json。若 peer 未装载，
   场景仍会跑完——审计需用两端 result.json 的 binding/episode_end 一致性补齐。
5. 无其他阻断性缺陷；上述均不阻止当前候选运行，但 2/3/4 决定独立审计能否成立。

## 边界

未启动任何真实运行；测试只用留存证据与临时目录。agy 的 aruco_raw_capture 三文件、
Claude 的 PX4 构建资源、主会话在接的 raw-CDR 模块均未触碰。#104 仍未完成。
