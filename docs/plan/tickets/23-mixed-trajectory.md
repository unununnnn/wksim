# 23 · 双栈混合轴与轨迹跟随

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

2026-09-09：#32已关闭。完整XYZ P+V+yaw的AP候选及新控制包已完成显式实验准入、双栈两段轨迹/停止保持/新锚点/落地和重复原始审计；[报告](../../2026-09-09-pv-flight-report.md)含所有失败、版本和边界。它不是XY速度/Z位置，不能独立关闭本票；真正混合轴新原生子模式及控制接缝正在实施，正式profile/最终生产提升及原生边界仍未完成。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者执行混合位置/速度目标和一条固定轨迹，未激活轴不会变成零目标。

## Acceptance criteria

- [ ] 分别验证速度XY/位置Z等批准组合及轨迹位置/速度/偏航语义。
- [ ] 加速度前馈是否执行必须显式声明，不能因消息带字段就声称生效。
- [ ] 固定轨迹的误差、驻留和恢复门槛预先确定，两栈保存真值证据。
- [ ] 模式切换、静止轴保持和停止信号不复用旧锚点；原命令/输出差分回归保持通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [双栈速度与偏航控制能力](https://github.com/unununnnn/wksim/issues/32)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：原生控制。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
