# ArduCopter 停传感器后 SIGTERM 不退出：精准诊断

2026-09-06 JST。Prometheus→wksim #8 决策前有界地面调查的唯一停止侧线。全部真实验证已结束；13 次 AP 均回收，自建 AP 进程组均为空，随后离线复查记录的 AP/调试器 PID 均不存在。已通知主线可开始其 FC 实测。本报告不是生产修复、空中停止验收或 G2 完成。

## 发现

**固定 AP 的 SIGTERM 已设置退出标志，但停流后的 JSON 收包重试不检查该标志，主线程不能返回 HAL 外层退出检查。** 这不是只凭源码推断：SIGTERM 五秒后真实主线程仍在 `JSON::recv_fdm → SocketAPM_native::recv → select`；调试器只读检查 `_should_exit` 所在字节为 **1**。随后不再发信号，仅恢复真实模型传感器，AP 在另外两个 1ms 步后输出 `Exitting` 并返回 0。无调试器重复同样成立。

关键一手证据：[退出标志和线程栈](../validation/ap-shutdown-hz_ha1zu/gdb.txt)、[该次原始结果](../validation/ap-shutdown-hz_ha1zu/result.json)、[无调试器恢复结果](../validation/ap-shutdown-c6c6wjas/result.json)、[退出日志](../validation/ap-shutdown-c6c6wjas/ap.log)。

与其形成单变量对照：保持物理输入推进时，SIGTERM 在 6.26–8.60ms 内退出 0；只关本次隔离实例的 DDS，停流后仍 RED/-9；SIGINT 在停流时两次均约 3.2ms 返回 -2。**SIGINT 的绿色只表示满足退出时限，是信号终止，不证明正常清理或日志持久化。**

## 固定身份、范围与方法

- AP：`/root/wksim-ap-dds-yaw-state-4Wr27s/build/sitl/bin/arducopter`，SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`；`src` HEAD `1511f27194f1dcc3728270883047bdf022b3fd53`。每次先做既有 `preflight`，再检查实际二进制和 commit。
- 模型：复用现存 `/tmp/wksim-model-5swsjm5f/libwksim_model.so`，SHA256 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`。原模型库/归档/包装器和构建清单继续经既有预检，不重写或重新构建它们。模型与原报告相同；本轮只有一个 Model 实例，直接在探针进程逐 1ms 调用。
- 每次新建 net、ipc、mount 命名空间和私有 `/dev/shm`，仅 loopback；全新 `/tmp/wksim-ap-stop-*` cwd/EEPROM。AP 使用 `start_new_session=True`，信号前逐次核对 PID、start_ticks、pgid、argv，信号只发自建 AP 组。
- 复用 `launch_spec`，沿用原真实 AP 启动参数、地面模型参数和只读遥测流率文件；默认 DDS_ENABLE=1。仅 DDS 对照一次使用本次 cwd 中的 DDS_ENABLE=0，未改飞控源码、全局参数基线或健康检查。
- 仅接收 MAVLink 心跳和真实 AP 执行器包；原始遥测字节完整记录。断言系统 241、未解锁、零归一化电机输入、真实模型 `abs(z)<0.1m`。发送的 JSON 不含 RC/飞行命令，`no_lockstep=false`、`no_time_sync=false`。
- 未启动 PX4、ROS 节点、DDS Agent、UE、QGC、CopterSim 或真实硬件。原 AP PID828/start_ticks19268 和 Windows UE35256 未作为操作或 `/proc` 诊断目标。
- 不导入或修改主线 `probe_joint_clock.py`，不要求主线正在修改的文件 SHA 保持不变；只读既有 Model、AP JSON、runtime/preflight/config/isolation 源码。

每份 `start.json`/`signals.json`/`result.json` 保存 AP 身份，`before-signal.json` 和红色时的 `after-five-seconds.json` 保存该 AP 各线程的 `/proc` 信息。每次独立证据目录保存当时两份探针源码，失败尝试也保留。所有研究输出集中于本报告；没有嵌套代理。

使用 `diagnosing-bugs`：先执行确切症状反馈环、重复和有界最小化，再公开四个预测并作单变量验证；旧联合地面报告仅用于定位资源，没有替代 red loop。`research` 要求的一手来源和单文档归档用于本报告；按用户禁止嵌套代理的指令直接完成研究。wksim 无独立 `docs/adr/`，未将兄弟 AeroTwinSim ADR 当成本迁移决策。所读工具按已有覆盖说明排除在图外，固定 WSL AP 源不属于本仓库图，使用已知文件直接读源；WSL 无 `rg` 时回退 `grep`，没有安装工具或重建索引。

## 可复现反馈环与最小化

在 WSL Ubuntu-22.04/root、wksim 目录运行：

```bash
bash tools/run-ap-shutdown-probe.sh
bash tools/run-ap-shutdown-probe.sh --ticks 2000
```

第一条确实执行过两次。第一次输出：

```text
Evidence: .../validation/ap-shutdown-10as6lxo
verdict=RED returncode=-9 signal_wait_seconds=5.0019633320043795
owned_group_remaining=false error=null
```

Python oracle：0=在五秒内退出；1=达到地面后发指定信号，五秒仍存活；2=前置/隔离/身份/地面证据不足或其他实验错误。RED 的判定在任何后续恢复、GDB 或 SIGKILL 前完成；`--resume` 最终即使退出 0，也保留 RED 和探针非零退出，不能把症状抹成通过。墙钟信号等待使用 `monotonic()`，总反馈循环有 45 秒上限，GDB 另有 10 秒上限。

原 10,004 tick 症状在去掉 PX4、第二模型进程、跨进程模型 IPC、双机屏障和暂停/单步流程后仍出现。再只缩短 AP 地面前置时长：1,000 tick 无未解锁心跳，INVALID；2,000 tick 两次独立 RED。最小有效循环约 6 秒，主要是用户指定的五秒信号观察窗。

这里的“最小”是**保留固定候选准入和可信地面证据的有界最小化**；没有穷举 1001–1999 tick 或删除每一个固定默认参数，不能宣称数学意义上每个残余元素均必要。隔离、身份和地面判据不能为缩短实验而移除。2,000 tick 已足以在稳定反馈中检验停止机制。

## 四个预先列出的可证伪假说

| 顺序 | 测试前预测 | 单变量证据与结论 |
|---|---|---|
| H1 停流使 JSON 等待阻止退出 | 只将信号后的传感器流改为继续推进，SIGTERM 应退出 | `ct2rpfsj` GREEN/0；完整前置时长 `bpupsbej` GREEN/0。支持停流是该复现的触发条件 |
| H2 SIGTERM 被忽略/未设置标志 | 信号掩码或实际退出标志应显示未受理；SIGINT 可能不同 | `_should_exit=1`，各线程 SigBlk/SigPnd/ShdPnd=0，SigCgt 包含 TERM，推翻“未受理”；INT 两次 -2 是不同终止路径 |
| H3 外层退出检查被内层收包循环阻隔 | 五秒后栈应在 JSON 等待；不重发信号而恢复传感器应推进退出 | `g9cgtb8z` 栈采样；`hz_ha1zu` 标志+栈+恢复，及无 GDB 的 `c6c6wjas` 恢复均吻合 |
| H4 DDS 线程是必要原因 | 只将隔离实例 DDS_ENABLE 改为 0，停流 TERM 应退出 | `ogwvhnln` 仍 RED/-9，推翻 DDS 是必要原因 |

H1/H3分别检查输入依赖和具体阻塞位置，不能当作两个独立根因。GDB 在五秒判据之后才附加，因此不影响已产生的 RED；恢复实验再以无 GDB 版本排除附加调试器是恢复所必需的解释。`--resume` 不发额外信号。

## 全部实际尝试

目录名前缀均为 `validation/ap-shutdown-`；所有信号窗口单位为墙钟秒。未列出的选项为 DDS=1、停流、SIGTERM；正常实验均有未解锁心跳和零电机输出。

| 后缀 | 前置 tick / 唯一变化 | 五秒判据 | 等待秒 | 最终 AP 返回值 |
|---|---|---|---:|---:|
| [10as6lxo](../validation/ap-shutdown-10as6lxo/result.json) | 10004，首次独立复现 | RED | 5.001963 | -9 |
| [s2egunhz](../validation/ap-shutdown-s2egunhz/result.json) | 1000，无地面心跳 | INVALID，未发送 TERM | — | -9，仅清理 |
| [xhe5onai](../validation/ap-shutdown-xhe5onai/result.json) | 2000 | RED | 5.001970 | -9 |
| [j_13pj0q](../validation/ap-shutdown-j_13pj0q/result.json) | 2000，独立重复 | RED | 5.002256 | -9 |
| [ct2rpfsj](../validation/ap-shutdown-ct2rpfsj/result.json) | 2000，流继续 | GREEN | 0.008600 | 0，推进至2002 |
| [g9cgtb8z](../validation/ap-shutdown-g9cgtb8z/result.json) | 2000，判据后 GDB 栈 | RED | 5.000920 | -9 |
| [i2ek00ls](../validation/ap-shutdown-i2ek00ls/result.json) | 2000，SIGINT | GREEN | 0.003243 | -2 |
| [ogwvhnln](../validation/ap-shutdown-ogwvhnln/result.json) | 2000，DDS=0 | RED | 5.000152 | -9 |
| [hz_ha1zu](../validation/ap-shutdown-hz_ha1zu/result.json) | 2000，判据后 GDB/恢复 | RED | 5.000800 | 0，恢复5.160ms至2002 |
| [c6c6wjas](../validation/ap-shutdown-c6c6wjas/result.json) | 2000，判据后恢复，无 GDB | RED | 5.000379 | 0，恢复5.021ms至2002 |
| [bpupsbej](../validation/ap-shutdown-bpupsbej/result.json) | 10004，流继续 | GREEN | 0.006262 | 0，推进至10006 |
| [lqaupwld](../validation/ap-shutdown-lqaupwld/result.json) | 10004，最终原条件重跑 | RED | 5.001035 | -9 |
| [6_whkzbc](../validation/ap-shutdown-6_whkzbc/result.json) | 2000，SIGINT重复 | GREEN | 0.003292 | -2 |

最后两次检验运行过的探针源码包含离线审计入口；随后仅增强离线审计的包级断言，没有再启动 FC。总计六次有效停流 TERM 不恢复实验全部 RED/-9，两次停流 TERM 后恢复实验均先 RED 再 exit0，两次继续流 TERM 均 exit0，两次 INT 均 -2，一次无效前置尝试。

复现其他对照：

```bash
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --flow live
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --signal INT
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --dds 0
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --gdb
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --resume
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --gdb --resume
```

## 固定实际源码如何解释现场

六份实际源文件已保存于 [源码/离线审计目录](../validation/ap-shutdown-audit-0h6xpjjd/audit.json)，其 SHA256 和与固定 commit 的逐字节比较均在清单中；六份均 `matches_fixed_commit=true`。本报告不引用更新分支或网络二手说明。

1. [HAL_SITL_Class.cpp](../validation/ap-shutdown-audit-0h6xpjjd/HAL_SITL_Class.cpp) 175–195：`exit_signal_handler` 仅设置 `Scheduler::_should_exit=true`；TERM 始终注册，INT/HUP/QUIT 只在 `HAL_COVERAGE_BUILD==1` 分支注册。288–300：外层 `while(true)` 先检查标志、`exit(0)`，然后才调用 `callbacks->loop()`。实际 INT 的 -2 和掩码符合本固定二进制没有捕获 INT 的行为；不只依赖预处理条件推断构建选项。
2. [SIM_JSON.cpp](../validation/ap-shutdown-audit-0h6xpjjd/SIM_JSON.cpp) 36、302–332：接收 timeout 常量为100ms；lockstep路径 `while(ret<=0)` 不检查退出标志，也无五秒总上限。累计 `wait_ms>1000` 重发执行器。附近注释写“10 second”，**实际代码门槛是1000ms**，不按注释解释时间。
3. [Socket.cpp](../validation/ap-shutdown-audit-0h6xpjjd/Socket.cpp) 347–353、443–463：`select` 返回值不是1则 `pollin=false`，`recv` 返回 -1，并置 `EWOULDBLOCK`。因此仅打断一次等待也仍落回 JSON 的 `ret<=0` 重试。此项为源码解释，未作逐个系统调用的 strace 时序取证，不声称实际那一次 select 一定被 TERM 打断。
4. [SITL_State.cpp](../validation/ap-shutdown-audit-0h6xpjjd/SITL_State.cpp) 86–94、118–129、207–254：主线程等仿真时钟时进入 `_fdm_input_step/_fdm_input_local`，调用模型更新后才设置模拟时钟。父进程存活检查也在 `_fdm_input_local()` 返回之后；本轮没有测试杀父进程，不能把该分支当作停流退出保证。
5. [Scheduler.cpp](../validation/ap-shutdown-audit-0h6xpjjd/Scheduler.cpp) 42 与 [Scheduler.h](../validation/ap-shutdown-audit-0h6xpjjd/Scheduler.h) 53：标志初值 false、声明为 static bool。现场 GDB 能读到1，足以否定本次“标志没有设上”；没有对其跨线程/异步信号语言层语义作普遍安全证明。

现场主线程完整链为 `HAL_SITL::run → AP_Vehicle::loop → AP_Scheduler::loop → AP_InertialSensor::wait_for_sample → Scheduler::delay_microseconds → SITL_State::wait_clock → _fdm_input_step → _fdm_input_local → JSON::update → JSON::recv_fdm → SocketAPM_native::recv → pollin → select`。该链由固定二进制真实 backtrace 给出，不来自猜测的调用图。

**推断边界：** 给出持续、合法的下一模型状态可使当前主循环返回外层检查，是本次根因机制的强支持；“任何状态下只需两个包”“所有 AP 构建均如此”“任意长时间停流均可恢复”均未证实。测得的2ms模型推进和毫秒级墙钟延迟不是生产上界。没有测试其他信号、重复 TERM、EOF、关闭UDP端口、杀父进程或飞行场景。

## 审计、失败和清理边界

离线命令不启动 AP，不需要新的网络隔离：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_ap_shutdown.py --audit
```

实际输出：

```text
audit=.../validation/ap-shutdown-audit-0h6xpjjd
runs=13 all_recorded_owned_pids_absent=true
```

审计核对每次证据哈希、传感器逐tick连续/时间戳、地面z、执行器归一化为零、记录的未解锁心跳、信号身份，以及红色停流从信号发送到五秒后快照期间零传感器发送。审计读取逐次记录的自建 PID，未枚举其他任务调用栈。各 AP 已经 `wait()` 回收；每次结束通过自建 pgid 的 `killpg(pgid,0)` 检查组不存在。证据文件与临时EEPROM/log保留，没有删除材料。

取证限制和失败没有隐藏：

- 1,000 tick 的尝试因缺地面心跳中止，只做 SIGKILL 清理，没有发 TERM；它不计入症状复现率。
- 首次 GDB 采样 `g9cgtb8z` 的 AP 身份完整，但当时使用同步 `subprocess.run`，**没有另存调试器自身 PID/start_ticks/pgid**。该 GDB 正常返回0并明确 detach；其自身身份不能事后补造。后续 `hz_ha1zu` 改用独立会话并保存 `debugger-start.json`、等待退出和 PID 缺失证据。主要标志/恢复结论来自后续完整记录及无 GDB 重复。
- 一次 WSL `rg` 查询不可用后改用 `grep`；一次 PowerShell 读取错误地重复了 `wksim/` 前缀，修正路径后读取成功。它们未启动额外 FC，也未改变实验判据。
- 离线哈希审计不等于独立重建飞控、完整飞控日志持久化审计或全机器无关进程审计。preflight中的历史飞行准入字段只复核候选身份，本次没有飞行。

本侧线按主代理分配的诊断边界，不执行生产修复/回归变绿阶段；这不否定用户对完整移植实施的总体授权。生产停止的时间推进/暂停语义仍受#8未决门槛约束。保留可自动变红的真实测试接缝，并最终重跑原条件确认仍 RED；不以强杀完成清理冒称缺陷修复。

## 给主线的最小建议与交付

可供主线评审的地面停止候选是：请求 AP 停止时暂时保留真实物理输入，由同一受监督时间线继续给出合法下一状态；观察 AP 实际退出后再停止模型，并记录实际增加的tick、退出码和清理。此轮仅验证这一顺序的地面可行性，没有直接集成。暂停期间是否允许为了停止额外推进权威时间仍是主线决策，不能偷偷推进、伪造传感器或用两个包作固定假设。维持有界超时和可识别的强制清理结果。

不建议把 SIGINT/-2 改名为优雅退出；源码层可中断 JSON/时钟等待属于另一个需评审的修复范围，本轮固定二进制不改。现有生产停止策略及主线 `--native-clocks` 工作均未写入。

交付仅新增/修改：[诊断探针](../tools/probe_ap_shutdown.py)、[隔离入口](../tools/run-ap-shutdown-probe.sh)、本报告，以及本轮创建的 `validation/ap-shutdown-*` 和 `/tmp/wksim-ap-stop-*` 证据目录。旧 `joint-clock-ground-91rnpgdz`、`8o1sy6o6` 仅作资源/启动证据参考，未改写。
