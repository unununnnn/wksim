# 原生等待的有界线程采样

`tools/sample_joint_threads.py` 是外部只读诊断工具，不改变亲和性、优先级、信号或内核开关。它从指定run的status/config/children绑定run、epoch、完整进程argv及PID/PGID/start_ticks，逐批在读取前后复核进程身份，逐线程保留start_ticks并校验读取前后身份。正常state/CPU计数变化不会丢样；Z/X退出或PID变化会立即退役该目标，不继续跟随复用PID。

输出使用全新目录，保存header/sample/target_retired/error/close与result；包含host_boot_id、CLK_TCK、sched_schedstats原值、每批读取耗时、采样器自身线程CPU、实际样本与线程行数、源码及日志SHA。空/重复目标、非整数频率、非法时长和行数超界拒绝。启动校验失败也保留header/error/close，不伪造有效run身份。

主会话发现并修复了epoch入口多一层目录、整stat变化误丢忙线程、僵尸误认为存活等问题；修正了独立测试的目标fixture和构造期拒绝预期。14项WSL检查通过，包含真实自建短命进程和PID/TID变化、忙线程、行上限及输出拒覆盖；没有运行SITL。

当前内核为WSL2 6.6.87.2，`sched_schedstats=0`、`CLK_TCK=100`。runqueue计数必须标记不可用，不能用零值证明无调度等待。CPU/线程状态和观测间隔仍可记录，但不足以单独判定Windows/WSL/飞控根因。采样自身开销也属于需要评估的实验条件。

下一场计划在tick10000附近启动一次40s、50Hz的采样，目标为该run的supervisor、arducopter-fc、px4-fc，覆盖第16场起飞前峰值所在区间。记录真实开始/结束，不以预设刻度伪造覆盖。采样器与运行器分别退场；不把带探针结果当作无探针性能保证。

为了固定诊断启动代次，主会话启动了600s自有WSL保活进程（非WSL配置修改）：boot_id `87e04105-21a5-41fd-a4ea-11f182fe8eb7`，PID/PGID599，start_ticks330，工具session74832；约06:31:42 JST开始。实验结束核验身份后关闭或等待其有界退出，不延长为永久后台服务。
