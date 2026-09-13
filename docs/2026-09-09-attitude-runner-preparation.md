# #34 独立运行入口准备

2026-09-09。原票要求分别证明 PX4 和 ArduCopter 的姿态/推力阶跃，并未要求联合时间场景。本轮新增明确的候选入口和任务，不修改生产 profile，也不把 #20/#33 的倍率失败抹除。两栈请求独立 speedup=1；真实目标发布间隔与 native/物理时钟须记录，不能从 40 Hz 配置推断实际频率。

`tools/run-attitude-flight.sh` 建立独立 network/IPC/mount namespace 和 `/dev/shm`；`tools/run_attitude_flight.py` 使用新输出目录、候选准入、实际安装路径、旧启动形状及公开 Task 流程。默认不开飞：候选身份检查与真实飞行结果分别归档。任务正常完成仅记 `observed`，须独立原始审计才能记 PASS。

新 `tools/attitude_physics.py` 为进程内显式观察包装，复用原 AP/PX4 协议/Lockstep，将一次持相同输入的 n 步调用拆为 n 次原生 1 ms 调用，并记录每步120输出、16输入及组关系。生产 Model/wrapper 没改；原降采样 truth 继续用于在线游标，不以插值补缺口。

实际等价验证先声明200组×4步、前三十组零输入、后续四电机正弦变化，其余通道零；两个新原生进程分别执行原4步和拆分观察版。最终每组120输出共24,000值完全一致；800条观察记录输入/步号/组号/末步输出核对通过。证据 `validation/attitude-physics-equivalence-20260909/summary.json`；两份组输出 SHA256 同为 `24fbb859fd8023bc97b12a72b9018504633fab155a2baa3b4c1ac67cd8262ec8`。此实验只验证观察包装不改变受控重演输出，不是姿态飞行或 G6。

AP 使用全新存储。固定候选 `ArduCopter/Parameters.cpp` 的 GUID_OPTIONS 默认0，两个既有默认参数文件均未覆盖该值；单独 `attitude.parm` 加 bit3=8、GUID_TIMEOUT=3，动态 DDS 参数文件仍最后。任务必须在解锁前实读并核验这些值，同时记录其余标定相关原生参数；不在适配器里暗改参数。

尚未执行本入口真实飞行；本文件只记录构造与观测等价验证。冻结 flight-budget 的数值和失败动作不变。
