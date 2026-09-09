# #20/#62 下一步 syscall / scheduler 取证方案

本次只读检查 WSL 工具、内核设置和 tracepoint 格式，没有启动仿真、附加进程、启用事件、修改 sysctl、安装软件或改动生产文件。沿用已核验 Astra low，无子代理。完整环境读数见 `environment.json`。

## 现成能力

| 项目 | 实读结果及限制 |
|---|---|
| 内核 | `6.6.87.2-microsoft-standard-WSL2` |
| strace | `/usr/bin/strace`，版本5.16；help确认支持按PID附加、过滤syscall、fd路径解码、纳秒时间戳/调用时长 |
| perf / trace-cmd | PATH中不可用；常见 `/usr/lib/linux-tools*/perf` 位置也未发现perf。未安装任何包 |
| tracefs | `/sys/kernel/tracing` 可读，存在 `instances/`；可读 `sched_switch`、`sched_wakeup`、`sys_enter_write`、`sys_exit_write` 格式 |
| 已有全局 tracing 状态 | `tracing_on=1`、`current_tracer=nop`、当前clock为`local`。不能覆盖或清空这个全局实例 |
| 可选clock | `mono`在现有trace_clock可选列表内，可供未来专属instance与worker monotonic时间对齐 |
| 权限相关 | `perf_event_paranoid=2`、`kptr_restrict=1`、`ptrace_scope=1`、`sched_schedstats=0`。这些不是实际attach/创建instance成功证明；本次没有写入测试 |

因此最小优先路径是 **专属 ftrace instance 的四类过滤事件**；不必先安装perf。strace可作为较易部署但扰动更大的备用路径。仅存在工具/事件不代表运行权限和缓冲容量已经验证。

## 要回答的具体问题

上一诊断已经定位：tick9509两worker在trace-write区域各约15.8ms，CPU仅39.5/70.5µs；另一事件tick5504主要是PX4原生输入等待约29.28ms。现在只需先回答前一个事件：

1. 15.8ms是否确实覆盖trace文件的write syscall，而非发生在两次Python计时标记之间的其他位置？
2. 长write期间，目标线程是否离开CPU？是仍可运行但迟迟未调度，还是先阻塞、被唤醒后才恢复？

不能把这次取证扩展成无界全系统采样或同时修改日志缓冲策略。

## 最小一次取证

先由主代理冻结新的诊断候选及资源窗口，保持原1ms/4tick、倍率/100ms等预算不变。若复用worker侧录，应继续明确`acceptance_eligible=false`，保存诊断开销。仅使用新epoch真实孩子身份，绝不沿用旧PID1887/1891。

1. 从该epoch的owned children记录取得AP/PX4两个worker PID/TID及监督线程；核对boot_id、start_ticks、argv。保存 `/proc/PID/fd`、`fdinfo`、`mountinfo`，明确哪个fd是原始trace、哪个是stdout管道、哪个是timing sidecar。采集前后复核身份和fd映射，不能猜“fd3就是日志”。
2. 创建一个唯一的新 `/sys/kernel/tracing/instances/wksim-rate-<token>`，只操作该实例。设置其clock为`mono`；不要改现有全局clock/tracing_on/filter/buffer，也不启用全局schedstats。
3. 只开启以下四类事件，使用实读字段名过滤：
   - `sys_enter_write`、`sys_exit_write`：`common_pid == AP_WORKER || common_pid == PX4_WORKER`。
   - `sched_switch`：`prev_pid`或`next_pid`属于这两个worker及监督线程。
   - `sched_wakeup`：事件的`pid`属于上述目标。不能用`common_pid`筛wake-up，因为唤醒者可能是其他线程。
4. write进入事件提供fd/count，退出事件提供ret；按TID顺序配对并用fd快照区分trace/sidecar/管道。sched事件用于同一段mono时间的离CPU、唤醒和重新上CPU。保留过滤器、clock、event格式和每CPU缓冲统计。
5. 从worker身份确认后捕获到首次故障，或最多20墙钟秒，先到即停止**取证器**。这个20s是诊断采集上限，不改变仿真watchdog或验收窗口。若窗口内没有目标长尾，结论只能是未捕获，不推断问题消失。
6. 只关闭本次专属instance，保存原始trace及每CPU overrun/drop状态，然后移除本次拥有的空实例。缓冲丢失、attach前已有调用、半条enter/exit、目标退出或boot变化均标记diagnostic_partial，不能补造时长或等待状态。主代理独立负责仿真进程生命周期。

四个事件的可用格式已核对。专属instance实际创建/过滤/读取权限仍须在受控窗口先验证；失败则停止该方案，不碰全局实例。

## strace备用方案

本机5.16支持下列命令形状；PID和输出目录须来自未来的新身份记录，此处未执行：

```bash
strace -qq -yy -s 0 --absolute-timestamps=unix,ns --syscall-times=ns \
  -e trace=write,writev -p "$AP_WORKER_PID" -p "$PX4_WORKER_PID" \
  -o "$NEW_EVIDENCE/worker-writes.strace"
```

无需dump写入内容，fd路径、count、返回值和时长已经足够。只附加这两个已核验worker，不跟随无关进程。记录tracer自身身份；停止时只中断拥有的tracer并核验已detach，不给worker发送终止信号。strace绝对时间是Unix时间，须同时记录WSL的realtime/monotonic配对及前后偏移，不直接当作worker的mono时间。

**strace本身不能完成scheduler归因。** ptrace在系统调用边界暂停线程，可能明显延长1kHz写路径并触发RateUnmet。`-T`测到的调用经过时间包含等待/调度与跟踪影响，不能直接等同磁盘服务时间。若只能用strace，本轮最强结论是“长耗时落在指定fd的write调用内”；还需scheduler事件才能区分阻塞/可运行等待。

## 开销及允许的结论

- ftrace过滤后的事件记录一般比逐syscall ptrace停顿更适合此路径，但仍有tracepoint/filter、环形缓冲和读取者的CPU/内存/I/O开销，不能假设为零。不要给collector更高实时优先级；记录实际亲和性/优先级，不临时改被测进程策略。
- `sched_switch`的`R`/`R+`说明离开CPU时仍可运行；之后到再次切入的间隔支持运行队列/调度延迟归因。`S`/`D`随后wake-up支持阻塞等待，但**D不单独证明存储盘故障**。有完整事件时，可区分switch-out→wake与wake→switch-in。
- write进入/退出跨越长尾且对应trace fd，可确认同步日志写调用在关键路径；若write很短而标记间隔长，应调查用户态附近抢占/标记扰动，不能继续称“磁盘阻塞”。
- 即使guest显示长等待，仍不能仅凭这些事件区分Windows宿主抢占、WSL虚拟CPU暂停或具体物理存储原因。进一步定位才考虑宿主或block事件，不在本轮预先扩张。
- 首轮仅覆盖worker写路径。tick5504的PX4响应尾部若还需解释，应另把**实际PX4线程TID集合**纳入后续过滤，并复核线程创建/退出覆盖；只观察FC主PID不能代表其所有工作线程。
- 本轮即便未触发RateUnmet，也不能宣称持续1×、60s或三epoch通过；也不能从诊断时长中减去tracer开销算出反事实PASS。

## 建议

独立采集器已完成静态加固：启用前记录保守窗口起点，禁用完成后记录终点；所有后处理错误只进入 metadata，嵌套 finally 仍尝试关闭 fd、关闭 tracing、核对并删除唯一自有 instance，最后才恢复信号处理器；instance/inode 所有权在早期文件中持久化。7 项故障/路径 guard、`--help` 和只读预检通过。当前采集器 SHA256 `6724a36d27970a72aa057823820b72e5a045aa46bdb2e45eb708ef2f96e0919f`，测试 SHA256 `58efdb67d452b0931486ecb64d74f458900572708cb82e0ae36a1a889c45e6c0`，见 `collector-hashes.json`。**现在不改日志缓冲、RPC顺序或预算。** 真实 tracefs instance 创建/启用/采集仍未执行；后续若受控窗口允许，必须新建同等诊断运行/输出目录，绝不附加已退休 proposal-03。
