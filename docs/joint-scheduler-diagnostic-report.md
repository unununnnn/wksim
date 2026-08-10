# 联合倍率：WSL 调度与写入取证

本批完成取证器修复和一次有效的地面诊断窗口。**没有完成1×的60秒空中验收，也没有改物理步长、四tick输入屏障、100ms迟到门槛、日志缓冲或产品调度策略。** 按用户要求，本批提交后停止继续推进。

## 结果与实际证据

旧#62失败日志经现有JointRate重放，精确重现tick7588、100,312,171ns迟到。1,887组中70组超过4ms；累计相位增量99.621ms，其中前组执行超期贡献73.637ms。原始失败未覆盖。重放在`validation/rate-remediation-ff63c72/replay.json`。

本次有效诊断为`/root/wksim-scheduler-probe-35728b1-03`，run=`scheduler-445190199c96`，epoch=`60f3d9cd76be469a9153f64d0aef0578`。未启动飞行任务；保持原8-vCPU运行树设置，开启既有阶段CPU采样，并使用独立tracefs实例。

| 写入路径 | 完整系统调用数 | 中位耗时 | P99 | 最大耗时 |
| --- | --- | --- | --- | --- |
| AP模型真值文件 | 9,934 | 6μs | 59μs | 428μs |
| PX4模型真值文件 | 9,934 | 6μs | 59μs | 170μs |
| AP模型RPC stdout | 9,934 | 3μs | 15μs | 341μs |
| PX4模型RPC stdout | 9,934 | 2μs | 14μs | 393μs |

共39,736组write进入/退出配对，未见短写/失败返回，也未见超过1ms的写调用。另有88,118个sched_switch和40,005个sched_wakeup事件；所有CPU的已知丢失计数为0。主采集窗口10.000355936秒，前面另有0.5秒请求时长的名称映射准备窗口。打印跟踪时间为微秒精度，边界缺半个调用/调度区间不补造。

整个被测地面段约11.02秒，有2,738组，末组起始相位迟到69.926ms，52组超过4ms。最长组1924→1928耗时12.00962ms，位于内核采集窗口内；tick1926的`native_inputs`阶段耗时8.098026ms，监督线程CPU为0.653392ms，`health_and_models`仅0.322997ms。依据当前`finish_inputs`源码，tick1926不是四tick边界，此时等待的是AP下一帧输入。这是本次最长组中可确认的等待位置，尚未追踪AP飞控各线程，不能进一步归因于某个飞控线程或Windows主机机制。

本窗口没有复现先前15.8ms的模型日志写入长尾，因而没有足够证据据此改写日志缓冲策略。短地面段的GREEN重放仅表示该段未跨100ms，不替代三epoch、60秒空中窗口或倍率验收。

## 修复的取证问题

1. **WSL PID命名空间错配。** 自有canary中，Ubuntu看到PID601，内核sched事件却报告1015。原采集器直接用Ubuntu PID过滤，产生空文件；第一场原先报告complete的结果已明确撤回为无效空采集。
2. **多线程名称歧义。** 解释器启动时命名监督进程会使ROS辅助线程继承同名，第二场被唯一映射守卫正确拒绝。改为私有`sitecustomize.py`只在精确绑定的监督主线程首次进入物理advance时命名，ROS线程此时已初始化；两模型进程仍在自身启动时命名。
3. **准确过滤与空结果拒绝。** 先用三个独有comm名称的sched事件得到内核PID，再启用数值过滤。仍用`PID:start_ticks`、boot_id、run/epoch argv核验可见进程。没有启用无过滤的全系统跟踪；空主trace不再判complete。
4. **收尾验证。** 采集器清理自己的唯一实例；驱动独立核对管理进程组及每个epoch组均为空。13项离线守卫/解析/归因/收尾检查通过，实际保留结果的epoch收尾也已复核。

临时命名钩子仅复制到该次输出目录，并经该次子进程的PYTHONPATH启用；未安装全局sitecustomize，未改变生产worker或supervisor源码。三个诊断运行均已退场；私有tracefs实例均删除，全局tracing_on/current_tracer/trace_clock与采集前一致。`docs/Prometheus.gitmodules.reference`的其他工作区修改不属于本批，保留未动。

## 可复制入口与归档

- `python3 -B tools/profile_joint_scheduler.py --output /root/wksim-scheduler-probe-<新名字>`：资源预检、独立地面场景、namespace映射、10秒主采集与公开stop收尾。输出目录必须不存在。
- `python3 -B tools/analyze_joint_scheduler.py <上述目录> --output <新的分析JSON>`：读取原始write/sched事件，区分可运行等待、唤醒前阻塞及未知区间，并关联rate组和阶段CPU记录。
- `python validation/rate-syscall-scheduler-plan-20260909/test_collect_tracefs.py`及`python -m unittest validation.test_joint_scheduler_analysis -v`：离线检查，不启动仿真。
- [归档清单](../validation/rate-remediation-ff63c72/archives.json)保存三场全部原始目录压缩件SHA和退场核验；probe-01为空采集，probe-02为歧义拒绝，probe-03才是有效诊断。canary与旧失败重放单独保留。

有效场的七份运行输入源码已逐字节核对并存于原始归档的`source-copies/`。后续驱动仅增加了epoch收尾的防误判检查，由离线用例和该场原始结果核验；没有宣称重新启动一场飞行。分析器版本由输出中的SHA绑定。
