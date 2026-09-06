# 21 · 深度相机与由深度生成的点云

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户配置一个深度相机，在已知几何场景中消费深度及带坐标标识的点云。

## Acceptance criteria

- [ ] 标定、距离单位、有效像素、无效深度和点云坐标有明确约定。
- [ ] 以已知平面/障碍验证距离和投影误差，阈值在运行前冻结。
- [ ] 图像、点云和状态关联同一采样身份，断流不阻塞物理。
- [ ] 明确本票是深度相机及其点云，不冒称扫描LiDAR、语义分割或所有视觉传感器均已完成。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [带时间与标定的真实RGB相机](https://github.com/unununnnn/wksim/issues/30)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：视觉传感器。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
