# 35 · GNSS中断与状态有效性恢复

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户按计划中断GNSS输入，观察定位有效性、飞控和任务控制恢复行为。

## Acceptance criteria

- [ ] 注入位置在真实传感器链，不仅修改显示标志；保留原始GPS质量与源时间。
- [ ] 定位失效、失联和过期数据不同事件分别可观察，旧坐标不能因新时间戳变成有效。
- [ ] 按已批准策略验证任务撤销、飞控动作和恢复后显式接管。
- [ ] 故障计划、真实传感器/状态/真值及固定预算一并记录，其他传感器故障不自动算通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [悬停期间DDS断连与显式恢复](https://github.com/unununnnn/wksim/issues/22)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)

## Parallel boundary

本票建议归属：故障/传感器。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
