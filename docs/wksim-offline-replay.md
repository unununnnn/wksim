# 已有实验记录的离线回看

运行时只用Python标准库，不导入ROS、不连接网络、不创建飞控或控制发布者。输入为已停止实验的目录；输入文件只读，导出只能新建到该目录之外。

在仓库根运行：

```powershell
python -m Simulator.wksim_runtime.replay validation/arducopter-dds-urq9hofr
python -m Simulator.wksim_runtime.replay validation/arducopter-dds-urq9hofr --record prometheus:100
python -m Simulator.wksim_runtime.replay validation/px4-dds-epf9gukj --clock fc_boot --from-time 40 --to-time 45 --output px4-records-40-45.json
python -m Simulator.wksim_runtime.replay validation/arducopter-dds-urq9hofr --events-only --output ap-events.json
python -m unittest validation.test_wksim_replay -v
```

默认显示各流数量、文件哈希、已记录运行结果及诊断统计。导出保留逐条原始JSON文本、原始行哈希、行号、源时间/时基、各流接收时间、命令/ACK/事件类别和状态有效性。按文件、行顺序回看，不把受理或ACK改写为动作完成。

旧记录的物理时间、飞控启动时间、ROS时钟和各记录器墙钟起点不能直接混排。工具将它们明确区分；时间筛选必须指定clock。关联仅基于同一个输入实验和原始消息，未记录的跨时基映射、run_id或epoch保持unknown，不用目录名补造。原始NaN/Infinity保留在raw_json中，解析载荷用nonfinite标记，不转换为有效的零坐标。

缺文件、格式错误、末行未结束、明确序号不连续、源时间倒退均有诊断；connected/odom_valid为false标为recorded_invalid。旧降采样真值没有连续记录序号，工具不把它的执行器frame差值当成丢包，也不能证明未记录区间完整。读取前后哈希不同则拒绝活跃/变化中的证据。

当前单文件上限64MiB，内存中读取；超限明确拒绝。该切片是CLI/JSON记录回看，不是确定性重新仿真、产品日志写入、实时状态分发或wksim图形界面，后者由相应独立票据完成。

2026-09-05最终核验：AP20,144条、PX4 21,537条原始记录的字节、行序和输入哈希一致；专属2项测试和包含它们的最终80项回归均通过。最终导出路径/哈希及早期夹具错误见[回看清单](../validation/offline-replay-20260905/result.json)，真实产品集成边界见[首批报告](2026-09-05_product-first-wave-report.md)。
