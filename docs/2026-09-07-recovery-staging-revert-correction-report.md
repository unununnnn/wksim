# 2026-09-07 恢复窗口违例归因纠正与修订后双侧回归报告

承接 `c162fa7`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。Goal active；未关闭任何 G2/Full 门槛。

## 核心结论（先行）

1. `c162fa7` 报告中的「recover 重连窗口末端单次 >100ms 停顿」三次失败（w1wi0gpj/dtcollzf/523cme9k）**不是 recover 窗口的 DDS 发现风暴，而是本会话一项未提交工程实验（recover 窗内预生成恢复任务进程组）注入的等待**。三份样本的 scene-lifecycle 均在违例前一条记录 `recovery_task_transport_initialized`，rate_boundary_check 迟到分别为 390.86/400.52/612.66ms，与该等待时长逐一吻合；窗口内 paced 组最坏 0–0.5ms 亦与 paced 物理无关。该实验已按实测证据回滚（`4cc93ca`），修订合同文本与数值不变。
2. 回滚后同一 0.5× 监督 AP 失联恢复回归真实通过（`_yrr1_v8`）：recover 窗口段最坏 0.77ms、边界检查 0，start-recovery-task 修订锚点按设计触发，风暴段最坏 94.87ms<100ms；原始审计两次字节一致（`0f84c8e2…`）+ 三项篡改负例通过。回滚后另一次 AP 运行（`y_3hsz3y`）recover 窗口段最坏 2.30ms、边界 0（该轮后在修订锚点段因宿主持续漂移 100.13ms 如实冻结，样本保留）。**「recover 窗口自身风暴」这一新未决问题随之撤回：该现象由注入的工程实验造成，不存在合同级问题。**
3. PX4 失联恢复修订后回归第三次真实尝试**通过**（`ffi_57_3`）：recover 窗口段最坏 0.04ms、锚点段 61.60ms<100ms、恢复任务/冷重置完成；原始审计两次字节一致（`4765a72f…`）+ 三项篡改负例通过，恢复 0.33 墙钟秒、2 进程组无残留。前两次任务级失败（`_7oddm5x`/`ievptgwi`）均为恢复接管后 2s 保持驻留门槛如实拒绝：接管瞬间垂向速度 0.526/0.508 m/s，略高于合同 0.5 m/s（PX4 原生 failsafe 瞬态），**无 rate_unmet**，样本保留。修订前 PX4 通过证据（nasz1u3f，94.18ms，审计通过）继续有效。

## 时间线与机制

- 并行会话在 `572c7bb` 工作树实施已批准的 start-recovery-task 重锚修订时，本会话同时在同一文件试验「recover 窗内预生成恢复任务」（意图工程压制发现风暴）。两者均被 `c162fa7` 一并提交。
- 该实验在 `recover()` 的 `recover_confirmed` 重锚之前同步等待两个任务进程完成 DDS 订阅匹配。`recover_confirmed` 重锚（非 recovery 标记）会把该等待计入既有计划的边界检查：390–613ms > 100ms，三场修订后尝试因此在锚点前如实 rate_unmet。恢复窗口内 paced 物理本身一直健康（0–2.3ms）。
- 本会话逐记录核验三份样本（lifecycle 标记紧邻违例、时长吻合、移除后同场景窗口 0.77–2.30ms）后回滚，并以同一驱动（`run_product_flow.py arducopter`）真实验证。
- `q2qexeye`（AP EKF origin 复位撤销、PX4 未起飞超时）与本实验无关（未到达 recover），归因维持并行会话原判。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| staging 实验回滚（提交） | `4cc93ca` | git |
| 修订后 AP 失联恢复回归 | **通过**（recover 窗 0.77ms、锚点段 94.87ms<100ms、恢复任务新请求 4–6/4–7、冷重置新 epoch） | `validation/product-joint-flow-_yrr1_v8/` |
| 上述原始审计 | 两次字节一致 `0f84c8e2…` + 篡改负例×3 | `validation/recovery-audit-20260907b-_yrr1_v8-{a,b,negative}.json` |
| 回滚后 recover 窗口健康第二样本 | 段最坏 2.30ms、边界 0（后段宿主漂移 100.13ms 如实冻结） | `validation/product-joint-flow-y_3hsz3y/` |
| 修订后 PX4 失联恢复回归 | 第三次**通过**（recover 窗 0.04ms、锚点段 61.60ms<100ms）；前两次任务级保持驻留门槛失败（无 rate_unmet） | `validation/product-joint-flow-ffi_57_3/`、失败样本 `_7oddm5x`/`ievptgwi` |
| 上述 PX4 原始审计 | 两次字节一致 `4765a72f…` + 篡改负例×3 | `validation/recovery-audit-20260907b-ffi_57_3-{a,b,negative}.json` |
| 倍率单测（含修订新增） | 11/11 | `validation/test_joint_rate.py` |

## 失败与边界样本（全部保留）

- `product-joint-flow-q2qexeye`：AP EKF origin 复位正确撤销（与本实验无关）。
- `product-joint-flow-{w1wi0gpj,dtcollzf,523cme9k}`：staging 实验造成的 recover 窗违例（已回滚，根因如上）。
- `product-joint-flow-y_3hsz3y`：回滚后 recover 窗健康，修订锚点段宿主持续漂移（段实测 0.4686×）100.13ms 如实 rate_unmet。
- `product-joint-flow-{_7oddm5x,ievptgwi}`：PX4 恢复保持驻留门槛任务级失败。

## 残留与卫生

每场真实运行结束后核验：WSL 无 arducopter/px4/Agent/ROS/驱动残留、无仿真端口监听；审计 `groups_without_residue=2`；本轮启动的驱动进程均到终态。

## 未决（不替用户回答）

1. PX4 修订后恢复前两次保持驻留门槛失败已定性为 PX4 原生 failsafe 瞬态边际（第三次同配置真实通过）；合同 0.5 m/s 门槛不动，无需提交新决策。
2. 持续 1×（47.1s/60s）与宿主噪声：维持并行会话报告的原未决状态。
