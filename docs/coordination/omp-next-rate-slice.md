# OMP #82 视角：ArUco 实跑验证的调度改动 vs mixed/PV 复用缺口（r2 校正）

日期：2026-09-11。只读对照当前源码，未改 runtime，未重跑证据。
r2 校正：此前"exit≠0+pass 反向拒绝缺口"已过时——当前
`joint_evidence.py:20` 为 `(returncode==0)!=(report.status=='pass')` 双向一致
（84cb 已修），不得再引用。tracking-14 已 retire 失败（tick65452/100.165787ms，
55 帧，publisher 图快照通过，中位组 3.409ms，arm 附近 20ms 峰值），原判不动。

## ArUco 实跑已验证的改动及当前门控（按当前源码）

| 改动 | 位置 | 门控现状 |
| --- | --- | --- |
| 后台证据写 AsyncEvidenceStream | `evidence_stream.py`；`joint_runtime.py:81,99-105,761-771` | `WKSIM_JOINT_ASYNC_EVIDENCE=1` 且仅 ArUco，否则显式拒绝（:83-84） |
| 模型侧异步证据 | 同上 flag `:82`（ASYNC_MODEL_EVIDENCE） | 同上 ArUco 限定 |
| 写时序探针 WriteTiming | `write_timing.py`；`:107-116` | `WKSIM_JOINT_WRITE_TIMING=1`，诊断用 |
| 延迟任务报告 | `joint_evidence.py:6-22`；`joint_runtime.py:607,754-765` | 仅 `aruco_task`；**双向一致已修** |
| DirectParentGuard | `joint_parent.py`；`joint_task.py:11,68` | 无任务门控，全联合任务生效 |
| **supervisor SCHED_RESET_ON_FORK** | `joint_runtime.py:140-146` | **仅 `aruco_task`**：FIFO/50 + RESET，防后台线程继承实时策略；native/model/FC leader 仍 FIFO/40 |
| **model 线程 RESET_ON_FORK** | `:191-198` | 仅 `role==model 且 ASYNC_MODEL_EVIDENCE`：模型进程内异步写线程不继承 FIFO/40 |
| CPU 阶段采样 | `wksim_core/joint.py:52` | `WKSIM_JOINT_CPU_TIMING=1`（#82 既有候选；15 场将开） |

## mixed/PV 复用的准确条件与资源风险

1. **延迟报告推广**：`joint_runtime.py:607`/`754` 的 `aruco_task` 门扩到
   `fixed_task`；`load_retired_task_report` 双向一致性已就位，无前置修复。
2. **异步证据是成对改动**：开 `WKSIM_JOINT_ASYNC_EVIDENCE` 必须同时接受
   supervisor 的 RESET_ON_FORK 语义（否则后台写线程以 FIFO/50 跑在实时档）；
   开 `ASYNC_MODEL_EVIDENCE` 必须同时给模型进程 RESET_ON_FORK（FIFO/40 同理）。
   对 `joint_quad_dds_mixed_pv_v1` 应设自己的显式实验位并核对 profile 名；
   默认生产保持同步+不 RESET。
3. **准入/资源风险**：joint-profiles.json 的 pin 只记 manifest 身份；
   调度策略/写路径属行为变化，必须在 #82 候选说明里显式声明，不能冒称
   原 evidence pin 已覆盖。FIFO/40-50 与 RESET_ON_FORK 需要 CAP_SYS_NICE 级的
   宿主权限，既有 OSError 回退记录保留。
4. **不变项**：DirectParentGuard、CPU 采样无需改动；倍率合同
   （0.5×、4tick 屏障、8ms 组间隔、100ms、滑窗 2%/1%）不动。

## 下一可实施切片（顺序）

1. 离线切片：defer 门控扩到 FIXED_TASKS + 单元负例（不跑 SITL）。
2. 15 场用既有 CPU 计时先定位组内/组外；若组外与证据写重叠，再开 async
   实验位（连同 RESET_ON_FORK 成对）做 A/B。
3. 定位后才谈 `JointRate.begin_group` 区间采样扩展（需先扩 #82 写入范围）。

## 边界

未改 runtime、未跑测试/构建、未刷新索引、未 nested/commit。#82 三场失败与
tracking-08/14 的 failed 判定保持原状；#83 前置不变。
