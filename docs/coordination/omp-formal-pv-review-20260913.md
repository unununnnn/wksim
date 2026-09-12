# OMP 正式 PV 新场独立复核（2026-09-13，只读）

对象：`joint-public-flight-1w6dru32`（epoch `a160e99bb6ac46b4a09f0b36b3daeed7`）。
未重飞/未重跑整套 decode 审计/未构建；无嵌套/Git。旧诊断、G6/Full 失败边界不动。

## 1. 保留源与门

- 留存 `source__tools__pv_trajectory_task.py.txt` SHA256
  `c6b3350eea83ff01a33c59a679801c223ada87284a090c4d21f45bdd01996132`（与指定一致）；
  文本核验：入场余量 `.4` 在（:87），dwell 2s 与原 .5/.5/.15 门未动（:82-88）。

## 2. 独立 1ms 真值扫描（waypoint 起止窗，原门原轴原公式）

公式照 `audit_pv_trajectory.py:101-112`（ENU pos=[7,6,−8]、vel=[4,3,−5]、
yaw=remainder(π/2−state[11])，目标 [2,3,3]/yaw 0，门 .5/.5/.15，窗 2000 tick）：

| stack | 窗口 | 样本 | 位置最大 m | 速度最大 m/s | yaw 最大 rad | 违例 |
|---|---|---|---:|---:|---:|---:|
| arducopter | [55047, 57047] | 2001 | 0.19494 | **0.49723** | 0.02632 | **0** |
| px4 | [58893, 60893] | 2001 | 0.45966 | 0.49894 | 0.00338 | 0 |

**原 2 次违例（旧场 tick 55012 速度 .505341 > .5）在新场消除**：AP 新窗起点移至
55047，窗内速度最大 .49723 < .5。PX4 依旧通过。

## 3. 场身份与 runner 终态

- result.json SHA256 `10044bf18c92214f1c93b5461d45dd0c59add2198ad30dc6c237760f3f3758a4`；
  runner status=pass、tick 116004、worst_lateness **89299145ns**（<100ms 门）、
  无 `rate_timing_probe` 字段、completed_groups 28992=（116004−36)/4 ✓。
- 留存构建逐字吻合：AP `1e6250ef…`、Control `6fe8c0b3…`（c2IXOr）、message
  `29969da0…`（Rzj3Pf）、baseline-PV `e05e5c9d…`。
- 主会话已独立核验 PGID 2060-2069 全空（本复核未重复）。

## 4. 完整 raw PV 审计终态（`formal-pv-settle-20260913-01/`）

- `raw-pv-audit.json`（v1）**failed**：`native_input_rejected` duplicate_source 事件
  （event_id 268、control_epoch `65536837…` 非任务 epoch）触发原 ERROR/FATAL 硬门。
- `raw-pv-audit-v2.json` **status=pass**：同一事件被 corroborated 保留
  （`corroborated_duplicate_status_events.px4` 收录原文）；`result_sha256` 与场
  result.json 逐字相等 ✓；run_id/epoch/profile 指向同场 ✓；无 rate_timing_probe ✓；
  速率窗：10s 完整滑窗 27493 个（最差相对误差 0.00131 < 预算 .02）、60s 21245 个
  （0.000514 < .01）✓；`outstanding_checks=[]` ✓；双腿轨迹/停止指标在档 ✓。

## 5. 结论与边界

- 本复核支撑：该场 runner pass + 原 waypoint 物理门两栈零违例 + v2 审计通过且
  身份逐字指向同场。
- v1 审计失败为审计器对重复 status 事件的硬门，v2 以 corroboration 处理——该
  corroboration 的正确性由审计器负责人负责，本复核只核对事件原文被保留而非丢弃。
- 未重跑全套 decode 审计；本报告不替代主会话对 v2 审计改动的验收。
- G6/Full/旧诊断失败边界保持原状。
