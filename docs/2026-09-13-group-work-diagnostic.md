# MIXED 工作阶段诊断

本场 `joint-public-flight-rfw9nmbb` 在 tick 98684 以 RateUnmet 失败，墙钟耗时 250.403797634 秒。原 1ms、4tick、无追赶、100ms 及物理验收门保持；这场开启了 `group_work_timing`，只能作诊断证据。

有界记录器核验了 24,661 个完整工作组，发现 18 个工作超额组，按预先设定的上限写出前 16 份详细报告，另 2 份计入 `reports_dropped`。没有不完整组或记录器错误。独立读取 rate 原件重算，与全部计数、报告身份和边界一致；未保留详细阶段的两组从 rate 原件仍可识别为 start_tick 80652 和 98044，不能补造其阶段数据。

最后完成组的工作时间未超过周期，随后开始检查触发 100,019,970ns 的累计迟到。因此“记录器 valid”与“飞行通过”是不同结论。正式验证器按诊断标记键的存在拒绝这场证据，已通过的 PV 场保持原记录，不填补缺失的无探针 MIXED 证明。

## 实现与验证

`tools/group_work_timing.py` 默认不接线。私有 producer 的 `timing_census=True` 提供每步已有阶段记录；私有 runner 将两类 CPU 诊断事件交给内存记录器，普通 wire/rate 事件保持原路径，只在工作超额时输出报告，最多 16 份。正常组不写阶段报告。`finish()` 在文件关闭后只收口内存状态；报告写入失败仍传播，不能掩盖业务错误。

CPU 与墙钟读数的观测窗口存在偏移，部分记录 CPU 大于 wall。保存原始读数，不把差值解释成严格的离 CPU 时间，更不能直接归因于飞控、操作系统或 Windows。

主会话合并检查通过 53 项：记录器 27 项、producer 补丁/真实事件 fixture 11 项、独立对抗测试 15 项。真实 fixture 回放输入为 23 条 wire 和 4 条 rate；输出保留 15 条普通 wire、4 条 rate，8 条诊断仅进入内存，产生 1 份工作分解报告。v2 使用实际 producer 输入，全部源码 pin 与回放结果一致；首版不合格回放及更正记录保留。该验证不启动模型，也不证明运行性能。

## 证据与后续

- 原件：Ubuntu-22.04 `/root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb`。
- 选取包：`validation/coordination/cb-evidence-pack-20260913-01/pack`，包含失败结果、压缩 rate、16 份报告及项目源快照。
- 补丁与回放：`validation/coordination/group-work-timing-integration-20260913`、`group-work-diagnostic-20260913-01`。
- 独立审查：`validation/coordination/cb-recorder-review-20260913-01`；合并收据：`rolling-six-20260913-02/recorder-integration.json`。

运行声明 source_unchanged=true、cleanup_errors=[]。后检时 WSL boot 已变化，当前 PGID 全空仅证明当前不存在残留，不能据此声称完成同 boot 的独立清理核验；没有向同号 PID 发信号。

下一步审查实际热路径候选及其目标 Python 版本等价性。每步开销收益需要放入实际累计迟到规律中评估；不能把单次微秒数直接与 100ms 阈值比较，也不能将 Windows 编码测试当作 WSL 飞行收益。未启动新飞行，#84/G6/Full 保持开放。
