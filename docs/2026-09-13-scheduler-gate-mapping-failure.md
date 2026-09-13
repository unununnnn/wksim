# 调度 gate / kernel mapping 唯一真实诊断失败

2026-09-13。此文件只保留 Ubuntu-22.04 原件 `/root/wksim-scheduler-probe-20260913-isolated-01` 的紧凑、可复核索引；没有复制原件、重新运行 probe、修改代码或提交。来源提交为 `bdd39ee`，run 为 `scheduler-a9e390ff8a6e`，epoch 为 `2557d7a0bdcf48cab2e1bb6d7982403f`。

原件树重新按 POSIX 相对路径排序并逐文件计算：137 个 regular files，2,876,292 bytes；manifest SHA256 为 `9d41706fcafc24aae050f2e7888ca2c437d82742d7e7038c3fab346e28c29830`。定义是对每个 `path<TAB>bytes<TAB>file_sha256<LF>` 的 UTF-8 行做 SHA-256，路径相对于原件根目录。机器可读索引见 [`summary.json`](../validation/33-scheduler-gate-mapping-failure-20260913/summary.json)。

失败有两个独立信号。`report.json` 的 outer error 是 `RuntimeError: First-step gate-release proof identity differs`；`collector.log` 同时报告 `ValueError: Kernel PID mapping ambiguous: ap_fc/arducopter`，collector 返回码为 1。bootstrap token 在 monotonic ns `115491101045` 发布，早于 gate-ready 的 `115620393685`；gate release 在 `115622995296`，但首步 release proof 身份仍不一致。两项都必须离线修复并独立审查，不能把其中一项的存在解释成另一项已通过。

inner preflight 返回 0，耗时 `23.223985977s`，实际记录为 `SCHED_OTHER`、policy value 0、priority 0、nice 0。它只证明 inner preflight 的这一项观察成立，不证明 manager、FC、model 或 collector 的完整调度捕获成立。

最终 authority physical tick 只有 25（last barrier/input tick 为 24），`flight_completed=false`、`action_results=[]`、`tasks={}`，没有启动 flight task。正式 active token `capture/capture-active.json` 不存在；collector 记录 `complete=false`，因此没有 formal active token 或完整 capture。这个 25-tick 诊断片段不能登记为飞行、倍率、调度捕获或验收证据。

清理字段是可复核的：manager rc 0，collector rc 1；manager group 与 epoch group 均无残留，epoch groups retired，trace instance removed，cleanup_errors 为空，sources unchanged 为 true。manager rc 0 仅表示受控结束，不能覆盖 collector 失败或 gate proof 失败。

关键原件的字节数和 SHA256 全部列在 `summary.json`。本记录不声明真实 flight、完整 trace、ACK/arrival 或 G0–G6 通过。下一步是离线修复并独立审查 gate-release identity 绑定和 `ap_fc/arducopter` PID 映射，再由主控决定是否需要新的真实 probe；在此之前禁止重跑本场 probe，禁止放宽 gate、mapping、时钟/物理 tick、ACK 或 cleanup 门槛。
