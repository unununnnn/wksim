# mixed-work-overrun-20260913 v2：CPU分段诊断存在性核对与修正建议

承接 v1（`mixed-work-overrun-20260913.md`）。本版只回答两件事：原件里是否已有 `WKSIM_JOINT_CPU_TIMING` 分段记录可提取；并修正 v1 的采样建议。只读原件，纯标准库分析，未执行任何被禁项。

## 结论：实际记录数 = 0，flag 关闭

证据链（可复核性逐项标注；raw wire 与 go/admission 件不在本 checkout 内，详见下节“可复核性与当前限度”）：

1. **门控点唯一**：冻结 `source__Simulator__wksim_core__joint.py.txt`（SHA `f5433c2e…`）第 54 行 `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`；`diagnostic_gc_timing`（55–67行）、`diagnostic_step_cpu_timing`（216行）、`diagnostic_native_input_timing`（275行）三种 kind 全部在此单一 flag 之下，无其它写入路径（`record()` 将全部 kind 写入 joint-wire.jsonl，runner 829–831 行）。
2. **wire 实测 0 条**：495,410 行 joint-wire.jsonl（SHA `20d0634e…`）中三种 diagnostic kind 计数均为 0（种类普查仅 actuator/sensor/step/barrier/gps/connected）。（raw 文件仅存于 Linux 接受根，未随场入库；计数固化于已跟踪的 `mixed-work-overrun-v2.json`，本 checkout 无法重算其 SHA 与行数。）
3. **反证下界**：若 flag 为 '1'，每个 `tick % 250 == 0` 的 step 无条件产生 `diagnostic_step_cpu_timing`；本场 tick 1..131,760 至少应有 **527** 条。实测 0 ⇒ flag 在该场为关。
4. **启动件 env 状态（修正 v1/v2 早期“均不含”的说法）**：launch.sh 第 4 行为**显式 unset 控制**——`unset CMAKE_PREFIX_PATH … WKSIM_JOINT_CPU_TIMING WKSIM_JOINT_RATE_TIMING_PROBE`（该行确实包含 `WKSIM_JOINT_CPU_TIMING` 字样，但语义是清除而非设置）；launch.json 与 children-start.json（本 checkout 已跟踪副本）不含该串；pre-run-identity.json 第 28 行记 `"WKSIM_JOINT_CPU_TIMING": null`。go.json 与 experimental-admission.json 未随场归档进本 checkout（未跟踪），其内容只能在接受根（外部）核对，此处无法本地复验。综合以上，flag 在该场为 off/unset 的结论保持成立：显式 unset 控制 + 身份记录 null + 启动件无设置路径。

因此现有记录**不能**提取 health_and_models / encode_send / native_inputs 分段或 wait bracket；v1 的两类主导形态（native 输入等待 vs step→sensor tick 间区）仍只有 wire 可见界，无 CPU/off-CPU 拆分。v2 输出 `mixed-work-overrun-v2.json` 的 `diagnostic_cpu_timing` 段固化了上述证据（含 7 组 ±邻域 tick 窗口普查，窗口内同样 0 行）。v1 全部数值经复跑不变。

## 可复核性与当前限度

v1 保留为历史证据，不再逐条修订；本节与上文修正为当前状态的权威表述。

- **raw joint-wire.jsonl（SHA `20d0634e…`，495,410 行）仅存在于 Linux 接受根，未随场入库**：本 checkout 无法重算其 SHA、行数或重跑 kind 普查；wire 侧计数结论依赖该外部原件与已跟踪的 v2 JSON 固化结果（`rate.jsonl.gz` 已入库，其 SHA 可本地复核）。
- **go.json 与 experimental-admission.json 未入库（untracked / 未随场归档）**：oxv29042 场目录在本 checkout 中不含这两件，其内容不能在本地复验。
- **v1 所引脚本 SHA `e5a0db2b…d81595fe` 不在 Git 中**：Git 已跟踪的 `analyze_mixed_work_overrun.py` 是更新后的版本（SHA `1162d9fbcaa581fe795dadd2a33427c6f03b69c81aa67111b8b98eda4e691972`，与 v2 JSON 的 `script_sha256` 一致）。v1 的复跑命令按旧 SHA 描述，已过时；复跑以本 v2 的脚本与 SHA 为准。
- **现场 runner 漂移**：本 checkout 的 `tools/run_joint_flight.py` 相对冻结快照（SHA `65c7a867…`）已有演进（约 377 行差异，新增 perf-capture 装载等）；wire `record()` 位于快照第 829 行与 v1 一致，但现场运行的 runner 与快照不再逐字节相同。joint.py 快照（SHA `f5433c2e…`）与本 checkout 的 `Simulator/wksim_core/joint.py` 逐字节一致，第 54 行门控点可本地复核。

## 修正后的建议（替换 v1“覆盖旧7个tick窗口”说法）

墙钟长尾未证明在固定 tick 复现——不对准历史 tick 碰运气。若协调者日后批准一次诊断复跑（不在本轮授权内），正确形态是：

- **按实际超额触发**：在 `end_group` 检测到 `work_ns > period_ns` 时才落盘该组窗口的分段记录；
- **有界环形保留**：`WKSIM_JOINT_CPU_TIMING` 三段 marks 与 `_native_wait` bracket 常驻写入有界 ring（如最近 64 组），超组触发时转储，正常组丢弃；
- 仍为 diagnostic_only：不改默认路径字节、不改任何阈值/预算。

## 交付物

- 脚本（已更新，可复跑；Git 已跟踪版本 SHA `1162d9fb…e691972`，v1 所引 `e5a0db2b…d81595fe` 不在 Git 中）：`validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py`
- v2 数据：`validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json`
- v1 报告与 JSON 原样保留。

限度：以上仅证明该场无 CPU 分段证据；不断言复跑必现超额；本结果不算全场通过。可复核性边界见“可复核性与当前限度”——raw wire 与 go/admission 两件留在外部，本地复核以已入库件为限。
