# #38 RC位置控制来源与接缝

2026-09-09只读准备，未实现RC入口、发送RC值、切换控制模式或修改原ROS1基线。按[已批准批次](2026-09-08-five-decisions-accepted.md)，RC属于C2，实际执行仍在C1速度/混合轴之后；GitHub原生依赖之外也保留这一已批准顺序。本文不关闭#38，也不以参数维护或公共位置任务代替RC实测。

图导航先读取index_status和detect_changes，快照2026-09-08 12:13:51 UTC、50865节点/165157边。宽泛查询仅用于定位，随后收窄到uav_controller.cpp的RC方法，返回3项/has_more=false；set_hover_pose_with_rc的一层入向图定位mainloop（LSP0.95）。实际源码已读取，覆盖检查为no_recorded_issue但metadata_changed，未据此作全库完整性声明；tools与外部固件仍直接读源。之后没有进行依赖本轮新增运行器结构的图查询。

## 源码事实

- `Modules/uav_control/include/rc_input.h:116–238` 接收mavros_msgs/RCIn，前四通道以(pwm-1500)/500归一化，死区0.05，死区外重缩放。源码注释的yaw/thrust排列容易误导；应以实际执行映射为准。
- `Modules/uav_control/src/uav_controller.cpp:452–472` 以delta_t积分位置/偏航：x += ch[1]×1.5m/s×dt，y -= ch[0]×1.5m/s×dt，z += ch[2]×1.3m/s×dt，yaw -= ch[3]×1.5rad/s×dt。公共世界坐标积分，没有把水平杆量旋转到机体系；高度目标下限0.2m。回中后保存积分目标，实际飞行仍有到达该目标的过渡，不能称回中即瞬时停止。
- 原通道5负责解锁/上锁沿，6负责INIT/RC_POS_CONTROL/COMMAND_CONTROL，7触发kill，8触发LAND。px4_rc_cb要求已解锁才处理位置模式，RC→COMMAND还检查OFFBOARD；这些原生前提不能用模拟RC取消。
- `check_failsafe:1054` 的1.5秒RC超时只在!sim_mode生效。迁移的模拟源也需要真实失效策略，不能照搬此豁免后宣称断流已验收。
- 原handle_rc_data在访问0..7通道前未检查长度，check_validity只打印部分通道错误并继续，前四通道也无整体输入范围拒绝。这些是移植前要明确修正的边界，不修改保存的上游基线。
- 当前ROS2 `command.py:112–146,210` 已有RC_POS_CONTROL枚举、进入时捕获hover的基础，但step仅返回未更新的hover，注释明确杆量积分未移植。`node.py:368–370` 对非COMMAND_CONTROL设置返回control_setup_mode_not_implemented。不能因为枚举存在就宣布RC已支持。

## 后续最小实现边界

先锁定一个明确命名的软件RC模拟源和独立输入信封：run/control_epoch/stream/sequence、产生与接收新鲜度、固定通道数/范围及单位。读入原始杆量后由产品模块执行上述死区与位置积分；实验驱动不预积分成位置命令来冒充产品RC。第一切片只做位置/偏航及显式模式交接，其他通道的解锁/kill等行为必须逐项声明支持或拒绝，不能隐式启用。

在运行前明确输入刷新率、积分时基/最大可接受间隔、1.5秒来源规则是否适用、断流的具体保持/撤销行为。已有联合100ms倍率合同不能直接冒充RC输入预算。正常运行时间按单机场景或权威联合时间分别处理，输入失效检测仍保持独立接收时钟；暂停、重置或新stream不会使旧杆量重新生效。

Control主机需要实际承接RC_POS_CONTROL与COMMAND_CONTROL的显式交接，核对新鲜定位、已解锁和原生模式。外部模式切走、输入过期或旧epoch必须撤销对应许可，重新接管需要新决定，不能自动抢回。输入可表达、处理器受理、原生发布/模式反馈和物理移动/回中保持/偏航须分开记录，最终双栈实飞并独立审计。

上述是待执行接缝，不是已冻结的新增RC协议或新数值预算。C1前置、输入合同与安装控制包提升都需要各自证据；后续实施继续沿原票据验收。

实际读取SHA256：rc_input.h为807e34f6aa460547543f9401a49570118d2552d8061c7aa3615caba856602124；uav_controller.cpp为9b0ed230a6629612bb65fc21460153dc337c0a3167d0513baa5e8a54a301f1ab；ROS2 command.py为5a37a7e1a00fe3764796ec3e5c1688d681a4ab30edc8a95b6c603324577d0d2f。
