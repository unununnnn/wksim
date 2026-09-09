# 独立 private tracefs 采集器

`collect_tracefs.py` 已实现；**没有执行真实采集**。实际只运行 `--help`、无目标的只读 `--preflight` 和7项离线guard测试。日志分别为 `collector-help.txt`、`collector-preflight.json`、`collector-final-tests.log`。预检不创建instance、不开启事件；创建/配置/清理内核instance仍是待受控实测的路径，不能把这些检查当作已采集证明。

## 行为

- 显式接收AP/PX4 worker与epoch监督线程的 `PID:start_ticks`、boot_id、run_id和epoch。开始前验证身份；真实采集还验证两个worker的模块/`--epoch`/trace路径和监督进程的run/epoch argv，拒绝错代次或错角色。
- 只创建随机唯一 `wksim-rate-<32hex>` private instance；所有控制文件写入均在其内。clock选`mono`，buffer固定每CPU1024KiB，只启用2个write事件及sched_switch/sched_wakeup共4类事件，使用受控整数TID过滤。
- 两worker的write entry/exit使用common_pid；sched_switch使用prev_pid/next_pid，wake-up使用目标pid，另外包含监督线程。目标进程不会收到任何信号。
- 非阻塞读取自己的trace_pipe，将原始事件写入新目录 `trace.txt`。默认10s，参数只允许`0 < duration <= 20`。每轮检查boot/目标start_ticks；退出、身份变化、信号或异常均进入自己的清理流程。用户态调度/I/O可能使停止晚于目标时刻，实际elapsed总是记录；超过20s明确`duration_cap_met=false`、partial，不伪造硬实时停止。
- 停止时关闭自己instance的tracing，保留每CPU原始stats与overrun/commit-overrun/dropped-events；未知丢失计数不视为0。保留filters、fd/fdinfo/mountinfo、前后owner、前后global控制读数、时间、trace hash及信号/错误。
- 删除前再次核对instance路径、随机名字、非symlink及dev/inode，然后只调用该instance的`rmdir`；没有递归删除或全局trace清理。清理失败保留路径并明确partial。不会恢复或改写其他实例/全局配置。
- `complete`只表示这个诊断窗口收集/清理无已知丢失，永远`acceptance_eligible=false`。窗口边界可以缺syscall的另一半，分析时只配对完整enter/exit，不补造时间。

## Root与proposal-03工作流的关联

proposal-03旧运行已经退休，不能附加其历史PID。后续如主代理决定再取证，应创建一个新的同等诊断run/epoch及全新输出目录，保留原proposal-03/失败证据。采集器本身不启动该运行，也不修改候选/sourcehash检查。

1. 从活动 `status.json` 读取epoch和supervisor的PID/start_ticks，从对应 `epochs/<epoch>/children.json` 的`arducopter-model.identity`及`px4-model.identity`读取两个worker身份，取本次记录的boot_id。不要使用旧例子中的1887/1891/1297。
2. 原样将这些值传入只读预检，确认角色/代次匹配后，在同一预留窗口另启采集器。比如在WSL仓库根目录中（变量必须是上述真实读回值）：

```bash
python3 -B validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py \
  --preflight --ap-worker "$AP_PID:$AP_START" --px4-worker "$PX4_PID:$PX4_START" \
  --supervisor "$SUP_PID:$SUP_START" --boot-id "$BOOT_ID" \
  --run-id "$RUN_ID" --epoch "$EPOCH"
```

3. 只在主代理明确安排时采集一次；输出目录必须是不存在的绝对路径、其父目录已存在：

```bash
python3 -B validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py \
  --ap-worker "$AP_PID:$AP_START" --px4-worker "$PX4_PID:$PX4_START" \
  --supervisor "$SUP_PID:$SUP_START" --boot-id "$BOOT_ID" \
  --run-id "$RUN_ID" --epoch "$EPOCH" --duration 10 --output "$FRESH_CAPTURE_DIR"
```

4. 分析用metadata的同一epoch、mono时间、实际fd路径，把trace-file write区间与worker timing、监督timing和rate-group时间对齐。先排除timing sidecar写和stdout管道写。完整sched事件用于区分阻塞和可运行等待；缺事件/丢失/边界半调用只报告unknown或partial。
5. 检查metadata中`instance_removed=true`、丢失计数和global_controls_unchanged。主代理另行负责仿真退场、13-owner/two-group等生命周期核验以及任何临时诊断代码恢复。collector的正常退出不证明仿真已退出。

没有perf依赖或包安装。这个方案可以缩小“trace-write区域15.8ms”归因，但不能把guest syscall/scheduler证据直接解释成某块物理盘或Windows宿主根因，更不能据此关闭#20/#62。
