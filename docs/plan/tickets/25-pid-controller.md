# 25 · Prometheus PID控制器选择与闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户选择迁移的Prometheus PID外部位置控制器，经姿态/推力出口执行定点与固定轨迹。

## Acceptance criteria

- [ ] 保留固定上游来源，记录初始化、重置、质量和推力映射。
- [ ] 界面/配置和结果显示实际使用PID，不能仅修改标签仍使用飞控位置环。
- [ ] 双栈定点、轨迹和预先声明扰动工况按冻结指标通过。
- [ ] 建立实际需要的控制器选择/复位契约，供后续UDE与NE复用，原ROS1代码保持不变。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [双栈姿态与推力出口](https://github.com/unununnnn/wksim/issues/34)

## Parallel boundary

本票建议归属：控制算法。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
