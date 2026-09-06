# 05 · 单机多航点任务与取消闭环

状态：completed；2026-09-05 15:14:40 UTC主代理验收关闭并读回。仅本票完成，不代表Full项目完成。[验收记录](https://github.com/unununnnn/wksim/issues/15#issuecomment-5552742286)。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

通过Prometheus任务入口执行多航点任务并可取消，用户看到各阶段进度和实际完成结果。

## Acceptance criteria

- [x] 同一ENU/机体系位置任务分别在双栈完成逐点驻留与降落；使用既有控制集成门槛。
- [x] 取消后不再发送后续航点；已接受飞控动作如何结束按明确契约报告，不伪造即时停止。
- [x] 持续递增命令身份，状态区分受理、接管、运行、完成、失败和取消。
- [x] 测试包含正常多航点、任务取消、无效目标和外部模式切换；观察器不代发控制。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)

## Parallel boundary

本票建议归属：任务。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
