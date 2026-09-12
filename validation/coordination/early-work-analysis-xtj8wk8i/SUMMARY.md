# xtj8wk8i early-manager-work 分析摘要（2026-09-13，纯离线）

输入：`/root/wksim-release-acceptance-fe3/validation/joint-public-flight-xtj8wk8i/early-manager-work.json`
（21239 样本、10 墙秒窗口、epoch `792e1feb…`、segment 1；runner 原始 status pass、
两栈 PV task pass、独立 PGID 全空——**本诊断不构成正式性能通过**）。
产物：`analysis.json`（status=pass，invalid=0，crossing=1，error_outcome=0，
无截断无诊断错误）。

## 五阶段分布（valid ok 样本；wall/thread-CPU ns）

| phase | n | wall 中位 | wall 最大 | CPU 中位 | CPU 最大 | 最大 tick |
|---|---:|---:|---:|---:|---:|---:|
| manager_health | 4997 | 116,271 | 869,102 | 115,554 | 872,058 | 5033 |
| rate_begin_group | 1250 | 3,793,590 | 4,633,879 | 1,404,041 | 1,865,671 | 5032 |
| physics_advance | 4998 | 783,737 | 6,622,100 | 598,220 | 1,984,444 | 5033 |
| clock_publication_log | 4997 | 79,246 | 433,381 | 78,771 | 433,444 | 5033 |
| post_advance_readiness_summary | 4997 | 26,340 | 349,803 | 26,118 | 351,734 | 5033 |

## 观察（全部限定在 10s 窗内）

- `rate_begin_group` 每 4-tick 组 wall 中位 3.79ms、线程 CPU 中位 1.40ms：
  wall−CPU ≈ 2.39ms/组。该阶段**包含 begin_group 内的主动 release sleep**，
  差值不得读作纯调度丢失。
- `physics_advance` wall/CPU 中位 784/598µs，最大 6.62/1.98ms。
- 全部样本 tick ≤ 5033（窗口内 10s ≈ 10000 tick 的前半）；1 个跨 10s 边界样本已标记。

## 硬性非声明

五阶段为顺序热点段，**不得跨 phase 求和当窗口闭合**；外层重叠同样不可相加。
线程 CPU 仅 manager 线程，**不含 model worker CPU**；wall−CPU 不是纯调度归因。
10s 诊断窗不外推全程；不是性能通过。runner/控制器/阈值未变。
