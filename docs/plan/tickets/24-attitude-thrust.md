# 24 · 双栈姿态与推力出口

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者通过批准姿态/推力profile驱动双栈，并可观察实际姿态和推力响应。

## Acceptance criteria

- [ ] 明确FLU/FRD四元数、归一化推力、符号、范围及标定条件。
- [ ] AP原生姿态出口若需候选变更须实际构建、核验身份并真实运行。
- [ ] 两栈固定姿态阶跃及恢复工况通过预先预算，有限值和非单位四元数等非法输入拒绝。
- [ ] 能力不会默认开放给未验证固件，已有位置/速度profile不被隐式替换。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)

## Parallel boundary

本票建议归属：原生控制。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
