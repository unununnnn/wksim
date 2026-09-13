# mixed-work-overrun-20260913 v2：CPU分段诊断存在性核对与修正建议

承接 v1（`mixed-work-overrun-20260913.md`）。本版只回答两件事：原件里是否已有 `WKSIM_JOINT_CPU_TIMING` 分段记录可提取；并修正 v1 的采样建议。只读原件，纯标准库分析，未执行任何被禁项。

## 结论：实际记录数 = 0，flag 关闭

证据链（全部可复核）：

1. **门控点唯一**：冻结 `source__Simulator__wksim_core__joint.py.txt`（SHA `f5433c2e…`）第 54 行 `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`；`diagnostic_gc_timing`（55–67行）、`diagnostic_step_cpu_timing`（216行）、`diagnostic_native_input_timing`（275行）三种 kind 全部在此单一 flag 之下，无其它写入路径（`record()` 将全部 kind 写入 joint-wire.jsonl，runner 829–831 行）。
2. **wire 实测 0 条**：495,410 行 joint-wire.jsonl（SHA `20d0634e…`）中三种 diagnostic kind 计数均为 0（种类普查仅 actuator/sensor/step/barrier/gps/connected）。
3. **反证下界**：若 flag 为 '1'，每个 `tick % 250 == 0` 的 step 无条件产生 `diagnostic_step_cpu_timing`；本场 tick 1..131,760 至少应有 **527** 条。实测 0 ⇒ flag 在该场为关。
4. **启动件无此 env**：launch.sh / launch.json / go.json / children-start.json / experimental-admission.json 均不含 `WKSIM_JOINT_CPU_TIMING`。

因此现有记录**不能**提取 health_and_models / encode_send / native_inputs 分段或 wait bracket；v1 的两类主导形态（native 输入等待 vs step→sensor tick 间区）仍只有 wire 可见界，无 CPU/off-CPU 拆分。v2 输出 `mixed-work-overrun-v2.json` 的 `diagnostic_cpu_timing` 段固化了上述证据（含 7 组 ±邻域 tick 窗口普查，窗口内同样 0 行）。v1 全部数值经复跑不变。

## 修正后的建议（替换 v1“覆盖旧7个tick窗口”说法）

墙钟长尾未证明在固定 tick 复现——不对准历史 tick 碰运气。若协调者日后批准一次诊断复跑（不在本轮授权内），正确形态是：

- **按实际超额触发**：在 `end_group` 检测到 `work_ns > period_ns` 时才落盘该组窗口的分段记录；
- **有界环形保留**：`WKSIM_JOINT_CPU_TIMING` 三段 marks 与 `_native_wait` bracket 常驻写入有界 ring（如最近 64 组），超组触发时转储，正常组丢弃；
- 仍为 diagnostic_only：不改默认路径字节、不改任何阈值/预算。

## 交付物

- 脚本（已更新，可复跑）：`validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py`
- v2 数据：`validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json`
- v1 报告与 JSON 原样保留。

限度：以上仅证明该场无 CPU 分段证据；不断言复跑必现超额；本结果不算全场通过。
