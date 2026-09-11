# ArUco PX4 WorkQueue v2 第 20 场结果

`validation/40-aruco-tracking-20-px4-workqueue` 使用 PX4 WorkQueue 组件诊断 v2 候选运行。run 为 `aruco-track-5bbf33c939`，scene epoch 为 `f70fb33ea2cc46e0a14e2738c3bbe72f`。两机已解锁并进入 AP 保持、PX4 OFFBOARD 跟踪；采到 55 个可处理 RGB 帧、证明 43 条 PX4 BODY MOVE 后，权威时钟在 tick 65440 以 `rate_unmet/resource_insufficient` 停止。倍率段完成 16,350 个四步组，测得倍率 `0.49961413033348456`，最坏累计迟到 `101.021467ms`。本场没有完成 90 帧、终态 HOLD、降落和完整退场验收，因此仍是失败场，#104/#40 保持开放。

受管 supervisor、两飞控、两个 Control、两模型及证据写入器均已结束；manager 返回 0，进程组无剩余成员，`cleanup_error` 与 writer error 均为空。原件共 456 个成员，逐成员重算后归档为 177,514,459 字节、6 个不超过 32MiB 的分片，整档 SHA256 为 `06bf9c53d91916c733d3a404dc22277b6a0c5866b912f5f82d41d8d071e76c9c`。完整 tar 保留在本机，仓库只保存可重建分片和 `archive.json`。

## 原生诊断边界

v2 日志包含 4 条 SEND、3 条 COMPONENT、2 条 WORK 和 4 条 QUEUE 慢段。两次最大的 WORK 都是 `wq:lp_default` 上的 `parameters`，分别为 `7.063471ms` 和 `6.307290ms`；PX4 源码将该名称定位到 `ParamAutosave::Run()`，它在参数改变后延迟并限频写入默认参数文件。对应 tick 2000 与 5504 的 PX4 原生等待为 `7.326935ms` 与 `6.579359ms`，四步组工作时间为 `10.766623ms` 与 `9.700916ms`。另有 `wq:nav_and_controllers` 的 `3.160077ms` 与 `wq:rate_ctrl` 的 `2.260610ms` 队列段。日志证明这些队列工作与屏障等待重叠，不证明它们是整个倍率失败的唯一原因。

最后一组 65436–65440 开始时已经累积 `98.624704ms` 相位迟到，组工作 `10.396763ms`，结束达到 `101.021467ms`。该窗口没有大于 2ms 的原生等待、WorkQueue 慢段或 GC；tick 65436/65437 的已采样 runtime 总耗时约 `3.08ms`/`6.57ms`，后者包含约 `4.29ms` physics 和 `0.996ms` clock publish。失败是此前累计相位债务遇到正常组内波动越过冻结门槛，不能归因于 tick 65440 的一个新原生尖峰。采样只覆盖部分 tick，原生日志也只记录超过阈值的段，因此仍不能从本场唯一确定全部累计债务来源。

## 独立审计

- publisher/writer 图通过：AP 135、PX4 176 个离散图快照均绑定实际 writer 和 raw GID；结论只覆盖采样时刻的排他性。
- native MOVE 复审通过：43 条 PX4 MOVE 均与原生 TrajectorySetpoint 字段精确对应，0 failure、0 unresolved。
- 初版 MOVE 报告的 13,174 条 `state_identity_differs` 全来自无公共命令的 AP 协同栈。审计器错误地用 `None` 作为该栈 control epoch；修复后以首条 SessionState 的实际 epoch 锚定，并保留命令存在时的命令/状态交叉核验。WSL 真实消息 CDR 的 15 项测试通过，原失败报告未覆盖。
- physical、rate、raw、native HOLD、native timestamp 都因本场在倍率门提前停止而保持失败，不能用已证明的 43 条 MOVE 把整场改判为通过。

下一次真实运行只能基于已独立复核、能减少累计热路径开销且保持每步 `/clock`、原生输入/时钟屏障、无追赶/隐式重锚和 100ms 门槛的改动；不重复运行相同 v2 候选。
