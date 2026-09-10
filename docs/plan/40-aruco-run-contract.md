# #104 · ArUco 相机闭环运行合同

状态：2026-09-11。运行入口与独立审计已实现。AP第15场已完成真实图像→公共命令→原生MOVE/HOLD→物理轨迹与退场核验；PX4对应新修复第16场在起飞前倍率失败，仍需完整场验证。原生载荷时间戳已在AP第15场和PX4第10场补证；PX4修复后的完整场仍待通过。#104/#40及Full保持OPEN，不能把单项通过或普通飞行采集当作完整闭环验收。

## 实际接口与执行边界

`tools/run_aruco_tracking.py` 在Windows协调真实UE RGB；联合模型、飞控与公共任务在WSL运行。显式profile为 `joint_quad_dds_aruco_experimental_v1`，task为 `aruco_tracking_experimental_v1`。`joint_aruco_profile.py`严格检查候选资源，`JointArUcoTask`通过session_v1公共入口执行。

| 环节 | 实现 | 契约 |
| --- | --- | --- |
| RGB | `Simulator/ue55/rgb.py` Reader | 当前View的新stream、真实PNG/元数据及通知代次一致 |
| 观测 | `wksim_perception/aruco.py` Consumer | 完整run/epoch/instance/generation/stream/vehicle/sensor/step/frame身份，PnP输出机体系FLU |
| 意图 | `target_intent.py`、`aruco_tracking_input.py` | 观测相对位置减期望位置；只有新鲜目标产生XYZ_VEL_BODY；诊断世界速度不进入命令 |
| 公共发送 | `aruco_task.py`、`aruco_joint_task.py`、Task.send | MOVE=4、XYZ_VEL_BODY=4、yaw_rate_mode=True、yaw_rate_ref=0，command_id单调且不回绕 |
| 失效撤回 | ArucoCommandAdapter | 发送CURRENT_POS_HOVER替代缓存速度；重复或过期目标不得继续MOVE，公共接受不等于原生完成 |
| 末尾HOLD | JointArUcoTask._wait_final_hold_native | 仍解锁且处于COMMAND_CONTROL；本请求的真实SessionState之后必须有更新的原生位置目标及其后随状态，才允许LAND |
| 原件 | `aruco_raw_capture.py` | 原始CDR、完整writer GID及RMW时间戳、连续哈希/计数/start/end；错误原件保留 |
| writer身份 | `aruco_publisher_guard.py` | 就绪绑定、每次公共发送前、每1s和报告前查询图；具体Control节点/类型/完整24字节GID固定，额外writer或换GID失败；逐收到样本校验 |

每次只有selected_stack构造相机接缝并发视觉命令，另一架起飞后保持、在同一episode_end降落。#104操作步骤3的每栈单独运行，要求各自图像/目标/CDR/真值来自同一run/epoch，不能跨场拼接。两架参与者必须同时存在并共享joint权威。

权威时间来自joint ROS纳秒时钟向下取整为1ms步，不以Windows墙钟推进。绑定来自实际joint状态和启用RGB后新stream，且在两任务完成起飞/稳定条件后建立。尚未绑定禁止视觉MOVE。step整数上界9007199254；run_id遵循项目运行ID规则，epoch/instance/stream为hex32。

外来身份、未来/过期/重复目标不能当新鲜反馈。坏帧不清去重高水位；同epoch可显式换新stream，退役身份不可复活；冷重置按新代次重新绑定。目标丢失时不发布不等于停车，必须显式HOLD或撤权。末尾等待沿用0.5s ROS预算，超时失败，不伪造native ACK。

## 已冻结预算

唯一配置源为 `Simulator/wksim_runtime/aruco-tracking-v1.json`，其原字节SHA被协调器、两任务及retained source共同绑定。以下是现有值，不是根据结果调整的新预算。

| 类别 | 冻结值 |
| --- | --- |
| 相机 | 1920×1440，水平FOV90°，位置[30,20,10]cm，quaternion_xyzw=[0,0,0,1]，每100步，front_rgb |
| 标记/感知 | DICT_6X6_250/ID23/边长0.5m；age≤300步、distance≤8m、speed≤2m/s、jump≤0.5m、reprojection≤1px |
| 控制 | desired_body_flu_m=[2.3,-0.32,0.06]，gain=0.6/s，speed≤0.5m/s |
| case5 | 出现2000、移动4000、遮挡2000、恢复4000步；目标world velocity=[0,0.25,0]m/s |
| 任务 | 初始保持5s，绑定超时30s，视觉命令受理超时0.5s，半径≤5m，高度2.4..3.6m，倾角≤0.35rad |
| 跟踪 | 全区间误差≤0.65m，恢复最后1000步误差≤0.3m；包含全部12,001个边界tick |
| 时钟/倍率 | 1ms模型步，原四tick输入屏障，0.5×；100ms累计迟到门、禁止追赶/暗中重锚；完整10s窗2%、60s窗1% |

图片几何/速度审计继续使用 `audit_aruco_flight_scene.py` 的2px/0.035m/0.12m/s门与各阶段样本要求。Consumer门与独立几何审计门分开报告，不互相替代。单次短相机任务没有完整60s双机空中窗时，不可称完整三epoch G2通过。

## 已存在的运行命令

先具备并通过固定资源预检：当前Control FWBLNX、PX4 land候选7RjMjQ、AP clock-stop基线、生成模型库与UE55候选。两个candidate JSON保存实际manifest路径及SHA；外部依赖缺失或不同即拒绝，不凭目录名宣称复现。

从仓库根执行，每次使用尚不存在的输出目录；以下名称是新运行示例：

```powershell
& work/dependencies/aruco-python/Scripts/python.exe -B tools/run_aruco_tracking.py --manifest validation/ue55-build-f0409a874ed243cdbad4ac9cb38d886d/candidate-manifest.json --candidate validation/aruco-tracking-candidate-01/candidate-arducopter.json --output validation/40-aruco-new-ap-01 --async-evidence --async-model-evidence --write-timing --cpu-timing
```

PX4改用 `validation/aruco-tracking-candidate-01/candidate.json` 和另一个全新输出目录。两个candidate只在selected_stack不同。显式后台日志使用有界队列，满或写/关闭错误即失败；默认路径未推广。监督器FIFO50+RESET_ON_FORK，模型/FC leader显式FIFO40，模型后台线程需RESET；实际策略保存在每场快照。异步模式不改变日志字节或模型物理步骤。

## 独立验收与留存

| 入口 | 范围 |
| --- | --- |
| `tools/audit_aruco_tracking_physical.py <capture-root> --output <new.json>` | 实际PNG几何、逐tick跟踪/恢复/包线、落地、writer完整退场 |
| `tools/audit_aruco_rate.py <capture-root> --output <new.json>` | 同场原始计划、累计迟到、完整倍率窗口 |
| `tools/audit_aruco_tracking_raw.py <capture-root> --output <new.json>` | 公共/CDR/provenance/失效-HOLD-恢复；自身返回pending，原生项目另验 |
| `tools/audit_aruco_native_moves.py <capture-root>/run/epochs/<epoch> --output <new.json>` | BODY引用状态及真实原生速度逐字段匹配 |
| `tools/audit_aruco_native_holds.py <capture-root> --output <new.json>` | post-MOVE冻结位置/HOLD原生窗口，含终态；初始接管另由任务前缀验证 |
| `tools/audit_aruco_publishers.py --run-root <capture-root> --output <new.json>` | 完整raw/Task/源码身份、具体writer、图快照与收到的样本；只声明采样时刻排他 |
| `tools/archive_aruco_tracking.py <capture-root>` | 原件逐成员SHA校验与有序32MiB分片，不纳入依赖二进制/厂商资产 |

物理审计使用包含OpenCV的Python；原生CDR审计在实际固定ROS overlay中执行（当前 `source /root/wksim-joint-control-FWBLNX/install/setup.bash`）。所有输出必须是新文件，保留失败；由 `tools/audit_aruco_native_timestamps.py <capture-root> --output <new.json>` 补原生载荷时间戳核对；全部同场门未闭合前不关闭本票。

连续DDS setpoint没有原生ACK通道。公共受理、原生下发、离散服务/VehicleCommand的原生ACK和实际动作完成分别报告；以原生字段、飞控反馈与物理真值共同证明闭环，不新增不可能的setpoint ACK要求。

运行器的 `captured_pending_independent_audit` 只表示采集/退场完成，不是闭环总验收。证据索引见 `docs/2026-09-11-aruco-tracking-15.md`；历史失败与PX4第10场末尾HOLD缺口保持原判，不能用新代码重放旧场补造通过。
