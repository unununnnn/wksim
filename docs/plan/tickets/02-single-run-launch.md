# 02 · 正式入口启动与停止一次双栈可选实验

状态：2026-09-05主代理已验收本机实现；对应工单[ #12 ](https://github.com/unununnnn/wksim/issues/12)，具体证据与剩余边界见完成评论。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用同一实验配置选择PX4或ArduCopter，启动产品节点，执行现有共同位置任务，在已落地后停止。

## Acceptance criteria

- [x] 复用当前已验证候选和正常任务，不由诊断观察器代发原生命令。
- [x] 就绪顺序依实际状态推进，配置中明确运行身份、模型、命名空间和资源；不要求MATLAB、Gazebo或原版应用运行。
- [x] PX4和ArduCopter分别经正式入口完成起飞、保持、航点、降落并输出结果。
- [x] 部分启动失败或已落地停止只回收本次创建的进程，空中停止动作不在本票擅自确定。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

None（可立即开始）

## Parallel boundary

本票建议归属：运行编排。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
