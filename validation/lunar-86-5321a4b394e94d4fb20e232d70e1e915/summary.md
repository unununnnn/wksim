# #86 `35-px4-flight` PX4 外部 PID 运行失败交接

## 票据与边界

- GitHub：#86 `[Luna] 执行一次 PX4 外部PID定点/轨迹/扰动`
- 稳定键：`35-px4-flight`
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`4e161e2 evidence: retain failed 1x epoch attempt`
- 前置 #50、#85 均已关闭；本票只尝试一次 PX4 外部 PID run，不重试、不修改 PID 配置或预算。

## 准确命令与身份

```text
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-luna-01 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-px4-luna-01
```

- run ID：`pid-px4-luna-01`
- 配置 SHA256：`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`
- `tools/run_pid_flight.py` SHA256：`695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f`
- `tools/run-pid-flight.sh` SHA256：`c772423deea8dde33914f05edef5777cf116c06cbae4c008f9accaea09ae8302`

## 实际结果

- 候选资源身份探测完成，但 runner 在 `/root/wksim-pid-px4-luna-01` 新鲜目录校验处失败：`ValueError: Use a fresh /root/wksim-pid-flight-* output directory`。
- 具体原因是票据命令的输出目录名 `wksim-pid-px4-luna-01` 不满足当前 runner 的固定前缀 `wksim-pid-flight-`；不是飞行物理结果，也不是 PID 性能结果。
- 退出码：`1`；输出根不存在；没有启动 PX4、模型、MicroXRCEAgent、PID physics、ROS 或控制节点。
- 运行后 WSL 快照没有该 run 或相关子进程；本次无进程需要清理。
- 因此未产生 hover 标定、PID measured stage、独立 1ms 审计或动作完成证据，不能关闭 #86。

## 证据

- 活动目录：`validation/lunar-86-5321a4b394e94d4fb20e232d70e1e915`
- 原始 stdout：`flight.stdout.log`，SHA256 `6abb26d4743ffe890d9b9c815c4042c965216b7c67be7845b4bd025b698d5f56`。
- 退出记录：`flight.result.json`，SHA256 `04e0062d09c2ad8593060af6b43aca020a23701f7a10ead37cc709e2278549ed`。
- WSL 进程快照：`processes-after.txt`，SHA256 `bdc5a2b68f2225422894470767df5f0907e7fab90eadd140e2d9dfedfa73f7f3`。
- 完整错误 traceback 保留在原始 stdout；本票未修改原始 PID/物理配置或既有运行记录。

## 完成判定与处理

本票完成条件未满足。按指南保持 #86 `OPEN`，移除 `ready-for-agent`、添加 `needs-triage`，将“票据输出目录契约与 runner 固定前缀不一致”交 Astra 修复或冻结新命令；在新合同/命令确认前不重试 PX4 飞行，也不进入 #87。
