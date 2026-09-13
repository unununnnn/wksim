# PX4 真实相机跟踪：首次完整采集与当前审计范围

第十场 `aruco-track-69b75c6f3c` / `e77b1ed46ede49d68e2e68edddc3fd25` 正常完成双机起飞、PX4相机跟踪、遮挡/恢复、双机降落与退场，运行器返回0且无authority fault。采集状态为`captured_pending_independent_audit`，不能替代#104/#40或Full最终验收。

已独立核对：

- 89帧真实RGB及场景读回，像素、PnP、目标速度和遮挡/恢复检查通过。
- 跟踪区间12,001个物理tick：PX4最大跟踪误差0.410998216m，恢复末窗最大误差0.049763611m；未超过预先冻结的0.65/0.3m门槛。两机范围、高度、倾角及最终落地检查通过。
- 五个后台证据流submitted/written字节数与文件实际大小相同，全部线程退场、无错误，队列高水位2（固定容量8）。进程组无残留。
- 原始倍率计划逐组核对通过，无重锚追赶或超100ms。最坏累计迟到82.258203ms；15个完整10s窗最大相对误差约0.207%，首60s窗也通过1%门槛。本场没有完整60s双机空中窗口，不能当作完整三epoch G2倍率运动阶段验收。
- 实际调度快照：监督器主线程FIFO/50且带reset-on-fork；其余监督器线程、Control/Agent/Task为SCHED_OTHER/0；模型主线程FIFO/40。PX4保留其自身设置的其它原生线程策略，未宣称所有飞控线程都为40。

证据：`validation/40-aruco-tracking-10`、`validation/coordination/aruco-10-physical-audit.json`、`validation/coordination/aruco-10-rate-audit-final.json`。所有先前失败保持原状。

剩余必需项包括：原始失效/撤回/恢复控制链在本场的审计、BODY MOVE逐字段原生设定值关联与发布者身份核验、ArduCopter作为相机跟踪载具的对应真实运行。独立内容检查通过不等于这些剩余项已经完成。
