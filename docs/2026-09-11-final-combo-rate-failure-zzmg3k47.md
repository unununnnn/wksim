# #83 当前控制最终组合倍率失败

2026-09-11。`joint-public-flight-zzmg3k47` 是准入修复后首个且唯一的新真实 `full_xyz_pv_yaw_v1` 场次。AP mixed manifest SHA256 为 `1e6250ef…e94c`，当前控制 `0DQQz9` manifest SHA256 为 `25edbf81…d610`，epoch 为 `1a4e2ccf023f4bb8bb880bbd2ea96926`。准入、零步初始化、实际 FIFO/nice 调度和双机起飞均成功。

运行在 tick 98,700 以 `rate_unmet/resource_insufficient` 锁存，累计迟到 `100.092095ms`，场均倍率 `0.49975687561984183`，完成 24,665 个四步组。按前一组 work 与下一组 start-to-start creep 正确配对后，24,664 个相邻区间精确闭合为 `99.881013ms = 14.535828ms` 前组 work-over + `85.345185ms` release excess。这只是时间区间分类，不声称 CPU 根因。最大 release excess 是 tick 16,384→16,388 的 `1.401230ms`；此前把 tick 1,924 的 `5.486732ms` 整段 creep 误称为 release excess，未扣除其中 `5.168901ms` 的前组 work-over，现已由 `tools/analyze_joint_rate_intervals.py` 的逐区间闭合校验纠正。

所有当时可形成的完整滑窗在平均倍率门内：23,165 个 10s 窗最坏绝对相对误差 `0.0013936196`（预算 0.02），16,918 个 60s 窗最坏 `0.0006475887`（预算 0.01）。这些是失败后从完整 `rate_group_end` 记录重算的诊断值；正式 PV 审计因运行/清理未 PASS 按设计在第一项终止，不能把滑窗结果单独登记为验收通过。累计 100ms 门没有放宽。

两机都完成第一段 12s P+V 参考、第一段 2s/2s endpoint 驻留及 2s/4s stop 驻留，并各自发出第二段 120 个参考点。最后参考为约 96.924s，倍率故障发生于 98.700s，尚未形成 `pv_2_endpoint_prepared`；第二段 endpoint/stop、LAND 和任务报告均未完成。Control 正常退出，所有 10 个 owned group 的 `remaining_group_members` 均为空；两个 Task 因 manager fault 返回 1，故 `flight_completed=false`，不能称为完整清理 PASS。

原始失败目录含 288 个成员、约 728MB。`tools/archive_joint_flight.py` 逐成员哈希、打包后再逐成员读回，生成 115,850,022 字节归档及 4 个不超过 32MiB 的分片；整档 SHA256 为 `4636a5fa55c6c6bbffd199b5f51bb8a7d437749dab97b65f1039c90bafedef1d`。分片重组哈希与字节数再次独立核对一致，归档不含 `.exe/.dll/.so/.uasset/.slx/.p/.pyc` 或 symlink。

#83 保持 OPEN / needs-triage。下一运行必须先有新的、独立测量的固定开销减负候选；不得重锚、追赶、缩短轨迹/驻留或提高 100ms 门。
