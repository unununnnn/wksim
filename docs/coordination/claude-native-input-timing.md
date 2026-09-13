# Claude：native input 分栈等待测量（#20/#33 倍率诊断）

本切片为倍率诊断补齐"AP 输入等待 / PX4 输入等待"的分段原始测量。动机：probe-03
（`/root/wksim-scheduler-probe-35728b1-03`）中 tick5504（5.754904ms）与 tick2000
（5.130931ms）等 4-tick 边界的 `native_inputs` 是 AP+PX4 合并等待，现有采集不能分栈归因。
本切片**只用 stub 原生等待做离线计时边界验证，未运行 SITL/UE/ROS/MATLAB/tracefs，不是真实
飞行验收，也不据现有数据伪造任何新测量**。

## 修改文件（本切片独占写入）

- `Simulator/wksim_core/joint.py`：新增 `_native_wait` 帮手并在 `finish_inputs` 的原生等待
  位置分栈采集。
- `validation/test_native_input_timing.py`（新）：8 项离线检查。
- 本文档（新）。

未改 `tools/analyze_joint_scheduler.py`、`tools/profile_joint_scheduler.py`、运行时、时钟、
证据或任何 Issue 状态；未 commit/push。

## 实现契约

- **启用条件**：沿用现有 `WKSIM_JOINT_CPU_TIMING == '1'`（`self.cpu_timing`）。默认关闭时
  `_native_wait` 直接 `return wait(*args), None`，**零新增时钟读取、零日志**；`finish_inputs`
  里仅多一个空 list 与 `if input_waits:` 短路。用 `getattr(self,'cpu_timing',False)` 以防
  既有 `object.__new__` 测试未设该属性。
- **采集点**：`finish_inputs` 内两处原生等待——`wait_ap`（仅当 `pending_ap['frame']!=tick`）
  与 `wait_px4`（仅当 `tick%4==0` 且非 recovery-synchronized 捷径）。每段记录
  `stack`、`wall_start_ns`/`wall_end_ns`（单调钟）、`wall_ns`、`thread_cpu_ns`（线程 CPU），
  并绑定收到的输入帧（AP 段 `ap_frame`，PX4 段 `px4_time_us`）。
- **不变量**：物理步长、四 tick 屏障、100ms 迟到门槛/调度/超时、`wait_ap`/`wait_px4` 的
  调用参数与全部输入/ack 顺序逐一保留；`acknowledge_ap`/`barrier`/`repair_input`/`record`
  语义不变；`native_inputs` 合并阶段的既有统计含义不变（仍是 `finish_inputs` 整体区间）。
  采样成本**不扣除**（诊断开启时段采集开销落入 `native_inputs` 残差，符合既有约定）。
- **记录**：成功路径在 `finish_inputs` 末尾、`self.inflight=None` 之前，经现有 `record`
  契约（自动绑定 `kind/epoch/tick/issued_monotonic_s`）发出 `diagnostic_native_input_timing`：
  `{ap_source_frame, px4_source_time_us, native_wait_wall_ns, waits:[...], limitation}`。
  记录量仍按既有慢样本/周期样本原则：仅当 `native_wait_wall_ns > 2ms 或 tick % 250 == 0`
  才记录，非全量普查。
- **ack/record 开销归属（明确）**：分段**只**包住 `wait_ap`/`wait_px4` 调用本身，**不含**
  `acknowledge_ap`、`barrier`/`repair_input` 及任何 `record` 写。这些开销仍留在合并的
  `native_inputs` 阶段里，可由同一 tick 的 `diagnostic_step_cpu_timing.native_inputs` 减去
  各分段之和得到残差。
- **fail-closed**：等待抛 `InputTimeout` 时不产生分段、不发记录，异常原样经 `finish_inputs`
  传播到运行时既有 `suspend_input` 路径；不会把失败写成成功。恢复路径（`recovering=True`）
  走同一 `_native_wait`，recovery-synchronized 捷径不调用 `wait_px4`、不虚构 PX4 段。
- **归因边界**：分段里的监督线程 off-CPU（`wall_ns - thread_cpu_ns`）含 I/O 等待与脱调度，
  **不能**据此直接断定原生 FC、宿主机或 Windows 根因（同既有分析的限制措辞）。

## 离线测试结果（本机，stub 原生等待）

`python -m unittest validation.test_native_input_timing -v` → **8 项全过**：
默认关闭零时钟读取且行为不变（ack/barrier/step 照常）；未设 `cpu_timing` 属性默认关；
AP-only tick 不虚构 PX4 段；边界 tick AP/PX4 分段 wall/CPU 独立且顺序不重叠、屏障仍完成；
<2ms 且非周期 tick 不记录；周期 tick（250）即便快也记录；AP 超时、PX4 超时均传播且无伪成功。

回归：`python -m unittest validation.test_joint_input_deadline validation.test_joint_scheduler_analysis`
→ **9 项全过**（确认未改 `native_inputs` 语义、超时/恢复 fail-closed 与分析器行为）。

## 下一条真实诊断验证命令（由主会话安排，本切片未运行）

前提：WSL Ubuntu22.04；`joint.py` 为本切片版本；按 `docs/coordination/short-cycle-goal.md`
串行预约 tracefs 等共享资源、单场唯一输出；选用依赖齐全且已过代码复核的稳态剖面
（`requested_rate=1.`，4-tick 边界密集）。地面诊断（不发起飞行任务、不能作倍率验收）：

```bash
python3 -B tools/profile_joint_scheduler.py --output /root/wksim-scheduler-probe-<新后缀>
```

其内部以 `WKSIM_JOINT_CPU_TIMING=1` 启动自有运行并捕 10s 私有 tracefs；新分段记录落在
`<输出>/runs/<run_id>/epochs/<epoch>/wire.jsonl` 的 `diagnostic_native_input_timing` 行。
读取/拆分（可按 stack 过滤边界 tick 的 AP/PX4 段）：

```bash
python3 -B tools/analyze_joint_scheduler.py /root/wksim-scheduler-probe-<新后缀> --output <新分析.json>
```

注：现有 `analyze_joint_scheduler.py` 只消费 `diagnostic_step_cpu_timing`，本切片不改它。
分栈汇总由同批新增的独立消费者 `tools/analyze_native_input_waits.py` 承担（见下节）。

## 追加切片：native input 等待分栈分析器（消费 diagnostic_native_input_timing）

在真实捕获运行期间补交付消费者，冻结 `joint.py` 与已交测试、不再改动。新增
`tools/analyze_native_input_waits.py` 与其测试 `validation/test_native_input_wait_analysis.py`。

- **复用不重写**：直接 `import` 已验证的 `parse/pair/explain/require`，沿用 report 守卫
  （capture 完整/loss-free/全局控制未变/instance 已删除）、`trace_sha256` 核验、
  `pid_mapping['kernel_pids']` 内核 PID 绑定与 `Path(report['directory'])/'epochs'/report['epoch']`
  的 epoch 绑定读取；不另写 trace 解析器，不改 record/collector/物理预算。
- **校验（非法即明确失败）**：每段 `stack∈{arducopter,px4}`、四个时间字段为 int、
  `wall_end>wall_start`、`wall_ns==wall_end-wall_start`、`0<=thread_cpu_ns<=wall_ns`；
  每 record 的 `waits` 非空、各段 sum 等于 `native_wait_wall_ns`、段间时间不重叠、stack 不重复
  且按 AP→PX4 顺序、epoch 等于绑定 epoch、tick 为 int。AP 段须带整数 `ap_frame`；PX4 段
  `px4_time_us` 允许为 `None`（启动期尚未绑定执行器时间戳），按源码原义保留、不虚造帧。
- **汇总（仅完全落入 capture 窗的片段，跨窗片段排除不插值）**：分栈给出保留样本数、最大值、
  总 wall/总 threadCPU、监督线程 blocked/runnable/unknown/off-CPU 合计，及按时长排序的前 10 条
  具体 tick（含帧绑定）。**不计算总体中位数/比率**，不把监督线程等待写成 FC 内部函数或
  Windows 根因。
- **CLI**：`python3 -B tools/analyze_native_input_waits.py <root> --output <新文件.json>`；
  输出用 `'x'` 模式打开，**绝不覆盖**原证据或已有分析。

离线测试 `python -m unittest validation.test_native_input_wait_analysis -v` → **14 项全过**：
时间不一致（wall 倒退/wall_ns 不符/threadCPU 超 wall）、重复与乱序 stack、空 waits、sum 不符、
未知 stack、epoch 不符均被拒；启动期 `px4_time_us=None` 被接受且不造帧；汇总的分栈数量/最大值/
总量/监督线程 blocked-runnable-unknown 数学正确；跨 capture 边界片段被排除计数；合成 capture 端到端
通过守卫+trace SHA+内核 PID 绑定并对监督 off-CPU 归因；capture 不完整与 trace 被篡改均被拒；
CLI 写出且二次同路径拒绝覆盖。全程未启动任何真实运行。

主会话真实验证命令（采集完成后）：先跑既有
`python3 -B tools/analyze_joint_scheduler.py <root> --output <...>`，再跑
`python3 -B tools/analyze_native_input_waits.py <root> --output <新文件.json>` 即可得到
tick5504/tick2000 这类边界等待的 AP/PX4 分栈归属。
# 主会话实测更新

已实际完成新捕获并由主会话复核，见 `docs/2026-09-11-short-cycle-results.md` 与 `validation/native-input-shortcycle-01/analysis-final.json`。当前分析器保留 CPU 原值：wall/CPU 分别读取造成不同测量窗，真实短样本可以 CPU>wall，不能套初版的上界假设。初版真实拒绝日志保留，修正后16项检查通过；同时拒绝空记录和没有完整窗内片段。以下原代理交接保留其当时版本，不替代主会话最终实测。
