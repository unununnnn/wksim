# Native 最终 1ms 等待接线契约（只读核对，2026-09-13，修订）

范围：仅契约核对与本文档；不改实现。bench02（各 1000 次）:Python 返回中位 148.5ns,CDLL 2979ns,PyDLL 2424ns;ctypes 接法暂不采用，OMP 的 CPython 扩展另行推进。

## 1. 最小可选接线位置（默认行为不变）

接线点不是唯一一处：`JointRate.begin_group` 有**两个**相同的最终 1ms 自旋分支——初次 `remaining<=1_000_000` 分支（`Simulator/wksim_runtime/joint_rate.py:99-103`，自旋在 100-101 行）与 health 之后的分支（114-118 行，自旋在 115-116 行）。两处均为 `while now<earliest: now=self.now()` 后接 `check` 与 `break`，接线必须**同时覆盖两处**（或都不接），否则同一释放沿出现两种等待实现。窗口不变式见注释 120-123 行：释放沿前不加 health/sleep/record。native 调用 deadline 取 `earliest`（93 行，已含 no-catch-up 的 `previous_start+period_ns` 约束）；两个分支的入口条件都保证进入时 `earliest-now<=1_000_000`，与 native 的 1ms 上界、过期立即返回语义对应。health 节奏（95、106-113 行，2ms）与 sleep(124 行）留在纯 Python。

## 2. 失败语义：不静默回退

native 状态非 0(clock_failure/clock_regressed/deadline_out_of_range/invalid_argument）时**不得回退到 Python 自旋**——静默回退会掩盖 native 失败、让一次失败的候选运行获得通过。接线路径上 native 失败必须保留失败并终止本次候选尝试（错误传播、记录为失败）。默认（未 opt-in）路径从不调用 native，行为字节级不变。opt-in 机制仿 `joint_rate_probe.py:23-30` 的显式 env 模式。

## 3. now 重读是保守约定，不是已证明等式

原 `actual_start_ns`/`previous_start`(126-127 行）本身也只是**最后一次 `self.now()` 采样**，不能断言它精确等于"Python 恢复时刻"。同理，native 返回后在 Python 侧重读 `now=self.now()` 是一条**保守约定**：区分 C 观测点（穿越 earliest 的采样）与返回点（Python 恢复后的采样），重读值 ≥ 返回点 ≥ C 观测点，迟到向保守方向计。按此约定，`check(max(0,now-ideal))`(102/117 行）的 100ms `LATE_LIMIT_NS`(6 行）度量、`rate_group_start` 记录（128-130 行）、下一组 `earliest` 锚定（93 行）与 probe 终值（`joint_rate_probe.py:222-224`）的记录含义保持与既有证据可比；这是为证据可比性而定的约定，而非已证明的语义定理。

## 4. 若用 C 观测值作 actual_start 的含义变化

C 观测点早于 Python 返回点一个 return_gap(bench02 ctypes 中位约 2.4-3.0µs):`lateness_ns` 系统性偏小，100ms 阈值证据强度下降且与既有记录不可比；`previous_start` 提前使下一组 `earliest` 提前至多 return_gap，实际 Python 侧组间距可被压缩到 period 以下；probe 的 `terminal_ns`/`release_excess_ns` 同步偏移。结论：禁止复用现有字段含义；如确需使用必须新增字段名并归入新证据类。

## 5. #84 同组合证明对 pacer 源码/启用方式的绑定核对（已缩小）

- 实际证据：`validation/33-formal-promotion/current-mixed-oxv29042/result.json` 的 `source_sha256` **确实包含** `Simulator/wksim_runtime/joint_rate.py` 与 `Simulator/wksim_runtime/joint_rate_probe.py`（且 `source_unchanged=True`；该 result 本身 status=failed，正式通过件以 profile 证据钉为准）。这些键经 joint_profile.py:334-339 逐字节封存并与 admission 一致——**该次运行的 pacer 源码已被绑定**。
- 但 joint_profile.py:328-331 的必需集不含这两个文件：绑定是该次飞行证据自带的事实，不是契约要求；不强制则未来运行可合法省略。
- `validation/33-final-combo-luna/pv-settle-1w6dru32/raw-pv-audit-v2.json` 的 `audit_source_sha256` 是**审计工具自身**的源清单，不含 pacer 文件；该次飞行 result 的 `source_sha256` 须经其留存 result.json（审计以 `result_sha256` 钉住）另行核对——不能仅由必需集遗漏断言旧证据对新字节自动有效：旧证据只对旧字节有效。
- 启用方式仅负向绑定：正式证据含 `rate_timing_probe` 即拒（joint_profile.py:274-275)。

## 6. 下一次私有实验/正式提升须补的确切证据

1. 将 `Simulator/wksim_runtime/joint_rate.py`（及接线适配模块）加入 joint_profile.py:328-331 必需集，并记录 C 源/适配器/.so 的 SHA 与编译 argv（参照 native-release-wait-bench-20260913-01/commands.json 的 source_identities 模式）。
2. 启用方式正向绑定：证据显式记录 opt-in 开关状态（默认关）；正式证据参照 274-275 行增设 native-wait 标记拒绝规则，直至提升。
3. native 失败即候选失败终止的证据（无静默回退），含各状态码各一次受控演示。
4. `actual_start_ns` 保持 Python 重读约定；任何 C 观测值用法走新字段新证据类。
5. 私有实验按 diagnostic_only 分类（仿 `timing_probe_identity`,joint_rate_probe.py:33-39)；采用决定待 CPython 扩展重测，bench02 ctypes 数字仅为接线演示。
6. #83 既有证据不失效的路径：不改 LATE_LIMIT_NS、period、记录键；probe 相位核算闭合（`_finish_sample` 负值即拒）保持。但若 joint_rate.py 字节因接线改变，其 SHA 变化使旧 `source_sha256` 不再匹配新文件——旧正式证据作为旧字节的证据继续有效、无需盲重跑，但新字节的正式飞行须重新取证；只有默认关且新字节被钉扎后的新运行才能扩展结论。

## 未决点（修订后）

- pv-settle 飞行 result 自身的 `source_sha256` 是否含 pacer 源（审计源清单不含，须查其钉住的 result.json)。
- 接线是改 joint_rate.py（字节变、需新正式证据）还是以独立可选模块承接（保持 pacer 字节不变）——由实现方与协调者定。
- bench02 为单进程微基准（其 summary scope 已声明），非飞行/产率证明；轮转不证明噪声对称，GC/迁移噪声记录于 host 字段。
