# Joint-rate final-spin guard diagnostic (Run 3)

这是继 `validation/33-rate-spin-guard-20260911/` 中两次独立测量之后的第三次测量。
本测量为**仅宿主定时基准、非生产因果证明**（Diagnostic-only host timing benchmark; not production or flight performance evidence）。
用于比较隔离的 8 ms 发布周期末窗各自旋守卫候选（1.0 ms、0.5 ms、0.2 ms）。

## 1. 运行环境与命令

- **精确执行命令**：
  ```bash
  wsl -d Ubuntu-22.04 -u root -- bash -c "cd /mnt/c/Users/PC/Documents/odid编译/wksim && mkdir -p validation/33-rate-spin-guard-20260911-02 && chrt -f 50 nice -n -10 python3 -B tools/benchmark_joint_rate_spin_guard.py --samples 1500 --output validation/33-rate-spin-guard-20260911-02/measurement.json"
  ```
- **执行时间（UTC）**：
  - 开始时间：`2026-09-11T08:24:42.461946+00:00`
  - 结束时间：`2026-09-11T08:25:18.933387+00:00`
- **主机 / 内核环境**：
  - 平台内核：`Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.35`
  - WSL 发行版：`Ubuntu-22.04`
  - Python 版本：`3.10.12 (main, Jun 22 2026, 18:55:27) [GCC 11.4.0]`
- **调度器设置**：
  - 策略：`SCHED_FIFO` (policy value 1)
  - 优先级：`50`
  - Nice 值：`-10`
- **源码 SHA-256**：
  - `tools/benchmark_joint_rate_spin_guard.py` SHA-256：
    `a97f711a68d7e7d5898049f8c1c67a0340ad2f983568f434ae1ef31fcf9bdba7`

## 2. 测量结果汇总（nearest-rank 百分位，每档 1,500 样本）

| guard | mean overshoot | median | p95 | p99 | max | >100 us | mean spin |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0 ms | 3,376 ns | 15 ns | 33 ns | 128,877 ns | 253,728 ns | 27 | 927,920 ns |
| 0.5 ms | 3,752 ns | 15 ns | 36 ns | 128,728 ns | 382,733 ns | 29 | 435,190 ns |
| 0.2 ms | 5,052 ns | 15 ns | 20,297 ns | 134,968 ns | 211,972 ns | 36 | 142,953 ns |

## 3. 预注册条件核对与结论

根据预注册准入条件：
> 只有当 0.5ms 相对 1ms 同时满足：
> 1. `mean overshoot` 更低；
> 2. `count_gt_100us` 不更高；
> 3. `max` 不更高。

对比实测数据（0.5 ms vs 1.0 ms）：
- `mean overshoot`：0.5 ms 为 `3,751.57 ns`，高于 1.0 ms 的 `3,376.30 ns`（**不满足**）；
- `count_gt_100us`：0.5 ms 为 `29`，高于 1.0 ms 的 `27`（**不满足**）；
- `max`：0.5 ms 为 `382,733 ns`，高于 1.0 ms 的 `253,728 ns`（**不满足**）。

**结论**：0.5 ms 候选三项指标均劣于 1.0 ms 基线，**完全不满足预注册条件**。
按既定规则，**不修改生产源码**（`Simulator/wksim_runtime/joint_rate.py` 保持不变），保留本次测量原件作为失败基准证据。

## 4. 文件 SHA-256

- `measurement.json`: `3881167e8f2dd78138b129f03c4f43341c3723c8c772d807bd3bad3290e63657`
