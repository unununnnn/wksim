# #33 完整 P+V 候选首次实飞合同

2026-09-09，首飞前冻结。本切片仅完整XYZ位置+速度+yaw角，AP新候选和PX4固定固件以共同权威时间执行。真正XY速度/Z位置仍未实现，不能据本切片关闭#33。由用户“继续推进直到所有票据完成”“全程你自己确认即可”授权主代理实施并确认；正式固件/profile不提升。

沿用现有门槛：位置距离≤0.5m，速度逐轴误差≤0.3m/s，yaw角误差≤0.15rad；起飞≥2.5m、落地绝对高度≤0.3m；停止后速度≤0.25m/s、距新停止锚点≤1m连续4s。全部逐原始1ms真值重算。倍率0.5×，原JointRate的100ms迟到、10s±2%/60s±1%保持不变；任务/场景墙钟900s、物理180,000tick上限沿用实验运行器。

先通过已有公开setup起飞并保持5s，再执行[2,3,3] ENU位置基线、≤0.5m且≤0.5m/s、yaw角≤0.15rad连续2s。两栈各生成当前run/scene/control/vehicle和一次性token的ready文件；监督器核验两侧后发共同ROS起点（当前边界+1s），任务验证精确ready回显。

每段持续12仿真秒，归一化s=t/12，q=10s³−15s⁴+6s⁵；P=P0+ΔP·q，V=ΔP·dq/dt，yaw=yaw0+Δyaw·q。轨迹参考约每100ms发布一条公共TRAJECTORY，任意相邻参考间隔不得超过250ms，按当下共同ROS时间计算，不追发错过的旧点。验收使用连续解析轨迹与原始真值，不把参考频率当物理频率。

第一段P0=[2,3,3]、yaw0=0，ΔP=[1.5,1,0.4]、Δyaw=0.6；三轴速度均真实非零。第二段从完成停止保持后的新实际位置/yaw重新锚定，ΔP=[-1,0.5,-0.2]、Δyaw=-0.3。两段公式相同，各自两栈共用起点时刻。输入acceleration_ref保留解析二阶导数，但既有Prometheus shaper不发送A；AP mask0x9C0/PX4失活A应明确证实，加速度前馈未执行。

每段12s结束后发送精确端点P+零V，准备2s、以位置/速度/yaw原界保持2s。随后公共CURRENT_POS_HOVER+ABSOLUTE_CONTROL触发停止信号，记录当时实际状态作为新锚点，准备2s后按原停止界保持4s。第二段首条TRAJECTORY通过EXIT_ABSOLUTE_CONTROL显式解除停止；最终LAND也显式退出绝对控制。不得重放第一段旧锚点。此处验证Prometheus停止/模式族切换，不冒充GCS外部模式切换或未实现的混合轴。

全程只监听并保存实际ROS原始CDR：公开请求/状态/事件/stop信号、AP GlobalPosition/WksimState、PX4 TrajectorySetpoint/OffboardControlMode及原生状态；观察器不发布控制。保存每一物理步、原生包、clock/rate、真实加载映射、执行源码、候选manifest。公开受理、原生目标发布和物理跟踪分别审计；AP该入口无目标ACK，不把发布成功写成原生确认。原生fence/origin/timeout边界仍须后续实际专场验证。
