# omp-parent-retention-review-20260913-01：父探针留存补丁接线性复核

对象：DS 冻结 `validation/coordination/ds-parent-probe-retention-20260913-01/`（`prepare_probe_retention.py` `5dbd9519…`、`prep-report.json` `cd7a06da…`、`run_joint_flight-candidate.py.txt` `08e20642f82f9052284f3054ae91c57d5d7e77017fb996e11d748bb98a86db99`）。基线=l6bxh4tn 归档 runner 快照（`f5411627…`，逐字）。本轮只读 + 直接 diff，未执行其脚本、未改任何运行时代码。

## 结论：CLEAR，无阻断

1. **diff 界限**：对钉扎基线直接 diff，恰好两个 hunk——`import collections`（7a8）与 `make_joint_rate` 尾部 5 行（62–70 → 63–76）；无其它字节变化。候选 SHA 与申报一致。
2. **默认/spin 路径不变**：`if diagnostic and not spin_cpu` 守卫；diagnostic=False（默认 JointRate）与 spin_cpu=True（子探针）两路径均不触新方法体，`return` 语义不变。
3. **deque 最新 1 + 逐组发射保留**：`rate.timings = collections.deque(rate.timings, maxlen=1)` 在构造**之后**；父模块 `_finish_sample` 的 `self.record("rate_timing_probe", ...)`（joint_rate_probe.py 193 行）与容器无关——每组发射照常落 rate.jsonl。
4. **构造/回调顺序/异常**：构造函数先跑完再重绑；health/sleep 包装与异常路径零改动；`collections.deque([], maxlen=1)` 无新异常面。
5. **无隐藏 timings 读者**：全仓 grep——仅 `validation/test_joint_rate_probe.py` 用 `.timings[-1]`（deque 支持负索引），且这些测试直接构造探针（不经 `make_joint_rate`），拿到的仍是 list；runner 与子探针从不读 `.timings`。bound 不失效。

## 备注（非阻断）

- bound 仅作用于 runner 构造的诊断路径；直接构造（测试）仍为无界 list，行为不变。
- 目标模式（env `WKSIM_JOINT_RATE_TIMING_PROBE=1`、CPU_TIMING unset、无 spin/census flag）正落在被改动分支上：`make_joint_rate(diagnostic=True, spin_cpu=False)` → 父探针 + deque bound。
- 结果含 `rate_timing_probe` 键 → 正式 validator 按键存在即拒，天然 diagnostic_only；收益为诊断内存有界（约 3.3 万组样本不再累计），不改变任何计时/timer/速率语义。

主会话可预约 native 资源。
