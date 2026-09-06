# 28 · RC位置控制与任务显式交接

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者通过已确认RC输入进行位置/偏航控制，并在RC与任务控制之间显式交接。

## Acceptance criteria

- [ ] 先明确输入设备/模拟源、通道、死区、有效期和失联动作，不以伪RC规避原生解锁检查。
- [ ] 真实双栈验证移动、回中保持、偏航和控制权交接。
- [ ] 断流或外部模式切走后不自动抢回，反馈区分输入失效与飞控模式拒绝。
- [ ] 本票仅位置RC闭环，其他RC/手动模式按来源矩阵继续跟踪。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：RC/控制。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
