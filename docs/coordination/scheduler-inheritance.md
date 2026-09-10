# 实时策略继承的实际核验

第九场在tick65088再次rate_unmet，尚未完成场景；这证明大报告收尾处理不是唯一问题，原结果保留。

原监督器先设SCHED_FIFO/50，再创建普通Control、DDS Agent、Task子进程及后台日志/ROS线程。仅给普通子进程调整nice并不会把它们从实时调度类降回普通类。一次只操作自有短命Python进程的真实WSL试验确认：原方式的子进程与新线程均为FIFO/50；父进程使用SCHED_RESET_ON_FORK后，二者均为SCHED_OTHER/0，而父进程保持FIFO/50。

证据为`validation/coordination/scheduler-inheritance-probe.json`，可用`tools/probe_scheduler_inheritance.py`复现。该证据说明继承行为，不证明它是全部倍率故障的唯一原因。

后续ArUco实验启用该重置标志：普通子进程与背景线程不再意外继承监督器实时等级；模型/飞控主线程仍通过原child_priority显式设置FIFO/40。启动时读取所有自有进程/线程的实际策略与优先级，结果记入scheduler_snapshot。其它联合任务当前策略不变；未改任何全局系统设置、物理步长、组节拍、许可或100ms门槛。
