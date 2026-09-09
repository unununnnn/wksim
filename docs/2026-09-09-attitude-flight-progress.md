# #34 独立姿态试验进展

2026-09-09。首轮 PX4 保留失败，尚不能关闭 #34。候选构建、默认关闭及非法输入检查、双栈真实 ROS 回环和只读准入均有独立证据；这些不替代物理响应。

PX4 实际命令为 `bash tools/run-attitude-flight.sh --stack px4 --run-id attitude-px4-01 --output-root /root/wksim-attitude-flight-px4-20260909-01`。所有模式/动作使用当前候选的公开会话命令。独立请求 speedup=1，不声称联合倍率通过。原始结果位于该输出目录的 `attitude-px4-01/result.json`，保留 ULog、CDR、原生遥测、源码副本、每1ms模型输入/120输出和原有50Hz真值。

真实悬停观测的 collective 中位数为 **0.5309605896472931**；水平2秒标定通过，原位置恢复通过。随后目标 roll=5°，接收物理游标27.36s起算，27.86s实际roll约2.7089°、27.88s约2.9451°，未达到原2°误差门。任务在固定检查窗口报 `attitude_tracking: frozen physical condition failed`，随后公开 LAND 受理并于35.64s观察到解除武装和物理地面。未运行推力阶跃，未调宽时间或误差。四个子进程全部回收，cleanup_errors为空。正式 `safe_landing` 仍为false，表示没有走成功试验的正常收尾路径；不能把失败降落称整轮通过。

该轮另有 `candidate_unchanged=false` 的记录器误报：复核前后准入均有效、固定固件/模型/Control/安装与脚本字节均一致，只是 Task、evidence、telemetry_dialect、attitude_task 在飞行时首次导入，导入模块集合多出四项。这四项早已在启动前的 `source_sha256` 和 run-source 中封存。新比对要求旧项逐个相同、新项必须匹配启动前独立运行封存；未知新模块或任一字节变化仍拒绝。两个针对性检查通过，对旧记录纯只读复算也确认资源未变。旧 result 和全部失败证据未重写，物理门槛失败不受此纠正影响。

主复核记录 `validation/attitude-run-preparation-20260909/px4-first-review.json`，驱动日志同目录 `px4-flight-01.log`。Native目标真实时间、实际控制响应和逐毫秒预算正在独立审计；接收游标不被伪称原生受理时间。AP首次独立试验已排入执行，后续结果继续追加。#20持续1×、#33最终组合倍率及Full义务不改变。

## AP 第一轮及下一步依据

AP 首次独立命令使用 `--stack arducopter --run-id attitude-ap-01 --output-root /root/wksim-attitude-flight-ap-20260909-01`。原结果同样为failed，源码及候选前后均一致；四孩子回收、cleanup_errors为空。真实hover为0.31348326802253723，水平2s标定及5°姿态窗口在线通过。独立审核的59.84–60.24s全部401步最大roll/pitch/yaw误差为0.2271°/0.1529°/0.4657°，原生GUIA和CDR一致；随后位置恢复在60.958s首次超过15°，中止后公开LAND落地。没有进入推力阶跃，保持失败。

实际BIN PARM显示 `PSC_ANGLE_MAX=0`、`ATC_ANGLE_MAX=30`、`WP_ACC=2.5`、`ATC_INPUT_TC≈0.1`。固定 `AC_PosControl.cpp` 的PSC参数为deg，正值优先限制位置控制所请求的倾角；零才沿用ATC限制，NE控制器在763行附近按它限制目标加速度。下一轮仅在本次独立候选新参数文件中使用 `PSC_ANGLE_MAX=10`，解锁前必须原生读回；保留15°物理中止包线及8s恢复要求，不改正式默认或其他增益。

PX4的ULog与固定Commander源另查明：[控制层传播诊断](2026-09-09-px4-attitude-transition.md)。27.360s的输入已为attitude-only，原生vehicle_control_mode到27.632s才退出MC位置控制，期间旧位置输出与新姿态目标共用topic。下一轮在原2s水平标定、5°阶跃及推力baseline之前加入明确的中性姿态接管，必须先收到更新后的原生使能和随后的中性目标，随后才发送首次阶跃并原样计时。该前置条件修正不用于重算或“挽救”旧失败窗口。
