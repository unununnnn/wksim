# 29 · 单机规划绕障到真实飞行

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户在固定地图中指定目标，选定Prometheus规划器生成并执行轨迹绕过障碍。

## Acceptance criteria

- [ ] 先冻结一个上游规划器、输入地图和任务profile，不把全部规划算法合在一票。
- [ ] 规划目标到真实飞行的完整路径经过公开控制入口，真值检查到达、碰撞和净空。
- [ ] 无路、取消和重规划不继续旧轨迹；输出命令ID在会话内严格递增。
- [ ] 迁移时修正已核对的上游停止参考被后续轨迹覆盖及每次新建命令导致ID重复的问题，并记录有意差异。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)
- [坡面与障碍场景的物理反馈](https://github.com/unununnnn/wksim/issues/29)
- [双栈混合轴与轨迹跟随](https://github.com/unununnnn/wksim/issues/33)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：规划。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
