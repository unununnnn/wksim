# 38 · 首期SITL产品流程集成验收

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者按批准的首期清单，从配置到飞行显示再到停止和结果回看，独立复现两套飞控。

## Acceptance criteria

- [ ] 以已批准首期机型/场景、矩阵和门槛执行完整产品黑盒验收，保留既有回归。
- [ ] 记录产品发命令、真实FC动作、独立物理真值和UE状态的同一证据链，失败样本保留。
- [ ] 核验核心不依赖Gazebo、原版程序、闭源DLL或MATLAB运行时；所有运行资源可控收尾。
- [ ] MATLAB按首期决议验证契约或实际桥，不能自动提升范围；首期通过不关闭完整Full目标、联合场景或其他未完成分支。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [实验能力预检与候选身份核验](https://github.com/unununnnn/wksim/issues/11)
- [两个独立实验同时运行且互不干扰](https://github.com/unununnnn/wksim/issues/13)
- [单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)
- [已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16)
- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)
- [wksim界面配置到任务结果的完整流程](https://github.com/unununnnn/wksim/issues/18)
- [悬停期间DDS断连与显式恢复](https://github.com/unununnnn/wksim/issues/22)
- [地面站查看与显式控制权交接](https://github.com/unununnnn/wksim/issues/42)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：主集成。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
