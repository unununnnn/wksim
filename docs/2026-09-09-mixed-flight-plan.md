# #33 真正 XY 速度 / Z 位置首次运行合同

2026-09-09，首次mixed运行前冻结。profile为xy_velocity_z_position_yaw_v1；固定PX4与独立新AP mixed候选，通过同一session_v1公共命令运行，0.5×共同权威时间。准备起飞/位置基线、限时900墙钟秒/180000tick、原100ms倍率限制及10s±2%/60s±1%均沿用P+V实验框架。非finite/溢出、未支持帧/轴组合必须拒绝；本场不完成全部原生异常边界或正式提升。

起飞保持5s、[2,3,3] ENU位置基线（距离≤0.5m、速度≤0.5m/s、yaw误差≤0.15rad持续2s）后按下列顺序进行。正常混合运动准备上限20仿真秒，达到XY逐轴速度误差≤0.3m/s、Z误差≤0.5m、yaw误差≤0.15rad后，连续检验3s；持续窗口任何违例即失败，不能靠瞬时过点。

| 阶段 | 公共命令 / 固定参考 | 持续检验 |
| --- | --- | --- |
| world_step | XY_VEL_Z_POS，Vxy=(0.8,0.4)，Z=4m，yaw=0 | 3s混合跟踪；高度目标明显区别于初始3m |
| world_reverse | 同模式，Vxy=(-0.4,0.6)，Z=3m，yaw=0 | 3s混合跟踪及改向 |
| world_one_axis | 同模式，Vxy=(0,0.6)，Z=3m，yaw=0 | 准备2s，X速度≤0.25m/s、X漂移≤1m，Y误差≤0.3m/s、Z/yaw原界，持续4s |
| world_zero | 同模式，Vxy=(0,0)，Z=3m | 准备2s，速度≤0.25m/s、距此次回中时实际位置≤1m、Z/yaw原界，持续4s；shaper转完整P，X延续当前one-axis锚点、Y新捕获，AP原生mask0x9F8 |
| invalid_world_yaw_rate | 仅AP：混合模式yaw_rate_mode=true | 受理前以arducopter_mixed_requires_yaw_angle拒绝，2s保持无副作用；PX4不冒称拒绝其已支持的模式 |
| world_reentry | 同模式，Vxy=(0.4,-0.3)，Z=3.6m，yaw=0 | 3s跟踪，验证P保持后重新进入真实mixed |
| world_absolute_stop | CURRENT_POS_HOVER + ABSOLUTE_CONTROL | 准备2s，速度≤0.25m/s、漂移≤1m、相对停止时yaw误差≤0.15rad持续4s |
| body_heading | 在刚才实际位置发XYZ_POS，yaw=0.6，EXIT_ABSOLUTE_CONTROL | 原位置/速度/yaw界持续2s；明确解除停止 |
| body_step | XY_VEL_Z_POS_BODY，body Vxy=(0.8,0.4)，相对Z=+1m，相对yaw=+0.3 | 首次解析后按固定ENU速度/绝对Z/yaw连续3s跟踪，转向过程中速度不能每tick重新旋转 |
| body_zero | 同BODY模式，Vxy=(0,0)，相对Z=0，相对yaw=0 | 从该次实际位置重新捕获完整P，准备2s后按停止/高度/yaw原界保持4s |
| body_absolute_stop / LAND | 再次CURRENT_POS_HOVER + ABSOLUTE_CONTROL；最后LAND + EXIT_ABSOLUTE_CONTROL | 按上述停止速度/漂移/yaw界准备2s/保持4s，再正常落地、最终公共状态与原始真值均确认 |

所有high-level velocity_ref的Vz仍按既有shaper/oracle为零前馈哨兵，AP adapter明确转换成原生IGNORE_VZ。AP运动期Pxy失活、Pz/Vxy/yaw有效，map/frame6/mask0x9E3；其lat/lon/Vz默认零只是失活载荷，不是XY位置目标。PX4沿用原shaper的Pxy NaN、Pz有限、Vxy有限/Vz=0的原生接口，不能将其零前馈说成原生NaN。两XY回中转完整P，必须保持实际新锚点而非原点。

BODY坐标在CommandProcessor第一次step解析时一次捕获，保持既有行为；控制节点新增只读mixed_body_reference_captured事件，记录该瞬间源位置/四元数/偏航、解析参考和shaped轴，不改变控制或输出，也不代表原生发送/ACK。审计从真实公共状态四元数独立重算旋转，结合实际原生包和逐1ms真值证明一次捕获。捕获事件可早于首次受输出频率限制的发送，不能用后来的姿态替代。

被动记录器与控制节点按已验证的恰好两个具名订阅端点检查，保持source/GID/run/epoch记录；使用现有pv-dds.jsonl作为同一原始消息容器，文件名不代表本次为完整P+V。原生AP GUIP日志（实际Log.cpp名称）必须出现新type7，结合真实native binary/源码/映射证明进入新子模式；其pX/pY零为失活占位，pZ属于origin NED，不能直接冒称home高度。Location/Fence转换失败、native timeout、native pause/EKF reset/避障等异常工况仍需独立运行，不以本正常场景代验。
