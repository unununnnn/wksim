# 26 · Prometheus UDE控制器闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户在同一任务中选择UDE控制器，运行并比较已声明扰动下的响应。

## Acceptance criteria

- [ ] 迁移实际UDE方法和所需状态，记录与上游的必要差异。
- [ ] 复用已落地的控制器选择与姿态出口，不另造任务控制入口。
- [ ] 双栈完成定点、轨迹和约定扰动，按预定超调/稳态/恢复指标判断。
- [ ] 切换与重置不保留旧观测器状态，失败时不回退成PID却报告UDE成功。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [Prometheus PID控制器选择与闭环](https://github.com/unununnnn/wksim/issues/35)

## Parallel boundary

本票建议归属：控制算法。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
