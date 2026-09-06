# 13 · 四旋翼固定工况数值对照

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

对一个有明确来源的四旋翼模型，在预先约定工况和误差预算下生成可复查的数值对照。

## Acceptance criteria

- [ ] 运行前冻结模型、初态、参数、输入、种子、采样时刻、观测量和误差预算。
- [ ] 对照独立模型与合法可用参考；无法观测的量单列，不能用有限数值检查代替精度。
- [ ] 输出逐量误差与完整失败记录，不事后放宽阈值，也不把控制任务门槛当作物理预算。
- [ ] 在缺少参考样本或授权时精确报告阻塞，不声称当前Full应用版本已核实。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：模型/数值。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
