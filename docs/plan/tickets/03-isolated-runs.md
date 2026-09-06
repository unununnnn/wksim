# 03 · 两个独立实验同时运行且互不干扰

状态：2026-09-05 14:00:01 UTC，主代理验收后按completed关闭并读回。证据见[第二批报告](../../2026-09-05_product-second-wave-report.md)。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

同时启动两次独立实验，停止其中一次后另一实验继续执行自己的任务。

## Acceptance criteria

- [x] 启动前检查载具ID、DDS namespace/domain、XRCE身份、端口和输出目录冲突。
- [x] 一套PX4与一套ArduCopter独立实验同时运行，分别保存自己的配置、时间和证据。
- [x] 实验A的启动失败、停止或资源清理不终止B及原有用户进程。
- [x] 界面或CLI明确标注独立实验，不能称为联合场景。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [实验能力预检与候选身份核验](https://github.com/unununnnn/wksim/issues/11)
- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)

## Parallel boundary

本票建议归属：运行编排。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
