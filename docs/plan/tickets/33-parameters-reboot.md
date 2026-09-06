# 33 · 仿真参数操作与飞控重启恢复

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者对已准入仿真参数执行读取和修改，并在飞控重启后重新进入就绪流程。

## Acceptance criteria

- [ ] 先锁定双栈对应的最小参数白名单、单位、可写范围和是否需重启，不把任意参数暴露给客户端。
- [ ] 读写有真实确认和生效状态；未支持的参数或不安全时机明确拒绝。
- [ ] 仅在隔离且已落地的SITL中重启自己创建的飞控；旧代次命令不再有效。
- [ ] 重启后重新发现、定位和显式接管，不能把进程启动当作飞控就绪或自动重放任务。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：参数/生命周期。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
