# 原生时间戳补证与循环诊断范围

时间戳审计已完成主审：PX4从后随同tick SessionState的sample时间、ENU位置和速度唯一确定先前实际反馈，再比较TrajectorySetpoint.timestamp与该VehicleLocalPosition.timestamp。两个时间字段不混同，也不把已发布但尚未消费的更新反馈强当作当前参考。AP要求原生消息header与同tick后随状态精确相等，且为合法非零启动微秒值。歧义保留unresolved，不跳过后授予通过。

21项检查通过。AP第15场618 MOVE样本+173 HOLD样本=791个，PX4第10场620+165=785个载荷时间戳全部通过。后者不能补造其没有发布的末尾HOLD，也不能补出未记录的writer图。第15场AP闭环各项已有同场证据；PX4采用后续修复的完整场仍未通过，#104继续OPEN。

`loop_timing.py` 与 `joint_runtime.py` 新增的循环边界探针只沿 `WKSIM_JOINT_CPU_TIMING=1` 启用。它记录管理、pacing、physics、clock_publish、clock_evidence、group_end_and_view的墙钟/线程CPU区间。pacing正常等待不当作慢计算；非pacing总耗时>2ms、每250tick或未完成的调用才输出。原核心内部三阶段探针仍保留，可结合定位未覆盖耗时。

关闭探针时不读额外时钟、不输出诊断。物理→时钟发布→证据→组结束/显示的次序、原始JSON载荷、物理步长、输入屏障、100ms门、原子重锚规则不变。诊断记录失败不能变成成功，原有RateUnmet不会被次级诊断错误遮住。31项针对性检查通过，包括真实advance函数的调用次序、pacing失败不推进物理、组结束原异常保留和日志失败传播；不是实际倍率通过证明。

Codebase Memory索引已检查，图查询定位ClockPublisher.publish，当前源代码随后直接读取；没有依赖未覆盖的新模块图，也没有无必要地重建大索引。下一实测用于观察新增边界，不放宽任何门槛。
