# 末尾 HOLD 原生执行边界

独立 CDR 检查定位了两场完整采集的剩余缺口。AP 第13场 request90（CURRENT_POS_HOVER）与91（LAND）在同一权威刻度69820发送，前者没有出现在任何 SessionState.last_request_id。PX4 第10场 request91 的悬停已出现在状态中，但在后续 LAND 前没有原生位置目标样本。公共接受事件不能证明原生发布。

`tools/audit_aruco_native_holds.py` 按相邻连续 SessionState 的 RMW source_timestamp 将每个原生样本归到随后同tick状态；使用首次执行悬停状态的冻结位置和归一化四元数航向，独立计算 PX4 NED float32 或 AP home-relative 经纬度/高度/航向。AP 11段169个样本、PX4中途14段165个样本逐字段一致。初始接管不在本工具范围，两个末尾缺口均保持 pending，未提升整场状态。命令接受、损失因果及发布者身份仍由各自独立审计负责。

修复仅作用于显式 ArUco 任务：最终悬停之后，先观察该 request 的真实原始 SessionState，再观察时间更新的原生位置目标和它之后的 SessionState，最后才允许 LAND。等待沿用冻结的0.5s ROS时间超时，失败立即退出，不用固定 sleep 或放宽倍率门槛。原始记录器仅为每个固定频道保留最后一个已写入记录，内存按频道数有界；正常跟踪循环不增加反序列化。

`validation/test_aruco_final_hold.py` 覆盖真实CDR、两栈发布次序、同刻度/旧原生样本、缺失执行状态、已被LAND替代和陈旧公共状态。WSL 与原任务/记录器测试合计42项通过；Windows37项通过、5项因无ROS跳过。运行时修复尚待下一场真实验证，不修改第10/13场原件。

诊断输出在 `validation/coordination/aruco-{10,13-ap}-native-holds-*.json`。早期检查器对未执行命令直接中止的失败输出也保留，后续版本显式列出 unresolved，继续检查其它已执行 HOLD。
