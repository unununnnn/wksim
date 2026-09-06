# 34 · 单电机效率故障的可复现实验

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户在固定模型任务中按事件计划降低一个电机效率并观察实际响应。

## Acceptance criteria

- [ ] 故障时刻、持续时间、目标电机和幅值进入运行配置及记录。
- [ ] 事件映射到实际模型执行器路径，真值和飞控反馈反映该电机变化。
- [ ] 使用预先批准的安全/失联与数值预算，重置后故障状态清除。
- [ ] 无故障回归和相同种子重复实验通过；卡死/关闭及其他电气故障继续列为独立扩展。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [悬停期间DDS断连与显式恢复](https://github.com/unununnnn/wksim/issues/22)
- [四旋翼参数保存导入与真实运行](https://github.com/unununnnn/wksim/issues/24)

## Parallel boundary

本票建议归属：故障/模型。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
